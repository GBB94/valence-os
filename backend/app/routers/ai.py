import json
import re
import sqlite3

from fastapi import APIRouter, Depends, HTTPException

from pydantic import ValidationError

from .. import audit, execution_ops, extractor, repo, stage7, stage9
from ..db import new_id, now_utc
from ..deps import get_conn
from ..schemas import (
    CommitmentCreate, DecisionCreate, ExtractionRequest, IssueCreate, ManualExtractionRequest,
    MomentCreate, PlayDefinitionCreate, PlayEffectiveness, ProposalAccept, PullSignalCreate,
    RiskCreate, TaskCreate, ValueStoryCreate,
)

_TARGET_SCHEMA = {
    "task": TaskCreate, "commitment": CommitmentCreate, "decision": DecisionCreate,
    "risk": RiskCreate, "issue": IssueCreate,
}

# §4.4 targets that create relationship / commercial records (not program-scoped execution objects).
_STAGE5_MUTATIONS = ("fill_placeholder", "log_pull_signal", "create_deployment_moment", "create_value_story")

router = APIRouter(prefix="/api", tags=["ai"])


def _notify(conn, kind, message, ref_type=None, ref_id=None):
    conn.execute(
        "INSERT INTO notifications (id, kind, message, ref_type, ref_id, read, created_at) VALUES (?,?,?,?,?,0,?)",
        (new_id(), kind, message, ref_type, ref_id, now_utc()),
    )


# --- Transcript extraction (Section 3 security model) ---
def _persist_run(conn, *, account_id, program_id, interaction_id, model_version, prompt_version,
                 transcript_chars, proposals):
    """Store an extraction run + its proposals. Nothing touches domain tables here —
    proposals await per-item human acceptance. Shared by every backend + manual paste."""
    ts = now_utc()
    run_id = new_id()
    with conn:
        conn.execute(
            "INSERT INTO extraction_runs (id, account_id, program_id, interaction_id, model_version, "
            "prompt_version, transcript_chars, status, created_at, updated_at) VALUES (?,?,?,?,?,?,?, 'proposed', ?, ?)",
            (run_id, account_id, program_id, interaction_id, model_version, prompt_version, transcript_chars, ts, ts),
        )
        audit.record(conn, object_type="extraction_run", object_id=run_id, action="create",
                     after={"model_version": model_version, "prompt_version": prompt_version, "proposals": len(proposals)})
        for p in proposals:
            conn.execute(
                "INSERT INTO extraction_proposals (id, run_id, mutation_type, payload_json, source_span, "
                "confidence, status, created_at, updated_at) VALUES (?,?,?,?,?,?, 'proposed', ?, ?)",
                (new_id(), run_id, p["mutation_type"], json.dumps(p["payload"]), p["source_span"], p["confidence"], ts, ts),
            )
    return run_id


@router.get("/extraction/config")
def extraction_config():
    """Which backend is active, plus the strict schema and the prompt to hand a local LLM."""
    return extractor.describe_config()


@router.post("/extraction/run", status_code=201)
def run_extraction(b: ExtractionRequest, conn: sqlite3.Connection = Depends(get_conn)):
    """Propose structured updates from a transcript via the mock or API backend."""
    repo.get_row(conn, "accounts", b.account_id)
    try:
        ex = extractor.get_extractor(b.backend)
        proposals = ex.extract(b.transcript)
    except (ValueError,) as e:
        raise HTTPException(422, str(e))
    except (RuntimeError,) as e:                       # backend unavailable (no SDK/creds) or model error
        raise HTTPException(502, str(e))
    run_id = _persist_run(conn, account_id=b.account_id, program_id=b.program_id,
                          interaction_id=b.interaction_id, model_version=ex.model_version,
                          prompt_version=ex.prompt_version, transcript_chars=len(b.transcript),
                          proposals=proposals)
    return get_run(run_id, conn)


