"""People module core (Comprehensive Spec §§3.1-3.2, 3.10).

Layer model, the full buying-committee role taxonomy, the evidence-enforced coach-vs-champion
rule, and the person profile card that the pre-call brief assembles from. Everything here is a
professional observation or a derived count — no sensitive personal data (trust boundary D-76).
"""
from __future__ import annotations

import json
import sqlite3

from . import cadence

# §3.1 — the five horizontal bands an F100 account is managed in.
LAYERS = ["executive", "economic", "operational", "technical_gating", "user_advocate"]
LAYER_LABELS = {
    "executive": "Executive", "economic": "Economic", "operational": "Operational",
    "technical_gating": "Technical & gating", "user_advocate": "User & advocate",
}

# §3.2 — the full buying committee (original roles kept for back-compat).
ROLES = [
    "executive_sponsor", "financial_gatekeeper", "procurement", "technical_evaluator",
    "legal_compliance", "end_user_voice", "coach", "champion", "detractor",
    "budget_owner", "program_owner", "it", "legal_dpo", "works_council_contact", "other",
]

# Default layer per role — a starting point; the operator can override per role.
DEFAULT_LAYER_BY_ROLE = {
    "executive_sponsor": "executive",
    "budget_owner": "economic", "financial_gatekeeper": "economic", "procurement": "economic",
    "program_owner": "operational", "champion": "operational", "coach": "operational",
    "detractor": "operational", "other": "operational",
    "it": "technical_gating", "technical_evaluator": "technical_gating",
    "legal_dpo": "technical_gating", "legal_compliance": "technical_gating",
    "works_council_contact": "technical_gating",
    "end_user_voice": "user_advocate",
}

# Advocacy kinds that count as "advocacy without us in the room" (§3.2 champion evidence).
_CHAMPION_EVIDENCE = ("advocacy_without_us", "secured_meeting", "defended_us", "presented_internally")


def default_layer(role: str) -> str:
    return DEFAULT_LAYER_BY_ROLE.get(role, "operational")


def resolved_layer(role_row: dict) -> str:
    """The layer to display: the stored one, else the role default."""
    return role_row.get("layer") or default_layer(role_row.get("role", "other"))


def has_champion_evidence(conn: sqlite3.Connection, person_id: str) -> bool:
    n = conn.execute(
        "SELECT COUNT(*) c FROM advocacy_events WHERE person_id=? AND archived=0 "
        "AND kind IN (%s)" % ",".join("?" * len(_CHAMPION_EVIDENCE)),
        (person_id, *_CHAMPION_EVIDENCE),
    ).fetchone()["c"]
    return n > 0


def effective_role(conn: sqlite3.Connection, person_id: str, role: str) -> tuple[str, str | None]:
    """A 'champion' with no logged advocacy-without-us reads as 'coach', with a stated reason
    (§3.2). Every other role is itself."""
    if role != "champion":
        return role, None
    if has_champion_evidence(conn, person_id):
        return "champion", None
    return "coach", ("Tagged champion, but no logged advocacy without us in the room yet — "
                     "showing as coach until a validation event is recorded.")


def _stance_trajectory(conn: sqlite3.Connection, role_ids: list[str]) -> list[dict]:
    """Dated stance history reconstructed from the audit log (no separate history table)."""
    if not role_ids:
        return []
    rows = conn.execute(
        "SELECT occurred_at, before, after FROM audit_events "
        "WHERE object_type='stakeholder_role' AND action IN ('create','update') "
        "AND object_id IN (%s) ORDER BY occurred_at" % ",".join("?" * len(role_ids)),
        tuple(role_ids),
    ).fetchall()
    traj, last = [], None
    for r in rows:
        after = json.loads(r["after"]) if r["after"] else {}
        stance = after.get("stance")
        if stance and stance != last:
            traj.append({"date": after.get("stance_assessed_on") or r["occurred_at"][:10],
                         "stance": stance, "evidence": after.get("stance_evidence_note")})
            last = stance
    return traj


