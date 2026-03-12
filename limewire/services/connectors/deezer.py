"""Deezer connector — public API for search/read, OAuth for write operations."""

from __future__ import annotations

import re
import threading
import time
from urllib.parse import urlencode

import requests

from .base import ConnectorBase, TrackResult, PlaylistResult
from .oauth import REDIRECT_URI, start_oauth_flow, generate_state, _sanitize_error
from .storage import save_account, load_account

API = "https://api.deezer.com"
AUTH_URL = "https://connect.deezer.com/oauth/auth.php"
TOKEN_URL = "https://connect.deezer.com/oauth/access_token.php"
PERMS = "basic_access,manage_library,offline_access"

_DEEZER_ID_RE = re.compile(r"^\d{1,20}$")
MAX_TRACKS = 10000


def _valid_id(did: str) -> bool:
    """Validate a Deezer numeric ID."""
    return bool(_DEEZER_ID_RE.match(str(did)))


class DeezerConnector(ConnectorBase):
    service_name = "deezer"
    requires_auth = False  # search works without auth

    def __init__(self, settings: dict):
        super().__init__(settings)
        self._app_id = settings.get("deezer_app_id", "")
        self._app_secret = settings.get("deezer_app_secret", "")
        self._lock = threading.Lock()
        acct = load_account("deezer")
        if acct:
            self._access_token = acct.get("access_token", "")
            self._user_id = acct.get("user_id", "")
        else:
            self._access_token = settings.get("deezer_access_token", "")
            self._user_id = ""

    def is_authenticated(self) -> bool:
        return bool(self._access_token)

    # ── OAuth (with state for CSRF) ──────────────────────────────────────────

    def start_auth(self) -> dict | None:
        if not self._app_id:
            return {"error": "Set deezer_app_id in Settings first"}
        state = generate_state()
        params = urlencode({
            "app_id": self._app_id,
            "redirect_uri": REDIRECT_URI,
            "perms": PERMS,
            "state": state,
        })
        result = start_oauth_flow(f"{AUTH_URL}?{params}", timeout=120,
                                  expected_state=state)
        if not result or "code" not in result:
            return {"error": "OAuth cancelled or timed out"}
        # Deezer token exchange is GET-based, returns text not JSON
        try:
            r = requests.get(TOKEN_URL, params={
                "app_id": self._app_id,
                "secret": self._app_secret,
                "code": result["code"],
                "output": "json",
            }, timeout=20)
            r.raise_for_status()
            tokens = r.json()
        except Exception as e:
            return {"error": _sanitize_error(e)}
        if "access_token" not in tokens:
            return {"error": tokens.get("error_reason", "Token exchange failed")}
        self._access_token = tokens["access_token"]
        # Get user info
        try:
            me = requests.get(f"{API}/user/me", params={"access_token": self._access_token}, timeout=10).json()
            self._user_id = str(me.get("id", ""))
            user_name = me.get("name", "")
        except Exception:
            self._user_id = ""
            user_name = ""
        save_account("deezer", {
            "access_token": self._access_token,
            "user_id": self._user_id,
            "user_name": user_name,
        })
        return tokens

    # ── HTTP helpers ─────────────────────────────────────────────────────────

    def _params(self) -> dict:
        if self._access_token:
            return {"access_token": self._access_token}
        return {}

    def _api_get(self, path: str, params: dict | None = None) -> dict:
        p = {**self._params(), **(params or {})}
        try:
            r = requests.get(f"{API}{path}", params=p, timeout=20)
            r.raise_for_status()
            data = r.json()
            if "error" in data:
                return {"error": data["error"].get("message", str(data["error"]))}
            return data
        except Exception as e:
            return {"error": _sanitize_error(e)}

    # ── Track parsing ────────────────────────────────────────────────────────

    def _parse_track(self, item: dict) -> TrackResult:
        artist = item.get("artist") or {}
        album = item.get("album") or {}
        return TrackResult(
            service="deezer",
            track_id=str(item.get("id", "")),
            title=item.get("title", ""),
            artist=artist.get("name", ""),
            album=album.get("title", ""),
            duration_ms=(item.get("duration") or 0) * 1000,
            isrc=item.get("isrc", ""),
            url=item.get("link", ""),
            artwork_url=album.get("cover_big") or album.get("cover_medium", ""),
            preview_url=item.get("preview", ""),
        )

    # ── Public interface ─────────────────────────────────────────────────────

    def search(self, query: str, limit: int = 10) -> list[TrackResult]:
        limit = min(limit, 50)
        data = self._api_get("/search", {"q": query, "limit": limit})
        if "error" in data:
            return []
        return [self._parse_track(t) for t in data.get("data", [])]

    def get_track(self, track_id: str) -> TrackResult | None:
        if not _valid_id(track_id):
            return None
        data = self._api_get(f"/track/{track_id}")
        if "error" in data:
            return None
        return self._parse_track(data)

    def get_playlist(self, playlist_id_or_url: str) -> PlaylistResult | None:
        pid = playlist_id_or_url
        # Extract ID from URL
        if "deezer.com" in pid:
            m = re.search(r"playlist/(\d+)", pid)
            if m:
                pid = m.group(1)
            else:
                return None
        if not _valid_id(pid):
            return None

        data = self._api_get(f"/playlist/{pid}")
        if "error" in data:
            return None

        tracks = [self._parse_track(t) for t in data.get("tracks", {}).get("data", [])[:MAX_TRACKS]]
        return PlaylistResult(
            service="deezer",
            playlist_id=str(data.get("id", pid)),
            name=data.get("title", ""),
            description=data.get("description", ""),
            owner=(data.get("creator") or {}).get("name", ""),
            track_count=len(tracks),
            tracks=tracks,
            url=data.get("link", ""),
        )

    def list_user_playlists(self) -> list[PlaylistResult]:
        if not self._access_token:
            return []
        data = self._api_get("/user/me/playlists")
        if "error" in data:
            return []
        out: list[PlaylistResult] = []
        for p in data.get("data", []):
            out.append(PlaylistResult(
                service="deezer",
                playlist_id=str(p.get("id", "")),
                name=p.get("title", ""),
                track_count=p.get("nb_tracks", 0),
                url=p.get("link", ""),
            ))
        return out

    def create_playlist(self, name: str, description: str = "") -> str | None:
        if not self._access_token or not self._user_id:
            return None
        if not _valid_id(self._user_id):
            return None
        try:
            r = requests.post(
                f"{API}/user/{self._user_id}/playlists",
                params=self._params(),
                data={"title": name},
                timeout=20,
            )
            r.raise_for_status()
            return str(r.json().get("id", ""))
        except Exception:
            return None

    def add_tracks(self, playlist_id: str, track_ids: list[str]) -> int:
        if not self._access_token:
            return 0
        if not _valid_id(playlist_id):
            return 0
        valid_ids = [tid for tid in track_ids if _valid_id(tid)]
        if not valid_ids:
            return 0
        try:
            r = requests.post(
                f"{API}/playlist/{playlist_id}/tracks",
                params=self._params(),
                data={"songs": ",".join(valid_ids)},
                timeout=20,
            )
            r.raise_for_status()
            return len(valid_ids) if r.json() is True else 0
        except Exception:
            return 0

    def supports_write(self) -> bool:
        return self.is_authenticated()

    # ── Liked songs ──────────────────────────────────────────────────────────

    def get_liked_songs(self, limit: int = 500) -> list[TrackResult]:
        limit = min(limit, 5000)
        if not self._access_token:
            return []
        data = self._api_get("/user/me/tracks", {"limit": min(limit, 200)})
        if "error" in data:
            return []
        return [self._parse_track(t) for t in data.get("data", [])[:limit]]

    def add_to_liked(self, track_ids: list[str]) -> int:
        if not self._access_token:
            return 0
        added = 0
        for tid in track_ids:
            if not _valid_id(tid):
                continue
            try:
                r = requests.post(
                    f"{API}/user/me/tracks",
                    params={**self._params(), "track_id": tid},
                    timeout=10,
                )
                if r.json() is True:
                    added += 1
            except Exception:
                continue
        return added

    def remove_from_liked(self, track_ids: list[str]) -> int:
        if not self._access_token:
            return 0
        removed = 0
        for tid in track_ids:
            if not _valid_id(tid):
                continue
            try:
                r = requests.delete(
                    f"{API}/user/me/tracks",
                    params={**self._params(), "track_id": tid},
                    timeout=10,
                )
                if r.json() is True:
                    removed += 1
            except Exception:
                continue
        return removed

    # ── Followed artists ─────────────────────────────────────────────────────

    def get_followed_artists(self, limit: int = 500) -> list[dict]:
        limit = min(limit, 5000)
        if not self._access_token:
            return []
        data = self._api_get("/user/me/artists", {"limit": min(limit, 200)})
        if "error" in data:
            return []
        return [{"id": str(a.get("id", "")), "name": a.get("name", ""),
                 "url": a.get("link", "")} for a in data.get("data", [])[:limit]]

    def follow_artist(self, artist_id: str) -> bool:
        if not self._access_token:
            return False
        if not _valid_id(artist_id):
            return False
        try:
            r = requests.post(
                f"{API}/user/me/artists",
                params={**self._params(), "artist_id": artist_id},
                timeout=10,
            )
            return r.json() is True
        except Exception:
            return False

    # ── Saved albums ─────────────────────────────────────────────────────────

    def get_saved_albums(self, limit: int = 500) -> list[dict]:
        limit = min(limit, 5000)
        if not self._access_token:
            return []
        data = self._api_get("/user/me/albums", {"limit": min(limit, 200)})
        if "error" in data:
            return []
        return [{"id": str(a.get("id", "")), "title": a.get("title", ""),
                 "artist": (a.get("artist") or {}).get("name", ""),
                 "url": a.get("link", "")} for a in data.get("data", [])[:limit]]

    def save_album(self, album_id: str) -> bool:
        if not self._access_token:
            return False
        if not _valid_id(album_id):
            return False
        try:
            r = requests.post(
                f"{API}/user/me/albums",
                params={**self._params(), "album_id": album_id},
                timeout=10,
            )
            return r.json() is True
        except Exception:
            return False
