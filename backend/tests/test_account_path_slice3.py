"""Acceptance tests for ACCOUNT-PATH-SPEC.md Slice 3 — playbooks, plan instances, exceptions.

These are written to try to make the planning layer overreach. A plan should never be able to
assert that something is true: not by carrying a legacy checkbox, not by excusing a requirement,
not by upgrading to a version that drops the failing condition, and not by putting a due date next
to a state and letting the date win. Each test asserts the honest answer instead.
"""
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


# --- fixture helpers -------------------------------------------------------------------------

def _account(c, name="Northwind Synthetic"):
    r = c.post("/api/accounts", json={"name": name})
    assert r.status_code == 201, r.text
    return r.json()


def _program(c, account_id, name, phase="launch"):
    r = c.post("/api/programs", json={"account_id": account_id, "name": name, "phase": phase})
    assert r.status_code == 201, r.text
    return r.json()


def _instantiate(c, account_id, expect=200, **body):
    r = c.post(f"/api/accounts/{account_id}/plan-instances", json=body)
    assert r.status_code == expect, r.text
    return r.json()


def _launch(c, account_id, program_id, anchor="2026-07-01", version=1, **kw):
    return _instantiate(c, account_id, playbook_key="enterprise-launch",
                        playbook_version=version, program_id=program_id,
                        anchor_type="kickoff", anchor_date=anchor, **kw)


def _plan(c, account_id, program_id=None):
    url = f"/api/accounts/{account_id}/plan-instances"
    if program_id:
        url += f"?program_id={program_id}"
    r = c.get(url)
    assert r.status_code == 200, r.text
    return r.json()


def _readiness(c, account_id, program_id=None):
    url = f"/api/accounts/{account_id}/readiness"
    if program_id:
        url += f"?program_id={program_id}"
    r = c.get(url)
    assert r.status_code == 200, r.text
    return r.json()


def _path(c, account_id, program_id=None):
    url = f"/api/accounts/{account_id}/execution-path"
    if program_id:
        url += f"?program_id={program_id}"
    r = c.get(url)
    assert r.status_code == 200, r.text
    return r.json()


def _component(readiness, pillar_key, requirement_key):
    for pillar in readiness["pillars"]:
        if pillar["key"] != pillar_key:
            continue
        for component in pillar["components"]:
            if component.get("definition_key") == requirement_key:
                return pillar, component
    for entry in readiness.get("programs", []):
        for pillar in entry["pillars"]:
            if pillar["key"] != pillar_key:
                continue
            for component in pillar["components"]:
                if component.get("definition_key") == requirement_key:
                    return pillar, component
    raise AssertionError(f"{pillar_key}/{requirement_key} not found")


def _by_key(payload):
    return {row["requirement_key"]: row for row in payload["requirements"]}


# --- the library and instantiation ------------------------------------------------------------

def test_playbook_library_keeps_every_version_selectable(client):
    """Unlike definitions, playbook versions do not retire each other.

    An account stays on the version it instantiated, so the version it is on must remain readable.
    A "one live version" rule here would make an active plan un-inspectable the moment a new
    template shipped.
    """
    rows = client.get("/api/readiness/playbooks").json()["playbooks"]
    versions = {(p["key"], p["version"]) for p in rows}
    assert ("enterprise-launch", 1) in versions
    assert ("enterprise-launch", 2) in versions
    for playbook in rows:
        assert playbook["entries"], f"{playbook['key']} v{playbook['version']} has no entries"
        for entry in playbook["entries"]:
            assert entry["necessity"] in ("required", "optional")


def test_instantiation_resolves_relative_dates_and_keeps_the_rule(client):
    """§13.9: relative dates resolve correctly *and* preserve their source rules.

    Keeping the rule is what makes a re-anchor possible later without guessing which dates were
    hand-edited.
    """
    account = _account(client)
    program = _program(client, account["id"], "Support Deflection")
    plan = _launch(client, account["id"], program["id"], anchor="2026-07-01")

    instances = {i["requirement_key"]: i for i in plan["instances"]}
    assert instances["exec_identified"]["due_date"] == "2026-07-15"
    assert instances["exec_identified"]["due_rule"] == {"anchor": "kickoff", "offset_days": 14}
    # A leap-safe boundary: 60 days past 1 July lands in August, not "sometime".
    assert instances["exec_engaged"]["due_date"] == "2026-08-30"
    # An entry with no offset carries no date rather than inventing today.
    assert instances["budget_authority_evidence"]["due_date"] is None
    assert instances["budget_authority_evidence"]["due_rule"]["offset_days"] is None


