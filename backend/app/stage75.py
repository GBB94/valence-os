"""Stage 7.5 services: qualification, operational triggers, renewal, and growth plans.

The module deliberately derives renewal and qualification state from canonical records. It
stores only operator-authored links and assumptions; no composite score and no duplicate
renewal-health field can drift away from the evidence beneath it.
"""
from __future__ import annotations

import json
import sqlite3
from datetime import date, timedelta

from fastapi import HTTPException

from . import audit, expansion, repo
from .db import new_id, now_utc


def _today() -> date:
    return date.fromisoformat(now_utc()[:10])


def _belongs(conn: sqlite3.Connection, table: str, row_id: str | None,
             account_id: str, label: str) -> dict | None:
    if not row_id:
        return None
    row = repo.get_row(conn, table, row_id)
    if row.get("account_id") != account_id:
        raise HTTPException(422, f"{label} belongs to a different account")
    return row


def _compliance(conn: sqlite3.Connection, opportunity: dict) -> dict:
    program_id = opportunity.get("qualification_program_id")
    if not program_id:
        return {"filled": False, "status": None, "program_id": None, "items": 0,
                "reason": "No program selected for the compliance path."}
    rows = repo.list_rows(conn, "compliance_items", where="program_id=?", params=(program_id,))
    if not rows:
        return {"filled": False, "status": None, "program_id": program_id, "items": 0,
                "reason": "The selected program has no compliance path on record."}
    statuses = {r["status"] for r in rows}
    status = ("blocked" if "blocked" in statuses else
              "clear" if statuses <= {"complete", "not_applicable"} else "in_progress")
    return {"filled": True, "status": status, "program_id": program_id,
            "items": len(rows), "reason": None}


def qualification(conn: sqlite3.Connection, opportunity: dict | str) -> dict:
    if isinstance(opportunity, str):
        opportunity = repo.get_row(conn, "expansion_opportunities", opportunity)
    account_id = opportunity["account_id"]
    target = _belongs(conn, "value_targets", opportunity.get("qualification_value_target_id"),
                      account_id, "value target")
    calendar = _belongs(conn, "ask_calendars", opportunity.get("qualification_ask_calendar_id"),
                        account_id, "ask calendar")
    champion_id = opportunity.get("qualification_champion_person_id")
    champion = _belongs(conn, "persons", champion_id, account_id, "champion")
    champion_validated = bool(champion_id and conn.execute(
        "SELECT 1 FROM champion_candidates cc WHERE cc.account_id=? AND cc.person_id=? AND cc.archived=0 "
        "AND cc.stage IN ('validate','arm','maintain') AND EXISTS (SELECT 1 FROM advocacy_events ae "
        "WHERE ae.person_id=cc.person_id AND ae.archived=0 AND ae.kind IN "
        "('advocacy_without_us','secured_meeting','defended_us','presented_internally'))",
        (account_id, champion_id)).fetchone())
    budget_owner = _belongs(conn, "persons", opportunity.get("budget_owner_person_id"),
                            account_id, "budget owner")
    compliance = _compliance(conn, opportunity)
    slots = {
        "metric": {"filled": bool(target), "id": target["id"] if target else None,
                   "label": target.get("notes") if target else None},
        "budget_owner": {"filled": bool(budget_owner), "id": budget_owner["id"] if budget_owner else None,
                         "label": budget_owner["name"] if budget_owner else None},
        "decision_process": {"filled": bool(calendar), "id": calendar["id"] if calendar else None,
                             "label": calendar["name"] if calendar else None},
        "champion": {"filled": champion_validated, "id": champion_id,
                     "label": champion["name"] if champion else None,
                     "reason": None if champion_validated else
                               ("Selected person is not validated in the champion pipeline."
                                if champion else "No validated champion selected.")},
        "compliance_path": compliance,
    }
    empty = [name for name, slot in slots.items() if not slot["filled"]]
    return {"slots": slots, "filled_count": 5 - len(empty), "empty_slots": empty,
            "fully_qualified": not empty}


