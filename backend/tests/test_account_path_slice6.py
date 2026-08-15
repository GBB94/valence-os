"""Acceptance tests for ACCOUNT-PATH-SPEC.md Slice 6 — shared plans and generated outputs.

These are written to try to get something in front of a customer that nobody promoted: through a
milestone group, through a status word, through a person's name, through a requirement whose state
is not sayable, through a stale `met`, through a link to an unpromoted record, and through a
markdown renderer that had a full database row in hand. Each test asserts the honest answer, which
is usually silence in the artifact and a named reason in the diagnostics.
"""
import json
import os
import pathlib
import sqlite3
import tempfile

import pytest
from fastapi.testclient import TestClient


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
            return [dict(r) for r in conn.execute(statement, params).fetchall()]
    finally:
        conn.close()


# --- fixture helpers ------------------------------------------------------------------------------

def _account(c, name="Northwind Synthetic"):
    return c.post("/api/accounts", json={"name": name}).json()


def _program(c, account_id, name, phase="launch"):
    return c.post("/api/programs", json={"account_id": account_id, "name": name, "phase": phase}).json()


def _person(c, account_id, name, affiliation="client"):
    return c.post("/api/persons", json={
        "name": name, "affiliation": affiliation,
        "account_id": None if affiliation == "valence" else account_id}).json()


def _source(c, label="Joint plan notes"):
    return c.post("/api/source-references", json={"label": label}).json()


def _interaction(c, account_id, program_id, summary="Plan agreed"):
    return c.post("/api/interactions", json={
        "account_id": account_id, "program_id": program_id, "type": "meeting",
        "summary": summary}).json()


def _task(c, program_id, description, **kw):
    return c.post("/api/tasks", json={"program_id": program_id, "description": description, **kw}).json()


def _commitment(c, program_id, responsible_id, owner_id, description, due_date="2026-09-30", **kw):
    return c.post("/api/commitments", json={
        "program_id": program_id, "description": description,
        "responsible_party_id": responsible_id, "internal_owner_id": owner_id,
        "due_date": due_date, **kw}).json()


def _milestone(c, program_id, name, **kw):
    return c.post("/api/milestones", json={"program_id": program_id, "name": name, **kw}).json()


def _promote(c, object_type, object_id, expect=200, **kw):
    r = c.post("/api/map/promote", json={"object_type": object_type, "object_id": object_id,
                                         "client_visible": True, **kw})
    assert r.status_code == expect, r.text
    return r.json()


def _demote(c, object_type, object_id):
    r = c.post("/api/map/promote", json={"object_type": object_type, "object_id": object_id,
                                         "client_visible": False})
    assert r.status_code == 200, r.text
    return r.json()


def _map(c, account_id):
    r = c.get(f"/api/accounts/{account_id}/map")
    assert r.status_code == 200, r.text
    return r.json()


def _launch(c, account_id, program_id, anchor="2026-07-01"):
    r = c.post(f"/api/accounts/{account_id}/plan-instances", json={
        "playbook_key": "enterprise-launch", "playbook_version": 1,
        "program_id": program_id, "anchor_type": "kickoff", "anchor_date": anchor})
    assert r.status_code == 200, r.text
    return r.json()


def _exec_sponsor(c, program_id, person_id):
    """Give `exec_identified` something to read.

    Readiness is a projection, so a requirement with no underlying record reads `unknown` and a
    plan that claimed a status for it would be inventing one. These tests are about what a *stated*
    requirement may say to a customer, so they need a real executive-layer stakeholder first.
    """
    r = c.post("/api/stakeholder-roles", json={
        "program_id": program_id, "person_id": person_id, "role": "executive_sponsor"})
    assert r.status_code == 201, r.text
    return r.json()


def _instances(c, account_id, program_id=None):
    url = f"/api/accounts/{account_id}/plan-instances"
    if program_id:
        url += f"?program_id={program_id}"
    out = {}
    for plan in c.get(url).json().get("plans", []):
        for instance in plan.get("instances", []):
            out[instance["requirement_key"]] = instance
    return out


def _scene(c):
    """One account, one program, one sourced commitment, one sourced milestone, one internal task."""
    account = _account(c)
    program = _program(c, account["id"], "Europe Deployment")
    customer = _person(c, account["id"], "Robin Ashfield")
    valence = _person(c, account["id"], "Sam Rivera", affiliation="valence")
    source = _source(c)
    interaction = _interaction(c, account["id"], program["id"])
    commitment = _commitment(c, program["id"], customer["id"], valence["id"],
                             "Confirm the data-processing addendum",
                             source_reference_id=source["id"])
    milestone = _milestone(c, program["id"], "Europe go-live", target_date="2026-09-15",
                           source_interaction_id=interaction["id"])
    internal = _task(c, program["id"], "INTERNAL: draft the renewal pricing memo",
                     internal_owner_id=valence["id"], source_reference_id=source["id"])
    return {"account": account, "program": program, "customer": customer, "valence": valence,
            "source": source, "interaction": interaction, "commitment": commitment,
            "milestone": milestone, "internal": internal}


