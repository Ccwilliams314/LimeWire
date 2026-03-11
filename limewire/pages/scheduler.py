"""SchedulerPage — Schedule downloads for future execution."""
import datetime
import tkinter as tk
from tkinter import messagebox

from limewire.core.theme import T
from limewire.core.constants import AUDIO_FMTS
from limewire.core.config import save_json, SCHEDULE_FILE
from limewire.ui.scroll_frame import ScrollFrame
from limewire.ui.widgets import (ClassicBtn, LimeBtn, GroupBox,
                                  ClassicEntry, ClassicCombo)


class SchedulerPage(ScrollFrame):
    """Schedule downloads for future execution."""
    def __init__(self, parent, app):
        super().__init__(parent); self.app = app; self._build(self.inner)

    def _build(self, p):
        g = GroupBox(p, "Schedule a Download"); g.pack(fill="x", padx=10, pady=(10, 6))
        tk.Label(g, text="URL:", font=T.F_BOLD, bg=T.BG, fg=T.TEXT).pack(anchor="w")
        self.sc_url = tk.StringVar()
        ClassicEntry(g, self.sc_url, width=60).pack(fill="x", ipady=2, pady=(0, 6))
        r = tk.Frame(g, bg=T.BG); r.pack(fill="x")
        dc = tk.Frame(r, bg=T.BG); dc.pack(side="left", padx=(0, 16))
        tk.Label(dc, text="Date/Time:", font=T.F_BOLD, bg=T.BG, fg=T.TEXT).pack(
            anchor="w")
        self.sc_dt = tk.StringVar(
            value=(datetime.datetime.now()
                   + datetime.timedelta(hours=1)).strftime("%Y-%m-%d %H:%M"))
        ClassicEntry(dc, self.sc_dt, width=20).pack(anchor="w", ipady=2)
        fc = tk.Frame(r, bg=T.BG); fc.pack(side="left", padx=(0, 16))
        tk.Label(fc, text="Format:", font=T.F_BOLD, bg=T.BG, fg=T.TEXT).pack(anchor="w")
        self.sc_fmt = tk.StringVar(value="mp3")
        ClassicCombo(fc, self.sc_fmt, AUDIO_FMTS, 8).pack(anchor="w")
        flc = tk.Frame(r, bg=T.BG); flc.pack(side="left", fill="x", expand=True)
        tk.Label(flc, text="Save To:", font=T.F_BOLD, bg=T.BG, fg=T.TEXT).pack(
            anchor="w")
        self.sc_f = tk.StringVar(value=self.app.output_dir)
        ClassicEntry(flc, self.sc_f, width=25).pack(
            side="left", fill="x", expand=True, ipady=2)
        LimeBtn(g, "+ Schedule", self._add_job).pack(pady=(8, 0), anchor="w")
        jg = GroupBox(p, "Jobs")
        jg.pack(fill="both", padx=10, pady=(0, 10), expand=True)
        self.jf = tk.Frame(jg, bg=T.BG); self.jf.pack(fill="both", expand=True)

    def refresh(self):
        for w in self.jf.winfo_children():
            w.destroy()
        for job in self.app.schedule:
            row = tk.Frame(self.jf, bg=T.CARD_BG, relief="flat", bd=0, padx=10, pady=8,
                           highlightthickness=1, highlightbackground=T.CARD_BORDER)
            row.pack(fill="x", pady=2)
            st = job.get("status", "pending")
            ico = {"pending": "\u23F1", "running": "\u27F3",
                   "done": "\u2713", "error": "\u2717"}.get(st, "?")
            col = {"pending": T.YELLOW, "running": T.LIME_DK,
                   "done": T.LIME_DK, "error": T.RED}.get(st, T.TEXT)
            tk.Label(row, text=ico, font=T.F_BODY, bg=T.CARD_BG, fg=col).pack(
                side="left", padx=(0, 8))
            tk.Label(row, text=job.get("url", "")[:50], font=T.F_BODY, bg=T.CARD_BG,
                     fg=T.TEXT_BLUE, anchor="w").pack(
                         side="left", fill="x", expand=True)
            tk.Label(row,
                     text=f"{job.get('when', '')} | {job.get('format', '').upper()}",
                     font=T.F_SMALL, bg=T.CARD_BG, fg=T.TEXT_DIM).pack(
                         side="left", padx=(8, 0))
            tk.Button(row, text="X", font=T.F_BTN, bg=T.CARD_BG, fg=T.RED,
                      relief="flat", bd=0, cursor="hand2",
                      command=lambda j=job: self._del(j)).pack(side="right")

    def _add_job(self):
        url = self.sc_url.get().strip()
        if not url or "http" not in url:
            return
        try:
            datetime.datetime.strptime(self.sc_dt.get(), "%Y-%m-%d %H:%M")
        except Exception:
            messagebox.showwarning("LimeWire", "Format: YYYY-MM-DD HH:MM"); return
        with self.app._sched_lock:
            self.app.schedule.append({
                "url": url, "when": self.sc_dt.get(), "format": self.sc_fmt.get(),
                "folder": self.sc_f.get(), "status": "pending",
            })
            save_json(SCHEDULE_FILE, self.app.schedule)
        self.refresh()

    def _del(self, job):
        with self.app._sched_lock:
            self.app.schedule.remove(job)
            save_json(SCHEDULE_FILE, self.app.schedule)
        self.refresh()
