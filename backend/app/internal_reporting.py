"""Internal generated outputs, no-surprises validation, and drillable book analytics."""
from __future__ import annotations

import sqlite3
import json
from collections import defaultdict
from datetime import date
from pathlib import Path
from statistics import median
import yaml

from fastapi import HTTPException

from . import audit, expansion, generators, queue, repo, stage75
from .db import new_id, now_utc
from .internal_forecast import _closed_actuals, calibration, totals
from .internal_asks import elapsed_business_hours
from .internal_reviews import account_brief_data, challenge_sheet, generate_account_brief


def sync_templates(conn: sqlite3.Connection) -> None:
    """Install versioned presentation metadata; generators keep the query allow-list."""
    path = Path(__file__).resolve().parent / "templates" / "internal_reports.yaml"
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    ts = now_utc()
    with conn:
        for item in data.get("templates", []):
            conn.execute("INSERT OR IGNORE INTO report_templates(id,kind,name,audience_profile,headings_json,effective_on,author,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?)",
                         (item["id"], item["kind"], item["name"], item["audience_profile"],
                          json.dumps(item.get("headings", [])), str(item["effective_on"]), item["author"], ts, ts))


def _latest_assessment(conn: sqlite3.Connection, account_id: str, dimension: str) -> dict | None:
    return repo.row_to_dict(conn.execute(
        "SELECT * FROM account_status_assessments WHERE account_id=? AND dimension=? "
        "AND archived=0 ORDER BY assessed_on DESC,created_at DESC LIMIT 1",
        (account_id, dimension),
    ).fetchone())


def _origin(origin_type: str, row: dict, *, account_id: str, account_name: str,
            label: str, record_type: str | None = None, record_id: str | None = None,
            record_version: str | None = None) -> dict:
    return {
        "type": origin_type,
        "id": row["id"],
        "account_id": account_id,
        "account_name": account_name,
        "label": label,
        "record_type": record_type or origin_type,
        "record_id": record_id or row["id"],
        "record_version": record_version or row.get("updated_at") or row.get("created_at"),
    }


def _eligible_red_origins(conn: sqlite3.Connection) -> list[dict]:
    origins: list[dict] = []
    accounts = {r["id"]: r for r in repo.list_rows(conn, "accounts", where="1=1")}
    for row in conn.execute(
        "SELECT r.*,p.account_id FROM risks r JOIN programs p ON p.id=r.program_id "
        "WHERE r.archived=0 AND r.status='open' AND (r.severity='high' OR r.is_blocker=1)"
    ):
        item, account = repo.row_to_dict(row), accounts[row["account_id"]]
        origins.append(_origin("risk", item, account_id=account["id"], account_name=account["name"],
                               label=f"Open {item['severity']} risk — {item['description']}"))
    for row in conn.execute(
        "SELECT i.*,p.account_id FROM issues i JOIN programs p ON p.id=i.program_id "
        "WHERE i.archived=0 AND i.status='open' AND i.is_blocker=1"
    ):
        item, account = repo.row_to_dict(row), accounts[row["account_id"]]
        origins.append(_origin("issue", item, account_id=account["id"], account_name=account["name"],
                               label=f"Open blocker issue — {item['description']}"))
    for account in accounts.values():
        for dimension in ("delivery", "commercial"):
            item = _latest_assessment(conn, account["id"], dimension)
            if item and item["value"] == "off_track" and not item["legacy_response_gap"]:
                origins.append(_origin("status_assessment", item, account_id=account["id"],
                    account_name=account["name"], label=f"{dimension.title()} off track — {item['rationale']}",
                    record_type="status_assessment"))
    for row in conn.execute(
        "SELECT e.*,a.account_id,a.need FROM escalation_instances e "
        "JOIN internal_asks a ON a.id=e.ask_id WHERE e.archived=0 AND e.status='open' "
        "AND e.severity IN ('high','critical')"
    ):
        item, account = repo.row_to_dict(row), accounts[row["account_id"]]
        origins.append(_origin("escalation", item, account_id=account["id"], account_name=account["name"],
                               label=f"Open {item['severity']} escalation — {item['need']}"))
    for row in conn.execute(
        "SELECT a.* FROM internal_asks a WHERE a.archived=0 AND "
        "(a.status='declined' OR (a.status NOT IN ('delivered','declined') AND a.needed_by<date('now'))) "
        "AND (EXISTS (SELECT 1 FROM escalation_defaults d WHERE d.archived=0 "
        "AND d.ask_type=a.ask_type AND d.severity IN ('high','critical')) "
        "OR EXISTS (SELECT 1 FROM escalation_defaults d WHERE d.archived=0 "
        "AND d.ask_type='general' AND d.severity IN ('high','critical')))"
    ):
        item, account = repo.row_to_dict(row), accounts[row["account_id"]]
        treatment = "Declined" if item["status"] == "declined" else "Overdue"
        origins.append(_origin("internal_ask", item, account_id=account["id"], account_name=account["name"],
                               label=f"{treatment} internal ask — {item['need']}"))

    # Attention is derived. Include only durable, allow-listed source objects not already
    # represented above; the stable queue key is the typed origin identifier.
    represented = {(x["record_type"], x["record_id"]) for x in origins}
    attention_types = {"commitment", "risk", "issue", "internal_ask", "escalation"}
    for item in queue.build_queue(conn)["items"]:
        pair = (item["object_type"], item["object_id"])
        if item["priority"] > 2 or item["object_type"] not in attention_types or pair in represented:
            continue
        account = accounts.get(item.get("account_id"))
        if not account:
            continue
        row = {"id": item["key"], "created_at": now_utc()}
        origins.append(_origin("attention_item", row, account_id=account["id"], account_name=account["name"],
            label=f"Active attention item — {item['title']}", record_type=item["object_type"],
            record_id=item["object_id"], record_version=item.get("due_date") or now_utc()))
    return sorted(origins, key=lambda x: (x["account_name"], x["type"], x["id"]))


