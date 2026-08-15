"""Acceptance tests for ACCOUNT-PATH-SPEC.md Slice 5 — relationships, evidence, and advancement.

These are written to try to make a relationship do more than it is entitled to do: to let an open
Task prove the condition it was created to advance, to let a requirement cite the suggestion it
produced, to let a document of the wrong kind move a state, to let a retraction quietly leave the
old answer standing, to let an override or a waiver look like completion afterwards, and to let a
gate claim credit for work nothing ever linked to it. Each test asserts the honest answer.
"""
import json
import os
import sqlite3
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
        c.db_path = path
        yield c
    for suffix in ("", "-wal", "-shm"):
        try: os.unlink(path + suffix)
        except FileNotFoundError: pass


def _sql(c, statement, params=()):
    conn = sqlite3.connect(c.db_path)
    try:
        conn.row_factory = sqlite3.Row
        with conn:
            cur = conn.execute(statement, params)
            return [dict(r) for r in cur.fetchall()]
    finally:
        conn.close()


# --- fixture helpers -------------------------------------------------------------------------

def _account(c, name="Northwind Synthetic"):
    r = c.post("/api/accounts", json={"name": name})
    assert r.status_code == 201, r.text
    return r.json()


def _program(c, account_id, name, phase="launch"):
    r = c.post("/api/programs", json={"account_id": account_id, "name": name, "phase": phase})
    assert r.status_code == 201, r.text
    return r.json()


def _person(c, account_id, name, affiliation="client"):
    r = c.post("/api/persons", json={
        "name": name, "affiliation": affiliation,
        "account_id": None if affiliation == "valence" else account_id,
    })
    assert r.status_code == 201, r.text
    return r.json()


def _task(c, program_id, description, **kw):
    r = c.post("/api/tasks", json={"program_id": program_id, "description": description, **kw})
    assert r.status_code == 201, r.text
    return r.json()


def _commitment(c, account_id, responsible_id, owner_id, description, due_date, **kw):
    r = c.post("/api/commitments", json={
        "account_id": account_id, "description": description,
        "responsible_party_id": responsible_id, "internal_owner_id": owner_id,
        "due_date": due_date, **kw,
    })
    assert r.status_code == 201, r.text
    return r.json()


def _milestone(c, program_id, name, **kw):
    r = c.post("/api/milestones", json={"program_id": program_id, "name": name, **kw})
    assert r.status_code == 201, r.text
    return r.json()


def _gate(c, program_id, name, gates_phase=None, items=()):
    body = {"program_id": program_id, "name": name, "items": list(items)}
    if gates_phase:
        body["gates_phase"] = gates_phase
    r = c.post("/api/phase-gates", json=body)
    assert r.status_code in (200, 201), r.text
    return r.json()


def _launch(c, account_id, program_id, anchor="2026-07-01", version=1, **kw):
    r = c.post(f"/api/accounts/{account_id}/plan-instances", json={
        "playbook_key": "enterprise-launch", "playbook_version": version,
        "program_id": program_id, "anchor_type": "kickoff", "anchor_date": anchor, **kw})
    assert r.status_code == 200, r.text
    return r.json()


def _instances(c, account_id, program_id=None):
    url = f"/api/accounts/{account_id}/plan-instances"
    if program_id:
        url += f"?program_id={program_id}"
    payload = c.get(url).json()
    out = {}
    for plan in payload.get("plans", []):
        for instance in plan.get("instances", []):
            out[instance["requirement_key"]] = instance
    return out


def _readiness(c, account_id, program_id=None):
    url = f"/api/accounts/{account_id}/readiness"
    if program_id:
        url += f"?program_id={program_id}"
    r = c.get(url)
    assert r.status_code == 200, r.text
    return r.json()


def _component(readiness, requirement_key):
    for scope in [readiness] + readiness.get("programs", []):
        for pillar in scope.get("pillars", []):
            for component in pillar.get("components", []):
                if component.get("definition_key") == requirement_key:
                    return pillar, component
    raise AssertionError(f"{requirement_key} not found in readiness")


def _phase_readiness(c, program_id, **params):
    r = c.get(f"/api/programs/{program_id}/phase-readiness", params=params)
    assert r.status_code == 200, r.text
    return r.json()


def _link(c, instance_id, expect=200, **body):
    r = c.post(f"/api/plan-instances/{instance_id}/action-links", json=body)
    assert r.status_code == expect, r.text
    return r.json()


def _attach(c, instance_id, expect=200, **body):
    r = c.post(f"/api/plan-instances/{instance_id}/evidence", json=body)
    assert r.status_code == expect, r.text
    return r.json()


def _base(c, phase="launch"):
    """An account with one program, a launch plan, and a plan instance to hang links on."""
    account = _account(c)
    program = _program(c, account["id"], "Support Deflection", phase=phase)
    _launch(c, account["id"], program["id"])
    return account, program, _instances(c, account["id"], program["id"])


# --- §15.10.1 typed relationship scope and uniqueness -------------------------------------------

def test_a_link_cannot_reach_across_accounts(client):
    """The scope check is the whole reason these tables are typed rather than polymorphic."""
    account, program, instances = _base(client)
    other = _account(client, "Southwind Synthetic")
    other_program = _program(client, other["id"], "Other deployment")
    foreign = _task(client, other_program["id"], "Work on the other account")

    instance = instances["exec_identified"]
    r = client.post(f"/api/plan-instances/{instance['id']}/action-links",
                    json={"task_id": foreign["id"]})
    assert r.status_code == 422
    assert "account" in r.json()["detail"].lower()


def test_a_program_scoped_requirement_rejects_another_programs_action(client):
    """Same account, wrong program. A requirement scheduled for one deployment cannot be
    advanced by work belonging to a different one, or the plan stops meaning anything."""
    account, program, instances = _base(client)
    sibling = _program(client, account["id"], "Second deployment")
    sibling_task = _task(client, sibling["id"], "Sibling programme work")

    instance = instances["exec_identified"]
    assert instance["program_id"] == program["id"]
    r = client.post(f"/api/plan-instances/{instance['id']}/action-links",
                    json={"task_id": sibling_task["id"]})
    assert r.status_code == 422
    assert "program" in r.json()["detail"].lower()


