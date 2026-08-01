"""Stage 7 domain services: signal episodes, mock calendar, and org-change proposals.

Signals are explainable episodes, not one-shot booleans.  Every evaluation either keeps one
active episode, closes it when the condition clears, or respects the operator's dismissal
cooldown.  No source in this module reaches a real external system.
"""
from __future__ import annotations

import json
import sqlite3
from datetime import date, datetime, timedelta

from fastapi import HTTPException

from . import adapters, audit, cadence, expansion, jobs, repo
from .db import new_id, now_utc

ACTIVE = ("open", "held")


def _today() -> date:
    return date.fromisoformat(now_utc()[:10])


def settings(conn: sqlite3.Connection, account_id: str) -> dict:
    row = conn.execute("SELECT * FROM account_settings WHERE account_id=?", (account_id,)).fetchone()
    if row:
        return dict(row)
    return {
        "account_id": account_id, "min_cohort_size": 25, "pull_signal_window_days": 90,
        "signal_cooldown_days": 30, "signal_hysteresis_pct": 0.05,
        "priority_response_hours": 24, "champion_quiet_days": 45,
        "business_timezone": "America/New_York",
        "business_day_start_hour": 9, "business_day_end_hour": 17,
    }


def _json(value) -> str:
    return json.dumps(value, separators=(",", ":"), sort_keys=True)


def _open_or_refresh(conn: sqlite3.Connection, candidate: dict) -> dict | None:
    """Open one episode, refresh its evidence, or suppress it during a dismissal cooldown."""
    ts = now_utc()
    current = conn.execute(
        "SELECT * FROM signal_episodes WHERE condition_key=? AND status IN ('open','held')",
        (candidate["condition_key"],)).fetchone()
    if current:
        values = {
            "status": candidate.get("status", "open"),
            "explanation": candidate["explanation"],
            "context_json": _json(candidate.get("context", {})),
            "current_value": candidate.get("current_value"),
            "threshold_value": candidate.get("threshold_value"),
            "rearm_value": candidate.get("rearm_value"),
            "direction": candidate.get("direction"),
            "freshness_as_of": candidate.get("freshness_as_of"),
            "held_reason": candidate.get("held_reason"),
            "last_evaluated_at": ts, "updated_at": ts,
        }
        conn.execute(
            "UPDATE signal_episodes SET " + ",".join(f"{k}=?" for k in values) + " WHERE id=?",
            (*values.values(), current["id"]),)
        return dict(conn.execute("SELECT * FROM signal_episodes WHERE id=?", (current["id"],)).fetchone())

    prior = conn.execute(
        "SELECT status,cooldown_until,condition_cleared_at FROM signal_episodes WHERE condition_key=? "
        "ORDER BY opened_at DESC LIMIT 1", (candidate["condition_key"],)).fetchone()
    if prior:
        # A terminal action is not a new episode while its source condition remains true.
        if prior["status"] in ("dismissed", "converted", "attached") and not prior["condition_cleared_at"]:
            return None
        if (prior["status"] == "dismissed" and prior["cooldown_until"] and
                prior["cooldown_until"] > _today().isoformat()):
            return None

    eid = new_id()
    row = {
        "id": eid, "account_id": candidate.get("account_id"),
        "program_id": candidate.get("program_id"), "cell_id": candidate.get("cell_id"),
        "kind": candidate["kind"], "condition_key": candidate["condition_key"],
        "object_type": candidate.get("object_type"), "object_id": candidate.get("object_id"),
        "source_kind": candidate["source_kind"], "source_id": candidate.get("source_id"),
        "status": candidate.get("status", "open"), "explanation": candidate["explanation"],
        "context_json": _json(candidate.get("context", {})),
        "threshold_value": candidate.get("threshold_value"),
        "current_value": candidate.get("current_value"), "rearm_value": candidate.get("rearm_value"),
        "direction": candidate.get("direction"), "freshness_as_of": candidate.get("freshness_as_of"),
        "held_reason": candidate.get("held_reason"), "opened_at": ts,
        "last_evaluated_at": ts, "created_at": ts, "updated_at": ts,
    }
    conn.execute(
        f"INSERT INTO signal_episodes ({','.join(row)}) VALUES ({','.join('?' for _ in row)})",
        tuple(row.values()))
    audit.record(conn, object_type="signal_episode", object_id=eid, action="create",
                 after={"kind": row["kind"], "condition_key": row["condition_key"],
                        "status": row["status"], "explanation": row["explanation"]})
    return dict(conn.execute("SELECT * FROM signal_episodes WHERE id=?", (eid,)).fetchone())


def _close_absent(conn: sqlite3.Connection, source_kind: str, current_keys: set[str]) -> int:
    rows = conn.execute(
        "SELECT id,condition_key,status FROM signal_episodes WHERE source_kind=? "
        "AND (status IN ('open','held') OR (status IN ('dismissed','converted','attached') "
        "AND condition_cleared_at IS NULL))", (source_kind,)).fetchall()
    ts, closed = now_utc(), 0
    for row in rows:
        if row["condition_key"] in current_keys:
            continue
        if row["status"] in ACTIVE:
            conn.execute("UPDATE signal_episodes SET status='closed',closed_at=?,condition_cleared_at=?,"
                         "last_evaluated_at=?,updated_at=? WHERE id=?", (ts, ts, ts, ts, row["id"]))
            audit.record(conn, object_type="signal_episode", object_id=row["id"], action="close",
                         before={"status": row["status"]}, after={"status": "closed"})
        else:
            conn.execute("UPDATE signal_episodes SET condition_cleared_at=?,last_evaluated_at=?,"
                         "updated_at=? WHERE id=?", (ts, ts, ts, row["id"]))
            audit.record(conn, object_type="signal_episode", object_id=row["id"], action="update",
                         before={"condition_cleared_at": None}, after={"condition_cleared_at": ts})
        closed += 1
    return closed


