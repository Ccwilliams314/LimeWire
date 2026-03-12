# Contributing to LimeWire

*Operations Manual v3.3*

Thanks for your interest in contributing! LimeWire is a modular Python application organized as the `limewire/` package with a backward-compatible `LimeWire.py` launcher.

## Getting Started

1. Fork the repo and clone it
2. Run `setup.bat` or install dependencies manually with `pip install -r requirements.txt`
3. Make sure FFmpeg is installed (`winget install ffmpeg`)
4. Launch with `python LimeWire.py` or `python -m limewire`

## Project Structure

```
LimeWire/
  LimeWire.py                     # Thin launcher (backward compat)
  limewire/
    __init__.py                   # __version__ = "3.3.0"
    __main__.py                   # python -m limewire support
    app.py                        # App(tk.Tk) main class
    core/
      theme.py                    # T namespace, 15 THEMES, apply_theme()
      constants.py                # Timing, dimension, format constants
      config.py                   # load_json, save_json, file paths
      platform.py                 # IS_WINDOWS, IS_MACOS, IS_LINUX
      deps.py                     # HAS_* flags, lazy loaders, optional imports
      audio_backend.py            # _AudioPlayer, _audio singleton
    i18n/
      __init__.py                 # _t(), set_language()
      strings.py                  # _LANG_STRINGS (6 languages)
    utils/
      helpers.py                  # sanitize_filename, is_url, detect_source, etc.
    services/
      analysis.py                 # BPM/key, loudness, harmonics, Camelot
      metadata.py                 # Shazam, MusicBrainz, AcoustID, lyrics
      cover_art.py                # Extract/embed/fetch album artwork
      audio_processing.py         # Waveform, demucs, pydub, spectrogram
      dj_integrations.py          # FL Studio, Serato
      plugins.py                  # PluginBase, PluginManager (hash-based trust)
      connectors/
        base.py                   # ConnectorBase ABC, TrackResult, PlaylistResult
        factory.py                # build_connector(), available_services()
        oauth.py                  # OAuth 2.0 with PKCE + CSRF state
        storage.py                # DPAPI-encrypted token storage (SQLite)
        spotify.py                # Spotify connector
        youtube.py                # YouTube Music connector
        tidal.py                  # TIDAL connector
        soundcloud.py             # SoundCloud connector
        deezer.py                 # Deezer connector
        transfer.py               # Cross-service transfer engine
        csv_io.py                 # CSV export/import for playlists
        utils.py                  # URL detection, service labels
    security/
      safe_paths.py               # Path traversal prevention, atomic writes
      safe_subprocess.py          # Binary allowlist (ffmpeg/ffprobe/yt-dlp only)
      safe_json.py                # Size limits, depth checks, key allowlists
      plugin_policy.py            # SHA-256 hash trust, scan without execute
    ui/
      widgets.py                  # ModernBtn, ClassicBtn, LimeBtn, GroupBox, etc.
      styles.py                   # init_limewire_styles()
      scroll_frame.py             # ScrollFrame base class
      tooltip.py                  # ToolTip
      toast.py                    # _ToastManager, show_toast
      command_palette.py          # CommandPalette, ShortcutRegistry
    pages/
      __init__.py                 # Re-exports all 24 page classes
      search.py                   # SearchPage
      download.py                 # DownloadPage
      playlist.py                 # PlaylistPage
      converter.py                # ConverterPage
      player.py                   # PlayerPage
      analyze.py                  # AnalyzePage
      stems.py                    # StemsPage
      effects.py                  # EffectsPage
      discovery.py                # DiscoveryPage
      samples.py                  # SamplesPage
      editor.py                   # EditorPage
      recorder.py                 # RecorderPage
      spectrogram.py              # SpectrogramPage
      pitchtime.py                # PitchTimePage
      remixer.py                  # RemixerPage
      batch_processor.py          # BatchProcessorPage
      scheduler.py                # SchedulerPage
      history.py                  # HistoryPage
      cover_art.py                # CoverArtPage
      settings.py                 # SettingsPage
      lyrics.py                   # LyricsPage
      visualizer.py               # VisualizerPage
      library.py                  # LibraryPage
      dj.py                       # DJPage
  tests/
    conftest.py                   # Shared fixtures
    test_safe_paths.py            # Path security tests
    test_safe_subprocess.py       # Subprocess allowlist tests
    test_safe_json.py             # JSON validation tests
    test_plugin_policy.py         # Plugin trust tests
    test_plugins.py               # PluginManager tests
    test_theme.py                 # Theme system tests
    test_config.py                # Config I/O tests
    test_constants.py             # Constants validation tests
    test_helpers.py               # Utility function tests
  screenshots/                    # Tab screenshots for README (24 tabs)
  SECURITY.md                     # Security policy and vulnerability scan
  requirements.txt                # Python dependencies
  setup.bat                       # Automated installer (Windows)
```

## How to Contribute

