"""Plugin system — custom audio processors loaded from plugins directory."""
import os, logging, importlib.util

_log = logging.getLogger("LimeWire")

PLUGINS_DIR = os.path.join(os.path.expanduser("~"), ".limewire", "plugins")


class PluginBase:
    """Base class for LimeWire audio processor plugins.

    Subclass this and implement process(audio_data, sr, **params) → audio_data.
    """
    name = "Unnamed Plugin"
    description = ""
    category = "Custom"
    parameters = {}  # {"param_name": {"type":"float","min":0,"max":1,"default":0.5,"label":"..."}}

    def process(self, audio_data, sr, **params):
        """Process audio data (numpy array) at sample rate sr. Return processed array."""
        return audio_data


class PluginManager:
    """Discovers, loads, and manages audio processor plugins."""

    def __init__(self):
        self._plugins = {}   # name → plugin_instance
        self._errors = []

    def discover(self):
        """Scan plugins directory and load all .py plugin files."""
        self._plugins = {}
        self._errors = []
        os.makedirs(PLUGINS_DIR, exist_ok=True)
        plugin_files = [fn for fn in os.listdir(PLUGINS_DIR)
                        if fn.endswith(".py") and not fn.startswith("_")]
        if not plugin_files:
            return
        _log.info(f"Loading {len(plugin_files)} plugin(s) from {PLUGINS_DIR}")
        for fn in plugin_files:
            path = os.path.join(PLUGINS_DIR, fn)
            try:
                spec = importlib.util.spec_from_file_location(fn[:-3], path)
                mod = importlib.util.module_from_spec(spec)
                _log.info(f"[PLUGIN] Loading: {path} (review before use)")
                spec.loader.exec_module(mod)
                # Find all PluginBase subclasses in the module
                for attr_name in dir(mod):
                    attr = getattr(mod, attr_name)
                    if (isinstance(attr, type) and issubclass(attr, PluginBase)
                            and attr is not PluginBase):
                        inst = attr()
                        self._plugins[inst.name] = inst
                        _log.info(f"Loaded plugin: {inst.name} from {fn}")
            except Exception as e:
                self._errors.append((fn, str(e)))
                _log.warning(f"Failed to load plugin {fn}: {e}")

    def list_plugins(self):
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


_plugin_manager = PluginManager()
try:
    _plugin_manager.discover()
except Exception:
    pass