@router.post("/extraction/manual", status_code=201)
def manual_extraction(b: ManualExtractionRequest, conn: sqlite3.Connection = Depends(get_conn)):
    """Ingest JSON the operator produced with their OWN local LLM. The app makes no
    external call; the pasted output is validated against the same strict schema."""
    repo.get_row(conn, "accounts", b.account_id)
    try:
        proposals = extractor.validate_proposals(b.proposals_json)
    except ValueError as e:
        raise HTTPException(422, f"pasted output failed validation: {e}")
    run_id = _persist_run(conn, account_id=b.account_id, program_id=b.program_id,
                          interaction_id=b.interaction_id, model_version="manual-local-llm",
                          prompt_version=extractor.ApiExtractor.prompt_version,
                          transcript_chars=len(b.proposals_json), proposals=proposals)
    return get_run(run_id, conn)


@router.get("/extraction/runs/{run_id}")
def get_run(run_id: str, conn: sqlite3.Connection = Depends(get_conn)):
    run = repo.get_row(conn, "extraction_runs", run_id)
    props = [repo.row_to_dict(r) for r in
             conn.execute("SELECT * FROM extraction_proposals WHERE run_id=? ORDER BY created_at", (run_id,))]
    for p in props:
        p["payload"] = json.loads(p["payload_json"])
    run["proposals"] = props
    return run


def _finalize_proposal(conn, proposal_id, source_span, created_type, created_id):
    with conn:
        conn.execute(
            "UPDATE extraction_proposals SET status='accepted', created_object_type=?, created_object_id=?, updated_at=? WHERE id=?",
            (created_type, created_id, now_utc(), proposal_id))
        audit.record(conn, object_type="extraction_proposal", object_id=proposal_id, action="convert",
                     after={"created": created_type, "id": created_id, "source_span": source_span})


# Generic seniority ranks. They appear in almost every position title, so matching on them
# would make everything look like everything else.
_PH_RANKS = {"vp", "head", "lead", "leader", "director", "manager", "chief", "officer",
             "senior", "global", "regional", "deputy", "interim"}
_PH_STOP = _PH_RANKS | {"of", "the", "and", "for", "our", "new", "will", "our", "their"}


def _role_tokens(text: str) -> set[str]:
    """The words in a position description that actually identify WHICH position.

    Two kinds carry signal: domain words ("security", "legal", "procurement") and uppercase
    acronyms ("IT", "HR", "DPO", "CHRO"). The acronyms have to be picked out case-sensitively
    before lowercasing — a >3-char filter drops "IT" and "HR", which are often the only
    identifying token in the sentence, and a >1-char filter on lowercased text would pull in
    "is", "of", and the pronoun "it".
    """
    acronyms = {a.lower() for a in re.findall(r"\b[A-Z]{2,6}\b", text or "")}
    words = {w for w in re.findall(r"[a-z]{4,}", (text or "").lower())}
    return (acronyms | words) - _PH_STOP


def _match_placeholder(conn, account_id: str, payload: dict, source_span: str | None) -> str | None:
    """Find the one unfilled placeholder this fill resolves, or None.

    Deliberately conservative: returns a match ONLY when exactly one placeholder shares a role
    token. Silently filling the wrong position is worse than leaving it open, and the spec's
    association rule is explicit that low-confidence items are assigned by a human, never
    guessed. The operator can always name the target with `placeholder_person_id`.
    """
    if not account_id:
        return None
    tokens = _role_tokens(" ".join(filter(None, [payload.get("title"), source_span])))
    if not tokens:
        return None
    hits = [ph["id"] for ph in repo.list_rows(
        conn, "persons", where="account_id=? AND is_placeholder=1", params=(account_id,))
        if tokens & _role_tokens(f"{ph['title'] or ''} {ph['placeholder_why'] or ''} {ph['name'] or ''}")]
    return hits[0] if len(hits) == 1 else None


