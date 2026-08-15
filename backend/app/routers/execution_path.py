"""Account Path execution model API (ACCOUNT-PATH-SPEC.md §10.1). Read-only by construction.

There is exactly one route and it projects. Opening it must not update visit state, review
checkpoints, phase state, proposed items, or any canonical record — including no readiness write,
because readiness is a projection with nothing to write to.
"""
import sqlite3

from fastapi import APIRouter, Depends, Query

from .. import execution_path
from ..deps import get_conn

router = APIRouter(prefix="/api", tags=["account-path"])


@router.get("/accounts/{account_id}/execution-path")
def account_execution_path(account_id: str, program_id: str | None = Query(default=None),
                           conn: sqlite3.Connection = Depends(get_conn)):
    """§10.1. Omitting `program_id` gives all-program scope with one path lane per program.

    An unknown, archived, or foreign `program_id` is a 404, never a silent fallback to all
    programs — a fallback would answer a different question than the one asked.
    """
    return execution_path.build_execution_path(conn, account_id, program_id=program_id)
