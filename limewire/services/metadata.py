"""Metadata & identification — Shazam, MusicBrainz, AcoustID, Apple Music, Spotify, lyrics."""
import os, asyncio

import requests

from limewire.core.deps import (
    HAS_SHAZAM, HAS_MB, HAS_ACOUSTID, HAS_LYRICS,
)
from limewire.core.constants import ACOUSTID_KEY

# Conditional imports (already validated by deps flags)
try:
    from shazamio import Shazam as ShazamEngine
except Exception:
    ShazamEngine = None

try:
    import musicbrainzngs
except Exception:
    musicbrainzngs = None

try:
    import acoustid
except Exception:
    acoustid = None

try:
    import lyricsgenius
except Exception:
    lyricsgenius = None


def lookup_lyrics(title, artist="", api_key=None):
    """Search Genius for song lyrics."""
    if not HAS_LYRICS:
        return {"error": "lyricsgenius not installed. Run: pip install lyricsgenius"}
    key = api_key or os.environ.get("GENIUS_API_KEY", "")
    if not key:
        return {"error": "Set Genius API key in Settings or GENIUS_API_KEY env var"}
    try:
        genius = lyricsgenius.Genius(key, timeout=15, retries=2, verbose=False)
        genius.remove_section_headers = True
        song = genius.search_song(title, artist)
        if song:
            return {
                "title": song.title, "artist": song.artist,
                "lyrics": song.lyrics, "url": song.url,
                "album": getattr(song, "album", ""),
                "thumbnail": getattr(song, "song_art_image_thumbnail_url", ""),
            }
        return {"error": "No lyrics found"}
    except Exception as e:
        return {"error": str(e)[:80]}


def identify_shazam(filepath):
    """Identify track using Shazam — uses shazamio if available."""
    if not HAS_SHAZAM or ShazamEngine is None:
        return {
            "title": None, "artist": None,
            "error": "shazamio not installed (needs Python <=3.12). "
                     "Use Shazam Search instead.",
        }
    try:
        async def _run():
            shazam = ShazamEngine()
            return await shazam.recognize(filepath)

        loop = asyncio.new_event_loop()
        try:
            result = loop.run_until_complete(_run())
        finally:
            loop.close()
        track = result.get("track", {})
        if track:
            return {
                "title": track.get("title"),
                "artist": track.get("subtitle"),
                "genre": track.get("genres", {}).get("primary", ""),
                "album": (track.get("sections", [{}])[0]
                          .get("metadata", [{}])[0].get("text", "")
                          if track.get("sections") else ""),
                "shazam_url": track.get("url", ""),
            }
        return {"title": None, "artist": None, "error": "No match found"}
    except Exception as e:
        return {"title": None, "artist": None, "error": str(e)[:80]}


