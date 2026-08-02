"""Stage 9 adversarial contracts: no invented analytics and no automatic learning mutation."""
import os
import tempfile

import pytest
from fastapi.testclient import TestClient

from conftest import utc_day


@pytest.fixture()
def client(monkeypatch):
    fd, path = tempfile.mkstemp(suffix=".sqlite"); os.close(fd)
    monkeypatch.setenv("VALENCE_OS_DB", path)
    monkeypatch.setenv("VALENCE_OS_WORKER", "0")
    from app.main import app
    with TestClient(app) as c:
        yield c
    for suffix in ("", "-wal", "-shm"):
        try: os.unlink(path + suffix)
        except FileNotFoundError: pass


def _day(offset=0):
    return utc_day(offset)


def _shape(client, name, use_case_id, tag_id):
    account = client.post("/api/accounts", json={"name": name}).json()
    partition = client.post("/api/population-partitions", json={
        "account_id": account["id"], "total_fte": 1000,
        "fte_source": "synthetic", "fte_as_of": _day()}).json()
    segment = client.post("/api/population-segments", json={
        "partition_id": partition["id"], "name": "Core", "headcount": 900,
        "headcount_source": "synthetic", "headcount_as_of": _day()}).json()
    view = client.post("/api/population-views", json={
        "account_id": account["id"], "name": "Frontline managers", "estimated_headcount": 300,
        "headcount_source": "synthetic", "headcount_as_of": _day(),
        "segment_ids": [segment["id"]], "tag_ids": [tag_id]}).json()
    cell = client.post("/api/whitespace-cells", json={
        "account_id": account["id"], "view_id": view["id"], "use_case_id": use_case_id}).json()
    changed = client.post(f"/api/whitespace-cells/{cell['id']}/set-fact", json={
        "fact": "evidence_state", "value": "measured", "reason": "Synthetic pilot evidence"})
    assert changed.status_code == 200 and changed.json()["state"] == "proven"
    history = client.get(f"/api/whitespace-cells/{cell['id']}").json()["history"][0]
    return {"account": account, "segment": segment, "view": view, "cell": cell, "history": history}


def _entry(client, shape, tag_id=None, motion="Sponsor-led manager pilot"):
    payload = {
        "transition_history_id": shape["history"]["id"], "motion_run": motion,
        "evidence_summary": "Activation cleared the agreed bar",
        "message_summary": "Start where managers already have a live moment",
        "message_layer": "operational", "motion_started_on": _day(-20),
        "what_worked": "Sponsor carried the readout", "what_differently": "Start procurement earlier"}
    if tag_id:
        payload["tag_ids"] = [tag_id]
    result = client.post("/api/playbook-entries", json=payload)
    assert result.status_code == 201, result.text
    return result.json()


def _segment_shape(client, name, use_case_id):
    account = client.post("/api/accounts", json={"name": name}).json()
    partition = client.post("/api/population-partitions", json={
        "account_id": account["id"], "total_fte": 500,
        "fte_source": "synthetic", "fte_as_of": _day()}).json()
    segment = client.post("/api/population-segments", json={
        "partition_id": partition["id"], "name": "Account-specific population", "headcount": 500,
        "headcount_source": "synthetic", "headcount_as_of": _day()}).json()
    cell = client.post("/api/whitespace-cells", json={
        "account_id": account["id"], "segment_id": segment["id"],
        "use_case_id": use_case_id}).json()
    changed = client.post(f"/api/whitespace-cells/{cell['id']}/set-fact", json={
        "fact": "evidence_state", "value": "measured", "reason": "Synthetic evidence"})
    assert changed.status_code == 200 and changed.json()["state"] == "proven"
    history = client.get(f"/api/whitespace-cells/{cell['id']}").json()["history"][0]
    return {"account": account, "segment": segment, "cell": cell, "history": history}


