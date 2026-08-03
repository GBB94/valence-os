"""Typed, rebuildable account-activity projection.

Canonical records and trustworthy append-only transitions remain the source of truth.  Adapters
normalize those records for command-center and chronology consumers without writing a second
event ledger.  Release 2 grows this registry source by source; uncovered sources are explicit in
the projection stamp rather than silently represented as an empty result.
"""
from __future__ import annotations

import sqlite3
from collections.abc import Callable, Iterable
from datetime import date, datetime, timedelta, timezone
from typing import Literal

from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from . import audit, repo
from .db import new_id, now_utc


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
    # One representation makes lexical SQLite ordering safe and prevents semantically identical
    # values (for example Z and +00:00) from creating separate checkpoints.
    return parsed.astimezone(timezone.utc).isoformat()


def _utc_datetime(value: str) -> datetime:
    _validate_utc_timestamp(value)
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


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


class ChangeCheckpointCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scope_type: Literal["account", "program"] = "account"
    program_id: str | None = None
    reviewed_through: str
    source_type: Literal["command_center", "copilot_run"] = "command_center"
    source_id: str | None = None

    @field_validator("reviewed_through")
    @classmethod
    def utc_timestamp(cls, value: str) -> str:
        return _validate_utc_timestamp(value)

    @model_validator(mode="after")
    def valid_scope_and_source(self):
        if (self.scope_type == "program") != bool(self.program_id):
            raise ValueError("program_id is required only for program scope")
        if self.source_type == "copilot_run" and not self.source_id:
            raise ValueError("copilot checkpoints require source_id")
        return self


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


def latest_change_checkpoint(
    conn: sqlite3.Connection,
    account_id: str,
    *,
    scope_type: Literal["account", "program"] = "account",
    program_id: str | None = None,
    actor_id: str = audit.DEFAULT_ACTOR,
) -> dict | None:
    row = conn.execute(
        "SELECT * FROM account_change_checkpoints "
        "WHERE account_id=? AND scope_type=? AND program_id IS ? AND actor_id=? "
        "ORDER BY julianday(reviewed_through) DESC,created_at DESC,id DESC LIMIT 1",
        (account_id, scope_type, program_id, actor_id),
    ).fetchone()
    return dict(row) if row else None


def insert_change_checkpoint(
    conn: sqlite3.Connection,
    account_id: str,
    values: ChangeCheckpointCreate | dict,
    *,
    actor_id: str = audit.DEFAULT_ACTOR,
) -> dict:
    """Insert inside the caller's transaction; never move a scope backward or into the future."""
    body = values if isinstance(values, ChangeCheckpointCreate) else ChangeCheckpointCreate(**values)
    _validate_scope(conn, account_id, body.program_id)
    now = now_utc()
    if _utc_datetime(body.reviewed_through) > _utc_datetime(now):
        raise HTTPException(422, "reviewed_through cannot be in the future")
    latest = latest_change_checkpoint(
        conn, account_id, scope_type=body.scope_type, program_id=body.program_id, actor_id=actor_id
    )
    if latest and _utc_datetime(body.reviewed_through) < _utc_datetime(latest["reviewed_through"]):
        raise HTTPException(409, "review checkpoint cannot move backward")
    if latest and _utc_datetime(body.reviewed_through) == _utc_datetime(latest["reviewed_through"]):
        return latest
    row = {
        "id": new_id(),
        "account_id": account_id,
        "scope_type": body.scope_type,
        "program_id": body.program_id,
        "reviewed_through": body.reviewed_through,
        "actor_id": actor_id,
        "source_type": body.source_type,
        "source_id": body.source_id,
        "created_at": now,
    }
    conn.execute(
        f"INSERT INTO account_change_checkpoints ({','.join(row)}) "
        f"VALUES ({','.join('?' for _ in row)})",
        tuple(row.values()),
    )
    audit.record(
        conn,
        object_type="account_change_checkpoint",
        object_id=row["id"],
        action="create",
        after=row,
        actor_id=actor_id,
    )
    return row


def create_change_checkpoint(
    conn: sqlite3.Connection,
    account_id: str,
    values: ChangeCheckpointCreate | dict,
    *,
    actor_id: str = audit.DEFAULT_ACTOR,
) -> dict:
    with conn:
        return insert_change_checkpoint(conn, account_id, values, actor_id=actor_id)


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


def _temporal(value: str) -> tuple[str, TemporalPrecision]:
    return value, "datetime" if "T" in value else "date"


