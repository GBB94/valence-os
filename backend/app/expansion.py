"""Whitespace map, value realization ledger, and funding intelligence
(EXPANSION-ENGINE-SPEC.md §§1, 2, 4, 10 — Stage 5.5).

Three rules are enforced here rather than trusted to callers, because each one is a way the
map can lie:

**The counting rule (§1.1).** A seat is one person-license owned by the ROW axis. Base segments
are the only additive dimension; composite views overlap by construction and use cases are
entitlements on a seat, not separate inventories. Every total this module returns is tagged
`additive: true|false` and the non-additive ones carry the reason, so a caller cannot sum
across a row and get a number that triple-counts the same manager.

**Derived cell state (§1.3).** The four facts are stored; the single heatmap state is computed
here under a fixed precedence and is never written. Blocked and Declined come first because
they change what the operator does next, which is what the color is for.

**The cohort privacy floor (§1.2).** Aggregate stops being non-identifying once a composite
narrows far enough. Any cohort-derived value for a population below the account's floor is
suppressed rather than rounded or zeroed, and suppression is applied on the way out of this
module so no caller can route around it.
"""
from __future__ import annotations

import sqlite3
from datetime import date, timedelta

from . import repo
from .db import now_utc

DEFAULT_MIN_COHORT = 25

# --- §1.3 derived state ---------------------------------------------------------------------
# (state, label, the move). Order IS the precedence — first match wins.
STATE_LABELS = {
    "blocked": ("Blocked", "Work the compliance lane, not the sales lane"),
    "declined": ("Declined", "Leave it alone until the reason changes"),
    "penetrated": ("Penetrated", "Protect and harvest stories"),
    "penetrated_unevidenced": ("Penetrated, unevidenced", "Close the evidence gap"),
    "proven": ("Proven", "Package the case, name the budget owner"),
    "target": ("Target", "Run a programmatic wedge to create evidence"),
    "white": ("White", "Prospect the cell: identify the buyer, build the relationship"),
}


def derive_state(cell: dict) -> str:
    """The single heatmap state, computed from the four stored facts. Never stored.

    Precedence is deliberate: a paid, evidenced cell that is ALSO gated shows Blocked, because
    the next action is the compliance lane. The cell card still shows all four facts, so nothing
    is hidden by the precedence — only the one-glance summary is opinionated.
    """
    if cell["blocker_state"] == "gated":
        return "blocked"
    if cell["pursuit_outcome"] == "declined" and not cell.get("reopened_on"):
        return "declined"
    paid = cell["penetration"] == "paid"
    if paid:
        # The state v1's six-state model could not express, and the one the ledger exists for.
        return "penetrated" if cell["evidence_state"] == "measured" else "penetrated_unevidenced"
    if cell["evidence_state"] in ("anecdotal", "measured"):
        return "proven"
    if cell.get("sponsor_person_id"):
        return "target"
    return "white"


def min_cohort_size(conn: sqlite3.Connection, account_id: str) -> int:
    row = conn.execute("SELECT min_cohort_size FROM account_settings WHERE account_id=?",
                       (account_id,)).fetchone()
    return row["min_cohort_size"] if row else DEFAULT_MIN_COHORT


def active_partition(conn: sqlite3.Connection, account_id: str) -> dict | None:
    return repo.row_to_dict(conn.execute(
        "SELECT * FROM population_partitions WHERE account_id=? AND status='active'",
        (account_id,)).fetchone())


def active_segments(conn: sqlite3.Connection, account_id: str, include_unallocated: bool = True) -> list[dict]:
    """Segments of the account's ACTIVE partition only.

    Querying `population_segments WHERE account_id=?` looks equivalent and is not: superseding a
    partition leaves its old segments in the table by design (history), so an account-wide query
    returns the union of every generation. That made a re-based account report 1,100 addressable
    seats against a 1,000-FTE partition — exactly the over-count §1.1 exists to prevent, produced
    by the very versioning that was supposed to make re-basing clean.
    """
    part = active_partition(conn, account_id)
    if not part:
        return []
    where = "partition_id=?" + ("" if include_unallocated else " AND is_unallocated=0")
    return repo.list_rows(conn, "population_segments",
                          where=where + " ORDER BY is_unallocated, display_order, name",
                          params=(part["id"],))


