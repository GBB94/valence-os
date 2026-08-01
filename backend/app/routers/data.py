import csv
import io
import sqlite3

from fastapi import APIRouter, Depends, HTTPException

from .. import adapters, audit, connections, expansion, repo
from ..db import new_id, now_utc
from ..deps import get_conn
from ..schemas import (
    BenchmarkCreate, MetricDefinitionCreate, MetricImport, MetricObservationCreate,
    ValueStoryCreate,
)

router = APIRouter(prefix="/api", tags=["data"])


@router.get("/accounts/{account_id}/metric-observations")
def account_metric_observations(account_id: str, conn: sqlite3.Connection = Depends(get_conn)):
    """Evidence picker read: only observations attributable to this account by program or
    stable population identity. Unscoped legacy observations stay out."""
    repo.get_row(conn, "accounts", account_id)
    rows = conn.execute(
        "SELECT mo.*, md.name metric_name, ps.name segment_name, pv.name view_name, pr.name program_name "
        "FROM metric_observations mo JOIN metric_definitions md ON md.id=mo.definition_id "
        "LEFT JOIN programs pr ON pr.id=mo.program_id "
        "LEFT JOIN population_segments ps ON ps.id=mo.population_segment_id "
        "LEFT JOIN population_views pv ON pv.id=mo.population_view_id "
        "WHERE mo.archived=0 AND (pr.account_id=? OR ps.account_id=? OR pv.account_id=?) "
        "ORDER BY mo.current_through DESC, md.name", (account_id, account_id, account_id)).fetchall()
    return [expansion.suppress_observation(conn, dict(r)) for r in rows]


def _observation_account(conn, values: dict) -> str | None:
    accounts = set()
    if values.get("program_id"):
        accounts.add(repo.get_row(conn, "programs", values["program_id"])["account_id"])
    if values.get("population_segment_id"):
        accounts.add(repo.get_row(conn, "population_segments",
                                  values["population_segment_id"])["account_id"])
    if values.get("population_view_id"):
        accounts.add(repo.get_row(conn, "population_views", values["population_view_id"])["account_id"])
    if len(accounts) > 1:
        raise HTTPException(422, "observation program and population belong to different accounts")
    return next(iter(accounts), None)


def _auto_link_observation(conn, observation: dict) -> None:
    """Exact stable-key matches are safe to link automatically; free-text cohorts never are."""
    account_id = _observation_account(conn, observation)
    if not account_id:
        return
    targets = conn.execute(
        "SELECT id FROM value_targets WHERE archived=0 AND status='active' AND account_id=? "
        "AND definition_id=? AND IFNULL(segment_id,'')=IFNULL(?, '') "
        "AND IFNULL(view_id,'')=IFNULL(?, '') AND (? IS NULL OR timeframe_start IS NULL OR ? >= timeframe_start) "
        "AND (? IS NULL OR ? <= timeframe_end)",
        (account_id, observation["definition_id"], observation.get("population_segment_id"),
         observation.get("population_view_id"), observation.get("current_through"),
         observation.get("current_through"), observation.get("current_through"),
         observation.get("current_through"))).fetchall()
    ts = now_utc()
    for target in targets:
        conn.execute("INSERT OR IGNORE INTO value_target_evidence "
                     "(id,target_id,object_type,object_id,note,created_at,updated_at) "
                     "VALUES (?,?,'metric_observation',?,'Auto-linked by stable population identity',?,?)",
                     (new_id(), target["id"], observation["id"], ts, ts))


# --- Metric definitions & observations (ingested, never recomputed) ---
@router.post("/metric-definitions", status_code=201)
def create_definition(b: MetricDefinitionCreate, conn: sqlite3.Connection = Depends(get_conn)):
    return repo.insert(conn, "metric_definitions", b.model_dump(), object_type="metric_definition")


@router.get("/metric-definitions")
def list_definitions(conn: sqlite3.Connection = Depends(get_conn)):
    return repo.list_rows(conn, "metric_definitions", where="1=1 ORDER BY name")


@router.post("/metric-observations", status_code=201)
def create_observation(b: MetricObservationCreate, conn: sqlite3.Connection = Depends(get_conn)):
    repo.get_row(conn, "metric_definitions", b.definition_id)
    _observation_account(conn, b.model_dump())
    reason = expansion.cohort_suppression_reason(
        conn, b.population_segment_id, b.population_view_id)
    if reason:
        raise HTTPException(422, f"metric observation refused: {reason}; import a sufficiently aggregated cohort")
    observation = repo.insert(conn, "metric_observations", b.model_dump(), object_type="metric_observation")
    _auto_link_observation(conn, observation)
    return observation