def search_shazam(query):
    """Search Shazam catalog by text query — pure HTTP, no Rust, always works."""
    try:
        url = ("https://www.shazam.com/services/amapi/v1/catalog/US/search"
               f"?types=songs&term={requests.utils.quote(query)}&limit=5")
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                                 "AppleWebKit/537.36"}
        resp = requests.get(url, headers=headers, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            songs = data.get("results", {}).get("songs", {}).get("data", [])
            if songs:
                s = songs[0].get("attributes", {})
                return {
                    "title": s.get("name"), "artist": s.get("artistName"),
                    "album": s.get("albumName", ""),
                    "genre": s.get("genreNames", [""])[0],
                    "url": s.get("url", ""),
                    "duration_ms": s.get("durationInMillis", 0),
                }
        # Fallback: v1 web search
        url2 = ("https://www.shazam.com/services/search/v3/en/US/web/search"
                f"?query={requests.utils.quote(query)}&numResults=5&type=SONGS")
        resp2 = requests.get(url2, headers=headers, timeout=10)
        if resp2.status_code == 200:
            data2 = resp2.json()
            tracks = data2.get("tracks", {}).get("hits", [])
            if tracks:
                t = tracks[0].get("track", {})
                return {
                    "title": t.get("title"), "artist": t.get("subtitle"),
                    "genre": t.get("genres", {}).get("primary", ""),
                    "url": t.get("url", ""),
                }
        return {"error": "No results found"}
    except Exception as e:
        return {"error": str(e)[:80]}


def lookup_musicbrainz(title, artist):
    """Search MusicBrainz for detailed metadata."""
    if not HAS_MB or musicbrainzngs is None:
        return {"error": "musicbrainzngs not installed"}
    try:
        result = musicbrainzngs.search_recordings(
            recording=title, artist=artist, limit=3)
        recs = result.get("recording-list", [])
        if recs:
            rec = recs[0]
            return {
                "mb_title": rec.get("title", ""),
                "mb_artist": rec.get("artist-credit-phrase", ""),
                "mb_album": (rec.get("release-list", [{}])[0].get("title", "")
                             if rec.get("release-list") else ""),
                "mb_date": (rec.get("release-list", [{}])[0].get("date", "")
                            if rec.get("release-list") else ""),
                "mb_id": rec.get("id", ""),
            }
        return {"error": "No MusicBrainz match"}
    except Exception as e:
        return {"error": str(e)[:80]}


def lookup_apple_music(title, artist=""):
    """Search iTunes/Apple Music catalog. Public API, no auth needed."""
    try:
        query = f"{title} {artist}".strip()
        url = (f"https://itunes.apple.com/search"
               f"?term={requests.utils.quote(query)}&entity=song&limit=3")
        resp = requests.get(url, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            results = data.get("results", [])
            if results:
                r = results[0]
                return {
                    "am_title": r.get("trackName", ""),
                    "am_artist": r.get("artistName", ""),
                    "am_album": r.get("collectionName", ""),
                    "am_genre": r.get("primaryGenreName", ""),
                    "am_date": (r.get("releaseDate", "")[:10]
                                if r.get("releaseDate") else ""),
                    "am_artwork": r.get("artworkUrl100", "").replace(
                        "100x100", "600x600"),
                    "am_preview": r.get("previewUrl", ""),
                    "am_url": r.get("trackViewUrl", ""),
                    "am_duration_ms": r.get("trackTimeMillis", 0),
                }
        return {"error": "No Apple Music match"}
    except Exception as e:
        return {"error": str(e)[:80]}


def resolve_spotify_url(url):
    """Resolve a Spotify URL to track info using oEmbed API (public, no auth)."""
    try:
        oembed_url = (f"https://open.spotify.com/oembed"
                      f"?url={requests.utils.quote(url)}")
        resp = requests.get(oembed_url, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            title = data.get("title", "")
            return {"title": title, "type": data.get("type", "track"),
                    "provider": "Spotify"}
        return {"error": f"Spotify oEmbed returned {resp.status_code}"}
    except Exception as e:
        return {"error": str(e)[:80]}


def spotify_to_youtube(url):
    """Resolve Spotify track URL → YouTube search URL for yt-dlp download."""
    info = resolve_spotify_url(url)
    if info.get("error"):
        return None, info["error"]
    title = info.get("title", "")
    if not title:
        return None, "Could not extract title from Spotify"
    return f"ytsearch1:{title}", None


def identify_acoustid(filepath):
    """Fingerprint and identify using AcoustID/Chromaprint."""
    if not HAS_ACOUSTID or acoustid is None:
        return {"error": "pyacoustid not installed"}
    try:
        results = list(acoustid.match(ACOUSTID_KEY, filepath))
        if results:
            score, rid, title, artist = results[0]
            return {"title": title, "artist": artist,
                    "score": round(score, 2), "recording_id": rid}
        return {"error": "No fingerprint match"}
    except Exception as e:
        return {"error": str(e)[:80]}


# ── Connector integration ────────────────────────────────────────────────────

def connector_search(service, query, settings, limit=10):
    """Search a music service via its connector. Returns list of dicts."""
    try:
        from limewire.services.connectors.factory import build_connector
        c = build_connector(service, settings)
        if not c:
            return {"error": f"Unknown service: {service}"}
        results = c.search(query, limit)
        return [r.to_dict() for r in results]
    except Exception as e:
        return {"error": str(e)[:120]}


def connector_import_playlist(service, url_or_id, settings):
    """Import a playlist from a music service. Returns dict with playlist data."""
    try:
        from limewire.services.connectors.factory import build_connector
        from limewire.services.connectors.utils import detect_service_from_url
        svc = service or detect_service_from_url(url_or_id)
        if not svc:
            return {"error": "Could not detect service from URL"}
        c = build_connector(svc, settings)
        if not c:
            return {"error": f"Unknown service: {svc}"}
        pl = c.get_playlist(url_or_id)
        if not pl:
            return {"error": "Playlist not found"}
        return pl.to_dict()
    except Exception as e:
        return {"error": str(e)[:120]}


def connector_transfer_playlist(source_svc, target_svc, playlist_id, settings,
                                target_name=None, progress_cb=None):
    """Transfer a playlist between services. Returns TransferReport as dict."""
    try:
        from limewire.services.connectors.factory import build_connector
        from limewire.services.connectors.transfer import transfer_playlist
        src = build_connector(source_svc, settings)
        tgt = build_connector(target_svc, settings)
        if not src or not tgt:
            return {"error": "Invalid service"}
        report = transfer_playlist(src, tgt, playlist_id, target_name,
                                   progress_callback=progress_cb)
        return report.to_dict()
    except Exception as e:
        return {"error": str(e)[:120]}
