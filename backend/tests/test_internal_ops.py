"""Adversarial acceptance tests for the internal operating layer."""
import os
import socket
import sqlite3
import tempfile
from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client():
    fd, path = tempfile.mkstemp(suffix=".sqlite"); os.close(fd)
    os.environ["VALENCE_OS_DB"] = path
    from app.main import app
    with TestClient(app) as c:
        yield c
    os.unlink(path)


def _day(offset=0):
    return (date.today() + timedelta(days=offset)).isoformat()


def _setup(c):
    account = c.post("/api/accounts", json={"name": "Internal Co"}).json()
    other = c.post("/api/accounts", json={"name": "Other Co"}).json()
    program = c.post("/api/programs", json={"account_id": account["id"], "name": "Core"}).json()
    client_person = c.post("/api/persons", json={"name": "Buyer", "account_id": account["id"]}).json()
    other_person = c.post("/api/persons", json={"name": "Other buyer", "account_id": other["id"]}).json()
    operator = c.post("/api/persons", json={"name": "Operator", "affiliation": "valence"}).json()
    interaction = c.post("/api/interactions", json={"account_id": account["id"], "program_id": program["id"],
        "occurred_on": _day(), "type": "meeting", "summary": "Budget review",
        "participant_ids": [client_person["id"], operator["id"]]}).json()
    return locals()


def test_forecast_soft_evidence_lock_and_cross_account_scope(client):
    s = _setup(client)
    period = client.post("/api/forecast-periods", json={"name": "Q4", "starts_on": _day(),
        "ends_on": _day(90), "cadence": "quarterly"}).json()
    opportunity = client.post("/api/expansions", json={"account_id": s["account"]["id"],
        "name": "DACH", "budget_owner_person_id": s["client_person"]["id"]}).json()
    entry_res = client.post(f"/api/forecast-periods/{period['id']}/entries", json={
        "account_id": s["account"]["id"], "opportunity_id": opportunity["id"], "category": "commit",
        "amount": 100000, "currency": "USD", "price_basis": "arr", "assessed_on": _day()})
    assert entry_res.status_code == 201, entry_res.text
    entry = entry_res.json()
    assert entry["id"] in {x["object_id"] for x in client.get("/api/search", params={"q": "DACH"}).json()["results"]}
    ev = client.get(f"/api/forecast-entries/{entry['id']}/evidence").json()
    assert ev["supported"] is False
    assert {r["rule_key"] for r in ev["missing"]} >= {"budget_allocated", "ask_date_in_period"}
    assert next(r for r in ev["rules"] if r["rule_key"] == "budget_owner_engaged_30d")["satisfied"] is True

    changed = client.post(f"/api/forecast-entries/{entry['id']}/category", json={
        "category": "best_case", "driver": "Correcting an overstated call"})
    assert changed.status_code == 200
    change_event = client.app.state.conn.execute(
        "SELECT id FROM forecast_change_events WHERE entry_id=? ORDER BY changed_at DESC,created_at DESC LIMIT 1",
        (entry["id"],)).fetchone()
    corrected = client.post(f"/api/forecast-entries/{entry['id']}/category", json={
        "category": "commit", "driver": "Correction: evidence was confirmed", "corrects_event_id": change_event["id"]})
    assert corrected.status_code == 200
    assert client.app.state.conn.execute(
        "SELECT 1 FROM forecast_change_events WHERE entry_id=? AND corrects_event_id=?",
        (entry["id"], change_event["id"])).fetchone()

    other_contract = client.post("/api/contracts", json={"account_id": s["other"]["id"],
        "version_label": "v1", "renewal_date": _day(60)}).json()
    bad = client.post(f"/api/forecast-periods/{period['id']}/entries", json={
        "account_id": s["account"]["id"], "contract_version_id": other_contract["id"],
        "category": "pipeline", "assessed_on": _day()})
    assert bad.status_code in (409, 422)

    assert client.post(f"/api/forecast-periods/{period['id']}/lock").status_code == 200
    # The Day-One snapshot locks, not the live call. Movement must remain possible until close.
    assert client.post(f"/api/forecast-entries/{entry['id']}/category", json={
        "category": "pipeline", "driver": "Scope changed"}).status_code == 200
    submission = client.post(f"/api/forecast-periods/{period['id']}/submissions")
    assert submission.status_code == 201, submission.text
    assert submission.json()["submission"]["baseline_kind"] == "opening"
    assert submission.json()["movement"][0]["category_before"] == "commit"
    opening = client.app.state.conn.execute(
        "SELECT category FROM forecast_opening_lines WHERE entry_id=?", (entry["id"],)
    ).fetchone()
    assert opening["category"] == "commit"


