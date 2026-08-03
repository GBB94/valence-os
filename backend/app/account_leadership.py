"""Leadership-lens read model over governed account and activity records."""
from __future__ import annotations

import sqlite3
from datetime import date, datetime, timedelta

from fastapi import HTTPException

from . import account_activity, internal_forecast, repo
from .db import now_utc


def _target(tab: str, record_type: str, record_id: str) -> dict:
    return {"tab": tab, "record_type": record_type, "record_id": record_id}


def _validate_scope(
    conn: sqlite3.Connection, account_id: str, program_id: str | None
) -> dict:
    account = repo.get_row(conn, "accounts", account_id)
    if not program_id:
        return account
    program = repo.get_row(conn, "programs", program_id)
    if program["account_id"] != account_id:
        raise HTTPException(422, "program does not belong to account")
    return account


def _scoped_program_ids(
    conn: sqlite3.Connection, account_id: str, program_id: str | None
) -> list[str]:
    if program_id:
        return [program_id]
    return [row["id"] for row in conn.execute(
        "SELECT id FROM programs WHERE account_id=? AND archived=0", (account_id,)
    )]


def _person_name(
    conn: sqlite3.Connection, person_id: str | None, account_id: str
) -> str | None:
    if not person_id:
        return None
    row = conn.execute(
        "SELECT name FROM persons WHERE id=? AND archived=0 "
        "AND (affiliation='valence' OR account_id=?)", (person_id, account_id)
    ).fetchone()
    return row["name"] if row else None


def _latest_statuses(conn: sqlite3.Connection, account_id: str) -> tuple[list[dict], list[dict]]:
    statuses: list[dict] = []
    gaps: list[dict] = []
    for dimension in ("delivery", "commercial"):
        raw = conn.execute(
            "SELECT * FROM account_status_assessments WHERE account_id=? AND dimension=? "
            "AND archived=0 ORDER BY assessed_on DESC,created_at DESC LIMIT 1",
            (account_id, dimension),
        ).fetchone()
        if not raw:
            statuses.append({
                "dimension": dimension, "value": "unknown", "rationale": None,
                "assessed_on": None, "recovery_owner": None, "recovery_action": None,
                "recovery_due_on": None, "leadership_response": None,
                "native_target": _target("internal", "status_assessment", ""),
            })
            gaps.append({
                "id": f"status:{dimension}:missing", "kind": "status evidence",
                "title": f"{dimension.title()} status is not assessed",
                "reason": "Leadership cannot infer an account status from other records.",
                "due_date": None, "severity": "unknown",
                "native_target": _target("internal", "status_assessment", ""),
            })
            continue
        row = dict(raw)
        leadership_response = None
        if row.get("leadership_ask_id"):
            ask = conn.execute(
                "SELECT id,need,status,needed_by FROM internal_asks "
                "WHERE id=? AND account_id=? AND archived=0",
                (row["leadership_ask_id"], account_id),
            ).fetchone()
            if ask:
                leadership_response = {
                    "kind": "ask", "id": ask["id"], "label": ask["need"],
                    "status": ask["status"], "needed_by": ask["needed_by"],
                    "native_target": _target("internal", "internal_ask", ask["id"]),
                }
        elif row.get("leadership_not_applicable_reason"):
            leadership_response = {
                "kind": "not_applicable", "label": row["leadership_not_applicable_reason"],
            }
        statuses.append({
            "id": row["id"], "dimension": dimension, "value": row["value"],
            "rationale": row.get("rationale"), "assessed_on": row["assessed_on"],
            "recovery_owner": _person_name(
                conn, row.get("recovery_owner_person_id"), account_id
            ),
            "recovery_action": row.get("recovery_action"),
            "recovery_due_on": row.get("recovery_due_on"),
            "leadership_response": leadership_response,
            "native_target": _target("internal", "status_assessment", row["id"]),
        })
        response_missing = row["value"] in ("at_risk", "off_track") and (
            row.get("legacy_response_gap")
            or not row.get("recovery_owner_person_id")
            or not row.get("recovery_action")
            or not row.get("recovery_due_on")
            or (row["value"] == "off_track" and not leadership_response)
        )
        if response_missing:
            gaps.append({
                "id": f"status:{row['id']}:response", "kind": "status evidence",
                "title": f"{dimension.title()} recovery response is incomplete",
                "reason": "The governed assessment is missing an owner, action, date, or required leadership response.",
                "due_date": row.get("recovery_due_on"), "severity": row["value"],
                "native_target": _target("internal", "status_assessment", row["id"]),
            })
    return statuses, gaps


