"""Account reviews, status governance, deterministic briefs, and challenge questions."""
from __future__ import annotations

import sqlite3
from datetime import date

from fastapi import HTTPException

from . import expansion, people_analytics, repo, stage75
from .db import new_id, now_utc
from .internal_forecast import evidence, operator


def create_review(conn: sqlite3.Connection, account_id: str, values: dict) -> dict:
    repo.get_row(conn, "accounts", account_id)
    participants = values.pop("participant_ids", [])
    if values.get("chair_person_id"):
        participants = list(dict.fromkeys([values["chair_person_id"], *participants]))
    for person_id in participants:
        person = repo.get_row(conn, "persons", person_id)
        if person["affiliation"] != "valence":
            raise HTTPException(422, "review participants must be Valence people")
    review = repo.insert(conn, "account_reviews", {"account_id": account_id, **values}, object_type="account_review")
    with conn:
        for person_id in participants:
            conn.execute("INSERT INTO account_review_participants(review_id,person_id,role) VALUES (?,?,?)",
                         (review["id"], person_id, "chair" if person_id == values.get("chair_person_id") else "participant"))
    return get_review(conn, review["id"])


def get_review(conn: sqlite3.Connection, review_id: str) -> dict:
    row = repo.get_row(conn, "account_reviews", review_id)
    participants = [repo.row_to_dict(r) for r in conn.execute(
        "SELECT p.id,p.name,rp.role FROM account_review_participants rp JOIN persons p ON p.id=rp.person_id WHERE rp.review_id=? ORDER BY p.name", (review_id,))]
    return {**row, "participants": participants}


def list_reviews(conn: sqlite3.Connection, account_id: str) -> list[dict]:
    repo.get_row(conn, "accounts", account_id)
    return [get_review(conn, r["id"]) for r in conn.execute("SELECT id FROM account_reviews WHERE account_id=? AND archived=0 ORDER BY COALESCE(held_on,scheduled_on) DESC", (account_id,))]


def hold_review(conn: sqlite3.Connection, review_id: str, held_on: str, interaction_id: str) -> dict:
    review = repo.get_row(conn, "account_reviews", review_id)
    interaction = repo.get_row(conn, "interactions", interaction_id)
    if interaction["account_id"] != review["account_id"]:
        raise HTTPException(422, "review interaction belongs to another account")
    if review["status"] != "planned":
        raise HTTPException(409, "only a planned review can be held")
    return repo.patch(conn, "account_reviews", review_id, {"status": "held", "held_on": held_on,
        "source_interaction_id": interaction_id}, object_type="account_review")


def create_operator_view(conn: sqlite3.Connection, account_id: str, values: dict) -> dict:
    repo.get_row(conn, "accounts", account_id)
    previous = conn.execute("SELECT id FROM operator_views WHERE account_id=? AND archived=0 ORDER BY assessed_on DESC,created_at DESC LIMIT 1", (account_id,)).fetchone()
    return repo.insert(conn, "operator_views", {"account_id": account_id, **values, "author": operator(conn),
        "supersedes_id": previous["id"] if previous else None}, object_type="operator_view")


def list_operator_views(conn: sqlite3.Connection, account_id: str) -> list[dict]:
    return repo.list_rows(conn, "operator_views", where="account_id=? ORDER BY assessed_on DESC,created_at DESC", params=(account_id,))


