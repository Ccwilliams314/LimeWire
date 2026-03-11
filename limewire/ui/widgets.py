"""Modern UI widgets — ModernBtn, ClassicBtn, LimeBtn, GroupBox, entries, etc."""
import tkinter as tk
from tkinter import ttk

from limewire.core.theme import T, _lerp_color
from limewire.core.constants import S, SP_XS, SP_SM, SP_MD, SP_LG
from limewire.core.settings_registry import get_page_setting, set_page_setting


def _round_rect_coords(x1, y1, x2, y2, radius=10):
    """Return polygon point list for a smooth rounded rectangle."""
    r = radius
    return [x1+r, y1, x2-r, y1, x2, y1, x2, y1+r,
            x2, y2-r, x2, y2, x2-r, y2, x1+r, y2,
            x1, y2, x1, y2-r, x1, y1+r, x1, y1, x1+r, y1]


def _round_rect(cv, x1, y1, x2, y2, radius=10, **kw):
    """Draw a smooth rounded rectangle on a Canvas."""
    pts = _round_rect_coords(x1, y1, x2, y2, radius)
    return cv.create_polygon(pts, smooth=True, **kw)


class ModernBtn(tk.Canvas):
    """Canvas-based rounded button with hover/press feedback and smooth transitions."""

    def __init__(self, parent, text="", command=None, width=None,
                 bg_color=None, fg_color=None, hover_color=None,
                 font=None, padx=20, pady=8, radius=10, **kw):
        self._bg_c = bg_color or T.BG
        self._fg_c = fg_color or T.TEXT
        self._hover_c = hover_color or T.BTN_HOVER
        self._font = font or T.F_BTN
        self._text = text
        self._cmd = command
        self._radius = radius
        self._padx = padx
        self._pady = pady
        self._pressed = False
        self._animating = False

        _tmp = tk.Label(parent, text=text, font=self._font)
        tw = _tmp.winfo_reqwidth()
        th = _tmp.winfo_reqheight()
        _tmp.destroy()
        if width:
            tw = max(tw, width * 8)
        cw = tw + padx * 2
        ch = th + pady * 2

        parent_bg = parent.cget("bg") if hasattr(parent, "cget") else T.BG
        super().__init__(parent, width=cw, height=ch, bg=parent_bg,
                         highlightthickness=0, bd=0, cursor="hand2", **kw)
        self._cw = cw
        self._ch = ch
        self._outline = _round_rect(self, 1, 1, cw-1, ch-1, radius=radius,
                                    fill="", outline=T.DIVIDER, width=1)
        self._rect = _round_rect(self, 2, 2, cw-2, ch-2,
                                 radius=max(1, radius-1),
                                 fill=self._bg_c, outline="")
        self._orig_rect_coords = _round_rect_coords(2, 2, cw-2, ch-2, max(1, radius-1))
        self._label = self.create_text(cw//2, ch//2, text=text,
                                       font=self._font, fill=self._fg_c)
        self.tag_raise(self._label)
        self.bind("<Enter>", self._on_enter)
        self.bind("<Leave>", self._on_leave)
        self.bind("<ButtonPress-1>", self._on_press)
        self.bind("<ButtonRelease-1>", self._on_release)

    def _animate_to(self, target, steps=3, step=0):
        if step >= steps:
            self.itemconfig(self._rect, fill=target)
            self._animating = False
            return
        self._animating = True
        current = self.itemcget(self._rect, "fill")
        mid = _lerp_color(current, target, (step + 1) / steps)
        self.itemconfig(self._rect, fill=mid)
        self.after(25, lambda: self._animate_to(target, steps, step + 1))

    def _on_enter(self, e=None):
        self._animate_to(self._hover_c, steps=3)

    def _on_leave(self, e=None):
        self._pressed = False
        self._animate_to(self._bg_c, steps=3)

    def _on_press(self, e=None):
        self._pressed = True
        self.itemconfig(self._rect, fill=T.BTN_PRESSED)
        # Scale-down effect
        s = S(2)
        shrunk = _round_rect_coords(2+s, 2+s, self._cw-2-s, self._ch-2-s,
                                    max(1, self._radius-2))
        self.coords(self._rect, *shrunk)
        self.coords(self._label, self._cw//2, self._ch//2 + 1)

    def _on_release(self, e=None):
        # Restore original size
        self.coords(self._rect, *self._orig_rect_coords)
        self.coords(self._label, self._cw//2, self._ch//2)
        if self._pressed and self._cmd:
            self._pressed = False
            self.itemconfig(self._rect, fill=self._hover_c)
            self._cmd()

    def config(self, **kw):
        self.configure(**kw)

    def configure(self, **kw):
        if "text" in kw:
            self._text = kw.pop("text")
            self.itemconfig(self._label, text=self._text)
        if "bg" in kw:
            self._bg_c = kw.pop("bg")
            self.itemconfig(self._rect, fill=self._bg_c)
        if "fg" in kw:
            self._fg_c = kw.pop("fg")
            self.itemconfig(self._label, fill=self._fg_c)
        if "command" in kw:
            self._cmd = kw.pop("command")
        if "state" in kw:
            st = kw.pop("state")
            if st == "disabled":
                self.itemconfig(self._rect, fill=T.SURFACE_2)
                self.itemconfig(self._label,
                                fill=_lerp_color(T.TEXT_DIM, T.BG, 0.12))
                self.itemconfig(self._outline, outline=T.DIVIDER)
                self.unbind("<Enter>"); self.unbind("<Leave>")
                self.unbind("<ButtonPress-1>"); self.unbind("<ButtonRelease-1>")
                self["cursor"] = ""
            else:
                self.itemconfig(self._rect, fill=self._bg_c)
                self.itemconfig(self._label, fill=self._fg_c)
                self.itemconfig(self._outline, outline=T.DIVIDER)
                self.bind("<Enter>", self._on_enter)
                self.bind("<Leave>", self._on_leave)
                self.bind("<ButtonPress-1>", self._on_press)
                self.bind("<ButtonRelease-1>", self._on_release)
                self["cursor"] = "hand2"
        if kw:
            super().configure(**kw)

    def cget(self, key):
        if key == "text":
            return self._text
        if key == "bg":
            return self._bg_c
        if key == "fg":
            return self._fg_c
        return super().cget(key)


# ── Factory functions ────────────────────────────────────────────────────────

def ClassicBtn(parent, text, cmd, width=None):
    return ModernBtn(parent, text=text, command=cmd, width=width,
                     bg_color=T.SURFACE_2, fg_color=T.TEXT,
                     hover_color=T.BTN_HOVER)


def LimeBtn(parent, text, cmd, width=None):
    return ModernBtn(parent, text=text, command=cmd, width=width,
                     bg_color=T.LIME, fg_color="#000000",
                     hover_color=T.LIME_HOVER)


def OrangeBtn(parent, text, cmd, width=None):
    return ModernBtn(parent, text=text, command=cmd, width=width,
                     bg_color=T.ORANGE, fg_color="#FFFFFF",
                     hover_color=T.ORANGE_HOVER)


def GroupBox(parent, text):
    lf = tk.LabelFrame(
        parent, text=f"  {text}  ", font=T.F_SECTION, bg=T.CARD_BG,
        fg=T.TEXT, relief="flat", bd=0, padx=SP_LG, pady=SP_MD,
        highlightthickness=1, highlightbackground=T.CARD_BORDER,
        highlightcolor=T.CARD_BORDER, labelanchor="nw")
    accent = tk.Frame(lf, bg=T.LIME, width=4)
    accent.place(x=0, y=8, relheight=0.85)
    # Drop shadow
    shadow = tk.Frame(parent, bg=_lerp_color(T.BG, "#000000", 0.08))
    lf._shadow = shadow
    _orig_pack = lf.pack

    def _shadow_pack(*a, **kw):
        _orig_pack(*a, **kw)
        lf.update_idletasks()
        shadow.place(in_=lf, x=S(3), y=S(3), relwidth=1.0, relheight=1.0)
        shadow.lower(lf)
    lf.pack = _shadow_pack
    return lf


def ClassicEntry(parent, var, width=40, **kw):
    return tk.Entry(
        parent, textvariable=var, font=T.F_BODY, bg=T.INPUT_BG,
        fg=T.TEXT, relief="flat", bd=0, insertbackground=T.LIME,
        width=width, highlightthickness=2,
        highlightbackground=T.INPUT_BORDER,
        highlightcolor=T.INPUT_FOCUS,
        selectbackground=T.BLUE_HL, selectforeground="#FFFFFF", **kw)


def ClassicCombo(parent, var, values, width=14):
    return ttk.Combobox(parent, textvariable=var, values=values,
                        state="readonly", width=width, font=T.F_BODY)


def ClassicCheck(parent, text, var):
    return tk.Checkbutton(
        parent, text=text, variable=var, font=T.F_BODY,
        bg=T.BG, fg=T.TEXT, activebackground=T.BG,
        activeforeground=T.LIME, selectcolor=T.SURFACE_2,
        anchor="w", relief="flat", bd=0, highlightthickness=0,
        padx=SP_SM, pady=3, indicatoron=True, cursor="hand2")


def ClassicListbox(parent, height=8, **kw):
    f = tk.Frame(parent, bg=T.INPUT_BORDER, padx=1, pady=1)
    lb = tk.Listbox(
        f, font=T.F_BODY, bg=T.INPUT_BG, fg=T.TEXT,
        selectbackground=T.BLUE_HL, selectforeground="#FFFFFF",
        relief="flat", height=height, activestyle="none", bd=0,
        highlightthickness=0, selectborderwidth=0, **kw)
    sb = ttk.Scrollbar(f, orient="vertical", command=lb.yview,
                       style="Vertical.TScrollbar")
    lb.config(yscrollcommand=sb.set)
    sb.pack(side="right", fill="y")
    lb.pack(side="left", fill="both", expand=True)
    return f, lb


def ClassicProgress(parent, thin=False):
    style = ("Thin.Horizontal.TProgressbar" if thin
             else "Lime.Horizontal.TProgressbar")
    return ttk.Progressbar(parent, style=style, mode="determinate", maximum=100)


def HSep(parent):
    tk.Frame(parent, bg=T.DIVIDER, height=1).pack(fill="x", pady=SP_SM)


# ── Animated widgets ────────────────────────────────────────────────────────

class LoadingSpinner(tk.Canvas):
    """Animated rotating arc spinner for async operations."""

    def __init__(self, parent, size=24, width=3, color=None, **kw):
        s = S(size)
        parent_bg = parent.cget("bg") if hasattr(parent, "cget") else T.BG
        super().__init__(parent, width=s, height=s, highlightthickness=0,
                         bg=parent_bg, bd=0, **kw)
        self._size = s
        self._lw = S(width)
        self._color = color or T.LIME
        self._angle = 0
        self._running = False
        pad = self._lw + 1
        self.create_arc(pad, pad, s - pad, s - pad, start=0, extent=359,
                        style="arc", outline=T.SURFACE_2, width=self._lw)
        self._arc = self.create_arc(pad, pad, s - pad, s - pad,
                                    start=0, extent=90, style="arc",
                                    outline=self._color, width=self._lw)

    def start(self):
        self._running = True
        self._tick()

    def stop(self):
        self._running = False

    def _tick(self):
        if not self._running:
            return
        self._angle = (self._angle + 12) % 360
        self.itemconfig(self._arc, start=self._angle)
        self.after(25, self._tick)


class ShimmerProgress(tk.Canvas):
    """Progress bar with animated shimmer highlight sweep."""

    def __init__(self, parent, height=8, **kw):
        h = S(height)
        parent_bg = parent.cget("bg") if hasattr(parent, "cget") else T.BG
        super().__init__(parent, height=h, highlightthickness=0,
                         bg=parent_bg, bd=0, **kw)
        self._h = h
        self._value = 0
        self._shimmer_x = 0
        self._running = False
        self._bg_rect = self.create_rectangle(0, 0, 0, h, fill=T.SURFACE_2, outline="")
        self._fill_rect = self.create_rectangle(0, 0, 0, h, fill=T.LIME, outline="")
        self._shimmer = self.create_rectangle(0, 0, 0, h, fill=T.LIME_LT, outline="",
                                              state="hidden")
        self.bind("<Configure>", self._redraw)

    def set(self, value):
        self._value = max(0, min(100, value))
        self._redraw()
        if value > 0 and not self._running:
            self._running = True
            self._shimmer_x = 0
            self._animate()
        elif value <= 0:
            self._running = False
            self.itemconfig(self._shimmer, state="hidden")

    def _redraw(self, e=None):
        w = self.winfo_width()
        fill_w = int(w * self._value / 100)
        self.coords(self._bg_rect, 0, 0, w, self._h)
        self.coords(self._fill_rect, 0, 0, fill_w, self._h)

    def _animate(self):
        if not self._running or self._value <= 0:
            self._running = False
            self.itemconfig(self._shimmer, state="hidden")
            return
        w = self.winfo_width()
        fill_w = int(w * self._value / 100)
        sw = S(40)
        self._shimmer_x += S(4)
        if self._shimmer_x > fill_w + sw:
            self._shimmer_x = -sw
        x1 = max(0, self._shimmer_x)
        x2 = min(fill_w, self._shimmer_x + sw)
        if x2 > x1:
            self.coords(self._shimmer, x1, 0, x2, self._h)
            self.itemconfig(self._shimmer, state="normal")
        else:
            self.itemconfig(self._shimmer, state="hidden")
        self.after(30, self._animate)


# ── Per-page settings infrastructure ────────────────────────────────────────

class PageSettingsPanel(tk.Frame):
    """Collapsible inline settings panel for per-page configuration.

    specs: list of (key, label, widget_type, default, options)
        widget_type: "bool", "int", "float", "str", "choice"
        options: dict with optional keys:
            choices: list of values (for "choice")
            min/max: numeric bounds (for "int"/"float")
    """

    def __init__(self, parent, page_key, app, specs):
        super().__init__(parent, bg=T.CARD_BG, highlightthickness=1,
                         highlightbackground=T.CARD_BORDER,
                         highlightcolor=T.CARD_BORDER)
        self._page_key = page_key
        self._app = app
        self._specs = specs
        self._vars = {}
        self._defaults = {s[0]: s[3] for s in specs}

        header = tk.Frame(self, bg=T.CARD_BG)
        header.pack(fill="x", padx=SP_SM, pady=(SP_XS, 0))
        tk.Label(header, text="\u2699  Page Settings", font=T.F_BOLD,
                 bg=T.CARD_BG, fg=T.TEXT_DIM).pack(side="left")

        for key, label, wtype, default, opts in specs:
            self._build_row(key, label, wtype, default, opts or {})

    def _build_row(self, key, label, wtype, default, opts):
        row = tk.Frame(self, bg=T.CARD_BG)
        row.pack(fill="x", padx=SP_MD, pady=(0, 3))
        tk.Label(row, text=f"{label}:", font=T.F_BODY, bg=T.CARD_BG,
                 fg=T.TEXT, width=20, anchor="w").pack(side="left")

        saved = get_page_setting(self._app.settings, self._page_key, key)
        val = saved if saved is not None else default

        if wtype == "bool":
            var = tk.BooleanVar(value=bool(val))
            tk.Checkbutton(row, variable=var, bg=T.CARD_BG,
                           activebackground=T.CARD_BG, selectcolor=T.SURFACE_2,
                           command=lambda k=key, v=var: self._on_change(k, v.get())
                           ).pack(side="left")
        elif wtype == "choice":
            var = tk.StringVar(value=str(val))
            cb = ttk.Combobox(row, textvariable=var,
                              values=opts.get("choices", []),
                              state="readonly", width=14, font=T.F_BODY)
            cb.pack(side="left", padx=(4, 0))
            cb.bind("<<ComboboxSelected>>",
                    lambda e, k=key, v=var: self._on_change(k, v.get()))
        elif wtype in ("int", "float"):
            var = tk.StringVar(value=str(val))
            mn = opts.get("min", 0)
            mx = opts.get("max", 99999)
            sb = tk.Spinbox(row, textvariable=var, from_=mn, to=mx,
                            width=8, font=T.F_BODY, bg=T.INPUT_BG,
                            fg=T.TEXT, buttonbackground=T.SURFACE_2,
                            relief="flat", bd=0, highlightthickness=1,
                            highlightbackground=T.INPUT_BORDER)
            if wtype == "float":
                sb.config(increment=opts.get("increment", 0.1))
            sb.pack(side="left", padx=(4, 0))
            sb.bind("<Return>",
                    lambda e, k=key, v=var, t=wtype: self._on_num_change(k, v, t))
            sb.bind("<FocusOut>",
                    lambda e, k=key, v=var, t=wtype: self._on_num_change(k, v, t))
            sb.bind("<<Increment>>",
                    lambda e, k=key, v=var, t=wtype: self.after(10, lambda: self._on_num_change(k, v, t)))
            sb.bind("<<Decrement>>",
                    lambda e, k=key, v=var, t=wtype: self.after(10, lambda: self._on_num_change(k, v, t)))
        else:  # str
            var = tk.StringVar(value=str(val))
            e = tk.Entry(row, textvariable=var, font=T.F_BODY, bg=T.INPUT_BG,
                         fg=T.TEXT, relief="flat", bd=0, width=20,
                         insertbackground=T.LIME, highlightthickness=1,
                         highlightbackground=T.INPUT_BORDER)
            e.pack(side="left", padx=(4, 0))
            e.bind("<Return>",
                   lambda ev, k=key, v=var: self._on_change(k, v.get()))
            e.bind("<FocusOut>",
                   lambda ev, k=key, v=var: self._on_change(k, v.get()))

        self._vars[key] = var

    def _on_change(self, key, value):
        set_page_setting(self._app.settings, self._page_key, key, value)
        self._app._save_settings()

    def _on_num_change(self, key, var, typ):
        try:
            val = int(var.get()) if typ == "int" else float(var.get())
        except (ValueError, tk.TclError):
            val = self._defaults[key]
            var.set(str(val))
        self._on_change(key, val)

    def get(self, key):
        """Get current value of a page setting."""
        return get_page_setting(self._app.settings, self._page_key, key)


def GearButton(parent, panel):
    """Small gear icon button that toggles a PageSettingsPanel's visibility."""
    visible = [False]

    def _toggle():
        if visible[0]:
            panel.pack_forget()
            visible[0] = False
        else:
            panel.pack(fill="x", padx=10, pady=(0, 6), before=_find_next(panel))
            visible[0] = True

    def _find_next(widget):
        """Find the widget packed after the gear button's parent row."""
        return None  # pack at end; each page controls placement

    btn = ModernBtn(parent, text="\u2699", command=_toggle,
                    bg_color=T.SURFACE_2, fg_color=T.TEXT_DIM,
                    hover_color=T.BTN_HOVER, padx=8, pady=4, radius=6)
    btn._panel = panel
    btn._toggle = _toggle
    return btn
