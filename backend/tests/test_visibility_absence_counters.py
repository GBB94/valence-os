"""Acceptance tests for VISIBILITY-SPEC.md Slice 2 — portfolio absence counters.

The counters answer "where am I not looking", so the failure that matters is a number that does not
match the list it links to: an operator opens the list, finds a different set, and stops trusting
the strip. These tests hold the count and the list to the same query, then try to get the two to
disagree by archiving records mid-window and by retracting evidence.
"""
import os
import sqlite3
import tempfile
from datetime import date, timedelta

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


def _absence(c, days=None):
    params = {} if days is None else {"days": days}
    response = c.get("/api/portfolio/absence", params=params)
    assert response.status_code == 200, response.text
    return response.json()


def _counter(payload, key):
    return next(c for c in payload["counters"] if c["key"] == key)


def _account(c, name):
    return c.post("/api/accounts", json={"name": name}).json()


def _interaction(c, account_id, *, days_ago, program_id=None, meaningful=True):
    return c.post("/api/interactions", json={
        "account_id": account_id, "program_id": program_id, "occurred_on": utc_day(-days_ago),
        "type": "meeting", "summary": "Working session", "meaningful_touch": meaningful}).json()


# --- the number and the list are the same query -------------------------------------------------

def test_every_count_equals_the_length_of_the_list_it_links_to(client):
    """A count an operator cannot reconcile against its own list is worse than no count."""
    quiet = _account(client, "Northwind Synthetic")
    recent = _account(client, "Umbra Fictional")
    _interaction(client, recent["id"], days_ago=2)
    _interaction(client, quiet["id"], days_ago=90)
    payload = _absence(client)
    for counter in payload["counters"]:
        assert counter["count"] == len(counter["records"]), counter["key"]
    interaction_counter = _counter(payload, "accounts_without_interaction")
    assert [r["id"] for r in interaction_counter["records"]] == [quiet["id"]]


def test_the_four_counters_are_independent_and_carry_no_composite(client):
    """No coverage score, no percentage, no total. §4.2 rule 2, asserted over the response shape."""
    _account(client, "Northwind Synthetic")
    payload = _absence(client)
    assert {c["key"] for c in payload["counters"]} == {
        "accounts_without_interaction", "accounts_without_assessment",
        "accounts_without_readiness_evidence", "programs_without_touch"}
    forbidden = ("score", "percent", "percentage", "grade", "coverage_score", "total", "overall",
                 "health", "ratio")
    flat = str(payload).lower()
    for word in forbidden:
        assert f'"{word}"' not in flat and f"'{word}'" not in flat, f"{word} would be a composite"
    for counter in payload["counters"]:
        assert set(counter) == {"key", "count", "record_kind", "records", "sentence"}


# --- the window is a parameter, stated in the sentence ------------------------------------------

def test_changing_the_window_changes_both_the_number_and_the_sentence(client):
    account = _account(client, "Northwind Synthetic")
    _interaction(client, account["id"], days_ago=20)
    narrow = _counter(_absence(client, days=7), "accounts_without_interaction")
    wide = _counter(_absence(client, days=60), "accounts_without_interaction")
    # 20 days ago is outside a 7-day window and inside a 60-day one.
    assert narrow["count"] == 1 and wide["count"] == 0
    assert "in 7 days" in narrow["sentence"]
    assert "in 60 days" in wide["sentence"]
    assert narrow["sentence"] == "1 account with no recorded interaction in 7 days"
    # Zero is rendered as zero, plainly, in the same frame (§4.2 rule 6).
    assert wide["sentence"] == "0 accounts with no recorded interaction in 60 days"


def test_the_default_window_is_stated_rather_than_silent(client):
    payload = _absence(client)
    assert payload["window"]["days"] == 30
    assert payload["window"]["default_days"] == 30
    expected = (date.fromisoformat(utc_day()) - timedelta(days=30)).isoformat()
    assert payload["window"]["since"] == expected


def test_an_out_of_range_window_is_refused_rather_than_clamped(client):
    """Clamping would answer a different question than the one asked, silently."""
    for days in (0, -5, 400):
        assert client.get("/api/portfolio/absence", params={"days": days}).status_code == 422


# --- archival and retraction, consistently ------------------------------------------------------

def test_an_account_archived_mid_window_leaves_both_the_count_and_the_list(client):
    account = _account(client, "Northwind Synthetic")
    before = _counter(_absence(client), "accounts_without_interaction")
    assert account["id"] in [r["id"] for r in before["records"]]
    assert client.post(f"/api/accounts/{account['id']}/archive").status_code == 204
    after = _counter(_absence(client), "accounts_without_interaction")
    assert account["id"] not in [r["id"] for r in after["records"]]
    assert after["count"] == before["count"] - 1
    assert after["count"] == len(after["records"])


