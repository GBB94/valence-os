"""Internal forecast ledger: soft evidence, immutable snapshots, and honest units."""
from __future__ import annotations

import json
import sqlite3
from collections import defaultdict
from datetime import date, timedelta

from fastapi import HTTPException

from . import audit, repo
from .db import new_id, now_utc


def operator(conn: sqlite3.Connection) -> str:
    row = conn.execute("SELECT operator_identity FROM internal_operations_settings WHERE id='singleton'").fetchone()
    return row["operator_identity"] if row else audit.DEFAULT_ACTOR


def create_period(conn: sqlite3.Connection, values: dict) -> dict:
    overlap = conn.execute(
        "SELECT id FROM forecast_periods WHERE archived=0 AND cadence=? AND scenario_type=? "
        "AND NOT (ends_on<? OR starts_on>?) LIMIT 1",
        (values["cadence"], values.get("scenario_type", "operating"), values["starts_on"], values["ends_on"]),
    ).fetchone()
    if overlap:
        raise HTTPException(409, "forecast period overlaps the same cadence and scenario")
    return repo.insert(conn, "forecast_periods", {**values, "status": "open"}, object_type="forecast_period")


def list_periods(conn: sqlite3.Connection) -> list[dict]:
    return repo.list_rows(conn, "forecast_periods", where="1=1 ORDER BY starts_on DESC")


def _period(conn: sqlite3.Connection, period_id: str, *, mutable: bool = False) -> dict:
    period = repo.get_row(conn, "forecast_periods", period_id)
    if mutable and period["status"] == "closed":
        raise HTTPException(409, f"forecast period is {period['status']}")
    return period


def create_entry(conn: sqlite3.Connection, period_id: str, values: dict) -> dict:
    _period(conn, period_id, mutable=True)
    # Inherit only when units are explicit and compatible. The mapping is intentionally
    # closed: monthly is never annualized here and every other basis remains unknown.
    if values.get("opportunity_id") and values.get("amount") is None:
        line = conn.execute("SELECT seat_count,seat_price_low,seat_price_high,seat_price_currency,seat_price_basis FROM growth_plan_lines WHERE opportunity_id=? AND archived=0 AND status NOT IN ('slipped','declined') ORDER BY updated_at DESC LIMIT 1", (values["opportunity_id"],)).fetchone()
        basis_map = {"annual_recurring": "arr", "term_total": "tcv", "one_time": "one_time"}
        if line and line["seat_price_low"] is not None and line["seat_price_high"] is not None and line["seat_price_basis"] in basis_map:
            values["amount"] = line["seat_count"] * ((line["seat_price_low"] + line["seat_price_high"]) / 2)
            values["currency"] = line["seat_price_currency"]
            values["price_basis"] = basis_map[line["seat_price_basis"]]
            values["amount_rationale"] = values.get("amount_rationale") or "Inherited midpoint of the linked priced growth-plan line."
    if values.get("contract_version_id"):
        contract = repo.get_row(conn, "contract_versions", values["contract_version_id"])
        if not contract.get("is_current"):
            raise HTTPException(422, "renewal forecast entries require the current contract version")
        values["amount"] = values.get("amount") if values.get("amount") is not None else contract.get("price")
        values["currency"] = values.get("currency") or contract.get("currency")
        values["price_basis"] = values.get("price_basis") or contract.get("price_basis")
        if values.get("amount") is not None and not values.get("amount_rationale"):
            values["amount_rationale"] = "Inherited from the current contract version."
    data = {**values, "period_id": period_id, "author": operator(conn)}
    try:
        return repo.insert(conn, "forecast_entries", data, object_type="forecast_entry")
    except sqlite3.IntegrityError as exc:
        raise HTTPException(409, str(exc)) from exc


def list_entries(conn: sqlite3.Connection, period_id: str) -> list[dict]:
    _period(conn, period_id)
    rows = repo.list_rows(conn, "forecast_entries", where="period_id=? ORDER BY category,created_at", params=(period_id,))
    return [{**row, "evidence": evidence(conn, row["id"])} for row in rows]


