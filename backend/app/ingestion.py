"""Communications ingestion (Comprehensive Spec §§4.1-4.4), all through the job table.

Recordings/transcripts -> transcribe (mock) -> associate -> draft Interaction -> extraction.
Emails (.eml fixtures) -> associate -> lightweight comm record + priority flag. Low-confidence
associations are surfaced (recording -> capture inbox; email -> low confidence shown), never
guessed silently. Mock sources only; real providers are a CONNECTIONS.md switch.
"""
from __future__ import annotations

import re
import sqlite3

from . import adapters, association, jobs, repo
from .db import new_id, now_utc

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


def ingest_email_message(conn: sqlite3.Connection, msg: dict) -> dict | None:
    """Create one lightweight comm record from a parsed email. Returns the row, or None if a
    dedupe hit. Link-first: the body stays behind a source reference; the summary is the record."""
    if msg.get("external_id") and conn.execute(
            "SELECT 1 FROM comm_messages WHERE external_id=?", (msg["external_id"],)).fetchone():
        return None
    res = association.resolve(
        conn, emails=[msg["from_addr"], *msg["to_addrs"]],
        keywords=re.findall(r"[a-zA-Z]{4,}", msg.get("subject", "")))
    src = repo.insert(conn, "source_references", {
        "type": "manual_entry", "label": f"Email: {msg.get('subject') or '(no subject)'}",
        "url": f"fixture://emails/{msg.get('fixture')}", "locator": msg.get("external_id"),
    }, object_type="source_reference")
    needs, reason = _flag_email(conn, person_id=res["person_id"], from_name=msg.get("from_name"),
                                subject=msg.get("subject", ""), body=msg.get("body", ""))
    row = repo.insert(conn, "comm_messages", {
        "account_id": res["account_id"], "program_id": res["program_id"], "direction": "inbound",
        "from_addr": msg["from_addr"], "to_addrs": ",".join(msg["to_addrs"]),
        "occurred_on": (msg.get("date_iso") or now_utc())[:10], "occurred_at": msg.get("date_iso") or now_utc(),
        "subject": msg.get("subject"), "summary": _summarize(msg.get("body", "")),
        "person_id": res["person_id"], "confidence": res["confidence"],
        "needs_response": 1 if needs else 0, "flag_reason": reason,
        "source_reference_id": src["id"], "external_id": msg.get("external_id"),
    }, object_type="comm_message")
    return row


def sync_emails(conn: sqlite3.Connection) -> dict:
    """§4.2 — sync the mock inbox. Idempotent via external_id dedupe."""
    created, skipped, flagged = 0, 0, 0
    for msg in adapters.fetch_emails():
        row = ingest_email_message(conn, msg)
        if row is None:
            skipped += 1
        else:
            created += 1
            flagged += 1 if row.get("needs_response") else 0
    return {"created": created, "skipped": skipped, "flagged": flagged}


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
    run_id = ai._persist_run(conn, account_id=res["account_id"], program_id=res["program_id"],
                             interaction_id=interaction["id"], model_version=ex.model_version,
                             prompt_version=ex.prompt_version, transcript_chars=len(transcript),
                             proposals=proposals)

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
