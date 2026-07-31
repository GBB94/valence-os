"""Relationship-intelligence analytics (Comprehensive Spec Stage 5).

  §3.4 champion pipeline  — stage per candidate, evidence-gated, single-thread risk.
  §3.5 influence paths    — shortest credible warm-intro paths to a target.
  §3.8 exec alignment     — Valence↔client executive pairings + exposure.
  §3.13 meeting dynamics  — observable attendance facts (present / committed / went quiet).

Everything here is a derived count or a professional observation — no sensitive personal data,
no sentiment inference, no individual product usage (trust boundaries D-76 / §2). Interpretation
is left to the operator's dated judgments; this module only counts observable facts.
"""
from __future__ import annotations

import sqlite3
from datetime import date

from . import cadence, people_core
from .db import now_utc

# --- §3.4 champion development pipeline --------------------------------------

STAGES = ["identify", "develop", "validate", "arm", "maintain"]
# Reaching these stages asserts the person actually advocates for us — so they require the same
# logged advocacy-without-us evidence that promotes a "coach" to a "champion" (§3.2).
EVIDENCE_GATED_STAGES = ("validate", "arm", "maintain")


def stage_requires_evidence(stage: str) -> bool:
    return stage in EVIDENCE_GATED_STAGES


def champion_pipeline(conn: sqlite3.Connection, account_id: str) -> dict:
    """Candidates grouped by stage, each with its advocacy-evidence count and cadence-decay state,
    plus the single-thread-risk signal (§3.4: fire a play if no validated champion beyond one)."""
    rows = [dict(r) for r in conn.execute(
        "SELECT cc.*, pe.name person_name, pe.title person_title, pr.name program_name "
        "FROM champion_candidates cc JOIN persons pe ON pe.id = cc.person_id "
        "LEFT JOIN programs pr ON pr.id = cc.program_id "
        "WHERE cc.account_id=? AND cc.archived=0 ORDER BY cc.stage", (account_id,)).fetchall()]

    by_stage = {s: [] for s in STAGES}
    validated = 0
    for r in rows:
        evidence = conn.execute(
            "SELECT COUNT(*) c FROM advocacy_events WHERE person_id=? AND archived=0 AND kind IN "
            "('advocacy_without_us','secured_meeting','defended_us','presented_internally')",
            (r["person_id"],)).fetchone()["c"]
        # cadence decay (§3.4 maintain) — reuse the person's primary role cadence state
        primary = conn.execute(
            "SELECT * FROM stakeholder_roles WHERE person_id=? AND archived=0 ORDER BY updated_at LIMIT 1",
            (r["person_id"],)).fetchone()
        decay = cadence.cadence_state(conn, dict(primary)) if primary else None
        r["evidence_count"] = evidence
        r["has_evidence"] = evidence > 0
        r["cadence"] = decay
        r["decay_alert"] = bool(decay and decay["overdue"])
        if r["stage"] in EVIDENCE_GATED_STAGES and evidence > 0:
            validated += 1
        by_stage.setdefault(r["stage"], []).append(r)

    counts = {s: len(by_stage[s]) for s in STAGES}
    return {
        "account_id": account_id,
        "candidates": rows,
        "by_stage": by_stage,
        "counts": counts,
        "validated_count": validated,
        # a single validated champion (or none) is single-thread risk — measured, not a vibe.
        "single_thread_risk": validated <= 1,
    }


# --- §3.5 influence paths ---------------------------------------------------
# Cost model: a strong relationship to the seed (the person we ask) is cheap, a weak one is dear;
# each extra hop adds one. So a two-hop path through strong relationships (0+2) ranks above a
# one-hop path through a weak one (6+1) — multithreading as route-planning.
_SEED_PENALTY = {"strong": 0, "medium": 3, "weak": 6}
_HOP_COST = 1
_STRENGTH_RANK = {"strong": 3, "medium": 2, "weak": 1}


def _our_strength(conn: sqlite3.Connection, person_id: str) -> str | None:
    """Strongest relationship WE have with this person, across their roles."""
    rows = conn.execute(
        "SELECT relationship_strength s FROM stakeholder_roles WHERE person_id=? AND archived=0 "
        "AND relationship_strength IS NOT NULL", (person_id,)).fetchall()
    best = None
    for r in rows:
        if best is None or _STRENGTH_RANK.get(r["s"], 0) > _STRENGTH_RANK.get(best, 0):
            best = r["s"]
    return best


