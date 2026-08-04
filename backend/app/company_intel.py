"""Stage 14 company intelligence domain service.

The adapter supplies deterministic public-artifact fixtures. This module owns identity,
proposal review, exact evidence, hiring derivation, and reproducible convergence.
"""
from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from datetime import date, timedelta

from fastapi import HTTPException

from . import adapters, audit, jobs, repo
from .db import new_id, now_utc

RULE_VERSION = "company-convergence-v1"
_INSTRUCTION_LIKE = re.compile(
    r"(?i)(ignore (?:all|any|the|previous|prior)|system prompt|developer message|follow these instructions|"
    r"do not cite|reveal (?:the )?(?:prompt|secret)|assistant:|<\|(?:system|assistant|user)\|>)")
_ENTAILMENT_STOP = {"about", "after", "again", "announced", "company", "during", "from", "into",
                    "named", "public", "source", "their", "there", "these", "they", "this", "with"}


def _today() -> date:
    """UTC, matching now_utc() and SQLite's date('now'). A local date would disagree with the
    triggers and with expiry comparisons whenever the local and UTC dates differ."""
    return date.fromisoformat(now_utc()[:10])


def _json(value) -> str:
    return json.dumps(value, separators=(",", ":"), sort_keys=True)


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _primary(conn: sqlite3.Connection, account_id: str) -> dict | None:
    row = conn.execute(
        "SELECT acl.*,ce.legal_name,ce.listing_status,ce.aliases_json,ce.hq_country,ce.fiscal_year_end_month "
        "FROM account_company_links acl JOIN company_entities ce ON ce.id=acl.company_entity_id "
        "WHERE acl.account_id=? AND acl.relationship='primary' AND acl.valid_to IS NULL "
        "AND acl.archived=0 AND ce.archived=0", (account_id,)).fetchone()
    return dict(row) if row else None


def get_company(conn: sqlite3.Connection, account_id: str) -> dict:
    repo.get_row(conn, "accounts", account_id)
    primary = _primary(conn, account_id)
    watch = conn.execute("SELECT * FROM company_watch_profiles WHERE account_id=? AND archived=0",
                         (account_id,)).fetchone()
    identifiers = []
    if primary:
        identifiers = [dict(r) for r in conn.execute(
            "SELECT * FROM company_identifiers WHERE company_entity_id=? AND archived=0 ORDER BY scheme,value",
            (primary["company_entity_id"],)).fetchall()]
        primary["aliases"] = json.loads(primary.pop("aliases_json") or "[]")
    result = {"company": primary, "watch": dict(watch) if watch else None,
              "identifiers": identifiers}
    if result["watch"]:
        for key in ("source_include", "source_exclude", "topic_include", "topic_exclude", "languages"):
            result["watch"][key] = json.loads(result["watch"].pop(key + "_json") or "[]")
    return result


