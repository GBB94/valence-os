"""HTTP boundary for internal report previews, documents, and honest analytics."""
import sqlite3

from fastapi import APIRouter, Depends, HTTPException

from .. import internal_reporting as service
from ..deps import get_conn
from ..schemas import ReportRedOriginExclusionCreate

router = APIRouter(prefix="/api", tags=["internal-reporting"])


@router.get("/internal-reports/{kind}/preview")
def preview(kind: str, conn: sqlite3.Connection = Depends(get_conn)):
    if kind != "monthly_portfolio_brief":
        raise HTTPException(422, "unsupported portfolio report kind")
    return service.monthly_preview(conn)


@router.post("/internal-reports/{kind}/documents", status_code=201)
def create(kind: str, conn: sqlite3.Connection = Depends(get_conn)):
    if kind != "monthly_portfolio_brief":
        raise HTTPException(422, "unsupported portfolio report kind")
    return service.generate_monthly(conn)


@router.get("/internal-reports/no-surprises")
def validate(conn: sqlite3.Connection = Depends(get_conn)):
    return service.no_surprises(conn)


@router.post("/internal-reports/red-origin-exclusions", status_code=201)
def exclude_origin(body: ReportRedOriginExclusionCreate, conn: sqlite3.Connection = Depends(get_conn)):
    return service.create_red_origin_exclusion(conn, body.model_dump())


@router.get("/portfolio/internal-analytics")
def analytics(conn: sqlite3.Connection = Depends(get_conn)):
    return service.portfolio_analytics(conn)
