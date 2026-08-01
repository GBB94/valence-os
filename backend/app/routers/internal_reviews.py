"""HTTP boundary for internal account reviews and governed status."""
import sqlite3

from fastapi import APIRouter, Depends

from .. import internal_reporting, internal_reviews as service
from ..deps import get_conn
from ..schemas import (AccountReviewCreate, AccountReviewHold, OperatorViewCreate,
                       StatusAssessmentCreate, StatusCriteriaCreate)

router = APIRouter(prefix="/api", tags=["internal-reviews"])


@router.get("/status-criteria")
def criteria(account_id: str | None = None, conn: sqlite3.Connection = Depends(get_conn)):
    if account_id:
        return [dict(r) for r in conn.execute("SELECT * FROM status_criteria_versions WHERE archived=0 AND (account_id IS NULL OR account_id=?) ORDER BY dimension,account_id", (account_id,))]
    return [dict(r) for r in conn.execute("SELECT * FROM status_criteria_versions WHERE archived=0 ORDER BY dimension,account_id")]


@router.post("/status-criteria", status_code=201)
def create_criteria(body: StatusCriteriaCreate, conn: sqlite3.Connection = Depends(get_conn)):
    return service.create_criteria(conn, body.model_dump())


@router.get("/accounts/{account_id}/reviews")
def reviews(account_id: str, conn: sqlite3.Connection = Depends(get_conn)):
    return service.list_reviews(conn, account_id)


@router.post("/accounts/{account_id}/reviews", status_code=201)
def create_review(account_id: str, body: AccountReviewCreate, conn: sqlite3.Connection = Depends(get_conn)):
    return service.create_review(conn, account_id, body.model_dump())


@router.post("/account-reviews/{review_id}/hold")
def hold(review_id: str, body: AccountReviewHold, conn: sqlite3.Connection = Depends(get_conn)):
    return service.hold_review(conn, review_id, body.held_on, body.source_interaction_id)


@router.get("/accounts/{account_id}/operator-views")
def views(account_id: str, conn: sqlite3.Connection = Depends(get_conn)):
    return service.list_operator_views(conn, account_id)


@router.post("/accounts/{account_id}/operator-views", status_code=201)
def create_view(account_id: str, body: OperatorViewCreate, conn: sqlite3.Connection = Depends(get_conn)):
    return service.create_operator_view(conn, account_id, body.model_dump())


@router.post("/accounts/{account_id}/status-assessments", status_code=201)
def assess(account_id: str, body: StatusAssessmentCreate, conn: sqlite3.Connection = Depends(get_conn)):
    return service.assess_status(conn, account_id, body.model_dump())


@router.get("/account-reviews/{review_id}/challenge-sheet")
def challenge(review_id: str, conn: sqlite3.Connection = Depends(get_conn)):
    return service.challenge_sheet(conn, review_id)


@router.post("/account-reviews/{review_id}/documents/{kind}", status_code=201)
def document(review_id: str, kind: str, conn: sqlite3.Connection = Depends(get_conn)):
    return internal_reporting.generate_review_artifact(conn, review_id, kind)
