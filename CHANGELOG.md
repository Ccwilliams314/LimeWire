# Changelog

## v1.1.0 — Quality of Life (2026-03-09)

### New: Cover Art Manager (19th Tab)
- Dedicated Cover Art page for viewing, adding, and managing album artwork
- Browse and embed cover art from local images (JPG/PNG)
- Auto-fetch cover art from iTunes Search API (no auth required)
- Auto-fetch cover art from MusicBrainz Cover Art Archive (no auth required)
- Batch apply cover art to entire album folders
- Remove embedded art from files
- Universal format support: MP3, FLAC, OGG, M4A, WAV
- Auto-populate artist/album fields from file tags
- Smart image processing: center-crop to square, resize to 500x500, JPEG optimization

### Enhanced Features
- **Effects chain undo/redo**: Full undo/redo stack (30 levels) for add, remove, edit, clear, and preset load operations
- **Waveform frequency coloring**: Editor waveform bars colored by spectral centroid (cyan=low, green=mid, orange=high) with toggle checkbox
- **Batch rename**: Pattern-based file renaming in History tab with tokens ({title}, {artist}, {bpm}, {key}, {date}, {n}, {ext}) and live preview
- **Multi-format auto-tagging**: AnalyzePage now writes tags to MP3, FLAC, OGG, M4A (not just MP3); optional auto-tag after analysis
- **Enhanced Player album art**: 200x200 display (up from 80x80), click to view full-size, universal format extraction (MP3/FLAC/OGG/M4A/WAV)

### Tab Count
- 19 tabs (added Cover Art)

---

## v1.0.0 — Studio Edition (2026-03-09)

First public release as **LimeWire 1.0 Studio Edition** — a complete all-in-one audio production studio.

### 18 Tabs (v1.0)

| Tab | Description |
|-----|-------------|
| Search & Grab | Download from 1000+ sites via yt-dlp |
| Batch Download | Queue multiple URLs with format selection |
| Playlist | Fetch and download entire playlists |
| Converter | Convert between mp3, wav, flac, ogg, m4a, aac, opus |
| Player | Playback with waveform, seek, A-B loop, EQ visualizer |
| Analyze | BPM, key, Camelot, loudness (LUFS), true peak |
| Stems | AI stem separation via Demucs (vocals, drums, bass, other, piano, guitar) |
| Effects | Effects chain with pedalboard (reverb, chorus, delay, compressor, etc.) |
| Discovery | Music library scanner with BPM/key indexing |
| Samples | Sample browser with preview and metadata |
| Editor | Non-destructive audio editor with trim, cut, fade, merge, undo/redo |
| Recorder | Microphone recording with VU meter, live waveform, Whisper transcription |
| Spectrogram | Linear/Mel/CQT spectrograms with custom colormaps |
| Pitch & Time | Pitch shift, time stretch, BPM-synced rate calc |
| Remixer | Per-stem volume, pan, mute/solo mixing console |
| Batch Process | Normalize, convert, fade, trim silence across many files |
| Scheduler | Schedule downloads for later |
| History | Full download history with search and re-download |

### Features

- Track identification via Shazam, MusicBrainz, Chromaprint/AcoustID, Apple Music
- Harmonic mixing with Camelot wheel compatibility
- Smart playlists with energy filtering and harmonic key flow
- Noise reduction, lyrics lookup, Serato crate export, FL Studio integration
- 12 themes: LiveWire (default), Classic Light, Classic Dark, Modern Dark, Synthwave, Dracula, Catppuccin, Tokyo Night, Spotify, LimeWire Classic, Nord, Gruvbox
- Gradient logo bar, icon toolbar, command palette (Ctrl+K), toast notifications
- Drag-and-drop file loading across all tabs (tkinterdnd2)
- Global search in command palette (history + discovery library)
- Editor waveform zoom/scroll (up to 32x) with minimap overview
- Effect chain presets (save/load as JSON)
- Dark title bar via Windows DWM API
- Recent files menu (File > Recent Files)
- Auto-save/restore session state between launches
- Batch stem separation (queue multiple files)
- Export library analysis to CSV
- Send to Player (auto-queue from Discovery)
- Media key shortcuts (Ctrl+Arrow for next/prev/volume)
- Now Playing toast notification on track change
- Snap to zero-crossing for clean Editor cuts
- Anonymized default paths, atomic JSON config writes, thread-safe operations