def put_watch(conn: sqlite3.Connection, account_id: str, body: dict) -> dict:
    repo.get_row(conn, "accounts", account_id)
    ts = now_utc()
    primary = _primary(conn, account_id)
    with conn:
        if not primary:
            entity_id = new_id()
            conn.execute(
                "INSERT INTO company_entities(id,legal_name,listing_status,aliases_json,hq_country,fiscal_year_end_month,created_at,updated_at) "
                "VALUES (?,?,?,?,?,?,?,?)",
                (entity_id, body["legal_name"].strip(), body["listing_status"], _json(body["aliases"]),
                 body.get("hq_country"), body.get("fiscal_year_end_month"), ts, ts))
            conn.execute(
                "INSERT INTO account_company_links(id,account_id,company_entity_id,relationship,created_at,updated_at) "
                "VALUES (?,?,?,'primary',?,?)", (new_id(), account_id, entity_id, ts, ts))
            audit.record(conn, object_type="company_entity", object_id=entity_id, action="create",
                         after={"legal_name": body["legal_name"], "account_id": account_id})
        else:
            entity_id = primary["company_entity_id"]
            conn.execute("UPDATE company_entities SET legal_name=?,listing_status=?,aliases_json=?,hq_country=?,"
                         "fiscal_year_end_month=?,updated_at=? WHERE id=?",
                         (body["legal_name"].strip(), body["listing_status"], _json(body["aliases"]),
                          body.get("hq_country"), body.get("fiscal_year_end_month"), ts, entity_id))

        for ident in body.get("identifiers", []):
            scheme, value = ident.get("scheme"), str(ident.get("value") or "").strip()
            if scheme not in {"domain", "cik", "lei", "ticker", "provider"} or not value:
                raise HTTPException(422, "each identifier requires a supported scheme and value")
            provider = str(ident.get("provider") or "")
            jurisdiction = str(ident.get("jurisdiction") or "")
            taken = conn.execute(
                "SELECT company_entity_id FROM company_identifiers WHERE scheme=? AND provider=? AND jurisdiction=? "
                "AND value=? AND archived=0 AND valid_to IS NULL", (scheme, provider, jurisdiction, value)).fetchone()
            if taken and taken["company_entity_id"] != entity_id:
                raise HTTPException(422, f"identifier {scheme}:{value} already resolves to a different company entity")
            conn.execute(
                "INSERT OR IGNORE INTO company_identifiers(id,company_entity_id,scheme,provider,jurisdiction,value,created_at,updated_at) "
                "VALUES (?,?,?,?,?,?,?,?)", (new_id(), entity_id, scheme, provider, jurisdiction, value, ts, ts))

        values = (body["watch_tier"], _json(body["source_include"]), _json(body["source_exclude"]),
                  _json(body["topic_include"]), _json(body["topic_exclude"]), _json(body["languages"]),
                  body["cadence_days"], body["hiring_cluster_min"], body["hiring_window_days"],
                  body["convergence_max_gap_days"], ts)
        current = conn.execute("SELECT id FROM company_watch_profiles WHERE account_id=?", (account_id,)).fetchone()
        if current:
            conn.execute("UPDATE company_watch_profiles SET watch_tier=?,source_include_json=?,source_exclude_json=?,"
                         "topic_include_json=?,topic_exclude_json=?,languages_json=?,cadence_days=?,hiring_cluster_min=?,"
                         "hiring_window_days=?,convergence_max_gap_days=?,updated_at=?,archived=0 WHERE id=?",
                         (*values, current["id"]))
        else:
            conn.execute("INSERT INTO company_watch_profiles(id,account_id,watch_tier,source_include_json,source_exclude_json,"
                         "topic_include_json,topic_exclude_json,languages_json,cadence_days,hiring_cluster_min,hiring_window_days,"
                         "convergence_max_gap_days,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                         (new_id(), account_id, *values[:-1], ts, ts))
        audit.record(conn, object_type="company_watch_profile", object_id=account_id, action="update",
                     after={"account_id": account_id, "watch_tier": body["watch_tier"]})
    # Pausing or changing the gap threshold takes effect immediately for persisted attention.
    refresh_account_signals(conn, account_id)
    return get_company(conn, account_id)


def _resolve_account(conn: sqlite3.Connection, item: dict) -> tuple[str, str] | None:
    account_id = item.get("account_id")
    if account_id:
        row = conn.execute(
            "SELECT acl.account_id,acl.company_entity_id FROM account_company_links acl "
            "WHERE acl.account_id=? AND acl.relationship='primary' AND acl.valid_to IS NULL AND acl.archived=0",
            (account_id,)).fetchone()
        return (row["account_id"], row["company_entity_id"]) if row else None
    ident = item.get("company_identifier") or {}
    rows = conn.execute(
        "SELECT acl.account_id,ci.company_entity_id FROM company_identifiers ci "
        "JOIN account_company_links acl ON acl.company_entity_id=ci.company_entity_id "
        "WHERE ci.scheme=? AND ci.provider=? AND ci.value=? AND ci.valid_to IS NULL AND ci.archived=0 "
        "AND acl.relationship='primary' AND acl.valid_to IS NULL AND acl.archived=0",
        (ident.get("scheme"), ident.get("provider", ""), ident.get("value"))).fetchall()
    return (rows[0]["account_id"], rows[0]["company_entity_id"]) if len(rows) == 1 else None


def _watch_policy_decision(conn: sqlite3.Connection, account_id: str, item: dict) -> tuple[bool, str | None]:
    """Apply the operator's watch boundary before any source record is persisted."""
    # Corrections and takedowns are governance events, not new monitoring. They must propagate
    # even when the watch is paused or its current source allow-list has changed.
    if item.get("action") == "retract":
        return True, None
    row = conn.execute(
        "SELECT * FROM company_watch_profiles WHERE account_id=? AND archived=0", (account_id,)).fetchone()
    if not row:
        return True, None
    if row["watch_tier"] == "paused":
        return False, "watch profile is paused"
    document = item.get("document") or {}
    source = str(document.get("kind") or "").lower()
    language = str(document.get("language") or "en").lower()
    event_topics = {str(event.get("kind") or "").lower() for event in item.get("events", [])}
    event_topics.update(str(event.get("summary") or "").lower() for event in item.get("events", []))

    source_include = {str(value).lower() for value in json.loads(row["source_include_json"] or "[]")}
    source_exclude = {str(value).lower() for value in json.loads(row["source_exclude_json"] or "[]")}
    topic_include = {str(value).lower() for value in json.loads(row["topic_include_json"] or "[]")}
    topic_exclude = {str(value).lower() for value in json.loads(row["topic_exclude_json"] or "[]")}
    languages = {str(value).lower() for value in json.loads(row["languages_json"] or "[]")}
    if source in source_exclude or (source_include and source not in source_include):
        return False, f"source class {source or 'unknown'} is outside watch policy"
    if languages and language not in languages:
        return False, f"language {language} is outside watch policy"
    if any(term and any(term == topic or term in topic for topic in event_topics) for term in topic_exclude):
        return False, "event topic is excluded by watch policy"
    if topic_include and not any(
            term and any(term == topic or term in topic for topic in event_topics) for term in topic_include):
        return False, "event topic is outside watch policy"
    return True, None


def _source_reference(conn, document: dict, fixture: str) -> str:
    source_id, ts = new_id(), now_utc()
    values = {"id": source_id, "type": "data_report", "label": document["title"],
              "url": document["url"], "locator": fixture,
              "tags": "company-intelligence,public,mock", "created_at": ts, "updated_at": ts}
    conn.execute(
        "INSERT INTO source_references(id,type,label,url,locator,tags,created_at,updated_at) "
        "VALUES (?,?,?,?,?,?,?,?)", tuple(values.values()))
    audit.record(conn, object_type="source_reference", object_id=source_id, action="create", after=values)
    return source_id


def _sync_item(conn: sqlite3.Connection, run_id: str, item: dict, account_id: str,
               entity_id: str) -> str:
    provider = item.get("provider", "fixture")
    document = item["document"]
    action = item.get("action", "upsert")
    if action == "retract":
        prior = conn.execute(
            "SELECT * FROM intel_documents WHERE provider=? AND external_id=? AND archived=0 "
            "ORDER BY version DESC LIMIT 1", (provider, document["external_id"])).fetchone()
        if not prior or prior["correction_state"] == "retracted":
            return "skipped"
        before = dict(prior)
        conn.execute("UPDATE intel_documents SET correction_state='retracted',updated_at=? WHERE id=?",
                     (now_utc(), prior["id"]))
        audit.record(conn, object_type="intel_document", object_id=prior["id"], action="update",
                     before=before, after={"correction_state": "retracted",
                                           "reason": item.get("correction_reason")})
        return "retracted"
    existing = conn.execute(
        "SELECT id FROM intel_documents WHERE provider=? AND external_id=? AND version=? AND archived=0",
        (provider, document["external_id"], document.get("version", 1))).fetchone()
    if existing:
        return "skipped"
    ts = now_utc()
    excerpt = "\n".join(span["excerpt"] for span in document.get("spans", []))
    src_id = _source_reference(conn, document, item["fixture"])
    doc_id = new_id()
    conn.execute(
        "INSERT INTO intel_documents(id,company_entity_id,provider,external_id,version,kind,title,publisher,published_on,"
        "retrieved_at,url,content_hash,language,source_role,canonical_source_key,origin_group,source_reference_id,created_at,updated_at) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (doc_id, entity_id, provider, document["external_id"], document.get("version", 1), document["kind"],
         document["title"], document["publisher"], document.get("published_on"), document.get("retrieved_at", ts),
         document["url"], _hash(excerpt), document.get("language", "en"), document.get("source_role", "original"),
         document.get("canonical_source_key", document["external_id"]),
         document.get("origin_group", document["external_id"]), src_id, ts, ts))
    supersedes_version = document.get("supersedes_version")
    corrected = False
    if supersedes_version is not None:
        prior = conn.execute(
            "SELECT * FROM intel_documents WHERE company_entity_id=? AND provider=? AND external_id=? "
            "AND version=? AND archived=0", (entity_id, provider, document["external_id"],
                                              supersedes_version)).fetchone()
        if not prior:
            raise ValueError("correction references an unknown document version")
        conn.execute("UPDATE intel_documents SET correction_state='superseded',superseded_by_id=?,updated_at=? WHERE id=?",
                     (doc_id, ts, prior["id"]))
        audit.record(conn, object_type="intel_document", object_id=prior["id"], action="update",
                     before=dict(prior), after={"correction_state": "superseded", "superseded_by_id": doc_id})
        corrected = True
    span_ids = []
    for span in document.get("spans", []):
        sid = new_id(); span_ids.append(sid)
        conn.execute(
            "INSERT INTO intel_document_spans(id,document_id,locator,excerpt,excerpt_hash,section,speaker,created_at,updated_at) "
            "VALUES (?,?,?,?,?,?,?,?,?)", (sid, doc_id, span["locator"], span["excerpt"], _hash(span["excerpt"]),
             span.get("section"), span.get("speaker"), ts, ts))
    for event in item.get("events", []):
        kind = conn.execute("SELECT id FROM company_event_kinds WHERE key=? AND active=1 AND archived=0",
                            (event["kind"],)).fetchone()
        if not kind or not span_ids:
            continue
        event_id = new_id()
        conn.execute(
            "INSERT INTO company_events(id,account_id,company_entity_id,kind_id,status,summary,canonical_occurrence_key,"
            "occurred_on,occurred_precision,observed_at,provider,external_id,derivation_version,created_at,updated_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (event_id, account_id, entity_id, kind["id"], "proposed", event["summary"],
             event.get("canonical_occurrence_key", event["external_id"]), event.get("occurred_on"),
             event.get("occurred_precision", "day"), event.get("observed_at", ts), provider,
             event["external_id"], event.get("derivation_version", f"fixture-v{document.get('version', 1)}"), ts, ts))
        for index in event.get("span_indexes", [0]):
            if 0 <= index < len(span_ids):
                conn.execute(
                    "INSERT INTO company_event_evidence(id,event_id,span_id,evidence_role,created_at,updated_at) "
                    "VALUES (?,?,?,'original',?,?)", (new_id(), event_id, span_ids[index], ts, ts))
        if event.get("account_wide", True):
            conn.execute(
                "INSERT INTO company_event_links(id,event_id,account_target_id,status,rationale,suggested_by,created_at,updated_at) "
                "VALUES (?,?,?,'proposed',?,'matcher',?,?)",
                (new_id(), event_id, account_id, "Public event applies to the linked company account.", ts, ts))
        if event["kind"] == "leadership_change":
            person = None
            if event.get("person_name"):
                matches = conn.execute(
                    "SELECT id FROM persons WHERE account_id=? AND lower(name)=lower(?) AND archived=0",
                    (account_id, event["person_name"])).fetchall()
                person = matches[0]["id"] if len(matches) == 1 else None
            change_type = event.get("leadership_change_type", "title_change")
            org_kind = {"arrival": "arrival", "departure": "departure",
                        "title_change": "title_change"}.get(change_type, "restructure")
            org_external = f"company-intel:{provider}:{event['external_id']}"
            existing_org = conn.execute(
                "SELECT id FROM org_change_flags WHERE external_id=? AND archived=0", (org_external,)).fetchone()
            if not existing_org:
                org_id = new_id()
                conn.execute(
                    "INSERT INTO org_change_flags(id,account_id,person_id,kind,status,summary,old_title,new_title,"
                    "person_name,occurred_on,source_reference_id,external_id,created_at,updated_at) "
                    "VALUES (?,?,?,?, 'proposed',?,?,?,?,?,?,?,?,?)",
                    (org_id, account_id, person, org_kind, event["summary"], event.get("old_title"),
                     event.get("new_title"), event.get("person_name"), event.get("occurred_on"),
                     src_id, org_external, ts, ts))
                conn.execute("UPDATE company_events SET org_change_flag_id=? WHERE id=?", (org_id, event_id))
    posting = item.get("hiring_posting")
    if posting and span_ids:
        conn.execute(
            "INSERT INTO hiring_postings(id,account_id,company_entity_id,provider,external_id,normalized_posting_key,title,"
            "function_label,region_label,first_seen_on,last_seen_on,state,document_id,span_id,created_at,updated_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (new_id(), account_id, entity_id, provider, posting["external_id"],
             posting.get("normalized_posting_key", posting["external_id"]), posting["title"],
             posting["function_label"], posting["region_label"], posting["first_seen_on"],
             posting["last_seen_on"], posting.get("state", "active"), doc_id, span_ids[0], ts, ts))
    return "corrected" if corrected else "created"


