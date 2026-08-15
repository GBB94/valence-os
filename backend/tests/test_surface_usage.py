"""Stage 17 Slice 2 — the rollup, the window that can refuse, and the four observations.

These are written to try to make the report say something it has no basis for: to get a covered
reading out of a two-week-old installation, to make a zero look like disuse when it is a gap in
instrumentation, to make a dismissal count as engagement, and to make the rollup outlive the off
switch. Each test asserts the honest answer, which is usually a refusal with a stated reason.
"""
import os
import re
import sqlite3
import tempfile
from dataclasses import replace
from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient

from app import surface_usage, surfaces

from conftest import utc_day


def _today():
    """`conftest.utc_day` as a date. Every row the app writes is stamped in UTC, so a fixture built
    from the local calendar day is one behind for the hours the two disagree — see `conftest`."""
    return date.fromisoformat(utc_day())


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


def _sql(c, statement, params=()):
    conn = _conn(c)
    try:
        with conn:
            return [dict(r) for r in conn.execute(statement, params).fetchall()]
    finally:
        conn.close()


def _emit(c, event_name, surface, *, when=None, **extra):
    meta = surfaces.BY_KEY[surface]
    properties = {"surface": surface, "route": meta.route, **extra}
    if event_name == "surface_rendered":
        properties.setdefault("kind", meta.kind)
        properties.setdefault("render_reason", "navigation")
    elif event_name == "surface_engaged":
        properties.setdefault("kind", meta.kind)
        properties.setdefault("engagement", "opened")
    payload = {"event_name": event_name, "properties": properties, "session_id": "local-abc12345"}
    if when:
        payload["occurred_at"] = when
    return c.post("/api/telemetry/events", json=payload)


def _measuring_since(c, days_ago):
    """Backdate the observation start so a covered window is reachable inside a test."""
    stamp = (_today() - timedelta(days=days_ago)).isoformat() + "T00:00:00+00:00"
    conn = _conn(c)
    try:
        with conn:
            conn.execute("UPDATE product_telemetry_settings SET measuring_since=? "
                         "WHERE id='singleton'", (stamp,))
    finally:
        conn.close()


def _report(c, **params):
    response = c.get("/api/telemetry/surface-usage", params=params)
    assert response.status_code == 200, response.text
    return response.json()


def _row(report, key):
    return next(r for r in report["surfaces"] if r["surface"] == key)


# --- §10 the schema stores counts and never a state ---------------------------------------------

def test_the_rollup_carries_no_state_no_account_and_no_score(client):
    """The introspection assertion migrations 0042, 0046, and 0050 each make in their own terms.

    A `state` here would be a stored answer to the question §6 computes, and the two would disagree
    the first time the window changed. A `score` would be the composite the whole spec refuses.
    """
    columns = {row["name"] for row in _sql(client, "PRAGMA table_info(surface_usage_months)")}
    assert columns == {"id", "surface_key", "month", "rendered", "engaged", "last_engaged_on",
                       "updated_at"}
    for forbidden in ("state", "status", "observation", "score", "rating", "health",
                      "usage_index", "account_id", "session_id", "properties_json"):
        assert forbidden not in columns


def test_no_column_or_response_field_in_this_feature_is_named_score(client):
    """§6.1's assertion, run over the schema and over an actual response body."""
    forbidden = re.compile(r"(?<![a-z_])(score|rating|health|usage_index)(?![a-z_])")
    columns = " ".join(row["name"] for row in _sql(client, "PRAGMA table_info(surface_usage_months)"))
    assert not forbidden.search(columns)
    report = _report(client)
    fields = set()
    for row in report["surfaces"]:
        fields.update(row)
    fields.update(report)
    fields.update(report["totals"])
    fields.update(report["window"])
    assert not [f for f in fields if forbidden.search(f)]


# --- §9.4 the fold ------------------------------------------------------------------------------

def test_the_fold_summarises_and_carries_strictly_less_than_the_rows_it_summarises(client):
    """The whole justification for a 36-month life: no session, no account, no properties."""
    _emit(client, "surface_rendered", "today.queue")
    _emit(client, "surface_rendered", "today.queue")
    _emit(client, "surface_engaged", "today.queue")
    client.post("/api/telemetry/surface-usage/fold")

    rows = _sql(client, "SELECT * FROM surface_usage_months")
    assert len(rows) == 1
    assert rows[0]["surface_key"] == "today.queue"
    assert rows[0]["rendered"] == 2
    assert rows[0]["engaged"] == 1
    assert rows[0]["month"] == _today().isoformat()[:7]
    assert rows[0]["last_engaged_on"] == _today().isoformat()


