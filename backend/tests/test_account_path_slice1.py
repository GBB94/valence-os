"""Acceptance tests for ACCOUNT-PATH-SPEC.md Slice 1 — the Execution Path read model.

These are written to try to make the projection lie: to let a suggestion outrank an overdue Task,
to invent a completed phase from a missing gate, to claim caught-up while a source failed, to
carry another program's work into a selected scope, to mint a snooze key that would 422 on click,
and to call a checklist section a lifecycle phase. Each test asserts the honest answer.
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


def _audit_count(c):
    """Counted straight from the table: there is no HTTP endpoint that lists audit events."""
    conn = sqlite3.connect(c.db_path)
    try:
        return conn.execute("SELECT COUNT(*) FROM audit_events").fetchone()[0]
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
    # A `client` commitment needs a program or a review to hang from (schema CHECK); an
    # account-wide one is expressed with a non-client class.
    r = c.post("/api/commitments", json={
        "account_id": account_id, "description": description,
        "responsible_party_id": responsible_id, "internal_owner_id": owner_id,
        "due_date": due_date, **kw,
    })
    assert r.status_code == 201, r.text
    return r.json()


def _risk(c, program_id, description, **kw):
    r = c.post("/api/risks", json={"program_id": program_id, "description": description, **kw})
    assert r.status_code == 201, r.text
    return r.json()


def _milestone(c, program_id, name, **kw):
    r = c.post("/api/milestones", json={"program_id": program_id, "name": name, **kw})
    assert r.status_code == 201, r.text
    return r.json()


def _gate(c, program_id, name, gates_phase, items):
    r = c.post("/api/phase-gates", json={
        "program_id": program_id, "name": name, "gates_phase": gates_phase, "items": items,
    })
    assert r.status_code == 201, r.text
    return r.json()


def _checklist(c, account_id, section, label, **kw):
    r = c.post("/api/checklist-items", json={
        "account_id": account_id, "section": section, "label": label, **kw,
    })
    assert r.status_code == 201, r.text
    return r.json()


def _interaction(c, account_id, summary, days_ago=1, **kw):
    r = c.post("/api/interactions", json={
        "account_id": account_id, "occurred_on": utc_day(-days_ago), "type": "meeting",
        "summary": summary, "meaningful_touch": True, **kw,
    })
    assert r.status_code == 201, r.text
    return r.json()


def _path(c, account_id, program_id=None, expect=200):
    url = f"/api/accounts/{account_id}/execution-path"
    if program_id:
        url += f"?program_id={program_id}"
    r = c.get(url)
    assert r.status_code == expect, r.text
    return r.json()


def _codes(payload, group="you_own"):
    return [row["reason_code"] for row in payload["work"][group]]


def _ids(payload, group="you_own"):
    return [row["id"] for row in payload["work"][group]]


# --- priority and determinism ----------------------------------------------------------------

def test_blocker_outranks_an_overdue_task_and_bands_are_stable(client):
    """§10.10: a blocker that gates the current phase wins over a merely overdue task."""
    account = _account(client)
    program = _program(client, account["id"], "Launch program")
    operator = _person(client, account["id"], "Sam Rivera", affiliation="valence")

    _task(client, program["id"], "Chase the overdue integration note",
          due_date=utc_day(-9), internal_owner_id=operator["id"])
    _risk(client, program["id"], "Security review has not started", is_blocker=True,
          internal_owner_id=operator["id"])
    _milestone(client, program["id"], "Go-live", target_date=utc_day(5))

    payload = _path(client, account["id"])
    assert payload["next_move"]["reason_code"] == "operator_blocker"
    assert payload["next_move"]["band"] == 1
    # Bands are monotonic down the list, which is what makes the order explainable.
    bands = [row["band"] for row in payload["work"]["you_own"]]
    assert bands == sorted(bands)
    assert _codes(payload) == [
        "operator_blocker", "overdue_operator_task", "milestone_preparation",
    ]


def test_overdue_operator_action_outranks_a_readiness_suggestion(client):
    """§10.5: readiness gaps are not a band. A suggestion may never outrank real work."""
    account = _account(client)
    program = _program(client, account["id"], "Launch program")
    _task(client, program["id"], "Send the revised rollout plan", due_date=utc_day(-2))

    payload = _path(client, account["id"])
    assert payload["next_move"]["source_type"] == "task"
    # Readiness is present and reports gaps, but none of them is a candidate for the next move.
    readiness = payload["work"]["account_essentials"]["readiness"]
    assert readiness is not None
    assert all(row["source_type"] != "readiness_requirement"
               for row in payload["work"]["you_own"])
    assert payload["empty_state"] is None


def test_ties_break_by_due_date_then_recorded_time_then_identity(client):
    """§10.5: undated work sorts after dated work inside the same band, never before it."""
    account = _account(client)
    program = _program(client, account["id"], "Launch program")
    dated = _task(client, program["id"], "Dated residual work", due_date=utc_day(45))
    undated = _task(client, program["id"], "Undated residual work")

    payload = _path(client, account["id"])
    order = _ids(payload)
    assert order.index(f"task:{dated['id']}") < order.index(f"task:{undated['id']}")


def test_gate_items_rank_in_band_two_by_stable_identity(client):
    """§10.5: gate items carry no owner and no date, so band 2 order is decided by identity."""
    account = _account(client)
    program = _program(client, account["id"], "Launch program", phase="launch")
    gate = _gate(client, program["id"], "Launch readiness", "launch",
                 ["Security review complete", "Data agreement signed", "Comms plan approved"])

    payload = _path(client, account["id"])
    rows = [r for r in payload["work"]["you_own"] if r["reason_code"] == "current_gate_item"]
    assert len(rows) == 3
    assert all(r["band"] == 2 for r in rows)
    assert all(r["owner"] is None and r["due_date"] is None for r in rows)
    assert [r["id"] for r in rows] == sorted(r["id"] for r in rows)
    assert gate["id"]


def test_a_gate_on_a_future_phase_is_not_current_work(client):
    """§10.5 band 2 is the *current* phase gate. A future gate is not urgent by existing."""
    account = _account(client)
    program = _program(client, account["id"], "Launch program", phase="foundation")
    _gate(client, program["id"], "Renewal readiness", "renewal", ["Renewal case drafted"])

    payload = _path(client, account["id"])
    assert "current_gate_item" not in _codes(payload)
    upcoming = payload["work"]["upcoming_gates"]
    assert [g["is_current_phase"] for g in upcoming] == [False]


# --- ownership split -------------------------------------------------------------------------

def test_customer_responsibility_keeps_its_internal_follow_up_owner(client):
    """§10.10: customer work appears under Waiting on customer and is never the operator's move."""
    account = _account(client)
    program = _program(client, account["id"], "Launch program")
    champion = _person(client, account["id"], "Devi Raman")
    operator = _person(client, account["id"], "Sam Rivera", affiliation="valence")
    _commitment(client, account["id"], champion["id"], operator["id"],
                "Customer to nominate the pilot cohort", utc_day(-3),
                program_id=program["id"])

    payload = _path(client, account["id"])
    assert _ids(payload, "you_own") == []
    waiting = payload["work"]["waiting_on_customer"]
    assert len(waiting) == 1
    assert waiting[0]["responsible_party"]["party"] == "customer"
    assert waiting[0]["owner"]["party"] == "valence"
    assert payload["next_move"] is None
    assert payload["empty_state"]["variant"] == "waiting_on_customer"


