-- Migration 0025 — Stage 9: honest portfolio analytics and the expansion playbook.
--
-- Analytics must be reconstructable from dated facts.  A growth-plan line previously named
-- only a population, so it could not say which use case was funded, and `updated_at` was not
-- a defensible funded date.  The optional cell link and immutable funded_on close that seam.
-- Cell history now snapshots the derived state on both sides of a fact change; the facts remain
-- canonical, but transitions no longer have to be guessed from today's cell.

PRAGMA foreign_keys = ON;

ALTER TABLE cell_state_history ADD COLUMN derived_state_before TEXT;
ALTER TABLE cell_state_history ADD COLUMN derived_state_after TEXT;

ALTER TABLE growth_plan_lines ADD COLUMN cell_id TEXT REFERENCES whitespace_cells(id);
ALTER TABLE growth_plan_lines ADD COLUMN funded_on TEXT;
ALTER TABLE growth_plan_lines ADD COLUMN seat_price_currency TEXT;
ALTER TABLE growth_plan_lines ADD COLUMN seat_price_basis TEXT CHECK (
    seat_price_basis IS NULL OR seat_price_basis IN ('annual_recurring','term_total','one_time'));
CREATE INDEX idx_growth_line_cell ON growth_plan_lines(cell_id, funded_on);

CREATE TRIGGER trg_growth_line_cell_scope_insert BEFORE INSERT ON growth_plan_lines
WHEN NEW.cell_id IS NOT NULL AND NOT EXISTS (
    SELECT 1 FROM whitespace_cells c
    WHERE c.id=NEW.cell_id AND c.account_id=NEW.account_id
      AND IFNULL(c.segment_id,'')=IFNULL(NEW.segment_id,'')
      AND IFNULL(c.view_id,'')=IFNULL(NEW.view_id,''))
BEGIN SELECT RAISE(ABORT, 'growth line cell belongs to a different account or population'); END;

CREATE TRIGGER trg_growth_line_cell_scope_update BEFORE UPDATE OF
account_id,segment_id,view_id,cell_id ON growth_plan_lines
WHEN NEW.cell_id IS NOT NULL AND NOT EXISTS (
    SELECT 1 FROM whitespace_cells c
    WHERE c.id=NEW.cell_id AND c.account_id=NEW.account_id
      AND IFNULL(c.segment_id,'')=IFNULL(NEW.segment_id,'')
      AND IFNULL(c.view_id,'')=IFNULL(NEW.view_id,''))
BEGIN SELECT RAISE(ABORT, 'growth line cell belongs to a different account or population'); END;

-- One structured learning record per eligible transition. Audience tags are a snapshot: later
-- edits to a population view must not silently rewrite the shape that was actually won or lost.
CREATE TABLE playbook_entries (
    id                    TEXT PRIMARY KEY,
    account_id            TEXT NOT NULL REFERENCES accounts(id),
    cell_id               TEXT NOT NULL REFERENCES whitespace_cells(id),
    transition_history_id TEXT NOT NULL UNIQUE REFERENCES cell_state_history(id),
    use_case_id           TEXT NOT NULL REFERENCES use_cases(id),
    transition_from       TEXT,
    transition_to         TEXT NOT NULL CHECK (transition_to IN ('proven','penetrated','declined')),
    transitioned_on       TEXT NOT NULL,
    motion_run            TEXT NOT NULL,
    evidence_summary      TEXT,
    message_summary       TEXT,
    message_layer         TEXT CHECK (message_layer IS NULL OR message_layer IN
                           ('executive','economic','operational','technical_gating','user_advocate')),
    motion_started_on     TEXT,
    duration_days         INTEGER CHECK (duration_days IS NULL OR duration_days >= 0),
    what_worked           TEXT,
    what_differently      TEXT,
    play_definition_id    TEXT REFERENCES play_definitions(id),
    messaging_entry_id    TEXT REFERENCES messaging_entries(id),
    created_at            TEXT NOT NULL,
    updated_at            TEXT NOT NULL,
    archived              INTEGER NOT NULL DEFAULT 0,
    archived_at           TEXT,
    archived_by           TEXT,
    CHECK (motion_started_on IS NULL OR motion_started_on <= transitioned_on)
);
CREATE INDEX idx_playbook_shape ON playbook_entries(use_case_id, transitioned_on);
CREATE INDEX idx_playbook_account ON playbook_entries(account_id, transitioned_on);

CREATE TABLE playbook_entry_tags (
    entry_id TEXT NOT NULL REFERENCES playbook_entries(id),
    tag_id   TEXT NOT NULL REFERENCES audience_tags(id),
    PRIMARY KEY (entry_id, tag_id)
);

CREATE TRIGGER trg_playbook_scope_insert BEFORE INSERT ON playbook_entries
WHEN NOT EXISTS (
    SELECT 1 FROM whitespace_cells c
    WHERE c.id=NEW.cell_id AND c.account_id=NEW.account_id AND c.use_case_id=NEW.use_case_id)
BEGIN SELECT RAISE(ABORT, 'playbook entry cell belongs to a different account or use case'); END;
