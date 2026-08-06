"""Acceptance tests for ACCOUNT-INTAKE-SPEC.md Slice 4 — ("create","milestone") and §17 telemetry.

A milestone is the first proposable target that carries a **date the rest of the app plans
against**. Every other target the extractor drafts is a sentence somebody reads; this one becomes a
row that readiness, the program path, and the shared plan all compute against. That changes what
"almost right" costs, and it is the whole reason this slice is separate from the four before it.

So the tests are grouped by the three ways an almost-right milestone gets made:

  §10  **A date that was guessed.** "Some time in the autumn" is not a date, and neither is
       03/04/2026. Both produce no milestone and a line in the coverage report — never a plausible
       date nobody chose.
  §10  **A program that was inferred.** The program comes from the operator's selector and is never
       read from the text. A drop with none reports the milestone and drafts nothing.
  §10  **A status that was asserted.** `at_risk`, `completed_on`, and `completion_note` are
       judgements about a plan rather than facts in a document. `MilestoneCreate` would drop them
       silently, so the proposal layer refuses them instead — a silently-dropped field is one
       nobody reviews.

Plus the structural claim the slice rests on: the pair travels **normalized**, `mutation_type` stays
NULL, and Slice 4 therefore needs no migration at all.

Everything here is synthetic. No real client names, people, or figures (CLAUDE.md).
"""
import os
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


# --- fixtures --------------------------------------------------------------------------------

def _account(c, name="Harbourline Synthetic"):
    r = c.post("/api/accounts", json={"name": name})
    assert r.status_code == 201, r.text
    return r.json()


def _program(c, account_id, name="Synthetic rollout", phase="launch"):
    r = c.post("/api/programs", json={"account_id": account_id, "name": name, "phase": phase})
    assert r.status_code == 201, r.text
    return r.json()


def _drop(c, account_id, **body):
    r = c.post(f"/api/accounts/{account_id}/intake/drops", json=body)
    assert r.status_code == 201, r.text
    return r.json()


def _rows(c, sql, params=()):
    conn = sqlite3.connect(c.db_path)
    conn.row_factory = sqlite3.Row
    try:
        return [dict(r) for r in conn.execute(sql, params)]
    finally:
        conn.close()


def _proposals(c, run_id):
    return _rows(c, "SELECT * FROM extraction_proposals WHERE run_id=? ORDER BY created_at",
                 (run_id,))


# A milestone the extractor can draft outright, padded to clear the paste floor. Deliberately free
# of commitment and decision cues: those rules are matched first, and a fixture that tripped one
# would be testing the wrong branch.
DATED = (
    "Rollout planning notes for the synthetic programme, written up after the session so the "
    "dates are all in one place and nothing has to be reconstructed from memory later on.\n"
    "The pilot go-live is 1 October 2026.\n"
    "Everything else in this note is background and needs no follow-up from anybody.\n"
)

UNDATED = (
    "Rollout planning notes for the synthetic programme, written up after the session so the "
    "dates are all in one place and nothing has to be reconstructed from memory later on.\n"
    "The pilot go-live is some time in the autumn.\n"
    "Everything else in this note is background and needs no follow-up from anybody.\n"
)


# --- §10 a date that was guessed ---------------------------------------------------------------

def test_a_relative_phrase_is_not_a_date_and_drafts_nothing(client):
    """"Some time in the autumn" is exactly the input a helpful extractor turns into a wrong row."""
    account = _account(client)
    program = _program(client, account["id"])
    drop = _drop(client, account["id"], text=UNDATED, program_id=program["id"])

    kinds = [p["target_type"] for p in _proposals(client, drop["extraction_run_id"] or "")]
    assert "milestone" not in kinds

    # Reported, not silent. An empty coverage report would read as "there was nothing there".
    named = drop["coverage"]["named_not_proposed"]
    assert len(named) == 1
    assert "go-live" in named[0]["what"]
    assert named[0]["why"]                      # the sentence is the server's, and it is present


def test_the_refusal_sentence_is_authored_on_the_server(client):
    """D-153. A view that composes any part of an "I did not do this" statement can soften one."""
    from app import extractor

    account = _account(client)
    program = _program(client, account["id"])
    drop = _drop(client, account["id"], text=UNDATED, program_id=program["id"])
    assert drop["coverage"]["named_not_proposed"][0]["why"] == extractor._NO_DATE


@pytest.mark.parametrize("text,expected", [
    ("Go-live is 2026-10-01.", "2026-10-01"),
    ("Go-live is 1 October 2026.", "2026-10-01"),
    ("Go-live is October 1, 2026.", "2026-10-01"),
    # No slash form is read at all: 03/04/2026 is 3 April to one reader and 4 March to another, and
    # nothing on a milestone records which reading was taken.
    ("Go-live is 03/04/2026.", None),
    ("Go-live is 3/4/26.", None),
    # Two dates in one sentence. Taking the first would be a coin flip presented as a reading.
    ("Go-live is 1 October 2026, moved from 15 November 2026.", None),
    ("Go-live is in the autumn.", None),
    ("Go-live is 2026-13-45.", None),
])
def test_find_date_returns_a_date_only_when_there_is_exactly_one_unambiguous_one(text, expected):
    from app import extractor
    assert extractor.find_date(text) == expected


