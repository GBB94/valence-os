"""Regressions for the defects the 2026-08-05 adversarial review found (D-147).

Every one of these passed the whole 513-test suite before the fix. That is the point of the file:
each test reproduces the exact lie the code told — an account fact that changed when you picked a
program, a meeting in 2099 asserting a condition is true today, a governance preview that could
only ever report "nothing changes", a cross-account write reached through an override, and an
idempotency check that closed one program's proposal against another program's record.
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


def _account(c, name="Northwind Synthetic"):
    return c.post("/api/accounts", json={"name": name}).json()


def _program(c, account_id, name, phase="programmatic"):
    r = c.post("/api/programs", json={"account_id": account_id, "name": name, "phase": phase})
    assert r.status_code == 201, r.text
    return r.json()


def _person(c, account_id, name, title=None, affiliation="client"):
    r = c.post("/api/persons", json={"name": name, "account_id": account_id,
                                     "affiliation": affiliation, "title": title})
    assert r.status_code == 201, r.text
    return r.json()


def _role(c, program_id, person_id, role):
    r = c.post("/api/stakeholder-roles", json={"program_id": program_id, "person_id": person_id,
                                               "role": role})
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


# --- 1. an account fact does not change when you pick a program --------------------------------

def test_account_scoped_pillar_is_identical_in_every_program_view(client):
    """The account-scoped pillars are one answer per account (§3.1).

    Evaluating them inside the selected program recomputed them from that program's stakeholder
    roles alone, so the budget owner who sits on Program A made the account read `met` beside A and
    `unknown` beside its sibling B. The same account, the same day, two different truths — decided
    by a filter the operator moved.
    """
    account = _account(client)
    prog_a = _program(client, account["id"], "Europe Deployment")
    prog_b = _program(client, account["id"], "Seat Expansion")
    owner = _person(client, account["id"], "Robin Vale", title="Director of Finance")
    _role(client, prog_a["id"], owner["id"], "budget_owner")
    _touch(client, account["id"], [owner["id"]], days_ago=3, program_id=prog_a["id"])

    account_view = _pillar(_readiness(client, account["id"]), "budget_owner")
    in_a = _pillar(_readiness(client, account["id"], prog_a["id"]), "budget_owner")
    in_b = _pillar(_readiness(client, account["id"], prog_b["id"]), "budget_owner")

    assert in_a["scope"] == "account" and in_b["scope"] == "account"
    assert in_a["state"] == in_b["state"] == account_view["state"], (
        "an account-scoped pillar changed state with the program filter: "
        f"account={account_view['state']} A={in_a['state']} B={in_b['state']}"
    )
    assert in_a["components"] == in_b["components"], \
        "the same account-scoped condition produced different components per program"


def test_program_scoped_pillar_still_stays_separate_per_program(client):
    """The fix must not overshoot: a *program* pillar keeps its own evidence (§3.1).

    Inheriting account-wide evidence into program pillars would merge Program A's champion with
    Program B's, manufacturing a `met` that is true of neither.
    """
    account = _account(client)
    prog_a = _program(client, account["id"], "Europe Deployment")
    prog_b = _program(client, account["id"], "Seat Expansion")
    champ = _person(client, account["id"], "Ada Kerr", title="Ops Lead")
    _role(client, prog_a["id"], champ["id"], "champion")
    _touch(client, account["id"], [champ["id"]], days_ago=2, program_id=prog_a["id"])

    in_a = _pillar(_readiness(client, account["id"], prog_a["id"]), "champion_continuity")
    in_b = _pillar(_readiness(client, account["id"], prog_b["id"]), "champion_continuity")
    assert in_a["scope"] == "program"
    assert in_a["components"] != in_b["components"], \
        "program-scoped evidence leaked across sibling programs"


# --- 2. the future is not evidence -------------------------------------------------------------

def test_a_future_dated_interaction_is_not_current_evidence(client):
    """A meeting that has not happened cannot make a condition true today.

    `age <= window_days` accepted a negative age, so a 2099 interaction reported `met · current ·
    assessed through 2099-01-01`. Both guards are asserted: the loader excludes it, and the
    freshness floor rejects a negative age even if a loader ever forgets.
    """
    from app.readiness import _freshness

    account = _account(client)
    program = _program(client, account["id"], "Europe Deployment")
    owner = _person(client, account["id"], "Robin Vale", title="Director of Finance")
    _role(client, program["id"], owner["id"], "budget_owner")
    r = client.post("/api/interactions", json={
        "account_id": account["id"], "program_id": program["id"],
        "occurred_on": "2099-01-01", "type": "meeting", "summary": "Planned working session",
        "participant_ids": [owner["id"]], "meaningful_touch": True,
    })
    assert r.status_code == 201, r.text

    pillar = _pillar(_readiness(client, account["id"]), "budget_owner")
    assert pillar["state"] != "met", "a 2099 meeting satisfied a condition today"
    for component in pillar["components"]:
        assert component["freshness"] != "current" or component["assessed_through"] is None, \
            f"{component['key']} called future evidence current"
        assert (component["assessed_through"] or "") < "2099-01-01", \
            "a future date was reported as the assessed-through date"

    assert _freshness(utc_day(0), "2099-01-01", 30) == "stale"
    assert _freshness(utc_day(0), utc_day(-2), 30) == "current"


def test_future_advocacy_does_not_validate_a_champion(client):
    account = _account(client)
    program = _program(client, account["id"], "Europe Deployment")
    champ = _person(client, account["id"], "Ada Kerr", title="Ops Lead")
    _role(client, program["id"], champ["id"], "champion")
    _touch(client, account["id"], [champ["id"]], days_ago=2, program_id=program["id"])
    r = client.post("/api/advocacy-events", json={
        "person_id": champ["id"], "program_id": program["id"], "kind": "advocacy_without_us",
        "occurred_on": "2099-06-01", "note": "Scheduled internal presentation",
    })
    assert r.status_code == 201, r.text

    pillar = _pillar(_readiness(client, account["id"], program["id"]), "champion_continuity")
    validated = [c for c in pillar["components"] if c["state"] == "met"]
    for component in validated:
        for evidence in component.get("evidence", []):
            assert "2099" not in evidence["label"], \
                "a scheduled advocacy event was used to validate a champion"


# --- 3. the upgrade preview previews ------------------------------------------------------------

def test_upgrade_preview_runs_the_candidate_evaluator(client):
    """§7.4's preview is the governance step for a versioned evaluator.

    It validated that the candidate was allowlisted and then reported the *live* state on both
    sides, so `changed_count` was structurally zero for every upgrade — including one that moved
    every account. Previewing the version already in force is the honest zero, and it must come
    from actually running it.
    """
    account = _account(client)
    program = _program(client, account["id"], "Europe Deployment")
    _person(client, account["id"], "Robin Vale", title="Director of Finance")

    r = client.post("/api/readiness/definition-upgrades/preview",
                    json={"pillar_key": "budget_owner", "evaluator_version": 1})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["applied"] is False, "a preview wrote something"
    assert body["affected_scopes"], "the preview evaluated no scopes at all"
    for transition in body["affected_scopes"]:
        assert transition["from_state"] is not None and transition["to_state"] is not None, \
            "a transition reported no state on one side"
    assert body["changed_count"] == 0, "re-previewing the live version should move nothing"

    r = client.post("/api/readiness/definition-upgrades/preview",
                    json={"pillar_key": "budget_owner", "evaluator_version": 99})
    assert r.status_code == 422, "an unallowlisted candidate must fail closed, not be previewed"
    assert program["id"]


def test_the_preview_override_actually_changes_which_evaluator_runs(client):
    """The zero above only means something if the candidate is genuinely being executed.

    Only v1 of each pillar evaluator is registered today, so no allowlisted candidate can produce a
    different answer through the route yet — a non-zero `changed_count` is unreachable until a v2
    exists, and a route test asserting one would be asserting nothing. The mechanism is therefore
    asserted where it lives: an override to an unregistered version must fail closed into `unknown`
    with a coverage failure. If the override were still being ignored, this pillar would come back
    `met` exactly as the live evaluation does.
    """
    from app import readiness
    from app.db import connect

    account = _account(client)
    program = _program(client, account["id"], "Europe Deployment")
    owner = _person(client, account["id"], "Robin Vale", title="Director of Finance")
    _role(client, program["id"], owner["id"], "budget_owner")
    _touch(client, account["id"], [owner["id"]], days_ago=3, program_id=program["id"])

    live = _pillar(_readiness(client, account["id"]), "budget_owner")
    assert live["state"] != "unknown", "fixture did not produce a state to move away from"

    conn = connect()
    overridden = readiness.evaluate(conn, account["id"],
                                    evaluator_override={"budget_owner": 99})
    moved = _pillar(overridden, "budget_owner")
    assert moved["state"] == "unknown", "the evaluator override was ignored"
    assert "budget_owner" in overridden["coverage"]["failed_evaluators"]
    assert overridden["coverage"]["status"] == "partial"

    after = _pillar(_readiness(client, account["id"]), "budget_owner")
    assert after["state"] == live["state"], "an override leaked into the live evaluation"


# --- 4. an internal owner is selectable ---------------------------------------------------------

def test_the_roster_endpoint_returns_global_valence_people(client):
    """`Create action` needs an internal owner, and internal people are global records.

    The form read people from the account-detail endpoint, which selects `WHERE account_id = ?`.
    Every Valence colleague is seeded with a null `account_id`, so the required internal-owner
    select was always empty and no commitment could be created from a requirement.
    """
    account = _account(client)
    r = client.post("/api/persons", json={"name": "Sam Rivera", "affiliation": "valence",
                                          "account_id": None, "title": "Engagement Manager"})
    assert r.status_code == 201, r.text

    detail = client.get(f"/api/accounts/{account['id']}").json()
    assert not [p for p in detail["people"] if p["affiliation"] == "valence"], \
        "account detail is account-scoped by design; this test documents why it is the wrong source"

    roster = client.get(f"/api/persons?account_id={account['id']}&include_valence=true").json()
    assert [p for p in roster if p["affiliation"] == "valence"], \
        "the roster endpoint the form now uses returned no internal owners"


# --- 5/6/7. proposal scope and concurrency -------------------------------------------------------

def _run_with_proposal(client, account_id, program_id, mutation="create_task",
                       payload=None, span="We will draft the rollout plan."):
    """A run written straight through the repo layer — the mock extractor picks its own shapes."""
    from app.db import connect
    from app.routers.ai import _persist_run

    conn = connect()
    with conn:
        run_id = _persist_run(
            conn, account_id=account_id, program_id=program_id, interaction_id=None,
            model_version="mock-1", prompt_version="p1", extractor_backend="mock",
            source_kind="manual", source_text=span,
            proposals=[{"mutation_type": mutation,
                        "payload": payload or {"description": "Draft the rollout plan"},
                        "source_span": span, "confidence": 0.9}],
        )
    body = client.get(f"/api/extraction/runs/{run_id}").json()
    return run_id, body["proposals"][0]


def test_an_override_cannot_move_a_proposal_to_another_account(client):
    """§6.8. `accept` reads scope back out of the merged payload, so an override writes it.

    A run on account A could name account B's program in `overrides` and the record would land
    there, citing a source that never mentioned it.
    """
    account_a = _account(client, "Northwind Synthetic")
    account_b = _account(client, "Terravance Synthetic")
    _program(client, account_a["id"], "Europe Deployment")
    foreign = _program(client, account_b["id"], "Other Rollout")

    _, prop = _run_with_proposal(client, account_a["id"], None)
    r = client.post(f"/api/extraction/proposals/{prop['id']}/accept",
                    json={"overrides": {"program_id": foreign["id"]}})
    assert r.status_code == 422, f"a cross-account override was accepted: {r.text}"
    assert "different account" in r.text


def test_an_override_cannot_move_a_proposal_to_a_sibling_program(client):
    account = _account(client)
    home = _program(client, account["id"], "Europe Deployment")
    sibling = _program(client, account["id"], "Seat Expansion")

    _, prop = _run_with_proposal(client, account["id"], home["id"])
    r = client.post(f"/api/extraction/proposals/{prop['id']}/accept",
                    json={"overrides": {"program_id": sibling["id"]}})
    assert r.status_code == 422, f"a cross-program override was accepted: {r.text}"


def test_idempotency_does_not_close_one_program_against_anothers_record(client):
    """§6.6 scoped on account alone, and the fingerprint carries no scope.

    The same sentence read under two programs fingerprints alike, so accepting in program B
    returned program A's task and closed B's proposal as `resolved_existing`. No duplicate was
    created — and program B ended up with no record at all.
    """
    account = _account(client)
    prog_a = _program(client, account["id"], "Europe Deployment")
    prog_b = _program(client, account["id"], "Seat Expansion")

    _, first = _run_with_proposal(client, account["id"], prog_a["id"])
    r = client.post(f"/api/extraction/proposals/{first['id']}/accept", json={})
    assert r.status_code == 200, r.text
    created_a = r.json()["created"]["id"]

    _, second = _run_with_proposal(client, account["id"], prog_b["id"])
    r = client.post(f"/api/extraction/proposals/{second['id']}/accept", json={})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body.get("status") != "resolved_existing", \
        "program B's proposal was closed against program A's record"
    assert body["created"]["id"] != created_a
    assert body["created"]["program_id"] == prog_b["id"]


def test_repeat_acceptance_in_the_same_scope_still_returns_the_existing_target(client):
    """The narrowing must not disable the check it narrows."""
    account = _account(client)
    program = _program(client, account["id"], "Europe Deployment")

    _, first = _run_with_proposal(client, account["id"], program["id"])
    r = client.post(f"/api/extraction/proposals/{first['id']}/accept", json={})
    assert r.status_code == 200, r.text
    created = r.json()["created"]["id"]

    _, twin = _run_with_proposal(client, account["id"], program["id"])
    r = client.post(f"/api/extraction/proposals/{twin['id']}/accept", json={})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "resolved_existing", "an identical proposal created a second record"
    assert body["resolved_target_id"] == created


def test_a_placeholder_fill_drafted_before_a_newer_edit_is_stale(client, monkeypatch):
    """§6.7's optimistic concurrency was unreachable in the running app.

    `expected_target_updated_at` was written by no production path and `target_id` was never
    stamped, so `conflict_preview` returned None on every proposal the extractor wrote and the
    only enabled update path — the placeholder fill — patched whatever it found.
    """
    account = _account(client)
    program = _program(client, account["id"], "Europe Deployment")
    r = client.post("/api/placeholders", json={
        "account_id": account["id"], "program_id": program["id"],
        "title": "Finance lead", "expected_role": "budget_owner", "why": "Budget signer unnamed"})
    assert r.status_code == 201, r.text
    placeholder = r.json()

    _, prop = _run_with_proposal(
        client, account["id"], program["id"], mutation="fill_placeholder",
        payload={"name": "Robin Vale", "title": "Director of Finance",
                 "placeholder_person_id": placeholder["id"]},
        span="Robin Vale owns the budget.")
    assert prop["target_id"] == placeholder["id"], "the drafted target was not stamped"
    assert prop["expected_target_updated_at"] == placeholder["updated_at"], \
        "the drafted target's version was not stamped"

    # Somebody else works on the same placeholder after the draft was written. `updated_at` is
    # second-precision, so the competing edit is pinned to a later second rather than raced for
    # one: the defect is that the version was never compared, not that clocks are coarse.
    from app import repo
    later = utc_day(1) + "T09:00:00+00:00"
    monkeypatch.setattr(repo, "now_utc", lambda: later)
    r = client.patch(f"/api/persons/{placeholder['id']}", json={"title": "VP Finance, EMEA"})
    assert r.status_code == 200, r.text
    assert r.json()["updated_at"] == later
    monkeypatch.undo()

    r = client.post(f"/api/extraction/proposals/{prop['id']}/accept", json={})
    assert r.status_code == 409, f"a stale placeholder fill overwrote a newer edit: {r.text}"
    assert "stale_proposal" in r.text

    after = client.get(f"/api/persons/{placeholder['id']}/card").json()
    assert after["title"] == "VP Finance, EMEA", "the newer edit was overwritten"
    assert after["is_placeholder"] is True, "the stale fill was applied anyway"


# --- migration 0044 ------------------------------------------------------------------------------

def test_a_pillar_with_live_requirements_cannot_be_retired(client):
    """0041 guarded one direction only; the illegal pair could still arrive from the other side."""
    import sqlite3
    from app.db import connect

    conn = connect()
    row = conn.execute(
        "SELECT key, version FROM readiness_pillar_definitions "
        "WHERE retired_at IS NULL AND archived = 0 LIMIT 1").fetchone()
    assert row, "no live pillar definition to test against"
    with pytest.raises(sqlite3.IntegrityError) as excinfo:
        with conn:
            conn.execute(
                "UPDATE readiness_pillar_definitions SET retired_at = ? WHERE key = ? AND version = ?",
                (utc_day(0), row["key"], row["version"]))
    assert "live requirement definitions" in str(excinfo.value)
