"""Stage 13 adoption communications.

Sequences are plans over existing ``comms_entries``. This module has deliberately no adapter
import and no background job: recording a send or attendance fact always requires an explicit
operator API action.
"""
from __future__ import annotations

import sqlite3
from datetime import date, datetime, timedelta, timezone

from fastapi import HTTPException

from . import audit, expansion, repo
from .db import now_utc


def _date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        return None


def _account_for_program(conn: sqlite3.Connection, program_id: str) -> str:
    return repo.get_row(conn, "programs", program_id)["account_id"]


def _active_sequence(conn: sqlite3.Connection, sequence_id: str) -> dict:
    sequence_row = repo.get_row(conn, "comms_sequences", sequence_id)
    if sequence_row.get("cancelled_at"):
        raise HTTPException(409, "comms sequence is cancelled")
    return sequence_row


def _touch_sequence(conn: sqlite3.Connection, sequence_id: str) -> None:
    with conn:
        conn.execute("UPDATE comms_sequences SET updated_at=? WHERE id=?", (now_utc(), sequence_id))


def create_sequence(conn: sqlite3.Connection, values: dict) -> dict:
    _account_for_program(conn, values["program_id"])
    if values.get("moment_id"):
        moment = repo.get_row(conn, "deployment_moments", values["moment_id"])
        if moment["program_id"] != values["program_id"]:
            raise HTTPException(422, "comms sequence moment belongs to a different program")
    return repo.insert(conn, "comms_sequences", values, object_type="comms_sequence")


def cancel_sequence(conn: sqlite3.Connection, sequence_id: str, reason: str) -> dict:
    before = repo.get_row(conn, "comms_sequences", sequence_id)
    if before.get("cancelled_at"):
        raise HTTPException(409, "comms sequence is already cancelled")
    ts = now_utc()
    with conn:
        conn.execute(
            "UPDATE comms_sequences SET cancelled_at=?,cancellation_reason=?,updated_at=? WHERE id=?",
            (ts, reason, ts, sequence_id),
        )
        after = repo.get_row(conn, "comms_sequences", sequence_id)
        audit.record(conn, object_type="comms_sequence", object_id=sequence_id,
                     action="close", before=before, after=after)
    return sequence(conn, sequence_id)


def _validate_population(conn: sqlite3.Connection, program_id: str,
                         segment_id: str | None, view_id: str | None) -> None:
    if segment_id and view_id:
        raise HTTPException(422, "a comms wave may name a segment or a view, not both")
    account_id = _account_for_program(conn, program_id)
    if segment_id and repo.get_row(conn, "population_segments", segment_id)["account_id"] != account_id:
        raise HTTPException(422, "comms wave population belongs to a different account")
    if view_id and repo.get_row(conn, "population_views", view_id)["account_id"] != account_id:
        raise HTTPException(422, "comms wave population belongs to a different account")


def create_wave(conn: sqlite3.Connection, sequence_id: str, values: dict) -> dict:
    seq = repo.get_row(conn, "comms_sequences", sequence_id)
    if seq.get("cancelled_at"):
        raise HTTPException(409, "cannot add a wave to a cancelled sequence")
    _validate_population(conn, seq["program_id"], values.get("segment_id"), values.get("view_id"))
    predecessor = values.get("follows_entry_id")
    if predecessor:
        previous = repo.get_row(conn, "comms_entries", predecessor)
        if previous.get("sequence_id") != sequence_id:
            raise HTTPException(422, "predecessor belongs to a different sequence")
    payload = {**values, "program_id": seq["program_id"], "sequence_id": sequence_id,
               "status": "planned", "sent_at": None}
    wave = repo.insert(conn, "comms_entries", payload, object_type="comms_entry")
    _touch_sequence(conn, sequence_id)
    return wave


_WAVE_MUTABLE = {
    "moment_id", "audience", "message", "sender", "channel", "send_date", "wave_number",
    "follows_entry_id", "offset_days", "segment_id", "view_id",
}