@router.get("/scoreboard")
def scoreboard(conn: sqlite3.Connection = Depends(get_conn)):
    """Latest observation per definition, with freshness. Stale renders as unknown (never
    carried-forward good state) — enforced here, not left to the UI."""
    today = now_utc()[:10]
    defs = repo.list_rows(conn, "metric_definitions", where="1=1 ORDER BY name")
    out = []
    for d in defs:
        obs = conn.execute(
            "SELECT * FROM metric_observations WHERE archived=0 AND definition_id=? "
            "ORDER BY current_through DESC, created_at DESC LIMIT 1", (d["id"],)
        ).fetchone()
        safe_obs = expansion.suppress_observation(conn, repo.row_to_dict(obs)) if obs else None
        card = {"definition": d, "observation": safe_obs, "stale": False,
                "display_value": None, "suppressed": bool(safe_obs and safe_obs["suppressed"])}
        if obs and obs["current_through"]:
            from datetime import date
            try:
                age = (date.fromisoformat(today) - date.fromisoformat(obs["current_through"])).days
                card["stale"] = age > d["stale_after_days"]
            except ValueError:
                card["stale"] = True
        card["display_value"] = ("suppressed" if card["suppressed"] else
                                 "unknown" if (not obs or card["stale"]) else obs["value"])
        # trend series for the sparkline (Section 6b) — last ~8 observations by period
        series = conn.execute(
            "SELECT period_label,value,target,population_segment_id,population_view_id "
            "FROM metric_observations WHERE archived=0 AND definition_id=? "
            "ORDER BY period_label DESC LIMIT 8", (d["id"],)).fetchall()
        card["series"] = [{"period": safe["period_label"], "value": safe["value"],
                           "target": safe["target"], "suppressed": safe["suppressed"]}
                          for safe in (expansion.suppress_observation(conn, dict(r))
                                       for r in reversed(series))]
        out.append(card)
    return {"as_of": today, "cards": out}


# --- Benchmarks (versioned, sourced; no hard-coded numbers) ---
@router.post("/benchmarks", status_code=201)
def create_benchmark(b: BenchmarkCreate, conn: sqlite3.Connection = Depends(get_conn)):
    return repo.insert(conn, "benchmarks", b.model_dump(), object_type="benchmark")


@router.get("/benchmarks")
def list_benchmarks(conn: sqlite3.Connection = Depends(get_conn)):
    return repo.list_rows(conn, "benchmarks", where="1=1 ORDER BY name, version")


# --- Value-story library (incl. negative evidence) ---
@router.post("/value-stories", status_code=201)
def create_value_story(b: ValueStoryCreate, conn: sqlite3.Connection = Depends(get_conn)):
    return repo.insert(conn, "value_stories", b.model_dump(), object_type="value_story")


@router.get("/value-stories")
def list_value_stories(account_id: str | None = None, conn: sqlite3.Connection = Depends(get_conn)):
    where = "1=1" if not account_id else "account_id = ?"
    params = () if not account_id else (account_id,)
    return repo.list_rows(conn, "value_stories", where=where + " ORDER BY is_negative, evidence_tier DESC", params=params)