def _actions(artifact):
    return [a for p in artifact["programs"] for g in p["groups"] for a in g["actions"]]


# --- §16.8: nothing appears without affirmative promotion -----------------------------------------

def test_an_empty_plan_is_empty_rather_than_a_summary_of_internal_work(client):
    scene = _scene(client)
    payload = _map(client, scene["account"]["id"])
    artifact = payload["artifact"]
    assert artifact["programs"] == [] and artifact["summary"]["shared_items"] == 0
    assert "No items have been shared" in artifact["markdown"]
    # But the operator is told there is unshared work, so an empty plan is distinguishable from a
    # plan somebody forgot to promote into.
    assert payload["diagnostics"]["unshared_counts"]["commitments"] == 1
    assert payload["diagnostics"]["unshared_counts"]["tasks"] == 1


def test_an_unpromoted_record_never_reaches_the_artifact_or_the_markdown(client):
    scene = _scene(client)
    _promote(client, "commitment", scene["commitment"]["id"])
    artifact = _map(client, scene["account"]["id"])["artifact"]
    blob = json.dumps(artifact)
    assert "renewal pricing memo" not in blob
    assert "INTERNAL" not in blob
    assert "renewal pricing memo" not in artifact["markdown"]


def test_a_promoted_record_from_another_account_cannot_appear(client):
    scene = _scene(client)
    other = _account(client, "Southwind Synthetic")
    other_program = _program(client, other["id"], "Other deployment")
    other_source = _source(client, "Other account notes")
    other_task = _task(client, other_program["id"], "Work belonging to the other customer",
                       source_reference_id=other_source["id"])
    _promote(client, "task", other_task["id"])
    artifact = _map(client, scene["account"]["id"])["artifact"]
    assert "other customer" not in json.dumps(artifact)


# --- §16.5: grouping and ordering -----------------------------------------------------------------

def test_actions_group_under_the_milestone_they_advance(client):
    scene = _scene(client)
    _promote(client, "commitment", scene["commitment"]["id"])
    _promote(client, "milestone", scene["milestone"]["id"])
    r = client.post(f"/api/milestones/{scene['milestone']['id']}/action-links",
                    json={"commitment_id": scene["commitment"]["id"], "relation": "advances"})
    assert r.status_code in (200, 201), r.text

    artifact = _map(client, scene["account"]["id"])["artifact"]
    groups = artifact["programs"][0]["groups"]
    assert [g["milestone"] for g in groups] == ["Europe go-live"]
    assert [a["what"] for a in groups[0]["actions"]] == ["Confirm the data-processing addendum"]
    # And the loose bucket is not created when there is nothing loose in it.
    assert all(g["milestone_id"] for g in groups)


def test_an_action_with_no_promoted_milestone_lands_in_the_other_work_group(client):
    scene = _scene(client)
    _promote(client, "commitment", scene["commitment"]["id"])
    artifact = _map(client, scene["account"]["id"])["artifact"]
    groups = artifact["programs"][0]["groups"]
    assert [g["milestone"] for g in groups] == ["Other agreed work"]
    assert groups[0]["milestone_id"] is None


def test_a_link_to_an_unpromoted_milestone_does_not_reveal_it(client):
    """The milestone stays internal, so its name must not appear — not as a group, not anywhere."""
    scene = _scene(client)
    _promote(client, "commitment", scene["commitment"]["id"])
    client.post(f"/api/milestones/{scene['milestone']['id']}/action-links",
                json={"commitment_id": scene["commitment"]["id"], "relation": "advances"})
    artifact = _map(client, scene["account"]["id"])["artifact"]
    assert "Europe go-live" not in json.dumps(artifact)
    assert [g["milestone"] for g in artifact["programs"][0]["groups"]] == ["Other agreed work"]


def test_multi_program_plans_stay_grouped_and_ordered(client):
    scene = _scene(client)
    second = _program(client, scene["account"]["id"], "Americas Deployment")
    task = _task(client, second["id"], "Agree the Americas onboarding window",
                 internal_owner_id=scene["valence"]["id"],
                 source_reference_id=scene["source"]["id"])
    _promote(client, "task", task["id"])
    _promote(client, "commitment", scene["commitment"]["id"])
    artifact = _map(client, scene["account"]["id"])["artifact"]
    assert [p["name"] for p in artifact["programs"]] == ["Americas Deployment", "Europe Deployment"]
    assert artifact["summary"]["programs"] == 2 and artifact["summary"]["shared_items"] == 2
    # Each program's own work stays under its own heading.
    americas = next(p for p in artifact["programs"] if p["name"] == "Americas Deployment")
    assert [a["what"] for g in americas["groups"] for a in g["actions"]] == \
        ["Agree the Americas onboarding window"]