def test_transition_snapshots_prompt_once_and_matches_explain_their_rank(client):
    tag = client.post("/api/audience-tags", json={"name": "Frontline", "slug": "frontline"}).json()
    use_case = client.post("/api/use-cases", json={"name": "Change", "slug": "change"}).json()
    one = _shape(client, "One", use_case["id"], tag["id"])
    entry = _entry(client, one, tag["id"])
    assert client.post("/api/playbook-entries", json={
        "transition_history_id": one["history"]["id"], "motion_run": "Duplicate"}).status_code == 409
    pending = client.get("/api/playbook-entries").json()["pending"]
    assert one["history"]["id"] not in {row["id"] for row in pending}
    matches = client.get(f"/api/whitespace-cells/{one['cell']['id']}/playbook-matches").json()
    assert matches["matches"][0]["id"] == entry["id"]
    assert matches["matches"][0]["match_rank"] == 1
    assert "Exact use case" in matches["matches"][0]["match_reason"]


def test_account_specific_use_cases_are_visibly_excluded_from_cross_account_matching(client):
    tag = client.post("/api/audience-tags", json={"name": "Executives", "slug": "executives"}).json()
    account = client.post("/api/accounts", json={"name": "Local"}).json()
    use_case = client.post("/api/use-cases", json={
        "name": "Local moment", "slug": "local-moment", "account_id": account["id"]}).json()
    partition = client.post("/api/population-partitions", json={"account_id": account["id"],
        "total_fte": 500, "fte_source": "synthetic", "fte_as_of": _day()}).json()
    segment = client.post("/api/population-segments", json={"partition_id": partition["id"],
        "name": "Core", "headcount": 500, "headcount_source": "synthetic", "headcount_as_of": _day()}).json()
    view = client.post("/api/population-views", json={"account_id": account["id"], "name": "Execs",
        "estimated_headcount": 50, "headcount_source": "synthetic", "headcount_as_of": _day(),
        "segment_ids": [segment["id"]], "tag_ids": [tag["id"]]}).json()
    cell = client.post("/api/whitespace-cells", json={"account_id": account["id"],
        "view_id": view["id"], "use_case_id": use_case["id"]}).json()
    result = client.get(f"/api/whitespace-cells/{cell['id']}/playbook-matches").json()
    assert result["cross_account_eligible"] is False and result["matches"] == []
    assert "Account-specific" in result["reason"]


def test_shape_tags_are_snapshotted_and_empty_sets_are_not_exact_matches(client):
    frontline = client.post("/api/audience-tags", json={
        "name": "Frontline", "slug": "frontline-snapshot"}).json()
    executives = client.post("/api/audience-tags", json={
        "name": "Executives", "slug": "executives-snapshot"}).json()
    use_case = client.post("/api/use-cases", json={
        "name": "Change snapshot", "slug": "change-snapshot"}).json()

    view_shape = _shape(client, "Tagged", use_case["id"], frontline["id"])
    entry = _entry(client, view_shape)  # no operator-supplied tag ids
    assert [tag["id"] for tag in entry["audience_tags"]] == [frontline["id"]]

    forged_shape = _shape(client, "Forged", use_case["id"], frontline["id"])
    forged = client.post("/api/playbook-entries", json={
        "transition_history_id": forged_shape["history"]["id"], "motion_run": "Wrong shape",
        "tag_ids": [executives["id"]]})
    assert forged.status_code == 422 and "derived" in forged.text

    segment_one = _segment_shape(client, "Segment one", use_case["id"])
    segment_two = _segment_shape(client, "Segment two", use_case["id"])
    segment_entry = _entry(client, segment_one)
    assert segment_entry["audience_tags"] == []
    matches = client.get(
        f"/api/whitespace-cells/{segment_two['cell']['id']}/playbook-matches").json()["matches"]
    matched = next(row for row in matches if row["id"] == segment_entry["id"])
    assert matched["match_rank"] == 3
    assert "unavailable" in matched["match_reason"]


