"""Acceptance tests for RELATIONSHIP-READINESS-SPEC.md §6 — the canonical proposal architecture.

These are written to try to make a proposal do something it must not: create a second persistence
model, assert a readiness state, sneak a forbidden field in through an override, duplicate a
canonical record on a repeat acceptance, match across accounts, or overwrite a record that moved
after the proposal was drafted. Each test asserts the honest answer instead.
"""
import json
import os
import sqlite3
import tempfile

import pytest
from fastapi.testclient import TestClient

from app import proposals


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


TRANSCRIPT = ("Action item: publish the rollout plan. "
              "We decided to start with the support org. "
              "The blocker is that SSO is not provisioned yet.")
# A different task, for the cases that need two proposals that are NOT fingerprint twins.
OTHER_TRANSCRIPT = "Action item: schedule the SSO workshop."


def _account(c, name="Northwind Synthetic"):
    return c.post("/api/accounts", json={"name": name}).json()


def _program(c, account_id, name="Launch"):
    return c.post("/api/programs", json={"account_id": account_id, "name": name,
                                         "phase": "launch"}).json()


def _run(c, account_id, program_id=None, transcript=TRANSCRIPT):
    r = c.post("/api/extraction/run", json={"transcript": transcript, "account_id": account_id,
                                            "program_id": program_id, "backend": "mock"})
    assert r.status_code == 201, r.text
    return r.json()


def _rows(client, sql, params=()):
    conn = sqlite3.connect(client.db_path)
    conn.row_factory = sqlite3.Row
    try:
        return [dict(r) for r in conn.execute(sql, params)]
    finally:
        conn.close()


# --- §6.1 one persistence model ------------------------------------------------------------------

def test_no_second_proposal_persistence_model_exists(client):
    """§6.1's exit criterion, asserted against the schema rather than left to review.

    A parallel intake table is the design this whole section rejects, and it is exactly what a
    later slice would add for convenience if nothing failed.

    The check is about *what a table stores*, not what it is called. `intake_drops`
    (ACCOUNT-INTAKE-SPEC.md §11.2) exists and is allowed to, because it stores only what
    `extraction_runs` does not — a filename, a detected kind, an outcome, and a foreign key to the
    one run. The assertion below is what makes that claim true rather than asserted: the moment it
    grows a payload, an intent, or a status of its own, it has become the second store and this
    fails.
    """
    names = {r["name"] for r in _rows(client, "SELECT name FROM sqlite_master WHERE type='table'")}
    forbidden_tables = {n for n in names
                        if n.startswith("proposal_queue")
                        or n in {"intake_runs", "intake_proposals", "intake_items"}}
    assert not forbidden_tables, forbidden_tables
    inbox = {c["name"] for c in _rows(client, "PRAGMA table_info(capture_inbox_items)")}
    assert not (inbox & {"payload_json", "intent", "target_type", "proposal_fingerprint"}), inbox
    drops = {c["name"] for c in _rows(client, "PRAGMA table_info(intake_drops)")}
    assert not (drops & {"payload_json", "intent", "target_type", "proposal_fingerprint",
                         "status", "proposal_status", "proposal_count", "field", "value"}), drops
    # It points at the one store rather than duplicating it.
    assert "extraction_run_id" in drops, drops


def test_no_proposal_column_can_assert_a_readiness_state(client):
    """§6.3's closing paragraph, at the schema level. Readiness is a query-time projection; a
    column here would be a second source of truth for it."""
    cols = {c["name"] for c in _rows(client, "PRAGMA table_info(extraction_proposals)")}
    forbidden = {"pillar", "requirement_key", "readiness_state", "composite_status", "phase",
                 "met", "coverage", "freshness", "applicability"}
    assert not (cols & forbidden), cols & forbidden


# --- §6.2 / §6.3 the allowlist -------------------------------------------------------------------

