"""Run lifecycle, job orchestration, feedback, and draft handoff for Stage 12."""
from __future__ import annotations

import hashlib
import json
import sqlite3
import time
from typing import Any

from fastapi import HTTPException

from . import (audit, copilot_context, copilot_evaluation, copilot_model,
               copilot_validation, generators, jobs, repo)
from .db import new_id, now_utc

FORBIDDEN_REQUESTS = (
    "raw sql", "run sql", "schema dump", "read a file", "browse the web", "search the web",
    "send email", "send an email", "create a task", "ignore the account", "ignore scope",
)
RELEASE_THRESHOLDS = {
    "max_latency_ms": 1000,
    "max_packet_bytes": 65536,
    "max_input_tokens": 16000,
    "max_output_tokens": 3000,
    "min_citation_correctness": 1.0,
    "min_citation_completeness": 1.0,
    "min_groundedness": 1.0,
    "max_scope_violations": 0,
    "max_privacy_violations": 0,
    "max_audience_violations": 0,
    "min_cache_hit_rate": 0.0,
}


def _loads(value: str | None, fallback: Any) -> Any:
    try:
        return json.loads(value) if value else fallback
    except json.JSONDecodeError:
        return fallback


def _run_row(conn: sqlite3.Connection, run_id: str) -> dict:
    row = conn.execute("SELECT * FROM copilot_runs WHERE id=?", (run_id,)).fetchone()
    if not row or row["archived"]:
        raise HTTPException(404, "copilot run not found")
    return dict(row)


def _validate_scope(conn: sqlite3.Connection, scope_type: str, account_id: str | None,
                    program_id: str | None) -> None:
    if scope_type == "portfolio":
        if account_id is not None or program_id is not None:
            raise HTTPException(422, "portfolio scope cannot carry an account or program id")
        return
    if not account_id:
        raise HTTPException(422, f"{scope_type} scope requires account_id")
    repo.get_row(conn, "accounts", account_id)
    if scope_type == "account":
        if program_id is not None:
            raise HTTPException(422, "account scope cannot carry program_id")
        return
    if scope_type != "program" or not program_id:
        raise HTTPException(422, "scope_type must be program, account, or portfolio")
    program = repo.get_row(conn, "programs", program_id)
    if program["account_id"] != account_id:
        raise HTTPException(422, "copilot program belongs to a different account")


def _configuration(conn: sqlite3.Connection, configuration_id: str | None = None) -> dict:
    if configuration_id:
        row = conn.execute("SELECT * FROM copilot_configurations WHERE id=?", (configuration_id,)).fetchone()
    else:
        row = conn.execute("SELECT * FROM copilot_configurations WHERE status='active'").fetchone()
    if not row:
        raise HTTPException(503, "no active copilot configuration")
    return dict(row)


def _same_scope(left: dict, right: dict) -> bool:
    return all(left.get(key) == right.get(key) for key in ("scope_type", "account_id", "program_id"))


def _latest_review_cursor(conn: sqlite3.Connection, scope_type: str, account_id: str | None,
                          program_id: str | None) -> str | None:
    row = conn.execute(
        "SELECT review_cursor FROM copilot_runs WHERE intent='changes' AND reviewed_at IS NOT NULL "
        "AND scope_type=? AND account_id IS ? AND program_id IS ? AND archived=0 "
        "ORDER BY reviewed_at DESC,created_at DESC,id DESC LIMIT 1",
        (scope_type, account_id, program_id)).fetchone()
    return row["review_cursor"] if row else None


