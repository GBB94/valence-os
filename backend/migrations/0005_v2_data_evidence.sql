-- Migration 0005 — v2 data & evidence
-- Metric definitions (Data-team owned; ingested, never recomputed) + observations,
-- versioned/sourced benchmarks (NO hard-coded numbers), the value-story library with
-- evidence tiers, visibility classes, and negative evidence, and import batches with
-- rollback. The QBR generator and operations screen are derived (no tables).

PRAGMA foreign_keys = ON;

-- Metric definition: owned by the Data team; the tool ingests, it does not recompute.
CREATE TABLE metric_definitions (
    id             TEXT PRIMARY KEY,
    name           TEXT NOT NULL,
    meaning        TEXT,
    source_system  TEXT,                 -- canonical owner (e.g. "Valence Data team")
    owner          TEXT,
    version        TEXT NOT NULL DEFAULT '1',
    population     TEXT,
    formula_notes  TEXT,                 -- optional (Section 11: rest of the 15-field schema deferred)
    stale_after_days INTEGER NOT NULL DEFAULT 30,   -- freshness threshold; past it, dependents render unknown
    created_at     TEXT NOT NULL,
    updated_at     TEXT NOT NULL,
    archived       INTEGER NOT NULL DEFAULT 0,
    archived_at    TEXT,
    archived_by    TEXT
);

-- Metric observation: a value for a definition version, program/cohort, and period.
-- current_through drives freshness; import_batch_id ties it to an ingest for rollback.
CREATE TABLE metric_observations (
    id                  TEXT PRIMARY KEY,
    definition_id       TEXT NOT NULL REFERENCES metric_definitions(id),
    definition_version  TEXT NOT NULL,
    program_id          TEXT REFERENCES programs(id),
    cohort_label        TEXT,
    period_label        TEXT,             -- e.g. "2026-06"
    value               REAL,
    unit                TEXT,
    target              REAL,             -- optional target for the scoreboard
    current_through     TEXT,             -- date the data is current through (freshness)
    source_reference_id TEXT REFERENCES source_references(id),
    import_batch_id     TEXT,             -- REFERENCES import_batches(id) (declared below)
    created_at          TEXT NOT NULL,
    updated_at          TEXT NOT NULL,
    archived            INTEGER NOT NULL DEFAULT 0,   -- rollback archives observations, never deletes
    archived_at         TEXT,
    archived_by         TEXT
);
CREATE INDEX idx_obs_def ON metric_observations(definition_id, current_through);
CREATE INDEX idx_obs_program ON metric_observations(program_id);
CREATE INDEX idx_obs_batch ON metric_observations(import_batch_id);

-- Benchmark: a versioned, sourced claim with population and period. Never hard-coded.
CREATE TABLE benchmarks (
    id                  TEXT PRIMARY KEY,
    name                TEXT NOT NULL,
    value               REAL,
    unit                TEXT,
    population          TEXT NOT NULL,    -- who it applies to
    period              TEXT NOT NULL,    -- when it was measured
    source              TEXT NOT NULL,    -- where the claim comes from
    version             TEXT NOT NULL DEFAULT '1',
    source_reference_id TEXT REFERENCES source_references(id),
    created_at          TEXT NOT NULL,
    updated_at          TEXT NOT NULL,
    archived            INTEGER NOT NULL DEFAULT 0,
    archived_at         TEXT,
    archived_by         TEXT
);

-- Value story: outcome + evidence tier + visibility class. Captures NEGATIVE evidence too
-- (objections, reservations, adoption friction, failed interventions, declined populations).
CREATE TABLE value_stories (
    id                  TEXT PRIMARY KEY,
    account_id          TEXT REFERENCES accounts(id),
    program_id          TEXT REFERENCES programs(id),
    outcome             TEXT NOT NULL,
    tags                TEXT,
    evidence_tier       TEXT NOT NULL DEFAULT 'anecdote'
        CHECK (evidence_tier IN ('anecdote','client_quote','measured_operational','correlated_business')),
    -- inherited safe default is internal-only; must be affirmatively promoted for client-facing use
    visibility_class    TEXT NOT NULL DEFAULT 'internal'
        CHECK (visibility_class IN ('internal','client_working','qbr_exec','externally_referenceable')),
    identifiable        INTEGER NOT NULL DEFAULT 0,   -- identifiable vs anonymized
    is_negative         INTEGER NOT NULL DEFAULT 0,   -- negative evidence (never client-facing)
    source_reference_id TEXT REFERENCES source_references(id),
    created_at          TEXT NOT NULL,
    updated_at          TEXT NOT NULL,
    archived            INTEGER NOT NULL DEFAULT 0,
    archived_at         TEXT,
    archived_by         TEXT
);
CREATE INDEX idx_value_account ON value_stories(account_id, visibility_class);

-- Import batch: the common adapter contract (validate, preview, dedupe, idempotent,
-- record batch, rollback, report freshness). Rollback archives the batch's observations.
CREATE TABLE import_batches (
    id             TEXT PRIMARY KEY,
    adapter        TEXT NOT NULL,        -- e.g. "csv_metric_observations"
    source_label   TEXT,
    status         TEXT NOT NULL DEFAULT 'committed'
        CHECK (status IN ('previewed','committed','rolled_back')),
    row_count      INTEGER NOT NULL DEFAULT 0,
    current_through TEXT,                -- freshness reported by the source
    notes          TEXT,
    created_at     TEXT NOT NULL,
    committed_at   TEXT,
    rolled_back_at TEXT
);
