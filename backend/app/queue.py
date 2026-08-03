"""Portfolio attention queue (Module A) — v0.3.

Rules-based and explainable, never an opaque score. Every item carries a `because`,
an age, an optional due date, and a next action. Items are DERIVED each call; only
snooze/resolve is persisted in attention_state (the overlay), which can suppress an
item until a return date passes or the underlying facts materially change.

v0.3 ships the 6 triggers whose source objects exist (attention-rules.md). Renewal
windows (v1), stale imports (v2), and fired plays (v4) are intentionally absent.
"""
from __future__ import annotations

import json
import sqlite3
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import HTTPException

from . import audit, cadence, repo
from .db import new_id, now_utc

SENIOR_ROLES = ("champion", "budget_owner", "program_owner")
STALE_DAYS = 21  # matches the morning-check scenario ("untouched for three weeks")

# priority band per trigger (1 = highest), matching Module A's documented order
PRIORITY = {
    "overdue_commitment": 1,
    "active_blocker": 2,
    "unanswered_email": 2,         # Phase 3 §4.3 — flagged email past the response threshold
    "checklist_overdue": 3,        # Phase 3 §2 — baseline; escalates to 2 when >1wk past due
    "unidentified_placeholder": 3, # Phase 3 §3 — baseline; escalates to 2 when >1wk past find-by
    "renewal_window": 3,       # enabled by v1 contracts
    "stale_import": 4,         # enabled by v2 metrics/imports
    "fired_play": 5,           # enabled by v4 plays
    "at_risk_milestone": 6,
    "untriaged_inbox": 7,
    "cadence_overdue": 8,      # Phase 3 §3.6 — supersedes the fixed-21d stale_stakeholder trigger
    "open_task": 9,
    "aging_internal_ask": 1,
    "unacknowledged_internal_ask": 2,
    "commit_ask_warning": 2,
    "delivered_ask_evidence_gap": 2,
    "escalation_overdue": 1,
    "feedback_acknowledgment": 3,
    "feedback_resolution": 2,
    # Stage 7 episodes. Customer pull and confirmed org facts outrank vendor-push timing.
    "campaign_evidence_gap": 3,   # Stage 11.1 §5.3 — one item per campaign, never per child
    "comms_sequence_overdue": 3,  # Stage 13 — one item per sequence, never per late wave
    "expansion_signal": 2,
    "org_change_confirmed": 2,
    "land_and_leave": 2,
    "no_second_champion": 3,
    "champion_gone_quiet": 3,
    "stalled_cohort": 3,
    "calendar_moment": 4,
    "company_convergence": 2,
    "intel_review_debt": 3,
}

# Trigger escalates into the top "needs you now" band once this far past its date (§2/§3).
ESCALATE_AFTER_DAYS = 7

RENEWAL_WINDOW_DAYS = 120  # "renewal readiness visible at least 120 days out" (Section 10)


def _today() -> str:
    return now_utc()[:10]


def _days_since(iso_date: str | None, today: str) -> int:
    if not iso_date:
        return 0
    try:
        return max(0, (date.fromisoformat(today) - date.fromisoformat(iso_date[:10])).days)
    except ValueError:
        return 0


def _business_hours_between(
    start_iso: str,
    end_iso: str,
    timezone_name: str = "America/New_York",
    start_hour: int = 9,
    end_hour: int = 17,
    working_weekdays: set[int] | None = None,
) -> float:
    """Count weekday hours inside an account's configured local working window."""
    try:
        local_tz = ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError:
        local_tz = timezone.utc
    start = datetime.fromisoformat(start_iso)
    end = datetime.fromisoformat(end_iso)
    if start.tzinfo is None:
        start = start.replace(tzinfo=timezone.utc)
    if end.tzinfo is None:
        end = end.replace(tzinfo=timezone.utc)
    start, end = start.astimezone(local_tz), end.astimezone(local_tz)
    if end <= start:
        return 0.0

    seconds = 0.0
    cursor = start.date()
    while cursor <= end.date():
        # Settings store ISO weekday numbers (1=Monday … 7=Sunday).
        active_days = working_weekdays or {1, 2, 3, 4, 5}
        if cursor.isoweekday() in active_days:
            window_start = datetime.combine(cursor, time(start_hour), tzinfo=local_tz)
            window_end = datetime.combine(cursor, time.min, tzinfo=local_tz) + timedelta(hours=end_hour)
            overlap_start, overlap_end = max(start, window_start), min(end, window_end)
            if overlap_end > overlap_start:
                seconds += (overlap_end - overlap_start).total_seconds()
        cursor += timedelta(days=1)
    return seconds / 3600