def test_folding_twice_does_not_double_count(client):
    """The write path already folded this one, which is the point — so both explicit passes are
    repeats, and a repeat that added anything would be the double count."""
    _emit(client, "surface_rendered", "today.queue")
    first = client.post("/api/telemetry/surface-usage/fold").json()
    second = client.post("/api/telemetry/surface-usage/fold").json()
    assert first["folded"] == 0
    assert second["folded"] == 0
    assert _sql(client, "SELECT rendered FROM surface_usage_months")[0]["rendered"] == 1


def test_the_fold_is_monotone_so_a_raw_purge_cannot_lower_a_month(client):
    """The reason the fold advances a watermark instead of recomputing over the raw window.

    A recompute would quietly shrink a month as it aged past the 90-day purge, and the number an
    operator wrote a retirement note against would stop matching the table it came from.
    """
    _emit(client, "surface_rendered", "today.queue")
    _emit(client, "surface_rendered", "today.queue")
    client.post("/api/telemetry/surface-usage/fold")
    conn = _conn(client)
    try:
        with conn:
            conn.execute("DELETE FROM product_events")
    finally:
        conn.close()
    client.post("/api/telemetry/surface-usage/fold")
    assert _sql(client, "SELECT rendered FROM surface_usage_months")[0]["rendered"] == 2


def test_more_renders_land_on_an_already_folded_month_with_no_engagement_in_either(client):
    """The commonest fold there is, and it aborted the whole batch.

    A month row with no engagement stores `last_engaged_on` NULL. Adding to it took a MAX over two
    coalesced empty strings, and `''` fails the column's CHECK — *inside* the upsert, so the
    normalising pass that was meant to catch it never ran. Every render after the first fold of a
    month with no engagement in it was lost, which is to say: a surface that is looked at and never
    operated, which is precisely the surface the retirement evidence is about.
    """
    _emit(client, "surface_rendered", "today.queue")
    client.post("/api/telemetry/surface-usage/fold")
    _emit(client, "surface_rendered", "today.queue")
    _emit(client, "surface_rendered", "today.queue")
    response = client.post("/api/telemetry/surface-usage/fold")
    assert response.status_code == 200, response.text

    row = _sql(client, "SELECT rendered, engaged, last_engaged_on FROM surface_usage_months")[0]
    assert row["rendered"] == 3
    assert row["engaged"] == 0
    # One representation of "never". An empty string here would be a second one, and the CHECK
    # exists to keep every reader from having to know about both.
    assert row["last_engaged_on"] is None


def test_a_raw_event_is_never_purged_before_it_has_been_folded(client):
    """Retention ran on every write; the rollup only advanced on a report read.

    So an installation nobody opened the usage report in for a quarter deleted raw events that had
    never reached `surface_usage_months` — and because that rollup is monotone and never
    recomputed, the counts were not stale but gone, with nothing anywhere saying so.
    """
    from app import telemetry
    _emit(client, "surface_rendered", "today.queue")
    _emit(client, "surface_engaged", "today.queue")

    conn = _conn(client)
    try:
        # Age every raw event past any retention window, then purge with the rollup already caught
        # up — which is what the write path now guarantees.
        with conn:
            conn.execute("UPDATE product_events SET occurred_at='2019-01-01T00:00:00+00:00'")
        assert telemetry.purge_expired(conn, retention_days=1) == 2
        assert conn.execute("SELECT COUNT(*) FROM product_events").fetchone()[0] == 0
    finally:
        conn.close()

    row = _sql(client, "SELECT rendered, engaged FROM surface_usage_months")[0]
    assert row["rendered"] == 1 and row["engaged"] == 1