def _active_forecast(conn: sqlite3.Connection, account_id: str) -> tuple[list[dict], list[dict]]:
    rows = conn.execute(
        "SELECT e.*,p.name period_name,p.starts_on,p.ends_on,p.status period_status," 
        "x.name opportunity_name,c.version_label contract_label "
        "FROM forecast_entries e JOIN forecast_periods p ON p.id=e.period_id "
        "LEFT JOIN expansion_opportunities x ON x.id=e.opportunity_id AND x.archived=0 "
        "LEFT JOIN contract_versions c ON c.id=e.contract_version_id AND c.archived=0 "
        "WHERE e.account_id=? AND e.archived=0 AND p.archived=0 "
        "AND p.status IN ('open','locked') ORDER BY p.ends_on,e.category,e.id",
        (account_id,),
    ).fetchall()
    entries: list[dict] = []
    gaps: list[dict] = []
    for raw in rows:
        row = dict(raw)
        evidence = internal_forecast.evidence(conn, row["id"])
        missing = [rule["explanation"] for rule in evidence["missing"]]
        label = row.get("opportunity_name") or (
            f"Renewal {row['contract_label']}" if row.get("contract_label") else "Forecast target"
        )
        entries.append({
            "id": row["id"], "target": label, "category": row["category"],
            "amount": row.get("amount"), "currency": row.get("currency"),
            "price_basis": row.get("price_basis"), "probability": row.get("probability"),
            "assessed_on": row["assessed_on"], "expected_decision_date": row.get("expected_decision_date"),
            "help_needed_note": row.get("help_needed_note"),
            "unresolved_conditions": row.get("unresolved_conditions"),
            "period": {
                "id": row["period_id"], "name": row["period_name"],
                "starts_on": row["starts_on"], "ends_on": row["ends_on"],
                "status": row["period_status"],
            },
            "evidence_supported": evidence["supported"], "missing_evidence": missing,
            "native_target": _target("internal", "forecast_entry", row["id"]),
        })
        if row["category"] in ("commit", "best_case") and not evidence["supported"]:
            gaps.append({
                "id": f"forecast:{row['id']}:evidence", "kind": "forecast evidence",
                "title": f"{label} lacks support for {row['category'].replace('_', ' ')}",
                "reason": "; ".join(missing) or "Required forecast evidence is incomplete.",
                "due_date": row.get("expected_decision_date"), "severity": "at_risk",
                "native_target": _target("internal", "forecast_entry", row["id"]),
            })
        if row.get("help_needed_note") or row.get("unresolved_conditions"):
            gaps.append({
                "id": f"forecast:{row['id']}:conditions", "kind": "forecast condition",
                "title": f"{label} has unresolved forecast conditions",
                "reason": " · ".join(value for value in (
                    row.get("help_needed_note"), row.get("unresolved_conditions")
                ) if value),
                "due_date": row.get("expected_decision_date"), "severity": "at_risk",
                "native_target": _target("internal", "forecast_entry", row["id"]),
            })
    if not entries:
        gaps.append({
            "id": "forecast:missing", "kind": "forecast evidence",
            "title": "No active forecast call is recorded",
            "reason": "Leadership has no open or locked account forecast entry to review.",
            "due_date": None, "severity": "unknown",
            "native_target": _target("internal", "forecast_entry", ""),
        })
    return entries, gaps


