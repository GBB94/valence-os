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
    os.environ["VALENCE_OS_DB"] = path
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


def _source(client, label="Mock evidence"):
    return client.post("/api/source-references", json={"label": label, "type": "data_report"}).json()["id"]


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
    source = _source(client)
    # promoted, internal, and negative value stories
    client.post("/api/value-stories", json={"account_id": a["id"], "outcome": "PROMOTED win", "visibility_class": "qbr_exec", "evidence_tier": "measured_operational", "source_reference_id": source})
    client.post("/api/value-stories", json={"account_id": a["id"], "outcome": "INTERNAL only note", "visibility_class": "internal"})
    client.post("/api/value-stories", json={"account_id": a["id"], "outcome": "NEGATIVE objection", "visibility_class": "internal", "is_negative": True})
    promoted_c = client.post("/api/commitments", json={"program_id": p["id"], "description": "PROMOTED commitment",
                                                       "responsible_party_id": _person(client, a), "internal_owner_id": _person(client, a, "v"), "due_date": _days(10), "source_reference_id": source}).json()
    client.post("/api/map/promote", json={"object_type": "commitment", "object_id": promoted_c["id"], "client_visible": True})
    qbr = client.get(f"/api/accounts/{a['id']}/qbr").json()
    outcomes = [v["outcome"] for v in qbr["value_stories"]]
    assert "PROMOTED win" in outcomes
    assert "INTERNAL only note" not in outcomes      # not promoted -> excluded by construction
    assert "NEGATIVE objection" not in outcomes       # negative evidence never client-facing
    assert qbr["open_commitments"] and qbr["stamp"]["data_current_through"]


def test_qbr_commitments_require_promotion(client):
    """A QBR is client-facing, so it carries only affirmatively-promoted commitments —
    the same rule the mutual action plan enforces. An un-promoted commitment is internal."""
    a = client.post("/api/accounts", json={"name": "Acme"}).json()
    p = client.post("/api/programs", json={"account_id": a["id"], "name": "P"}).json()
    source = _source(client)
    rp, io = _person(client, a), _person(client, a, "v")
    shared = client.post("/api/commitments", json={"program_id": p["id"], "description": "SHARED commitment",
                                                   "responsible_party_id": rp, "internal_owner_id": io, "due_date": _days(10), "source_reference_id": source}).json()
    client.post("/api/commitments", json={"program_id": p["id"], "description": "INTERNAL commitment",
                                          "responsible_party_id": rp, "internal_owner_id": io, "due_date": _days(10)})
    client.post("/api/map/promote", json={"object_type": "commitment", "object_id": shared["id"], "client_visible": True})

    descriptions = [c["description"] for c in client.get(f"/api/accounts/{a['id']}/qbr").json()["open_commitments"]]
    assert "SHARED commitment" in descriptions
    assert "INTERNAL commitment" not in descriptions


def test_qbr_metrics_stale_shows_unknown(client):
    a = client.post("/api/accounts", json={"name": "Acme"}).json()
    p = client.post("/api/programs", json={"account_id": a["id"], "name": "P"}).json()
    d = client.post("/api/metric-definitions", json={"name": "Activation", "stale_after_days": 30}).json()
    client.post("/api/metric-observations", json={"definition_id": d["id"], "program_id": p["id"], "value": 0.9, "current_through": _days(-120), "source_reference_id": _source(client)})
    qbr = client.get(f"/api/accounts/{a['id']}/qbr").json()
    m = next(m for m in qbr["metrics"] if m["name"] == "Activation")
    assert m["value"] == "unknown"
    assert "Activation" in qbr["stamp"]["missing_or_stale_sources"]


def test_qbr_metrics_are_account_scoped(client):
    """Metric definitions are global; observations are not. One account's client-facing QBR
    must never render another account's numbers, and an observation with no program is
    unattributable and never reaches a client artifact."""
    a1 = client.post("/api/accounts", json={"name": "Acme"}).json()
    a2 = client.post("/api/accounts", json={"name": "Globex"}).json()
    p1 = client.post("/api/programs", json={"account_id": a1["id"], "name": "P1"}).json()
    p2 = client.post("/api/programs", json={"account_id": a2["id"], "name": "P2"}).json()
    d = client.post("/api/metric-definitions", json={"name": "Activation", "stale_after_days": 30}).json()
    other = client.post("/api/metric-definitions", json={"name": "Adoption", "stale_after_days": 30}).json()
    source = _source(client)
    client.post("/api/metric-observations", json={"definition_id": d["id"], "program_id": p1["id"], "value": 0.40, "current_through": _days(-2), "source_reference_id": source})
    client.post("/api/metric-observations", json={"definition_id": d["id"], "program_id": p2["id"], "value": 0.95, "current_through": _days(-1), "source_reference_id": source})
    # unattributable: no program, and more recent than either of the above
    client.post("/api/metric-observations", json={"definition_id": other["id"], "value": 0.99, "current_through": _today()})

    m1 = {m["name"]: m["value"] for m in client.get(f"/api/accounts/{a1['id']}/qbr").json()["metrics"]}
    m2 = {m["name"]: m["value"] for m in client.get(f"/api/accounts/{a2['id']}/qbr").json()["metrics"]}
    assert m1["Activation"] == 0.40          # not 0.95 — the newer observation belongs to Globex
    assert m2["Activation"] == 0.95
    assert "Adoption" not in m1 and "Adoption" not in m2


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


