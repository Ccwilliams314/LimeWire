"""Plugin trust policy — hash-based approval, no auto-execution."""

import hashlib
import importlib.util
import logging
import os
from types import ModuleType

_log = logging.getLogger("LimeWire.security")


class PluginTrustError(RuntimeError):
    """Raised when a plugin fails trust verification."""


def sha256_file(path: str) -> str:
    """Compute SHA-256 hex digest of a file."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


class PluginScan:
    """Result of scanning a single plugin file."""
    __slots__ = ("path", "filename", "sha256", "trusted", "size_bytes")

    def __init__(self, path, filename, sha256, trusted, size_bytes):
        self.path = path
        self.filename = filename
        self.sha256 = sha256
        self.trusted = trusted
        self.size_bytes = size_bytes


def scan_plugins(plugin_dir: str, trusted_hashes: set[str]) -> list[PluginScan]:
    """Discover plugin files without executing them.

    Returns a list of PluginScan results showing path, hash, and trust status.
    """
    os.makedirs(plugin_dir, exist_ok=True)
    results = []
    for fn in sorted(os.listdir(plugin_dir)):
        if not fn.endswith(".py") or fn.startswith("_"):
            continue
        path = os.path.join(plugin_dir, fn)
        if not os.path.isfile(path):
            continue
        digest = sha256_file(path)
        results.append(PluginScan(
            path=path,
            filename=fn,
            sha256=digest,
            trusted=(digest in trusted_hashes),
            size_bytes=os.path.getsize(path),
        ))
    return results


def load_trusted_plugin(path: str, expected_hash: str) -> ModuleType:
    """Load a plugin module ONLY if its hash matches the trusted value.

    Args:
        path: Absolute path to the .py plugin file.
        expected_hash: SHA-256 hex digest that was previously approved.

    Returns:
        The loaded module.

    Raises:
        PluginTrustError: If hash doesn't match or file can't be loaded.
    """
    actual = sha256_file(path)
    if actual != expected_hash:
        raise PluginTrustError(
            f"Plugin hash mismatch for {os.path.basename(path)}: "
            f"expected {expected_hash[:16]}..., got {actual[:16]}..."
        )

    name = os.path.splitext(os.path.basename(path))[0]
    spec = importlib.util.spec_from_file_location(f"limewire_plugin_{name}", path)
    if spec is None or spec.loader is None:
        raise PluginTrustError(f"Cannot create import spec for {path}")

    _log.info("[plugin] Loading trusted plugin: %s (hash=%s...)", name, actual[:16])
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