def sync_company_intel(conn: sqlite3.Connection) -> dict:
    ts, run_id = now_utc(), new_id()
    counts = {key: 0 for key in ("created", "skipped", "unmatched", "corrected", "retracted", "error")}
    affected_accounts: set[str] = set()
    with conn:
        conn.execute("INSERT INTO intel_sync_runs(id,provider,mode,status,started_at,created_at,updated_at) "
                     "VALUES (?,'fixture','mock_json','running',?,?,?)", (run_id, ts, ts, ts))
        for item in adapters.fetch_company_intel():
            resolved = _resolve_account(conn, item)
            outcome, detail = "unmatched", None
            conn.execute("SAVEPOINT company_intel_item")
            try:
                if resolved:
                    affected_accounts.add(resolved[0])
                    allowed, detail = _watch_policy_decision(conn, resolved[0], item)
                    outcome = _sync_item(conn, run_id, item, *resolved) if allowed else "skipped"
                else:
                    detail = "no single active primary company link matched"
            except (KeyError, TypeError, sqlite3.IntegrityError, ValueError) as exc:
                outcome, detail = "error", str(exc)
                conn.execute("ROLLBACK TO company_intel_item")
            finally:
                conn.execute("RELEASE company_intel_item")
            counts[outcome] += 1
            conn.execute(
                "INSERT INTO intel_sync_items(id,run_id,fixture,provider,external_id,company_entity_id,outcome,detail,created_at,updated_at) "
                "VALUES (?,?,?,?,?,?,?,?,?,?)",
                (new_id(), run_id, item.get("fixture"), item.get("provider", "fixture"),
                 item.get("document", {}).get("external_id"), resolved[1] if resolved else None,
                 outcome, detail, ts, ts))
        status = "partial" if counts["error"] or counts["unmatched"] else "completed"
        conn.execute("UPDATE intel_sync_runs SET status=?,created_count=?,skipped_count=?,unmatched_count=?,"
                     "corrected_count=?,retracted_count=?,error_count=?,completed_at=?,updated_at=? WHERE id=?",
                     (status, counts["created"], counts["skipped"], counts["unmatched"], counts["corrected"],
                     counts["retracted"], counts["error"], now_utc(), now_utc(), run_id))
    for account_id in affected_accounts:
        refresh_account_signals(conn, account_id)
    return {"run_id": run_id, **counts}


