"""Stage 14 company-intelligence API. Domain rules stay in company_intel.py."""
import json
import sqlite3

from fastapi import APIRouter, Depends, HTTPException

from .. import company_intel, jobs
from ..deps import get_conn
from ..schemas import (CompanyEventLinkCreate, CompanyIntelAction, CompanyLinkKeywordCreate,
                       CompanyWatchPut, IntelDocumentAction)

router = APIRouter(prefix="/api", tags=["company-intelligence"])


@router.get("/company-intel/fixtures")
def fixtures():
    from .. import adapters
    return {"fixtures": adapters.list_company_intel_fixtures()}


@router.get("/accounts/{account_id}/company")
def company_workspace(account_id: str, conn: sqlite3.Connection = Depends(get_conn)):
    return company_intel.account_workspace(conn, account_id)


@router.get("/accounts/{account_id}/company-watch")
def company_watch(account_id: str, conn: sqlite3.Connection = Depends(get_conn)):
    return company_intel.get_company(conn, account_id)


@router.put("/accounts/{account_id}/company-watch")
def put_company_watch(account_id: str, body: CompanyWatchPut,
                      conn: sqlite3.Connection = Depends(get_conn)):
    return company_intel.put_watch(conn, account_id, body.model_dump())


@router.post("/ingest/company-intel/sync")
def sync(conn: sqlite3.Connection = Depends(get_conn)):
    job = jobs.enqueue(conn, "sync_company_intel", {})
    jobs.run_pending(conn)
    done = jobs.get_job(conn, job["id"])
    result = json.loads(done["result_json"]) if done and done["result_json"] else None
    return {"job_id": job["id"], "status": done["status"] if done else "queued", "result": result}


@router.get("/accounts/{account_id}/intel/feed")
def feed(account_id: str, status: str | None = None,
         conn: sqlite3.Connection = Depends(get_conn)):
    if status and status not in {"proposed","confirmed","dismissed","superseded","retracted","invalidated"}:
        raise HTTPException(422, "invalid company event status")
    return {"events": company_intel.feed(conn, account_id, status)}


@router.get("/intel/events/{event_id}")
def event_detail(event_id: str, conn: sqlite3.Connection = Depends(get_conn)):
    event = company_intel.repo.get_row(conn, "company_events", event_id)
    rows = company_intel.feed(conn, event["account_id"])
    return next(row for row in rows if row["id"] == event_id)


@router.get("/accounts/{account_id}/intel/overlay")
def overlay(account_id: str, conn: sqlite3.Connection = Depends(get_conn)):
    return company_intel.overlay(conn, account_id)


@router.get("/accounts/{account_id}/intel/hiring")
def hiring(account_id: str, conn: sqlite3.Connection = Depends(get_conn)):
    company_intel.repo.get_row(conn, "accounts", account_id)
    return {"postings": [dict(row) for row in conn.execute(
        "SELECT * FROM hiring_postings WHERE account_id=? AND archived=0 ORDER BY last_seen_on DESC,title",
        (account_id,)).fetchall()], "observations": [dict(row) for row in conn.execute(
        "SELECT * FROM hiring_observations WHERE account_id=? AND archived=0 ORDER BY observed_on DESC,function_label,region_label",
        (account_id,)).fetchall()]}


@router.post("/intel/events/{event_id}/confirm")
def confirm_event(event_id: str, body: CompanyIntelAction,
                  conn: sqlite3.Connection = Depends(get_conn)):
    return company_intel.confirm_event(conn, event_id, body.actor)


@router.post("/intel/events/{event_id}/dismiss")
def dismiss_event(event_id: str, body: CompanyIntelAction,
                  conn: sqlite3.Connection = Depends(get_conn)):
    return company_intel.dismiss_event(conn, event_id, body.reason or "")


@router.post("/intel/documents/{document_id}/retract")
def retract_document(document_id: str, body: IntelDocumentAction,
                     conn: sqlite3.Connection = Depends(get_conn)):
    return company_intel.retract_document(conn, document_id, body.actor, body.reason)


@router.post("/intel/events/{event_id}/links", status_code=201)
def create_link(event_id: str, body: CompanyEventLinkCreate,
                conn: sqlite3.Connection = Depends(get_conn)):
    return company_intel.create_link(conn, event_id, body.model_dump())


@router.post("/intel/events/{event_id}/links/suggest")
def suggest_links(event_id: str, conn: sqlite3.Connection = Depends(get_conn)):
    return {"links": company_intel.suggest_links(conn, event_id)}


@router.post("/intel/events/{event_id}/links/{link_id}/confirm")
def confirm_link(event_id: str, link_id: str, body: CompanyIntelAction,
                 conn: sqlite3.Connection = Depends(get_conn)):
    row = company_intel.repo.get_row(conn, "company_event_links", link_id)
    if row["event_id"] != event_id:
        raise HTTPException(404, "link does not belong to event")
    return company_intel.confirm_link(conn, link_id, body.actor)


@router.post("/intel/events/{event_id}/links/{link_id}/dismiss")
def dismiss_link(event_id: str, link_id: str, body: CompanyIntelAction,
                 conn: sqlite3.Connection = Depends(get_conn)):
    row = company_intel.repo.get_row(conn, "company_event_links", link_id)
    if row["event_id"] != event_id:
        raise HTTPException(404, "link does not belong to event")
    return company_intel.dismiss_link(conn, link_id, body.reason or "")


@router.post("/accounts/{account_id}/intel/link-keywords", status_code=201)
def create_link_keyword(account_id: str, body: CompanyLinkKeywordCreate,
                        conn: sqlite3.Connection = Depends(get_conn)):
    return company_intel.create_link_keyword(conn, account_id, body.phrase, body.use_case_id)


@router.post("/accounts/{account_id}/intel/evaluate")
def evaluate(account_id: str, conn: sqlite3.Connection = Depends(get_conn)):
    hiring = company_intel.derive_hiring_events(conn, account_id)
    result = company_intel.refresh_account_signals(conn, account_id)
    result["hiring"] = hiring
    return result