def _sub_floor_populations(conn: sqlite3.Connection, account_id: str) -> set[str]:
    """Segment and view ids whose population is below the account's minimum cohort size.

    Used to gate METRIC-derived values (§1.2). The distinction that matters: a metric
    observation is behavioural data about the people in a cohort — "0.8 activation" over ten
    identifiable colleagues tells you about individuals. Seats sold and headcount are
    commercial facts about licences and are not gated; see `_suppressed` for why the density
    rule is a display convention rather than a second privacy control.
    """
    floor = min_cohort_size(conn, account_id)
    out = set()
    for s in repo.list_rows(conn, "population_segments", where="account_id=?", params=(account_id,)):
        if s["headcount"] is not None and s["headcount"] < floor:
            out.add(s["id"])
    for v in repo.list_rows(conn, "population_views", where="account_id=?", params=(account_id,)):
        if v["estimated_headcount"] is not None and v["estimated_headcount"] < floor:
            out.add(v["id"])
    return out


def _suppressed(value, headcount: int | None, floor: int) -> dict:
    """Below the floor a penetration rate is suppressed, never zeroed or rounded.

    Honest about what this is: a DISPLAY convention, not a privacy control. Density is
    paid_seats / headcount and both operands are commercial facts the operator legitimately
    sees, so anyone can recompute it — a review pointed this out and was right. What it does
    buy is not implying a precise rate over ten people. The actual privacy control is
    `_sub_floor_populations`, which gates metric-derived (behavioural) values in the ledger.

    Returned as a dict so the UI renders the existing cross-hatched unknown treatment with a
    reason, rather than receiving a bare number it cannot tell apart from a real one.
    """
    if headcount is not None and headcount < floor:
        return {"value": None, "suppressed": True, "reason": f"cohort below {floor}"}
    return {"value": value, "suppressed": False, "reason": None}


# --- §1.1 the map ----------------------------------------------------------------------------
def _row_label(seg: dict | None, view: dict | None) -> str:
    return (seg or view)["name"]


