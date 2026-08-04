import sqlite3

from fastapi import APIRouter, Depends, HTTPException

from .. import audit, repo
from ..db import new_id, now_utc
from ..deps import get_conn
from ..schemas import InteractionCreate

router = APIRouter(prefix="/api", tags=["interactions"])


@router.post("/interactions", status_code=201)
def create_interaction(body: InteractionCreate, conn: sqlite3.Connection = Depends(get_conn)):
    """The 30-second capture path: interaction + participants + inbox notes in one atomic write."""
    repo.get_row(conn, "accounts", body.account_id)  # 404 if account missing
    if body.program_id:
        prog = repo.get_row(conn, "programs", body.program_id)
        if prog["account_id"] != body.account_id:
            raise HTTPException(422, "program_id does not belong to account_id")

    ts = now_utc()
    occurred_on = body.occurred_on or ts[:10]
    interaction = {
        "id": new_id(),
        "account_id": body.account_id,
        "program_id": body.program_id,
        "occurred_on": occurred_on,
        "occurred_at_time": body.occurred_at_time,
        "type": body.type,
        "summary": body.summary,
        "raw_notes": body.raw_notes,
        "source_reference_id": body.source_reference_id,
        "follow_up": body.follow_up,
        "meaningful_touch": 1 if body.meaningful_touch else 0,
        "created_at": ts,
        "updated_at": ts,
    }
    with conn:
        cols = ", ".join(interaction.keys())
        conn.execute(
            f"INSERT INTO interactions ({cols}) VALUES ({', '.join('?' for _ in interaction)})",
            tuple(interaction.values()),
        )
        audit.record(conn, object_type="interaction", object_id=interaction["id"],
                     action="create", after=interaction)

        for pid in dict.fromkeys(body.participant_ids):  # dedupe, preserve order
            # A participant must belong to this account (or be a Valence colleague). Accepting a
            # foreign person put another account's label into this account's activity, and made
            # the account un-exportable — its bundle referenced a person it does not contain.
            participant = conn.execute(
                "SELECT 1 FROM persons WHERE id=? AND archived=0 "
                "AND (affiliation='valence' OR account_id=?)",
                (pid, interaction["account_id"]),
            ).fetchone()
            if not participant:
                raise HTTPException(422, "participant belongs to a different account")
            conn.execute(
                "INSERT OR IGNORE INTO interaction_participants (interaction_id, person_id) VALUES (?,?)",
                (interaction["id"], pid),
            )

        for note in body.inbox_notes:
            note = note.strip()
            if not note:
                continue
            item = {
                "id": new_id(), "interaction_id": interaction["id"], "raw_text": note,
                "status": "untriaged", "created_at": ts, "updated_at": ts,
            }
            conn.execute(
                f"INSERT INTO capture_inbox_items ({', '.join(item.keys())}) "
                f"VALUES ({', '.join('?' for _ in item)})",
                tuple(item.values()),
            )
            audit.record(conn, object_type="capture_inbox_item", object_id=item["id"],
                         action="create", after=item)

    return get_interaction(interaction["id"], conn)


@router.get("/interactions/{interaction_id}")
def get_interaction(interaction_id: str, conn: sqlite3.Connection = Depends(get_conn)):
    interaction = repo.get_row(conn, "interactions", interaction_id)
    rows = conn.execute(
        "SELECT p.* FROM interaction_participants ip "
        "JOIN persons p ON p.id = ip.person_id WHERE ip.interaction_id = ?",
        (interaction_id,),
    ).fetchall()
    interaction["participants"] = [repo.row_to_dict(r) for r in rows]
    interaction["inbox_items"] = repo.list_rows(
        conn, "capture_inbox_items", where="interaction_id = ?", params=(interaction_id,)
    )
    return interaction
