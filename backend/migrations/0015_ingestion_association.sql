-- Migration 0015 — Phase 3 Stage 4: communications ingestion + association (Comprehensive Spec Part 4)
--   §4.2 comm_messages: lightweight email records threaded onto the ledger, link-first (the
--        one-line summary is the working record; the body stays behind a source reference).
--   §4.3 priority flagging lives on the comm record (needs_response + reason); the queue derives
--        the "unanswered past threshold" attention item.
--   §4.5 association_hints: the shared association engine learns from manual corrections. Hints
--        are never hard-deleted — a correction supersedes by flipping active.
-- All sources are MOCK (fixture .eml + fixture transcripts). Real providers are a CONNECTIONS.md
-- switch (Part 6). Mock-only data.

PRAGMA foreign_keys = ON;

CREATE TABLE comm_messages (
    id                  TEXT PRIMARY KEY,
    account_id          TEXT REFERENCES accounts(id),   -- resolved (best guess); nullable if unresolved
    program_id          TEXT REFERENCES programs(id),
    direction           TEXT NOT NULL DEFAULT 'inbound' CHECK (direction IN ('inbound','outbound')),
    from_addr           TEXT,
    to_addrs            TEXT,                            -- comma-joined recipient addresses
    occurred_on         TEXT,                            -- date
    occurred_at         TEXT,                            -- timestamp if known (for hour-level flag age)
    subject             TEXT,
    summary             TEXT,                            -- one-line summary = the working record
    person_id           TEXT REFERENCES persons(id),     -- resolved counterpart (best match)
    confidence          REAL,                            -- association confidence 0..1 (shown, never hidden)
    needs_response      INTEGER NOT NULL DEFAULT 0,       -- §4.3 priority flag
    flag_reason         TEXT,
    responded           INTEGER NOT NULL DEFAULT 0,
    responded_on        TEXT,
    source_reference_id TEXT REFERENCES source_references(id),  -- link to the original .eml (link-first)
    external_id         TEXT,                            -- message-id / fixture name (dedupe)
    created_at          TEXT NOT NULL,
    updated_at          TEXT NOT NULL,
    archived            INTEGER NOT NULL DEFAULT 0,
    archived_at         TEXT,
    archived_by         TEXT
);
CREATE INDEX idx_comm_account ON comm_messages(account_id, occurred_on);
CREATE INDEX idx_comm_flag ON comm_messages(needs_response, responded);
CREATE UNIQUE INDEX idx_comm_external ON comm_messages(external_id) WHERE external_id IS NOT NULL;

CREATE TABLE association_hints (
    id          TEXT PRIMARY KEY,
    hint_type   TEXT NOT NULL CHECK (hint_type IN ('email_person','name_person','keyword_account')),
    key         TEXT NOT NULL,                           -- lowercased email / name / keyword
    person_id   TEXT REFERENCES persons(id),
    account_id  TEXT REFERENCES accounts(id),
    source      TEXT NOT NULL DEFAULT 'auto' CHECK (source IN ('auto','correction')),
    active      INTEGER NOT NULL DEFAULT 1,               -- supersede-not-delete
    created_at  TEXT NOT NULL
);
CREATE INDEX idx_hints_key ON association_hints(hint_type, key, active);
