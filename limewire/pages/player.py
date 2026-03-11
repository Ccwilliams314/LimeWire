"""PlayerPage — Audio player with waveform visualization, A-B looping, and EQ spectrum."""
import os, threading, datetime, random, bisect
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from io import BytesIO

import mutagen
from PIL import Image, ImageTk

from limewire.core.theme import T, _lerp_color
from limewire.core.constants import (
    PLAYER_WAVEFORM_W, PLAYER_WAVEFORM_H, PLAYER_UPDATE_MS,
    EQ_BAR_COUNT, EQ_PEAK_DECAY, SP_LG, SP_XS,
)
from limewire.core.config import load_json, save_json, ANALYSIS_CACHE_FILE
from limewire.core.audio_backend import _audio
from limewire.ui.scroll_frame import ScrollFrame
from limewire.ui.widgets import (ClassicBtn, LimeBtn, OrangeBtn, GroupBox,
                                  ClassicProgress, PageSettingsPanel, GearButton)
from limewire.ui.toast import show_toast
from limewire.utils.helpers import fmt_duration
from limewire.services.cover_art import extract_cover_art
from limewire.services.audio_processing import (
    generate_waveform_data, compute_frequency_profile,
)


class PlayerPage(ScrollFrame):
    """Audio player with waveform visualization, A-B looping, and EQ spectrum."""
    def __init__(self, parent, app):
        super().__init__(parent); self.app = app
        self._playlist = []; self._playlist_set = set()  # O(1) membership checks
        self._cur = -1; self._playing = False; self._dur = 0
        self._seeking = False; self._wave_bars = []; self._ab_a = None; self._ab_b = None
        self._lock = threading.Lock()  # protects _wave_bars from background thread
        # Shuffle & repeat state
        self._shuffle = False
        self._repeat_mode = "off"  # "off" | "all" | "one"
        self._shuffle_order = []
        self._shuffle_idx = -1
        # Frequency profile for real EQ
        self._freq_times = None
        self._freq_bands = None
        self._freq_loading = False
        # Crossfade state
        self._crossfading = False
        # Elapsed/remaining toggle
        self._show_remaining = False
        # Drag-to-reorder state
        self._drag_src = None
        # Mini-player reference
        self._mini_win = None
        self._build(self.inner)

    def _build(self, p):
        ng = GroupBox(p, "Now Playing"); ng.pack(fill="x", padx=10, pady=(10, 6))
        nr = tk.Frame(ng, bg=T.BG); nr.pack(fill="x")
        # -- Settings panel (hidden by default) --
        self._settings_panel = PageSettingsPanel(p, "player", self.app, [
            ("eq_preset", "EQ Preset", "choice", "Flat",
             {"choices": ["Flat", "Bass Boost", "Treble Boost", "Vocal", "Classical"]}),
            ("art_display_size", "Album Art Size", "choice", "160",
             {"choices": ["120", "160", "200", "240"]}),
        ])
        self._gear = GearButton(nr, self._settings_panel)
        self._gear.pack(side="right")
        self._blank_art = tk.PhotoImage(width=160, height=160)
        self.art = tk.Label(nr, bg=T.SURFACE_2, image=self._blank_art,
                            text="\u266A", compound="center",
                            font=("Segoe UI", 28), fg=T.TEXT_DIM,
                            relief="flat", bd=0, cursor="hand2",
                            highlightthickness=1, highlightbackground=T.CARD_BORDER)
        self.art.pack(side="left", padx=(0, 12))
        self.art.bind("<Button-1>", self._show_fullsize_art)
        self._art_data = None
        ni = tk.Frame(nr, bg=T.BG); ni.pack(side="left", fill="both", expand=True)
        self.np_t = tk.Label(ni, text="No track loaded", font=T.F_HEADER, bg=T.BG,
                             fg=T.TEXT, anchor="w")
        self.np_t.pack(fill="x")
        self.np_a = tk.Label(ni, text="", font=T.F_BODY, bg=T.BG, fg=T.TEXT_DIM,
                             anchor="w")
        self.np_a.pack(fill="x", pady=(2, 0))

        # Waveform (click to seek)
        self.wave_cv = tk.Canvas(ng, bg=T.CANVAS_BG, height=50, relief="flat", bd=0,
                                 highlightthickness=1, highlightbackground=T.CARD_BORDER,
                                 cursor="hand2")
        self.wave_cv.pack(fill="x", pady=(6, 0))
        self.wave_cv.bind("<Button-1>", self._wave_click)

        sr = tk.Frame(ng, bg=T.BG); sr.pack(fill="x", pady=(6, 0))
        self.pos_l = tk.Label(sr, text="0:00", font=T.F_SMALL, bg=T.BG, fg=T.TEXT,
                              width=6, cursor="hand2")
        self.pos_l.pack(side="left")
        self.pos_l.bind("<Button-1>", self._toggle_elapsed)
        self.seek_v = tk.DoubleVar(value=0)
        self.seek = ttk.Scale(sr, from_=0, to=100, orient="horizontal",
                              variable=self.seek_v, command=self._oseek)
        self.seek.pack(side="left", fill="x", expand=True, padx=4)
        self.seek.bind("<ButtonPress-1>", self._slider_press)
        self.seek.bind("<ButtonRelease-1>", self._slider_release)
        self.dur_l = tk.Label(sr, text="0:00", font=T.F_SMALL, bg=T.BG, fg=T.TEXT,
                              width=6)
        self.dur_l.pack(side="left")

        cr = tk.Frame(ng, bg=T.BG); cr.pack(pady=(6, 4))
        ClassicBtn(cr, "|<", self._prev, width=4).pack(side="left", padx=2)
        self.play_b = LimeBtn(cr, "Play", self._toggle, width=8)
        self.play_b.pack(side="left", padx=4)
        ClassicBtn(cr, ">|", self._next, width=4).pack(side="left", padx=2)
        OrangeBtn(cr, "Analyze", self._analyze_cur).pack(side="left", padx=(12, 4))
        OrangeBtn(cr, "Split Stems", self._stems_cur).pack(side="left")
        ClassicBtn(cr, "Mini", self._toggle_mini, width=5).pack(side="left", padx=(12, 0))

        # Up Next indicator
        self._upnext_lbl = tk.Label(ng, text="", font=T.F_SMALL, bg=T.BG,
                                    fg=T.TEXT_DIM, anchor="w")
        self._upnext_lbl.pack(fill="x", pady=(SP_XS, 0))

        # ── Playback Options ────────────────────────────────────────────────
        og = GroupBox(p, "Playback Options"); og.pack(fill="x", padx=10, pady=(0, 6))

        spr = tk.Frame(og, bg=T.BG); spr.pack(fill="x")
        tk.Label(spr, text="Speed:", font=T.F_BOLD, bg=T.BG, fg=T.TEXT).pack(
            side="left", padx=(0, 4))
        self.speed_var = tk.StringVar(value="1.0x")
        for spd in ["0.5x", "0.75x", "1.0x", "1.25x", "1.5x", "2.0x"]:
            tk.Radiobutton(spr, text=spd, variable=self.speed_var, value=spd,
                           font=T.F_SMALL, bg=T.BG, fg=T.TEXT,
                           selectcolor=T.LIME_DK, activebackground=T.BTN_HOVER,
                           indicator=0, padx=8, pady=3, relief="flat", bd=0,
                           highlightthickness=1, highlightbackground=T.CARD_BORDER,
                           command=self._apply_speed).pack(side="left", padx=1)
        tk.Label(spr, text="  ", bg=T.BG).pack(side="left")
        ClassicBtn(spr, "Set A", self._set_ab_a, width=5).pack(side="left", padx=(0, 2))
        ClassicBtn(spr, "Set B", self._set_ab_b, width=5).pack(side="left", padx=(0, 2))
        self.ab_lbl = tk.Label(spr, text="A-B: off", font=T.F_SMALL, bg=T.BG,
                               fg=T.TEXT_DIM)
        self.ab_lbl.pack(side="left", padx=(4, 0))
        ClassicBtn(spr, "Clear", self._clear_ab, width=5).pack(side="left", padx=(4, 0))

        vr = tk.Frame(og, bg=T.BG); vr.pack(fill="x", pady=(4, 0))
        tk.Label(vr, text="Vol:", font=T.F_BOLD, bg=T.BG, fg=T.TEXT).pack(
            side="left", padx=(0, 6))
        self.vol = tk.DoubleVar(value=80)
        ttk.Scale(vr, from_=0, to=100, orient="horizontal", variable=self.vol,
                  command=lambda v: _audio.set_volume(float(v) / 100)).pack(side="left")
        tk.Label(vr, text="  Crossfade:", font=T.F_BOLD, bg=T.BG, fg=T.TEXT).pack(
            side="left", padx=(SP_LG, SP_XS))
        self._crossfade_ms = tk.IntVar(value=0)
        tk.Spinbox(vr, from_=0, to=5000, increment=500, textvariable=self._crossfade_ms,
                   width=5, font=T.F_BODY, bg=T.INPUT_BG, fg=T.TEXT, relief="flat",
                   bd=0, highlightthickness=1,
                   highlightbackground=T.INPUT_BORDER).pack(side="left")
        tk.Label(vr, text="ms", font=T.F_SMALL, bg=T.BG, fg=T.TEXT_DIM).pack(
            side="left", padx=SP_XS)

        # Shuffle & Repeat row
        mr = tk.Frame(og, bg=T.BG); mr.pack(fill="x", pady=(4, 0))
        self._shuf_btn = ClassicBtn(mr, "Shuffle: Off", self._toggle_shuffle, width=12)
        self._shuf_btn.pack(side="left", padx=(0, 8))
        self._rep_btn = ClassicBtn(mr, "Repeat: Off", self._cycle_repeat, width=12)
        self._rep_btn.pack(side="left")

        # EQ Spectrum Visualizer
        eqg = GroupBox(p, "EQ Spectrum"); eqg.pack(fill="x", padx=10, pady=(0, 6))
        self.eq_cv = tk.Canvas(eqg, bg=T.CANVAS_BG, height=60, relief="flat", bd=0,
                               highlightthickness=1, highlightbackground=T.CARD_BORDER)
        self.eq_cv.pack(fill="x")
        self._eq_bars = []
        self._eq_peaks = []
        self._init_eq_bars()

        # ── Playlist (Treeview) ─────────────────────────────────────────────
        self._pl_title_var = tk.StringVar(value="Playlist")
        plg = GroupBox(p, "Playlist")
        plg.pack(fill="both", padx=10, pady=(0, 10), expand=True)
        self._plg = plg  # keep ref for title updates
        pr = tk.Frame(plg, bg=T.BG); pr.pack(fill="x", pady=(0, 6))
        LimeBtn(pr, "+ Add", self._addf).pack(side="left", padx=(0, 4))
        ClassicBtn(pr, "Add Downloads", self._adddl).pack(side="left", padx=(0, 4))
        ClassicBtn(pr, "Save M3U", self._save_m3u).pack(side="left", padx=(0, 4))
        ClassicBtn(pr, "Load M3U", self._load_m3u).pack(side="left", padx=(0, 4))
        OrangeBtn(pr, "Share JSON", self._share_playlist_json).pack(
            side="left", padx=(0, 4))
        ClassicBtn(pr, "Import JSON", self._import_playlist_json).pack(
            side="left", padx=(0, 4))
        ClassicBtn(pr, "Clear", self._clr).pack(side="left")

        # Treeview with columns
        tvf = tk.Frame(plg, bg=T.BG); tvf.pack(fill="both", expand=True)
        cols = ("title", "artist", "duration")
        self.plb = ttk.Treeview(tvf, columns=cols, show="headings", height=7,
                                 selectmode="browse")
        self.plb.heading("title", text="Title")
        self.plb.heading("artist", text="Artist")
        self.plb.heading("duration", text="Duration")
        self.plb.column("title", width=300, minwidth=100)
        self.plb.column("artist", width=150, minwidth=60)
        self.plb.column("duration", width=60, minwidth=40, anchor="e")
        sb = ttk.Scrollbar(tvf, orient="vertical", command=self.plb.yview)
        self.plb.configure(yscrollcommand=sb.set)
        self.plb.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")

        self.plb.bind("<Double-Button-1>", self._psel)
        self.plb.bind("<Button-3>", self._playlist_context_menu)
        self.plb.bind("<Delete>", lambda e: self._remove_selected())
        self.plb.bind("<BackSpace>", lambda e: self._remove_selected())
        # Drag-to-reorder bindings
        self.plb.bind("<ButtonPress-1>", self._drag_start)
        self.plb.bind("<B1-Motion>", self._drag_motion)
        self.plb.bind("<ButtonRelease-1>", self._drag_end)

        self._upd_pos()

    # ── Shuffle & Repeat ───────────────────────────────────────────────────────
    def _toggle_shuffle(self):
        self._shuffle = not self._shuffle
        self._shuf_btn.config(text=f"Shuffle: {'On' if self._shuffle else 'Off'}")
        if self._shuffle:
            self._rebuild_shuffle_order()
        self._update_upnext()

    def _cycle_repeat(self):
        modes = ["off", "all", "one"]
        idx = modes.index(self._repeat_mode)
        self._repeat_mode = modes[(idx + 1) % 3]
        labels = {"off": "Repeat: Off", "all": "Repeat: All", "one": "Repeat: One"}
        self._rep_btn.config(text=labels[self._repeat_mode])
        self._update_upnext()

    def _rebuild_shuffle_order(self):
        """Build a shuffled index list, placing current track first."""
        n = len(self._playlist)
        if n == 0:
            self._shuffle_order = []; self._shuffle_idx = -1; return
        order = list(range(n))
        random.shuffle(order)
        # Move current track to front if playing
        if self._cur >= 0 and self._cur in order:
            order.remove(self._cur)
            order.insert(0, self._cur)
        self._shuffle_order = order
        self._shuffle_idx = 0 if self._cur >= 0 else -1

    # ── Playlist management ───────────────────────────────────────────────────
    def _get_track_meta(self, path):
        """Extract title, artist, duration string from audio file."""
        title = os.path.splitext(os.path.basename(path))[0]
        artist = ""
        dur_str = ""
        try:
            mf = mutagen.File(path)
            if mf:
                if hasattr(mf, 'tags') and mf.tags:
                    for key in ["TPE1", "artist", "ARTIST", "Author", "\u00a9ART"]:
                        if key in mf.tags:
                            val = mf.tags[key]
                            artist = str(val[0]) if isinstance(val, list) else str(val)
                            break
                    for key in ["TIT2", "title", "TITLE", "\u00a9nam"]:
                        if key in mf.tags:
                            val = mf.tags[key]
                            t = str(val[0]) if isinstance(val, list) else str(val)
                            if t.strip():
                                title = t
                            break
                if hasattr(mf, 'info') and mf.info:
                    length = getattr(mf.info, 'length', 0)
                    if length > 0:
                        dur_str = fmt_duration(length)
        except Exception:
            pass
        return title, artist, dur_str

    def _addf(self):
        files = filedialog.askopenfilenames(
            filetypes=[("Audio", "*.mp3 *.wav *.flac *.ogg *.m4a"), ("All", "*.*")])
        for f in files:
            if f not in self._playlist_set:
                self._playlist.append(f); self._playlist_set.add(f)
                title, artist, dur_str = self._get_track_meta(f)
                self.plb.insert("", "end", iid=str(len(self._playlist) - 1),
                                values=(title, artist, dur_str))
        if self._shuffle:
            self._rebuild_shuffle_order()
        self._update_playlist_count()

    def _adddl(self):
        f = self.app.output_dir
        if os.path.exists(f):
            for fn in sorted(os.listdir(f)):
                if fn.lower().endswith((".mp3", ".wav", ".flac", ".ogg", ".m4a")):
                    path = os.path.join(f, fn)
                    if path not in self._playlist_set:
                        self._playlist.append(path); self._playlist_set.add(path)
                        title, artist, dur_str = self._get_track_meta(path)
                        self.plb.insert("", "end",
                                        iid=str(len(self._playlist) - 1),
                                        values=(title, artist, dur_str))
        if self._shuffle:
            self._rebuild_shuffle_order()
        self._update_playlist_count()

    def _clr(self):
        _audio.stop(); self._playlist = []; self._playlist_set = set()
        self._cur = -1; self._playing = False
        for item in self.plb.get_children():
            self.plb.delete(item)
        self.np_t.config(text="No track loaded"); self.np_a.config(text="")
        self.play_b.config(text="Play")
        self.wave_cv.delete("all")
        self._freq_times = None; self._freq_bands = None
        self._shuffle_order = []; self._shuffle_idx = -1
        self._update_playlist_count()
        self._update_upnext()

    def _psel(self, e=None):
        sel = self.plb.selection()
        if sel:
            idx = self._iid_to_idx(sel[0])
            if idx is not None:
                self._load(idx)

    def _iid_to_idx(self, iid):
        """Convert Treeview iid to playlist index."""
        children = self.plb.get_children()
        try:
            return list(children).index(iid)
        except ValueError:
            return None

    def _idx_to_iid(self, idx):
        """Convert playlist index to Treeview iid."""
        children = self.plb.get_children()
        if 0 <= idx < len(children):
            return children[idx]
        return None

    # ── Track loading ─────────────────────────────────────────────────────────
    def _load(self, idx):
        if idx < 0 or idx >= len(self._playlist):
            return
        self._cur = idx; path = self._playlist[idx]
        # Update Treeview selection
        self.plb.selection_set(self._idx_to_iid(idx) or "")
        iid = self._idx_to_iid(idx)
        if iid:
            self.plb.see(iid)
        name = os.path.splitext(os.path.basename(path))[0]
        self.np_t.config(text=name); self.np_a.config(text="")
        self.art.config(image=self._blank_art, text="\u266A")
        self._art_data = None
        try:
            mf = mutagen.File(path)
            if mf and mf.info:
                self._dur = mf.info.length
            else:
                self._dur = 0
            # Extract artist from any format
            artist = ""
            if hasattr(mf, 'tags') and mf.tags:
                for key in ["TPE1", "artist", "ARTIST", "Author", "\u00a9ART"]:
                    if key in mf.tags:
                        val = mf.tags[key]
                        artist = str(val[0]) if isinstance(val, list) else str(val)
                        break
            if artist:
                self.np_a.config(text=artist)
            self.dur_l.config(text=fmt_duration(self._dur))
            self.seek.config(to=self._dur)
            # Album art -- use universal extractor (MP3/FLAC/OGG/M4A/WAV)
            art_data, _ = extract_cover_art(path)
            if art_data:
                self._art_data = art_data
                with Image.open(BytesIO(art_data)) as raw:
                    img = raw.convert("RGB"); img.thumbnail((200, 200), Image.LANCZOS)
                ph = ImageTk.PhotoImage(img)
                self.art.config(image=ph, text="")
                self.art._img = ph
        except Exception:
            self._dur = 0
        # Generate waveform in background
        threading.Thread(target=self._gen_wave, args=(path,), daemon=True).start()
        # Compute frequency profile for real EQ
        self._freq_times = None; self._freq_bands = None; self._freq_loading = True
        threading.Thread(target=self._gen_freq_profile, args=(path,),
                         daemon=True).start()
        try:
            _audio.load(path); _audio.set_volume(self.vol.get() / 100)
            # Apply current speed setting
            rate = float(self.speed_var.get().rstrip("x"))
            _audio.set_speed(rate)
            _audio.play(); self._playing = True; self.play_b.config(text="Pause")
            self._crossfading = False
            show_toast(self.app, f"Now Playing: {name}", "info")
            self.app._update_discord_rpc(
                f"Playing: {name[:60]}",
                f"LimeWire Studio \u2014 {fmt_duration(self._dur)}")
            self.app._add_recent_file(path)
        except Exception as e:
            messagebox.showerror("LimeWire", str(e))
        self._highlight_current()
        self._update_upnext()
        # Update shuffle index
        if self._shuffle and self._cur in self._shuffle_order:
            self._shuffle_idx = self._shuffle_order.index(self._cur)
        # Update mini-player if open
        self._update_mini_player()

    def _show_fullsize_art(self, e=None):
        if not self._art_data:
            return
        dlg = tk.Toplevel(self); dlg.title("Album Art"); dlg.configure(bg=T.BG)
        try:
            img = Image.open(BytesIO(self._art_data)).convert("RGB")
            w, h = img.size; scale = min(600 / w, 600 / h, 1.0)
            img = img.resize((int(w * scale), int(h * scale)), Image.LANCZOS)
            ph = ImageTk.PhotoImage(img)
            lbl = tk.Label(dlg, image=ph, bg=T.BG); lbl._img = ph
            lbl.pack(padx=8, pady=8)
            dlg.geometry(f"{int(w * scale) + 16}x{int(h * scale) + 16}")
        except Exception:
            tk.Label(dlg, text="Cannot display image", font=T.F_BODY, bg=T.BG,
                     fg=T.RED).pack(padx=20, pady=20)
        dlg.bind("<Escape>", lambda e: dlg.destroy())

    # ── Waveform ──────────────────────────────────────────────────────────────
    def _gen_wave(self, path):
        bars = generate_waveform_data(path, PLAYER_WAVEFORM_W, PLAYER_WAVEFORM_H - 5)
        if bars:
            with self._lock:
                self._wave_bars = bars
            self.after(0, lambda: self._draw_wave(bars))

    def _gen_freq_profile(self, path):
        """Compute frequency profile in background thread."""
        times, bands = compute_frequency_profile(path)
        self._freq_times = times
        self._freq_bands = bands
        self._freq_loading = False

    def _draw_wave(self, bars, cursor_ratio=None):
        if not bars:
            return
        cv = self.wave_cv; cv.delete("all")
        w = cv.winfo_width() or PLAYER_WAVEFORM_W; h = PLAYER_WAVEFORM_H
        bw = max(1, w / len(bars)); gap = max(1, bw * 0.15)
        for i, amp in enumerate(bars):
            x = i * bw; bh = max(1, amp * h * 0.85)
            y1 = (h - bh) / 2; y2 = (h + bh) / 2
            if amp < 0.3:
                color = T.LIME
            elif amp < 0.6:
                color = _lerp_color(T.LIME, T.YELLOW, (amp - 0.3) / 0.3)
            elif amp < 0.85:
                color = _lerp_color(T.YELLOW, T.ORANGE, (amp - 0.6) / 0.25)
            else:
                color = T.RED
            cv.create_rectangle(x + gap / 2, y1, x + bw - gap / 2, y2,
                                fill=color, outline="")
        # Create overlay items (cursor + markers) with tags for fast updates
        self._wave_cursor = cv.create_line(0, 0, 0, h, fill=T.TEXT, width=2,
                                           tags="cursor")
        self._wave_marker_a = cv.create_line(0, 0, 0, h, fill=T.ORANGE, width=2,
                                             dash=(4, 2), tags="marker_a",
                                             state="hidden")
        self._wave_marker_b = cv.create_line(0, 0, 0, h, fill=T.ORANGE, width=2,
                                             dash=(4, 2), tags="marker_b",
                                             state="hidden")
        if cursor_ratio is not None:
            self._update_wave_cursor(cursor_ratio)

    def _update_wave_cursor(self, cursor_ratio):
        """Update only the cursor and markers -- no full redraw."""
        cv = self.wave_cv; w = cv.winfo_width() or 500; h = 50
        if hasattr(self, "_wave_cursor"):
            cx = int(cursor_ratio * w)
            cv.coords(self._wave_cursor, cx, 0, cx, h)
        if hasattr(self, "_wave_marker_a") and self._ab_a is not None and self._dur > 0:
            ax = int((self._ab_a / self._dur) * w)
            cv.coords(self._wave_marker_a, ax, 0, ax, h)
            cv.itemconfig(self._wave_marker_a, state="normal")
        if hasattr(self, "_wave_marker_b") and self._ab_b is not None and self._dur > 0:
            bx = int((self._ab_b / self._dur) * w)
            cv.coords(self._wave_marker_b, bx, 0, bx, h)
            cv.itemconfig(self._wave_marker_b, state="normal")

    def _wave_click(self, e):
        if self._dur > 0 and self._wave_bars:
            w = self.wave_cv.winfo_width() or 500
            ratio = max(0, min(1, e.x / w))
            pos = ratio * self._dur
            _audio.play(start=pos)
            self._playing = True; self.play_b.config(text="Pause")

    # ── Playback controls ─────────────────────────────────────────────────────
    def _toggle(self):
        if not self._playlist:
            self._addf(); return
        if self._cur < 0:
            if self._playlist:
                self._load(0)
            return
        if self._playing:
            _audio.pause(); self._playing = False; self.play_b.config(text="Play")
        else:
            _audio.play(); self._playing = True; self.play_b.config(text="Pause")
        self._update_mini_player()

    def _prev(self):
        if not self._playlist:
            return
        if self._repeat_mode == "one":
            self._load(self._cur); return
        if self._shuffle and self._shuffle_order:
            if self._shuffle_idx > 0:
                self._shuffle_idx -= 1
                self._load(self._shuffle_order[self._shuffle_idx])
            elif self._repeat_mode == "all":
                self._shuffle_idx = len(self._shuffle_order) - 1
                self._load(self._shuffle_order[self._shuffle_idx])
            return
        if self._cur > 0:
            self._load(self._cur - 1)
        elif self._repeat_mode == "all" and self._playlist:
            self._load(len(self._playlist) - 1)

    def _next(self):
        if not self._playlist:
            return
        if self._repeat_mode == "one":
            self._load(self._cur); return
        if self._shuffle and self._shuffle_order:
            if self._shuffle_idx < len(self._shuffle_order) - 1:
                self._shuffle_idx += 1
                self._load(self._shuffle_order[self._shuffle_idx])
            elif self._repeat_mode == "all":
                self._rebuild_shuffle_order()
                self._shuffle_idx = 0
                self._load(self._shuffle_order[0])
            else:
                self._playing = False; self.play_b.config(text="Play")
            return
        if self._cur < len(self._playlist) - 1:
            self._load(self._cur + 1)
        elif self._repeat_mode == "all":
            self._load(0)
        else:
            self._playing = False; self.play_b.config(text="Play")

    def _oseek(self, val):
        if self._seeking and self._playing:
            _audio.play(start=float(val))

    def _slider_press(self, e):
        self._seeking = True

    def _slider_release(self, e):
        self._seeking = False

    def _upd_pos(self):
        try:
            if self._playing and _audio.get_busy():
                pos = _audio.get_pos()
                # Position label (elapsed or remaining)
                if self._show_remaining and self._dur > 0:
                    remaining = self._dur - pos
                    self.pos_l.config(text=f"-{fmt_duration(max(0, remaining))}")
                else:
                    self.pos_l.config(text=fmt_duration(pos))
                if self._dur > 0 and not self._seeking:
                    self.seek_v.set(pos)
                # Update cursor position (fast, no full redraw)
                if self._wave_bars and self._dur > 0:
                    self._update_wave_cursor(pos / self._dur)
                self._update_eq(pos)
                # A-B loop: jump back to A if past B
                if (self._ab_a is not None and self._ab_b is not None
                        and pos >= self._ab_b):
                    _audio.play(start=self._ab_a)
                # Crossfade logic
                elif self._dur > 0:
                    cf_ms = self._crossfade_ms.get()
                    cf_sec = cf_ms / 1000
                    remaining = self._dur - pos
                    if cf_ms > 0 and remaining <= cf_sec and remaining > 0:
                        # Fade out current track
                        fade_ratio = remaining / cf_sec
                        _audio.set_volume((self.vol.get() / 100) * fade_ratio)
                        self._crossfading = True
                    elif cf_ms > 0 and remaining <= 0:
                        self._next()
                    elif pos >= self._dur - 1:
                        self._next()
                    elif self._crossfading and remaining > cf_sec:
                        # Fade-in complete, restore volume
                        _audio.set_volume(self.vol.get() / 100)
                        self._crossfading = False
            elif self._playing and not _audio.get_busy():
                self._next()
        except Exception:
            pass
        try:
            if self.winfo_exists():
                self.after(PLAYER_UPDATE_MS, self._upd_pos)
        except Exception:
            pass

    def _analyze_cur(self):
        if 0 <= self._cur < len(self._playlist):
            ap = self.app.pages.get("analyze")
            if ap:
                ap.file_var.set(self._playlist[self._cur])
                self.app._show_tab("analyze")

    def _stems_cur(self):
        if 0 <= self._cur < len(self._playlist):
            sp = self.app.pages.get("stems")
            if sp:
                sp.file_var.set(self._playlist[self._cur])
                self.app._show_tab("stems")

    def _apply_speed(self):
        rate = float(self.speed_var.get().rstrip("x"))
        _audio.set_speed(rate)

    # ── Elapsed / Remaining toggle ─────────────────────────────────────────────
    def _toggle_elapsed(self, e=None):
        self._show_remaining = not self._show_remaining

    # ── A-B loop ──────────────────────────────────────────────────────────────
    def _set_ab_a(self):
        if self._playing and _audio.get_busy():
            self._ab_a = _audio.get_pos()
            self._update_ab_label()

    def _set_ab_b(self):
        if self._playing and _audio.get_busy():
            self._ab_b = _audio.get_pos()
            self._update_ab_label()

    def _clear_ab(self):
        self._ab_a = None; self._ab_b = None
        self.ab_lbl.config(text="A-B: off", fg=T.TEXT_DIM)

    def _update_ab_label(self):
        a = fmt_duration(self._ab_a) if self._ab_a is not None else "?"
        b = fmt_duration(self._ab_b) if self._ab_b is not None else "?"
        self.ab_lbl.config(text=f"A-B: {a} \u2192 {b}", fg=T.ORANGE)

    # ── EQ spectrum ───────────────────────────────────────────────────────────
    def _init_eq_bars(self):
        """Defer EQ bar creation to first <Configure> when canvas has real width."""
        self._eq_initialized = False
        self._eq_peak_vals = [0.0] * EQ_BAR_COUNT
        self.eq_cv.bind("<Configure>", self._on_eq_configure, add="+")

    def _on_eq_configure(self, event=None):
        if self._eq_initialized:
            return
        self._eq_initialized = True
        w = self.eq_cv.winfo_width() or 400; h = 60
        n = EQ_BAR_COUNT; bw = max(2, w / n)
        gap = max(1, bw * 0.2)
        self._eq_bars = []; self._eq_peaks = []
        colors = [T.LIME] * 10 + [T.LIME_LT] * 8 + [T.YELLOW] * 8 + [T.RED] * 6
        for i in range(n):
            x = i * bw
            bar = self.eq_cv.create_rectangle(x + gap / 2, h, x + bw - gap / 2, h,
                                              fill=colors[min(i, len(colors) - 1)],
                                              outline="")
            peak = self.eq_cv.create_line(x + gap / 2, h, x + bw - gap / 2, h,
                                          fill=T.CANVAS_BG, width=1)
            self._eq_bars.append(bar); self._eq_peaks.append(peak)

    def _update_eq(self, pos=None):
        """Update EQ bars — use real frequency profile if available, else random."""
        if not self._playing or not self._eq_bars:
            return
        cv = self.eq_cv; h = 60; n = len(self._eq_bars)
        w = cv.winfo_width() or 400; bw = max(2, w / n)
        gap = max(1, bw * 0.2)

        # Try to use real frequency data
        use_real = (self._freq_times is not None and self._freq_bands is not None
                    and pos is not None and len(self._freq_times) > 0)
        if use_real:
            # Find the nearest frame for current playback position
            fi = bisect.bisect_left(self._freq_times, pos)
            fi = min(fi, len(self._freq_bands) - 1)
            band_data = self._freq_bands[fi]
        else:
            band_data = None

        for i in range(n):
            if band_data and i < len(band_data):
                amp = band_data[i]
            else:
                # Fallback: random animation
                if i < 6:
                    amp = random.uniform(0.4, 1.0)
                elif i < 16:
                    amp = random.uniform(0.2, 0.85)
                else:
                    amp = random.uniform(0.05, 0.6)
            bh = max(1, int(amp * h * 0.9)); x = i * bw; y1 = h - bh
            cv.coords(self._eq_bars[i], x + gap / 2, y1, x + bw - gap / 2, h)
            if amp > self._eq_peak_vals[i]:
                self._eq_peak_vals[i] = amp
            else:
                self._eq_peak_vals[i] = max(0, self._eq_peak_vals[i] - EQ_PEAK_DECAY)
            py = h - int(self._eq_peak_vals[i] * h * 0.9)
            cv.coords(self._eq_peaks[i], x + gap / 2, py, x + bw - gap / 2, py)
            cv.itemconfig(self._eq_peaks[i], fill=T.TEXT)

    # ── Playlist context menu & track removal ─────────────────────────────────
    def _playlist_context_menu(self, e):
        iid = self.plb.identify_row(e.y)
        if not iid:
            return
        self.plb.selection_set(iid)
        idx = self._iid_to_idx(iid)
        if idx is None:
            return
        menu = tk.Menu(self, tearoff=0, bg=T.SURFACE_2, fg=T.TEXT,
                       activebackground=T.LIME, activeforeground="#000",
                       font=T.F_BODY)
        menu.add_command(label="Play", command=lambda: self._load(idx))
        menu.add_separator()
        menu.add_command(label="Move Up", command=lambda: self._move_track(idx, -1))
        menu.add_command(label="Move Down", command=lambda: self._move_track(idx, 1))
        menu.add_separator()
        menu.add_command(label="Remove", command=lambda: self._remove_track(idx))
        menu.tk_popup(e.x_root, e.y_root)

    def _remove_selected(self):
        sel = self.plb.selection()
        if sel:
            idx = self._iid_to_idx(sel[0])
            if idx is not None:
                self._remove_track(idx)

    def _remove_track(self, idx):
        if idx < 0 or idx >= len(self._playlist):
            return
        path = self._playlist.pop(idx)
        self._playlist_set.discard(path)
        # Rebuild Treeview
        self._rebuild_treeview()
        # Adjust current index
        if len(self._playlist) == 0:
            self._cur = -1; _audio.stop(); self._playing = False
            self.np_t.config(text="No track loaded"); self.np_a.config(text="")
            self.play_b.config(text="Play")
        elif idx < self._cur:
            self._cur -= 1
        elif idx == self._cur:
            _audio.stop(); self._playing = False; self.play_b.config(text="Play")
            if self._cur < len(self._playlist):
                self._load(self._cur)
            elif len(self._playlist) > 0:
                self._cur = len(self._playlist) - 1
                self._load(self._cur)
            else:
                self._cur = -1
        self._highlight_current()
        if self._shuffle:
            self._rebuild_shuffle_order()
        self._update_playlist_count()
        self._update_upnext()

    def _move_track(self, idx, direction):
        """Move track at idx up (-1) or down (+1)."""
        new_idx = idx + direction
        if new_idx < 0 or new_idx >= len(self._playlist):
            return
        # Swap in playlist
        self._playlist[idx], self._playlist[new_idx] = (
            self._playlist[new_idx], self._playlist[idx])
        # Adjust current index
        if self._cur == idx:
            self._cur = new_idx
        elif self._cur == new_idx:
            self._cur = idx
        self._rebuild_treeview()
        self._highlight_current()
        # Select the moved item
        iid = self._idx_to_iid(new_idx)
        if iid:
            self.plb.selection_set(iid)
            self.plb.see(iid)

    # ── Drag-to-reorder ───────────────────────────────────────────────────────
    def _drag_start(self, e):
        iid = self.plb.identify_row(e.y)
        if iid:
            self._drag_src = self._iid_to_idx(iid)
        else:
            self._drag_src = None

    def _drag_motion(self, e):
        if self._drag_src is None:
            return
        iid = self.plb.identify_row(e.y)
        if iid:
            target = self._iid_to_idx(iid)
            if target is not None and target != self._drag_src:
                # Move track
                self._move_track(self._drag_src, target - self._drag_src)
                self._drag_src = target

    def _drag_end(self, e):
        self._drag_src = None

    # ── Current track highlight ───────────────────────────────────────────────
    def _highlight_current(self):
        """Visually highlight the currently playing track in the Treeview."""
        for i, iid in enumerate(self.plb.get_children()):
            if i == self._cur:
                self.plb.item(iid, tags=("current",))
            else:
                self.plb.item(iid, tags=())
        self.plb.tag_configure("current", background=T.LIME_DK, foreground="#FFFFFF")

    # ── Playlist count & Up Next ──────────────────────────────────────────────
    def _update_playlist_count(self):
        n = len(self._playlist)
        # Calculate total duration
        total_dur = 0
        for path in self._playlist:
            try:
                mf = mutagen.File(path)
                if mf and mf.info:
                    total_dur += getattr(mf.info, 'length', 0)
            except Exception:
                pass
        dur_str = fmt_duration(total_dur) if total_dur > 0 else ""
        title = f"Playlist ({n} track{'s' if n != 1 else ''}"
        if dur_str:
            title += f", {dur_str}"
        title += ")"
        self._plg.config(text=title)

    def _update_upnext(self):
        """Update the Up Next indicator based on shuffle/repeat mode."""
        if self._cur < 0 or not self._playlist:
            self._upnext_lbl.config(text=""); return
        nxt_idx = None
        if self._repeat_mode == "one":
            nxt_idx = self._cur
        elif self._shuffle and self._shuffle_order:
            if self._shuffle_idx < len(self._shuffle_order) - 1:
                nxt_idx = self._shuffle_order[self._shuffle_idx + 1]
            elif self._repeat_mode == "all":
                nxt_idx = self._shuffle_order[0] if self._shuffle_order else None
        else:
            if self._cur + 1 < len(self._playlist):
                nxt_idx = self._cur + 1
            elif self._repeat_mode == "all":
                nxt_idx = 0
        if nxt_idx is not None and 0 <= nxt_idx < len(self._playlist):
            nxt_name = os.path.splitext(
                os.path.basename(self._playlist[nxt_idx]))[0]
            self._upnext_lbl.config(text=f"Up Next: {nxt_name}")
        else:
            self._upnext_lbl.config(text="")

    # ── Rebuild Treeview ──────────────────────────────────────────────────────
    def _rebuild_treeview(self):
        """Clear and rebuild Treeview from playlist data."""
        for item in self.plb.get_children():
            self.plb.delete(item)
        for i, path in enumerate(self._playlist):
            title, artist, dur_str = self._get_track_meta(path)
            self.plb.insert("", "end", iid=str(i), values=(title, artist, dur_str))
        self._highlight_current()

    # ── Mini-Player ───────────────────────────────────────────────────────────
    def _toggle_mini(self):
        if self._mini_win and self._mini_win.winfo_exists():
            self._mini_win.destroy()
            self._mini_win = None
            return
        dlg = tk.Toplevel(self)
        dlg.title("LimeWire Mini")
        dlg.configure(bg=T.BG)
        dlg.geometry("340x110")
        dlg.attributes("-topmost", True)
        dlg.resizable(False, False)
        self._mini_win = dlg

        mf = tk.Frame(dlg, bg=T.BG); mf.pack(fill="both", expand=True, padx=8, pady=6)

        # Top row: art + title
        tr = tk.Frame(mf, bg=T.BG); tr.pack(fill="x")
        self._mini_art = tk.Label(tr, bg=T.SURFACE_2, width=6, height=3,
                                   text="\u266A", font=("Segoe UI", 14),
                                   fg=T.TEXT_DIM)
        self._mini_art.pack(side="left", padx=(0, 8))
        ti = tk.Frame(tr, bg=T.BG); ti.pack(side="left", fill="x", expand=True)
        self._mini_title = tk.Label(ti, text="No track", font=T.F_BOLD, bg=T.BG,
                                     fg=T.TEXT, anchor="w")
        self._mini_title.pack(fill="x")
        self._mini_artist = tk.Label(ti, text="", font=T.F_SMALL, bg=T.BG,
                                      fg=T.TEXT_DIM, anchor="w")
        self._mini_artist.pack(fill="x")

        # Progress bar (thin)
        self._mini_prog = ClassicProgress(mf, thin=True)
        self._mini_prog.pack(fill="x", pady=(4, 2))

        # Controls row
        br = tk.Frame(mf, bg=T.BG); br.pack(fill="x")
        ClassicBtn(br, "|<", self._prev, width=3).pack(side="left", padx=1)
        self._mini_play_btn = ClassicBtn(br, "Pause" if self._playing else "Play",
                                          self._toggle, width=5)
        self._mini_play_btn.pack(side="left", padx=1)
        ClassicBtn(br, ">|", self._next, width=3).pack(side="left", padx=1)
        # Volume
        tk.Label(br, text="  Vol:", font=T.F_SMALL, bg=T.BG, fg=T.TEXT_DIM).pack(
            side="left", padx=(8, 2))
        ttk.Scale(br, from_=0, to=100, orient="horizontal", variable=self.vol,
                  command=lambda v: _audio.set_volume(float(v) / 100),
                  length=80).pack(side="left")

        self._update_mini_player()
        self._mini_update_loop()
        dlg.protocol("WM_DELETE_WINDOW", self._toggle_mini)

    def _update_mini_player(self):
        """Sync mini-player display with current state."""
        if not self._mini_win or not self._mini_win.winfo_exists():
            return
        if 0 <= self._cur < len(self._playlist):
            name = os.path.splitext(os.path.basename(self._playlist[self._cur]))[0]
            self._mini_title.config(text=name[:40])
            artist = self.np_a.cget("text")
            self._mini_artist.config(text=artist[:40] if artist else "")
            # Mini art
            if self._art_data:
                try:
                    with Image.open(BytesIO(self._art_data)) as raw:
                        img = raw.convert("RGB")
                        img.thumbnail((48, 48), Image.LANCZOS)
                    ph = ImageTk.PhotoImage(img)
                    self._mini_art.config(image=ph, text="")
                    self._mini_art._img = ph
                except Exception:
                    pass
        self._mini_play_btn.config(text="Pause" if self._playing else "Play")

    def _mini_update_loop(self):
        """Update mini-player progress bar."""
        if not self._mini_win or not self._mini_win.winfo_exists():
            return
        if self._playing and self._dur > 0:
            pos = _audio.get_pos()
            pct = min(100, (pos / self._dur) * 100)
            self._mini_prog["value"] = pct
        self._mini_play_btn.config(text="Pause" if self._playing else "Play")
        try:
            if self._mini_win.winfo_exists():
                self._mini_win.after(500, self._mini_update_loop)
        except Exception:
            pass

    # ── M3U ───────────────────────────────────────────────────────────────────
    def _save_m3u(self):
        if not self._playlist:
            return
        path = filedialog.asksaveasfilename(defaultextension=".m3u",
                                            filetypes=[("M3U Playlist", "*.m3u")])
        if path:
            with open(path, "w", encoding="utf-8") as f:
                f.write("#EXTM3U\n")
                for p_ in self._playlist:
                    f.write(p_ + "\n")
            self.app.toast(f"Saved {len(self._playlist)} tracks to M3U")

    def _load_m3u(self):
        path = filedialog.askopenfilename(
            filetypes=[("M3U Playlist", "*.m3u"), ("All", "*.*")])
        if not path:
            return
        _AUDIO_EXTS = frozenset({".mp3", ".wav", ".flac", ".ogg", ".m4a",
                                 ".aac", ".opus", ".wma", ".aiff"})
        try:
            with open(path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if (line and not line.startswith("#")
                            and os.path.splitext(line)[1].lower() in _AUDIO_EXTS
                            and os.path.exists(line)):
                        if line not in self._playlist_set:
                            self._playlist.append(line)
                            self._playlist_set.add(line)
                            title, artist, dur_str = self._get_track_meta(line)
                            self.plb.insert("", "end",
                                            iid=str(len(self._playlist) - 1),
                                            values=(title, artist, dur_str))
            self.app.toast(f"Loaded playlist: {len(self._playlist)} tracks")
        except Exception as e:
            self.app.toast(f"Failed to load M3U: {str(e)[:50]}", "error")
        if self._shuffle:
            self._rebuild_shuffle_order()
        self._update_playlist_count()

    # ── Collaborative JSON playlists ──────────────────────────────────────────
    def _share_playlist_json(self):
        """Export collaborative playlist as shareable JSON with metadata."""
        if not self._playlist:
            return
        cache = load_json(ANALYSIS_CACHE_FILE, {})
        tracks = []
        for fp in self._playlist:
            entry = {"path": fp, "filename": os.path.basename(fp)}
            # Try to add metadata
            try:
                mf = mutagen.File(fp)
                if mf:
                    if hasattr(mf, "tags") and mf.tags:
                        for k in mf.tags:
                            if "TIT2" in str(k):
                                entry["title"] = str(mf.tags[k])
                            if "TPE1" in str(k):
                                entry["artist"] = str(mf.tags[k])
                    if hasattr(mf, "info"):
                        entry["duration"] = round(getattr(mf.info, "length", 0), 1)
            except Exception:
                pass
            # Add analysis data if available
            mtime = os.path.getmtime(fp) if os.path.exists(fp) else 0
            cache_key = f"{fp}|{mtime}"
            if cache_key in cache:
                cd = cache[cache_key]
                entry["bpm"] = cd.get("bpm")
                entry["key"] = cd.get("key")
                entry["camelot"] = cd.get("camelot")
            tracks.append(entry)
        playlist_data = {
            "version": "1.0", "app": "LimeWire Studio",
            "created": datetime.datetime.now().isoformat(),
            "track_count": len(tracks), "tracks": tracks,
        }
        path = filedialog.asksaveasfilename(
            defaultextension=".json",
            filetypes=[("JSON Playlist", "*.json")],
            initialfile="limewire_playlist.json")
        if path:
            save_json(path, playlist_data)
            self.app.toast(f"Shared playlist: {len(tracks)} tracks", "success")

    def _import_playlist_json(self):
        """Import collaborative playlist from shared JSON."""
        path = filedialog.askopenfilename(
            filetypes=[("JSON Playlist", "*.json"), ("All", "*.*")])
        if not path:
            return
        try:
            data = load_json(path, {})
            tracks = data.get("tracks", [])
            added = 0
            for t in tracks:
                fp = t.get("path", "")
                _AUDIO_EXTS = frozenset({".mp3", ".wav", ".flac", ".ogg", ".m4a",
                                         ".aac", ".opus", ".wma", ".aiff"})
                if (fp and os.path.splitext(fp)[1].lower() in _AUDIO_EXTS
                        and os.path.exists(fp) and fp not in self._playlist_set):
                    self._playlist.append(fp); self._playlist_set.add(fp)
                    title = t.get("title") or os.path.splitext(
                        os.path.basename(fp))[0]
                    artist = t.get("artist", "")
                    dur = t.get("duration", 0)
                    dur_str = fmt_duration(dur) if dur else ""
                    bpm = t.get("bpm", ""); key = t.get("key", "")
                    if bpm:
                        title += f" [{bpm}bpm]"
                    if key:
                        title += f" ({key})"
                    self.plb.insert("", "end",
                                    iid=str(len(self._playlist) - 1),
                                    values=(title, artist, dur_str))
                    added += 1
            src_info = (f" from {data.get('app', 'unknown')}"
                        if data.get("app") else "")
            self.app.toast(f"Imported {added} tracks{src_info}", "success")
        except Exception as e:
            self.app.toast(f"Import error: {str(e)[:50]}", "error")
        if self._shuffle:
            self._rebuild_shuffle_order()
        self._update_playlist_count()