def create_run(conn: sqlite3.Connection, values: dict, *, configuration_id: str | None = None,
               retry_of_run_id: str | None = None, golden_case_id: str | None = None) -> dict:
    query = " ".join((values.get("query_text") or "").split())
    if not query:
        raise HTTPException(422, "question is required")
    if len(query) > 1200:
        raise HTTPException(422, "question is too long; keep it under 1,200 characters")
    scope_type = values["scope_type"]
    account_id, program_id = values.get("account_id"), values.get("program_id")
    _validate_scope(conn, scope_type, account_id, program_id)
    context_run_id = values.get("context_run_id")
    prior = _run_row(conn, context_run_id) if context_run_id else None
    if prior and (prior["status"] != "completed" or not _same_scope(prior, values)):
        raise HTTPException(422, "follow-up context must be a completed run in the exact same scope")
    plan = copilot_model.strict_plan(
        query, scope_type, account_id, program_id, values.get("intent"),
        values.get("time_window_start"), values.get("time_window_end"))
    if plan["intent"] == "changes" and not values.get("time_window_start"):
        values["time_window_start"] = _latest_review_cursor(
            conn, scope_type, account_id, program_id)
        plan["time_window"]["start"] = values.get("time_window_start")
    elif prior:
        values["time_window_start"] = values.get("time_window_start") or prior.get("time_window_start")
        values["time_window_end"] = values.get("time_window_end") or prior.get("time_window_end")
        plan["time_window"] = {"start": values.get("time_window_start"),
                               "end": values.get("time_window_end")}
    config = _configuration(conn, configuration_id)
    supplied_idem = values.get("idempotency_key")
    if supplied_idem:
        existing = conn.execute(
            "SELECT id FROM copilot_runs WHERE idempotency_key=? "
            "AND status IN ('queued','running','completed') AND archived=0", (supplied_idem,)).fetchone()
        if existing:
            return detail(conn, existing["id"])
    ts = now_utc()
    run_id = new_id()
    # Identical questions are not automatically cached: native facts may have changed. A caller
    # supplies a key only for a retry of the same request; otherwise each ask gets a fresh run.
    idem = supplied_idem or f"run:{run_id}"
    with conn:
        conn.execute(
            "INSERT INTO copilot_runs "
            "(id,scope_type,account_id,program_id,query_text,intent,time_window_start,time_window_end,"
            "model_version,prompt_version,retrieval_version,validator_version,backend,configuration_id,"
            "context_run_id,golden_case_id,retry_of_run_id,idempotency_key,created_at,updated_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (run_id, scope_type, account_id, program_id, query, plan["intent"],
             values.get("time_window_start"), values.get("time_window_end"),
             config["model_version"], config["prompt_version"], config["retrieval_version"],
             config["validator_version"], config["backend"], config["id"], context_run_id,
             golden_case_id, retry_of_run_id, idem, ts, ts))
        audit.record(conn, object_type="copilot_run", object_id=run_id, action="create",
                     after={"scope_type": scope_type, "account_id": account_id,
                            "program_id": program_id, "intent": plan["intent"]})
    job = jobs.enqueue(conn, "copilot_query", {"run_id": run_id}, account_id=account_id,
                       max_attempts=2)
    with conn:
        conn.execute("UPDATE copilot_runs SET job_id=?,updated_at=? WHERE id=?",
                     (job["id"], now_utc(), run_id))
    return detail(conn, run_id)


def list_configurations(conn: sqlite3.Connection) -> list[dict]:
    return [dict(row) for row in conn.execute(
        "SELECT * FROM copilot_configurations ORDER BY created_at DESC,id")]


def create_configuration(conn: sqlite3.Connection, values: dict) -> dict:
    ts = now_utc()
    row = {"id": new_id(), "label": values["label"], "backend": "mock",
           "model_version": values["model_version"], "prompt_version": values["prompt_version"],
           "retrieval_version": values["retrieval_version"],
           "validator_version": values["validator_version"], "status": "candidate",
           "created_at": ts, "updated_at": ts}
    with conn:
        conn.execute(f"INSERT INTO copilot_configurations ({','.join(row)}) VALUES ({','.join('?' for _ in row)})",
                     tuple(row.values()))
        audit.record(conn, object_type="copilot_configuration", object_id=row["id"], action="create",
                     after={"label": row["label"], "status": "candidate"})
    return dict(conn.execute("SELECT * FROM copilot_configurations WHERE id=?", (row["id"],)).fetchone())


def replay_configuration(conn: sqlite3.Connection, configuration_id: str,
                         run_ids: list[str]) -> list[dict]:
    config = _configuration(conn, configuration_id)
    if config["status"] not in ("candidate", "passed"):
        raise HTTPException(409, "only a candidate or passed configuration can be replayed")
    replayed = []
    for source_id in dict.fromkeys(run_ids):
        source = _run_row(conn, source_id)
        replayed.append(create_run(conn, {
            "scope_type": source["scope_type"], "account_id": source.get("account_id"),
            "program_id": source.get("program_id"), "query_text": source["query_text"],
            "intent": source["intent"], "time_window_start": source.get("time_window_start"),
            "time_window_end": source.get("time_window_end"),
            "idempotency_key": f"replay:{configuration_id}:{source_id}",
        }, configuration_id=configuration_id, retry_of_run_id=source_id,
           golden_case_id=source.get("golden_case_id")))
    return replayed


