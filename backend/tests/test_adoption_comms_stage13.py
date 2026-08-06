"""Stage 13 adversarial contracts: no sending, immutable facts, and honest attendance."""
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
        yield c
    for suffix in ("", "-wal", "-shm"):
        try: os.unlink(path + suffix)
        except FileNotFoundError: pass


@pytest.fixture()
def ctx(client):
    account = client.post("/api/accounts", json={"name": "Northstar Works"}).json()
    program = client.post("/api/programs", json={"account_id": account["id"], "name": "Manager launch"}).json()
    partition = client.post("/api/population-partitions", json={
        "account_id": account["id"], "total_fte": 1000}).json()
    segment = client.post("/api/population-segments", json={
        "partition_id": partition["id"], "name": "Field managers", "headcount": 300}).json()
    sequence = client.post("/api/comms-sequences", json={
        "program_id": program["id"], "name": "Manager launch wave",
        "purpose": "Invite, remind, and reinforce the live sessions"}).json()
    return {"account": account, "program": program, "partition": partition,
            "segment": segment, "sequence": sequence}


def _wave(client, ctx, number=1, **extra):
    body = {"message": f"Wave {number}", "audience": "Field managers", "channel": "email",
            "wave_number": number, "segment_id": ctx["segment"]["id"], **extra}
    response = client.post(f"/api/comms-sequences/{ctx['sequence']['id']}/waves", json=body)
    assert response.status_code == 201, response.text
    return response.json()


def _session(client, ctx, wave, starts=None):
    response = client.post("/api/comms-sessions", json={
        "comms_sequence_id": ctx["sequence"]["id"], "invited_by_entry_id": wave["id"],
        "purpose": "webinar", "title": "Manager launch webinar",
        "starts_at": (starts or utc_day(-1)) + "T15:00:00+00:00"})
    assert response.status_code == 201, response.text
    return response.json()


def _attendee(client, event, n, scope="audience", status="attended"):
    return client.put(f"/api/calendar-events/{event['id']}/attendees", json={
        "name": f"Attendee {n}", "email": f"attendee-{n}@example.test",
        "attendance_scope": scope, "attendance_status": status})


def test_expected_dates_derive_from_actual_predecessor_send(client, ctx):
    first = _wave(client, ctx, send_date=utc_day(-5))
    second = _wave(client, ctx, 2, follows_entry_id=first["id"], offset_days=3)
    before = client.get(f"/api/comms-sequences/{ctx['sequence']['id']}").json()
    successor = next(w for w in before["waves"] if w["id"] == second["id"])
    assert successor["expected_send_on"] == utc_day(-2)
    assert successor["date_provisional"] is True

    sent = client.post(f"/api/comms-waves/{first['id']}/sent", json={
        "sent_at": utc_day(-3) + "T17:00:00+00:00"})
    assert sent.status_code == 200
    after = client.get(f"/api/comms-sequences/{ctx['sequence']['id']}").json()
    successor = next(w for w in after["waves"] if w["id"] == second["id"])
    assert successor["expected_send_on"] == utc_day(0)
    assert successor["date_provisional"] is False
    assert after["status"] == "running"


def test_cross_account_population_rejected_at_api_and_trigger(client, ctx):
    other = client.post("/api/accounts", json={"name": "Other synthetic account"}).json()
    part = client.post("/api/population-partitions", json={"account_id": other["id"], "total_fte": 100}).json()
    foreign = client.post("/api/population-segments", json={
        "partition_id": part["id"], "name": "Other cohort", "headcount": 80}).json()
    response = client.post(f"/api/comms-sequences/{ctx['sequence']['id']}/waves", json={
        "message": "Wrong scope", "wave_number": 1, "segment_id": foreign["id"]})
    assert response.status_code == 422 and "different account" in response.json()["detail"]

    conn = client.app.state.conn
    with pytest.raises(sqlite3.IntegrityError, match="invalid comms wave scope"):
        conn.execute("INSERT INTO comms_entries "
                     "(id,program_id,message,status,sequence_id,wave_number,segment_id,created_at,updated_at) "
                     "VALUES ('bad',?,?, 'planned',?,1,?,datetime('now'),datetime('now'))",
                     (ctx["program"]["id"], "Wrong scope", ctx["sequence"]["id"], foreign["id"]))


