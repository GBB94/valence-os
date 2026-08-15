"""Adversarial acceptance tests for RELATIONSHIP-READINESS-SPEC.md RR-0 and RR-1.

These are written to try to make readiness lie: to make it claim a champion it does not have, to
borrow another program's contacts, to read a role default as assessed evidence, to treat a
negotiated target as a baseline, and to resolve a budget-owner conflict by silently picking one.
Each test asserts the honest answer, not merely a non-crash.
"""
import os
import tempfile

import pytest
from fastapi.testclient import TestClient

from conftest import utc_day


@pytest.fixture()
def client():
    fd, path = tempfile.mkstemp(suffix=".sqlite"); os.close(fd)
    os.environ["VALENCE_OS_DB"] = path
    os.environ["VALENCE_OS_WORKER"] = "0"
    from app.main import app
    with TestClient(app) as c:
        yield c
    for suffix in ("", "-wal", "-shm"):
        try: os.unlink(path + suffix)
        except FileNotFoundError: pass


# --- fixture helpers -------------------------------------------------------------------------

def _account(c, name="Northwind Synthetic"):
    return c.post("/api/accounts", json={"name": name}).json()


def _program(c, account_id, name, phase="programmatic"):
    r = c.post("/api/programs", json={"account_id": account_id, "name": name, "phase": phase})
    assert r.status_code == 201, r.text
    return r.json()


def _person(c, account_id, name, title=None):
    r = c.post("/api/persons", json={"name": name, "account_id": account_id,
                                     "affiliation": "client", "title": title})
    assert r.status_code == 201, r.text
    return r.json()


def _role(c, program_id, person_id, role, layer=None):
    body = {"program_id": program_id, "person_id": person_id, "role": role}
    if layer:
        body["layer"] = layer
    r = c.post("/api/stakeholder-roles", json=body)
    assert r.status_code == 201, r.text
    return r.json()


def _touch(c, account_id, person_ids, days_ago=5, program_id=None):
    r = c.post("/api/interactions", json={
        "account_id": account_id, "program_id": program_id,
        "occurred_on": utc_day(-days_ago), "type": "meeting", "summary": "Working session",
        "participant_ids": person_ids, "meaningful_touch": True,
    })
    assert r.status_code == 201, r.text
    return r.json()


def _advocacy(c, person_id, program_id, days_ago=10, kind="advocacy_without_us"):
    r = c.post("/api/advocacy-events", json={
        "person_id": person_id, "program_id": program_id, "kind": kind,
        "occurred_on": utc_day(-days_ago), "note": "Presented the case internally",
    })
    assert r.status_code == 201, r.text
    return r.json()


def _readiness(c, account_id, program_id=None):
    url = f"/api/accounts/{account_id}/readiness"
    if program_id:
        url += f"?program_id={program_id}"
    r = c.get(url)
    assert r.status_code == 200, r.text
    return r.json()


def _pillar(result, key):
    for p in result["pillars"]:
        if p["key"] == key:
            return p
    for entry in result["programs"]:
        for p in entry["pillars"]:
            if p["key"] == key:
                return p
    raise AssertionError(f"pillar {key} not in result")


def _component(pillar, key):
    for c in pillar["components"]:
        if c["key"] == key:
            return c
    raise AssertionError(f"component {key} not in {pillar['key']}: "
                         f"{[c['key'] for c in pillar['components']]}")


# --- §11.1 definitions and registry ------------------------------------------------------------

def test_definitions_are_versioned_and_only_one_live_version_per_key(client):
    body = client.get("/api/readiness/definitions").json()
    keys = [p["key"] for p in body["pillars"]]
    assert keys == ["stakeholder_breadth", "champion_continuity", "executive_sponsorship",
                    "quantified_value", "budget_owner", "active_expansion_plan"]
    assert len(keys) == len(set(keys)), "more than one live version of a pillar key"
    for p in body["pillars"]:
        assert p["version"] >= 1 and p["evaluator_version"] >= 1
        assert p["research_class"] in ("core_hypothesis", "supporting_hypothesis")
        assert p["requirements"], f"{p['key']} has no requirement definitions"


