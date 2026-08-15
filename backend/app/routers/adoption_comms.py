"""Stage 13 thin routes for planned comms waves and session attendance."""
import sqlite3

from fastapi import APIRouter, Depends

from .. import adoption_comms
from ..deps import get_conn
from ..schemas import (
    AttendeeRecord, CommsSequenceCancel, CommsSequenceCreate, CommsSessionCreate,
    CommsWaveCreate, CommsWavePatch, CommsWaveSent,
)

router = APIRouter(prefix="/api", tags=["adoption-comms"])


@router.get("/accounts/{account_id}/comms-sequences")
def list_sequences(account_id: str, conn: sqlite3.Connection = Depends(get_conn)):
    return {"sequences": adoption_comms.list_for_account(conn, account_id)}


@router.post("/comms-sequences", status_code=201)
def create_sequence(body: CommsSequenceCreate, conn: sqlite3.Connection = Depends(get_conn)):
    return adoption_comms.create_sequence(conn, body.model_dump())


@router.get("/comms-sequences/{sequence_id}")
def get_sequence(sequence_id: str, conn: sqlite3.Connection = Depends(get_conn)):
    return adoption_comms.sequence(conn, sequence_id)


@router.post("/comms-sequences/{sequence_id}/cancel")
def cancel_sequence(sequence_id: str, body: CommsSequenceCancel,
                    conn: sqlite3.Connection = Depends(get_conn)):
    return adoption_comms.cancel_sequence(conn, sequence_id, body.reason)


@router.post("/comms-sequences/{sequence_id}/waves", status_code=201)
def create_wave(sequence_id: str, body: CommsWaveCreate,
                conn: sqlite3.Connection = Depends(get_conn)):
    return adoption_comms.create_wave(conn, sequence_id, body.model_dump())


@router.patch("/comms-waves/{entry_id}")
def patch_wave(entry_id: str, body: CommsWavePatch,
               conn: sqlite3.Connection = Depends(get_conn)):
    return adoption_comms.patch_wave(conn, entry_id, body.model_dump(), body.model_fields_set)


@router.post("/comms-waves/{entry_id}/sent")
def mark_sent(entry_id: str, body: CommsWaveSent,
              conn: sqlite3.Connection = Depends(get_conn)):
    return adoption_comms.mark_sent(conn, entry_id, body.sent_at)


@router.post("/comms-waves/{entry_id}/cancel")
def cancel_wave(entry_id: str, conn: sqlite3.Connection = Depends(get_conn)):
    return adoption_comms.cancel_wave(conn, entry_id)


@router.post("/comms-sessions", status_code=201)
def create_session(body: CommsSessionCreate, conn: sqlite3.Connection = Depends(get_conn)):
    return adoption_comms.create_session(conn, body.model_dump())


@router.put("/calendar-events/{event_id}/attendees")
def record_attendee(event_id: str, body: AttendeeRecord,
                    conn: sqlite3.Connection = Depends(get_conn)):
    return adoption_comms.record_attendee(conn, event_id, body.model_dump())


@router.get("/calendar-events/{event_id}/attendance")
def attendance(event_id: str, conn: sqlite3.Connection = Depends(get_conn)):
    return adoption_comms.attendance(conn, event_id)