def test_internal_ask_escalation_snapshot_and_today(client, monkeypatch):
    s = _setup(client)
    functions = client.get("/api/internal-functions").json()
    data_fn = next(x for x in functions if x["name"] == "Data")
    ask = client.post(f"/api/accounts/{s['account']['id']}/internal-asks", json={
        "need": "Cohort cut", "success_condition": "CSV attached", "ask_type": "data_request",
        "requested_by_person_id": s["operator"]["id"], "requested_from_function_id": data_fn["id"],
        "needed_by": _day(-2)}).json()
    queue = client.get("/api/queue").json()
    assert sum(x["object_id"] == ask["id"] for x in queue["items"]) == 1
    def outbound_forbidden(*_args, **_kwargs):
        raise AssertionError("internal escalation attempted an outbound connection")
    monkeypatch.setattr(socket.socket, "connect", outbound_forbidden)
    escalation = client.post(f"/api/internal-asks/{ask['id']}/escalations", json={"severity": "high"}).json()
    original = escalation["threshold_business_hours"]
    client.app.state.conn.execute("UPDATE escalation_defaults SET threshold_business_hours=99 WHERE id=?", (escalation["default_id"],))
    client.app.state.conn.commit()
    stored = client.app.state.conn.execute("SELECT threshold_business_hours FROM escalation_instances WHERE id=?", (escalation["id"],)).fetchone()
    assert stored["threshold_business_hours"] == original
    with pytest.raises(sqlite3.IntegrityError, match="applied escalation rules are immutable"):
        client.app.state.conn.execute("UPDATE escalation_instances SET threshold_business_hours=77 WHERE id=?", (escalation["id"],))
    assert "Requested action" in escalation["suggested_note"]


