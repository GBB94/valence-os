"""Stage 9 — portfolio commercial analytics and the expansion playbook.

The module deliberately returns counts, samples, denominators, and record ids.  It does not
manufacture rates over five accounts, sum currencies, or infer a missing commercial link.
"""
from __future__ import annotations

import re
import sqlite3
from collections import Counter, defaultdict
from datetime import date, timedelta
from statistics import median

from fastapi import HTTPException

from . import audit, expansion, repo, stage75
from .db import new_id, now_utc

ELIGIBLE_TRANSITIONS = {"proven", "penetrated", "declined"}


def _days(start: str, end: str) -> int:
    return (date.fromisoformat(end[:10]) - date.fromisoformat(start[:10])).days


def _summary(samples: list[dict], key: str = "days") -> dict:
    values = [row[key] for row in samples]
    return {
        "sample_count": len(values),
        "median_days": median(values) if values else None,
        "minimum_days": min(values) if values else None,
        "maximum_days": max(values) if values else None,
        "insufficient_data": not values,
        "samples": samples,
    }


def portfolio_analytics(conn: sqlite3.Connection, window_days: int = 90) -> dict:
    if window_days < 1 or window_days > 730:
        raise HTTPException(422, "window_days must be between 1 and 730")
    today = date.fromisoformat(now_utc()[:10])
    since = (today - timedelta(days=window_days)).isoformat()
    accounts = repo.list_rows(conn, "accounts", where="1=1 ORDER BY name")
    account_names = {a["id"]: a["name"] for a in accounts}

    transitions = [repo.row_to_dict(r) for r in conn.execute(
        "SELECT h.*,c.account_id FROM cell_state_history h "
        "JOIN whitespace_cells c ON c.id=h.cell_id "
        "WHERE h.derived_state_before IS NOT NULL AND h.derived_state_after IS NOT NULL "
        "AND h.derived_state_before<>h.derived_state_after AND h.changed_on>=? "
        "ORDER BY h.changed_on DESC", (since,))]
    transition_groups: dict[tuple[str, str], list] = defaultdict(list)
    for row in transitions:
        transition_groups[(row["derived_state_before"], row["derived_state_after"])].append(row)
    transition_counts = [{
        "from": before, "to": after, "count": len(rows),
        "cell_ids": sorted({r["cell_id"] for r in rows}),
        "account_count": len({r["account_id"] for r in rows}),
    } for (before, after), rows in sorted(transition_groups.items())]

    current_cells = [repo.row_to_dict(r) for r in conn.execute(
        "SELECT c.*,MAX(CASE WHEN h.derived_state_before IS NOT NULL "
        "AND h.derived_state_after IS NOT NULL "
        "AND h.derived_state_before<>h.derived_state_after THEN h.changed_on END) "
        "AS last_state_transition_on FROM whitespace_cells c "
        "LEFT JOIN cell_state_history h ON h.cell_id=c.id WHERE c.archived=0 GROUP BY c.id")]
    stalled: dict[str, list] = defaultdict(list)
    for cell in current_cells:
        state = expansion.derive_state(cell)
        last = cell.get("last_state_transition_on") or cell["created_at"][:10]
        if last < since:
            stalled[state].append({"cell_id": cell["id"], "account_id": cell["account_id"],
                                   "last_state_transition_on": last})
    stalls = [{"state": state, "count": len(rows), "cells": rows,
               "basis": f"No cell fact transition in the {window_days}-day window."}
              for state, rows in sorted(stalled.items())]

    velocity_samples = []
    for line in conn.execute(
        "SELECT id,account_id,cell_id,funded_on FROM growth_plan_lines "
        "WHERE archived=0 AND status='funded' AND cell_id IS NOT NULL AND funded_on IS NOT NULL"):
        proven = conn.execute(
            "SELECT changed_on FROM cell_state_history WHERE cell_id=? "
            "AND derived_state_after='proven' AND changed_on<=? "
            "ORDER BY changed_on DESC,created_at DESC LIMIT 1",
            (line["cell_id"], line["funded_on"])).fetchone()
        if proven:
            velocity_samples.append({"line_id": line["id"], "cell_id": line["cell_id"],
                                     "account_id": line["account_id"],
                                     "proven_on": proven["changed_on"], "funded_on": line["funded_on"],
                                     "days": _days(proven["changed_on"], line["funded_on"])})

    ask_samples = []
    for line in conn.execute(
        "SELECT id,account_id,ask_calendar_id,funded_on FROM growth_plan_lines "
        "WHERE archived=0 AND status='funded' AND ask_calendar_id IS NOT NULL AND funded_on IS NOT NULL"):
        delivered = conn.execute(
            "SELECT completed_on FROM ask_calendar_steps WHERE calendar_id=? "
            "AND kind='business_case_delivered' AND status='done' AND completed_on IS NOT NULL "
            "ORDER BY completed_on LIMIT 1", (line["ask_calendar_id"],)).fetchone()
        if delivered and delivered["completed_on"] <= line["funded_on"]:
            ask_samples.append({"line_id": line["id"], "account_id": line["account_id"],
                                "case_delivered_on": delivered["completed_on"],
                                "funded_on": line["funded_on"],
                                "days": _days(delivered["completed_on"], line["funded_on"])})

    value_counts: Counter = Counter()
    value_records = []
    for account in accounts:
        ledger = expansion.ledger(conn, account["id"])
        value_counts.update(ledger["counts"])
        value_records.extend({"account_id": account["id"], "target_id": t["id"],
                              "status": t["realization"]["status"]} for t in ledger["targets"])

    revenues = []
    for account in accounts:
        row = expansion.revenue_movement(conn, account["id"], since)
        row["account_name"] = account["name"]
        growth = stage75.growth_plan(conn, account["id"])
        active_lines = [line for line in growth.get("lines", [])
                        if line["status"] not in ("declined", "slipped")]
        recurring = [line for line in active_lines
                     if line.get("seat_price_basis") == "annual_recurring"
                     and line.get("seat_price_currency") == row.get("currency")
                     and line.get("seat_price_low") is not None
                     and line.get("seat_price_high") is not None]
        projection_ok = bool(growth.get("plan") and growth["rollup"]["additive"]
                             and active_lines and len(recurring) == len(active_lines)
                             and row.get("base_arr") is not None)
        if projection_ok:
            low = sum(line["seat_count"] * line["seat_price_low"] for line in recurring)
            high = sum(line["seat_count"] * line["seat_price_high"] for line in recurring)
            weighted = sum(line["seat_count"] * ((line["seat_price_low"] + line["seat_price_high"]) / 2)
                           * line["probability"] for line in recurring)
            row["projected_expansion"] = {"low": low, "high": high,
                                           "probability_weighted": round(weighted, 2),
                                           "currency": row["currency"], "line_count": len(recurring),
                                           "insufficient_data": False}
            row["projected_ending_arr"] = {"low": row["ending_arr"] + low,
                                            "high": row["ending_arr"] + high,
                                            "probability_weighted": row["ending_arr"] + weighted}
        else:
            reasons = []
            if not growth.get("plan"): reasons.append("no active growth plan")
            elif not growth["rollup"]["additive"]: reasons.append("overlapping growth lines")
            if active_lines and len(recurring) != len(active_lines):
                reasons.append("every active line needs an annual-recurring price band in the contract currency")
            if row.get("base_arr") is None: reasons.append("current contract ARR is unavailable")
            row["projected_expansion"] = {"low": None, "high": None,
                                           "probability_weighted": None, "currency": row.get("currency"),
                                           "line_count": len(recurring), "insufficient_data": True,
                                           "reason": "; ".join(reasons) or "no active priced lines"}
            row["projected_ending_arr"] = None
        revenues.append(row)
    currency_groups = []
    for currency in sorted({r["currency"] for r in revenues if r["currency"]}):
        rows = [r for r in revenues if r["currency"] == currency and r["base_arr"] is not None]
        currency_groups.append({"currency": currency, "account_count": len(rows),
                                "base_arr": sum(r["base_arr"] for r in rows),
                                "net_movement": sum(r["net_movement"] for r in rows),
                                "ending_arr": sum(r["ending_arr"] for r in rows),
                                "account_ids": [r["account_id"] for r in rows]})

    bridge_rows, additive_rows, excluded = [], [], []
    for account in accounts:
        growth = stage75.growth_plan(conn, account["id"])
        if not growth.get("plan"):
            excluded.append({"account_id": account["id"], "reason": "no active growth plan"})
            continue
        row = {"account_id": account["id"], "account_name": account["name"], **growth["rollup"]}
        bridge_rows.append(row)
        (additive_rows if row["additive"] else excluded).append(
            row if row["additive"] else {"account_id": account["id"],
                                         "reason": "overlapping active growth-plan populations"})
    portfolio_bridge = {
        "accounts_with_plans": len(bridge_rows), "portfolio_account_count": len(accounts),
        "accounts_in_total": len(additive_rows), "excluded": excluded, "accounts": bridge_rows,
        "totals": ({"current_seats": sum(r["current_seats"] for r in additive_rows),
                    "target_seats": sum(r["target_seats"] for r in additive_rows),
                    "named_seats": sum(r["named_seats"] for r in additive_rows),
                    "committed_seats": sum(r["committed_seats"] for r in additive_rows),
                    "probability_weighted_seats": round(sum(r["probability_weighted_seats"] for r in additive_rows), 1),
                    "unfunded_gap": sum(r["unfunded_gap"] for r in additive_rows)} if additive_rows else None),
        "insufficient_data": not additive_rows,
        "basis": "Totals include only account plans whose active lines do not overlap base populations.",
    }

    land_leave = [repo.row_to_dict(r) for r in conn.execute(
        "SELECT id,account_id,status,explanation,opened_at,closed_at FROM signal_episodes "
        "WHERE kind='land_and_leave' AND opened_at>=? ORDER BY opened_at DESC", (since,))]
    return {
        "window": {"start": since, "end": today.isoformat(), "days": window_days},
        "portfolio_account_count": len(accounts),
        "whitespace": {"transition_count": len(transitions), "transitions": transition_counts,
                       "stalls": stalls, "tracked_cell_count": len(current_cells),
                       "history_coverage_note": "Only transitions captured after Stage 9 carry derived-state snapshots; older fact history is not guessed."},
        "time_to_expansion": _summary(velocity_samples),
        "ask_cycle": _summary(ask_samples),
        "value_realization": {"counts": dict(value_counts), "total": len(value_records),
                              "records": value_records, "insufficient_data": not value_records},
        "revenue": {"accounts": revenues, "currency_groups": currency_groups,
                    "account_count": len(accounts),
                    "note": "Actual and projected recurring-revenue movement in absolutes, grouped by currency; no blended percentage and no FX conversion. Projections require non-overlapping annual-recurring price bands."},
        "portfolio_bridge": portfolio_bridge,
        "land_and_leave": {"count": len(land_leave), "episodes": land_leave},
        "stamp": {"generated_at": now_utc(), "data_current_through": today.isoformat()},
    }


