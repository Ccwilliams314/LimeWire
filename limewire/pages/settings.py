"""SettingsPage — Tabbed application settings: appearance, audio, playback, etc."""
import threading
import tkinter as tk
from tkinter import ttk, filedialog

from limewire.core.theme import T
from limewire.core.constants import AUDIO_FMTS
from limewire.core.settings_registry import get_setting
from limewire.ui.scroll_frame import ScrollFrame
from limewire.ui.widgets import ClassicBtn, GroupBox, ClassicEntry, ClassicCheck
from limewire.ui.tooltip import ToolTip
from limewire.ui.toast import show_toast

try:
    import sounddevice as sd
    HAS_SD = True
except Exception:
    HAS_SD = False


class SettingsPage(ScrollFrame):
    """Application settings — tabbed multi-section panel."""

    def __init__(self, parent, app):
        super().__init__(parent)
        self.app = app
        self._build(self.inner)

    # ── helpers ───────────────────────────────────────────────────────────
    def _s(self, key, fallback=None):
        """Read a global setting with fallback."""
        v = get_setting(self.app.settings, key)
        return v if v is not None else fallback

    def _set(self, key, value):
        self.app.settings[key] = value
        self.app._save_settings()

    def _row(self, parent, label_text):
        row = tk.Frame(parent, bg=T.BG)
        row.pack(fill="x", pady=(0, 5))
        tk.Label(row, text=label_text, font=T.F_BOLD, bg=T.BG,
                 fg=T.TEXT, width=22, anchor="w").pack(side="left")
        return row

    # ── build ────────────────────────────────────────────────────────────
    def _build(self, p):
        nb = ttk.Notebook(p, style="Settings.TNotebook")
        nb.pack(fill="both", expand=True, padx=6, pady=6)

        self._build_appearance(nb)
        self._build_general(nb)
        self._build_audio(nb)
        self._build_playback(nb)
        self._build_performance(nb)
        self._build_accounts(nb)
        self._build_about(nb)

    # ── Appearance ───────────────────────────────────────────────────────
    def _build_appearance(self, nb):
        f = tk.Frame(nb, bg=T.BG)
        nb.add(f, text="  Appearance  ")
        g = GroupBox(f, "Theme")
        g.pack(fill="x", padx=10, pady=(10, 6))

        r = self._row(g, "Theme:")
        _display = [
            "LiveWire", "Classic Light", "Classic Dark", "Modern Dark",
            "Synthwave", "Dracula", "Catppuccin", "Tokyo Night", "Spotify",
            "LimeWire Classic", "Nord", "Gruvbox", "High Contrast",
            "Old School", "Electric",
        ]
        self._theme_var = tk.StringVar()
        cb = ttk.Combobox(r, textvariable=self._theme_var, values=_display,
                          state="readonly", width=18, font=T.F_BODY)
        cb.pack(side="left", padx=(4, 0))
        cb.set(self.app._theme_key_map.get(
            self.app.settings.get("theme", "livewire"), "LiveWire"))
        cb.bind("<<ComboboxSelected>>", self.app._on_theme_select)
        tk.Label(g, text="Cycle themes via View menu or load a community theme JSON.",
                 font=T.F_SMALL, bg=T.BG, fg=T.TEXT_DIM, anchor="w").pack(fill="x")

        g2 = GroupBox(f, "Font")
        g2.pack(fill="x", padx=10, pady=(0, 6))
        r2 = self._row(g2, "Font Scale:")
        self._font_var = tk.DoubleVar(value=self._s("ui.font_scale", 1.0))
        sc = tk.Scale(r2, variable=self._font_var, from_=0.8, to=1.5,
                      resolution=0.05, orient="horizontal", length=180,
                      bg=T.BG, fg=T.TEXT, troughcolor=T.SURFACE_2,
                      highlightthickness=0, font=T.F_SMALL)
        sc.pack(side="left", padx=(4, 0))
        sc.bind("<ButtonRelease-1>",
                lambda e: self._set("ui.font_scale", self._font_var.get()))
        ToolTip(sc, "Scale all UI fonts (restart to fully apply)")

        g3 = GroupBox(f, "Window")
        g3.pack(fill="x", padx=10, pady=(0, 6))
        self._geo_var = tk.BooleanVar(value=self._s("restore_window_geometry", True))
        ClassicCheck(g3, "Remember window size and position", self._geo_var).pack(anchor="w")
        self._geo_var.trace_add("write",
            lambda *_: self._set("restore_window_geometry", self._geo_var.get()))
        self._tab_var = tk.BooleanVar(value=self._s("restore_active_tab", True))
        ClassicCheck(g3, "Restore last active tab on startup", self._tab_var).pack(anchor="w")
        self._tab_var.trace_add("write",
            lambda *_: self._set("restore_active_tab", self._tab_var.get()))

    # ── General ──────────────────────────────────────────────────────────
    def _build_general(self, nb):
        f = tk.Frame(nb, bg=T.BG)
        nb.add(f, text="  General  ")
        g = GroupBox(f, "Downloads")
        g.pack(fill="x", padx=10, pady=(10, 6))

        r = self._row(g, "Download Folder:")
        self._out_var = tk.StringVar(value=self.app.output_dir)
        ClassicEntry(r, self._out_var, width=35).pack(side="left", padx=(4, 4),
                                                       fill="x", expand=True, ipady=2)
        ClassicBtn(r, "Browse", self._browse_out).pack(side="left")

        g2 = GroupBox(f, "Network")
        g2.pack(fill="x", padx=10, pady=(0, 6))
        r2 = self._row(g2, "Proxy:")
        self._proxy_var = tk.StringVar(value=self.app.settings.get("proxy", ""))
        ClassicEntry(r2, self._proxy_var, width=30).pack(side="left", padx=(4, 4), ipady=2)
        ClassicBtn(r2, "Apply", self._apply_proxy).pack(side="left")

        r3 = self._row(g2, "Rate Limit:")
        self._rate_var = tk.StringVar(value=self.app.settings.get("rate_limit", ""))
        ClassicEntry(r3, self._rate_var, width=15).pack(side="left", padx=(4, 4), ipady=2)
        tk.Label(r3, text="e.g. 5M = 5 MB/s", font=T.F_SMALL,
                 bg=T.BG, fg=T.TEXT_DIM).pack(side="left")
        self._rate_var.trace_add("write",
            lambda *_: self._set("rate_limit", self._rate_var.get().strip()))

        g3 = GroupBox(f, "Behavior")
        g3.pack(fill="x", padx=10, pady=(0, 6))
        self._clip_var = tk.BooleanVar(value=self.app.settings.get("clipboard_watch", True))
        ClassicCheck(g3, "Auto-detect URLs from clipboard", self._clip_var).pack(anchor="w")
        self._clip_var.trace_add("write",
            lambda *_: self._set("clipboard_watch", self._clip_var.get()))

        self._rpc_var = tk.BooleanVar(value=self.app.settings.get("discord_rpc", True))
        ClassicCheck(g3, "Enable Discord Rich Presence", self._rpc_var).pack(anchor="w")
        self._rpc_var.trace_add("write",
            lambda *_: self._set("discord_rpc", self._rpc_var.get()))

        self._exit_var = tk.BooleanVar(value=self._s("confirm_on_exit", False))
        ClassicCheck(g3, "Confirm before exit", self._exit_var).pack(anchor="w")
        self._exit_var.trace_add("write",
            lambda *_: self._set("confirm_on_exit", self._exit_var.get()))

    # ── Audio ────────────────────────────────────────────────────────────
    def _build_audio(self, nb):
        f = tk.Frame(nb, bg=T.BG)
        nb.add(f, text="  Audio  ")
        g = GroupBox(f, "Output")
        g.pack(fill="x", padx=10, pady=(10, 6))

        r = self._row(g, "Output Device:")
        devices = ["Default"]
        if HAS_SD:
            try:
                for d in sd.query_devices():
                    if d.get("max_output_channels", 0) > 0:
                        devices.append(d["name"])
            except Exception:
                pass
        self._dev_var = tk.StringVar(value=self._s("audio.output_device", "Default"))
        cb = ttk.Combobox(r, textvariable=self._dev_var, values=devices,
                          state="readonly", width=30, font=T.F_BODY)
        cb.pack(side="left", padx=(4, 0))
        cb.bind("<<ComboboxSelected>>",
                lambda e: self._set("audio.output_device", self._dev_var.get()))

        g2 = GroupBox(f, "Defaults")
        g2.pack(fill="x", padx=10, pady=(0, 6))

        r2 = self._row(g2, "Default Format:")
        self._fmt_var = tk.StringVar(value=self._s("audio.default_format", "mp3"))
        ttk.Combobox(r2, textvariable=self._fmt_var, values=AUDIO_FMTS,
                     state="readonly", width=10, font=T.F_BODY).pack(side="left", padx=(4, 0))
        self._fmt_var.trace_add("write",
            lambda *_: self._set("audio.default_format", self._fmt_var.get()))

        r3 = self._row(g2, "Default Bitrate:")
        brs = ["320k", "256k", "192k", "128k", "96k", "64k"]
        self._br_var = tk.StringVar(value=self._s("audio.default_bitrate", "320k"))
        ttk.Combobox(r3, textvariable=self._br_var, values=brs,
                     state="readonly", width=10, font=T.F_BODY).pack(side="left", padx=(4, 0))
        self._br_var.trace_add("write",
            lambda *_: self._set("audio.default_bitrate", self._br_var.get()))

        r4 = self._row(g2, "Default Sample Rate:")
        srs = ["22050", "44100", "48000", "96000"]
        self._sr_var = tk.StringVar(value=str(self._s("audio.default_sample_rate", 44100)))
        ttk.Combobox(r4, textvariable=self._sr_var, values=srs,
                     state="readonly", width=10, font=T.F_BODY).pack(side="left", padx=(4, 0))
        self._sr_var.trace_add("write",
            lambda *_: self._set("audio.default_sample_rate", int(self._sr_var.get())))

        r5 = self._row(g2, "Default Channels:")
        chs = ["mono", "stereo"]
        ch_val = "stereo" if self._s("audio.default_channels", 2) == 2 else "mono"
        self._ch_var = tk.StringVar(value=ch_val)
        ttk.Combobox(r5, textvariable=self._ch_var, values=chs,
                     state="readonly", width=10, font=T.F_BODY).pack(side="left", padx=(4, 0))
        self._ch_var.trace_add("write",
            lambda *_: self._set("audio.default_channels",
                                 2 if self._ch_var.get() == "stereo" else 1))

    # ── Playback ─────────────────────────────────────────────────────────
    def _build_playback(self, nb):
        f = tk.Frame(nb, bg=T.BG)
        nb.add(f, text="  Playback  ")
        g = GroupBox(f, "Playback Settings")
        g.pack(fill="x", padx=10, pady=(10, 6))

        r = self._row(g, "Crossfade (ms):")
        self._cf_var = tk.IntVar(value=self._s("playback.crossfade_ms", 0))
        sb = tk.Spinbox(r, textvariable=self._cf_var, from_=0, to=5000,
                        increment=100, width=8, font=T.F_BODY, bg=T.INPUT_BG,
                        fg=T.TEXT, relief="flat", highlightthickness=1,
                        highlightbackground=T.INPUT_BORDER)
        sb.pack(side="left", padx=(4, 0))
        sb.bind("<Return>",
                lambda e: self._set("playback.crossfade_ms", self._cf_var.get()))
        sb.bind("<FocusOut>",
                lambda e: self._set("playback.crossfade_ms", self._cf_var.get()))

        self._gap_var = tk.BooleanVar(value=self._s("playback.gapless", False))
        ClassicCheck(g, "Gapless playback", self._gap_var).pack(anchor="w")
        self._gap_var.trace_add("write",
            lambda *_: self._set("playback.gapless", self._gap_var.get()))

        r2 = self._row(g, "Replay Gain:")
        rg_choices = ["off", "track", "album"]
        self._rg_var = tk.StringVar(value=self._s("playback.replay_gain", "off"))
        ttk.Combobox(r2, textvariable=self._rg_var, values=rg_choices,
                     state="readonly", width=10, font=T.F_BODY).pack(side="left", padx=(4, 0))
        self._rg_var.trace_add("write",
            lambda *_: self._set("playback.replay_gain", self._rg_var.get()))

    # ── Performance ──────────────────────────────────────────────────────
    def _build_performance(self, nb):
        f = tk.Frame(nb, bg=T.BG)
        nb.add(f, text="  Performance  ")
        g = GroupBox(f, "Threading & Limits")
        g.pack(fill="x", padx=10, pady=(10, 6))

        r = self._row(g, "Max Download Threads:")
        self._thr_var = tk.IntVar(value=self._s("perf.max_download_threads", 2))
        tk.Spinbox(r, textvariable=self._thr_var, from_=1, to=8, width=5,
                   font=T.F_BODY, bg=T.INPUT_BG, fg=T.TEXT, relief="flat",
                   highlightthickness=1, highlightbackground=T.INPUT_BORDER
                   ).pack(side="left", padx=(4, 0))
        self._thr_var.trace_add("write",
            lambda *_: self._set("perf.max_download_threads", self._thr_var.get()))

        r2 = self._row(g, "Max Analysis Workers:")
        self._aw_var = tk.IntVar(value=self._s("perf.max_analysis_workers", 4))
        tk.Spinbox(r2, textvariable=self._aw_var, from_=1, to=8, width=5,
                   font=T.F_BODY, bg=T.INPUT_BG, fg=T.TEXT, relief="flat",
                   highlightthickness=1, highlightbackground=T.INPUT_BORDER
                   ).pack(side="left", padx=(4, 0))
        self._aw_var.trace_add("write",
            lambda *_: self._set("perf.max_analysis_workers", self._aw_var.get()))

        r3 = self._row(g, "Discovery Cache Max:")
        self._dc_var = tk.IntVar(value=self._s("perf.discovery_cache_max", 5000))
        tk.Spinbox(r3, textvariable=self._dc_var, from_=500, to=50000,
                   increment=500, width=8, font=T.F_BODY, bg=T.INPUT_BG,
                   fg=T.TEXT, relief="flat", highlightthickness=1,
                   highlightbackground=T.INPUT_BORDER
                   ).pack(side="left", padx=(4, 0))
        self._dc_var.trace_add("write",
            lambda *_: self._set("perf.discovery_cache_max", self._dc_var.get()))

        r4 = self._row(g, "Demucs Device:")
        dev_choices = ["auto", "cpu", "cuda"]
        self._dd_var = tk.StringVar(value=self._s("perf.demucs_device", "auto"))
        ttk.Combobox(r4, textvariable=self._dd_var, values=dev_choices,
                     state="readonly", width=10, font=T.F_BODY).pack(side="left", padx=(4, 0))
        self._dd_var.trace_add("write",
            lambda *_: self._set("perf.demucs_device", self._dd_var.get()))

    # ── Accounts ──────────────────────────────────────────────────────────
    def _build_accounts(self, nb):
        f = tk.Frame(nb, bg=T.BG)
        nb.add(f, text="  Accounts  ")

        g = GroupBox(f, "Service Connectors")
        g.pack(fill="x", padx=10, pady=(10, 6))
        tk.Label(g, text="Link music services for search, playlist import, and transfer.",
                 font=T.F_SMALL, bg=T.BG, fg=T.TEXT_DIM, anchor="w").pack(fill="x", pady=(0, 6))

        from limewire.services.connectors.utils import CONNECTOR_LABELS
        from limewire.services.connectors import storage

        self._acct_status = {}

        for svc, label in CONNECTOR_LABELS.items():
            row = tk.Frame(g, bg=T.BG)
            row.pack(fill="x", pady=(0, 4))
            tk.Label(row, text=label, font=T.F_BOLD, bg=T.BG, fg=T.TEXT, width=16, anchor="w").pack(side="left")
            st_lbl = tk.Label(row, text="Not linked", font=T.F_BODY, bg=T.BG, fg=T.TEXT_DIM, width=14)
            st_lbl.pack(side="left", padx=(4, 8))
            self._acct_status[svc] = st_lbl

            def _connect(s=svc):
                self._connect_service(s)
            def _disconnect(s=svc):
                self._disconnect_service(s)

            ClassicBtn(row, "Connect", _connect).pack(side="left", padx=(0, 4))
            ClassicBtn(row, "Disconnect", _disconnect).pack(side="left")

        # API credentials section
        g2 = GroupBox(f, "API Credentials")
        g2.pack(fill="x", padx=10, pady=(0, 6))
        tk.Label(g2, text="Enter your API keys for services that require them.",
                 font=T.F_SMALL, bg=T.BG, fg=T.TEXT_DIM, anchor="w").pack(fill="x", pady=(0, 6))

        cred_fields = [
            ("spotify_client_id", "Spotify Client ID"),
            ("spotify_client_secret", "Spotify Client Secret"),
            ("youtube_api_key", "YouTube API Key"),
            ("soundcloud_client_id", "SoundCloud Client ID"),
            ("tidal_client_id", "TIDAL Client ID"),
            ("tidal_client_secret", "TIDAL Client Secret"),
            ("deezer_app_id", "Deezer App ID"),
            ("deezer_app_secret", "Deezer App Secret"),
        ]
        self._cred_vars = {}
        for key, label in cred_fields:
            r = self._row(g2, f"{label}:")
            var = tk.StringVar(value=self._s(key, ""))
            self._cred_vars[key] = var
            ClassicEntry(r, var, width=30).pack(side="left", padx=(4, 0), ipady=2)

        ClassicBtn(g2, "Save Credentials", self._save_credentials).pack(anchor="w", pady=(6, 0))

        # Refresh status
        self.after(100, self._refresh_account_status)

    def _refresh_account_status(self):
        try:
            from limewire.services.connectors import storage
            storage.init_db()
            for svc, lbl in self._acct_status.items():
                acct = storage.load_account(svc)
                if acct and acct.get("access_token"):
                    name = acct.get("user_name") or "linked"
                    lbl.config(text=name[:14], fg=T.LIME_DK)
                else:
                    lbl.config(text="Not linked", fg=T.TEXT_DIM)
        except Exception:
            pass

    def _connect_service(self, service):
        """Start OAuth flow for a service in a background thread."""
        show_toast(self.app, f"Connecting {service}...", "info")

        def run():
            try:
                from limewire.services.connectors import build_connector
                conn = build_connector(service, self.app.settings)
                if hasattr(conn, "start_auth"):
                    conn.start_auth()
                    self.after(0, lambda: (
                        self._refresh_account_status(),
                        show_toast(self.app, f"{service} connected!", "info")))
                else:
                    self.after(0, lambda: show_toast(self.app, f"{service} doesn't require auth", "info"))
            except Exception as e:
                self.after(0, lambda: show_toast(self.app, f"Error: {str(e)[:40]}", "error"))

        threading.Thread(target=run, daemon=True).start()

    def _disconnect_service(self, service):
        try:
            from limewire.services.connectors import storage
            storage.init_db()
            storage.remove_account(service)
            self._refresh_account_status()
            show_toast(self.app, f"{service} disconnected", "info")
        except Exception as e:
            show_toast(self.app, f"Error: {str(e)[:40]}", "error")

    def _save_credentials(self):
        for key, var in self._cred_vars.items():
            self._set(key, var.get().strip())
        show_toast(self.app, "API credentials saved", "info")

    # ── About ────────────────────────────────────────────────────────────
    def _build_about(self, nb):
        f = tk.Frame(nb, bg=T.BG)
        nb.add(f, text="  About  ")
        g = GroupBox(f, "LimeWire Studio Edition")
        g.pack(fill="x", padx=10, pady=(10, 6))
        tk.Label(g, text="LimeWire v3.0.0 Studio Edition", font=T.F_BOLD,
                 bg=T.BG, fg=T.LIME_DK).pack(anchor="w")
        tk.Label(g, text="A modern music toolkit with 24 pages — download, play, "
                 "analyze, remix, and more.", font=T.F_BODY,
                 bg=T.BG, fg=T.TEXT, wraplength=500, anchor="w").pack(anchor="w", pady=(4, 0))
        tk.Label(g, text="Built with Python, tkinter, yt-dlp, pyglet, mutagen, "
                 "ffmpeg, demucs, whisper & more.",
                 font=T.F_SMALL, bg=T.BG, fg=T.TEXT_DIM, wraplength=500,
                 anchor="w").pack(anchor="w", pady=(4, 0))

    # ── callbacks ────────────────────────────────────────────────────────
    def _browse_out(self):
        d = filedialog.askdirectory(initialdir=self.app.output_dir)
        if d:
            self.app.output_dir = d
            self._out_var.set(d)
            self.app.settings["output_dir"] = d
            self.app._save_settings()
            show_toast(self.app, f"Download folder: {d}", "info")

    def _apply_proxy(self):
        self.app.settings["proxy"] = self._proxy_var.get().strip()
        self.app._save_settings()
        show_toast(self.app, "Proxy updated", "info")
