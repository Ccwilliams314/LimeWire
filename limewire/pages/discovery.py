"""DiscoveryPage — Music library scanner with BPM/key caching and harmonic mixing."""
import os, threading
import tkinter as tk
from tkinter import filedialog, messagebox
from concurrent.futures import ThreadPoolExecutor, as_completed

from limewire.core.theme import T
from limewire.core.constants import MAX_PLAYLIST_GEN, SP_SM, SP_LG
from limewire.core.config import ANALYSIS_CACHE_FILE, load_json, save_json
from limewire.ui.scroll_frame import ScrollFrame
from limewire.ui.widgets import (ClassicBtn, LimeBtn, OrangeBtn, GroupBox,
                                  ClassicEntry, ClassicCombo, ClassicListbox,
                                  ClassicProgress, PageSettingsPanel, GearButton)
from limewire.ui.toast import show_toast
from limewire.services.analysis import (
    analyze_bpm_key, key_to_camelot, get_harmonic_matches,
)


class DiscoveryPage(ScrollFrame):
    """Music library scanner with BPM/key caching and harmonic mixing."""
    def __init__(self, parent, app):
        super().__init__(parent); self.app = app; self._library = {}
        self._build(self.inner)

    def _build(self, p):
        # Library Scanner
        sg = GroupBox(p, "Music Library Scanner")
        sg.pack(fill="x", padx=10, pady=(10, 6))
        sr = tk.Frame(sg, bg=T.BG); sr.pack(fill="x")
        tk.Label(sr, text="Folder:", font=T.F_BOLD, bg=T.BG, fg=T.TEXT).pack(
            side="left", padx=(0, 6))
        self.lib_var = tk.StringVar(
            value=os.path.join(os.path.expanduser("~"), "Downloads", "LimeWire"))
        ClassicEntry(sr, self.lib_var, width=45).pack(
            side="left", fill="x", expand=True, ipady=2, padx=(0, 6))
        ClassicBtn(sr, "Browse...", self._browse_lib).pack(side="left", padx=(0, 6))
        LimeBtn(sr, "Scan Library", self._scan_library).pack(side="left")
        self._settings_panel = PageSettingsPanel(p, "discovery", self.app, [
            ("max_scan_files", "Max Scan Files", "int", 50000, {"min": 1000, "max": 200000}),
            ("cache_limit", "Cache Limit", "int", 5000, {"min": 500, "max": 50000}),
            ("analysis_workers", "Analysis Workers", "int", 4, {"min": 1, "max": 8}),
        ])
        self._gear = GearButton(sr, self._settings_panel)
        self._gear.pack(side="right")
        self.scan_status = tk.Label(
            sg,
            text="Scan a music folder to analyze BPM, key, and build a library index",
            font=T.F_SMALL, bg=T.BG, fg=T.TEXT_DIM, anchor="w")
        self.scan_status.pack(fill="x", pady=(4, 0))
        self.scan_prog = ClassicProgress(sg)
        self.scan_prog.pack(fill="x", pady=(2, 0))

        # Library View
        lg = GroupBox(p, "Library Analysis")
        lg.pack(fill="both", padx=10, pady=(0, 6), expand=True)
        cols_frame = tk.Frame(lg, bg=T.CARD_BG, bd=0); cols_frame.pack(fill="x")
        tk.Frame(lg, bg=T.CARD_BORDER, height=1).pack(fill="x")
        for col, w in [("File", 35), ("BPM", 8), ("Key", 12), ("Camelot", 8)]:
            tk.Label(cols_frame, text=col, font=T.F_BOLD, bg=T.CARD_BG, fg=T.TEXT,
                     width=w, anchor="w").pack(side="left")
        self.lib_frame, self.lib_lb = ClassicListbox(lg, height=10)
        self.lib_frame.pack(fill="both", expand=True)

        # Harmonic Mixing
        mg = GroupBox(p, "Harmonic Mixing")
        mg.pack(fill="x", padx=10, pady=(0, 6))
        mr = tk.Frame(mg, bg=T.BG); mr.pack(fill="x")
        OrangeBtn(mr, "Find Compatible Tracks", self._find_harmonic).pack(
            side="left", padx=(0, 6))
        ClassicBtn(mr, "Generate DJ Playlist", self._gen_playlist).pack(
            side="left", padx=(0, 6))
        ClassicBtn(mr, "Export Playlist (.m3u)", self._export_m3u).pack(
            side="left", padx=(0, 6))
        ClassicBtn(mr, "Export CSV", self._export_csv).pack(side="left")
        self.mix_status = tk.Label(
            mg,
            text="Select a track in the library, then find harmonically compatible tracks",
            font=T.F_SMALL, bg=T.BG, fg=T.TEXT_DIM, anchor="w")
        self.mix_status.pack(fill="x", pady=(4, 0))

        # Harmonic results
        self.harm_frame, self.harm_lb = ClassicListbox(mg, height=6)
        self.harm_frame.pack(fill="x", pady=(4, 0))

        # Smart Playlist Options
        spg = GroupBox(p, "Smart Playlist")
        spg.pack(fill="x", padx=10, pady=(0, 6))
        spf = tk.Frame(spg, bg=T.BG); spf.pack(fill="x")
        tk.Label(spf, text="Energy:", font=T.F_BODY, bg=T.BG, fg=T.TEXT).pack(
            side="left")
        self._energy_filter = tk.StringVar(value="All")
        ClassicCombo(spf, self._energy_filter,
                     ["All", "Low (<100 BPM)", "Medium (100-130)",
                      "High (130-160)", "Very High (160+)"],
                     width=18).pack(side="left", padx=SP_SM)
        tk.Label(spf, text="Sort:", font=T.F_BODY, bg=T.BG, fg=T.TEXT).pack(
            side="left", padx=(SP_LG, 0))
        self._sort_mode = tk.StringVar(value="Harmonic Flow")
        ClassicCombo(spf, self._sort_mode,
                     ["Harmonic Flow", "BPM Ramp Up", "BPM Ramp Down", "Key Groups"],
                     width=16).pack(side="left", padx=SP_SM)
        LimeBtn(spf, "Smart Generate", self._smart_playlist).pack(
            side="left", padx=SP_SM)
        OrangeBtn(spf, "Send to Player", self._send_to_player).pack(
            side="left", padx=SP_SM)

        # Playlist
        pg = GroupBox(p, "Generated Playlist")
        pg.pack(fill="x", padx=10, pady=(0, 10))
        self.pl_frame, self.pl_lb = ClassicListbox(pg, height=6)
        self.pl_frame.pack(fill="x")

    def _browse_lib(self):
        d = filedialog.askdirectory(initialdir=self.lib_var.get())
        if d:
            self.lib_var.set(d)

    # ── Scanning ──────────────────────────────────────────────────────────────
    def _scan_library(self):
        folder = self.lib_var.get()
        if not os.path.isdir(folder):
            messagebox.showinfo("LimeWire", "Select a valid folder."); return
        self.scan_status.config(text="Scanning...", fg=T.YELLOW)
        self.scan_prog.configure(value=0)
        threading.Thread(target=self._do_scan, args=(folder,), daemon=True).start()

    def _do_scan(self, folder):
        audio_exts = {".mp3", ".wav", ".flac", ".ogg", ".m4a", ".aac", ".opus"}
        # Recursive scan for large libraries
        files = []
        for root, dirs, fnames in os.walk(folder):
            for fn in fnames:
                if os.path.splitext(fn)[1].lower() in audio_exts:
                    files.append(os.path.join(root, fn))
            if len(files) >= 50000:
                break  # safety cap
        if not files:
            self.after(0, lambda: self.scan_status.config(
                text="No audio files found.", fg=T.RED))
            return
        self.after(0, lambda n=len(files): self.scan_status.config(
            text=f"Found {n} files, analyzing...", fg=T.YELLOW))
        # Load analysis cache (evict if too large)
        cache = load_json(ANALYSIS_CACHE_FILE, {})
        MAX_CACHE = 5000
        if len(cache) > MAX_CACHE:
            cache = dict(list(cache.items())[-MAX_CACHE:])
        self._library = {}; analyzed = 0; total = len(files)
        # Split into cached and uncached
        uncached = []
        for fp in files:
            try:
                mtime = str(os.path.getmtime(fp))
            except OSError:
                mtime = ""
            cache_key = f"{fp}|{mtime}"
            if cache_key in cache:
                self._library[fp] = cache[cache_key]
            else:
                uncached.append((fp, cache_key))
        # Parallel analysis for uncached files using thread pool
        if uncached:
            def _analyze_one(item):
                fp, cache_key = item
                bk = analyze_bpm_key(fp)
                bpm = bk.get("bpm"); key = bk.get("key", "")
                camelot = key_to_camelot(key) or ""
                entry = {"bpm": bpm, "key": key, "camelot": camelot,
                         "file": os.path.basename(fp)}
                return fp, cache_key, entry

            workers = min(4, os.cpu_count() or 2)
            with ThreadPoolExecutor(max_workers=workers) as pool:
                futures = {pool.submit(_analyze_one, item): item
                           for item in uncached}
                done = 0
                for fut in as_completed(futures):
                    try:
                        fp, cache_key, entry = fut.result()
                        self._library[fp] = entry
                        cache[cache_key] = entry; analyzed += 1
                    except Exception:
                        pass
                    done += 1
                    if done % 10 == 0 or done == len(uncached):
                        pct = int(((total - len(uncached) + done)
                                   / max(1, total)) * 100)
                        self.after(0, lambda p=pct, d=done:
                                   self.scan_prog.configure(value=p))
        save_json(ANALYSIS_CACHE_FILE, cache)
        cached = total - analyzed
        msg = (f"Scanned {len(self._library)} tracks "
               f"({analyzed} analyzed, {cached} cached)")
        self.after(0, lambda: (
            self.scan_prog.configure(value=100),
            self.scan_status.config(text=msg, fg=T.LIME_DK),
            self._render_library()))

    def _render_library(self):
        self.lib_lb.delete(0, "end")
        for fp, info in sorted(self._library.items(),
                                key=lambda x: x[1].get("bpm") or 0):
            bpm = f"{info['bpm']:.1f}" if info["bpm"] else "?"
            line = (f" {info['file'][:35]:35s} {bpm:>8s} "
                    f"{info['key']:12s} {info['camelot']:8s}")
            self.lib_lb.insert("end", line)

    def _get_selected_file(self):
        sel = self.lib_lb.curselection()
        if sel:
            files = sorted(self._library.keys(),
                           key=lambda x: self._library[x].get("bpm") or 0)
            if sel[0] < len(files):
                return files[sel[0]]
        return None

    # ── Harmonic matching ─────────────────────────────────────────────────────
    def _find_harmonic(self):
        fp = self._get_selected_file()
        if not fp:
            messagebox.showinfo("LimeWire",
                                "Select a track from the library first."); return
        info = self._library[fp]
        key = info.get("key", "")
        if not key:
            self.mix_status.config(
                text="Selected track has no key detected.", fg=T.RED); return
        lib_keys = {f: d["key"] for f, d in self._library.items()
                    if d.get("key") and f != fp}
        matches = get_harmonic_matches(key, lib_keys)
        self.harm_lb.delete(0, "end")
        for f, k, c, lvl in matches:
            bpm = self._library[f].get("bpm")
            bpm_s = f"{bpm:.1f}" if bpm else "?"
            tag = "\u2605" if lvl == "perfect" else "\u266A"
            self.harm_lb.insert(
                "end",
                f" {tag} {os.path.basename(f)[:30]:30s} {bpm_s:>8s} {k:12s} {c:6s}")
        self.mix_status.config(
            text=f"Found {len(matches)} compatible tracks for "
                 f"{info['camelot']} ({key})",
            fg=T.LIME_DK)

    # ── Playlist generation ───────────────────────────────────────────────────
    def _gen_playlist(self):
        if not self._library:
            messagebox.showinfo("LimeWire", "Scan a library first."); return
        fp = self._get_selected_file()
        if not fp:
            # Use first track as seed
            fp = next(iter(self._library))
        # Build playlist by harmonic progression
        playlist = [fp]; used = {fp}
        current = self._library[fp]
        for _ in range(min(MAX_PLAYLIST_GEN, len(self._library) - 1)):
            key = current.get("key", "")
            bpm = current.get("bpm") or 120
            lib_keys = {f: d["key"] for f, d in self._library.items()
                        if f not in used and d.get("key")}
            matches = get_harmonic_matches(key, lib_keys)
            if not matches:
                # Fallback: closest BPM
                remaining = [(f, d) for f, d in self._library.items()
                             if f not in used]
                if not remaining:
                    break
                remaining.sort(
                    key=lambda x: abs((x[1].get("bpm") or 120) - bpm))
                nxt = remaining[0][0]
            else:
                # Prefer similar BPM among harmonic matches
                matches.sort(
                    key=lambda x: abs(
                        (self._library[x[0]].get("bpm") or 120) - bpm))
                nxt = matches[0][0]
            playlist.append(nxt); used.add(nxt)
            current = self._library[nxt]
        self.pl_lb.delete(0, "end")
        for i, fp in enumerate(playlist):
            info = self._library[fp]
            bpm = f"{info['bpm']:.1f}" if info.get("bpm") else "?"
            c = info.get("camelot", "")
            self.pl_lb.insert(
                "end",
                f" {i + 1:3d}. {info['file'][:35]:35s} {bpm:>8s} {c:6s}")
        self._playlist_files = playlist
        self.mix_status.config(
            text=f"Generated {len(playlist)}-track harmonic playlist",
            fg=T.LIME_DK)

    # ── Export ────────────────────────────────────────────────────────────────
    def _export_m3u(self):
        if not hasattr(self, "_playlist_files") or not self._playlist_files:
            return
        path = filedialog.asksaveasfilename(
            defaultextension=".m3u", filetypes=[("M3U Playlist", "*.m3u")])
        if path:
            with open(path, "w", encoding="utf-8") as f:
                f.write("#EXTM3U\n")
                for fp in self._playlist_files:
                    info = self._library.get(fp, {})
                    dur = 0  # could compute if needed
                    f.write(f"#EXTINF:{dur},{info.get('file', '')}\n{fp}\n")
            self.mix_status.config(
                text=f"Exported: {os.path.basename(path)}", fg=T.LIME_DK)

    def _export_csv(self):
        """Export library analysis results to CSV."""
        if not self._library:
            show_toast(self.app, "Scan a library first", "warning"); return
        path = filedialog.asksaveasfilename(
            defaultextension=".csv", filetypes=[("CSV", "*.csv")],
            initialfile="library_analysis.csv")
        if not path:
            return
        try:
            import csv
            with open(path, "w", newline="", encoding="utf-8") as f:
                w = csv.writer(f)
                w.writerow(["File", "Path", "BPM", "Key", "Camelot"])
                for fp, info in sorted(self._library.items(),
                                        key=lambda x: x[1].get("bpm") or 0):
                    bpm = f"{info['bpm']:.1f}" if info.get("bpm") else ""
                    w.writerow([info.get("file", ""), fp, bpm,
                                info.get("key", ""), info.get("camelot", "")])
            show_toast(self.app,
                       f"Exported {len(self._library)} tracks to CSV", "success")
        except Exception as e:
            show_toast(self.app, f"CSV export failed: {str(e)[:50]}", "error")

    def _send_to_player(self):
        """Send generated playlist to Player tab."""
        if not hasattr(self, "_playlist_files") or not self._playlist_files:
            return
        pp = self.app.pages.get("player")
        if not pp:
            return
        added = 0
        for fp in self._playlist_files:
            if fp not in pp._playlist_set:
                pp._playlist.append(fp); pp._playlist_set.add(fp)
                title, artist, dur_str = pp._get_track_meta(fp)
                pp.plb.insert("", "end",
                              iid=str(len(pp._playlist) - 1),
                              values=(title, artist, dur_str))
                added += 1
        if added:
            show_toast(self.app, f"Added {added} tracks to Player", "success")
        self.app._show_tab("player")

    # ── Smart playlist ────────────────────────────────────────────────────────
    def _smart_playlist(self):
        if not self._library:
            messagebox.showinfo("LimeWire", "Scan a library first."); return
        # Filter by energy level
        ef = self._energy_filter.get()
        pool = dict(self._library)
        if "Low" in ef:
            pool = {f: d for f, d in pool.items()
                    if (d.get("bpm") or 120) < 100}
        elif "Medium" in ef:
            pool = {f: d for f, d in pool.items()
                    if 100 <= (d.get("bpm") or 120) < 130}
        elif "High" in ef and "Very" not in ef:
            pool = {f: d for f, d in pool.items()
                    if 130 <= (d.get("bpm") or 120) < 160}
        elif "Very" in ef:
            pool = {f: d for f, d in pool.items()
                    if (d.get("bpm") or 120) >= 160}
        if not pool:
            self.mix_status.config(
                text="No tracks match energy filter", fg=T.YELLOW); return
        # Sort
        sm = self._sort_mode.get()
        items = list(pool.items())
        if "Ramp Up" in sm:
            items.sort(key=lambda x: x[1].get("bpm") or 120)
        elif "Ramp Down" in sm:
            items.sort(key=lambda x: -(x[1].get("bpm") or 120))
        elif "Key Groups" in sm:
            # Group by major/minor then by Camelot number
            def _key_sort(x):
                cam = x[1].get("camelot", "")
                num = 0; letter = "A"
                if cam:
                    try:
                        num = int(cam[:-1]); letter = cam[-1]
                    except Exception:
                        pass
                return (letter, num)
            items.sort(key=_key_sort)
        else:
            # Harmonic Flow: use existing logic but with filtered pool
            fp = next(iter(pool))
            playlist = [fp]; used = {fp}; current = pool[fp]
            for _ in range(min(MAX_PLAYLIST_GEN, len(pool) - 1)):
                key = current.get("key", "")
                bpm = current.get("bpm") or 120
                lib_keys = {f: d["key"] for f, d in pool.items()
                            if f not in used and d.get("key")}
                matches = get_harmonic_matches(key, lib_keys)
                if not matches:
                    remaining = [(f, d) for f, d in pool.items()
                                 if f not in used]
                    if not remaining:
                        break
                    remaining.sort(
                        key=lambda x: abs((x[1].get("bpm") or 120) - bpm))
                    nxt = remaining[0][0]
                else:
                    matches.sort(
                        key=lambda x: abs(
                            (pool[x[0]].get("bpm") or 120) - bpm))
                    nxt = matches[0][0]
                playlist.append(nxt); used.add(nxt); current = pool[nxt]
            items = [(f, pool[f]) for f in playlist]
        self.pl_lb.delete(0, "end")
        self._playlist_files = [f for f, _ in items]
        for i, (fp, info) in enumerate(items):
            bpm = f"{info['bpm']:.1f}" if info.get("bpm") else "?"
            c = info.get("camelot", "")
            self.pl_lb.insert(
                "end",
                f" {i + 1:3d}. {info['file'][:35]:35s} {bpm:>8s} {c:6s}")
        self.mix_status.config(
            text=f"Smart playlist: {len(items)} tracks ({ef}, {sm})",
            fg=T.LIME_DK)
