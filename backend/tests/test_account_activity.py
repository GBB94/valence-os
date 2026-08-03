"""Release 2 typed activity-projection contract."""
import os
import sqlite3
import tempfile

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from pydantic import ValidationError

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
