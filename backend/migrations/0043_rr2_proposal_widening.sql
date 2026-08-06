-- Migration 0043 — RR-2.0: widen the canonical proposal tables.
--
-- RELATIONSHIP-READINESS-SPEC.md §6. §6.1 settles the shape before any column exists: widen
-- `extraction_runs` and `extraction_proposals`; do NOT add parallel `intake_runs`/`intake_items`,
-- and do NOT hang proposal payloads off `capture_inbox_items`. A second proposal persistence model
-- is the failure this slice exists to prevent, so this file adds no new table at all — every
-- column below lands on one of the two tables that already hold proposals.
--
-- Five rules shape the columns, and each one rejects a more obvious design:
--
--   * **Intent is separate from target.** `mutation_type` fused "what to do" with "what to do it
--     to", which is why it could only ever create. `intent` (§6.2) and `target_type` (§6.3) split
--     them, so an `update` to an existing Task is expressible without inventing an
--     `update_task_owner` verb per field. `mutation_type` stays, populated, because §6.5 requires
--     the legacy contract readable until every reader is normalized — `Extraction.jsx` still is not.
--   * **`intent` gets a CHECK; `target_type` deliberately does not.** The intent vocabulary is
--     closed at five values by the specification. The target allowlist is not: §6.3 grows it, and
--     Slice 5 adds link/close targets. So the allowlist lives in Python next to the native write
--     path that must exist for a target to be legal at all — a row *configures* an allowlisted
--     target and can never *create* one, the same rule 0041 applies to readiness evaluators. A
--     SQL CHECK here would let a migration widen the allowlist without a write path behind it.
--   * **No proposal may set a readiness state.** There is no `pillar`, `requirement_key`,
--     `state`, `composite_status`, or `phase` column, and `target_type` is not free to name one
--     because the Python allowlist omits them (§6.3, closing paragraph). Readiness is a query-time
--     projection; a proposal that could write one would fabricate evidence.
--   * **Counts are derived, never stored.** §6.5 suggests counts on the run. They are not here.
--     A stored `proposal_count`/`accepted_count` drifts from the rows it counts the moment one is
--     resolved outside the counter's path — the second-source-of-truth defect D-141 and D-143
--     already rejected one level up. `error_json` and `coverage_json` DO land, because an
--     adapter's own failure report is a fact it observed and nothing downstream can recompute it.
--   * **Two identities, not one.** §6.6: `external_id` alone is insufficient, because a provider
--     item can be corrected, retranscribed, or reprocessed with a new extractor. The run carries
--     a source-version identity (provider + external id + content hash + source kind) and each
--     proposal carries a fingerprint over normalized intent, target, payload, span/locator, and
--     extractor version. Both are plain columns on the existing tables for the same reason as
--     above: an identity table would be the second persistence model §6.1 forbids.
--
-- `created_object_type`/`created_object_id` are renamed to `resolved_target_*`. "created" is a lie
-- for an `update`, a `resolved_existing`, or a `no_change`, and this is the last moment the rename
-- is cheap — exactly two readers exist, both in `app/routers/ai.py`.
--
-- Every existing row survives with a deterministic backfill. Mock-only data throughout.
--
-- Both tables are rebuilt, and `extraction_proposals` FKs into `extraction_runs`, so the parent
-- cannot be dropped with enforcement on. Same bracket as 0034 and 0038: enforcement off around an
-- explicit transaction, back on at the end.
PRAGMA foreign_keys = OFF;
BEGIN;

-- --- extraction_runs: provenance, source-version identity, adapter outcome ----------------------
-- SQLite cannot alter a CHECK in place, and `status` must widen to the §6.5 run lifecycle while
-- still accepting the three legacy values every existing row holds. Rebuild. `extraction_proposals`
-- FKs into this table, so it is rebuilt first and the proposal rebuild below re-points at it.
CREATE TABLE extraction_runs_new (
    id                  TEXT PRIMARY KEY,
    account_id          TEXT REFERENCES accounts(id),
    program_id          TEXT REFERENCES programs(id),
    interaction_id      TEXT REFERENCES interactions(id),

    -- Where the material came from. `source_reference_id` is the §6.1 reuse: provenance keeps
    -- living in source_references rather than growing a parallel provenance model here.
    source_kind         TEXT NOT NULL DEFAULT 'transcript' CHECK (source_kind IN (
                          'transcript','interaction','email','meeting','document','manual','other')),
    provider            TEXT,
    external_id         TEXT,
    content_hash        TEXT,
    -- provider|external_id|content_hash|source_kind, composed by the writer. Stored rather than
    -- computed in every query so the idempotency lookup is one indexed equality test.
    source_version_key  TEXT,
    source_reference_id TEXT REFERENCES source_references(id),

    extractor_backend   TEXT,
    model_version       TEXT NOT NULL,
    prompt_version      TEXT NOT NULL,
    transcript_chars    INTEGER,

    -- 'proposed'/'applied'/'discarded' are the pre-RR-2 review states and are kept verbatim so
    -- existing rows and the existing endpoints stay valid. The four new values are the adapter
    -- lifecycle §6.5 asks for. 'partial' and 'failed' are distinct because a partial run still
    -- produced proposals worth reviewing and a failed one did not.
    status              TEXT NOT NULL DEFAULT 'proposed' CHECK (status IN (
                          'proposed','applied','discarded','running','completed','partial','failed')),
    -- What the adapter itself reported. Not recomputable, so not derived.
    error_json          TEXT,
    coverage_json       TEXT,

    created_at          TEXT NOT NULL,
    updated_at          TEXT NOT NULL
);
INSERT INTO extraction_runs_new (
    id, account_id, program_id, interaction_id, source_kind, extractor_backend,
    model_version, prompt_version, transcript_chars, status, created_at, updated_at)