# --- §16.3: simple status, derived, never guessed --------------------------------------------------

def test_a_blocker_must_itself_be_shared_before_a_milestone_can_be_called_blocked(client):
    """Otherwise the status word announces the existence of internal work."""
    scene = _scene(client)
    _promote(client, "milestone", scene["milestone"]["id"])
    client.post(f"/api/milestones/{scene['milestone']['id']}/action-links",
                json={"task_id": scene["internal"]["id"], "relation": "blocks"})
    artifact = _map(client, scene["account"]["id"])["artifact"]
    group = artifact["programs"][0]["groups"][0]
    assert group["client_status"] == "not_started"
    assert "blocked" not in artifact["markdown"].lower()

    # Promote the blocker and the same milestone becomes honestly blocked.
    _promote(client, "task", scene["internal"]["id"])
    group = _map(client, scene["account"]["id"])["artifact"]["programs"][0]["groups"][0]
    assert group["client_status"] == "blocked"


def test_every_status_in_the_artifact_is_one_of_the_five_words(client):
    scene = _scene(client)
    _promote(client, "commitment", scene["commitment"]["id"])
    _promote(client, "milestone", scene["milestone"]["id"])
    _promote(client, "task", scene["internal"]["id"])
    from app import shared_plan
    artifact = _map(client, scene["account"]["id"])["artifact"]
    statuses = {a["client_status"] for a in _actions(artifact)}
    statuses |= {g["client_status"] for p in artifact["programs"] for g in p["groups"]
                 if g["client_status"]}
    assert statuses and statuses <= set(shared_plan.CLIENT_STATUSES)


def test_a_cancelled_task_reads_as_not_applicable_rather_than_disappearing(client):
    scene = _scene(client)
    _promote(client, "task", scene["internal"]["id"])
    r = client.post(f"/api/tasks/{scene['internal']['id']}/close",
                    json={"status": "cancelled", "close_note": "Superseded"})
    assert r.status_code == 200, r.text
    artifact = _map(client, scene["account"]["id"])["artifact"]
    assert [a["client_status"] for a in _actions(artifact)] == ["not_applicable"]
    # The close note is an internal explanation and is not selected.
    assert "Superseded" not in json.dumps(artifact)


def test_a_milestone_does_not_read_not_started_above_actions_the_customer_sees_underway(client):
    """The document must not disagree with itself.

    An open shared action renders `In progress` (`_action_status` refuses to invent the
    untouched/underway distinction), so a milestone that required a *completed* advancing action
    before moving off `not_started` printed "Not started" directly above a row saying the opposite.
    """
    scene = _scene(client)
    _promote(client, "commitment", scene["commitment"]["id"])
    _promote(client, "milestone", scene["milestone"]["id"])
    client.post(f"/api/milestones/{scene['milestone']['id']}/action-links",
                json={"commitment_id": scene["commitment"]["id"], "relation": "advances"})
    group = _map(client, scene["account"]["id"])["artifact"]["programs"][0]["groups"][0]
    assert [a["client_status"] for a in group["actions"]] == ["in_progress"]
    assert group["client_status"] == "in_progress"


def test_a_milestone_whose_only_advancing_action_was_cancelled_stays_not_started(client):
    """The other direction: `not_applicable` must not talk a milestone into progress."""
    scene = _scene(client)
    _promote(client, "task", scene["internal"]["id"])
    _promote(client, "milestone", scene["milestone"]["id"])
    client.post(f"/api/milestones/{scene['milestone']['id']}/action-links",
                json={"task_id": scene["internal"]["id"], "relation": "advances"})
    r = client.post(f"/api/tasks/{scene['internal']['id']}/close",
                    json={"status": "cancelled", "close_note": "Dropped"})
    assert r.status_code == 200, r.text
    group = _map(client, scene["account"]["id"])["artifact"]["programs"][0]["groups"][0]
    assert [a["client_status"] for a in group["actions"]] == ["not_applicable"]
    assert group["client_status"] == "not_started"


# --- §16.5: owners are named on two sides, and nothing else about them travels ---------------------

def test_owner_names_are_split_by_side_and_carry_nothing_else(client):
    scene = _scene(client)
    _promote(client, "commitment", scene["commitment"]["id"])
    artifact = _map(client, scene["account"]["id"])["artifact"]
    item = _actions(artifact)[0]
    assert item["customer_owner"] == "Robin Ashfield"
    assert item["valence_owner"] == "Sam Rivera"
    assert set(item) == {"kind", "id", "what", "due", "client_status",
                         "customer_owner", "valence_owner", "source"}