def _accept_stage5(conn, prop, run, payload):
    """Apply a §4.4 relationship/commercial proposal (placeholder-fill, pull signal, deployment
    moment, value-story candidate). Same per-item human acceptance as execution proposals."""
    mt = prop["mutation_type"]
    account_id = payload.get("account_id") or run.get("account_id")
    program_id = payload.get("program_id") or run.get("program_id")
    desc = payload.get("description") or ""
    interaction_id = run.get("interaction_id")

    if mt == "fill_placeholder":
        name = (payload.get("name") or desc or "").strip()
        if not name:
            raise HTTPException(422, "This placeholder-fill needs a name (supply it in overrides).")
        # A placeholder-fill must FILL a placeholder. It used to always insert a new person,
        # leaving the placeholder unidentified and putting two rows in the org chart for one
        # position — the opposite of what the mutation is named for, and it kept the
        # `unidentified_placeholder` queue trigger firing forever.
        target_id = payload.get("placeholder_person_id")
        if target_id:
            ph = repo.get_row(conn, "persons", target_id)
            if not ph["is_placeholder"]:
                raise HTTPException(422, f"person {target_id} is not a placeholder")
            if ph["account_id"] != account_id:
                raise HTTPException(422, "that placeholder belongs to a different account")
        else:
            target_id = _match_placeholder(conn, account_id, payload, prop["source_span"])
        if target_id:
            created = repo.patch(conn, "persons", target_id, {
                "name": name, "title": payload.get("title") or None, "is_placeholder": 0,
            }, object_type="person")
        else:
            # No placeholder matched: fall back to creating the person, so a newly-named
            # stakeholder is never dropped. The operator can still fill a placeholder
            # explicitly by passing placeholder_person_id in overrides.
            created = repo.insert(conn, "persons", {
                "name": name, "affiliation": "client", "account_id": account_id,
                "title": payload.get("title")}, object_type="person")
        target = "person"

    elif mt == "log_pull_signal":
        body = PullSignalCreate(account_id=account_id, program_id=program_id, description=desc or "expansion signal",
                               occurred_on=now_utc()[:10], source_interaction_id=interaction_id)
        created = repo.insert(conn, "pull_signals", body.model_dump(), object_type="pull_signal")
        target = "pull_signal"

    elif mt == "create_deployment_moment":
        if not program_id:
            raise HTTPException(422, "A deployment moment needs a program_id (supply it in overrides).")
        body = MomentCreate(program_id=program_id, name=desc or "deployment moment",
                            type=payload.get("moment_type") or "business_event")
        created = repo.insert(conn, "deployment_moments", body.model_dump(), object_type="deployment_moment")
        target = "deployment_moment"

    elif mt == "create_value_story":
        # defaults to internal visibility — safe by construction; the operator promotes later.
        body = ValueStoryCreate(outcome=desc or "value story", account_id=account_id, program_id=program_id,
                                source_reference_id=payload.get("source_reference_id"))
        created = repo.insert(conn, "value_stories", body.model_dump(), object_type="value_story")
        target = "value_story"
    else:  # pragma: no cover — guarded by the caller's membership check
        raise HTTPException(422, f"unhandled stage-5 mutation {mt}")

    _finalize_proposal(conn, prop["id"], prop["source_span"], target, created["id"])
    return {"proposal_id": prop["id"], "created_type": target, "created": created}


@router.post("/extraction/proposals/{proposal_id}/accept")
def accept_proposal(proposal_id: str, b: ProposalAccept, conn: sqlite3.Connection = Depends(get_conn)):
    """Apply ONE proposal, creating the real object. Requires a program (execution objects
    are program-scoped). Overrides let the operator complete required fields (e.g. owners)."""
    prop = conn.execute("SELECT * FROM extraction_proposals WHERE id=?", (proposal_id,)).fetchone()
    if not prop:
        raise HTTPException(404, "proposal not found")
    if prop["status"] != "proposed":
        raise HTTPException(409, f"proposal already {prop['status']}")
    run = repo.get_row(conn, "extraction_runs", prop["run_id"])
    payload = {**json.loads(prop["payload_json"]), **(b.overrides or {})}

    # §4.4 relationship/commercial targets take a different (non-execution) write path.
    if prop["mutation_type"] in _STAGE5_MUTATIONS:
        return _accept_stage5(conn, prop, run, payload)

    program_id = payload.get("program_id") or run.get("program_id")
    if not program_id:
        raise HTTPException(422, "This proposal needs a program_id (supply it in overrides).")
    payload["program_id"] = program_id
    if run.get("interaction_id"):
        payload.setdefault("source_interaction_id", run["interaction_id"])
    target = prop["mutation_type"].replace("create_", "")
    # validate against the same schema the manual API uses, so required fields
    # (e.g. a commitment's two owners + due date) yield a clean 422, not a DB error
    try:
        validated = _TARGET_SCHEMA[target](**payload).model_dump()
    except ValidationError as e:
        raise HTTPException(422, f"{target} needs more before it can be created: {e.errors()[0].get('loc')} — supply it in overrides.")
    created = execution_ops.create(conn, target, validated)
    _finalize_proposal(conn, proposal_id, prop["source_span"], target, created["id"])
    return {"proposal_id": proposal_id, "created_type": target, "created": created}


