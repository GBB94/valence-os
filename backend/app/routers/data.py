import csv
import io
import sqlite3

from fastapi import APIRouter, Depends, HTTPException

from .. import audit, repo
from ..db import new_id, now_utc
from ..deps import get_conn
from ..schemas import (
    BenchmarkCreate, MetricDefinitionCreate, MetricImport, MetricObservationCreate,
    ValueStoryCreate,
)

router = APIRouter(prefix="/api", tags=["data"])


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
    return repo.insert(conn, "metric_observations", b.model_dump(), object_type="metric_observation")


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
        card = {"definition": d, "observation": repo.row_to_dict(obs), "stale": False, "display_value": None}
        if obs and obs["current_through"]:
            from datetime import date
            try:
                age = (date.fromisoformat(today) - date.fromisoformat(obs["current_through"])).days
                card["stale"] = age > d["stale_after_days"]
            except ValueError:
                card["stale"] = True
        card["display_value"] = "unknown" if (not obs or card["stale"]) else obs["value"]
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
        # duplicate = same definition+period+program already observed (would supersede)
        if row["definition_id"] and row["period_label"]:
            dup = conn.execute(
                "SELECT 1 FROM metric_observations WHERE archived=0 AND definition_id=? AND period_label=? "
                "AND IFNULL(program_id,'')=IFNULL(?, '')",
                (row["definition_id"], row["period_label"], row["program_id"]),
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
    with conn:
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
                "AND period_label=? AND IFNULL(program_id,'')=IFNULL(?, '')",
                (ts, r["definition_id"], r["period_label"], r["program_id"]),
            )
            obs = {"id": new_id(), "definition_id": r["definition_id"], "definition_version": "1",
                   "program_id": r["program_id"], "cohort_label": r["cohort_label"],
                   "period_label": r["period_label"], "value": r["value_num"],
                   "unit": r["unit"], "target": float(r["target"]) if r["target"] else None,
                   "current_through": b.current_through, "import_batch_id": batch_id,
                   "created_at": ts, "updated_at": ts}
            conn.execute(
                f"INSERT INTO metric_observations ({','.join(obs)}) VALUES ({','.join('?' for _ in obs)})",
                tuple(obs.values()),
            )
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
        "job_worker": "none configured yet (single in-process worker arrives with v4 jobs)",
        "import_batches": batches,
        "failed_or_rolled_back": sum(1 for b in batches if b["status"] == "rolled_back"),
        "audit_events": audit_count,
        "source_freshness": fresh,
        "backup": {"rpo_hours": 24, "last_restore_test": None, "note": "mock/local mode — backups apply in production mode"},
    }