@jobs.register("sync_company_intel")
def sync_company_intel_job(conn: sqlite3.Connection, payload: dict) -> dict:
    return sync_company_intel(conn)


def feed(conn: sqlite3.Connection, account_id: str, status: str | None = None) -> list[dict]:
    repo.get_row(conn, "accounts", account_id)
    params: list = [account_id]
    clause = " AND e.status=?" if status else ""
    if status: params.append(status)
    rows = conn.execute(
        "SELECT e.*,k.key kind,k.label kind_label,k.direction,d.id document_id,d.title document_title,"
        "d.publisher,d.published_on,d.url,d.origin_group,s.id span_id,s.locator,s.excerpt "
        "FROM company_events e JOIN company_event_kinds k ON k.id=e.kind_id "
        "LEFT JOIN company_event_evidence ee ON ee.event_id=e.id AND ee.archived=0 "
        "LEFT JOIN intel_document_spans s ON s.id=ee.span_id AND s.archived=0 "
        "LEFT JOIN intel_documents d ON d.id=s.document_id AND d.archived=0 "
        "WHERE e.account_id=? AND e.archived=0" + clause +
        " ORDER BY COALESCE(e.occurred_on,e.observed_at) DESC,e.created_at DESC", tuple(params)).fetchall()
    grouped: dict[str, dict] = {}
    for raw in rows:
        row = dict(raw); event_id = row["id"]
        item = grouped.setdefault(event_id, {k: v for k, v in row.items()
                                             if k not in {"span_id","locator","excerpt"}},)
        item.setdefault("evidence", [])
        if row["span_id"]:
            item["evidence"].append({"span_id": row["span_id"], "document_id": row["document_id"],
                                     "title": row["document_title"], "publisher": row["publisher"],
                                     "published_on": row["published_on"], "url": row["url"],
                                     "locator": row["locator"], "excerpt": row["excerpt"]})
    for item in grouped.values():
        item["links"] = [dict(r) for r in conn.execute(
            "SELECT * FROM company_event_links WHERE event_id=? AND archived=0 ORDER BY created_at",
            (item["id"],)).fetchall()]
    return list(grouped.values())