def _latest_overlays(conn: sqlite3.Connection) -> dict[str, dict]:
    """Most recent attention_state row per item_key."""
    rows = conn.execute(
        "SELECT * FROM attention_state ORDER BY created_at ASC"
    ).fetchall()
    latest: dict[str, dict] = {}
    for r in rows:
        latest[r["item_key"]] = dict(r)  # later rows overwrite earlier -> newest wins
    return latest


def _suppressed(overlay: dict | None, underlying_updated_at: str, today: str) -> str | None:
    """Return 'snoozed' / 'resolved' if the item is currently suppressed, else None.

    A snoozed item resurfaces when its return date passes OR the underlying object
    changed after the overlay was set. A resolved item resurfaces only on underlying change.
    """
    if not overlay:
        return None
    changed_since = underlying_updated_at and underlying_updated_at > overlay["created_at"]
    if overlay["state"] == "snoozed":
        if overlay.get("snooze_until") and overlay["snooze_until"] <= today:
            return None
        if changed_since:
            return None
        return "snoozed"
    if overlay["state"] == "resolved":
        if changed_since:
            return None
        return "resolved"
    return None


def _candidates(conn: sqlite3.Connection, today: str) -> list[dict]:
    items: list[dict] = []

    def prog_ctx():
        return (
            "SELECT p.id pid, p.name pname, a.id aid, a.name aname "
            "FROM programs p JOIN accounts a ON a.id = p.account_id"
        )

    progs = {r["pid"]: dict(r) for r in conn.execute(prog_ctx()).fetchall()}
    accounts = {r["aid"]: dict(r) for r in conn.execute(
        "SELECT id aid,name aname,NULL pid,NULL pname FROM accounts WHERE archived=0").fetchall()}

    # 1. Overdue commitments (any open commitment past due; none may be hidden)
    for r in conn.execute(
        "SELECT * FROM commitments WHERE archived=0 AND status='open' AND due_date < ?", (today,)
    ):
        p = progs.get(r["program_id"], accounts.get(r["account_id"], {}))
        overdue = _days_since(r["due_date"], today)
        items.append(_item(
            "overdue_commitment", "commitment", r["id"], r["updated_at"], p,
            title=r["description"],
            because=f"Overdue {overdue}d — commitment due {r['due_date']}.",
            age_days=overdue, due_date=r["due_date"], next_action="Close, chase, or renegotiate the due date.",
        ))

    # 2. Active blockers (risks or issues flagged is_blocker, still open)
    for r in conn.execute("SELECT * FROM risks WHERE archived=0 AND status='open' AND is_blocker=1"):
        p = progs.get(r["program_id"], {})
        items.append(_item(
            "active_blocker", "risk", r["id"], r["updated_at"], p,
            title=r["description"],
            because=f"Active blocker (risk) — raised {r['created_at'][:10]}.",
            age_days=_days_since(r["created_at"], today), due_date=None,
            next_action="Drive to closure or escalate.",
        ))
    for r in conn.execute("SELECT * FROM issues WHERE archived=0 AND status='open' AND is_blocker=1"):
        p = progs.get(r["program_id"], {})
        items.append(_item(
            "active_blocker", "issue", r["id"], r["updated_at"], p,
            title=r["description"],
            because=f"Active blocker (issue) — raised {r['created_at'][:10]}.",
            age_days=_days_since(r["created_at"], today), due_date=None,
            next_action="Drive to closure or escalate.",
        ))

    # 3. Renewal / notice windows (current contracts whose renewal is within the window)
    for r in conn.execute(
        "SELECT c.*, a.id aid, a.name aname FROM contract_versions c "
        "JOIN accounts a ON a.id = c.account_id WHERE c.archived=0 AND c.is_current=1 AND c.renewal_date IS NOT NULL"
    ):
        try:
            days_until = (date.fromisoformat(r["renewal_date"]) - date.fromisoformat(today)).days
        except ValueError:
            continue
        if days_until > RENEWAL_WINDOW_DAYS or days_until < -30:
            continue
        p = {"aid": r["aid"], "aname": r["aname"], "pname": None}
        notice = r["notice_period_days"]
        note = f" · notice period {notice}d" if notice else ""
        overlay = f" · ops expected decision {r['overlay_expected_decision_date']}" if r["overlay_expected_decision_date"] else ""
        items.append(_item(
            "renewal_window", "contract_version", r["id"], r["updated_at"], p,
            title=f"Renewal — {r['version_label']} ({r['seats'] or '?'} seats)",
            because=f"Renewal in {days_until}d on {r['renewal_date']}{note}{overlay}.",
            age_days=max(0, RENEWAL_WINDOW_DAYS - days_until), due_date=r["renewal_date"],
            next_action="Start renewal prep / confirm procurement timeline.",
        ))

    # 4. Failed or stale imports (metric sources past their freshness threshold)
    for d in conn.execute("SELECT * FROM metric_definitions WHERE archived=0"):
        latest = conn.execute(
            "SELECT MAX(current_through) m FROM metric_observations WHERE archived=0 AND definition_id=?",
            (d["id"],)).fetchone()["m"]
        stale = True
        age = None
        if latest:
            try:
                age = (date.fromisoformat(today) - date.fromisoformat(latest)).days
                stale = age > d["stale_after_days"]
            except ValueError:
                stale = True
        if not latest or stale:
            items.append(_item(
                "stale_import", "metric_definition", d["id"], d["updated_at"], {},
                title=f"Stale metric: {d['name']}",
                because=(f"No fresh data — last through {latest} ({age}d ago)." if latest else "No observations imported yet."),
                age_days=age or 999, due_date=None, next_action="Re-import from the Data team.",
            ))

    # 5. Fired plays awaiting completion
    for r in conn.execute(
        "SELECT pr.*, pd.name pname FROM play_runs pr JOIN play_definitions pd ON pd.id = pr.play_id "
        "WHERE pr.status='fired'"):
        acct = conn.execute("SELECT id aid, name aname FROM accounts WHERE id=?", (r["account_id"],)).fetchone()
        p = {"aid": acct["aid"], "aname": acct["aname"], "pname": None} if acct else {}
        items.append(_item(
            "fired_play", "play_run", r["id"], r["fired_at"], p,
            title=f"Play: {r['pname']}",
            because=f"Fired — {r['trigger_context']}.",
            age_days=_days_since(r["fired_at"], today), due_date=None,
            next_action=r["action_text"] or "Run the play and record effectiveness.",
        ))

    # 5b. Stage-7 signal episodes. Held episodes stay visible but never fire a play; hiding the
    # pacing guard would make "no recommendation" look like "no signal".
    for r in conn.execute(
        "SELECT se.*, a.name aname FROM signal_episodes se LEFT JOIN accounts a ON a.id=se.account_id "
        "WHERE se.status IN ('open','held') AND se.source_kind<>'attention'"):
        ctx = {}
        if r["context_json"]:
            try:
                ctx = json.loads(r["context_json"])
            except (TypeError, ValueError):
                ctx = {}
        p = {"aid": r["account_id"], "aname": r["aname"], "pid": r["program_id"], "pname": None}
        title = ctx.get("title") or r["kind"].replace("_", " ").title()
        why = r["explanation"]
        if r["status"] == "held":
            title = f"Held — {title}"
            why += f" {r['held_reason'] or 'Pacing guard is active.'}"
        items.append(_item(
            r["kind"], "signal_episode", r["id"], r["updated_at"], p,
            title=title, because=why, age_days=_days_since(r["opened_at"], today),
            due_date=None,
            next_action=("Close the value gap before vendor-initiated expansion."
                         if r["status"] == "held" else
                         ctx.get("next_action") or "Qualify, attach to an opportunity, or dismiss with a reason."),
        ))

    # Stage 14 review debt is an operational nudge, never evidence. One item per account.
    for r in conn.execute(
        "SELECT e.account_id,a.name aname,COUNT(*) proposed_count,MIN(e.created_at) oldest,MAX(e.updated_at) updated_at "
        "FROM company_events e JOIN accounts a ON a.id=e.account_id "
        "WHERE e.status='proposed' AND e.archived=0 AND date(e.created_at)<=date(?, '-7 days') "
        "GROUP BY e.account_id,a.name", (today,)):
        age = _days_since(r["oldest"], today)
        items.append(_item(
            "intel_review_debt", "account", r["account_id"], r["updated_at"],
            {"aid": r["account_id"], "aname": r["aname"], "pid": None, "pname": None},
            title=f"Review {r['proposed_count']} company-intel proposal(s)",
            because=f"Oldest unreviewed public-source proposal is {age}d old.",
            age_days=age, due_date=None, next_action="Review, confirm, or dismiss the proposed events.",
        ))

    # 5c. Earned pre-agreed expansions awaiting action. These fire regardless of a value gap;
    # the gap remains attached as risk rather than suppressing an agreement the client made.
    for r in conn.execute(
        "SELECT oe.*, oa.name agreement_name, a.name aname FROM operational_agreement_events oe "
        "JOIN operational_agreements oa ON oa.id=oe.agreement_id "
        "JOIN accounts a ON a.id=oe.account_id WHERE oe.status='fired'"):
        late = r["action_due_on"] < today
        items.append(_item(
            "expansion_signal", "operational_agreement_event", r["id"], r["updated_at"],
            {"aid": r["account_id"], "aname": r["aname"], "pid": None, "pname": None},
            title=f"Earned expansion — {r['agreement_name']}",
            because=(f"Pre-agreed threshold fired; action was due {r['action_due_on']}."
                     if late else f"Pre-agreed threshold fired; act by {r['action_due_on']}.") +
                    (f" {r['risk_note']}" if r["risk_note"] else ""),
            age_days=_days_since(r["fired_at"], today), due_date=r["action_due_on"],
            next_action="Run the agreed process and draft the expansion paper.",
        ))

    # 6. At-risk upcoming milestones (flagged, or past target and incomplete)
    for r in conn.execute("SELECT * FROM milestones WHERE archived=0 AND status='upcoming'"):
        past = bool(r["target_date"]) and r["target_date"] < today
        if not (r["at_risk"] or past):
            continue
        p = progs.get(r["program_id"], {})
        why = "past target date" if past else "flagged at risk"
        items.append(_item(
            "at_risk_milestone", "milestone", r["id"], r["updated_at"], p,
            title=r["name"],
            because=f"Milestone at risk — {why} (target {r['target_date'] or 'unset'}).",
            age_days=_days_since(r["target_date"], today) if past else 0, due_date=r["target_date"],
            next_action="Recover, re-baseline, or complete.",
        ))

    # 4. Untriaged inbox items
    for r in conn.execute("SELECT * FROM capture_inbox_items WHERE archived=0 AND status='untriaged'"):
        inter = conn.execute("SELECT account_id, program_id FROM interactions WHERE id=?", (r["interaction_id"],)).fetchone()
        p = progs.get(inter["program_id"], {}) if inter and inter["program_id"] else {}
        if not p and inter:
            a = conn.execute("SELECT id aid, name aname FROM accounts WHERE id=?", (inter["account_id"],)).fetchone()
            p = {"aid": a["aid"], "aname": a["aname"], "pname": None} if a else {}
        age = _days_since(r["created_at"], today)
        items.append(_item(
            "untriaged_inbox", "capture_inbox_item", r["id"], r["updated_at"], p,
            title=r["raw_text"],
            because=f"Untriaged note, {age}d old" + (" — aging" if age >= 3 else "") + ".",
            age_days=age, due_date=None, next_action="Convert or dismiss.",
        ))

    # 5. Cadence-overdue relationships (Phase 3 §3.6 — every tracked stakeholder has a target
    #    touch cadence; overdue ones fire with a suggested next touch that carries content).
    for r in conn.execute(
        "SELECT sr.*, pe.name pname FROM stakeholder_roles sr "
        "JOIN persons pe ON pe.id = sr.person_id "
        # placeholders are unidentified positions, not overdue relationships (their own trigger)
        "WHERE sr.archived=0 AND pe.is_placeholder=0 AND pe.affiliation='client'",
    ):
        r = dict(r)
        cad = cadence.cadence_state(conn, r, today)
        if not cad["overdue"]:
            continue
        p = progs.get(r["program_id"], {})
        since = cad["days_since"]
        touch = f"last touch {since}d ago" if since is not None else "no logged touch"
        items.append(_item(
            "cadence_overdue", "stakeholder_role", r["id"], r["updated_at"], p,
            title=f"{r['pname']} ({r['role'].replace('_', ' ')})",
            because=f"Cadence overdue — {cadence.QUADRANT_LABEL[cad['quadrant']]} "
                    f"(target every {cad['target_days']}d, {touch}).",
            age_days=(cad["overdue_by"] or since or 999),
            due_date=None,
            next_action=cadence.suggested_touch(conn, r["person_id"], r["pname"], r.get("cares_about")),
        ))

    # 7. Launch-checklist items past their due window (Phase 3 §2 escalation)
    for r in conn.execute(
        "SELECT ci.*, a.id aid, a.name aname, p.id pid, p.name pname "
        "FROM checklist_items ci JOIN accounts a ON a.id = ci.account_id "
        "LEFT JOIN programs p ON p.id = ci.program_id "
        "WHERE ci.archived=0 AND ci.status='open' AND ci.due_date IS NOT NULL AND ci.due_date < ?",
        (today,),
    ):
        overdue = _days_since(r["due_date"], today)
        p = {"aid": r["aid"], "aname": r["aname"], "pid": r["pid"], "pname": r["pname"]}
        section = r["section"].replace("_", " ")
        it = _item(
            "checklist_overdue", "checklist_item", r["id"], r["updated_at"], p,
            title=r["label"],
            because=f"Launch checklist slipping — {section} item {overdue}d past due.",
            age_days=overdue, due_date=r["due_date"],
            next_action="Do it, mark it done, or push the date.",
        )
        it["priority"] = 2 if overdue > ESCALATE_AFTER_DAYS else 3  # >1wk past -> risk band
        items.append(it)

    # 8. Unidentified org-chart placeholders past their find-by date (Phase 3 §3)
    for r in conn.execute(
        "SELECT pe.*, a.name aname FROM persons pe JOIN accounts a ON a.id = pe.account_id "
        "WHERE pe.archived=0 AND pe.is_placeholder=1 AND pe.find_by_date IS NOT NULL AND pe.find_by_date < ?",
        (today,),
    ):
        overdue = _days_since(r["find_by_date"], today)
        prow = conn.execute(
            "SELECT program_id FROM stakeholder_roles WHERE person_id=? AND archived=0 LIMIT 1",
            (r["id"],)).fetchone()
        p = progs.get(prow["program_id"], {}) if prow and prow["program_id"] else {}
        if not p:
            p = {"aid": r["account_id"], "aname": r["aname"], "pid": None, "pname": None}
        it = _item(
            "unidentified_placeholder", "person", r["id"], r["updated_at"], p,
            title=f"Still unidentified: {r['title'] or r['name']}",
            because=f"Critical position not identified — find-by {r['find_by_date']} passed {overdue}d ago.",
            age_days=overdue, due_date=r["find_by_date"],
            next_action="Identify the person and convert the placeholder.",
        )
        it["priority"] = 2 if overdue > ESCALATE_AFTER_DAYS else 3
        items.append(it)

    # 9. Flagged emails needing a response (Phase 3 §4.3). Age in hours when recent.
    for r in conn.execute(
        "SELECT cm.*, a.id aid, a.name aname, p.id pid, p.name pname "
        "FROM comm_messages cm JOIN accounts a ON a.id = cm.account_id "
        "LEFT JOIN programs p ON p.id = cm.program_id "
        "WHERE cm.archived=0 AND cm.needs_response=1 AND cm.responded=0",
    ):
        p = {"aid": r["aid"], "aname": r["aname"], "pid": r["pid"], "pname": r["pname"]}
        cfg = conn.execute(
            "SELECT priority_response_hours,business_timezone,business_day_start_hour,"
            "business_day_end_hour FROM account_settings WHERE account_id=?",
            (r["account_id"],),
        ).fetchone()
        threshold = cfg["priority_response_hours"] if cfg else 24
        hours = None
        if r["occurred_at"]:
            try:
                hours = int(_business_hours_between(
                    r["occurred_at"], now_utc(),
                    cfg["business_timezone"] if cfg else "America/New_York",
                    cfg["business_day_start_hour"] if cfg else 9,
                    cfg["business_day_end_hour"] if cfg else 17,
                ))
            except ValueError:
                hours = None
        if hours is not None and hours < threshold:
            continue
        age_days = _days_since(r["occurred_on"], today)
        unanswered = (f"unanswered {hours} business h" if hours is not None
                      else f"unanswered {age_days}d")
        items.append(_item(
            "unanswered_email", "comm_message", r["id"], r["updated_at"], p,
            title=r["subject"] or "(no subject)",
            because=f"{r['flag_reason'] or 'Flagged email'} — {unanswered}.",
            age_days=age_days, due_date=None,
            next_action="Reply, or mark handled.",
        ))

    # 6. Open tasks (overdue ones sort to the top of this band)
    for r in conn.execute("SELECT * FROM tasks WHERE archived=0 AND status='open'"):
        p = progs.get(r["program_id"], {})
        overdue = bool(r["due_date"]) and r["due_date"] < today
        age = _days_since(r["due_date"], today) if overdue else _days_since(r["created_at"], today)
        items.append(_item(
            "open_task", "task", r["id"], r["updated_at"], p,
            title=r["description"],
            because=("Overdue task — due " + r["due_date"] + ".") if overdue else "Open task.",
            age_days=age, due_date=r["due_date"], next_action="Do, reassign, or close.",
        ))

    # Internal asks are derived into Today; resolving a queue overlay never mutates the ask.
    for r in conn.execute(
        "SELECT * FROM internal_asks WHERE archived=0 AND status NOT IN ('delivered','declined') AND needed_by<?",
        (today,)):
        p = accounts.get(r["account_id"], {})
        age = _days_since(r["needed_by"], today)
        items.append(_item("aging_internal_ask", "internal_ask", r["id"], r["updated_at"], p,
            title=r["need"], because=f"Internal ask is {age}d past needed-by {r['needed_by']}.",
            age_days=age, due_date=r["needed_by"], next_action="Advance, escalate, deliver, or decline with reason."))

    internal_cfg = conn.execute("SELECT * FROM internal_operations_settings WHERE id='singleton'").fetchone()
    internal_weekdays = set(json.loads(internal_cfg["working_weekdays_json"]))
    for r in conn.execute("SELECT * FROM internal_asks WHERE archived=0 AND status='raised'"):
        default = conn.execute(
            "SELECT * FROM escalation_defaults WHERE archived=0 AND ask_type=? "
            "ORDER BY threshold_business_hours,severity LIMIT 1", (r["ask_type"],)
        ).fetchone()
        if not default:
            default = conn.execute(
                "SELECT * FROM escalation_defaults WHERE archived=0 AND ask_type='general' "
                "ORDER BY threshold_business_hours,severity LIMIT 1"
            ).fetchone()
        if not default:
            continue
        elapsed = _business_hours_between(
            r["created_at"], now_utc(), internal_cfg["business_timezone"],
            internal_cfg["business_day_start_hour"], internal_cfg["business_day_end_hour"],
            internal_weekdays,
        )
        if elapsed >= default["threshold_business_hours"]:
            p = accounts.get(r["account_id"], {})
            items.append(_item(
                "unacknowledged_internal_ask", "internal_ask", r["id"], r["updated_at"], p,
                title=r["need"],
                because=f"Ask remains unacknowledged after {int(elapsed)} internal business hours; policy threshold is {default['threshold_business_hours']}.",
                age_days=_days_since(r["created_at"], today), due_date=r["needed_by"],
                next_action="Record acknowledgment or apply the configured escalation path.",
            ))

    for r in conn.execute(
        "SELECT a.*,e.category forecast_category FROM internal_asks a "
        "JOIN forecast_entries e ON e.id=a.forecast_entry_id "
        "WHERE a.archived=0 AND a.status NOT IN ('delivered','declined') "
        "AND e.archived=0 AND e.category='commit' AND a.needed_by>=date('now')"
    ):
        default = conn.execute(
            "SELECT * FROM escalation_defaults WHERE archived=0 AND ask_type=? "
            "ORDER BY threshold_business_hours,severity LIMIT 1", (r["ask_type"],)
        ).fetchone() or conn.execute(
            "SELECT * FROM escalation_defaults WHERE archived=0 AND ask_type='general' "
            "ORDER BY threshold_business_hours,severity LIMIT 1"
        ).fetchone()
        if not default:
            continue
        local_tz = ZoneInfo(internal_cfg["business_timezone"])
        due_at = datetime.combine(date.fromisoformat(r["needed_by"]),
                                  time(internal_cfg["business_day_end_hour"]), tzinfo=local_tz).isoformat()
        remaining = _business_hours_between(
            now_utc(), due_at, internal_cfg["business_timezone"],
            internal_cfg["business_day_start_hour"], internal_cfg["business_day_end_hour"],
            internal_weekdays,
        )
        if remaining <= default["threshold_business_hours"]:
            p = accounts.get(r["account_id"], {})
            items.append(_item(
                "commit_ask_warning", "internal_ask", r["id"], r["updated_at"], p,
                title=r["need"],
                because=f"Commit-linked ask is inside its {default['threshold_business_hours']}-business-hour warning window.",
                age_days=0, due_date=r["needed_by"],
                next_action="Confirm delivery or escalate before the Commit call is exposed.",
            ))

    from .internal_forecast import evidence as forecast_evidence
    for r in conn.execute(
        "SELECT a.*,e.updated_at forecast_updated_at FROM internal_asks a "
        "LEFT JOIN forecast_entries e ON e.id=a.forecast_entry_id "
        "WHERE a.archived=0 AND a.status='delivered' "
        "AND (a.forecast_entry_id IS NOT NULL OR a.generated_document_id IS NOT NULL)"
    ):
        reasons = []
        if r["forecast_entry_id"] and not forecast_evidence(conn, r["forecast_entry_id"])["supported"]:
            reasons.append("linked forecast evidence remains incomplete")
        if r["generated_document_id"] and not conn.execute(
            "SELECT 1 FROM generated_document_sources WHERE document_id=?", (r["generated_document_id"],)
        ).fetchone():
            reasons.append("dependent artifact has no frozen source evidence")
        if reasons:
            p = accounts.get(r["account_id"], {})
            source_version = max(r["updated_at"], r["forecast_updated_at"] or r["updated_at"])
            items.append(_item(
                "delivered_ask_evidence_gap", "internal_ask", r["id"], source_version, p,
                title=r["need"], because="; ".join(reasons).capitalize() + ".",
                age_days=_days_since(r["delivered_on"], today), due_date=None,
                next_action="Complete the dependent evidence or reopen the ask with a reason.",
            ))

    for r in conn.execute(
        "SELECT e.*,a.account_id,a.need FROM escalation_instances e JOIN internal_asks a ON a.id=e.ask_id "
        "WHERE e.archived=0 AND e.status='open'"):
        elapsed = _business_hours_between(r["opened_at"], now_utc(),
            internal_cfg["business_timezone"], internal_cfg["business_day_start_hour"],
            internal_cfg["business_day_end_hour"], set(json.loads(internal_cfg["working_weekdays_json"])))
        if elapsed < r["expected_response_hours"]:
            continue
        p = accounts.get(r["account_id"], {})
        items.append(_item("escalation_overdue", "escalation", r["id"], r["updated_at"], p,
            title=r["need"], because=f"Escalation has no recorded response after {int(elapsed)} internal business hours.",
            age_days=_days_since(r["opened_at"], today), due_date=None, next_action=r["next_step"]))

    for r in conn.execute(
        "SELECT o.id,o.account_id,o.updated_at,i.title FROM product_feedback_occurrences o "
        "JOIN product_feedback_items i ON i.id=o.feedback_item_id WHERE o.archived=0 AND o.active=1 "
        "AND NOT EXISTS (SELECT 1 FROM product_feedback_touches t WHERE t.occurrence_id=o.id AND t.touch_type='acknowledgment')"):
        items.append(_item("feedback_acknowledgment", "product_feedback_occurrence", r["id"], r["updated_at"], accounts.get(r["account_id"], {}),
            title=r["title"], because="Client feedback is logged but not yet acknowledged.", age_days=0,
            due_date=None, next_action="Record the acknowledgment interaction; do not auto-send."))
    for r in conn.execute(
        "SELECT o.id,o.account_id,o.updated_at,i.title,i.status FROM product_feedback_occurrences o "
        "JOIN product_feedback_items i ON i.id=o.feedback_item_id WHERE o.archived=0 AND o.active=1 "
        "AND i.status IN ('shipped','declined') AND NOT EXISTS (SELECT 1 FROM product_feedback_touches t WHERE t.occurrence_id=o.id AND t.touch_type='resolution')"):
        items.append(_item("feedback_resolution", "product_feedback_occurrence", r["id"], r["updated_at"], accounts.get(r["account_id"], {}),
            title=r["title"], because=f"Feedback is {r['status']} but this account has not received the resolution loop.", age_days=0,
            due_date=None, next_action="Record the resolution interaction; do not auto-send."))

    # Stage 11.1 §5.3 — ONE item per campaign whose evidence has gone quiet past its checkpoint.
    # Deliberately narrow: linked tasks and commitments already raise their own items when they go
    # overdue, and a campaign that also raised one per child would double-count the same work and
    # train the operator to skim the queue. The campaign speaks only to what no child record can —
    # the evidence it is measured by has stopped arriving.
    from . import campaigns as _campaigns
    for gap in _campaigns.attention_items(conn):
        items.append(_item(
            "campaign_evidence_gap", "adoption_campaign", gap["campaign_id"],
            gap["scheduled_on"], accounts.get(gap["account_id"], {}),
            title=gap["title"], because=gap["because"],
            age_days=_days_since(gap["scheduled_on"], today) or 0,
            due_date=gap["scheduled_on"], next_action=gap["next_action"]))

    # Stage 13 — a late sequence is one operational problem even when several waves are late.
    # The service derives dates from actual predecessor sends; no scheduler or send action runs.
    from . import adoption_comms as _adoption_comms
    for gap in _adoption_comms.attention_items(conn, today):
        items.append(_item(
            "comms_sequence_overdue", "comms_sequence", gap["sequence_id"],
            gap["updated_at"], accounts.get(gap["account_id"], {}),
            title=gap["title"], because=gap["because"],
            age_days=_days_since(gap["due_on"], today), due_date=gap["due_on"],
            next_action=gap["next_action"]))

    return items


