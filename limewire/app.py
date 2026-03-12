"""App — Main application class (tk.Tk subclass) for LimeWire Studio Edition."""

import os
import sys
import time
import datetime
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

import yt_dlp
import requests

from limewire.core.theme import (
    T, THEMES, THEME_DARK, apply_theme, _lerp_color,
)
from limewire.core.config import (
    load_json, save_json,
    HISTORY_FILE, SCHEDULE_FILE, SETTINGS_FILE,
    ANALYSIS_CACHE_FILE, SESSION_FILE, RECENT_FILES_FILE,
)
from limewire.core.constants import (
    CLIPBOARD_POLL_MS, CLIPBOARD_INITIAL_DELAY_MS, STATUS_PULSE_MS,
    SCHEDULER_POLL_SEC, HISTORY_MAX, YDL_BASE,
    S, LOGO_BAR_HEIGHT, TOOLBAR_HEIGHT, STATUS_HEIGHT,
    init_dpi_scale, set_user_scale,
)
from limewire.core.settings_registry import apply_defaults, get_setting
from limewire.core.deps import (
    HAS_FFMPEG, HAS_LIBROSA, HAS_LOUDNESS, HAS_SHAZAM, HAS_SHAZAM_SEARCH,
    HAS_MB, HAS_ACOUSTID, HAS_DEMUCS, HAS_PYFLP, HAS_SERATO,
    HAS_PYDUB, HAS_SOUNDDEVICE, HAS_WHISPER, HAS_RUBBERBAND,
    HAS_DND, HAS_DISCORD_RPC, DiscordRPC,
)
from limewire.core.audio_backend import _audio
from limewire.utils.helpers import open_folder, is_url
from limewire.ui.styles import init_limewire_styles
from limewire.ui.widgets import ModernBtn, _round_rect
from limewire.ui.toast import show_toast
from limewire.ui.tooltip import ToolTip
from limewire.ui.command_palette import ShortcutRegistry, CommandPalette
from limewire.i18n import _t, set_language, SUPPORTED_LANGUAGES
from limewire.services.dj_integrations import find_fl_studio
from limewire.services.plugins import PLUGINS_DIR

# Conditional DnD import
if HAS_DND:
    import tkinterdnd2

