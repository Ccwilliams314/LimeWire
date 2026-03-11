"""ConverterPage — Convert audio/video files between formats with optional loudness normalization."""
import os, subprocess, threading
import tkinter as tk
from tkinter import filedialog, messagebox

from limewire.core.theme import T
from limewire.core.constants import CONV_AUDIO, CONV_VIDEO, FFMPEG_TIMEOUT
from limewire.core.deps import HAS_FFMPEG
from limewire.ui.scroll_frame import ScrollFrame
from limewire.ui.widgets import (ClassicBtn, LimeBtn, GroupBox,
                                  ClassicEntry, ClassicCombo, ClassicListbox,
                                  ClassicProgress)


class ConverterPage(ScrollFrame):
    """Convert audio/video files between formats with optional loudness normalization."""
    def __init__(self, parent, app):
        super().__init__(parent); self.app = app; self._files = []; self._build(self.inner)

    def _build(self, p):
        ig = GroupBox(p, "Input Files"); ig.pack(fill="x", padx=10, pady=(10, 6))
        ir = tk.Frame(ig, bg=T.BG); ir.pack(fill="x", pady=(0, 6))
        LimeBtn(ir, "+ Add Files", self._add).pack(side="left", padx=(0, 4))
        ClassicBtn(ir, "Clear", self._clr).pack(side="left")
        self.fcnt = tk.Label(ir, text="0 files", font=T.F_BODY, bg=T.BG, fg=T.TEXT_DIM)
        self.fcnt.pack(side="right")
        self.ff, self.fl = ClassicListbox(ig, height=5); self.ff.pack(fill="x")

        og = GroupBox(p, "Output"); og.pack(fill="x", padx=10, pady=(0, 6))
        or_ = tk.Frame(og, bg=T.BG); or_.pack(fill="x")
        for lbl, attr, vals, dflt, w in [
            ("Format:", "out_fmt", CONV_AUDIO + CONV_VIDEO, "mp3", 10),
            ("Bitrate:", "bitrate", ["320k", "256k", "192k", "128k"], "320k", 8),
        ]:
            c = tk.Frame(or_, bg=T.BG); c.pack(side="left", padx=(0, 16))
            tk.Label(c, text=lbl, font=T.F_BOLD, bg=T.BG, fg=T.TEXT).pack(anchor="w")
            var = tk.StringVar(value=dflt); setattr(self, attr, var)
            ClassicCombo(c, var, vals, w).pack(anchor="w")

        nc = tk.Frame(or_, bg=T.BG); nc.pack(side="left", padx=(0, 16))
        tk.Label(nc, text="Normalize:", font=T.F_BOLD, bg=T.BG, fg=T.TEXT).pack(anchor="w")
        self.norm_var = tk.StringVar(value="off")
        ClassicCombo(nc, self.norm_var, ["off", "-14 LUFS", "-16 LUFS", "-23 LUFS"],
                     width=10).pack(anchor="w")

        fc = tk.Frame(or_, bg=T.BG); fc.pack(side="left", fill="x", expand=True)
        tk.Label(fc, text="Folder:", font=T.F_BOLD, bg=T.BG, fg=T.TEXT).pack(anchor="w")
        self.out_f = tk.StringVar(value=self.app.output_dir)
        ClassicEntry(fc, self.out_f, width=30).pack(side="left", fill="x", expand=True, ipady=2)

        LimeBtn(p, "Convert All", self._conv, width=16).pack(padx=10, pady=6, anchor="w")
        pg = GroupBox(p, "Progress"); pg.pack(fill="x", padx=10, pady=(0, 10))
        self.cb = ClassicProgress(pg); self.cb.pack(fill="x", pady=(0, 2))
        self.cl = tk.Label(pg, text="--", font=T.F_SMALL, bg=T.BG, fg=T.TEXT_DIM)
        self.cl.pack(anchor="w")

    def _add(self):
        files = filedialog.askopenfilenames(
            filetypes=[("Media", "*.mp3 *.wav *.flac *.ogg *.mp4 *.mkv *.m4a *.aac"),
                       ("All", "*.*")])
        for f in files:
            if f not in self._files:
                self._files.append(f); self.fl.insert("end", os.path.basename(f))
        self.fcnt.config(text=f"{len(self._files)} files")

    def _clr(self):
        self._files = []; self.fl.delete(0, "end"); self.fcnt.config(text="0 files")

    def _conv(self):
        if not self._files:
            return
        if not HAS_FFMPEG:
            messagebox.showerror(
                "LimeWire",
                "FFmpeg not found in PATH.\nInstall: winget install ffmpeg (Windows)\n"
                "         brew install ffmpeg (macOS)")
            return
        out = self.out_f.get(); fmt = self.out_fmt.get()
        br = self.bitrate.get(); total = len(self._files)
        norm = self.norm_var.get()
        os.makedirs(out, exist_ok=True); self.cb["value"] = 0

        def run():
            ok = 0; fail = 0
            for i, src in enumerate(self._files, 1):
                name = os.path.splitext(os.path.basename(src))[0]
                dst = os.path.join(out, f"{name}.{fmt}")
                self.after(0, lambda i=i, n=name: self.cl.config(
                    text=f"[{i}/{total}] {n}..."))
                try:
                    cmd = ["ffmpeg", "-y", "-i", src]
                    if norm != "off":
                        lufs_target = norm.split()[0]
                        cmd += ["-af", f"loudnorm=I={lufs_target}:TP=-1.5:LRA=11"]
                    if fmt in CONV_AUDIO:
                        cmd += ["-ab", br]
                    cmd.append(dst)
                    subprocess.run(cmd, capture_output=True, check=True,
                                   timeout=FFMPEG_TIMEOUT)
                    ok += 1
                except Exception as e:
                    fail += 1
                    self.after(0, lambda n=name, e=e: self.cl.config(
                        text=f"FAILED: {n} - {str(e)[:40]}", fg=T.RED))
                self.after(0, lambda p=int((i / total) * 100):
                           self.cb.configure(value=p))
            msg = f"Done - {ok} converted" + (f", {fail} failed" if fail else "")
            self.after(0, lambda: self.cl.config(
                text=msg, fg=T.LIME_DK if fail == 0 else T.YELLOW))
        threading.Thread(target=run, daemon=True).start()