def sync_attention_episodes(conn: sqlite3.Connection, items: list[dict]) -> list[dict]:
    """Turn derived queue conditions into episodes so a resolved condition can later recur."""
    keys, active = set(), []
    for item in items:
        if item.get("object_type") == "signal_episode" or item.get("trigger_type") == "fired_play":
            continue
        key = f"attention:{item['trigger_type']}:{item['object_type']}:{item['object_id']}"
        keys.add(key)
        ep = _open_or_refresh(conn, {
            "account_id": item.get("account_id"), "program_id": item.get("program_id"),
            "kind": item["trigger_type"], "condition_key": key,
            "object_type": item["object_type"], "object_id": item["object_id"],
            "source_kind": "attention", "source_id": item["object_id"],
            "explanation": item["because"],
            "context": {"title": item.get("title"), "because": item["because"],
                        "next_action": item.get("next_action")},
        })
        if ep:
            active.append(ep)
    _close_absent(conn, "attention", keys)
    return active


def _guard_for_cell(conn: sqlite3.Connection, cell: dict) -> tuple[str, str | None]:
    """Vendor-initiated signals wait behind unrealized value; client pull never calls this."""
    where = "account_id=? AND status='active'"
    params: list = [cell["account_id"]]
    if cell.get("segment_id"):
        where += " AND segment_id=?"; params.append(cell["segment_id"])
    elif cell.get("view_id"):
        where += " AND view_id=?"; params.append(cell["view_id"])
    else:
        return "open", None
    targets = repo.list_rows(conn, "value_targets", where=where, params=tuple(params))
    if not targets:
        return "open", None
    statuses = [expansion.target_realization(conn, target)["status"] for target in targets]
    if "realized" in statuses:
        return "open", None
    return "held", "Vendor-initiated motion held: underlying value target is not realized."


def _pull_candidates(conn: sqlite3.Connection) -> list[dict]:
    out: list[dict] = []
    for account in conn.execute("SELECT id FROM accounts WHERE archived=0"):
        cfg = settings(conn, account["id"])
        start = (_today() - timedelta(days=cfg["pull_signal_window_days"])).isoformat()
        rows = conn.execute(
            "SELECT ps.* FROM pull_signals ps "
            "WHERE ps.account_id=? AND ps.archived=0 AND ps.status='open' AND ps.cell_id IS NOT NULL "
            "AND COALESCE(ps.occurred_on, substr(ps.created_at,1,10))>=? ORDER BY ps.occurred_on",
            (account["id"], start)).fetchall()
        by_cell: dict[str, list] = {}
        for row in rows:
            by_cell.setdefault(row["cell_id"], []).append(dict(row))
        for cell_id, signals in by_cell.items():
            champion = [s for s in signals if s["signal_kind"] == "champion_ask"]
            qualifying = champion or (signals if len(signals) >= 2 else [])
            if not qualifying:
                continue
            strongest = bool(champion)
            out.append({
                "account_id": account["id"], "cell_id": cell_id,
                "kind": "expansion_signal", "condition_key": f"pull:{'champion' if strongest else 'window'}:{cell_id}",
                "object_type": "whitespace_cell", "object_id": cell_id, "source_kind": "pull",
                "source_id": qualifying[-1]["id"],
                "explanation": ("Validated champion asked for an internal expansion motion."
                                if strongest else
                                f"{len(signals)} client pull signals landed in this cell within "
                                f"{cfg['pull_signal_window_days']} days."),
                "context": {"signal_type": "champion_ask" if strongest else "client_pull",
                            "pull_signal_ids": [s["id"] for s in qualifying],
                            "priority": "customer_pull"},
            })
    return out