def _cursor_for(item, account_cursor: str | None, program_cursor: str | None, program_id: str | None):
    if program_id and item.program_id == program_id:
        values = [value for value in (account_cursor, program_cursor) if value]
        return max(values) if values else None
    return account_cursor


def _movement(
    conn: sqlite3.Connection, account_id: str, program_id: str | None, stamp: str
) -> tuple[list[dict], dict, dict]:
    projection = account_activity.project_account_activity(
        conn, account_id, program_id=program_id, as_of=stamp
    )
    account_checkpoint = account_activity.latest_change_checkpoint(conn, account_id)
    program_checkpoint = account_activity.latest_change_checkpoint(
        conn, account_id, scope_type="program", program_id=program_id
    ) if program_id else None
    account_cursor = account_checkpoint["reviewed_through"] if account_checkpoint else None
    program_cursor = program_checkpoint["reviewed_through"] if program_checkpoint else None
    fallback = (datetime.fromisoformat(stamp) - timedelta(days=30)).isoformat()
    kinds = {
        "forecast_category_changed", "decision_recorded", "interaction_recorded",
        "risk_closed", "issue_resolved", "milestone_completed",
    }
    items = []
    for item in projection.items:
        cursor = _cursor_for(item, account_cursor, program_cursor, program_id) or fallback
        included_kind = item.event_kind in kinds or (
            item.source_type == "company_event" and item.state == "confirmed"
        )
        if (
            included_kind and item.state == "confirmed" and item.direction == "past"
            and item.materiality == "material" and item.recorded_at > cursor
        ):
            items.append(item.model_dump())
    items.sort(key=lambda item: (item["display_at"], item["recorded_at"], item["id"]), reverse=True)
    return items[:20], {
        "account_reviewed_through": account_cursor,
        "program_reviewed_through": program_cursor,
        "fallback_starts_at": fallback if not account_cursor else None,
    }, projection.stamp.model_dump()


