"""Playlist transfer and sync orchestration."""

from __future__ import annotations

from .base import ConnectorBase, TransferReport
from .matching import match_tracks_bulk
from .storage import save_transfer


def transfer_playlist(
    source: ConnectorBase,
    target: ConnectorBase,
    source_playlist_id: str,
    target_playlist_name: str | None = None,
    skip_existing: bool = True,
    progress_callback=None,
) -> TransferReport:
    """Transfer a playlist from one service to another.

    Steps:
    1. Fetch source playlist tracks
    2. Match each track against target service
    3. Create target playlist
    4. Add matched tracks to target
    5. Return report

    progress_callback(current: int, total: int, stage: str) optional.
    """
    report = TransferReport(
        source_service=source.service_name,
        target_service=target.service_name,
        source_playlist=source_playlist_id,
    )

    # 1. Fetch source playlist
    if progress_callback:
        progress_callback(0, 1, "Fetching source playlist...")
    src_playlist = source.get_playlist(source_playlist_id)
    if not src_playlist:
        report.errors.append("Could not fetch source playlist")
        return report

    report.total = len(src_playlist.tracks)
    playlist_name = target_playlist_name or src_playlist.name

    # 2. Match tracks
    def match_progress(current, total):
        if progress_callback:
            progress_callback(current, total, f"Matching tracks ({current}/{total})...")

    matches = match_tracks_bulk(
        src_playlist.tracks, target, threshold=0.75,
        progress_callback=match_progress,
    )
    report.matches = matches
    report.matched = sum(1 for m in matches if m.matched)

    # 3. Create target playlist
    if progress_callback:
        progress_callback(0, 1, "Creating target playlist...")
    target_pid = target.create_playlist(playlist_name, src_playlist.description)
    if not target_pid:
        report.errors.append("Could not create target playlist")
        return report
    report.target_playlist_id = target_pid

    # 4. Add matched tracks
    matched_ids = [m.target.track_id for m in matches if m.matched and m.target]
    if matched_ids:
        if progress_callback:
            progress_callback(0, 1, f"Adding {len(matched_ids)} tracks...")
        added = target.add_tracks(target_pid, matched_ids)
        report.added = added
        report.failed = len(matched_ids) - added
    else:
        report.added = 0

    # 5. Persist transfer record
    save_transfer(
        source.service_name, target.service_name, playlist_name,
        report.total, report.matched, report.added, report.failed,
    )

    return report


def sync_playlist(
    source: ConnectorBase,
    target: ConnectorBase,
    source_playlist_id: str,
    target_playlist_id: str,
    progress_callback=None,
) -> TransferReport:
    """Sync a playlist: add tracks that exist in source but not in target.

    Does not remove tracks from target. Does not duplicate existing tracks.
    """
    report = TransferReport(
        source_service=source.service_name,
        target_service=target.service_name,
        source_playlist=source_playlist_id,
        target_playlist_id=target_playlist_id,
    )

    # Fetch both playlists
    if progress_callback:
        progress_callback(0, 1, "Fetching playlists...")
    src_pl = source.get_playlist(source_playlist_id)
    tgt_pl = target.get_playlist(target_playlist_id)

    if not src_pl:
        report.errors.append("Could not fetch source playlist")
        return report
    if not tgt_pl:
        report.errors.append("Could not fetch target playlist")
        return report

    # Find tracks in source but not in target (by title+artist match)
    existing_keys = set()
    for t in tgt_pl.tracks:
        key = f"{t.title.lower().strip()}|{t.artist.lower().strip()}"
        existing_keys.add(key)

    missing = []
    for t in src_pl.tracks:
        key = f"{t.title.lower().strip()}|{t.artist.lower().strip()}"
        if key not in existing_keys:
            missing.append(t)

    report.total = len(src_pl.tracks)
    report.skipped = len(src_pl.tracks) - len(missing)

    if not missing:
        return report

    # Match missing tracks on target service
    def match_progress(current, total):
        if progress_callback:
            progress_callback(current, total, f"Matching new tracks ({current}/{total})...")

    matches = match_tracks_bulk(missing, target, progress_callback=match_progress)
    report.matches = matches
    report.matched = sum(1 for m in matches if m.matched)

    # Add matched
    matched_ids = [m.target.track_id for m in matches if m.matched and m.target]
    if matched_ids:
        if progress_callback:
            progress_callback(0, 1, f"Adding {len(matched_ids)} new tracks...")
        added = target.add_tracks(target_playlist_id, matched_ids)
        report.added = added
        report.failed = len(matched_ids) - added

    save_transfer(
        source.service_name, target.service_name, f"sync:{source_playlist_id}",
        report.total, report.matched, report.added, report.failed,
    )

    return report
