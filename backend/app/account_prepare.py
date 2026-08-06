"""Meeting-specific Prepare lens over canonical calendar, people, and activity records."""
from __future__ import annotations

import sqlite3
from datetime import date, datetime, timedelta, timezone

from fastapi import HTTPException

from . import account_activity, repo
from .db import now_utc


def _instant(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _target(tab: str, record_type: str, record_id: str) -> dict:
    return {"tab": tab, "record_type": record_type, "record_id": record_id}


def _meeting_rows(
    conn: sqlite3.Connection, account_id: str, program_id: str | None, stamp: str
) -> list[dict]:
    cutoff = (_instant(stamp) - timedelta(days=30)).date().isoformat()
    sql = (
        "SELECT e.*,p.name program_name,sr.label source_label,sr.url source_url "
        "FROM calendar_events e LEFT JOIN programs p ON p.id=e.program_id "
        "LEFT JOIN source_references sr ON sr.id=e.source_reference_id AND sr.archived=0 "
        "WHERE e.account_id=? AND e.archived=0 AND substr(e.starts_at,1,10)>=?"
    )
    params: list[str] = [account_id, cutoff]
    if program_id:
        sql += " AND (e.program_id=? OR e.program_id IS NULL)"
        params.append(program_id)
    rows = [dict(row) for row in conn.execute(sql, tuple(params)).fetchall()]
    rows.sort(key=lambda row: (_instant(row["starts_at"]), row["id"]))
    return rows


def _meeting_summary(row: dict, now: datetime) -> dict:
    starts = _instant(row["starts_at"])
    return {
        "id": row["id"], "title": row["title"], "starts_at": row["starts_at"],
        "ends_at": row["ends_at"], "purpose": row["purpose"],
        "program_id": row["program_id"], "program_name": row.get("program_name"),
        "location": row["location"], "organizer_email": row["organizer_email"],
        "association_confidence": row["association_confidence"],
        "timing": "upcoming" if starts >= now else "recent",
        "source_reference": ({
            "id": row["source_reference_id"], "label": row.get("source_label"),
            "url": row.get("source_url"),
        } if row["source_reference_id"] else None),
        "native_target": _target("plan", "calendar_event", row["id"]),
    }


def _role_for_person(
    conn: sqlite3.Connection, person_id: str, account_id: str, program_id: str | None
) -> dict | None:
    sql = (
        "SELECT sr.*,p.name program_name FROM stakeholder_roles sr "
        "JOIN programs p ON p.id=sr.program_id "
        "WHERE sr.person_id=? AND p.account_id=? AND sr.archived=0 AND p.archived=0"
    )
    params: list[str] = [person_id, account_id]
    if program_id:
        sql += " AND sr.program_id=?"
        params.append(program_id)
    sql += " ORDER BY sr.stance_assessed_on DESC,sr.updated_at DESC,sr.id LIMIT 1"
    row = conn.execute(sql, tuple(params)).fetchone()
    if not row:
        return None
    role = dict(row)
    from . import people_core
    effective, reason = people_core.effective_role(conn, person_id, role["role"])
    return {
        "role_id": role["id"], "role": role["role"], "effective_role": effective,
        "role_reason": reason, "layer": people_core.resolved_layer(role),
        "program_id": role["program_id"], "program_name": role["program_name"],
        # CLAUDE.md §2: a stance or influence rating always traffics with its date AND its
        # evidence note. Emitting the judgment without its basis is the failure the rule names.
        "stance": role["stance"], "stance_assessed_on": role["stance_assessed_on"],
        "stance_evidence_note": role["stance_evidence_note"],
        "cares_about": role["cares_about"], "value_for_them": role["value_for_them"],
        "influence": role["influence"], "influence_assessed_on": role["graph_assessed_on"],
        "influence_evidence_note": role["graph_evidence_note"],
    }


def _last_touch(
    conn: sqlite3.Connection, account_id: str, person_id: str, before: str
) -> dict | None:
    row = conn.execute(
        "SELECT i.id,i.occurred_on,i.type,i.summary,i.created_at FROM interactions i "
        "JOIN interaction_participants ip ON ip.interaction_id=i.id "
        "WHERE i.account_id=? AND ip.person_id=? AND i.meaningful_touch=1 AND i.archived=0 "
        "AND i.occurred_on<=? ORDER BY i.occurred_on DESC,i.created_at DESC LIMIT 1",
        (account_id, person_id, before[:10]),
    ).fetchone()
    return dict(row) if row else None


def _attendees(
    conn: sqlite3.Connection, account_id: str, meeting: dict, program_id: str | None, today: date
) -> tuple[list[dict], list[dict], set[str]]:
    rows = conn.execute(
        "SELECT a.*,p.name resolved_name,p.title,p.affiliation,p.account_id person_account_id "
        "FROM calendar_event_attendees a LEFT JOIN persons p ON p.id=a.person_id AND p.archived=0 "
        "WHERE a.event_id=? ORDER BY CASE WHEN a.person_id IS NULL THEN 1 ELSE 0 END,"
        "COALESCE(p.name,a.name,a.email)", (meeting["id"],)
    ).fetchall()
    out: list[dict] = []
    gaps: list[dict] = []
    resolved_ids: set[str] = set()
    role_scope = meeting.get("program_id") or program_id
    for raw in rows:
        row = dict(raw)
        resolved = bool(
            row.get("person_id") and row.get("resolved_name")
            and (row.get("affiliation") == "valence" or row.get("person_account_id") == account_id)
        )
        person_id = row["person_id"] if resolved else None
        role = _role_for_person(conn, person_id, account_id, role_scope) if person_id else None
        touch = _last_touch(conn, account_id, person_id, meeting["starts_at"]) if person_id else None
        item = {
            "key": row["email"] or person_id or row.get("name"),
            "person_id": person_id,
            "name": row.get("resolved_name") if resolved else row.get("name"),
            "email": row.get("email"), "affiliation": row.get("affiliation") if resolved else None,
            "association_state": "resolved" if resolved else "unknown",
            "response_status": row["response_status"],
            "attendance_status": row["attendance_status"],
            "attendance_scope": row.get("attendance_scope", "unknown"),
            "title": row.get("title") if resolved else None,
            "role": role, "last_meaningful_touch": touch,
            "native_target": _target("people", "person", person_id) if person_id else None,
        }
        out.append(item)
        label = item["name"] or item["email"] or "Unknown invitee"
        if not resolved:
            gaps.append({
                "kind": "unknown_attendee", "title": f"{label} is not resolved to a person",
                "detail": "Invitee context remains unknown; no person match was guessed.",
                "native_target": _target("people", "calendar_event", meeting["id"]),
            })
            continue
        resolved_ids.add(person_id)
        is_colleague = item.get("affiliation") == "valence"
        if not role and not is_colleague:
            gaps.append({
                "kind": "missing_role", "title": f"{label} has no stakeholder role in scope",
                "detail": "Role, layer, stance, and cares-about context are not recorded for this program.",
                "native_target": item["native_target"],
            })
        elif role:
            assessed = role.get("stance_assessed_on")
            if not role.get("stance"):
                gaps.append({
                    "kind": "missing_stance", "title": f"{label} has no stance assessment",
                    "detail": "Prepare cannot infer support or resistance from role alone.",
                    "native_target": item["native_target"],
                })
            elif not assessed or (today - date.fromisoformat(assessed)).days > 30:
                gaps.append({
                    "kind": "stale_stance", "title": f"{label}'s stance needs reassessment",
                    "detail": f"Last assessed {assessed or 'without a date'}; the 30-day freshness window has passed.",
                    "native_target": item["native_target"],
                })
        if not touch and not is_colleague:
            gaps.append({
                "kind": "missing_touch", "title": f"No meaningful touch is recorded for {label}",
                "detail": "Attendee-specific change context uses the 30-day fallback window.",
                "native_target": item["native_target"],
            })
        if row["response_status"] in ("unknown", "needs_action"):
            gaps.append({
                "kind": "response_unknown", "title": f"{label}'s response is {row['response_status'].replace('_', ' ')}",
                "detail": "Attendance is not assumed from an unresolved calendar response.",
                "native_target": _target("plan", "calendar_event", meeting["id"]),
            })
    return out, gaps, resolved_ids


def _related_source_ids(
    conn: sqlite3.Connection, account_id: str, person_ids: set[str]
) -> dict[str, set[str]]:
    if not person_ids:
        return {}
    placeholders = ",".join("?" for _ in person_ids)
    ids = tuple(person_ids)
    return {
        "commitment": {row["id"] for row in conn.execute(
            f"SELECT id FROM commitments WHERE account_id=? AND archived=0 AND "
            f"(responsible_party_id IN ({placeholders}) OR internal_owner_id IN ({placeholders}) "
            f"OR acknowledged_by_id IN ({placeholders}))",
            (account_id, *ids, *ids, *ids),
        )},
        "decision": {row["id"] for row in conn.execute(
            f"SELECT id FROM decisions WHERE account_id=? AND archived=0 "
            f"AND decided_by_id IN ({placeholders})", (account_id, *ids),
        )},
        # Scoped even though the caller intersects against an account-scoped projection: the
        # intersection must not be the only thing preventing a cross-account read.
        "calendar": {row["event_id"] for row in conn.execute(
            f"SELECT DISTINCT a.event_id FROM calendar_event_attendees a "
            f"JOIN calendar_events e ON e.id=a.event_id AND e.archived=0 "
            f"WHERE e.account_id=? AND a.person_id IN ({placeholders})", (account_id, *ids),
        )},
        "internal_ask": {row["id"] for row in conn.execute(
            f"SELECT id FROM internal_asks WHERE account_id=? AND archived=0 AND "
            f"(requested_by_person_id IN ({placeholders}) OR requested_from_person_id IN ({placeholders}) "
            f"OR current_owner_person_id IN ({placeholders}))",
            (account_id, *ids, *ids, *ids),
        )},
    }


def public_company_context(
    conn: sqlite3.Connection, account_id: str, person_ids: set[str] | None = None, *, limit: int = 5,
) -> list[dict]:
    """Return a bounded set of active public facts relevant to the account or its attendees."""
    if limit < 1:
        return []
    people = person_ids or set()
    rows = conn.execute(
        "SELECT e.id,e.summary,e.occurred_on,e.expires_on,k.key kind,k.label kind_label,k.direction "
        "FROM company_events e JOIN company_event_kinds k ON k.id=e.kind_id "
        "WHERE e.account_id=? AND e.status='confirmed' AND e.expires_on>=date('now') "
        "AND e.occurred_on<=date('now') AND e.archived=0 "
        "ORDER BY e.occurred_on DESC,e.id", (account_id,)
    ).fetchall()
    result = []
    for raw in rows:
        event = dict(raw)
        links = [dict(row) for row in conn.execute(
            "SELECT account_target_id,person_id FROM company_event_links "
            "WHERE event_id=? AND status='confirmed' AND archived=0", (event["id"],)
        ).fetchall()]
        attendee_ids = {link["person_id"] for link in links if link.get("person_id") in people}
        attendee_names = []
        if attendee_ids:
            placeholders = ",".join("?" for _ in attendee_ids)
            attendee_names = [row["name"] for row in conn.execute(
                f"SELECT name FROM persons WHERE id IN ({placeholders}) AND account_id=? "
                "AND archived=0 ORDER BY name", (*attendee_ids, account_id),
            ).fetchall()]
        account_wide = any(link.get("account_target_id") == account_id for link in links)
        if not attendee_ids and not account_wide:
            continue
        evidence = [dict(row) for row in conn.execute(
            "SELECT s.id span_id,s.locator,s.excerpt,d.id document_id,d.title,d.publisher,"
            "d.published_on,d.retrieved_at,d.url FROM company_event_evidence ee "
            "JOIN intel_document_spans s ON s.id=ee.span_id AND s.archived=0 "
            "JOIN intel_documents d ON d.id=s.document_id AND d.archived=0 "
            "AND d.correction_state='active' WHERE ee.event_id=? AND ee.archived=0 "
            "ORDER BY d.published_on DESC,d.id,s.id", (event["id"],)
        ).fetchall()]
        if not evidence:
            continue
        if attendee_names:
            relevance = f"Linked to attendee{'s' if len(attendee_names) > 1 else ''} " + ", ".join(attendee_names)
        elif attendee_ids:
            relevance = "Linked to a resolved attendee"
        else:
            relevance = "Confirmed account-wide context"
        result.append({
            **event, "title": event["kind_label"], "relevance": relevance,
            "evidence": evidence,
            "source_count": len({source["document_id"] for source in evidence}),
            "span_count": len(evidence),
            "native_target": {"tab": "commercial", "subview": "company",
                              "record_type": "company_event", "record_id": event["id"]},
        })
        if len(result) >= limit:
            break
    return result


def _recent_context(
    conn: sqlite3.Connection, account_id: str, program_id: str | None, meeting: dict,
    attendees: list[dict], person_ids: set[str], stamp: str,
) -> tuple[list[dict], dict]:
    context_person_ids = {
        item["person_id"] for item in attendees
        if item.get("person_id") and item.get("affiliation") != "valence"
    }
    touches_by_person = {
        item["person_id"]: item["last_meaningful_touch"]["occurred_on"]
        for item in attendees
        if item.get("person_id") in context_person_ids and item.get("last_meaningful_touch")
    }
    touches = list(touches_by_person.values())
    fallback = (_instant(stamp) - timedelta(days=30)).date().isoformat()
    complete_touches = bool(context_person_ids) and set(touches_by_person) == context_person_ids
    window_start = min(touches) if complete_touches else fallback
    baseline_interactions = {
        item["last_meaningful_touch"]["id"]
        for item in attendees if item.get("last_meaningful_touch")
    }
    related = _related_source_ids(conn, account_id, person_ids)
    projection = account_activity.project_account_activity(
        conn, account_id, program_id=meeting.get("program_id") or program_id, as_of=stamp
    )
    items = []
    for item in projection.items:
        if item.state != "confirmed" or item.direction != "past" or item.display_at[:10] < window_start:
            continue
        if item.source_type == "interaction" and item.source_id in baseline_interactions:
            continue
        is_related = (
            (item.source_type == "interaction" and any(p.id in person_ids for p in item.participants))
            or item.source_id in related.get(item.source_type, set())
        )
        if is_related and not (item.source_type == "calendar" and item.source_id == meeting["id"]):
            items.append(item.model_dump())
    return items[:12], {
        "starts_on": window_start,
        "basis": (
            "earliest last meaningful touch across resolved attendees"
            if complete_touches
            else "30-day fallback because at least one resolved attendee has no meaningful touch"
            if context_person_ids
            else "30-day fallback because no client attendee is resolved"
        ),
        "coverage": projection.stamp.coverage,
        "omitted": projection.stamp.omitted,
    }


def _scope_program_ids(
    conn: sqlite3.Connection, account_id: str, program_id: str | None
) -> list[str]:
    if program_id:
        return [program_id]
    return [row["id"] for row in conn.execute(
        "SELECT id FROM programs WHERE account_id=? AND archived=0", (account_id,)
    )]


def _open_threads(
    conn: sqlite3.Connection, account_id: str, program_id: str | None,
    person_ids: set[str], attendees: list[dict],
) -> list[dict]:
    program_ids = _scope_program_ids(conn, account_id, program_id)
    pq = ",".join("?" for _ in program_ids) or "''"
    rows: list[dict] = []
    commitments = conn.execute(
        f"SELECT * FROM commitments WHERE account_id=? AND archived=0 AND status='open' "
        f"AND (program_id IS NULL OR program_id IN ({pq})) ORDER BY due_date,id",
        (account_id, *program_ids),
    ).fetchall()
    for raw in commitments:
        row = dict(raw)
        related = bool(person_ids & {
            value for value in (row["responsible_party_id"], row["internal_owner_id"], row["acknowledged_by_id"])
            if value
        })
        rows.append({
            "id": f"commitment:{row['id']}", "kind": "commitment", "title": row["description"],
            "detail": "Meeting attendee is an owner" if related else "Open in the selected scope",
            "due_date": row["due_date"], "related_to_attendee": related,
            "native_target": _target("ledger", "commitment", row["id"]),
        })
    if program_ids:
        for table, kind in (("risks", "risk"), ("issues", "issue")):
            for row in conn.execute(
                f"SELECT * FROM {table} WHERE program_id IN ({pq}) AND archived=0 "
                f"AND status='open' AND is_blocker=1", tuple(program_ids),
            ):
                rows.append({
                    "id": f"{kind}:{row['id']}", "kind": kind, "title": row["description"],
                    "detail": "Open blocker in the selected scope", "due_date": None,
                    "related_to_attendee": False,
                    "native_target": _target("ledger", kind, row["id"]),
                })
    for row in conn.execute(
        "SELECT * FROM internal_asks WHERE account_id=? AND archived=0 "
        "AND status NOT IN ('delivered','declined') ORDER BY needed_by,id", (account_id,)
    ):
        related = bool(person_ids & {
            value for value in (
                row["requested_by_person_id"], row["requested_from_person_id"],
                row["current_owner_person_id"],
            ) if value
        })
        rows.append({
            "id": f"internal_ask:{row['id']}", "kind": "internal ask", "title": row["need"],
            "detail": "Meeting attendee is involved" if related else "Active account ask",
            "due_date": row["needed_by"], "related_to_attendee": related,
            "native_target": _target("internal", "internal_ask", row["id"]),
        })
    attendee_emails = {str(item.get("email") or "").lower() for item in attendees if item.get("email")}
    comm_sql = (
        "SELECT * FROM comm_messages WHERE account_id=? AND archived=0 "
        "AND needs_response=1 AND responded=0"
    )
    comm_params: list[str] = [account_id]
    if program_id:
        comm_sql += " AND (program_id=? OR program_id IS NULL)"
        comm_params.append(program_id)
    for row in conn.execute(comm_sql, tuple(comm_params)):
        message_emails = {
            value.strip().lower() for value in
            [row["from_addr"] or "", *(row["to_addrs"] or "").split(",")] if value.strip()
        }
        related = bool(
            (row["person_id"] and row["person_id"] in person_ids)
            or attendee_emails & message_emails
        )
        rows.append({
            "id": f"comm_message:{row['id']}", "kind": "customer follow-up",
            "title": row["subject"] or row["summary"] or "Unanswered customer message",
            "detail": row["flag_reason"] or "Flagged as needing a response",
            "due_date": row["occurred_on"], "related_to_attendee": related,
            "native_target": _target("ledger", "comm_message", row["id"]),
        })
    rows.sort(key=lambda row: (
        0 if row["related_to_attendee"] else 1,
        0 if row["kind"] in ("risk", "issue") else 1,
        row["due_date"] or "9999-12-31", row["id"],
    ))
    return rows[:12]


def build_meeting_prep(
    conn: sqlite3.Connection,
    account_id: str,
    *,
    program_id: str | None = None,
    meeting_id: str | None = None,
) -> dict:
    repo.get_row(conn, "accounts", account_id)
    if program_id:
        program = repo.get_row(conn, "programs", program_id)
        if program["account_id"] != account_id:
            raise HTTPException(422, "program does not belong to account")
    stamp = now_utc()
    now = _instant(stamp)
    rows = _meeting_rows(conn, account_id, program_id, stamp)
    by_id = {row["id"]: row for row in rows}
    if meeting_id and meeting_id not in by_id:
        raise HTTPException(422, "meeting is not available in this account and program scope")
    selected = by_id.get(meeting_id) if meeting_id else next(
        (row for row in rows if _instant(row["starts_at"]) >= now),
        rows[-1] if rows else None,
    )
    meetings = [_meeting_summary(row, now) for row in rows]
    if not selected:
        return {
            "stamp": {"generated_at": stamp, "data_current_through": stamp},
            "meetings": meetings, "selected_meeting": None, "attendees": [],
            "recent_context": [], "public_context": [], "context_window": None, "open_threads": [],
            "evidence_gaps": [{
                "kind": "meeting_not_recorded", "title": "No associated meeting is recorded",
                "detail": "Create or associate a calendar event before preparing attendee context.",
                "native_target": _target("plan", "calendar_event", ""),
            }],
            "brief_person_ids": [],
        }
    attendees, gaps, person_ids = _attendees(
        conn, account_id, selected, program_id, now.date()
    )
    if not attendees:
        gaps.append({
            "kind": "attendees_missing", "title": "No invitees are recorded",
            "detail": "Attendee context and attendee-specific changes cannot be assembled.",
            "native_target": _target("plan", "calendar_event", selected["id"]),
        })
    if selected.get("association_confidence") is None or selected["association_confidence"] < 1:
        gaps.append({
            "kind": "association_confidence", "title": "Calendar association is not fully confirmed",
            "detail": ("The meeting-to-account association is not recorded."
                       if selected.get("association_confidence") is None
                       else "The meeting-to-account association is recorded as not fully confirmed."),
            "native_target": _target("plan", "calendar_event", selected["id"]),
        })
    if not selected.get("source_reference_id"):
        gaps.append({
            "kind": "meeting_source_missing", "title": "Meeting has no source reference",
            "detail": "Identity is operator-recorded but not linked to an original calendar source.",
            "native_target": _target("plan", "calendar_event", selected["id"]),
        })
    missing_identity = []
    if selected.get("purpose") == "other":
        missing_identity.append("specific purpose")
    if not selected.get("location"):
        missing_identity.append("location")
    if not selected.get("organizer_email"):
        missing_identity.append("organizer")
    if missing_identity:
        gaps.append({
            "kind": "meeting_identity_missing", "title": "Meeting identity is incomplete",
            "detail": "Not recorded: " + ", ".join(missing_identity) + ".",
            "native_target": _target("plan", "calendar_event", selected["id"]),
        })
    effective_program = selected.get("program_id") or program_id
    recent, context_window = _recent_context(
        conn, account_id, effective_program, selected, attendees, person_ids, stamp
    )
    eligible = list(dict.fromkeys(
        attendee["person_id"] for attendee in attendees
        if attendee["person_id"] and attendee.get("role")
        and attendee.get("affiliation") == "client"
    ))
    return {
        "stamp": {"generated_at": stamp, "data_current_through": stamp},
        "meetings": meetings, "selected_meeting": _meeting_summary(selected, now),
        "attendees": attendees, "recent_context": recent,
        "public_context": public_company_context(conn, account_id, person_ids),
        "context_window": context_window,
        "open_threads": _open_threads(
            conn, account_id, effective_program, person_ids, attendees
        ),
        "evidence_gaps": gaps, "brief_person_ids": eligible,
    }
