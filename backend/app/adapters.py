"""External-source adapters — MOCK implementations only (Comprehensive Spec Part 4 / Part 6).

Every external touchpoint is an adapter with a mock now and a config swap later. Nothing here
reaches a real inbox, recording store, or transcription service; the mock reads fixture files
under app/fixtures/. Flipping any of these to a real source is a CONNECTIONS.md gate.
"""
from __future__ import annotations

import email
import csv
import json
import os
import re
from email.utils import parseaddr, getaddresses, parsedate_to_datetime
from pathlib import Path

FIXTURES = Path(__file__).resolve().parent / "fixtures"
EMAIL_DIR = FIXTURES / "emails"
TRANSCRIPT_DIR = FIXTURES / "transcripts"
CALENDAR_DIR = FIXTURES / "calendar"
ORG_CHANGE_DIR = FIXTURES / "org_changes"
HEADCOUNT_DIR = FIXTURES / "headcount"
COMPANY_INTEL_DIR = FIXTURES / "company_intel"


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


def recording_provider() -> str:
    """Who produced the transcript. Recorded on the extraction run so the §6.6 source-version key
    names its origin: two providers can hand back the same reference and mean different material.
    Flipping this to a real engine is a CONNECTIONS.md decision, not a code change here."""
    return "mock-transcription"


def list_transcript_fixtures() -> list[str]:
    return sorted(p.name for p in TRANSCRIPT_DIR.glob("*.txt")) if TRANSCRIPT_DIR.exists() else []


# --- Email adapter -----------------------------------------------------------

def _body(msg) -> tuple[str, str]:
    """`(text, body_source)` — the readable body and which part it came from.

    `body_source` is `text/plain`, `html_only`, or `empty`, and it exists because the empty string
    means three different things. A synced fixture never hit that ambiguity; a *dropped* message
    can (§7.2), and "there was no plain-text part" has to reach the receipt as its own sentence
    rather than as "nothing in that was clear enough to draft", which would blame the document for
    a shape we declined to read. Reading `text/html` instead would mean running a tag stripper over
    untrusted markup, which is a parser-hardening question nobody has reviewed — so it is named,
    not attempted.

    Decoding is per part, with the charset the part declares. `decode=True` hands back the
    transfer-decoded bytes; `get_content_charset()` is what the message says they are.
    """
    if msg.is_multipart():
        html = False
        for part in msg.walk():
            ctype = part.get_content_type()
            if ctype == "text/plain":
                return _decode_part(part), "text/plain"
            html = html or ctype == "text/html"
        return "", ("html_only" if html else "empty")
    payload = msg.get_payload(decode=True)
    if not payload:
        text = msg.get_payload() or ""
        return text, ("text/plain" if text else "empty")
    if msg.get_content_type() == "text/html":
        return "", "html_only"
    return _decode_part(msg), "text/plain"


def _decode_part(part) -> str:
    """One MIME part's bytes, decoded with the charset **that part declares**.

    Not UTF-8, and not the whole message's charset: a message is allowed to carry parts in
    different encodings, and a citation is only worth having if it is byte-accurate to what the
    source said. `errors="replace"` is the last resort for a part whose declared charset is a lie —
    a mangled character is preferable to refusing a message we can otherwise read in full, and the
    refusal would name the wrong culprit.
    """
    raw = part.get_payload(decode=True) or b""
    charset = part.get_content_charset() or "utf-8"
    try:
        return raw.decode(charset, errors="replace")
    except LookupError:                      # a charset name Python has never heard of
        return raw.decode("utf-8", errors="replace")


def _attachments(msg) -> list[str]:
    """Attachment filenames only. §14.8 wants attachments referenced when they support a proposal;
    the name and the link to the source `.eml` are that reference. Nothing reads the bytes."""
    if not msg.is_multipart():
        return []
    return [n for n in (p.get_filename() for p in msg.walk()) if n]


