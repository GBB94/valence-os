"""Stage 7.5 adversarial contracts: five slots, earned triggers, renewal, and overlap."""
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


def _setup(client, name="Account"):
    account = client.post("/api/accounts", json={"name": name, "incumbent_note": "Legacy vendor"}).json()
    program = client.post("/api/programs", json={"account_id": account["id"], "name": "Global"}).json()
    partition = client.post("/api/population-partitions", json={
        "account_id": account["id"], "total_fte": 1000, "fte_source": "client", "fte_as_of": _day()}).json()
    segment = client.post("/api/population-segments", json={
        "partition_id": partition["id"], "name": "Core", "headcount": 900,
        "headcount_source": "client", "headcount_as_of": _day()}).json()
    person = client.post("/api/persons", json={"name": "Budget owner", "account_id": account["id"]}).json()
    champion = client.post("/api/persons", json={"name": "Champion", "account_id": account["id"]}).json()
    source = client.post("/api/source-references", json={"label": "Signed scorecard", "type": "file"}).json()
    definition = client.post("/api/metric-definitions", json={
        "name": f"Activation {account['id'][:5]}", "stale_after_days": 30}).json()
    target = client.post("/api/value-targets", json={
        "account_id": account["id"], "definition_id": definition["id"], "segment_id": segment["id"],
        "target_value": .7, "direction": "at_least", "timeframe_end": _day(30),
        "source_reference_id": source["id"]}).json()
    observation = client.post("/api/metric-observations", json={
        "definition_id": definition["id"], "program_id": program["id"],
        "population_segment_id": segment["id"], "value": .8, "current_through": _day(),
        "source_reference_id": source["id"]}).json()
    contract = client.post("/api/contracts", json={
        "account_id": account["id"], "version_label": "FY27", "seats": 200,
        "renewal_date": _day(90), "notice_period_days": 30}).json()
    return locals()


def _validated_champion(client, setup):
    from app import repo
    conn = client.app.state.conn
    candidate = repo.insert(conn, "champion_candidates", {
        "person_id": setup["champion"]["id"], "program_id": setup["program"]["id"],
        "account_id": setup["account"]["id"], "stage": "validate"}, object_type="champion_candidate")
    repo.insert(conn, "advocacy_events", {
        "person_id": setup["champion"]["id"], "program_id": setup["program"]["id"],
        "kind": "advocacy_without_us", "occurred_on": _day(), "note": "Presented internally"},
        object_type="advocacy_event")
    return candidate


def test_five_slots_are_links_not_a_score(client):
    s = _setup(client); _validated_champion(client, s)
    client.post("/api/compliance-items", json={
        "program_id": s["program"]["id"], "lane": "legal_dpo", "status": "complete"})
    opportunity = client.post("/api/expansions", json={
        "account_id": s["account"]["id"], "name": "Next wave"}).json()
    calendar = client.post("/api/ask-calendars", json={
        "account_id": s["account"]["id"], "name": "Next wave ask", "target_close_date": _day(60),
        "opportunity_id": opportunity["id"]}).json()
    result = client.patch(f"/api/expansions/{opportunity['id']}/qualification", json={
        "value_target_id": s["target"]["id"], "budget_owner_person_id": s["person"]["id"],
        "ask_calendar_id": calendar["id"], "champion_person_id": s["champion"]["id"],
        "program_id": s["program"]["id"]})
    assert result.status_code == 200, result.text
    q = result.json()["qualification"]
    assert q["filled_count"] == 5 and q["fully_qualified"] is True
    assert "score" not in q and q["slots"]["compliance_path"]["status"] == "clear"


def test_unvalidated_champion_is_rejected(client):
    s = _setup(client)
    opportunity = client.post("/api/expansions", json={
        "account_id": s["account"]["id"], "name": "Next wave"}).json()
    result = client.patch(f"/api/expansions/{opportunity['id']}/qualification", json={
        "champion_person_id": s["champion"]["id"]})
    assert result.status_code == 422 and "validated" in result.json()["detail"]


