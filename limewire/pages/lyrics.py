"""LyricsPage — Synced lyrics display with karaoke mode and LRC support."""
import os, re, bisect, threading
import tkinter as tk
from tkinter import ttk, filedialog

import mutagen

from limewire.core.theme import T
from limewire.core.constants import (
    LRC_OFFSET_RANGE, LYRICS_FONT_SIZE_DEFAULT, LYRICS_UPDATE_MS,
    SP_SM, SP_LG,
)
from limewire.core.audio_backend import _audio
from limewire.ui.scroll_frame import ScrollFrame
from limewire.ui.widgets import (
    ClassicBtn, LimeBtn, GroupBox, ClassicCheck, ClassicEntry,
    PageSettingsPanel, GearButton,
)
from limewire.ui.toast import show_toast
from limewire.services.metadata import lookup_lyrics


class LyricsPage(ScrollFrame):
    def __init__(self, parent, app):
        super().__init__(parent)
        self.app = app
        self._lyrics_raw = ""
        self._lrc_lines = []          # [(time_sec, text), ...]
        self._current_line = -1
        self._karaoke_var = tk.BooleanVar(value=True)
        self._offset_var = tk.DoubleVar(value=0.0)
        self._font_size_var = tk.IntVar(value=LYRICS_FONT_SIZE_DEFAULT)
        self._synced = False
        self._update_after = None
        self._build(self.inner)

    # ── UI ────────────────────────────────────────────────────────────────────

    def _build(self, p):
        # Controls
        cg = GroupBox(p, "Lyrics")
        cg.pack(fill="x", padx=10, pady=(10, 6))
        cr = tk.Frame(cg, bg=T.BG)
        cr.pack(fill="x")
        self._settings_panel = PageSettingsPanel(p, "lyrics", self.app, [
            ("font_family", "Font Family", "choice", "Segoe UI", {"choices": ["Segoe UI", "Consolas", "Arial", "Georgia"]}),
            ("alignment", "Text Alignment", "choice", "center", {"choices": ["left", "center", "right"]}),
        ])
        self._gear = GearButton(cr, self._settings_panel)
        self._gear.pack(side="right")
        LimeBtn(cr, "Fetch Lyrics", self._fetch_lyrics).pack(side="left", padx=(0, 6))
        ClassicBtn(cr, "Load LRC", self._load_lrc).pack(side="left", padx=(0, 6))
        ClassicBtn(cr, "Save LRC", self._save_lrc).pack(side="left", padx=(0, 6))
        ClassicBtn(cr, "Clear", self._clear).pack(side="left")

        self._track_lbl = tk.Label(cg, text="No track loaded", font=T.F_SMALL,
                                   bg=T.BG, fg=T.TEXT_DIM, anchor="w")
        self._track_lbl.pack(fill="x", pady=(4, 0))

        # Settings
        sg = GroupBox(p, "Display Settings")
        sg.pack(fill="x", padx=10, pady=(0, 6))
        sr = tk.Frame(sg, bg=T.BG)
        sr.pack(fill="x")

        ClassicCheck(sr, "Karaoke Mode", self._karaoke_var).pack(side="left", padx=(0, 12))

        tk.Label(sr, text="Font:", font=T.F_SMALL, bg=T.BG, fg=T.TEXT).pack(side="left")
        font_sc = ttk.Scale(sr, from_=10, to=28, variable=self._font_size_var,
                            orient="horizontal", length=100,
                            command=lambda _: self._apply_font())
        font_sc.pack(side="left", padx=(4, 12))

        tk.Label(sr, text="Offset:", font=T.F_SMALL, bg=T.BG, fg=T.TEXT).pack(side="left")
        off_sc = ttk.Scale(sr, from_=-LRC_OFFSET_RANGE, to=LRC_OFFSET_RANGE,
                           variable=self._offset_var, orient="horizontal", length=120)
        off_sc.pack(side="left", padx=(4, 4))
        self._off_lbl = tk.Label(sr, text="0.0s", font=T.F_SMALL, bg=T.BG, fg=T.TEXT_DIM,
                                 width=5)
        self._off_lbl.pack(side="left")
        self._offset_var.trace_add("write", self._on_offset)

        # Lyrics display
        lg = GroupBox(p, "Lyrics Display")
        lg.pack(fill="both", expand=True, padx=10, pady=(0, 10))

        self._txt = tk.Text(lg, bg=T.CANVAS_BG, fg=T.TEXT, font=("Segoe UI", LYRICS_FONT_SIZE_DEFAULT),
                            wrap="word", state="disabled", cursor="arrow",
                            highlightthickness=0, bd=0, padx=20, pady=20,
                            spacing1=4, spacing3=4)
        sb = ttk.Scrollbar(lg, orient="vertical", command=self._txt.yview)
        self._txt.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        self._txt.pack(fill="both", expand=True)

        # Tags for karaoke highlighting
        self._txt.tag_configure("current", foreground=T.LIME,
                                font=("Segoe UI Bold", LYRICS_FONT_SIZE_DEFAULT))
        self._txt.tag_configure("past", foreground=T.TEXT_DIM)
        self._txt.tag_configure("future", foreground=T.TEXT)
        self._txt.tag_configure("center", justify="center")

        # Status
        self._status = tk.Label(p, text="", font=T.F_SMALL, bg=T.BG, fg=T.TEXT_DIM,
                                anchor="w")
        self._status.pack(fill="x", padx=10)

    # ── Lyrics fetch ──────────────────────────────────────────────────────────

    def _get_current_track(self):
        pp = self.app.pages.get("player")
        if pp and 0 <= pp._cur < len(pp._playlist):
            return pp._playlist[pp._cur]
        return None

    def _fetch_lyrics(self):
        path = self._get_current_track()
        if not path:
            show_toast(self.app, "No track playing", "warning")
            return
        title, artist = "", ""
        try:
            mf = mutagen.File(path, easy=True)
            if mf:
                title = (mf.get("title") or [""])[0]
                artist = (mf.get("artist") or [""])[0]
        except Exception:
            pass
        if not title:
            title = os.path.splitext(os.path.basename(path))[0]
        self._track_lbl.config(text=f"{artist} - {title}" if artist else title)
        self._status.config(text="Searching...", fg=T.YELLOW)

        def _do():
            result = lookup_lyrics(title, artist)
            self.after(0, lambda: self._on_lyrics(result))

        threading.Thread(target=_do, daemon=True).start()

    def _on_lyrics(self, result):
        if "error" in result and not result.get("lyrics"):
            self._status.config(text=result["error"], fg=T.RED)
            return
        lyrics = result.get("lyrics", "")
        url = result.get("url", "")
        self._lyrics_raw = lyrics
        self._synced = False
        self._lrc_lines = []
        self._display_text(lyrics)
        src = f"Source: Genius"
        if url:
            src += f"  |  {url}"
        self._status.config(text=src, fg=T.TEXT_DIM)

    # ── LRC support ───────────────────────────────────────────────────────────

    def _parse_lrc(self, content):
        lines = []
        for line in content.splitlines():
            m = re.match(r'\[(\d+):(\d+(?:\.\d+)?)\]\s*(.*)', line)
            if m:
                mins, secs, text = m.groups()
                t = int(mins) * 60 + float(secs)
                if text.strip():
                    lines.append((t, text.strip()))
        return sorted(lines, key=lambda x: x[0])

    def _load_lrc(self):
        path = filedialog.askopenfilename(
            filetypes=[("LRC files", "*.lrc"), ("All", "*.*")])
        if not path:
            return
        try:
            for enc in ("utf-8", "utf-8-sig", "latin-1"):
                try:
                    with open(path, encoding=enc) as f:
                        content = f.read()
                    break
                except UnicodeDecodeError:
                    continue
            else:
                show_toast(self.app, "Could not decode LRC file", "error")
                return
            self._lrc_lines = self._parse_lrc(content)
            if not self._lrc_lines:
                show_toast(self.app, "No timed lines found in LRC", "warning")
                return
            self._synced = True
            text = "\n".join(t for _, t in self._lrc_lines)
            self._display_text(text)
            self._status.config(text=f"Loaded: {os.path.basename(path)} ({len(self._lrc_lines)} lines)",
                                fg=T.LIME_DK)
            self._start_tracking()
        except Exception as e:
            show_toast(self.app, f"Error: {e}", "error")

    def _save_lrc(self):
        if not self._lrc_lines:
            show_toast(self.app, "No synced lyrics to save", "warning")
            return
        path = filedialog.asksaveasfilename(
            defaultextension=".lrc", filetypes=[("LRC files", "*.lrc")])
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8") as f:
                for t, text in self._lrc_lines:
                    m, s = divmod(t, 60)
                    f.write(f"[{int(m):02d}:{s:05.2f}]{text}\n")
            show_toast(self.app, "LRC saved", "success")
        except Exception as e:
            show_toast(self.app, f"Error: {e}", "error")

    # ── Display ───────────────────────────────────────────────────────────────

    def _display_text(self, text):
        self._txt.config(state="normal")
        self._txt.delete("1.0", "end")
        self._txt.insert("1.0", text)
        self._txt.tag_add("center", "1.0", "end")
        self._txt.tag_add("future", "1.0", "end")
        self._txt.config(state="disabled")
        self._current_line = -1

    def _clear(self):
        self._stop_tracking()
        self._lyrics_raw = ""
        self._lrc_lines = []
        self._synced = False
        self._txt.config(state="normal")
        self._txt.delete("1.0", "end")
        self._txt.config(state="disabled")
        self._track_lbl.config(text="No track loaded")
        self._status.config(text="")

    def _apply_font(self):
        sz = self._font_size_var.get()
        self._txt.config(font=("Segoe UI", sz))
        self._txt.tag_configure("current", font=("Segoe UI Bold", sz))

    def _on_offset(self, *_):
        val = self._offset_var.get()
        self._off_lbl.config(text=f"{val:+.1f}s")

    # ── Karaoke tracking ─────────────────────────────────────────────────────

    def _start_tracking(self):
        if self._update_after is not None:
            return
        self._update_loop()

    def _stop_tracking(self):
        if self._update_after is not None:
            self.after_cancel(self._update_after)
            self._update_after = None

    def _update_loop(self):
        if self._synced and self._karaoke_var.get() and _audio.get_busy():
            pos = _audio.get_pos() + self._offset_var.get()
            times = [t for t, _ in self._lrc_lines]
            idx = bisect.bisect_right(times, pos) - 1
            idx = max(0, min(idx, len(self._lrc_lines) - 1))

            if idx != self._current_line:
                self._current_line = idx
                self._highlight_line(idx)

        self._update_after = self.after(LYRICS_UPDATE_MS, self._update_loop)

    def _highlight_line(self, idx):
        self._txt.config(state="normal")
        self._txt.tag_remove("current", "1.0", "end")
        self._txt.tag_remove("past", "1.0", "end")
        self._txt.tag_remove("future", "1.0", "end")

        total = len(self._lrc_lines)
        if idx > 0:
            self._txt.tag_add("past", "1.0", f"{idx}.0")
        self._txt.tag_add("current", f"{idx + 1}.0", f"{idx + 2}.0")
        if idx + 2 <= total:
            self._txt.tag_add("future", f"{idx + 2}.0", "end")

        # Auto-scroll to current line
        self._txt.see(f"{idx + 1}.0")
        self._txt.config(state="disabled")

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def refresh(self):
        if self._synced and self._karaoke_var.get():
            self._start_tracking()
        # Update track label
        path = self._get_current_track()
        if path:
            name = os.path.splitext(os.path.basename(path))[0]
            self._track_lbl.config(text=name)
