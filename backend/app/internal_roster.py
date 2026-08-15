"""Internal roster and deterministic coverage briefing."""
from __future__ import annotations

import sqlite3
from datetime import date, timedelta

from fastapi import HTTPException

from . import repo
from .db import new_id, now_utc


def add(conn: sqlite3.Connection, account_id: str, values: dict) -> dict:
    repo.get_row(conn, "accounts", account_id)
    try:
        return repo.insert(conn, "account_internal_roster", {"account_id": account_id, **values}, object_type="internal_roster")
    except sqlite3.IntegrityError as exc:
        raise HTTPException(422, str(exc)) from exc


def list_roster(conn: sqlite3.Connection, account_id: str) -> list[dict]:
    repo.get_row(conn, "accounts", account_id)
    rows = conn.execute("SELECT r.*,p.name person_name FROM account_internal_roster r JOIN persons p ON p.id=r.person_id WHERE r.account_id=? AND r.archived=0 ORDER BY r.role,r.coverage_type,p.name", (account_id,)).fetchall()
    return [repo.row_to_dict(r) for r in rows]


def contribution(conn: sqlite3.Connection, account_id: str) -> dict:
    roster = list_roster(conn, account_id); today = date.fromisoformat(now_utc()[:10])
    rows = []
    for member in roster:
        touch = conn.execute("SELECT i.id,i.occurred_on FROM interactions i JOIN interaction_participants ip ON ip.interaction_id=i.id WHERE i.account_id=? AND ip.person_id=? AND i.meaningful_touch=1 AND i.archived=0 ORDER BY i.occurred_on DESC LIMIT 1", (account_id, member["person_id"])).fetchone()
        days = (today - date.fromisoformat(touch["occurred_on"][:10])).days if touch else None
        rows.append({**member, "last_touch_interaction_id": touch["id"] if touch else None,
                     "last_touch_on": touch["occurred_on"] if touch else None, "days_since_touch": days,
                     "cadence_overdue": bool(member.get("expected_touch_cadence_days") and (days is None or days > member["expected_touch_cadence_days"]))})
    distinct = {r["person_id"] for r in rows if r["last_touch_on"] and r["last_touch_on"] >= (today - timedelta(days=90)).isoformat()}
    return {"members": rows, "recent_internal_participant_count": len(distinct),
            "single_thread_exposed": len(distinct) <= 1,
            "basis": "Derived from meaningful interaction participation in the prior 90 days; not an activity score."}


def coverage_data(conn: sqlite3.Connection, account_id: str, days: int = 14) -> dict:
    if days < 1 or days > 60:
        raise HTTPException(422, "coverage window must be 1 to 60 days")
    account = repo.get_row(conn, "accounts", account_id); start = date.fromisoformat(now_utc()[:10]); end = start + timedelta(days=days)
    commitments = [repo.row_to_dict(r) for r in conn.execute("SELECT * FROM commitments WHERE account_id=? AND archived=0 AND status='open' ORDER BY due_date", (account_id,))]
    asks = [repo.row_to_dict(r) for r in conn.execute("SELECT * FROM internal_asks WHERE account_id=? AND archived=0 AND status NOT IN ('delivered','declined') ORDER BY needed_by", (account_id,))]
    risks = [repo.row_to_dict(r) for r in conn.execute("SELECT r.* FROM risks r JOIN programs p ON p.id=r.program_id WHERE p.account_id=? AND r.archived=0 AND r.status='open' ORDER BY CASE r.severity WHEN 'high' THEN 0 WHEN 'medium' THEN 1 ELSE 2 END,r.created_at", (account_id,))]
    forecast = [repo.row_to_dict(r) for r in conn.execute("SELECT e.* FROM forecast_entries e JOIN forecast_periods p ON p.id=e.period_id WHERE e.account_id=? AND e.archived=0 AND p.status IN ('open','locked') ORDER BY CASE e.category WHEN 'commit' THEN 0 WHEN 'best_case' THEN 1 ELSE 2 END,e.amount DESC", (account_id,))]
    calendar = [repo.row_to_dict(r) for r in conn.execute("SELECT * FROM calendar_events WHERE account_id=? AND archived=0 AND substr(starts_at,1,10) BETWEEN ? AND ? ORDER BY starts_at", (account_id, start.isoformat(), end.isoformat()))]
    contract = repo.row_to_dict(conn.execute("SELECT * FROM contract_versions WHERE account_id=? AND is_current=1 AND archived=0 ORDER BY created_at DESC LIMIT 1", (account_id,)).fetchone())
    break_items = []
    if risks: break_items.append({"kind": "risk", "id": risks[0]["id"], "text": risks[0]["description"], "basis": "highest-severity unresolved risk"})
    dated = ([{"kind": "commitment", "id": r["id"], "text": r["description"], "on": r["due_date"]} for r in commitments] +
             [{"kind": "ask", "id": r["id"], "text": r["need"], "on": r["needed_by"]} for r in asks] +
             [{"kind": "calendar_event", "id": r["id"], "text": r["title"], "on": r["starts_at"][:10]} for r in calendar])
    if dated:
        nearest = sorted(dated, key=lambda x: x["on"])[0]; break_items.append({**nearest, "basis": "nearest material date"})
    blocked = [e for e in forecast if e["category"] in ("commit", "best_case") and e.get("help_needed_note")]
    if blocked:
        largest = sorted(blocked, key=lambda x: x.get("amount") or -1, reverse=True)[0]
        break_items.append({"kind": "forecast_entry", "id": largest["id"], "text": largest["help_needed_note"], "basis": "highest-value blocked forecast call"})
    return {"account": account, "window": {"starts_on": start.isoformat(), "ends_on": end.isoformat(), "days": days},
            "roster": list_roster(conn, account_id), "contribution": contribution(conn, account_id),
            "commitments": commitments, "asks": asks, "risks": risks, "forecast": forecast,
            "calendar": calendar, "contract": contract, "things_that_break": break_items[:3]}


