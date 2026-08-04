"""Single in-process job worker (PHASE-3-SPEC.md §0b / scoping-doc §7/8).

Boring on purpose: one `jobs` table, one background thread, no external queue. Long or
scheduled work — transcription, email sync, association, scheduled generation — enqueues a
job by `kind`; a registered handler runs it. Routine edits/navigation stay synchronous.

Handlers register with @register("kind"); each takes (conn, payload: dict) and returns a
JSON-serializable dict (or None). A handler that raises fails the job (retried up to
max_attempts, then marked 'failed' with a notification).

The auto-worker thread is env-gated (VALENCE_OS_WORKER, default off) so tests stay
deterministic and drive jobs synchronously via run_pending()/the run endpoint. The real
server turns it on. See decisions.md D-74.
"""
from __future__ import annotations

import json
import os
import sqlite3
import threading
import time
from typing import Any, Callable

from datetime import datetime, timedelta

from .db import connect, new_id, now_utc

# kind -> handler(conn, payload) -> result dict | None
Handler = Callable[[sqlite3.Connection, dict], "dict | None"]
HANDLERS: dict[str, Handler] = {}

# Retry backoff. A failed attempt previously went straight back to 'queued' with no
# scheduled_for, so the next drain retried it immediately — which is harmless against a mock
# adapter and a hammer against a failing real one. The delay grows per attempt and is capped.
# Set the base to 0 to restore immediate retries (the tests that assert attempt counts do).
#
# When a real HTTP adapter lands, a 429's `Retry-After` should override this for that job:
# honour the header when present, fall back to _retry_delay_seconds otherwise.
RETRY_BACKOFF_BASE_SECONDS = 30
RETRY_BACKOFF_MAX_SECONDS = 900


def _retry_delay_seconds(attempts_made: int) -> int:
    """Exponential backoff: 30s, 60s, 120s … capped at RETRY_BACKOFF_MAX_SECONDS."""
    if RETRY_BACKOFF_BASE_SECONDS <= 0:
        return 0
    delay = RETRY_BACKOFF_BASE_SECONDS * (2 ** max(0, attempts_made - 1))
    return min(delay, RETRY_BACKOFF_MAX_SECONDS)


def register(kind: str) -> Callable[[Handler], Handler]:
    """Decorator registering a handler for a job kind."""
    def deco(fn: Handler) -> Handler:
        HANDLERS[kind] = fn
        return fn
    return deco


def _notify(conn: sqlite3.Connection, kind: str, message: str, ref_type=None, ref_id=None) -> None:
    conn.execute(
        "INSERT INTO notifications (id, kind, message, ref_type, ref_id, read, created_at) "
        "VALUES (?,?,?,?,?,0,?)",
        (new_id(), kind, message, ref_type, ref_id, now_utc()),
    )


def _row(conn: sqlite3.Connection, job_id: str) -> dict | None:
    r = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
    return dict(r) if r else None


# --- enqueue / read ---------------------------------------------------------

def enqueue(
    conn: sqlite3.Connection,
    kind: str,
    payload: dict | None = None,
    *,
    scheduled_for: str | None = None,
    account_id: str | None = None,
    max_attempts: int = 1,
) -> dict:
    """Add a job. Does not run it — a worker (or run_pending) does. Returns the row."""
    jid = new_id()
    ts = now_utc()
    with conn:
        conn.execute(
            "INSERT INTO jobs (id, kind, payload_json, status, attempts, max_attempts, "
            "scheduled_for, account_id, created_at, updated_at) "
            "VALUES (?,?,?, 'queued', 0, ?, ?, ?, ?, ?)",
            (jid, kind, json.dumps(payload) if payload is not None else None,
             max_attempts, scheduled_for, account_id, ts, ts),
        )
    return _row(conn, jid)


def get_job(conn: sqlite3.Connection, job_id: str) -> dict | None:
    return _row(conn, job_id)


def list_jobs(conn: sqlite3.Connection, *, status: str | None = None,
              account_id: str | None = None, limit: int = 100) -> list[dict]:
    where, params = [], []
    if status:
        where.append("status = ?"); params.append(status)
    if account_id:
        where.append("account_id = ?"); params.append(account_id)
    clause = ("WHERE " + " AND ".join(where)) if where else ""
    rows = conn.execute(
        f"SELECT * FROM jobs {clause} ORDER BY created_at DESC LIMIT ?",
        (*params, limit),
    ).fetchall()
    return [dict(r) for r in rows]


# --- execution --------------------------------------------------------------