def _active_exclusions(conn: sqlite3.Connection, report_kind: str) -> list[dict]:
    rows = [repo.row_to_dict(r) for r in conn.execute(
        "SELECT * FROM report_red_origin_exclusions WHERE report_kind=? "
        "AND effective_on<=date('now') AND expires_on>=date('now') ORDER BY created_at",
        (report_kind,),
    )]
    id_columns = {"risk": "risk_id", "issue": "issue_id", "status_assessment": "status_assessment_id",
                  "escalation": "escalation_id", "internal_ask": "internal_ask_id",
                  "attention_item": "attention_item_key"}
    return [{**row, "origin_id": row[id_columns[row["origin_type"]]]} for row in rows]


def create_red_origin_exclusion(conn: sqlite3.Connection, values: dict) -> dict:
    try:
        expires = date.fromisoformat(values["expires_on"])
    except ValueError as exc:
        raise HTTPException(422, "expires_on must be an ISO date") from exc
    if expires.isoformat() < now_utc()[:10]:
        raise HTTPException(422, "expires_on cannot be in the past")
    eligible = {(x["type"], x["id"]): x for x in _eligible_red_origins(conn)}
    key = (values["origin_type"], values["origin_id"])
    if key not in eligible:
        raise HTTPException(422, "the referenced origin is not currently report-eligible")
    if key in {(x["origin_type"], x["origin_id"])
               for x in _active_exclusions(conn, values["report_kind"])}:
        raise HTTPException(409, "this red origin already has an active exclusion")
    columns = {"risk": "risk_id", "issue": "issue_id", "status_assessment": "status_assessment_id",
               "escalation": "escalation_id", "internal_ask": "internal_ask_id",
               "attention_item": "attention_item_key"}
    ts, exclusion_id = now_utc(), new_id()
    row = {"id": exclusion_id, "report_kind": values["report_kind"], "origin_type": values["origin_type"],
           "risk_id": None, "issue_id": None, "status_assessment_id": None, "escalation_id": None,
           "internal_ask_id": None, "attention_item_key": None, "reason": values["reason"],
           "excluded_by": audit.DEFAULT_ACTOR, "effective_on": ts[:10],
           "expires_on": values["expires_on"], "created_at": ts}
    row[columns[values["origin_type"]]] = values["origin_id"]
    with conn:
        conn.execute(f"INSERT INTO report_red_origin_exclusions ({','.join(row)}) VALUES ({','.join('?' for _ in row)})", tuple(row.values()))
        audit.record(conn, object_type="report_origin_exclusion", object_id=exclusion_id,
                     action="create", after=row)
    return repo.row_to_dict(conn.execute("SELECT * FROM report_red_origin_exclusions WHERE id=?", (exclusion_id,)).fetchone())


