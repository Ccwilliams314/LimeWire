#!/usr/bin/env python3
"""
LimeWire v1.0.0 — Studio Edition
The modern music utility for everything. 18-tab audio production studio.
Features: Download, Batch DL, Playlist, Convert, Player (crossfade/EQ),
          Stem Separation (Demucs), Audio Analysis (BPM/Key/LUFS),
          Shazam ID, MusicBrainz Tagging, Chromaprint, Scheduler, History,
          Audio Editor (trim/cut/fade/merge/undo), Microphone Recording,
          Whisper Transcription (SRT export), Spectrogram Visualization,
          Pitch Shift, Time Stretch, Vocal Isolation,
          Stem Remixer (per-stem vol/pan/mute/solo), Batch Processor,
          Loudness Targeting (platform presets), Smart Playlists (energy/key)
UI: Modern rounded buttons, gradient header, command palette (Ctrl+K),
    tooltips, toast notifications, live theme switching, icon toolbar
Requirements: pip install yt-dlp pillow requests mutagen pyglet
              pip install librosa soundfile pyloudnorm shazamio musicbrainzngs demucs pyacoustid
              pip install pydub sounddevice pyrubberband openai-whisper
              winget install ffmpeg
"""

import os, sys, json, threading, datetime, time, urllib.request, subprocess, re, webbrowser, asyncio, struct, wave, math, shutil, logging
from io import BytesIO
from concurrent.futures import ThreadPoolExecutor, as_completed

# ── Logging ───────────────────────────────────────────────────────────────────
_log = logging.getLogger("LimeWire")
_log.setLevel(logging.INFO)
_log_handler = logging.StreamHandler(sys.stderr)
_log_handler.setFormatter(logging.Formatter("[%(levelname)s] %(message)s"))
_log.addHandler(_log_handler)

import tkinter as tk
from tkinter import ttk, filedialog, messagebox

# ── Dependency validation ─────────────────────────────────────────────────────
# Validate required packages — report missing instead of auto-installing.
# Auto-pip-install during startup is unsafe (blocks GUI, may fail offline, needs elevation).
_REQUIRED = [("yt_dlp","yt-dlp"),("PIL","Pillow"),("requests","requests"),
             ("mutagen","mutagen"),("pyglet","pyglet")]
_missing = []
for _imp, _pkg in _REQUIRED:
    try: __import__(_imp)
    except ImportError: _missing.append(_pkg)
if _missing:
    print(f"ERROR: Missing required packages: {', '.join(_missing)}", file=sys.stderr)
    print(f"Install with: pip install {' '.join(_missing)}", file=sys.stderr)
    try:
        import tkinter as _tk; _tk.Tk().withdraw()
        from tkinter import messagebox as _mb
        _mb.showerror("LimeWire — Missing Dependencies",
            f"Required packages not installed:\n\n{chr(10).join(_missing)}\n\n"
            f"Run:\n  pip install {' '.join(_missing)}")
    except Exception: pass
    sys.exit(1)

# FFmpeg validation — needed for audio conversion and yt-dlp post-processing
HAS_FFMPEG = shutil.which("ffmpeg") is not None

# shazamio requires Rust compiler for shazamio-core — no prebuilt wheel for Python 3.13+
# We skip auto-install and use a pure-HTTP Shazam search fallback instead.
# If on Python <=3.12 you can manually: pip install shazamio

import yt_dlp
from PIL import Image, ImageTk
import requests, mutagen
from mutagen.easyid3 import EasyID3
from mutagen.id3 import ID3, APIC, TIT2, TPE1, TALB, TDRC, TCON, TBPM, TKEY
from mutagen.mp3 import MP3
import pyglet

# Optional imports — per-module graceful fallback
# Heavy libs (librosa, demucs, torch) are lazy-imported to cut startup time by 3-5s.
try: import numpy as np; HAS_NUMPY = True
except Exception: HAS_NUMPY = False

# Lazy-loaded on first use (librosa pulls numpy, scipy, numba — ~3s import cost)
HAS_LIBROSA = False; HAS_LOUDNESS = False
def _ensure_librosa():
    global HAS_LIBROSA, librosa
    if HAS_LIBROSA: return True
    try: import librosa as _lib; librosa = _lib; HAS_LIBROSA = True; return True
    except Exception: return False
def _ensure_loudness():
    global HAS_LOUDNESS, sf, pyln
    if HAS_LOUDNESS: return True
    try:
        import soundfile as _sf; import pyloudnorm as _pyln
        sf = _sf; pyln = _pyln; HAS_LOUDNESS = True; return True
    except Exception: return False

try: import musicbrainzngs; musicbrainzngs.set_useragent("LimeWire","1.0","https://github.com"); HAS_MB = True
except Exception: HAS_MB = False
try: import acoustid; HAS_ACOUSTID = True
except Exception: HAS_ACOUSTID = False
# Demucs: use stable top-level import, not internal demucs.separate
try: import demucs; HAS_DEMUCS = True
except Exception: HAS_DEMUCS = False
# Shazam: try full library, else use pure-HTTP search (always available via requests)
try: from shazamio import Shazam as ShazamEngine; HAS_SHAZAM = True
except Exception: HAS_SHAZAM = False
HAS_SHAZAM_SEARCH = True  # pure-HTTP always works
try: import tkinterdnd2; HAS_DND = True
except Exception: HAS_DND = False
try: import pyflp; HAS_PYFLP = True
except Exception: HAS_PYFLP = False
try: from serato_tools.crate import Crate as SeratoCrate; HAS_SERATO = True
except Exception: HAS_SERATO = False
# New audio features
try: import noisereduce as nr; HAS_NOISEREDUCE = True
except Exception: HAS_NOISEREDUCE = False
try: import pedalboard; HAS_PEDALBOARD = True
except Exception: HAS_PEDALBOARD = False
try: import lyricsgenius; HAS_LYRICS = True
except Exception: HAS_LYRICS = False

# Audio editing / recording / pitch — lazy loaded on first use
HAS_PYDUB = False; HAS_SOUNDDEVICE = False; HAS_WHISPER = False; HAS_RUBBERBAND = False
def _ensure_pydub():
    global HAS_PYDUB, pydub, AudioSegment
    if HAS_PYDUB: return True
    try:
        from pydub import AudioSegment as _AS
        pydub = __import__("pydub"); AudioSegment = _AS; HAS_PYDUB = True; return True
    except Exception: return False
def _ensure_sounddevice():
    global HAS_SOUNDDEVICE, sd_mod
    if HAS_SOUNDDEVICE: return True
    try: import sounddevice as _sd; sd_mod = _sd; HAS_SOUNDDEVICE = True; return True
    except Exception: return False
def _ensure_whisper():
    global HAS_WHISPER, whisper_mod
    if HAS_WHISPER: return True
    try: import whisper as _w; whisper_mod = _w; HAS_WHISPER = True; return True
    except Exception: return False
def _ensure_rubberband():
    global HAS_RUBBERBAND, pyrubberband
    if HAS_RUBBERBAND: return True
    try: import pyrubberband as _pr; pyrubberband = _pr; HAS_RUBBERBAND = True; return True
    except Exception: return False

# ── Audio backend ─────────────────────────────────────────────────────────────
class _AudioPlayer:
    """Thin wrapper around pyglet.media.Player for audio playback."""
    def __init__(self):
        self._player = None
        self._volume = 0.8
    def load(self, path):
        if not os.path.isfile(path):
            raise FileNotFoundError(f"Audio file not found: {path}")
        self.stop()
        src = pyglet.media.load(path)
        self._player = pyglet.media.Player()
        self._player.volume = self._volume
        self._player.queue(src)
    def play(self, start=0):
        if self._player:
            try:
                if start > 0: self._player.seek(start)
            except Exception: pass
            self._player.play()
    def pause(self):
        if self._player:
            self._player.pause()
    def stop(self):
        if self._player:
            try:
                self._player.pause()
                self._player.delete()
            except Exception: pass
            self._player = None
    def set_volume(self, v):
        self._volume = v
        if self._player:
            self._player.volume = v
    def get_busy(self): return self._player.playing if self._player else False
    def get_pos(self): return self._player.time if self._player else 0
_audio = _AudioPlayer()

# ═══════════════════════════════════════════════════════════════════════════════
# LIMEWIRE THEME — Light & Dark palettes
# ═══════════════════════════════════════════════════════════════════════════════
THEME_LIGHT={
    "BG":"#F0F2F5","BG_DARK":"#E4E6EA","PANEL":"#FFFFFF","WHITE":"#FFFFFF","BLACK":"#1A1A2E",
    "TEXT":"#1A1A2E","TEXT_DIM":"#5A6270","TEXT_BLUE":"#0A58CA",
    "LIME":"#27AE60","LIME_DK":"#1E8449","LIME_LT":"#82E0AA",
    "BLUE_HL":"#0D6EFD","RED":"#DC3545","YELLOW":"#E0A800","ORANGE":"#E8590C",
    "TOOLBAR":"#FFFFFF","BORDER_L":"#D0D5DD","BORDER_D":"#BFC5CF","INPUT_BG":"#FFFFFF","TROUGH":"#DEE2E6",
    "CARD_BG":"#FFFFFF","CARD_BORDER":"#D0D5DD","BTN_HOVER":"#E4E6EA",
    "LIME_HOVER":"#1E8449","ORANGE_HOVER":"#C74E0A",
    "INPUT_BORDER":"#BFC5CF","INPUT_FOCUS":"#6EA8FE","TAB_ACTIVE":"#27AE60",
    "SUCCESS":"#27AE60","WARNING":"#E0A800","ERROR":"#DC3545","INFO":"#0A85D1",
    "SURFACE":"#FFFFFF","SURFACE_2":"#F5F6F8","SURFACE_3":"#E4E6EA",
    "ACCENT_START":"#27AE60","ACCENT_END":"#17A589",
    "CANVAS_BG":"#161B22",
}
THEME_DARK={
    "BG":"#1A1D21","BG_DARK":"#13161A","PANEL":"#22262B","WHITE":"#2A2E33","BLACK":"#0D0F12",
    "TEXT":"#E8EAED","TEXT_DIM":"#9CA3AF","TEXT_BLUE":"#6EA8FE",
    "LIME":"#2ECC71","LIME_DK":"#27AE60","LIME_LT":"#56D384",
    "BLUE_HL":"#4A90D9","RED":"#EF4444","YELLOW":"#FBBF24","ORANGE":"#F97316",
    "TOOLBAR":"#1E2227","BORDER_L":"#343A40","BORDER_D":"#13161A","INPUT_BG":"#22262B","TROUGH":"#343A40",
    "CARD_BG":"#22262B","CARD_BORDER":"#343A40","BTN_HOVER":"#2C3035",
    "LIME_HOVER":"#25A35A","ORANGE_HOVER":"#EA6C0E",
    "INPUT_BORDER":"#343A40","INPUT_FOCUS":"#4A90D9","TAB_ACTIVE":"#2ECC71",
    "SUCCESS":"#2ECC71","WARNING":"#FBBF24","ERROR":"#EF4444","INFO":"#22D3EE",
    "SURFACE":"#22262B","SURFACE_2":"#1A1D21","SURFACE_3":"#13161A",
    "ACCENT_START":"#2ECC71","ACCENT_END":"#1ABC9C",
    "CANVAS_BG":"#0D0F12",
}
THEME_MODERN={
    "BG":"#0D1117","BG_DARK":"#010409","PANEL":"#161B22","WHITE":"#21262D","BLACK":"#010409",
    "TEXT":"#F0F6FC","TEXT_DIM":"#A0ADB8","TEXT_BLUE":"#58A6FF",
    "LIME":"#3FB950","LIME_DK":"#2EA043","LIME_LT":"#56D364",
    "BLUE_HL":"#1F6FEB","RED":"#F85149","YELLOW":"#D29922","ORANGE":"#DB6D28",
    "TOOLBAR":"#161B22","BORDER_L":"#30363D","BORDER_D":"#21262D","INPUT_BG":"#0D1117","TROUGH":"#21262D",
    "CARD_BG":"#161B22","CARD_BORDER":"#30363D","BTN_HOVER":"#30363D",
    "LIME_HOVER":"#2EA043","ORANGE_HOVER":"#C05010",
    "INPUT_BORDER":"#30363D","INPUT_FOCUS":"#1F6FEB","TAB_ACTIVE":"#3FB950",
    "SUCCESS":"#3FB950","WARNING":"#D29922","ERROR":"#F85149","INFO":"#58A6FF",
    "SURFACE":"#161B22","SURFACE_2":"#0D1117","SURFACE_3":"#010409",
    "ACCENT_START":"#3FB950","ACCENT_END":"#1ABC9C",
    "CANVAS_BG":"#010409",
}
THEME_SYNTHWAVE={
    "BG":"#0C0C0C","BG_DARK":"#060606","PANEL":"#1A1A2E","WHITE":"#16213E","BLACK":"#060606",
    "TEXT":"#EF9AF2","TEXT_DIM":"#7C52A8","TEXT_BLUE":"#00BFFF",
    "LIME":"#FF2975","LIME_DK":"#D41E60","LIME_LT":"#FF6B9D",
    "BLUE_HL":"#8C1EFF","RED":"#FF1744","YELLOW":"#FF901F","ORANGE":"#F222FF",
    "TOOLBAR":"#1A1A2E","BORDER_L":"#2D2060","BORDER_D":"#0C0C0C","INPUT_BG":"#16213E","TROUGH":"#2D2060",
    "CARD_BG":"#1A1A2E","CARD_BORDER":"#2D2060","BTN_HOVER":"#2D2060",
    "LIME_HOVER":"#D41E60","ORANGE_HOVER":"#C918D4",
    "INPUT_BORDER":"#2D2060","INPUT_FOCUS":"#8C1EFF","TAB_ACTIVE":"#FF2975",
    "SUCCESS":"#FF2975","WARNING":"#FF901F","ERROR":"#FF1744","INFO":"#00BFFF",
    "SURFACE":"#1A1A2E","SURFACE_2":"#0C0C0C","SURFACE_3":"#060606",
    "ACCENT_START":"#FF2975","ACCENT_END":"#8C1EFF",
    "CANVAS_BG":"#060606",
}
THEME_DRACULA={
    "BG":"#282A36","BG_DARK":"#21222C","PANEL":"#44475A","WHITE":"#44475A","BLACK":"#191A21",
    "TEXT":"#F8F8F2","TEXT_DIM":"#6272A4","TEXT_BLUE":"#8BE9FD",
    "LIME":"#FF79C6","LIME_DK":"#D962A8","LIME_LT":"#FFB2DD",
    "BLUE_HL":"#BD93F9","RED":"#FF5555","YELLOW":"#F1FA8C","ORANGE":"#FFB86C",
    "TOOLBAR":"#21222C","BORDER_L":"#44475A","BORDER_D":"#191A21","INPUT_BG":"#44475A","TROUGH":"#44475A",
    "CARD_BG":"#44475A","CARD_BORDER":"#6272A4","BTN_HOVER":"#6272A4",
    "LIME_HOVER":"#D962A8","ORANGE_HOVER":"#E89C50",
    "INPUT_BORDER":"#6272A4","INPUT_FOCUS":"#BD93F9","TAB_ACTIVE":"#FF79C6",
    "SUCCESS":"#50FA7B","WARNING":"#F1FA8C","ERROR":"#FF5555","INFO":"#8BE9FD",
    "SURFACE":"#44475A","SURFACE_2":"#282A36","SURFACE_3":"#21222C",
    "ACCENT_START":"#FF79C6","ACCENT_END":"#BD93F9",
    "CANVAS_BG":"#191A21",
}
THEME_CATPPUCCIN={
    "BG":"#1E1E2E","BG_DARK":"#181825","PANEL":"#313244","WHITE":"#313244","BLACK":"#11111B",
    "TEXT":"#CDD6F4","TEXT_DIM":"#6C7086","TEXT_BLUE":"#89DCEB",
    "LIME":"#CBA6F7","LIME_DK":"#B490E0","LIME_LT":"#DFC0FF",
    "BLUE_HL":"#89B4FA","RED":"#F38BA8","YELLOW":"#F9E2AF","ORANGE":"#FAB387",
    "TOOLBAR":"#181825","BORDER_L":"#45475A","BORDER_D":"#11111B","INPUT_BG":"#313244","TROUGH":"#45475A",
    "CARD_BG":"#313244","CARD_BORDER":"#45475A","BTN_HOVER":"#45475A",
    "LIME_HOVER":"#B490E0","ORANGE_HOVER":"#E09070",
    "INPUT_BORDER":"#45475A","INPUT_FOCUS":"#89B4FA","TAB_ACTIVE":"#CBA6F7",
    "SUCCESS":"#A6E3A1","WARNING":"#F9E2AF","ERROR":"#F38BA8","INFO":"#89DCEB",
    "SURFACE":"#313244","SURFACE_2":"#1E1E2E","SURFACE_3":"#181825",
    "ACCENT_START":"#CBA6F7","ACCENT_END":"#F5C2E7",
    "CANVAS_BG":"#11111B",
}
THEME_TOKYO={
    "BG":"#1A1B26","BG_DARK":"#16161E","PANEL":"#292E42","WHITE":"#292E42","BLACK":"#0D0E16",
    "TEXT":"#C0CAF5","TEXT_DIM":"#565F89","TEXT_BLUE":"#7DCFFF",
    "LIME":"#7AA2F7","LIME_DK":"#5D7FD4","LIME_LT":"#A0BEF9",
    "BLUE_HL":"#BB9AF7","RED":"#F7768E","YELLOW":"#E0AF68","ORANGE":"#FF9E64",
    "TOOLBAR":"#16161E","BORDER_L":"#3B4261","BORDER_D":"#0D0E16","INPUT_BG":"#292E42","TROUGH":"#3B4261",
    "CARD_BG":"#292E42","CARD_BORDER":"#3B4261","BTN_HOVER":"#3B4261",
    "LIME_HOVER":"#5D7FD4","ORANGE_HOVER":"#E0844A",
    "INPUT_BORDER":"#3B4261","INPUT_FOCUS":"#BB9AF7","TAB_ACTIVE":"#7AA2F7",
    "SUCCESS":"#9ECE6A","WARNING":"#E0AF68","ERROR":"#F7768E","INFO":"#7DCFFF",
    "SURFACE":"#292E42","SURFACE_2":"#1A1B26","SURFACE_3":"#16161E",
    "ACCENT_START":"#7AA2F7","ACCENT_END":"#BB9AF7",
    "CANVAS_BG":"#0D0E16",
}
THEME_SPOTIFY={
    "BG":"#121212","BG_DARK":"#0A0A0A","PANEL":"#212121","WHITE":"#282828","BLACK":"#060606",
    "TEXT":"#FFFFFF","TEXT_DIM":"#B3B3B3","TEXT_BLUE":"#1ED760",
    "LIME":"#1DB954","LIME_DK":"#169C46","LIME_LT":"#4ADE80",
    "BLUE_HL":"#1DB954","RED":"#E91429","YELLOW":"#F59B23","ORANGE":"#E8590C",
    "TOOLBAR":"#0A0A0A","BORDER_L":"#333333","BORDER_D":"#0A0A0A","INPUT_BG":"#282828","TROUGH":"#333333",
    "CARD_BG":"#212121","CARD_BORDER":"#333333","BTN_HOVER":"#333333",
    "LIME_HOVER":"#169C46","ORANGE_HOVER":"#C74E0A",
    "INPUT_BORDER":"#333333","INPUT_FOCUS":"#1DB954","TAB_ACTIVE":"#1DB954",
    "SUCCESS":"#1DB954","WARNING":"#F59B23","ERROR":"#E91429","INFO":"#1ED760",
    "SURFACE":"#212121","SURFACE_2":"#121212","SURFACE_3":"#0A0A0A",
    "ACCENT_START":"#1DB954","ACCENT_END":"#1ED760",
    "CANVAS_BG":"#060606",
}
THEME_CLASSIC={
    "BG":"#000000","BG_DARK":"#000000","PANEL":"#1A1A1A","WHITE":"#1A1A1A","BLACK":"#000000",
    "TEXT":"#E0E0E0","TEXT_DIM":"#808080","TEXT_BLUE":"#3CFF3C",
    "LIME":"#1EFF00","LIME_DK":"#18CC00","LIME_LT":"#5AFF3C",
    "BLUE_HL":"#32CD32","RED":"#FF3333","YELLOW":"#FFFF00","ORANGE":"#FF8C00",
    "TOOLBAR":"#0A0A0A","BORDER_L":"#2D2D2D","BORDER_D":"#000000","INPUT_BG":"#1A1A1A","TROUGH":"#2D2D2D",
    "CARD_BG":"#1A1A1A","CARD_BORDER":"#2D2D2D","BTN_HOVER":"#2D2D2D",
    "LIME_HOVER":"#18CC00","ORANGE_HOVER":"#D47200",
    "INPUT_BORDER":"#2D2D2D","INPUT_FOCUS":"#1EFF00","TAB_ACTIVE":"#1EFF00",
    "SUCCESS":"#1EFF00","WARNING":"#FFFF00","ERROR":"#FF3333","INFO":"#3CFF3C",
    "SURFACE":"#1A1A1A","SURFACE_2":"#0A0A0A","SURFACE_3":"#000000",
    "ACCENT_START":"#1EFF00","ACCENT_END":"#02E102",
    "CANVAS_BG":"#000000",
}
THEME_NORD={
    "BG":"#2E3440","BG_DARK":"#272C36","PANEL":"#3B4252","WHITE":"#3B4252","BLACK":"#242933",
    "TEXT":"#D8DEE9","TEXT_DIM":"#4C566A","TEXT_BLUE":"#88C0D0",
    "LIME":"#88C0D0","LIME_DK":"#6EA8B8","LIME_LT":"#8FBCBB",
    "BLUE_HL":"#5E81AC","RED":"#BF616A","YELLOW":"#EBCB8B","ORANGE":"#D08770",
    "TOOLBAR":"#272C36","BORDER_L":"#434C5E","BORDER_D":"#242933","INPUT_BG":"#3B4252","TROUGH":"#434C5E",
    "CARD_BG":"#3B4252","CARD_BORDER":"#434C5E","BTN_HOVER":"#434C5E",
    "LIME_HOVER":"#6EA8B8","ORANGE_HOVER":"#B8705C",
    "INPUT_BORDER":"#434C5E","INPUT_FOCUS":"#5E81AC","TAB_ACTIVE":"#88C0D0",
    "SUCCESS":"#A3BE8C","WARNING":"#EBCB8B","ERROR":"#BF616A","INFO":"#88C0D0",
    "SURFACE":"#3B4252","SURFACE_2":"#2E3440","SURFACE_3":"#272C36",
    "ACCENT_START":"#88C0D0","ACCENT_END":"#5E81AC",
    "CANVAS_BG":"#242933",
}
THEME_GRUVBOX={
    "BG":"#282828","BG_DARK":"#1D2021","PANEL":"#3C3836","WHITE":"#3C3836","BLACK":"#1D2021",
    "TEXT":"#EBDBB2","TEXT_DIM":"#665C54","TEXT_BLUE":"#83A598",
    "LIME":"#D79921","LIME_DK":"#B57B14","LIME_LT":"#FABD2F",
    "BLUE_HL":"#458588","RED":"#CC241D","YELLOW":"#FABD2F","ORANGE":"#D65D0E",
    "TOOLBAR":"#1D2021","BORDER_L":"#504945","BORDER_D":"#1D2021","INPUT_BG":"#3C3836","TROUGH":"#504945",
    "CARD_BG":"#3C3836","CARD_BORDER":"#504945","BTN_HOVER":"#504945",
    "LIME_HOVER":"#B57B14","ORANGE_HOVER":"#AF4E0D",
    "INPUT_BORDER":"#504945","INPUT_FOCUS":"#458588","TAB_ACTIVE":"#D79921",
    "SUCCESS":"#98971A","WARNING":"#FABD2F","ERROR":"#CC241D","INFO":"#83A598",
    "SURFACE":"#3C3836","SURFACE_2":"#282828","SURFACE_3":"#1D2021",
    "ACCENT_START":"#D79921","ACCENT_END":"#D65D0E",
    "CANVAS_BG":"#1D2021",
}
THEME_LIVEWIRE={
    "BG":"#080C12","BG_DARK":"#040810","PANEL":"#101820","WHITE":"#142030","BLACK":"#020408",
    "TEXT":"#E0F4FF","TEXT_DIM":"#4A7A90","TEXT_BLUE":"#48F7FF",
    "LIME":"#00E5FF","LIME_DK":"#00B8D4","LIME_LT":"#48F7FF",
    "BLUE_HL":"#0066FF","RED":"#FF1744","YELLOW":"#FFD600","ORANGE":"#FFAB00",
    "TOOLBAR":"#0A1018","BORDER_L":"#1A2A38","BORDER_D":"#040810","INPUT_BG":"#101820","TROUGH":"#1A2A38",
    "CARD_BG":"#101820","CARD_BORDER":"#1A2A38","BTN_HOVER":"#1A2A38",
    "LIME_HOVER":"#00B8D4","ORANGE_HOVER":"#E09600",
    "INPUT_BORDER":"#1A2A38","INPUT_FOCUS":"#00E5FF","TAB_ACTIVE":"#00E5FF",
    "SUCCESS":"#00E676","WARNING":"#FFD600","ERROR":"#FF1744","INFO":"#48F7FF",
    "SURFACE":"#101820","SURFACE_2":"#080C12","SURFACE_3":"#040810",
    "ACCENT_START":"#00E5FF","ACCENT_END":"#0066FF",
    "CANVAS_BG":"#020408",
}
THEMES={"livewire":THEME_LIVEWIRE,"light":THEME_LIGHT,"dark":THEME_DARK,"modern":THEME_MODERN,
        "synthwave":THEME_SYNTHWAVE,"dracula":THEME_DRACULA,"catppuccin":THEME_CATPPUCCIN,
        "tokyo":THEME_TOKYO,"spotify":THEME_SPOTIFY,"classic":THEME_CLASSIC,
        "nord":THEME_NORD,"gruvbox":THEME_GRUVBOX}

# Current theme vars — initialized to LiveWire (default)
BG="#080C12"; BG_DARK="#040810"; PANEL="#101820"; WHITE="#142030"; BLACK="#020408"
TEXT="#E0F4FF"; TEXT_DIM="#4A7A90"; TEXT_BLUE="#48F7FF"
LIME="#00E5FF"; LIME_DK="#00B8D4"; LIME_LT="#48F7FF"
BLUE_HL="#0066FF"; RED="#FF1744"; YELLOW="#FFD600"; ORANGE="#FFAB00"
TOOLBAR="#0A1018"; BORDER_L="#1A2A38"; BORDER_D="#040810"; INPUT_BG="#101820"; TROUGH="#1A2A38"
CARD_BG="#101820"; CARD_BORDER="#1A2A38"; BTN_HOVER="#1A2A38"
LIME_HOVER="#00B8D4"; ORANGE_HOVER="#E09600"
INPUT_BORDER="#1A2A38"; INPUT_FOCUS="#00E5FF"; TAB_ACTIVE="#00E5FF"
SUCCESS="#00E676"; WARNING="#FFD600"; ERROR="#FF1744"; INFO="#48F7FF"
SURFACE="#101820"; SURFACE_2="#080C12"; SURFACE_3="#040810"
ACCENT_START="#00E5FF"; ACCENT_END="#0066FF"; CANVAS_BG="#020408"

def apply_theme(mode="livewire"):
    """Apply theme palette to module-level color vars."""
    if isinstance(mode,bool): mode="dark" if mode else "light"  # backward compat
    t=THEMES.get(mode,THEME_LIVEWIRE)
    g=globals()
    for k,v in t.items(): g[k]=v
    # Modern fonts for all themes (Segoe UI everywhere)
    g["F_TITLE"]=("Segoe UI Semibold",18); g["F_LOGO"]=("Segoe UI",20,"bold")
    g["F_BODY"]=("Segoe UI",10); g["F_BOLD"]=("Segoe UI Semibold",10)
    g["F_SMALL"]=("Segoe UI",9); g["F_BTN"]=("Segoe UI Semibold",9)
    g["F_MONO"]=("Cascadia Code",9); g["F_TAB"]=("Segoe UI Semibold",9)
    g["F_STATUS"]=("Segoe UI",8); g["F_HEADER"]=("Segoe UI Semibold",13)
    g["F_SECTION"]=("Segoe UI Semibold",10)
    g["F_H1"]=("Segoe UI Semibold",24); g["F_H2"]=("Segoe UI Semibold",20)
    g["F_H3"]=("Segoe UI Semibold",16); g["F_H4"]=("Segoe UI Semibold",13)

F_TITLE=("Segoe UI Semibold",18); F_LOGO=("Segoe UI",20,"bold"); F_BODY=("Segoe UI",10)
F_BOLD=("Segoe UI Semibold",10); F_SMALL=("Segoe UI",9); F_BTN=("Segoe UI Semibold",9)
F_MONO=("Cascadia Code",9); F_TAB=("Segoe UI Semibold",9); F_STATUS=("Segoe UI",8)
F_HEADER=("Segoe UI Semibold",13); F_SECTION=("Segoe UI Semibold",10)
F_H1=("Segoe UI Semibold",24); F_H2=("Segoe UI Semibold",20)
F_H3=("Segoe UI Semibold",16); F_H4=("Segoe UI Semibold",13)

def _lerp_color(c1,c2,t):
    """Linear interpolate between two hex colors. t in [0,1]."""
    r1,g1,b1=int(c1[1:3],16),int(c1[3:5],16),int(c1[5:7],16)
    r2,g2,b2=int(c2[1:3],16),int(c2[3:5],16),int(c2[5:7],16)
    r=int(r1+(r2-r1)*t); g=int(g1+(g2-g1)*t); b=int(b1+(b2-b1)*t)
    return f"#{r:02x}{g:02x}{b:02x}"

# ── App Constants ─────────────────────────────────────────────────────────────
CLIPBOARD_POLL_MS = 1500
CLIPBOARD_INITIAL_DELAY_MS = 2000
STATUS_PULSE_MS = 1500
PLAYER_UPDATE_MS = 500
SCHEDULER_POLL_SEC = 30
EQ_BAR_COUNT = 32
EQ_PEAK_DECAY = 0.03
WAVEFORM_W = 600
WAVEFORM_H = 80
PLAYER_WAVEFORM_W = 500
PLAYER_WAVEFORM_H = 50
LOGO_BAR_HEIGHT = 48
HISTORY_MAX = 300
RECENT_DL_MAX = 20
MAX_PLAYLIST_GEN = 20
MAX_URL_LENGTH = 500
FILENAME_MAX_LENGTH = 200
NETWORK_TIMEOUT = 30
FFMPEG_TIMEOUT = 600
# Editor
EDITOR_UNDO_MAX = 50
EDITOR_WAVEFORM_H = 100
EDITOR_FADE_DEFAULT_MS = 500
# Recorder
RECORDER_SAMPLE_RATE = 44100
RECORDER_CHANNELS = 1
RECORDER_CHUNK = 1024
RECORDER_VU_UPDATE_MS = 50
# Spectrogram
SPECTROGRAM_FFT = 2048
SPECTROGRAM_HOP = 512
SPECTROGRAM_CMAP = "viridis"
# Pitch/Time
PITCH_SEMITONE_RANGE = 12
TEMPO_RANGE = (0.25, 4.0)

AUDIO_FMTS=["mp3","wav","aac","flac","ogg","m4a","opus"]
VIDEO_FMTS=["mp4","mkv","webm","avi","mov"]
QUALITIES=["best","2160p","1440p","1080p","720p","480p","360p","worst"]
CONV_AUDIO=["mp3","wav","flac","aac","ogg","m4a","opus"]
CONV_VIDEO=["mp4","mkv","webm","avi","mov","gif"]

def _migrate_config(name):
    """Migrate old .ytdl_* config to .limewire_* if needed."""
    new=os.path.join(os.path.expanduser("~"),f".limewire_{name}.json")
    if not os.path.exists(new):
        old=os.path.join(os.path.expanduser("~"),f".ytdl_{name}.json")
        if os.path.exists(old):
            try: os.rename(old,new)
            except Exception: pass
    return new
HISTORY_FILE=_migrate_config("history")
SCHEDULE_FILE=_migrate_config("schedule")
SETTINGS_FILE=_migrate_config("settings")
QUEUE_FILE=_migrate_config("queue")
ANALYSIS_CACHE_FILE=_migrate_config("analysis_cache")
SUPPRESS=("No supported JavaScript","impersonat","Only deno","js-runtimes","Remote components")
ACOUSTID_KEY=os.environ.get("ACOUSTID_API_KEY","vNReaS8VLo")
YDL_BASE={"remote_components":["ejs:github"],"socket_timeout":NETWORK_TIMEOUT}
def ydl_opts(**kw): return {**YDL_BASE, **kw}

URL_PATTERNS=[re.compile(r'https?://(?:www\.)?youtube\.com/watch\?v=[\w-]+'),
    re.compile(r'https?://youtu\.be/[\w-]+'),re.compile(r'https?://(?:www\.)?soundcloud\.com/[\w-]+/[\w-]+'),
    re.compile(r'https?://\S+\.\S+')]

def load_json(p,d):
    try:
        with open(p) as f: return json.load(f)
    except Exception as e:
        if os.path.exists(p): _log.warning("Failed to load %s: %s",p,e)
        return d
def save_json(p,d):
    """Atomic JSON write — write to tmp file then rename to prevent corruption."""
    try:
        tmp=p+".tmp"
        with open(tmp,"w") as f: json.dump(d,f,indent=2)
        os.replace(tmp,p)  # atomic on same filesystem
    except Exception: pass
def fmt_duration(s):
    try: return str(datetime.timedelta(seconds=int(s)))
    except Exception: return "--:--"
def fetch_thumbnail(url,size=(120,80)):
    try:
        with urllib.request.urlopen(url,timeout=5) as r: data=r.read()
        with Image.open(BytesIO(data)) as raw:
            img=raw.convert("RGB"); img.thumbnail(size,Image.LANCZOS); return img
    except Exception: return None
_BLOCKED_SCHEMES = frozenset({"file","ftp","ftps","rtsp","rtmp","smb","ssh","telnet","data"})
def is_url(t):
    t=t.strip()
    if not t or len(t)>MAX_URL_LENGTH: return False
    # Block dangerous URI schemes (file://, ftp://, rtsp://, etc.)
    scheme=t.split("://",1)[0].lower() if "://" in t else ""
    if scheme in _BLOCKED_SCHEMES: return False
    return any(p.match(t) for p in URL_PATTERNS)
_WIN_RESERVED = frozenset({"CON","PRN","AUX","NUL"} |
    {f"COM{i}" for i in range(1,10)} | {f"LPT{i}" for i in range(1,10)})
def sanitize_filename(n):
    n=re.sub(r'[<>:"/\\|?*\x00-\x1f]','',n); n=n.strip('. ')
    # Windows reserved device names (CON, PRN, NUL, COM1-9, LPT1-9)
    base=n.split('.')[0].upper()
    if base in _WIN_RESERVED: n=f"_{n}"
    return n[:FILENAME_MAX_LENGTH] if n else "untitled"
_SOURCE_PATTERNS = [
    ("youtube.com","YouTube"),("youtu.be","YouTube"),("soundcloud.com","SoundCloud"),
    ("twitter.com","X/Twitter"),("x.com","X/Twitter"),("bandcamp.com","Bandcamp"),
    ("spotify.com","Spotify"),("open.spotify","Spotify"),("music.apple.com","Apple Music"),
    ("vimeo.com","Vimeo"),("twitch.tv","Twitch"),("dailymotion.com","Dailymotion"),
    ("dai.ly","Dailymotion"),("tiktok.com","TikTok"),("instagram.com","Instagram"),
    ("reddit.com","Reddit"),("redd.it","Reddit"),("facebook.com","Facebook"),
    ("fb.watch","Facebook"),("rumble.com","Rumble"),("odysee.com","Odysee"),
    ("bilibili.com","Bilibili"),("kick.com","Kick"),
]
def detect_source(url):
    u=url.lower()
    for pat,src in _SOURCE_PATTERNS:
        if pat in u: return src
    return "Web"

_FORMAT_PATTERNS = [
    ("youtube.com",("audio","mp3")),("youtu.be",("audio","mp3")),
    ("soundcloud.com",("audio","mp3")),("bandcamp.com",("audio","flac")),
    ("spotify.com",("audio","mp3")),("open.spotify",("audio","mp3")),
    ("music.apple.com",("audio","mp3")),
    ("twitter.com",("video","mp4")),("x.com",("video","mp4")),
    ("vimeo.com",("video","mp4")),("dailymotion.com",("video","mp4")),
    ("dai.ly",("video","mp4")),("tiktok.com",("video","mp4")),
    ("instagram.com",("video","mp4")),("reddit.com",("video","mp4")),
    ("redd.it",("video","mp4")),("facebook.com",("video","mp4")),
    ("fb.watch",("video","mp4")),("twitch.tv",("video","mp4")),
    ("rumble.com",("video","mp4")),("kick.com",("video","mp4")),
    ("bilibili.com",("video","mp4")),("odysee.com",("video","mp4")),
]
def auto_detect_format(url):
    """Suggest format based on URL source."""
    u=url.lower()
    for pat,result in _FORMAT_PATTERNS:
        if pat in u: return result
    return None,None

def open_folder(path):
    if os.path.exists(path):
        try:
            if sys.platform=="win32": os.startfile(path)
            elif sys.platform=="darwin": subprocess.run(["open",path],timeout=10)
            else: subprocess.run(["xdg-open",path],timeout=10)
        except Exception: pass

def _ui(widget, fn, *args):
    """Schedule fn(*args) on the main thread via widget.after(0, ...)."""
    widget.after(0, lambda: fn(*args))

class _SilentLogger:
    def debug(self,m): pass
    def warning(self,m): pass
    def error(self,m): pass

# ═══════════════════════════════════════════════════════════════════════════════
# FL STUDIO & SERATO HELPERS
# ═══════════════════════════════════════════════════════════════════════════════

FL_STUDIO_PATHS=[
    r"C:\Program Files\Image-Line\FL Studio 2025\FL64.exe",
    r"C:\Program Files\Image-Line\FL Studio 2024\FL64.exe",
    r"C:\Program Files\Image-Line\FL Studio 21\FL64.exe",
    r"C:\Program Files\Image-Line\FL Studio 20\FL64.exe",
    r"C:\Program Files (x86)\Image-Line\FL Studio 20\FL64.exe",
]

def find_fl_studio():
    """Auto-detect FL Studio installation path on Windows."""
    for p in FL_STUDIO_PATHS:
        if os.path.exists(p): return p
    if sys.platform=="win32":
        try:
            import winreg
            for kp in [r"SOFTWARE\Image-Line\FL Studio",r"SOFTWARE\WOW6432Node\Image-Line\FL Studio"]:
                try:
                    with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,kp) as key:
                        val,_=winreg.QueryValueEx(key,"InstallPath")
                        exe=os.path.join(val,"FL64.exe")
                        if os.path.exists(exe): return exe
                except Exception: continue
        except Exception: pass
    return None

def open_in_fl_studio(filepath=None,fl_path=None):
    """Launch FL Studio, optionally with a project file."""
    fl=fl_path or find_fl_studio()
    if not fl: return False,"FL Studio not found. Set path in Tools menu."
    try:
        if filepath and filepath.lower().endswith(".flp"):
            subprocess.Popen([fl,filepath])
        else:
            subprocess.Popen([fl])
        return True,None
    except Exception as e:
        return False,str(e)[:80]

def export_stems_for_fl(stem_dir,track_name,bpm=None,key=None,output_dir=None):
    """Organize Demucs stems for FL Studio import with numbered prefixes."""
    import shutil
    if not output_dir:
        output_dir=os.path.join(os.path.dirname(stem_dir),"FL_Export",track_name)
    os.makedirs(output_dir,exist_ok=True)
    stem_names={"vocals":"01_Vocals","drums":"02_Drums","bass":"03_Bass",
                "other":"04_Other","piano":"05_Piano","guitar":"06_Guitar"}
    copied=[]
    for wav in sorted(os.listdir(stem_dir)):
        if not wav.endswith(".wav"): continue
        stem_type=os.path.splitext(wav)[0]
        prefix=stem_names.get(stem_type,stem_type)
        suffix=""
        if bpm: suffix+=f"_{int(bpm)}bpm"
        if key: suffix+=f"_{key.replace(' ','')}"
        new_name=f"{prefix}{suffix}.wav"
        shutil.copy2(os.path.join(stem_dir,wav),os.path.join(output_dir,new_name))
        copied.append(new_name)
    return output_dir,copied

def create_fl_project(stem_dir,track_name,bpm=None,output_path=None):
    """Generate an FL Studio .flp project with stems loaded on channels."""
    if not HAS_PYFLP: return None,"pyflp not installed. Run: pip install pyflp"
    try:
        import pyflp
        # Create a new project
        project=pyflp.Project()
        if bpm: project.tempo=float(bpm)
        # Add stems as sampler channels
        stem_files=sorted([f for f in os.listdir(stem_dir) if f.endswith(".wav")])
        for sf in stem_files:
            stem_path=os.path.abspath(os.path.join(stem_dir,sf))
            ch=project.channels.add_sampler()
            ch.name=os.path.splitext(sf)[0].capitalize()
            ch.sample_path=stem_path
        if not output_path:
            output_path=os.path.join(os.path.dirname(stem_dir),f"{track_name}_stems.flp")
        project.save(output_path)
        return output_path,None
    except Exception as e:
        return None,str(e)[:120]

SERATO_BASE=os.path.join(os.path.expanduser("~"),"Music","_Serato_")
SERATO_SUBCRATES=os.path.join(SERATO_BASE,"Subcrates")

def write_serato_tags(filepath,bpm=None,key=None):
    """Write Serato-compatible BPM/Key tags to an MP3 file."""
    try:
        from mutagen.id3 import GEOB,TBPM,TKEY
        audio=ID3(filepath)
        if key:
            serato_key=key_to_serato_tkey(key)
            if serato_key: audio["TKEY"]=TKEY(encoding=3,text=serato_key)
        if bpm:
            audio["TBPM"]=TBPM(encoding=3,text=str(int(round(bpm))))
            # Serato Autotags GEOB frame
            bpm_s=f"{bpm:.2f}\x00"; gain_s=f"0.000\x00"; gaindb_s=f"0.000\x00"
            autotag_data=b"\x01\x01"+bpm_s.encode("ascii")+gain_s.encode("ascii")+gaindb_s.encode("ascii")
            audio["GEOB:Serato Autotags"]=GEOB(encoding=0,mime="application/octet-stream",
                desc="Serato Autotags",data=autotag_data)
        audio.save()
        return True,None
    except Exception as e:
        return False,str(e)[:80]

def add_to_serato_crate(filepath,crate_name="LimeWire"):
    """Add a track to a Serato crate. Creates crate if it doesn't exist."""
    if HAS_SERATO:
        try:
            crate_path=os.path.join(SERATO_SUBCRATES,f"{crate_name}.crate")
            os.makedirs(SERATO_SUBCRATES,exist_ok=True)
            crate=SeratoCrate(crate_path) if os.path.exists(crate_path) else SeratoCrate()
            crate.add_track(filepath)
            crate.save(crate_path)
            return True,None
        except Exception as e:
            return False,str(e)[:80]
    return _write_crate_manual(filepath,crate_name)

def _write_crate_tag(f,tag_name,string_value):
    encoded=string_value.encode("utf-16-be")
    f.write(tag_name.encode("ascii")); f.write(struct.pack(">I",len(encoded))); f.write(encoded)

def _write_crate_tag_raw(f,tag_name,raw_data):
    f.write(tag_name.encode("ascii")); f.write(struct.pack(">I",len(raw_data))); f.write(raw_data)

def _encode_crate_str(tag_name,string_value):
    encoded=string_value.encode("utf-16-be")
    return tag_name.encode("ascii")+struct.pack(">I",len(encoded))+encoded

def _read_crate_tracks(crate_path):
    tracks=[]
    try:
        with open(crate_path,"rb") as f: data=f.read()
        pos=0
        while pos<len(data)-8:
            tag=data[pos:pos+4].decode("ascii",errors="replace")
            length=struct.unpack(">I",data[pos+4:pos+8])[0]
            payload=data[pos+8:pos+8+length]
            if tag=="otrk":
                ip=0
                while ip<len(payload)-8:
                    it=payload[ip:ip+4].decode("ascii",errors="replace")
                    il=struct.unpack(">I",payload[ip+4:ip+8])[0]
                    if it=="ptrk": tracks.append(payload[ip+8:ip+8+il].decode("utf-16-be"))
                    ip+=8+il
            pos+=8+length
    except Exception: pass
    return tracks

def _write_crate_manual(filepath,crate_name="LimeWire"):
    """Write Serato .crate file manually without serato-tools."""
    crate_path=os.path.join(SERATO_SUBCRATES,f"{crate_name}.crate")
    os.makedirs(SERATO_SUBCRATES,exist_ok=True)
    existing=_read_crate_tracks(crate_path) if os.path.exists(crate_path) else []
    drive,rel_path=os.path.splitdrive(filepath)
    serato_path=rel_path.lstrip(os.sep).replace("\\","/")
    if serato_path in existing: return True,"Already in crate"
    existing.append(serato_path)
    with open(crate_path,"wb") as f:
        _write_crate_tag(f,"vrsn","1.0/Serato ScratchLive Crate")
        for track in existing:
            track_data=_encode_crate_str("ptrk",track)
            _write_crate_tag_raw(f,"otrk",track_data)
    return True,None

# ═══════════════════════════════════════════════════════════════════════════════
# ANALYSIS HELPERS
# ═══════════════════════════════════════════════════════════════════════════════

KEY_NAMES = ["C","C#","D","D#","E","F","F#","G","G#","A","A#","B"]
CAMELOT_MAP = {
    "C Major":"8B","C Minor":"5A","C# Major":"3B","C# Minor":"12A",
    "D Major":"10B","D Minor":"7A","D# Major":"5B","D# Minor":"2A",
    "E Major":"12B","E Minor":"9A","F Major":"7B","F Minor":"4A",
    "F# Major":"2B","F# Minor":"11A","G Major":"9B","G Minor":"6A",
    "G# Major":"4B","G# Minor":"1A","A Major":"11B","A Minor":"8A",
    "A# Major":"6B","A# Minor":"3A","B Major":"1B","B Minor":"10A",
}
CAMELOT_REVERSE = {v:k for k,v in CAMELOT_MAP.items()}

def key_to_camelot(key_str):
    """Convert standard key notation to Camelot. 'A Minor' -> '8A'."""
    return CAMELOT_MAP.get(key_str) if key_str else None

def key_to_serato_tkey(key_str):
    """Convert 'A Minor' -> 'Am', 'C Major' -> 'C' for Serato TKEY."""
    if not key_str: return None
    parts=key_str.split()
    if len(parts)!=2: return key_str
    root,mode=parts
    return root+"m" if mode=="Minor" else root

def analyze_bpm_key(filepath):
    """Detect BPM and musical key using librosa."""
    if not _ensure_librosa(): return {"bpm": None, "key": None, "error": "librosa not installed"}
    try:
        y, sr = librosa.load(filepath, sr=22050, mono=True, duration=120)
        # BPM
        tempo, _ = librosa.beat.beat_track(y=y, sr=sr)
        bpm = float(tempo[0]) if hasattr(tempo,'__len__') else float(tempo)
        # Key detection via chroma
        chroma = librosa.feature.chroma_cqt(y=y, sr=sr)
        chroma_avg = chroma.mean(axis=1)
        key_idx = int(chroma_avg.argmax())
        # Major/minor estimation
        major_profile = [6.35,2.23,3.48,2.33,4.38,4.09,2.52,5.19,2.39,3.66,2.29,2.88]
        minor_profile = [6.33,2.68,3.52,5.38,2.60,3.53,2.54,4.75,3.98,2.69,3.34,3.17]
        best_corr_maj = -1; best_corr_min = -1; best_maj = 0; best_min = 0
        for i in range(12):
            rolled = np.roll(chroma_avg, -i)
            cmaj = float(np.corrcoef(rolled, major_profile)[0,1])
            cmin = float(np.corrcoef(rolled, minor_profile)[0,1])
            if cmaj > best_corr_maj: best_corr_maj = cmaj; best_maj = i
            if cmin > best_corr_min: best_corr_min = cmin; best_min = i
        if best_corr_maj >= best_corr_min:
            key_str = f"{KEY_NAMES[best_maj]} Major"
        else:
            key_str = f"{KEY_NAMES[best_min]} Minor"
        return {"bpm": round(bpm, 1), "key": key_str}
    except Exception as e:
        return {"bpm": None, "key": None, "error": str(e)[:80]}

def analyze_loudness(filepath):
    """Measure LUFS and peak using pyloudnorm."""
    if not _ensure_loudness(): return {"lufs": None, "peak": None, "error": "pyloudnorm not installed"}
    try:
        data, rate = sf.read(filepath)
        if len(data.shape) == 1: data = data.reshape(-1, 1)
        meter = pyln.Meter(rate)
        lufs = meter.integrated_loudness(data)
        peak_db = 20 * np.log10(np.max(np.abs(data)) + 1e-10)
        return {"lufs": round(lufs, 1), "peak": round(peak_db, 1)}
    except Exception as e:
        return {"lufs": None, "peak": None, "error": str(e)[:80]}

def reduce_noise(filepath,output_path=None):
    """Apply AI noise reduction to audio file."""
    if not HAS_NOISEREDUCE: return None,"noisereduce not installed. Run: pip install noisereduce"
    try:
        data,rate=sf.read(filepath) if _ensure_loudness() else (None,None)
        if data is None: return None,"soundfile not installed"
        reduced=nr.reduce_noise(y=data,sr=rate)
        if not output_path:
            base,ext=os.path.splitext(filepath)
            output_path=f"{base}_clean{ext}"
        sf.write(output_path,reduced,rate)
        return output_path,None
    except Exception as e:
        return None,str(e)[:80]

def apply_effects_chain(filepath,effects_list,output_path=None):
    """Apply a chain of pedalboard effects to audio file.
    effects_list: list of pedalboard effect instances."""
    if not HAS_PEDALBOARD: return None,"pedalboard not installed. Run: pip install pedalboard"
    try:
        with pedalboard.io.AudioFile(filepath) as f:
            audio=f.read(f.frames); sr=f.samplerate
        board=pedalboard.Pedalboard(effects_list)
        processed=board(audio,sample_rate=sr)
        if not output_path:
            base,ext=os.path.splitext(filepath)
            output_path=f"{base}_fx{ext}"
        with pedalboard.io.AudioFile(output_path,"w",sr,processed.shape[0]) as f:
            f.write(processed)
        return output_path,None
    except Exception as e:
        return None,str(e)[:80]

def lookup_lyrics(title,artist="",api_key=None):
    """Search Genius for song lyrics."""
    if not HAS_LYRICS: return {"error":"lyricsgenius not installed. Run: pip install lyricsgenius"}
    key=api_key or os.environ.get("GENIUS_API_KEY","")
    if not key: return {"error":"Set Genius API key in Settings or GENIUS_API_KEY env var"}
    try:
        genius=lyricsgenius.Genius(key,timeout=15,retries=2,verbose=False)
        genius.remove_section_headers=True
        song=genius.search_song(title,artist)
        if song:
            return {"title":song.title,"artist":song.artist,"lyrics":song.lyrics,
                    "url":song.url,"album":getattr(song,"album",""),
                    "thumbnail":getattr(song,"song_art_image_thumbnail_url","")}
        return {"error":"No lyrics found"}
    except Exception as e:
        return {"error":str(e)[:80]}

def get_harmonic_matches(key_str,library_keys):
    """Find harmonically compatible tracks from a library of {file: key_str} entries.
    Returns list of (file, key, compatibility) sorted by compatibility."""
    if not key_str: return []
    camelot=key_to_camelot(key_str)
    if not camelot: return []
    num=int(camelot[:-1]); letter=camelot[-1]
    # Compatible Camelot codes: same, ±1 on wheel, same number other letter
    compat=set()
    compat.add(camelot)  # same key
    compat.add(f"{(num%12)+1}{letter}")  # +1
    compat.add(f"{((num-2)%12)+1}{letter}")  # -1
    other="A" if letter=="B" else "B"
    compat.add(f"{num}{other}")  # parallel major/minor
    results=[]
    for f,k in library_keys.items():
        c=key_to_camelot(k)
        if c and c in compat:
            lvl="perfect" if c==camelot else "harmonic"
            results.append((f,k,c,lvl))
    return results

def identify_shazam(filepath):
    """Identify track using Shazam — uses shazamio if available, else unavailable."""
    if not HAS_SHAZAM:
        return {"title": None, "artist": None, "error": "shazamio not installed (needs Python <=3.12). Use Shazam Search instead."}
    try:
        async def _run():
            shazam = ShazamEngine()
            result = await shazam.recognize(filepath)
            return result
        loop = asyncio.new_event_loop()
        try:
            result = loop.run_until_complete(_run())
        finally:
            loop.close()
        track = result.get("track", {})
        if track:
            return {"title": track.get("title"), "artist": track.get("subtitle"),
                    "genre": track.get("genres", {}).get("primary", ""),
                    "album": track.get("sections", [{}])[0].get("metadata", [{}])[0].get("text", "") if track.get("sections") else "",
                    "shazam_url": track.get("url", "")}
        return {"title": None, "artist": None, "error": "No match found"}
    except Exception as e:
        return {"title": None, "artist": None, "error": str(e)[:80]}

def search_shazam(query):
    """Search Shazam catalog by text query — pure HTTP, no Rust, always works."""
    try:
        url = f"https://www.shazam.com/services/amapi/v1/catalog/US/search?types=songs&term={requests.utils.quote(query)}&limit=5"
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
        resp = requests.get(url, headers=headers, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            songs = data.get("results", {}).get("songs", {}).get("data", [])
            if songs:
                s = songs[0].get("attributes", {})
                return {"title": s.get("name"), "artist": s.get("artistName"),
                        "album": s.get("albumName", ""), "genre": s.get("genreNames", [""])[0],
                        "url": s.get("url", ""), "duration_ms": s.get("durationInMillis", 0)}
        # Fallback: try the v1 web search
        url2 = f"https://www.shazam.com/services/search/v3/en/US/web/search?query={requests.utils.quote(query)}&numResults=5&type=SONGS"
        resp2 = requests.get(url2, headers=headers, timeout=10)
        if resp2.status_code == 200:
            data2 = resp2.json()
            tracks = data2.get("tracks", {}).get("hits", [])
            if tracks:
                t = tracks[0].get("track", {})
                return {"title": t.get("title"), "artist": t.get("subtitle"),
                        "genre": t.get("genres", {}).get("primary", ""),
                        "url": t.get("url", "")}
        return {"error": "No results found"}
    except Exception as e:
        return {"error": str(e)[:80]}

def lookup_musicbrainz(title, artist):
    """Search MusicBrainz for detailed metadata."""
    if not HAS_MB: return {"error": "musicbrainzngs not installed"}
    try:
        result = musicbrainzngs.search_recordings(recording=title, artist=artist, limit=3)
        recs = result.get("recording-list", [])
        if recs:
            rec = recs[0]
            return {
                "mb_title": rec.get("title", ""),
                "mb_artist": rec.get("artist-credit-phrase", ""),
                "mb_album": rec.get("release-list", [{}])[0].get("title", "") if rec.get("release-list") else "",
                "mb_date": rec.get("release-list", [{}])[0].get("date", "") if rec.get("release-list") else "",
                "mb_id": rec.get("id", ""),
            }
        return {"error": "No MusicBrainz match"}
    except Exception as e:
        return {"error": str(e)[:80]}

def lookup_apple_music(title, artist=""):
    """Search iTunes/Apple Music catalog for track metadata. Public API, no auth needed."""
    try:
        query=f"{title} {artist}".strip()
        url=f"https://itunes.apple.com/search?term={requests.utils.quote(query)}&entity=song&limit=3"
        resp=requests.get(url,timeout=10)
        if resp.status_code==200:
            data=resp.json()
            results=data.get("results",[])
            if results:
                r=results[0]
                return {
                    "am_title":r.get("trackName",""),
                    "am_artist":r.get("artistName",""),
                    "am_album":r.get("collectionName",""),
                    "am_genre":r.get("primaryGenreName",""),
                    "am_date":r.get("releaseDate","")[:10] if r.get("releaseDate") else "",
                    "am_artwork":r.get("artworkUrl100","").replace("100x100","600x600"),
                    "am_preview":r.get("previewUrl",""),
                    "am_url":r.get("trackViewUrl",""),
                    "am_duration_ms":r.get("trackTimeMillis",0),
                }
        return {"error":"No Apple Music match"}
    except Exception as e:
        return {"error":str(e)[:80]}

def resolve_spotify_url(url):
    """Resolve a Spotify URL to track info using oEmbed API (public, no auth)."""
    try:
        oembed_url=f"https://open.spotify.com/oembed?url={requests.utils.quote(url)}"
        resp=requests.get(oembed_url,timeout=10)
        if resp.status_code==200:
            data=resp.json()
            title=data.get("title","")
            # oEmbed title format is typically "Song Name" or for playlists "Playlist Name"
            return {"title":title,"type":data.get("type","track"),"provider":"Spotify"}
        return {"error":f"Spotify oEmbed returned {resp.status_code}"}
    except Exception as e:
        return {"error":str(e)[:80]}

def spotify_to_youtube(url):
    """Resolve Spotify track URL → YouTube search URL for yt-dlp download."""
    info=resolve_spotify_url(url)
    if info.get("error"): return None,info["error"]
    title=info.get("title","")
    if not title: return None,"Could not extract title from Spotify"
    # Use yt-dlp's YouTube search
    search_url=f"ytsearch1:{title}"
    return search_url,None

def identify_acoustid(filepath):
    """Fingerprint and identify using AcoustID/Chromaprint."""
    if not HAS_ACOUSTID: return {"error": "pyacoustid not installed"}
    try:
        # pyacoustid needs fpcalc binary
        results = list(acoustid.match(ACOUSTID_KEY, filepath))
        if results:
            score, rid, title, artist = results[0]
            return {"title": title, "artist": artist, "score": round(score, 2), "recording_id": rid}
        return {"error": "No fingerprint match"}
    except Exception as e:
        return {"error": str(e)[:80]}

def generate_waveform_data(filepath, width=WAVEFORM_W, height=WAVEFORM_H):
    """Generate waveform amplitude data for visualization using ffmpeg."""
    try:
        cmd = ["ffmpeg", "-i", filepath, "-ac", "1", "-ar", "8000", "-f", "s16le", "-"]
        r = subprocess.run(cmd, capture_output=True, timeout=30)
        raw = r.stdout
        if not raw: return []
        if HAS_NUMPY:
            samples = np.frombuffer(raw, dtype=np.int16)
            chunk = max(1, len(samples) // width)
            trim = (len(samples) // chunk) * chunk
            reshaped = np.abs(samples[:trim].reshape(-1, chunk))
            bars = (reshaped.max(axis=1) / 32768.0).tolist()
        else:
            samples = struct.unpack(f"<{len(raw)//2}h", raw)
            chunk = max(1, len(samples) // width)
            bars = []
            for i in range(0, len(samples), chunk):
                seg = samples[i:i+chunk]
                if seg:
                    peak = max(abs(min(seg)), abs(max(seg)))
                    bars.append(peak / 32768.0)
        return bars[:width]
    except Exception:
        return []

def _demucs_cli_error(e):
    """Extract a useful error message from a subprocess error."""
    if hasattr(e, "stderr") and e.stderr:
        msg = e.stderr.decode("utf-8", errors="replace") if isinstance(e.stderr, bytes) else str(e.stderr)
        # Return last meaningful lines (skip blank)
        lines = [l.strip() for l in msg.strip().splitlines() if l.strip()]
        return "\n".join(lines[-5:]) if lines else str(e)[:200]
    return str(e)[:200]

def _patch_torchaudio_save():
    """Monkey-patch torchaudio.save to use soundfile when torchcodec is broken.
    torchaudio 2.9+ hardcodes save() → save_with_torchcodec() which needs
    FFmpeg shared DLLs (not just the CLI). Patch it to use soundfile instead."""
    try:
        import torchaudio
        # Test if save_with_torchcodec actually works
        try:
            import torchcodec  # noqa
            return  # torchcodec works, no patch needed
        except Exception:
            pass
        # torchcodec broken — replace save with soundfile-based version
        if _ensure_loudness():  # soundfile is available (imported as sf)
            import torch
            _orig_save = torchaudio.save
            def _sf_save(uri, src, sample_rate, channels_first=True, **kw):
                if isinstance(src, torch.Tensor):
                    data = src.numpy()
                    if channels_first and data.ndim == 2: data = data.T
                    sf.write(str(uri), data, sample_rate)
                else:
                    _orig_save(uri, src, sample_rate, channels_first=channels_first, **kw)
            torchaudio.save = _sf_save
    except Exception:
        pass

def run_demucs(filepath, output_dir, model="htdemucs", two_stems=None):
    """Run Demucs stem separation."""
    _patch_torchaudio_save()

    def _build_cmd():
        cmd = [sys.executable, "-m", "demucs", "-n", model, "-o", output_dir]
        if two_stems: cmd += ["--two-stems", two_stems]
        cmd.append(filepath)
        return cmd

    if not HAS_DEMUCS:
        try:
            subprocess.run(_build_cmd(), check=True, capture_output=True, timeout=600)
            return True
        except Exception as e:
            return f"Demucs not installed. Run: pip install demucs\n{_demucs_cli_error(e)}"
    # Try Python API first, catch SystemExit too (demucs calls sys.exit on error)
    try:
        import demucs.separate
        args = ["-n", model, "-o", output_dir]
        if two_stems:
            args += ["--two-stems", two_stems]
        args.append(filepath)
        demucs.separate.main(args)
        return True
    except (Exception, SystemExit) as e:
        api_err = str(e)[:200]
        # Fallback to CLI subprocess
        try:
            subprocess.run(_build_cmd(), check=True, capture_output=True, timeout=600)
            return True
        except Exception as e2:
            cli_err = _demucs_cli_error(e2)
            return f"Python API: {api_err}\nCLI: {cli_err}"


# ═══════════════════════════════════════════════════════════════════════════════
# AUDIO EDITING / RECORDING / SPECTROGRAM UTILITIES
# ═══════════════════════════════════════════════════════════════════════════════

def load_audio_pydub(filepath):
    """Load audio file into pydub AudioSegment."""
    if not _ensure_pydub(): return None, "pydub not installed. Run: pip install pydub"
    if not HAS_FFMPEG: return None, "FFmpeg required for audio loading"
    try: return AudioSegment.from_file(filepath), None
    except Exception as e: return None, str(e)[:80]

def export_audio_pydub(seg, path, fmt="mp3"):
    """Export pydub AudioSegment to file."""
    try: seg.export(path, format=fmt); return path, None
    except Exception as e: return None, str(e)[:80]

def audio_segment_to_waveform(seg, width=600, height=80):
    """Convert pydub AudioSegment to list of bar heights for waveform drawing."""
    samples = seg.get_array_of_samples()
    if not samples: return []
    chunk = max(1, len(samples) // width)
    bars = []
    for i in range(0, len(samples), chunk):
        sl = samples[i:i+chunk]
        if sl: bars.append(max(abs(min(sl)), abs(max(sl))))
    mx = max(bars) if bars else 1
    return [int(v / max(1, mx) * height) for v in bars]

def _get_colormap(name="viridis"):
    """Generate 256x3 RGB LUT for spectrogram coloring (no matplotlib needed)."""
    anchors = {
        "viridis": [(68,1,84),(59,82,139),(33,145,140),(94,201,98),(253,231,37)],
        "magma":   [(0,0,4),(81,18,124),(183,55,121),(254,159,109),(252,253,191)],
        "plasma":  [(13,8,135),(126,3,168),(204,71,120),(248,149,64),(240,249,33)],
        "inferno": [(0,0,4),(87,16,110),(188,55,84),(249,142,9),(252,255,164)],
    }
    pts = anchors.get(name, anchors["viridis"])
    lut = np.zeros((256, 3), dtype=np.uint8)
    seg_len = 256 // (len(pts) - 1)
    for i in range(len(pts) - 1):
        for j in range(seg_len):
            t = j / seg_len; idx = i * seg_len + j
            if idx < 256:
                lut[idx] = [int(pts[i][c] + (pts[i+1][c] - pts[i][c]) * t) for c in range(3)]
    # Fill remaining
    for idx in range((len(pts)-1)*seg_len, 256):
        lut[idx] = pts[-1]
    return lut

def generate_spectrogram_image(filepath, fft_size=SPECTROGRAM_FFT, hop=SPECTROGRAM_HOP,
                                cmap=SPECTROGRAM_CMAP, width=800, height=400):
    """Generate spectrogram as PIL Image using librosa + custom colormap."""
    if not _ensure_librosa(): return None, "librosa not installed"
    if not HAS_NUMPY: return None, "numpy not installed"
    try:
        y, sr = librosa.load(filepath, sr=22050, mono=True)
        S = librosa.amplitude_to_db(np.abs(librosa.stft(y, n_fft=fft_size, hop_length=hop)), ref=np.max)
        S_norm = np.clip((S + 80) / 80 * 255, 0, 255).astype(np.uint8)
        lut = _get_colormap(cmap)
        rgb = lut[S_norm]
        img = Image.fromarray(rgb[::-1].astype(np.uint8))
        return img.resize((width, height), Image.LANCZOS), None
    except Exception as e:
        return None, str(e)[:80]

def pitch_shift_audio(filepath, semitones, output_path=None):
    """Shift pitch by N semitones using pyrubberband."""
    if not _ensure_rubberband(): return None, "pyrubberband not installed. Run: pip install pyrubberband"
    if not _ensure_loudness(): return None, "soundfile not installed"
    try:
        y, sr = sf.read(filepath)
        shifted = pyrubberband.pitch_shift(y, sr, semitones)
        if not output_path:
            base, ext = os.path.splitext(filepath)
            output_path = f"{base}_pitch{semitones:+d}.wav"
        sf.write(output_path, shifted, sr)
        return output_path, None
    except Exception as e:
        return None, str(e)[:80]

def time_stretch_audio(filepath, rate, output_path=None):
    """Time-stretch audio by rate factor using pyrubberband."""
    if not _ensure_rubberband(): return None, "pyrubberband not installed. Run: pip install pyrubberband"
    if not _ensure_loudness(): return None, "soundfile not installed"
    try:
        y, sr = sf.read(filepath)
        stretched = pyrubberband.time_stretch(y, sr, rate)
        if not output_path:
            base, ext = os.path.splitext(filepath)
            output_path = f"{base}_tempo{rate:.2f}x.wav"
        sf.write(output_path, stretched, sr)
        return output_path, None
    except Exception as e:
        return None, str(e)[:80]

def _srt_timestamp(s):
    """Format seconds to SRT timestamp (HH:MM:SS,mmm)."""
    h, rem = divmod(int(s), 3600); m, sec = divmod(rem, 60)
    ms = int((s - int(s)) * 1000)
    return f"{h:02d}:{m:02d}:{sec:02d},{ms:03d}"


# ═══════════════════════════════════════════════════════════════════════════════
# MODERN UI WIDGETS
# ═══════════════════════════════════════════════════════════════════════════════

SP_XS=4; SP_SM=8; SP_MD=12; SP_LG=16; SP_XL=24

def _round_rect(cv,x1,y1,x2,y2,radius=10,**kw):
    """Draw a smooth rounded rectangle on a Canvas."""
    r=radius
    pts=[x1+r,y1, x2-r,y1, x2,y1, x2,y1+r,
         x2,y2-r, x2,y2, x2-r,y2, x1+r,y2,
         x1,y2, x1,y2-r, x1,y1+r, x1,y1, x1+r,y1]
    return cv.create_polygon(pts,smooth=True,**kw)

class ModernBtn(tk.Canvas):
    """Canvas-based rounded button with hover/press feedback."""
    def __init__(self,parent,text="",command=None,width=None,bg_color=None,fg_color=None,
                 hover_color=None,font=None,padx=16,pady=6,radius=8,**kw):
        self._bg_c=bg_color or BG
        self._fg_c=fg_color or TEXT
        self._hover_c=hover_color or BTN_HOVER
        self._font=font or F_BTN
        self._text=text
        self._cmd=command
        self._radius=radius
        self._padx=padx; self._pady=pady
        self._pressed=False
        # Measure text to set canvas size
        _tmp=tk.Label(parent,text=text,font=self._font)
        tw=_tmp.winfo_reqwidth(); th=_tmp.winfo_reqheight(); _tmp.destroy()
        if width: tw=max(tw,width*8)
        cw=tw+padx*2; ch=th+pady*2
        super().__init__(parent,width=cw,height=ch,bg=parent.cget("bg") if hasattr(parent,"cget") else BG,
                         highlightthickness=0,bd=0,cursor="hand2",**kw)
        self._cw=cw; self._ch=ch
        self._rect=_round_rect(self,1,1,cw-1,ch-1,radius=radius,fill=self._bg_c,outline="")
        self._label=self.create_text(cw//2,ch//2,text=text,font=self._font,fill=self._fg_c)
        self.bind("<Enter>",self._on_enter)
        self.bind("<Leave>",self._on_leave)
        self.bind("<ButtonPress-1>",self._on_press)
        self.bind("<ButtonRelease-1>",self._on_release)

    def _on_enter(self,e=None):
        self.itemconfig(self._rect,fill=self._hover_c)
    def _on_leave(self,e=None):
        self._pressed=False; self.itemconfig(self._rect,fill=self._bg_c)
    def _on_press(self,e=None):
        self._pressed=True
        self.itemconfig(self._rect,fill=_lerp_color(self._hover_c,"#000000",0.15))
    def _on_release(self,e=None):
        if self._pressed and self._cmd:
            self._pressed=False; self.itemconfig(self._rect,fill=self._hover_c)
            self._cmd()

    def config(self,**kw):
        self.configure(**kw)
    def configure(self,**kw):
        if "text" in kw: self._text=kw.pop("text"); self.itemconfig(self._label,text=self._text)
        if "bg" in kw:
            self._bg_c=kw.pop("bg"); self.itemconfig(self._rect,fill=self._bg_c)
        if "fg" in kw:
            self._fg_c=kw.pop("fg"); self.itemconfig(self._label,fill=self._fg_c)
        if "command" in kw: self._cmd=kw.pop("command")
        if "state" in kw:
            st=kw.pop("state")
            if st=="disabled":
                self.itemconfig(self._rect,fill=TROUGH); self.itemconfig(self._label,fill=TEXT_DIM)
                self.unbind("<Enter>"); self.unbind("<Leave>"); self.unbind("<ButtonPress-1>"); self.unbind("<ButtonRelease-1>")
                self["cursor"]=""
            else:
                self.itemconfig(self._rect,fill=self._bg_c); self.itemconfig(self._label,fill=self._fg_c)
                self.bind("<Enter>",self._on_enter); self.bind("<Leave>",self._on_leave)
                self.bind("<ButtonPress-1>",self._on_press); self.bind("<ButtonRelease-1>",self._on_release)
                self["cursor"]="hand2"
        if kw: super().configure(**kw)

    def cget(self,key):
        if key=="text": return self._text
        if key=="bg": return self._bg_c
        if key=="fg": return self._fg_c
        return super().cget(key)

def ClassicBtn(parent,text,cmd,width=None):
    return ModernBtn(parent,text=text,command=cmd,width=width)
def LimeBtn(parent,text,cmd,width=None):
    return ModernBtn(parent,text=text,command=cmd,width=width,bg_color=LIME,fg_color="#000000",hover_color=LIME_HOVER)
def OrangeBtn(parent,text,cmd,width=None):
    return ModernBtn(parent,text=text,command=cmd,width=width,bg_color=ORANGE,fg_color="#FFFFFF",hover_color=ORANGE_HOVER)
def GroupBox(parent,text):
    lf=tk.LabelFrame(parent,text=f"  {text}  ",font=F_SECTION,bg=BG,fg=TEXT,
                      relief="flat",bd=0,padx=SP_LG,pady=SP_MD,
                      highlightthickness=2,highlightbackground=CARD_BORDER,highlightcolor=CARD_BORDER,
                      labelanchor="nw")
    # Accent stripe on the left edge
    accent=tk.Frame(lf,bg=LIME,width=3)
    accent.place(x=0,y=0,relheight=1.0)
    return lf
def ClassicEntry(parent,var,width=40,**kw):
    return tk.Entry(parent,textvariable=var,font=F_BODY,bg=INPUT_BG,fg=TEXT,relief="flat",bd=0,
                    insertbackground=TEXT,width=width,
                    highlightthickness=2,highlightbackground=INPUT_BORDER,highlightcolor=INPUT_FOCUS,**kw)
def ClassicCombo(parent,var,values,width=14):
    return ttk.Combobox(parent,textvariable=var,values=values,state="readonly",width=width,font=F_BODY)
def ClassicCheck(parent,text,var):
    return tk.Checkbutton(parent,text=text,variable=var,font=F_BODY,bg=BG,fg=TEXT,activebackground=BG,
                          activeforeground=TEXT,selectcolor=INPUT_BG,anchor="w",relief="flat",bd=0,
                          highlightthickness=0,padx=SP_XS,pady=2,indicatoron=True)
def ClassicListbox(parent,height=8,**kw):
    f=tk.Frame(parent,bg=CARD_BORDER,padx=1,pady=1)
    lb=tk.Listbox(f,font=F_BODY,bg=INPUT_BG,fg=TEXT,selectbackground=BLUE_HL,selectforeground="#FFFFFF",
                  relief="flat",height=height,activestyle="none",bd=0,highlightthickness=0,**kw)
    sb=tk.Scrollbar(f,orient="vertical",command=lb.yview,relief="flat",bd=0,highlightthickness=0)
    lb.config(yscrollcommand=sb.set)
    sb.pack(side="right",fill="y"); lb.pack(side="left",fill="both",expand=True)
    return f,lb
def ClassicProgress(parent):
    return ttk.Progressbar(parent,style="Lime.Horizontal.TProgressbar",mode="determinate",maximum=100)
def HSep(parent):
    tk.Frame(parent,bg=CARD_BORDER,height=1).pack(fill="x",pady=SP_XS)
def init_limewire_styles(root):
    s=ttk.Style(root); s.theme_use("clam")
    s.configure("TCombobox",fieldbackground=INPUT_BG,background=BG,foreground=TEXT,arrowcolor=TEXT,
                selectbackground=BLUE_HL,selectforeground="#FFFFFF",bordercolor=INPUT_BORDER,
                borderwidth=1,relief="flat",padding=[8,6])
    s.map("TCombobox",bordercolor=[("focus",INPUT_FOCUS)],lightcolor=[("focus",INPUT_FOCUS)],
          darkcolor=[("focus",INPUT_FOCUS)],
          fieldbackground=[("readonly",INPUT_BG)],foreground=[("readonly",TEXT)])
    # Style the dropdown list
    root.option_add("*TCombobox*Listbox.background",INPUT_BG)
    root.option_add("*TCombobox*Listbox.foreground",TEXT)
    root.option_add("*TCombobox*Listbox.selectBackground",BLUE_HL)
    root.option_add("*TCombobox*Listbox.selectForeground","#FFFFFF")
    root.option_add("*TCombobox*Listbox.font",F_BODY)
    # Spinbox global styling
    root.option_add("*Spinbox.background",INPUT_BG)
    root.option_add("*Spinbox.foreground",TEXT)
    root.option_add("*Spinbox.buttonBackground",BG)
    root.option_add("*Spinbox.insertBackground",TEXT)
    root.option_add("*Spinbox.selectBackground",BLUE_HL)
    root.option_add("*Spinbox.selectForeground","#FFFFFF")
    s.configure("Lime.Horizontal.TProgressbar",troughcolor=TROUGH,background=LIME,
                bordercolor=CARD_BORDER,lightcolor=LIME,darkcolor=LIME_DK,thickness=10,borderwidth=0)
    s.configure("TScale",background=BG,troughcolor=TROUGH,sliderlength=18,sliderrelief="flat",borderwidth=0)
    s.configure("TNotebook",background=BG,borderwidth=0,tabmargins=[0,0,0,0])
    s.configure("TNotebook.Tab",background=BG,foreground=BG,padding=[0,0],width=0,
                font=("Segoe UI",1),borderwidth=0,
                lightcolor=BG,darkcolor=BG,bordercolor=BG,focuscolor=BG)
    s.map("TNotebook.Tab",background=[("selected",BG),("!selected",BG)],
          foreground=[("selected",BG),("!selected",BG)],
          lightcolor=[("selected",BG),("!selected",BG)],
          darkcolor=[("selected",BG),("!selected",BG)],
          bordercolor=[("selected",BG),("!selected",BG)])
    # Treeview styling (History, Discovery)
    s.configure("Treeview",background=INPUT_BG,foreground=TEXT,fieldbackground=INPUT_BG,
                borderwidth=0,font=F_BODY,rowheight=24)
    s.configure("Treeview.Heading",background=BG,foreground=TEXT,font=F_BOLD,borderwidth=0,
                relief="flat",padding=[8,4])
    s.map("Treeview",background=[("selected",BLUE_HL)],foreground=[("selected","#FFFFFF")])
    s.map("Treeview.Heading",background=[("active",BTN_HOVER)])

class ScrollFrame(tk.Frame):
    def __init__(self,parent,**kw):
        super().__init__(parent,bg=BG,**kw)
        self._cv=tk.Canvas(self,bg=BG,highlightthickness=0)
        vsb=tk.Scrollbar(self,orient="vertical",command=self._cv.yview); self._cv.configure(yscrollcommand=vsb.set)
        vsb.pack(side="right",fill="y"); self._cv.pack(side="left",fill="both",expand=True)
        self.inner=tk.Frame(self._cv,bg=BG)
        self._wid=self._cv.create_window((0,0),window=self.inner,anchor="nw")
        self.inner.bind("<Configure>",lambda e:self._cv.configure(scrollregion=self._cv.bbox("all")))
        self._cv.bind("<Configure>",lambda e:self._cv.itemconfig(self._wid,width=e.width))
        self._cv.bind("<Enter>",lambda e:self._cv.bind_all("<MouseWheel>",self._on_wheel))
        self._cv.bind("<Leave>",lambda e:self._cv.unbind_all("<MouseWheel>"))
    def _on_wheel(self,e):
        self._cv.yview_scroll(-1*(e.delta//120),"units")

class ToolTip:
    """Hover tooltip with delay, theme-matching colors."""
    def __init__(self,widget,text,delay=300):
        self._w=widget; self._text=text; self._delay=delay; self._tw=None; self._aid=None
        widget.bind("<Enter>",self._schedule,add="+")
        widget.bind("<Leave>",self._cancel,add="+")
    def _schedule(self,e=None):
        self._cancel()
        self._aid=self._w.after(self._delay,self._show)
    def _cancel(self,e=None):
        if self._aid: self._w.after_cancel(self._aid); self._aid=None
        if self._tw:
            try: self._tw.destroy()
            except Exception: pass
            self._tw=None
    def _show(self):
        self._aid=None
        tw=tk.Toplevel(self._w); tw.overrideredirect(True); tw.attributes("-topmost",True)
        tw.configure(bg=CARD_BORDER)
        f=tk.Frame(tw,bg=SURFACE_2,padx=SP_SM,pady=SP_XS)
        f.pack(fill="both",expand=True,padx=1,pady=1)
        tk.Label(f,text=self._text,font=F_SMALL,bg=SURFACE_2,fg=TEXT,wraplength=250,justify="left").pack()
        tw.update_idletasks()
        x=self._w.winfo_rootx()+self._w.winfo_width()//2-tw.winfo_width()//2
        y=self._w.winfo_rooty()+self._w.winfo_height()+4
        tw.geometry(f"+{x}+{y}")
        self._tw=tw

class _ToastManager:
    """Manages a stack of up to 4 toast notifications."""
    MAX_TOASTS=4
    def __init__(self):
        self._stack=[]
    def show(self,parent,msg,duration=3000,bg_color=None,fg_color=None,icon=None):
        # Dismiss oldest if at capacity
        while len(self._stack)>=self.MAX_TOASTS:
            old=self._stack.pop(0)
            try: old.destroy()
            except Exception: pass
        t=_Toast(parent,msg,duration,bg_color,fg_color,icon,self)
        self._stack.append(t)
        self._reposition(parent)
    def remove(self,toast):
        if toast in self._stack: self._stack.remove(toast)
    def _reposition(self,parent):
        try:
            pw=parent.winfo_rootx()+parent.winfo_width()
            py=parent.winfo_rooty()
        except Exception: return
        for i,t in enumerate(self._stack):
            try:
                w=t.winfo_width()
                tx=pw-w-SP_LG; ty=py+56+i*52
                t._target_x=tx; t._y=ty
            except Exception: pass

_toast_mgr=_ToastManager()

class _Toast(tk.Toplevel):
    """Single toast notification with slide-in and fade-out."""
    def __init__(self,parent,msg,duration=3000,bg_color=None,fg_color=None,icon=None,mgr=None):
        super().__init__(parent)
        self._mgr=mgr
        self.overrideredirect(True)
        self.attributes("-topmost",True)
        _bg=bg_color or LIME_DK; _fg=fg_color or "#FFFFFF"
        self.configure(bg=CARD_BORDER)
        inner=tk.Frame(self,bg=_bg); inner.pack(fill="both",expand=True,padx=1,pady=1)
        row=tk.Frame(inner,bg=_bg); row.pack(fill="x",padx=SP_MD,pady=SP_SM)
        ico=icon or "\u2713"
        tk.Label(row,text=ico,font=("Segoe UI",14),bg=_bg,fg=_fg).pack(side="left",padx=(0,10))
        tk.Label(row,text=msg,font=F_BOLD,bg=_bg,fg=_fg,wraplength=380,justify="left").pack(side="left",fill="x")
        self.update_idletasks()
        pw=parent.winfo_rootx()+parent.winfo_width()
        py=parent.winfo_rooty()
        w=self.winfo_width()
        idx=len(mgr._stack) if mgr else 0
        self._target_x=pw-w-SP_LG; self._start_x=pw+10; self._y=py+56+idx*52
        self.geometry(f"+{self._start_x}+{self._y}")
        self._slide_in()
        self.after(duration,self._fade_out)
    def _slide_in(self,step=0):
        if step>8: return
        x=self._start_x+int((self._target_x-self._start_x)*(step/8))
        try: self.geometry(f"+{x}+{self._y}"); self.after(16,lambda:self._slide_in(step+1))
        except Exception: pass
    def _fade_out(self,alpha=1.0):
        if alpha<=0:
            if self._mgr: self._mgr.remove(self)
            try: self.destroy()
            except Exception: pass
            return
        try: self.attributes("-alpha",alpha); self.after(30,lambda:self._fade_out(alpha-0.1))
        except Exception: pass

def show_toast(parent,msg,level="info",duration=3000):
    colors={"info":(LIME_DK,"#FFFFFF","\u2713"),"warn":(YELLOW,"#000000","\u26A0"),"error":(RED,"#FFFFFF","\u2717")}
    bg,fg,ico=colors.get(level,(LIME_DK,"#FFFFFF","\u2139"))
    _toast_mgr.show(parent,msg,duration,bg,fg,ico)


# ═══════════════════════════════════════════════════════════════════════════════
# COMMAND PALETTE & SHORTCUT REGISTRY
# ═══════════════════════════════════════════════════════════════════════════════

class ShortcutRegistry:
    """Central registry of keyboard shortcuts with help display."""
    def __init__(self):
        self._shortcuts=[]
    def register(self,combo,desc,callback):
        self._shortcuts.append((combo,desc,callback))
    def all(self):
        return list(self._shortcuts)
    def show_help(self,parent):
        w=tk.Toplevel(parent); w.title("Keyboard Shortcuts"); w.geometry("400x360")
        w.configure(bg=BG); w.transient(parent); w.grab_set()
        tk.Label(w,text="Keyboard Shortcuts",font=F_H3,bg=BG,fg=TEXT).pack(pady=(SP_LG,SP_SM))
        f=tk.Frame(w,bg=BG); f.pack(fill="both",expand=True,padx=SP_LG,pady=SP_SM)
        for combo,desc,_ in self._shortcuts:
            row=tk.Frame(f,bg=BG); row.pack(fill="x",pady=2)
            tk.Label(row,text=combo,font=F_MONO,bg=SURFACE_2,fg=LIME,padx=SP_SM,pady=2).pack(side="left")
            tk.Label(row,text=desc,font=F_BODY,bg=BG,fg=TEXT).pack(side="left",padx=(SP_SM,0))
        ClassicBtn(w,"Close",w.destroy).pack(pady=SP_MD)

class CommandPalette(tk.Toplevel):
    """Ctrl+K command palette with fuzzy search."""
    def __init__(self,app):
        super().__init__(app)
        self._app=app
        self.overrideredirect(True); self.attributes("-topmost",True)
        self.configure(bg=CARD_BORDER)
        # Position centered over app
        aw=app.winfo_width(); ax=app.winfo_rootx(); ay=app.winfo_rooty()
        pw=500; ph=400
        self.geometry(f"{pw}x{ph}+{ax+aw//2-pw//2}+{ay+80}")
        inner=tk.Frame(self,bg=BG); inner.pack(fill="both",expand=True,padx=1,pady=1)
        # Search entry
        sf=tk.Frame(inner,bg=SURFACE_2); sf.pack(fill="x",padx=SP_SM,pady=SP_SM)
        tk.Label(sf,text="\U0001F50D",font=("Segoe UI",14),bg=SURFACE_2,fg=TEXT_DIM).pack(side="left",padx=(SP_SM,SP_XS))
        self._var=tk.StringVar()
        self._entry=tk.Entry(sf,textvariable=self._var,font=F_H4,bg=SURFACE_2,fg=TEXT,relief="flat",bd=0,
                             insertbackground=TEXT,highlightthickness=0)
        self._entry.pack(side="left",fill="x",expand=True,padx=SP_XS,pady=SP_SM)
        self._entry.focus_set()
        # Results list
        self._lb=tk.Listbox(inner,font=F_BODY,bg=BG,fg=TEXT,selectbackground=BLUE_HL,selectforeground="#FFFFFF",
                            relief="flat",bd=0,highlightthickness=0,activestyle="none")
        self._lb.pack(fill="both",expand=True,padx=SP_SM,pady=(0,SP_SM))
        # Build commands
        self._commands=[]
        page_icons={"search":"\U0001F50D","download":"\U0001F4E5","playlist":"\U0001F4CB","converter":"\U0001F504",
                     "player":"\U0001F3B5","analyze":"\U0001F4CA","stems":"\U0001F39A","effects":"\U0001F3A8",
                     "discovery":"\U0001F30D","samples":"\U0001F4E6","editor":"\u2702","recorder":"\U0001F3A4",
                     "spectrogram":"\U0001F308","pitchtime":"\U0001F3B9","schedule":"\u23F0","history":"\U0001F4DC"}
        for name,page in app.pages.items():
            ico=page_icons.get(name,"\u25CF")
            self._commands.append((f"{ico}  Go to {name.title()}",lambda n=name:app._show_tab(n)))
        self._commands.append(("\U0001F4C2  Open Downloads Folder",app._open_dl_folder))
        self._commands.append(("\U0001F3A8  Cycle Theme",app._toggle_dark_mode))
        if hasattr(app,'_shortcut_reg'):
            self._commands.append(("\u2328  Show Shortcuts",lambda:app._shortcut_reg.show_help(app)))
        # Global search: history entries
        for entry in (app.history or [])[:100]:
            title=entry.get("title","")
            if not title: continue
            url=entry.get("url",""); src=entry.get("source","")[:10]
            def _go_hist(u=url):
                sp=app.pages.get("search")
                if sp and u: sp.url_var.set(u); app._show_tab("search")
            self._commands.append((f"\U0001F4DC  {title[:40]}  ({src})",_go_hist))
        # Global search: discovery library
        disc=app.pages.get("discovery")
        if disc and hasattr(disc,"_library"):
            for fp,info in list(disc._library.items())[:100]:
                bpm=info.get("bpm","?"); key=info.get("key","?")
                fname=os.path.basename(fp)[:35]
                def _go_play(f=fp):
                    pp=app.pages.get("player")
                    if pp:
                        if f not in pp._playlist_set:
                            pp._playlist.append(f); pp._playlist_set.add(f)
                            pp.plb.insert("end",os.path.basename(f))
                        app._show_tab("player")
                self._commands.append((f"\U0001F3B5  {fname}  BPM:{bpm} Key:{key}",_go_play))
        self._filtered=list(self._commands)
        self._refresh_list()
        self._var.trace_add("write",lambda *a:self._filter())
        self._entry.bind("<Return>",self._execute)
        self._entry.bind("<Escape>",lambda e:self.destroy())
        self._entry.bind("<Down>",lambda e:self._move(1))
        self._entry.bind("<Up>",lambda e:self._move(-1))
        self._lb.bind("<Double-Button-1>",self._execute)
        # Click outside to dismiss
        self.bind("<FocusOut>",lambda e:self.after(100,self._check_focus))
    def _check_focus(self):
        try:
            if self.focus_get() not in (self._entry,self._lb): self.destroy()
        except Exception: pass
    def _filter(self):
        q=self._var.get().lower()
        self._filtered=[(t,cb) for t,cb in self._commands if q in t.lower()]
        self._refresh_list()
    def _refresh_list(self):
        self._lb.delete(0,"end")
        for text,_ in self._filtered: self._lb.insert("end",text)
        if self._filtered: self._lb.selection_set(0)
    def _move(self,delta):
        if not self._filtered: return
        cur=self._lb.curselection()
        idx=(cur[0] if cur else 0)+delta
        idx=max(0,min(idx,len(self._filtered)-1))
        self._lb.selection_clear(0,"end"); self._lb.selection_set(idx); self._lb.see(idx)
    def _execute(self,e=None):
        cur=self._lb.curselection()
        if cur and cur[0]<len(self._filtered):
            _,cb=self._filtered[cur[0]]
            self.destroy(); cb()

# ═══════════════════════════════════════════════════════════════════════════════
# APP
# ═══════════════════════════════════════════════════════════════════════════════

class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("LimeWire 1.0 Studio Edition"); self.minsize(760,700)
        # Fit window to screen
        sw,sh=self.winfo_screenwidth(),self.winfo_screenheight()
        w,h=min(820,sw-40),min(960,sh-80)
        self.geometry(f"{w}x{h}")
        self.configure(bg=BG)
        self._lock=threading.Lock(); self._sched_lock=threading.Lock()
        self._completed=0; self._total=0; self._cancel=threading.Event()
        self._dark_mode=False
        self.settings=load_json(SETTINGS_FILE,{"clipboard_watch":True,"proxy":"","rate_limit":""})
        # Restore theme
        theme_mode=self.settings.get("theme","livewire")
        self._dark_mode=(theme_mode!="light"); apply_theme(theme_mode)
        self.history=load_json(HISTORY_FILE,[]); self.schedule=load_json(SCHEDULE_FILE,[])
        self.output_dir=os.path.join(os.path.expanduser("~"),"Downloads","LimeWire")
        self._last_clipboard=""
        init_limewire_styles(self)
        self._build_menubar(); self._build_logo_bar(); self._build_toolbar()
        self._build_notebook(); self._build_statusbar()
        self._start_scheduler(); self._start_clipboard_watch()
        self._bind_shortcuts(); self._setup_dnd()
        self.protocol("WM_DELETE_WINDOW",self._on_close)
    def _on_close(self):
        """Clean shutdown: stop audio, cancel pending work, destroy window."""
        self._cancel.set()
        try: _audio.stop()
        except Exception: pass
        self.destroy()
    def _bind_shortcuts(self):
        self._shortcut_reg=ShortcutRegistry()
        sr=self._shortcut_reg
        sr.register("Ctrl+D","Download / Grab URL",lambda:self.pages["search"]._grab())
        sr.register("Ctrl+O","Open downloads folder",self._open_dl_folder)
        sr.register("Space","Play / Pause",lambda:self._space_toggle(None))
        sr.register("Ctrl+K","Command Palette",lambda:CommandPalette(self))
        sr.register("Ctrl+?","Show shortcuts",lambda:self._shortcut_reg.show_help(self))
        self.bind("<Control-d>",lambda e:self.pages["search"]._grab())
        self.bind("<Control-o>",lambda e:self._open_dl_folder())
        self.bind("<space>",lambda e:self._space_toggle(e))
        self.bind("<Control-k>",lambda e:CommandPalette(self))
        self.bind("<Control-question>",lambda e:self._shortcut_reg.show_help(self))
    def _space_toggle(self,e):
        if isinstance(e.widget,(tk.Entry,ttk.Entry,ttk.Combobox,tk.Text,tk.Listbox,tk.Spinbox)): return
        pp=self.pages.get("player")
        if pp: pp._toggle()
    def _setup_dnd(self):
        if not HAS_DND: return
        try:
            self.drop_target_register(tkinterdnd2.DND_FILES,tkinterdnd2.DND_TEXT)
            self.dnd_bind("<<Drop>>",self._on_drop)
        except Exception: pass
    def _on_drop(self,e):
        data=e.data.strip()
        if data.startswith("http"):
            sp=self.pages.get("search")
            if sp: sp.url_var.set(data); self._show_tab("search")
        elif os.path.exists(data.strip("{}")):
            path=data.strip("{}")
            if not path.lower().endswith((".mp3",".wav",".flac",".ogg",".m4a",".aac",".opus")): return
            active=self._get_active_tab()
            page=self.pages.get(active)
            # Route to active tab if it has a file_var
            if page and hasattr(page,"file_var"):
                page.file_var.set(path)
                # Auto-load if page has a load method
                if hasattr(page,"_load"): self.after(50,page._load)
                elif hasattr(page,"_load_file"): self.after(50,page._load_file)
            else:
                # Default: add to player playlist
                pp=self.pages.get("player")
                if pp and path not in pp._playlist_set:
                    pp._playlist.append(path); pp._playlist_set.add(path)
                    pp.plb.insert("end",os.path.basename(path))
                self._show_tab("player")

    def _build_menubar(self):
        mb=tk.Menu(self,font=F_BODY,bg=BG)
        fm=tk.Menu(mb,tearoff=0,font=F_BODY)
        fm.add_command(label="Open Downloads Folder",command=self._open_dl_folder)
        fm.add_separator(); fm.add_command(label="Exit",command=self.destroy)
        mb.add_cascade(label="File",menu=fm)
        tm=tk.Menu(mb,tearoff=0,font=F_BODY)
        tm.add_command(label="Clear History",command=lambda:(self.history.clear(),save_json(HISTORY_FILE,[])) if messagebox.askyesno("Clear","Clear?") else None)
        tm.add_separator()
        tm.add_command(label="Cycle Theme (Light/Dark/Modern)",command=self._toggle_dark_mode)
        tm.add_command(label="Check yt-dlp Update",command=self._check_ytdlp_update)
        tm.add_separator()
        tm.add_command(label="Set FL Studio Path",command=self._set_fl_path)
        mb.add_cascade(label="Tools",menu=tm)
        hm=tk.Menu(mb,tearoff=0,font=F_BODY)
        caps = []
        if HAS_LIBROSA: caps.append("BPM/Key")
        if HAS_LOUDNESS: caps.append("LUFS")
        if HAS_SHAZAM: caps.append("Shazam Audio ID")
        elif HAS_SHAZAM_SEARCH: caps.append("Shazam Search")
        if HAS_MB: caps.append("MusicBrainz")
        if HAS_ACOUSTID: caps.append("Chromaprint")
        if HAS_DEMUCS: caps.append("Demucs Stems")
        cap_str = ", ".join(caps) if caps else "None (install optional deps)"
        hm.add_command(label="About",command=lambda:messagebox.showinfo("About",
            f"LimeWire v1.0 Studio Edition\n\n"
            f"The modern music utility for everything.\n"
            f"Powered by yt-dlp + Demucs + librosa + pydub\n\n"
            f"18 pages: Search, Batch DL, Playlist, Convert, Player,\n"
            f"Analyze, Stems, Effects, Discovery, Samples, Editor,\n"
            f"Recorder, Spectrogram, Pitch/Time, Remixer, Batch Process,\n"
            f"Scheduler, History\n\n"
            f"Active modules: {cap_str}\n\n"
            f"Highlights: Modern UI with rounded buttons, gradient header,\n"
            f"command palette (Ctrl+K), tooltips, stem remixer,\n"
            f"batch processor, loudness targeting, smart playlists,\n"
            f"player crossfade, live theme switching.\n\n"
            f"Optional: pip install librosa pyloudnorm demucs pydub\n"
            f"  sounddevice pyrubberband openai-whisper shazamio\n\n"
            f"\"Definitely virus-free since 2024\""))
        mb.add_cascade(label="Help",menu=hm)
        self.config(menu=mb)

    def _build_logo_bar(self):
        LOGO_H=56
        bar=tk.Canvas(self,height=LOGO_H,highlightthickness=0,bd=0); bar.pack(fill="x")
        def _draw_gradient(e=None):
            w=bar.winfo_width(); h=LOGO_H
            bar.delete("grad")
            steps=max(1,w//4)
            for i in range(steps):
                c=_lerp_color(ACCENT_START,ACCENT_END,i/max(1,steps-1))
                x=int(i*w/steps); x2=int((i+1)*w/steps)+1
                bar.create_rectangle(x,0,x2,h,fill=c,outline="",tags="grad")
            bar.tag_lower("grad")
            # Redraw foreground items
            bar.delete("fg")
            # Icon circle with glow
            cx,cy=32,LOGO_H//2
            bar.create_oval(cx-18,cy-18,cx+18,cy+18,fill="",outline="#555555",width=3,tags="fg")
            bar.create_oval(cx-14,cy-14,cx+14,cy+14,fill="#3a6e4e",outline="",tags="fg")
            bar.create_text(cx,cy,text="\u25C9",font=("Segoe UI",18),fill="#FFFFFF",tags="fg")
            # Title
            bar.create_text(62,LOGO_H//2,text="LimeWire",font=F_LOGO,fill="#FFFFFF",anchor="w",tags="fg")
            # Pill badge
            bx=220; by=LOGO_H//2
            _round_rect(bar,bx,by-10,bx+90,by+10,radius=10,fill="#3a6e4e",outline="",tags="fg")
            bar.create_text(bx+45,by,text="v1.0 Studio",font=("Segoe UI",7,"bold"),fill="#FFFFFF",tags="fg")
            # Status indicator (right side)
            sx=w-100; sy=LOGO_H//2
            self._status_x=sx; self._status_y=sy
            bar.create_oval(sx-5,sy-5,sx+5,sy+5,fill=LIME,outline="",tags=("fg","status_dot"))
            bar.create_text(sx+14,sy,text="Connected",font=F_SMALL,fill="#FFFFFF",anchor="w",tags="fg")
        bar.bind("<Configure>",_draw_gradient)
        self._logo_bar=bar
        self._pulse_status()

    def _pulse_status(self):
        try:
            bar=self._logo_bar
            dot=bar.find_withtag("status_dot")
            if dot:
                cur=bar.itemcget(dot[0],"fill")
                nxt=LIME_LT if cur==LIME else LIME
                bar.itemconfig(dot[0],fill=nxt)
        except Exception: pass
        self.after(STATUS_PULSE_MS,self._pulse_status)

    def _build_toolbar(self):
        tk.Frame(self,bg=CARD_BORDER,height=1).pack(fill="x")
        tb=tk.Frame(self,bg=TOOLBAR,height=48); tb.pack(fill="x"); tb.pack_propagate(False)
        self._toolbar=tb
        self._tb_btns={}
        items=[("search","\U0001F50D","Search"),("download","\U0001F4E5","Batch"),
               ("playlist","\U0001F4CB","Playlist"),("converter","\U0001F504","Convert"),
               ("player","\U0001F3B5","Player"),("analyze","\U0001F4CA","Analyze"),
               ("stems","\U0001F39A","Stems"),("effects","\u2728","Effects"),
               ("discovery","\U0001F30D","Library"),("samples","\U0001F3B6","Samples"),
               ("editor","\u2702","Editor"),("recorder","\U0001F3A4","Record"),
               ("spectrogram","\U0001F308","Spectro"),("pitchtime","\U0001F3B9","Pitch"),
               ("remixer","\U0001F3A7","Remix"),("batch","\u2699","Batch"),
               ("schedule","\u23F0","Schedule"),("history","\U0001F4DC","History")]
        for name,icon,label in items:
            bf=tk.Frame(tb,bg=TOOLBAR,cursor="hand2")
            bf.pack(side="left",padx=1,pady=(4,0))
            il=tk.Label(bf,text=icon,font=("Segoe UI",11),bg=TOOLBAR,fg=TEXT_DIM)
            il.pack(side="top",pady=(0,1))
            nl=tk.Label(bf,text=label,font=("Segoe UI",7,"bold"),bg=TOOLBAR,fg=TEXT_DIM)
            nl.pack(side="top")
            ind=tk.Frame(bf,bg=TOOLBAR,height=3); ind.pack(fill="x",side="bottom",pady=(2,0))
            self._tb_btns[name]=(bf,il,nl,ind)
            ToolTip(bf,f"Go to {label}")
            for w in (bf,il,nl):
                w.bind("<Button-1>",lambda e,n=name:self._show_tab(n))
                w.bind("<Enter>",lambda e,n=name:self._tb_hover(n,True))
                w.bind("<Leave>",lambda e,n=name:self._tb_hover(n,False))
        tk.Frame(self,bg=CARD_BORDER,height=1).pack(fill="x")

    def _tb_hover(self,name,entering):
        if name not in self._tb_btns: return
        bf,il,nl,ind=self._tb_btns[name]
        if entering:
            for w in (bf,il,nl): w.config(bg=BTN_HOVER)
            il.config(fg=TEXT); nl.config(fg=TEXT)
        else:
            active=self._get_active_tab()
            bg=TOOLBAR; fg=TEXT_DIM
            if name==active: fg=TAB_ACTIVE
            for w in (bf,il,nl): w.config(bg=bg)
            il.config(fg=fg); nl.config(fg=fg)

    def _get_active_tab(self):
        try:
            idx=self.nb.index(self.nb.select()); return list(self.pages.keys())[idx]
        except Exception: return ""

    def _update_tb_active(self):
        active=self._get_active_tab()
        for name,(bf,il,nl,ind) in self._tb_btns.items():
            if name==active:
                il.config(fg=TAB_ACTIVE); nl.config(fg=TAB_ACTIVE); ind.config(bg=TAB_ACTIVE)
            else:
                il.config(fg=TEXT_DIM); nl.config(fg=TEXT_DIM); ind.config(bg=TOOLBAR)

    def _build_notebook(self):
        self.nb=ttk.Notebook(self,style="TNotebook"); self.nb.pack(fill="both",expand=True,padx=4)
        self.pages={}
        for name,label,cls in [("search","Search & Grab",SearchPage),("download","Batch Download",DownloadPage),
                                ("playlist","Playlist",PlaylistPage),("converter","Converter",ConverterPage),
                                ("player","Player",PlayerPage),("analyze","Analyze",AnalyzePage),
                                ("stems","Stems",StemsPage),("effects","Effects",EffectsPage),
                                ("discovery","Discovery",DiscoveryPage),("samples","Samples",SamplesPage),
                                ("editor","Editor",EditorPage),("recorder","Recorder",RecorderPage),
                                ("spectrogram","Spectrogram",SpectrogramPage),("pitchtime","Pitch/Time",PitchTimePage),
                                ("remixer","Remixer",RemixerPage),("batch","Batch Process",BatchProcessorPage),
                                ("schedule","Schedule",SchedulerPage),("history","History",HistoryPage)]:
            page=cls(self.nb,self); self.nb.add(page,text=f" {label} "); self.pages[name]=page
        self.nb.bind("<<NotebookTabChanged>>",self._on_tab)

    def _show_tab(self,name):
        keys=list(self.pages.keys())
        if name in keys: self.nb.select(keys.index(name))
    def _on_tab(self,e=None):
        idx=self.nb.index(self.nb.select()); keys=list(self.pages.keys())
        if idx<len(keys) and hasattr(self.pages[keys[idx]],'refresh'): self.pages[keys[idx]].refresh()
        if hasattr(self,'_tb_btns'): self._update_tb_active()

    def _build_statusbar(self):
        tk.Frame(self,bg=CARD_BORDER,height=1).pack(fill="x",side="bottom")
        sb=tk.Frame(self,bg=BG,height=24); sb.pack(fill="x",side="bottom"); sb.pack_propagate(False)
        self.status_lbl=tk.Label(sb,text="Ready  |  Ctrl+D: Download  Space: Play/Pause  Ctrl+O: Open Folder",font=F_STATUS,bg=BG,fg=TEXT_DIM,anchor="w")
        self.status_lbl.pack(side="left",padx=8,fill="x",expand=True)
        tk.Frame(sb,bg=CARD_BORDER,width=1).pack(side="left",fill="y",pady=4)
        self.dl_count_lbl=tk.Label(sb,text=f"Downloads: {len(self.history)}",font=F_STATUS,bg=BG,fg=TEXT,padx=10)
        self.dl_count_lbl.pack(side="left")
        tk.Frame(sb,bg=CARD_BORDER,width=1).pack(side="left",fill="y",pady=4)
        mod_map={"FFmpeg":HAS_FFMPEG,"BPM/Key":HAS_LIBROSA,"LUFS":HAS_LOUDNESS,
                 "Shazam":HAS_SHAZAM or HAS_SHAZAM_SEARCH,
                 "MusicBrainz":HAS_MB,"Chromaprint":HAS_ACOUSTID,"Demucs":HAS_DEMUCS,
                 "FL Studio":HAS_PYFLP,"Serato":HAS_SERATO,
                 "pydub":HAS_PYDUB,"SoundDevice":HAS_SOUNDDEVICE,
                 "Whisper":HAS_WHISPER,"Rubberband":HAS_RUBBERBAND}
        loaded=sum(mod_map.values()); total=len(mod_map)
        missing=[k for k,v in mod_map.items() if not v]
        tip=f"Missing: {', '.join(missing)}" if missing else "All modules loaded"
        mod_lbl=tk.Label(sb,text=f"\u25CF {loaded}/{total} modules",font=F_STATUS,bg=BG,fg=LIME if loaded>=total//2 else YELLOW,padx=10,cursor="hand2")
        mod_lbl.pack(side="left")
        mod_lbl.bind("<Button-1>",lambda e:messagebox.showinfo("Module Status",
            "\n".join(f"{'\u2713' if v else '\u2717'} {k}" for k,v in mod_map.items())+"\n\n"+tip))

    def set_status(self,text): self.status_lbl.config(text=text)
    def toast(self,msg,level="info"): show_toast(self,msg,level)
    def add_history(self,entry):
        self.history.insert(0,entry); save_json(HISTORY_FILE,self.history[:HISTORY_MAX])
        self.dl_count_lbl.config(text=f"Downloads: {len(self.history)}")
    def _open_dl_folder(self):
        os.makedirs(self.output_dir,exist_ok=True); open_folder(self.output_dir)
    def _toggle_dark_mode(self):
        cycle=["livewire","light","dark","modern","synthwave","dracula","catppuccin","tokyo","spotify","classic","nord","gruvbox"]
        cur=self.settings.get("theme","livewire")
        if cur not in cycle: cur="livewire"
        nxt=cycle[(cycle.index(cur)+1)%len(cycle)]
        # Capture old theme colors for remapping
        old=THEMES.get(cur,THEME_DARK)
        apply_theme(nxt); self._dark_mode=(nxt!="light")
        new=THEMES.get(nxt,THEME_DARK)
        self.settings["theme"]=nxt; self._save_settings()
        # Build color remap table (old→new for all theme keys)
        cmap={v.lower():new[k].lower() for k,v in old.items() if isinstance(v,str) and v.startswith("#")}
        init_limewire_styles(self)
        self._reconfig_all(self,cmap)
        # Redraw logo bar gradient
        if hasattr(self,"_logo_bar"):
            self._logo_bar.event_generate("<Configure>")
        names={"livewire":"LiveWire","light":"Classic Light","dark":"Classic Dark","modern":"Modern Dark",
               "synthwave":"Synthwave","dracula":"Dracula","catppuccin":"Catppuccin",
               "tokyo":"Tokyo Night","spotify":"Spotify","classic":"LimeWire Classic",
               "nord":"Nord","gruvbox":"Gruvbox"}
        show_toast(self,f"Theme: {names.get(nxt,nxt)}","info")

    def _reconfig_all(self,widget,cmap):
        """Recursively remap widget colors using old→new color mapping."""
        def _remap(color):
            if not color or not isinstance(color,str): return None
            return cmap.get(color.lower())
        try:
            wtype=widget.winfo_class()
            if wtype in ("Frame","Labelframe"):
                old_bg=widget.cget("bg").lower()
                new_bg=_remap(old_bg) or BG
                widget.configure(bg=new_bg)
                if wtype=="Labelframe":
                    try:
                        old_fg=widget.cget("fg").lower()
                        new_fg=_remap(old_fg) or TEXT
                        widget.configure(fg=new_fg,highlightbackground=CARD_BORDER,highlightcolor=CARD_BORDER)
                    except Exception: pass
            elif wtype=="Label":
                old_bg=widget.cget("bg").lower()
                new_bg=_remap(old_bg) or BG
                widget.configure(bg=new_bg)
                try:
                    old_fg=widget.cget("fg").lower()
                    new_fg=_remap(old_fg)
                    if new_fg: widget.configure(fg=new_fg)
                except Exception: pass
            elif wtype=="Checkbutton":
                try: widget.configure(bg=BG,fg=TEXT,activebackground=BG,activeforeground=TEXT,selectcolor=INPUT_BG)
                except Exception: pass
            elif wtype=="Radiobutton":
                try: widget.configure(bg=BG,fg=TEXT,activebackground=BG,activeforeground=TEXT,selectcolor=INPUT_BG)
                except Exception: pass
            elif wtype=="Entry":
                try: widget.configure(bg=INPUT_BG,fg=TEXT,insertbackground=TEXT,
                                      highlightbackground=INPUT_BORDER,highlightcolor=INPUT_FOCUS)
                except Exception: pass
            elif wtype=="Listbox":
                try: widget.configure(bg=INPUT_BG,fg=TEXT,selectbackground=BLUE_HL,selectforeground="#FFFFFF")
                except Exception: pass
            elif wtype=="Scrollbar":
                try: widget.configure(bg=BG,troughcolor=TROUGH)
                except Exception: pass
            elif wtype=="Spinbox":
                try: widget.configure(bg=INPUT_BG,fg=TEXT,buttonbackground=BG,insertbackground=TEXT,
                                      selectbackground=BLUE_HL,selectforeground="#FFFFFF")
                except Exception: pass
            elif wtype=="Canvas":
                if isinstance(widget,ModernBtn):
                    # Remap ModernBtn colors
                    new_bg=_remap(widget._bg_c)
                    new_fg=_remap(widget._fg_c)
                    new_hv=_remap(widget._hover_c)
                    if new_bg: widget._bg_c=new_bg; widget.itemconfig(widget._rect,fill=new_bg)
                    if new_fg: widget._fg_c=new_fg; widget.itemconfig(widget._label,fill=new_fg)
                    if new_hv: widget._hover_c=new_hv
                    # Update canvas bg to match parent
                    try:
                        pbg=widget.master.cget("bg") if hasattr(widget.master,"cget") else BG
                        widget.configure(bg=pbg)
                    except Exception: pass
                elif widget!=getattr(self,'_logo_bar',None):
                    old_bg=widget.cget("bg").lower()
                    new_bg=_remap(old_bg)
                    widget.configure(bg=new_bg if new_bg else BG)
            elif wtype=="Toplevel":
                widget.configure(bg=BG)
        except Exception: pass
        for child in widget.winfo_children():
            self._reconfig_all(child,cmap)
    def _check_ytdlp_update(self):
        self.set_status("Checking yt-dlp version...")
        def _check():
            try:
                cur=yt_dlp.version.__version__
                resp=requests.get("https://pypi.org/pypi/yt-dlp/json",timeout=10)
                latest=resp.json()["info"]["version"]
                if cur!=latest:
                    self.after(0,lambda:show_toast(self,f"yt-dlp update available: {cur} → {latest}\nRun: pip install -U yt-dlp","warn",5000))
                else:
                    self.after(0,lambda:show_toast(self,f"yt-dlp {cur} is up to date","info"))
                self.after(0,lambda:self.set_status(f"yt-dlp: {cur} (latest: {latest})"))
            except Exception as e:
                self.after(0,lambda:show_toast(self,f"Update check failed: {str(e)[:60]}","error"))
        threading.Thread(target=_check,daemon=True).start()
    def _set_fl_path(self):
        current=self.settings.get("fl_studio_path","")
        detected=find_fl_studio()
        initial=os.path.dirname(current or detected or r"C:\Program Files\Image-Line")
        path=filedialog.askopenfilename(title="Select FL64.exe",initialdir=initial,
            filetypes=[("FL Studio","FL64.exe FL.exe"),("All","*.*")])
        if path:
            self.settings["fl_studio_path"]=path; self._save_settings()
            self.toast(f"FL Studio path: {os.path.basename(path)}")
    def _save_settings(self):
        save_json(SETTINGS_FILE,self.settings)
    def get_ydl_extra(self):
        extra={}
        proxy=self.settings.get("proxy","").strip()
        if proxy: extra["proxy"]=proxy
        rl=self.settings.get("rate_limit","").strip()
        if rl: extra["ratelimit"]=self._parse_rate(rl)
        return extra
    @staticmethod
    def _parse_rate(s):
        s=s.strip().upper()
        try:
            if s.endswith("M"): return int(float(s[:-1])*1024*1024)
            if s.endswith("K"): return int(float(s[:-1])*1024)
            return int(s)
        except Exception: return None
    def _start_clipboard_watch(self):
        def _poll():
            if self.settings.get("clipboard_watch",True):
                try:
                    clip=self.clipboard_get().strip()
                    if clip!=self._last_clipboard and is_url(clip):
                        self._last_clipboard=clip; sp=self.pages.get("search")
                        if sp: self.after(0,lambda:sp._on_clipboard(clip))
                except Exception: pass
            self.after(CLIPBOARD_POLL_MS,_poll)
        self.after(CLIPBOARD_INITIAL_DELAY_MS,_poll)
    def _start_scheduler(self):
        def _loop():
            while True:
                time.sleep(SCHEDULER_POLL_SEC); now=datetime.datetime.now()
                with self._sched_lock:
                    for job in self.schedule:
                        if job.get("status")!="pending": continue
                        try: when=datetime.datetime.strptime(job["when"],"%Y-%m-%d %H:%M")
                        except Exception: continue
                        if now>=when:
                            job["status"]="running"
                            threading.Thread(target=self._run_sched,args=(job,),daemon=True).start()
                            save_json(SCHEDULE_FILE,self.schedule)
        threading.Thread(target=_loop,daemon=True).start()
    def _run_sched(self,job):
        url=job.get("url",""); fmt=job.get("format","mp3"); out=job.get("folder",self.output_dir)
        os.makedirs(out,exist_ok=True)
        opts={"quiet":True,"outtmpl":os.path.join(out,"%(title)s.%(ext)s"),"format":"bestaudio/best",
              "postprocessors":[{"key":"FFmpegExtractAudio","preferredcodec":fmt}],**self.get_ydl_extra()}
        try:
            with yt_dlp.YoutubeDL({**YDL_BASE,**opts}) as ydl: ydl.download([url]); status="done"
        except Exception: status="error"
        with self._sched_lock:
            job["status"]=status; save_json(SCHEDULE_FILE,self.schedule)


# ═══════════════════════════════════════════════════════════════════════════════
# SEARCH & GRAB PAGE
# ═══════════════════════════════════════════════════════════════════════════════

class SearchPage(ScrollFrame):
    """Search for media by URL, preview metadata, and download audio/video."""
    def __init__(self,parent,app):
        super().__init__(parent); self.app=app; self._downloading=False; self._recent=[]
        self._build(self.inner)
    def _build(self,p):
        sf=tk.Frame(p,bg=BG,padx=12,pady=10); sf.pack(fill="x")
        tk.Label(sf,text="Search:",font=F_BOLD,bg=BG,fg=TEXT).pack(side="left",padx=(0,8))
        # URL validation indicator
        self.url_indicator=tk.Label(sf,text="\u25CF",font=F_BODY,bg=BG,fg=TEXT_DIM)
        self.url_indicator.pack(side="left",padx=(0,3))
        self.url_var=tk.StringVar(); self.url_e=ClassicEntry(sf,self.url_var,width=38)
        self.url_e.pack(side="left",fill="x",expand=True,ipady=3,padx=(0,6))
        self.url_e.bind("<Return>",lambda e:self._grab())
        self.url_var.trace_add("write",self._on_url_change)
        # Mode toggle
        self.dl_mode=tk.StringVar(value="audio")
        tk.Radiobutton(sf,text="Audio",variable=self.dl_mode,value="audio",font=F_SMALL,bg=BG,selectcolor=INPUT_BG,
                       command=self._mode_changed).pack(side="left")
        tk.Radiobutton(sf,text="Video",variable=self.dl_mode,value="video",font=F_SMALL,bg=BG,selectcolor=INPUT_BG,
                       command=self._mode_changed).pack(side="left",padx=(0,4))
        tk.Label(sf,text="Fmt:",font=F_BODY,bg=BG,fg=TEXT).pack(side="left",padx=(0,3))
        self.fmt_var=tk.StringVar(value="mp3")
        self.fmt_combo=ClassicCombo(sf,self.fmt_var,AUDIO_FMTS,width=5); self.fmt_combo.pack(side="left",padx=(0,4))
        tk.Label(sf,text="Q:",font=F_BODY,bg=BG,fg=TEXT).pack(side="left")
        self.qual_var=tk.StringVar(value="1080p")
        self.qual_combo=ClassicCombo(sf,self.qual_var,QUALITIES,width=6); self.qual_combo.pack(side="left",padx=(0,6))
        self.qual_combo.pack_forget()  # hidden in audio mode
        LimeBtn(sf,"Download",self._grab).pack(side="left",padx=(0,4))
        self.cancel_btn=tk.Button(sf,text="Cancel",font=F_BTN,bg=RED,fg="#FFFFFF",relief="flat",bd=0,padx=12,pady=5,
                                  cursor="hand2",command=self._cancel)
        ClassicBtn(sf,"Preview",self._preview).pack(side="left")
        HSep(p)
        self.clip_lbl=tk.Label(p,text="  Tip: Copy a URL and it auto-appears here",font=F_SMALL,bg=CARD_BG,fg=TEXT_DIM,
                               anchor="w",relief="flat",bd=0,padx=8,pady=4,
                               highlightthickness=1,highlightbackground=CARD_BORDER)
        self.clip_lbl.pack(fill="x",padx=10,pady=(6,0))
        ig=GroupBox(p,"File Information"); ig.pack(fill="x",padx=10,pady=8)
        ir=tk.Frame(ig,bg=BG); ir.pack(fill="x")
        self.thumb=tk.Label(ir,bg=CARD_BG,width=18,height=6,text="No\nPreview",font=F_SMALL,fg=TEXT_DIM,
                           relief="flat",bd=0,highlightthickness=1,highlightbackground=CARD_BORDER)
        self.thumb.pack(side="left",padx=(0,12))
        ic=tk.Frame(ir,bg=BG); ic.pack(side="left",fill="both",expand=True)
        def irow(par,lbl,default="--"):
            r=tk.Frame(par,bg=BG); r.pack(fill="x",pady=1)
            tk.Label(r,text=lbl,font=F_BOLD,bg=BG,fg=TEXT,width=10,anchor="w").pack(side="left")
            l=tk.Label(r,text=default,font=F_BODY,bg=BG,fg=TEXT_DIM,anchor="w"); l.pack(side="left",fill="x",expand=True); return l
        self.info_title=irow(ic,"Title:"); self.info_artist=irow(ic,"Artist:")
        self.info_dur=irow(ic,"Duration:"); self.info_source=irow(ic,"Source:")
        self.info_status=irow(ic,"Status:","Ready")
        pg=tk.Frame(ig,bg=BG); pg.pack(fill="x",pady=(8,4))
        tk.Label(pg,text="Progress:",font=F_BOLD,bg=BG,fg=TEXT).pack(side="left",padx=(0,8))
        self.prog=ClassicProgress(pg); self.prog.pack(side="left",fill="x",expand=True)
        self.pct_lbl=tk.Label(pg,text="0%",font=F_BODY,bg=BG,fg=TEXT,width=5); self.pct_lbl.pack(side="left",padx=(4,0))

        ag=GroupBox(p,"Actions"); ag.pack(fill="x",padx=10,pady=(0,8))
        ar=tk.Frame(ag,bg=BG); ar.pack(fill="x")
        ClassicBtn(ar,"Open Folder",self._open_folder).pack(side="left",padx=(0,6))
        ClassicBtn(ar,"Copy Path",self._copy_path).pack(side="left",padx=(0,6))
        OrangeBtn(ar,"Analyze Last",self._analyze_last).pack(side="left",padx=(0,6))
        OrangeBtn(ar,"Split Stems",self._stems_last).pack(side="left")
        ar2=tk.Frame(ag,bg=BG); ar2.pack(fill="x",pady=(4,0))
        self.subs_var=tk.BooleanVar(value=False)
        ClassicCheck(ar2,"Download subtitles",self.subs_var).pack(side="left",padx=(0,12))

        # Settings row
        stg=GroupBox(p,"Settings"); stg.pack(fill="x",padx=10,pady=(0,4))
        stgr=tk.Frame(stg,bg=BG); stgr.pack(fill="x")
        tk.Label(stgr,text="Proxy:",font=F_BOLD,bg=BG,fg=TEXT).pack(side="left")
        self.proxy_var=tk.StringVar(value=self.app.settings.get("proxy",""))
        ClassicEntry(stgr,self.proxy_var,width=18).pack(side="left",padx=(4,12),ipady=1)
        tk.Label(stgr,text="Rate Limit:",font=F_BOLD,bg=BG,fg=TEXT).pack(side="left")
        self.rate_var=tk.StringVar(value=self.app.settings.get("rate_limit",""))
        ClassicEntry(stgr,self.rate_var,width=8).pack(side="left",padx=(4,12),ipady=1)
        tk.Label(stgr,text="(e.g. 1M, 500K)",font=F_SMALL,bg=BG,fg=TEXT_DIM).pack(side="left",padx=(0,12))
        self.clip_var=tk.BooleanVar(value=self.app.settings.get("clipboard_watch",True))
        ClassicCheck(stgr,"Clipboard Watch",self.clip_var).pack(side="left")
        ClassicBtn(stgr,"Save",self._save_settings).pack(side="right")

        lg=GroupBox(p,"Save Location"); lg.pack(fill="x",padx=10,pady=(0,8))
        lr=tk.Frame(lg,bg=BG); lr.pack(fill="x")
        self.folder_var=tk.StringVar(value=self.app.output_dir)
        ClassicEntry(lr,self.folder_var,width=55).pack(side="left",fill="x",expand=True,ipady=2,padx=(0,8))
        ClassicBtn(lr,"Browse...",self._browse).pack(side="left")
        rg=GroupBox(p,"Recent Downloads"); rg.pack(fill="both",padx=10,pady=(0,10),expand=True)
        hdr=tk.Frame(rg,bg=CARD_BG,bd=0); hdr.pack(fill="x")
        tk.Frame(rg,bg=CARD_BORDER,height=1).pack(fill="x")
        for t,w in [("Status",6),("Title",35),("Source",10),("Format",6),("Time",6)]:
            tk.Label(hdr,text=t,font=F_BTN,bg=CARD_BG,fg=TEXT,width=w,anchor="w",padx=4,pady=2).pack(side="left")
        self.rec_f,self.rec_lb=ClassicListbox(rg,height=6); self.rec_f.pack(fill="both",expand=True)
        self._last_file = None

    def _mode_changed(self):
        if self.dl_mode.get()=="video":
            self.fmt_combo.pack_forget()
            self.fmt_var.set("mp4"); self.fmt_combo.config(values=VIDEO_FMTS)
            self.fmt_combo.pack(side="left",padx=(0,4)); self.qual_combo.pack(side="left",padx=(0,6))
        else:
            self.qual_combo.pack_forget(); self.fmt_var.set("mp3"); self.fmt_combo.config(values=AUDIO_FMTS)

    def _on_url_change(self,*_):
        url=self.url_var.get().strip()
        if not url:
            self.url_indicator.config(fg=TEXT_DIM)
        elif is_url(url):
            self.url_indicator.config(fg=LIME_DK)
            src=detect_source(url)
            mode,fmt=auto_detect_format(url)
            if src=="Spotify":
                self.clip_lbl.config(text=f"  Spotify detected — will resolve to YouTube for download ({mode}/{fmt})",fg=ORANGE)
            elif src=="Apple Music":
                self.clip_lbl.config(text=f"  Apple Music detected ({mode}/{fmt})",fg=LIME_DK)
            elif mode and fmt:
                self.clip_lbl.config(text=f"  Auto-detected: {src} ({mode}/{fmt})",fg=LIME_DK)
        else:
            self.url_indicator.config(fg=RED)
    def _save_settings(self):
        self.app.settings["proxy"]=self.proxy_var.get().strip()
        self.app.settings["rate_limit"]=self.rate_var.get().strip()
        self.app.settings["clipboard_watch"]=self.clip_var.get()
        self.app._save_settings()
        self.app.toast("Settings saved")
    def _cancel(self):
        self.app._cancel.set()
        self.info_status.config(text="Cancelling...",fg=YELLOW)
    def _on_clipboard(self,url):
        if not self.url_e.get().strip():
            self.url_var.set(url); self.clip_lbl.config(text=f"  Auto-detected {detect_source(url)} URL",fg=LIME_DK)
    def _preview(self):
        url=self.url_var.get().strip()
        if not url or "http" not in url: return
        self.info_status.config(text="Fetching...",fg=YELLOW); threading.Thread(target=self._do_pv,args=(url,),daemon=True).start()
    def _do_pv(self,url):
        try:
            with yt_dlp.YoutubeDL(ydl_opts(quiet=True,no_warnings=True,skip_download=True)) as ydl:
                info=ydl.extract_info(url,download=False)
            t=info.get("title","?"); a=info.get("uploader") or info.get("channel",""); d=fmt_duration(info.get("duration",0))
            self.after(0,lambda:(self.info_title.config(text=t,fg=TEXT),self.info_artist.config(text=a or "?",fg=TEXT),
                self.info_dur.config(text=d,fg=TEXT),self.info_source.config(text=detect_source(url),fg=TEXT_BLUE),
                self.info_status.config(text="Ready",fg=LIME_DK)))
            th=info.get("thumbnail","")
            if th:
                img=fetch_thumbnail(th,(140,80))
                if img:
                    ph=ImageTk.PhotoImage(img)
                    self.after(0,lambda ph=ph:(self.thumb.config(image=ph,text="",width=140,height=80),setattr(self.thumb,"_img",ph)))
        except Exception as e:
            self.after(0,lambda:self.info_status.config(text=f"Error: {str(e)[:50]}",fg=RED))

    def _grab(self):
        url=self.url_var.get().strip()
        if not url or "http" not in url: return
        if self._downloading: return
        self._downloading=True; self.app._cancel.clear()
        self.prog["value"]=0; self.pct_lbl.config(text="0%")
        self.cancel_btn.pack(side="left",padx=(4,0))
        self.info_status.config(text="Starting...",fg=YELLOW); self.app.set_status("Downloading...")
        threading.Thread(target=self._do_grab,args=(url,),daemon=True).start()
    def _do_grab(self,url):
        fmt=self.fmt_var.get(); mode=self.dl_mode.get(); source=detect_source(url)
        # Spotify bridge: resolve to YouTube search URL
        if source=="Spotify":
            self.after(0,lambda:self.info_status.config(text="Resolving Spotify → YouTube...",fg=YELLOW))
            yt_url,err=spotify_to_youtube(url)
            if err:
                self.after(0,lambda:(self.info_status.config(text=f"Spotify error: {err}",fg=RED),
                    self.app.toast(f"Spotify: {err}","error")))
                self._downloading=False; return
            self.after(0,lambda:self.info_status.config(text=f"Spotify resolved, downloading...",fg=LIME_DK))
            url=yt_url; source="Spotify→YouTube"
        out=self.folder_var.get(); os.makedirs(out,exist_ok=True)
        title=url; artist=""
        def hook(d):
            if self.app._cancel.is_set(): raise Exception("Cancelled by user")
            if d["status"]=="downloading":
                raw=d.get("_percent_str","0%").strip().replace("%","")
                try: pct=float(raw)
                except Exception: pct=0
                spd=d.get("_speed_str","").strip()
                self.after(0,lambda:(self.prog.configure(value=pct),self.pct_lbl.config(text=f"{pct:.0f}%"),
                    self.info_status.config(text=f"Downloading: {pct:.0f}% {spd}",fg=TEXT)))
            elif d["status"]=="finished":
                self.after(0,lambda:(self.prog.configure(value=100),self.pct_lbl.config(text="100%"),
                    self.info_status.config(text=f"Converting to {fmt.upper()}...",fg=LIME_DK)))
        extra=self.app.get_ydl_extra()
        # %(title).200B truncates to 200 bytes, avoiding Windows MAX_PATH issues
        outtmpl=os.path.join(out,"%(title).200B.%(ext)s")
        if mode=="audio":
            opts={"outtmpl":outtmpl,"logger":_SilentLogger(),"progress_hooks":[hook],
                  "quiet":True,"noplaylist":True,"format":"bestaudio/best",
                  "postprocessors":[{"key":"FFmpegExtractAudio","preferredcodec":fmt}],**extra}
        else:
            q=self.qual_var.get()
            vf="bestvideo+bestaudio/best" if q=="best" else f"bestvideo[height<={q[:-1]}]+bestaudio/best[height<={q[:-1]}]"
            opts={"outtmpl":outtmpl,"logger":_SilentLogger(),"progress_hooks":[hook],
                  "quiet":True,"noplaylist":True,"format":vf,"merge_output_format":fmt,**extra}
        if self.subs_var.get():
            opts["writesubtitles"]=True; opts["writeautomaticsub"]=True; opts["subtitleslangs"]=["en"]
        try:
            with yt_dlp.YoutubeDL({**YDL_BASE,**opts}) as ydl:
                info=ydl.extract_info(url,download=True)
                title=info.get("title","Unknown"); artist=info.get("uploader") or info.get("channel","")
                th=info.get("thumbnail","")
                self.after(0,lambda:(self.info_title.config(text=title,fg=TEXT),self.info_artist.config(text=artist or "?",fg=TEXT),
                    self.info_dur.config(text=fmt_duration(info.get("duration",0)),fg=TEXT),self.info_source.config(text=source,fg=TEXT_BLUE)))
                if th:
                    img=fetch_thumbnail(th,(140,80))
                    if img:
                        ph=ImageTk.PhotoImage(img); self.after(0,lambda ph=ph:(self.thumb.config(image=ph,text="",width=140,height=80),setattr(self.thumb,"_img",ph)))
            # Find file
            actual=os.path.join(out,f"{title}.{fmt}")
            if not os.path.exists(actual):
                safe=sanitize_filename(title)
                for f in os.listdir(out):
                    if f.endswith(f".{fmt}") and (title[:20] in f or safe[:20] in f):
                        actual=os.path.join(out,f); break
            self._last_file = actual if os.path.exists(actual) else None
            # Tag MP3 — create ID3 header if missing (mutagen.id3.ID3NoHeaderError)
            if fmt=="mp3" and self._last_file:
                try:
                    try: audio=ID3(self._last_file)
                    except mutagen.id3.ID3NoHeaderError: audio=ID3(); audio.save(self._last_file)
                    audio["TIT2"]=TIT2(encoding=3,text=title); audio["TPE1"]=TPE1(encoding=3,text=artist)
                    if info.get("upload_date"): audio["TDRC"]=TDRC(encoding=3,text=info["upload_date"][:4])
                    if th:
                        try:
                            resp=requests.get(th,timeout=5)
                            # Detect MIME from content for correct artwork embedding
                            ct=resp.headers.get("content-type","image/jpeg")
                            mime=ct.split(";")[0].strip() if ct else "image/jpeg"
                            audio["APIC"]=APIC(encoding=3,mime=mime,type=3,desc="Cover",data=resp.content)
                        except Exception: pass
                    audio.save(self._last_file)
                except Exception: pass
            now_t=datetime.datetime.now().strftime("%H:%M")
            self._recent.insert(0,f"  OK     {title[:35]:35s} {source:10s} {fmt.upper():6s} {now_t}")
            self.after(0,self._render_recent)
            entry={"title":title,"url":url,"mode":mode,"format":fmt,"status":"done","source":source,
                   "date":datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),"folder":out,
                   "filepath":self._last_file}
            self.after(0,lambda:self.app.add_history(entry))
            self.after(0,lambda:(self.info_status.config(text=f"Complete! Saved as {fmt.upper()}",fg=LIME_DK),
                self.app.set_status(f"Done: {title}"),self.app.toast(f"Downloaded: {title[:40]}")))
        except Exception as e:
            msg=str(e); fr=("Cancelled" if "Cancel" in msg else "Rate limited" if "429" in msg else msg[:80])
            self.after(0,lambda:(self.info_status.config(text=f"FAILED: {fr}",fg=RED),self.app.set_status(f"Failed"),
                self.app.toast(f"Failed: {fr[:40]}","error")))
        finally:
            self._downloading=False
            self.after(0,lambda:self.cancel_btn.pack_forget())
    def _render_recent(self):
        self.rec_lb.delete(0,"end")
        for item in self._recent[:RECENT_DL_MAX]: self.rec_lb.insert("end",item)
    def _browse(self):
        d=filedialog.askdirectory(initialdir=self.folder_var.get())
        if d: self.folder_var.set(d)
    def _open_folder(self):
        open_folder(self.folder_var.get())
    def _copy_path(self):
        self.app.clipboard_clear(); self.app.clipboard_append(self.folder_var.get())
    def _analyze_last(self):
        if self._last_file and os.path.exists(self._last_file):
            ap=self.app.pages.get("analyze")
            if ap: ap.file_var.set(self._last_file); self.app._show_tab("analyze")
    def _stems_last(self):
        if self._last_file and os.path.exists(self._last_file):
            sp=self.app.pages.get("stems")
            if sp: sp.file_var.set(self._last_file); self.app._show_tab("stems")


# ═══════════════════════════════════════════════════════════════════════════════
# ANALYZE PAGE — BPM, Key, LUFS, Shazam, MusicBrainz, Chromaprint, Waveform
# ═══════════════════════════════════════════════════════════════════════════════

class AnalyzePage(ScrollFrame):
    """Audio analysis: BPM, key, loudness, waveform, Shazam/MusicBrainz identification."""
    def __init__(self,parent,app):
        super().__init__(parent); self.app=app; self._build(self.inner)
    def _build(self,p):
        # File selector
        fg=GroupBox(p,"Audio File"); fg.pack(fill="x",padx=10,pady=(10,6))
        fr=tk.Frame(fg,bg=BG); fr.pack(fill="x")
        self.file_var=tk.StringVar()
        ClassicEntry(fr,self.file_var,width=55).pack(side="left",fill="x",expand=True,ipady=2,padx=(0,8))
        ClassicBtn(fr,"Browse...",self._browse).pack(side="left",padx=(0,6))
        LimeBtn(fr,"Analyze All",self._run_all).pack(side="left")

        # Waveform display
        wg=GroupBox(p,"Waveform"); wg.pack(fill="x",padx=10,pady=(0,6))
        self.wave_cv=tk.Canvas(wg,bg=CANVAS_BG,height=80,relief="flat",bd=0,highlightthickness=1,highlightbackground=CARD_BORDER)
        self.wave_cv.pack(fill="x")

        # Results grid
        rg=GroupBox(p,"Analysis Results"); rg.pack(fill="x",padx=10,pady=(0,6))
        self.results_frame=tk.Frame(rg,bg=BG); self.results_frame.pack(fill="x")
        # Pre-create result labels
        self._res = {}
        for label in ["BPM","Key","Camelot","Loudness (LUFS)","True Peak","Duration","Sample Rate","File Size"]:
            r=tk.Frame(self.results_frame,bg=BG); r.pack(fill="x",pady=2)
            tk.Label(r,text=f"{label}:",font=F_BOLD,bg=BG,fg=TEXT,width=16,anchor="w").pack(side="left")
            v=tk.Label(r,text="--",font=F_BODY,bg=BG,fg=TEXT_DIM,anchor="w"); v.pack(side="left",fill="x",expand=True)
            self._res[label]=v

        # Identification section
        ig=GroupBox(p,"Track Identification"); ig.pack(fill="x",padx=10,pady=(0,6))
        ibr=tk.Frame(ig,bg=BG); ibr.pack(fill="x",pady=(0,6))
        OrangeBtn(ibr,"Shazam Audio ID" + (" ✓" if HAS_SHAZAM else " ✗"),self._run_shazam).pack(side="left",padx=(0,6))
        LimeBtn(ibr,"Shazam Search (by name)",self._run_shazam_search).pack(side="left",padx=(0,6))
        ClassicBtn(ibr,"Chromaprint/AcoustID",self._run_acoustid).pack(side="left",padx=(0,6))
        ClassicBtn(ibr,"MusicBrainz Lookup",self._run_mb).pack(side="left",padx=(0,6))
        OrangeBtn(ibr,"Apple Music Lookup",self._run_apple_music).pack(side="left",padx=(0,6))
        ClassicBtn(ibr,"Write Tags to File",self._write_tags).pack(side="left")

        self._id_res = {}
        for label in ["Identified Title","Identified Artist","Genre","Album","Shazam URL","Chromaprint","MusicBrainz","Apple Music"]:
            r=tk.Frame(ig,bg=BG); r.pack(fill="x",pady=1)
            tk.Label(r,text=f"{label}:",font=F_BOLD,bg=BG,fg=TEXT,width=16,anchor="w").pack(side="left")
            v=tk.Label(r,text="--",font=F_BODY,bg=BG,fg=TEXT_DIM,anchor="w",wraplength=500,justify="left")
            v.pack(side="left",fill="x",expand=True)
            self._id_res[label]=v

        # Export buttons
        eg=GroupBox(p,"Export Results"); eg.pack(fill="x",padx=10,pady=(0,6))
        er=tk.Frame(eg,bg=BG); er.pack(fill="x")
        ClassicBtn(er,"Export JSON",self._export_json).pack(side="left",padx=(0,6))
        ClassicBtn(er,"Export CSV",self._export_csv).pack(side="left")

        # Audio Tools section
        atg=GroupBox(p,"Audio Tools"); atg.pack(fill="x",padx=10,pady=(0,6))
        atr=tk.Frame(atg,bg=BG); atr.pack(fill="x")
        OrangeBtn(atr,"Noise Reduction" + (" ✓" if HAS_NOISEREDUCE else " ✗"),self._noise_reduce).pack(side="left",padx=(0,6))
        LimeBtn(atr,"Lyrics Lookup" + (" ✓" if HAS_LYRICS else " ✗"),self._lyrics_lookup).pack(side="left",padx=(0,6))
        ClassicBtn(atr,"Effects Chain" + (" ✓" if HAS_PEDALBOARD else " ✗"),
                   lambda:self.app._show_tab("effects")).pack(side="left",padx=(0,6))
        self.lyrics_text=tk.Text(atg,height=6,font=F_MONO,bg=INPUT_BG,fg=TEXT,wrap="word",
                                 relief="flat",bd=0,state="disabled",padx=6,pady=4,
                                 highlightthickness=1,highlightbackground=INPUT_BORDER)
        self.lyrics_text.pack(fill="x",pady=(6,0))

        # DJ Integration section
        dg=GroupBox(p,"DJ Integration"); dg.pack(fill="x",padx=10,pady=(0,6))
        dr=tk.Frame(dg,bg=BG); dr.pack(fill="x")
        OrangeBtn(dr,"Write Serato Tags",self._write_serato_tags).pack(side="left",padx=(0,6))
        ClassicBtn(dr,"Add to Serato Crate",self._add_to_serato_crate).pack(side="left",padx=(0,6))
        tk.Label(dr,text="Crate:",font=F_BODY,bg=BG,fg=TEXT).pack(side="left",padx=(8,4))
        self.crate_var=tk.StringVar(value="LimeWire")
        ClassicEntry(dr,self.crate_var,width=15).pack(side="left",ipady=1,padx=(0,6))
        dr2=tk.Frame(dg,bg=BG); dr2.pack(fill="x",pady=(6,0))
        LimeBtn(dr2,"Open in FL Studio",self._open_fl_studio).pack(side="left",padx=(0,6))
        fl_detected=find_fl_studio()
        tk.Label(dr2,text=f"FL: {'Found' if fl_detected else 'Not found (set in Tools menu)'}",
                 font=F_SMALL,bg=BG,fg=LIME_DK if fl_detected else TEXT_DIM).pack(side="left",padx=(8,0))

        # Loudness Targeting
        lg=GroupBox(p,"Loudness Targeting"); lg.pack(fill="x",padx=10,pady=(0,6))
        lr=tk.Frame(lg,bg=BG); lr.pack(fill="x")
        tk.Label(lr,text="Platform:",font=F_BODY,bg=BG,fg=TEXT).pack(side="left")
        self._lufs_preset=tk.StringVar(value="Spotify (-14 LUFS)")
        _presets=["Spotify (-14 LUFS)","YouTube (-13 LUFS)","Apple Music (-16 LUFS)",
                  "CD/Master (-9 LUFS)","Club (-6 LUFS)","Podcast (-16 LUFS)"]
        ClassicCombo(lr,self._lufs_preset,_presets,width=22).pack(side="left",padx=SP_SM)
        LimeBtn(lr,"Normalize to Target",self._normalize_loudness).pack(side="left",padx=SP_SM)
        lr2=tk.Frame(lg,bg=BG); lr2.pack(fill="x",pady=(SP_XS,0))
        tk.Label(lr2,text="Before:",font=F_BODY,bg=BG,fg=TEXT_DIM).pack(side="left")
        self._lufs_before=tk.Label(lr2,text="-- LUFS",font=F_MONO,bg=BG,fg=TEXT_DIM); self._lufs_before.pack(side="left",padx=(SP_XS,SP_LG))
        tk.Label(lr2,text="After:",font=F_BODY,bg=BG,fg=TEXT_DIM).pack(side="left")
        self._lufs_after=tk.Label(lr2,text="-- LUFS",font=F_MONO,bg=BG,fg=TEXT_DIM); self._lufs_after.pack(side="left",padx=SP_XS)

        self.status_lbl=tk.Label(p,text="Select an audio file and click Analyze All",font=F_SMALL,bg=BG,fg=TEXT_DIM)
        self.status_lbl.pack(padx=10,anchor="w",pady=(0,10))

    def _normalize_loudness(self):
        path=self.file_var.get().strip()
        if not path or not os.path.isfile(path):
            self.status_lbl.config(text="Select a file first",fg=YELLOW); return
        if not HAS_FFMPEG:
            self.status_lbl.config(text="FFmpeg required for loudness normalization",fg=RED); return
        preset=self._lufs_preset.get()
        # Parse target LUFS from preset string
        import re
        m=re.search(r"(-?\d+)",preset)
        target=float(m.group(1)) if m else -14.0
        self.status_lbl.config(text=f"Normalizing to {target:.0f} LUFS...",fg=YELLOW)
        def _do():
            base,ext=os.path.splitext(path)
            out=f"{base}_norm{ext}"
            # Two-pass loudnorm
            try:
                # Pass 1: measure
                r=subprocess.run(["ffmpeg","-i",path,"-af",f"loudnorm=I={target}:TP=-1.5:LRA=11:print_format=json",
                    "-f","null",os.devnull],capture_output=True,text=True,timeout=120)
                # Extract measured values from stderr JSON block
                stderr=r.stderr
                import json as _json
                json_start=stderr.rfind("{"); json_end=stderr.rfind("}")+1
                if json_start>=0:
                    measured=_json.loads(stderr[json_start:json_end])
                    mi=measured.get("input_i","-24"); mtp=measured.get("input_tp","-1")
                    mlra=measured.get("input_lra","7"); mt=measured.get("input_thresh","-34")
                    before_lufs=float(mi)
                    self.after(0,lambda:self._lufs_before.config(text=f"{before_lufs:.1f} LUFS",fg=TEXT))
                    # Pass 2: apply
                    af=f"loudnorm=I={target}:TP=-1.5:LRA=11:measured_I={mi}:measured_TP={mtp}:measured_LRA={mlra}:measured_thresh={mt}:linear=true"
                    subprocess.run(["ffmpeg","-y","-i",path,"-af",af,out],capture_output=True,timeout=300)
                    # Measure output
                    r2=subprocess.run(["ffmpeg","-i",out,"-af","loudnorm=print_format=json","-f","null",os.devnull],
                        capture_output=True,text=True,timeout=120)
                    j2s=r2.stderr.rfind("{"); j2e=r2.stderr.rfind("}")+1
                    if j2s>=0:
                        m2=_json.loads(r2.stderr[j2s:j2e])
                        after_lufs=float(m2.get("input_i",target))
                        self.after(0,lambda:self._lufs_after.config(text=f"{after_lufs:.1f} LUFS",fg=LIME_DK))
                    self.after(0,lambda:(self.status_lbl.config(text=f"Normalized: {os.path.basename(out)}",fg=LIME_DK),
                        self.app.toast(f"Loudness normalized to {target:.0f} LUFS")))
                else:
                    self.after(0,lambda:self.status_lbl.config(text="Could not parse loudnorm output",fg=RED))
            except Exception as e:
                self.after(0,lambda:self.status_lbl.config(text=f"Error: {str(e)[:60]}",fg=RED))
        threading.Thread(target=_do,daemon=True).start()

    def _browse(self):
        f=filedialog.askopenfilename(filetypes=[("Audio","*.mp3 *.wav *.flac *.ogg *.m4a *.aac"),("All","*.*")])
        if f: self.file_var.set(f)

    def _run_all(self):
        path=self.file_var.get()
        if not path or not os.path.exists(path): messagebox.showwarning("LimeWire","Select a valid file."); return
        self.status_lbl.config(text="Analyzing...",fg=YELLOW); self.app.set_status("Analyzing audio...")
        threading.Thread(target=self._do_analyze,args=(path,),daemon=True).start()

    def _do_analyze(self,path):
        # Basic file info
        fsize=os.path.getsize(path)/(1024*1024)
        self.after(0,lambda:self._res["File Size"].config(text=f"{fsize:.1f} MB",fg=TEXT))
        # Duration/SR via ffprobe
        try:
            r=subprocess.run(["ffprobe","-v","quiet","-print_format","json","-show_format","-show_streams",path],
                            capture_output=True,text=True,timeout=15)
            info=json.loads(r.stdout)
            dur=float(info.get("format",{}).get("duration",0))
            sr=info.get("streams",[{}])[0].get("sample_rate","?")
            self.after(0,lambda:(self._res["Duration"].config(text=fmt_duration(dur),fg=TEXT),
                                  self._res["Sample Rate"].config(text=f"{sr} Hz",fg=TEXT)))
        except Exception: pass
        # BPM + Key
        bk=analyze_bpm_key(path)
        if bk.get("bpm"):
            camelot=key_to_camelot(bk.get("key","")) or "?"
            self.after(0,lambda:(self._res["BPM"].config(text=f"{bk['bpm']}",fg=LIME_DK),
                                  self._res["Key"].config(text=bk.get("key","?"),fg=LIME_DK),
                                  self._res["Camelot"].config(text=camelot,fg=LIME_DK)))
        elif bk.get("error"):
            self.after(0,lambda:self._res["BPM"].config(text=bk["error"],fg=RED))
        # Loudness
        loud=analyze_loudness(path)
        if loud.get("lufs") is not None:
            self.after(0,lambda:(self._res["Loudness (LUFS)"].config(text=f"{loud['lufs']} LUFS",fg=TEXT),
                                  self._res["True Peak"].config(text=f"{loud['peak']} dBTP",fg=TEXT)))
        elif loud.get("error"):
            self.after(0,lambda:self._res["Loudness (LUFS)"].config(text=loud["error"],fg=RED))
        # Waveform
        bars=generate_waveform_data(path,600,70)
        if bars:
            self.after(0,lambda:self._draw_waveform(bars))
        self.after(0,lambda:(self.status_lbl.config(text="Analysis complete",fg=LIME_DK),
                              self.app.set_status("Analysis complete")))

    def _draw_waveform(self,bars):
        if not bars: return
        cv=self.wave_cv; cv.delete("all")
        w=cv.winfo_width() or WAVEFORM_W; h=WAVEFORM_H
        bw=max(1,w/len(bars)); gap=max(1,bw*0.15)
        for i,amp in enumerate(bars):
            x=i*bw; bar_h=max(1,amp*h*0.85)
            y1=(h-bar_h)/2; y2=(h+bar_h)/2
            if amp<0.3: color=LIME
            elif amp<0.6: color=_lerp_color(LIME,YELLOW,(amp-0.3)/0.3)
            elif amp<0.85: color=_lerp_color(YELLOW,ORANGE,(amp-0.6)/0.25)
            else: color=RED
            cv.create_rectangle(x+gap/2,y1,x+bw-gap/2,y2,fill=color,outline="")

    def _run_shazam(self):
        path=self.file_var.get()
        if not path or not os.path.exists(path): return
        self.status_lbl.config(text="Identifying with Shazam...",fg=YELLOW)
        threading.Thread(target=self._do_shazam,args=(path,),daemon=True).start()
    def _do_shazam(self,path):
        result=identify_shazam(path)
        if result.get("title"):
            self.after(0,lambda:(
                self._id_res["Identified Title"].config(text=result["title"],fg=LIME_DK),
                self._id_res["Identified Artist"].config(text=result.get("artist","?"),fg=TEXT),
                self._id_res["Genre"].config(text=result.get("genre","?"),fg=TEXT),
                self._id_res["Shazam URL"].config(text=result.get("shazam_url",""),fg=TEXT_BLUE),
                self.status_lbl.config(text=f"Shazam: {result['title']} by {result.get('artist','')}",fg=LIME_DK)))
        else:
            self.after(0,lambda:self.status_lbl.config(text=f"Shazam: {result.get('error','No match')}",fg=RED))

    def _run_shazam_search(self):
        """Search Shazam by filename/title — works on any Python version, no Rust needed."""
        path=self.file_var.get()
        if not path: return
        # Use filename as search query
        query = os.path.splitext(os.path.basename(path))[0]
        # Clean up typical YouTube title cruft
        query = re.sub(r'\[.*?\]|\(.*?\)|official.*|music.*video|lyrics|hd|hq|audio|ft\.?|feat\.?', '', query, flags=re.IGNORECASE)
        query = re.sub(r'[_\-]+', ' ', query).strip()
        if not query: messagebox.showinfo("LimeWire","Could not extract search term from filename."); return
        self.status_lbl.config(text=f"Searching Shazam for: {query}",fg=YELLOW)
        threading.Thread(target=self._do_shazam_search,args=(query,),daemon=True).start()
    def _do_shazam_search(self,query):
        result=search_shazam(query)
        if result.get("title"):
            self.after(0,lambda:(
                self._id_res["Identified Title"].config(text=result["title"],fg=LIME_DK),
                self._id_res["Identified Artist"].config(text=result.get("artist","?"),fg=TEXT),
                self._id_res["Genre"].config(text=result.get("genre","?"),fg=TEXT),
                self._id_res["Album"].config(text=result.get("album",""),fg=TEXT),
                self._id_res["Shazam URL"].config(text=result.get("url",""),fg=TEXT_BLUE),
                self.status_lbl.config(text=f"Found: {result['title']} by {result.get('artist','')}",fg=LIME_DK)))
        else:
            self.after(0,lambda:self.status_lbl.config(text=f"Search: {result.get('error','No results')}",fg=RED))

    def _run_acoustid(self):
        path=self.file_var.get()
        if not path or not os.path.exists(path): return
        self.status_lbl.config(text="Fingerprinting with Chromaprint...",fg=YELLOW)
        threading.Thread(target=self._do_acoustid,args=(path,),daemon=True).start()
    def _do_acoustid(self,path):
        result=identify_acoustid(path)
        if result.get("title"):
            self.after(0,lambda:(
                self._id_res["Chromaprint"].config(text=f"{result['title']} by {result.get('artist','')} (score: {result.get('score','')})",fg=LIME_DK),
                self.status_lbl.config(text=f"Chromaprint matched",fg=LIME_DK)))
        else:
            self.after(0,lambda:self._id_res["Chromaprint"].config(text=result.get("error","No match"),fg=RED))

    def _run_mb(self):
        title=self._id_res["Identified Title"].cget("text")
        artist=self._id_res["Identified Artist"].cget("text")
        if title=="--" or not title: messagebox.showinfo("LimeWire","Run Shazam or Chromaprint first to get title/artist."); return
        self.status_lbl.config(text="Looking up MusicBrainz...",fg=YELLOW)
        threading.Thread(target=self._do_mb,args=(title,artist),daemon=True).start()
    def _do_mb(self,title,artist):
        result=lookup_musicbrainz(title,artist)
        if result.get("mb_title"):
            self.after(0,lambda:(
                self._id_res["MusicBrainz"].config(text=f"{result['mb_title']} — {result.get('mb_artist','')} [{result.get('mb_album','')}] ({result.get('mb_date','')})",fg=LIME_DK),
                self.status_lbl.config(text="MusicBrainz match found",fg=LIME_DK)))
        else:
            self.after(0,lambda:self._id_res["MusicBrainz"].config(text=result.get("error","No match"),fg=RED))

    def _run_apple_music(self):
        title=self._id_res["Identified Title"].cget("text")
        artist=self._id_res["Identified Artist"].cget("text")
        if title=="--" or not title: messagebox.showinfo("LimeWire","Run Shazam or Chromaprint first to get title/artist."); return
        self.status_lbl.config(text="Looking up Apple Music...",fg=YELLOW)
        threading.Thread(target=self._do_apple_music,args=(title,artist),daemon=True).start()
    def _do_apple_music(self,title,artist):
        result=lookup_apple_music(title,artist)
        if result.get("am_title"):
            dur_s=result.get("am_duration_ms",0)//1000
            info=f"{result['am_title']} — {result.get('am_artist','')} [{result.get('am_album','')}] ({result.get('am_date','')}) {fmt_duration(dur_s)}"
            self.after(0,lambda:(
                self._id_res["Apple Music"].config(text=info,fg=LIME_DK),
                self._id_res["Genre"].config(text=result.get("am_genre","?"),fg=TEXT) if self._id_res["Genre"].cget("text")=="--" else None,
                self._id_res["Album"].config(text=result.get("am_album",""),fg=TEXT) if self._id_res["Album"].cget("text")=="--" else None,
                self.status_lbl.config(text=f"Apple Music: {result['am_title']}",fg=LIME_DK)))
        else:
            self.after(0,lambda:self._id_res["Apple Music"].config(text=result.get("error","No match"),fg=RED))

    def _write_tags(self):
        path=self.file_var.get()
        if not path or not os.path.exists(path) or not path.lower().endswith(".mp3"):
            messagebox.showinfo("LimeWire","Select an MP3 file first."); return
        title=self._id_res["Identified Title"].cget("text")
        artist=self._id_res["Identified Artist"].cget("text")
        bpm_str=self._res["BPM"].cget("text")
        key_str=self._res["Key"].cget("text")
        try:
            audio=ID3(path)
            if title and title!="--": audio["TIT2"]=TIT2(encoding=3,text=title)
            if artist and artist!="--": audio["TPE1"]=TPE1(encoding=3,text=artist)
            if bpm_str and bpm_str!="--":
                try: audio["TBPM"]=TBPM(encoding=3,text=str(int(float(bpm_str))))
                except Exception: pass
            if key_str and key_str!="--": audio["TKEY"]=TKEY(encoding=3,text=key_str)
            genre=self._id_res["Genre"].cget("text")
            if genre and genre!="--": audio["TCON"]=TCON(encoding=3,text=genre)
            audio.save()
            self.status_lbl.config(text="Tags written to MP3",fg=LIME_DK)
        except Exception as e:
            self.status_lbl.config(text=f"Tag error: {str(e)[:60]}",fg=RED)

    def _get_results_dict(self):
        data={}
        for k,v in self._res.items():
            val=v.cget("text"); data[k]=val if val!="--" else None
        for k,v in self._id_res.items():
            val=v.cget("text"); data[k]=val if val!="--" else None
        data["file"]=self.file_var.get()
        return data
    def _export_json(self):
        data=self._get_results_dict()
        if not data.get("file"): return
        path=filedialog.asksaveasfilename(defaultextension=".json",filetypes=[("JSON","*.json")],
            initialfile=os.path.splitext(os.path.basename(data["file"]))[0]+"_analysis.json")
        if path:
            save_json(path,data); self.status_lbl.config(text=f"Exported to {os.path.basename(path)}",fg=LIME_DK)
    def _export_csv(self):
        data=self._get_results_dict()
        if not data.get("file"): return
        path=filedialog.asksaveasfilename(defaultextension=".csv",filetypes=[("CSV","*.csv")],
            initialfile=os.path.splitext(os.path.basename(data["file"]))[0]+"_analysis.csv")
        if path:
            import csv
            with open(path,"w",newline="") as f:
                w=csv.writer(f); w.writerow(data.keys()); w.writerow(data.values())
            self.status_lbl.config(text=f"Exported to {os.path.basename(path)}",fg=LIME_DK)

    # ── DJ Integration methods ──
    def _write_serato_tags(self):
        path=self.file_var.get()
        if not path or not os.path.exists(path) or not path.lower().endswith(".mp3"):
            messagebox.showinfo("LimeWire","Select an MP3 file first."); return
        bpm_str=self._res["BPM"].cget("text")
        key_str=self._res["Key"].cget("text")
        bpm=float(bpm_str) if bpm_str and bpm_str!="--" else None
        key=key_str if key_str and key_str!="--" else None
        if not bpm and not key:
            messagebox.showinfo("LimeWire","Run analysis first to get BPM/Key."); return
        ok,err=write_serato_tags(path,bpm=bpm,key=key)
        if ok:
            camelot=key_to_camelot(key) or ""
            self.status_lbl.config(text=f"Serato tags written — BPM:{int(bpm) if bpm else '?'} Key:{key_to_serato_tkey(key) or '?'} Camelot:{camelot}",fg=LIME_DK)
            self.app.toast("Serato tags written")
        else:
            self.status_lbl.config(text=f"Serato error: {err}",fg=RED)

    def _add_to_serato_crate(self):
        path=self.file_var.get()
        if not path or not os.path.exists(path):
            messagebox.showinfo("LimeWire","Select a file first."); return
        crate_name=self.crate_var.get().strip() or "LimeWire"
        ok,msg=add_to_serato_crate(path,crate_name)
        if ok:
            self.status_lbl.config(text=f"Added to Serato crate: {crate_name}" + (f" ({msg})" if msg else ""),fg=LIME_DK)
            self.app.toast(f"Added to crate: {crate_name}")
        else:
            self.status_lbl.config(text=f"Crate error: {msg}",fg=RED)

    def _open_fl_studio(self):
        path=self.file_var.get()
        fl_path=self.app.settings.get("fl_studio_path","")
        ok,err=open_in_fl_studio(path,fl_path or None)
        if not ok:
            messagebox.showinfo("LimeWire",f"FL Studio: {err}")

    def _noise_reduce(self):
        path=self.file_var.get()
        if not path or not os.path.exists(path):
            messagebox.showinfo("LimeWire","Select an audio file first."); return
        if not HAS_NOISEREDUCE:
            messagebox.showinfo("LimeWire","noisereduce not installed.\nRun: pip install noisereduce"); return
        self.status_lbl.config(text="Applying noise reduction...",fg=YELLOW)
        def _do():
            out,err=reduce_noise(path)
            if out:
                self.after(0,lambda:(self.status_lbl.config(text=f"Cleaned: {os.path.basename(out)}",fg=LIME_DK),
                    self.app.toast(f"Noise reduced: {os.path.basename(out)}")))
            else:
                self.after(0,lambda:self.status_lbl.config(text=f"Noise reduction error: {err}",fg=RED))
        threading.Thread(target=_do,daemon=True).start()

    def _lyrics_lookup(self):
        title=self._id_res["Identified Title"].cget("text")
        artist=self._id_res["Identified Artist"].cget("text")
        if title=="--" or not title:
            # Try filename
            path=self.file_var.get()
            if path:
                title=os.path.splitext(os.path.basename(path))[0]
                title=re.sub(r'\[.*?\]|\(.*?\)|official.*|music.*video|lyrics|hd|hq|audio',
                             '',title,flags=re.IGNORECASE)
                title=re.sub(r'[_\-]+',' ',title).strip()
            else:
                messagebox.showinfo("LimeWire","Identify a track first or select a file."); return
            artist=""
        self.status_lbl.config(text=f"Looking up lyrics: {title}...",fg=YELLOW)
        api_key=self.app.settings.get("genius_api_key","")
        def _do():
            result=lookup_lyrics(title,artist,api_key)
            if result.get("lyrics"):
                self.after(0,lambda:self._show_lyrics(result))
            else:
                self.after(0,lambda:self.status_lbl.config(text=f"Lyrics: {result.get('error','Not found')}",fg=RED))
        threading.Thread(target=_do,daemon=True).start()

    def _show_lyrics(self,result):
        self.lyrics_text.config(state="normal")
        self.lyrics_text.delete("1.0","end")
        header=f"{result.get('title','')} — {result.get('artist','')}\n{'─'*60}\n"
        self.lyrics_text.insert("1.0",header+result.get("lyrics",""))
        self.lyrics_text.config(state="disabled")
        self.status_lbl.config(text=f"Lyrics: {result['title']} by {result.get('artist','')}",fg=LIME_DK)


# ═══════════════════════════════════════════════════════════════════════════════
# STEMS PAGE — Demucs stem separation
# ═══════════════════════════════════════════════════════════════════════════════

class StemsPage(ScrollFrame):
    """AI stem separation using Demucs with FL Studio integration."""
    def __init__(self,parent,app):
        super().__init__(parent); self.app=app; self._running=False; self._build(self.inner)
    def _build(self,p):
        fg=GroupBox(p,"Source Audio File"); fg.pack(fill="x",padx=10,pady=(10,6))
        fr=tk.Frame(fg,bg=BG); fr.pack(fill="x")
        self.file_var=tk.StringVar()
        ClassicEntry(fr,self.file_var,width=55).pack(side="left",fill="x",expand=True,ipady=2,padx=(0,8))
        ClassicBtn(fr,"Browse...",self._browse).pack(side="left")

        sg=GroupBox(p,"Separation Settings"); sg.pack(fill="x",padx=10,pady=(0,6))
        sr=tk.Frame(sg,bg=BG); sr.pack(fill="x")
        mc=tk.Frame(sr,bg=BG); mc.pack(side="left",padx=(0,20))
        tk.Label(mc,text="Model:",font=F_BOLD,bg=BG,fg=TEXT).pack(anchor="w")
        self.model_var=tk.StringVar(value="htdemucs")
        ClassicCombo(mc,self.model_var,["htdemucs","htdemucs_ft","htdemucs_6s","mdx_extra_q"],width=14).pack(anchor="w")

        ts=tk.Frame(sr,bg=BG); ts.pack(side="left",padx=(0,20))
        tk.Label(ts,text="Separation Mode:",font=F_BOLD,bg=BG,fg=TEXT).pack(anchor="w")
        self.stems_mode=tk.StringVar(value="all")
        tk.Radiobutton(ts,text="All stems (vocals/drums/bass/other)",variable=self.stems_mode,value="all",
                       font=F_BODY,bg=BG,fg=TEXT,selectcolor=INPUT_BG,activebackground=BG,activeforeground=TEXT).pack(anchor="w")
        tk.Radiobutton(ts,text="Vocals only (karaoke mode)",variable=self.stems_mode,value="vocals",
                       font=F_BODY,bg=BG,fg=TEXT,selectcolor=INPUT_BG,activebackground=BG,activeforeground=TEXT).pack(anchor="w")
        tk.Radiobutton(ts,text="Drums only",variable=self.stems_mode,value="drums",
                       font=F_BODY,bg=BG,fg=TEXT,selectcolor=INPUT_BG,activebackground=BG,activeforeground=TEXT).pack(anchor="w")
        tk.Radiobutton(ts,text="Bass only",variable=self.stems_mode,value="bass",
                       font=F_BODY,bg=BG,fg=TEXT,selectcolor=INPUT_BG,activebackground=BG,activeforeground=TEXT).pack(anchor="w")

        og=GroupBox(p,"Output Folder"); og.pack(fill="x",padx=10,pady=(0,6))
        ofr=tk.Frame(og,bg=BG); ofr.pack(fill="x")
        self.out_var=tk.StringVar(value=os.path.join(self.app.output_dir,"Stems"))
        ClassicEntry(ofr,self.out_var,width=55).pack(side="left",fill="x",expand=True,ipady=2,padx=(0,8))
        ClassicBtn(ofr,"Browse...",lambda:(d:=filedialog.askdirectory(initialdir=self.out_var.get())) and self.out_var.set(d)).pack(side="left")

        bf=tk.Frame(p,bg=BG); bf.pack(fill="x",padx=10,pady=8)
        LimeBtn(bf,"Split Stems",self._run,width=18).pack(side="left",padx=(0,8))
        ClassicBtn(bf,"Open Output Folder",self._open_out).pack(side="left")

        pg=GroupBox(p,"Status"); pg.pack(fill="x",padx=10,pady=(0,6))
        self.stem_prog=ClassicProgress(pg); self.stem_prog.pack(fill="x",pady=(0,4))
        self.stem_status=tk.Label(pg,text="Select a file and click Split Stems. Uses Demucs AI model.",
                                  font=F_BODY,bg=BG,fg=TEXT_DIM,anchor="w",wraplength=700,justify="left")
        self.stem_status.pack(fill="x")

        # FL Studio Integration
        fl_g=GroupBox(p,"FL Studio Integration"); fl_g.pack(fill="x",padx=10,pady=(0,6))
        fl_r=tk.Frame(fl_g,bg=BG); fl_r.pack(fill="x")
        LimeBtn(fl_r,"Export for FL Studio",self._export_for_fl).pack(side="left",padx=(0,6))
        OrangeBtn(fl_r,"Create FL Project (.flp)" + (" ✓" if HAS_PYFLP else " ✗"),self._create_fl_project).pack(side="left",padx=(0,6))
        ClassicBtn(fl_r,"Open in FL Studio",self._open_fl_in_studio).pack(side="left")
        self.fl_status=tk.Label(fl_g,text="Split stems first, then export for FL Studio or create .flp project",
                                font=F_SMALL,bg=BG,fg=TEXT_DIM,anchor="w")
        self.fl_status.pack(fill="x",pady=(4,0))

        # Info about models
        info_g=GroupBox(p,"Model Info"); info_g.pack(fill="x",padx=10,pady=(0,10))
        tk.Label(info_g,text="htdemucs — Default Hybrid Transformer model. Good balance of speed and quality.\n"
                 "htdemucs_ft — Fine-tuned version. 4x slower but best quality.\n"
                 "htdemucs_6s — 6 stems: adds piano and guitar separation.\n"
                 "mdx_extra_q — Quantized MDX model. Smaller, faster, slightly less accurate.",
                 font=F_SMALL,bg=BG,fg=TEXT_DIM,justify="left",anchor="w").pack(fill="x")

    def _browse(self):
        f=filedialog.askopenfilename(filetypes=[("Audio","*.mp3 *.wav *.flac *.ogg *.m4a"),("All","*.*")])
        if f: self.file_var.set(f)

    def _run(self):
        path=self.file_var.get()
        if not path or not os.path.exists(path): messagebox.showwarning("LimeWire","Select a valid audio file."); return
        if self._running: return
        self._running=True
        model=self.model_var.get(); mode=self.stems_mode.get()
        two_stems=None if mode=="all" else mode
        out=self.out_var.get()
        self.stem_status.config(text=f"Running Demucs ({model})... This may take several minutes.",fg=YELLOW)
        self.stem_prog.config(mode="indeterminate"); self.stem_prog.start(20)
        self.app.set_status(f"Splitting stems with {model}...")
        threading.Thread(target=self._do_split,args=(path,out,model,two_stems),daemon=True).start()

    def _do_split(self,path,out,model,two_stems):
        try:
            result=run_demucs(path,out,model,two_stems)
            self.after(0,lambda:self.stem_prog.stop())
            self.after(0,lambda:self.stem_prog.config(mode="determinate"))
            if result is True:
                track_name=os.path.splitext(os.path.basename(path))[0]
                stem_dir=os.path.join(out,model,track_name)
                stems_found=[]
                if os.path.exists(stem_dir):
                    stems_found=[f for f in os.listdir(stem_dir) if f.endswith(".wav")]
                self.after(0,lambda:(
                    self.stem_prog.configure(value=100),
                    self.stem_status.config(text=f"Done! {len(stems_found)} stems saved to: {stem_dir}\nFiles: {', '.join(stems_found)}",fg=LIME_DK),
                    self.app.set_status("Stem separation complete")))
            else:
                self.after(0,lambda:(
                    self.stem_status.config(text=f"Error: {result}",fg=RED),
                    self.app.set_status("Stem separation failed")))
        finally:
            self._running=False

    def _open_out(self):
        open_folder(self.out_var.get())

    def _get_stem_dir(self):
        path=self.file_var.get()
        if not path: return None
        track_name=os.path.splitext(os.path.basename(path))[0]
        model=self.model_var.get()
        stem_dir=os.path.join(self.out_var.get(),model,track_name)
        return stem_dir if os.path.exists(stem_dir) else None

    def _export_for_fl(self):
        stem_dir=self._get_stem_dir()
        if not stem_dir:
            messagebox.showinfo("LimeWire","Split stems first."); return
        track_name=os.path.splitext(os.path.basename(self.file_var.get()))[0]
        bpm=None; key=None
        ap=self.app.pages.get("analyze")
        if ap:
            try: bpm=float(ap._res["BPM"].cget("text"))
            except Exception: pass
            k=ap._res["Key"].cget("text")
            key=k if k and k!="--" else None
        out_dir,copied=export_stems_for_fl(stem_dir,track_name,bpm,key)
        self.fl_status.config(text=f"Exported {len(copied)} stems to: {out_dir}",fg=LIME_DK)
        self.app.toast(f"FL Export: {len(copied)} stems")

    def _create_fl_project(self):
        stem_dir=self._get_stem_dir()
        if not stem_dir:
            messagebox.showinfo("LimeWire","Split stems first."); return
        if not HAS_PYFLP:
            messagebox.showinfo("LimeWire","pyflp not installed. Run: pip install pyflp"); return
        track_name=os.path.splitext(os.path.basename(self.file_var.get()))[0]
        bpm=None
        ap=self.app.pages.get("analyze")
        if ap:
            try: bpm=float(ap._res["BPM"].cget("text"))
            except Exception: pass
        self.fl_status.config(text="Generating FL Studio project...",fg=YELLOW)
        threading.Thread(target=self._do_create_fl,args=(stem_dir,track_name,bpm),daemon=True).start()

    def _do_create_fl(self,stem_dir,track_name,bpm):
        flp_path,err=create_fl_project(stem_dir,track_name,bpm)
        if flp_path:
            self.after(0,lambda:(self.fl_status.config(text=f"FL project: {os.path.basename(flp_path)}",fg=LIME_DK),
                self.app.toast(f"Created {os.path.basename(flp_path)}")))
        else:
            self.after(0,lambda:self.fl_status.config(text=f"FLP error: {err}",fg=RED))

    def _open_fl_in_studio(self):
        stem_dir=self._get_stem_dir()
        flp_path=None
        if stem_dir:
            track_name=os.path.splitext(os.path.basename(self.file_var.get()))[0]
            candidate=os.path.join(os.path.dirname(stem_dir),f"{track_name}_stems.flp")
            if os.path.exists(candidate): flp_path=candidate
        fl_path=self.app.settings.get("fl_studio_path","")
        ok,err=open_in_fl_studio(flp_path,fl_path or None)
        if not ok:
            messagebox.showinfo("LimeWire",f"FL Studio: {err}")


# ═══════════════════════════════════════════════════════════════════════════════
# REMAINING PAGES — Batch Download, Playlist, Converter, Player, Scheduler, History
# (Same as v4.2 with waveform added to Player)
# ═══════════════════════════════════════════════════════════════════════════════

class DownloadPage(ScrollFrame):
    """Batch download multiple URLs with concurrent workers."""
    def __init__(self,parent,app):
        super().__init__(parent); self.app=app; self._build(self.inner)
        # Restore persisted queue
        saved=load_json(QUEUE_FILE,[])
        for url in saved:
            self.ul.insert("end",url)
        self.cnt.config(text=f"{self.ul.size()} items")
    def _build(self,p):
        qg=GroupBox(p,"Download Queue"); qg.pack(fill="x",padx=10,pady=(10,6))
        qr=tk.Frame(qg,bg=BG); qr.pack(fill="x",pady=(0,6))
        tk.Label(qr,text="URL:",font=F_BOLD,bg=BG,fg=TEXT).pack(side="left",padx=(0,6))
        self.url_var=tk.StringVar(); self.url_e=ClassicEntry(qr,self.url_var,width=45)
        self.url_e.pack(side="left",fill="x",expand=True,ipady=2,padx=(0,6))
        self.url_e.bind("<Return>",lambda e:self._add())
        LimeBtn(qr,"+ Add",self._add).pack(side="left")
        self.uf,self.ul=ClassicListbox(qg,height=4); self.uf.pack(fill="x",pady=(0,4))
        ar=tk.Frame(qg,bg=BG); ar.pack(fill="x")
        ClassicBtn(ar,"Remove",self._remove).pack(side="left",padx=(0,4)); ClassicBtn(ar,"Clear",self._clear).pack(side="left")
        self.cnt=tk.Label(ar,text="0 items",font=F_BODY,bg=BG,fg=TEXT_DIM); self.cnt.pack(side="right")
        sg=GroupBox(p,"Settings"); sg.pack(fill="x",padx=10,pady=(0,6))
        sr=tk.Frame(sg,bg=BG); sr.pack(fill="x")
        mc=tk.Frame(sr,bg=BG); mc.pack(side="left",padx=(0,16))
        tk.Label(mc,text="Type:",font=F_BOLD,bg=BG,fg=TEXT).pack(anchor="w")
        self.mode=tk.StringVar(value="audio")
        tk.Radiobutton(mc,text="Audio",variable=self.mode,value="audio",font=F_BODY,bg=BG,fg=TEXT,selectcolor=INPUT_BG).pack(anchor="w")
        tk.Radiobutton(mc,text="Video",variable=self.mode,value="video",font=F_BODY,bg=BG,fg=TEXT,selectcolor=INPUT_BG).pack(anchor="w")
        fc=tk.Frame(sr,bg=BG); fc.pack(side="left",padx=(0,16))
        tk.Label(fc,text="Format:",font=F_BOLD,bg=BG,fg=TEXT).pack(anchor="w")
        self.afmt=tk.StringVar(value="mp3"); ClassicCombo(fc,self.afmt,AUDIO_FMTS,10).pack(anchor="w")
        qc=tk.Frame(sr,bg=BG); qc.pack(side="left",padx=(0,16))
        tk.Label(qc,text="Quality:",font=F_BOLD,bg=BG,fg=TEXT).pack(anchor="w")
        self.vqual=tk.StringVar(value="1080p"); ClassicCombo(qc,self.vqual,QUALITIES,10).pack(anchor="w")
        wc=tk.Frame(sr,bg=BG); wc.pack(side="left")
        tk.Label(wc,text="Threads:",font=F_BOLD,bg=BG,fg=TEXT).pack(anchor="w")
        self.workers=tk.IntVar(value=2)
        tk.Spinbox(wc,from_=1,to=5,textvariable=self.workers,width=4,font=F_BODY,bg=INPUT_BG,fg=TEXT,
                   relief="flat",bd=0,highlightthickness=1,highlightbackground=INPUT_BORDER,
                   buttonbackground=BG).pack(anchor="w")
        self.skip=tk.BooleanVar(value=True); ClassicCheck(sg,"Skip already downloaded",self.skip).pack(anchor="w")
        fg_=GroupBox(p,"Save To"); fg_.pack(fill="x",padx=10,pady=(0,6))
        fr=tk.Frame(fg_,bg=BG); fr.pack(fill="x")
        self.folder=tk.StringVar(value=self.app.output_dir)
        ClassicEntry(fr,self.folder,width=55).pack(side="left",fill="x",expand=True,ipady=2,padx=(0,8))
        ClassicBtn(fr,"Browse...",lambda:(d:=filedialog.askdirectory(initialdir=self.folder.get())) and self.folder.set(d)).pack(side="left")
        bf=tk.Frame(p,bg=BG); bf.pack(fill="x",padx=10,pady=6)
        LimeBtn(bf,"Download All",self._start,width=18).pack(side="left")
        self.dl_st=tk.Label(bf,text="",font=F_BODY,bg=BG,fg=TEXT_DIM); self.dl_st.pack(side="left",padx=(12,0))
        pg=GroupBox(p,"Progress"); pg.pack(fill="x",padx=10,pady=(0,6))
        o=tk.Frame(pg,bg=BG); o.pack(fill="x",pady=(0,4))
        tk.Label(o,text="Overall:",font=F_BOLD,bg=BG,fg=TEXT).pack(side="left",padx=(0,6))
        self.ov_bar=ClassicProgress(o); self.ov_bar.pack(side="left",fill="x",expand=True)
        self.ov_lbl=tk.Label(o,text="0/0",font=F_BODY,bg=BG,fg=TEXT,width=6); self.ov_lbl.pack(side="left")
        t_=tk.Frame(pg,bg=BG); t_.pack(fill="x")
        tk.Label(t_,text="Current:",font=F_BOLD,bg=BG,fg=TEXT).pack(side="left",padx=(0,6))
        self.tr_bar=ClassicProgress(t_); self.tr_bar.pack(side="left",fill="x",expand=True)
        self.tr_name=tk.Label(pg,text="--",font=F_SMALL,bg=BG,fg=TEXT_DIM,anchor="w"); self.tr_name.pack(fill="x",pady=(2,0))
        from tkinter import scrolledtext as st
        log_g=GroupBox(p,"Log"); log_g.pack(fill="both",padx=10,pady=(0,10),expand=True)
        self.log=st.ScrolledText(log_g,font=F_MONO,bg=INPUT_BG,fg=TEXT,relief="flat",bd=0,height=5,state="disabled",padx=6,pady=4,
                                 highlightthickness=1,highlightbackground=INPUT_BORDER)
        self.log.pack(fill="both",expand=True)
        self.log.tag_config("ok",foreground=LIME_DK); self.log.tag_config("warn",foreground=YELLOW)
        self.log.tag_config("error",foreground=RED); self.log.tag_config("dim",foreground=TEXT_DIM)
    def _persist_queue(self):
        save_json(QUEUE_FILE,list(self.ul.get(0,"end")))
    def _add(self):
        url=self.url_var.get().strip()
        if url and "http" in url:
            self.ul.insert("end",url); self.url_var.set(""); self.cnt.config(text=f"{self.ul.size()} items")
            self._persist_queue()
    def _remove(self):
        for i in reversed(self.ul.curselection()): self.ul.delete(i)
        self.cnt.config(text=f"{self.ul.size()} items"); self._persist_queue()
    def _clear(self): self.ul.delete(0,"end"); self.cnt.config(text="0 items"); self._persist_queue()
    def _lm(self,msg,tag="ok"):
        def d(): self.log.configure(state="normal"); self.log.insert("end",msg+"\n",tag); self.log.see("end"); self.log.configure(state="disabled")
        self.after(0,d)
    def _start(self):
        urls=list(self.ul.get(0,"end"))
        if not urls: self._lm("Add URLs first","warn"); return
        self.app._total=len(urls); self.app._completed=0; self.ov_bar["value"]=0
        self.ov_lbl.config(text=f"0/{len(urls)}"); self.dl_st.config(text="Downloading...",fg=LIME_DK)
        threading.Thread(target=self._pool,args=(urls,),daemon=True).start()
    def _pool(self,urls):
        with ThreadPoolExecutor(max_workers=self.workers.get()) as pool:
            for f in as_completed({pool.submit(self._dl,i+1,u):u for i,u in enumerate(urls)}): pass
        self._lm(f"\nDone - {self.app._completed}/{self.app._total}","ok")
        all_ok=self.app._completed==self.app._total
        self.after(0,lambda:(self.dl_st.config(text=f"Complete: {self.app._completed}/{self.app._total}"),
            self._clear() if all_ok else None,
            self.app.toast(f"Batch: {self.app._completed}/{self.app._total}" + (" - some failed" if not all_ok else ""),
                           "info" if all_ok else "warn")))
    def _dl(self,idx,url):
        out=self.folder.get(); th=[None]; os.makedirs(out,exist_ok=True)
        mode=self.mode.get(); page=self
        class L:
            def debug(s,m): pass
            def warning(s,m): pass
            def error(s,m): page._lm(f"ERR: {m.strip()[:60]}","error")
        def hook(d):
            t=th[0] or f"track {idx}"
            if d["status"]=="downloading":
                try: pct=float(d.get("_percent_str","0%").strip().replace("%",""))
                except Exception: pct=0
                self.after(0,lambda:(self.tr_bar.__setitem__("value",pct),self.tr_name.config(text=t[:50])))
        base={"outtmpl":os.path.join(out,"%(title)s.%(ext)s"),"logger":L(),"progress_hooks":[hook],"quiet":True,
              **({"download_archive":os.path.join(out,".archive.txt")} if self.skip.get() else {})}
        if mode=="audio": base.update({"format":"bestaudio/best","postprocessors":[{"key":"FFmpegExtractAudio","preferredcodec":self.afmt.get()}]})
        else:
            q=self.vqual.get()
            vf="bestvideo+bestaudio/best" if q=="best" else f"bestvideo[height<={q[:-1]}]+bestaudio/best[height<={q[:-1]}]"
            base.update({"format":vf,"merge_output_format":"mp4"})
        status="error"; title=url
        try:
            with yt_dlp.YoutubeDL({**YDL_BASE,**base}) as ydl:
                info=ydl.extract_info(url,download=False); title=info.get("title",url); th[0]=title
                self._lm(f"[{idx}] {title}","ok"); ydl.download([url])
            self._lm(f"[{idx}] Saved","dim"); status="done"
        except Exception as e: self._lm(f"[{idx}] FAILED: {str(e)[:60]}","error")
        self.after(0,lambda:self.app.add_history({"title":title,"url":url,"mode":mode,"format":self.afmt.get(),
            "status":status,"date":datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),"folder":out}))
        with self.app._lock: self.app._completed+=1
        self.after(0,lambda:(self.ov_bar.__setitem__("value",int((self.app._completed/max(1,self.app._total))*100)),
            self.ov_lbl.config(text=f"{self.app._completed}/{self.app._total}")))

class PlaylistPage(ScrollFrame):
    """Fetch and selectively download tracks from online playlists."""
    def __init__(self,parent,app):
        super().__init__(parent); self.app=app; self._tracks=[]; self._cvars=[]; self._build(self.inner)
    def _build(self,p):
        g=GroupBox(p,"Playlist URL"); g.pack(fill="x",padx=10,pady=(10,6))
        r=tk.Frame(g,bg=BG); r.pack(fill="x")
        self.pl_var=tk.StringVar(); ClassicEntry(r,self.pl_var,width=50).pack(side="left",fill="x",expand=True,ipady=2,padx=(0,8))
        LimeBtn(r,"Fetch",self._fetch).pack(side="left")
        self.pl_st=tk.Label(g,text="",font=F_SMALL,bg=BG,fg=TEXT_DIM); self.pl_st.pack(anchor="w",pady=(4,0))
        tg=GroupBox(p,"Tracks"); tg.pack(fill="both",padx=10,pady=(0,6),expand=True)
        cr=tk.Frame(tg,bg=BG); cr.pack(fill="x",pady=(0,4))
        ClassicBtn(cr,"All",self._sel_all).pack(side="left",padx=(0,4)); ClassicBtn(cr,"None",self._desel).pack(side="left")
        self.sel_cnt=tk.Label(cr,text="",font=F_BODY,bg=BG,fg=TEXT_DIM); self.sel_cnt.pack(side="right")
        self.tf=tk.Frame(tg,bg=INPUT_BG,relief="flat",bd=0,highlightthickness=1,highlightbackground=CARD_BORDER)
        self.tf.pack(fill="both",expand=True)
        self.ti=tk.Frame(self.tf,bg=INPUT_BG); self.ti.pack(fill="both",expand=True,padx=4,pady=4)
        sg=GroupBox(p,"Settings"); sg.pack(fill="x",padx=10,pady=(0,6))
        sr=tk.Frame(sg,bg=BG); sr.pack(fill="x")
        for lbl,attr,vals,dflt,w in [("Mode:","pl_mode",["audio","video"],"audio",8),("Fmt:","pl_fmt",AUDIO_FMTS,"mp3",8)]:
            c=tk.Frame(sr,bg=BG); c.pack(side="left",padx=(0,16))
            tk.Label(c,text=lbl,font=F_BOLD,bg=BG,fg=TEXT).pack(anchor="w")
            var=tk.StringVar(value=dflt); setattr(self,attr,var); ClassicCombo(c,var,vals,w).pack(anchor="w")
        fc=tk.Frame(sr,bg=BG); fc.pack(side="left",fill="x",expand=True)
        tk.Label(fc,text="Save To:",font=F_BOLD,bg=BG,fg=TEXT).pack(anchor="w")
        self.pl_folder=tk.StringVar(value=self.app.output_dir)
        ClassicEntry(fc,self.pl_folder,width=30).pack(side="left",fill="x",expand=True,ipady=2)
        bf=tk.Frame(p,bg=BG); bf.pack(fill="x",padx=10,pady=6)
        LimeBtn(bf,"Download Selected",self._dl_sel,width=20).pack(side="left",padx=(0,6))
        OrangeBtn(bf,"Retry Failed",self._retry_failed,width=14).pack(side="left")
        pg=GroupBox(p,"Progress"); pg.pack(fill="x",padx=10,pady=(0,10))
        self.pl_prog=ClassicProgress(pg); self.pl_prog.pack(fill="x",pady=(0,2))
        self.pl_lbl=tk.Label(pg,text="--",font=F_SMALL,bg=BG,fg=TEXT_DIM); self.pl_lbl.pack(anchor="w")
        self._failed_urls=[]
    def refresh(self): pass
    def _fetch(self):
        url=self.pl_var.get().strip()
        if not url: return
        self.pl_st.config(text="Fetching...",fg=YELLOW)
        threading.Thread(target=self._do_fetch,args=(url,),daemon=True).start()
    def _do_fetch(self,url):
        try:
            with yt_dlp.YoutubeDL(ydl_opts(quiet=True,no_warnings=True,extract_flat=True,skip_download=True)) as ydl:
                info=ydl.extract_info(url,download=False)
            entries=info.get("entries",[]) or [info]
            self._tracks=[]
            for e in entries:
                if not e: continue
                title=e.get("title") or e.get("fulltitle") or e.get("id") or "Untitled"
                url=e.get("url") or e.get("webpage_url") or ""
                dur=e.get("duration") or 0
                self._tracks.append({"title":str(title),"url":url,"dur":dur})
            self.after(0,self._render); self.after(0,lambda:self.pl_st.config(text=f"{len(self._tracks)} tracks",fg=LIME_DK))
        except Exception as e: self.after(0,lambda:self.pl_st.config(text=f"Error: {str(e)[:60]}",fg=RED))
    def _render(self):
        for w in self.ti.winfo_children(): w.destroy()
        self._cvars=[]
        for i,tr in enumerate(self._tracks):
            var=tk.BooleanVar(value=True); self._cvars.append(var)
            rbg=INPUT_BG if i%2==0 else CARD_BG
            row=tk.Frame(self.ti,bg=rbg); row.pack(fill="x",pady=0)
            tk.Checkbutton(row,variable=var,bg=rbg,selectcolor=INPUT_BG,activebackground=rbg,
                           command=self._upd).pack(side="left")
            tk.Label(row,text=f"{i+1:>3}. {tr['title'][:55]}",font=F_BODY,bg=rbg,fg=TEXT,anchor="w").pack(side="left",fill="x",expand=True)
            tk.Label(row,text=fmt_duration(tr["dur"]),font=F_SMALL,bg=rbg,fg=TEXT_DIM,width=8).pack(side="right")
        self._upd()
    def _sel_all(self):
        for v in self._cvars: v.set(True)
        self._upd()
    def _desel(self):
        for v in self._cvars: v.set(False)
        self._upd()
    def _upd(self): self.sel_cnt.config(text=f"{sum(1 for v in self._cvars if v.get())} selected")
    def _dl_sel(self):
        urls=[t["url"] for t,v in zip(self._tracks,self._cvars) if v.get() and t["url"]]
        self._download_urls(urls)
    def _retry_failed(self):
        if self._failed_urls: self._download_urls(list(self._failed_urls))
    def _download_urls(self,urls):
        if not urls: return
        out=self.pl_folder.get(); fmt=self.pl_fmt.get(); mode=self.pl_mode.get()
        total=len(urls); self.pl_prog["value"]=0
        self._failed_urls=[]
        extra=self.app.get_ydl_extra()
        def run():
            ok=0; fail=0
            for i,url in enumerate(urls,1):
                opts={"quiet":True,"no_warnings":True,"outtmpl":os.path.join(out,"%(title)s.%(ext)s"),**extra}
                if mode=="audio":
                    opts.update({"format":"bestaudio/best","postprocessors":[{"key":"FFmpegExtractAudio","preferredcodec":fmt}]})
                else:
                    opts.update({"format":"bestvideo+bestaudio/best","merge_output_format":fmt})
                try:
                    os.makedirs(out,exist_ok=True)
                    with yt_dlp.YoutubeDL({**YDL_BASE,**opts}) as ydl: ydl.download([url])
                    ok+=1
                except Exception:
                    fail+=1; self._failed_urls.append(url)
                self.after(0,lambda p=int((i/total)*100),d=i:(self.pl_prog.configure(value=p),self.pl_lbl.config(text=f"{d}/{total}")))
            msg=f"Done - {ok} OK"+(f", {fail} failed (click Retry)" if fail else "")
            col=LIME_DK if fail==0 else YELLOW
            self.after(0,lambda:self.pl_lbl.config(text=msg,fg=col))
        threading.Thread(target=run,daemon=True).start()

class ConverterPage(ScrollFrame):
    """Convert audio/video files between formats with optional loudness normalization."""
    def __init__(self,parent,app):
        super().__init__(parent); self.app=app; self._files=[]; self._build(self.inner)
    def _build(self,p):
        ig=GroupBox(p,"Input Files"); ig.pack(fill="x",padx=10,pady=(10,6))
        ir=tk.Frame(ig,bg=BG); ir.pack(fill="x",pady=(0,6))
        LimeBtn(ir,"+ Add Files",self._add).pack(side="left",padx=(0,4)); ClassicBtn(ir,"Clear",self._clr).pack(side="left")
        self.fcnt=tk.Label(ir,text="0 files",font=F_BODY,bg=BG,fg=TEXT_DIM); self.fcnt.pack(side="right")
        self.ff,self.fl=ClassicListbox(ig,height=5); self.ff.pack(fill="x")
        og=GroupBox(p,"Output"); og.pack(fill="x",padx=10,pady=(0,6))
        or_=tk.Frame(og,bg=BG); or_.pack(fill="x")
        for lbl,attr,vals,dflt,w in [("Format:","out_fmt",CONV_AUDIO+CONV_VIDEO,"mp3",10),("Bitrate:","bitrate",["320k","256k","192k","128k"],"320k",8)]:
            c=tk.Frame(or_,bg=BG); c.pack(side="left",padx=(0,16))
            tk.Label(c,text=lbl,font=F_BOLD,bg=BG,fg=TEXT).pack(anchor="w")
            var=tk.StringVar(value=dflt); setattr(self,attr,var); ClassicCombo(c,var,vals,w).pack(anchor="w")
        nc=tk.Frame(or_,bg=BG); nc.pack(side="left",padx=(0,16))
        tk.Label(nc,text="Normalize:",font=F_BOLD,bg=BG,fg=TEXT).pack(anchor="w")
        self.norm_var=tk.StringVar(value="off")
        ClassicCombo(nc,self.norm_var,["off","-14 LUFS","-16 LUFS","-23 LUFS"],width=10).pack(anchor="w")
        fc=tk.Frame(or_,bg=BG); fc.pack(side="left",fill="x",expand=True)
        tk.Label(fc,text="Folder:",font=F_BOLD,bg=BG,fg=TEXT).pack(anchor="w")
        self.out_f=tk.StringVar(value=self.app.output_dir)
        ClassicEntry(fc,self.out_f,width=30).pack(side="left",fill="x",expand=True,ipady=2)
        LimeBtn(p,"Convert All",self._conv,width=16).pack(padx=10,pady=6,anchor="w")
        pg=GroupBox(p,"Progress"); pg.pack(fill="x",padx=10,pady=(0,10))
        self.cb=ClassicProgress(pg); self.cb.pack(fill="x",pady=(0,2))
        self.cl=tk.Label(pg,text="--",font=F_SMALL,bg=BG,fg=TEXT_DIM); self.cl.pack(anchor="w")
    def _add(self):
        files=filedialog.askopenfilenames(filetypes=[("Media","*.mp3 *.wav *.flac *.ogg *.mp4 *.mkv *.m4a *.aac"),("All","*.*")])
        for f in files:
            if f not in self._files: self._files.append(f); self.fl.insert("end",os.path.basename(f))
        self.fcnt.config(text=f"{len(self._files)} files")
    def _clr(self): self._files=[]; self.fl.delete(0,"end"); self.fcnt.config(text="0 files")
    def _conv(self):
        if not self._files: return
        if not HAS_FFMPEG:
            messagebox.showerror("LimeWire","FFmpeg not found in PATH.\nInstall: winget install ffmpeg (Windows)\n         brew install ffmpeg (macOS)")
            return
        out=self.out_f.get(); fmt=self.out_fmt.get(); br=self.bitrate.get(); total=len(self._files)
        norm=self.norm_var.get()
        os.makedirs(out,exist_ok=True); self.cb["value"]=0
        def run():
            ok=0; fail=0
            for i,src in enumerate(self._files,1):
                name=os.path.splitext(os.path.basename(src))[0]; dst=os.path.join(out,f"{name}.{fmt}")
                self.after(0,lambda i=i,n=name:self.cl.config(text=f"[{i}/{total}] {n}..."))
                try:
                    cmd=["ffmpeg","-y","-i",src]
                    if norm!="off":
                        lufs_target=norm.split()[0]
                        cmd+=["-af",f"loudnorm=I={lufs_target}:TP=-1.5:LRA=11"]
                    if fmt in CONV_AUDIO: cmd+=["-ab",br]
                    cmd.append(dst); subprocess.run(cmd,capture_output=True,check=True,timeout=FFMPEG_TIMEOUT); ok+=1
                except Exception as e:
                    fail+=1
                    self.after(0,lambda n=name,e=e:self.cl.config(text=f"FAILED: {n} - {str(e)[:40]}",fg=RED))
                self.after(0,lambda p=int((i/total)*100):self.cb.configure(value=p))
            msg=f"Done - {ok} converted"+(f", {fail} failed" if fail else "")
            self.after(0,lambda:self.cl.config(text=msg,fg=LIME_DK if fail==0 else YELLOW))
        threading.Thread(target=run,daemon=True).start()

class PlayerPage(ScrollFrame):
    """Audio player with waveform visualization, A-B looping, and EQ spectrum."""
    def __init__(self,parent,app):
        super().__init__(parent); self.app=app
        self._playlist=[]; self._playlist_set=set()  # O(1) membership checks
        self._cur=-1; self._playing=False; self._dur=0
        self._seeking=False; self._wave_bars=[]; self._ab_a=None; self._ab_b=None
        self._lock=threading.Lock()  # protects _wave_bars from background thread
        self._build(self.inner)
    def _build(self,p):
        ng=GroupBox(p,"Now Playing"); ng.pack(fill="x",padx=10,pady=(10,6))
        nr=tk.Frame(ng,bg=BG); nr.pack(fill="x")
        self.art=tk.Label(nr,bg=BG,width=10,height=5,text="\u266A",font=F_TITLE,fg=TEXT_DIM,
                          relief="flat",bd=0,highlightthickness=1,highlightbackground=CARD_BORDER)
        self.art.pack(side="left",padx=(0,12))
        ni=tk.Frame(nr,bg=BG); ni.pack(side="left",fill="both",expand=True)
        self.np_t=tk.Label(ni,text="No track loaded",font=F_HEADER,bg=BG,fg=TEXT,anchor="w"); self.np_t.pack(fill="x")
        self.np_a=tk.Label(ni,text="",font=F_BODY,bg=BG,fg=TEXT_DIM,anchor="w"); self.np_a.pack(fill="x",pady=(2,0))
        # Waveform (click to seek)
        self.wave_cv=tk.Canvas(ng,bg=CANVAS_BG,height=50,relief="flat",bd=0,highlightthickness=1,highlightbackground=CARD_BORDER,cursor="hand2")
        self.wave_cv.pack(fill="x",pady=(6,0))
        self.wave_cv.bind("<Button-1>",self._wave_click)
        sr=tk.Frame(ng,bg=BG); sr.pack(fill="x",pady=(6,0))
        self.pos_l=tk.Label(sr,text="0:00",font=F_SMALL,bg=BG,fg=TEXT,width=6); self.pos_l.pack(side="left")
        self.seek_v=tk.DoubleVar(value=0)
        self.seek=ttk.Scale(sr,from_=0,to=100,orient="horizontal",variable=self.seek_v,command=self._oseek)
        self.seek.pack(side="left",fill="x",expand=True,padx=4)
        self.seek.bind("<ButtonPress-1>",self._slider_press)
        self.seek.bind("<ButtonRelease-1>",self._slider_release)
        self.dur_l=tk.Label(sr,text="0:00",font=F_SMALL,bg=BG,fg=TEXT,width=6); self.dur_l.pack(side="left")
        cr=tk.Frame(ng,bg=BG); cr.pack(pady=(6,4))
        ClassicBtn(cr,"|<",self._prev,width=4).pack(side="left",padx=2)
        self.play_b=LimeBtn(cr,"Play",self._toggle,width=8)
        self.play_b.pack(side="left",padx=4)
        ClassicBtn(cr,">|",self._next,width=4).pack(side="left",padx=2)
        # Quick analyze/stems buttons
        qa=tk.Frame(ng,bg=BG); qa.pack(pady=(4,0))
        OrangeBtn(qa,"Analyze",self._analyze_cur).pack(side="left",padx=(0,6))
        OrangeBtn(qa,"Split Stems",self._stems_cur).pack(side="left",padx=(0,6))
        # Speed + A-B loop
        spr=tk.Frame(ng,bg=BG); spr.pack(pady=(4,0))
        tk.Label(spr,text="Speed:",font=F_BOLD,bg=BG,fg=TEXT).pack(side="left",padx=(0,4))
        self.speed_var=tk.StringVar(value="1.0x")
        for spd in ["0.5x","0.75x","1.0x","1.25x","1.5x","2.0x"]:
            tk.Radiobutton(spr,text=spd,variable=self.speed_var,value=spd,font=F_SMALL,bg=BG,fg=TEXT,
                           selectcolor=LIME_DK,activebackground=BTN_HOVER,indicator=0,
                           padx=8,pady=3,relief="flat",bd=0,
                           highlightthickness=1,highlightbackground=CARD_BORDER,
                           command=self._apply_speed).pack(side="left",padx=1)
        tk.Label(spr,text="  ",bg=BG).pack(side="left")
        ClassicBtn(spr,"Set A",self._set_ab_a,width=5).pack(side="left",padx=(0,2))
        ClassicBtn(spr,"Set B",self._set_ab_b,width=5).pack(side="left",padx=(0,2))
        self.ab_lbl=tk.Label(spr,text="A-B: off",font=F_SMALL,bg=BG,fg=TEXT_DIM)
        self.ab_lbl.pack(side="left",padx=(4,0))
        ClassicBtn(spr,"Clear",self._clear_ab,width=5).pack(side="left",padx=(4,0))
        vr=tk.Frame(ng,bg=BG); vr.pack(pady=(4,0))
        tk.Label(vr,text="Vol:",font=F_BOLD,bg=BG,fg=TEXT).pack(side="left",padx=(0,6))
        self.vol=tk.DoubleVar(value=80)
        ttk.Scale(vr,from_=0,to=100,orient="horizontal",variable=self.vol,
                  command=lambda v:_audio.set_volume(float(v)/100)).pack(side="left")
        tk.Label(vr,text="  Crossfade:",font=F_BOLD,bg=BG,fg=TEXT).pack(side="left",padx=(SP_LG,SP_XS))
        self._crossfade_ms=tk.IntVar(value=0)
        tk.Spinbox(vr,from_=0,to=5000,increment=500,textvariable=self._crossfade_ms,width=5,
                   font=F_BODY,bg=INPUT_BG,fg=TEXT,relief="flat",bd=0,
                   highlightthickness=1,highlightbackground=INPUT_BORDER).pack(side="left")
        tk.Label(vr,text="ms",font=F_SMALL,bg=BG,fg=TEXT_DIM).pack(side="left",padx=SP_XS)
        # Up Next indicator
        self._upnext_lbl=tk.Label(ng,text="",font=F_SMALL,bg=BG,fg=TEXT_DIM,anchor="w")
        self._upnext_lbl.pack(fill="x",pady=(SP_XS,0))
        # EQ Spectrum Visualizer
        eqg=GroupBox(p,"EQ Spectrum"); eqg.pack(fill="x",padx=10,pady=(0,6))
        self.eq_cv=tk.Canvas(eqg,bg=CANVAS_BG,height=60,relief="flat",bd=0,highlightthickness=1,highlightbackground=CARD_BORDER)
        self.eq_cv.pack(fill="x")
        self._eq_bars=[]
        self._eq_peaks=[]
        self._init_eq_bars()

        plg=GroupBox(p,"Playlist"); plg.pack(fill="both",padx=10,pady=(0,10),expand=True)
        pr=tk.Frame(plg,bg=BG); pr.pack(fill="x",pady=(0,6))
        LimeBtn(pr,"+ Add",self._addf).pack(side="left",padx=(0,4))
        ClassicBtn(pr,"Add Downloads",self._adddl).pack(side="left",padx=(0,4))
        ClassicBtn(pr,"Save M3U",self._save_m3u).pack(side="left",padx=(0,4))
        ClassicBtn(pr,"Load M3U",self._load_m3u).pack(side="left",padx=(0,4))
        ClassicBtn(pr,"Clear",self._clr).pack(side="left")
        self.plf,self.plb=ClassicListbox(plg,height=7); self.plf.pack(fill="both",expand=True)
        self.plb.bind("<Double-Button-1>",self._psel)
        self._upd_pos()
    def _addf(self):
        files=filedialog.askopenfilenames(filetypes=[("Audio","*.mp3 *.wav *.flac *.ogg *.m4a"),("All","*.*")])
        for f in files:
            if f not in self._playlist_set:
                self._playlist.append(f); self._playlist_set.add(f)
                self.plb.insert("end",os.path.basename(f))
    def _adddl(self):
        f=self.app.output_dir
        if os.path.exists(f):
            for fn in sorted(os.listdir(f)):
                if fn.lower().endswith((".mp3",".wav",".flac",".ogg",".m4a")):
                    path=os.path.join(f,fn)
                    if path not in self._playlist_set:
                        self._playlist.append(path); self._playlist_set.add(path)
                        self.plb.insert("end",fn)
    def _clr(self):
        _audio.stop(); self._playlist=[]; self._playlist_set=set()
        self._cur=-1; self._playing=False
        self.plb.delete(0,"end"); self.np_t.config(text="No track loaded"); self.np_a.config(text=""); self.play_b.config(text="Play")
        self.wave_cv.delete("all")
    def _psel(self,e=None):
        sel=self.plb.curselection()
        if sel: self._load(sel[0])
    def _load(self,idx):
        if idx<0 or idx>=len(self._playlist): return
        self._cur=idx; path=self._playlist[idx]
        self.plb.selection_clear(0,"end"); self.plb.selection_set(idx); self.plb.see(idx)
        name=os.path.splitext(os.path.basename(path))[0]; self.np_t.config(text=name); self.np_a.config(text="")
        self.art.config(image="",text="♪",width=10,height=5)
        try:
            mf=mutagen.File(path)
            if mf and mf.info: self._dur=mf.info.length
            else: self._dur=0
            # Extract artist from any format
            artist=""
            if hasattr(mf,'tags') and mf.tags:
                for key in ["TPE1","artist","ARTIST","Author","©ART"]:
                    if key in mf.tags:
                        val=mf.tags[key]
                        artist=str(val[0]) if isinstance(val,list) else str(val)
                        break
            if artist: self.np_a.config(text=artist)
            self.dur_l.config(text=fmt_duration(self._dur)); self.seek.config(to=self._dur)
            # Album art — try ID3 APIC first, then FLAC/OGG pictures
            art_data=None
            if hasattr(mf,'tags') and mf.tags:
                if "APIC:" in mf.tags: art_data=mf.tags["APIC:"].data
                elif hasattr(mf,'pictures') and mf.pictures: art_data=mf.pictures[0].data
            if art_data:
                with Image.open(BytesIO(art_data)) as raw:
                    img=raw.convert("RGB"); img.thumbnail((80,80),Image.LANCZOS)
                ph=ImageTk.PhotoImage(img); self.art.config(image=ph,text="",width=80,height=80); self.art._img=ph
        except Exception: self._dur=0
        # Generate waveform in background
        threading.Thread(target=self._gen_wave,args=(path,),daemon=True).start()
        try: _audio.load(path); _audio.set_volume(self.vol.get()/100); _audio.play(); self._playing=True; self.play_b.config(text="Pause")
        except Exception as e: messagebox.showerror("LimeWire",str(e))
        # Up Next indicator
        nxt_idx=idx+1
        if nxt_idx<len(self._playlist):
            nxt_name=os.path.splitext(os.path.basename(self._playlist[nxt_idx]))[0]
            self._upnext_lbl.config(text=f"Up Next: {nxt_name}")
        else:
            self._upnext_lbl.config(text="")
    def _gen_wave(self,path):
        bars=generate_waveform_data(path,PLAYER_WAVEFORM_W,PLAYER_WAVEFORM_H-5)
        if bars:
            with self._lock:
                self._wave_bars=bars
            self.after(0,lambda:self._draw_wave(bars))
    def _draw_wave(self,bars,cursor_ratio=None):
        if not bars: return
        cv=self.wave_cv; cv.delete("all"); w=cv.winfo_width() or PLAYER_WAVEFORM_W; h=PLAYER_WAVEFORM_H
        bw=max(1,w/len(bars)); gap=max(1,bw*0.15)
        for i,amp in enumerate(bars):
            x=i*bw; bh=max(1,amp*h*0.85); y1=(h-bh)/2; y2=(h+bh)/2
            if amp<0.3: color=LIME
            elif amp<0.6: color=_lerp_color(LIME,YELLOW,(amp-0.3)/0.3)
            elif amp<0.85: color=_lerp_color(YELLOW,ORANGE,(amp-0.6)/0.25)
            else: color=RED
            cv.create_rectangle(x+gap/2,y1,x+bw-gap/2,y2,fill=color,outline="")
        # Create overlay items (cursor + markers) with tags for fast updates
        self._wave_cursor=cv.create_line(0,0,0,h,fill=TEXT,width=2,tags="cursor")
        self._wave_marker_a=cv.create_line(0,0,0,h,fill=ORANGE,width=2,dash=(4,2),tags="marker_a",state="hidden")
        self._wave_marker_b=cv.create_line(0,0,0,h,fill=ORANGE,width=2,dash=(4,2),tags="marker_b",state="hidden")
        if cursor_ratio is not None: self._update_wave_cursor(cursor_ratio)
    def _update_wave_cursor(self,cursor_ratio):
        """Update only the cursor and markers — no full redraw."""
        cv=self.wave_cv; w=cv.winfo_width() or 500; h=50
        if hasattr(self,"_wave_cursor"):
            cx=int(cursor_ratio*w)
            cv.coords(self._wave_cursor,cx,0,cx,h)
        if hasattr(self,"_wave_marker_a") and self._ab_a is not None and self._dur>0:
            ax=int((self._ab_a/self._dur)*w)
            cv.coords(self._wave_marker_a,ax,0,ax,h); cv.itemconfig(self._wave_marker_a,state="normal")
        if hasattr(self,"_wave_marker_b") and self._ab_b is not None and self._dur>0:
            bx=int((self._ab_b/self._dur)*w)
            cv.coords(self._wave_marker_b,bx,0,bx,h); cv.itemconfig(self._wave_marker_b,state="normal")
    def _wave_click(self,e):
        if self._dur>0 and self._wave_bars:
            w=self.wave_cv.winfo_width() or 500
            ratio=max(0,min(1,e.x/w))
            pos=ratio*self._dur
            _audio.play(start=pos)
            self._playing=True; self.play_b.config(text="Pause")
    def _toggle(self):
        if not self._playlist: self._addf(); return
        if self._cur<0:
            if self._playlist: self._load(0)
            return
        if self._playing: _audio.pause(); self._playing=False; self.play_b.config(text="Play")
        else: _audio.play(); self._playing=True; self.play_b.config(text="Pause")
    def _prev(self):
        if self._cur>0: self._load(self._cur-1)
    def _next(self):
        if self._cur<len(self._playlist)-1: self._load(self._cur+1)
    def _oseek(self,val):
        if self._seeking and self._playing: _audio.play(start=float(val))
    def _slider_press(self,e): self._seeking=True
    def _slider_release(self,e): self._seeking=False
    def _upd_pos(self):
        try:
            if self._playing and _audio.get_busy():
                pos=_audio.get_pos(); self.pos_l.config(text=fmt_duration(pos))
                if self._dur>0 and not self._seeking: self.seek_v.set(pos)
                # Update cursor position (fast, no full redraw)
                if self._wave_bars and self._dur>0:
                    self._update_wave_cursor(pos/self._dur)
                self._update_eq()
                # A-B loop: jump back to A if past B
                if self._ab_a is not None and self._ab_b is not None and pos>=self._ab_b:
                    _audio.play(start=self._ab_a)
                elif self._dur>0 and pos>=self._dur-1: self._next()
            elif self._playing and not _audio.get_busy(): self._next()
        except Exception: pass
        self.after(PLAYER_UPDATE_MS,self._upd_pos)
    def _analyze_cur(self):
        if self._cur>=0 and self._cur<len(self._playlist):
            ap=self.app.pages.get("analyze")
            if ap: ap.file_var.set(self._playlist[self._cur]); self.app._show_tab("analyze")
    def _stems_cur(self):
        if self._cur>=0 and self._cur<len(self._playlist):
            sp=self.app.pages.get("stems")
            if sp: sp.file_var.set(self._playlist[self._cur]); self.app._show_tab("stems")
    def _apply_speed(self):
        # Note: pyglet Player does not support playback speed changes.
        # This is a placeholder for future backend support.
        pass
    def _set_ab_a(self):
        if self._playing and _audio.get_busy():
            self._ab_a=_audio.get_pos()
            self._update_ab_label()
    def _set_ab_b(self):
        if self._playing and _audio.get_busy():
            self._ab_b=_audio.get_pos()
            self._update_ab_label()
    def _clear_ab(self):
        self._ab_a=None; self._ab_b=None
        self.ab_lbl.config(text="A-B: off",fg=TEXT_DIM)
    def _init_eq_bars(self):
        """Defer EQ bar creation to first <Configure> when canvas has real width."""
        self._eq_initialized=False; self._eq_peak_vals=[0.0]*EQ_BAR_COUNT
        self.eq_cv.bind("<Configure>",self._on_eq_configure,add="+")
    def _on_eq_configure(self,event=None):
        if self._eq_initialized: return
        self._eq_initialized=True
        w=self.eq_cv.winfo_width() or 400; h=60; n=EQ_BAR_COUNT; bw=max(2,w/n)
        gap=max(1,bw*0.2)
        self._eq_bars=[]; self._eq_peaks=[]
        colors=[LIME]*10+[LIME_LT]*8+[YELLOW]*8+[RED]*6
        for i in range(n):
            x=i*bw
            bar=self.eq_cv.create_rectangle(x+gap/2,h,x+bw-gap/2,h,fill=colors[min(i,len(colors)-1)],outline="")
            peak=self.eq_cv.create_line(x+gap/2,h,x+bw-gap/2,h,fill=CANVAS_BG,width=1)
            self._eq_bars.append(bar); self._eq_peaks.append(peak)
    def _update_eq(self):
        """Update EQ bars with random-seeded decay animation when playing."""
        if not self._playing or not self._eq_bars: return
        import random
        cv=self.eq_cv; h=60; n=len(self._eq_bars); w=cv.winfo_width() or 400; bw=max(2,w/n)
        gap=max(1,bw*0.2)
        for i in range(n):
            if i<6: amp=random.uniform(0.4,1.0)
            elif i<16: amp=random.uniform(0.2,0.85)
            else: amp=random.uniform(0.05,0.6)
            bh=max(1,int(amp*h*0.9)); x=i*bw; y1=h-bh
            cv.coords(self._eq_bars[i],x+gap/2,y1,x+bw-gap/2,h)
            if amp>self._eq_peak_vals[i]: self._eq_peak_vals[i]=amp
            else: self._eq_peak_vals[i]=max(0,self._eq_peak_vals[i]-EQ_PEAK_DECAY)
            py=h-int(self._eq_peak_vals[i]*h*0.9)
            cv.coords(self._eq_peaks[i],x+gap/2,py,x+bw-gap/2,py)
            cv.itemconfig(self._eq_peaks[i],fill=TEXT)
    def _update_ab_label(self):
        a=fmt_duration(self._ab_a) if self._ab_a is not None else "?"
        b=fmt_duration(self._ab_b) if self._ab_b is not None else "?"
        self.ab_lbl.config(text=f"A-B: {a} → {b}",fg=ORANGE)
    def _save_m3u(self):
        if not self._playlist: return
        path=filedialog.asksaveasfilename(defaultextension=".m3u",filetypes=[("M3U Playlist","*.m3u")])
        if path:
            with open(path,"w",encoding="utf-8") as f:
                f.write("#EXTM3U\n")
                for p_ in self._playlist: f.write(p_+"\n")
            self.app.toast(f"Saved {len(self._playlist)} tracks to M3U")
    def _load_m3u(self):
        path=filedialog.askopenfilename(filetypes=[("M3U Playlist","*.m3u"),("All","*.*")])
        if not path: return
        with open(path,"r",encoding="utf-8") as f:
            for line in f:
                line=line.strip()
                if line and not line.startswith("#") and os.path.exists(line):
                    if line not in self._playlist_set:
                        self._playlist.append(line); self._playlist_set.add(line)
                        self.plb.insert("end",os.path.basename(line))
        self.app.toast(f"Loaded playlist: {len(self._playlist)} tracks")

class SchedulerPage(ScrollFrame):
    """Schedule downloads for future execution."""
    def __init__(self,parent,app):
        super().__init__(parent); self.app=app; self._build(self.inner)
    def _build(self,p):
        g=GroupBox(p,"Schedule a Download"); g.pack(fill="x",padx=10,pady=(10,6))
        tk.Label(g,text="URL:",font=F_BOLD,bg=BG,fg=TEXT).pack(anchor="w")
        self.sc_url=tk.StringVar(); ClassicEntry(g,self.sc_url,width=60).pack(fill="x",ipady=2,pady=(0,6))
        r=tk.Frame(g,bg=BG); r.pack(fill="x")
        dc=tk.Frame(r,bg=BG); dc.pack(side="left",padx=(0,16))
        tk.Label(dc,text="Date/Time:",font=F_BOLD,bg=BG,fg=TEXT).pack(anchor="w")
        self.sc_dt=tk.StringVar(value=(datetime.datetime.now()+datetime.timedelta(hours=1)).strftime("%Y-%m-%d %H:%M"))
        ClassicEntry(dc,self.sc_dt,width=20).pack(anchor="w",ipady=2)
        fc=tk.Frame(r,bg=BG); fc.pack(side="left",padx=(0,16))
        tk.Label(fc,text="Format:",font=F_BOLD,bg=BG,fg=TEXT).pack(anchor="w")
        self.sc_fmt=tk.StringVar(value="mp3"); ClassicCombo(fc,self.sc_fmt,AUDIO_FMTS,8).pack(anchor="w")
        flc=tk.Frame(r,bg=BG); flc.pack(side="left",fill="x",expand=True)
        tk.Label(flc,text="Save To:",font=F_BOLD,bg=BG,fg=TEXT).pack(anchor="w")
        self.sc_f=tk.StringVar(value=self.app.output_dir)
        ClassicEntry(flc,self.sc_f,width=25).pack(side="left",fill="x",expand=True,ipady=2)
        LimeBtn(g,"+ Schedule",self._add_job).pack(pady=(8,0),anchor="w")
        jg=GroupBox(p,"Jobs"); jg.pack(fill="both",padx=10,pady=(0,10),expand=True)
        self.jf=tk.Frame(jg,bg=BG); self.jf.pack(fill="both",expand=True)
    def refresh(self):
        for w in self.jf.winfo_children(): w.destroy()
        for job in self.app.schedule:
            row=tk.Frame(self.jf,bg=CARD_BG,relief="flat",bd=0,padx=10,pady=8,
                        highlightthickness=1,highlightbackground=CARD_BORDER); row.pack(fill="x",pady=2)
            st=job.get("status","pending")
            ico={"pending":"⏱","running":"⟳","done":"✓","error":"✗"}.get(st,"?")
            col={"pending":YELLOW,"running":LIME_DK,"done":LIME_DK,"error":RED}.get(st,TEXT)
            tk.Label(row,text=ico,font=F_BODY,bg=CARD_BG,fg=col).pack(side="left",padx=(0,8))
            tk.Label(row,text=job.get("url","")[:50],font=F_BODY,bg=CARD_BG,fg=TEXT_BLUE,anchor="w").pack(side="left",fill="x",expand=True)
            tk.Label(row,text=f"{job.get('when','')} | {job.get('format','').upper()}",font=F_SMALL,bg=CARD_BG,fg=TEXT_DIM).pack(side="left",padx=(8,0))
            tk.Button(row,text="X",font=F_BTN,bg=CARD_BG,fg=RED,relief="flat",bd=0,cursor="hand2",
                      command=lambda j=job:self._del(j)).pack(side="right")
    def _add_job(self):
        url=self.sc_url.get().strip()
        if not url or "http" not in url: return
        try: datetime.datetime.strptime(self.sc_dt.get(),"%Y-%m-%d %H:%M")
        except Exception: messagebox.showwarning("LimeWire","Format: YYYY-MM-DD HH:MM"); return
        with self.app._sched_lock:
            self.app.schedule.append({"url":url,"when":self.sc_dt.get(),"format":self.sc_fmt.get(),"folder":self.sc_f.get(),"status":"pending"})
            save_json(SCHEDULE_FILE,self.app.schedule)
        self.refresh()
    def _del(self,job):
        with self.app._sched_lock:
            self.app.schedule.remove(job); save_json(SCHEDULE_FILE,self.app.schedule)
        self.refresh()

class HistoryPage(ScrollFrame):
    """Browse and manage download history with filtering."""
    def __init__(self,parent,app):
        super().__init__(parent); self.app=app; self._build(self.inner)
    def _build(self,p):
        hdr=tk.Frame(p,bg=BG,padx=10,pady=8); hdr.pack(fill="x")
        tk.Label(hdr,text="Download History",font=F_TITLE,bg=BG,fg=TEXT).pack(side="left")
        ClassicBtn(hdr,"Open File",self._open_file).pack(side="right",padx=(4,0))
        ClassicBtn(hdr,"Redownload",self._redown_sel).pack(side="right",padx=(4,0))
        ClassicBtn(hdr,"Clear",self._clear).pack(side="right")
        # Search/filter bar
        sf=tk.Frame(p,bg=BG,padx=10); sf.pack(fill="x",pady=(4,0))
        tk.Label(sf,text="Filter:",font=F_BOLD,bg=BG,fg=TEXT).pack(side="left",padx=(0,6))
        self.filter_var=tk.StringVar()
        self.filter_e=ClassicEntry(sf,self.filter_var,width=30)
        self.filter_e.pack(side="left",fill="x",expand=True,ipady=2,padx=(0,6))
        self.filter_var.trace_add("write",lambda *_:self.refresh())
        self.filter_count=tk.Label(sf,text="",font=F_SMALL,bg=BG,fg=TEXT_DIM)
        self.filter_count.pack(side="left")
        HSep(p)
        self.hf,self.hlb=ClassicListbox(p,height=20,selectmode="browse")
        self.hf.pack(fill="both",expand=True,padx=10,pady=(6,10))
        self.hlb.bind("<Double-Button-1>",lambda e:self._redown_sel())
    def refresh(self):
        self.hlb.delete(0,"end")
        self._filtered_indices=[]  # maps listbox index → history index
        query=self.filter_var.get().strip().lower() if hasattr(self,"filter_var") else ""
        for i,entry in enumerate(self.app.history[:300]):
            st=entry.get("status",""); ico="OK" if st=="done" else "XX"
            title=entry.get("title","")[:35]; src=entry.get("source","")
            fmt_s=entry.get("format","").upper(); date=entry.get("date","")
            fp=entry.get("filepath","")
            line=f" {ico:3s} {title:35s} {src:10s} {fmt_s:5s} {date:16s}"
            if fp: line+=f" [{os.path.basename(fp)[:20]}]"
            if query and query not in line.lower(): continue
            self.hlb.insert("end",line); self._filtered_indices.append(i)
        shown=len(self._filtered_indices)
        if hasattr(self,"filter_count"):
            self.filter_count.config(text=f"{shown}/{len(self.app.history)}" if query else f"{shown} total")
    def _get_selected_entry(self):
        sel=self.hlb.curselection()
        if sel and sel[0]<len(self._filtered_indices):
            idx=self._filtered_indices[sel[0]]
            if idx<len(self.app.history): return self.app.history[idx]
        return None
    def _clear(self):
        if messagebox.askyesno("LimeWire","Clear all?"): self.app.history=[]; save_json(HISTORY_FILE,[]); self.refresh()
    def _redown_sel(self):
        entry=self._get_selected_entry()
        if entry:
            url=entry.get("url","")
            if url: sp=self.app.pages["search"]; sp.url_var.set(url); self.app._show_tab("search")
    def _open_file(self):
        entry=self._get_selected_entry()
        if not entry: return
        fp=entry.get("filepath","")
        if fp and os.path.exists(fp):
            open_folder(os.path.dirname(fp))
        elif entry.get("folder"):
            open_folder(entry["folder"])


# ═══════════════════════════════════════════════════════════════════════════════
# EFFECTS PAGE — Pedalboard effects chain
# ═══════════════════════════════════════════════════════════════════════════════

class EffectsPage(ScrollFrame):
    """Pedalboard effects chain processor for audio files."""
    def __init__(self,parent,app):
        super().__init__(parent); self.app=app; self._chain=[]; self._build(self.inner)
    def _build(self,p):
        fg=GroupBox(p,"Source Audio File"); fg.pack(fill="x",padx=10,pady=(10,6))
        fr=tk.Frame(fg,bg=BG); fr.pack(fill="x")
        self.file_var=tk.StringVar()
        ClassicEntry(fr,self.file_var,width=55).pack(side="left",fill="x",expand=True,ipady=2,padx=(0,8))
        ClassicBtn(fr,"Browse...",self._browse).pack(side="left")

        eg=GroupBox(p,"Effects Chain"); eg.pack(fill="x",padx=10,pady=(0,6))
        if not HAS_PEDALBOARD:
            tk.Label(eg,text="pedalboard not installed. Run: pip install pedalboard",
                     font=F_BODY,bg=BG,fg=RED).pack(fill="x",padx=6,pady=6)
            return
        # Effect selector
        ar=tk.Frame(eg,bg=BG); ar.pack(fill="x",pady=(0,6))
        tk.Label(ar,text="Add Effect:",font=F_BOLD,bg=BG,fg=TEXT).pack(side="left",padx=(0,6))
        self._fx_names=["Compressor","Reverb","Delay","Distortion","Gain","NoiseGate",
                        "HighpassFilter","LowpassFilter","HighShelfFilter","LowShelfFilter","Chorus","Phaser"]
        self._fx_var=tk.StringVar(value="Compressor")
        ClassicCombo(ar,self._fx_var,self._fx_names,width=16).pack(side="left",padx=(0,6))
        LimeBtn(ar,"Add",self._add_fx).pack(side="left",padx=(0,6))
        OrangeBtn(ar,"Clear All",self._clear_fx).pack(side="left",padx=(0,6))
        ClassicBtn(ar,"Save Preset",self._save_preset).pack(side="left",padx=(0,6))
        ClassicBtn(ar,"Load Preset",self._load_preset).pack(side="left",padx=(0,6))

        # Chain display
        self.chain_frame=tk.Frame(eg,bg=BG); self.chain_frame.pack(fill="x")
        self._render_chain()

        # Parameters
        pg=GroupBox(p,"Effect Parameters"); pg.pack(fill="x",padx=10,pady=(0,6))
        self.param_frame=tk.Frame(pg,bg=BG); self.param_frame.pack(fill="x")
        self._param_vars={}

        # Actions
        ag=GroupBox(p,"Process"); ag.pack(fill="x",padx=10,pady=(0,6))
        abr=tk.Frame(ag,bg=BG); abr.pack(fill="x")
        LimeBtn(abr,"Apply Effects",self._apply,width=18).pack(side="left",padx=(0,8))
        ClassicBtn(abr,"Preview (5s)",self._preview).pack(side="left",padx=(0,8))
        self.fx_status=tk.Label(ag,text="Add effects above, then click Apply",
                                font=F_SMALL,bg=BG,fg=TEXT_DIM,anchor="w")
        self.fx_status.pack(fill="x",pady=(4,0))
        self.fx_prog=ClassicProgress(ag); self.fx_prog.pack(fill="x",pady=(4,0))

    def _browse(self):
        f=filedialog.askopenfilename(filetypes=[("Audio","*.mp3 *.wav *.flac *.ogg *.m4a"),("All","*.*")])
        if f: self.file_var.set(f)

    def _add_fx(self):
        name=self._fx_var.get()
        self._chain.append({"name":name,"params":self._default_params(name)})
        self._render_chain()

    def _default_params(self,name):
        defaults={
            "Compressor":{"threshold_db":-20,"ratio":4,"attack_ms":5,"release_ms":100},
            "Reverb":{"room_size":0.5,"wet_level":0.3},
            "Delay":{"delay_seconds":0.3,"feedback":0.4,"mix":0.3},
            "Distortion":{"drive_db":15},
            "Gain":{"gain_db":0},
            "NoiseGate":{"threshold_db":-40},
            "HighpassFilter":{"cutoff_frequency_hz":100},
            "LowpassFilter":{"cutoff_frequency_hz":8000},
            "HighShelfFilter":{"cutoff_frequency_hz":4000,"gain_db":3},
            "LowShelfFilter":{"cutoff_frequency_hz":300,"gain_db":3},
            "Chorus":{"rate_hz":1.5,"depth":0.5,"mix":0.5},
            "Phaser":{"rate_hz":1.0,"depth":0.5,"mix":0.5},
        }
        return defaults.get(name,{})

    def _render_chain(self):
        for w in self.chain_frame.winfo_children(): w.destroy()
        if not self._chain:
            tk.Label(self.chain_frame,text="No effects in chain. Add effects above.",
                     font=F_SMALL,bg=BG,fg=TEXT_DIM).pack(pady=4)
            return
        for i,fx in enumerate(self._chain):
            r=tk.Frame(self.chain_frame,bg=CARD_BG,relief="flat",bd=0,
                       highlightthickness=1,highlightbackground=CARD_BORDER)
            r.pack(fill="x",pady=2,padx=4)
            tk.Label(r,text=f"  {i+1}. {fx['name']}",font=F_BOLD,bg=CARD_BG,fg=LIME).pack(side="left",padx=4)
            # Show key params inline
            params_str=" | ".join(f"{k}={v}" for k,v in fx["params"].items())
            tk.Label(r,text=params_str,font=F_SMALL,bg=CARD_BG,fg=TEXT_DIM).pack(side="left",padx=8)
            ClassicBtn(r,"Edit",lambda i=i:self._edit_fx(i)).pack(side="right",padx=2)
            ClassicBtn(r,"X",lambda i=i:self._remove_fx(i)).pack(side="right",padx=2)

    def _remove_fx(self,idx):
        if idx<len(self._chain): self._chain.pop(idx); self._render_chain()

    def _edit_fx(self,idx):
        if idx>=len(self._chain): return
        fx=self._chain[idx]
        # Show edit dialog
        dlg=tk.Toplevel(self); dlg.title(f"Edit {fx['name']}"); dlg.geometry("350x300")
        dlg.configure(bg=BG); dlg.transient(self); dlg.grab_set()
        tk.Label(dlg,text=fx["name"],font=F_HEADER,bg=BG,fg=TEXT).pack(pady=(10,6))
        vars_={}
        for k,v in fx["params"].items():
            r=tk.Frame(dlg,bg=BG); r.pack(fill="x",padx=20,pady=3)
            tk.Label(r,text=f"{k}:",font=F_BODY,bg=BG,fg=TEXT,width=20,anchor="w").pack(side="left")
            sv=tk.StringVar(value=str(v)); vars_[k]=sv
            ClassicEntry(r,sv,width=10).pack(side="left",ipady=1)
        def _save():
            for k,sv in vars_.items():
                try: fx["params"][k]=float(sv.get())
                except Exception: pass
            self._render_chain(); dlg.destroy()
        LimeBtn(dlg,"Save",_save).pack(pady=10)

    def _clear_fx(self):
        self._chain=[]; self._render_chain()

    def _save_preset(self):
        if not self._chain:
            show_toast(self.app,"No effects to save","warning"); return
        f=filedialog.asksaveasfilename(defaultextension=".json",
            filetypes=[("Effect Preset","*.json")],initialfile="my_preset.json")
        if not f: return
        try:
            save_json(f,{"version":1,"chain":self._chain})
            show_toast(self.app,f"Preset saved: {os.path.basename(f)}","success")
        except Exception as e:
            show_toast(self.app,f"Save failed: {e}","error")

    def _load_preset(self):
        f=filedialog.askopenfilename(filetypes=[("Effect Preset","*.json"),("All","*.*")])
        if not f: return
        try:
            data=load_json(f)
            chain=data.get("chain",[]) if isinstance(data,dict) else data
            if not isinstance(chain,list): show_toast(self.app,"Invalid preset file","error"); return
            self._chain=chain; self._render_chain()
            show_toast(self.app,f"Loaded {len(chain)} effects from preset","success")
        except Exception as e:
            show_toast(self.app,f"Load failed: {e}","error")

    def _build_board(self):
        """Build pedalboard.Pedalboard from current chain."""
        effects=[]
        for fx in self._chain:
            cls=getattr(pedalboard,fx["name"],None)
            if cls:
                # Map param names
                params={}
                for k,v in fx["params"].items():
                    # Convert _ms to _seconds for pedalboard API
                    if k.endswith("_ms"):
                        params[k.replace("_ms","_seconds")]=v/1000.0
                    else:
                        params[k]=v
                try: effects.append(cls(**params))
                except Exception as e:
                    self.fx_status.config(text=f"Error creating {fx['name']}: {e}",fg=RED); return None
        return pedalboard.Pedalboard(effects)

    def _apply(self):
        path=self.file_var.get()
        if not path or not os.path.exists(path):
            messagebox.showinfo("LimeWire","Select an audio file first."); return
        if not self._chain:
            messagebox.showinfo("LimeWire","Add effects to the chain first."); return
        board=self._build_board()
        if not board: return
        self.fx_status.config(text="Processing...",fg=YELLOW)
        self.fx_prog.configure(value=0)
        def _do():
            try:
                base,ext=os.path.splitext(path)
                out=f"{base}_fx{ext}"
                with pedalboard.io.AudioFile(path) as f:
                    audio=f.read(f.frames); sr=f.samplerate
                self.after(0,lambda:self.fx_prog.configure(value=50))
                processed=board(audio,sample_rate=sr)
                with pedalboard.io.AudioFile(out,"w",sr,processed.shape[0]) as f:
                    f.write(processed)
                self.after(0,lambda:(self.fx_prog.configure(value=100),
                    self.fx_status.config(text=f"Saved: {os.path.basename(out)}",fg=LIME_DK),
                    self.app.toast(f"Effects applied: {os.path.basename(out)}")))
            except Exception as e:
                self.after(0,lambda:self.fx_status.config(text=f"Error: {str(e)[:80]}",fg=RED))
        threading.Thread(target=_do,daemon=True).start()

    def _preview(self):
        path=self.file_var.get()
        if not path or not os.path.exists(path) or not self._chain: return
        board=self._build_board()
        if not board: return
        self.fx_status.config(text="Generating preview...",fg=YELLOW)
        def _do():
            try:
                with pedalboard.io.AudioFile(path) as f:
                    sr=f.samplerate; chunk=f.read(min(sr*5,f.frames))
                processed=board(chunk,sample_rate=sr)
                preview_path=os.path.join(os.environ.get("TEMP","."),"_lw_fx_preview.wav")
                with pedalboard.io.AudioFile(preview_path,"w",sr,processed.shape[0]) as f:
                    f.write(processed)
                _audio.load(preview_path); _audio.play()
                self.after(0,lambda:self.fx_status.config(text="Playing 5s preview...",fg=LIME_DK))
            except Exception as e:
                self.after(0,lambda:self.fx_status.config(text=f"Preview error: {str(e)[:80]}",fg=RED))
        threading.Thread(target=_do,daemon=True).start()


# ═══════════════════════════════════════════════════════════════════════════════
# DISCOVERY PAGE — Music discovery, genre detection, playlist generation
# ═══════════════════════════════════════════════════════════════════════════════

class DiscoveryPage(ScrollFrame):
    """Music library scanner with BPM/key caching and harmonic mixing."""
    def __init__(self,parent,app):
        super().__init__(parent); self.app=app; self._library={}; self._build(self.inner)
    def _build(self,p):
        # Library Scanner
        sg=GroupBox(p,"Music Library Scanner"); sg.pack(fill="x",padx=10,pady=(10,6))
        sr=tk.Frame(sg,bg=BG); sr.pack(fill="x")
        tk.Label(sr,text="Folder:",font=F_BOLD,bg=BG,fg=TEXT).pack(side="left",padx=(0,6))
        self.lib_var=tk.StringVar(value=os.path.join(os.path.expanduser("~"),"Downloads","LimeWire"))
        ClassicEntry(sr,self.lib_var,width=45).pack(side="left",fill="x",expand=True,ipady=2,padx=(0,6))
        ClassicBtn(sr,"Browse...",self._browse_lib).pack(side="left",padx=(0,6))
        LimeBtn(sr,"Scan Library",self._scan_library).pack(side="left")
        self.scan_status=tk.Label(sg,text="Scan a music folder to analyze BPM, key, and build a library index",
                                  font=F_SMALL,bg=BG,fg=TEXT_DIM,anchor="w")
        self.scan_status.pack(fill="x",pady=(4,0))
        self.scan_prog=ClassicProgress(sg); self.scan_prog.pack(fill="x",pady=(2,0))

        # Library View
        lg=GroupBox(p,"Library Analysis"); lg.pack(fill="both",padx=10,pady=(0,6),expand=True)
        cols_frame=tk.Frame(lg,bg=CARD_BG,bd=0); cols_frame.pack(fill="x")
        tk.Frame(lg,bg=CARD_BORDER,height=1).pack(fill="x")
        for col,w in [("File",35),("BPM",8),("Key",12),("Camelot",8)]:
            tk.Label(cols_frame,text=col,font=F_BOLD,bg=CARD_BG,fg=TEXT,width=w,anchor="w").pack(side="left")
        self.lib_frame,self.lib_lb=ClassicListbox(lg,height=10)
        self.lib_frame.pack(fill="both",expand=True)

        # Harmonic Mixing
        mg=GroupBox(p,"Harmonic Mixing"); mg.pack(fill="x",padx=10,pady=(0,6))
        mr=tk.Frame(mg,bg=BG); mr.pack(fill="x")
        OrangeBtn(mr,"Find Compatible Tracks",self._find_harmonic).pack(side="left",padx=(0,6))
        ClassicBtn(mr,"Generate DJ Playlist",self._gen_playlist).pack(side="left",padx=(0,6))
        ClassicBtn(mr,"Export Playlist (.m3u)",self._export_m3u).pack(side="left")
        self.mix_status=tk.Label(mg,text="Select a track in the library, then find harmonically compatible tracks",
                                 font=F_SMALL,bg=BG,fg=TEXT_DIM,anchor="w")
        self.mix_status.pack(fill="x",pady=(4,0))

        # Harmonic results
        self.harm_frame,self.harm_lb=ClassicListbox(mg,height=6)
        self.harm_frame.pack(fill="x",pady=(4,0))

        # Smart Playlist Options
        spg=GroupBox(p,"Smart Playlist"); spg.pack(fill="x",padx=10,pady=(0,6))
        spf=tk.Frame(spg,bg=BG); spf.pack(fill="x")
        tk.Label(spf,text="Energy:",font=F_BODY,bg=BG,fg=TEXT).pack(side="left")
        self._energy_filter=tk.StringVar(value="All")
        ClassicCombo(spf,self._energy_filter,["All","Low (<100 BPM)","Medium (100-130)","High (130-160)","Very High (160+)"],width=18).pack(side="left",padx=SP_SM)
        tk.Label(spf,text="Sort:",font=F_BODY,bg=BG,fg=TEXT).pack(side="left",padx=(SP_LG,0))
        self._sort_mode=tk.StringVar(value="Harmonic Flow")
        ClassicCombo(spf,self._sort_mode,["Harmonic Flow","BPM Ramp Up","BPM Ramp Down","Key Groups"],width=16).pack(side="left",padx=SP_SM)
        LimeBtn(spf,"Smart Generate",self._smart_playlist).pack(side="left",padx=SP_SM)

        # Playlist
        pg=GroupBox(p,"Generated Playlist"); pg.pack(fill="x",padx=10,pady=(0,10))
        self.pl_frame,self.pl_lb=ClassicListbox(pg,height=6)
        self.pl_frame.pack(fill="x")

    def _browse_lib(self):
        d=filedialog.askdirectory(initialdir=self.lib_var.get())
        if d: self.lib_var.set(d)

    def _scan_library(self):
        folder=self.lib_var.get()
        if not os.path.isdir(folder): messagebox.showinfo("LimeWire","Select a valid folder."); return
        self.scan_status.config(text="Scanning...",fg=YELLOW)
        self.scan_prog.configure(value=0)
        threading.Thread(target=self._do_scan,args=(folder,),daemon=True).start()

    def _do_scan(self,folder):
        audio_exts={".mp3",".wav",".flac",".ogg",".m4a",".aac",".opus"}
        files=[os.path.join(folder,f) for f in os.listdir(folder)
               if os.path.splitext(f)[1].lower() in audio_exts]
        if not files:
            self.after(0,lambda:self.scan_status.config(text="No audio files found.",fg=RED)); return
        # Load analysis cache (keyed by filepath|mtime for invalidation)
        cache=load_json(ANALYSIS_CACHE_FILE,{})
        self._library={}; analyzed=0
        for i,fp in enumerate(files):
            pct=int((i/max(1,len(files)))*100)
            self.after(0,lambda p=pct:self.scan_prog.configure(value=p))
            try: mtime=str(os.path.getmtime(fp))
            except OSError: mtime=""
            cache_key=f"{fp}|{mtime}"
            if cache_key in cache:
                entry=cache[cache_key]
            else:
                bk=analyze_bpm_key(fp)
                bpm=bk.get("bpm"); key=bk.get("key","")
                camelot=key_to_camelot(key) or ""
                entry={"bpm":bpm,"key":key,"camelot":camelot,"file":os.path.basename(fp)}
                cache[cache_key]=entry; analyzed+=1
            self._library[fp]=entry
        save_json(ANALYSIS_CACHE_FILE,cache)
        cached=len(files)-analyzed
        msg=f"Scanned {len(self._library)} tracks ({analyzed} analyzed, {cached} cached)"
        self.after(0,lambda:(self.scan_prog.configure(value=100),
            self.scan_status.config(text=msg,fg=LIME_DK),
            self._render_library()))

    def _render_library(self):
        self.lib_lb.delete(0,"end")
        for fp,info in sorted(self._library.items(),key=lambda x:x[1].get("bpm") or 0):
            bpm=f"{info['bpm']:.1f}" if info["bpm"] else "?"
            line=f" {info['file'][:35]:35s} {bpm:>8s} {info['key']:12s} {info['camelot']:8s}"
            self.lib_lb.insert("end",line)

    def _get_selected_file(self):
        sel=self.lib_lb.curselection()
        if sel:
            files=sorted(self._library.keys(),key=lambda x:self._library[x].get("bpm") or 0)
            if sel[0]<len(files): return files[sel[0]]
        return None

    def _find_harmonic(self):
        fp=self._get_selected_file()
        if not fp:
            messagebox.showinfo("LimeWire","Select a track from the library first."); return
        info=self._library[fp]
        key=info.get("key","")
        if not key:
            self.mix_status.config(text="Selected track has no key detected.",fg=RED); return
        lib_keys={f:d["key"] for f,d in self._library.items() if d.get("key") and f!=fp}
        matches=get_harmonic_matches(key,lib_keys)
        self.harm_lb.delete(0,"end")
        for f,k,c,lvl in matches:
            bpm=self._library[f].get("bpm")
            bpm_s=f"{bpm:.1f}" if bpm else "?"
            tag="★" if lvl=="perfect" else "♪"
            self.harm_lb.insert("end",f" {tag} {os.path.basename(f)[:30]:30s} {bpm_s:>8s} {k:12s} {c:6s}")
        self.mix_status.config(text=f"Found {len(matches)} compatible tracks for {info['camelot']} ({key})",fg=LIME_DK)

    def _gen_playlist(self):
        if not self._library:
            messagebox.showinfo("LimeWire","Scan a library first."); return
        fp=self._get_selected_file()
        if not fp:
            # Use first track as seed
            fp=next(iter(self._library))
        # Build playlist by harmonic progression
        playlist=[fp]; used={fp}
        current=self._library[fp]
        for _ in range(min(MAX_PLAYLIST_GEN,len(self._library)-1)):
            key=current.get("key","")
            bpm=current.get("bpm") or 120
            lib_keys={f:d["key"] for f,d in self._library.items() if f not in used and d.get("key")}
            matches=get_harmonic_matches(key,lib_keys)
            if not matches:
                # Fallback: closest BPM
                remaining=[(f,d) for f,d in self._library.items() if f not in used]
                if not remaining: break
                remaining.sort(key=lambda x:abs((x[1].get("bpm") or 120)-bpm))
                nxt=remaining[0][0]
            else:
                # Prefer similar BPM among harmonic matches
                matches.sort(key=lambda x:abs((self._library[x[0]].get("bpm") or 120)-bpm))
                nxt=matches[0][0]
            playlist.append(nxt); used.add(nxt)
            current=self._library[nxt]
        self.pl_lb.delete(0,"end")
        for i,fp in enumerate(playlist):
            info=self._library[fp]
            bpm=f"{info['bpm']:.1f}" if info.get("bpm") else "?"
            c=info.get("camelot","")
            self.pl_lb.insert("end",f" {i+1:3d}. {info['file'][:35]:35s} {bpm:>8s} {c:6s}")
        self._playlist_files=playlist
        self.mix_status.config(text=f"Generated {len(playlist)}-track harmonic playlist",fg=LIME_DK)

    def _export_m3u(self):
        if not hasattr(self,"_playlist_files") or not self._playlist_files: return
        path=filedialog.asksaveasfilename(defaultextension=".m3u",filetypes=[("M3U Playlist","*.m3u")])
        if path:
            with open(path,"w",encoding="utf-8") as f:
                f.write("#EXTM3U\n")
                for fp in self._playlist_files:
                    info=self._library.get(fp,{})
                    dur=0  # could compute if needed
                    f.write(f"#EXTINF:{dur},{info.get('file','')}\n{fp}\n")
            self.mix_status.config(text=f"Exported: {os.path.basename(path)}",fg=LIME_DK)

    def _smart_playlist(self):
        if not self._library:
            messagebox.showinfo("LimeWire","Scan a library first."); return
        # Filter by energy level
        ef=self._energy_filter.get()
        pool=dict(self._library)
        if "Low" in ef: pool={f:d for f,d in pool.items() if (d.get("bpm") or 120)<100}
        elif "Medium" in ef: pool={f:d for f,d in pool.items() if 100<=(d.get("bpm") or 120)<130}
        elif "High" in ef and "Very" not in ef: pool={f:d for f,d in pool.items() if 130<=(d.get("bpm") or 120)<160}
        elif "Very" in ef: pool={f:d for f,d in pool.items() if (d.get("bpm") or 120)>=160}
        if not pool:
            self.mix_status.config(text="No tracks match energy filter",fg=YELLOW); return
        # Sort
        sm=self._sort_mode.get()
        items=list(pool.items())
        if "Ramp Up" in sm: items.sort(key=lambda x:x[1].get("bpm") or 120)
        elif "Ramp Down" in sm: items.sort(key=lambda x:-(x[1].get("bpm") or 120))
        elif "Key Groups" in sm:
            # Group by major/minor then by Camelot number
            def _key_sort(x):
                cam=x[1].get("camelot","")
                num=0; letter="A"
                if cam:
                    try: num=int(cam[:-1]); letter=cam[-1]
                    except Exception: pass
                return (letter,num)
            items.sort(key=_key_sort)
        else:
            # Harmonic Flow: use existing logic but with filtered pool
            fp=next(iter(pool))
            playlist=[fp]; used={fp}; current=pool[fp]
            for _ in range(min(MAX_PLAYLIST_GEN,len(pool)-1)):
                key=current.get("key",""); bpm=current.get("bpm") or 120
                lib_keys={f:d["key"] for f,d in pool.items() if f not in used and d.get("key")}
                matches=get_harmonic_matches(key,lib_keys)
                if not matches:
                    remaining=[(f,d) for f,d in pool.items() if f not in used]
                    if not remaining: break
                    remaining.sort(key=lambda x:abs((x[1].get("bpm") or 120)-bpm))
                    nxt=remaining[0][0]
                else:
                    matches.sort(key=lambda x:abs((pool[x[0]].get("bpm") or 120)-bpm))
                    nxt=matches[0][0]
                playlist.append(nxt); used.add(nxt); current=pool[nxt]
            items=[(f,pool[f]) for f in playlist]
        self.pl_lb.delete(0,"end")
        self._playlist_files=[f for f,_ in items]
        for i,(fp,info) in enumerate(items):
            bpm=f"{info['bpm']:.1f}" if info.get("bpm") else "?"
            c=info.get("camelot","")
            self.pl_lb.insert("end",f" {i+1:3d}. {info['file'][:35]:35s} {bpm:>8s} {c:6s}")
        self.mix_status.config(text=f"Smart playlist: {len(items)} tracks ({ef}, {sm})",fg=LIME_DK)


# ═══════════════════════════════════════════════════════════════════════════════
# SAMPLES PAGE — Freesound sample browser
# ═══════════════════════════════════════════════════════════════════════════════

class SamplesPage(ScrollFrame):
    """Freesound.org sample browser and downloader."""
    def __init__(self,parent,app):
        super().__init__(parent); self.app=app; self._results=[]; self._build(self.inner)
    def _build(self,p):
        sg=GroupBox(p,"Freesound Sample Search"); sg.pack(fill="x",padx=10,pady=(10,6))
        sr=tk.Frame(sg,bg=BG); sr.pack(fill="x")
        tk.Label(sr,text="Search:",font=F_BOLD,bg=BG,fg=TEXT).pack(side="left",padx=(0,6))
        self.query_var=tk.StringVar()
        self.query_e=ClassicEntry(sr,self.query_var,width=30)
        self.query_e.pack(side="left",fill="x",expand=True,ipady=2,padx=(0,6))
        self.query_e.bind("<Return>",lambda e:self._search())
        LimeBtn(sr,"Search",self._search).pack(side="left",padx=(0,6))
        # Filters
        fr=tk.Frame(sg,bg=BG); fr.pack(fill="x",pady=(4,0))
        tk.Label(fr,text="Duration:",font=F_SMALL,bg=BG,fg=TEXT).pack(side="left",padx=(0,4))
        self.dur_var=tk.StringVar(value="any")
        ClassicCombo(fr,self.dur_var,["any","0-5s","5-30s","30s-2m","2m+"],width=8).pack(side="left",padx=(0,12))
        tk.Label(fr,text="Sort:",font=F_SMALL,bg=BG,fg=TEXT).pack(side="left",padx=(0,4))
        self.sort_var=tk.StringVar(value="score")
        ClassicCombo(fr,self.sort_var,["score","downloads_desc","rating_desc","duration_asc","created_desc"],width=16).pack(side="left")

        self.search_status=tk.Label(sg,text="Search Freesound.org for samples, loops, and sound effects (API key required)",
                                    font=F_SMALL,bg=BG,fg=TEXT_DIM,anchor="w")
        self.search_status.pack(fill="x",pady=(4,0))

        # Results
        rg=GroupBox(p,"Results"); rg.pack(fill="both",padx=10,pady=(0,6),expand=True)
        cols=tk.Frame(rg,bg=CARD_BG,bd=0); cols.pack(fill="x")
        tk.Frame(rg,bg=CARD_BORDER,height=1).pack(fill="x")
        for col,w in [("Name",30),("Duration",10),("Rate",8),("Downloads",10),("License",15)]:
            tk.Label(cols,text=col,font=F_BOLD,bg=CARD_BG,fg=TEXT,width=w,anchor="w").pack(side="left")
        self.res_frame,self.res_lb=ClassicListbox(rg,height=12)
        self.res_frame.pack(fill="both",expand=True)

        # Actions
        ag=tk.Frame(rg,bg=BG); ag.pack(fill="x",pady=(6,0))
        OrangeBtn(ag,"Preview",self._preview).pack(side="left",padx=(0,6))
        LimeBtn(ag,"Download Selected",self._download).pack(side="left",padx=(0,6))
        ClassicBtn(ag,"Open in Browser",self._open_web).pack(side="left")

        # API Key
        kg=GroupBox(p,"Freesound API Key"); kg.pack(fill="x",padx=10,pady=(0,10))
        kr=tk.Frame(kg,bg=BG); kr.pack(fill="x")
        tk.Label(kr,text="API Key:",font=F_BODY,bg=BG,fg=TEXT).pack(side="left",padx=(0,6))
        self.key_var=tk.StringVar(value=self.app.settings.get("freesound_api_key",""))
        ClassicEntry(kr,self.key_var,width=40).pack(side="left",fill="x",expand=True,ipady=1,padx=(0,6))
        ClassicBtn(kr,"Save Key",self._save_key).pack(side="left")
        tk.Label(kg,text="Get a free key at freesound.org/apiv2/apply/",font=F_SMALL,bg=BG,fg=TEXT_BLUE).pack(anchor="w",pady=(2,0))

    def _save_key(self):
        self.app.settings["freesound_api_key"]=self.key_var.get().strip()
        self.app._save_settings(); self.app.toast("Freesound API key saved")

    def _search(self):
        query=self.query_var.get().strip()
        if not query: return
        key=self.key_var.get().strip() or self.app.settings.get("freesound_api_key","")
        if not key:
            messagebox.showinfo("LimeWire","Set your Freesound API key first."); return
        self.search_status.config(text=f"Searching: {query}...",fg=YELLOW)
        threading.Thread(target=self._do_search,args=(query,key),daemon=True).start()

    def _do_search(self,query,api_key):
        try:
            dur_filter=""
            dur=self.dur_var.get() if hasattr(self,"dur_var") else "any"
            if dur=="0-5s": dur_filter="&filter=duration:[0 TO 5]"
            elif dur=="5-30s": dur_filter="&filter=duration:[5 TO 30]"
            elif dur=="30s-2m": dur_filter="&filter=duration:[30 TO 120]"
            elif dur=="2m+": dur_filter="&filter=duration:[120 TO *]"
            sort=self.sort_var.get() if hasattr(self,"sort_var") else "score"
            url=(f"https://freesound.org/apiv2/search/text/?query={requests.utils.quote(query)}"
                 f"&fields=id,name,duration,samplerate,download_count,license,previews,url"
                 f"&page_size=30&sort={sort}{dur_filter}&token={api_key}")
            resp=requests.get(url,timeout=15)
            if resp.status_code==200:
                data=resp.json()
                self._results=data.get("results",[])
                self.after(0,lambda:self._render_results(data.get("count",0)))
            elif resp.status_code==401:
                self.after(0,lambda:self.search_status.config(text="Invalid API key",fg=RED))
            else:
                self.after(0,lambda:self.search_status.config(text=f"Error: HTTP {resp.status_code}",fg=RED))
        except Exception as e:
            self.after(0,lambda:self.search_status.config(text=f"Error: {str(e)[:60]}",fg=RED))

    def _render_results(self,total):
        self.res_lb.delete(0,"end")
        for r in self._results:
            dur=r.get("duration",0)
            dur_s=f"{dur:.1f}s" if dur<60 else f"{dur/60:.1f}m"
            sr=f"{r.get('samplerate',0)//1000}k"
            dl=str(r.get("download_count",0))
            lic=r.get("license","").split("/")[-2] if "/" in r.get("license","") else "?"
            name=r.get("name","")[:30]
            self.res_lb.insert("end",f" {name:30s} {dur_s:>10s} {sr:>8s} {dl:>10s} {lic:15s}")
        self.search_status.config(text=f"Found {total} results, showing {len(self._results)}",fg=LIME_DK)

    def _get_selected(self):
        sel=self.res_lb.curselection()
        if sel and sel[0]<len(self._results): return self._results[sel[0]]
        return None

    def _preview(self):
        r=self._get_selected()
        if not r: return
        preview_url=r.get("previews",{}).get("preview-lq-mp3","") or r.get("previews",{}).get("preview-hq-mp3","")
        if not preview_url:
            self.search_status.config(text="No preview available",fg=RED); return
        self.search_status.config(text=f"Loading preview: {r.get('name','')}...",fg=YELLOW)
        def _do():
            try:
                tmp=os.path.join(os.environ.get("TEMP","."),"_lw_sample_preview.mp3")
                resp=requests.get(preview_url,timeout=15)
                with open(tmp,"wb") as f: f.write(resp.content)
                _audio.load(tmp); _audio.play()
                self.after(0,lambda:self.search_status.config(text=f"Playing: {r.get('name','')}",fg=LIME_DK))
            except Exception as e:
                self.after(0,lambda:self.search_status.config(text=f"Preview error: {str(e)[:60]}",fg=RED))
        threading.Thread(target=_do,daemon=True).start()

    def _download(self):
        r=self._get_selected()
        if not r: return
        key=self.key_var.get().strip() or self.app.settings.get("freesound_api_key","")
        if not key: messagebox.showinfo("LimeWire","Set API key first."); return
        # Freesound download requires OAuth2, use preview as fallback
        preview_url=r.get("previews",{}).get("preview-hq-mp3","")
        if not preview_url:
            messagebox.showinfo("LimeWire","No download available for this sample."); return
        out_dir=os.path.join(self.app.output_dir,"Samples")
        os.makedirs(out_dir,exist_ok=True)
        name=r.get("name","sample").replace("/","_")
        out_path=os.path.join(out_dir,f"{name}.mp3")
        self.search_status.config(text=f"Downloading: {name}...",fg=YELLOW)
        def _do():
            try:
                resp=requests.get(preview_url,timeout=30)
                with open(out_path,"wb") as f: f.write(resp.content)
                self.after(0,lambda:(self.search_status.config(text=f"Saved: {os.path.basename(out_path)}",fg=LIME_DK),
                    self.app.toast(f"Sample: {name}")))
            except Exception as e:
                self.after(0,lambda:self.search_status.config(text=f"Download error: {str(e)[:60]}",fg=RED))
        threading.Thread(target=_do,daemon=True).start()

    def _open_web(self):
        r=self._get_selected()
        if r and r.get("url"): webbrowser.open(r["url"])


# ═══════════════════════════════════════════════════════════════════════════════
# EDITOR PAGE — Non-destructive audio editor
# ═══════════════════════════════════════════════════════════════════════════════

class EditorPage(ScrollFrame):
    """Non-destructive audio editor with trim, cut, fade, merge, and undo/redo."""
    def __init__(self,parent,app):
        super().__init__(parent); self.app=app
        self._segment=None; self._undo_stack=[]; self._redo_stack=[]
        self._sel_start_ms=0; self._sel_end_ms=0; self._drag_start=None
        self._merge_files=[]; self._bars=[]
        self._zoom=1.0; self._scroll_offset=0.0  # 0.0-1.0 normalized scroll
        self._build(self.inner)

    def _build(self,p):
        # Source file
        fg=GroupBox(p,"Source Audio File"); fg.pack(fill="x",padx=10,pady=(10,6))
        fr=tk.Frame(fg,bg=BG); fr.pack(fill="x")
        self.file_var=tk.StringVar()
        ClassicEntry(fr,self.file_var,width=55).pack(side="left",fill="x",expand=True,ipady=2,padx=(0,8))
        ClassicBtn(fr,"Browse...",self._browse).pack(side="left")
        self.info_lbl=tk.Label(fg,text="Load an audio file to begin editing",font=F_SMALL,bg=BG,fg=TEXT_DIM,anchor="w")
        self.info_lbl.pack(fill="x",pady=(4,0))

        # Waveform canvas
        wg=GroupBox(p,"Waveform"); wg.pack(fill="x",padx=10,pady=(0,6))
        self.wave_cv=tk.Canvas(wg,bg=CANVAS_BG,height=EDITOR_WAVEFORM_H,highlightthickness=0)
        self.wave_cv.pack(fill="x",padx=4,pady=4)
        self.wave_cv.bind("<ButtonPress-1>",self._on_press)
        self.wave_cv.bind("<B1-Motion>",self._on_drag)
        self.wave_cv.bind("<ButtonRelease-1>",self._on_release)
        self.wave_cv.bind("<MouseWheel>",self._on_zoom)  # Ctrl+scroll = zoom
        self.wave_cv.bind("<Shift-MouseWheel>",self._on_hscroll)  # Shift+scroll = pan
        # Zoom controls
        zf=tk.Frame(wg,bg=BG); zf.pack(fill="x",padx=4,pady=(0,2))
        ClassicBtn(zf,"Zoom In (+)",self._zoom_in).pack(side="left",padx=(0,4))
        ClassicBtn(zf,"Zoom Out (-)",self._zoom_out).pack(side="left",padx=(0,4))
        ClassicBtn(zf,"Fit All",self._zoom_reset).pack(side="left",padx=(0,8))
        self._zoom_lbl=tk.Label(zf,text="1.0x",font=F_SMALL,bg=BG,fg=TEXT_DIM)
        self._zoom_lbl.pack(side="left",padx=(0,8))
        self._hscroll=tk.Scrollbar(wg,orient="horizontal",command=self._on_scrollbar)
        self._hscroll.pack(fill="x",padx=4)
        # Time labels
        tf=tk.Frame(wg,bg=BG); tf.pack(fill="x",padx=4)
        self.time_start_lbl=tk.Label(tf,text="Start: 0.000s",font=F_SMALL,bg=BG,fg=TEXT_DIM)
        self.time_start_lbl.pack(side="left")
        self.time_end_lbl=tk.Label(tf,text="End: 0.000s",font=F_SMALL,bg=BG,fg=TEXT_DIM)
        self.time_end_lbl.pack(side="right")
        self.sel_lbl=tk.Label(tf,text="Selection: none",font=F_SMALL,bg=BG,fg=LIME)
        self.sel_lbl.pack()

        # Selection controls
        sg=GroupBox(p,"Selection (ms)"); sg.pack(fill="x",padx=10,pady=(0,6))
        sr=tk.Frame(sg,bg=BG); sr.pack(fill="x")
        tk.Label(sr,text="Start:",font=F_BODY,bg=BG,fg=TEXT).pack(side="left",padx=(0,4))
        self.sel_start_var=tk.StringVar(value="0")
        self.sel_start_sp=tk.Spinbox(sr,textvariable=self.sel_start_var,from_=0,to=9999999,
            width=10,font=F_BODY,bg=INPUT_BG,fg=TEXT,relief="flat",bd=1)
        self.sel_start_sp.pack(side="left",padx=(0,10))
        tk.Label(sr,text="End:",font=F_BODY,bg=BG,fg=TEXT).pack(side="left",padx=(0,4))
        self.sel_end_var=tk.StringVar(value="0")
        self.sel_end_sp=tk.Spinbox(sr,textvariable=self.sel_end_var,from_=0,to=9999999,
            width=10,font=F_BODY,bg=INPUT_BG,fg=TEXT,relief="flat",bd=1)
        self.sel_end_sp.pack(side="left",padx=(0,10))
        ClassicBtn(sr,"Select All",self._select_all).pack(side="left",padx=(0,6))
        ClassicBtn(sr,"Apply",self._apply_sel).pack(side="left")

        # Operations
        og=GroupBox(p,"Operations"); og.pack(fill="x",padx=10,pady=(0,6))
        obr=tk.Frame(og,bg=BG); obr.pack(fill="x")
        for txt,cmd in [("Trim",self._trim),("Cut",self._cut),("Fade In",self._fade_in),
                        ("Fade Out",self._fade_out),("Normalize",self._normalize),
                        ("Reverse",self._reverse),("Silence",self._silence)]:
            LimeBtn(obr,txt,cmd,width=10).pack(side="left",padx=(0,4),pady=2)
        ubr=tk.Frame(og,bg=BG); ubr.pack(fill="x",pady=(4,0))
        ClassicBtn(ubr,"Undo (Ctrl+Z)",self._undo).pack(side="left",padx=(0,6))
        ClassicBtn(ubr,"Redo (Ctrl+Y)",self._redo).pack(side="left")

        # Merge
        mg=GroupBox(p,"Merge / Concatenate"); mg.pack(fill="x",padx=10,pady=(0,6))
        mr=tk.Frame(mg,bg=BG); mr.pack(fill="x")
        LimeBtn(mr,"Add File",self._merge_add).pack(side="left",padx=(0,6))
        OrangeBtn(mr,"Clear List",self._merge_clear).pack(side="left",padx=(0,6))
        LimeBtn(mr,"Merge All",self._merge_all).pack(side="left")
        self.merge_lb_frame,self.merge_lb=ClassicListbox(mg,height=4)
        self.merge_lb_frame.pack(fill="x",pady=(4,0))

        # Export
        eg=GroupBox(p,"Export"); eg.pack(fill="x",padx=10,pady=(0,10))
        er=tk.Frame(eg,bg=BG); er.pack(fill="x")
        tk.Label(er,text="Format:",font=F_BODY,bg=BG,fg=TEXT).pack(side="left",padx=(0,6))
        self.exp_fmt_var=tk.StringVar(value="mp3")
        ClassicCombo(er,self.exp_fmt_var,["mp3","wav","flac","ogg","aac","m4a"],width=8).pack(side="left",padx=(0,8))
        LimeBtn(er,"Export",self._export,width=12).pack(side="left",padx=(0,8))
        ClassicBtn(er,"Play Preview",self._play_preview).pack(side="left")
        self.exp_status=tk.Label(eg,text="",font=F_SMALL,bg=BG,fg=TEXT_DIM,anchor="w")
        self.exp_status.pack(fill="x",pady=(4,0))
        self.exp_prog=ClassicProgress(eg); self.exp_prog.pack(fill="x",pady=(4,0))

    def _browse(self):
        f=filedialog.askopenfilename(filetypes=[("Audio","*.mp3 *.wav *.flac *.ogg *.m4a *.aac *.opus"),("All","*.*")])
        if f: self.file_var.set(f); self._load_file(f)

    def _load_file(self,path):
        self.exp_status.config(text="Loading...",fg=YELLOW)
        def _do():
            seg,err=load_audio_pydub(path)
            if err:
                self.after(0,lambda:self.exp_status.config(text=f"Error: {err}",fg=RED))
                return
            self._segment=seg; self._undo_stack=[seg]; self._redo_stack=[]
            self._sel_start_ms=0; self._sel_end_ms=len(seg)
            dur=len(seg)/1000
            self.after(0,lambda:(
                self.info_lbl.config(text=f"{os.path.basename(path)}  |  {dur:.1f}s  |  {seg.channels}ch  {seg.frame_rate}Hz"),
                self.exp_status.config(text="Loaded",fg=LIME_DK),
                self._update_sel_labels(),
                self._draw_waveform()
            ))
        threading.Thread(target=_do,daemon=True).start()

    def _push_undo(self):
        if self._segment is not None:
            self._undo_stack.append(self._segment)
            if len(self._undo_stack)>EDITOR_UNDO_MAX:
                self._undo_stack.pop(0)
            self._redo_stack.clear()

    def _draw_waveform(self):
        cv=self.wave_cv; cv.delete("all")
        if not self._segment: return
        cv.update_idletasks()
        w=cv.winfo_width() or 600; h=EDITOR_WAVEFORM_H
        dur_ms=len(self._segment)
        # Compute zoomed sample count — render more bars than canvas width for zoom
        total_bars=int(w*self._zoom)
        all_bars=audio_segment_to_waveform(self._segment,total_bars,h)
        if not all_bars: return
        # Visible window based on scroll offset
        visible=len(all_bars)/self._zoom if self._zoom>0 else len(all_bars)
        start_idx=int(self._scroll_offset*max(0,len(all_bars)-visible))
        end_idx=int(start_idx+visible)
        start_idx=max(0,min(start_idx,len(all_bars)-1))
        end_idx=max(start_idx+1,min(end_idx,len(all_bars)))
        visible_bars=all_bars[start_idx:end_idx]
        self._bars=all_bars; self._view_start=start_idx; self._view_end=end_idx
        # Draw bars scaled to canvas width
        mid=h//2
        n=len(visible_bars)
        for i,bh in enumerate(visible_bars):
            x=int(i*w/n) if n>0 else i
            cv.create_line(x,mid-bh//2,x,mid+bh//2,fill=LIME)
        # Draw selection overlay (mapped to visible range)
        if self._segment and self._sel_start_ms<self._sel_end_ms and dur_ms>0:
            # Map ms to bar index
            sel_bar_start=self._sel_start_ms/dur_ms*len(all_bars)
            sel_bar_end=self._sel_end_ms/dur_ms*len(all_bars)
            # Map to visible pixel range
            x1=int((sel_bar_start-start_idx)/(end_idx-start_idx)*w)
            x2=int((sel_bar_end-start_idx)/(end_idx-start_idx)*w)
            x1=max(0,min(x1,w)); x2=max(0,min(x2,w))
            if x2>x1: cv.create_rectangle(x1,0,x2,h,fill=LIME,stipple="gray25",outline="")
        # Update scrollbar
        if len(all_bars)>0:
            thumb_size=min(1.0,1.0/self._zoom)
            lo=self._scroll_offset*(1.0-thumb_size)
            self._hscroll.set(lo,lo+thumb_size)
        self._zoom_lbl.config(text=f"{self._zoom:.1f}x")

    def _px_to_ms(self,x):
        """Convert canvas pixel x to milliseconds, accounting for zoom/scroll."""
        if not self._segment: return 0
        cv=self.wave_cv; w=cv.winfo_width() or 600; dur_ms=len(self._segment)
        if not hasattr(self,"_view_start"): return int(x/w*dur_ms)
        total=len(self._bars) if self._bars else w
        bar_idx=self._view_start+(x/w)*(self._view_end-self._view_start)
        return int(max(0,min(dur_ms,bar_idx/total*dur_ms)))
    def _on_press(self,e):
        self._drag_start=e.x
    def _on_drag(self,e):
        if self._drag_start is None or not self._segment: return
        x1=min(self._drag_start,e.x); x2=max(self._drag_start,e.x)
        self._sel_start_ms=self._px_to_ms(x1)
        self._sel_end_ms=self._px_to_ms(x2)
        self._update_sel_labels(); self._draw_waveform()
    def _on_release(self,e):
        self._drag_start=None
        self._update_sel_labels()
    def _on_zoom(self,e):
        """Ctrl+mousewheel or plain mousewheel to zoom."""
        if e.delta>0: self._zoom_in()
        else: self._zoom_out()
    def _on_hscroll(self,e):
        """Shift+mousewheel to pan horizontally."""
        if self._zoom<=1.0: return
        step=0.05
        if e.delta>0: self._scroll_offset=max(0.0,self._scroll_offset-step)
        else: self._scroll_offset=min(1.0,self._scroll_offset+step)
        self._draw_waveform()
    def _on_scrollbar(self,*args):
        """Handle scrollbar commands."""
        if args[0]=="moveto":
            thumb_size=min(1.0,1.0/self._zoom)
            self._scroll_offset=min(1.0,float(args[1])/(1.0-thumb_size)) if thumb_size<1.0 else 0.0
            self._scroll_offset=max(0.0,min(1.0,self._scroll_offset))
            self._draw_waveform()
    def _zoom_in(self):
        self._zoom=min(32.0,self._zoom*1.5); self._draw_waveform()
    def _zoom_out(self):
        self._zoom=max(1.0,self._zoom/1.5)
        if self._zoom<=1.0: self._scroll_offset=0.0
        self._draw_waveform()
    def _zoom_reset(self):
        self._zoom=1.0; self._scroll_offset=0.0; self._draw_waveform()

    def _update_sel_labels(self):
        if not self._segment: return
        dur_ms=len(self._segment)
        self.time_start_lbl.config(text=f"Start: {self._sel_start_ms/1000:.3f}s")
        self.time_end_lbl.config(text=f"End: {dur_ms/1000:.3f}s")
        sel_dur=(self._sel_end_ms-self._sel_start_ms)/1000
        self.sel_lbl.config(text=f"Selection: {self._sel_start_ms}ms - {self._sel_end_ms}ms ({sel_dur:.3f}s)")
        self.sel_start_var.set(str(self._sel_start_ms))
        self.sel_end_var.set(str(self._sel_end_ms))

    def _select_all(self):
        if not self._segment: return
        self._sel_start_ms=0; self._sel_end_ms=len(self._segment)
        self._update_sel_labels(); self._draw_waveform()

    def _apply_sel(self):
        try:
            self._sel_start_ms=int(self.sel_start_var.get())
            self._sel_end_ms=int(self.sel_end_var.get())
            self._draw_waveform(); self._update_sel_labels()
        except ValueError: pass

    def _trim(self):
        if not self._segment: return
        self._push_undo()
        self._segment=self._segment[self._sel_start_ms:self._sel_end_ms]
        self._sel_start_ms=0; self._sel_end_ms=len(self._segment)
        self._update_sel_labels(); self._draw_waveform()
        self.exp_status.config(text="Trimmed",fg=LIME_DK)

    def _cut(self):
        if not self._segment: return
        self._push_undo()
        before=self._segment[:self._sel_start_ms]
        after=self._segment[self._sel_end_ms:]
        self._segment=before+after
        self._sel_end_ms=min(self._sel_start_ms,len(self._segment))
        self._update_sel_labels(); self._draw_waveform()
        self.exp_status.config(text="Cut selection removed",fg=LIME_DK)

    def _fade_in(self):
        if not self._segment: return
        self._push_undo()
        dur=self._sel_end_ms-self._sel_start_ms
        if dur<=0: dur=EDITOR_FADE_DEFAULT_MS
        self._segment=self._segment.fade_in(dur)
        self._draw_waveform()
        self.exp_status.config(text=f"Fade in: {dur}ms",fg=LIME_DK)

    def _fade_out(self):
        if not self._segment: return
        self._push_undo()
        dur=self._sel_end_ms-self._sel_start_ms
        if dur<=0: dur=EDITOR_FADE_DEFAULT_MS
        self._segment=self._segment.fade_out(dur)
        self._draw_waveform()
        self.exp_status.config(text=f"Fade out: {dur}ms",fg=LIME_DK)

    def _normalize(self):
        if not self._segment: return
        self._push_undo()
        from pydub.effects import normalize
        self._segment=normalize(self._segment)
        self._draw_waveform()
        self.exp_status.config(text="Normalized",fg=LIME_DK)

    def _reverse(self):
        if not self._segment: return
        self._push_undo()
        self._segment=self._segment.reverse()
        self._draw_waveform()
        self.exp_status.config(text="Reversed",fg=LIME_DK)

    def _silence(self):
        if not self._segment: return
        self._push_undo()
        from pydub import AudioSegment as _AS
        dur=self._sel_end_ms-self._sel_start_ms
        if dur<=0: return
        silent=_AS.silent(duration=dur,frame_rate=self._segment.frame_rate)
        self._segment=self._segment[:self._sel_start_ms]+silent+self._segment[self._sel_end_ms:]
        self._draw_waveform()
        self.exp_status.config(text=f"Silenced {dur}ms",fg=LIME_DK)

    def _undo(self):
        if len(self._undo_stack)<=1: return
        self._redo_stack.append(self._undo_stack.pop())
        self._segment=self._undo_stack[-1]
        self._sel_start_ms=0; self._sel_end_ms=len(self._segment)
        self._update_sel_labels(); self._draw_waveform()
        self.exp_status.config(text="Undo",fg=TEXT_DIM)

    def _redo(self):
        if not self._redo_stack: return
        seg=self._redo_stack.pop()
        self._undo_stack.append(seg); self._segment=seg
        self._sel_start_ms=0; self._sel_end_ms=len(self._segment)
        self._update_sel_labels(); self._draw_waveform()
        self.exp_status.config(text="Redo",fg=TEXT_DIM)

    def _merge_add(self):
        f=filedialog.askopenfilename(filetypes=[("Audio","*.mp3 *.wav *.flac *.ogg *.m4a"),("All","*.*")])
        if f:
            self._merge_files.append(f)
            self.merge_lb.insert("end",os.path.basename(f))

    def _merge_clear(self):
        self._merge_files.clear(); self.merge_lb.delete(0,"end")

    def _merge_all(self):
        files=list(self._merge_files)
        if self._segment: files.insert(0,None)  # None = current segment
        if len(files)<2:
            self.exp_status.config(text="Add at least 2 files to merge",fg=YELLOW); return
        self.exp_status.config(text="Merging...",fg=YELLOW)
        def _do():
            try:
                combined=self._segment if self._segment else AudioSegment.empty()
                for f in files:
                    if f is None: continue
                    seg,err=load_audio_pydub(f)
                    if err: self.after(0,lambda:self.exp_status.config(text=f"Error: {err}",fg=RED)); return
                    combined+=seg
                self._push_undo(); self._segment=combined
                self._sel_start_ms=0; self._sel_end_ms=len(combined)
                self.after(0,lambda:(self._update_sel_labels(),self._draw_waveform(),
                    self.exp_status.config(text=f"Merged {len(files)} files ({len(combined)/1000:.1f}s)",fg=LIME_DK)))
            except Exception as e:
                self.after(0,lambda:self.exp_status.config(text=f"Merge error: {str(e)[:60]}",fg=RED))
        threading.Thread(target=_do,daemon=True).start()

    def _export(self):
        if not self._segment: return
        fmt=self.exp_fmt_var.get()
        path=filedialog.asksaveasfilename(defaultextension=f".{fmt}",
            filetypes=[(fmt.upper(),f"*.{fmt}"),("All","*.*")],
            initialdir=self.app.output_dir)
        if not path: return
        self.exp_status.config(text="Exporting...",fg=YELLOW)
        self.exp_prog["value"]=50
        def _do():
            out,err=export_audio_pydub(self._segment,path,fmt)
            if err:
                self.after(0,lambda:(self.exp_status.config(text=f"Error: {err}",fg=RED),
                    self.exp_prog.configure(value=0)))
            else:
                self.after(0,lambda:(self.exp_status.config(text=f"Exported: {os.path.basename(out)}",fg=LIME_DK),
                    self.exp_prog.configure(value=100),self.app.toast(f"Exported: {os.path.basename(out)}")))
        threading.Thread(target=_do,daemon=True).start()

    def _play_preview(self):
        if not self._segment: return
        tmp=os.path.join(os.environ.get("TEMP","."),"_lw_editor_preview.wav")
        self._segment.export(tmp,format="wav")
        _audio.load(tmp); _audio.play()
        self.exp_status.config(text="Playing preview...",fg=LIME_DK)


# ═══════════════════════════════════════════════════════════════════════════════
# RECORDER PAGE — Microphone recording + Whisper transcription
# ═══════════════════════════════════════════════════════════════════════════════

class RecorderPage(ScrollFrame):
    """Microphone recording with VU meter, live waveform, and Whisper transcription."""
    def __init__(self,parent,app):
        super().__init__(parent); self.app=app
        self._recording=False; self._stream=None; self._frames=[]
        self._recorded_data=None; self._recorded_sr=RECORDER_SAMPLE_RATE
        self._vu_after=None; self._wave_after=None
        self._build(self.inner)

    def _build(self,p):
        # Record controls
        rg=GroupBox(p,"Record"); rg.pack(fill="x",padx=10,pady=(10,6))
        cr=tk.Frame(rg,bg=BG); cr.pack(fill="x")
        tk.Label(cr,text="Device:",font=F_BODY,bg=BG,fg=TEXT).pack(side="left",padx=(0,6))
        self.dev_var=tk.StringVar(value="Default")
        self.dev_combo=ClassicCombo(cr,self.dev_var,["Default"],width=30)
        self.dev_combo.pack(side="left",padx=(0,8))
        ClassicBtn(cr,"Refresh",self._refresh_devices).pack(side="left",padx=(0,16))
        self.rec_btn=LimeBtn(cr,"\u25CF Record",self._toggle_record,width=12)
        self.rec_btn.pack(side="left",padx=(0,6))
        self.stop_btn=OrangeBtn(cr,"\u25A0 Stop",self._stop_recording,width=8)
        self.stop_btn.pack(side="left")
        self.timer_lbl=tk.Label(rg,text="00:00.0",font=("Courier New",14,"bold"),bg=BG,fg=RED)
        self.timer_lbl.pack(anchor="w",pady=(4,0))

        # VU meter
        vg=GroupBox(p,"Level Meter"); vg.pack(fill="x",padx=10,pady=(0,6))
        self.vu_cv=tk.Canvas(vg,bg=CANVAS_BG,height=24,highlightthickness=0)
        self.vu_cv.pack(fill="x",padx=4,pady=4)
        self._vu_bar=self.vu_cv.create_rectangle(0,2,0,22,fill=LIME,outline="")
        self._vu_peak=self.vu_cv.create_line(0,0,0,24,fill=RED,width=2)
        self._peak_val=0.0

        # Live waveform
        wg=GroupBox(p,"Live Waveform"); wg.pack(fill="x",padx=10,pady=(0,6))
        self.live_cv=tk.Canvas(wg,bg=CANVAS_BG,height=60,highlightthickness=0)
        self.live_cv.pack(fill="x",padx=4,pady=4)

        # Playback
        pg=GroupBox(p,"Playback"); pg.pack(fill="x",padx=10,pady=(0,6))
        pbr=tk.Frame(pg,bg=BG); pbr.pack(fill="x")
        LimeBtn(pbr,"\u25B6 Play",self._play_recorded,width=10).pack(side="left",padx=(0,6))
        OrangeBtn(pbr,"\u25A0 Stop",lambda:_audio.stop(),width=8).pack(side="left")
        self.play_lbl=tk.Label(pg,text="No recording yet",font=F_SMALL,bg=BG,fg=TEXT_DIM,anchor="w")
        self.play_lbl.pack(fill="x",pady=(4,0))

        # Transcription
        tg=GroupBox(p,"Transcription (Whisper)"); tg.pack(fill="x",padx=10,pady=(0,6))
        tr=tk.Frame(tg,bg=BG); tr.pack(fill="x")
        tk.Label(tr,text="Model:",font=F_BODY,bg=BG,fg=TEXT).pack(side="left",padx=(0,4))
        self.whisper_model_var=tk.StringVar(value="base")
        ClassicCombo(tr,self.whisper_model_var,["tiny","base","small","medium"],width=10).pack(side="left",padx=(0,8))
        tk.Label(tr,text="Lang:",font=F_BODY,bg=BG,fg=TEXT).pack(side="left",padx=(0,4))
        self.whisper_lang_var=tk.StringVar(value="en")
        ClassicCombo(tr,self.whisper_lang_var,["en","es","fr","de","it","pt","zh","ja","ko","auto"],width=6).pack(side="left",padx=(0,8))
        LimeBtn(tr,"Transcribe",self._transcribe,width=12).pack(side="left",padx=(0,6))
        ClassicBtn(tr,"Export SRT",self._export_srt).pack(side="left")
        self.trans_text=tk.Text(tg,height=6,font=F_MONO,bg=INPUT_BG,fg=TEXT,relief="flat",bd=1,wrap="word")
        self.trans_text.pack(fill="x",padx=4,pady=(4,0))
        self.trans_status=tk.Label(tg,text="Record audio first, then transcribe",font=F_SMALL,bg=BG,fg=TEXT_DIM,anchor="w")
        self.trans_status.pack(fill="x",pady=(2,0))
        self._whisper_segments=[]

        # Save
        sg=GroupBox(p,"Save Recording"); sg.pack(fill="x",padx=10,pady=(0,10))
        sr=tk.Frame(sg,bg=BG); sr.pack(fill="x")
        tk.Label(sr,text="Format:",font=F_BODY,bg=BG,fg=TEXT).pack(side="left",padx=(0,4))
        self.save_fmt_var=tk.StringVar(value="wav")
        ClassicCombo(sr,self.save_fmt_var,["wav","mp3","flac","ogg"],width=8).pack(side="left",padx=(0,8))
        tk.Label(sr,text="Filename:",font=F_BODY,bg=BG,fg=TEXT).pack(side="left",padx=(0,4))
        self.save_name_var=tk.StringVar(value="recording")
        ClassicEntry(sr,self.save_name_var,width=20).pack(side="left",fill="x",expand=True,ipady=2,padx=(0,8))
        LimeBtn(sr,"Save",self._save,width=10).pack(side="left")
        self.save_status=tk.Label(sg,text="",font=F_SMALL,bg=BG,fg=TEXT_DIM,anchor="w")
        self.save_status.pack(fill="x",pady=(4,0))

        # Auto-refresh devices on build
        self.after(500,self._refresh_devices)

    def _refresh_devices(self):
        if not _ensure_sounddevice():
            self.dev_combo.configure(values=["Default (sounddevice not installed)"]); return
        try:
            devs=sd_mod.query_devices()
            input_devs=["Default"]
            for i,d in enumerate(devs):
                if d["max_input_channels"]>0:
                    input_devs.append(f"{i}: {d['name']}")
            self.dev_combo.configure(values=input_devs)
        except Exception: pass

    def _get_device_index(self):
        val=self.dev_var.get()
        if val.startswith("Default") or val=="Default": return None
        try: return int(val.split(":")[0])
        except Exception: return None

    def _toggle_record(self):
        if self._recording: self._stop_recording()
        else: self._start_recording()

    def _start_recording(self):
        if not _ensure_sounddevice():
            messagebox.showinfo("LimeWire","sounddevice not installed.\nRun: pip install sounddevice"); return
        if not HAS_NUMPY:
            messagebox.showinfo("LimeWire","numpy required for recording"); return
        self._frames=[]; self._recording=True; self._peak_val=0.0
        self.rec_btn.config(text="\u25CF Recording...",bg=RED,fg="#FFFFFF")
        self._start_time=time.time()
        dev_idx=self._get_device_index()
        try:
            self._stream=sd_mod.InputStream(
                samplerate=RECORDER_SAMPLE_RATE,channels=RECORDER_CHANNELS,
                dtype="float32",blocksize=RECORDER_CHUNK,device=dev_idx,
                callback=self._audio_callback)
            self._stream.start()
            self._update_timer()
            self._update_vu()
            self._update_live_wave()
        except Exception as e:
            self._recording=False
            self.rec_btn.config(text="\u25CF Record",bg=LIME,fg=TEXT)
            messagebox.showerror("Recording Error",str(e)[:200])

    def _audio_callback(self,indata,frames,time_info,status):
        if self._recording:
            self._frames.append(indata.copy())

    def _stop_recording(self):
        if not self._recording: return
        self._recording=False
        if self._stream:
            try: self._stream.stop(); self._stream.close()
            except Exception: pass
            self._stream=None
        self.rec_btn.config(text="\u25CF Record",bg=LIME,fg=TEXT)
        if self._vu_after: self.after_cancel(self._vu_after); self._vu_after=None
        if self._wave_after: self.after_cancel(self._wave_after); self._wave_after=None
        if self._frames:
            self._recorded_data=np.concatenate(self._frames,axis=0)
            dur=len(self._recorded_data)/RECORDER_SAMPLE_RATE
            self.play_lbl.config(text=f"Recorded {dur:.1f}s  ({RECORDER_SAMPLE_RATE}Hz, {RECORDER_CHANNELS}ch)")
            self.trans_status.config(text="Ready to transcribe",fg=LIME_DK)
        else:
            self.play_lbl.config(text="No audio captured",fg=YELLOW)

    def _update_timer(self):
        if not self._recording: return
        elapsed=time.time()-self._start_time
        m,s=divmod(elapsed,60)
        self.timer_lbl.config(text=f"{int(m):02d}:{s:05.1f}")
        self.after(100,self._update_timer)

    def _update_vu(self):
        if not self._recording: return
        if self._frames:
            chunk=self._frames[-1]
            rms=float(np.sqrt(np.mean(chunk**2)))
            db=max(0,min(1,(20*np.log10(rms+1e-10)+60)/60))
            self._peak_val=max(self._peak_val*0.95,db)
            w=self.vu_cv.winfo_width() or 400
            bar_x=int(db*w); peak_x=int(self._peak_val*w)
            color=LIME if db<0.7 else (YELLOW if db<0.9 else RED)
            self.vu_cv.coords(self._vu_bar,0,2,bar_x,22)
            self.vu_cv.itemconfig(self._vu_bar,fill=color)
            self.vu_cv.coords(self._vu_peak,peak_x,0,peak_x,24)
        self._vu_after=self.after(RECORDER_VU_UPDATE_MS,self._update_vu)

    def _update_live_wave(self):
        if not self._recording: return
        cv=self.live_cv; cv.delete("all")
        w=cv.winfo_width() or 600; h=60; mid=h//2
        # Show last ~100 chunks
        recent=self._frames[-100:] if len(self._frames)>100 else self._frames
        if recent:
            all_data=np.concatenate(recent,axis=0).flatten()
            step=max(1,len(all_data)//w)
            for i in range(0,min(len(all_data),w*step),step):
                x=i//step; val=all_data[i] if i<len(all_data) else 0
                y=int(val*mid*2)
                cv.create_line(x,mid-y,x,mid+y,fill=LIME)
        self._wave_after=self.after(80,self._update_live_wave)

    def _play_recorded(self):
        if self._recorded_data is None:
            self.play_lbl.config(text="Nothing recorded yet",fg=YELLOW); return
        if not _ensure_loudness():
            self.play_lbl.config(text="soundfile needed for playback",fg=RED); return
        tmp=os.path.join(os.environ.get("TEMP","."),"_lw_rec_preview.wav")
        sf.write(tmp,self._recorded_data,RECORDER_SAMPLE_RATE)
        _audio.load(tmp); _audio.play()
        self.play_lbl.config(text="Playing...",fg=LIME_DK)

    def _transcribe(self):
        if self._recorded_data is None:
            self.trans_status.config(text="Record audio first",fg=YELLOW); return
        if not _ensure_whisper():
            messagebox.showinfo("LimeWire","openai-whisper not installed.\nRun: pip install openai-whisper"); return
        model_size=self.whisper_model_var.get()
        lang=self.whisper_lang_var.get()
        self.trans_status.config(text=f"Loading Whisper {model_size} model...",fg=YELLOW)
        def _do():
            try:
                if not _ensure_loudness():
                    self.after(0,lambda:self.trans_status.config(text="soundfile required",fg=RED)); return
                tmp=os.path.join(os.environ.get("TEMP","."),"_lw_rec_whisper.wav")
                sf.write(tmp,self._recorded_data,RECORDER_SAMPLE_RATE)
                self.after(0,lambda:self.trans_status.config(text="Transcribing...",fg=YELLOW))
                model=whisper_mod.load_model(model_size)
                opts={"language":lang} if lang!="auto" else {}
                result=model.transcribe(tmp,**opts)
                self._whisper_segments=result.get("segments",[])
                text=result.get("text","")
                self.after(0,lambda:(
                    self.trans_text.delete("1.0","end"),
                    self.trans_text.insert("1.0",text),
                    self.trans_status.config(text=f"Transcribed ({len(self._whisper_segments)} segments, lang={result.get('language','?')})",fg=LIME_DK)
                ))
            except Exception as e:
                self.after(0,lambda:self.trans_status.config(text=f"Error: {str(e)[:80]}",fg=RED))
        threading.Thread(target=_do,daemon=True).start()

    def _export_srt(self):
        if not self._whisper_segments:
            self.trans_status.config(text="Transcribe first",fg=YELLOW); return
        path=filedialog.asksaveasfilename(defaultextension=".srt",
            filetypes=[("SRT","*.srt"),("All","*.*")],initialdir=self.app.output_dir)
        if not path: return
        with open(path,"w",encoding="utf-8") as f:
            for i,seg in enumerate(self._whisper_segments,1):
                f.write(f"{i}\n")
                f.write(f"{_srt_timestamp(seg['start'])} --> {_srt_timestamp(seg['end'])}\n")
                f.write(f"{seg['text'].strip()}\n\n")
        self.trans_status.config(text=f"SRT saved: {os.path.basename(path)}",fg=LIME_DK)
        self.app.toast(f"SRT exported: {os.path.basename(path)}")

    def _save(self):
        if self._recorded_data is None:
            self.save_status.config(text="Nothing to save",fg=YELLOW); return
        fmt=self.save_fmt_var.get(); name=self.save_name_var.get().strip() or "recording"
        name=sanitize_filename(name)
        out_dir=os.path.join(self.app.output_dir,"Recordings"); os.makedirs(out_dir,exist_ok=True)
        path=os.path.join(out_dir,f"{name}.{fmt}")
        self.save_status.config(text="Saving...",fg=YELLOW)
        def _do():
            try:
                if fmt=="wav":
                    if not _ensure_loudness():
                        self.after(0,lambda:self.save_status.config(text="soundfile required",fg=RED)); return
                    sf.write(path,self._recorded_data,RECORDER_SAMPLE_RATE)
                else:
                    # Use pydub for non-wav formats
                    if not _ensure_pydub():
                        self.after(0,lambda:self.save_status.config(text="pydub required for non-wav",fg=RED)); return
                    if not _ensure_loudness():
                        self.after(0,lambda:self.save_status.config(text="soundfile required",fg=RED)); return
                    tmp=os.path.join(os.environ.get("TEMP","."),"_lw_rec_tmp.wav")
                    sf.write(tmp,self._recorded_data,RECORDER_SAMPLE_RATE)
                    seg=AudioSegment.from_wav(tmp)
                    seg.export(path,format=fmt)
                self.after(0,lambda:(self.save_status.config(text=f"Saved: {os.path.basename(path)}",fg=LIME_DK),
                    self.app.toast(f"Recording saved: {os.path.basename(path)}")))
            except Exception as e:
                self.after(0,lambda:self.save_status.config(text=f"Error: {str(e)[:60]}",fg=RED))
        threading.Thread(target=_do,daemon=True).start()


# ═══════════════════════════════════════════════════════════════════════════════
# SPECTROGRAM PAGE — Frequency visualization
# ═══════════════════════════════════════════════════════════════════════════════

class SpectrogramPage(ScrollFrame):
    """Spectrogram visualization with multiple colormaps and export."""
    def __init__(self,parent,app):
        super().__init__(parent); self.app=app
        self._spec_img=None; self._spec_pil=None
        self._build(self.inner)

    def _build(self,p):
        # File
        fg=GroupBox(p,"Audio File"); fg.pack(fill="x",padx=10,pady=(10,6))
        fr=tk.Frame(fg,bg=BG); fr.pack(fill="x")
        self.file_var=tk.StringVar()
        ClassicEntry(fr,self.file_var,width=55).pack(side="left",fill="x",expand=True,ipady=2,padx=(0,8))
        ClassicBtn(fr,"Browse...",self._browse).pack(side="left")

        # Settings
        sg=GroupBox(p,"Spectrogram Settings"); sg.pack(fill="x",padx=10,pady=(0,6))
        sr=tk.Frame(sg,bg=BG); sr.pack(fill="x")
        tk.Label(sr,text="Type:",font=F_BODY,bg=BG,fg=TEXT).pack(side="left",padx=(0,4))
        self.type_var=tk.StringVar(value="Linear")
        ClassicCombo(sr,self.type_var,["Linear","Mel","CQT"],width=8).pack(side="left",padx=(0,10))
        tk.Label(sr,text="FFT:",font=F_BODY,bg=BG,fg=TEXT).pack(side="left",padx=(0,4))
        self.fft_var=tk.StringVar(value="2048")
        ClassicCombo(sr,self.fft_var,["512","1024","2048","4096"],width=6).pack(side="left",padx=(0,10))
        tk.Label(sr,text="Colormap:",font=F_BODY,bg=BG,fg=TEXT).pack(side="left",padx=(0,4))
        self.cmap_var=tk.StringVar(value=SPECTROGRAM_CMAP)
        ClassicCombo(sr,self.cmap_var,["viridis","magma","plasma","inferno"],width=10).pack(side="left",padx=(0,10))
        LimeBtn(sr,"Generate",self._generate,width=12).pack(side="left")

        # Canvas
        cg=GroupBox(p,"Spectrogram Display"); cg.pack(fill="both",padx=10,pady=(0,6),expand=True)
        self.spec_cv=tk.Canvas(cg,bg=CANVAS_BG,height=300,highlightthickness=0)
        self.spec_cv.pack(fill="both",expand=True,padx=4,pady=4)
        self.spec_cv.bind("<Motion>",self._on_hover)
        self.hover_lbl=tk.Label(cg,text="",font=F_SMALL,bg=BG,fg=TEXT_DIM,anchor="w")
        self.hover_lbl.pack(fill="x")

        # Actions
        ag=GroupBox(p,"Actions"); ag.pack(fill="x",padx=10,pady=(0,10))
        ar=tk.Frame(ag,bg=BG); ar.pack(fill="x")
        LimeBtn(ar,"Save Image",self._save_image,width=12).pack(side="left",padx=(0,6))
        ClassicBtn(ar,"Play Audio",self._play_audio).pack(side="left")
        self.status_lbl=tk.Label(ag,text="Load a file and click Generate",font=F_SMALL,bg=BG,fg=TEXT_DIM,anchor="w")
        self.status_lbl.pack(fill="x",pady=(4,0))

    def _browse(self):
        f=filedialog.askopenfilename(filetypes=[("Audio","*.mp3 *.wav *.flac *.ogg *.m4a"),("All","*.*")])
        if f: self.file_var.set(f)

    def _generate(self):
        path=self.file_var.get().strip()
        if not path or not os.path.isfile(path):
            self.status_lbl.config(text="Select a valid audio file",fg=YELLOW); return
        fft=int(self.fft_var.get()); cmap=self.cmap_var.get()
        spec_type=self.type_var.get()
        self.status_lbl.config(text="Generating spectrogram...",fg=YELLOW)
        def _do():
            try:
                if not _ensure_librosa():
                    self.after(0,lambda:self.status_lbl.config(text="librosa not installed",fg=RED)); return
                if not HAS_NUMPY:
                    self.after(0,lambda:self.status_lbl.config(text="numpy required",fg=RED)); return
                y, sr = librosa.load(path, sr=22050, mono=True)
                # Choose spectrogram type
                if spec_type=="Mel":
                    S=librosa.amplitude_to_db(librosa.feature.melspectrogram(y=y,sr=sr,n_fft=fft,hop_length=SPECTROGRAM_HOP),ref=np.max)
                elif spec_type=="CQT":
                    S=librosa.amplitude_to_db(np.abs(librosa.cqt(y,sr=sr,hop_length=SPECTROGRAM_HOP)),ref=np.max)
                else:
                    S=librosa.amplitude_to_db(np.abs(librosa.stft(y,n_fft=fft,hop_length=SPECTROGRAM_HOP)),ref=np.max)
                S_norm=np.clip((S+80)/80*255,0,255).astype(np.uint8)
                lut=_get_colormap(cmap)
                rgb=lut[S_norm]
                img=Image.fromarray(rgb[::-1].astype(np.uint8))
                self._spec_pil=img
                self._dur=len(y)/sr
                self._freq_max=sr//2
                # Resize to canvas
                self.after(0,self._render_spectrogram)
                self.after(0,lambda:self.status_lbl.config(
                    text=f"{spec_type} spectrogram | FFT={fft} | {len(y)/sr:.1f}s | {cmap}",fg=LIME_DK))
            except Exception as e:
                self.after(0,lambda:self.status_lbl.config(text=f"Error: {str(e)[:80]}",fg=RED))
        threading.Thread(target=_do,daemon=True).start()

    def _render_spectrogram(self):
        if not self._spec_pil: return
        cv=self.spec_cv; cv.update_idletasks()
        w=cv.winfo_width() or 800; h=cv.winfo_height() or 300
        resized=self._spec_pil.resize((w,h),Image.LANCZOS)
        self._spec_img=ImageTk.PhotoImage(resized)
        cv.delete("all")
        cv.create_image(0,0,anchor="nw",image=self._spec_img)

    def _on_hover(self,e):
        if not self._spec_pil or not hasattr(self,"_dur"): return
        cv=self.spec_cv
        w=cv.winfo_width() or 800; h=cv.winfo_height() or 300
        t=e.x/w*self._dur
        f=self._freq_max*(1-e.y/h)
        self.hover_lbl.config(text=f"Time: {t:.2f}s  |  Freq: {f:.0f} Hz")

    def _save_image(self):
        if not self._spec_pil:
            self.status_lbl.config(text="Generate a spectrogram first",fg=YELLOW); return
        path=filedialog.asksaveasfilename(defaultextension=".png",
            filetypes=[("PNG","*.png"),("JPEG","*.jpg"),("All","*.*")],
            initialdir=self.app.output_dir)
        if path:
            self._spec_pil.save(path)
            self.status_lbl.config(text=f"Saved: {os.path.basename(path)}",fg=LIME_DK)
            self.app.toast(f"Spectrogram saved: {os.path.basename(path)}")

    def _play_audio(self):
        path=self.file_var.get().strip()
        if path and os.path.isfile(path):
            _audio.load(path); _audio.play()
            self.status_lbl.config(text="Playing...",fg=LIME_DK)


# ═══════════════════════════════════════════════════════════════════════════════
# PITCH/TIME PAGE — Pitch shift, time stretch, vocal isolation
# ═══════════════════════════════════════════════════════════════════════════════

KEY_NAMES_FULL=["C","C#","D","D#","E","F","F#","G","G#","A","A#","B"]
ALL_KEYS=[f"{n} {m}" for m in ["Major","Minor"] for n in KEY_NAMES_FULL]

class PitchTimePage(ScrollFrame):
    """Pitch shifting, time stretching, key transposition, and vocal isolation."""
    def __init__(self,parent,app):
        super().__init__(parent); self.app=app
        self._detected_bpm=None; self._detected_key=None; self._output_file=None
        self._build(self.inner)

    def _build(self,p):
        # Source
        fg=GroupBox(p,"Source Audio"); fg.pack(fill="x",padx=10,pady=(10,6))
        fr=tk.Frame(fg,bg=BG); fr.pack(fill="x")
        self.file_var=tk.StringVar()
        ClassicEntry(fr,self.file_var,width=45).pack(side="left",fill="x",expand=True,ipady=2,padx=(0,8))
        ClassicBtn(fr,"Browse...",self._browse).pack(side="left",padx=(0,6))
        LimeBtn(fr,"Detect BPM/Key",self._detect,width=14).pack(side="left")
        self.detect_lbl=tk.Label(fg,text="Load a file to detect BPM and key",font=F_BODY,bg=BG,fg=TEXT_DIM,anchor="w")
        self.detect_lbl.pack(fill="x",pady=(4,0))

        # Pitch shift
        pg=GroupBox(p,"Pitch Shift"); pg.pack(fill="x",padx=10,pady=(0,6))
        pr=tk.Frame(pg,bg=BG); pr.pack(fill="x")
        tk.Label(pr,text="Semitones:",font=F_BODY,bg=BG,fg=TEXT).pack(side="left",padx=(0,4))
        self.semi_var=tk.IntVar(value=0)
        self.semi_scale=tk.Scale(pr,from_=-PITCH_SEMITONE_RANGE,to=PITCH_SEMITONE_RANGE,
            orient="horizontal",variable=self.semi_var,length=200,
            bg=BG,fg=TEXT,troughcolor=TROUGH,highlightthickness=0,font=F_SMALL)
        self.semi_scale.pack(side="left",padx=(0,8))
        tk.Label(pr,text="Target Key:",font=F_BODY,bg=BG,fg=TEXT).pack(side="left",padx=(0,4))
        self.target_key_var=tk.StringVar(value="")
        ClassicCombo(pr,self.target_key_var,["(auto)"]+ALL_KEYS,width=12).pack(side="left",padx=(0,8))
        LimeBtn(pr,"Shift Pitch",self._pitch_shift,width=12).pack(side="left")

        # Time stretch
        tg=GroupBox(p,"Time Stretch"); tg.pack(fill="x",padx=10,pady=(0,6))
        tr=tk.Frame(tg,bg=BG); tr.pack(fill="x")
        tk.Label(tr,text="Rate:",font=F_BODY,bg=BG,fg=TEXT).pack(side="left",padx=(0,4))
        self.rate_var=tk.DoubleVar(value=1.0)
        self.rate_scale=tk.Scale(tr,from_=TEMPO_RANGE[0],to=TEMPO_RANGE[1],resolution=0.01,
            orient="horizontal",variable=self.rate_var,length=200,
            bg=BG,fg=TEXT,troughcolor=TROUGH,highlightthickness=0,font=F_SMALL)
        self.rate_scale.pack(side="left",padx=(0,8))
        tk.Label(tr,text="Target BPM:",font=F_BODY,bg=BG,fg=TEXT).pack(side="left",padx=(0,4))
        self.target_bpm_var=tk.StringVar(value="")
        ClassicEntry(tr,self.target_bpm_var,width=8).pack(side="left",ipady=2,padx=(0,6))
        ClassicBtn(tr,"Calc Rate",self._calc_rate).pack(side="left",padx=(0,8))
        LimeBtn(tr,"Stretch",self._time_stretch,width=10).pack(side="left")

        # Vocal isolation
        vg=GroupBox(p,"Vocal Isolation (Demucs)"); vg.pack(fill="x",padx=10,pady=(0,6))
        vr=tk.Frame(vg,bg=BG); vr.pack(fill="x")
        tk.Label(vr,text="Mode:",font=F_BODY,bg=BG,fg=TEXT).pack(side="left",padx=(0,4))
        self.vocal_mode_var=tk.StringVar(value="Vocals Only")
        ClassicCombo(vr,self.vocal_mode_var,["Vocals Only","Instrumental","Full 4-Stem"],width=14).pack(side="left",padx=(0,8))
        tk.Label(vr,text="Model:",font=F_BODY,bg=BG,fg=TEXT).pack(side="left",padx=(0,4))
        self.demucs_model_var=tk.StringVar(value="htdemucs")
        ClassicCombo(vr,self.demucs_model_var,["htdemucs","htdemucs_ft","mdx_extra"],width=14).pack(side="left",padx=(0,8))
        LimeBtn(vr,"Process",self._vocal_isolate,width=10).pack(side="left")
        self.vocal_status=tk.Label(vg,text="Requires Demucs: pip install demucs",font=F_SMALL,bg=BG,fg=TEXT_DIM,anchor="w")
        self.vocal_status.pack(fill="x",pady=(4,0))

        # Output
        og=GroupBox(p,"Output"); og.pack(fill="x",padx=10,pady=(0,10))
        self.out_lbl=tk.Label(og,text="No output yet",font=F_BODY,bg=BG,fg=TEXT_DIM,anchor="w")
        self.out_lbl.pack(fill="x")
        obr=tk.Frame(og,bg=BG); obr.pack(fill="x",pady=(4,0))
        LimeBtn(obr,"\u25B6 Play",self._play_result,width=10).pack(side="left",padx=(0,6))
        ClassicBtn(obr,"Open Folder",self._open_folder).pack(side="left")
        self.status_lbl=tk.Label(og,text="",font=F_SMALL,bg=BG,fg=TEXT_DIM,anchor="w")
        self.status_lbl.pack(fill="x",pady=(4,0))
        self.prog=ClassicProgress(og); self.prog.pack(fill="x",pady=(4,0))

    def _browse(self):
        f=filedialog.askopenfilename(filetypes=[("Audio","*.mp3 *.wav *.flac *.ogg *.m4a"),("All","*.*")])
        if f: self.file_var.set(f)

    def _detect(self):
        path=self.file_var.get().strip()
        if not path or not os.path.isfile(path):
            self.detect_lbl.config(text="Select a valid audio file",fg=YELLOW); return
        self.detect_lbl.config(text="Analyzing BPM and key...",fg=YELLOW)
        def _do():
            result=analyze_bpm_key(path)
            self._detected_bpm=result.get("bpm")
            self._detected_key=result.get("key")
            if result.get("error"):
                self.after(0,lambda:self.detect_lbl.config(text=f"Error: {result['error']}",fg=RED))
            else:
                self.after(0,lambda:self.detect_lbl.config(
                    text=f"BPM: {self._detected_bpm}  |  Key: {self._detected_key}",fg=LIME_DK))
        threading.Thread(target=_do,daemon=True).start()

    def _pitch_shift(self):
        path=self.file_var.get().strip()
        if not path or not os.path.isfile(path):
            self.status_lbl.config(text="Select a file first",fg=YELLOW); return
        semitones=self.semi_var.get()
        if semitones==0:
            self.status_lbl.config(text="Set semitones != 0",fg=YELLOW); return
        self.status_lbl.config(text=f"Shifting pitch by {semitones:+d} semitones...",fg=YELLOW)
        self.prog["value"]=30
        def _do():
            out,err=pitch_shift_audio(path,semitones)
            if err:
                self.after(0,lambda:(self.status_lbl.config(text=f"Error: {err}",fg=RED),
                    self.prog.configure(value=0)))
            else:
                self._output_file=out
                self.after(0,lambda:(
                    self.out_lbl.config(text=os.path.basename(out),fg=LIME_DK),
                    self.status_lbl.config(text=f"Pitch shifted {semitones:+d} semitones",fg=LIME_DK),
                    self.prog.configure(value=100),
                    self.app.toast(f"Pitch shifted: {os.path.basename(out)}")))
        threading.Thread(target=_do,daemon=True).start()

    def _time_stretch(self):
        path=self.file_var.get().strip()
        if not path or not os.path.isfile(path):
            self.status_lbl.config(text="Select a file first",fg=YELLOW); return
        rate=self.rate_var.get()
        if abs(rate-1.0)<0.01:
            self.status_lbl.config(text="Set rate != 1.0",fg=YELLOW); return
        self.status_lbl.config(text=f"Time stretching at {rate:.2f}x...",fg=YELLOW)
        self.prog["value"]=30
        def _do():
            out,err=time_stretch_audio(path,rate)
            if err:
                self.after(0,lambda:(self.status_lbl.config(text=f"Error: {err}",fg=RED),
                    self.prog.configure(value=0)))
            else:
                self._output_file=out
                self.after(0,lambda:(
                    self.out_lbl.config(text=os.path.basename(out),fg=LIME_DK),
                    self.status_lbl.config(text=f"Stretched at {rate:.2f}x",fg=LIME_DK),
                    self.prog.configure(value=100),
                    self.app.toast(f"Time stretched: {os.path.basename(out)}")))
        threading.Thread(target=_do,daemon=True).start()

    def _calc_rate(self):
        if not self._detected_bpm:
            self.status_lbl.config(text="Detect BPM first",fg=YELLOW); return
        try:
            target=float(self.target_bpm_var.get())
            rate=target/self._detected_bpm
            rate=max(TEMPO_RANGE[0],min(TEMPO_RANGE[1],rate))
            self.rate_var.set(round(rate,2))
            self.status_lbl.config(text=f"Rate: {self._detected_bpm:.1f} BPM → {target:.1f} BPM = {rate:.2f}x",fg=LIME_DK)
        except ValueError:
            self.status_lbl.config(text="Enter a valid target BPM",fg=YELLOW)

    def _vocal_isolate(self):
        path=self.file_var.get().strip()
        if not path or not os.path.isfile(path):
            self.vocal_status.config(text="Select a file first",fg=YELLOW); return
        mode=self.vocal_mode_var.get(); model=self.demucs_model_var.get()
        two_stems=None
        if mode=="Vocals Only": two_stems="vocals"
        elif mode=="Instrumental": two_stems="vocals"
        out_dir=os.path.join(self.app.output_dir,"Stems")
        os.makedirs(out_dir,exist_ok=True)
        self.vocal_status.config(text=f"Running {model} ({mode})... This may take a while.",fg=YELLOW)
        self.prog["value"]=20
        def _do():
            result=run_demucs(path,out_dir,model=model,two_stems=two_stems)
            if result is True:
                track_name=os.path.splitext(os.path.basename(path))[0]
                stem_dir=os.path.join(out_dir,model,track_name)
                if mode=="Vocals Only":
                    vocal_file=os.path.join(stem_dir,"vocals.wav")
                    self._output_file=vocal_file if os.path.exists(vocal_file) else stem_dir
                elif mode=="Instrumental":
                    inst_file=os.path.join(stem_dir,"no_vocals.wav")
                    self._output_file=inst_file if os.path.exists(inst_file) else stem_dir
                else:
                    self._output_file=stem_dir
                self.after(0,lambda:(
                    self.out_lbl.config(text=os.path.basename(str(self._output_file)),fg=LIME_DK),
                    self.vocal_status.config(text=f"Done! Stems in: {stem_dir}",fg=LIME_DK),
                    self.prog.configure(value=100),
                    self.app.toast(f"Vocal isolation complete")))
            else:
                self.after(0,lambda:(
                    self.vocal_status.config(text=f"Error: {str(result)[:80]}",fg=RED),
                    self.prog.configure(value=0)))
        threading.Thread(target=_do,daemon=True).start()

    def _play_result(self):
        if self._output_file and os.path.isfile(self._output_file):
            _audio.load(self._output_file); _audio.play()
            self.status_lbl.config(text="Playing...",fg=LIME_DK)
        else:
            self.status_lbl.config(text="No output file to play",fg=YELLOW)

    def _open_folder(self):
        if self._output_file:
            folder=os.path.dirname(self._output_file) if os.path.isfile(self._output_file) else self._output_file
            open_folder(folder)


# ═══════════════════════════════════════════════════════════════════════════════
# STEM REMIXER PAGE
# ═══════════════════════════════════════════════════════════════════════════════

class RemixerPage(ScrollFrame):
    """Mix Demucs-separated stems with per-stem volume, pan, mute, solo."""
    STEM_COLORS={"vocals":"#2ECC71","drums":"#FD7E14","bass":"#0D6EFD","other":"#6C757D",
                 "piano":"#FFC107","guitar":"#DC3545"}
    def __init__(self,parent,app):
        super().__init__(parent); self.app=app; self._stems={}; self._stem_data={}
        p=self.inner
        tk.Label(p,text="Stem Remixer",font=F_H2,bg=BG,fg=TEXT).pack(anchor="w",padx=SP_LG,pady=(SP_LG,SP_SM))
        tk.Label(p,text="Mix Demucs stems: adjust volume, pan, mute/solo each stem, then export a remix.",
                 font=F_BODY,bg=BG,fg=TEXT_DIM).pack(anchor="w",padx=SP_LG)
        # Browse
        bf=tk.Frame(p,bg=BG); bf.pack(fill="x",padx=SP_LG,pady=SP_MD)
        self.dir_var=tk.StringVar()
        ClassicEntry(bf,self.dir_var,width=50).pack(side="left",fill="x",expand=True,padx=(0,SP_SM))
        LimeBtn(bf,"Browse Stems",self._browse).pack(side="left")
        # Channel strips container
        self._strip_frame=tk.Frame(p,bg=BG); self._strip_frame.pack(fill="x",padx=SP_LG,pady=SP_SM)
        # Master controls
        mg=GroupBox(p,"Master"); mg.pack(fill="x",padx=SP_LG,pady=SP_SM)
        mf=tk.Frame(mg,bg=BG); mf.pack(fill="x")
        tk.Label(mf,text="Master Vol",font=F_BODY,bg=BG,fg=TEXT).pack(side="left")
        self.master_vol=tk.DoubleVar(value=100.0)
        ttk.Scale(mf,from_=0,to=150,variable=self.master_vol,orient="horizontal").pack(side="left",fill="x",expand=True,padx=SP_SM)
        self.master_lbl=tk.Label(mf,text="100%",font=F_MONO,bg=BG,fg=TEXT,width=6)
        self.master_lbl.pack(side="left")
        self.master_vol.trace_add("write",lambda *a:self.master_lbl.config(text=f"{self.master_vol.get():.0f}%"))
        # Buttons
        cf=tk.Frame(p,bg=BG); cf.pack(fill="x",padx=SP_LG,pady=SP_SM)
        LimeBtn(cf,"Preview Mix",self._preview).pack(side="left",padx=(0,SP_SM))
        OrangeBtn(cf,"Export Remix",self._export).pack(side="left",padx=(0,SP_SM))
        self.status_lbl=tk.Label(p,text="Load stems from a Demucs output folder",font=F_BODY,bg=BG,fg=TEXT_DIM)
        self.status_lbl.pack(anchor="w",padx=SP_LG,pady=SP_SM)
        self.prog=ClassicProgress(p); self.prog.pack(fill="x",padx=SP_LG,pady=(0,SP_SM))

    def _browse(self):
        d=filedialog.askdirectory(title="Select Demucs Stems Folder")
        if not d: return
        self.dir_var.set(d)
        # Clear old strips
        for w in self._strip_frame.winfo_children(): w.destroy()
        self._stems={}; self._stem_data={}
        # Find audio files in folder
        found=[]
        for fn in sorted(os.listdir(d)):
            if fn.lower().endswith((".wav",".mp3",".flac",".ogg",".m4a")):
                found.append(fn)
        if not found:
            self.status_lbl.config(text="No audio files found in folder",fg=YELLOW); return
        for fn in found:
            stem_name=os.path.splitext(fn)[0].lower()
            color=self.STEM_COLORS.get(stem_name,"#6C757D")
            sf=tk.Frame(self._strip_frame,bg=SURFACE_2,padx=SP_SM,pady=SP_SM,
                        highlightthickness=1,highlightbackground=CARD_BORDER)
            sf.pack(fill="x",pady=2)
            # Header row
            hf=tk.Frame(sf,bg=SURFACE_2); hf.pack(fill="x")
            tk.Label(hf,text="\u25CF",font=("Segoe UI",12),bg=SURFACE_2,fg=color).pack(side="left")
            tk.Label(hf,text=stem_name.title(),font=F_BOLD,bg=SURFACE_2,fg=TEXT).pack(side="left",padx=SP_SM)
            # Mute/Solo
            mute_var=tk.BooleanVar(value=False)
            solo_var=tk.BooleanVar(value=False)
            tk.Checkbutton(hf,text="M",variable=mute_var,font=F_BTN,bg=SURFACE_2,fg=RED,
                           selectcolor=INPUT_BG,activebackground=SURFACE_2,activeforeground=RED).pack(side="right",padx=2)
            tk.Checkbutton(hf,text="S",variable=solo_var,font=F_BTN,bg=SURFACE_2,fg=YELLOW,
                           selectcolor=INPUT_BG,activebackground=SURFACE_2,activeforeground=YELLOW).pack(side="right",padx=2)
            # Volume
            vf=tk.Frame(sf,bg=SURFACE_2); vf.pack(fill="x")
            tk.Label(vf,text="Vol",font=F_SMALL,bg=SURFACE_2,fg=TEXT_DIM).pack(side="left")
            vol_var=tk.DoubleVar(value=100.0)
            ttk.Scale(vf,from_=0,to=150,variable=vol_var,orient="horizontal").pack(side="left",fill="x",expand=True,padx=SP_XS)
            vol_lbl=tk.Label(vf,text="100%",font=F_MONO,bg=SURFACE_2,fg=TEXT,width=6); vol_lbl.pack(side="left")
            vol_var.trace_add("write",lambda *a,l=vol_lbl,v=vol_var:l.config(text=f"{v.get():.0f}%"))
            # Pan
            pf=tk.Frame(sf,bg=SURFACE_2); pf.pack(fill="x")
            tk.Label(pf,text="Pan",font=F_SMALL,bg=SURFACE_2,fg=TEXT_DIM).pack(side="left")
            pan_var=tk.DoubleVar(value=0.0)
            ttk.Scale(pf,from_=-100,to=100,variable=pan_var,orient="horizontal").pack(side="left",fill="x",expand=True,padx=SP_XS)
            pan_lbl=tk.Label(pf,text="C",font=F_MONO,bg=SURFACE_2,fg=TEXT,width=6); pan_lbl.pack(side="left")
            def _pan_disp(*a,l=pan_lbl,v=pan_var):
                val=v.get()
                l.config(text="C" if abs(val)<5 else f"L{abs(val):.0f}" if val<0 else f"R{val:.0f}")
            pan_var.trace_add("write",_pan_disp)
            self._stems[stem_name]={"file":os.path.join(d,fn),"vol":vol_var,"pan":pan_var,"mute":mute_var,"solo":solo_var}
        self.status_lbl.config(text=f"Loaded {len(found)} stems",fg=LIME_DK)

    def _mix_stems(self):
        """Mix all stems according to current settings. Returns pydub AudioSegment or None."""
        _ensure_pydub()
        if not HAS_PYDUB:
            self.status_lbl.config(text="pydub required (pip install pydub)",fg=RED); return None
        from pydub import AudioSegment
        any_solo=any(s["solo"].get() for s in self._stems.values())
        mixed=None
        for name,s in self._stems.items():
            if s["mute"].get(): continue
            if any_solo and not s["solo"].get(): continue
            try: seg=AudioSegment.from_file(s["file"])
            except Exception as e:
                self.status_lbl.config(text=f"Error loading {name}: {e}",fg=RED); return None
            # Volume
            vol=s["vol"].get()/100.0
            if vol<=0: continue
            seg=seg+( 20*__import__("math").log10(vol) if vol>0 else -120)
            # Pan
            pan_val=s["pan"].get()/100.0
            if abs(pan_val)>0.05: seg=seg.pan(pan_val)
            if mixed is None: mixed=seg
            else:
                # Match lengths
                if len(mixed)<len(seg): mixed=mixed+AudioSegment.silent(duration=len(seg)-len(mixed))
                elif len(seg)<len(mixed): seg=seg+AudioSegment.silent(duration=len(mixed)-len(seg))
                mixed=mixed.overlay(seg)
        if mixed is None:
            self.status_lbl.config(text="No stems to mix (all muted?)",fg=YELLOW); return None
        # Master volume
        mvol=self.master_vol.get()/100.0
        if mvol>0 and abs(mvol-1.0)>0.01:
            mixed=mixed+(20*__import__("math").log10(mvol))
        return mixed

    def _preview(self):
        self.status_lbl.config(text="Mixing...",fg=YELLOW); self.prog["value"]=30
        def _do():
            mixed=self._mix_stems()
            if mixed is None: self.after(0,lambda:self.prog.configure(value=0)); return
            tmp=os.path.join(self.app.output_dir,"_remix_preview.wav")
            mixed.export(tmp,format="wav")
            _audio.load(tmp); _audio.play()
            self.after(0,lambda:(self.status_lbl.config(text="Playing preview...",fg=LIME_DK),self.prog.configure(value=100)))
        threading.Thread(target=_do,daemon=True).start()

    def _export(self):
        mixed=self._mix_stems()
        if mixed is None: return
        path=filedialog.asksaveasfilename(defaultextension=".wav",filetypes=[("WAV","*.wav"),("MP3","*.mp3"),("FLAC","*.flac")])
        if not path: return
        fmt=os.path.splitext(path)[1].lstrip(".") or "wav"
        self.status_lbl.config(text="Exporting...",fg=YELLOW); self.prog["value"]=60
        def _do():
            mixed.export(path,format=fmt)
            self.after(0,lambda:(self.status_lbl.config(text=f"Exported: {os.path.basename(path)}",fg=LIME_DK),
                self.prog.configure(value=100),self.app.toast(f"Remix exported: {os.path.basename(path)}")))
        threading.Thread(target=_do,daemon=True).start()


# ═══════════════════════════════════════════════════════════════════════════════
# BATCH PROCESSOR PAGE
# ═══════════════════════════════════════════════════════════════════════════════

class BatchProcessorPage(ScrollFrame):
    """Apply operations to many audio files at once."""
    def __init__(self,parent,app):
        super().__init__(parent); self.app=app; self._files=[]; self._cancel=False
        p=self.inner
        tk.Label(p,text="Batch Processor",font=F_H2,bg=BG,fg=TEXT).pack(anchor="w",padx=SP_LG,pady=(SP_LG,SP_SM))
        tk.Label(p,text="Apply bulk operations to multiple audio files.",
                 font=F_BODY,bg=BG,fg=TEXT_DIM).pack(anchor="w",padx=SP_LG)
        # File selection
        fg=GroupBox(p,"Files"); fg.pack(fill="x",padx=SP_LG,pady=SP_MD)
        bf=tk.Frame(fg,bg=BG); bf.pack(fill="x")
        LimeBtn(bf,"Add Files",self._add_files).pack(side="left",padx=(0,SP_SM))
        ClassicBtn(bf,"Add Folder",self._add_folder).pack(side="left",padx=(0,SP_SM))
        ClassicBtn(bf,"Clear",self._clear_files).pack(side="left")
        self.file_count_lbl=tk.Label(fg,text="0 files",font=F_BODY,bg=BG,fg=TEXT_DIM)
        self.file_count_lbl.pack(anchor="w",pady=SP_XS)
        self._file_frame,self._file_lb=ClassicListbox(fg,height=6)
        self._file_frame.pack(fill="x",pady=SP_XS)
        # Operations
        og=GroupBox(p,"Operations"); og.pack(fill="x",padx=SP_LG,pady=SP_SM)
        self._op_normalize=tk.BooleanVar(value=False)
        self._op_convert=tk.BooleanVar(value=False)
        self._op_fade_in=tk.BooleanVar(value=False)
        self._op_fade_out=tk.BooleanVar(value=False)
        self._op_trim_silence=tk.BooleanVar(value=False)
        self._op_strip_meta=tk.BooleanVar(value=False)
        # Normalize row
        nf=tk.Frame(og,bg=BG); nf.pack(fill="x",pady=2)
        ClassicCheck(nf,"Normalize LUFS",self._op_normalize).pack(side="left")
        tk.Label(nf,text="Target:",font=F_SMALL,bg=BG,fg=TEXT_DIM).pack(side="left",padx=(SP_LG,SP_XS))
        self.target_lufs=tk.DoubleVar(value=-14.0)
        tk.Spinbox(nf,from_=-60,to=0,increment=0.5,textvariable=self.target_lufs,width=6,
                   font=F_BODY,bg=INPUT_BG,fg=TEXT,relief="flat",bd=0,highlightthickness=1,
                   highlightbackground=INPUT_BORDER).pack(side="left")
        tk.Label(nf,text="LUFS",font=F_SMALL,bg=BG,fg=TEXT_DIM).pack(side="left",padx=SP_XS)
        # Convert row
        cf=tk.Frame(og,bg=BG); cf.pack(fill="x",pady=2)
        ClassicCheck(cf,"Convert Format",self._op_convert).pack(side="left")
        self.out_fmt=tk.StringVar(value="mp3")
        ClassicCombo(cf,self.out_fmt,["mp3","wav","flac","ogg","m4a"],width=8).pack(side="left",padx=(SP_LG,0))
        # Fade rows
        ff=tk.Frame(og,bg=BG); ff.pack(fill="x",pady=2)
        ClassicCheck(ff,"Fade In",self._op_fade_in).pack(side="left")
        self.fade_in_ms=tk.IntVar(value=500)
        tk.Spinbox(ff,from_=0,to=10000,increment=100,textvariable=self.fade_in_ms,width=6,
                   font=F_BODY,bg=INPUT_BG,fg=TEXT,relief="flat",bd=0,highlightthickness=1,
                   highlightbackground=INPUT_BORDER).pack(side="left",padx=(SP_SM,0))
        tk.Label(ff,text="ms",font=F_SMALL,bg=BG,fg=TEXT_DIM).pack(side="left",padx=SP_XS)
        ClassicCheck(ff,"Fade Out",self._op_fade_out).pack(side="left",padx=(SP_LG,0))
        self.fade_out_ms=tk.IntVar(value=500)
        tk.Spinbox(ff,from_=0,to=10000,increment=100,textvariable=self.fade_out_ms,width=6,
                   font=F_BODY,bg=INPUT_BG,fg=TEXT,relief="flat",bd=0,highlightthickness=1,
                   highlightbackground=INPUT_BORDER).pack(side="left",padx=(SP_SM,0))
        tk.Label(ff,text="ms",font=F_SMALL,bg=BG,fg=TEXT_DIM).pack(side="left",padx=SP_XS)
        # Trim & strip
        tf=tk.Frame(og,bg=BG); tf.pack(fill="x",pady=2)
        ClassicCheck(tf,"Trim Silence",self._op_trim_silence).pack(side="left")
        ClassicCheck(tf,"Strip Metadata",self._op_strip_meta).pack(side="left",padx=(SP_LG,0))
        # Output
        ofg=GroupBox(p,"Output"); ofg.pack(fill="x",padx=SP_LG,pady=SP_SM)
        of=tk.Frame(ofg,bg=BG); of.pack(fill="x")
        self.out_dir_var=tk.StringVar(value=os.path.join(app.output_dir,"Batch"))
        ClassicEntry(of,self.out_dir_var,width=50).pack(side="left",fill="x",expand=True,padx=(0,SP_SM))
        ClassicBtn(of,"Browse",self._browse_out).pack(side="left")
        # Process
        pf=tk.Frame(p,bg=BG); pf.pack(fill="x",padx=SP_LG,pady=SP_MD)
        LimeBtn(pf,"Process All",self._process).pack(side="left",padx=(0,SP_SM))
        OrangeBtn(pf,"Cancel",self._cancel_proc).pack(side="left")
        self.status_lbl=tk.Label(p,text="Add files and select operations",font=F_BODY,bg=BG,fg=TEXT_DIM)
        self.status_lbl.pack(anchor="w",padx=SP_LG,pady=SP_XS)
        self.prog=ClassicProgress(p); self.prog.pack(fill="x",padx=SP_LG,pady=(0,SP_SM))

    def _add_files(self):
        fs=filedialog.askopenfilenames(filetypes=[("Audio","*.mp3 *.wav *.flac *.ogg *.m4a *.aac")])
        for f in fs:
            if f not in self._files: self._files.append(f); self._file_lb.insert("end",os.path.basename(f))
        self.file_count_lbl.config(text=f"{len(self._files)} files")

    def _add_folder(self):
        d=filedialog.askdirectory()
        if not d: return
        exts=(".mp3",".wav",".flac",".ogg",".m4a",".aac")
        for fn in sorted(os.listdir(d)):
            fp=os.path.join(d,fn)
            if fn.lower().endswith(exts) and fp not in self._files:
                self._files.append(fp); self._file_lb.insert("end",fn)
        self.file_count_lbl.config(text=f"{len(self._files)} files")

    def _clear_files(self):
        self._files.clear(); self._file_lb.delete(0,"end")
        self.file_count_lbl.config(text="0 files")

    def _browse_out(self):
        d=filedialog.askdirectory()
        if d: self.out_dir_var.set(d)

    def _cancel_proc(self):
        self._cancel=True

    def _process(self):
        if not self._files:
            self.status_lbl.config(text="No files added",fg=YELLOW); return
        _ensure_pydub()
        if not HAS_PYDUB:
            self.status_lbl.config(text="pydub required (pip install pydub)",fg=RED); return
        out_dir=self.out_dir_var.get(); os.makedirs(out_dir,exist_ok=True)
        self._cancel=False
        total=len(self._files)
        def _do():
            from pydub import AudioSegment
            from pydub.silence import detect_leading_silence
            done=0; errors=0
            for i,fp in enumerate(self._files):
                if self._cancel:
                    self.after(0,lambda:(self.status_lbl.config(text="Cancelled",fg=YELLOW),self.prog.configure(value=0)))
                    return
                self.after(0,lambda ii=i:(self.status_lbl.config(text=f"Processing {ii+1}/{total}: {os.path.basename(fp)}",fg=YELLOW),
                    self.prog.configure(value=int(ii/total*100))))
                try:
                    seg=AudioSegment.from_file(fp)
                    # Normalize
                    if self._op_normalize.get() and HAS_FFMPEG:
                        target=self.target_lufs.get()
                        # Simple loudness normalization via pydub dBFS
                        change=target-seg.dBFS
                        seg=seg.apply_gain(change)
                    # Trim silence
                    if self._op_trim_silence.get():
                        start_trim=detect_leading_silence(seg,silence_threshold=-50)
                        end_trim=detect_leading_silence(seg.reverse(),silence_threshold=-50)
                        seg=seg[start_trim:len(seg)-end_trim]
                    # Fades
                    if self._op_fade_in.get(): seg=seg.fade_in(min(self.fade_in_ms.get(),len(seg)))
                    if self._op_fade_out.get(): seg=seg.fade_out(min(self.fade_out_ms.get(),len(seg)))
                    # Output
                    fmt=self.out_fmt.get() if self._op_convert.get() else os.path.splitext(fp)[1].lstrip(".") or "wav"
                    base=os.path.splitext(os.path.basename(fp))[0]
                    out_path=os.path.join(out_dir,f"{base}.{fmt}")
                    tags=None if not self._op_strip_meta.get() else {}
                    seg.export(out_path,format=fmt,tags=tags)
                    done+=1
                except Exception as e:
                    errors+=1
            self.after(0,lambda:(self.status_lbl.config(text=f"Done! {done} processed, {errors} errors",fg=LIME_DK),
                self.prog.configure(value=100),
                self.app.toast(f"Batch: {done}/{total} files processed")))
        threading.Thread(target=_do,daemon=True).start()


# ── Launch ────────────────────────────────────────────────────────────────────
if __name__=="__main__":
    try: app=App(); app.mainloop()
    except Exception as e:
        import traceback
        try: messagebox.showerror("LimeWire Error",traceback.format_exc())
        except Exception: input(f"ERROR: {e}\nPress Enter...")
