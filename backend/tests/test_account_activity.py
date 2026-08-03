"""Release 2 typed activity-projection contract."""
import os
import sqlite3
import tempfile

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app import account_activity
from app.account_activity import ActivityItem, adapter_names, project_account_activity
from conftest import utc_day


@pytest.fixture()
def client():
    fd, path = tempfile.mkstemp(suffix=".sqlite")
    os.close(fd)
    os.environ["VALENCE_OS_DB"] = path
    os.environ["VALENCE_OS_WORKER"] = "0"
    from app.main import app
    with TestClient(app) as test_client:
        yield test_client
    for suffix in ("", "-wal", "-shm"):
        try:
            os.unlink(path + suffix)
        except FileNotFoundError:
            pass


def test_activity_contract_rejects_conflated_or_invalid_time_fields():
    base = {
        "id": "interaction:1:recorded", "account_id": "account-1", "source_type": "interaction",
        "source_id": "1", "event_kind": "interaction_recorded", "stream": "customer",
        "state": "confirmed", "title": "Call interaction", "display_at": "2026-08-03",
        "recorded_at": "2026-08-03T15:00:00+00:00", "temporal_kind": "occurred",
        "temporal_precision": "date", "direction": "past", "materiality": "material",
        "reason": "Meaningful customer interaction recorded",
        "native_target": {"tab": "ledger", "record_type": "interaction", "record_id": "1"},
    }
    assert ActivityItem(**base).stream == "customer"
    with pytest.raises(ValidationError):
        ActivityItem(**{**base, "stream": "planned"})
    with pytest.raises(ValidationError):
        ActivityItem(**{**base, "display_at": "2026-08-03T15:00:00", "temporal_precision": "date"})
    with pytest.raises(ValidationError):
        ActivityItem(**{**base, "recorded_at": "2026-08-03T15:00:00"})
    with pytest.raises(ValidationError):
        ActivityItem(**{**base, "recorded_at": "2026-08-03T15:00:00+05:00"})


def test_interaction_adapter_preserves_scope_timing_and_trust_boundary(client):
    account = client.post("/api/accounts", json={"name": "Alpine Synthetic"}).json()
    other_account = client.post("/api/accounts", json={"name": "Summit Synthetic"}).json()
    europe = client.post("/api/programs", json={
        "account_id": account["id"], "name": "Europe", "phase": "launch",
    }).json()
    americas = client.post("/api/programs", json={
        "account_id": account["id"], "name": "Americas", "phase": "foundation",
    }).json()
    other_program = client.post("/api/programs", json={
        "account_id": other_account["id"], "name": "Other", "phase": "foundation",
    }).json()
    customer = client.post("/api/persons", json={
        "name": "Casey Client", "account_id": account["id"], "affiliation": "client",
    }).json()
    colleague = client.post("/api/persons", json={
        "name": "Val Operator", "affiliation": "valence",
    }).json()

    customer_interaction = client.post("/api/interactions", json={
        "account_id": account["id"], "program_id": europe["id"], "type": "call",
        "occurred_on": "2026-07-29", "occurred_at_time": "14:00", "summary": "Readiness review",
        "raw_notes": "Internal-only detail must never enter activity", "participant_ids": [customer["id"]],
    }).json()
    client.post("/api/interactions", json={
        "account_id": account["id"], "program_id": europe["id"], "type": "meeting",
        "occurred_on": "2026-07-30", "summary": "Internal preparation",
        "participant_ids": [colleague["id"]],
    })
    client.post("/api/interactions", json={
        "account_id": account["id"], "type": "email", "occurred_on": "2026-07-31",
        "summary": "Account-level interaction without resolved participants",
    })
    client.post("/api/interactions", json={
        "account_id": account["id"], "program_id": americas["id"], "type": "call",
        "occurred_on": "2026-08-01", "summary": "Different program",
    })

    with client.app.state.conn_lock:
        projection = project_account_activity(
            client.app.state.conn, account["id"], program_id=europe["id"],
            as_of="2026-08-03T15:00:00+00:00", include_adapters=["interaction"],
        )

    assert "interaction" in adapter_names()
    assert projection.stamp.coverage == ["interaction"] and projection.stamp.omitted == []
    assert len(projection.items) == 3  # selected program plus direct account records; not Americas
    by_summary = {item.summary: item for item in projection.items}
    assert by_summary["Readiness review"].stream == "customer"
    assert by_summary["Internal preparation"].stream == "internal"
    assert by_summary["Account-level interaction without resolved participants"].stream == "unknown"
    item = by_summary["Readiness review"]
    assert item.display_at == "2026-07-29T14:00" and item.temporal_precision == "datetime"
    assert item.recorded_at == customer_interaction["created_at"]
    assert item.native_target.tab == "ledger"
    assert "raw_notes" not in item.model_dump()
    assert "Internal-only detail" not in str(item.model_dump())

    with client.app.state.conn_lock, pytest.raises(HTTPException) as exc:
        project_account_activity(client.app.state.conn, account["id"], program_id=other_program["id"])
    assert exc.value.status_code == 422


