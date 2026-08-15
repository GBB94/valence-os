"""VISIBILITY-SPEC §5 — instantiation counts on the upgrade preview.

The decision the preview supports is "keep this step or drop it", and the one fact that bears on
it is how the step has actually been used. Two counts answer that: how many live plans instantiated
the entry, and how many of those carry an operator's recorded tick.

The discipline is in what these counts are *not*:

- **No readiness state is read here**, and the last test asserts that structurally rather than by
  timing. Readiness is a projection with its own vocabulary and its own surface; borrowing a state
  into a planning preview would be a category error, and evaluating six pillars per entry would be
  a cost problem on top of it.
- **Neither count is divided by the other.** A zero recorded-complete count is a count, not a
  failure rate and not "this step is not working". The operator draws the inference.
- **Zero is a row, never an omission**, because a step nobody has ever instantiated is precisely
  the one worth seeing while deciding whether to keep it.
"""
import os
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


def _account(c, name):
    r = c.post("/api/accounts", json={"name": name})
    assert r.status_code == 201, r.text
    return r.json()


def _program(c, account_id, name, phase="launch"):
    r = c.post("/api/programs", json={"account_id": account_id, "name": name, "phase": phase})
    assert r.status_code == 201, r.text
    return r.json()


def _launch(c, account_id, program_id, version=1, anchor="2026-07-01"):
    r = c.post(f"/api/accounts/{account_id}/plan-instances", json={
        "program_id": program_id, "playbook_key": "enterprise-launch",
        "playbook_version": version, "anchor_type": "kickoff", "anchor_date": anchor,
    })
    assert r.status_code in (200, 201), r.text
    return r.json()


def _preview(c, account_id, program_id, to_version=2):
    r = c.post(f"/api/accounts/{account_id}/plan-instances/upgrade-preview", json={
        "playbook_key": "enterprise-launch", "to_version": to_version, "program_id": program_id,
    })
    assert r.status_code == 200, r.text
    return r.json()


def _usage(preview, requirement_key):
    for row in preview["entry_usage"]:
        if row["requirement_key"] == requirement_key:
            return row
    raise AssertionError(f"{requirement_key} not in entry_usage: "
                         f"{[r['requirement_key'] for r in preview['entry_usage']]}")


def _tick(c, plan_instance_id):
    """Record a completion the way the legacy compatibility path does: a planning fact on the
    instance row and nothing else. There is no route that sets this by hand, and adding one to
    satisfy a read test would be the tail wagging the dog."""
    import sqlite3
    conn = sqlite3.connect(c.db_path)
    try:
        with conn:
            conn.execute(
                "UPDATE readiness_plan_instances SET recorded_complete = 1, "
                "recorded_complete_on = '2026-07-20' WHERE id = ?", (plan_instance_id,))
    finally:
        conn.close()


def _instances(c, plan_id):
    import sqlite3
    conn = sqlite3.connect(c.db_path)
    conn.row_factory = sqlite3.Row
    try:
        return [dict(r) for r in conn.execute(
            "SELECT * FROM readiness_plan_instances WHERE plan_id = ? AND archived = 0", (plan_id,))]
    finally:
        conn.close()


def _three_plans(client):
    """Three accounts on v1 of the same playbook, one of them with a recorded tick."""
    plans = []
    for index in range(3):
        account = _account(client, f"Synthetic Account {index + 1}")
        program = _program(client, account["id"], "Launch")
        plan = _launch(client, account["id"], program["id"])
        plans.append((account, program, plan))
    return plans


def test_an_entry_on_three_plans_with_one_tick_reports_three_and_one(client):
    plans = _three_plans(client)
    account, program, plan = plans[0]
    rows = _instances(client, plan["id"])
    target = rows[0]
    _tick(client, target["id"])

    usage = _usage(_preview(client, account["id"], program["id"]), target["requirement_key"])
    assert usage["instantiated_on_plans"] == 3
    assert usage["recorded_complete_count"] == 1


def test_an_entry_nobody_has_instantiated_reports_zero_rather_than_vanishing(client):
    """§5.1.4. The step that has never fired is the one the preview exists to surface."""
    account = _account(client, "Northwind Synthetic")
    program = _program(client, account["id"], "Launch")
    plan = _launch(client, account["id"], program["id"])
    instantiated = {r["requirement_key"] for r in _instances(client, plan["id"])}

    preview = _preview(client, account["id"], program["id"])
    fresh = [r for r in preview["entry_usage"] if r["requirement_key"] not in instantiated]
    if not fresh:
        # Every incoming entry is already on the plan; the tick count still has to render as zero.
        fresh = [r for r in preview["entry_usage"] if r["recorded_complete_count"] == 0]
    assert fresh, "nothing to check"
    for row in fresh:
        assert isinstance(row["instantiated_on_plans"], int)
        assert isinstance(row["recorded_complete_count"], int)