def _direction(value: str, as_of: str) -> ActivityDirection:
    return "future" if value[:10] > as_of[:10] else "past"


def _person(conn: sqlite3.Connection, person_id: str | None) -> dict | None:
    if not person_id:
        return None
    row = conn.execute(
        "SELECT id,name,affiliation FROM persons WHERE id=? AND archived=0", (person_id,)
    ).fetchone()
    return dict(row) if row else None


def _scoped_program_rows(
    conn: sqlite3.Connection, table: str, query: ActivityQuery
) -> list[dict]:
    sql = (
        f"SELECT r.*,p.account_id resolved_account_id FROM {table} r "
        "JOIN programs p ON p.id=r.program_id "
        "WHERE p.account_id=? AND r.archived=0 AND p.archived=0"
    )
    params: list[str] = [query.account_id]
    if query.program_id:
        sql += " AND r.program_id=?"
        params.append(query.program_id)
    return [dict(row) for row in conn.execute(sql, tuple(params)).fetchall()]


def _execution_created(
    *, row: dict, source_type: str, title: str, summary: str | None, stream: ActivityStream,
    materiality: ActivityMateriality, reason: str, owner: str | None = None,
    state: ActivityState = "confirmed", status: str | None = None,
) -> ActivityItem:
    return ActivityItem(
        id=f"{source_type}:{row['id']}:created",
        account_id=row.get("account_id") or row["resolved_account_id"],
        program_id=row.get("program_id"),
        source_type=source_type,
        source_id=row["id"],
        event_kind=f"{source_type}_created",
        stream=stream,
        state=state,
        title=title,
        summary=summary,
        display_at=row["created_at"],
        recorded_at=row["created_at"],
        temporal_kind="recorded",
        temporal_precision="datetime",
        direction="past",
        materiality=materiality,
        status=status,
        reason=reason,
        owner=owner,
        native_target=ActivityNativeTarget(
            tab="ledger", record_type=source_type, record_id=row["id"]
        ),
    )


def _dated_execution_item(
    *, row: dict, source_type: str, transition: str, title: str, summary: str | None,
    display_at: str, recorded_at: str, temporal_kind: TemporalKind, stream: ActivityStream,
    materiality: ActivityMateriality, reason: str, as_of: str, owner: str | None = None,
    status: str | None = None,
) -> ActivityItem:
    value, precision = _temporal(display_at)
    return ActivityItem(
        id=f"{source_type}:{row['id']}:{transition}",
        account_id=row.get("account_id") or row["resolved_account_id"],
        program_id=row.get("program_id"),
        source_type=source_type,
        source_id=row["id"],
        event_kind=f"{source_type}_{transition}",
        stream=stream,
        state="confirmed",
        title=title,
        summary=summary,
        display_at=value,
        recorded_at=recorded_at,
        temporal_kind=temporal_kind,
        temporal_precision=precision,
        direction=_direction(value, as_of),
        materiality=materiality,
        status=status,
        reason=reason,
        owner=owner,
        native_target=ActivityNativeTarget(
            tab="ledger", record_type=source_type, record_id=row["id"]
        ),
    )


