"""SpectrogramPage — Frequency visualization with multiple colormaps and export."""
import os, threading
import tkinter as tk
from tkinter import filedialog

from limewire.core.theme import T
from limewire.core.constants import SPECTROGRAM_CMAP, SPECTROGRAM_HOP
from limewire.core.deps import (
    _ensure_librosa, HAS_NUMPY, np,
    Image, ImageTk,
)
from limewire.core.audio_backend import _audio
from limewire.ui.scroll_frame import ScrollFrame
from limewire.ui.widgets import (ClassicBtn, LimeBtn, GroupBox,
                                  ClassicEntry, ClassicCombo)
from limewire.services.audio_processing import _get_colormap


class SpectrogramPage(ScrollFrame):
    """Spectrogram visualization with multiple colormaps and export."""
    def __init__(self,parent,app):
        super().__init__(parent); self.app=app
        self._spec_img=None; self._spec_pil=None
        self._build(self.inner)

    def _build(self,p):
        # File
        fg=GroupBox(p,"Audio File"); fg.pack(fill="x",padx=10,pady=(10,6))
        fr=tk.Frame(fg,bg=T.BG); fr.pack(fill="x")
        self.file_var=tk.StringVar()
        ClassicEntry(fr,self.file_var,width=55).pack(side="left",fill="x",expand=True,ipady=2,padx=(0,8))
        ClassicBtn(fr,"Browse...",self._browse).pack(side="left")

        # Settings
        sg=GroupBox(p,"Spectrogram Settings"); sg.pack(fill="x",padx=10,pady=(0,6))
        sr=tk.Frame(sg,bg=T.BG); sr.pack(fill="x")
        tk.Label(sr,text="Type:",font=T.F_BODY,bg=T.BG,fg=T.TEXT).pack(side="left",padx=(0,4))
        self.type_var=tk.StringVar(value="Linear")
        ClassicCombo(sr,self.type_var,["Linear","Mel","CQT"],width=8).pack(side="left",padx=(0,10))
        tk.Label(sr,text="FFT:",font=T.F_BODY,bg=T.BG,fg=T.TEXT).pack(side="left",padx=(0,4))
        self.fft_var=tk.StringVar(value="2048")
        ClassicCombo(sr,self.fft_var,["512","1024","2048","4096"],width=6).pack(side="left",padx=(0,10))
        tk.Label(sr,text="Colormap:",font=T.F_BODY,bg=T.BG,fg=T.TEXT).pack(side="left",padx=(0,4))
        self.cmap_var=tk.StringVar(value=SPECTROGRAM_CMAP)
        ClassicCombo(sr,self.cmap_var,["viridis","magma","plasma","inferno"],width=10).pack(side="left",padx=(0,10))
        LimeBtn(sr,"Generate",self._generate,width=12).pack(side="left")

        # Canvas
        cg=GroupBox(p,"Spectrogram Display"); cg.pack(fill="both",padx=10,pady=(0,6),expand=True)
        self.spec_cv=tk.Canvas(cg,bg=T.CANVAS_BG,height=300,highlightthickness=0)
        self.spec_cv.pack(fill="both",expand=True,padx=4,pady=4)
        self.spec_cv.bind("<Motion>",self._on_hover)
        self.hover_lbl=tk.Label(cg,text="",font=T.F_SMALL,bg=T.BG,fg=T.TEXT_DIM,anchor="w")
        self.hover_lbl.pack(fill="x")

        # Actions
        ag=GroupBox(p,"Actions"); ag.pack(fill="x",padx=10,pady=(0,10))
        ar=tk.Frame(ag,bg=T.BG); ar.pack(fill="x")
        LimeBtn(ar,"Save Image",self._save_image,width=12).pack(side="left",padx=(0,6))
        ClassicBtn(ar,"Play Audio",self._play_audio).pack(side="left")
        self.status_lbl=tk.Label(ag,text="Load a file and click Generate",font=T.F_SMALL,bg=T.BG,fg=T.TEXT_DIM,anchor="w")
        self.status_lbl.pack(fill="x",pady=(4,0))

    def _browse(self):
        f=filedialog.askopenfilename(filetypes=[("Audio","*.mp3 *.wav *.flac *.ogg *.m4a"),("All","*.*")])
        if f: self.file_var.set(f)

    def _generate(self):
        path=self.file_var.get().strip()
        if not path or not os.path.isfile(path):
            self.status_lbl.config(text="Select a valid audio file",fg=T.YELLOW); return
        fft=int(self.fft_var.get()); cmap=self.cmap_var.get()
        spec_type=self.type_var.get()
        self.status_lbl.config(text="Generating spectrogram...",fg=T.YELLOW)
        def _do():
            try:
                if not _ensure_librosa():
                    self.after(0,lambda:self.status_lbl.config(text="librosa not installed",fg=T.RED)); return
                if not HAS_NUMPY:
                    self.after(0,lambda:self.status_lbl.config(text="numpy required",fg=T.RED)); return
                import limewire.core.deps as _d
                librosa = _d.librosa
                y, sr = librosa.load(path, sr=22050, mono=True)
                # Choose spectrogram type
                if spec_type=="Mel":
                    S=librosa.amplitude_to_db(librosa.feature.melspectrogram(y=y,sr=sr,n_fft=fft,hop_length=SPECTROGRAM_HOP),ref=np.max)
                elif spec_type=="CQT":
                    S=librosa.amplitude_to_db(np.abs(librosa.cqt(y,sr=sr,hop_length=SPECTROGRAM_HOP)),ref=np.max)
                else:
                    S=librosa.amplitude_to_db(np.abs(librosa.stft(y,n_fft=fft,hop_length=SPECTROGRAM_HOP)),ref=np.max)
                S_norm=np.clip((S+80)/80*255,0,255).astype(np.uint8)
                lut=_get_colormap(cmap)
                rgb=lut[S_norm]
                img=Image.fromarray(rgb[::-1].astype(np.uint8))
                self._spec_pil=img
                self._dur=len(y)/sr
                self._freq_max=sr//2
                # Resize to canvas
                self.after(0,self._render_spectrogram)
                self.after(0,lambda:self.status_lbl.config(
                    text=f"{spec_type} spectrogram | FFT={fft} | {len(y)/sr:.1f}s | {cmap}",fg=T.LIME_DK))
            except Exception as e:
                self.after(0,lambda:self.status_lbl.config(text=f"Error: {str(e)[:80]}",fg=T.RED))
        threading.Thread(target=_do,daemon=True).start()

    def _render_spectrogram(self):
        if not self._spec_pil: return
        cv=self.spec_cv; cv.update_idletasks()
        w=cv.winfo_width() or 800; h=cv.winfo_height() or 300
        resized=self._spec_pil.resize((w,h),Image.LANCZOS)
        self._spec_img=ImageTk.PhotoImage(resized)
        cv.delete("all")
        cv.create_image(0,0,anchor="nw",image=self._spec_img)

    def _on_hover(self,e):
        if not self._spec_pil or not hasattr(self,"_dur"): return
        cv=self.spec_cv
        w=cv.winfo_width() or 800; h=cv.winfo_height() or 300
        t=e.x/w*self._dur
        f=self._freq_max*(1-e.y/h)
        self.hover_lbl.config(text=f"Time: {t:.2f}s  |  Freq: {f:.0f} Hz")

    def _save_image(self):
        if not self._spec_pil:
            self.status_lbl.config(text="Generate a spectrogram first",fg=T.YELLOW); return
        path=filedialog.asksaveasfilename(defaultextension=".png",
            filetypes=[("PNG","*.png"),("JPEG","*.jpg"),("All","*.*")],
            initialdir=self.app.output_dir)
        if path:
            self._spec_pil.save(path)
            self.status_lbl.config(text=f"Saved: {os.path.basename(path)}",fg=T.LIME_DK)
            self.app.toast(f"Spectrogram saved: {os.path.basename(path)}")

    def _play_audio(self):
        path=self.file_var.get().strip()
        if path and os.path.isfile(path):
            _audio.load(path); _audio.play()
            self.status_lbl.config(text="Playing...",fg=T.LIME_DK)