def test_instantiation_never_marks_anything_complete(client):
    """A plan states an expectation. Seeding it as partly done would assert unseen evidence."""
    account = _account(client)
    program = _program(client, account["id"], "Support Deflection")
    plan = _launch(client, account["id"], program["id"])
    assert all(i["recorded_complete"] is False for i in plan["instances"])
    assert all(i["recorded_complete_on"] is None for i in plan["instances"])
    # And nothing readiness reports moved to met on the strength of a plan existing.
    states = {c["state"] for p in _readiness(client, account["id"], program["id"])["pillars"]
              for c in p["components"]}
    assert "met" not in states


def test_duplicate_active_plan_is_rejected_unless_it_is_an_upgrade(client):
    account = _account(client)
    program = _program(client, account["id"], "Support Deflection")
    _launch(client, account["id"], program["id"])
    body = {"playbook_key": "enterprise-launch", "playbook_version": 1,
            "program_id": program["id"], "anchor_type": "kickoff", "anchor_date": "2026-07-01"}
    r = client.post(f"/api/accounts/{account['id']}/plan-instances", json=body)
    assert r.status_code == 409
    assert "already exists" in r.json()["detail"]


def test_scope_validation_rejects_the_wrong_shape_of_request(client):
    account = _account(client)
    other = _account(client, "Contoso Synthetic")
    program = _program(client, other["id"], "Elsewhere")

    # A program-scoped playbook with no program.
    r = client.post(f"/api/accounts/{account['id']}/plan-instances", json={
        "playbook_key": "enterprise-launch", "playbook_version": 1,
        "anchor_type": "kickoff", "anchor_date": "2026-07-01"})
    assert r.status_code == 422 and "needs a program_id" in r.json()["detail"]

    # An account-scoped playbook handed a program.
    mine = _program(client, account["id"], "Support Deflection")
    r = client.post(f"/api/accounts/{account['id']}/plan-instances", json={
        "playbook_key": "renewal-readiness", "playbook_version": 1, "program_id": mine["id"],
        "anchor_type": "renewal", "anchor_date": "2027-01-01"})
    assert r.status_code == 422 and "omit program_id" in r.json()["detail"]

    # Another account's program is an error, never a silent fall back to account scope.
    r = client.post(f"/api/accounts/{account['id']}/plan-instances", json={
        "playbook_key": "enterprise-launch", "playbook_version": 1, "program_id": program["id"],
        "anchor_type": "kickoff", "anchor_date": "2026-07-01"})
    assert r.status_code == 404

    # An anchor the playbook version does not allow.
    r = client.post(f"/api/accounts/{account['id']}/plan-instances", json={
        "playbook_key": "enterprise-launch", "playbook_version": 1, "program_id": mine["id"],
        "anchor_type": "renewal_date", "anchor_date": "2027-01-01"})
    assert r.status_code == 422 and "not allowed" in r.json()["detail"]


def test_a_required_entry_cannot_be_excluded_at_instantiation(client):
    """Excluding a required entry would let the plan disagree with the playbook it claims to be.

    The governed alternative — a `not_applicable` decision with a reason and an actor — is named
    in the error, because refusing without an alternative just invites a worse workaround.
    """
    account = _account(client)
    program = _program(client, account["id"], "Support Deflection")
    r = client.post(f"/api/accounts/{account['id']}/plan-instances", json={
        "playbook_key": "enterprise-launch", "playbook_version": 1, "program_id": program["id"],
        "anchor_type": "kickoff", "anchor_date": "2026-07-01",
        "excluded_requirements": ["exec_identified"]})
    assert r.status_code == 422
    assert "not applicable" in r.json()["detail"]

    ok = _launch(client, account["id"], program["id"],
                 excluded_requirements=["budget_authority_evidence"])
    assert "budget_authority_evidence" not in {i["requirement_key"] for i in ok["instances"]}


def test_account_and_program_plans_stay_independently_scoped(client):
    """Two programs on one account keep their own dates. A shared account plan is visible in both.

    Merging either direction would put one program's schedule on another program's condition.
    """
    account = _account(client)
    first = _program(client, account["id"], "Support Deflection")
    second = _program(client, account["id"], "Sales Enablement")
    _launch(client, account["id"], first["id"], anchor="2026-07-01")
    _launch(client, account["id"], second["id"], anchor="2026-09-01")
    _instantiate(client, account["id"], playbook_key="renewal-readiness", playbook_version=1,
                 anchor_type="renewal", anchor_date="2027-01-01")

    first_rows = _by_key(_plan(client, account["id"], first["id"]))
    second_rows = _by_key(_plan(client, account["id"], second["id"]))
    assert first_rows["exec_identified"]["due_date"] == "2026-07-15"
    assert second_rows["exec_identified"]["due_date"] == "2026-09-15"
    # The account-wide renewal plan is in force inside a selected program too.
    assert "budget_owner_engagement" in first_rows          # from the account-wide renewal plan
    assert first_rows["budget_owner_engagement"]["due_date"] == "2026-10-03"   # 90 days before
    assert first_rows["budget_owner_engagement"] == second_rows["budget_owner_engagement"]