def test_an_unowned_task_still_ranks_and_still_renders(client):
    """§6.1/§10.4: an empty owner is a data-entry gap, not a reason to hide real work."""
    account = _account(client)
    program = _program(client, account["id"], "Launch program")
    _task(client, program["id"], "Unassigned overdue follow-up", due_date=utc_day(-4))

    payload = _path(client, account["id"])
    move = payload["next_move"]
    assert move is not None
    assert move["owner"] is None
    assert move["reason_code"] == "overdue_operator_task"


def test_an_unowned_undated_candidate_still_ranks(client):
    """§10.10: no owner and no due date must not suppress an otherwise eligible item."""
    account = _account(client)
    program = _program(client, account["id"], "Launch program")
    _task(client, program["id"], "Undated unassigned work")

    payload = _path(client, account["id"])
    assert payload["next_move"]["owner"] is None
    assert payload["next_move"]["due_date"] is None
    assert payload["next_move"]["urgency"] == "later"


# --- scope -----------------------------------------------------------------------------------

def test_all_program_scope_keeps_paths_separate_and_invents_no_aggregate_phase(client):
    """§6.3/§10.10: one lane per program; there is no account-level `current_phase`."""
    account = _account(client)
    _program(client, account["id"], "Europe rollout", phase="launch")
    _program(client, account["id"], "Global rollout", phase="programmatic")

    payload = _path(client, account["id"])
    assert payload["scope"]["mode"] == "all_programs"
    assert len(payload["program_paths"]) == 2
    assert {p["current_phase"] for p in payload["program_paths"]} == {"launch", "programmatic"}
    assert "current_phase" not in payload["scope"]


