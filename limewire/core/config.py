"""Configuration file I/O — load_json, save_json, file paths, migration."""
import os, json, logging, tempfile

_log = logging.getLogger("LimeWire")


def _migrate_config(name):
    """Migrate old .ytdl_* config to .limewire_* if needed."""
    new = os.path.join(os.path.expanduser("~"), f".limewire_{name}.json")
    if not os.path.exists(new):
        old = os.path.join(os.path.expanduser("~"), f".ytdl_{name}.json")
        if os.path.exists(old):
            try: os.rename(old, new)
            except Exception: pass
    return new


# Config file paths
HISTORY_FILE = _migrate_config("history")
SCHEDULE_FILE = _migrate_config("schedule")
SETTINGS_FILE = _migrate_config("settings")
QUEUE_FILE = _migrate_config("queue")
ANALYSIS_CACHE_FILE = _migrate_config("analysis_cache")
SESSION_FILE = _migrate_config("session")
RECENT_FILES_FILE = _migrate_config("recent_files")
LIBRARY_FILE = _migrate_config("library")
SMART_PLAYLISTS_FILE = _migrate_config("smart_playlists")


def load_json(p, d):
    """Load JSON file with fallback default."""
    try:
        with open(p) as f: return json.load(f)
    except Exception as e:
        if os.path.exists(p): _log.warning("Failed to load %s: %s", p, e)
        return d


def save_json(p, d):
    """Atomic JSON write — write to tmp file then rename to prevent corruption."""
    try:
        tmp = p + ".tmp"
        with open(tmp, "w") as f: json.dump(d, f, indent=2)
        os.replace(tmp, p)  # atomic on same filesystem
    except Exception as e:
        try: os.unlink(p + ".tmp")
        except OSError: pass
        _log.warning(f"save_json failed for {p}: {e}")
