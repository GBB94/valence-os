"""Sales-handover intake parse (PHASE-3-SPEC.md §1a).

A deterministic, local, mock parser: pasted sales notes -> proposed records the operator
accepts one by one (same approval pattern as transcript extraction — nothing writes without
acceptance). No browsing, no external calls; the text is treated as DATA, never instructions.
The real/LLM intake parser is a CONNECTIONS.md switch later; this proves the surface.

Proposal types (stateless — the client sends an accepted proposal back to /intake/accept):
  stakeholder   -> a client Person (+ stakeholder_role) to create
  key_date      -> a milestone to create (label + date)
  incumbent     -> text to append to account.incumbent_note
  open_question -> a first_call checklist item to add
"""
from __future__ import annotations

import re
import sqlite3

from fastapi import HTTPException

from . import repo
from .db import now_utc

# "Name — Title" / "Name, Title" / "Name (Title)" where Name is 2+ capitalized words.
_NAME = r"[A-Z][a-z]+(?:\s+[A-Z][a-z]+)+"
_STAKEHOLDER_RES = [
    re.compile(rf"\b({_NAME})\s*[\(—,-]\s*(?:the\s+)?([A-Za-z][A-Za-z /]+?)\)?(?:[.;,\n]|$)"),
]
_ISO_DATE = re.compile(r"\b(\d{4}-\d{2}-\d{2})\b")
_DATE_LABEL = re.compile(r"([A-Za-z][A-Za-z \-]{2,40}?)\s*(?:on|:|=|is|by)?\s*(\d{4}-\d{2}-\d{2})", re.I)
_INCUMBENT = re.compile(r"([^.\n]*\b(?:incumbent|currently using|current vendor|replacing)\b[^.\n]*)", re.I)
_QUESTION = re.compile(r"([A-Z][^?.\n]{6,}\?)")

_TITLE_STOP = {"we", "the", "they", "it", "action", "next", "kickoff", "renewal"}

_PLACEHOLDER_ROLE_TERMS = (
    ("works_council_contact", ("works council", "works-council")),
    ("legal_dpo", ("legal", "dpo", "privacy")),
    ("budget_owner", ("budget owner", "economic buyer")),
    ("champion", ("champion",)),
    ("it", ("it security", "security lead", "cio", "ciso")),
    ("other", ("chro", "chief human resources")),
)


def _matching_placeholder(conn: sqlite3.Connection, account_id: str, proposal: dict) -> dict | None:
    """Return one role-identical placeholder, never a fuzzy title guess.

    Intake used to create a second person for "Aisha Kone (Champion)" while leaving the seeded
    Champion placeholder—and its Today escalation—alive.  Only explicit role terms participate;
    ordinary titles such as "VP of Learning" still create a new stakeholder.
    """
    title = (proposal.get("title") or "").strip().lower()
    roles = [role for role, terms in _PLACEHOLDER_ROLE_TERMS if any(term in title for term in terms)]
    if len(roles) != 1:
        return None
    matches = repo.list_rows(
        conn, "persons", where="account_id=? AND is_placeholder=1 AND expected_role=?",
        params=(account_id, roles[0]),
    )
    return matches[0] if len(matches) == 1 else None


def parse_intake(text: str) -> list[dict]:
    """Return ordered, de-duplicated proposals. Deterministic for a given input."""
    if not text or not text.strip():
        return []
    proposals: list[dict] = []
    seen: set[tuple] = set()

    def add(kind: str, key: tuple, payload: dict, source: str):
        if key in seen:
            return
        seen.add(key)
        proposals.append({"type": kind, "source_span": source.strip()[:200], **payload})

    for rx in _STAKEHOLDER_RES:
        for m in rx.finditer(text):
            name, title = m.group(1).strip(), m.group(2).strip()
            if name.split()[0].lower() in _TITLE_STOP or len(title) > 40:
                continue
            add("stakeholder", ("stk", name.lower()),
                {"name": name, "title": title}, m.group(0))

    labelled_dates: set[str] = set()
    for m in _DATE_LABEL.finditer(text):
        label, iso = m.group(1).strip(" -"), m.group(2)
        if label.lower() in _TITLE_STOP or len(label) < 3:
            continue
        labelled_dates.add(iso)
        add("key_date", ("date", iso, label.lower()),
            {"label": label.title(), "date": iso}, m.group(0))
    # Bare dates with no label still surface as a generic key date — but only if the same date
    # did not already produce a labelled one. "Go live is 2026-10-01" used to yield both
    # "Go Live" and a second unlabelled "Key date", so the operator triaged the same fact
    # twice; the 30-second capture rule loses every time that happens.
    for m in _ISO_DATE.finditer(text):
        if m.group(1) in labelled_dates:
            continue
        add("key_date", ("date", m.group(1), ""),
            {"label": "Key date", "date": m.group(1)}, m.group(0))

    for m in _INCUMBENT.finditer(text):
        add("incumbent", ("inc", m.group(1).lower()[:40]),
            {"note": m.group(1).strip()}, m.group(1))

    for m in _QUESTION.finditer(text):
        add("open_question", ("q", m.group(1).lower()[:40]),
            {"question": m.group(1).strip()}, m.group(1))

    return proposals


def accept_proposal(conn: sqlite3.Connection, account_id: str,
                    proposal: dict, program_id: str | None = None) -> dict:
    """Create the record a proposal describes. Mirrors the extraction accept contract:
    returns {created_type, created}."""
    repo.get_row(conn, "accounts", account_id)
    kind = proposal.get("type")

    if kind == "stakeholder":
        placeholder = _matching_placeholder(conn, account_id, proposal)
        if placeholder:
            person = repo.patch(conn, "persons", placeholder["id"], {
                "name": proposal["name"], "title": proposal.get("title"), "is_placeholder": 0,
                "placeholder_why": None, "find_by_date": None, "expected_influence": None,
                "expected_role": None,
            }, object_type="person", allow_null={"placeholder_why", "find_by_date",
                                                   "expected_influence", "expected_role"})
        else:
            person = repo.insert(conn, "persons", {
                "name": proposal["name"], "affiliation": "client",
                "account_id": account_id, "title": proposal.get("title"),
            }, object_type="person")
        if program_id and not placeholder:
            repo.insert(conn, "stakeholder_roles",
                        {"program_id": program_id, "person_id": person["id"], "role": "other"},
                        object_type="stakeholder_role")
        return {"created_type": "person", "created": person,
                "filled_placeholder_id": placeholder["id"] if placeholder else None}

    if kind == "key_date":
        if not program_id:
            raise HTTPException(422, "a key_date needs a program_id to become a milestone")
        ms = repo.insert(conn, "milestones", {
            "program_id": program_id, "name": proposal.get("label", "Key date"),
            "target_date": proposal["date"],
        }, object_type="milestone")
        return {"created_type": "milestone", "created": ms}

    if kind == "incumbent":
        acct = repo.get_row(conn, "accounts", account_id)
        existing = acct.get("incumbent_note")
        merged = f"{existing}\n{proposal['note']}".strip() if existing else proposal["note"]
        updated = repo.patch(conn, "accounts", account_id,
                             {"incumbent_note": merged}, object_type="account")
        return {"created_type": "account", "created": updated}

    if kind == "open_question":
        item = repo.insert(conn, "checklist_items", {
            "account_id": account_id, "program_id": program_id,
            "section": "first_call", "label": proposal["question"],
            "detail": "From sales-handover intake.",
        }, object_type="checklist_item")
        return {"created_type": "checklist_item", "created": item}

    raise HTTPException(422, f"unknown intake proposal type: {kind}")