def patch_entry(conn: sqlite3.Connection, entry_id: str, changes: dict, fields_set: set[str]) -> dict:
    entry = repo.get_row(conn, "forecast_entries", entry_id)
    _period(conn, entry["period_id"], mutable=True)
    allowed = {"amount", "currency", "price_basis", "probability", "probability_rationale",
               "amount_rationale", "assessed_on", "expected_decision_date", "help_needed_note",
               "renewal_budget_owner_person_id", "renewal_position", "unresolved_conditions"}
    if "category" in changes:
        raise HTTPException(422, "use the category transition endpoint")
    values = {k: v for k, v in changes.items() if k in allowed and k in fields_set}
    if values.get("probability") is not None and not (values.get("probability_rationale") or entry.get("probability_rationale")):
        raise HTTPException(422, "probability_rationale is required with probability")
    return repo.patch(conn, "forecast_entries", entry_id, values, object_type="forecast_entry",
                      allow_null=allowed)


def change_category(conn: sqlite3.Connection, entry_id: str, values: dict) -> dict:
    before = repo.get_row(conn, "forecast_entries", entry_id)
    _period(conn, before["period_id"], mutable=True)
    after_category = values["category"]
    if before["category"] == after_category:
        raise HTTPException(409, "forecast category is unchanged")
    if after_category == "omitted" and not values.get("omitted_reason"):
        raise HTTPException(422, "omitted_reason is required")
    if values.get("corrects_event_id"):
        corrected = repo.get_row(conn, "forecast_change_events", values["corrects_event_id"])
        if corrected["entry_id"] != entry_id:
            raise HTTPException(422, "a correction must reference an event on the same forecast entry")
    ts, actor = now_utc(), operator(conn)
    event = {"id": new_id(), "entry_id": entry_id, "category_before": before["category"],
             "category_after": after_category, "driver": values["driver"], "actor": actor,
             "changed_at": ts, "source_interaction_id": values.get("source_interaction_id"),
             "source_reference_id": values.get("source_reference_id"),
             "corrects_event_id": values.get("corrects_event_id"), "created_at": ts}
    with conn:
        conn.execute("UPDATE forecast_entries SET category=?,omitted_reason=?,updated_at=? WHERE id=?",
                     (after_category, values.get("omitted_reason"), ts, entry_id))
        conn.execute(f"INSERT INTO forecast_change_events ({','.join(event)}) VALUES ({','.join('?' for _ in event)})", tuple(event.values()))
        audit.record(conn, object_type="forecast_entry", object_id=entry_id, action="update", before=before,
                     after=repo.get_row(conn, "forecast_entries", entry_id))
    return repo.get_row(conn, "forecast_entries", entry_id)


def add_source(conn: sqlite3.Connection, entry_id: str, values: dict) -> dict:
    repo.get_row(conn, "forecast_entries", entry_id)
    row = {"id": new_id(), "entry_id": entry_id, **values, "created_at": now_utc()}
    try:
        with conn:
            conn.execute(f"INSERT INTO forecast_entry_sources ({','.join(row)}) VALUES ({','.join('?' for _ in row)})", tuple(row.values()))
    except sqlite3.IntegrityError as exc:
        raise HTTPException(422, str(exc)) from exc
    return repo.row_to_dict(conn.execute("SELECT * FROM forecast_entry_sources WHERE id=?", (row["id"],)).fetchone())


def record_renewal_outcome(conn: sqlite3.Connection, values: dict) -> dict:
    try:
        return repo.insert(conn, "renewal_outcome_events", values, object_type="renewal_outcome")
    except sqlite3.IntegrityError as exc:
        raise HTTPException(422, str(exc)) from exc


def _rule(key: str, satisfied: bool, explanation: str, ids: list[str] | None = None,
          observed_on: str | None = None) -> dict:
    return {"rule_key": key, "satisfied": satisfied, "record_ids": ids or [],
            "observed_on": observed_on, "freshness": "current" if satisfied else "missing",
            "explanation": explanation}