def patch_wave(conn: sqlite3.Connection, entry_id: str, values: dict,
               supplied: set[str] | None = None) -> dict:
    wave = repo.get_row(conn, "comms_entries", entry_id)
    if not wave.get("sequence_id"):
        raise HTTPException(422, "standalone comms entries are not sequence waves")
    if wave["status"] != "planned":
        raise HTTPException(409, "only planned waves may be edited")
    _active_sequence(conn, wave["sequence_id"])
    changes = {k: v for k, v in values.items() if k in _WAVE_MUTABLE and
               (v is not None or supplied is not None and k in supplied)}
    _validate_population(conn, wave["program_id"],
                         changes.get("segment_id", wave.get("segment_id")),
                         changes.get("view_id", wave.get("view_id")))
    if changes.get("follows_entry_id"):
        previous = repo.get_row(conn, "comms_entries", changes["follows_entry_id"])
        if previous.get("sequence_id") != wave["sequence_id"]:
            raise HTTPException(422, "predecessor belongs to a different sequence")
    patched = repo.patch(conn, "comms_entries", entry_id, changes, object_type="comms_entry",
                         allow_null={k for k in _WAVE_MUTABLE if supplied and k in supplied})
    _touch_sequence(conn, wave["sequence_id"])
    return patched


def mark_sent(conn: sqlite3.Connection, entry_id: str, sent_at: str | None = None) -> dict:
    before = repo.get_row(conn, "comms_entries", entry_id)
    if not before.get("sequence_id"):
        raise HTTPException(422, "standalone comms entries use the legacy workflow")
    if before["status"] != "planned":
        raise HTTPException(409, f"wave is already {before['status']}")
    _active_sequence(conn, before["sequence_id"])
    actual = sent_at or now_utc()
    try:
        parsed = datetime.fromisoformat(actual.replace("Z", "+00:00"))
    except ValueError as exc:
        raise HTTPException(422, "sent_at must be an ISO-8601 timestamp") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    if parsed.astimezone(timezone.utc) > datetime.now(timezone.utc) + timedelta(minutes=1):
        raise HTTPException(422, "sent_at cannot be in the future")
    actual = parsed.astimezone(timezone.utc).replace(microsecond=0).isoformat()
    ts = now_utc()
    with conn:
        conn.execute("UPDATE comms_entries SET status='sent',sent_at=?,updated_at=? WHERE id=?",
                     (actual, ts, entry_id))
        conn.execute("UPDATE comms_sequences SET updated_at=? WHERE id=?",
                     (ts, before["sequence_id"]))
        after = repo.get_row(conn, "comms_entries", entry_id)
        audit.record(conn, object_type="comms_entry", object_id=entry_id,
                     action="update", before=before, after=after)
    return after


def cancel_wave(conn: sqlite3.Connection, entry_id: str) -> dict:
    before = repo.get_row(conn, "comms_entries", entry_id)
    if not before.get("sequence_id"):
        raise HTTPException(422, "standalone comms entries use the legacy workflow")
    if before["status"] != "planned":
        raise HTTPException(409, f"wave is already {before['status']}")
    _active_sequence(conn, before["sequence_id"])
    ts = now_utc()
    with conn:
        conn.execute("UPDATE comms_entries SET status='cancelled',updated_at=? WHERE id=?",
                     (ts, entry_id))
        conn.execute("UPDATE comms_sequences SET updated_at=? WHERE id=?",
                     (ts, before["sequence_id"]))
        after = repo.get_row(conn, "comms_entries", entry_id)
        audit.record(conn, object_type="comms_entry", object_id=entry_id,
                     action="close", before=before, after=after)
    return after


def _expected_dates(waves: list[dict]) -> dict[str, tuple[str | None, bool]]:
    by_id = {w["id"]: w for w in waves}
    cache: dict[str, tuple[str | None, bool]] = {}

    def resolve(wave: dict, seen: set[str]) -> tuple[str | None, bool]:
        if wave["id"] in cache:
            return cache[wave["id"]]
        if wave["id"] in seen:  # defensive; the database trigger should make this impossible
            return None, True
        if not wave.get("follows_entry_id"):
            result = ((wave.get("sent_at") or "")[:10] or wave.get("send_date"), False)
        else:
            previous = by_id.get(wave["follows_entry_id"])
            if not previous:
                result = (None, True)
            else:
                base = _date(previous.get("sent_at"))
                provisional = base is None
                if base is None:
                    previous_date, inherited = resolve(previous, seen | {wave["id"]})
                    base = _date(previous_date)
                    provisional = provisional or inherited
                result = ((base + timedelta(days=wave.get("offset_days") or 0)).isoformat()
                          if base else None, provisional)
        cache[wave["id"]] = result
        return result

    for wave in waves:
        resolve(wave, set())
    return cache


