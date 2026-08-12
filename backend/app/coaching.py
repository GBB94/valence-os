"""Stage 18 — private personal Call Coach domain and deterministic local backend."""
from __future__ import annotations

import base64
import hashlib
import json
import re
import sqlite3
from datetime import date
from typing import Any

from fastapi import HTTPException

from . import audit, coaching_contract, coaching_rubrics, interaction_ops, jobs, readiness, repo
from .db import new_id, now_utc
from .schemas import InteractionCreate

PROVIDER = "call_coach"
CREATED_BY = "operator"
ALLOWED_SOURCE_KINDS = frozenset({
    "paste", "notes", "script", "txt", "md", "vtt", "srt", "practice_transcript",
})
ALLOWED_RESPONSES = frozenset({"useful", "inaccurate", "dismissed"})

PILLAR_HINTS = {
    "stakeholder_breadth": ("stakeholder", "who else", "decision maker", "influence", "committee"),
    "champion_continuity": ("champion", "advocate", "backup", "continuity", "without you"),
    "executive_sponsorship": ("executive", "sponsor", "c-suite", "vp ", "leadership"),
    "quantified_value": ("metric", "measure", "baseline", "outcome", "percent", "%", "value"),
    "budget_owner": ("budget", "funding", "economic buyer", "procurement", "authority"),
    "active_expansion_plan": ("expand", "expansion", "renewal", "next team", "next region"),
}
CALL_RELEVANCE = {
    "account_kickoff": set(PILLAR_HINTS) - {"active_expansion_plan"},
    "deployment_session": {"stakeholder_breadth", "champion_continuity", "executive_sponsorship",
                           "quantified_value"},
    "stakeholder_discovery": {"stakeholder_breadth", "champion_continuity", "executive_sponsorship"},
    "executive_qbr": set(PILLAR_HINTS),
    "renewal_expansion": set(PILLAR_HINTS),
    "risk_recovery": {"champion_continuity", "executive_sponsorship", "quantified_value"},
    "internal_alignment": {"stakeholder_breadth", "executive_sponsorship", "budget_owner"},
    "interview_networking": set(),
    "other": set(),
}


def config() -> dict:
    return {
        "contract_version": coaching_contract.CONTRACT_VERSION,
        "backend": "deterministic_local",
        "model_version": coaching_contract.MODEL_VERSION,
        "real_model_enabled": False,
        "accepted_source_kinds": sorted(ALLOWED_SOURCE_KINDS),
        "max_source_bytes": coaching_contract.MAX_SOURCE_BYTES,
        "call_types": coaching_rubrics.listing(),
        "skills": [{"key": key, "label": value}
                   for key, value in coaching_rubrics.UNIVERSAL_SKILLS.items()],
        "gates": {"model": "closed", "audio": "closed", "live": "closed", "sharing": "closed"},
    }


def _text_from_input(*, text: str | None, content_b64: str | None) -> tuple[str, int]:
    if bool(text) == bool(content_b64):
        raise HTTPException(422, "provide exactly one of text or content_b64")
    if content_b64:
        try:
            raw = base64.b64decode(content_b64, validate=True)
            source = raw.decode("utf-8")
        except (ValueError, UnicodeDecodeError) as exc:
            raise HTTPException(422, "the coaching source must be valid base64 UTF-8 text") from exc
    else:
        source = text or ""
        raw = source.encode("utf-8")
    if not source.strip():
        raise HTTPException(422, "the coaching source is empty")
    if len(raw) > coaching_contract.MAX_SOURCE_BYTES:
        raise HTTPException(413, "the coaching source exceeds the 1 MB text limit")
    return source.replace("\x00", ""), len(raw)


def _validate_date(value: str | None) -> str | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value).isoformat()
    except ValueError as exc:
        raise HTTPException(422, "call_date must be a real ISO date") from exc


def _validate_scope(conn: sqlite3.Connection, *, account_id: str | None,
                    program_id: str | None, interaction_id: str | None) -> tuple[str | None, str | None]:
    if interaction_id:
        interaction = repo.get_row(conn, "interactions", interaction_id)
        if account_id and interaction["account_id"] != account_id:
            raise HTTPException(422, "interaction_id belongs to a different account")
        account_id = interaction["account_id"]
        if program_id and interaction["program_id"] and interaction["program_id"] != program_id:
            raise HTTPException(422, "interaction_id belongs to a different program")
        program_id = program_id or interaction["program_id"]
    if account_id:
        repo.get_row(conn, "accounts", account_id)
    if program_id:
        if not account_id:
            raise HTTPException(422, "program_id requires account_id")
        program = repo.get_row(conn, "programs", program_id)
        if program["account_id"] != account_id:
            raise HTTPException(422, "program_id belongs to a different account")
    return account_id, program_id


