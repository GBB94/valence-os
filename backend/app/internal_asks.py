"""Internal ask and escalation state machines. No outbound side effects exist here."""
from __future__ import annotations

import json
import sqlite3

from fastapi import HTTPException

from . import audit, repo
from .db import new_id, now_utc
from .internal_forecast import operator
from .queue import _business_hours_between

TRANSITIONS = {
    "raised": {"acknowledged", "in_progress", "delivered", "declined"},
    "acknowledged": {"in_progress", "delivered", "declined"},
    "in_progress": {"delivered", "declined"},
    "delivered": {"raised"},
    "declined": {"raised"},
}


def create_ask(conn: sqlite3.Connection, account_id: str, values: dict) -> dict:
    repo.get_row(conn, "accounts", account_id)
    data = {"account_id": account_id, **values, "status": "raised"}
    try:
        row = repo.insert(conn, "internal_asks", data, object_type="internal_ask")
    except sqlite3.IntegrityError as exc:
        raise HTTPException(422, str(exc)) from exc
    with conn:
        _event(conn, row["id"], "created", None, "raised", "Ask raised")
    return get_ask(conn, row["id"])


def _event(conn: sqlite3.Connection, ask_id: str, event_type: str, before: str | None,
           after: str | None, reason: str | None) -> None:
    ts = now_utc()
    conn.execute("INSERT INTO internal_ask_events(id,ask_id,event_type,status_before,status_after,reason,actor,occurred_at,created_at) VALUES (?,?,?,?,?,?,?,?,?)",
                 (new_id(), ask_id, event_type, before, after, reason, operator(conn), ts, ts))


def get_ask(conn: sqlite3.Connection, ask_id: str) -> dict:
    row = repo.get_row(conn, "internal_asks", ask_id)
    events = [repo.row_to_dict(r) for r in conn.execute("SELECT * FROM internal_ask_events WHERE ask_id=? ORDER BY occurred_at,created_at", (ask_id,))]
    escalations = [get_escalation(conn, r["id"]) for r in conn.execute("SELECT id FROM escalation_instances WHERE ask_id=? AND archived=0 ORDER BY opened_at", (ask_id,))]
    inherited_category = None
    if row.get("forecast_entry_id"):
        linked = conn.execute("SELECT category FROM forecast_entries WHERE id=? AND archived=0", (row["forecast_entry_id"],)).fetchone()
        inherited_category = linked["category"] if linked else None
    return {**row, "events": events, "escalations": escalations,
            "inherited_forecast_category": inherited_category,
            "commit_urgent": inherited_category == "commit"}


def list_asks(conn: sqlite3.Connection, account_id: str) -> list[dict]:
    repo.get_row(conn, "accounts", account_id)
    ids = [r["id"] for r in conn.execute("SELECT id FROM internal_asks WHERE account_id=? AND archived=0 ORDER BY needed_by,created_at", (account_id,))]
    return [get_ask(conn, ask_id) for ask_id in ids]


def transition(conn: sqlite3.Connection, ask_id: str, values: dict) -> dict:
    before = repo.get_row(conn, "internal_asks", ask_id)
    after = values["status"]
    if after not in TRANSITIONS[before["status"]]:
        raise HTTPException(409, f"cannot move ask from {before['status']} to {after}")
    reason = values.get("reason")
    if before["status"] in ("delivered", "declined") and after == "raised" and not reason:
        raise HTTPException(422, "reopening an ask requires a reason")
    if after == "declined" and not reason:
        raise HTTPException(422, "declining an ask requires a reason")
    if after == "delivered" and not (values.get("completion_note") or values.get("result_source_reference_id")):
        raise HTTPException(422, "delivery requires a completion note or artifact source")
    ts = now_utc(); event_type = {"acknowledged": "acknowledged", "in_progress": "started",
        "delivered": "delivered", "declined": "declined", "raised": "reopened"}[after]
    updates = {"status": after, "updated_at": ts}
    if after == "declined": updates["decline_reason"] = reason
    if after == "delivered": updates.update({"delivered_on": values.get("delivered_on") or ts[:10],
        "delivered_by": operator(conn), "completion_note": values.get("completion_note"),
        "result_source_reference_id": values.get("result_source_reference_id")})
    if after == "raised": updates.update({"decline_reason": None, "delivered_on": None, "delivered_by": None, "completion_note": None})
    with conn:
        conn.execute(f"UPDATE internal_asks SET {','.join(f'{k}=?' for k in updates)} WHERE id=?", (*updates.values(), ask_id))
        _event(conn, ask_id, event_type, before["status"], after, reason)
        audit.record(conn, object_type="internal_ask", object_id=ask_id, action="update",
                     before=before, after=repo.get_row(conn, "internal_asks", ask_id))
    return get_ask(conn, ask_id)


