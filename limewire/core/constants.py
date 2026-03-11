"""Application constants — timings, dimensions, format lists."""
import os, re

# ── Timing ────────────────────────────────────────────────────────────────────
CLIPBOARD_POLL_MS = 1500
CLIPBOARD_INITIAL_DELAY_MS = 2000
STATUS_PULSE_MS = 1500
PLAYER_UPDATE_MS = 500
SCHEDULER_POLL_SEC = 30

# ── Visualization ─────────────────────────────────────────────────────────────
EQ_BAR_COUNT = 32
EQ_PEAK_DECAY = 0.03
WAVEFORM_W = 600
WAVEFORM_H = 80
PLAYER_WAVEFORM_W = 500
PLAYER_WAVEFORM_H = 50
FREQ_PROFILE_HOP = 0.05
FREQ_PROFILE_BANDS = 32
LOGO_BAR_HEIGHT = 48

# ── Limits ────────────────────────────────────────────────────────────────────
HISTORY_MAX = 300
RECENT_DL_MAX = 20
MAX_PLAYLIST_GEN = 20
MAX_URL_LENGTH = 500
FILENAME_MAX_LENGTH = 200
NETWORK_TIMEOUT = 30
FFMPEG_TIMEOUT = 600

# ── Editor ────────────────────────────────────────────────────────────────────
EDITOR_UNDO_MAX = 50
EDITOR_WAVEFORM_H = 100
EDITOR_FADE_DEFAULT_MS = 500

# ── Recorder ──────────────────────────────────────────────────────────────────
RECORDER_SAMPLE_RATE = 44100
RECORDER_CHANNELS = 1
RECORDER_CHUNK = 1024
RECORDER_VU_UPDATE_MS = 50

# ── Spectrogram ───────────────────────────────────────────────────────────────
SPECTROGRAM_FFT = 2048
SPECTROGRAM_HOP = 512
SPECTROGRAM_CMAP = "viridis"

# ── Pitch/Time ────────────────────────────────────────────────────────────────
PITCH_SEMITONE_RANGE = 12
TEMPO_RANGE = (0.25, 4.0)
KEY_NAMES_FULL = ["C","C#","D","D#","E","F","F#","G","G#","A","A#","B"]
ALL_KEYS = [f"{n} {m}" for m in ["Major","Minor"] for n in KEY_NAMES_FULL]

# ── Formats ───────────────────────────────────────────────────────────────────
AUDIO_FMTS = ["mp3","wav","aac","flac","ogg","m4a","opus"]
VIDEO_FMTS = ["mp4","mkv","webm","avi","mov"]
QUALITIES = ["best","2160p","1440p","1080p","720p","480p","360p","worst"]
CONV_AUDIO = ["mp3","wav","flac","aac","ogg","m4a","opus"]
CONV_VIDEO = ["mp4","mkv","webm","avi","mov","gif"]

# ── yt-dlp ────────────────────────────────────────────────────────────────────
SUPPRESS = ("No supported JavaScript","impersonat","Only deno","js-runtimes","Remote components")
ACOUSTID_KEY = os.environ.get("ACOUSTID_API_KEY", "")
YDL_BASE = {"remote_components": ["ejs:github"], "socket_timeout": NETWORK_TIMEOUT}

def ydl_opts(**kw):
    return {**YDL_BASE, **kw}

# ── URL patterns ──────────────────────────────────────────────────────────────
URL_PATTERNS = [
    re.compile(r'https?://(?:www\.)?youtube\.com/watch\?v=[\w-]+'),
    re.compile(r'https?://youtu\.be/[\w-]+'),
    re.compile(r'https?://(?:www\.)?soundcloud\.com/[\w-]+/[\w-]+'),
    re.compile(r'https?://\S+\.\S+'),
]

# ── Spacing ───────────────────────────────────────────────────────────────────
SP_XS = 4; SP_SM = 8; SP_MD = 12; SP_LG = 16; SP_XL = 24; SP_2XL = 32
