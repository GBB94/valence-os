"""v0.1 capture-slice tests — the portion of the Stage-0 acceptance script that
Section 9 assigns to v0.1 (Step 1: capture), plus the schema-level guards.
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
    from app.main import app  # imported after env is set
    with TestClient(app) as c:  # triggers lifespan -> migrations
        yield c
    for suffix in ("", "-wal", "-shm"):
        try:
            os.unlink(path + suffix)
        except FileNotFoundError:
            pass


def _account(client, name="Acme Global"):
    return client.post("/api/accounts", json={"name": name}).json()


def _program(client, account_id, name="Rollout"):
    return client.post("/api/programs", json={"account_id": account_id, "name": name, "phase": "launch"}).json()


def test_health(client):
    assert client.get("/api/health").json()["slice"] == "v0.1 capture"


def test_migrations_ran(client):
    # A protected table exists only if migration 0001 applied.
    r = client.get("/api/accounts")
    assert r.status_code == 200


def test_capture_creates_interaction_participants_and_inbox(client):
    acct = _account(client)
    prog = _program(client, acct["id"])
    person = client.post("/api/persons", json={"name": "Dana", "account_id": acct["id"], "title": "CHRO"}).json()

    r = client.post("/api/interactions", json={
        "account_id": acct["id"],
        "program_id": prog["id"],
        "type": "call",
        "summary": "Readiness call",
        "raw_notes": "internal only",
        "participant_ids": [person["id"]],
        "inbox_notes": ["Sofie to secure DPO sign-off", "Works-council may slip"],
    })
    assert r.status_code == 201
    body = r.json()
    assert body["program_id"] == prog["id"]
    assert [p["name"] for p in body["participants"]] == ["Dana"]
    assert len(body["inbox_items"]) == 2
    assert all(i["status"] == "untriaged" for i in body["inbox_items"])

    # Inbox lists both untriaged items with interaction context.
    inbox = client.get("/api/inbox?status=untriaged").json()
    assert len(inbox) == 2
    assert inbox[0]["interaction"]["summary"] == "Readiness call"


def test_account_level_interaction_allows_null_program(client):
    acct = _account(client)
    r = client.post("/api/interactions", json={"account_id": acct["id"], "type": "meeting"})
    assert r.status_code == 201
    assert r.json()["program_id"] is None


def test_program_must_belong_to_account(client):
    a1 = _account(client, "A1")
    a2 = _account(client, "A2")
    prog = _program(client, a2["id"])
    r = client.post("/api/interactions", json={"account_id": a1["id"], "program_id": prog["id"], "type": "call"})
    assert r.status_code == 422


def test_stance_requires_date_and_evidence(client):
    acct = _account(client)
    prog = _program(client, acct["id"])
    person = client.post("/api/persons", json={"name": "Henrik", "account_id": acct["id"]}).json()

    bad = client.post("/api/stakeholder-roles", json={
        "program_id": prog["id"], "person_id": person["id"], "role": "budget_owner", "stance": "skeptic",
    })
    assert bad.status_code == 422

    good = client.post("/api/stakeholder-roles", json={
        "program_id": prog["id"], "person_id": person["id"], "role": "budget_owner",
        "stance": "skeptic", "stance_assessed_on": "2026-07-12", "stance_evidence_note": "Said so on the call.",
    })
    assert good.status_code == 201


def test_dismiss_inbox_item_is_audited_not_deleted(client):
    acct = _account(client)
    inter = client.post("/api/interactions", json={
        "account_id": acct["id"], "type": "call", "inbox_notes": ["a note"],
    }).json()
    item_id = inter["inbox_items"][0]["id"]

    d = client.post(f"/api/inbox/{item_id}/dismiss")
    assert d.status_code == 200
    assert d.json()["status"] == "dismissed"
    # Gone from untriaged, still present under dismissed.
    assert client.get("/api/inbox?status=untriaged").json() == []
    assert len(client.get("/api/inbox?status=dismissed").json()) == 1
    # Double-dismiss is a clean conflict, not a crash.
    assert client.post(f"/api/inbox/{item_id}/dismiss").status_code == 409


def test_no_individual_usage_field_anywhere(client):
    """Trust boundary: no column may exist for a named person's product usage."""
    import sqlite3
    conn = sqlite3.connect(os.environ["VALENCE_OS_DB"])
    tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")]
    banned = ("usage", "activation", "weekly_return", "sessions", "logins", "minutes_used")
    for t in tables:
        cols = [c[1].lower() for c in conn.execute(f"PRAGMA table_info({t})")]
        for col in cols:
            assert not any(b in col for b in banned), f"banned usage-like column {t}.{col}"
    conn.close()
