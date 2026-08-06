"""Stage 7 adversarial contracts: recurrence, cooldown, pacing, source idempotency, and scope."""
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


def _day(offset=0):
    return utc_day(offset)


def _account_program(client, name="A"):
    account = client.post("/api/accounts", json={"name": name}).json()
    program = client.post("/api/programs", json={"account_id": account["id"], "name": "Launch"}).json()
    return account, program


def _cell(client, account):
    partition = client.post("/api/population-partitions", json={
        "account_id": account["id"], "total_fte": 1000,
        "fte_source": "client", "fte_as_of": _day()}).json()
    segment = client.post("/api/population-segments", json={
        "partition_id": partition["id"], "name": "Core", "headcount": 900,
        "headcount_source": "client", "headcount_as_of": _day()}).json()
    use_case = client.post("/api/use-cases", json={
        "name": f"Change {account['id'][:5]}", "slug": f"change-{account['id']}"}).json()
    cell = client.post("/api/whitespace-cells", json={
        "account_id": account["id"], "segment_id": segment["id"],
        "use_case_id": use_case["id"], "estimated_seats": 300}).json()
    return segment, cell


def test_play_can_refire_after_condition_closes_and_recurs(client):
    account, program = _account_program(client)
    responsible = client.post("/api/persons", json={"name": "Client", "account_id": account["id"]}).json()
    owner = client.post("/api/persons", json={"name": "Operator", "affiliation": "valence"}).json()
    commitment = client.post("/api/commitments", json={
        "program_id": program["id"], "description": "Late", "responsible_party_id": responsible["id"],
        "internal_owner_id": owner["id"], "due_date": _day(-2)}).json()
    client.post("/api/plays", json={"name": "Chase", "trigger_kind": "overdue_commitment",
                                     "action_template": "Chase {title}"})

    first = client.post("/api/plays/evaluate").json()
    assert first["count"] == 1
    assert client.post("/api/plays/evaluate").json()["count"] == 0

    conn = client.app.state.conn
    conn.execute("UPDATE commitments SET status='closed',updated_at=? WHERE id=?",
                 (_day(), commitment["id"])); conn.commit()
    assert client.post("/api/plays/evaluate").json()["count"] == 0
    conn.execute("UPDATE commitments SET status='open',updated_at=? WHERE id=?",
                 (_day(1), commitment["id"])); conn.commit()
    second = client.post("/api/plays/evaluate").json()
    assert second["count"] == 1
    runs = client.get("/api/play-runs").json()
    assert len(runs) == 2 and runs[0]["signal_episode_id"] != runs[1]["signal_episode_id"]


def test_client_pull_bypasses_pacing_and_dismissal_has_cooldown(client):
    account, program = _account_program(client)
    _segment, cell = _cell(client, account)
    for n in range(2):
        res = client.post("/api/pull-signals", json={
            "account_id": account["id"], "program_id": program["id"], "cell_id": cell["id"],
            "description": f"Client team {n} asked for access", "occurred_on": _day(-n)})
        assert res.status_code == 201
    client.post("/api/signals/evaluate")
    episodes = client.get(f"/api/signal-episodes?account_id={account['id']}").json()["episodes"]
    pull = next(e for e in episodes if e["context"].get("signal_type") == "client_pull")
    assert pull["status"] == "open"               # customer pull is never pacing-suppressed
    assert client.post(f"/api/signal-episodes/{pull['id']}/dismiss", json={"reason": "Already funded elsewhere"}).status_code == 200
    client.post("/api/signals/evaluate")
    after = client.get(f"/api/signal-episodes?account_id={account['id']}").json()["episodes"]
    assert not any(e["status"] == "open" and e["condition_key"] == pull["condition_key"] for e in after)


def test_vendor_calendar_signal_is_held_by_unrealized_value(client):
    account, program = _account_program(client)
    segment, cell = _cell(client, account)
    definition = client.post("/api/metric-definitions", json={"name": "Activation", "stale_after_days": 30}).json()
    client.post("/api/value-targets", json={
        "account_id": account["id"], "definition_id": definition["id"],
        "segment_id": segment["id"], "target_value": 0.7, "timeframe_end": _day(30)})
    event = client.post("/api/calendar-events", json={
        "account_id": account["id"], "program_id": program["id"], "cell_id": cell["id"],
        "purpose": "qbr", "title": "Value review", "starts_at": _day(10) + "T15:00:00+00:00"})
    assert event.status_code == 201
    client.post("/api/signals/evaluate")
    episodes = client.get(f"/api/signal-episodes?account_id={account['id']}").json()["episodes"]
    calendar = next(e for e in episodes if e["kind"] == "calendar_moment")
    assert calendar["status"] == "held" and "value target" in calendar["held_reason"]
    assert client.post(f"/api/signal-episodes/{calendar['id']}/draft-opportunity").status_code == 409