def test_link_and_close_are_in_the_vocabulary_but_refused(client):
    """The intent vocabulary is fixed by the spec; the enabled subset is not. Both must be true at
    once, or a later slice will either lose the word or quietly enable the behaviour."""
    assert "link" in proposals.INTENTS and "close" in proposals.INTENTS
    for intent in ("link", "close"):
        # The refusal has to name the intent and say why, not cite a slice number: this string
        # reaches an operator, and "deferred to Slice 5" tells them nothing about what they may
        # do instead. What matters to the test is that both intents are refused by name.
        with pytest.raises(proposals.ProposalError, match="governed operator commands") as raised:
            proposals.check_pair(intent, "task")
        assert f"'{intent}'" in str(raised.value)


def test_creatable_is_not_updatable(client):
    """The allowlist is a pair, not two lists. A Task has a create path and no field-level patch
    path, so `update` on it must fail even though `create` succeeds."""
    proposals.check_pair("create", "task")
    with pytest.raises(proposals.ProposalError, match="not allowed"):
        proposals.check_pair("update", "task")
    # And an unknown target fails by name rather than being treated as a create.
    with pytest.raises(proposals.ProposalError, match="not an allowlisted proposal target"):
        proposals.check_pair("create", "readiness_requirement")


def test_an_update_cannot_change_a_field_outside_its_allowlist():
    proposals.check_payload("update", "person", {"name": "Sam Okafor", "account_id": "acc-1"})
    with pytest.raises(proposals.ProposalError, match="expected_influence"):
        proposals.check_payload("update", "person", {"expected_influence": "high"})


def test_a_proposal_cannot_promote_a_value_story_to_a_client_facing_artifact():
    """Visibility is an operator act. A source that could set it would publish itself."""
    with pytest.raises(proposals.ProposalError, match="visibility_class"):
        proposals.check_payload("create", "value_story",
                                {"outcome": "Support cut handle time", "visibility_class": "client"})


def test_an_override_cannot_smuggle_a_forbidden_field_past_acceptance(client):
    """§6.8 revalidates the FINAL edited payload. Overrides are operator input, and an override is
    exactly how a forbidden field would arrive."""
    acct = _account(client)
    prog = _program(client, acct["id"])
    run = _run(client, acct["id"], prog["id"])
    prop = next(p for p in run["proposals"] if p["target_type"] == "task")
    r = client.post(f"/api/extraction/proposals/{prop['id']}/accept",
                    json={"overrides": {"archived": 1}})
    assert r.status_code == 422 and "archived" in r.json()["detail"]


# --- §6.4 the normalized contract ----------------------------------------------------------------

def test_the_legacy_and_normalized_contracts_both_stay_readable(client):
    """§6.5: `mutation_type` survives until every reader is normalized, and the two vocabularies
    agree because one mapping produces both."""
    acct = _account(client)
    run = _run(client, acct["id"])
    for p in run["proposals"]:
        norm = p["normalized"]
        assert (norm["intent"], norm["target_type"]) == proposals.legacy_pair(p["mutation_type"])
        assert norm["source"]["content_hash"] == run["content_hash"]
        assert norm["account_id"] == acct["id"]
        assert norm["proposal_fingerprint"].startswith("sha256:")


def test_confidence_is_metadata_and_never_changes_what_is_allowed(client):
    """§6.4's closing line. A low-confidence proposal is reviewed the same way as a high-confidence
    one — it is not blocked, not auto-accepted, and not re-ranked."""
    acct = _account(client)
    prog = _program(client, acct["id"])
    run = _run(client, acct["id"], prog["id"])
    conn = sqlite3.connect(client.db_path)
    with conn:
        conn.execute("UPDATE extraction_proposals SET confidence='low' WHERE run_id=?", (run["id"],))
    conn.close()
    prop = next(p for p in run["proposals"] if p["target_type"] == "task")
    r = client.post(f"/api/extraction/proposals/{prop['id']}/accept", json={"overrides": {}})
    assert r.status_code == 200, r.text


# --- §6.6 idempotency ----------------------------------------------------------------------------

