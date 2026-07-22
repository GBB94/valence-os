"""Create + transition helpers for v0.2 execution objects.

Shared by the execution router and the inbox-convert endpoint so conversion
reuses exactly the same creation path (no divergent logic). Each helper assumes
it runs inside a transaction opened by the caller (`with conn:`), EXCEPT the
public create_* used standalone by the router, which manage their own via repo.
"""
from __future__ import annotations

import sqlite3

from fastapi import HTTPException

from . import audit, repo
from .db import now_utc

# Map target type -> (table, object_type, allowed payload columns)
EXEC_TABLES = {
    "task": "tasks",
    "commitment": "commitments",
    "decision": "decisions",
    "risk": "risks",
    "issue": "issues",
    "milestone": "milestones",
}


def _require_program(conn: sqlite3.Connection, program_id: str) -> dict:
    if not program_id:
        raise HTTPException(422, "program_id is required for execution objects")
    return repo.get_row(conn, "programs", program_id)


def create(conn: sqlite3.Connection, target: str, data: dict) -> dict:
    """Create an execution object from a plain dict of column values."""
    table = EXEC_TABLES[target]
    _require_program(conn, data.get("program_id"))
    values = dict(data)
    # normalize booleans -> ints for sqlite
    for b in ("is_blocker", "at_risk"):
        if b in values:
            values[b] = 1 if values[b] else 0
    # if superseding a decision, mark the old one superseded (in the same tx)
    supersedes_id = values.get("supersedes_id") if target == "decision" else None
    row = repo.insert(conn, table, values, object_type=target)
    if supersedes_id:
        old = repo.get_row(conn, "decisions", supersedes_id)
        with conn:
            conn.execute(
                "UPDATE decisions SET status='superseded', updated_at=? WHERE id=?",
                (now_utc(), supersedes_id),
            )
            after = repo.get_row(conn, "decisions", supersedes_id)
            audit.record(conn, object_type="decision", object_id=supersedes_id,
                         action="update", before=old, after=after)
    return row


def _close(conn, table, id_, object_type, changes: dict, guard_status: str) -> dict:
    before = repo.get_row(conn, table, id_)
    if before["status"] != guard_status:
        raise HTTPException(409, f"{object_type} is {before['status']}, expected {guard_status}")
    changes = {k: v for k, v in changes.items() if v is not None}
    changes["updated_at"] = now_utc()
    sets = ", ".join(f"{k} = ?" for k in changes)
    with conn:
        conn.execute(f"UPDATE {table} SET {sets} WHERE id = ?", (*changes.values(), id_))
        after = repo.get_row(conn, table, id_)
        audit.record(conn, object_type=object_type, object_id=id_, action="close",
                     before=before, after=after)
    return after


def close_commitment(conn, id_, *, acknowledged_by_id=None, closed_on=None, close_note=None) -> dict:
    # Closes only on receiving-party acknowledgement (Section 4).
    return _close(conn, "commitments", id_, "commitment", {
        "status": "closed",
        "acknowledged_by_id": acknowledged_by_id,
        "closed_on": closed_on or now_utc()[:10],
        "closed_by": audit.DEFAULT_ACTOR,
        "close_note": close_note,
    }, guard_status="open")


def close_task(conn, id_, *, status="done", closed_on=None, close_note=None) -> dict:
    return _close(conn, "tasks", id_, "task", {
        "status": status,
        "closed_on": closed_on or now_utc()[:10],
        "closed_by": audit.DEFAULT_ACTOR,
        "close_note": close_note,
    }, guard_status="open")


def close_risk(conn, id_, *, close_reason, closed_on=None, close_note=None) -> dict:
    # Mitigation is NOT closure; a risk closes only when no longer possible/relevant.
    return _close(conn, "risks", id_, "risk", {
        "status": "closed",
        "close_reason": close_reason,
        "closed_on": closed_on or now_utc()[:10],
        "closed_by": audit.DEFAULT_ACTOR,
        "close_note": close_note,
    }, guard_status="open")


def resolve_issue(conn, id_, *, resolution_type, resolved_on=None, resolution_note=None) -> dict:
    return _close(conn, "issues", id_, "issue", {
        "status": "resolved",
        "resolution_type": resolution_type,
        "resolved_on": resolved_on or now_utc()[:10],
        "resolved_by": audit.DEFAULT_ACTOR,
        "resolution_note": resolution_note,
    }, guard_status="open")


def complete_milestone(conn, id_, *, completed_on=None, completion_note=None) -> dict:
    return _close(conn, "milestones", id_, "milestone", {
        "status": "complete",
        "completed_on": completed_on or now_utc()[:10],
        "completed_by": audit.DEFAULT_ACTOR,
        "completion_note": completion_note,
    }, guard_status="upcoming")


def program_execution(conn: sqlite3.Connection, program_id: str) -> dict:
    """All execution objects for a program, with derived overdue/at-risk flags."""
    today = now_utc()[:10]
    out = {}
    for target, table in EXEC_TABLES.items():
        rows = repo.list_rows(conn, table, where="program_id = ? ORDER BY created_at DESC",
                              params=(program_id,))
        for r in rows:
            if table == "commitments":
                r["overdue"] = r["status"] == "open" and (r.get("due_date") or "9999") < today
            if table == "tasks":
                r["overdue"] = r["status"] == "open" and bool(r.get("due_date")) and r["due_date"] < today
            if table == "milestones":
                r["derived_at_risk"] = r["status"] == "upcoming" and (
                    bool(r.get("at_risk")) or (bool(r.get("target_date")) and r["target_date"] < today)
                )
        out[table] = rows
    return out
