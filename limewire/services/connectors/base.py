"""Base dataclasses and abstract connector interface for all music services."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field, asdict
from typing import Any, Optional


@dataclass
class TrackResult:
    """Normalized track from any music service."""
    service: str              # "spotify", "youtube", "apple_music", etc.
    track_id: str             # service-specific ID
    title: str
    artist: str
    album: str = ""
    duration_ms: int = 0
    isrc: str = ""
    url: str = ""
    artwork_url: str = ""
    preview_url: str = ""
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class PlaylistResult:
    """Normalized playlist from any music service."""
    service: str
    playlist_id: str
    name: str
    description: str = ""
    owner: str = ""
    track_count: int = 0
    tracks: list[TrackResult] = field(default_factory=list)
    url: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class TrackMatch:
    """Result of matching a source track to a target service."""
    source: TrackResult
    target: Optional[TrackResult]
    confidence: float         # 0.0–1.0
    match_method: str         # "isrc", "title_artist", "fuzzy", "cached", "none"

    @property
    def matched(self) -> bool:
        return self.target is not None and self.confidence >= 0.5


@dataclass
class TransferReport:
    """Summary of a playlist transfer or sync operation."""
    source_service: str
    target_service: str
    source_playlist: str
    target_playlist_id: str = ""
    total: int = 0
    matched: int = 0
    added: int = 0
    failed: int = 0
    skipped: int = 0
    matches: list[TrackMatch] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class ConnectorBase(ABC):
    """Abstract base for all music service connectors."""

    service_name: str = ""
    requires_auth: bool = True

    def __init__(self, settings: dict):
        self.settings = settings

    @abstractmethod
    def is_authenticated(self) -> bool:
        """Return True if the connector has valid credentials."""
        ...

    @abstractmethod
    def search(self, query: str, limit: int = 10) -> list[TrackResult]:
        """Search for tracks by text query."""
        ...

    def get_track(self, track_id: str) -> Optional[TrackResult]:
        """Get a single track by service-specific ID."""
        return None

    def get_playlist(self, playlist_id_or_url: str) -> Optional[PlaylistResult]:
        """Get playlist metadata and tracks."""
        return None

    def list_user_playlists(self) -> list[PlaylistResult]:
        """List the authenticated user's playlists."""
        return []

    def create_playlist(self, name: str, description: str = "") -> Optional[str]:
        """Create a new playlist, return its ID."""
        return None

    def add_tracks(self, playlist_id: str, track_ids: list[str]) -> int:
        """Add tracks to a playlist, return count added."""
        return 0

    def supports_write(self) -> bool:
        """Return True if this connector supports playlist creation/modification."""
        return False

    # ── Liked songs / favorites ──────────────────────────────────────────

    def get_liked_songs(self, limit: int = 500) -> list[TrackResult]:
        """Get user's liked/saved tracks."""
        return []

    def add_to_liked(self, track_ids: list[str]) -> int:
        """Add tracks to user's liked/saved songs. Returns count added."""
        return 0

    def remove_from_liked(self, track_ids: list[str]) -> int:
        """Remove tracks from user's liked/saved songs. Returns count removed."""
        return 0

    # ── Artists / Albums ─────────────────────────────────────────────────

    def get_followed_artists(self, limit: int = 500) -> list[dict]:
        """Get user's followed artists. Returns list of {id, name, url}."""
        return []

    def follow_artist(self, artist_id: str) -> bool:
        """Follow an artist. Returns True on success."""
        return False

    def get_saved_albums(self, limit: int = 500) -> list[dict]:
        """Get user's saved albums. Returns list of {id, title, artist, url}."""
        return []

    def save_album(self, album_id: str) -> bool:
        """Save an album to library. Returns True on success."""
        return False
