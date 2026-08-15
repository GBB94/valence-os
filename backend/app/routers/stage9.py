"""Stage 9 API: honest portfolio analytics and human-curated expansion learning."""
import sqlite3

from fastapi import APIRouter, Depends

from .. import stage9
from ..deps import get_conn
from ..schemas import PlaybookEntryCreate, PlaybookMessagePromotion, PlaybookPlayPromotion

router = APIRouter(prefix="/api", tags=["stage9"])


@router.get("/portfolio/commercial-analytics")
def commercial_analytics(window_days: int = 90, conn: sqlite3.Connection = Depends(get_conn)):
    return stage9.portfolio_analytics(conn, window_days)


@router.get("/playbook-entries")
def playbook_entries(account_id: str | None = None,
                     conn: sqlite3.Connection = Depends(get_conn)):
    return {"entries": stage9.list_entries(conn, account_id),
            "pending": stage9.pending_transitions(conn, account_id)}


@router.post("/playbook-entries", status_code=201)
def create_playbook_entry(body: PlaybookEntryCreate,
                          conn: sqlite3.Connection = Depends(get_conn)):
    return stage9.create_entry(conn, body.model_dump())


@router.get("/whitespace-cells/{cell_id}/playbook-matches")
def playbook_matches(cell_id: str, conn: sqlite3.Connection = Depends(get_conn)):
    return stage9.matches(conn, cell_id)


@router.post("/playbook-entries/{entry_id}/promote-play", status_code=201)
def promote_play(entry_id: str, body: PlaybookPlayPromotion,
                 conn: sqlite3.Connection = Depends(get_conn)):
    return stage9.promote_play(conn, entry_id, body.name, body.action_template)


@router.post("/playbook-entries/{entry_id}/promote-message", status_code=201)
def promote_message(entry_id: str, body: PlaybookMessagePromotion,
                    conn: sqlite3.Connection = Depends(get_conn)):
    return stage9.promote_message(conn, entry_id, body.model_dump())