def generate_coverage_brief(conn: sqlite3.Connection, account_id: str, days: int = 14) -> dict:
    data = coverage_data(conn, account_id, days); a = data["account"]
    lines = [f"# {a['name']} — {days}-day coverage brief", "", f"Coverage window: {data['window']['starts_on']} to {data['window']['ends_on']}", "", "## Three things that break if ignored"]
    lines += [f"- {x['text']} ({x['basis']}; {x['kind']} {x['id']})" for x in data["things_that_break"]] or ["- No qualifying exposure found"]
    lines += ["", "## Live commitments", *([f"- {r['description']} — {r['due_date']} ({r['commitment_class']})" for r in data["commitments"]] or ["- None"]),
              "", "## Open asks", *([f"- {r['need']} — needed {r['needed_by']}" for r in data["asks"]] or ["- None"]),
              "", "## Next 14 days", *([f"- {r['starts_at']}: {r['title']}" for r in data["calendar"]] or ["- No calendar events"]),
              "", "## Forecast calls", *([f"- {r['category']}: {r.get('amount')} {r.get('currency') or ''} {r.get('price_basis') or ''}" for r in data["forecast"]] or ["- None"])]
    doc = repo.insert(conn, "generated_documents", {"account_id": account_id, "kind": "coverage_brief",
        "title": f"{a['name']} — coverage brief", "body_markdown": "\n".join(lines), "status": "draft",
        "generated_at": now_utc(), "data_current_through": now_utc()[:10], "audience": "internal",
        "audience_profile": "working"}, object_type="generated_document")
    with conn:
        for collection, typ in (("commitments", "commitment"), ("asks", "internal_ask"), ("risks", "risk"), ("forecast", "forecast_entry"), ("calendar", "calendar_event"), ("roster", "internal_roster")):
            for row in data[collection]:
                conn.execute("INSERT INTO generated_document_sources(id,document_id,record_type,record_id,record_version,inclusion_reason,visibility_class,created_at) VALUES (?,?,?,?,?,?,?,?)",
                             (new_id(), doc["id"], typ, row["id"], row.get("updated_at"), collection, "internal", now_utc()))
    return {"document": doc, "data": data}


def _save_brief(conn: sqlite3.Connection, account_id: str, kind: str, title: str,
                lines: list[str], sources: list[tuple[str, dict, str]]) -> dict:
    doc = repo.insert(conn, "generated_documents", {"account_id": account_id, "kind": kind,
        "title": title, "body_markdown": "\n".join(lines), "status": "draft",
        "generated_at": now_utc(), "data_current_through": now_utc()[:10], "audience": "internal",
        "audience_profile": "working"}, object_type="generated_document")
    with conn:
        for record_type, row, reason in sources:
            conn.execute(
                "INSERT INTO generated_document_sources(id,document_id,record_type,record_id,record_version,inclusion_reason,visibility_class,created_at) VALUES (?,?,?,?,?,?,?,?)",
                (new_id(), doc["id"], record_type, row["id"], row.get("updated_at") or row.get("occurred_at"),
                 reason, "internal", now_utc()),
            )
    return doc


