"""PitchTimePage — Pitch shifting, time stretching, key transposition, and vocal isolation."""
import os, threading
import tkinter as tk
from tkinter import filedialog

from limewire.core.theme import T
from limewire.core.constants import PITCH_SEMITONE_RANGE, TEMPO_RANGE
from limewire.core.audio_backend import _audio
from limewire.ui.scroll_frame import ScrollFrame
from limewire.ui.widgets import (ClassicBtn, LimeBtn, GroupBox,
                                  ClassicEntry, ClassicCombo, ClassicProgress,
                                  PageSettingsPanel, GearButton)
from limewire.services.audio_processing import pitch_shift_audio, time_stretch_audio, run_demucs
from limewire.services.analysis import analyze_bpm_key
from limewire.utils.helpers import open_folder

KEY_NAMES_FULL=["C","C#","D","D#","E","F","F#","G","G#","A","A#","B"]
ALL_KEYS=[f"{n} {m}" for m in ["Major","Minor"] for n in KEY_NAMES_FULL]


class PitchTimePage(ScrollFrame):
    """Pitch shifting, time stretching, key transposition, and vocal isolation."""
    def __init__(self,parent,app):
        super().__init__(parent); self.app=app
        self._detected_bpm=None; self._detected_key=None; self._output_file=None
        self._build(self.inner)

    def _build(self,p):
        # Source
        fg=GroupBox(p,"Source Audio"); fg.pack(fill="x",padx=10,pady=(10,6))
        fr=tk.Frame(fg,bg=T.BG); fr.pack(fill="x")
        self._settings_panel=PageSettingsPanel(p,"pitchtime",self.app,[
            ("semitone_range","Semitone Range","choice","12",{"choices":["6","12","24"]}),
        ])
        self._gear=GearButton(fr,self._settings_panel)
        self._gear.pack(side="right")
        self.file_var=tk.StringVar()
        ClassicEntry(fr,self.file_var,width=45).pack(side="left",fill="x",expand=True,ipady=2,padx=(0,8))
        ClassicBtn(fr,"Browse...",self._browse).pack(side="left",padx=(0,6))
        LimeBtn(fr,"Detect BPM/Key",self._detect,width=14).pack(side="left")
        self.detect_lbl=tk.Label(fg,text="Load a file to detect BPM and key",font=T.F_BODY,bg=T.BG,fg=T.TEXT_DIM,anchor="w")
        self.detect_lbl.pack(fill="x",pady=(4,0))

        # Pitch shift
        pg=GroupBox(p,"Pitch Shift"); pg.pack(fill="x",padx=10,pady=(0,6))
        pr=tk.Frame(pg,bg=T.BG); pr.pack(fill="x")
        tk.Label(pr,text="Semitones:",font=T.F_BODY,bg=T.BG,fg=T.TEXT).pack(side="left",padx=(0,4))
        self.semi_var=tk.IntVar(value=0)
        self.semi_scale=tk.Scale(pr,from_=-PITCH_SEMITONE_RANGE,to=PITCH_SEMITONE_RANGE,
            orient="horizontal",variable=self.semi_var,length=200,
            bg=T.BG,fg=T.TEXT,troughcolor=T.TROUGH,highlightthickness=0,font=T.F_SMALL)
        self.semi_scale.pack(side="left",padx=(0,8))
        tk.Label(pr,text="Target Key:",font=T.F_BODY,bg=T.BG,fg=T.TEXT).pack(side="left",padx=(0,4))
        self.target_key_var=tk.StringVar(value="")
        ClassicCombo(pr,self.target_key_var,["(auto)"]+ALL_KEYS,width=12).pack(side="left",padx=(0,8))
        LimeBtn(pr,"Shift Pitch",self._pitch_shift,width=12).pack(side="left")

        # Time stretch
        tg=GroupBox(p,"Time Stretch"); tg.pack(fill="x",padx=10,pady=(0,6))
        tr=tk.Frame(tg,bg=T.BG); tr.pack(fill="x")
        tk.Label(tr,text="Rate:",font=T.F_BODY,bg=T.BG,fg=T.TEXT).pack(side="left",padx=(0,4))
        self.rate_var=tk.DoubleVar(value=1.0)
        self.rate_scale=tk.Scale(tr,from_=TEMPO_RANGE[0],to=TEMPO_RANGE[1],resolution=0.01,
            orient="horizontal",variable=self.rate_var,length=200,
            bg=T.BG,fg=T.TEXT,troughcolor=T.TROUGH,highlightthickness=0,font=T.F_SMALL)
        self.rate_scale.pack(side="left",padx=(0,8))
        tk.Label(tr,text="Target BPM:",font=T.F_BODY,bg=T.BG,fg=T.TEXT).pack(side="left",padx=(0,4))
        self.target_bpm_var=tk.StringVar(value="")
        ClassicEntry(tr,self.target_bpm_var,width=8).pack(side="left",ipady=2,padx=(0,6))
        ClassicBtn(tr,"Calc Rate",self._calc_rate).pack(side="left",padx=(0,8))
        LimeBtn(tr,"Stretch",self._time_stretch,width=10).pack(side="left")

        # Vocal isolation
        vg=GroupBox(p,"Vocal Isolation (Demucs)"); vg.pack(fill="x",padx=10,pady=(0,6))
        vr=tk.Frame(vg,bg=T.BG); vr.pack(fill="x")
        tk.Label(vr,text="Mode:",font=T.F_BODY,bg=T.BG,fg=T.TEXT).pack(side="left",padx=(0,4))
        self.vocal_mode_var=tk.StringVar(value="Vocals Only")
        ClassicCombo(vr,self.vocal_mode_var,["Vocals Only","Instrumental","Full 4-Stem"],width=14).pack(side="left",padx=(0,8))
        tk.Label(vr,text="Model:",font=T.F_BODY,bg=T.BG,fg=T.TEXT).pack(side="left",padx=(0,4))
        self.demucs_model_var=tk.StringVar(value="htdemucs")
        ClassicCombo(vr,self.demucs_model_var,["htdemucs","htdemucs_ft","mdx_extra"],width=14).pack(side="left",padx=(0,8))
        LimeBtn(vr,"Process",self._vocal_isolate,width=10).pack(side="left")
        self.vocal_status=tk.Label(vg,text="Requires Demucs: pip install demucs",font=T.F_SMALL,bg=T.BG,fg=T.TEXT_DIM,anchor="w")
        self.vocal_status.pack(fill="x",pady=(4,0))

        # Output
        og=GroupBox(p,"Output"); og.pack(fill="x",padx=10,pady=(0,10))
        self.out_lbl=tk.Label(og,text="No output yet",font=T.F_BODY,bg=T.BG,fg=T.TEXT_DIM,anchor="w")
        self.out_lbl.pack(fill="x")
        obr=tk.Frame(og,bg=T.BG); obr.pack(fill="x",pady=(4,0))
        LimeBtn(obr,"\u25B6 Play",self._play_result,width=10).pack(side="left",padx=(0,6))
        ClassicBtn(obr,"Open Folder",self._open_folder).pack(side="left")
        self.status_lbl=tk.Label(og,text="",font=T.F_SMALL,bg=T.BG,fg=T.TEXT_DIM,anchor="w")
        self.status_lbl.pack(fill="x",pady=(4,0))
        self.prog=ClassicProgress(og); self.prog.pack(fill="x",pady=(4,0))

    def _browse(self):
        f=filedialog.askopenfilename(filetypes=[("Audio","*.mp3 *.wav *.flac *.ogg *.m4a"),("All","*.*")])
        if f: self.file_var.set(f)

    def _detect(self):
        path=self.file_var.get().strip()
        if not path or not os.path.isfile(path):
            self.detect_lbl.config(text="Select a valid audio file",fg=T.YELLOW); return
        self.detect_lbl.config(text="Analyzing BPM and key...",fg=T.YELLOW)
        def _do():
            result=analyze_bpm_key(path)
            self._detected_bpm=result.get("bpm")
            self._detected_key=result.get("key")
            if result.get("error"):
                self.after(0,lambda:self.detect_lbl.config(text=f"Error: {result['error']}",fg=T.RED))
            else:
                self.after(0,lambda:self.detect_lbl.config(
                    text=f"BPM: {self._detected_bpm}  |  Key: {self._detected_key}",fg=T.LIME_DK))
        threading.Thread(target=_do,daemon=True).start()

    def _pitch_shift(self):
        path=self.file_var.get().strip()
        if not path or not os.path.isfile(path):
            self.status_lbl.config(text="Select a file first",fg=T.YELLOW); return
        semitones=self.semi_var.get()
        if semitones==0:
            self.status_lbl.config(text="Set semitones != 0",fg=T.YELLOW); return
        self.status_lbl.config(text=f"Shifting pitch by {semitones:+d} semitones...",fg=T.YELLOW)
        self.prog["value"]=30
        def _do():
            out,err=pitch_shift_audio(path,semitones)
            if err:
                self.after(0,lambda:(self.status_lbl.config(text=f"Error: {err}",fg=T.RED),
                    self.prog.configure(value=0)))
            else:
                self._output_file=out
                self.after(0,lambda:(
                    self.out_lbl.config(text=os.path.basename(out),fg=T.LIME_DK),
                    self.status_lbl.config(text=f"Pitch shifted {semitones:+d} semitones",fg=T.LIME_DK),
                    self.prog.configure(value=100),
                    self.app.toast(f"Pitch shifted: {os.path.basename(out)}")))
        threading.Thread(target=_do,daemon=True).start()

    def _time_stretch(self):
        path=self.file_var.get().strip()
        if not path or not os.path.isfile(path):
            self.status_lbl.config(text="Select a file first",fg=T.YELLOW); return
        rate=self.rate_var.get()
        if abs(rate-1.0)<0.01:
            self.status_lbl.config(text="Set rate != 1.0",fg=T.YELLOW); return
        self.status_lbl.config(text=f"Time stretching at {rate:.2f}x...",fg=T.YELLOW)
        self.prog["value"]=30
        def _do():
            out,err=time_stretch_audio(path,rate)
            if err:
                self.after(0,lambda:(self.status_lbl.config(text=f"Error: {err}",fg=T.RED),
                    self.prog.configure(value=0)))
            else:
                self._output_file=out
                self.after(0,lambda:(
                    self.out_lbl.config(text=os.path.basename(out),fg=T.LIME_DK),
                    self.status_lbl.config(text=f"Stretched at {rate:.2f}x",fg=T.LIME_DK),
                    self.prog.configure(value=100),
                    self.app.toast(f"Time stretched: {os.path.basename(out)}")))
        threading.Thread(target=_do,daemon=True).start()

    def _calc_rate(self):
        if not self._detected_bpm:
            self.status_lbl.config(text="Detect BPM first",fg=T.YELLOW); return
        try:
            target=float(self.target_bpm_var.get())
            rate=target/self._detected_bpm
            rate=max(TEMPO_RANGE[0],min(TEMPO_RANGE[1],rate))
            self.rate_var.set(round(rate,2))
            self.status_lbl.config(text=f"Rate: {self._detected_bpm:.1f} BPM \u2192 {target:.1f} BPM = {rate:.2f}x",fg=T.LIME_DK)
        except ValueError:
            self.status_lbl.config(text="Enter a valid target BPM",fg=T.YELLOW)

    def _vocal_isolate(self):
        path=self.file_var.get().strip()
        if not path or not os.path.isfile(path):
            self.vocal_status.config(text="Select a file first",fg=T.YELLOW); return
        mode=self.vocal_mode_var.get(); model=self.demucs_model_var.get()
        two_stems=None
        if mode=="Vocals Only": two_stems="vocals"
        elif mode=="Instrumental": two_stems="vocals"
        out_dir=os.path.join(self.app.output_dir,"Stems")
        os.makedirs(out_dir,exist_ok=True)
        self.vocal_status.config(text=f"Running {model} ({mode})... This may take a while.",fg=T.YELLOW)
        self.prog["value"]=20
        def _do():
            result=run_demucs(path,out_dir,model=model,two_stems=two_stems)
            if result is True:
                track_name=os.path.splitext(os.path.basename(path))[0]
                stem_dir=os.path.join(out_dir,model,track_name)
                if mode=="Vocals Only":
                    vocal_file=os.path.join(stem_dir,"vocals.wav")
                    self._output_file=vocal_file if os.path.exists(vocal_file) else stem_dir
                elif mode=="Instrumental":
                    inst_file=os.path.join(stem_dir,"no_vocals.wav")
                    self._output_file=inst_file if os.path.exists(inst_file) else stem_dir
                else:
                    self._output_file=stem_dir
                self.after(0,lambda:(
                    self.out_lbl.config(text=os.path.basename(str(self._output_file)),fg=T.LIME_DK),
                    self.vocal_status.config(text=f"Done! Stems in: {stem_dir}",fg=T.LIME_DK),
                    self.prog.configure(value=100),
                    self.app.toast(f"Vocal isolation complete")))
            else:
                self.after(0,lambda:(
                    self.vocal_status.config(text=f"Error: {str(result)[:80]}",fg=T.RED),
                    self.prog.configure(value=0)))
        threading.Thread(target=_do,daemon=True).start()

    def _play_result(self):
        if self._output_file and os.path.isfile(self._output_file):
            _audio.load(self._output_file); _audio.play()
            self.status_lbl.config(text="Playing...",fg=T.LIME_DK)
        else:
            self.status_lbl.config(text="No output file to play",fg=T.YELLOW)

    def _open_folder(self):
        if self._output_file:
            folder=os.path.dirname(self._output_file) if os.path.isfile(self._output_file) else self._output_file
            open_folder(folder)
