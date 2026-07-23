"""Portfolio attention queue (Module A) — v0.3.

Rules-based and explainable, never an opaque score. Every item carries a `because`,
an age, an optional due date, and a next action. Items are DERIVED each call; only
snooze/resolve is persisted in attention_state (the overlay), which can suppress an
item until a return date passes or the underlying facts materially change.

v0.3 ships the 6 triggers whose source objects exist (attention-rules.md). Renewal
windows (v1), stale imports (v2), and fired plays (v4) are intentionally absent.
"""
from __future__ import annotations

import sqlite3
from datetime import date

from fastapi import HTTPException

from . import audit, repo
from .db import new_id, now_utc

SENIOR_ROLES = ("champion", "budget_owner", "program_owner")
STALE_DAYS = 21  # matches the morning-check scenario ("untouched for three weeks")

# priority band per trigger (1 = highest)
PRIORITY = {
    "overdue_commitment": 1,
    "active_blocker": 2,
    "at_risk_milestone": 3,
    "untriaged_inbox": 4,
    "stale_stakeholder": 5,
    "open_task": 6,
}


def _today() -> str:
    return now_utc()[:10]


def _days_since(iso_date: str | None, today: str) -> int:
    if not iso_date:
        return 0
    try:
        return max(0, (date.fromisoformat(today) - date.fromisoformat(iso_date[:10])).days)
    except ValueError:
        return 0


def _latest_overlays(conn: sqlite3.Connection) -> dict[str, dict]:
    """Most recent attention_state row per item_key."""
    rows = conn.execute(
        "SELECT * FROM attention_state ORDER BY created_at ASC"
    ).fetchall()
    latest: dict[str, dict] = {}
    for r in rows:
        latest[r["item_key"]] = dict(r)  # later rows overwrite earlier -> newest wins
    return latest


def _suppressed(overlay: dict | None, underlying_updated_at: str, today: str) -> str | None:
    """Return 'snoozed' / 'resolved' if the item is currently suppressed, else None.

    A snoozed item resurfaces when its return date passes OR the underlying object
    changed after the overlay was set. A resolved item resurfaces only on underlying change.
    """
    if not overlay:
        return None
    changed_since = underlying_updated_at and underlying_updated_at > overlay["created_at"]
    if overlay["state"] == "snoozed":
        if overlay.get("snooze_until") and overlay["snooze_until"] <= today:
            return None
        if changed_since:
            return None
        return "snoozed"
    if overlay["state"] == "resolved":
        if changed_since:
            return None
        return "resolved"
    return None