def test_scoped_checkpoints_are_append_only_idempotent_and_monotonic(client):
    account = client.post("/api/accounts", json={"name": "Checkpoint Synthetic"}).json()
    program = client.post("/api/programs", json={
        "account_id": account["id"], "name": "Program", "phase": "launch",
    }).json()
    other = client.post("/api/accounts", json={"name": "Other Synthetic"}).json()
    other_program = client.post("/api/programs", json={
        "account_id": other["id"], "name": "Other", "phase": "foundation",
    }).json()
    first_stamp = "2026-08-01T12:00:00+00:00"
    first = client.post(f"/api/accounts/{account['id']}/change-checkpoints", json={
        "scope_type": "account", "reviewed_through": first_stamp,
    })
    assert first.status_code == 201, first.text
    repeated = client.post(f"/api/accounts/{account['id']}/change-checkpoints", json={
        "scope_type": "account", "reviewed_through": first_stamp.replace("+00:00", "Z"),
    })
    assert repeated.status_code == 201 and repeated.json()["id"] == first.json()["id"]
    program_checkpoint = client.post(f"/api/accounts/{account['id']}/change-checkpoints", json={
        "scope_type": "program", "program_id": program["id"],
        "reviewed_through": "2026-08-02T12:00:00+00:00",
    })
    assert program_checkpoint.status_code == 201
    backward = client.post(f"/api/accounts/{account['id']}/change-checkpoints", json={
        "scope_type": "program", "program_id": program["id"],
        "reviewed_through": first_stamp,
    })
    assert backward.status_code == 409
    wrong_scope = client.post(f"/api/accounts/{account['id']}/change-checkpoints", json={
        "scope_type": "program", "program_id": other_program["id"],
        "reviewed_through": "2026-08-02T12:00:00+00:00",
    })
    assert wrong_scope.status_code == 422
    future = client.post(f"/api/accounts/{account['id']}/change-checkpoints", json={
        "scope_type": "account", "reviewed_through": "2099-01-01T00:00:00+00:00",
    })
    assert future.status_code == 422

    checkpoint_id = program_checkpoint.json()["id"]
    with client.app.state.conn_lock, pytest.raises(sqlite3.IntegrityError):
        client.app.state.conn.execute(
            "UPDATE account_change_checkpoints SET reviewed_through=? WHERE id=?",
            ("2026-08-03T00:00:00+00:00", checkpoint_id),
        )


