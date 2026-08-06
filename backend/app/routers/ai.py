import json
import re
import sqlite3

from fastapi import APIRouter, Depends, HTTPException

from pydantic import ValidationError

from .. import audit, execution_ops, extractor, repo, stage7, stage9
from .. import proposal_grounding as proposal_grounding_mod
from .. import proposal_read, proposal_review
from .. import proposals as proposals_mod
from ..db import new_id, now_utc
from ..deps import get_conn
from ..schemas import (
    CommitmentCreate, DecisionCreate, ExtractionRequest, IssueCreate, ManualExtractionRequest,
    MilestoneCreate, MomentCreate, PlayDefinitionCreate, PlayEffectiveness, ProposalAccept, ProposalReject,
    ProposalResolveExisting, ProposalSupersede, PullSignalCreate, RiskCreate, TaskCreate,
    ValueStoryCreate,
)

_TARGET_SCHEMA = {
    "task": TaskCreate, "commitment": CommitmentCreate, "decision": DecisionCreate,
    "risk": RiskCreate, "issue": IssueCreate,
    # ACCOUNT-INTAKE-SPEC.md §10. `MilestoneCreate` requires `program_id` and `name`, so §10's
    # "program required and never inferred from the text" is enforced by the same 422 every other
    # execution target already gets rather than by a rule of its own.
    "milestone": MilestoneCreate,
}

# §4.4 targets that create relationship / commercial records (not program-scoped execution objects).
# Keyed on `target_type`, not on the legacy enum: `create_milestone` has no legacy name, so
# `mutation_type` is NULL on those rows and every dispatch that read it would raise on the None.
_STAGE5_TARGETS = frozenset({"person", "pull_signal", "deployment_moment", "value_story"})

router = APIRouter(prefix="/api", tags=["ai"])


def _notify(conn, kind, message, ref_type=None, ref_id=None):
    conn.execute(
        "INSERT INTO notifications (id, kind, message, ref_type, ref_id, read, created_at) VALUES (?,?,?,?,?,0,?)",
        (new_id(), kind, message, ref_type, ref_id, now_utc()),
    )


# --- Transcript extraction (Section 3 security model) ---
def _drafted_target(conn, intent: str, target_type: str, payload: dict):
    """(target_id, expected_target_updated_at) for an `update` proposal that names its target.

    A `create` has no target, and an update whose target is only resolved at review time (a
    placeholder matched by name) cannot be stamped here — that case falls back to the proposal's
    own `created_at` in `conflict_preview`. Returning (None, None) is therefore normal, not a
    failure; what would be a failure is stamping a target the draft never actually read.
    """
    if intent != "update":
        return None, None
    target_id = payload.get("target_id") or payload.get("placeholder_person_id")
    table = proposal_review._TABLE.get(target_type)
    if not target_id or not table:
        return None, None
    row = conn.execute(f"SELECT updated_at FROM {table} WHERE id=?", (target_id,)).fetchone()
    if not row:
        return None, None
    return target_id, row["updated_at"]


