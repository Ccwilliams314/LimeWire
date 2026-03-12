"""SQLite persistence for linked accounts, track mappings, and transfer history.

Security: Tokens are encrypted at rest using Windows DPAPI (CryptProtectData)
when available, with a fallback obfuscation layer on other platforms.
Client secrets are NOT stored — load from settings at runtime only.
"""

from __future__ import annotations

import base64
import os
import sqlite3
import sys
import time
import threading

DB_DIR = os.path.join(os.path.expanduser("~"), ".limewire")
DB_PATH = os.path.join(DB_DIR, "connectors.db")

_local = threading.local()

# ── Token encryption ─────────────────────────────────────────────────────────

def _encrypt_token(plaintext: str) -> str:
    """Encrypt a token for at-rest storage. Uses DPAPI on Windows."""
    if not plaintext:
        return ""
    data = plaintext.encode("utf-8")
    try:
        if sys.platform == "win32":
            import ctypes
            import ctypes.wintypes

            class DATA_BLOB(ctypes.Structure):
                _fields_ = [("cbData", ctypes.wintypes.DWORD),
                            ("pbData", ctypes.POINTER(ctypes.c_char))]

            input_blob = DATA_BLOB(len(data), ctypes.create_string_buffer(data, len(data)))
            output_blob = DATA_BLOB()
            if ctypes.windll.crypt32.CryptProtectData(
                ctypes.byref(input_blob), None, None, None, None, 0,
                ctypes.byref(output_blob)
            ):
                encrypted = ctypes.string_at(output_blob.pbData, output_blob.cbData)
                ctypes.windll.kernel32.LocalFree(output_blob.pbData)
                return "dpapi:" + base64.b64encode(encrypted).decode("ascii")
    except Exception:
        pass
    # Fallback: base64 obfuscation (not true encryption, but better than plaintext)
    return "b64:" + base64.b64encode(data).decode("ascii")


def _decrypt_token(stored: str) -> str:
    """Decrypt a token from at-rest storage."""
    if not stored:
        return ""
    if stored.startswith("dpapi:"):
        try:
            import ctypes
            import ctypes.wintypes

            class DATA_BLOB(ctypes.Structure):
                _fields_ = [("cbData", ctypes.wintypes.DWORD),
                            ("pbData", ctypes.POINTER(ctypes.c_char))]

            encrypted = base64.b64decode(stored[6:])
            input_blob = DATA_BLOB(len(encrypted),
                                   ctypes.create_string_buffer(encrypted, len(encrypted)))
            output_blob = DATA_BLOB()
            if ctypes.windll.crypt32.CryptUnprotectData(
                ctypes.byref(input_blob), None, None, None, None, 0,
                ctypes.byref(output_blob)
            ):
                plaintext = ctypes.string_at(output_blob.pbData, output_blob.cbData)
                ctypes.windll.kernel32.LocalFree(output_blob.pbData)
                return plaintext.decode("utf-8")
        except Exception:
            return ""
    elif stored.startswith("b64:"):
        try:
            return base64.b64decode(stored[4:]).decode("utf-8")
        except Exception:
            return ""
    # Legacy plaintext (from before encryption was added) — read as-is
    return stored


# ── Database ──────────────────────────────────────────────────────────────────

