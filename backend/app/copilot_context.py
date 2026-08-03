"""Typed, scope-first readers for the Stage 12 Account Copilot.

Every function in this module receives the run scope and constrains SQL before rows are returned.
FTS snippets are discovery hints only: candidate records are hydrated from canonical tables and the
saved packet contains a minimal, immutable field snapshot. Retrieved prose is data, never planner
input or a way to select another reader.
"""
from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from datetime import date, timedelta
from difflib import SequenceMatcher
from typing import Any

from fastapi import HTTPException

from . import campaigns, expansion, queue, repo, search
from .db import now_utc

RETRIEVAL_VERSION = "copilot-retrieval-v1"
MAX_PACKET_ITEMS = 24
MAX_EXCERPT = 420

_INJECTION = re.compile(
    r"(?i)(ignore\s+(all\s+)?previous|system\s+prompt|developer\s+message|reveal\s+other|"
    r"create\s+(a\s+)?task|execute\s+sql|send\s+(an\s+)?email|tool\s+call)"
)

# Only fields named here can enter a packet. In particular, interaction raw_notes, email bodies,
# named-person usage, secrets, and internal binary payloads do not have a path through hydration.
_RECORDS: dict[str, tuple[str, tuple[str, ...]]] = {
    "account": ("accounts", ("name", "short_context", "delivery_status", "commercial_status")),
    "program": ("programs", ("name", "phase", "problem_statement", "success_criteria", "region", "audience")),
    "person": ("persons", ("name", "title", "affiliation")),
    "population_segment": ("population_segments", ("name", "business_unit", "region", "is_unallocated")),
    "population_view": ("population_views", ("name",)),
    "interaction": ("interactions", ("occurred_on", "summary", "follow_up", "meaningful_touch")),
    "commitment": ("commitments", ("description", "commitment_class", "due_date", "status", "closed_on", "acknowledged_by_id")),
    "risk": ("risks", ("description", "severity", "is_blocker", "status", "mitigation")),
    "issue": ("issues", ("description", "issue_type", "is_blocker", "status", "resolution")),
    "decision": ("decisions", ("description", "decided_on", "rationale", "status", "supersedes_id")),
    "task": ("tasks", ("description", "due_date", "status", "completed_on")),
    "milestone": ("milestones", ("name", "due_date", "status", "at_risk", "success_criteria")),
    "expansion_opportunity": ("expansion_opportunities", ("name", "use_case", "budget_state", "next_action", "status", "outcome", "outcome_reason")),
    "contract_version": ("contract_versions", ("version_label", "renewal_date", "notice_period_days", "is_current", "derived_arr", "currency", "price_basis")),
    "internal_ask": ("internal_asks", ("need", "needed_by", "status", "success_condition", "revenue_amount", "currency")),
    "forecast_entry": ("forecast_entries", ("category", "amount", "currency", "price_basis", "help_needed_note", "unresolved_conditions")),
    "status_assessment": ("account_status_assessments", ("dimension", "value", "rationale", "assessed_on", "recovery_action")),
    "adoption_campaign": ("adoption_campaigns", ("name", "status", "target_behavior", "hypothesis", "starts_on", "ends_on", "completion_outcome")),
    "calendar_event": ("calendar_events", ("title", "starts_at", "ends_at", "purpose")),
    "value_target": ("value_targets", ("target_value", "operator", "unit", "timeframe_start", "timeframe_end", "status")),
    "growth_plan_line": ("growth_plan_lines", ("name", "status", "seat_count", "seat_price_low", "seat_price_high", "ask_date")),
    "generated_document": ("generated_documents", ("kind", "title", "status", "generated_at", "data_current_through", "audience")),
    "company_event": ("company_events", ("status", "summary", "occurred_on", "expires_on", "canonical_occurrence_key")),
    "intel_document_span": ("intel_document_spans", ("locator", "excerpt", "section", "speaker")),
}


def _row_account(conn: sqlite3.Connection, record_type: str, row: dict) -> tuple[str | None, str | None]:
    account_id = row.get("account_id")
    program_id = row.get("program_id")
    if record_type == "account":
        account_id = row.get("id")
    if account_id is None and program_id:
        program = conn.execute("SELECT account_id FROM programs WHERE id=?", (program_id,)).fetchone()
        account_id = program["account_id"] if program else None
    if record_type == "value_target":
        account_id = row.get("account_id")
    return account_id, program_id


def _assert_scope(conn: sqlite3.Connection, run: dict, account_id: str | None,
                  program_id: str | None = None) -> None:
    if run["scope_type"] == "portfolio":
        return
    if account_id != run["account_id"]:
        raise HTTPException(422, "record is outside the copilot run scope")
    if run["scope_type"] == "program" and program_id != run["program_id"]:
        raise HTTPException(422, "record is outside the copilot program scope")


def _safe_text(value: Any) -> str:
    text = " ".join(str(value or "").split())
    return text[:MAX_EXCERPT]


def _statement(record_type: str, fields: dict) -> str:
    title = fields.get("name") or fields.get("title") or fields.get("description") or fields.get("need")
    bits = [str(title)] if title else []
    for key in ("dimension", "value", "status", "category", "completion_outcome", "due_date",
                "renewal_date", "assessed_on", "starts_on", "ends_on", "next_action"):
        value = fields.get(key)
        if value not in (None, ""):
            bits.append(f"{key.replace('_', ' ')}: {value}")
    return "; ".join(bits) or f"{record_type.replace('_', ' ')} record"


