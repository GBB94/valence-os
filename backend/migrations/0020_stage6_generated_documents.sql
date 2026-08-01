-- Migration 0020 — Stage 6: generated documents (PHASE-3-SPEC.md Part 5)
--
-- The generators stop being read-only views and start producing artifacts the operator edits,
-- reviews, and sends. That needs somewhere to put them, and the spec is explicit about the
-- rule those artifacts live under: scheduled generation "saved as a draft for review, never
-- auto-sent." So `status` starts at 'draft' and only a human moves it.
--
-- The body is stored as markdown, not as a rendered binary. Rendering to .pptx is a pure
-- function of the markdown plus the stamp (app/decks.py), so a stored deck can be re-rendered
-- when the template changes, and the stored artifact stays diffable and greppable. Binaries
-- are produced on download, never persisted.
--
-- The stamp is denormalized onto the row on purpose. A document is a claim about what was true
-- at a moment; re-deriving `data_current_through` later would silently restate history, which
-- is the exact failure the freshness language exists to prevent.

PRAGMA foreign_keys = ON;

CREATE TABLE generated_documents (
    id            TEXT PRIMARY KEY,
    account_id    TEXT REFERENCES accounts(id),     -- NULL for portfolio-wide (the team update)
    program_id    TEXT REFERENCES programs(id),
    kind          TEXT NOT NULL CHECK (kind IN (
                    'pre_call_brief', 'business_case', 'champion_kit', 'value_review',
                    'kickoff_deck', 'team_update')),
    title         TEXT NOT NULL,
    body_markdown TEXT NOT NULL,

    -- Draft until a human says otherwise. 'sent' records that it left the building; nothing in
    -- this app sends anything, so it is an operator assertion, not an integration.
    status        TEXT NOT NULL DEFAULT 'draft' CHECK (status IN ('draft', 'reviewed', 'sent', 'discarded')),
    reviewed_on   TEXT,
    reviewed_by   TEXT,

    -- Stamp, frozen at generation (see header).
    generated_at            TEXT NOT NULL,
    data_current_through    TEXT,
    missing_or_stale_note   TEXT,          -- what was unknown when this was produced
    -- Client-facing artifacts carry only affirmatively promoted records. Recorded per document
    -- so a reader can tell which rule set produced it without re-running the generator.
    audience      TEXT NOT NULL DEFAULT 'internal' CHECK (audience IN ('internal', 'client_facing')),

    -- Provenance: which job produced it, if it was scheduled rather than requested.
    source_job_id TEXT,
    source_interaction_id TEXT REFERENCES interactions(id),

    created_at    TEXT NOT NULL,
    updated_at    TEXT NOT NULL,
    archived      INTEGER NOT NULL DEFAULT 0,
    archived_at   TEXT,
    archived_by   TEXT,

    -- A reviewed document records who reviewed it and when, or the status is an empty claim.
    CHECK (status IN ('draft', 'discarded') OR (reviewed_on IS NOT NULL AND reviewed_by IS NOT NULL))
);
CREATE INDEX idx_gendoc_account ON generated_documents(account_id, kind, generated_at);
CREATE INDEX idx_gendoc_status ON generated_documents(status) WHERE archived = 0;

-- The ROI inputs behind a champion kit (Part 5). Assumptions, explicitly: seat price and
-- retention are operator judgments, not synced facts, so they carry an author and a date and
-- render labeled as assumptions per the standing credibility rules. Recovered vendor spend is
-- NOT restated here — it points at the existing record.
CREATE TABLE roi_models (
    account_id            TEXT PRIMARY KEY REFERENCES accounts(id),
    seat_price            REAL,
    seat_price_currency   TEXT,
    seat_price_basis      TEXT,           -- e.g. "list, pre-discount" — an assumption, stated
    retention_uplift_pct  REAL,           -- the retention math input
    retention_note        TEXT,
    recovered_spend_id    TEXT REFERENCES recovered_spend(id),
    assumptions_note      TEXT,
    author                TEXT,
    assessed_on           TEXT,
    created_at            TEXT NOT NULL,
    updated_at            TEXT NOT NULL,
    -- An assumption without an author and a date is a number nobody owns.
    CHECK (seat_price IS NULL OR (author IS NOT NULL AND assessed_on IS NOT NULL))
);