def test_one_active_identical_relationship_and_no_more(client):
    """Recording the same relationship twice is idempotent, not an error and not a duplicate.

    A different relation between the same two records is a different fact, so it is allowed:
    an action can advance one requirement and block another, and saying so is not a duplicate.
    """
    account, program, instances = _base(client)
    instance = instances["exec_identified"]
    task = _task(client, program["id"], "Confirm the executive sponsor")

    first = _link(client, instance["id"], task_id=task["id"], relation="advances")
    assert first["created"] is True
    again = _link(client, instance["id"], task_id=task["id"], relation="advances")
    assert again["created"] is False
    assert again["link"]["id"] == first["link"]["id"]

    other = _link(client, instance["id"], task_id=task["id"], relation="blocks")
    assert other["created"] is True and other["link"]["id"] != first["link"]["id"]

    rows = _sql(client, "SELECT relation FROM readiness_requirement_action_links "
                        "WHERE plan_instance_id = ? AND archived = 0", (instance["id"],))
    assert sorted(r["relation"] for r in rows) == ["advances", "blocks"]


def test_a_link_needs_exactly_one_action_and_a_known_relation(client):
    account, program, instances = _base(client)
    instance = instances["exec_identified"]
    task = _task(client, program["id"], "Confirm the executive sponsor")
    person = _person(client, account["id"], "Sponsor Contact")
    owner = _person(client, account["id"], "Internal Owner", affiliation="valence")
    commitment = _commitment(client, account["id"], person["id"], owner["id"],
                             "Share the sponsor briefing", utc_day(7),
                             program_id=program["id"], commitment_class="client")

    assert client.post(f"/api/plan-instances/{instance['id']}/action-links",
                       json={}).status_code == 422
    assert client.post(f"/api/plan-instances/{instance['id']}/action-links",
                       json={"task_id": task["id"],
                             "commitment_id": commitment["id"]}).status_code == 422
    assert client.post(f"/api/plan-instances/{instance['id']}/action-links",
                       json={"task_id": task["id"], "relation": "supports"}).status_code == 422


def test_an_archived_action_cannot_be_linked(client):
    account, program, instances = _base(client)
    instance = instances["exec_identified"]
    task = _task(client, program["id"], "Work that was archived")
    # Tasks have no HTTP archive route; the soft-delete columns are what the link check reads.
    _sql(client, "UPDATE tasks SET archived = 1, archived_at = datetime('now') WHERE id = ?",
         (task["id"],))

    r = client.post(f"/api/plan-instances/{instance['id']}/action-links",
                    json={"task_id": task["id"]})
    assert r.status_code == 422


# --- §15.10.2 link archival and history ---------------------------------------------------------

def test_archiving_a_link_preserves_it_and_frees_the_slot(client):
    """§15.2 — archival, never deletion. A link that influenced a gate stays readable after it
    stops applying, and a new identical link is a new row rather than a resurrection."""
    account, program, instances = _base(client)
    instance = instances["exec_identified"]
    task = _task(client, program["id"], "Confirm the executive sponsor")
    link = _link(client, instance["id"], task_id=task["id"])["link"]

    assert client.post(f"/api/action-links/{link['id']}/archive",
                       json={"reason": "short"}).status_code == 422
    archived = client.post(f"/api/action-links/{link['id']}/archive",
                           json={"reason": "The sponsor thread moved to a different task"})
    assert archived.status_code == 200, archived.text

    rows = _sql(client, "SELECT * FROM readiness_requirement_action_links WHERE id = ?",
                (link["id"],))
    assert len(rows) == 1 and rows[0]["archived"] == 1
    assert rows[0]["archived_reason"] == "The sponsor thread moved to a different task"

    live = client.get(f"/api/plan-instances/{instance['id']}/links").json()
    assert live["actions"] == []

    replacement = _link(client, instance["id"], task_id=task["id"])
    assert replacement["created"] is True and replacement["link"]["id"] != link["id"]


# --- §15.10.3 evaluators and evaluator versions -------------------------------------------------
#
# The generic §15.4 evaluators are configured by definition rows, and no shipped definition uses
# one yet (adding one would assert a new readiness condition for every account, which is a product
# decision rather than an implementation one). These tests therefore author their own definitions,
# which is exactly the governance path the registry exists to serve.

_HARNESS_PLAYBOOK = "slice5-harness"


def _define(c, key, evaluator_key, config, *, pillar="quantified_value", version=1,
            evaluator_version=1, evidence_types=(), scope="program"):
    _sql(c, """
        INSERT INTO readiness_requirement_definitions
          (id,key,version,pillar_key,pillar_version,label,purpose,definition_of_done,
           default_scope,evaluator_key,evaluator_version,evaluator_config_json,
           allowed_evidence_types_json,freshness_policy_json,phase_applicability_json,
           suggested_action_json,active_from,governance_note,created_at,updated_at)
        VALUES (?,?,?,?,1,?,'Test harness definition.','Test harness condition.',
                ?,?,?,?,?,'{}','{}',NULL,'2026-08-01','Authored by the Slice 5 tests.',
                datetime('now'),datetime('now'))
    """, (f"rrd-{key}-{version}", key, version, pillar, key.replace("_", " ").title(),
          scope, evaluator_key, evaluator_version, json.dumps(config),
          json.dumps(list(evidence_types))))
    return key


def _harness(c, entries, playbook_version=1):
    """A playbook whose entries are exactly the definitions a test just authored."""
    _sql(c, """
        INSERT INTO readiness_playbook_definitions
          (id,key,version,label,purpose,kind,default_anchor,allowed_anchors_json,
           default_scope,active_from,governance_note,created_at,updated_at)
        VALUES (?,?,?,'Slice 5 harness','Exercises the generic evaluators.','other','kickoff',
                '["kickoff"]','program','2026-08-01','Authored by the Slice 5 tests.',
                datetime('now'),datetime('now'))
    """, (f"rpb-harness-{playbook_version}", _HARNESS_PLAYBOOK, playbook_version))
    for order, (key, requirement_version, necessity) in enumerate(entries, start=1):
        _sql(c, """
            INSERT INTO readiness_playbook_entries
              (id,playbook_key,playbook_version,requirement_key,requirement_version,display_order,
               necessity,offset_days,note,created_at,updated_at)
            VALUES (?,?,?,?,?,?,?,30,NULL,datetime('now'),datetime('now'))
        """, (f"rpe-harness-{playbook_version}-{order}", _HARNESS_PLAYBOOK, playbook_version,
              key, requirement_version, order * 10, necessity))


