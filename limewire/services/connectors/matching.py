"""Track matching engine — ISRC, title+artist, and fuzzy matching."""

from __future__ import annotations

from difflib import SequenceMatcher

from .base import ConnectorBase, TrackResult, TrackMatch
from .utils import normalize_title
from .storage import lookup_track_mapping, cache_track_mapping


def _similarity(a: str, b: str) -> float:
    """Normalized string similarity score (0.0–1.0)."""
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, a.lower().strip(), b.lower().strip()).ratio()


def match_track(
    source: TrackResult,
    candidates: list[TrackResult],
    threshold: float = 0.75,
) -> TrackMatch:
    """Find the best match for a source track among candidates.

    Strategy (in priority order):
    1. ISRC exact match → confidence 1.0
    2. Normalized title + artist exact match → confidence 0.95
    3. Fuzzy title + artist → confidence = combined ratio
    4. Below threshold → no match
    """
    if not candidates:
        return TrackMatch(source=source, target=None, confidence=0.0, match_method="none")

    best_target: TrackResult | None = None
    best_confidence = 0.0
    best_method = "none"

    src_title_norm = normalize_title(source.title)
    src_artist_norm = source.artist.lower().strip()

    for c in candidates:
        # 1. ISRC exact match
        if source.isrc and c.isrc and source.isrc.upper() == c.isrc.upper():
            return TrackMatch(source=source, target=c, confidence=1.0, match_method="isrc")

        # 2. Normalized title+artist exact match
        c_title_norm = normalize_title(c.title)
        c_artist_norm = c.artist.lower().strip()
        if src_title_norm and c_title_norm:
            if src_title_norm == c_title_norm and _similarity(src_artist_norm, c_artist_norm) > 0.8:
                if 0.95 > best_confidence:
                    best_target = c
                    best_confidence = 0.95
                    best_method = "title_artist"

        # 3. Fuzzy matching
        title_score = _similarity(src_title_norm, c_title_norm)
        artist_score = _similarity(src_artist_norm, c_artist_norm)

        # Duration tolerance bonus
        duration_score = 0.0
        if source.duration_ms and c.duration_ms:
            diff = abs(source.duration_ms - c.duration_ms)
            if diff <= 2000:
                duration_score = 0.1
            elif diff <= 5000:
                duration_score = 0.05

        combined = 0.55 * title_score + 0.35 * artist_score + duration_score
        if combined > best_confidence:
            best_confidence = combined
            best_target = c
            best_method = "fuzzy"

    if best_confidence >= threshold and best_target is not None:
        return TrackMatch(
            source=source, target=best_target,
            confidence=best_confidence, match_method=best_method,
        )

    return TrackMatch(source=source, target=None, confidence=best_confidence, match_method="none")


def match_tracks_bulk(
    source_tracks: list[TrackResult],
    target_connector: ConnectorBase,
    threshold: float = 0.75,
    progress_callback=None,
) -> list[TrackMatch]:
    """Match a list of source tracks against a target service.

    For each source track:
    1. Check cached mappings first
    2. Search target service by "artist title"
    3. Pick best match from results

    progress_callback(current: int, total: int) is called after each track.
    """
    total = len(source_tracks)
    matches: list[TrackMatch] = []

    for i, src in enumerate(source_tracks):
        # 1. Check cache
        cached = lookup_track_mapping(
            src.service, src.track_id, target_connector.service_name,
        )
        if cached:
            matches.append(TrackMatch(
                source=src,
                target=TrackResult(
                    service=target_connector.service_name,
                    track_id=cached["target_id"],
                    title="(cached)", artist="",
                ),
                confidence=cached.get("confidence", 0.9),
                match_method="cached",
            ))
            if progress_callback:
                progress_callback(i + 1, total)
            continue

        # 2. Search target service
        query = f"{src.artist} {src.title}".strip()
        if not query:
            matches.append(TrackMatch(source=src, target=None, confidence=0.0, match_method="none"))
            if progress_callback:
                progress_callback(i + 1, total)
            continue

        candidates = target_connector.search(query, limit=5)

        # 3. Match
        m = match_track(src, candidates, threshold)
        matches.append(m)

        # 4. Cache successful match
        if m.matched and m.target:
            cache_track_mapping(
                src.service, src.track_id,
                target_connector.service_name, m.target.track_id,
                m.confidence, m.match_method,
            )

        if progress_callback:
            progress_callback(i + 1, total)

    return matches