def test_selected_scope_excludes_other_programs_but_keeps_account_wide_facts(client):
    """§7.4: another program's work stays out; an account-wide commitment stays in."""
    account = _account(client)
    selected = _program(client, account["id"], "Europe rollout")
    other = _program(client, account["id"], "Global rollout")
    champion = _person(client, account["id"], "Devi Raman")
    operator = _person(client, account["id"], "Sam Rivera", affiliation="valence")
    _task(client, selected["id"], "In-scope task", due_date=utc_day(-1))
    _task(client, other["id"], "Out-of-scope task", due_date=utc_day(-8))
    _commitment(client, account["id"], operator["id"], operator["id"],
                "Account-wide security questionnaire", utc_day(-2),
                commitment_class="operator_to_internal")

    payload = _path(client, selected["id"] and account["id"], program_id=selected["id"])
    titles = [row["title"] for row in payload["work"]["you_own"]]
    assert "In-scope task" in titles
    assert "Out-of-scope task" not in titles
    assert "Account-wide security questionnaire" in titles
    assert len(payload["program_paths"]) == 1
    assert other["id"] not in [p["program_id"] for p in payload["program_paths"]]


def test_a_foreign_or_unknown_program_is_a_404_not_a_silent_fallback(client):
    """§10.1: falling back to all programs would answer a different question than the one asked."""
    account = _account(client)
    other_account = _account(client, "Harborline Synthetic")
    foreign = _program(client, other_account["id"], "Someone else's program")
    _program(client, account["id"], "Launch program")

    _path(client, account["id"], program_id=foreign["id"], expect=404)
    _path(client, account["id"], program_id="prog-does-not-exist", expect=404)


# --- program path derivation ------------------------------------------------------------------

def test_a_missing_gate_produces_unknown_not_complete(client):
    """§10.8: honest `unknown` beats reconstructed history. Absence is not evidence of passing."""
    account = _account(client)
    _program(client, account["id"], "Launch program", phase="programmatic")

    payload = _path(client, account["id"])
    steps = {s["key"]: s["state"] for s in payload["program_paths"][0]["steps"]}
    assert steps["foundation"] == "unknown"
    assert steps["launch"] == "unknown"
    assert steps["programmatic"] == "current"
    assert steps["expansion"] == "future"
    assert steps["closed"] == "not_applicable"


def test_a_passed_gate_completes_its_phase_and_a_waived_gate_says_waived(client):
    account = _account(client)
    program = _program(client, account["id"], "Launch program", phase="programmatic")
    foundation = _gate(client, program["id"], "Foundation gate", "foundation", ["Scope agreed"])
    launch = _gate(client, program["id"], "Launch gate", "launch", ["Cohort confirmed"])
    # Completing every item auto-passes the gate through its own governed flow.
    item = foundation["items"][0]
    assert client.post(f"/api/gate-items/{item['id']}/toggle",
                       json={"complete": True}).status_code == 200
    assert client.post(f"/api/phase-gates/{launch['id']}/waive",
                       json={"waiver_reason": "Cohort confirmed in the steering forum"}
                       ).status_code == 200

    payload = _path(client, account["id"])
    steps = {s["key"]: s for s in payload["program_paths"][0]["steps"]}
    assert steps["foundation"]["state"] == "complete"
    assert steps["launch"]["state"] == "waived"
    assert steps["launch"]["blocking_reason"] == "Cohort confirmed in the steering forum"


