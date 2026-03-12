"""YouTube / YouTube Music connector — yt-dlp for read, Data API v3 for write."""

from __future__ import annotations

import re
import threading
import time
from urllib.parse import urlencode

import requests

from .base import ConnectorBase, TrackResult, PlaylistResult
from .oauth import (
    REDIRECT_URI, start_oauth_flow, exchange_code_for_token,
    refresh_access_token, generate_state, generate_pkce, _sanitize_error,
)
from .storage import save_account, load_account

YT_API = "https://www.googleapis.com/youtube/v3"
AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
SCOPES = "https://www.googleapis.com/auth/youtube"

_YT_VIDEO_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
_YT_PLAYLIST_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,128}$")
_YT_CHANNEL_ID_RE = re.compile(r"^UC[A-Za-z0-9_-]{1,128}$")
_SAFE_YT_URL_RE = re.compile(
    r"^https?://(www\.)?(youtube\.com|youtu\.be|music\.youtube\.com)/",
)
MAX_RESULTS = 5000


def _valid_video_id(vid: str) -> bool:
    return bool(_YT_VIDEO_ID_RE.match(vid))


def _valid_playlist_id(pid: str) -> bool:
    return bool(_YT_PLAYLIST_ID_RE.match(pid))


def _valid_channel_id(cid: str) -> bool:
    return bool(_YT_CHANNEL_ID_RE.match(cid))


def _safe_yt_url(url: str) -> bool:
    """Validate a URL is a YouTube domain before passing to yt-dlp."""
    return bool(_SAFE_YT_URL_RE.match(url))


