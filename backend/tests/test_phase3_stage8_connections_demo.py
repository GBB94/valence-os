"""Stage 8: executable connection governance and the Phase 3 end-to-end demo."""
from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from conftest import utc_day


@pytest.fixture()
def client(monkeypatch):
    fd, path = tempfile.mkstemp(suffix=".sqlite"); os.close(fd)
    monkeypatch.setenv("VALENCE_OS_DB", path)
    monkeypatch.setenv("VALENCE_OS_WORKER", "0")
    monkeypatch.delenv("EXTRACTOR_BACKEND", raising=False)
    monkeypatch.delenv("COPILOT_BACKEND", raising=False)
    monkeypatch.delenv("VALENCE_OS_REAL_CONNECTIONS_APPROVED", raising=False)
    monkeypatch.delenv("VALENCE_OS_REAL_CONNECTIONS_DECISION", raising=False)
    from app.main import app
    with TestClient(app) as test_client:
        yield test_client
    for suffix in ("", "-wal", "-shm"):
        try: os.unlink(path + suffix)
        except FileNotFoundError: pass


def _day(offset=0):
    return utc_day(offset)


def _post(client, path, body=None, status=201):
    response = client.post(path, json=body or {})
    assert response.status_code == status, f"{path}: {response.status_code} {response.text}"
    return response.json()


def test_registry_is_complete_documented_and_local_by_default(client):
    from app import connections
    snapshot = connections.registry_snapshot()
    ids = {row["id"] for row in snapshot["connections"]}
    assert ids == {
        "recording_source", "transcription_source", "email_provider", "calendar_provider",
            "enrichment_source", "headcount_source", "metric_source", "notification_channel",
            "llm_endpoint", "copilot_endpoint", "company_intel_source",
            "intel_extraction_endpoint", "file_storage", "hosting",
    }
    assert snapshot["approval"]["approved"] is False
    assert all(row["gate_status"] == "local" for row in snapshot["connections"])
    assert all(Path(__file__).parents[1].joinpath("app", "fixtures", fixture).exists()
               for row in snapshot["connections"] for fixture in row["fixtures"])

    registry_doc = Path(__file__).parents[2].joinpath("CONNECTIONS.md").read_text(encoding="utf-8")
    for connection_id in ids:
        assert f"`{connection_id}`" in registry_doc
    assert "VALENCE_OS_REAL_CONNECTIONS_APPROVED" in registry_doc
    assert "VALENCE_OS_REAL_CONNECTIONS_DECISION" in registry_doc

    operations = client.get("/api/operations").json()["connection_registry"]
    assert {row["id"] for row in operations["connections"]} == ids


def test_network_llm_mode_is_fail_closed_even_if_selected(monkeypatch, client):
    from app import connections, extractor
    monkeypatch.setenv("EXTRACTOR_BACKEND", "api")
    monkeypatch.delenv(connections.REAL_APPROVAL_ENV, raising=False)
    monkeypatch.delenv(connections.REAL_DECISION_ENV, raising=False)
    with pytest.raises(RuntimeError, match="data-governance gate"):
        extractor.get_extractor()
    account = _post(client, "/api/accounts", {"name": "Connection Gate Demo"})
    blocked = client.post("/api/extraction/run", json={
        "account_id": account["id"], "backend": "api", "transcript": "Synthetic input.",
    })
    assert blocked.status_code == 502 and "data-governance gate" in blocked.json()["detail"]

    monkeypatch.setenv(connections.REAL_APPROVAL_ENV, "1")
    with pytest.raises(RuntimeError, match="data-governance gate"):
        extractor.get_extractor()  # flag without the logged decision is still insufficient

    monkeypatch.setenv(connections.REAL_DECISION_ENV, "D-REAL-CONNECTION-APPROVAL")
    assert isinstance(extractor.get_extractor(), extractor.ApiExtractor)


