"""Regression tests for six defects found by an adversarial review of Stages 1-5 (D-85).

Each of these reproduced against the pre-fix code. They are grouped here rather than scattered
into the per-stage files because they share a cause worth naming: **a write path that trusts
its inputs.** Three of them (cross-account onboarding, accept-then-reject, placeholder fill)
are the same shape as the QBR account-scoping bug fixed in D-82 — an endpoint that looks up a
row by id and never checks the row belongs where the caller says it does.
"""
import os
import tempfile

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client():
    fd, path = tempfile.mkstemp(suffix=".sqlite")
    os.close(fd)
    os.environ["VALENCE_OS_DB"] = path
    os.environ["VALENCE_OS_WORKER"] = "0"
    from app.main import app
    with TestClient(app) as c:
        yield c
    for s in ("", "-wal", "-shm"):
        try: os.unlink(path + s)
        except FileNotFoundError: pass


# --- onboarding write path ----------------------------------------------------------------
def test_onboarding_rejects_a_program_from_another_account(client):
    """Seeding account A's launch pack onto account B's program mixes two customers' data."""
    a = client.post("/api/accounts", json={"name": "A"}).json()
    b = client.post("/api/accounts", json={"name": "B"}).json()
    bp = client.post("/api/programs", json={"account_id": b["id"], "name": "B program"}).json()

    r = client.post(f"/api/accounts/{a['id']}/onboard",
                    json={"kickoff_date": "2026-08-01", "program_id": bp["id"]})
    assert r.status_code == 422 and "different account" in r.json()["detail"]
    # and B's program is untouched — no checklist seeded against it
    assert client.get(f"/api/accounts/{b['id']}/onboarding").json()["checklist_progress"]["total"] == 0


def test_bad_kickoff_date_writes_nothing(client):
    """The date used to blow up mid-way through seeding milestones, leaving an orphan program
    behind and surfacing as a 500. A bad date should cost nothing."""
    a = client.post("/api/accounts", json={"name": "A"}).json()
    r = client.post(f"/api/accounts/{a['id']}/onboard", json={"kickoff_date": "not-a-date"})
    assert r.status_code == 422
    assert client.get(f"/api/accounts/{a['id']}").json()["programs"] == []


# --- extraction acceptance ------------------------------------------------------------------
def test_placeholder_fill_converts_the_placeholder_instead_of_duplicating(client):
    """`fill_placeholder` must fill a placeholder. It used to always INSERT a new person,
    leaving the position unidentified — two org-chart rows for one seat, and the
    `unidentified_placeholder` queue trigger firing forever."""
    a = client.post("/api/accounts", json={"name": "A"}).json()
    ob = client.post(f"/api/accounts/{a['id']}/onboard", json={"kickoff_date": "2026-08-01"}).json()
    before = client.get(f"/api/accounts/{a['id']}/onboarding").json()["placeholders"]
    it_lead = next(p for p in before if p["title"] == "IT security lead")

    run = client.post("/api/extraction/run", json={
        "account_id": a["id"], "program_id": ob["program_id"],
        "transcript": "Our new VP of IT is Dana Okafor."}).json()
    prop = next(p for p in run["proposals"] if p["mutation_type"] == "fill_placeholder")
    assert client.post(f"/api/extraction/proposals/{prop['id']}/accept",
                       json={"overrides": {}}).status_code == 200

    filled = client.get(f"/api/persons/{it_lead['id']}/card").json()
    assert filled["is_placeholder"] is False and filled["name"] == "Dana Okafor"
    names = [p["name"] for p in client.get(f"/api/persons?account_id={a['id']}").json()]
    assert names.count("Dana Okafor") == 1                       # converted, not duplicated
    assert "IT security lead (unknown)" not in names


def test_placeholder_fill_can_name_its_target_explicitly(client):
    """Ambiguity is resolved by the operator, not by the matcher — the spec's rule is that
    low-confidence associations are assigned by a human, never guessed."""
    a = client.post("/api/accounts", json={"name": "A"}).json()
    ob = client.post(f"/api/accounts/{a['id']}/onboard", json={"kickoff_date": "2026-08-01"}).json()
    chro = next(p for p in client.get(f"/api/accounts/{a['id']}/onboarding").json()["placeholders"]
                if p["title"] == "CHRO")
    run = client.post("/api/extraction/run", json={
        "account_id": a["id"], "program_id": ob["program_id"],
        "transcript": "Our new VP of IT is Dana Okafor."}).json()
    prop = next(p for p in run["proposals"] if p["mutation_type"] == "fill_placeholder")

    r = client.post(f"/api/extraction/proposals/{prop['id']}/accept",
                    json={"overrides": {"placeholder_person_id": chro["id"]}})
    assert r.status_code == 200
    assert client.get(f"/api/persons/{chro['id']}/card").json()["is_placeholder"] is False


