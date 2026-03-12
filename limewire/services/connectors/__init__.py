"""Music service connectors — unified interface for Spotify, YouTube, Apple Music, Deezer, etc."""

from .base import ConnectorBase, TrackResult, PlaylistResult, TrackMatch, TransferReport
from .factory import build_connector, available_services
from .transfer import (
    transfer_playlist, sync_playlist,
    batch_transfer_playlists, transfer_liked_songs,
    transfer_followed_artists, transfer_saved_albums,
    generate_smart_links,
)
from .csv_io import export_tracks_csv, import_tracks_csv, export_playlist_csv
from .utils import parse_source_query, detect_service_from_url, CONNECTOR_LABELS

__all__ = [
    "ConnectorBase", "TrackResult", "PlaylistResult", "TrackMatch", "TransferReport",
    "build_connector", "available_services",
    "transfer_playlist", "sync_playlist",
    "batch_transfer_playlists", "transfer_liked_songs",
    "transfer_followed_artists", "transfer_saved_albums",
    "generate_smart_links",
    "export_tracks_csv", "import_tracks_csv", "export_playlist_csv",
    "parse_source_query", "detect_service_from_url", "CONNECTOR_LABELS",
]
