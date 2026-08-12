"""HTTP boundary for Release 2 account activity and the Operate command center."""
import sqlite3
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import ValidationError

from .. import account_activity, account_command_center, account_leadership, account_prepare
from ..deps import get_conn

router = APIRouter(prefix="/api/accounts", tags=["account-command-center"])


@router.get("/{account_id}/activity")
def activity(
    account_id: str,
    program_id: str | None = None,
    stream: list[Literal["customer", "internal", "external", "unknown"]] = Query(default=[]),
    source_type: list[Literal[
        "interaction", "commitment", "decision", "task", "risk", "issue", "milestone",
        "status_assessment", "forecast_change", "internal_ask", "account_review",
        "operator_view", "calendar", "deployment_moment", "communication", "company_event",
    ]] = Query(default=[]),
    event_kind: list[str] = Query(default=[]),
    state: Literal["confirmed", "proposed", "superseded", "retracted", "dismissed", "invalidated", "unknown"] | None = None,
    direction: Literal["past", "future", "all"] = "all",
    materiality: Literal["material", "context"] | None = None,
    recorded_after: str | None = None,
    display_from: str | None = None,
    display_to: str | None = None,
    cursor: str | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    conn: sqlite3.Connection = Depends(get_conn),
):
    return account_activity.activity_page(
        conn, account_id, program_id=program_id, stream=stream, source_type=source_type,
        event_kind=event_kind, state=state, direction=direction, materiality=materiality,
        recorded_after=recorded_after, display_from=display_from, display_to=display_to,
        cursor=cursor, limit=limit,
    )


@router.get("/{account_id}/command-center")
def command_center(
    account_id: str,
    program_id: str | None = None,
    recorded_after: str | None = None,
    conn: sqlite3.Connection = Depends(get_conn),
):
    if recorded_after:
        try:
            account_activity.ActivityQuery(account_id=account_id, program_id=program_id, as_of=recorded_after)
        except ValidationError as exc:
            raise HTTPException(422, "recorded_after must be an ISO-8601 UTC timestamp") from exc
    return account_command_center.build_command_center(
        conn, account_id, program_id=program_id, recorded_after=recorded_after
    )


@router.get("/{account_id}/command-center/prepare")
def prepare(
    account_id: str,
    program_id: str | None = None,
    meeting_id: str | None = None,
    conn: sqlite3.Connection = Depends(get_conn),
):
    return account_prepare.build_meeting_prep(
        conn, account_id, program_id=program_id, meeting_id=meeting_id
    )


@router.get("/{account_id}/command-center/leadership")
def leadership(
    account_id: str,
    program_id: str | None = None,
    conn: sqlite3.Connection = Depends(get_conn),
):
    return account_leadership.build_leadership_review(
        conn, account_id, program_id=program_id
    )


@router.post("/{account_id}/change-checkpoints", status_code=201)
def checkpoint(
    account_id: str,
    body: account_activity.ChangeCheckpointCreate,
    conn: sqlite3.Connection = Depends(get_conn),
):
    return account_activity.create_change_checkpoint(conn, account_id, body)