def _persist_run(conn, *, account_id, program_id, interaction_id, model_version, prompt_version,
                 source_text, proposals, extractor_backend, source_kind="transcript",
                 provider=None, external_id=None, source_reference_id=None, coverage=None):
    """Store an extraction run + its proposals. Nothing touches domain tables here —
    proposals await per-item human acceptance. Shared by every backend + manual paste.

    Every proposal arrives in the normalized §6.4 shape (intent + target, fingerprinted) carrying
    the legacy `mutation_type` the current review UI still reads where one exists — §6.5 keeps both
    until the last reader moves. `extractor.KIND_PAIRS` and `proposals.legacy_mutation` are the only
    place the two vocabularies meet, so they cannot drift. A pair with no legacy name — `("create",
    "milestone")` is the first — carries `mutation_type` NULL, which is what migration 0043 made
    the column nullable for.

    `coverage` is what the source contained that this run did **not** read — the drop zone's §14
    object, stored on the run's own `coverage_json` (migration 0043 added the column for exactly
    this). It is a parameter here rather than a second table because a run and its coverage
    disagreeing about what was read is the failure the single-store rule exists to prevent. Callers
    with nothing omitted pass None, which is the honest value: no claim rather than an empty one.

    §10's undraftable screen runs here rather than in each caller because *every* path into an
    extraction run — drop, `.eml`, transcript, manual paste — must report the same omissions. The
    caller's `coverage` dict is mutated in place on purpose: the drop paths hand the same object to
    `_record` for the receipt, so the receipt sees what the run stored without a second read.
    """
    proposals, omissions = extractor.screen_undraftable(proposals, program_id=program_id)
    if omissions:
        if coverage is None:
            coverage = {}
        for key, entries in omissions.items():
            coverage.setdefault(key, []).extend(entries)
    ts = now_utc()
    run_id = new_id()
    hash_ = proposals_mod.content_hash(source_text)
    version_key = proposals_mod.source_version_key(
        source_kind=source_kind, provider=provider, external_id=external_id, hash_=hash_)
    extractor_version = f"{extractor_backend}:{model_version}:{prompt_version}"
    with conn:
        conn.execute(
            "INSERT INTO extraction_runs (id, account_id, program_id, interaction_id, source_kind, "
            "provider, external_id, content_hash, source_version_key, source_reference_id, "
            "extractor_backend, model_version, prompt_version, transcript_chars, coverage_json, "
            "status, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?, 'proposed', ?, ?)",
            (run_id, account_id, program_id, interaction_id, source_kind, provider, external_id,
             hash_, version_key, source_reference_id, extractor_backend, model_version,
             prompt_version, len(source_text), json.dumps(coverage) if coverage else None, ts, ts),
        )
        audit.record(conn, object_type="extraction_run", object_id=run_id, action="create",
                     after={"model_version": model_version, "prompt_version": prompt_version,
                            "backend": extractor_backend, "proposals": len(proposals)})
        for p in proposals:
            # The normalized pair when the caller speaks it, translated from the legacy name when
            # it does not. §6.5 keeps both vocabularies until the last reader moves, and this is
            # the one place they meet — a second translation site is how they would drift.
            intent, target_type = p.get("intent"), p.get("target_type")
            if not (intent and target_type):
                intent, target_type = proposals_mod.legacy_pair(p["mutation_type"])
            fingerprint = proposals_mod.proposal_fingerprint(
                intent=intent, target_type=target_type, payload=p["payload"],
                source_span=p["source_span"], extractor_version=extractor_version)
            # §6.7's optimistic concurrency needs the target as the *draft* saw it. Stamped here
            # rather than at accept time on purpose: `updated_at` read at accept time is the row's
            # current value, so it would compare the record against itself and never be stale.
            target_id, expected = _drafted_target(conn, intent, target_type, p["payload"])
            conn.execute(
                "INSERT INTO extraction_proposals (id, run_id, intent, target_type, mutation_type, "
                "payload_json, source_span, proposal_fingerprint, confidence, target_id, "
                "expected_target_updated_at, status, created_at, updated_at) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?, 'proposed', ?, ?)",
                (new_id(), run_id, intent, target_type, p.get("mutation_type"), json.dumps(p["payload"]),
                 p["source_span"], fingerprint, p["confidence"], target_id, expected, ts, ts),
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
                          prompt_version=ex.prompt_version, source_text=b.transcript,
                          proposals=proposals,
                          extractor_backend=(b.backend or extractor.configured_backend()))
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
                          source_text=b.proposals_json, proposals=proposals,
                          extractor_backend="manual", source_kind="manual")
    return get_run(run_id, conn)