def test_an_unfolded_surface_event_survives_a_purge_whose_fold_failed(client, monkeypatch):
    """The clause, not the call order. Fold first is the normal path; the delete has to hold on its
    own when that fold raises, or the guarantee is only as good as the statement above it.

    The other fourteen event names reach no rollup, so gating them on a mark they never advance
    would keep them past their retention for nothing. They go on time, in the same statement.
    """
    from app import surface_usage as su, telemetry
    _emit(client, "surface_rendered", "today.queue")
    client.post("/api/telemetry/events", json={
        "event_name": "account_path_viewed", "session_id": "local-abc12345",
        "properties": {"has_next_move": "yes", "coverage_status": "complete"}})

    conn = _conn(client)
    try:
        with conn:
            conn.execute("UPDATE product_events SET occurred_at='2019-01-01T00:00:00+00:00'")
            # The state a failed fold leaves behind: rows above the mark, none of them read.
            conn.execute("UPDATE product_telemetry_settings SET surface_rollup_watermark=0")

        def explode(_conn):
            raise sqlite3.OperationalError("database is locked")
        monkeypatch.setattr(su, "fold", explode)

        # One deletion, not two: the expired `account_path_viewed` goes, the unfolded
        # `surface_rendered` stays. Nothing was lost that the rollup had not already recorded.
        assert telemetry.purge_expired(conn, retention_days=1) == 1
        remaining = [r[0] for r in conn.execute("SELECT event_name FROM product_events")]
        assert remaining == ["surface_rendered"]
    finally:
        conn.close()


def test_the_watermark_means_every_row_up_to_here_was_offered_to_the_fold(client):
    """Not "the last row the fold used". Fourteen of the sixteen names are read in neither column,
    so under the older reading the mark sat behind a run of them and the purge could not use it."""
    _emit(client, "surface_rendered", "today.queue")
    for _ in range(2):
        client.post("/api/telemetry/events", json={
            "event_name": "account_path_viewed", "session_id": "local-abc12345",
            "properties": {"has_next_move": "yes", "coverage_status": "complete"}})
    client.post("/api/telemetry/surface-usage/fold")

    conn = _conn(client)
    try:
        mark = conn.execute("SELECT surface_rollup_watermark FROM product_telemetry_settings"
                            " WHERE id='singleton'").fetchone()[0]
        highest = conn.execute("SELECT MAX(rowid) FROM product_events").fetchone()[0]
    finally:
        conn.close()
    assert mark == highest


def test_a_dismissal_is_not_folded_into_engagement(client):
    """D-287. A dismissal reinforces the clutter case; counting it as use would invert the reading."""
    _emit(client, "surface_rendered", "today.queue")
    _emit(client, "surface_dismissed", "today.queue", dismiss_kind="collapsed")
    client.post("/api/telemetry/surface-usage/fold")
    row = _sql(client, "SELECT rendered, engaged, last_engaged_on FROM surface_usage_months")[0]
    assert row["rendered"] == 1
    assert row["engaged"] == 0
    assert row["last_engaged_on"] is None


def test_the_rollup_dies_with_the_off_switch(client):
    """§9.4. A rollup that survived would make 'measurement is disabled' and 'there is measurement
    data' both true at once — which is the whole loophole the off switch exists to close."""
    _emit(client, "surface_rendered", "today.queue")
    client.post("/api/telemetry/surface-usage/fold")
    assert _sql(client, "SELECT COUNT(*) c FROM surface_usage_months")[0]["c"] == 1

    client.patch("/api/telemetry/settings", json={"enabled": False})
    assert _sql(client, "SELECT COUNT(*) c FROM surface_usage_months")[0]["c"] == 0
    assert _sql(client, "SELECT COUNT(*) c FROM product_events")[0]["c"] == 0
    settings = _sql(client, "SELECT surface_rollup_watermark w, measuring_since m "
                            "FROM product_telemetry_settings")[0]
    assert settings["w"] == 0
    # The observation period restarts too. Carrying the old start forward would claim a long window
    # over data that no longer exists — a covered reading with nothing behind it.
    assert settings["m"] is None


def test_turning_measurement_back_on_starts_a_new_observation_period(client):
    client.patch("/api/telemetry/settings", json={"enabled": False})
    client.patch("/api/telemetry/settings", json={"enabled": True})
    since = _sql(client, "SELECT measuring_since m FROM product_telemetry_settings")[0]["m"]
    assert since is not None
    assert _report(client)["window"]["measuring_since"] == since[:10]


def test_the_rollup_retention_is_thirty_six_months_and_purges_whole_months(client):
    conn = _conn(client)
    try:
        with conn:
            conn.execute(
                "INSERT INTO surface_usage_months (id,surface_key,month,rendered,engaged,updated_at)"
                " VALUES ('old','today.queue','2019-01',5,1,'2019-01-31T00:00:00+00:00')")
        assert surface_usage.purge_expired_rollups(conn) == 1
    finally:
        conn.close()
    assert _sql(client, "SELECT COUNT(*) c FROM surface_usage_months")[0]["c"] == 0


