"""DJPage — Dual-deck DJ interface with crossfader, sync, and beat matching."""
import os, time, json, threading
import tkinter as tk
from tkinter import ttk, filedialog

import mutagen

from limewire.core.theme import T
from limewire.core.constants import (
    DJ_WAVEFORM_H, DJ_CROSSFADE_DEFAULT, DJ_SPEED_RANGE,
    PLAYER_UPDATE_MS, SP_SM, SP_LG, AUDIO_FMTS,
)
from limewire.core.audio_backend import _dj_deck_a, _dj_deck_b
from limewire.ui.scroll_frame import ScrollFrame
from limewire.ui.widgets import (
    ClassicBtn, LimeBtn, OrangeBtn, GroupBox, ClassicProgress,
    PageSettingsPanel, GearButton,
)
from limewire.ui.toast import show_toast
from limewire.services.audio_processing import generate_waveform_data
from limewire.services.analysis import analyze_bpm_key
from limewire.utils.helpers import fmt_duration


class _DeckState:
    """State container for one DJ deck."""
    __slots__ = ("path", "name", "bpm", "key", "duration",
                 "playing", "speed_pct", "volume", "wave_bars", "cue_point")

    def __init__(self):
        self.path = ""
        self.name = ""
        self.bpm = 0.0
        self.key = ""
        self.duration = 0.0
        self.playing = False
        self.speed_pct = 0       # -8 to +8 percent
        self.volume = 80
        self.wave_bars = []
        self.cue_point = 0.0


