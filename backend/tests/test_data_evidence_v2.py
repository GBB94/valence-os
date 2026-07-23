"""v2 tests — metric freshness (stale=unknown), benchmarks require population/period,
value-story visibility, the QBR generator's by-construction exclusion, and the CSV
import adapter with supersede + rollback.
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
    os.environ["ACCOUNT_OS_DB"] = path
    from app.main import app
    with TestClient(app) as c:
        yield c
    for s in ("", "-wal", "-shm"):
        try: os.unlink(path + s)
        except FileNotFoundError: pass


def _today():
    from app.db import now_utc
    return now_utc()[:10]


def _days(n):
    return (date.fromisoformat(_today()) + timedelta(days=n)).isoformat()


def test_scoreboard_renders_stale_as_unknown(client):
    d = client.post("/api/metric-definitions", json={"name": "Activation", "stale_after_days": 30}).json()
    # fresh observation -> value; stale -> unknown
    client.post("/api/metric-observations", json={"definition_id": d["id"], "value": 0.72, "current_through": _days(-5)})
    sb = client.get("/api/scoreboard").json()
    card = next(c for c in sb["cards"] if c["definition"]["id"] == d["id"])
    assert card["display_value"] == 0.72 and card["stale"] is False

    d2 = client.post("/api/metric-definitions", json={"name": "WeeklyReturn", "stale_after_days": 30}).json()
    client.post("/api/metric-observations", json={"definition_id": d2["id"], "value": 0.41, "current_through": _days(-90)})
    sb = client.get("/api/scoreboard").json()
    card2 = next(c for c in sb["cards"] if c["definition"]["id"] == d2["id"])
    assert card2["stale"] is True and card2["display_value"] == "unknown"  # never carried-forward good state


def test_benchmark_requires_population_and_period(client):
    assert client.post("/api/benchmarks", json={"name": "x", "value": 0.65}).status_code == 422
    ok = client.post("/api/benchmarks", json={"name": "x", "value": 0.65, "population": "F100", "period": "H1 2026", "source": "internal"})
    assert ok.status_code == 201


def test_qbr_excludes_internal_and_negative_by_construction(client):
    a = client.post("/api/accounts", json={"name": "Acme"}).json()
    p = client.post("/api/programs", json={"account_id": a["id"], "name": "P"}).json()
    # promoted, internal, and negative value stories
    client.post("/api/value-stories", json={"account_id": a["id"], "outcome": "PROMOTED win", "visibility_class": "qbr_exec", "evidence_tier": "measured_operational"})
    client.post("/api/value-stories", json={"account_id": a["id"], "outcome": "INTERNAL only note", "visibility_class": "internal"})
    client.post("/api/value-stories", json={"account_id": a["id"], "outcome": "NEGATIVE objection", "visibility_class": "internal", "is_negative": True})
    client.post("/api/commitments", json={"program_id": p["id"], "description": "client commitment",
                                          "responsible_party_id": _person(client, a), "internal_owner_id": _person(client, a, "v"), "due_date": _days(10)})
    qbr = client.get(f"/api/accounts/{a['id']}/qbr").json()
    outcomes = [v["outcome"] for v in qbr["value_stories"]]
    assert "PROMOTED win" in outcomes
    assert "INTERNAL only note" not in outcomes      # not promoted -> excluded by construction
    assert "NEGATIVE objection" not in outcomes       # negative evidence never client-facing
    assert qbr["open_commitments"] and qbr["stamp"]["data_current_through"]


def test_qbr_metrics_stale_shows_unknown(client):
    a = client.post("/api/accounts", json={"name": "Acme"}).json()
    d = client.post("/api/metric-definitions", json={"name": "Activation", "stale_after_days": 30}).json()
    client.post("/api/metric-observations", json={"definition_id": d["id"], "value": 0.9, "current_through": _days(-120)})
    qbr = client.get(f"/api/accounts/{a['id']}/qbr").json()
    m = next(m for m in qbr["metrics"] if m["name"] == "Activation")
    assert m["value"] == "unknown"
    assert "Activation" in qbr["stamp"]["missing_or_stale_sources"]


def test_csv_import_preview_commit_supersede_rollback(client):
    d = client.post("/api/metric-definitions", json={"name": "Activation"}).json()
    csv1 = f"definition_id,period_label,value\n{d['id']},2026-06,0.70\n{d['id']},2026-07,0.72\n"
    # preview does not write
    pv = client.post("/api/imports/metric-observations/preview", json={"csv_text": csv1, "current_through": _days(-2)}).json()
    assert pv["valid"] == 2 and pv["invalid"] == 0
    assert client.get("/api/scoreboard").json()["cards"][0]["observation"] is None

    commit = client.post("/api/imports/metric-observations/commit", json={"csv_text": csv1, "current_through": _days(-2)}).json()
    batch = commit["batch_id"]
    assert commit["committed"] == 2

    # re-import 2026-07 supersedes (old archived, one active for that period)
    csv2 = f"definition_id,period_label,value\n{d['id']},2026-07,0.80\n"
    client.post("/api/imports/metric-observations/commit", json={"csv_text": csv2, "current_through": _days(-1)})
    sb = client.get("/api/scoreboard").json().get("cards")[0]
    assert sb["observation"]["value"] == 0.80  # latest supersedes

    # rollback the first batch archives its (still-active) rows; idempotency guard
    rb = client.post(f"/api/imports/{batch}/rollback").json()
    assert rb["status"] == "rolled_back"
    assert client.post(f"/api/imports/{batch}/rollback").status_code == 409


def test_csv_import_rejects_bad_rows(client):
    bad = "definition_id,period_label,value\nnope,2026-06,abc\n"
    assert client.post("/api/imports/metric-observations/commit", json={"csv_text": bad}).status_code == 422


def test_operations_screen_reports_without_logs(client):
    d = client.post("/api/metric-definitions", json={"name": "Activation", "stale_after_days": 30}).json()
    client.post("/api/metric-observations", json={"definition_id": d["id"], "value": 0.5, "current_through": _days(-120)})
    ops = client.get("/api/operations").json()
    assert ops["source_freshness"] and ops["source_freshness"][0]["stale"] is True
    assert "job_worker" in ops and "audit_events" in ops


def _person(client, a, kind="c"):
    aff = "valence" if kind == "v" else "client"
    return client.post("/api/persons", json={"name": kind, "affiliation": aff, "account_id": a["id"] if kind == "c" else None}).json()["id"]