def create_session(conn: sqlite3.Connection, body: dict) -> dict:
    mode = body.get("mode") or "review"
    if mode not in {"review", "rehearsal"}:
        raise HTTPException(422, "mode must be review or rehearsal")
    source_kind = body.get("source_kind") or ("practice_transcript" if mode == "rehearsal" else "paste")
    if source_kind not in ALLOWED_SOURCE_KINDS:
        raise HTTPException(422, "that source kind is not accepted; use text, TXT, MD, VTT, or SRT")
    filename = (body.get("filename") or "").strip() or None
    if filename and not filename.lower().endswith((".txt", ".md", ".vtt", ".srt")):
        raise HTTPException(415, "audio, video, PDF, and office files are not accepted; provide a transcript")
    source, byte_length = _text_from_input(text=body.get("text"), content_b64=body.get("content_b64"))
    content_hash = hashlib.sha256(source.encode("utf-8")).hexdigest()
    account_id, program_id = _validate_scope(
        conn, account_id=body.get("account_id"), program_id=body.get("program_id"),
        interaction_id=body.get("interaction_id"))
    call_type = body.get("call_type") or "other"
    if call_type not in coaching_rubrics.RUBRICS:
        raise HTTPException(422, "unknown call_type")
    intended_outcome = (body.get("intended_outcome") or "").strip()
    if not intended_outcome:
        raise HTTPException(422, "intended_outcome is required")

    parent_id = body.get("parent_session_id")
    origin_id = body.get("origin_observation_id")
    if mode == "review" and (parent_id or origin_id):
        raise HTTPException(422, "review sessions cannot carry rehearsal lineage")
    if parent_id:
        repo.get_row(conn, "coaching_sessions", parent_id)
    if origin_id:
        origin = conn.execute(
            "SELECT o.id,r.session_id FROM coaching_observations o "
            "JOIN coaching_runs r ON r.id=o.run_id WHERE o.id=?", (origin_id,)).fetchone()
        if not origin:
            raise HTTPException(404, "origin coaching observation not found")
        if parent_id and origin["session_id"] != parent_id:
            raise HTTPException(422, "origin observation does not belong to parent session")

    speakers = coaching_contract.speaker_keys(source)
    speaker = (body.get("coached_speaker_key") or "").strip() or None
    speaker_status = body.get("speaker_status") or ("confirmed_by_operator" if speaker else "unknown")
    if speaker_status == "confirmed_by_operator" and (not speaker or speaker not in speakers):
        raise HTTPException(422, "choose a speaker label that appears in the source")
    if speaker_status not in {"confirmed_by_operator", "unknown", "not_applicable"}:
        raise HTTPException(422, "unknown speaker_status")
    if mode == "review" and speaker_status == "not_applicable":
        speaker_status = "unknown"

    session_id = new_id()
    source_id = new_id()
    ts = now_utc()
    title = (body.get("title") or ("Practice" if mode == "rehearsal" else "Call review")).strip()
    values = {
        "id": session_id, "mode": mode, "parent_session_id": parent_id,
        "origin_observation_id": origin_id, "account_id": account_id, "program_id": program_id,
        "interaction_id": body.get("interaction_id"), "title": title[:240], "call_type": call_type,
        "call_date": _validate_date(body.get("call_date")), "intended_outcome": intended_outcome,
        "coaching_focus": (body.get("coaching_focus") or "").strip() or None,
        "coached_speaker_key": speaker if speaker_status == "confirmed_by_operator" else None,
        "speaker_status": speaker_status,
        "reflection_worked": (body.get("reflection_worked") or "").strip() or None,
        "reflection_difficult": (body.get("reflection_difficult") or "").strip() or None,
        "reflection_outcome": (body.get("reflection_outcome") or "").strip() or None,
        "reflection_change": (body.get("reflection_change") or "").strip() or None,
        "created_by": CREATED_BY, "created_at": ts, "updated_at": ts,
    }
    with conn:
        conn.execute(
            f"INSERT INTO coaching_sessions ({', '.join(values)}) "
            f"VALUES ({', '.join('?' for _ in values)})", tuple(values.values()))
        conn.execute(
            "INSERT INTO coaching_sources(id,session_id,source_kind,filename,byte_length,content_hash,"
            "snapshot_text,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?)",
            (source_id, session_id, source_kind, filename, byte_length, content_hash, source, ts, ts))
        audit.record(conn, object_type="coaching_session", object_id=session_id, action="create",
                     after={"mode": mode, "account_id": account_id, "source_kind": source_kind})
    run = enqueue_run(conn, session_id)
    result = get_session(conn, session_id)
    result["receipt"] = {"job_id": run["job_id"], "run_id": run["id"],
                         "speakers": speakers, "source_kind": source_kind}
    return result


def _account_context(conn: sqlite3.Connection, session: dict) -> dict | None:
    account_id = session.get("account_id")
    if not account_id:
        return None
    account = repo.get_row(conn, "accounts", account_id)
    program = repo.get_row(conn, "programs", session["program_id"]) if session.get("program_id") else None
    recent = [dict(row) for row in conn.execute(
        "SELECT id,occurred_on,type,summary,meaningful_touch FROM interactions "
        "WHERE account_id=? AND (? IS NULL OR program_id=?) "
        "ORDER BY occurred_on DESC,created_at DESC LIMIT 5",
        (account_id, session.get("program_id"), session.get("program_id"))).fetchall()]
    readiness_view = readiness.evaluate(conn, account_id, session.get("program_id"))
    return {
        "account": {"id": account["id"], "name": account["name"]},
        "program": ({"id": program["id"], "name": program["name"], "phase": program["phase"]}
                    if program else None),
        "recent_interactions": recent,
        "readiness": {"as_of": readiness_view["as_of"], "coverage": readiness_view["coverage"],
                      "pillars": readiness_view["pillars"], "programs": readiness_view["programs"]},
        "omitted": ["draft proposals", "untriaged capture", "private Nadia data", "telemetry",
                    "other accounts"],
    }


