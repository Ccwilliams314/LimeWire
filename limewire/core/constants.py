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
LOGO_BAR_HEIGHT = 58

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

# ── Visualizer ────────────────────────────────────────────────────────────────
VISUALIZER_UPDATE_MS = 33
VISUALIZER_BAR_COUNT = 64
VISUALIZER_PARTICLE_COUNT = 200

# ── DJ ────────────────────────────────────────────────────────────────────────
DJ_SPEED_RANGE = 0.08
DJ_WAVEFORM_H = 60
DJ_CROSSFADE_DEFAULT = 50

# ── Lyrics ────────────────────────────────────────────────────────────────────
LRC_OFFSET_RANGE = 5.0
LYRICS_FONT_SIZE_DEFAULT = 14
LYRICS_UPDATE_MS = 200

# ── Library ───────────────────────────────────────────────────────────────────
LIBRARY_SCAN_EXTS = frozenset({
    ".mp3", ".wav", ".flac", ".ogg", ".m4a", ".aac", ".opus", ".wma", ".aiff",
})

# ── Layout Dimensions (base values, scaled via S()) ─────────────────────────
TOOLBAR_HEIGHT = 50
STATUS_HEIGHT = 30
SCROLLBAR_WIDTH = 12
TREEVIEW_ROW_HEIGHT = 32

# ── Spacing ───────────────────────────────────────────────────────────────────
SP_XS = 4; SP_SM = 8; SP_MD = 12; SP_LG = 16; SP_XL = 24; SP_2XL = 32

# ── DPI Scaling ──────────────────────────────────────────────────────────────
_DPI_SCALE = 1.0  # set at runtime by init_dpi_scale()


def init_dpi_scale(root):
    """Compute DPI scale factor from tk scaling. Call once after Tk() init."""
    global _DPI_SCALE
    raw = root.tk.call("tk", "scaling")  # returns float, 1.0 = 72 DPI
    _DPI_SCALE = max(1.0, raw / 1.333)  # 1.333 = 96 DPI baseline
    rescale_spacing()


def S(px):
    """Scale a pixel value by DPI factor. Use for all dynamic sizes."""
    return max(1, int(px * _DPI_SCALE))


def set_user_scale(factor):
    """Apply user font-scale preference on top of DPI scale."""
    global _DPI_SCALE
    raw_dpi = _DPI_SCALE
    _DPI_SCALE = raw_dpi * factor
    rescale_spacing()


def rescale_spacing():
    """Rescale spacing constants to current DPI factor."""
    global SP_XS, SP_SM, SP_MD, SP_LG, SP_XL, SP_2XL
    SP_XS = S(4); SP_SM = S(8); SP_MD = S(12)
    SP_LG = S(16); SP_XL = S(24); SP_2XL = S(32)