def test_no_composite_score_field_exists_anywhere(client):
    """§2.2 asserts the absence of a score. Assert it by introspection, not by reading the UI."""
    import sqlite3
    from app.db import connect
    conn = connect()
    tables = [r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'readiness%'")]
    assert tables, "readiness definition tables missing"
    banned = ("score", "points", "weight", "rating", "grade", "percent")
    for t in tables:
        for col in (r[1] for r in conn.execute(f"PRAGMA table_info({t})")):
            assert not any(b in col.lower() for b in banned), f"{t}.{col} looks like a score"

    account = _account(client)
    result = _readiness(client, account["id"])
    payload = repr(result).lower()
    for token in ('"score"', "'score'", '"overall"', "'overall'"):
        assert token not in payload, f"response carries {token}"


def test_definition_row_cannot_introduce_an_evaluator(client):
    """§2.3 — a definition configures allowlisted code; it cannot create executable behavior."""
    r = client.post("/api/readiness/definition-upgrades/preview",
                    json={"pillar_key": "stakeholder_breadth", "evaluator_version": 99})
    assert r.status_code == 422
    assert "allowlist" in r.json()["detail"]


def test_unknown_requirement_evaluator_fails_closed_into_partial_coverage(client):
    """A definition pointing at code that does not exist must degrade coverage, not vanish."""
    from app.db import connect
    account = _account(client)
    program = _program(client, account["id"], "Ops enablement")
    conn = connect()
    conn.execute("UPDATE readiness_requirement_definitions SET evaluator_key='nonexistent_eval' "
                 "WHERE key='breadth_engaged_contacts'")
    conn.commit()

    result = _readiness(client, account["id"], program["id"])
    assert result["coverage"]["status"] == "partial"
    assert "nonexistent_eval" in str(result["coverage"])
    breadth = _pillar(result, "stakeholder_breadth")
    failed = _component(breadth, "breadth_engaged_contacts")
    assert failed["state"] == "unknown"
    assert "allowlisted registry" in failed["reason"]


def test_preview_reports_affected_scopes_and_applies_nothing(client):
    account = _account(client)
    program = _program(client, account["id"], "Ops enablement")
    before = client.get("/api/readiness/definitions").json()
    r = client.post("/api/readiness/definition-upgrades/preview",
                    json={"pillar_key": "stakeholder_breadth", "evaluator_version": 1})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["applied"] is False
    scopes = [s["program_id"] for s in body["affected_scopes"]]
    assert program["id"] in scopes
    assert client.get("/api/readiness/definitions").json() == before


# --- §11.2 program scoping ---------------------------------------------------------------------

def test_another_programs_contacts_do_not_satisfy_the_selected_program(client):
    account = _account(client)
    a = _program(client, account["id"], "Program A")
    b = _program(client, account["id"], "Program B")
    for i in range(4):
        person = _person(client, account["id"], f"Contact A{i}")
        _role(client, a["id"], person["id"], "program_owner", layer="operational")
        _touch(client, account["id"], [person["id"]], program_id=a["id"])

    in_a = _pillar(_readiness(client, account["id"], a["id"]), "stakeholder_breadth")
    in_b = _pillar(_readiness(client, account["id"], b["id"]), "stakeholder_breadth")
    assert _component(in_a, "breadth_engaged_contacts")["state"] == "met"
    assert _component(in_b, "breadth_engaged_contacts")["state"] == "unknown", \
        "Program B borrowed Program A's contacts"


def test_champion_validated_in_one_program_is_not_a_champion_in_another(client):
    """The defect `people_core.has_champion_evidence` would introduce: it ignores program."""
    account = _account(client)
    a = _program(client, account["id"], "Program A")
    b = _program(client, account["id"], "Program B")
    person = _person(client, account["id"], "Rowan Vale")
    _role(client, a["id"], person["id"], "champion", layer="operational")
    _role(client, b["id"], person["id"], "champion", layer="operational")
    _advocacy(client, person["id"], a["id"])
    _touch(client, account["id"], [person["id"]], program_id=a["id"])
    _touch(client, account["id"], [person["id"]], program_id=b["id"])

    in_a = _component(_pillar(_readiness(client, account["id"], a["id"]), "champion_continuity"),
                      "champion_primary_validated")
    in_b = _component(_pillar(_readiness(client, account["id"], b["id"]), "champion_continuity"),
                      "champion_primary_validated")
    assert in_a["state"] == "met"
    assert in_b["state"] == "thin", "advocacy leaked across programs"
    assert "coach" in in_b["reason"]


def test_unknown_or_foreign_program_is_an_error_not_an_account_fallback(client):
    account = _account(client)
    other = _account(client, "Other Synthetic")
    foreign = _program(client, other["id"], "Their program")
    assert client.get(f"/api/accounts/{account['id']}/readiness?program_id=missing").status_code == 404
    r = client.get(f"/api/accounts/{account['id']}/readiness?program_id={foreign['id']}")
    assert r.status_code == 404, "a foreign program silently fell back to account scope"


def test_all_program_scope_reports_programs_separately_rather_than_merging(client):
    """Merging would manufacture a `met` that is true of neither program."""
    account = _account(client)
    a = _program(client, account["id"], "Program A")
    b = _program(client, account["id"], "Program B")
    champ = _person(client, account["id"], "Rowan Vale")
    _role(client, a["id"], champ["id"], "champion", layer="operational")
    _advocacy(client, champ["id"], a["id"])
    _touch(client, account["id"], [champ["id"]], program_id=a["id"])

    result = _readiness(client, account["id"])
    by_program = {e["program_id"]: e for e in result["programs"]}
    assert set(by_program) == {a["id"], b["id"]}
    states = {e["program_name"]: next(p["state"] for p in e["pillars"]
                                      if p["key"] == "champion_continuity")
              for e in result["programs"]}
    assert states["Program A"] == "thin"     # champion yes, second thread no
    assert states["Program B"] == "unknown"  # nothing at all
    assert "champion_continuity" not in [p["key"] for p in result["pillars"]], \
        "a program-scoped pillar was reported at account level"


# --- §11.3 state, freshness, and honest gaps ----------------------------------------------------

def test_a_role_defaulted_layer_is_not_layer_evidence(client):
    """Three unassessed people would otherwise span three layers on role defaults alone."""
    account = _account(client)
    program = _program(client, account["id"], "Ops enablement")
    for name, role in [("Ari Bly", "champion"), ("Sam Reyes", "budget_owner"),
                       ("Jo Kestrel", "executive_sponsor")]:
        person = _person(client, account["id"], name)
        _role(client, program["id"], person["id"], role)  # no layer assessed
        _touch(client, account["id"], [person["id"]], program_id=program["id"])

    breadth = _pillar(_readiness(client, account["id"], program["id"]), "stakeholder_breadth")
    spread = _component(breadth, "breadth_layer_spread")
    assert spread["state"] == "thin", "defaulted layers were counted as assessed spread"
    assert spread["provenance"] == "unsupported"
    assert "no assessed stakeholder layer" in spread["reason"]
    assert any("defaulted from role" in e["label"] for e in spread["evidence"])


def test_known_identity_with_stale_engagement_stays_thin_and_stale(client):
    account = _account(client)
    program = _program(client, account["id"], "Ops enablement")
    person = _person(client, account["id"], "Jo Kestrel")
    _role(client, program["id"], person["id"], "executive_sponsor", layer="executive")
    _touch(client, account["id"], [person["id"]], days_ago=400, program_id=program["id"])

    exec_pillar = _pillar(_readiness(client, account["id"], program["id"]), "executive_sponsorship")
    identified = _component(exec_pillar, "exec_identified")
    engaged = _component(exec_pillar, "exec_engaged")
    assert identified["state"] == "met"
    assert engaged["state"] == "thin" and engaged["freshness"] == "stale"
    assert engaged["assessed_through"] == utc_day(-400)
    assert exec_pillar["state"] == "thin", "known identity collapsed to unknown"
    # Only one component in this pillar is dated, so the pillar freshness is that component's.
    assert exec_pillar["freshness"] == "stale"


def test_state_and_freshness_are_independent_fields(client):
    """§3.4 — one fresh component may never make a stale required one look current."""
    account = _account(client)
    program = _program(client, account["id"], "Ops enablement")
    person = _person(client, account["id"], "Jo Kestrel")
    _role(client, program["id"], person["id"], "executive_sponsor", layer="executive")
    _touch(client, account["id"], [person["id"]], days_ago=400, program_id=program["id"])
    pillar = _pillar(_readiness(client, account["id"], program["id"]), "executive_sponsorship")
    freshness = {c["key"]: c["freshness"] for c in pillar["components"]}
    assert freshness["exec_engaged"] == "stale"
    assert "current" not in freshness.values()


def test_unknown_is_distinguished_from_absent(client):
    """Nothing recorded is `unknown` with a stated reason — never a silent `not met`."""
    account = _account(client)
    program = _program(client, account["id"], "Ops enablement")
    result = _readiness(client, account["id"], program["id"])
    for pillar in result["pillars"]:
        if pillar["applicability"] in ("not_applicable", "not_due"):
            continue
        assert pillar["state"] in ("unknown", "thin", "conflicted"), pillar
        assert pillar["reason"], f"{pillar['key']} gave no reason"
        assert pillar["missing"] or pillar["state"] == "conflicted"


def test_phase_applicability_marks_expansion_not_due_rather_than_missing(client):
    account = _account(client)
    program = _program(client, account["id"], "Early program", phase="foundation")
    pillar = _pillar(_readiness(client, account["id"], program["id"]), "active_expansion_plan")
    assert pillar["applicability"] == "not_due"
    assert pillar["state"] != "thin"
    assert "foundation" in pillar["reason"]
    assert pillar["missing"] == []


def test_closed_phase_marks_pillars_not_applicable(client):
    account = _account(client)
    program = _program(client, account["id"], "Wound down", phase="closed")
    result = _readiness(client, account["id"], program["id"])
    breadth = _pillar(result, "stakeholder_breadth")
    assert breadth["applicability"] == "not_applicable"
    assert breadth["state"] == "not_applicable"


# --- pillar-specific traps ---------------------------------------------------------------------

def test_tagged_champion_without_advocacy_reads_as_coach(client):
    account = _account(client)
    program = _program(client, account["id"], "Ops enablement")
    person = _person(client, account["id"], "Ari Bly")
    _role(client, program["id"], person["id"], "champion", layer="operational")
    _touch(client, account["id"], [person["id"]], program_id=program["id"])
    component = _component(
        _pillar(_readiness(client, account["id"], program["id"]), "champion_continuity"),
        "champion_primary_validated")
    assert component["state"] == "thin"
    assert component["provenance"] == "unsupported"
    assert "reads as coach" in component["reason"]


def test_single_thread_dependency_is_named_when_only_one_champion_exists(client):
    account = _account(client)
    program = _program(client, account["id"], "Ops enablement")
    champ = _person(client, account["id"], "Ari Bly")
    _role(client, program["id"], champ["id"], "champion", layer="operational")
    _advocacy(client, champ["id"], program["id"])
    _touch(client, account["id"], [champ["id"]], program_id=program["id"])
    pillar = _pillar(_readiness(client, account["id"], program["id"]), "champion_continuity")
    second = _component(pillar, "champion_second_thread")
    assert second["state"] == "unknown"
    assert "single relationship" in second["reason"]
    assert pillar["state"] == "thin"


def test_early_stage_champion_candidate_is_not_a_second_thread(client):
    """A name on a list is not a relationship: identify/develop stages do not count."""
    account = _account(client)
    program = _program(client, account["id"], "Ops enablement")
    champ = _person(client, account["id"], "Ari Bly")
    _role(client, program["id"], champ["id"], "champion", layer="operational")
    _advocacy(client, champ["id"], program["id"])
    _touch(client, account["id"], [champ["id"]], program_id=program["id"])
    maybe = _person(client, account["id"], "Noor Aldridge")
    r = client.post("/api/champion-candidates", json={
        "person_id": maybe["id"], "program_id": program["id"], "stage": "develop"})
    assert r.status_code == 201, r.text
    _touch(client, account["id"], [maybe["id"]], program_id=program["id"])

    pillar = _pillar(_readiness(client, account["id"], program["id"]), "champion_continuity")
    assert _component(pillar, "champion_second_thread")["state"] == "unknown"


def test_validated_champion_candidate_counts_as_a_second_thread(client):
    account = _account(client)
    program = _program(client, account["id"], "Ops enablement")
    champ = _person(client, account["id"], "Ari Bly")
    _role(client, program["id"], champ["id"], "champion", layer="operational")
    _advocacy(client, champ["id"], program["id"])
    _touch(client, account["id"], [champ["id"]], program_id=program["id"])
    second = _person(client, account["id"], "Noor Aldridge")
    client.post("/api/champion-candidates", json={
        "person_id": second["id"], "program_id": program["id"], "stage": "identify"})
    from app.db import connect
    conn = connect()
    conn.execute("UPDATE champion_candidates SET stage='arm' WHERE person_id=?", (second["id"],))
    conn.commit()
    _touch(client, account["id"], [second["id"]], program_id=program["id"])

    pillar = _pillar(_readiness(client, account["id"], program["id"]), "champion_continuity")
    assert _component(pillar, "champion_second_thread")["state"] == "met"
    assert pillar["state"] == "met"


def test_executive_value_link_is_unknown_until_the_typed_relation_exists(client):
    """§4.3 — free-text similarity is not a link, so the pillar is capped at thin, honestly."""
    account = _account(client)
    program = _program(client, account["id"], "Ops enablement")
    person = _person(client, account["id"], "Jo Kestrel")
    _role(client, program["id"], person["id"], "executive_sponsor", layer="executive")
    _touch(client, account["id"], [person["id"]], program_id=program["id"])
    pillar = _pillar(_readiness(client, account["id"], program["id"]), "executive_sponsorship")
    link = _component(pillar, "exec_value_link")
    assert link["state"] == "unknown"
    assert "RR-3" in link["reason"]
    assert pillar["state"] == "thin", "the pillar claimed met without a value link"


def test_a_negotiated_target_is_not_a_baseline(client):
    account = _account(client)
    program = _program(client, account["id"], "Ops enablement")
    from app.db import connect, new_id, now_utc
    conn = connect()
    definition_id = new_id()
    conn.execute("INSERT INTO metric_definitions (id, name, created_at, updated_at) "
                 "VALUES (?,?,?,?)",
                 (definition_id, "Weekly active reviewers", now_utc(), now_utc()))
    conn.execute(
        "INSERT INTO value_targets (id, account_id, definition_id, target_value, unit, "
        "direction, origin, status, timeframe_start, timeframe_end, created_at, updated_at) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
        (new_id(), account["id"], definition_id, 42.0, "hours saved", "at_least",
         "business_case", "active", utc_day(-90), utc_day(90), now_utc(), now_utc()))
    conn.commit()

    pillar = _pillar(_readiness(client, account["id"], program["id"]), "quantified_value")
    baseline = _component(pillar, "value_baseline_locked")
    assert baseline["state"] == "unknown"
    assert baseline["provenance"] == "unsupported"
    assert "not a pre-deployment measurement" in baseline["reason"]


def test_conflicting_budget_owner_records_report_conflicted_not_a_winner(client):
    account = _account(client)
    program = _program(client, account["id"], "Ops enablement")
    one = _person(client, account["id"], "Sam Reyes")
    two = _person(client, account["id"], "Dana Locke")
    _role(client, program["id"], one["id"], "budget_owner", layer="economic")
    from app.db import connect, new_id, now_utc
    conn = connect()
    conn.execute(
        "INSERT INTO funding_pools (id, account_id, name, kind, owner_person_id, status, "
        "created_at, updated_at) VALUES (?,?,?,?,?,?,?,?)",
        (new_id(), account["id"], "Transformation pool", "transformation_program", two["id"],
         "confirmed", now_utc(), now_utc()))
    conn.commit()

    pillar = _pillar(_readiness(client, account["id"], program["id"]), "budget_owner")
    authority = _component(pillar, "budget_authority_evidence")
    assert authority["state"] == "conflicted"
    assert pillar["state"] == "conflicted"
    labels = " ".join(e["label"] for e in authority["evidence"])
    assert "Sam Reyes" in labels and "Dana Locke" in labels
    assert "reported rather than resolved" in authority["reason"]


def test_every_pillar_result_links_to_the_records_that_decided_it(client):
    """§5.1 — a conclusion with no traversable evidence is an assertion, not an assessment."""
    account = _account(client)
    program = _program(client, account["id"], "Ops enablement")
    person = _person(client, account["id"], "Ari Bly")
    _role(client, program["id"], person["id"], "champion", layer="operational")
    _advocacy(client, person["id"], program["id"])
    _touch(client, account["id"], [person["id"]], program_id=program["id"])

    result = _readiness(client, account["id"], program["id"])
    for pillar in result["pillars"]:
        for component in pillar["components"]:
            if component["state"] in ("met", "conflicted"):
                assert component["evidence"], \
                    f"{pillar['key']}.{component['key']} asserted {component['state']} with no evidence"
                for e in component["evidence"]:
                    assert e["id"] and e["type"] and e["provenance"] in (
                        "confirmed_source", "operator_recorded", "unsupported")


def test_pillar_detail_endpoint_returns_the_same_verdict_as_the_summary(client):
    account = _account(client)
    program = _program(client, account["id"], "Ops enablement")
    summary = _pillar(_readiness(client, account["id"], program["id"]), "stakeholder_breadth")
    detail = client.get(f"/api/accounts/{account['id']}/readiness/stakeholder_breadth"
                        f"?program_id={program['id']}").json()
    assert detail["pillar"]["state"] == summary["state"]
    assert detail["pillar"]["components"] == summary["components"]
    assert client.get(f"/api/accounts/{account['id']}/readiness/no_such_pillar"
                      f"?program_id={program['id']}").status_code == 404


def test_readiness_writes_nothing(client):
    """A projection that mutates is a second source of truth. Prove it does not."""
    from app.db import connect
    account = _account(client)
    program = _program(client, account["id"], "Ops enablement")
    person = _person(client, account["id"], "Ari Bly")
    _role(client, program["id"], person["id"], "champion", layer="operational")
    conn = connect()
    before = conn.execute("SELECT COUNT(*) FROM audit_events").fetchone()[0]
    for _ in range(3):
        _readiness(client, account["id"], program["id"])
        _readiness(client, account["id"])
    client.post("/api/readiness/definition-upgrades/preview",
                json={"pillar_key": "stakeholder_breadth", "evaluator_version": 1})
    assert conn.execute("SELECT COUNT(*) FROM audit_events").fetchone()[0] == before


def test_placeholder_people_never_satisfy_a_condition(client):
    """A placeholder is a gap marker; counting it would convert a known gap into a met condition."""
    from app.db import connect
    account = _account(client)
    program = _program(client, account["id"], "Ops enablement")
    ghost = _person(client, account["id"], "Unknown finance lead")
    conn = connect()
    conn.execute("UPDATE persons SET is_placeholder=1, placeholder_why='not identified yet' "
                 "WHERE id=?", (ghost["id"],))
    conn.commit()
    _role(client, program["id"], ghost["id"], "budget_owner", layer="economic")
    _touch(client, account["id"], [ghost["id"]], program_id=program["id"])

    pillar = _pillar(_readiness(client, account["id"], program["id"]), "budget_owner")
    assert _component(pillar, "budget_authority_evidence")["state"] == "unknown"


def test_account_level_touches_do_not_leak_into_program_breadth(client):
    """§3.1 — a null-program interaction is account-level; only pillars that opt in may use it."""
    account = _account(client)
    program = _program(client, account["id"], "Ops enablement")
    for i in range(4):
        person = _person(client, account["id"], f"Contact {i}")
        _role(client, program["id"], person["id"], "program_owner", layer="operational")
        _touch(client, account["id"], [person["id"]], program_id=None)  # account-level only

    breadth = _pillar(_readiness(client, account["id"], program["id"]), "stakeholder_breadth")
    assert _component(breadth, "breadth_engaged_contacts")["state"] == "unknown"


# --- quantified value and expansion: the paths that need real records ---------------------------

def _campaign_with_locked_baseline(client, account, program, *, cohort="Field operations",
                                   unit="reviews per week", version="1"):
    """Build the only record shape that produces a baseline: a campaign target that locked one."""
    from app.db import connect, new_id, now_utc
    conn = connect()
    now = now_utc()
    ids = {k: new_id() for k in ("definition", "use_case", "partition", "segment", "target",
                                 "campaign", "campaign_target", "baseline", "owner")}
    conn.execute("INSERT INTO metric_definitions (id, name, version, created_at, updated_at) "
                 "VALUES (?,?,?,?,?)",
                 (ids["definition"], "Weekly active reviewers", version, now, now))
    conn.execute("INSERT INTO use_cases (id, name, slug, created_at, updated_at) VALUES (?,?,?,?,?)",
                 (ids["use_case"], "Review throughput", "review-throughput", now, now))
    conn.execute("INSERT INTO population_partitions (id, account_id, created_at, updated_at) "
                 "VALUES (?,?,?,?)", (ids["partition"], account["id"], now, now))
    conn.execute("INSERT INTO population_segments (id, partition_id, account_id, name, "
                 "created_at, updated_at) VALUES (?,?,?,?,?,?)",
                 (ids["segment"], ids["partition"], account["id"], cohort, now, now))
    conn.execute("INSERT INTO value_targets (id, account_id, definition_id, segment_id, "
                 "target_value, unit, direction, origin, status, timeframe_start, timeframe_end, "
                 "created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                 (ids["target"], account["id"], ids["definition"], ids["segment"], 60.0, unit,
                  "at_least", "business_case", "active", utc_day(-120), utc_day(120), now, now))
    conn.execute("INSERT INTO persons (id, name, affiliation, created_at, updated_at) "
                 "VALUES (?,?,?,?,?)", (ids["owner"], "Internal owner", "valence", now, now))
    conn.execute(
        "INSERT INTO adoption_campaigns (id, account_id, program_id, segment_id, use_case_id, "
        "name, target_behavior, hypothesis, planned_start_on, planned_end_on, "
        "internal_owner_person_id, evaluation_design, status, created_at, updated_at) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (ids["campaign"], account["id"], program["id"], ids["segment"], ids["use_case"],
         "Review habit push", "Weekly review", "Prompted reviews raise weekly usage",
         utc_day(-60), utc_day(-10), ids["owner"], "pre_post", "active", now, now))
    conn.execute("INSERT INTO metric_observations (id, definition_id, definition_version, "
                 "program_id, cohort_label, period_label, value, unit, current_through, "
                 "created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                 (ids["baseline"], ids["definition"], version, program["id"], cohort,
                  "Pre-launch", 20.0, unit, utc_day(-70), now, now))
    conn.execute("INSERT INTO adoption_campaign_targets (id, campaign_id, value_target_id, role, "
                 "baseline_observation_id, baseline_locked_on, created_at, updated_at) "
                 "VALUES (?,?,?,?,?,?,?,?)",
                 (ids["campaign_target"], ids["campaign"], ids["target"], "primary",
                  ids["baseline"], utc_day(-65), now, now))
    conn.commit()
    return ids


