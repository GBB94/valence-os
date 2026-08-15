"""Account Path Slice 5 — relationship, evidence, gate-readiness, and phase-transition routes.

`ACCOUNT-PATH-SPEC.md` §15. The reads write nothing. The writes write links, decisions, and phase
history — never a readiness state, because there is nowhere to write one.
"""
import sqlite3

from fastapi import APIRouter, Depends, HTTPException, Query

from .. import path_links, phase_readiness
from ..deps import get_conn

router = APIRouter(prefix="/api", tags=["account-path"])


def _body(body: dict | None) -> dict:
    return body or {}


# --- requirement relationships ---------------------------------------------------------------

@router.get("/plan-instances/{plan_instance_id}/links")
def requirement_links(plan_instance_id: str, conn: sqlite3.Connection = Depends(get_conn)):
    """§15.8 — the requirement detail panel: linked actions, attached evidence, dependent gates."""
    return path_links.requirement_links(conn, plan_instance_id)


@router.post("/plan-instances/{plan_instance_id}/action-links")
def link_action(plan_instance_id: str, body: dict = None,
                conn: sqlite3.Connection = Depends(get_conn)):
    body = _body(body)
    return path_links.link_action(
        conn, plan_instance_id, task_id=body.get("task_id"),
        commitment_id=body.get("commitment_id"), relation=body.get("relation", "advances"),
        origin=body.get("origin", "operator"), source_type=body.get("source_type"),
        source_id=body.get("source_id"), note=body.get("note"), actor_id=body.get("actor_id"),
    )


@router.post("/action-links/{link_id}/archive")
def archive_action_link(link_id: str, body: dict = None,
                        conn: sqlite3.Connection = Depends(get_conn)):
    body = _body(body)
    return path_links.archive_action_link(conn, link_id, reason=body.get("reason", ""),
                                          actor_id=body.get("actor_id"))


# --- evidence ---------------------------------------------------------------------------------

@router.get("/readiness/evidence-types")
def evidence_types():
    """The §15.3 allowlist, so the review surface offers exactly what the write path accepts."""
    return {"evidence_types": list(path_links.EVIDENCE_TYPES),
            "account_fields": sorted(path_links._ACCOUNT_FIELDS),
            "program_fields": sorted(path_links._PROGRAM_FIELDS)}


@router.post("/plan-instances/{plan_instance_id}/evidence")
def attach_evidence(plan_instance_id: str, body: dict = None,
                    conn: sqlite3.Connection = Depends(get_conn)):
    body = _body(body)
    for field in ("evidence_type", "evidence_id"):
        if not body.get(field):
            raise HTTPException(422, f"{field} is required")
    return path_links.attach_evidence(
        conn, plan_instance_id, evidence_type=body["evidence_type"],
        evidence_id=body["evidence_id"], note=body.get("note"),
        reviewed_on=body.get("reviewed_on"), review_note=body.get("review_note"),
        actor_id=body.get("actor_id"),
    )


@router.post("/evidence-links/{link_id}/review")
def review_evidence(link_id: str, body: dict = None,
                    conn: sqlite3.Connection = Depends(get_conn)):
    body = _body(body)
    if not body.get("reviewed_on"):
        raise HTTPException(422, "reviewed_on is required")
    return path_links.review_evidence(conn, link_id, reviewed_on=body["reviewed_on"],
                                      review_note=body.get("review_note", ""),
                                      actor_id=body.get("actor_id"))


@router.post("/evidence-links/{link_id}/retract")
def retract_evidence(link_id: str, body: dict = None,
                     conn: sqlite3.Connection = Depends(get_conn)):
    body = _body(body)
    return path_links.retract_evidence(conn, link_id, reason=body.get("reason", ""),
                                       superseded_by_id=body.get("superseded_by_id"),
                                       actor_id=body.get("actor_id"))


# --- milestone and gate relationships ---------------------------------------------------------

@router.get("/milestones/{milestone_id}/action-links")
def milestone_links(milestone_id: str, conn: sqlite3.Connection = Depends(get_conn)):
    """§15.8 — the timeline's dependency lines, and only the explicit ones."""
    return path_links.milestone_links(conn, milestone_id)


@router.post("/milestones/{milestone_id}/action-links")
def link_milestone_action(milestone_id: str, body: dict = None,
                          conn: sqlite3.Connection = Depends(get_conn)):
    body = _body(body)
    return path_links.link_milestone_action(
        conn, milestone_id, task_id=body.get("task_id"),
        commitment_id=body.get("commitment_id"), relation=body.get("relation", "advances"),
        note=body.get("note"), actor_id=body.get("actor_id"),
    )