def _stuck(
    conn: sqlite3.Connection, account_id: str, program_id: str | None,
    today: str, evidence_gaps: list[dict],
) -> list[dict]:
    rows: list[dict] = list(evidence_gaps)
    program_ids = _scoped_program_ids(conn, account_id, program_id)
    placeholders = ",".join("?" for _ in program_ids) or "''"
    if program_ids:
        for table, kind in (("risks", "risk"), ("issues", "issue")):
            for raw in conn.execute(
                f"SELECT r.*,p.name program_name FROM {table} r JOIN programs p ON p.id=r.program_id "
                f"WHERE r.program_id IN ({placeholders}) AND r.archived=0 "
                f"AND r.status='open' AND r.is_blocker=1", tuple(program_ids),
            ):
                row = dict(raw)
                rows.append({
                    "id": f"{kind}:{row['id']}", "kind": kind,
                    "title": row["description"], "reason": f"Open blocker · {row['program_name']}",
                    "due_date": None, "severity": row.get("severity") or "off_track",
                    "owner": _person_name(conn, row.get("internal_owner_id"), account_id),
                    "native_target": _target("ledger", kind, row["id"]),
                })
        for raw in conn.execute(
            f"SELECT m.*,p.name program_name FROM milestones m JOIN programs p ON p.id=m.program_id "
            f"WHERE m.program_id IN ({placeholders}) AND m.archived=0 "
            f"AND m.status='upcoming' AND m.at_risk=1", tuple(program_ids),
        ):
            row = dict(raw)
            rows.append({
                "id": f"milestone:{row['id']}", "kind": "milestone",
                "title": row["name"], "reason": f"At-risk milestone · {row['program_name']}",
                "due_date": row.get("target_date"), "severity": "at_risk",
                "native_target": _target("ledger", "milestone", row["id"]),
            })
    commitment_sql = (
        "SELECT * FROM commitments WHERE account_id=? AND archived=0 "
        "AND status='open' AND due_date<?"
    )
    params: list[str] = [account_id, today]
    if program_id:
        commitment_sql += " AND (program_id=? OR program_id IS NULL)"
        params.append(program_id)
    for raw in conn.execute(commitment_sql, tuple(params)):
        row = dict(raw)
        rows.append({
            "id": f"commitment:{row['id']}", "kind": "commitment",
            "title": row["description"], "reason": "Overdue commitment",
            "due_date": row["due_date"], "severity": "off_track",
            "owner": _person_name(conn, row.get("internal_owner_id"), account_id),
            "native_target": _target("ledger", "commitment", row["id"]),
        })
    for raw in conn.execute(
        "SELECT * FROM internal_asks WHERE account_id=? AND archived=0 "
        "AND status NOT IN ('delivered','declined') AND needed_by<?", (account_id, today),
    ):
        row = dict(raw)
        rows.append({
            "id": f"internal_ask:{row['id']}", "kind": "internal ask",
            "title": row["need"], "reason": "Overdue internal ask",
            "due_date": row["needed_by"], "severity": "off_track",
            "owner": _person_name(conn, row.get("current_owner_person_id"), account_id),
            "native_target": _target("internal", "internal_ask", row["id"]),
        })
    contract = conn.execute(
        "SELECT * FROM contract_versions WHERE account_id=? AND archived=0 AND is_current=1 "
        "ORDER BY created_at DESC LIMIT 1", (account_id,),
    ).fetchone()
    if contract and contract["renewal_date"]:
        renewal = date.fromisoformat(contract["renewal_date"])
        current = date.fromisoformat(today)
        if renewal < current:
            rows.append({
                "id": f"contract:{contract['id']}:renewal-overdue", "kind": "renewal",
                "title": "Current contract renewal date has passed",
                "reason": "The canonical current contract still carries a past renewal date.",
                "due_date": contract["renewal_date"], "severity": "off_track",
                "native_target": _target("commercial", "contract_version", contract["id"]),
            })
        elif contract["notice_period_days"] is not None:
            notice = renewal - timedelta(days=contract["notice_period_days"])
            if notice < current:
                rows.append({
                    "id": f"contract:{contract['id']}:notice-overdue", "kind": "contract notice",
                    "title": "Contract notice deadline has passed",
                    "reason": f"The recorded {contract['notice_period_days']}-day notice deadline passed before renewal.",
                    "due_date": notice.isoformat(), "severity": "off_track",
                    "native_target": _target("commercial", "contract_version", contract["id"]),
                })
    severity = {"off_track": 0, "high": 0, "at_risk": 1, "medium": 1, "unknown": 2, "low": 3}
    rows.sort(key=lambda row: (
        severity.get(row.get("severity"), 2), row.get("due_date") or "9999-12-31", row["id"]
    ))
    return rows[:20]


def _asks(conn: sqlite3.Connection, account_id: str) -> list[dict]:
    rows = []
    for raw in conn.execute(
        "SELECT a.*,rb.name requested_by_name,rf.name requested_from_name," 
        "co.name current_owner_name,f.name function_name "
        "FROM internal_asks a LEFT JOIN persons rb ON rb.id=a.requested_by_person_id "
        "AND rb.archived=0 AND (rb.affiliation='valence' OR rb.account_id=a.account_id) "
        "LEFT JOIN persons rf ON rf.id=a.requested_from_person_id AND rf.archived=0 "
        "AND (rf.affiliation='valence' OR rf.account_id=a.account_id) "
        "LEFT JOIN persons co ON co.id=a.current_owner_person_id AND co.archived=0 "
        "AND (co.affiliation='valence' OR co.account_id=a.account_id) "
        "LEFT JOIN internal_functions f ON f.id=a.requested_from_function_id "
        "WHERE a.account_id=? AND a.archived=0 AND a.status NOT IN ('delivered','declined') "
        "ORDER BY a.needed_by,a.created_at", (account_id,),
    ):
        row = dict(raw)
        escalations = [dict(item) for item in conn.execute(
            "SELECT id,severity,path_type,destination_role,next_step,opened_at,status "
            "FROM escalation_instances WHERE ask_id=? AND archived=0 AND status='open' "
            "ORDER BY opened_at,id", (row["id"],),
        )]
        rows.append({
            "id": row["id"], "need": row["need"], "success_condition": row["success_condition"],
            "ask_type": row["ask_type"], "status": row["status"], "needed_by": row["needed_by"],
            "requested_by": row["requested_by_name"],
            "requested_from": row.get("requested_from_name") or row.get("function_name"),
            "current_owner": row.get("current_owner_name"),
            "next_action": escalations[-1]["next_step"] if escalations else row["success_condition"],
            "escalations": escalations,
            "native_target": _target("internal", "internal_ask", row["id"]),
        })
    return rows[:20]


