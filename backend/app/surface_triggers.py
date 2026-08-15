"""Stage 17 Slice 4 — trigger counts for event-driven surfaces (`SURFACE-USAGE-SPEC.md` §6.4).

A renewal panel has no cadence. Elapsed time says nothing about it, so §6.2's window-coverage rule —
which is what stops a short window being read as a quiet one — has nothing to measure against and
every `event_driven` or `unscheduled` surface would report `insufficient_window` forever. Permanently
unobservable is permanently safe, which is the opposite of useful.

The answer §6.4 gives is that these surfaces are observed against their **trigger**: the number of
times, in the window, that the condition which should have summoned them was true. That count comes
from domain data rather than telemetry, and it does exactly one job — it decides **coverage**. It
never becomes an observation, and it is never divided into `rendered` or `engaged`. §6.4's own
example is three separate numbers side by side:

    the condition was true 4 times; rendered 4 times; engaged 0 times

which is a real `rendered_not_engaged` reading. A ratio of any two of them would be the composite
score §12 forbids, and it would be a worse one than most: "rendered on 4 of the 4 occasions it
mattered" reads like a compliance figure and says nothing about whether the surface was any use.

Four rules here are not obvious and are each one bad edit away from a confident lie.

**A registry row configures an evaluator and can never create one.** `EVALUATORS` is an allowlist in
this file, beside the SQL it runs. `Surface.trigger` selects one by name. An unknown name is not a
missing feature to be improvised around — it fails closed to *unobservable, and says which name it
did not recognise*. This is the readiness pillar rule (D-139) applied to the same shape of problem:
a definition that could name a new evaluator into existence would let a data edit decide what counts
as evidence.

**Zero is not disuse.** A trigger count of zero means the condition never arose — the surface had
nothing to be summoned by, so nothing about it is knowable. It reports `insufficient_window` with a
sentence naming the zero, and never `not_rendered`. Reading a zero-trigger window as evidence of
disuse would retire every surface for the crime of a quiet quarter, which is §9.3 exactly.

**Two occurrences, the same as everywhere else.** §6.2 requires two expected occurrences before a
window covers a scheduled surface, because one that did not happen is indistinguishable from a week
the operator was away. The identical argument holds for a trigger: one renewal you happened to miss
looks the same as a renewal panel nobody needs. The threshold is shared rather than restated.

**A failing evaluator names itself and refuses.** A missing table, a renamed column, a SQL error: the
surface goes unobservable with the evaluator named, never to a count of zero. Zero and "the query
broke" are different facts, and the second one silently becoming the first is how a retirement gets
argued from a typo.

This module reads domain tables and is therefore *upstream* of measurement, never downstream of it.
§17.1's boundary is directional and unchanged: nothing about which screens the operator uses may be
read by account status, pillar state, ranking, or any customer-facing surface. Reading a count of
renewals *into* the report does not cross that line; a domain module importing this one would.
"""
from __future__ import annotations

import sqlite3

from . import surfaces

# §6.2's threshold, shared rather than restated. Two occurrences before a window says anything.
TRIGGER_OCCURRENCES = 2

# How far ahead of a date the condition counts as "true". A renewal summons its panel while it is
# approaching, not on the day it lands, so the count asks whether a renewal was within reach of a day
# in the window. Named here rather than inlined so the one number a reader would want to check is
# visible beside the query that uses it.
APPROACH_DAYS = 90


def _count(conn: sqlite3.Connection, sql: str, params: tuple) -> int:
    row = conn.execute(sql, params).fetchone()
    return int(row[0] or 0)


# --- the allowlist ------------------------------------------------------------------------------
#
# Each evaluator answers one question: how many times in [start, end] was the condition true? Every
# one counts *occurrences of the condition*, never records touched, and never anything about a named
# individual. They read only dates and statuses.

def _renewal_approaching(conn, start, end):
    """§6.4's own example. A renewal within `APPROACH_DAYS` of a day in the window."""
    return _count(conn,
                  "SELECT COUNT(*) FROM contract_versions "
                  "WHERE COALESCE(archived,0)=0 AND renewal_date IS NOT NULL "
                  "AND renewal_date >= ? AND renewal_date <= date(?, ?)",
                  (start, end, f"+{APPROACH_DAYS} days"))


def _expansion_signal(conn, start, end):
    return _count(conn,
                  "SELECT COUNT(*) FROM pull_signals "
                  "WHERE COALESCE(archived,0)=0 AND occurred_on IS NOT NULL "
                  "AND occurred_on >= ? AND occurred_on <= ?", (start, end))


def _org_change_flagged(conn, start, end):
    return _count(conn,
                  "SELECT COUNT(*) FROM org_change_flags "
                  "WHERE occurred_on IS NOT NULL AND occurred_on >= ? AND occurred_on <= ?",
                  (start, end))


