"""VISIBILITY-SPEC §7.2 — the evaluator configuration is reported beside the reading.

The gap this closes is narrow and specific. A requirement definition names an evaluator and hands
it a config; the reading that comes back says `unknown` or `thin` and names the evaluator, but
never what it was asked to look for. That is worst in the one case the readiness spec designed for
— an evaluator key that is not in the allowlisted registry fails **closed** into `coverage:
partial` rather than dropping the pillar — because then nothing ran, and the only thing left that
could explain the degraded reading is the configuration nobody could see.

So these tests assert three things: the configuration is carried on every component, it survives
the evaluator's absence, and it is **configuration** and never a second reading. The last one is
the load-bearing rule: a config is an input, so nothing on it may claim a state, and the shape
must stay the definition's own values rather than a description of what the evaluator does.
"""
import json
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


def _account(c, name="Northwind Synthetic"):
    return c.post("/api/accounts", json={"name": name}).json()


def _readiness(c, account_id, program_id=None):
    url = f"/api/accounts/{account_id}/readiness"
    if program_id:
        url += f"?program_id={program_id}"
    r = c.get(url)
    assert r.status_code == 200, r.text
    return r.json()


def _components(result):
    for pillar in result["pillars"]:
        for component in pillar["components"]:
            yield pillar, component


def _sql(c, statement, params=()):
    conn = sqlite3.connect(c.db_path)
    try:
        with conn:
            conn.execute(statement, params)
    finally:
        conn.close()


def test_every_component_reports_the_configuration_it_was_evaluated_with(client):
    account = _account(client)
    result = _readiness(client, account["id"])
    seen = 0
    for pillar, component in _components(result):
        assert "evaluator_config" in component, \
            f"{pillar['key']}/{component['key']} names its evaluator but not its configuration"
        assert isinstance(component["evaluator_config"], dict)
        seen += 1
    assert seen > 0, "no components to check"


def test_the_configuration_is_the_definition_row_verbatim(client):
    """Not a paraphrase and not a subset. A rendered gloss could drift from the code; the values
    the definition actually stored cannot."""
    account = _account(client)
    result = _readiness(client, account["id"])
    conn = sqlite3.connect(client.db_path)
    conn.row_factory = sqlite3.Row
    try:
        stored = {
            (row["key"], row["version"]): json.loads(row["evaluator_config_json"] or "{}")
            for row in conn.execute(
                "SELECT key, version, evaluator_config_json FROM readiness_requirement_definitions")
        }
    finally:
        conn.close()
    checked = 0
    for _pillar, component in _components(result):
        expected = stored.get((component["definition_key"], component["definition_version"]))
        if expected is None:
            continue
        assert component["evaluator_config"] == expected, component["definition_key"]
        checked += 1
    assert checked > 0, "no component matched a stored definition"


def test_a_configured_requirement_actually_carries_operands(client):
    """A payload of empty dicts would satisfy the shape tests and tell an operator nothing."""
    account = _account(client)
    result = _readiness(client, account["id"])
    with_operands = [c for _p, c in _components(result) if c["evaluator_config"]]
    assert with_operands, "no component reports a single configured value"


def test_an_unallowlisted_evaluator_still_reports_what_was_configured(client):
    """The case §7.2 exists for. Nothing ran, the pillar degrades, and the configuration is the
    only remaining account of what was being asked."""
    account = _account(client)
    before = _readiness(client, account["id"])
    target = next(c for _p, c in _components(before) if c["evaluator_config"])
    config_before = target["evaluator_config"]

    _sql(client, "UPDATE readiness_requirement_definitions SET evaluator_key = ? WHERE key = ?",
         ("not_in_the_registry", target["definition_key"]))

    after = _readiness(client, account["id"])
    broken = next(c for _p, c in _components(after) if c["definition_key"] == target["definition_key"])
    assert broken["state"] == "unknown"
    assert broken["evaluator_key"] == "not_in_the_registry"
    # Unchanged: the configuration is an input to the reading, so the reading failing does not
    # take it with it.
    assert broken["evaluator_config"] == config_before
    pillar = next(p for p, c in _components(after) if c["definition_key"] == target["definition_key"])
    assert after["coverage"]["status"] == "partial"
    assert pillar["key"] in json.dumps(after["coverage"]) or \
        "not_in_the_registry" in json.dumps(after["coverage"])


