"""The single native Interaction creation path.

Quick capture and Call Coach both create the same account record. Keeping the transaction here
prevents the coaching bridge from becoming a second, subtly weaker Interaction writer.
"""
from __future__ import annotations

import sqlite3

from fastapi import HTTPException

from . import audit, repo
from .db import new_id, now_utc
from .schemas import InteractionCreate


def create(conn: sqlite3.Connection, body: InteractionCreate) -> dict:
    """Create one Interaction, its participants, and capture notes atomically."""
    repo.get_row(conn, "accounts", body.account_id)
    if body.program_id:
        program = repo.get_row(conn, "programs", body.program_id)
        if program["account_id"] != body.account_id:
            raise HTTPException(422, "program_id does not belong to account_id")

    ts = now_utc()
    interaction = {
        "id": new_id(),
        "account_id": body.account_id,
        "program_id": body.program_id,
        "occurred_on": body.occurred_on or ts[:10],
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
        columns = ", ".join(interaction)
        conn.execute(
            f"INSERT INTO interactions ({columns}) VALUES ({', '.join('?' for _ in interaction)})",
            tuple(interaction.values()),
        )
        audit.record(conn, object_type="interaction", object_id=interaction["id"],
                     action="create", after=interaction)

        for person_id in dict.fromkeys(body.participant_ids):
            participant = conn.execute(
                "SELECT 1 FROM persons WHERE id=? AND archived=0 "
                "AND (affiliation='valence' OR account_id=?)",
                (person_id, body.account_id),
            ).fetchone()
            if not participant:
                raise HTTPException(422, "participant belongs to a different account")
            conn.execute(
                "INSERT OR IGNORE INTO interaction_participants (interaction_id, person_id) "
                "VALUES (?,?)", (interaction["id"], person_id),
            )

        for raw_note in body.inbox_notes:
            note = raw_note.strip()
            if not note:
                continue
            item = {
                "id": new_id(), "interaction_id": interaction["id"], "raw_text": note,
                "status": "untriaged", "created_at": ts, "updated_at": ts,
            }
            conn.execute(
                f"INSERT INTO capture_inbox_items ({', '.join(item)}) "
                f"VALUES ({', '.join('?' for _ in item)})", tuple(item.values()),
            )
            audit.record(conn, object_type="capture_inbox_item", object_id=item["id"],
                         action="create", after=item)
    return read(conn, interaction["id"])


def read(conn: sqlite3.Connection, interaction_id: str) -> dict:
    interaction = repo.get_row(conn, "interactions", interaction_id)
    people = conn.execute(
        "SELECT p.* FROM interaction_participants ip JOIN persons p ON p.id=ip.person_id "
        "WHERE ip.interaction_id=?", (interaction_id,),
    ).fetchall()
    interaction["participants"] = [repo.row_to_dict(row) for row in people]
    interaction["inbox_items"] = repo.list_rows(
        conn, "capture_inbox_items", where="interaction_id = ?", params=(interaction_id,))
    return interaction
