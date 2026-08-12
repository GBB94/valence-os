"""Stage 17 Slice 2 — the monthly fold and the four-axis reading (`SURFACE-USAGE-SPEC.md` §6, §9.4).

Two halves, deliberately separate.

**The fold** turns raw `product_events` into `surface_usage_months`. It is incremental and monotone
over `product_events.rowid` rather than a recompute over the raw window, because a recompute would
lower a month's counts as that month aged past the 90-day purge — and a rollup that shrinks on its
own is worse than none: the number an operator wrote a retirement note against would stop matching
the table it came from.

**The reading** is §6's four axes, which never combine. There is no usage score, and there is no
name for one; `test_surface_usage.py` asserts that no field, column, or CSS class in this feature is
called `score`, `rating`, `health`, or `usage_index`. A single number would be read as a kill order,
and the data cannot support that reading.

The one rule here that is easy to lose and expensive to lose is §6.2's **window coverage**. A window
covers a surface when it contains at least two of that surface's expected occurrences — two rather
than one, because a single expected occurrence that did not happen is indistinguishable from a week
you were away. When the window does not cover the cadence, the surface reports `insufficient_window`
and *nothing else is claimed*. That is the same move as withholding a stale `met` rather than
showing it as `Complete` (D-151…D-155): a reading with no honest basis is withheld, never softened
into the nearest available one.

A dismissal is not an engagement and is not folded into `engaged` (D-287). It is evidence the
surface was seen and rejected, which *reinforces* `rendered_not_engaged` rather than contradicting
it; counting it as engagement would let the clutter case score as use.

This module reads `product_events` and is therefore named in the §17.1 allowlist beside
`telemetry.py`. Nothing in the domain may import it, and it imports nothing from the domain.
"""
from __future__ import annotations

import sqlite3
from calendar import monthrange
from datetime import date, timedelta

# `surface_retirement` imports this module lazily, inside `preview`, precisely so this direction
# can be a plain top-level import: the §6.1 fourth axis is a *reading* of what an operator recorded,
# so the report joins it rather than deriving a second copy of the same latest-note query.
from . import surface_retirement, surface_triggers, surfaces
from .db import now_utc

# §6.3's four observations. Mutually exclusive; `insufficient_window` wins over all of them.
OBSERVATIONS = ("engaged", "rendered_not_engaged", "not_rendered", "insufficient_window")

# The §8 caveat, authored here and rendered beside the numbers rather than in a tooltip. It is on
# the server for the reason every refusal sentence in this repo is (D-151…D-155): a view that
# composes part of a caution can soften one, and this is the caution that stops the table being
# read as a kill list.
CAVEAT = (
    "These counts describe exposure and engagement on your own screen. They cannot say whether a "
    "surface is valuable — a low count can mean it was never found, was misunderstood, or is "
    "rarely relevant and essential when it is. Record a cause before changing anything."
)

# What each observation means and what it argues for. Server-authored for the same reason, and
# because the middle two are the pair most likely to be collapsed by a reader in a hurry: the
# distinction between them is the entire practical value of separating render from engage.
OBSERVATION_COPY = {
    "engaged": {
        "label": "Engaged",
        "meaning": "Operated at least once in a covered window.",
        "suggests": "Nothing.",
    },
    "rendered_not_engaged": {
        "label": "Shown, never operated",
        "meaning": "Displayed repeatedly and never operated in a covered window.",
        # §6.3's clutter case: it costs screen every time and returns nothing.
        "suggests": "The clutter case. It costs you screen every time and returns nothing.",
    },
    "not_rendered": {
        "label": "Never displayed",
        "meaning": "Never displayed at all in a covered window.",
        # Explicitly the weaker signal. Removing it would be removing something never seen.
        "suggests": ("The reachability case — a navigation or entry-point problem, not a value "
                     "one. This is a weaker argument for removal than the clutter case, not a "
                     "stronger one: try making it more prominent first."),
    },
    "insufficient_window": {
        "label": "Not yet knowable",
        "meaning": "The observation window is too short to cover this surface's cadence.",
        "suggests": "Wait, or observe it against its trigger.",
    },
}