def _near_term(
    conn: sqlite3.Connection, account_id: str, program_id: str | None, today: str
) -> list[dict]:
    horizon = (date.fromisoformat(today) + timedelta(days=30)).isoformat()
    rows: list[dict] = []
    review = conn.execute(
        "SELECT * FROM account_reviews WHERE account_id=? AND archived=0 AND status='planned' "
        "AND scheduled_on>=? ORDER BY scheduled_on,id LIMIT 1", (account_id, today),
    ).fetchone()
    if review:
        rows.append({
            "id": f"review:{review['id']}", "kind": "account review",
            "title": f"{review['review_type'].title()} account review",
            "due_date": review["scheduled_on"], "detail": "Next planned account review · account-wide",
            "native_target": _target("internal", "account_review", review["id"]),
        })
    contract = conn.execute(
        "SELECT * FROM contract_versions WHERE account_id=? AND archived=0 AND is_current=1 "
        "ORDER BY created_at DESC LIMIT 1", (account_id,),
    ).fetchone()
    if contract and contract["renewal_date"] and contract["renewal_date"] >= today:
        if contract["notice_period_days"] is not None:
            notice = (
                date.fromisoformat(contract["renewal_date"])
                - timedelta(days=contract["notice_period_days"])
            ).isoformat()
            if notice >= today:
                rows.append({
                    "id": f"contract:{contract['id']}:notice", "kind": "contract notice",
                    "title": "Contract notice deadline", "due_date": notice,
                    "detail": f"{contract['notice_period_days']}-day notice period · account-wide",
                    "native_target": _target("commercial", "contract_version", contract["id"]),
                })
        rows.append({
            "id": f"contract:{contract['id']}:renewal", "kind": "renewal",
            "title": "Contract renewal", "due_date": contract["renewal_date"],
            "detail": "Current contractual renewal date · account-wide",
            "native_target": _target("commercial", "contract_version", contract["id"]),
        })
    commitment_sql = (
        "SELECT * FROM commitments WHERE account_id=? AND archived=0 AND status='open' "
        "AND due_date BETWEEN ? AND ?"
    )
    params: list[str] = [account_id, today, horizon]
    if program_id:
        commitment_sql += " AND (program_id=? OR program_id IS NULL)"
        params.append(program_id)
    for raw in conn.execute(commitment_sql, tuple(params)):
        row = dict(raw)
        rows.append({
            "id": f"commitment:{row['id']}", "kind": "commitment",
            "title": row["description"], "due_date": row["due_date"],
            "detail": "Open commitment in the selected scope",
            "native_target": _target("ledger", "commitment", row["id"]),
        })
    calendar_sql = (
        "SELECT * FROM calendar_events WHERE account_id=? AND archived=0 "
        "AND substr(starts_at,1,10) BETWEEN ? AND ?"
    )
    calendar_params: list[str] = [account_id, today, horizon]
    if program_id:
        calendar_sql += " AND (program_id=? OR program_id IS NULL)"
        calendar_params.append(program_id)
    for raw in conn.execute(calendar_sql, tuple(calendar_params)):
        row = dict(raw)
        rows.append({
            "id": f"calendar:{row['id']}", "kind": "meeting", "title": row["title"],
            "due_date": row["starts_at"], "detail": row["purpose"].replace("_", " "),
            "native_target": _target("plan", "calendar_event", row["id"]),
        })
    rows.sort(key=lambda row: (row["due_date"], row["id"]))
    return rows[:20]


