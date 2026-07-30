import sqlite3

from fastapi import APIRouter, Depends, HTTPException

from .. import repo
from ..deps import get_conn
from ..schemas import EdgeCreate, GraphAssessment, RecoveredSpendCreate

router = APIRouter(prefix="/api", tags=["viz"])

_INFLUENCE_SIZE = {"low": 20, "medium": 34, "high": 50}
_STRENGTH_WIDTH = {"weak": 1, "medium": 2.5, "strong": 4.5}


@router.patch("/stakeholder-roles/{role_id}/graph")
def set_graph_assessment(role_id: str, b: GraphAssessment, conn: sqlite3.Connection = Depends(get_conn)):
    if (b.influence or b.relationship_strength) and not (b.graph_assessed_on and b.graph_evidence_note):
        raise HTTPException(422, "Influence/relationship strength require a date and an evidence note (Section 2).")
    return repo.patch(conn, "stakeholder_roles", role_id, b.model_dump(), object_type="stakeholder_role")


@router.post("/relationship-edges", status_code=201)
def create_edge(b: EdgeCreate, conn: sqlite3.Connection = Depends(get_conn)):
    return repo.insert(conn, "relationship_edges", b.model_dump(), object_type="relationship_edge")


@router.post("/recovered-spend", status_code=201)
def create_recovered(b: RecoveredSpendCreate, conn: sqlite3.Connection = Depends(get_conn)):
    return repo.insert(conn, "recovered_spend", b.model_dump(), object_type="recovered_spend")


@router.get("/accounts/{account_id}/stakeholder-graph")
def stakeholder_graph(account_id: str, program_id: str | None = None, conn: sqlite3.Connection = Depends(get_conn)):
    """Nodes = people with their strongest role/stance/influence; edges = relationships.
    Encodings (Section 6b): node size = influence, color = stance, edge width = strength,
    arrowheads = direction. Also returns power-interest coordinates."""
    repo.get_row(conn, "accounts", account_id)
    where = "program_id IN (SELECT id FROM programs WHERE account_id=?)"
    params = [account_id]
    if program_id:
        where = "program_id = ?"
        params = [program_id]
    roles = repo.list_rows(conn, "stakeholder_roles", where=where, params=tuple(params))
    people = {p["id"]: p for p in repo.list_rows(conn, "persons", where="account_id=?", params=(account_id,))}

    # aggregate per person (strongest influence, most recent stance)
    nodes = {}
    for r in roles:
        pid = r["person_id"]
        person = people.get(pid)
        if not person:
            continue
        n = nodes.setdefault(pid, {"id": pid, "name": person["name"], "title": person["title"],
                                   "role": r["role"], "stance": r["stance"], "influence": r["influence"],
                                   "relationship_strength": r["relationship_strength"],
                                   # §3 placeholder: a position known to exist but not yet identified
                                   "is_placeholder": bool(person.get("is_placeholder")),
                                   "expected_influence": person.get("expected_influence"),
                                   "find_by_date": person.get("find_by_date")})
        # prefer a set influence/stance over null
        if r["influence"] and not n["influence"]:
            n["influence"] = r["influence"]
        if r["stance"] and not n["stance"]:
            n["stance"] = r["stance"]
    # decorate for rendering + power-interest grid (power=influence, interest~stance)
    interest = {"supporter": 3, "unconverted": 2, "skeptic": 1, None: 2}
    power = {"high": 3, "medium": 2, "low": 1, None: 1}
    for n in nodes.values():
        # placeholders size by EXPECTED influence and render in the unknown treatment (frontend)
        infl = n["expected_influence"] if n["is_placeholder"] else n["influence"]
        n["size"] = _INFLUENCE_SIZE.get(infl, 22)
        n["power"] = power.get(infl, 1)
        n["interest"] = interest.get(n["stance"], 2)

    edges = []
    for e in repo.list_rows(conn, "relationship_edges", where="account_id=?", params=(account_id,)):
        if e["from_person_id"] in nodes and e["to_person_id"] in nodes:
            edges.append({"id": e["id"], "source": e["from_person_id"], "target": e["to_person_id"],
                          "type": e["type"], "note": e["note"]})
    return {"nodes": list(nodes.values()), "edges": edges}