def _cell_tags(conn: sqlite3.Connection, cell: dict) -> list[dict]:
    if not cell.get("view_id"):
        return []
    return [repo.row_to_dict(r) for r in conn.execute(
        "SELECT t.* FROM audience_tags t JOIN population_view_tags pvt ON pvt.tag_id=t.id "
        "WHERE pvt.view_id=? AND t.archived=0 ORDER BY t.name", (cell["view_id"],))]


def pending_transitions(conn: sqlite3.Connection, account_id: str | None = None) -> list[dict]:
    where, params = ("h.derived_state_after IN ('proven','penetrated','declined') "
                     "AND h.derived_state_before IS NOT NULL "
                     "AND h.derived_state_before<>h.derived_state_after"), []
    if account_id:
        repo.get_row(conn, "accounts", account_id)
        where += " AND c.account_id=?"; params.append(account_id)
    rows = conn.execute(
        "SELECT h.*,c.account_id,c.use_case_id,c.segment_id,c.view_id,uc.name AS use_case_name,"
        "uc.account_id AS use_case_account_id,COALESCE(ps.name,pv.name) AS population_name "
        "FROM cell_state_history h JOIN whitespace_cells c ON c.id=h.cell_id "
        "JOIN use_cases uc ON uc.id=c.use_case_id LEFT JOIN population_segments ps ON ps.id=c.segment_id "
        "LEFT JOIN population_views pv ON pv.id=c.view_id LEFT JOIN playbook_entries pe "
        "ON pe.transition_history_id=h.id AND pe.archived=0 WHERE " + where +
        " AND pe.id IS NULL ORDER BY h.changed_on DESC", params).fetchall()
    return [{**repo.row_to_dict(r), "audience_tags": _cell_tags(conn, repo.row_to_dict(r)),
             "cross_account_eligible": r["use_case_account_id"] is None} for r in rows]


