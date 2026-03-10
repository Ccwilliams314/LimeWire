<h1 align="center">
  <br>
  LimeWire
  <br>
</h1>

<h3 align="center">v1.1 Studio Edition &mdash; The Modern Music Utility for Everything</h3>

<p align="center">
  <img src="https://img.shields.io/badge/python-3.10+-blue?style=flat-square&logo=python" alt="Python">
  <img src="https://img.shields.io/badge/platform-Windows%2010%2F11-0078D6?style=flat-square&logo=windows" alt="Windows">
  <img src="https://img.shields.io/badge/tabs-19-2ECC71?style=flat-square" alt="19 Tabs">
  <img src="https://img.shields.io/badge/modules-40+-orange?style=flat-square" alt="40+ Integrations">
  <img src="https://img.shields.io/badge/license-MIT-green?style=flat-square" alt="License">
</p>

<p align="center">
  <strong>Download. Play. Analyze. Edit. Separate. Remix. Process. All in one app.</strong>
</p>

<p align="center">
  <img src="screenshots/01_search.png" width="700" alt="LimeWire Search & Grab">
</p>

---

## What is LimeWire?

LimeWire is a **19-tab all-in-one audio production studio** built with Python and tkinter. It started as a simple YouTube downloader and evolved into a comprehensive music utility covering the entire audio workflow &mdash; from downloading and converting, to analysis, editing, stem separation, remixing, and batch processing.

### Key Highlights

- **Download from 1000+ sites** via yt-dlp (YouTube, Spotify, SoundCloud, Bandcamp, etc.)
- **AI stem separation** with Demucs (vocals, drums, bass, other, piano, guitar)
- **Audio analysis** &mdash; BPM, key, Camelot notation, loudness (LUFS), waveform
- **Track identification** &mdash; Shazam, MusicBrainz, Chromaprint, Apple Music
- **Non-destructive editor** with undo/redo, waveform selection
- **Microphone recording** with Whisper AI transcription
- **Stem remixer** &mdash; mix individual stems with volume, pan, mute/solo
- **Batch processor** &mdash; normalize, convert, fade, trim silence across many files
- **Smart playlists** with energy filtering and harmonic key matching
- **Cover art manager** &mdash; view, add, fetch (iTunes/MusicBrainz), batch-apply album artwork
- **Effects undo/redo** &mdash; 30-level undo stack for the effects chain
- **Frequency waveform** &mdash; Editor bars colored by spectral centroid
- **Batch file rename** &mdash; pattern-based renaming with metadata tokens
- **Multi-format tagging** &mdash; write analysis results to MP3, FLAC, OGG, M4A
- **Modern UI** with rounded buttons, gradient header, command palette, live themes

---

## Screenshots

<details>
<summary><strong>Click to expand all 19 tabs</strong></summary>

| Tab | Screenshot |
|-----|-----------|
| **Search & Grab** | <img src="screenshots/01_search.png" width="600"> |
| **Batch Download** | <img src="screenshots/02_download.png" width="600"> |
| **Playlist** | <img src="screenshots/03_playlist.png" width="600"> |
| **Converter** | <img src="screenshots/04_converter.png" width="600"> |
| **Player** | <img src="screenshots/05_player.png" width="600"> |
| **Analyze** | <img src="screenshots/06_analyze.png" width="600"> |
| **Stems** | <img src="screenshots/07_stems.png" width="600"> |
| **Effects** | <img src="screenshots/08_effects.png" width="600"> |
| **Discovery** | <img src="screenshots/09_discovery.png" width="600"> |
| **Samples** | <img src="screenshots/10_samples.png" width="600"> |
| **Editor** | <img src="screenshots/11_editor.png" width="600"> |
| **Recorder** | <img src="screenshots/12_recorder.png" width="600"> |
| **Spectrogram** | <img src="screenshots/13_spectrogram.png" width="600"> |
| **Pitch/Time** | <img src="screenshots/14_pitchtime.png" width="600"> |
| **Remixer** | <img src="screenshots/15_remixer.png" width="600"> |
| **Batch Process** | <img src="screenshots/16_batch.png" width="600"> |
| **Scheduler** | <img src="screenshots/17_schedule.png" width="600"> |
| **History** | <img src="screenshots/18_history.png" width="600"> |
| **Cover Art** | <img src="screenshots/19_coverart.png" width="600"> |

</details>

---

## Installation

### Prerequisites

- **Python 3.10+** (tested with 3.14)
- **FFmpeg** on PATH

### Quick Start

```bash
# 1. Install FFmpeg
winget install ffmpeg

# 2. Install core dependencies
pip install yt-dlp pillow requests mutagen pyglet

# 3. Run
python LimeWire.py
```

### Optional Modules