def _item(trigger, object_type, object_id, updated_at, p, *, title, because, age_days, due_date, next_action):
    return {
        "key": f"{trigger}:{object_type}:{object_id}",
        "trigger_type": trigger,
        "priority": PRIORITY[trigger],
        "object_type": object_type,
        "object_id": object_id,
        "_updated_at": updated_at,
        "account_id": p.get("aid"),
        "account_name": p.get("aname"),
        "program_id": p.get("pid"),
        "program_name": p.get("pname"),
        "title": title,
        "because": because,
        "age_days": age_days,
        "due_date": due_date,
        "next_action": next_action,
    }


def build_queue(conn: sqlite3.Connection) -> dict:
    today = _today()
    overlays = _latest_overlays(conn)
    active, snoozed = [], []
    for it in _candidates(conn, today):
        state = _suppressed(overlays.get(it["key"]), it["_updated_at"], today)
        it.pop("_updated_at", None)
        if state is None:
            active.append(it)
        elif state == "snoozed":
            ov = overlays[it["key"]]
            it["snooze_until"] = ov.get("snooze_until")
            it["resurface_condition"] = ov.get("resurface_condition")
            snoozed.append(it)
        # resolved items are omitted entirely (still trackable via audit/overlay)
    active.sort(key=lambda x: (x["priority"], -x["age_days"]))
    return {"as_of": today, "items": active, "snoozed": snoozed, "snoozed_count": len(snoozed)}