def test_a_person_from_another_account_is_never_loaded(client):
    scene = _scene(client)
    other = _account(client, "Southwind Synthetic")
    stranger = _person(client, other["id"], "Alex Nordholm")
    from app import shared_plan
    conn = sqlite3.connect(client.db_path); conn.row_factory = sqlite3.Row
    try:
        people = shared_plan._people(conn, scene["account"]["id"])
    finally:
        conn.close()
    assert stranger["id"] not in people
    assert scene["customer"]["id"] in people and scene["valence"]["id"] in people


# --- §16.3/§16.4: promoting a requirement ---------------------------------------------------------

def test_a_requirement_cannot_be_shared_without_a_client_safe_label(client):
    """The canonical label is written for operators. §16.3 wants one confirmed for external eyes."""
    scene = _scene(client)
    _launch(client, scene["account"]["id"], scene["program"]["id"])
    instance = _instances(client, scene["account"]["id"], scene["program"]["id"])["exec_identified"]
    r = client.post("/api/map/promote", json={"object_type": "requirement",
                                              "object_id": instance["id"], "client_visible": True})
    assert r.status_code == 422 and "client-safe label" in r.json()["detail"]


def test_the_database_refuses_a_client_visible_requirement_with_no_label(client):
    """The rule is a trigger, not a validator, so it also holds against a hand-typed UPDATE."""
    scene = _scene(client)
    _launch(client, scene["account"]["id"], scene["program"]["id"])
    instance = _instances(client, scene["account"]["id"], scene["program"]["id"])["exec_identified"]
    conn = sqlite3.connect(client.db_path)
    try:
        with pytest.raises(sqlite3.IntegrityError):
            with conn:
                conn.execute("UPDATE readiness_plan_instances SET client_visible = 1 WHERE id = ?",
                             (instance["id"],))
    finally:
        conn.close()


def test_a_requirement_with_no_readiness_reading_is_withheld_rather_than_guessed(client):
    """Nothing records an executive sponsor here, so readiness says `unknown` and the plan says
    nothing at all — `not_started` would be a claim the records do not support."""
    scene = _scene(client)
    _launch(client, scene["account"]["id"], scene["program"]["id"])
    instance = _instances(client, scene["account"]["id"], scene["program"]["id"])["exec_identified"]
    _promote(client, "requirement", instance["id"], client_label="Executive sponsor confirmed")

    payload = _map(client, scene["account"]["id"])
    assert "Executive sponsor confirmed" not in json.dumps(payload["artifact"])
    withheld = [w for w in payload["diagnostics"]["withheld"] if w["id"] == instance["id"]]
    assert withheld and withheld[0]["label"] == "Executive sponsor confirmed"
    assert "no readiness reading" in withheld[0]["reason"]


def test_a_shared_requirement_with_no_client_visible_support_is_withheld_and_explained(client):
    scene = _scene(client)
    _exec_sponsor(client, scene["program"]["id"], scene["customer"]["id"])
    _launch(client, scene["account"]["id"], scene["program"]["id"])
    instance = _instances(client, scene["account"]["id"], scene["program"]["id"])["exec_identified"]
    _promote(client, "requirement", instance["id"], client_label="Executive sponsor confirmed")

    payload = _map(client, scene["account"]["id"])
    # The requirement now has a state, but its only evidence is the internal stakeholder record.
    assert "Executive sponsor confirmed" not in json.dumps(payload["artifact"])
    withheld = [w for w in payload["diagnostics"]["withheld"] if w["id"] == instance["id"]]
    assert withheld and withheld[0]["label"] == "Executive sponsor confirmed"
    assert "no client-visible source or shared action" in withheld[0]["reason"]


def test_a_shared_requirement_appears_once_a_shared_action_supports_it(client):
    scene = _scene(client)
    _exec_sponsor(client, scene["program"]["id"], scene["customer"]["id"])
    _launch(client, scene["account"]["id"], scene["program"]["id"])
    instance = _instances(client, scene["account"]["id"], scene["program"]["id"])["exec_identified"]
    _promote(client, "requirement", instance["id"], client_label="Executive sponsor confirmed",
             client_owner_person_id=scene["customer"]["id"])
    _promote(client, "commitment", scene["commitment"]["id"])
    r = client.post(f"/api/plan-instances/{instance['id']}/action-links",
                    json={"commitment_id": scene["commitment"]["id"], "relation": "advances"})
    assert r.status_code in (200, 201), r.text

    payload = _map(client, scene["account"]["id"])
    requirements = [r for p in payload["artifact"]["programs"] for r in p["requirements"]]
    assert [r["what"] for r in requirements] == ["Executive sponsor confirmed"]
    assert requirements[0]["customer_owner"] == "Robin Ashfield"
    assert requirements[0]["client_status"] in ("not_applicable", "in_progress", "complete")
    assert requirements[0]["source"] == "Tracked by shared plan items"


