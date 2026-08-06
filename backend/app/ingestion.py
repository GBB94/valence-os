"""Communications ingestion (Comprehensive Spec §§4.1-4.4), all through the job table.

Recordings/transcripts -> transcribe (mock) -> associate -> draft Interaction -> extraction.
Emails (.eml fixtures) -> associate -> lightweight comm record + priority flag. Low-confidence
associations are surfaced (recording -> capture inbox; email -> low confidence shown), never
guessed silently. Mock sources only; real providers are a CONNECTIONS.md switch.
"""
from __future__ import annotations

import re
import sqlite3
from typing import NamedTuple

from . import adapters, association, email_thread, jobs, proposals as proposals_mod, repo
from .db import new_id, now_utc


class DropOrigin(NamedTuple):
    """Where a message came from when it did **not** come from the mock inbox.

    ACCOUNT-INTAKE-SPEC.md §7.4: a dropped `.eml` must produce the same records a synced one does,
    or the same message means different things depending on how it arrived — missing from the
    account's comms timeline, and silently absent from the reciprocity and response-time counts
    that are supposed to describe all of our correspondence. So the drop supplies this instead of a
    fixture file and calls `ingest_email_message` unchanged.

    Only five things differ, and each is a fact about origin rather than about the message:

      * `account_id` / `program_id` — §8. The account is the page the operator dropped on, not a
        guess from the sender, so association is not consulted for it and there is no confidence
        gate on scope. Association still runs, because resolving *who sent this* is a separate
        question and a useful one.
      * `provider` — §6.6. Two providers can hand back the same Message-ID and mean different
        material, so a run drafted from a dropped file must not claim `mock-inbox` provenance.
      * `source_label` — the source reference's name. Its `url` is deliberately NULL: the bytes
        were never persisted (§5), so there is no location to point at and claiming one would be
        a provenance claim about a file that does not exist here.
      * `extractor_backend` — the sync path is always `mock`; a drop honours the request's backend.
      * `coverage` — §14. What the drop did not read, stored on the run's own `coverage_json`.
    """
    account_id: str
    program_id: str | None
    provider: str
    source_label: str
    extractor_backend: str | None = None
    coverage: dict | None = None

# §4.3 priority-flagging cues.
_KEYWORDS = re.compile(
    r"\b(renewal|procurement|purchase order|\bpo\b|contract|sign[- ]?off|signature|deadline|"
    r"by (mon|tue|wed|thu|fri|next|end of)|approve|budget)\b", re.I)
_SENIOR = ("champion", "budget_owner", "program_owner", "executive_sponsor", "financial_gatekeeper")


def _summarize(body: str) -> str:
    first = next((s.strip() for s in re.split(r"(?<=[.!?])\s+|\n+", body) if len(s.strip()) > 8), body[:120])
    return (first[:157] + "…") if len(first) > 158 else first


def _is_senior(conn, person_id) -> bool:
    if not person_id:
        return False
    n = conn.execute(
        "SELECT COUNT(*) c FROM stakeholder_roles WHERE person_id=? AND archived=0 AND role IN (%s)"
        % ",".join("?" * len(_SENIOR)), (person_id, *_SENIOR)).fetchone()["c"]
    return n > 0


def _flag_email(conn, *, person_id, from_name, subject, body) -> tuple[bool, str | None]:
    text = f"{subject}\n{body}"
    question = "?" in text
    keyword = bool(_KEYWORDS.search(text))
    senior = _is_senior(conn, person_id)
    who = from_name or "sender"
    if senior and question:
        return True, f"{who} (senior stakeholder) asked a direct question"
    if question and person_id:
        return True, f"{who} asked a direct question"
    if keyword:
        m = _KEYWORDS.search(text)
        return True, f"{who} — {m.group(0).lower()} language, may need a response"
    return False, None