def test_intake_named_role_fills_seeded_placeholder_without_duplicate(client):
    account = _post(client, "/api/accounts", {"name": "Synthetic Launch"})
    onboard = _post(client, f"/api/accounts/{account['id']}/onboard", {
        "kickoff_date": _day(-2), "program_name": "Launch", "europe_in_scope": True,
    })
    before = client.get(f"/api/accounts/{account['id']}/onboarding").json()["placeholders"]
    champion = next(row for row in before if row["expected_role"] == "champion")
    proposal = client.post("/api/intake/parse", json={
        "text": "Met with Aisha Kone (Champion)."
    }).json()["proposals"][0]
    accepted = _post(client, "/api/intake/accept", {
        "account_id": account["id"], "program_id": onboard["program_id"], "proposal": proposal,
    })
    assert accepted["filled_placeholder_id"] == champion["id"]
    assert accepted["created"]["id"] == champion["id"]
    people = client.get(f"/api/persons?account_id={account['id']}&include_valence=false").json()
    assert sum(person["name"] == "Aisha Kone" for person in people) == 1
    assert not next(person for person in people if person["id"] == champion["id"])["is_placeholder"]


def test_brand_new_account_reaches_delivered_expansion_case_entirely_on_mocks(client):
    # 1 — assigned -> seeded plan, checklists, and placeholders.
    account = _post(client, "/api/accounts", {"name": "Bluepeak Demo"})
    onboard = _post(client, f"/api/accounts/{account['id']}/onboard", {
        "kickoff_date": _day(-40), "program_name": "Manager Enablement Launch",
        "europe_in_scope": True,
    })
    program_id = onboard["program_id"]
    assert onboard["seeded"] == {"milestones": 7, "prep_tasks": 3,
                                  "checklist_items": 20, "placeholders": 6}
    proposals = client.post("/api/intake/parse", json={
        "text": "Met with Aisha Kone (Champion). They are currently using Ascend. "
                "Go-live target is 2026-10-01. What is the works-council timeline?",
    }).json()["proposals"]
    for proposal in proposals:
        accepted = _post(client, "/api/intake/accept", {
            "account_id": account["id"], "program_id": program_id, "proposal": proposal,
        })
        if proposal["type"] == "stakeholder":
            aisha = accepted["created"]
    aisha = client.patch(f"/api/persons/{aisha['id']}", json={
        "title": "VP of Learning", "email": "aisha.kone@example-bluepeak.test",
    }).json()
    role_id = client.app.state.conn.execute(
        "SELECT id FROM stakeholder_roles WHERE program_id=? AND person_id=?",
        (program_id, aisha["id"]),
    ).fetchone()[0]
    assessed = client.patch(f"/api/stakeholder-roles/{role_id}", json={
        "layer": "operational", "stance": "supporter", "stance_assessed_on": _day(),
        "stance_evidence_note": "Volunteered to carry the launch into the staff meeting.",
    })
    assert assessed.status_code == 200
    queue = client.get("/api/queue").json()["items"]
    assert any(item["trigger_type"] == "checklist_overdue" for item in queue)
    assert any(item["trigger_type"] == "unidentified_placeholder" for item in queue)

    org_sync = _post(client, "/api/ingest/org-changes/sync", status=200)
    assert org_sync["status"] == "succeeded" and org_sync["result"]["created"] == 1
    org_flag = client.get(f"/api/accounts/{account['id']}/org-changes").json()["flags"][0]
    assert client.get(f"/api/persons/{aisha['id']}/card").json()["title"] == "VP of Learning"
    _post(client, f"/api/org-change-flags/{org_flag['id']}/confirm", status=200)
    assert client.get(f"/api/persons/{aisha['id']}/card").json()["title"] == "VP of Talent Enablement"

    # 2 — fixture jobs associate, flag, clear, and refuse to guess a low-confidence recording.
    synced = _post(client, "/api/ingest/emails/sync", status=200)
    assert synced["status"] == "succeeded"
    flagged = client.get("/api/comms/flagged").json()["comms"]
    aisha_message = next(row for row in flagged if row["from_addr"] == aisha["email"])
    _post(client, f"/api/comms/{aisha_message['id']}/responded", status=200)
    recording = _post(client, "/api/ingest/recording", {
        "reference": "kickoff-call.txt", "attendees": ["Aisha Kone"],
        "keywords": ["bluepeak"],
    }, status=200)
    assert recording["result"]["needs_triage"] is False and recording["result"]["proposals"] >= 3
    uncertain = _post(client, "/api/ingest/recording", {
        "reference": "kickoff-call.txt", "attendees": ["Unknown Person"],
        "keywords": ["bluepeak"],
    }, status=200)
    assert uncertain["result"]["needs_triage"] is True
    assert any("Low-confidence" in item["raw_text"] for item in client.get("/api/inbox").json())

    # 3 — extended extraction remains propose -> per-item accept.
    extraction = _post(client, "/api/extraction/run", {
        "account_id": account["id"], "program_id": program_id,
        "transcript": "Our new VP of IT is Dana Okafor.\n"
                      "Two other regions also want to roll out to their teams.\n"
                      "Let's align the launch to the fall performance review.\n"
                      "Manager activation improved by 20% in the pilot.",
    })
    by_type = {proposal["mutation_type"]: proposal for proposal in extraction["proposals"]}
    assert {"fill_placeholder", "log_pull_signal", "create_deployment_moment",
            "create_value_story"} <= set(by_type)
    it_placeholder = next(row for row in client.get(
        f"/api/accounts/{account['id']}/onboarding").json()["placeholders"]
        if row["expected_role"] == "it")
    for mutation_type in ("fill_placeholder", "log_pull_signal",
                          "create_deployment_moment", "create_value_story"):
        overrides = {"placeholder_person_id": it_placeholder["id"]} \
            if mutation_type == "fill_placeholder" else {}
        _post(client, f"/api/extraction/proposals/{by_type[mutation_type]['id']}/accept",
              {"overrides": overrides}, status=200)
    extracted_story = next(row for row in client.get(
        f"/api/value-stories?account_id={account['id']}").json()
        if "improved by 20%" in row["outcome"])
    assert extracted_story["visibility_class"] == "internal"

    # 4 — validated champion + sourced aggregate evidence.
    source = _post(client, "/api/source-references", {
        "label": "Synthetic signed scorecard", "type": "file",
    })
    _post(client, "/api/advocacy-events", {
        "person_id": aisha["id"], "program_id": program_id,
        "kind": "advocacy_without_us", "occurred_on": _day(),
        "note": "Presented the rollout case internally without Valence present.",
        "source_reference_id": source["id"],
    })
    _post(client, "/api/champion-candidates", {
        "person_id": aisha["id"], "program_id": program_id, "stage": "validate",
    })
    partition = _post(client, "/api/population-partitions", {
        "account_id": account["id"], "basis": "business unit", "total_fte": 1000,
        "fte_source": "synthetic scorecard", "fte_as_of": _day(),
    })
    segment = _post(client, "/api/population-segments", {
        "partition_id": partition["id"], "name": "Core managers", "headcount": 800,
        "headcount_source": "synthetic scorecard", "headcount_as_of": _day(),
        "paid_seats": 200, "paid_seats_source": "synthetic contract",
        "paid_seats_as_of": _day(), "source_reference_id": source["id"],
    })
    definition = _post(client, "/api/metric-definitions", {
        "name": "Synthetic manager activation", "stale_after_days": 30,
    })
    observation = _post(client, "/api/metric-observations", {
        "definition_id": definition["id"], "program_id": program_id,
        "population_segment_id": segment["id"], "value": .82,
        "current_through": _day(), "source_reference_id": source["id"],
    })
    target = _post(client, "/api/value-targets", {
        "account_id": account["id"], "definition_id": definition["id"],
        "segment_id": segment["id"], "target_value": .7, "timeframe_end": _day(30),
        "client_accepted": True, "accepted_by_person_id": aisha["id"],
        "accepted_on": _day(), "client_visible": True,
        "source_reference_id": source["id"],
    })
    ledger = client.get(f"/api/accounts/{account['id']}/ledger").json()
    assert ledger["targets"][0]["realization"]["status"] == "realized"
    assert ledger["targets"][0]["realization"]["observation_id"] == observation["id"]
    use_case = _post(client, "/api/use-cases", {
        "name": "Synthetic performance reviews", "slug": "synthetic-performance-reviews",
    })
    cell = _post(client, "/api/whitespace-cells", {
        "account_id": account["id"], "segment_id": segment["id"],
        "use_case_id": use_case["id"], "estimated_seats": 600, "paid_seats": 200,
        "sponsor_person_id": aisha["id"], "client_visible": True,
        "source_reference_id": source["id"],
    })
    for fact, value, reason in (("penetration", "paid", "Synthetic signed order"),
                                ("evidence_state", "measured", "Fresh aggregate readout")):
        _post(client, f"/api/whitespace-cells/{cell['id']}/set-fact", {
            "fact": fact, "value": value, "reason": reason,
        }, status=200)

    # 5 — earned agreement -> one opportunity -> five linked qualification slots -> growth line.
    budget_owner = _post(client, "/api/persons", {
        "name": "Morgan Hale", "account_id": account["id"], "title": "VP Finance",
    })
    contract = _post(client, "/api/contracts", {
        "account_id": account["id"], "version_label": "Synthetic FY27", "seats": 200,
        "renewal_date": _day(90), "notice_period_days": 30, "procurement_lead_days": 25,
    })
    fiscal = client.put(f"/api/accounts/{account['id']}/fiscal-map", json={
        "fiscal_year_end": _day(180), "planning_window_start": _day(20),
        "planning_window_end": _day(60), "budget_request_deadline": _day(50),
        "procurement_lead_contract_id": contract["id"], "works_council_lead_days": 20,
        "confirmed_on": _day(), "confirmed_by": "operator",
    })
    assert fiscal.status_code == 200
    pool = _post(client, "/api/funding-pools", {
        "account_id": account["id"], "name": "Synthetic transformation budget",
        "kind": "transformation_program", "owner_person_id": budget_owner["id"],
        "status": "confirmed", "amount": 50000, "currency": "USD",
        "client_visible": True, "source_reference_id": source["id"],
    })
    _post(client, "/api/compliance-items", {
        "program_id": program_id, "lane": "legal_dpo", "status": "complete",
    })
    _post(client, "/api/plays", {
        "name": "Synthetic earned expansion", "trigger_kind": "expansion_signal",
        "action_template": "Prepare {title}: {because}",
    })
    _post(client, "/api/operational-agreements", {
        "account_id": account["id"], "contract_version_id": contract["id"],
        "name": "Activation unlocks wave two", "source_kind": "signed_paper",
        "source_reference_id": source["id"], "value_target_id": target["id"],
        "effective_on": _day(-1), "seat_band_min": 200, "seat_band_max": 400,
        "unit_price": 40, "currency": "USD", "agreed_process": "Issue the order form",
        "budget_owner_person_id": budget_owner["id"], "client_visible": True,
    })
    fired = _post(client, "/api/operational-agreements/evaluate", status=200)
    assert fired["fired"] == 1
    assert _post(client, "/api/operational-agreements/evaluate", status=200)["fired"] == 0
    event_id = fired["event_ids"][0]
    assert any(item["object_id"] == event_id for item in client.get("/api/queue").json()["items"])
    opportunity = _post(client, f"/api/operational-agreement-events/{event_id}/action")["opportunity"]
    ask = _post(client, "/api/ask-calendars", {
        "account_id": account["id"], "name": "Synthetic wave-two ask",
        "target_close_date": _day(70), "opportunity_id": opportunity["id"],
    })
    qualified = client.patch(f"/api/expansions/{opportunity['id']}/qualification", json={
        "value_target_id": target["id"], "budget_owner_person_id": budget_owner["id"],
        "ask_calendar_id": ask["id"], "champion_person_id": aisha["id"],
        "program_id": program_id,
    })
    assert qualified.status_code == 200, qualified.text
    assert qualified.json()["qualification"]["fully_qualified"] is True
    plan = _post(client, "/api/growth-plans", {
        "account_id": account["id"], "name": "Synthetic account growth plan",
        "target_seats": 700, "target_date": _day(180),
    })
    _post(client, "/api/growth-plan-lines", {
        "plan_id": plan["id"], "name": "Wave two", "segment_id": segment["id"],
        "opportunity_id": opportunity["id"], "budget_owner_person_id": budget_owner["id"],
        "funding_pool_id": pool["id"], "ask_calendar_id": ask["id"], "seat_count": 300,
        "probability": .75, "probability_author": "operator", "probability_assessed_on": _day(),
        "ask_date": _day(30), "status": "committed", "client_visible": True,
        "source_reference_id": source["id"], "competitive_notes": "SECRET INTERNAL TACTIC",
    })
    growth = client.get(f"/api/accounts/{account['id']}/growth-plan").json()
    assert growth["rollup"]["additive"] is True and growth["rollup"]["unfunded_gap"] == 200
    renewal = client.get(f"/api/accounts/{account['id']}/renewal-center").json()
    assert [row["id"] for row in renewal["eligible_expansions"]] == [opportunity["id"]]
    mutual = client.get(f"/api/accounts/{account['id']}/map").json()["markdown"]
    assert "Wave two" in mutual and "SECRET INTERNAL TACTIC" not in mutual
    assert "probability" not in mutual.lower()

    # 6 — finished artifacts remain review-gated; "sent" records delivery but transmits nothing.
    assert client.get(f"/api/accounts/{account['id']}/pre-call-brief").status_code == 200
    assert client.get(f"/api/accounts/{account['id']}/kickoff-deck").status_code == 200
    assert client.get(f"/api/accounts/{account['id']}/champion-kit").status_code == 200
    value_review = _post(client, f"/api/accounts/{account['id']}/documents", {
        "kind": "value_review",
    })
    pptx = client.get(f"/api/documents/{value_review['id']}/pptx")
    assert pptx.status_code == 200 and pptx.content[:2] == b"PK"
    business_case = _post(client, f"/api/accounts/{account['id']}/documents", {
        "kind": "business_case",
    })
    delivered = _post(client, f"/api/documents/{business_case['id']}/status", {
        "status": "sent", "reviewed_by": "operator",
    }, status=200)
    assert delivered["status"] == "sent" and delivered["reviewed_on"]

    runs = client.get("/api/play-runs").json()
    assert runs and runs[0]["status"] == "fired"
    completed = _post(client, f"/api/play-runs/{runs[0]['id']}/complete", {
        "effectiveness": "effective", "effectiveness_note": "Synthetic earned path worked.",
    }, status=200)
    assert completed["status"] == "completed"
    _post(client, "/api/weekly-team-update/schedule", {"recurring": False})
    drained = _post(client, "/api/jobs/run", status=200)
    assert drained["count"] >= 1
    drafts = client.get("/api/documents?status=draft").json()
    assert any(row["kind"] == "team_update" and row["audience"] == "internal" for row in drafts)

    # 7 — final governance and trust-boundary assertions.
    registry = client.get("/api/operations").json()["connection_registry"]
    assert registry["approval"]["approved"] is False
    assert all(row["gate_status"] == "local" for row in registry["connections"])
    schema = " ".join(row[1] for row in client.app.state.conn.execute(
        "SELECT name, sql FROM sqlite_master WHERE type='table' AND sql IS NOT NULL"))
    assert "person_usage" not in schema.lower() and "individual_usage" not in schema.lower()