def assess_status(conn: sqlite3.Connection, account_id: str, values: dict) -> dict:
    account = repo.get_row(conn, "accounts", account_id)
    if values.get("recovery_owner_person_id"):
        owner = conn.execute(
            "SELECT id FROM persons WHERE id=? AND archived=0 "
            "AND (affiliation='valence' OR account_id=?)",
            (values["recovery_owner_person_id"], account_id),
        ).fetchone()
        if not owner:
            raise HTTPException(422, "recovery owner is not available in this account")
    if values.get("leadership_ask_id"):
        leadership_ask = conn.execute(
            "SELECT id FROM internal_asks WHERE id=? AND account_id=? AND archived=0",
            (values["leadership_ask_id"], account_id),
        ).fetchone()
        if not leadership_ask:
            raise HTTPException(422, "leadership ask is not available in this account")
    criteria_id = values.get("criteria_version_id")
    if not criteria_id:
        row = conn.execute("SELECT id FROM status_criteria_versions WHERE dimension=? AND account_id IS NULL AND archived=0 ORDER BY effective_on DESC LIMIT 1", (values["dimension"],)).fetchone()
        criteria_id = row["id"] if row else None
    if not criteria_id:
        raise HTTPException(422, "no status criteria are configured")
    criteria = repo.get_row(conn, "status_criteria_versions", criteria_id)
    if criteria["dimension"] != values["dimension"] or criteria.get("account_id") not in (None, account_id):
        raise HTTPException(422, "status criteria do not apply to this account and dimension")
    previous = conn.execute("SELECT id FROM account_status_assessments WHERE account_id=? AND dimension=? AND archived=0 ORDER BY assessed_on DESC,created_at DESC LIMIT 1", (account_id, values["dimension"])).fetchone()
    data = {"account_id": account_id, **values, "criteria_version_id": criteria_id,
            "author": operator(conn), "supersedes_id": previous["id"] if previous else None}
    try:
        assessment = repo.insert(conn, "account_status_assessments", data, object_type="status_assessment")
    except sqlite3.IntegrityError as exc:
        raise HTTPException(422, str(exc)) from exc
    prefix = values["dimension"]
    with conn:
        conn.execute(f"UPDATE accounts SET {prefix}_status=?,{prefix}_status_rationale=?,{prefix}_status_assessed_on=?,updated_at=? WHERE id=?",
                     (values["value"], values.get("rationale"), values["assessed_on"], now_utc(), account_id))
    return {"assessment": assessment, "account": {**account, f"{prefix}_status": values["value"]}}


def create_criteria(conn: sqlite3.Connection, values: dict) -> dict:
    if values.get("account_id"):
        repo.get_row(conn, "accounts", values["account_id"])
    # Versioning means the previous live row is archived, never overwritten.
    with conn:
        conn.execute("UPDATE status_criteria_versions SET archived=1,archived_at=?,archived_by=?,updated_at=? WHERE dimension=? AND account_id IS ? AND archived=0",
                     (now_utc(), operator(conn), now_utc(), values["dimension"], values.get("account_id")))
    return repo.insert(conn, "status_criteria_versions", {**values, "author": operator(conn)}, object_type="status_criteria")


def challenge_sheet(conn: sqlite3.Connection, review_id: str) -> dict:
    review = repo.get_row(conn, "account_reviews", review_id)
    account_id = review["account_id"]; today = date.fromisoformat(now_utc()[:10]); questions = []
    for row in conn.execute("SELECT id FROM forecast_entries WHERE account_id=? AND category IN ('commit','best_case') AND archived=0", (account_id,)):
        ev = evidence(conn, row["id"])
        if not ev["supported"]:
            questions.append({"rule": "unsupported_forecast", "question": f"What closes the evidence gaps on {ev['category'].replace('_',' ').title()} entry {row['id']}?", "source_ids": [row["id"], *[x for r in ev["missing"] for x in r["record_ids"]]]})
    for row in conn.execute("SELECT r.id,r.description,r.severity,r.mitigation,r.internal_owner_id FROM risks r JOIN programs p ON p.id=r.program_id WHERE p.account_id=? AND r.archived=0 AND r.status='open' AND r.severity='high'", (account_id,)):
        if not row["mitigation"] or not row["internal_owner_id"]:
            questions.append({"rule": "unmitigated_high_risk", "question": f"Who owns mitigation for high risk: {row['description']}?", "source_ids": [row["id"]]})
    for row in conn.execute("SELECT id,description,due_date FROM commitments WHERE account_id=? AND archived=0 AND status='open' AND due_date<?", (account_id, today.isoformat())):
        questions.append({"rule": "overdue_review_commitment", "question": f"Why is the commitment overdue: {row['description']}?", "source_ids": [row["id"]]})
    for row in conn.execute("SELECT id,need,needed_by FROM internal_asks WHERE account_id=? AND archived=0 AND status NOT IN ('delivered','declined') AND needed_by<?", (account_id, today.isoformat())):
        questions.append({"rule": "aging_ask", "question": f"What will unblock the overdue internal ask: {row['need']}?", "source_ids": [row["id"]]})
    return {"review_id": review_id, "account_id": account_id, "questions": questions,
            "generated_at": now_utc(), "deterministic": True}