def test_a_shared_requirement_never_carries_its_internal_reasoning(client):
    scene = _scene(client)
    _exec_sponsor(client, scene["program"]["id"], scene["customer"]["id"])
    _launch(client, scene["account"]["id"], scene["program"]["id"])
    instance = _instances(client, scene["account"]["id"], scene["program"]["id"])["exec_identified"]
    _promote(client, "requirement", instance["id"], client_label="Executive sponsor confirmed")
    _promote(client, "commitment", scene["commitment"]["id"])
    client.post(f"/api/plan-instances/{instance['id']}/action-links",
                json={"commitment_id": scene["commitment"]["id"], "relation": "advances"})

    artifact = json.dumps(_map(client, scene["account"]["id"])["artifact"])
    for internal_key in ("definition_of_done", "suggested_action", "evidence", "missing",
                         "provenance", "evaluator_key", "pillar_key", "freshness", "necessity",
                         "reason", "state", "applicability", "waiver", "recorded_complete"):
        assert f'"{internal_key}"' not in artifact, internal_key


def test_demoting_a_requirement_clears_the_promotion_stamp(client):
    scene = _scene(client)
    _launch(client, scene["account"]["id"], scene["program"]["id"])
    instance = _instances(client, scene["account"]["id"], scene["program"]["id"])["exec_identified"]
    _promote(client, "requirement", instance["id"], client_label="Executive sponsor confirmed")
    assert _sql(client, "SELECT client_promoted_on FROM readiness_plan_instances WHERE id=?",
                (instance["id"],))[0]["client_promoted_on"]
    _demote(client, "requirement", instance["id"])
    row = _sql(client, "SELECT client_visible, client_promoted_on, client_promoted_by "
                       "FROM readiness_plan_instances WHERE id=?", (instance["id"],))[0]
    assert row["client_visible"] == 0
    assert row["client_promoted_on"] is None and row["client_promoted_by"] is None


def test_a_client_owner_from_another_account_is_refused(client):
    scene = _scene(client)
    other = _account(client, "Southwind Synthetic")
    stranger = _person(client, other["id"], "Alex Nordholm")
    _launch(client, scene["account"]["id"], scene["program"]["id"])
    instance = _instances(client, scene["account"]["id"], scene["program"]["id"])["exec_identified"]
    r = client.post("/api/map/promote", json={
        "object_type": "requirement", "object_id": instance["id"], "client_visible": True,
        "client_label": "Executive sponsor confirmed", "client_owner_person_id": stranger["id"]})
    assert r.status_code == 422 and "different account" in r.json()["detail"]


# --- §16.4: preview before promoting ---------------------------------------------------------------

def test_promotion_preview_shows_what_a_customer_would_see(client):
    scene = _scene(client)
    r = client.get("/api/map/promotion-preview",
                   params={"object_type": "commitment", "object_id": scene["commitment"]["id"]})
    assert r.status_code == 200, r.text
    preview = r.json()
    assert preview["what"] == "Confirm the data-processing addendum"
    assert preview["customer_owner"] == "Robin Ashfield"
    assert preview["client_status"] == "in_progress"
    # And the record is still not on the plan: previewing is not promoting.
    assert _map(client, scene["account"]["id"])["artifact"]["programs"] == []


def test_promotion_preview_of_a_requirement_says_it_would_not_appear(client):
    scene = _scene(client)
    _launch(client, scene["account"]["id"], scene["program"]["id"])
    instance = _instances(client, scene["account"]["id"], scene["program"]["id"])["exec_identified"]
    r = client.get("/api/map/promotion-preview",
                   params={"object_type": "requirement", "object_id": instance["id"],
                           "client_label": "Executive sponsor confirmed"})
    assert r.status_code == 200, r.text
    preview = r.json()
    assert preview["would_appear"] is False
    assert preview["withheld_reason"]


