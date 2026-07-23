import sqlite3

from fastapi import APIRouter, Depends, HTTPException

from .. import audit, repo
from ..db import new_id, now_utc
from ..deps import get_conn
from ..schemas import (
    CommsCreate, ComplianceCreate, CompliancePatch, GateItemToggle, GateWaive,
    GovernancePatch, MomentCreate, PhaseGateCreate, ScopeChangeCreate,
)

router = APIRouter(prefix="/api", tags=["delivery"])


# --- Phase gates + items ---
@router.post("/phase-gates", status_code=201)
def create_gate(b: PhaseGateCreate, conn: sqlite3.Connection = Depends(get_conn)):
    repo.get_row(conn, "programs", b.program_id)
    data = {k: v for k, v in b.model_dump().items() if k != "items"}
    gate = repo.insert(conn, "phase_gates", data, object_type="phase_gate")
    ts = now_utc()
    with conn:
        for desc in b.items:
            if desc.strip():
                conn.execute(
                    "INSERT INTO phase_gate_items (id, gate_id, description, complete, created_at, updated_at) "
                    "VALUES (?,?,?,0,?,?)", (new_id(), gate["id"], desc.strip(), ts, ts),
                )
    return _gate_with_items(conn, gate["id"])


@router.post("/gate-items/{item_id}/toggle")
def toggle_gate_item(item_id: str, b: GateItemToggle, conn: sqlite3.Connection = Depends(get_conn)):
    row = conn.execute("SELECT * FROM phase_gate_items WHERE id=?", (item_id,)).fetchone()
    if not row:
        raise HTTPException(404, "gate item not found")
    ts = now_utc()
    with conn:
        conn.execute("UPDATE phase_gate_items SET complete=?, completed_on=?, updated_at=? WHERE id=?",
                     (1 if b.complete else 0, ts[:10] if b.complete else None, ts, item_id))
    _maybe_autopass(conn, row["gate_id"])
    return _gate_with_items(conn, row["gate_id"])


@router.post("/phase-gates/{gate_id}/waive")
def waive_gate(gate_id: str, b: GateWaive, conn: sqlite3.Connection = Depends(get_conn)):
    before = repo.get_row(conn, "phase_gates", gate_id)
    with conn:
        conn.execute("UPDATE phase_gates SET status='waived', waiver_reason=?, waived_by=?, "
                     "passed_on=?, updated_at=? WHERE id=?",
                     (b.waiver_reason, audit.DEFAULT_ACTOR, now_utc()[:10], now_utc(), gate_id))
        after = repo.get_row(conn, "phase_gates", gate_id)
        audit.record(conn, object_type="phase_gate", object_id=gate_id, action="close",
                     before=before, after=after)
    return _gate_with_items(conn, gate_id)


def _maybe_autopass(conn, gate_id):
    gate = repo.get_row(conn, "phase_gates", gate_id)
    if gate["status"] != "open":
        return
    items = conn.execute("SELECT complete FROM phase_gate_items WHERE gate_id=?", (gate_id,)).fetchall()
    if items and all(i["complete"] for i in items):
        with conn:
            conn.execute("UPDATE phase_gates SET status='passed', passed_on=?, updated_at=? WHERE id=?",
                         (now_utc()[:10], now_utc(), gate_id))
            audit.record(conn, object_type="phase_gate", object_id=gate_id, action="close",
                         before=gate, after=repo.get_row(conn, "phase_gates", gate_id))


def _gate_with_items(conn, gate_id):
    gate = repo.get_row(conn, "phase_gates", gate_id)
    gate["items"] = [repo.row_to_dict(r) for r in
                     conn.execute("SELECT * FROM phase_gate_items WHERE gate_id=? ORDER BY created_at", (gate_id,))]
    return gate


# --- Deployment moments + comms ---
@router.post("/deployment-moments", status_code=201)
def create_moment(b: MomentCreate, conn: sqlite3.Connection = Depends(get_conn)):
    repo.get_row(conn, "programs", b.program_id)
    return repo.insert(conn, "deployment_moments", b.model_dump(), object_type="deployment_moment")


@router.post("/comms-entries", status_code=201)
def create_comms(b: CommsCreate, conn: sqlite3.Connection = Depends(get_conn)):
    repo.get_row(conn, "programs", b.program_id)
    return repo.insert(conn, "comms_entries", b.model_dump(), object_type="comms_entry")


# --- Compliance / readiness ---
@router.post("/compliance-items", status_code=201)
def create_compliance(b: ComplianceCreate, conn: sqlite3.Connection = Depends(get_conn)):
    repo.get_row(conn, "programs", b.program_id)
    return repo.insert(conn, "compliance_items", b.model_dump(), object_type="compliance_item")


@router.patch("/compliance-items/{item_id}")
def patch_compliance(item_id: str, b: CompliancePatch, conn: sqlite3.Connection = Depends(get_conn)):
    return repo.patch(conn, "compliance_items", item_id, b.model_dump(), object_type="compliance_item")


# --- Scope changes ---
@router.post("/scope-changes", status_code=201)
def create_scope_change(b: ScopeChangeCreate, conn: sqlite3.Connection = Depends(get_conn)):
    repo.get_row(conn, "programs", b.program_id)
    return repo.insert(conn, "scope_changes", b.model_dump(), object_type="scope_change")


# --- Governance cadence on the program ---
@router.patch("/programs/{program_id}/governance")
def patch_governance(program_id: str, b: GovernancePatch, conn: sqlite3.Connection = Depends(get_conn)):
    return repo.patch(conn, "programs", program_id, b.model_dump(), object_type="program")


# --- Program-level aggregation of all v1 delivery objects ---
@router.get("/programs/{program_id}/delivery")
def program_delivery(program_id: str, conn: sqlite3.Connection = Depends(get_conn)):
    repo.get_row(conn, "programs", program_id)
    names = {p["id"]: p["name"] for p in repo.list_rows(conn, "persons", where="1=1")}
    gates = repo.list_rows(conn, "phase_gates", where="program_id=? ORDER BY created_at", params=(program_id,))
    for g in gates:
        g["items"] = [repo.row_to_dict(r) for r in
                      conn.execute("SELECT * FROM phase_gate_items WHERE gate_id=? ORDER BY created_at", (g["id"],))]
    moments = repo.list_rows(conn, "deployment_moments", where="program_id=? ORDER BY event_date", params=(program_id,))
    for m in moments:
        m["client_owner_name"] = names.get(m["client_owner_person_id"])
    compliance = repo.list_rows(conn, "compliance_items", where="program_id=? ORDER BY lane", params=(program_id,))
    for c in compliance:
        c["owner_name"] = names.get(c["owner_person_id"])
    scope = repo.list_rows(conn, "scope_changes", where="program_id=? ORDER BY changed_on DESC", params=(program_id,))
    for s in scope:
        s["agreed_by_name"] = names.get(s["agreed_by_person_id"])
    comms = repo.list_rows(conn, "comms_entries", where="program_id=? ORDER BY send_date DESC", params=(program_id,))
    return {"phase_gates": gates, "deployment_moments": moments, "compliance_items": compliance,
            "scope_changes": scope, "comms_entries": comms}