def confirm_event(conn: sqlite3.Connection, event_id: str, actor: str) -> dict:
    event = repo.get_row(conn, "company_events", event_id)
    if event["status"] != "proposed":
        raise HTTPException(409, "only proposed events can be confirmed")
    kind = repo.get_row(conn, "company_event_kinds", event["kind_id"])
    if not event["occurred_on"]:
        raise HTTPException(422, "occurred_on is required before confirmation")
    excerpts = [row["excerpt"] for row in conn.execute(
        "SELECT s.excerpt FROM company_event_evidence ee JOIN intel_document_spans s ON s.id=ee.span_id "
        "JOIN intel_documents d ON d.id=s.document_id WHERE ee.event_id=? AND ee.archived=0 AND s.archived=0 "
        "AND d.archived=0 AND d.correction_state='active'", (event_id,)).fetchall()]
    if not excerpts:
        raise HTTPException(422, "confirmed company events require a live evidence span")
    if any(_INSTRUCTION_LIKE.search(excerpt or "") for excerpt in excerpts):
        raise HTTPException(422, "public evidence contains quarantined instruction-like text")
    summary_terms = {term for term in re.findall(r"[a-z0-9]+", event["summary"].lower())
                     if len(term) >= 4 and term not in _ENTAILMENT_STOP}
    evidence_terms = set(re.findall(r"[a-z0-9]+", " ".join(excerpts).lower()))
    overlap = summary_terms & evidence_terms
    if summary_terms and len(overlap) < min(2, len(summary_terms)):
        raise HTTPException(422, "event summary is not entailed by its live evidence excerpts")
    expiry = (date.fromisoformat(event["occurred_on"]) + timedelta(days=kind["default_decay_days"])).isoformat()
    return repo.patch(conn, "company_events", event_id,
                      {"status": "confirmed", "expires_on": expiry, "confirmed_at": now_utc(),
                       "confirmed_by": actor}, object_type="company_event")


def dismiss_event(conn: sqlite3.Connection, event_id: str, reason: str) -> dict:
    if not reason.strip():
        raise HTTPException(422, "dismissal reason is required")
    event = repo.patch(conn, "company_events", event_id,
                       {"status": "dismissed", "dismissal_reason": reason.strip()}, object_type="company_event")
    refresh_account_signals(conn, event["account_id"])
    return event


def retract_document(conn: sqlite3.Connection, document_id: str, actor: str, reason: str) -> dict:
    document = repo.get_row(conn, "intel_documents", document_id)
    if document["correction_state"] == "retracted":
        raise HTTPException(409, "document is already retracted")
    ts = now_utc()
    with conn:
        conn.execute("UPDATE intel_documents SET correction_state='retracted',updated_at=? WHERE id=?",
                     (ts, document_id))
        audit.record(conn, object_type="intel_document", object_id=document_id, action="update",
                     actor_id=actor, before=document,
                     after={"correction_state": "retracted", "reason": reason})
    accounts = [row["account_id"] for row in conn.execute(
        "SELECT DISTINCT e.account_id FROM company_event_evidence ee JOIN company_events e ON e.id=ee.event_id "
        "JOIN intel_document_spans s ON s.id=ee.span_id WHERE s.document_id=?", (document_id,)).fetchall()]
    for account_id in accounts:
        refresh_account_signals(conn, account_id)
    return repo.get_row(conn, "intel_documents", document_id)


def create_link(conn: sqlite3.Connection, event_id: str, body: dict) -> dict:
    repo.get_row(conn, "company_events", event_id)
    values = {k: body.get(k) for k in ("account_target_id","segment_id","view_id","use_case_id","cell_id","person_id")}
    values.update({"event_id": event_id, "status": "proposed", "rationale": body["rationale"],
                   "suggested_by": body.get("suggested_by", "operator")})
    return repo.insert(conn, "company_event_links", values, object_type="company_event_link")


def confirm_link(conn: sqlite3.Connection, link_id: str, actor: str) -> dict:
    link = repo.get_row(conn, "company_event_links", link_id)
    event = repo.get_row(conn, "company_events", link["event_id"])
    if event["status"] != "confirmed":
        raise HTTPException(422, "confirm the event before confirming its map link")
    result = repo.patch(conn, "company_event_links", link_id,
                        {"status": "confirmed", "confirmed_at": now_utc(), "confirmed_by": actor},
                        object_type="company_event_link")
    refresh_account_signals(conn, event["account_id"])
    return result


def dismiss_link(conn: sqlite3.Connection, link_id: str, reason: str) -> dict:
    if not reason.strip():
        raise HTTPException(422, "link dismissal reason is required")
    link = repo.get_row(conn, "company_event_links", link_id)
    event = repo.get_row(conn, "company_events", link["event_id"])
    result = repo.patch(conn, "company_event_links", link_id,
                        {"status": "dismissed", "dismissal_reason": reason.strip()},
                        object_type="company_event_link")
    refresh_account_signals(conn, event["account_id"])
    return result