def test_an_open_gate_makes_the_phase_current_not_blocked(client):
    """§10.8: a merely open gate or incomplete item is ordinary current work."""
    account = _account(client)
    program = _program(client, account["id"], "Launch program", phase="launch")
    _gate(client, program["id"], "Launch gate", "launch", ["Comms plan approved"])

    payload = _path(client, account["id"])
    steps = {s["key"]: s for s in payload["program_paths"][0]["steps"]}
    assert steps["launch"]["state"] == "current"
    assert steps["launch"]["missing_count"] == 1


def test_an_open_blocker_marks_the_current_phase_blocked_with_a_named_reason(client):
    account = _account(client)
    program = _program(client, account["id"], "Launch program", phase="launch")
    _risk(client, program["id"], "Data-processing terms unresolved", is_blocker=True)

    payload = _path(client, account["id"])
    step = {s["key"]: s for s in payload["program_paths"][0]["steps"]}["launch"]
    assert step["state"] == "blocked"
    assert step["blocking_reason"] == "Data-processing terms unresolved"


def test_one_program_blocker_does_not_block_a_sibling_program(client):
    """§7.4: program records stay program-scoped, including the reason a phase is blocked."""
    account = _account(client)
    blocked = _program(client, account["id"], "Europe rollout", phase="launch")
    clean = _program(client, account["id"], "Global rollout", phase="launch")
    _risk(client, blocked["id"], "Works-council consultation open", is_blocker=True)

    payload = _path(client, account["id"])
    states = {p["program_id"]: {s["key"]: s["state"] for s in p["steps"]}
              for p in payload["program_paths"]}
    assert states[blocked["id"]]["launch"] == "blocked"
    assert states[clean["id"]]["launch"] == "current"


# --- latest interaction ------------------------------------------------------------------------

def test_latest_interaction_lists_only_records_linked_to_it(client):
    """§10.6: accepted actions are matched by link, never inferred from note text."""
    account = _account(client)
    program = _program(client, account["id"], "Launch program")
    older = _interaction(client, account["id"], "Earlier scoping call", days_ago=20)
    latest = _interaction(client, account["id"], "Onboarding call", days_ago=1)
    linked = _task(client, program["id"], "Confirm the metric of record",
                   source_interaction_id=latest["id"])
    _task(client, program["id"], "Unrelated backlog item")
    _task(client, program["id"], "From the older call", source_interaction_id=older["id"])

    payload = _path(client, account["id"])
    block = payload["latest_interaction"]
    assert block["interaction_id"] == latest["id"]
    assert block["summary"] == "Onboarding call"
    assert [a["id"] for a in block["accepted_actions"]] == [f"task:{linked['id']}"]


def test_an_interaction_with_no_accepted_action_returns_an_empty_list(client):
    """§10.6: absence of a record is not proof that no action was agreed."""
    account = _account(client)
    _program(client, account["id"], "Launch program")
    _interaction(client, account["id"], "Onboarding call", days_ago=1)

    payload = _path(client, account["id"])
    assert payload["latest_interaction"]["accepted_actions"] == []


def test_latest_interaction_work_is_promoted_above_the_residual_pile(client):
    """§10.5 band 7: an accepted action from the latest touch outranks other undated work."""
    account = _account(client)
    program = _program(client, account["id"], "Launch program")
    latest = _interaction(client, account["id"], "Onboarding call", days_ago=1)
    residual = _task(client, program["id"], "Aging residual work")
    accepted = _task(client, program["id"], "Confirm the metric of record",
                     source_interaction_id=latest["id"])

    payload = _path(client, account["id"])
    order = _ids(payload)
    assert order.index(f"task:{accepted['id']}") < order.index(f"task:{residual['id']}")
    move = payload["next_move"]
    assert move["reason_code"] == "latest_interaction_action"
    assert move["band"] == 7