@router.post("/milestone-action-links/{link_id}/archive")
def archive_milestone_link(link_id: str, body: dict = None,
                           conn: sqlite3.Connection = Depends(get_conn)):
    body = _body(body)
    return path_links.archive_milestone_link(conn, link_id, reason=body.get("reason", ""),
                                             actor_id=body.get("actor_id"))


@router.post("/phase-gates/{gate_id}/requirement-links")
def link_gate_requirement(gate_id: str, body: dict = None,
                          conn: sqlite3.Connection = Depends(get_conn)):
    body = _body(body)
    if not body.get("plan_instance_id"):
        raise HTTPException(422, "plan_instance_id is required")
    return path_links.link_gate_requirement(
        conn, gate_id, plan_instance_id=body["plan_instance_id"],
        necessity=body.get("necessity", "required"), note=body.get("note"),
        actor_id=body.get("actor_id"),
    )


@router.post("/gate-requirement-links/{link_id}/archive")
def archive_gate_link(link_id: str, body: dict = None,
                      conn: sqlite3.Connection = Depends(get_conn)):
    body = _body(body)
    return path_links.archive_gate_link(conn, link_id, reason=body.get("reason", ""),
                                        actor_id=body.get("actor_id"))


# --- action detail ------------------------------------------------------------------------------

@router.get("/actions/{action_type}/{action_id}/path-context")
def action_context(action_type: str, action_id: str,
                   conn: sqlite3.Connection = Depends(get_conn)):
    """§15.8 — the inverse read: what this Task or Commitment advances."""
    if action_type not in ("task", "commitment"):
        raise HTTPException(422, "action_type must be task or commitment")
    return path_links.action_context(
        conn, task_id=action_id if action_type == "task" else None,
        commitment_id=action_id if action_type == "commitment" else None,
    )


@router.post("/actions/{action_type}/{action_id}/close-with-successor")
def close_with_successor(action_type: str, action_id: str, body: dict = None,
                         conn: sqlite3.Connection = Depends(get_conn)):
    """§15.7 — close through the native flow and carry the relationship to a successor.

    Closing settles the action. It does not settle the requirement, and the response says so.
    """
    body = _body(body)
    return path_links.close_with_successor(
        conn, action_type=action_type, action_id=action_id, closure=body.get("closure"),
        successor=body.get("successor"), actor_id=body.get("actor_id"),
    )


# --- gate readiness and phase transitions -------------------------------------------------------

@router.get("/programs/{program_id}/phase-readiness")
def program_phase_readiness(program_id: str, as_of: str | None = Query(default=None),
                            conn: sqlite3.Connection = Depends(get_conn)):
    """§15.5. `ready` means the contract is satisfied. It does not advance anything."""
    return phase_readiness.phase_readiness(conn, program_id, as_of=as_of)


@router.get("/programs/{program_id}/phase-transitions")
def program_phase_history(program_id: str, conn: sqlite3.Connection = Depends(get_conn)):
    return phase_readiness.history(conn, program_id)


@router.post("/programs/{program_id}/phase-transitions")
def create_phase_transition(program_id: str, body: dict = None,
                            conn: sqlite3.Connection = Depends(get_conn)):
    """§15.6. Version-checked, atomic, and append-only in history.

    `outcome: "proposed"` records the intent without moving anything; it is the honest thing to
    submit when the gate is blocked and the team still wants the expectation on the record.
    """
    body = _body(body)
    outcome = body.get("outcome", "completed")
    if outcome not in ("completed", "proposed"):
        raise HTTPException(422, "outcome must be completed or proposed")
    if not body.get("requested_next_phase"):
        raise HTTPException(422, "requested_next_phase is required")
    if outcome == "proposed":
        return phase_readiness.propose(
            conn, program_id, requested_next_phase=body["requested_next_phase"],
            note=body.get("note"), actor_id=body.get("actor_id"), as_of=body.get("as_of"))
    for field in ("expected_current_phase", "readiness_stamp"):
        if not body.get(field):
            raise HTTPException(422, f"{field} is required")
    return phase_readiness.transition(
        conn, program_id, expected_current_phase=body["expected_current_phase"],
        requested_next_phase=body["requested_next_phase"],
        readiness_stamp=body["readiness_stamp"], actor_id=body.get("actor_id"),
        override=bool(body.get("override")), reason=body.get("reason"), as_of=body.get("as_of"),
    )


# Waiving a gate is deliberately NOT routed here. `POST /api/phase-gates/{gate_id}/waive` already
# exists in `routers/delivery.py` and now delegates to `phase_readiness.waive_gate`, so the §15.6
# semantics govern the one command every existing caller already uses. A second route on the same
# path would have been shadowed by registration order and left two waives that disagree.