def hydrate_record(conn: sqlite3.Connection, run: dict, record_type: str, record_id: str,
                   *, method: str = "exact", reason: str = "exact record match",
                   rank: int = 1) -> dict | None:
    definition = _RECORDS.get(record_type)
    if not definition:
        return None
    table, allowed = definition
    row = conn.execute(f"SELECT * FROM {table} WHERE id=?", (record_id,)).fetchone()
    if not row:
        return None
    raw = dict(row)
    if raw.get("archived"):
        return None
    account_id, program_id = _row_account(conn, record_type, raw)
    _assert_scope(conn, run, account_id, program_id)
    fields = {key: raw.get(key) for key in allowed if key in raw}
    untrusted = [key for key, value in fields.items()
                 if isinstance(value, str) and _INJECTION.search(value)]
    if untrusted:
        return {"excluded": True, "record_type": record_type, "record_id": record_id,
                "reason": f"quarantined untrusted instruction-like text in {', '.join(untrusted)}"}
    statement = _statement(record_type, fields)
    version = raw.get("updated_at") or raw.get("created_at") or "unknown"
    return {
        "record_type": record_type, "record_id": record_id, "account_id": account_id,
        "program_id": program_id, "record_version": version,
        "authority": "canonical_native_record", "freshness_state": "current",
        "visibility": "internal", "fields": fields, "statement": statement,
        "excerpt": _safe_text(statement), "retrieval_method": method,
        "retrieval_rank": rank, "inclusion_reason": reason,
    }


def search_records(conn: sqlite3.Connection, run: dict, query: str,
                   record_types: list[str] | None = None, limit: int = 12) -> tuple[list[dict], list[dict]]:
    stop = {"a", "about", "all", "and", "are", "did", "do", "does", "for", "from", "how",
            "in", "is", "it", "me", "my", "of", "on", "said", "the", "this", "to", "was",
            "we", "what", "where", "which", "who", "why", "with"}
    terms = [term.lower() for term in re.findall(r"[A-Za-z0-9_-]+", query)
             if len(term) >= 3 and term.lower() not in stop]
    # Natural questions rarely make good FTS AND expressions. Search the meaningful terms inside
    # the SQL scope, then rank candidates by how many distinct terms found them. Scope is never
    # widened and every hit is still canonically hydrated.
    merged: dict[tuple[str, str], dict] = {}
    for term_index, term in enumerate(dict.fromkeys(terms[:8])):
        for hit in search.search(
                conn, term, limit=limit,
                account_id=run.get("account_id") if run["scope_type"] != "portfolio" else None,
                program_id=run.get("program_id") if run["scope_type"] == "program" else None,
                record_types=record_types):
            key = (hit["object_type"], hit["object_id"])
            entry = merged.setdefault(key, {**hit, "term_hits": 0, "first_term": term_index})
            entry["term_hits"] += 1
    results = sorted(merged.values(), key=lambda h: (
        -h["term_hits"], h["first_term"], h["object_type"], h["object_id"]))[:limit]
    included, excluded = [], []
    historical = any(term in query.lower() for term in
                     ("histor", "previous", "prior", "superseded", "as of"))
    for rank, hit in enumerate(results, 1):
        item = hydrate_record(conn, run, hit["object_type"], hit["object_id"],
                              method="fts", reason="lexical candidate, canonically hydrated",
                              rank=rank)
        if not item:
            excluded.append({"record_type": hit["object_type"], "record_id": hit["object_id"],
                             "reason": "record type has no copilot reader"})
        elif item.get("excluded"):
            excluded.append(item)
        elif not any(term in json.dumps(item["fields"], default=str).lower() for term in terms):
            excluded.append({"record_type": item["record_type"], "record_id": item["record_id"],
                             "reason": "lexical match existed only outside allowlisted hydrated fields"})
        elif (item["record_type"] == "decision" and
              item["fields"].get("status") == "superseded" and not historical):
            excluded.append({"record_type": "decision", "record_id": item["record_id"],
                             "reason": "superseded decision excluded from current-state answer"})
        else:
            included.append(item)
    return included, excluded