def whitespace_map(conn: sqlite3.Connection, account_id: str) -> dict:
    """The Commercial tab's signature surface, assembled with the counting rule attached.

    Returns segment rows (additive) and view rows (non-additive) separately rather than in one
    undifferentiated list, because the difference is the whole point and a flat list invites
    exactly the summing error the rule exists to prevent.
    """
    repo.get_row(conn, "accounts", account_id)
    floor = min_cohort_size(conn, account_id)
    today = now_utc()[:10]

    partition = active_partition(conn, account_id)
    segments = active_segments(conn, account_id)
    views = repo.list_rows(conn, "population_views", where="account_id=? ORDER BY name",
                           params=(account_id,))
    # Global use cases plus this account's own; account-specific ones are marked non-comparable
    # so §11's cross-account matching can exclude them out loud rather than silently.
    use_cases = repo.list_rows(
        conn, "use_cases",
        where="(account_id IS NULL OR account_id=?) ORDER BY display_order, name",
        params=(account_id,))
    for uc in use_cases:
        uc["portfolio_comparable"] = uc["account_id"] is None

    cells = repo.list_rows(conn, "whitespace_cells", where="account_id=?", params=(account_id,))
    by_key = {}
    for c in cells:
        c["state"] = derive_state(c)
        c["state_label"], c["state_move"] = STATE_LABELS[c["state"]]
        by_key[(c["segment_id"], c["view_id"], c["use_case_id"])] = c

    def build_row(seg, view):
        headcount = seg["headcount"] if seg else view["estimated_headcount"]
        row_cells = []
        for uc in use_cases:
            c = by_key.get((seg["id"] if seg else None, view["id"] if view else None, uc["id"]))
            if c:
                c = {**c, "paid_density": _suppressed(
                    round(c["paid_seats"] / headcount, 4) if headcount else None, headcount, floor)}
            row_cells.append({"use_case_id": uc["id"], "use_case": uc["name"], "cell": c})
        paid = sum(c["cell"]["paid_seats"] for c in row_cells if c["cell"])
        return {
            "row_type": "segment" if seg else "view",
            "id": (seg or view)["id"],
            "name": _row_label(seg, view),
            "headcount": headcount,
            "headcount_source": (seg or view).get("headcount_source"),
            "headcount_as_of": (seg or view).get("headcount_as_of"),
            "is_unallocated": bool(seg["is_unallocated"]) if seg else False,
            # A seat is owned by the row, so max-across-cells is the honest paid figure for the
            # row; summing would count a person once per use case they are lit for.
            "paid_seats": max((c["cell"]["paid_seats"] for c in row_cells if c["cell"]), default=0),
            "paid_seats_sum_across_use_cases": paid,
            "paid_seats_note": "Row paid seats is the max across use cases, not the sum: "
                               "use cases are entitlements on a seat, not separate inventories.",
            "cells": row_cells,
        }

    segment_rows = [build_row(s, None) for s in segments]
    view_rows = [build_row(None, v) for v in views]

    # Reconciliation (§1.1): the visible unallocated remainder is what stops the map claiming
    # more addressable seats than the company has people.
    allocated = sum(s["headcount"] or 0 for s in segments if not s["is_unallocated"])
    unallocated_row = next((s for s in segments if s["is_unallocated"]), None)
    total_fte = partition["total_fte"] if partition else None
    reconciliation = {
        "total_fte": total_fte,
        "allocated_headcount": allocated,
        "unallocated_headcount": (unallocated_row or {}).get("headcount"),
        "remainder": (total_fte - allocated) if total_fte is not None else None,
        "reconciles": (total_fte is not None
                       and allocated + ((unallocated_row or {}).get("headcount") or 0) == total_fte),
    }

    return {
        "account_id": account_id,
        "partition": partition,
        "use_cases": use_cases,
        "segment_rows": segment_rows,
        "view_rows": view_rows,
        "reconciliation": reconciliation,
        "rollup": rollup(conn, account_id),
        "min_cohort_size": floor,
        "counting_rule": {
            "seat_definition": "One person-license, owned by the row axis.",
            "additive_dimension": "population_segments (the base partition) only.",
            "non_additive": ["population_views (composites overlap by construction)",
                             "seat estimates across a row (use cases are entitlements, not inventories)"],
        },
        "stamp": {"generated_at": now_utc(), "data_current_through": today},
    }


def rollup(conn: sqlite3.Connection, account_id: str) -> dict:
    """The account thesis in one number: addressable vs paid, by state.

    Computed over SEGMENT cells only. Composite views are excluded from every total here — not
    filtered out quietly, but reported in `excluded_view_cells` so the omission is visible.
    """
    # Only cells on the ACTIVE partition's segments count; cells left behind by a superseded
    # partition are history, not addressable inventory.
    live = {s["id"] for s in active_segments(conn, account_id)}
    cells = repo.list_rows(conn, "whitespace_cells", where="account_id=?", params=(account_id,))
    segment_cells = [c for c in cells if c["segment_id"] in live]
    by_state: dict[str, dict] = {}
    for c in segment_cells:
        s = derive_state(c)
        b = by_state.setdefault(s, {"state": s, "label": STATE_LABELS[s][0], "cells": 0, "paid_seats": 0})
        b["cells"] += 1
        b["paid_seats"] += c["paid_seats"]

    segments = [s for s in active_segments(conn, account_id, include_unallocated=False)]
    # Addressable is a ROW total (headcount per segment), never a sum of cell estimates.
    addressable = sum(s["headcount"] or 0 for s in segments)
    paid_by_segment = {}
    for c in segment_cells:
        paid_by_segment[c["segment_id"]] = max(paid_by_segment.get(c["segment_id"], 0), c["paid_seats"])
    paid = sum(paid_by_segment.values())

    return {
        "addressable_seats": addressable,
        "paid_seats": paid,
        "unpenetrated_seats": max(addressable - paid, 0),
        "by_state": sorted(by_state.values(), key=lambda x: -x["cells"]),
        "excluded_view_cells": len(cells) - len(segment_cells),
        "additive": True,
        "basis": "Segment rows only; paid seats taken as the max across use cases per segment.",
    }