def test_cross_account_pull_links_rejected_by_api_and_database(client):
    a1, p1 = _account_program(client, "A1")
    a2, _p2 = _account_program(client, "A2")
    _segment, foreign_cell = _cell(client, a2)
    res = client.post("/api/pull-signals", json={
        "account_id": a1["id"], "program_id": p1["id"], "cell_id": foreign_cell["id"],
        "description": "wrong account"})
    assert res.status_code == 422

    conn = client.app.state.conn
    from app.db import new_id, now_utc
    with pytest.raises(sqlite3.IntegrityError, match="different account"):
        conn.execute("INSERT INTO pull_signals (id,account_id,program_id,cell_id,description,created_at,updated_at) "
                     "VALUES (?,?,?,?,?,?,?)", (new_id(), a1["id"], p1["id"], foreign_cell["id"],
                                                  "raw bypass", now_utc(), now_utc()))


def test_org_change_is_proposal_until_confirmed(client):
    account, _program = _account_program(client)
    person = client.post("/api/persons", json={
        "name": "Budget owner", "account_id": account["id"], "title": "VP L&D"}).json()
    from app import repo
    flag = repo.insert(client.app.state.conn, "org_change_flags", {
        "account_id": account["id"], "person_id": person["id"], "kind": "title_change",
        "summary": "Promoted", "old_title": "VP L&D", "new_title": "SVP Talent",
        "occurred_on": _day(),
    }, object_type="org_change_flag")
    assert client.get(f"/api/persons/{person['id']}/card").json()["title"] == "VP L&D"
    confirmed = client.post(f"/api/org-change-flags/{flag['id']}/confirm", json={})
    assert confirmed.status_code == 200
    assert client.get(f"/api/persons/{person['id']}/card").json()["title"] == "SVP Talent"
    client.post("/api/signals/evaluate")
    episodes = client.get(f"/api/signal-episodes?account_id={account['id']}").json()["episodes"]
    assert any(e["kind"] == "org_change_confirmed" and e["object_id"] == flag["id"] for e in episodes)


def test_confirmed_champion_departure_preserves_snapshot_and_opens_successor(client):
    account, program = _account_program(client)
    person = client.post("/api/persons", json={
        "name": "Champion", "account_id": account["id"], "title": "CHRO"}).json()
    role = client.post("/api/stakeholder-roles", json={
        "program_id": program["id"], "person_id": person["id"], "role": "champion",
        "cares_about": "manager quality"}).json()
    from app import repo
    conn = client.app.state.conn
    candidate = repo.insert(conn, "champion_candidates", {
        "person_id": person["id"], "program_id": program["id"], "account_id": account["id"],
        "stage": "maintain"}, object_type="champion_candidate")
    flag = repo.insert(conn, "org_change_flags", {
        "account_id": account["id"], "person_id": person["id"], "kind": "departure",
        "summary": "Champion left", "new_company": "Future account", "occurred_on": _day(),
    }, object_type="org_change_flag")
    result = client.post(f"/api/org-change-flags/{flag['id']}/confirm", json={})
    assert result.status_code == 200, result.text
    effects = result.json()["side_effects"]
    placeholder = conn.execute("SELECT * FROM persons WHERE id=?", (effects["successor_placeholder_id"],)).fetchone()
    succession = conn.execute("SELECT * FROM succession_records WHERE id=?", (effects["succession_id"],)).fetchone()
    assert placeholder["is_placeholder"] == 1 and "Successor" in placeholder["name"]
    assert succession["status"] == "open" and "manager quality" in succession["relationship_snapshot_json"]
    assert conn.execute("SELECT archived FROM stakeholder_roles WHERE id=?", (role["id"],)).fetchone()[0] == 1
    assert conn.execute("SELECT archived FROM champion_candidates WHERE id=?", (candidate["id"],)).fetchone()[0] == 1


