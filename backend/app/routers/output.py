import sqlite3

from fastapi import APIRouter, Depends

from .. import output_gen
from ..deps import get_conn

router = APIRouter(prefix="/api", tags=["output"])


@router.get("/accounts/{account_id}/history")
def account_history(account_id: str, person_id: str | None = None, program_id: str | None = None,
                    conn: sqlite3.Connection = Depends(get_conn)):
    return output_gen.account_history(conn, account_id, person_id=person_id, program_id=program_id)


@router.get("/team-update")
def team_update(since: str | None = None, conn: sqlite3.Connection = Depends(get_conn)):
    return output_gen.team_update(conn, since=since)


@router.get("/accounts/{account_id}/qbr")
def qbr(account_id: str, conn: sqlite3.Connection = Depends(get_conn)):
    return output_gen.qbr(conn, account_id)