def test_a_configuration_never_carries_a_state(client):
    """RELATIONSHIP-READINESS-SPEC.md §2: readiness is a projection with one source. A config that
    could carry `met`, a freshness, or a coverage value would be a stored second reading arriving
    through the definition table."""
    account = _account(client)
    result = _readiness(client, account["id"])
    forbidden = {"state", "freshness", "coverage", "applicability", "met", "status", "verdict"}
    for pillar, component in _components(result):
        overlap = forbidden & set(component["evaluator_config"])
        assert not overlap, f"{pillar['key']}/{component['key']} config claims {overlap}"


def test_a_suppressed_component_reports_its_configuration_too(client):
    """A `not_applicable` decision silences the requirement without changing what it was
    configured to look for — and the operator reviewing the decision is exactly who needs it."""
    account = _account(client)
    before = _readiness(client, account["id"])
    pillar, target = next((p, c) for p, c in _components(before) if c["evaluator_config"])
    r = client.post(f"/api/accounts/{account['id']}/readiness-exceptions", json={
        "requirement_key": target["definition_key"],
        "kind": "not_applicable", "reason": "Out of scope for this synthetic engagement.",
        "actor_id": "op-1",
    })
    assert r.status_code in (200, 201), r.text

    after = _readiness(client, account["id"])
    suppressed = next(c for _p, c in _components(after)
                      if c["definition_key"] == target["definition_key"])
    assert suppressed.get("applicability_override") is not None
    assert suppressed["evaluator_config"] == target["evaluator_config"]


def test_the_plan_row_carries_the_configuration_the_readiness_reading_does(client):
    """One value, reached two ways. A plan row that reported a different configuration than the
    readiness reading would be the second source of truth in miniature."""
    account = _account(client)
    r = client.post("/api/programs", json={"account_id": account["id"], "name": "Region rollout",
                                           "phase": "programmatic"})
    assert r.status_code == 201, r.text
    program = r.json()

    r = client.post(f"/api/accounts/{account['id']}/plan-instances", json={
        "program_id": program["id"],
        "playbook_key": "enterprise-launch", "playbook_version": 1,
        "anchor_type": "kickoff", "anchor_date": "2026-07-01",
    })
    assert r.status_code in (200, 201), r.text

    plan = client.get(
        f"/api/accounts/{account['id']}/plan-instances?program_id={program['id']}").json()
    reading = {c["definition_key"]: c["evaluator_config"]
               for _p, c in _components(_readiness(client, account["id"], program["id"]))}
    checked = 0
    for row in plan["requirements"]:
        if "evaluator_config" not in row:
            continue      # a legacy pinned version claims no reading at all, and so no config
        assert row["evaluator_config"] == reading.get(row["requirement_key"]), row["requirement_key"]
        checked += 1
    assert checked > 0, "no plan row carried a configuration"


def test_this_slice_adds_no_table_and_no_column(client):
    """§7.2 is presentation over a value the definition table has stored since migration 0041."""
    conn = sqlite3.connect(client.db_path)
    try:
        columns = {row[1] for row in conn.execute(
            "PRAGMA table_info(readiness_requirement_definitions)")}
        tables = {row[0] for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'")}
    finally:
        conn.close()
    assert "evaluator_config_json" in columns
    assert not [c for c in columns if c.startswith("evaluator_config") and c != "evaluator_config_json"]
    assert not [t for t in tables if "evaluator_config" in t]