def evaluate_configuration(conn: sqlite3.Connection, configuration_id: str,
                           run_ids_by_case: dict[str, str]) -> dict:
    config = _configuration(conn, configuration_id)
    if config["status"] not in ("candidate", "passed"):
        raise HTTPException(409, "only a candidate or passed configuration can be evaluated")
    cases = {case["id"]: case for case in copilot_evaluation.load_golden_cases()}
    if set(run_ids_by_case) != set(cases):
        missing = sorted(set(cases) - set(run_ids_by_case))
        extra = sorted(set(run_ids_by_case) - set(cases))
        raise HTTPException(422, {"message": "evaluation must cover the exact golden set",
                                  "missing": missing, "extra": extra})
    results = {}
    for case_id, run_id in run_ids_by_case.items():
        run = detail(conn, run_id)
        if run["configuration_id"] != configuration_id:
            raise HTTPException(422, f"golden run {case_id} used another configuration")
        results[case_id] = copilot_evaluation.grade_case(cases[case_id], run)
    passed = all(
        grade["retrieval_recall"] == 1.0 and grade["citation_completeness"] == 1.0 and
        grade["citation_correctness"] >= RELEASE_THRESHOLDS["min_citation_correctness"] and
        grade["groundedness"] >= RELEASE_THRESHOLDS["min_groundedness"] and
        grade["answer_fact_completeness"] == 1.0 and grade["gap_completeness"] == 1.0 and
        grade["abstention_correctness"] == 1.0 and grade["scope_violations"] == 0 and
        grade["privacy_violations"] <= RELEASE_THRESHOLDS["max_privacy_violations"] and
        grade["audience_violations"] <= RELEASE_THRESHOLDS["max_audience_violations"] and
        grade["freshness_violations"] == 0 and grade["forbidden_source_violations"] == 0 and
        grade["prohibited_claim_violations"] == 0
        for grade in results.values())
    runs = [detail(conn, run_id) for run_id in run_ids_by_case.values()]
    passed = passed and all(
        (run.get("latency_ms") or 0) <= RELEASE_THRESHOLDS["max_latency_ms"] and
        (run.get("packet_bytes") or 0) <= RELEASE_THRESHOLDS["max_packet_bytes"] and
        (run.get("input_tokens") or 0) <= RELEASE_THRESHOLDS["max_input_tokens"] and
        (run.get("output_tokens") or 0) <= RELEASE_THRESHOLDS["max_output_tokens"]
        for run in runs)
    cache_hit_rate = sum(run["cache_hit"] for run in runs) / len(runs)
    passed = passed and cache_hit_rate >= RELEASE_THRESHOLDS["min_cache_hit_rate"]
    report = {"version": copilot_evaluation.EVALUATION_VERSION, "passed": passed,
              "configuration_id": configuration_id, "results": results,
              "cache_hit_rate": cache_hit_rate, "thresholds": RELEASE_THRESHOLDS}
    ts = now_utc()
    with conn:
        conn.execute("UPDATE copilot_configurations SET status=?,evaluation_version=?,evaluation_json=?,"
                     "evaluated_at=?,updated_at=? WHERE id=?",
                     ("passed" if passed else "candidate", copilot_evaluation.EVALUATION_VERSION,
                      json.dumps(report, sort_keys=True), ts, ts, configuration_id))
    return report


def activate_configuration(conn: sqlite3.Connection, configuration_id: str) -> dict:
    candidate = _configuration(conn, configuration_id)
    if candidate["status"] != "passed":
        raise HTTPException(409, "configuration cannot activate until the full golden set passes")
    active = conn.execute("SELECT * FROM copilot_configurations WHERE status='active'").fetchone()
    ts = now_utc()
    with conn:
        if active:
            conn.execute("UPDATE copilot_configurations SET status='retired',updated_at=? WHERE id=?",
                         (ts, active["id"]))
        conn.execute("UPDATE copilot_configurations SET status='active',previous_config_id=?,"
                     "activated_at=?,updated_at=? WHERE id=?",
                     (active["id"] if active else None, ts, ts, configuration_id))
    return _configuration(conn, configuration_id)