def generate_role_brief(conn: sqlite3.Connection, account_id: str, roster_id: str,
                        days: int = 14) -> dict:
    """Generate a call/joiner brief constrained by the colleague's recorded role."""
    data = coverage_data(conn, account_id, days)
    member = repo.get_row(conn, "account_internal_roster", roster_id)
    if member["account_id"] != account_id or member["archived"]:
        raise HTTPException(422, "roster member does not actively cover this account")
    person = repo.get_row(conn, "persons", member["person_id"])
    if person["affiliation"] != "valence":
        raise HTTPException(422, "call briefs are for Valence colleagues only")
    lines = [f"# {data['account']['name']} — role-scoped call brief", "",
             f"For: {person['name']} · {member['role'].replace('_', ' ')}", "",
             "## Your remit", member["standing_responsibilities"],
             f"Briefing scope: {member.get('briefing_scope') or 'Use the responsibilities above; do not assume account ownership.'}",
             "", "## What needs attention"]
    lines += [f"- {x['text']} ({x['basis']})" for x in data["things_that_break"]] or ["- No qualifying exposure found"]
    lines += ["", f"## Dates in the next {days} days",
              *([f"- {r['starts_at']}: {r['title']}" for r in data["calendar"]] or ["- None recorded"]),
              "", "## Open internal dependencies",
              *([f"- {r['need']} — needed {r['needed_by']} ({r['status']})" for r in data["asks"]] or ["- None"])]
    sources = [("internal_roster", member, "recipient role and remit")]
    for key, typ in (("commitments", "commitment"), ("asks", "internal_ask"),
                     ("risks", "risk"), ("forecast", "forecast_entry"),
                     ("calendar", "calendar_event")):
        sources.extend((typ, row, key) for row in data[key])
    doc = _save_brief(conn, account_id, "colleague_call_brief",
                      f"{data['account']['name']} — call brief for {person['name']}", lines, sources)
    return {"document": doc, "data": {**data, "recipient": {**member, "person_name": person["name"]}}}


def generate_return_brief(conn: sqlite3.Connection, account_id: str, starts_on: str,
                          ends_on: str) -> dict:
    """Summarize sourced movement during a temporary handoff window."""
    account = repo.get_row(conn, "accounts", account_id)
    try:
        start, end = date.fromisoformat(starts_on), date.fromisoformat(ends_on)
    except ValueError as exc:
        raise HTTPException(422, "return brief dates must be ISO dates") from exc
    if end < start or (end - start).days > 90:
        raise HTTPException(422, "return brief window must be ordered and no longer than 90 days")
    interactions = [repo.row_to_dict(r) for r in conn.execute(
        "SELECT * FROM interactions WHERE account_id=? AND archived=0 AND substr(occurred_on,1,10) BETWEEN ? AND ? ORDER BY occurred_on",
        (account_id, starts_on, ends_on))]
    ask_events = [repo.row_to_dict(r) for r in conn.execute(
        "SELECT e.* FROM internal_ask_events e JOIN internal_asks a ON a.id=e.ask_id WHERE a.account_id=? AND substr(e.occurred_at,1,10) BETWEEN ? AND ? ORDER BY e.occurred_at",
        (account_id, starts_on, ends_on))]
    forecast_changes = [repo.row_to_dict(r) for r in conn.execute(
        "SELECT e.* FROM forecast_change_events e JOIN forecast_entries f ON f.id=e.entry_id WHERE f.account_id=? AND substr(e.changed_at,1,10) BETWEEN ? AND ? ORDER BY e.changed_at",
        (account_id, starts_on, ends_on))]
    live = coverage_data(conn, account_id, 14)
    lines = [f"# {account['name']} — return brief", "", f"Change window: {starts_on} to {ends_on}", "",
             "## Interactions while away",
             *([f"- {r['occurred_on']}: {r['summary'] or r['type']}" for r in interactions] or ["- None recorded"]),
             "", "## Internal ask movement",
             *([f"- {r['occurred_at'][:10]}: {r['event_type']} ({r['ask_id']})" for r in ask_events] or ["- None"]),
             "", "## Forecast movement",
             *([f"- {r['category_before']} → {r['category_after']}: {r['driver']}" for r in forecast_changes] or ["- None"]),
             "", "## Resume here",
             *([f"- {x['text']} ({x['basis']})" for x in live["things_that_break"]] or ["- No qualifying exposure found"])]
    sources = [("interaction", r, "interaction while away") for r in interactions]
    sources += [("internal_ask_event", r, "ask movement while away") for r in ask_events]
    sources += [("forecast_change_event", r, "forecast movement while away") for r in forecast_changes]
    doc = _save_brief(conn, account_id, "coverage_return_brief",
                      f"{account['name']} — return brief", lines, sources)
    return {"document": doc, "data": {"account": account, "window": {"starts_on": starts_on, "ends_on": ends_on},
            "interactions": interactions, "ask_events": ask_events, "forecast_changes": forecast_changes,
            "resume_here": live["things_that_break"]}}