def _sequence_status(seq: dict, waves: list[dict]) -> str:
    if seq.get("cancelled_at"):
        return "cancelled"
    live = [w for w in waves if not w.get("archived")]
    if live and all(w["status"] in ("sent", "cancelled") for w in live):
        return "complete"
    if any(w["status"] == "sent" for w in live):
        return "running"
    return "planned"


def attendance(conn: sqlite3.Connection, event_id: str) -> dict:
    event = repo.get_row(conn, "calendar_events", event_id)
    base = {"event_id": event_id, "state": "unknown", "invited": None, "attended": None,
            "no_show": None, "unknown": None, "rate": None, "suppression_reason": None,
            "reason": None}
    if _date(event["starts_at"]) and _date(event["starts_at"]) > date.fromisoformat(now_utc()[:10]):
        return {**base, "reason": "session has not happened yet"}
    if not event.get("invited_by_entry_id"):
        return {**base, "reason": "no invitation wave is linked"}
    wave = repo.get_row(conn, "comms_entries", event["invited_by_entry_id"])
    segment_id, view_id = wave.get("segment_id"), wave.get("view_id")
    if not segment_id and not view_id:
        return {**base, "reason": "invitation wave has no modeled cohort"}
    table = "population_segments" if segment_id else "population_views"
    size_column = "headcount" if segment_id else "estimated_headcount"
    population = repo.get_row(conn, table, segment_id or view_id)
    floor = expansion.min_cohort_size(conn, population["account_id"])
    size = population.get(size_column)
    if size is None:
        reason = "cohort size is unknown; privacy floor cannot be proven"
        return {**base, "state": "suppressed", "suppression_reason": reason, "reason": reason}
    if size < floor:
        reason = f"cohort size {size} is below the account minimum of {floor}"
        return {**base, "state": "suppressed", "suppression_reason": reason, "reason": reason}
    rows = [dict(r) for r in conn.execute(
        "SELECT attendance_scope,attendance_status FROM calendar_event_attendees WHERE event_id=?",
        (event_id,)).fetchall()]
    if any(r["attendance_scope"] == "unknown" for r in rows):
        return {**base, "state": "incomplete",
                "reason": "one or more attendees are not classified as audience, facilitator, or observer"}
    audience = [r for r in rows if r["attendance_scope"] == "audience"]
    if not audience:
        return {**base, "reason": "no audience attendees are recorded"}
    if len(audience) < floor:
        reason = f"invited audience {len(audience)} is below the account minimum of {floor}"
        return {**base, "state": "suppressed", "suppression_reason": reason, "reason": reason}
    attended = sum(r["attendance_status"] == "attended" for r in audience)
    no_show = sum(r["attendance_status"] == "no_show" for r in audience)
    unknown = len(audience) - attended - no_show
    if attended + no_show == 0:
        return {**base, "reason": "attendance outcomes have not been recorded"}
    # §5.3: an unrecorded outcome is missing data, not a no-show. Dividing by the full invited
    # count would render "we never asked" as "they did not come" — the exact reading the section
    # forbids. The rate is therefore over RESOLVED outcomes, and the unresolved count travels with
    # it so the denominator is legible, matching how Stage 10 calibration reports closed/unresolved
    # rather than folding the gap into the numerator's denominator.
    resolved = attended + no_show
    return {**base, "state": "known", "invited": len(audience), "attended": attended,
            "no_show": no_show, "unknown": unknown, "rate": attended / resolved,
            "rate_basis": f"{attended} of {resolved} recorded outcomes",
            "outcomes_unrecorded": unknown}


def sequence(conn: sqlite3.Connection, sequence_id: str) -> dict:
    seq = repo.get_row(conn, "comms_sequences", sequence_id)
    waves = repo.list_rows(conn, "comms_entries",
                           where="sequence_id=? ORDER BY wave_number,created_at", params=(sequence_id,))
    expected = _expected_dates(waves)
    segments = {r["id"]: r["name"] for r in repo.list_rows(conn, "population_segments", where="1=1")}
    views = {r["id"]: r["name"] for r in repo.list_rows(conn, "population_views", where="1=1")}
    for wave in waves:
        wave["expected_send_on"], wave["date_provisional"] = expected[wave["id"]]
        wave["population"] = segments.get(wave.get("segment_id")) or views.get(wave.get("view_id"))
    sessions = repo.list_rows(conn, "calendar_events",
                              where="comms_sequence_id=? ORDER BY starts_at", params=(sequence_id,))
    for event in sessions:
        event["attendees"] = [dict(r) for r in conn.execute(
            "SELECT * FROM calendar_event_attendees WHERE event_id=? ORDER BY attendance_scope,name,email",
            (event["id"],)).fetchall()]
        event["attendance"] = attendance(conn, event["id"])
    account_id = _account_for_program(conn, seq["program_id"])
    return {**seq, "account_id": account_id, "status": _sequence_status(seq, waves),
            "waves": waves, "sessions": sessions}


