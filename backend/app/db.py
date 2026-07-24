"""SQLite connection + versioned migration runner.

Boring on purpose: raw sqlite3, numbered .sql files, one schema_migrations table.
Every schema change is a new migration file; no manual DB surgery (CLAUDE.md).
"""
from __future__ import annotations

import os
import re
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
MIGRATIONS_DIR = BACKEND_DIR / "migrations"
DEFAULT_DB = BACKEND_DIR / "data" / "valence_os.sqlite"

MIGRATION_RE = re.compile(r"^(\d{4})_.*\.sql$")


def db_path() -> Path:
    return Path(os.environ.get("VALENCE_OS_DB", str(DEFAULT_DB)))


def connect() -> sqlite3.Connection:
    path = db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


def now_utc() -> str:
    """ISO-8601 UTC timestamp, seconds precision."""
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def new_id() -> str:
    return uuid.uuid4().hex


def _applied_versions(conn: sqlite3.Connection) -> set[int]:
    conn.execute(
        "CREATE TABLE IF NOT EXISTS schema_migrations "
        "(version INTEGER PRIMARY KEY, name TEXT NOT NULL, applied_at TEXT NOT NULL)"
    )
    rows = conn.execute("SELECT version FROM schema_migrations").fetchall()
    return {r["version"] for r in rows}


def discover_migrations() -> list[tuple[int, Path]]:
    found: list[tuple[int, Path]] = []
    for p in sorted(MIGRATIONS_DIR.glob("*.sql")):
        m = MIGRATION_RE.match(p.name)
        if not m:
            continue
        found.append((int(m.group(1)), p))
    found.sort(key=lambda t: t[0])
    return found


def run_migrations(conn: sqlite3.Connection) -> list[int]:
    """Apply every migration whose version is not yet recorded. Returns applied versions."""
    applied = _applied_versions(conn)
    newly: list[int] = []
    for version, path in discover_migrations():
        if version in applied:
            continue
        sql = path.read_text(encoding="utf-8")
        with conn:  # transaction per migration
            conn.executescript(sql)
            conn.execute(
                "INSERT INTO schema_migrations (version, name, applied_at) VALUES (?,?,?)",
                (version, path.name, now_utc()),
            )
        newly.append(version)
    return newly
