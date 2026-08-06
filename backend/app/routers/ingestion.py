"""Ingestion API (Comprehensive Spec Part 4) — email sync, recording ingest, comms + corrections.
The heavy work runs as jobs; these endpoints enqueue and (when the worker is off) drain, so a
demo/test sees the result synchronously."""
import json
import sqlite3

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from .. import adapters, association, ingestion, jobs, repo
from ..db import now_utc
from ..deps import get_conn

router = APIRouter(prefix="/api", tags=["ingestion"])


def _run_now(conn, kind, payload):
    job = jobs.enqueue(conn, kind, payload)
    jobs.run_pending(conn)  # no-op if the background worker already claimed it
    done = jobs.get_job(conn, job["id"])
    result = json.loads(done["result_json"]) if done and done["result_json"] else None
    return {"job_id": job["id"], "status": done["status"] if done else "queued", "result": result}


class RecordingIngest(BaseModel):
    reference: str                       # transcript fixture name or inline transcript text
    attendees: list[str] = []
    keywords: list[str] = []


@router.get("/ingest/fixtures")
def fixtures():
    return {"transcripts": adapters.list_transcript_fixtures(), "emails": len(adapters.fetch_emails())}


@router.post("/ingest/emails/sync")
def sync_inbox(conn: sqlite3.Connection = Depends(get_conn)):
    return _run_now(conn, "sync_emails", {})


@router.post("/ingest/recording")
def ingest_recording(body: RecordingIngest, conn: sqlite3.Connection = Depends(get_conn)):
    return _run_now(conn, "ingest_recording",
                    {"reference": body.reference, "attendees": body.attendees, "keywords": body.keywords})


@router.get("/accounts/{account_id}/comms")
def account_comms(account_id: str, conn: sqlite3.Connection = Depends(get_conn)):
    return {"comms": repo.list_rows(conn, "comm_messages",
                                    where="account_id = ? ORDER BY occurred_at DESC", params=(account_id,))}


@router.get("/comms/flagged")
def flagged_comms(conn: sqlite3.Connection = Depends(get_conn)):
    return {"comms": repo.list_rows(conn, "comm_messages",
                                    where="needs_response = 1 AND responded = 0 ORDER BY occurred_at DESC")}


@router.get("/comms/unresolved")
def unresolved_comms(conn: sqlite3.Connection = Depends(get_conn)):
    """Emails the association engine couldn't place — surfaced for manual triage, never guessed."""
    return {"comms": repo.list_rows(conn, "comm_messages",
                                    where="account_id IS NULL ORDER BY occurred_at DESC")}


class CommAssociate(BaseModel):
    account_id: str | None = None
    program_id: str | None = None
    person_id: str | None = None


@router.post("/comms/{comm_id}/associate")
def correct_association(comm_id: str, body: CommAssociate, conn: sqlite3.Connection = Depends(get_conn)):
    """Manual correction — updates the record, teaches the association engine (§4.5), and releases
    the §14.8 extraction gate.

    A low-confidence email is ingested as a comm record and nothing more: it proposes nothing,
    because a proposal names an account the moment it is written and a wrongly-placed one would put
    another client's material in this account's review queue. This endpoint is the explicit review
    §14.8 requires in front of that, so the extractor runs here, on the operator's authority, and
    only for a message that had been held back.
    """
    comm = repo.get_row(conn, "comm_messages", comm_id)
    if body.program_id:
        program = repo.get_row(conn, "programs", body.program_id)
        if body.account_id and program["account_id"] != body.account_id:
            raise HTTPException(422, "that program belongs to a different account")
    updated = repo.patch(conn, "comm_messages", comm_id, {
        "account_id": body.account_id, "program_id": body.program_id, "person_id": body.person_id,
        "confidence": 1.0,   # a human confirmed it
        "association_confirmed_at": now_utc(), "association_confirmed_by": "operator",
    }, object_type="comm_message")
    if body.person_id and comm.get("from_addr"):
        association.record_correction(conn, hint_type="email_person", key=comm["from_addr"],
                                      person_id=body.person_id, account_id=body.account_id)
    elif body.account_id and comm.get("from_addr"):
        association.record_correction(conn, hint_type="email_person", key=comm["from_addr"],
                                      account_id=body.account_id)
    run_id = ingestion.extract_after_confirmation(conn, comm_id) if body.account_id else None
    if run_id:
        updated = repo.get_row(conn, "comm_messages", comm_id)
    return {**updated, "extraction_run_id": run_id}


@router.post("/comms/{comm_id}/responded")
def mark_responded(comm_id: str, conn: sqlite3.Connection = Depends(get_conn)):
    return repo.patch(conn, "comm_messages", comm_id,
                      {"responded": 1, "responded_on": now_utc()[:10]}, object_type="comm_message")