def create_entry(conn: sqlite3.Connection, values: dict) -> dict:
    history = repo.get_row(conn, "cell_state_history", values["transition_history_id"])
    transition_to = history.get("derived_state_after")
    if transition_to not in ELIGIBLE_TRANSITIONS:
        raise HTTPException(422, "playbook entries require a transition to Proven, Penetrated, or Declined")
    if (history.get("derived_state_before") is None
            or history.get("derived_state_before") == transition_to):
        raise HTTPException(422, "playbook entries require a real derived-state transition")
    cell = repo.get_row(conn, "whitespace_cells", history["cell_id"])
    use_case = repo.get_row(conn, "use_cases", cell["use_case_id"])
    started = values.get("motion_started_on")
    duration = _days(started, history["changed_on"]) if started else None
    if duration is not None and duration < 0:
        raise HTTPException(422, "motion_started_on cannot be after the transition")
    requested_tag_ids = set(values.pop("tag_ids", []))
    # Shape is an observation about the transitioned cell, not an operator-authored label.  The
    # entry snapshots the view's global tags so later view edits cannot rewrite history; segment
    # cells honestly retain an empty tag set and match at the use-case tier only.
    tag_ids = [tag["id"] for tag in _cell_tags(conn, cell)]
    if requested_tag_ids and requested_tag_ids != set(tag_ids):
        raise HTTPException(422, "playbook shape tags are derived from the transitioned cell")
    row = {"id": new_id(), "account_id": cell["account_id"], "cell_id": cell["id"],
           "transition_history_id": history["id"], "use_case_id": use_case["id"],
           "transition_from": history.get("derived_state_before"), "transition_to": transition_to,
           "transitioned_on": history["changed_on"], **values, "duration_days": duration,
           "created_at": now_utc(), "updated_at": now_utc()}
    try:
        with conn:
            conn.execute(f"INSERT INTO playbook_entries ({','.join(row)}) VALUES "
                         f"({','.join('?' for _ in row)})", tuple(row.values()))
            for tag_id in tag_ids:
                conn.execute("INSERT INTO playbook_entry_tags(entry_id,tag_id) VALUES (?,?)",
                             (row["id"], tag_id))
            audit.record(conn, object_type="playbook_entry", object_id=row["id"],
                         action="create", after=row)
    except sqlite3.IntegrityError as exc:
        if "UNIQUE" in str(exc):
            raise HTTPException(409, "that transition already has a playbook entry") from exc
        raise
    return get_entry(conn, row["id"])