def test_the_preview_does_not_count_a_shared_action_the_export_will_not_produce(client):
    """§16.7's contract, applied to the preview's own query.

    A requirement earns a client-safe source from a linked action the customer can already see.
    The preview used to look for that action across the whole portfolio while the export looks
    only inside the account's live programs. An account-scoped requirement may link to an action
    in any of the account's programs, so archiving that program left the dry run promising a
    source the export would not produce.
    """
    scene = _scene(client)
    r = client.post(f"/api/accounts/{scene['account']['id']}/plan-instances", json={
        "playbook_key": "renewal-readiness", "playbook_version": 1,
        "anchor_type": "renewal", "anchor_date": "2026-12-01"})
    assert r.status_code == 200, r.text
    instance = sorted(_instances(client, scene["account"]["id"]).items())[0][1]

    retired = _program(client, scene["account"]["id"], "Retired pilot")
    supporting = _task(client, retired["id"], "Gather the renewal evidence pack",
                       internal_owner_id=scene["valence"]["id"],
                       source_reference_id=scene["source"]["id"])
    _promote(client, "task", supporting["id"])
    r = client.post(f"/api/plan-instances/{instance['id']}/action-links",
                    json={"task_id": supporting["id"], "relation": "advances"})
    assert r.status_code in (200, 201), r.text

    def _preview():
        r = client.get("/api/map/promotion-preview",
                       params={"object_type": "requirement", "object_id": instance["id"],
                               "client_label": "Renewal evidence agreed"})
        assert r.status_code == 200, r.text
        return r.json()

    assert _preview()["source"] == "Tracked by shared plan items"

    r = client.post(f"/api/programs/{retired['id']}/archive")
    assert r.status_code in (200, 204), r.text
    preview = _preview()
    # The export cannot see the supporting action any more, so neither may the dry run.
    assert preview["source"] is None
    assert preview["would_appear"] is False
    # And the export agrees: promoting it anyway puts nothing in front of the customer.
    _promote(client, "requirement", instance["id"], client_label="Renewal evidence agreed")
    artifact = _map(client, scene["account"]["id"])["artifact"]
    assert "Renewal evidence agreed" not in json.dumps(artifact)


# --- §16.7: preview and export are the same object -------------------------------------------------

def test_the_saved_document_body_is_the_previewed_markdown(client):
    scene = _scene(client)
    _promote(client, "commitment", scene["commitment"]["id"])
    previewed = _map(client, scene["account"]["id"])["artifact"]["markdown"]
    r = client.post(f"/api/accounts/{scene['account']['id']}/map/document")
    assert r.status_code == 201, r.text
    body = r.json()["document"]["body_markdown"]
    # The generation timestamp is the only thing that legitimately differs between two renders.
    strip = lambda text: "\n".join(l for l in text.splitlines() if not l.startswith("_Generated"))
    assert strip(body) == strip(previewed)


def test_the_markdown_renderer_reads_the_artifact_and_not_the_database(client):
    """§16.7 in its strongest form: a field the API response does not contain cannot be in the
    export, because the renderer is a pure function of the response."""
    from app import shared_plan
    scene = _scene(client)
    _promote(client, "commitment", scene["commitment"]["id"])
    artifact = _map(client, scene["account"]["id"])["artifact"]
    assert shared_plan.render_markdown(artifact) == artifact["markdown"]


# --- §16.6: stamps and source manifests -------------------------------------------------------------

def test_a_saved_plan_records_its_template_audience_and_sources(client):
    scene = _scene(client)
    _promote(client, "commitment", scene["commitment"]["id"])
    _promote(client, "milestone", scene["milestone"]["id"])
    r = client.post(f"/api/accounts/{scene['account']['id']}/map/document")
    doc = r.json()["document"]
    assert doc["template_key"] == "mutual_action_plan" and doc["template_version"] == 2
    assert doc["audience"] == "client_facing" and doc["status"] == "draft"
    assert doc["data_current_through"]

    sources = _sql(client, "SELECT record_type, record_id, visibility_class FROM "
                           "generated_document_sources WHERE document_id=?", (doc["id"],))
    kinds = {s["record_type"] for s in sources}
    assert {"commitment", "milestone"} <= kinds
    assert {s["record_id"] for s in sources} >= {scene["commitment"]["id"], scene["milestone"]["id"]}
    assert {s["visibility_class"] for s in sources} == {"client_facing"}
    # An unpromoted record is not in the manifest either.
    assert scene["internal"]["id"] not in {s["record_id"] for s in sources}


def test_a_fully_sourced_plan_reports_no_source_gaps(client):
    scene = _scene(client)
    _promote(client, "commitment", scene["commitment"]["id"])
    artifact = _map(client, scene["account"]["id"])["artifact"]
    assert artifact["stamp"]["missing_or_stale_sources"] == []
    assert artifact["stamp"]["data_current_through"]
    # The synthetic "Other agreed work" heading has no source of its own and must not be counted
    # as an item missing one — it is a grouping label, not a record.
    assert [g["milestone"] for g in artifact["programs"][0]["groups"]] == ["Other agreed work"]


