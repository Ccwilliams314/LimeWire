"""Centralized path safety — resolve, confine, sanitize, atomic writes."""

import os
import re
import tempfile

_WIN_RESERVED = frozenset(
    {"CON", "PRN", "AUX", "NUL"}
    | {f"COM{i}" for i in range(1, 10)}
    | {f"LPT{i}" for i in range(1, 10)}
)

# Allowed root directories for writes — lazily populated
_ALLOWED_ROOTS: list[str] = []


class PathPolicyError(ValueError):
    """Raised when a path violates security policy."""


def init_allowed_roots(extra_roots: list[str] | None = None):
    """Initialize the allowed write roots.  Called once at app startup."""
    _ALLOWED_ROOTS.clear()
    home = os.path.expanduser("~")
    _ALLOWED_ROOTS.extend([
        os.path.join(home, ".limewire"),
        os.path.join(home, "Downloads"),
        os.path.join(home, "Music"),
        os.path.join(home, "Documents"),
        tempfile.gettempdir(),
    ])
    if extra_roots:
        _ALLOWED_ROOTS.extend(extra_roots)


def resolve_path(candidate: str) -> str:
    """Resolve a path to absolute, following symlinks."""
    return os.path.realpath(os.path.expanduser(candidate))


def is_under_root(path: str, root: str) -> bool:
    """Check if resolved path is under root (no traversal escape)."""
    path = os.path.normcase(os.path.normpath(resolve_path(path)))
    root = os.path.normcase(os.path.normpath(resolve_path(root)))
    return path.startswith(root + os.sep) or path == root


def require_under_root(path: str, root: str):
    """Raise PathPolicyError if path escapes root."""
    if not is_under_root(path, root):
        raise PathPolicyError(f"Path escapes allowed root: {path}")


def require_allowed_write(path: str):
    """Raise PathPolicyError if path is not under any allowed root."""
    resolved = resolve_path(path)
    if not _ALLOWED_ROOTS:
        return  # not initialized — permissive mode during migration
    for root in _ALLOWED_ROOTS:
        if is_under_root(resolved, root):
            return
    raise PathPolicyError(
        f"Write target not in allowed roots: {resolved}"
    )


def sanitize_filename(name: str, max_length: int = 200) -> str:
    """Strip dangerous characters, reserved names, enforce length limit."""
    # Remove path-separator characters and control chars
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '', name)
    name = name.strip('. ')
    # Block Windows reserved names
    base = name.split('.')[0].upper()
    if base in _WIN_RESERVED:
        name = f"_{name}"
    return name[:max_length] if name else "untitled"


def atomic_write(target: str, data: bytes | str, mode: str = "wb"):
    """Write to tmp file then os.replace — crash-safe."""
    target = resolve_path(target)
    require_allowed_write(target)
    os.makedirs(os.path.dirname(target), exist_ok=True)
    tmp = target + ".tmp"
    try:
        with open(tmp, mode) as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, target)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def safe_join(root: str, *parts: str) -> str:
    """Join path parts and verify result stays under root."""
    joined = os.path.join(root, *parts)
    resolved = resolve_path(joined)
    root_resolved = resolve_path(root)
    if not (resolved.startswith(root_resolved + os.sep) or resolved == root_resolved):
        raise PathPolicyError(f"Path traversal detected: {joined}")
    return resolved
