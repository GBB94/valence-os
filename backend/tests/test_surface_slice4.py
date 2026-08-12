"""Stage 17 Slice 4 — triggers, screen weight, and the checklist telemetry cannot do (§6.4, §7.0, §8).

Three things are being defended here, and each one is a place where a number could start meaning
something it has not earned.

**A trigger decides coverage and nothing else.** §6.4 exists so an event-driven surface is not
permanently unobservable, and the temptation once a trigger count exists is to compare it with
`rendered` — "shown on 4 of the 4 occasions it mattered". That is a rate, it reads as a compliance
figure, and §12 forbids it. The tests below assert the count travels as its own field, that a
covered trigger changes only *which* of §6.3's four observations is reachable, and that no
combination of it with anything else has a name.

**Zero triggers, an unknown evaluator, and a broken query are three different facts.** Each keeps
its own sentence and each leaves the surface unobservable. The one that would do real damage is a
broken query silently reading as zero, because zero-with-coverage is the argument for removing
something.

**A screen-weight row never launders §6.2's refusal.** A section whose window does not cover it
cannot appear on a screen's never-operated list. One level up is exactly where a "not knowable"
would quietly become a "nobody wanted it".
"""
import os
import re
import sqlite3
import tempfile
from dataclasses import replace

import pytest
from fastapi.testclient import TestClient

from app import surface_triggers, surface_usage, surfaces

from conftest import utc_day


@pytest.fixture()
def client():
    fd, path = tempfile.mkstemp(suffix=".sqlite"); os.close(fd)
    os.environ["VALENCE_OS_DB"] = path
    os.environ["VALENCE_OS_WORKER"] = "0"
    os.environ.pop("VALENCE_OS_TELEMETRY_STRICT", None)
    from app.main import app
    with TestClient(app) as c:
        c.db_path = path
        yield c
    for suffix in ("", "-wal", "-shm"):
        try: os.unlink(path + suffix)
        except FileNotFoundError: pass


def _conn(c):
    conn = sqlite3.connect(c.db_path)
    conn.row_factory = sqlite3.Row
    return conn


def _exec(c, statement, params=()):
    conn = _conn(c)
    try:
        with conn:
            conn.execute(statement, params)
    finally:
        conn.close()


def _report(c, **params):
    response = c.get("/api/telemetry/surface-usage", params=params)
    assert response.status_code == 200, response.text
    return response.json()


def _row(report, key):
    return next(row for row in report["surfaces"] if row["surface"] == key)


def _measuring_since(c, days_ago):
    _exec(c, "UPDATE product_telemetry_settings SET measuring_since=? WHERE id='singleton'",
          (utc_day(-days_ago) + "T00:00:00+00:00",))


def _account(c):
    """A mock account for the trigger fixtures. The fixture database is migrated, not seeded."""
    conn = _conn(c)
    try:
        row = conn.execute("SELECT id FROM accounts LIMIT 1").fetchone()
        if row:
            return row["id"]
        stamp = utc_day() + "T00:00:00+00:00"
        with conn:
            conn.execute("INSERT INTO accounts (id, name, created_at, updated_at) VALUES (?,?,?,?)",
                         ("acc-slice4", "Placeholder Account", stamp, stamp))
        return "acc-slice4"
    finally:
        conn.close()


def _flag_org_changes(c, count, *, day_offset=-1):
    """Mock org-change flags, which is `people.org_changes`'s declared trigger."""
    account = _account(c)
    for index in range(count):
        _exec(c,
              "INSERT INTO org_change_flags (id, account_id, kind, status, summary, occurred_on, "
              "created_at, updated_at) VALUES (?,?,?,?,?,?,?,?)",
              (f"ocf-slice4-{index}", account, "departure", "confirmed",
               "Placeholder org change for a test", utc_day(day_offset),
               utc_day(day_offset) + "T00:00:00+00:00", utc_day(day_offset) + "T00:00:00+00:00"))


# --- §6.4 the trigger is a coverage rule, never a reading ---------------------------------------

def test_an_event_driven_surface_with_no_trigger_stays_unobservable_forever(client):
    """§6.4's honest case. `global.copilot` is summoned by a question in the operator's head.

    There is no domain fact for that, so the surface says so and is never read as unused. A build
    that quietly gave it a trigger to make the report tidier would be inventing the evidence.
    """
    copilot = replace(surfaces.BY_KEY["global.copilot"], instrumented=True)
    observation, notice = surface_usage._observe(
        copilot, rendered=0, engaged=0, observed_days=400)
    assert observation == "insufficient_window"
    assert copilot.trigger is None
    assert "no trigger count is available" in notice


