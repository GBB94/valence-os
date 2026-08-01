"""Adoption campaign endpoints (Stage 11.0).

Thin by design — all derivation and transition logic lives in `app/campaigns.py`. Two rules are
visible in the shape of this router:

  * **There is no generic status patch.** `PATCH /campaigns/{id}` edits draft content only;
    every lifecycle move is its own endpoint carrying a reason, so "why is this paused" is always
    answerable from the record.
  * **Linked records are validated against the campaign's account.** The recurring defect in this
    repo is looking a row up by id and trusting the caller about where it belongs; the DB triggers
    are the backstop, these checks are the readable error.
"""
import json
import sqlite3

from fastapi import APIRouter, Depends, HTTPException

from .. import audit, campaigns, repo
from ..db import new_id, now_utc
from ..deps import get_conn
from ..schemas import (
    CampaignBarrierCreate, CampaignBarrierPatch, CampaignCheckpointCreate, CampaignCheckpointHold,
    CampaignCreate, CampaignPatch, CampaignPlanLinkCreate, CampaignTargetCreate, CampaignTransition,
)

router = APIRouter(prefix="/api", tags=["campaigns"])

# Plan-link column -> the table it must exist in, and how that table reaches an account.
_LINK_SCOPE = {
    "task_id": ("tasks", "program"),
    "commitment_id": ("commitments", "program_or_account"),
    "milestone_id": ("milestones", "program"),
    "comms_entry_id": ("comms_entries", "program"),
    "deployment_moment_id": ("deployment_moments", "program"),
    "calendar_event_id": ("calendar_events", "account"),
    "generated_document_id": ("generated_documents", "account"),
    "messaging_entry_id": ("messaging_entries", "global"),
}


def _require_scoped_link(conn, column: str, object_id: str, account_id: str) -> None:
    table, reach = _LINK_SCOPE[column]
    row = conn.execute(f"SELECT * FROM {table} WHERE id=?", (object_id,)).fetchone()
    if not row:
        raise HTTPException(422, f"no {table[:-1]} with id {object_id}")
    if reach == "global":
        return
    row = dict(row)
    owner = row.get("account_id")
    if owner is None and row.get("program_id"):
        program = conn.execute("SELECT account_id FROM programs WHERE id=?",
                               (row["program_id"],)).fetchone()
        owner = program["account_id"] if program else None
    if owner != account_id:
        raise HTTPException(422, f"that {table[:-1]} belongs to a different account")


# --- campaigns ------------------------------------------------------------------------------
@router.post("/campaigns", status_code=201)
def create_campaign(b: CampaignCreate, conn: sqlite3.Connection = Depends(get_conn)):
    repo.get_row(conn, "accounts", b.account_id)
    return repo.insert(conn, "adoption_campaigns", b.model_dump(), object_type="adoption_campaign")


@router.get("/accounts/{account_id}/campaigns")
def list_campaigns(account_id: str, status: str | None = None,
                   conn: sqlite3.Connection = Depends(get_conn)):
    repo.get_row(conn, "accounts", account_id)
    where, params = "account_id=?", [account_id]
    if status:
        where += " AND status=?"
        params.append(status)
    rows = repo.list_rows(conn, "adoption_campaigns",
                          where=where + " ORDER BY planned_start_on DESC", params=tuple(params))
    populations = {s["id"]: s["name"] for s in repo.list_rows(conn, "population_segments", where="1=1")}
    populations.update({v["id"]: v["name"] for v in repo.list_rows(conn, "population_views", where="1=1")})
    use_cases = {u["id"]: u["name"] for u in repo.list_rows(conn, "use_cases", where="1=1")}
    for r in rows:
        r["population"] = populations.get(r["segment_id"] or r["view_id"])
        r["use_case"] = use_cases.get(r["use_case_id"])
    return rows


@router.get("/campaigns/{campaign_id}")
def get_campaign(campaign_id: str, conn: sqlite3.Connection = Depends(get_conn)):
    return campaigns.detail(conn, campaign_id)


@router.patch("/campaigns/{campaign_id}")
def patch_campaign(campaign_id: str, b: CampaignPatch, conn: sqlite3.Connection = Depends(get_conn)):
    """Draft content only. A completed or cancelled campaign is immutable (§2.2)."""
    c = repo.get_row(conn, "adoption_campaigns", campaign_id)
    if c["status"] in ("completed", "cancelled"):
        raise HTTPException(422, f"a {c['status']} campaign is immutable except for archival")
    return repo.patch(conn, "adoption_campaigns", campaign_id, b.model_dump(),
                      object_type="adoption_campaign")


