"""v0.4 output generators — account history and the weekly team update.

Both are DERIVED reads (no new tables). The team update is INTERNAL, but it is
built by *construction*: the generator only ever selects promotable, summary-level
fields. It never queries raw_notes or stakeholder stance/evidence, so internal-only
capture material cannot leak into the output regardless of operator behavior — the
same construction the v2 client-facing QBR generator will rely on. There is no
column anywhere for a named individual's product usage, so none can appear.
"""
from __future__ import annotations

import sqlite3
from datetime import date, timedelta

from . import repo
from .db import now_utc

# Records that can be created from an interaction (for history back-references).
DERIVED_TABLES = {
    "commitment": "commitments",
    "risk": "risks",
    "issue": "issues",
    "decision": "decisions",
    "task": "tasks",
    "milestone": "milestones",
}


def _label(table: str, row: dict) -> str:
    return row.get("name") if table == "milestones" else row.get("description")


def account_history(conn, account_id, *, person_id=None, program_id=None) -> dict:
    """Chronological interaction ledger for an account, newest first, with the
    records created from each interaction. Filterable by person or program."""
    acct = repo.get_row(conn, "accounts", account_id)
    where = "archived=0 AND account_id=?"
    params: list = [account_id]
    if program_id:
        where += " AND program_id=?"
        params.append(program_id)
    interactions = repo.list_rows(
        conn, "interactions", where=where + " ORDER BY occurred_on DESC, created_at DESC", params=tuple(params)
    )

    prog_names = {p["id"]: p["name"] for p in repo.list_rows(conn, "programs", where="account_id=?", params=(account_id,))}
    person_names = {p["id"]: p["name"] for p in repo.list_rows(conn, "persons", where="1=1")}

    out = []
    for it in interactions:
        parts = conn.execute(
            "SELECT person_id FROM interaction_participants WHERE interaction_id=?", (it["id"],)
        ).fetchall()
        participant_ids = [r["person_id"] for r in parts]
        if person_id and person_id not in participant_ids:
            continue
        derived = []
        for kind, table in DERIVED_TABLES.items():
            for r in repo.list_rows(conn, table, where="source_interaction_id=?", params=(it["id"],)):
                derived.append({"type": kind, "id": r["id"], "label": _label(table, r), "status": r.get("status")})
        out.append({
            "id": it["id"],
            "occurred_on": it["occurred_on"],
            "type": it["type"],
            "summary": it["summary"],
            "program_id": it["program_id"],
            "program_name": prog_names.get(it["program_id"]),
            "meaningful_touch": it["meaningful_touch"],
            "participants": [{"id": pid, "name": person_names.get(pid)} for pid in participant_ids],
            "created_records": derived,
        })
    return {"account_id": account_id, "account_name": acct["name"], "interactions": out}


def _in_window(iso_ts: str | None, since: str) -> bool:
    return bool(iso_ts) and iso_ts[:10] >= since