def _company_event_confirmed(conn, start, end):
    """Confirmed only. A proposed event has not yet earned the right to summon anything (D-110)."""
    return _count(conn,
                  "SELECT COUNT(*) FROM company_events "
                  "WHERE status='confirmed' AND substr(observed_at,1,10) >= ? "
                  "AND substr(observed_at,1,10) <= ?", (start, end))


def _extraction_run_landed(conn, start, end):
    return _count(conn,
                  "SELECT COUNT(*) FROM extraction_runs "
                  "WHERE substr(created_at,1,10) >= ? AND substr(created_at,1,10) <= ?",
                  (start, end))


def _coaching_run_completed(conn, start, end):
    return _count(conn,
                  "SELECT COUNT(*) FROM coaching_runs WHERE status IN ('completed','partial') "
                  "AND substr(finished_at,1,10) >= ? AND substr(finished_at,1,10) <= ?",
                  (start, end))


def _coaching_priority_available(conn, start, end):
    return _count(conn,
                  "SELECT COUNT(*) FROM coaching_observations WHERE is_top_priority=1 "
                  "AND substr(created_at,1,10) >= ? AND substr(created_at,1,10) <= ?",
                  (start, end))


# Exactly the evaluators the registry selects, and no more. An evaluator nothing selects is SQL
# nobody runs, which rots against a renamed column and then fails closed on the day some surface
# finally names it — a test asserts this set and the registry's triggers are the same set in both
# directions. Adding an evaluator here is half a change; the other half is the surface that uses it.
EVALUATORS = {
    "renewal_approaching": (_renewal_approaching, "a renewal was within 90 days"),
    "expansion_signal": (_expansion_signal, "an expansion signal was recorded"),
    "org_change_flagged": (_org_change_flagged, "an org change was flagged"),
    "company_event_confirmed": (_company_event_confirmed, "a company event was confirmed"),
    "extraction_run_landed": (_extraction_run_landed, "a document produced proposals"),
    "coaching_run_completed": (_coaching_run_completed, "a private coaching review completed"),
    "coaching_priority_available": (_coaching_priority_available,
                                    "a coaching priority became available to practice"),
}


# --- the reading --------------------------------------------------------------------------------

def _unobservable(reason: str, *, evaluator: str | None = None) -> dict:
    return {"evaluator": evaluator, "condition": None, "count": None,
            "covered": False, "available": False, "reason": reason}


def evaluate(conn: sqlite3.Connection, surface, start: str, end: str) -> dict:
    """One surface's trigger reading for the window. Never raises.

    Returns `available: False` with a stated `reason` in every case that is not a real count —
    no trigger declared, an unrecognised evaluator name, or a query that failed. Each of those is a
    different fact and each keeps its own sentence, because collapsing them into a zero is how a
    retirement gets argued from a broken query.
    """
    if surfaces.window_days(surface.cadence) is not None:
        # Scheduled. Elapsed time covers it and a trigger would be a second answer to one question.
        return _unobservable("This surface has a schedule and is covered by elapsed time.")
    if not surface.trigger:
        return _unobservable(
            f"{surface.label} has no schedule and no computable trigger, so nothing about it is "
            f"knowable from counts. It stays unobservable rather than being read as unused.")
    entry = EVALUATORS.get(surface.trigger)
    if entry is None:
        # Fails closed, and names what it did not recognise. A registry row selects an evaluator;
        # it can never define one.
        return _unobservable(
            f"{surface.label} names the trigger '{surface.trigger}', which this build does not "
            f"recognise. No count is available and nothing is claimed.",
            evaluator=surface.trigger)
    evaluator, condition = entry
    try:
        count = evaluator(conn, start[:10], end[:10])
    except sqlite3.Error as exc:
        # A broken query is not a zero.
        return _unobservable(
            f"The trigger for {surface.label} could not be counted ({exc.__class__.__name__}). "
            f"No count is available and nothing is claimed.", evaluator=surface.trigger)
    return {
        "evaluator": surface.trigger,
        "condition": condition,
        "count": count,
        "covered": count >= TRIGGER_OCCURRENCES,
        "available": True,
        "reason": None,
    }


def sentence(surface, trigger: dict) -> str:
    """The §6.2-shaped sentence for an event-driven surface whose window does not cover it.

    Server-authored, and it names the number so the claim is checkable — the same reason the
    scheduled sentence names both the observed days and the days required.
    """
    if not trigger.get("available"):
        return trigger.get("reason") or (
            f"{surface.label} is observed against its trigger, and no trigger count is available.")
    count = trigger["count"]
    if count == 0:
        return (f"The condition that summons {surface.label} — {trigger['condition']} — was never "
                f"true in this window, so nothing about it is knowable yet.")
    return (f"The condition that summons {surface.label} — {trigger['condition']} — was true "
            f"{count} time{'s' if count != 1 else ''}; {TRIGGER_OCCURRENCES} are needed before this "
            f"says anything.")


def counts(conn: sqlite3.Connection, start: str, end: str) -> dict[str, dict]:
    """Every registered surface's trigger reading, computed once per report."""
    return {s.key: evaluate(conn, s, start, end) for s in surfaces.REGISTRY}