def test_no_op_fact_history_never_becomes_a_playbook_transition(client):
    tag = client.post("/api/audience-tags", json={"name": "Managers no-op", "slug": "managers-no-op"}).json()
    use_case = client.post("/api/use-cases", json={"name": "Reviews no-op", "slug": "reviews-no-op"}).json()
    shape = _shape(client, "No-op", use_case["id"], tag["id"])
    repeated = client.post(f"/api/whitespace-cells/{shape['cell']['id']}/set-fact", json={
        "fact": "evidence_state", "value": "measured", "reason": "Evidence reconfirmed"})
    assert repeated.status_code == 200
    no_op = client.get(f"/api/whitespace-cells/{shape['cell']['id']}").json()["history"][0]
    assert no_op["derived_state_before"] == no_op["derived_state_after"] == "proven"
    pending = client.get("/api/playbook-entries").json()["pending"]
    assert no_op["id"] not in {row["id"] for row in pending}
    rejected = client.post("/api/playbook-entries", json={
        "transition_history_id": no_op["id"], "motion_run": "Nothing changed"})
    assert rejected.status_code == 422 and "real derived-state transition" in rejected.text


def test_velocity_uses_the_latest_proven_episode_before_funding(client):
    tag = client.post("/api/audience-tags", json={"name": "Managers episode", "slug": "managers-episode"}).json()
    use_case = client.post("/api/use-cases", json={"name": "Reviews episode", "slug": "reviews-episode"}).json()
    shape = _shape(client, "Episodes", use_case["id"], tag["id"])
    conn = client.app.state.conn
    conn.execute("UPDATE cell_state_history SET changed_on=? WHERE id=?",
                 (_day(-40), shape["history"]["id"]))
    client.post(f"/api/whitespace-cells/{shape['cell']['id']}/set-fact", json={
        "fact": "evidence_state", "value": "none", "reason": "Evidence expired"})
    regressed = client.get(f"/api/whitespace-cells/{shape['cell']['id']}").json()["history"][0]
    conn.execute("UPDATE cell_state_history SET changed_on=? WHERE id=?", (_day(-20), regressed["id"]))
    client.post(f"/api/whitespace-cells/{shape['cell']['id']}/set-fact", json={
        "fact": "evidence_state", "value": "measured", "reason": "Fresh evidence"})
    reproven = client.get(f"/api/whitespace-cells/{shape['cell']['id']}").json()["history"][0]
    conn.execute("UPDATE cell_state_history SET changed_on=? WHERE id=?", (_day(-10), reproven["id"]))

    plan = client.post("/api/growth-plans", json={"account_id": shape["account"]["id"],
        "name": "Episode plan", "target_seats": 800, "target_date": _day(180)}).json()
    line = client.post("/api/growth-plan-lines", json={"plan_id": plan["id"], "name": "Episode line",
        "view_id": shape["view"]["id"], "cell_id": shape["cell"]["id"], "seat_count": 200,
        "probability_author": "operator", "probability_assessed_on": _day(), "status": "funded"}).json()
    conn.execute("UPDATE growth_plan_lines SET funded_on=? WHERE id=?", (_day(-5), line["id"]))
    samples = client.get("/api/portfolio/commercial-analytics?window_days=90").json()["time_to_expansion"]
    assert samples["sample_count"] == 1
    assert samples["samples"][0]["proven_on"] == _day(-10)
    assert samples["median_days"] == 5


def test_portfolio_velocity_requires_explicit_cell_and_dated_funding(client):
    tag = client.post("/api/audience-tags", json={"name": "Managers", "slug": "managers"}).json()
    use_case = client.post("/api/use-cases", json={"name": "Reviews", "slug": "reviews"}).json()
    shape = _shape(client, "Velocity", use_case["id"], tag["id"])
    contract = client.post("/api/contracts", json={"account_id": shape["account"]["id"],
        "version_label": "FY27", "price": 100000, "seats": 100}).json()
    priced = client.patch(f"/api/contracts/{contract['id']}/revenue", json={
        "currency": "USD", "price_basis": "arr"})
    assert priced.status_code == 200 and priced.json()["derived_arr"] == 100000
    plan = client.post("/api/growth-plans", json={"account_id": shape["account"]["id"],
        "name": "Growth", "target_seats": 800, "target_date": _day(180)}).json()
    line = client.post("/api/growth-plan-lines", json={"plan_id": plan["id"], "name": "Manager line",
        "view_id": shape["view"]["id"], "cell_id": shape["cell"]["id"], "seat_count": 200,
        "seat_price_low": 10, "seat_price_high": 20, "seat_price_currency": "USD",
        "seat_price_basis": "annual_recurring",
        "probability_author": "operator", "probability_assessed_on": _day(), "status": "funded"})
    assert line.status_code == 201, line.text
    conn = client.app.state.conn
    conn.execute("UPDATE cell_state_history SET changed_on=? WHERE id=?", (_day(-30), shape["history"]["id"]))
    conn.execute("UPDATE growth_plan_lines SET funded_on=? WHERE id=?", (_day(-5), line.json()["id"]))
    analytics = client.get("/api/portfolio/commercial-analytics?window_days=90").json()
    assert analytics["time_to_expansion"]["sample_count"] == 1
    assert analytics["time_to_expansion"]["median_days"] == 25
    assert analytics["portfolio_account_count"] == 1
    revenue = analytics["revenue"]["accounts"][0]
    assert revenue["projected_expansion"]["low"] == 2000
    assert revenue["projected_expansion"]["high"] == 4000
    assert revenue["projected_ending_arr"]["low"] == 102000
    assert "blended" in analytics["revenue"]["note"].lower()