def test_the_stamp_names_a_shared_item_whose_source_was_withdrawn(client):
    """`missing_or_stale_sources` shipped permanently empty, which read as "every source is
    accounted for" on a plan where one was not.

    Promotion demands a source, so the gap opens *after* the fact: the cited document is archived
    and the item keeps its place on the customer's plan with a blank source column. The missing
    half is answerable from the records and is now stated. The stale half is not — no freshness
    threshold applies to a reference or a meeting, and inventing one would be a benchmark in code.
    """
    scene = _scene(client)
    _promote(client, "commitment", scene["commitment"]["id"])
    # There is no archive endpoint for a source reference, so the withdrawal is written directly.
    _sql(client, "UPDATE source_references SET archived = 1 WHERE id = ?", (scene["source"]["id"],))

    artifact = _map(client, scene["account"]["id"])["artifact"]
    assert [a["source"] for a in _actions(artifact)] == [None]
    assert artifact["stamp"]["missing_or_stale_sources"] == \
        ["no sourced items have been shared to this plan",
         "1 shared item carries no source on record"]
    assert artifact["stamp"]["data_current_through"] is None
    # And the reader of the exported body is told, rather than left to infer it from a blank column.
    assert "carries no source on record" in artifact["markdown"]

    # A second, still-sourced item answers the first gap and leaves the second one counted.
    second = _commitment(client, scene["program"]["id"], scene["customer"]["id"],
                         scene["valence"]["id"], "Agree the pilot success measures",
                         source_interaction_id=scene["interaction"]["id"])
    _promote(client, "commitment", second["id"])
    stamp = _map(client, scene["account"]["id"])["artifact"]["stamp"]
    assert stamp["data_current_through"]
    assert stamp["missing_or_stale_sources"] == ["1 shared item carries no source on record"]


def test_the_five_named_outputs_are_all_stamped_with_a_template(client):
    """§16.6 lists five outputs. An unstamped body is unattributable the moment a renderer moves."""
    from app import generators
    for kind in ("mutual_action_plan", "value_review", "team_update",
                 "internal_review_packet", "pre_call_brief"):
        assert generators.TEMPLATE_VERSIONS.get(kind), kind
        assert generators.template_stamp(kind) == {"template_key": kind,
                                                   "template_version": generators.TEMPLATE_VERSIONS[kind]}


def test_a_generated_client_output_carries_its_template(client):
    scene = _scene(client)
    r = client.post(f"/api/accounts/{scene['account']['id']}/documents",
                    json={"kind": "value_review"})
    assert r.status_code == 201, r.text
    doc = r.json()
    assert doc["template_key"] == "value_review" and doc["template_version"] == 1


# --- §16.8: demotion does not rewrite history --------------------------------------------------------

def test_demotion_changes_future_plans_and_leaves_the_old_artifact_alone(client):
    scene = _scene(client)
    _promote(client, "commitment", scene["commitment"]["id"])
    saved = client.post(f"/api/accounts/{scene['account']['id']}/map/document").json()["document"]
    assert "data-processing addendum" in saved["body_markdown"]

    _demote(client, "commitment", scene["commitment"]["id"])
    live = _map(client, scene["account"]["id"])["artifact"]
    assert live["programs"] == []

    stored = client.get(f"/api/documents/{saved['id']}").json()
    assert stored["body_markdown"] == saved["body_markdown"]
    assert "data-processing addendum" in stored["body_markdown"]
    # The manifest is history too: it still names what the artifact was built from.
    sources = _sql(client, "SELECT record_id FROM generated_document_sources WHERE document_id=?",
                   (saved["id"],))
    assert scene["commitment"]["id"] in {s["record_id"] for s in sources}


# --- §16.5: the projection is a query, not a filter --------------------------------------------------

def test_the_projection_module_never_selects_a_whole_row(client):
    """§16.5's rule made mechanical. An internal column that never enters the process cannot leak
    from a renderer, an accessibility label, hidden DOM, or an analytics payload."""
    import ast
    module = pathlib.Path(__file__).resolve().parents[1] / "app" / "shared_plan.py"
    tree = ast.parse(module.read_text(encoding="utf-8"))
    # Only real string literals count. The module's own prose says the words "SELECT *" while
    # explaining why it does not contain one, and a docstring is not a query.
    docstrings = {id(ast.get_docstring(node, clean=False)) for node in ast.walk(tree)
                  if isinstance(node, (ast.Module, ast.FunctionDef, ast.ClassDef))}
    offenders = [n.value for n in ast.walk(tree)
                 if isinstance(n, ast.Constant) and isinstance(n.value, str)
                 and id(n.value) not in docstrings and "select *" in n.value.lower()]
    assert offenders == []


def test_the_internal_columns_of_a_promoted_record_do_not_travel(client):
    """A promoted commitment brings its description, owners, date, status and source label — not
    its close note, not its acknowledgement, not its commitment class."""
    scene = _scene(client)
    client.patch(f"/api/commitments/{scene['commitment']['id']}",
                 json={"acknowledged_by_id": scene["customer"]["id"]})
    _promote(client, "commitment", scene["commitment"]["id"])
    artifact = json.dumps(_map(client, scene["account"]["id"])["artifact"])
    for internal_key in ("commitment_class", "acknowledged_by_id", "close_note", "internal_owner_id",
                         "responsible_party_id", "source_reference_id", "source_interaction_id",
                         "at_risk", "archived"):
        assert internal_key not in artifact, internal_key


