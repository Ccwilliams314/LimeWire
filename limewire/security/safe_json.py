"""Schema-validated JSON I/O — size limits, key allowlists, type checks."""

import json
import logging
import os

from limewire.security.safe_paths import atomic_write, resolve_path

_log = logging.getLogger("LimeWire.security")

MAX_JSON_BYTES = 5 * 1024 * 1024  # 5 MB hard limit


class JsonPolicyError(ValueError):
    """Raised when JSON content violates policy."""


def load_validated(
    path: str,
    default,
    *,
    max_bytes: int = MAX_JSON_BYTES,
    allowed_keys: frozenset | None = None,
    max_depth: int = 10,
):
    """Load JSON with size limit, optional key allowlist, and depth check.

    Args:
        path: File path to read.
        default: Fallback value if file missing or invalid.
        max_bytes: Reject files larger than this.
        allowed_keys: If set, reject any top-level keys not in this set.
        max_depth: Maximum nesting depth allowed.

    Returns:
        Parsed and validated data, or default on failure.
    """
    path = resolve_path(path)
    if not os.path.exists(path):
        return default

    try:
        size = os.path.getsize(path)
        if size > max_bytes:
            _log.warning("JSON file too large (%d bytes): %s", size, path)
            return default

        with open(path) as f:
            data = json.load(f)

        # Depth check
        if not _check_depth(data, max_depth):
            _log.warning("JSON exceeds max depth (%d): %s", max_depth, path)
            return default

        # Key allowlist (for dicts like themes, settings)
        if allowed_keys is not None and isinstance(data, dict):
            unknown = set(data.keys()) - allowed_keys
            if unknown:
                _log.warning("Unknown keys in %s: %s", path, sorted(unknown))
                # Strip unknown keys rather than reject entirely
                data = {k: v for k, v in data.items() if k in allowed_keys}

        return data

    except json.JSONDecodeError as e:
        _log.warning("Invalid JSON in %s: %s", path, e)
        return default
    except Exception as e:
        _log.warning("Failed to load %s: %s", path, e)
        return default


def save_validated(path: str, data, *, max_bytes: int = MAX_JSON_BYTES):
    """Serialize data to JSON and write atomically with size guard.

    Args:
        path: Target file path.
        data: JSON-serializable data.
        max_bytes: Refuse to write if serialized size exceeds this.

    Raises:
        JsonPolicyError: If serialized data exceeds max_bytes.
    """
    payload = json.dumps(data, indent=2, ensure_ascii=False)
    if len(payload.encode("utf-8")) > max_bytes:
        raise JsonPolicyError(
            f"Serialized JSON too large ({len(payload)} bytes) for {path}"
        )
    atomic_write(path, payload, mode="w")


def validate_theme(data: dict, allowed_keys: frozenset) -> dict:
    """Validate a community theme dict — strip unknown keys, verify color format.

    Args:
        data: Raw theme dict from JSON.
        allowed_keys: The frozenset of permitted theme key names.

    Returns:
        Sanitized theme dict with only allowed keys and valid hex colors.

    Raises:
        JsonPolicyError: If data is not a dict or has no required keys.
    """
    if not isinstance(data, dict):
        raise JsonPolicyError("Theme must be a JSON object")
    if "BG" not in data or "TEXT" not in data:
        raise JsonPolicyError("Theme must have at least BG and TEXT keys")

    clean = {}
    for k, v in data.items():
        if k not in allowed_keys:
            _log.warning("Stripping unknown theme key: %s", k)
            continue
        if isinstance(v, str) and v.startswith("#"):
            # Validate hex color format
            hex_body = v[1:]
            if len(hex_body) not in (3, 6, 8):
                _log.warning("Invalid color for %s: %s", k, v)
                continue
            if not all(c in "0123456789abcdefABCDEF" for c in hex_body):
                _log.warning("Invalid hex chars in %s: %s", k, v)
                continue
        clean[k] = v
    return clean


def _check_depth(obj, max_depth: int, current: int = 0) -> bool:
    """Recursively check that JSON nesting doesn't exceed max_depth."""
    if current > max_depth:
        return False
    if isinstance(obj, dict):
        return all(_check_depth(v, max_depth, current + 1) for v in obj.values())
    if isinstance(obj, list):
        return all(_check_depth(v, max_depth, current + 1) for v in obj)
    return True