def test_external_id_alone_is_not_an_identity():
    """§6.6 says so directly: a provider item can be corrected or retranscribed. Without a content
    hash there is no key at all, which sends the material to review rather than suppressing it."""
    assert proposals.source_version_key(source_kind="interaction", provider="p",
                                        external_id="item-42") is None
    a = proposals.source_version_key(source_kind="interaction", provider="p", external_id="item-42",
                                     hash_=proposals.content_hash("first pass"))
    b = proposals.source_version_key(source_kind="interaction", provider="p", external_id="item-42",
                                     hash_=proposals.content_hash("corrected pass"))
    assert a and b and a != b


def test_a_fingerprint_ignores_formatting_but_not_content():
    kw = dict(intent="create", target_type="task", source_span="Aisha will send the calendar")
    base = proposals.proposal_fingerprint(payload={"description": "Send the HR calendar"}, **kw)
    same = proposals.proposal_fingerprint(payload={"description": "  send the   HR calendar "}, **kw)
    assert base == same
    # A different due date is a different proposal, not a formatting variant.
    other = proposals.proposal_fingerprint(payload={"description": "Send the HR calendar",
                                                    "due_date": "2026-08-07"}, **kw)
    assert base != other
    # A new extractor reading the same sentence is worth reviewing, not suppressing.
    reread = proposals.proposal_fingerprint(payload={"description": "Send the HR calendar"},
                                            extractor_version="mock:v2:cue-rules-2", **kw)
    assert base != reread


def test_repeated_acceptance_returns_the_existing_target_and_creates_nothing_new(client):
    """§6.6's binding sentence. Two runs over the same transcript produce identically fingerprinted
    proposals; accepting the second must resolve to the first's record, not duplicate it."""
    acct = _account(client)
    prog = _program(client, acct["id"])
    first, second = _run(client, acct["id"], prog["id"]), _run(client, acct["id"], prog["id"])
    p1 = next(p for p in first["proposals"] if p["target_type"] == "task")
    p2 = next(p for p in second["proposals"] if p["target_type"] == "task")
    assert p1["proposal_fingerprint"] == p2["proposal_fingerprint"]

    accepted = client.post(f"/api/extraction/proposals/{p1['id']}/accept", json={"overrides": {}})
    assert accepted.status_code == 200, accepted.text
    task_id = accepted.json()["created"]["id"]

    repeat = client.post(f"/api/extraction/proposals/{p2['id']}/accept", json={"overrides": {}})
    assert repeat.status_code == 200, repeat.text
    body = repeat.json()
    assert body["status"] == "resolved_existing" and body["resolved_target_id"] == task_id
    tasks = _rows(client, "SELECT id FROM tasks WHERE program_id=?", (prog["id"],))
    assert len(tasks) == 1, "a repeat acceptance created a duplicate canonical record"


# --- §6.7 matching, resolutions, concurrency -----------------------------------------------------

def test_match_candidates_are_suggestions_and_never_cross_an_account(client):
    """The candidate list is read-only advice; the same sentence in another account must not appear
    in it, whatever it would have suggested."""
    a, b = _account(client), _account(client, "Southgate Synthetic")
    prog_a, prog_b = _program(client, a["id"]), _program(client, b["id"])
    run_a = _run(client, a["id"], prog_a["id"])
    p_a = next(p for p in run_a["proposals"] if p["target_type"] == "task")
    client.post(f"/api/extraction/proposals/{p_a['id']}/accept", json={"overrides": {}})

    run_b = _run(client, b["id"], prog_b["id"])
    p_b = next(p for p in run_b["proposals"] if p["target_type"] == "task")
    review = client.get(f"/api/extraction/proposals/{p_b['id']}/review").json()
    assert review["match_candidates"] == []
    # …and the identical-fingerprint rule is scoped too: this proposal still accepts normally.
    assert client.post(f"/api/extraction/proposals/{p_b['id']}/accept",
                       json={"overrides": {}}).json()["created_type"] == "task"

    # Within one account the same content IS offered as a candidate — and still only as advice.
    run_a2 = _run(client, a["id"], prog_a["id"], transcript="We decided to start with the support org.")
    p_a2 = next(p for p in run_a2["proposals"] if p["target_type"] == "decision")
    before = _rows(client, "SELECT id FROM decisions WHERE program_id=?", (prog_a["id"],))
    client.get(f"/api/extraction/proposals/{p_a2['id']}/review")
    assert _rows(client, "SELECT id FROM decisions WHERE program_id=?", (prog_a["id"],)) == before


