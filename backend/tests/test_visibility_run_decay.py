"""Acceptance tests for VISIBILITY-SPEC.md Slice 1 — decay and withholding on persisted runs.

`copilot_runs` is the only place in the app that persists generated prose and re-opens it by id, so
it is the only place a February answer can render in August as if it were written this morning.
These tests try to make that happen: to get the body out of an over-window run without asking, to
get a different treatment for a run that arrived from history than for one just asked, to hide the
evidence along with the prose, and to launder a withheld answer into a saved internal note.
"""
import os
import sqlite3
import tempfile
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from conftest import utc_day


@pytest.fixture()
def client():
    fd, path = tempfile.mkstemp(suffix=".sqlite"); os.close(fd)
    os.environ["VALENCE_OS_DB"] = path
    os.environ["VALENCE_OS_WORKER"] = "0"
    os.environ["COPILOT_BACKEND"] = "mock"
    from app.main import app
    with TestClient(app) as c:
        c.db_path = path
        yield c
    for suffix in ("", "-wal", "-shm"):
        try: os.unlink(path + suffix)
        except FileNotFoundError: pass


def _setup(c):
    account = c.post("/api/accounts", json={"name": "Northwind Synthetic"}).json()
    program = c.post("/api/programs", json={"account_id": account["id"], "name": "Europe"}).json()
    person = c.post("/api/persons", json={"name": "Jordan Lee", "account_id": account["id"]}).json()
    interaction = c.post("/api/interactions", json={
        "account_id": account["id"], "program_id": program["id"], "occurred_on": utc_day(),
        "type": "meeting", "summary": "Security review walkthrough",
        "raw_notes": "Security review is the gate before the pilot widens."}).json()
    c.post("/api/commitments", json={
        "account_id": account["id"], "program_id": program["id"],
        "description": "Complete the Security review packet", "owner_side": "valence",
        "source_interaction_id": interaction["id"], "due_date": utc_day(5)})
    return account, program, person


def _ask(c, body):
    queued = c.post("/api/copilot/runs", json=body)
    assert queued.status_code == 202, queued.text
    c.post("/api/jobs/run")
    return c.get(f"/api/copilot/runs/{queued.json()['id']}").json()


_IMMUTABLE = "trg_copilot_run_answer_frozen"


def _backdate(c, run_id, days):
    """
    Move a completed run's `generated_at` back N days. Nothing else about the run changes.

    A completed run is immutable — `trg_copilot_run_answer_frozen` aborts this update, and
    correctly so, which is why there is no application path that ages a run. The trigger is lifted
    for the single statement and put back from `sqlite_master`'s own text rather than from a copy of
    the DDL kept here, so a test fixture cannot quietly leave the invariant weaker than it found it.
    """
    stamp = (datetime.now(UTC) - timedelta(days=days)).replace(microsecond=0).isoformat()
    conn = sqlite3.connect(c.db_path)
    try:
        ddl = conn.execute("SELECT sql FROM sqlite_master WHERE type='trigger' AND name=?",
                           (_IMMUTABLE,)).fetchone()
        assert ddl, f"{_IMMUTABLE} is missing; the immutability invariant is gone"
        with conn:
            conn.execute(f"DROP TRIGGER {_IMMUTABLE}")
            conn.execute("UPDATE copilot_runs SET generated_at=? WHERE id=?", (stamp, run_id))
            conn.execute(ddl[0])
        restored = conn.execute("SELECT COUNT(*) FROM sqlite_master WHERE type='trigger' AND name=?",
                                (_IMMUTABLE,)).fetchone()[0]
        assert restored == 1
    finally:
        conn.close()
    return stamp


def _reason(c, run_id):
    return c.get(f"/api/copilot/runs/{run_id}").json()["freshness"]["withheld_reason"]


def _completed_run(c, account_id):
    run = _ask(c, {"scope_type": "account", "account_id": account_id,
                   "query_text": "What did we promise on the Security review?"})
    assert run["status"] == "completed", run
    assert run["answer_markdown"]
    return run


# --- the window itself -------------------------------------------------------------------------