def _default(conn: sqlite3.Connection, ask_type: str, severity: str, default_id: str | None) -> dict:
    if default_id:
        selected = repo.get_row(conn, "escalation_defaults", default_id)
        if selected["severity"] != severity or selected["ask_type"] not in (ask_type, "general"):
            raise HTTPException(422, "selected escalation default does not match the ask type and severity")
        return selected
    row = conn.execute("SELECT * FROM escalation_defaults WHERE ask_type=? AND severity=? AND archived=0", (ask_type, severity)).fetchone()
    if not row:
        row = conn.execute("SELECT * FROM escalation_defaults WHERE ask_type='general' AND severity=? AND archived=0", (severity,)).fetchone()
    if not row:
        raise HTTPException(422, f"no {severity} escalation default is configured for {ask_type}")
    return repo.row_to_dict(row)


def open_escalation(conn: sqlite3.Connection, ask_id: str, severity: str, default_id: str | None = None) -> dict:
    ask = repo.get_row(conn, "internal_asks", ask_id)
    if ask["status"] in ("delivered", "declined"):
        raise HTTPException(409, "terminal asks cannot be escalated")
    default = _default(conn, ask["ask_type"], severity, default_id)
    ts = now_utc()
    values = {"ask_id": ask_id, "default_id": default["id"], "severity": severity,
              "path_type": default["path_type"], "threshold_business_hours": default["threshold_business_hours"],
              "destination_function_id": default.get("destination_function_id"), "destination_role": default.get("destination_role"),
              "expected_response_hours": default["expected_response_hours"], "next_step": default["next_step"],
              "opened_at": ts, "opened_by": operator(conn), "status": "open"}
    row = repo.insert(conn, "escalation_instances", values, object_type="escalation")
    add_escalation_event(conn, row["id"], {"event_type": "raised", "destination_function_id": row.get("destination_function_id"),
        "threshold_reason": f"Applied {row['threshold_business_hours']} internal business-hour threshold."})
    return get_escalation(conn, row["id"])


def add_escalation_event(conn: sqlite3.Connection, escalation_id: str, values: dict) -> dict:
    escalation = repo.get_row(conn, "escalation_instances", escalation_id)
    if escalation["status"] == "resolved":
        raise HTTPException(409, "escalation is already resolved")
    ts = now_utc(); row = {"id": new_id(), "escalation_id": escalation_id, **values,
                           "actor": operator(conn), "occurred_at": ts, "created_at": ts}
    with conn:
        conn.execute(f"INSERT INTO escalation_events ({','.join(row)}) VALUES ({','.join('?' for _ in row)})", tuple(row.values()))
        if values["event_type"] == "resolved":
            if not values.get("response"):
                raise HTTPException(422, "resolution requires the outcome")
            conn.execute("UPDATE escalation_instances SET status='resolved',resolved_at=?,resolution=?,updated_at=? WHERE id=?",
                         (ts, values["response"], ts, escalation_id))
    return repo.row_to_dict(conn.execute("SELECT * FROM escalation_events WHERE id=?", (row["id"],)).fetchone())


def get_escalation(conn: sqlite3.Connection, escalation_id: str) -> dict:
    row = repo.get_row(conn, "escalation_instances", escalation_id)
    events = [repo.row_to_dict(r) for r in conn.execute("SELECT * FROM escalation_events WHERE escalation_id=? ORDER BY occurred_at,created_at", (escalation_id,))]
    return {**row, "events": events, "suggested_note": suggested_note(conn, row),
            "elapsed_business_hours": elapsed_business_hours(conn, row["opened_at"], row.get("resolved_at") or now_utc())}


def elapsed_business_hours(conn: sqlite3.Connection, start: str, end: str) -> float:
    settings = conn.execute("SELECT * FROM internal_operations_settings WHERE id='singleton'").fetchone()
    return round(_business_hours_between(start, end, settings["business_timezone"],
                 settings["business_day_start_hour"], settings["business_day_end_hour"],
                 set(json.loads(settings["working_weekdays_json"]))), 2)


def suggested_note(conn: sqlite3.Connection, escalation: dict) -> str:
    ask = repo.get_row(conn, "internal_asks", escalation["ask_id"])
    return (f"Escalation: {ask['need']}. Needed by {ask['needed_by']}. "
            f"Current state: {ask['status']}. Requested action: {ask['success_condition']}. "
            f"Next step if unresolved: {escalation['next_step']}")
