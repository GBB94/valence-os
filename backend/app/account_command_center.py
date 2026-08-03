"""Operate-lens orchestration over the typed account activity projection."""
from __future__ import annotations

import sqlite3
from datetime import date, datetime, timedelta, timezone

from . import account_activity, repo
from .db import now_utc


def _target(tab: str, record_type: str, record_id: str) -> dict:
    return {"tab": tab, "record_type": record_type, "record_id": record_id}


def _attention(
    conn: sqlite3.Connection, account_id: str, program_id: str | None, today: str
) -> list[dict]:
    horizon = (date.fromisoformat(today) + timedelta(days=7)).isoformat()
    rows: list[dict] = []

    commitment_sql = (
        "SELECT * FROM commitments WHERE account_id=? AND archived=0 AND status='open'"
    )
    params: list[str] = [account_id]
    if program_id:
        commitment_sql += " AND (program_id=? OR program_id IS NULL)"
        params.append(program_id)
    for row in conn.execute(commitment_sql, tuple(params)):
        if row["due_date"] <= horizon:
            overdue = row["due_date"] < today
            rows.append({
                "id": f"attention:commitment:{row['id']}", "kind": "commitment",
                "title": row["description"], "reason": "Commitment is overdue" if overdue else "Commitment is due within seven days",
                "due_date": row["due_date"], "band": "now" if overdue else "soon",
                "native_target": _target("ledger", "commitment", row["id"]),
            })

    program_where = "p.account_id=? AND p.archived=0"
    program_params: list[str] = [account_id]
    if program_id:
        program_where += " AND p.id=?"
        program_params.append(program_id)
    for table, kind, label, date_field in (
        ("tasks", "task", "description", "due_date"),
        ("milestones", "milestone", "name", "target_date"),
    ):
        terminal = "'open'" if table == "tasks" else "'upcoming'"
        for row in conn.execute(
            f"SELECT r.* FROM {table} r JOIN programs p ON p.id=r.program_id "
            f"WHERE {program_where} AND r.archived=0 AND r.status={terminal} "
            f"AND r.{date_field} IS NOT NULL AND r.{date_field}<=?",
            (*program_params, horizon),
        ):
            overdue = row[date_field] < today
            rows.append({
                "id": f"attention:{kind}:{row['id']}", "kind": kind, "title": row[label],
                "reason": f"{kind.title()} is overdue" if overdue else f"{kind.title()} is due within seven days",
                "due_date": row[date_field],
                "band": "now" if overdue or ("at_risk" in row.keys() and row["at_risk"]) else "soon",
                "native_target": _target("ledger", kind, row["id"]),
            })
    for table, kind in (("risks", "risk"), ("issues", "issue")):
        for row in conn.execute(
            f"SELECT r.* FROM {table} r JOIN programs p ON p.id=r.program_id "
            f"WHERE {program_where} AND r.archived=0 AND r.status='open' AND r.is_blocker=1",
            tuple(program_params),
        ):
            rows.append({
                "id": f"attention:{kind}:{row['id']}", "kind": kind,
                "title": row["description"], "reason": "Open blocker",
                "due_date": None, "band": "now",
                "native_target": _target("ledger", kind, row["id"]),
            })

    for dimension in ("delivery", "commercial"):
        row = conn.execute(
            "SELECT * FROM account_status_assessments WHERE account_id=? AND dimension=? "
            "AND archived=0 ORDER BY assessed_on DESC,created_at DESC LIMIT 1",
            (account_id, dimension),
        ).fetchone()
        if row and row["value"] in ("at_risk", "off_track"):
            rows.append({
                "id": f"attention:status:{row['id']}", "kind": "status",
                "title": f"{dimension.title()} is {row['value'].replace('_', ' ')}",
                "reason": row["recovery_action"] or "Recovery response needs review",
                "due_date": row["recovery_due_on"],
                "band": "now" if row["value"] == "off_track" else "soon",
                "native_target": _target("overview", "status_assessment", row["id"]),
            })

    for row in conn.execute(
        "SELECT * FROM internal_asks WHERE account_id=? AND archived=0 "
        "AND status NOT IN ('delivered','declined') AND needed_by<=?", (account_id, horizon)
    ):
        overdue = row["needed_by"] < today
        rows.append({
            "id": f"attention:internal_ask:{row['id']}", "kind": "internal ask",
            "title": row["need"], "reason": "Internal ask is overdue" if overdue else "Internal ask is needed within seven days",
            "due_date": row["needed_by"], "band": "now" if overdue else "soon",
            "native_target": _target("internal", "internal_ask", row["id"]),
        })

    if not program_id:
        for row in conn.execute(
            "SELECT * FROM account_reviews WHERE account_id=? AND archived=0 AND status='planned' "
            "AND scheduled_on IS NOT NULL AND scheduled_on<=?", (account_id, horizon)
        ):
            overdue = row["scheduled_on"] < today
            rows.append({
                "id": f"attention:account_review:{row['id']}", "kind": "review",
                "title": f"{row['review_type'].title()} account review",
                "reason": "Review is overdue" if overdue else "Review is scheduled within seven days",
                "due_date": row["scheduled_on"], "band": "now" if overdue else "soon",
                "native_target": _target("internal", "account_review", row["id"]),
            })

    rank = {"now": 0, "soon": 1, "watch": 2}
    rows.sort(key=lambda row: (rank[row["band"]], row["due_date"] or "9999-12-31", row["id"]))
    return rows


