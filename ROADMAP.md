# Roadmap

## v1.0.1 — Shipped!
- [x] Drag-and-drop file loading across all tabs
- [x] Global search across downloads, history, and library
- [x] Playlist auto-queue from Discovery matches
- [x] Waveform zoom and scroll in Editor
- [x] Batch stem separation
- [x] Export presets (save/load effect chains)
- [x] Dark title bar (Windows DWM API)
- [x] Recent files menu
- [x] Auto-save/restore session state
- [x] Media key shortcuts
- [x] Editor minimap with viewport indicator
- [x] Snap to zero-crossing for clean cuts
- [x] Now Playing toast notifications
- [x] Export library analysis to CSV

## v1.1 — Quality of Life — Shipped!
- [x] Cover Art Manager (19th tab) — view, add, fetch, batch-apply album artwork
- [x] Fetch cover art from iTunes Search API and MusicBrainz Cover Art Archive
- [x] Universal cover art embedding (MP3/FLAC/OGG/M4A/WAV)
- [x] Undo/redo in Effects chain (30-level stack)
- [x] Waveform color coding by frequency in Editor (spectral centroid)
- [x] Batch rename downloaded files with pattern tokens
- [x] Auto-tag metadata from analysis results (multi-format)
- [x] Enhanced Player album art (200x200, click-to-enlarge, all formats)

## v1.2 — Keyboard & Navigation — Shipped!
- [x] Tab/Shift+Tab focus cycling across all tabs
- [x] Enter to trigger primary action on each page
- [x] Keyboard shortcut customization dialog (rebind any shortcut)
- [x] Arrow key waveform seeking in Player (±5s, Shift ±15s)

## v1.3 — Streaming & Social — Shipped!
- [x] SoundCloud search (`sc:query`) and Bandcamp search (`bc:query`)
- [x] Bare text YouTube search (just type and press Enter)
- [x] Share analysis results as PNG image cards with album art
- [x] Collaborative playlist building via shared JSON export/import
- [x] Discord Rich Presence (show currently playing track)

## v2.0 — Cross-Platform & Plugins — Shipped!
- [x] Platform detection (IS_WINDOWS, IS_MACOS, IS_LINUX)
- [x] Plugin system for custom audio processors (`~/.limewire/plugins/`)
- [x] VST3/AU plugin hosting in Effects chain via pedalboard
- [x] MIDI controller mapping for Remixer (MIDI Learn mode)
- [x] Cloud sync for settings and history (export/import to cloud folders)
- [x] Auto-update mechanism (GitHub release check)
- [x] Community theme support (load theme JSON files)

## Ongoing — Shipped!
- [x] Performance optimization: recursive scan, parallel analysis (ThreadPoolExecutor)
- [x] Accessibility: High Contrast theme (13 total)
- [x] Localization: 6 languages (EN, ES, FR, DE, JA, PT)
- [x] Community theme submissions via JSON

## v2.0.1 — Visual Facelift — Shipped!
- [x] Typography refresh (body 11pt, buttons 10pt, logo Segoe UI Black 22pt)
- [x] 4 new theme tokens (BTN_PRESSED, CARD_SHADOW, DIVIDER, FOCUS_RING) across all 13 themes
- [x] WCAG contrast fixes in Light, Classic, and High Contrast themes
- [x] Smooth 3-step animated button hover transitions
- [x] Buttons get visible backgrounds (SURFACE_2) and subtle outline ring
- [x] GroupBox cards use distinct CARD_BG with thinner borders and refined accent stripe
- [x] Themed ttk scrollbars (10px width, dark-matching colors)
- [x] Monochrome Unicode toolbar icons (Segoe UI Symbol) replacing emoji
- [x] Smoothstep gradient logo bar with lightning bolt icon and drop shadow title
- [x] Compact status bar with SURFACE_3 background and semantic module colors
- [x] Toast notifications with close button, tinted borders, and larger icons
- [x] Thinner progress bars (8px) with new Thin variant (4px)
- [x] Treeview rows taller (28px) with improved heading styling

## v2.0.2 — Settings & Security Hardening — Shipped!
- [x] Dedicated Settings tab (20th tab) with theme selector, download folder, proxy, rate limit
- [x] Theme sandbox: `apply_theme()` restricted to known color keys only
- [x] Freesound sample filename sanitization via `sanitize_filename()`
- [x] Remixer temp file hardened with `tempfile.mkstemp()`
- [x] Effect preset `load_json()` bug fix (missing default argument)
- [x] Crash traceback written to log file instead of displayed to user
- [x] Toolbar icons reverted to emoji, menu backgrounds properly themed
- [x] Automated screenshot capture with anonymization (`--screenshots` CLI)
- [x] All 20 screenshots updated at 960x960

## v3.0.0 — Modular Architecture — Shipped!
- [x] Full package restructuring (`limewire/` with `core/`, `services/`, `security/`, `ui/`, `pages/`)
- [x] Security hardening module (path confinement, subprocess allowlist, JSON validation, plugin trust)
- [x] UI uniformity pass (all 20 tabs use GroupBox pattern)
- [x] Player layout fix (pixel-based album art, split GroupBoxes)
- [x] Skin Customizer tool (standalone theme editor with live preview)
- [x] Backward-compatible launcher + `python -m limewire`

## v3.3.0 — Security & Connectors — Shipped!
- [x] Music service connectors: Spotify, YouTube, TIDAL, SoundCloud, Deezer, Apple Music, Amazon Music
- [x] Cross-service playlist transfer, sync, liked songs, followed artists, saved albums
- [x] OAuth 2.0 PKCE + CSRF state validation on all connectors
- [x] DPAPI token encryption at rest (Windows CryptProtectData)
- [x] SSRF prevention with URL domain allowlists
- [x] Regex-based ID validation on all service-specific identifiers
- [x] Error message sanitization (strip tokens/secrets before display)
- [x] Security indicators in Settings > Accounts (per-service badges + info panel)
- [x] Lyrics tab — synced lyrics display and search
- [x] Visualizer tab — real-time audio visualizations
- [x] Library tab — local music library management
- [x] DJ tab — dual-deck mixing with crossfader and BPM sync
- [x] 2 new themes: Solarized, Monokai (15 total)
- [x] Bug fixes: player freq profile race condition, effects undo limit, temp file lifecycle (effects/recorder/remixer), stems batch flag reset, editor selection end label, analyze image card dict keys, batch processor label accuracy, search subtitle language setting

## Future Ideas
- [ ] Real-time collaborative mixing via WebSocket
- [ ] AI-powered auto-mixing suggestions
- [ ] Built-in sample marketplace
- [ ] Stem-based karaoke mode with lyrics overlay
- [ ] Ableton Live / Logic Pro project export

---

Have an idea? [Open a feature request](https://github.com/Ccwilliams314/LimeWire/issues/new?template=feature_request.md)