def test_activity_and_operate_endpoints_expose_coverage_attention_and_truth_state(client):
    account = client.post("/api/accounts", json={"name": "Operate Synthetic"}).json()
    program = client.post("/api/programs", json={
        "account_id": account["id"], "name": "Europe", "phase": "launch",
    }).json()
    customer = client.post("/api/persons", json={
        "name": "Client Sponsor", "account_id": account["id"], "affiliation": "client",
    }).json()
    owner = client.post("/api/persons", json={
        "name": "Val Owner", "affiliation": "valence",
    }).json()
    client.post("/api/interactions", json={
        "account_id": account["id"], "program_id": program["id"], "type": "call",
        "occurred_on": utc_day(-1), "summary": "Customer governance call",
        "participant_ids": [customer["id"]],
    })
    commitment = client.post("/api/commitments", json={
        "account_id": account["id"], "program_id": program["id"],
        "description": "Confirm rollout decision", "responsible_party_id": customer["id"],
        "internal_owner_id": owner["id"], "due_date": utc_day(-1),
    })
    assert commitment.status_code == 201, commitment.text
    risk = client.post("/api/risks", json={
        "program_id": program["id"], "description": "Data access is blocked",
        "severity": "high", "is_blocker": True,
    })
    assert risk.status_code == 201, risk.text
    client.post(f"/api/accounts/{account['id']}/operator-views", json={
        "body": "Expansion depends on closing the data gap.", "assessed_on": utc_day(),
    })

    activity = client.get(f"/api/accounts/{account['id']}/activity", params={
        "program_id": program["id"], "limit": 200,
    })
    assert activity.status_code == 200, activity.text
    body = activity.json()
    assert {"interaction", "execution", "status_assessment", "company_event"}.issubset(
        set(body["stamp"]["coverage"])
    )
    assert body["stamp"]["omitted"] == []
    assert any(item["source_type"] == "commitment" for item in body["items"])
    assert all("raw_notes" not in item for item in body["items"])

    command = client.get(f"/api/accounts/{account['id']}/command-center", params={
        "program_id": program["id"],
    })
    assert command.status_code == 200, command.text
    data = command.json()
    reasons = {row["reason"] for row in data["attention"]}
    assert "Commitment is overdue" in reasons and "Open blocker" in reasons
    assert data["operator_view"]["body"].startswith("Expansion depends")
    assert data["changes_since_review"]

    reviewed = client.post(f"/api/accounts/{account['id']}/change-checkpoints", json={
        "scope_type": "program", "program_id": program["id"],
        "reviewed_through": data["stamp"]["data_current_through"],
    })
    assert reviewed.status_code == 201
    after = client.get(f"/api/accounts/{account['id']}/command-center", params={
        "program_id": program["id"],
    }).json()
    assert all(item["program_id"] is None for item in after["changes_since_review"])


def test_activity_filters_facets_metrics_and_cursor_order_are_stable(client):
    account = client.post("/api/accounts", json={"name": "Activity Consumer"}).json()
    program = client.post("/api/programs", json={
        "account_id": account["id"], "name": "Europe", "phase": "launch",
    }).json()
    other_program = client.post("/api/programs", json={
        "account_id": account["id"], "name": "Americas", "phase": "foundation",
    }).json()
    customer = client.post("/api/persons", json={
        "name": "Activity Customer", "account_id": account["id"], "affiliation": "client",
    }).json()
    colleague = client.post("/api/persons", json={
        "name": "Activity Colleague", "affiliation": "valence",
    }).json()
    created_interactions = {}
    for summary, participant_ids, meaningful, selected_program in (
        ("Customer material", [customer["id"]], True, program["id"]),
        ("Internal context", [colleague["id"]], False, program["id"]),
        ("Direct account material", [customer["id"]], True, None),
        ("Other program hidden", [customer["id"]], True, other_program["id"]),
    ):
        created_interactions[summary] = client.post("/api/interactions", json={
            "account_id": account["id"], "program_id": selected_program,
            "occurred_on": utc_day(-1), "type": "call", "summary": summary,
            "meaningful_touch": meaningful, "participant_ids": participant_ids,
        }).json()
    linked_commitment = client.post("/api/commitments", json={
        "account_id": account["id"], "program_id": program["id"],
        "description": "Follow through from the customer touch",
        "responsible_party_id": customer["id"], "internal_owner_id": colleague["id"],
        "due_date": utc_day(4),
        "source_interaction_id": created_interactions["Customer material"]["id"],
    })
    assert linked_commitment.status_code == 201, linked_commitment.text
    early = client.post("/api/calendar-events", json={
        "account_id": account["id"], "program_id": program["id"], "purpose": "governance",
        "title": "Earlier meeting", "starts_at": f"{utc_day(2)}T10:00:00+00:00",
    }).json()
    late = client.post("/api/calendar-events", json={
        "account_id": account["id"], "program_id": program["id"], "purpose": "qbr",
        "title": "Later meeting", "starts_at": f"{utc_day(3)}T10:00:00+00:00",
    }).json()

    base_params = [
        ("program_id", program["id"]), ("direction", "past"),
        ("source_type", "interaction"),
    ]
    full = client.get(f"/api/accounts/{account['id']}/activity", params=[*base_params, ("limit", "200")])
    assert full.status_code == 200, full.text
    body = full.json()
    assert body["matched_count"] == 3
    assert body["facets"]["source_types"]["interaction"] == 3
    assert body["facets"]["source_types"]["calendar"] == 2
    assert body["stamp"]["projection_duration_ms"] >= 0
    assert len(body["stamp"]["adapter_metrics"]) == len(adapter_names())
    interaction_metric = next(
        item for item in body["stamp"]["adapter_metrics"] if item["adapter"] == "interaction"
    )
    assert interaction_metric["status"] == "covered" and interaction_metric["item_count"] == 3
    assert interaction_metric["duration_ms"] >= 0
    assert all("Other program hidden" not in str(item) for item in body["items"])
    grouped_response = client.get(f"/api/accounts/{account['id']}/activity", params=[
        ("program_id", program["id"]), ("direction", "all"),
        ("source_type", "interaction"), ("source_type", "commitment"), ("limit", "200"),
    ]).json()
    group_id = f"interaction:{created_interactions['Customer material']['id']}"
    grouped = [item for item in grouped_response["items"] if item.get("group_id") == group_id]
    assert {item["group_role"] for item in grouped} == {"origin", "derived"}
    assert {item["source_type"] for item in grouped} == {"interaction", "commitment"}

    first = client.get(f"/api/accounts/{account['id']}/activity", params=[*base_params, ("limit", "2")]).json()
    assert first["next_cursor"] and first["matched_count"] == 3
    second = client.get(f"/api/accounts/{account['id']}/activity", params=[
        *base_params, ("limit", "2"), ("cursor", first["next_cursor"]),
    ]).json()
    assert second["matched_count"] == 3 and second["next_cursor"] is None
    assert [item["id"] for item in [*first["items"], *second["items"]]] == [
        item["id"] for item in body["items"]
    ]

    context = client.get(f"/api/accounts/{account['id']}/activity", params=[
        *base_params, ("materiality", "context"),
    ]).json()
    assert [item["summary"] for item in context["items"]] == ["Internal context"]
    customer_only = client.get(f"/api/accounts/{account['id']}/activity", params=[
        *base_params, ("stream", "customer"),
    ]).json()
    assert {item["summary"] for item in customer_only["items"]} == {
        "Customer material", "Direct account material",
    }

    future = client.get(f"/api/accounts/{account['id']}/activity", params=[
        ("program_id", program["id"]), ("direction", "future"),
        ("source_type", "calendar"),
    ]).json()
    assert [item["source_id"] for item in future["items"]] == [early["id"], late["id"]]
    assert client.get(f"/api/accounts/{account['id']}/activity", params={
        "event_kind": "invented_transition",
    }).status_code == 422
    assert client.get(f"/api/accounts/{account['id']}/activity", params={
        "display_from": "not-a-date",
    }).status_code == 422
    assert client.get(f"/api/accounts/{account['id']}/activity", params={
        "display_from": utc_day(2), "display_to": utc_day(1),
    }).status_code == 422
    same_day = client.get(f"/api/accounts/{account['id']}/activity", params={
        "direction": "future", "source_type": "calendar",
        "display_from": utc_day(2), "display_to": utc_day(2),
    })
    assert [item["source_id"] for item in same_day.json()["items"]] == [early["id"]]
    assert client.get(f"/api/accounts/{account['id']}/activity", params={
        "source_type": "invented_source",
    }).status_code == 422