def next_seats(conn: sqlite3.Connection, account_id: str, limit: int = 10) -> dict:
    """"Where do the next 2,000 seats live?" — answered from the ROW axis (§1.1).

    Ranked by unpenetrated headcount per segment. The columns tell you the motion, not the
    count, so each row also carries its best-shaped use case rather than a seat number per cell.
    """
    segments = [s for s in active_segments(conn, account_id, include_unallocated=False)]
    cells = repo.list_rows(conn, "whitespace_cells", where="account_id=? AND segment_id IS NOT NULL",
                           params=(account_id,))
    use_cases = {u["id"]: u["name"] for u in repo.list_rows(conn, "use_cases", where="1=1")}
    by_segment: dict[str, list] = {}
    for c in cells:
        by_segment.setdefault(c["segment_id"], []).append(c)

    # Motion priority: the nearest thing to funded evidence is the cheapest next move.
    order = ["proven", "penetrated_unevidenced", "target", "white", "blocked", "declined", "penetrated"]
    rows = []
    for s in segments:
        scs = by_segment.get(s["id"], [])
        paid = max((c["paid_seats"] for c in scs), default=0)
        gap = (s["headcount"] or 0) - paid
        if gap <= 0:
            continue
        ranked = sorted(scs, key=lambda c: order.index(derive_state(c)))
        best = ranked[0] if ranked else None
        rows.append({
            "segment_id": s["id"], "segment": s["name"],
            "headcount": s["headcount"], "paid_seats": paid, "unpenetrated_seats": gap,
            "headcount_source": s["headcount_source"], "headcount_as_of": s["headcount_as_of"],
            "best_motion": ({"use_case": use_cases.get(best["use_case_id"]),
                             "state": derive_state(best),
                             "move": STATE_LABELS[derive_state(best)][1]} if best else None),
        })
    rows.sort(key=lambda r: -r["unpenetrated_seats"])
    return {"account_id": account_id, "rows": rows[:limit],
            "total_unpenetrated": sum(r["unpenetrated_seats"] for r in rows),
            "additive": True,
            "basis": "Row axis only. Use cases indicate the motion, not additional seats."}


# --- §2 the value realization ledger ----------------------------------------------------------
def target_realization(conn: sqlite3.Connection, target: dict) -> dict:
    """Realized / on track / at risk / not demonstrated — derived, never stored.

    Freshness governs: past the definition's staleness threshold the status is `unknown`, not a
    carried-forward good state. That is the same rule the scoreboard and QBR already follow.
    """
    today = now_utc()[:10]
    definition = repo.get_row(conn, "metric_definitions", target["definition_id"])

    # Metric definitions are global; observations are not. An account-wide target (no segment,
    # no view) must still be bounded by THIS account, or it silently reads whichever account
    # reported that definition most recently — the same defect fixed in the QBR (D-82) and
    # reintroduced here by scoping the population but forgetting the account.
    account_id = target["account_id"]
    population_id = target["segment_id"] or target["view_id"]
    if population_id and population_id in _sub_floor_populations(conn, account_id):
        # The real privacy control: a metric over a sub-floor cohort is behavioural data about
        # a handful of identifiable people, so its value never leaves this module.
        return {"status": "suppressed", "value": None, "current_through": None, "stale": False,
                "reason": f"cohort below the account's minimum of {min_cohort_size(conn, account_id)}"}

    where = "archived=0 AND definition_id=?"
    params: list = [target["definition_id"]]
    if target["segment_id"]:
        where += " AND population_segment_id=?"
        params.append(target["segment_id"])
    elif target["view_id"]:
        where += " AND population_view_id=?"
        params.append(target["view_id"])
    else:
        seg_ids = [s["id"] for s in repo.list_rows(
            conn, "population_segments", where="account_id=?", params=(account_id,))]
        prog_ids = [p["id"] for p in repo.list_rows(
            conn, "programs", where="account_id=?", params=(account_id,))]
        if not seg_ids and not prog_ids:
            return {"status": "not_demonstrated", "value": None, "current_through": None,
                    "stale": True, "reason": "no observation for this account"}
        clauses, extra = [], []
        if seg_ids:
            clauses.append(f"population_segment_id IN ({','.join('?' * len(seg_ids))})")
            extra += seg_ids
        if prog_ids:
            clauses.append(f"program_id IN ({','.join('?' * len(prog_ids))})")
            extra += prog_ids
        where += " AND (" + " OR ".join(clauses) + ")"
        params += extra

    obs = conn.execute(
        f"SELECT * FROM metric_observations WHERE {where} ORDER BY current_through DESC LIMIT 1",
        params).fetchone()

    if not obs:
        return {"status": "not_demonstrated", "value": None, "current_through": None,
                "stale": True, "reason": "no observation for this population"}

    obs = repo.row_to_dict(obs)
    stale = True
    if obs["current_through"]:
        try:
            stale = (date.fromisoformat(today)
                     - date.fromisoformat(obs["current_through"])).days > definition["stale_after_days"]
        except ValueError:
            stale = True
    if stale:
        return {"status": "unknown", "value": None, "current_through": obs["current_through"],
                "stale": True, "reason": "observation past its freshness threshold"}

    met = (obs["value"] >= target["target_value"] if target["direction"] == "at_least"
           else obs["value"] <= target["target_value"])
    past_due = bool(target["timeframe_end"] and target["timeframe_end"] < today)
    if met:
        status = "realized"
    elif past_due:
        status = "not_demonstrated"
    else:
        # Inside the window: on track if within 20% of the bar, otherwise at risk. A crude
        # split on purpose — a precise-looking projection over a handful of observations
        # would imply a confidence the data does not carry.
        ratio = (obs["value"] / target["target_value"]) if target["target_value"] else 0
        near = ratio >= 0.8 if target["direction"] == "at_least" else ratio <= 1.2
        status = "on_track" if near else "at_risk"
    return {"status": status, "value": obs["value"], "current_through": obs["current_through"],
            "stale": False, "past_due": past_due, "reason": None}