def no_surprises(conn: sqlite3.Connection, report_kind: str = "monthly_portfolio_brief") -> dict:
    blockers = []
    for account in repo.list_rows(conn, "accounts", where="1=1"):
        for dimension in ("delivery", "commercial"):
            projected = account[f"{dimension}_status"]
            assessment = _latest_assessment(conn, account["id"], dimension)
            if projected == "off_track" and (not assessment or assessment["value"] != "off_track"):
                blockers.append({"account_id": account["id"], "account_name": account["name"], "dimension": dimension,
                    "claim": f"{dimension} is projected off track", "accepted_origin_types": ["status_assessment"],
                    "reason": "mutable status projection has no matching latest assessment event",
                    "resolution": "Create an off-track status assessment with recovery response and leadership handling."})
            elif assessment and assessment["value"] == "off_track" and assessment["legacy_response_gap"]:
                blockers.append({"account_id": account["id"], "account_name": account["name"], "dimension": dimension,
                    "claim": f"{dimension} is off track", "accepted_origin_types": ["status_assessment"],
                    "reason": "red status has no governed response record",
                    "resolution": "Create a current off-track assessment with recovery response and leadership handling."})
    origins = _eligible_red_origins(conn)
    exclusions = _active_exclusions(conn, report_kind)
    excluded_by_key = {(x["origin_type"], x["origin_id"]): x for x in exclusions}
    included, excluded = [], []
    for origin in origins:
        exclusion = excluded_by_key.get((origin["type"], origin["id"]))
        if exclusion:
            excluded.append({"origin": origin, "exclusion": exclusion})
        else:
            included.append(origin)
    return {"valid": not blockers, "blockers": blockers, "generation_blockers": blockers,
            "eligible_red_origins": origins, "included_red_origins": included,
            "excluded_red_origins": excluded, "checked_at": now_utc()}


def monthly_preview(conn: sqlite3.Connection) -> dict:
    check = no_surprises(conn)
    accounts = repo.list_rows(conn, "accounts", where="1=1 ORDER BY name")
    periods = repo.list_rows(conn, "forecast_periods", where="status IN ('open','locked') ORDER BY ends_on")
    entries = []
    if periods:
        entries = repo.list_rows(conn, "forecast_entries", where="period_id=? ORDER BY account_id", params=(periods[0]["id"],))
    top_asks = [repo.row_to_dict(r) for r in conn.execute("SELECT ia.*,a.name account_name FROM internal_asks ia JOIN accounts a ON a.id=ia.account_id WHERE ia.archived=0 AND ia.status NOT IN ('delivered','declined') ORDER BY ia.needed_by LIMIT 10")]
    # All open risks appear: register membership must guarantee upward visibility, not merely
    # make a risk eligible for a top-N list where it can silently fall off the page.
    risks = [repo.row_to_dict(r) for r in conn.execute("SELECT r.*,p.account_id,a.name account_name FROM risks r JOIN programs p ON p.id=r.program_id JOIN accounts a ON a.id=p.account_id WHERE r.archived=0 AND r.status='open' ORDER BY CASE r.severity WHEN 'high' THEN 0 WHEN 'medium' THEN 1 ELSE 2 END,r.created_at")]
    changes = [repo.row_to_dict(r) for r in conn.execute("SELECT ce.*,fe.account_id,a.name account_name FROM forecast_change_events ce JOIN forecast_entries fe ON fe.id=ce.entry_id JOIN accounts a ON a.id=fe.account_id WHERE ce.changed_at>=date('now','-30 days') ORDER BY ce.changed_at DESC")]
    wins = [repo.row_to_dict(r) for r in conn.execute(
        "SELECT re.*,a.name account_name FROM revenue_events re JOIN accounts a ON a.id=re.account_id "
        "WHERE re.archived=0 AND re.kind IN ('expansion','renewal_flat') "
        "AND re.effective_on>=date('now','-30 days') ORDER BY re.effective_on DESC")]
    headwinds = [repo.row_to_dict(r) for r in conn.execute(
        "SELECT re.*,a.name account_name FROM revenue_events re JOIN accounts a ON a.id=re.account_id "
        "WHERE re.archived=0 AND re.kind IN ('contraction','churn') "
        "AND re.effective_on>=date('now','-30 days') ORDER BY re.effective_on DESC")]
    statuses = []
    for account in accounts:
        status = {"account_id": account["id"], "account_name": account["name"]}
        for dimension in ("delivery", "commercial"):
            current = _latest_assessment(conn, account["id"], dimension)
            prior = conn.execute("SELECT value FROM account_status_assessments WHERE account_id=? AND dimension=? AND archived=0 ORDER BY assessed_on DESC,created_at DESC LIMIT 1 OFFSET 1", (account["id"], dimension)).fetchone()
            status[dimension] = current["value"] if current else "unknown"
            status[f"{dimension}_assessed_on"] = current["assessed_on"] if current else None
            status[f"{dimension}_assessment"] = current
            status[f"{dimension}_previous"] = prior["value"] if prior else None
            status[f"{dimension}_moved"] = bool(prior and prior["value"] != status[dimension])
        statuses.append(status)
    period = periods[0] if periods else None
    rollup = totals(entries, _closed_actuals(conn, period, entries) if period else [])
    return {"validation": check, "period": periods[0] if periods else None,
            "forecast_totals": rollup["groups"], "forecast_amount_exclusions": rollup["amount_exclusions"],
            "forecast_weighting_exclusions": rollup["weighting_exclusions"], "forecast_entries": entries,
            "statuses": statuses, "top_risks": risks,
            "top_asks": top_asks, "forecast_changes": changes, "wins": wins, "revenue_headwinds": headwinds,
            "generated_at": now_utc()}