def set_qualification(conn: sqlite3.Connection, opportunity_id: str,
                      values: dict, supplied: set[str]) -> dict:
    opportunity = repo.get_row(conn, "expansion_opportunities", opportunity_id)
    account_id = opportunity["account_id"]
    mapping = {
        "value_target_id": ("qualification_value_target_id", "value_targets", "value target"),
        "ask_calendar_id": ("qualification_ask_calendar_id", "ask_calendars", "ask calendar"),
        "champion_person_id": ("qualification_champion_person_id", "persons", "champion"),
        "program_id": ("qualification_program_id", "programs", "program"),
        "budget_owner_person_id": ("budget_owner_person_id", "persons", "budget owner"),
    }
    changes = {}
    for api_name in supplied:
        column, table, label = mapping[api_name]
        value = values.get(api_name)
        linked = _belongs(conn, table, value, account_id, label)
        if api_name == "value_target_id" and linked and linked["status"] != "active":
            raise HTTPException(422, "qualification value target must be active")
        if api_name == "ask_calendar_id" and linked and linked.get("opportunity_id") not in (None, opportunity_id):
            raise HTTPException(422, "ask calendar is already linked to another opportunity")
        changes[column] = value
    champion_id = changes.get("qualification_champion_person_id")
    if champion_id and not conn.execute(
            "SELECT 1 FROM champion_candidates cc WHERE cc.account_id=? AND cc.person_id=? AND cc.archived=0 "
            "AND cc.stage IN ('validate','arm','maintain') AND EXISTS (SELECT 1 FROM advocacy_events ae "
            "WHERE ae.person_id=cc.person_id AND ae.archived=0 AND ae.kind IN "
            "('advocacy_without_us','secured_meeting','defended_us','presented_internally'))",
            (account_id, champion_id)).fetchone():
        raise HTTPException(422, "champion must be validated in the champion pipeline")
    if changes:
        before = dict(opportunity); changes["updated_at"] = now_utc()
        with conn:
            conn.execute("UPDATE expansion_opportunities SET " +
                         ",".join(f"{k}=?" for k in changes) + " WHERE id=?",
                         (*changes.values(), opportunity_id))
            calendar_id = changes.get("qualification_ask_calendar_id")
            if calendar_id:
                calendar = repo.get_row(conn, "ask_calendars", calendar_id)
                if calendar.get("opportunity_id") is None:
                    conn.execute("UPDATE ask_calendars SET opportunity_id=?,updated_at=? WHERE id=?",
                                 (opportunity_id, changes["updated_at"], calendar_id))
                    audit.record(conn, object_type="ask_calendar", object_id=calendar_id,
                                 action="update", before=calendar,
                                 after={**calendar, "opportunity_id": opportunity_id})
            after = repo.get_row(conn, "expansion_opportunities", opportunity_id)
            audit.record(conn, object_type="expansion_opportunity", object_id=opportunity_id,
                         action="update", before=before, after=after)
    row = repo.get_row(conn, "expansion_opportunities", opportunity_id)
    return {"opportunity": row, "qualification": qualification(conn, row)}


def create_agreement(conn: sqlite3.Connection, values: dict) -> dict:
    account_id = values["account_id"]
    _belongs(conn, "contract_versions", values["contract_version_id"], account_id, "contract")
    _belongs(conn, "value_targets", values["value_target_id"], account_id, "value target")
    _belongs(conn, "persons", values.get("budget_owner_person_id"), account_id, "budget owner")
    if values.get("source_interaction_id"):
        interaction = repo.get_row(conn, "interactions", values["source_interaction_id"])
        if interaction["account_id"] != account_id:
            raise HTTPException(422, "source interaction belongs to a different account")
    return repo.insert(conn, "operational_agreements", values, object_type="operational_agreement")


def agreements(conn: sqlite3.Connection, account_id: str) -> dict:
    repo.get_row(conn, "accounts", account_id)
    rows = repo.list_rows(conn, "operational_agreements",
                          where="account_id=? ORDER BY status,effective_on DESC", params=(account_id,))
    events = {r["agreement_id"]: dict(r) for r in conn.execute(
        "SELECT * FROM operational_agreement_events WHERE account_id=?", (account_id,))}
    people = {r["id"]: r["name"] for r in repo.list_rows(conn, "persons", where="1=1")}
    out = []
    for row in rows:
        target = repo.get_row(conn, "value_targets", row["value_target_id"])
        realization = expansion.target_realization(conn, target)
        out.append({**row, "target": target, "realization": realization,
                    "budget_owner_name": people.get(row.get("budget_owner_person_id")),
                    "event": events.get(row["id"]),
                    "contractual": row["source_kind"] == "signed_paper"})
    return {"account_id": account_id, "agreements": out,
            "gap": "No pre-agreed triggers on the current contract." if not rows else None}


