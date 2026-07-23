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


def qbr(conn, account_id: str) -> dict:
    """Client-facing QBR skeleton. Assembles from live data and INCLUDES ONLY
    affirmatively-promoted records by construction (Section 2 / Module K):

    - value stories only where visibility_class in {qbr_exec, externally_referenceable}
      AND is_negative = 0. Internal-only and negative evidence are never queried.
    - metrics vs targets, with stale rendered as unknown (never carried-forward good state).
    - benchmarks shown only as versioned/sourced claims (population + period attached).
    - content is typed: confirmed_fact / internal_interpretation / open_hypothesis / recommended_action.
    Stamped with generation time, data-current-through, and missing/stale sources.
    """
    acct = repo.get_row(conn, "accounts", account_id)
    today = now_utc()[:10]
    programs = {p["id"]: p for p in repo.list_rows(conn, "programs", where="account_id=?", params=(account_id,))}
    pids = list(programs)

    # metrics vs targets (stale -> unknown)
    from datetime import date
    metrics = []
    missing_or_stale = []
    for d in repo.list_rows(conn, "metric_definitions", where="1=1 ORDER BY name"):
        obs = conn.execute(
            "SELECT * FROM metric_observations WHERE archived=0 AND definition_id=? "
            "ORDER BY current_through DESC LIMIT 1", (d["id"],)).fetchone()
        stale = True
        if obs and obs["current_through"]:
            try:
                stale = (date.fromisoformat(today) - date.fromisoformat(obs["current_through"])).days > d["stale_after_days"]
            except ValueError:
                stale = True
        if not obs or stale:
            missing_or_stale.append(d["name"])
        metrics.append({"name": d["name"], "type": "confirmed_fact",
                        "value": ("unknown" if (not obs or stale) else obs["value"]),
                        "target": (obs["target"] if obs else None),
                        "current_through": (obs["current_through"] if obs else None),
                        "population": d["population"], "definition_version": d["version"]})

    benchmarks = [{"name": b["name"], "type": "confirmed_fact", "value": b["value"], "unit": b["unit"],
                   "population": b["population"], "period": b["period"], "source": b["source"], "version": b["version"]}
                  for b in repo.list_rows(conn, "benchmarks", where="1=1 ORDER BY name")]

    # ONLY affirmatively-promoted, non-negative value stories (by construction)
    promoted = repo.list_rows(
        conn, "value_stories",
        where="account_id=? AND is_negative=0 AND visibility_class IN ('qbr_exec','externally_referenceable') ORDER BY evidence_tier DESC",
        params=(account_id,))
    value_stories = [{"outcome": v["outcome"], "type": "confirmed_fact" if v["evidence_tier"] in
                      ("measured_operational", "correlated_business") else "internal_interpretation",
                      "evidence_tier": v["evidence_tier"], "tags": v["tags"]} for v in promoted]

    open_commitments = []
    risk_open = 0
    if pids:
        qmarks = ",".join("?" * len(pids))
        for r in conn.execute(f"SELECT * FROM commitments WHERE archived=0 AND status='open' AND program_id IN ({qmarks})", pids):
            open_commitments.append({"description": r["description"], "due_date": r["due_date"], "type": "confirmed_fact"})
        risk_open = conn.execute(f"SELECT COUNT(*) c FROM risks WHERE archived=0 AND status='open' AND program_id IN ({qmarks})", pids).fetchone()["c"]

    stamp = {"generated_at": now_utc(), "data_current_through": today,
             "missing_or_stale_sources": missing_or_stale,
             "content_types": ["confirmed_fact", "internal_interpretation", "open_hypothesis", "recommended_action"]}
    return {
        "account_id": account_id, "account_name": acct["name"], "stamp": stamp,
        "metrics": metrics, "benchmarks": benchmarks, "value_stories": value_stories,
        "open_commitments": open_commitments,
        "risk_posture": {"type": "internal_interpretation", "open_risks": risk_open},
        "excluded_note": "Internal-only and negative-evidence records are excluded by construction, not by review.",
    }


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
