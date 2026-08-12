import sqlite3

from fastapi import APIRouter, Depends

from .. import interaction_ops
from ..deps import get_conn
from ..schemas import InteractionCreate

router = APIRouter(prefix="/api", tags=["interactions"])


@router.post("/interactions", status_code=201)
def create_interaction(body: InteractionCreate, conn: sqlite3.Connection = Depends(get_conn)):
    """The 30-second capture path: interaction + participants + inbox notes in one atomic write."""
    return interaction_ops.create(conn, body)


@router.get("/interactions/{interaction_id}")
def get_interaction(interaction_id: str, conn: sqlite3.Connection = Depends(get_conn)):
    return interaction_ops.read(conn, interaction_id)
