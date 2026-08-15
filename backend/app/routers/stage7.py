"""Stage 7 API: mock adapter sync, signal actions, calendar, and org-change confirmation."""
import json
import sqlite3

from fastapi import APIRouter, Depends, HTTPException

from .. import adapters, jobs, repo, stage7, stage75
from ..deps import get_conn
from ..schemas import CalendarEventCreate, OrgChangeAction, SignalDismiss, SuccessionComplete

router = APIRouter(prefix="/api", tags=["stage7"])


def _run_now(conn, kind):
    job = jobs.enqueue(conn, kind, {})
    jobs.run_pending(conn)
    done = jobs.get_job(conn, job["id"])
    result = json.loads(done["result_json"]) if done and done["result_json"] else None
    return {"job_id": job["id"], "status": done["status"] if done else "queued", "result": result}


@router.get("/stage7/fixtures")
def fixture_inventory():
    return {"calendar": adapters.list_calendar_fixtures(),
            "org_changes": adapters.list_org_change_fixtures(),
            "headcount_rows": len(adapters.fetch_headcount_observations())}


@router.post("/ingest/calendar/sync")
def sync_calendar(conn: sqlite3.Connection = Depends(get_conn)):
    return _run_now(conn, "sync_calendar")


@router.post("/ingest/org-changes/sync")
def sync_org_changes(conn: sqlite3.Connection = Depends(get_conn)):
    return _run_now(conn, "sync_org_changes")


@router.post("/ingest/headcount/sync")
def sync_headcount(conn: sqlite3.Connection = Depends(get_conn)):
    return _run_now(conn, "sync_headcount")


@router.get("/accounts/{account_id}/calendar-events")
def calendar_events(account_id: str, conn: sqlite3.Connection = Depends(get_conn)):
    repo.get_row(conn, "accounts", account_id)
    events = repo.list_rows(conn, "calendar_events",
                            where="account_id=? ORDER BY starts_at", params=(account_id,))
    for event in events:
        event["attendees"] = [dict(r) for r in conn.execute(
            "SELECT cea.*, p.name person_name FROM calendar_event_attendees cea "
            "LEFT JOIN persons p ON p.id=cea.person_id WHERE cea.event_id=? ORDER BY cea.name",
            (event["id"],)).fetchall()]
    return {"events": events}


@router.post("/calendar-events", status_code=201)
def create_calendar_event(body: CalendarEventCreate,
                          conn: sqlite3.Connection = Depends(get_conn)):
    if body.program_id and repo.get_row(conn, "programs", body.program_id)["account_id"] != body.account_id:
        raise HTTPException(422, "program belongs to a different account")
    if body.cell_id and repo.get_row(conn, "whitespace_cells", body.cell_id)["account_id"] != body.account_id:
        raise HTTPException(422, "cell belongs to a different account")
    return stage7.write_calendar_event(conn, body.model_dump())


@router.get("/accounts/{account_id}/org-changes")
def org_changes(account_id: str, conn: sqlite3.Connection = Depends(get_conn)):
    repo.get_row(conn, "accounts", account_id)
    return {"flags": repo.list_rows(conn, "org_change_flags",
                                     where="account_id=? ORDER BY occurred_on DESC", params=(account_id,)),
            "successions": repo.list_rows(conn, "succession_records",
                                           where="account_id=? ORDER BY created_at DESC", params=(account_id,))}


@router.post("/org-change-flags/{flag_id}/confirm")
def confirm_org_change(flag_id: str, body: OrgChangeAction,
                       conn: sqlite3.Connection = Depends(get_conn)):
    return stage7.confirm_org_change(conn, flag_id, body.actor)


@router.post("/org-change-flags/{flag_id}/dismiss")
def dismiss_org_change(flag_id: str, body: OrgChangeAction,
                       conn: sqlite3.Connection = Depends(get_conn)):
    if not body.reason:
        raise HTTPException(422, "dismissal reason is required")
    return stage7.dismiss_org_change(conn, flag_id, body.reason)


@router.post("/succession-records/{record_id}/complete")
def complete_succession(record_id: str, body: SuccessionComplete,
                        conn: sqlite3.Connection = Depends(get_conn)):
    return stage7.complete_succession(conn, record_id, body.successor_person_id, body.transfer_note)


@router.post("/signals/evaluate")
def evaluate_signals(conn: sqlite3.Connection = Depends(get_conn)):
    result = stage7.evaluate_domain_signals(conn)
    result["operational_agreements"] = stage75.evaluate_agreements(conn)
    return result


@router.get("/signal-episodes")
def signal_episodes(account_id: str | None = None, status: str | None = None,
                    conn: sqlite3.Connection = Depends(get_conn)):
    if status and status not in ("open","held","dismissed","converted","attached","closed"):
        raise HTTPException(422, "invalid signal status")
    return {"episodes": stage7.list_episodes(conn, account_id, status)}


@router.post("/signal-episodes/{episode_id}/dismiss")
def dismiss_signal(episode_id: str, body: SignalDismiss,
                   conn: sqlite3.Connection = Depends(get_conn)):
    return stage7.dismiss_episode(conn, episode_id, body.reason)


@router.post("/signal-episodes/{episode_id}/draft-opportunity", status_code=201)
def draft_opportunity(episode_id: str, conn: sqlite3.Connection = Depends(get_conn)):
    return stage7.draft_opportunity(conn, episode_id)
