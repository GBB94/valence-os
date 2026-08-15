"""HTTP boundary for account coverage and briefing."""
import sqlite3

from fastapi import APIRouter, Depends

from .. import internal_roster as service
from ..deps import get_conn
from ..schemas import RosterCreate

router = APIRouter(prefix="/api", tags=["internal-roster"])


@router.get("/accounts/{account_id}/internal-roster")
def roster(account_id: str, conn: sqlite3.Connection = Depends(get_conn)):
    return service.list_roster(conn, account_id)


@router.post("/accounts/{account_id}/internal-roster", status_code=201)
def add(account_id: str, body: RosterCreate, conn: sqlite3.Connection = Depends(get_conn)):
    return service.add(conn, account_id, body.model_dump())


@router.get("/accounts/{account_id}/coverage")
def coverage(account_id: str, days: int = 14, conn: sqlite3.Connection = Depends(get_conn)):
    return service.coverage_data(conn, account_id, days)


@router.get("/accounts/{account_id}/coverage-brief")
def coverage_brief(account_id: str, days: int = 14, conn: sqlite3.Connection = Depends(get_conn)):
    return service.generate_coverage_brief(conn, account_id, days)


@router.get("/accounts/{account_id}/call-brief")
def call_brief(account_id: str, roster_id: str, days: int = 14,
               conn: sqlite3.Connection = Depends(get_conn)):
    return service.generate_role_brief(conn, account_id, roster_id, days)


@router.get("/accounts/{account_id}/return-brief")
def return_brief(account_id: str, starts_on: str, ends_on: str,
                 conn: sqlite3.Connection = Depends(get_conn)):
    return service.generate_return_brief(conn, account_id, starts_on, ends_on)