def _instantiate_harness(c, account_id, program_id, anchor="2026-07-01", playbook_version=1):
    r = c.post(f"/api/accounts/{account_id}/plan-instances", json={
        "playbook_key": _HARNESS_PLAYBOOK, "playbook_version": playbook_version,
        "program_id": program_id, "anchor_type": "kickoff", "anchor_date": anchor})
    assert r.status_code == 200, r.text
    return _instances(c, account_id, program_id)


def test_field_present_reads_only_allowlisted_columns(client):
    """A definition configures an evaluator; it does not get to name an arbitrary column.

    Reading whatever a configuration asked for would turn a requirement into a free query over the
    schema, including columns that exist for reasons nothing to do with readiness.
    """
    account = _account(client)
    program = _program(client, account["id"], "Support Deflection")
    _define(client, "harness_scope_named", "field_present",
            {"scope": "program", "fields": ["success_criteria"]})
    _define(client, "harness_scope_forbidden", "field_present",
            {"scope": "program", "fields": ["renewal_date"]})
    _harness(client, [("harness_scope_named", 1, "required"),
                      ("harness_scope_forbidden", 1, "required")])
    _instantiate_harness(client, account["id"], program["id"])

    readiness = _readiness(client, account["id"], program["id"])
    _, named = _component(readiness, "harness_scope_named")
    _, forbidden = _component(readiness, "harness_scope_forbidden")
    assert named["state"] in ("thin", "unknown")       # the column exists and is empty
    assert forbidden["state"] == "unknown"
    assert "renewal_date" in forbidden["reason"]

    client.patch(f"/api/programs/{program['id']}",
                 json={"success_criteria": "Two cohorts live by the end of the quarter."})
    readiness = _readiness(client, account["id"], program["id"])
    _, named = _component(readiness, "harness_scope_named")
    assert named["state"] == "met"
    # Filling an allowlisted field never rescues the one that was never readable.
    _, forbidden = _component(readiness, "harness_scope_forbidden")
    assert forbidden["state"] == "unknown"


def test_record_closed_does_not_count_a_cancelled_task(client):
    """`record_closed` asks for governed closure that proves the condition. Cancelling a task is
    a governed closure of the task and proof of nothing at all."""
    account = _account(client)
    program = _program(client, account["id"], "Support Deflection")
    _define(client, "harness_closed_action", "record_closed", {"record_type": "task"})
    _harness(client, [("harness_closed_action", 1, "required")])
    instances = _instantiate_harness(client, account["id"], program["id"])
    instance = instances["harness_closed_action"]

    task = _task(client, program["id"], "Run the readiness workshop")
    _link(client, instance["id"], task_id=task["id"], relation="advances")

    _, before = _component(_readiness(client, account["id"], program["id"]),
                           "harness_closed_action")
    assert before["state"] != "met"

    client.post(f"/api/tasks/{task['id']}/close",
                json={"status": "cancelled", "close_note": "No longer needed."})
    _, cancelled = _component(_readiness(client, account["id"], program["id"]),
                              "harness_closed_action")
    assert cancelled["state"] != "met", "a cancelled task proves nothing"

    done = _task(client, program["id"], "Run the readiness workshop, properly")
    _link(client, instance["id"], task_id=done["id"], relation="advances")
    client.post(f"/api/tasks/{done['id']}/close",
                json={"status": "done", "close_note": "Workshop held and written up."})
    _, after = _component(_readiness(client, account["id"], program["id"]),
                          "harness_closed_action")
    assert after["state"] == "met"


def test_an_unknown_evaluator_version_fails_closed_into_partial_coverage(client):
    """A definition row configures an allowlisted evaluator and can never create one.

    Bumping the version is the realistic way this happens: the definition says v2, the code
    registry only has v1, and the honest answer is that this condition could not be evaluated —
    not that it passed, and not that the pillar quietly shrank by one component.
    """
    account = _account(client)
    program = _program(client, account["id"], "Support Deflection")
    _define(client, "harness_future_evaluator", "field_present",
            {"scope": "program", "fields": ["success_criteria"]}, evaluator_version=2)
    _harness(client, [("harness_future_evaluator", 1, "required")])
    _instantiate_harness(client, account["id"], program["id"])

    readiness = _readiness(client, account["id"], program["id"])
    pillar, component = _component(readiness, "harness_future_evaluator")
    assert component["state"] == "unknown"
    assert "field_present" in component["reason"] and "v2" in component["reason"]
    scope = next(p for p in readiness["programs"] if p["program_id"] == program["id"]) \
        if readiness.get("programs") else readiness
    assert scope["coverage"]["status"] == "partial"
    assert "field_present" in scope["coverage"]["failed_evaluators"]


def test_every_component_reports_the_evaluator_that_produced_it(client):
    """§15.4 — evaluator versions are recorded, so a state change can be attributed to a rule
    change rather than to the account."""
    account, program, _ = _base(client)
    readiness = _readiness(client, account["id"], program["id"])
    seen = 0
    for scope in [readiness] + readiness.get("programs", []):
        for pillar in scope.get("pillars", []):
            for component in pillar.get("components", []):
                if component.get("suppressed"):
                    continue
                assert component["evaluator_key"], component
                assert isinstance(component["evaluator_version"], int)
                seen += 1
    assert seen > 0


def test_composition_fails_closed_as_one_unit(client):
    """`all_of` over an unresolvable child reports that the composite could not be evaluated.

    Reporting the resolvable half would be a narrower claim than the definition made, and a
    narrower claim that reads as an answer is worse than no answer.
    """
    account = _account(client)
    program = _program(client, account["id"], "Support Deflection")
    _define(client, "harness_both_fields", "all_of", {"evaluators": [
        {"evaluator_key": "field_present", "evaluator_version": 1,
         "config": {"scope": "program", "fields": ["success_criteria"]}},
        {"evaluator_key": "field_present", "evaluator_version": 1,
         "config": {"scope": "program", "fields": ["problem_statement"]}},
    ]})
    _define(client, "harness_broken_composite", "all_of", {"evaluators": [
        {"evaluator_key": "field_present", "evaluator_version": 1,
         "config": {"scope": "program", "fields": ["success_criteria"]}},
        {"evaluator_key": "vibe_check", "evaluator_version": 1, "config": {}},
    ]})
    _harness(client, [("harness_both_fields", 1, "required"),
                      ("harness_broken_composite", 1, "required")])
    _instantiate_harness(client, account["id"], program["id"])
    client.patch(f"/api/programs/{program['id']}", json={
        "success_criteria": "Two cohorts live by the end of the quarter.",
        "problem_statement": "Support handling time is above the agreed threshold."})

    readiness = _readiness(client, account["id"], program["id"])
    _, both = _component(readiness, "harness_both_fields")
    _, broken = _component(readiness, "harness_broken_composite")
    assert both["state"] == "met"
    # Its resolvable half is satisfied, and the composite still refuses to answer.
    assert broken["state"] == "unknown"
    assert "vibe_check" in broken["reason"]