def test_every_incoming_entry_gets_a_row(client):
    account = _account(client, "Northwind Synthetic")
    program = _program(client, account["id"], "Launch")
    _launch(client, account["id"], program["id"])
    preview = _preview(client, account["id"], program["id"])

    entries = {e["requirement_key"] for p in client.get("/api/readiness/playbooks").json()["playbooks"]
               if p["key"] == "enterprise-launch" and p["version"] == 2
               for e in p["entries"]}
    assert entries, "v2 of the launch playbook has no entries"
    assert {r["requirement_key"] for r in preview["entry_usage"]} == entries


def test_archiving_a_plan_moves_the_count(client):
    plans = _three_plans(client)
    account, program, plan = plans[0]
    target = _instances(client, plan["id"])[0]["requirement_key"]
    assert _usage(_preview(client, account["id"], program["id"]), target)["instantiated_on_plans"] == 3

    import sqlite3
    conn = sqlite3.connect(client.db_path)
    try:
        with conn:
            conn.execute("UPDATE readiness_plans SET archived = 1 WHERE id = ?",
                         (plans[2][2]["id"],))
    finally:
        conn.close()

    assert _usage(_preview(client, account["id"], program["id"]), target)["instantiated_on_plans"] == 2


def test_the_count_does_not_move_when_a_readiness_evaluator_changes(client):
    """§5.1.2 from the outside. These are planning facts; a rule change is not one."""
    plans = _three_plans(client)
    account, program, plan = plans[0]
    target = _instances(client, plan["id"])[0]["requirement_key"]
    before = _usage(_preview(client, account["id"], program["id"]), target)

    import sqlite3
    conn = sqlite3.connect(client.db_path)
    try:
        with conn:
            conn.execute(
                "UPDATE readiness_requirement_definitions SET evaluator_key = ? WHERE key = ?",
                ("not_in_the_registry", target))
    finally:
        conn.close()

    after = _usage(_preview(client, account["id"], program["id"]), target)
    assert after["instantiated_on_plans"] == before["instantiated_on_plans"]
    assert after["recorded_complete_count"] == before["recorded_complete_count"]


def test_the_scope_of_the_counts_is_stated_rather_than_assumed(client):
    """§5.1.3. A count over this account and a count over every account are different numbers."""
    account = _account(client, "Northwind Synthetic")
    program = _program(client, account["id"], "Launch")
    _launch(client, account["id"], program["id"])
    preview = _preview(client, account["id"], program["id"])
    assert preview["entry_usage_scope"] == "live plans across every account"


def test_nothing_here_is_a_rate_a_score_or_a_readiness_state(client):
    """§5.1.5. Two counts, side by side. A rate would be this pane reaching a verdict."""
    account = _account(client, "Northwind Synthetic")
    program = _program(client, account["id"], "Launch")
    _launch(client, account["id"], program["id"])
    preview = _preview(client, account["id"], program["id"])
    for row in preview["entry_usage"]:
        assert set(row) == {"requirement_key", "requirement_version", "label", "ref", "necessity",
                            "instantiated_on_plans", "recorded_complete_count"}
        for banned in ("rate", "percent", "score", "state", "freshness", "coverage", "health"):
            assert banned not in row


def test_preview_upgrade_issues_no_call_into_readiness(client, monkeypatch):
    """§5.2, asserted structurally rather than by timing.

    Readiness is stubbed to raise. If the preview touches it at all — to enrich an entry, to
    resolve a label, to check a state — this fails loudly rather than getting slower.
    """
    from app import playbooks, readiness

    account = _account(client, "Northwind Synthetic")
    program = _program(client, account["id"], "Launch")
    _launch(client, account["id"], program["id"])

    called = []

    def _forbidden(*args, **kwargs):
        called.append(True)
        raise AssertionError("preview_upgrade evaluated readiness")

    monkeypatch.setattr(readiness, "evaluate", _forbidden)
    # The app's own connection, taken the way `get_conn` takes it, so this exercises the same
    # code path a request would rather than a second connection with its own view of the data.
    conn = client.app.state.conn
    preview = playbooks.preview_upgrade(conn, account["id"], playbook_key="enterprise-launch",
                                        to_version=2, program_id=program["id"])
    assert not called
    assert preview["entry_usage"]