@router.get("/extraction/runs/{run_id}")
def get_run(run_id: str, conn: sqlite3.Connection = Depends(get_conn)):
    run = repo.get_row(conn, "extraction_runs", run_id)
    props = [repo.row_to_dict(r) for r in
             conn.execute("SELECT * FROM extraction_proposals WHERE run_id=? ORDER BY created_at", (run_id,))]
    for p in props:
        p["payload"] = json.loads(p["payload_json"])
        # The §6.4 shape rides alongside the legacy row rather than replacing it: the current
        # review UI still reads `mutation_type` and the flat keys, and §6.5 keeps both readable
        # until the last reader moves.
        p["normalized"] = proposals_mod.normalized(p, run)
    run["proposals"] = props
    return run


def _finalize_proposal(conn, proposal_id, source_span, created_type, created_id):
    ts = now_utc()
    with conn:
        conn.execute(
            "UPDATE extraction_proposals SET status='accepted', resolved_target_type=?, "
            "resolved_target_id=?, resolved_at=?, updated_at=? WHERE id=?",
            (created_type, created_id, ts, ts, proposal_id))
        audit.record(conn, object_type="extraction_proposal", object_id=proposal_id, action="convert",
                     after={"resolved_target": created_type, "id": created_id, "source_span": source_span})


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


def _require_scope_of_run(conn, run, payload):
    """§6.8: an override may complete a proposal's scope, never move it out of the run's.

    `accept` merges operator overrides into the payload and then reads `account_id`/`program_id`
    back out of it, so an override is a direct write path into which account a record lands. A run
    on account A could otherwise create a task on account B's program, and the audit trail would
    cite a source that never mentioned it. A run with no program is the one case an override may
    supply one, and even then the program must belong to the run's account.
    """
    run_account = run.get("account_id")
    account_id = payload.get("account_id")
    if account_id and run_account and account_id != run_account:
        raise HTTPException(422, "an override cannot move a proposal to a different account")

    program_id = payload.get("program_id")
    if not program_id:
        return
    program = conn.execute(
        "SELECT account_id FROM programs WHERE id=? AND archived=0", (program_id,)
    ).fetchone()
    if not program:
        raise HTTPException(422, f"program {program_id} not found")
    if run_account and program["account_id"] != run_account:
        raise HTTPException(422, "that program belongs to a different account")
    if run.get("program_id") and program_id != run["program_id"]:
        raise HTTPException(422, "an override cannot move a proposal to a different program")


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
            # The one path that patches a record the proposal did not create. The generic check in
            # `accept_proposal` could not run it, because the row is only chosen here — so it runs
            # here instead, against the resolved target. Skipping it would let a draft written
            # before somebody else identified this placeholder overwrite their answer.
            conflict = proposal_review.conflict_preview(conn, prop, run, payload,
                                                        target_id=target_id)
            if conflict and conflict["stale"]:
                raise HTTPException(409, {"error": "stale_proposal", "conflict": conflict})
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

    # §6.8: the FINAL edited payload is revalidated, not the drafted one. Overrides are operator
    # input, and an override is exactly how a forbidden field would arrive.
    try:
        proposals_mod.check_pair(prop["intent"], prop["target_type"])
        proposals_mod.check_payload(prop["intent"], prop["target_type"], payload)
    except proposals_mod.ProposalError as e:
        raise HTTPException(422, str(e))
    _require_scope_of_run(conn, run, payload)

    # §6.6: a repeat of an already-resolved proposal returns the existing target. It does not
    # create a second canonical record, and it does not silently no-op either — the proposal is
    # closed as `resolved_existing` so the review queue drains and the audit trail says why.
    prior = proposal_review.already_resolved(conn, prop, run)
    if prior:
        _resolve_existing(conn, prop, prior["target_type"], prior["target_id"],
                          note="Identical to a proposal already resolved against this record.")
        return {"proposal_id": proposal_id, "status": "resolved_existing",
                "resolved_target_type": prior["target_type"], "resolved_target_id": prior["target_id"],
                "duplicate_of": prior["proposal_id"]}

    # §6.7: an update whose target moved after the proposal was drafted returns the preview
    # instead of overwriting newer state.
    conflict = proposal_review.conflict_preview(conn, prop, run, b.overrides)
    if conflict and conflict["stale"]:
        raise HTTPException(409, {"error": "stale_proposal", "conflict": conflict})

    # §4.4 relationship/commercial targets take a different (non-execution) write path.
    if prop["target_type"] in _STAGE5_TARGETS:
        return _accept_stage5(conn, prop, run, payload)

    program_id = payload.get("program_id") or run.get("program_id")
    if not program_id:
        raise HTTPException(422, "This proposal needs a program_id (supply it in overrides).")
    payload["program_id"] = program_id
    if run.get("interaction_id"):
        payload.setdefault("source_interaction_id", run["interaction_id"])
    # The target *is* the target: derived from the normalized column rather than by stripping a
    # prefix off the legacy name, which is NULL for a pair that never had one (§10).
    target = prop["target_type"]
    # validate against the same schema the manual API uses, so required fields
    # (e.g. a commitment's two owners + due date) yield a clean 422, not a DB error
    try:
        validated = _TARGET_SCHEMA[target](**payload).model_dump()
    except ValidationError as e:
        raise HTTPException(422, f"{target} needs more before it can be created: {e.errors()[0].get('loc')} — supply it in overrides.")
    created = execution_ops.create(conn, target, validated)
    _finalize_proposal(conn, proposal_id, prop["source_span"], target, created["id"])
    return {"proposal_id": proposal_id, "created_type": target, "created": created}