def bounded_domain_fallback(conn: sqlite3.Connection, run: dict, query: str,
                            limit: int = 8) -> tuple[list[dict], list[dict]]:
    """One typed retrieval expansion when lexical search cannot express the domain noun.

    This is not fuzzy model-selected tooling. The vocabulary and SQL are fixed, scoped before rows
    return, and the second round is visible on the run. It covers ordinary operator language such as
    "promise" for a commitment without requiring every record description to repeat its table name.
    """
    q = query.lower()
    selected: list[tuple[str, str, tuple]] = []
    scope_account = run.get("account_id")
    scope_program = run.get("program_id")
    if any(word in q for word in ("promise", "promised", "commitment", "committed")):
        sql, params = "SELECT id FROM commitments WHERE archived=0", []
        if run["scope_type"] != "portfolio":
            sql += " AND account_id=?"
            params.append(scope_account)
        if run["scope_type"] == "program":
            sql += " AND program_id=?"
            params.append(scope_program)
        selected.append(("commitment", sql + " ORDER BY due_date,id LIMIT ?", (*params, limit)))
    if any(word in q for word in ("block", "blocked", "blocker", "risk", "issue")):
        for record_type, table in (("risk", "risks"), ("issue", "issues")):
            sql = f"SELECT x.id FROM {table} x JOIN programs p ON p.id=x.program_id WHERE x.archived=0"
            params = []
            if run["scope_type"] != "portfolio":
                sql += " AND p.account_id=?"
                params.append(scope_account)
            if run["scope_type"] == "program":
                sql += " AND x.program_id=?"
                params.append(scope_program)
            selected.append((record_type, sql + " ORDER BY x.updated_at DESC,x.id LIMIT ?", (*params, limit)))
    if "decision" in q:
        sql, params = "SELECT id FROM decisions WHERE archived=0", []
        if not any(term in q for term in ("histor", "previous", "prior", "superseded", "as of")):
            sql += " AND status='recorded'"
        if run["scope_type"] != "portfolio":
            sql += " AND account_id=?"
            params.append(scope_account)
        if run["scope_type"] == "program":
            sql += " AND program_id=?"
            params.append(scope_program)
        selected.append(("decision", sql + " ORDER BY decided_on DESC,id LIMIT ?", (*params, limit)))
    if any(word in q for word in ("contract", "renewal")):
        sql, params = "SELECT id FROM contract_versions WHERE archived=0 AND is_current=1", []
        if run["scope_type"] != "portfolio":
            sql += " AND account_id=?"
            params.append(scope_account)
        selected.append(("contract_version", sql + " ORDER BY renewal_date,id LIMIT ?", (*params, limit)))
    if any(word in q for word in ("internal ask", "leadership ask", "escalation")):
        sql, params = "SELECT id FROM internal_asks WHERE archived=0", []
        if run["scope_type"] != "portfolio":
            sql += " AND account_id=?"
            params.append(scope_account)
        selected.append(("internal_ask", sql + " ORDER BY needed_by,id LIMIT ?", (*params, limit)))

    included, excluded, rank = [], [], 1
    for record_type, sql, params in selected:
        for row in conn.execute(sql, params).fetchall():
            try:
                item = hydrate_record(conn, run, record_type, row["id"], method="typed_fallback",
                                      reason="bounded domain-vocabulary expansion", rank=rank)
            except HTTPException:
                continue
            if item and not item.get("excluded"):
                included.append(item)
                rank += 1
            elif item:
                excluded.append(item)
    return included[:limit], excluded


def resolve_named_entities(conn: sqlite3.Connection, run: dict, query: str,
                           limit: int = 8) -> list[dict]:
    """Resolve exact names, governed aliases, then bounded fuzzy candidates inside scope."""
    q = " ".join(re.findall(r"[a-z0-9]+", query.lower()))
    q_words = q.split()
    candidates: list[tuple[int, float, str, str, str]] = []
    definitions = (
        ("person", "persons"), ("program", "programs"),
        ("population_segment", "population_segments"),
        ("population_view", "population_views"),
    )
    for record_type, table in definitions:
        sql, params = f"SELECT id,name FROM {table} WHERE archived=0", []
        if run["scope_type"] != "portfolio":
            sql += " AND account_id=?"
            params.append(run["account_id"])
        if record_type == "program" and run["scope_type"] == "program":
            sql += " AND id=?"
            params.append(run["program_id"])
        for row in conn.execute(sql, tuple(params)).fetchall():
            name = " ".join(re.findall(r"[a-z0-9]+", row["name"].lower()))
            if not name:
                continue
            if name in q:
                candidates.append((1, 1.0, row["name"], record_type, row["id"]))
                continue
            width = len(name.split())
            windows = [" ".join(q_words[i:i + width])
                       for i in range(max(1, len(q_words) - width + 1))]
            score = max((SequenceMatcher(None, name, window).ratio() for window in windows), default=0)
            if len(name) >= 5 and score >= 0.82:
                candidates.append((3, score, row["name"], record_type, row["id"]))
    alias_sql = "SELECT * FROM copilot_entity_aliases WHERE archived=0"
    alias_params: list[str] = []
    if run["scope_type"] != "portfolio":
        alias_sql += " AND (account_id=? OR account_id IS NULL)"
        alias_params.append(run["account_id"])
    for alias in conn.execute(alias_sql, tuple(alias_params)).fetchall():
        if alias["alias"].lower() in query.lower():
            candidates.append((2, 1.0, alias["alias"], alias["record_type"], alias["record_id"]))

    out, seen = [], set()
    for priority, score, label, record_type, record_id in sorted(
            candidates, key=lambda row: (row[0], -row[1], row[2].lower(), row[3], row[4])):
        key = (record_type, record_id)
        if key in seen:
            continue
        try:
            item = hydrate_record(conn, run, record_type, record_id,
                                  method={1: "exact_entity", 2: "governed_alias", 3: "fuzzy_entity"}[priority],
                                  reason=f"entity candidate for '{label}'", rank=priority)
        except HTTPException:
            continue
        if item and not item.get("excluded"):
            item["entity_match_label"] = label
            item["entity_match_kind"] = {1: "exact", 2: "alias", 3: "fuzzy"}[priority]
            item["entity_match_score"] = round(score, 3)
            out.append(item)
            seen.add(key)
        if len(out) >= limit:
            break
    return out


