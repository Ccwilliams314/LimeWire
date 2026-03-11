"""Dependency validation and lazy loaders for optional packages."""
import sys, os, shutil, logging

_log = logging.getLogger("LimeWire")

# ── Required packages ─────────────────────────────────────────────────────────
_REQUIRED = [("yt_dlp","yt-dlp"),("PIL","Pillow"),("requests","requests"),
             ("mutagen","mutagen"),("pyglet","pyglet")]

def validate_required():
    """Check required packages, show error dialog and exit if missing."""
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

# FFmpeg
HAS_FFMPEG = shutil.which("ffmpeg") is not None

# ── Required imports (after validation) ───────────────────────────────────────
import yt_dlp  # noqa: E402
from PIL import Image, ImageTk  # noqa: E402
import requests, mutagen  # noqa: E402
from mutagen.easyid3 import EasyID3  # noqa: E402
from mutagen.id3 import ID3, APIC, TIT2, TPE1, TALB, TDRC, TCON, TBPM, TKEY  # noqa: E402
from mutagen.mp3 import MP3  # noqa: E402
import pyglet  # noqa: E402

# ── Optional: eager imports ───────────────────────────────────────────────────
try: import numpy as np; HAS_NUMPY = True
except Exception: HAS_NUMPY = False; np = None

try: import musicbrainzngs; musicbrainzngs.set_useragent("LimeWire","1.0","https://github.com"); HAS_MB = True
except Exception: HAS_MB = False; musicbrainzngs = None
try: import acoustid; HAS_ACOUSTID = True
except Exception: HAS_ACOUSTID = False; acoustid = None
try: import demucs; HAS_DEMUCS = True
except Exception: HAS_DEMUCS = False; demucs = None
try: from shazamio import Shazam as ShazamEngine; HAS_SHAZAM = True
except Exception: HAS_SHAZAM = False; ShazamEngine = None
HAS_SHAZAM_SEARCH = True  # pure-HTTP always works
try: import tkinterdnd2; HAS_DND = True
except Exception: HAS_DND = False; tkinterdnd2 = None
try: import pyflp; HAS_PYFLP = True
except Exception: HAS_PYFLP = False; pyflp = None
try: from serato_tools.crate import Crate as SeratoCrate; HAS_SERATO = True
except Exception: HAS_SERATO = False; SeratoCrate = None
try: import noisereduce as nr; HAS_NOISEREDUCE = True
except Exception: HAS_NOISEREDUCE = False; nr = None
try: import pedalboard; HAS_PEDALBOARD = True
except Exception: HAS_PEDALBOARD = False; pedalboard = None
try: import lyricsgenius; HAS_LYRICS = True
except Exception: HAS_LYRICS = False; lyricsgenius = None
try: from pypresence import Presence as DiscordRPC; HAS_DISCORD_RPC = True
except Exception: HAS_DISCORD_RPC = False; DiscordRPC = None

# ── Lazy loaders ──────────────────────────────────────────────────────────────
HAS_LIBROSA = False; librosa = None
HAS_LOUDNESS = False; sf = None; pyln = None

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

HAS_PYDUB = False; pydub = None; AudioSegment = None
HAS_SOUNDDEVICE = False; sd_mod = None
HAS_WHISPER = False; whisper_mod = None
HAS_RUBBERBAND = False; pyrubberband = None

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
