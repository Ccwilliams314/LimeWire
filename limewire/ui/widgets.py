"""Modern UI widgets — ModernBtn, ClassicBtn, LimeBtn, GroupBox, entries, etc."""
import tkinter as tk
from tkinter import ttk

from limewire.core.theme import T, _lerp_color
from limewire.core.constants import SP_XS, SP_SM, SP_MD, SP_LG


def _round_rect(cv, x1, y1, x2, y2, radius=10, **kw):
    """Draw a smooth rounded rectangle on a Canvas."""
    r = radius
    pts = [x1+r, y1, x2-r, y1, x2, y1, x2, y1+r,
           x2, y2-r, x2, y2, x2-r, y2, x1+r, y2,
           x1, y2, x1, y2-r, x1, y1+r, x1, y1, x1+r, y1]
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

    def _on_release(self, e=None):
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
                                fill=_lerp_color(T.TEXT_DIM, T.BG, 0.3))
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
