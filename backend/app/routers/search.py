import sqlite3

from fastapi import APIRouter, Depends

from .. import search as search_lib
from ..deps import get_conn

router = APIRouter(prefix="/api", tags=["search"])


@router.get("/search")
def global_search(q: str = "", limit: int = 30, account_id: str | None = None,
                  program_id: str | None = None, record_types: str | None = None,
                  conn: sqlite3.Connection = Depends(get_conn)):
    """Full-text search across native records and stored summaries (Section 8)."""
    types = [t.strip() for t in (record_types or "").split(",") if t.strip()]
    return {"q": q, "results": search_lib.search(
        conn, q, limit=limit, account_id=account_id, program_id=program_id,
        record_types=types)}
