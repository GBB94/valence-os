"""Job table + in-process worker (PHASE-3-SPEC.md §0b, decisions.md D-74).

Covers: enqueue -> run -> succeeded; the built-in echo handler; failure path with retries
and a notification; scheduled-for jobs not running before their time; run_pending draining;
unknown-kind rejection; and the live Worker thread running a job on its own connection.
"""
import os
import tempfile
import time
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client():
    fd, path = tempfile.mkstemp(suffix=".sqlite")
    os.close(fd)
    os.environ["VALENCE_OS_DB"] = path
    os.environ["VALENCE_OS_WORKER"] = "0"  # deterministic: drive jobs synchronously
    from app.main import app
    with TestClient(app) as c:
        yield c
    for s in ("", "-wal", "-shm"):
        try: os.unlink(path + s)
        except FileNotFoundError: pass


def _future(seconds: int) -> str:
    return (datetime.now(timezone.utc).replace(microsecond=0)
            + timedelta(seconds=seconds)).isoformat()


# --- API-level -------------------------------------------------------------

def test_enqueue_run_and_succeed(client):
    job = client.post("/api/jobs", json={"kind": "echo", "payload": {"n": 1}}).json()
    assert job["status"] == "queued" and job["attempts"] == 0
    run = client.post("/api/jobs/run").json()
    assert run["count"] == 1
    got = client.get(f"/api/jobs/{job['id']}").json()
    assert got["status"] == "succeeded"
    assert got["attempts"] == 1 and got["finished_at"]
    import json as _json
    assert _json.loads(got["result_json"]) == {"echo": {"n": 1}}


def test_unknown_kind_rejected(client):
    r = client.post("/api/jobs", json={"kind": "not_a_handler"})
    assert r.status_code == 422


def test_missing_job_is_404(client):
    assert client.get("/api/jobs/nope").status_code == 404


def test_scheduled_job_waits_for_its_time(client):
    job = client.post("/api/jobs", json={"kind": "echo", "scheduled_for": _future(3600)}).json()
    # a drain now must not pick it up
    assert client.post("/api/jobs/run").json()["count"] == 0
    assert client.get(f"/api/jobs/{job['id']}").json()["status"] == "queued"


def test_list_filters_by_status(client):
    client.post("/api/jobs", json={"kind": "echo"})
    client.post("/api/jobs/run")
    done = client.get("/api/jobs", params={"status": "succeeded"}).json()["jobs"]
    assert len(done) == 1 and all(j["status"] == "succeeded" for j in done)


# --- module-level: failure path, retries, worker thread --------------------

def test_failure_marks_failed_and_notifies(client):
    from app import jobs

    @jobs.register("boom")
    def _boom(conn, payload):
        raise ValueError("kaboom")

    conn = client.app.state.conn
    job = jobs.enqueue(conn, "boom", {"x": 1})
    jobs.run_pending(conn)
    row = jobs.get_job(conn, job["id"])
    assert row["status"] == "failed" and "kaboom" in row["error"]
    # a failure notification was written
    n = client.get("/api/notifications?unread_only=true").json()
    assert n["unread"] >= 1


def test_retries_until_max_attempts(client):
    from app import jobs

    calls = {"n": 0}

    @jobs.register("flaky")
    def _flaky(conn, payload):
        calls["n"] += 1
        raise RuntimeError("still failing")

    conn = client.app.state.conn
    job = jobs.enqueue(conn, "flaky", max_attempts=3)
    # each drain makes one attempt (a requeued job isn't re-run within the same drain)
    for _ in range(3):
        jobs.run_pending(conn)
    row = jobs.get_job(conn, job["id"])
    assert calls["n"] == 3
    assert row["status"] == "failed" and row["attempts"] == 3


def test_worker_thread_runs_a_job(client):
    from app import jobs

    conn = client.app.state.conn
    job = jobs.enqueue(conn, "echo", {"via": "thread"})
    w = jobs.Worker(interval=0.05)
    w.start()
    try:
        deadline = time.time() + 3
        while time.time() < deadline:
            if jobs.get_job(conn, job["id"])["status"] == "succeeded":
                break
            time.sleep(0.05)
    finally:
        w.stop()
        w.join(timeout=2)
    assert jobs.get_job(conn, job["id"])["status"] == "succeeded"
