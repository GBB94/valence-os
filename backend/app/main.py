"""Account OS backend — v0.1 capture slice."""
from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .db import connect, run_migrations
from .routers import (
    accounts, attention, commercial, delivery, execution, inbox, interactions,
    output, people, programs,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    conn = connect()
    applied = run_migrations(conn)
    if applied:
        print(f"[migrations] applied: {applied}")
    app.state.conn = conn
    yield
    conn.close()


app = FastAPI(title="Account OS", version="0.1.0", lifespan=lifespan)

# Frontend runs on the Vite dev server in development.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(accounts.router)
app.include_router(programs.router)
app.include_router(people.router)
app.include_router(interactions.router)
app.include_router(execution.router)
app.include_router(attention.router)
app.include_router(output.router)
app.include_router(commercial.router)
app.include_router(delivery.router)
app.include_router(inbox.router)


@app.get("/api/health")
def health():
    return {"status": "ok", "version": "0.1.0", "slice": "v0.1 capture"}


# Serve the built frontend if present (production-ish single-process serving).
_dist = Path(__file__).resolve().parent.parent.parent / "frontend" / "dist"
if _dist.is_dir():
    app.mount("/", StaticFiles(directory=str(_dist), html=True), name="frontend")
