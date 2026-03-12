"""Amazon Music connector — scaffold only (API access requires approval)."""

from __future__ import annotations

from .base import ConnectorBase, TrackResult, PlaylistResult


class AmazonMusicConnector(ConnectorBase):
    service_name = "amazon_music"
    requires_auth = True

    def is_authenticated(self) -> bool:
        return False

    def search(self, query: str, limit: int = 10) -> list[TrackResult]:
        return []

    def get_track(self, track_id: str) -> TrackResult | None:
        return None

    def get_playlist(self, playlist_id_or_url: str) -> PlaylistResult | None:
        return None