def test_a_composite_with_one_satisfied_part_is_thin_not_met(client):
    account = _account(client)
    program = _program(client, account["id"], "Support Deflection")
    _define(client, "harness_both_fields", "all_of", {"evaluators": [
        {"evaluator_key": "field_present", "evaluator_version": 1,
         "config": {"scope": "program", "fields": ["success_criteria"]}},
        {"evaluator_key": "field_present", "evaluator_version": 1,
         "config": {"scope": "program", "fields": ["problem_statement"]}},
    ]})
    _harness(client, [("harness_both_fields", 1, "required")])
    _instantiate_harness(client, account["id"], program["id"])
    client.patch(f"/api/programs/{program['id']}",
                 json={"success_criteria": "Two cohorts live by the end of the quarter."})

    _, component = _component(_readiness(client, account["id"], program["id"]),
                              "harness_both_fields")
    assert component["state"] == "thin"
    assert "1 of 2" in component["reason"]


# --- §15.10.4 evidence: refusal, retraction, supersession, staleness ----------------------------

def test_an_open_action_advances_a_requirement_without_becoming_evidence(client):
    """§15.9, stated as plainly as the spec states it: advancing is not proving."""
    account, program, instances = _base(client)
    instance = instances["exec_identified"]
    task = _task(client, program["id"], "Confirm the executive sponsor")
    _link(client, instance["id"], task_id=task["id"], relation="advances")

    r = client.post(f"/api/plan-instances/{instance['id']}/evidence",
                    json={"evidence_type": "task", "evidence_id": task["id"]})
    assert r.status_code == 422
    detail = r.json()["detail"].lower()
    assert "open" in detail and "advances" in detail


def test_a_requirement_cannot_cite_its_own_suggested_action(client):
    """§15.2's last integrity rule. A condition may not satisfy itself by having asked for
    something: the suggestion came from the requirement, so it cannot be independent proof of it.
    """
    account, program, instances = _base(client)
    instance = instances["exec_identified"]
    task = _task(client, program["id"], "Identify the executive sponsor")
    _link(client, instance["id"], task_id=task["id"], relation="advances",
          origin="suggested_action")
    client.post(f"/api/tasks/{task['id']}/close",
                json={"status": "done", "close_note": "Sponsor named in the steering forum."})

    r = client.post(f"/api/plan-instances/{instance['id']}/evidence",
                    json={"evidence_type": "task", "evidence_id": task["id"]})
    assert r.status_code == 422
    assert "suggest" in r.json()["detail"].lower()


def test_evidence_of_a_disallowed_kind_attaches_as_context_and_moves_nothing(client):
    """§15.3 — unsupported evidence is context, not a refusal and not support.

    Refusing it would push the operator into attaching it somewhere less honest; counting it would
    let any record satisfy any condition. It attaches, it is visible, and it is inert.
    """
    account = _account(client)
    program = _program(client, account["id"], "Support Deflection")
    _define(client, "harness_reviewed", "manual_evidence_review", {"min_count": 1},
            evidence_types=["decision"])
    _harness(client, [("harness_reviewed", 1, "required")])
    instances = _instantiate_harness(client, account["id"], program["id"])
    instance = instances["harness_reviewed"]

    interaction = client.post("/api/interactions", json={
        "account_id": account["id"], "program_id": program["id"], "kind": "meeting",
        "occurred_at": utc_day(-2), "summary": "Steering review"}).json()
    attached = _attach(client, instance["id"], evidence_type="interaction",
                       evidence_id=interaction["id"], reviewed_on=utc_day(-1),
                       review_note="Reviewed in the steering forum.")
    assert attached["evidence"]["supporting"] is False

    readiness = _readiness(client, account["id"], program["id"])
    _, component = _component(readiness, "harness_reviewed")
    assert component["state"] == "unknown", "context-only evidence cannot satisfy the review"
    labels = " ".join(e["label"] for e in component.get("evidence") or [])
    assert "context only" in labels, "it is still cited, so the operator sees what was attached"


def test_retracting_evidence_returns_the_requirement_to_its_gap_state(client):
    """§15.3 — retraction removes support at read time, because the read never looked anywhere
    else. The withdrawn row stays visible: a claim made and taken back is a different fact from a
    claim that never existed."""
    account = _account(client)
    program = _program(client, account["id"], "Support Deflection")
    _define(client, "harness_reviewed", "manual_evidence_review", {"min_count": 1},
            evidence_types=["decision"])
    _harness(client, [("harness_reviewed", 1, "required")])
    instances = _instantiate_harness(client, account["id"], program["id"])
    instance = instances["harness_reviewed"]

    decision = client.post("/api/decisions", json={
        "account_id": account["id"], "program_id": program["id"],
        "description": "Cohort two is in scope for the launch.",
        "decided_on": utc_day(-3), "decided_by_id": None}).json()
    link = _attach(client, instance["id"], evidence_type="decision", evidence_id=decision["id"],
                   reviewed_on=utc_day(-1), review_note="Confirmed against the minutes.")

    _, met = _component(_readiness(client, account["id"], program["id"]), "harness_reviewed")
    assert met["state"] == "met"

    retracted = client.post(f"/api/evidence-links/{link['evidence']['id']}/retract",
                            json={"reason": "The minutes recorded a different decision."})
    assert retracted.status_code == 200, retracted.text

    _, after = _component(_readiness(client, account["id"], program["id"]), "harness_reviewed")
    assert after["state"] == "unknown"

    rows = _sql(client, "SELECT * FROM readiness_requirement_evidence_links WHERE id = ?",
                (link["evidence"]["id"],))
    assert len(rows) == 1 and rows[0]["archived"] == 0 and rows[0]["retracted_at"]