def test_a_scheduled_surface_never_carries_a_trigger():
    """Two coverage answers for one surface would force the report to pick between them."""
    for surface in surfaces.REGISTRY:
        if surfaces.window_days(surface.cadence) is not None:
            assert surface.trigger is None, surface.key
    with pytest.raises(ValueError, match="second answer to the same question"):
        surfaces._validate((surfaces.Surface(
            key="x.y", label="X", route="today", kind="section", cadence="weekly",
            added_on=utc_day(), reaches=("account",), trigger="renewal_approaching"),))


def test_a_zero_trigger_count_is_not_disuse(client):
    """The condition never arose, so nothing is knowable. Never `not_rendered`."""
    _measuring_since(client, 400)
    row = _row(_report(client), "people.org_changes")
    assert row["trigger_count"] == 0
    assert row["observation"] == "insufficient_window"
    assert "was never true in this window" in row["notice"]
    # The sentence names the condition, so the operator can check the claim against the data.
    assert "an org change was flagged" in row["notice"]


def test_one_occurrence_is_not_enough_and_says_how_many_there_were(client):
    """§6.2's threshold, shared. One occurrence you happened to miss looks like a dead surface."""
    _measuring_since(client, 400)
    _flag_org_changes(client, 1)
    row = _row(_report(client), "people.org_changes")
    assert row["trigger_count"] == 1
    assert row["observation"] == "insufficient_window"
    assert "was true 1 time" in row["notice"] and "2 are needed" in row["notice"]


def test_a_covered_trigger_makes_the_ordinary_three_readings_reachable(client):
    """§6.4's worked example: condition true 4 times, rendered 4, engaged 0 → the clutter case."""
    _measuring_since(client, 400)
    _flag_org_changes(client, 4)
    for _ in range(4):
        client.post("/api/telemetry/events",
                    json={"event_name": "surface_rendered",
                          "properties": {"surface": "people.org_changes",
                                         "route": "account.people", "kind": "section"}})
    row = _row(_report(client), "people.org_changes")
    assert row["trigger_count"] == 4
    assert row["rendered"] == 4
    assert row["engaged"] == 0
    assert row["observation"] == "rendered_not_engaged"
    assert row["window_covered"] is True
    assert row["notice"] is None


def test_the_three_counts_travel_separately_and_are_never_divided(client):
    """A rate of any two of them would read as a compliance figure and say nothing about value."""
    _measuring_since(client, 400)
    _flag_org_changes(client, 4)
    row = _row(_report(client), "people.org_changes")
    for forbidden in ("trigger_rate", "trigger_ratio", "coverage_rate", "engagement_rate",
                      "rendered_per_trigger", "trigger_share"):
        assert forbidden not in row
    assert isinstance(row["trigger_count"], int)
    assert isinstance(row["rendered"], int)
    assert isinstance(row["engaged"], int)


def test_an_unrecognised_evaluator_fails_closed_and_names_itself():
    """A registry row selects an evaluator and can never define one (the D-139 rule, sideways)."""
    surface = surfaces.Surface(key="x.y", label="Ghost panel", route="today", kind="section",
                               cadence="event_driven", added_on=utc_day(),
                               reaches=("account",), trigger="whatever_you_like")
    reading = surface_triggers.evaluate(sqlite3.connect(":memory:"), surface,
                                        utc_day(-30), utc_day())
    assert reading["available"] is False
    assert reading["count"] is None
    assert "whatever_you_like" in reading["reason"]
    assert "does not recognise" in reading["reason"]


def test_a_broken_query_is_not_a_zero():
    """A missing table must not become the argument for removing the surface that reads it."""
    surface = next(s for s in surfaces.REGISTRY if s.trigger)
    reading = surface_triggers.evaluate(sqlite3.connect(":memory:"), surface,
                                        utc_day(-30), utc_day())
    assert reading["available"] is False
    assert reading["count"] is None
    assert "could not be counted" in reading["reason"]
    assert surface.label in reading["reason"]


def test_every_registered_trigger_resolves_to_an_allowlisted_evaluator():
    """The gate for the guard above: a registry that outlived its evaluator is a build error.

    Asserted in a test rather than at import, because the fail-closed path has to keep working —
    it is the state a stale registry is actually in, and validating at import would delete it.
    """
    unknown = sorted(s.key for s in surfaces.REGISTRY
                     if s.trigger and s.trigger not in surface_triggers.EVALUATORS)
    assert not unknown, f"surfaces naming an evaluator that does not exist: {unknown}"


