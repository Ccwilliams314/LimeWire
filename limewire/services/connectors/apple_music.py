"""Apple Music connector — read-only via public iTunes Search API."""

from __future__ import annotations

import requests

from .base import ConnectorBase, TrackResult, PlaylistResult
from .utils import split_artists


class AppleMusicConnector(ConnectorBase):
    service_name = "apple_music"
    requires_auth = False  # search works without auth

    def is_authenticated(self) -> bool:
        return True  # always available for search

    def search(self, query: str, limit: int = 10) -> list[TrackResult]:
        try:
            r = requests.get(
                "https://itunes.apple.com/search",
                params={"term": query, "entity": "song", "limit": limit},
                timeout=20,
            )
            r.raise_for_status()
            items = r.json().get("results", [])
        except Exception:
            return []

        out: list[TrackResult] = []
        for item in items:
            art_url = (item.get("artworkUrl100") or "").replace("100x100", "600x600")
            out.append(TrackResult(
                service="apple_music",
                track_id=str(item.get("trackId", "")),
                title=item.get("trackName", ""),
                artist=item.get("artistName", ""),
                album=item.get("collectionName", ""),
                duration_ms=item.get("trackTimeMillis", 0),
                url=item.get("trackViewUrl", ""),
                artwork_url=art_url or "",
                preview_url=item.get("previewUrl", ""),
            ))
        return out

    def get_track(self, track_id: str) -> TrackResult | None:
        try:
            r = requests.get(
                "https://itunes.apple.com/lookup",
                params={"id": track_id, "entity": "song"},
                timeout=20,
            )
            r.raise_for_status()
            results = r.json().get("results", [])
        except Exception:
            return None

        for item in results:
            if item.get("wrapperType") == "track":
                art_url = (item.get("artworkUrl100") or "").replace("100x100", "600x600")
                return TrackResult(
                    service="apple_music",
                    track_id=str(item.get("trackId", "")),
                    title=item.get("trackName", ""),
                    artist=item.get("artistName", ""),
                    album=item.get("collectionName", ""),
                    duration_ms=item.get("trackTimeMillis", 0),
                    url=item.get("trackViewUrl", ""),
                    artwork_url=art_url or "",
                    preview_url=item.get("previewUrl", ""),
                )
        return None

    def get_playlist(self, playlist_id_or_url: str) -> PlaylistResult | None:
        # Public playlist retrieval not supported via unauthenticated iTunes API
        return None