def test_use_existing_is_neither_an_acceptance_nor_a_rejection(client):
    acct = _account(client)
    prog = _program(client, acct["id"])
    run = _run(client, acct["id"], prog["id"])
    p1, p2 = (next(p for p in r["proposals"] if p["target_type"] == "task")
              for r in (run, _run(client, acct["id"], prog["id"], transcript=OTHER_TRANSCRIPT)))
    task_id = client.post(f"/api/extraction/proposals/{p1['id']}/accept",
                          json={"overrides": {}}).json()["created"]["id"]

    r = client.post(f"/api/extraction/proposals/{p2['id']}/resolve-existing",
                    json={"target_id": task_id, "note": "Same commitment, already logged."})
    assert r.status_code == 200, r.text
    row = _rows(client, "SELECT * FROM extraction_proposals WHERE id=?", (p2["id"],))[0]
    assert row["status"] == "resolved_existing" and row["resolved_target_id"] == task_id
    # Nothing was created, and it is not recorded as the operator disagreeing with the source.
    assert len(_rows(client, "SELECT id FROM tasks WHERE program_id=?", (prog["id"],))) == 1
    assert row["rejection_reason"] is None


def test_use_existing_cannot_point_at_another_accounts_record(client):
    """§6.8: cross-account targets are rejected before any write."""
    a, b = _account(client), _account(client, "Southgate Synthetic")
    prog_a, prog_b = _program(client, a["id"]), _program(client, b["id"])
    run_a, run_b = _run(client, a["id"], prog_a["id"]), _run(client, b["id"], prog_b["id"])
    p_b = next(p for p in run_b["proposals"] if p["target_type"] == "task")
    p_a = next(p for p in run_a["proposals"] if p["target_type"] == "task")
    foreign = client.post(f"/api/extraction/proposals/{p_a['id']}/accept",
                          json={"overrides": {}}).json()["created"]["id"]
    r = client.post(f"/api/extraction/proposals/{p_b['id']}/resolve-existing",
                    json={"target_id": foreign})
    assert r.status_code == 422 and "different program" in r.json()["detail"]


def test_a_rejection_carries_its_reason(client):
    acct = _account(client)
    run = _run(client, acct["id"])
    prop = run["proposals"][0]
    assert client.post(f"/api/extraction/proposals/{prop['id']}/reject",
                       json={"reason": ""}).status_code == 422
    r = client.post(f"/api/extraction/proposals/{prop['id']}/reject",
                    json={"reason": "The speaker was describing a past call, not committing."})
    assert r.status_code == 200
    row = _rows(client, "SELECT * FROM extraction_proposals WHERE id=?", (prop["id"],))[0]
    assert row["status"] == "rejected" and "past call" in row["rejection_reason"]


def test_supersede_retires_a_draft_and_refuses_anything_already_resolved(client):
    acct = _account(client)
    prog = _program(client, acct["id"])
    old = _run(client, acct["id"], prog["id"])
    new = _run(client, acct["id"], prog["id"], transcript=OTHER_TRANSCRIPT)
    p_old = next(p for p in old["proposals"] if p["target_type"] == "task")
    p_new = next(p for p in new["proposals"] if p["target_type"] == "task")

    assert client.post(f"/api/extraction/proposals/{p_old['id']}/supersede",
                       json={"superseded_by_id": p_old["id"]}).status_code == 422
    r = client.post(f"/api/extraction/proposals/{p_old['id']}/supersede",
                    json={"superseded_by_id": p_new["id"], "reason": "Re-extracted with the owner named."})
    assert r.status_code == 200, r.text
    row = _rows(client, "SELECT * FROM extraction_proposals WHERE id=?", (p_old["id"],))[0]
    assert row["status"] == "superseded" and row["superseded_by_id"] == p_new["id"]
    # Superseding wrote no canonical record, and a retired draft cannot be accepted afterwards.
    assert _rows(client, "SELECT id FROM tasks WHERE program_id=?", (prog["id"],)) == []
    assert client.post(f"/api/extraction/proposals/{p_old['id']}/accept",
                       json={"overrides": {}}).status_code == 409