def _observation(ids, program_id, *, days_ago, value, cohort="Field operations",
                 unit="reviews per week", version="1"):
    from app.db import connect, new_id, now_utc
    conn = connect()
    now = now_utc()
    oid = new_id()
    conn.execute("INSERT INTO metric_observations (id, definition_id, definition_version, "
                 "program_id, cohort_label, period_label, value, unit, current_through, "
                 "created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                 (oid, ids["definition"], version, program_id, cohort, "After", value, unit,
                  utc_day(-days_ago), now, now))
    conn.commit()
    return oid


def test_a_locked_baseline_plus_a_comparable_observation_is_met(client):
    account = _account(client)
    program = _program(client, account["id"], "Ops enablement")
    ids = _campaign_with_locked_baseline(client, account, program)
    _observation(ids, program["id"], days_ago=10, value=34.0)

    pillar = _pillar(_readiness(client, account["id"], program["id"]), "quantified_value")
    assert _component(pillar, "value_baseline_locked")["state"] == "met"
    assert _component(pillar, "value_comparison_observation")["state"] == "met"
    assert pillar["state"] == "met"


def test_an_observation_on_a_different_metric_version_is_not_comparable(client):
    """§4.4 — a redefined metric produces a number, not a comparison. Say which basis differs."""
    account = _account(client)
    program = _program(client, account["id"], "Ops enablement")
    ids = _campaign_with_locked_baseline(client, account, program)
    _observation(ids, program["id"], days_ago=10, value=34.0, version="2")

    comparison = _component(_pillar(_readiness(client, account["id"], program["id"]),
                                    "quantified_value"), "value_comparison_observation")
    assert comparison["state"] == "thin"
    assert comparison["provenance"] == "unsupported"
    assert "metric definition version" in comparison["reason"]