def account_snapshots(conn: sqlite3.Connection, run: dict) -> list[dict]:
    if run["scope_type"] == "portfolio":
        rows = conn.execute("SELECT * FROM accounts WHERE archived=0 ORDER BY name").fetchall()
    else:
        rows = conn.execute("SELECT * FROM accounts WHERE id=? AND archived=0",
                            (run["account_id"],)).fetchall()
    out = []
    for rank, row in enumerate(rows, 1):
        a = dict(row)
        contract = conn.execute(
            "SELECT version_label,renewal_date,derived_arr,currency FROM contract_versions "
            "WHERE account_id=? AND archived=0 AND is_current=1 ORDER BY created_at DESC LIMIT 1",
            (a["id"],)).fetchone()
        fields = {"name": a["name"], "delivery_status": a.get("delivery_status"),
                  "commercial_status": a.get("commercial_status"),
                  "program_count": conn.execute(
                      "SELECT COUNT(*) n FROM programs WHERE account_id=? AND archived=0", (a["id"],)).fetchone()["n"]}
        if contract:
            fields["current_contract"] = dict(contract)
        statement = _statement("account_snapshot", fields)
        out.append({"record_type": "account_snapshot", "record_id": a["id"],
                    "account_id": a["id"], "program_id": None,
                    "record_version": a.get("updated_at") or a.get("created_at") or "unknown",
                    "authority": "derived_from_current_native_records", "freshness_state": "current",
                    "visibility": "internal", "fields": fields, "statement": statement,
                    "excerpt": statement, "retrieval_method": "typed_reader", "retrieval_rank": rank,
                    "inclusion_reason": "current account state"})
    return out


def evidence_context(conn: sqlite3.Connection, run: dict) -> list[dict]:
    where, params = ["mo.archived=0"], []
    if run["scope_type"] != "portfolio":
        where.append("(pr.account_id=? OR ps.account_id=? OR pv.account_id=?)")
        params.extend([run["account_id"]] * 3)
    if run["scope_type"] == "program":
        where.append("mo.program_id=?")
        params.append(run["program_id"])
    rows = conn.execute(
        "SELECT mo.*,md.name metric_name,md.stale_after_days,pr.account_id program_account," 
        "ps.account_id segment_account,pv.account_id view_account FROM metric_observations mo "
        "JOIN metric_definitions md ON md.id=mo.definition_id "
        "LEFT JOIN programs pr ON pr.id=mo.program_id "
        "LEFT JOIN population_segments ps ON ps.id=mo.population_segment_id "
        "LEFT JOIN population_views pv ON pv.id=mo.population_view_id "
        f"WHERE {' AND '.join(where)} ORDER BY mo.current_through DESC LIMIT 12", tuple(params)).fetchall()
    today = date.fromisoformat(now_utc()[:10])
    out = []
    for rank, raw_row in enumerate(rows, 1):
        raw = dict(raw_row)
        account_id = raw.get("program_account") or raw.get("segment_account") or raw.get("view_account")
        safe = expansion.suppress_observation(conn, raw)
        stale = True
        try:
            stale = (today - date.fromisoformat(raw["current_through"])).days > raw["stale_after_days"]
        except (TypeError, ValueError):
            pass
        fields = {"metric": raw["metric_name"], "current_through": raw.get("current_through"),
                  "period_label": raw.get("period_label"), "unit": raw.get("unit")}
        freshness = "current"
        if safe.get("suppressed"):
            fields["display_value"] = "suppressed"
            freshness = "suppressed"
        elif stale:
            fields["display_value"] = "unknown"
            freshness = "stale"
        else:
            fields["value"] = safe.get("value")
            fields["target"] = safe.get("target")
        statement = (f"{fields['metric']}: {fields.get('value', fields.get('display_value'))} "
                     f"{fields.get('unit') or ''}; current through {fields.get('current_through')}").strip()
        out.append({"record_type": "metric_observation", "record_id": raw["id"],
                    "account_id": account_id, "program_id": raw.get("program_id"),
                    "record_version": raw.get("updated_at") or raw.get("created_at") or "unknown",
                    "authority": "ingested_aggregate_observation", "freshness_state": freshness,
                    "visibility": "internal", "fields": fields, "statement": statement,
                    "excerpt": statement, "retrieval_method": "typed_reader", "retrieval_rank": rank,
                    "inclusion_reason": "latest scoped aggregate evidence"})
    return out