def evaluate_agreements(conn: sqlite3.Connection) -> dict:
    today, opened = _today(), []
    rows = conn.execute("SELECT * FROM operational_agreements WHERE archived=0 AND status='active'").fetchall()
    for raw in rows:
        agreement = dict(raw)
        if date.fromisoformat(agreement["effective_on"]) > today:
            continue
        if agreement.get("expires_on") and date.fromisoformat(agreement["expires_on"]) < today:
            with conn:
                conn.execute("UPDATE operational_agreements SET status='expired',updated_at=? WHERE id=?",
                             (now_utc(), agreement["id"]))
                audit.record(conn, object_type="operational_agreement", object_id=agreement["id"],
                             action="update", before={"status": "active"}, after={"status": "expired"})
            continue
        if conn.execute("SELECT 1 FROM operational_agreement_events WHERE agreement_id=?",
                        (agreement["id"],)).fetchone():
            continue
        target = repo.get_row(conn, "value_targets", agreement["value_target_id"])
        realized = expansion.target_realization(conn, target)
        if realized["status"] != "realized" or realized.get("value") is None or not realized.get("current_through"):
            continue
        risk_count = len(expansion.value_gaps(conn, agreement["account_id"]))
        risk_note = (f"{risk_count} value gap{'s' if risk_count != 1 else ''} remain visible; "
                     "the pre-agreed trigger still fires." if risk_count else None)
        ts, event_id = now_utc(), new_id()
        due = (today + timedelta(days=agreement["action_window_days"])).isoformat()
        with conn:
            conn.execute("INSERT INTO operational_agreement_events "
                         "(id,agreement_id,account_id,value_at_fire,threshold_at_fire,freshness_as_of,"
                         "risk_note,status,fired_at,action_due_on,created_at,updated_at) "
                         "VALUES (?,?,?,?,?,?,?,'fired',?,?,?,?)",
                         (event_id, agreement["id"], agreement["account_id"], realized["value"],
                          target["target_value"], realized["current_through"], risk_note, ts, due, ts, ts))
            audit.record(conn, object_type="operational_agreement_event", object_id=event_id,
                         action="create", after={"agreement_id": agreement["id"], "status": "fired",
                                                 "action_due_on": due})
            for play in conn.execute("SELECT * FROM play_definitions WHERE archived=0 AND active=1 "
                                     "AND trigger_kind='expansion_signal'"):
                run_id = new_id()
                action = (f"{agreement['agreed_process']} Unlock {agreement['seat_band_min']}–"
                          f"{agreement['seat_band_max']} seats by {due}.")
                conn.execute("INSERT INTO play_runs "
                             "(id,play_id,account_id,trigger_context,action_text,status,dedupe_key,fired_at) "
                             "VALUES (?,?,?,?,?,'fired',?,?)",
                             (run_id, play["id"], agreement["account_id"],
                              f"Pre-agreed trigger met: {agreement['name']}", action,
                              f"agreement:{event_id}:{play['id']}", ts))
                audit.record(conn, object_type="play_run", object_id=run_id, action="create",
                             after={"agreement_event_id": event_id, "action_text": action})
        opened.append(event_id)
    return {"fired": len(opened), "event_ids": opened}