def _thread_duplicate(conn, thread_id: str | None, new_hash: str | None) -> bool:
    """Has this exact new text already arrived in this thread? (§14.8 quoted-text dedupe.)

    Checked in code as well as enforced by 0045's unique index, because a duplicate inside a thread
    is an ordinary, expected event — somebody replies-all to their own message — and an
    `IntegrityError` at the bottom of a sync loop is not how an expected event should read.
    """
    if not thread_id or not new_hash:
        return False
    return bool(conn.execute(
        "SELECT 1 FROM comm_messages WHERE thread_id=? AND new_text_hash=?",
        (thread_id, new_hash)).fetchone())


def _extract_from_email(conn, row: dict, new_text: str, msg: dict, src_id: str,
                        origin: DropOrigin | None = None) -> str | None:
    """Draft proposals from one email's **new text**, or return None with a reason recorded.

    Two gates stand in front of this, and both are §14.8 rules rather than caution:

      * A low-confidence association cannot change account state. It also cannot *propose* against
        an account, because a proposal names an account the moment it is written and a wrong one
        would put another client's material in this account's review queue. The message stays a
        comm record awaiting `confirm_association`.
      * Nothing extracts from quoted history. `new_text` is what this sender added; a bare forward
        adds nothing and produces no run at all rather than an empty one.
    """
    from .routers import ai            # shared, security-reviewed persistence — never a second path
    if not row.get("account_id") or (row.get("confidence") or 0) < association.LOW_CONFIDENCE:
        return None
    if not new_text.strip():
        return None
    backend = (origin.extractor_backend if origin else None) or "mock"
    ex = __import__("app.extractor", fromlist=["get_extractor"]).get_extractor(backend)
    proposals = ex.extract(new_text)
    if not proposals:
        return None
    # `source_text` is the new text, so the run's content hash — and therefore its §6.6
    # source-version key — covers what this message added and not the thread below it.
    return ai._persist_run(
        conn, account_id=row["account_id"], program_id=row.get("program_id"),
        interaction_id=None, model_version=ex.model_version, prompt_version=ex.prompt_version,
        source_text=new_text, proposals=proposals, extractor_backend=backend,
        source_kind="email", provider=(origin.provider if origin else adapters.email_provider()),
        external_id=msg.get("message_id") or msg.get("external_id"), source_reference_id=src_id,
        coverage=(origin.coverage if origin else None))