def ledger(conn: sqlite3.Connection, account_id: str) -> dict:
    """The account's promised-vs-realized picture, plus the value gaps it implies."""
    repo.get_row(conn, "accounts", account_id)
    targets = repo.list_rows(conn, "value_targets",
                             where="account_id=? AND status='active' ORDER BY timeframe_end",
                             params=(account_id,))
    definitions = {d["id"]: d for d in repo.list_rows(conn, "metric_definitions", where="1=1")}
    names = {p["id"]: p["name"] for p in repo.list_rows(conn, "persons", where="1=1")}
    segments = {s["id"]: s["name"] for s in repo.list_rows(conn, "population_segments", where="1=1")}
    views = {v["id"]: v["name"] for v in repo.list_rows(conn, "population_views", where="1=1")}

    rows = []
    for t in targets:
        rows.append({
            **t,
            "metric": definitions.get(t["definition_id"], {}).get("name"),
            "population": segments.get(t["segment_id"]) or views.get(t["view_id"]) or "Account-wide",
            "accepted_by_name": names.get(t["accepted_by_person_id"]),
            "realization": target_realization(conn, t),
        })

    counts: dict[str, int] = {}
    for r in rows:
        counts[r["realization"]["status"]] = counts.get(r["realization"]["status"], 0) + 1

    return {
        "account_id": account_id, "targets": rows,
        # Counts, not rates (§10) — a percentage over a handful of targets implies precision
        # the sample does not support.
        "counts": counts, "total": len(rows),
        "value_gaps": value_gaps(conn, account_id),
        "stamp": {"generated_at": now_utc(), "data_current_through": now_utc()[:10]},
    }