def test_land_and_leave_requires_two_periods_and_closes_when_expansion_recorded(client):
    account, _program = _account_program(client)
    segment, _cell_row = _cell(client, account)
    for period, headcount, observed in (("Q1", 800, _day(-90)), ("Q2", 900, _day(-1))):
        assert client.post("/api/population-headcount-observations", json={
            "segment_id": segment["id"], "period_label": period, "headcount": headcount,
            "source_kind": "client_stated", "observed_on": observed}).status_code == 201
    client.post("/api/signals/evaluate")
    episodes = client.get(f"/api/signal-episodes?account_id={account['id']}").json()["episodes"]
    assert any(e["kind"] == "land_and_leave" and e["status"] == "open" for e in episodes)
    assert client.post("/api/revenue-events", json={
        "account_id": account["id"], "kind": "expansion", "effective_on": _day(-30),
        "amount": 1000, "currency": "USD", "reason": "Expansion amendment"}).status_code == 201
    client.post("/api/signals/evaluate")
    episodes = client.get(f"/api/signal-episodes?account_id={account['id']}").json()["episodes"]
    assert not any(e["kind"] == "land_and_leave" and e["status"] == "open" for e in episodes)


def test_mock_adapters_parse_without_external_connections():
    from app import adapters
    events = adapters.fetch_calendar_events()
    changes = adapters.fetch_org_changes()
    headcount = adapters.fetch_headcount_observations()
    assert len(events) >= 2 and all(e["external_id"] for e in events)
    assert changes and all(c["external_id"] for c in changes)
    assert headcount and {r["period_label"] for r in headcount} >= {"2026-Q1", "2026-Q2"}


def test_priority_response_clock_excludes_weekend_hours():
    from app.queue import _business_hours_between
    # Friday 17:00 through Monday 17:00 in New York contains one eight-hour workday, not 72h.
    hours = _business_hours_between(
        "2026-07-31T21:00:00+00:00", "2026-08-03T21:00:00+00:00",
        "America/New_York", 9, 17,
    )
    assert hours == 8


def test_business_hours_settings_reject_invalid_timezone_and_window(client):
    account, _program = _account_program(client)
    url = f"/api/accounts/{account['id']}/settings"
    assert client.put(url, json={"business_timezone": "Mars/Olympus_Mons"}).status_code == 422
    assert client.put(url, json={
        "business_day_start_hour": 18, "business_day_end_hour": 9,
    }).status_code == 422
    accepted = client.put(url, json={
        "business_timezone": "Europe/Berlin",
        "business_day_start_hour": 8, "business_day_end_hour": 16,
    })
    assert accepted.status_code == 200
    assert accepted.json()["business_timezone"] == "Europe/Berlin"


def test_calendar_and_succession_update_guards_reject_cross_account_people(client):
    account_a, program_a = _account_program(client, "A")
    account_b, _program_b = _account_program(client, "B")
    person_a = client.post("/api/persons", json={
        "name": "A person", "account_id": account_a["id"], "email": "a@example.test",
    }).json()
    person_b = client.post("/api/persons", json={
        "name": "B person", "account_id": account_b["id"], "email": "b@example.test",
    }).json()
    event = client.post("/api/calendar-events", json={
        "account_id": account_a["id"], "program_id": program_a["id"],
        "title": "Account A review", "starts_at": "2026-08-03T14:00:00+00:00",
    }).json()
    from app.db import new_id, now_utc
    conn = client.app.state.conn
    conn.execute("INSERT INTO calendar_event_attendees "
                 "(event_id,person_id,email,response_status,attendance_status,created_at) "
                 "VALUES (?,?,?,'accepted','invited',?)",
                 (event["id"], person_a["id"], person_a["email"], now_utc()))
    succession_id = new_id()
    conn.execute("INSERT INTO succession_records "
                 "(id,account_id,departed_person_id,status,created_at,updated_at) "
                 "VALUES (?,?,?,'open',?,?)",
                 (succession_id, account_a["id"], person_a["id"], now_utc(), now_utc()))
    conn.commit()

    with pytest.raises(sqlite3.IntegrityError, match="calendar attendee"):
        conn.execute("UPDATE calendar_event_attendees SET person_id=? WHERE event_id=? AND email=?",
                     (person_b["id"], event["id"], person_a["email"]))
    with pytest.raises(sqlite3.IntegrityError, match="succession person"):
        conn.execute("UPDATE succession_records SET successor_person_id=? WHERE id=?",
                     (person_b["id"], succession_id))