# --- the fold ---------------------------------------------------------------------------------

def _month_of(occurred_at: str) -> str:
    return (occurred_at or "")[:7]


def _day_of(occurred_at: str) -> str:
    return (occurred_at or "")[:10]


def fold(conn: sqlite3.Connection) -> dict:
    """Advance the rollup over every raw event above the watermark. Idempotent.

    Returns `{"folded": n, "watermark": rowid, "surfaces": k}`.

    The watermark means **every row up to here has been offered to the fold**, not "the last row
    the fold used". Those differ whenever the newest events are not surface events, which is most
    of the time — fourteen of the sixteen event names are read in neither column. Under the older
    reading the watermark sat behind a run of `path_viewed` rows forever, and `purge_expired`
    cannot use a mark that lags for reasons unrelated to whether anything was folded. So the
    ceiling is taken over the whole table, and the scan is bounded to it rather than to "now": a
    row inserted mid-scan is above the ceiling and waits for the next pass instead of being marked
    folded without having been read.
    """
    row = conn.execute(
        "SELECT surface_rollup_watermark FROM product_telemetry_settings WHERE id='singleton'"
    ).fetchone()
    watermark = int(row[0]) if row else 0
    ceiling = int(conn.execute(
        "SELECT COALESCE(MAX(rowid), ?) FROM product_events", (watermark,)).fetchone()[0])

    # Only the two events that carry a surface and mean exposure or operation. `surface_dismissed`
    # is read in neither column on purpose (D-287).
    events = conn.execute(
        "SELECT rowid, event_name, occurred_at, "
        "json_extract(properties_json,'$.surface') AS surface_key "
        "FROM product_events "
        "WHERE rowid > ? AND rowid <= ? AND event_name IN ('surface_rendered','surface_engaged') "
        "ORDER BY rowid", (watermark, ceiling)).fetchall()

    highest = max(watermark, ceiling)
    buckets: dict[tuple[str, str], dict] = {}
    for event in events:
        key = event["surface_key"]
        # An unregistered slug cannot reach the sink (§5), but a row written before a surface was
        # renamed can survive one. It is dropped from the rollup rather than given a row, because a
        # rollup row for a surface that does not exist is a line in the report nobody can act on.
        if not key or not surfaces.is_surface(key):
            continue
        month = _month_of(event["occurred_at"])
        if len(month) != 7:
            continue
        bucket = buckets.setdefault((key, month), {"rendered": 0, "engaged": 0, "last": None})
        if event["event_name"] == "surface_rendered":
            bucket["rendered"] += 1
        else:
            bucket["engaged"] += 1
            day = _day_of(event["occurred_at"])
            if bucket["last"] is None or day > bucket["last"]:
                bucket["last"] = day

    stamp = now_utc()
    with conn:
        for (key, month), bucket in buckets.items():
            conn.execute(
                "INSERT INTO surface_usage_months "
                "(id,surface_key,month,rendered,engaged,last_engaged_on,updated_at) "
                "VALUES (?,?,?,?,?,?,?) "
                "ON CONFLICT(surface_key,month) DO UPDATE SET "
                "  rendered = rendered + excluded.rendered,"
                "  engaged = engaged + excluded.engaged,"
                # MAX over the stored value, because the fold adds to what is there and a later
                # batch can contain an earlier day than one already recorded. The NULLIF is not
                # tidying: MAX('','') is '', which fails the column's CHECK *inside this statement*
                # — so the ordinary case of more renders landing on an already-folded month with no
                # engagement in either batch aborted the whole fold. Normalising afterwards cannot
                # reach it, because there is no afterwards.
                "  last_engaged_on = NULLIF(MAX(COALESCE(last_engaged_on,''),"
                "                               COALESCE(excluded.last_engaged_on,'')), ''),"
                "  updated_at = excluded.updated_at",
                (f"{key}:{month}", key, month, bucket["rendered"], bucket["engaged"],
                 bucket["last"], stamp))
        conn.execute("UPDATE product_telemetry_settings SET surface_rollup_watermark=? "
                     "WHERE id='singleton'", (highest,))
    return {"folded": len(events), "watermark": highest, "surfaces": len(buckets)}