def enqueue_run(conn: sqlite3.Connection, session_id: str) -> dict:
    session = repo.get_row(conn, "coaching_sessions", session_id)
    if session["archived"]:
        raise HTTPException(409, "archived coaching sessions cannot be analyzed")
    source = conn.execute("SELECT * FROM coaching_sources WHERE session_id=?", (session_id,)).fetchone()
    if not source or source["snapshot_text"] is None:
        raise HTTPException(409, "the retained source was deleted; this session cannot be reanalyzed")
    rubric = coaching_rubrics.get(session["call_type"])
    run_id = new_id()
    ts = now_utc()
    context = _account_context(conn, session)
    with conn:
        conn.execute(
            "INSERT INTO coaching_runs(id,session_id,source_content_hash,contract_version,rubric_key,"
            "rubric_version,extractor_backend,model_version,prompt_version,status,"
            "account_context_snapshot_json,created_at,updated_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,'queued',?,?,?)",
            (run_id, session_id, source["content_hash"], coaching_contract.CONTRACT_VERSION,
             session["call_type"], rubric["version"], "deterministic_local",
             coaching_contract.MODEL_VERSION, coaching_contract.PROMPT_VERSION,
             json.dumps(context) if context else None, ts, ts))
    job = jobs.enqueue(conn, "coaching_analyze", {"run_id": run_id},
                       account_id=session.get("account_id"), max_attempts=1)
    with conn:
        conn.execute("UPDATE coaching_runs SET job_id=?,updated_at=? WHERE id=?",
                     (job["id"], now_utc(), run_id))
    return dict(conn.execute("SELECT * FROM coaching_runs WHERE id=?", (run_id,)).fetchone())


def _turns_for_session(session: dict, source: str) -> tuple[list[dict], dict]:
    turns = coaching_contract.transcript_turns(source)
    if session["speaker_status"] == "confirmed_by_operator":
        selected = [turn for turn in turns if turn["speaker"] == session["coached_speaker_key"]]
        return selected, {"status": "complete", "mode": "speaker_confirmed", "turns_read": len(turns),
                          "coached_turns": len(selected), "whole_source_read": True}
    # Restricted mode evaluates the language on the page without saying who said it.
    anonymous = [{**turn, "speaker": None} for turn in turns]
    return anonymous, {"status": "restricted", "mode": "content_only", "turns_read": len(turns),
                       "coached_turns": None, "whole_source_read": True,
                       "reason": "No speaker was confirmed; no participant is evaluated."}


def _observation(turn: dict, *, kind: str, skill: str, headline: str, situation: str,
                 behavior: str, impact: str, alternative: str, priority: bool = False) -> dict:
    return {
        "kind": kind, "skill_key": skill, "headline": headline, "situation": situation,
        "behavior": behavior, "impact_type": "inferred", "impact_text": impact,
        "alternative": alternative, "source_span": turn["text"],
        "source_start": turn["start"], "source_end": turn["end"],
        "source_timestamp": turn.get("timestamp"), "source_speaker_key": turn.get("speaker"),
        "is_top_priority": priority,
    }