def test_account_level_review_commitments_search_export_and_no_surprises(client):
    s = _setup(client)
    source = client.post("/api/source-references", json={"label": "Leadership review note"}).json()
    review = client.post(f"/api/accounts/{s['account']['id']}/reviews", json={
        "review_type": "quarterly", "scheduled_on": _day(7), "participant_ids": [s["operator"]["id"]]}).json()
    commitment = client.post("/api/commitments", json={"account_id": s["account"]["id"],
        "account_review_id": review["id"], "commitment_class": "leadership_to_operator",
        "description": "Fund exec touch", "responsible_party_id": s["operator"]["id"],
        "internal_owner_id": s["operator"]["id"], "due_date": _day(-1),
        "source_reference_id": source["id"]})
    assert commitment.status_code == 201, commitment.text
    decision = client.post("/api/decisions", json={"account_id": s["account"]["id"],
        "description": "Use annual pricing", "decided_on": _day(), "source_reference_id": source["id"]})
    assert decision.status_code == 201, decision.text
    execution = client.get(f"/api/accounts/{s['account']['id']}/execution").json()
    assert commitment.json()["id"] in {x["id"] for x in execution["commitments"]}
    assert decision.json()["id"] in {x["id"] for x in execution["decisions"]}
    bundle = client.get(f"/api/accounts/{s['account']['id']}/export").json()
    assert commitment.json()["id"] in {x["id"] for x in bundle["tables"]["commitments"]}
    assert decision.json()["id"] in {x["id"] for x in bundle["tables"]["decisions"]}
    assert commitment.json()["id"] in {x["object_id"] for x in client.get("/api/queue").json()["items"]}

    # Legacy red with no governed register origin must block upward reporting.
    conn = client.app.state.conn
    conn.execute("UPDATE accounts SET commercial_status='off_track' WHERE id=?", (s["account"]["id"],)); conn.commit()
    blocked = client.post("/api/internal-reports/monthly_portfolio_brief/documents")
    assert blocked.status_code == 409
    other_fn = next(x for x in client.get("/api/internal-functions").json() if x["name"] == "Other")
    leadership_ask = client.post(f"/api/accounts/{s['account']['id']}/internal-asks", json={
        "need": "Choose pricing exception", "success_condition": "Decision recorded",
        "requested_by_person_id": s["operator"]["id"], "requested_from_function_id": other_fn["id"],
        "needed_by": _day(2)}).json()
    assessment = client.post(f"/api/accounts/{s['account']['id']}/status-assessments", json={
        "dimension": "commercial", "value": "off_track", "rationale": "Pricing decision blocked",
        "recovery_owner_person_id": s["operator"]["id"], "recovery_action": "Bring options",
        "recovery_due_on": _day(3), "leadership_ask_id": leadership_ask["id"],
        "assessed_on": _day()})
    assert assessment.status_code == 201, assessment.text
    assert client.post("/api/internal-reports/monthly_portfolio_brief/documents").status_code == 201

    assert client.post(f"/api/accounts/{s['account']['id']}/operator-views", json={
        "body": "The account can grow if leadership resolves pricing before the renewal window.",
        "assessed_on": _day()}).status_code == 201
    for kind in ("internal_account_brief", "internal_review_packet", "internal_challenge_sheet"):
        generated = client.post(f"/api/account-reviews/{review['id']}/documents/{kind}")
        assert generated.status_code == 201, generated.text
        document_id = generated.json()["document"]["id"]
        assert conn.execute("SELECT COUNT(*) FROM generated_document_sources WHERE document_id=?", (document_id,)).fetchone()[0] > 0

    analytics = client.get("/api/portfolio/internal-analytics").json()
    assert {"escalations", "review_commitments", "exec_touch_coverage", "feedback_loops"} <= set(analytics)

    # Row-level restore guard: neither record depends on a program to survive or resolve scope.
    fd, restored_path = tempfile.mkstemp(suffix=".sqlite"); os.close(fd)
    try:
        os.environ["VALENCE_OS_DB"] = restored_path
        from app import portfolio_io, search
        from app.db import connect, run_migrations
        restored = connect(); run_migrations(restored)
        full_bundle = client.get(f"/api/accounts/{s['account']['id']}/export").json()
        portfolio_io.import_account(restored, full_bundle)
        assert commitment.json()["id"] in {r["object_id"] for r in search.search(restored, "Fund exec")}
        assert decision.json()["id"] in {r["object_id"] for r in search.search(restored, "annual pricing")}
        assert restored.execute("SELECT source_reference_id FROM commitments WHERE id=?", (commitment.json()["id"],)).fetchone()[0] == source["id"]
        restored_decision = restored.execute("SELECT account_id,program_id FROM decisions WHERE id=?", (decision.json()["id"],)).fetchone()
        assert tuple(restored_decision) == (s["account"]["id"], None)
        assert restored.execute("SELECT leadership_ask_id FROM account_status_assessments WHERE id=?", (assessment.json()["assessment"]["id"],)).fetchone()[0] == leadership_ask["id"]
        restored.close()
    finally:
        os.unlink(restored_path)


