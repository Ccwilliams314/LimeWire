#!/usr/bin/env python3
"""
LimeWire v2.0.1 — Studio Edition
The modern music utility for everything. 19-tab cross-platform audio production studio.
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
# Discord Rich Presence
try: from pypresence import Presence as DiscordRPC; HAS_DISCORD_RPC = True
except Exception: HAS_DISCORD_RPC = False; DiscordRPC = None

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

# ── Platform detection ─────────────────────────────────────────────────────────
IS_WINDOWS = sys.platform == "win32"
IS_MACOS = sys.platform == "darwin"
IS_LINUX = sys.platform.startswith("linux")
PLATFORM = "windows" if IS_WINDOWS else ("macos" if IS_MACOS else "linux")

# ═══════════════════════════════════════════════════════════════════════════════
# LIMEWIRE THEME — Light & Dark palettes
# ═══════════════════════════════════════════════════════════════════════════════
THEME_LIGHT={
    "BG":"#F0F2F5","BG_DARK":"#E4E6EA","PANEL":"#FFFFFF","WHITE":"#FFFFFF","BLACK":"#1A1A2E",
    "TEXT":"#1A1A2E","TEXT_DIM":"#4A5568","TEXT_BLUE":"#0A58CA",
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
    "BTN_PRESSED":"#D0D5DD","CARD_SHADOW":"#C8CDD5","DIVIDER":"#E2E6EB","FOCUS_RING":"#0D6EFD",
}
THEME_DARK={
    "BG":"#1A1D21","BG_DARK":"#13161A","PANEL":"#22262B","WHITE":"#2A2E33","BLACK":"#0D0F12",
    "TEXT":"#E8EAED","TEXT_DIM":"#9CA3AF","TEXT_BLUE":"#6EA8FE",
    "LIME":"#2ECC71","LIME_DK":"#27AE60","LIME_LT":"#56D384",
    "BLUE_HL":"#4A90D9","RED":"#EF4444","YELLOW":"#FBBF24","ORANGE":"#F97316",
    "TOOLBAR":"#1E2227","BORDER_L":"#343A40","BORDER_D":"#13161A","INPUT_BG":"#22262B","TROUGH":"#343A40",
    "CARD_BG":"#242930","CARD_BORDER":"#343A40","BTN_HOVER":"#2C3035",
    "LIME_HOVER":"#25A35A","ORANGE_HOVER":"#EA6C0E",
    "INPUT_BORDER":"#343A40","INPUT_FOCUS":"#4A90D9","TAB_ACTIVE":"#2ECC71",
    "SUCCESS":"#2ECC71","WARNING":"#FBBF24","ERROR":"#EF4444","INFO":"#22D3EE",
    "SURFACE":"#22262B","SURFACE_2":"#1A1D21","SURFACE_3":"#13161A",
    "ACCENT_START":"#2ECC71","ACCENT_END":"#1ABC9C",
    "CANVAS_BG":"#0D0F12",
    "BTN_PRESSED":"#1A1D21","CARD_SHADOW":"#0D0F12","DIVIDER":"#2C3035","FOCUS_RING":"#4A90D9",
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
    "BTN_PRESSED":"#21262D","CARD_SHADOW":"#010409","DIVIDER":"#262C36","FOCUS_RING":"#1F6FEB",
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
    "BTN_PRESSED":"#190830","CARD_SHADOW":"#060606","DIVIDER":"#1C1640","FOCUS_RING":"#8C1EFF",
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
    "BTN_PRESSED":"#4A4D62","CARD_SHADOW":"#191A21","DIVIDER":"#383A4A","FOCUS_RING":"#BD93F9",
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
    "BTN_PRESSED":"#333548","CARD_SHADOW":"#11111B","DIVIDER":"#383A4F","FOCUS_RING":"#89B4FA",
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
    "BTN_PRESSED":"#2A3050","CARD_SHADOW":"#0D0E16","DIVIDER":"#2A2F44","FOCUS_RING":"#BB9AF7",
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
    "BTN_PRESSED":"#242424","CARD_SHADOW":"#060606","DIVIDER":"#282828","FOCUS_RING":"#1DB954",
}
THEME_CLASSIC={
    "BG":"#000000","BG_DARK":"#000000","PANEL":"#1A1A1A","WHITE":"#1A1A1A","BLACK":"#000000",
    "TEXT":"#E0E0E0","TEXT_DIM":"#999999","TEXT_BLUE":"#3CFF3C",
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
    "BTN_PRESSED":"#1A1A1A","CARD_SHADOW":"#000000","DIVIDER":"#222222","FOCUS_RING":"#1EFF00",
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
    "BTN_PRESSED":"#353B49","CARD_SHADOW":"#242933","DIVIDER":"#3C4350","FOCUS_RING":"#5E81AC",
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
    "BTN_PRESSED":"#3A3530","CARD_SHADOW":"#1D2021","DIVIDER":"#3C3732","FOCUS_RING":"#458588",
}
THEME_LIVEWIRE={
    "BG":"#080C12","BG_DARK":"#040810","PANEL":"#101820","WHITE":"#142030","BLACK":"#020408",
    "TEXT":"#E0F4FF","TEXT_DIM":"#4A7A90","TEXT_BLUE":"#48F7FF",
    "LIME":"#00E5FF","LIME_DK":"#00B8D4","LIME_LT":"#48F7FF",
    "BLUE_HL":"#0066FF","RED":"#FF1744","YELLOW":"#FFD600","ORANGE":"#FFAB00",
    "TOOLBAR":"#0A1018","BORDER_L":"#1A2A38","BORDER_D":"#040810","INPUT_BG":"#101820","TROUGH":"#1A2A38",
    "CARD_BG":"#121C28","CARD_BORDER":"#1A2A38","BTN_HOVER":"#1A2A38",
    "LIME_HOVER":"#00B8D4","ORANGE_HOVER":"#E09600",
    "INPUT_BORDER":"#1A2A38","INPUT_FOCUS":"#00E5FF","TAB_ACTIVE":"#00E5FF",
    "SUCCESS":"#00E676","WARNING":"#FFD600","ERROR":"#FF1744","INFO":"#48F7FF",
    "SURFACE":"#101820","SURFACE_2":"#080C12","SURFACE_3":"#040810",
    "ACCENT_START":"#00E5FF","ACCENT_END":"#0066FF",
    "CANVAS_BG":"#020408",
    "BTN_PRESSED":"#0A1218","CARD_SHADOW":"#020406","DIVIDER":"#162230","FOCUS_RING":"#00E5FF",
}
THEME_HIGHCONTRAST={
    "BG":"#000000","BG_DARK":"#000000","PANEL":"#0A0A0A","WHITE":"#FFFFFF","BLACK":"#000000",
    "TEXT":"#FFFFFF","TEXT_DIM":"#E0E0E0","TEXT_BLUE":"#00CCFF",
    "LIME":"#00FF00","LIME_DK":"#00CC00","LIME_LT":"#66FF66",
    "BLUE_HL":"#0088FF","RED":"#FF0000","YELLOW":"#FFFF00","ORANGE":"#FF8800",
    "TOOLBAR":"#111111","BORDER_L":"#FFFFFF","BORDER_D":"#FFFFFF","INPUT_BG":"#111111","TROUGH":"#333333",
    "CARD_BG":"#111111","CARD_BORDER":"#FFFFFF","BTN_HOVER":"#333333",
    "LIME_HOVER":"#00AA00","ORANGE_HOVER":"#CC6600",
    "INPUT_BORDER":"#FFFFFF","INPUT_FOCUS":"#00FF00","TAB_ACTIVE":"#00FF00",
    "SUCCESS":"#00FF00","WARNING":"#FFFF00","ERROR":"#FF0000","INFO":"#00CCFF",
    "SURFACE":"#111111","SURFACE_2":"#000000","SURFACE_3":"#000000",
    "ACCENT_START":"#00FF00","ACCENT_END":"#00CCFF",
    "CANVAS_BG":"#000000",
    "BTN_PRESSED":"#222222","CARD_SHADOW":"#000000","DIVIDER":"#444444","FOCUS_RING":"#FFFF00",
}
THEMES={"livewire":THEME_LIVEWIRE,"light":THEME_LIGHT,"dark":THEME_DARK,"modern":THEME_MODERN,
        "synthwave":THEME_SYNTHWAVE,"dracula":THEME_DRACULA,"catppuccin":THEME_CATPPUCCIN,
        "tokyo":THEME_TOKYO,"spotify":THEME_SPOTIFY,"classic":THEME_CLASSIC,
        "nord":THEME_NORD,"gruvbox":THEME_GRUVBOX,"highcontrast":THEME_HIGHCONTRAST}

# Current theme vars — initialized to LiveWire (default)
BG="#080C12"; BG_DARK="#040810"; PANEL="#101820"; WHITE="#142030"; BLACK="#020408"
TEXT="#E0F4FF"; TEXT_DIM="#4A7A90"; TEXT_BLUE="#48F7FF"
LIME="#00E5FF"; LIME_DK="#00B8D4"; LIME_LT="#48F7FF"
BLUE_HL="#0066FF"; RED="#FF1744"; YELLOW="#FFD600"; ORANGE="#FFAB00"
TOOLBAR="#0A1018"; BORDER_L="#1A2A38"; BORDER_D="#040810"; INPUT_BG="#101820"; TROUGH="#1A2A38"
CARD_BG="#121C28"; CARD_BORDER="#1A2A38"; BTN_HOVER="#1A2A38"
LIME_HOVER="#00B8D4"; ORANGE_HOVER="#E09600"
INPUT_BORDER="#1A2A38"; INPUT_FOCUS="#00E5FF"; TAB_ACTIVE="#00E5FF"
SUCCESS="#00E676"; WARNING="#FFD600"; ERROR="#FF1744"; INFO="#48F7FF"
SURFACE="#101820"; SURFACE_2="#080C12"; SURFACE_3="#040810"
BTN_PRESSED="#0A1218"; CARD_SHADOW="#020406"; DIVIDER="#162230"; FOCUS_RING="#00E5FF"
ACCENT_START="#00E5FF"; ACCENT_END="#0066FF"; CANVAS_BG="#020408"

def apply_theme(mode="livewire"):
    """Apply theme palette to module-level color vars."""
    if isinstance(mode,bool): mode="dark" if mode else "light"  # backward compat
    t=THEMES.get(mode,THEME_LIVEWIRE)
    g=globals()
    for k,v in t.items(): g[k]=v
    # Backward-compat defaults for community themes missing new keys
    if "BTN_PRESSED" not in t: g["BTN_PRESSED"]=_lerp_color(g["BTN_HOVER"],"#000000",0.3)
    if "CARD_SHADOW" not in t: g["CARD_SHADOW"]=g["BG_DARK"]
    if "DIVIDER" not in t: g["DIVIDER"]=_lerp_color(g["BORDER_L"],g["BG"],0.5)
    if "FOCUS_RING" not in t: g["FOCUS_RING"]=g["INPUT_FOCUS"]
    # Modern fonts for all themes (Segoe UI everywhere)
    g["F_TITLE"]=("Segoe UI Semibold",20); g["F_LOGO"]=("Segoe UI Black",22)
    g["F_BODY"]=("Segoe UI",11); g["F_BOLD"]=("Segoe UI Semibold",11)
    g["F_SMALL"]=("Segoe UI",9); g["F_BTN"]=("Segoe UI Semibold",10)
    g["F_MONO"]=("Cascadia Code",10); g["F_TAB"]=("Segoe UI Semibold",8)
    g["F_STATUS"]=("Segoe UI",9); g["F_HEADER"]=("Segoe UI Semibold",14)
    g["F_SECTION"]=("Segoe UI Semibold",11)
    g["F_H1"]=("Segoe UI Bold",26); g["F_H2"]=("Segoe UI Semibold",21)
    g["F_H3"]=("Segoe UI Semibold",17); g["F_H4"]=("Segoe UI Semibold",14)
    g["F_CAPTION"]=("Segoe UI",8); g["F_LABEL"]=("Segoe UI Semibold",9)

F_TITLE=("Segoe UI Semibold",20); F_LOGO=("Segoe UI Black",22); F_BODY=("Segoe UI",11)
F_BOLD=("Segoe UI Semibold",11); F_SMALL=("Segoe UI",9); F_BTN=("Segoe UI Semibold",10)
F_MONO=("Cascadia Code",10); F_TAB=("Segoe UI Semibold",8); F_STATUS=("Segoe UI",9)
F_HEADER=("Segoe UI Semibold",14); F_SECTION=("Segoe UI Semibold",11)
F_H1=("Segoe UI Bold",26); F_H2=("Segoe UI Semibold",21)
F_H3=("Segoe UI Semibold",17); F_H4=("Segoe UI Semibold",14)
F_CAPTION=("Segoe UI",8); F_LABEL=("Segoe UI Semibold",9)

# ── Localization / i18n ────────────────────────────────────────────────────────
_LANG_STRINGS={
    "en":{
        "search":"Search","download":"Download","playlist":"Playlist","convert":"Convert",
        "player":"Player","analyze":"Analyze","stems":"Stems","effects":"Effects",
        "library":"Library","samples":"Samples","editor":"Editor","record":"Record",
        "spectro":"Spectrogram","pitch":"Pitch/Time","remix":"Remix","batch":"Batch",
        "schedule":"Schedule","history":"History","cover":"Cover Art",
        "play":"Play","pause":"Pause","stop":"Stop","next":"Next","prev":"Previous",
        "browse":"Browse...","save":"Save","cancel":"Cancel","close":"Close",
        "apply":"Apply","clear":"Clear","add":"Add","remove":"Remove",
        "ready":"Ready","loading":"Loading...","error":"Error","success":"Success",
        "no_file":"No file selected","no_track":"No track loaded",
        "settings":"Settings","about":"About","help":"Help","tools":"Tools","file":"File",
    },
    "es":{
        "search":"Buscar","download":"Descargar","playlist":"Lista","convert":"Convertir",
        "player":"Reproductor","analyze":"Analizar","stems":"Pistas","effects":"Efectos",
        "library":"Biblioteca","samples":"Muestras","editor":"Editor","record":"Grabar",
        "spectro":"Espectro","pitch":"Tono/Tiempo","remix":"Remezcla","batch":"Lote",
        "schedule":"Programar","history":"Historial","cover":"Portada",
        "play":"Reproducir","pause":"Pausa","stop":"Detener","next":"Siguiente","prev":"Anterior",
        "browse":"Examinar...","save":"Guardar","cancel":"Cancelar","close":"Cerrar",
        "apply":"Aplicar","clear":"Limpiar","add":"Agregar","remove":"Eliminar",
        "ready":"Listo","loading":"Cargando...","error":"Error","success":"Éxito",
        "no_file":"Ningún archivo","no_track":"Sin pista","settings":"Ajustes",
        "about":"Acerca de","help":"Ayuda","tools":"Herramientas","file":"Archivo",
    },
    "fr":{
        "search":"Rechercher","download":"Télécharger","playlist":"Playlist","convert":"Convertir",
        "player":"Lecteur","analyze":"Analyser","stems":"Pistes","effects":"Effets",
        "library":"Bibliothèque","samples":"Échantillons","editor":"Éditeur","record":"Enregistrer",
        "spectro":"Spectrogramme","pitch":"Ton/Temps","remix":"Remix","batch":"Lot",
        "schedule":"Planifier","history":"Historique","cover":"Pochette",
        "play":"Lire","pause":"Pause","stop":"Arrêter","next":"Suivant","prev":"Précédent",
        "browse":"Parcourir...","save":"Enregistrer","cancel":"Annuler","close":"Fermer",
        "apply":"Appliquer","clear":"Effacer","add":"Ajouter","remove":"Supprimer",
        "ready":"Prêt","loading":"Chargement...","error":"Erreur","success":"Succès",
        "no_file":"Aucun fichier","no_track":"Aucune piste","settings":"Paramètres",
        "about":"À propos","help":"Aide","tools":"Outils","file":"Fichier",
    },
    "de":{
        "search":"Suchen","download":"Herunterladen","playlist":"Playlist","convert":"Konvertieren",
        "player":"Spieler","analyze":"Analysieren","stems":"Spuren","effects":"Effekte",
        "library":"Bibliothek","samples":"Samples","editor":"Editor","record":"Aufnehmen",
        "spectro":"Spektrogramm","pitch":"Tonhöhe/Zeit","remix":"Remix","batch":"Stapel",
        "schedule":"Planen","history":"Verlauf","cover":"Cover Art",
        "play":"Abspielen","pause":"Pause","stop":"Stopp","next":"Nächster","prev":"Vorheriger",
        "browse":"Durchsuchen...","save":"Speichern","cancel":"Abbrechen","close":"Schließen",
        "apply":"Anwenden","clear":"Löschen","add":"Hinzufügen","remove":"Entfernen",
        "ready":"Bereit","loading":"Laden...","error":"Fehler","success":"Erfolg",
        "no_file":"Keine Datei","no_track":"Kein Titel","settings":"Einstellungen",
        "about":"Über","help":"Hilfe","tools":"Werkzeuge","file":"Datei",
    },
    "ja":{
        "search":"検索","download":"ダウンロード","playlist":"プレイリスト","convert":"変換",
        "player":"プレーヤー","analyze":"分析","stems":"ステム","effects":"エフェクト",
        "library":"ライブラリ","samples":"サンプル","editor":"エディタ","record":"録音",
        "spectro":"スペクトログラム","pitch":"ピッチ/テンポ","remix":"リミックス","batch":"一括処理",
        "schedule":"スケジュール","history":"履歴","cover":"カバーアート",
        "play":"再生","pause":"一時停止","stop":"停止","next":"次へ","prev":"前へ",
        "browse":"参照...","save":"保存","cancel":"キャンセル","close":"閉じる",
        "apply":"適用","clear":"クリア","add":"追加","remove":"削除",
        "ready":"準備完了","loading":"読み込み中...","error":"エラー","success":"成功",
        "no_file":"ファイル未選択","no_track":"トラックなし","settings":"設定",
        "about":"概要","help":"ヘルプ","tools":"ツール","file":"ファイル",
    },
    "pt":{
        "search":"Pesquisar","download":"Baixar","playlist":"Playlist","convert":"Converter",
        "player":"Reprodutor","analyze":"Analisar","stems":"Faixas","effects":"Efeitos",
        "library":"Biblioteca","samples":"Amostras","editor":"Editor","record":"Gravar",
        "spectro":"Espectrograma","pitch":"Tom/Tempo","remix":"Remix","batch":"Lote",
        "schedule":"Agendar","history":"Histórico","cover":"Capa",
        "play":"Tocar","pause":"Pausar","stop":"Parar","next":"Próximo","prev":"Anterior",
        "browse":"Navegar...","save":"Salvar","cancel":"Cancelar","close":"Fechar",
        "apply":"Aplicar","clear":"Limpar","add":"Adicionar","remove":"Remover",
        "ready":"Pronto","loading":"Carregando...","error":"Erro","success":"Sucesso",
        "no_file":"Nenhum arquivo","no_track":"Sem faixa","settings":"Configurações",
        "about":"Sobre","help":"Ajuda","tools":"Ferramentas","file":"Arquivo",
    },
}
_CURRENT_LANG="en"
def _t(key):
    """Get translated string for current language. Falls back to English."""
    return _LANG_STRINGS.get(_CURRENT_LANG,_LANG_STRINGS["en"]).get(key,
           _LANG_STRINGS["en"].get(key,key))
def set_language(lang):
    global _CURRENT_LANG
    if lang in _LANG_STRINGS: _CURRENT_LANG=lang
SUPPORTED_LANGUAGES=list(_LANG_STRINGS.keys())

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
SESSION_FILE=_migrate_config("session")
RECENT_FILES_FILE=_migrate_config("recent_files")
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
# PLUGIN SYSTEM — Custom audio processors loaded from plugins directory
# ═══════════════════════════════════════════════════════════════════════════════

PLUGINS_DIR=os.path.join(os.path.expanduser("~"),".limewire","plugins")

class PluginBase:
    """Base class for LimeWire audio processor plugins.
    Subclass this and implement process(audio_data, sr, **params) → audio_data."""
    name="Unnamed Plugin"
    description=""
    category="Custom"
    parameters={}  # {"param_name": {"type":"float","min":0,"max":1,"default":0.5,"label":"..."}}
    def process(self,audio_data,sr,**params):
        """Process audio data (numpy array) at sample rate sr. Return processed array."""
        return audio_data

class PluginManager:
    """Discovers, loads, and manages audio processor plugins."""
    def __init__(self):
        self._plugins={}  # name → plugin_instance
        self._errors=[]
    def discover(self):
        """Scan plugins directory and load all .py plugin files."""
        self._plugins={}; self._errors=[]
        os.makedirs(PLUGINS_DIR,exist_ok=True)
        for fn in os.listdir(PLUGINS_DIR):
            if not fn.endswith(".py") or fn.startswith("_"): continue
            path=os.path.join(PLUGINS_DIR,fn)
            try:
                import importlib.util
                spec=importlib.util.spec_from_file_location(fn[:-3],path)
                mod=importlib.util.module_from_spec(spec)
                spec.loader.exec_module(mod)
                # Find all PluginBase subclasses in the module
                for attr_name in dir(mod):
                    attr=getattr(mod,attr_name)
                    if isinstance(attr,type) and issubclass(attr,PluginBase) and attr is not PluginBase:
                        inst=attr()
                        self._plugins[inst.name]=inst
                        _log.info(f"Loaded plugin: {inst.name} from {fn}")
            except Exception as e:
                self._errors.append((fn,str(e)))
                _log.warning(f"Failed to load plugin {fn}: {e}")
    def list_plugins(self):
        return list(self._plugins.values())
    def get(self,name):
        return self._plugins.get(name)
    def process(self,name,audio_data,sr,**params):
        plugin=self._plugins.get(name)
        if not plugin: raise ValueError(f"Plugin not found: {name}")
        return plugin.process(audio_data,sr,**params)
    def get_errors(self):
        return list(self._errors)

_plugin_manager=PluginManager()
try: _plugin_manager.discover()
except Exception: pass

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

# ── Cover Art Utilities ──────────────────────────────────────────────────────

def extract_cover_art(filepath):
    """Extract embedded cover art bytes from any audio format.
    Returns (bytes, mime_str) or (None, None)."""
    try:
        audio=mutagen.File(filepath)
        if audio is None: return None,None
        # MP3 / WAV — ID3 APIC
        if hasattr(audio,'tags') and audio.tags:
            for k in audio.tags:
                if str(k).startswith("APIC"):
                    frame=audio.tags[k]
                    return frame.data, getattr(frame,'mime','image/jpeg')
        # FLAC pictures
        if hasattr(audio,'pictures') and audio.pictures:
            pic=audio.pictures[0]
            return pic.data, pic.mime or 'image/jpeg'
        # M4A — covr atom
        if hasattr(audio,'tags') and audio.tags and 'covr' in audio.tags:
            covr=audio.tags['covr']
            if covr: return bytes(covr[0]), 'image/jpeg'
        # OGG — metadata_block_picture
        if hasattr(audio,'tags') and audio.tags and 'metadata_block_picture' in audio:
            import base64
            from mutagen.flac import Picture
            raw=base64.b64decode(audio['metadata_block_picture'][0])
            pic=Picture(raw)
            return pic.data, pic.mime or 'image/jpeg'
    except Exception: pass
    return None,None

def embed_cover_art(filepath, img_bytes, mime='image/jpeg'):
    """Embed cover art into any supported audio file."""
    audio=mutagen.File(filepath)
    if audio is None: raise ValueError(f"Unsupported: {filepath}")
    from mutagen.mp3 import MP3 as _MP3
    from mutagen.flac import FLAC as _FLAC, Picture as _Picture
    from mutagen.mp4 import MP4 as _MP4, MP4Cover as _MP4Cover
    from mutagen.oggvorbis import OggVorbis as _OGG
    from mutagen.wave import WAVE as _WAVE
    import base64
    if isinstance(audio,(_MP3,_WAVE)):
        try: audio.add_tags()
        except Exception: pass
        audio.tags.delall("APIC")
        audio.tags.add(APIC(encoding=3,mime=mime,type=3,desc="Cover",data=img_bytes))
    elif isinstance(audio,_FLAC):
        pic=_Picture(); pic.type=3; pic.mime=mime; pic.desc="Cover"; pic.data=img_bytes
        audio.clear_pictures(); audio.add_picture(pic)
    elif isinstance(audio,_OGG):
        pic=_Picture(); pic.type=3; pic.mime=mime; pic.desc="Cover"; pic.data=img_bytes
        try:
            im=Image.open(BytesIO(img_bytes)); pic.width,pic.height=im.size; pic.depth=24
        except Exception: pic.width=pic.height=500; pic.depth=24
        encoded=base64.b64encode(pic.write()).decode('ascii')
        audio['metadata_block_picture']=[encoded]
    elif isinstance(audio,_MP4):
        fmt=_MP4Cover.FORMAT_PNG if mime=='image/png' else _MP4Cover.FORMAT_JPEG
        audio.tags['covr']=[_MP4Cover(img_bytes,imageformat=fmt)]
    else:
        raise ValueError(f"Unsupported tag type: {type(audio)}")
    audio.save()

def prepare_cover_image(img_bytes, size=500, quality=90):
    """Center-crop to square, resize, return JPEG bytes."""
    img=Image.open(BytesIO(img_bytes)).convert("RGB")
    w,h=img.size; side=min(w,h)
    left=(w-side)//2; top=(h-side)//2
    img=img.crop((left,top,left+side,top+side))
    img=img.resize((size,size),Image.LANCZOS)
    buf=BytesIO(); img.save(buf,format="JPEG",quality=quality); return buf.getvalue()

def fetch_itunes_art(query, size=600):
    """Fetch album art from iTunes Search API (no auth). Returns bytes or None."""
    try:
        url="https://itunes.apple.com/search"
        resp=requests.get(url,params={"term":query,"entity":"album","limit":5},timeout=10)
        if resp.status_code!=200: return None
        for r in resp.json().get("results",[]):
            art_url=r.get("artworkUrl100","")
            if art_url:
                art_url=art_url.replace("100x100bb",f"{size}x{size}bb")
                img_resp=requests.get(art_url,timeout=15)
                if img_resp.status_code==200 and len(img_resp.content)>1000:
                    return img_resp.content
    except Exception: pass
    return None

def fetch_musicbrainz_art(query, size=500):
    """Fetch cover art from MusicBrainz Cover Art Archive (no auth). Returns bytes or None."""
    if not HAS_MUSICBRAINZ: return None
    try:
        results=musicbrainzngs.search_releases(query=query,limit=5)
        for rel in results.get("release-list",[]):
            mbid=rel["id"]
            try:
                data=musicbrainzngs.get_image_front(mbid,size=str(size))
                if data and len(data)>1000: return data
            except Exception: continue
    except Exception: pass
    return None

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

SP_XS=4; SP_SM=8; SP_MD=12; SP_LG=16; SP_XL=24; SP_2XL=32

def _round_rect(cv,x1,y1,x2,y2,radius=10,**kw):
    """Draw a smooth rounded rectangle on a Canvas."""
    r=radius
    pts=[x1+r,y1, x2-r,y1, x2,y1, x2,y1+r,
         x2,y2-r, x2,y2, x2-r,y2, x1+r,y2,
         x1,y2, x1,y2-r, x1,y1+r, x1,y1, x1+r,y1]
    return cv.create_polygon(pts,smooth=True,**kw)

class ModernBtn(tk.Canvas):
    """Canvas-based rounded button with hover/press feedback and smooth transitions."""
    def __init__(self,parent,text="",command=None,width=None,bg_color=None,fg_color=None,
                 hover_color=None,font=None,padx=20,pady=8,radius=10,**kw):
        self._bg_c=bg_color or BG
        self._fg_c=fg_color or TEXT
        self._hover_c=hover_color or BTN_HOVER
        self._font=font or F_BTN
        self._text=text
        self._cmd=command
        self._radius=radius
        self._padx=padx; self._pady=pady
        self._pressed=False; self._animating=False
        _tmp=tk.Label(parent,text=text,font=self._font)
        tw=_tmp.winfo_reqwidth(); th=_tmp.winfo_reqheight(); _tmp.destroy()
        if width: tw=max(tw,width*8)
        cw=tw+padx*2; ch=th+pady*2
        super().__init__(parent,width=cw,height=ch,bg=parent.cget("bg") if hasattr(parent,"cget") else BG,
                         highlightthickness=0,bd=0,cursor="hand2",**kw)
        self._cw=cw; self._ch=ch
        self._outline=_round_rect(self,1,1,cw-1,ch-1,radius=radius,fill="",outline=DIVIDER,width=1)
        self._rect=_round_rect(self,2,2,cw-2,ch-2,radius=max(1,radius-1),fill=self._bg_c,outline="")
        self._label=self.create_text(cw//2,ch//2,text=text,font=self._font,fill=self._fg_c)
        self.tag_raise(self._label)
        self.bind("<Enter>",self._on_enter)
        self.bind("<Leave>",self._on_leave)
        self.bind("<ButtonPress-1>",self._on_press)
        self.bind("<ButtonRelease-1>",self._on_release)

    def _animate_to(self,target,steps=3,step=0):
        if step>=steps:
            self.itemconfig(self._rect,fill=target); self._animating=False; return
        self._animating=True
        current=self.itemcget(self._rect,"fill")
        mid=_lerp_color(current,target,(step+1)/steps)
        self.itemconfig(self._rect,fill=mid)
        self.after(25,lambda:self._animate_to(target,steps,step+1))
    def _on_enter(self,e=None):
        self._animate_to(self._hover_c,steps=3)
    def _on_leave(self,e=None):
        self._pressed=False; self._animate_to(self._bg_c,steps=3)
    def _on_press(self,e=None):
        self._pressed=True
        self.itemconfig(self._rect,fill=BTN_PRESSED)
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
                self.itemconfig(self._rect,fill=SURFACE_2)
                self.itemconfig(self._label,fill=_lerp_color(TEXT_DIM,BG,0.3))
                self.itemconfig(self._outline,outline=DIVIDER)
                self.unbind("<Enter>"); self.unbind("<Leave>"); self.unbind("<ButtonPress-1>"); self.unbind("<ButtonRelease-1>")
                self["cursor"]=""
            else:
                self.itemconfig(self._rect,fill=self._bg_c); self.itemconfig(self._label,fill=self._fg_c)
                self.itemconfig(self._outline,outline=DIVIDER)
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
    return ModernBtn(parent,text=text,command=cmd,width=width,bg_color=SURFACE_2,fg_color=TEXT,hover_color=BTN_HOVER)
def LimeBtn(parent,text,cmd,width=None):
    return ModernBtn(parent,text=text,command=cmd,width=width,bg_color=LIME,fg_color="#000000",hover_color=LIME_HOVER)
def OrangeBtn(parent,text,cmd,width=None):
    return ModernBtn(parent,text=text,command=cmd,width=width,bg_color=ORANGE,fg_color="#FFFFFF",hover_color=ORANGE_HOVER)
def GroupBox(parent,text):
    lf=tk.LabelFrame(parent,text=f"  {text}  ",font=F_SECTION,bg=CARD_BG,fg=TEXT,
                      relief="flat",bd=0,padx=SP_LG,pady=SP_MD,
                      highlightthickness=1,highlightbackground=CARD_BORDER,highlightcolor=CARD_BORDER,
                      labelanchor="nw")
    accent=tk.Frame(lf,bg=LIME,width=4)
    accent.place(x=0,y=8,relheight=0.85)
    return lf
def ClassicEntry(parent,var,width=40,**kw):
    return tk.Entry(parent,textvariable=var,font=F_BODY,bg=INPUT_BG,fg=TEXT,relief="flat",bd=0,
                    insertbackground=LIME,width=width,
                    highlightthickness=2,highlightbackground=INPUT_BORDER,highlightcolor=INPUT_FOCUS,
                    selectbackground=BLUE_HL,selectforeground="#FFFFFF",**kw)
def ClassicCombo(parent,var,values,width=14):
    return ttk.Combobox(parent,textvariable=var,values=values,state="readonly",width=width,font=F_BODY)
def ClassicCheck(parent,text,var):
    return tk.Checkbutton(parent,text=text,variable=var,font=F_BODY,bg=BG,fg=TEXT,activebackground=BG,
                          activeforeground=LIME,selectcolor=SURFACE_2,anchor="w",relief="flat",bd=0,
                          highlightthickness=0,padx=SP_SM,pady=3,indicatoron=True,cursor="hand2")
def ClassicListbox(parent,height=8,**kw):
    f=tk.Frame(parent,bg=INPUT_BORDER,padx=1,pady=1)
    lb=tk.Listbox(f,font=F_BODY,bg=INPUT_BG,fg=TEXT,selectbackground=BLUE_HL,selectforeground="#FFFFFF",
                  relief="flat",height=height,activestyle="none",bd=0,highlightthickness=0,
                  selectborderwidth=0,**kw)
    sb=ttk.Scrollbar(f,orient="vertical",command=lb.yview,style="Vertical.TScrollbar")
    lb.config(yscrollcommand=sb.set)
    sb.pack(side="right",fill="y"); lb.pack(side="left",fill="both",expand=True)
    return f,lb
def ClassicProgress(parent,thin=False):
    style="Thin.Horizontal.TProgressbar" if thin else "Lime.Horizontal.TProgressbar"
    return ttk.Progressbar(parent,style=style,mode="determinate",maximum=100)
def HSep(parent):
    tk.Frame(parent,bg=DIVIDER,height=1).pack(fill="x",pady=SP_SM)
def init_limewire_styles(root):
    s=ttk.Style(root); s.theme_use("clam")
    s.configure("TCombobox",fieldbackground=INPUT_BG,background=SURFACE_2,foreground=TEXT,arrowcolor=TEXT_DIM,
                selectbackground=BLUE_HL,selectforeground="#FFFFFF",bordercolor=INPUT_BORDER,
                borderwidth=1,relief="flat",padding=[10,7])
    s.map("TCombobox",bordercolor=[("focus",INPUT_FOCUS)],lightcolor=[("focus",INPUT_FOCUS)],
          darkcolor=[("focus",INPUT_FOCUS)],
          fieldbackground=[("readonly",INPUT_BG)],foreground=[("readonly",TEXT)])
    root.option_add("*TCombobox*Listbox.background",INPUT_BG)
    root.option_add("*TCombobox*Listbox.foreground",TEXT)
    root.option_add("*TCombobox*Listbox.selectBackground",BLUE_HL)
    root.option_add("*TCombobox*Listbox.selectForeground","#FFFFFF")
    root.option_add("*TCombobox*Listbox.font",F_BODY)
    root.option_add("*Spinbox.background",INPUT_BG)
    root.option_add("*Spinbox.foreground",TEXT)
    root.option_add("*Spinbox.buttonBackground",BG)
    root.option_add("*Spinbox.insertBackground",LIME)
    root.option_add("*Spinbox.selectBackground",BLUE_HL)
    root.option_add("*Spinbox.selectForeground","#FFFFFF")
    s.configure("Lime.Horizontal.TProgressbar",troughcolor=SURFACE_2,background=LIME,
                bordercolor=SURFACE_2,lightcolor=LIME_LT,darkcolor=LIME_DK,thickness=8,borderwidth=0)
    s.configure("Thin.Horizontal.TProgressbar",troughcolor=SURFACE_2,background=LIME,
                bordercolor=SURFACE_2,lightcolor=LIME_LT,darkcolor=LIME_DK,thickness=4,borderwidth=0)
    s.configure("TScale",background=BG,troughcolor=TROUGH,sliderlength=18,sliderrelief="flat",borderwidth=0)
    # Scrollbar theming
    s.configure("TScrollbar",background=_lerp_color(BORDER_L,BG,0.3),troughcolor=SURFACE_3,
                bordercolor=SURFACE_3,arrowcolor=TEXT_DIM,relief="flat",borderwidth=0,width=10)
    s.map("TScrollbar",background=[("active",BORDER_L),("pressed",TEXT_DIM)])
    s.configure("Vertical.TScrollbar",background=_lerp_color(BORDER_L,BG,0.3),
                troughcolor=SURFACE_3,width=10)
    s.map("Vertical.TScrollbar",background=[("active",BORDER_L),("pressed",TEXT_DIM)])
    s.configure("TNotebook",background=BG,borderwidth=0,tabmargins=[0,0,0,0])
    s.configure("TNotebook.Tab",background=BG,foreground=BG,padding=[0,0],width=0,
                font=("Segoe UI",1),borderwidth=0,
                lightcolor=BG,darkcolor=BG,bordercolor=BG,focuscolor=BG)
    s.map("TNotebook.Tab",background=[("selected",BG),("!selected",BG)],
          foreground=[("selected",BG),("!selected",BG)],
          lightcolor=[("selected",BG),("!selected",BG)],
          darkcolor=[("selected",BG),("!selected",BG)],
          bordercolor=[("selected",BG),("!selected",BG)])
    s.configure("Treeview",background=INPUT_BG,foreground=TEXT,fieldbackground=INPUT_BG,
                borderwidth=0,font=F_BODY,rowheight=28,relief="flat")
    s.configure("Treeview.Heading",background=SURFACE_2,foreground=TEXT,font=F_BOLD,borderwidth=0,
                relief="flat",padding=[10,6])
    s.map("Treeview",background=[("selected",BLUE_HL)],foreground=[("selected","#FFFFFF")])
    s.map("Treeview.Heading",background=[("active",BTN_HOVER)])

class ScrollFrame(tk.Frame):
    def __init__(self,parent,**kw):
        super().__init__(parent,bg=BG,**kw)
        self._cv=tk.Canvas(self,bg=BG,highlightthickness=0)
        vsb=ttk.Scrollbar(self,orient="vertical",command=self._cv.yview,style="Vertical.TScrollbar")
        self._cv.configure(yscrollcommand=vsb.set)
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
        f=tk.Frame(tw,bg=SURFACE,padx=SP_MD,pady=SP_SM)
        f.pack(fill="both",expand=True,padx=1,pady=1)
        tk.Label(f,text=self._text,font=F_SMALL,bg=SURFACE,fg=TEXT,wraplength=280,justify="left").pack()
        tw.update_idletasks()
        x=self._w.winfo_rootx()+self._w.winfo_width()//2-tw.winfo_width()//2
        y=self._w.winfo_rooty()+self._w.winfo_height()+6
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
                tx=pw-w-SP_LG; ty=py+56+i*58
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
        self.configure(bg=_lerp_color(_bg,"#000000",0.3))
        inner=tk.Frame(self,bg=_bg); inner.pack(fill="both",expand=True,padx=1,pady=1)
        row=tk.Frame(inner,bg=_bg); row.pack(fill="x",padx=SP_LG,pady=SP_MD)
        ico=icon or "\u2713"
        tk.Label(row,text=ico,font=("Segoe UI Symbol",16),bg=_bg,fg=_fg).pack(side="left",padx=(0,SP_MD))
        tk.Label(row,text=msg,font=F_BOLD,bg=_bg,fg=_fg,wraplength=350,justify="left").pack(side="left",fill="x")
        close_btn=tk.Label(row,text="\u2715",font=F_CAPTION,bg=_bg,
                            fg=_lerp_color(_fg,_bg,0.4),cursor="hand2")
        close_btn.pack(side="right",padx=(SP_SM,0))
        close_btn.bind("<Button-1>",lambda e:self._fade_out(0.8))
        self.update_idletasks()
        pw=parent.winfo_rootx()+parent.winfo_width()
        py=parent.winfo_rooty()
        w=self.winfo_width()
        idx=len(mgr._stack) if mgr else 0
        self._target_x=pw-w-SP_LG; self._start_x=pw+10; self._y=py+56+idx*58
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
    colors={"info":(LIME_DK,"#FFFFFF","\u2713"),"warn":(WARNING,"#000000","\u26A0"),
            "error":(ERROR,"#FFFFFF","\u2717"),"success":(SUCCESS,"#FFFFFF","\u2713")}
    bg,fg,ico=colors.get(level,(LIME_DK,"#FFFFFF","\u2139"))
    _toast_mgr.show(parent,msg,duration,bg,fg,ico)


# ═══════════════════════════════════════════════════════════════════════════════
# COMMAND PALETTE & SHORTCUT REGISTRY
# ═══════════════════════════════════════════════════════════════════════════════

class ShortcutRegistry:
    """Central registry of keyboard shortcuts with help display and customization."""
    def __init__(self):
        self._shortcuts=[]  # [(combo, desc, callback, action_id), ...]
        self._custom_bindings={}  # action_id → custom combo (from settings)
    def register(self,combo,desc,callback,action_id=None):
        aid=action_id or desc.lower().replace(" ","_")
        # Use custom binding if available
        effective=self._custom_bindings.get(aid,combo)
        self._shortcuts.append((effective,desc,callback,aid))
    def load_custom(self,bindings_dict):
        """Load custom keybindings from settings."""
        if bindings_dict: self._custom_bindings=dict(bindings_dict)
    def get_combo(self,action_id):
        for combo,desc,cb,aid in self._shortcuts:
            if aid==action_id: return combo
        return None
    def all(self):
        return [(c,d,cb) for c,d,cb,_ in self._shortcuts]
    def show_help(self,parent):
        w=tk.Toplevel(parent); w.title("Keyboard Shortcuts"); w.geometry("400x420")
        w.configure(bg=BG); w.transient(parent); w.grab_set()
        tk.Label(w,text="Keyboard Shortcuts",font=F_H3,bg=BG,fg=TEXT).pack(pady=(SP_LG,SP_SM))
        f=tk.Frame(w,bg=BG); f.pack(fill="both",expand=True,padx=SP_LG,pady=SP_SM)
        for combo,desc,_,_ in self._shortcuts:
            row=tk.Frame(f,bg=BG); row.pack(fill="x",pady=2)
            tk.Label(row,text=combo,font=F_MONO,bg=SURFACE_2,fg=LIME,padx=SP_SM,pady=2).pack(side="left")
            tk.Label(row,text=desc,font=F_BODY,bg=BG,fg=TEXT).pack(side="left",padx=(SP_SM,0))
        br=tk.Frame(w,bg=BG); br.pack(pady=SP_MD)
        ClassicBtn(br,"Customize...",lambda:[w.destroy(),self.show_customize(parent)]).pack(side="left",padx=(0,8))
        ClassicBtn(br,"Close",w.destroy).pack(side="left")
    def show_customize(self,parent):
        """Show shortcut customization dialog."""
        dlg=tk.Toplevel(parent); dlg.title("Customize Shortcuts"); dlg.geometry("520x500")
        dlg.configure(bg=BG); dlg.transient(parent); dlg.grab_set()
        tk.Label(dlg,text="Customize Keyboard Shortcuts",font=F_H3,bg=BG,fg=TEXT).pack(pady=(SP_LG,SP_SM))
        tk.Label(dlg,text="Click a shortcut to rebind it. Press Escape to cancel.",font=F_SMALL,bg=BG,fg=TEXT_DIM).pack()
        sf=tk.Frame(dlg,bg=BG); sf.pack(fill="both",expand=True,padx=SP_LG,pady=SP_SM)
        cv=tk.Canvas(sf,bg=BG,highlightthickness=0); vsb=tk.Scrollbar(sf,orient="vertical",command=cv.yview)
        cv.configure(yscrollcommand=vsb.set); vsb.pack(side="right",fill="y"); cv.pack(side="left",fill="both",expand=True)
        inner=tk.Frame(cv,bg=BG); cv.create_window((0,0),window=inner,anchor="nw")
        inner.bind("<Configure>",lambda e:cv.configure(scrollregion=cv.bbox("all")))
        entries={}
        for combo,desc,cb,aid in self._shortcuts:
            row=tk.Frame(inner,bg=BG); row.pack(fill="x",pady=2)
            tk.Label(row,text=desc,font=F_BODY,bg=BG,fg=TEXT,width=25,anchor="w").pack(side="left")
            var=tk.StringVar(value=combo)
            ent=tk.Entry(row,textvariable=var,font=F_MONO,bg=INPUT_BG,fg=LIME,width=18,relief="flat",bd=0,
                         insertbackground=TEXT,highlightthickness=2,highlightbackground=INPUT_BORDER,highlightcolor=INPUT_FOCUS)
            ent.pack(side="left",padx=SP_SM)
            entries[aid]=var
            def _capture(e,entry=ent,v=var):
                parts=[]
                if e.state & 0x4: parts.append("Ctrl")
                if e.state & 0x8: parts.append("Alt")
                if e.state & 0x1: parts.append("Shift")
                key=e.keysym
                if key in ("Control_L","Control_R","Alt_L","Alt_R","Shift_L","Shift_R"): return
                if key=="Escape": entry.selection_clear(); return
                parts.append(key.capitalize() if len(key)==1 else key)
                v.set("+".join(parts))
                entry.selection_clear(); dlg.focus_set()
                return "break"
            ent.bind("<KeyPress>",_capture)
        def _save():
            new_binds={}
            for aid,var in entries.items():
                new_binds[aid]=var.get()
            self._custom_bindings=new_binds
            # Save to app settings
            if hasattr(parent,"settings"):
                parent.settings["custom_shortcuts"]=new_binds
                parent._save_settings()
            # Rebuild bindings
            if hasattr(parent,"_rebind_shortcuts"):
                parent._rebind_shortcuts()
            show_toast(parent,"Shortcuts saved — restart for full effect","info")
            dlg.destroy()
        def _reset():
            self._custom_bindings={}
            if hasattr(parent,"settings"):
                parent.settings.pop("custom_shortcuts",None)
                parent._save_settings()
            if hasattr(parent,"_rebind_shortcuts"):
                parent._rebind_shortcuts()
            show_toast(parent,"Shortcuts reset to defaults","info")
            dlg.destroy()
        br=tk.Frame(dlg,bg=BG); br.pack(pady=SP_MD)
        LimeBtn(br,"Save",_save).pack(side="left",padx=(0,8))
        OrangeBtn(br,"Reset Defaults",_reset).pack(side="left",padx=(0,8))
        ClassicBtn(br,"Cancel",dlg.destroy).pack(side="left")

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
        self.title("LimeWire 2.0.1 Studio Edition"); self.minsize(760,700)
        # Fit window to screen
        sw,sh=self.winfo_screenwidth(),self.winfo_screenheight()
        w,h=min(820,sw-40),min(960,sh-80)
        self.geometry(f"{w}x{h}")
        self.configure(bg=BG)
        self._apply_dark_titlebar()
        self._lock=threading.Lock(); self._sched_lock=threading.Lock()
        self._completed=0; self._total=0; self._cancel=threading.Event()
        self._dark_mode=False
        self.settings=load_json(SETTINGS_FILE,{"clipboard_watch":True,"proxy":"","rate_limit":""})
        # Restore language
        set_language(self.settings.get("language","en"))
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
        self._restore_session()
        self._init_discord_rpc()
        self.protocol("WM_DELETE_WINDOW",self._on_close)
        # Minimize to taskbar instead of quitting on X (Shift+X to actually close)
        self.bind("<Shift-Escape>",lambda e:self._on_close())
    def _save_session(self):
        """Save current session state (loaded files per tab, active tab, player playlist)."""
        session={"active_tab":self._get_active_tab(),"files":{},"player_playlist":[]}
        for name,page in self.pages.items():
            if hasattr(page,"file_var"):
                v=page.file_var.get()
                if v: session["files"][name]=v
        pp=self.pages.get("player")
        if pp: session["player_playlist"]=list(pp._playlist)
        save_json(SESSION_FILE,session)
    def _restore_session(self):
        """Restore session state from previous launch."""
        session=load_json(SESSION_FILE,{})
        if not session: return
        # Restore file_vars
        for name,path in session.get("files",{}).items():
            page=self.pages.get(name)
            if page and hasattr(page,"file_var") and os.path.exists(path):
                page.file_var.set(path)
        # Restore player playlist
        pp=self.pages.get("player")
        if pp:
            for path in session.get("player_playlist",[]):
                if os.path.exists(path) and path not in pp._playlist_set:
                    pp._playlist.append(path); pp._playlist_set.add(path)
                    pp.plb.insert("end",os.path.basename(path))
        # Restore active tab
        tab=session.get("active_tab","")
        if tab: self.after(100,lambda:self._show_tab(tab))
    def _apply_dark_titlebar(self):
        """Use Windows DWM API to set dark title bar matching theme."""
        if sys.platform!="win32": return
        try:
            import ctypes
            hwnd=ctypes.windll.user32.GetParent(self.winfo_id())
            DWMWA_USE_IMMERSIVE_DARK_MODE=20
            val=ctypes.c_int(1 if self._dark_mode else 0)
            ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd,DWMWA_USE_IMMERSIVE_DARK_MODE,ctypes.byref(val),ctypes.sizeof(val))
        except Exception: pass
    def _on_close(self):
        """Clean shutdown: save session, stop audio, cancel pending work, destroy."""
        self._save_session()
        self._cancel.set()
        self._close_discord_rpc()
        try: _audio.stop()
        except Exception: pass
        self.destroy()
    def _init_discord_rpc(self):
        """Initialize Discord Rich Presence connection (optional)."""
        self._discord_rpc=None
        if not HAS_DISCORD_RPC or not self.settings.get("discord_rpc",True): return
        def _connect():
            try:
                # LimeWire Discord Application ID (placeholder — replace with real app ID)
                rpc=DiscordRPC("1234567890123456789")
                rpc.connect()
                self._discord_rpc=rpc
                self._update_discord_rpc("Idle","LimeWire Studio Edition")
            except Exception: self._discord_rpc=None
        threading.Thread(target=_connect,daemon=True).start()
    def _update_discord_rpc(self,state,details,large_text="LimeWire"):
        """Update Discord Rich Presence status."""
        if not self._discord_rpc: return
        try:
            self._discord_rpc.update(state=state,details=details[:128],
                large_image="limewire_logo",large_text=large_text,
                start=int(time.time()))
        except Exception: self._discord_rpc=None  # Disconnected
    def _close_discord_rpc(self):
        if self._discord_rpc:
            try: self._discord_rpc.close()
            except Exception: pass
    def _bind_shortcuts(self):
        self._shortcut_reg=ShortcutRegistry()
        sr=self._shortcut_reg
        # Load custom bindings from settings
        sr.load_custom(self.settings.get("custom_shortcuts",{}))
        sr.register("Ctrl+D","Download / Grab URL",lambda:self.pages["search"]._grab(),"grab_url")
        sr.register("Ctrl+O","Open downloads folder",self._open_dl_folder,"open_folder")
        sr.register("Space","Play / Pause",lambda:self._space_toggle(None),"play_pause")
        sr.register("Ctrl+K","Command Palette",lambda:CommandPalette(self),"command_palette")
        sr.register("Ctrl+?","Show shortcuts",lambda:self._shortcut_reg.show_help(self),"show_shortcuts")
        sr.register("Ctrl+Right","Next track",lambda:self._media_next(),"next_track")
        sr.register("Ctrl+Left","Previous track",lambda:self._media_prev(),"prev_track")
        sr.register("Ctrl+Up","Volume up",lambda:self._media_vol(5),"vol_up")
        sr.register("Ctrl+Down","Volume down",lambda:self._media_vol(-5),"vol_down")
        sr.register("Left","Seek back 5s (Player)",lambda:self._player_seek(-5),"seek_back")
        sr.register("Right","Seek forward 5s (Player)",lambda:self._player_seek(5),"seek_fwd")
        sr.register("Shift+Left","Seek back 15s (Player)",lambda:self._player_seek(-15),"seek_back_long")
        sr.register("Shift+Right","Seek forward 15s (Player)",lambda:self._player_seek(15),"seek_fwd_long")
        sr.register("Tab","Focus next widget",lambda:self._focus_cycle(1),"focus_next")
        sr.register("Shift+Tab","Focus previous widget",lambda:self._focus_cycle(-1),"focus_prev")
        sr.register("Enter","Trigger primary action",lambda:self._primary_action(),"primary_action")
        self._apply_bindings()
    def _apply_bindings(self):
        """Apply actual tk bindings from registry."""
        self.bind("<Control-d>",lambda e:self.pages["search"]._grab())
        self.bind("<Control-o>",lambda e:self._open_dl_folder())
        self.bind("<space>",lambda e:self._space_toggle(e))
        self.bind("<Control-k>",lambda e:CommandPalette(self))
        self.bind("<Control-question>",lambda e:self._shortcut_reg.show_help(self))
        self.bind("<Control-Right>",lambda e:self._media_next())
        self.bind("<Control-Left>",lambda e:self._media_prev())
        self.bind("<Control-Up>",lambda e:self._media_vol(5))
        self.bind("<Control-Down>",lambda e:self._media_vol(-5))
        # Arrow key seeking (only when not in a text widget)
        self.bind("<Left>",lambda e:self._arrow_key(e,-5))
        self.bind("<Right>",lambda e:self._arrow_key(e,5))
        self.bind("<Shift-Left>",lambda e:self._arrow_key(e,-15))
        self.bind("<Shift-Right>",lambda e:self._arrow_key(e,15))
        # Tab/Shift+Tab focus cycling
        self.bind_all("<Tab>",self._on_tab_key)
        self.bind_all("<Shift-Tab>",self._on_shift_tab_key)
        # Enter for primary action (only outside text inputs)
        self.bind("<Return>",self._on_enter_key)
    def _rebind_shortcuts(self):
        """Rebuild shortcut registry from saved settings and re-apply bindings."""
        self._bind_shortcuts()
    def _arrow_key(self,e,delta):
        """Arrow key handler: seek if Player is active, otherwise ignore."""
        if isinstance(e.widget,(tk.Entry,ttk.Entry,ttk.Combobox,tk.Text,tk.Listbox,tk.Spinbox)): return
        if self._get_active_tab()=="player":
            self._player_seek(delta)
            return "break"
    def _player_seek(self,delta):
        """Seek player by delta seconds."""
        pp=self.pages.get("player")
        if pp and pp._playing and pp._dur>0:
            cur_pos=_audio.get_pos()
            new_pos=max(0,min(pp._dur,cur_pos+delta))
            _audio.play(start=new_pos)
            pp._playing=True; pp.play_b.config(text="Pause")
    def _on_tab_key(self,e):
        """Tab key: cycle focus to next interactive widget in current page."""
        if isinstance(e.widget,(tk.Text,)): return  # let Text handle Tab normally
        self._focus_cycle(1)
        return "break"
    def _on_shift_tab_key(self,e):
        """Shift+Tab: cycle focus to previous interactive widget in current page."""
        if isinstance(e.widget,(tk.Text,)): return
        self._focus_cycle(-1)
        return "break"
    def _focus_cycle(self,direction):
        """Cycle focus through interactive widgets in the active page."""
        tab=self._get_active_tab()
        page=self.pages.get(tab)
        if not page: return
        # Collect focusable widgets
        focusable=[]
        def _collect(w):
            for child in w.winfo_children():
                if isinstance(child,(tk.Entry,ttk.Entry,ttk.Combobox,tk.Spinbox,tk.Listbox)):
                    focusable.append(child)
                elif isinstance(child,ModernBtn):
                    focusable.append(child)
                elif isinstance(child,(tk.Button,ttk.Button)):
                    focusable.append(child)
                elif isinstance(child,(ttk.Scale,)):
                    focusable.append(child)
                _collect(child)
        _collect(page)
        if not focusable: return
        cur=self.focus_get()
        try: idx=focusable.index(cur)
        except (ValueError,Exception): idx=-1 if direction==1 else len(focusable)
        nxt=(idx+direction)%len(focusable)
        focusable[nxt].focus_set()
    def _on_enter_key(self,e):
        """Enter key: trigger primary action of active page, unless in text input."""
        if isinstance(e.widget,(tk.Entry,ttk.Entry,ttk.Combobox,tk.Text,tk.Listbox,tk.Spinbox)): return
        self._primary_action()
    def _primary_action(self):
        """Execute the primary action for the currently active page."""
        tab=self._get_active_tab()
        page=self.pages.get(tab)
        if not page: return
        # Map of page → primary action method
        actions={
            "search":"_grab","download":"_start_batch","playlist":"_fetch",
            "converter":"_convert","player":"_toggle","analyze":"_analyze",
            "stems":"_separate","effects":"_apply","discovery":"_scan",
            "samples":"_preview_sel","editor":"_export",
            "recorder":"_toggle_rec","spectrogram":"_generate",
            "pitchtime":"_apply","remixer":"_export",
            "batch":"_run","schedule":"_add","history":"_redownload",
            "coverart":"_apply_selected"
        }
        method_name=actions.get(tab)
        if method_name and hasattr(page,method_name):
            getattr(page,method_name)()
    def _space_toggle(self,e):
        if e and isinstance(e.widget,(tk.Entry,ttk.Entry,ttk.Combobox,tk.Text,tk.Listbox,tk.Spinbox)): return
        pp=self.pages.get("player")
        if pp: pp._toggle()
    def _media_next(self):
        pp=self.pages.get("player")
        if pp: pp._next()
    def _media_prev(self):
        pp=self.pages.get("player")
        if pp: pp._prev()
    def _media_vol(self,delta):
        pp=self.pages.get("player")
        if pp and hasattr(pp,"vol"):
            v=max(0,min(100,pp.vol.get()+delta))
            pp.vol.set(v); _audio.set_volume(v/100)
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
                page.file_var.set(path); self._add_recent_file(path)
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

    def _add_recent_file(self,path):
        """Track recently opened files (max 15)."""
        if not path or not os.path.exists(path): return
        recent=load_json(RECENT_FILES_FILE,[])
        if path in recent: recent.remove(path)
        recent.insert(0,path)
        save_json(RECENT_FILES_FILE,recent[:15])
        if hasattr(self,"_recent_menu"): self._refresh_recent_menu()
    def _refresh_recent_menu(self):
        self._recent_menu.delete(0,"end")
        recent=load_json(RECENT_FILES_FILE,[])
        if not recent:
            self._recent_menu.add_command(label="(none)",state="disabled")
            return
        for path in recent[:10]:
            name=os.path.basename(path)
            self._recent_menu.add_command(label=name,command=lambda p=path:self._open_recent(p))
        self._recent_menu.add_separator()
        self._recent_menu.add_command(label="Clear Recent",command=lambda:(save_json(RECENT_FILES_FILE,[]),self._refresh_recent_menu()))
    def _open_recent(self,path):
        """Open a recent file in the active tab or player."""
        if not os.path.exists(path): show_toast(self,"File not found","warning"); return
        active=self._get_active_tab()
        page=self.pages.get(active)
        if page and hasattr(page,"file_var"):
            page.file_var.set(path)
            if hasattr(page,"_load"): self.after(50,page._load)
            elif hasattr(page,"_load_file"): self.after(50,page._load_file)
        else:
            pp=self.pages.get("player")
            if pp and path not in pp._playlist_set:
                pp._playlist.append(path); pp._playlist_set.add(path)
                pp.plb.insert("end",os.path.basename(path))
            self._show_tab("player")
    def _build_menubar(self):
        mb=tk.Menu(self,font=F_BODY,bg=BG)
        fm=tk.Menu(mb,tearoff=0,font=F_BODY)
        fm.add_command(label="Open Downloads Folder",command=self._open_dl_folder)
        # Recent Files submenu
        self._recent_menu=tk.Menu(fm,tearoff=0,font=F_BODY)
        fm.add_cascade(label="Recent Files",menu=self._recent_menu)
        self._refresh_recent_menu()
        fm.add_separator(); fm.add_command(label="Exit",command=self.destroy)
        mb.add_cascade(label="File",menu=fm)
        tm=tk.Menu(mb,tearoff=0,font=F_BODY)
        tm.add_command(label="Clear History",command=lambda:(self.history.clear(),save_json(HISTORY_FILE,[])) if messagebox.askyesno("Clear","Clear?") else None)
        tm.add_separator()
        tm.add_command(label="Cycle Theme (Light/Dark/Modern)",command=self._toggle_dark_mode)
        tm.add_command(label="Check yt-dlp Update",command=self._check_ytdlp_update)
        tm.add_command(label="Check App Update",command=self._check_app_update)
        tm.add_separator()
        tm.add_command(label="Cloud Sync → Export",command=self._cloud_sync_export)
        tm.add_command(label="Cloud Sync → Import",command=self._cloud_sync_import)
        tm.add_separator()
        tm.add_command(label="Open Plugins Folder",command=lambda:open_folder(PLUGINS_DIR))
        tm.add_separator()
        # Language submenu
        lm=tk.Menu(tm,tearoff=0,font=F_BODY)
        lang_names={"en":"English","es":"Español","fr":"Français","de":"Deutsch","ja":"日本語","pt":"Português"}
        for code in SUPPORTED_LANGUAGES:
            lm.add_command(label=lang_names.get(code,code),
                command=lambda c=code:[set_language(c),self.settings.__setitem__("language",c),self._save_settings(),
                    show_toast(self,f"Language: {lang_names.get(c,c)} (restart for full effect)","info")])
        tm.add_cascade(label="Language",menu=lm)
        tm.add_command(label="Load Community Theme",command=self._load_community_theme)
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
            f"LimeWire v2.0.1 Studio Edition\n\n"
            f"The modern music utility for everything.\n"
            f"Powered by yt-dlp + Demucs + librosa + pydub\n\n"
            f"19 pages: Search, Batch DL, Playlist, Convert, Player,\n"
            f"Analyze, Stems, Effects, Discovery, Samples, Editor,\n"
            f"Recorder, Spectrogram, Pitch/Time, Remixer, Batch Process,\n"
            f"Scheduler, History, Cover Art\n\n"
            f"Active modules: {cap_str}\n\n"
            f"v2.0: Plugin system, VST3/AU hosting, MIDI mapping,\n"
            f"cloud sync, auto-update, SoundCloud/Bandcamp search,\n"
            f"Discord RPC, keyboard customization, arrow seek,\n"
            f"13 themes + community themes, 6 languages.\n\n"
            f"Optional: pip install librosa pyloudnorm demucs pydub\n"
            f"  sounddevice pyrubberband openai-whisper shazamio pypresence mido\n\n"
            f"\"Definitely virus-free since 2024\""))
        mb.add_cascade(label="Help",menu=hm)
        self.config(menu=mb)

    def _build_logo_bar(self):
        LOGO_H=52
        bar=tk.Canvas(self,height=LOGO_H,highlightthickness=0,bd=0); bar.pack(fill="x")
        def _draw_gradient(e=None):
            w=bar.winfo_width(); h=LOGO_H
            bar.delete("grad")
            steps=max(1,w//3)
            for i in range(steps):
                t=i/max(1,steps-1); t=t*t*(3-2*t)  # smoothstep
                c=_lerp_color(ACCENT_START,ACCENT_END,t)
                x=int(i*w/steps); x2=int((i+1)*w/steps)+1
                bar.create_rectangle(x,0,x2,h,fill=c,outline="",tags="grad")
            bar.create_rectangle(0,h-1,w,h,fill=_lerp_color(ACCENT_END,"#000000",0.4),outline="",tags="grad")
            bar.tag_lower("grad")
            bar.delete("fg")
            cx,cy=30,LOGO_H//2
            bar.create_oval(cx-17,cy-17,cx+17,cy+17,fill="",
                            outline=_lerp_color(ACCENT_START,"#FFFFFF",0.3),width=2,tags="fg")
            bar.create_oval(cx-13,cy-13,cx+13,cy+13,
                            fill=_lerp_color(ACCENT_START,"#000000",0.2),outline="",tags="fg")
            bar.create_text(cx,cy,text="\u26A1",font=("Segoe UI",14),fill="#FFFFFF",tags="fg")
            tx=56; ty=LOGO_H//2
            bar.create_text(tx+1,ty+1,text="LimeWire",font=F_LOGO,
                            fill=_lerp_color(ACCENT_END,"#000000",0.5),anchor="w",tags="fg")
            bar.create_text(tx,ty,text="LimeWire",font=F_LOGO,fill="#FFFFFF",anchor="w",tags="fg")
            bx=200; by=LOGO_H//2
            _round_rect(bar,bx,by-11,bx+82,by+11,radius=11,
                         fill=_lerp_color(ACCENT_START,"#000000",0.35),
                         outline=_lerp_color(ACCENT_START,"#FFFFFF",0.15),tags="fg")
            bar.create_text(bx+41,by,text="v2.0.1 Studio",font=("Segoe UI Semibold",8),fill="#FFFFFF",tags="fg")
            sx=w-90; sy=LOGO_H//2
            self._status_x=sx; self._status_y=sy
            bar.create_oval(sx-4,sy-4,sx+4,sy+4,fill=SUCCESS,outline="",tags=("fg","status_dot"))
            bar.create_text(sx+12,sy,text="Ready",font=F_CAPTION,
                            fill=_lerp_color("#FFFFFF",ACCENT_END,0.15),anchor="w",tags="fg")
        bar.bind("<Configure>",_draw_gradient)
        self._logo_bar=bar
        self._pulse_status()

    def _pulse_status(self):
        try:
            bar=self._logo_bar
            dot=bar.find_withtag("status_dot")
            if dot:
                cur=bar.itemcget(dot[0],"fill")
                bright=_lerp_color(SUCCESS,"#FFFFFF",0.4)
                nxt=bright if cur==SUCCESS else SUCCESS
                bar.itemconfig(dot[0],fill=nxt)
        except Exception: pass
        self.after(STATUS_PULSE_MS,self._pulse_status)

    def _build_toolbar(self):
        tk.Frame(self,bg=DIVIDER,height=1).pack(fill="x")
        tb=tk.Frame(self,bg=TOOLBAR,height=44); tb.pack(fill="x"); tb.pack_propagate(False)
        self._toolbar=tb
        self._tb_btns={}
        items=[("search","\u2315","Search"),("download","\u2913","Batch"),
               ("playlist","\u2630","Playlist"),("converter","\u21C4","Convert"),
               ("player","\u25B6","Player"),("analyze","\u2261","Analyze"),
               ("stems","\u2632","Stems"),("effects","\u2726","Effects"),
               ("discovery","\u25CE","Library"),("samples","\u2B22","Samples"),
               ("editor","\u2702","Editor"),("recorder","\u25CF","Record"),
               ("spectrogram","\u2248","Spectro"),("pitchtime","\u266B","Pitch"),
               ("remixer","\u2725","Remix"),("batch","\u2699","Batch"),
               ("schedule","\u25F7","Schedule"),("history","\u21BA","History"),
               ("coverart","\u25A3","Cover")]
        for name,icon,label in items:
            bf=tk.Frame(tb,bg=TOOLBAR,cursor="hand2")
            bf.pack(side="left",padx=2,pady=(3,0))
            il=tk.Label(bf,text=icon,font=("Segoe UI Symbol",13),bg=TOOLBAR,fg=TEXT_DIM)
            il.pack(side="top",pady=(0,0))
            nl=tk.Label(bf,text=label,font=F_TAB,bg=TOOLBAR,fg=TEXT_DIM)
            nl.pack(side="top")
            ind=tk.Frame(bf,bg=TOOLBAR,height=3); ind.pack(fill="x",side="bottom",pady=(1,0))
            self._tb_btns[name]=(bf,il,nl,ind)
            ToolTip(bf,f"Go to {label}")
            for w in (bf,il,nl):
                w.bind("<Button-1>",lambda e,n=name:self._show_tab(n))
                w.bind("<Enter>",lambda e,n=name:self._tb_hover(n,True))
                w.bind("<Leave>",lambda e,n=name:self._tb_hover(n,False))
        tk.Frame(self,bg=DIVIDER,height=1).pack(fill="x")

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
                                ("schedule","Schedule",SchedulerPage),("history","History",HistoryPage),
                                ("coverart","Cover Art",CoverArtPage)]:
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
        tk.Frame(self,bg=DIVIDER,height=1).pack(fill="x",side="bottom")
        sb=tk.Frame(self,bg=SURFACE_3,height=26); sb.pack(fill="x",side="bottom"); sb.pack_propagate(False)
        self.status_lbl=tk.Label(sb,text="Ready  |  Ctrl+D: Download  Space: Play/Pause  Ctrl+O: Open Folder",font=F_STATUS,bg=SURFACE_3,fg=TEXT_DIM,anchor="w")
        self.status_lbl.pack(side="left",padx=10,fill="x",expand=True)
        tk.Frame(sb,bg=DIVIDER,width=1).pack(side="left",fill="y",pady=5)
        self.dl_count_lbl=tk.Label(sb,text=f"\u2193 {len(self.history)}",font=F_STATUS,bg=SURFACE_3,fg=TEXT,padx=10)
        self.dl_count_lbl.pack(side="left")
        tk.Frame(sb,bg=DIVIDER,width=1).pack(side="left",fill="y",pady=5)
        mod_map={"FFmpeg":HAS_FFMPEG,"BPM/Key":HAS_LIBROSA,"LUFS":HAS_LOUDNESS,
                 "Shazam":HAS_SHAZAM or HAS_SHAZAM_SEARCH,
                 "MusicBrainz":HAS_MB,"Chromaprint":HAS_ACOUSTID,"Demucs":HAS_DEMUCS,
                 "FL Studio":HAS_PYFLP,"Serato":HAS_SERATO,
                 "pydub":HAS_PYDUB,"SoundDevice":HAS_SOUNDDEVICE,
                 "Whisper":HAS_WHISPER,"Rubberband":HAS_RUBBERBAND}
        loaded=sum(mod_map.values()); total=len(mod_map)
        missing=[k for k,v in mod_map.items() if not v]
        tip=f"Missing: {', '.join(missing)}" if missing else "All modules loaded"
        color=SUCCESS if loaded>=int(total*0.8) else WARNING if loaded>=int(total*0.5) else ERROR
        mod_lbl=tk.Label(sb,text=f"\u25CF {loaded}/{total}",font=F_STATUS,bg=SURFACE_3,fg=color,padx=10,cursor="hand2")
        mod_lbl.pack(side="left")
        mod_lbl.bind("<Button-1>",lambda e:messagebox.showinfo("Module Status",
            "\n".join(f"{'\u2713' if v else '\u2717'} {k}" for k,v in mod_map.items())+"\n\n"+tip))

    def set_status(self,text): self.status_lbl.config(text=text)
    def toast(self,msg,level="info"): show_toast(self,msg,level)
    def add_history(self,entry):
        self.history.insert(0,entry); save_json(HISTORY_FILE,self.history[:HISTORY_MAX])
        self.dl_count_lbl.config(text=f"\u2193 {len(self.history)}")
    def _open_dl_folder(self):
        os.makedirs(self.output_dir,exist_ok=True); open_folder(self.output_dir)
    def _toggle_dark_mode(self):
        cycle=["livewire","light","dark","modern","synthwave","dracula","catppuccin","tokyo","spotify","classic","nord","gruvbox","highcontrast"]
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
               "nord":"Nord","gruvbox":"Gruvbox","highcontrast":"High Contrast"}
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
                        widget.configure(bg=CARD_BG,fg=TEXT,highlightbackground=CARD_BORDER,highlightcolor=CARD_BORDER)
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
                try: widget.configure(bg=BG,fg=TEXT,activebackground=BG,activeforeground=LIME,selectcolor=SURFACE_2)
                except Exception: pass
            elif wtype=="Radiobutton":
                try: widget.configure(bg=BG,fg=TEXT,activebackground=BG,activeforeground=LIME,selectcolor=SURFACE_2)
                except Exception: pass
            elif wtype=="Entry":
                try: widget.configure(bg=INPUT_BG,fg=TEXT,insertbackground=LIME,
                                      highlightbackground=INPUT_BORDER,highlightcolor=INPUT_FOCUS,
                                      selectbackground=BLUE_HL,selectforeground="#FFFFFF")
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
                    new_bg=_remap(widget._bg_c)
                    new_fg=_remap(widget._fg_c)
                    new_hv=_remap(widget._hover_c)
                    if new_bg: widget._bg_c=new_bg; widget.itemconfig(widget._rect,fill=new_bg)
                    if new_fg: widget._fg_c=new_fg; widget.itemconfig(widget._label,fill=new_fg)
                    if new_hv: widget._hover_c=new_hv
                    try: widget.itemconfig(widget._outline,outline=DIVIDER)
                    except Exception: pass
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
    def _load_community_theme(self):
        """Load a community theme from a JSON file."""
        f=filedialog.askopenfilename(filetypes=[("Theme JSON","*.json"),("All","*.*")],title="Load Community Theme")
        if not f: return
        try:
            data=load_json(f)
            if not isinstance(data,dict) or "BG" not in data:
                show_toast(self,"Invalid theme file — must have BG, TEXT, LIME, etc. keys","error"); return
            # Register theme with a custom name
            name=os.path.splitext(os.path.basename(f))[0].lower().replace(" ","_")
            # Ensure required keys exist (fill from dark theme)
            for k,v in THEME_DARK.items():
                if k not in data: data[k]=v
            THEMES[name]=data
            # Apply it
            old=THEMES.get(self.settings.get("theme","livewire"),THEME_DARK)
            apply_theme(name); self._dark_mode=True
            new=data
            self.settings["theme"]=name; self._save_settings()
            cmap={v.lower():new[k].lower() for k,v in old.items() if isinstance(v,str) and v.startswith("#")}
            init_limewire_styles(self); self._reconfig_all(self,cmap)
            if hasattr(self,"_logo_bar"): self._logo_bar.event_generate("<Configure>")
            show_toast(self,f"Theme loaded: {name}","success")
        except Exception as e:
            show_toast(self,f"Theme error: {str(e)[:60]}","error")
    def _check_app_update(self):
        """Check GitHub for newer LimeWire releases."""
        self.set_status("Checking for updates...")
        def _check():
            try:
                resp=requests.get("https://api.github.com/repos/Ccwilliams314/LimeWire/releases/latest",timeout=10)
                if resp.status_code==200:
                    data=resp.json(); tag=data.get("tag_name","")
                    current="v2.0.1"
                    if tag and tag>current:
                        url=data.get("html_url","")
                        self.after(0,lambda:show_toast(self,f"Update available: {tag}\nVisit GitHub to download","warn",8000))
                    else:
                        self.after(0,lambda:show_toast(self,f"LimeWire {current} is up to date","info"))
                self.after(0,lambda:self.set_status("Ready"))
            except Exception as e:
                self.after(0,lambda:show_toast(self,f"Update check failed: {str(e)[:50]}","error"))
        threading.Thread(target=_check,daemon=True).start()
    def _cloud_sync_export(self):
        """Export settings and history to a sync-friendly directory."""
        sync_dir=self.settings.get("cloud_sync_dir","")
        if not sync_dir:
            sync_dir=filedialog.askdirectory(title="Select Cloud Sync Folder (Dropbox/OneDrive/Google Drive)")
            if not sync_dir: return
            self.settings["cloud_sync_dir"]=sync_dir; self._save_settings()
        os.makedirs(sync_dir,exist_ok=True)
        # Export settings, history, analysis cache, shortcuts
        for name,src in [("settings",SETTINGS_FILE),("history",HISTORY_FILE),
                          ("schedule",SCHEDULE_FILE),("analysis_cache",ANALYSIS_CACHE_FILE)]:
            data=load_json(src,{} if name!="history" else [])
            save_json(os.path.join(sync_dir,f"limewire_{name}.json"),data)
        show_toast(self,"Settings exported to cloud sync folder","success")
    def _cloud_sync_import(self):
        """Import settings and history from a cloud sync directory."""
        sync_dir=self.settings.get("cloud_sync_dir","")
        if not sync_dir:
            sync_dir=filedialog.askdirectory(title="Select Cloud Sync Folder")
            if not sync_dir: return
        imported=0
        for name,dest in [("settings",SETTINGS_FILE),("history",HISTORY_FILE),
                          ("schedule",SCHEDULE_FILE),("analysis_cache",ANALYSIS_CACHE_FILE)]:
            src=os.path.join(sync_dir,f"limewire_{name}.json")
            if os.path.exists(src):
                data=load_json(src)
                if data: save_json(dest,data); imported+=1
        if imported:
            self.settings=load_json(SETTINGS_FILE,self.settings)
            self.history=load_json(HISTORY_FILE,[])
            show_toast(self,f"Imported {imported} files from cloud sync","success")
        else:
            show_toast(self,"No sync files found in folder","warning")
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
        self.clip_lbl=tk.Label(p,text="  Tip: Paste URL, or type sc:query / bc:query / yt:query to search",font=F_SMALL,bg=CARD_BG,fg=TEXT_DIM,
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
        elif url.startswith("sc:"):
            self.url_indicator.config(fg=LIME_DK)
            self.clip_lbl.config(text=f"  SoundCloud search: {url[3:].strip()}",fg=ORANGE)
        elif url.startswith("bc:"):
            self.url_indicator.config(fg=LIME_DK)
            self.clip_lbl.config(text=f"  Bandcamp search: {url[3:].strip()}",fg=ORANGE)
        elif url.startswith("yt:"):
            self.url_indicator.config(fg=LIME_DK)
            self.clip_lbl.config(text=f"  YouTube search: {url[3:].strip()}",fg=ORANGE)
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
            self.url_indicator.config(fg=YELLOW)
            self.clip_lbl.config(text=f"  Will search YouTube for: {url[:50]}",fg=TEXT_DIM)
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
        if not url: return
        # Support search queries: "sc:query" for SoundCloud, "bc:query" for Bandcamp, "yt:query" for YouTube
        if url.startswith("sc:"):
            url=f"scsearch:{url[3:].strip()}"
        elif url.startswith("bc:"):
            url=f"bcsearch:{url[3:].strip()}"
        elif url.startswith("yt:"):
            url=f"ytsearch:{url[3:].strip()}"
        elif "http" not in url and not url.startswith(("scsearch:","bcsearch:","ytsearch:")):
            # Treat bare text as YouTube search
            url=f"ytsearch:{url}"
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
        ClassicBtn(ibr,"Write Tags to File",self._write_tags).pack(side="left",padx=(0,6))
        self._auto_tag=tk.BooleanVar(value=False)
        tk.Checkbutton(ibr,text="Auto-tag after analysis",variable=self._auto_tag,font=F_SMALL,
                       bg=BG,fg=TEXT,selectcolor=INPUT_BG,activebackground=BG,activeforeground=TEXT).pack(side="left")

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
        ClassicBtn(er,"Export CSV",self._export_csv).pack(side="left",padx=(0,6))
        OrangeBtn(er,"Share as Image Card",self._export_image_card).pack(side="left")

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
        # Auto-tag if enabled
        if hasattr(self,"_auto_tag") and self._auto_tag.get():
            self.after(200,self._write_tags)

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
        if not path or not os.path.exists(path):
            messagebox.showinfo("LimeWire","Select an audio file first."); return
        title=self._id_res["Identified Title"].cget("text")
        artist=self._id_res["Identified Artist"].cget("text")
        bpm_str=self._res["BPM"].cget("text")
        key_str=self._res["Key"].cget("text")
        genre=self._id_res["Genre"].cget("text") if "Genre" in self._id_res else ""
        try:
            audio=mutagen.File(path)
            if audio is None: self.status_lbl.config(text="Unsupported format",fg=RED); return
            from mutagen.mp3 import MP3 as _MP3; from mutagen.flac import FLAC as _FLAC
            from mutagen.mp4 import MP4 as _MP4; from mutagen.wave import WAVE as _WAVE
            ext=os.path.splitext(path)[1].lower()
            if isinstance(audio,(_MP3,_WAVE)):
                # ID3 tags
                try: audio.add_tags()
                except Exception: pass
                tags=audio.tags or audio
                if title and title!="--": tags["TIT2"]=TIT2(encoding=3,text=title)
                if artist and artist!="--": tags["TPE1"]=TPE1(encoding=3,text=artist)
                if bpm_str and bpm_str!="--":
                    try: tags["TBPM"]=TBPM(encoding=3,text=str(int(float(bpm_str))))
                    except Exception: pass
                if key_str and key_str!="--": tags["TKEY"]=TKEY(encoding=3,text=key_str)
                if genre and genre!="--": tags["TCON"]=TCON(encoding=3,text=genre)
            elif isinstance(audio,(_FLAC,)) or ext in (".ogg",".opus"):
                # Vorbis comments
                if title and title!="--": audio["TITLE"]=[title]
                if artist and artist!="--": audio["ARTIST"]=[artist]
                if bpm_str and bpm_str!="--": audio["BPM"]=[str(int(float(bpm_str)))]
                if key_str and key_str!="--": audio["KEY"]=[key_str]
                if genre and genre!="--": audio["GENRE"]=[genre]
            elif isinstance(audio,_MP4):
                # MP4 atoms
                if title and title!="--": audio.tags["\u00a9nam"]=[title]
                if artist and artist!="--": audio.tags["\u00a9ART"]=[artist]
                if bpm_str and bpm_str!="--":
                    try: audio.tags["tmpo"]=[int(float(bpm_str))]
                    except Exception: pass
                if genre and genre!="--": audio.tags["\u00a9gen"]=[genre]
            audio.save()
            self.status_lbl.config(text=f"Tags written to {ext.upper().lstrip('.')} file",fg=LIME_DK)
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

    def _export_image_card(self):
        """Export analysis results as a shareable PNG image card."""
        data=self._get_results_dict()
        if not data.get("file"):
            messagebox.showinfo("LimeWire","Analyze a file first."); return
        path=filedialog.asksaveasfilename(defaultextension=".png",filetypes=[("PNG","*.png")],
            initialfile=os.path.splitext(os.path.basename(data["file"]))[0]+"_card.png")
        if not path: return
        try:
            from PIL import Image,ImageDraw,ImageFont
            W,H=600,400; card=Image.new("RGB",(W,H),"#1a1a2e")
            draw=ImageDraw.Draw(card)
            # Gradient header bar
            for y in range(80):
                r=int(50+y*1.2); g=int(180-y*0.5); b=int(80+y*0.3)
                draw.line([(0,y),(W,y)],fill=(r,g,b))
            # Text
            try: font_lg=ImageFont.truetype("segoeui.ttf",28)
            except Exception: font_lg=ImageFont.load_default()
            try: font_md=ImageFont.truetype("segoeui.ttf",18)
            except Exception: font_md=font_lg
            try: font_sm=ImageFont.truetype("segoeui.ttf",14)
            except Exception: font_sm=font_md
            # Title
            title=os.path.splitext(os.path.basename(data["file"]))[0][:40]
            draw.text((20,20),title,fill="#FFFFFF",font=font_lg)
            draw.text((20,55),"LimeWire Analysis",fill="#80ffaa",font=font_sm)
            # Results
            y=100; items=[("BPM",data.get("bpm","--")),("Key",data.get("key","--")),
                          ("Camelot",data.get("camelot","--")),("Loudness",f"{data.get('lufs','--')} LUFS"),
                          ("True Peak",f"{data.get('true_peak','--')} dBFS"),
                          ("Duration",data.get("duration","--")),("Sample Rate",data.get("sample_rate","--"))]
            for label,val in items:
                draw.text((30,y),f"{label}:",fill="#aaaaaa",font=font_md)
                draw.text((200,y),str(val),fill="#FFFFFF",font=font_md)
                y+=36
            # Footer
            draw.text((20,H-30),"Generated by LimeWire Studio Edition",fill="#555555",font=font_sm)
            # Embed album art if available
            fp=data.get("file","")
            art_data,_=extract_cover_art(fp) if fp else (None,None)
            if art_data:
                try:
                    art=Image.open(BytesIO(art_data)).convert("RGB").resize((120,120),Image.LANCZOS)
                    card.paste(art,(460,100))
                    draw.rectangle([(459,99),(581,221)],outline="#80ffaa",width=2)
                except Exception: pass
            card.save(path); self.status_lbl.config(text=f"Image card saved: {os.path.basename(path)}",fg=LIME_DK)
            show_toast(self.app,"Analysis card exported","success")
        except Exception as e:
            messagebox.showerror("Export Error",str(e))

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
        OrangeBtn(bf,"Batch Split",self._batch_run,width=14).pack(side="left",padx=(0,8))
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

    def _batch_run(self):
        """Queue multiple files for stem separation."""
        files=filedialog.askopenfilenames(filetypes=[("Audio","*.mp3 *.wav *.flac *.ogg *.m4a"),("All","*.*")])
        if not files: return
        if self._running: show_toast(self.app,"Separation already running","warning"); return
        self._running=True
        model=self.model_var.get(); mode=self.stems_mode.get()
        two_stems=None if mode=="all" else mode
        out=self.out_var.get()
        total=len(files)
        self.stem_status.config(text=f"Batch: 0/{total} files processed...",fg=YELLOW)
        self.stem_prog.configure(value=0)
        def _do_batch():
            ok=0; fail=0
            for i,path in enumerate(files):
                name=os.path.basename(path)
                self.after(0,lambda i=i,n=name:self.stem_status.config(text=f"Batch [{i+1}/{total}]: {n}...",fg=YELLOW))
                try:
                    result=run_demucs(path,out,model,two_stems)
                    if result is True: ok+=1
                    else: fail+=1
                except Exception: fail+=1
                self.after(0,lambda p=int(((i+1)/total)*100):self.stem_prog.configure(value=p))
            msg=f"Batch done — {ok} succeeded"+(f", {fail} failed" if fail else "")
            self.after(0,lambda:(self.stem_status.config(text=msg,fg=LIME_DK if fail==0 else YELLOW),
                self.app.set_status(msg)))
            self._running=False
        threading.Thread(target=_do_batch,daemon=True).start()
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
        self.art=tk.Label(nr,bg=CARD_BG,width=200,height=200,text="\u266A",font=("Segoe UI",32),fg=TEXT_DIM,
                          relief="groove",bd=1,cursor="hand2")
        self.art.pack(side="left",padx=(0,12))
        self.art.bind("<Button-1>",self._show_fullsize_art)
        self._art_data=None
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
        OrangeBtn(pr,"Share JSON",self._share_playlist_json).pack(side="left",padx=(0,4))
        ClassicBtn(pr,"Import JSON",self._import_playlist_json).pack(side="left",padx=(0,4))
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
        self.art.config(image="",text="\u266A",width=200,height=200); self._art_data=None
        try:
            mf=mutagen.File(path)
            if mf and mf.info: self._dur=mf.info.length
            else: self._dur=0
            # Extract artist from any format
            artist=""
            if hasattr(mf,'tags') and mf.tags:
                for key in ["TPE1","artist","ARTIST","Author","\u00a9ART"]:
                    if key in mf.tags:
                        val=mf.tags[key]
                        artist=str(val[0]) if isinstance(val,list) else str(val)
                        break
            if artist: self.np_a.config(text=artist)
            self.dur_l.config(text=fmt_duration(self._dur)); self.seek.config(to=self._dur)
            # Album art — use universal extractor (MP3/FLAC/OGG/M4A/WAV)
            art_data,_=extract_cover_art(path)
            if art_data:
                self._art_data=art_data
                with Image.open(BytesIO(art_data)) as raw:
                    img=raw.convert("RGB"); img.thumbnail((200,200),Image.LANCZOS)
                ph=ImageTk.PhotoImage(img); self.art.config(image=ph,text="",width=200,height=200); self.art._img=ph
        except Exception: self._dur=0
        # Generate waveform in background
        threading.Thread(target=self._gen_wave,args=(path,),daemon=True).start()
        try:
            _audio.load(path); _audio.set_volume(self.vol.get()/100); _audio.play(); self._playing=True; self.play_b.config(text="Pause")
            show_toast(self.app,f"Now Playing: {name}","info")
            self.app._update_discord_rpc(f"Playing: {name[:60]}",f"LimeWire Studio — {fmt_duration(self._dur)}")
            self.app._add_recent_file(path)
        except Exception as e: messagebox.showerror("LimeWire",str(e))
        # Up Next indicator
        nxt_idx=idx+1
        if nxt_idx<len(self._playlist):
            nxt_name=os.path.splitext(os.path.basename(self._playlist[nxt_idx]))[0]
            self._upnext_lbl.config(text=f"Up Next: {nxt_name}")
        else:
            self._upnext_lbl.config(text="")
    def _show_fullsize_art(self,e=None):
        if not self._art_data: return
        dlg=tk.Toplevel(self); dlg.title("Album Art"); dlg.configure(bg=BG)
        try:
            img=Image.open(BytesIO(self._art_data)).convert("RGB")
            w,h=img.size; scale=min(600/w,600/h,1.0)
            img=img.resize((int(w*scale),int(h*scale)),Image.LANCZOS)
            ph=ImageTk.PhotoImage(img)
            lbl=tk.Label(dlg,image=ph,bg=BG); lbl._img=ph; lbl.pack(padx=8,pady=8)
            dlg.geometry(f"{int(w*scale)+16}x{int(h*scale)+16}")
        except Exception:
            tk.Label(dlg,text="Cannot display image",font=F_BODY,bg=BG,fg=RED).pack(padx=20,pady=20)
        dlg.bind("<Escape>",lambda e:dlg.destroy())
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
    def _share_playlist_json(self):
        """Export collaborative playlist as shareable JSON with metadata."""
        if not self._playlist: return
        cache=load_json(ANALYSIS_CACHE_FILE,{})
        tracks=[]
        for fp in self._playlist:
            entry={"path":fp,"filename":os.path.basename(fp)}
            # Try to add metadata
            try:
                mf=mutagen.File(fp)
                if mf:
                    if hasattr(mf,"tags") and mf.tags:
                        for k in mf.tags:
                            if "TIT2" in str(k): entry["title"]=str(mf.tags[k])
                            if "TPE1" in str(k): entry["artist"]=str(mf.tags[k])
                    if hasattr(mf,"info"): entry["duration"]=round(getattr(mf.info,"length",0),1)
            except Exception: pass
            # Add analysis data if available
            mtime=os.path.getmtime(fp) if os.path.exists(fp) else 0
            cache_key=f"{fp}|{mtime}"
            if cache_key in cache:
                cd=cache[cache_key]
                entry["bpm"]=cd.get("bpm"); entry["key"]=cd.get("key"); entry["camelot"]=cd.get("camelot")
            tracks.append(entry)
        playlist_data={"version":"1.0","app":"LimeWire Studio","created":datetime.datetime.now().isoformat(),
                       "track_count":len(tracks),"tracks":tracks}
        path=filedialog.asksaveasfilename(defaultextension=".json",filetypes=[("JSON Playlist","*.json")],
            initialfile="limewire_playlist.json")
        if path:
            save_json(path,playlist_data)
            self.app.toast(f"Shared playlist: {len(tracks)} tracks","success")
    def _import_playlist_json(self):
        """Import collaborative playlist from shared JSON."""
        path=filedialog.askopenfilename(filetypes=[("JSON Playlist","*.json"),("All","*.*")])
        if not path: return
        try:
            data=load_json(path,{})
            tracks=data.get("tracks",[])
            added=0
            for t in tracks:
                fp=t.get("path","")
                if fp and os.path.exists(fp) and fp not in self._playlist_set:
                    self._playlist.append(fp); self._playlist_set.add(fp)
                    name=t.get("title") or os.path.basename(fp)
                    bpm=t.get("bpm",""); key=t.get("key","")
                    label=f"{name}"
                    if bpm: label+=f" [{bpm}bpm]"
                    if key: label+=f" ({key})"
                    self.plb.insert("end",label)
                    added+=1
            src_info=f" from {data.get('app','unknown')}" if data.get("app") else ""
            self.app.toast(f"Imported {added} tracks{src_info}","success")
        except Exception as e:
            self.app.toast(f"Import error: {str(e)[:50]}","error")

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
        ClassicBtn(hdr,"Batch Rename",self._batch_rename).pack(side="right",padx=(4,0))
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
    def _batch_rename(self):
        """Batch rename downloaded files using a pattern template."""
        # Collect files that exist
        files=[]
        for entry in self.app.history:
            fp=entry.get("filepath","")
            if fp and os.path.exists(fp): files.append((entry,fp))
        if not files:
            show_toast(self.app,"No existing files in history","warning"); return
        dlg=tk.Toplevel(self); dlg.title("Batch Rename"); dlg.geometry("550x420")
        dlg.configure(bg=BG); dlg.transient(self); dlg.grab_set()
        tk.Label(dlg,text="Rename Pattern",font=F_HEADER,bg=BG,fg=TEXT).pack(pady=(10,4))
        tk.Label(dlg,text="Tokens: {title} {artist} {bpm} {key} {date} {n} {ext}",
                 font=F_SMALL,bg=BG,fg=TEXT_DIM).pack()
        pat_var=tk.StringVar(value="{title} - {artist}.{ext}")
        ClassicEntry(dlg,pat_var,width=50).pack(padx=20,pady=6,ipady=2)
        tk.Label(dlg,text="Preview (first 8 files):",font=F_BOLD,bg=BG,fg=TEXT).pack(anchor="w",padx=20)
        preview_lb=tk.Listbox(dlg,font=F_MONO,bg=INPUT_BG,fg=TEXT,height=8,relief="flat",bd=1)
        preview_lb.pack(fill="both",expand=True,padx=20,pady=4)
        def _preview(*_):
            preview_lb.delete(0,"end")
            pat=pat_var.get()
            for i,(entry,fp) in enumerate(files[:8]):
                ext=os.path.splitext(fp)[1].lstrip(".")
                title=entry.get("title","Unknown")[:40]
                artist=""
                try:
                    mf=mutagen.File(fp)
                    if mf and hasattr(mf,'tags') and mf.tags:
                        for k in ["TPE1","artist","ARTIST","\u00a9ART"]:
                            if k in mf.tags:
                                v=mf.tags[k]; artist=str(v[0]) if isinstance(v,list) else str(v); break
                except Exception: pass
                # Check analysis cache for BPM/key
                bpm=""; key=""
                cache=load_json(ANALYSIS_CACHE_FILE,{})
                ckey=f"{fp}|{os.path.getmtime(fp):.0f}" if os.path.exists(fp) else ""
                if ckey in cache:
                    bpm=str(int(cache[ckey].get("bpm",0))) if cache[ckey].get("bpm") else ""
                    key=cache[ckey].get("key","")
                date=entry.get("date","")[:10]
                new_name=pat.replace("{title}",title).replace("{artist}",artist or "Unknown")
                new_name=new_name.replace("{bpm}",bpm or "0").replace("{key}",key or "?")
                new_name=new_name.replace("{date}",date).replace("{n}",str(i+1)).replace("{ext}",ext)
                # Sanitize
                new_name=re.sub(r'[/<>:"|?*]','_',new_name)
                old=os.path.basename(fp)
                preview_lb.insert("end",f"{old[:25]:25s} \u2192 {new_name}")
        pat_var.trace_add("write",_preview); _preview()
        def _apply():
            renamed=0
            for i,(entry,fp) in enumerate(files):
                ext=os.path.splitext(fp)[1].lstrip(".")
                title=entry.get("title","Unknown")[:40]; artist=""; bpm=""; key=""
                try:
                    mf=mutagen.File(fp)
                    if mf and hasattr(mf,'tags') and mf.tags:
                        for k in ["TPE1","artist","ARTIST","\u00a9ART"]:
                            if k in mf.tags:
                                v=mf.tags[k]; artist=str(v[0]) if isinstance(v,list) else str(v); break
                except Exception: pass
                cache=load_json(ANALYSIS_CACHE_FILE,{})
                ckey=f"{fp}|{os.path.getmtime(fp):.0f}" if os.path.exists(fp) else ""
                if ckey in cache:
                    bpm=str(int(cache[ckey].get("bpm",0))) if cache[ckey].get("bpm") else ""
                    key=cache[ckey].get("key","")
                date=entry.get("date","")[:10]; pat=pat_var.get()
                new_name=pat.replace("{title}",title).replace("{artist}",artist or "Unknown")
                new_name=new_name.replace("{bpm}",bpm or "0").replace("{key}",key or "?")
                new_name=new_name.replace("{date}",date).replace("{n}",str(i+1)).replace("{ext}",ext)
                new_name=re.sub(r'[/<>:"|?*]','_',new_name)
                new_path=os.path.join(os.path.dirname(fp),new_name)
                if new_path!=fp and not os.path.exists(new_path):
                    try: os.rename(fp,new_path); entry["filepath"]=new_path; renamed+=1
                    except Exception: pass
            save_json(HISTORY_FILE,self.app.history)
            dlg.destroy(); self.refresh()
            show_toast(self.app,f"Renamed {renamed}/{len(files)} files","success")
        LimeBtn(dlg,"Rename All",_apply).pack(pady=8)


# ═══════════════════════════════════════════════════════════════════════════════
# EFFECTS PAGE — Pedalboard effects chain
# ═══════════════════════════════════════════════════════════════════════════════

class EffectsPage(ScrollFrame):
    """Pedalboard effects chain processor for audio files."""
    def __init__(self,parent,app):
        super().__init__(parent); self.app=app; self._chain=[]; self._undo_stack=[]; self._redo_stack=[]
        self._build(self.inner)
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
        # Add loaded plugins to effects list
        for p in _plugin_manager.list_plugins():
            plugin_label=f"\U0001F9E9 {p.name}"
            if plugin_label not in self._fx_names: self._fx_names.append(plugin_label)
        self._fx_var=tk.StringVar(value="Compressor")
        ClassicCombo(ar,self._fx_var,self._fx_names,width=16).pack(side="left",padx=(0,6))
        LimeBtn(ar,"Add",self._add_fx).pack(side="left",padx=(0,6))
        OrangeBtn(ar,"Clear All",self._clear_fx).pack(side="left",padx=(0,6))
        ClassicBtn(ar,"Save Preset",self._save_preset).pack(side="left",padx=(0,6))
        ClassicBtn(ar,"Load Preset",self._load_preset).pack(side="left",padx=(0,6))
        ClassicBtn(ar,"\u21a9 Undo",self._undo).pack(side="left",padx=(0,6))
        ClassicBtn(ar,"\u21aa Redo",self._redo).pack(side="left",padx=(0,6))

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
        OrangeBtn(abr,"Load VST3 Plugin",self._load_vst).pack(side="left",padx=(0,8))
        ClassicBtn(abr,"Reload Plugins",self._reload_plugins).pack(side="left")
        self.fx_status=tk.Label(ag,text="Add effects above, then click Apply",
                                font=F_SMALL,bg=BG,fg=TEXT_DIM,anchor="w")
        self.fx_status.pack(fill="x",pady=(4,0))
        self.fx_prog=ClassicProgress(ag); self.fx_prog.pack(fill="x",pady=(4,0))

    def _browse(self):
        f=filedialog.askopenfilename(filetypes=[("Audio","*.mp3 *.wav *.flac *.ogg *.m4a"),("All","*.*")])
        if f: self.file_var.set(f)

    def _push_undo(self):
        import copy
        self._undo_stack.append(copy.deepcopy(self._chain))
        if len(self._undo_stack)>30: self._undo_stack.pop(0)
        self._redo_stack.clear()
    def _undo(self):
        if not self._undo_stack: show_toast(self.app,"Nothing to undo","info"); return
        import copy
        self._redo_stack.append(copy.deepcopy(self._chain))
        self._chain=self._undo_stack.pop()
        self._render_chain(); show_toast(self.app,"Undone","info")
    def _redo(self):
        if not self._redo_stack: show_toast(self.app,"Nothing to redo","info"); return
        import copy
        self._undo_stack.append(copy.deepcopy(self._chain))
        self._chain=self._redo_stack.pop()
        self._render_chain(); show_toast(self.app,"Redone","info")

    def _add_fx(self):
        self._push_undo()
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
        if idx<len(self._chain): self._push_undo(); self._chain.pop(idx); self._render_chain()

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
            self._push_undo()
            for k,sv in vars_.items():
                try: fx["params"][k]=float(sv.get())
                except Exception: pass
            self._render_chain(); dlg.destroy()
        LimeBtn(dlg,"Save",_save).pack(pady=10)

    def _clear_fx(self):
        self._push_undo(); self._chain=[]; self._render_chain()

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
            self._push_undo(); self._chain=chain; self._render_chain()
            show_toast(self.app,f"Loaded {len(chain)} effects from preset","success")
        except Exception as e:
            show_toast(self.app,f"Load failed: {e}","error")

    def _load_vst(self):
        """Load a VST3/AU plugin file into the effects chain."""
        if not HAS_PEDALBOARD:
            show_toast(self.app,"pedalboard required for VST hosting","error"); return
        ftypes=[("VST3 Plugin","*.vst3")]
        if IS_MACOS: ftypes.append(("Audio Unit","*.component"))
        ftypes.append(("All","*.*"))
        f=filedialog.askopenfilename(filetypes=ftypes,title="Select VST3/AU Plugin")
        if not f: return
        try:
            # Test loading the plugin
            vst=pedalboard.load_plugin(f)
            name=os.path.splitext(os.path.basename(f))[0]
            # Get plugin parameters
            params={}
            for param_name in vst.parameters:
                p=vst.parameters[param_name]
                params[param_name]=getattr(p,"default_value",0.5)
            self._push_undo()
            self._chain.append({"name":f"VST:{name}","params":params,"vst_path":f})
            self._render_chain()
            show_toast(self.app,f"Loaded VST: {name}","success")
        except Exception as e:
            show_toast(self.app,f"VST load failed: {str(e)[:60]}","error")
    def _reload_plugins(self):
        """Reload custom plugins from plugins directory."""
        _plugin_manager.discover()
        # Rebuild effects list
        base_fx=["Compressor","Reverb","Delay","Distortion","Gain","NoiseGate",
                 "HighpassFilter","LowpassFilter","HighShelfFilter","LowShelfFilter","Chorus","Phaser"]
        for p in _plugin_manager.list_plugins():
            label=f"\U0001F9E9 {p.name}"
            if label not in base_fx: base_fx.append(label)
        self._fx_names=base_fx
        errors=_plugin_manager.get_errors()
        if errors:
            show_toast(self.app,f"Loaded plugins ({len(errors)} errors)","warning")
        else:
            show_toast(self.app,f"Plugins reloaded: {len(_plugin_manager.list_plugins())} loaded","success")

    def _build_board(self):
        """Build pedalboard.Pedalboard from current chain."""
        effects=[]
        for fx in self._chain:
            # Handle VST plugins
            if fx["name"].startswith("VST:") and fx.get("vst_path"):
                try:
                    vst=pedalboard.load_plugin(fx["vst_path"])
                    for k,v in fx.get("params",{}).items():
                        try: setattr(vst,k,v)
                        except Exception: pass
                    effects.append(vst); continue
                except Exception: continue
            # Handle custom plugins (processed separately in _apply)
            if fx["name"].startswith("\U0001F9E9 "): continue
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
        ClassicBtn(mr,"Export Playlist (.m3u)",self._export_m3u).pack(side="left",padx=(0,6))
        ClassicBtn(mr,"Export CSV",self._export_csv).pack(side="left")
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
        OrangeBtn(spf,"Send to Player",self._send_to_player).pack(side="left",padx=SP_SM)

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
        # Recursive scan for large libraries
        files=[]
        for root,dirs,fnames in os.walk(folder):
            for fn in fnames:
                if os.path.splitext(fn)[1].lower() in audio_exts:
                    files.append(os.path.join(root,fn))
            if len(files)>=50000: break  # safety cap
        if not files:
            self.after(0,lambda:self.scan_status.config(text="No audio files found.",fg=RED)); return
        self.after(0,lambda n=len(files):self.scan_status.config(text=f"Found {n} files, analyzing...",fg=YELLOW))
        # Load analysis cache
        cache=load_json(ANALYSIS_CACHE_FILE,{})
        self._library={}; analyzed=0; total=len(files)
        # Split into cached and uncached
        uncached=[]
        for fp in files:
            try: mtime=str(os.path.getmtime(fp))
            except OSError: mtime=""
            cache_key=f"{fp}|{mtime}"
            if cache_key in cache:
                self._library[fp]=cache[cache_key]
            else:
                uncached.append((fp,cache_key))
        # Parallel analysis for uncached files using thread pool
        if uncached:
            def _analyze_one(item):
                fp,cache_key=item
                bk=analyze_bpm_key(fp)
                bpm=bk.get("bpm"); key=bk.get("key","")
                camelot=key_to_camelot(key) or ""
                entry={"bpm":bpm,"key":key,"camelot":camelot,"file":os.path.basename(fp)}
                return fp,cache_key,entry
            workers=min(4,os.cpu_count() or 2)
            with ThreadPoolExecutor(max_workers=workers) as pool:
                futures={pool.submit(_analyze_one,item):item for item in uncached}
                done=0
                for fut in as_completed(futures):
                    try:
                        fp,cache_key,entry=fut.result()
                        self._library[fp]=entry; cache[cache_key]=entry; analyzed+=1
                    except Exception: pass
                    done+=1
                    if done%10==0 or done==len(uncached):
                        pct=int(((total-len(uncached)+done)/max(1,total))*100)
                        self.after(0,lambda p=pct,d=done:self.scan_prog.configure(value=p))
        save_json(ANALYSIS_CACHE_FILE,cache)
        cached=total-analyzed
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

    def _export_csv(self):
        """Export library analysis results to CSV."""
        if not self._library: show_toast(self.app,"Scan a library first","warning"); return
        path=filedialog.asksaveasfilename(defaultextension=".csv",filetypes=[("CSV","*.csv")],initialfile="library_analysis.csv")
        if not path: return
        import csv
        with open(path,"w",newline="",encoding="utf-8") as f:
            w=csv.writer(f)
            w.writerow(["File","Path","BPM","Key","Camelot"])
            for fp,info in sorted(self._library.items(),key=lambda x:x[1].get("bpm") or 0):
                bpm=f"{info['bpm']:.1f}" if info.get("bpm") else ""
                w.writerow([info.get("file",""),fp,bpm,info.get("key",""),info.get("camelot","")])
        show_toast(self.app,f"Exported {len(self._library)} tracks to CSV","success")

    def _send_to_player(self):
        """Send generated playlist to Player tab."""
        if not hasattr(self,"_playlist_files") or not self._playlist_files: return
        pp=self.app.pages.get("player")
        if not pp: return
        added=0
        for fp in self._playlist_files:
            if fp not in pp._playlist_set:
                pp._playlist.append(fp); pp._playlist_set.add(fp)
                pp.plb.insert("end",os.path.basename(fp)); added+=1
        if added: show_toast(self.app,f"Added {added} tracks to Player","success")
        self.app._show_tab("player")

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
        self._color_freq=tk.BooleanVar(value=False)
        tk.Checkbutton(zf,text="Color by frequency",variable=self._color_freq,font=F_SMALL,
                       bg=BG,fg=TEXT,selectcolor=INPUT_BG,activebackground=BG,activeforeground=TEXT,
                       command=self._draw_waveform).pack(side="left",padx=(0,8))
        self._freq_colors=[]
        self._hscroll=tk.Scrollbar(wg,orient="horizontal",command=self._on_scrollbar)
        self._hscroll.pack(fill="x",padx=4)
        # Minimap — full waveform overview with viewport indicator
        self._minimap=tk.Canvas(wg,bg=CANVAS_BG,height=24,highlightthickness=0)
        self._minimap.pack(fill="x",padx=4,pady=(2,0))
        self._minimap.bind("<Button-1>",self._minimap_click)
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
        ClassicBtn(sr,"Apply",self._apply_sel).pack(side="left",padx=(0,6))
        ClassicBtn(sr,"Snap Zero-X",self._snap_zero_crossing).pack(side="left")

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
        # Compute frequency colors if enabled
        use_freq=self._color_freq.get() if hasattr(self,"_color_freq") else False
        if use_freq and len(self._freq_colors)!=len(all_bars):
            self._freq_colors=self._compute_freq_colors(self._segment,len(all_bars))
        # Draw bars scaled to canvas width
        mid=h//2
        n=len(visible_bars)
        for i,bh in enumerate(visible_bars):
            x=int(i*w/n) if n>0 else i
            if use_freq and self._freq_colors:
                ci=start_idx+i
                clr=self._freq_colors[ci] if ci<len(self._freq_colors) else LIME
            else:
                clr=LIME
            cv.create_line(x,mid-bh//2,x,mid+bh//2,fill=clr)
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
        # Update minimap
        self._draw_minimap(all_bars,start_idx,end_idx)

    def _compute_freq_colors(self,segment,num_bars):
        """Compute per-bar color based on spectral centroid (low=cyan, mid=green, high=orange)."""
        if not _ensure_librosa(): return [LIME]*num_bars
        try:
            import numpy as _np
            samples=_np.array(segment.get_array_of_samples(),dtype=_np.float32)
            if segment.channels>1: samples=samples[::segment.channels]
            sr=segment.frame_rate
            # Compute spectral centroid
            S=librosa.feature.spectral_centroid(y=samples,sr=sr,hop_length=max(1,len(samples)//num_bars))
            centroids=S[0]
            # Normalize to 0-1 range
            mn,mx=centroids.min(),centroids.max()
            if mx-mn<1: return [LIME]*num_bars
            norm=(centroids-mn)/(mx-mn)
            # Map to colors: 0=cyan(low), 0.5=lime(mid), 1.0=orange(high)
            colors=[]
            for v in norm:
                if v<0.33: colors.append(_lerp_color("#00CED1",LIME,v/0.33))
                elif v<0.66: colors.append(_lerp_color(LIME,YELLOW,(v-0.33)/0.33))
                else: colors.append(_lerp_color(YELLOW,ORANGE,(v-0.66)/0.34))
            # Pad/trim to match num_bars
            while len(colors)<num_bars: colors.append(LIME)
            return colors[:num_bars]
        except Exception:
            return [LIME]*num_bars

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
    def _draw_minimap(self,all_bars,view_start,view_end):
        """Draw minimap showing full waveform with viewport rectangle."""
        mm=self._minimap; mm.delete("all")
        if not all_bars: return
        mm.update_idletasks()
        w=mm.winfo_width() or 600; h=24; mid=h//2; n=len(all_bars)
        # Draw full waveform (compressed)
        for i in range(w):
            bar_idx=int(i*n/w)
            if bar_idx<n:
                bh=max(1,all_bars[bar_idx])
                mm.create_line(i,mid-bh*mid//max(1,max(all_bars)),i,mid+bh*mid//max(1,max(all_bars)),fill=TEXT_DIM)
        # Draw viewport rectangle
        if self._zoom>1.0 and n>0:
            x1=int(view_start/n*w); x2=int(view_end/n*w)
            mm.create_rectangle(x1,0,x2,h,outline=LIME,width=2,fill="")
    def _minimap_click(self,e):
        """Click minimap to scroll to that position."""
        if self._zoom<=1.0: return
        mm=self._minimap; w=mm.winfo_width() or 600
        self._scroll_offset=max(0.0,min(1.0,e.x/w))
        self._draw_waveform()

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

    def _snap_zero_crossing(self):
        """Snap selection edges to nearest zero-crossing for clean cuts."""
        if not self._segment or not _ensure_pydub(): return
        samples=self._segment.get_array_of_samples()
        sr=self._segment.frame_rate; ch=self._segment.channels
        def _find_zero(ms,direction=1):
            idx=int(ms/1000*sr)*ch
            search=range(idx,min(idx+sr*ch//10,len(samples)-1)) if direction>0 else range(idx,max(idx-sr*ch//10,0),-1)
            for i in search:
                if i+1<len(samples) and samples[i]<=0<=samples[i+1] or samples[i]>=0>=samples[i+1]:
                    return int(i/ch/sr*1000)
            return ms
        self._sel_start_ms=_find_zero(self._sel_start_ms,1)
        self._sel_end_ms=_find_zero(self._sel_end_ms,-1)
        self._update_sel_labels(); self._draw_waveform()
        show_toast(self.app,"Snapped to zero-crossings","info")

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
        ClassicBtn(cf,"MIDI Learn",self._midi_learn).pack(side="left",padx=(0,SP_SM))
        self._midi_active=False; self._midi_map={}
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
    def _midi_learn(self):
        """Toggle MIDI learn mode for mapping controllers to stem faders."""
        try:
            import mido
        except ImportError:
            show_toast(self.app,"Install mido for MIDI: pip install mido python-rtmidi","error"); return
        if self._midi_active:
            self._midi_active=False
            self.status_lbl.config(text="MIDI learn disabled",fg=TEXT_DIM); return
        self._midi_active=True
        self.status_lbl.config(text="MIDI Learn active — move a fader, then click a stem volume slider",fg=ORANGE)
        def _listen():
            import mido
            try:
                ports=mido.get_input_names()
                if not ports:
                    self.after(0,lambda:self.status_lbl.config(text="No MIDI devices found",fg=RED))
                    self._midi_active=False; return
                with mido.open_input(ports[0]) as port:
                    self.after(0,lambda:self.status_lbl.config(text=f"Listening on {ports[0]}... Move a control",fg=YELLOW))
                    while self._midi_active:
                        for msg in port.iter_pending():
                            if msg.type=="control_change":
                                cc=msg.control; val=msg.value
                                # Map CC to any stem that has focus or the first unassigned
                                if cc not in self._midi_map:
                                    stem_names=list(self._stems.keys())
                                    idx=len(self._midi_map)%len(stem_names) if stem_names else 0
                                    if idx<len(stem_names):
                                        self._midi_map[cc]=stem_names[idx]
                                        sn=stem_names[idx]
                                        self.after(0,lambda s=sn,c=cc:self.status_lbl.config(
                                            text=f"CC{c} → {s.title()} volume",fg=LIME_DK))
                                if cc in self._midi_map:
                                    target=self._midi_map[cc]
                                    if target in self._stems:
                                        vol_pct=val/127.0*150.0
                                        self.after(0,lambda t=target,v=vol_pct:self._stems[t]["vol"].set(v))
                        time.sleep(0.01)
            except Exception as e:
                self.after(0,lambda:self.status_lbl.config(text=f"MIDI error: {str(e)[:50]}",fg=RED))
                self._midi_active=False
        threading.Thread(target=_listen,daemon=True).start()


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


# ── Cover Art Page ────────────────────────────────────────────────────────────

class CoverArtPage(ScrollFrame):
    """Manage album cover art — view, add, fetch, and batch-apply to audio files."""
    AUDIO_EXTS=(".mp3",".wav",".flac",".ogg",".m4a",".aac",".opus",".wma")
    def __init__(self,parent,app):
        super().__init__(parent); self.app=app; self._files=[]; self._new_art=None; self._new_mime=None
        self._build(self.inner)
    def _build(self,p):
        # ── Source Files ──
        fg=GroupBox(p,"Source Files"); fg.pack(fill="x",padx=10,pady=(10,6))
        fr=tk.Frame(fg,bg=BG); fr.pack(fill="x")
        self.file_var=tk.StringVar()
        ClassicEntry(fr,self.file_var,width=50).pack(side="left",fill="x",expand=True,ipady=2,padx=(0,8))
        ClassicBtn(fr,"Browse File",self._browse_file).pack(side="left",padx=(0,4))
        ClassicBtn(fr,"Add Folder",self._add_folder).pack(side="left",padx=(0,4))
        ClassicBtn(fr,"Clear",self._clear_files).pack(side="left")
        self.file_lb=tk.Listbox(fg,font=F_MONO,bg=INPUT_BG,fg=TEXT,selectbackground=LIME_DK,
                                selectforeground=WHITE,height=6,relief="flat",bd=1,highlightthickness=1,
                                highlightcolor=BORDER_L,highlightbackground=BORDER_D)
        self.file_lb.pack(fill="x",pady=(6,0))
        self.file_lb.bind("<<ListboxSelect>>",self._on_select)
        # ── Current Cover Art ──
        row=tk.Frame(p,bg=BG); row.pack(fill="x",padx=10,pady=(0,6))
        cg=GroupBox(row,"Current Cover Art"); cg.pack(side="left",fill="both",expand=True,padx=(0,6))
        self.cur_art=tk.Label(cg,text="No file\nselected",font=F_BODY,bg=CARD_BG,fg=TEXT_DIM,
                              width=26,height=12,relief="groove",bd=1)
        self.cur_art.pack(pady=4)
        self.cur_info=tk.Label(cg,text="",font=F_SMALL,bg=BG,fg=TEXT_DIM,anchor="w")
        self.cur_info.pack(fill="x")
        # ── New Cover Art ──
        ng=GroupBox(row,"New Cover Art"); ng.pack(side="left",fill="both",expand=True)
        self.new_art=tk.Label(ng,text="No image\nselected",font=F_BODY,bg=CARD_BG,fg=TEXT_DIM,
                              width=26,height=12,relief="groove",bd=1)
        self.new_art.pack(pady=4)
        nbr=tk.Frame(ng,bg=BG); nbr.pack(fill="x",pady=(2,0))
        ClassicBtn(nbr,"Browse Image",self._browse_image).pack(side="left",padx=(0,4))
        LimeBtn(nbr,"Fetch from iTunes",self._fetch_itunes).pack(side="left",padx=(0,4))
        ClassicBtn(nbr,"Fetch from MusicBrainz",self._fetch_mb).pack(side="left")
        # ── Search fields ──
        sf=tk.Frame(ng,bg=BG); sf.pack(fill="x",pady=(6,0))
        tk.Label(sf,text="Artist:",font=F_BOLD,bg=BG,fg=TEXT).pack(side="left")
        self.artist_var=tk.StringVar()
        ClassicEntry(sf,self.artist_var,width=18).pack(side="left",padx=(4,8),ipady=2)
        tk.Label(sf,text="Album/Title:",font=F_BOLD,bg=BG,fg=TEXT).pack(side="left")
        self.album_var=tk.StringVar()
        ClassicEntry(sf,self.album_var,width=18).pack(side="left",padx=(4,0),ipady=2)
        self.new_info=tk.Label(ng,text="",font=F_SMALL,bg=BG,fg=TEXT_DIM,anchor="w")
        self.new_info.pack(fill="x",pady=(2,0))
        # ── Apply ──
        ag=GroupBox(p,"Apply"); ag.pack(fill="x",padx=10,pady=(0,6))
        abr=tk.Frame(ag,bg=BG); abr.pack(fill="x")
        LimeBtn(abr,"Apply to Selected",self._apply_selected,width=18).pack(side="left",padx=(0,8))
        LimeBtn(abr,"Apply to All Files",self._apply_all,width=18).pack(side="left",padx=(0,8))
        OrangeBtn(abr,"Remove Art",self._remove_art).pack(side="left",padx=(0,8))
        self.status_lbl=tk.Label(ag,text="Select files and cover art above",font=F_SMALL,bg=BG,fg=TEXT_DIM,anchor="w")
        self.status_lbl.pack(fill="x",pady=(4,0))
        self.prog=ClassicProgress(ag); self.prog.pack(fill="x",pady=(4,0))

    # ── File management ──
    def _browse_file(self):
        f=filedialog.askopenfilename(filetypes=[("Audio","*.mp3 *.wav *.flac *.ogg *.m4a *.aac *.opus"),("All","*.*")])
        if f:
            self.file_var.set(f)
            if f not in self._files: self._files.append(f)
            self._refresh_list(); self._select_file(len(self._files)-1)
    def _add_folder(self):
        d=filedialog.askdirectory()
        if not d: return
        added=0
        for fn in sorted(os.listdir(d)):
            fp=os.path.join(d,fn)
            if os.path.isfile(fp) and os.path.splitext(fn)[1].lower() in self.AUDIO_EXTS:
                if fp not in self._files: self._files.append(fp); added+=1
        self._refresh_list()
        show_toast(self.app,f"Added {added} audio files","info")
    def _clear_files(self):
        self._files.clear(); self.file_lb.delete(0,"end")
        self.cur_art.config(image="",text="No file\nselected"); self.cur_info.config(text="")
    def _refresh_list(self):
        self.file_lb.delete(0,"end")
        for fp in self._files:
            art_data,_=extract_cover_art(fp)
            icon="\u2713" if art_data else "\u2717"
            self.file_lb.insert("end",f" {icon}  {os.path.basename(fp)}")
    def _select_file(self,idx):
        self.file_lb.selection_clear(0,"end"); self.file_lb.selection_set(idx); self.file_lb.see(idx)
        self._show_current_art(self._files[idx])
    def _on_select(self,e=None):
        sel=self.file_lb.curselection()
        if not sel: return
        idx=sel[0]
        if idx<len(self._files):
            fp=self._files[idx]; self.file_var.set(fp); self._show_current_art(fp)
            # Auto-populate artist/album from tags
            try:
                mf=mutagen.File(fp)
                if mf and hasattr(mf,'tags') and mf.tags:
                    for k in ["TPE1","artist","ARTIST","\u00a9ART"]:
                        if k in mf.tags:
                            v=mf.tags[k]; self.artist_var.set(str(v[0]) if isinstance(v,list) else str(v)); break
                    for k in ["TALB","album","ALBUM","\u00a9alb"]:
                        if k in mf.tags:
                            v=mf.tags[k]; self.album_var.set(str(v[0]) if isinstance(v,list) else str(v)); break
                    for k in ["TIT2","title","TITLE","\u00a9nam"]:
                        if k in mf.tags:
                            v=mf.tags[k]
                            if not self.album_var.get(): self.album_var.set(str(v[0]) if isinstance(v,list) else str(v))
                            break
            except Exception: pass

    # ── Display helpers ──
    def _show_current_art(self,filepath):
        art_data,mime=extract_cover_art(filepath)
        if art_data:
            self._display_art(self.cur_art,art_data)
            try:
                img=Image.open(BytesIO(art_data))
                self.cur_info.config(text=f"{img.size[0]}x{img.size[1]}  {mime or '?'}  {len(art_data)//1024}KB")
            except Exception: self.cur_info.config(text=f"{len(art_data)//1024}KB")
        else:
            self.cur_art.config(image="",text="No cover art\nembedded"); self.cur_info.config(text="")
    def _display_art(self,label,img_bytes,size=200):
        try:
            img=Image.open(BytesIO(img_bytes)).convert("RGB")
            img.thumbnail((size,size),Image.LANCZOS)
            ph=ImageTk.PhotoImage(img); label.config(image=ph,text="",width=size,height=size); label._img=ph
        except Exception:
            label.config(image="",text="Error loading\nimage")
    def _show_new_art(self,img_bytes,mime):
        self._new_art=img_bytes; self._new_mime=mime
        self._display_art(self.new_art,img_bytes)
        try:
            img=Image.open(BytesIO(img_bytes))
            self.new_info.config(text=f"{img.size[0]}x{img.size[1]}  {mime}  {len(img_bytes)//1024}KB")
        except Exception: self.new_info.config(text=f"{len(img_bytes)//1024}KB")

    # ── Image source actions ──
    def _browse_image(self):
        f=filedialog.askopenfilename(filetypes=[("Images","*.jpg *.jpeg *.png *.bmp *.webp"),("All","*.*")])
        if not f: return
        with open(f,"rb") as fh: data=fh.read()
        mime="image/png" if f.lower().endswith(".png") else "image/jpeg"
        prepared=prepare_cover_image(data,size=500)
        self._show_new_art(prepared,"image/jpeg")
        show_toast(self.app,f"Loaded: {os.path.basename(f)}","info")
    def _fetch_itunes(self):
        query=f"{self.artist_var.get()} {self.album_var.get()}".strip()
        if not query:
            # Try filename
            sel=self.file_lb.curselection()
            if sel and sel[0]<len(self._files):
                query=os.path.splitext(os.path.basename(self._files[sel[0]]))[0]
        if not query: show_toast(self.app,"Enter artist/album or select a file","warning"); return
        self.status_lbl.config(text=f"Searching iTunes for '{query[:40]}'...",fg=YELLOW)
        def _do():
            data=fetch_itunes_art(query,size=600)
            if data:
                prepared=prepare_cover_image(data,size=500)
                self.after(0,lambda:(self._show_new_art(prepared,"image/jpeg"),
                    self.status_lbl.config(text="iTunes cover art found!",fg=LIME_DK)))
            else:
                self.after(0,lambda:self.status_lbl.config(text="No cover art found on iTunes",fg=RED))
        threading.Thread(target=_do,daemon=True).start()
    def _fetch_mb(self):
        query=f"{self.artist_var.get()} {self.album_var.get()}".strip()
        if not query:
            sel=self.file_lb.curselection()
            if sel and sel[0]<len(self._files):
                query=os.path.splitext(os.path.basename(self._files[sel[0]]))[0]
        if not query: show_toast(self.app,"Enter artist/album or select a file","warning"); return
        self.status_lbl.config(text=f"Searching MusicBrainz for '{query[:40]}'...",fg=YELLOW)
        def _do():
            data=fetch_musicbrainz_art(query,size=500)
            if data:
                prepared=prepare_cover_image(data,size=500)
                self.after(0,lambda:(self._show_new_art(prepared,"image/jpeg"),
                    self.status_lbl.config(text="MusicBrainz cover art found!",fg=LIME_DK)))
            else:
                self.after(0,lambda:self.status_lbl.config(text="No cover art found on MusicBrainz",fg=RED))
        threading.Thread(target=_do,daemon=True).start()

    # ── Apply / Remove ──
    def _apply_selected(self):
        if not self._new_art: show_toast(self.app,"Select or fetch cover art first","warning"); return
        sel=self.file_lb.curselection()
        if not sel: show_toast(self.app,"Select a file from the list","warning"); return
        idx=sel[0]
        if idx>=len(self._files): return
        fp=self._files[idx]
        try:
            embed_cover_art(fp,self._new_art,self._new_mime or "image/jpeg")
            show_toast(self.app,f"Cover art applied to {os.path.basename(fp)}","success")
            self._refresh_list(); self._select_file(idx); self._show_current_art(fp)
        except Exception as e:
            show_toast(self.app,f"Error: {str(e)[:60]}","error")
    def _apply_all(self):
        if not self._new_art: show_toast(self.app,"Select or fetch cover art first","warning"); return
        if not self._files: show_toast(self.app,"Add files first","warning"); return
        total=len(self._files); self.prog.configure(value=0)
        self.status_lbl.config(text=f"Applying cover art to {total} files...",fg=YELLOW)
        def _do():
            ok=0; fail=0
            for i,fp in enumerate(self._files):
                try:
                    embed_cover_art(fp,self._new_art,self._new_mime or "image/jpeg")
                    ok+=1
                except Exception: fail+=1
                self.after(0,lambda p=int((i+1)/total*100):self.prog.configure(value=p))
            msg=f"Done! {ok} files updated"+(f", {fail} failed" if fail else "")
            self.after(0,lambda:(self.status_lbl.config(text=msg,fg=LIME_DK if fail==0 else YELLOW),
                self._refresh_list(),show_toast(self.app,msg,"success" if fail==0 else "warning")))
        threading.Thread(target=_do,daemon=True).start()
    def _remove_art(self):
        sel=self.file_lb.curselection()
        if not sel: show_toast(self.app,"Select a file first","warning"); return
        idx=sel[0]
        if idx>=len(self._files): return
        fp=self._files[idx]
        try:
            audio=mutagen.File(fp)
            if audio is None: return
            from mutagen.mp3 import MP3 as _MP3; from mutagen.flac import FLAC as _FLAC
            from mutagen.mp4 import MP4 as _MP4; from mutagen.wave import WAVE as _WAVE
            if isinstance(audio,(_MP3,_WAVE)):
                if audio.tags: audio.tags.delall("APIC")
            elif isinstance(audio,_FLAC):
                audio.clear_pictures()
            elif isinstance(audio,_MP4):
                if audio.tags and 'covr' in audio.tags: del audio.tags['covr']
            elif hasattr(audio,'tags') and audio.tags and 'metadata_block_picture' in audio:
                del audio['metadata_block_picture']
            audio.save()
            show_toast(self.app,f"Cover art removed from {os.path.basename(fp)}","info")
            self._refresh_list(); self._select_file(idx); self._show_current_art(fp)
        except Exception as e:
            show_toast(self.app,f"Error: {str(e)[:60]}","error")


# ── Launch ────────────────────────────────────────────────────────────────────
if __name__=="__main__":
    try: app=App(); app.mainloop()
    except Exception as e:
        import traceback
        try: messagebox.showerror("LimeWire Error",traceback.format_exc())
        except Exception: input(f"ERROR: {e}\nPress Enter...")
