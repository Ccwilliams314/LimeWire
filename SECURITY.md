# Security Policy

## Supported Versions

| Version | Supported |
|---------|-----------|
| 3.3.x   | Yes       |
| 3.0.x   | No        |
| 2.0.x   | No        |
| 1.x     | No        |

## Reporting a Vulnerability

If you discover a security vulnerability, please report it responsibly:

1. **Do not** open a public issue
2. Email the maintainer directly (or use GitHub's private vulnerability reporting)
3. Include steps to reproduce and potential impact
4. Allow reasonable time for a fix before public disclosure

## Scope

LimeWire is a local desktop application. Security concerns include:
- Command injection via user-supplied URLs or filenames
- Path traversal in file operations
- Unsafe deserialization of JSON config files
- Dependencies with known CVEs
- Plugin system code execution
- Theme file globals overwrite
- OAuth token theft or misuse
- Service connector SSRF or injection

## Vulnerability Scan Report (v3.3.0)

**Scan Date:** 2026-03-11
**Method:** Manual code review of full codebase (~9,000 lines across 24 pages + 7 connectors)

### Summary

| Severity | Found | Fixed | Remaining |
|----------|-------|-------|-----------|
| Critical | 0     | —     | 0         |
| High     | 1     | 1     | 0         |
| Medium   | 4     | 4     | 0         |
| Low      | 12    | 1     | 11        |
| Info     | 2     | —     | 2         |

### High Severity (0 remaining)

| # | Finding | Status | Notes |
|---|---------|--------|-------|
| 1.1 | Plugin system auto-executes `.py` files from `~/.limewire/plugins/` without user confirmation | **Fixed** | Plugins are now discovered but NOT loaded until user approves their SHA-256 hash. Trust auto-revoked on file change. See `limewire/security/plugin_policy.py`. |

### Medium Severity (4 fixed in v3.0.0)

| # | Finding | Status |
|---|---------|--------|
| 2.1 | Freesound sample filename not sanitized | **Fixed** — now uses `sanitize_filename()` |
| 3.2 | Community theme JSON could overwrite arbitrary globals via `apply_theme()` | **Fixed** — theme keys restricted to allowlist |
| 5.1 | Remixer preview used predictable temp file path | **Fixed** — now uses `tempfile.mkstemp()` with cleanup |
| 7.3 | Effect preset `load_json()` missing default argument | **Fixed** — added missing `{}` default |
| 10.1 | Full Python traceback shown to user on crash | **Fixed** — traceback written to `~/.limewire_crash.log` |

### Low Severity (12 — acceptable risk for desktop app)

| # | Finding | Status |
|---|---------|--------|
| 1.2 | FL Studio path from settings | Mitigated (list-form subprocess, extension check) |
| 1.3 | subprocess calls with file paths | Mitigated (list-form, never shell=True, timeouts) |
| 2.2 | JSON playlist imports trusted file paths | Partially mitigated (extension filter + exists check) |
| 4.3 | Spoofed User-Agent for Shazam API | Noted (common practice) |
| 5.2 | Temp file cleanup race during audio playback | **Fixed in v3.3.0** — deferred cleanup pattern (store path, delete on next use) |
| 6.2 | Freesound API token in URL query parameter | Noted (API's required auth method) |
| 8.2 | Player playlist mutations without lock | Acceptable (all on main tkinter thread) |
| 8.3 | Discovery library dict from background thread | Low risk (Python GIL protection) |
| 9.1 | History file growth | HISTORY_MAX constant enforced |
| 9.3 | Library scanner walks entire directory trees | User-initiated, background thread |
| 9.4 | ThreadPool worker count from UI | Bounded by Spinbox min/max |
| 12.2 | Proxy string applied without validation | Acceptable (user-entered setting) |
| 12.4 | Cloud sync import trusts remote JSON | Low risk (user explicitly triggers import) |

## Mitigations in Place

### Input Validation
- URL scheme validation via `urllib.parse.urlparse()` — only http/https allowed
- `sanitize_filename()` strips path separators, Windows reserved names, control chars
- `MAX_URL_LENGTH = 500` prevents oversized URLs
- `_AUDIO_EXTS` frozenset restricts playlist imports to audio formats
- Effect preset names validated against `_ALLOWED_EFFECTS` frozenset

### Code Execution
- `apply_theme()` restricted to known color key allowlist (prevents globals overwrite)
- VST plugins from presets require `user_loaded` flag (only set via interactive file dialog)
- `_ALLOWED_EFFECTS` frozenset blocks unknown effect names from `getattr(pedalboard, ...)`
- **Plugin trust system** (`limewire/security/plugin_policy.py`): SHA-256 hash-based approval, no auto-execution, auto-revoke on file change
- **Subprocess allowlist** (`limewire/security/safe_subprocess.py`): only ffmpeg/ffprobe/yt-dlp permitted, no `shell=True`, mandatory timeouts, audit logging
- **JSON validation** (`limewire/security/safe_json.py`): size limits, depth checks, key allowlists, hex color validation for themes

### File System
- Atomic JSON writes via `tmp + os.replace()` prevents config corruption
- `tempfile.mkstemp()` used for all temporary files (6 locations) with cleanup
- Path traversal check on batch rename: validates output stays in parent directory
- **Safe paths** (`limewire/security/safe_paths.py`): centralized path resolution, symlink traversal prevention, allowed-root enforcement for writes

### Network
- SSL certificate verification enabled (requests library default)
- No network listeners — all connections are outbound only
- No auto-execution of downloaded content
- AcoustID and Genius API keys loaded from environment variables (not hardcoded)

### Thread Safety
- `threading.Lock` on: scheduler jobs, download counter, waveform data, recorder frames
- `_playlist_set` for O(1) membership checks
- Background threads use `widget.after(0, callback)` for UI updates

### Error Handling
- Error strings truncated to 60-80 chars before display (`str(e)[:60]`)
- Crash tracebacks written to `~/.limewire_crash.log` (not shown in UI)
- `winfo_exists()` check before `.after()` rescheduling prevents shutdown crashes
- Connector errors sanitized via `_sanitize_error()` — tokens, secrets, and keys stripped before display

### Service Connector Security (v3.3.0)

All 7 music service connectors (Spotify, YouTube, TIDAL, SoundCloud, Deezer, Apple Music, Amazon Music) are hardened with defense-in-depth:

| Protection | Implementation |
|-----------|---------------|
| **OAuth 2.0 PKCE** | `generate_pkce()` creates 128-byte code verifier + S256 challenge. Prevents authorization code interception. |
| **CSRF State** | `generate_state()` creates 64-byte cryptographic state parameter. Validated on every OAuth callback. |
| **Encrypted Storage** | Tokens encrypted at rest via Windows DPAPI (`CryptProtectData`/`CryptUnprotectData`). Schema migration removes plaintext `client_secret` columns. |
| **ID Validation** | Regex patterns (`_SPOTIFY_ID_RE`, `_TIDAL_ID_RE`, `_SC_ID_RE`, `_DEEZER_ID_RE`, `_valid_video_id`, `_valid_playlist_id`) validate all service-specific identifiers before API calls. Prevents path traversal and injection. |
| **SSRF Prevention** | URL domain allowlists (`_safe_yt_url`, `_safe_sc_url`) restrict outbound requests to expected API domains only. |
| **Error Sanitization** | `_sanitize_error()` scrubs tokens, client secrets, and API keys from error messages before they reach the UI or logs. |
| **Pagination Bounds** | `MAX_TRACKS = 10000` caps all paginated API responses to prevent resource exhaustion. |
