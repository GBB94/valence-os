"""Playbooks, plan instances, and governed exceptions (`ACCOUNT-PATH-SPEC.md` §13.4/§13.7).

These are the only writing routes in the readiness area, and none of them writes a state. They
write *plans* (which conditions are scheduled, at which version, due when) and *decisions* (which
conditions are excused, by whom, why). What is true stays a projection over the records.
"""
import sqlite3

from fastapi import APIRouter, Depends, HTTPException, Query

from .. import checklist_compatibility, phase_readiness, playbooks
from ..deps import get_conn

router = APIRouter(prefix="/api", tags=["playbooks"])


def _body(body: dict | None) -> dict:
    return body or {}


@router.get("/readiness/playbooks")
def list_playbooks(conn: sqlite3.Connection = Depends(get_conn)):
    """§13.3 — every playbook version, because an account stays on the one it instantiated."""
    return playbooks.list_playbooks(conn)


@router.get("/accounts/{account_id}/plan-instances")
def plan_instances(account_id: str, program_id: str | None = Query(default=None),
                   conn: sqlite3.Connection = Depends(get_conn)):
    """The merged plan: scheduling from the instance, every evaluative axis from readiness."""
    merged = playbooks.merged_plan(conn, account_id, program_id)
    merged["plans"] = playbooks.list_plans(conn, account_id, program_id)["plans"]
    merged["legacy_items"] = checklist_compatibility.legacy_items(conn, account_id, program_id)
    # The operational half of the merged standard (migration 0051). Beside the requirements, never
    # folded into them: a gate item carries no readiness axis and never acquires one.
    merged["setup_items"] = phase_readiness.setup_items(conn, account_id, program_id)
    # The deployment half. With these three arrays the payload carries the whole merged standard,
    # which is what lets the timeline draw a launch rather than two-thirds of one. Three arrays and
    # not one: each kind keeps its own vocabulary, and only the dates are shared.
    merged["milestones"] = phase_readiness.plan_milestones(conn, account_id, program_id)
    return merged


@router.post("/accounts/{account_id}/plan-instances")
def create_plan_instances(account_id: str, body: dict = None,
                          conn: sqlite3.Connection = Depends(get_conn)):
    """§13.4. Instantiating states an expectation; it never marks anything complete."""
    body = _body(body)
    if not body.get("playbook_key") or body.get("playbook_version") is None:
        raise HTTPException(422, "playbook_key and playbook_version are required")
    try:
        version = int(body["playbook_version"])
    except (TypeError, ValueError):
        raise HTTPException(422, "playbook_version must be an integer")
    return playbooks.instantiate(
        conn, account_id,
        playbook_key=body["playbook_key"], playbook_version=version,
        program_id=body.get("program_id"), anchor_type=body.get("anchor_type"),
        anchor_date=body.get("anchor_date"), excluded=body.get("excluded_requirements"),
        actor_id=body.get("actor_id"), note=body.get("note"),
    )


@router.post("/accounts/{account_id}/plan-instances/upgrade-preview")
def upgrade_preview(account_id: str, body: dict = None,
                    conn: sqlite3.Connection = Depends(get_conn)):
    """§13.9 — the diff an operator sees before an active plan moves. Writes nothing."""
    body = _body(body)
    if not body.get("playbook_key") or body.get("to_version") is None:
        raise HTTPException(422, "playbook_key and to_version are required")
    return playbooks.preview_upgrade(conn, account_id, playbook_key=body["playbook_key"],
                                     to_version=body["to_version"],
                                     program_id=body.get("program_id"))


@router.post("/accounts/{account_id}/plan-instances/upgrade")
def upgrade(account_id: str, body: dict = None, conn: sqlite3.Connection = Depends(get_conn)):
    body = _body(body)
    if not body.get("playbook_key") or body.get("to_version") is None:
        raise HTTPException(422, "playbook_key and to_version are required")
    return playbooks.apply_upgrade(conn, account_id, playbook_key=body["playbook_key"],
                                   to_version=body["to_version"],
                                   program_id=body.get("program_id"),
                                   excluded=body.get("excluded_requirements"),
                                   actor_id=body.get("actor_id"), note=body.get("note"))


@router.get("/accounts/{account_id}/readiness-exceptions/{requirement_key}")
def exception_history(account_id: str, requirement_key: str,
                      program_id: str | None = Query(default=None),
                      conn: sqlite3.Connection = Depends(get_conn)):
    """§13.7 — every decision ever recorded here, including the revoked and the lapsed ones."""
    return {"requirement_key": requirement_key,
            "history": playbooks.exception_history(conn, account_id, requirement_key, program_id)}


@router.post("/accounts/{account_id}/readiness-exceptions")
def set_exception(account_id: str, body: dict = None,
                  conn: sqlite3.Connection = Depends(get_conn)):
    """Record `not_applicable` or a waiver. Neither can mark a requirement met."""
    body = _body(body)
    for field in ("requirement_key", "kind", "reason"):
        if not body.get(field):
            raise HTTPException(422, f"{field} is required")
    return playbooks.set_exception(
        conn, account_id, requirement_key=body["requirement_key"], kind=body["kind"],
        reason=body["reason"], program_id=body.get("program_id"),
        decided_on=body.get("decided_on"), expires_on=body.get("expires_on"),
        actor_id=body.get("actor_id"),
    )


@router.post("/readiness-exceptions/{exception_id}/revoke")
def revoke_exception(exception_id: str, body: dict = None,
                     conn: sqlite3.Connection = Depends(get_conn)):
    body = _body(body)
    if not body.get("reason"):
        raise HTTPException(422, "reason is required")
    return playbooks.revoke_exception(conn, exception_id, reason=body["reason"],
                                      actor_id=body.get("actor_id"))


@router.post("/accounts/{account_id}/checklist-compatibility")
def run_compatibility(account_id: str, body: dict = None,
                      conn: sqlite3.Connection = Depends(get_conn)):
    """§13.5 — map exact template keys onto plan instances and return the per-account report.

    Idempotent, and `dry_run` runs the same computation without writing, so the preview cannot
    disagree with the run.
    """
    body = _body(body)
    return checklist_compatibility.migrate_account(
        conn, account_id, dry_run=bool(body.get("dry_run")), actor_id=body.get("actor_id"),
    )