# --- §6.2 window coverage -----------------------------------------------------------------------

def test_a_fresh_installation_claims_nothing_about_any_surface(client):
    """The most important single behaviour here. On day one everything is unknowable, not unused."""
    report = _report(client)
    assert report["window"]["observed_days"] == 0
    assert {row["observation"] for row in report["surfaces"]} == {"insufficient_window"}
    assert report["totals"]["not_rendered"] == 0
    assert report["totals"]["insufficient_window"] == report["totals"]["surfaces"]


def test_the_insufficient_window_sentence_names_both_numbers(client):
    """§6.2's wording, server-authored so a view cannot soften it, and checkable because it says
    how long it observed *and* how long it would need."""
    _measuring_since(client, 34)
    # Operations measurement is currently exposure-only, so its instrumentation refusal correctly
    # wins in the real report. Exercise the cadence branch with that one variable made complete.
    monthly = replace(surfaces.BY_KEY["operations.measurement"], instrumented=True)
    observation, notice = surface_usage._observe(
        monthly, rendered=0, engaged=0, observed_days=34)
    assert observation == "insufficient_window"
    assert notice == (
        "Observed for 34 days; a monthly surface needs 90 before this says anything.")


def test_a_window_covering_one_cadence_can_still_refuse_another(client):
    """The four axes are per-surface. A 30-day window covers a weekly surface and not a monthly one,
    and the report must say so per row rather than pick one verdict for the page."""
    _measuring_since(client, 30)
    report = _report(client)
    assert _row(report, "today.queue")["window_covered"] is True       # session, needs 14
    assert _row(report, "plan.timeline")["window_covered"] is True     # weekly, needs 28
    assert _row(report, "overview.where_account_stands")["window_covered"] is False  # quarterly


def test_an_event_driven_surface_is_never_scored_on_elapsed_days(client):
    """§6.4. Elapsed time says nothing about a surface with no schedule, so no length of window
    makes it covered — it stays unobservable and says why, rather than being called unused."""
    _measuring_since(client, 900)
    copilot = replace(surfaces.BY_KEY["global.copilot"], instrumented=True)
    observation, notice = surface_usage._observe(
        copilot, rendered=0, engaged=0, observed_days=900)
    assert copilot.cadence == "event_driven"
    assert surfaces.window_days(copilot.cadence) is None
    assert observation == "insufficient_window"
    assert "no schedule" in notice
    assert "trigger" in notice


def test_insufficient_window_wins_over_the_counts(client):
    """It is decided *before* the counts are read. Otherwise a zero on an uncovered window would
    slip through as `not_rendered`, which is the confident lie §6.2 names."""
    _measuring_since(client, 10)
    _emit(client, "surface_rendered", "today.queue")
    _emit(client, "surface_engaged", "today.queue")
    row = _row(_report(client), "today.queue")
    assert row["engaged"] == 1
    assert row["observation"] == "insufficient_window"


# --- §6.3 the four observations -----------------------------------------------------------------

def test_the_four_observations_are_mutually_exclusive_and_never_combine(client):
    _measuring_since(client, 40)
    _emit(client, "surface_rendered", "today.queue")
    _emit(client, "surface_engaged", "today.queue")
    _emit(client, "surface_rendered", "plan.timeline")
    report = _report(client)

    assert _row(report, "today.queue")["observation"] == "engaged"
    assert _row(report, "plan.timeline")["observation"] == "rendered_not_engaged"
    assert _row(report, "today.saved_views")["observation"] == "not_rendered"
    assert _row(report, "operations.measurement")["observation"] == "insufficient_window"

    # Four independent counters over the same population. Nothing divides or totals them into one.
    totals = report["totals"]
    assert sum(totals[name] for name in surface_usage.OBSERVATIONS) == totals["surfaces"]
    assert not any(isinstance(v, float) for v in totals.values())


def test_never_displayed_is_stated_as_the_weaker_removal_argument(client):
    """§6.3's most losable sentence. `not_rendered` is a reachability finding; presenting it as a
    stronger case than the clutter one is how something never seen gets removed for not being used.
    """
    report = _report(client)
    clutter = report["observations"]["rendered_not_engaged"]["suggests"]
    reach = report["observations"]["not_rendered"]["suggests"]
    assert "clutter" in clutter.lower()
    assert "weaker" in reach.lower()
    assert "more prominent" in reach.lower()