def test_superseded_evidence_names_its_replacement(client):
    account = _account(client)
    program = _program(client, account["id"], "Support Deflection")
    _define(client, "harness_reviewed", "manual_evidence_review", {"min_count": 1},
            evidence_types=["decision"])
    _harness(client, [("harness_reviewed", 1, "required")])
    instances = _instantiate_harness(client, account["id"], program["id"])
    instance = instances["harness_reviewed"]

    first = client.post("/api/decisions", json={
        "account_id": account["id"], "program_id": program["id"],
        "description": "Cohort two is in scope.", "decided_on": utc_day(-9)}).json()
    second = client.post("/api/decisions", json={
        "account_id": account["id"], "program_id": program["id"],
        "description": "Cohort two is in scope, with the revised population.",
        "decided_on": utc_day(-2)}).json()
    old = _attach(client, instance["id"], evidence_type="decision", evidence_id=first["id"],
                  reviewed_on=utc_day(-8), review_note="Reviewed at the time.")
    new = _attach(client, instance["id"], evidence_type="decision", evidence_id=second["id"],
                  reviewed_on=utc_day(-1), review_note="Reviewed after the revision.")

    r = client.post(f"/api/evidence-links/{old['evidence']['id']}/retract",
                    json={"reason": "Replaced by the revised decision.",
                          "superseded_by_id": new["evidence"]["id"]})
    assert r.status_code == 200, r.text
    assert r.json()["evidence"]["superseded_by_id"] == new["evidence"]["id"]

    # The replacement still stands on its own, so the requirement stays met.
    _, component = _component(_readiness(client, account["id"], program["id"]),
                              "harness_reviewed")
    assert component["state"] == "met"


def test_a_review_ages_out_and_stops_counting(client):
    """The date is what makes a manual review an evaluator rather than a checkbox."""
    account = _account(client)
    program = _program(client, account["id"], "Support Deflection")
    _define(client, "harness_reviewed", "manual_evidence_review", {"min_count": 1},
            evidence_types=["decision"])
    _sql(client, "UPDATE readiness_requirement_definitions "
                 "SET freshness_policy_json = ? WHERE key = ?",
         (json.dumps({"harness_reviewed": {"window_days": 30}}), "harness_reviewed"))
    _harness(client, [("harness_reviewed", 1, "required")])
    instances = _instantiate_harness(client, account["id"], program["id"])
    instance = instances["harness_reviewed"]

    decision = client.post("/api/decisions", json={
        "account_id": account["id"], "program_id": program["id"],
        "description": "Cohort two is in scope.", "decided_on": utc_day(-200)}).json()
    _attach(client, instance["id"], evidence_type="decision", evidence_id=decision["id"],
            reviewed_on=utc_day(-200), review_note="Reviewed at the time and not since.")

    _, component = _component(_readiness(client, account["id"], program["id"]),
                              "harness_reviewed")
    assert component["state"] == "thin"
    assert component["freshness"] == "stale"


# --- §15.10.5 gate readiness under complete, blocked, and partial coverage -----------------------

def test_gate_readiness_names_every_unmet_condition(client):
    account, program, instances = _base(client)
    gate = _gate(client, program["id"], "Launch gate", gates_phase="launch",
                 items=["Cohort confirmed"])
    for key in ("exec_identified", "value_baseline_locked"):
        r = client.post(f"/api/phase-gates/{gate['id']}/requirement-links",
                        json={"plan_instance_id": instances[key]["id"], "necessity": "required"})
        assert r.status_code == 200, r.text

    payload = _phase_readiness(client, program["id"])
    assert payload["readiness"] == "blocked"
    assert payload["advances_automatically"] is False
    keys = {row["requirement_key"] for row in payload["requirements"]}
    assert {"exec_identified", "value_baseline_locked"} <= keys
    assert payload["open_gate_items"], "an incomplete gate item is named, not assumed away"
    assert payload["readiness_stamp"].startswith("pr1:")


def test_a_program_with_no_open_gate_reads_passed_and_still_advances_nothing(client):
    """§15.6 — becoming ready never auto-advances the phase."""
    account, program, instances = _base(client)
    gate = _gate(client, program["id"], "Launch gate", gates_phase="launch", items=["Signed off"])
    item = gate["items"][0]
    client.post(f"/api/gate-items/{item['id']}/toggle", json={"complete": True})

    payload = _phase_readiness(client, program["id"])
    assert payload["readiness"] == "passed"
    assert payload["advances_automatically"] is False
    assert client.get(f"/api/programs/{program['id']}").json()["phase"] == "launch"


def test_partial_coverage_reads_as_insufficient_data_not_as_ready(client):
    """A condition nobody could evaluate is not a condition that passed."""
    account = _account(client)
    program = _program(client, account["id"], "Support Deflection")
    _define(client, "harness_unevaluatable", "field_present",
            {"scope": "program", "fields": ["success_criteria"]}, evaluator_version=3)
    _harness(client, [("harness_unevaluatable", 1, "required")])
    instances = _instantiate_harness(client, account["id"], program["id"])
    gate = _gate(client, program["id"], "Launch gate", gates_phase="launch")
    client.post(f"/api/phase-gates/{gate['id']}/requirement-links",
                json={"plan_instance_id": instances["harness_unevaluatable"]["id"]})

    payload = _phase_readiness(client, program["id"])
    assert payload["readiness"] == "insufficient_data"
    assert payload["coverage"] != "complete"
    assert payload["coverage_failures"]


def test_a_gate_condition_whose_plan_instance_was_archived_is_not_reported_as_outstanding(client):
    """`blocked` claims a condition was read and found unsatisfied. This one was never read.

    A playbook upgrade archives every instance of the superseded plan, so this is not an exotic
    input — one ordinary upgrade breaks every gate requirement link on the program at once. The
    classifier used to look for `state == "unknown"` and a known evaluator key, and the row the
    archived branch builds carries neither, so it landed in `determined` and the gate announced
    "1 required condition outstanding" about a condition nobody could evaluate.
    """
    account, program, instances = _base(client)
    gate = _gate(client, program["id"], "Launch gate", gates_phase="launch")
    r = client.post(f"/api/phase-gates/{gate['id']}/requirement-links",
                    json={"plan_instance_id": instances["budget_authority_evidence"]["id"],
                          "necessity": "required"})
    assert r.status_code == 200, r.text

    before = _phase_readiness(client, program["id"])
    assert before["readiness"] == "blocked", "the linked condition is genuinely unmet to begin with"

    # v2 of the playbook drops `budget_authority_evidence`; the upgrade archives the instances.
    r = client.post(f"/api/accounts/{account['id']}/plan-instances/upgrade", json={
        "playbook_key": "enterprise-launch", "to_version": 2, "program_id": program["id"]})
    assert r.status_code == 200, r.text

    payload = _phase_readiness(client, program["id"])
    assert payload["coverage"] == "partial"
    assert payload["readiness"] == "insufficient_data", (
        "an unreadable condition is not an unsatisfied one")
    assert "could not be evaluated" in payload["summary"]
    assert "outstanding" not in payload["summary"]
    unavailable = [r for r in payload["requirements"] if r["available"] is False]
    assert unavailable, "the lost condition is still named, not silently dropped"