def ingest_email_message(conn: sqlite3.Connection, msg: dict,
                         origin: DropOrigin | None = None) -> dict | None:
    """Create one lightweight comm record from a parsed email. Returns the row, or None if a
    dedupe hit. Link-first: the body stays behind a source reference; the summary is the record.

    §14.8: the record keeps message and thread identity, the quoted boundary is computed before
    anything reads the body, and only the new text can reach an extractor.

    `origin` is set when the message was dropped on an account page rather than synced from the
    mock inbox (ACCOUNT-INTAKE-SPEC.md §7.4). It changes where the account comes from and how the
    run is labelled — **not** how the message is parsed, split, threaded, or deduplicated. Those
    are the parts that must not diverge, so they are outside the branch entirely: the two dedupe
    checks below run first and identically, which is what makes dropping a message that already
    synced a no-op rather than a duplicate comm record.
    """
    if msg.get("external_id") and conn.execute(
            "SELECT 1 FROM comm_messages WHERE external_id=?", (msg["external_id"],)).fetchone():
        return None
    body = msg.get("body", "")
    new_text, quoted = email_thread.split_quoted(body)
    thread_id = email_thread.thread_key(
        message_id=msg.get("message_id") or msg.get("external_id"),
        in_reply_to=msg.get("in_reply_to"), references=msg.get("references"))
    new_hash = proposals_mod.content_hash(new_text) if new_text.strip() else None
    if _thread_duplicate(conn, thread_id, new_hash):
        return None

    res = association.resolve(
        conn, emails=[msg["from_addr"], *msg["to_addrs"], *msg.get("cc_addrs", [])],
        keywords=re.findall(r"[a-zA-Z]{4,}", msg.get("subject", "")))
    if origin:
        # §8. The account is the page, not a guess — so it replaces whatever association reached,
        # and the confidence it replaces is 1.0 because a human chose it a second ago. Association
        # still supplied `person_id`, which is a different question and still worth asking.
        # The program is re-picked *inside* the chosen account: leaving it NULL while a synced copy
        # of the same message got one is exactly the divergence §7.4 is about.
        res = dict(res, account_id=origin.account_id, confidence=1.0,
                   program_id=origin.program_id
                   or association.pick_program(conn, origin.account_id, res["matched_person_ids"]))
    src = repo.insert(conn, "source_references", {
        "type": "manual_entry",
        "label": origin.source_label if origin else f"Email: {msg.get('subject') or '(no subject)'}",
        # NULL for a drop, and deliberately: §5 keeps no bytes, so there is no location to point
        # at, and a `fixture://` url would name a file that was never written.
        "url": None if origin else f"fixture://emails/{msg.get('fixture')}",
        "locator": msg.get("external_id"),
    }, object_type="source_reference")
    # Flagging reads the new text, not the body: a keyword buried in quoted history was already
    # seen when its own message arrived, and re-flagging it makes an old question look new.
    needs, reason = _flag_email(conn, person_id=res["person_id"], from_name=msg.get("from_name"),
                                subject=msg.get("subject", ""), body=new_text)
    row = repo.insert(conn, "comm_messages", {
        "account_id": res["account_id"], "program_id": res["program_id"], "direction": "inbound",
        "from_addr": msg["from_addr"], "to_addrs": ",".join(msg["to_addrs"]),
        "cc_addrs": ",".join(msg.get("cc_addrs", [])) or None,
        "occurred_on": (msg.get("date_iso") or now_utc())[:10], "occurred_at": msg.get("date_iso") or now_utc(),
        "subject": msg.get("subject"), "summary": _summarize(new_text or body),
        "person_id": res["person_id"], "confidence": res["confidence"],
        "needs_response": 1 if needs else 0, "flag_reason": reason,
        "source_reference_id": src["id"], "external_id": msg.get("external_id"),
        "message_id": msg.get("message_id") or msg.get("external_id"),
        "thread_id": thread_id, "in_reply_to": msg.get("in_reply_to"),
        "attachments": ",".join(msg.get("attachments", [])) or None,
        "new_text_hash": new_hash, "quoted_chars": len(quoted),
    }, object_type="comm_message")

    run_id = _extract_from_email(conn, row, new_text, msg, src["id"], origin)
    if run_id:
        row = repo.patch(conn, "comm_messages", row["id"], {"extraction_run_id": run_id},
                         object_type="comm_message")
    return row


def extract_after_confirmation(conn: sqlite3.Connection, comm_id: str) -> str | None:
    """§14.8 — run the extractor once a human has agreed the association, and not before.

    This is the second half of the existing `/comms/{id}/associate` correction, not a second
    association path: an email held back by the confidence gate has no proposals, and the operator
    agreeing to the account is exactly the event that unblocks it. Called after the correction has
    already written the account, so the gate in `_extract_from_email` reads the confirmed row.

    Returns the run id, or None when there was nothing to draft — an already-extracted message, a
    message whose fixture is gone, or one whose new text yielded no proposals. None is normal.
    """
    row = repo.get_row(conn, "comm_messages", comm_id)
    if row.get("extraction_run_id") or not row.get("source_reference_id"):
        return None
    src = repo.get_row(conn, "source_references", row["source_reference_id"])
    fixture = (src.get("url") or "").rsplit("/", 1)[-1]
    msg = next((m for m in adapters.fetch_emails() if m.get("fixture") == fixture), None)
    if not msg:
        return None
    new_text, _quoted = email_thread.split_quoted(msg.get("body", ""))
    run_id = _extract_from_email(conn, row, new_text, msg, row["source_reference_id"])
    if run_id:
        repo.patch(conn, "comm_messages", comm_id, {"extraction_run_id": run_id},
                   object_type="comm_message")
    return run_id