def _latest_status(conn: sqlite3.Connection, account_id: str, dimension: str) -> dict | None:
    return repo.row_to_dict(conn.execute("SELECT * FROM account_status_assessments WHERE account_id=? AND dimension=? AND archived=0 ORDER BY assessed_on DESC,created_at DESC LIMIT 1", (account_id, dimension)).fetchone())


def account_brief_data(conn: sqlite3.Connection, account_id: str) -> dict:
    account = repo.get_row(conn, "accounts", account_id)
    pov = conn.execute("SELECT * FROM operator_views WHERE account_id=? AND archived=0 ORDER BY assessed_on DESC,created_at DESC LIMIT 1", (account_id,)).fetchone()
    risks = [repo.row_to_dict(r) for r in conn.execute("SELECT r.* FROM risks r JOIN programs p ON p.id=r.program_id WHERE p.account_id=? AND r.archived=0 AND r.status='open' ORDER BY CASE r.severity WHEN 'high' THEN 0 WHEN 'medium' THEN 1 ELSE 2 END,r.created_at LIMIT 3", (account_id,))]
    asks = [repo.row_to_dict(r) for r in conn.execute("SELECT * FROM internal_asks WHERE account_id=? AND archived=0 AND status NOT IN ('delivered','declined') ORDER BY needed_by LIMIT 5", (account_id,))]
    entries = [repo.row_to_dict(r) for r in conn.execute("SELECT e.* FROM forecast_entries e JOIN forecast_periods p ON p.id=e.period_id WHERE e.account_id=? AND e.archived=0 AND p.archived=0 AND p.status IN ('open','locked') ORDER BY p.ends_on,e.category", (account_id,))]
    contract = repo.row_to_dict(conn.execute("SELECT * FROM contract_versions WHERE account_id=? AND is_current=1 AND archived=0 ORDER BY created_at DESC LIMIT 1", (account_id,)).fetchone())
    growth = stage75.growth_plan(conn, account_id)
    champions = people_analytics.champion_pipeline(conn, account_id)
    try:
        renewal = stage75.renewal_center(conn, account_id)
    except HTTPException:
        renewal = None
    return {"account": account, "delivery_status": _latest_status(conn, account_id, "delivery"),
            "commercial_status": _latest_status(conn, account_id, "commercial"),
            "operator_view": repo.row_to_dict(pov), "top_risks": risks, "open_asks": asks,
            "forecast_entries": entries, "current_contract": contract, "growth_plan": growth,
            "champion_picture": champions, "renewal": renewal}