def test_the_source_label_of_an_interaction_is_a_date_and_not_its_content(client):
    scene = _scene(client)
    interaction = _interaction(client, scene["account"]["id"], scene["program"]["id"],
                               summary="Pricing pushback from procurement")
    task = _task(client, scene["program"]["id"], "Share the rollout timeline",
                 internal_owner_id=scene["valence"]["id"],
                 source_interaction_id=interaction["id"])
    _promote(client, "task", task["id"])
    artifact = _map(client, scene["account"]["id"])["artifact"]
    assert "Pricing pushback" not in json.dumps(artifact)
    assert any("Agreed in a meeting on" in (a["source"] or "") for a in _actions(artifact))


def test_diagnostics_stay_out_of_the_artifact(client):
    scene = _scene(client)
    _launch(client, scene["account"]["id"], scene["program"]["id"])
    instance = _instances(client, scene["account"]["id"], scene["program"]["id"])["exec_identified"]
    _promote(client, "requirement", instance["id"], client_label="Executive sponsor confirmed")
    payload = _map(client, scene["account"]["id"])
    assert payload["diagnostics"]["withheld"]
    for key in ("withheld", "unshared_counts", "source_manifest", "diagnostics"):
        assert key not in payload["artifact"]


# --- §16.2: what is never allowed -------------------------------------------------------------------

def test_a_decision_cannot_be_promoted(client):
    """§16.2's allowlist does not include decisions, so there is no promotion path to try."""
    r = client.post("/api/map/promote", json={"object_type": "decision", "object_id": "whatever",
                                              "client_visible": True})
    assert r.status_code == 422
    r = client.get("/api/map/promotion-preview",
                   params={"object_type": "decision", "object_id": "whatever"})
    assert r.status_code == 422


def test_a_risk_or_issue_has_no_promotion_path(client):
    for object_type in ("risk", "issue"):
        r = client.post("/api/map/promote", json={"object_type": object_type, "object_id": "x",
                                                  "client_visible": True})
        assert r.status_code == 422, object_type


# --- §16.5: summary and upcoming ---------------------------------------------------------------------

def test_the_summary_counts_milestones_and_never_names_the_internal_phase(client):
    scene = _scene(client)
    _promote(client, "milestone", scene["milestone"]["id"])
    artifact = _map(client, scene["account"]["id"])["artifact"]
    summary = artifact["summary"]
    assert summary["milestones_shared"] == 1 and summary["milestones_complete"] == 0
    assert summary["next_milestone"]["name"] == "Europe go-live"
    # The program's phase is `launch`. It is an internal commercial vocabulary and does not travel.
    for phase in ("foundation", "launch", "programmatic", "expansion", "renewal"):
        assert f'"{phase}"' not in json.dumps(artifact), phase


def test_a_past_dated_milestone_is_not_listed_as_upcoming(client):
    scene = _scene(client)
    past = _milestone(client, scene["program"]["id"], "Pilot wrap-up", target_date="2020-01-31",
                      source_interaction_id=scene["interaction"]["id"])
    _promote(client, "milestone", past["id"])
    _promote(client, "milestone", scene["milestone"]["id"])
    artifact = _map(client, scene["account"]["id"])["artifact"]
    assert [m["name"] for m in artifact["upcoming_milestones"]] == ["Europe go-live"]
    # It is still in the plan itself — it is only the "confirmed upcoming" block it stays out of.
    assert "Pilot wrap-up" in [g["milestone"] for p in artifact["programs"] for g in p["groups"]]


def test_every_withheld_reason_completes_the_same_sentence(client):
    """The operator surface renders `Held back because {reason}.`

    Reasons are authored on the server and shown verbatim, so they have to be clauses of one shape.
    A reason that arrived as its own capitalized sentence would force the UI to reformat text it
    did not write, and reformatting is one edit away from paraphrasing a refusal.
    """
    from app import shared_plan
    readings = [
        {"legacy": True},
        {"applicability_override": {"kind": "suppression"}},
        {"waiver": {"id": "w1"}},
        {"state": "conflicted"},
        {"state": "unknown"},
        {"state": "met", "freshness": "stale"},
        {"state": "brand_new"},
    ]
    reasons = [shared_plan._requirement_status(r)[1] for r in readings]
    assert all(reasons), reasons
    for reason in reasons:
        assert reason[0].islower(), reason
        assert not reason.endswith("."), reason
        # Each clause carries its own subject, so the view never has to supply a linking word. An
        # earlier build did supply one, and the reasons that already began "it is ..." then read as
        # "held back because it it is ..." while this one read as "because it no readiness reading".
        # `frontend/src/sharedPlan.js:withheldSentence` is the other half of the contract.
        assert len(reason.split()) >= 4, reason