def evidence(conn: sqlite3.Connection, entry_id: str) -> dict:
    entry = repo.get_row(conn, "forecast_entries", entry_id)
    period = repo.get_row(conn, "forecast_periods", entry["period_id"])
    amount_ok = entry.get("amount") is not None and bool(entry.get("currency")) and bool(entry.get("price_basis"))
    rules: list[dict] = []
    if entry.get("opportunity_id"):
        target = repo.get_row(conn, "expansion_opportunities", entry["opportunity_id"])
        order = {"conceptually_supported": 0, "in_planning": 1, "formally_allocated": 2,
                 "requisition_created": 3, "procurement_approved": 4, "executed": 5}
        budget_ok = order.get(target["budget_state"], -1) >= 2
        owner_id = target.get("budget_owner_person_id")
        cutoff = (date.fromisoformat(entry["assessed_on"][:10]) - timedelta(days=30)).isoformat()
        touch = conn.execute(
            "SELECT i.id,i.occurred_on FROM interactions i JOIN interaction_participants ip ON ip.interaction_id=i.id "
            "WHERE i.account_id=? AND ip.person_id=? AND i.meaningful_touch=1 AND i.occurred_on BETWEEN ? AND ? "
            "ORDER BY i.occurred_on DESC LIMIT 1", (entry["account_id"], owner_id or "", cutoff, entry["assessed_on"][:10])).fetchone()
        calendar = conn.execute(
            "SELECT ac.id,ac.target_close_date,acs.id step_id,acs.due_date step_due_date "
            "FROM ask_calendars ac LEFT JOIN ask_calendar_steps acs ON acs.calendar_id=ac.id "
            "AND acs.due_date BETWEEN ? AND ? "
            "WHERE ac.id=? AND ac.account_id=? AND ac.archived=0 "
            "AND (ac.target_close_date BETWEEN ? AND ? OR acs.id IS NOT NULL) "
            "ORDER BY acs.due_date LIMIT 1",
            (period["starts_on"], period["ends_on"], target.get("qualification_ask_calendar_id") or "",
             entry["account_id"], period["starts_on"], period["ends_on"])).fetchone()
        calendar_ids = ([calendar["id"]] + ([calendar["step_id"]] if calendar and calendar["step_id"] else [])) if calendar else []
        rules += [_rule("budget_allocated", budget_ok, "Budget is formally allocated or beyond.", [target["id"]]),
                  _rule("budget_owner_named", bool(owner_id), "A same-account budget owner is named.", [owner_id] if owner_id else []),
                  _rule("budget_owner_engaged_30d", bool(touch), "Budget owner has a meaningful touch in the prior 30 days.", [touch["id"]] if touch else [], touch["occurred_on"] if touch else None),
                  _rule("ask_date_in_period", bool(calendar), "A qualified ask calendar target or required step lands inside the period.", calendar_ids),
                  _rule("defensible_amount", amount_ok, "Amount, currency, and price basis are present.")]
        slots = [target.get("qualification_value_target_id"), owner_id, target.get("qualification_ask_calendar_id"),
                 target.get("qualification_champion_person_id"), target.get("qualification_program_id")]
        qualification_complete = sum(bool(x) for x in slots)
    else:
        target = repo.get_row(conn, "contract_versions", entry["contract_version_id"])
        decision = target.get("overlay_expected_decision_date") or target.get("renewal_date")
        owner_id = entry.get("renewal_budget_owner_person_id")
        cutoff = (date.fromisoformat(entry["assessed_on"][:10]) - timedelta(days=30)).isoformat()
        touch = conn.execute(
            "SELECT i.id,i.occurred_on FROM interactions i JOIN interaction_participants ip ON ip.interaction_id=i.id "
            "WHERE i.account_id=? AND ip.person_id=? AND i.meaningful_touch=1 AND i.occurred_on BETWEEN ? AND ? ORDER BY i.occurred_on DESC LIMIT 1",
            (entry["account_id"], owner_id or "", cutoff, entry["assessed_on"][:10])).fetchone()
        date_ok = bool(decision and period["starts_on"] <= decision[:10] <= period["ends_on"])
        position_ok = entry.get("renewal_position") in ("confirmed_intent", "commercial_review", "procurement_in_progress")
        rules += [_rule("renewal_date_in_period", date_ok, "Renewal decision date is inside the period.", [target["id"]]),
                  _rule("renewal_budget_owner_named", bool(owner_id), "A same-account renewal budget owner is named.", [owner_id] if owner_id else []),
                  _rule("renewal_owner_engaged_30d", bool(touch), "Renewal owner has a meaningful touch in the prior 30 days.", [touch["id"]] if touch else [], touch["occurred_on"] if touch else None),
                  _rule("renewal_position_sourced", position_ok, "Renewal position is confirmed, in commercial review, or procurement.", [entry_id] if position_ok else []),
                  _rule("defensible_amount", amount_ok, "Amount, currency, and price basis are present.")]
        qualification_complete = sum(r["satisfied"] for r in rules)
    missing = [r for r in rules if not r["satisfied"]]
    if entry["category"] == "best_case" and not entry.get("unresolved_conditions"):
        missing.append(_rule("conditions_named", False, "Every unresolved condition must be named."))
    supported = (entry["category"] in ("pipeline", "omitted") or
                 (entry["category"] == "commit" and not missing) or
                 (entry["category"] == "best_case" and qualification_complete >= 3 and not any(r["rule_key"] == "conditions_named" for r in missing)))
    return {"entry_id": entry_id, "category": entry["category"], "supported": supported,
            "qualification_complete": qualification_complete, "qualification_total": 5,
            "rules": rules, "missing": missing}


