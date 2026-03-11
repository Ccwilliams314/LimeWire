"""StemsPage -- AI stem separation using Demucs with FL Studio integration."""

import os, threading
import tkinter as tk
from tkinter import filedialog, messagebox

from limewire.core.theme import T
from limewire.core.deps import HAS_PYFLP
from limewire.ui.scroll_frame import ScrollFrame
from limewire.ui.widgets import (
    ClassicBtn, LimeBtn, OrangeBtn, GroupBox,
    ClassicEntry, ClassicCombo, ClassicProgress,
)
from limewire.ui.toast import show_toast
from limewire.utils.helpers import open_folder
from limewire.services.audio_processing import run_demucs
from limewire.services.dj_integrations import (
    export_stems_for_fl, create_fl_project, open_in_fl_studio,
)


class StemsPage(ScrollFrame):
    """AI stem separation using Demucs with FL Studio integration."""

    def __init__(self, parent, app):
        super().__init__(parent)
        self.app = app
        self._running = False
        self._build(self.inner)

    def _build(self, p):
        fg = GroupBox(p, "Source Audio File")
        fg.pack(fill="x", padx=10, pady=(10, 6))
        fr = tk.Frame(fg, bg=T.BG)
        fr.pack(fill="x")
        self.file_var = tk.StringVar()
        ClassicEntry(fr, self.file_var, width=55).pack(side="left", fill="x", expand=True, ipady=2, padx=(0, 8))
        ClassicBtn(fr, "Browse...", self._browse).pack(side="left")

        sg = GroupBox(p, "Separation Settings")
        sg.pack(fill="x", padx=10, pady=(0, 6))
        sr = tk.Frame(sg, bg=T.BG)
        sr.pack(fill="x")
        mc = tk.Frame(sr, bg=T.BG)
        mc.pack(side="left", padx=(0, 20))
        tk.Label(mc, text="Model:", font=T.F_BOLD, bg=T.BG, fg=T.TEXT).pack(anchor="w")
        self.model_var = tk.StringVar(value="htdemucs")
        ClassicCombo(mc, self.model_var,
                      ["htdemucs", "htdemucs_ft", "htdemucs_6s", "mdx_extra_q"], width=14).pack(anchor="w")

        ts = tk.Frame(sr, bg=T.BG)
        ts.pack(side="left", padx=(0, 20))
        tk.Label(ts, text="Separation Mode:", font=T.F_BOLD, bg=T.BG, fg=T.TEXT).pack(anchor="w")
        self.stems_mode = tk.StringVar(value="all")
        tk.Radiobutton(ts, text="All stems (vocals/drums/bass/other)", variable=self.stems_mode,
                        value="all", font=T.F_BODY, bg=T.BG, fg=T.TEXT, selectcolor=T.INPUT_BG,
                        activebackground=T.BG, activeforeground=T.TEXT).pack(anchor="w")
        tk.Radiobutton(ts, text="Vocals only (karaoke mode)", variable=self.stems_mode,
                        value="vocals", font=T.F_BODY, bg=T.BG, fg=T.TEXT, selectcolor=T.INPUT_BG,
                        activebackground=T.BG, activeforeground=T.TEXT).pack(anchor="w")
        tk.Radiobutton(ts, text="Drums only", variable=self.stems_mode,
                        value="drums", font=T.F_BODY, bg=T.BG, fg=T.TEXT, selectcolor=T.INPUT_BG,
                        activebackground=T.BG, activeforeground=T.TEXT).pack(anchor="w")
        tk.Radiobutton(ts, text="Bass only", variable=self.stems_mode,
                        value="bass", font=T.F_BODY, bg=T.BG, fg=T.TEXT, selectcolor=T.INPUT_BG,
                        activebackground=T.BG, activeforeground=T.TEXT).pack(anchor="w")

        og = GroupBox(p, "Output Folder")
        og.pack(fill="x", padx=10, pady=(0, 6))
        ofr = tk.Frame(og, bg=T.BG)
        ofr.pack(fill="x")
        self.out_var = tk.StringVar(value=os.path.join(self.app.output_dir, "Stems"))
        ClassicEntry(ofr, self.out_var, width=55).pack(side="left", fill="x", expand=True, ipady=2, padx=(0, 8))
        ClassicBtn(ofr, "Browse...",
                    lambda: (d := filedialog.askdirectory(initialdir=self.out_var.get())) and self.out_var.set(d)).pack(
            side="left")

        bf = tk.Frame(p, bg=T.BG)
        bf.pack(fill="x", padx=10, pady=8)
        LimeBtn(bf, "Split Stems", self._run, width=18).pack(side="left", padx=(0, 8))
        OrangeBtn(bf, "Batch Split", self._batch_run, width=14).pack(side="left", padx=(0, 8))
        ClassicBtn(bf, "Open Output Folder", self._open_out).pack(side="left")

        pg = GroupBox(p, "Status")
        pg.pack(fill="x", padx=10, pady=(0, 6))
        self.stem_prog = ClassicProgress(pg)
        self.stem_prog.pack(fill="x", pady=(0, 4))
        self.stem_status = tk.Label(pg, text="Select a file and click Split Stems. Uses Demucs AI model.",
                                     font=T.F_BODY, bg=T.BG, fg=T.TEXT_DIM, anchor="w",
                                     wraplength=700, justify="left")
        self.stem_status.pack(fill="x")

        # FL Studio Integration
        fl_g = GroupBox(p, "FL Studio Integration")
        fl_g.pack(fill="x", padx=10, pady=(0, 6))
        fl_r = tk.Frame(fl_g, bg=T.BG)
        fl_r.pack(fill="x")
        LimeBtn(fl_r, "Export for FL Studio", self._export_for_fl).pack(side="left", padx=(0, 6))
        OrangeBtn(fl_r, "Create FL Project (.flp)" + (" \u2713" if HAS_PYFLP else " \u2717"),
                   self._create_fl_project).pack(side="left", padx=(0, 6))
        ClassicBtn(fl_r, "Open in FL Studio", self._open_fl_in_studio).pack(side="left")
        self.fl_status = tk.Label(fl_g,
                                   text="Split stems first, then export for FL Studio or create .flp project",
                                   font=T.F_SMALL, bg=T.BG, fg=T.TEXT_DIM, anchor="w")
        self.fl_status.pack(fill="x", pady=(4, 0))

        # Info about models
        info_g = GroupBox(p, "Model Info")
        info_g.pack(fill="x", padx=10, pady=(0, 10))
        tk.Label(info_g,
                  text="htdemucs \u2014 Default Hybrid Transformer model. Good balance of speed and quality.\n"
                       "htdemucs_ft \u2014 Fine-tuned version. 4x slower but best quality.\n"
                       "htdemucs_6s \u2014 6 stems: adds piano and guitar separation.\n"
                       "mdx_extra_q \u2014 Quantized MDX model. Smaller, faster, slightly less accurate.",
                  font=T.F_SMALL, bg=T.BG, fg=T.TEXT_DIM, justify="left", anchor="w").pack(fill="x")

    def _browse(self):
        f = filedialog.askopenfilename(
            filetypes=[("Audio", "*.mp3 *.wav *.flac *.ogg *.m4a"), ("All", "*.*")])
        if f:
            self.file_var.set(f)

    def _run(self):
        path = self.file_var.get()
        if not path or not os.path.exists(path):
            messagebox.showwarning("LimeWire", "Select a valid audio file.")
            return
        if self._running:
            return
        self._running = True
        model = self.model_var.get()
        mode = self.stems_mode.get()
        two_stems = None if mode == "all" else mode
        out = self.out_var.get()
        self.stem_status.config(text=f"Running Demucs ({model})... This may take several minutes.", fg=T.YELLOW)
        self.stem_prog.config(mode="indeterminate")
        self.stem_prog.start(20)
        self.app.set_status(f"Splitting stems with {model}...")
        threading.Thread(target=self._do_split, args=(path, out, model, two_stems), daemon=True).start()

    def _do_split(self, path, out, model, two_stems):
        try:
            result = run_demucs(path, out, model, two_stems)
            self.after(0, lambda: self.stem_prog.stop())
            self.after(0, lambda: self.stem_prog.config(mode="determinate"))
            if result is True:
                track_name = os.path.splitext(os.path.basename(path))[0]
                stem_dir = os.path.join(out, model, track_name)
                stems_found = []
                if os.path.exists(stem_dir):
                    stems_found = [f for f in os.listdir(stem_dir) if f.endswith(".wav")]
                self.after(0, lambda: (
                    self.stem_prog.configure(value=100),
                    self.stem_status.config(
                        text=f"Done! {len(stems_found)} stems saved to: {stem_dir}\n"
                             f"Files: {', '.join(stems_found)}",
                        fg=T.LIME_DK),
                    self.app.set_status("Stem separation complete")))
            else:
                self.after(0, lambda: (
                    self.stem_status.config(text=f"Error: {result}", fg=T.RED),
                    self.app.set_status("Stem separation failed")))
        finally:
            self._running = False

    def _batch_run(self):
        """Queue multiple files for stem separation."""
        files = filedialog.askopenfilenames(
            filetypes=[("Audio", "*.mp3 *.wav *.flac *.ogg *.m4a"), ("All", "*.*")])
        if not files:
            return
        if self._running:
            show_toast(self.app, "Separation already running", "warning")
            return
        self._running = True
        model = self.model_var.get()
        mode = self.stems_mode.get()
        two_stems = None if mode == "all" else mode
        out = self.out_var.get()
        total = len(files)
        self.stem_status.config(text=f"Batch: 0/{total} files processed...", fg=T.YELLOW)
        self.stem_prog.configure(value=0)

        def _do_batch():
            ok = 0
            fail = 0
            for i, path in enumerate(files):
                name = os.path.basename(path)
                self.after(0, lambda i=i, n=name: self.stem_status.config(
                    text=f"Batch [{i + 1}/{total}]: {n}...", fg=T.YELLOW))
                try:
                    result = run_demucs(path, out, model, two_stems)
                    if result is True:
                        ok += 1
                    else:
                        fail += 1
                except Exception:
                    fail += 1
                self.after(0, lambda p=int(((i + 1) / total) * 100): self.stem_prog.configure(value=p))
            msg = f"Batch done \u2014 {ok} succeeded" + (f", {fail} failed" if fail else "")
            self.after(0, lambda: (
                self.stem_status.config(text=msg, fg=T.LIME_DK if fail == 0 else T.YELLOW),
                self.app.set_status(msg)))
            self._running = False

        threading.Thread(target=_do_batch, daemon=True).start()

    def _open_out(self):
        open_folder(self.out_var.get())

    def _get_stem_dir(self):
        path = self.file_var.get()
        if not path:
            return None
        track_name = os.path.splitext(os.path.basename(path))[0]
        model = self.model_var.get()
        stem_dir = os.path.join(self.out_var.get(), model, track_name)
        return stem_dir if os.path.exists(stem_dir) else None

    def _export_for_fl(self):
        stem_dir = self._get_stem_dir()
        if not stem_dir:
            messagebox.showinfo("LimeWire", "Split stems first.")
            return
        track_name = os.path.splitext(os.path.basename(self.file_var.get()))[0]
        bpm = None
        key = None
        ap = self.app.pages.get("analyze")
        if ap:
            try:
                bpm = float(ap._res["BPM"].cget("text"))
            except Exception:
                pass
            k = ap._res["Key"].cget("text")
            key = k if k and k != "--" else None
        out_dir, copied = export_stems_for_fl(stem_dir, track_name, bpm, key)
        self.fl_status.config(text=f"Exported {len(copied)} stems to: {out_dir}", fg=T.LIME_DK)
        self.app.toast(f"FL Export: {len(copied)} stems")

    def _create_fl_project(self):
        stem_dir = self._get_stem_dir()
        if not stem_dir:
            messagebox.showinfo("LimeWire", "Split stems first.")
            return
        if not HAS_PYFLP:
            messagebox.showinfo("LimeWire", "pyflp not installed. Run: pip install pyflp")
            return
        track_name = os.path.splitext(os.path.basename(self.file_var.get()))[0]
        bpm = None
        ap = self.app.pages.get("analyze")
        if ap:
            try:
                bpm = float(ap._res["BPM"].cget("text"))
            except Exception:
                pass
        self.fl_status.config(text="Generating FL Studio project...", fg=T.YELLOW)
        threading.Thread(target=self._do_create_fl, args=(stem_dir, track_name, bpm), daemon=True).start()

    def _do_create_fl(self, stem_dir, track_name, bpm):
        flp_path, err = create_fl_project(stem_dir, track_name, bpm)
        if flp_path:
            self.after(0, lambda: (
                self.fl_status.config(text=f"FL project: {os.path.basename(flp_path)}", fg=T.LIME_DK),
                self.app.toast(f"Created {os.path.basename(flp_path)}")))
        else:
            self.after(0, lambda: self.fl_status.config(text=f"FLP error: {err}", fg=T.RED))

    def _open_fl_in_studio(self):
        stem_dir = self._get_stem_dir()
        flp_path = None
        if stem_dir:
            track_name = os.path.splitext(os.path.basename(self.file_var.get()))[0]
            candidate = os.path.join(os.path.dirname(stem_dir), f"{track_name}_stems.flp")
            if os.path.exists(candidate):
                flp_path = candidate
        fl_path = self.app.settings.get("fl_studio_path", "")
        ok, err = open_in_fl_studio(flp_path, fl_path or None)
        if not ok:
            messagebox.showinfo("LimeWire", f"FL Studio: {err}")