def suggest_links(conn: sqlite3.Connection, event_id: str) -> list[dict]:
    event = repo.get_row(conn, "company_events", event_id)
    text = event["summary"].lower()
    candidates: list[dict] = []
    for row in conn.execute(
        "SELECT id,name,business_unit,region FROM population_segments WHERE account_id=? AND archived=0",
        (event["account_id"],)).fetchall():
        labels = [row["name"], row["business_unit"], row["region"]]
        if any(label and label.lower() in text for label in labels):
            candidates.append({"segment_id": row["id"], "rationale":
                               f"Event language matches population segment {row['name']}."})
    for row in conn.execute(
        "SELECT k.phrase,k.use_case_id,u.name FROM company_link_keywords k "
        "JOIN use_cases u ON u.id=k.use_case_id AND u.archived=0 "
        "WHERE k.archived=0 AND (k.account_id IS NULL OR k.account_id=?)",
        (event["account_id"],)).fetchall():
        if row["phrase"].lower() in text:
            candidates.append({"use_case_id": row["use_case_id"], "rationale":
                               f"Governed keyword “{row['phrase']}” maps to {row['name']}."})
    if event.get("org_change_flag_id"):
        person = conn.execute("SELECT person_id FROM org_change_flags WHERE id=?",
                              (event["org_change_flag_id"],)).fetchone()
        if person and person["person_id"]:
            candidates.append({"person_id": person["person_id"],
                               "rationale": "Resolved person from the linked org-change proposal."})
    created = []
    for candidate in candidates:
        target_column = next(key for key in ("segment_id","use_case_id","person_id") if candidate.get(key))
        exists = conn.execute(
            f"SELECT 1 FROM company_event_links WHERE event_id=? AND {target_column}=? AND archived=0",
            (event_id, candidate[target_column])).fetchone()
        if not exists:
            created.append(repo.insert(conn, "company_event_links", {
                "event_id": event_id, target_column: candidate[target_column], "status": "proposed",
                "rationale": candidate["rationale"], "suggested_by": "matcher",
            }, object_type="company_event_link"))
    return created


def create_link_keyword(conn: sqlite3.Connection, account_id: str, phrase: str,
                        use_case_id: str) -> dict:
    repo.get_row(conn, "accounts", account_id)
    use_case = repo.get_row(conn, "use_cases", use_case_id)
    if use_case.get("account_id") not in (None, account_id):
        raise HTTPException(422, "use case belongs to a different account")
    return repo.insert(conn, "company_link_keywords", {
        "account_id": account_id, "phrase": phrase.strip().lower(), "use_case_id": use_case_id,
    }, object_type="company_link_keyword")


def overlay(conn: sqlite3.Connection, account_id: str) -> dict:
    today = _today().isoformat()
    rows = conn.execute(
        "SELECT l.*,e.summary,e.id event_id,k.direction FROM company_event_links l "
        "JOIN company_events e ON e.id=l.event_id JOIN company_event_kinds k ON k.id=e.kind_id "
        "WHERE e.account_id=? AND e.status='confirmed' AND e.expires_on>=? AND e.archived=0 "
        "AND l.status='confirmed' AND l.archived=0", (account_id, today)).fetchall()
    result = {"segments": {}, "views": {}, "use_cases": {}, "cells": {}}
    for raw in rows:
        row = dict(raw)
        for column, key in (("segment_id","segments"),("view_id","views"),
                            ("use_case_id","use_cases"),("cell_id","cells")):
            if row[column]: result[key].setdefault(row[column], []).append(
                {"event_id": row["event_id"], "summary": row["summary"], "direction": row["direction"]})
    return result