def _get_db() -> sqlite3.Connection:
    """Get a thread-local database connection."""
    conn = getattr(_local, "conn", None)
    if conn is None:
        os.makedirs(DB_DIR, exist_ok=True)
        # Restrict directory permissions (user-only on Unix)
        if sys.platform != "win32":
            os.chmod(DB_DIR, 0o700)
        conn = sqlite3.connect(DB_PATH, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        _local.conn = conn
    return conn


def init_db():
    """Create tables if they don't exist."""
    db = _get_db()
    db.executescript("""
        CREATE TABLE IF NOT EXISTS linked_accounts (
            service       TEXT PRIMARY KEY,
            access_token  TEXT DEFAULT '',
            refresh_token TEXT DEFAULT '',
            token_expiry  REAL DEFAULT 0,
            user_id       TEXT DEFAULT '',
            user_name     TEXT DEFAULT '',
            linked_at     REAL DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS track_mappings (
            source_service TEXT NOT NULL,
            source_id      TEXT NOT NULL,
            target_service TEXT NOT NULL,
            target_id      TEXT NOT NULL,
            confidence     REAL DEFAULT 0,
            match_method   TEXT DEFAULT '',
            created_at     REAL DEFAULT 0,
            PRIMARY KEY (source_service, source_id, target_service)
        );

        CREATE TABLE IF NOT EXISTS transfer_history (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            source_service  TEXT NOT NULL,
            target_service  TEXT NOT NULL,
            playlist_name   TEXT DEFAULT '',
            total           INTEGER DEFAULT 0,
            matched         INTEGER DEFAULT 0,
            added           INTEGER DEFAULT 0,
            failed          INTEGER DEFAULT 0,
            timestamp       REAL DEFAULT 0
        );
    """)
    # Migration: drop client_id/client_secret columns if they exist (old schema)
    try:
        cols = [r[1] for r in db.execute("PRAGMA table_info(linked_accounts)").fetchall()]
        if "client_id" in cols or "client_secret" in cols:
            # SQLite doesn't support DROP COLUMN before 3.35 — recreate table
            db.executescript("""
                CREATE TABLE IF NOT EXISTS _la_new (
                    service       TEXT PRIMARY KEY,
                    access_token  TEXT DEFAULT '',
                    refresh_token TEXT DEFAULT '',
                    token_expiry  REAL DEFAULT 0,
                    user_id       TEXT DEFAULT '',
                    user_name     TEXT DEFAULT '',
                    linked_at     REAL DEFAULT 0
                );
                INSERT OR IGNORE INTO _la_new (service, access_token, refresh_token,
                    token_expiry, user_id, user_name, linked_at)
                SELECT service, access_token, refresh_token,
                    token_expiry, user_id, user_name, linked_at
                FROM linked_accounts;
                DROP TABLE linked_accounts;
                ALTER TABLE _la_new RENAME TO linked_accounts;
            """)
    except Exception:
        pass
    db.commit()


# ── Linked accounts ──────────────────────────────────────────────────────────

def save_account(service: str, tokens: dict):
    """Save or update a linked account. Tokens are encrypted at rest.

    NOTE: client_id and client_secret are NOT stored — load from settings only.
    """
    db = _get_db()
    db.execute("""
        INSERT INTO linked_accounts
            (service, access_token, refresh_token,
             token_expiry, user_id, user_name, linked_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(service) DO UPDATE SET
            access_token  = excluded.access_token,
            refresh_token = excluded.refresh_token,
            token_expiry  = excluded.token_expiry,
            user_id       = excluded.user_id,
            user_name     = excluded.user_name,
            linked_at     = excluded.linked_at
    """, (
        service,
        _encrypt_token(tokens.get("access_token", "")),
        _encrypt_token(tokens.get("refresh_token", "")),
        tokens.get("token_expiry", 0),
        tokens.get("user_id", ""),
        tokens.get("user_name", ""),
        time.time(),
    ))
    db.commit()


def load_account(service: str) -> dict | None:
    """Load a linked account. Tokens are decrypted from at-rest encryption."""
    db = _get_db()
    row = db.execute("SELECT * FROM linked_accounts WHERE service = ?", (service,)).fetchone()
    if row is None:
        return None
    d = dict(row)
    d["access_token"] = _decrypt_token(d.get("access_token", ""))
    d["refresh_token"] = _decrypt_token(d.get("refresh_token", ""))
    return d


def remove_account(service: str):
    """Remove a linked account."""
    db = _get_db()
    db.execute("DELETE FROM linked_accounts WHERE service = ?", (service,))
    db.commit()


def list_linked_accounts() -> list[dict]:
    """List all linked accounts (tokens decrypted)."""
    db = _get_db()
    rows = db.execute("SELECT * FROM linked_accounts ORDER BY service").fetchall()
    out = []
    for r in rows:
        d = dict(r)
        d["access_token"] = _decrypt_token(d.get("access_token", ""))
        d["refresh_token"] = _decrypt_token(d.get("refresh_token", ""))
        out.append(d)
    return out


# ── Track mappings ───────────────────────────────────────────────────────────

def cache_track_mapping(source_service: str, source_id: str,
                        target_service: str, target_id: str,
                        confidence: float, match_method: str):
    """Cache a successful track mapping for reuse."""
    db = _get_db()
    db.execute("""
        INSERT INTO track_mappings
            (source_service, source_id, target_service, target_id,
             confidence, match_method, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(source_service, source_id, target_service) DO UPDATE SET
            target_id    = excluded.target_id,
            confidence   = excluded.confidence,
            match_method = excluded.match_method,
            created_at   = excluded.created_at
    """, (source_service, source_id, target_service, target_id,
          confidence, match_method, time.time()))
    db.commit()


def lookup_track_mapping(source_service: str, source_id: str,
                         target_service: str) -> dict | None:
    """Look up a cached track mapping."""
    db = _get_db()
    row = db.execute("""
        SELECT * FROM track_mappings
        WHERE source_service = ? AND source_id = ? AND target_service = ?
    """, (source_service, source_id, target_service)).fetchone()
    return dict(row) if row else None


# ── Transfer history ─────────────────────────────────────────────────────────

def save_transfer(source_service: str, target_service: str, playlist_name: str,
                  total: int, matched: int, added: int, failed: int) -> int:
    """Save a transfer record. Returns row ID."""
    db = _get_db()
    cur = db.execute("""
        INSERT INTO transfer_history
            (source_service, target_service, playlist_name,
             total, matched, added, failed, timestamp)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (source_service, target_service, playlist_name,
          total, matched, added, failed, time.time()))
    db.commit()
    return cur.lastrowid


def get_transfer_history(limit: int = 50) -> list[dict]:
    """Get recent transfer history."""
    db = _get_db()
    rows = db.execute(
        "SELECT * FROM transfer_history ORDER BY timestamp DESC LIMIT ?",
        (limit,)
    ).fetchall()
    return [dict(r) for r in rows]
