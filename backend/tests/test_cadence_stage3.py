"""Phase 3 Stage 3 — cadence engine, relationship health, coverage analytics
(Comprehensive Spec §§3.6, 3.7, 3.11)."""
import os
import tempfile
from datetime import date, timedelta

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


def _today_minus(n):
    return (date.today() - timedelta(days=n)).isoformat()


@pytest.fixture()
def scene(client):
    a = client.post("/api/accounts", json={"name": "Acme"}).json()
    p = client.post("/api/programs", json={"account_id": a["id"], "name": "Launch", "phase": "launch"}).json()
    person = client.post("/api/persons", json={"name": "Dana Reed", "account_id": a["id"]}).json()
    return {"c": client, "a": a, "p": p, "person": person}


def _role(c, p, person, **kw):
    return c.post("/api/stakeholder-roles", json={"program_id": p["id"], "person_id": person["id"], **kw}).json()


def _card(c, pid):
    return c.get(f"/api/persons/{pid}/card").json()


# --- §3.6 cadence defaults + override ---------------------------------------

def test_manage_closely_for_high_influence_supporter(scene):
    c, p, person = scene["c"], scene["p"], scene["person"]
    role = _role(c, p, person, role="end_user_voice",
                 stance="supporter", stance_assessed_on=_today_minus(1), stance_evidence_note="e")
    c.patch(f"/api/stakeholder-roles/{role['id']}/graph",
            json={"influence": "high", "graph_assessed_on": _today_minus(1), "graph_evidence_note": "e"})
    cad = _card(c, person["id"])["cadence"]
    assert cad["quadrant"] == "manage_closely" and cad["target_days"] == 14


def test_monitor_default_when_unassessed(scene):
    c, p, person = scene["c"], scene["p"], scene["person"]
    _role(c, p, person, role="end_user_voice")
    cad = _card(c, person["id"])["cadence"]
    assert cad["quadrant"] == "monitor" and cad["target_days"] == 90


def test_senior_role_is_floored_to_three_weeks(scene):
    c, p, person = scene["c"], scene["p"], scene["person"]
    _role(c, p, person, role="champion")   # senior, unassessed -> monitor(90) floored to 21
    assert _card(c, person["id"])["cadence"]["target_days"] == 21


def test_per_role_cadence_override(scene):
    c, p, person = scene["c"], scene["p"], scene["person"]
    role = _role(c, p, person, role="other")
    c.patch(f"/api/stakeholder-roles/{role['id']}", json={"cadence_target_days": 7})
    assert _card(c, person["id"])["cadence"]["target_days"] == 7


# --- §3.6 overdue fires into Today with content-carrying suggestion ----------

def test_overdue_cadence_fires_with_content(scene):
    c, p, person = scene["c"], scene["p"], scene["person"]
    _role(c, p, person, role="champion", cares_about="reducing manager turnover")
    q = c.get("/api/queue").json()
    item = next(i for i in q["items"] if i["trigger_type"] == "cadence_overdue" and i["title"].startswith("Dana"))
    assert "Cadence overdue" in item["because"]
    # suggested next touch carries content, not just "ping"
    assert "care about" in item["next_action"] and "reducing manager turnover" in item["next_action"]
    assert "ping" not in item["next_action"].lower()


def test_recent_touch_clears_cadence(scene):
    c, a, p, person = scene["c"], scene["a"], scene["p"], scene["person"]
    _role(c, p, person, role="champion")
    c.post("/api/interactions", json={"account_id": a["id"], "program_id": p["id"],
                                      "occurred_on": _today_minus(0), "type": "meeting",
                                      "participant_ids": [person["id"]], "meaningful_touch": True})
    q = c.get("/api/queue").json()
    assert not any(i["trigger_type"] == "cadence_overdue" and i["title"].startswith("Dana") for i in q["items"])
    assert _card(c, person["id"])["cadence"]["overdue"] is False


# --- §3.7 health panel ------------------------------------------------------

def test_health_panel_shape_and_pending_signals(scene):
    c, p, person = scene["c"], scene["p"], scene["person"]
    _role(c, p, person, role="program_owner")
    h = _card(c, person["id"])["health"]
    assert "recency" in h and "frequency" in h and h["cadence"] is not None
    # reciprocity/attendance are honest unknowns until the comms/calendar adapters connect
    assert h["reciprocity"]["status"] == "unknown" and h["attendance"]["status"] == "unknown"


# --- §3.11 coverage analytics -----------------------------------------------

def test_coverage_reports_cadence_compliance_layer_heat_and_detractors(scene):
    c, a, p, person = scene["c"], scene["a"], scene["p"], scene["person"]
    _role(c, p, person, role="champion")                 # overdue (no touch)
    d = c.post("/api/persons", json={"name": "Rob Blocker", "account_id": a["id"]}).json()
    drole = _role(c, p, d, role="detractor", layer="economic")
    c.patch(f"/api/stakeholder-roles/{drole['id']}/graph",
            json={"influence": "high", "graph_assessed_on": _today_minus(1), "graph_evidence_note": "e"})
    cov = c.get(f"/api/accounts/{a['id']}/stakeholder-coverage").json()
    assert cov["cadence_compliance"] is not None
    assert cov["cadence_overdue_count"] >= 1
    assert isinstance(cov["layer_heat"], dict) and "operational" in cov["layer_heat"]
    assert any(x["name"] == "Rob Blocker" and x["high_influence"] for x in cov["detractors"])