# --- version pinning and upgrade ---------------------------------------------------------------

def test_editing_a_template_does_not_mutate_an_existing_plan(client):
    """§13.9. v2 exists and differs; the v1 plan is untouched until an upgrade is applied."""
    account = _account(client)
    program = _program(client, account["id"], "Support Deflection")
    before = _launch(client, account["id"], program["id"], version=1)
    keys_before = {i["requirement_key"] for i in before["instances"]}
    assert "champion_second_thread" not in keys_before   # v2 adds it

    after = _plan(client, account["id"], program["id"])
    assert {r["requirement_key"] for r in after["requirements"]} == keys_before
    assert all(r["playbook"]["version"] == 1 for r in after["requirements"])


def test_upgrade_preview_shows_every_kind_of_change_and_applies_nothing(client):
    account = _account(client)
    program = _program(client, account["id"], "Support Deflection")
    _launch(client, account["id"], program["id"], version=1)

    r = client.post(f"/api/accounts/{account['id']}/plan-instances/upgrade-preview", json={
        "playbook_key": "enterprise-launch", "to_version": 2, "program_id": program["id"]})
    assert r.status_code == 200, r.text
    diff = r.json()
    assert diff["applied"] is False
    assert [a["requirement_key"] for a in diff["additions"]] == ["champion_second_thread"]
    assert [x["requirement_key"] for x in diff["removals"]] == ["budget_authority_evidence"]
    timing = {t["requirement_key"]: t for t in diff["timing_changes"]}
    assert timing["exec_engaged"]["from_due_date"] == "2026-08-30"
    assert timing["exec_engaged"]["to_due_date"] == "2026-08-15"
    assert [n["requirement_key"] for n in diff["necessity_changes"]] == ["breadth_layer_spread"]

    # Preview means preview: the live plan is still v1 with its v1 dates.
    rows = _by_key(_plan(client, account["id"], program["id"]))
    assert rows["exec_engaged"]["due_date"] == "2026-08-30"
    assert "champion_second_thread" not in rows


def test_upgrade_applies_the_previewed_diff_and_keeps_the_anchor(client):
    account = _account(client)
    program = _program(client, account["id"], "Support Deflection")
    _launch(client, account["id"], program["id"], version=1)
    r = client.post(f"/api/accounts/{account['id']}/plan-instances/upgrade", json={
        "playbook_key": "enterprise-launch", "to_version": 2, "program_id": program["id"]})
    assert r.status_code == 200, r.text
    applied = r.json()
    assert applied["applied"] is True
    assert applied["plan"]["playbook_version"] == 2
    assert applied["plan"]["anchor_date"] == "2026-07-01"
    assert applied["plan"]["supersedes_id"]

    rows = _by_key(_plan(client, account["id"], program["id"]))
    assert "champion_second_thread" in rows
    assert "budget_authority_evidence" not in rows
    assert rows["exec_engaged"]["due_date"] == "2026-08-15"
    assert rows["breadth_layer_spread"]["necessity"] == "optional"
    # Exactly one live plan for the scope, so the superseded rows cannot show up twice.
    assert len([p for p in _plan(client, account["id"], program["id"])["plans"]
                if p["status"] == "active" and p["playbook_key"] == "enterprise-launch"]) == 1


# --- exceptions -------------------------------------------------------------------------------

def test_not_applicable_records_a_reason_and_suppresses_without_changing_evidence(client):
    """§13.9's longest criterion, checked one clause at a time.

    The suppressed component is *reported*, not dropped. If it disappeared, a pillar could reach
    `met` because its only failing condition was excused — which is a suppression buying a pass.
    """
    account = _account(client)
    program = _program(client, account["id"], "Support Deflection")
    _launch(client, account["id"], program["id"])
    before = _component(_readiness(client, account["id"], program["id"]),
                        "executive_sponsorship", "exec_engaged")[1]

    r = client.post(f"/api/accounts/{account['id']}/readiness-exceptions", json={
        "requirement_key": "exec_engaged", "kind": "not_applicable", "program_id": program["id"],
        "reason": "No executive tier exists in this synthetic pilot scope."})
    assert r.status_code == 200, r.text
    assert r.json()["exception"]["actor_id"]
    assert r.json()["exception"]["decided_on"]

    pillar, component = _component(_readiness(client, account["id"], program["id"]),
                                   "executive_sponsorship", "exec_engaged")
    assert component["state"] == "not_applicable"
    assert component["applicability_override"]["reason"].startswith("No executive tier")
    # The other components' evidence and states are untouched by someone else's exception.
    others = [c for c in pillar["components"] if c["definition_key"] != "exec_engaged"]
    assert all(c["state"] != "not_applicable" for c in others)
    assert pillar["suppressed_count"] == 1
    assert "marked not applicable" in pillar["reason"]
    # The pillar did not become met by losing a condition.
    assert pillar["state"] != "met"
    assert before["state"] != "met"