class DJPage(ScrollFrame):
    def __init__(self, parent, app):
        super().__init__(parent)
        self.app = app
        self._state_a = _DeckState()
        self._state_b = _DeckState()
        self._crossfade_var = tk.IntVar(value=DJ_CROSSFADE_DEFAULT)
        self._update_after = None
        self._session_log = []
        self._recording = False
        self._rec_start = 0
        self._build(self.inner)

    # ── UI ────────────────────────────────────────────────────────────────────

    def _build(self, p):
        main = tk.Frame(p, bg=T.BG)
        main.pack(fill="both", expand=True, padx=10, pady=(10, 6))

        # Left deck
        left = tk.Frame(main, bg=T.BG)
        left.pack(side="left", fill="both", expand=True)
        self._a_widgets = self._build_deck(left, "A", self._state_a, _dj_deck_a)

        # Mixer center
        mixer = self._build_mixer(main)
        mixer.pack(side="left", fill="y", padx=8)

        # Right deck
        right = tk.Frame(main, bg=T.BG)
        right.pack(side="left", fill="both", expand=True)
        self._b_widgets = self._build_deck(right, "B", self._state_b, _dj_deck_b)

        # Session
        sg = GroupBox(p, "Session")
        sg.pack(fill="x", padx=10, pady=(0, 10))
        sr = tk.Frame(sg, bg=T.BG)
        sr.pack(fill="x")
        self._settings_panel = PageSettingsPanel(p, "dj", self.app, [
            ("speed_range", "Speed Range (%)", "choice", "8", {"choices": ["4", "8", "12", "16"]}),
            ("crossfader_curve", "Crossfader Curve", "choice", "linear", {"choices": ["linear", "fast_cut", "slow_cut"]}),
        ])
        self._gear = GearButton(sr, self._settings_panel)
        self._gear.pack(side="right")
        self._rec_btn = OrangeBtn(sr, "Record Mix", self._toggle_recording)
        self._rec_btn.pack(side="left", padx=(0, 6))
        ClassicBtn(sr, "Export Session Log", self._export_session).pack(side="left")
        self._rec_lbl = tk.Label(sr, text="", font=T.F_SMALL, bg=T.BG, fg=T.TEXT_DIM)
        self._rec_lbl.pack(side="left", padx=(10, 0))

    def _build_deck(self, parent, letter, state, audio):
        g = GroupBox(parent, f"Deck {letter}")
        g.pack(fill="both", expand=True)

        widgets = {}

        # File row
        fr = tk.Frame(g, bg=T.BG)
        fr.pack(fill="x")
        ClassicBtn(fr, "Load", lambda l=letter: self._load_deck(l)).pack(side="left", padx=(0, 6))
        widgets["name_lbl"] = tk.Label(fr, text="No track", font=T.F_SMALL,
                                       bg=T.BG, fg=T.TEXT_DIM, anchor="w")
        widgets["name_lbl"].pack(side="left", fill="x", expand=True)

        # Waveform
        widgets["wave_cv"] = tk.Canvas(g, bg=T.CANVAS_BG, height=DJ_WAVEFORM_H,
                                       highlightthickness=0)
        widgets["wave_cv"].pack(fill="x", padx=4, pady=4)
        widgets["wave_cv"].bind("<ButtonPress-1>",
                                lambda e, l=letter: self._seek_deck(l, e))

        # Info row
        ir = tk.Frame(g, bg=T.BG)
        ir.pack(fill="x")
        widgets["bpm_lbl"] = tk.Label(ir, text="BPM: --", font=T.F_BOLD,
                                      bg=T.BG, fg=T.LIME)
        widgets["bpm_lbl"].pack(side="left", padx=(0, 12))
        widgets["key_lbl"] = tk.Label(ir, text="Key: --", font=T.F_BOLD,
                                      bg=T.BG, fg=T.TEXT)
        widgets["key_lbl"].pack(side="left", padx=(0, 12))
        widgets["pos_lbl"] = tk.Label(ir, text="0:00 / 0:00", font=T.F_SMALL,
                                      bg=T.BG, fg=T.TEXT_DIM)
        widgets["pos_lbl"].pack(side="right")

        # Transport
        tr = tk.Frame(g, bg=T.BG)
        tr.pack(fill="x", pady=(4, 0))
        widgets["play_btn"] = LimeBtn(tr, "Play", lambda l=letter: self._play_deck(l))
        widgets["play_btn"].pack(side="left", padx=(0, 4))
        ClassicBtn(tr, "Cue", lambda l=letter: self._cue_deck(l)).pack(side="left", padx=(0, 4))
        ClassicBtn(tr, "Stop", lambda l=letter: self._stop_deck(l)).pack(side="left")

        # Volume
        vr = tk.Frame(g, bg=T.BG)
        vr.pack(fill="x", pady=(4, 0))
        tk.Label(vr, text="Vol:", font=T.F_SMALL, bg=T.BG, fg=T.TEXT).pack(side="left")
        widgets["vol_var"] = tk.IntVar(value=state.volume)
        vol_sc = ttk.Scale(vr, from_=0, to=100, variable=widgets["vol_var"],
                           orient="horizontal",
                           command=lambda v, l=letter: self._on_vol(l, v))
        vol_sc.pack(side="left", fill="x", expand=True, padx=4)
        widgets["vol_lbl"] = tk.Label(vr, text="80%", font=T.F_SMALL,
                                      bg=T.BG, fg=T.TEXT_DIM, width=4)
        widgets["vol_lbl"].pack(side="left")

        # Speed
        spr = tk.Frame(g, bg=T.BG)
        spr.pack(fill="x", pady=(4, 4))
        tk.Label(spr, text="Speed:", font=T.F_SMALL, bg=T.BG, fg=T.TEXT).pack(side="left")
        widgets["speed_var"] = tk.IntVar(value=0)
        sp_sc = ttk.Scale(spr, from_=-8, to=8, variable=widgets["speed_var"],
                          orient="horizontal",
                          command=lambda v, l=letter: self._on_speed(l, v))
        sp_sc.pack(side="left", fill="x", expand=True, padx=4)
        widgets["speed_lbl"] = tk.Label(spr, text="0%", font=T.F_SMALL,
                                        bg=T.BG, fg=T.TEXT_DIM, width=5)
        widgets["speed_lbl"].pack(side="left")

        return widgets

    def _build_mixer(self, parent):
        f = tk.Frame(parent, bg=T.BG, width=80)

        tk.Label(f, text="A", font=T.F_BOLD, bg=T.BG, fg=T.LIME).pack(pady=(10, 0))

        # Crossfader (vertical)
        cf = ttk.Scale(f, from_=0, to=100, variable=self._crossfade_var,
                       orient="vertical", length=200,
                       command=self._on_crossfade)
        cf.pack(pady=8)

        tk.Label(f, text="B", font=T.F_BOLD, bg=T.BG, fg=T.ORANGE).pack()

        # Sync button
        OrangeBtn(f, "SYNC", self._sync_bpm, width=6).pack(pady=(12, 4))
        self._sync_lbl = tk.Label(f, text="", font=T.F_SMALL, bg=T.BG,
                                  fg=T.TEXT_DIM, wraplength=70)
        self._sync_lbl.pack()

        return f

    # ── Deck operations ───────────────────────────────────────────────────────

    def _get_deck(self, letter):
        if letter == "A":
            return self._state_a, _dj_deck_a, self._a_widgets
        return self._state_b, _dj_deck_b, self._b_widgets

    def _load_deck(self, letter):
        exts = " ".join(f"*.{e}" for e in AUDIO_FMTS)
        path = filedialog.askopenfilename(
            filetypes=[("Audio", exts), ("All", "*.*")])
        if not path:
            return
        state, audio, widgets = self._get_deck(letter)
        state.path = path
        state.name = os.path.splitext(os.path.basename(path))[0]
        widgets["name_lbl"].config(text=state.name, fg=T.TEXT)

        # Load audio
        try:
            audio.load(path)
        except Exception as e:
            show_toast(self.app, f"Load error: {e}", "error")
            return

        # Get duration
        try:
            mf = mutagen.File(path)
            if mf and hasattr(mf.info, "length"):
                state.duration = mf.info.length
        except Exception:
            pass

        # Waveform in background
        def _wave():
            bars = generate_waveform_data(path, width=350, height=DJ_WAVEFORM_H)
            self.after(0, lambda: self._set_wave(letter, bars))
        threading.Thread(target=_wave, daemon=True).start()

        # BPM/key in background
        def _analysis():
            result = analyze_bpm_key(path)
            self.after(0, lambda: self._set_analysis(letter, result))
        threading.Thread(target=_analysis, daemon=True).start()

        self._log_event(f"Load Deck {letter}: {state.name}")

    def _set_wave(self, letter, bars):
        state, _, widgets = self._get_deck(letter)
        state.wave_bars = bars
        self._draw_wave(letter)

    def _set_analysis(self, letter, result):
        state, _, widgets = self._get_deck(letter)
        state.bpm = result.get("bpm", 0) or 0
        state.key = result.get("key", "") or ""
        widgets["bpm_lbl"].config(text=f"BPM: {state.bpm:.0f}" if state.bpm else "BPM: --")
        widgets["key_lbl"].config(text=f"Key: {state.key}" if state.key else "Key: --")

    def _draw_wave(self, letter, pos=0):
        state, _, widgets = self._get_deck(letter)
        cv = widgets["wave_cv"]
        cv.delete("all")
        cv.update_idletasks()
        w = cv.winfo_width() or 350
        h = DJ_WAVEFORM_H
        bars = state.wave_bars
        if not bars:
            return
        mid = h // 2
        color = T.LIME if letter == "A" else T.ORANGE
        for i, amp in enumerate(bars):
            x = int(i * w / len(bars))
            bh = max(1, int(amp * h * 0.85))
            cv.create_line(x, mid - bh // 2, x, mid + bh // 2, fill=color)
        # Cursor
        if state.duration > 0:
            cx = int(pos / state.duration * w)
            cv.create_line(cx, 0, cx, h, fill="#FFFFFF", width=2)

    def _seek_deck(self, letter, event):
        state, audio, widgets = self._get_deck(letter)
        if not state.path or state.duration <= 0:
            return
        cv = widgets["wave_cv"]
        w = cv.winfo_width() or 350
        ratio = event.x / max(1, w)
        seek_pos = ratio * state.duration
        audio.play(start=seek_pos)
        state.playing = True
        self._log_event(f"Seek Deck {letter}: {seek_pos:.1f}s")
        self._ensure_update()

    def _play_deck(self, letter):
        state, audio, widgets = self._get_deck(letter)
        if not state.path:
            show_toast(self.app, f"Load a track into Deck {letter}", "warning")
            return
        if state.playing:
            audio.pause()
            state.playing = False
            widgets["play_btn"].config(text="Play")
            self._log_event(f"Pause Deck {letter}")
        else:
            audio.play()
            state.playing = True
            widgets["play_btn"].config(text="Pause")
            self._log_event(f"Play Deck {letter}")
            self._ensure_update()

    def _stop_deck(self, letter):
        state, audio, widgets = self._get_deck(letter)
        audio.stop()
        state.playing = False
        widgets["play_btn"].config(text="Play")
        widgets["pos_lbl"].config(text="0:00 / 0:00")
        self._draw_wave(letter, 0)
        self._log_event(f"Stop Deck {letter}")

    def _cue_deck(self, letter):
        state, audio, _ = self._get_deck(letter)
        if not state.path:
            return
        if state.playing:
            # Set cue point at current position
            state.cue_point = audio.get_pos()
            self._log_event(f"Set Cue Deck {letter}: {state.cue_point:.1f}s")
        else:
            # Jump to cue point
            audio.play(start=state.cue_point)
            state.playing = True
            self._log_event(f"Jump Cue Deck {letter}")
            self._ensure_update()

    # ── Volume / Speed / Crossfade ────────────────────────────────────────────

    def _on_vol(self, letter, val):
        state, audio, widgets = self._get_deck(letter)
        v = int(float(val))
        state.volume = v
        widgets["vol_lbl"].config(text=f"{v}%")
        self._apply_volumes()

    def _on_speed(self, letter, val):
        state, audio, widgets = self._get_deck(letter)
        pct = int(float(val))
        state.speed_pct = pct
        rate = 1.0 + pct / 100
        audio.set_speed(rate)
        sign = "+" if pct >= 0 else ""
        widgets["speed_lbl"].config(text=f"{sign}{pct}%")

    def _on_crossfade(self, val=None):
        self._apply_volumes()

    def _apply_volumes(self):
        cf = self._crossfade_var.get() / 100  # 0.0 to 1.0
        vol_a = (self._state_a.volume / 100) * min(1.0, 2 * (1 - cf))
        vol_b = (self._state_b.volume / 100) * min(1.0, 2 * cf)
        _dj_deck_a.set_volume(vol_a)
        _dj_deck_b.set_volume(vol_b)

    def _sync_bpm(self):
        a, b = self._state_a, self._state_b
        if not a.bpm or not b.bpm:
            show_toast(self.app, "Load tracks with BPM data on both decks", "warning")
            return
        ratio = a.bpm / b.bpm
        pct = int((ratio - 1.0) * 100)
        pct = max(-8, min(8, pct))
        self._state_b.speed_pct = pct
        _dj_deck_b.set_speed(ratio)
        self._b_widgets["speed_var"].set(pct)
        sign = "+" if pct >= 0 else ""
        self._b_widgets["speed_lbl"].config(text=f"{sign}{pct}%")
        self._sync_lbl.config(text=f"{a.bpm:.0f} -> {b.bpm:.0f}")
        self._log_event(f"Sync BPM: {a.bpm:.0f} -> {b.bpm:.0f} ({sign}{pct}%)")
        show_toast(self.app, f"Synced Deck B to {a.bpm:.0f} BPM", "success")

    # ── Update loop ───────────────────────────────────────────────────────────

    def _ensure_update(self):
        if self._update_after is None:
            self._update_loop()

    def _update_loop(self):
        active = False
        for letter in ("A", "B"):
            state, audio, widgets = self._get_deck(letter)
            if state.playing:
                active = True
                pos = audio.get_pos()
                dur_str = fmt_duration(state.duration) if state.duration else "0:00"
                pos_str = fmt_duration(pos)
                widgets["pos_lbl"].config(text=f"{pos_str} / {dur_str}")
                self._draw_wave(letter, pos)

                # Auto-stop at end
                if state.duration > 0 and pos >= state.duration - 0.5:
                    self._stop_deck(letter)

        if active:
            self._update_after = self.after(PLAYER_UPDATE_MS, self._update_loop)
        else:
            self._update_after = None

    # ── Session recording ─────────────────────────────────────────────────────

    def _log_event(self, action):
        if not self._recording:
            return
        elapsed = time.time() - self._rec_start
        self._session_log.append({
            "time": round(elapsed, 1),
            "action": action,
            "crossfade": self._crossfade_var.get(),
        })

    def _toggle_recording(self):
        if self._recording:
            self._recording = False
            self._rec_btn.config(text="Record Mix")
            n = len(self._session_log)
            self._rec_lbl.config(text=f"Stopped ({n} events)", fg=T.TEXT_DIM)
        else:
            self._recording = True
            self._rec_start = time.time()
            self._session_log = []
            self._rec_btn.config(text="Stop Rec")
            self._rec_lbl.config(text="Recording...", fg=T.RED)

    def _export_session(self):
        if not self._session_log:
            show_toast(self.app, "No session recorded", "warning")
            return
        path = filedialog.asksaveasfilename(
            defaultextension=".json", filetypes=[("JSON", "*.json")])
        if not path:
            return
        data = {
            "deck_a": self._state_a.name,
            "deck_b": self._state_b.name,
            "events": self._session_log,
        }
        try:
            with open(path, "w") as f:
                json.dump(data, f, indent=2)
            show_toast(self.app, "Session exported", "success")
        except Exception as e:
            show_toast(self.app, f"Error: {e}", "error")

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def refresh(self):
        self._apply_volumes()
