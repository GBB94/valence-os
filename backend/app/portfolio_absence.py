"""
Portfolio absence counters (VISIBILITY-SPEC §4) — *where am I not looking.*

Every other portfolio read ranks or summarises what exists: `queue.build_queue` orders what needs
attention, `internal_reporting.portfolio_analytics` aggregates asks and escalations,
`internal_roster.coverage_data` is account-scoped. None of them can answer the question an operator
actually opens the app with on a Monday, which is about the accounts they have *not* touched.

Two rules shape everything here.

**These are counts about our own record-keeping, never about the customer.** An account with no
recorded interaction in thirty days is a fact about us. That is what keeps this inside the trust
boundary: nothing here reads, infers, or approximates customer behaviour, and nothing that does may
be added — a counter over the customer's side of the relationship would be the individual-usage
boundary crossed by arithmetic rather than by a column.

**State the count, never score it.** There is no composite coverage score, no percentage of
portfolio, no ring, no ramp across the strip. Four independent numbers that do not combine, for the
same reason readiness has six pillars and no health score: a single number would be read as a grade,
and a grade about coverage is a claim nobody here is entitled to make.

Nothing is stored. Every number is a `NOT EXISTS` over live records, computed on the read.
"""
from __future__ import annotations

import sqlite3
from datetime import date, timedelta

from fastapi import HTTPException

from .db import now_utc

# The default lookback. It is a **coverage threshold, not a benchmark**: it asserts nothing about
# whether thirty days without a note is good or bad, only which rows this read is asking about. The
# no-hard-coded-benchmarks rule bans the claim, not the window — recorded here so the next reader
# does not have to re-derive the distinction and then delete a working default over it. The window is
# a caller-supplied parameter and always renders inside the sentence, never as a silent constant.
DEFAULT_WINDOW_DAYS = 30
MIN_WINDOW_DAYS = 1
MAX_WINDOW_DAYS = 365


def _plural(count: int, singular: str) -> str:
    return singular if count == 1 else f"{singular}s"


# --- the four counters --------------------------------------------------------------------------
#
# Each is a `NOT EXISTS` against a live record of one kind, anchored on a date we recorded. They are
# deliberately four separate reads rather than one join: an account can be absent from three of them
# and present in the fourth, and collapsing that into one row would lose exactly the information the
# strip exists to show.
#
# `interaction` and `touch` are different words on purpose and the SQL keeps them different: the
# account counter asks whether *anything* was recorded, the program counter asks whether a
# `meaningful_touch` was — the same definition `internal_roster.contribution` already uses. Widening
# the second to any interaction would let an automated log entry read as contact.

_ACCOUNT_NO_INTERACTION = """
SELECT a.id, a.name FROM accounts a
WHERE a.archived = 0
  AND NOT EXISTS (
    SELECT 1 FROM interactions i
    WHERE i.account_id = a.id AND i.archived = 0 AND i.occurred_on >= ?)
ORDER BY a.name
"""

_ACCOUNT_NO_ASSESSMENT = """
SELECT a.id, a.name FROM accounts a
WHERE a.archived = 0
  AND NOT EXISTS (
    SELECT 1 FROM stakeholder_roles s
    JOIN programs p ON p.id = s.program_id
    WHERE p.account_id = a.id AND p.archived = 0 AND s.archived = 0
      AND s.stance_assessed_on IS NOT NULL AND s.stance_assessed_on >= ?)
ORDER BY a.name
"""

# A retracted link is explicitly withdrawn rather than archived (0046), and a withdrawn piece of
# evidence is not evidence we hold. Both exclusions are required or the counter would report an
# account as covered by something an operator took back.
_ACCOUNT_NO_READINESS_EVIDENCE = """
SELECT a.id, a.name FROM accounts a
WHERE a.archived = 0
  AND NOT EXISTS (
    SELECT 1 FROM readiness_requirement_evidence_links e
    WHERE e.account_id = a.id AND e.archived = 0 AND e.retracted_at IS NULL
      AND substr(e.created_at, 1, 10) >= ?)
ORDER BY a.name
"""

# `closed` is the only phase that is not active; the other five are all live work. Naming the
# exclusion rather than listing the five means a phase added later is treated as active by default,
# which is the safe direction: a new phase silently dropping out of a coverage count is the failure
# that would go unnoticed.
_PROGRAM_NO_TOUCH = """
SELECT p.id, p.name, p.phase, p.account_id, a.name AS account_name
FROM programs p JOIN accounts a ON a.id = p.account_id
WHERE p.archived = 0 AND a.archived = 0 AND p.phase <> 'closed'
  AND NOT EXISTS (
    SELECT 1 FROM interactions i
    WHERE i.program_id = p.id AND i.archived = 0 AND i.meaningful_touch = 1
      AND i.occurred_on >= ?)
ORDER BY a.name, p.name
"""


def _counter(conn: sqlite3.Connection, *, key: str, sql: str, cutoff: str,
             record_kind: str, noun: str, predicate: str, days: int) -> dict:
    """One counter, its records, and the sentence that states both.

    The sentence is authored here rather than in the view because the count and the window are both
    server facts and the number has to appear beside the window that produced it. A view assembling
    "62 accounts" and "in 30 days" separately is a view that can render one without the other.
    """
    rows = [dict(row) for row in conn.execute(sql, (cutoff,))]
    count = len(rows)
    return {
        "key": key,
        "count": count,
        "record_kind": record_kind,
        # The list the number counted, always shipped with it. A count an operator cannot open is an
        # accusation they have no way to answer (§4.2, rule 4).
        "records": rows,
        "sentence": f"{count} {_plural(count, noun)} {predicate} in {days} days",
    }


def absence_counters(conn: sqlite3.Connection, days: int = DEFAULT_WINDOW_DAYS) -> dict:
    """The four counters, their record lists, and the window they were computed over."""
    days = int(days)
    if days < MIN_WINDOW_DAYS or days > MAX_WINDOW_DAYS:
        raise HTTPException(422, f"absence window must be {MIN_WINDOW_DAYS} to {MAX_WINDOW_DAYS} days")
    today = date.fromisoformat(now_utc()[:10])
    cutoff = (today - timedelta(days=days)).isoformat()
    counters = [
        _counter(conn, key="accounts_without_interaction", sql=_ACCOUNT_NO_INTERACTION,
                 cutoff=cutoff, record_kind="account", noun="account",
                 predicate="with no recorded interaction", days=days),
        _counter(conn, key="accounts_without_assessment", sql=_ACCOUNT_NO_ASSESSMENT,
                 cutoff=cutoff, record_kind="account", noun="account",
                 predicate="with no dated stakeholder assessment", days=days),
        _counter(conn, key="accounts_without_readiness_evidence", sql=_ACCOUNT_NO_READINESS_EVIDENCE,
                 cutoff=cutoff, record_kind="account", noun="account",
                 predicate="with no readiness evidence recorded", days=days),
        _counter(conn, key="programs_without_touch", sql=_PROGRAM_NO_TOUCH,
                 cutoff=cutoff, record_kind="program", noun="program",
                 predicate="in an active phase with no recorded touch", days=days),
    ]
    return {
        "window": {"days": days, "since": cutoff, "default_days": DEFAULT_WINDOW_DAYS},
        "counters": counters,
        # Stated on the payload rather than left to the view to remember. The strip is the one place
        # four numbers sit in a row, which is exactly where a reader starts adding them up.
        "basis": ("Counts of our own record-keeping over the stated window. They are independent and "
                  "do not combine into a coverage score."),
    }
