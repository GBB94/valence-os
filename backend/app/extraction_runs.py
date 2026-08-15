"""The one extraction-run / proposal persistence service.

Every path that turns a source into proposals — transcript extraction, manual paste, the account
drop zone, `.eml` ingestion, Call Coach's draft-account-updates bridge, and the seed's demo run —
lands here. There is exactly one `extraction_runs` + `extraction_proposals` store (RR-2, D-145/
D-146), and this module is its only writer, so a new input adapter cannot quietly create a second
proposal store or a second acceptance path.

This used to live on the AI router as `_persist_run`, which put the dependency arrow backwards:
domain modules (`intake_drop`, `ingestion`, `coaching`) were importing a private function from
`app.routers`. Persistence is domain behavior; the router now calls down into this service like
every other caller, and an architecture test pins the direction (no domain module imports from
`app.routers`).
"""
from __future__ import annotations

import json

from . import audit, extractor
from . import proposal_review
from . import proposals as proposals_mod
from .db import new_id, now_utc


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


def persist_run(conn, *, account_id, program_id, interaction_id, model_version, prompt_version,
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
