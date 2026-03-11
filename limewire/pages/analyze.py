"""AnalyzePage -- Audio analysis: BPM, key, loudness, waveform, Shazam/MusicBrainz identification."""

import os, threading, json, re, subprocess
import tkinter as tk
from tkinter import filedialog, messagebox
from io import BytesIO

import mutagen
from mutagen.id3 import TIT2, TPE1, TBPM, TKEY, TCON

from limewire.core.theme import T, _lerp_color
from limewire.core.constants import WAVEFORM_W, WAVEFORM_H, SP_SM, SP_XS, SP_LG
from limewire.core.config import save_json
from limewire.core.deps import (
    HAS_SHAZAM, HAS_NOISEREDUCE, HAS_PEDALBOARD, HAS_FFMPEG, HAS_LYRICS,
)
from limewire.ui.scroll_frame import ScrollFrame
from limewire.ui.widgets import (
    ClassicBtn, LimeBtn, OrangeBtn, GroupBox,
    ClassicEntry, ClassicCombo, ClassicCheck, ClassicProgress, HSep,
)
from limewire.ui.toast import show_toast
from limewire.utils.helpers import fmt_duration
from limewire.services.analysis import (
    analyze_bpm_key, analyze_loudness, reduce_noise,
)
from limewire.services.audio_processing import generate_waveform_data
from limewire.services.metadata import (
    identify_shazam, search_shazam, lookup_musicbrainz,
    lookup_apple_music, identify_acoustid, lookup_lyrics,
)
from limewire.services.cover_art import extract_cover_art
from limewire.services.dj_integrations import (
    write_serato_tags, add_to_serato_crate, find_fl_studio,
    open_in_fl_studio, key_to_camelot, key_to_serato_tkey,
)