def test_placeholder_fill_will_not_target_another_accounts_placeholder(client):
    a = client.post("/api/accounts", json={"name": "A"}).json()
    b = client.post("/api/accounts", json={"name": "B"}).json()
    client.post(f"/api/accounts/{a['id']}/onboard", json={"kickoff_date": "2026-08-01"})
    ob_b = client.post(f"/api/accounts/{b['id']}/onboard", json={"kickoff_date": "2026-08-01"}).json()
    b_chro = next(p for p in client.get(f"/api/accounts/{b['id']}/onboarding").json()["placeholders"]
                  if p["title"] == "CHRO")

    run = client.post("/api/extraction/run", json={
        "account_id": a["id"], "transcript": "Our new VP of IT is Dana Okafor."}).json()
    prop = next(p for p in run["proposals"] if p["mutation_type"] == "fill_placeholder")
    r = client.post(f"/api/extraction/proposals/{prop['id']}/accept",
                    json={"overrides": {"placeholder_person_id": b_chro["id"]}})
    assert r.status_code == 422 and "different account" in r.json()["detail"]
    assert client.get(f"/api/persons/{b_chro['id']}/card").json()["is_placeholder"] is True


def test_an_accepted_proposal_cannot_then_be_rejected(client):
    """Accepting writes a domain record. Flipping the proposal to 'rejected' afterwards left
    the record in place and made the audit trail claim the operator declined it."""
    a = client.post("/api/accounts", json={"name": "A"}).json()
    run = client.post("/api/extraction/run", json={
        "account_id": a["id"], "transcript": "Retention improved sharply."}).json()
    prop = next(p for p in run["proposals"] if p["mutation_type"] == "create_value_story")
    assert client.post(f"/api/extraction/proposals/{prop['id']}/accept",
                       json={"overrides": {}}).status_code == 200

    r = client.post(f"/api/extraction/proposals/{prop['id']}/reject")
    assert r.status_code == 409 and "already accepted" in r.json()["detail"]
    final = client.get(f"/api/extraction/runs/{run['id']}").json()
    assert next(p for p in final["proposals"] if p["id"] == prop["id"])["status"] == "accepted"


# --- capture + jobs ---------------------------------------------------------------------------
def test_a_labelled_date_does_not_also_emit_a_generic_duplicate(client):
    """"Go live is 2026-10-01" used to yield both "Go Live" and a second unlabelled "Key date",
    so the operator triaged the same fact twice. The 30-second capture rule wins ties."""
    props = client.post("/api/intake/parse", json={"text": "Go live is 2026-10-01."}).json()["proposals"]
    dates = [p for p in props if p["type"] == "key_date"]
    assert len(dates) == 1 and dates[0]["label"] == "Go Live"

    # a genuinely bare date still surfaces
    bare = client.post("/api/intake/parse", json={"text": "2026-10-01"}).json()["proposals"]
    assert [p["label"] for p in bare if p["type"] == "key_date"] == ["Key date"]


def test_one_drain_gives_a_failing_job_exactly_one_attempt(client):
    """run_pending documents that a job left queued after a failure waits for the next pass.
    The `seen` guard was checked AFTER run_next returned, so the handler had already run a
    second time — one drain burned two of three attempts."""
    from app import jobs
    calls = {"n": 0}

    @jobs.register("review_flaky")
    def flaky(conn, payload):
        calls["n"] += 1
        raise RuntimeError("boom")

    job = jobs.enqueue(client.app.state.conn, "review_flaky", max_attempts=3)
    jobs.run_pending(client.app.state.conn)
    assert calls["n"] == 1
    assert jobs.get_job(client.app.state.conn, job["id"])["attempts"] == 1

    jobs.run_pending(client.app.state.conn)          # next pass picks it up again
    assert calls["n"] == 2
    jobs.run_pending(client.app.state.conn)
    assert jobs.get_job(client.app.state.conn, job["id"])["status"] == "failed"   # attempts exhausted