def test_roster_feedback_two_loops_and_cross_account_guards(client):
    s = _setup(client)
    roster = client.post(f"/api/accounts/{s['account']['id']}/internal-roster", json={
        "person_id": s["operator"]["id"], "role": "account_lead", "standing_responsibilities": "Run account",
        "coverage_type": "primary", "active_from": _day()})
    assert roster.status_code == 201
    with pytest.raises(sqlite3.IntegrityError, match="roster members must be Valence"):
        client.app.state.conn.execute("UPDATE account_internal_roster SET person_id=? WHERE id=?", (s["client_person"]["id"], roster.json()["id"]))
    rejected = client.post(f"/api/accounts/{s['account']['id']}/internal-roster", json={
        "person_id": s["client_person"]["id"], "role": "advisor", "standing_responsibilities": "Wrong boundary",
        "coverage_type": "backup", "active_from": _day()})
    assert rejected.status_code == 422

    theme = client.post("/api/product-feedback", json={"title": "Localized nudges",
        "problem_statement": "Managers need nudges in local languages", "feedback_type": "localization"}).json()
    occurrence = client.post(f"/api/product-feedback/{theme['id']}/occurrences", json={
        "account_id": s["account"]["id"], "stakeholder_person_id": s["client_person"]["id"],
        "source_interaction_id": s["interaction"]["id"], "source_span": "Need German nudges",
        "captured_on": _day()})
    assert occurrence.status_code == 201, occurrence.text
    other_interaction = client.post("/api/interactions", json={
        "account_id": s["other"]["id"], "occurred_on": _day(), "type": "meeting",
        "summary": "Localized workflow review", "participant_ids": [s["other_person"]["id"], s["operator"]["id"]],
    }).json()
    second_occurrence = client.post(f"/api/product-feedback/{theme['id']}/occurrences", json={
        "account_id": s["other"]["id"], "stakeholder_person_id": s["other_person"]["id"],
        "source_interaction_id": other_interaction["id"], "source_span": "Need French nudges",
        "captured_on": _day(),
    })
    assert second_occurrence.status_code == 201, second_occurrence.text
    aggregate = next(x for x in client.get("/api/product-feedback").json() if x["id"] == theme["id"])
    assert aggregate["account_count"] == 2
    assert roster.json()["id"] in {x["object_id"] for x in client.get("/api/search", params={"q": "Run account"}).json()["results"]}
    assert occurrence.json()["id"] in {x["object_id"] for x in client.get("/api/search", params={"q": "German nudges"}).json()["results"]}
    touch = client.post(f"/api/product-feedback-occurrences/{occurrence.json()['id']}/touches", json={
        "touch_type": "acknowledgment", "interaction_id": s["interaction"]["id"]})
    assert touch.status_code == 201
    shipped = client.post(f"/api/product-feedback/{theme['id']}/status", json={
        "status": "shipped", "reason": "Released", "product_reference": "release-42"})
    assert shipped.status_code == 200
    queue = client.get("/api/queue").json()["items"]
    assert any(x["trigger_type"] == "feedback_resolution" and x["object_id"] == occurrence.json()["id"] for x in queue)
    resolution = client.post(f"/api/product-feedback-occurrences/{occurrence.json()['id']}/touches", json={
        "touch_type": "resolution", "interaction_id": s["interaction"]["id"]})
    assert resolution.status_code == 201
    queue = client.get("/api/queue").json()["items"]
    assert not any(x["trigger_type"] in ("feedback_acknowledgment", "feedback_resolution") and x["object_id"] == occurrence.json()["id"] for x in queue)

    for path in (f"/api/accounts/{s['account']['id']}/coverage-brief",
                 f"/api/accounts/{s['account']['id']}/call-brief?roster_id={roster.json()['id']}",
                 f"/api/accounts/{s['account']['id']}/return-brief?starts_on={_day(-7)}&ends_on={_day()}"):
        generated = client.get(path)
        assert generated.status_code == 200, generated.text
        document_id = generated.json()["document"]["id"]
        assert client.app.state.conn.execute("SELECT COUNT(*) FROM generated_document_sources WHERE document_id=?", (document_id,)).fetchone()[0] > 0
    with pytest.raises(sqlite3.IntegrityError, match="source type is not allow-listed"):
        client.app.state.conn.execute("INSERT INTO generated_document_sources(id,document_id,record_type,record_id,inclusion_reason,created_at) VALUES ('bad-source',?,'arbitrary_table','bad','bad','now')", (document_id,))

    # Timer-generated internal outputs retain an immutable source snapshot too.
    from app import generators
    weekly = generators._weekly_team_update(client.app.state.conn, {"recurring": False})
    assert weekly["accounts_covered"] >= 1
    assert client.app.state.conn.execute("SELECT COUNT(*) FROM generated_document_sources WHERE document_id=?", (weekly["document_id"],)).fetchone()[0] > 0


