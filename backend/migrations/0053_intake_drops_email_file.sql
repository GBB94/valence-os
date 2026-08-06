-- Migration 0053 — `email_file` joins the drop kinds (ACCOUNT-INTAKE-SPEC.md §7.2, Slice 2).
--
-- A dropped `.eml` and a pasted thread are not the same kind, and collapsing them would be a
-- receipt that lies about which path ran. The difference is not cosmetic:
--
--   * An `.eml` carries a Message-ID, so it creates a `comm_message`, joins the thread graph, and
--     is deduplicated against synced mail (§7.4). `comm_message_id` is set.
--   * A paste has no message identity, so it creates none of that, and the receipt says so in its
--     own coverage reason. `comm_message_id` is NULL for a paste, always.
--
-- One column can therefore mean two different things about `comm_message_id` being NULL, and the
-- kind is what tells them apart. So this is a CHECK widening, which in SQLite is a table rebuild.
--
-- Everything else about 0052 is carried over verbatim, including the four things it deliberately
-- does not store (coverage, errors, proposal counts, provenance) and the forbidden-column rule
-- asserted by schema introspection in the tests. `outcome` remains the single named exemption: it
-- describes our own processing of a file and never anything about the account.

PRAGMA foreign_keys = ON;

CREATE TABLE intake_drops_new (
    id                  TEXT PRIMARY KEY,
    account_id          TEXT NOT NULL REFERENCES accounts(id),
    program_id          TEXT REFERENCES programs(id),

    filename            TEXT,
    detected_kind       TEXT NOT NULL CHECK (detected_kind IN (
                          'notes','email_paste','email_file','transcript')),
    byte_length         INTEGER NOT NULL,
    content_hash        TEXT NOT NULL,

    snapshot_text       TEXT,
    snapshot_deleted_at TEXT,
    snapshot_deleted_by TEXT,

    new_text_chars      INTEGER,
    quoted_chars        INTEGER,

    outcome             TEXT NOT NULL CHECK (outcome IN (
                          'rejected_kind','parse_failed','no_proposals','drafted','duplicate')),
    outcome_reason      TEXT,
    extraction_run_id   TEXT REFERENCES extraction_runs(id),
    comm_message_id     TEXT REFERENCES comm_messages(id),
    duplicate_of_id     TEXT REFERENCES intake_drops(id),

    created_at          TEXT NOT NULL,
    created_by          TEXT NOT NULL,
    updated_at          TEXT NOT NULL,
    archived            INTEGER NOT NULL DEFAULT 0,
    archived_at         TEXT,
    archived_by         TEXT
);

INSERT INTO intake_drops_new
SELECT id, account_id, program_id, filename, detected_kind, byte_length, content_hash,
       snapshot_text, snapshot_deleted_at, snapshot_deleted_by, new_text_chars, quoted_chars,
       outcome, outcome_reason, extraction_run_id, comm_message_id, duplicate_of_id,
       created_at, created_by, updated_at, archived, archived_at, archived_by
FROM intake_drops;

DROP TABLE intake_drops;
ALTER TABLE intake_drops_new RENAME TO intake_drops;

CREATE INDEX idx_intake_drops_account ON intake_drops (account_id, created_at DESC);
CREATE INDEX idx_intake_drops_hash ON intake_drops (account_id, content_hash);