def generate_monthly(conn: sqlite3.Connection) -> dict:
    preview = monthly_preview(conn)
    if not preview["validation"]["valid"]:
        raise HTTPException(status_code=409, detail={"code": "no_surprises_blocked", **preview["validation"]})
    lines = ["# Monthly portfolio brief", "", f"Data current through {now_utc()[:10]}", "", "## Forecast"]
    lines += [f"- {g['currency']} / {g['price_basis']}: Closed {g['closed']:,.2f}; Commit {g['commit']:,.2f}; Best Case {g['best_case']:,.2f}; weighted open {g['weighted_open']:,.2f}" for g in preview["forecast_totals"]] or ["- No defensible active-period amounts"]
    lines += ["", "## What moved"]
    lines += [f"- {c['account_name']}: {c['category_before'].replace('_',' ')} → {c['category_after'].replace('_',' ')} — {c['driver']}" for c in preview["forecast_changes"]] or ["- No forecast category movement in the prior 30 days"]
    lines += ["", "## Account status"]
    lines += [f"- {s['account_name']}: delivery {s['delivery'].replace('_',' ')}{' ↕' if s['delivery_moved'] else ' →'}; commercial {s['commercial'].replace('_',' ')}{' ↕' if s['commercial_moved'] else ' →'}" for s in preview["statuses"]]
    lines += ["", "## Red origins requiring attention"]
    lines += ([f"- {o['account_name']}: {o['label']} ({o['type']} {o['id']})" for o in preview["validation"]["included_red_origins"]]
              or ["- None"])
    lines += ["", "## Top risks"] + ([f"- {r['account_name']}: {r['description']} ({r['severity']})" for r in preview["top_risks"]] or ["- None open"])
    lines += ["", "## What leadership can unblock"] + ([f"- {a['account_name']}: {a['need']} — {a['needed_by']}" for a in preview["top_asks"]] or ["- No active asks"])
    lines += ["", "## Wins worth repeating upward"] + ([f"- {w['account_name']}: {w['kind'].replace('_',' ')} — {w.get('amount') if w.get('amount') is not None else 'amount not recorded'} {w.get('currency') or ''} {w.get('price_basis') or ''}" for w in preview["wins"]] or ["- No sourced revenue events in the prior 30 days"])
    lines += ["", "## Revenue headwinds"] + ([f"- {w['account_name']}: {w['kind'].replace('_',' ')} — {w.get('amount') if w.get('amount') is not None else 'amount not recorded'} {w.get('currency') or ''} {w.get('price_basis') or ''}" for w in preview["revenue_headwinds"]] or ["- None sourced in the prior 30 days"])
    exclusions = preview["forecast_amount_exclusions"] + preview["forecast_weighting_exclusions"]
    lines += ["", "## Data gaps and exclusions"]
    lines += ([f"- Forecast {x.get('entry_id') or x.get('source_id')}: {x['reason']}" for x in exclusions] or ["- No forecast rollup exclusions"])
    lines += [f"- Red origin {x['origin']['type']} {x['origin']['id']} excluded through {x['exclusion']['expires_on']}: {x['exclusion']['reason']}" for x in preview["validation"]["excluded_red_origins"]]
    doc = repo.insert(conn, "generated_documents", {"kind": "monthly_portfolio_brief",
        "title": "Monthly portfolio brief", "body_markdown": "\n".join(lines), "status": "draft",
        "generated_at": now_utc(), "data_current_through": now_utc()[:10], "audience": "internal",
        "audience_profile": "leadership",
        **generators.template_stamp("monthly_portfolio_brief")}, object_type="generated_document")
    with conn:
        for s in preview["statuses"]:
            account = repo.get_row(conn, "accounts", s["account_id"])
            conn.execute("INSERT INTO generated_document_sources(id,document_id,record_type,record_id,record_version,inclusion_reason,visibility_class,created_at) VALUES (?,?,?,?,?,?,?,?)",
                         (new_id(), doc["id"], "account", account["id"], account["updated_at"], "portfolio status row", "internal", now_utc()))
            for dimension in ("delivery", "commercial"):
                assessment = s.get(f"{dimension}_assessment")
                if assessment:
                    conn.execute("INSERT OR IGNORE INTO generated_document_sources(id,document_id,record_type,record_id,record_version,inclusion_reason,visibility_class,created_at) VALUES (?,?,?,?,?,?,?,?)",
                                 (new_id(), doc["id"], "status_assessment", assessment["id"], assessment["updated_at"], f"{dimension} status event", "internal", now_utc()))
        for origin in preview["validation"]["included_red_origins"]:
            conn.execute("INSERT INTO generated_document_sources(id,document_id,record_type,record_id,record_version,inclusion_reason,visibility_class,created_at) VALUES (?,?,?,?,?,?,?,?)",
                         (new_id(), doc["id"], origin["record_type"], origin["record_id"], origin["record_version"], "red origin", "internal", now_utc()))
        for item in preview["validation"]["excluded_red_origins"]:
            exclusion = item["exclusion"]
            conn.execute("INSERT INTO generated_document_sources(id,document_id,record_type,record_id,record_version,inclusion_reason,visibility_class,created_at) VALUES (?,?,?,?,?,?,?,?)",
                         (new_id(), doc["id"], "report_origin_exclusion", exclusion["id"], exclusion["created_at"], "typed red-origin exclusion", "internal", now_utc()))
        manifest_groups = (("top_risks", "risk", "open risk"), ("top_asks", "internal_ask", "leadership help"),
                           ("forecast_changes", "forecast_change_event", "forecast movement"),
                           ("wins", "revenue_event", "upward win"),
                           ("revenue_headwinds", "revenue_event", "revenue headwind"))
        for key, record_type, reason in manifest_groups:
            for row in preview[key]:
                conn.execute("INSERT OR IGNORE INTO generated_document_sources(id,document_id,record_type,record_id,record_version,inclusion_reason,visibility_class,created_at) VALUES (?,?,?,?,?,?,?,?)",
                             (new_id(), doc["id"], record_type, row["id"], row.get("updated_at") or row.get("changed_at") or row.get("effective_on"), reason, "internal", now_utc()))
        if preview["period"]:
            period = preview["period"]
            conn.execute("INSERT INTO generated_document_sources(id,document_id,record_type,record_id,record_version,inclusion_reason,visibility_class,created_at) VALUES (?,?,?,?,?,?,?,?)",
                         (new_id(), doc["id"], "forecast_period", period["id"], period["updated_at"], "forecast rollup period", "internal", now_utc()))
        for row in preview["forecast_entries"]:
            conn.execute("INSERT INTO generated_document_sources(id,document_id,record_type,record_id,record_version,inclusion_reason,visibility_class,created_at) VALUES (?,?,?,?,?,?,?,?)",
                         (new_id(), doc["id"], "forecast_entry", row["id"], row["updated_at"], "forecast rollup entry", "internal", now_utc()))
    return {"document": doc, "preview": preview}


