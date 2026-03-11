"""Plugin system — custom audio processors with hash-based trust.

Plugins are discovered in ~/.limewire/plugins/ but NOT auto-executed.
They must be explicitly approved by the user (stored by SHA-256 hash).
"""

import logging
import os

from limewire.security.plugin_policy import (
    scan_plugins, load_trusted_plugin, PluginTrustError,
)

_log = logging.getLogger("LimeWire")

PLUGINS_DIR = os.path.join(os.path.expanduser("~"), ".limewire", "plugins")


class PluginBase:
    """Base class for LimeWire audio processor plugins.

    Subclass this and implement process(audio_data, sr, **params) -> audio_data.
    """
    name = "Unnamed Plugin"
    description = ""
    category = "Custom"
    parameters = {}  # {"param_name": {"type":"float","min":0,"max":1,"default":0.5,"label":"..."}}

    def process(self, audio_data, sr, **params):
        """Process audio data (numpy array) at sample rate sr. Return processed array."""
        return audio_data


class PluginManager:
    """Discovers, loads, and manages audio processor plugins.

    Security: plugins are only loaded if their SHA-256 hash has been
    explicitly approved by the user.  No auto-execution on discovery.
    """

    def __init__(self):
        self._plugins = {}   # name -> plugin_instance
        self._discovered = []  # list of PluginScan results
        self._errors = []

    def discover(self, trusted_hashes: set[str] | None = None):
        """Scan plugins directory — discover files without executing them.

        Args:
            trusted_hashes: Set of SHA-256 hashes the user has approved.
                            Only plugins matching a trusted hash will be loaded.
                            If None, discovery only (no loading).
        """
        self._plugins = {}
        self._errors = []
        self._discovered = scan_plugins(PLUGINS_DIR, trusted_hashes or set())

        if trusted_hashes is None:
            # Discovery only — no loading
            return

        for scan in self._discovered:
            if not scan.trusted:
                _log.info("[plugin] Skipping untrusted plugin: %s (hash=%s...)",
                          scan.filename, scan.sha256[:16])
                continue
            try:
                mod = load_trusted_plugin(scan.path, scan.sha256)
                # Find all PluginBase subclasses in the module
                for attr_name in dir(mod):
                    attr = getattr(mod, attr_name)
                    if (isinstance(attr, type) and issubclass(attr, PluginBase)
                            and attr is not PluginBase):
                        inst = attr()
                        self._plugins[inst.name] = inst
                        _log.info("Loaded trusted plugin: %s from %s", inst.name, scan.filename)
            except PluginTrustError as e:
                self._errors.append((scan.filename, str(e)))
                _log.warning("Plugin trust error for %s: %s", scan.filename, e)
            except Exception as e:
                self._errors.append((scan.filename, str(e)))
                _log.warning("Failed to load plugin %s: %s", scan.filename, e)

    def get_discovered(self):
        """Return list of PluginScan results (discovered but not necessarily loaded)."""
        return list(self._discovered)

    def list_plugins(self):
        """Return list of loaded (trusted) plugin instances."""
        return list(self._plugins.values())

    def get(self, name):
        return self._plugins.get(name)

    def process(self, name, audio_data, sr, **params):
        plugin = self._plugins.get(name)
        if not plugin:
            raise ValueError(f"Plugin not found: {name}")
        return plugin.process(audio_data, sr, **params)

    def get_errors(self):
        return list(self._errors)


# Singleton — discovery happens lazily when App calls discover()
_plugin_manager = PluginManager()