def test_forecast_rollup_separates_units_computes_closed_and_discloses_gaps(client):
    s = _setup(client)
    period = client.post("/api/forecast-periods", json={"name": "Operating quarter", "starts_on": _day(-5),
        "ends_on": _day(90), "cadence": "quarterly", "scenario_type": "review-rollup"}).json()
    opportunities = [client.post("/api/expansions", json={
        "account_id": s["account"]["id"], "name": name}).json() for name in ("US", "DACH", "Unknown units")]
    entries = []
    for opportunity, values in zip(opportunities, (
        {"amount": 100, "currency": "USD", "price_basis": "arr", "probability": .5,
         "probability_rationale": "Qualified"},
        {"amount": 200, "currency": "EUR", "price_basis": "arr"},
        {"amount": 300},
    )):
        response = client.post(f"/api/forecast-periods/{period['id']}/entries", json={
            "account_id": s["account"]["id"], "opportunity_id": opportunity["id"],
            "category": "pipeline", "assessed_on": _day(), **values,
        })
        assert response.status_code == 201, response.text
        entries.append(response.json())

    assert client.post(f"/api/expansions/{opportunities[0]['id']}/close", json={
        "outcome": "won", "outcome_reason": "Signed"}).status_code == 200
    actual = client.post("/api/revenue-events", json={
        "account_id": s["account"]["id"], "opportunity_id": opportunities[0]["id"],
        "kind": "expansion", "amount": 125, "currency": "USD", "price_basis": "arr",
        "effective_on": _day(), "reason": "Booked",
    })
    assert actual.status_code == 201, actual.text
    submission = client.post(f"/api/forecast-periods/{period['id']}/submissions")
    assert submission.status_code == 201, submission.text
    body = submission.json()
    groups = {(x["currency"], x["price_basis"]): x for x in body["totals"]}
    assert set(groups) == {("USD", "arr"), ("EUR", "arr")}
    assert groups[("USD", "arr")]["closed"] == 125
    assert groups[("USD", "arr")]["pipeline"] == 0
    assert groups[("USD", "arr")]["weighted_open"] == 0
    assert groups[("EUR", "arr")]["missing_probability_count"] == 1
    assert body["amount_exclusions"] == [{"entry_id": entries[2]["id"],
                                           "reason": "forecast currency or price basis is unknown"}]
    assert body["weighting_exclusions"] == [{"entry_id": entries[1]["id"],
                                              "reason": "probability is not recorded"}]
    assert "Closed 125.00" in body["document"]["body_markdown"]

    old_contract = client.post("/api/contracts", json={"account_id": s["account"]["id"],
        "version_label": "old", "renewal_date": _day(60)}).json()
    client.post("/api/contracts", json={"account_id": s["account"]["id"],
        "version_label": "current", "renewal_date": _day(70), "supersedes_id": old_contract["id"]})
    historical = client.post(f"/api/forecast-periods/{period['id']}/entries", json={
        "account_id": s["account"]["id"], "contract_version_id": old_contract["id"],
        "category": "pipeline", "assessed_on": _day(),
    })
    assert historical.status_code == 422
    with pytest.raises(sqlite3.IntegrityError, match="renewal contracts must be current"):
        client.app.state.conn.execute(
            "INSERT INTO forecast_entries(id,period_id,account_id,contract_version_id,category,author,assessed_on,created_at,updated_at) "
            "VALUES ('bad-old-contract',?,?,?,'pipeline','test',?,?,?)",
            (period["id"], s["account"]["id"], old_contract["id"], _day(), _day(), _day()),
        )