def test_a_fresh_run_returns_its_body_and_no_refusal(client):
    account, _, _ = _setup(client)
    run = _completed_run(client, account["id"])
    assert run["freshness"]["withheld"] is False
    assert run["freshness"]["withheld_reason"] is None
    assert run["answer_markdown"]


def test_a_run_past_its_window_returns_a_sentence_and_no_body(client):
    account, _, _ = _setup(client)
    run = _completed_run(client, account["id"])
    _backdate(client, run["id"], 200)
    stale = client.get(f"/api/copilot/runs/{run['id']}").json()
    assert stale["freshness"]["withheld"] is True
    assert stale["answer_markdown"] is None
    # The clause is a lower-case completion of "held back because ...", never a whole sentence, so
    # the one frame in `sharedPlan.js` is the only place a capital letter and a full stop appear.
    reason = stale["freshness"]["withheld_reason"]
    assert reason and reason[0].islower() and not reason.endswith(".")


def test_the_refusal_names_the_window_rather_than_referring_to_it(client):
    """Rule 4: the threshold rides on the payload so the sentence can say what it is."""
    account, _, _ = _setup(client)
    run = _completed_run(client, account["id"])
    _backdate(client, run["id"], 200)
    stale = client.get(f"/api/copilot/runs/{run['id']}").json()
    threshold = stale["freshness"]["threshold_days"]
    assert threshold == 30  # account scope
    assert f"{threshold}-day" in stale["freshness"]["withheld_reason"]
    assert "200 days ago" in stale["freshness"]["withheld_reason"]


def test_the_window_is_a_property_of_scope_not_a_constant(client):
    """A 20-day-old answer is past a program window and inside an account one, on the same day."""
    account, program, _ = _setup(client)
    account_run = _completed_run(client, account["id"])
    queued = client.post("/api/copilot/runs", json={
        "scope_type": "program", "account_id": account["id"], "program_id": program["id"],
        "query_text": "What did we promise on the Security review?"})
    assert queued.status_code == 202, queued.text
    client.post("/api/jobs/run")
    program_run_id = queued.json()["id"]
    _backdate(client, account_run["id"], 20)
    _backdate(client, program_run_id, 20)
    account_after = client.get(f"/api/copilot/runs/{account_run['id']}").json()
    program_after = client.get(f"/api/copilot/runs/{program_run_id}").json()
    assert account_after["freshness"]["threshold_days"] == 30
    assert program_after["freshness"]["threshold_days"] == 14
    assert account_after["freshness"]["withheld"] is False
    assert program_after["freshness"]["withheld"] is True


def test_the_boundary_day_is_not_withheld(client):
    """Exactly at the window is inside it. Off-by-one here silently withholds a current answer."""
    account, _, _ = _setup(client)
    run = _completed_run(client, account["id"])
    _backdate(client, run["id"], 30)
    at_boundary = client.get(f"/api/copilot/runs/{run['id']}").json()
    assert at_boundary["freshness"]["age_days"] == 30
    assert at_boundary["freshness"]["withheld"] is False
    _backdate(client, run["id"], 31)
    past = client.get(f"/api/copilot/runs/{run['id']}").json()
    assert past["freshness"]["withheld"] is True


# --- what withholding does and does not touch --------------------------------------------------

def test_the_claims_and_sources_block_is_never_withheld(client):
    """Rule 5: an operator handed a refusal needs the evidence that explains it."""
    account, _, _ = _setup(client)
    run = _completed_run(client, account["id"])
    assert run["claims"] and run["sources"]
    _backdate(client, run["id"], 200)
    stale = client.get(f"/api/copilot/runs/{run['id']}").json()
    assert stale["answer_markdown"] is None
    assert len(stale["claims"]) == len(run["claims"])
    assert len(stale["sources"]) == len(run["sources"])
    assert [c["claim_text"] for c in stale["claims"]] == [c["claim_text"] for c in run["claims"]]


