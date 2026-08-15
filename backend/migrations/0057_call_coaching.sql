-- Migration 0057 — Stage 18: private, evidence-grounded personal call coaching.
--
-- Coaching is deliberately its own private domain. None of these tables is read by account
-- readiness, the Ledger, search, exports, QBR, MAP, or client-facing generators. When a call also
-- contains account facts, those facts enter the existing extraction_runs/extraction_proposals
-- workflow; coaching observations never become canonical account records.
--
-- Deliberate absences: no score, confidence, sentiment, emotion, personality, quality index,
-- leaderboard, sharing, or manager-assignment columns. Longitudinal views derive counts over
-- comparable observations rather than storing a second skill-state authority.
PRAGMA foreign_keys = ON;

CREATE TABLE coaching_sessions (
    id                    TEXT PRIMARY KEY,
    mode                  TEXT NOT NULL CHECK (mode IN ('review','rehearsal')),
    parent_session_id     TEXT REFERENCES coaching_sessions(id),
    -- Forward reference is valid in SQLite and preserves the exact reviewed moment a practice
    -- session came from. It is nullable because Coach home also starts standalone practice.
    origin_observation_id TEXT REFERENCES coaching_observations(id),
    account_id            TEXT REFERENCES accounts(id),
    program_id            TEXT REFERENCES programs(id),
    interaction_id        TEXT REFERENCES interactions(id),
    title                 TEXT NOT NULL,
    call_type             TEXT NOT NULL,
    call_date             TEXT,
    intended_outcome      TEXT NOT NULL,
    coaching_focus        TEXT,
    coached_speaker_key   TEXT,
    speaker_status        TEXT NOT NULL CHECK (speaker_status IN
                              ('confirmed_by_operator','unknown','not_applicable')),
    reflection_worked     TEXT,
    reflection_difficult  TEXT,
    reflection_outcome    TEXT,
    reflection_change     TEXT,
    created_by            TEXT NOT NULL,
    created_at            TEXT NOT NULL,
    updated_at            TEXT NOT NULL,
    archived              INTEGER NOT NULL DEFAULT 0 CHECK (archived IN (0,1)),
    archived_at           TEXT,
    archived_by           TEXT,
    CHECK (length(title) BETWEEN 1 AND 240),
    CHECK (length(intended_outcome) BETWEEN 1 AND 2000)
);

CREATE TABLE coaching_sources (
    id                  TEXT PRIMARY KEY,
    session_id          TEXT NOT NULL UNIQUE REFERENCES coaching_sessions(id),
    source_kind         TEXT NOT NULL CHECK (source_kind IN
                            ('paste','notes','script','txt','md','vtt','srt','practice_transcript')),
    filename            TEXT,
    byte_length         INTEGER NOT NULL CHECK (byte_length >= 0),
    content_hash        TEXT NOT NULL,
    snapshot_text       TEXT,
    snapshot_deleted_at TEXT,
    snapshot_deleted_by TEXT,
    created_at          TEXT NOT NULL,
    updated_at          TEXT NOT NULL
);

CREATE INDEX idx_coaching_sources_hash ON coaching_sources(content_hash);

CREATE TABLE coaching_runs (
    id                            TEXT PRIMARY KEY,
    session_id                    TEXT NOT NULL REFERENCES coaching_sessions(id),
    job_id                        TEXT REFERENCES jobs(id),
    -- Optional bridge to the one existing account-fact proposal store.
    extraction_run_id             TEXT REFERENCES extraction_runs(id),
    source_content_hash           TEXT NOT NULL,
    contract_version              TEXT NOT NULL,
    rubric_key                    TEXT NOT NULL,
    rubric_version                INTEGER NOT NULL,
    extractor_backend             TEXT,
    model_version                 TEXT NOT NULL,
    prompt_version                TEXT NOT NULL,
    status                        TEXT NOT NULL CHECK (status IN
                                      ('queued','running','completed','partial','failed')),
    summary                       TEXT,
    account_context_snapshot_json TEXT,
    account_lens_json             TEXT,
    practice_json                 TEXT,
    coverage_json                 TEXT,
    error_json                    TEXT,
    created_at                    TEXT NOT NULL,
    updated_at                    TEXT NOT NULL,
    finished_at                   TEXT
);

CREATE INDEX idx_coaching_runs_session ON coaching_runs(session_id, created_at);
CREATE INDEX idx_coaching_runs_job ON coaching_runs(job_id);

CREATE TABLE coaching_observations (
    id                  TEXT PRIMARY KEY,
    run_id              TEXT NOT NULL REFERENCES coaching_runs(id),
    kind                TEXT NOT NULL CHECK (kind IN ('strength','opportunity')),
    skill_key           TEXT NOT NULL,
    headline            TEXT NOT NULL,
    situation           TEXT NOT NULL,
    behavior            TEXT NOT NULL,
    impact_type         TEXT NOT NULL CHECK (impact_type IN ('observed','inferred')),
    impact_text         TEXT NOT NULL,
    alternative         TEXT NOT NULL,
    source_span         TEXT NOT NULL,
    source_start        INTEGER NOT NULL,
    source_end          INTEGER NOT NULL,
    source_timestamp    TEXT,
    source_speaker_key  TEXT,
    is_top_priority     INTEGER NOT NULL DEFAULT 0 CHECK (is_top_priority IN (0,1)),
    ordinal             INTEGER NOT NULL,
    operator_response   TEXT CHECK (operator_response IN ('useful','inaccurate','dismissed')),
    operator_note       TEXT,
    created_at          TEXT NOT NULL,
    updated_at          TEXT NOT NULL,
    CHECK (source_start >= 0 AND source_end > source_start)
);

CREATE INDEX idx_coaching_observations_run ON coaching_observations(run_id, ordinal);
CREATE UNIQUE INDEX uq_coaching_top_priority
ON coaching_observations(run_id) WHERE is_top_priority=1;

CREATE TABLE coaching_goals (
    id                    TEXT PRIMARY KEY,
    source_observation_id TEXT NOT NULL REFERENCES coaching_observations(id),
    skill_key             TEXT NOT NULL,
    behavior              TEXT NOT NULL,
    status                TEXT NOT NULL CHECK (status IN
                              ('active','completed','replaced','abandoned')),
    revisit_after         TEXT,
    completed_at          TEXT,
    created_by            TEXT NOT NULL,
    created_at            TEXT NOT NULL,
    updated_at            TEXT NOT NULL
);

CREATE UNIQUE INDEX uq_coaching_active_goal
ON coaching_goals(status) WHERE status='active';
CREATE INDEX idx_coaching_goals_observation ON coaching_goals(source_observation_id);
