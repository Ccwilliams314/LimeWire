"""CSV import/export for track lists and playlists."""

from __future__ import annotations

import csv
import io
from pathlib import Path

from .base import TrackResult, PlaylistResult

# Column order for export
_COLUMNS = [
    "service", "track_id", "title", "artist", "album",
    "duration_ms", "isrc", "url", "artwork_url", "preview_url",
]


def export_tracks_csv(tracks: list[TrackResult], path: str | Path) -> int:
    """Export a list of TrackResults to a CSV file. Returns count written."""
    path = Path(path)
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=_COLUMNS, extrasaction="ignore")
        writer.writeheader()
        for t in tracks:
            writer.writerow(t.to_dict())
    return len(tracks)


def export_playlist_csv(playlist: PlaylistResult, path: str | Path) -> int:
    """Export a PlaylistResult's tracks to CSV with playlist metadata header."""
    path = Path(path)
    with open(path, "w", newline="", encoding="utf-8") as f:
        # Write playlist metadata as comments
        f.write(f"# Playlist: {playlist.name}\n")
        f.write(f"# Service: {playlist.service}\n")
        if playlist.owner:
            f.write(f"# Owner: {playlist.owner}\n")
        if playlist.description:
            f.write(f"# Description: {playlist.description}\n")
        f.write(f"# Track count: {len(playlist.tracks)}\n")
        writer = csv.DictWriter(f, fieldnames=_COLUMNS, extrasaction="ignore")
        writer.writeheader()
        for t in playlist.tracks:
            writer.writerow(t.to_dict())
    return len(playlist.tracks)


def import_tracks_csv(path: str | Path) -> list[TrackResult]:
    """Import tracks from a CSV file. Returns list of TrackResults."""
    path = Path(path)
    tracks: list[TrackResult] = []
    with open(path, "r", encoding="utf-8") as f:
        # Skip comment lines
        lines = [line for line in f if not line.startswith("#")]
    reader = csv.DictReader(io.StringIO("".join(lines)))
    for row in reader:
        tracks.append(TrackResult(
            service=row.get("service", "csv"),
            track_id=row.get("track_id", ""),
            title=row.get("title", ""),
            artist=row.get("artist", ""),
            album=row.get("album", ""),
            duration_ms=int(row.get("duration_ms", 0) or 0),
            isrc=row.get("isrc", ""),
            url=row.get("url", ""),
            artwork_url=row.get("artwork_url", ""),
            preview_url=row.get("preview_url", ""),
        ))
    return tracks


def tracks_to_csv_string(tracks: list[TrackResult]) -> str:
    """Export tracks to a CSV string (for clipboard copy)."""
    out = io.StringIO()
    writer = csv.DictWriter(out, fieldnames=_COLUMNS, extrasaction="ignore")
    writer.writeheader()
    for t in tracks:
        writer.writerow(t.to_dict())
    return out.getvalue()