def purge_expired_rollups(conn: sqlite3.Connection, months: int | None = None) -> int:
    """§9.4's 36-month retention. Whole months, so a partial month is never half-counted."""
    if months is None:
        row = conn.execute("SELECT rollup_retention_months FROM product_telemetry_settings "
                           "WHERE id='singleton'").fetchone()
        months = int(row[0]) if row else 36
    cutoff = conn.execute("SELECT strftime('%Y-%m', 'now', ?)",
                          (f"-{int(months)} months",)).fetchone()[0]
    with conn:
        cursor = conn.execute("DELETE FROM surface_usage_months WHERE month < ?", (cutoff,))
    return cursor.rowcount or 0


# --- the reading ------------------------------------------------------------------------------

def _today(today: str | None) -> date:
    if today:
        return date.fromisoformat(today[:10])
    return date.fromisoformat(now_utc()[:10])


def observation_window(conn: sqlite3.Connection, *, today: str | None = None,
                       window_days: int | None = None) -> dict:
    """The window every reading is made against, and how long it has actually been observing.

    `observed_days` is bounded by `measuring_since` rather than by the earliest surviving row.
    Inferring the start from the data would make a quiet month look like a short window — the exact
    inversion of §6.2, which exists to stop a short window being read as a quiet one.
    """
    end = _today(today)
    row = conn.execute("SELECT enabled, measuring_since FROM product_telemetry_settings "
                       "WHERE id='singleton'").fetchone()
    since = (row["measuring_since"] or "")[:10] if row else ""
    started = date.fromisoformat(since) if len(since) == 10 else None

    requested = int(window_days) if window_days else None
    if requested is not None:
        start = end - timedelta(days=requested)
        if started and started > start:
            start = started
    else:
        start = started or end

    observed = max((end - start).days, 0)
    return {
        "from": start.isoformat(),
        "to": end.isoformat(),
        "observed_days": observed,
        # §9.1: stated prominently so a period known to be a build week can be discounted.
        "measuring_since": started.isoformat() if started else None,
        "measurement_enabled": bool(row["enabled"]) if row else False,
        "requested_window_days": requested,
    }


def _insufficient_sentence(surface, observed_days: int, required: int | None) -> str:
    """The §6.2 sentence, authored here. It names both numbers so the claim is checkable."""
    if required is None:
        return (f"{surface.label} has no schedule, so elapsed time says nothing about it. It is "
                f"observed against its trigger instead, and no trigger count is available yet.")
    return (f"Observed for {observed_days} days; a {surface.cadence} surface needs {required} "
            f"before this says anything.")


def _observe(surface, *, rendered: int, engaged: int, observed_days: int,
             trigger: dict | None = None) -> tuple[str, str | None]:
    """§6.3's four observations, in the one place they are decided.

    `insufficient_window` wins over all of them, and it wins *before* the counts are looked at —
    otherwise a covered-looking zero would slip through on a surface whose window cannot support the
    claim, which is the confident lie §6.2 names.

    §6.4 changes *which* coverage question is asked, never which observations exist. A surface with
    no schedule is covered by its trigger count instead of by elapsed days; once covered, it is read
    from `rendered` and `engaged` exactly like every other surface. The trigger count is never
    compared with either of them — that comparison would be the composite §12 forbids, and it would
    read as a compliance figure rather than as evidence about whether the surface is any use.
    """
    # A wrapper can prove that the surface was exposed without proving that any of its meaningful
    # operations emit `surface_engaged`. In that state a zero is an instrumentation gap, not disuse.
    # Refuse before reading the counters, exactly as a short observation window does.
    if surface.instrumented is not True:
        return "insufficient_window", str(surface.instrumented)

    required = surfaces.window_days(surface.cadence)
    if required is None:
        if trigger and trigger.get("covered"):
            pass  # Covered by its trigger. Fall through to the same three readings.
        elif trigger is not None:
            return "insufficient_window", surface_triggers.sentence(surface, trigger)
        else:
            return "insufficient_window", _insufficient_sentence(surface, observed_days, None)
    elif observed_days < required:
        return "insufficient_window", _insufficient_sentence(surface, observed_days, required)
    if engaged > 0:
        return "engaged", None
    if rendered > 0:
        return "rendered_not_engaged", None
    return "not_rendered", None