# --- run-scoped accept-all — ACCOUNT-INTAKE-SPEC.md §11.4, D-208 -------------------------------

def _accept_blocker(conn, prop, run) -> str | None:
    """Why this proposal cannot be applied with no operator input, or None.

    A **dry run of the accept path**, in its order, writing nothing. §11.4 names three guards — every
    item `proposed`, no conflict, no match candidate — and a fourth is unavoidable in practice:
    `accept_proposal` 422s on a payload missing a required field, and a batch that discovered that on
    item four would have already created three records with no way to say which. So everything is
    checked before anything is written, and the whole call refuses rather than half-applying.

    The reasons are returned as sentences because they are what the operator reads when the button
    is unavailable. A disabled control with no reason reads as a broken app.
    """
    if prop["status"] != "proposed":
        return f"already {prop['status']}"

    payload = json.loads(prop["payload_json"])
    try:
        proposals_mod.check_pair(prop["intent"], prop["target_type"])
        proposals_mod.check_payload(prop["intent"], prop["target_type"], payload)
    except proposals_mod.ProposalError as e:
        return str(e)

    # A match candidate means "this may already exist". Choosing between creating a second record
    # and closing against the existing one is the reviewer's judgement, and it is exactly the
    # judgement a bulk key would skip.
    if proposal_review.match_candidates(conn, prop, run, limit=1):
        return "a record here may already hold this — it needs a choice"

    if proposal_review.already_resolved(conn, prop, run):
        return "an identical proposal was already resolved against a record"

    conflict = proposal_review.conflict_preview(conn, prop, run)
    if conflict and conflict["stale"]:
        return "the record changed after this was drafted"

    if prop["target_type"] in _STAGE5_TARGETS:
        mt = prop["mutation_type"]
        if mt == "fill_placeholder" and not (payload.get("name") or payload.get("description")):
            return "it needs a name"
        if mt == "create_deployment_moment" and not (payload.get("program_id") or run.get("program_id")):
            return "it needs a program"
        return None

    if not (payload.get("program_id") or run.get("program_id")):
        return "it needs a program"
    target = prop["target_type"]
    schema = _TARGET_SCHEMA.get(target)
    if schema is None:
        return f"nothing here knows how to create a {target}"
    trial = {**payload, "program_id": payload.get("program_id") or run.get("program_id")}
    if run.get("interaction_id"):
        trial.setdefault("source_interaction_id", run["interaction_id"])
    try:
        schema(**trial)
    except ValidationError as e:
        field = e.errors()[0].get("loc")
        return f"it needs {field[0] if field else 'more'} filled in first"
    return None


