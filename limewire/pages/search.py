"""SearchPage -- Search for media by URL, preview metadata, and download audio/video."""

import os, threading, datetime
import tkinter as tk
from tkinter import filedialog

import yt_dlp
import requests
import mutagen
from mutagen.id3 import ID3, APIC, TIT2, TPE1, TDRC
from PIL import ImageTk

from limewire.core.theme import T
from limewire.core.constants import AUDIO_FMTS, VIDEO_FMTS, QUALITIES, RECENT_DL_MAX, YDL_BASE, ydl_opts
from limewire.ui.scroll_frame import ScrollFrame
from limewire.ui.widgets import (
    ClassicBtn, LimeBtn, OrangeBtn, GroupBox,
    ClassicEntry, ClassicCombo, ClassicCheck, ClassicListbox, ClassicProgress, HSep,
    PageSettingsPanel, GearButton,
)
from limewire.utils.helpers import (
    is_url, detect_source, auto_detect_format, sanitize_filename,
    fmt_duration, fetch_thumbnail, open_folder, _SilentLogger,
)
from limewire.services.metadata import spotify_to_youtube


class SearchPage(ScrollFrame):
    """Search for media by URL, preview metadata, and download audio/video."""

    def __init__(self, parent, app):
        super().__init__(parent)
        self.app = app
        self._downloading = False
        self._recent = []
        self._build(self.inner)

    def _build(self, p):
        sf = tk.Frame(p, bg=T.BG, padx=12, pady=10)
        sf.pack(fill="x")
        tk.Label(sf, text="Search:", font=T.F_BOLD, bg=T.BG, fg=T.TEXT).pack(side="left", padx=(0, 8))
        # URL validation indicator
        self.url_indicator = tk.Label(sf, text="\u25cf", font=T.F_BODY, bg=T.BG, fg=T.TEXT_DIM)
        self.url_indicator.pack(side="left", padx=(0, 3))
        self.url_var = tk.StringVar()
        self.url_e = ClassicEntry(sf, self.url_var, width=38)
        self.url_e.pack(side="left", fill="x", expand=True, ipady=3, padx=(0, 6))
        self.url_e.bind("<Return>", lambda e: self._grab())
        self.url_var.trace_add("write", self._on_url_change)
        # Mode toggle
        self.dl_mode = tk.StringVar(value="audio")
        tk.Radiobutton(sf, text="Audio", variable=self.dl_mode, value="audio", font=T.F_SMALL,
                        bg=T.BG, selectcolor=T.INPUT_BG,
                        command=self._mode_changed).pack(side="left")
        tk.Radiobutton(sf, text="Video", variable=self.dl_mode, value="video", font=T.F_SMALL,
                        bg=T.BG, selectcolor=T.INPUT_BG,
                        command=self._mode_changed).pack(side="left", padx=(0, 4))
        tk.Label(sf, text="Fmt:", font=T.F_BODY, bg=T.BG, fg=T.TEXT).pack(side="left", padx=(0, 3))
        self.fmt_var = tk.StringVar(value="mp3")
        self.fmt_combo = ClassicCombo(sf, self.fmt_var, AUDIO_FMTS, width=5)
        self.fmt_combo.pack(side="left", padx=(0, 4))
        tk.Label(sf, text="Q:", font=T.F_BODY, bg=T.BG, fg=T.TEXT).pack(side="left")
        self.qual_var = tk.StringVar(value="1080p")
        self.qual_combo = ClassicCombo(sf, self.qual_var, QUALITIES, width=6)
        self.qual_combo.pack(side="left", padx=(0, 6))
        self.qual_combo.pack_forget()  # hidden in audio mode
        LimeBtn(sf, "Download", self._grab).pack(side="left", padx=(0, 4))
        self.cancel_btn = tk.Button(sf, text="Cancel", font=T.F_BTN, bg=T.RED, fg="#FFFFFF",
                                     relief="flat", bd=0, padx=12, pady=5,
                                     cursor="hand2", command=self._cancel)
        ClassicBtn(sf, "Preview", self._preview).pack(side="left")
        HSep(p)
        self.clip_lbl = tk.Label(p, text="  Tip: Paste URL, or type sc:query / bc:query / yt:query to search",
                                  font=T.F_SMALL, bg=T.CARD_BG, fg=T.TEXT_DIM,
                                  anchor="w", relief="flat", bd=0, padx=8, pady=4,
                                  highlightthickness=1, highlightbackground=T.CARD_BORDER)
        self.clip_lbl.pack(fill="x", padx=10, pady=(6, 0))
        ig = GroupBox(p, "File Information")
        ig.pack(fill="x", padx=10, pady=8)
        ir = tk.Frame(ig, bg=T.BG)
        ir.pack(fill="x")
        # -- Settings panel (hidden by default) --
        self._settings_panel = PageSettingsPanel(p, "search", self.app, [
            ("subtitle_lang", "Subtitle Language", "str", "en", None),
            ("output_template", "Filename Template", "str", "%(title)s.%(ext)s", None),
            ("file_conflict", "File Conflict", "choice", "skip",
             {"choices": ["overwrite", "skip", "rename"]}),
        ])
        self._gear = GearButton(ir, self._settings_panel)
        self._gear.pack(side="right")
        self.thumb = tk.Label(ir, bg=T.CARD_BG, width=18, height=6, text="No\nPreview",
                               font=T.F_SMALL, fg=T.TEXT_DIM,
                               relief="flat", bd=0, highlightthickness=1,
                               highlightbackground=T.CARD_BORDER)
        self.thumb.pack(side="left", padx=(0, 12))
        ic = tk.Frame(ir, bg=T.BG)
        ic.pack(side="left", fill="both", expand=True)

        def irow(par, lbl, default="--"):
            r = tk.Frame(par, bg=T.BG)
            r.pack(fill="x", pady=1)
            tk.Label(r, text=lbl, font=T.F_BOLD, bg=T.BG, fg=T.TEXT, width=10, anchor="w").pack(side="left")
            l = tk.Label(r, text=default, font=T.F_BODY, bg=T.BG, fg=T.TEXT_DIM, anchor="w")
            l.pack(side="left", fill="x", expand=True)
            return l

        self.info_title = irow(ic, "Title:")
        self.info_artist = irow(ic, "Artist:")
        self.info_dur = irow(ic, "Duration:")
        self.info_source = irow(ic, "Source:")
        self.info_status = irow(ic, "Status:", "Ready")
        pg = tk.Frame(ig, bg=T.BG)
        pg.pack(fill="x", pady=(8, 4))
        tk.Label(pg, text="Progress:", font=T.F_BOLD, bg=T.BG, fg=T.TEXT).pack(side="left", padx=(0, 8))
        self.prog = ClassicProgress(pg)
        self.prog.pack(side="left", fill="x", expand=True)
        self.pct_lbl = tk.Label(pg, text="0%", font=T.F_BODY, bg=T.BG, fg=T.TEXT, width=5)
        self.pct_lbl.pack(side="left", padx=(4, 0))

        ag = GroupBox(p, "Actions")
        ag.pack(fill="x", padx=10, pady=(0, 8))
        ar = tk.Frame(ag, bg=T.BG)
        ar.pack(fill="x")
        ClassicBtn(ar, "Open Folder", self._open_folder).pack(side="left", padx=(0, 6))
        ClassicBtn(ar, "Copy Path", self._copy_path).pack(side="left", padx=(0, 6))
        OrangeBtn(ar, "Analyze Last", self._analyze_last).pack(side="left", padx=(0, 6))
        OrangeBtn(ar, "Split Stems", self._stems_last).pack(side="left")
        ar2 = tk.Frame(ag, bg=T.BG)
        ar2.pack(fill="x", pady=(4, 0))
        self.subs_var = tk.BooleanVar(value=False)
        ClassicCheck(ar2, "Download subtitles", self.subs_var).pack(side="left", padx=(0, 12))

        # Settings row
        stg = GroupBox(p, "Settings")
        stg.pack(fill="x", padx=10, pady=(0, 4))
        stgr = tk.Frame(stg, bg=T.BG)
        stgr.pack(fill="x")
        tk.Label(stgr, text="Proxy:", font=T.F_BOLD, bg=T.BG, fg=T.TEXT).pack(side="left")
        self.proxy_var = tk.StringVar(value=self.app.settings.get("proxy", ""))
        ClassicEntry(stgr, self.proxy_var, width=18).pack(side="left", padx=(4, 12), ipady=1)
        tk.Label(stgr, text="Rate Limit:", font=T.F_BOLD, bg=T.BG, fg=T.TEXT).pack(side="left")
        self.rate_var = tk.StringVar(value=self.app.settings.get("rate_limit", ""))
        ClassicEntry(stgr, self.rate_var, width=8).pack(side="left", padx=(4, 12), ipady=1)
        tk.Label(stgr, text="(e.g. 1M, 500K)", font=T.F_SMALL, bg=T.BG, fg=T.TEXT_DIM).pack(side="left", padx=(0, 12))
        self.clip_var = tk.BooleanVar(value=self.app.settings.get("clipboard_watch", True))
        ClassicCheck(stgr, "Clipboard Watch", self.clip_var).pack(side="left")
        ClassicBtn(stgr, "Save", self._save_settings).pack(side="right")

        lg = GroupBox(p, "Save Location")
        lg.pack(fill="x", padx=10, pady=(0, 8))
        lr = tk.Frame(lg, bg=T.BG)
        lr.pack(fill="x")
        self.folder_var = tk.StringVar(value=self.app.output_dir)
        ClassicEntry(lr, self.folder_var, width=55).pack(side="left", fill="x", expand=True, ipady=2, padx=(0, 8))
        ClassicBtn(lr, "Browse...", self._browse).pack(side="left")
        rg = GroupBox(p, "Recent Downloads")
        rg.pack(fill="both", padx=10, pady=(0, 10), expand=True)
        hdr = tk.Frame(rg, bg=T.CARD_BG, bd=0)
        hdr.pack(fill="x")
        tk.Frame(rg, bg=T.CARD_BORDER, height=1).pack(fill="x")
        for t, w in [("Status", 6), ("Title", 35), ("Source", 10), ("Format", 6), ("Time", 6)]:
            tk.Label(hdr, text=t, font=T.F_BTN, bg=T.CARD_BG, fg=T.TEXT, width=w, anchor="w",
                      padx=4, pady=2).pack(side="left")
        self.rec_f, self.rec_lb = ClassicListbox(rg, height=6)
        self.rec_f.pack(fill="both", expand=True)
        self._last_file = None

    def _mode_changed(self):
        if self.dl_mode.get() == "video":
            self.fmt_combo.pack_forget()
            self.fmt_var.set("mp4")
            self.fmt_combo.config(values=VIDEO_FMTS)
            self.fmt_combo.pack(side="left", padx=(0, 4))
            self.qual_combo.pack(side="left", padx=(0, 6))
        else:
            self.qual_combo.pack_forget()
            self.fmt_var.set("mp3")
            self.fmt_combo.config(values=AUDIO_FMTS)

    def _on_url_change(self, *_):
        url = self.url_var.get().strip()
        if not url:
            self.url_indicator.config(fg=T.TEXT_DIM)
        elif url.startswith("sc:"):
            self.url_indicator.config(fg=T.LIME_DK)
            self.clip_lbl.config(text=f"  SoundCloud search: {url[3:].strip()}", fg=T.ORANGE)
        elif url.startswith("bc:"):
            self.url_indicator.config(fg=T.LIME_DK)
            self.clip_lbl.config(text=f"  Bandcamp search: {url[3:].strip()}", fg=T.ORANGE)
        elif url.startswith("yt:"):
            self.url_indicator.config(fg=T.LIME_DK)
            self.clip_lbl.config(text=f"  YouTube search: {url[3:].strip()}", fg=T.ORANGE)
        elif is_url(url):
            self.url_indicator.config(fg=T.LIME_DK)
            src = detect_source(url)
            mode, fmt = auto_detect_format(url)
            if src == "Spotify":
                self.clip_lbl.config(text=f"  Spotify detected \u2014 will resolve to YouTube for download ({mode}/{fmt})", fg=T.ORANGE)
            elif src == "Apple Music":
                self.clip_lbl.config(text=f"  Apple Music detected ({mode}/{fmt})", fg=T.LIME_DK)
            elif mode and fmt:
                self.clip_lbl.config(text=f"  Auto-detected: {src} ({mode}/{fmt})", fg=T.LIME_DK)
        else:
            self.url_indicator.config(fg=T.YELLOW)
            self.clip_lbl.config(text=f"  Will search YouTube for: {url[:50]}", fg=T.TEXT_DIM)

    def _save_settings(self):
        self.app.settings["proxy"] = self.proxy_var.get().strip()
        self.app.settings["rate_limit"] = self.rate_var.get().strip()
        self.app.settings["clipboard_watch"] = self.clip_var.get()
        self.app._save_settings()
        self.app.toast("Settings saved")

    def _cancel(self):
        self.app._cancel.set()
        self.info_status.config(text="Cancelling...", fg=T.YELLOW)

    def _on_clipboard(self, url):
        if not self.url_e.get().strip():
            self.url_var.set(url)
            self.clip_lbl.config(text=f"  Auto-detected {detect_source(url)} URL", fg=T.LIME_DK)

    def _preview(self):
        url = self.url_var.get().strip()
        if not url or "http" not in url:
            return
        self.info_status.config(text="Fetching...", fg=T.YELLOW)
        threading.Thread(target=self._do_pv, args=(url,), daemon=True).start()

    def _do_pv(self, url):
        try:
            with yt_dlp.YoutubeDL(ydl_opts(quiet=True, no_warnings=True, skip_download=True)) as ydl:
                info = ydl.extract_info(url, download=False)
            t = info.get("title", "?")
            a = info.get("uploader") or info.get("channel", "")
            d = fmt_duration(info.get("duration", 0))
            self.after(0, lambda: (
                self.info_title.config(text=t, fg=T.TEXT),
                self.info_artist.config(text=a or "?", fg=T.TEXT),
                self.info_dur.config(text=d, fg=T.TEXT),
                self.info_source.config(text=detect_source(url), fg=T.TEXT_BLUE),
                self.info_status.config(text="Ready", fg=T.LIME_DK)))
            th = info.get("thumbnail", "")
            if th:
                img = fetch_thumbnail(th, (140, 80))
                if img:
                    ph = ImageTk.PhotoImage(img)
                    self.after(0, lambda ph=ph: (
                        self.thumb.config(image=ph, text="", width=140, height=80),
                        setattr(self.thumb, "_img", ph)))
        except Exception as e:
            self.after(0, lambda: self.info_status.config(text=f"Error: {str(e)[:50]}", fg=T.RED))

    def _grab(self):
        url = self.url_var.get().strip()
        if not url:
            return
        # Support search queries: "sc:query" for SoundCloud, "bc:query" for Bandcamp, "yt:query" for YouTube
        if url.startswith("sc:"):
            url = f"scsearch:{url[3:].strip()}"
        elif url.startswith("bc:"):
            url = f"bcsearch:{url[3:].strip()}"
        elif url.startswith("yt:"):
            url = f"ytsearch:{url[3:].strip()}"
        elif "http" not in url and not url.startswith(("scsearch:", "bcsearch:", "ytsearch:")):
            # Treat bare text as YouTube search
            url = f"ytsearch:{url}"
        if self._downloading:
            return
        self._downloading = True
        self.app._cancel.clear()
        self.prog["value"] = 0
        self.pct_lbl.config(text="0%")
        self.cancel_btn.pack(side="left", padx=(4, 0))
        self.info_status.config(text="Starting...", fg=T.YELLOW)
        self.app.set_status("Downloading...")
        threading.Thread(target=self._do_grab, args=(url,), daemon=True).start()

    def _do_grab(self, url):
        fmt = self.fmt_var.get()
        mode = self.dl_mode.get()
        source = detect_source(url)
        # Spotify bridge: resolve to YouTube search URL
        if source == "Spotify":
            self.after(0, lambda: self.info_status.config(text="Resolving Spotify \u2192 YouTube...", fg=T.YELLOW))
            yt_url, err = spotify_to_youtube(url)
            if err:
                self.after(0, lambda: (
                    self.info_status.config(text=f"Spotify error: {err}", fg=T.RED),
                    self.app.toast(f"Spotify: {err}", "error")))
                self._downloading = False
                return
            self.after(0, lambda: self.info_status.config(text="Spotify resolved, downloading...", fg=T.LIME_DK))
            url = yt_url
            source = "Spotify\u2192YouTube"
        out = self.folder_var.get()
        os.makedirs(out, exist_ok=True)
        title = url
        artist = ""

        def hook(d):
            if self.app._cancel.is_set():
                raise Exception("Cancelled by user")
            if d["status"] == "downloading":
                raw = d.get("_percent_str", "0%").strip().replace("%", "")
                try:
                    pct = float(raw)
                except Exception:
                    pct = 0
                spd = d.get("_speed_str", "").strip()
                self.after(0, lambda: (
                    self.prog.configure(value=pct),
                    self.pct_lbl.config(text=f"{pct:.0f}%"),
                    self.info_status.config(text=f"Downloading: {pct:.0f}% {spd}", fg=T.TEXT)))
            elif d["status"] == "finished":
                self.after(0, lambda: (
                    self.prog.configure(value=100),
                    self.pct_lbl.config(text="100%"),
                    self.info_status.config(text=f"Converting to {fmt.upper()}...", fg=T.LIME_DK)))

        extra = self.app.get_ydl_extra()
        # %(title).200B truncates to 200 bytes, avoiding Windows MAX_PATH issues
        outtmpl = os.path.join(out, "%(title).200B.%(ext)s")
        if mode == "audio":
            opts = {"outtmpl": outtmpl, "logger": _SilentLogger(), "progress_hooks": [hook],
                    "quiet": True, "noplaylist": True, "format": "bestaudio/best",
                    "postprocessors": [{"key": "FFmpegExtractAudio", "preferredcodec": fmt}], **extra}
        else:
            q = self.qual_var.get()
            vf = "bestvideo+bestaudio/best" if q == "best" else f"bestvideo[height<={q[:-1]}]+bestaudio/best[height<={q[:-1]}]"
            opts = {"outtmpl": outtmpl, "logger": _SilentLogger(), "progress_hooks": [hook],
                    "quiet": True, "noplaylist": True, "format": vf,
                    "merge_output_format": fmt, **extra}
        if self.subs_var.get():
            opts["writesubtitles"] = True
            opts["writeautomaticsub"] = True
            opts["subtitleslangs"] = ["en"]
        try:
            with yt_dlp.YoutubeDL({**YDL_BASE, **opts}) as ydl:
                info = ydl.extract_info(url, download=True)
                title = info.get("title", "Unknown")
                artist = info.get("uploader") or info.get("channel", "")
                th = info.get("thumbnail", "")
                self.after(0, lambda: (
                    self.info_title.config(text=title, fg=T.TEXT),
                    self.info_artist.config(text=artist or "?", fg=T.TEXT),
                    self.info_dur.config(text=fmt_duration(info.get("duration", 0)), fg=T.TEXT),
                    self.info_source.config(text=source, fg=T.TEXT_BLUE)))
                if th:
                    img = fetch_thumbnail(th, (140, 80))
                    if img:
                        ph = ImageTk.PhotoImage(img)
                        self.after(0, lambda ph=ph: (
                            self.thumb.config(image=ph, text="", width=140, height=80),
                            setattr(self.thumb, "_img", ph)))
            # Find file
            actual = os.path.join(out, f"{title}.{fmt}")
            if not os.path.exists(actual):
                safe = sanitize_filename(title)
                for f in os.listdir(out):
                    if f.endswith(f".{fmt}") and (title[:20] in f or safe[:20] in f):
                        actual = os.path.join(out, f)
                        break
            self._last_file = actual if os.path.exists(actual) else None
            # Tag MP3 -- create ID3 header if missing (mutagen.id3.ID3NoHeaderError)
            if fmt == "mp3" and self._last_file:
                try:
                    try:
                        audio = ID3(self._last_file)
                    except mutagen.id3.ID3NoHeaderError:
                        audio = ID3()
                        audio.save(self._last_file)
                    audio["TIT2"] = TIT2(encoding=3, text=title)
                    audio["TPE1"] = TPE1(encoding=3, text=artist)
                    if info.get("upload_date"):
                        audio["TDRC"] = TDRC(encoding=3, text=info["upload_date"][:4])
                    if th:
                        try:
                            resp = requests.get(th, timeout=5)
                            # Detect MIME from content for correct artwork embedding
                            ct = resp.headers.get("content-type", "image/jpeg")
                            mime = ct.split(";")[0].strip() if ct else "image/jpeg"
                            audio["APIC"] = APIC(encoding=3, mime=mime, type=3, desc="Cover", data=resp.content)
                        except Exception:
                            pass
                    audio.save(self._last_file)
                except Exception:
                    pass
            now_t = datetime.datetime.now().strftime("%H:%M")
            self._recent.insert(0, f"  OK     {title[:35]:35s} {source:10s} {fmt.upper():6s} {now_t}")
            self.after(0, self._render_recent)
            entry = {"title": title, "url": url, "mode": mode, "format": fmt, "status": "done",
                     "source": source, "date": datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
                     "folder": out, "filepath": self._last_file}
            self.after(0, lambda: self.app.add_history(entry))
            self.after(0, lambda: (
                self.info_status.config(text=f"Complete! Saved as {fmt.upper()}", fg=T.LIME_DK),
                self.app.set_status(f"Done: {title}"),
                self.app.toast(f"Downloaded: {title[:40]}")))
        except Exception as e:
            msg = str(e)
            fr = ("Cancelled" if "Cancel" in msg else "Rate limited" if "429" in msg else msg[:80])
            self.after(0, lambda: (
                self.info_status.config(text=f"FAILED: {fr}", fg=T.RED),
                self.app.set_status("Failed"),
                self.app.toast(f"Failed: {fr[:40]}", "error")))
        finally:
            self._downloading = False
            self.after(0, lambda: self.cancel_btn.pack_forget())

    def _render_recent(self):
        self.rec_lb.delete(0, "end")
        for item in self._recent[:RECENT_DL_MAX]:
            self.rec_lb.insert("end", item)

    def _browse(self):
        d = filedialog.askdirectory(initialdir=self.folder_var.get())
        if d:
            self.folder_var.set(d)

    def _open_folder(self):
        open_folder(self.folder_var.get())

    def _copy_path(self):
        self.app.clipboard_clear()
        self.app.clipboard_append(self.folder_var.get())

    def _analyze_last(self):
        if self._last_file and os.path.exists(self._last_file):
            ap = self.app.pages.get("analyze")
            if ap:
                ap.file_var.set(self._last_file)
                self.app._show_tab("analyze")

    def _stems_last(self):
        if self._last_file and os.path.exists(self._last_file):
            sp = self.app.pages.get("stems")
            if sp:
                sp.file_var.set(self._last_file)
                self.app._show_tab("stems")
