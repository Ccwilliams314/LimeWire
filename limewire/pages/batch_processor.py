"""BatchProcessorPage — Apply operations to many audio files at once."""
import os, threading
import tkinter as tk
from tkinter import filedialog

from limewire.core.theme import T
from limewire.core.constants import SP_XS, SP_SM, SP_MD, SP_LG
from limewire.core.deps import _ensure_pydub, HAS_PYDUB, HAS_FFMPEG
from limewire.ui.scroll_frame import ScrollFrame
from limewire.ui.widgets import (ClassicBtn, LimeBtn, OrangeBtn, GroupBox,
                                  ClassicEntry, ClassicCombo, ClassicCheck,
                                  ClassicListbox, ClassicProgress,
                                  PageSettingsPanel, GearButton)


class BatchProcessorPage(ScrollFrame):
    """Apply operations to many audio files at once."""
    def __init__(self,parent,app):
        super().__init__(parent); self.app=app; self._files=[]; self._cancel=False
        p=self.inner
        # File selection
        fg=GroupBox(p,"Files"); fg.pack(fill="x",padx=SP_LG,pady=(SP_LG,SP_MD))
        tk.Label(fg,text="Add audio files for bulk processing.",
                 font=T.F_BODY,bg=T.BG,fg=T.TEXT_DIM).pack(anchor="w",pady=(0,SP_XS))
        bf=tk.Frame(fg,bg=T.BG); bf.pack(fill="x")
        self._settings_panel=PageSettingsPanel(p,"batch",self.app,[
            ("silence_threshold_db","Silence Threshold (dBFS)","int",-50,{"min":-70,"max":-20}),
            ("fade_curve","Fade Curve","choice","linear",{"choices":["linear","exponential","logarithmic"]}),
        ])
        self._gear=GearButton(bf,self._settings_panel)
        self._gear.pack(side="right")
        LimeBtn(bf,"Add Files",self._add_files).pack(side="left",padx=(0,SP_SM))
        ClassicBtn(bf,"Add Folder",self._add_folder).pack(side="left",padx=(0,SP_SM))
        ClassicBtn(bf,"Clear",self._clear_files).pack(side="left")
        self.file_count_lbl=tk.Label(fg,text="0 files",font=T.F_BODY,bg=T.BG,fg=T.TEXT_DIM)
        self.file_count_lbl.pack(anchor="w",pady=SP_XS)
        self._file_frame,self._file_lb=ClassicListbox(fg,height=6)
        self._file_frame.pack(fill="x",pady=SP_XS)
        # Operations
        og=GroupBox(p,"Operations"); og.pack(fill="x",padx=SP_LG,pady=SP_SM)
        self._op_normalize=tk.BooleanVar(value=False)
        self._op_convert=tk.BooleanVar(value=False)
        self._op_fade_in=tk.BooleanVar(value=False)
        self._op_fade_out=tk.BooleanVar(value=False)
        self._op_trim_silence=tk.BooleanVar(value=False)
        self._op_strip_meta=tk.BooleanVar(value=False)
        # Normalize row
        nf=tk.Frame(og,bg=T.BG); nf.pack(fill="x",pady=2)
        ClassicCheck(nf,"Normalize LUFS",self._op_normalize).pack(side="left")
        tk.Label(nf,text="Target:",font=T.F_SMALL,bg=T.BG,fg=T.TEXT_DIM).pack(side="left",padx=(SP_LG,SP_XS))
        self.target_lufs=tk.DoubleVar(value=-14.0)
        tk.Spinbox(nf,from_=-60,to=0,increment=0.5,textvariable=self.target_lufs,width=6,
                   font=T.F_BODY,bg=T.INPUT_BG,fg=T.TEXT,relief="flat",bd=0,highlightthickness=1,
                   highlightbackground=T.INPUT_BORDER).pack(side="left")
        tk.Label(nf,text="LUFS",font=T.F_SMALL,bg=T.BG,fg=T.TEXT_DIM).pack(side="left",padx=SP_XS)
        # Convert row
        cf=tk.Frame(og,bg=T.BG); cf.pack(fill="x",pady=2)
        ClassicCheck(cf,"Convert Format",self._op_convert).pack(side="left")
        self.out_fmt=tk.StringVar(value="mp3")
        ClassicCombo(cf,self.out_fmt,["mp3","wav","flac","ogg","m4a"],width=8).pack(side="left",padx=(SP_LG,0))
        # Fade rows
        ff=tk.Frame(og,bg=T.BG); ff.pack(fill="x",pady=2)
        ClassicCheck(ff,"Fade In",self._op_fade_in).pack(side="left")
        self.fade_in_ms=tk.IntVar(value=500)
        tk.Spinbox(ff,from_=0,to=10000,increment=100,textvariable=self.fade_in_ms,width=6,
                   font=T.F_BODY,bg=T.INPUT_BG,fg=T.TEXT,relief="flat",bd=0,highlightthickness=1,
                   highlightbackground=T.INPUT_BORDER).pack(side="left",padx=(SP_SM,0))
        tk.Label(ff,text="ms",font=T.F_SMALL,bg=T.BG,fg=T.TEXT_DIM).pack(side="left",padx=SP_XS)
        ClassicCheck(ff,"Fade Out",self._op_fade_out).pack(side="left",padx=(SP_LG,0))
        self.fade_out_ms=tk.IntVar(value=500)
        tk.Spinbox(ff,from_=0,to=10000,increment=100,textvariable=self.fade_out_ms,width=6,
                   font=T.F_BODY,bg=T.INPUT_BG,fg=T.TEXT,relief="flat",bd=0,highlightthickness=1,
                   highlightbackground=T.INPUT_BORDER).pack(side="left",padx=(SP_SM,0))
        tk.Label(ff,text="ms",font=T.F_SMALL,bg=T.BG,fg=T.TEXT_DIM).pack(side="left",padx=SP_XS)
        # Trim & strip
        tf=tk.Frame(og,bg=T.BG); tf.pack(fill="x",pady=2)
        ClassicCheck(tf,"Trim Silence",self._op_trim_silence).pack(side="left")
        ClassicCheck(tf,"Strip Metadata",self._op_strip_meta).pack(side="left",padx=(SP_LG,0))
        # Output
        ofg=GroupBox(p,"Output"); ofg.pack(fill="x",padx=SP_LG,pady=SP_SM)
        of=tk.Frame(ofg,bg=T.BG); of.pack(fill="x")
        self.out_dir_var=tk.StringVar(value=os.path.join(app.output_dir,"Batch"))
        ClassicEntry(of,self.out_dir_var,width=50).pack(side="left",fill="x",expand=True,padx=(0,SP_SM))
        ClassicBtn(of,"Browse",self._browse_out).pack(side="left")
        # Process
        # ── Process ──────────────────────────────────────────────────────────
        ag=GroupBox(p,"Process"); ag.pack(fill="x",padx=SP_LG,pady=SP_SM)
        pf=tk.Frame(ag,bg=T.BG); pf.pack(fill="x")
        LimeBtn(pf,"Process All",self._process).pack(side="left",padx=(0,SP_SM))
        OrangeBtn(pf,"Cancel",self._cancel_proc).pack(side="left")
        self.status_lbl=tk.Label(ag,text="Add files and select operations",font=T.F_BODY,bg=T.BG,fg=T.TEXT_DIM)
        self.status_lbl.pack(anchor="w",pady=(SP_XS,0))
        self.prog=ClassicProgress(ag); self.prog.pack(fill="x",pady=(SP_XS,0))

    def _add_files(self):
        fs=filedialog.askopenfilenames(filetypes=[("Audio","*.mp3 *.wav *.flac *.ogg *.m4a *.aac")])
        for f in fs:
            if f not in self._files: self._files.append(f); self._file_lb.insert("end",os.path.basename(f))
        self.file_count_lbl.config(text=f"{len(self._files)} files")

    def _add_folder(self):
        d=filedialog.askdirectory()
        if not d: return
        exts=(".mp3",".wav",".flac",".ogg",".m4a",".aac")
        for fn in sorted(os.listdir(d)):
            fp=os.path.join(d,fn)
            if fn.lower().endswith(exts) and fp not in self._files:
                self._files.append(fp); self._file_lb.insert("end",fn)
        self.file_count_lbl.config(text=f"{len(self._files)} files")

    def _clear_files(self):
        self._files.clear(); self._file_lb.delete(0,"end")
        self.file_count_lbl.config(text="0 files")

    def _browse_out(self):
        d=filedialog.askdirectory()
        if d: self.out_dir_var.set(d)

    def _cancel_proc(self):
        self._cancel=True

    def _process(self):
        if not self._files:
            self.status_lbl.config(text="No files added",fg=T.YELLOW); return
        _ensure_pydub()
        if not HAS_PYDUB:
            self.status_lbl.config(text="pydub required (pip install pydub)",fg=T.RED); return
        out_dir=self.out_dir_var.get(); os.makedirs(out_dir,exist_ok=True)
        self._cancel=False
        total=len(self._files)
        def _do():
            from pydub import AudioSegment
            from pydub.silence import detect_leading_silence
            done=0; errors=0
            for i,fp in enumerate(self._files):
                if self._cancel:
                    self.after(0,lambda:(self.status_lbl.config(text="Cancelled",fg=T.YELLOW),self.prog.configure(value=0)))
                    return
                self.after(0,lambda ii=i,_fp=fp:(self.status_lbl.config(text=f"Processing {ii+1}/{total}: {os.path.basename(_fp)}",fg=T.YELLOW),
                    self.prog.configure(value=int(ii/total*100))))
                try:
                    seg=AudioSegment.from_file(fp)
                    # Normalize
                    if self._op_normalize.get() and HAS_FFMPEG:
                        target=self.target_lufs.get()
                        # Simple loudness normalization via pydub dBFS
                        change=target-seg.dBFS
                        seg=seg.apply_gain(change)
                    # Trim silence
                    if self._op_trim_silence.get():
                        start_trim=detect_leading_silence(seg,silence_threshold=-50)
                        end_trim=detect_leading_silence(seg.reverse(),silence_threshold=-50)
                        seg=seg[start_trim:len(seg)-end_trim]
                    # Fades
                    if self._op_fade_in.get(): seg=seg.fade_in(min(self.fade_in_ms.get(),len(seg)))
                    if self._op_fade_out.get(): seg=seg.fade_out(min(self.fade_out_ms.get(),len(seg)))
                    # Output
                    fmt=self.out_fmt.get() if self._op_convert.get() else os.path.splitext(fp)[1].lstrip(".") or "wav"
                    base=os.path.splitext(os.path.basename(fp))[0]
                    out_path=os.path.join(out_dir,f"{base}.{fmt}")
                    tags=None if not self._op_strip_meta.get() else {}
                    seg.export(out_path,format=fmt,tags=tags)
                    done+=1
                except Exception as e:
                    errors+=1
            self.after(0,lambda:(self.status_lbl.config(text=f"Done! {done} processed, {errors} errors",fg=T.LIME_DK),
                self.prog.configure(value=100),
                self.app.toast(f"Batch: {done}/{total} files processed")))
        threading.Thread(target=_do,daemon=True).start()