# --- CSV import adapter (validate, preview, dedupe, commit, rollback, freshness) ---
def _parse(csv_text: str, conn) -> list[dict]:
    reader = csv.DictReader(io.StringIO(csv_text.strip()))
    rows = []
    for i, raw in enumerate(reader, start=1):
        row = {"line": i, "definition_id": (raw.get("definition_id") or "").strip(),
               "period_label": (raw.get("period_label") or "").strip(),
               "value": (raw.get("value") or "").strip(),
               "program_id": (raw.get("program_id") or "").strip() or None,
               "population_segment_id": (raw.get("population_segment_id") or "").strip() or None,
               "population_view_id": (raw.get("population_view_id") or "").strip() or None,
               "cohort_label": (raw.get("cohort_label") or "").strip() or None,
               "target": (raw.get("target") or "").strip() or None,
               "unit": (raw.get("unit") or "").strip() or None,
               "errors": [], "duplicate": False}
        if not row["definition_id"]:
            row["errors"].append("missing definition_id")
        elif not conn.execute("SELECT 1 FROM metric_definitions WHERE id=?", (row["definition_id"],)).fetchone():
            row["errors"].append(f"unknown definition_id {row['definition_id']}")
        try:
            row["value_num"] = float(row["value"])
        except ValueError:
            row["errors"].append("value not numeric")
        if row["population_segment_id"] and row["population_view_id"]:
            row["errors"].append("use one population_segment_id or population_view_id, not both")
        population_account = None
        if row["population_segment_id"]:
            segment = conn.execute("SELECT account_id FROM population_segments WHERE id=? AND archived=0",
                                   (row["population_segment_id"],)).fetchone()
            if not segment:
                row["errors"].append(f"unknown population_segment_id {row['population_segment_id']}")
            else:
                population_account = segment["account_id"]
        if row["population_view_id"]:
            view = conn.execute("SELECT account_id FROM population_views WHERE id=? AND archived=0",
                                (row["population_view_id"],)).fetchone()
            if not view:
                row["errors"].append(f"unknown population_view_id {row['population_view_id']}")
            else:
                population_account = view["account_id"]
        if row["program_id"]:
            program = conn.execute("SELECT account_id FROM programs WHERE id=? AND archived=0",
                                   (row["program_id"],)).fetchone()
            if not program:
                row["errors"].append(f"unknown program_id {row['program_id']}")
            elif population_account and program["account_id"] != population_account:
                row["errors"].append("program and population belong to different accounts")
        if not row["errors"]:
            reason = expansion.cohort_suppression_reason(
                conn, row["population_segment_id"], row["population_view_id"])
            if reason:
                row["errors"].append(f"metric observation refused: {reason}")
        # duplicate = same definition+period+program already observed (would supersede)
        if row["definition_id"] and row["period_label"]:
            dup = conn.execute(
                "SELECT 1 FROM metric_observations WHERE archived=0 AND definition_id=? AND period_label=? "
                "AND IFNULL(program_id,'')=IFNULL(?, '') "
                "AND IFNULL(population_segment_id,'')=IFNULL(?, '') "
                "AND IFNULL(population_view_id,'')=IFNULL(?, '')",
                (row["definition_id"], row["period_label"], row["program_id"],
                 row["population_segment_id"], row["population_view_id"]),
            ).fetchone()
            row["duplicate"] = bool(dup)
        rows.append(row)
    return rows


@router.post("/imports/metric-observations/preview")
def import_preview(b: MetricImport, conn: sqlite3.Connection = Depends(get_conn)):
    rows = _parse(b.csv_text, conn)
    return {"adapter": "csv_metric_observations", "current_through": b.current_through,
            "rows": rows, "valid": sum(1 for r in rows if not r["errors"]),
            "invalid": sum(1 for r in rows if r["errors"]),
            "duplicates": sum(1 for r in rows if r["duplicate"])}


@router.post("/imports/metric-observations/commit")
def import_commit(b: MetricImport, conn: sqlite3.Connection = Depends(get_conn)):
    rows = _parse(b.csv_text, conn)
    bad = [r for r in rows if r["errors"]]
    if bad:
        raise HTTPException(422, {"message": "fix errors before committing", "rows": bad})
    ts = now_utc()
    batch_id = new_id()
    source_id = new_id() if b.source_label else None
    with conn:
        if source_id:
            conn.execute("INSERT INTO source_references (id,type,label,created_at,updated_at) "
                         "VALUES (?,'data_report',?,?,?)", (source_id, b.source_label, ts, ts))
            audit.record(conn, object_type="source_reference", object_id=source_id, action="create",
                         after={"id": source_id, "type": "data_report", "label": b.source_label})
        conn.execute(
            "INSERT INTO import_batches (id, adapter, source_label, status, row_count, current_through, created_at, committed_at) "
            "VALUES (?,?,?,'committed',?,?,?,?)",
            (batch_id, "csv_metric_observations", b.source_label, len(rows), b.current_through, ts, ts),
        )
        audit.record(conn, object_type="import_batch", object_id=batch_id, action="create",
                     after={"rows": len(rows), "adapter": "csv_metric_observations"})
        for r in rows:
            # supersede: imported observations are superseded, not deleted
            conn.execute(
                "UPDATE metric_observations SET archived=1, archived_at=? WHERE archived=0 AND definition_id=? "
                "AND period_label=? AND IFNULL(program_id,'')=IFNULL(?, '') "
                "AND IFNULL(population_segment_id,'')=IFNULL(?, '') "
                "AND IFNULL(population_view_id,'')=IFNULL(?, '')",
                (ts, r["definition_id"], r["period_label"], r["program_id"],
                 r["population_segment_id"], r["population_view_id"]),
            )
            obs = {"id": new_id(), "definition_id": r["definition_id"], "definition_version": "1",
                   "program_id": r["program_id"], "cohort_label": r["cohort_label"],
                   "population_segment_id": r["population_segment_id"],
                   "population_view_id": r["population_view_id"],
                   "period_label": r["period_label"], "value": r["value_num"],
                   "unit": r["unit"], "target": float(r["target"]) if r["target"] else None,
                   "current_through": b.current_through, "import_batch_id": batch_id,
                   "source_reference_id": source_id,
                   "created_at": ts, "updated_at": ts}
            conn.execute(
                f"INSERT INTO metric_observations ({','.join(obs)}) VALUES ({','.join('?' for _ in obs)})",
                tuple(obs.values()),
            )
            _auto_link_observation(conn, obs)
    return {"batch_id": batch_id, "committed": len(rows)}


