"""Phase-gate item operations — the one write path for ticking, dating, and filling a gate item.

This used to live inside the delivery router, which meant the seed's onboarded-launch demo had to
import a route handler to tick items "through the same code path an operator uses". The intent was
right — one write path — but the layering was backwards: the router is the HTTP wrapper, and the
behavior (the tick, the date push, the §1e field fill, and the auto-pass when the last item
completes) is domain. Both the router and the seed now call down into this module.
"""
from __future__ import annotations

import sqlite3

from fastapi import HTTPException

from . import audit, repo
from .db import now_utc


def patch_item(conn: sqlite3.Connection, item_id: str, *, complete: bool | None = None,
               due_date: str | None = None, fill_value: str | None = None) -> dict:
    """Complete a gate item, push its date, or record the answer it was asking for.

    The merged launch standard (migration 0051) moved the operational half of the launch checklist
    onto phase gates, which brought two behaviours with it that `toggle` had no room for:

    * **Pushing the date.** The queue tells an operator to "do it, mark it done, or push the date",
      and a gate item now carries a date to push. Without this the third option was not real.
    * **Filling the field it asks about (PHASE-3-SPEC.md §1e).** "Confirm the success definition"
      exists to put an answer in `program.success_criteria`; a tick that left the field empty would
      record that the conversation happened and lose what it produced.

    `fills_field` still never writes on its own — nothing infers a value from a completion. The
    operator supplies `fill_value` and this patches exactly the one field the template named.

    Returns ``{"gate_id", "filled_field"}``; the router composes the HTTP response shape.
    """
    row = conn.execute(
        "SELECT gi.*, g.program_id, p.account_id FROM phase_gate_items gi "
        "JOIN phase_gates g ON g.id = gi.gate_id JOIN programs p ON p.id = g.program_id "
        "WHERE gi.id=?", (item_id,)).fetchone()
    if not row:
        raise HTTPException(404, "gate item not found")

    ts = now_utc()
    sets, params = [], []
    if complete is not None:
        sets += ["complete=?", "completed_on=?"]
        params += [1 if complete else 0, ts[:10] if complete else None]
    if due_date is not None:
        sets.append("due_date=?")
        params.append(due_date)
    if sets:
        with conn:
            conn.execute(f"UPDATE phase_gate_items SET {', '.join(sets)}, updated_at=? WHERE id=?",
                         (*params, ts, item_id))

    filled = None
    if fill_value and row["fills_field"]:
        target, _, field = row["fills_field"].partition(".")
        if target == "account":
            repo.patch(conn, "accounts", row["account_id"], {field: fill_value},
                       object_type="account")
            filled = row["fills_field"]
        elif target == "program":
            repo.patch(conn, "programs", row["program_id"], {field: fill_value},
                       object_type="program")
            filled = row["fills_field"]

    if complete:
        maybe_autopass(conn, row["gate_id"])
    return {"gate_id": row["gate_id"], "filled_field": filled}


def maybe_autopass(conn: sqlite3.Connection, gate_id: str) -> None:
    gate = repo.get_row(conn, "phase_gates", gate_id)
    if gate["status"] != "open":
        return
    items = conn.execute("SELECT complete FROM phase_gate_items WHERE gate_id=?", (gate_id,)).fetchall()
    if items and all(i["complete"] for i in items):
        with conn:
            conn.execute("UPDATE phase_gates SET status='passed', passed_on=?, updated_at=? WHERE id=?",
                         (now_utc()[:10], now_utc(), gate_id))
            audit.record(conn, object_type="phase_gate", object_id=gate_id, action="close",
                         before=gate, after=repo.get_row(conn, "phase_gates", gate_id))


def gate_with_items(conn: sqlite3.Connection, gate_id: str) -> dict:
    gate = repo.get_row(conn, "phase_gates", gate_id)
    gate["items"] = [repo.row_to_dict(r) for r in
                     conn.execute("SELECT * FROM phase_gate_items WHERE gate_id=? ORDER BY created_at", (gate_id,))]
    return gate