# --- §10 a program that was inferred -----------------------------------------------------------

def test_a_milestone_with_no_program_is_refused_rather_than_left_homeless(client):
    """The program comes from the operator's selector. A date with no plan to sit on is not a plan."""
    account = _account(client)
    drop = _drop(client, account["id"], text=DATED)          # no program_id

    kinds = [p["target_type"] for p in _proposals(client, drop["extraction_run_id"] or "")]
    assert "milestone" not in kinds

    refused = drop["coverage"]["refused"]
    assert len(refused) == 1
    assert "go-live" in refused[0]["what"]

    # `refused`, not `named_not_proposed`, and the difference is not cosmetic: one is about the
    # document and cannot be fixed, the other is about a choice the operator has not made yet and
    # is fixed by choosing a program.
    assert drop["coverage"]["named_not_proposed"] == []


def test_the_two_omissions_are_told_apart_by_which_one_the_operator_can_fix(client):
    from app import extractor
    account = _account(client)
    drop = _drop(client, account["id"], text=DATED)
    assert drop["coverage"]["refused"][0]["why"] == extractor._NO_PROGRAM
    assert extractor._NO_PROGRAM != extractor._NO_DATE


# --- the normalized pair, and why there is no migration ----------------------------------------

def test_a_drafted_milestone_stores_the_pair_and_leaves_the_legacy_column_null(client):
    """§10's better shape. `create_milestone` has no legacy name, so none is invented for it.

    Migration 0043 made `mutation_type` nullable for exactly this, which is why Slice 4 adds no
    migration of its own: inventing a tenth value would have to pass a CHECK written over nine.
    """
    account = _account(client)
    program = _program(client, account["id"])
    drop = _drop(client, account["id"], text=DATED, program_id=program["id"])

    rows = [p for p in _proposals(client, drop["extraction_run_id"])
            if p["target_type"] == "milestone"]
    assert len(rows) == 1
    assert rows[0]["intent"] == "create"
    assert rows[0]["mutation_type"] is None
    assert rows[0]["proposal_fingerprint"]                    # still fingerprinted, still cited
    assert rows[0]["source_span"]


def test_the_legacy_check_constraint_is_untouched_by_this_slice(client):
    """Nothing widened the nine-value CHECK — the pair went around it instead."""
    sql = _rows(client, "SELECT sql FROM sqlite_master WHERE name='extraction_proposals'")[0]["sql"]
    assert "create_milestone" not in sql
    assert "milestone" not in sql          # `target_type` deliberately has no CHECK at all (RR-2)


def test_the_allowlist_lives_in_python_beside_the_write_path(client):
    from app import proposals
    assert proposals.TARGET_ALLOWLIST["milestone"] == frozenset({"create", "no_change"})
    # `close` is deliberately absent: no document ticks anything off.
    proposals.check_pair("create", "milestone")
    with pytest.raises(proposals.ProposalError):
        proposals.check_pair("close", "milestone")
    assert proposals.legacy_mutation("create", "milestone") is None


# --- §10 a status that was asserted ------------------------------------------------------------

@pytest.mark.parametrize("field", ["at_risk", "completed_on", "completion_note", "completed"])
def test_no_document_may_assert_a_milestones_status(field):
    """These are judgements about a plan, not facts in a document.

    `MilestoneCreate` would drop every one of them silently, and a silently-dropped field is one
    nobody reviews. So they fail the proposal rather than disappearing from it.
    """
    from app import proposals
    with pytest.raises(proposals.ProposalError):
        proposals.check_payload("create", "milestone",
                                {"name": "Pilot go-live", "target_date": "2026-10-01", field: 1})


def test_an_override_cannot_smuggle_a_status_in_at_accept_time(client):
    """§6.8 revalidates the FINAL payload, and an override is exactly how one would arrive."""
    account = _account(client)
    program = _program(client, account["id"])
    drop = _drop(client, account["id"], text=DATED, program_id=program["id"])
    prop = [p for p in _proposals(client, drop["extraction_run_id"])
            if p["target_type"] == "milestone"][0]

    r = client.post(f"/api/extraction/proposals/{prop['id']}/accept",
                    json={"overrides": {"at_risk": True}})
    assert r.status_code == 422
    assert _rows(client, "SELECT id FROM milestones") == []


# --- acceptance writes a real record through the native path ------------------------------------

