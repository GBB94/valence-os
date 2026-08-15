-- Migration 0018 — Stage 5.5: the value realization ledger (EXPANSION-ENGINE-SPEC.md §2)
--
-- Promised-vs-realized as a record instead of a memory. Two naming/identity decisions are
-- load-bearing here:
--
--   1. These are VALUE TARGETS, not "value commitments". `commitments` already exists as an
--      execution promise (responsible party, internal owner, acknowledgement-based closure) —
--      a different record with a different lifecycle. Reusing the word would have collided in
--      the API, the UI, and every rollup.
--
--   2. A target names a POPULATION, and the population must be a stable reference. Today
--      metric_observations.cohort_label is free text, which cannot be joined to a target
--      reliably, so realization was not computable at all. population_segment_id (added below)
--      is what makes the ledger work.
--
-- Targets are VERSIONED: a renegotiated bar supersedes rather than overwrites, because
-- "we hit the target" is only meaningful against the target that was actually agreed at the
-- time. Acceptance is a dated event with a named accepter, per the standing evidence rules.

PRAGMA foreign_keys = ON;

-- --- stable population identity on observations (§2) ---------------------------------------
-- Nullable and additive: existing observations keep their free-text cohort_label, and the
-- ledger simply cannot see them until they are re-pointed. Better a visible gap than a
-- fuzzy string match that silently attributes the wrong cohort's numbers to a target.
ALTER TABLE metric_observations ADD COLUMN population_segment_id TEXT REFERENCES population_segments(id);
ALTER TABLE metric_observations ADD COLUMN population_view_id    TEXT REFERENCES population_views(id);
CREATE INDEX idx_obs_segment ON metric_observations(population_segment_id, current_through);

-- --- value targets --------------------------------------------------------------------------
CREATE TABLE value_targets (
    id              TEXT PRIMARY KEY,
    account_id      TEXT NOT NULL REFERENCES accounts(id),
    definition_id   TEXT NOT NULL REFERENCES metric_definitions(id),

    -- The population the bar applies to: a base segment, a composite view, or account-wide
    -- (both NULL). Not a string — see the header note.
    segment_id      TEXT REFERENCES population_segments(id),
    view_id         TEXT REFERENCES population_views(id),

    target_value    REAL NOT NULL,
    unit            TEXT,
    -- Direction matters: "response time under 24h" and "activation above 70%" are both targets
    -- and comparing them the same way gets one of them backwards.
    direction       TEXT NOT NULL DEFAULT 'at_least' CHECK (direction IN ('at_least','at_most')),
    timeframe_start TEXT,
    timeframe_end   TEXT NOT NULL,          -- the bar is only meaningful with a by-when

    -- Acceptance: who agreed, when, and where it came from.
    accepted_by_person_id TEXT REFERENCES persons(id),
    accepted_on     TEXT,
    origin          TEXT NOT NULL DEFAULT 'scorecard' CHECK (origin IN
                      ('scorecard','business_case','renewal','expansion','other')),
    source_interaction_id TEXT REFERENCES interactions(id),
    source_reference_id   TEXT REFERENCES source_references(id),

    -- Versioning: a renegotiated bar supersedes; both stay readable.
    version         INTEGER NOT NULL DEFAULT 1,
    supersedes_id   TEXT REFERENCES value_targets(id),
    status          TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active','superseded','withdrawn')),

    -- Negative evidence stays in (§2): a target the client declined to accept is recorded, not
    -- discarded, because a business case that ignores them gets dismantled in procurement.
    -- Internal-only by default; reaching a client artifact requires affirmative promotion.
    client_accepted INTEGER NOT NULL DEFAULT 0,
    not_accepted_reason TEXT,
    client_visible  INTEGER NOT NULL DEFAULT 0,

    notes           TEXT,
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL,
    archived        INTEGER NOT NULL DEFAULT 0,
    archived_at     TEXT,
    archived_by     TEXT,

    CHECK (segment_id IS NULL OR view_id IS NULL),
    -- Accepted means accepted BY someone ON a date; otherwise it is an aspiration.
    CHECK (client_accepted = 0 OR (accepted_by_person_id IS NOT NULL AND accepted_on IS NOT NULL))
);
CREATE INDEX idx_value_target_account ON value_targets(account_id, status);
CREATE INDEX idx_value_target_definition ON value_targets(definition_id);

-- Stories and observations that bear on a target. Realization status is DERIVED from
-- observations at read time (app/expansion.py:target_realization) — never stored, so it
-- cannot go stale as a carried-forward good state.
CREATE TABLE value_target_evidence (
    id          TEXT PRIMARY KEY,
    target_id   TEXT NOT NULL REFERENCES value_targets(id),
    object_type TEXT NOT NULL CHECK (object_type IN ('value_story','metric_observation')),
    object_id   TEXT NOT NULL,
    note        TEXT,
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);
CREATE UNIQUE INDEX idx_target_evidence ON value_target_evidence(target_id, object_type, object_id);