def list_for_account(conn: sqlite3.Connection, account_id: str) -> list[dict]:
    repo.get_row(conn, "accounts", account_id)
    ids = [r["id"] for r in conn.execute(
        "SELECT s.id FROM comms_sequences s JOIN programs p ON p.id=s.program_id "
        "WHERE p.account_id=? AND s.archived=0 ORDER BY s.created_at DESC", (account_id,)).fetchall()]
    return [sequence(conn, sequence_id) for sequence_id in ids]


def create_session(conn: sqlite3.Connection, values: dict) -> dict:
    seq = _active_sequence(conn, values["comms_sequence_id"])
    account_id = _account_for_program(conn, seq["program_id"])
    invitation = values.get("invited_by_entry_id")
    if invitation:
        wave = repo.get_row(conn, "comms_entries", invitation)
        if wave.get("sequence_id") != seq["id"]:
            raise HTTPException(422, "session invitation wave belongs to a different sequence")
    payload = {**values, "account_id": account_id, "program_id": seq["program_id"],
               "direction": "written"}
    event = repo.insert(conn, "calendar_events", payload, object_type="calendar_event")
    _touch_sequence(conn, seq["id"])
    return event


def record_attendee(conn: sqlite3.Connection, event_id: str, values: dict) -> dict:
    event = repo.get_row(conn, "calendar_events", event_id)
    if event["purpose"] not in ("webinar", "office_hours"):
        raise HTTPException(422, "cohort attendance is only recorded for webinar or office hours")
    if values.get("person_id"):
        person = repo.get_row(conn, "persons", values["person_id"])
        if person.get("affiliation") != "valence" and person.get("account_id") != event["account_id"]:
            raise HTTPException(422, "calendar attendee belongs to a different account")
    email = (values.get("email") or "").strip().lower()
    if not email:
        raise HTTPException(422, "attendee email is required")
    row = {**values, "email": email, "event_id": event_id, "created_at": now_utc()}
    before = conn.execute("SELECT * FROM calendar_event_attendees WHERE event_id=? AND email=?",
                          (event_id, email)).fetchone()
    with conn:
        conn.execute(
            "INSERT INTO calendar_event_attendees "
            "(event_id,person_id,name,email,response_status,attendance_status,created_at,attendance_scope) "
            "VALUES (:event_id,:person_id,:name,:email,:response_status,:attendance_status,:created_at,:attendance_scope) "
            "ON CONFLICT(event_id,email) DO UPDATE SET person_id=excluded.person_id,name=excluded.name,"
            "response_status=excluded.response_status,attendance_status=excluded.attendance_status,"
            "attendance_scope=excluded.attendance_scope", row)
        after = dict(conn.execute("SELECT * FROM calendar_event_attendees WHERE event_id=? AND email=?",
                                  (event_id, email)).fetchone())
        audit.record(conn, object_type="calendar_event_attendee",
                     object_id=f"{event_id}:{email}", action="update" if before else "create",
                     before=dict(before) if before else None, after=after)
    return after


def attention_items(conn: sqlite3.Connection, today: str | None = None) -> list[dict]:
    today = today or now_utc()[:10]
    out = []
    for row in conn.execute("SELECT id FROM comms_sequences WHERE archived=0 AND cancelled_at IS NULL"):
        seq = sequence(conn, row["id"])
        late = [w for w in seq["waves"] if w["status"] == "planned" and
                w.get("expected_send_on") and w["expected_send_on"] < today]
        if not late:
            continue
        first = min(late, key=lambda w: w["expected_send_on"])
        out.append({"sequence_id": seq["id"], "account_id": seq["account_id"],
                    "program_id": seq["program_id"], "title": seq["name"],
                    "due_on": first["expected_send_on"], "updated_at": seq["updated_at"],
                    "because": f"{len(late)} planned wave{'s are' if len(late) != 1 else ' is'} overdue; "
                               f"the earliest was expected {first['expected_send_on']}.",
                    "next_action": "Record the send, revise the plan, or cancel the wave. Nothing is auto-sent."})
    return out
