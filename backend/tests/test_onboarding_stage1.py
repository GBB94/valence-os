"""Phase 3 Stage 1 — onboarding, launch checklists, org-chart placeholders
(PHASE-3-SPEC.md §§1-3). Covers seeding, falling-behind escalation into Today, placeholder
find-by escalation, coverage counting placeholders as exposure (not stale relationships),
convert-preserves-edges, the intake parse approval pattern, and the deck skeleton.
"""
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


def _kickoff(days_ago: int) -> str:
    from app.db import now_utc
    return (date.fromisoformat(now_utc()[:10]) - timedelta(days=days_ago)).isoformat()


@pytest.fixture()
def onboarded(client):
    """An account onboarded with a kickoff 40 days ago (so early items are overdue)."""
    a = client.post("/api/accounts", json={"name": "Northwind"}).json()
    res = client.post(f"/api/accounts/{a['id']}/onboard",
                      json={"kickoff_date": _kickoff(40), "program_name": "Launch",
                            "europe_in_scope": True}).json()
    return {"c": client, "a": a, "pid": res["program_id"], "seed": res}


# --- §1 seeding -------------------------------------------------------------

def test_onboard_seeds_the_full_pack(onboarded):
    seed = onboarded["seed"]["seeded"]
    assert seed["milestones"] == 7
    assert seed["prep_tasks"] == 3
    assert seed["checklist_items"] > 15
    assert seed["placeholders"] == 6          # incl. works-council (europe_in_scope=True)
    board = onboarded["c"].get(f"/api/programs/{onboarded['pid']}/execution").json()
    assert len(board["milestones"]) == 7


def test_europe_flag_gates_works_council_placeholder(client):
    a = client.post("/api/accounts", json={"name": "Domestic"}).json()
    res = client.post(f"/api/accounts/{a['id']}/onboard",
                      json={"kickoff_date": _kickoff(1), "europe_in_scope": False}).json()
    assert res["seeded"]["placeholders"] == 5  # works-council placeholder omitted


def test_reonboarding_a_program_is_conflict(onboarded):
    c, a, pid = onboarded["c"], onboarded["a"], onboarded["pid"]
    r = c.post(f"/api/accounts/{a['id']}/onboard",
               json={"kickoff_date": _kickoff(1), "program_id": pid})
    assert r.status_code == 409


# --- §2 checklist escalation ------------------------------------------------

def test_overdue_checklist_escalates_into_today(onboarded):
    c = onboarded["c"]
    q = c.get("/api/queue").json()
    checklist = [i for i in q["items"] if i["trigger_type"] == "checklist_overdue"]
    assert checklist, "overdue checklist items should surface in Today"
    # first_call items were due at kickoff (40d ago) -> >1wk past -> top 'needs you now' band
    assert any(i["priority"] == 2 for i in checklist)
    assert all("past due" in i["because"] for i in checklist)


def test_marking_a_first_call_question_fills_its_field(onboarded):
    c, a, pid = onboarded["c"], onboarded["a"], onboarded["pid"]
    state = c.get(f"/api/accounts/{a['id']}/onboarding").json()
    q = next(i for i in state["checklist"]["first_call"]
             if i["fills_field"] == "program.success_criteria")
    r = c.patch(f"/api/checklist-items/{q['id']}",
                json={"status": "done", "fill_value": "80% of managers active by day 30"}).json()
    assert r["filled_field"] == "program.success_criteria"
    assert c.get(f"/api/programs/{pid}").json()["success_criteria"] == "80% of managers active by day 30"


# --- §3 placeholders --------------------------------------------------------

def test_placeholder_find_by_escalates_and_is_not_a_stale_relationship(onboarded):
    c = onboarded["c"]
    q = c.get("/api/queue").json()
    ph = [i for i in q["items"] if i["trigger_type"] == "unidentified_placeholder"]
    assert ph, "placeholders past find-by should surface in Today"
    # placeholders must NOT masquerade as overdue relationships (cadence excludes them)
    cadence = [i for i in q["items"] if i["trigger_type"] == "cadence_overdue"]
    assert not cadence


