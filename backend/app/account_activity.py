"""Typed, rebuildable account-activity projection.

Canonical records and trustworthy append-only transitions remain the source of truth.  Adapters
normalize those records for command-center and chronology consumers without writing a second
event ledger.  Release 2 grows this registry source by source; uncovered sources are explicit in
the projection stamp rather than silently represented as an empty result.
"""
from __future__ import annotations

import sqlite3
from collections.abc import Callable, Iterable
from datetime import date, datetime, timedelta
from typing import Literal

from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from . import repo
from .db import now_utc


ActivityStream = Literal["customer", "internal", "external", "unknown"]
ActivityState = Literal[
    "confirmed", "proposed", "superseded", "retracted", "dismissed", "invalidated", "unknown"
]
TemporalKind = Literal["occurred", "effective", "recorded", "scheduled", "due"]
TemporalPrecision = Literal["date", "datetime"]
ActivityDirection = Literal["past", "future"]
ActivityMateriality = Literal["material", "context"]


def _validate_utc_timestamp(value: str) -> str:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("must be an ISO-8601 UTC timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() != timedelta(0):
        raise ValueError("must include a UTC offset")
    return value


class ActivityParticipant(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    name: str
    affiliation: Literal["client", "valence"]


class ActivitySourceReference(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    label: str
    url: str | None = None
    locator: str | None = None


class ActivityNativeTarget(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tab: Literal["overview", "ledger", "people", "plan", "commercial", "evidence", "outputs", "internal"]
    record_type: str
    record_id: str


class ActivityItem(BaseModel):
    """Stable cross-source shape.  It deliberately has no raw-notes field."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1)
    account_id: str
    program_id: str | None = None
    source_type: str
    source_id: str
    event_kind: str
    stream: ActivityStream
    state: ActivityState
    title: str = Field(min_length=1)
    summary: str | None = None
    display_at: str
    recorded_at: str
    temporal_kind: TemporalKind
    temporal_precision: TemporalPrecision
    direction: ActivityDirection
    materiality: ActivityMateriality
    status: str | None = None
    reason: str = Field(min_length=1)
    actor: str | None = None
    owner: str | None = None
    participants: list[ActivityParticipant] = Field(default_factory=list)
    source_reference: ActivitySourceReference | None = None
    native_target: ActivityNativeTarget

    @model_validator(mode="after")
    def validate_times(self):
        try:
            if self.temporal_precision == "date":
                if len(self.display_at) != 10:
                    raise ValueError
                date.fromisoformat(self.display_at)
            else:
                if "T" not in self.display_at:
                    raise ValueError
                datetime.fromisoformat(self.display_at.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValueError("display_at must match temporal_precision") from exc
        _validate_utc_timestamp(self.recorded_at)
        return self


class ActivityStamp(BaseModel):
    model_config = ConfigDict(extra="forbid")

    generated_at: str
    data_current_through: str
    as_of: str
    coverage: list[str]
    omitted: list[str]

    @field_validator("generated_at", "data_current_through", "as_of")
    @classmethod
    def utc_timestamps(cls, value: str) -> str:
        return _validate_utc_timestamp(value)


class ActivityProjection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    stamp: ActivityStamp
    items: list[ActivityItem]


class ActivityQuery(BaseModel):
    model_config = ConfigDict(extra="forbid")

    account_id: str
    program_id: str | None = None
    as_of: str

    @field_validator("as_of")
    @classmethod
    def utc_timestamp(cls, value: str) -> str:
        return _validate_utc_timestamp(value)


ActivityAdapter = Callable[[sqlite3.Connection, ActivityQuery], Iterable[ActivityItem]]
_ADAPTERS: dict[str, ActivityAdapter] = {}


def register_adapter(name: str):
    """Register one explicit source adapter; duplicate names are programming errors."""

    def decorate(adapter: ActivityAdapter) -> ActivityAdapter:
        if not name or name in _ADAPTERS:
            raise RuntimeError(f"duplicate or empty activity adapter: {name}")
        _ADAPTERS[name] = adapter
        return adapter

    return decorate


def adapter_names() -> tuple[str, ...]:
    return tuple(_ADAPTERS)


def _validate_scope(conn: sqlite3.Connection, account_id: str, program_id: str | None) -> None:
    repo.get_row(conn, "accounts", account_id)
    if not program_id:
        return
    program = repo.get_row(conn, "programs", program_id)
    if program["account_id"] != account_id:
        raise HTTPException(422, "program does not belong to account")


def project_account_activity(
    conn: sqlite3.Connection,
    account_id: str,
    *,
    program_id: str | None = None,
    include_adapters: Iterable[str] | None = None,
    as_of: str | None = None,
) -> ActivityProjection:
    """Project covered sources newest-first and name any adapter that could not be read."""
    _validate_scope(conn, account_id, program_id)
    stamp = as_of or now_utc()
    query = ActivityQuery(account_id=account_id, program_id=program_id, as_of=stamp)
    requested = tuple(dict.fromkeys(include_adapters)) if include_adapters is not None else adapter_names()
    unknown = [name for name in requested if name not in _ADAPTERS]
    if unknown:
        raise ValueError(f"unknown activity adapter(s): {', '.join(unknown)}")

    coverage: list[str] = []
    omitted: list[str] = []
    items: list[ActivityItem] = []
    for name in requested:
        try:
            items.extend(_ADAPTERS[name](conn, query))
            coverage.append(name)
        except sqlite3.Error:
            omitted.append(name)
    items.sort(key=lambda item: (item.display_at, item.recorded_at, item.id), reverse=True)
    return ActivityProjection(
        stamp=ActivityStamp(
            generated_at=stamp,
            data_current_through=stamp,
            as_of=stamp,
            coverage=coverage,
            omitted=omitted,
        ),
        items=items,
    )


def _source_reference(conn: sqlite3.Connection, source_id: str | None) -> ActivitySourceReference | None:
    if not source_id:
        return None
    row = conn.execute(
        "SELECT id,label,url,locator FROM source_references WHERE id=? AND archived=0", (source_id,)
    ).fetchone()
    return ActivitySourceReference(**dict(row)) if row else None


def _display_time(occurred_on: str, occurred_at_time: str | None) -> tuple[str, TemporalPrecision]:
    if not occurred_at_time:
        return occurred_on, "date"
    return f"{occurred_on}T{occurred_at_time}", "datetime"


@register_adapter("interaction")
def interaction_activity(conn: sqlite3.Connection, query: ActivityQuery) -> list[ActivityItem]:
    where = "i.account_id=? AND i.archived=0"
    params: list[str] = [query.account_id]
    if query.program_id:
        # Account-level interactions remain visible and explicitly retain program_id=None.
        where += " AND (i.program_id=? OR i.program_id IS NULL)"
        params.append(query.program_id)
    rows = conn.execute(
        f"SELECT i.* FROM interactions i WHERE {where} ORDER BY i.occurred_on DESC,i.created_at DESC",
        tuple(params),
    ).fetchall()
    out: list[ActivityItem] = []
    for raw in rows:
        row = dict(raw)
        participant_rows = conn.execute(
            "SELECT p.id,p.name,p.affiliation FROM interaction_participants ip "
            "JOIN persons p ON p.id=ip.person_id "
            "WHERE ip.interaction_id=? AND p.archived=0 ORDER BY p.name",
            (row["id"],),
        ).fetchall()
        participants = [ActivityParticipant(**dict(person)) for person in participant_rows]
        if any(person.affiliation == "client" for person in participants):
            stream: ActivityStream = "customer"
        elif participants:
            stream = "internal"
        else:
            stream = "unknown"
        display_at, precision = _display_time(row["occurred_on"], row["occurred_at_time"])
        direction: ActivityDirection = "future" if row["occurred_on"] > query.as_of[:10] else "past"
        meaningful = bool(row["meaningful_touch"])
        reason = (
            "Meaningful customer interaction recorded"
            if meaningful and stream == "customer"
            else "Meaningful internal interaction recorded"
            if meaningful and stream == "internal"
            else "Meaningful interaction recorded"
            if meaningful
            else "Interaction recorded"
        )
        out.append(ActivityItem(
            id=f"interaction:{row['id']}:recorded",
            account_id=row["account_id"],
            program_id=row["program_id"],
            source_type="interaction",
            source_id=row["id"],
            event_kind="interaction_recorded",
            stream=stream,
            state="confirmed",
            title=f"{row['type'].replace('_', ' ').title()} interaction",
            summary=row["summary"],
            display_at=display_at,
            recorded_at=row["created_at"],
            temporal_kind="occurred",
            temporal_precision=precision,
            direction=direction,
            materiality="material" if meaningful else "context",
            reason=reason,
            participants=participants,
            source_reference=_source_reference(conn, row["source_reference_id"]),
            native_target=ActivityNativeTarget(
                tab="ledger", record_type="interaction", record_id=row["id"]
            ),
        ))
    return out