def test_the_caveat_is_server_authored_and_travels_with_the_numbers(client):
    """§8: beside the numbers, not in a tooltip. On the server for the reason every refusal
    sentence in this repo is — a view that composes part of a caution can soften one."""
    report = _report(client)
    assert report["caveat"] == surface_usage.CAVEAT
    assert "cannot say whether a surface is valuable" in report["caveat"]
    assert "Record a cause before changing anything." in report["caveat"]


def test_the_recorded_cause_is_always_null_until_an_operator_records_one(client):
    """§6.1's fourth axis is never inferred. Slice 3 is what lets one be recorded at all."""
    assert all(row["recorded_cause"] is None for row in _report(client)["surfaces"])


def test_an_uninstrumented_surface_says_so_rather_than_reading_zero(client):
    """A zero means two different things — nobody used it, and nobody wired it up — and only one of
    those is a reason to remove anything. The registry's `instrumented` reason carries through."""
    report = _report(client)
    for row in report["surfaces"]:
        assert isinstance(row["instrumented"], bool)
        if not row["instrumented"]:
            assert row["instrumentation_note"]
    assert report["totals"]["uninstrumented"] == sum(
        1 for s in surfaces.REGISTRY if s.kind != "command" and s.instrumented is not True)


def test_incomplete_engagement_wiring_never_becomes_disuse_evidence(client):
    """Even synthetic counts cannot make an exposure-only surface knowable.

    The adversarial case is a descendant control that is heavily used but never calls the wrapper's
    `engage`: renders accumulate, engagement stays zero, and the old report called that clutter. A
    registry sentence must win before either counter is interpreted.
    """
    _measuring_since(client, 300)
    _emit(client, "surface_rendered", "commercial.whitespace")
    report = _report(client)
    row = _row(report, "commercial.whitespace")
    assert row["rendered"] == 1
    assert row["engaged"] == 0
    assert row["instrumented"] is False
    assert row["observation"] == "insufficient_window"
    assert row["window_covered"] is False
    assert "semantic engagement" in row["notice"]
    assert all(item["surface"] != "commercial.whitespace"
               for screen in report["screens"] for item in screen["never_engaged"])


# --- §8 the report ------------------------------------------------------------------------------

def test_the_default_order_is_navigation_order_not_least_used(client):
    """A leaderboard sorted by disuse reads as a kill list, and its top row would be whichever
    surface has the least honest window rather than the least useful one."""
    report = _report(client)
    assert report["sort"] == "navigation"
    expected = [s.key for s in surfaces.REGISTRY if s.kind != "command"]
    assert [row["surface"] for row in report["surfaces"]] == expected


def test_sorting_by_disuse_is_available_and_puts_unknowable_rows_last(client):
    _measuring_since(client, 40)
    _emit(client, "surface_rendered", "today.queue")
    _emit(client, "surface_engaged", "today.queue")
    _emit(client, "surface_rendered", "plan.timeline")
    report = _report(client, sort="least_used")
    assert report["sort"] == "least_used"
    order = [row["observation"] for row in report["surfaces"]]
    # The clutter case heads the list; the unknowable rows cannot head a list they have no basis
    # to head, so they sit at the end whatever their counts say.
    assert order[0] == "rendered_not_engaged"
    assert order[-1] == "insufficient_window"


def test_commands_are_not_rows_in_the_surface_report(client):
    """A command is invoked, never rendered. Giving it an exposure count would invent a number."""
    keys = {row["surface"] for row in _report(client)["surfaces"]}
    assert keys.isdisjoint(surfaces.COMMAND_KEYS)
    assert keys == surfaces.SURFACE_KEYS


def test_every_registered_surface_gets_a_row_even_with_no_events(client):
    """A surface missing from the table is indistinguishable from one nobody thought to register."""
    assert len(_report(client)["surfaces"]) == len(surfaces.SURFACE_KEYS)


def test_the_window_states_when_it_started_observing(client):
    """§9.1: stated prominently, so a period known to be a build week can be discounted."""
    _measuring_since(client, 40)
    window = _report(client)["window"]
    assert window["observed_days"] == 40
    assert window["measuring_since"] == (_today() - timedelta(days=40)).isoformat()
    assert window["from"] == window["measuring_since"]


