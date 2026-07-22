import sqlite3

from fastapi import APIRouter, Depends, HTTPException

from .. import audit, repo
from ..db import now_utc
from ..deps import get_conn

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
