"""Tiny data-access helpers shared by routers. No ORM — explicit SQL, audited writes."""
from __future__ import annotations

import sqlite3
from typing import Any

from fastapi import HTTPException

from . import audit
from .db import new_id, now_utc


def row_to_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
    if row is None:
        return None
    d = dict(row)
    # Surface SQLite integer booleans as real bools for the API.
    for k in ("archived", "meaningful_touch"):
        if k in d and d[k] is not None:
            d[k] = bool(d[k])
    return d


def get_row(conn: sqlite3.Connection, table: str, id_: str) -> dict[str, Any]:
    row = conn.execute(f"SELECT * FROM {table} WHERE id = ?", (id_,)).fetchone()
    d = row_to_dict(row)
    if d is None or d.get("archived"):
        raise HTTPException(status_code=404, detail=f"{table[:-1]} not found: {id_}")
    return d


def insert(
    conn: sqlite3.Connection, table: str, values: dict[str, Any], *, object_type: str
) -> dict[str, Any]:
    """Insert with generated id + timestamps, write a 'create' audit event, return the row."""
    ts = now_utc()
    row = {"id": new_id(), "created_at": ts, "updated_at": ts, **values}
    cols = ", ".join(row.keys())
    placeholders = ", ".join("?" for _ in row)
    with conn:
        conn.execute(
            f"INSERT INTO {table} ({cols}) VALUES ({placeholders})", tuple(row.values())
        )
        audit.record(conn, object_type=object_type, object_id=row["id"], action="create", after=row)
    return get_row(conn, table, row["id"])


def patch(
    conn: sqlite3.Connection, table: str, id_: str, changes: dict[str, Any], *, object_type: str
) -> dict[str, Any]:
    """Apply a partial update (only non-None fields), audited with before/after."""
    before = get_row(conn, table, id_)
    changes = {k: v for k, v in changes.items() if v is not None}
    if not changes:
        return before
    changes["updated_at"] = now_utc()
    sets = ", ".join(f"{k} = ?" for k in changes)
    with conn:
        conn.execute(f"UPDATE {table} SET {sets} WHERE id = ?", (*changes.values(), id_))
        after = get_row(conn, table, id_)
        audit.record(
            conn, object_type=object_type, object_id=id_, action="update",
            before=before, after=after,
        )
    return after


def archive(conn: sqlite3.Connection, table: str, id_: str, *, object_type: str) -> None:
    before = get_row(conn, table, id_)
    ts = now_utc()
    with conn:
        conn.execute(
            f"UPDATE {table} SET archived = 1, archived_at = ?, archived_by = ?, updated_at = ? WHERE id = ?",
            (ts, audit.DEFAULT_ACTOR, ts, id_),
        )
        audit.record(conn, object_type=object_type, object_id=id_, action="archive", before=before)


def list_rows(conn: sqlite3.Connection, table: str, where: str = "", params: tuple = ()) -> list[dict]:
    clause = "WHERE archived = 0" + (f" AND {where}" if where else "")
    rows = conn.execute(f"SELECT * FROM {table} {clause}", params).fetchall()
    return [row_to_dict(r) for r in rows]