def test_a_fully_suppressed_pillar_reports_not_applicable_not_met(client):
    account = _account(client)
    program = _program(client, account["id"], "Support Deflection")
    readiness = _readiness(client, account["id"], program["id"])
    pillar = next(p for p in readiness["pillars"] if p["key"] == "executive_sponsorship")
    for component in pillar["components"]:
        r = client.post(f"/api/accounts/{account['id']}/readiness-exceptions", json={
            "requirement_key": component["definition_key"], "kind": "not_applicable",
            "program_id": program["id"],
            "reason": "Out of scope for this synthetic pilot engagement."})
        assert r.status_code == 200, r.text
    after = next(p for p in _readiness(client, account["id"], program["id"])["pillars"]
                 if p["key"] == "executive_sponsorship")
    assert after["state"] == "not_applicable"
    assert after["applicability"] == "not_applicable"


def test_a_waiver_accepts_the_gap_without_satisfying_it(client):
    """A waiver is not a synonym for `not_applicable`, and it is certainly not a `met`.

    The state stays exactly where the evidence put it; only the outstanding ask is silenced.
    """
    account = _account(client)
    program = _program(client, account["id"], "Support Deflection")
    _launch(client, account["id"], program["id"])
    before = _component(_readiness(client, account["id"], program["id"]),
                        "quantified_value", "value_baseline_locked")[1]

    r = client.post(f"/api/accounts/{account['id']}/readiness-exceptions", json={
        "requirement_key": "value_baseline_locked", "kind": "waiver", "program_id": program["id"],
        "reason": "Baseline deferred to the next measurement window by agreement.",
        "expires_on": utc_day(90)})
    assert r.status_code == 200, r.text

    pillar, component = _component(_readiness(client, account["id"], program["id"]),
                                   "quantified_value", "value_baseline_locked")
    assert component["state"] == before["state"] != "met"
    assert component["waiver"]["kind"] == "waiver"
    assert component["missing"] == []
    assert pillar["waived_count"] == 1
    assert "waived" in pillar["reason"]
    assert pillar["state"] != "met"


def test_a_waiver_must_carry_an_expiry_and_a_real_reason(client):
    account = _account(client)
    program = _program(client, account["id"], "Support Deflection")
    r = client.post(f"/api/accounts/{account['id']}/readiness-exceptions", json={
        "requirement_key": "value_baseline_locked", "kind": "waiver", "program_id": program["id"],
        "reason": "A permanent gap wearing a temporary label is still permanent."})
    assert r.status_code == 422 and "expiry" in r.json()["detail"]

    r = client.post(f"/api/accounts/{account['id']}/readiness-exceptions", json={
        "requirement_key": "value_baseline_locked", "kind": "not_applicable",
        "program_id": program["id"], "reason": "n/a"})
    assert r.status_code == 422 and "at least" in r.json()["detail"]


def test_exception_history_keeps_revoked_and_lapsed_decisions(client):
    """A suppression that vanished when it stopped applying would leave an unexplained change."""
    account = _account(client)
    program = _program(client, account["id"], "Support Deflection")
    first = client.post(f"/api/accounts/{account['id']}/readiness-exceptions", json={
        "requirement_key": "exec_engaged", "kind": "not_applicable", "program_id": program["id"],
        "reason": "Executive tier is out of scope for the pilot."}).json()["exception"]
    # A replacing decision revokes the prior one rather than editing it.
    second = client.post(f"/api/accounts/{account['id']}/readiness-exceptions", json={
        "requirement_key": "exec_engaged", "kind": "not_applicable", "program_id": program["id"],
        "reason": "Restated after the scope review; still out of scope."}).json()["exception"]
    r = client.post(f"/api/readiness-exceptions/{second['id']}/revoke", json={
        "reason": "An executive sponsor was named at the quarterly review."})
    assert r.status_code == 200, r.text

    history = client.get(
        f"/api/accounts/{account['id']}/readiness-exceptions/exec_engaged"
        f"?program_id={program['id']}").json()["history"]
    by_id = {h["id"]: h for h in history}
    assert by_id[first["id"]]["status"] == "revoked"
    assert by_id[second["id"]]["status"] == "revoked"
    assert by_id[second["id"]]["revoked_reason"].startswith("An executive sponsor")
    # And with nothing live, the component is evaluated again on its own evidence.
    _, component = _component(_readiness(client, account["id"], program["id"]),
                              "executive_sponsorship", "exec_engaged")
    assert component["state"] != "not_applicable"
    assert component.get("applicability_override") is None


