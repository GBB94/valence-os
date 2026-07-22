import sqlite3

from fastapi import APIRouter, Depends, HTTPException

from .. import audit, execution_ops, repo
from ..db import now_utc
from ..deps import get_conn
from ..schemas import InboxConvert

router = APIRouter(prefix="/api/inbox", tags=["inbox"])


@router.get("")
def list_inbox(status: str = "untriaged", conn: sqlite3.Connection = Depends(get_conn)):
    """Untriaged items feed the attention queue (v0.3). Conversion to execution objects is v0.2."""
    items = repo.list_rows(
        conn, "capture_inbox_items",
        where="status = ? ORDER BY created_at ASC", params=(status,),
    )
    # Attach a little context: which interaction/account each came from.
    for it in items:
        inter = conn.execute(
            "SELECT id, account_id, program_id, occurred_on, summary FROM interactions WHERE id = ?",
            (it["interaction_id"],),
        ).fetchone()
        it["interaction"] = repo.row_to_dict(inter)
    return items


@router.post("/{item_id}/convert")
def convert_item(item_id: str, body: InboxConvert, conn: sqlite3.Connection = Depends(get_conn)):
    """Convert an untriaged note into one execution object — no retype (Section 3).

    program_id defaults to the source interaction's program; source_interaction_id
    is auto-linked so the created record traces back to the call.
    """
    item = repo.get_row(conn, "capture_inbox_items", item_id)
    if item["status"] != "untriaged":
        raise HTTPException(409, f"item is already {item['status']}")

    interaction = repo.get_row(conn, "interactions", item["interaction_id"])
    payload = dict(body.payload)
    payload.setdefault("program_id", interaction.get("program_id"))
    if not payload.get("program_id"):
        raise HTTPException(
            422,
            "This note's interaction is account-level; choose a program_id for the "
            f"{body.target_type} in the convert form.",
        )
    payload.setdefault("description", item["raw_text"])
    if body.target_type == "milestone":
        payload.setdefault("name", item["raw_text"])
    payload["source_interaction_id"] = item["interaction_id"]

    created = execution_ops.create(conn, body.target_type, payload)

    ts = now_utc()
    with conn:
        conn.execute(
            "UPDATE capture_inbox_items SET status='converted', converted_to_type=?, "
            "converted_to_id=?, resolved_on=?, resolved_by=?, updated_at=? WHERE id=?",
            (body.target_type, created["id"], ts[:10], audit.DEFAULT_ACTOR, ts, item_id),
        )
        after = repo.get_row(conn, "capture_inbox_items", item_id)
        audit.record(conn, object_type="capture_inbox_item", object_id=item_id,
                     action="convert", before=item, after=after)
    return {"item": after, "created": created, "target_type": body.target_type}


@router.post("/{item_id}/dismiss")
def dismiss_item(item_id: str, conn: sqlite3.Connection = Depends(get_conn)):
    """Dismiss a non-actionable note. Auditable, not a silent delete. (Convert arrives in v0.2.)"""
    before = repo.get_row(conn, "capture_inbox_items", item_id)
    if before["status"] != "untriaged":
        raise HTTPException(409, f"item is already {before['status']}")
    ts = now_utc()
    with conn:
        conn.execute(
            "UPDATE capture_inbox_items SET status='dismissed', resolved_on=?, resolved_by=?, updated_at=? WHERE id=?",
            (ts[:10], audit.DEFAULT_ACTOR, ts, item_id),
        )
        after = repo.get_row(conn, "capture_inbox_items", item_id)
        audit.record(conn, object_type="capture_inbox_item", object_id=item_id,
                     action="update", before=before, after=after)
    return after
