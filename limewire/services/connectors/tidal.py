"""TIDAL connector — developer API with OAuth PKCE."""

from __future__ import annotations

import threading
import time
from urllib.parse import urlencode

import requests

from .base import ConnectorBase, TrackResult, PlaylistResult
from .oauth import REDIRECT_URI, start_oauth_flow, exchange_code_for_token, refresh_access_token
from .storage import save_account, load_account

API = "https://openapi.tidal.com"
AUTH_URL = "https://login.tidal.com/authorize"
TOKEN_URL = "https://auth.tidal.com/v1/oauth2/token"


class TidalConnector(ConnectorBase):
    service_name = "tidal"
    requires_auth = True

    def __init__(self, settings: dict):
        super().__init__(settings)
        self._client_id = settings.get("tidal_client_id", "")
        self._client_secret = settings.get("tidal_client_secret", "")
        self._lock = threading.Lock()
        acct = load_account("tidal")
        if acct:
            self._access_token = acct.get("access_token", "")
            self._refresh_token = acct.get("refresh_token", "")
            self._token_expiry = acct.get("token_expiry", 0)
        else:
            self._access_token = settings.get("tidal_access_token", "")
            self._refresh_token = settings.get("tidal_refresh_token", "")
            self._token_expiry = 0

    def is_authenticated(self) -> bool:
        return bool(self._access_token)

    # ── OAuth ────────────────────────────────────────────────────────────────

    def start_auth(self) -> dict | None:
        if not self._client_id:
            return {"error": "Set tidal_client_id in Settings first"}
        params = urlencode({
            "client_id": self._client_id,
            "redirect_uri": REDIRECT_URI,
            "response_type": "code",
            "scope": "playlists.read playlists.write collection.read collection.write",
        })
        result = start_oauth_flow(f"{AUTH_URL}?{params}", timeout=120)
        if not result or "code" not in result:
            return {"error": "OAuth cancelled or timed out"}
        tokens = exchange_code_for_token(
            TOKEN_URL, result["code"], self._client_id, self._client_secret,
        )
        if "error" in tokens:
            return tokens
        self._access_token = tokens.get("access_token", "")
        self._refresh_token = tokens.get("refresh_token", self._refresh_token)
        self._token_expiry = time.time() + tokens.get("expires_in", 3600)
        self._persist_tokens()
        return tokens

    def _persist_tokens(self):
        save_account("tidal", {
            "access_token": self._access_token,
            "refresh_token": self._refresh_token,
            "client_id": self._client_id,
            "client_secret": self._client_secret,
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

    # ── HTTP ─────────────────────────────────────────────────────────────────

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._access_token}"}

    def _api_get(self, path: str, params: dict | None = None) -> dict:
        self._ensure_token()
        try:
            r = requests.get(f"{API}{path}", headers=self._headers(),
                             params=params, timeout=20)
            if r.status_code == 429:
                time.sleep(2)
                r = requests.get(f"{API}{path}", headers=self._headers(),
                                 params=params, timeout=20)
            r.raise_for_status()
            return r.json()
        except Exception as e:
            return {"error": str(e)[:200]}

    def _api_post(self, path: str, json: dict | None = None) -> dict:
        self._ensure_token()
        try:
            r = requests.post(f"{API}{path}", headers=self._headers(),
                              json=json, timeout=20)
            r.raise_for_status()
            return r.json() if r.text.strip() else {}
        except Exception as e:
            return {"error": str(e)[:200]}

    # ── Track parsing ────────────────────────────────────────────────────────

    def _parse_track(self, item: dict) -> TrackResult:
        resource = item.get("resource") or item
        attrs = resource.get("attributes") or resource
        title = attrs.get("title", "")
        isrc = attrs.get("isrc", "")
        duration = attrs.get("duration") or attrs.get("durationInSeconds") or 0
        # Try to get artist name
        artists_rel = (resource.get("relationships") or {}).get("artists", {})
        artist_data = artists_rel.get("data") or []
        artist_names = []
        for a in artist_data:
            a_attrs = (a.get("attributes") or {})
            name = a_attrs.get("name", "")
            if name:
                artist_names.append(name)
        artist_str = ", ".join(artist_names) if artist_names else attrs.get("artistName", "")

        return TrackResult(
            service="tidal",
            track_id=str(resource.get("id", "")),
            title=title,
            artist=artist_str,
            duration_ms=duration * 1000 if duration else 0,
            isrc=isrc,
            url=attrs.get("externalLink", ""),
        )

    # ── Public interface ─────────────────────────────────────────────────────

    def search(self, query: str, limit: int = 10) -> list[TrackResult]:
        data = self._api_get("/searchresults", {
            "query": query, "limit": limit, "type": "TRACKS",
        })
        if "error" in data:
            return []
        # Handle different response shapes
        items = data.get("data") or data.get("tracks") or []
        if isinstance(items, dict):
            items = items.get("data", [])
        return [self._parse_track(item) for item in items]

    def get_track(self, track_id: str) -> TrackResult | None:
        data = self._api_get(f"/tracks/{track_id}")
        if "error" in data:
            return None
        resource = data.get("data") or data.get("resource") or data
        if isinstance(resource, list):
            resource = resource[0] if resource else {}
        return self._parse_track(resource)

    def get_playlist(self, playlist_id_or_url: str) -> PlaylistResult | None:
        pid = playlist_id_or_url
        if "tidal.com" in pid:
            from .utils import extract_tidal_id
            _, pid = extract_tidal_id(pid)
            if not pid:
                return None

        data = self._api_get(f"/playlists/{pid}")
        if "error" in data:
            return None

        p_resource = data.get("data") or data
        if isinstance(p_resource, list):
            p_resource = p_resource[0] if p_resource else {}
        p_attrs = p_resource.get("attributes") or p_resource

        # Fetch tracks
        items_data = self._api_get(f"/playlists/{pid}/relationships/items")
        tracks_list = items_data.get("data") or []
        tracks = [self._parse_track(t) for t in tracks_list]

        return PlaylistResult(
            service="tidal",
            playlist_id=str(p_resource.get("id", pid)),
            name=p_attrs.get("name", ""),
            description=p_attrs.get("description", ""),
            track_count=len(tracks),
            tracks=tracks,
        )

    def create_playlist(self, name: str, description: str = "") -> str | None:
        data = self._api_post("/playlists", {
            "data": {
                "type": "playlists",
                "attributes": {"name": name, "description": description},
            }
        })
        if "error" in data:
            return None
        resource = data.get("data") or data
        if isinstance(resource, list):
            resource = resource[0] if resource else {}
        return str(resource.get("id", ""))

    def add_tracks(self, playlist_id: str, track_ids: list[str]) -> int:
        result = self._api_post(f"/playlists/{playlist_id}/relationships/items", {
            "data": [{"id": tid, "type": "tracks"} for tid in track_ids],
        })
        if "error" not in result:
            return len(track_ids)
        return 0

    def supports_write(self) -> bool:
        return self.is_authenticated()

    # ── Liked songs (favorites) ───────────────────────────────────────────────

    def get_liked_songs(self, limit: int = 500) -> list[TrackResult]:
        tracks: list[TrackResult] = []
        offset = 0
        batch = min(limit, 100)
        while len(tracks) < limit:
            data = self._api_get("/me/favorites/tracks", {"limit": batch, "offset": offset})
            if "error" in data:
                break
            items = data.get("data") or []
            if not items:
                break
            for item in items:
                tracks.append(self._parse_track(item))
            offset += len(items)
            if len(items) < batch:
                break
        return tracks[:limit]

    def add_to_liked(self, track_ids: list[str]) -> int:
        self._ensure_token()
        added = 0
        for tid in track_ids:
            try:
                r = requests.post(
                    f"{API}/me/favorites/tracks",
                    headers=self._headers(),
                    json={"data": [{"id": tid, "type": "tracks"}]},
                    timeout=20,
                )
                r.raise_for_status()
                added += 1
            except Exception:
                continue
        return added

    def remove_from_liked(self, track_ids: list[str]) -> int:
        self._ensure_token()
        removed = 0
        for tid in track_ids:
            try:
                r = requests.delete(
                    f"{API}/me/favorites/tracks/{tid}",
                    headers=self._headers(), timeout=20,
                )
                r.raise_for_status()
                removed += 1
            except Exception:
                continue
        return removed

    # ── Followed artists ──────────────────────────────────────────────────────

    def get_followed_artists(self, limit: int = 500) -> list[dict]:
        artists: list[dict] = []
        offset = 0
        batch = min(limit, 100)
        while len(artists) < limit:
            data = self._api_get("/me/favorites/artists", {"limit": batch, "offset": offset})
            if "error" in data:
                break
            items = data.get("data") or []
            if not items:
                break
            for item in items:
                resource = item.get("resource") or item
                attrs = resource.get("attributes") or resource
                artists.append({
                    "id": str(resource.get("id", "")),
                    "name": attrs.get("name", ""),
                    "url": attrs.get("externalLink", ""),
                })
            offset += len(items)
            if len(items) < batch:
                break
        return artists[:limit]

    def follow_artist(self, artist_id: str) -> bool:
        self._ensure_token()
        try:
            r = requests.post(
                f"{API}/me/favorites/artists",
                headers=self._headers(),
                json={"data": [{"id": artist_id, "type": "artists"}]},
                timeout=20,
            )
            r.raise_for_status()
            return True
        except Exception:
            return False

    # ── Saved albums ──────────────────────────────────────────────────────────

    def get_saved_albums(self, limit: int = 500) -> list[dict]:
        albums: list[dict] = []
        offset = 0
        batch = min(limit, 100)
        while len(albums) < limit:
            data = self._api_get("/me/favorites/albums", {"limit": batch, "offset": offset})
            if "error" in data:
                break
            items = data.get("data") or []
            if not items:
                break
            for item in items:
                resource = item.get("resource") or item
                attrs = resource.get("attributes") or resource
                albums.append({
                    "id": str(resource.get("id", "")),
                    "title": attrs.get("title", ""),
                    "artist": attrs.get("artistName", ""),
                    "url": attrs.get("externalLink", ""),
                })
            offset += len(items)
            if len(items) < batch:
                break
        return albums[:limit]

    def save_album(self, album_id: str) -> bool:
        self._ensure_token()
        try:
            r = requests.post(
                f"{API}/me/favorites/albums",
                headers=self._headers(),
                json={"data": [{"id": album_id, "type": "albums"}]},
                timeout=20,
            )
            r.raise_for_status()
            return True
        except Exception:
            return False