def parse_eml_bytes(raw: bytes, source_name: str) -> dict:
    """One RFC-822 message, parsed from bytes. The only `.eml` parser in this codebase.

    `_parse_eml` (the fixture sync) and the account drop zone (ACCOUNT-INTAKE-SPEC.md §7.3) both
    come through here, and that is the point: a second parser for drops is how the sync path and
    the drop path start disagreeing about what a message said, which would surface not as an error
    but as a comms timeline and a set of relationship-health counts that are quietly wrong.

    Parsed from BYTES, not text. `get_payload(decode=True)` on a str-parsed message falls back to
    `raw-unicode-escape`, which rewrites a real em dash as the six literal characters of its escape
    sequence — and that mangled text goes straight into a proposal description and span.

    `source_name` names where the bytes came from — a fixture filename for the sync path, the
    dropped filename for a drop. It is a fallback identity only: a message with no `Message-ID` is
    still identifiable rather than un-dedupable.
    """
    msg = email.message_from_bytes(raw)
    from_name, from_addr = parseaddr(msg.get("From", ""))
    tos = [addr for _n, addr in getaddresses([msg.get("To", "")]) if addr]
    ccs = [addr for _n, addr in getaddresses([msg.get("Cc", "")]) if addr]
    try:
        dt = parsedate_to_datetime(msg.get("Date", ""))
        date_iso = dt.isoformat() if dt else None
    except (TypeError, ValueError):
        date_iso = None
    # §14.8 message identity: the Message-ID is the message, and In-Reply-To/References are what
    # make the conversation reconstructible. Falling back to the fixture name keeps a malformed
    # fixture identifiable rather than un-dedupable.
    message_id = (msg.get("Message-ID") or source_name).strip("<>")
    body, body_source = _body(msg)
    return {
        "external_id": message_id,
        "message_id": message_id,
        "in_reply_to": msg.get("In-Reply-To"),
        "references": msg.get("References"),
        "from_name": from_name, "from_addr": from_addr.lower(),
        "to_addrs": [a.lower() for a in tos],
        "cc_addrs": [a.lower() for a in ccs],
        "subject": msg.get("Subject", ""),
        "date_iso": date_iso,
        "body": body.strip(),
        # Which part the body came from, so a caller can tell "empty message" from "we declined to
        # read the only part there was". §7.2.
        "body_source": body_source,
        "attachments": _attachments(msg),
        "fixture": source_name,
    }


def _parse_eml(path: Path) -> dict:
    """The fixture caller. Behaviour is unchanged — one implementation, two callers (§7.3)."""
    return parse_eml_bytes(path.read_bytes(), path.name)


def email_provider() -> str:
    """Who supplied the message. Recorded on an email extraction run so its §6.6 source-version key
    names its origin, exactly as `recording_provider` does for transcripts. Two providers can hand
    back the same Message-ID and mean different material. Real provider = CONNECTIONS.md switch."""
    return "mock-inbox"


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


# --- Company-intelligence adapter ------------------------------------------

def fetch_company_intel() -> list[dict]:
    """MOCK public-source boundary. Fixtures contain snapshots and extracted proposals.

    No URL is fetched here. Real retrieval and extraction are separate CONNECTIONS.md gates.
    """
    mode = os.environ.get("COMPANY_INTEL_BACKEND", "mock").strip().lower()
    if mode != "mock":
        from . import connections
        connections.require_real_connection("company_intel_source", mode)
        raise RuntimeError("company-intelligence real mode has no implementation; use COMPANY_INTEL_BACKEND=mock")
    if not COMPANY_INTEL_DIR.exists():
        return []
    rows: list[dict] = []
    for path in sorted(COMPANY_INTEL_DIR.glob("*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        for row in payload if isinstance(payload, list) else payload.get("items", []):
            rows.append({**row, "fixture": path.name})
    return rows


def list_company_intel_fixtures() -> list[str]:
    return sorted(p.name for p in COMPANY_INTEL_DIR.glob("*.json")) if COMPANY_INTEL_DIR.exists() else []