@router.get("/campaigns/{campaign_id}/readiness")
def get_readiness(campaign_id: str, conn: sqlite3.Connection = Depends(get_conn)):
    return campaigns.readiness(conn, campaign_id)


def _transition(conn, campaign_id, to_status, b: CampaignTransition, extra_fields=()):
    extra = {k: getattr(b, k) for k in extra_fields if getattr(b, k) is not None}
    return campaigns.transition(conn, campaign_id, to_status, reason=b.reason,
                                actor=b.actor or audit.DEFAULT_ACTOR, extra=extra)


@router.post("/campaigns/{campaign_id}/ready")
def mark_ready(campaign_id: str, b: CampaignTransition, conn: sqlite3.Connection = Depends(get_conn)):
    """Locks the baseline series (§5.1) as a side effect — that is what readiness *means*."""
    return _transition(conn, campaign_id, "ready", b)


@router.post("/campaigns/{campaign_id}/activate")
def activate(campaign_id: str, b: CampaignTransition, conn: sqlite3.Connection = Depends(get_conn)):
    return _transition(conn, campaign_id, "active", b)


@router.post("/campaigns/{campaign_id}/pause")
def pause(campaign_id: str, b: CampaignTransition, conn: sqlite3.Connection = Depends(get_conn)):
    if not b.pause_reason or not b.resume_condition:
        raise HTTPException(422, "pausing records why and what would resume it")
    return _transition(conn, campaign_id, "paused", b, ("pause_reason", "resume_condition"))


@router.post("/campaigns/{campaign_id}/resume")
def resume(campaign_id: str, b: CampaignTransition, conn: sqlite3.Connection = Depends(get_conn)):
    return _transition(conn, campaign_id, "active", b)


@router.post("/campaigns/{campaign_id}/complete")
def complete(campaign_id: str, b: CampaignTransition, conn: sqlite3.Connection = Depends(get_conn)):
    if not b.completion_outcome or not b.completion_reviewed_on:
        raise HTTPException(422, "completion records an outcome and the date it was reviewed")
    return _transition(conn, campaign_id, "completed", b,
                       ("completion_outcome", "completion_reviewed_on", "completion_note"))


@router.post("/campaigns/{campaign_id}/cancel")
def cancel(campaign_id: str, b: CampaignTransition, conn: sqlite3.Connection = Depends(get_conn)):
    if not b.cancel_reason:
        raise HTTPException(422, "cancelling records why")
    return _transition(conn, campaign_id, "cancelled", b, ("cancel_reason",))


# --- barriers -------------------------------------------------------------------------------
@router.post("/campaigns/{campaign_id}/barriers", status_code=201)
def add_barrier(campaign_id: str, b: CampaignBarrierCreate,
                conn: sqlite3.Connection = Depends(get_conn)):
    repo.get_row(conn, "adoption_campaigns", campaign_id)
    values = {**b.model_dump(), "campaign_id": campaign_id,
              "is_primary": 1 if b.is_primary else 0}
    return repo.insert(conn, "adoption_campaign_barriers", values,
                       object_type="adoption_campaign_barrier")


@router.patch("/campaign-barriers/{barrier_id}")
def patch_barrier(barrier_id: str, b: CampaignBarrierPatch,
                  conn: sqlite3.Connection = Depends(get_conn)):
    changes = b.model_dump()
    if changes.get("is_primary") is not None:
        changes["is_primary"] = 1 if changes["is_primary"] else 0
    return repo.patch(conn, "adoption_campaign_barriers", barrier_id, changes,
                      object_type="adoption_campaign_barrier")


# --- targets --------------------------------------------------------------------------------
@router.post("/campaigns/{campaign_id}/targets", status_code=201)
def add_target(campaign_id: str, b: CampaignTargetCreate,
               conn: sqlite3.Connection = Depends(get_conn)):
    """Scope and comparator-disjointness are enforced by trigger; these are the readable errors."""
    c = repo.get_row(conn, "adoption_campaigns", campaign_id)
    vt = repo.get_row(conn, "value_targets", b.value_target_id)
    if vt["account_id"] != c["account_id"]:
        raise HTTPException(422, "that value target belongs to a different account")
    if (vt.get("segment_id") or None) != (c.get("segment_id") or None) or \
       (vt.get("view_id") or None) != (c.get("view_id") or None):
        raise HTTPException(422, "the value target names a different population than the campaign")
    if b.comparator_segment_id or b.comparator_view_id:
        _check_comparator(conn, c, b.comparator_segment_id, b.comparator_view_id)
    return repo.insert(conn, "adoption_campaign_targets",
                       {**b.model_dump(), "campaign_id": campaign_id},
                       object_type="adoption_campaign_target")


