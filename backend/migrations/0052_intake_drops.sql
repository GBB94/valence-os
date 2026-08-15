-- Migration 0052 — the account drop zone (ACCOUNT-INTAKE-SPEC.md §13).
--
-- One table. It records what was dropped on an account page and what happened to it. It is
-- deliberately NOT a second proposal store: the proposals a drop produces live in
-- `extraction_runs` / `extraction_proposals` exactly as a transcript extraction's do, and
-- `extraction_run_id` below is the whole of the relationship.
--
-- Four things this table deliberately does NOT carry, each because migration 0043 already carries
-- it and a second copy is a cached disagreement waiting to happen:
--
--  1. **No `coverage_json`.** `extraction_runs.coverage_json` is where a run says what it did not
--     read. A drop that produced no run has no coverage to report beyond `outcome_reason` — which
--     is the honest shape, because nothing was read, so there is nothing to say about what was
--     skipped.
--  2. **No `error_json`.** Same table, same reason.
--  3. **No proposal count.** Derived from `extraction_proposals` on every read.
--  4. **No provenance model.** 0043's own header states the rule: provenance keeps living in
--     `source_references`.
--
-- `content_hash` IS kept despite `extraction_runs.content_hash`, and the reason is narrow enough
-- to write down: a refused or parse-failed drop never creates a run at all, and a drop whose
-- snapshot has been deleted can no longer derive one. Duplicate detection (Slice 3) has to work
-- for both, so the hash has to survive independently of the run.
--
-- **Forbidden columns.** No column here may be named or suffixed `state`, `met`, `freshness`,
-- `coverage`, `applicability`, `score`, or `weight` — the RELATIONSHIP-READINESS-SPEC.md §2 rule,
-- asserted by schema introspection in `test_intake_drop_slice1.py`. `outcome` is the single
-- exemption and is asserted by name: it describes **our own processing of a file**, never anything
-- about the account. A dropped document can no more assert a readiness answer than a plan can.

CREATE TABLE intake_drops (
    id                  TEXT PRIMARY KEY,
    -- §8: the account is the route parameter, never a guess and never read from the text.
    account_id          TEXT NOT NULL REFERENCES accounts(id),
    -- Optional, and it comes from the operator's selector. A run with no program is account-level
    -- work, not work in every program.
    program_id          TEXT REFERENCES programs(id),

    filename            TEXT,                 -- NULL for a paste
    detected_kind       TEXT NOT NULL CHECK (detected_kind IN (
                          'notes','email_paste','transcript')),
    byte_length         INTEGER NOT NULL,
    content_hash        TEXT NOT NULL,

    -- §5: text in, bytes never persisted. This column is the *text*; the bytes it was decoded from
    -- are gone when the request ends. NULL once the operator deletes it, which keeps the drop, its
    -- hash, and every proposal drawn from it — a citation survives as a quoted span even when its
    -- source is gone. There is no automatic expiry: a timer that silently destroyed the evidence
    -- behind a live proposal would be worse than keeping it.
    snapshot_text       TEXT,
    snapshot_deleted_at TEXT,
    snapshot_deleted_by TEXT,

    new_text_chars      INTEGER,              -- what reached the extractor
    quoted_chars        INTEGER,              -- what did not

    outcome             TEXT NOT NULL CHECK (outcome IN (
                          'rejected_kind','parse_failed','no_proposals','drafted','duplicate')),
    outcome_reason      TEXT,                 -- the sentence shown to the operator, authored server-side
    extraction_run_id   TEXT REFERENCES extraction_runs(id),
    -- §7.4, set in Slice 2 when a dropped .eml goes through the ingestion path. NULL for a paste,
    -- always: pasted text has no Message-ID, so it has no thread identity and cannot be
    -- deduplicated against synced mail. Inventing one would corrupt the thread graph.
    comm_message_id     TEXT,
    duplicate_of_id     TEXT REFERENCES intake_drops(id),

    created_at          TEXT NOT NULL,
    created_by          TEXT NOT NULL,
    -- A receipt of a past event barely has an update, but `repo.archive` stamps this and using the
    -- shared helper is worth more than saving a column.
    updated_at          TEXT NOT NULL,
    archived            INTEGER NOT NULL DEFAULT 0,
    archived_at         TEXT,
    archived_by         TEXT
);

CREATE INDEX idx_intake_drops_account ON intake_drops (account_id, created_at DESC);
-- Slice 3's duplicate lookup: the same bytes dropped twice on the same account.
CREATE INDEX idx_intake_drops_hash ON intake_drops (account_id, content_hash);