def _analyze_review(session: dict, source: str) -> dict:
    turns, coverage = _turns_for_session(session, source)
    if not turns:
        return {"summary": "There was not enough attributable text to coach safely.",
                "observations": [], "coverage": {**coverage, "status": "insufficient"}}
    lower = [(turn["text"].lower(), turn) for turn in turns]
    observations: list[dict] = []

    synthesis = next((turn for text, turn in lower if any(phrase in text for phrase in
        ("what i'm hearing", "what i am hearing", "let me summarize", "so you're saying",
         "it sounds like", "have i got that right"))), None)
    purposeful_question = next((turn for text, turn in lower if "?" in turn["text"] and
        any(word in text for word in ("what", "how", "why", "which", "who", "where"))), None)
    explicit_close = next((turn for text, turn in reversed(lower) if any(word in text for word in
        ("next step", "by friday", "by monday", "owner", "follow up", "send you", "i'll", "i will"))), None)
    acknowledgement = next((turn for text, turn in lower if any(phrase in text for phrase in
        ("i hear", "that makes sense", "i understand", "thank you for being", "i appreciate"))), None)

    if synthesis:
        observations.append(_observation(
            synthesis, kind="strength", skill="synthesis", headline="You made the thinking visible",
            situation="The conversation needed a shared reading of what had been said.",
            behavior="You offered a synthesis that the other person could confirm or correct.",
            impact="That kind of checkpoint can reduce parallel interpretations before a decision.",
            alternative="Repeat the synthesis and end with a direct accuracy check."))
    elif purposeful_question:
        observations.append(_observation(
            purposeful_question, kind="strength", skill="curiosity_questions",
            headline="You opened space for a substantive answer",
            situation="A useful question was available instead of another assertion.",
            behavior="You used an open question tied to the topic at hand.",
            impact="An open question can surface constraints and reasoning that a closed check misses.",
            alternative="Keep the question, then follow the answer before moving to the next topic."))
    elif acknowledgement:
        observations.append(_observation(
            acknowledgement, kind="strength", skill="trust_safety",
            headline="You acknowledged the concern before moving on",
            situation="The moment carried tension or risk.", behavior="You named that you heard it.",
            impact="Acknowledgement can make it safer to add detail instead of defending a position.",
            alternative="Keep the acknowledgement and ask what part matters most."))

    if explicit_close:
        observations.append(_observation(
            explicit_close, kind="strength", skill="ownership_next_steps",
            headline="You moved the conversation toward follow-through",
            situation="The call needed to turn discussion into action.",
            behavior="You named a next action or timing cue.",
            impact="Explicit follow-through reduces the chance that agreement dissolves after the call.",
            alternative="Preserve the close and make owner, deliverable, and date explicit together."))

    long_turn = next((turn for turn in turns if len(turn["text"]) > 420), None)
    stacked = next((turn for turn in turns if turn["text"].count("?") > 1), None)
    solution_first = next((turn for index, (text, turn) in enumerate(lower[:max(1, len(lower)//2)])
                           if any(phrase in text for phrase in ("we should", "what we can do",
                                                                "here's what", "the solution is"))
                           and not any("?" in prior[1]["text"] for prior in lower[:index])), None)
    if stacked:
        observations.append(_observation(
            stacked, kind="opportunity", skill="curiosity_questions",
            headline="Ask one question and stay with the answer",
            situation="Several questions arrived in the same turn.",
            behavior="The turn bundled multiple possible directions.",
            impact="A bundled question lets the respondent choose the easiest part and leave the useful one unanswered.",
            alternative="Ask the highest-leverage question alone, pause, then build the next question from the answer.",
            priority=True))
    elif solution_first:
        observations.append(_observation(
            solution_first, kind="opportunity", skill="listening_follow_up",
            headline="Stay in discovery one turn longer",
            situation="A solution appeared before the source shows a clarifying question.",
            behavior="You moved quickly from the issue to a proposed answer.",
            impact="Early solutioning can narrow the problem before the constraint behind it is understood.",
            alternative="Reflect the concern, then ask what makes it difficult before offering a path.",
            priority=True))
    elif long_turn:
        observations.append(_observation(
            long_turn, kind="opportunity", skill="clarity_concision",
            headline="Make the intervention easier to answer",
            situation="One contribution carried several ideas at once.",
            behavior="The turn stayed with your explanation for an extended passage.",
            impact="Multiple ideas in one turn can hide which point needs a response.",
            alternative="Lead with the one decision or question, stop, and add context only if it is needed.",
            priority=True))
    elif not explicit_close:
        last = turns[-1]
        observations.append(_observation(
            last, kind="opportunity", skill="ownership_next_steps",
            headline="Close with one explicit ownership sentence",
            situation="The retained source reaches its end without an explicit owner-and-date close.",
            behavior="The final coached turn did not state owner, deliverable, and timing together.",
            impact="A conversational ending can leave each person with a different version of what happens next.",
            alternative="End with: ‘I own X by Tuesday; you own Y by Friday—have I got that right?’",
            priority=True))
    else:
        pivot = turns[-1]
        observations.append(_observation(
            pivot, kind="opportunity", skill="synthesis",
            headline="Test the shared understanding before leaving the topic",
            situation="The call had enough substance to benefit from a final accuracy check.",
            behavior="The coached turn advanced the conversation without testing a synthesis.",
            impact="An untested interpretation can survive the call as apparent agreement.",
            alternative="State the decision, constraint, and open question in one sentence, then ask what is wrong or missing.",
            priority=True))

    # Two by two is a ceiling, not a quota. Keep stable source order within each kind while showing
    # the one opportunity first in the UI through the explicit priority flag.
    strengths = [item for item in observations if item["kind"] == "strength"][:2]
    opportunities = [item for item in observations if item["kind"] == "opportunity"][:2]
    return {
        "summary": "The call created useful movement; the clearest next gain is a more explicit, testable intervention.",
        "observations": strengths + opportunities, "coverage": coverage,
    }


def _analyze_practice(session: dict, source: str) -> dict:
    turns = coaching_contract.transcript_turns(source)
    turn = turns[-1] if turns else {"text": source.strip(), "start": source.find(source.strip()),
                                    "end": len(source), "speaker": None, "timestamp": None}
    text = turn["text"].lower()
    skill = session.get("coaching_focus") or "clarity_concision"
    patterns = {
        "ownership_next_steps": (" by ", "i will", "i'll", "you will", "owner"),
        "synthesis": ("what i'm hearing", "it sounds", "have i got", "in other words"),
        "curiosity_questions": ("?", "what ", "how ", "which "),
        "listening_follow_up": ("tell me more", "what makes", "when you say", "help me understand"),
        "constructive_challenge": ("tension", "tradeoff", "concern", "challenge"),
        "decision_clarity": ("decision", "constraint", "open question", "agree"),
        "value_measurement": ("measure", "metric", "baseline", "outcome"),
        "commercial_clarity": ("budget", "authority", "timing", "procurement"),
    }
    expected = patterns.get(skill, ("?", "because", "next"))
    hits = sum(token in text for token in expected)
    if len(turn["text"].strip()) < 12:
        status = "unable_to_assess"
        adjustment = "Try a complete sentence that performs the target behavior."
    elif hits >= 2:
        status = "observed"
        adjustment = "Keep the structure and make the final check even more explicit."
    elif hits == 1:
        status = "partial"
        adjustment = "Make the target behavior unmistakable instead of implied."
    else:
        status = "not_observed"
        adjustment = f"Rewrite the line so it visibly practices {skill.replace('_', ' ')}."
    return {
        "summary": "This attempt is evaluated only against the selected practice behavior.",
        "observations": [],
        "coverage": {"status": "complete" if status != "unable_to_assess" else "insufficient",
                     "mode": "practice", "whole_source_read": True},
        "practice": {"target_behavior": skill, "result": status, "source_span": turn["text"],
                     "source_start": turn["start"], "source_end": turn["end"],
                     "adjustment": adjustment},
    }


def _account_lens(session: dict, source: str, context: dict | None) -> list[dict]:
    if not context:
        return []
    relevant = CALL_RELEVANCE.get(session["call_type"], set())
    lower = source.lower()
    output = []
    current: dict[str, dict] = {}
    for pillar in context["readiness"].get("pillars", []):
        current[pillar.get("key")] = pillar
    for program in context["readiness"].get("programs", []):
        for pillar in program.get("pillars", []):
            current.setdefault(pillar.get("key"), pillar)
    for key, hints in PILLAR_HINTS.items():
        hit = next((hint for hint in hints if hint in lower), None)
        if hit:
            start = lower.find(hit)
            line_start = source.rfind("\n", 0, start) + 1
            line_end = source.find("\n", start)
            if line_end < 0:
                line_end = len(source)
            output.append({"pillar_key": key, "label": "clarified",
                           "reason": "The call discussed language relevant to this pillar; it is not account evidence until reviewed.",
                           "source_span": source[line_start:line_end].strip(),
                           "current_readiness": current.get(key)})
        elif key in relevant:
            output.append({"pillar_key": key, "label": "missed_opportunity",
                           "reason": "This call type made the pillar relevant, but the retained source did not make it explicit.",
                           "source_span": None, "current_readiness": current.get(key)})
        else:
            output.append({"pillar_key": key, "label": "not_relevant",
                           "reason": "This pillar was not required for the selected call type.",
                           "source_span": None, "current_readiness": current.get(key)})
    return output


@jobs.register("coaching_analyze")
def analyze_job(conn: sqlite3.Connection, payload: dict) -> dict:
    run_id = payload.get("run_id")
    run = repo.get_row(conn, "coaching_runs", run_id)
    session = repo.get_row(conn, "coaching_sessions", run["session_id"])
    source_row = conn.execute("SELECT * FROM coaching_sources WHERE session_id=?",
                              (session["id"],)).fetchone()
    ts = now_utc()
    with conn:
        conn.execute("UPDATE coaching_runs SET status='running',updated_at=? WHERE id=?", (ts, run_id))
    try:
        if not source_row or source_row["snapshot_text"] is None:
            raise ValueError("the retained source is unavailable")
        source = source_row["snapshot_text"]
        output = (_analyze_practice(session, source) if session["mode"] == "rehearsal"
                  else _analyze_review(session, source))
        coaching_contract.validate(output, source, session.get("coached_speaker_key"))
        context = json.loads(run["account_context_snapshot_json"]) if run["account_context_snapshot_json"] else None
        lens = _account_lens(session, source, context) if session["mode"] == "review" else []
        status = "partial" if output["coverage"].get("status") in {"restricted", "insufficient"} else "completed"
        finished = now_utc()
        with conn:
            conn.execute("DELETE FROM coaching_observations WHERE run_id=?", (run_id,))
            for ordinal, item in enumerate(output["observations"]):
                conn.execute(
                    "INSERT INTO coaching_observations(id,run_id,kind,skill_key,headline,situation,"
                    "behavior,impact_type,impact_text,alternative,source_span,source_start,source_end,"
                    "source_timestamp,source_speaker_key,is_top_priority,ordinal,created_at,updated_at) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (new_id(), run_id, item["kind"], item["skill_key"], item["headline"],
                     item["situation"], item["behavior"], item["impact_type"], item["impact_text"],
                     item["alternative"], item["source_span"], item["source_start"], item["source_end"],
                     item.get("source_timestamp"), item.get("source_speaker_key"),
                     1 if item.get("is_top_priority") else 0, ordinal, finished, finished))
            conn.execute(
                "UPDATE coaching_runs SET status=?,summary=?,account_lens_json=?,practice_json=?,"
                "coverage_json=?,error_json=NULL,finished_at=?,updated_at=? WHERE id=?",
                (status, output["summary"], json.dumps(lens),
                 json.dumps(output.get("practice")) if output.get("practice") else None,
                 json.dumps(output["coverage"]), finished, finished, run_id))
        return {"run_id": run_id, "session_id": session["id"], "status": status}
    except Exception as exc:
        finished = now_utc()
        with conn:
            conn.execute("UPDATE coaching_runs SET status='failed',error_json=?,finished_at=?,"
                         "updated_at=? WHERE id=?",
                         (json.dumps({"message": str(exc), "retryable": True}), finished, finished, run_id))
        raise


def _decode(row: dict, *keys: str) -> dict:
    for key in keys:
        raw = row.get(key)
        row[key.removesuffix("_json")] = json.loads(raw) if raw else None
    return row


def _run_detail(conn: sqlite3.Connection, run: dict) -> dict:
    run = _decode(dict(run), "account_context_snapshot_json", "account_lens_json", "practice_json",
                  "coverage_json", "error_json")
    run["observations"] = [dict(row) for row in conn.execute(
        "SELECT * FROM coaching_observations WHERE run_id=? ORDER BY is_top_priority DESC,ordinal",
        (run["id"],)).fetchall()]
    return run


def get_session(conn: sqlite3.Connection, session_id: str) -> dict:
    session = repo.get_row(conn, "coaching_sessions", session_id)
    source = conn.execute("SELECT * FROM coaching_sources WHERE session_id=?", (session_id,)).fetchone()
    runs = [_run_detail(conn, dict(row)) for row in conn.execute(
        "SELECT * FROM coaching_runs WHERE session_id=? ORDER BY created_at DESC", (session_id,)).fetchall()]
    result = dict(session)
    result["source"] = dict(source) if source else None
    if result["source"]:
        result["source"]["snapshot_present"] = result["source"]["snapshot_text"] is not None
        result["source"]["speakers"] = (coaching_contract.speaker_keys(result["source"]["snapshot_text"])
                                         if result["source"]["snapshot_text"] else [])
    result["runs"] = runs
    result["latest_run"] = runs[0] if runs else None
    result["active_goal"] = active_goal(conn)
    if result.get("account_id"):
        account = conn.execute("SELECT id,name FROM accounts WHERE id=?", (result["account_id"],)).fetchone()
        result["account"] = dict(account) if account else None
    if result.get("program_id"):
        program = conn.execute("SELECT id,name,phase FROM programs WHERE id=?", (result["program_id"],)).fetchone()
        result["program"] = dict(program) if program else None
    return result


def list_sessions(conn: sqlite3.Connection, *, account_id: str | None = None,
                  mode: str | None = None, limit: int = 50) -> dict:
    clauses = ["s.archived=0"]
    params: list[Any] = []
    if account_id:
        clauses.append("s.account_id=?"); params.append(account_id)
    if mode:
        clauses.append("s.mode=?"); params.append(mode)
    params.append(max(1, min(limit, 200)))
    rows = conn.execute(
        "SELECT s.*,a.name AS account_name,(SELECT status FROM coaching_runs r WHERE r.session_id=s.id "
        "ORDER BY r.created_at DESC LIMIT 1) AS latest_status,"
        "(SELECT summary FROM coaching_runs r WHERE r.session_id=s.id ORDER BY r.created_at DESC LIMIT 1) AS latest_summary "
        "FROM coaching_sessions s LEFT JOIN accounts a ON a.id=s.account_id WHERE "
        + " AND ".join(clauses) + " ORDER BY s.updated_at DESC LIMIT ?", tuple(params)).fetchall()
    return {"sessions": [dict(row) for row in rows], "active_goal": active_goal(conn)}


def respond_to_observation(conn: sqlite3.Connection, observation_id: str,
                           response: str, note: str | None = None) -> dict:
    if response not in ALLOWED_RESPONSES:
        raise HTTPException(422, "unknown coaching response")
    row = repo.get_row(conn, "coaching_observations", observation_id)
    ts = now_utc()
    with conn:
        conn.execute("UPDATE coaching_observations SET operator_response=?,operator_note=?,updated_at=? "
                     "WHERE id=?", (response, (note or "").strip() or None, ts, observation_id))
        audit.record(conn, object_type="coaching_observation", object_id=observation_id,
                     action="update", before={"response": row["operator_response"]},
                     after={"event": "operator_response", "response": response})
    return dict(conn.execute("SELECT * FROM coaching_observations WHERE id=?", (observation_id,)).fetchone())


def active_goal(conn: sqlite3.Connection) -> dict | None:
    row = conn.execute(
        "SELECT g.*,o.headline,o.alternative,o.run_id,r.session_id,s.title AS session_title "
        "FROM coaching_goals g JOIN coaching_observations o ON o.id=g.source_observation_id "
        "JOIN coaching_runs r ON r.id=o.run_id JOIN coaching_sessions s ON s.id=r.session_id "
        "WHERE g.status='active' ORDER BY g.created_at DESC LIMIT 1").fetchone()
    return dict(row) if row else None


def create_goal(conn: sqlite3.Connection, observation_id: str, revisit_after: str | None = None) -> dict:
    observation = repo.get_row(conn, "coaching_observations", observation_id)
    ts = now_utc()
    goal_id = new_id()
    with conn:
        conn.execute("UPDATE coaching_goals SET status='replaced',updated_at=? WHERE status='active'", (ts,))
        conn.execute("INSERT INTO coaching_goals(id,source_observation_id,skill_key,behavior,status,"
                     "revisit_after,created_by,created_at,updated_at) VALUES (?,?,?,?, 'active',?,?,?,?)",
                     (goal_id, observation_id, observation["skill_key"], observation["alternative"],
                      revisit_after, CREATED_BY, ts, ts))
        audit.record(conn, object_type="coaching_goal", object_id=goal_id, action="create",
                     after={"event": "activated", "skill_key": observation["skill_key"]})
    return active_goal(conn)


def complete_goal(conn: sqlite3.Connection, goal_id: str) -> dict:
    goal = repo.get_row(conn, "coaching_goals", goal_id)
    if goal["status"] != "active":
        raise HTTPException(409, "only the active coaching focus can be completed")
    ts = now_utc()
    with conn:
        conn.execute("UPDATE coaching_goals SET status='completed',completed_at=?,updated_at=? WHERE id=?",
                     (ts, ts, goal_id))
        audit.record(conn, object_type="coaching_goal", object_id=goal_id, action="update",
                     before={"status": goal["status"]},
                     after={"event": "completed", "status": "completed"})
    return dict(conn.execute("SELECT * FROM coaching_goals WHERE id=?", (goal_id,)).fetchone())


def create_rehearsal(conn: sqlite3.Connection, parent_session_id: str, body: dict) -> dict:
    parent = get_session(conn, parent_session_id)
    observation_id = body.get("origin_observation_id")
    if not observation_id:
        raise HTTPException(422, "origin_observation_id is required")
    observation = repo.get_row(conn, "coaching_observations", observation_id)
    if not any(observation_id == item["id"] for run in parent["runs"] for item in run["observations"]):
        raise HTTPException(422, "origin observation does not belong to this session")
    attempt = (body.get("attempt_text") or "").strip()
    if not attempt:
        raise HTTPException(422, "attempt_text is required")
    return create_session(conn, {
        "mode": "rehearsal", "parent_session_id": parent_session_id,
        "origin_observation_id": observation_id, "account_id": parent.get("account_id"),
        "program_id": parent.get("program_id"), "title": f"Practice · {observation['headline']}",
        "call_type": parent["call_type"], "intended_outcome": body.get("objective") or observation["alternative"],
        "coaching_focus": observation["skill_key"], "source_kind": "practice_transcript",
        "text": attempt, "speaker_status": "not_applicable",
    })


def link_preview(conn: sqlite3.Connection, session_id: str, account_id: str,
                 program_id: str | None = None) -> dict:
    session = repo.get_row(conn, "coaching_sessions", session_id)
    account_id, program_id = _validate_scope(conn, account_id=account_id, program_id=program_id,
                                             interaction_id=None)
    return {"session_id": session_id, "from": {"account_id": session["account_id"],
            "program_id": session["program_id"]}, "to": {"account_id": account_id,
            "program_id": program_id}, "consequences": [
                "A new account-aware coaching run will be created.",
                "Earlier standalone runs remain unchanged.",
                "No account record or readiness state will be written.",
            ]}


def link_session(conn: sqlite3.Connection, session_id: str, account_id: str,
                 program_id: str | None = None) -> dict:
    preview = link_preview(conn, session_id, account_id, program_id)
    ts = now_utc()
    with conn:
        conn.execute("UPDATE coaching_sessions SET account_id=?,program_id=?,updated_at=? WHERE id=?",
                     (account_id, program_id, ts, session_id))
        audit.record(conn, object_type="coaching_session", object_id=session_id, action="update",
                     before=preview["from"], after=preview["to"])
    run = enqueue_run(conn, session_id)
    result = get_session(conn, session_id)
    result["receipt"] = {"run_id": run["id"], "job_id": run["job_id"]}
    return result


def unlink_preview(conn: sqlite3.Connection, session_id: str) -> dict:
    session = repo.get_row(conn, "coaching_sessions", session_id)
    return {"session_id": session_id, "account_id": session["account_id"],
            "program_id": session["program_id"], "interaction_id": session["interaction_id"],
            "survives": [value for value in (
                "The historical account-context snapshot remains on completed runs.",
                "The native Interaction survives." if session["interaction_id"] else None,
                "Resolved proposal decisions survive.",
            ) if value]}


def unlink_session(conn: sqlite3.Connection, session_id: str) -> dict:
    preview = unlink_preview(conn, session_id)
    ts = now_utc()
    with conn:
        conn.execute("UPDATE coaching_sessions SET account_id=NULL,program_id=NULL,updated_at=? WHERE id=?",
                     (ts, session_id))
        audit.record(conn, object_type="coaching_session", object_id=session_id, action="update",
                     before={"account_id": preview["account_id"], "program_id": preview["program_id"]},
                     after={"account_id": None, "program_id": None})
    return get_session(conn, session_id)


def log_interaction(conn: sqlite3.Connection, session_id: str) -> dict:
    session = repo.get_row(conn, "coaching_sessions", session_id)
    if session["mode"] != "review":
        raise HTTPException(422, "practice is not an account interaction")
    if not session["account_id"]:
        raise HTTPException(422, "link the call to an account before logging it")
    if session["interaction_id"]:
        return interaction_ops.read(conn, session["interaction_id"])
    interaction = interaction_ops.create(conn, InteractionCreate(
        account_id=session["account_id"], program_id=session["program_id"],
        occurred_on=session["call_date"], type="call", summary=session["title"],
        raw_notes="Reviewed privately in Call Coach; retained source remains in Coach.",
        meaningful_touch=True,
    ))
    with conn:
        conn.execute("UPDATE coaching_sessions SET interaction_id=?,updated_at=? WHERE id=?",
                     (interaction["id"], now_utc(), session_id))
    return interaction


def draft_account_updates(conn: sqlite3.Connection, session_id: str, run_id: str | None = None) -> dict:
    session = repo.get_row(conn, "coaching_sessions", session_id)
    if session["mode"] != "review" or not session["account_id"]:
        raise HTTPException(422, "only an account-linked completed call can draft account updates")
    source = conn.execute("SELECT * FROM coaching_sources WHERE session_id=?", (session_id,)).fetchone()
    if not source or source["snapshot_text"] is None:
        raise HTTPException(409, "the retained source is unavailable")
    target_run = conn.execute(
        "SELECT id,extraction_run_id FROM coaching_runs WHERE id=? AND session_id=?",
        (run_id, session_id),
    ).fetchone() if run_id else conn.execute(
        "SELECT id,extraction_run_id FROM coaching_runs WHERE session_id=? ORDER BY created_at DESC LIMIT 1",
        (session_id,),
    ).fetchone()
    if not target_run:
        raise HTTPException(422, "coaching run does not belong to this session")
    if target_run["extraction_run_id"]:
        existing = repo.get_row(conn, "extraction_runs", target_run["extraction_run_id"])
        row = conn.execute("SELECT COUNT(*) AS n FROM extraction_proposals WHERE run_id=?",
                           (existing["id"],)).fetchone()
        return {"session_id": session_id, "coaching_run_id": target_run["id"],
                "extraction_run_id": existing["id"], "proposal_count": row["n"],
                "already_drafted": True,
                "note": "These account drafts were already waiting in Proposal Review; no duplicate run was created."}
    from . import extractor
    from .routers.ai import _persist_run
    engine = extractor.get_extractor("mock")
    proposals = engine.extract(source["snapshot_text"])
    extraction_run_id = _persist_run(
        conn, account_id=session["account_id"], program_id=session["program_id"],
        interaction_id=session["interaction_id"], model_version=engine.model_version,
        prompt_version=engine.prompt_version, source_text=source["snapshot_text"],
        proposals=proposals, extractor_backend="mock", source_kind="other", provider=PROVIDER,
        # Proposal grounding resolves this closed provider id back to coaching_sources by session.
        # Idempotency belongs to coaching_runs.extraction_run_id above, not to this provenance key.
        external_id=session_id, coverage={"source": "private_call_coach_snapshot"})
    with conn:
        conn.execute("UPDATE coaching_runs SET extraction_run_id=?,updated_at=? WHERE id=?",
                     (extraction_run_id, now_utc(), target_run["id"]))
    row = conn.execute("SELECT COUNT(*) AS n FROM extraction_proposals WHERE run_id=?",
                       (extraction_run_id,)).fetchone()
    return {"session_id": session_id, "coaching_run_id": target_run["id"],
            "extraction_run_id": extraction_run_id, "proposal_count": row["n"],
            "already_drafted": False,
            "note": "Drafts are waiting in the existing Proposal Review. Coaching observations were not copied."}


def delete_source_snapshot(conn: sqlite3.Connection, source_id: str) -> dict:
    source = repo.get_row(conn, "coaching_sources", source_id)
    if source["snapshot_text"] is None:
        return {"source_id": source_id, "snapshot_present": False,
                "note": "The retained source had already been deleted."}
    ts = now_utc()
    with conn:
        conn.execute("UPDATE coaching_sources SET snapshot_text=NULL,snapshot_deleted_at=?,"
                     "snapshot_deleted_by=?,updated_at=? WHERE id=?", (ts, CREATED_BY, ts, source_id))
        audit.record(conn, object_type="coaching_source", object_id=source_id, action="update",
                     before={"snapshot_chars": len(source["snapshot_text"])},
                     after={"snapshot_text": None})
    return {"source_id": source_id, "snapshot_present": False,
            "note": "Source text was deleted. Existing citations remain as quoted spans and cannot be reopened in context."}


def archive_session(conn: sqlite3.Connection, session_id: str) -> None:
    session = repo.get_row(conn, "coaching_sessions", session_id)
    if session["archived"]:
        return
    ts = now_utc()
    with conn:
        conn.execute("UPDATE coaching_sessions SET archived=1,archived_at=?,archived_by=?,updated_at=? "
                     "WHERE id=?", (ts, CREATED_BY, ts, session_id))
        audit.record(conn, object_type="coaching_session", object_id=session_id, action="archive",
                     after={"archived": True})