def rollback_configuration(conn: sqlite3.Connection, configuration_id: str) -> dict:
    active = _configuration(conn, configuration_id)
    if active["status"] != "active" or not active.get("previous_config_id"):
        raise HTTPException(409, "active configuration has no rollback target")
    previous = _configuration(conn, active["previous_config_id"])
    ts = now_utc()
    with conn:
        conn.execute("UPDATE copilot_configurations SET status='retired',updated_at=? WHERE id=?",
                     (ts, active["id"]))
        conn.execute("UPDATE copilot_configurations SET status='active',updated_at=? WHERE id=?",
                     (ts, previous["id"]))
    return _configuration(conn, previous["id"])


def _persist_packet(conn: sqlite3.Connection, run_id: str, packet: dict) -> dict[str, str]:
    ids: dict[str, str] = {}
    ts = now_utc()
    for item in packet["items"]:
        source_id = new_id()
        ids[item["packet_id"]] = source_id
        fields_json = json.dumps({**item["fields"], "statement": item["statement"]},
                                 sort_keys=True, default=str)
        content_hash = hashlib.sha256(fields_json.encode()).hexdigest()
        conn.execute(
            "INSERT INTO copilot_run_sources "
            "(id,run_id,packet_id,record_type,record_id,account_id,program_id,record_version,"
            "content_hash,authority,freshness_state,visibility,retrieval_method,retrieval_rank,"
            "inclusion_reason,fields_json,excerpt,created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (source_id, run_id, item["packet_id"], item["record_type"], item["record_id"],
             item.get("account_id"), item.get("program_id"), item["record_version"], content_hash,
             item["authority"], item["freshness_state"], item["visibility"],
             item["retrieval_method"], item["retrieval_rank"], item["inclusion_reason"],
             fields_json, item.get("excerpt"), ts))
    return ids


def _persist_claims(conn: sqlite3.Connection, run_id: str, claims: list[dict],
                    source_ids: dict[str, str]) -> None:
    ts = now_utc()
    for claim in claims:
        claim_id = new_id()
        conn.execute(
            "INSERT INTO copilot_claims "
            "(id,run_id,sequence,kind,claim_text,support_state,validation_result,created_at) "
            "VALUES (?,?,?,?,?,?,?,?)",
            (claim_id, run_id, claim["sequence"], claim["kind"], claim["claim_text"],
             claim["support_state"], "validated", ts))
        for packet_id in claim.get("packet_ids") or []:
            conn.execute(
                "INSERT INTO copilot_claim_sources (id,claim_id,run_source_id,support_note,created_at) "
                "VALUES (?,?,?,?,?)", (new_id(), claim_id, source_ids[packet_id],
                                        "snapshot entails the claim", ts))


def _abstain(conn: sqlite3.Connection, run_id: str, failure_class: str, detail_text: str,
             *, latency_ms: int = 0) -> None:
    ts = now_utc()
    conn.execute(
        "UPDATE copilot_runs SET status='abstained',evidence_state='insufficient',answer_markdown=NULL,"
        "failure_class=?,failure_detail=?,generated_at=?,latency_ms=?,updated_at=? WHERE id=?",
        (failure_class, detail_text, ts, latency_ms, ts, run_id))