def test_reveal_returns_the_same_body_that_was_written_and_stays_withheld(client):
    """Revealing is reading a record, not making it current. Nothing regenerates."""
    account, _, _ = _setup(client)
    run = _completed_run(client, account["id"])
    stamp = _backdate(client, run["id"], 200)
    revealed = client.get(f"/api/copilot/runs/{run['id']}", params={"reveal": "true"}).json()
    assert revealed["answer_markdown"] == run["answer_markdown"]
    assert revealed["id"] == run["id"]
    assert revealed["generated_at"] == stamp
    # Still withheld — the operator opened it, which is not the same as it being current.
    assert revealed["freshness"]["withheld"] is True
    assert revealed["freshness"]["revealed"] is True
    assert revealed["freshness"]["withheld_reason"] == _reason(client, run["id"])


def test_the_saved_runs_list_withholds_the_same_bodies_as_the_detail_read(client):
    """The list is where a stale answer is most likely to be re-opened; it may not ship the body."""
    account, _, _ = _setup(client)
    run = _completed_run(client, account["id"])
    _backdate(client, run["id"], 200)
    listed = client.get("/api/copilot/runs", params={
        "scope_type": "account", "account_id": account["id"]}).json()["runs"]
    row = next(item for item in listed if item["id"] == run["id"])
    assert row["answer_markdown"] is None
    assert row["freshness"]["withheld"] is True
    assert row["freshness"]["withheld_reason"] == _reason(client, run["id"])


def test_a_withheld_answer_cannot_seed_a_saved_internal_note(client):
    """Copying the prose into a document would carry it forward without its refusal."""
    account, _, _ = _setup(client)
    run = _completed_run(client, account["id"])
    ok = client.post(f"/api/copilot/runs/{run['id']}/draft-preview", json={"title": "Internal note"})
    assert ok.status_code == 200, ok.text
    _backdate(client, run["id"], 200)
    refused = client.post(f"/api/copilot/runs/{run['id']}/draft-preview",
                          json={"title": "Internal note"})
    assert refused.status_code == 409
    assert "held back because" in refused.json()["detail"]
    saved = client.post(f"/api/copilot/runs/{run['id']}/draft", json={"title": "Internal note"})
    assert saved.status_code == 409


# --- treatment does not depend on how the run reached the screen --------------------------------

def test_arrival_route_does_not_change_the_freshness_answer(client):
    """Rule 1: the signal is the date. Detail, list, and reveal agree on every field but `revealed`."""
    account, _, _ = _setup(client)
    run = _completed_run(client, account["id"])
    _backdate(client, run["id"], 200)
    detail = client.get(f"/api/copilot/runs/{run['id']}").json()["freshness"]
    listed = next(item for item in client.get("/api/copilot/runs", params={
        "scope_type": "account", "account_id": account["id"]}).json()["runs"]
        if item["id"] == run["id"])["freshness"]
    revealed = client.get(f"/api/copilot/runs/{run['id']}",
                          params={"reveal": "true"}).json()["freshness"]
    assert detail == listed
    assert {k: v for k, v in revealed.items() if k != "revealed"} == \
           {k: v for k, v in detail.items() if k != "revealed"}


# --- nothing was stored -------------------------------------------------------------------------

def test_this_slice_stores_nothing(client):
    """`freshness` is a query-time projection. A stored copy is a second thing that can disagree."""
    conn = sqlite3.connect(client.db_path)
    try:
        columns = {row[1] for row in conn.execute("PRAGMA table_info(copilot_runs)")}
        tables = {row[0] for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
    finally:
        conn.close()
    for forbidden in ("freshness", "withheld", "withheld_reason", "threshold_days",
                      "age_days", "is_stale", "revealed"):
        assert forbidden not in columns, f"copilot_runs.{forbidden} would be a stored state"
    assert not [t for t in tables if "freshness" in t or "decay" in t]


def test_an_abstained_run_is_never_described_as_withheld(client):
    """Abstention and staleness are different refusals; merging them loses which one happened."""
    from app import copilot_service
    row = {"scope_type": "account", "status": "abstained", "generated_at": None,
           "answer_markdown": None}
    freshness = copilot_service.answer_freshness(row)
    assert freshness["withheld"] is False
    assert freshness["withheld_reason"] is None
    assert freshness["age_days"] is None