def _usage_candidates(conn: sqlite3.Connection) -> list[dict]:
    out = []
    targets = repo.list_rows(conn, "value_targets", where="status='active'")
    for target in targets:
        result = expansion.target_realization(conn, target)
        where, params = ["account_id=?"], [target["account_id"]]
        if target.get("segment_id"):
            where.append("segment_id=?"); params.append(target["segment_id"])
        elif target.get("view_id"):
            where.append("view_id=?"); params.append(target["view_id"])
        else:
            continue
        cfg = settings(conn, target["account_id"])
        margin = cfg["signal_hysteresis_pct"]
        rearm = (target["target_value"] * (1 - margin) if target["direction"] == "at_least"
                 else target["target_value"] * (1 + margin))
        for cell in repo.list_rows(conn, "whitespace_cells",
                                   where=" AND ".join(where), params=tuple(params)):
            # A population target does not identify a use-case column.  The only safe implicit
            # mapping is the live pilot wedge in that population; proposing every white cell in
            # the row would turn one metric into several invented opportunities.
            if cell["penetration"] != "pilot" or cell["evidence_state"] == "measured":
                continue
            key = f"usage:{target['id']}:{cell['id']}"
            active = conn.execute("SELECT 1 FROM signal_episodes WHERE condition_key=? "
                                  "AND status IN ('open','held')", (key,)).fetchone()
            value = result.get("value")
            met = result["status"] == "realized"
            # Hysteresis: after firing, stay open inside the margin; only re-arm once the value
            # has moved materially back across it.
            inside_margin = bool(active and value is not None and (
                value >= rearm if target["direction"] == "at_least" else value <= rearm))
            if not (met or inside_margin):
                continue
            status, held = _guard_for_cell(conn, cell)
            out.append({
                "account_id": target["account_id"], "cell_id": cell["id"],
                "kind": "expansion_signal", "condition_key": key,
                "object_type": "value_target", "object_id": target["id"],
                "source_kind": "usage", "source_id": result.get("observation_id"),
                "status": status, "held_reason": held,
                "explanation": f"Cohort value crossed the agreed {target['direction'].replace('_',' ')} bar: "
                               f"{value:g} vs {target['target_value']:g}.",
                "threshold_value": target["target_value"], "current_value": value,
                "rearm_value": rearm, "direction": target["direction"],
                "freshness_as_of": result.get("current_through"),
                "context": {"signal_type": "usage_threshold", "target_id": target["id"],
                            "cell_id": cell["id"], "value_status": result["status"]},
            })
    return out


def _calendar_candidates(conn: sqlite3.Connection) -> list[dict]:
    end = (_today() + timedelta(days=45)).isoformat()
    out = []
    for event in conn.execute(
        "SELECT * FROM calendar_events WHERE archived=0 AND cell_id IS NOT NULL "
        "AND substr(starts_at,1,10) BETWEEN ? AND ?", (_today().isoformat(), end)):
        cell = repo.get_row(conn, "whitespace_cells", event["cell_id"])
        status, held = _guard_for_cell(conn, cell)
        out.append({
            "account_id": event["account_id"], "program_id": event["program_id"],
            "cell_id": event["cell_id"], "kind": "calendar_moment",
            "condition_key": f"calendar:{event['id']}:{event['cell_id']}",
            "object_type": "calendar_event", "object_id": event["id"],
            "source_kind": "calendar", "source_id": event["id"], "status": status,
            "held_reason": held,
            "explanation": f"{('QBR' if event['purpose'] == 'qbr' else event['purpose'].replace('_',' ').title())} "
                           f"on {event['starts_at'][:10]} "
                           "is an approaching deployment moment for this cell.",
            "freshness_as_of": event["starts_at"][:10],
            "context": {"signal_type": "calendar_moment", "title": event["title"],
                        "starts_at": event["starts_at"]},
        })
    return out


def _org_candidates(conn: sqlite3.Connection) -> list[dict]:
    out = []
    for flag in conn.execute("SELECT * FROM org_change_flags WHERE archived=0 AND status='confirmed'"):
        out.append({
            "account_id": flag["account_id"], "cell_id": flag["cell_id"],
            "kind": "org_change_confirmed", "condition_key": f"org:{flag['id']}",
            "object_type": "org_change_flag", "object_id": flag["id"],
            "source_kind": "org_change", "source_id": flag["id"],
            "explanation": f"Confirmed {flag['kind'].replace('_',' ')}: {flag['summary']}",
            "freshness_as_of": flag["occurred_on"],
            "context": {"signal_type": "org_change", "change_kind": flag["kind"]},
        })
        if flag["cell_id"]:
            cell = repo.get_row(conn, "whitespace_cells", flag["cell_id"])
            status, held = _guard_for_cell(conn, cell)
            out.append({
                "account_id": flag["account_id"], "cell_id": flag["cell_id"],
                "kind": "expansion_signal", "condition_key": f"org-expansion:{flag['id']}:{flag['cell_id']}",
                "object_type": "org_change_flag", "object_id": flag["id"],
                "source_kind": "org_change", "source_id": flag["id"], "status": status,
                "held_reason": held,
                "explanation": f"Business event makes this cell timely: {flag['summary']}",
                "freshness_as_of": flag["occurred_on"],
                "context": {"signal_type": "business_event", "change_kind": flag["kind"]},
            })
    return out


def _relationship_candidates(conn: sqlite3.Connection) -> list[dict]:
    out = []
    for account in conn.execute("SELECT id, name FROM accounts WHERE archived=0"):
        validated = conn.execute(
            "SELECT COUNT(*) n FROM champion_candidates WHERE account_id=? AND archived=0 "
            "AND stage IN ('validate','arm','maintain')", (account["id"],)).fetchone()["n"]
        programs = conn.execute("SELECT COUNT(*) n FROM programs WHERE account_id=? AND archived=0",
                                (account["id"],)).fetchone()["n"]
        if programs and validated < 2:
            out.append({
                "account_id": account["id"], "kind": "no_second_champion",
                "condition_key": f"champion-coverage:{account['id']}",
                "object_type": "account", "object_id": account["id"], "source_kind": "relationship",
                "explanation": f"Only {validated} validated {'champion' if validated == 1 else 'champions'}; "
                               "the account needs a second independent thread.",
                "context": {"title": f"Second champion needed — {account['name']}",
                            "validated_count": validated},
            })
        cfg = settings(conn, account["id"])
        for cand in conn.execute(
            "SELECT cc.*, p.name FROM champion_candidates cc JOIN persons p ON p.id=cc.person_id "
            "WHERE cc.account_id=? AND cc.archived=0 AND cc.stage IN ('validate','arm','maintain')",
            (account["id"],)):
            last = cadence.last_meaningful_touch(conn, cand["person_id"])
            quiet = last is None or (date.fromisoformat(last[:10]) <=
                                     _today() - timedelta(days=cfg["champion_quiet_days"]))
            if quiet:
                out.append({
                    "account_id": account["id"], "program_id": cand["program_id"],
                    "kind": "champion_gone_quiet", "condition_key": f"champion-quiet:{cand['id']}",
                    "object_type": "champion_candidate", "object_id": cand["id"],
                    "source_kind": "relationship",
                    "explanation": f"Validated champion {cand['name']} has no meaningful touch within "
                                   f"{cfg['champion_quiet_days']} days.",
                    "context": {"title": f"Champion gone quiet — {cand['name']}", "last_touch": last},
                })
    return out


