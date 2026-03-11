"""PlayerPage — Audio player with waveform visualization, A-B looping, and EQ spectrum."""
import os, threading, datetime
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from io import BytesIO

import mutagen
from PIL import Image, ImageTk

from limewire.core.theme import T, _lerp_color
from limewire.core.constants import (
    PLAYER_WAVEFORM_W, PLAYER_WAVEFORM_H, PLAYER_UPDATE_MS,
    EQ_BAR_COUNT, EQ_PEAK_DECAY, SP_LG, SP_XS,
    ANALYSIS_CACHE_FILE,
)
from limewire.core.config import load_json, save_json
from limewire.core.audio_backend import _audio
from limewire.ui.scroll_frame import ScrollFrame
from limewire.ui.widgets import (ClassicBtn, LimeBtn, OrangeBtn, GroupBox,
                                  ClassicEntry, ClassicListbox, ClassicProgress)
from limewire.ui.toast import show_toast
from limewire.utils.helpers import fmt_duration
from limewire.services.cover_art import extract_cover_art
from limewire.services.audio_processing import generate_waveform_data


class PlayerPage(ScrollFrame):
    """Audio player with waveform visualization, A-B looping, and EQ spectrum."""
    def __init__(self, parent, app):
        super().__init__(parent); self.app = app
        self._playlist = []; self._playlist_set = set()  # O(1) membership checks
        self._cur = -1; self._playing = False; self._dur = 0
        self._seeking = False; self._wave_bars = []; self._ab_a = None; self._ab_b = None
        self._lock = threading.Lock()  # protects _wave_bars from background thread
        self._build(self.inner)

    def _build(self, p):
        ng = GroupBox(p, "Now Playing"); ng.pack(fill="x", padx=10, pady=(10, 6))
        nr = tk.Frame(ng, bg=T.BG); nr.pack(fill="x")
        self.art = tk.Label(nr, bg=T.CARD_BG, width=200, height=200, text="\u266A",
                            font=("Segoe UI", 32), fg=T.TEXT_DIM,
                            relief="groove", bd=1, cursor="hand2")
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
                              width=6)
        self.pos_l.pack(side="left")
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

        # Quick analyze/stems buttons
        qa = tk.Frame(ng, bg=T.BG); qa.pack(pady=(4, 0))
        OrangeBtn(qa, "Analyze", self._analyze_cur).pack(side="left", padx=(0, 6))
        OrangeBtn(qa, "Split Stems", self._stems_cur).pack(side="left", padx=(0, 6))

        # Speed + A-B loop
        spr = tk.Frame(ng, bg=T.BG); spr.pack(pady=(4, 0))
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

        vr = tk.Frame(ng, bg=T.BG); vr.pack(pady=(4, 0))
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

        # Up Next indicator
        self._upnext_lbl = tk.Label(ng, text="", font=T.F_SMALL, bg=T.BG,
                                    fg=T.TEXT_DIM, anchor="w")
        self._upnext_lbl.pack(fill="x", pady=(SP_XS, 0))

        # EQ Spectrum Visualizer
        eqg = GroupBox(p, "EQ Spectrum"); eqg.pack(fill="x", padx=10, pady=(0, 6))
        self.eq_cv = tk.Canvas(eqg, bg=T.CANVAS_BG, height=60, relief="flat", bd=0,
                               highlightthickness=1, highlightbackground=T.CARD_BORDER)
        self.eq_cv.pack(fill="x")
        self._eq_bars = []
        self._eq_peaks = []
        self._init_eq_bars()

        plg = GroupBox(p, "Playlist")
        plg.pack(fill="both", padx=10, pady=(0, 10), expand=True)
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
        self.plf, self.plb = ClassicListbox(plg, height=7)
        self.plf.pack(fill="both", expand=True)
        self.plb.bind("<Double-Button-1>", self._psel)
        self._upd_pos()

    # ── Playlist management ───────────────────────────────────────────────────
    def _addf(self):
        files = filedialog.askopenfilenames(
            filetypes=[("Audio", "*.mp3 *.wav *.flac *.ogg *.m4a"), ("All", "*.*")])
        for f in files:
            if f not in self._playlist_set:
                self._playlist.append(f); self._playlist_set.add(f)
                self.plb.insert("end", os.path.basename(f))

    def _adddl(self):
        f = self.app.output_dir
        if os.path.exists(f):
            for fn in sorted(os.listdir(f)):
                if fn.lower().endswith((".mp3", ".wav", ".flac", ".ogg", ".m4a")):
                    path = os.path.join(f, fn)
                    if path not in self._playlist_set:
                        self._playlist.append(path); self._playlist_set.add(path)
                        self.plb.insert("end", fn)

    def _clr(self):
        _audio.stop(); self._playlist = []; self._playlist_set = set()
        self._cur = -1; self._playing = False
        self.plb.delete(0, "end")
        self.np_t.config(text="No track loaded"); self.np_a.config(text="")
        self.play_b.config(text="Play")
        self.wave_cv.delete("all")

    def _psel(self, e=None):
        sel = self.plb.curselection()
        if sel:
            self._load(sel[0])

    # ── Track loading ─────────────────────────────────────────────────────────
    def _load(self, idx):
        if idx < 0 or idx >= len(self._playlist):
            return
        self._cur = idx; path = self._playlist[idx]
        self.plb.selection_clear(0, "end"); self.plb.selection_set(idx)
        self.plb.see(idx)
        name = os.path.splitext(os.path.basename(path))[0]
        self.np_t.config(text=name); self.np_a.config(text="")
        self.art.config(image="", text="\u266A", width=200, height=200)
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
                self.art.config(image=ph, text="", width=200, height=200)
                self.art._img = ph
        except Exception:
            self._dur = 0
        # Generate waveform in background
        threading.Thread(target=self._gen_wave, args=(path,), daemon=True).start()
        try:
            _audio.load(path); _audio.set_volume(self.vol.get() / 100)
            _audio.play(); self._playing = True; self.play_b.config(text="Pause")
            show_toast(self.app, f"Now Playing: {name}", "info")
            self.app._update_discord_rpc(
                f"Playing: {name[:60]}",
                f"LimeWire Studio \u2014 {fmt_duration(self._dur)}")
            self.app._add_recent_file(path)
        except Exception as e:
            messagebox.showerror("LimeWire", str(e))
        # Up Next indicator
        nxt_idx = idx + 1
        if nxt_idx < len(self._playlist):
            nxt_name = os.path.splitext(
                os.path.basename(self._playlist[nxt_idx]))[0]
            self._upnext_lbl.config(text=f"Up Next: {nxt_name}")
        else:
            self._upnext_lbl.config(text="")

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

    def _prev(self):
        if self._cur > 0:
            self._load(self._cur - 1)

    def _next(self):
        if self._cur < len(self._playlist) - 1:
            self._load(self._cur + 1)

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
                pos = _audio.get_pos(); self.pos_l.config(text=fmt_duration(pos))
                if self._dur > 0 and not self._seeking:
                    self.seek_v.set(pos)
                # Update cursor position (fast, no full redraw)
                if self._wave_bars and self._dur > 0:
                    self._update_wave_cursor(pos / self._dur)
                self._update_eq()
                # A-B loop: jump back to A if past B
                if (self._ab_a is not None and self._ab_b is not None
                        and pos >= self._ab_b):
                    _audio.play(start=self._ab_a)
                elif self._dur > 0 and pos >= self._dur - 1:
                    self._next()
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
        # Note: pyglet Player does not support playback speed changes.
        # This is a placeholder for future backend support.
        pass

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

    def _update_eq(self):
        """Update EQ bars with random-seeded decay animation when playing."""
        if not self._playing or not self._eq_bars:
            return
        import random
        cv = self.eq_cv; h = 60; n = len(self._eq_bars)
        w = cv.winfo_width() or 400; bw = max(2, w / n)
        gap = max(1, bw * 0.2)
        for i in range(n):
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
                            self.plb.insert("end", os.path.basename(line))
            self.app.toast(f"Loaded playlist: {len(self._playlist)} tracks")
        except Exception as e:
            self.app.toast(f"Failed to load M3U: {str(e)[:50]}", "error")

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
                    name = t.get("title") or os.path.basename(fp)
                    bpm = t.get("bpm", ""); key = t.get("key", "")
                    label = f"{name}"
                    if bpm:
                        label += f" [{bpm}bpm]"
                    if key:
                        label += f" ({key})"
                    self.plb.insert("end", label)
                    added += 1
            src_info = (f" from {data.get('app', 'unknown')}"
                        if data.get("app") else "")
            self.app.toast(f"Imported {added} tracks{src_info}", "success")
        except Exception as e:
            self.app.toast(f"Import error: {str(e)[:50]}", "error")