def _partial_months(start: str, end: str) -> dict:
    """Which months `_rollup_rows` actually sums, and how far they reach outside the labeled window.

    This is the disclosure the whole-month decision depends on. Summing whole months is right —
    pro-rating would invent renders that may or may not have happened on the days actually in the
    window — but the counts then span days the window's own dates exclude, and a window labeled
    10 July – 9 August that silently counts a 1 July render is the confident lie §6.2 exists to
    stop. So the overhang is named on both sides, in days, and the sentence is authored here rather
    than in the view: a client that composes half of a "these numbers cover more than the dates
    say" statement is a client that can drop the other half.

    Days, never a share of anything. This is not a fifth axis and nothing divides by it.
    """
    first, last = date.fromisoformat(start), date.fromisoformat(end)
    months, cursor = [], first.replace(day=1)
    while cursor <= last:
        closing = cursor.replace(day=monthrange(cursor.year, cursor.month)[1])
        months.append((cursor, closing))
        cursor = closing + timedelta(days=1)
    if not months:
        return {"months": [], "partial": [], "days_before_window": 0, "days_after_window": 0,
                "notice": None}

    before = max((first - months[0][0]).days, 0)
    after = max((months[-1][1] - last).days, 0)
    partial = [opening.strftime("%Y-%m") for opening, closing in months
               if opening < first or closing > last]
    edges = []
    if before:
        edges.append(f"{before} day{'' if before == 1 else 's'} before {start}")
    if after:
        edges.append(f"{after} day{'' if after == 1 else 's'} after {end}")
    read_from = (f"the month {months[0][0]:%Y-%m}" if len(months) == 1
                 else f"{months[0][0]:%Y-%m} through {months[-1][0]:%Y-%m}")
    notice = None
    if edges:
        # "span", not "include": the trailing edge of a window ending today is days that have not
        # happened yet, and claiming their activity is counted would be its own small lie.
        notice = (
            f"Counts are summed over whole calendar months, so this window is read from "
            f"{read_from} and they span {' and '.join(edges)}. The edges are not pro-rated: "
            f"dividing a month's counts across its days would invent renders that may or may not "
            f"have happened on the days actually in the window.")
    return {"months": [opening.strftime("%Y-%m") for opening, _ in months],
            "partial": partial, "days_before_window": before, "days_after_window": after,
            "notice": notice}


def _rollup_rows(conn: sqlite3.Connection, start: str, end: str) -> dict[str, dict]:
    """Rollup months that fall inside the window, keyed by surface.

    Months are whole, so a window that starts mid-month includes that month entire. Stated in the
    response as `partial_months` rather than silently pro-rated: pro-rating would invent renders
    that may or may not have happened on the days actually in the window.
    """
    rows = conn.execute(
        "SELECT surface_key, SUM(rendered) AS rendered, SUM(engaged) AS engaged, "
        "MAX(last_engaged_on) AS last_engaged_on "
        "FROM surface_usage_months WHERE month >= ? AND month <= ? GROUP BY surface_key",
        (start[:7], end[:7])).fetchall()
    return {row["surface_key"]: {"rendered": int(row["rendered"] or 0),
                                 "engaged": int(row["engaged"] or 0),
                                 "last_engaged_on": row["last_engaged_on"]} for row in rows}