@router.post("/imports/{batch_id}/rollback")
def import_rollback(batch_id: str, conn: sqlite3.Connection = Depends(get_conn)):
    batch = conn.execute("SELECT * FROM import_batches WHERE id=?", (batch_id,)).fetchone()
    if not batch:
        raise HTTPException(404, "batch not found")
    if batch["status"] == "rolled_back":
        raise HTTPException(409, "already rolled back")
    ts = now_utc()
    with conn:
        conn.execute("UPDATE metric_observations SET archived=1, archived_at=? WHERE import_batch_id=? AND archived=0",
                     (ts, batch_id))
        conn.execute("UPDATE import_batches SET status='rolled_back', rolled_back_at=? WHERE id=?", (ts, batch_id))
        audit.record(conn, object_type="import_batch", object_id=batch_id, action="update",
                     before=dict(batch), after={"status": "rolled_back"})
    return {"batch_id": batch_id, "status": "rolled_back"}


# --- Operations screen (derived): no server logs needed to see when it's broken ---
@router.get("/operations")
def operations(conn: sqlite3.Connection = Depends(get_conn)):
    today = now_utc()[:10]
    batches = [repo.row_to_dict(r) for r in conn.execute(
        "SELECT * FROM import_batches ORDER BY created_at DESC LIMIT 20")]
    audit_count = conn.execute("SELECT COUNT(*) c FROM audit_events").fetchone()["c"]
    # freshness of each metric source
    from datetime import date
    fresh = []
    for d in repo.list_rows(conn, "metric_definitions", where="1=1 ORDER BY name"):
        obs = conn.execute("SELECT MAX(current_through) m FROM metric_observations WHERE archived=0 AND definition_id=?",
                           (d["id"],)).fetchone()["m"]
        stale = True
        if obs:
            try:
                stale = (date.fromisoformat(today) - date.fromisoformat(obs)).days > d["stale_after_days"]
            except ValueError:
                stale = True
        fresh.append({"metric": d["name"], "current_through": obs, "stale": stale})
    return {
        "as_of": today,
        "job_worker": "in-process queue; background polling is env-gated, API sync drains synchronously",
        "import_batches": batches,
        "failed_or_rolled_back": sum(1 for b in batches if b["status"] == "rolled_back"),
        "audit_events": audit_count,
        "source_freshness": fresh,
        "mock_adapters": [
            {"name": "calendar", "mode": "mock", "fixtures": len(adapters.list_calendar_fixtures()),
             "records": conn.execute("SELECT COUNT(*) n FROM calendar_events WHERE archived=0").fetchone()["n"]},
            {"name": "org change", "mode": "mock", "fixtures": len(adapters.list_org_change_fixtures()),
             "records": conn.execute("SELECT COUNT(*) n FROM org_change_flags WHERE archived=0").fetchone()["n"]},
            {"name": "population headcount", "mode": "mock", "fixtures": len(adapters.fetch_headcount_observations()),
             "records": conn.execute("SELECT COUNT(*) n FROM population_headcount_observations WHERE archived=0").fetchone()["n"]},
        ],
        "connection_registry": connections.registry_snapshot(),
        "backup": {"rpo_hours": 24, "restore_test": "passing (account export → restore round-trip, tests/test_portfolio_io.py)",
                   "export": "per-account export/restore available (GET /accounts/{id}/export, POST /accounts/import)",
                   "note": "mock/local mode — encrypted off-site backups apply in production mode"},
    }