@jobs.register("copilot_query")
def execute_job(conn: sqlite3.Connection, payload: dict) -> dict:
    run_id = payload["run_id"]
    started = time.perf_counter()
    run = _run_row(conn, run_id)
    if run["status"] in ("completed", "abstained"):
        return {"run_id": run_id, "status": run["status"], "idempotent": True}
    with conn:
        conn.execute("UPDATE copilot_runs SET status='running',updated_at=? WHERE id=?",
                     (now_utc(), run_id))
    try:
        q = run["query_text"].lower()
        forbidden = next((term for term in FORBIDDEN_REQUESTS if term in q), None)
        if forbidden:
            with conn:
                _abstain(conn, run_id, "unsupported_capability",
                         f"'{forbidden}' is outside the copilot's read-only native-record tools.")
            return {"run_id": run_id, "status": "abstained"}

        packet = copilot_context.build_packet(conn, run)
        output = copilot_model.generate(packet, run)
        errors = copilot_validation.validate_answer(packet, output)
        attempts = 1
        if errors:
            # One same-packet repair is permitted for output-shaped failures. The deterministic
            # mock should never need it, which makes any occurrence observable and testable.
            repaired = copilot_model.generate(packet, run)
            errors = copilot_validation.validate_answer(packet, repaired)
            output = repaired
            attempts = 2
        latency = int((time.perf_counter() - started) * 1000)
        with conn:
            if errors:
                conn.execute("UPDATE copilot_runs SET validator_attempts=?,retrieval_rounds=?,updated_at=? WHERE id=?",
                             (attempts, packet["retrieval_rounds"], now_utc(), run_id))
                _abstain(conn, run_id, "validation_failure", "; ".join(errors), latency_ms=latency)
                return {"run_id": run_id, "status": "abstained", "errors": errors}
            if output.get("abstain"):
                conn.execute(
                    "UPDATE copilot_runs SET gaps_json=?,resolved_entities_json=?,readers_json=?,excluded_json=?,packet_hash=?,"
                    "packet_bytes=?,validator_attempts=?,retrieval_rounds=?,updated_at=? WHERE id=?",
                    (json.dumps(output["gaps"]), json.dumps(packet.get("resolved_entities", [])),
                     json.dumps(packet["readers"]),
                     json.dumps(packet["excluded"]), packet["packet_hash"], packet["packet_bytes"],
                     attempts, packet["retrieval_rounds"], now_utc(), run_id))
                _abstain(conn, run_id, "insufficient_evidence", output["diagnostic"], latency_ms=latency)
                return {"run_id": run_id, "status": "abstained"}
            source_ids = _persist_packet(conn, run_id, packet)
            _persist_claims(conn, run_id, output["claims"], source_ids)
            ts = now_utc()
            conn.execute(
                "UPDATE copilot_runs SET status='completed',evidence_state=?,answer_markdown=?,"
                "gaps_json=?,resolved_entities_json=?,readers_json=?,excluded_json=?,packet_hash=?,packet_bytes=?,input_tokens=?,"
                "output_tokens=?,validator_attempts=?,retrieval_rounds=?,latency_ms=?,generated_at=?,updated_at=? "
                "WHERE id=?",
                (output["evidence_state"], output["answer_markdown"], json.dumps(output["gaps"]),
                 json.dumps((packet.get("resolved_entities") or []) + (packet.get("ambiguities") or [])),
                 json.dumps(packet["readers"]), json.dumps(packet["excluded"]), packet["packet_hash"],
                 packet["packet_bytes"], output["estimated_input_tokens"],
                 output["estimated_output_tokens"], attempts, packet["retrieval_rounds"], latency,
                 ts, ts, run_id))
        return {"run_id": run_id, "status": "completed"}
    except Exception as exc:
        with conn:
            conn.execute(
                "UPDATE copilot_runs SET status='failed',failure_class='execution_failure',"
                "failure_detail=?,updated_at=? WHERE id=?", (str(exc)[:500], now_utc(), run_id))
        raise


def _source_archived(conn: sqlite3.Connection, source: dict) -> bool | None:
    definition = copilot_context._RECORDS.get(source["record_type"])
    if not definition:
        return None
    table = definition[0]
    row = conn.execute(f"SELECT archived FROM {table} WHERE id=?", (source["record_id"],)).fetchone()
    return True if not row else bool(row["archived"])


def detail(conn: sqlite3.Connection, run_id: str) -> dict:
    run = _run_row(conn, run_id)
    sources = [dict(row) for row in conn.execute(
        "SELECT * FROM copilot_run_sources WHERE run_id=? ORDER BY retrieval_rank,packet_id", (run_id,))]
    for source in sources:
        source["fields"] = _loads(source.pop("fields_json"), {})
        source["archived_after_answer"] = _source_archived(conn, source)
    claims = [dict(row) for row in conn.execute(
        "SELECT * FROM copilot_claims WHERE run_id=? ORDER BY sequence", (run_id,))]
    support = conn.execute(
        "SELECT cs.claim_id,s.id source_id,s.packet_id FROM copilot_claim_sources cs "
        "JOIN copilot_run_sources s ON s.id=cs.run_source_id JOIN copilot_claims c ON c.id=cs.claim_id "
        "WHERE c.run_id=? ORDER BY c.sequence,s.packet_id", (run_id,)).fetchall()
    by_claim: dict[str, list[dict]] = {}
    for row in support:
        by_claim.setdefault(row["claim_id"], []).append({"source_id": row["source_id"],
                                                          "packet_id": row["packet_id"]})
    for claim in claims:
        claim["sources"] = by_claim.get(claim["id"], [])
    run["gaps"] = _loads(run.pop("gaps_json"), [])
    run["resolved_entities"] = _loads(run.pop("resolved_entities_json"), [])
    run["readers"] = _loads(run.pop("readers_json"), [])
    run["excluded"] = _loads(run.pop("excluded_json"), [])
    run["sources"] = sources
    run["claims"] = claims
    return run