def test_a_program_exception_does_not_reach_another_program(client):
    account = _account(client)
    first = _program(client, account["id"], "Support Deflection")
    second = _program(client, account["id"], "Sales Enablement")
    client.post(f"/api/accounts/{account['id']}/readiness-exceptions", json={
        "requirement_key": "exec_engaged", "kind": "not_applicable", "program_id": first["id"],
        "reason": "Executive tier is out of scope for this program only."})
    _, suppressed = _component(_readiness(client, account["id"], first["id"]),
                               "executive_sponsorship", "exec_engaged")
    _, untouched = _component(_readiness(client, account["id"], second["id"]),
                              "executive_sponsorship", "exec_engaged")
    assert suppressed["state"] == "not_applicable"
    assert untouched["state"] != "not_applicable"


# --- checklist compatibility --------------------------------------------------------------------

def _onboard_pre_merge(client, account_id, kickoff="2026-07-01"):
    """Onboard, then add the `checklist_items` rows onboarding used to create.

    Migration 0051 merged the three launch standards, and onboarding now seeds phase-gate items and
    a plan instance instead of twenty checklist rows. The compatibility layer exists for exactly the
    accounts that were onboarded *before* that, so its fixture has to be legacy data — reading it
    out of today's seed would mean the tests below stop covering the case the moment the seed is
    correct. These rows are written from the retired template, straight to the table, so they are
    the shape the old code path actually left behind.
    """
    r = client.post(f"/api/accounts/{account_id}/onboard",
                    json={"kickoff_date": kickoff, "program_name": "Support Deflection"})
    assert r.status_code == 201, r.text
    onboarded = r.json()

    import yaml
    from app import repo
    from app.db import connect
    from app.onboarding import TEMPLATES_DIR, _offset

    template = yaml.safe_load(
        (TEMPLATES_DIR / "launch_checklist.yaml").read_text(encoding="utf-8"))
    conn = connect()
    try:
        for section, items in template.items():
            for it in items:
                repo.insert(conn, "checklist_items", {
                    "account_id": account_id, "program_id": onboarded["program_id"],
                    "template_key": f"{section}:{it['label']}", "section": section,
                    "label": it["label"], "detail": it.get("detail"),
                    "fills_field": it.get("fills_field"),
                    "due_offset_days": it.get("due_offset_days"),
                    "due_date": _offset(kickoff, it.get("due_offset_days")),
                }, object_type="checklist_item")
    finally:
        conn.close()
    return onboarded


def _checklist_item(client, account_id, label):
    rows = client.get(f"/api/checklist-items?account_id={account_id}").json()
    rows = rows["items"] if isinstance(rows, dict) else rows
    return next(r for r in rows if r["label"] == label)


def test_compatibility_maps_only_exact_template_keys(client):
    """§13.5.2. A label that reads like a requirement is not a mapping, and never becomes one."""
    account = _account(client)
    _onboard_pre_merge(client, account["id"])
    report = client.post(f"/api/accounts/{account['id']}/checklist-compatibility",
                         json={"dry_run": True}).json()
    mapped_keys = {m["template_key"] for m in report["mapped"]}
    assert mapped_keys <= {"first_call:Identify the budget owner",
                           "first_two_weeks:Scorecard and budget owner named",
                           "first_30_days:Baselines captured"}
    assert report["counts"]["unmatched"] > 0
    # "Lock a baseline" and "Baselines captured" describe the same thing in different words; only
    # the explicit key mapped, and every other item stayed a legacy row.
    assert all(u["reason"] == "no exact template_key mapping" for u in report["unmatched"])


def test_a_done_checklist_item_never_acquires_a_readiness_state(client):
    """§13.9. The tick is carried as a planning fact and reported as an evidence gap."""
    account = _account(client)
    _onboard_pre_merge(client, account["id"])
    item = _checklist_item(client, account["id"], "Baselines captured")
    assert client.patch(f"/api/checklist-items/{item['id']}",
                        json={"status": "done"}).status_code == 200

    report = client.post(f"/api/accounts/{account['id']}/checklist-compatibility", json={}).json()
    carried = next(m for m in report["mapped"] if m["requirement_key"] == "value_baseline_locked")
    assert carried["recorded_complete"] is True
    flagged = {e["requirement_key"] for e in report["evidence_missing"]}
    assert "value_baseline_locked" in flagged

    program_id = item["program_id"]
    _, component = _component(_readiness(client, account["id"], program_id),
                              "quantified_value", "value_baseline_locked")
    assert component["state"] != "met"
    rows = _by_key(_plan(client, account["id"], program_id))
    assert rows["value_baseline_locked"]["recorded_complete"] is True
    assert rows["value_baseline_locked"]["state"] != "met"


