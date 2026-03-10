# Contributing to LimeWire

Thanks for your interest in contributing! LimeWire is a single-file Python application, so the barrier to entry is low.

## Getting Started

1. Fork the repo and clone it
2. Run `setup.bat` or install dependencies manually with `pip install -r requirements.txt`
3. Make sure FFmpeg is installed (`winget install ffmpeg`)
4. Launch with `python LimeWire.py`

## Project Structure

```
LimeWire.py              — Entire application (single file, ~7,300 lines)
requirements.txt         — Python dependencies
setup.bat                — Automated installer (Windows)
screenshots/             — Tab screenshots for README (20 tabs)
SECURITY.md              — Security policy and vulnerability scan report
```

The app is intentionally a single file. This makes it easy to distribute, run, and understand without complex project scaffolding.

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
3. Test at least LiveWire (default), Classic Light, and one dark theme
4. Make sure `python -c "import py_compile; py_compile.compile('LimeWire.py', doraise=True)"` passes
5. If adding a new page/tab, update the toolbar items list and `_build_notebook()` page registration

### Code Style
- Follow existing patterns in the codebase
- Use compact formatting consistent with the rest of the file
- Thread-safety: use `self.after(0, callback)` for UI updates from background threads
- Lazy imports for heavy libraries (librosa, demucs, whisper, etc.)
- Use `sanitize_filename()` for any filename from external sources
- Use `tempfile.mkstemp()` for temporary files (never hardcoded paths)

## Architecture Quick Reference

- `App(tk.Tk)` — main window, holds `self.pages` dict of 20 page instances
- All pages extend `ScrollFrame` — a custom scrollable frame
- Widget factories: `ModernBtn`, `ClassicBtn`, `LimeBtn`, `OrangeBtn`, `GroupBox`, `ClassicEntry`, `ClassicCombo`, `ClassicCheck`, `ClassicListbox`, `ClassicProgress`
- Theme system: 13 theme dicts with `apply_theme()` (key-allowlisted) + `_reconfig_all()` for live switching
- Config files: `~/.limewire_*.json` (history, settings, schedule, queue, analysis_cache, session, recent_files)
- Security: see `SECURITY.md` for vulnerability scan report and mitigation details

### Pages (20 tabs)

| Tab | Class | Purpose |
|-----|-------|---------|
| Search & Grab | `SearchPage` | URL download with auto-detect |
| Batch Download | `DownloadPage` | Multi-URL queue |
| Playlist | `PlaylistPage` | YouTube playlist fetch |
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
| Settings | `SettingsPage` | Theme, proxy, preferences |

## License

By contributing, you agree that your contributions will be licensed under the MIT License.