def person_card(conn: sqlite3.Connection, person_id: str) -> dict:
    """The §3.10 profile card: the unit the pre-call brief assembles from. Aggregation only."""
    p = conn.execute("SELECT * FROM persons WHERE id=?", (person_id,)).fetchone()
    if p is None:
        return {}
    p = dict(p)

    # roles by program (with resolved layer + evidence-checked effective role)
    role_rows = conn.execute(
        "SELECT sr.*, pr.name pname, pr.account_id FROM stakeholder_roles sr "
        "JOIN programs pr ON pr.id=sr.program_id WHERE sr.person_id=? AND sr.archived=0",
        (person_id,)).fetchall()
    roles, role_ids, raw_roles = [], [], []
    for r in role_rows:
        r = dict(r); role_ids.append(r["id"]); raw_roles.append(r)
        eff, reason = effective_role(conn, person_id, r["role"])
        roles.append({
            "role_id": r["id"],
            "role": r["role"], "effective_role": eff, "coach_reason": reason,
            "layer": resolved_layer(r), "program_id": r["program_id"], "program_name": r["pname"],
            "stance": r["stance"], "stance_assessed_on": r["stance_assessed_on"],
            "cares_about": r["cares_about"], "value_for_them": r["value_for_them"],
            "influence": r["influence"], "relationship_strength": r["relationship_strength"],
        })

    # open commitments in both directions (they owe / owed to them)
    commitments = [dict(x) for x in conn.execute(
        "SELECT c.id, c.program_id, pr.name program_name, c.description, c.due_date, c.status, "
        "CASE WHEN c.responsible_party_id=? THEN 'theirs' ELSE 'ours' END direction "
        "FROM commitments c JOIN programs pr ON pr.id=c.program_id "
        "WHERE c.archived=0 AND c.status='open' "
        "AND (c.responsible_party_id=? OR c.acknowledged_by_id=?)",
        (person_id, person_id, person_id)).fetchall()]

    # influence edges touching this person
    edges = [dict(x) for x in conn.execute(
        "SELECT id, from_person_id, to_person_id, type, note FROM relationship_edges "
        "WHERE archived=0 AND (from_person_id=? OR to_person_id=?)",
        (person_id, person_id)).fetchall()]

    # interaction history filtered to them (most recent first)
    history = [dict(x) for x in conn.execute(
        "SELECT i.id, i.occurred_on, i.type, i.summary FROM interactions i "
        "JOIN interaction_participants ip ON ip.interaction_id=i.id "
        "WHERE ip.person_id=? AND i.archived=0 ORDER BY i.occurred_on DESC LIMIT 25",
        (person_id,)).fetchall()]
    last_touch = history[0]["occurred_on"] if history else None

    advocacy = [dict(x) for x in conn.execute(
        "SELECT id, kind, occurred_on, note FROM advocacy_events "
        "WHERE person_id=? AND archived=0 ORDER BY occurred_on DESC", (person_id,)).fetchall()]

    # §3.6/§3.7 — cadence state + health panel keyed off the person's primary (first) role
    primary = raw_roles[0] if raw_roles else None
    cadence_block = cadence.cadence_state(conn, primary) if primary else None
    health = cadence.person_health(conn, person_id, primary) if not p.get("is_placeholder") else None

    # §3.13 attendance strip + §3.4 champion pipeline stage (local import: analytics -> people_core)
    from . import people_analytics
    attendance = people_analytics.person_attendance(conn, person_id) if not p.get("is_placeholder") else None
    champ = conn.execute(
        "SELECT id, stage, program_id FROM champion_candidates WHERE person_id=? AND archived=0 LIMIT 1",
        (person_id,)).fetchone()

    return {
        "id": p["id"], "name": p["name"], "title": p["title"], "email": p["email"],
        "affiliation": p["affiliation"], "account_id": p["account_id"],
        "is_placeholder": bool(p.get("is_placeholder")),
        "comms_preference": p.get("comms_preference"),
        "metric_judged_on": p.get("metric_judged_on"),
        "roles": roles,
        "layers": sorted({r["layer"] for r in roles}),
        "stance_trajectory": _stance_trajectory(conn, role_ids),
        "open_commitments": commitments,
        "influence_edges": edges,
        "interaction_history": history,
        "last_touch": last_touch,
        "advocacy": advocacy,
        "cadence": cadence_block,
        "health": health,
        "attendance": attendance,
        "champion_stage": champ["stage"] if champ else None,
    }