def generate_account_brief(conn: sqlite3.Connection, account_id: str, kind: str = "internal_account_brief") -> dict:
    data = account_brief_data(conn, account_id); a = data["account"]
    lines = [f"# {a['name']} — Internal account brief", "", f"Data current through {now_utc()[:10]}", "",
             "## Status"]
    for dim in ("delivery", "commercial"):
        state = data[f"{dim}_status"]
        lines.append(f"- {dim.title()}: {state['value'].replace('_',' ') if state else 'unknown'} — {state.get('rationale') if state else 'No governed assessment.'}")
    rollup = data["growth_plan"].get("rollup") or {}
    champion_rows = data["champion_picture"].get("candidates", [])
    renewal = data.get("renewal") or {}
    lines += ["", "## Operator point of view", "", (data["operator_view"]["body"] if data["operator_view"] else "Gap: no dated operator point of view."),
              "", "## Growth-plan bridge",
              f"- Target: {rollup.get('target_seats', 'unknown')} seats; named: {rollup.get('named_seats', 'unknown')}; committed: {rollup.get('committed_seats', 'unknown')}; unfunded gap: {rollup.get('unfunded_gap', 'unknown')}",
              f"- Additive: {rollup.get('additive', False)}; overlap exclusions: {len(data['growth_plan'].get('conflicts', []))}",
              "", "## Top risks"]
    lines += [f"- {r['severity']}: {r['description']} — mitigation: {r.get('mitigation') or 'missing'}" for r in data["top_risks"]] or ["- None recorded"]
    lines += ["", "## Champion picture",
              *([f"- {c.get('person_name') or c.get('person_id')}: {c.get('stage')}" for c in champion_rows] or ["- No champion candidates recorded"]),
              f"- Single-thread exposure: {data['champion_picture'].get('single_thread_risk', 'unknown')}",
              "", "## Renewal countdown",
              f"- Renewal date: {data['current_contract'].get('renewal_date') if data['current_contract'] else 'unknown'}; readiness: {renewal.get('readiness', {}).get('state', 'unknown') if isinstance(renewal.get('readiness'), dict) else 'unknown'}",
              "", "## Forecast", *([f"- {e['category']}: {e.get('amount')} {e.get('currency') or ''} {e.get('price_basis') or ''}" for e in data["forecast_entries"]] or ["- No active forecast entries"]), "", "## Internal asks", *([f"- {x['need']} — needed {x['needed_by']}" for x in data["open_asks"]] or ["- None open"])]
    doc = repo.insert(conn, "generated_documents", {"account_id": account_id, "kind": kind,
        "title": f"{a['name']} — Internal account brief", "body_markdown": "\n".join(lines),
        "status": "draft", "generated_at": now_utc(), "data_current_through": now_utc()[:10],
        "audience": "internal", "audience_profile": "working"}, object_type="generated_document")
    sources = [("account", a["id"], a["updated_at"], "account context")]
    for key, kind_name in (("operator_view", "operator_view"), ("delivery_status", "status_assessment"), ("commercial_status", "status_assessment")):
        if data[key]: sources.append((kind_name, data[key]["id"], data[key]["updated_at"], key.replace("_", " ")))
    for collection, kind_name in (("top_risks", "risk"), ("open_asks", "internal_ask"), ("forecast_entries", "forecast_entry")):
        sources += [(kind_name, r["id"], r["updated_at"], collection.replace("_", " ")) for r in data[collection]]
    if data["current_contract"]:
        sources.append(("contract_version", data["current_contract"]["id"], data["current_contract"]["updated_at"], "renewal countdown"))
    if data["growth_plan"].get("plan"):
        plan = data["growth_plan"]["plan"]
        sources.append(("account_growth_plan", plan["id"], plan["updated_at"], "growth bridge"))
    sources += [("growth_plan_line", row["id"], row["updated_at"], "growth bridge line")
                for row in data["growth_plan"].get("lines", [])]
    sources += [("champion_candidate", row["id"], row["updated_at"], "champion picture")
                for row in data["champion_picture"].get("candidates", []) if row.get("id")]
    with conn:
        for typ, record_id, version, reason in sources:
            conn.execute("INSERT INTO generated_document_sources(id,document_id,record_type,record_id,record_version,inclusion_reason,visibility_class,created_at) VALUES (?,?,?,?,?,?,?,?)",
                         (new_id(), doc["id"], typ, record_id, version, reason, "internal", now_utc()))
    return {"document": doc, "data": data}