from limewire.pages import (
    SearchPage, AnalyzePage, StemsPage, DownloadPage, PlaylistPage,
    ConverterPage, PlayerPage, EffectsPage, DiscoveryPage, SamplesPage,
    EditorPage, RecorderPage, SpectrogramPage, PitchTimePage, RemixerPage,
    BatchProcessorPage, SchedulerPage, HistoryPage, SettingsPage, CoverArtPage,
    LyricsPage, VisualizerPage, LibraryPage, DJPage,
)


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        init_dpi_scale(self)
        self.title("LimeWire 3.0.0 Studio Edition")
        self.minsize(760, 700)
        sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
        w, h = min(int(sw * 0.75), sw - 40), min(int(sh * 0.85), sh - 80)
        self.geometry(f"{w}x{h}")
        self.configure(bg=T.BG)
        self._apply_dark_titlebar()
        self._lock = threading.Lock()
        self._sched_lock = threading.Lock()
        self._completed = 0
        self._total = 0
        self._cancel = threading.Event()
        self._dark_mode = False
        self.settings = load_json(SETTINGS_FILE, {"clipboard_watch": True, "proxy": "", "rate_limit": ""})
        apply_defaults(self.settings)
        # Initialize connector database
        try:
            from limewire.services.connectors.storage import init_db
            init_db()
        except Exception:
            pass
        # Apply user font-scale preference
        font_scale = get_setting(self.settings, "ui.font_scale")
        if font_scale and font_scale != 1.0:
            set_user_scale(font_scale)
        set_language(self.settings.get("language", "en"))
        theme_mode = self.settings.get("theme", "livewire")
        self._dark_mode = (theme_mode != "light")
        apply_theme(theme_mode)
        self.history = load_json(HISTORY_FILE, [])
        self.schedule = load_json(SCHEDULE_FILE, [])
        self.output_dir = self.settings.get("output_dir",
                            os.path.join(os.path.expanduser("~"), "Downloads", "LimeWire"))
        self._last_clipboard = ""
        init_limewire_styles(self)
        self._build_menubar()
        self._build_logo_bar()
        self._build_toolbar()
        self._build_notebook()
        self._build_statusbar()
        self._start_scheduler()
        self._start_clipboard_watch()
        self._bind_shortcuts()
        # Restore window geometry
        if get_setting(self.settings, "restore_window_geometry"):
            saved_geo = self.settings.get("window_geometry")
            if saved_geo:
                try: self.geometry(saved_geo)
                except Exception: pass
        # Restore last active tab
        if get_setting(self.settings, "restore_active_tab"):
            saved_tab = self.settings.get("last_active_tab")
            if saved_tab and saved_tab in self.pages:
                self.after(100, lambda: self._show_tab(saved_tab))
        self._setup_dnd()
        self._restore_session()
        self._init_discord_rpc()
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.bind("<Shift-Escape>", lambda e: self._on_close())

    # ── Session persistence ──────────────────────────────────────────────────
    def _save_session(self):
        session = {"active_tab": self._get_active_tab(), "files": {}, "player_playlist": []}
        for name, page in self.pages.items():
            if hasattr(page, "file_var"):
                v = page.file_var.get()
                if v:
                    session["files"][name] = v
        pp = self.pages.get("player")
        if pp:
            session["player_playlist"] = list(pp._playlist)
        save_json(SESSION_FILE, session)

    def _restore_session(self):
        session = load_json(SESSION_FILE, {})
        if not session:
            return
        for name, path in session.get("files", {}).items():
            page = self.pages.get(name)
            if page and hasattr(page, "file_var") and os.path.exists(path):
                page.file_var.set(path)
        pp = self.pages.get("player")
        if pp:
            for path in session.get("player_playlist", []):
                if os.path.exists(path) and path not in pp._playlist_set:
                    pp._playlist.append(path)
                    pp._playlist_set.add(path)
                    title, artist, dur_str = pp._get_track_meta(path)
                    pp.plb.insert("", "end",
                                  iid=str(len(pp._playlist) - 1),
                                  values=(title, artist, dur_str))
            pp._update_playlist_count()
        tab = session.get("active_tab", "")
        if tab:
            self.after(100, lambda: self._show_tab(tab))

    # ── Window setup ─────────────────────────────────────────────────────────
    def _apply_dark_titlebar(self):
        if sys.platform != "win32":
            return
        try:
            import ctypes
            hwnd = ctypes.windll.user32.GetParent(self.winfo_id())
            DWMWA_USE_IMMERSIVE_DARK_MODE = 20
            val = ctypes.c_int(1 if self._dark_mode else 0)
            ctypes.windll.dwmapi.DwmSetWindowAttribute(
                hwnd, DWMWA_USE_IMMERSIVE_DARK_MODE, ctypes.byref(val), ctypes.sizeof(val),
            )
        except Exception:
            pass

    def _on_close(self):
        # Save window geometry and active tab
        try:
            self.settings["window_geometry"] = self.geometry()
        except Exception:
            pass
        if hasattr(self, "_current_tab"):
            self.settings["last_active_tab"] = self._current_tab
        self._save_settings()
        self._save_session()
        self._cancel.set()
        self._close_discord_rpc()
        try:
            _audio.stop()
        except Exception:
            pass
        self.destroy()

    # ── Discord Rich Presence ────────────────────────────────────────────────
    def _init_discord_rpc(self):
        self._discord_rpc = None
        if not HAS_DISCORD_RPC or not self.settings.get("discord_rpc", True):
            return

        def _connect():
            try:
                rpc = DiscordRPC("1234567890123456789")
                rpc.connect()
                self._discord_rpc = rpc
                self._update_discord_rpc("Idle", "LimeWire Studio Edition")
            except Exception:
                self._discord_rpc = None

        threading.Thread(target=_connect, daemon=True).start()

    def _update_discord_rpc(self, state, details, large_text="LimeWire"):
        if not self._discord_rpc:
            return
        try:
            self._discord_rpc.update(
                state=state, details=details[:128],
                large_image="limewire_logo", large_text=large_text,
                start=int(time.time()),
            )
        except Exception:
            self._discord_rpc = None

    def _close_discord_rpc(self):
        if self._discord_rpc:
            try:
                self._discord_rpc.close()
            except Exception:
                pass

    # ── Keyboard shortcuts ───────────────────────────────────────────────────
    def _bind_shortcuts(self):
        self._shortcut_reg = ShortcutRegistry()
        sr = self._shortcut_reg
        sr.load_custom(self.settings.get("custom_shortcuts", {}))
        sr.register("Ctrl+D", "Download / Grab URL", lambda: self.pages["search"]._grab(), "grab_url")
        sr.register("Ctrl+O", "Open downloads folder", self._open_dl_folder, "open_folder")
        sr.register("Space", "Play / Pause", lambda: self._space_toggle(None), "play_pause")
        sr.register("Ctrl+K", "Command Palette", lambda: CommandPalette(self), "command_palette")
        sr.register("Ctrl+?", "Show shortcuts", lambda: self._shortcut_reg.show_help(self), "show_shortcuts")
        sr.register("Ctrl+Right", "Next track", lambda: self._media_next(), "next_track")
        sr.register("Ctrl+Left", "Previous track", lambda: self._media_prev(), "prev_track")
        sr.register("Ctrl+Up", "Volume up", lambda: self._media_vol(5), "vol_up")
        sr.register("Ctrl+Down", "Volume down", lambda: self._media_vol(-5), "vol_down")
        sr.register("Left", "Seek back 5s (Player)", lambda: self._player_seek(-5), "seek_back")
        sr.register("Right", "Seek forward 5s (Player)", lambda: self._player_seek(5), "seek_fwd")
        sr.register("Shift+Left", "Seek back 15s (Player)", lambda: self._player_seek(-15), "seek_back_long")
        sr.register("Shift+Right", "Seek forward 15s (Player)", lambda: self._player_seek(15), "seek_fwd_long")
        sr.register("Tab", "Focus next widget", lambda: self._focus_cycle(1), "focus_next")
        sr.register("Shift+Tab", "Focus previous widget", lambda: self._focus_cycle(-1), "focus_prev")
        sr.register("Enter", "Trigger primary action", lambda: self._primary_action(), "primary_action")
        self._apply_bindings()

    def _apply_bindings(self):
        self.bind("<Control-d>", lambda e: self.pages["search"]._grab())
        self.bind("<Control-o>", lambda e: self._open_dl_folder())
        self.bind("<space>", lambda e: self._space_toggle(e))
        self.bind("<Control-k>", lambda e: CommandPalette(self))
        self.bind("<Control-question>", lambda e: self._shortcut_reg.show_help(self))
        self.bind("<Control-Right>", lambda e: self._media_next())
        self.bind("<Control-Left>", lambda e: self._media_prev())
        self.bind("<Control-Up>", lambda e: self._media_vol(5))
        self.bind("<Control-Down>", lambda e: self._media_vol(-5))
        self.bind("<Left>", lambda e: self._arrow_key(e, -5))
        self.bind("<Right>", lambda e: self._arrow_key(e, 5))
        self.bind("<Shift-Left>", lambda e: self._arrow_key(e, -15))
        self.bind("<Shift-Right>", lambda e: self._arrow_key(e, 15))
        self.bind_all("<Tab>", self._on_tab_key)
        self.bind_all("<Shift-Tab>", self._on_shift_tab_key)
        self.bind("<Return>", self._on_enter_key)

    def _rebind_shortcuts(self):
        self._bind_shortcuts()

    def _arrow_key(self, e, delta):
        if isinstance(e.widget, (tk.Entry, ttk.Entry, ttk.Combobox, tk.Text, tk.Listbox, tk.Spinbox)):
            return
        if self._get_active_tab() == "player":
            self._player_seek(delta)
            return "break"

    def _player_seek(self, delta):
        pp = self.pages.get("player")
        if pp and pp._playing and pp._dur > 0:
            cur_pos = _audio.get_pos()
            new_pos = max(0, min(pp._dur, cur_pos + delta))
            _audio.play(start=new_pos)
            pp._playing = True
            pp.play_b.config(text="Pause")

    def _on_tab_key(self, e):
        if isinstance(e.widget, (tk.Text,)):
            return
        self._focus_cycle(1)
        return "break"

    def _on_shift_tab_key(self, e):
        if isinstance(e.widget, (tk.Text,)):
            return
        self._focus_cycle(-1)
        return "break"

    def _focus_cycle(self, direction):
        tab = self._get_active_tab()
        page = self.pages.get(tab)
        if not page:
            return
        focusable = []

        def _collect(w):
            for child in w.winfo_children():
                if isinstance(child, (tk.Entry, ttk.Entry, ttk.Combobox, tk.Spinbox, tk.Listbox)):
                    focusable.append(child)
                elif isinstance(child, ModernBtn):
                    focusable.append(child)
                elif isinstance(child, (tk.Button, ttk.Button)):
                    focusable.append(child)
                elif isinstance(child, (ttk.Scale,)):
                    focusable.append(child)
                _collect(child)

        _collect(page)
        if not focusable:
            return
        cur = self.focus_get()
        try:
            idx = focusable.index(cur)
        except (ValueError, Exception):
            idx = -1 if direction == 1 else len(focusable)
        nxt = (idx + direction) % len(focusable)
        focusable[nxt].focus_set()

    def _on_enter_key(self, e):
        if isinstance(e.widget, (tk.Entry, ttk.Entry, ttk.Combobox, tk.Text, tk.Listbox, tk.Spinbox)):
            return
        self._primary_action()

    def _primary_action(self):
        tab = self._get_active_tab()
        page = self.pages.get(tab)
        if not page:
            return
        actions = {
            "search": "_grab", "download": "_start_batch", "playlist": "_fetch",
            "converter": "_convert", "player": "_toggle", "analyze": "_analyze",
            "stems": "_separate", "effects": "_apply", "discovery": "_scan",
            "samples": "_preview_sel", "editor": "_export",
            "recorder": "_toggle_rec", "spectrogram": "_generate",
            "pitchtime": "_apply", "remixer": "_export",
            "batch": "_run", "schedule": "_add", "history": "_redownload",
            "coverart": "_apply_selected",
        }
        method_name = actions.get(tab)
        if method_name and hasattr(page, method_name):
            getattr(page, method_name)()

    def _space_toggle(self, e):
        if e and isinstance(e.widget, (tk.Entry, ttk.Entry, ttk.Combobox, tk.Text, tk.Listbox, tk.Spinbox)):
            return
        pp = self.pages.get("player")
        if pp:
            pp._toggle()

    def _media_next(self):
        pp = self.pages.get("player")
        if pp:
            pp._next()

    def _media_prev(self):
        pp = self.pages.get("player")
        if pp:
            pp._prev()

    def _media_vol(self, delta):
        pp = self.pages.get("player")
        if pp and hasattr(pp, "vol"):
            v = max(0, min(100, pp.vol.get() + delta))
            pp.vol.set(v)
            _audio.set_volume(v / 100)

    # ── Drag and Drop ────────────────────────────────────────────────────────
    def _setup_dnd(self):
        if not HAS_DND:
            return
        try:
            self.drop_target_register(tkinterdnd2.DND_FILES, tkinterdnd2.DND_TEXT)
            self.dnd_bind("<<Drop>>", self._on_drop)
        except Exception:
            pass

    def _on_drop(self, e):
        data = e.data.strip()
        if data.startswith("http"):
            sp = self.pages.get("search")
            if sp:
                sp.url_var.set(data)
                self._show_tab("search")
        elif os.path.exists(data.strip("{}")):
            path = data.strip("{}")
            if not path.lower().endswith((".mp3", ".wav", ".flac", ".ogg", ".m4a", ".aac", ".opus")):
                return
            active = self._get_active_tab()
            page = self.pages.get(active)
            if page and hasattr(page, "file_var"):
                page.file_var.set(path)
                self._add_recent_file(path)
                if hasattr(page, "_load"):
                    self.after(50, page._load)
                elif hasattr(page, "_load_file"):
                    self.after(50, page._load_file)
            else:
                pp = self.pages.get("player")
                if pp and path not in pp._playlist_set:
                    pp._playlist.append(path)
                    pp._playlist_set.add(path)
                    title, artist, dur_str = pp._get_track_meta(path)
                    pp.plb.insert("", "end",
                                  iid=str(len(pp._playlist) - 1),
                                  values=(title, artist, dur_str))
                self._show_tab("player")

    # ── Recent files ─────────────────────────────────────────────────────────
    def _add_recent_file(self, path):
        if not path or not os.path.exists(path):
            return
        recent = load_json(RECENT_FILES_FILE, [])
        if path in recent:
            recent.remove(path)
        recent.insert(0, path)
        save_json(RECENT_FILES_FILE, recent[:15])
        if hasattr(self, "_recent_menu"):
            self._refresh_recent_menu()

    def _refresh_recent_menu(self):
        self._recent_menu.delete(0, "end")
        recent = load_json(RECENT_FILES_FILE, [])
        if not recent:
            self._recent_menu.add_command(label="(none)", state="disabled")
            return
        for path in recent[:10]:
            name = os.path.basename(path)
            self._recent_menu.add_command(label=name, command=lambda p=path: self._open_recent(p))
        self._recent_menu.add_separator()
        self._recent_menu.add_command(
            label="Clear Recent",
            command=lambda: (save_json(RECENT_FILES_FILE, []), self._refresh_recent_menu()),
        )

    def _open_recent(self, path):
        if not os.path.exists(path):
            show_toast(self, "File not found", "warning")
            return
        active = self._get_active_tab()
        page = self.pages.get(active)
        if page and hasattr(page, "file_var"):
            page.file_var.set(path)
            if hasattr(page, "_load"):
                self.after(50, page._load)
            elif hasattr(page, "_load_file"):
                self.after(50, page._load_file)
        else:
            pp = self.pages.get("player")
            if pp and path not in pp._playlist_set:
                pp._playlist.append(path)
                pp._playlist_set.add(path)
                title, artist, dur_str = pp._get_track_meta(path)
                pp.plb.insert("", "end",
                              iid=str(len(pp._playlist) - 1),
                              values=(title, artist, dur_str))
            self._show_tab("player")

    # ── Menu bar ─────────────────────────────────────────────────────────────
    def _build_menubar(self):
        _mc = dict(
            bg=T.SURFACE_2, fg=T.TEXT, activebackground=T.LIME, activeforeground=T.BG_DARK,
            disabledforeground=T.TEXT_DIM, font=T.F_BODY,
        )
        mb = tk.Menu(self, **_mc)
        fm = tk.Menu(mb, tearoff=0, **_mc)
        fm.add_command(label="Open Downloads Folder", command=self._open_dl_folder)
        self._recent_menu = tk.Menu(fm, tearoff=0, **_mc)
        fm.add_cascade(label="Recent Files", menu=self._recent_menu)
        self._refresh_recent_menu()
        fm.add_separator()
        fm.add_command(label="Exit", command=self.destroy)
        mb.add_cascade(label="File", menu=fm)

        tm = tk.Menu(mb, tearoff=0, **_mc)
        tm.add_command(
            label="Clear History",
            command=lambda: (self.history.clear(), save_json(HISTORY_FILE, []))
            if messagebox.askyesno("Clear", "Clear?") else None,
        )
        tm.add_separator()
        tm.add_command(label="Cycle Theme (Light/Dark/Modern)", command=self._toggle_dark_mode)
        tm.add_command(label="Check yt-dlp Update", command=self._check_ytdlp_update)
        tm.add_command(label="Check App Update", command=self._check_app_update)
        tm.add_separator()
        tm.add_command(label="Cloud Sync \u2192 Export", command=self._cloud_sync_export)
        tm.add_command(label="Cloud Sync \u2192 Import", command=self._cloud_sync_import)
        tm.add_separator()
        tm.add_command(label="Open Plugins Folder", command=lambda: open_folder(PLUGINS_DIR))
        tm.add_separator()

        lm = tk.Menu(tm, tearoff=0, **_mc)
        lang_names = {"en": "English", "es": "Espa\u00f1ol", "fr": "Fran\u00e7ais",
                      "de": "Deutsch", "ja": "\u65e5\u672c\u8a9e", "pt": "Portugu\u00eas"}
        for code in SUPPORTED_LANGUAGES:
            lm.add_command(
                label=lang_names.get(code, code),
                command=lambda c=code: [
                    set_language(c),
                    self.settings.__setitem__("language", c),
                    self._save_settings(),
                    show_toast(self, f"Language: {lang_names.get(c, c)} (restart for full effect)", "info"),
                ],
            )
        tm.add_cascade(label="Language", menu=lm)
        tm.add_command(label="Load Community Theme", command=self._load_community_theme)
        tm.add_command(label="Set FL Studio Path", command=self._set_fl_path)
        mb.add_cascade(label="Tools", menu=tm)

        hm = tk.Menu(mb, tearoff=0, **_mc)
        caps = []
        if HAS_LIBROSA: caps.append("BPM/Key")
        if HAS_LOUDNESS: caps.append("LUFS")
        if HAS_SHAZAM: caps.append("Shazam Audio ID")
        elif HAS_SHAZAM_SEARCH: caps.append("Shazam Search")
        if HAS_MB: caps.append("MusicBrainz")
        if HAS_ACOUSTID: caps.append("Chromaprint")
        if HAS_DEMUCS: caps.append("Demucs Stems")
        cap_str = ", ".join(caps) if caps else "None (install optional deps)"
        hm.add_command(label="About", command=lambda: messagebox.showinfo("About",
            f"LimeWire v3.0.0 Studio Edition\n\n"
            f"The modern music utility for everything.\n"
            f"Powered by yt-dlp + Demucs + librosa + pydub\n\n"
            f"24 pages: Search, Batch DL, Playlist, Convert, Player,\n"
            f"Lyrics, Visualizer, Analyze, Stems, Effects, Discovery,\n"
            f"Library, DJ, Samples, Editor, Recorder, Spectrogram,\n"
            f"Pitch/Time, Remixer, Batch Process, Scheduler, History,\n"
            f"Cover Art, Settings\n\n"
            f"Active modules: {cap_str}\n\n"
            f"v2.0: Plugin system, VST3/AU hosting, MIDI mapping,\n"
            f"cloud sync, auto-update, SoundCloud/Bandcamp search,\n"
            f"Discord RPC, keyboard customization, arrow seek,\n"
            f"15 themes + community themes, 6 languages.\n\n"
            f"Optional: pip install librosa pyloudnorm demucs pydub\n"
            f"  sounddevice pyrubberband openai-whisper shazamio pypresence mido\n\n"
            f"\"Definitely virus-free since 2024\""))
        mb.add_cascade(label="Help", menu=hm)
        self.config(menu=mb)

    # ── Logo bar ─────────────────────────────────────────────────────────────
    def _build_logo_bar(self):
        LOGO_H = S(LOGO_BAR_HEIGHT)
        bar = tk.Canvas(self, height=LOGO_H, highlightthickness=0, bd=0)
        bar.pack(fill="x")

        def _draw_gradient(e=None):
            w = bar.winfo_width()
            h = LOGO_H
            bar.delete("grad")
            steps = max(1, w // 3)
            for i in range(steps):
                t = i / max(1, steps - 1)
                t = t * t * (3 - 2 * t)
                c = _lerp_color(T.ACCENT_START, T.ACCENT_END, t)
                x = int(i * w / steps)
                x2 = int((i + 1) * w / steps) + 1
                bar.create_rectangle(x, 0, x2, h, fill=c, outline="", tags="grad")
            bar.create_rectangle(0, h - 1, w, h, fill=_lerp_color(T.ACCENT_END, "#000000", 0.4), outline="", tags="grad")
            bar.tag_lower("grad")
            bar.delete("fg")
            cx, cy = 30, LOGO_H // 2
            bar.create_oval(cx - 17, cy - 17, cx + 17, cy + 17, fill="",
                            outline=_lerp_color(T.ACCENT_START, "#FFFFFF", 0.3), width=2, tags="fg")
            bar.create_oval(cx - 13, cy - 13, cx + 13, cy + 13,
                            fill=_lerp_color(T.ACCENT_START, "#000000", 0.2), outline="", tags="fg")
            bar.create_text(cx, cy, text=T.LOGO_ICON, font=("Segoe UI", 14), fill="#FFFFFF", tags="fg")
            tx = 56
            ty = LOGO_H // 2
            bar.create_text(tx + 1, ty + 1, text=T.LOGO_TEXT, font=T.F_LOGO,
                            fill=_lerp_color(T.ACCENT_END, "#000000", 0.5), anchor="w", tags="fg")
            bar.create_text(tx, ty, text=T.LOGO_TEXT, font=T.F_LOGO, fill="#FFFFFF", anchor="w", tags="fg")
            bx = 230 if len(T.LOGO_TEXT) > 10 else 200
            by = LOGO_H // 2
            _round_rect(bar, bx, by - 11, bx + 82, by + 11, radius=11,
                        fill=_lerp_color(T.ACCENT_START, "#000000", 0.35),
                        outline=_lerp_color(T.ACCENT_START, "#FFFFFF", 0.15), tags="fg")
            bar.create_text(bx + 41, by, text="v3.0.0 Studio", font=("Segoe UI Semibold", 8), fill="#FFFFFF", tags="fg")
            sx = w - 90
            sy = LOGO_H // 2
            self._status_x = sx
            self._status_y = sy
            bar.create_oval(sx - 4, sy - 4, sx + 4, sy + 4, fill=T.SUCCESS, outline="", tags=("fg", "status_dot"))
            bar.create_text(sx + 12, sy, text="Ready", font=T.F_CAPTION,
                            fill=_lerp_color("#FFFFFF", T.ACCENT_END, 0.15), anchor="w", tags="fg")

        bar.bind("<Configure>", _draw_gradient)
        self._logo_bar = bar
        self._pulse_status()

    def _pulse_status(self):
        try:
            bar = self._logo_bar
            dot = bar.find_withtag("status_dot")
            if dot:
                cur = bar.itemcget(dot[0], "fill")
                bright = _lerp_color(T.SUCCESS, "#FFFFFF", 0.4)
                nxt = bright if cur == T.SUCCESS else T.SUCCESS
                bar.itemconfig(dot[0], fill=nxt)
        except Exception:
            pass
        try:
            if self.winfo_exists():
                self.after(STATUS_PULSE_MS, self._pulse_status)
        except Exception:
            pass

    # ── Toolbar ──────────────────────────────────────────────────────────────
    def _build_toolbar(self):
        tk.Frame(self, bg=T.DIVIDER, height=1).pack(fill="x")
        tb = tk.Frame(self, bg=T.TOOLBAR, height=S(TOOLBAR_HEIGHT))
        tb.pack(fill="x")
        tb.pack_propagate(False)
        self._toolbar = tb
        self._tb_btns = {}
        items = [
            ("search", "\U0001F50D", "Search"), ("download", "\U0001F4E5", "Download"),
            ("playlist", "\U0001F4CB", "Playlist"), ("converter", "\U0001F504", "Convert"),
            ("player", "\U0001F3B5", "Player"), ("analyze", "\U0001F4CA", "Analyze"),
            ("stems", "\U0001F39A", "Stems"), ("effects", "\u2728", "Effects"),
            ("discovery", "\U0001F30D", "Discover"), ("samples", "\U0001F3B6", "Samples"),
            ("editor", "\u2702", "Editor"), ("recorder", "\U0001F3A4", "Record"),
            ("spectrogram", "\U0001F308", "Spectro"), ("pitchtime", "\U0001F3B9", "Pitch"),
            ("remixer", "\U0001F3A7", "Remix"), ("batch", "\u2699", "Batch"),
            ("schedule", "\u23F0", "Schedule"), ("history", "\U0001F4DC", "History"),
            ("coverart", "\U0001F5BC", "Cover"),
            ("lyrics", "\U0001F4DD", "Lyrics"),
            ("visualizer", "\U0001F4A0", "Visual"),
            ("library", "\U0001F4DA", "Library"),
            ("dj", "\U0001F39B", "DJ"),
            ("settings", "\u2699\uFE0F", "Settings"),
        ]
        for name, icon, label in items:
            bf = tk.Frame(tb, bg=T.TOOLBAR, cursor="hand2")
            bf.pack(side="left", padx=2, pady=(3, 0))
            il = tk.Label(bf, text=icon, font=("Segoe UI", 11), bg=T.TOOLBAR, fg=T.TEXT_DIM)
            il.pack(side="top", pady=(0, 0))
            nl = tk.Label(bf, text=label, font=T.F_TAB, bg=T.TOOLBAR, fg=T.TEXT_DIM)
            nl.pack(side="top")
            # Spacer replaces old static indicator
            tk.Frame(bf, bg=T.TOOLBAR, height=3).pack(fill="x", side="bottom", pady=(1, 0))
            self._tb_btns[name] = (bf, il, nl)
            ToolTip(bf, f"Go to {label}")
            for w in (bf, il, nl):
                w.bind("<Button-1>", lambda e, n=name: self._show_tab(n))
                w.bind("<Enter>", lambda e, n=name: self._tb_hover(n, True))
                w.bind("<Leave>", lambda e, n=name: self._tb_hover(n, False))

        # Sliding indicator bar
        self._tb_indicator = tk.Canvas(tb, height=S(3), bg=T.TOOLBAR,
                                       highlightthickness=0, bd=0)
        self._tb_indicator.place(relx=0, rely=1.0, y=-S(4),
                                 relwidth=1.0, height=S(3))
        self._tb_ind_rect = self._tb_indicator.create_rectangle(
            0, 0, 0, S(3), fill=T.TAB_ACTIVE, outline="")

        _theme_display = [
            "LiveWire", "Classic Light", "Classic Dark", "Modern Dark",
            "Synthwave", "Dracula", "Catppuccin", "Tokyo Night", "Spotify",
            "LimeWire Classic", "Nord", "Gruvbox", "High Contrast",
            "Old School", "Electric",
        ]
        _theme_keys = list(THEMES.keys())
        self._theme_name_map = dict(zip(_theme_display, _theme_keys))
        self._theme_key_map = dict(zip(_theme_keys, _theme_display))
        tk.Frame(self, bg=T.DIVIDER, height=1).pack(fill="x")

    def _tb_hover(self, name, entering):
        if name not in self._tb_btns:
            return
        bf, il, nl = self._tb_btns[name]
        if entering:
            for w in (bf, il, nl):
                w.config(bg=T.BTN_HOVER)
            il.config(fg=T.TEXT)
            nl.config(fg=T.TEXT)
        else:
            active = self._get_active_tab()
            bg = T.TOOLBAR
            fg = T.TEXT_DIM
            if name == active:
                fg = T.TAB_ACTIVE
            for w in (bf, il, nl):
                w.config(bg=bg)
            il.config(fg=fg)
            nl.config(fg=fg)

    def _get_active_tab(self):
        try:
            idx = self.nb.index(self.nb.select())
            return list(self.pages.keys())[idx]
        except Exception:
            return ""

    def _update_tb_active(self):
        active = self._get_active_tab()
        for name, (bf, il, nl) in self._tb_btns.items():
            if name == active:
                il.config(fg=T.TAB_ACTIVE)
                nl.config(fg=T.TAB_ACTIVE)
            else:
                il.config(fg=T.TEXT_DIM)
                nl.config(fg=T.TEXT_DIM)
        # Slide indicator to active tab
        if active in self._tb_btns and hasattr(self, "_tb_indicator"):
            bf = self._tb_btns[active][0]
            self.after(10, lambda: self._slide_indicator(
                bf.winfo_x(), bf.winfo_width()))

    def _slide_indicator(self, tx, tw, steps=6, step=0):
        if step >= steps:
            self._tb_indicator.coords(self._tb_ind_rect,
                                      tx, 0, tx + tw, S(3))
            return
        cx1, _, cx2, _ = self._tb_indicator.coords(self._tb_ind_rect)
        t = (step + 1) / steps
        t = t * t * (3 - 2 * t)  # smoothstep easing
        nx1 = cx1 + (tx - cx1) * t
        nx2 = cx2 + ((tx + tw) - cx2) * t
        self._tb_indicator.coords(self._tb_ind_rect, nx1, 0, nx2, S(3))
        self.after(16, lambda: self._slide_indicator(tx, tw, steps, step + 1))

    # ── Notebook ─────────────────────────────────────────────────────────────
    def _build_notebook(self):
        self.nb = ttk.Notebook(self, style="TNotebook")
        self.nb.pack(fill="both", expand=True, padx=4)
        # Force tab bar hidden after notebook creation
        s = ttk.Style()
        s.layout("TNotebook", [("TNotebook.client", {"sticky": "nswe"})])
        self.pages = {}
        for name, label, cls in [
            ("search", "Search & Grab", SearchPage),
            ("download", "Batch Download", DownloadPage),
            ("playlist", "Playlist", PlaylistPage),
            ("converter", "Converter", ConverterPage),
            ("player", "Player", PlayerPage),
            ("lyrics", "Lyrics", LyricsPage),
            ("visualizer", "Visualizer", VisualizerPage),
            ("analyze", "Analyze", AnalyzePage),
            ("stems", "Stems", StemsPage),
            ("effects", "Effects", EffectsPage),
            ("discovery", "Discovery", DiscoveryPage),
            ("library", "Library", LibraryPage),
            ("dj", "DJ", DJPage),
            ("samples", "Samples", SamplesPage),
            ("editor", "Editor", EditorPage),
            ("recorder", "Recorder", RecorderPage),
            ("spectrogram", "Spectrogram", SpectrogramPage),
            ("pitchtime", "Pitch/Time", PitchTimePage),
            ("remixer", "Remixer", RemixerPage),
            ("batch", "Batch Process", BatchProcessorPage),
            ("schedule", "Schedule", SchedulerPage),
            ("history", "History", HistoryPage),
            ("coverart", "Cover Art", CoverArtPage),
            ("settings", "Settings", SettingsPage),
        ]:
            page = cls(self.nb, self)
            self.nb.add(page, text=f" {label} ")
            self.pages[name] = page
        self.nb.bind("<<NotebookTabChanged>>", self._on_tab)

    def _show_tab(self, name):
        keys = list(self.pages.keys())
        if name not in keys:
            return
        # Page wipe transition
        if not hasattr(self, "_wipe_cv"):
            self._wipe_cv = tk.Canvas(self.nb, highlightthickness=0, bd=0)
        self._wipe_cv.configure(bg=T.BG)
        self._wipe_cv.place(relx=0, rely=0, relwidth=1, relheight=1)
        tk.Misc.tkraise(self._wipe_cv)
        self.nb.select(keys.index(name))
        self._wipe_step(5)

    def _wipe_step(self, remaining):
        if remaining <= 0:
            self._wipe_cv.place_forget()
            return
        frac = remaining / 5
        self._wipe_cv.place(relx=0, rely=0, relwidth=1, relheight=frac)
        self.after(18, lambda: self._wipe_step(remaining - 1))

    def _on_tab(self, e=None):
        idx = self.nb.index(self.nb.select())
        keys = list(self.pages.keys())
        if idx < len(keys):
            self._current_tab = keys[idx]
            if hasattr(self.pages[keys[idx]], "refresh"):
                self.pages[keys[idx]].refresh()
        if hasattr(self, "_tb_btns"):
            self._update_tb_active()

    # ── Status bar ───────────────────────────────────────────────────────────
    def _build_statusbar(self):
        tk.Frame(self, bg=T.DIVIDER, height=1).pack(fill="x", side="bottom")
        sb = tk.Frame(self, bg=T.SURFACE_3, height=S(STATUS_HEIGHT))
        sb.pack(fill="x", side="bottom")
        sb.pack_propagate(False)
        self.status_lbl = tk.Label(
            sb, text="Ready  |  Ctrl+D: Download  Space: Play/Pause  Ctrl+O: Open Folder",
            font=T.F_STATUS, bg=T.SURFACE_3, fg=T.TEXT_DIM, anchor="w",
        )
        self.status_lbl.pack(side="left", padx=10, fill="x", expand=True)
        tk.Frame(sb, bg=T.DIVIDER, width=1).pack(side="left", fill="y", pady=5)
        self.dl_count_lbl = tk.Label(
            sb, text=f"\u2193 {len(self.history)}", font=T.F_STATUS,
            bg=T.SURFACE_3, fg=T.TEXT, padx=10,
        )
        self.dl_count_lbl.pack(side="left")
        tk.Frame(sb, bg=T.DIVIDER, width=1).pack(side="left", fill="y", pady=5)

        mod_map = {
            "FFmpeg": HAS_FFMPEG, "BPM/Key": HAS_LIBROSA, "LUFS": HAS_LOUDNESS,
            "Shazam": HAS_SHAZAM or HAS_SHAZAM_SEARCH,
            "MusicBrainz": HAS_MB, "Chromaprint": HAS_ACOUSTID, "Demucs": HAS_DEMUCS,
            "FL Studio": HAS_PYFLP, "Serato": HAS_SERATO,
            "pydub": HAS_PYDUB, "SoundDevice": HAS_SOUNDDEVICE,
            "Whisper": HAS_WHISPER, "Rubberband": HAS_RUBBERBAND,
        }
        loaded = sum(mod_map.values())
        total = len(mod_map)
        missing = [k for k, v in mod_map.items() if not v]
        tip = f"Missing: {', '.join(missing)}" if missing else "All modules loaded"
        color = T.SUCCESS if loaded >= int(total * 0.8) else T.WARNING if loaded >= int(total * 0.5) else T.ERROR
        mod_lbl = tk.Label(
            sb, text=f"\u25CF {loaded}/{total}", font=T.F_STATUS,
            bg=T.SURFACE_3, fg=color, padx=10, cursor="hand2",
        )
        mod_lbl.pack(side="left")
        mod_lbl.bind("<Button-1>", lambda e: messagebox.showinfo("Module Status",
            "\n".join(f"{chr(0x2713) if v else chr(0x2717)} {k}" for k, v in mod_map.items()) + "\n\n" + tip))

    # ── Public helpers ───────────────────────────────────────────────────────
    def set_status(self, text):
        self.status_lbl.config(text=text)

    def toast(self, msg, level="info"):
        show_toast(self, msg, level)

    def add_history(self, entry):
        self.history.insert(0, entry)
        save_json(HISTORY_FILE, self.history[:HISTORY_MAX])
        self.dl_count_lbl.config(text=f"\u2193 {len(self.history)}")

    def _open_dl_folder(self):
        os.makedirs(self.output_dir, exist_ok=True)
        open_folder(self.output_dir)

    # ── Theme switching ──────────────────────────────────────────────────────
    def _toggle_dark_mode(self):
        cycle = [
            "livewire", "light", "dark", "modern", "synthwave", "dracula",
            "catppuccin", "tokyo", "spotify", "classic", "nord", "gruvbox", "highcontrast",
        ]
        cur = self.settings.get("theme", "livewire")
        if cur not in cycle:
            cur = "livewire"
        nxt = cycle[(cycle.index(cur) + 1) % len(cycle)]
        old = THEMES.get(cur, THEME_DARK)
        apply_theme(nxt)
        self._dark_mode = (nxt != "light")
        new = THEMES.get(nxt, THEME_DARK)
        self.settings["theme"] = nxt
        self._save_settings()
        cmap = {v.lower(): new[k].lower() for k, v in old.items() if isinstance(v, str) and v.startswith("#")}
        init_limewire_styles(self)
        self._reconfig_all(self, cmap)
        if hasattr(self, "_logo_bar"):
            self._logo_bar.event_generate("<Configure>")
        sp = self.pages.get("settings")
        if sp and hasattr(sp, "_theme_combo"):
            sp._theme_combo.set(self._theme_key_map.get(nxt, nxt))
        show_toast(self, f"Theme: {self._theme_key_map.get(nxt, nxt)}", "info")

    def _on_theme_select(self, event=None):
        sp = self.pages.get("settings")
        if not sp:
            return
        display = sp._theme_var.get()
        nxt = self._theme_name_map.get(display, "livewire")
        cur = self.settings.get("theme", "livewire")
        if nxt == cur:
            return
        old = THEMES.get(cur, THEME_DARK)
        apply_theme(nxt)
        self._dark_mode = (nxt != "light")
        new = THEMES.get(nxt, THEME_DARK)
        self.settings["theme"] = nxt
        self._save_settings()
        cmap = {v.lower(): new[k].lower() for k, v in old.items() if isinstance(v, str) and v.startswith("#")}
        init_limewire_styles(self)
        self._reconfig_all(self, cmap)
        if hasattr(self, "_logo_bar"):
            self._logo_bar.event_generate("<Configure>")
        show_toast(self, f"Theme: {display}", "info")

    def _reconfig_all(self, widget, cmap):
        def _remap(color):
            if not color or not isinstance(color, str):
                return None
            return cmap.get(color.lower())

        try:
            wtype = widget.winfo_class()
            if wtype in ("Frame", "Labelframe"):
                old_bg = widget.cget("bg").lower()
                new_bg = _remap(old_bg) or T.BG
                widget.configure(bg=new_bg)
                if wtype == "Labelframe":
                    try:
                        widget.configure(bg=T.CARD_BG, fg=T.TEXT,
                                         highlightbackground=T.CARD_BORDER, highlightcolor=T.CARD_BORDER)
                    except Exception:
                        pass
            elif wtype == "Label":
                old_bg = widget.cget("bg").lower()
                new_bg = _remap(old_bg) or T.BG
                widget.configure(bg=new_bg)
                try:
                    old_fg = widget.cget("fg").lower()
                    new_fg = _remap(old_fg)
                    if new_fg:
                        widget.configure(fg=new_fg)
                except Exception:
                    pass
            elif wtype == "Checkbutton":
                try:
                    widget.configure(bg=T.BG, fg=T.TEXT, activebackground=T.BG,
                                     activeforeground=T.LIME, selectcolor=T.SURFACE_2)
                except Exception:
                    pass
            elif wtype == "Radiobutton":
                try:
                    widget.configure(bg=T.BG, fg=T.TEXT, activebackground=T.BG,
                                     activeforeground=T.LIME, selectcolor=T.SURFACE_2)
                except Exception:
                    pass
            elif wtype == "Entry":
                try:
                    widget.configure(bg=T.INPUT_BG, fg=T.TEXT, insertbackground=T.LIME,
                                     highlightbackground=T.INPUT_BORDER, highlightcolor=T.INPUT_FOCUS,
                                     selectbackground=T.BLUE_HL, selectforeground="#FFFFFF")
                except Exception:
                    pass
            elif wtype == "Listbox":
                try:
                    widget.configure(bg=T.INPUT_BG, fg=T.TEXT,
                                     selectbackground=T.BLUE_HL, selectforeground="#FFFFFF")
                except Exception:
                    pass
            elif wtype == "Scrollbar":
                try:
                    widget.configure(bg=T.BG, troughcolor=T.TROUGH)
                except Exception:
                    pass
            elif wtype == "Spinbox":
                try:
                    widget.configure(bg=T.INPUT_BG, fg=T.TEXT, buttonbackground=T.BG,
                                     insertbackground=T.TEXT,
                                     selectbackground=T.BLUE_HL, selectforeground="#FFFFFF")
                except Exception:
                    pass
            elif wtype == "Canvas":
                if isinstance(widget, ModernBtn):
                    new_bg = _remap(widget._bg_c)
                    new_fg = _remap(widget._fg_c)
                    new_hv = _remap(widget._hover_c)
                    if new_bg:
                        widget._bg_c = new_bg
                        widget.itemconfig(widget._rect, fill=new_bg)
                    if new_fg:
                        widget._fg_c = new_fg
                        widget.itemconfig(widget._label, fill=new_fg)
                    if new_hv:
                        widget._hover_c = new_hv
                    try:
                        widget.itemconfig(widget._outline, outline=T.DIVIDER)
                    except Exception:
                        pass
                    try:
                        pbg = widget.master.cget("bg") if hasattr(widget.master, "cget") else T.BG
                        widget.configure(bg=pbg)
                    except Exception:
                        pass
                elif widget != getattr(self, "_logo_bar", None):
                    old_bg = widget.cget("bg").lower()
                    new_bg = _remap(old_bg)
                    widget.configure(bg=new_bg if new_bg else T.BG)
            elif wtype == "Menu":
                try:
                    widget.configure(bg=T.SURFACE_2, fg=T.TEXT, activebackground=T.LIME,
                                     activeforeground=T.BG_DARK, disabledforeground=T.TEXT_DIM)
                except Exception:
                    pass
            elif wtype == "Toplevel":
                widget.configure(bg=T.BG)
        except Exception:
            pass
        for child in widget.winfo_children():
            self._reconfig_all(child, cmap)

    # ── Update checks ────────────────────────────────────────────────────────
    def _check_ytdlp_update(self):
        self.set_status("Checking yt-dlp version...")

        def _check():
            try:
                cur = yt_dlp.version.__version__
                resp = requests.get("https://pypi.org/pypi/yt-dlp/json", timeout=10)
                latest = resp.json()["info"]["version"]
                if cur != latest:
                    self.after(0, lambda: show_toast(
                        self, f"yt-dlp update available: {cur} \u2192 {latest}\nRun: pip install -U yt-dlp", "warn", 5000))
                else:
                    self.after(0, lambda: show_toast(self, f"yt-dlp {cur} is up to date", "info"))
                self.after(0, lambda: self.set_status(f"yt-dlp: {cur} (latest: {latest})"))
            except Exception as e:
                self.after(0, lambda: show_toast(self, f"Update check failed: {str(e)[:60]}", "error"))

        threading.Thread(target=_check, daemon=True).start()

    def _load_community_theme(self):
        f = filedialog.askopenfilename(
            filetypes=[("Theme JSON", "*.json"), ("All", "*.*")],
            title="Load Community Theme",
        )
        if not f:
            return
        try:
            data = load_json(f, {})
            if not isinstance(data, dict) or "BG" not in data:
                show_toast(self, "Invalid theme file \u2014 must have BG, TEXT, LIME, etc. keys", "error")
                return
            name = os.path.splitext(os.path.basename(f))[0].lower().replace(" ", "_")
            for k, v in THEME_DARK.items():
                if k not in data:
                    data[k] = v
            THEMES[name] = data
            old = THEMES.get(self.settings.get("theme", "livewire"), THEME_DARK)
            apply_theme(name)
            self._dark_mode = True
            new = data
            self.settings["theme"] = name
            self._save_settings()
            cmap = {v.lower(): new[k].lower() for k, v in old.items() if isinstance(v, str) and v.startswith("#")}
            init_limewire_styles(self)
            self._reconfig_all(self, cmap)
            if hasattr(self, "_logo_bar"):
                self._logo_bar.event_generate("<Configure>")
            show_toast(self, f"Theme loaded: {name}", "success")
        except Exception as e:
            show_toast(self, f"Theme error: {str(e)[:60]}", "error")

    def _check_app_update(self):
        self.set_status("Checking for updates...")

        def _check():
            try:
                resp = requests.get("https://api.github.com/repos/Ccwilliams314/LimeWire/releases/latest", timeout=10)
                if resp.status_code == 200:
                    data = resp.json()
                    tag = data.get("tag_name", "")
                    current = "v3.0.0"
                    if tag and tag > current:
                        self.after(0, lambda: show_toast(
                            self, f"Update available: {tag}\nVisit GitHub to download", "warn", 8000))
                    else:
                        self.after(0, lambda: show_toast(self, f"LimeWire {current} is up to date", "info"))
                self.after(0, lambda: self.set_status("Ready"))
            except Exception as e:
                self.after(0, lambda: show_toast(self, f"Update check failed: {str(e)[:50]}", "error"))

        threading.Thread(target=_check, daemon=True).start()

    # ── Cloud sync ───────────────────────────────────────────────────────────
    def _cloud_sync_export(self):
        sync_dir = self.settings.get("cloud_sync_dir", "")
        if not sync_dir:
            sync_dir = filedialog.askdirectory(title="Select Cloud Sync Folder (Dropbox/OneDrive/Google Drive)")
            if not sync_dir:
                return
            self.settings["cloud_sync_dir"] = sync_dir
            self._save_settings()
        os.makedirs(sync_dir, exist_ok=True)
        for name, src in [("settings", SETTINGS_FILE), ("history", HISTORY_FILE),
                          ("schedule", SCHEDULE_FILE), ("analysis_cache", ANALYSIS_CACHE_FILE)]:
            data = load_json(src, {} if name != "history" else [])
            save_json(os.path.join(sync_dir, f"limewire_{name}.json"), data)
        show_toast(self, "Settings exported to cloud sync folder", "success")

    def _cloud_sync_import(self):
        sync_dir = self.settings.get("cloud_sync_dir", "")
        if not sync_dir:
            sync_dir = filedialog.askdirectory(title="Select Cloud Sync Folder")
            if not sync_dir:
                return
        imported = 0
        for name, dest in [("settings", SETTINGS_FILE), ("history", HISTORY_FILE),
                           ("schedule", SCHEDULE_FILE), ("analysis_cache", ANALYSIS_CACHE_FILE)]:
            src = os.path.join(sync_dir, f"limewire_{name}.json")
            if os.path.exists(src):
                data = load_json(src, {})
                if data:
                    save_json(dest, data)
                    imported += 1
        if imported:
            self.settings = load_json(SETTINGS_FILE, self.settings)
            self.history = load_json(HISTORY_FILE, [])
            show_toast(self, f"Imported {imported} files from cloud sync", "success")
        else:
            show_toast(self, "No sync files found in folder", "warning")

    def _set_fl_path(self):
        current = self.settings.get("fl_studio_path", "")
        detected = find_fl_studio()
        initial = os.path.dirname(current or detected or r"C:\Program Files\Image-Line")
        path = filedialog.askopenfilename(
            title="Select FL64.exe", initialdir=initial,
            filetypes=[("FL Studio", "FL64.exe FL.exe"), ("All", "*.*")],
        )
        if path:
            self.settings["fl_studio_path"] = path
            self._save_settings()
            self.toast(f"FL Studio path: {os.path.basename(path)}")

    def _save_settings(self):
        save_json(SETTINGS_FILE, self.settings)

    def get_ydl_extra(self):
        extra = {}
        proxy = self.settings.get("proxy", "").strip()
        if proxy:
            extra["proxy"] = proxy
        rl = self.settings.get("rate_limit", "").strip()
        if rl:
            extra["ratelimit"] = self._parse_rate(rl)
        return extra

    @staticmethod
    def _parse_rate(s):
        s = s.strip().upper()
        try:
            if s.endswith("M"):
                return int(float(s[:-1]) * 1024 * 1024)
            if s.endswith("K"):
                return int(float(s[:-1]) * 1024)
            return int(s)
        except Exception:
            return None

    # ── Background tasks ─────────────────────────────────────────────────────
    def _start_clipboard_watch(self):
        def _poll():
            try:
                if not self.winfo_exists():
                    return
            except Exception:
                return
            if self.settings.get("clipboard_watch", True):
                try:
                    clip = self.clipboard_get().strip()
                    if clip != self._last_clipboard and is_url(clip):
                        self._last_clipboard = clip
                        sp = self.pages.get("search")
                        if sp:
                            self.after(0, lambda: sp._on_clipboard(clip))
                except Exception:
                    pass
            self.after(CLIPBOARD_POLL_MS, _poll)

        self.after(CLIPBOARD_INITIAL_DELAY_MS, _poll)

    def _start_scheduler(self):
        def _loop():
            while True:
                time.sleep(SCHEDULER_POLL_SEC)
                now = datetime.datetime.now()
                with self._sched_lock:
                    for job in self.schedule:
                        if job.get("status") != "pending":
                            continue
                        try:
                            when = datetime.datetime.strptime(job["when"], "%Y-%m-%d %H:%M")
                        except Exception:
                            continue
                        if now >= when:
                            job["status"] = "running"
                            threading.Thread(target=self._run_sched, args=(job,), daemon=True).start()
                            save_json(SCHEDULE_FILE, self.schedule)

        threading.Thread(target=_loop, daemon=True).start()

    def _run_sched(self, job):
        url = job.get("url", "")
        fmt = job.get("format", "mp3")
        out = job.get("folder", self.output_dir)
        os.makedirs(out, exist_ok=True)
        opts = {
            "quiet": True,
            "outtmpl": os.path.join(out, "%(title)s.%(ext)s"),
            "format": "bestaudio/best",
            "postprocessors": [{"key": "FFmpegExtractAudio", "preferredcodec": fmt}],
            **self.get_ydl_extra(),
        }
        try:
            with yt_dlp.YoutubeDL({**YDL_BASE, **opts}) as ydl:
                ydl.download([url])
                status = "done"
        except Exception:
            status = "error"
        with self._sched_lock:
            job["status"] = status
            save_json(SCHEDULE_FILE, self.schedule)