def report(conn: sqlite3.Connection, *, today: str | None = None,
           window_days: int | None = None, sort: str = "navigation") -> dict:
    """§8's report. Default order is navigation order, never least-used-first.

    A leaderboard sorted by disuse reads as a kill list, and its top row would be whichever surface
    has the least honest window rather than the least useful one. Sorting by disuse exists as an
    explicit control and is not the default.
    """
    fold(conn)
    window = observation_window(conn, today=today, window_days=window_days)
    counts = _rollup_rows(conn, window["from"], window["to"])
    causes = surface_retirement.current_actions(conn)
    triggers = surface_triggers.counts(conn, window["from"], window["to"])

    rows = []
    for surface in surfaces.REGISTRY:
        if surface.kind == "command":
            continue
        seen = counts.get(surface.key, {"rendered": 0, "engaged": 0, "last_engaged_on": None})
        trigger = triggers.get(surface.key)
        observation, notice = _observe(
            surface, rendered=seen["rendered"], engaged=seen["engaged"],
            observed_days=window["observed_days"], trigger=trigger)
        rows.append({
            "surface": surface.key,
            "label": surface.label,
            "route": surface.route,
            "kind": surface.kind,
            "cadence": surface.cadence,
            # The four axes, each named and each standing alone.
            "rendered": seen["rendered"],
            "engaged": seen["engaged"],
            "last_engaged_on": seen["last_engaged_on"],
            "window_days_required": surfaces.window_days(surface.cadence),
            "window_covered": observation != "insufficient_window",
            # §6.4, kept as its own block so nothing downstream can quietly fold it into the two
            # counters above. `trigger_count` is `None` — not zero — whenever no count is available.
            "trigger": surface.trigger,
            "trigger_condition": (trigger or {}).get("condition"),
            "trigger_count": (trigger or {}).get("count"),
            "trigger_available": bool((trigger or {}).get("available")),
            "observation": observation,
            "observation_label": OBSERVATION_COPY[observation]["label"],
            "notice": notice,
            # §6.1 axis four. Never inferred — it is only ever what an operator recorded, read
            # from the latest note rather than re-derived here. `retirement_action` sits beside it
            # because a cause recorded with `none` is a decision to keep, and showing the cause
            # without the action would read as a decision to remove.
            "recorded_cause": (causes.get(surface.key) or {}).get("cause_code"),
            "recorded_cause_on": (causes.get(surface.key) or {}).get("recorded_on"),
            "retirement_action": (causes.get(surface.key) or {}).get("action") or "none",
            "instrumented": surface.instrumented is True,
            "instrumentation_note": (None if surface.instrumented is True
                                     else surface.instrumented),
        })

    if sort == "least_used":
        # Explicitly requested. Ordered by observation first so `insufficient_window` rows cannot
        # head a list they have no basis to head, then by engagement, then by exposure.
        order = {"rendered_not_engaged": 0, "not_rendered": 1, "engaged": 2,
                 "insufficient_window": 3}
        rows.sort(key=lambda r: (order[r["observation"]], r["engaged"], -r["rendered"]))

    return {
        "window": window,
        "caveat": CAVEAT,
        "observations": OBSERVATION_COPY,
        "sort": "least_used" if sort == "least_used" else "navigation",
        # The whole-month disclosure `_rollup_rows` depends on. Its own key rather than folded into
        # `window`, because `window` is what was asked for and this is what was counted.
        "partial_months": _partial_months(window["from"], window["to"]),
        "surfaces": rows,
        "totals": _totals(rows),
        "screens": _screen_weight(rows),
        "screen_weight_caveat": SCREEN_WEIGHT_CAVEAT,
    }


# --- §8's screen weight, and §7.0's checklist ---------------------------------------------------

SCREEN_WEIGHT_CAVEAT = (
    "A screen that renders eleven sections of which two are ever operated is a layout finding, not "
    "a value one. Sections whose window does not yet cover them are counted separately and are not "
    "on the never-operated list — a section nobody could have known about is not a section nobody "
    "wanted. Position matters here too: the never-operated sections are often the ones sitting "
    "below everything else."
)

# §7.0's threshold, and the whole of its point. Three surfaces reaching one record type is not a
# defect — it is a question worth twenty minutes.
REDUNDANCY_THRESHOLD = 3

