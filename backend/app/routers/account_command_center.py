"""HTTP boundary for Release 2 account activity and the Operate command center."""
import sqlite3
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import ValidationError

from .. import account_activity, account_command_center
from ..deps import get_conn

router = APIRouter(prefix="/api/accounts", tags=["account-command-center"])


@router.get("/{account_id}/activity")
def activity(
    account_id: str,
    program_id: str | None = None,
    stream: list[Literal["customer", "internal", "external", "unknown"]] = Query(default=[]),
    event_kind: list[str] = Query(default=[]),
    state: Literal["confirmed", "proposed", "superseded", "retracted", "dismissed", "invalidated", "unknown"] | None = None,
    direction: Literal["past", "future", "all"] = "all",
    recorded_after: str | None = None,
    display_from: str | None = None,
    display_to: str | None = None,
    cursor: str | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    conn: sqlite3.Connection = Depends(get_conn),
):
    if recorded_after:
        try:
            account_activity.ActivityQuery(account_id=account_id, program_id=program_id, as_of=recorded_after)
        except ValidationError as exc:
            raise HTTPException(422, "recorded_after must be an ISO-8601 UTC timestamp") from exc
    projection = account_activity.project_account_activity(conn, account_id, program_id=program_id)
    items = projection.items
    if stream:
        items = [item for item in items if item.stream in stream]
    if event_kind:
        items = [item for item in items if item.event_kind in event_kind]
    if state:
        items = [item for item in items if item.state == state]
    if direction != "all":
        items = [item for item in items if item.direction == direction]
    if recorded_after:
        items = [item for item in items if item.recorded_at > recorded_after]
    if display_from:
        items = [item for item in items if item.display_at >= display_from]
    if display_to:
        items = [item for item in items if item.display_at <= display_to]
    items.sort(
        key=lambda item: (item.display_at, item.recorded_at, item.id),
        reverse=direction != "future",
    )
    if cursor:
        positions = [index for index, item in enumerate(items) if item.id == cursor]
        if not positions:
            raise HTTPException(422, "activity cursor is not valid for these filters")
        items = items[positions[0] + 1:]
    page = items[:limit]
    return {
        "stamp": projection.stamp.model_dump(),
        "items": [item.model_dump() for item in page],
        "next_cursor": page[-1].id if len(items) > limit else None,
    }


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


@router.post("/{account_id}/change-checkpoints", status_code=201)
def checkpoint(
    account_id: str,
    body: account_activity.ChangeCheckpointCreate,
    conn: sqlite3.Connection = Depends(get_conn),
):
    return account_activity.create_change_checkpoint(conn, account_id, body)
