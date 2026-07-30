-- Migration 0011 — Phase 3 job table (PHASE-3-SPEC.md §0b prerequisite)
-- A single in-process worker drains this table. Deliberately boring: one table, no
-- external queue (CLAUDE.md "keep it boring"; the dataset is a few thousand rows).
-- Background work in Phase 3 — transcription, email sync, association runs, scheduled
-- generation — enqueues here and a worker thread runs registered handlers by `kind`.
-- Routine edits and navigation stay synchronous and instant; only long/scheduled work
-- goes through jobs.

PRAGMA foreign_keys = ON;

CREATE TABLE jobs (
    id            TEXT PRIMARY KEY,
    kind          TEXT NOT NULL,          -- registered handler name (e.g. 'transcribe_recording')
    payload_json  TEXT,                   -- handler input args (validated by the handler)
    status        TEXT NOT NULL DEFAULT 'queued'
                  CHECK (status IN ('queued','running','succeeded','failed','cancelled')),
    attempts      INTEGER NOT NULL DEFAULT 0,
    max_attempts  INTEGER NOT NULL DEFAULT 1,
    result_json   TEXT,                   -- handler return value on success
    error         TEXT,                   -- message on failure (last attempt)
    scheduled_for TEXT,                   -- ISO-8601 UTC; NULL = run as soon as a worker is free
    account_id    TEXT REFERENCES accounts(id),  -- optional association for filtering/notifications
    created_at    TEXT NOT NULL,
    updated_at    TEXT NOT NULL,
    started_at    TEXT,
    finished_at   TEXT
);

-- The worker claims the oldest due, queued job; this index serves that scan.
CREATE INDEX idx_jobs_claim ON jobs(status, scheduled_for, created_at);
CREATE INDEX idx_jobs_account ON jobs(account_id);