@router.get("/accounts/{account_id}/stakeholder-coverage")
def stakeholder_coverage(account_id: str, conn: sqlite3.Connection = Depends(get_conn)):
    """Coverage measure (Section 5C/6b): active senior relationships, days since last
    meaningful touch, and whether the business case is multithreaded (2nd internal owner)."""
    from datetime import date
    from ..db import now_utc
    repo.get_row(conn, "accounts", account_id)
    today = now_utc()[:10]
    senior = ("champion", "budget_owner", "program_owner")
    # real senior relationships only — placeholders are counted separately as exposure (§3)
    rows = conn.execute(
        "SELECT DISTINCT sr.person_id, sr.role FROM stakeholder_roles sr "
        "JOIN programs pr ON pr.id=sr.program_id "
        "JOIN persons pe ON pe.id=sr.person_id "
        "WHERE pr.account_id=? AND sr.archived=0 AND pe.is_placeholder=0 AND sr.role IN (?,?,?)",
        (account_id, *senior)).fetchall()
    names = {p["id"]: p["name"] for p in repo.list_rows(conn, "persons", where="1=1")}
    people = []
    for r in rows:
        last = conn.execute(
            "SELECT MAX(i.occurred_on) m FROM interaction_participants ip JOIN interactions i ON i.id=ip.interaction_id "
            "WHERE ip.person_id=? AND i.meaningful_touch=1 AND i.archived=0", (r["person_id"],)).fetchone()["m"]
        days = None
        if last:
            try: days = (date.fromisoformat(today) - date.fromisoformat(last)).days
            except ValueError: days = None
        people.append({"name": names.get(r["person_id"]), "role": r["role"],
                       "last_touch": last, "days_since_touch": days,
                       "stale": days is None or days > 21})

    # business-case owners = distinct internal owners driving expansion/commercial work
    owners = set()
    for x in repo.list_rows(conn, "expansion_opportunities", where="account_id=?", params=(account_id,)):
        for c in ("sponsor_person_id", "budget_owner_person_id"):
            if x.get(c): owners.add(x[c])
    for c in conn.execute(
        "SELECT DISTINCT internal_owner_id FROM commitments cm JOIN programs p ON p.id=cm.program_id "
        "WHERE p.account_id=? AND cm.internal_owner_id IS NOT NULL", (account_id,)):
        owners.add(c["internal_owner_id"])

    # §3 — unidentified critical positions count as exposure, not as active relationships.
    placeholders = conn.execute(
        "SELECT id, title, expected_role, expected_influence, find_by_date FROM persons "
        "WHERE account_id=? AND is_placeholder=1 AND archived=0", (account_id,)).fetchall()

    return {
        "senior_stakeholders": sorted(people, key=lambda x: (x["days_since_touch"] is None, -(x["days_since_touch"] or 0))),
        "vp_plus_total": len(people),
        "vp_plus_active": sum(1 for p in people if not p["stale"]),
        "business_case_owner_count": len(owners),
        "multithreaded": len(owners) >= 2,
        "placeholder_count": len(placeholders),
        "placeholders": [dict(p) for p in placeholders],
    }


@router.get("/accounts/{account_id}/waterfall")
def budget_waterfall(account_id: str, conn: sqlite3.Connection = Depends(get_conn)):
    """Ordered narrative (Section 6b): current contract -> recovered vendor spend ->
    expansion increments -> total. Green additions / red subtractions is the single
    documented status-color exception; this endpoint returns no status indicators."""
    repo.get_row(conn, "accounts", account_id)
    steps = []
    current = conn.execute(
        "SELECT * FROM contract_versions WHERE account_id=? AND is_current=1 AND archived=0 ORDER BY created_at DESC LIMIT 1",
        (account_id,)).fetchone()
    base = (current["price"] or 0) if current else 0
    steps.append({"label": "Current contract", "amount": base, "kind": "start"})
    for r in repo.list_rows(conn, "recovered_spend", where="account_id=?", params=(account_id,)):
        steps.append({"label": r["label"], "amount": r["amount"], "kind": "add"})
    for x in repo.list_rows(conn, "expansion_opportunities",
                            where="account_id=? AND status='open' ORDER BY created_at", params=(account_id,)):
        if x["expected_value"]:
            steps.append({"label": x["name"], "amount": x["expected_value"], "kind": "add"})
    total = base + sum(s["amount"] for s in steps[1:])
    steps.append({"label": "Expansion total", "amount": total, "kind": "total"})
    return {"account_id": account_id, "steps": steps}


@router.get("/metric-definitions/{definition_id}/observations")
def observation_history(definition_id: str, conn: sqlite3.Connection = Depends(get_conn)):
    repo.get_row(conn, "metric_definitions", definition_id)
    rows = repo.list_rows(conn, "metric_observations",
                          where="definition_id=? ORDER BY period_label", params=(definition_id,))
    return {"definition_id": definition_id,
            "series": [{"period": r["period_label"], "value": r["value"], "target": r["target"]} for r in rows]}