class AnalyzePage(ScrollFrame):
    """Audio analysis: BPM, key, loudness, waveform, Shazam/MusicBrainz identification."""

    def __init__(self, parent, app):
        super().__init__(parent)
        self.app = app
        self._build(self.inner)

    def _build(self, p):
        # File selector
        fg = GroupBox(p, "Audio File")
        fg.pack(fill="x", padx=10, pady=(10, 6))
        fr = tk.Frame(fg, bg=T.BG)
        fr.pack(fill="x")
        self.file_var = tk.StringVar()
        ClassicEntry(fr, self.file_var, width=55).pack(side="left", fill="x", expand=True, ipady=2, padx=(0, 8))
        ClassicBtn(fr, "Browse...", self._browse).pack(side="left", padx=(0, 6))
        LimeBtn(fr, "Analyze All", self._run_all).pack(side="left")

        # Waveform display
        wg = GroupBox(p, "Waveform")
        wg.pack(fill="x", padx=10, pady=(0, 6))
        self.wave_cv = tk.Canvas(wg, bg=T.CANVAS_BG, height=80, relief="flat", bd=0,
                                  highlightthickness=1, highlightbackground=T.CARD_BORDER)
        self.wave_cv.pack(fill="x")

        # Results grid
        rg = GroupBox(p, "Analysis Results")
        rg.pack(fill="x", padx=10, pady=(0, 6))
        self.results_frame = tk.Frame(rg, bg=T.BG)
        self.results_frame.pack(fill="x")
        # Pre-create result labels
        self._res = {}
        for label in ["BPM", "Key", "Camelot", "Loudness (LUFS)", "True Peak", "Duration", "Sample Rate", "File Size"]:
            r = tk.Frame(self.results_frame, bg=T.BG)
            r.pack(fill="x", pady=2)
            tk.Label(r, text=f"{label}:", font=T.F_BOLD, bg=T.BG, fg=T.TEXT, width=16, anchor="w").pack(side="left")
            v = tk.Label(r, text="--", font=T.F_BODY, bg=T.BG, fg=T.TEXT_DIM, anchor="w")
            v.pack(side="left", fill="x", expand=True)
            self._res[label] = v

        # Identification section
        ig = GroupBox(p, "Track Identification")
        ig.pack(fill="x", padx=10, pady=(0, 6))
        ibr = tk.Frame(ig, bg=T.BG)
        ibr.pack(fill="x", pady=(0, 6))
        OrangeBtn(ibr, "Shazam Audio ID" + (" \u2713" if HAS_SHAZAM else " \u2717"), self._run_shazam).pack(side="left", padx=(0, 6))
        LimeBtn(ibr, "Shazam Search (by name)", self._run_shazam_search).pack(side="left", padx=(0, 6))
        ClassicBtn(ibr, "Chromaprint/AcoustID", self._run_acoustid).pack(side="left", padx=(0, 6))
        ClassicBtn(ibr, "MusicBrainz Lookup", self._run_mb).pack(side="left", padx=(0, 6))
        OrangeBtn(ibr, "Apple Music Lookup", self._run_apple_music).pack(side="left", padx=(0, 6))
        ClassicBtn(ibr, "Write Tags to File", self._write_tags).pack(side="left", padx=(0, 6))
        self._auto_tag = tk.BooleanVar(value=False)
        tk.Checkbutton(ibr, text="Auto-tag after analysis", variable=self._auto_tag, font=T.F_SMALL,
                        bg=T.BG, fg=T.TEXT, selectcolor=T.INPUT_BG,
                        activebackground=T.BG, activeforeground=T.TEXT).pack(side="left")

        self._id_res = {}
        for label in ["Identified Title", "Identified Artist", "Genre", "Album", "Shazam URL",
                       "Chromaprint", "MusicBrainz", "Apple Music"]:
            r = tk.Frame(ig, bg=T.BG)
            r.pack(fill="x", pady=1)
            tk.Label(r, text=f"{label}:", font=T.F_BOLD, bg=T.BG, fg=T.TEXT, width=16, anchor="w").pack(side="left")
            v = tk.Label(r, text="--", font=T.F_BODY, bg=T.BG, fg=T.TEXT_DIM, anchor="w",
                          wraplength=500, justify="left")
            v.pack(side="left", fill="x", expand=True)
            self._id_res[label] = v

        # Export buttons
        eg = GroupBox(p, "Export Results")
        eg.pack(fill="x", padx=10, pady=(0, 6))
        er = tk.Frame(eg, bg=T.BG)
        er.pack(fill="x")
        ClassicBtn(er, "Export JSON", self._export_json).pack(side="left", padx=(0, 6))
        ClassicBtn(er, "Export CSV", self._export_csv).pack(side="left", padx=(0, 6))
        OrangeBtn(er, "Share as Image Card", self._export_image_card).pack(side="left")

        # Audio Tools section
        atg = GroupBox(p, "Audio Tools")
        atg.pack(fill="x", padx=10, pady=(0, 6))
        atr = tk.Frame(atg, bg=T.BG)
        atr.pack(fill="x")
        OrangeBtn(atr, "Noise Reduction" + (" \u2713" if HAS_NOISEREDUCE else " \u2717"), self._noise_reduce).pack(side="left", padx=(0, 6))
        LimeBtn(atr, "Lyrics Lookup" + (" \u2713" if HAS_LYRICS else " \u2717"), self._lyrics_lookup).pack(side="left", padx=(0, 6))
        ClassicBtn(atr, "Effects Chain" + (" \u2713" if HAS_PEDALBOARD else " \u2717"),
                    lambda: self.app._show_tab("effects")).pack(side="left", padx=(0, 6))
        self.lyrics_text = tk.Text(atg, height=6, font=T.F_MONO, bg=T.INPUT_BG, fg=T.TEXT,
                                    wrap="word", relief="flat", bd=0, state="disabled", padx=6, pady=4,
                                    highlightthickness=1, highlightbackground=T.INPUT_BORDER)
        self.lyrics_text.pack(fill="x", pady=(6, 0))

        # DJ Integration section
        dg = GroupBox(p, "DJ Integration")
        dg.pack(fill="x", padx=10, pady=(0, 6))
        dr = tk.Frame(dg, bg=T.BG)
        dr.pack(fill="x")
        OrangeBtn(dr, "Write Serato Tags", self._write_serato_tags).pack(side="left", padx=(0, 6))
        ClassicBtn(dr, "Add to Serato Crate", self._add_to_serato_crate).pack(side="left", padx=(0, 6))
        tk.Label(dr, text="Crate:", font=T.F_BODY, bg=T.BG, fg=T.TEXT).pack(side="left", padx=(8, 4))
        self.crate_var = tk.StringVar(value="LimeWire")
        ClassicEntry(dr, self.crate_var, width=15).pack(side="left", ipady=1, padx=(0, 6))
        dr2 = tk.Frame(dg, bg=T.BG)
        dr2.pack(fill="x", pady=(6, 0))
        LimeBtn(dr2, "Open in FL Studio", self._open_fl_studio).pack(side="left", padx=(0, 6))
        fl_detected = find_fl_studio()
        tk.Label(dr2, text=f"FL: {'Found' if fl_detected else 'Not found (set in Tools menu)'}",
                  font=T.F_SMALL, bg=T.BG, fg=T.LIME_DK if fl_detected else T.TEXT_DIM).pack(side="left", padx=(8, 0))

        # Loudness Targeting
        lg = GroupBox(p, "Loudness Targeting")
        lg.pack(fill="x", padx=10, pady=(0, 6))
        lr = tk.Frame(lg, bg=T.BG)
        lr.pack(fill="x")
        tk.Label(lr, text="Platform:", font=T.F_BODY, bg=T.BG, fg=T.TEXT).pack(side="left")
        self._lufs_preset = tk.StringVar(value="Spotify (-14 LUFS)")
        _presets = ["Spotify (-14 LUFS)", "YouTube (-13 LUFS)", "Apple Music (-16 LUFS)",
                    "CD/Master (-9 LUFS)", "Club (-6 LUFS)", "Podcast (-16 LUFS)"]
        ClassicCombo(lr, self._lufs_preset, _presets, width=22).pack(side="left", padx=SP_SM)
        LimeBtn(lr, "Normalize to Target", self._normalize_loudness).pack(side="left", padx=SP_SM)
        lr2 = tk.Frame(lg, bg=T.BG)
        lr2.pack(fill="x", pady=(SP_XS, 0))
        tk.Label(lr2, text="Before:", font=T.F_BODY, bg=T.BG, fg=T.TEXT_DIM).pack(side="left")
        self._lufs_before = tk.Label(lr2, text="-- LUFS", font=T.F_MONO, bg=T.BG, fg=T.TEXT_DIM)
        self._lufs_before.pack(side="left", padx=(SP_XS, SP_LG))
        tk.Label(lr2, text="After:", font=T.F_BODY, bg=T.BG, fg=T.TEXT_DIM).pack(side="left")
        self._lufs_after = tk.Label(lr2, text="-- LUFS", font=T.F_MONO, bg=T.BG, fg=T.TEXT_DIM)
        self._lufs_after.pack(side="left", padx=SP_XS)

        self.status_lbl = tk.Label(p, text="Select an audio file and click Analyze All",
                                    font=T.F_SMALL, bg=T.BG, fg=T.TEXT_DIM)
        self.status_lbl.pack(padx=10, anchor="w", pady=(0, 10))

    def _normalize_loudness(self):
        path = self.file_var.get().strip()
        if not path or not os.path.isfile(path):
            self.status_lbl.config(text="Select a file first", fg=T.YELLOW)
            return
        if not HAS_FFMPEG:
            self.status_lbl.config(text="FFmpeg required for loudness normalization", fg=T.RED)
            return
        preset = self._lufs_preset.get()
        # Parse target LUFS from preset string
        m = re.search(r"(-?\d+)", preset)
        target = float(m.group(1)) if m else -14.0
        self.status_lbl.config(text=f"Normalizing to {target:.0f} LUFS...", fg=T.YELLOW)

        def _do():
            base, ext = os.path.splitext(path)
            out = f"{base}_norm{ext}"
            # Two-pass loudnorm
            try:
                # Pass 1: measure
                r = subprocess.run(
                    ["ffmpeg", "-i", path, "-af",
                     f"loudnorm=I={target}:TP=-1.5:LRA=11:print_format=json",
                     "-f", "null", os.devnull],
                    capture_output=True, text=True, timeout=120)
                # Extract measured values from stderr JSON block
                stderr = r.stderr
                import json as _json
                json_start = stderr.rfind("{")
                json_end = stderr.rfind("}") + 1
                if json_start >= 0:
                    measured = _json.loads(stderr[json_start:json_end])
                    mi = measured.get("input_i", "-24")
                    mtp = measured.get("input_tp", "-1")
                    mlra = measured.get("input_lra", "7")
                    mt = measured.get("input_thresh", "-34")
                    before_lufs = float(mi)
                    self.after(0, lambda: self._lufs_before.config(text=f"{before_lufs:.1f} LUFS", fg=T.TEXT))
                    # Pass 2: apply
                    af = (f"loudnorm=I={target}:TP=-1.5:LRA=11:"
                          f"measured_I={mi}:measured_TP={mtp}:measured_LRA={mlra}:"
                          f"measured_thresh={mt}:linear=true")
                    subprocess.run(["ffmpeg", "-y", "-i", path, "-af", af, out],
                                   capture_output=True, timeout=300)
                    # Measure output
                    r2 = subprocess.run(
                        ["ffmpeg", "-i", out, "-af", "loudnorm=print_format=json",
                         "-f", "null", os.devnull],
                        capture_output=True, text=True, timeout=120)
                    j2s = r2.stderr.rfind("{")
                    j2e = r2.stderr.rfind("}") + 1
                    if j2s >= 0:
                        m2 = _json.loads(r2.stderr[j2s:j2e])
                        after_lufs = float(m2.get("input_i", target))
                        self.after(0, lambda: self._lufs_after.config(text=f"{after_lufs:.1f} LUFS", fg=T.LIME_DK))
                    self.after(0, lambda: (
                        self.status_lbl.config(text=f"Normalized: {os.path.basename(out)}", fg=T.LIME_DK),
                        self.app.toast(f"Loudness normalized to {target:.0f} LUFS")))
                else:
                    self.after(0, lambda: self.status_lbl.config(text="Could not parse loudnorm output", fg=T.RED))
            except Exception as e:
                self.after(0, lambda: self.status_lbl.config(text=f"Error: {str(e)[:60]}", fg=T.RED))

        threading.Thread(target=_do, daemon=True).start()

    def _browse(self):
        f = filedialog.askopenfilename(
            filetypes=[("Audio", "*.mp3 *.wav *.flac *.ogg *.m4a *.aac"), ("All", "*.*")])
        if f:
            self.file_var.set(f)

    def _run_all(self):
        path = self.file_var.get()
        if not path or not os.path.exists(path):
            messagebox.showwarning("LimeWire", "Select a valid file.")
            return
        self.status_lbl.config(text="Analyzing...", fg=T.YELLOW)
        self.app.set_status("Analyzing audio...")
        threading.Thread(target=self._do_analyze, args=(path,), daemon=True).start()

    def _do_analyze(self, path):
        # Basic file info
        fsize = os.path.getsize(path) / (1024 * 1024)
        self.after(0, lambda: self._res["File Size"].config(text=f"{fsize:.1f} MB", fg=T.TEXT))
        # Duration/SR via ffprobe
        try:
            r = subprocess.run(
                ["ffprobe", "-v", "quiet", "-print_format", "json",
                 "-show_format", "-show_streams", path],
                capture_output=True, text=True, timeout=15)
            info = json.loads(r.stdout)
            dur = float(info.get("format", {}).get("duration", 0))
            sr = info.get("streams", [{}])[0].get("sample_rate", "?")
            self.after(0, lambda: (
                self._res["Duration"].config(text=fmt_duration(dur), fg=T.TEXT),
                self._res["Sample Rate"].config(text=f"{sr} Hz", fg=T.TEXT)))
        except Exception:
            pass
        # BPM + Key
        bk = analyze_bpm_key(path)
        if bk.get("bpm"):
            camelot = key_to_camelot(bk.get("key", "")) or "?"
            self.after(0, lambda: (
                self._res["BPM"].config(text=f"{bk['bpm']}", fg=T.LIME_DK),
                self._res["Key"].config(text=bk.get("key", "?"), fg=T.LIME_DK),
                self._res["Camelot"].config(text=camelot, fg=T.LIME_DK)))
        elif bk.get("error"):
            self.after(0, lambda: self._res["BPM"].config(text=bk["error"], fg=T.RED))
        # Loudness
        loud = analyze_loudness(path)
        if loud.get("lufs") is not None:
            self.after(0, lambda: (
                self._res["Loudness (LUFS)"].config(text=f"{loud['lufs']} LUFS", fg=T.TEXT),
                self._res["True Peak"].config(text=f"{loud['peak']} dBTP", fg=T.TEXT)))
        elif loud.get("error"):
            self.after(0, lambda: self._res["Loudness (LUFS)"].config(text=loud["error"], fg=T.RED))
        # Waveform
        bars = generate_waveform_data(path, 600, 70)
        if bars:
            self.after(0, lambda: self._draw_waveform(bars))
        self.after(0, lambda: (
            self.status_lbl.config(text="Analysis complete", fg=T.LIME_DK),
            self.app.set_status("Analysis complete")))
        # Auto-tag if enabled
        if hasattr(self, "_auto_tag") and self._auto_tag.get():
            self.after(200, self._write_tags)

    def _draw_waveform(self, bars):
        if not bars:
            return
        cv = self.wave_cv
        cv.delete("all")
        w = cv.winfo_width() or WAVEFORM_W
        h = WAVEFORM_H
        bw = max(1, w / len(bars))
        gap = max(1, bw * 0.15)
        for i, amp in enumerate(bars):
            x = i * bw
            bar_h = max(1, amp * h * 0.85)
            y1 = (h - bar_h) / 2
            y2 = (h + bar_h) / 2
            if amp < 0.3:
                color = T.LIME
            elif amp < 0.6:
                color = _lerp_color(T.LIME, T.YELLOW, (amp - 0.3) / 0.3)
            elif amp < 0.85:
                color = _lerp_color(T.YELLOW, T.ORANGE, (amp - 0.6) / 0.25)
            else:
                color = T.RED
            cv.create_rectangle(x + gap / 2, y1, x + bw - gap / 2, y2, fill=color, outline="")

    def _run_shazam(self):
        path = self.file_var.get()
        if not path or not os.path.exists(path):
            return
        self.status_lbl.config(text="Identifying with Shazam...", fg=T.YELLOW)
        threading.Thread(target=self._do_shazam, args=(path,), daemon=True).start()

    def _do_shazam(self, path):
        result = identify_shazam(path)
        if result.get("title"):
            self.after(0, lambda: (
                self._id_res["Identified Title"].config(text=result["title"], fg=T.LIME_DK),
                self._id_res["Identified Artist"].config(text=result.get("artist", "?"), fg=T.TEXT),
                self._id_res["Genre"].config(text=result.get("genre", "?"), fg=T.TEXT),
                self._id_res["Shazam URL"].config(text=result.get("shazam_url", ""), fg=T.TEXT_BLUE),
                self.status_lbl.config(text=f"Shazam: {result['title']} by {result.get('artist', '')}", fg=T.LIME_DK)))
        else:
            self.after(0, lambda: self.status_lbl.config(
                text=f"Shazam: {result.get('error', 'No match')}", fg=T.RED))

    def _run_shazam_search(self):
        """Search Shazam by filename/title -- works on any Python version, no Rust needed."""
        path = self.file_var.get()
        if not path:
            return
        # Use filename as search query
        query = os.path.splitext(os.path.basename(path))[0]
        # Clean up typical YouTube title cruft
        query = re.sub(
            r'\[.*?\]|\(.*?\)|official.*|music.*video|lyrics|hd|hq|audio|ft\.?|feat\.?',
            '', query, flags=re.IGNORECASE)
        query = re.sub(r'[_\-]+', ' ', query).strip()
        if not query:
            messagebox.showinfo("LimeWire", "Could not extract search term from filename.")
            return
        self.status_lbl.config(text=f"Searching Shazam for: {query}", fg=T.YELLOW)
        threading.Thread(target=self._do_shazam_search, args=(query,), daemon=True).start()

    def _do_shazam_search(self, query):
        result = search_shazam(query)
        if result.get("title"):
            self.after(0, lambda: (
                self._id_res["Identified Title"].config(text=result["title"], fg=T.LIME_DK),
                self._id_res["Identified Artist"].config(text=result.get("artist", "?"), fg=T.TEXT),
                self._id_res["Genre"].config(text=result.get("genre", "?"), fg=T.TEXT),
                self._id_res["Album"].config(text=result.get("album", ""), fg=T.TEXT),
                self._id_res["Shazam URL"].config(text=result.get("url", ""), fg=T.TEXT_BLUE),
                self.status_lbl.config(text=f"Found: {result['title']} by {result.get('artist', '')}", fg=T.LIME_DK)))
        else:
            self.after(0, lambda: self.status_lbl.config(
                text=f"Search: {result.get('error', 'No results')}", fg=T.RED))

    def _run_acoustid(self):
        path = self.file_var.get()
        if not path or not os.path.exists(path):
            return
        self.status_lbl.config(text="Fingerprinting with Chromaprint...", fg=T.YELLOW)
        threading.Thread(target=self._do_acoustid, args=(path,), daemon=True).start()

    def _do_acoustid(self, path):
        result = identify_acoustid(path)
        if result.get("title"):
            self.after(0, lambda: (
                self._id_res["Chromaprint"].config(
                    text=f"{result['title']} by {result.get('artist', '')} (score: {result.get('score', '')})",
                    fg=T.LIME_DK),
                self.status_lbl.config(text="Chromaprint matched", fg=T.LIME_DK)))
        else:
            self.after(0, lambda: self._id_res["Chromaprint"].config(
                text=result.get("error", "No match"), fg=T.RED))

    def _run_mb(self):
        title = self._id_res["Identified Title"].cget("text")
        artist = self._id_res["Identified Artist"].cget("text")
        if title == "--" or not title:
            messagebox.showinfo("LimeWire", "Run Shazam or Chromaprint first to get title/artist.")
            return
        self.status_lbl.config(text="Looking up MusicBrainz...", fg=T.YELLOW)
        threading.Thread(target=self._do_mb, args=(title, artist), daemon=True).start()

    def _do_mb(self, title, artist):
        result = lookup_musicbrainz(title, artist)
        if result.get("mb_title"):
            self.after(0, lambda: (
                self._id_res["MusicBrainz"].config(
                    text=(f"{result['mb_title']} \u2014 {result.get('mb_artist', '')} "
                          f"[{result.get('mb_album', '')}] ({result.get('mb_date', '')})"),
                    fg=T.LIME_DK),
                self.status_lbl.config(text="MusicBrainz match found", fg=T.LIME_DK)))
        else:
            self.after(0, lambda: self._id_res["MusicBrainz"].config(
                text=result.get("error", "No match"), fg=T.RED))

    def _run_apple_music(self):
        title = self._id_res["Identified Title"].cget("text")
        artist = self._id_res["Identified Artist"].cget("text")
        if title == "--" or not title:
            messagebox.showinfo("LimeWire", "Run Shazam or Chromaprint first to get title/artist.")
            return
        self.status_lbl.config(text="Looking up Apple Music...", fg=T.YELLOW)
        threading.Thread(target=self._do_apple_music, args=(title, artist), daemon=True).start()

    def _do_apple_music(self, title, artist):
        result = lookup_apple_music(title, artist)
        if result.get("am_title"):
            dur_s = result.get("am_duration_ms", 0) // 1000
            info = (f"{result['am_title']} \u2014 {result.get('am_artist', '')} "
                    f"[{result.get('am_album', '')}] ({result.get('am_date', '')}) {fmt_duration(dur_s)}")
            self.after(0, lambda: (
                self._id_res["Apple Music"].config(text=info, fg=T.LIME_DK),
                self._id_res["Genre"].config(text=result.get("am_genre", "?"), fg=T.TEXT)
                    if self._id_res["Genre"].cget("text") == "--" else None,
                self._id_res["Album"].config(text=result.get("am_album", ""), fg=T.TEXT)
                    if self._id_res["Album"].cget("text") == "--" else None,
                self.status_lbl.config(text=f"Apple Music: {result['am_title']}", fg=T.LIME_DK)))
        else:
            self.after(0, lambda: self._id_res["Apple Music"].config(
                text=result.get("error", "No match"), fg=T.RED))

    def _write_tags(self):
        path = self.file_var.get()
        if not path or not os.path.exists(path):
            messagebox.showinfo("LimeWire", "Select an audio file first.")
            return
        title = self._id_res["Identified Title"].cget("text")
        artist = self._id_res["Identified Artist"].cget("text")
        bpm_str = self._res["BPM"].cget("text")
        key_str = self._res["Key"].cget("text")
        genre = self._id_res["Genre"].cget("text") if "Genre" in self._id_res else ""
        try:
            audio = mutagen.File(path)
            if audio is None:
                self.status_lbl.config(text="Unsupported format", fg=T.RED)
                return
            from mutagen.mp3 import MP3 as _MP3
            from mutagen.flac import FLAC as _FLAC
            from mutagen.mp4 import MP4 as _MP4
            from mutagen.wave import WAVE as _WAVE
            ext = os.path.splitext(path)[1].lower()
            if isinstance(audio, (_MP3, _WAVE)):
                # ID3 tags
                try:
                    audio.add_tags()
                except Exception:
                    pass
                tags = audio.tags or audio
                if title and title != "--":
                    tags["TIT2"] = TIT2(encoding=3, text=title)
                if artist and artist != "--":
                    tags["TPE1"] = TPE1(encoding=3, text=artist)
                if bpm_str and bpm_str != "--":
                    try:
                        tags["TBPM"] = TBPM(encoding=3, text=str(int(float(bpm_str))))
                    except Exception:
                        pass
                if key_str and key_str != "--":
                    tags["TKEY"] = TKEY(encoding=3, text=key_str)
                if genre and genre != "--":
                    tags["TCON"] = TCON(encoding=3, text=genre)
            elif isinstance(audio, (_FLAC,)) or ext in (".ogg", ".opus"):
                # Vorbis comments
                if title and title != "--":
                    audio["TITLE"] = [title]
                if artist and artist != "--":
                    audio["ARTIST"] = [artist]
                if bpm_str and bpm_str != "--":
                    audio["BPM"] = [str(int(float(bpm_str)))]
                if key_str and key_str != "--":
                    audio["KEY"] = [key_str]
                if genre and genre != "--":
                    audio["GENRE"] = [genre]
            elif isinstance(audio, _MP4):
                # MP4 atoms
                if title and title != "--":
                    audio.tags["\u00a9nam"] = [title]
                if artist and artist != "--":
                    audio.tags["\u00a9ART"] = [artist]
                if bpm_str and bpm_str != "--":
                    try:
                        audio.tags["tmpo"] = [int(float(bpm_str))]
                    except Exception:
                        pass
                if genre and genre != "--":
                    audio.tags["\u00a9gen"] = [genre]
            audio.save()
            self.status_lbl.config(text=f"Tags written to {ext.upper().lstrip('.')} file", fg=T.LIME_DK)
        except Exception as e:
            self.status_lbl.config(text=f"Tag error: {str(e)[:60]}", fg=T.RED)

    def _get_results_dict(self):
        data = {}
        for k, v in self._res.items():
            val = v.cget("text")
            data[k] = val if val != "--" else None
        for k, v in self._id_res.items():
            val = v.cget("text")
            data[k] = val if val != "--" else None
        data["file"] = self.file_var.get()
        return data

    def _export_json(self):
        data = self._get_results_dict()
        if not data.get("file"):
            return
        path = filedialog.asksaveasfilename(
            defaultextension=".json", filetypes=[("JSON", "*.json")],
            initialfile=os.path.splitext(os.path.basename(data["file"]))[0] + "_analysis.json")
        if path:
            save_json(path, data)
            self.status_lbl.config(text=f"Exported to {os.path.basename(path)}", fg=T.LIME_DK)

    def _export_csv(self):
        data = self._get_results_dict()
        if not data.get("file"):
            return
        path = filedialog.asksaveasfilename(
            defaultextension=".csv", filetypes=[("CSV", "*.csv")],
            initialfile=os.path.splitext(os.path.basename(data["file"]))[0] + "_analysis.csv")
        if path:
            import csv
            with open(path, "w", newline="") as f:
                w = csv.writer(f)
                w.writerow(data.keys())
                w.writerow(data.values())
            self.status_lbl.config(text=f"Exported to {os.path.basename(path)}", fg=T.LIME_DK)

    def _export_image_card(self):
        """Export analysis results as a shareable PNG image card."""
        data = self._get_results_dict()
        if not data.get("file"):
            messagebox.showinfo("LimeWire", "Analyze a file first.")
            return
        path = filedialog.asksaveasfilename(
            defaultextension=".png", filetypes=[("PNG", "*.png")],
            initialfile=os.path.splitext(os.path.basename(data["file"]))[0] + "_card.png")
        if not path:
            return
        try:
            from PIL import Image, ImageDraw, ImageFont
            W, H = 600, 400
            card = Image.new("RGB", (W, H), "#1a1a2e")
            draw = ImageDraw.Draw(card)
            # Gradient header bar
            for y in range(80):
                r = int(50 + y * 1.2)
                g = int(180 - y * 0.5)
                b = int(80 + y * 0.3)
                draw.line([(0, y), (W, y)], fill=(r, g, b))
            # Text
            try:
                font_lg = ImageFont.truetype("segoeui.ttf", 28)
            except Exception:
                font_lg = ImageFont.load_default()
            try:
                font_md = ImageFont.truetype("segoeui.ttf", 18)
            except Exception:
                font_md = font_lg
            try:
                font_sm = ImageFont.truetype("segoeui.ttf", 14)
            except Exception:
                font_sm = font_md
            # Title
            title = os.path.splitext(os.path.basename(data["file"]))[0][:40]
            draw.text((20, 20), title, fill="#FFFFFF", font=font_lg)
            draw.text((20, 55), "LimeWire Analysis", fill="#80ffaa", font=font_sm)
            # Results
            y = 100
            items = [("BPM", data.get("bpm", "--")), ("Key", data.get("key", "--")),
                     ("Camelot", data.get("camelot", "--")),
                     ("Loudness", f"{data.get('lufs', '--')} LUFS"),
                     ("True Peak", f"{data.get('true_peak', '--')} dBFS"),
                     ("Duration", data.get("duration", "--")),
                     ("Sample Rate", data.get("sample_rate", "--"))]
            for label, val in items:
                draw.text((30, y), f"{label}:", fill="#aaaaaa", font=font_md)
                draw.text((200, y), str(val), fill="#FFFFFF", font=font_md)
                y += 36
            # Footer
            draw.text((20, H - 30), "Generated by LimeWire Studio Edition", fill="#555555", font=font_sm)
            # Embed album art if available
            fp = data.get("file", "")
            art_data, _ = extract_cover_art(fp) if fp else (None, None)
            if art_data:
                try:
                    art = Image.open(BytesIO(art_data)).convert("RGB").resize((120, 120), Image.LANCZOS)
                    card.paste(art, (460, 100))
                    draw.rectangle([(459, 99), (581, 221)], outline="#80ffaa", width=2)
                except Exception:
                    pass
            card.save(path)
            self.status_lbl.config(text=f"Image card saved: {os.path.basename(path)}", fg=T.LIME_DK)
            show_toast(self.app, "Analysis card exported", "success")
        except Exception as e:
            messagebox.showerror("Export Error", str(e))

    # -- DJ Integration methods --
    def _write_serato_tags(self):
        path = self.file_var.get()
        if not path or not os.path.exists(path) or not path.lower().endswith(".mp3"):
            messagebox.showinfo("LimeWire", "Select an MP3 file first.")
            return
        bpm_str = self._res["BPM"].cget("text")
        key_str = self._res["Key"].cget("text")
        bpm = float(bpm_str) if bpm_str and bpm_str != "--" else None
        key = key_str if key_str and key_str != "--" else None
        if not bpm and not key:
            messagebox.showinfo("LimeWire", "Run analysis first to get BPM/Key.")
            return
        ok, err = write_serato_tags(path, bpm=bpm, key=key)
        if ok:
            camelot = key_to_camelot(key) or ""
            self.status_lbl.config(
                text=f"Serato tags written \u2014 BPM:{int(bpm) if bpm else '?'} "
                     f"Key:{key_to_serato_tkey(key) or '?'} Camelot:{camelot}",
                fg=T.LIME_DK)
            self.app.toast("Serato tags written")
        else:
            self.status_lbl.config(text=f"Serato error: {err}", fg=T.RED)

    def _add_to_serato_crate(self):
        path = self.file_var.get()
        if not path or not os.path.exists(path):
            messagebox.showinfo("LimeWire", "Select a file first.")
            return
        crate_name = self.crate_var.get().strip() or "LimeWire"
        ok, msg = add_to_serato_crate(path, crate_name)
        if ok:
            self.status_lbl.config(
                text=f"Added to Serato crate: {crate_name}" + (f" ({msg})" if msg else ""),
                fg=T.LIME_DK)
            self.app.toast(f"Added to crate: {crate_name}")
        else:
            self.status_lbl.config(text=f"Crate error: {msg}", fg=T.RED)

    def _open_fl_studio(self):
        path = self.file_var.get()
        fl_path = self.app.settings.get("fl_studio_path", "")
        ok, err = open_in_fl_studio(path, fl_path or None)
        if not ok:
            messagebox.showinfo("LimeWire", f"FL Studio: {err}")

    def _noise_reduce(self):
        path = self.file_var.get()
        if not path or not os.path.exists(path):
            messagebox.showinfo("LimeWire", "Select an audio file first.")
            return
        if not HAS_NOISEREDUCE:
            messagebox.showinfo("LimeWire", "noisereduce not installed.\nRun: pip install noisereduce")
            return
        self.status_lbl.config(text="Applying noise reduction...", fg=T.YELLOW)

        def _do():
            out, err = reduce_noise(path)
            if out:
                self.after(0, lambda: (
                    self.status_lbl.config(text=f"Cleaned: {os.path.basename(out)}", fg=T.LIME_DK),
                    self.app.toast(f"Noise reduced: {os.path.basename(out)}")))
            else:
                self.after(0, lambda: self.status_lbl.config(
                    text=f"Noise reduction error: {err}", fg=T.RED))

        threading.Thread(target=_do, daemon=True).start()

    def _lyrics_lookup(self):
        title = self._id_res["Identified Title"].cget("text")
        artist = self._id_res["Identified Artist"].cget("text")
        if title == "--" or not title:
            # Try filename
            path = self.file_var.get()
            if path:
                title = os.path.splitext(os.path.basename(path))[0]
                title = re.sub(
                    r'\[.*?\]|\(.*?\)|official.*|music.*video|lyrics|hd|hq|audio',
                    '', title, flags=re.IGNORECASE)
                title = re.sub(r'[_\-]+', ' ', title).strip()
            else:
                messagebox.showinfo("LimeWire", "Identify a track first or select a file.")
                return
            artist = ""
        self.status_lbl.config(text=f"Looking up lyrics: {title}...", fg=T.YELLOW)
        api_key = self.app.settings.get("genius_api_key", "")

        def _do():
            result = lookup_lyrics(title, artist, api_key)
            if result.get("lyrics"):
                self.after(0, lambda: self._show_lyrics(result))
            else:
                self.after(0, lambda: self.status_lbl.config(
                    text=f"Lyrics: {result.get('error', 'Not found')}", fg=T.RED))

        threading.Thread(target=_do, daemon=True).start()

    def _show_lyrics(self, result):
        self.lyrics_text.config(state="normal")
        self.lyrics_text.delete("1.0", "end")
        header = f"{result.get('title', '')} \u2014 {result.get('artist', '')}\n{'\u2500' * 60}\n"
        self.lyrics_text.insert("1.0", header + result.get("lyrics", ""))
        self.lyrics_text.config(state="disabled")
        self.status_lbl.config(text=f"Lyrics: {result['title']} by {result.get('artist', '')}", fg=T.LIME_DK)