def influence_paths(conn: sqlite3.Connection, account_id: str, target_id: str, max_paths: int = 3) -> dict:
    """Shortest credible warm-intro paths from someone we know to `target_id`."""
    people = {p["id"]: dict(p) for p in conn.execute(
        "SELECT id, name, title, is_placeholder FROM persons WHERE account_id=? AND archived=0",
        (account_id,)).fetchall()}
    if target_id not in people:
        return {"target_id": target_id, "already_known": False, "paths": [], "note": "unknown target"}

    # undirected adjacency over reporting + influence + sponsorship edges (any can carry an intro)
    adj: dict[str, set[str]] = {pid: set() for pid in people}
    for e in conn.execute(
        "SELECT from_person_id f, to_person_id t FROM relationship_edges WHERE account_id=? AND archived=0",
        (account_id,)).fetchall():
        if e["f"] in adj and e["t"] in adj:
            adj[e["f"]].add(e["t"]); adj[e["t"]].add(e["f"])

    target_strength = _our_strength(conn, target_id)
    if target_strength:
        return {"target_id": target_id, "target_name": people[target_id]["name"],
                "already_known": True, "our_strength": target_strength, "paths": []}

    # seeds = people we already have a relationship with (excluding the target)
    seeds = [(pid, s) for pid in people if pid != target_id and (s := _our_strength(conn, pid))]
    paths: list[dict] = []
    for seed_id, strength in seeds:
        route = _bfs_path(adj, seed_id, target_id)
        if not route:
            continue
        hops = len(route) - 1
        cost = _SEED_PENALTY.get(strength, 6) + hops * _HOP_COST
        next_hop = people[route[1]]["name"] if hops >= 1 else people[target_id]["name"]
        paths.append({
            "seed_id": seed_id, "seed_name": people[seed_id]["name"], "seed_strength": strength,
            "hops": hops, "cost": cost,
            "path": [{"id": pid, "name": people[pid]["name"], "title": people[pid].get("title")} for pid in route],
            "action": f"Ask {people[seed_id]['name']} to introduce you to {people[target_id]['name']}"
                      + (f" (via {next_hop})" if hops > 1 else "") + ".",
        })
    # best (lowest-cost) path per seed already; rank all, keep the cheapest, distinct routes
    paths.sort(key=lambda p: (p["cost"], p["hops"]))
    return {"target_id": target_id, "target_name": people[target_id]["name"],
            "already_known": False, "paths": paths[:max_paths]}


def _bfs_path(adj: dict[str, set[str]], src: str, dst: str) -> list[str] | None:
    """Shortest (fewest-hop) path src→dst, or None. Deterministic (sorted neighbours)."""
    if src == dst:
        return [src]
    seen = {src}
    queue = [[src]]
    while queue:
        path = queue.pop(0)
        for nxt in sorted(adj.get(path[-1], ())):
            if nxt in seen:
                continue
            if nxt == dst:
                return path + [nxt]
            seen.add(nxt)
            queue.append(path + [nxt])
    return None


# --- §3.8 executive alignment map -------------------------------------------

def _last_exec_touch(conn: sqlite3.Connection, valence_id: str, client_id: str) -> str | None:
    return conn.execute(
        "SELECT MAX(i.occurred_on) m FROM interactions i "
        "JOIN interaction_participants a ON a.interaction_id=i.id AND a.person_id=? "
        "JOIN interaction_participants b ON b.interaction_id=i.id AND b.person_id=? "
        "WHERE i.archived=0", (valence_id, client_id)).fetchone()["m"]


def exec_alignment(conn: sqlite3.Connection, account_id: str) -> dict:
    """Valence↔client exec pairings with last/next exec-to-exec touch, plus unpaired client
    executives (exposure). 'Executive' = executive-layer role or high influence."""
    people = {p["id"]: dict(p) for p in conn.execute(
        "SELECT id, name, title FROM persons WHERE account_id=? AND archived=0 AND is_placeholder=0",
        (account_id,)).fetchall()}
    pairings = []
    paired_clients = set()
    for r in conn.execute(
        "SELECT * FROM exec_pairings WHERE account_id=? AND archived=0", (account_id,)).fetchall():
        r = dict(r)
        paired_clients.add(r["client_person_id"])
        v = people.get(r["valence_person_id"]) or _person(conn, r["valence_person_id"])
        c = people.get(r["client_person_id"]) or _person(conn, r["client_person_id"])
        last = _last_exec_touch(conn, r["valence_person_id"], r["client_person_id"])
        pairings.append({
            "id": r["id"],
            "valence_person_id": r["valence_person_id"], "valence_name": v["name"] if v else None,
            "client_person_id": r["client_person_id"], "client_name": c["name"] if c else None,
            "client_title": c.get("title") if c else None,
            "last_touch": last, "next_touch_planned": r["next_touch_planned"], "notes": r["notes"],
        })

    # client executives = executive-layer role OR high influence — those unpaired are exposure.
    execs = {}
    for r in conn.execute(
        "SELECT sr.person_id, sr.role, sr.layer, sr.influence, pe.name, pe.title "
        "FROM stakeholder_roles sr JOIN programs pr ON pr.id=sr.program_id "
        "JOIN persons pe ON pe.id=sr.person_id "
        "WHERE pr.account_id=? AND sr.archived=0 AND pe.is_placeholder=0 AND pe.affiliation='client'",
        (account_id,)).fetchall():
        layer = r["layer"] or people_core.default_layer(r["role"])
        if layer == "executive" or r["influence"] == "high":
            execs[r["person_id"]] = {"person_id": r["person_id"], "name": r["name"],
                                     "title": r["title"], "layer": layer, "influence": r["influence"]}
    unpaired = [e for pid, e in execs.items() if pid not in paired_clients]
    return {"account_id": account_id, "pairings": pairings,
            "unpaired_execs": unpaired, "exposure_count": len(unpaired)}


