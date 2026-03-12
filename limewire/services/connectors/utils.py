"""Utility functions for source detection, URL parsing, and text normalization."""

from __future__ import annotations

import re
from urllib.parse import urlparse, parse_qs

# ── Source prefix map ────────────────────────────────────────────────────────
SOURCE_PREFIXES: dict[str, str] = {
    "sp": "spotify",
    "yt": "youtube",
    "am": "apple_music",
    "sc": "soundcloud",
    "td": "tidal",
    "az": "amazon_music",
}

# ── URL-to-service patterns ──────────────────────────────────────────────────
_URL_PATTERNS: list[tuple[str, str]] = [
    (r"open\.spotify\.com|spotify\.com", "spotify"),
    (r"music\.youtube\.com|youtube\.com|youtu\.be", "youtube"),
    (r"music\.apple\.com|itunes\.apple\.com", "apple_music"),
    (r"soundcloud\.com", "soundcloud"),
    (r"tidal\.com|listen\.tidal", "tidal"),
    (r"music\.amazon\.", "amazon_music"),
]

CONNECTOR_LABELS: dict[str, str] = {
    "spotify": "Spotify",
    "youtube": "YouTube",
    "apple_music": "Apple Music",
    "amazon_music": "Amazon Music",
    "tidal": "TIDAL",
    "soundcloud": "SoundCloud",
}


def parse_source_query(text: str) -> tuple[str | None, str]:
    """Parse 'sp:daft punk' → ('spotify', 'daft punk'). Returns (None, text) if no prefix."""
    text = (text or "").strip()
    if ":" not in text:
        return None, text
    prefix, rest = text.split(":", 1)
    service = SOURCE_PREFIXES.get(prefix.lower())
    return service, rest.strip()


def detect_service_from_url(url: str) -> str | None:
    """Detect music service from a URL. Returns service key or None."""
    if not url:
        return None
    for pattern, service in _URL_PATTERNS:
        if re.search(pattern, url, re.I):
            return service
    return None


def extract_spotify_id(url: str) -> tuple[str, str]:
    """Extract (type, id) from a Spotify URL.

    Returns ("track"|"playlist"|"album"|"artist", "id") or ("", "").
    """
    m = re.search(
        r"open\.spotify\.com/(?:intl-[a-z]+/)?(track|album|playlist|artist)/([A-Za-z0-9]+)",
        url,
    )
    if m:
        return m.group(1), m.group(2)
    return "", ""


def extract_youtube_playlist_id(url: str) -> str | None:
    """Extract playlist ID from a YouTube or YouTube Music URL."""
    parsed = urlparse(url)
    if "youtube.com" in parsed.netloc or "music.youtube.com" in parsed.netloc:
        qs = parse_qs(parsed.query)
        vals = qs.get("list")
        return vals[0] if vals else None
    return None


def extract_tidal_id(url: str) -> tuple[str, str]:
    """Extract (type, id) from a TIDAL URL.

    Returns ("track"|"playlist"|"album", "id") or ("", "").
    """
    m = re.search(r"tidal\.com/browse/(track|album|playlist)/([A-Za-z0-9\-]+)", url)
    if m:
        return m.group(1), m.group(2)
    return "", ""


def normalize_title(title: str) -> str:
    """Normalize a track title for fuzzy matching.

    Strips parenthetical content (feat., remix tags), special characters,
    collapses whitespace.
    """
    if not title:
        return ""
    t = title.lower().strip()
    t = re.sub(r"\(.*?\)|\[.*?\]", "", t)           # strip (feat. ...) [Remix] etc.
    t = re.sub(r"[^a-z0-9\s]", "", t)               # remove punctuation
    t = re.sub(r"\s+", " ", t).strip()               # collapse whitespace
    return t


def split_artists(name: str | None) -> list[str]:
    """Split a combined artist string into individual artist names."""
    if not name:
        return []
    return [a.strip() for a in re.split(r",|&| feat\.? | ft\.? | x ", name, flags=re.I) if a.strip()]
