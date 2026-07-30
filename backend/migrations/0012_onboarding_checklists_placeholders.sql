-- Migration 0012 — Phase 3 Stage 1 (PHASE-3-SPEC.md §§1-3)
-- Guided onboarding seeds a launch plan, checklists, and org-chart placeholders per account.
--   §1  kickoff anchor on the program (all seeded dates are relative to it) + onboarded guard.
--   §2  time-phased launch checklist items (incl. the §1e first-call question list) with due
--       windows relative to kickoff; falling-behind escalation is DERIVED in the queue.
--   §3  org-chart placeholders — a position known to exist but not yet identified. Modeled as a
--       persons row (is_placeholder=1) so relationship_edges and stakeholder_roles attach the
--       same way, and "convert to a real person" preserves edges by keeping the same id.
-- No trust-boundary change: placeholders are positions, not product usage; stance still needs a
-- date + evidence (unchanged CHECK on stakeholder_roles). Mock-only data.

PRAGMA foreign_keys = ON;

-- §1 — kickoff anchor + idempotency guard for the guided seed.
ALTER TABLE programs ADD COLUMN kickoff_date TEXT;   -- date; null until onboarded
ALTER TABLE programs ADD COLUMN onboarded_at TEXT;   -- set when seed_onboarding runs

-- §3 — placeholder metadata on persons. A real person has is_placeholder=0 and these null.
ALTER TABLE persons ADD COLUMN is_placeholder INTEGER NOT NULL DEFAULT 0;
ALTER TABLE persons ADD COLUMN placeholder_why TEXT;          -- why this position matters
ALTER TABLE persons ADD COLUMN find_by_date TEXT;             -- date; past it -> fires into Today
ALTER TABLE persons ADD COLUMN expected_influence TEXT
    CHECK (expected_influence IS NULL OR expected_influence IN ('low','medium','high'));
ALTER TABLE persons ADD COLUMN expected_role TEXT;            -- e.g. 'budget_owner' (stakeholder role enum)

-- §2/§1e — time-phased launch checklist items. Seeded from editable templates; due windows
-- relative to kickoff. first_call items double as the §1e question list (fills_field points at
-- the account/program field the answer should fill).
CREATE TABLE checklist_items (
    id              TEXT PRIMARY KEY,
    account_id      TEXT NOT NULL REFERENCES accounts(id),
    program_id      TEXT REFERENCES programs(id),
    template_key    TEXT,                 -- provenance: the template row that seeded this
    section         TEXT NOT NULL CHECK (section IN
                      ('first_call','first_two_weeks','first_30_days','first_90_days')),
    label           TEXT NOT NULL,
    detail          TEXT,                 -- the thing to understand / do
    fills_field     TEXT,                 -- account/program field this answers (e.g. 'program.success_criteria')
    due_offset_days INTEGER,              -- relative to kickoff; used to compute due_date at seed
    due_date        TEXT,                 -- computed at seed; editable
    status          TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open','done','na')),
    answer_note     TEXT,                 -- what was learned (first-call questions)
    done_on         TEXT,
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL,
    archived        INTEGER NOT NULL DEFAULT 0,
    archived_at     TEXT,
    archived_by     TEXT
);
CREATE INDEX idx_checklist_program ON checklist_items(program_id, section);
CREATE INDEX idx_checklist_account ON checklist_items(account_id, status);
CREATE INDEX idx_checklist_due ON checklist_items(status, due_date);
