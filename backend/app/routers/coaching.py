"""Private Call Coach API. No route here resolves account proposals or writes readiness."""
from __future__ import annotations

import sqlite3
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field

from .. import coaching
from ..deps import get_conn

router = APIRouter(prefix="/api/coaching", tags=["coaching"])


class SessionCreate(BaseModel):
    mode: Literal["review", "rehearsal"] = "review"
    parent_session_id: str | None = None
    origin_observation_id: str | None = None
    account_id: str | None = None
    program_id: str | None = None
    interaction_id: str | None = None
    title: str = Field(default="Call review", min_length=1, max_length=240)
    call_type: str = "other"
    call_date: str | None = None
    intended_outcome: str = Field(min_length=1, max_length=2000)
    coaching_focus: str | None = None
    coached_speaker_key: str | None = None
    speaker_status: Literal["confirmed_by_operator", "unknown", "not_applicable"] = "unknown"
    reflection_worked: str | None = None
    reflection_difficult: str | None = None
    reflection_outcome: str | None = None
    reflection_change: str | None = None
    source_kind: str = "paste"
    filename: str | None = None
    text: str | None = None
    content_b64: str | None = None


class ObservationResponse(BaseModel):
    response: Literal["useful", "inaccurate", "dismissed"]
    note: str | None = Field(default=None, max_length=2000)


class GoalCreate(BaseModel):
    observation_id: str
    revisit_after: str | None = None


class RehearsalCreate(BaseModel):
    origin_observation_id: str
    attempt_text: str = Field(min_length=1, max_length=20_000)
    objective: str | None = None


class LinkBody(BaseModel):
    account_id: str
    program_id: str | None = None


class DraftUpdatesBody(BaseModel):
    run_id: str | None = None


@router.get("/config")
def get_config():
    return coaching.config()


@router.get("/sessions")
def sessions(account_id: str | None = None, mode: str | None = None, limit: int = 50,
             conn: sqlite3.Connection = Depends(get_conn)):
    if mode and mode not in {"review", "rehearsal"}:
        raise HTTPException(422, "mode must be review or rehearsal")
    return coaching.list_sessions(conn, account_id=account_id, mode=mode, limit=limit)


@router.post("/sessions", status_code=201)
def create_session(body: SessionCreate, conn: sqlite3.Connection = Depends(get_conn)):
    return coaching.create_session(conn, body.model_dump())


@router.get("/sessions/{session_id}")
def session(session_id: str, conn: sqlite3.Connection = Depends(get_conn)):
    return coaching.get_session(conn, session_id)


@router.post("/sessions/{session_id}/runs", status_code=201)
def create_run(session_id: str, conn: sqlite3.Connection = Depends(get_conn)):
    return coaching.enqueue_run(conn, session_id)


@router.post("/sessions/{session_id}/retry", status_code=201)
def retry(session_id: str, conn: sqlite3.Connection = Depends(get_conn)):
    return coaching.retry_run(conn, session_id)


@router.patch("/observations/{observation_id}/response")
def observation_response(observation_id: str, body: ObservationResponse,
                         conn: sqlite3.Connection = Depends(get_conn)):
    return coaching.respond_to_observation(conn, observation_id, body.response, body.note)


@router.post("/goals", status_code=201)
def create_goal(body: GoalCreate, conn: sqlite3.Connection = Depends(get_conn)):
    return coaching.create_goal(conn, body.observation_id, body.revisit_after)


@router.post("/goals/{goal_id}/complete")
def complete_goal(goal_id: str, conn: sqlite3.Connection = Depends(get_conn)):
    return coaching.complete_goal(conn, goal_id)


@router.post("/sessions/{session_id}/rehearsals", status_code=201)
def create_rehearsal(session_id: str, body: RehearsalCreate,
                     conn: sqlite3.Connection = Depends(get_conn)):
    return coaching.create_rehearsal(conn, session_id, body.model_dump())


@router.post("/sessions/{session_id}/link-preview")
def link_preview(session_id: str, body: LinkBody,
                 conn: sqlite3.Connection = Depends(get_conn)):
    return coaching.link_preview(conn, session_id, body.account_id, body.program_id)


@router.post("/sessions/{session_id}/link")
def link(session_id: str, body: LinkBody, conn: sqlite3.Connection = Depends(get_conn)):
    return coaching.link_session(conn, session_id, body.account_id, body.program_id)


@router.post("/sessions/{session_id}/unlink-preview")
def unlink_preview(session_id: str, conn: sqlite3.Connection = Depends(get_conn)):
    return coaching.unlink_preview(conn, session_id)


@router.post("/sessions/{session_id}/unlink")
def unlink(session_id: str, conn: sqlite3.Connection = Depends(get_conn)):
    return coaching.unlink_session(conn, session_id)


@router.post("/sessions/{session_id}/log-interaction", status_code=201)
def log_interaction(session_id: str, conn: sqlite3.Connection = Depends(get_conn)):
    return coaching.log_interaction(conn, session_id)


@router.post("/sessions/{session_id}/draft-account-updates", status_code=201)
def draft_account_updates(session_id: str, body: DraftUpdatesBody,
                          conn: sqlite3.Connection = Depends(get_conn)):
    return coaching.draft_account_updates(conn, session_id, body.run_id)


@router.delete("/sources/{source_id}/snapshot")
def delete_source(source_id: str, conn: sqlite3.Connection = Depends(get_conn)):
    return coaching.delete_source_snapshot(conn, source_id)


@router.delete("/sessions/{session_id}", status_code=204)
def archive_session(session_id: str, conn: sqlite3.Connection = Depends(get_conn)):
    coaching.archive_session(conn, session_id)
    return Response(status_code=204)