def _candidates(conn: sqlite3.Connection, today: str) -> list[dict]:
    items: list[dict] = []

    def prog_ctx():
        return (
            "SELECT p.id pid, p.name pname, a.id aid, a.name aname "
            "FROM programs p JOIN accounts a ON a.id = p.account_id"
        )

    progs = {r["pid"]: dict(r) for r in conn.execute(prog_ctx()).fetchall()}

    # 1. Overdue commitments (any open commitment past due; none may be hidden)
    for r in conn.execute(
        "SELECT * FROM commitments WHERE archived=0 AND status='open' AND due_date < ?", (today,)
    ):
        p = progs.get(r["program_id"], {})
        overdue = _days_since(r["due_date"], today)
        items.append(_item(
            "overdue_commitment", "commitment", r["id"], r["updated_at"], p,
            title=r["description"],
            because=f"Overdue {overdue}d — commitment due {r['due_date']}.",
            age_days=overdue, due_date=r["due_date"], next_action="Close, chase, or renegotiate the due date.",
        ))

    # 2. Active blockers (risks or issues flagged is_blocker, still open)
    for r in conn.execute("SELECT * FROM risks WHERE archived=0 AND status='open' AND is_blocker=1"):
        p = progs.get(r["program_id"], {})
        items.append(_item(
            "active_blocker", "risk", r["id"], r["updated_at"], p,
            title=r["description"],
            because=f"Active blocker (risk) — raised {r['created_at'][:10]}.",
            age_days=_days_since(r["created_at"], today), due_date=None,
            next_action="Drive to closure or escalate.",
        ))
    for r in conn.execute("SELECT * FROM issues WHERE archived=0 AND status='open' AND is_blocker=1"):
        p = progs.get(r["program_id"], {})
        items.append(_item(
            "active_blocker", "issue", r["id"], r["updated_at"], p,
            title=r["description"],
            because=f"Active blocker (issue) — raised {r['created_at'][:10]}.",
            age_days=_days_since(r["created_at"], today), due_date=None,
            next_action="Drive to closure or escalate.",
        ))

    # 3. At-risk upcoming milestones (flagged, or past target and incomplete)
    for r in conn.execute("SELECT * FROM milestones WHERE archived=0 AND status='upcoming'"):
        past = bool(r["target_date"]) and r["target_date"] < today
        if not (r["at_risk"] or past):
            continue
        p = progs.get(r["program_id"], {})
        why = "past target date" if past else "flagged at risk"
        items.append(_item(
            "at_risk_milestone", "milestone", r["id"], r["updated_at"], p,
            title=r["name"],
            because=f"Milestone at risk — {why} (target {r['target_date'] or 'unset'}).",
            age_days=_days_since(r["target_date"], today) if past else 0, due_date=r["target_date"],
            next_action="Recover, re-baseline, or complete.",
        ))

    # 4. Untriaged inbox items
    for r in conn.execute("SELECT * FROM capture_inbox_items WHERE archived=0 AND status='untriaged'"):
        inter = conn.execute("SELECT account_id, program_id FROM interactions WHERE id=?", (r["interaction_id"],)).fetchone()
        p = progs.get(inter["program_id"], {}) if inter and inter["program_id"] else {}
        if not p and inter:
            a = conn.execute("SELECT id aid, name aname FROM accounts WHERE id=?", (inter["account_id"],)).fetchone()
            p = {"aid": a["aid"], "aname": a["aname"], "pname": None} if a else {}
        age = _days_since(r["created_at"], today)
        items.append(_item(
            "untriaged_inbox", "capture_inbox_item", r["id"], r["updated_at"], p,
            title=r["raw_text"],
            because=f"Untriaged note, {age}d old" + (" — aging" if age >= 3 else "") + ".",
            age_days=age, due_date=None, next_action="Convert or dismiss.",
        ))

    # 5. Stale stakeholder relationships (senior roles, no meaningful touch in STALE_DAYS)
    for r in conn.execute(
        "SELECT sr.*, pr.account_id acct FROM stakeholder_roles sr "
        "JOIN programs pr ON pr.id = sr.program_id "
        "WHERE sr.archived=0 AND sr.role IN (%s)" % ",".join("?" * len(SENIOR_ROLES)),
        SENIOR_ROLES,
    ):
        last = conn.execute(
            "SELECT MAX(i.occurred_on) m FROM interaction_participants ip "
            "JOIN interactions i ON i.id = ip.interaction_id "
            "WHERE ip.person_id = ? AND i.meaningful_touch = 1 AND i.archived = 0",
            (r["person_id"],),
        ).fetchone()["m"]
        baseline = last or r["created_at"][:10]
        days = _days_since(baseline, today)
        if days <= STALE_DAYS:
            continue
        p = progs.get(r["program_id"], {})
        person = conn.execute("SELECT name FROM persons WHERE id=?", (r["person_id"],)).fetchone()
        items.append(_item(
            "stale_stakeholder", "stakeholder_role", r["id"], r["updated_at"], p,
            title=f"{person['name'] if person else 'stakeholder'} ({r['role']})",
            because=f"No meaningful touch in {days}d.",
            age_days=days, due_date=None, next_action="Reach out or schedule.",
        ))

    # 6. Open tasks (overdue ones sort to the top of this band)
    for r in conn.execute("SELECT * FROM tasks WHERE archived=0 AND status='open'"):
        p = progs.get(r["program_id"], {})
        overdue = bool(r["due_date"]) and r["due_date"] < today
        age = _days_since(r["due_date"], today) if overdue else _days_since(r["created_at"], today)
        items.append(_item(
            "open_task", "task", r["id"], r["updated_at"], p,
            title=r["description"],
            because=("Overdue task — due " + r["due_date"] + ".") if overdue else "Open task.",
            age_days=age, due_date=r["due_date"], next_action="Do, reassign, or close.",
        ))

    return items