def list_runs(conn: sqlite3.Connection, *, scope_type: str | None = None,
              account_id: str | None = None, program_id: str | None = None,
              limit: int = 50) -> list[dict]:
    where = ["archived=0"]
    params: list[Any] = []
    for column, value in (("scope_type", scope_type), ("account_id", account_id),
                          ("program_id", program_id)):
        if value is not None:
            where.append(f"{column}=?")
            params.append(value)
    params.append(max(1, min(limit, 100)))
    return [dict(row) for row in conn.execute(
        f"SELECT * FROM copilot_runs WHERE {' AND '.join(where)} ORDER BY created_at DESC LIMIT ?",
        tuple(params))]


def archive_run(conn: sqlite3.Connection, run_id: str) -> None:
    repo.archive(conn, "copilot_runs", run_id, object_type="copilot_run")


def add_feedback(conn: sqlite3.Connection, run_id: str, values: dict) -> dict:
    _run_row(conn, run_id)
    claim_id = values.get("claim_id")
    if claim_id and not conn.execute(
            "SELECT 1 FROM copilot_claims WHERE id=? AND run_id=?", (claim_id, run_id)).fetchone():
        raise HTTPException(422, "feedback claim belongs to a different run")
    run_source_id = values.get("run_source_id")
    if run_source_id and not conn.execute(
            "SELECT 1 FROM copilot_run_sources WHERE id=? AND run_id=?",
            (run_source_id, run_id)).fetchone():
        raise HTTPException(422, "feedback source belongs to a different run")
    row = {"id": new_id(), "run_id": run_id, "claim_id": claim_id,
           "run_source_id": run_source_id,
           "issue_kind": values["issue_kind"], "note": values.get("note"),
           "actor": values.get("actor") or audit.DEFAULT_ACTOR, "created_at": now_utc()}
    with conn:
        conn.execute(f"INSERT INTO copilot_feedback ({','.join(row)}) VALUES ({','.join('?' for _ in row)})",
                     tuple(row.values()))
        audit.record(conn, object_type="copilot_feedback", object_id=row["id"], action="create",
                     after={"run_id": run_id, "claim_id": claim_id, "issue_kind": row["issue_kind"]})
    return row


def list_feedback(conn: sqlite3.Connection, *, pending_only: bool = False) -> list[dict]:
    where = "WHERE fr.id IS NULL" if pending_only else ""
    rows = conn.execute(
        "SELECT f.*,r.query_text,r.account_id,r.program_id,c.claim_text,"
        "s.record_type source_record_type,s.record_id source_record_id,s.packet_id source_packet_id,"
        "fr.id review_id,fr.disposition,fr.resolution_note,fr.reviewed_by,fr.reviewed_at "
        "FROM copilot_feedback f JOIN copilot_runs r ON r.id=f.run_id "
        "LEFT JOIN copilot_claims c ON c.id=f.claim_id "
        "LEFT JOIN copilot_run_sources s ON s.id=f.run_source_id "
        "LEFT JOIN copilot_feedback_reviews fr ON fr.feedback_id=f.id "
        f"{where} ORDER BY f.created_at DESC").fetchall()
    return [dict(row) for row in rows]


