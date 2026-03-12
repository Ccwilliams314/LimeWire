"""Settings registry — central schema, defaults, and helpers for all app settings."""


# ── Schema ───────────────────────────────────────────────────────────────────
# Each entry: (default, type)
# Types: "bool", "int", "float", "str", "choice"
# For "choice", default is one of the valid values (validated at read time).

SETTINGS_SCHEMA = {
    # ── General (top-level keys for backward compat) ─────────────────────────
    "clipboard_watch":  (True, "bool"),
    "proxy":            ("", "str"),
    "rate_limit":       ("", "str"),
    "discord_rpc":      (True, "bool"),
    "confirm_on_exit":  (False, "bool"),
    "restore_window_geometry": (True, "bool"),
    "restore_active_tab":      (True, "bool"),

    # ── Audio ────────────────────────────────────────────────────────────────
    "audio.output_device":       ("Default", "str"),
    "audio.default_format":      ("mp3", "str"),
    "audio.default_bitrate":     ("320k", "str"),
    "audio.default_sample_rate": (44100, "int"),
    "audio.default_channels":    (2, "int"),

    # ── Playback ─────────────────────────────────────────────────────────────
    "playback.crossfade_ms":  (0, "int"),
    "playback.gapless":       (False, "bool"),
    "playback.replay_gain":   ("off", "str"),

    # ── Performance ──────────────────────────────────────────────────────────
    "perf.max_download_threads": (2, "int"),
    "perf.max_analysis_workers": (4, "int"),
    "perf.discovery_cache_max":  (5000, "int"),
    "perf.demucs_device":        ("auto", "str"),

    # ── UI ───────────────────────────────────────────────────────────────────
    "ui.font_scale": (1.0, "float"),

    # ── Service connectors ─────────────────────────────────────────────────
    "spotify_client_id":     ("", "str"),
    "spotify_client_secret": ("", "str"),
    "youtube_api_key":       ("", "str"),
    "youtube_client_id":     ("", "str"),
    "youtube_client_secret": ("", "str"),
    "soundcloud_client_id":  ("", "str"),
    "tidal_client_id":       ("", "str"),
    "tidal_client_secret":   ("", "str"),
}

# ── Per-page settings schemas ────────────────────────────────────────────────
# Key: page_key, Value: dict of {setting_name: (default, type)}

PAGE_SETTINGS_SCHEMA = {
    "player": {
        "eq_preset":       ("Flat", "str"),
        "art_display_size": (160, "int"),
    },
    "search": {
        "subtitle_lang":   ("en", "str"),
        "output_template": ("%(title)s.%(ext)s", "str"),
        "file_conflict":   ("skip", "str"),
    },
    "download": {
        "output_template": ("%(title)s.%(ext)s", "str"),
        "file_conflict":   ("skip", "str"),
        "retry_count":     (3, "int"),
        "retry_timeout":   (30, "int"),
    },
    "converter": {
        "sample_rate":   ("keep", "str"),
        "channels":      ("keep", "str"),
        "normalize_tp":  (-1.5, "float"),
        "normalize_lra": (11.0, "float"),
    },
    "recorder": {
        "sample_rate":       (44100, "int"),
        "channels":          (1, "int"),
        "vu_warn_threshold": (0.7, "float"),
        "vu_clip_threshold": (0.9, "float"),
    },
    "effects": {
        "preview_duration_s": (5, "int"),
        "undo_max":           (30, "int"),
        "output_suffix":      ("_fx", "str"),
    },
    "stems": {
        "demucs_device":      ("auto", "str"),
        "stem_output_format": ("wav", "str"),
    },
    "analyze": {
        "custom_lufs_target": (-14.0, "float"),
        "normalize_tp":       (-1.5, "float"),
        "normalize_lra":      (11.0, "float"),
    },
    "editor": {
        "default_fade_ms":        (500, "int"),
        "max_zoom":               (32, "int"),
        "normalization_target_db": (-1.0, "float"),
    },
    "spectrogram": {
        "default_sample_rate": (22050, "int"),
        "db_range_min":        (-80, "int"),
        "db_range_max":        (0, "int"),
    },
    "discovery": {
        "max_scan_files":    (50000, "int"),
        "cache_limit":       (5000, "int"),
        "analysis_workers":  (4, "int"),
    },
    "playlist": {
        "concurrent_downloads": (1, "int"),
        "track_numbering":      (True, "bool"),
    },
    "batch": {
        "silence_threshold_db": (-50, "int"),
        "fade_curve":           ("linear", "str"),
    },
    "history": {
        "history_limit": (300, "int"),
        "sort_by":       ("date_desc", "str"),
    },
    "lyrics": {
        "font_family": ("Segoe UI", "str"),
        "alignment":   ("center", "str"),
    },
    "visualizer": {
        "bar_count":      (64, "int"),
        "particle_count": (200, "int"),
    },
    "dj": {
        "speed_range":      (8, "int"),
        "crossfader_curve": ("linear", "str"),
    },
    "remixer": {
        "pan_law":           ("linear", "str"),
        "export_sample_rate": (44100, "int"),
        "export_bit_depth":   (24, "int"),
    },
    "library": {
        "scan_batch_size": (50, "int"),
    },
    "coverart": {
        "art_display_size":    (200, "int"),
        "art_fetch_resolution": (500, "int"),
    },
    "samples": {
        "results_per_page":  (30, "int"),
        "request_timeout":   (15, "int"),
    },
    "pitchtime": {
        "semitone_range": (12, "int"),
    },
    "schedule": {
        "retry_count":   (0, "int"),
        "retry_delay_s": (60, "int"),
    },
}


# ── Helper functions ─────────────────────────────────────────────────────────

def get_setting(settings, key):
    """Get a global setting value, falling back to schema default.

    For dotted keys like 'audio.default_format', looks up
    settings['audio.default_format'] first (flat), then schema default.
    """
    if key in settings:
        return settings[key]
    schema_entry = SETTINGS_SCHEMA.get(key)
    if schema_entry:
        return schema_entry[0]
    return None


def get_page_setting(settings, page_key, setting_key):
    """Get a per-page setting value, falling back to schema default."""
    page_s = settings.get("page_settings", {}).get(page_key, {})
    if setting_key in page_s:
        return page_s[setting_key]
    page_schema = PAGE_SETTINGS_SCHEMA.get(page_key, {})
    entry = page_schema.get(setting_key)
    if entry:
        return entry[0]
    return None


def set_page_setting(settings, page_key, setting_key, value):
    """Set a per-page setting value."""
    if "page_settings" not in settings:
        settings["page_settings"] = {}
    if page_key not in settings["page_settings"]:
        settings["page_settings"][page_key] = {}
    settings["page_settings"][page_key][setting_key] = value


def apply_defaults(settings):
    """Fill in missing top-level settings from schema defaults.

    Does NOT overwrite existing values — safe for migration.
    """
    for key, (default, _typ) in SETTINGS_SCHEMA.items():
        if key not in settings:
            settings[key] = default
    # Ensure page_settings dict exists
    if "page_settings" not in settings:
        settings["page_settings"] = {}
    return settings
