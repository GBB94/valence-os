"""Jobs API — enqueue, inspect, and (when the auto-worker is off) drain the job table.

The worker runs in-process; these endpoints let the UI show job status and let a demo/test
drive work deterministically without the background thread. See app/jobs.py, decisions.md D-74.
"""
import sqlite3

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from .. import jobs
from ..deps import get_conn

router = APIRouter(prefix="/api", tags=["jobs"])


class EnqueueJob(BaseModel):
    kind: str
    payload: dict | None = None
    scheduled_for: str | None = None
    account_id: str | None = None
    max_attempts: int = 1


@router.post("/jobs", status_code=201)
def create_job(body: EnqueueJob, conn: sqlite3.Connection = Depends(get_conn)):
    if body.kind not in jobs.HANDLERS:
        raise HTTPException(status_code=422, detail=f"unknown job kind: {body.kind}")
    return jobs.enqueue(
        conn, body.kind, body.payload,
        scheduled_for=body.scheduled_for, account_id=body.account_id,
        max_attempts=body.max_attempts,
    )


@router.get("/jobs")
def list_jobs(status: str | None = None, account_id: str | None = None,
              conn: sqlite3.Connection = Depends(get_conn)):
    return {"jobs": jobs.list_jobs(conn, status=status, account_id=account_id)}


@router.get("/jobs/{job_id}")
def get_job(job_id: str, conn: sqlite3.Connection = Depends(get_conn)):
    job = jobs.get_job(conn, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"job not found: {job_id}")
    return job


@router.post("/jobs/run")
def run_pending(conn: sqlite3.Connection = Depends(get_conn)):
    """Drain due jobs synchronously. A no-op when the background worker is already running."""
    processed = jobs.run_pending(conn)
    return {"processed": processed, "count": len(processed)}