def _claim_next(conn: sqlite3.Connection, skip_ids: set[str] | None = None) -> dict | None:
    """Atomically claim the oldest due, queued job and mark it running. None if none due.

    `skip_ids` excludes jobs already attempted in this drain, so a job that fails and returns
    to 'queued' is not immediately re-claimed. The exclusion has to happen HERE rather than
    after run_next returns: checking afterwards means the handler has already run again, which
    is exactly how one drain used to burn two attempts.
    """
    ts = now_utc()
    skip = tuple(skip_ids or ())
    not_in = f" AND id NOT IN ({','.join('?' * len(skip))})" if skip else ""
    with conn:  # transaction: select-then-update as one unit
        r = conn.execute(
            "SELECT * FROM jobs WHERE status = 'queued' "
            "AND (scheduled_for IS NULL OR scheduled_for <= ?)"
            + not_in +
            " ORDER BY created_at LIMIT 1",
            (ts, *skip),
        ).fetchone()
        if r is None:
            return None
        conn.execute(
            "UPDATE jobs SET status = 'running', attempts = attempts + 1, "
            "started_at = COALESCE(started_at, ?), updated_at = ? WHERE id = ?",
            (ts, ts, r["id"]),
        )
    return _row(conn, r["id"])


def run_next(conn: sqlite3.Connection, skip_ids: set[str] | None = None) -> dict | None:
    """Claim and run one due job. Returns the finished job row, or None if nothing was due."""
    job = _claim_next(conn, skip_ids)
    if job is None:
        return None
    handler = HANDLERS.get(job["kind"])
    payload = json.loads(job["payload_json"]) if job["payload_json"] else {}
    if job["kind"] == "weekly_team_update":
        payload["_job_id"] = job["id"]
    try:
        if handler is None:
            raise RuntimeError(f"no handler registered for job kind '{job['kind']}'")
        result = handler(conn, payload)
        ts = now_utc()
        with conn:
            conn.execute(
                "UPDATE jobs SET status = 'succeeded', result_json = ?, error = NULL, "
                "finished_at = ?, updated_at = ? WHERE id = ?",
                (json.dumps(result) if result is not None else None, ts, ts, job["id"]),
            )
        return _row(conn, job["id"])
    except Exception as exc:  # a handler failure must never crash the worker loop
        ts = now_utc()
        exhausted = job["attempts"] >= job["max_attempts"]
        with conn:
            if exhausted:
                conn.execute(
                    "UPDATE jobs SET status = 'failed', error = ?, finished_at = ?, "
                    "updated_at = ? WHERE id = ?",
                    (str(exc), ts, ts, job["id"]),
                )
                _notify(conn, "job_failed",
                        f"Job '{job['kind']}' failed: {exc}", "job", job["id"])
            else:
                # Leave for another attempt, but not immediately: back off so a persistently
                # failing job cannot be retried on every drain.
                delay = _retry_delay_seconds(job["attempts"])
                next_at = (
                    (datetime.fromisoformat(ts) + timedelta(seconds=delay)).isoformat()
                    if delay else None
                )
                conn.execute(
                    "UPDATE jobs SET status = 'queued', error = ?, scheduled_for = ?, "
                    "updated_at = ? WHERE id = ?",
                    (str(exc), next_at, ts, job["id"]),
                )
        return _row(conn, job["id"])


def run_pending(conn: sqlite3.Connection, max_jobs: int = 100) -> list[dict]:
    """Drain due jobs until none remain or max_jobs processed. Returns finished rows.

    A job left 'queued' after a failed attempt (retries remaining) is not re-run within the
    same drain — it waits for the next pass — so one bad job can't spin the loop.
    """
    done: list[dict] = []
    seen: set[str] = set()
    while len(done) < max_jobs:
        job = run_next(conn, skip_ids=seen)
        if job is None:
            break
        seen.add(job["id"])
        done.append(job)
    return done


# --- background worker ------------------------------------------------------

class Worker(threading.Thread):
    """Polls its own connection for due jobs. One per process (the single in-process worker)."""

    def __init__(self, interval: float = 0.5):
        super().__init__(daemon=True, name="valence-job-worker")
        self.interval = interval
        self._stop_event = threading.Event()
        self._conn: sqlite3.Connection | None = None

    def run(self) -> None:
        self._conn = connect()
        while not self._stop_event.is_set():
            try:
                run_pending(self._conn)
            except Exception:  # never let the worker thread die on a transient error
                pass
            self._stop_event.wait(self.interval)
        self._conn.close()

    def stop(self) -> None:
        self._stop_event.set()


def worker_enabled() -> bool:
    """Auto-worker is opt-in (default off) so tests are deterministic (decisions.md D-74)."""
    return os.environ.get("VALENCE_OS_WORKER", "0") not in ("0", "", "false", "False")


def start_worker(interval: float = 0.5) -> Worker | None:
    if not worker_enabled():
        return None
    w = Worker(interval=interval)
    w.start()
    return w
