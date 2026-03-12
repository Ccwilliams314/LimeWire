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
    PageSettingsPanel, GearButton,
)
from limewire.utils.helpers import fmt_duration
from limewire.services.connectors.utils import CONNECTOR_LABELS, detect_service_from_url


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
        self._settings_panel = PageSettingsPanel(p, "playlist", self.app, [
            ("concurrent_downloads", "Concurrent Downloads", "int", 1, {"min": 1, "max": 4}),
            ("track_numbering", "Track Numbering Prefix", "bool", True, None),
        ])
        self._gear = GearButton(r, self._settings_panel)
        self._gear.pack(side="right")
        self.pl_var = tk.StringVar()
        ClassicEntry(r, self.pl_var, width=50).pack(side="left", fill="x", expand=True, ipady=2, padx=(0, 8))
        LimeBtn(r, "Fetch", self._fetch).pack(side="left", padx=(0, 4))
        OrangeBtn(r, "Transfer...", self._open_transfer).pack(side="left")
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
        pg = GroupBox(p, "Download")
        pg.pack(fill="x", padx=10, pady=(0, 10))
        bf = tk.Frame(pg, bg=T.BG)
        bf.pack(fill="x", pady=(0, 6))
        LimeBtn(bf, "Download Selected", self._dl_sel, width=20).pack(side="left", padx=(0, 6))
        OrangeBtn(bf, "Retry Failed", self._retry_failed, width=14).pack(side="left")
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
        # Route Spotify/TIDAL/Apple Music/SoundCloud URLs to connector import
        service = detect_service_from_url(url)
        if service and service not in ("youtube",):
            self._import_service_playlist(url)
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
        urls = [t.get("_yt_query") or t["url"]
                for t, v in zip(self._tracks, self._cvars) if v.get() and (t["url"] or t.get("_yt_query"))]
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

    # ── Service playlist import ───────────────────────────────────────
    def _import_service_playlist(self, url):
        """Import a playlist from a music service via connectors."""
        service = detect_service_from_url(url)
        if not service:
            self.pl_st.config(text="Could not detect service from URL", fg=T.RED)
            return
        self.pl_st.config(text=f"Importing from {CONNECTOR_LABELS.get(service, service)}...", fg=T.YELLOW)

        def run():
            try:
                from limewire.services.metadata import connector_import_playlist
                result = connector_import_playlist(service, url, self.app.settings)
                if not result or "error" in result:
                    err = result.get("error", "Import failed") if result else "Import failed"
                    self.after(0, lambda: self.pl_st.config(text=str(err)[:60], fg=T.RED))
                    return
                tracks = result.get("tracks", [])
                self._tracks = []
                for t in tracks:
                    self._tracks.append({
                        "title": f"{t.get('artist', '')} - {t.get('title', '')}" if t.get("artist") else t.get("title", ""),
                        "url": "",  # will search YouTube on download
                        "dur": (t.get("duration_ms", 0) or 0) // 1000,
                        "_yt_query": f"ytsearch1:{t.get('artist', '')} - {t.get('title', '')}",
                    })
                self.after(0, self._render)
                name = result.get("name", "playlist")
                self.after(0, lambda: self.pl_st.config(
                    text=f"Imported {len(self._tracks)} tracks from \"{name}\"", fg=T.LIME_DK))
            except Exception as e:
                self.after(0, lambda: self.pl_st.config(text=f"Error: {str(e)[:60]}", fg=T.RED))

        threading.Thread(target=run, daemon=True).start()

    # ── Transfer dialog ───────────────────────────────────────────────
    def _open_transfer(self):
        """Open a dialog to transfer playlists between services."""
        dlg = tk.Toplevel(self.app)
        dlg.title("Transfer Playlist")
        dlg.geometry("420x320")
        dlg.configure(bg=T.BG)
        dlg.transient(self.app)
        dlg.grab_set()

        tk.Label(dlg, text="Transfer Playlist Between Services", font=T.F_BOLD,
                 bg=T.BG, fg=T.TEXT).pack(pady=(12, 8))

        # Source
        sf = tk.Frame(dlg, bg=T.BG)
        sf.pack(fill="x", padx=16, pady=4)
        tk.Label(sf, text="Source:", font=T.F_BOLD, bg=T.BG, fg=T.TEXT, width=12, anchor="w").pack(side="left")
        src_var = tk.StringVar(value="spotify")
        from tkinter import ttk
        src_cb = ttk.Combobox(sf, textvariable=src_var, values=list(CONNECTOR_LABELS.keys()),
                              state="readonly", width=16, font=T.F_BODY)
        src_cb.pack(side="left", padx=(4, 0))

        # Source URL
        uf = tk.Frame(dlg, bg=T.BG)
        uf.pack(fill="x", padx=16, pady=4)
        tk.Label(uf, text="Playlist URL:", font=T.F_BOLD, bg=T.BG, fg=T.TEXT, width=12, anchor="w").pack(side="left")
        url_var = tk.StringVar(value=self.pl_var.get())
        ClassicEntry(uf, url_var, width=30).pack(side="left", fill="x", expand=True, ipady=2)

        # Target
        tf = tk.Frame(dlg, bg=T.BG)
        tf.pack(fill="x", padx=16, pady=4)
        tk.Label(tf, text="Target:", font=T.F_BOLD, bg=T.BG, fg=T.TEXT, width=12, anchor="w").pack(side="left")
        tgt_var = tk.StringVar(value="youtube")
        tgt_cb = ttk.Combobox(tf, textvariable=tgt_var, values=list(CONNECTOR_LABELS.keys()),
                              state="readonly", width=16, font=T.F_BODY)
        tgt_cb.pack(side="left", padx=(4, 0))

        # Progress
        prog = ClassicProgress(dlg)
        prog.pack(fill="x", padx=16, pady=(12, 4))
        status = tk.Label(dlg, text="Ready", font=T.F_BODY, bg=T.BG, fg=T.TEXT_DIM)
        status.pack(padx=16, anchor="w")

        # Result
        result_lbl = tk.Label(dlg, text="", font=T.F_BODY, bg=T.BG, fg=T.TEXT, wraplength=380)
        result_lbl.pack(padx=16, pady=(4, 0), anchor="w")

        def do_transfer():
            src = src_var.get()
            tgt = tgt_var.get()
            pl_url = url_var.get().strip()
            if not pl_url:
                status.config(text="Enter a playlist URL", fg=T.RED)
                return
            if src == tgt:
                status.config(text="Source and target must differ", fg=T.RED)
                return
            status.config(text=f"Transferring {CONNECTOR_LABELS.get(src)} → {CONNECTOR_LABELS.get(tgt)}...", fg=T.YELLOW)
            prog["value"] = 10

            def run():
                try:
                    from limewire.services.metadata import connector_transfer_playlist
                    report = connector_transfer_playlist(src, tgt, pl_url, self.app.settings)
                    if "error" in report:
                        self.after(0, lambda: status.config(text=report["error"][:60], fg=T.RED))
                        return
                    self.after(0, lambda: prog.configure(value=100))
                    msg = (f"Matched: {report.get('matched', 0)}/{report.get('total', 0)}, "
                           f"Added: {report.get('added', 0)}, Failed: {report.get('failed', 0)}")
                    col = T.LIME_DK if report.get("failed", 0) == 0 else T.YELLOW
                    self.after(0, lambda: (
                        status.config(text="Transfer complete!", fg=col),
                        result_lbl.config(text=msg, fg=T.TEXT)))
                except Exception as e:
                    self.after(0, lambda: status.config(text=f"Error: {str(e)[:60]}", fg=T.RED))

            threading.Thread(target=run, daemon=True).start()

        bf = tk.Frame(dlg, bg=T.BG)
        bf.pack(fill="x", padx=16, pady=(12, 8))
        LimeBtn(bf, "Transfer", do_transfer, width=14).pack(side="left", padx=(0, 6))
        ClassicBtn(bf, "Close", dlg.destroy).pack(side="left")