@register_adapter("execution")
def execution_activity(conn: sqlite3.Connection, query: ActivityQuery) -> list[ActivityItem]:
    out: list[ActivityItem] = []

    commitment_sql = "SELECT * FROM commitments WHERE account_id=? AND archived=0"
    commitment_params: list[str] = [query.account_id]
    if query.program_id:
        commitment_sql += " AND (program_id=? OR program_id IS NULL)"
        commitment_params.append(query.program_id)
    for row in [dict(r) for r in conn.execute(commitment_sql, tuple(commitment_params))]:
        stream: ActivityStream = "customer" if row["commitment_class"] == "client" else "internal"
        owner = _person(conn, row.get("internal_owner_id"))
        owner_name = owner["name"] if owner else None
        out.append(_execution_created(
            row=row, source_type="commitment", title="Commitment recorded",
            summary=row["description"], stream=stream, materiality="material",
            reason="A two-party commitment was recorded", owner=owner_name, status=row["status"],
        ))
        if row["status"] == "open":
            due_material = row["due_date"] <= (date.fromisoformat(query.as_of[:10]) + timedelta(days=7)).isoformat()
            out.append(_dated_execution_item(
                row=row, source_type="commitment", transition="due", title="Commitment due",
                summary=row["description"], display_at=row["due_date"], recorded_at=row["created_at"],
                temporal_kind="due", stream=stream,
                materiality="material" if due_material else "context",
                reason="Open commitment has a required due date", owner=owner_name, status=row["status"],
                as_of=query.as_of,
            ))
        elif row.get("closed_on"):
            out.append(_dated_execution_item(
                row=row, source_type="commitment", transition="closed", title="Commitment closed",
                summary=row["description"], display_at=row["closed_on"], recorded_at=row["updated_at"],
                temporal_kind="occurred", stream=stream, materiality="material",
                reason="Commitment closure was recorded", owner=owner_name, status=row["status"],
                as_of=query.as_of,
            ))

    decision_sql = "SELECT * FROM decisions WHERE account_id=? AND archived=0"
    decision_params: list[str] = [query.account_id]
    if query.program_id:
        decision_sql += " AND (program_id=? OR program_id IS NULL)"
        decision_params.append(query.program_id)
    for row in [dict(r) for r in conn.execute(decision_sql, tuple(decision_params))]:
        decider = _person(conn, row.get("decided_by_id"))
        stream = "customer" if decider and decider["affiliation"] == "client" else "internal" if decider else "unknown"
        value, precision = _temporal(row.get("decided_on") or row["created_at"])
        out.append(ActivityItem(
            id=f"decision:{row['id']}:recorded", account_id=row["account_id"],
            program_id=row.get("program_id"), source_type="decision", source_id=row["id"],
            event_kind="decision_recorded", stream=stream,
            state="superseded" if row["status"] == "superseded" else "confirmed",
            title="Decision recorded", summary=row["description"], display_at=value,
            recorded_at=row["created_at"], temporal_kind="occurred" if row.get("decided_on") else "recorded",
            temporal_precision=precision, direction=_direction(value, query.as_of), materiality="material",
            status=row["status"], reason="A governed decision was recorded",
            actor=decider["name"] if decider else None,
            source_reference=_source_reference(conn, row.get("source_reference_id")),
            native_target=ActivityNativeTarget(tab="ledger", record_type="decision", record_id=row["id"]),
        ))

    specs = {
        "task": ("tasks", "description"),
        "risk": ("risks", "description"),
        "issue": ("issues", "description"),
        "milestone": ("milestones", "name"),
    }
    for source_type, (table, label_field) in specs.items():
        for row in _scoped_program_rows(conn, table, query):
            owner = _person(conn, row.get("internal_owner_id"))
            owner_name = owner["name"] if owner else None
            created_material = (
                (source_type == "risk" and (row.get("is_blocker") or row.get("severity") == "high"))
                or (source_type == "issue" and row.get("is_blocker"))
                or (source_type == "milestone" and row.get("at_risk"))
            )
            out.append(_execution_created(
                row=row, source_type=source_type,
                title=f"{source_type.title()} recorded", summary=row[label_field], stream="internal",
                materiality="material" if created_material else "context",
                reason=("Open blocker recorded" if row.get("is_blocker") else f"{source_type.title()} recorded"),
                owner=owner_name, status=row.get("status"),
            ))
            due_date = row.get("due_date") if source_type == "task" else row.get("target_date") if source_type == "milestone" else None
            is_open = row.get("status") in ("open", "upcoming")
            if due_date and is_open:
                due_material = due_date <= (date.fromisoformat(query.as_of[:10]) + timedelta(days=7)).isoformat()
                out.append(_dated_execution_item(
                    row=row, source_type=source_type, transition="due",
                    title=f"{source_type.title()} due", summary=row[label_field], display_at=due_date,
                    recorded_at=row["created_at"], temporal_kind="due", stream="internal",
                    materiality="material" if due_material or row.get("at_risk") else "context",
                    reason=f"Open {source_type} has a target date", owner=owner_name,
                    status=row.get("status"), as_of=query.as_of,
                ))
            terminal_date = row.get("closed_on") or row.get("resolved_on") or row.get("completed_on")
            if terminal_date:
                transition = "resolved" if source_type == "issue" else "completed" if source_type in ("task", "milestone") else "closed"
                out.append(_dated_execution_item(
                    row=row, source_type=source_type, transition=transition,
                    title=f"{source_type.title()} {transition}", summary=row[label_field],
                    display_at=terminal_date, recorded_at=row["updated_at"], temporal_kind="occurred",
                    stream="internal", materiality="material", reason=f"{source_type.title()} {transition} was recorded",
                    owner=owner_name, status=row.get("status"), as_of=query.as_of,
                ))
    return out