class YouTubeConnector(ConnectorBase):
    service_name = "youtube"
    requires_auth = False  # read operations work without auth via yt-dlp

    def __init__(self, settings: dict):
        super().__init__(settings)
        self._api_key = settings.get("youtube_api_key", "")
        self._client_id = settings.get("youtube_client_id", "")
        self._client_secret = settings.get("youtube_client_secret", "")
        self._lock = threading.Lock()
        acct = load_account("youtube")
        if acct:
            self._access_token = acct.get("access_token", "")
            self._refresh_token = acct.get("refresh_token", "")
            self._token_expiry = acct.get("token_expiry", 0)
        else:
            self._access_token = settings.get("youtube_access_token", "")
            self._refresh_token = settings.get("youtube_refresh_token", "")
            self._token_expiry = 0

    def is_authenticated(self) -> bool:
        return bool(self._access_token or self._api_key)

    # ── OAuth (with state + PKCE) ─────────────────────────────────────────────

    def start_auth(self) -> dict | None:
        if not self._client_id:
            return {"error": "Set youtube_client_id in Settings first"}
        state = generate_state()
        verifier, challenge = generate_pkce()
        params = urlencode({
            "client_id": self._client_id,
            "redirect_uri": REDIRECT_URI,
            "response_type": "code",
            "scope": SCOPES,
            "access_type": "offline",
            "prompt": "consent",
            "state": state,
            "code_challenge_method": "S256",
            "code_challenge": challenge,
        })
        result = start_oauth_flow(f"{AUTH_URL}?{params}", timeout=120,
                                  expected_state=state)
        if not result or "code" not in result:
            return {"error": "OAuth cancelled or timed out"}
        tokens = exchange_code_for_token(
            TOKEN_URL, result["code"], self._client_id, self._client_secret,
            code_verifier=verifier,
        )
        if "error" in tokens:
            return tokens
        self._access_token = tokens.get("access_token", "")
        self._refresh_token = tokens.get("refresh_token", self._refresh_token)
        self._token_expiry = time.time() + tokens.get("expires_in", 3600)
        self._persist_tokens()
        return tokens

    def _persist_tokens(self):
        save_account("youtube", {
            "access_token": self._access_token,
            "refresh_token": self._refresh_token,
            "token_expiry": self._token_expiry,
        })

    def _ensure_token(self) -> bool:
        with self._lock:
            if not self._access_token:
                return False
            if time.time() < self._token_expiry - 60:
                return True
            if not self._refresh_token:
                return False
            tokens = refresh_access_token(
                TOKEN_URL, self._refresh_token, self._client_id, self._client_secret,
            )
            if "error" in tokens:
                return False
            self._access_token = tokens.get("access_token", "")
            self._token_expiry = time.time() + tokens.get("expires_in", 3600)
            if tokens.get("refresh_token"):
                self._refresh_token = tokens["refresh_token"]
            self._persist_tokens()
            return True

    # ── yt-dlp based search (no auth needed) ─────────────────────────────────

    def search(self, query: str, limit: int = 10) -> list[TrackResult]:
        limit = min(limit, 50)
        try:
            import yt_dlp
            ydl_opts = {
                "quiet": True, "no_warnings": True,
                "extract_flat": True, "skip_download": True,
            }
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(f"ytsearch{limit}:{query}", download=False)
            entries = info.get("entries") or []
            out: list[TrackResult] = []
            for e in entries:
                vid = e.get("id", "")
                if not _valid_video_id(vid):
                    continue
                out.append(TrackResult(
                    service="youtube",
                    track_id=vid,
                    title=e.get("title", ""),
                    artist=e.get("uploader") or e.get("channel") or "",
                    duration_ms=(e.get("duration") or 0) * 1000,
                    url=e.get("url") or f"https://www.youtube.com/watch?v={vid}",
                    artwork_url=(e.get("thumbnails") or [{}])[-1].get("url", ""),
                ))
            return out
        except Exception:
            return []

    def get_track(self, track_id: str) -> TrackResult | None:
        if not _valid_video_id(track_id):
            return None
        try:
            import yt_dlp
            url = f"https://www.youtube.com/watch?v={track_id}"
            ydl_opts = {"quiet": True, "no_warnings": True, "skip_download": True}
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
            return TrackResult(
                service="youtube",
                track_id=info.get("id", track_id),
                title=info.get("title", ""),
                artist=info.get("uploader") or info.get("channel") or "",
                duration_ms=(info.get("duration") or 0) * 1000,
                url=info.get("webpage_url", ""),
                artwork_url=(info.get("thumbnails") or [{}])[-1].get("url", ""),
            )
        except Exception:
            return None

    def get_playlist(self, playlist_id_or_url: str) -> PlaylistResult | None:
        try:
            import yt_dlp
            url = playlist_id_or_url
            if not url.startswith("http"):
                if not _valid_playlist_id(url):
                    return None
                url = f"https://www.youtube.com/playlist?list={url}"
            elif not _safe_yt_url(url):
                return None  # reject non-YouTube URLs for yt-dlp
            ydl_opts = {
                "quiet": True, "no_warnings": True,
                "extract_flat": True, "skip_download": True,
            }
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
            entries = (info.get("entries") or [])[:MAX_RESULTS]
            tracks = []
            for e in entries:
                vid = e.get("id", "")
                if not _valid_video_id(vid):
                    continue
                tracks.append(TrackResult(
                    service="youtube",
                    track_id=vid,
                    title=e.get("title", ""),
                    artist=e.get("uploader") or e.get("channel") or "",
                    duration_ms=(e.get("duration") or 0) * 1000,
                    url=e.get("url") or f"https://www.youtube.com/watch?v={vid}",
                ))
            return PlaylistResult(
                service="youtube",
                playlist_id=info.get("id", ""),
                name=info.get("title", ""),
                description=info.get("description", ""),
                owner=info.get("uploader") or "",
                track_count=len(tracks),
                tracks=tracks,
                url=info.get("webpage_url", ""),
            )
        except Exception:
            return None

    # ── YouTube Data API v3 write operations ─────────────────────────────────

    def _api_headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._access_token}"}

    def _api_params(self) -> dict[str, str]:
        if self._api_key and not self._access_token:
            return {"key": self._api_key}
        return {}

    def create_playlist(self, name: str, description: str = "") -> str | None:
        if not self._ensure_token():
            return None
        try:
            r = requests.post(
                f"{YT_API}/playlists",
                headers=self._api_headers(),
                params={"part": "snippet,status"},
                json={
                    "snippet": {"title": name, "description": description},
                    "status": {"privacyStatus": "private"},
                },
                timeout=20,
            )
            r.raise_for_status()
            return r.json().get("id")
        except Exception as e:
            return None

    def add_tracks(self, playlist_id: str, track_ids: list[str]) -> int:
        if not self._ensure_token():
            return 0
        if not _valid_playlist_id(playlist_id):
            return 0
        added = 0
        for vid in track_ids:
            if not _valid_video_id(vid):
                continue
            try:
                r = requests.post(
                    f"{YT_API}/playlistItems",
                    headers=self._api_headers(),
                    params={"part": "snippet"},
                    json={
                        "snippet": {
                            "playlistId": playlist_id,
                            "resourceId": {"kind": "youtube#video", "videoId": vid},
                        }
                    },
                    timeout=20,
                )
                r.raise_for_status()
                added += 1
            except Exception:
                continue
        return added

    def supports_write(self) -> bool:
        return bool(self._access_token)

    # ── Liked songs (YouTube "Liked videos" playlist) ─────────────────────────

    def get_liked_songs(self, limit: int = 500) -> list[TrackResult]:
        limit = min(limit, 5000)
        if not self._ensure_token():
            return []
        tracks: list[TrackResult] = []
        params: dict = {"part": "snippet", "myRating": "like", "maxResults": min(limit, 50)}
        while len(tracks) < limit:
            try:
                r = requests.get(f"{YT_API}/videos", headers=self._api_headers(),
                                 params=params, timeout=20)
                r.raise_for_status()
                data = r.json()
            except Exception:
                break
            for item in data.get("items", []):
                snip = item.get("snippet", {})
                vid = item.get("id", "")
                if not _valid_video_id(vid):
                    continue
                tracks.append(TrackResult(
                    service="youtube",
                    track_id=vid,
                    title=snip.get("title", ""),
                    artist=snip.get("channelTitle", ""),
                    url=f"https://www.youtube.com/watch?v={vid}",
                    artwork_url=(snip.get("thumbnails") or {}).get("high", {}).get("url", ""),
                ))
            npt = data.get("nextPageToken")
            if not npt:
                break
            params["pageToken"] = npt
        return tracks[:limit]

    def add_to_liked(self, track_ids: list[str]) -> int:
        if not self._ensure_token():
            return 0
        added = 0
        for vid in track_ids:
            if not _valid_video_id(vid):
                continue
            try:
                r = requests.post(
                    f"{YT_API}/videos/rate",
                    headers=self._api_headers(),
                    params={"id": vid, "rating": "like"},
                    timeout=20,
                )
                r.raise_for_status()
                added += 1
            except Exception:
                continue
        return added

    def remove_from_liked(self, track_ids: list[str]) -> int:
        if not self._ensure_token():
            return 0
        removed = 0
        for vid in track_ids:
            if not _valid_video_id(vid):
                continue
            try:
                r = requests.post(
                    f"{YT_API}/videos/rate",
                    headers=self._api_headers(),
                    params={"id": vid, "rating": "none"},
                    timeout=20,
                )
                r.raise_for_status()
                removed += 1
            except Exception:
                continue
        return removed

    # ── Subscriptions (closest to "followed artists") ─────────────────────────

    def get_followed_artists(self, limit: int = 500) -> list[dict]:
        limit = min(limit, 5000)
        if not self._ensure_token():
            return []
        channels: list[dict] = []
        params: dict = {"part": "snippet", "mine": "true", "maxResults": min(limit, 50)}
        while len(channels) < limit:
            try:
                r = requests.get(f"{YT_API}/subscriptions", headers=self._api_headers(),
                                 params=params, timeout=20)
                r.raise_for_status()
                data = r.json()
            except Exception:
                break
            for item in data.get("items", []):
                snip = item.get("snippet", {}).get("resourceId", {})
                cid = snip.get("channelId", "")
                channels.append({
                    "id": cid,
                    "name": item.get("snippet", {}).get("title", ""),
                    "url": f"https://www.youtube.com/channel/{cid}" if cid else "",
                })
            npt = data.get("nextPageToken")
            if not npt:
                break
            params["pageToken"] = npt
        return channels[:limit]

    def follow_artist(self, artist_id: str) -> bool:
        if not self._ensure_token():
            return False
        try:
            r = requests.post(
                f"{YT_API}/subscriptions",
                headers=self._api_headers(),
                params={"part": "snippet"},
                json={"snippet": {"resourceId": {"kind": "youtube#channel", "channelId": artist_id}}},
                timeout=20,
            )
            r.raise_for_status()
            return True
        except Exception:
            return False