def test_provenance_names_the_interaction_it_came_from(client):
    """§6.5: a plain source label, kept separate from readiness evidence provenance."""
    account = _account(client)
    program = _program(client, account["id"], "Launch program")
    latest = _interaction(client, account["id"], "Onboarding call", days_ago=1)
    _task(client, program["id"], "Confirm the metric of record", due_date=utc_day(-1),
          source_interaction_id=latest["id"])

    move = _path(client, account["id"])["next_move"]
    assert move["provenance"]["kind"] == "interaction"
    assert move["provenance"]["label"].startswith("From ")
    assert move["provenance"]["interaction_id"] == latest["id"]


# --- snooze and suppression --------------------------------------------------------------------

def test_the_snooze_key_reuses_the_queue_key_and_suppresses_in_both_places(client):
    """§6.1: the projection id is two-part and would 422; `snooze_key` is the queue's own key."""
    account = _account(client)
    program = _program(client, account["id"], "Launch program")
    task = _task(client, program["id"], "Chase the integration note", due_date=utc_day(-6))

    payload = _path(client, account["id"])
    move = payload["next_move"]
    assert move["id"] == f"task:{task['id']}"
    assert move["snooze_key"] == f"open_task:task:{task['id']}"
    assert len(move["snooze_key"].split(":")) == 3

    # The key is accepted by the queue's own writer, and the item disappears from both surfaces.
    assert client.post("/api/queue/snooze", json={
        "item_key": move["snooze_key"], "snooze_until": utc_day(7),
    }).status_code in (200, 201)
    after = _path(client, account["id"])
    assert f"task:{task['id']}" not in _ids(after)
    # The warning is rendered copy as of Slice 7, so it is asserted as a sentence rather than as a
    # substring: one hidden row reads in the singular, and the response still calls itself complete
    # because a suppression is subtractive, not a failure to read a source.
    assert "1 item is snoozed and is not shown here" in after["coverage"]["warnings"]
    assert after["coverage"]["status"] == "complete"

    # A second snooze uses the plural, so the sentence is generated rather than hard-coded singular.
    _task(client, program["id"], "Confirm the environment date", due_date=utc_day(-5))
    client.post("/api/queue/snooze", json={
        "item_key": _path(client, account["id"])["next_move"]["snooze_key"],
        "snooze_until": utc_day(7)})
    assert "2 items are snoozed and are not shown here" in (
        _path(client, account["id"])["coverage"]["warnings"])


def test_a_snooze_resurfaces_on_its_return_date(client):
    """§10.4: Account Path does not invent a second expiry rule; it reuses the queue's."""
    account = _account(client)
    program = _program(client, account["id"], "Launch program")
    task = _task(client, program["id"], "Chase the integration note", due_date=utc_day(-6))
    key = _path(client, account["id"])["next_move"]["snooze_key"]

    client.post("/api/queue/snooze", json={"item_key": key, "snooze_until": utc_day(30)})
    assert f"task:{task['id']}" not in _ids(_path(client, account["id"]))

    # A return date that has already passed suppresses nothing — the same rule the queue applies.
    client.post("/api/queue/snooze", json={"item_key": key, "snooze_until": utc_day(-1)})
    assert f"task:{task['id']}" in _ids(_path(client, account["id"]))


def test_suppression_is_the_queues_own_helper_not_a_second_implementation(client):
    """§10.4: the underlying-change rule is shared code, so it cannot drift between surfaces."""
    from app import queue

    account = _account(client)
    program = _program(client, account["id"], "Launch program")
    task = _task(client, program["id"], "Chase the integration note", due_date=utc_day(-6))
    key = _path(client, account["id"])["next_move"]["snooze_key"]
    client.post("/api/queue/snooze", json={"item_key": key, "snooze_until": utc_day(30)})

    conn = sqlite3.connect(client.db_path)
    conn.row_factory = sqlite3.Row
    try:
        overlays = queue._latest_overlays(conn)
        assert key in overlays
        stale = queue.suppression_state(conn, [key], overlays[key]["created_at"], utc_day())
        assert stale == "snoozed"
        # An underlying change recorded after the overlay resurfaces the item regardless.
        changed = queue.suppression_state(conn, [key], "2099-01-01T00:00:00Z", utc_day())
        assert changed is None
    finally:
        conn.close()
    assert task["id"]