def test_csv_import_identity_includes_stable_population(client):
    a = client.post("/api/accounts", json={"name": "Acme"}).json()
    part = client.post("/api/population-partitions", json={
        "account_id": a["id"], "total_fte": 1000}).json()
    s1 = client.post("/api/population-segments", json={
        "partition_id": part["id"], "name": "North", "headcount": 500}).json()
    s2 = client.post("/api/population-segments", json={
        "partition_id": part["id"], "name": "South", "headcount": 500}).json()
    d = client.post("/api/metric-definitions", json={"name": "Activation"}).json()
    for segment, value in ((s1, .7), (s2, .8)):
        csv = ("definition_id,period_label,value,population_segment_id\n"
               f"{d['id']},2026-Q3,{value},{segment['id']}\n")
        assert client.post("/api/imports/metric-observations/commit", json={
            "csv_text": csv, "current_through": _today(), "source_label": "Cohort report"
        }).status_code == 200
    rows = client.app.state.conn.execute(
        "SELECT population_segment_id,value FROM metric_observations "
        "WHERE definition_id=? AND archived=0", (d["id"],)).fetchall()
    assert {(r["population_segment_id"], r["value"]) for r in rows} == {
        (s1["id"], .7), (s2["id"], .8)}


def test_target_realization_uses_linked_matching_evidence_inside_timeframe(client):
    a = client.post("/api/accounts", json={"name": "Acme"}).json()
    p = client.post("/api/programs", json={"account_id": a["id"], "name": "P"}).json()
    part = client.post("/api/population-partitions", json={
        "account_id": a["id"], "total_fte": 500}).json()
    seg = client.post("/api/population-segments", json={
        "partition_id": part["id"], "name": "North", "headcount": 500}).json()
    d = client.post("/api/metric-definitions", json={"name": "Activation"}).json()
    source = _source(client)
    target = client.post("/api/value-targets", json={
        "account_id": a["id"], "definition_id": d["id"], "segment_id": seg["id"],
        "target_value": .75, "timeframe_start": _days(-30), "timeframe_end": _days(30)}).json()
    # Same metric/cohort but before the agreed measurement window: it must not prove the target.
    first_obs = client.post("/api/metric-observations", json={
        "definition_id": d["id"], "program_id": p["id"], "population_segment_id": seg["id"],
        "value": .9, "current_through": _days(-60), "source_reference_id": source}).json()
    first = client.get(f"/api/accounts/{a['id']}/ledger").json()["targets"][0]
    assert first["realization"]["value"] is None
    # Inside the window: the API auto-links the exact stable cohort and realization can use it.
    obs = client.post("/api/metric-observations", json={
        "definition_id": d["id"], "program_id": p["id"], "population_segment_id": seg["id"],
        "value": .8, "current_through": _today(), "source_reference_id": source}).json()
    second = client.get(f"/api/accounts/{a['id']}/ledger").json()["targets"][0]
    assert second["realization"]["value"] == .8
    assert second["realization"]["observation_id"] == obs["id"]
    assert any(e["object_id"] == obs["id"] for e in second["evidence"])
    picker = client.get(f"/api/accounts/{a['id']}/metric-observations").json()
    assert {r["id"] for r in picker} == {obs["id"], first_obs["id"]}


def test_operations_screen_reports_without_logs(client):
    d = client.post("/api/metric-definitions", json={"name": "Activation", "stale_after_days": 30}).json()
    client.post("/api/metric-observations", json={"definition_id": d["id"], "value": 0.5, "current_through": _days(-120)})
    ops = client.get("/api/operations").json()
    assert ops["source_freshness"] and ops["source_freshness"][0]["stale"] is True
    assert "job_worker" in ops and "audit_events" in ops


def _person(client, a, kind="c"):
    aff = "valence" if kind == "v" else "client"
    return client.post("/api/persons", json={"name": kind, "affiliation": aff, "account_id": a["id"] if kind == "c" else None}).json()["id"]