def test_repeated_success_needs_human_promotion_and_round_trips(client):
    tag = client.post("/api/audience-tags", json={"name": "Early career", "slug": "early-career"}).json()
    use_case = client.post("/api/use-cases", json={"name": "Onboarding", "slug": "onboarding"}).json()
    one = _shape(client, "One", use_case["id"], tag["id"])
    two = _shape(client, "Two", use_case["id"], tag["id"])
    e1, e2 = _entry(client, one, tag["id"]), _entry(client, two, tag["id"])
    assert e1["play_definition_id"] is None and e2["play_definition_id"] is None
    promoted = client.post(f"/api/playbook-entries/{e1['id']}/promote-play", json={
        "name": "Sponsor-led onboarding pilot", "action_template": "Run the proven sponsor-led wedge"})
    assert promoted.status_code == 201, promoted.text
    assert promoted.json()["evidence_count"] == 2
    assert set(promoted.json()["linked_entry_ids"]) == {e1["id"], e2["id"]}
    unrelated_use_case = client.post("/api/use-cases", json={
        "name": "Conflict", "slug": "conflict-unrelated"}).json()
    unrelated = _shape(client, "Unrelated", unrelated_use_case["id"], tag["id"])
    from app import stage9
    assert stage9.play_applies_to_cell(client.app.state.conn, promoted.json()["play"]["id"],
                                       one["cell"]["id"]) is True
    assert stage9.play_applies_to_cell(client.app.state.conn, promoted.json()["play"]["id"],
                                       unrelated["cell"]["id"]) is False
    message = client.post(f"/api/playbook-entries/{e1['id']}/promote-message", json={})
    assert message.status_code == 201, message.text

    bundle = client.get(f"/api/accounts/{one['account']['id']}/export").json()
    assert len(bundle["tables"]["playbook_entries"]) == 1
    assert len(bundle["tables"]["play_definitions"]) == 1
    assert len(bundle["tables"]["messaging_entries"]) == 1
    assert bundle["tables"]["playbook_entry_tags"] == [{"entry_id": e1["id"], "tag_id": tag["id"]}]

    fd, path = tempfile.mkstemp(suffix=".sqlite"); os.close(fd)
    try:
        os.environ["VALENCE_OS_DB"] = path
        from app import portfolio_io
        from app.db import connect, run_migrations
        conn = connect(); run_migrations(conn)
        portfolio_io.import_account(conn, bundle)
        restored = conn.execute("SELECT * FROM playbook_entries WHERE id=?", (e1["id"],)).fetchone()
        assert restored and restored["play_definition_id"] == promoted.json()["play"]["id"]
        assert conn.execute("SELECT tag_id FROM playbook_entry_tags WHERE entry_id=?",
                            (e1["id"],)).fetchone()[0] == tag["id"]
        assert not conn.execute("PRAGMA foreign_key_check").fetchall()
        conn.close()
    finally:
        for suffix in ("", "-wal", "-shm"):
            try: os.unlink(path + suffix)
            except FileNotFoundError: pass
