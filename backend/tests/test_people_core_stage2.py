"""Phase 3 Stage 2 — People module core (Comprehensive Spec §§3.1-3.2, 3.10).
Layer model, widened role taxonomy, evidence-enforced coach-vs-champion, and the person card.
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


@pytest.fixture()
def scene(client):
    a = client.post("/api/accounts", json={"name": "Acme"}).json()
    p = client.post("/api/programs", json={"account_id": a["id"], "name": "Launch", "phase": "launch"}).json()
    person = client.post("/api/persons", json={"name": "Dana Reed", "account_id": a["id"], "title": "VP Finance"}).json()
    return {"c": client, "a": a, "p": p, "person": person}


def _role(c, p, person, **kw):
    body = {"program_id": p["id"], "person_id": person["id"], **kw}
    r = c.post("/api/stakeholder-roles", json=body)
    assert r.status_code == 201, r.text
    return r.json()


# --- §3.2 taxonomy ----------------------------------------------------------

def test_taxonomy_exposes_layers_and_full_committee(client):
    t = client.get("/api/people/taxonomy").json()
    assert set(t["layers"]) == {"executive", "economic", "operational", "technical_gating", "user_advocate"}
    for r in ("financial_gatekeeper", "technical_evaluator", "coach", "detractor", "executive_sponsor"):
        assert r in t["roles"]
    assert t["default_layer_by_role"]["financial_gatekeeper"] == "economic"


def test_new_committee_role_and_layer_accepted(scene):
    c, p, person = scene["c"], scene["p"], scene["person"]
    role = _role(c, p, person, role="technical_evaluator")
    g = c.get(f"/api/accounts/{scene['a']['id']}/stakeholder-graph").json()
    node = next(n for n in g["nodes"] if n["id"] == person["id"])
    assert node["role"] == "technical_evaluator"
    assert node["layer"] == "technical_gating"   # resolved from role default when unset


def test_explicit_layer_overrides_default(scene):
    c, p, person = scene["c"], scene["p"], scene["person"]
    _role(c, p, person, role="champion", layer="executive")
    g = c.get(f"/api/accounts/{scene['a']['id']}/stakeholder-graph").json()
    assert next(n for n in g["nodes"] if n["id"] == person["id"])["layer"] == "executive"


# --- §3.2 coach-vs-champion, enforced by evidence ---------------------------

def test_champion_without_advocacy_reads_as_coach(scene):
    c, p, person = scene["c"], scene["p"], scene["person"]
    _role(c, p, person, role="champion")
    card = c.get(f"/api/persons/{person['id']}/card").json()
    assert card["roles"][0]["role"] == "champion"
    assert card["roles"][0]["effective_role"] == "coach"
    assert "advocacy without us" in card["roles"][0]["coach_reason"]

    # log an advocacy-without-us event -> now reads as champion
    c.post("/api/advocacy-events", json={"person_id": person["id"], "kind": "advocacy_without_us",
                                         "occurred_on": "2026-07-01", "note": "Pitched us in the CFO staff meeting"})
    card2 = c.get(f"/api/persons/{person['id']}/card").json()
    assert card2["roles"][0]["effective_role"] == "champion" and card2["roles"][0]["coach_reason"] is None
    # the graph reflects the same evidence gate
    g = c.get(f"/api/accounts/{scene['a']['id']}/stakeholder-graph").json()
    assert next(n for n in g["nodes"] if n["id"] == person["id"])["effective_role"] == "champion"


# --- §3.10 person card ------------------------------------------------------

def test_card_aggregates_roles_commitments_and_stance_trajectory(scene):
    c, a, p, person = scene["c"], scene["a"], scene["p"], scene["person"]
    role = _role(c, p, person, role="budget_owner",
                 stance="skeptic", stance_assessed_on="2026-06-01", stance_evidence_note="pushed back on price")
    # a stance change is captured as trajectory (reconstructed from the audit log)
    c.patch(f"/api/stakeholder-roles/{role['id']}",
            json={"stance": "supporter", "stance_assessed_on": "2026-07-01", "stance_evidence_note": "approved the pilot"})
    # an open commitment they owe
    owner = c.post("/api/persons", json={"name": "Sam", "affiliation": "valence"}).json()
    c.post("/api/commitments", json={"program_id": p["id"], "description": "send DPA", "responsible_party_id": person["id"],
                                     "internal_owner_id": owner["id"], "due_date": "2026-08-01"})
    card = c.get(f"/api/persons/{person['id']}/card").json()
    assert card["name"] == "Dana Reed" and card["title"] == "VP Finance"
    assert card["roles"][0]["layer"] == "economic"
    stances = [s["stance"] for s in card["stance_trajectory"]]
    assert stances == ["skeptic", "supporter"]
    assert any(x["direction"] == "theirs" and "DPA" in x["description"] for x in card["open_commitments"])


def test_patch_stance_requires_date_and_evidence(scene):
    c, p, person = scene["c"], scene["p"], scene["person"]
    role = _role(c, p, person, role="program_owner")
    assert c.patch(f"/api/stakeholder-roles/{role['id']}", json={"stance": "supporter"}).status_code == 422


def test_person_card_carries_professional_fields_only(scene):
    c, person = scene["c"], scene["person"]
    c.patch(f"/api/persons/{person['id']}",
            json={"comms_preference": "prefers async, email over calls", "metric_judged_on": "manager activation rate"})
    card = c.get(f"/api/persons/{person['id']}/card").json()
    assert card["comms_preference"] == "prefers async, email over calls"
    assert card["metric_judged_on"] == "manager activation rate"


def test_card_404_for_unknown_person(client):
    assert client.get("/api/persons/nope/card").status_code == 404
