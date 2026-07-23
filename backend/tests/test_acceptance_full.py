"""The full Stage-0 acceptance script, end to end (Section 9).

A mock call is captured, converted into a commitment and a risk, surfaced in the
attention queue, reflected in the account history, and included correctly in a
generated team update — WITHOUT introducing any new object type.
"""
import os
import tempfile

import pytest
from fastapi.testclient import TestClient

OBJECT_TABLES = {  # the frozen object inventory (excludes infra: schema_migrations, audit, attention, join)
    "accounts", "programs", "persons", "stakeholder_roles", "interactions",
    "capture_inbox_items", "source_references", "tasks", "commitments", "decisions",
    "risks", "issues", "milestones",
}


@pytest.fixture()
def client():
    fd, path = tempfile.mkstemp(suffix=".sqlite")
    os.close(fd)
    os.environ["ACCOUNT_OS_DB"] = path
    from app.main import app
    with TestClient(app) as c:
        c._db_path = path
        yield c
    for s in ("", "-wal", "-shm"):
        try: os.unlink(path + s)
        except FileNotFoundError: pass


def _tables(path):
    import sqlite3
    conn = sqlite3.connect(path)
    t = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    conn.close()
    return t


def test_full_acceptance_script(client):
    tables_before = _tables(client._db_path)

    # setup
    acct = client.post("/api/accounts", json={"name": "Acme Ag"}).json()
    prog = client.post("/api/programs", json={"account_id": acct["id"], "name": "Europe", "phase": "launch"}).json()
    sofie = client.post("/api/persons", json={"name": "Sofie", "account_id": acct["id"]}).json()
    sam = client.post("/api/persons", json={"name": "Sam", "affiliation": "valence"}).json()

    # STEP 1 — capture a call with two ambiguous notes, plus internal-only raw notes
    inter = client.post("/api/interactions", json={
        "account_id": acct["id"], "program_id": prog["id"], "type": "call",
        "summary": "Europe readiness call",
        "raw_notes": "SECRET-INTERNAL-NOTE do not broadcast",
        "participant_ids": [sofie["id"], sam["id"]],
        "inbox_notes": ["Sofie to secure DPO sign-off before EU activation",
                        "Works-council consultation may slip past September"],
    }).json()
    ib1, ib2 = inter["inbox_items"][0]["id"], inter["inbox_items"][1]["id"]

    # STEP 2 — convert note 1 -> commitment (both owners, due date), no retype
    cm = client.post(f"/api/inbox/{ib1}/convert", json={
        "target_type": "commitment",
        "payload": {"responsible_party_id": sofie["id"], "internal_owner_id": sam["id"], "due_date": "2000-01-01"},
    }).json()["created"]
    assert cm["source_interaction_id"] == inter["id"]

    # STEP 3 — convert note 2 -> risk (blocker)
    risk = client.post(f"/api/inbox/{ib2}/convert", json={
        "target_type": "risk", "payload": {"is_blocker": True, "severity": "high"},
    }).json()["created"]

    # STEP 4 — both surface in the attention queue (blocker now; commitment overdue via 2000 due date)
    q = client.get("/api/queue").json()
    keys = {i["key"] for i in q["items"]}
    assert f"active_blocker:risk:{risk['id']}" in keys
    assert f"overdue_commitment:commitment:{cm['id']}" in keys
    assert all(i["because"] for i in q["items"])  # every item explains itself

    # STEP 5 — reflected in account history with back-references and derived last-touch
    hist = client.get(f"/api/accounts/{acct['id']}/history").json()
    top = hist["interactions"][0]
    created_types = {r["type"] for r in top["created_records"]}
    assert {"commitment", "risk"} <= created_types
    assert "Sofie" in [p["name"] for p in top["participants"]]

    # STEP 6 — included correctly in the team update, internal-only excluded BY CONSTRUCTION
    tu = client.get("/api/team-update").json()
    md = tu["markdown"]
    assert "SECRET-INTERNAL-NOTE" not in md                 # raw notes never leak
    assert "Sofie to secure DPO sign-off" in md             # the new commitment appears
    assert "Works-council consultation may slip" in md      # the new blocker appears
    assert tu["stamp"]["data_current_through"]              # freshness-stamped
    # no stakeholder stance/evidence text anywhere in the output
    assert "supporter" not in md and "skeptic" not in md

    # INVARIANT — no new object type introduced anywhere in the flow
    assert _tables(client._db_path) == tables_before
    assert OBJECT_TABLES <= tables_before


def test_history_filters_by_person(client):
    acct = client.post("/api/accounts", json={"name": "Acme"}).json()
    prog = client.post("/api/programs", json={"account_id": acct["id"], "name": "P"}).json()
    a = client.post("/api/persons", json={"name": "Ann", "account_id": acct["id"]}).json()
    b = client.post("/api/persons", json={"name": "Bo", "account_id": acct["id"]}).json()
    client.post("/api/interactions", json={"account_id": acct["id"], "program_id": prog["id"], "type": "call", "participant_ids": [a["id"]]})
    client.post("/api/interactions", json={"account_id": acct["id"], "program_id": prog["id"], "type": "call", "participant_ids": [b["id"]]})
    only_ann = client.get(f"/api/accounts/{acct['id']}/history?person_id={a['id']}").json()
    assert len(only_ann["interactions"]) == 1


def test_team_update_empty_is_clean(client):
    client.post("/api/accounts", json={"name": "Quiet Co"})
    tu = client.get("/api/team-update").json()
    assert tu["sections"] == []
    assert "Nothing to report" in tu["markdown"]
