import sqlite3

from fastapi import APIRouter, Depends

from .. import audit, output_gen, repo
from ..db import now_utc
from ..deps import get_conn
from ..schemas import MapPromote

router = APIRouter(prefix="/api", tags=["map"])

_TABLE = {"commitment": "commitments", "task": "tasks", "milestone": "milestones"}


@router.post("/map/promote")
def promote(b: MapPromote, conn: sqlite3.Connection = Depends(get_conn)):
    """Promote (or demote) an execution object onto the client-facing mutual action plan."""
    table = _TABLE[b.object_type]
    before = repo.get_row(conn, table, b.object_id)
    with conn:
        conn.execute(f"UPDATE {table} SET client_visible=?, updated_at=? WHERE id=?",
                     (1 if b.client_visible else 0, now_utc(), b.object_id))
        after = repo.get_row(conn, table, b.object_id)
        audit.record(conn, object_type=b.object_type, object_id=b.object_id, action="update",
                     before=before, after=after)
    return after


@router.get("/accounts/{account_id}/map")
def account_map(account_id: str, conn: sqlite3.Connection = Depends(get_conn)):
    return output_gen.mutual_action_plan(conn, account_id)
