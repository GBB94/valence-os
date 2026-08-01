import sqlite3

from fastapi import APIRouter, Depends, HTTPException

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
    if b.client_visible:
        source_ref = before.get("source_reference_id")
        source_interaction = before.get("source_interaction_id")
        if not source_ref and not source_interaction:
            raise HTTPException(422, "a client-visible plan item needs a source")
        if source_ref:
            repo.get_row(conn, "source_references", source_ref)
        if source_interaction:
            interaction = repo.get_row(conn, "interactions", source_interaction)
            program = repo.get_row(conn, "programs", before["program_id"])
            if interaction["account_id"] != program["account_id"] or \
                    (interaction.get("program_id") and interaction["program_id"] != before["program_id"]):
                raise HTTPException(422, "source interaction belongs to a different scope")
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
