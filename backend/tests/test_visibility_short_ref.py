"""VISIBILITY-SPEC §7.4 — a speakable reference id on configuration objects.

Two people discussing a requirement definition on a call have to read a label back word for word.
A four-character token settles it. The token adds no column: it is derived from the id the row
already has, on every read.

The reason this is a server derivation rather than a client one is the only interesting thing
about it. A reference that names two rows is worse than no reference, because both people would
be certain they were talking about the same object — so uniqueness has to be checked against the
**whole population**, not against whatever subset a screen happens to render. That also makes it
stable: the same definition gets the same token in the readiness reading, in the plan row, and in
the definitions listing, because all three derive it from the same set.
"""
import os
import sqlite3
import tempfile

import pytest
from fastapi.testclient import TestClient

from app.short_ref import short_refs


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


def _components(result):
    for pillar in result["pillars"]:
        for component in pillar["components"]:
            yield component


# --- the derivation ----------------------------------------------------------------------------

def test_a_reference_is_short_and_derived_from_the_id(client):
    refs = short_refs(["rrd-breadth-contacts-1", "rpe-l1-a"])
    assert refs["rrd-breadth-contacts-1"] == "RBC1"
    assert refs["rpe-l1-a"] == "RLA"


def test_two_rows_never_share_a_reference(client):
    # The whole point. Widening is uniform so the screen keeps one vocabulary rather than mixing
    # a four-character token with a nine-character one.
    refs = short_refs(["alpha-one", "alpha-two", "beta-one"])
    assert len(set(refs.values())) == 3
    assert len({len(ref) for ref in refs.values()}) == 1


def test_an_underivable_pair_falls_back_to_the_full_id_rather_than_colliding(client):
    long_a = "identical-prefix-segments-aaaaaaaaaaaa"
    long_b = "identical-prefix-segments-aaaaaaaaaaab"
    refs = short_refs([long_a, long_b])
    assert refs[long_a] != refs[long_b]
    assert refs[long_a] == long_a.upper()


def test_an_empty_or_partial_population_is_handled_without_inventing_a_token(client):
    assert short_refs([]) == {}
    assert short_refs([None, ""]) == {}
    assert short_refs(["x"]) == {"x": "X"}


def test_the_derivation_is_stable_for_the_same_input(client):
    ids = ["rrd-breadth-contacts-1", "rrd-breadth-contacts-2", "rrd-champ-named-1"]
    assert short_refs(ids) == short_refs(list(reversed(ids)))


# --- the payloads ------------------------------------------------------------------------------

def test_every_live_requirement_definition_reports_a_reference(client):
    body = client.get("/api/readiness/definitions").json()
    refs = []
    for pillar in body["pillars"]:
        for requirement in pillar["requirements"]:
            assert requirement.get("ref"), requirement["key"]
            refs.append(requirement["ref"])
    assert refs, "no requirement definitions to check"
    assert len(set(refs)) == len(refs), "two definitions share a reference"


def test_playbook_entries_report_a_reference(client):
    body = client.get("/api/readiness/playbooks").json()
    refs = [entry["ref"] for p in body["playbooks"] for entry in p["entries"]]
    assert refs, "no playbook entries to check"
    assert all(refs)
    assert len(set(refs)) == len(refs)


def test_the_same_definition_has_the_same_reference_on_every_surface(client):
    """A token that differed between the listing and the reading would be two names for one row,
    which is the failure this exists to prevent, arriving from the other direction."""
    account = _account(client)
    listing = {(r["key"], r["version"]): r["ref"]
               for p in client.get("/api/readiness/definitions").json()["pillars"]
               for r in p["requirements"]}
    readiness = client.get(f"/api/accounts/{account['id']}/readiness").json()
    checked = 0
    for component in _components(readiness):
        expected = listing.get((component["definition_key"], component["definition_version"]))
        if expected is None:
            continue
        assert component["ref"] == expected, component["definition_key"]
        checked += 1
    assert checked > 0, "no component matched a listed definition"


def test_the_plan_row_shows_the_same_reference_the_reading_does(client):
    account = _account(client)
    r = client.post("/api/programs", json={"account_id": account["id"], "name": "Region rollout",
                                           "phase": "programmatic"})
    assert r.status_code == 201, r.text
    program = r.json()
    r = client.post(f"/api/accounts/{account['id']}/plan-instances", json={
        "program_id": program["id"], "playbook_key": "enterprise-launch", "playbook_version": 1,
        "anchor_type": "kickoff", "anchor_date": "2026-07-01",
    })
    assert r.status_code in (200, 201), r.text

    plan = client.get(
        f"/api/accounts/{account['id']}/plan-instances?program_id={program['id']}").json()
    reading = {c["definition_key"]: c["ref"] for c in _components(
        client.get(f"/api/accounts/{account['id']}/readiness"
                   f"?program_id={program['id']}").json())}
    checked = 0
    for row in plan["requirements"]:
        if "ref" not in row:
            continue      # a legacy pinned version claims no reading, and so carries no token
        assert row["ref"] == reading.get(row["requirement_key"]), row["requirement_key"]
        checked += 1
    assert checked > 0, "no plan row carried a reference"


def test_the_reference_adds_no_column_and_no_table(client):
    """§7.4 says derived from the existing id, and means it: nothing stores this."""
    conn = sqlite3.connect(client.db_path)
    try:
        tables = [row[0] for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'")]
        offenders = []
        for table in tables:
            for row in conn.execute(f"PRAGMA table_info({table})"):
                if row[1] in ("ref", "short_ref", "reference_id"):
                    offenders.append(f"{table}.{row[1]}")
    finally:
        conn.close()
    assert not offenders, offenders
    assert not [t for t in tables if "short_ref" in t]