def _source_manifest(conn: sqlite3.Connection, entry_id: str) -> list[dict]:
    return [repo.row_to_dict(r) for r in conn.execute("SELECT * FROM forecast_entry_sources WHERE entry_id=? ORDER BY created_at", (entry_id,))]


def lock_period(conn: sqlite3.Connection, period_id: str) -> dict:
    period = _period(conn, period_id, mutable=True)
    if period["status"] != "open":
        raise HTTPException(409, "only an open forecast period can lock its opening snapshot")
    lines = repo.list_rows(conn, "forecast_entries", where="period_id=? ORDER BY id", params=(period_id,))
    ts, actor, snapshot_id = now_utc(), operator(conn), new_id()
    with conn:
        conn.execute("INSERT INTO forecast_opening_snapshots(id,period_id,locked_at,locked_by,created_at) VALUES (?,?,?,?,?)",
                     (snapshot_id, period_id, ts, actor, ts))
        for entry in lines:
            target_type = "opportunity" if entry.get("opportunity_id") else "renewal"
            target_id = entry.get("opportunity_id") or entry.get("contract_version_id")
            conn.execute("INSERT INTO forecast_opening_lines(id,snapshot_id,entry_id,account_id,target_type,target_id,category,amount,currency,price_basis,probability,source_manifest_json,created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                         (new_id(), snapshot_id, entry["id"], entry["account_id"], target_type, target_id,
                          entry["category"], entry.get("amount"), entry.get("currency"), entry.get("price_basis"),
                          entry.get("probability"), json.dumps(_source_manifest(conn, entry["id"]), sort_keys=True), ts))
        conn.execute("UPDATE forecast_periods SET status='locked',locked_at=?,locked_by=?,updated_at=? WHERE id=?",
                     (ts, actor, ts, period_id))
        audit.record(conn, object_type="forecast_period", object_id=period_id, action="update", before=period,
                     after={**period, "status": "locked", "locked_at": ts})
    return repo.get_row(conn, "forecast_periods", period_id)


def _closed_actuals(conn: sqlite3.Connection, period: dict, entries: list[dict]) -> list[dict]:
    """Return sourced terminal outcomes; won rows carry the dated actual when available."""
    rows = []
    for entry in entries:
        if entry.get("opportunity_id"):
            opportunity = conn.execute(
                "SELECT status,outcome FROM expansion_opportunities WHERE id=?",
                (entry["opportunity_id"],),
            ).fetchone()
            if not opportunity or opportunity["status"] != "closed":
                continue
            actual = conn.execute(
                "SELECT id,amount,currency,price_basis FROM revenue_events "
                "WHERE account_id=? AND opportunity_id=? AND kind='expansion' "
                "AND effective_on BETWEEN ? AND ? AND archived=0 ORDER BY effective_on DESC LIMIT 1",
                (entry["account_id"], entry["opportunity_id"], period["starts_on"], period["ends_on"]),
            ).fetchone()
            amount_key = "amount"
            counts_as_closed = opportunity["outcome"] == "won"
            source_id = actual["id"] if actual else entry["opportunity_id"]
        else:
            outcome = conn.execute(
                "SELECT id,outcome,actual_amount,currency,price_basis FROM renewal_outcome_events "
                "WHERE account_id=? AND contract_version_id=? "
                "AND occurred_on BETWEEN ? AND ? AND archived=0 ORDER BY occurred_on DESC LIMIT 1",
                (entry["account_id"], entry["contract_version_id"], period["starts_on"], period["ends_on"]),
            ).fetchone()
            if not outcome or outcome["outcome"] == "unresolved":
                continue
            actual = outcome
            amount_key = "actual_amount"
            counts_as_closed = outcome["outcome"] == "renewed"
            source_id = outcome["id"]
        rows.append({"source_id": source_id, "entry_id": entry["id"],
                     "counts_as_closed": counts_as_closed,
                     "amount": actual[amount_key] if actual else None,
                     "currency": actual["currency"] if actual else None,
                     "price_basis": actual["price_basis"] if actual else None})
    return rows