def test_an_na_checklist_item_is_proposed_not_applied(client):
    """Suppressing a condition is a governed decision with an actor. A migration is not one."""
    account = _account(client)
    _onboard_pre_merge(client, account["id"])
    item = _checklist_item(client, account["id"], "Identify the budget owner")
    client.patch(f"/api/checklist-items/{item['id']}",
                 json={"status": "na", "answer_note": "Funding is centrally allocated here."})

    report = client.post(f"/api/accounts/{account['id']}/checklist-compatibility", json={}).json()
    proposed = [m for m in report["mapped"] if m["proposed_exception"]]
    assert proposed, "an `na` item should propose an exception"
    assert proposed[0]["proposed_exception"]["kind"] == "not_applicable"
    # Proposed, not applied: no exception row exists until an operator records one.
    history = client.get(
        f"/api/accounts/{account['id']}/readiness-exceptions/budget_authority_evidence"
    ).json()["history"]
    assert history == []


def test_compatibility_is_idempotent_and_reports_ambiguity(client):
    """A rerun updates in place. Two items mapping to one requirement is named, never merged."""
    account = _account(client)
    _onboard_pre_merge(client, account["id"])
    first = client.post(f"/api/accounts/{account['id']}/checklist-compatibility", json={}).json()
    second = client.post(f"/api/accounts/{account['id']}/checklist-compatibility", json={}).json()
    assert first["counts"]["created"] > 0
    assert second["counts"]["created"] == 0
    assert second["counts"]["mapped"] == first["counts"]["mapped"]

    # One scope holds one instance of a requirement, so the two seeded budget-owner keys collide
    # on purpose. The second is reported and left as a legacy item rather than overwriting.
    assert first["counts"]["ambiguous"] == 1
    ambiguity = first["ambiguous"][0]
    assert ambiguity["requirement_key"] == "budget_authority_evidence"
    assert ambiguity["kept_checklist_item_id"] != ambiguity["other_checklist_item_id"]


def test_unmatched_checklist_items_stay_readable_as_legacy(client):
    account = _account(client)
    _onboard_pre_merge(client, account["id"])
    client.post(f"/api/accounts/{account['id']}/checklist-compatibility", json={})
    plan = _plan(client, account["id"])
    assert plan["legacy_items"], "unmatched items must stay visible"
    for row in plan["legacy_items"]:
        # A legacy row carries no readiness axes at all: a synthesised state would be a second,
        # weaker source of truth beside the projection.
        assert row["legacy"] is True
        assert row["state"] is None and row["freshness"] is None and row["applicability"] is None


def test_checklist_items_are_not_deleted_by_the_migration(client):
    """§13.5's closing note. Removal needs a separate deprecation decision."""
    account = _account(client)
    _onboard_pre_merge(client, account["id"])
    before = client.get(f"/api/checklist-items?account_id={account['id']}").json()
    before = before["items"] if isinstance(before, dict) else before
    client.post(f"/api/accounts/{account['id']}/checklist-compatibility", json={})
    after = client.get(f"/api/checklist-items?account_id={account['id']}").json()
    after = after["items"] if isinstance(after, dict) else after
    assert len(after) == len(before) > 0


# --- Execution Path integration -----------------------------------------------------------------

def test_due_dates_ride_beside_readiness_without_moving_a_state(client):
    account = _account(client)
    program = _program(client, account["id"], "Support Deflection")
    _launch(client, account["id"], program["id"], anchor="2020-01-01")   # long overdue
    payload = _path(client, account["id"], program["id"])
    rows = {r["requirement_key"]: r
            for r in payload["work"]["account_essentials"]["requirements"]["requirements"]}
    overdue = rows["exec_identified"]
    assert overdue["overdue"] is True
    assert overdue["due_date"] == "2020-01-15"
    # Overdue is a statement about the plan. The four readiness axes are unchanged by it.
    _, component = _component(_readiness(client, account["id"], program["id"]),
                              "executive_sponsorship", "exec_identified")
    assert overdue["state"] == component["state"]
    assert overdue["freshness"] == component["freshness"]


def test_suggested_actions_stay_out_of_canonical_work(client):
    """A suggestion is a proposal for a Task. Ranking it against real work would let it win."""
    account = _account(client)
    program = _program(client, account["id"], "Support Deflection")
    _launch(client, account["id"], program["id"])
    payload = _path(client, account["id"], program["id"])
    requirements = payload["work"]["account_essentials"]["requirements"]
    assert requirements["gaps"], "a fresh account should have required gaps"
    assert any(r["suggested_action"] for r in requirements["requirements"])
    # None of them entered the ranked queue, and none carries a band.
    for row in payload["work"]["you_own"]:
        assert not row["id"].startswith("requirement:")
    assert all("band" not in r for r in requirements["requirements"])
    # `Create action` prefills a native form and does not claim a durable link yet (§13.8).
    prefilled = next(r for r in requirements["requirements"] if r["create_action_prefill"])
    assert prefilled["create_action_prefill"]["linked"] is False
    # Slice 5 connected the link store, so the prefill's `linked: False` is now the honest answer
    # to a live question rather than a placeholder: the durable link exists as a concept and this
    # suggestion still has not made one. The suggestion stays out of the ranked queue either way.
    assert payload["integration"]["requirement_actions"] == "connected"


