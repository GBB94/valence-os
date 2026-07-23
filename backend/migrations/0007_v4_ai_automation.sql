-- Migration 0007 — v4 AI & automation
-- Transcript extraction (Section 3 security model), the plays trigger engine with
-- effectiveness notes, and notifications. The extractor is a deterministic LOCAL mock
-- behind a swappable interface: no browsing/tools/outbound; strict validated mutation
-- schema; nothing writes without per-item human acceptance; every proposal carries a
-- source span; model + prompt versions are recorded; document content is data, not
-- instructions.

PRAGMA foreign_keys = ON;

-- One extraction run over a pasted/uploaded transcript.
CREATE TABLE extraction_runs (
    id             TEXT PRIMARY KEY,
    account_id     TEXT REFERENCES accounts(id),
    program_id     TEXT REFERENCES programs(id),
    interaction_id TEXT REFERENCES interactions(id),
    model_version  TEXT NOT NULL,        -- recorded for provenance (e.g. "mock-extractor-1")
    prompt_version TEXT NOT NULL,
    transcript_chars INTEGER,
    status         TEXT NOT NULL DEFAULT 'proposed' CHECK (status IN ('proposed','applied','discarded')),
    created_at     TEXT NOT NULL,
    updated_at     TEXT NOT NULL
);

-- Each proposed mutation. Strictly one of a predefined set; nothing writes until accepted.
CREATE TABLE extraction_proposals (
    id                TEXT PRIMARY KEY,
    run_id            TEXT NOT NULL REFERENCES extraction_runs(id),
    mutation_type     TEXT NOT NULL CHECK (mutation_type IN
                      ('create_commitment','create_risk','create_decision','create_task','create_issue')),
    payload_json      TEXT NOT NULL,      -- validated predefined shape
    source_span       TEXT,               -- the transcript span the proposal came from
    confidence        TEXT,
    status            TEXT NOT NULL DEFAULT 'proposed' CHECK (status IN ('proposed','accepted','rejected')),
    created_object_type TEXT,
    created_object_id TEXT,
    created_at        TEXT NOT NULL,
    updated_at        TEXT NOT NULL
);
CREATE INDEX idx_proposals_run ON extraction_proposals(run_id, status);

-- Play definition: a predefined trigger-and-response.
CREATE TABLE play_definitions (
    id            TEXT PRIMARY KEY,
    name          TEXT NOT NULL,
    trigger_kind  TEXT NOT NULL CHECK (trigger_kind IN
                  ('renewal_window','overdue_commitment','stale_stakeholder','active_blocker')),
    action_template TEXT NOT NULL,        -- what the play tells the operator to do
    active        INTEGER NOT NULL DEFAULT 1,
    created_at    TEXT NOT NULL,
    updated_at    TEXT NOT NULL,
    archived      INTEGER NOT NULL DEFAULT 0,
    archived_at   TEXT,
    archived_by   TEXT
);

-- Play run: records a firing, its generated action, completion, and (v4) an
-- effectiveness note so the playbook improves rather than just automating.
CREATE TABLE play_runs (
    id              TEXT PRIMARY KEY,
    play_id         TEXT NOT NULL REFERENCES play_definitions(id),
    account_id      TEXT REFERENCES accounts(id),
    trigger_context TEXT,                 -- why it fired
    action_text     TEXT,                 -- the generated action
    status          TEXT NOT NULL DEFAULT 'fired' CHECK (status IN ('fired','completed','dismissed')),
    effectiveness   TEXT CHECK (effectiveness IN ('effective','unclear','ineffective')),
    effectiveness_note TEXT,
    dedupe_key      TEXT,                  -- prevents re-firing the same play for the same target
    fired_at        TEXT NOT NULL,
    completed_at    TEXT
);
CREATE INDEX idx_playruns_status ON play_runs(status);
CREATE UNIQUE INDEX idx_playruns_dedupe ON play_runs(dedupe_key) WHERE dedupe_key IS NOT NULL;

-- Notifications: actionable success/failure signals (jobs, plays, extraction).
CREATE TABLE notifications (
    id          TEXT PRIMARY KEY,
    kind        TEXT NOT NULL,
    message     TEXT NOT NULL,
    ref_type    TEXT,
    ref_id      TEXT,
    read        INTEGER NOT NULL DEFAULT 0,
    created_at  TEXT NOT NULL
);
CREATE INDEX idx_notifications_read ON notifications(read, created_at);
