"""Spotify Web API connector — search, track/playlist lookup, and write operations."""

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

API = "https://api.spotify.com/v1"
AUTH_URL = "https://accounts.spotify.com/authorize"
TOKEN_URL = "https://accounts.spotify.com/api/token"
SCOPES = "playlist-read-private playlist-modify-public playlist-modify-private user-library-read user-library-modify user-follow-read user-follow-modify"

_SPOTIFY_ID_RE = re.compile(r"^[A-Za-z0-9]{1,64}$")
MAX_TRACKS = 10000


def _valid_id(sid: str) -> bool:
    """Validate a Spotify ID is alphanumeric (no path traversal)."""
    return bool(_SPOTIFY_ID_RE.match(sid))


class SpotifyConnector(ConnectorBase):
    service_name = "spotify"
    requires_auth = True

    def __init__(self, settings: dict):
        super().__init__(settings)
        self._client_id = settings.get("spotify_client_id", "")
        self._client_secret = settings.get("spotify_client_secret", "")
        self._lock = threading.Lock()
        # Load persisted tokens
        acct = load_account("spotify")
        if acct:
            self._access_token = acct.get("access_token", "")
            self._refresh_token = acct.get("refresh_token", "")
            self._token_expiry = acct.get("token_expiry", 0)
        else:
            self._access_token = settings.get("spotify_access_token", "")
            self._refresh_token = settings.get("spotify_refresh_token", "")
            self._token_expiry = settings.get("spotify_token_expiry", 0)

    def is_authenticated(self) -> bool:
        return bool(self._access_token)

    # ── OAuth flow ───────────────────────────────────────────────────────────

    def start_auth(self) -> dict | None:
        """Launch OAuth in browser, wait for callback. Returns token dict or None."""
        if not self._client_id:
            return {"error": "Set spotify_client_id in Settings first"}
        state = generate_state()
        verifier, challenge = generate_pkce()
        params = urlencode({
            "client_id": self._client_id,
            "response_type": "code",
            "redirect_uri": REDIRECT_URI,
            "scope": SCOPES,
            "show_dialog": "true",
            "state": state,
            "code_challenge_method": "S256",
            "code_challenge": challenge,
        })
        url = f"{AUTH_URL}?{params}"
        result = start_oauth_flow(url, timeout=120, expected_state=state)
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
        save_account("spotify", {
            "access_token": self._access_token,
            "refresh_token": self._refresh_token,
            "token_expiry": self._token_expiry,
        })

    def _ensure_token(self) -> bool:
        """Refresh token if expired. Returns True if valid token available."""
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

    # ── HTTP helpers ─────────────────────────────────────────────────────────

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._access_token}"}

    def _api_get(self, path: str, params: dict | None = None) -> dict:
        self._ensure_token()
        try:
            r = requests.get(f"{API}{path}", headers=self._headers(),
                             params=params, timeout=20)
            if r.status_code == 429:
                retry = int(r.headers.get("Retry-After", "2"))
                time.sleep(min(retry, 10))
                r = requests.get(f"{API}{path}", headers=self._headers(),
                                 params=params, timeout=20)
            r.raise_for_status()
            return r.json()
        except Exception as e:
            return {"error": _sanitize_error(e)}

    def _api_post(self, path: str, json: dict | list | None = None) -> dict:
        self._ensure_token()
        try:
            r = requests.post(f"{API}{path}", headers=self._headers(),
                              json=json, timeout=20)
            r.raise_for_status()
            return r.json() if r.text.strip() else {}
        except Exception as e:
            return {"error": _sanitize_error(e)}

    # ── Track parsing ────────────────────────────────────────────────────────

    def _parse_track(self, item: dict) -> TrackResult:
        album = item.get("album") or {}
        ext_ids = item.get("external_ids") or {}
        ext_urls = item.get("external_urls") or {}
        images = album.get("images") or []
        artists = [a.get("name", "") for a in item.get("artists", []) if a.get("name")]
        return TrackResult(
            service="spotify",
            track_id=item.get("id", ""),
            title=item.get("name", ""),
            artist=", ".join(artists),
            album=album.get("name", ""),
            duration_ms=item.get("duration_ms", 0),
            isrc=ext_ids.get("isrc", ""),
            url=ext_urls.get("spotify", ""),
            artwork_url=images[0]["url"] if images else "",
            preview_url=item.get("preview_url") or "",
        )

    # ── Public interface ─────────────────────────────────────────────────────

    def search(self, query: str, limit: int = 10) -> list[TrackResult]:
        limit = min(limit, 50)
        data = self._api_get("/search", {"q": query, "type": "track", "limit": limit})
        if "error" in data:
            return []
        return [self._parse_track(t) for t in data.get("tracks", {}).get("items", [])]

    def get_track(self, track_id: str) -> TrackResult | None:
        if not _valid_id(track_id):
            return None
        data = self._api_get(f"/tracks/{track_id}")
        if "error" in data:
            return None
        return self._parse_track(data)

    def get_playlist(self, playlist_id_or_url: str) -> PlaylistResult | None:
        # Extract ID from URL if needed
        pid = playlist_id_or_url
        if "spotify.com" in pid:
            from .utils import extract_spotify_id
            _, pid = extract_spotify_id(pid)
            if not pid:
                return None
        if not _valid_id(pid):
            return None

        data = self._api_get(f"/playlists/{pid}")
        if "error" in data:
            return None

        # Fetch all tracks with pagination (bounded)
        tracks: list[TrackResult] = []
        tracks_data = data.get("tracks", {})
        for item in tracks_data.get("items", []):
            t = item.get("track")
            if t:
                tracks.append(self._parse_track(t))

        # Paginate — validate next_url stays on Spotify API domain
        next_url = tracks_data.get("next")
        while next_url and len(tracks) < MAX_TRACKS:
            if not next_url.startswith("https://api.spotify.com/"):
                break  # SSRF protection
            try:
                r = requests.get(next_url, headers=self._headers(), timeout=20)
                r.raise_for_status()
                page = r.json()
                for item in page.get("items", []):
                    t = item.get("track")
                    if t:
                        tracks.append(self._parse_track(t))
                next_url = page.get("next")
            except Exception:
                break

        return PlaylistResult(
            service="spotify",
            playlist_id=data.get("id", pid),
            name=data.get("name", ""),
            description=data.get("description", ""),
            owner=(data.get("owner") or {}).get("display_name", ""),
            track_count=len(tracks),
            tracks=tracks,
            url=(data.get("external_urls") or {}).get("spotify", ""),
        )

    def list_user_playlists(self) -> list[PlaylistResult]:
        data = self._api_get("/me/playlists", {"limit": 50})
        if "error" in data:
            return []
        out: list[PlaylistResult] = []
        for p in data.get("items", []):
            out.append(PlaylistResult(
                service="spotify",
                playlist_id=p.get("id", ""),
                name=p.get("name", ""),
                description=p.get("description", ""),
                owner=(p.get("owner") or {}).get("display_name", ""),
                track_count=p.get("tracks", {}).get("total", 0),
                url=(p.get("external_urls") or {}).get("spotify", ""),
            ))
        return out

    def create_playlist(self, name: str, description: str = "") -> str | None:
        me = self._api_get("/me")
        if "error" in me:
            return None
        user_id = me.get("id")
        if not _valid_id(user_id):
            return None
        data = self._api_post(f"/users/{user_id}/playlists", {
            "name": name, "description": description, "public": False,
        })
        return data.get("id")

    def add_tracks(self, playlist_id: str, track_ids: list[str]) -> int:
        if not _valid_id(playlist_id):
            return 0
        added = 0
        uris = [f"spotify:track:{tid}" for tid in track_ids if _valid_id(tid)]
        for i in range(0, len(uris), 100):
            batch = uris[i:i + 100]
            result = self._api_post(f"/playlists/{playlist_id}/tracks", {"uris": batch})
            if "error" not in result:
                added += len(batch)
        return added

    def supports_write(self) -> bool:
        return self.is_authenticated()

    # ── Liked songs ──────────────────────────────────────────────────────────

    def get_liked_songs(self, limit: int = 500) -> list[TrackResult]:
        limit = min(limit, 5000)
        tracks: list[TrackResult] = []
        offset = 0
        batch = min(limit, 50)
        while len(tracks) < limit:
            data = self._api_get("/me/tracks", {"limit": batch, "offset": offset})
            if "error" in data:
                break
            items = data.get("items", [])
            if not items:
                break
            for item in items:
                t = item.get("track")
                if t:
                    tracks.append(self._parse_track(t))
            offset += len(items)
            if not data.get("next"):
                break
        return tracks[:limit]

    def add_to_liked(self, track_ids: list[str]) -> int:
        added = 0
        valid_ids = [tid for tid in track_ids if _valid_id(tid)]
        for i in range(0, len(valid_ids), 50):
            batch = valid_ids[i:i + 50]
            try:
                r = requests.put(
                    f"{API}/me/tracks", headers=self._headers(),
                    json={"ids": batch}, timeout=20,
                )
                r.raise_for_status()
                added += len(batch)
            except Exception:
                continue
        return added

    def remove_from_liked(self, track_ids: list[str]) -> int:
        removed = 0
        valid_ids = [tid for tid in track_ids if _valid_id(tid)]
        for i in range(0, len(valid_ids), 50):
            batch = valid_ids[i:i + 50]
            try:
                r = requests.delete(
                    f"{API}/me/tracks", headers=self._headers(),
                    json={"ids": batch}, timeout=20,
                )
                r.raise_for_status()
                removed += len(batch)
            except Exception:
                continue
        return removed

    # ── Followed artists ─────────────────────────────────────────────────────

    def get_followed_artists(self, limit: int = 500) -> list[dict]:
        limit = min(limit, 5000)
        artists: list[dict] = []
        params: dict = {"type": "artist", "limit": min(limit, 50)}
        while len(artists) < limit:
            data = self._api_get("/me/following", params)
            if "error" in data:
                break
            items = (data.get("artists") or {}).get("items", [])
            if not items:
                break
            for a in items:
                artists.append({
                    "id": a.get("id", ""),
                    "name": a.get("name", ""),
                    "url": (a.get("external_urls") or {}).get("spotify", ""),
                })
            cursor_after = (data.get("artists") or {}).get("cursors", {}).get("after")
            if not cursor_after:
                break
            params["after"] = cursor_after
        return artists[:limit]

    def follow_artist(self, artist_id: str) -> bool:
        if not _valid_id(artist_id):
            return False
        self._ensure_token()
        try:
            r = requests.put(
                f"{API}/me/following", headers=self._headers(),
                params={"type": "artist", "ids": artist_id}, timeout=20,
            )
            r.raise_for_status()
            return True
        except Exception:
            return False

    # ── Saved albums ─────────────────────────────────────────────────────────

    def get_saved_albums(self, limit: int = 500) -> list[dict]:
        limit = min(limit, 5000)
        albums: list[dict] = []
        offset = 0
        batch = min(limit, 50)
        while len(albums) < limit:
            data = self._api_get("/me/albums", {"limit": batch, "offset": offset})
            if "error" in data:
                break
            items = data.get("items", [])
            if not items:
                break
            for item in items:
                a = item.get("album", {})
                artists = [x.get("name", "") for x in a.get("artists", [])]
                albums.append({
                    "id": a.get("id", ""),
                    "title": a.get("name", ""),
                    "artist": ", ".join(artists),
                    "url": (a.get("external_urls") or {}).get("spotify", ""),
                })
            offset += len(items)
            if not data.get("next"):
                break
        return albums[:limit]

    def save_album(self, album_id: str) -> bool:
        if not _valid_id(album_id):
            return False
        self._ensure_token()
        try:
            r = requests.put(
                f"{API}/me/albums", headers=self._headers(),
                json={"ids": [album_id]}, timeout=20,
            )
            r.raise_for_status()
            return True
        except Exception:
            return False