def test_duplicate_order_cross_sequence_predecessor_and_cycles_are_rejected(client, ctx):
    first = _wave(client, ctx)
    duplicate = client.post(f"/api/comms-sequences/{ctx['sequence']['id']}/waves", json={
        "message": "Duplicate", "wave_number": 1, "segment_id": ctx["segment"]["id"]})
    assert duplicate.status_code == 409
    other = client.post("/api/comms-sequences", json={
        "program_id": ctx["program"]["id"], "name": "Other sequence"}).json()
    foreign_wave = client.post(f"/api/comms-sequences/{other['id']}/waves", json={
        "message": "Other", "wave_number": 1}).json()
    cross = client.post(f"/api/comms-sequences/{ctx['sequence']['id']}/waves", json={
        "message": "Cross", "wave_number": 2, "follows_entry_id": foreign_wave["id"],
        "offset_days": 1})
    assert cross.status_code == 422

    second = _wave(client, ctx, 2, follows_entry_id=first["id"], offset_days=1)
    cycle = client.patch(f"/api/comms-waves/{first['id']}", json={
        "follows_entry_id": second["id"], "offset_days": 1})
    assert cycle.status_code == 422 and "cannot cycle" in cycle.json()["detail"]


def test_sent_wave_is_an_explicit_immutable_fact(client, ctx):
    wave = _wave(client, ctx)
    conn = client.app.state.conn
    with pytest.raises(sqlite3.IntegrityError, match="send state"):
        conn.execute("UPDATE comms_entries SET status='sent' WHERE id=?", (wave["id"],))
    assert client.post(f"/api/comms-waves/{wave['id']}/sent", json={}).status_code == 200
    changed = client.patch(f"/api/comms-waves/{wave['id']}", json={"message": "Rewrite history"})
    assert changed.status_code == 409
    with pytest.raises(sqlite3.IntegrityError, match="immutable"):
        conn.execute("UPDATE comms_entries SET message='Rewrite history' WHERE id=?", (wave["id"],))


def test_cancelled_sequence_freezes_waves_but_legacy_standalone_comms_still_work(client, ctx):
    wave = _wave(client, ctx)
    assert client.post(f"/api/comms-sequences/{ctx['sequence']['id']}/cancel", json={
        "reason": "Launch was withdrawn"}).status_code == 200
    blocked = client.post(f"/api/comms-waves/{wave['id']}/sent", json={})
    assert blocked.status_code == 409 and "cancelled" in blocked.json()["detail"]
    conn = client.app.state.conn
    with pytest.raises(sqlite3.IntegrityError, match="cancelled comms sequences are immutable"):
        conn.execute("UPDATE comms_entries SET message='After cancellation' WHERE id=?", (wave["id"],))

    # Stage 13 may not retroactively impose sent_at on the pre-existing standalone workflow.
    standalone = client.post("/api/comms-entries", json={
        "program_id": ctx["program"]["id"], "message": "Legacy one-off", "status": "sent"})
    assert standalone.status_code == 201, standalone.text
    conn.execute("UPDATE comms_entries SET message='Corrected legacy label' WHERE id=?",
                 (standalone.json()["id"],))
    conn.commit()


def test_future_and_unclassified_attendance_are_unknown_or_incomplete(client, ctx):
    wave = _wave(client, ctx)
    future = _session(client, ctx, wave, utc_day(3))
    assert client.get(f"/api/calendar-events/{future['id']}/attendance").json()["state"] == "unknown"

    past = _session(client, ctx, wave)
    assert _attendee(client, past, 1, scope="unknown").status_code == 200
    result = client.get(f"/api/calendar-events/{past['id']}/attendance").json()
    assert result["state"] == "incomplete" and result["rate"] is None


def test_attendance_floor_and_facilitator_exclusion(client, ctx):
    wave = _wave(client, ctx)
    event = _session(client, ctx, wave)
    for n in range(24):
        assert _attendee(client, event, n, status="attended" if n < 18 else "no_show").status_code == 200
    facilitator = _attendee(client, event, 99, scope="facilitator")
    assert facilitator.status_code == 200
    below = client.get(f"/api/calendar-events/{event['id']}/attendance").json()
    assert below["state"] == "suppressed" and below["invited"] is None

    assert _attendee(client, event, 24, status="attended").status_code == 200
    known = client.get(f"/api/calendar-events/{event['id']}/attendance").json()
    assert known["state"] == "known" and known["invited"] == 25
    assert known["attended"] == 19 and known["no_show"] == 6
    assert known["rate"] == 19 / 25


def test_an_unrecorded_outcome_is_not_counted_as_a_no_show(client, ctx):
    """§5.3: absence of data may not render as a bad outcome.

    Regression. The rate divided by the full invited count, so an audience member whose outcome
    was never recorded was indistinguishable from one who was asked and did not come.
    """
    wave = _wave(client, ctx)
    event = _session(client, ctx, wave)
    for n in range(20):
        _attendee(client, event, n, status="attended")
    for n in range(20, 25):
        _attendee(client, event, n, status="invited")     # invited, outcome never recorded

    a = client.get(f"/api/calendar-events/{event['id']}/attendance").json()
    assert a["state"] == "known" and a["invited"] == 25
    assert a["attended"] == 20 and a["no_show"] == 0 and a["unknown"] == 5
    assert a["rate"] == 1.0                                # 20 of 20 recorded, not 20 of 25
    assert a["outcomes_unrecorded"] == 5 and "20 of 20" in a["rate_basis"]