def material_changes(conn: sqlite3.Connection, run: dict, after: str | None = None,
                     through: str | None = None) -> list[dict]:
    after = after or (date.fromisoformat(now_utc()[:10]) - timedelta(days=7)).isoformat()
    through = through or now_utc()
    prior = conn.execute(
        "SELECT id FROM copilot_runs WHERE intent='changes' AND reviewed_at IS NOT NULL "
        "AND review_cursor=? AND scope_type=? AND account_id IS ? AND program_id IS ? "
        "AND archived=0 ORDER BY reviewed_at DESC,created_at DESC,id DESC LIMIT 1",
        (after, run["scope_type"], run.get("account_id"), run.get("program_id"))).fetchone()
    seen_ids = ({row["record_id"] for row in conn.execute(
        "SELECT record_id FROM copilot_run_sources WHERE run_id=?", (prior["id"],)).fetchall()}
        if prior else set())
    rows: list[dict] = []
    queries = (
        ("forecast_change", "SELECT e.account_id,NULL program_id,x.id,x.changed_at occurred_at,"
         "'forecast_entry' native_record_type,e.id native_record_id,"
         "'Forecast '||x.category_before||' to '||x.category_after||': '||x.driver statement "
         "FROM forecast_change_events x JOIN forecast_entries e ON e.id=x.entry_id "
         "WHERE x.changed_at >= ? AND x.changed_at <= ?", "e.account_id", None),
        ("status_change", "SELECT s.account_id,NULL program_id,s.id,s.created_at occurred_at,"
         "'status_assessment' native_record_type,s.id native_record_id,"
         "s.dimension||' status: '||s.value||' — '||s.rationale statement "
         "FROM account_status_assessments s WHERE s.created_at >= ? AND s.created_at <= ? AND s.archived=0",
         "s.account_id", None),
        ("ask_change", "SELECT a.account_id,NULL program_id,e.id,e.occurred_at,"
         "'internal_ask' native_record_type,a.id native_record_id,"
         "'Internal ask '||COALESCE(e.status_before,'created')||' to '||COALESCE(e.status_after,e.event_type)||': '||COALESCE(e.reason,e.event_type) statement "
         "FROM internal_ask_events e JOIN internal_asks a ON a.id=e.ask_id "
         "WHERE e.created_at >= ? AND e.created_at <= ?", "a.account_id", None),
        ("campaign_change", "SELECT c.account_id,c.program_id,h.id,h.created_at occurred_at,"
         "'adoption_campaign' native_record_type,c.id native_record_id,"
         "'Campaign '||h.from_status||' to '||h.to_status||': '||h.reason statement "
         "FROM adoption_campaign_state_history h JOIN adoption_campaigns c ON c.id=h.campaign_id "
         "WHERE h.created_at >= ? AND h.created_at <= ?", "c.account_id", "c.program_id"),
    )
    for kind, sql, account_column, program_column in queries:
        params: list[str] = [after, through]
        if run["scope_type"] != "portfolio":
            sql += f" AND {account_column}=?"
            params.append(run["account_id"])
        if run["scope_type"] == "program":
            if not program_column:
                continue
            sql += f" AND {program_column}=?"
            params.append(run["program_id"])
        for raw in conn.execute(sql, tuple(params)).fetchall():
            row = dict(raw)
            if row["id"] in seen_ids:
                continue
            rows.append({"kind": kind, **row})
    # Creation and ordinary lifecycle writes that do not own a richer domain event still belong in
    # the feed. Audit is used only as a locator; the statement is hydrated from the current native
    # record so a generic before/after blob never becomes the answer source.
    # Audit is a locator for ordinary native lifecycle changes. Join each governed type to its
    # native table and apply scope in SQL before an audit row can leave the database.
    for record_type, (table, _) in _RECORDS.items():
        columns = {row["name"] for row in conn.execute(f"PRAGMA table_info({table})")}
        sql = (f"SELECT ae.* FROM audit_events ae JOIN {table} native ON native.id=ae.object_id "
               "WHERE ae.object_type=? AND ae.occurred_at >= ? AND ae.occurred_at <= ?")
        params: list[str] = [record_type, after, through]
        if "archived" in columns:
            sql += " AND native.archived=0"
        if run["scope_type"] == "account":
            if table == "accounts":
                sql += " AND native.id=?"
            elif "account_id" in columns:
                sql += " AND native.account_id=?"
            elif "program_id" in columns:
                sql += " AND EXISTS (SELECT 1 FROM programs p WHERE p.id=native.program_id AND p.account_id=?)"
            else:
                continue
            params.append(run["account_id"])
        elif run["scope_type"] == "program":
            if table == "programs":
                sql += " AND native.id=?"
            elif "program_id" in columns:
                sql += " AND native.program_id=?"
            else:
                continue
            params.append(run["program_id"])
        for event in conn.execute(sql + " ORDER BY ae.occurred_at DESC", tuple(params)).fetchall():
            e = dict(event)
            if e["id"] in seen_ids:
                continue
            hydrated = hydrate_record(conn, run, record_type, e["object_id"])
            if not hydrated or hydrated.get("excluded"):
                continue
            rows.append({"kind": f"{record_type}_change", "account_id": hydrated["account_id"],
                         "program_id": hydrated.get("program_id"), "id": e["id"],
                         "native_record_type": record_type,
                         "native_record_id": e["object_id"],
                         "occurred_at": e["occurred_at"],
                         "statement": f"{record_type.replace('_', ' ').title()} {e['action']}: {hydrated['statement']}"})
    rows.sort(key=lambda r: (r["occurred_at"], r["kind"], r["id"]), reverse=True)
    out = []
    for rank, row in enumerate(rows[:MAX_PACKET_ITEMS], 1):
        out.append({"record_type": row["kind"], "record_id": row["id"],
                    "account_id": row["account_id"], "program_id": row.get("program_id"),
                    "record_version": row["occurred_at"], "authority": "append_only_domain_event",
                    "freshness_state": "current", "visibility": "internal",
                    "fields": {"occurred_at": row["occurred_at"], "statement": row["statement"],
                               "native_record_type": row.get("native_record_type"),
                               "native_record_id": row.get("native_record_id")},
                    "statement": row["statement"], "excerpt": _safe_text(row["statement"]),
                    "retrieval_method": "change_feed", "retrieval_rank": rank,
                    "inclusion_reason": f"material change after {after}"})
    return out


