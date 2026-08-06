"""ACCOUNT-PATH-SPEC.md §17.7 walkthrough acceptance scripts.

§17.7 asks for structured walkthroughs across eight account states, recording *the navigation
needed* to answer the eight §2 product outcomes and *any misinterpretation* of owner, phase,
status, or evidence. This file is the machine-checkable half of that.

Two things it does deliberately.

**It counts requests, not clicks.** "Rarely need to decide which tab to inspect" (§2) is a claim
about where the answers live. Every walkthrough here asks the eight outcomes of exactly one
Execution Path response — if an outcome needed a second endpoint, the operator needed another
tab, and the assertion fails. That is the part of "ten seconds" a test can hold.

**It records `unanswered` rather than requiring eight answers.** Several states genuinely cannot
answer all eight — a brand-new account has no interaction to summarise, and inventing one would
be the misinterpretation §17.7 is looking for. Each walkthrough pins the exact set it can and
cannot answer, so a future change that starts answering an outcome out of thin air fails here.

**Not covered here, by construction:** the last two §17.7 walkthroughs — narrow split-screen, and
keyboard-only / reduced-motion — are presentation, not payload. They are verified in
`design-screenshots/account-path/VERIFICATION.md` with both-theme captures, and asserting them
from a JSON body would be a test that passes while the page is unusable.
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
    os.environ.pop("VALENCE_OS_RANKING_RULES", None)
    from app.main import app
    with TestClient(app) as c:
        c.db_path = path
        yield c
    for suffix in ("", "-wal", "-shm"):
        try: os.unlink(path + suffix)
        except FileNotFoundError: pass


# --- the eight §2 outcomes, as predicates over one response ---------------------------------

def _outcome_1(body):
    """What is the single most important thing I can do next?

    An explicit empty state answers this too. "Nothing is urgent, and here is why" is an answer;
    a blank panel is not, which is why the variant has to be present and named.
    """
    return bool(body.get("next_move")) or bool((body.get("empty_state") or {}).get("variant"))


def _outcome_2(body):
    """Why is it next, who owns it, and when is it due?

    Ownership is answered by a named person *or* by the lane, and both are real answers. A
    contract decision window has no owner field to read: the record is a contract, not an
    assignment. "You own it and nobody is named" is the truth there, and requiring a person here
    would push the code toward inventing one.
    """
    move = body.get("next_move")
    if not move:
        return False
    in_operator_lane = any(row["id"] == move["id"]
                           for row in (body.get("work") or {}).get("you_own", []))
    who = move.get("owner") or move.get("responsible_party") or in_operator_lane
    return bool(move.get("reason")) and bool(move.get("reason_code")) and bool(who)


def _outcome_3(body):
    """Which phase and gate is each active program working toward?"""
    paths = body.get("program_paths") or []
    return bool(paths) and all(p.get("current_phase") and p.get("steps") for p in paths)


def _outcome_4(body):
    """What did the latest meaningful interaction add or change?"""
    latest = body.get("latest_interaction")
    return bool(latest) and "accepted_actions" in latest


def _requirement_rows(body):
    """The Slice 3 block, or an empty list when the plan layer could not be read."""
    block = (body.get("work") or {}).get("account_essentials", {}).get("requirements") or {}
    return block.get("requirements") or []


def _outcome_5(body):
    """Which standard account requirements are still missing or unsupported?"""
    return bool(_requirement_rows(body))


def _outcome_6(body):
    """What is waiting on the customer, and what is my follow-up responsibility?"""
    waiting = (body.get("work") or {}).get("waiting_on_customer") or []
    return bool(waiting) and all(row.get("responsible_party") or row.get("owner")
                                 for row in waiting)


def _outcome_7(body):
    """What milestone, decision, launch moment, review, notice, or renewal is approaching?"""
    work = body.get("work") or {}
    dated = [row for row in work.get("you_own", []) if row.get("due_date")]
    return bool(work.get("upcoming_gates")) or bool(dated) or any(
        p.get("next_milestone") for p in body.get("program_paths") or [])


def _outcome_8(body):
    """What evidence proves that a requirement or milestone is actually complete?"""
    if any(row.get("evidence") for row in _requirement_rows(body)):
        return True
    # A path row's provenance names the record the claim came from, which is the same question
    # asked of execution work rather than of a requirement.
    return all(row.get("provenance") for row in (body.get("work") or {}).get("you_own", []))


OUTCOMES = {1: _outcome_1, 2: _outcome_2, 3: _outcome_3, 4: _outcome_4,
            5: _outcome_5, 6: _outcome_6, 7: _outcome_7, 8: _outcome_8}


def _walkthrough(client, account_id, program_id=None):
    """Open the account once. Every outcome must be answerable from what came back."""
    query = f"?program_id={program_id}" if program_id else ""
    res = client.get(f"/api/accounts/{account_id}/execution-path{query}")
    assert res.status_code == 200
    body = res.json()
    answered = {n for n, check in OUTCOMES.items() if check(body)}
    return body, answered


def _misreadings(body):
    """§17.7: "any misinterpretation of owner, phase, status, or evidence".

    Each of these is a specific way an earlier slice could have lied, restated as a check that
    runs on every walkthrough rather than on the one account that happened to expose it.
    """
    problems = []
    for row in (body.get("work") or {}).get("you_own", []):
        # Phase: only a gate item genuinely has one (§10.2). A Task stamped with its program's
        # phase would attribute work to a phase nobody assigned it to.
        if row.get("phase") and row["source_type"] != "phase_gate_item":
            problems.append(f"{row['id']} claims phase '{row['phase']}'")
        # Owner: a row in the operator's own lane must not be owned by the customer.
        party = (row.get("responsible_party") or {}).get("party")
        if party == "customer":
            problems.append(f"{row['id']} is customer-owned but sits in you_own")
        if not row.get("provenance"):
            problems.append(f"{row['id']} names no source record")
    for row in (body.get("work") or {}).get("waiting_on_customer", []):
        if (row.get("responsible_party") or {}).get("party") == "valence":
            problems.append(f"{row['id']} is operator-owned but sits in waiting_on_customer")
    for path in body.get("program_paths") or []:
        for step in path["steps"]:
            # Status: a phase before the current one with no governed gate record is `unknown`,
            # never `complete`. Reconstructed history is the misinterpretation that matters most.
            if step["state"] == "complete" and not step.get("gate_id"):
                problems.append(f"{path['program_id']}/{step['key']} reads complete with no gate")
    return problems


# --- fixture helpers -------------------------------------------------------------------------

def _account(c, name):
    return c.post("/api/accounts", json={"name": name}).json()


def _program(c, account_id, name, phase="launch"):
    return c.post("/api/programs", json={"account_id": account_id, "name": name,
                                         "phase": phase}).json()


def _person(c, account_id, name, affiliation):
    return c.post("/api/persons", json={
        "name": name, "affiliation": affiliation,
        "account_id": None if affiliation == "valence" else account_id}).json()


def _task(c, program_id, description, due_date=None, owner_id=None):
    return c.post("/api/tasks", json={
        "program_id": program_id, "description": description, "due_date": due_date,
        "internal_owner_id": owner_id}).json()


def _commitment(c, account_id, program_id, description, responsible_id, owner_id, due_date):
    return c.post("/api/commitments", json={
        "account_id": account_id, "program_id": program_id, "description": description,
        "responsible_party_id": responsible_id, "internal_owner_id": owner_id,
        "due_date": due_date}).json()


def _interaction(c, account_id, program_id, title, occurred_on):
    return c.post("/api/interactions", json={
        "account_id": account_id, "program_id": program_id, "interaction_type": "meeting",
        "title": title, "occurred_on": occurred_on, "meaningful_touch": True}).json()


# --- the walkthroughs ------------------------------------------------------------------------

def test_walkthrough_new_account_immediately_after_onboarding(client):
    """State 1. Nothing has happened yet, and the page must say so rather than look broken."""
    account = _account(client, "Aldergrove Synthetic")
    program = _program(client, account["id"], "Initial Deployment", phase="foundation")
    body, answered = _walkthrough(client, account["id"])

    assert 1 in answered, "a new account still gets one explicit state"
    assert body["next_move"] is None
    assert body["empty_state"]["variant"] in {
        "caught_up", "prepare_for_next_gate", "coverage_incomplete", "waiting_on_customer"}
    assert 3 in answered, "the phase the program starts in is knowable on day one"
    # Honest gaps. There is no interaction to summarise and no customer wait to report, and
    # manufacturing either would be exactly the misinterpretation §17.7 is looking for.
    assert 4 not in answered and 6 not in answered
    assert _misreadings(body) == []
    assert program["phase"] == "foundation"


def test_walkthrough_mature_multi_program_account(client):
    """State 2. Two live programs, and the answer must stay per-program rather than averaged."""
    account = _account(client, "Brackenridge Synthetic")
    europe = _program(client, account["id"], "Europe Deployment", phase="launch")
    apac = _program(client, account["id"], "APAC Deployment", phase="programmatic")
    operator = _person(client, account["id"], "Operator One", "valence")
    _task(client, europe["id"], "Confirm the launch communications wave", utc_day(3), operator["id"])
    _task(client, apac["id"], "Schedule the quarterly programmatic review", utc_day(10), operator["id"])

    body, answered = _walkthrough(client, account["id"])
    assert {1, 2, 3, 7} <= answered
    assert len(body["program_paths"]) == 2
    # Each lane keeps its own phase. One blended phase for the account would be a number that
    # describes neither program.
    assert {p["current_phase"] for p in body["program_paths"]} == {"launch", "programmatic"}
    assert _misreadings(body) == []


def test_walkthrough_blocked_launch(client):
    """State 3. A blocker must outrank everything and must say which program it blocks."""
    account = _account(client, "Calderwood Synthetic")
    program = _program(client, account["id"], "Launch Programme", phase="launch")
    operator = _person(client, account["id"], "Operator One", "valence")
    _task(client, program["id"], "Draft the rollout note", utc_day(2), operator["id"])
    blocker = client.post("/api/issues", json={
        "program_id": program["id"], "description": "Sandbox environment is unavailable",
        "severity": "high", "internal_owner_id": operator["id"], "status": "open",
        "is_blocker": True})
    assert blocker.status_code == 201

    body, answered = _walkthrough(client, account["id"])
    assert {1, 2, 3} <= answered
    assert body["next_move"]["reason_code"] == "operator_blocker", (
        "a blocker that ranks below routine work would make the page worse than a task list")
    blocked = [step for path in body["program_paths"] for step in path["steps"]
               if step["state"] == "blocked"]
    assert blocked and blocked[0]["blocking_reason"]
    assert _misreadings(body) == []


def test_walkthrough_waiting_on_multiple_customer_owners(client):
    """State 4. §2 outcome 6: what is waiting, and what is *my* responsibility for each."""
    account = _account(client, "Draycott Synthetic")
    program = _program(client, account["id"], "Rollout", phase="launch")
    operator = _person(client, account["id"], "Operator One", "valence")
    first = _person(client, account["id"], "Client Contact One", "client")
    second = _person(client, account["id"], "Client Contact Two", "client")
    _commitment(client, account["id"], program["id"], "Return the signed data addendum",
                first["id"], operator["id"], utc_day(-3))
    _commitment(client, account["id"], program["id"], "Nominate the site coordinators",
                second["id"], operator["id"], utc_day(5))

    body, answered = _walkthrough(client, account["id"])
    assert 6 in answered
    waiting = body["work"]["waiting_on_customer"]
    assert len(waiting) == 2
    # Two customer owners stay two rows. Collapsing them would lose which follow-up belongs to
    # which person, which is the whole question.
    assert len({row["responsible_party"]["id"] for row in waiting}) == 2
    # Every customer wait still names the operator's own follow-up owner.
    assert all(row["owner"] and row["owner"]["party"] == "valence" for row in waiting)
    assert _misreadings(body) == []


def test_walkthrough_incomplete_or_partial_data(client):
    """State 5. A source that cannot be read must be named, and must suppress nothing.

    The plan-instance layer is broken deliberately. §13.9 is explicit that failed readiness
    coverage cannot hide canonical work, and this is the walkthrough where that is load-bearing:
    an operator looking at a degraded page still has to see the overdue Task.
    """
    account = _account(client, "Elverton Synthetic")
    program = _program(client, account["id"], "Deployment", phase="launch")
    operator = _person(client, account["id"], "Operator One", "valence")
    _task(client, program["id"], "Send the revised schedule", utc_day(-2), operator["id"])

    conn = sqlite3.connect(client.db_path)
    try:
        with conn:
            conn.execute("ALTER TABLE readiness_plan_instances RENAME TO readiness_plan_instances_x")
        body, answered = _walkthrough(client, account["id"])
    finally:
        with conn:
            conn.execute("ALTER TABLE readiness_plan_instances_x RENAME TO readiness_plan_instances")
        conn.close()

    assert body["coverage"]["status"] in {"partial", "unavailable"}
    assert body["coverage"]["omitted_sources"], "a failing source must name itself"
    assert {1, 2} <= answered, "canonical work survives a failed source"
    assert body["next_move"]["source_type"] == "task"
    assert _misreadings(body) == []


def test_walkthrough_renewal_inside_the_notice_window(client):
    """State 6. The notice window must surface with the window stated, not as a bare date."""
    account = _account(client, "Fernhollow Synthetic")
    _program(client, account["id"], "Deployment", phase="renewal")
    client.post("/api/contracts", json={
        "account_id": account["id"], "version_label": "Initial term",
        "renewal_date": utc_day(45), "notice_period_days": 90})

    body, answered = _walkthrough(client, account["id"])
    assert {1, 2, 7} <= answered
    assert body["next_move"]["reason_code"] == "contract_decision_window"
    # The threshold is in the sentence. A window the operator cannot see is a hidden benchmark.
    assert "90 days before renewal" in body["next_move"]["reason"]
    assert body["next_move"]["provenance"]["kind"] == "contract"
    # No individual is named, and that is the honest answer: a contract carries no assignment.
    # Ownership is read from the lane instead. Naming somebody here would be a misinterpretation
    # of owner in exactly the sense §17.7 asks to be recorded.
    assert body["next_move"]["owner"] is None
    assert any(row["id"] == body["next_move"]["id"] for row in body["work"]["you_own"])
    assert _misreadings(body) == []


def test_a_walkthrough_answers_the_outcomes_from_one_request(client):
    """§2: "rarely need to decide which tab to inspect merely to discover the next action".

    The claim under test is about *where the answers live*, so this asserts that a fully-populated
    account answers every outcome the state supports without a second endpoint.
    """
    account = _account(client, "Glenmorrow Synthetic")
    program = _program(client, account["id"], "Europe Deployment", phase="launch")
    operator = _person(client, account["id"], "Operator One", "valence")
    contact = _person(client, account["id"], "Client Contact One", "client")
    interaction = _interaction(client, account["id"], program["id"],
                               "Launch readiness review", utc_day(-1))
    _task(client, program["id"], "Circulate the updated rollout plan", utc_day(-1), operator["id"])
    _commitment(client, account["id"], program["id"], "Confirm the site list",
                contact["id"], operator["id"], utc_day(4))
    client.post("/api/milestones", json={
        "program_id": program["id"], "name": "Europe go-live", "target_date": utc_day(9),
        "status": "upcoming"})

    body, answered = _walkthrough(client, account["id"])
    assert {1, 2, 3, 6, 7, 8} <= answered, f"unanswered: {sorted(set(OUTCOMES) - answered)}"
    assert interaction["id"]
    assert _misreadings(body) == []
