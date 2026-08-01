"""External-source adapters — MOCK implementations only (Comprehensive Spec Part 4 / Part 6).

Every external touchpoint is an adapter with a mock now and a config swap later. Nothing here
reaches a real inbox, recording store, or transcription service; the mock reads fixture files
under app/fixtures/. Flipping any of these to a real source is a CONNECTIONS.md gate.
"""
from __future__ import annotations

import email
import csv
import json
import re
from email.utils import parseaddr, getaddresses, parsedate_to_datetime
from pathlib import Path

FIXTURES = Path(__file__).resolve().parent / "fixtures"
EMAIL_DIR = FIXTURES / "emails"
TRANSCRIPT_DIR = FIXTURES / "transcripts"
CALENDAR_DIR = FIXTURES / "calendar"
ORG_CHANGE_DIR = FIXTURES / "org_changes"
HEADCOUNT_DIR = FIXTURES / "headcount"


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


# --- Calendar adapter --------------------------------------------------------

def _unfold_ics(text: str) -> list[str]:
    """RFC 5545 line unfolding for the deliberately small mock fixture parser."""
    lines: list[str] = []
    for raw in text.replace("\r\n", "\n").split("\n"):
        if raw.startswith((" ", "\t")) and lines:
            lines[-1] += raw[1:]
        else:
            lines.append(raw)
    return lines


def _ics_dt(value: str | None) -> str | None:
    if not value:
        return None
    value = value.strip()
    # Normalize the fixture's UTC/basic format into the same ISO strings used elsewhere.
    m = re.fullmatch(r"(\d{4})(\d{2})(\d{2})T(\d{2})(\d{2})(\d{2})Z", value)
    if m:
        y, mo, d, h, mi, s = m.groups()
        return f"{y}-{mo}-{d}T{h}:{mi}:{s}+00:00"
    m = re.fullmatch(r"(\d{4})(\d{2})(\d{2})", value)
    if m:
        y, mo, d = m.groups()
        return f"{y}-{mo}-{d}"
    return value


def _parse_ics(path: Path) -> list[dict]:
    events, current = [], None
    for line in _unfold_ics(path.read_text(encoding="utf-8")):
        if line == "BEGIN:VEVENT":
            current = {"attendees": [], "fixture": path.name}
            continue
        if line == "END:VEVENT":
            if current:
                events.append(current)
            current = None
            continue
        if current is None or ":" not in line:
            continue
        lhs, value = line.split(":", 1)
        key, *params = lhs.split(";")
        key = key.upper()
        if key == "ATTENDEE":
            meta = {}
            for param in params:
                if "=" in param:
                    k, v = param.split("=", 1); meta[k.upper()] = v.strip('"')
            current["attendees"].append({
                "email": value.removeprefix("mailto:").lower(),
                "name": meta.get("CN"),
                "response_status": meta.get("PARTSTAT", "UNKNOWN").lower().replace("needs-action", "needs_action"),
                "attendance_status": meta.get("X-VALENCE-ATTENDANCE", "UNKNOWN").lower(),
            })
        else:
            mapping = {
                "UID": "external_id", "SUMMARY": "title", "DTSTART": "starts_at",
                "DTEND": "ends_at", "LOCATION": "location", "ORGANIZER": "organizer_email",
                "X-VALENCE-ACCOUNT-ID": "account_id", "X-VALENCE-PROGRAM-ID": "program_id",
                "X-VALENCE-CELL-ID": "cell_id", "X-VALENCE-PURPOSE": "purpose",
            }
            if key in mapping:
                current[mapping[key]] = _ics_dt(value) if key in ("DTSTART", "DTEND") else value.removeprefix("mailto:")
    return events


def fetch_calendar_events() -> list[dict]:
    """MOCK calendar: read .ics fixtures. No network, token, or real mailbox is touched."""
    if not CALENDAR_DIR.exists():
        return []
    return [event for path in sorted(CALENDAR_DIR.glob("*.ics")) for event in _parse_ics(path)]


def list_calendar_fixtures() -> list[str]:
    return sorted(p.name for p in CALENDAR_DIR.glob("*.ics")) if CALENDAR_DIR.exists() else []


# --- Enrichment/org-change adapter ------------------------------------------

def fetch_org_changes() -> list[dict]:
    """MOCK enrichment source. Rows are proposals; the domain service requires confirmation."""
    if not ORG_CHANGE_DIR.exists():
        return []
    rows: list[dict] = []
    for path in sorted(ORG_CHANGE_DIR.glob("*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        for row in payload if isinstance(payload, list) else payload.get("changes", []):
            rows.append({**row, "fixture": path.name})
    return rows


def list_org_change_fixtures() -> list[str]:
    return sorted(p.name for p in ORG_CHANGE_DIR.glob("*.json")) if ORG_CHANGE_DIR.exists() else []


# --- Population-headcount adapter -------------------------------------------

def fetch_headcount_observations() -> list[dict]:
    """MOCK HRIS-shaped CSV source. Values remain dated claims with adapter provenance."""
    if not HEADCOUNT_DIR.exists():
        return []
    rows: list[dict] = []
    for path in sorted(HEADCOUNT_DIR.glob("*.csv")):
        with path.open(encoding="utf-8", newline="") as fh:
            for row in csv.DictReader(fh):
                rows.append({**row, "fixture": path.name})
    return rows