def test_a_gate_item_offers_no_snooze_key_rather_than_a_key_that_would_fail(client):
    """§6.1: `phase_gate_item` has no queue object table, so a key here would 422 on click."""
    account = _account(client)
    program = _program(client, account["id"], "Launch program", phase="launch")
    _gate(client, program["id"], "Launch gate", "launch", ["Security review complete"])

    move = _path(client, account["id"])["next_move"]
    assert move["reason_code"] == "current_gate_item"
    assert move["snooze_key"] is None
    assert move["native_target"]["record_type"] == "phase_gate_item"


def test_only_a_gate_item_claims_a_phase(client):
    """§6.2's phase filter reads `phase`, and only a gate item genuinely has one.

    A Task belongs to a program. Stamping it with whatever phase that program happens to be in
    would let the path filter present it as work the phase requires, which the record never says.
    """
    account = _account(client)
    program = _program(client, account["id"], "Launch program", phase="launch")
    _gate(client, program["id"], "Launch gate", "launch", ["Security review complete"])
    _task(client, program["id"], "Chase the integration note", due_date=utc_day(-3))

    items = {c["source_type"]: c for c in _path(client, account["id"])["work"]["you_own"]}
    assert items["phase_gate_item"]["phase"] == "launch"
    assert items["task"]["phase"] is None


# --- account essentials --------------------------------------------------------------------------

def test_readiness_comes_first_and_checklists_are_a_labelled_supplement(client):
    """§10.7: readiness is primary; a checkbox is not evidence and never reaches a pillar state."""
    account = _account(client)
    _program(client, account["id"], "Launch program")
    _checklist(client, account["id"], "first_call", "Confirm the data-processing contact")

    essentials = _path(client, account["id"])["work"]["account_essentials"]
    assert essentials["readiness"] is not None
    assert list(essentials.keys()).index("readiness") == 0
    supplement = essentials["checklist_supplements"]
    assert len(supplement) == 1
    assert supplement[0]["compatibility_source"] is True
    assert supplement[0]["source_label"] == "Standard onboarding requirement"


def test_no_checklist_item_is_labelled_a_current_phase_requirement(client):
    """§10.7: `section` is time from kickoff, not a program phase, and must not claim otherwise."""
    account = _account(client)
    program = _program(client, account["id"], "Launch program", phase="programmatic")
    for section in ("first_90_days", "first_call", "first_30_days"):
        _checklist(client, account["id"], section, f"Item for {section}")

    supplement = _path(client, account["id"])["work"]["account_essentials"]["checklist_supplements"]
    assert [row["section"] for row in supplement] == [
        "first_call", "first_30_days", "first_90_days",
    ]
    blob = repr(supplement).lower()
    assert "current-phase" not in blob and "current phase" not in blob
    assert all(row["section"] != program["phase"] for row in supplement)


def test_account_wide_checklist_items_stay_visible_in_a_selected_program(client):
    """§10.7/§7.4: an account-wide requirement is visible in every scope."""
    account = _account(client)
    program = _program(client, account["id"], "Launch program")
    _checklist(client, account["id"], "first_call", "Confirm the data-processing contact")

    scoped = _path(client, account["id"], program_id=program["id"])
    supplement = scoped["work"]["account_essentials"]["checklist_supplements"]
    assert [row["scope_label"] for row in supplement] == ["Account-wide"]


def test_a_done_or_na_checklist_item_is_not_an_open_supplement(client):
    """§10.7: `na` is Not applicable; it never counts as incomplete."""
    account = _account(client)
    _program(client, account["id"], "Launch program")
    done = _checklist(client, account["id"], "first_call", "Signed data agreement")
    na = _checklist(client, account["id"], "first_call", "Works council consultation")
    open_item = _checklist(client, account["id"], "first_call", "SSO contact identified")
    client.patch(f"/api/checklist-items/{done['id']}", json={"status": "done"})
    client.patch(f"/api/checklist-items/{na['id']}", json={"status": "na"})

    supplement = _path(client, account["id"])["work"]["account_essentials"]["checklist_supplements"]
    assert [row["source_id"] for row in supplement] == [open_item["id"]]