def test_every_evaluator_is_reachable_from_the_registry():
    """The other direction. An evaluator nothing selects is untested SQL nobody will notice rot."""
    selected = {s.trigger for s in surfaces.REGISTRY if s.trigger}
    orphans = sorted(set(surface_triggers.EVALUATORS) - selected)
    assert not orphans, f"evaluators no surface selects: {orphans}"


def test_every_evaluator_runs_against_the_real_schema(client):
    """Each one is executed, so a renamed column fails here rather than as a silent refusal."""
    conn = _conn(client)
    try:
        for name, (evaluator, _condition) in surface_triggers.EVALUATORS.items():
            count = evaluator(conn, utc_day(-400), utc_day())
            assert isinstance(count, int) and count >= 0, name
    finally:
        conn.close()


def test_the_trigger_evaluators_read_dates_and_statuses_only():
    """§17.1 and the standing people rule. No evaluator may select a person or any free text."""
    source = (surface_triggers.__file__)
    text = open(source, encoding="utf-8").read()
    body = text.split('"""', 2)[-1]
    for forbidden in ("person_id", "persons", "raw_notes", "summary,", "SELECT *", "email"):
        assert forbidden not in body, forbidden
    # Every evaluator is a COUNT. Selecting rows would let record content reach the report.
    assert body.count("SELECT COUNT(*)") == len(surface_triggers.EVALUATORS)


# --- §8 screen weight ----------------------------------------------------------------------------

def test_screens_are_grouped_by_route_in_navigation_order(client):
    report = _report(client)
    routes = [screen["route"] for screen in report["screens"]]
    assert routes == list(surfaces.ROUTES)
    # Never alphabetical: sorting screens would read as a ranking of screens, which it is not.
    assert routes != sorted(routes)


def test_every_registered_section_is_counted_on_exactly_one_screen(client):
    report = _report(client)
    counted = sum(screen["sections"] for screen in report["screens"])
    assert counted == len(report["surfaces"]) == len(surfaces.SURFACE_KEYS)


def test_a_screen_row_holds_independent_counters_and_no_ratio(client):
    report = _report(client)
    for screen in report["screens"]:
        assert set(screen) == {"route", "sections", "sections_rendered", "sections_engaged",
                               "sections_not_yet_knowable", "never_engaged"}
        for key in screen:
            assert not re.search(r"rate|ratio|percent|score|share|index", key), key
        assert (screen["sections_rendered"] <= screen["sections"]
                and screen["sections_engaged"] <= screen["sections"])


def test_a_section_whose_window_does_not_cover_it_is_never_on_the_never_operated_list(client):
    """§6.2's refusal must not be laundered into a layout finding one level up."""
    report = _report(client)
    unknowable = {row["surface"] for row in report["surfaces"]
                  if row["observation"] == "insufficient_window"}
    assert unknowable, "the fixture is meant to have uncovered surfaces"
    for screen in report["screens"]:
        listed = {entry["surface"] for entry in screen["never_engaged"]}
        assert not (listed & unknowable), screen["route"]
        assert screen["sections_not_yet_knowable"] > 0 or not (
            set(surfaces.SURFACE_KEYS) & unknowable & {
                row["surface"] for row in report["surfaces"] if row["route"] == screen["route"]})


def test_a_screen_with_a_covered_engaged_section_reports_it(client):
    _measuring_since(client, 400)
    client.post("/api/telemetry/events",
                json={"event_name": "surface_rendered",
                      "properties": {"surface": "today.queue", "route": "today",
                                     "kind": "section"}})
    client.post("/api/telemetry/events",
                json={"event_name": "surface_engaged",
                      "properties": {"surface": "today.queue", "route": "today",
                                     "kind": "section", "engagement": "opened"}})
    screen = next(s for s in _report(client)["screens"] if s["route"] == "today")
    assert screen["sections_engaged"] == 1
    assert screen["sections_rendered"] == 1
    assert "today.queue" not in {entry["surface"] for entry in screen["never_engaged"]}


def test_the_screen_weight_caveat_names_the_position_confound(client):
    """§9.2. A never-operated section that sits last on its screen is a layout finding."""
    caveat = _report(client)["screen_weight_caveat"]
    assert "layout finding" in caveat
    assert "below everything else" in caveat
    assert "not a section nobody wanted" in caveat


# --- §7.0 the checklist telemetry cannot do -------------------------------------------------------

def _checklist(c):
    response = c.get("/api/telemetry/surface-usage/redundancy")
    assert response.status_code == 200, response.text
    return response.json()