def _archive_interaction(c, interaction_id):
    """Soft-delete an interaction directly. There is no archive route for one, and adding a write
    endpoint to satisfy a read test would be the tail wagging the dog."""
    conn = sqlite3.connect(c.db_path)
    try:
        with conn:
            conn.execute("UPDATE interactions SET archived=1 WHERE id=?", (interaction_id,))
    finally:
        conn.close()


def test_an_archived_interaction_stops_counting_as_contact(client):
    """The counter is over live records; a deleted note is not a note we have."""
    account = _account(client, "Northwind Synthetic")
    interaction = _interaction(client, account["id"], days_ago=2)
    assert _counter(_absence(client), "accounts_without_interaction")["count"] == 0
    _archive_interaction(client, interaction["id"])
    assert _counter(_absence(client), "accounts_without_interaction")["count"] == 1


# --- interaction and touch are different words on purpose ---------------------------------------

def test_a_program_counter_asks_for_a_meaningful_touch_not_any_interaction(client):
    account = _account(client, "Northwind Synthetic")
    program = client.post("/api/programs", json={
        "account_id": account["id"], "name": "Europe", "phase": "launch"}).json()
    _interaction(client, account["id"], days_ago=2, program_id=program["id"], meaningful=False)
    # The account has a recorded interaction; the program has no recorded touch. Both are true and
    # the two counters must say so independently.
    payload = _absence(client)
    assert _counter(payload, "accounts_without_interaction")["count"] == 0
    programs = _counter(payload, "programs_without_touch")
    assert [r["id"] for r in programs["records"]] == [program["id"]]
    assert programs["records"][0]["account_name"] == "Northwind Synthetic"


def test_a_closed_program_is_not_counted_as_uncovered(client):
    account = _account(client, "Northwind Synthetic")
    client.post("/api/programs", json={
        "account_id": account["id"], "name": "Wound down", "phase": "closed"})
    assert _counter(_absence(client), "programs_without_touch")["count"] == 0


def test_a_program_on_an_archived_account_is_excluded(client):
    account = _account(client, "Northwind Synthetic")
    client.post("/api/programs", json={"account_id": account["id"], "name": "Europe"})
    assert _counter(_absence(client), "programs_without_touch")["count"] == 1
    client.post(f"/api/accounts/{account['id']}/archive")
    assert _counter(_absence(client), "programs_without_touch")["count"] == 0


# --- a dated assessment is what counts, not the row ---------------------------------------------

def test_an_undated_stakeholder_row_does_not_count_as_an_assessment(client):
    """A role with no stance carries no `stance_assessed_on`; it is a directory entry, not a judgment."""
    account = _account(client, "Northwind Synthetic")
    program = client.post("/api/programs", json={
        "account_id": account["id"], "name": "Europe"}).json()
    person = client.post("/api/persons", json={
        "name": "Jordan Lee", "account_id": account["id"]}).json()
    undated = client.post("/api/stakeholder-roles", json={
        "program_id": program["id"], "person_id": person["id"], "role": "champion"})
    assert undated.status_code in (200, 201), undated.text
    assert _counter(_absence(client), "accounts_without_assessment")["count"] == 1
    dated = client.post("/api/stakeholder-roles", json={
        "program_id": program["id"], "person_id": person["id"], "role": "budget_owner",
        "stance": "supporter", "stance_assessed_on": utc_day(-3),
        "stance_evidence_note": "Said so on the steering call."})
    assert dated.status_code in (200, 201), dated.text
    assert _counter(_absence(client), "accounts_without_assessment")["count"] == 0


def test_an_assessment_older_than_the_window_does_not_count(client):
    account = _account(client, "Northwind Synthetic")
    program = client.post("/api/programs", json={
        "account_id": account["id"], "name": "Europe"}).json()
    person = client.post("/api/persons", json={
        "name": "Jordan Lee", "account_id": account["id"]}).json()
    client.post("/api/stakeholder-roles", json={
        "program_id": program["id"], "person_id": person["id"], "role": "champion",
        "stance": "supporter", "stance_assessed_on": utc_day(-120),
        "stance_evidence_note": "Said so on the steering call."})
    assert _counter(_absence(client), "accounts_without_assessment")["count"] == 1
    assert _counter(_absence(client, days=200), "accounts_without_assessment")["count"] == 0


# --- nothing is stored --------------------------------------------------------------------------

def test_this_slice_adds_no_table_and_no_column(client):
    """§4.3. The counters are `NOT EXISTS` reads; a stored count is a number that can go stale."""
    _absence(client)
    conn = sqlite3.connect(client.db_path)
    try:
        tables = {row[0] for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
        account_columns = {row[1] for row in conn.execute("PRAGMA table_info(accounts)")}
        program_columns = {row[1] for row in conn.execute("PRAGMA table_info(programs)")}
    finally:
        conn.close()
    assert not [t for t in tables if "absence" in t or "coverage_count" in t]
    for forbidden in ("absence", "uncovered", "last_looked_at", "coverage_score", "days_quiet"):
        assert forbidden not in account_columns
        assert forbidden not in program_columns