def test_coverage_counts_placeholders_as_exposure_not_relationships(onboarded):
    c, a = onboarded["c"], onboarded["a"]
    cov = c.get(f"/api/accounts/{a['id']}/stakeholder-coverage").json()
    assert cov["placeholder_count"] == 6
    assert cov["vp_plus_total"] == 0   # no REAL senior relationships yet, only placeholders
    assert cov["vp_plus_active"] == 0


def test_placeholder_renders_on_graph_in_unknown_treatment(onboarded):
    c, a = onboarded["c"], onboarded["a"]
    g = c.get(f"/api/accounts/{a['id']}/stakeholder-graph").json()
    ph_nodes = [n for n in g["nodes"] if n["is_placeholder"]]
    assert len(ph_nodes) == 6
    # sized by EXPECTED influence (champion/budget owner are 'high' -> largest)
    assert any(n["expected_influence"] == "high" and n["size"] >= 50 for n in ph_nodes)


def test_convert_placeholder_preserves_edges_and_clears_the_flag(onboarded):
    c, a, pid = onboarded["c"], onboarded["a"], onboarded["pid"]
    state = c.get(f"/api/accounts/{a['id']}/onboarding").json()
    phs = {p["expected_role"]: p for p in state["placeholders"]}
    champ, budget = phs["champion"], phs["budget_owner"]
    # an edge between two placeholders (budget owner reports to champion)
    c.post("/api/relationship-edges", json={"account_id": a["id"], "from_person_id": budget["id"],
                                            "to_person_id": champ["id"], "type": "reports_to"})
    before = c.get(f"/api/accounts/{a['id']}/stakeholder-graph").json()
    assert any(e["source"] == budget["id"] and e["target"] == champ["id"] for e in before["edges"])

    conv = c.post(f"/api/placeholders/{champ['id']}/convert",
                  json={"name": "Dana Okafor", "title": "VP People", "email": "dana@northwind.test"})
    assert conv.status_code == 200 and conv.json()["is_placeholder"] is False

    after = c.get(f"/api/accounts/{a['id']}/stakeholder-graph").json()
    node = next(n for n in after["nodes"] if n["id"] == champ["id"])
    assert node["is_placeholder"] is False and node["name"] == "Dana Okafor"
    assert any(e["source"] == budget["id"] and e["target"] == champ["id"] for e in after["edges"])  # edge preserved
    # converting a non-placeholder is a conflict
    assert c.post(f"/api/placeholders/{champ['id']}/convert", json={"name": "x"}).status_code == 409


# --- §1a intake parse (propose, accept each) --------------------------------

def test_intake_parse_proposes_without_writing_then_accepts(onboarded):
    c, a, pid = onboarded["c"], onboarded["a"], onboarded["pid"]
    notes = ("Met with Priya Anand (VP of Learning), the champion. "
             "They are currently using Ascend as the incumbent. "
             "Go-live target is 2026-10-01. What is the works-council timeline?")
    parsed = c.post("/api/intake/parse", json={"text": notes}).json()["proposals"]
    kinds = {p["type"] for p in parsed}
    assert {"stakeholder", "incumbent", "key_date", "open_question"} <= kinds

    # nothing was written by parsing
    before = c.get("/api/persons").json()
    stk = next(p for p in parsed if p["type"] == "stakeholder")
    assert stk["name"] == "Priya Anand"

    # accept the stakeholder proposal -> a person is created
    r = c.post("/api/intake/accept", json={"account_id": a["id"], "program_id": pid, "proposal": stk})
    assert r.status_code == 201 and r.json()["created_type"] == "person"
    after = c.get("/api/persons").json()
    assert len(after) == len(before) + 1

    # accept the incumbent note -> lands on the account
    inc = next(p for p in parsed if p["type"] == "incumbent")
    c.post("/api/intake/accept", json={"account_id": a["id"], "proposal": inc})
    assert "Ascend" in (c.get(f"/api/accounts/{a['id']}").json()["incumbent_note"] or "")


# --- §1d deck skeleton ------------------------------------------------------

def test_deck_skeleton_pulls_account_data(onboarded):
    c, a, pid = onboarded["c"], onboarded["a"], onboarded["pid"]
    md = c.get(f"/api/accounts/{a['id']}/deck-skeleton", params={"program_id": pid}).json()["markdown"]
    assert "# Kickoff — Northwind" in md
    assert "not yet identified" in md   # placeholders marked, not silently omitted
    assert "{{" not in md               # every template slot filled