def test_calibration_displays_closed_not_closed_and_unresolved(client):
    s = _setup(client)
    period = client.post("/api/forecast-periods", json={"name": "Calibration A", "starts_on": _day(-10),
        "ends_on": _day(10), "cadence": "custom", "scenario_type": "calibration-a"}).json()
    opportunities = [client.post("/api/expansions", json={
        "account_id": s["account"]["id"], "name": name}).json() for name in ("Won", "Lost", "Missing outcome evidence")]
    for opportunity in opportunities:
        assert client.post(f"/api/forecast-periods/{period['id']}/entries", json={
            "account_id": s["account"]["id"], "opportunity_id": opportunity["id"],
            "category": "commit", "amount": 10, "currency": "USD", "price_basis": "arr",
            "assessed_on": _day(),
        }).status_code == 201
    assert client.post(f"/api/forecast-periods/{period['id']}/lock").status_code == 200
    assert client.post(f"/api/expansions/{opportunities[0]['id']}/close", json={
        "outcome": "won", "outcome_reason": "Signed"}).status_code == 200
    assert client.post("/api/revenue-events", json={"account_id": s["account"]["id"],
        "opportunity_id": opportunities[0]["id"], "kind": "expansion", "amount": 10,
        "currency": "USD", "price_basis": "arr", "effective_on": _day()}).status_code == 201
    assert client.post(f"/api/expansions/{opportunities[1]['id']}/close", json={
        "outcome": "lost", "outcome_reason": "No budget"}).status_code == 200
    assert client.post(f"/api/expansions/{opportunities[2]['id']}/close", json={
        "outcome": "won", "outcome_reason": "Signed but booking is missing"}).status_code == 200
    closed = client.post(f"/api/forecast-periods/{period['id']}/close")
    assert closed.status_code == 200, closed.text
    bucket = closed.json()["calibration"]["categories"]["commit"]
    assert (bucket["closed"], bucket["not_closed"], bucket["unresolved"], bucket["opening"]) == (1, 1, 1, 3)
    assert bucket["display"] == "1 closed · 1 not closed · 1 unresolved of 3"
    assert client.post(f"/api/forecast-periods/{period['id']}/submissions").status_code == 409

    second = client.post("/api/forecast-periods", json={"name": "Calibration B", "starts_on": _day(11),
        "ends_on": _day(30), "cadence": "custom", "scenario_type": "calibration-b"}).json()
    second_opportunity = client.post("/api/expansions", json={
        "account_id": s["account"]["id"], "name": "Best Case unresolved"}).json()
    assert client.post(f"/api/forecast-periods/{second['id']}/entries", json={
        "account_id": s["account"]["id"], "opportunity_id": second_opportunity["id"],
        "category": "best_case", "amount": 20, "currency": "EUR", "price_basis": "tcv",
        "assessed_on": _day(), "unresolved_conditions": "Legal approval",
    }).status_code == 201
    assert client.post(f"/api/forecast-periods/{second['id']}/lock").status_code == 200
    assert client.post(f"/api/forecast-periods/{second['id']}/close").status_code == 200
    periods = client.get("/api/portfolio/internal-analytics").json()["forecast_calibration"]
    assert len(periods) == 2
    second_bucket = next(x for x in periods if x["period"]["id"] == second["id"])["calibration"]["categories"]["best_case"]
    assert second_bucket["display"] == "0 closed · 0 not closed · 1 unresolved of 1"


