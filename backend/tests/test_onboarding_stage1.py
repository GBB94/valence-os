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

def test_onboard_seeds_one_merged_standard(onboarded):
    """Migration 0051. Three lists claimed to be the standard; twelve items were duplicates.

    The counts are asserted exactly, not as a floor, because the point of the merge is that each
    piece of standard work appears once. A `> 15` here is what let the old checklist grow a second
    copy of the budget owner and a third copy of the launch milestones without a test noticing.
    """
    seed = onboarded["seed"]["seeded"]
    assert seed["milestones"] == 7            # deployment events
    assert seed["prep_tasks"] == 3            # back-scheduled from kickoff
    assert seed["gate_items"] == 8            # operational setup, incl. works council (Europe)
    assert seed["plan_requirements"] == 8     # relationship conditions (enterprise-launch v3)
    assert "checklist_items" not in seed      # the third list is not seeded any more
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

def _gates(c, pid):
    return c.get(f"/api/programs/{pid}/delivery").json()["phase_gates"]


def _gate_items(c, pid):
    return [it for g in _gates(c, pid) for it in g["items"]]


def test_overdue_setup_escalates_into_today(onboarded):
    """The escalation moved with the items; it did not go away.

    Migration 0051 seeds gate items where it used to seed checklist items. Had the trigger not moved
    with them, an operational step could sit a month past due and Today would say nothing — the
    merge would have deleted a behaviour while claiming to consolidate one.
    """
    c = onboarded["c"]
    q = c.get("/api/queue").json()
    overdue = [i for i in q["items"] if i["trigger_type"] == "gate_item_overdue"]
    assert overdue, "overdue gate items should surface in Today"
    # foundation items were due at kickoff (40d ago) -> >1wk past -> top 'needs you now' band
    assert any(i["priority"] == 2 for i in overdue)
    assert all("past due" in i["because"] for i in overdue)


def test_a_passed_gate_stops_arguing_with_the_operator_who_passed_it(onboarded):
    """A settled gate's items do not come back as overdue work."""
    c, pid = onboarded["c"], onboarded["pid"]
    gate_id = _gates(c, pid)[0]["id"]
    before = {i["object_id"] for i in c.get("/api/queue").json()["items"]
              if i["trigger_type"] == "gate_item_overdue"}
    assert before
    c.post(f"/api/phase-gates/{gate_id}/waive", json={"waiver_reason": "Handled off-platform."})
    after = {i["object_id"] for i in c.get("/api/queue").json()["items"]
             if i["trigger_type"] == "gate_item_overdue"}
    assert after < before


def test_marking_a_setup_question_fills_its_field(onboarded):
    """§1e survives the merge: the answer lands in the field, not just a tick."""
    c, pid = onboarded["c"], onboarded["pid"]
    item = next(i for i in _gate_items(c, pid)
                if i["fills_field"] == "program.success_criteria")
    r = c.patch(f"/api/gate-items/{item['id']}",
                json={"complete": True, "fill_value": "80% of managers active by day 30"}).json()
    assert r["filled_field"] == "program.success_criteria"
    assert c.get(f"/api/programs/{pid}").json()["success_criteria"] == "80% of managers active by day 30"


def test_a_tick_alone_writes_nothing_but_the_tick(onboarded):
    """No value is ever inferred from a completion — `fills_field` is not a write trigger."""
    c, pid = onboarded["c"], onboarded["pid"]
    item = next(i for i in _gate_items(c, pid)
                if i["fills_field"] == "program.success_criteria")
    c.patch(f"/api/gate-items/{item['id']}", json={"complete": True})
    assert c.get(f"/api/programs/{pid}").json()["success_criteria"] in (None, "")


def test_pushing_the_date_is_a_real_option(onboarded):
    """The queue offers "push the date" as one of three moves, so the date has to be pushable."""
    c, pid = onboarded["c"], onboarded["pid"]
    item = next(i for i in _gate_items(c, pid) if i["due_date"])
    later = _kickoff(-30)
    c.patch(f"/api/gate-items/{item['id']}", json={"due_date": later})
    moved = next(i for i in _gate_items(c, pid) if i["id"] == item["id"])
    assert moved["due_date"] == later
    assert moved["complete"] == 0
    assert not any(i["object_id"] == item["id"] for i in c.get("/api/queue").json()["items"])


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