@router.post("/extraction/runs/{run_id}/accept-all")
def accept_all_in_run(run_id: str, conn: sqlite3.Connection = Depends(get_conn)):
    """Apply every open proposal in ONE run, or none of them (§11.4, D-208).

    **Scoped to a run, never to an account.** A key that applied everything pending would apply
    drafts from sources the operator has not looked at — the batch has to be a statement about
    something they can see on one screen, which is why the review surface takes a `run_id` filter in
    the same slice.

    The client's copy of these guards is UX; this one is the truth. A stale browser tab, a second
    reviewer, or a record edited thirty seconds ago all produce a client that thinks the batch is
    clean when it is not — so eligibility is recomputed here and a single ineligible item refuses
    the whole call with the reason.

    **A bare `a` for a single item does not ship** (§11.4). This is the batch path only; one
    proposal is accepted through its own endpoint, with its fields, matches, and conflict in view.
    """
    run = repo.get_row(conn, "extraction_runs", run_id)
    rows = conn.execute(
        "SELECT * FROM extraction_proposals WHERE run_id=? AND status='proposed' "
        "ORDER BY created_at, rowid", (run_id,)).fetchall()
    if not rows:
        raise HTTPException(409, {"error": "nothing_to_accept",
                                  "message": "This source has no open drafts."})

    blocked = [{"proposal_id": r["id"], "target_type": r["target_type"], "why": why}
               for r in rows if (why := _accept_blocker(conn, r, run))]
    if blocked:
        raise HTTPException(409, {
            "error": "not_all_acceptable",
            "message": (f"{len(blocked)} of these {len(rows)} drafts needs a decision of its own, "
                        "so none were applied. Review them one at a time."),
            "blocked": blocked,
        })

    applied, failed = [], []
    for row in rows:
        try:
            applied.append(accept_proposal(row["id"], ProposalAccept(), conn))
        except HTTPException as e:
            # Should be unreachable after the preflight. Reported rather than raised, because the
            # records created before this point are real and the operator has to be told which.
            failed.append({"proposal_id": row["id"], "why": str(e.detail)})
            break
    return {
        "run_id": run_id, "account_id": run["account_id"],
        "accepted": len(applied), "results": applied,
        "complete": not failed, "failed": failed,
    }


@router.post("/extraction/proposals/{proposal_id}/reject")
def reject_proposal(proposal_id: str, b: ProposalReject | None = None,
                    conn: sqlite3.Connection = Depends(get_conn)):
    prop = conn.execute("SELECT * FROM extraction_proposals WHERE id=?", (proposal_id,)).fetchone()
    if not prop:
        raise HTTPException(404, "proposal not found")
    # An accepted proposal already wrote a domain record. Flipping it to 'rejected' leaves the
    # record in place and makes the audit trail say the operator declined something they
    # actually accepted — archive the created object instead.
    if prop["status"] == "accepted":
        raise HTTPException(409, "proposal was already accepted; archive the resolved "
                                 f"{prop['resolved_target_type'] or 'record'} instead of rejecting it")
    reason = b.reason if b else None
    ts = now_utc()
    with conn:
        conn.execute("UPDATE extraction_proposals SET status='rejected', rejection_reason=?, "
                     "resolved_at=?, updated_at=? WHERE id=?", (reason, ts, ts, proposal_id))
        audit.record(conn, object_type="extraction_proposal", object_id=proposal_id, action="update",
                     after={"event": "proposal_rejected", "reason": reason})
    return {"proposal_id": proposal_id, "status": "rejected", "rejection_reason": reason}


def _resolve_existing(conn, prop, target_type, target_id, note=None):
    """Close a proposal against a record that already holds the fact. Writes nothing else.

    This is §6.7's "use existing". It is not an acceptance — no canonical record is created or
    patched — and it is not a rejection, because the source was right. Conflating it with either
    is how a review queue starts lying: a rejection says the source was wrong, and an acceptance
    would put a second record in the account saying the same thing.
    """
    ts = now_utc()
    with conn:
        conn.execute(
            "UPDATE extraction_proposals SET status='resolved_existing', resolved_target_type=?, "
            "resolved_target_id=?, resolved_at=?, updated_at=? WHERE id=?",
            (target_type, target_id, ts, ts, prop["id"]))
        audit.record(conn, object_type="extraction_proposal", object_id=prop["id"], action="update",
                     after={"event": "proposal_resolved_existing", "target_type": target_type,
                            "target_id": target_id, "note": note})