def test_pre_agreed_trigger_fires_with_visible_value_gap_and_actions_once(client):
    s = _setup(client)
    client.post("/api/plays", json={
        "name": "Earned expansion", "trigger_kind": "expansion_signal", "action_template": "Run it"})
    agreement = client.post("/api/operational-agreements", json={
        "account_id": s["account"]["id"], "contract_version_id": s["contract"]["id"],
        "name": "Proof unlocks wave 2", "source_kind": "signed_paper",
        "source_reference_id": s["source"]["id"], "value_target_id": s["target"]["id"],
        "effective_on": _day(-1), "seat_band_min": 100, "seat_band_max": 200,
        "agreed_process": "Issue the order form", "budget_owner_person_id": s["person"]["id"]})
    assert agreement.status_code == 201, agreement.text
    fired = client.post("/api/operational-agreements/evaluate").json()
    assert fired["fired"] == 1
    assert client.post("/api/operational-agreements/evaluate").json()["fired"] == 0
    view = client.get(f"/api/accounts/{s['account']['id']}/operational-agreements").json()
    event = view["agreements"][0]["event"]
    assert event["status"] == "fired" and event["value_at_fire"] == .8
    source = next(x for x in client.get("/api/library").json()["sources"] if x["id"] == s["source"]["id"])
    assert any(c["object_type"] == "operational_agreement" for c in source["citations"])
    queue = client.get("/api/queue").json()["items"]
    assert any(i["object_type"] == "operational_agreement_event" for i in queue)
    actioned = client.post(f"/api/operational-agreement-events/{event['id']}/action")
    assert actioned.status_code == 201
    assert actioned.json()["opportunity"]["qualification_value_target_id"] == s["target"]["id"]
    assert client.post(f"/api/operational-agreement-events/{event['id']}/action").status_code == 409


def test_agreement_rejects_cross_account_contract_even_via_raw_sql(client):
    one, two = _setup(client, "One"), _setup(client, "Two")
    payload = {
        "account_id": one["account"]["id"], "contract_version_id": two["contract"]["id"],
        "name": "Wrong", "source_kind": "signed_paper", "source_reference_id": one["source"]["id"],
        "value_target_id": one["target"]["id"], "effective_on": _day(),
        "seat_band_min": 10, "seat_band_max": 20, "agreed_process": "No"}
    assert client.post("/api/operational-agreements", json=payload).status_code == 422
    from app.db import new_id, now_utc
    with pytest.raises(sqlite3.IntegrityError, match="different account"):
        client.app.state.conn.execute(
            "INSERT INTO operational_agreements "
            "(id,account_id,contract_version_id,name,source_kind,source_reference_id,value_target_id,"
            "effective_on,seat_band_min,seat_band_max,agreed_process,created_at,updated_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (new_id(), one["account"]["id"], two["contract"]["id"], "Wrong", "signed_paper",
             one["source"]["id"], one["target"]["id"], _day(), 10, 20, "No", now_utc(), now_utc()))


def test_overlapping_growth_lines_withhold_totals_and_mutual_plan_hides_internal_fields(client):
    s = _setup(client)
    plan = client.post("/api/growth-plans", json={
        "account_id": s["account"]["id"], "name": "Growth", "target_seats": 800,
        "target_date": _day(180)}).json()
    tag = client.post("/api/audience-tags", json={"name": "Managers", "slug": f"mgr-{s['account']['id']}"}).json()
    views = []
    for n in (1, 2):
        views.append(client.post("/api/population-views", json={
            "account_id": s["account"]["id"], "name": f"View {n}",
            "segment_ids": [s["segment"]["id"]], "tag_ids": [tag["id"]],
            "estimated_headcount": 300}).json())
    for n, view in enumerate(views):
        result = client.post("/api/growth-plan-lines", json={
            "plan_id": plan["id"], "name": f"Line {n}", "view_id": view["id"],
            "seat_count": 200, "probability": .5, "probability_author": "operator",
            "probability_assessed_on": _day(), "client_visible": n == 0,
            "source_reference_id": s["source"]["id"] if n == 0 else None,
            "competitive_notes": "SECRET competitive tactic"})
        assert result.status_code == 201, result.text
    growth = client.get(f"/api/accounts/{s['account']['id']}/growth-plan").json()
    assert growth["rollup"]["additive"] is False
    assert growth["rollup"]["named_seats"] is None and growth["conflicts"]
    # ACCOUNT-PATH-SPEC.md §16.5 replaced the flat `items` list with a grouped artifact; the growth
    # lines moved to their own block, and the intent of this assertion is unchanged.
    mutual = client.get(f"/api/accounts/{s['account']['id']}/map").json()["artifact"]
    assert [line["name"] for line in mutual["growth_lines"]] == ["Line 0"]
    assert "SECRET competitive tactic" not in mutual["markdown"]
    assert "probability" not in mutual["markdown"].lower()
    source = next(x for x in client.get("/api/library").json()["sources"] if x["id"] == s["source"]["id"])
    assert any(c["object_type"] == "growth_plan_line" for c in source["citations"])
    first = growth["lines"][0]
    assert client.patch(f"/api/growth-plan-lines/{first['id']}", json={"probability": .8}).status_code == 422
    assert client.patch(f"/api/growth-plan-lines/{first['id']}", json={
        "probability": .8, "probability_author": "operator", "probability_assessed_on": _day(),
    }).status_code == 200