def derive_hiring_events(conn: sqlite3.Connection, account_id: str) -> dict:
    """Materialize dated aggregates and proposal-only clusters from active unique postings."""
    primary = _primary(conn, account_id)
    if not primary:
        raise HTTPException(422, "account has no primary company link")
    watch = conn.execute("SELECT * FROM company_watch_profiles WHERE account_id=? AND archived=0",
                         (account_id,)).fetchone()
    if watch and watch["watch_tier"] == "paused":
        return {"observations": 0, "proposed_events": 0, "event_ids": [], "paused": True}
    minimum = int(watch["hiring_cluster_min"] if watch else 5)
    window = int(watch["hiring_window_days"] if watch else 21)
    today = _today(); cutoff = (today - timedelta(days=window)).isoformat(); ts = now_utc()
    groups = conn.execute(
        "SELECT function_label,region_label,COUNT(DISTINCT normalized_posting_key) postings_count "
        "FROM hiring_postings WHERE account_id=? AND state='active' AND archived=0 AND last_seen_on>=? "
        "GROUP BY function_label,region_label", (account_id, cutoff)).fetchall()
    observations, proposed = 0, []
    with conn:
        for group in groups:
            conn.execute(
                "INSERT INTO hiring_observations(id,account_id,function_label,region_label,postings_count,"
                "observed_on,derivation_version,created_at,updated_at) VALUES (?,?,?,?,?,?,'hiring-v1',?,?) "
                "ON CONFLICT(account_id,function_label,region_label,observed_on,derivation_version) DO UPDATE SET "
                "postings_count=excluded.postings_count,updated_at=excluded.updated_at",
                (new_id(), account_id, group["function_label"], group["region_label"],
                 group["postings_count"], today.isoformat(), ts, ts))
            observations += 1
            if group["postings_count"] < minimum:
                continue
            # The occurrence is the cluster, not the day it was observed: a persisting cluster must
            # not re-propose daily while its prior event is still under review or still live.
            cluster_key = f"hiring:{account_id}:{group['function_label']}:{group['region_label']}"
            external_id = f"{cluster_key}:{today.isoformat()}"
            if conn.execute(
                "SELECT 1 FROM company_events WHERE provider='derived-hiring' AND canonical_occurrence_key=? "
                "AND archived=0 AND (status='proposed' OR (status='confirmed' AND expires_on>=?))",
                    (cluster_key, today.isoformat())).fetchone():
                continue
            event_id = new_id()
            summary = (f"{group['postings_count']} active unique postings cluster in "
                       f"{group['function_label']} · {group['region_label']}.")
            conn.execute(
                "INSERT INTO company_events(id,account_id,company_entity_id,kind_id,status,summary,canonical_occurrence_key,"
                "occurred_on,occurred_precision,observed_at,provider,external_id,derivation_version,created_at,updated_at) "
                "VALUES (?,?,?,'cek-hiring','proposed',?,?,?,'day',?,'derived-hiring',?,'hiring-v1',?,?)",
                (event_id, account_id, primary["company_entity_id"], summary, cluster_key,
                 today.isoformat(), ts, external_id, ts, ts))
            spans = conn.execute(
                "SELECT DISTINCT span_id FROM hiring_postings WHERE account_id=? AND function_label=? AND region_label=? "
                "AND state='active' AND archived=0 AND last_seen_on>=? AND span_id IS NOT NULL",
                (account_id, group["function_label"], group["region_label"], cutoff)).fetchall()
            for span in spans:
                conn.execute("INSERT INTO company_event_evidence(id,event_id,span_id,evidence_role,created_at,updated_at) "
                             "VALUES (?,?,?,'derived',?,?)", (new_id(), event_id, span["span_id"], ts, ts))
            conn.execute("INSERT INTO company_event_links(id,event_id,account_target_id,status,rationale,suggested_by,created_at,updated_at) "
                         "VALUES (?,?,?,'proposed','Derived posting cluster applies account-wide','matcher',?,?)",
                         (new_id(), event_id, account_id, ts, ts))
            proposed.append(event_id)
    return {"observations": observations, "proposed_events": len(proposed), "event_ids": proposed}


def _target(link: sqlite3.Row) -> tuple[str, str]:
    for column, kind in (("account_target_id","account"),("segment_id","segment"),
                         ("view_id","view"),("use_case_id","use_case")):
        if link[column]: return kind, link[column]
    return "", ""


def evaluate_convergence(conn: sqlite3.Connection, account_id: str) -> dict:
    repo.get_row(conn, "accounts", account_id)
    today, ts = _today().isoformat(), now_utc()
    watch = conn.execute("SELECT watch_tier,convergence_max_gap_days FROM company_watch_profiles WHERE account_id=? AND archived=0",
                         (account_id,)).fetchone()
    max_gap = int(watch["convergence_max_gap_days"] if watch else 120)
    if watch and watch["watch_tier"] == "paused":
        with conn:
            current = conn.execute(
                "SELECT id FROM company_convergences WHERE account_id=? AND status='active' AND archived=0",
                (account_id,)).fetchall()
            for row in current:
                conn.execute("UPDATE company_convergences SET status='closed',closed_at=?,last_evaluated_at=?,updated_at=? "
                             "WHERE id=?", (ts, ts, ts, row["id"]))
        return {"opened": 0, "active": 0, "convergence_ids": [], "paused": True}
    links = conn.execute(
        "SELECT l.*,e.summary,e.canonical_occurrence_key,e.occurred_on,e.expires_on,e.id event_id,k.key kind,d.origin_group "
        "FROM company_event_links l JOIN company_events e ON e.id=l.event_id "
        "JOIN company_event_kinds k ON k.id=e.kind_id JOIN company_event_evidence ee ON ee.event_id=e.id AND ee.archived=0 "
        "JOIN intel_document_spans s ON s.id=ee.span_id AND s.archived=0 JOIN intel_documents d ON d.id=s.document_id "
        "WHERE e.account_id=? AND e.status='confirmed' AND e.expires_on>=? AND e.archived=0 "
        "AND l.status='confirmed' AND l.archived=0 AND d.correction_state='active' AND d.archived=0",
        (account_id, today)).fetchall()
    by_target: dict[tuple[str,str], dict[str,dict]] = {}
    for link in links:
        target = _target(link)
        if not target[0]: continue
        event = dict(link)
        event_map = by_target.setdefault(target, {})
        if event["event_id"] in event_map:
            event_map[event["event_id"]]["origin_groups"].add(event["origin_group"])
        else:
            event["origin_groups"] = {event["origin_group"]}
            event_map[event["event_id"]] = event
    active_keys, opened = set(), []
    with conn:
        for (target_kind, target_id), event_map in by_target.items():
            events = list(event_map.values()); composing: set[str] = set()
            for i, left in enumerate(events):
                for right in events[i+1:]:
                    gap = abs((date.fromisoformat(left["occurred_on"]) - date.fromisoformat(right["occurred_on"])).days)
                    independent = (left["kind"] != right["kind"] and
                                   left["canonical_occurrence_key"] != right["canonical_occurrence_key"] and
                                   left["origin_groups"].isdisjoint(right["origin_groups"]))
                    overlaps = max(left["occurred_on"], right["occurred_on"]) <= min(left["expires_on"], right["expires_on"])
                    if independent and overlaps and gap <= max_gap:
                        composing.update((left["event_id"], right["event_id"]))
            if len(composing) < 2: continue
            key = f"company_convergence:{account_id}:{target_kind}:{target_id}"; active_keys.add(key)
            existing = conn.execute("SELECT id FROM company_convergences WHERE condition_key=? AND status='active' AND archived=0",
                                    (key,)).fetchone()
            summaries = [event_map[eid]["summary"] for eid in sorted(composing)]
            explanation = "Independent company events converge: " + " + ".join(summaries)
            if existing:
                convergence_id = existing["id"]
                conn.execute("UPDATE company_convergences SET explanation=?,last_evaluated_at=?,updated_at=? WHERE id=?",
                             (explanation, ts, ts, convergence_id))
                conn.execute("UPDATE company_convergence_events SET archived=1,archived_at=?,archived_by='system',updated_at=? "
                             "WHERE convergence_id=? AND archived=0", (ts, ts, convergence_id))
            else:
                convergence_id = new_id(); opened.append(convergence_id)
                conn.execute("INSERT INTO company_convergences(id,account_id,target_kind,target_id,condition_key,status,"
                             "rule_version,explanation,first_evaluated_at,last_evaluated_at,created_at,updated_at) "
                             "VALUES (?,?,?,?,?,'active',?,?,?,?,?,?)",
                             (convergence_id, account_id, target_kind, target_id, key, RULE_VERSION,
                              explanation, ts, ts, ts, ts))
            for eid in composing:
                prior = conn.execute(
                    "SELECT id FROM company_convergence_events WHERE convergence_id=? AND event_id=?",
                    (convergence_id, eid)).fetchone()
                if prior:
                    conn.execute("UPDATE company_convergence_events SET origin_group=?,archived=0,archived_at=NULL,"
                                 "archived_by=NULL,updated_at=? WHERE id=?",
                                 (_json(sorted(event_map[eid]["origin_groups"])), ts, prior["id"]))
                else:
                    conn.execute("INSERT INTO company_convergence_events(id,convergence_id,event_id,origin_group,created_at,updated_at) "
                                 "VALUES (?,?,?,?,?,?)", (new_id(), convergence_id, eid,
                                                          _json(sorted(event_map[eid]["origin_groups"])), ts, ts))
        current = conn.execute("SELECT id,condition_key FROM company_convergences WHERE account_id=? AND status='active' AND archived=0",
                               (account_id,)).fetchall()
        for row in current:
            if row["condition_key"] not in active_keys:
                conn.execute("UPDATE company_convergences SET status='closed',closed_at=?,last_evaluated_at=?,updated_at=? WHERE id=?",
                             (ts, ts, ts, row["id"]))
    return {"opened": len(opened), "active": len(active_keys), "convergence_ids": opened}