def team_update(conn, *, since: str | None = None) -> dict:
    """One-click weekly internal team update across the portfolio. Stamped with
    generation time, data-current-through, and the window. Summary-level only."""
    today = now_utc()[:10]
    if not since:
        since = (date.fromisoformat(today) - timedelta(days=7)).isoformat()

    accounts = repo.list_rows(conn, "accounts", where="1=1 ORDER BY name")
    programs = {p["id"]: p for p in repo.list_rows(conn, "programs", where="1=1")}

    def prog(pid):
        return programs.get(pid, {}).get("name") if pid else None

    sections = []
    for a in accounts:
        pids = [pid for pid, p in programs.items() if p["account_id"] == a["id"]]
        if not pids:
            continue
        qmarks = ",".join("?" * len(pids))

        def rows(table, extra=""):
            return [dict(r) for r in conn.execute(
                f"SELECT * FROM {table} WHERE archived=0 AND program_id IN ({qmarks}) {extra}", pids
            )]

        # NOTE: interaction SELECT deliberately takes summary only — never raw_notes.
        new_interactions = [
            {"occurred_on": r["occurred_on"], "type": r["type"], "summary": r["summary"], "program": prog(r["program_id"])}
            for r in rows("interactions", "ORDER BY occurred_on DESC")
            if _in_window(r["occurred_on"], since)
        ]
        new_commitments = [
            {"description": r["description"], "due_date": r["due_date"], "program": prog(r["program_id"]),
             "responsible": r["responsible_party_id"], "owner": r["internal_owner_id"]}
            for r in rows("commitments") if _in_window(r["created_at"], since)
        ]
        open_blockers = (
            [{"kind": "risk", "description": r["description"], "program": prog(r["program_id"])}
             for r in rows("risks", "AND status='open' AND is_blocker=1")]
            + [{"kind": "issue", "description": r["description"], "program": prog(r["program_id"])}
               for r in rows("issues", "AND status='open' AND is_blocker=1")]
        )
        overdue = [
            {"description": r["description"], "due_date": r["due_date"], "program": prog(r["program_id"])}
            for r in rows("commitments", "AND status='open'") if r["due_date"] and r["due_date"] < today
        ]
        at_risk_ms = [
            {"name": r["name"], "target_date": r["target_date"], "program": prog(r["program_id"])}
            for r in rows("milestones", "AND status='upcoming'")
            if r["at_risk"] or (r["target_date"] and r["target_date"] < today)
        ]
        decisions = [
            {"description": r["description"], "program": prog(r["program_id"])}
            for r in rows("decisions") if _in_window(r["created_at"], since)
        ]
        # person names for commitment owners
        names = {p["id"]: p["name"] for p in repo.list_rows(conn, "persons", where="1=1")}
        for c in new_commitments:
            c["responsible"] = names.get(c["responsible"], c["responsible"])
            c["owner"] = names.get(c["owner"], c["owner"])

        if any([new_interactions, new_commitments, open_blockers, overdue, at_risk_ms, decisions]):
            sections.append({
                "account_id": a["id"], "account_name": a["name"],
                "delivery_status": a["delivery_status"], "commercial_status": a["commercial_status"],
                "new_interactions": new_interactions, "new_commitments": new_commitments,
                "open_blockers": open_blockers, "overdue_commitments": overdue,
                "at_risk_milestones": at_risk_ms, "decisions": decisions,
            })

    stamp = {"generated_at": now_utc(), "data_current_through": today, "window_since": since, "window_until": today}
    return {"stamp": stamp, "sections": sections, "markdown": _render_markdown(stamp, sections)}


def _render_markdown(stamp, sections) -> str:
    L = [f"# Weekly team update", "",
         f"_Generated {stamp['generated_at']} · data current through {stamp['data_current_through']} · "
         f"covering {stamp['window_since']} → {stamp['window_until']}_", ""]
    if not sections:
        L.append("_Nothing to report this week._")
        return "\n".join(L)
    for s in sections:
        L.append(f"## {s['account_name']}  —  delivery: {s['delivery_status']} · commercial: {s['commercial_status']}")
        def block(title, items, fmt):
            if items:
                L.append(f"**{title}**")
                for it in items:
                    L.append(f"- {fmt(it)}")
                L.append("")
        block("New interactions", s["new_interactions"], lambda i: f"{i['occurred_on']} · {i['type']} · {i['program'] or 'account-level'} — {i['summary'] or '(no summary)'}")
        block("New commitments", s["new_commitments"], lambda c: f"{c['description']} — {c['responsible']} → {c['owner']}, due {c['due_date']} ({c['program']})")
        block("Open blockers", s["open_blockers"], lambda b: f"[{b['kind']}] {b['description']} ({b['program']})")
        block("Overdue commitments", s["overdue_commitments"], lambda o: f"{o['description']} — was due {o['due_date']} ({o['program']})")
        block("At-risk milestones", s["at_risk_milestones"], lambda m: f"{m['name']} — target {m['target_date'] or 'unset'} ({m['program']})")
        block("Decisions", s["decisions"], lambda d: f"{d['description']} ({d['program']})")
    return "\n".join(L)