def _effective_cursor(item, account_cursor: str | None, program_cursor: str | None, program_id: str | None):
    if program_id and item.program_id == program_id:
        return max(value for value in (account_cursor, program_cursor) if value) if (account_cursor or program_cursor) else None
    return account_cursor


def build_command_center(
    conn: sqlite3.Connection,
    account_id: str,
    *,
    program_id: str | None = None,
    recorded_after: str | None = None,
) -> dict:
    account = repo.get_row(conn, "accounts", account_id)
    if program_id:
        program = repo.get_row(conn, "programs", program_id)
        if program["account_id"] != account_id:
            from fastapi import HTTPException
            raise HTTPException(422, "program does not belong to account")
    stamp = now_utc()
    projection = account_activity.project_account_activity(
        conn, account_id, program_id=program_id, as_of=stamp
    )
    account_checkpoint = account_activity.latest_change_checkpoint(conn, account_id)
    program_checkpoint = account_activity.latest_change_checkpoint(
        conn, account_id, scope_type="program", program_id=program_id
    ) if program_id else None
    account_cursor = account_checkpoint["reviewed_through"] if account_checkpoint else None
    program_cursor = program_checkpoint["reviewed_through"] if program_checkpoint else None
    initial_window = (datetime.fromisoformat(stamp) - timedelta(days=30)).isoformat()

    material = [item for item in projection.items if item.materiality == "material" and item.state != "proposed"]
    since_review = []
    for item in material:
        cursor = _effective_cursor(item, account_cursor, program_cursor, program_id)
        if item.recorded_at > (cursor or initial_window):
            since_review.append(item)
    since_visit = [item for item in material if recorded_after and item.recorded_at > recorded_after]
    upcoming = sorted(
        [item for item in projection.items if item.direction == "future" and item.state == "confirmed"],
        key=lambda item: (item.display_at, item.recorded_at, item.id),
    )[:10]

    contract = conn.execute(
        "SELECT * FROM contract_versions WHERE account_id=? AND archived=0 AND is_current=1 "
        "ORDER BY created_at DESC LIMIT 1", (account_id,)
    ).fetchone()
    if contract and contract["renewal_date"] and contract["renewal_date"] >= stamp[:10]:
        upcoming.append({
            "id": f"contract:{contract['id']}:renewal", "source_type": "contract",
            "source_id": contract["id"], "event_kind": "contract_renewal", "stream": "customer",
            "state": "confirmed", "title": "Contract renewal", "summary": None,
            "display_at": contract["renewal_date"], "recorded_at": contract["created_at"],
            "temporal_kind": "due", "temporal_precision": "date", "direction": "future",
            "materiality": "material", "status": "current", "reason": "Current contractual renewal date",
            "actor": None, "owner": None, "participants": [], "source_reference": None,
            "native_target": _target("commercial", "contract_version", contract["id"]),
            "account_id": account_id, "program_id": None,
        })
        upcoming.sort(key=lambda item: (item.display_at if hasattr(item, "display_at") else item["display_at"]))

    operator_view = conn.execute(
        "SELECT * FROM operator_views WHERE account_id=? AND archived=0 "
        "ORDER BY assessed_on DESC,created_at DESC LIMIT 1", (account_id,)
    ).fetchone()
    return {
        "stamp": projection.stamp.model_dump(),
        "account": account,
        "scope": {"program_id": program_id},
        "cursors": {
            "account": account_checkpoint,
            "program": program_checkpoint,
            "initial_window_start": initial_window if not account_checkpoint else None,
            "requested_visit_after": recorded_after,
        },
        "changes_since_review": [item.model_dump() for item in since_review[:20]],
        "changes_since_visit": [item.model_dump() for item in since_visit[:20]],
        "attention": _attention(conn, account_id, program_id, stamp[:10])[:20],
        "upcoming": [item.model_dump() if hasattr(item, "model_dump") else item for item in upcoming[:10]],
        "operator_view": dict(operator_view) if operator_view else None,
    }
