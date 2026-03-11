"""ToolTip — hover tooltip with delay and theme-matching colors."""
import tkinter as tk

from limewire.core.theme import T
from limewire.core.constants import SP_SM, SP_MD


class ToolTip:
    """Hover tooltip with delay, theme-matching colors."""

    def __init__(self, widget, text, delay=300):
        self._w = widget
        self._text = text
        self._delay = delay
        self._tw = None
        self._aid = None
        widget.bind("<Enter>", self._schedule, add="+")
        widget.bind("<Leave>", self._cancel, add="+")

    def _schedule(self, e=None):
        self._cancel()
        self._aid = self._w.after(self._delay, self._show)

    def _cancel(self, e=None):
        if self._aid:
            self._w.after_cancel(self._aid)
            self._aid = None
        if self._tw:
            try:
                self._tw.destroy()
            except Exception:
                pass
            self._tw = None

    def _show(self):
        self._aid = None
        tw = tk.Toplevel(self._w)
        tw.overrideredirect(True)
        tw.attributes("-topmost", True)
        tw.configure(bg=T.CARD_BORDER)
        f = tk.Frame(tw, bg=T.SURFACE, padx=SP_MD, pady=SP_SM)
        f.pack(fill="both", expand=True, padx=1, pady=1)
        tk.Label(f, text=self._text, font=T.F_SMALL, bg=T.SURFACE,
                 fg=T.TEXT, wraplength=280, justify="left").pack()
        tw.update_idletasks()
        x = (self._w.winfo_rootx() + self._w.winfo_width() // 2
             - tw.winfo_width() // 2)
        y = self._w.winfo_rooty() + self._w.winfo_height() + 6
        tw.geometry(f"+{x}+{y}")
        self._tw = tw
