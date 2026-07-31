"""Cadence engine + relationship health (Comprehensive Spec §§3.6, 3.7).

Cadence: a target touch interval per stakeholder role, defaulted by power-interest quadrant
(floored for senior roles), overridable per role. State is derived from the last meaningful
touch — nothing about cadence "state" is stored. Overdue relationships get a suggested next
touch that carries CONTENT (what they care about, open items, wins to share), never "ping X".

Health: an evidence-based panel, never one opaque score. Recency/frequency and stance trend are
derived now; reciprocity and attendance are marked pending until the comms/calendar adapters are
connected (Stage 4/7) — shown as unknown, never fabricated (trust boundary + freshness discipline).
"""
from __future__ import annotations

import sqlite3
from datetime import date

from .db import now_utc

# Quadrant -> target interval (§3.6). power = influence, interest = stance.
QUADRANT_DAYS = {"manage_closely": 14, "keep_satisfied": 42, "keep_informed": 30, "monitor": 90}
QUADRANT_LABEL = {"manage_closely": "Manage closely", "keep_satisfied": "Keep satisfied",
                  "keep_informed": "Keep informed", "monitor": "Monitor"}
_SENIOR = ("champion", "budget_owner", "program_owner", "executive_sponsor", "financial_gatekeeper")


def quadrant(influence: str | None, stance: str | None) -> str:
    high_power = influence == "high"
    high_interest = stance == "supporter"
    if high_power and high_interest:
        return "manage_closely"
    if high_power:
        return "keep_satisfied"
    if high_interest:
        return "keep_informed"
    return "monitor"


def default_cadence_days(role: str, influence: str | None, stance: str | None) -> int:
    days = QUADRANT_DAYS[quadrant(influence, stance)]
    if role in _SENIOR:
        days = min(days, 21)   # senior relationships get touched at least every three weeks
    return days


def target_days(role_row: dict) -> int:
    if role_row.get("cadence_target_days"):
        return int(role_row["cadence_target_days"])
    return default_cadence_days(role_row.get("role", "other"),
                                role_row.get("influence"), role_row.get("stance"))


def _days_since(iso: str | None, today: str) -> int | None:
    if not iso:
        return None
    try:
        return (date.fromisoformat(today) - date.fromisoformat(iso[:10])).days
    except ValueError:
        return None


def last_meaningful_touch(conn: sqlite3.Connection, person_id: str) -> str | None:
    return conn.execute(
        "SELECT MAX(i.occurred_on) m FROM interaction_participants ip "
        "JOIN interactions i ON i.id = ip.interaction_id "
        "WHERE ip.person_id=? AND i.meaningful_touch=1 AND i.archived=0",
        (person_id,)).fetchone()["m"]


def cadence_state(conn: sqlite3.Connection, role_row: dict, today: str | None = None) -> dict:
    today = today or now_utc()[:10]
    tgt = target_days(role_row)
    last = last_meaningful_touch(conn, role_row["person_id"])
    since = _days_since(last, today)
    overdue = since is None or since > tgt
    return {
        "quadrant": quadrant(role_row.get("influence"), role_row.get("stance")),
        "target_days": tgt, "last_touch": last, "days_since": since,
        "overdue": overdue, "overdue_by": (since - tgt) if (since is not None and since > tgt) else None,
    }


def suggested_touch(conn: sqlite3.Connection, person_id: str, name: str, cares_about: str | None) -> str:
    """A next touch that carries content, not just contact (§3.6)."""
    bits: list[str] = []
    if cares_about:
        bits.append(f"they care about {cares_about}")
    commit = conn.execute(
        "SELECT description FROM commitments WHERE archived=0 AND status='open' "
        "AND (responsible_party_id=? OR acknowledged_by_id=?) ORDER BY due_date LIMIT 1",
        (person_id, person_id)).fetchone()
    if commit:
        bits.append(f"open item: {commit['description']}")
    # a shareable win (non-internal visibility only) — "wins not yet shared"
    win = conn.execute(
        "SELECT vs.outcome FROM value_stories vs WHERE vs.archived=0 AND vs.visibility_class != 'internal' "
        "AND vs.account_id=(SELECT account_id FROM persons WHERE id=?) "
        "ORDER BY vs.created_at DESC LIMIT 1", (person_id,)).fetchone()
    if win:
        bits.append(f"share the win: {win['outcome']}")
    if not bits:
        return f"Reach out to {name} — reconnect and resurface the plan."
    return f"Reach out to {name}: " + "; ".join(bits) + "."


def person_health(conn: sqlite3.Connection, person_id: str, primary_role: dict | None) -> dict:
    """The §3.7 evidence panel. Each element carries evidence + freshness; unavailable signals
    render as unknown (pending the comms/calendar adapters), never invented."""
    today = now_utc()[:10]
    last = last_meaningful_touch(conn, person_id)
    since = _days_since(last, today)
    freq90 = conn.execute(
        "SELECT COUNT(*) c FROM interaction_participants ip JOIN interactions i ON i.id=ip.interaction_id "
        "WHERE ip.person_id=? AND i.meaningful_touch=1 AND i.archived=0 AND i.occurred_on >= date(?, '-90 day')",
        (person_id, today)).fetchone()["c"]
    cad = cadence_state(conn, primary_role, today) if primary_role else None
    return {
        "recency": {"last_touch": last, "days_since": since, "evidence": "from logged interactions"},
        "frequency": {"count_90d": freq90, "evidence": "meaningful touches, last 90 days"},
        "cadence": cad,
        # Pending the comms/calendar adapters — shown as unknown, not fabricated (Part 6 gate).
        "reciprocity": {"status": "unknown", "reason": "awaiting comms adapter (counts + response times only)"},
        "attendance": {"status": "unknown", "reason": "awaiting calendar adapter (invited vs attended)"},
    }