def get_entry(conn: sqlite3.Connection, entry_id: str) -> dict:
    entry = repo.get_row(conn, "playbook_entries", entry_id)
    use_case = repo.get_row(conn, "use_cases", entry["use_case_id"])
    tags = [repo.row_to_dict(r) for r in conn.execute(
        "SELECT t.* FROM audience_tags t JOIN playbook_entry_tags pet ON pet.tag_id=t.id "
        "WHERE pet.entry_id=? ORDER BY t.name", (entry_id,))]
    account = repo.get_row(conn, "accounts", entry["account_id"])
    return {**entry, "use_case": use_case["name"], "account_name": account["name"],
            "audience_tags": tags, "cross_account_eligible": use_case["account_id"] is None}


def list_entries(conn: sqlite3.Connection, account_id: str | None = None) -> list[dict]:
    where, params = "archived=0", []
    if account_id:
        where += " AND account_id=?"; params.append(account_id)
    ids = [r["id"] for r in conn.execute(
        f"SELECT id FROM playbook_entries WHERE {where} ORDER BY transitioned_on DESC,created_at DESC", params)]
    return [get_entry(conn, entry_id) for entry_id in ids]


def rank_shape(target_tags: set[str], entry_tags: set[str],
               tag_names: dict[str, str] | None = None) -> tuple[int, str]:
    """Rank one candidate against a target audience shape, and say why (D-94).

    Shared with adoption-campaign matching (`campaigns.matches`) rather than reimplemented there.
    The rule this encodes was a live bug: `set() == set()` used to rank as tier 1 "exact shape", so
    two unrelated *untagged* populations matched at the strongest tier. Exact now requires a
    NON-EMPTY equal tag set; tagless shapes fall through to an honest use-case-only match.

    That distinction is the whole value of the tier: "we have run this exact shape before" justifies
    copying a motion, "we have used this feature before" does not. One copy of the rule means one
    place it can regress.
    """
    overlap = sorted(target_tags & entry_tags)
    if target_tags and entry_tags == target_tags:
        return 1, "Exact use case and audience-tag shape."
    if overlap:
        names = [(tag_names or {}).get(t, t) for t in overlap]
        return 2, "Same use case; overlapping audience tags: " + ", ".join(names) + "."
    if target_tags and entry_tags:
        return 3, "Same global use case; no audience-tag overlap."
    return 3, "Same global use case; audience tags unavailable for one or both shapes."


