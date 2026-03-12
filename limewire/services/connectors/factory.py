"""Connector factory — build service connectors by name."""

from __future__ import annotations

from .base import ConnectorBase
from .spotify import SpotifyConnector
from .youtube import YouTubeConnector
from .apple_music import AppleMusicConnector
from .soundcloud import SoundCloudConnector
from .tidal import TidalConnector
from .amazon_music import AmazonMusicConnector
from .deezer import DeezerConnector

_REGISTRY: dict[str, type[ConnectorBase]] = {
    "spotify": SpotifyConnector,
    "youtube": YouTubeConnector,
    "apple_music": AppleMusicConnector,
    "soundcloud": SoundCloudConnector,
    "tidal": TidalConnector,
    "amazon_music": AmazonMusicConnector,
    "deezer": DeezerConnector,
}


def build_connector(service: str, settings: dict) -> ConnectorBase | None:
    """Build a connector instance by service name, injecting settings."""
    cls = _REGISTRY.get(service)
    if cls is None:
        return None
    return cls(settings)


def available_services() -> list[str]:
    """Return list of all registered service names."""
    return list(_REGISTRY.keys())


def writable_services(settings: dict) -> list[str]:
    """Return list of services that support write operations with current settings."""
    out = []
    for name, cls in _REGISTRY.items():
        try:
            c = cls(settings)
            if c.supports_write():
                out.append(name)
        except Exception:
            continue
    return out