### Bug Reports
- Use the [Bug Report](https://github.com/Ccwilliams314/LimeWire/issues/new?template=bug_report.md) template
- Include your Python version, OS, and steps to reproduce
- Check `~/.limewire_crash.log` for crash details

### Feature Requests
- Use the [Feature Request](https://github.com/Ccwilliams314/LimeWire/issues/new?template=feature_request.md) template
- Describe the use case, not just the solution

### Pull Requests
1. Create a branch from `main`
2. Keep changes focused — one feature or fix per PR
3. Test at least LiveWire (default), Light, and one dark theme
4. Run the test suite: `python -m pytest tests/ -v`
5. Make sure syntax checks pass on all package files
6. If adding a new page/tab, create it in `limewire/pages/` and register in `pages/__init__.py`

## Running Tests

```bash
pip install pytest
python -m pytest tests/ -v
```

The test suite covers:
- **Security modules** — path traversal, subprocess allowlist, JSON validation, plugin trust
- **Core modules** — theme switching, config I/O, constants, URL detection
- **Services** — plugin loading, source detection, format detection

## Architecture Quick Reference

### Module Dependency Flow

```
core/ ← utils/ ← services/ ← ui/ ← pages/ ← app.py
           ↑                                      ↑
       security/                             __main__.py
```

Pages receive `app` as a constructor arg — they never import `app.py` directly. This prevents circular imports.

### Theme System

The mutable namespace `T` holds all theme colors and fonts:

```python
from limewire.core.theme import T
label = tk.Label(parent, text="Hello", bg=T.BG, fg=T.TEXT, font=T.F_BODY)
```

`T.BG`, `T.TEXT`, etc. are attribute lookups on a shared object — they always reflect the current theme. When `apply_theme("dark")` is called, all subsequent reads from `T` return dark theme values.

### Security Layer

| Module | Purpose |
|--------|---------|
| `safe_paths.py` | Path confinement, `sanitize_filename()`, `atomic_write()`, symlink prevention |
| `safe_subprocess.py` | Only `ffmpeg`, `ffprobe`, `yt-dlp` allowed — no `shell=True`, mandatory timeouts |
| `safe_json.py` | Size limits (5 MB), depth checks (10 levels), key allowlists for themes/settings |
| `plugin_policy.py` | SHA-256 hash trust — plugins discovered but not loaded until user approves |

### Config Files

All stored in `~/.limewire_*.json`:
- `history` — download log
- `settings` — user preferences (theme, proxy, etc.)
- `schedule` — scheduled downloads
- `queue` — download queue
- `analysis_cache` — BPM/key/loudness cache
- `session` — window state, last tab
- `recent_files` — recently opened files

### Code Style
- Follow existing patterns in the codebase
- Use compact formatting consistent with the rest of the file
- Thread-safety: use `widget.after(0, callback)` for UI updates from background threads
- Lazy imports for heavy libraries (librosa, demucs, whisper, etc.) via `core/deps.py`
- Use `sanitize_filename()` for any filename from external sources
- Use `tempfile.mkstemp()` for temporary files (never hardcoded paths)
- Use security modules for subprocess calls, JSON I/O, and path operations
- Service connectors: extend `ConnectorBase` in `services/connectors/base.py`; use `oauth.py` for auth, `storage.py` for token persistence
- All connector IDs must be validated with regex before API calls
- Use `_sanitize_error()` to strip tokens from error messages

### Pages (24 tabs)

| Tab | Class | Purpose |
|-----|-------|---------|
| Search & Grab | `SearchPage` | URL download with auto-detect |
| Batch Download | `DownloadPage` | Multi-URL queue |
| Playlist | `PlaylistPage` | Playlist fetch + cross-service transfer |
| Converter | `ConverterPage` | Format conversion |
| Player | `PlayerPage` | Playback with waveform |
| Analyze | `AnalyzePage` | BPM/key/loudness analysis |
| Stems | `StemsPage` | AI stem separation (Demucs) |
| Effects | `EffectsPage` | Audio effects chain |
| Discovery | `DiscoveryPage` | Library scanner |
| Samples | `SamplesPage` | Freesound browser |
| Editor | `EditorPage` | Non-destructive audio editor |
| Recorder | `RecorderPage` | Mic recording + Whisper |
| Spectrogram | `SpectrogramPage` | Spectral visualization |
| Pitch/Time | `PitchTimePage` | Pitch shift & time stretch |
| Remixer | `RemixerPage` | Stem mixing console |
| Batch Process | `BatchProcessorPage` | Bulk audio processing |
| Scheduler | `SchedulerPage` | Scheduled downloads |
| History | `HistoryPage` | Download log |
| Cover Art | `CoverArtPage` | Album artwork manager |
| Settings | `SettingsPage` | Theme, proxy, accounts, preferences |
| Lyrics | `LyricsPage` | Synced lyrics display |
| Visualizer | `VisualizerPage` | Real-time audio visualizations |
| Library | `LibraryPage` | Local music library manager |
| DJ | `DJPage` | Dual-deck mixing with crossfader |

## License

By contributing, you agree that your contributions will be licensed under the MIT License.