def matches(conn: sqlite3.Connection, cell_id: str) -> dict:
    cell = repo.get_row(conn, "whitespace_cells", cell_id)
    use_case = repo.get_row(conn, "use_cases", cell["use_case_id"])
    target_tags = {t["id"] for t in _cell_tags(conn, cell)}
    if use_case["account_id"] is not None:
        return {"cell_id": cell_id, "cross_account_eligible": False, "matches": [],
                "reason": "Account-specific use cases are excluded from cross-account matching."}
    ranked = []
    for entry in list_entries(conn):
        if entry["use_case_id"] != use_case["id"] or not entry["cross_account_eligible"]:
            continue
        entry_tags = {t["id"] for t in entry["audience_tags"]}
        rank, reason = rank_shape(target_tags, entry_tags,
                                  {t["id"]: t["name"] for t in entry["audience_tags"]})
        ranked.append({**entry, "match_rank": rank, "match_reason": reason})
    ranked.sort(key=lambda e: (e["match_rank"],
                               -date.fromisoformat(e["transitioned_on"][:10]).toordinal(), e["id"]))
    return {"cell_id": cell_id, "cross_account_eligible": True,
            "shape": {"use_case": use_case["name"], "audience_tags": [t["name"] for t in _cell_tags(conn, cell)]},
            "matches": ranked, "reason": None}


def play_applies_to_cell(conn: sqlite3.Connection, play_id: str, cell_id: str | None) -> bool:
    """Scope learned plays to the global cell shapes that supplied their evidence.

    Hand-authored legacy plays have no playbook links and retain their existing trigger-wide
    behavior. A play promoted from the library must not fire for every expansion signal merely
    because all of those signals share one broad trigger kind.
    """
    source_ids = {r["id"] for r in conn.execute(
        "SELECT id FROM playbook_entries WHERE play_definition_id=? AND archived=0", (play_id,))}
    if not source_ids:
        return True
    if not cell_id:
        return False
    return bool(source_ids & {entry["id"] for entry in matches(conn, cell_id)["matches"]})