def test_activity_partial_coverage_names_omitted_adapter_and_cost(client, monkeypatch):
    account = client.post("/api/accounts", json={"name": "Partial Activity"}).json()

    def unavailable_adapter(_conn, _query):
        raise sqlite3.OperationalError("synthetic adapter outage")

    monkeypatch.setitem(account_activity._ADAPTERS, "calendar", unavailable_adapter)
    response = client.get(f"/api/accounts/{account['id']}/activity")
    assert response.status_code == 200, response.text
    stamp = response.json()["stamp"]
    assert "calendar" in stamp["omitted"] and "calendar" not in stamp["coverage"]
    metric = next(item for item in stamp["adapter_metrics"] if item["adapter"] == "calendar")
    assert metric["status"] == "omitted" and metric["item_count"] == 0
    assert metric["duration_ms"] >= 0


def test_prepare_selects_scoped_meeting_without_guessing_attendees(client):
    account = client.post("/api/accounts", json={"name": "Prepare Synthetic"}).json()
    program = client.post("/api/programs", json={
        "account_id": account["id"], "name": "Europe", "phase": "launch",
    }).json()
    other_program = client.post("/api/programs", json={
        "account_id": account["id"], "name": "Americas", "phase": "foundation",
    }).json()
    customer = client.post("/api/persons", json={
        "name": "Dana Customer", "email": "dana@example.com",
        "account_id": account["id"], "affiliation": "client",
    }).json()
    owner = client.post("/api/persons", json={
        "name": "Val Owner", "email": "owner@valence.example", "affiliation": "valence",
    }).json()
    role = client.post("/api/stakeholder-roles", json={
        "program_id": program["id"], "person_id": customer["id"], "role": "program_owner",
        "stance": "supporter", "stance_assessed_on": utc_day(-2),
        "stance_evidence_note": "Confirmed in governance", "cares_about": "launch readiness",
    })
    assert role.status_code == 201, role.text
    client.post("/api/interactions", json={
        "account_id": account["id"], "program_id": program["id"], "type": "call",
        "occurred_on": utc_day(-5), "summary": "Resolved the rollout sequence",
        "participant_ids": [customer["id"]],
    })
    meeting = client.post("/api/calendar-events", json={
        "account_id": account["id"], "program_id": program["id"], "purpose": "qbr",
        "title": "Europe governance review", "starts_at": f"{utc_day(2)}T15:00:00+00:00",
        "ends_at": f"{utc_day(2)}T16:00:00+00:00", "location": "Video",
        "organizer_email": "owner@valence.example",
    }).json()
    # General calendar attendees arrive through the read-only calendar adapter; the Stage 13
    # attendee endpoint deliberately accepts only cohort webinar/office-hours outcomes.
    with client.app.state.conn:
        client.app.state.conn.execute(
            "INSERT INTO calendar_event_attendees "
            "(event_id,person_id,name,email,response_status,attendance_status,created_at) "
            "VALUES (?,?,?,?,?,?,?)",
            (meeting["id"], customer["id"], customer["name"], "dana@example.com",
             "accepted", "invited", meeting["created_at"]),
        )
        client.app.state.conn.execute(
            "INSERT INTO calendar_event_attendees "
            "(event_id,person_id,name,email,response_status,attendance_status,created_at) "
            "VALUES (?,?,?,?,?,?,?)",
            (meeting["id"], owner["id"], owner["name"], "owner@valence.example",
             "accepted", "invited", meeting["created_at"]),
        )
        client.app.state.conn.execute(
            "INSERT INTO calendar_event_attendees "
            "(event_id,person_id,name,email,response_status,attendance_status,created_at) "
            "VALUES (?,?,?,?,?,?,?)",
            (meeting["id"], None, "Mystery Guest", "mystery@example.com",
             "unknown", "unknown", meeting["created_at"]),
        )
    commitment = client.post("/api/commitments", json={
        "account_id": account["id"], "program_id": program["id"],
        "description": "Confirm QBR decision", "responsible_party_id": customer["id"],
        "internal_owner_id": owner["id"], "due_date": utc_day(1),
    })
    assert commitment.status_code == 201, commitment.text
    blocker = client.post("/api/risks", json={
        "program_id": program["id"], "description": "Executive agenda is blocked",
        "severity": "high", "is_blocker": True,
    })
    assert blocker.status_code == 201, blocker.text

    other_meeting = client.post("/api/calendar-events", json={
        "account_id": account["id"], "program_id": other_program["id"], "purpose": "other",
        "title": "Americas review", "starts_at": f"{utc_day(3)}T15:00:00+00:00",
    }).json()
    response = client.get(f"/api/accounts/{account['id']}/command-center/prepare", params={
        "program_id": program["id"],
    })
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["selected_meeting"]["id"] == meeting["id"]
    assert {row["id"] for row in data["meetings"]} == {meeting["id"]}
    attendees = {row["email"]: row for row in data["attendees"]}
    assert attendees["dana@example.com"]["association_state"] == "resolved"
    assert attendees["dana@example.com"]["role"]["effective_role"] == "program_owner"
    assert attendees["dana@example.com"]["last_meaningful_touch"]["summary"].startswith("Resolved")
    assert attendees["mystery@example.com"]["association_state"] == "unknown"
    assert attendees["mystery@example.com"]["person_id"] is None
    assert data["brief_person_ids"] == [customer["id"]]
    assert data["context_window"]["starts_on"] == utc_day(-5)
    assert data["context_window"]["basis"].startswith("earliest last meaningful touch")
    assert any(item["source_type"] == "commitment" for item in data["recent_context"])
    assert all(item["summary"] != "Resolved the rollout sequence" for item in data["recent_context"])
    assert {row["kind"] for row in data["open_threads"]} >= {"commitment", "risk"}
    assert "unknown_attendee" in {gap["kind"] for gap in data["evidence_gaps"]}
    assert client.get("/api/documents", params={"account_id": account["id"]}).json() == []

    account_meeting = client.post("/api/calendar-events", json={
        "account_id": account["id"], "purpose": "governance", "title": "Account governance",
        "starts_at": f"{utc_day(4)}T15:00:00+00:00",
    }).json()
    direct_account_scope = client.get(
        f"/api/accounts/{account['id']}/command-center/prepare",
        params={"program_id": program["id"], "meeting_id": account_meeting["id"]},
    )
    assert direct_account_scope.status_code == 200
    assert direct_account_scope.json()["selected_meeting"]["program_id"] is None

    out_of_scope = client.get(
        f"/api/accounts/{account['id']}/command-center/prepare",
        params={"program_id": program["id"], "meeting_id": other_meeting["id"]},
    )
    assert out_of_scope.status_code == 422
    brief = client.get(f"/api/accounts/{account['id']}/pre-call-brief", params={
        "program_id": program["id"], "person_ids": customer["id"],
    })
    assert brief.status_code == 200 and [row["person_id"] for row in brief.json()["attendees"]] == [customer["id"]]
    assert client.get("/api/documents", params={"account_id": account["id"]}).json() == []

    empty_account = client.post("/api/accounts", json={"name": "No Meetings Synthetic"}).json()
    empty = client.get(f"/api/accounts/{empty_account['id']}/command-center/prepare")
    assert empty.status_code == 200 and empty.json()["selected_meeting"] is None
    assert empty.json()["evidence_gaps"][0]["kind"] == "meeting_not_recorded"