def test_the_checklist_states_the_honest_limit_before_anything_else(client):
    """§7.0's risk is that the report becomes the only place simplification is thought about."""
    limit = _checklist(client)["honest_limit"]
    assert "Telemetry finds clutter" in limit
    assert "blind to redundancy" in limit
    assert "does not reduce the number of concepts" in limit


def test_the_checklist_lists_every_surface_reaching_each_record_type(client):
    checklist = _checklist(client)
    interaction = next(item for item in checklist["record_types"]
                       if item["record_type"] == "interaction")
    expected = sorted(s.key for s in surfaces.REGISTRY if "interaction" in s.reaches)
    assert sorted(entry["surface"] for entry in interaction["surfaces"]) == expected
    assert interaction["count"] == len(expected)
    assert interaction["ask_why"] is (len(expected) >= 3)


def test_the_checklist_asks_rather_than_answers(client):
    """Nothing here is a defect, nothing is actionable by the app, and there is no threshold to tune.

    A `severity`, a `recommendation`, or a `duplicate` flag would turn twenty minutes of judgment
    into a queue item the app appears to have already decided.
    """
    checklist = _checklist(client)
    assert checklist["threshold"] == 3
    assert "once a quarter" in checklist["cadence"]
    for item in checklist["record_types"]:
        assert set(item) == {"record_type", "surfaces", "count", "ask_why"}
        for key in item:
            assert not re.search(r"score|severity|recommend|duplicate|redundant", key), key


def test_a_retired_surface_stops_counting_as_a_duplicate_route(client):
    """Otherwise the checklist keeps asking about a screen that is no longer offered."""
    before = _checklist(client)
    target = next(s for s in surfaces.REGISTRY
                  if s.kind == "section" and "interaction" in s.reaches
                  and s.key != "ledger.records")
    response = client.post("/api/telemetry/surface-retirement/apply", json={"staged": [
        {"surface": target.key, "cause_code": "superseded", "action": "retire"}]})
    assert response.status_code == 200, response.text
    after = _checklist(client)

    def count_of(payload):
        return next(item["count"] for item in payload["record_types"]
                    if item["record_type"] == "interaction")

    assert count_of(after) == count_of(before) - 1


def test_a_collapsed_surface_still_counts_as_a_route(client):
    """Collapse hides a surface; it does not stop it answering the question it answers."""
    before = _checklist(client)
    response = client.post("/api/telemetry/surface-retirement/apply", json={"staged": [
        {"surface": "ledger.communications", "cause_code": "not_needed", "action": "collapse"}]})
    assert response.status_code == 200, response.text
    after = _checklist(client)
    assert after["record_types"] == before["record_types"]


def test_the_checklist_stores_nothing(client):
    """It is a read over the registry. A table here would be a fifth thing to keep in step."""
    conn = _conn(client)
    try:
        _checklist(client)
        tables = {row["name"] for row in
                  conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
    finally:
        conn.close()
    assert not {t for t in tables if "redundan" in t or "checklist_surface" in t}


# --- §11 instrumentation drift, at Slice 4's size -------------------------------------------------

def test_every_route_the_app_navigates_to_has_at_least_one_registered_surface():
    """Slice 4's completeness claim, made checkable. A screen with no registered surface is a screen
    the report cannot see at all, and its silence would be indistinguishable from disuse."""
    navigable = {"today", "accounts", "library", "operations", "global",
                 "account.overview", "account.ledger", "account.people", "account.plan",
                 "account.commercial", "account.evidence", "account.outputs", "account.internal"}
    missing = sorted(navigable - set(surfaces.ROUTES))
    assert not missing, f"routes with no registered surface: {missing}"


def test_incomplete_engagement_coverage_is_always_explained():
    """Exposure-only wrappers must refuse interpretation rather than impersonating disuse."""
    excused = [s.key for s in surfaces.REGISTRY if s.instrumented is not True]
    assert excused, "remove this only when every surface has semantic engagement"
    assert all(isinstance(s.instrumented, str) and "engagement" in s.instrumented
               for s in surfaces.REGISTRY if s.instrumented is not True)


def test_no_rate_or_score_name_entered_the_report_with_slice_4(client):
    """§6's rule, re-asserted over the two new blocks rather than trusted to stay true."""
    report = _report(client)
    payload = str(report)
    for forbidden in ("usage_score", "surface_score", "usage_index", "surface_rating",
                      "surface_health", "engagement_score", "usage_rate"):
        assert forbidden not in payload, forbidden


def test_the_report_still_names_its_caveat_beside_the_new_numbers(client):
    report = _report(client)
    assert "cannot say whether a surface is valuable" in report["caveat"]
    assert report["screen_weight_caveat"]
    assert surface_usage.CAVEAT in report["caveat"]
