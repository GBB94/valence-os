"""HTTP boundary for product feedback themes and account occurrences."""
import sqlite3

from fastapi import APIRouter, Depends

from .. import product_feedback as service
from ..deps import get_conn
from ..schemas import (FeedbackItemCreate, FeedbackOccurrenceCreate, FeedbackOccurrenceMove,
                       FeedbackStatus, FeedbackTouchCreate)

router = APIRouter(prefix="/api", tags=["product-feedback"])


@router.get("/product-feedback")
def items(account_id: str | None = None, conn: sqlite3.Connection = Depends(get_conn)):
    return service.list_items(conn, account_id)


@router.post("/product-feedback", status_code=201)
def create(body: FeedbackItemCreate, conn: sqlite3.Connection = Depends(get_conn)):
    return service.create_item(conn, body.model_dump())


@router.post("/product-feedback/{item_id}/occurrences", status_code=201)
def occurrence(item_id: str, body: FeedbackOccurrenceCreate, conn: sqlite3.Connection = Depends(get_conn)):
    return service.add_occurrence(conn, item_id, body.model_dump())


@router.post("/product-feedback/{item_id}/status")
def status(item_id: str, body: FeedbackStatus, conn: sqlite3.Connection = Depends(get_conn)):
    return service.transition(conn, item_id, body.model_dump())


@router.post("/product-feedback-occurrences/{occurrence_id}/touches", status_code=201)
def touch(occurrence_id: str, body: FeedbackTouchCreate, conn: sqlite3.Connection = Depends(get_conn)):
    return service.record_touch(conn, occurrence_id, body.touch_type, body.interaction_id)


@router.post("/product-feedback-occurrences/{occurrence_id}/move")
def move(occurrence_id: str, body: FeedbackOccurrenceMove, conn: sqlite3.Connection = Depends(get_conn)):
    return service.move_occurrence(conn, occurrence_id, body.feedback_item_id, body.reason)