def test_an_observation_on_a_different_cohort_is_not_comparable(client):
    account = _account(client)
    program = _program(client, account["id"], "Ops enablement")
    ids = _campaign_with_locked_baseline(client, account, program)
    _observation(ids, program["id"], days_ago=10, value=34.0, cohort="Head office")

    comparison = _component(_pillar(_readiness(client, account["id"], program["id"]),
                                    "quantified_value"), "value_comparison_observation")
    assert comparison["state"] == "thin"
    assert "cohort differs" in comparison["reason"]


def test_another_programs_observation_is_not_this_programs_after_measurement(client):
    account = _account(client)
    program = _program(client, account["id"], "Ops enablement")
    other = _program(client, account["id"], "Second program")
    ids = _campaign_with_locked_baseline(client, account, program)
    _observation(ids, other["id"], days_ago=10, value=34.0)

    comparison = _component(_pillar(_readiness(client, account["id"], program["id"]),
                                    "quantified_value"), "value_comparison_observation")
    assert comparison["state"] == "unknown", "another program's observation was borrowed"


def test_expansion_without_a_client_sponsor_is_an_internal_hypothesis(client):
    from app.db import connect, new_id, now_utc
    account = _account(client)
    program = _program(client, account["id"], "Ops enablement", phase="expansion")
    conn = connect(); now = now_utc()
    conn.execute("INSERT INTO expansion_opportunities (id, account_id, name, budget_state, "
                 "status, created_at, updated_at) VALUES (?,?,?,?,?,?,?)",
                 (new_id(), account["id"], "Second business unit", "conceptually_supported",
                  "open", now, now))
    conn.commit()

    pillar = _pillar(_readiness(client, account["id"], program["id"]), "active_expansion_plan")
    assert pillar["applicability"] == "required"
    assert _component(pillar, "expansion_opportunity_open")["state"] == "met"
    ownership = _component(pillar, "expansion_client_ownership")
    assert ownership["state"] == "thin"
    assert "internal hypothesis" in ownership["reason"]
    assert _component(pillar, "expansion_dated_next_step")["state"] == "thin"
    budget = _component(pillar, "expansion_budget_state")
    assert budget["state"] == "thin", "conceptually_supported was read as live budget"
    assert "rather than committed money" in budget["reason"]
    assert pillar["state"] == "thin"


