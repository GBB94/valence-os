"""Stage 7.5 API: five-slot qualification, operational triggers, renewal, and growth plans."""
import sqlite3

from fastapi import APIRouter, Depends, HTTPException

from .. import stage75
from ..deps import get_conn
from ..schemas import (
    AgreementEventAction, GrowthPlanCreate, GrowthPlanLineCreate, GrowthPlanLinePatch,
    OperationalAgreementCreate, OpportunityQualificationPatch,
)

router = APIRouter(prefix="/api", tags=["stage75"])


@router.get("/expansions/{opportunity_id}/qualification")
def get_qualification(opportunity_id: str, conn: sqlite3.Connection = Depends(get_conn)):
    return stage75.qualification(conn, opportunity_id)


@router.patch("/expansions/{opportunity_id}/qualification")
def patch_qualification(opportunity_id: str, body: OpportunityQualificationPatch,
                        conn: sqlite3.Connection = Depends(get_conn)):
    return stage75.set_qualification(conn, opportunity_id, body.model_dump(), body.model_fields_set)


@router.post("/operational-agreements", status_code=201)
def create_agreement(body: OperationalAgreementCreate,
                     conn: sqlite3.Connection = Depends(get_conn)):
    return stage75.create_agreement(conn, body.model_dump())


@router.get("/accounts/{account_id}/operational-agreements")
def list_agreements(account_id: str, conn: sqlite3.Connection = Depends(get_conn)):
    return stage75.agreements(conn, account_id)


@router.post("/operational-agreements/evaluate")
def evaluate_agreements(conn: sqlite3.Connection = Depends(get_conn)):
    return stage75.evaluate_agreements(conn)


@router.post("/operational-agreement-events/{event_id}/action", status_code=201)
def action_agreement(event_id: str, conn: sqlite3.Connection = Depends(get_conn)):
    return stage75.action_agreement_event(conn, event_id)


@router.post("/operational-agreement-events/{event_id}/dismiss")
def dismiss_agreement(event_id: str, body: AgreementEventAction,
                      conn: sqlite3.Connection = Depends(get_conn)):
    if not body.dismissal_reason:
        raise HTTPException(422, "dismissal reason is required")
    return stage75.dismiss_agreement_event(conn, event_id, body.dismissal_reason)


@router.get("/accounts/{account_id}/renewal-center")
def renewal_center(account_id: str, contract_id: str | None = None,
                   conn: sqlite3.Connection = Depends(get_conn)):
    return stage75.renewal_center(conn, account_id, contract_id)


@router.post("/growth-plans", status_code=201)
def create_growth_plan(body: GrowthPlanCreate, conn: sqlite3.Connection = Depends(get_conn)):
    return stage75.create_growth_plan(conn, body.model_dump())


@router.get("/accounts/{account_id}/growth-plan")
def get_growth_plan(account_id: str, conn: sqlite3.Connection = Depends(get_conn)):
    return stage75.growth_plan(conn, account_id)


@router.post("/growth-plan-lines", status_code=201)
def create_growth_line(body: GrowthPlanLineCreate,
                       conn: sqlite3.Connection = Depends(get_conn)):
    return stage75.create_growth_line(conn, body.model_dump())


@router.patch("/growth-plan-lines/{line_id}")
def patch_growth_line(line_id: str, body: GrowthPlanLinePatch,
                      conn: sqlite3.Connection = Depends(get_conn)):
    return stage75.patch_growth_line(conn, line_id, body.model_dump(), body.model_fields_set)