def generate_review_artifact(conn: sqlite3.Connection, review_id: str, kind: str) -> dict:
    review = repo.get_row(conn, "account_reviews", review_id)
    manifest_records: list[tuple[str, dict, str]] = []
    if kind == "internal_account_brief":
        return generate_account_brief(conn, review["account_id"], kind)
    if kind == "internal_challenge_sheet":
        data = challenge_sheet(conn, review_id)
        body = ["# Review challenge sheet", ""] + ([f"- {q['question']} Sources: {', '.join(q['source_ids'])}" for q in data["questions"]] or ["- No rule-generated challenges."])
    elif kind == "internal_review_packet":
        brief = account_brief_data(conn, review["account_id"])
        body = [f"# {brief['account']['name']} — Full internal review packet", "",
                "## Governed status",
                f"- Delivery: {brief['delivery_status']['value'] if brief['delivery_status'] else 'unknown'}",
                f"- Commercial: {brief['commercial_status']['value'] if brief['commercial_status'] else 'unknown'}", "",
                "## Operator point of view",
                brief["operator_view"]["body"] if brief["operator_view"] else "Gap: no dated operator point of view.", "",
                "## Top risks",
                *([f"- {r['severity']}: {r['description']} — {r.get('mitigation') or 'mitigation missing'}" for r in brief["top_risks"]] or ["- None recorded"]), "",
                "## Forecast",
                *([f"- {e['category']}: {e.get('amount')} {e.get('currency') or ''} {e.get('price_basis') or ''}" for e in brief["forecast_entries"]] or ["- No active forecast entries"]), "",
                "## Review commitments"]
        rows = repo.list_rows(conn, "commitments", where="account_review_id=? ORDER BY due_date", params=(review_id,))
        value = expansion.ledger(conn, review["account_id"])
        whitespace = expansion.rollup(conn, review["account_id"])
        agreements = stage75.agreements(conn, review["account_id"])
        asks = repo.list_rows(conn, "internal_asks", where="account_id=? AND status NOT IN ('delivered','declined') ORDER BY needed_by", params=(review["account_id"],))
        feedback = [repo.row_to_dict(r) for r in conn.execute("SELECT o.*,i.title,i.status feedback_status FROM product_feedback_occurrences o JOIN product_feedback_items i ON i.id=o.feedback_item_id WHERE o.account_id=? AND o.archived=0 ORDER BY o.captured_on DESC", (review["account_id"],))]
        roster = [repo.row_to_dict(r) for r in conn.execute("SELECT ar.*,p.name person_name FROM account_internal_roster ar JOIN persons p ON p.id=ar.person_id WHERE ar.account_id=? AND ar.archived=0 ORDER BY ar.role", (review["account_id"],))]
        body += [f"- {r['commitment_class']}: {r['description']} — {r['status']} / {r['due_date']}" for r in rows] or ["- None captured"]
        body += ["", "## Whitespace and value realization",
                 f"- Paid seats: {whitespace.get('paid_seats')}; addressable: {whitespace.get('addressable_seats')}; value targets: {value.get('total')}",
                 f"- Value states: {value.get('counts')}", "", "## Operational triggers",
                 *([f"- {r['name']}: {r['status']}" for r in agreements.get('agreements', [])] or ["- None recorded"]),
                 "", "## Open asks and escalations",
                 *([f"- {a['need']} — {a['status']} / {a['needed_by']}" for a in asks] or ["- None open"]),
                 "", "## Product feedback",
                 *([f"- {f['title']} — {f['feedback_status']}" for f in feedback] or ["- None sourced"]),
                 "", "## Internal coverage",
                 *([f"- {r['person_name']}: {r['role']} ({r['coverage_type']})" for r in roster] or ["- No active roster"])]
        data = {"review_id": review_id, "commitments": rows, "whitespace": whitespace,
                "value": value, "operational_triggers": agreements, "asks": asks,
                "feedback": feedback, "roster": roster}
        manifest_records += [("commitment", r, "review commitment") for r in rows]
        manifest_records += [("internal_ask", r, "open ask") for r in asks]
        manifest_records += [("product_feedback_occurrence", r, "account feedback") for r in feedback]
        manifest_records += [("internal_roster", r, "coverage") for r in roster]
        manifest_records += [("risk", r, "top review risk") for r in brief["top_risks"]]
        manifest_records += [("forecast_entry", r, "forecast call") for r in brief["forecast_entries"]]
        manifest_records += [("value_target", r, "value realization") for r in value.get("targets", [])]
        manifest_records += [("operational_agreement", r, "operational trigger") for r in agreements.get("agreements", [])]
        if brief["operator_view"]:
            manifest_records.append(("operator_view", brief["operator_view"], "operator point of view"))
        if brief["current_contract"]:
            manifest_records.append(("contract_version", brief["current_contract"], "renewal countdown"))
        if brief["growth_plan"].get("plan"):
            manifest_records.append(("account_growth_plan", brief["growth_plan"]["plan"], "growth bridge"))
        manifest_records += [("growth_plan_line", r, "growth bridge line") for r in brief["growth_plan"].get("lines", [])]
    else:
        raise HTTPException(422, "unsupported review artifact kind")
    doc = repo.insert(conn, "generated_documents", {"account_id": review["account_id"], "kind": kind,
        "title": kind.replace("_", " ").title(), "body_markdown": "\n".join(body), "status": "draft",
        "generated_at": now_utc(), "data_current_through": now_utc()[:10], "audience": "internal",
        "audience_profile": "working",
        **generators.template_stamp(kind)}, object_type="generated_document")
    with conn:
        conn.execute("INSERT INTO generated_document_sources(id,document_id,record_type,record_id,record_version,inclusion_reason,visibility_class,created_at) VALUES (?,?,?,?,?,?,?,?)",
                     (new_id(), doc["id"], "account_review", review_id, review["updated_at"], "review context", "internal", now_utc()))
        for record_type, row, reason in manifest_records:
            conn.execute("INSERT OR IGNORE INTO generated_document_sources(id,document_id,record_type,record_id,record_version,inclusion_reason,visibility_class,created_at) VALUES (?,?,?,?,?,?,?,?)",
                         (new_id(), doc["id"], record_type, row["id"], row.get("updated_at"), reason, "internal", now_utc()))
    return {"document": doc, "data": data}


