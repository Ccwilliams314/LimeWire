"""Toast notifications — slide-in/fade-out toast system."""
import tkinter as tk

from limewire.core.theme import T, _lerp_color
from limewire.core.constants import SP_SM, SP_MD, SP_LG


class _ToastManager:
    """Manages a stack of up to 4 toast notifications."""
    MAX_TOASTS = 4

    def __init__(self):
        self._stack = []

    def show(self, parent, msg, duration=3000,
             bg_color=None, fg_color=None, icon=None):
        # Dismiss oldest if at capacity
        while len(self._stack) >= self.MAX_TOASTS:
            old = self._stack.pop(0)
            try:
                old.destroy()
            except Exception:
                pass
        t = _Toast(parent, msg, duration, bg_color, fg_color, icon, self)
        self._stack.append(t)
        self._reposition(parent)

    def remove(self, toast):
        if toast in self._stack:
            self._stack.remove(toast)

    def _reposition(self, parent):
        try:
            pw = parent.winfo_rootx() + parent.winfo_width()
            py = parent.winfo_rooty()
        except Exception:
            return
        for i, t in enumerate(self._stack):
            try:
                w = t.winfo_width()
                tx = pw - w - SP_LG
                ty = py + 56 + i * 58
                t._target_x = tx
                t._y = ty
            except Exception:
                pass


_toast_mgr = _ToastManager()


class _Toast(tk.Toplevel):
    """Single toast notification with slide-in and fade-out."""

    def __init__(self, parent, msg, duration=3000,
                 bg_color=None, fg_color=None, icon=None, mgr=None):
        super().__init__(parent)
        self._mgr = mgr
        self.overrideredirect(True)
        self.attributes("-topmost", True)
        _bg = bg_color or T.LIME_DK
        _fg = fg_color or "#FFFFFF"
        self.configure(bg=_lerp_color(_bg, "#000000", 0.3))
        inner = tk.Frame(self, bg=_bg)
        inner.pack(fill="both", expand=True, padx=1, pady=1)
        row = tk.Frame(inner, bg=_bg)
        row.pack(fill="x", padx=SP_LG, pady=SP_MD)
        ico = icon or "\u2713"
        tk.Label(row, text=ico, font=("Segoe UI Symbol", 16),
                 bg=_bg, fg=_fg).pack(side="left", padx=(0, SP_MD))
        tk.Label(row, text=msg, font=T.F_BOLD, bg=_bg, fg=_fg,
                 wraplength=350, justify="left").pack(side="left", fill="x")
        close_btn = tk.Label(row, text="\u2715", font=T.F_CAPTION, bg=_bg,
                             fg=_lerp_color(_fg, _bg, 0.4), cursor="hand2")
        close_btn.pack(side="right", padx=(SP_SM, 0))
        close_btn.bind("<Button-1>", lambda e: self._fade_out(0.8))
        self.update_idletasks()
        pw = parent.winfo_rootx() + parent.winfo_width()
        py = parent.winfo_rooty()
        w = self.winfo_width()
        idx = len(mgr._stack) if mgr else 0
        self._target_x = pw - w - SP_LG
        self._start_x = pw + 10
        self._y = py + 56 + idx * 58
        self.geometry(f"+{self._start_x}+{self._y}")
        self._slide_in()
        self.after(duration, self._fade_out)

    def _slide_in(self, step=0):
        if step > 8:
            return
        x = self._start_x + int(
            (self._target_x - self._start_x) * (step / 8))
        try:
            self.geometry(f"+{x}+{self._y}")
            self.after(16, lambda: self._slide_in(step + 1))
        except Exception:
            pass

    def _fade_out(self, alpha=1.0):
        if alpha <= 0:
            if self._mgr:
                self._mgr.remove(self)
            try:
                self.destroy()
            except Exception:
                pass
            return
        try:
            self.attributes("-alpha", alpha)
            self.after(30, lambda: self._fade_out(alpha - 0.1))
        except Exception:
            pass


def show_toast(parent, msg, level="info", duration=3000):
    """Show a themed toast notification."""
    colors = {
        "info": (T.LIME_DK, "#FFFFFF", "\u2713"),
        "warn": (T.WARNING, "#000000", "\u26A0"),
        "error": (T.ERROR, "#FFFFFF", "\u2717"),
        "success": (T.SUCCESS, "#FFFFFF", "\u2713"),
    }
    bg, fg, ico = colors.get(level, (T.LIME_DK, "#FFFFFF", "\u2139"))
    _toast_mgr.show(parent, msg, duration, bg, fg, ico)