HONEST_LIMIT = (
    "Hiding surfaces reduces visual load. It does not reduce the number of concepts you have to "
    "hold, because the model underneath is the same size. The two moves that genuinely simplify — "
    "merging two surfaces that answer the same question, and removing a record type nobody needs — "
    "do not fall out of usage data at all: two surfaces both operated weekly can be answering the "
    "same question in two places, and the counts will call both of them healthy. Telemetry finds "
    "clutter. It is blind to redundancy. This list is the twenty-minute manual pass that is not."
)


def _screen_weight(rows: list[dict]) -> list[dict]:
    """§8's screen-weight view: one row per screen, grouped by route.

    Four independent counters and one list, never a ratio. `never_engaged` deliberately excludes
    `insufficient_window` rows — a section whose window cannot cover it has not been shown to be
    unwanted, and putting it on a never-operated list is precisely how §6.2's refusal would get
    laundered into a finding one level up.
    """
    by_route: dict[str, list[dict]] = {route: [] for route in surfaces.ROUTES}
    for row in rows:
        by_route.setdefault(row["route"], []).append(row)

    screens = []
    for route, group in by_route.items():
        knowable = [row for row in group if row["observation"] != "insufficient_window"]
        screens.append({
            "route": route,
            "sections": len(group),
            "sections_rendered": sum(1 for row in knowable if row["rendered"] > 0),
            "sections_engaged": sum(1 for row in knowable if row["engaged"] > 0),
            "sections_not_yet_knowable": len(group) - len(knowable),
            # Labels, in registry (navigation) order — this is a list to read down a screen with,
            # not a ranking.
            "never_engaged": [{"surface": row["surface"], "label": row["label"],
                               "observation": row["observation"]}
                              for row in knowable if row["engaged"] == 0],
        })
    return screens


def redundancy_checklist(conn: sqlite3.Connection) -> dict:
    """§7.0 — the manual pass telemetry cannot do, rendered from the registry rather than measured.

    For each record type, every *offered* surface that declares a route to it. Three or more, ask
    why. Nothing here is a defect and nothing here is actionable by the app: the output is a
    question list, which is why it stores nothing, counts no events, and has no threshold anybody
    can tune. It reads the retirement state only so that a surface already retired stops appearing
    as a duplicate route — otherwise the checklist would keep asking about a screen that is no
    longer offered.
    """
    offered = surface_retirement.offered_keys(conn)
    by_record: dict[str, list[dict]] = {}
    for surface in surfaces.REGISTRY:
        if surface.key not in offered:
            continue
        for record_type in surface.reaches:
            by_record.setdefault(record_type, []).append(
                {"surface": surface.key, "label": surface.label, "route": surface.route})

    items = [{"record_type": record_type, "surfaces": entries, "count": len(entries),
              "ask_why": len(entries) >= REDUNDANCY_THRESHOLD}
             for record_type, entries in sorted(by_record.items())]
    return {
        "honest_limit": HONEST_LIMIT,
        "threshold": REDUNDANCY_THRESHOLD,
        "record_types": items,
        "ask_why": sum(1 for item in items if item["ask_why"]),
        # A recurring item, not a feature (§7.0). The cadence is stated rather than scheduled,
        # because a due date the app enforced would make this the twelfth thing on a queue instead
        # of the twenty minutes it is meant to be.
        "cadence": "Run this once a quarter, or whenever a new surface is registered.",
    }


def _totals(rows: list[dict]) -> dict:
    """Counts of surfaces per observation. Deliberately four independent counters, never a ratio.

    The same rule VISIBILITY's four absence counters follow: they are counts over our own
    record-keeping, and nothing here divides, totals, or rates one.
    """
    totals = {name: 0 for name in OBSERVATIONS}
    for row in rows:
        totals[row["observation"]] += 1
    totals["surfaces"] = len(rows)
    totals["uninstrumented"] = sum(1 for row in rows if not row["instrumented"])
    return totals
