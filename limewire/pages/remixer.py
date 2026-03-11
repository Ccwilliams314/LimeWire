"""RemixerPage — Mix Demucs-separated stems with per-stem volume, pan, mute, solo."""
import os, time, tempfile, threading
import tkinter as tk
from tkinter import ttk, filedialog

from limewire.core.theme import T
from limewire.core.constants import SP_XS, SP_SM, SP_MD, SP_LG
from limewire.core.deps import HAS_PYDUB, _ensure_pydub
from limewire.core.audio_backend import _audio
from limewire.ui.scroll_frame import ScrollFrame
from limewire.ui.widgets import (ClassicBtn, LimeBtn, OrangeBtn, GroupBox,
                                  ClassicEntry, ClassicProgress)
from limewire.ui.toast import show_toast


class RemixerPage(ScrollFrame):
    """Mix Demucs-separated stems with per-stem volume, pan, mute, solo."""
    STEM_COLORS={"vocals":"#2ECC71","drums":"#FD7E14","bass":"#0D6EFD","other":"#6C757D",
                 "piano":"#FFC107","guitar":"#DC3545"}
    def __init__(self,parent,app):
        super().__init__(parent); self.app=app; self._stems={}; self._stem_data={}
        p=self.inner
        tk.Label(p,text="Stem Remixer",font=T.F_H2,bg=T.BG,fg=T.TEXT).pack(anchor="w",padx=SP_LG,pady=(SP_LG,SP_SM))
        tk.Label(p,text="Mix Demucs stems: adjust volume, pan, mute/solo each stem, then export a remix.",
                 font=T.F_BODY,bg=T.BG,fg=T.TEXT_DIM).pack(anchor="w",padx=SP_LG)
        # Browse
        bf=tk.Frame(p,bg=T.BG); bf.pack(fill="x",padx=SP_LG,pady=SP_MD)
        self.dir_var=tk.StringVar()
        ClassicEntry(bf,self.dir_var,width=50).pack(side="left",fill="x",expand=True,padx=(0,SP_SM))
        LimeBtn(bf,"Browse Stems",self._browse).pack(side="left")
        # Channel strips container
        self._strip_frame=tk.Frame(p,bg=T.BG); self._strip_frame.pack(fill="x",padx=SP_LG,pady=SP_SM)
        # Master controls
        mg=GroupBox(p,"Master"); mg.pack(fill="x",padx=SP_LG,pady=SP_SM)
        mf=tk.Frame(mg,bg=T.BG); mf.pack(fill="x")
        tk.Label(mf,text="Master Vol",font=T.F_BODY,bg=T.BG,fg=T.TEXT).pack(side="left")
        self.master_vol=tk.DoubleVar(value=100.0)
        ttk.Scale(mf,from_=0,to=150,variable=self.master_vol,orient="horizontal").pack(side="left",fill="x",expand=True,padx=SP_SM)
        self.master_lbl=tk.Label(mf,text="100%",font=T.F_MONO,bg=T.BG,fg=T.TEXT,width=6)
        self.master_lbl.pack(side="left")
        self.master_vol.trace_add("write",lambda *a:self.master_lbl.config(text=f"{self.master_vol.get():.0f}%"))
        # Buttons
        cf=tk.Frame(p,bg=T.BG); cf.pack(fill="x",padx=SP_LG,pady=SP_SM)
        LimeBtn(cf,"Preview Mix",self._preview).pack(side="left",padx=(0,SP_SM))
        OrangeBtn(cf,"Export Remix",self._export).pack(side="left",padx=(0,SP_SM))
        ClassicBtn(cf,"MIDI Learn",self._midi_learn).pack(side="left",padx=(0,SP_SM))
        self._midi_active=False; self._midi_map={}
        self.status_lbl=tk.Label(p,text="Load stems from a Demucs output folder",font=T.F_BODY,bg=T.BG,fg=T.TEXT_DIM)
        self.status_lbl.pack(anchor="w",padx=SP_LG,pady=SP_SM)
        self.prog=ClassicProgress(p); self.prog.pack(fill="x",padx=SP_LG,pady=(0,SP_SM))

    def _browse(self):
        d=filedialog.askdirectory(title="Select Demucs Stems Folder")
        if not d: return
        self.dir_var.set(d)
        # Clear old strips
        for w in self._strip_frame.winfo_children(): w.destroy()
        self._stems={}; self._stem_data={}
        # Find audio files in folder
        found=[]
        for fn in sorted(os.listdir(d)):
            if fn.lower().endswith((".wav",".mp3",".flac",".ogg",".m4a")):
                found.append(fn)
        if not found:
            self.status_lbl.config(text="No audio files found in folder",fg=T.YELLOW); return
        for fn in found:
            stem_name=os.path.splitext(fn)[0].lower()
            color=self.STEM_COLORS.get(stem_name,"#6C757D")
            sf=tk.Frame(self._strip_frame,bg=T.SURFACE_2,padx=SP_SM,pady=SP_SM,
                        highlightthickness=1,highlightbackground=T.CARD_BORDER)
            sf.pack(fill="x",pady=2)
            # Header row
            hf=tk.Frame(sf,bg=T.SURFACE_2); hf.pack(fill="x")
            tk.Label(hf,text="\u25CF",font=("Segoe UI",12),bg=T.SURFACE_2,fg=color).pack(side="left")
            tk.Label(hf,text=stem_name.title(),font=T.F_BOLD,bg=T.SURFACE_2,fg=T.TEXT).pack(side="left",padx=SP_SM)
            # Mute/Solo
            mute_var=tk.BooleanVar(value=False)
            solo_var=tk.BooleanVar(value=False)
            tk.Checkbutton(hf,text="M",variable=mute_var,font=T.F_BTN,bg=T.SURFACE_2,fg=T.RED,
                           selectcolor=T.INPUT_BG,activebackground=T.SURFACE_2,activeforeground=T.RED).pack(side="right",padx=2)
            tk.Checkbutton(hf,text="S",variable=solo_var,font=T.F_BTN,bg=T.SURFACE_2,fg=T.YELLOW,
                           selectcolor=T.INPUT_BG,activebackground=T.SURFACE_2,activeforeground=T.YELLOW).pack(side="right",padx=2)
            # Volume
            vf=tk.Frame(sf,bg=T.SURFACE_2); vf.pack(fill="x")
            tk.Label(vf,text="Vol",font=T.F_SMALL,bg=T.SURFACE_2,fg=T.TEXT_DIM).pack(side="left")
            vol_var=tk.DoubleVar(value=100.0)
            ttk.Scale(vf,from_=0,to=150,variable=vol_var,orient="horizontal").pack(side="left",fill="x",expand=True,padx=SP_XS)
            vol_lbl=tk.Label(vf,text="100%",font=T.F_MONO,bg=T.SURFACE_2,fg=T.TEXT,width=6); vol_lbl.pack(side="left")
            vol_var.trace_add("write",lambda *a,l=vol_lbl,v=vol_var:l.config(text=f"{v.get():.0f}%"))
            # Pan
            pf=tk.Frame(sf,bg=T.SURFACE_2); pf.pack(fill="x")
            tk.Label(pf,text="Pan",font=T.F_SMALL,bg=T.SURFACE_2,fg=T.TEXT_DIM).pack(side="left")
            pan_var=tk.DoubleVar(value=0.0)
            ttk.Scale(pf,from_=-100,to=100,variable=pan_var,orient="horizontal").pack(side="left",fill="x",expand=True,padx=SP_XS)
            pan_lbl=tk.Label(pf,text="C",font=T.F_MONO,bg=T.SURFACE_2,fg=T.TEXT,width=6); pan_lbl.pack(side="left")
            def _pan_disp(*a,l=pan_lbl,v=pan_var):
                val=v.get()
                l.config(text="C" if abs(val)<5 else f"L{abs(val):.0f}" if val<0 else f"R{val:.0f}")
            pan_var.trace_add("write",_pan_disp)
            self._stems[stem_name]={"file":os.path.join(d,fn),"vol":vol_var,"pan":pan_var,"mute":mute_var,"solo":solo_var}
        self.status_lbl.config(text=f"Loaded {len(found)} stems",fg=T.LIME_DK)

    def _mix_stems(self):
        """Mix all stems according to current settings. Returns pydub AudioSegment or None."""
        _ensure_pydub()
        if not HAS_PYDUB:
            self.status_lbl.config(text="pydub required (pip install pydub)",fg=T.RED); return None
        from pydub import AudioSegment
        any_solo=any(s["solo"].get() for s in self._stems.values())
        mixed=None
        for name,s in self._stems.items():
            if s["mute"].get(): continue
            if any_solo and not s["solo"].get(): continue
            try: seg=AudioSegment.from_file(s["file"])
            except Exception as e:
                self.status_lbl.config(text=f"Error loading {name}: {e}",fg=T.RED); return None
            # Volume
            vol=s["vol"].get()/100.0
            if vol<=0: continue
            seg=seg+( 20*__import__("math").log10(vol) if vol>0 else -120)
            # Pan
            pan_val=s["pan"].get()/100.0
            if abs(pan_val)>0.05: seg=seg.pan(pan_val)
            if mixed is None: mixed=seg
            else:
                # Match lengths
                if len(mixed)<len(seg): mixed=mixed+AudioSegment.silent(duration=len(seg)-len(mixed))
                elif len(seg)<len(mixed): seg=seg+AudioSegment.silent(duration=len(mixed)-len(seg))
                mixed=mixed.overlay(seg)
        if mixed is None:
            self.status_lbl.config(text="No stems to mix (all muted?)",fg=T.YELLOW); return None
        # Master volume
        mvol=self.master_vol.get()/100.0
        if mvol>0 and abs(mvol-1.0)>0.01:
            mixed=mixed+(20*__import__("math").log10(mvol))
        return mixed

    def _preview(self):
        self.status_lbl.config(text="Mixing...",fg=T.YELLOW); self.prog["value"]=30
        def _do():
            mixed=self._mix_stems()
            if mixed is None: self.after(0,lambda:self.prog.configure(value=0)); return
            fd,tmp=tempfile.mkstemp(suffix=".wav",prefix="_lw_remix_")
            os.close(fd)
            try:
                mixed.export(tmp,format="wav")
                _audio.load(tmp); _audio.play()
                self.after(0,lambda:(self.status_lbl.config(text="Playing preview...",fg=T.LIME_DK),self.prog.configure(value=100)))
            finally:
                try: os.unlink(tmp)
                except OSError: pass
        threading.Thread(target=_do,daemon=True).start()

    def _export(self):
        path=filedialog.asksaveasfilename(defaultextension=".wav",filetypes=[("WAV","*.wav"),("MP3","*.mp3"),("FLAC","*.flac")])
        if not path: return
        fmt=os.path.splitext(path)[1].lstrip(".") or "wav"
        self.status_lbl.config(text="Mixing and exporting...",fg=T.YELLOW); self.prog["value"]=30
        def _do():
            mixed=self._mix_stems()
            if mixed is None:
                self.after(0,lambda:self.status_lbl.config(text="Mix failed",fg=T.RED)); return
            self.after(0,lambda:self.prog.configure(value=60))
            mixed.export(path,format=fmt)
            self.after(0,lambda:(self.status_lbl.config(text=f"Exported: {os.path.basename(path)}",fg=T.LIME_DK),
                self.prog.configure(value=100),self.app.toast(f"Remix exported: {os.path.basename(path)}")))
        threading.Thread(target=_do,daemon=True).start()

    def _midi_learn(self):
        """Toggle MIDI learn mode for mapping controllers to stem faders."""
        try:
            import mido
        except ImportError:
            show_toast(self.app,"Install mido for MIDI: pip install mido python-rtmidi","error"); return
        if self._midi_active:
            self._midi_active=False
            self.status_lbl.config(text="MIDI learn disabled",fg=T.TEXT_DIM); return
        self._midi_active=True
        self.status_lbl.config(text="MIDI Learn active \u2014 move a fader, then click a stem volume slider",fg=T.ORANGE)
        def _listen():
            import mido
            try:
                ports=mido.get_input_names()
                if not ports:
                    self.after(0,lambda:self.status_lbl.config(text="No MIDI devices found",fg=T.RED))
                    self._midi_active=False; return
                with mido.open_input(ports[0]) as port:
                    self.after(0,lambda:self.status_lbl.config(text=f"Listening on {ports[0]}... Move a control",fg=T.YELLOW))
                    while self._midi_active:
                        for msg in port.iter_pending():
                            if msg.type=="control_change":
                                cc=msg.control; val=msg.value
                                # Map CC to any stem that has focus or the first unassigned
                                if cc not in self._midi_map:
                                    stem_names=list(self._stems.keys())
                                    idx=len(self._midi_map)%len(stem_names) if stem_names else 0
                                    if idx<len(stem_names):
                                        self._midi_map[cc]=stem_names[idx]
                                        sn=stem_names[idx]
                                        self.after(0,lambda s=sn,c=cc:self.status_lbl.config(
                                            text=f"CC{c} \u2192 {s.title()} volume",fg=T.LIME_DK))
                                if cc in self._midi_map:
                                    target=self._midi_map[cc]
                                    if target in self._stems:
                                        vol_pct=val/127.0*150.0
                                        self.after(0,lambda t=target,v=vol_pct:self._stems[t]["vol"].set(v))
                        time.sleep(0.01)
            except Exception as e:
                self.after(0,lambda:self.status_lbl.config(text=f"MIDI error: {str(e)[:50]}",fg=T.RED))
                self._midi_active=False
        threading.Thread(target=_listen,daemon=True).start()