Install only what you need:

```bash
# Audio analysis (BPM, key, loudness)
pip install librosa soundfile pyloudnorm

# Track identification
pip install musicbrainzngs pyacoustid
pip install shazamio  # Python 3.12 or earlier only

# AI stem separation (requires PyTorch)
pip install demucs

# Audio editing & recording
pip install pydub sounddevice pyrubberband

# Whisper transcription
pip install openai-whisper

# Audio effects
pip install pedalboard

# DJ integration
pip install pyflp

# Drag & drop support
pip install tkinterdnd2
```

### All-in-One Install

```bash
pip install yt-dlp pillow requests mutagen pyglet librosa soundfile pyloudnorm musicbrainzngs pyacoustid demucs pydub sounddevice pyrubberband openai-whisper pedalboard
```

> The status bar (bottom-right) shows module count (e.g., `12/14 modules`). Click it to see what's missing.

---

## Features

### Download & Library

| Feature | Description |
|---------|-------------|
| **Search & Grab** | Paste URL, auto-detect source, download in any format (MP3/WAV/FLAC/OGG/M4A/AAC/OPUS) |
| **Batch Download** | Queue multiple URLs, persistent queue, retry failed downloads |
| **Playlist Download** | Fetch YouTube playlists, select individual tracks, batch download |
| **Converter** | Convert between audio formats with ffmpeg, preserves metadata |
| **History** | Complete download log with search, replay, and management |
| **Scheduler** | Schedule downloads for specific times, background polling |
| **Cover Art** | View, add, fetch (iTunes/MusicBrainz), batch-apply album artwork |

### Playback & Analysis

| Feature | Description |
|---------|-------------|
| **Player** | Waveform display, EQ spectrum, album art, speed control, A-B loop, crossfade, M3U playlists |
| **Analyze** | BPM, key, Camelot, LUFS, true peak, waveform. Shazam/MusicBrainz/Chromaprint/Apple Music ID |
| **Loudness Targeting** | Platform presets (Spotify/YouTube/Apple Music/CD/Club/Podcast), 2-pass ffmpeg loudnorm |
| **Discovery** | Library scanner with BPM/key caching, harmonic mixing, smart playlists with energy filter |
| **Spectrogram** | Linear/Mel/CQT spectrograms with viridis/magma/plasma/inferno colormaps, PNG export |

### Production & Editing

| Feature | Description |
|---------|-------------|
| **Stems** | AI separation via Demucs (htdemucs, htdemucs_ft, mdx_extra). Vocals, drums, bass, other, piano, guitar |
| **Remixer** | Mix separated stems: per-stem volume (0-150%), pan (L-R), mute/solo. Preview and export |
| **Editor** | Non-destructive trim/cut/fade/merge with full undo/redo stack and waveform selection |
| **Recorder** | Mic recording with VU meter, live waveform, Whisper AI transcription, SRT export |
| **Pitch/Time** | Pitch shift (semitones), time stretch (rate), BPM auto-detect, vocal isolation |
| **Effects** | Pedalboard effects chain: gain, compressor, limiter, reverb, delay, chorus, filters |
| **Batch Process** | Bulk: normalize LUFS, convert format, fade in/out, trim silence, strip metadata |
| **Samples** | Freesound.org browser with preview and download |

---

## Keyboard Shortcuts

| Shortcut | Action |
|----------|--------|
| `Ctrl+K` | Command Palette (fuzzy search pages, history, library) |
| `Ctrl+D` | Download / Grab URL |
| `Ctrl+O` | Open downloads folder |
| `Space` | Play / Pause |
| `Ctrl+Right` | Next track |
| `Ctrl+Left` | Previous track |
| `Ctrl+Up/Down` | Volume up/down |
| `Shift+Escape` | Quick close |
| `Ctrl+?` | Show shortcuts dialog |

---

## Themes

12 built-in themes with **live switching** (no restart required):

| Theme | Style |
|-------|-------|
| **LiveWire** (default) | Electric cyan/blue, dark navy background |
| **Classic Light** | Warm neutrals, soft green accents |
| **Classic Dark** | Rich dark, green accents |
| **Modern Dark** | GitHub-inspired, high contrast |
| **Synthwave** | Neon pink/purple, retro aesthetic |
| **Dracula** | Purple/cyan/green, popular dev theme |
| **Catppuccin** | Pastel tones, easy on the eyes |
| **Tokyo Night** | Blue-tinted dark, calm palette |
| **Spotify** | Green accents on dark background |
| **LimeWire Classic** | Original lime green nostalgia |
| **Nord** | Arctic blue-grey, muted tones |
| **Gruvbox** | Warm retro brown/orange/green |

Switch via: **Tools > Cycle Theme** or **Ctrl+K > type "theme"**