SELECT id, account_id, program_id, interaction_id,
       'transcript',
       -- Only three producers have ever written a run, and each stamped a distinguishable
       -- model_version, so the backend is recoverable rather than guessed.
       CASE WHEN model_version = 'manual-local-llm' THEN 'manual'
            WHEN model_version LIKE 'mock-%'        THEN 'mock'
            ELSE 'api' END,
       model_version, prompt_version, transcript_chars, status, created_at, updated_at
FROM extraction_runs;
DROP TABLE extraction_runs;
ALTER TABLE extraction_runs_new RENAME TO extraction_runs;
CREATE INDEX idx_extraction_runs_account ON extraction_runs(account_id, created_at);
-- Not UNIQUE: the same source version may legitimately be re-extracted by a newer extractor, and
-- §6.6 resolves that at the proposal fingerprint, not by refusing the run.
CREATE INDEX idx_extraction_runs_source_version ON extraction_runs(source_version_key);

-- --- extraction_proposals: the normalized §6.4 contract -----------------------------------------
CREATE TABLE extraction_proposals_new (
    id                  TEXT PRIMARY KEY,
    run_id              TEXT NOT NULL REFERENCES extraction_runs(id),

    -- §6.2. 'link' and 'close' are accepted by the CHECK but rejected by the Python allowlist
    -- until the typed relationship and governed closure contracts of Account Path Slice 5 exist:
    -- the vocabulary is fixed by the specification, the enabled subset is not.
    intent              TEXT NOT NULL DEFAULT 'create' CHECK (intent IN (
                          'create','update','link','close','no_change')),
    -- §6.3. Allowlisted in Python, deliberately not here — see the header.
    target_type         TEXT NOT NULL,
    target_id           TEXT,
    -- Optimistic concurrency for updates (§6.7). A proposal that carries the target's updated_at
    -- from when it was drafted returns a conflict preview instead of overwriting newer state.
    expected_target_updated_at TEXT,

    -- Legacy contract. Retained and populated per §6.5 until every reader is normalized. Nullable
    -- because a normalized pair the old enum has no name for must not invent one: the old UI
    -- reading a plausible-but-wrong verb is worse than reading nothing.
    mutation_type       TEXT CHECK (mutation_type IS NULL OR mutation_type IN (
                          'create_commitment','create_risk','create_decision','create_task','create_issue',
                          'fill_placeholder','log_pull_signal','create_deployment_moment','create_value_story')),

    payload_json        TEXT NOT NULL,
    source_reference_id TEXT REFERENCES source_references(id),
    source_span         TEXT,
    source_locator      TEXT,
    -- §6.6 second identity. Not UNIQUE: a repeat is a match candidate the reviewer resolves
    -- (§6.7), not a write the database silently refuses.
    proposal_fingerprint TEXT,

    -- Explanatory metadata only. It never auto-accepts, never ranks above canonical work, and
    -- never relaxes validation (§6.4, closing line).
    confidence          TEXT,
    validation_warnings_json TEXT,

    -- §6.5 resolution set. 'resolved_existing' records that the reviewer pointed the proposal at a
    -- record that already said this; 'superseded' that a newer proposal replaced it. Neither is a
    -- rejection, and neither wrote a new canonical record.
    status              TEXT NOT NULL DEFAULT 'proposed' CHECK (status IN (
                          'proposed','accepted','rejected','resolved_existing','superseded')),
    rejection_reason    TEXT,
    superseded_by_id    TEXT REFERENCES extraction_proposals(id),
    -- Renamed from created_object_*: an update or a use-existing resolves a target it did not create.
    resolved_target_type TEXT,
    resolved_target_id  TEXT,
    resolved_at         TEXT,

    created_at          TEXT NOT NULL,
    updated_at          TEXT NOT NULL
);
INSERT INTO extraction_proposals_new (
    id, run_id, intent, target_type, mutation_type, payload_json, source_span, confidence,
    status, resolved_target_type, resolved_target_id, resolved_at, created_at, updated_at)
SELECT id, run_id,
       -- Backfilled from the verb half of mutation_type. fill_placeholder is the one existing
       -- mutation that patches a record it did not create, so it is the one 'update'.
       CASE WHEN mutation_type = 'fill_placeholder' THEN 'update' ELSE 'create' END,
       -- Backfilled from the target half. These are exactly the targets the accept paths in
       -- app/routers/ai.py already write, so no row gains a target the app cannot honour.
       CASE mutation_type
            WHEN 'create_commitment'        THEN 'commitment'
            WHEN 'create_risk'              THEN 'risk'
            WHEN 'create_decision'          THEN 'decision'
            WHEN 'create_task'              THEN 'task'
            WHEN 'create_issue'             THEN 'issue'
            WHEN 'fill_placeholder'         THEN 'person'
            WHEN 'log_pull_signal'          THEN 'pull_signal'
            WHEN 'create_deployment_moment' THEN 'deployment_moment'
            WHEN 'create_value_story'       THEN 'value_story'
       END,
       mutation_type, payload_json, source_span, confidence, status,
       created_object_type, created_object_id,
       -- An already-accepted row resolved at its last update; nothing else has resolved.
       CASE WHEN status = 'accepted' THEN updated_at ELSE NULL END,
       created_at, updated_at
FROM extraction_proposals;
DROP TABLE extraction_proposals;
ALTER TABLE extraction_proposals_new RENAME TO extraction_proposals;
CREATE INDEX idx_proposals_run ON extraction_proposals(run_id, status);
CREATE INDEX idx_proposals_fingerprint ON extraction_proposals(proposal_fingerprint);
CREATE INDEX idx_proposals_target ON extraction_proposals(target_type, target_id);

COMMIT;
PRAGMA foreign_keys = ON;