def test_renewal_center_surfaces_only_fully_qualified_expansion_as_eligible(client):
    s = _setup(client); _validated_champion(client, s)
    client.post("/api/compliance-items", json={
        "program_id": s["program"]["id"], "lane": "legal_dpo", "status": "complete"})
    opportunity = client.post("/api/expansions", json={
        "account_id": s["account"]["id"], "name": "Ride renewal"}).json()
    calendar = client.post("/api/ask-calendars", json={
        "account_id": s["account"]["id"], "name": "Renewal ask", "target_close_date": _day(70),
        "opportunity_id": opportunity["id"]}).json()
    client.patch(f"/api/expansions/{opportunity['id']}/qualification", json={
        "value_target_id": s["target"]["id"], "budget_owner_person_id": s["person"]["id"],
        "ask_calendar_id": calendar["id"], "champion_person_id": s["champion"]["id"],
        "program_id": s["program"]["id"]})
    renewal = client.get(f"/api/accounts/{s['account']['id']}/renewal-center").json()
    assert renewal["timeline"]["days_to_notice"] == 60
    assert [o["id"] for o in renewal["eligible_expansions"]] == [opportunity["id"]]
    assert renewal["alternative_landscape"] == "Legacy vendor"


def test_stage75_graph_round_trips_with_cyclic_opportunity_calendar_links(client):
    s = _setup(client)
    opportunity = client.post("/api/expansions", json={
        "account_id": s["account"]["id"], "name": "Round-trip wave",
        "budget_owner_person_id": s["person"]["id"]}).json()
    calendar = client.post("/api/ask-calendars", json={
        "account_id": s["account"]["id"], "name": "Round-trip ask",
        "target_close_date": _day(60), "opportunity_id": opportunity["id"]}).json()
    client.patch(f"/api/expansions/{opportunity['id']}/qualification", json={
        "value_target_id": s["target"]["id"], "ask_calendar_id": calendar["id"]})
    agreement = client.post("/api/operational-agreements", json={
        "account_id": s["account"]["id"], "contract_version_id": s["contract"]["id"],
        "name": "Round trip agreement", "source_kind": "signed_paper",
        "source_reference_id": s["source"]["id"], "value_target_id": s["target"]["id"],
        "effective_on": _day(), "seat_band_min": 20, "seat_band_max": 30,
        "agreed_process": "Issue paper"}).json()
    plan = client.post("/api/growth-plans", json={
        "account_id": s["account"]["id"], "name": "Round trip plan",
        "target_seats": 600, "target_date": _day(120)}).json()
    line = client.post("/api/growth-plan-lines", json={
        "plan_id": plan["id"], "name": "Core line", "segment_id": s["segment"]["id"],
        "opportunity_id": opportunity["id"], "ask_calendar_id": calendar["id"],
        "seat_count": 100, "probability_author": "operator", "probability_assessed_on": _day(),
        "source_reference_id": s["source"]["id"], "client_visible": True}).json()
    bundle = client.get(f"/api/accounts/{s['account']['id']}/export").json()

    fd, path = tempfile.mkstemp(suffix=".sqlite"); os.close(fd)
    try:
        os.environ["VALENCE_OS_DB"] = path
        from app import portfolio_io
        from app.db import connect, run_migrations
        conn = connect(); run_migrations(conn)
        restored = portfolio_io.import_account(conn, bundle)
        assert restored["account_id"] == s["account"]["id"]
        assert conn.execute("SELECT qualification_ask_calendar_id FROM expansion_opportunities "
                            "WHERE id=?", (opportunity["id"],)).fetchone()[0] == calendar["id"]
        assert conn.execute("SELECT 1 FROM operational_agreements WHERE id=?", (agreement["id"],)).fetchone()
        assert conn.execute("SELECT 1 FROM growth_plan_lines WHERE id=?", (line["id"],)).fetchone()
        assert not conn.execute("PRAGMA foreign_key_check").fetchall()
        conn.close()
    finally:
        for suffix in ("", "-wal", "-shm"):
            try: os.unlink(path + suffix)
            except FileNotFoundError: pass


def test_client_visible_conversation_agreement_never_leaks_interaction_summary(client):
    s = _setup(client)
    interaction = client.post("/api/interactions", json={
        "account_id": s["account"]["id"], "program_id": s["program"]["id"],
        "type": "meeting", "summary": "SECRET internal meeting interpretation",
        "raw_notes": "SECRET raw notes"}).json()
    created = client.post("/api/operational-agreements", json={
        "account_id": s["account"]["id"], "contract_version_id": s["contract"]["id"],
        "name": "Conversation trigger", "source_kind": "agreed_conversation",
        "source_interaction_id": interaction["id"], "value_target_id": s["target"]["id"],
        "effective_on": _day(), "seat_band_min": 10, "seat_band_max": 20,
        "agreed_process": "Jointly review the next wave", "client_visible": True})
    assert created.status_code == 201, created.text
    mutual = client.get(f"/api/accounts/{s['account']['id']}/map").json()["artifact"]["markdown"]
    review = client.get(f"/api/accounts/{s['account']['id']}/value-review").json()["markdown"]
    assert "Conversation trigger" in mutual and "Conversation trigger" in review
    assert "SECRET" not in mutual and "SECRET" not in review