---

## Architecture

Single-file application (`~5,500 lines`):

```
LimeWire.py
├── Imports & dependency detection (HAS_LIBROSA, HAS_DEMUCS, etc.)
├── Theme system (12 palettes, semantic tokens, apply_theme())
├── Font system (Segoe UI, Cascadia Code, heading hierarchy)
├── Utility functions (audio loading, waveform, spectrogram, pitch/time)
├── Modern widget system (ModernBtn, ToolTip, ToastManager, CommandPalette)
├── 18 Page classes (all extend ScrollFrame)
├── App class (tk.Tk) — window, menubar, logo bar, toolbar, notebook, statusbar
└── Launch block
```

### Data Files

| File | Purpose |
|------|---------|
| `~/.limewire_history.json` | Download history |
| `~/.limewire_schedule.json` | Scheduled downloads |
| `~/.limewire_settings.json` | User preferences (theme, paths) |
| `~/.limewire_queue.json` | Batch download queue |
| `~/.limewire_analysis_cache.json` | BPM/key analysis cache |
| `~/.limewire_session.json` | Session state (loaded files, active tab) |
| `~/.limewire_recent_files.json` | Recently opened files |

---

## Highlights

### Modern UI
- Canvas-based **rounded buttons** with hover/press animations
- **Gradient logo bar** with pill-shaped version badge
- **Icon + label toolbar** with active tab indicator
- **Segoe UI** typography across all themes
- Professional **color palettes** with semantic tokens (success/warning/error)
- **Spacing constants** system for consistent layout

### UX Infrastructure
- **Command Palette** (`Ctrl+K`) &mdash; fuzzy search pages, history, and library
- **Tooltips** on toolbar buttons
- **Toast notification queue** &mdash; stacks up to 4, severity colors
- **Shortcut Registry** with `Ctrl+?` help dialog
- **Live theme switching** &mdash; 12 themes, no restart required
- **Dark title bar** &mdash; Windows DWM API matches theme
- **Drag-and-drop** &mdash; drop audio files onto any tab
- **Recent files menu** &mdash; File > Recent Files (persisted)
- **Session restore** &mdash; remembers loaded files and active tab between launches
- **Media keys** &mdash; Ctrl+Arrow for next/prev/volume

### Studio Features
- **Stem Remixer** &mdash; mix Demucs stems with per-stem volume/pan/mute/solo
- **Batch stem separation** &mdash; queue multiple files for Demucs
- **Batch Processor** &mdash; normalize, convert, fade, trim silence, strip metadata
- **Effects presets** &mdash; save/load effect chains as JSON
- **Loudness Targeting** &mdash; platform presets with 2-pass ffmpeg loudnorm
- **Smart Playlists** &mdash; energy-level filtering + 4 sort modes + send to Player
- **CSV export** &mdash; export library analysis from Discovery
- **Editor zoom** &mdash; waveform zoom up to 32x with minimap overview
- **Snap to zero-crossing** &mdash; clean cut edges in Editor
- **Player crossfade** control (0-5000ms)
- **Up Next** track indicator + Now Playing toast

---

## Troubleshooting

| Issue | Solution |
|-------|----------|
| "FFmpeg not found" | `winget install ffmpeg` or add ffmpeg to PATH |
| Module not found | Check status bar module counter, install with pip |
| Downloads fail | `pip install -U yt-dlp` to update |
| Demucs slow | Install PyTorch with CUDA for GPU acceleration |
| Whisper fails | `pip install openai-whisper` (first run downloads model) |
| Theme looks wrong | Tools > Cycle Theme. Requires Segoe UI font (Windows 10/11) |

---

## File Structure

```
LimeWire/
├── LimeWire.py                              # Main application
├── README.md                                # This file
├── LimeWire_v1.0_Operation_Manual.pdf       # 43-page operation manual
└── screenshots/                             # App screenshots (19 tabs)
    ├── 01_search.png
    ├── 02_download.png
    ├── ...
    └── 18_history.png
```

---

## Tech Stack

| Component | Technology |
|-----------|-----------|
| Language | Python 3.10+ |
| GUI | tkinter / ttk |
| Downloads | yt-dlp |
| Audio Playback | pyglet |
| Metadata | mutagen |
| Audio Processing | pydub, ffmpeg |
| Analysis | librosa, pyloudnorm |
| Stem Separation | Demucs (Meta AI) |
| Pitch/Time | pyrubberband |
| Recording | sounddevice |
| Transcription | openai-whisper |
| Effects | pedalboard (Spotify) |
| Track ID | shazamio, pyacoustid, musicbrainzngs |

---

<p align="center">
  <em>"Definitely virus-free since 2024"</em>
</p>