def action_agreement_event(conn: sqlite3.Connection, event_id: str) -> dict:
    event = conn.execute("SELECT * FROM operational_agreement_events WHERE id=?", (event_id,)).fetchone()
    if not event:
        raise HTTPException(404, "operational agreement event not found")
    if event["status"] != "fired":
        raise HTTPException(409, f"agreement event is already {event['status']}")
    agreement = repo.get_row(conn, "operational_agreements", event["agreement_id"])
    ts, opportunity_id = now_utc(), new_id()
    expected = ((agreement.get("unit_price") or 0) * agreement["seat_band_min"] or None)
    values = {
        "id": opportunity_id, "account_id": agreement["account_id"],
        "name": f"Pre-agreed — {agreement['name']}",
        "target_seats": agreement["seat_band_max"], "expected_value": expected,
        "budget_owner_person_id": agreement.get("budget_owner_person_id"),
        "qualification_value_target_id": agreement["value_target_id"],
        "supporting_evidence": (f"Operational agreement fired at {event['value_at_fire']} against "
                                f"{event['threshold_at_fire']} (through {event['freshness_as_of']})."),
        "next_action": agreement["agreed_process"], "created_at": ts, "updated_at": ts,
    }
    with conn:
        conn.execute(f"INSERT INTO expansion_opportunities ({','.join(values)}) "
                     f"VALUES ({','.join('?' for _ in values)})", tuple(values.values()))
        audit.record(conn, object_type="expansion_opportunity", object_id=opportunity_id,
                     action="create", after=values)
        conn.execute("UPDATE operational_agreement_events SET status='actioned',opportunity_id=?,"
                     "actioned_at=?,updated_at=? WHERE id=?", (opportunity_id, ts, ts, event_id))
        audit.record(conn, object_type="operational_agreement_event", object_id=event_id,
                     action="update", before={"status": "fired"},
                     after={"status": "actioned", "opportunity_id": opportunity_id})
    return {"event_id": event_id, "opportunity": repo.get_row(conn, "expansion_opportunities", opportunity_id)}


def dismiss_agreement_event(conn: sqlite3.Connection, event_id: str, reason: str) -> dict:
    event = conn.execute("SELECT * FROM operational_agreement_events WHERE id=?", (event_id,)).fetchone()
    if not event:
        raise HTTPException(404, "operational agreement event not found")
    if event["status"] != "fired":
        raise HTTPException(409, f"agreement event is already {event['status']}")
    ts = now_utc()
    with conn:
        conn.execute("UPDATE operational_agreement_events SET status='dismissed',dismissal_reason=?,"
                     "updated_at=? WHERE id=?", (reason, ts, event_id))
        audit.record(conn, object_type="operational_agreement_event", object_id=event_id,
                     action="update", before={"status": "fired"},
                     after={"status": "dismissed", "reason": reason})
    return dict(conn.execute("SELECT * FROM operational_agreement_events WHERE id=?", (event_id,)).fetchone())


def renewal_center(conn: sqlite3.Connection, account_id: str, contract_id: str | None = None) -> dict:
    account = repo.get_row(conn, "accounts", account_id)
    if contract_id:
        contract = _belongs(conn, "contract_versions", contract_id, account_id, "contract")
    else:
        contract = repo.row_to_dict(conn.execute(
            "SELECT * FROM contract_versions WHERE account_id=? AND archived=0 AND is_current=1 "
            "ORDER BY created_at DESC LIMIT 1", (account_id,)).fetchone())
    if not contract:
        return {"account_id": account_id, "contract": None, "gap": "No current contract on record."}
    renewal_on = date.fromisoformat(contract["renewal_date"]) if contract.get("renewal_date") else None
    notice_on = (renewal_on - timedelta(days=contract.get("notice_period_days") or 0)
                 if renewal_on else None)
    decision = contract.get("overlay_expected_decision_date") or contract.get("renewal_date")
    led = expansion.ledger(conn, account_id)
    rollup = expansion.rollup(conn, account_id)
    stories = repo.list_rows(conn, "value_stories",
                             where="account_id=? AND is_negative=0 ORDER BY created_at DESC",
                             params=(account_id,))[:5]
    program_ids = [p["id"] for p in repo.list_rows(conn, "programs", where="account_id=?", params=(account_id,))]
    risks = []
    if program_ids:
        q = ",".join("?" * len(program_ids))
        risks = [dict(r) for r in conn.execute(
            f"SELECT * FROM risks WHERE archived=0 AND status='open' AND program_id IN ({q})", program_ids)]
    opportunities = repo.list_rows(conn, "expansion_opportunities",
                                   where="account_id=? AND status='open' ORDER BY created_at DESC",
                                   params=(account_id,))
    qualified = [{**o, "qualification": qualification(conn, o)} for o in opportunities]
    agreement_view = agreements(conn, account_id)
    fiscal = repo.row_to_dict(conn.execute("SELECT * FROM fiscal_maps WHERE account_id=?",
                                           (account_id,)).fetchone())
    return {
        "account_id": account_id, "account_name": account["name"], "contract": contract,
        "timeline": {"today": _today().isoformat(),
                     "notice_date": notice_on.isoformat() if notice_on else None,
                     "renewal_date": contract.get("renewal_date"), "decision_date": decision,
                     "days_to_notice": (notice_on - _today()).days if notice_on else None,
                     "days_to_decision": ((date.fromisoformat(decision) - _today()).days if decision else None)},
        "fiscal_map": fiscal,
        "value": {"counts": led["counts"], "gaps": led["value_gaps"]},
        "penetration": rollup, "stories": stories, "risks": risks,
        "alternative_landscape": account.get("incumbent_note"),
        "opportunities": qualified,
        "eligible_expansions": [o for o in qualified if o["qualification"]["fully_qualified"] and
                                o["qualification"]["slots"]["compliance_path"]["status"] != "blocked"],
        "agreement_gap": agreement_view["gap"],
    }


