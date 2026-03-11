"""VisualizerPage — Animated canvas visualizer synced with Player playback."""
import os, math, random, bisect, threading
import tkinter as tk
from tkinter import ttk

from limewire.core.theme import T, _lerp_color
from limewire.core.constants import (
    VISUALIZER_UPDATE_MS, VISUALIZER_BAR_COUNT, VISUALIZER_PARTICLE_COUNT,
    SP_SM, SP_LG,
)
from limewire.core.audio_backend import _audio
from limewire.ui.scroll_frame import ScrollFrame
from limewire.ui.widgets import ClassicBtn, LimeBtn, GroupBox, ClassicCombo
from limewire.services.audio_processing import compute_frequency_profile


# ── Color schemes ─────────────────────────────────────────────────────────────

def _scheme_theme(i, n, amp):
    return T.LIME

def _scheme_rainbow(i, n, amp):
    hue = i / max(1, n)
    r, g, b = _hsv_to_rgb(hue, 0.9, 0.8 + 0.2 * amp)
    return f"#{int(r*255):02x}{int(g*255):02x}{int(b*255):02x}"

def _scheme_fire(i, n, amp):
    t = amp
    r = min(255, int(255 * min(1, t * 2)))
    g = min(255, int(200 * max(0, t - 0.3)))
    b = min(255, int(60 * max(0, t - 0.7)))
    return f"#{r:02x}{g:02x}{b:02x}"

def _scheme_ice(i, n, amp):
    t = amp
    r = min(255, int(60 * max(0, t - 0.5)))
    g = min(255, int(180 * t + 40))
    b = min(255, int(200 + 55 * t))
    return f"#{r:02x}{g:02x}{b:02x}"

_SCHEMES = {
    "Theme": _scheme_theme,
    "Rainbow": _scheme_rainbow,
    "Fire": _scheme_fire,
    "Ice": _scheme_ice,
}

def _hsv_to_rgb(h, s, v):
    if s == 0:
        return v, v, v
    i = int(h * 6)
    f = h * 6 - i
    p, q, t = v * (1 - s), v * (1 - s * f), v * (1 - s * (1 - f))
    i %= 6
    return [(v,t,p),(q,v,p),(p,v,t),(p,q,v),(t,p,v),(v,p,q)][i]