# --- overlay mutations ---

def _object_table(object_type: str) -> str:
    return {
        "commitment": "commitments", "risk": "risks", "issue": "issues",
        "milestone": "milestones", "task": "tasks", "capture_inbox_item": "capture_inbox_items",
        "stakeholder_role": "stakeholder_roles", "contract_version": "contract_versions",
        "metric_definition": "metric_definitions", "play_run": "play_runs",
        "signal_episode": "signal_episodes",
        "operational_agreement_event": "operational_agreement_events",
        "checklist_item": "checklist_items", "person": "persons",
        "comm_message": "comm_messages",
        "internal_ask": "internal_asks", "escalation": "escalation_instances",
        "product_feedback_occurrence": "product_feedback_occurrences",
        "adoption_campaign": "adoption_campaigns",
        "comms_sequence": "comms_sequences",
    }[object_type]


def _validate_key(conn: sqlite3.Connection, item_key: str) -> None:
    try:
        _trigger, object_type, object_id = item_key.split(":", 2)
        table = _object_table(object_type)
    except (ValueError, KeyError):
        raise HTTPException(422, f"malformed item_key: {item_key}")
    if not conn.execute(f"SELECT 1 FROM {table} WHERE id=?", (object_id,)).fetchone():
        raise HTTPException(404, f"queue item target not found: {item_key}")