def create_growth_plan(conn: sqlite3.Connection, values: dict) -> dict:
    repo.get_row(conn, "accounts", values["account_id"])
    ts, plan_id = now_utc(), new_id()
    row = {"id": plan_id, **values, "created_at": ts, "updated_at": ts}
    with conn:
        current = conn.execute("SELECT * FROM account_growth_plans WHERE account_id=? AND status='active' "
                               "AND archived=0", (values["account_id"],)).fetchone()
        if current:
            conn.execute("UPDATE account_growth_plans SET status='superseded',updated_at=? WHERE id=?",
                         (ts, current["id"]))
            audit.record(conn, object_type="account_growth_plan", object_id=current["id"], action="update",
                         before={"status": "active"}, after={"status": "superseded"})
        conn.execute(f"INSERT INTO account_growth_plans ({','.join(row)}) "
                     f"VALUES ({','.join('?' for _ in row)})", tuple(row.values()))
        audit.record(conn, object_type="account_growth_plan", object_id=plan_id,
                     action="create", after=row)
    return repo.get_row(conn, "account_growth_plans", plan_id)


def create_growth_line(conn: sqlite3.Connection, values: dict) -> dict:
    plan = repo.get_row(conn, "account_growth_plans", values["plan_id"])
    values = {"account_id": plan["account_id"], **values}
    _validate_growth_cell(conn, values)
    _normalize_line_currency(values)
    if values.get("status") == "funded":
        values["funded_on"] = now_utc()[:10]
    return repo.insert(conn, "growth_plan_lines", values, object_type="growth_plan_line")


def patch_growth_line(conn: sqlite3.Connection, line_id: str, changes: dict,
                      supplied: set[str]) -> dict:
    line = repo.get_row(conn, "growth_plan_lines", line_id)
    allowed = {k: v for k, v in changes.items() if k in supplied}
    if "cell_id" in supplied:
        _validate_growth_cell(conn, {**line, **allowed})
    _normalize_line_currency(allowed)
    if "probability" in supplied and not {"probability_author", "probability_assessed_on"} <= supplied:
        raise HTTPException(422, "changing probability requires a new author and assessment date")
    if allowed.get("client_visible") and not (allowed.get("source_reference_id") or
                                                line.get("source_reference_id")):
        raise HTTPException(422, "shared growth-plan lines require a source reference")
    if allowed.get("status") == "funded" and line.get("status") != "funded":
        allowed["funded_on"] = now_utc()[:10]
    elif "status" in supplied and allowed.get("status") != "funded":
        # A correction away from funded must also clear the dated fact; otherwise portfolio
        # velocity continues to count a line the operator explicitly retracted.
        allowed["funded_on"] = None
    return repo.patch(conn, "growth_plan_lines", line_id, allowed,
                      object_type="growth_plan_line", allow_null={"ask_date","source_reference_id","notes",
                                                                   "cell_id","funded_on"})