@register_adapter("status_assessment")
def status_activity(conn: sqlite3.Connection, query: ActivityQuery) -> list[ActivityItem]:
    rows = [dict(row) for row in conn.execute(
        "SELECT * FROM account_status_assessments WHERE account_id=? AND archived=0 "
        "ORDER BY dimension,assessed_on,created_at", (query.account_id,)
    )]
    previous: dict[str, str] = {}
    out: list[ActivityItem] = []
    for row in rows:
        prior = previous.get(row["dimension"])
        changed = prior is not None and prior != row["value"]
        owner = _person(conn, row.get("recovery_owner_person_id"))
        out.append(ActivityItem(
            id=f"status_assessment:{row['id']}:recorded", account_id=query.account_id,
            source_type="status_assessment", source_id=row["id"], event_kind="status_assessed",
            stream="internal", state="confirmed",
            title=f"{row['dimension'].title()} status assessed {row['value'].replace('_', ' ')}",
            summary=row.get("rationale"), display_at=row["assessed_on"], recorded_at=row["created_at"],
            temporal_kind="effective", temporal_precision="date", direction=_direction(row["assessed_on"], query.as_of),
            materiality="material" if changed or row["value"] in ("at_risk", "off_track") else "context",
            status=row["value"], reason="Status changed" if changed else "Governed status assessment recorded",
            actor=row["author"], owner=owner["name"] if owner else None,
            native_target=ActivityNativeTarget(tab="internal", record_type="status_assessment", record_id=row["id"]),
        ))
        previous[row["dimension"]] = row["value"]
    return out


@register_adapter("forecast_change")
def forecast_activity(conn: sqlite3.Connection, query: ActivityQuery) -> list[ActivityItem]:
    rows = conn.execute(
        "SELECT e.*,f.account_id FROM forecast_change_events e "
        "JOIN forecast_entries f ON f.id=e.entry_id "
        "WHERE f.account_id=? AND f.archived=0 ORDER BY e.changed_at", (query.account_id,)
    ).fetchall()
    return [ActivityItem(
        id=f"forecast_change:{row['id']}:recorded", account_id=query.account_id,
        source_type="forecast_change", source_id=row["id"], event_kind="forecast_category_changed",
        stream="internal", state="confirmed",
        title=f"Forecast moved {row['category_before'].replace('_', ' ')} → {row['category_after'].replace('_', ' ')}",
        summary=row["driver"], display_at=row["changed_at"], recorded_at=row["created_at"],
        temporal_kind="occurred", temporal_precision="datetime", direction=_direction(row["changed_at"], query.as_of),
        materiality="material", status=row["category_after"], reason="Append-only forecast transition recorded",
        actor=row["actor"], source_reference=_source_reference(conn, row["source_reference_id"]),
        native_target=ActivityNativeTarget(tab="internal", record_type="forecast_change", record_id=row["id"]),
    ) for row in rows]


@register_adapter("internal_ask")
def internal_ask_activity(conn: sqlite3.Connection, query: ActivityQuery) -> list[ActivityItem]:
    rows = conn.execute(
        "SELECT e.*,a.account_id,a.need,a.current_owner_person_id,a.source_reference_id "
        "FROM internal_ask_events e JOIN internal_asks a ON a.id=e.ask_id "
        "WHERE a.account_id=? AND a.archived=0 ORDER BY e.occurred_at", (query.account_id,)
    ).fetchall()
    out: list[ActivityItem] = []
    for row in rows:
        owner = _person(conn, row["current_owner_person_id"])
        out.append(ActivityItem(
            id=f"internal_ask:{row['id']}:recorded", account_id=query.account_id,
            source_type="internal_ask", source_id=row["ask_id"],
            event_kind=f"internal_ask_{row['event_type']}", stream="internal", state="confirmed",
            title=f"Internal ask {row['event_type'].replace('_', ' ')}", summary=row["need"],
            display_at=row["occurred_at"], recorded_at=row["created_at"], temporal_kind="occurred",
            temporal_precision="datetime", direction=_direction(row["occurred_at"], query.as_of),
            materiality="material" if row["event_type"] != "note" else "context",
            status=row["status_after"], reason="Append-only internal ask transition recorded",
            actor=row["actor"], owner=owner["name"] if owner else None,
            source_reference=_source_reference(conn, row["source_reference_id"]),
            native_target=ActivityNativeTarget(tab="internal", record_type="internal_ask", record_id=row["ask_id"]),
        ))
    return out


