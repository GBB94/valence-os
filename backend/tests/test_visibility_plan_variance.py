"""VISIBILITY-SPEC §6 — plan variance, asserted over the response shape.

The arithmetic itself is a presentation rule and is tested in `frontend/src/requirementDetail.test.js`.
What has to be true on this side is the thing that makes the arithmetic safe: the payload must ship
the two planning dates as two named fields and must never offer `assessed_through` under a name that
implies completion.

That is the whole of §2.2's correction. `assessed_through` is the date evidence was assessed
*through* — the boundary of what the evaluator looked at. It is not the date a requirement became
true, and there is no field anywhere that is. A view given a key called `completed_on` will subtract
it from `due_date` without asking what it means, so the defence is that no such key exists.
"""
import os
import re
import tempfile

import pytest
from fastapi.testclient import TestClient


# Keys whose *name* invites reading the value as "when this was finished". Every one of them is
# either an operator-recorded planning fact or a count of them, and none is a readiness date.
COMPLETION_KEYS = {
    "recorded_complete",
    "recorded_complete_on",
    "recorded_complete_note",
    "recorded_complete_count",
    "recorded_complete_at_risk",
    "definition_of_done",
}

_IMPLIES_COMPLETION = re.compile(r"complet|finish|\bdone\b|actual", re.I)


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


def _walk(node, path="$"):
    """Every (path, key, value) pair in a JSON response, dicts and lists alike."""
    if isinstance(node, dict):
        for key, value in node.items():
            yield f"{path}.{key}", key, value
            yield from _walk(value, f"{path}.{key}")
    elif isinstance(node, list):
        for index, value in enumerate(node):
            yield from _walk(value, f"{path}[{index}]")


def _scope(client):
    account = client.post("/api/accounts", json={"name": "Northwind Synthetic"}).json()
    r = client.post("/api/programs", json={"account_id": account["id"], "name": "Launch",
                                           "phase": "launch"})
    assert r.status_code == 201, r.text
    program = r.json()
    r = client.post(f"/api/accounts/{account['id']}/plan-instances", json={
        "program_id": program["id"], "playbook_key": "enterprise-launch", "playbook_version": 1,
        "anchor_type": "kickoff", "anchor_date": "2026-06-01",
    })
    assert r.status_code in (200, 201), r.text
    return account, program


def _plan(client, account, program):
    return client.get(
        f"/api/accounts/{account['id']}/plan-instances?program_id={program['id']}").json()


def test_no_key_implies_completion_outside_the_recorded_tick(client):
    """§6.2. The allowlist is small on purpose: every name on it is operator-recorded."""
    account, program = _scope(client)
    for body in (_plan(client, account, program),
                 client.get(f"/api/accounts/{account['id']}/readiness"
                            f"?program_id={program['id']}").json()):
        offenders = [
            f"{path} ({key})" for path, key, _ in _walk(body)
            if _IMPLIES_COMPLETION.search(key) and key not in COMPLETION_KEYS
        ]
        assert not offenders, offenders


def test_assessed_through_is_only_ever_called_assessed_through(client):
    """The value may appear once, under its own name. A second name for it is a second meaning."""
    account, program = _scope(client)
    readiness = client.get(f"/api/accounts/{account['id']}/readiness"
                           f"?program_id={program['id']}").json()
    dates = {value for path, key, value in _walk(readiness)
             if key == "assessed_through" and isinstance(value, str)}
    for path, key, value in _walk(readiness):
        if key == "assessed_through" or not isinstance(value, str):
            continue
        if value in dates and _IMPLIES_COMPLETION.search(key):
            raise AssertionError(f"{path} carries an assessed-through date under {key!r}")


def test_the_two_planning_dates_ship_as_two_named_fields(client):
    """Both operands of the one legal subtraction, each named for what it is."""
    account, program = _scope(client)
    rows = [r for r in _plan(client, account, program)["requirements"] if r.get("playbook")]
    assert rows, "no planned requirements to check"
    for row in rows:
        assert "due_date" in row
        assert "recorded_complete_on" in row
        # Nothing marks itself complete at instantiation; the delta simply has no second operand.
        assert row["recorded_complete_on"] is None
        assert row["recorded_complete"] is False


def test_the_server_computes_no_variance(client):
    """§6 is a presentation rule. A stored or server-computed delta would be a third statement
    about the same two dates, free to disagree with the two it came from."""
    account, program = _scope(client)
    body = _plan(client, account, program)
    banned = re.compile(r"variance|days_late|days_early|slip|overrun|delta", re.I)
    offenders = [f"{path} ({key})" for path, key, _ in _walk(body) if banned.search(key)]
    assert not offenders, offenders


def test_a_recorded_tick_gives_the_delta_its_second_operand(client):
    """The one row that may be differenced, arriving with both dates and no delta attached."""
    import sqlite3
    account, program = _scope(client)
    conn = sqlite3.connect(client.db_path)
    conn.row_factory = sqlite3.Row
    try:
        row = conn.execute(
            "SELECT id FROM readiness_plan_instances WHERE account_id = ? AND archived = 0 "
            "AND due_date IS NOT NULL LIMIT 1", (account["id"],)).fetchone()
        assert row is not None, "no dated plan instance"
        with conn:
            conn.execute("UPDATE readiness_plan_instances SET recorded_complete = 1, "
                         "recorded_complete_on = '2026-06-22' WHERE id = ?", (row["id"],))
    finally:
        conn.close()

    ticked = [r for r in _plan(client, account, program)["requirements"]
              if r.get("recorded_complete")]
    assert len(ticked) == 1
    assert ticked[0]["recorded_complete_on"] == "2026-06-22"
    assert ticked[0]["due_date"]
    # Two dates, no arithmetic. The view does the subtraction because only the view knows it is
    # allowed to — both operands are planning facts here, and nowhere else.
    assert "days" not in ticked[0]
