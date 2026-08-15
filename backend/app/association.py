"""Shared association engine (Comprehensive Spec §4.5).

One resolver for recordings, email, and (later) calendar: given attendee emails/names and content
keywords, it resolves the account, program, and matched people against the stakeholder registry,
with a confidence. It learns from manual corrections — a correction adds a hint and supersedes the
prior one (never a hard delete). Low confidence is surfaced, never guessed silently.
"""
from __future__ import annotations

import sqlite3

from .db import new_id, now_utc

EMAIL_MATCH = 0.9
NAME_MATCH = 0.6
KEYWORD_MATCH = 0.4
LOW_CONFIDENCE = 0.6   # below this, ingestion routes to manual triage


def _hint(conn, hint_type, key):
    r = conn.execute(
        "SELECT person_id, account_id FROM association_hints "
        "WHERE hint_type=? AND key=? AND active=1 ORDER BY created_at DESC LIMIT 1",
        (hint_type, key)).fetchone()
    return dict(r) if r else None


def _person_by_email(conn, addr):
    r = conn.execute(
        "SELECT id, account_id FROM persons WHERE lower(email)=? AND is_placeholder=0 AND archived=0 LIMIT 1",
        (addr,)).fetchone()
    return dict(r) if r else None


def _person_by_name(conn, name):
    r = conn.execute(
        "SELECT id, account_id FROM persons WHERE lower(name)=? AND is_placeholder=0 AND archived=0 LIMIT 1",
        (name.lower(),)).fetchone()
    return dict(r) if r else None


def pick_program(conn, account_id, person_ids):
    """The most plausible program inside `account_id`, or None.

    Public because the account drop zone needs it: a dropped `.eml` takes its account from the page
    rather than from the sender (ACCOUNT-INTAKE-SPEC.md §8), and if it then left `program_id` NULL
    while a synced copy of the same message got one, the two paths would produce different records
    from identical material — the divergence §7.4 exists to prevent.

    **The account constraint is load-bearing, not defensive.** A matched person can hold a
    stakeholder role in a program belonging to a *different* account, and without the join this
    would hand back that program — putting one client's material under another client's program on
    a run that names the right account. It matters more once the caller supplies the account
    independently of the people, which is exactly what a drop does.
    """
    if person_ids:
        q = ("SELECT r.program_id FROM stakeholder_roles r JOIN programs p ON p.id = r.program_id "
             "WHERE r.archived=0 AND p.account_id=? AND r.person_id IN (%s) "
             "ORDER BY r.updated_at DESC LIMIT 1" % ",".join("?" * len(person_ids)))
        r = conn.execute(q, (account_id, *person_ids)).fetchone()
        if r:
            return r["program_id"]
    r = conn.execute(
        "SELECT id FROM programs WHERE account_id=? AND archived=0 "
        "ORDER BY (onboarded_at IS NULL), onboarded_at DESC LIMIT 1", (account_id,)).fetchone()
    return r["id"] if r else None


def resolve(conn: sqlite3.Connection, *, emails=None, names=None, keywords=None) -> dict:
    """Return {account_id, program_id, person_id, confidence, matched_person_ids}."""
    emails = [e.lower() for e in (emails or []) if e]
    names = [n for n in (names or []) if n]
    keywords = [k.lower() for k in (keywords or []) if k]

    best = {"account_id": None, "person_id": None, "confidence": 0.0}
    matched: list[str] = []

    def consider(account_id, person_id, score):
        if account_id and score > best["confidence"]:
            best.update(account_id=account_id, person_id=person_id, confidence=score)

    for e in emails:
        hint = _hint(conn, "email_person", e)
        p = ({"id": hint["person_id"], "account_id": hint["account_id"]} if hint and hint["person_id"]
             else _person_by_email(conn, e))
        if p:
            matched.append(p["id"])
            consider(p["account_id"], p["id"], EMAIL_MATCH)

    for n in names:
        hint = _hint(conn, "name_person", n.lower())
        p = ({"id": hint["person_id"], "account_id": hint["account_id"]} if hint and hint["person_id"]
             else _person_by_name(conn, n))
        if p:
            matched.append(p["id"])
            consider(p["account_id"], p["id"], NAME_MATCH)

    for k in keywords:
        h = _hint(conn, "keyword_account", k)
        if h and h["account_id"]:
            consider(h["account_id"], None, KEYWORD_MATCH)
            continue
        r = conn.execute(
            "SELECT id FROM accounts WHERE archived=0 AND (lower(name) LIKE ? OR lower(short_context) LIKE ?) LIMIT 1",
            (f"%{k}%", f"%{k}%")).fetchone()
        if r:
            consider(r["id"], None, KEYWORD_MATCH)

    matched = list(dict.fromkeys(matched))
    program_id = pick_program(conn, best["account_id"], matched) if best["account_id"] else None
    return {
        "account_id": best["account_id"], "program_id": program_id,
        "person_id": best["person_id"], "confidence": round(best["confidence"], 2),
        "matched_person_ids": matched,
    }


def record_correction(conn: sqlite3.Connection, *, hint_type: str, key: str,
                      person_id: str | None = None, account_id: str | None = None) -> dict:
    """Learn from a manual correction: supersede any prior active hint for this key, add a new one."""
    key = key.lower()
    with conn:
        conn.execute(
            "UPDATE association_hints SET active=0 WHERE hint_type=? AND key=? AND active=1",
            (hint_type, key))
        row = {"id": new_id(), "hint_type": hint_type, "key": key, "person_id": person_id,
               "account_id": account_id, "source": "correction", "active": 1, "created_at": now_utc()}
        conn.execute(
            "INSERT INTO association_hints (id, hint_type, key, person_id, account_id, source, active, created_at) "
            "VALUES (:id,:hint_type,:key,:person_id,:account_id,:source,:active,:created_at)", row)
    return row