def _members(conn, segment_id: str | None, view_id: str | None) -> set[str]:
    """Resolve a population to its base-segment set — the same resolution growth-line overlap
    detection uses. A view and a segment are only comparable once both are base segments."""
    if segment_id:
        return {segment_id}
    return {r["segment_id"] for r in conn.execute(
        "SELECT segment_id FROM population_view_segments WHERE view_id=?", (view_id,))}


def _check_comparator(conn, campaign: dict, seg: str | None, view: str | None) -> None:
    """§5.2 — the control cannot contain the treated cohort.

    Views overlap segments by construction here, so without this a comparator view containing the
    target segment would quietly absorb the effect it exists to isolate.
    """
    for column, value in (("population_segments", seg), ("population_views", view)):
        if value:
            row = repo.get_row(conn, column, value)
            if row["account_id"] != campaign["account_id"]:
                raise HTTPException(422, "the comparator population belongs to a different account")
    treated = _members(conn, campaign.get("segment_id"), campaign.get("view_id"))
    control = _members(conn, seg, view)
    overlap = treated & control
    if overlap:
        raise HTTPException(422, "the comparator population overlaps the treated cohort "
                                 f"({len(overlap)} shared base segment(s)); a control that "
                                 f"contains the treated cannot isolate the effect")


# --- plan links -----------------------------------------------------------------------------
@router.post("/campaigns/{campaign_id}/plan", status_code=201)
def add_plan_link(campaign_id: str, b: CampaignPlanLinkCreate,
                  conn: sqlite3.Connection = Depends(get_conn)):
    c = repo.get_row(conn, "adoption_campaigns", campaign_id)
    values = {**b.model_dump(), "campaign_id": campaign_id,
              "is_reinforcement": 1 if b.is_reinforcement else 0}
    for column in _LINK_SCOPE:
        if values.get(column):
            _require_scoped_link(conn, column, values[column], c["account_id"])
    if values.get("intended_barrier_id"):
        barrier = repo.get_row(conn, "adoption_campaign_barriers", values["intended_barrier_id"])
        if barrier["campaign_id"] != campaign_id:
            raise HTTPException(422, "that barrier belongs to a different campaign")
    return repo.insert(conn, "adoption_campaign_plan_links", values,
                       object_type="adoption_campaign_plan_link")


@router.delete("/campaign-plan-links/{link_id}", status_code=204)
def remove_plan_link(link_id: str, conn: sqlite3.Connection = Depends(get_conn)):
    repo.archive(conn, "adoption_campaign_plan_links", link_id,
                 object_type="adoption_campaign_plan_link")


# --- checkpoints ----------------------------------------------------------------------------
@router.post("/campaigns/{campaign_id}/checkpoints", status_code=201)
def add_checkpoint(campaign_id: str, b: CampaignCheckpointCreate,
                   conn: sqlite3.Connection = Depends(get_conn)):
    repo.get_row(conn, "adoption_campaigns", campaign_id)
    return repo.insert(conn, "adoption_campaign_checkpoints",
                       {**b.model_dump(), "campaign_id": campaign_id},
                       object_type="adoption_campaign_checkpoint")


@router.post("/campaign-checkpoints/{checkpoint_id}/hold")
def hold_checkpoint(checkpoint_id: str, b: CampaignCheckpointHold,
                    conn: sqlite3.Connection = Depends(get_conn)):
    """Record the review. Adjusting appends plan links; it never rewrites the hypothesis or the
    locked baseline (§5.3)."""
    cp = repo.get_row(conn, "adoption_campaign_checkpoints", checkpoint_id)
    changes = b.model_dump()
    changes["observations_reviewed_json"] = json.dumps(changes.pop("observations_reviewed"))
    return repo.patch(conn, "adoption_campaign_checkpoints", checkpoint_id, changes,
                      object_type="adoption_campaign_checkpoint")