@register_adapter("account_review")
def account_review_activity(conn: sqlite3.Connection, query: ActivityQuery) -> list[ActivityItem]:
    out: list[ActivityItem] = []
    for raw in conn.execute(
        "SELECT * FROM account_reviews WHERE account_id=? AND archived=0", (query.account_id,)
    ):
        row = dict(raw)
        value = row.get("held_on") or row.get("scheduled_on") or row["updated_at"]
        temporal_kind: TemporalKind = "occurred" if row["status"] == "held" else "scheduled" if row.get("scheduled_on") else "recorded"
        display_at, precision = _temporal(value)
        chair = _person(conn, row.get("chair_person_id"))
        out.append(ActivityItem(
            id=f"account_review:{row['id']}:{row['status']}", account_id=query.account_id,
            source_type="account_review", source_id=row["id"], event_kind=f"account_review_{row['status']}",
            stream="internal", state="confirmed", title=f"{row['review_type'].title()} account review {row['status']}",
            summary=row.get("cancellation_reason"), display_at=display_at, recorded_at=row["updated_at"],
            temporal_kind=temporal_kind, temporal_precision=precision, direction=_direction(display_at, query.as_of),
            materiality="material", status=row["status"], reason=f"Account review is {row['status']}",
            owner=chair["name"] if chair else None,
            native_target=ActivityNativeTarget(tab="internal", record_type="account_review", record_id=row["id"]),
        ))
    for raw in conn.execute(
        "SELECT * FROM operator_views WHERE account_id=? AND archived=0", (query.account_id,)
    ):
        row = dict(raw)
        out.append(ActivityItem(
            id=f"operator_view:{row['id']}:recorded", account_id=query.account_id,
            source_type="operator_view", source_id=row["id"], event_kind="operator_view_recorded",
            stream="internal", state="confirmed", title="Operator point of view recorded",
            summary=row["body"], display_at=row["assessed_on"], recorded_at=row["created_at"],
            temporal_kind="effective", temporal_precision="date", direction=_direction(row["assessed_on"], query.as_of),
            materiality="material", reason="Dated operator point of view recorded", actor=row["author"],
            native_target=ActivityNativeTarget(tab="internal", record_type="operator_view", record_id=row["id"]),
        ))
    return out


@register_adapter("calendar")
def calendar_activity(conn: sqlite3.Connection, query: ActivityQuery) -> list[ActivityItem]:
    sql = "SELECT * FROM calendar_events WHERE account_id=? AND archived=0"
    params: list[str] = [query.account_id]
    if query.program_id:
        sql += " AND (program_id=? OR program_id IS NULL)"
        params.append(query.program_id)
    out: list[ActivityItem] = []
    for raw in conn.execute(sql, tuple(params)):
        row = dict(raw)
        participant_rows = conn.execute(
            "SELECT p.id,p.name,p.affiliation FROM calendar_event_attendees a "
            "JOIN persons p ON p.id=a.person_id WHERE a.event_id=? AND p.archived=0 ORDER BY p.name",
            (row["id"],),
        ).fetchall()
        participants = [ActivityParticipant(**dict(person)) for person in participant_rows]
        stream: ActivityStream = (
            "customer" if any(p.affiliation == "client" for p in participants)
            else "internal" if participants else "unknown"
        )
        out.append(ActivityItem(
            id=f"calendar:{row['id']}:scheduled", account_id=query.account_id,
            program_id=row.get("program_id"), source_type="calendar", source_id=row["id"],
            event_kind="calendar_event_scheduled", stream=stream, state="confirmed", title=row["title"],
            summary=" · ".join(part for part in (row.get("purpose"), row.get("location")) if part),
            display_at=row["starts_at"], recorded_at=row["created_at"], temporal_kind="scheduled",
            temporal_precision="datetime", direction=_direction(row["starts_at"], query.as_of),
            materiality="material" if abs((date.fromisoformat(row["starts_at"][:10]) - date.fromisoformat(query.as_of[:10])).days) <= 14 else "context",
            status="scheduled", reason="Associated account calendar event", participants=participants,
            source_reference=_source_reference(conn, row["source_reference_id"]),
            native_target=ActivityNativeTarget(tab="plan", record_type="calendar_event", record_id=row["id"]),
        ))
    return out