def _stalled_candidates(conn: sqlite3.Connection) -> list[dict]:
    out = []
    for target in repo.list_rows(conn, "value_targets", where="status='active'"):
        if expansion.cohort_suppression_reason(conn, target.get("segment_id"), target.get("view_id")):
            continue
        ids = [r["object_id"] for r in conn.execute(
            "SELECT object_id FROM value_target_evidence WHERE target_id=? "
            "AND object_type='metric_observation'", (target["id"],))]
        if len(ids) < 2:
            continue
        obs = conn.execute(
            "SELECT mo.*, md.stale_after_days FROM metric_observations mo "
            "JOIN metric_definitions md ON md.id=mo.definition_id WHERE mo.id IN (" +
            ",".join("?" * len(ids)) + ") AND mo.archived=0 ORDER BY mo.current_through DESC LIMIT 2", ids).fetchall()
        if len(obs) < 2 or not obs[0]["current_through"]:
            continue
        try:
            if (_today() - date.fromisoformat(obs[0]["current_through"])).days > obs[0]["stale_after_days"]:
                continue
        except ValueError:
            continue
        stalled = (obs[0]["value"] <= obs[1]["value"] if target["direction"] == "at_least"
                   else obs[0]["value"] >= obs[1]["value"])
        if stalled:
            out.append({
                "account_id": target["account_id"], "kind": "stalled_cohort",
                "condition_key": f"stalled:{target['id']}", "object_type": "value_target",
                "object_id": target["id"], "source_kind": "usage", "source_id": obs[0]["id"],
                "explanation": f"Cohort stalled across fresh observations: {obs[1]['value']:g} → {obs[0]['value']:g}.",
                "freshness_as_of": obs[0]["current_through"],
                "context": {"title": "Cohort stalled", "target_id": target["id"]},
            })
    return out


def _land_leave_candidates(conn: sqlite3.Connection) -> list[dict]:
    out = []
    segments = conn.execute("SELECT id, account_id, name FROM population_segments WHERE archived=0")
    for seg in segments:
        obs = conn.execute(
            "SELECT * FROM population_headcount_observations WHERE segment_id=? AND archived=0 "
            "ORDER BY observed_on DESC, period_label DESC LIMIT 2", (seg["id"],)).fetchall()
        if len(obs) < 2 or obs[0]["headcount"] <= obs[1]["headcount"]:
            continue
        expansion_event = conn.execute(
            "SELECT 1 FROM revenue_events WHERE account_id=? AND archived=0 AND kind='expansion' "
            "AND effective_on>? AND effective_on<=? LIMIT 1",
            (seg["account_id"], obs[1]["observed_on"], obs[0]["observed_on"])).fetchone()
        if expansion_event:
            continue
        out.append({
            "account_id": seg["account_id"], "kind": "land_and_leave",
            "condition_key": f"land-leave:{seg['id']}:{obs[0]['period_label']}",
            "object_type": "population_segment", "object_id": seg["id"],
            "source_kind": "headcount", "source_id": obs[0]["id"],
            "explanation": f"{seg['name']} grew {obs[1]['headcount']:,} → {obs[0]['headcount']:,} "
                           "with no expansion revenue event recorded for the interval.",
            "freshness_as_of": obs[0]["observed_on"],
            "context": {"title": f"Land-and-leave risk — {seg['name']}",
                        "previous": obs[1]["headcount"], "current": obs[0]["headcount"]},
        })
    return out


def evaluate_domain_signals(conn: sqlite3.Connection) -> dict:
    """Evaluate every Stage 7 source in one transaction and close conditions that cleared."""
    groups = {
        "pull": _pull_candidates(conn), "usage": _usage_candidates(conn) + _stalled_candidates(conn),
        "calendar": _calendar_candidates(conn), "org_change": _org_candidates(conn),
        "headcount": _land_leave_candidates(conn),
    }
    groups["relationship"] = _relationship_candidates(conn)
    opened, refreshed = [], 0
    with conn:
        for source_kind, candidates in groups.items():
            keys = {c["condition_key"] for c in candidates}
            _close_absent(conn, source_kind, keys)
            for candidate in candidates:
                existed = conn.execute("SELECT 1 FROM signal_episodes WHERE condition_key=? "
                                       "AND status IN ('open','held')", (candidate["condition_key"],)).fetchone()
                ep = _open_or_refresh(conn, candidate)
                if ep and existed:
                    refreshed += 1
                elif ep:
                    opened.append(ep)
    return {"opened": len(opened), "refreshed": refreshed, "episodes": opened}


