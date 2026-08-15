-- VISIBILITY-SPEC.md §8 — advocacy tags on people. The one migration in that spec.
--
-- What this records is **public-facing advocacy**: a person agreed to be a reference, wrote a
-- review, gave a quote, joined a beta, or spoke. Every one of those is deployment engagement, which
-- the §2 trust boundary permits by name ("meetings, comms, advocacy"). None of it is, or can be
-- derived from, that person's usage of the product.
--
-- Why this is not more kinds on `advocacy_events` (migration 0013), which is the obvious move:
--
--   1. `advocacy_events` is *internal* advocacy inside the customer's organisation, and it is read
--      by name in four places — `people_core.has_champion_evidence`, `people_analytics`,
--      `stage75`, and `readiness._CHAMPION_EVIDENCE_KINDS` — each with its own `kind IN (...)`
--      filter. Widening that CHECK would require all four to be updated in lockstep, and the one
--      that got missed would quietly start counting a conference talk as proof that someone
--      advocates for us when we are not in the room. That inference is the entire point of the
--      coach-vs-champion gate, and it would be wrong.
--   2. §8 requires the date and the evidence note **structurally**. `advocacy_events.occurred_on`
--      and `.note` are both nullable and have rows. Tightening them means a table rebuild that
--      either fails on existing data or backfills a date nobody recorded, and inventing a date is
--      the failure this whole spec exists to prevent.
--
-- What is deliberately absent, and must stay absent: any sentiment, inferred willingness, score, or
-- "advocacy level" column. A tag says a dated thing happened and points at the evidence. It does
-- not say how enthusiastic anyone is. `backend/tests/test_visibility_advocacy_tags.py` asserts the
-- column set exactly, so a later addition has to argue with a test rather than slip in.

CREATE TABLE advocacy_tags (
    id                  TEXT PRIMARY KEY,
    person_id           TEXT NOT NULL REFERENCES persons(id),
    kind                TEXT NOT NULL CHECK (kind IN (
                          'reference','review','quote','beta_participant','speaking')),
    -- NOT NULL *and* non-empty: NOT NULL alone is satisfied by '', which is how a required field
    -- becomes an optional one without anybody editing the schema.
    occurred_on         TEXT NOT NULL CHECK (length(trim(occurred_on)) > 0),
    evidence_note       TEXT NOT NULL CHECK (length(trim(evidence_note)) > 0),
    source_reference_id TEXT REFERENCES source_references(id),
    actor_id            TEXT,
    created_at          TEXT NOT NULL,
    updated_at          TEXT NOT NULL,
    archived            INTEGER NOT NULL DEFAULT 0,
    archived_at         TEXT,
    archived_by         TEXT
);

CREATE INDEX idx_advocacy_tag_person ON advocacy_tags(person_id, occurred_on);
