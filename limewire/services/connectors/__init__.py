"""Music service connectors — unified interface for Spotify, YouTube, Apple Music, etc."""

from .base import ConnectorBase, TrackResult, PlaylistResult, TrackMatch, TransferReport
from .factory import build_connector, available_services
from .transfer import transfer_playlist, sync_playlist
from .utils import parse_source_query, detect_service_from_url, CONNECTOR_LABELS

__all__ = [
    "ConnectorBase", "TrackResult", "PlaylistResult", "TrackMatch", "TransferReport",
    "build_connector", "available_services",
    "transfer_playlist", "sync_playlist",
    "parse_source_query", "detect_service_from_url", "CONNECTOR_LABELS",
]