def review_feedback(conn: sqlite3.Connection, feedback_id: str, values: dict) -> dict:
    feedback = conn.execute("SELECT * FROM copilot_feedback WHERE id=?", (feedback_id,)).fetchone()
    if not feedback:
        raise HTTPException(404, "copilot feedback not found")
    row = {"id": new_id(), "feedback_id": feedback_id, "disposition": values["disposition"],
           "resolution_note": values["resolution_note"], "reviewed_by": values["reviewed_by"],
           "reviewed_at": now_utc()}
    try:
        with conn:
            conn.execute(f"INSERT INTO copilot_feedback_reviews ({','.join(row)}) "
                         f"VALUES ({','.join('?' for _ in row)})", tuple(row.values()))
            audit.record(conn, object_type="copilot_feedback_review", object_id=row["id"],
                         action="create", after={"feedback_id": feedback_id,
                                                  "disposition": row["disposition"]})
    except sqlite3.IntegrityError as exc:
        raise HTTPException(409, "feedback has already been reviewed") from exc
    return row


def list_aliases(conn: sqlite3.Connection, account_id: str | None = None) -> list[dict]:
    if account_id:
        rows = conn.execute("SELECT * FROM copilot_entity_aliases WHERE archived=0 "
                            "AND (account_id=? OR account_id IS NULL) ORDER BY alias",
                            (account_id,)).fetchall()
    else:
        rows = conn.execute("SELECT * FROM copilot_entity_aliases WHERE archived=0 ORDER BY alias").fetchall()
    return [dict(row) for row in rows]


def create_alias(conn: sqlite3.Connection, values: dict) -> dict:
    definition = copilot_context._RECORDS[values["record_type"]]
    target = conn.execute(f"SELECT * FROM {definition[0]} WHERE id=? AND archived=0",
                          (values["record_id"],)).fetchone()
    if not target:
        raise HTTPException(404, "alias target not found")
    target = dict(target)
    target_account, _ = copilot_context._row_account(conn, values["record_type"], target)
    if values.get("account_id") != target_account:
        raise HTTPException(422, "alias account must match its native record")
    alias = " ".join(values["alias"].split())
    if not alias:
        raise HTTPException(422, "alias cannot be blank")
    row = {"id": new_id(), "account_id": target_account, "record_type": values["record_type"],
           "record_id": values["record_id"], "alias": alias,
           "created_by": values["created_by"], "created_at": now_utc()}
    try:
        with conn:
            conn.execute(f"INSERT INTO copilot_entity_aliases ({','.join(row)}) VALUES ({','.join('?' for _ in row)})",
                         tuple(row.values()))
    except sqlite3.IntegrityError as exc:
        raise HTTPException(409, "that alias already exists or its target is outside scope") from exc
    return row


def mark_reviewed(conn: sqlite3.Connection, run_id: str) -> dict:
    run = _run_row(conn, run_id)
    if run["intent"] != "changes" or run["status"] != "completed":
        raise HTTPException(409, "only a completed change brief can advance its review cursor")
    ts = now_utc()
    with conn:
        conn.execute("UPDATE copilot_runs SET reviewed_at=?,review_cursor=?,updated_at=? WHERE id=?",
                     (ts, run["generated_at"], ts, run_id))
        audit.record(conn, object_type="copilot_run", object_id=run_id, action="update",
                     before={"reviewed_at": run.get("reviewed_at")},
                     after={"reviewed_at": ts, "review_cursor": run["generated_at"]})
    return detail(conn, run_id)