def portfolio_analytics(conn: sqlite3.Connection) -> dict:
    closed_periods = repo.list_rows(conn, "forecast_periods", where="status='closed' ORDER BY ends_on DESC")
    forecast = [{"period": p, "calibration": calibration(conn, p["id"])} for p in closed_periods]
    asks = [repo.row_to_dict(r) for r in conn.execute("SELECT ia.id,ia.requested_from_function_id,ia.status,ia.created_at,ia.delivered_on,ia.needed_by FROM internal_asks ia WHERE ia.archived=0")]
    by_function: dict[str, dict] = defaultdict(lambda: {"open": 0, "past_needed_by": 0,
        "acknowledgment_hours": [], "delivered_days": [], "record_ids": []})
    today = now_utc()[:10]
    for ask in asks:
        b = by_function[ask.get("requested_from_function_id") or "person-directed"]; b["record_ids"].append(ask["id"])
        if ask["status"] not in ("delivered", "declined"):
            b["open"] += 1; b["past_needed_by"] += int(ask["needed_by"] < today)
        if ask.get("delivered_on"):
            b["delivered_days"].append((date.fromisoformat(ask["delivered_on"][:10]) - date.fromisoformat(ask["created_at"][:10])).days)
        acknowledged = conn.execute(
            "SELECT occurred_at FROM internal_ask_events WHERE ask_id=? "
            "AND event_type IN ('acknowledged','started','delivered','declined') "
            "ORDER BY occurred_at,created_at LIMIT 1", (ask["id"],)
        ).fetchone()
        if acknowledged:
            b["acknowledgment_hours"].append(elapsed_business_hours(conn, ask["created_at"], acknowledged["occurred_at"]))
    ask_summary = [{"function_id": key, "open": value["open"], "past_needed_by": value["past_needed_by"],
                    "acknowledged_count": len(value["acknowledgment_hours"]),
                    "median_acknowledgment_hours": median(value["acknowledgment_hours"]) if len(value["acknowledgment_hours"]) >= 3 else None,
                    "delivered_count": len(value["delivered_days"]),
                    "median_resolution_days": median(value["delivered_days"]) if len(value["delivered_days"]) >= 3 else None,
                    "insufficient_data": len(value["acknowledgment_hours"]) < 3 and len(value["delivered_days"]) < 3,
                    "record_ids": value["record_ids"]} for key, value in sorted(by_function.items())]
    feedback = [repo.row_to_dict(r) for r in conn.execute("SELECT i.id,i.status,COUNT(DISTINCT o.account_id) account_count FROM product_feedback_items i LEFT JOIN product_feedback_occurrences o ON o.feedback_item_id=i.id AND o.archived=0 WHERE i.archived=0 GROUP BY i.id ORDER BY i.status,i.title")]
    escalation_rows = [repo.row_to_dict(r) for r in conn.execute("SELECT e.*,a.requested_from_function_id FROM escalation_instances e JOIN internal_asks a ON a.id=e.ask_id WHERE e.archived=0")]
    escalation_groups: dict[tuple[str, str, str], dict] = defaultdict(lambda: {"opened": 0, "open": 0, "resolution_hours": [], "record_ids": []})
    from datetime import datetime
    for row in escalation_rows:
        key = (row["severity"], row["path_type"], row.get("requested_from_function_id") or "person-directed")
        group = escalation_groups[key]; group["opened"] += 1; group["record_ids"].append(row["id"])
        if row["status"] == "open":
            group["open"] += 1
        elif row.get("resolved_at"):
            group["resolution_hours"].append((datetime.fromisoformat(row["resolved_at"]) - datetime.fromisoformat(row["opened_at"])).total_seconds() / 3600)
    escalations = [{"severity": key[0], "path_type": key[1], "function_id": key[2],
                    "opened": value["opened"], "open": value["open"],
                    "resolved_count": len(value["resolution_hours"]),
                    "median_resolution_hours": median(value["resolution_hours"]) if len(value["resolution_hours"]) >= 3 else None,
                    "insufficient_data": len(value["resolution_hours"]) < 3, "record_ids": value["record_ids"]}
                   for key, value in sorted(escalation_groups.items())]
    commitment_rows = [repo.row_to_dict(r) for r in conn.execute("SELECT id,commitment_class,status,due_date,closed_on FROM commitments WHERE archived=0 AND commitment_class<>'client'")]
    commitment_groups: dict[str, dict] = defaultdict(lambda: {"open": 0, "closed": 0, "on_time": 0, "record_ids": []})
    for row in commitment_rows:
        group = commitment_groups[row["commitment_class"]]; group["record_ids"].append(row["id"]); group[row["status"]] += 1
        if row["status"] == "closed" and row.get("closed_on") and row["closed_on"][:10] <= row["due_date"]:
            group["on_time"] += 1
    commitments = [{"commitment_class": key, **value,
                    "completion_fraction": f"{value['closed']} of {value['open'] + value['closed']}",
                    "completion_rate": value["closed"] / (value["open"] + value["closed"]) if value["open"] + value["closed"] >= 3 else None,
                    "on_time_rate": value["on_time"] / value["closed"] if value["closed"] >= 3 else None,
                    "insufficient_data": value["open"] + value["closed"] < 3}
                   for key, value in sorted(commitment_groups.items())]
    feedback_loops = repo.row_to_dict(conn.execute("SELECT COUNT(*) occurrence_count,SUM(EXISTS(SELECT 1 FROM product_feedback_touches t WHERE t.occurrence_id=o.id AND t.touch_type='acknowledgment')) acknowledged_count,SUM(EXISTS(SELECT 1 FROM product_feedback_touches t WHERE t.occurrence_id=o.id AND t.touch_type='resolution')) resolution_count FROM product_feedback_occurrences o WHERE o.archived=0").fetchone())
    roster_exposure = []
    for account in repo.list_rows(conn, "accounts", where="1=1 ORDER BY name"):
        participants = [r["person_id"] for r in conn.execute("SELECT DISTINCT ip.person_id FROM interactions i JOIN interaction_participants ip ON ip.interaction_id=i.id JOIN persons p ON p.id=ip.person_id WHERE i.account_id=? AND i.occurred_on>=date('now','-90 days') AND p.affiliation='valence'", (account["id"],))]
        roster_exposure.append({"account_id": account["id"], "account_name": account["name"],
            "recent_internal_participant_count": len(participants), "single_thread_exposed": len(participants) <= 1,
            "person_ids": participants})
    exec_touch = []
    for account in repo.list_rows(conn, "accounts", where="1=1 ORDER BY name"):
        sponsors = [repo.row_to_dict(r) for r in conn.execute("SELECT ar.*,p.name person_name FROM account_internal_roster ar JOIN persons p ON p.id=ar.person_id WHERE ar.account_id=? AND ar.role='executive_sponsor' AND ar.archived=0", (account["id"],))]
        sponsor_rows = []
        for sponsor in sponsors:
            touch = conn.execute("SELECT i.id,i.occurred_on FROM interactions i JOIN interaction_participants ip ON ip.interaction_id=i.id WHERE i.account_id=? AND ip.person_id=? AND i.meaningful_touch=1 AND i.archived=0 ORDER BY i.occurred_on DESC LIMIT 1", (account["id"], sponsor["person_id"])).fetchone()
            sponsor_rows.append({"roster_id": sponsor["id"], "person_id": sponsor["person_id"], "person_name": sponsor["person_name"],
                                 "last_touch_interaction_id": touch["id"] if touch else None,
                                 "last_touch_on": touch["occurred_on"] if touch else None,
                                 "expected_touch_cadence_days": sponsor.get("expected_touch_cadence_days")})
        exec_touch.append({"account_id": account["id"], "account_name": account["name"], "sponsors": sponsor_rows,
                           "has_exec_sponsor": bool(sponsor_rows), "has_evidenced_exec_touch": any(x["last_touch_on"] for x in sponsor_rows)})
    return {"forecast_calibration": forecast, "asks_by_function": ask_summary,
            "escalations": escalations, "review_commitments": commitments,
            "feedback_themes": feedback, "feedback_loops": feedback_loops,
            "coverage_exposure": roster_exposure, "exec_touch_coverage": exec_touch,
            "generated_at": now_utc(), "rules": {"composite_score": False, "people_ranked": False}}