def totals(entries: list[dict], closed_actuals: list[dict] | None = None) -> dict:
    """Roll up only defensible, exactly compatible units and disclose every exclusion."""
    groups: dict[tuple[str, str], dict] = defaultdict(lambda: {
        "closed": 0.0, "commit": 0.0, "best_case": 0.0, "pipeline": 0.0,
        "weighted_open": 0.0, "missing_probability_count": 0,
    })
    amount_exclusions, weighting_exclusions = [], []
    terminal_entry_ids = {row["entry_id"] for row in closed_actuals or []}
    for row in entries:
        if row["category"] == "omitted" or row["id"] in terminal_entry_ids:
            continue
        if row.get("amount") is None:
            amount_exclusions.append({"entry_id": row["id"], "reason": "forecast amount is not recorded"})
            continue
        if not row.get("currency") or not row.get("price_basis"):
            amount_exclusions.append({"entry_id": row["id"], "reason": "forecast currency or price basis is unknown"})
            continue
        key = (row["currency"], row["price_basis"])
        groups[key][row["category"]] += row["amount"]
        if row.get("probability") is None:
            groups[key]["missing_probability_count"] += 1
            weighting_exclusions.append({"entry_id": row["id"], "reason": "probability is not recorded"})
        else:
            groups[key]["weighted_open"] += row["amount"] * row["probability"]
    for row in closed_actuals or []:
        if not row["counts_as_closed"]:
            continue
        if row.get("amount") is None or not row.get("currency") or not row.get("price_basis"):
            amount_exclusions.append({"entry_id": row.get("entry_id"), "source_id": row.get("source_id"),
                                      "reason": "closed actual amount units are unavailable"})
            continue
        groups[(row["currency"], row["price_basis"])]["closed"] += row["amount"]
    return {
        "groups": [{"currency": key[0], "price_basis": key[1], **value}
                   for key, value in sorted(groups.items())],
        "amount_exclusions": amount_exclusions,
        "weighting_exclusions": weighting_exclusions,
    }


