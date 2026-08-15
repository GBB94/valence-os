"""HTTP boundary for the internal forecast ledger."""
import sqlite3

from fastapi import APIRouter, Depends

from .. import internal_forecast as service
from ..deps import get_conn
from ..schemas import (ForecastCategoryChange, ForecastEntryCreate, ForecastEntryPatch,
                       ForecastPeriodCreate, ForecastSourceCreate, RenewalOutcomeCreate)

router = APIRouter(prefix="/api", tags=["internal-forecast"])


@router.get("/forecast-periods")
def periods(conn: sqlite3.Connection = Depends(get_conn)):
    return service.list_periods(conn)


@router.post("/forecast-periods", status_code=201)
def create_period(body: ForecastPeriodCreate, conn: sqlite3.Connection = Depends(get_conn)):
    return service.create_period(conn, body.model_dump())


@router.get("/forecast-periods/{period_id}/entries")
def entries(period_id: str, conn: sqlite3.Connection = Depends(get_conn)):
    return service.list_entries(conn, period_id)


@router.post("/forecast-periods/{period_id}/entries", status_code=201)
def create_entry(period_id: str, body: ForecastEntryCreate, conn: sqlite3.Connection = Depends(get_conn)):
    return service.create_entry(conn, period_id, body.model_dump())


@router.patch("/forecast-entries/{entry_id}")
def patch_entry(entry_id: str, body: ForecastEntryPatch, conn: sqlite3.Connection = Depends(get_conn)):
    return service.patch_entry(conn, entry_id, body.model_dump(), body.model_fields_set)


@router.post("/forecast-entries/{entry_id}/category")
def category(entry_id: str, body: ForecastCategoryChange, conn: sqlite3.Connection = Depends(get_conn)):
    return service.change_category(conn, entry_id, body.model_dump())


@router.get("/forecast-entries/{entry_id}/evidence")
def evidence(entry_id: str, conn: sqlite3.Connection = Depends(get_conn)):
    return service.evidence(conn, entry_id)


@router.post("/forecast-entries/{entry_id}/sources", status_code=201)
def add_source(entry_id: str, body: ForecastSourceCreate, conn: sqlite3.Connection = Depends(get_conn)):
    return service.add_source(conn, entry_id, body.model_dump())


@router.post("/renewal-outcomes", status_code=201)
def renewal_outcome(body: RenewalOutcomeCreate, conn: sqlite3.Connection = Depends(get_conn)):
    return service.record_renewal_outcome(conn, body.model_dump())


@router.post("/forecast-periods/{period_id}/lock")
def lock(period_id: str, conn: sqlite3.Connection = Depends(get_conn)):
    return service.lock_period(conn, period_id)


@router.post("/forecast-periods/{period_id}/submissions", status_code=201)
def submit(period_id: str, conn: sqlite3.Connection = Depends(get_conn)):
    return service.submit(conn, period_id)


@router.post("/forecast-periods/{period_id}/close")
def close(period_id: str, conn: sqlite3.Connection = Depends(get_conn)):
    return service.close_period(conn, period_id)


@router.get("/forecast-periods/{period_id}/calibration")
def calibration(period_id: str, conn: sqlite3.Connection = Depends(get_conn)):
    return service.calibration(conn, period_id)