def snooze(conn, *, item_key, snooze_until=None, resurface_condition=None) -> dict:
    if not snooze_until and not resurface_condition:
        raise HTTPException(422, "Snoozing requires a return date or a resurfacing condition.")
    _validate_key(conn, item_key)
    row = {
        "id": new_id(), "item_key": item_key, "state": "snoozed",
        "snooze_until": snooze_until, "resurface_condition": resurface_condition,
        "created_at": now_utc(), "created_by": audit.DEFAULT_ACTOR,
    }
    with conn:
        conn.execute(
            "INSERT INTO attention_state (id,item_key,state,snooze_until,resurface_condition,created_at,created_by) "
            "VALUES (:id,:item_key,:state,:snooze_until,:resurface_condition,:created_at,:created_by)", row,
        )
        audit.record(conn, object_type="attention_state", object_id=row["id"], action="create", after=row)
    return row


def resolve(conn, *, item_key, successor_action_type, successor_action_id) -> dict:
    if not successor_action_id:
        raise HTTPException(422, "Resolving requires a linked successor action (a task or commitment).")
    _validate_key(conn, item_key)
    table = "tasks" if successor_action_type == "task" else "commitments"
    if not conn.execute(f"SELECT 1 FROM {table} WHERE id=?", (successor_action_id,)).fetchone():
        raise HTTPException(404, f"successor {successor_action_type} not found")
    row = {
        "id": new_id(), "item_key": item_key, "state": "resolved",
        "successor_action_type": successor_action_type, "successor_action_id": successor_action_id,
        "created_at": now_utc(), "created_by": audit.DEFAULT_ACTOR,
    }
    with conn:
        conn.execute(
            "INSERT INTO attention_state (id,item_key,state,successor_action_type,successor_action_id,created_at,created_by) "
            "VALUES (:id,:item_key,:state,:successor_action_type,:successor_action_id,:created_at,:created_by)", row,
        )
        audit.record(conn, object_type="attention_state", object_id=row["id"], action="create", after=row)
    return row