def test_account_pillar_takes_the_strongest_applicability_across_live_programs(client):
    """An account-scoped answer must not be weakened by the scope the operator happened to pick.

    There is one budget-owner answer per account. If the account runs a `launch` program (where
    the pillar is optional) alongside an `expansion` one (where it is required), reporting
    `optional` in the all-programs view would hide a required gap behind a scope choice, and the
    compact Overview — which shows only required gaps — would drop it silently.
    """
    account = _account(client)
    _program(client, account["id"], "Coaching pilot", phase="launch")

    launch_only = _pillar(_readiness(client, account["id"]), "budget_owner")
    assert launch_only["applicability"] == "optional"

    expansion = _program(client, account["id"], "Second business unit", phase="expansion")
    both = _pillar(_readiness(client, account["id"]), "budget_owner")
    assert both["applicability"] == "required", "the expansion program's requirement was lost"

    # Narrowing to the launch program still reports that program's own answer.
    assert _pillar(_readiness(client, account["id"], expansion["id"]),
                   "budget_owner")["applicability"] == "required"


def test_account_pillar_not_due_reads_without_a_phase_in_scope(client):
    """`not_due` at account scope means every live program said so — and must still explain itself
    rather than raising on the phase it cannot name."""
    account = _account(client)
    _program(client, account["id"], "Coaching pilot", phase="launch")

    pillar = _pillar(_readiness(client, account["id"]), "active_expansion_plan")
    assert pillar["applicability"] == "not_due"
    assert pillar["reason"] == "Not due during any live program's current phase."
    assert pillar["components"] == [], "a not-due pillar must not be evaluated"