@router.post("/extraction/proposals/{proposal_id}/resolve-existing")
def resolve_existing(proposal_id: str, b: ProposalResolveExisting,
                     conn: sqlite3.Connection = Depends(get_conn)):
    """"Use existing" (§6.7): the source was right, a record already says it."""
    prop = conn.execute("SELECT * FROM extraction_proposals WHERE id=?", (proposal_id,)).fetchone()
    if not prop:
        raise HTTPException(404, "proposal not found")
    if prop["status"] != "proposed":
        raise HTTPException(409, f"proposal already {prop['status']}")
    target_type = b.target_type or prop["target_type"]
    if target_type != prop["target_type"]:
        raise HTTPException(422, f"this proposal is about a {prop['target_type']}, not a {target_type}")
    run = repo.get_row(conn, "extraction_runs", prop["run_id"])
    _require_same_scope(conn, target_type, b.target_id, run)
    _resolve_existing(conn, prop, target_type, b.target_id, note=b.note)
    return {"proposal_id": proposal_id, "status": "resolved_existing",
            "resolved_target_type": target_type, "resolved_target_id": b.target_id}


@router.post("/extraction/proposals/{proposal_id}/supersede")
def supersede_proposal(proposal_id: str, b: ProposalSupersede,
                       conn: sqlite3.Connection = Depends(get_conn)):
    """Replace this proposal with a newer one over the same material (§6.7).

    The replacement must still be open and must be about the same target type, and a proposal
    cannot supersede itself. Superseding never touches canonical records — it retires one draft in
    favour of another, which is why an already-accepted proposal cannot be superseded: the record
    it wrote would be left behind with nothing pointing at it.
    """
    prop = conn.execute("SELECT * FROM extraction_proposals WHERE id=?", (proposal_id,)).fetchone()
    if not prop:
        raise HTTPException(404, "proposal not found")
    if prop["status"] != "proposed":
        raise HTTPException(409, f"proposal already {prop['status']}")
    if b.superseded_by_id == proposal_id:
        raise HTTPException(422, "a proposal cannot supersede itself")
    newer = conn.execute("SELECT * FROM extraction_proposals WHERE id=?", (b.superseded_by_id,)).fetchone()
    if not newer:
        raise HTTPException(404, "the superseding proposal was not found")
    if newer["status"] != "proposed":
        raise HTTPException(409, f"the superseding proposal is already {newer['status']}")
    if newer["target_type"] != prop["target_type"]:
        raise HTTPException(422, "a proposal can only be superseded by one about the same target type")
    run, newer_run = (repo.get_row(conn, "extraction_runs", p["run_id"]) for p in (prop, newer))
    if run.get("account_id") != newer_run.get("account_id"):
        raise HTTPException(422, "the superseding proposal belongs to a different account")
    ts = now_utc()
    with conn:
        conn.execute("UPDATE extraction_proposals SET status='superseded', superseded_by_id=?, "
                     "rejection_reason=?, resolved_at=?, updated_at=? WHERE id=?",
                     (b.superseded_by_id, b.reason, ts, ts, proposal_id))
        audit.record(conn, object_type="extraction_proposal", object_id=proposal_id, action="update",
                     after={"event": "proposal_superseded", "by": b.superseded_by_id, "reason": b.reason})
    return {"proposal_id": proposal_id, "status": "superseded", "superseded_by_id": b.superseded_by_id}