@router.post("/extraction/proposals/{proposal_id}/reject")
def reject_proposal(proposal_id: str, conn: sqlite3.Connection = Depends(get_conn)):
    prop = conn.execute("SELECT * FROM extraction_proposals WHERE id=?", (proposal_id,)).fetchone()
    if not prop:
        raise HTTPException(404, "proposal not found")
    # An accepted proposal already wrote a domain record. Flipping it to 'rejected' leaves the
    # record in place and makes the audit trail say the operator declined something they
    # actually accepted — archive the created object instead.
    if prop["status"] == "accepted":
        raise HTTPException(409, "proposal was already accepted; archive the created "
                                 f"{prop['created_object_type'] or 'record'} instead of rejecting it")
    with conn:
        conn.execute("UPDATE extraction_proposals SET status='rejected', updated_at=? WHERE id=?",
                     (now_utc(), proposal_id))
    return {"proposal_id": proposal_id, "status": "rejected"}


# --- Plays trigger engine ---
@router.post("/plays", status_code=201)
def create_play(b: PlayDefinitionCreate, conn: sqlite3.Connection = Depends(get_conn)):
    return repo.insert(conn, "play_definitions", b.model_dump(), object_type="play_definition")


@router.get("/plays")
def list_plays(conn: sqlite3.Connection = Depends(get_conn)):
    plays = repo.list_rows(conn, "play_definitions", where="1=1 ORDER BY name")
    for p in plays:
        p["active"] = bool(p["active"])
    return plays


@router.post("/plays/evaluate")
def evaluate_plays(conn: sqlite3.Connection = Depends(get_conn)):
    """Evaluate active plays against recurring condition episodes.

    A play is unique per episode, not per object forever. A condition which clears and later
    recurs gets a new episode and may fire again; repeated evaluation of the same open episode
    remains idempotent.
    """
    fired = []
    plays = repo.list_rows(conn, "play_definitions", where="active=1")
    from ..queue import build_queue
    q = build_queue(conn)
    stage7.sync_attention_episodes(conn, q["items"])
    stage7.evaluate_domain_signals(conn)
    episodes = stage7.list_episodes(conn, status="open")
    by_trigger: dict[str, list] = {}
    for episode in episodes:
        by_trigger.setdefault(episode["kind"], []).append(episode)
    with conn:
        for play in plays:
            for episode in by_trigger.get(play["trigger_kind"], []):
                if not stage9.play_applies_to_cell(conn, play["id"], episode.get("cell_id")):
                    continue
                dedupe = f"{play['id']}:episode:{episode['id']}"
                exists = conn.execute("SELECT 1 FROM play_runs WHERE dedupe_key=?", (dedupe,)).fetchone()
                if exists:
                    continue
                rid = new_id()
                context = episode.get("context") or {}
                title = context.get("title") or episode.get("use_case") or episode["kind"].replace("_", " ")
                because = episode["explanation"]
                action = play["action_template"].replace("{title}", title).replace("{because}", because)
                conn.execute(
                    "INSERT INTO play_runs (id,play_id,account_id,signal_episode_id,trigger_context,"
                    "action_text,status,dedupe_key,fired_at) VALUES (?,?,?,?,?,?,'fired',?,?)",
                    (rid, play["id"], episode.get("account_id"), episode["id"], because,
                     action, dedupe, now_utc()))
                _notify(conn, "play_fired", f"Play '{play['name']}' fired: {action}", "play_run", rid)
                audit.record(conn, object_type="play_run", object_id=rid, action="create",
                             after={"play": play["name"], "trigger": play["trigger_kind"],
                                    "episode_id": episode["id"]})
                fired.append({"id": rid, "play": play["name"], "action": action,
                              "context": because, "episode_id": episode["id"]})
    return {"fired": fired, "count": len(fired)}