def test_monthly_report_separates_headwinds_and_tracks_reverse_no_surprises(client):
    s = _setup(client)
    risk = client.post("/api/risks", json={"program_id": s["program"]["id"],
        "description": "Works council blocks rollout", "severity": "high", "is_blocker": True})
    assert risk.status_code == 201, risk.text
    contract = client.post("/api/contracts", json={"account_id": s["account"]["id"],
        "version_label": "v1", "renewal_date": _day(60)}).json()
    churn = client.post("/api/revenue-events", json={"account_id": s["account"]["id"],
        "contract_version_id": contract["id"], "kind": "churn", "amount": -250000,
        "currency": "USD", "price_basis": "arr", "effective_on": _day(), "reason": "Lost region"})
    assert churn.status_code == 201, churn.text
    preview = client.get("/api/internal-reports/monthly_portfolio_brief/preview").json()
    assert preview["wins"] == []
    assert [x["kind"] for x in preview["revenue_headwinds"]] == ["churn"]
    origin = next(x for x in preview["validation"]["included_red_origins"] if x["id"] == risk.json()["id"])
    exclusion = client.post("/api/internal-reports/red-origin-exclusions", json={
        "origin_type": origin["type"], "origin_id": origin["id"],
        "reason": "Covered in the contractual loss section", "expires_on": _day(7),
    })
    assert exclusion.status_code == 201, exclusion.text
    generated = client.post("/api/internal-reports/monthly_portfolio_brief/documents")
    assert generated.status_code == 201, generated.text
    markdown = generated.json()["document"]["body_markdown"]
    wins_section = markdown.split("## Wins worth repeating upward", 1)[1].split("## Revenue headwinds", 1)[0]
    assert "churn" not in wins_section.lower()
    assert "churn — -250000" in markdown.lower()
    assert "covered in the contractual loss section" in markdown.lower()
    manifest_types = {r["record_type"] for r in client.app.state.conn.execute(
        "SELECT record_type FROM generated_document_sources WHERE document_id=?",
        (generated.json()["document"]["id"],),
    )}
    assert {"revenue_event", "report_origin_exclusion"} <= manifest_types
    frozen_sources = list(client.app.state.conn.execute(
        "SELECT record_type,record_id,inclusion_reason FROM generated_document_sources "
        "WHERE document_id=? ORDER BY record_type,record_id,inclusion_reason",
        (generated.json()["document"]["id"],),
    ))
    client.post("/api/risks", json={"program_id": s["program"]["id"],
        "description": "Late-breaking risk", "severity": "high"})
    stored = client.app.state.conn.execute(
        "SELECT body_markdown FROM generated_documents WHERE id=?", (generated.json()["document"]["id"],)
    ).fetchone()
    assert stored["body_markdown"] == markdown
    assert list(client.app.state.conn.execute(
        "SELECT record_type,record_id,inclusion_reason FROM generated_document_sources "
        "WHERE document_id=? ORDER BY record_type,record_id,inclusion_reason",
        (generated.json()["document"]["id"],),
    )) == frozen_sources


def test_review_hold_and_ask_terminal_rules(client):
    s = _setup(client)
    review = client.post(f"/api/accounts/{s['account']['id']}/reviews", json={
        "review_type": "quarterly", "scheduled_on": _day(), "participant_ids": [s["operator"]["id"]],
    }).json()
    other_interaction = client.post("/api/interactions", json={"account_id": s["other"]["id"],
        "occurred_on": _day(), "type": "meeting", "summary": "Wrong account"}).json()
    assert client.post(f"/api/account-reviews/{review['id']}/hold", json={
        "held_on": _day(), "source_interaction_id": other_interaction["id"]}).status_code == 422
    assert client.post(f"/api/account-reviews/{review['id']}/hold", json={
        "held_on": _day(), "source_interaction_id": s["interaction"]["id"]}).status_code == 200
    held = client.get(f"/api/accounts/{s['account']['id']}/reviews").json()[0]
    assert held["status"] == "held"
    assert {x["id"] for x in held["participants"]} == {s["operator"]["id"]}

    invalid_amber = client.post(f"/api/accounts/{s['account']['id']}/status-assessments", json={
        "dimension": "delivery", "value": "at_risk", "rationale": "Slipping", "assessed_on": _day(),
    })
    assert invalid_amber.status_code == 422
    invalid_red = client.post(f"/api/accounts/{s['account']['id']}/status-assessments", json={
        "dimension": "commercial", "value": "off_track", "rationale": "Blocked", "assessed_on": _day(),
        "recovery_owner_person_id": s["operator"]["id"], "recovery_action": "Escalate",
        "recovery_due_on": _day(3),
    })
    assert invalid_red.status_code == 422

    assert client.post(f"/api/accounts/{s['account']['id']}/operator-views", json={
        "body": "Older view must not render.", "assessed_on": _day(-2)}).status_code == 201
    assert client.post(f"/api/accounts/{s['account']['id']}/operator-views", json={
        "body": "Latest view is the point of view.", "assessed_on": _day()}).status_code == 201
    brief = client.post(f"/api/account-reviews/{review['id']}/documents/internal_account_brief")
    assert brief.status_code == 201, brief.text
    assert "Latest view is the point of view." in brief.json()["document"]["body_markdown"]
    assert "Older view must not render." not in brief.json()["document"]["body_markdown"]

    other_function = next(x for x in client.get("/api/internal-functions").json() if x["name"] == "Other")
    ask_response = client.post(f"/api/accounts/{s['account']['id']}/internal-asks", json={
        "need": "Approve exception", "success_condition": "Decision attached", "ask_type": "pricing",
        "requested_by_person_id": s["operator"]["id"],
        "requested_from_function_id": other_function["id"], "needed_by": _day(),
    })
    assert ask_response.status_code == 201, ask_response.text
    ask = ask_response.json()
    assert client.post(f"/api/internal-asks/{ask['id']}/status", json={"status": "delivered"}).status_code == 422
    assert client.post(f"/api/internal-asks/{ask['id']}/status", json={
        "status": "declined", "reason": "Margin floor"}).status_code == 200
    assert client.post(f"/api/internal-asks/{ask['id']}/status", json={"status": "raised"}).status_code == 422
    assert client.post(f"/api/internal-asks/{ask['id']}/status", json={
        "status": "raised", "reason": "New commercial option"}).status_code == 200

    columns = {r["name"] for table in ("product_feedback_items", "product_feedback_occurrences")
               for r in client.app.state.conn.execute(f"PRAGMA table_info({table})")}
    assert not {"usage", "usage_count", "product_usage", "last_active_at"} & columns