@register_adapter("deployment_moment")
def deployment_activity(conn: sqlite3.Connection, query: ActivityQuery) -> list[ActivityItem]:
    out: list[ActivityItem] = []
    for row in _scoped_program_rows(conn, "deployment_moments", query):
        if not row.get("event_date"):
            continue
        out.append(ActivityItem(
            id=f"deployment_moment:{row['id']}:scheduled", account_id=query.account_id,
            program_id=row["program_id"], source_type="deployment_moment", source_id=row["id"],
            event_kind="deployment_moment_scheduled", stream="customer", state="confirmed",
            title=row["name"], summary=row.get("comms_hook"), display_at=row["event_date"],
            recorded_at=row["created_at"], temporal_kind="scheduled", temporal_precision="date",
            direction=_direction(row["event_date"], query.as_of),
            materiality="material" if abs((date.fromisoformat(row["event_date"]) - date.fromisoformat(query.as_of[:10])).days) <= 30 else "context",
            status=row["integration_status"], reason="Dated deployment moment",
            owner=(_person(conn, row.get("client_owner_person_id")) or {}).get("name"),
            native_target=ActivityNativeTarget(tab="plan", record_type="deployment_moment", record_id=row["id"]),
        ))
    return out


@register_adapter("communication")
def communication_activity(conn: sqlite3.Connection, query: ActivityQuery) -> list[ActivityItem]:
    out: list[ActivityItem] = []
    for row in _scoped_program_rows(conn, "comms_entries", query):
        value = row.get("sent_at") or row.get("send_date") or row["updated_at"]
        display_at, precision = _temporal(value)
        out.append(ActivityItem(
            id=f"communication:{row['id']}:{row['status']}", account_id=query.account_id,
            program_id=row["program_id"], source_type="communication", source_id=row["id"],
            event_kind=f"communication_{row['status']}", stream="customer", state="confirmed",
            title=f"Communication {row['status']}", summary=row.get("message"), display_at=display_at,
            recorded_at=row["updated_at"], temporal_kind="occurred" if row["status"] == "sent" else "scheduled" if row.get("send_date") else "recorded",
            temporal_precision=precision, direction=_direction(display_at, query.as_of),
            materiality="material" if row["status"] == "sent" or (row.get("send_date") and row["send_date"] <= (date.fromisoformat(query.as_of[:10]) + timedelta(days=7)).isoformat()) else "context",
            status=row["status"], reason=f"Operator-recorded communication is {row['status']}",
            actor=row.get("sender"),
            native_target=ActivityNativeTarget(tab="plan", record_type="communication", record_id=row["id"]),
        ))
    return out


def _company_source(conn: sqlite3.Connection, event_id: str) -> ActivitySourceReference | None:
    row = conn.execute(
        "SELECT sr.id,sr.label,sr.url,sr.locator FROM company_event_evidence e "
        "JOIN intel_document_spans s ON s.id=e.span_id AND s.archived=0 "
        "JOIN intel_documents d ON d.id=s.document_id AND d.archived=0 "
        "JOIN source_references sr ON sr.id=d.source_reference_id AND sr.archived=0 "
        "WHERE e.event_id=? AND e.archived=0 ORDER BY e.created_at LIMIT 1", (event_id,)
    ).fetchone()
    return ActivitySourceReference(**dict(row)) if row else None


@register_adapter("company_event")
def company_activity(conn: sqlite3.Connection, query: ActivityQuery) -> list[ActivityItem]:
    rows = conn.execute(
        "SELECT e.*,k.label kind_label FROM company_events e "
        "JOIN company_event_kinds k ON k.id=e.kind_id "
        "WHERE e.account_id=? AND e.archived=0", (query.account_id,)
    ).fetchall()
    out: list[ActivityItem] = []
    for row in rows:
        value = row["occurred_on"] or row["observed_at"]
        display_at, precision = _temporal(value)
        state: ActivityState = row["status"]
        out.append(ActivityItem(
            id=f"company_event:{row['id']}:{row['status']}", account_id=query.account_id,
            source_type="company_event", source_id=row["id"], event_kind=f"company_{row['kind_id']}",
            stream="external", state=state, title=row["kind_label"], summary=row["summary"],
            display_at=display_at, recorded_at=row["updated_at"],
            temporal_kind="occurred" if row["occurred_on"] else "recorded", temporal_precision=precision,
            direction=_direction(display_at, query.as_of),
            materiality="material" if row["status"] in ("confirmed", "retracted", "invalidated") else "context",
            status=row["status"],
            reason="Confirmed external change" if row["status"] == "confirmed" else "External change proposal awaiting review" if row["status"] == "proposed" else f"External change is {row['status']}",
            source_reference=_company_source(conn, row["id"]),
            native_target=ActivityNativeTarget(tab="commercial", record_type="company_event", record_id=row["id"]),
        ))
    return out