def test_leadership_review_is_scoped_governed_and_read_only(client):
    account = client.post("/api/accounts", json={"name": "Leadership Synthetic"}).json()
    other_account = client.post("/api/accounts", json={"name": "Other Leadership"}).json()
    program = client.post("/api/programs", json={
        "account_id": account["id"], "name": "Europe", "phase": "launch",
    }).json()
    other_program = client.post("/api/programs", json={
        "account_id": account["id"], "name": "Americas", "phase": "foundation",
    }).json()
    customer = client.post("/api/persons", json={
        "name": "Leadership Buyer", "account_id": account["id"], "affiliation": "client",
    }).json()
    operator = client.post("/api/persons", json={
        "name": "Leadership Operator", "affiliation": "valence",
    }).json()
    other_person = client.post("/api/persons", json={
        "name": "Other Account Person", "account_id": other_account["id"], "affiliation": "client",
    }).json()
    function = next(item for item in client.get("/api/internal-functions").json() if item["name"] == "Other")
    bad_person_ask = client.post(f"/api/accounts/{account['id']}/internal-asks", json={
        "need": "Cross-account request", "success_condition": "Must be rejected",
        "requested_by_person_id": operator["id"], "requested_from_person_id": other_person["id"],
        "needed_by": utc_day(1),
    })
    assert bad_person_ask.status_code == 422
    ask = client.post(f"/api/accounts/{account['id']}/internal-asks", json={
        "need": "Choose the recovery tradeoff", "success_condition": "Decision recorded",
        "ask_type": "executive", "requested_by_person_id": operator["id"],
        "requested_from_function_id": function["id"], "current_owner_person_id": operator["id"],
        "needed_by": utc_day(-1),
    }).json()
    escalation = client.post(f"/api/internal-asks/{ask['id']}/escalations", json={
        "severity": "high",
    })
    assert escalation.status_code == 201, escalation.text
    other_ask = client.post(f"/api/accounts/{other_account['id']}/internal-asks", json={
        "need": "Other account secret", "success_condition": "Do not disclose",
        "requested_by_person_id": operator["id"], "requested_from_function_id": function["id"],
        "needed_by": utc_day(1),
    }).json()
    cross_account_status = client.post(f"/api/accounts/{account['id']}/status-assessments", json={
        "dimension": "commercial", "value": "off_track", "rationale": "Needs leadership",
        "recovery_owner_person_id": operator["id"], "recovery_action": "Choose a path",
        "recovery_due_on": utc_day(2), "leadership_ask_id": other_ask["id"],
        "assessed_on": utc_day(),
    })
    assert cross_account_status.status_code == 422
    commercial = client.post(f"/api/accounts/{account['id']}/status-assessments", json={
        "dimension": "commercial", "value": "off_track", "rationale": "Pricing path is blocked",
        "recovery_owner_person_id": operator["id"], "recovery_action": "Bring two options",
        "recovery_due_on": utc_day(2), "leadership_ask_id": ask["id"],
        "assessed_on": utc_day(),
    })
    assert commercial.status_code == 201, commercial.text
    delivery = client.post(f"/api/accounts/{account['id']}/status-assessments", json={
        "dimension": "delivery", "value": "at_risk", "rationale": "Sequence is compressed",
        "recovery_owner_person_id": operator["id"], "recovery_action": "Re-sequence launch",
        "recovery_due_on": utc_day(3), "assessed_on": utc_day(),
    })
    assert delivery.status_code == 201, delivery.text

    client.post(f"/api/accounts/{account['id']}/operator-views", json={
        "body": "Growth remains possible if leadership settles the recovery path.",
        "assessed_on": utc_day(),
    })
    review = client.post(f"/api/accounts/{account['id']}/reviews", json={
        "review_type": "monthly", "scheduled_on": utc_day(5),
        "chair_person_id": operator["id"],
    })
    assert review.status_code == 201, review.text

    period = client.post("/api/forecast-periods", json={
        "name": "Leadership quarter", "starts_on": utc_day(-10), "ends_on": utc_day(60),
        "cadence": "custom",
    }).json()
    opportunity = client.post("/api/expansions", json={
        "account_id": account["id"], "name": "Europe expansion",
        "budget_owner_person_id": customer["id"],
    }).json()
    forecast = client.post(f"/api/forecast-periods/{period['id']}/entries", json={
        "account_id": account["id"], "opportunity_id": opportunity["id"],
        "category": "pipeline", "amount": 120000, "currency": "USD", "price_basis": "arr",
        "assessed_on": utc_day(), "expected_decision_date": utc_day(20),
    }).json()
    moved_forecast = client.post(f"/api/forecast-entries/{forecast['id']}/category", json={
        "category": "best_case", "driver": "Leadership confirmed the evaluation path",
    })
    assert moved_forecast.status_code == 200, moved_forecast.text

    client.post("/api/interactions", json={
        "account_id": account["id"], "program_id": program["id"], "type": "meeting",
        "occurred_on": utc_day(), "summary": "Europe decision review",
        "participant_ids": [customer["id"], operator["id"]],
    })
    client.post("/api/interactions", json={
        "account_id": account["id"], "program_id": other_program["id"], "type": "meeting",
        "occurred_on": utc_day(), "summary": "Americas secret movement",
        "participant_ids": [operator["id"]],
    })
    selected_decision = client.post("/api/decisions", json={
        "account_id": account["id"], "program_id": program["id"],
        "description": "Sequence Europe first", "decided_on": utc_day(),
    }).json()
    direct_decision = client.post("/api/decisions", json={
        "account_id": account["id"], "description": "Keep the annual envelope",
        "decided_on": utc_day(),
    }).json()
    other_decision = client.post("/api/decisions", json={
        "account_id": account["id"], "program_id": other_program["id"],
        "description": "Americas private decision", "decided_on": utc_day(),
    }).json()

    selected_risk = client.post("/api/risks", json={
        "program_id": program["id"], "description": "Europe launch blocker",
        "severity": "high", "is_blocker": True,
    }).json()
    client.post("/api/risks", json={
        "program_id": other_program["id"], "description": "Americas private blocker",
        "severity": "high", "is_blocker": True,
    })
    selected_milestone = client.post("/api/milestones", json={
        "program_id": program["id"], "name": "Europe readiness",
        "target_date": utc_day(8), "at_risk": True,
    }).json()
    client.post("/api/milestones", json={
        "program_id": other_program["id"], "name": "Americas private milestone",
        "target_date": utc_day(8), "at_risk": True,
    })
    selected_commitment = client.post("/api/commitments", json={
        "account_id": account["id"], "program_id": program["id"],
        "description": "Confirm Europe sponsor", "responsible_party_id": customer["id"],
        "internal_owner_id": operator["id"], "due_date": utc_day(7),
    }).json()
    client.post("/api/commitments", json={
        "account_id": account["id"], "program_id": other_program["id"],
        "description": "Americas private commitment", "responsible_party_id": customer["id"],
        "internal_owner_id": operator["id"], "due_date": utc_day(7),
    })
    selected_meeting = client.post("/api/calendar-events", json={
        "account_id": account["id"], "program_id": program["id"], "purpose": "governance",
        "title": "Europe leadership meeting", "starts_at": f"{utc_day(4)}T15:00:00+00:00",
    }).json()
    client.post("/api/calendar-events", json={
        "account_id": account["id"], "program_id": other_program["id"], "purpose": "governance",
        "title": "Americas private meeting", "starts_at": f"{utc_day(4)}T16:00:00+00:00",
    })
    contract = client.post("/api/contracts", json={
        "account_id": account["id"], "version_label": "leadership-v1",
        "renewal_date": utc_day(45), "notice_period_days": 30,
    })
    assert contract.status_code == 201, contract.text

    before_documents = client.get("/api/documents", params={"account_id": account["id"]}).json()
    before_checkpoints = client.app.state.conn.execute(
        "SELECT COUNT(*) FROM account_change_checkpoints WHERE account_id=?", (account["id"],)
    ).fetchone()[0]
    response = client.get(f"/api/accounts/{account['id']}/command-center/leadership", params={
        "program_id": program["id"],
    })
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["scope"]["governed_facts"] == "account-wide"
    statuses = {item["dimension"]: item for item in data["standing"]["statuses"]}
    assert statuses["commercial"]["value"] == "off_track"
    assert statuses["commercial"]["leadership_response"]["id"] == ask["id"]
    assert statuses["delivery"]["recovery_owner"] == operator["name"]
    assert data["standing"]["forecast"][0]["id"] == forecast["id"]
    assert data["standing"]["forecast"][0]["evidence_supported"] is False

    movement_sources = {(item["source_type"], item["source_id"]) for item in data["movement"]}
    assert ("decision", selected_decision["id"]) in movement_sources
    assert ("decision", direct_decision["id"]) in movement_sources
    assert ("decision", other_decision["id"]) not in movement_sources
    assert any(item["summary"] == "Europe decision review" for item in data["movement"])
    assert all(item.get("summary") != "Americas secret movement" for item in data["movement"])

    stuck_ids = {item["id"] for item in data["stuck"]}
    assert f"risk:{selected_risk['id']}" in stuck_ids
    assert f"milestone:{selected_milestone['id']}" in stuck_ids
    assert f"internal_ask:{ask['id']}" in stuck_ids
    assert f"forecast:{forecast['id']}:evidence" in stuck_ids
    assert all("Americas private" not in item["title"] for item in data["stuck"])
    assert data["needs"][0]["id"] == ask["id"]
    assert data["needs"][0]["escalations"][0]["severity"] == "high"
    assert data["needs"][0]["next_action"]

    near_ids = {item["id"] for item in data["near_term"]}
    assert f"commitment:{selected_commitment['id']}" in near_ids
    assert f"calendar:{selected_meeting['id']}" in near_ids
    assert f"review:{review.json()['id']}" in near_ids
    assert any(item["kind"] == "contract notice" for item in data["near_term"])
    assert all("Americas private" not in item["title"] for item in data["near_term"])
    assert data["operator_view"]["body"].startswith("Growth remains possible")
    assert data["review_trail"][0]["participants"] == [operator["name"]]
    assert other_ask["id"] not in str(data)
    assert client.get("/api/documents", params={"account_id": account["id"]}).json() == before_documents
    after_checkpoints = client.app.state.conn.execute(
        "SELECT COUNT(*) FROM account_change_checkpoints WHERE account_id=?", (account["id"],)
    ).fetchone()[0]
    assert after_checkpoints == before_checkpoints


def test_leadership_names_missing_stale_and_missed_contract_evidence(client):
    account = client.post("/api/accounts", json={"name": "Leadership Gaps"}).json()
    client.post(f"/api/accounts/{account['id']}/operator-views", json={
        "body": "This point of view is intentionally old.", "assessed_on": utc_day(-40),
    })
    contract = client.post("/api/contracts", json={
        "account_id": account["id"], "version_label": "gap-v1",
        "renewal_date": utc_day(10), "notice_period_days": 30,
    })
    assert contract.status_code == 201, contract.text

    response = client.get(f"/api/accounts/{account['id']}/command-center/leadership")
    assert response.status_code == 200, response.text
    data = response.json()
    assert {item["value"] for item in data["standing"]["statuses"]} == {"unknown"}
    assert data["standing"]["forecast"] == []
    stuck_ids = {item["id"] for item in data["stuck"]}
    assert {"status:delivery:missing", "status:commercial:missing", "forecast:missing"} <= stuck_ids
    assert any(item_id.startswith("operator_view:") and item_id.endswith(":stale") for item_id in stuck_ids)
    assert f"contract:{contract.json()['id']}:notice-overdue" in stuck_ids
