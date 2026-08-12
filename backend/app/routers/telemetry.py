"""Account Path Slice 7 — product measurement API (`ACCOUNT-PATH-SPEC.md` §17).

These routes are the only way an event enters the sink, and they are separate from every domain
router on purpose: nothing here reads or writes a canonical record, and nothing in the domain
imports this module.

§17.3 asks an unknown event to be *rejected in development* and *ignored with a diagnostic in
production*. That branch lives here, in `strict_mode()`, and nowhere else — the client treats both
answers identically, because a measurement response can never change what the operator sees.
"""
import sqlite3

from fastapi import APIRouter, Body, Depends, HTTPException, Query

from .. import execution_path, surface_retirement, surface_usage, telemetry
from ..deps import get_conn

router = APIRouter(prefix="/api/telemetry", tags=["measurement"])


@router.post("/events", status_code=202)
def record_event(payload: dict = Body(...), conn: sqlite3.Connection = Depends(get_conn)):
    """Record one product event. Always 202 in production mode, even when the event is dropped.

    A 4xx here would train a client to retry, and a retry loop over a diagnostic sink is worse
    than the lost event it is trying to recover.
    """
    event_name = payload.get("event_name")
    fields = {
        "account_id": payload.get("account_id"),
        "program_id": payload.get("program_id"),
        "occurred_at": payload.get("occurred_at"),
        "session_id": payload.get("session_id"),
        "properties": payload.get("properties") or {},
        "ranking_rule_version": payload.get("ranking_rule_version"),
    }
    if telemetry.strict_mode():
        try:
            telemetry.validate(event_name, **fields)
        except telemetry.TelemetryRejected as exc:
            # Development only. The client still ignores the response body; this exists so a
            # contract mistake is visible while the events are being wired, rather than becoming
            # a silently empty funnel three weeks later.
            raise HTTPException(status_code=422, detail=str(exc)) from exc
    return telemetry.record(conn, event_name, **fields)


@router.get("/settings")
def get_settings(conn: sqlite3.Connection = Depends(get_conn)):
    return {**telemetry.settings(conn), "strict": telemetry.strict_mode(),
            "schema_version": telemetry.SCHEMA_VERSION,
            "events": sorted(telemetry.EVENTS)}


@router.patch("/settings")
def patch_settings(payload: dict = Body(...), conn: sqlite3.Connection = Depends(get_conn)):
    """§17.4: a local setting can disable measurement. Turning it off also clears what was kept."""
    try:
        return telemetry.set_settings(conn, enabled=payload.get("enabled"),
                                      retention_days=payload.get("retention_days"))
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/funnel")
def funnel(account_id: str | None = Query(default=None),
           conn: sqlite3.Connection = Depends(get_conn)):
    return telemetry.funnel(conn, account_id)


@router.get("/surface-usage")
def surface_usage_report(window_days: int | None = Query(default=None, ge=1, le=1200),
                         sort: str = Query(default="navigation"),
                         today: str | None = Query(default=None),
                         conn: sqlite3.Connection = Depends(get_conn)):
    """`SURFACE-USAGE-SPEC.md` §8. Four axes, a window that can refuse, and a caveat beside them.

    `sort` defaults to navigation order. `least_used` is available because an operator sometimes
    genuinely wants it, but it is never the default: a leaderboard sorted by disuse reads as a kill
    list, and its top row would be whichever surface has the least honest window.
    """
    return surface_usage.report(conn, today=today, window_days=window_days, sort=sort)


@router.post("/surface-usage/fold")
def fold_surface_usage(conn: sqlite3.Connection = Depends(get_conn)):
    """Advance the monthly rollup and purge past its 36-month retention. Idempotent."""
    result = surface_usage.fold(conn)
    result["purged_months"] = surface_usage.purge_expired_rollups(conn)
    return result


@router.get("/surface-usage/redundancy")
def surface_redundancy(conn: sqlite3.Connection = Depends(get_conn)):
    """`SURFACE-USAGE-SPEC.md` §7.0 — the manual pass the counts cannot do.

    Reads the registry, not the events: this is the complement to measurement, not part of it. Its
    output is a list of questions, and the app never answers one.
    """
    return surface_usage.redundancy_checklist(conn)


@router.get("/surface-retirement")
def retirement_state(conn: sqlite3.Connection = Depends(get_conn)):
    """§7.3. Every registered surface's current action, derived from the latest note.

    Every key is present, including the untouched ones. A caller that had to tell "not retired" from
    "absent from the response" would eventually get it wrong in the direction that hides something.
    """
    return {"surfaces": surface_retirement.state_of(conn),
            "vocabulary": surface_retirement.vocabulary()}


@router.get("/surface-retirement/history")
def retirement_history(surface: str | None = Query(default=None),
                       conn: sqlite3.Connection = Depends(get_conn)):
    """The table is append-only, so this is the whole story including every reversal."""
    return {"notes": surface_retirement.history(conn, surface)}


@router.post("/surface-retirement/preview")
def retirement_preview(payload: dict = Body(...), conn: sqlite3.Connection = Depends(get_conn)):
    """§7.8. Runs the same checks and the same projection Apply runs — never a parallel path."""
    return surface_retirement.preview(conn, payload.get("staged") or [],
                                      today=payload.get("today"))


@router.post("/surface-retirement/apply")
def retirement_apply(payload: dict = Body(...), conn: sqlite3.Connection = Depends(get_conn)):
    """All-or-nothing. A refusal is a 422 carrying the sentence, because unlike a dropped event
    this is a command the operator is waiting on and must be told about."""
    try:
        return surface_retirement.apply_batch(conn, payload.get("staged") or [],
                                              actor=payload.get("actor"),
                                              today=payload.get("today"))
    except surface_retirement.RetirementRefused as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/surface-retirement/undo")
def retirement_undo(payload: dict = Body(...), conn: sqlite3.Connection = Depends(get_conn)):
    try:
        return surface_retirement.undo_batch(conn, payload.get("batch_id") or "",
                                             actor=payload.get("actor"),
                                             today=payload.get("today"))
    except surface_retirement.RetirementRefused as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/surface-retirement/restore")
def retirement_restore(payload: dict = Body(...), conn: sqlite3.Connection = Depends(get_conn)):
    """§7.2's first-class rollback, available forever and independent of any batch."""
    try:
        return surface_retirement.restore(conn, payload.get("surface") or "",
                                          actor=payload.get("actor"))
    except surface_retirement.RetirementRefused as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/ranking-rules")
def ranking_rules():
    """The §17.6 registry. A candidate ruleset is listed so it can be compared, not selected."""
    return {
        "active_version": execution_path.active_ranking_version(),
        "flag": execution_path.RANKING_RULE_ENV,
        "versions": [
            {"version": version, "status": entry["status"], "summary": entry["summary"],
             "bands": entry["bands"]}
            for version, entry in sorted(execution_path.RANKING_RULE_VERSIONS.items())
        ],
    }


@router.post("/ranking-rules/compare")
def compare_ranking_rules(payload: dict = Body(...),
                          conn: sqlite3.Connection = Depends(get_conn)):
    """§17.6 step 4. Given no account list, compares across every unarchived account."""
    account_ids = payload.get("account_ids") or [
        row[0] for row in conn.execute("SELECT id FROM accounts WHERE archived=0 ORDER BY name")
    ]
    return execution_path.compare_rule_versions(
        conn, account_ids,
        payload.get("version_a") or execution_path.DEFAULT_RANKING_VERSION,
        payload.get("version_b") or "v2-candidate-notice-first")
