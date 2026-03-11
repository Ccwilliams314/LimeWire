"""RecorderPage — Microphone recording with VU meter, live waveform, and Whisper transcription."""
import os, threading, tempfile, time
import tkinter as tk
from tkinter import filedialog, messagebox

from limewire.core.theme import T
from limewire.core.constants import (
    RECORDER_SAMPLE_RATE, RECORDER_CHANNELS, RECORDER_CHUNK, RECORDER_VU_UPDATE_MS,
)
from limewire.core.deps import (
    _ensure_sounddevice, _ensure_whisper, _ensure_pydub, _ensure_loudness,
    HAS_NUMPY, HAS_SOUNDDEVICE, HAS_PYDUB,
    sd_mod, whisper_mod, sf, AudioSegment, np,
)
from limewire.core.audio_backend import _audio
from limewire.ui.scroll_frame import ScrollFrame
from limewire.ui.widgets import (ClassicBtn, LimeBtn, OrangeBtn, GroupBox,
                                  ClassicEntry, ClassicCombo,
                                  PageSettingsPanel, GearButton)
from limewire.ui.toast import show_toast
from limewire.utils.helpers import sanitize_filename
from limewire.services.audio_processing import _srt_timestamp


class RecorderPage(ScrollFrame):
    """Microphone recording with VU meter, live waveform, and Whisper transcription."""
    def __init__(self,parent,app):
        super().__init__(parent); self.app=app
        self._recording=False; self._stream=None; self._frames=[]
        self._frames_lock=threading.Lock()
        self._recorded_data=None; self._recorded_sr=RECORDER_SAMPLE_RATE
        self._vu_after=None; self._wave_after=None
        self._build(self.inner)

    def _build(self,p):
        # Record controls
        rg=GroupBox(p,"Record"); rg.pack(fill="x",padx=10,pady=(10,6))
        cr=tk.Frame(rg,bg=T.BG); cr.pack(fill="x")
        # -- Settings panel (hidden by default) --
        self._settings_panel = PageSettingsPanel(p, "recorder", self.app, [
            ("sample_rate", "Sample Rate", "choice", "44100",
             {"choices": ["22050", "44100", "48000", "96000"]}),
            ("channels", "Channels", "choice", "1", {"choices": ["1", "2"]}),
            ("vu_warn_threshold", "VU Warn Level", "float", 0.7, {"min": 0.5, "max": 0.9, "increment": 0.05}),
            ("vu_clip_threshold", "VU Clip Level", "float", 0.9, {"min": 0.8, "max": 1.0, "increment": 0.05}),
        ])
        self._gear = GearButton(cr, self._settings_panel)
        self._gear.pack(side="right")
        tk.Label(cr,text="Device:",font=T.F_BODY,bg=T.BG,fg=T.TEXT).pack(side="left",padx=(0,6))
        self.dev_var=tk.StringVar(value="Default")
        self.dev_combo=ClassicCombo(cr,self.dev_var,["Default"],width=30)
        self.dev_combo.pack(side="left",padx=(0,8))
        ClassicBtn(cr,"Refresh",self._refresh_devices).pack(side="left",padx=(0,16))
        self.rec_btn=LimeBtn(cr,"\u25CF Record",self._toggle_record,width=12)
        self.rec_btn.pack(side="left",padx=(0,6))
        self.stop_btn=OrangeBtn(cr,"\u25A0 Stop",self._stop_recording,width=8)
        self.stop_btn.pack(side="left")
        self.timer_lbl=tk.Label(rg,text="00:00.0",font=("Courier New",14,"bold"),bg=T.BG,fg=T.RED)
        self.timer_lbl.pack(anchor="w",pady=(4,0))

        # VU meter
        vg=GroupBox(p,"Level Meter"); vg.pack(fill="x",padx=10,pady=(0,6))
        self.vu_cv=tk.Canvas(vg,bg=T.CANVAS_BG,height=24,highlightthickness=0)
        self.vu_cv.pack(fill="x",padx=4,pady=4)
        self._vu_bar=self.vu_cv.create_rectangle(0,2,0,22,fill=T.LIME,outline="")
        self._vu_peak=self.vu_cv.create_line(0,0,0,24,fill=T.RED,width=2)
        self._peak_val=0.0

        # Live waveform
        wg=GroupBox(p,"Live Waveform"); wg.pack(fill="x",padx=10,pady=(0,6))
        self.live_cv=tk.Canvas(wg,bg=T.CANVAS_BG,height=60,highlightthickness=0)
        self.live_cv.pack(fill="x",padx=4,pady=4)

        # Playback
        pg=GroupBox(p,"Playback"); pg.pack(fill="x",padx=10,pady=(0,6))
        pbr=tk.Frame(pg,bg=T.BG); pbr.pack(fill="x")
        LimeBtn(pbr,"\u25B6 Play",self._play_recorded,width=10).pack(side="left",padx=(0,6))
        OrangeBtn(pbr,"\u25A0 Stop",lambda:_audio.stop(),width=8).pack(side="left")
        self.play_lbl=tk.Label(pg,text="No recording yet",font=T.F_SMALL,bg=T.BG,fg=T.TEXT_DIM,anchor="w")
        self.play_lbl.pack(fill="x",pady=(4,0))

        # Transcription
        tg=GroupBox(p,"Transcription (Whisper)"); tg.pack(fill="x",padx=10,pady=(0,6))
        tr=tk.Frame(tg,bg=T.BG); tr.pack(fill="x")
        tk.Label(tr,text="Model:",font=T.F_BODY,bg=T.BG,fg=T.TEXT).pack(side="left",padx=(0,4))
        self.whisper_model_var=tk.StringVar(value="base")
        ClassicCombo(tr,self.whisper_model_var,["tiny","base","small","medium"],width=10).pack(side="left",padx=(0,8))
        tk.Label(tr,text="Lang:",font=T.F_BODY,bg=T.BG,fg=T.TEXT).pack(side="left",padx=(0,4))
        self.whisper_lang_var=tk.StringVar(value="en")
        ClassicCombo(tr,self.whisper_lang_var,["en","es","fr","de","it","pt","zh","ja","ko","auto"],width=6).pack(side="left",padx=(0,8))
        LimeBtn(tr,"Transcribe",self._transcribe,width=12).pack(side="left",padx=(0,6))
        ClassicBtn(tr,"Export SRT",self._export_srt).pack(side="left")
        self.trans_text=tk.Text(tg,height=6,font=T.F_MONO,bg=T.INPUT_BG,fg=T.TEXT,relief="flat",bd=1,wrap="word")
        self.trans_text.pack(fill="x",padx=4,pady=(4,0))
        self.trans_status=tk.Label(tg,text="Record audio first, then transcribe",font=T.F_SMALL,bg=T.BG,fg=T.TEXT_DIM,anchor="w")
        self.trans_status.pack(fill="x",pady=(2,0))
        self._whisper_segments=[]

        # Save
        sg=GroupBox(p,"Save Recording"); sg.pack(fill="x",padx=10,pady=(0,10))
        sr=tk.Frame(sg,bg=T.BG); sr.pack(fill="x")
        tk.Label(sr,text="Format:",font=T.F_BODY,bg=T.BG,fg=T.TEXT).pack(side="left",padx=(0,4))
        self.save_fmt_var=tk.StringVar(value="wav")
        ClassicCombo(sr,self.save_fmt_var,["wav","mp3","flac","ogg"],width=8).pack(side="left",padx=(0,8))
        tk.Label(sr,text="Filename:",font=T.F_BODY,bg=T.BG,fg=T.TEXT).pack(side="left",padx=(0,4))
        self.save_name_var=tk.StringVar(value="recording")
        ClassicEntry(sr,self.save_name_var,width=20).pack(side="left",fill="x",expand=True,ipady=2,padx=(0,8))
        LimeBtn(sr,"Save",self._save,width=10).pack(side="left")
        self.save_status=tk.Label(sg,text="",font=T.F_SMALL,bg=T.BG,fg=T.TEXT_DIM,anchor="w")
        self.save_status.pack(fill="x",pady=(4,0))

        # Auto-refresh devices on build
        self.after(500,self._refresh_devices)

    def _refresh_devices(self):
        if not _ensure_sounddevice():
            self.dev_combo.configure(values=["Default (sounddevice not installed)"]); return
        try:
            devs=sd_mod.query_devices()
            input_devs=["Default"]
            for i,d in enumerate(devs):
                if d["max_input_channels"]>0:
                    input_devs.append(f"{i}: {d['name']}")
            self.dev_combo.configure(values=input_devs)
        except Exception: pass

    def _get_device_index(self):
        val=self.dev_var.get()
        if val.startswith("Default") or val=="Default": return None
        try: return int(val.split(":")[0])
        except Exception: return None

    def _toggle_record(self):
        if self._recording: self._stop_recording()
        else: self._start_recording()

    def _start_recording(self):
        if not _ensure_sounddevice():
            messagebox.showinfo("LimeWire","sounddevice not installed.\nRun: pip install sounddevice"); return
        if not HAS_NUMPY:
            messagebox.showinfo("LimeWire","numpy required for recording"); return
        self._frames=[]; self._recording=True; self._peak_val=0.0
        self.rec_btn.config(text="\u25CF Recording...",bg=T.RED,fg="#FFFFFF")
        self._start_time=time.time()
        dev_idx=self._get_device_index()
        try:
            self._stream=sd_mod.InputStream(
                samplerate=RECORDER_SAMPLE_RATE,channels=RECORDER_CHANNELS,
                dtype="float32",blocksize=RECORDER_CHUNK,device=dev_idx,
                callback=self._audio_callback)
            self._stream.start()
            self._update_timer()
            self._update_vu()
            self._update_live_wave()
        except Exception as e:
            self._recording=False
            self.rec_btn.config(text="\u25CF Record",bg=T.LIME,fg=T.TEXT)
            messagebox.showerror("Recording Error",str(e)[:200])

    def _audio_callback(self,indata,frames,time_info,status):
        if self._recording:
            with self._frames_lock:
                self._frames.append(indata.copy())

    def _stop_recording(self):
        if not self._recording: return
        self._recording=False
        if self._stream:
            try: self._stream.stop(); self._stream.close()
            except Exception: pass
            self._stream=None
        self.rec_btn.config(text="\u25CF Record",bg=T.LIME,fg=T.TEXT)
        if self._vu_after: self.after_cancel(self._vu_after); self._vu_after=None
        if self._wave_after: self.after_cancel(self._wave_after); self._wave_after=None
        with self._frames_lock:
            frames_copy=list(self._frames); self._frames.clear()
        if frames_copy:
            self._recorded_data=np.concatenate(frames_copy,axis=0)
            dur=len(self._recorded_data)/RECORDER_SAMPLE_RATE
            self.play_lbl.config(text=f"Recorded {dur:.1f}s  ({RECORDER_SAMPLE_RATE}Hz, {RECORDER_CHANNELS}ch)")
            self.trans_status.config(text="Ready to transcribe",fg=T.LIME_DK)
        else:
            self.play_lbl.config(text="No audio captured",fg=T.YELLOW)

    def _update_timer(self):
        if not self._recording: return
        elapsed=time.time()-self._start_time
        m,s=divmod(elapsed,60)
        self.timer_lbl.config(text=f"{int(m):02d}:{s:05.1f}")
        self.after(100,self._update_timer)

    def _update_vu(self):
        if not self._recording: return
        with self._frames_lock:
            chunk=self._frames[-1].copy() if self._frames else None
        if chunk is not None:
            rms=float(np.sqrt(np.mean(chunk**2)))
            db=max(0,min(1,(20*np.log10(rms+1e-10)+60)/60))
            self._peak_val=max(self._peak_val*0.95,db)
            w=self.vu_cv.winfo_width() or 400
            bar_x=int(db*w); peak_x=int(self._peak_val*w)
            color=T.LIME if db<0.7 else (T.YELLOW if db<0.9 else T.RED)
            self.vu_cv.coords(self._vu_bar,0,2,bar_x,22)
            self.vu_cv.itemconfig(self._vu_bar,fill=color)
            self.vu_cv.coords(self._vu_peak,peak_x,0,peak_x,24)
        self._vu_after=self.after(RECORDER_VU_UPDATE_MS,self._update_vu)

    def _update_live_wave(self):
        if not self._recording: return
        cv=self.live_cv; cv.delete("all")
        w=cv.winfo_width() or 600; h=60; mid=h//2
        # Show last ~100 chunks
        recent=self._frames[-100:] if len(self._frames)>100 else self._frames
        if recent:
            all_data=np.concatenate(recent,axis=0).flatten()
            step=max(1,len(all_data)//w)
            for i in range(0,min(len(all_data),w*step),step):
                x=i//step; val=all_data[i] if i<len(all_data) else 0
                y=int(val*mid*2)
                cv.create_line(x,mid-y,x,mid+y,fill=T.LIME)
        self._wave_after=self.after(80,self._update_live_wave)

    def _play_recorded(self):
        if self._recorded_data is None:
            self.play_lbl.config(text="Nothing recorded yet",fg=T.YELLOW); return
        if not _ensure_loudness():
            self.play_lbl.config(text="soundfile needed for playback",fg=T.RED); return
        fd,tmp=tempfile.mkstemp(suffix=".wav",prefix="_lw_rec_")
        os.close(fd)
        try:
            sf.write(tmp,self._recorded_data,RECORDER_SAMPLE_RATE)
            _audio.load(tmp); _audio.play()
        finally:
            try: os.unlink(tmp)
            except OSError: pass
        self.play_lbl.config(text="Playing...",fg=T.LIME_DK)

    def _transcribe(self):
        if self._recorded_data is None:
            self.trans_status.config(text="Record audio first",fg=T.YELLOW); return
        if not _ensure_whisper():
            messagebox.showinfo("LimeWire","openai-whisper not installed.\nRun: pip install openai-whisper"); return
        model_size=self.whisper_model_var.get()
        lang=self.whisper_lang_var.get()
        self.trans_status.config(text=f"Loading Whisper {model_size} model...",fg=T.YELLOW)
        def _do():
            try:
                if not _ensure_loudness():
                    self.after(0,lambda:self.trans_status.config(text="soundfile required",fg=T.RED)); return
                fd,tmp=tempfile.mkstemp(suffix=".wav",prefix="_lw_wh_")
                os.close(fd)
                sf.write(tmp,self._recorded_data,RECORDER_SAMPLE_RATE)
                self.after(0,lambda:self.trans_status.config(text="Transcribing...",fg=T.YELLOW))
                model=whisper_mod.load_model(model_size)
                opts={"language":lang} if lang!="auto" else {}
                result=model.transcribe(tmp,**opts)
                self._whisper_segments=result.get("segments",[])
                text=result.get("text","")
                self.after(0,lambda:(
                    self.trans_text.delete("1.0","end"),
                    self.trans_text.insert("1.0",text),
                    self.trans_status.config(text=f"Transcribed ({len(self._whisper_segments)} segments, lang={result.get('language','?')})",fg=T.LIME_DK)
                ))
            except Exception as e:
                self.after(0,lambda:self.trans_status.config(text=f"Error: {str(e)[:80]}",fg=T.RED))
        threading.Thread(target=_do,daemon=True).start()

    def _export_srt(self):
        if not self._whisper_segments:
            self.trans_status.config(text="Transcribe first",fg=T.YELLOW); return
        path=filedialog.asksaveasfilename(defaultextension=".srt",
            filetypes=[("SRT","*.srt"),("All","*.*")],initialdir=self.app.output_dir)
        if not path: return
        try:
            with open(path,"w",encoding="utf-8") as f:
                for i,seg in enumerate(self._whisper_segments,1):
                    f.write(f"{i}\n")
                    f.write(f"{_srt_timestamp(seg['start'])} --> {_srt_timestamp(seg['end'])}\n")
                    f.write(f"{seg['text'].strip()}\n\n")
            self.trans_status.config(text=f"SRT saved: {os.path.basename(path)}",fg=T.LIME_DK)
            self.app.toast(f"SRT exported: {os.path.basename(path)}")
        except Exception as e:
            self.trans_status.config(text=f"Save error: {str(e)[:60]}",fg=T.RED)

    def _save(self):
        if self._recorded_data is None:
            self.save_status.config(text="Nothing to save",fg=T.YELLOW); return
        fmt=self.save_fmt_var.get(); name=self.save_name_var.get().strip() or "recording"
        name=sanitize_filename(name)
        out_dir=os.path.join(self.app.output_dir,"Recordings"); os.makedirs(out_dir,exist_ok=True)
        path=os.path.join(out_dir,f"{name}.{fmt}")
        self.save_status.config(text="Saving...",fg=T.YELLOW)
        def _do():
            try:
                if fmt=="wav":
                    if not _ensure_loudness():
                        self.after(0,lambda:self.save_status.config(text="soundfile required",fg=T.RED)); return
                    sf.write(path,self._recorded_data,RECORDER_SAMPLE_RATE)
                else:
                    # Use pydub for non-wav formats
                    if not _ensure_pydub():
                        self.after(0,lambda:self.save_status.config(text="pydub required for non-wav",fg=T.RED)); return
                    if not _ensure_loudness():
                        self.after(0,lambda:self.save_status.config(text="soundfile required",fg=T.RED)); return
                    fd,tmp=tempfile.mkstemp(suffix=".wav",prefix="_lw_rtmp_")
                    os.close(fd)
                    try:
                        sf.write(tmp,self._recorded_data,RECORDER_SAMPLE_RATE)
                        seg=AudioSegment.from_wav(tmp)
                        seg.export(path,format=fmt)
                    finally:
                        try: os.unlink(tmp)
                        except OSError: pass
                self.after(0,lambda:(self.save_status.config(text=f"Saved: {os.path.basename(path)}",fg=T.LIME_DK),
                    self.app.toast(f"Recording saved: {os.path.basename(path)}")))
            except Exception as e:
                self.after(0,lambda:self.save_status.config(text=f"Error: {str(e)[:60]}",fg=T.RED))
        threading.Thread(target=_do,daemon=True).start()
