"""PlaylistPage -- Fetch and selectively download tracks from online playlists."""

import os, threading
import tkinter as tk
from tkinter import filedialog

import yt_dlp

from limewire.core.theme import T
from limewire.core.constants import AUDIO_FMTS, YDL_BASE, ydl_opts
from limewire.ui.scroll_frame import ScrollFrame
from limewire.ui.widgets import (
    ClassicBtn, LimeBtn, OrangeBtn, GroupBox,
    ClassicEntry, ClassicCombo, ClassicProgress,
)
from limewire.utils.helpers import fmt_duration


class PlaylistPage(ScrollFrame):
    """Fetch and selectively download tracks from online playlists."""

    def __init__(self, parent, app):
        super().__init__(parent)
        self.app = app
        self._tracks = []
        self._cvars = []
        self._build(self.inner)

    def _build(self, p):
        g = GroupBox(p, "Playlist URL")
        g.pack(fill="x", padx=10, pady=(10, 6))
        r = tk.Frame(g, bg=T.BG)
        r.pack(fill="x")
        self.pl_var = tk.StringVar()
        ClassicEntry(r, self.pl_var, width=50).pack(side="left", fill="x", expand=True, ipady=2, padx=(0, 8))
        LimeBtn(r, "Fetch", self._fetch).pack(side="left")
        self.pl_st = tk.Label(g, text="", font=T.F_SMALL, bg=T.BG, fg=T.TEXT_DIM)
        self.pl_st.pack(anchor="w", pady=(4, 0))
        tg = GroupBox(p, "Tracks")
        tg.pack(fill="both", padx=10, pady=(0, 6), expand=True)
        cr = tk.Frame(tg, bg=T.BG)
        cr.pack(fill="x", pady=(0, 4))
        ClassicBtn(cr, "All", self._sel_all).pack(side="left", padx=(0, 4))
        ClassicBtn(cr, "None", self._desel).pack(side="left")
        self.sel_cnt = tk.Label(cr, text="", font=T.F_BODY, bg=T.BG, fg=T.TEXT_DIM)
        self.sel_cnt.pack(side="right")
        self.tf = tk.Frame(tg, bg=T.INPUT_BG, relief="flat", bd=0,
                            highlightthickness=1, highlightbackground=T.CARD_BORDER)
        self.tf.pack(fill="both", expand=True)
        self.ti = tk.Frame(self.tf, bg=T.INPUT_BG)
        self.ti.pack(fill="both", expand=True, padx=4, pady=4)
        sg = GroupBox(p, "Settings")
        sg.pack(fill="x", padx=10, pady=(0, 6))
        sr = tk.Frame(sg, bg=T.BG)
        sr.pack(fill="x")
        for lbl, attr, vals, dflt, w in [("Mode:", "pl_mode", ["audio", "video"], "audio", 8),
                                           ("Fmt:", "pl_fmt", AUDIO_FMTS, "mp3", 8)]:
            c = tk.Frame(sr, bg=T.BG)
            c.pack(side="left", padx=(0, 16))
            tk.Label(c, text=lbl, font=T.F_BOLD, bg=T.BG, fg=T.TEXT).pack(anchor="w")
            var = tk.StringVar(value=dflt)
            setattr(self, attr, var)
            ClassicCombo(c, var, vals, w).pack(anchor="w")
        fc = tk.Frame(sr, bg=T.BG)
        fc.pack(side="left", fill="x", expand=True)
        tk.Label(fc, text="Save To:", font=T.F_BOLD, bg=T.BG, fg=T.TEXT).pack(anchor="w")
        self.pl_folder = tk.StringVar(value=self.app.output_dir)
        ClassicEntry(fc, self.pl_folder, width=30).pack(side="left", fill="x", expand=True, ipady=2)
        bf = tk.Frame(p, bg=T.BG)
        bf.pack(fill="x", padx=10, pady=6)
        LimeBtn(bf, "Download Selected", self._dl_sel, width=20).pack(side="left", padx=(0, 6))
        OrangeBtn(bf, "Retry Failed", self._retry_failed, width=14).pack(side="left")
        pg = GroupBox(p, "Progress")
        pg.pack(fill="x", padx=10, pady=(0, 10))
        self.pl_prog = ClassicProgress(pg)
        self.pl_prog.pack(fill="x", pady=(0, 2))
        self.pl_lbl = tk.Label(pg, text="--", font=T.F_SMALL, bg=T.BG, fg=T.TEXT_DIM)
        self.pl_lbl.pack(anchor="w")
        self._failed_urls = []

    def refresh(self):
        pass

    def _fetch(self):
        url = self.pl_var.get().strip()
        if not url:
            return
        self.pl_st.config(text="Fetching...", fg=T.YELLOW)
        threading.Thread(target=self._do_fetch, args=(url,), daemon=True).start()

    def _do_fetch(self, url):
        try:
            with yt_dlp.YoutubeDL(ydl_opts(quiet=True, no_warnings=True,
                                            extract_flat=True, skip_download=True)) as ydl:
                info = ydl.extract_info(url, download=False)
            entries = info.get("entries", []) or [info]
            self._tracks = []
            for e in entries:
                if not e:
                    continue
                title = e.get("title") or e.get("fulltitle") or e.get("id") or "Untitled"
                entry_url = e.get("url") or e.get("webpage_url") or ""
                dur = e.get("duration") or 0
                self._tracks.append({"title": str(title), "url": entry_url, "dur": dur})
            self.after(0, self._render)
            self.after(0, lambda: self.pl_st.config(text=f"{len(self._tracks)} tracks", fg=T.LIME_DK))
        except Exception as e:
            self.after(0, lambda: self.pl_st.config(text=f"Error: {str(e)[:60]}", fg=T.RED))

    def _render(self):
        for w in self.ti.winfo_children():
            w.destroy()
        self._cvars = []
        for i, tr in enumerate(self._tracks):
            var = tk.BooleanVar(value=True)
            self._cvars.append(var)
            rbg = T.INPUT_BG if i % 2 == 0 else T.CARD_BG
            row = tk.Frame(self.ti, bg=rbg)
            row.pack(fill="x", pady=0)
            tk.Checkbutton(row, variable=var, bg=rbg, selectcolor=T.INPUT_BG, activebackground=rbg,
                            command=self._upd).pack(side="left")
            tk.Label(row, text=f"{i + 1:>3}. {tr['title'][:55]}", font=T.F_BODY, bg=rbg,
                      fg=T.TEXT, anchor="w").pack(side="left", fill="x", expand=True)
            tk.Label(row, text=fmt_duration(tr["dur"]), font=T.F_SMALL, bg=rbg,
                      fg=T.TEXT_DIM, width=8).pack(side="right")
        self._upd()

    def _sel_all(self):
        for v in self._cvars:
            v.set(True)
        self._upd()

    def _desel(self):
        for v in self._cvars:
            v.set(False)
        self._upd()

    def _upd(self):
        self.sel_cnt.config(text=f"{sum(1 for v in self._cvars if v.get())} selected")

    def _dl_sel(self):
        urls = [t["url"] for t, v in zip(self._tracks, self._cvars) if v.get() and t["url"]]
        self._download_urls(urls)

    def _retry_failed(self):
        if self._failed_urls:
            self._download_urls(list(self._failed_urls))

    def _download_urls(self, urls):
        if not urls:
            return
        out = self.pl_folder.get()
        fmt = self.pl_fmt.get()
        mode = self.pl_mode.get()
        total = len(urls)
        self.pl_prog["value"] = 0
        self._failed_urls = []
        extra = self.app.get_ydl_extra()

        def run():
            ok = 0
            fail = 0
            for i, url in enumerate(urls, 1):
                opts = {"quiet": True, "no_warnings": True,
                        "outtmpl": os.path.join(out, "%(title)s.%(ext)s"), **extra}
                if mode == "audio":
                    opts.update({"format": "bestaudio/best",
                                  "postprocessors": [{"key": "FFmpegExtractAudio", "preferredcodec": fmt}]})
                else:
                    opts.update({"format": "bestvideo+bestaudio/best", "merge_output_format": fmt})
                try:
                    os.makedirs(out, exist_ok=True)
                    with yt_dlp.YoutubeDL({**YDL_BASE, **opts}) as ydl:
                        ydl.download([url])
                    ok += 1
                except Exception:
                    fail += 1
                    self._failed_urls.append(url)
                self.after(0, lambda p=int((i / total) * 100), d=i: (
                    self.pl_prog.configure(value=p),
                    self.pl_lbl.config(text=f"{d}/{total}")))
            msg = f"Done - {ok} OK" + (f", {fail} failed (click Retry)" if fail else "")
            col = T.LIME_DK if fail == 0 else T.YELLOW
            self.after(0, lambda: self.pl_lbl.config(text=msg, fg=col))

        threading.Thread(target=run, daemon=True).start()