def test_an_unreadable_condition_does_not_excuse_a_second_gap_with_the_same_key(client):
    """The exclusion is by link identity, because two gates can link the same requirement key.

    Filtering `determined` by `requirement_key` meant one unreadable row could suppress another
    gate's genuinely established gap — a failure in the direction that makes a gate look better
    than it is.
    """
    account, program, instances = _base(client)
    gate = _gate(client, program["id"], "Launch gate", gates_phase="launch")
    for key in ("exec_identified", "value_baseline_locked"):
        r = client.post(f"/api/phase-gates/{gate['id']}/requirement-links",
                        json={"plan_instance_id": instances[key]["id"], "necessity": "required"})
        assert r.status_code == 200, r.text

    payload = _phase_readiness(client, program["id"])
    assert payload["readiness"] == "blocked"
    determined = {r["requirement_key"] for r in payload["requirements"] if r["is_gap"]}
    assert {"exec_identified", "value_baseline_locked"} <= determined
    assert "2 required conditions outstanding" in payload["summary"]


# --- §15.10.6 atomic transition and stale readiness ---------------------------------------------

def _ready_program(c):
    """A program whose only gate is satisfied, so a transition is genuinely available."""
    account = _account(c)
    program = _program(c, account["id"], "Support Deflection", phase="launch")
    gate = _gate(c, program["id"], "Launch gate", gates_phase="launch", items=["Signed off"])
    c.post(f"/api/gate-items/{gate['items'][0]['id']}/toggle", json={"complete": True})
    return account, program, gate


def test_a_stale_readiness_stamp_is_rejected(client):
    account, program, gate = _ready_program(client)
    payload = _phase_readiness(client, program["id"])
    stale = payload["readiness_stamp"]

    # Something changes underneath the operator's open dialog.
    _gate(client, program["id"], "Second launch gate", gates_phase="launch", items=["Not done"])
    assert _phase_readiness(client, program["id"])["readiness_stamp"] != stale

    r = client.post(f"/api/programs/{program['id']}/phase-transitions", json={
        "expected_current_phase": "launch", "requested_next_phase": "programmatic",
        "readiness_stamp": stale})
    assert r.status_code == 409
    assert client.get(f"/api/programs/{program['id']}").json()["phase"] == "launch"


def test_a_transition_rejects_a_phase_the_operator_was_not_looking_at(client):
    account, program, gate = _ready_program(client)
    payload = _phase_readiness(client, program["id"])
    r = client.post(f"/api/programs/{program['id']}/phase-transitions", json={
        "expected_current_phase": "foundation", "requested_next_phase": "programmatic",
        "readiness_stamp": payload["readiness_stamp"]})
    assert r.status_code == 409


def test_a_satisfied_transition_moves_the_phase_and_records_it_once(client):
    account, program, gate = _ready_program(client)
    payload = _phase_readiness(client, program["id"])
    assert payload["readiness"] == "passed"

    r = client.post(f"/api/programs/{program['id']}/phase-transitions", json={
        "expected_current_phase": "launch", "requested_next_phase": "programmatic",
        "readiness_stamp": payload["readiness_stamp"]})
    assert r.status_code == 200, r.text
    assert client.get(f"/api/programs/{program['id']}").json()["phase"] == "programmatic"

    history = client.get(f"/api/programs/{program['id']}/phase-transitions").json()
    completed = [e for e in history["events"] if e["outcome"] == "completed"]
    assert len(completed) == 1
    assert completed[0]["from_phase"] == "launch" and completed[0]["to_phase"] == "programmatic"
    assert completed[0]["is_override"] is False


def test_a_non_adjacent_transition_needs_an_override(client):
    account, program, gate = _ready_program(client)
    payload = _phase_readiness(client, program["id"])
    r = client.post(f"/api/programs/{program['id']}/phase-transitions", json={
        "expected_current_phase": "launch", "requested_next_phase": "renewal",
        "readiness_stamp": payload["readiness_stamp"]})
    assert r.status_code == 422
    assert client.get(f"/api/programs/{program['id']}").json()["phase"] == "launch"


def test_a_blocked_transition_records_the_attempt_and_moves_nothing(client):
    account, program, instances = _base(client)
    gate = _gate(client, program["id"], "Launch gate", gates_phase="launch", items=["Not done"])
    client.post(f"/api/phase-gates/{gate['id']}/requirement-links",
                json={"plan_instance_id": instances["exec_identified"]["id"]})
    payload = _phase_readiness(client, program["id"])
    assert payload["readiness"] == "blocked"

    r = client.post(f"/api/programs/{program['id']}/phase-transitions", json={
        "expected_current_phase": "launch", "requested_next_phase": "programmatic",
        "readiness_stamp": payload["readiness_stamp"]})
    assert r.status_code == 422
    assert client.get(f"/api/programs/{program['id']}").json()["phase"] == "launch"

    history = client.get(f"/api/programs/{program['id']}/phase-transitions").json()
    rejected = [e for e in history["events"] if e["outcome"] == "rejected"]
    assert len(rejected) == 1, "the refusal is itself part of the provenance"
    assert rejected[0]["unmet_at_transition"]


def test_phase_history_is_append_only(client):
    """Enforced by a trigger rather than by convention, because history that can be edited is
    not history."""
    account, program, gate = _ready_program(client)
    payload = _phase_readiness(client, program["id"])
    client.post(f"/api/programs/{program['id']}/phase-transitions", json={
        "expected_current_phase": "launch", "requested_next_phase": "programmatic",
        "readiness_stamp": payload["readiness_stamp"]})
    event = _sql(client, "SELECT id FROM program_phase_events LIMIT 1")[0]

    for statement, params in (
        ("UPDATE program_phase_events SET reason = 'rewritten' WHERE id = ?", (event["id"],)),
        ("DELETE FROM program_phase_events WHERE id = ?", (event["id"],)),
    ):
        with pytest.raises(sqlite3.IntegrityError) as excinfo:
            _sql(client, statement, params)
        assert "append-only" in str(excinfo.value)


# --- §15.10.7 override and waiver semantics -----------------------------------------------------