def submit(conn: sqlite3.Connection, period_id: str) -> dict:
    period = _period(conn, period_id)
    if period["status"] == "closed":
        raise HTTPException(409, "closed forecast periods cannot receive new submissions")
    entries = repo.list_rows(conn, "forecast_entries", where="period_id=? ORDER BY account_id,id", params=(period_id,))
    prior = conn.execute("SELECT * FROM forecast_submissions WHERE period_id=? ORDER BY submitted_at DESC LIMIT 1", (period_id,)).fetchone()
    baseline = "previous_submission" if prior else ("opening" if period["status"] in ("locked", "closed") else "none")
    baseline_rows = []
    if prior:
        baseline_rows = [repo.row_to_dict(r) for r in conn.execute("SELECT * FROM forecast_submission_lines WHERE submission_id=?", (prior["id"],))]
    elif baseline == "opening":
        baseline_rows = [repo.row_to_dict(r) for r in conn.execute("SELECT l.* FROM forecast_opening_lines l JOIN forecast_opening_snapshots s ON s.id=l.snapshot_id WHERE s.period_id=?", (period_id,))]
    before_by_entry = {r["entry_id"]: r for r in baseline_rows}
    movement = []
    for entry in (entries if baseline != "none" else []):
        before = before_by_entry.pop(entry["id"], None)
        if before is None:
            movement.append({"entry_id": entry["id"], "kind": "added", "category_before": None, "category_after": entry["category"]})
        elif before["category"] != entry["category"] or before.get("amount") != entry.get("amount") or before.get("probability") != entry.get("probability"):
            movement.append({"entry_id": entry["id"], "kind": "changed", "category_before": before["category"],
                             "category_after": entry["category"], "amount_before": before.get("amount"),
                             "amount_after": entry.get("amount"), "probability_before": before.get("probability"),
                             "probability_after": entry.get("probability")})
    movement += [{"entry_id": entry_id, "kind": "removed", "category_before": row["category"], "category_after": None}
                 for entry_id, row in before_by_entry.items()]
    evidence_by_entry = {entry["id"]: evidence(conn, entry["id"]) for entry in entries}
    unsupported = [evidence_by_entry[e["id"]] for e in entries
                   if e["category"] in ("commit", "best_case") and not evidence_by_entry[e["id"]]["supported"]]
    help_asks = [repo.row_to_dict(r) for r in conn.execute(
        "SELECT a.* FROM internal_asks a JOIN forecast_entries e ON e.id=a.forecast_entry_id "
        "WHERE e.period_id=? AND a.archived=0 AND a.status NOT IN ('delivered','declined') ORDER BY a.needed_by",
        (period_id,))]
    rollup = totals(entries, _closed_actuals(conn, period, entries))
    lines = [f"# Forecast — {period['name']}", "", f"Data current through {now_utc()[:10]}", "",
             "## Movement", "", ("First submission — no prior baseline." if baseline == "none" else f"Baseline: {baseline.replace('_',' ')}."), ""]
    lines += ([f"- {m['entry_id']}: {m['kind']} · {m.get('category_before') or '—'} → {m.get('category_after') or '—'}" for m in movement] or ["- No movement from baseline."])
    lines += ["", "## Totals", ""]
    for g in rollup["groups"]:
        lines.append(f"- {g['currency']} / {g['price_basis']}: Closed {g['closed']:,.2f}; Commit {g['commit']:,.2f}; Best Case {g['best_case']:,.2f}; Pipeline {g['pipeline']:,.2f}; weighted open {g['weighted_open']:,.2f}; {g['missing_probability_count']} excluded from weighting")
    if not rollup["groups"]:
        lines.append("- No amounts have defensible units.")
    lines += ["", "## Data exclusions", ""]
    lines += ([f"- {x.get('entry_id') or x.get('source_id')}: {x['reason']}" for x in
               rollup["amount_exclusions"] + rollup["weighting_exclusions"]] or ["- None"])
    lines += ["", "## Unsupported calls", ""]
    lines += ([f"- {x['entry_id']}: " + "; ".join(r["explanation"] for r in x["missing"]) for x in unsupported] or ["- None"])
    lines += ["", "## Leadership help needed", ""]
    lines += ([f"- {a['need']} — needed {a['needed_by']} (ask {a['id']})" for a in help_asks] or ["- None"])
    doc = repo.insert(conn, "generated_documents", {"kind": "forecast_submission", "title": f"Forecast — {period['name']}",
        "body_markdown": "\n".join(lines), "status": "draft", "generated_at": now_utc(),
        "data_current_through": now_utc()[:10], "audience": "internal", "audience_profile": "leadership"}, object_type="generated_document")
    ts, submission_id = now_utc(), new_id()
    with conn:
        conn.execute("INSERT INTO forecast_submissions(id,period_id,document_id,submitted_at,actor,baseline_kind,prior_submission_id,created_at) VALUES (?,?,?,?,?,?,?,?)",
                     (submission_id, period_id, doc["id"], ts, operator(conn), baseline, prior["id"] if prior else None, ts))
        for entry in entries:
            manifest = _source_manifest(conn, entry["id"])
            line_id = new_id(); ev = evidence_by_entry[entry["id"]]
            conn.execute("INSERT INTO forecast_submission_lines(id,submission_id,entry_id,account_id,target_type,target_id,category,amount,currency,price_basis,probability,evidence_json,help_needed_note,source_manifest_json,created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                         (line_id, submission_id, entry["id"], entry["account_id"], "opportunity" if entry.get("opportunity_id") else "renewal", entry.get("opportunity_id") or entry.get("contract_version_id"), entry["category"], entry.get("amount"), entry.get("currency"), entry.get("price_basis"), entry.get("probability"), json.dumps(ev, sort_keys=True), entry.get("help_needed_note"), json.dumps(manifest, sort_keys=True), ts))
            conn.execute("INSERT INTO generated_document_sources(id,document_id,record_type,record_id,record_version,inclusion_reason,visibility_class,created_at) VALUES (?,?,?,?,?,?,?,?)",
                         (new_id(), doc["id"], "forecast_entry", entry["id"], entry["updated_at"], "period entry", "internal", ts))
        for ask in help_asks:
            conn.execute("INSERT INTO generated_document_sources(id,document_id,record_type,record_id,record_version,inclusion_reason,visibility_class,created_at) VALUES (?,?,?,?,?,?,?,?)",
                         (new_id(), doc["id"], "internal_ask", ask["id"], ask["updated_at"], "forecast help needed", "internal", ts))
    return {"submission": repo.row_to_dict(conn.execute("SELECT * FROM forecast_submissions WHERE id=?", (submission_id,)).fetchone()), "document": doc, "totals": rollup["groups"], "amount_exclusions": rollup["amount_exclusions"], "weighting_exclusions": rollup["weighting_exclusions"], "movement": movement, "unsupported": unsupported, "help_needed": help_asks}


def close_period(conn: sqlite3.Connection, period_id: str) -> dict:
    period = _period(conn, period_id)
    if period["status"] != "locked":
        raise HTTPException(409, "only a locked period can close")
    ts = now_utc()
    with conn:
        conn.execute("UPDATE forecast_periods SET status='closed',closed_at=?,closed_by=?,updated_at=? WHERE id=?", (ts, operator(conn), ts, period_id))
    return {"period": repo.get_row(conn, "forecast_periods", period_id), "calibration": calibration(conn, period_id)}


def calibration(conn: sqlite3.Connection, period_id: str) -> dict:
    period = _period(conn, period_id)
    lines = [repo.row_to_dict(r) for r in conn.execute("SELECT l.* FROM forecast_opening_lines l JOIN forecast_opening_snapshots s ON s.id=l.snapshot_id WHERE s.period_id=?", (period_id,))]
    out = {k: {"closed": 0, "not_closed": 0, "opening": 0, "unresolved": 0, "entry_ids": []}
           for k in ("commit", "best_case", "pipeline")}
    amounts, exclusions = defaultdict(lambda: {"forecast": 0.0, "actual": 0.0, "count": 0}), []
    for line in lines:
        if line["category"] not in out:
            continue
        bucket = out[line["category"]]; bucket["opening"] += 1; bucket["entry_ids"].append(line["entry_id"])
        outcome_state, actual = "unresolved", None
        if line["target_type"] == "opportunity":
            opp = conn.execute("SELECT status,outcome FROM expansion_opportunities WHERE id=?", (line["target_id"],)).fetchone()
            actual = conn.execute("SELECT amount,currency,price_basis FROM revenue_events WHERE account_id=? AND opportunity_id=? AND kind='expansion' AND effective_on BETWEEN ? AND ? AND archived=0 ORDER BY effective_on DESC LIMIT 1", (line["account_id"], line["target_id"], period["starts_on"], period["ends_on"])).fetchone()
            # Opportunities have no dated outcome column in the legacy schema. Require the
            # won state *and* a dated expansion event inside the period; updated_at is not a
            # commercial outcome date and must never be used as one.
            if opp and opp["status"] == "closed" and opp["outcome"] == "lost":
                outcome_state = "not_closed"
            elif opp and opp["status"] == "closed" and opp["outcome"] == "won" and actual:
                outcome_state = "closed"
        else:
            outcome = conn.execute("SELECT outcome,actual_amount,currency,price_basis FROM renewal_outcome_events WHERE contract_version_id=? AND occurred_on BETWEEN ? AND ? AND archived=0 ORDER BY occurred_on DESC LIMIT 1", (line["target_id"], period["starts_on"], period["ends_on"])).fetchone()
            if outcome and outcome["outcome"] == "renewed":
                outcome_state = "closed"
            elif outcome and outcome["outcome"] == "churned":
                outcome_state = "not_closed"
            actual = outcome
        bucket[outcome_state] += 1
        if outcome_state == "closed" and actual and actual["amount" if line["target_type"] == "opportunity" else "actual_amount"] is not None and actual["currency"] == line.get("currency") and actual["price_basis"] == line.get("price_basis"):
            key = (line.get("currency"), line.get("price_basis")); amounts[key]["forecast"] += line.get("amount") or 0; amounts[key]["actual"] += actual["amount" if line["target_type"] == "opportunity" else "actual_amount"]; amounts[key]["count"] += 1
        elif outcome_state == "closed":
            exclusions.append({"entry_id": line["entry_id"], "reason": "actual amount units unavailable or incompatible"})
    for value in out.values():
        value["display"] = (f"{value['closed']} closed · {value['not_closed']} not closed · "
                            f"{value['unresolved']} unresolved of {value['opening']}")
    return {"period_id": period_id, "categories": out,
            "amounts": [{"currency": k[0], "price_basis": k[1], **v} for k, v in amounts.items()],
            "amount_exclusions": exclusions}
