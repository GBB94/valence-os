"""Valence OS backend — v0.1 capture slice."""
from __future__ import annotations

import sqlite3
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from . import (copilot_service, ingestion, jobs, stage7,
               internal_reporting as internal_reporting_service)  # noqa: F401 — imports register job handlers
from .db import connect, run_migrations
from .routers import (
    accounts, campaigns, copilot, ai, attention, commercial, data, delivery, execution, expansion, inbox,
    ingestion as ingestion_router, interactions, jobs as jobs_router, library,
    mutual_action_plan, onboarding as onboarding_router, output, people, programs,
    relationships, search as search_router, stage7 as stage7_router, stage75 as stage75_router,
    stage9 as stage9_router, viz, internal_forecast, internal_asks, internal_reviews,
    internal_reporting, internal_roster, product_feedback, adoption_comms,
)


@jobs.register("echo")
def _echo(conn, payload):
    """Built-in handler: returns its payload. Used by the e2e demo and to prove the pipeline."""
    return {"echo": payload}


@asynccontextmanager
async def lifespan(app: FastAPI):
    conn = connect()
    applied = run_migrations(conn)
    if applied:
        print(f"[migrations] applied: {applied}")
    internal_reporting_service.sync_templates(conn)
    app.state.conn = conn
    worker = jobs.start_worker()  # env-gated (VALENCE_OS_WORKER); None when off
    if worker:
        print("[jobs] in-process worker started")
    yield
    if worker:
        worker.stop()
    conn.close()


app = FastAPI(title="Valence OS", version="0.1.0", lifespan=lifespan)


@app.exception_handler(sqlite3.IntegrityError)
def _integrity_error(request, exc: sqlite3.IntegrityError):
    """Database invariants are client errors, not server errors.

    The schema now carries ~95 triggers that `RAISE(ABORT, '<readable message>')` to enforce
    relationships single-column foreign keys cannot express — account scope, promotion
    provenance, comparator disjointness. Those fire correctly and protect the data, but an
    uncaught IntegrityError surfaces as a bare 500 with no message, which is indistinguishable
    from a crash and tells the operator nothing. The trigger already wrote a good sentence;
    this returns it.

    UNIQUE violations are a conflict rather than a validation failure, so they keep 409.
    """
    detail = str(exc)
    status = 409 if detail.startswith("UNIQUE constraint failed") else 422
    return JSONResponse(status_code=status, content={"detail": detail})

# Frontend runs on the Vite dev server in development.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(accounts.router)
app.include_router(campaigns.router)
app.include_router(copilot.router)
app.include_router(programs.router)
app.include_router(people.router)
app.include_router(interactions.router)
app.include_router(execution.router)
app.include_router(attention.router)
app.include_router(output.router)
app.include_router(commercial.router)
app.include_router(delivery.router)
app.include_router(data.router)
app.include_router(viz.router)
app.include_router(ai.router)
app.include_router(search_router.router)
app.include_router(library.router)
app.include_router(mutual_action_plan.router)
app.include_router(inbox.router)
app.include_router(jobs_router.router)
app.include_router(onboarding_router.router)
app.include_router(ingestion_router.router)
app.include_router(relationships.router)
app.include_router(expansion.router)
app.include_router(stage7_router.router)
app.include_router(stage75_router.router)
app.include_router(stage9_router.router)
app.include_router(internal_forecast.router)
app.include_router(internal_asks.router)
app.include_router(internal_reviews.router)
app.include_router(internal_reporting.router)
app.include_router(internal_roster.router)
app.include_router(product_feedback.router)
app.include_router(adoption_comms.router)


@app.get("/api/health")
def health():
    return {"status": "ok", "version": "0.1.0", "slice": "v0.1 capture"}


# Serve the built frontend if present (production-ish single-process serving).
_dist = Path(__file__).resolve().parent.parent.parent / "frontend" / "dist"
if _dist.is_dir():
    app.mount("/", StaticFiles(directory=str(_dist), html=True), name="frontend")