def week_inputs(conn: sqlite3.Connection, run: dict) -> list[dict]:
    items = queue.build_queue(conn)["items"]
    if run["scope_type"] != "portfolio":
        items = [i for i in items if i.get("account_id") == run["account_id"]]
    if run["scope_type"] == "program":
        items = [i for i in items if i.get("program_id") == run["program_id"]]
    out = []
    for rank, item in enumerate(items[:MAX_PACKET_ITEMS], 1):
        fields = {key: item.get(key) for key in
                  ("title", "because", "next_action", "due_date", "priority", "trigger_type")}
        statement = f"{item['title']}; {item['because']} Next: {item['next_action']}"
        out.append({"record_type": "attention_item", "record_id": item["key"],
                    "account_id": item.get("account_id"), "program_id": item.get("program_id"),
                    "record_version": item.get("due_date") or now_utc()[:10],
                    "authority": "deterministic_attention_rule", "freshness_state": "current",
                    "visibility": "internal", "fields": fields, "statement": statement,
                    "excerpt": _safe_text(statement), "retrieval_method": "week_inputs",
                    "retrieval_rank": rank, "inclusion_reason": "canonical Today priority"})
    return out


def company_inputs(conn: sqlite3.Connection, run: dict) -> tuple[list[dict], list[str], list[dict]]:
    """Confirmed event + exact live span packets; proposed records have no query path."""
    if run["scope_type"] != "account":
        return [], ["Company briefs require account scope."], []
    rows = conn.execute(
        "SELECT e.id event_id,e.summary,e.occurred_on,e.expires_on,e.updated_at,k.key kind,k.direction,"
        "d.kind document_kind,d.title,d.publisher,d.published_on,d.retrieved_at,d.url,"
        "s.id span_id,s.locator,s.excerpt,s.section,s.speaker "
        "FROM company_events e JOIN company_event_kinds k ON k.id=e.kind_id "
        "JOIN company_event_evidence ee ON ee.event_id=e.id AND ee.archived=0 "
        "JOIN intel_document_spans s ON s.id=ee.span_id AND s.archived=0 "
        "JOIN intel_documents d ON d.id=s.document_id AND d.archived=0 AND d.correction_state='active' "
        "WHERE e.account_id=? AND e.status='confirmed' AND e.expires_on>=date('now') AND e.archived=0 "
        "ORDER BY e.occurred_on DESC,e.id,s.id LIMIT ?",
        (run["account_id"], MAX_PACKET_ITEMS)).fetchall()
    listing = conn.execute(
        "SELECT ce.listing_status FROM account_company_links acl JOIN company_entities ce ON ce.id=acl.company_entity_id "
        "WHERE acl.account_id=? AND acl.relationship='primary' AND acl.valid_to IS NULL AND acl.archived=0",
        (run["account_id"],)).fetchone()
    gaps = []
    if not rows:
        gaps.append("No confirmed company events with live evidence spans were found.")
    if listing and listing["listing_status"] == "private":
        gaps.append("Earnings and filing coverage is not expected for this private company.")
    items, excluded = [], []
    action_kinds = {"m_and_a","geo_or_facility_expansion","leadership_change","restructuring_or_layoffs","partnership_or_alliance"}
    convergence = {row["event_id"]: dict(row) for row in conn.execute(
        "SELECT ce.event_id,c.target_kind,c.target_id,c.explanation,c.id convergence_id "
        "FROM company_convergence_events ce JOIN company_convergences c ON c.id=ce.convergence_id "
        "WHERE c.account_id=? AND c.status='active' AND c.archived=0 AND ce.archived=0",
        (run["account_id"],)).fetchall()}
    rank = 1
    for raw in rows:
        row = dict(raw)
        untrusted = _INJECTION.search(row["excerpt"] or "")
        if untrusted:
            excluded.append({"record_type": "company_event", "record_id": row["event_id"],
                             "reason": "quarantined untrusted instruction-like text in public evidence excerpt"})
            continue
        section = "What they did" if row["kind"] in action_kinds else "What they said"
        if row["kind"] == "hiring_cluster": section = "Hiring picture"
        statement = (f"{row['summary']} Source: {row['publisher']}, "
                     f"{row['published_on'] or 'date unknown'}, {row['locator']}.")
        fields = {"brief_section": section, "kind": row["kind"], "direction": row["direction"],
                  "summary": row["summary"], "occurred_on": row["occurred_on"],
                  "expires_on": row["expires_on"], "publisher": row["publisher"],
                  "published_on": row["published_on"], "locator": row["locator"],
                  "evidence_excerpt": _safe_text(row["excerpt"]), "source_url": row["url"],
                  "native_record_type": "company_event", "native_record_id": row["event_id"],
                  "evidence_span_id": row["span_id"]}
        base_item = {"record_type": "company_event", "record_id": f"{row['event_id']}:{row['span_id']}",
                     "account_id": run["account_id"], "program_id": None,
                     "record_version": row["updated_at"], "authority": "confirmed_public_span",
                     "freshness_state": "current",
                     "visibility": "internal", "fields": fields, "statement": statement,
                     "excerpt": _safe_text(row["excerpt"]), "retrieval_method": "company_inputs",
                     "retrieval_rank": rank, "inclusion_reason": "confirmed event with live exact evidence span"}
        items.append(base_item)
        rank += 1

        links = conn.execute(
            "SELECT l.*,COALESCE(a.name,ps.name,pv.name,uc.name,"
            "COALESCE(cps.name,cpv.name)||' · '||cuc.name,p.name) target_label "
            "FROM company_event_links l LEFT JOIN accounts a ON a.id=l.account_target_id "
            "LEFT JOIN population_segments ps ON ps.id=l.segment_id LEFT JOIN population_views pv ON pv.id=l.view_id "
            "LEFT JOIN use_cases uc ON uc.id=l.use_case_id LEFT JOIN whitespace_cells wc ON wc.id=l.cell_id "
            "LEFT JOIN population_segments cps ON cps.id=wc.segment_id LEFT JOIN population_views cpv ON cpv.id=wc.view_id "
            "LEFT JOIN use_cases cuc ON cuc.id=wc.use_case_id LEFT JOIN persons p ON p.id=l.person_id "
            "WHERE l.event_id=? AND l.status='confirmed' AND l.archived=0", (row["event_id"],)).fetchall()
        if links:
            labels = ", ".join(link["target_label"] for link in links if link["target_label"])
            map_statement = (f"On the map: {row['summary']} Confirmed targets: {labels}. "
                             f"Source: {row['publisher']}, {row['published_on'] or 'date unknown'}, {row['locator']}.")
            items.append({**base_item, "record_id": f"{row['event_id']}:{row['span_id']}:map",
                          "fields": {**fields, "brief_section": "On the map", "confirmed_targets": labels},
                          "statement": map_statement, "retrieval_rank": rank,
                          "inclusion_reason": "confirmed event and operator-confirmed map link"})
            rank += 1
        converged = convergence.get(row["event_id"])
        expiring = bool(row["expires_on"] and row["expires_on"] >= now_utc()[:10] and
                        row["expires_on"] <= (date.fromisoformat(now_utc()[:10]) + timedelta(days=30)).isoformat())
        if converged or expiring:
            detail = (f"It composes active convergence on {converged['target_kind']} {converged['target_id']}. "
                      if converged else f"It expires on {row['expires_on']}. ")
            watch_statement = (f"Watch: {row['summary']} {detail}Source: {row['publisher']}, "
                               f"{row['published_on'] or 'date unknown'}, {row['locator']}.")
            items.append({**base_item, "record_id": f"{row['event_id']}:{row['span_id']}:watch",
                          "fields": {**fields, "brief_section": "Watch",
                                     "convergence_id": converged["convergence_id"] if converged else None},
                          "statement": watch_statement, "retrieval_rank": rank,
                          "inclusion_reason": "active convergence composition or approaching expiry"})
            rank += 1

    # Coverage is ordered by retrieval time rather than event occurrence time. This separate query
    # also prevents the content limit from silently hiding an otherwise-covered source class.
    coverage_rows = conn.execute(
        "SELECT * FROM (SELECT e.id event_id,d.kind document_kind,d.title,d.publisher,d.published_on,"
        "d.retrieved_at,d.url,s.id span_id,s.locator,s.excerpt,"
        "ROW_NUMBER() OVER (PARTITION BY d.kind ORDER BY d.retrieved_at DESC,d.id,s.id) source_rank "
        "FROM company_events e JOIN company_event_evidence ee ON ee.event_id=e.id AND ee.archived=0 "
        "JOIN intel_document_spans s ON s.id=ee.span_id AND s.archived=0 "
        "JOIN intel_documents d ON d.id=s.document_id AND d.archived=0 AND d.correction_state='active' "
        "WHERE e.account_id=? AND e.status='confirmed' AND e.expires_on>=date('now') AND e.archived=0) "
        "WHERE source_rank=1 ORDER BY document_kind", (run["account_id"],)
    ).fetchall()
    covered_kinds = {row["document_kind"] for row in coverage_rows}
    if (listing and listing["listing_status"] == "public" and
            not covered_kinds.intersection({"earnings_call", "annual_report", "regulatory_filing"})):
        gaps.append("No confirmed earnings or filing evidence is available for this public company.")
    coverage_items = []
    for coverage_rank, row in enumerate(coverage_rows, 1):
        source_class = row["document_kind"]
        coverage_statement = (f"Coverage includes {source_class.replace('_', ' ')} through "
                              f"{row['retrieved_at'][:10]}: {row['title']}, {row['locator']}.")
        fields = {"brief_section": "Coverage and as-of", "source_class": source_class,
                  "retrieved_at": row["retrieved_at"], "title": row["title"],
                  "publisher": row["publisher"], "published_on": row["published_on"],
                  "locator": row["locator"], "evidence_excerpt": _safe_text(row["excerpt"]),
                  "source_url": row["url"], "native_record_type": "company_event",
                  "native_record_id": row["event_id"], "evidence_span_id": row["span_id"]}
        coverage_items.append({"record_type": "intel_document_span", "record_id": f"{row['span_id']}:coverage",
                      "account_id": run["account_id"], "program_id": None,
                      "record_version": row["retrieved_at"], "authority": "confirmed_public_span",
                      "freshness_state": "current", "visibility": "internal", "fields": fields,
                      "statement": coverage_statement, "excerpt": _safe_text(row["excerpt"]),
                      "retrieval_method": "company_inputs", "retrieval_rank": coverage_rank,
                      "inclusion_reason": "latest live exact span for covered public source class"})
    # Coverage is the brief's as-of contract, so reserve the leading ranks for it. Content starts
    # after those ranks and remains bounded without being able to crowd coverage out of the packet.
    for item in items:
        item["retrieval_rank"] += len(coverage_items)
    return (coverage_items + items)[:MAX_PACKET_ITEMS], gaps, excluded