class VisualizerPage(ScrollFrame):
    def __init__(self, parent, app):
        super().__init__(parent)
        self.app = app
        self._mode = "Bars"
        self._running = False
        self._freq_times = None
        self._freq_bands = None
        self._sensitivity = 1.0
        self._scheme_name = "Theme"
        self._fullscreen_win = None
        self._fs_canvas = None
        self._tick_after = None
        self._bars_items = []
        self._particles = []
        self._prev_bands = [0.0] * VISUALIZER_BAR_COUNT
        self._loaded_path = None
        self._build(self.inner)

    # ── UI ────────────────────────────────────────────────────────────────────

    def _build(self, p):
        cg = GroupBox(p, "Visualizer Controls")
        cg.pack(fill="x", padx=10, pady=(10, 6))
        cr = tk.Frame(cg, bg=T.BG)
        cr.pack(fill="x")

        tk.Label(cr, text="Mode:", font=T.F_SMALL, bg=T.BG, fg=T.TEXT).pack(side="left")
        self._mode_var = tk.StringVar(value="Bars")
        mode_cb = ClassicCombo(cr, self._mode_var,
                               ["Bars", "Circular", "Waveform", "Particles"], width=10)
        mode_cb.pack(side="left", padx=(4, 12))
        self._mode_var.trace_add("write", lambda *_: self._on_mode_change())

        tk.Label(cr, text="Colors:", font=T.F_SMALL, bg=T.BG, fg=T.TEXT).pack(side="left")
        self._scheme_var = tk.StringVar(value="Theme")
        ClassicCombo(cr, self._scheme_var, list(_SCHEMES.keys()), width=8).pack(
            side="left", padx=(4, 12))
        self._scheme_var.trace_add("write", lambda *_: setattr(self, '_scheme_name', self._scheme_var.get()))

        tk.Label(cr, text="Sensitivity:", font=T.F_SMALL, bg=T.BG, fg=T.TEXT).pack(side="left")
        self._sens_var = tk.DoubleVar(value=1.0)
        ttk.Scale(cr, from_=0.5, to=2.0, variable=self._sens_var,
                  orient="horizontal", length=100).pack(side="left", padx=(4, 12))
        self._sens_var.trace_add("write", lambda *_: setattr(self, '_sensitivity', self._sens_var.get()))

        LimeBtn(cr, "Fullscreen", self._toggle_fullscreen).pack(side="right")
        self._play_btn = ClassicBtn(cr, "Start", self._toggle_viz)
        self._play_btn.pack(side="right", padx=(0, 6))

        # Canvas
        vg = GroupBox(p, "Visualization")
        vg.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        self._canvas = tk.Canvas(vg, bg=T.CANVAS_BG, height=400, highlightthickness=0)
        self._canvas.pack(fill="both", expand=True, padx=4, pady=4)

        # Status
        self._status = tk.Label(p, text="Waiting for playback...", font=T.F_SMALL,
                                bg=T.BG, fg=T.TEXT_DIM, anchor="w")
        self._status.pack(fill="x", padx=10)

    # ── Control ───────────────────────────────────────────────────────────────

    def _toggle_viz(self):
        if self._running:
            self._stop_viz()
        else:
            self._start_viz()

    def _start_viz(self):
        self._running = True
        self._play_btn.config(text="Stop")
        self._load_freq_data()
        self._on_mode_change()
        self._tick()

    def _stop_viz(self):
        self._running = False
        self._play_btn.config(text="Start")
        if self._tick_after:
            self.after_cancel(self._tick_after)
            self._tick_after = None

    def _on_mode_change(self):
        self._mode = self._mode_var.get()
        self._bars_items = []
        self._particles = []
        cv = self._get_canvas()
        cv.delete("all")
        if self._mode == "Bars":
            self._init_bars(cv)
        elif self._mode == "Particles":
            self._particles = []

    def _load_freq_data(self):
        pp = self.app.pages.get("player")
        if not pp or pp._cur < 0 or pp._cur >= len(pp._playlist):
            return
        path = pp._playlist[pp._cur]
        if path == self._loaded_path:
            return
        self._freq_times = None
        self._freq_bands = None
        self._loaded_path = path
        self._status.config(text="Loading frequency data...", fg=T.YELLOW)

        def _do():
            times, bands = compute_frequency_profile(path, n_bands=VISUALIZER_BAR_COUNT)
            self.after(0, lambda: self._on_freq_loaded(times, bands))

        threading.Thread(target=_do, daemon=True).start()

    def _on_freq_loaded(self, times, bands):
        self._freq_times = times
        self._freq_bands = bands
        name = os.path.basename(self._loaded_path) if self._loaded_path else ""
        if times:
            self._status.config(text=f"Synced: {name}", fg=T.LIME_DK)
        else:
            self._status.config(text=f"No frequency data (librosa required)", fg=T.TEXT_DIM)

    def _get_canvas(self):
        return self._fs_canvas if self._fullscreen_win and self._fs_canvas else self._canvas

    # ── Animation loop ────────────────────────────────────────────────────────

    def _tick(self):
        if not self._running:
            return
        cv = self._get_canvas()
        cv.update_idletasks()
        band_data = self._get_band_data()

        mode = self._mode
        if mode == "Bars":
            self._draw_bars(cv, band_data)
        elif mode == "Circular":
            self._draw_circular(cv, band_data)
        elif mode == "Waveform":
            self._draw_waveform(cv, band_data)
        elif mode == "Particles":
            self._draw_particles(cv, band_data)

        self._tick_after = self.after(VISUALIZER_UPDATE_MS, self._tick)

    def _get_band_data(self):
        if self._freq_times and self._freq_bands and _audio.get_busy():
            pos = _audio.get_pos()
            fi = bisect.bisect_left(self._freq_times, pos)
            fi = min(fi, len(self._freq_bands) - 1)
            raw = self._freq_bands[fi]
            return [min(1.0, v * self._sensitivity) for v in raw]
        # Fallback: gentle random motion
        return [random.uniform(0.05, 0.3) for _ in range(VISUALIZER_BAR_COUNT)]

    # ── Bars mode ─────────────────────────────────────────────────────────────

    def _init_bars(self, cv):
        cv.delete("all")
        w = cv.winfo_width() or 600
        h = cv.winfo_height() or 400
        n = VISUALIZER_BAR_COUNT
        bw = max(2, w / n)
        gap = max(1, bw * 0.15)
        self._bars_items = []
        for i in range(n):
            x = i * bw
            rect = cv.create_rectangle(x + gap, h, x + bw - gap, h,
                                       fill=T.LIME, outline="")
            self._bars_items.append(rect)

    def _draw_bars(self, cv, band_data):
        if not self._bars_items:
            self._init_bars(cv)
        w = cv.winfo_width() or 600
        h = cv.winfo_height() or 400
        n = len(self._bars_items)
        bw = max(2, w / n)
        gap = max(1, bw * 0.15)
        scheme = _SCHEMES.get(self._scheme_name, _scheme_theme)

        for i in range(n):
            target = band_data[i] if i < len(band_data) else 0
            # Smooth transition
            self._prev_bands[i] += (target - self._prev_bands[i]) * 0.4
            amp = self._prev_bands[i]
            bh = max(1, int(amp * h * 0.9))
            x = i * bw
            cv.coords(self._bars_items[i], x + gap, h - bh, x + bw - gap, h)
            cv.itemconfig(self._bars_items[i], fill=scheme(i, n, amp))

    # ── Circular mode ─────────────────────────────────────────────────────────

    def _draw_circular(self, cv, band_data):
        cv.delete("all")
        w = cv.winfo_width() or 600
        h = cv.winfo_height() or 400
        cx, cy = w // 2, h // 2
        base_r = min(cx, cy) * 0.25
        max_r = min(cx, cy) * 0.85
        n = len(band_data)
        scheme = _SCHEMES.get(self._scheme_name, _scheme_theme)

        for i in range(n):
            amp = band_data[i]
            angle = (2 * math.pi * i / n) - math.pi / 2
            r = base_r + (max_r - base_r) * amp
            x1 = cx + base_r * math.cos(angle)
            y1 = cy + base_r * math.sin(angle)
            x2 = cx + r * math.cos(angle)
            y2 = cy + r * math.sin(angle)
            color = scheme(i, n, amp)
            cv.create_line(x1, y1, x2, y2, fill=color, width=max(2, int(w / n * 0.6)))

        # Center circle
        cv.create_oval(cx - base_r, cy - base_r, cx + base_r, cy + base_r,
                       outline=T.LIME, width=2)

    # ── Waveform mode ─────────────────────────────────────────────────────────

    def _draw_waveform(self, cv, band_data):
        cv.delete("all")
        w = cv.winfo_width() or 600
        h = cv.winfo_height() or 400
        mid = h // 2
        n = len(band_data)
        scheme = _SCHEMES.get(self._scheme_name, _scheme_theme)

        points = []
        for i in range(n):
            x = int(i * w / n)
            amp = band_data[i]
            y = mid - int(amp * mid * 0.85)
            points.extend([x, y])

        if len(points) >= 4:
            cv.create_line(points, fill=scheme(0, 1, 0.7), width=2, smooth=True)
            # Mirror
            mirror = []
            for i in range(0, len(points), 2):
                mirror.extend([points[i], h - (points[i + 1] - mid) + mid])
            cv.create_line(mirror, fill=scheme(n // 2, n, 0.5), width=1, smooth=True)

        # Center line
        cv.create_line(0, mid, w, mid, fill=T.TEXT_DIM, dash=(4, 4))

    # ── Particles mode ────────────────────────────────────────────────────────

    def _draw_particles(self, cv, band_data):
        cv.delete("all")
        w = cv.winfo_width() or 600
        h = cv.winfo_height() or 400
        scheme = _SCHEMES.get(self._scheme_name, _scheme_theme)

        # Average energy drives spawn rate
        avg_energy = sum(band_data) / max(1, len(band_data))
        spawn = int(avg_energy * 15)

        for _ in range(spawn):
            if len(self._particles) < VISUALIZER_PARTICLE_COUNT:
                x = random.uniform(w * 0.3, w * 0.7)
                y = h
                vx = random.uniform(-2, 2)
                vy = random.uniform(-4, -1) * (1 + avg_energy * 2)
                life = random.uniform(0.5, 1.0)
                bi = random.randint(0, len(band_data) - 1)
                self._particles.append([x, y, vx, vy, life, bi])

        alive = []
        for p in self._particles:
            p[0] += p[2]  # x += vx
            p[1] += p[3]  # y += vy
            p[3] += 0.1   # gravity
            p[4] -= 0.02  # life decay
            if p[4] > 0 and 0 <= p[0] <= w and p[1] <= h:
                sz = max(1, int(p[4] * 4))
                color = scheme(p[5], len(band_data), p[4])
                cv.create_oval(p[0] - sz, p[1] - sz, p[0] + sz, p[1] + sz,
                               fill=color, outline="")
                alive.append(p)
        self._particles = alive

    # ── Fullscreen ────────────────────────────────────────────────────────────

    def _toggle_fullscreen(self):
        if self._fullscreen_win:
            self._fullscreen_win.destroy()
            self._fullscreen_win = None
            self._fs_canvas = None
            if self._running:
                self._on_mode_change()
            return
        win = tk.Toplevel(self)
        win.attributes("-fullscreen", True)
        win.configure(bg="#000000")
        self._fs_canvas = tk.Canvas(win, bg="#000000", highlightthickness=0)
        self._fs_canvas.pack(fill="both", expand=True)
        self._fullscreen_win = win
        win.bind("<Escape>", lambda e: self._toggle_fullscreen())
        win.bind("<F11>", lambda e: self._toggle_fullscreen())
        # Reset mode items for new canvas
        self._bars_items = []
        self._particles = []
        if not self._running:
            self._start_viz()

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def refresh(self):
        pp = self.app.pages.get("player")
        if pp and 0 <= pp._cur < len(pp._playlist):
            path = pp._playlist[pp._cur]
            if path != self._loaded_path:
                self._load_freq_data()
            name = os.path.basename(path)
            self._status.config(text=f"Track: {name}")