@router.get("/play-runs")
def list_play_runs(status: str | None = None, conn: sqlite3.Connection = Depends(get_conn)):
    where = "1=1" if not status else "status=?"
    params = () if not status else (status,)
    runs = [repo.row_to_dict(r) for r in conn.execute(
        f"SELECT * FROM play_runs WHERE {where} ORDER BY fired_at DESC", params)]
    names = {p["id"]: p["name"] for p in repo.list_rows(conn, "play_definitions", where="1=1")}
    for r in runs:
        r["play_name"] = names.get(r["play_id"])
    return runs


@router.post("/play-runs/{run_id}/complete")
def complete_play_run(run_id: str, b: PlayEffectiveness, conn: sqlite3.Connection = Depends(get_conn)):
    """Complete a play run WITH an effectiveness note so the playbook improves."""
    run = conn.execute("SELECT * FROM play_runs WHERE id=?", (run_id,)).fetchone()
    if not run:
        raise HTTPException(404, "play run not found")
    with conn:
        conn.execute(
            "UPDATE play_runs SET status='completed', effectiveness=?, effectiveness_note=?, completed_at=? WHERE id=?",
            (b.effectiveness, b.effectiveness_note, now_utc(), run_id))
        audit.record(conn, object_type="play_run", object_id=run_id, action="close",
                     after={"effectiveness": b.effectiveness})
    return {"run_id": run_id, "status": "completed", "effectiveness": b.effectiveness}


# --- Notifications ---
@router.get("/notifications")
def list_notifications(unread_only: bool = False, conn: sqlite3.Connection = Depends(get_conn)):
    where = "read=0" if unread_only else "1=1"
    rows = [repo.row_to_dict(r) for r in conn.execute(
        f"SELECT * FROM notifications WHERE {where} ORDER BY created_at DESC LIMIT 50")]
    for r in rows:
        r["read"] = bool(r["read"])
    unread = conn.execute("SELECT COUNT(*) c FROM notifications WHERE read=0").fetchone()["c"]
    return {"notifications": rows, "unread": unread}


@router.post("/notifications/{notification_id}/read")
def mark_read(notification_id: str, conn: sqlite3.Connection = Depends(get_conn)):
    with conn:
        conn.execute("UPDATE notifications SET read=1 WHERE id=?", (notification_id,))
    return {"ok": True}


# --- Briefing assistance (pre-call prep, derived) ---
@router.get("/programs/{program_id}/brief")
def call_brief(program_id: str, conn: sqlite3.Connection = Depends(get_conn)):
    """Assemble a pre-call brief: stance/what-they-care-about per stakeholder, open
    commitments, top risks, last interaction. Derived — labeled as prep, not fact."""
    prog = repo.get_row(conn, "programs", program_id)
    from .programs import _stakeholders_for
    stakeholders = _stakeholders_for(conn, program_id)
    open_commitments = repo.list_rows(conn, "commitments", where="program_id=? AND status='open' ORDER BY due_date", params=(program_id,))
    open_risks = repo.list_rows(conn, "risks", where="program_id=? AND status='open' ORDER BY severity DESC", params=(program_id,))
    last = conn.execute("SELECT * FROM interactions WHERE program_id=? AND archived=0 ORDER BY occurred_on DESC LIMIT 1", (program_id,)).fetchone()
    return {
        "program": {"id": prog["id"], "name": prog["name"], "phase": prog["phase"]},
        "label": "prep brief — recommendations, not confirmed facts",
        "stakeholders": [{"name": s["person_name"], "role": s["role"], "stance": s["stance"],
                          "cares_about": s["cares_about"]} for s in stakeholders],
        "open_commitments": [{"description": c["description"], "due_date": c["due_date"]} for c in open_commitments],
        "top_risks": [{"description": r["description"], "severity": r["severity"], "is_blocker": r["is_blocker"]} for r in open_risks[:3]],
        "last_interaction": repo.row_to_dict(last),
    }