def refresh_account_signals(conn: sqlite3.Connection, account_id: str) -> dict:
    """Reevaluate persisted convergence and its Stage 7 episode after lifecycle mutations."""
    result = evaluate_convergence(conn, account_id)
    from . import stage7
    result["signals"] = stage7.evaluate_domain_signals(conn)
    return result


def account_workspace(conn: sqlite3.Connection, account_id: str) -> dict:
    info = get_company(conn, account_id)
    info["events"] = feed(conn, account_id)
    info["overlay"] = overlay(conn, account_id)
    info["convergences"] = [dict(r) for r in conn.execute(
        "SELECT * FROM company_convergences WHERE account_id=? AND archived=0 ORDER BY last_evaluated_at DESC",
        (account_id,)).fetchall()]
    info["hiring"] = [dict(r) for r in conn.execute(
        "SELECT * FROM hiring_postings WHERE account_id=? AND archived=0 ORDER BY last_seen_on DESC",
        (account_id,)).fetchall()]
    info["link_keywords"] = [dict(r) for r in conn.execute(
        "SELECT k.*,u.name use_case_name FROM company_link_keywords k JOIN use_cases u ON u.id=k.use_case_id "
        "WHERE k.archived=0 AND (k.account_id IS NULL OR k.account_id=?) ORDER BY k.phrase", (account_id,)).fetchall()]
    info["map_targets"] = {
        "segments": [dict(r) for r in conn.execute(
            "SELECT id,name FROM population_segments WHERE account_id=? AND archived=0 ORDER BY display_order,name",
            (account_id,)).fetchall()],
        "views": [dict(r) for r in conn.execute(
            "SELECT id,name FROM population_views WHERE account_id=? AND archived=0 ORDER BY name", (account_id,)).fetchall()],
        "use_cases": [dict(r) for r in conn.execute(
            "SELECT id,name FROM use_cases WHERE archived=0 AND (account_id IS NULL OR account_id=?) ORDER BY display_order,name",
            (account_id,)).fetchall()],
        "cells": [dict(r) for r in conn.execute(
            "SELECT wc.id,COALESCE(ps.name,pv.name)||' · '||uc.name name FROM whitespace_cells wc "
            "JOIN use_cases uc ON uc.id=wc.use_case_id LEFT JOIN population_segments ps ON ps.id=wc.segment_id "
            "LEFT JOIN population_views pv ON pv.id=wc.view_id WHERE wc.account_id=? AND wc.archived=0 ORDER BY name",
            (account_id,)).fetchall()],
        "people": [dict(r) for r in conn.execute(
            "SELECT id,name FROM persons WHERE account_id=? AND affiliation='client' AND archived=0 ORDER BY name",
            (account_id,)).fetchall()],
    }
    return info
