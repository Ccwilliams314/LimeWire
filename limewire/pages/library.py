"""LibraryPage — Music library with tag editing, smart playlists, and search."""
import os, csv, threading, datetime
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

import mutagen

from limewire.core.theme import T
from limewire.core.constants import LIBRARY_SCAN_EXTS, SP_SM, SP_LG
from limewire.core.config import (
    load_json, save_json, LIBRARY_FILE, SMART_PLAYLISTS_FILE,
    ANALYSIS_CACHE_FILE,
)
from limewire.ui.scroll_frame import ScrollFrame
from limewire.ui.widgets import (
    ClassicBtn, LimeBtn, OrangeBtn, GroupBox, ClassicEntry,
    ClassicCombo, ClassicProgress,
)
from limewire.ui.toast import show_toast
from limewire.services.cover_art import extract_cover_art
from limewire.utils.helpers import fmt_duration

try:
    from PIL import Image, ImageTk
except Exception:
    Image = ImageTk = None


class LibraryPage(ScrollFrame):
    def __init__(self, parent, app):
        super().__init__(parent)
        self.app = app
        self._library = []       # list of dicts
        self._filtered = []
        self._sort_col = "title"
        self._sort_asc = True
        self._art_photo = None
        self._scan_thread = None
        self._build(self.inner)
        # Load persisted library
        saved = load_json(LIBRARY_FILE, [])
        if saved:
            self._library = saved
            self._filtered = list(saved)
            self.after(100, self._refresh_tree)

    # ── UI ────────────────────────────────────────────────────────────────────

    def _build(self, p):
        # Scanner
        sg = GroupBox(p, "Scan Library")
        sg.pack(fill="x", padx=10, pady=(10, 6))
        sr = tk.Frame(sg, bg=T.BG)
        sr.pack(fill="x")
        self._folder_var = tk.StringVar()
        ClassicEntry(sr, self._folder_var, width=50).pack(side="left", fill="x", expand=True, padx=(0, 6))
        ClassicBtn(sr, "Browse", self._browse_folder).pack(side="left", padx=(0, 6))
        LimeBtn(sr, "Scan", self._scan_library).pack(side="left")

        self._prog = ClassicProgress(sg, thin=True)
        self._prog.pack(fill="x", pady=(4, 0))
        self._scan_lbl = tk.Label(sg, text="", font=T.F_SMALL, bg=T.BG, fg=T.TEXT_DIM)
        self._scan_lbl.pack(fill="x")

        # Search / Filter
        fg = GroupBox(p, "Search & Filter")
        fg.pack(fill="x", padx=10, pady=(0, 6))
        fr = tk.Frame(fg, bg=T.BG)
        fr.pack(fill="x")

        tk.Label(fr, text="Search:", font=T.F_SMALL, bg=T.BG, fg=T.TEXT).pack(side="left")
        self._search_var = tk.StringVar()
        ClassicEntry(fr, self._search_var, width=25).pack(side="left", padx=(4, 12))

        tk.Label(fr, text="Genre:", font=T.F_SMALL, bg=T.BG, fg=T.TEXT).pack(side="left")
        self._genre_var = tk.StringVar(value="All")
        self._genre_cb = ClassicCombo(fr, self._genre_var, ["All"], width=12)
        self._genre_cb.pack(side="left", padx=(4, 12))

        tk.Label(fr, text="BPM:", font=T.F_SMALL, bg=T.BG, fg=T.TEXT).pack(side="left")
        self._bpm_min_var = tk.StringVar()
        self._bpm_max_var = tk.StringVar()
        ClassicEntry(fr, self._bpm_min_var, width=5).pack(side="left", padx=(4, 2))
        tk.Label(fr, text="-", bg=T.BG, fg=T.TEXT).pack(side="left")
        ClassicEntry(fr, self._bpm_max_var, width=5).pack(side="left", padx=(2, 12))

        tk.Label(fr, text="Key:", font=T.F_SMALL, bg=T.BG, fg=T.TEXT).pack(side="left")
        self._key_var = tk.StringVar(value="All")
        ClassicCombo(fr, self._key_var, ["All"], width=10).pack(side="left", padx=(4, 12))

        ClassicBtn(fr, "Filter", self._apply_filter).pack(side="left")

        # Treeview
        tg = GroupBox(p, "Library")
        tg.pack(fill="both", expand=True, padx=10, pady=(0, 6))

        cols = ("title", "artist", "album", "genre", "duration", "bpm", "key")
        self._tree = ttk.Treeview(tg, columns=cols, show="headings", height=12,
                                  selectmode="extended")
        widths = {"title": 250, "artist": 150, "album": 150, "genre": 80,
                  "duration": 60, "bpm": 50, "key": 60}
        for c in cols:
            self._tree.heading(c, text=c.title(),
                               command=lambda col=c: self._sort_by(col))
            anchor = "e" if c in ("duration", "bpm") else "w"
            self._tree.column(c, width=widths.get(c, 100), anchor=anchor)

        sb = ttk.Scrollbar(tg, orient="vertical", command=self._tree.yview)
        self._tree.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        self._tree.pack(fill="both", expand=True)
        self._tree.bind("<<TreeviewSelect>>", self._on_select)
        self._tree.bind("<Button-3>", self._context_menu)
        self._tree.bind("<Delete>", lambda e: self._remove_selected())

        self._count_lbl = tk.Label(tg, text="0 tracks", font=T.F_SMALL,
                                   bg=T.BG, fg=T.TEXT_DIM, anchor="w")
        self._count_lbl.pack(fill="x")

        # Tag editor
        eg = GroupBox(p, "Tag Editor")
        eg.pack(fill="x", padx=10, pady=(0, 6))
        ef = tk.Frame(eg, bg=T.BG)
        ef.pack(fill="x")

        # Art display (left)
        self._art_lbl = tk.Label(ef, bg=T.CANVAS_BG, width=20, height=10)
        self._art_lbl.pack(side="left", padx=(0, 10))

        # Tag fields (right)
        tf = tk.Frame(ef, bg=T.BG)
        tf.pack(side="left", fill="x", expand=True)

        self._edit_vars = {}
        for field in ("title", "artist", "album", "genre", "date"):
            row = tk.Frame(tf, bg=T.BG)
            row.pack(fill="x", pady=1)
            tk.Label(row, text=f"{field.title()}:", font=T.F_SMALL, bg=T.BG,
                     fg=T.TEXT, width=8, anchor="e").pack(side="left")
            v = tk.StringVar()
            ClassicEntry(row, v, width=40).pack(side="left", padx=(4, 0))
            self._edit_vars[field] = v

        btn_row = tk.Frame(tf, bg=T.BG)
        btn_row.pack(fill="x", pady=(4, 0))
        LimeBtn(btn_row, "Save Tags", self._save_tags).pack(side="left", padx=(0, 6))

        # Actions
        ag = GroupBox(p, "Actions")
        ag.pack(fill="x", padx=10, pady=(0, 10))
        ar = tk.Frame(ag, bg=T.BG)
        ar.pack(fill="x")
        LimeBtn(ar, "Send to Player", self._send_to_player).pack(side="left", padx=(0, 6))
        ClassicBtn(ar, "Export CSV", self._export_csv).pack(side="left")

    # ── Scanning ──────────────────────────────────────────────────────────────

    def _browse_folder(self):
        d = filedialog.askdirectory()
        if d:
            self._folder_var.set(d)

    def _scan_library(self):
        folder = self._folder_var.get()
        if not folder or not os.path.isdir(folder):
            show_toast(self.app, "Select a valid folder", "warning")
            return
        if self._scan_thread and self._scan_thread.is_alive():
            return
        self._library = []
        self._filtered = []
        self._refresh_tree()
        self._prog["value"] = 0
        self._scan_lbl.config(text="Scanning...", fg=T.YELLOW)

        def _do():
            files = []
            for root, _, fnames in os.walk(folder):
                for fn in fnames:
                    if os.path.splitext(fn)[1].lower() in LIBRARY_SCAN_EXTS:
                        files.append(os.path.join(root, fn))

            total = len(files)
            cache = load_json(ANALYSIS_CACHE_FILE, {})
            batch = []

            for i, fp in enumerate(files):
                entry = self._read_metadata(fp, cache)
                batch.append(entry)
                if len(batch) >= 50 or i == total - 1:
                    chunk = list(batch)
                    pct = int((i + 1) / max(1, total) * 100)
                    self.after(0, lambda c=chunk, p=pct, t=total:
                               self._on_scan_batch(c, p, t))
                    batch = []

            self.after(0, self._on_scan_done)

        self._scan_thread = threading.Thread(target=_do, daemon=True)
        self._scan_thread.start()

    def _read_metadata(self, fp, cache=None):
        entry = {
            "path": fp,
            "title": os.path.splitext(os.path.basename(fp))[0],
            "artist": "", "album": "", "genre": "",
            "duration": "", "bpm": "", "key": "", "date": "",
        }
        try:
            mf = mutagen.File(fp, easy=True)
            if mf:
                entry["title"] = (mf.get("title") or [entry["title"]])[0]
                entry["artist"] = (mf.get("artist") or [""])[0]
                entry["album"] = (mf.get("album") or [""])[0]
                entry["genre"] = (mf.get("genre") or [""])[0]
                entry["date"] = (mf.get("date") or [""])[0]
                if hasattr(mf, "info") and hasattr(mf.info, "length"):
                    entry["duration"] = fmt_duration(mf.info.length)
        except Exception:
            pass
        # Check analysis cache for BPM/key
        if cache and fp in cache:
            c = cache[fp]
            entry["bpm"] = str(int(c["bpm"])) if c.get("bpm") else ""
            entry["key"] = c.get("key", "")
        return entry

    def _on_scan_batch(self, chunk, pct, total):
        self._library.extend(chunk)
        self._filtered = list(self._library)
        self._prog["value"] = pct
        self._scan_lbl.config(text=f"Scanned {len(self._library)} / {total}")
        self._refresh_tree()

    def _on_scan_done(self):
        self._prog["value"] = 100
        n = len(self._library)
        self._scan_lbl.config(text=f"Done — {n} tracks", fg=T.LIME_DK)
        self._update_genre_list()
        save_json(LIBRARY_FILE, self._library)

    # ── Treeview ──────────────────────────────────────────────────────────────

    def _refresh_tree(self):
        self._tree.delete(*self._tree.get_children())
        for i, entry in enumerate(self._filtered):
            self._tree.insert("", "end", iid=str(i), values=(
                entry.get("title", ""), entry.get("artist", ""),
                entry.get("album", ""), entry.get("genre", ""),
                entry.get("duration", ""), entry.get("bpm", ""),
                entry.get("key", ""),
            ))
        self._count_lbl.config(text=f"{len(self._filtered)} tracks")

    def _sort_by(self, col):
        if self._sort_col == col:
            self._sort_asc = not self._sort_asc
        else:
            self._sort_col = col
            self._sort_asc = True

        def sort_key(e):
            v = e.get(col, "")
            if col == "bpm":
                try: return float(v)
                except Exception: return 0
            return str(v).lower()

        self._filtered.sort(key=sort_key, reverse=not self._sort_asc)
        self._refresh_tree()

    def _on_select(self, event=None):
        sel = self._tree.selection()
        if not sel:
            return
        idx = int(sel[0])
        if idx >= len(self._filtered):
            return
        entry = self._filtered[idx]

        # Populate tag editor
        for field, var in self._edit_vars.items():
            var.set(entry.get(field, ""))

        # Load cover art
        self._load_art(entry.get("path", ""))

    def _load_art(self, path):
        if not path or not Image:
            return
        try:
            img = extract_cover_art(path)
            if img:
                if isinstance(img, str) and os.path.isfile(img):
                    img = Image.open(img)
                if hasattr(img, "resize"):
                    img = img.resize((120, 120), Image.LANCZOS)
                    self._art_photo = ImageTk.PhotoImage(img)
                    self._art_lbl.config(image=self._art_photo)
                    return
        except Exception:
            pass
        self._art_lbl.config(image="")

    # ── Tag editing ───────────────────────────────────────────────────────────

    def _save_tags(self):
        sel = self._tree.selection()
        if not sel:
            show_toast(self.app, "Select a track first", "warning")
            return
        idx = int(sel[0])
        if idx >= len(self._filtered):
            return
        entry = self._filtered[idx]
        path = entry.get("path", "")
        try:
            audio = mutagen.File(path, easy=True)
            if audio is None:
                show_toast(self.app, "Cannot write tags to this format", "warning")
                return
            for field, var in self._edit_vars.items():
                val = var.get()
                if val:
                    audio[field] = val
                elif field in audio:
                    del audio[field]
            audio.save()
            # Update in-memory
            for field, var in self._edit_vars.items():
                entry[field] = var.get()
            self._refresh_tree()
            save_json(LIBRARY_FILE, self._library)
            show_toast(self.app, "Tags saved", "success")
        except Exception as e:
            show_toast(self.app, f"Error: {e}", "error")

    # ── Filter ────────────────────────────────────────────────────────────────

    def _apply_filter(self):
        search = self._search_var.get().lower().strip()
        genre = self._genre_var.get()
        key = self._key_var.get()
        bpm_min = self._bpm_min_var.get()
        bpm_max = self._bpm_max_var.get()

        self._filtered = []
        for e in self._library:
            if search:
                haystack = f"{e.get('title','')} {e.get('artist','')} {e.get('album','')}".lower()
                if search not in haystack:
                    continue
            if genre != "All" and e.get("genre", "") != genre:
                continue
            if key != "All" and e.get("key", "") != key:
                continue
            if bpm_min:
                try:
                    if float(e.get("bpm", 0) or 0) < float(bpm_min):
                        continue
                except ValueError:
                    pass
            if bpm_max:
                try:
                    if float(e.get("bpm", 0) or 0) > float(bpm_max):
                        continue
                except ValueError:
                    pass
            self._filtered.append(e)

        self._refresh_tree()

    def _update_genre_list(self):
        genres = sorted({e.get("genre", "") for e in self._library if e.get("genre")})
        self._genre_cb.config(values=["All"] + genres)

    # ── Context menu ──────────────────────────────────────────────────────────

    def _context_menu(self, event):
        sel = self._tree.selection()
        if not sel:
            return
        menu = tk.Menu(self, tearoff=0)
        menu.add_command(label="Play", command=self._play_selected)
        menu.add_command(label="Add to Player", command=self._send_to_player)
        menu.add_separator()
        menu.add_command(label="Show in Folder", command=self._show_in_folder)
        menu.add_command(label="Remove from Library", command=self._remove_selected)
        menu.post(event.x_root, event.y_root)

    def _play_selected(self):
        sel = self._tree.selection()
        if not sel:
            return
        idx = int(sel[0])
        if idx >= len(self._filtered):
            return
        path = self._filtered[idx].get("path", "")
        pp = self.app.pages.get("player")
        if pp and path:
            pp._addf_paths([path])
            pp._cur = len(pp._playlist) - 1
            pp._load()

    def _send_to_player(self):
        sel = self._tree.selection()
        if not sel:
            show_toast(self.app, "Select tracks first", "warning")
            return
        pp = self.app.pages.get("player")
        if not pp:
            return
        paths = []
        for s in sel:
            idx = int(s)
            if idx < len(self._filtered):
                paths.append(self._filtered[idx].get("path", ""))
        paths = [p for p in paths if p]
        if paths:
            pp._addf_paths(paths)
            show_toast(self.app, f"Added {len(paths)} tracks to Player", "success")

    def _show_in_folder(self):
        sel = self._tree.selection()
        if not sel:
            return
        idx = int(sel[0])
        if idx >= len(self._filtered):
            return
        path = self._filtered[idx].get("path", "")
        if path:
            folder = os.path.dirname(path)
            from limewire.utils.helpers import open_folder
            open_folder(folder)

    def _remove_selected(self):
        sel = self._tree.selection()
        if not sel:
            return
        indices = sorted([int(s) for s in sel], reverse=True)
        for idx in indices:
            if idx < len(self._filtered):
                entry = self._filtered[idx]
                self._filtered.pop(idx)
                if entry in self._library:
                    self._library.remove(entry)
        self._refresh_tree()
        save_json(LIBRARY_FILE, self._library)

    # ── Export ────────────────────────────────────────────────────────────────

    def _export_csv(self):
        if not self._filtered:
            show_toast(self.app, "No tracks to export", "warning")
            return
        path = filedialog.asksaveasfilename(
            defaultextension=".csv", filetypes=[("CSV", "*.csv")])
        if not path:
            return
        try:
            fields = ["title", "artist", "album", "genre", "duration", "bpm", "key", "path"]
            with open(path, "w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
                writer.writeheader()
                for entry in self._filtered:
                    writer.writerow(entry)
            show_toast(self.app, f"Exported {len(self._filtered)} tracks", "success")
        except Exception as e:
            show_toast(self.app, f"Error: {e}", "error")

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def refresh(self):
        pass