def list_episodes(conn: sqlite3.Connection, account_id: str | None = None,
                  status: str | None = None) -> list[dict]:
    where, params = ["1=1"], []
    if account_id:
        where.append("se.account_id=?"); params.append(account_id)
    if status:
        where.append("se.status=?"); params.append(status)
    rows = conn.execute(
        "SELECT se.*, a.name account_name, uc.name use_case, "
        "COALESCE(ps.name,pv.name) population FROM signal_episodes se "
        "LEFT JOIN accounts a ON a.id=se.account_id "
        "LEFT JOIN whitespace_cells wc ON wc.id=se.cell_id "
        "LEFT JOIN use_cases uc ON uc.id=wc.use_case_id "
        "LEFT JOIN population_segments ps ON ps.id=wc.segment_id "
        "LEFT JOIN population_views pv ON pv.id=wc.view_id "
        f"WHERE {' AND '.join(where)} ORDER BY CASE se.status WHEN 'open' THEN 0 WHEN 'held' THEN 1 ELSE 2 END, "
        "se.opened_at DESC", tuple(params)).fetchall()
    out = []
    for row in rows:
        item = dict(row)
        item["context"] = json.loads(item.pop("context_json") or "{}")
        out.append(item)
    return out


def dismiss_episode(conn: sqlite3.Connection, episode_id: str, reason: str) -> dict:
    episode = conn.execute("SELECT * FROM signal_episodes WHERE id=?", (episode_id,)).fetchone()
    if not episode:
        raise HTTPException(404, "signal episode not found")
    if episode["status"] not in ACTIVE:
        raise HTTPException(409, f"signal episode is already {episode['status']}")
    cooldown = settings(conn, episode["account_id"])["signal_cooldown_days"] if episode["account_id"] else 30
    ts = now_utc(); until = (_today() + timedelta(days=cooldown)).isoformat()
    with conn:
        conn.execute("UPDATE signal_episodes SET status='dismissed',dismissal_reason=?,cooldown_until=?,"
                     "closed_at=?,updated_at=? WHERE id=?", (reason, until, ts, ts, episode_id))
        if episode["source_kind"] == "pull":
            context = json.loads(episode["context_json"] or "{}")
            ids = context.get("pull_signal_ids") or []
            if ids:
                conn.execute("UPDATE pull_signals SET status='dismissed',updated_at=? WHERE id IN (" +
                             ",".join("?" * len(ids)) + ")", (ts, *ids))
        audit.record(conn, object_type="signal_episode", object_id=episode_id, action="update",
                     after={"reason": reason, "cooldown_until": until})
    return dict(conn.execute("SELECT * FROM signal_episodes WHERE id=?", (episode_id,)).fetchone())


def draft_opportunity(conn: sqlite3.Connection, episode_id: str) -> dict:
    episode = conn.execute("SELECT * FROM signal_episodes WHERE id=?", (episode_id,)).fetchone()
    if not episode:
        raise HTTPException(404, "signal episode not found")
    if episode["status"] == "held":
        raise HTTPException(409, episode["held_reason"] or "signal is held")
    if episode["status"] != "open":
        raise HTTPException(409, f"signal episode is already {episode['status']}")
    cell = repo.get_row(conn, "whitespace_cells", episode["cell_id"]) if episode["cell_id"] else None
    use_case = population = None
    if cell:
        use_case = repo.get_row(conn, "use_cases", cell["use_case_id"])["name"]
        if cell.get("segment_id"):
            population = repo.get_row(conn, "population_segments", cell["segment_id"])["name"]
        elif cell.get("view_id"):
            population = repo.get_row(conn, "population_views", cell["view_id"])["name"]
    opportunity_id, ts = new_id(), now_utc()
    opportunity_values = {
        "id": opportunity_id,
        "account_id": episode["account_id"],
        "name": f"{population or 'Expansion'} — {use_case or episode['kind'].replace('_',' ')}",
        "use_case": use_case, "target_seats": cell.get("estimated_seats") if cell else None,
        "sponsor_person_id": cell.get("sponsor_person_id") if cell else None,
        "supporting_evidence": episode["explanation"],
        "next_action": "Qualify the signal and name the funding path.",
        "created_at": ts, "updated_at": ts,
    }
    context = json.loads(episode["context_json"] or "{}")
    context["opportunity_id"] = opportunity_id
    with conn:
        conn.execute(
            f"INSERT INTO expansion_opportunities ({','.join(opportunity_values)}) "
            f"VALUES ({','.join('?' for _ in opportunity_values)})",
            tuple(opportunity_values.values()),
        )
        audit.record(conn, object_type="expansion_opportunity", object_id=opportunity_id,
                     action="create", after=opportunity_values)
        conn.execute("UPDATE signal_episodes SET status='converted',closed_at=?,context_json=?,updated_at=? "
                     "WHERE id=?", (ts, _json(context), ts, episode_id))
        if episode["source_kind"] == "pull":
            ids = context.get("pull_signal_ids") or []
            if ids:
                conn.execute("UPDATE pull_signals SET status='actioned',updated_at=? WHERE id IN (" +
                             ",".join("?" * len(ids)) + ")", (ts, *ids))
        audit.record(conn, object_type="signal_episode", object_id=episode_id, action="convert",
                     before={"status": "open"},
                     after={"status": "converted", "opportunity_id": opportunity_id})
    opportunity = repo.get_row(conn, "expansion_opportunities", opportunity_id)
    return {"episode_id": episode_id, "opportunity": opportunity}


