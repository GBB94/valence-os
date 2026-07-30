-- Migration 0013 — Phase 3 Stage 2: People module core (Comprehensive Spec §§3.1-3.2, 3.10)
--   §3.1 layer model: every stakeholder role carries a horizontal-band layer.
--   §3.2 role taxonomy: widen roles to the full buying committee; coach-vs-champion is enforced
--        by EVIDENCE (advocacy_events), computed at read time, not stored on the row.
--   §3.10 person card: a couple of professional-observation-only fields on persons.
-- Trust boundary (D-76): professional observations only — no sensitive personal data.
-- SQLite can't widen a CHECK in place, so stakeholder_roles is recreated (nothing FKs into it;
-- it only FKs out to programs/persons, so the drop+rename is safe).

PRAGMA foreign_keys = ON;

-- --- recreate stakeholder_roles with the widened role enum + a layer column ---------------
CREATE TABLE stakeholder_roles_new (
    id                  TEXT PRIMARY KEY,
    program_id          TEXT NOT NULL REFERENCES programs(id),
    person_id           TEXT NOT NULL REFERENCES persons(id),
    role                TEXT NOT NULL DEFAULT 'other' CHECK (role IN (
                          -- original set (kept for back-compat: queue senior roles, coverage)
                          'champion','budget_owner','program_owner','it','legal_dpo',
                          'works_council_contact','other',
                          -- §3.2 full buying committee
                          'executive_sponsor','financial_gatekeeper','procurement',
                          'technical_evaluator','legal_compliance','end_user_voice',
                          'coach','detractor')),
    -- §3.1 layer (nullable; a default is derived from role at read time when null)
    layer               TEXT CHECK (layer IS NULL OR layer IN (
                          'executive','economic','operational','technical_gating','user_advocate')),
    stance              TEXT CHECK (stance IN ('supporter','skeptic','unconverted')),
    stance_assessed_on  TEXT,
    stance_evidence_note TEXT,
    cares_about         TEXT,
    value_for_them      TEXT,
    created_at          TEXT NOT NULL,
    updated_at          TEXT NOT NULL,
    archived            INTEGER NOT NULL DEFAULT 0,
    archived_at         TEXT,
    archived_by         TEXT,
    influence           TEXT CHECK (influence IN ('low','medium','high')),
    relationship_strength TEXT CHECK (relationship_strength IN ('weak','medium','strong')),
    graph_assessed_on   TEXT,
    graph_evidence_note TEXT,
    CHECK (stance IS NULL OR (stance_assessed_on IS NOT NULL AND stance_evidence_note IS NOT NULL))
);

INSERT INTO stakeholder_roles_new (
    id, program_id, person_id, role, stance, stance_assessed_on, stance_evidence_note,
    cares_about, value_for_them, created_at, updated_at, archived, archived_at, archived_by,
    influence, relationship_strength, graph_assessed_on, graph_evidence_note)
SELECT
    id, program_id, person_id, role, stance, stance_assessed_on, stance_evidence_note,
    cares_about, value_for_them, created_at, updated_at, archived, archived_at, archived_by,
    influence, relationship_strength, graph_assessed_on, graph_evidence_note
FROM stakeholder_roles;

DROP TABLE stakeholder_roles;
ALTER TABLE stakeholder_roles_new RENAME TO stakeholder_roles;
CREATE INDEX idx_stakeholder_program ON stakeholder_roles(program_id);
CREATE INDEX idx_stakeholder_person ON stakeholder_roles(person_id);

-- --- advocacy evidence (coach-vs-champion; reused by the Stage 5 champion pipeline) -------
-- A champion tag only reads as "champion" if there's a logged instance of advocacy WITHOUT
-- us in the room; otherwise the person card labels them coach and says why (§3.2).
CREATE TABLE advocacy_events (
    id                  TEXT PRIMARY KEY,
    person_id           TEXT NOT NULL REFERENCES persons(id),
    program_id          TEXT REFERENCES programs(id),
    kind                TEXT NOT NULL CHECK (kind IN (
                          'advocacy_without_us','secured_meeting','defended_us',
                          'presented_internally','other')),
    occurred_on         TEXT,
    note                TEXT,               -- professional observation only
    source_reference_id TEXT REFERENCES source_references(id),
    created_at          TEXT NOT NULL,
    updated_at          TEXT NOT NULL,
    archived            INTEGER NOT NULL DEFAULT 0,
    archived_at         TEXT,
    archived_by         TEXT
);
CREATE INDEX idx_advocacy_person ON advocacy_events(person_id, program_id);

-- --- person-card fields (professional observations only) ----------------------------------
ALTER TABLE persons ADD COLUMN comms_preference TEXT;   -- e.g. "prefers async; email over calls"
ALTER TABLE persons ADD COLUMN metric_judged_on TEXT;   -- the business metric they're measured on
