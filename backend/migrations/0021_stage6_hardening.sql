-- Migration 0021 — adversarial hardening for Stage 5.5/6.
--
-- Client-facing generators must have an affirmative promotion bit on every record type they
-- consume.  Row-level paid inventory is stored separately from per-use-case cell counts because
-- the union of overlapping use-case populations cannot be derived with SUM or MAX.

PRAGMA foreign_keys = ON;

ALTER TABLE whitespace_cells ADD COLUMN client_visible INTEGER NOT NULL DEFAULT 0;
ALTER TABLE whitespace_cells ADD COLUMN source_reference_id TEXT REFERENCES source_references(id);

ALTER TABLE funding_pools ADD COLUMN client_visible INTEGER NOT NULL DEFAULT 0;
ALTER TABLE funding_pools ADD COLUMN source_reference_id TEXT REFERENCES source_references(id);

ALTER TABLE population_segments ADD COLUMN paid_seats INTEGER;
ALTER TABLE population_segments ADD COLUMN paid_seats_source TEXT;
ALTER TABLE population_segments ADD COLUMN paid_seats_as_of TEXT;

-- Money cannot be added safely without a currency. Existing rows inherit the current contract
-- currency where one is known; otherwise they remain explicitly unknown and are excluded from
-- mixed-currency waterfall totals.
ALTER TABLE recovered_spend ADD COLUMN currency TEXT;
UPDATE recovered_spend SET currency = (
    SELECT cv.currency FROM contract_versions cv
    WHERE cv.account_id=recovered_spend.account_id AND cv.is_current=1 AND cv.archived=0
    ORDER BY cv.created_at DESC LIMIT 1
) WHERE currency IS NULL;

-- Preserve the previous best-known value as an explicitly labelled legacy estimate. Operators
-- can replace it with the actual segment inventory through the normal API/UI.
UPDATE population_segments
SET paid_seats = (
        SELECT MAX(wc.paid_seats) FROM whitespace_cells wc
        WHERE wc.segment_id = population_segments.id AND wc.archived = 0
    ),
    paid_seats_source = 'Legacy max-across-use-cases estimate',
    paid_seats_as_of = date('now')
WHERE EXISTS (
    SELECT 1 FROM whitespace_cells wc
    WHERE wc.segment_id = population_segments.id AND wc.archived = 0
);

CREATE INDEX idx_cell_client_visible ON whitespace_cells(account_id, client_visible)
    WHERE archived = 0;
CREATE INDEX idx_pool_client_visible ON funding_pools(account_id, client_visible)
    WHERE archived = 0;

-- A champion kit is only useful if the pipeline can answer who received which version and
-- when. Generation links the intended audience; the operator's explicit `sent` transition
-- records the handoff date. No transmission happens here.
CREATE TABLE generated_document_people (
    document_id TEXT NOT NULL REFERENCES generated_documents(id),
    person_id   TEXT NOT NULL REFERENCES persons(id),
    purpose     TEXT NOT NULL DEFAULT 'champion_enablement',
    shared_on   TEXT,
    created_at  TEXT NOT NULL,
    PRIMARY KEY (document_id, person_id)
);
CREATE INDEX idx_gendoc_people_person ON generated_document_people(person_id, shared_on);

-- Relationship constraints which ordinary single-column foreign keys cannot express.
CREATE TRIGGER trg_gendoc_program_account_insert
BEFORE INSERT ON generated_documents
WHEN NEW.account_id IS NOT NULL AND NEW.program_id IS NOT NULL
 AND NOT EXISTS (SELECT 1 FROM programs p WHERE p.id=NEW.program_id AND p.account_id=NEW.account_id)
BEGIN SELECT RAISE(ABORT, 'document program belongs to a different account'); END;

CREATE TRIGGER trg_gendoc_program_account_update
BEFORE UPDATE OF account_id, program_id ON generated_documents
WHEN NEW.account_id IS NOT NULL AND NEW.program_id IS NOT NULL
 AND NOT EXISTS (SELECT 1 FROM programs p WHERE p.id=NEW.program_id AND p.account_id=NEW.account_id)
BEGIN SELECT RAISE(ABORT, 'document program belongs to a different account'); END;

CREATE TRIGGER trg_gendoc_person_account_insert
BEFORE INSERT ON generated_document_people
WHEN NOT EXISTS (
    SELECT 1 FROM generated_documents gd JOIN persons p ON p.id=NEW.person_id
    WHERE gd.id=NEW.document_id AND gd.account_id=p.account_id)
BEGIN SELECT RAISE(ABORT, 'document person belongs to a different account'); END;

CREATE TRIGGER trg_population_view_segment_account_insert
BEFORE INSERT ON population_view_segments
WHEN NOT EXISTS (
    SELECT 1 FROM population_views v JOIN population_segments s ON s.id=NEW.segment_id
    WHERE v.id=NEW.view_id AND v.account_id=s.account_id)
BEGIN SELECT RAISE(ABORT, 'population view segment belongs to a different account'); END;

CREATE TRIGGER trg_value_target_visibility_insert
BEFORE INSERT ON value_targets
WHEN NEW.client_visible=1 AND
     (NEW.client_accepted<>1 OR (NEW.source_reference_id IS NULL AND NEW.source_interaction_id IS NULL))