def _person(conn, pid):
    r = conn.execute("SELECT id, name, title FROM persons WHERE id=?", (pid,)).fetchone()
    return dict(r) if r else None


# --- §3.13 meeting dynamics -------------------------------------------------

_QUIET_DAYS = 45  # attended before, but silent this long -> "went quiet" (observable, not a mood)


def meeting_dynamics(conn: sqlite3.Connection, program_id: str, today: str | None = None) -> dict:
    """Observable attendance facts per client attendee for a program's meetings: present count,
    first/last attended, commitments made, and a 'went quiet' flag. No sentiment, no inference."""
    today = today or now_utc()[:10]
    meetings = [dict(m) for m in conn.execute(
        "SELECT id, occurred_on, type, summary FROM interactions "
        "WHERE program_id=? AND archived=0 AND type IN ('meeting','call','workshop') "
        "ORDER BY occurred_on", (program_id,)).fetchall()]
    meeting_ids = {m["id"] for m in meetings}

    attendees: dict[str, dict] = {}
    for row in conn.execute(
        "SELECT ip.interaction_id, ip.person_id, pe.name, pe.affiliation, i.occurred_on "
        "FROM interaction_participants ip JOIN interactions i ON i.id=ip.interaction_id "
        "JOIN persons pe ON pe.id=ip.person_id "
        "WHERE i.program_id=? AND i.archived=0 AND i.type IN ('meeting','call','workshop') "
        "AND pe.affiliation='client'", (program_id,)).fetchall():
        a = attendees.setdefault(row["person_id"], {
            "person_id": row["person_id"], "name": row["name"], "attended": 0,
            "first_attended": None, "last_attended": None, "committed_count": 0})
        a["attended"] += 1
        d = row["occurred_on"]
        if d and (a["first_attended"] is None or d < a["first_attended"]):
            a["first_attended"] = d
        if d and (a["last_attended"] is None or d > a["last_attended"]):
            a["last_attended"] = d

    for a in attendees.values():
        a["committed_count"] = conn.execute(
            "SELECT COUNT(*) c FROM commitments WHERE archived=0 AND responsible_party_id=? "
            "AND program_id=?", (a["person_id"], program_id)).fetchone()["c"]
        gap = _days(a["last_attended"], today)
        # went quiet = showed up more than once historically, but silent for a while and absent
        # from the most recent meeting.
        a["went_quiet"] = bool(
            a["attended"] >= 2 and gap is not None and gap > _QUIET_DAYS and meetings
            and a["last_attended"] < meetings[-1]["occurred_on"])

    return {"program_id": program_id, "meeting_count": len(meeting_ids),
            "attendees": sorted(attendees.values(), key=lambda x: (-x["attended"], x["name"]))}


def person_attendance(conn: sqlite3.Connection, person_id: str, today: str | None = None) -> dict:
    """Attendance strip for one person across all their meetings (person-card §3.13)."""
    today = today or now_utc()[:10]
    rows = conn.execute(
        "SELECT COUNT(*) attended, MAX(i.occurred_on) last, MIN(i.occurred_on) first "
        "FROM interaction_participants ip JOIN interactions i ON i.id=ip.interaction_id "
        "WHERE ip.person_id=? AND i.archived=0 AND i.type IN ('meeting','call','workshop')",
        (person_id,)).fetchone()
    committed = conn.execute(
        "SELECT COUNT(*) c FROM commitments WHERE archived=0 AND responsible_party_id=?",
        (person_id,)).fetchone()["c"]
    gap = _days(rows["last"], today)
    return {"attended": rows["attended"] or 0, "first_attended": rows["first"],
            "last_attended": rows["last"], "committed_count": committed,
            "went_quiet": bool((rows["attended"] or 0) >= 2 and gap is not None and gap > _QUIET_DAYS)}


def _days(iso: str | None, today: str) -> int | None:
    if not iso:
        return None
    try:
        return (date.fromisoformat(today) - date.fromisoformat(iso[:10])).days
    except ValueError:
        return None