# --- Mock-source ingestion --------------------------------------------------

def sync_calendar(conn: sqlite3.Connection) -> dict:
    created = skipped = attendees = 0
    for event in adapters.fetch_calendar_events():
        if event.get("external_id") and conn.execute(
                "SELECT 1 FROM calendar_events WHERE external_id=? AND archived=0",
                (event["external_id"],)).fetchone():
            skipped += 1; continue
        account_id = event.get("account_id")
        if account_id:
            repo.get_row(conn, "accounts", account_id)
        src = repo.insert(conn, "source_references", {
            "type": "manual_entry", "label": f"Calendar fixture: {event['title']}",
            "url": f"fixture://calendar/{event['fixture']}", "locator": event.get("external_id"),
        }, object_type="source_reference")
        row = repo.insert(conn, "calendar_events", {
            "external_id": event.get("external_id"), "account_id": account_id,
            "program_id": event.get("program_id"), "cell_id": event.get("cell_id"),
            "direction": "read", "purpose": event.get("purpose", "other"),
            "title": event["title"], "starts_at": event["starts_at"], "ends_at": event.get("ends_at"),
            "location": event.get("location"), "organizer_email": event.get("organizer_email"),
            "association_confidence": 1.0 if account_id else 0.0,
            "source_reference_id": src["id"],
        }, object_type="calendar_event")
        ts = now_utc()
        with conn:
            for att in event.get("attendees", []):
                person = conn.execute("SELECT id FROM persons WHERE lower(email)=lower(?) AND archived=0",
                                      (att["email"],)).fetchone()
                conn.execute("INSERT INTO calendar_event_attendees "
                             "(event_id,person_id,name,email,response_status,attendance_status,created_at) "
                             "VALUES (?,?,?,?,?,?,?)",
                             (row["id"], person["id"] if person else None, att.get("name"), att["email"],
                              att["response_status"] if att["response_status"] in
                              ("accepted","declined","tentative","needs_action","unknown") else "unknown",
                              att["attendance_status"] if att["attendance_status"] in
                              ("invited","attended","no_show","unknown") else "unknown", ts))
                attendees += 1
        created += 1
    return {"created": created, "skipped": skipped, "attendees": attendees}


def write_calendar_event(conn: sqlite3.Connection, values: dict) -> dict:
    account = repo.get_row(conn, "accounts", values["account_id"])
    return repo.insert(conn, "calendar_events", {
        **values, "direction": "written", "external_id": f"local-{new_id()}",
        "association_confidence": 1.0,
    }, object_type="calendar_event")


def sync_org_changes(conn: sqlite3.Connection) -> dict:
    created = skipped = unmatched = 0
    for change in adapters.fetch_org_changes():
        if conn.execute("SELECT 1 FROM org_change_flags WHERE external_id=? AND archived=0",
                        (change.get("external_id"),)).fetchone():
            skipped += 1; continue
        # A fixture/provider payload should not depend on Valence OS's internal UUIDs. Resolve
        # external identifiers conservatively; an absent/ambiguous match is reported and skipped,
        # never guessed and never allowed to fail the rest of the sync batch.
        account_id = change.get("account_id")
        if not account_id and change.get("account_name"):
            accounts = conn.execute("SELECT id FROM accounts WHERE archived=0 AND name=?",
                                    (change["account_name"],)).fetchall()
            account_id = accounts[0]["id"] if len(accounts) == 1 else None
        if not account_id or not conn.execute(
                "SELECT 1 FROM accounts WHERE id=? AND archived=0", (account_id,)).fetchone():
            unmatched += 1; continue
        person_id = change.get("person_id")
        if not person_id and change.get("person_email"):
            people = conn.execute("SELECT id FROM persons WHERE archived=0 AND account_id=? AND email=?",
                                  (account_id, change["person_email"].lower())).fetchall()
            person_id = people[0]["id"] if len(people) == 1 else None
            if len(people) != 1:
                unmatched += 1; continue
        src = repo.insert(conn, "source_references", {
            "type": "manual_entry", "label": f"Enrichment fixture: {change['summary']}",
            "url": f"fixture://org_changes/{change['fixture']}", "locator": change.get("external_id"),
        }, object_type="source_reference")
        repo.insert(conn, "org_change_flags", {
            **{k: change.get(k) for k in ("cell_id","kind","summary", "old_title","new_title",
                                          "person_name","new_company","occurred_on","external_id")},
            "account_id": account_id, "person_id": person_id,
            "source_reference_id": src["id"],
        }, object_type="org_change_flag")
        created += 1
    return {"created": created, "skipped": skipped, "unmatched": unmatched}


def sync_headcount(conn: sqlite3.Connection) -> dict:
    created = skipped = 0
    for raw in adapters.fetch_headcount_observations():
        segment = repo.get_row(conn, "population_segments", raw["segment_id"])
        if segment["account_id"] != raw["account_id"]:
            raise HTTPException(422, "headcount segment belongs to a different account")
        if conn.execute("SELECT 1 FROM population_headcount_observations WHERE segment_id=? "
                        "AND period_label=? AND archived=0", (raw["segment_id"], raw["period_label"])).fetchone():
            skipped += 1; continue
        repo.insert(conn, "population_headcount_observations", {
            "segment_id": raw["segment_id"], "account_id": raw["account_id"],
            "period_label": raw["period_label"], "headcount": int(raw["headcount"]),
            "source_kind": "hris_adapter", "source_note": raw.get("source_note"),
            "observed_on": raw["observed_on"],
        }, object_type="population_headcount_observation")
        created += 1
    return {"created": created, "skipped": skipped}


