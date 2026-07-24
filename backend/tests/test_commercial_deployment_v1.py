"""v1 tests — expansion outcomes, contract versioning + overlay, phase gates,
compliance, scope changes, and the renewal-window queue trigger v1 enables.
"""
import os
import tempfile
from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client():
    fd, path = tempfile.mkstemp(suffix=".sqlite")
    os.close(fd)
    os.environ["VALENCE_OS_DB"] = path
    from app.main import app
    with TestClient(app) as c:
        yield c
    for s in ("", "-wal", "-shm"):
        try: os.unlink(path + s)
        except FileNotFoundError: pass


@pytest.fixture()
def acct_prog(client):
    a = client.post("/api/accounts", json={"name": "Acme"}).json()
    p = client.post("/api/programs", json={"account_id": a["id"], "name": "Rollout", "phase": "programmatic"}).json()
    return client, a, p


def test_expansion_close_requires_outcome_and_reason(acct_prog):
    c, a, _ = acct_prog
    xo = c.post("/api/expansions", json={"account_id": a["id"], "name": "3k seats", "target_seats": 3000}).json()
    assert xo["budget_state"] == "conceptually_supported" and xo["status"] == "open"
    # outcome enum is required by the schema; reason required too
    assert c.post(f"/api/expansions/{xo['id']}/close", json={"outcome": "won"}).status_code == 422
    ok = c.post(f"/api/expansions/{xo['id']}/close", json={"outcome": "won", "outcome_reason": "budget approved"})
    assert ok.status_code == 200 and ok.json()["status"] == "closed" and ok.json()["outcome"] == "won"
    assert c.post(f"/api/expansions/{xo['id']}/close", json={"outcome": "lost", "outcome_reason": "x"}).status_code == 409


def test_contract_supersede_keeps_history_and_overlay(acct_prog):
    c, a, _ = acct_prog
    v1 = c.post("/api/contracts", json={"account_id": a["id"], "version_label": "v1", "seats": 1000, "renewal_date": "2027-01-01"}).json()
    v2 = c.post("/api/contracts", json={"account_id": a["id"], "version_label": "v2", "seats": 1200, "supersedes_id": v1["id"]}).json()
    rows = c.get(f"/api/accounts/{a['id']}/contracts").json()
    by = {r["id"]: r for r in rows}
    assert by[v1["id"]]["is_current"] is False and by[v2["id"]]["is_current"] is True
    # overlay never overwrites canonical renewal_date
    ov = c.post(f"/api/contracts/{v1['id']}/overlay", json={
        "overlay_expected_decision_date": "2026-10-15", "overlay_rationale": "procurement lead time",
    }).json()
    assert ov["renewal_date"] == "2027-01-01"  # canonical untouched
    assert ov["overlay_expected_decision_date"] == "2026-10-15"


def test_phase_gate_autopasses_when_items_complete(acct_prog):
    c, _, p = acct_prog
    gate = c.post("/api/phase-gates", json={"program_id": p["id"], "name": "Launch", "items": ["a", "b"]}).json()
    assert gate["status"] == "open" and len(gate["items"]) == 2
    i1, i2 = gate["items"][0]["id"], gate["items"][1]["id"]
    c.post(f"/api/gate-items/{i1}/toggle", json={"complete": True})
    g = c.post(f"/api/gate-items/{i2}/toggle", json={"complete": True}).json()
    assert g["status"] == "passed"  # auto-passes when all items complete


def test_phase_gate_waive_requires_reason(acct_prog):
    c, _, p = acct_prog
    gate = c.post("/api/phase-gates", json={"program_id": p["id"], "name": "Launch", "items": ["x"]}).json()
    assert c.post(f"/api/phase-gates/{gate['id']}/waive", json={}).status_code == 422
    w = c.post(f"/api/phase-gates/{gate['id']}/waive", json={"waiver_reason": "exec sign-off"}).json()
    assert w["status"] == "waived" and w["waiver_reason"] == "exec sign-off"


def test_compliance_and_scope_and_delivery_aggregation(acct_prog):
    c, a, p = acct_prog
    c.post("/api/compliance-items", json={"program_id": p["id"], "lane": "works_council", "status": "blocked"})
    c.post("/api/scope-changes", json={"program_id": p["id"], "description": "added NL entity"})
    c.post("/api/deployment-moments", json={"program_id": p["id"], "name": "Review cycle", "type": "talent_calendar"})
    d = c.get(f"/api/programs/{p['id']}/delivery").json()
    assert len(d["compliance_items"]) == 1 and d["compliance_items"][0]["lane"] == "works_council"
    assert len(d["scope_changes"]) == 1 and len(d["deployment_moments"]) == 1


def test_renewal_window_queue_trigger(acct_prog):
    c, a, _ = acct_prog
    soon = (date(2026, 1, 1)).isoformat()  # placeholder, replaced below
    # a contract renewing ~90 days out should surface; one 2 years out should not
    near = c.post("/api/contracts", json={"account_id": a["id"], "version_label": "near", "seats": 500,
                                          "renewal_date": _in_days(90)}).json()
    c.post("/api/contracts", json={"account_id": a["id"], "version_label": "far", "seats": 500,
                                   "renewal_date": _in_days(900), "supersedes_id": near["id"]})
    # 'near' is no longer current after supersede; make a fresh current near-renewal
    cur = c.post("/api/contracts", json={"account_id": a["id"], "version_label": "cur", "seats": 500,
                                         "renewal_date": _in_days(100)}).json()
    q = c.get("/api/queue").json()
    keys = {i["key"] for i in q["items"]}
    assert f"renewal_window:contract_version:{cur['id']}" in keys
    item = next(i for i in q["items"] if i["object_id"] == cur["id"])
    assert item["priority"] == 3 and "Renewal in" in item["because"]


def _in_days(n):
    # tests must not call date.today(); derive from a fixed anchor near "now" via the API's own clock.
    # Use the queue's as_of to stay clock-consistent.
    from app.db import now_utc
    return (date.fromisoformat(now_utc()[:10]) + timedelta(days=n)).isoformat()