def list_styles(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute(
        "SELECT * FROM writing_style_profiles WHERE archived=0 ORDER BY audience,is_active DESC,version DESC").fetchall()
    out = []
    for row in rows:
        item = dict(row)
        item["rules"] = _loads(item.pop("rules_json"), {})
        out.append(item)
    return out


def create_style(conn: sqlite3.Connection, values: dict) -> dict:
    audience = values["audience"]
    active = conn.execute(
        "SELECT * FROM writing_style_profiles WHERE audience=? AND is_active=1 AND archived=0",
        (audience,)).fetchone()
    if active and not values.get("supersedes_id"):
        raise HTTPException(409, "an active style exists; supersede it instead of overwriting")
    if values.get("supersedes_id"):
        prior = repo.get_row(conn, "writing_style_profiles", values["supersedes_id"])
        if prior["audience"] != audience or not prior["is_active"]:
            raise HTTPException(422, "style can supersede only the active profile for its audience")
        version = prior["version"] + 1
    else:
        version = 1
    ts = now_utc()
    row = {"id": new_id(), "name": values["name"], "audience": audience, "version": version,
           "rules_json": json.dumps(values.get("rules") or {}, sort_keys=True),
           "sample_text": values.get("sample_text"), "effective_on": values["effective_on"],
           "author": values["author"], "supersedes_id": values.get("supersedes_id"),
           "is_active": 1, "created_at": ts, "updated_at": ts}
    with conn:
        if values.get("supersedes_id"):
            conn.execute("UPDATE writing_style_profiles SET is_active=0,updated_at=? WHERE id=?",
                         (ts, values["supersedes_id"]))
        conn.execute(f"INSERT INTO writing_style_profiles ({','.join(row)}) VALUES ({','.join('?' for _ in row)})",
                     tuple(row.values()))
        audit.record(conn, object_type="writing_style_profile", object_id=row["id"], action="create",
                     after={"audience": audience, "version": version,
                            "supersedes_id": values.get("supersedes_id")})
    return next(style for style in list_styles(conn) if style["id"] == row["id"])


def preview_internal_note(conn: sqlite3.Connection, run_id: str, title: str) -> dict:
    run = detail(conn, run_id)
    if run["status"] != "completed" or run["evidence_state"] == "insufficient":
        raise HTTPException(409, "only a completed, supported answer can seed a draft")
    profile = conn.execute(
        "SELECT * FROM writing_style_profiles WHERE audience='internal' AND is_active=1 AND archived=0"
    ).fetchone()
    rules = _loads(profile["rules_json"], {}) if profile else {}
    lint = copilot_validation.lint_style(run["answer_markdown"], rules)
    if lint:
        raise HTTPException(422, {"message": "draft failed the active style contract", "errors": lint})
    return {"kind": "copilot_internal_note", "title": title, "account_id": run.get("account_id"),
            "account_name": None, "program_id": run.get("program_id"), "audience": "internal",
            "markdown": run["answer_markdown"], "source_run_id": run_id,
            "source_job_id": run.get("job_id"),
            "writing_style_profile_id": profile["id"] if profile else None,
            "writing_style_profile_version": profile["version"] if profile else None,
            "stamp": {"generated_at": now_utc(), "data_current_through": run["generated_at"][:10],
                      "missing_or_stale_sources": run["gaps"]}}


def draft_internal_note(conn: sqlite3.Connection, run_id: str, title: str) -> dict:
    preview = preview_internal_note(conn, run_id, title)
    with conn:
        doc = generators.save_draft(
            conn, preview, source_job_id=preview.get("source_job_id"),
            program_id=preview.get("program_id"), title=title,
            writing_style_profile_id=preview.get("writing_style_profile_id"))
        conn.execute(
            "INSERT INTO generated_document_sources "
            "(id,document_id,record_type,record_id,record_version,inclusion_reason,visibility_class,created_at) "
            "VALUES (?,?,?,?,?,'copilot answer passed claim validation','internal',?)",
            (new_id(), doc["id"], "copilot_run", run_id,
             detail(conn, run_id)["validator_version"], now_utc()))
        audit.record(conn, object_type="generated_document", object_id=doc["id"], action="update",
                     after={"kind": doc["kind"], "copilot_run_id": run_id})
    return dict(conn.execute("SELECT * FROM generated_documents WHERE id=?", (doc["id"],)).fetchone())


def health(conn: sqlite3.Connection) -> dict:
    counts = {row["status"]: row["n"] for row in conn.execute(
        "SELECT status,COUNT(*) n FROM copilot_runs WHERE archived=0 GROUP BY status")}
    recent = [dict(row) for row in conn.execute(
        "SELECT status,evidence_state,latency_ms,packet_bytes,input_tokens,output_tokens,"
        "validator_attempts,retrieval_rounds,cache_hit FROM copilot_runs WHERE archived=0 "
        "ORDER BY created_at DESC LIMIT 50")]
    config_error = None
    try:
        config = copilot_model.backend_state()
    except RuntimeError as exc:
        config, config_error = {"mode": "blocked", "network": False}, str(exc)
    active = conn.execute("SELECT * FROM copilot_configurations WHERE status='active'").fetchone()
    return {"configuration": config, "configuration_error": config_error,
            "active_configuration": dict(active) if active else None,
            "counts": counts, "recent": recent, "thresholds": RELEASE_THRESHOLDS,
            "evaluation": copilot_evaluation.manifest(),
            "quality": {"composite_score": None,
                        "note": "Groundedness, citations, scope, privacy, latency, and cost stay separate."}}