def test_gaps_are_ordered_stably_with_required_before_optional(client):
    account = _account(client)
    program = _program(client, account["id"], "Support Deflection")
    _launch(client, account["id"], program["id"], version=2)
    first = _path(client, account["id"], program["id"])
    second = _path(client, account["id"], program["id"])
    keys = lambda p: [r["requirement_key"]
                      for r in p["work"]["account_essentials"]["requirements"]["requirements"]]
    assert keys(first) == keys(second)
    rows = first["work"]["account_essentials"]["requirements"]["requirements"]
    gap_flags = [r["is_gap"] for r in rows]
    assert gap_flags == sorted(gap_flags, reverse=True), "gaps come before settled requirements"


def test_suppressed_and_waived_requirements_are_not_gaps(client):
    account = _account(client)
    program = _program(client, account["id"], "Support Deflection")
    _launch(client, account["id"], program["id"])
    client.post(f"/api/accounts/{account['id']}/readiness-exceptions", json={
        "requirement_key": "exec_engaged", "kind": "not_applicable", "program_id": program["id"],
        "reason": "Executive tier is out of scope for this pilot."})
    client.post(f"/api/accounts/{account['id']}/readiness-exceptions", json={
        "requirement_key": "value_baseline_locked", "kind": "waiver", "program_id": program["id"],
        "reason": "Baseline deferred to the next measurement window by agreement.",
        "expires_on": utc_day(60)})
    requirements = _path(client, account["id"],
                         program["id"])["work"]["account_essentials"]["requirements"]
    gap_keys = {r["requirement_key"] for r in requirements["gaps"]}
    assert "exec_engaged" not in gap_keys
    assert "value_baseline_locked" not in gap_keys
    # Both are still listed, with the decision attached. Silently dropping them would hide a
    # governed choice behind an empty list.
    all_keys = {r["requirement_key"] for r in requirements["requirements"]}
    assert {"exec_engaged", "value_baseline_locked"} <= all_keys
    assert requirements["counts"]["suppressed"] == 1
    assert requirements["counts"]["waived"] == 1


def test_readiness_coverage_is_reported_apart_from_execution_coverage(client):
    account = _account(client)
    program = _program(client, account["id"], "Support Deflection")
    payload = _path(client, account["id"], program["id"])
    coverage = payload["coverage"]
    assert coverage["status"] in ("complete", "partial", "unavailable")
    # Readiness coverage is its own claim in its own vocabulary, reported beside execution
    # coverage rather than folded into it. Merging them would let a thin evidence base read as a
    # missing work source, or a failing adapter read as thin evidence.
    assert coverage["readiness"]["status"] in ("complete", "partial", "unavailable")
    assert isinstance(coverage["readiness"], dict) and isinstance(coverage["status"], str)
    assert not any(o["source"] == "readiness" for o in coverage["omitted_sources"])


def test_a_failing_plan_layer_cannot_suppress_canonical_work(client, monkeypatch):
    """§13.9. The plan layer is guarded exactly like every other adapter."""
    account = _account(client)
    program = _program(client, account["id"], "Support Deflection")
    r = client.post("/api/tasks", json={"program_id": program["id"],
                                        "description": "Send the kickoff agenda",
                                        "due_date": utc_day(-3)})
    assert r.status_code == 201, r.text

    from app import execution_path
    monkeypatch.setattr(execution_path, "_requirement_rows",
                        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("plan layer down")))
    payload = _path(client, account["id"], program["id"])
    assert payload["work"]["you_own"], "canonical work survives a plan-layer failure"
    assert payload["work"]["account_essentials"]["requirements"] is None
    assert payload["integration"]["plan_instances"] == "not_connected"
    assert any(o["source"] == "plan_instances" for o in payload["coverage"]["omitted_sources"])
    assert payload["coverage"]["status"] == "partial"


# --- schema guards -------------------------------------------------------------------------------