def value_gaps(conn: sqlite3.Connection, account_id: str) -> list[dict]:
    """§2 — the dangerous state: paid and active, with nothing demonstrated.

    This is the same condition as derived state `penetrated_unevidenced` (§1.3), computed once
    here and surfaced in both the ledger and the map so the two can never disagree.
    """
    cells = repo.list_rows(conn, "whitespace_cells", where="account_id=?", params=(account_id,))
    segments = {s["id"]: s["name"] for s in repo.list_rows(conn, "population_segments", where="1=1")}
    views = {v["id"]: v["name"] for v in repo.list_rows(conn, "population_views", where="1=1")}
    use_cases = {u["id"]: u["name"] for u in repo.list_rows(conn, "use_cases", where="1=1")}
    today = now_utc()[:10]

    gaps = []
    for c in cells:
        if derive_state(c) != "penetrated_unevidenced":
            continue
        population = segments.get(c["segment_id"]) or views.get(c["view_id"])
        overdue = conn.execute(
            "SELECT COUNT(*) n FROM value_targets WHERE archived=0 AND status='active' "
            "AND account_id=? AND timeframe_end < ? AND (segment_id=? OR view_id=?)",
            (account_id, today, c["segment_id"], c["view_id"])).fetchone()["n"]
        gaps.append({
            "cell_id": c["id"], "population": population,
            "use_case": use_cases.get(c["use_case_id"]),
            "paid_seats": c["paid_seats"],
            "overdue_targets": overdue,
            "because": f"{c['paid_seats']} paid seats in {population} for "
                       f"{use_cases.get(c['use_case_id'])}, with no measured evidence"
                       + (f" and {overdue} target(s) past their timeframe" if overdue else ""),
        })
    return sorted(gaps, key=lambda g: (-g["overdue_targets"], -g["paid_seats"]))


# --- §4 funding intelligence -------------------------------------------------------------------
# Back-scheduling offsets in days before the target close date. Defaults, not benchmarks: the
# fiscal map overrides procurement and works-council lead times with the account's real ones.
_ASK_STEPS = [
    ("business_case_delivered", "Business case delivered", 120),
    ("budget_owner_sponsorship", "Budget owner sponsorship secured", 100),
    ("budget_window", "Budget request submitted in planning window", 80),
    ("procurement", "Procurement process started", 55),
    ("works_council", "Works council consultation", 40),
    ("signature", "Signature", 0),
]


def back_schedule(conn: sqlite3.Connection, account_id: str, target_close: str,
                  include_works_council: bool = True) -> list[dict]:
    """Work backwards from a close date to every step and its deadline (§4).

    "An ask that misses the planning window slips a full cycle; the tool's job is to make that
    impossible to discover late." Lead times come from the account's fiscal map and contract
    where present, so this is the account's calendar rather than a generic one.
    """
    fm = repo.row_to_dict(conn.execute(
        "SELECT * FROM fiscal_maps WHERE account_id=?", (account_id,)).fetchone()) or {}
    procurement_days = None
    if fm.get("procurement_lead_contract_id"):
        cv = conn.execute("SELECT procurement_lead_days FROM contract_versions WHERE id=?",
                          (fm["procurement_lead_contract_id"],)).fetchone()
        procurement_days = cv["procurement_lead_days"] if cv else None

    close = date.fromisoformat(target_close)
    steps = []
    for order, (kind, label, default_offset) in enumerate(_ASK_STEPS):
        if kind == "works_council" and not include_works_council:
            continue
        offset = default_offset
        source = "default"
        due = None
        if kind == "procurement" and procurement_days:
            offset, source = procurement_days, "contract"
        if kind == "works_council" and fm.get("works_council_lead_days"):
            offset, source = fm["works_council_lead_days"], "fiscal_map"
        if kind == "budget_window":
            # The budget request is not a lead time, it is a DATE the client's finance calendar
            # fixes: miss the window and the ask slips a full cycle. Back-scheduling off a
            # generic 80-day offset ignored the deadline the operator had already recorded,
            # which is precisely the "discover it late" failure §4 exists to prevent.
            due = _last_deadline_before(fm.get("budget_request_deadline")
                                        or fm.get("planning_window_end"), close)
            if due:
                source = "fiscal_map"
        if due is None:
            due = (close - timedelta(days=offset)).isoformat()
        steps.append({"kind": kind, "label": label, "due_date": due,
                      "lead_days": offset, "lead_source": source, "display_order": order})
    return steps


def _last_deadline_before(month_day: str | None, close: date) -> str | None:
    """Turn an MM-DD finance deadline into the latest actual date on or before the close.

    The fiscal map stores month-day because the window recurs annually; the ask needs the
    concrete occurrence that still precedes this close date.
    """
    if not month_day:
        return None
    try:
        month, day = (int(x) for x in month_day.split("-"))
    except (ValueError, AttributeError):
        return None
    for year in (close.year, close.year - 1):
        try:
            candidate = date(year, month, day)
        except ValueError:
            return None
        if candidate <= close:
            return candidate.isoformat()
    return None