def test_readiness_passes_through_its_own_four_axis_vocabulary(client):
    """§12.1: state, freshness, coverage, and applicability stay four independent axes."""
    account = _account(client)
    _program(client, account["id"], "Launch program")

    readiness = _path(client, account["id"])["work"]["account_essentials"]["readiness"]
    assert readiness["coverage"]["status"] in ("complete", "partial", "unavailable")
    pillars = list(readiness["pillars"])
    for entry in readiness["programs"]:
        pillars.extend(entry["pillars"])
    assert pillars
    for pillar in pillars:
        assert pillar["state"] in ("met", "thin", "unknown", "conflicted", "not_applicable")
        assert pillar["freshness"] in ("current", "stale", "mixed", "undated", "not_applicable")
        assert pillar["applicability"] in ("required", "optional", "not_due", "not_applicable")
        # No composite score, in Account Path's copy of the response either.
        assert "score" not in pillar and "grade" not in pillar


def test_readiness_coverage_is_reported_separately_from_execution_coverage(client):
    """§10.9: a pillar the app could not evaluate says nothing about the Task list."""
    account = _account(client)
    _program(client, account["id"], "Launch program")

    payload = _path(client, account["id"])
    execution = payload["coverage"]
    readiness = payload["work"]["account_essentials"]["readiness"]["coverage"]
    assert execution is not readiness
    assert "failed_evaluators" not in execution
    assert payload["integration"]["pillars"] == "connected"
    assert payload["integration"]["proposed_updates"] == "not_connected"


# --- contract dates ------------------------------------------------------------------------------

def test_a_contract_inside_its_configured_lead_window_becomes_band_four(client):
    """§10.5 band 4. The window comes from the record's own notice period, not from a constant."""
    account = _account(client)
    _program(client, account["id"], "Launch program")
    r = client.post("/api/contracts", json={
        "account_id": account["id"], "version_label": "Initial term",
        "renewal_date": utc_day(60), "notice_period_days": 90, "is_current": True,
    })
    assert r.status_code == 201, r.text

    payload = _path(client, account["id"])
    rows = [row for row in payload["work"]["you_own"]
            if row["reason_code"] == "contract_decision_window"]
    assert len(rows) == 1
    assert rows[0]["band"] == 4
    assert "90 days" in rows[0]["reason"]
    assert rows[0]["provenance"]["kind"] == "contract"


def test_a_contract_outside_its_lead_window_is_not_yet_work(client):
    account = _account(client)
    _program(client, account["id"], "Launch program")
    r = client.post("/api/contracts", json={
        "account_id": account["id"], "version_label": "Initial term",
        "renewal_date": utc_day(300), "notice_period_days": 60, "is_current": True,
    })
    assert r.status_code == 201, r.text

    assert "contract_decision_window" not in _codes(_path(client, account["id"]))


# --- dedupe, coverage, empty states, purity --------------------------------------------------------

def test_a_record_appears_once_even_when_several_sources_reach_it(client):
    """§7.3: a wrapper record never creates a second visible action."""
    account = _account(client)
    program = _program(client, account["id"], "Launch program")
    _task(client, program["id"], "Chase the integration note", due_date=utc_day(-6))

    ids = _ids(_path(client, account["id"]))
    assert len(ids) == len(set(ids))


def test_a_failed_adapter_names_itself_and_forbids_a_caught_up_claim(client, monkeypatch):
    """§10.9: adapter failure must not become a blank page or a false caught-up state."""
    account = _account(client)
    _program(client, account["id"], "Launch program")
    from app import execution_path as ep

    def boom(ctx):
        raise RuntimeError("tasks table unavailable")

    monkeypatch.setattr(ep, "_adapt_tasks", boom)
    payload = _path(client, account["id"])
    assert payload["coverage"]["status"] == "partial"
    assert [o["source"] for o in payload["coverage"]["omitted_sources"]] == ["tasks"]
    assert "tasks" not in payload["coverage"]["included_sources"]
    assert payload["empty_state"]["variant"] != "caught_up"