def test_an_override_records_the_unmet_conditions_without_satisfying_them(client):
    account, program, instances = _base(client)
    gate = _gate(client, program["id"], "Launch gate", gates_phase="launch", items=["Not done"])
    client.post(f"/api/phase-gates/{gate['id']}/requirement-links",
                json={"plan_instance_id": instances["exec_identified"]["id"]})
    payload = _phase_readiness(client, program["id"])
    before = _component(_readiness(client, account["id"], program["id"]), "exec_identified")[1]

    assert client.post(f"/api/programs/{program['id']}/phase-transitions", json={
        "expected_current_phase": "launch", "requested_next_phase": "programmatic",
        "readiness_stamp": payload["readiness_stamp"], "override": True,
        "reason": "short"}).status_code == 422

    r = client.post(f"/api/programs/{program['id']}/phase-transitions", json={
        "expected_current_phase": "launch", "requested_next_phase": "programmatic",
        "readiness_stamp": payload["readiness_stamp"], "override": True,
        "reason": "Steering committee accepted the gap for the quarter."})
    assert r.status_code == 200, r.text
    assert client.get(f"/api/programs/{program['id']}").json()["phase"] == "programmatic"

    event = [e for e in client.get(f"/api/programs/{program['id']}/phase-transitions").json()
             ["events"] if e["outcome"] == "completed"][0]
    assert event["is_override"] is True and event["unmet_at_transition"]

    # The requirement is exactly as unmet as it was. Advancing past it changed nothing about it.
    after = _component(_readiness(client, account["id"], program["id"]), "exec_identified")[1]
    assert after["state"] == before["state"]
    # And the gate it bypassed is still open. An override is not a pass.
    assert _sql(client, "SELECT status, passed_on FROM phase_gates WHERE id = ?",
                (gate["id"],))[0]["status"] == "open"


def test_waiving_a_gate_moves_no_phase_and_satisfies_no_requirement(client):
    """§15.6 — waiving a gate is distinct from completing its requirements."""
    account, program, instances = _base(client)
    gate = _gate(client, program["id"], "Launch gate", gates_phase="launch", items=["Not done"])
    client.post(f"/api/phase-gates/{gate['id']}/requirement-links",
                json={"plan_instance_id": instances["exec_identified"]["id"]})
    before = _component(_readiness(client, account["id"], program["id"]), "exec_identified")[1]

    r = client.post(f"/api/phase-gates/{gate['id']}/waive",
                    json={"waiver_reason": "Accepted by the steering committee this quarter."})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "waived"
    assert body["waiver"]["phase_unchanged"] == "launch"
    assert body["waiver"]["unmet_at_waiver"]

    row = _sql(client, "SELECT status, passed_on FROM phase_gates WHERE id = ?", (gate["id"],))[0]
    assert row["status"] == "waived"
    assert row["passed_on"] is None, "a waived gate was never passed, so it carries no pass date"

    assert client.get(f"/api/programs/{program['id']}").json()["phase"] == "launch"
    after = _component(_readiness(client, account["id"], program["id"]), "exec_identified")[1]
    assert after["state"] == before["state"]

    waived = [e for e in client.get(f"/api/programs/{program['id']}/phase-transitions").json()
              ["events"] if e["outcome"] == "waived"]
    assert len(waived) == 1
    assert waived[0]["from_phase"] == waived[0]["to_phase"], "a waiver is not a movement"


def test_a_proposal_records_the_intent_without_moving_anything(client):
    account, program, instances = _base(client)
    _gate(client, program["id"], "Launch gate", gates_phase="launch", items=["Not done"])
    r = client.post(f"/api/programs/{program['id']}/phase-transitions", json={
        "outcome": "proposed", "requested_next_phase": "programmatic",
        "note": "Targeting the end of the quarter."})
    assert r.status_code == 200, r.text
    assert client.get(f"/api/programs/{program['id']}").json()["phase"] == "launch"
    events = client.get(f"/api/programs/{program['id']}/phase-transitions").json()["events"]
    assert [e["outcome"] for e in events] == ["proposed"]


# --- §15.10.8 successor-action behaviour --------------------------------------------------------

def test_closing_with_a_successor_carries_the_link_forward_as_a_follow_up(client):
    """§15.7 — `Resolve` must not become a way to hide incomplete account work."""
    account, program, instances = _base(client)
    instance = instances["exec_identified"]
    milestone = _milestone(client, program["id"], "Executive briefing", target_date=utc_day(20))
    task = _task(client, program["id"], "Draft the sponsor briefing")
    _link(client, instance["id"], task_id=task["id"], relation="advances")
    client.post(f"/api/milestones/{milestone['id']}/action-links",
                json={"task_id": task["id"], "relation": "advances"})

    before = _component(_readiness(client, account["id"], program["id"]), "exec_identified")[1]
    r = client.post(f"/api/actions/task/{task['id']}/close-with-successor", json={
        "closure": {"status": "done", "close_note": "Draft handed to the sponsor."},
        "successor": {"type": "task", "description": "Hold the sponsor briefing",
                      "due_date": utc_day(14)}})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["closed"]["status"] == "done"
    assert body["successor"]["id"]
    relations = sorted(link["relation"] for link in body["carried_links"])
    assert relations == ["advances", "follow_up_for"], (
        "the requirement link becomes a follow-up (downstream of the condition, never evidence "
        "for it); the milestone link keeps its own relation")
    assert "stay open" in body["requirement_note"]

    after = _component(_readiness(client, account["id"], program["id"]), "exec_identified")[1]
    assert after["state"] == before["state"], "closing an action settles no condition"

    context = client.get(f"/api/actions/task/{body['successor']['id']}/path-context").json()
    assert [r["requirement_key"] for r in context["requirements"]] == ["exec_identified"]
    assert [m["milestone_id"] for m in context["milestones"]] == [milestone["id"]]


def test_closing_without_a_successor_still_says_the_requirement_is_open(client):
    account, program, instances = _base(client)
    instance = instances["exec_identified"]
    task = _task(client, program["id"], "Draft the sponsor briefing")
    _link(client, instance["id"], task_id=task["id"], relation="advances")

    r = client.post(f"/api/actions/task/{task['id']}/close-with-successor", json={
        "closure": {"status": "done", "close_note": "Done for now."}})
    assert r.status_code == 200, r.text
    assert r.json()["successor"] is None
    assert "stay open" in r.json()["requirement_note"]


# --- §15.10.9 explicit-relation ranking reason --------------------------------------------------

