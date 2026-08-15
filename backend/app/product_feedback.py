"""Portfolio feedback themes with sourced account occurrences and two touch loops."""
from __future__ import annotations

import sqlite3

from fastapi import HTTPException

from . import repo
from .db import new_id, now_utc
from .internal_forecast import operator


def create_item(conn: sqlite3.Connection, values: dict) -> dict:
    return repo.insert(conn, "product_feedback_items", values, object_type="product_feedback")


def list_items(conn: sqlite3.Connection, account_id: str | None = None) -> list[dict]:
    params: tuple = ()
    account_filter = ""
    if account_id:
        repo.get_row(conn, "accounts", account_id)
        account_filter = " AND EXISTS (SELECT 1 FROM product_feedback_occurrences ox WHERE ox.feedback_item_id=i.id AND ox.account_id=? AND ox.archived=0)"
        params = (account_id,)
    ids = [r["id"] for r in conn.execute("SELECT i.id FROM product_feedback_items i WHERE i.archived=0" + account_filter + " ORDER BY i.status,i.title", params)]
    return [get_item(conn, item_id) for item_id in ids]


def get_item(conn: sqlite3.Connection, item_id: str) -> dict:
    item = repo.get_row(conn, "product_feedback_items", item_id)
    occurrences = []
    for row in conn.execute("SELECT o.*,a.name account_name,p.name stakeholder_name FROM product_feedback_occurrences o JOIN accounts a ON a.id=o.account_id JOIN persons p ON p.id=o.stakeholder_person_id WHERE o.feedback_item_id=? AND o.archived=0 ORDER BY o.captured_on", (item_id,)):
        occurrence = repo.row_to_dict(row)
        touches = [repo.row_to_dict(t) for t in conn.execute("SELECT * FROM product_feedback_touches WHERE occurrence_id=? ORDER BY created_at", (occurrence["id"],))]
        occurrence["touches"] = touches
        occurrence["acknowledged"] = any(t["touch_type"] == "acknowledgment" for t in touches)
        occurrence["resolution_closed_loop"] = any(t["touch_type"] == "resolution" for t in touches)
        occurrences.append(occurrence)
    events = [repo.row_to_dict(r) for r in conn.execute("SELECT * FROM product_feedback_events WHERE feedback_item_id=? ORDER BY occurred_at,created_at", (item_id,))]
    return {**item, "occurrences": occurrences, "account_count": len({x["account_id"] for x in occurrences}), "events": events}


def add_occurrence(conn: sqlite3.Connection, item_id: str, values: dict) -> dict:
    repo.get_row(conn, "product_feedback_items", item_id)
    data = {"feedback_item_id": item_id, **values, "captured_by": operator(conn)}
    try:
        return repo.insert(conn, "product_feedback_occurrences", data, object_type="product_feedback_occurrence")
    except sqlite3.IntegrityError as exc:
        raise HTTPException(422, str(exc)) from exc


def transition(conn: sqlite3.Connection, item_id: str, values: dict) -> dict:
    item = repo.get_row(conn, "product_feedback_items", item_id); after = values["status"]
    if item["status"] == after:
        raise HTTPException(409, "feedback status is unchanged")
    if after == "declined" and not values.get("reason"):
        raise HTTPException(422, "declined feedback requires a reason")
    if after == "shipped" and not values.get("product_reference"):
        raise HTTPException(422, "shipped feedback requires a product reference or release note")
    ts = now_utc()
    with conn:
        conn.execute("UPDATE product_feedback_items SET status=?,status_rationale=?,product_reference=COALESCE(?,product_reference),updated_at=? WHERE id=?",
                     (after, values["reason"], values.get("product_reference"), ts, item_id))
        conn.execute("INSERT INTO product_feedback_events(id,feedback_item_id,event_type,value_before,value_after,reason,actor,occurred_at,created_at) VALUES (?,?,?,?,?,?,?,?,?)",
                     (new_id(), item_id, "status_changed", item["status"], after, values["reason"], operator(conn), ts, ts))
    return get_item(conn, item_id)


def record_touch(conn: sqlite3.Connection, occurrence_id: str, touch_type: str, interaction_id: str) -> dict:
    occurrence = repo.get_row(conn, "product_feedback_occurrences", occurrence_id)
    item = repo.get_row(conn, "product_feedback_items", occurrence["feedback_item_id"])
    if touch_type == "resolution" and item["status"] not in ("shipped", "declined"):
        raise HTTPException(409, "resolution touches require a shipped or declined theme")
    values = {"id": new_id(), "occurrence_id": occurrence_id, "touch_type": touch_type,
              "interaction_id": interaction_id, "recorded_by": operator(conn), "created_at": now_utc()}
    try:
        with conn:
            conn.execute(f"INSERT INTO product_feedback_touches ({','.join(values)}) VALUES ({','.join('?' for _ in values)})", tuple(values.values()))
    except sqlite3.IntegrityError as exc:
        raise HTTPException(422, str(exc)) from exc
    return repo.row_to_dict(conn.execute("SELECT * FROM product_feedback_touches WHERE id=?", (values["id"],)).fetchone())


def move_occurrence(conn: sqlite3.Connection, occurrence_id: str, item_id: str, reason: str) -> dict:
    occurrence = repo.get_row(conn, "product_feedback_occurrences", occurrence_id)
    repo.get_row(conn, "product_feedback_items", item_id)
    if occurrence["feedback_item_id"] == item_id:
        raise HTTPException(409, "occurrence is already on that theme")
    ts = now_utc()
    with conn:
        conn.execute("UPDATE product_feedback_occurrences SET feedback_item_id=?,updated_at=? WHERE id=?", (item_id, ts, occurrence_id))
        conn.execute("INSERT INTO product_feedback_events(id,feedback_item_id,occurrence_id,event_type,value_before,value_after,reason,actor,occurred_at,created_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
                     (new_id(), item_id, occurrence_id, "occurrence_moved", occurrence["feedback_item_id"], item_id, reason, operator(conn), ts, ts))
    return repo.get_row(conn, "product_feedback_occurrences", occurrence_id)