def build_packet(conn: sqlite3.Connection, run: dict) -> dict:
    """Build the stable, bounded packet for one already-validated plan."""
    included: list[dict] = []
    excluded: list[dict] = []
    readers: list[str] = []
    retrieval_rounds = 1
    intent = run["intent"]
    coverage_gaps: list[str] = []
    if intent == "company_brief":
        readers.append("get_company_inputs")
        company_items, coverage_gaps, company_excluded = company_inputs(conn, run)
        included.extend(company_items)
        excluded.extend(company_excluded)
    elif intent == "changes":
        readers.append("get_material_changes")
        included.extend(material_changes(conn, run, run.get("time_window_start"),
                                         run.get("time_window_end")))
    elif intent == "weekly":
        readers.append("get_week_inputs")
        included.extend(week_inputs(conn, run))
    else:
        readers.extend(["resolve_entities", "search_records"])
        included.extend(resolve_named_entities(conn, run, run["query_text"]))
        found, rejected = search_records(conn, run, run["query_text"])
        included.extend(found)
        excluded.extend(rejected)
        if not found:
            fallback, fallback_rejected = bounded_domain_fallback(conn, run, run["query_text"])
            if fallback or fallback_rejected:
                retrieval_rounds = 2
                readers.append("bounded_domain_fallback")
                included.extend(fallback)
                excluded.extend(fallback_rejected)
        q = run["query_text"].lower()
        if any(word in q for word in
               ("account", "portfolio", "delivery status", "commercial status", "contract",
                "renewal", "program count", "programs")):
            readers.insert(0, "get_account_snapshot")
            included.extend(account_snapshots(conn, run))
        if any(word in q for word in ("metric", "evidence", "adoption", "usage", "value")):
            readers.append("get_evidence_context")
            included.extend(evidence_context(conn, run))

    # Deduplicate by native identity, prefer the earlier/higher-authority reader, then assign stable
    # packet ids only after sorting. Per-run ids and timestamps are deliberately not in the hash.
    unique: dict[tuple[str, str], dict] = {}
    for item in included:
        unique.setdefault((item["record_type"], item["record_id"]), item)
    ordered = sorted(unique.values(), key=lambda i: (
        i["retrieval_rank"], i["record_type"], i["record_id"]))[:MAX_PACKET_ITEMS]
    for index, item in enumerate(ordered, 1):
        item["packet_id"] = f"p{index:03d}"

    # Entity resolution must be inspectable and must never pick a winner by search rank. If the
    # operator used a name that maps to multiple live records in the selected scope, preserve every
    # candidate and make the ambiguity part of the answer contract.
    query_folded = " ".join(run["query_text"].lower().split())
    named: dict[tuple[str, str], list[dict]] = {}
    for item in ordered:
        label = str(item["fields"].get("name") or "").strip()
        matched_label = item.get("entity_match_label") or label
        if not label or (not item.get("entity_match_label") and label.lower() not in query_folded):
            continue
        named.setdefault((item["record_type"], matched_label.lower()), []).append(item)
    ambiguities, resolved = [], []
    for (record_type, _), candidates in sorted(named.items()):
        entry = {
            "record_type": record_type,
            "label": candidates[0].get("entity_match_label") or candidates[0]["fields"]["name"],
            "match_kind": candidates[0].get("entity_match_kind") or "exact",
            "candidates": [
                {"record_id": item["record_id"], "packet_id": item["packet_id"],
                 "account_id": item.get("account_id"), "program_id": item.get("program_id")}
                for item in candidates
            ],
        }
        if len(candidates) > 1:
            ambiguities.append(entry)
        else:
            resolved.append(entry)
    if run.get("context_run_id"):
        prior = conn.execute("SELECT resolved_entities_json FROM copilot_runs WHERE id=?",
                             (run["context_run_id"],)).fetchone()
        for entity in json.loads(prior["resolved_entities_json"] or "[]") if prior else []:
            inherited = {**entity, "inherited_from_run_id": run["context_run_id"]}
            if not any(e.get("record_type") == inherited.get("record_type") and
                       e.get("label") == inherited.get("label") for e in resolved + ambiguities):
                resolved.append(inherited)
    canonical = json.dumps([
        {k: item[k] for k in ("record_type", "record_id", "account_id", "program_id",
                              "record_version", "authority", "freshness_state", "visibility",
                              "fields", "statement")}
        for item in ordered], sort_keys=True, separators=(",", ":"), default=str)
    return {"items": ordered, "readers": readers, "excluded": excluded,
            "ambiguities": ambiguities, "resolved_entities": resolved,
            "coverage_gaps": coverage_gaps,
            "packet_hash": hashlib.sha256(canonical.encode()).hexdigest(),
            "packet_bytes": len(canonical.encode()), "retrieval_rounds": retrieval_rounds}