def test_unknown_cohort_size_suppresses_attendance(client, ctx):
    unknown = client.post("/api/population-segments", json={
        "partition_id": ctx["partition"]["id"], "name": "Unmeasured cohort"}).json()
    wave = _wave(client, ctx, segment_id=unknown["id"])
    event = _session(client, ctx, wave)
    result = client.get(f"/api/calendar-events/{event['id']}/attendance").json()
    assert result["state"] == "suppressed"
    assert "unknown" in result["suppression_reason"]


def test_one_today_item_per_overdue_sequence(client, ctx):
    first = _wave(client, ctx, send_date=utc_day(-4))
    _wave(client, ctx, 2, follows_entry_id=first["id"], offset_days=1)
    queue = client.get("/api/queue").json()["items"]
    items = [i for i in queue if i["object_type"] == "comms_sequence" and
             i["object_id"] == ctx["sequence"]["id"]]
    assert len(items) == 1 and "2 planned waves" in items[0]["because"]
    assert "auto-sent" in items[0]["next_action"]


def test_campaign_plan_reads_wave_state_from_canonical_comms_entry(client, ctx):
    """Stage 11's no-cloned-state contract still holds after a comms entry becomes a wave."""
    wave = _wave(client, ctx)
    # The campaign test suite covers link creation. Here the service-level source map is enough to
    # prove the canonical state column remains comms_entries.status rather than a sequence copy.
    from app import campaigns
    assert campaigns._LINK_SOURCES["comms_entry_id"] == ("comms_entries", "message", "status")
    client.post(f"/api/comms-waves/{wave['id']}/sent", json={})
    assert client.app.state.conn.execute(
        "SELECT status FROM comms_entries WHERE id=?", (wave["id"],)).fetchone()["status"] == "sent"


def test_stage13_has_no_outbound_or_auto_advance_path(client, ctx):
    import app.adoption_comms as service
    import app.routers.adoption_comms as router_module
    source = (service.__doc__ or "") + open(service.__file__).read() + open(router_module.__file__).read()
    for forbidden in ("smtplib", "sendgrid", "requests.post", "httpx.post", "urlopen",
                      "fetch_calendar_events", "jobs.enqueue"):
        assert forbidden not in source
    routes = [r.path for r in client.app.routes if hasattr(r, "path")]
    assert not any("/send" in path for path in routes if "comms-sequence" in path or "comms-wave" in path)


def test_calendar_rebuild_preserves_pre_stage13_events_and_attendees():
    """0035 rebuilds a referenced parent table; prove an actual 0034 database survives it."""
    from app.db import discover_migrations
    fd, path = tempfile.mkstemp(suffix=".sqlite"); os.close(fd)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    try:
        for version, migration in discover_migrations():
            if version > 34:
                break
            conn.executescript(migration.read_text())
        now = "2026-08-01T12:00:00+00:00"
        conn.execute("INSERT INTO accounts(id,name,created_at,updated_at) VALUES ('a','Legacy synthetic',?,?)", (now, now))
        conn.execute("INSERT INTO programs(id,account_id,name,phase,created_at,updated_at) "
                     "VALUES ('p','a','Legacy launch','foundation',?,?)", (now, now))
        conn.execute("INSERT INTO calendar_events "
                     "(id,account_id,program_id,purpose,title,starts_at,created_at,updated_at) "
                     "VALUES ('e','a','p','governance','Legacy forum',?,?,?)", (now, now, now))
        conn.execute("INSERT INTO calendar_event_attendees "
                     "(event_id,name,email,attendance_status,created_at) "
                     "VALUES ('e','Legacy attendee','legacy@example.test','attended',?)", (now,))
        conn.commit()
        migration35 = next(path for version, path in discover_migrations() if version == 35)
        conn.executescript(migration35.read_text())
        event = conn.execute("SELECT * FROM calendar_events WHERE id='e'").fetchone()
        attendee = conn.execute("SELECT * FROM calendar_event_attendees WHERE event_id='e'").fetchone()
        assert event["purpose"] == "governance" and event["comms_sequence_id"] is None
        assert attendee["attendance_status"] == "attended" and attendee["attendance_scope"] == "unknown"
        assert conn.execute("PRAGMA foreign_key_check").fetchall() == []
        assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    finally:
        conn.close()
        for suffix in ("", "-wal", "-shm"):
            try: os.unlink(path + suffix)
            except FileNotFoundError: pass
