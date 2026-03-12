"""SoundCloud connector — yt-dlp for search, API for authenticated operations."""

from __future__ import annotations

import requests

from .base import ConnectorBase, TrackResult, PlaylistResult
from .storage import load_account, save_account

SC_API = "https://api.soundcloud.com"


class SoundCloudConnector(ConnectorBase):
    service_name = "soundcloud"
    requires_auth = False  # search works via yt-dlp without auth

    def __init__(self, settings: dict):
        super().__init__(settings)
        self._client_id = settings.get("soundcloud_client_id", "")
        acct = load_account("soundcloud")
        if acct:
            self._access_token = acct.get("access_token", "")
        else:
            self._access_token = settings.get("soundcloud_access_token", "")

    def is_authenticated(self) -> bool:
        return bool(self._access_token)

    def _headers(self) -> dict[str, str]:
        if self._access_token:
            return {"Authorization": f"OAuth {self._access_token}"}
        return {}

    def _parse_track(self, item: dict) -> TrackResult:
        user = item.get("user") or {}
        pub = item.get("publisher_metadata") or {}
        return TrackResult(
            service="soundcloud",
            track_id=str(item.get("id", "")),
            title=item.get("title", ""),
            artist=user.get("username", ""),
            album=pub.get("album_title", ""),
            duration_ms=item.get("duration", 0),
            isrc=pub.get("isrc", ""),
            url=item.get("permalink_url", ""),
            artwork_url=item.get("artwork_url") or "",
        )

    # ── Search (yt-dlp fallback if no API auth) ─────────────────────────────

    def search(self, query: str, limit: int = 10) -> list[TrackResult]:
        # Try authenticated API first
        if self._access_token:
            try:
                r = requests.get(
                    f"{SC_API}/tracks",
                    headers=self._headers(),
                    params={"q": query, "limit": limit},
                    timeout=20,
                )
                r.raise_for_status()
                return [self._parse_track(t) for t in r.json()]
            except Exception:
                pass

        # Fallback to yt-dlp
        try:
            import yt_dlp
            ydl_opts = {
                "quiet": True, "no_warnings": True,
                "extract_flat": True, "skip_download": True,
            }
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(f"scsearch{limit}:{query}", download=False)
            entries = info.get("entries") or []
            out: list[TrackResult] = []
            for e in entries:
                out.append(TrackResult(
                    service="soundcloud",
                    track_id=str(e.get("id", "")),
                    title=e.get("title", ""),
                    artist=e.get("uploader") or "",
                    duration_ms=(e.get("duration") or 0) * 1000,
                    url=e.get("url") or e.get("webpage_url", ""),
                    artwork_url=(e.get("thumbnails") or [{}])[-1].get("url", ""),
                ))
            return out
        except Exception:
            return []

    def get_playlist(self, playlist_id_or_url: str) -> PlaylistResult | None:
        # Try yt-dlp for URL-based playlist fetch
        try:
            import yt_dlp
            url = playlist_id_or_url
            if not url.startswith("http"):
                # Try API if authenticated
                if self._access_token:
                    r = requests.get(
                        f"{SC_API}/playlists/{url}",
                        headers=self._headers(), timeout=20,
                    )
                    r.raise_for_status()
                    data = r.json()
                    tracks = [self._parse_track(t) for t in data.get("tracks", [])]
                    return PlaylistResult(
                        service="soundcloud",
                        playlist_id=str(data.get("id", url)),
                        name=data.get("title", ""),
                        description=data.get("description", ""),
                        owner=(data.get("user") or {}).get("username", ""),
                        track_count=len(tracks),
                        tracks=tracks,
                        url=data.get("permalink_url", ""),
                    )
                return None

            ydl_opts = {
                "quiet": True, "no_warnings": True,
                "extract_flat": True, "skip_download": True,
            }
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
            entries = info.get("entries") or []
            tracks = []
            for e in entries:
                tracks.append(TrackResult(
                    service="soundcloud",
                    track_id=str(e.get("id", "")),
                    title=e.get("title", ""),
                    artist=e.get("uploader") or "",
                    duration_ms=(e.get("duration") or 0) * 1000,
                    url=e.get("url") or "",
                ))
            return PlaylistResult(
                service="soundcloud",
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

    def create_playlist(self, name: str, description: str = "") -> str | None:
        if not self._access_token:
            return None
        try:
            r = requests.post(
                f"{SC_API}/playlists",
                headers=self._headers(),
                json={"playlist": {"title": name, "description": description, "tracks": []}},
                timeout=20,
            )
            r.raise_for_status()
            return str(r.json().get("id"))
        except Exception:
            return None

    def add_tracks(self, playlist_id: str, track_ids: list[str]) -> int:
        if not self._access_token:
            return 0
        try:
            r = requests.get(
                f"{SC_API}/playlists/{playlist_id}",
                headers=self._headers(), timeout=20,
            )
            r.raise_for_status()
            existing = r.json().get("tracks", [])
            existing.extend({"id": int(tid)} for tid in track_ids)
            r2 = requests.put(
                f"{SC_API}/playlists/{playlist_id}",
                headers=self._headers(),
                json={"playlist": {"tracks": existing}},
                timeout=20,
            )
            r2.raise_for_status()
            return len(track_ids)
        except Exception:
            return 0

    def supports_write(self) -> bool:
        return self.is_authenticated()

    # ── Liked songs ───────────────────────────────────────────────────────────

    def get_liked_songs(self, limit: int = 500) -> list[TrackResult]:
        if not self._access_token:
            return []
        tracks: list[TrackResult] = []
        offset = 0
        batch = min(limit, 50)
        while len(tracks) < limit:
            try:
                r = requests.get(
                    f"{SC_API}/me/favorites",
                    headers=self._headers(),
                    params={"limit": batch, "offset": offset},
                    timeout=20,
                )
                r.raise_for_status()
                items = r.json()
            except Exception:
                break
            if not items:
                break
            for item in items:
                tracks.append(self._parse_track(item))
            offset += len(items)
            if len(items) < batch:
                break
        return tracks[:limit]

    def add_to_liked(self, track_ids: list[str]) -> int:
        if not self._access_token:
            return 0
        added = 0
        for tid in track_ids:
            try:
                r = requests.put(
                    f"{SC_API}/me/favorites/{tid}",
                    headers=self._headers(), timeout=20,
                )
                r.raise_for_status()
                added += 1
            except Exception:
                continue
        return added

    def remove_from_liked(self, track_ids: list[str]) -> int:
        if not self._access_token:
            return 0
        removed = 0
        for tid in track_ids:
            try:
                r = requests.delete(
                    f"{SC_API}/me/favorites/{tid}",
                    headers=self._headers(), timeout=20,
                )
                r.raise_for_status()
                removed += 1
            except Exception:
                continue
        return removed

    # ── Followed artists (users) ──────────────────────────────────────────────

    def get_followed_artists(self, limit: int = 500) -> list[dict]:
        if not self._access_token:
            return []
        artists: list[dict] = []
        offset = 0
        batch = min(limit, 50)
        while len(artists) < limit:
            try:
                r = requests.get(
                    f"{SC_API}/me/followings",
                    headers=self._headers(),
                    params={"limit": batch, "offset": offset},
                    timeout=20,
                )
                r.raise_for_status()
                data = r.json()
            except Exception:
                break
            items = data.get("collection") or data if isinstance(data, list) else data.get("collection", [])
            if not items:
                break
            for u in items:
                artists.append({
                    "id": str(u.get("id", "")),
                    "name": u.get("username", ""),
                    "url": u.get("permalink_url", ""),
                })
            offset += len(items)
            if len(items) < batch:
                break
        return artists[:limit]

    def follow_artist(self, artist_id: str) -> bool:
        if not self._access_token:
            return False
        try:
            r = requests.put(
                f"{SC_API}/me/followings/{artist_id}",
                headers=self._headers(), timeout=20,
            )
            r.raise_for_status()
            return True
        except Exception:
            return False