@router.get("/extraction/proposals/{proposal_id}/review")
def proposal_review_context(proposal_id: str, conn: sqlite3.Connection = Depends(get_conn)):
    """Everything a reviewer needs before deciding: the normalized proposal, deterministic match
    candidates, and — for an update — the conflict preview. Read-only, and nothing here ranks or
    pre-selects a resolution."""
    prop = conn.execute("SELECT * FROM extraction_proposals WHERE id=?", (proposal_id,)).fetchone()
    if not prop:
        raise HTTPException(404, "proposal not found")
    run = repo.get_row(conn, "extraction_runs", prop["run_id"])
    row = repo.row_to_dict(prop)
    return {
        "proposal": proposals_mod.normalized(row, run),
        "match_candidates": proposal_review.match_candidates(conn, prop, run),
        "conflict": proposal_review.conflict_preview(conn, prop, run),
        "resolutions": ["accept", "edit_and_accept", "reject", "use_existing", "supersede"],
    }


@router.get("/extraction/proposals/{proposal_id}/grounding")
def proposal_grounding(proposal_id: str, full: bool = False,
                       conn: sqlite3.Connection = Depends(get_conn)):
    """ACCOUNT-INTAKE-SPEC.md §11.2 — the quote, the retained source around it, and what is missing.

    Its own endpoint rather than a field on `/review`, because a snapshot can be the full 1 MB cap
    and most proposals are decided without ever opening the source pane. Fetched when the pane opens.
    """
    return proposal_grounding_mod.grounding(conn, proposal_id, full=full)


@router.get("/accounts/{account_id}/proposed-updates")
def account_proposed_updates(account_id: str,
                             program_id: str | None = None,
                             source_interaction_id: str | None = None,
                             run_id: str | None = None,
                             status: str = "proposed",
                             conn: sqlite3.Connection = Depends(get_conn)):
    """§7.2 — the account's proposals grouped by source and target type.

    Manual capture items ride along in their own list so the UI can offer one combined review
    experience (§0.5) without either store being copied into the other.

    `run_id` narrows to one run (§11.4). It is a filter on the one queue, not a second queue: the
    same composition, the same commands, and the account's other pending work is stated as withheld
    rather than silently absent — the D-160 rule that a subtractive response always says so.
    """
    try:
        return proposal_read.proposed_updates(
            conn, account_id, program_id=program_id, source_interaction_id=source_interaction_id,
            run_id=run_id, status=status)
    except ValueError as e:
        # The cross-account run id. It surfaces as a refusal rather than an empty list, because an
        # empty list would read as "this source has nothing pending" about a source that is not
        # this account's to report on at all.
        raise HTTPException(422, str(e))


@router.get("/accounts/{account_id}/proposed-updates/preview")
def account_proposal_preview(account_id: str, program_id: str | None = None, limit: int = 3,
                             conn: sqlite3.Connection = Depends(get_conn)):
    """§8.1 — up to three proposals from the latest source, plus the full scoped pending count."""
    return proposal_read.latest_source_preview(
        conn, account_id, program_id=program_id, limit=min(max(limit, 0), 3))


def _require_same_scope(conn, target_type, target_id, run):
    """§6.8: cross-account or cross-program targets are rejected, always, before any write."""
    table = proposal_review._TABLE.get(target_type)
    if not table:
        raise HTTPException(422, f"'{target_type}' is not a resolvable proposal target")
    row = conn.execute(f"SELECT * FROM {table} WHERE id=?", (target_id,)).fetchone()
    if not row:
        raise HTTPException(404, f"{target_type} {target_id} not found")
    keys = row.keys()
    if "account_id" in keys and run.get("account_id") and row["account_id"] != run["account_id"]:
        raise HTTPException(422, "that record belongs to a different account")
    if "program_id" in keys and run.get("program_id") and row["program_id"] not in (None, run["program_id"]):
        raise HTTPException(422, "that record belongs to a different program")
    if "account_id" not in keys and "program_id" in keys and row["program_id"] != run.get("program_id"):
        # Program-only tables (tasks, risks, issues, moments) have no other way to prove the
        # account matches, so an exact program match is the only safe answer.
        raise HTTPException(422, "that record belongs to a different program")
    return row


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
