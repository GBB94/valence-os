import sqlite3

from fastapi import APIRouter, Depends, HTTPException

from .. import audit, phase_readiness, repo
from ..db import new_id, now_utc
from ..deps import get_conn
from ..schemas import (
    CommsCreate, ComplianceCreate, CompliancePatch, GateItemPatch, GateItemToggle, GateWaive,
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


@router.patch("/gate-items/{item_id}")
def patch_gate_item(item_id: str, b: GateItemPatch, conn: sqlite3.Connection = Depends(get_conn)):
    """Complete a gate item, push its date, or record the answer it was asking for.

    The merged launch standard (migration 0051) moved the operational half of the launch checklist
    onto phase gates, which brought two behaviours with it that `toggle` had no room for:

    * **Pushing the date.** The queue tells an operator to "do it, mark it done, or push the date",
      and a gate item now carries a date to push. Without this the third option was not real.
    * **Filling the field it asks about (PHASE-3-SPEC.md §1e).** "Confirm the success definition"
      exists to put an answer in `program.success_criteria`; a tick that left the field empty would
      record that the conversation happened and lose what it produced.

    `fills_field` still never writes on its own — nothing infers a value from a completion. The
    operator supplies `fill_value` and this patches exactly the one field the template named.
    """
    row = conn.execute(
        "SELECT gi.*, g.program_id, p.account_id FROM phase_gate_items gi "
        "JOIN phase_gates g ON g.id = gi.gate_id JOIN programs p ON p.id = g.program_id "
        "WHERE gi.id=?", (item_id,)).fetchone()
    if not row:
        raise HTTPException(404, "gate item not found")

    ts = now_utc()
    sets, params = [], []
    if b.complete is not None:
        sets += ["complete=?", "completed_on=?"]
        params += [1 if b.complete else 0, ts[:10] if b.complete else None]
    if b.due_date is not None:
        sets.append("due_date=?")
        params.append(b.due_date)
    if sets:
        with conn:
            conn.execute(f"UPDATE phase_gate_items SET {', '.join(sets)}, updated_at=? WHERE id=?",
                         (*params, ts, item_id))

    filled = None
    if b.fill_value and row["fills_field"]:
        target, _, field = row["fills_field"].partition(".")
        if target == "account":
            repo.patch(conn, "accounts", row["account_id"], {field: b.fill_value},
                       object_type="account")
            filled = row["fills_field"]
        elif target == "program":
            repo.patch(conn, "programs", row["program_id"], {field: b.fill_value},
                       object_type="program")
            filled = row["fills_field"]

    if b.complete:
        _maybe_autopass(conn, row["gate_id"])
    return {"gate": _gate_with_items(conn, row["gate_id"]), "filled_field": filled}


@router.post("/phase-gates/{gate_id}/waive")
def waive_gate(gate_id: str, b: GateWaive, conn: sqlite3.Connection = Depends(get_conn)):
    """Waiving settles the gate and moves nothing (`ACCOUNT-PATH-SPEC.md` §15.6).

    Slice 5 owns the semantics and this stays the only waive route, so there is one command
    rather than two that could disagree. Against the previous implementation that means: a
    `waived` row in `program_phase_events`, no `passed_on` stamp (a waived gate was never
    passed, and dating it as if it were is exactly the conflation §15.6 forbids), and the
    accepted gaps returned so the operator sees what the waiver did not fill.
    """
    waiver = phase_readiness.waive_gate(conn, gate_id, reason=b.waiver_reason)
    gate = _gate_with_items(conn, gate_id)
    gate["waiver"] = {key: waiver[key] for key in
                      ("event_id", "phase_unchanged", "unmet_at_waiver", "note")}
    return gate


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