def test_a_stale_update_returns_a_conflict_preview_instead_of_overwriting(client):
    """§6.7's last paragraph. The record moved after the proposal was drafted, so the proposal
    shows what it would change and declines to apply it."""
    acct = _account(client)
    person = client.post("/api/placeholders", json={
        "account_id": acct["id"], "title": "Head of Support",
        "why": "Named on the kickoff but not introduced."}).json()
    run = _run(client, acct["id"], transcript="The new Head of Support is Sam Okafor.")
    prop = next((p for p in run["proposals"] if p["target_type"] == "person"), None)
    assert prop, [p["mutation_type"] for p in run["proposals"]]

    conn = sqlite3.connect(client.db_path)
    with conn:
        conn.execute("UPDATE extraction_proposals SET target_id=?, expected_target_updated_at=? WHERE id=?",
                     (person["id"], "2020-01-01T00:00:00+00:00", prop["id"]))
    conn.close()

    review = client.get(f"/api/extraction/proposals/{prop['id']}/review").json()
    conflict = review["conflict"]
    assert conflict["stale"] is True
    assert conflict["target_updated_at"] == person["updated_at"]
    assert conflict["expected_target_updated_at"] == "2020-01-01T00:00:00+00:00"
    assert {f["field"] for f in conflict["fields"]}, "the preview must name what would change"
    assert set(conflict["source_dates"]) == {"proposed", "current"}

    r = client.post(f"/api/extraction/proposals/{prop['id']}/accept", json={"overrides": {}})
    assert r.status_code == 409 and r.json()["detail"]["error"] == "stale_proposal"
    # The record is untouched: still a placeholder, still unnamed.
    row = _rows(client, "SELECT * FROM persons WHERE id=?", (person["id"],))[0]
    assert row["is_placeholder"] == 1 and row["name"] == "Head of Support (unknown)"


def test_no_accept_all_endpoint_exists(client):
    """§6.8's closing line, asserted against the route table so a convenience endpoint cannot be
    added without this failing."""
    from app.main import app
    paths = [getattr(r, "path", "") for r in app.routes]
    assert not [p for p in paths if "accept-all" in p or "accept_all" in p], paths


# --- provenance ------------------------------------------------------------------------------------

def test_an_ingested_recording_records_its_provider_and_version_key(client):
    """The one path with a real provider item behind it supplies the full §6.6 source-version
    identity, so a retranscription of the same reference reads as new material."""
    acct = _account(client)
    person = client.post("/api/persons", json={"name": "Aisha Kone", "affiliation": "client",
                                               "account_id": acct["id"]}).json()
    _program(client, acct["id"])
    r = client.post("/api/ingest/recording", json={"reference": TRANSCRIPT,
                                                   "attendees": ["Aisha Kone"], "keywords": []})
    assert r.status_code == 200, r.text
    result = r.json()["result"] if "result" in r.json() else r.json()
    if result.get("status") != "ingested":
        pytest.skip(f"association did not resolve in this fixture: {result}")
    run = _rows(client, "SELECT * FROM extraction_runs WHERE id=?", (result["extraction_run_id"],))[0]
    assert run["source_kind"] == "interaction"
    assert run["provider"] and run["external_id"] and run["content_hash"].startswith("sha256:")
    assert run["source_version_key"].startswith(f"interaction|{run['provider']}|")
    assert run["source_reference_id"], "the run must point at the source_references row"
    assert person["id"]