def promote_play(conn: sqlite3.Connection, entry_id: str, name: str, action_template: str) -> dict:
    entry = get_entry(conn, entry_id)
    if entry["transition_to"] not in ("proven", "penetrated"):
        raise HTTPException(422, "only successful transitions can be promoted to a play")
    if not entry["cross_account_eligible"]:
        raise HTTPException(422, "account-specific use cases cannot become portfolio plays")
    normalized = re.sub(r"\s+", " ", entry["motion_run"].strip().lower())
    peers = [e for e in list_entries(conn) if e["transition_to"] in ("proven", "penetrated")
             and e["cross_account_eligible"]
             and re.sub(r"\s+", " ", e["motion_run"].strip().lower()) == normalized]
    if len(peers) < 2:
        raise HTTPException(422, "promotion requires the same successful motion in at least two playbook entries")
    if any(e.get("play_definition_id") for e in peers):
        raise HTTPException(409, "this repeated motion is already linked to a play")
    ts, play_id = now_utc(), new_id()
    play = {"id": play_id, "name": name, "trigger_kind": "expansion_signal",
            "action_template": action_template, "active": True, "created_at": ts, "updated_at": ts}
    with conn:
        conn.execute("INSERT INTO play_definitions "
                     "(id,name,trigger_kind,action_template,active,created_at,updated_at) "
                     "VALUES (?,?,?,?,?,?,?)", tuple(play.values()))
        audit.record(conn, object_type="play_definition", object_id=play_id,
                     action="create", after=play)
        for peer in peers:
            before = repo.get_row(conn, "playbook_entries", peer["id"])
            conn.execute("UPDATE playbook_entries SET play_definition_id=?,updated_at=? WHERE id=?",
                         (play_id, ts, peer["id"]))
            audit.record(conn, object_type="playbook_entry", object_id=peer["id"], action="update",
                         before=before, after={**before, "play_definition_id": play_id})
    return {"play": play, "linked_entry_ids": [e["id"] for e in peers],
            "evidence_count": len(peers)}


def promote_message(conn: sqlite3.Connection, entry_id: str, values: dict) -> dict:
    entry = get_entry(conn, entry_id)
    if entry["transition_to"] not in ("proven", "penetrated") or not entry.get("message_summary"):
        raise HTTPException(422, "a successful entry with a message is required")
    if entry.get("messaging_entry_id"):
        raise HTTPException(409, "this message is already promoted")
    ts, message_id = now_utc(), new_id()
    message = {"id": message_id, "layer": entry.get("message_layer") or "operational",
               "role": values.get("role"),
               "value_prop": values.get("value_prop") or entry["message_summary"],
               "proof_points": values.get("proof_points") or entry.get("evidence_summary"),
               "objections": values.get("objections"), "artifacts_note": values.get("artifacts_note"),
               "visibility_class": "internal", "created_at": ts, "updated_at": ts}
    with conn:
        conn.execute("INSERT INTO messaging_entries "
                     "(id,layer,role,value_prop,proof_points,objections,artifacts_note,visibility_class,"
                     "created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?,?)", tuple(message.values()))
        audit.record(conn, object_type="messaging_entry", object_id=message_id,
                     action="create", after=message)
        conn.execute("UPDATE playbook_entries SET messaging_entry_id=?,updated_at=? WHERE id=?",
                     (message_id, ts, entry_id))
        audit.record(conn, object_type="playbook_entry", object_id=entry_id, action="update",
                     before=entry, after={**entry, "messaging_entry_id": message_id})
    return {"messaging_entry": message, "playbook_entry_id": entry_id}