def test_the_plan_layer_stores_no_state_freshness_or_coverage(client):
    """RELATIONSHIP-READINESS-SPEC.md §2 asserted against Slice 3's own tables.

    A plan schedules a requirement; it never states one. The guard is schema introspection rather
    than review, because this is exactly the column somebody adds "just to cache it".
    """
    conn = sqlite3.connect(client.db_path)
    try:
        tables = [r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' "
            "AND (name LIKE 'readiness_plan%' OR name = 'readiness_exceptions')")]
        assert tables, "expected the Slice 3 tables to exist"
        banned = ("state", "met", "freshness", "coverage", "applicability", "score", "weight")
        for table in tables:
            for column in (r[1].lower() for r in conn.execute(f"PRAGMA table_info({table})")):
                assert not any(b == column or column.endswith(f"_{b}") for b in banned), \
                    f"{table}.{column} would let a plan assert a readiness answer"
    finally:
        conn.close()


def test_no_stored_pillar_state_table_exists(client):
    """Still true after Slice 3 (§13.9's last criterion). Six new tables, none of them a cache."""
    conn = sqlite3.connect(client.db_path)
    try:
        for name in [r[0] for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'readiness%'")]:
            columns = {r[1].lower() for r in conn.execute(f"PRAGMA table_info({name})")}
            # A definition row may *configure* an evaluator; no row may *hold* an evaluated answer.
            assert "pillar_state" not in columns
            assert not (columns >= {"pillar_key", "state"}), \
                f"{name} looks like a stored pillar state"
    finally:
        conn.close()


# --- review pass ---------------------------------------------------------------------------------

def test_a_removed_requirement_is_named_in_words_like_every_other_change(client):
    """The removals are the rows that take a recorded tick with them, so they are the last ones
    that should read as an internal key beside four groups that read as sentences."""
    account = _account(client)
    program = _program(client, account["id"], "Support Deflection")
    _launch(client, account["id"], program["id"], version=1)

    diff = client.post(f"/api/accounts/{account['id']}/plan-instances/upgrade-preview", json={
        "playbook_key": "enterprise-launch", "to_version": 2,
        "program_id": program["id"]}).json()
    removed = diff["removals"][0]
    assert removed["requirement_key"] == "budget_authority_evidence"
    assert removed["label"], "a removal carries the definition's own label"
    assert removed["label"] != removed["requirement_key"]
    assert "_" not in removed["label"]
    # Read from the version the plan pinned, not from whatever is current.
    conn = sqlite3.connect(client.db_path)
    try:
        conn.row_factory = sqlite3.Row
        pinned = conn.execute(
            "SELECT requirement_version FROM readiness_plan_instances "
            "WHERE account_id = ? AND requirement_key = ? AND archived = 0",
            (account["id"], "budget_authority_evidence")).fetchone()["requirement_version"]
        expected = conn.execute(
            "SELECT label FROM readiness_requirement_definitions WHERE key = ? AND version = ?",
            ("budget_authority_evidence", pinned)).fetchone()["label"]
    finally:
        conn.close()
    assert removed["label"] == expected


def test_an_orphaned_migrated_instance_is_not_counted_as_an_unmatched_checklist_item(client):
    """`unmatched` is a partition of the checklist items; these are not checklist items.

    Counted together, `unmatched` could exceed `checklist_items` — so "mapped N of M" stopped being
    readable — and the orphan inherited a reason that is untrue of it twice over: it carries no
    template key to match, and it was not left as it is. It is a live instance holding a tick.
    """
    account = _account(client)
    _onboard_pre_merge(client, account["id"])
    item = _checklist_item(client, account["id"], "Baselines captured")
    first = client.post(f"/api/accounts/{account['id']}/checklist-compatibility",
                        json={"dry_run": False}).json()
    assert first["counts"]["orphaned"] == 0
    assert first["orphaned"] == []
    mapped_before = first["counts"]["mapped"]
    assert mapped_before > 0

    # Archive the source item. No route does this — an operator archiving a checklist item after a
    # migration is the situation, and the instance it produced is what survives it.
    conn = sqlite3.connect(client.db_path)
    try:
        conn.execute("UPDATE checklist_items SET archived = 1 WHERE id = ?", (item["id"],))
        conn.commit()
    finally:
        conn.close()

    report = client.post(f"/api/accounts/{account['id']}/checklist-compatibility",
                         json={"dry_run": True}).json()
    assert report["counts"]["orphaned"] == 1
    orphan = report["orphaned"][0]
    assert orphan["checklist_item_id"] == item["id"]
    assert orphan["reason"] == "a migrated instance whose source checklist item is gone"
    # The partition still holds, which is what makes the headline count honest.
    counts = report["counts"]
    assert counts["mapped"] + counts["unmatched"] + counts["ambiguous"] == counts["checklist_items"]
    assert all(u["reason"] == "no exact template_key mapping" for u in report["unmatched"])
    # And the instance itself is still there, tick and all, rather than deleted.
    assert any(r["requirement_key"] == orphan["requirement_key"]
               for r in _plan(client, account["id"])["requirements"])
