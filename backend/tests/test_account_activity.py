"""Release 2 typed activity-projection contract."""
import os
import tempfile

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.account_activity import ActivityItem, adapter_names, project_account_activity


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
            as_of="2026-08-03T15:00:00+00:00",
        )

    assert adapter_names() == ("interaction",)
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