def test_accepting_a_milestone_creates_the_native_record(client):
    """The native audited write path, not a second one. `execution_ops` already knew this table."""
    account = _account(client)
    program = _program(client, account["id"])
    drop = _drop(client, account["id"], text=DATED, program_id=program["id"])
    prop = [p for p in _proposals(client, drop["extraction_run_id"])
            if p["target_type"] == "milestone"][0]

    r = client.post(f"/api/extraction/proposals/{prop['id']}/accept", json={})
    assert r.status_code == 200, r.text
    assert r.json()["created_type"] == "milestone"

    rows = _rows(client, "SELECT * FROM milestones")
    assert len(rows) == 1
    assert rows[0]["program_id"] == program["id"]
    assert rows[0]["target_date"] == "2026-10-01"
    # Nothing about the record's condition came from the document.
    assert rows[0]["at_risk"] == 0
    assert rows[0]["status"] == "upcoming"

    audits = _rows(client, "SELECT * FROM audit_events WHERE object_type='milestone'")
    assert audits, "a milestone created from a proposal is still a material change"


def test_the_reviewer_may_correct_the_date_before_it_becomes_a_plan(client):
    account = _account(client)
    program = _program(client, account["id"])
    drop = _drop(client, account["id"], text=DATED, program_id=program["id"])
    prop = [p for p in _proposals(client, drop["extraction_run_id"])
            if p["target_type"] == "milestone"][0]

    r = client.post(f"/api/extraction/proposals/{prop['id']}/accept",
                    json={"overrides": {"target_date": "2026-11-15"}})
    assert r.status_code == 200, r.text
    assert _rows(client, "SELECT target_date FROM milestones")[0]["target_date"] == "2026-11-15"


def test_accept_all_applies_a_milestone_with_everything_else_in_its_run(client):
    """§11.4. The batch path dispatches on the same normalized column the single path does."""
    account = _account(client)
    program = _program(client, account["id"])
    drop = _drop(client, account["id"], text=DATED, program_id=program["id"])
    run_id = drop["extraction_run_id"]

    r = client.post(f"/api/extraction/runs/{run_id}/accept-all", json={})
    assert r.status_code == 200, r.text
    assert len(_rows(client, "SELECT id FROM milestones")) == 1
    assert [p["status"] for p in _proposals(client, run_id)
            if p["target_type"] == "milestone"] == ["accepted"]


def test_a_second_drop_of_the_same_milestone_is_offered_as_a_possible_duplicate(client):
    """§6.7. A milestone's duplicate signal is its name within the program — nothing fuzzier."""
    account = _account(client)
    program = _program(client, account["id"])
    first = _drop(client, account["id"], text=DATED, program_id=program["id"])
    prop = [p for p in _proposals(client, first["extraction_run_id"])
            if p["target_type"] == "milestone"][0]
    assert client.post(f"/api/extraction/proposals/{prop['id']}/accept", json={}).status_code == 200

    # Same milestone, different surrounding words, so it is a fresh document rather than a dedupe.
    second = _drop(client, account["id"], program_id=program["id"], text=(
        "Follow-up planning notes recorded a week later, covering the same ground again because "
        "two people asked for the dates in writing rather than in the call recording.\n"
        "The pilot go-live is 1 October 2026.\n"
        "There is nothing else outstanding from this conversation at all.\n"
    ))
    repeat = [p for p in _proposals(client, second["extraction_run_id"])
              if p["target_type"] == "milestone"][0]
    r = client.get(f"/api/extraction/proposals/{repeat['id']}/review")
    assert r.status_code == 200, r.text
    checks = [c["check"] for c in r.json()["match_candidates"]]
    assert "exact_content" in checks


# --- §17 telemetry — the contract amendment -----------------------------------------------------

def test_the_drop_events_are_under_the_same_contract_as_every_other_event():
    """Not a second store. Two contracts about what may leave a record eventually disagree."""
    from app import telemetry
    for name in ("drop_zone_shown", "drop_received", "drop_refused", "drop_drafted",
                 "drop_no_proposals", "drop_receipt_opened"):
        assert name in telemetry.EVENTS


def test_a_drop_event_cannot_carry_a_filename_by_any_route(client):
    """§17 — "a filename is document content by another name"."""
    from app import telemetry
    for key in ("filename", "file_name", "document", "subject", "snippet", "kind_label"):
        with pytest.raises(telemetry.TelemetryRejected):
            telemetry.validate("drop_refused", properties={key: "q3-renewal.eml"})
    # And the one property it does carry cannot hold a sentence — the slug rule is the shape check.
    with pytest.raises(telemetry.TelemetryRejected):
        telemetry.validate("drop_refused", properties={"reason_code": "That file had no readable text."})
    telemetry.validate("drop_refused", properties={"reason_code": "parse_failed"})


def test_the_events_that_report_nothing_carry_nothing(client):
    from app import telemetry
    for name in ("drop_zone_shown", "drop_received", "drop_drafted", "drop_no_proposals",
                 "drop_receipt_opened"):
        telemetry.validate(name, properties={})
        with pytest.raises(telemetry.TelemetryRejected):
            telemetry.validate(name, properties={"reason_code": "drafted"})