BEGIN SELECT RAISE(ABORT, 'client-visible target requires client acceptance and a source'); END;

CREATE TRIGGER trg_value_target_visibility_update
BEFORE UPDATE OF client_visible, client_accepted, source_reference_id, source_interaction_id ON value_targets
WHEN NEW.client_visible=1 AND
     (NEW.client_accepted<>1 OR (NEW.source_reference_id IS NULL AND NEW.source_interaction_id IS NULL))
BEGIN SELECT RAISE(ABORT, 'client-visible target requires client acceptance and a source'); END;

CREATE TRIGGER trg_cell_visibility_insert
BEFORE INSERT ON whitespace_cells
WHEN NEW.client_visible=1 AND NEW.source_reference_id IS NULL
BEGIN SELECT RAISE(ABORT, 'client-visible whitespace cell requires a source'); END;

CREATE TRIGGER trg_cell_visibility_update
BEFORE UPDATE OF client_visible, source_reference_id ON whitespace_cells
WHEN NEW.client_visible=1 AND NEW.source_reference_id IS NULL
BEGIN SELECT RAISE(ABORT, 'client-visible whitespace cell requires a source'); END;

CREATE TRIGGER trg_pool_visibility_insert
BEFORE INSERT ON funding_pools
WHEN NEW.client_visible=1 AND NEW.source_reference_id IS NULL
BEGIN SELECT RAISE(ABORT, 'client-visible funding pool requires a source'); END;

CREATE TRIGGER trg_pool_visibility_update
BEFORE UPDATE OF client_visible, source_reference_id ON funding_pools
WHEN NEW.client_visible=1 AND NEW.source_reference_id IS NULL
BEGIN SELECT RAISE(ABORT, 'client-visible funding pool requires a source'); END;

CREATE TRIGGER trg_roi_provenance_insert
BEFORE INSERT ON roi_models
WHEN (NEW.seat_price IS NOT NULL OR NEW.retention_uplift_pct IS NOT NULL OR
      NEW.recovered_spend_id IS NOT NULL OR NEW.assumptions_note IS NOT NULL)
 AND (NEW.author IS NULL OR NEW.assessed_on IS NULL)
BEGIN SELECT RAISE(ABORT, 'ROI assumptions require an author and assessment date'); END;

CREATE TRIGGER trg_roi_provenance_update
BEFORE UPDATE ON roi_models
WHEN (NEW.seat_price IS NOT NULL OR NEW.retention_uplift_pct IS NOT NULL OR
      NEW.recovered_spend_id IS NOT NULL OR NEW.assumptions_note IS NOT NULL)
 AND (NEW.author IS NULL OR NEW.assessed_on IS NULL)
BEGIN SELECT RAISE(ABORT, 'ROI assumptions require an author and assessment date'); END;

CREATE TRIGGER trg_roi_recovered_account_insert
BEFORE INSERT ON roi_models
WHEN NEW.recovered_spend_id IS NOT NULL AND NOT EXISTS (
    SELECT 1 FROM recovered_spend r WHERE r.id=NEW.recovered_spend_id AND r.account_id=NEW.account_id)
BEGIN SELECT RAISE(ABORT, 'recovered spend belongs to a different account'); END;

CREATE TRIGGER trg_roi_recovered_account_update
BEFORE UPDATE OF account_id, recovered_spend_id ON roi_models
WHEN NEW.recovered_spend_id IS NOT NULL AND NOT EXISTS (
    SELECT 1 FROM recovered_spend r WHERE r.id=NEW.recovered_spend_id AND r.account_id=NEW.account_id)
BEGIN SELECT RAISE(ABORT, 'recovered spend belongs to a different account'); END;

CREATE TRIGGER trg_segment_paid_cap_insert
BEFORE INSERT ON population_segments
WHEN NEW.paid_seats IS NOT NULL AND NEW.headcount IS NOT NULL AND NEW.paid_seats > NEW.headcount
BEGIN SELECT RAISE(ABORT, 'segment paid seats cannot exceed headcount'); END;

CREATE TRIGGER trg_segment_paid_cap_update
BEFORE UPDATE OF paid_seats, headcount ON population_segments
WHEN NEW.paid_seats IS NOT NULL AND NEW.headcount IS NOT NULL AND NEW.paid_seats > NEW.headcount
BEGIN SELECT RAISE(ABORT, 'segment paid seats cannot exceed headcount'); END;

CREATE TRIGGER trg_recovered_spend_money_insert
BEFORE INSERT ON recovered_spend
WHEN NEW.amount < 0 OR (NEW.currency IS NOT NULL AND
     (length(NEW.currency)<>3 OR NEW.currency<>upper(NEW.currency)))
BEGIN SELECT RAISE(ABORT, 'recovered spend requires a non-negative amount and ISO currency'); END;

CREATE TRIGGER trg_recovered_spend_money_update
BEFORE UPDATE OF amount, currency ON recovered_spend
WHEN NEW.amount < 0 OR (NEW.currency IS NOT NULL AND
     (length(NEW.currency)<>3 OR NEW.currency<>upper(NEW.currency)))
BEGIN SELECT RAISE(ABORT, 'recovered spend requires a non-negative amount and ISO currency'); END;