def confirm_org_change(conn: sqlite3.Connection, flag_id: str, actor: str = "operator") -> dict:
    flag = repo.get_row(conn, "org_change_flags", flag_id)
    if flag["status"] != "proposed":
        raise HTTPException(409, f"org-change flag is already {flag['status']}")
    ts = now_utc(); side_effects: dict = {}
    with conn:
        if flag["kind"] == "title_change":
            if not flag["person_id"] or not flag["new_title"]:
                raise HTTPException(422, "title change needs a tracked person and new title")
            before = repo.get_row(conn, "persons", flag["person_id"])
            conn.execute("UPDATE persons SET title=?,updated_at=? WHERE id=?",
                         (flag["new_title"], ts, flag["person_id"]))
            audit.record(conn, object_type="person", object_id=flag["person_id"], action="update",
                         before=before, after={**before, "title": flag["new_title"]})
            side_effects["person_updated"] = flag["person_id"]
        elif flag["kind"] == "departure":
            if not flag["person_id"]:
                raise HTTPException(422, "departure needs a tracked person")
            person = repo.get_row(conn, "persons", flag["person_id"])
            roles = [dict(r) for r in conn.execute(
                "SELECT * FROM stakeholder_roles WHERE person_id=? AND archived=0", (person["id"],))]
            placeholder_id = new_id()
            conn.execute("INSERT INTO persons (id,name,affiliation,account_id,title,is_placeholder,"
                         "placeholder_why,find_by_date,expected_influence,expected_role,created_at,updated_at,archived) "
                         "VALUES (?,?,?,?,?,1,?,?,?,?,?,?,0)",
                         (placeholder_id, f"Successor to {person['name']} (unknown)", "client", flag["account_id"],
                          person.get("title"), "Confirmed departure; identify the successor.",
                          (_today()+timedelta(days=30)).isoformat(),
                          roles[0].get("influence") if roles else None,
                          roles[0].get("role") if roles else "other", ts, ts))
            audit.record(conn, object_type="person", object_id=placeholder_id, action="create",
                         after={"name": f"Successor to {person['name']} (unknown)",
                                "account_id": flag["account_id"], "is_placeholder": True})
            for role in roles:
                replacement_role_id = new_id()
                conn.execute("INSERT INTO stakeholder_roles "
                             "(id,program_id,person_id,role,layer,cares_about,value_for_them,created_at,updated_at,"
                             "archived,influence,relationship_strength,cadence_target_days) "
                             "VALUES (?,?,?,?,?,?,?,?,?,0,?,?,?)",
                             (replacement_role_id, role["program_id"], placeholder_id, role["role"], role.get("layer"),
                              role.get("cares_about"), role.get("value_for_them"), ts, ts,
                              role.get("influence"), role.get("relationship_strength"),
                              role.get("cadence_target_days")))
                audit.record(conn, object_type="stakeholder_role", object_id=replacement_role_id,
                             action="create", after={"person_id": placeholder_id,
                                                     "program_id": role["program_id"],
                                                     "role": role["role"]})
                audit.record(conn, object_type="stakeholder_role", object_id=role["id"], action="archive",
                             before={"archived": 0}, after={"archived": 1})
            conn.execute("UPDATE stakeholder_roles SET archived=1,archived_at=?,archived_by=?,updated_at=? "
                         "WHERE person_id=? AND archived=0", (ts, actor, ts, person["id"]))
            conn.execute("UPDATE champion_candidates SET archived=1,archived_at=?,archived_by=?,updated_at=? "
                         "WHERE person_id=? AND archived=0", (ts, actor, ts, person["id"]))
            succession_id = new_id()
            snapshot = {"person": {k: person.get(k) for k in ("name","title","comms_preference","metric_judged_on")},
                        "roles": roles}
            conn.execute("INSERT INTO succession_records "
                         "(id,account_id,departed_person_id,successor_placeholder_id,org_change_flag_id,status,"
                         "departed_to,relationship_snapshot_json,occurred_on,created_at,updated_at) "
                         "VALUES (?,?,?,?,?,'open',?,?,?,?,?)",
                         (succession_id, flag["account_id"], person["id"], placeholder_id, flag["id"],
                          flag.get("new_company"), _json(snapshot), flag.get("occurred_on"), ts, ts))
            audit.record(conn, object_type="succession_record", object_id=succession_id, action="create",
                         after={"account_id": flag["account_id"], "departed_person_id": person["id"],
                                "successor_placeholder_id": placeholder_id, "status": "open"})
            side_effects.update({"successor_placeholder_id": placeholder_id, "succession_id": succession_id})
        elif flag["kind"] == "arrival":
            if not flag["person_name"]:
                raise HTTPException(422, "arrival needs the new leader's name")
            person_id = new_id()
            conn.execute("INSERT INTO persons (id,name,affiliation,account_id,title,is_placeholder,created_at,updated_at,archived) "
                         "VALUES (?,?,?,?,?,0,?,?,0)",
                         (person_id, flag["person_name"], "client", flag["account_id"], flag["new_title"], ts, ts))
            audit.record(conn, object_type="person", object_id=person_id, action="create",
                         after={"name": flag["person_name"], "account_id": flag["account_id"],
                                "title": flag["new_title"]})
            program = conn.execute("SELECT id FROM programs WHERE account_id=? AND archived=0 "
                                   "ORDER BY created_at LIMIT 1", (flag["account_id"],)).fetchone()
            if program:
                role_id = new_id()
                conn.execute("INSERT INTO stakeholder_roles (id,program_id,person_id,role,created_at,updated_at,archived) "
                             "VALUES (?,?,?,'other',?,?,0)", (role_id, program["id"], person_id, ts, ts))
                audit.record(conn, object_type="stakeholder_role", object_id=role_id, action="create",
                             after={"program_id": program["id"], "person_id": person_id, "role": "other"})
                for label in ("Map a warm introduction path", "Prepare a first-90-days value brief",
                              "Offer one early, measurable win"):
                    checklist_id = new_id()
                    conn.execute("INSERT INTO checklist_items (id,account_id,program_id,section,label,due_date,status,"
                                 "created_at,updated_at,archived) VALUES (?,?,?,'first_90_days',?,?,'open',?,?,0)",
                                 (checklist_id, flag["account_id"], program["id"], label,
                                  (_today()+timedelta(days=14)).isoformat(), ts, ts))
                    audit.record(conn, object_type="checklist_item", object_id=checklist_id, action="create",
                                 after={"account_id": flag["account_id"], "program_id": program["id"],
                                        "section": "first_90_days", "label": label})
            side_effects["new_person_id"] = person_id
        conn.execute("UPDATE org_change_flags SET status='confirmed',confirmed_at=?,confirmed_by=?,updated_at=? "
                     "WHERE id=?", (ts, actor, ts, flag_id))
        audit.record(conn, object_type="org_change_flag", object_id=flag_id, action="update",
                     after={"kind": flag["kind"], **side_effects})
    return {"flag": repo.get_row(conn, "org_change_flags", flag_id), "side_effects": side_effects}


