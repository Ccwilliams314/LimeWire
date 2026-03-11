"""DownloadPage -- Batch download multiple URLs with concurrent workers."""

import os, threading, datetime
import tkinter as tk
from tkinter import filedialog
from tkinter import scrolledtext as st
from concurrent.futures import ThreadPoolExecutor, as_completed

import yt_dlp

from limewire.core.theme import T
from limewire.core.constants import AUDIO_FMTS, VIDEO_FMTS, QUALITIES, YDL_BASE
from limewire.core.config import load_json, save_json, QUEUE_FILE
from limewire.ui.scroll_frame import ScrollFrame
from limewire.ui.widgets import (
    ClassicBtn, LimeBtn, GroupBox,
    ClassicEntry, ClassicCombo, ClassicCheck, ClassicListbox, ClassicProgress,
)


class DownloadPage(ScrollFrame):
    """Batch download multiple URLs with concurrent workers."""

    def __init__(self, parent, app):
        super().__init__(parent)
        self.app = app
        self._build(self.inner)
        # Restore persisted queue
        saved = load_json(QUEUE_FILE, [])
        for url in saved:
            self.ul.insert("end", url)
        self.cnt.config(text=f"{self.ul.size()} items")

    def _build(self, p):
        qg = GroupBox(p, "Download Queue")
        qg.pack(fill="x", padx=10, pady=(10, 6))
        qr = tk.Frame(qg, bg=T.BG)
        qr.pack(fill="x", pady=(0, 6))
        tk.Label(qr, text="URL:", font=T.F_BOLD, bg=T.BG, fg=T.TEXT).pack(side="left", padx=(0, 6))
        self.url_var = tk.StringVar()
        self.url_e = ClassicEntry(qr, self.url_var, width=45)
        self.url_e.pack(side="left", fill="x", expand=True, ipady=2, padx=(0, 6))
        self.url_e.bind("<Return>", lambda e: self._add())
        LimeBtn(qr, "+ Add", self._add).pack(side="left")
        self.uf, self.ul = ClassicListbox(qg, height=4)
        self.uf.pack(fill="x", pady=(0, 4))
        ar = tk.Frame(qg, bg=T.BG)
        ar.pack(fill="x")
        ClassicBtn(ar, "Remove", self._remove).pack(side="left", padx=(0, 4))
        ClassicBtn(ar, "Clear", self._clear).pack(side="left")
        self.cnt = tk.Label(ar, text="0 items", font=T.F_BODY, bg=T.BG, fg=T.TEXT_DIM)
        self.cnt.pack(side="right")
        sg = GroupBox(p, "Settings")
        sg.pack(fill="x", padx=10, pady=(0, 6))
        sr = tk.Frame(sg, bg=T.BG)
        sr.pack(fill="x")
        mc = tk.Frame(sr, bg=T.BG)
        mc.pack(side="left", padx=(0, 16))
        tk.Label(mc, text="Type:", font=T.F_BOLD, bg=T.BG, fg=T.TEXT).pack(anchor="w")
        self.mode = tk.StringVar(value="audio")
        tk.Radiobutton(mc, text="Audio", variable=self.mode, value="audio", font=T.F_BODY,
                        bg=T.BG, fg=T.TEXT, selectcolor=T.INPUT_BG).pack(anchor="w")
        tk.Radiobutton(mc, text="Video", variable=self.mode, value="video", font=T.F_BODY,
                        bg=T.BG, fg=T.TEXT, selectcolor=T.INPUT_BG).pack(anchor="w")
        fc = tk.Frame(sr, bg=T.BG)
        fc.pack(side="left", padx=(0, 16))
        tk.Label(fc, text="Format:", font=T.F_BOLD, bg=T.BG, fg=T.TEXT).pack(anchor="w")
        self.afmt = tk.StringVar(value="mp3")
        ClassicCombo(fc, self.afmt, AUDIO_FMTS, 10).pack(anchor="w")
        qc = tk.Frame(sr, bg=T.BG)
        qc.pack(side="left", padx=(0, 16))
        tk.Label(qc, text="Quality:", font=T.F_BOLD, bg=T.BG, fg=T.TEXT).pack(anchor="w")
        self.vqual = tk.StringVar(value="1080p")
        ClassicCombo(qc, self.vqual, QUALITIES, 10).pack(anchor="w")
        wc = tk.Frame(sr, bg=T.BG)
        wc.pack(side="left")
        tk.Label(wc, text="Threads:", font=T.F_BOLD, bg=T.BG, fg=T.TEXT).pack(anchor="w")
        self.workers = tk.IntVar(value=2)
        tk.Spinbox(wc, from_=1, to=5, textvariable=self.workers, width=4, font=T.F_BODY,
                    bg=T.INPUT_BG, fg=T.TEXT, relief="flat", bd=0,
                    highlightthickness=1, highlightbackground=T.INPUT_BORDER,
                    buttonbackground=T.BG).pack(anchor="w")
        self.skip = tk.BooleanVar(value=True)
        ClassicCheck(sg, "Skip already downloaded", self.skip).pack(anchor="w")
        fg_ = GroupBox(p, "Save To")
        fg_.pack(fill="x", padx=10, pady=(0, 6))
        fr = tk.Frame(fg_, bg=T.BG)
        fr.pack(fill="x")
        self.folder = tk.StringVar(value=self.app.output_dir)
        ClassicEntry(fr, self.folder, width=55).pack(side="left", fill="x", expand=True, ipady=2, padx=(0, 8))
        ClassicBtn(fr, "Browse...",
                    lambda: (d := filedialog.askdirectory(initialdir=self.folder.get())) and self.folder.set(d)).pack(
            side="left")
        bf = tk.Frame(p, bg=T.BG)
        bf.pack(fill="x", padx=10, pady=6)
        LimeBtn(bf, "Download All", self._start, width=18).pack(side="left")
        self.dl_st = tk.Label(bf, text="", font=T.F_BODY, bg=T.BG, fg=T.TEXT_DIM)
        self.dl_st.pack(side="left", padx=(12, 0))
        pg = GroupBox(p, "Progress")
        pg.pack(fill="x", padx=10, pady=(0, 6))
        o = tk.Frame(pg, bg=T.BG)
        o.pack(fill="x", pady=(0, 4))
        tk.Label(o, text="Overall:", font=T.F_BOLD, bg=T.BG, fg=T.TEXT).pack(side="left", padx=(0, 6))
        self.ov_bar = ClassicProgress(o)
        self.ov_bar.pack(side="left", fill="x", expand=True)
        self.ov_lbl = tk.Label(o, text="0/0", font=T.F_BODY, bg=T.BG, fg=T.TEXT, width=6)
        self.ov_lbl.pack(side="left")
        t_ = tk.Frame(pg, bg=T.BG)
        t_.pack(fill="x")
        tk.Label(t_, text="Current:", font=T.F_BOLD, bg=T.BG, fg=T.TEXT).pack(side="left", padx=(0, 6))
        self.tr_bar = ClassicProgress(t_)
        self.tr_bar.pack(side="left", fill="x", expand=True)
        self.tr_name = tk.Label(pg, text="--", font=T.F_SMALL, bg=T.BG, fg=T.TEXT_DIM, anchor="w")
        self.tr_name.pack(fill="x", pady=(2, 0))

        log_g = GroupBox(p, "Log")
        log_g.pack(fill="both", padx=10, pady=(0, 10), expand=True)
        self.log = st.ScrolledText(log_g, font=T.F_MONO, bg=T.INPUT_BG, fg=T.TEXT, relief="flat",
                                    bd=0, height=5, state="disabled", padx=6, pady=4,
                                    highlightthickness=1, highlightbackground=T.INPUT_BORDER)
        self.log.pack(fill="both", expand=True)
        self.log.tag_config("ok", foreground=T.LIME_DK)
        self.log.tag_config("warn", foreground=T.YELLOW)
        self.log.tag_config("error", foreground=T.RED)
        self.log.tag_config("dim", foreground=T.TEXT_DIM)

    def _persist_queue(self):
        save_json(QUEUE_FILE, list(self.ul.get(0, "end")))

    def _add(self):
        url = self.url_var.get().strip()
        if url and "http" in url:
            self.ul.insert("end", url)
            self.url_var.set("")
            self.cnt.config(text=f"{self.ul.size()} items")
            self._persist_queue()

    def _remove(self):
        for i in reversed(self.ul.curselection()):
            self.ul.delete(i)
        self.cnt.config(text=f"{self.ul.size()} items")
        self._persist_queue()

    def _clear(self):
        self.ul.delete(0, "end")
        self.cnt.config(text="0 items")
        self._persist_queue()

    def _lm(self, msg, tag="ok"):
        def d():
            self.log.configure(state="normal")
            self.log.insert("end", msg + "\n", tag)
            self.log.see("end")
            self.log.configure(state="disabled")
        self.after(0, d)

    def _start(self):
        urls = list(self.ul.get(0, "end"))
        if not urls:
            self._lm("Add URLs first", "warn")
            return
        self.app._total = len(urls)
        self.app._completed = 0
        self.ov_bar["value"] = 0
        self.ov_lbl.config(text=f"0/{len(urls)}")
        self.dl_st.config(text="Downloading...", fg=T.LIME_DK)
        threading.Thread(target=self._pool, args=(urls,), daemon=True).start()

    def _pool(self, urls):
        with ThreadPoolExecutor(max_workers=self.workers.get()) as pool:
            for f in as_completed({pool.submit(self._dl, i + 1, u): u for i, u in enumerate(urls)}):
                pass
        self._lm(f"\nDone - {self.app._completed}/{self.app._total}", "ok")
        all_ok = self.app._completed == self.app._total
        self.after(0, lambda: (
            self.dl_st.config(text=f"Complete: {self.app._completed}/{self.app._total}"),
            self._clear() if all_ok else None,
            self.app.toast(
                f"Batch: {self.app._completed}/{self.app._total}" + (" - some failed" if not all_ok else ""),
                "info" if all_ok else "warn")))

    def _dl(self, idx, url):
        out = self.folder.get()
        th = [None]
        os.makedirs(out, exist_ok=True)
        mode = self.mode.get()
        page = self

        class L:
            def debug(s, m):
                pass

            def warning(s, m):
                pass

            def error(s, m):
                page._lm(f"ERR: {m.strip()[:60]}", "error")

        def hook(d):
            t = th[0] or f"track {idx}"
            if d["status"] == "downloading":
                try:
                    pct = float(d.get("_percent_str", "0%").strip().replace("%", ""))
                except Exception:
                    pct = 0
                self.after(0, lambda: (
                    self.tr_bar.__setitem__("value", pct),
                    self.tr_name.config(text=t[:50])))

        base = {"outtmpl": os.path.join(out, "%(title)s.%(ext)s"), "logger": L(),
                "progress_hooks": [hook], "quiet": True,
                **({"download_archive": os.path.join(out, ".archive.txt")} if self.skip.get() else {})}
        if mode == "audio":
            base.update({"format": "bestaudio/best",
                          "postprocessors": [{"key": "FFmpegExtractAudio", "preferredcodec": self.afmt.get()}]})
        else:
            q = self.vqual.get()
            vf = ("bestvideo+bestaudio/best" if q == "best"
                  else f"bestvideo[height<={q[:-1]}]+bestaudio/best[height<={q[:-1]}]")
            base.update({"format": vf, "merge_output_format": "mp4"})
        status = "error"
        title = url
        try:
            with yt_dlp.YoutubeDL({**YDL_BASE, **base}) as ydl:
                info = ydl.extract_info(url, download=False)
                title = info.get("title", url)
                th[0] = title
                self._lm(f"[{idx}] {title}", "ok")
                ydl.download([url])
            self._lm(f"[{idx}] Saved", "dim")
            status = "done"
        except Exception as e:
            self._lm(f"[{idx}] FAILED: {str(e)[:60]}", "error")
        self.after(0, lambda: self.app.add_history({
            "title": title, "url": url, "mode": mode, "format": self.afmt.get(),
            "status": status, "date": datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
            "folder": out}))
        with self.app._lock:
            self.app._completed += 1
        self.after(0, lambda: (
            self.ov_bar.__setitem__("value", int((self.app._completed / max(1, self.app._total)) * 100)),
            self.ov_lbl.config(text=f"{self.app._completed}/{self.app._total}")))