def ask_calendar_status(conn: sqlite3.Connection, calendar_id: str) -> dict:
    """A calendar with its steps, each marked late against today so nothing slips quietly."""
    cal = repo.get_row(conn, "ask_calendars", calendar_id)
    today = now_utc()[:10]
    steps = [repo.row_to_dict(r) for r in conn.execute(
        "SELECT * FROM ask_calendar_steps WHERE calendar_id=? ORDER BY display_order, due_date",
        (calendar_id,))]
    names = {p["id"]: p["name"] for p in repo.list_rows(conn, "persons", where="1=1")}
    late = 0
    for s in steps:
        s["owner_name"] = names.get(s["owner_person_id"])
        s["derived_late"] = s["status"] == "pending" and s["due_date"] < today
        if s["derived_late"]:
            late += 1
    return {**cal, "steps": steps, "late_steps": late,
            "next_step": next((s for s in steps if s["status"] == "pending"), None)}


def funding_view(conn: sqlite3.Connection, account_id: str) -> dict:
    """Pools, the fiscal map with its freshness, and every live ask calendar (§4)."""
    repo.get_row(conn, "accounts", account_id)
    names = {p["id"]: p["name"] for p in repo.list_rows(conn, "persons", where="1=1")}
    pools = repo.list_rows(conn, "funding_pools", where="account_id=? ORDER BY status, name",
                           params=(account_id,))
    for p in pools:
        p["owner_name"] = names.get(p["owner_person_id"])
    fm = repo.row_to_dict(conn.execute("SELECT * FROM fiscal_maps WHERE account_id=?",
                                       (account_id,)).fetchone())
    calendars = [ask_calendar_status(conn, c["id"]) for c in repo.list_rows(
        conn, "ask_calendars", where="account_id=? AND status='active' ORDER BY target_close_date",
        params=(account_id,))]
    return {"account_id": account_id, "funding_pools": pools, "fiscal_map": fm,
            "ask_calendars": calendars,
            "late_steps_total": sum(c["late_steps"] for c in calendars),
            "stamp": {"generated_at": now_utc(), "data_current_through": now_utc()[:10]}}


# --- §10 revenue, reported as counts ------------------------------------------------------------
def revenue_movement(conn: sqlite3.Connection, account_id: str, since: str | None = None) -> dict:
    """Net revenue movement for one account, stated in absolutes with its denominator.

    Deliberately NOT a blended portfolio NRR percentage: with five accounts a rate implies a
    precision the sample cannot carry and invites comparisons it cannot survive (§10). The
    caller gets base ARR, the signed movement by kind, and the account count behind it.
    """
    repo.get_row(conn, "accounts", account_id)
    where = "account_id=?"
    params: list = [account_id]
    if since:
        where += " AND effective_on >= ?"
        params.append(since)
    events = repo.list_rows(conn, "revenue_events", where=f"{where} ORDER BY effective_on", params=tuple(params))

    contract = repo.row_to_dict(conn.execute(
        "SELECT * FROM contract_versions WHERE account_id=? AND is_current=1 AND archived=0 "
        "ORDER BY start_date DESC LIMIT 1", (account_id,)).fetchone())

    by_kind: dict[str, float] = {}
    for e in events:
        by_kind[e["kind"]] = by_kind.get(e["kind"], 0.0) + (e["amount"] or 0.0)

    base = (contract or {}).get("derived_arr")
    movement = sum(by_kind.values())
    return {
        "account_id": account_id,
        "base_arr": base,
        "currency": (contract or {}).get("currency"),
        "price_basis": (contract or {}).get("price_basis"),
        "movement_by_kind": by_kind,
        "net_movement": movement,
        "ending_arr": (base + movement) if base is not None else None,
        "event_count": len(events),
        "insufficient_data": base is None or not events,
        "note": "Absolute movement with its base, not a blended rate: one account is not a "
                "population (§10).",
    }