def dismiss_org_change(conn: sqlite3.Connection, flag_id: str, reason: str) -> dict:
    flag = repo.get_row(conn, "org_change_flags", flag_id)
    if flag["status"] != "proposed":
        raise HTTPException(409, f"org-change flag is already {flag['status']}")
    return repo.patch(conn, "org_change_flags", flag_id,
                      {"status": "dismissed", "dismissal_reason": reason},
                      object_type="org_change_flag")


def complete_succession(conn: sqlite3.Connection, succession_id: str,
                        successor_person_id: str, note: str | None) -> dict:
    rec = repo.get_row(conn, "succession_records", succession_id)
    if rec["status"] != "open":
        raise HTTPException(409, "succession is already completed")
    successor = repo.get_row(conn, "persons", successor_person_id)
    if successor.get("account_id") != rec["account_id"]:
        raise HTTPException(422, "successor belongs to a different account")
    placeholder = rec["successor_placeholder_id"]
    ts = now_utc()
    with conn:
        if placeholder:
            for role in conn.execute("SELECT * FROM stakeholder_roles WHERE person_id=? AND archived=0",
                                     (placeholder,)).fetchall():
                exists = conn.execute("SELECT 1 FROM stakeholder_roles WHERE program_id=? AND person_id=? "
                                      "AND archived=0", (role["program_id"], successor_person_id)).fetchone()
                if exists:
                    conn.execute("UPDATE stakeholder_roles SET archived=1,archived_at=?,archived_by='operator',"
                                 "updated_at=? WHERE id=?", (ts, ts, role["id"]))
                    audit.record(conn, object_type="stakeholder_role", object_id=role["id"], action="archive",
                                 before={"person_id": placeholder, "archived": 0},
                                 after={"person_id": placeholder, "archived": 1})
                else:
                    conn.execute("UPDATE stakeholder_roles SET person_id=?,updated_at=? WHERE id=?",
                                 (successor_person_id, ts, role["id"]))
                    audit.record(conn, object_type="stakeholder_role", object_id=role["id"], action="update",
                                 before={"person_id": placeholder}, after={"person_id": successor_person_id})
            conn.execute("UPDATE persons SET archived=1,archived_at=?,archived_by='operator',updated_at=? "
                         "WHERE id=?", (ts, ts, placeholder))
            audit.record(conn, object_type="person", object_id=placeholder, action="archive",
                         before={"archived": 0}, after={"archived": 1})
        conn.execute("UPDATE succession_records SET successor_person_id=?,status='completed',transfer_note=?,"
                     "completed_at=?,updated_at=? WHERE id=?",
                     (successor_person_id, note, ts, ts, succession_id))
        audit.record(conn, object_type="succession_record", object_id=succession_id, action="close",
                     after={"successor_person_id": successor_person_id, "transfer_note": note})
    return repo.get_row(conn, "succession_records", succession_id)


@jobs.register("sync_calendar")
def _job_sync_calendar(conn, payload):
    return sync_calendar(conn)


@jobs.register("sync_org_changes")
def _job_sync_org_changes(conn, payload):
    return sync_org_changes(conn)


@jobs.register("sync_headcount")
def _job_sync_headcount(conn, payload):
    return sync_headcount(conn)
