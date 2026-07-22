"""Append-only audit log helper (CLAUDE.md: every material change logged)."""
from __future__ import annotations

import json
import sqlite3
from typing import Any

from .db import new_id, now_utc

# In v0 there is one operator; the actor id can be threaded through later.
DEFAULT_ACTOR = "p-val-operator"


def record(
    conn: sqlite3.Connection,
    *,
    object_type: str,
    object_id: str,
    action: str,
    before: dict[str, Any] | None = None,
    after: dict[str, Any] | None = None,
    actor_id: str | None = None,
) -> None:
    conn.execute(
        "INSERT INTO audit_events "
        "(id, occurred_at, actor_id, object_type, object_id, action, before, after, source) "
        "VALUES (?,?,?,?,?,?,?,?, 'user')",
        (
            new_id(),
            now_utc(),
            actor_id or DEFAULT_ACTOR,
            object_type,
            object_id,
            action,
            json.dumps(before) if before is not None else None,
            json.dumps(after) if after is not None else None,
        ),
    )
