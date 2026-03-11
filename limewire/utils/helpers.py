"""General utility functions — sanitize_filename, is_url, detect_source, etc."""
import os, sys, re, subprocess, datetime, urllib.request, urllib.parse
from io import BytesIO

from limewire.core.deps import Image
from limewire.core.constants import (
    MAX_URL_LENGTH, FILENAME_MAX_LENGTH, URL_PATTERNS,
)

_WIN_RESERVED = frozenset({"CON","PRN","AUX","NUL"} |
    {f"COM{i}" for i in range(1,10)} | {f"LPT{i}" for i in range(1,10)})

_BLOCKED_SCHEMES = frozenset({"file","ftp","ftps","rtsp","rtmp","smb","ssh","telnet","data"})


def fmt_duration(s):
    try: return str(datetime.timedelta(seconds=int(s)))
    except Exception: return "--:--"


def fetch_thumbnail(url, size=(120, 80)):
    try:
        with urllib.request.urlopen(url, timeout=5) as r: data = r.read()
        with Image.open(BytesIO(data)) as raw:
            img = raw.convert("RGB"); img.thumbnail(size, Image.LANCZOS); return img
    except Exception: return None


def is_url(t):
    t = t.strip()
    if not t or len(t) > MAX_URL_LENGTH: return False
    try:
        parsed = urllib.parse.urlparse(t)
        if parsed.scheme and parsed.scheme.lower() not in ("http", "https", ""): return False
    except Exception: return False
    return any(p.match(t) for p in URL_PATTERNS)


def sanitize_filename(n):
    n = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '', n); n = n.strip('. ')
    base = n.split('.')[0].upper()
    if base in _WIN_RESERVED: n = f"_{n}"
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
    u = url.lower()
    for pat, src in _SOURCE_PATTERNS:
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
    u = url.lower()
    for pat, result in _FORMAT_PATTERNS:
        if pat in u: return result
    return None, None


def open_folder(path):
    if os.path.exists(path):
        try:
            if sys.platform == "win32": os.startfile(path)
            elif sys.platform == "darwin": subprocess.run(["open", path], timeout=10)
            else: subprocess.run(["xdg-open", path], timeout=10)
        except Exception: pass


def _ui(widget, fn, *args):
    """Schedule fn(*args) on the main thread via widget.after(0, ...)."""
    widget.after(0, lambda: fn(*args))


class _SilentLogger:
    def debug(self, m): pass
    def warning(self, m): pass
    def error(self, m): pass