def test_gate_impact_is_claimed_only_from_an_explicit_required_link(client):
    """§15.8 — `Unblocks the … gate` is a claim about a relationship, so it needs one."""
    account, program, instances = _base(client)
    instance = instances["exec_identified"]
    task = _task(client, program["id"], "Confirm the executive sponsor", due_date=utc_day(-3))
    gate = _gate(client, program["id"], "Launch gate", gates_phase="launch", items=["Not done"])

    def _row_for(task_id):
        payload = client.get(f"/api/accounts/{account['id']}/execution-path",
                             params={"program_id": program["id"]}).json()
        for bucket in ("you_own", "you_owe", "waiting_on"):
            for row in payload["work"].get(bucket) or []:
                if row.get("source_id") == task_id:
                    return row
        raise AssertionError("task did not reach the queue")

    # No relationship yet: no claim.
    assert _row_for(task["id"])["gate_impact"] is None

    # A relationship the gate does not depend on: still no claim.
    _link(client, instance["id"], task_id=task["id"], relation="advances")
    assert _row_for(task["id"])["gate_impact"] is None

    # The gate depends on the requirement this task advances. Now the claim is earned.
    client.post(f"/api/phase-gates/{gate['id']}/requirement-links",
                json={"plan_instance_id": instance["id"], "necessity": "required"})
    row = _row_for(task["id"])
    assert row["gate_impact"]["gate_name"] == "Launch gate"
    assert "Unblocks the Launch gate" in row["reason"]


def test_an_optional_gate_link_does_not_claim_to_unblock(client):
    account, program, instances = _base(client)
    instance = instances["exec_identified"]
    task = _task(client, program["id"], "Confirm the executive sponsor", due_date=utc_day(-3))
    gate = _gate(client, program["id"], "Launch gate", gates_phase="launch", items=["Not done"])
    _link(client, instance["id"], task_id=task["id"], relation="advances")
    client.post(f"/api/phase-gates/{gate['id']}/requirement-links",
                json={"plan_instance_id": instance["id"], "necessity": "optional"})

    payload = client.get(f"/api/accounts/{account['id']}/execution-path",
                         params={"program_id": program["id"]}).json()
    rows = [r for bucket in ("you_own", "you_owe", "waiting_on")
            for r in payload["work"].get(bucket) or [] if r.get("source_id") == task["id"]]
    assert rows and rows[0]["gate_impact"] is None


# --- §15.10.10 detail panels and timeline dependencies ------------------------------------------

def test_the_requirement_panel_and_the_action_panel_agree(client):
    """§15.8 — the same relationship, read from both ends, with no third source of truth."""
    account, program, instances = _base(client)
    instance = instances["exec_identified"]
    task = _task(client, program["id"], "Confirm the executive sponsor")
    gate = _gate(client, program["id"], "Launch gate", gates_phase="launch")
    _link(client, instance["id"], task_id=task["id"], relation="advances")
    client.post(f"/api/phase-gates/{gate['id']}/requirement-links",
                json={"plan_instance_id": instance["id"], "necessity": "required"})

    panel = client.get(f"/api/plan-instances/{instance['id']}/links").json()
    assert [a["action"]["id"] for a in panel["actions"]] == [task["id"]]
    assert panel["actions"][0]["action"]["status"] == "open"
    assert [g["gate_id"] for g in panel["gates"]] == [gate["id"]]

    context = client.get(f"/api/actions/task/{task['id']}/path-context").json()
    assert [r["requirement_key"] for r in context["requirements"]] == ["exec_identified"]
    assert context["requirements"][0]["label"]
    assert [g["gate_id"] for g in context["gates"]] == [gate["id"]]
    assert context["gates"][0]["through_requirement"] == "exec_identified"


def test_timeline_dependencies_come_only_from_explicit_links(client):
    """A dependency line is drawn from an accepted relationship or it is not drawn. Sharing a
    date, an owner, or a description is not a dependency."""
    account, program, instances = _base(client)
    milestone = _milestone(client, program["id"], "Executive briefing", target_date=utc_day(20))
    linked = _task(client, program["id"], "Draft the sponsor briefing", due_date=utc_day(20))
    lookalike = _task(client, program["id"], "Executive briefing", due_date=utc_day(20))

    assert client.get(f"/api/milestones/{milestone['id']}/action-links").json()["links"] == []

    client.post(f"/api/milestones/{milestone['id']}/action-links",
                json={"task_id": linked["id"], "relation": "advances"})
    links = client.get(f"/api/milestones/{milestone['id']}/action-links").json()["links"]
    assert [l["action"]["id"] for l in links] == [linked["id"]]
    assert lookalike["id"] not in [l["action"]["id"] for l in links]

    r = client.post(f"/api/milestone-action-links/{links[0]['id']}/archive",
                    json={"reason": "The briefing moved to a different workstream."})
    assert r.status_code == 200, r.text
    assert client.get(f"/api/milestones/{milestone['id']}/action-links").json()["links"] == []


# --- the structural guard -----------------------------------------------------------------------

def test_no_relationship_table_stores_a_readiness_state(client):
    """The Slice 3 guard, extended sideways to the Slice 5 tables.

    A link records that two records are related and a phase event records what was decided. Either
    one storing a state, freshness, coverage, or applicability value would be a second source of
    truth that could disagree with the records readiness actually reads. `unmet_at_transition_json`
    is deliberately named so it cannot be mistaken for one: it is a snapshot of a past decision,
    and the test allows it by name rather than by pattern.
    """
    banned_suffixes = ("state", "met", "freshness", "coverage", "applicability", "score", "weight")
    allowed = {"unmet_at_transition_json"}
    expected = {"readiness_requirement_action_links", "readiness_requirement_evidence_links",
                "milestone_action_links", "gate_requirement_links", "program_phase_events"}
    tables = {r["name"] for r in _sql(
        client, "SELECT name FROM sqlite_master WHERE type = 'table' AND ("
                "name LIKE 'readiness_requirement_%_links' OR name = 'milestone_action_links' "
                "OR name = 'gate_requirement_links' OR name = 'program_phase_events')")}
    assert tables == expected, tables
    for table in tables:
        for column in [r["name"] for r in _sql(client, f"PRAGMA table_info({table})")]:
            if column in allowed:
                continue
            for suffix in banned_suffixes:
                assert column != suffix and not column.endswith("_" + suffix), (
                    f"{table}.{column} looks like a stored readiness verdict")