def test_a_requested_window_never_claims_more_than_was_observed(client):
    """Asking for 210 days on a 40-day-old installation gets 40 days and a `from` that says so.

    Honouring the request literally would produce a covered reading over a period during which
    nothing was being recorded — every surface `not_rendered`, and every one of those a lie.
    """
    _measuring_since(client, 40)
    window = _report(client, window_days=210)["window"]
    assert window["observed_days"] == 40
    assert window["requested_window_days"] == 210
    assert _row(_report(client, window_days=210), "operations.measurement")["observation"] == (
        "insufficient_window")


def test_a_narrower_window_than_the_observation_period_is_honoured(client):
    _measuring_since(client, 400)
    window = _report(client, window_days=30)["window"]
    assert window["observed_days"] == 30


# --- the whole-month disclosure -----------------------------------------------------------------

def _month_edges(day):
    """First and last day of `day`'s month, without importing a calendar into the test."""
    first = day.replace(day=1)
    return first, (first.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)


def test_counts_reach_outside_the_labeled_window_and_the_report_says_so(client):
    """The counts are summed over whole months, so a window starting mid-month counts the days
    before it. That is the right call — pro-rating would invent renders — but a window labeled
    from the 14th that silently counts a 1st-of-the-month render is the confident lie §6.2 exists
    to stop, so the overhang is named in days on both sides.
    """
    _measuring_since(client, 60)
    first, last = _month_edges(_today())
    assert _emit(client, "surface_rendered", "accounts.book",
                 when=f"{first.isoformat()}T09:00:00+00:00").status_code in (200, 202)

    report = _report(client, today=(first + timedelta(days=14)).isoformat(), window_days=1)
    assert report["window"]["from"] == (first + timedelta(days=13)).isoformat()
    # The render on the 1st is outside that window and is counted anyway. This is the fact the
    # disclosure exists for; without the assertion the disclosure could be describing nothing.
    assert _row(report, "accounts.book")["rendered"] >= 1

    partial = report["partial_months"]
    assert partial["months"] == [f"{first:%Y-%m}"]
    assert partial["partial"] == [f"{first:%Y-%m}"]
    assert partial["days_before_window"] == 13
    assert partial["days_after_window"] == (last - (first + timedelta(days=14))).days
    assert "whole calendar months" in partial["notice"]
    assert "13 days before" in partial["notice"]


def test_a_window_on_whole_month_boundaries_discloses_no_overhang(client):
    """A disclosure that is always on is wallpaper. When the window is whole months, there is no
    overhang to state and no sentence is authored."""
    _measuring_since(client, 400)
    first, last = _month_edges(_today())
    report = _report(client, today=last.isoformat(), window_days=(last - first).days)
    assert report["window"]["from"] == first.isoformat()

    partial = report["partial_months"]
    assert partial["partial"] == []
    assert partial["days_before_window"] == 0 and partial["days_after_window"] == 0
    assert partial["notice"] is None


# --- §17.1, carried forward ---------------------------------------------------------------------

def test_no_domain_module_imports_surface_usage():
    """Which screens the operator uses may never reach an account, a pillar, or a ranking."""
    import pathlib
    app_dir = pathlib.Path(__file__).resolve().parent.parent / "app"
    # `surface_retirement.py` reads the report so its §7.8 preview freezes the same counts the
    # operator was looking at. It is the other half of the measurement feature, not a domain module.
    # `telemetry.py` folds before it purges, so a raw event cannot be deleted before it has reached
    # the monotone rollup. That is measurement calling measurement — the direction §17.1 permits.
    # What §17.1 forbids is a *domain* module reading which screens the operator uses, and the sink
    # is not one: nothing here reaches an account, a pillar, a ranking, or a generated output.
    allowed = {"surface_usage.py", "surface_retirement.py", "telemetry.py",
               "routers/telemetry.py"}
    # The module, not the table. `telemetry.py` also names `surface_usage_months` because the off
    # switch deletes it in the same transaction as the raw events (§9.4), and that write belongs
    # beside the setting it enforces.
    module = re.compile(r"(import\s+surface_usage|from\s+\.+surface_usage|surface_usage\.[a-z])")
    offenders = []
    for path in sorted(app_dir.rglob("*.py")):
        rel = str(path.relative_to(app_dir))
        if rel in allowed or rel.startswith("__"):
            continue
        if module.search(path.read_text()):
            offenders.append(rel)
    assert offenders == [], f"these modules read surface usage: {offenders}"