def test_today_derives_policy_commit_warning_and_delivered_evidence_gap(client):
    s = _setup(client)
    period = client.post("/api/forecast-periods", json={"name": "Ask urgency", "starts_on": _day(-1),
        "ends_on": _day(30), "cadence": "monthly", "scenario_type": "ask-urgency"}).json()
    opportunity = client.post("/api/expansions", json={
        "account_id": s["account"]["id"], "name": "Unsupported commit"}).json()
    entry = client.post(f"/api/forecast-periods/{period['id']}/entries", json={
        "account_id": s["account"]["id"], "opportunity_id": opportunity["id"],
        "category": "commit", "amount": 50, "currency": "USD", "price_basis": "arr",
        "assessed_on": _day(),
    }).json()
    other_function = next(x for x in client.get("/api/internal-functions").json() if x["name"] == "Other")
    ask = client.post(f"/api/accounts/{s['account']['id']}/internal-asks", json={
        "need": "Confirm exec approval", "success_condition": "Approval linked", "ask_type": "general",
        "requested_by_person_id": s["operator"]["id"], "requested_from_function_id": other_function["id"],
        "forecast_entry_id": entry["id"], "needed_by": _day(),
    }).json()
    client.app.state.conn.execute(
        "UPDATE internal_asks SET created_at=datetime('now','-3 days') WHERE id=?", (ask["id"],)
    )
    client.app.state.conn.commit()
    items = client.get("/api/queue").json()["items"]
    triggers = {x["trigger_type"] for x in items if x["object_id"] == ask["id"]}
    assert {"unacknowledged_internal_ask", "commit_ask_warning"} <= triggers
    escalation = client.post(f"/api/internal-asks/{ask['id']}/escalations", json={"severity": "high"})
    assert escalation.status_code == 201, escalation.text
    assert escalation.json()["default_id"] == "esc-general-high"
    assert escalation.json()["severity"] == "high"
    assert escalation.json()["threshold_business_hours"] == 8
    delivered = client.post(f"/api/internal-asks/{ask['id']}/status", json={
        "status": "delivered", "completion_note": "Approval received",
    })
    assert delivered.status_code == 200, delivered.text
    items = client.get("/api/queue").json()["items"]
    triggers = {x["trigger_type"] for x in items if x["object_id"] == ask["id"]}
    assert triggers == {"delivered_ask_evidence_gap"}