def _validate_growth_cell(conn: sqlite3.Connection, line: dict) -> None:
    """A velocity link is valid only when account and row identity both match."""
    if not line.get("cell_id"):
        return
    cell = repo.get_row(conn, "whitespace_cells", line["cell_id"])
    if (cell["account_id"] != line["account_id"]
            or cell.get("segment_id") != line.get("segment_id")
            or cell.get("view_id") != line.get("view_id")):
        raise HTTPException(422, "growth line cell belongs to a different account or population")


def _normalize_line_currency(values: dict) -> None:
    currency = values.get("seat_price_currency")
    if currency is not None:
        currency = currency.upper()
        if len(currency) != 3 or not currency.isalpha():
            raise HTTPException(422, "seat_price_currency must be a three-letter ISO 4217 code")
        values["seat_price_currency"] = currency


def _members(conn: sqlite3.Connection, line: dict) -> set[str]:
    if line.get("segment_id"):
        return {line["segment_id"]}
    return {r["segment_id"] for r in conn.execute(
        "SELECT segment_id FROM population_view_segments WHERE view_id=?", (line["view_id"],))}


def growth_plan(conn: sqlite3.Connection, account_id: str) -> dict:
    repo.get_row(conn, "accounts", account_id)
    plan = repo.row_to_dict(conn.execute(
        "SELECT * FROM account_growth_plans WHERE account_id=? AND status='active' AND archived=0 "
        "ORDER BY created_at DESC LIMIT 1", (account_id,)).fetchone())
    if not plan:
        return {"account_id": account_id, "plan": None, "lines": [],
                "gap": "No active growth plan."}
    lines = repo.list_rows(conn, "growth_plan_lines",
                           where="plan_id=? ORDER BY ask_date,name", params=(plan["id"],))
    names = {r["id"]: r["name"] for r in repo.list_rows(conn, "persons", where="1=1")}
    populations = {r["id"]: r["name"] for r in repo.list_rows(
        conn, "population_segments", where="account_id=?", params=(account_id,))}
    populations.update({r["id"]: r["name"] for r in repo.list_rows(
        conn, "population_views", where="account_id=?", params=(account_id,))})
    use_cases = {r["id"]: r["name"] for r in repo.list_rows(conn, "use_cases", where="1=1")}
    cells = {r["id"]: r for r in repo.list_rows(
        conn, "whitespace_cells", where="account_id=?", params=(account_id,))}
    enriched = []
    for line in lines:
        linked_cell = cells.get(line.get("cell_id"))
        enriched.append({**line, "population": populations.get(line.get("segment_id") or line.get("view_id")),
                         "budget_owner_name": names.get(line.get("budget_owner_person_id")),
                         "cell_use_case": use_cases.get(linked_cell["use_case_id"]) if linked_cell else None})
    active = [l for l in enriched if l["status"] not in ("declined", "slipped")]
    conflicts = []
    for i, left in enumerate(active):
        lm = _members(conn, left)
        for right in active[i + 1:]:
            overlap = sorted(lm & _members(conn, right))
            if overlap:
                conflicts.append({"left_id": left["id"], "left": left["name"],
                                  "right_id": right["id"], "right": right["name"],
                                  "segment_ids": overlap})
    additive = not conflicts
    current = expansion.rollup(conn, account_id)["paid_seats"]
    named = sum(l["seat_count"] for l in active) if additive else None
    committed = (sum(l["seat_count"] for l in active if l["status"] in ("committed", "funded"))
                 if additive else None)
    weighted = (round(sum(l["seat_count"] * l["probability"] for l in active), 1)
                if additive else None)
    target = plan["target_seats"]
    return {"account_id": account_id, "plan": plan, "lines": enriched,
            "conflicts": conflicts, "rollup": {
                "current_seats": current, "target_seats": target, "named_seats": named,
                "committed_seats": committed, "probability_weighted_seats": weighted,
                "unfunded_gap": max(target - current - committed, 0) if additive else None,
                "weighted_gap": max(target - current - weighted, 0) if additive else None,
                "additive": additive,
                "basis": ("No population overlap among active lines." if additive else
                          "Totals withheld: two or more lines overlap the same base population.")}}
