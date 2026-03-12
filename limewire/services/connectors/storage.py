"""SQLite persistence for linked accounts, track mappings, and transfer history."""

from __future__ import annotations

import os
import sqlite3
import time
import threading

DB_DIR = os.path.join(os.path.expanduser("~"), ".limewire")
DB_PATH = os.path.join(DB_DIR, "connectors.db")

_local = threading.local()


def _get_db() -> sqlite3.Connection:
    """Get a thread-local database connection."""
    conn = getattr(_local, "conn", None)
    if conn is None:
        os.makedirs(DB_DIR, exist_ok=True)
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
            client_id     TEXT DEFAULT '',
            client_secret TEXT DEFAULT '',
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
    db.commit()


# ── Linked accounts ──────────────────────────────────────────────────────────

def save_account(service: str, tokens: dict):
    """Save or update a linked account."""
    db = _get_db()
    db.execute("""
        INSERT INTO linked_accounts
            (service, access_token, refresh_token, client_id, client_secret,
             token_expiry, user_id, user_name, linked_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(service) DO UPDATE SET
            access_token  = excluded.access_token,
            refresh_token = excluded.refresh_token,
            client_id     = excluded.client_id,
            client_secret = excluded.client_secret,
            token_expiry  = excluded.token_expiry,
            user_id       = excluded.user_id,
            user_name     = excluded.user_name,
            linked_at     = excluded.linked_at
    """, (
        service,
        tokens.get("access_token", ""),
        tokens.get("refresh_token", ""),
        tokens.get("client_id", ""),
        tokens.get("client_secret", ""),
        tokens.get("token_expiry", 0),
        tokens.get("user_id", ""),
        tokens.get("user_name", ""),
        time.time(),
    ))
    db.commit()


def load_account(service: str) -> dict | None:
    """Load a linked account. Returns dict or None."""
    db = _get_db()
    row = db.execute("SELECT * FROM linked_accounts WHERE service = ?", (service,)).fetchone()
    if row is None:
        return None
    return dict(row)


def remove_account(service: str):
    """Remove a linked account."""
    db = _get_db()
    db.execute("DELETE FROM linked_accounts WHERE service = ?", (service,))
    db.commit()


def list_linked_accounts() -> list[dict]:
    """List all linked accounts."""
    db = _get_db()
    rows = db.execute("SELECT * FROM linked_accounts ORDER BY service").fetchall()
    return [dict(r) for r in rows]


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
