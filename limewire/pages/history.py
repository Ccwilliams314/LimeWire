"""HistoryPage — Browse and manage download history with filtering."""
import os
import tkinter as tk
from tkinter import messagebox

import mutagen

from limewire.core.theme import T
from limewire.core.config import save_json, load_json, HISTORY_FILE, ANALYSIS_CACHE_FILE
from limewire.ui.scroll_frame import ScrollFrame
from limewire.ui.widgets import (ClassicBtn, LimeBtn, GroupBox,
                                  ClassicEntry, ClassicListbox, HSep,
                                  PageSettingsPanel, GearButton)
from limewire.ui.toast import show_toast
from limewire.utils.helpers import sanitize_filename, open_folder


class HistoryPage(ScrollFrame):
    """Browse and manage download history with filtering."""
    def __init__(self, parent, app):
        super().__init__(parent); self.app = app; self._build(self.inner)

    def _build(self, p):
        hdr = tk.Frame(p, bg=T.BG, padx=10, pady=8); hdr.pack(fill="x")
        tk.Label(hdr, text="Download History", font=T.F_TITLE, bg=T.BG,
                 fg=T.TEXT).pack(side="left")
        self._settings_panel = PageSettingsPanel(p, "history", self.app, [
            ("history_limit", "Max Entries Shown", "int", 300, {"min": 100, "max": 2000}),
            ("sort_by", "Sort By", "choice", "date_desc", {"choices": ["date_desc", "date_asc", "title", "source"]}),
        ])
        self._gear = GearButton(hdr, self._settings_panel)
        self._gear.pack(side="right")
        ClassicBtn(hdr, "Open File", self._open_file).pack(side="right", padx=(4, 0))
        ClassicBtn(hdr, "Redownload", self._redown_sel).pack(side="right", padx=(4, 0))
        ClassicBtn(hdr, "Batch Rename", self._batch_rename).pack(
            side="right", padx=(4, 0))
        ClassicBtn(hdr, "Clear", self._clear).pack(side="right")
        # Search/filter bar
        sf = tk.Frame(p, bg=T.BG, padx=10); sf.pack(fill="x", pady=(4, 0))
        tk.Label(sf, text="Filter:", font=T.F_BOLD, bg=T.BG, fg=T.TEXT).pack(
            side="left", padx=(0, 6))
        self.filter_var = tk.StringVar()
        self.filter_e = ClassicEntry(sf, self.filter_var, width=30)
        self.filter_e.pack(side="left", fill="x", expand=True, ipady=2, padx=(0, 6))
        self.filter_var.trace_add("write", lambda *_: self.refresh())
        self.filter_count = tk.Label(sf, text="", font=T.F_SMALL, bg=T.BG,
                                     fg=T.TEXT_DIM)
        self.filter_count.pack(side="left")
        HSep(p)
        self.hf, self.hlb = ClassicListbox(p, height=20, selectmode="browse")
        self.hf.pack(fill="both", expand=True, padx=10, pady=(6, 10))
        self.hlb.bind("<Double-Button-1>", lambda e: self._redown_sel())

    def refresh(self):
        self.hlb.delete(0, "end")
        self._filtered_indices = []  # maps listbox index -> history index
        query = (self.filter_var.get().strip().lower()
                 if hasattr(self, "filter_var") else "")
        for i, entry in enumerate(self.app.history[:300]):
            st = entry.get("status", ""); ico = "OK" if st == "done" else "XX"
            title = entry.get("title", "")[:35]; src = entry.get("source", "")
            fmt_s = entry.get("format", "").upper(); date = entry.get("date", "")
            fp = entry.get("filepath", "")
            line = f" {ico:3s} {title:35s} {src:10s} {fmt_s:5s} {date:16s}"
            if fp:
                line += f" [{os.path.basename(fp)[:20]}]"
            if query and query not in line.lower():
                continue
            self.hlb.insert("end", line); self._filtered_indices.append(i)
        shown = len(self._filtered_indices)
        if hasattr(self, "filter_count"):
            self.filter_count.config(
                text=f"{shown}/{len(self.app.history)}" if query
                else f"{shown} total")

    def _get_selected_entry(self):
        sel = self.hlb.curselection()
        if sel and sel[0] < len(self._filtered_indices):
            idx = self._filtered_indices[sel[0]]
            if idx < len(self.app.history):
                return self.app.history[idx]
        return None

    def _clear(self):
        if messagebox.askyesno("LimeWire", "Clear all?"):
            self.app.history = []; save_json(HISTORY_FILE, []); self.refresh()

    def _redown_sel(self):
        entry = self._get_selected_entry()
        if entry:
            url = entry.get("url", "")
            if url:
                sp = self.app.pages["search"]
                sp.url_var.set(url); self.app._show_tab("search")

    def _open_file(self):
        entry = self._get_selected_entry()
        if not entry:
            return
        fp = entry.get("filepath", "")
        if fp and os.path.exists(fp):
            open_folder(os.path.dirname(fp))
        elif entry.get("folder"):
            open_folder(entry["folder"])

    def _batch_rename(self):
        """Batch rename downloaded files using a pattern template."""
        # Collect files that exist
        files = []
        for entry in self.app.history:
            fp = entry.get("filepath", "")
            if fp and os.path.exists(fp):
                files.append((entry, fp))
        if not files:
            show_toast(self.app, "No existing files in history", "warning"); return
        dlg = tk.Toplevel(self); dlg.title("Batch Rename"); dlg.geometry("550x420")
        dlg.configure(bg=T.BG); dlg.transient(self); dlg.grab_set()
        tk.Label(dlg, text="Rename Pattern", font=T.F_HEADER, bg=T.BG,
                 fg=T.TEXT).pack(pady=(10, 4))
        tk.Label(dlg,
                 text="Tokens: {title} {artist} {bpm} {key} {date} {n} {ext}",
                 font=T.F_SMALL, bg=T.BG, fg=T.TEXT_DIM).pack()
        pat_var = tk.StringVar(value="{title} - {artist}.{ext}")
        ClassicEntry(dlg, pat_var, width=50).pack(padx=20, pady=6, ipady=2)
        tk.Label(dlg, text="Preview (first 8 files):", font=T.F_BOLD, bg=T.BG,
                 fg=T.TEXT).pack(anchor="w", padx=20)
        preview_lb = tk.Listbox(dlg, font=T.F_MONO, bg=T.INPUT_BG, fg=T.TEXT,
                                height=8, relief="flat", bd=1)
        preview_lb.pack(fill="both", expand=True, padx=20, pady=4)

        def _preview(*_):
            preview_lb.delete(0, "end")
            pat = pat_var.get()
            for i, (entry, fp) in enumerate(files[:8]):
                ext = os.path.splitext(fp)[1].lstrip(".")
                title = entry.get("title", "Unknown")[:40]
                artist = ""
                try:
                    mf = mutagen.File(fp)
                    if mf and hasattr(mf, 'tags') and mf.tags:
                        for k in ["TPE1", "artist", "ARTIST", "\u00a9ART"]:
                            if k in mf.tags:
                                v = mf.tags[k]
                                artist = (str(v[0]) if isinstance(v, list)
                                          else str(v))
                                break
                except Exception: pass
                # Check analysis cache for BPM/key
                bpm = ""; key = ""
                cache = load_json(ANALYSIS_CACHE_FILE, {})
                ckey = (f"{fp}|{os.path.getmtime(fp):.0f}"
                        if os.path.exists(fp) else "")
                if ckey in cache:
                    bpm = (str(int(cache[ckey].get("bpm", 0)))
                           if cache[ckey].get("bpm") else "")
                    key = cache[ckey].get("key", "")
                date = entry.get("date", "")[:10]
                new_name = pat.replace("{title}", title)
                new_name = new_name.replace("{artist}", artist or "Unknown")
                new_name = new_name.replace("{bpm}", bpm or "0")
                new_name = new_name.replace("{key}", key or "?")
                new_name = new_name.replace("{date}", date)
                new_name = new_name.replace("{n}", str(i + 1))
                new_name = new_name.replace("{ext}", ext)
                # Sanitize
                new_name = sanitize_filename(new_name)
                old = os.path.basename(fp)
                preview_lb.insert("end", f"{old[:25]:25s} \u2192 {new_name}")
        pat_var.trace_add("write", _preview); _preview()

        def _apply():
            renamed = 0
            for i, (entry, fp) in enumerate(files):
                ext = os.path.splitext(fp)[1].lstrip(".")
                title = entry.get("title", "Unknown")[:40]
                artist = ""; bpm = ""; key = ""
                try:
                    mf = mutagen.File(fp)
                    if mf and hasattr(mf, 'tags') and mf.tags:
                        for k in ["TPE1", "artist", "ARTIST", "\u00a9ART"]:
                            if k in mf.tags:
                                v = mf.tags[k]
                                artist = (str(v[0]) if isinstance(v, list)
                                          else str(v))
                                break
                except Exception: pass
                cache = load_json(ANALYSIS_CACHE_FILE, {})
                ckey = (f"{fp}|{os.path.getmtime(fp):.0f}"
                        if os.path.exists(fp) else "")
                if ckey in cache:
                    bpm = (str(int(cache[ckey].get("bpm", 0)))
                           if cache[ckey].get("bpm") else "")
                    key = cache[ckey].get("key", "")
                date = entry.get("date", "")[:10]; pat = pat_var.get()
                new_name = pat.replace("{title}", title)
                new_name = new_name.replace("{artist}", artist or "Unknown")
                new_name = new_name.replace("{bpm}", bpm or "0")
                new_name = new_name.replace("{key}", key or "?")
                new_name = new_name.replace("{date}", date)
                new_name = new_name.replace("{n}", str(i + 1))
                new_name = new_name.replace("{ext}", ext)
                new_name = sanitize_filename(new_name)
                parent_dir = os.path.dirname(os.path.abspath(fp))
                new_path = os.path.join(parent_dir, new_name)
                # Prevent path traversal
                if os.path.dirname(os.path.abspath(new_path)) != parent_dir:
                    continue
                if new_path != fp and not os.path.exists(new_path):
                    try:
                        os.rename(fp, new_path); entry["filepath"] = new_path
                        renamed += 1
                    except Exception: pass
            save_json(HISTORY_FILE, self.app.history)
            dlg.destroy(); self.refresh()
            show_toast(self.app, f"Renamed {renamed}/{len(files)} files", "success")
        LimeBtn(dlg, "Rename All", _apply).pack(pady=8)