def _item(trigger, object_type, object_id, updated_at, p, *, title, because, age_days, due_date, next_action):
    return {
        "key": f"{trigger}:{object_type}:{object_id}",
        "trigger_type": trigger,
        "priority": PRIORITY[trigger],
        "object_type": object_type,
        "object_id": object_id,
        "_updated_at": updated_at,
        "account_id": p.get("aid"),
        "account_name": p.get("aname"),
        "program_id": p.get("pid"),
        "program_name": p.get("pname"),
        "title": title,
        "because": because,
        "age_days": age_days,
        "due_date": due_date,
        "next_action": next_action,
    }


def build_queue(conn: sqlite3.Connection) -> dict:
    today = _today()
    overlays = _latest_overlays(conn)
    active, snoozed = [], []
    for it in _candidates(conn, today):
        state = _suppressed(overlays.get(it["key"]), it["_updated_at"], today)
        it.pop("_updated_at", None)
        if state is None:
            active.append(it)
        elif state == "snoozed":
            ov = overlays[it["key"]]
            it["snooze_until"] = ov.get("snooze_until")
            it["resurface_condition"] = ov.get("resurface_condition")
            snoozed.append(it)
        # resolved items are omitted entirely (still trackable via audit/overlay)
    active.sort(key=lambda x: (x["priority"], -x["age_days"]))
    return {"as_of": today, "items": active, "snoozed": snoozed, "snoozed_count": len(snoozed)}


# --- overlay mutations ---

def _object_table(object_type: str) -> str:
    return {
        "commitment": "commitments", "risk": "risks", "issue": "issues",
        "milestone": "milestones", "task": "tasks", "capture_inbox_item": "capture_inbox_items",
        "stakeholder_role": "stakeholder_roles",
    }[object_type]


def _validate_key(conn: sqlite3.Connection, item_key: str) -> None:
    try:
        _trigger, object_type, object_id = item_key.split(":", 2)
        table = _object_table(object_type)
    except (ValueError, KeyError):
        raise HTTPException(422, f"malformed item_key: {item_key}")
    if not conn.execute(f"SELECT 1 FROM {table} WHERE id=?", (object_id,)).fetchone():
        raise HTTPException(404, f"queue item target not found: {item_key}")


def snooze(conn, *, item_key, snooze_until=None, resurface_condition=None) -> dict:
    if not snooze_until and not resurface_condition:
        raise HTTPException(422, "Snoozing requires a return date or a resurfacing condition.")
    _validate_key(conn, item_key)
    row = {
        "id": new_id(), "item_key": item_key, "state": "snoozed",
        "snooze_until": snooze_until, "resurface_condition": resurface_condition,
        "created_at": now_utc(), "created_by": audit.DEFAULT_ACTOR,
    }
    with conn:
        conn.execute(
            "INSERT INTO attention_state (id,item_key,state,snooze_until,resurface_condition,created_at,created_by) "
            "VALUES (:id,:item_key,:state,:snooze_until,:resurface_condition,:created_at,:created_by)", row,
        )
        audit.record(conn, object_type="attention_state", object_id=row["id"], action="create", after=row)
    return row


def resolve(conn, *, item_key, successor_action_type, successor_action_id) -> dict:
    if not successor_action_id:
        raise HTTPException(422, "Resolving requires a linked successor action (a task or commitment).")
    _validate_key(conn, item_key)
    table = "tasks" if successor_action_type == "task" else "commitments"
    if not conn.execute(f"SELECT 1 FROM {table} WHERE id=?", (successor_action_id,)).fetchone():
        raise HTTPException(404, f"successor {successor_action_type} not found")
    row = {
        "id": new_id(), "item_key": item_key, "state": "resolved",
        "successor_action_type": successor_action_type, "successor_action_id": successor_action_id,
        "created_at": now_utc(), "created_by": audit.DEFAULT_ACTOR,
    }
    with conn:
        conn.execute(
            "INSERT INTO attention_state (id,item_key,state,successor_action_type,successor_action_id,created_at,created_by) "
            "VALUES (:id,:item_key,:state,:successor_action_type,:successor_action_id,:created_at,:created_by)", row,
        )
        audit.record(conn, object_type="attention_state", object_id=row["id"], action="create", after=row)
    return row
