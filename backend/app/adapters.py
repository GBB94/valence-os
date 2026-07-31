"""External-source adapters — MOCK implementations only (Comprehensive Spec Part 4 / Part 6).

Every external touchpoint is an adapter with a mock now and a config swap later. Nothing here
reaches a real inbox, recording store, or transcription service; the mock reads fixture files
under app/fixtures/. Flipping any of these to a real source is a CONNECTIONS.md gate.
"""
from __future__ import annotations

import email
from email.utils import parseaddr, getaddresses, parsedate_to_datetime
from pathlib import Path

FIXTURES = Path(__file__).resolve().parent / "fixtures"
EMAIL_DIR = FIXTURES / "emails"
TRANSCRIPT_DIR = FIXTURES / "transcripts"


# --- Transcription adapter ---------------------------------------------------

def transcribe(reference: str) -> str:
    """MOCK: return a fixture transcript by name. A real engine (Whisper, a vendor API) is a
    CONNECTIONS.md switch. `reference` is a fixture filename or an inline transcript."""
    if reference and reference.endswith(".txt"):
        path = TRANSCRIPT_DIR / Path(reference).name
        if path.exists():
            return path.read_text(encoding="utf-8")
    # treat the reference itself as an inline transcript (upload path)
    return reference or ""


def list_transcript_fixtures() -> list[str]:
    return sorted(p.name for p in TRANSCRIPT_DIR.glob("*.txt")) if TRANSCRIPT_DIR.exists() else []


# --- Email adapter -----------------------------------------------------------

def _body(msg) -> str:
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() == "text/plain":
                return part.get_payload(decode=True).decode(errors="replace")
        return ""
    payload = msg.get_payload(decode=True)
    return payload.decode(errors="replace") if payload else (msg.get_payload() or "")


def _parse_eml(path: Path) -> dict:
    msg = email.message_from_string(path.read_text(encoding="utf-8"))
    from_name, from_addr = parseaddr(msg.get("From", ""))
    tos = [addr for _n, addr in getaddresses([msg.get("To", "")]) if addr]
    try:
        dt = parsedate_to_datetime(msg.get("Date", ""))
        date_iso = dt.isoformat() if dt else None
    except (TypeError, ValueError):
        date_iso = None
    return {
        "external_id": (msg.get("Message-ID") or path.name).strip("<>"),
        "from_name": from_name, "from_addr": from_addr.lower(),
        "to_addrs": [a.lower() for a in tos],
        "subject": msg.get("Subject", ""),
        "date_iso": date_iso,
        "body": _body(msg).strip(),
        "fixture": path.name,
    }


def fetch_emails() -> list[dict]:
    """MOCK inbox: parse every .eml fixture. A real provider (Graph/Gmail/IMAP) is a switch."""
    if not EMAIL_DIR.exists():
        return []
    return [_parse_eml(p) for p in sorted(EMAIL_DIR.glob("*.eml"))]