def _review_trail(
    conn: sqlite3.Connection, account_id: str, today: str
) -> tuple[dict | None, list[dict], list[dict]]:
    pov = conn.execute(
        "SELECT * FROM operator_views WHERE account_id=? AND archived=0 "
        "ORDER BY assessed_on DESC,created_at DESC LIMIT 1", (account_id,),
    ).fetchone()
    gaps = []
    if not pov:
        gaps.append({
            "id": "operator_view:missing", "kind": "point of view",
            "title": "No dated operator point of view is recorded",
            "reason": "Leadership cannot distinguish the operator's judgment from source facts.",
            "due_date": None, "severity": "unknown",
            "native_target": _target("internal", "operator_view", ""),
        })
    elif (date.fromisoformat(today) - date.fromisoformat(pov["assessed_on"][:10])).days > 30:
        gaps.append({
            "id": f"operator_view:{pov['id']}:stale", "kind": "point of view",
            "title": "The operator point of view is stale",
            "reason": f"Last assessed {pov['assessed_on'][:10]}; the 30-day leadership window has passed.",
            "due_date": None, "severity": "unknown",
            "native_target": _target("internal", "operator_view", pov["id"]),
        })
    views = ({
        **dict(pov), "native_target": _target("internal", "operator_view", pov["id"])
    } if pov else None)
    reviews = []
    for raw in conn.execute(
        "SELECT * FROM account_reviews WHERE account_id=? AND archived=0 "
        "ORDER BY COALESCE(held_on,scheduled_on,created_at) DESC,created_at DESC LIMIT 5",
        (account_id,),
    ):
        row = dict(raw)
        participants = [item["name"] for item in conn.execute(
            "SELECT p.name FROM account_review_participants rp JOIN persons p ON p.id=rp.person_id "
            "WHERE rp.review_id=? AND p.archived=0 ORDER BY p.name", (row["id"],),
        )]
        reviews.append({
            "id": row["id"], "review_type": row["review_type"], "status": row["status"],
            "scheduled_on": row.get("scheduled_on"), "held_on": row.get("held_on"),
            "participants": participants, "source_interaction_id": row.get("source_interaction_id"),
            "native_target": _target("internal", "account_review", row["id"]),
        })
    return views, reviews, gaps


def build_leadership_review(
    conn: sqlite3.Connection,
    account_id: str,
    *,
    program_id: str | None = None,
) -> dict:
    _validate_scope(conn, account_id, program_id)
    stamp = now_utc()
    statuses, status_gaps = _latest_statuses(conn, account_id)
    forecast, forecast_gaps = _active_forecast(conn, account_id)
    operator_view, reviews, pov_gaps = _review_trail(conn, account_id, stamp[:10])
    movement, window, activity_stamp = _movement(conn, account_id, program_id, stamp)
    evidence_gaps = [*status_gaps, *forecast_gaps, *pov_gaps]
    return {
        "stamp": activity_stamp,
        "scope": {
            "program_id": program_id,
            "governed_facts": "account-wide",
            "program_aware_sections": "movement, stuck work, meetings, milestones, and commitments",
        },
        "standing": {"statuses": statuses, "forecast": forecast},
        "movement": movement, "movement_window": window,
        "stuck": _stuck(conn, account_id, program_id, stamp[:10], evidence_gaps),
        "needs": _asks(conn, account_id),
        "near_term": _near_term(conn, account_id, program_id, stamp[:10]),
        "operator_view": operator_view, "review_trail": reviews,
        "evidence_gaps": evidence_gaps,
    }