def test_a_failed_readiness_adapter_cannot_suppress_canonical_work(client, monkeypatch):
    """§10.9: a broken integration disconnects itself; it does not hide the Task list."""
    account = _account(client)
    program = _program(client, account["id"], "Launch program")
    _task(client, program["id"], "Chase the integration note", due_date=utc_day(-6))
    from app import execution_path as ep

    def boom(ctx):
        raise RuntimeError("readiness definitions unreadable")

    monkeypatch.setattr(ep, "_adapt_readiness", boom)
    payload = _path(client, account["id"])
    assert payload["next_move"]["source_type"] == "task"
    assert payload["integration"]["pillars"] == "not_connected"
    assert [o["source"] for o in payload["coverage"]["omitted_sources"]] == ["readiness"]


def test_an_account_with_no_program_reports_insufficient_plan_data(client):
    account = _account(client)

    payload = _path(client, account["id"])
    assert payload["next_move"] is None
    assert payload["empty_state"]["variant"] == "insufficient_plan_data"
    assert payload["program_paths"] == []


def test_a_failed_programs_adapter_is_not_reported_as_an_account_with_no_programs(client, monkeypatch):
    """`ctx.programs == []` has two causes and only one of them is a fact about the records.

    The adapter harness leaves the list empty when `_adapt_programs` raises, so reading it as
    "nothing is planned" states a positive claim on the strength of a failed read — and it did so
    by shadowing `coverage_incomplete`, the variant written for exactly this case.
    """
    account = _account(client)
    _program(client, account["id"], "Launch program")

    from app import execution_path
    monkeypatch.setattr(execution_path, "_adapt_programs",
                        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("programs down")))
    payload = _path(client, account["id"])
    assert payload["coverage"]["status"] != "complete"
    assert any(o["source"] == "programs" for o in payload["coverage"]["omitted_sources"])
    assert payload["empty_state"]["variant"] == "coverage_incomplete"
    assert "No program" not in payload["empty_state"]["message"]


def test_caught_up_is_only_legal_when_every_source_succeeded(client):
    account = _account(client)
    _program(client, account["id"], "Launch program")

    payload = _path(client, account["id"])
    assert payload["coverage"]["status"] == "complete"
    assert payload["empty_state"]["variant"] in ("caught_up", "prepare_for_next_gate")


def test_prepare_for_the_next_gate_surfaces_a_required_readiness_gap(client):
    """§6.1: the one path by which a readiness gap reaches Next best move — as a suggestion."""
    account = _account(client)
    _program(client, account["id"], "Launch program")

    payload = _path(client, account["id"])
    state = payload["empty_state"]
    assert state["variant"] == "prepare_for_next_gate"
    requirement = state["requirement"]
    assert requirement["applicability"] == "required"
    assert requirement["state"] in ("conflicted", "unknown", "thin")
    # It is a suggestion, not work: it never enters the operator's own list.
    assert _ids(payload, "you_own") == []


def test_opening_the_endpoint_writes_nothing(client):
    """§10.10: no audit event, no record change, no visit state — including no readiness write."""
    account = _account(client)
    program = _program(client, account["id"], "Launch program", phase="launch")
    _task(client, program["id"], "Chase the integration note", due_date=utc_day(-6))
    _gate(client, program["id"], "Launch gate", "launch", ["Security review complete"])
    _checklist(client, account["id"], "first_call", "Confirm the data-processing contact")

    before = _audit_count(client)
    for _ in range(3):
        _path(client, account["id"])
        _path(client, account["id"], program_id=program["id"])
    assert _audit_count(client) == before


def test_the_projection_is_stable_across_repeated_reads(client):
    """A rebuildable projection must answer the same question the same way."""
    account = _account(client)
    program = _program(client, account["id"], "Launch program", phase="launch")
    _task(client, program["id"], "Chase the integration note", due_date=utc_day(-6))
    _risk(client, program["id"], "Security review has not started", is_blocker=True)
    _gate(client, program["id"], "Launch gate", "launch", ["Security review complete"])

    first, second = _path(client, account["id"]), _path(client, account["id"])
    for payload in (first, second):
        payload.pop("stamp")
    assert first == second
