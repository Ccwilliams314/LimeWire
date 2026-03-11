"""ScrollFrame — scrollable container used as base for all page tabs."""
import tkinter as tk
from tkinter import ttk

from limewire.core.theme import T


class ScrollFrame(tk.Frame):
    """A scrollable frame widget. All page tabs extend this."""

    def __init__(self, parent, **kw):
        super().__init__(parent, bg=T.BG, **kw)
        self._cv = tk.Canvas(self, bg=T.BG, highlightthickness=0)
        vsb = ttk.Scrollbar(self, orient="vertical", command=self._cv.yview,
                            style="Vertical.TScrollbar")
        self._cv.configure(yscrollcommand=vsb.set)
        vsb.pack(side="right", fill="y")
        self._cv.pack(side="left", fill="both", expand=True)
        self.inner = tk.Frame(self._cv, bg=T.BG)
        self._wid = self._cv.create_window((0, 0), window=self.inner,
                                           anchor="nw")
        self.inner.bind("<Configure>",
                        lambda e: self._cv.configure(
                            scrollregion=self._cv.bbox("all")))
        self._cv.bind("<Configure>",
                      lambda e: self._cv.itemconfig(self._wid, width=e.width))
        self._cv.bind("<Enter>",
                      lambda e: self._cv.bind_all("<MouseWheel>",
                                                  self._on_wheel))
        self._cv.bind("<Leave>",
                      lambda e: self._cv.unbind_all("<MouseWheel>"))

    def _on_wheel(self, e):
        """Smooth scroll — animate over several frames."""
        delta = -1 * (e.delta // 120)
        self._smooth_scroll(delta * 3, steps=6)

    def _smooth_scroll(self, total_units, steps=6, step=0):
        if step >= steps or total_units == 0:
            return
        self._cv.yview_scroll(1 if total_units > 0 else -1, "units")
        remaining = abs(total_units) - 1
        if remaining > 0:
            sign = 1 if total_units > 0 else -1
            self._cv.after(12, lambda: self._smooth_scroll(
                sign * remaining, steps, step + 1))