def sync_emails(conn: sqlite3.Connection) -> dict:
    """§4.2 — sync the mock inbox. Idempotent via external_id and thread new-text dedupe."""
    created, skipped, flagged, extracted, awaiting = 0, 0, 0, 0, 0
    for msg in adapters.fetch_emails():
        row = ingest_email_message(conn, msg)
        if row is None:
            skipped += 1
            continue
        created += 1
        flagged += 1 if row.get("needs_response") else 0
        if row.get("extraction_run_id"):
            extracted += 1
        elif row.get("account_id") and (row.get("confidence") or 0) < association.LOW_CONFIDENCE:
            awaiting += 1
    return {"created": created, "skipped": skipped, "flagged": flagged,
            "extracted": extracted, "awaiting_association": awaiting}


def ingest_recording(conn: sqlite3.Connection, reference: str,
                     attendees: list[str] | None = None, keywords: list[str] | None = None) -> dict:
    """§4.1 — transcribe (mock), associate, create a draft interaction, run extraction. Low
    confidence drops a capture-inbox note for manual assignment instead of guessing."""
    from .routers import ai  # reuse the shared, security-reviewed extraction persistence
    attendees = attendees or []
    transcript = adapters.transcribe(reference)
    res = association.resolve(conn, names=attendees, keywords=keywords or [])
    if not res["account_id"]:
        return {"status": "unresolved", "confidence": res["confidence"], "reference": reference}

    src = repo.insert(conn, "source_references", {
        "type": "transcript_span", "label": f"Recording: {reference}",
        "url": f"fixture://transcripts/{reference}",
    }, object_type="source_reference")
    interaction = repo.insert(conn, "interactions", {
        "account_id": res["account_id"], "program_id": res["program_id"], "occurred_on": now_utc()[:10],
        "type": "call", "summary": f"Auto-ingested recording ({reference})",
        "source_reference_id": src["id"], "meaningful_touch": 1,
    }, object_type="interaction")
    with conn:
        for pid in res["matched_person_ids"]:
            conn.execute("INSERT OR IGNORE INTO interaction_participants (interaction_id, person_id) VALUES (?,?)",
                         (interaction["id"], pid))

    ex = __import__("app.extractor", fromlist=["get_extractor"]).get_extractor("mock")
    proposals = ex.extract(transcript)
    # This is the one path with a real provider item behind it, so it is the one that can supply
    # the §6.6 source-version identity: the recording adapter, the reference it was asked for, and
    # a hash of what came back. A retranscription of the same reference hashes differently and is
    # therefore new material, which is exactly the case `external_id` alone would have missed.
    run_id = ai._persist_run(conn, account_id=res["account_id"], program_id=res["program_id"],
                             interaction_id=interaction["id"], model_version=ex.model_version,
                             prompt_version=ex.prompt_version, source_text=transcript,
                             proposals=proposals, extractor_backend="mock",
                             source_kind="interaction", provider=adapters.recording_provider(),
                             external_id=reference, source_reference_id=src["id"])

    low = res["confidence"] < association.LOW_CONFIDENCE
    if low:
        repo.insert(conn, "capture_inbox_items", {
            "interaction_id": interaction["id"],
            "raw_text": f"Low-confidence auto-association ({res['confidence']}) — confirm account/program for “{reference}”.",
        }, object_type="capture_inbox_item")

    return {"status": "ingested", "interaction_id": interaction["id"], "extraction_run_id": run_id,
            "account_id": res["account_id"], "program_id": res["program_id"],
            "confidence": res["confidence"], "proposals": len(proposals), "needs_triage": low}


# --- job handlers (run through the in-process worker) -------------------------

@jobs.register("sync_emails")
def _job_sync_emails(conn, payload):
    return sync_emails(conn)


@jobs.register("ingest_recording")
def _job_ingest_recording(conn, payload):
    return ingest_recording(conn, payload.get("reference"),
                            attendees=payload.get("attendees", []), keywords=payload.get("keywords", []))
