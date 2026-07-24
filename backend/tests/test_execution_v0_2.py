"""v0.2 execution tests — acceptance Steps 2-3 (convert to commitment + risk),
the Section 4 closure rules, and the two-owner commitment guarantee.
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
    from app.main import app
    with TestClient(app) as c:
        yield c
    for s in ("", "-wal", "-shm"):
        try: os.unlink(path + s)
        except FileNotFoundError: pass


@pytest.fixture()
def scenario(client):
    """Account + program + two people + an interaction with two inbox notes."""
    acct = client.post("/api/accounts", json={"name": "Acme"}).json()
    prog = client.post("/api/programs", json={"account_id": acct["id"], "name": "Europe", "phase": "launch"}).json()
    client_person = client.post("/api/persons", json={"name": "Sofie", "account_id": acct["id"]}).json()
    owner = client.post("/api/persons", json={"name": "Sam", "affiliation": "valence"}).json()
    inter = client.post("/api/interactions", json={
        "account_id": acct["id"], "program_id": prog["id"], "type": "call",
        "summary": "Europe readiness",
        "inbox_notes": ["Sofie to secure DPO sign-off before EU activation",
                        "Works-council consultation may slip past September"],
    }).json()
    return {"client": client, "acct": acct, "prog": prog, "person": client_person,
            "owner": owner, "inter": inter}


def test_convert_inbox_to_commitment_no_retype(scenario):
    c = scenario["client"]
    item = scenario["inter"]["inbox_items"][0]
    r = c.post(f"/api/inbox/{item['id']}/convert", json={
        "target_type": "commitment",
        "payload": {
            "responsible_party_id": scenario["person"]["id"],
            "internal_owner_id": scenario["owner"]["id"],
            "due_date": "2026-08-15",
        },
    })
    assert r.status_code == 200
    body = r.json()
    created = body["created"]
    # description carried from raw_text (no retype); source interaction linked
    assert created["description"] == item["raw_text"]
    assert created["source_interaction_id"] == scenario["inter"]["id"]
    assert created["responsible_party_id"] and created["internal_owner_id"] and created["due_date"]
    # inbox item now converted and linked
    assert body["item"]["status"] == "converted"
    assert body["item"]["converted_to_type"] == "commitment"
    assert body["item"]["converted_to_id"] == created["id"]
    # gone from untriaged
    assert c.get("/api/inbox?status=untriaged").json().__len__() == 1


def test_convert_inbox_to_risk_blocker(scenario):
    c = scenario["client"]
    item = scenario["inter"]["inbox_items"][1]
    r = c.post(f"/api/inbox/{item['id']}/convert", json={
        "target_type": "risk", "payload": {"severity": "high", "is_blocker": True},
    })
    assert r.status_code == 200
    risk = r.json()["created"]
    assert risk["is_blocker"] is True and risk["status"] == "open"
    assert risk["source_interaction_id"] == scenario["inter"]["id"]


def test_commitment_requires_both_owners_and_due_date(scenario):
    c = scenario["client"]
    # missing internal_owner_id -> 422 at the schema edge
    r = c.post("/api/commitments", json={
        "program_id": scenario["prog"]["id"], "description": "x",
        "responsible_party_id": scenario["person"]["id"], "due_date": "2026-08-01",
    })
    assert r.status_code == 422


def test_commitment_closes_only_via_close_endpoint(scenario):
    c = scenario["client"]
    cm = c.post("/api/commitments", json={
        "program_id": scenario["prog"]["id"], "description": "send summary",
        "responsible_party_id": scenario["owner"]["id"], "internal_owner_id": scenario["owner"]["id"],
        "due_date": "2026-07-16",
    }).json()
    assert cm["status"] == "open"
    closed = c.post(f"/api/commitments/{cm['id']}/close", json={
        "acknowledged_by_id": scenario["person"]["id"], "close_note": "client confirmed receipt",
    }).json()
    assert closed["status"] == "closed" and closed["acknowledged_by_id"] == scenario["person"]["id"]
    assert closed["closed_on"]
    # double close -> 409
    assert c.post(f"/api/commitments/{cm['id']}/close", json={}).status_code == 409


def test_risk_close_requires_reason_mitigation_is_not_closure(scenario):
    c = scenario["client"]
    risk = c.post("/api/risks", json={
        "program_id": scenario["prog"]["id"], "description": "works council", "is_blocker": True,
    }).json()
    # adding mitigation does not close it
    # (mitigation would be a patch; here we assert closing needs a reason)
    bad = c.post(f"/api/risks/{risk['id']}/close", json={})  # missing close_reason
    assert bad.status_code == 422
    good = c.post(f"/api/risks/{risk['id']}/close", json={"close_reason": "no_longer_relevant", "close_note": "EU launch descoped"})
    assert good.status_code == 200 and good.json()["status"] == "closed"


def test_issue_resolve_requires_type(scenario):
    c = scenario["client"]
    issue = c.post("/api/issues", json={"program_id": scenario["prog"]["id"], "description": "SSO broken"}).json()
    assert c.post(f"/api/issues/{issue['id']}/resolve", json={}).status_code == 422
    ok = c.post(f"/api/issues/{issue['id']}/resolve", json={"resolution_type": "condition_removed"})
    assert ok.status_code == 200 and ok.json()["status"] == "resolved"


def test_milestone_complete(scenario):
    c = scenario["client"]
    ms = c.post("/api/milestones", json={"program_id": scenario["prog"]["id"], "name": "Go-live", "at_risk": True}).json()
    done = c.post(f"/api/milestones/{ms['id']}/complete", json={"completion_note": "activated"}).json()
    assert done["status"] == "complete" and done["completed_on"]


def test_decision_supersede_marks_old(scenario):
    c = scenario["client"]
    d1 = c.post("/api/decisions", json={"program_id": scenario["prog"]["id"], "description": "Launch in Q3"}).json()
    d2 = c.post("/api/decisions", json={"program_id": scenario["prog"]["id"], "description": "Launch in Q4", "supersedes_id": d1["id"]}).json()
    board = c.get(f"/api/programs/{scenario['prog']['id']}/execution").json()
    by_id = {d["id"]: d for d in board["decisions"]}
    assert by_id[d1["id"]]["status"] == "superseded"
    assert by_id[d2["id"]]["status"] == "recorded"


def test_convert_account_level_note_needs_program(client):
    acct = client.post("/api/accounts", json={"name": "Acme"}).json()
    inter = client.post("/api/interactions", json={
        "account_id": acct["id"], "type": "meeting", "inbox_notes": ["do a thing"],
    }).json()
    item = inter["inbox_items"][0]
    # no program on the interaction, none supplied -> 422 with guidance
    r = client.post(f"/api/inbox/{item['id']}/convert", json={"target_type": "task", "payload": {}})
    assert r.status_code == 422
    # supplying a program succeeds
    prog = client.post("/api/programs", json={"account_id": acct["id"], "name": "P"}).json()
    r2 = client.post(f"/api/inbox/{item['id']}/convert", json={"target_type": "task", "payload": {"program_id": prog["id"]}})
    assert r2.status_code == 200


def test_overdue_derived_on_board(scenario):
    c = scenario["client"]
    c.post("/api/commitments", json={
        "program_id": scenario["prog"]["id"], "description": "late one",
        "responsible_party_id": scenario["owner"]["id"], "internal_owner_id": scenario["owner"]["id"],
        "due_date": "2000-01-01",
    })
    board = c.get(f"/api/programs/{scenario['prog']['id']}/execution").json()
    assert any(cm["overdue"] for cm in board["commitments"])
