-- Migration 0026 — Internal Ops Stage 10.0: integrity foundations.
-- One rebuild each for generated documents, commitments, and decisions. Account-level
-- execution follows the proven interaction shape: account required, program optional.

PRAGMA foreign_keys = OFF;

ALTER TABLE revenue_events ADD COLUMN price_basis TEXT CHECK (
    price_basis IS NULL OR price_basis IN ('arr','tcv','one_time','monthly'));
ALTER TABLE revenue_events ADD COLUMN opportunity_id TEXT REFERENCES expansion_opportunities(id);

CREATE TABLE internal_operations_settings (
    id                      TEXT PRIMARY KEY CHECK (id='singleton'),
    operator_identity       TEXT NOT NULL DEFAULT 'operator',
    business_timezone       TEXT NOT NULL DEFAULT 'America/New_York',
    business_day_start_hour INTEGER NOT NULL DEFAULT 9 CHECK (business_day_start_hour BETWEEN 0 AND 23),
    business_day_end_hour   INTEGER NOT NULL DEFAULT 17 CHECK (business_day_end_hour BETWEEN 1 AND 24),
    working_weekdays_json   TEXT NOT NULL DEFAULT '[1,2,3,4,5]',
    created_at              TEXT NOT NULL,
    updated_at              TEXT NOT NULL,
    CHECK (business_day_end_hour > business_day_start_hour)
);
INSERT INTO internal_operations_settings
    (id,operator_identity,business_timezone,business_day_start_hour,business_day_end_hour,
     working_weekdays_json,created_at,updated_at)
VALUES ('singleton','operator','America/New_York',9,17,'[1,2,3,4,5]',datetime('now'),datetime('now'));

CREATE TABLE status_criteria_versions (
    id              TEXT PRIMARY KEY,
    account_id      TEXT REFERENCES accounts(id),
    dimension       TEXT NOT NULL CHECK (dimension IN ('delivery','commercial')),
    green_criteria  TEXT NOT NULL,
    amber_criteria  TEXT NOT NULL,
    red_criteria    TEXT NOT NULL,
    unknown_criteria TEXT NOT NULL,
    effective_on    TEXT NOT NULL,
    author          TEXT NOT NULL,
    source_note     TEXT,
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL,
    archived        INTEGER NOT NULL DEFAULT 0,
    archived_at     TEXT,
    archived_by     TEXT
);
CREATE UNIQUE INDEX idx_status_criteria_portfolio_live
ON status_criteria_versions(dimension) WHERE account_id IS NULL AND archived=0;
CREATE INDEX idx_status_criteria_account ON status_criteria_versions(account_id,dimension,effective_on);

INSERT INTO status_criteria_versions
(id,account_id,dimension,green_criteria,amber_criteria,red_criteria,unknown_criteria,
 effective_on,author,source_note,created_at,updated_at)
VALUES
('criteria-delivery-v1',NULL,'delivery','Value delivery is on plan and material assumptions remain true.',
 'A named recovery action can restore delivery without a leadership tradeoff.',
 'Delivery requires leadership to choose among explicit options or tradeoffs.',
 'There is not enough current evidence to make the assessment.','2026-07-31','operator',
 'Internal Ops v2 seeded default',datetime('now'),datetime('now')),
('criteria-commercial-v1',NULL,'commercial','Commercial motion is on plan and material assumptions remain true.',
 'A named recovery action can restore the commercial motion without a leadership tradeoff.',
 'The commercial motion requires leadership to choose among explicit options or tradeoffs.',
 'There is not enough current evidence to make the assessment.','2026-07-31','operator',
 'Internal Ops v2 seeded default',datetime('now'),datetime('now'));

CREATE TABLE account_status_assessments (
    id                       TEXT PRIMARY KEY,
    account_id               TEXT NOT NULL REFERENCES accounts(id),
    dimension                TEXT NOT NULL CHECK (dimension IN ('delivery','commercial')),
    value                    TEXT NOT NULL CHECK (value IN ('on_track','at_risk','off_track','unknown')),
    rationale                TEXT,
    criteria_version_id      TEXT REFERENCES status_criteria_versions(id),
    recovery_owner_person_id TEXT REFERENCES persons(id),
    recovery_action          TEXT,
    recovery_due_on          TEXT,
    leadership_ask_id        TEXT,
    leadership_not_applicable_reason TEXT,
    assessed_on              TEXT NOT NULL,
    author                   TEXT NOT NULL,
    supersedes_id            TEXT REFERENCES account_status_assessments(id),
    legacy_response_gap      INTEGER NOT NULL DEFAULT 0,
    created_at               TEXT NOT NULL,
    updated_at               TEXT NOT NULL,
    archived                 INTEGER NOT NULL DEFAULT 0,
    archived_at              TEXT,
    archived_by              TEXT,
    CHECK (value<>'at_risk' OR legacy_response_gap=1 OR
           (recovery_owner_person_id IS NOT NULL AND recovery_action IS NOT NULL AND recovery_due_on IS NOT NULL)),
    CHECK (value<>'off_track' OR legacy_response_gap=1 OR
           (recovery_owner_person_id IS NOT NULL AND recovery_action IS NOT NULL AND recovery_due_on IS NOT NULL
            AND (leadership_ask_id IS NOT NULL OR leadership_not_applicable_reason IS NOT NULL)))
);
CREATE INDEX idx_status_assessment_account ON account_status_assessments(account_id,dimension,assessed_on);

INSERT INTO account_status_assessments
(id,account_id,dimension,value,rationale,criteria_version_id,assessed_on,author,legacy_response_gap,created_at,updated_at)
SELECT 'backfill-delivery-'||id,id,'delivery',delivery_status,delivery_status_rationale,
       'criteria-delivery-v1',COALESCE(delivery_status_assessed_on,date('now')),'migration-0026',
       CASE WHEN delivery_status IN ('at_risk','off_track') THEN 1 ELSE 0 END,datetime('now'),datetime('now')
FROM accounts WHERE delivery_status<>'unknown';
INSERT INTO account_status_assessments
(id,account_id,dimension,value,rationale,criteria_version_id,assessed_on,author,legacy_response_gap,created_at,updated_at)
SELECT 'backfill-commercial-'||id,id,'commercial',commercial_status,commercial_status_rationale,
       'criteria-commercial-v1',COALESCE(commercial_status_assessed_on,date('now')),'migration-0026',
       CASE WHEN commercial_status IN ('at_risk','off_track') THEN 1 ELSE 0 END,datetime('now'),datetime('now')
FROM accounts WHERE commercial_status<>'unknown';

-- Existing amber/red snapshots retain an explicit legacy gap instead of fabricated owners or
-- actions. New assessments cannot set this API-hidden migration flag.

CREATE TABLE account_reviews (
    id                    TEXT PRIMARY KEY,
    account_id            TEXT NOT NULL REFERENCES accounts(id),
    review_type           TEXT NOT NULL DEFAULT 'quarterly' CHECK (review_type IN ('weekly','monthly','quarterly','ad_hoc')),
    scheduled_on          TEXT,
    held_on               TEXT,
    chair_person_id       TEXT REFERENCES persons(id),
    source_interaction_id TEXT REFERENCES interactions(id),
    status                TEXT NOT NULL DEFAULT 'planned' CHECK (status IN ('planned','held','cancelled')),
    cancellation_reason   TEXT,
    created_at            TEXT NOT NULL,
    updated_at            TEXT NOT NULL,
    archived              INTEGER NOT NULL DEFAULT 0,
    archived_at           TEXT,
    archived_by           TEXT,
    CHECK (status<>'held' OR (held_on IS NOT NULL AND source_interaction_id IS NOT NULL)),
    CHECK (status<>'cancelled' OR cancellation_reason IS NOT NULL)
);
CREATE INDEX idx_account_reviews ON account_reviews(account_id,scheduled_on,status);

CREATE TABLE account_review_participants (
    review_id  TEXT NOT NULL REFERENCES account_reviews(id),
    person_id  TEXT NOT NULL REFERENCES persons(id),
    role       TEXT,
    PRIMARY KEY (review_id,person_id)
);
CREATE TRIGGER trg_review_participant_valence BEFORE INSERT ON account_review_participants
WHEN NOT EXISTS (SELECT 1 FROM persons p WHERE p.id=NEW.person_id AND p.affiliation='valence')
BEGIN SELECT RAISE(ABORT,'review participants must be Valence people'); END;

CREATE TABLE operator_views (
    id             TEXT PRIMARY KEY,
    account_id     TEXT NOT NULL REFERENCES accounts(id),
    body           TEXT NOT NULL,
    author         TEXT NOT NULL,
    assessed_on    TEXT NOT NULL,
    supersedes_id  TEXT REFERENCES operator_views(id),
    created_at     TEXT NOT NULL,
    updated_at     TEXT NOT NULL,
    archived       INTEGER NOT NULL DEFAULT 0,
    archived_at    TEXT,
    archived_by    TEXT
);
CREATE INDEX idx_operator_views_account ON operator_views(account_id,assessed_on);
CREATE TRIGGER trg_operator_views_immutable_update BEFORE UPDATE ON operator_views
BEGIN SELECT RAISE(ABORT,'operator views are append-only'); END;
CREATE TRIGGER trg_operator_views_immutable_delete BEFORE DELETE ON operator_views
BEGIN SELECT RAISE(ABORT,'operator views are append-only'); END;

CREATE TABLE commitments_new (
    id                    TEXT PRIMARY KEY,
    account_id            TEXT NOT NULL REFERENCES accounts(id),
    program_id            TEXT REFERENCES programs(id),
    account_review_id     TEXT REFERENCES account_reviews(id),
    commitment_class      TEXT NOT NULL DEFAULT 'client' CHECK (commitment_class IN
                          ('client','leadership_to_operator','operator_to_internal','internal_peer')),
    description           TEXT NOT NULL,
    responsible_party_id  TEXT NOT NULL REFERENCES persons(id),
    internal_owner_id     TEXT NOT NULL REFERENCES persons(id),
    due_date              TEXT NOT NULL,
    status                TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open','closed')),
    acknowledged_by_id    TEXT REFERENCES persons(id),
    closed_on             TEXT,
    closed_by             TEXT,
    close_note            TEXT,
    source_interaction_id TEXT REFERENCES interactions(id),
    source_reference_id   TEXT REFERENCES source_references(id),
    client_visible        INTEGER NOT NULL DEFAULT 0,
    created_at            TEXT NOT NULL,
    updated_at            TEXT NOT NULL,
    archived              INTEGER NOT NULL DEFAULT 0,
    archived_at           TEXT,
    archived_by           TEXT,
    CHECK (program_id IS NOT NULL OR account_review_id IS NOT NULL OR commitment_class<>'client')
);
INSERT INTO commitments_new
(id,account_id,program_id,account_review_id,commitment_class,description,responsible_party_id,
 internal_owner_id,due_date,status,acknowledged_by_id,closed_on,closed_by,close_note,
 source_interaction_id,source_reference_id,client_visible,created_at,updated_at,archived,archived_at,archived_by)
SELECT c.id,p.account_id,c.program_id,NULL,
       'client',
       c.description,c.responsible_party_id,c.internal_owner_id,c.due_date,c.status,
       c.acknowledged_by_id,c.closed_on,c.closed_by,c.close_note,c.source_interaction_id,
       c.source_reference_id,c.client_visible,c.created_at,c.updated_at,c.archived,c.archived_at,c.archived_by
FROM commitments c JOIN programs p ON p.id=c.program_id;
DROP TABLE commitments;
ALTER TABLE commitments_new RENAME TO commitments;
CREATE INDEX idx_commitments_program ON commitments(program_id,status);
CREATE INDEX idx_commitments_account ON commitments(account_id,status,due_date);
CREATE INDEX idx_commitments_due ON commitments(status,due_date);

CREATE TABLE decisions_new (
    id                    TEXT PRIMARY KEY,
    account_id            TEXT NOT NULL REFERENCES accounts(id),
    program_id            TEXT REFERENCES programs(id),
    account_review_id     TEXT REFERENCES account_reviews(id),
    description           TEXT NOT NULL,
    decided_on            TEXT,
    decided_by_id         TEXT REFERENCES persons(id),
    rationale             TEXT,
    supersedes_id         TEXT REFERENCES decisions_new(id),
    status                TEXT NOT NULL DEFAULT 'recorded' CHECK (status IN ('recorded','superseded')),
    source_interaction_id TEXT REFERENCES interactions(id),
    source_reference_id   TEXT REFERENCES source_references(id),
    created_at            TEXT NOT NULL,
    updated_at            TEXT NOT NULL,
    archived              INTEGER NOT NULL DEFAULT 0,
    archived_at           TEXT,
    archived_by           TEXT
);
INSERT INTO decisions_new
(id,account_id,program_id,account_review_id,description,decided_on,decided_by_id,rationale,
 supersedes_id,status,source_interaction_id,source_reference_id,created_at,updated_at,archived,archived_at,archived_by)
SELECT d.id,p.account_id,d.program_id,NULL,d.description,d.decided_on,d.decided_by_id,d.rationale,
       d.supersedes_id,d.status,d.source_interaction_id,d.source_reference_id,d.created_at,d.updated_at,
       d.archived,d.archived_at,d.archived_by
FROM decisions d JOIN programs p ON p.id=d.program_id;
DROP TABLE decisions;
ALTER TABLE decisions_new RENAME TO decisions;
CREATE INDEX idx_decisions_program ON decisions(program_id);
CREATE INDEX idx_decisions_account ON decisions(account_id,decided_on);

-- This trigger belongs to the child table, so SQLite does not remove it when the
-- parent is rebuilt. Drop and restore it around the one-time rebuild.
DROP TRIGGER trg_gendoc_person_account_insert;

CREATE TABLE generated_documents_new (
    id            TEXT PRIMARY KEY,
    account_id    TEXT REFERENCES accounts(id),
    program_id    TEXT REFERENCES programs(id),
    kind          TEXT NOT NULL CHECK (kind IN (
                    'pre_call_brief','business_case','champion_kit','value_review','kickoff_deck','team_update',
                    'internal_account_brief','internal_review_packet','internal_challenge_sheet',
                    'forecast_submission','monthly_portfolio_brief','colleague_call_brief',
                    'coverage_brief','coverage_return_brief')),
    title         TEXT NOT NULL,
    body_markdown TEXT NOT NULL,
    status        TEXT NOT NULL DEFAULT 'draft' CHECK (status IN ('draft','reviewed','sent','discarded')),
    reviewed_on   TEXT,
    reviewed_by   TEXT,
    generated_at            TEXT NOT NULL,
    data_current_through    TEXT,
    missing_or_stale_note   TEXT,
    audience      TEXT NOT NULL DEFAULT 'internal' CHECK (audience IN ('internal','client_facing')),
    audience_profile TEXT NOT NULL DEFAULT 'working' CHECK (audience_profile IN ('working','leadership')),
    source_job_id TEXT,
    source_interaction_id TEXT REFERENCES interactions(id),
    created_at    TEXT NOT NULL,
    updated_at    TEXT NOT NULL,
    archived      INTEGER NOT NULL DEFAULT 0,
    archived_at   TEXT,
    archived_by   TEXT,
    CHECK (status IN ('draft','discarded') OR (reviewed_on IS NOT NULL AND reviewed_by IS NOT NULL))
);
INSERT INTO generated_documents_new
(id,account_id,program_id,kind,title,body_markdown,status,reviewed_on,reviewed_by,
 generated_at,data_current_through,missing_or_stale_note,audience,audience_profile,
 source_job_id,source_interaction_id,created_at,updated_at,archived,archived_at,archived_by)
SELECT id,account_id,program_id,kind,title,body_markdown,status,reviewed_on,reviewed_by,
       generated_at,data_current_through,missing_or_stale_note,audience,'working',
       source_job_id,source_interaction_id,created_at,updated_at,archived,archived_at,archived_by
FROM generated_documents;
DROP TABLE generated_documents;
ALTER TABLE generated_documents_new RENAME TO generated_documents;
CREATE INDEX idx_gendoc_account ON generated_documents(account_id,kind,generated_at);
CREATE INDEX idx_gendoc_status ON generated_documents(status) WHERE archived=0;

CREATE TRIGGER trg_gendoc_program_account_insert BEFORE INSERT ON generated_documents
WHEN NEW.account_id IS NOT NULL AND NEW.program_id IS NOT NULL AND NOT EXISTS (
    SELECT 1 FROM programs p WHERE p.id=NEW.program_id AND p.account_id=NEW.account_id)
BEGIN SELECT RAISE(ABORT,'document program belongs to a different account'); END;
CREATE TRIGGER trg_gendoc_program_account_update BEFORE UPDATE OF account_id,program_id ON generated_documents
WHEN NEW.account_id IS NOT NULL AND NEW.program_id IS NOT NULL AND NOT EXISTS (
    SELECT 1 FROM programs p WHERE p.id=NEW.program_id AND p.account_id=NEW.account_id)
BEGIN SELECT RAISE(ABORT,'document program belongs to a different account'); END;
CREATE TRIGGER trg_gendoc_person_account_insert BEFORE INSERT ON generated_document_people
WHEN NOT EXISTS (
    SELECT 1 FROM generated_documents gd JOIN persons p ON p.id=NEW.person_id
    WHERE gd.id=NEW.document_id AND gd.account_id=p.account_id)
BEGIN SELECT RAISE(ABORT,'document person belongs to a different account'); END;

CREATE TABLE report_templates (
    id               TEXT PRIMARY KEY,
    kind             TEXT NOT NULL,
    name             TEXT NOT NULL,
    audience_profile TEXT NOT NULL CHECK (audience_profile IN ('working','leadership')),
    headings_json    TEXT NOT NULL DEFAULT '{}',
    effective_on     TEXT NOT NULL,
    author           TEXT NOT NULL,
    created_at       TEXT NOT NULL,
    updated_at       TEXT NOT NULL,
    archived         INTEGER NOT NULL DEFAULT 0,
    archived_at      TEXT,
    archived_by      TEXT
);

CREATE TABLE generated_document_sources (
    id               TEXT PRIMARY KEY,
    document_id      TEXT NOT NULL REFERENCES generated_documents(id),
    record_type      TEXT NOT NULL,
    record_id        TEXT NOT NULL,
    record_version   TEXT,
    inclusion_reason TEXT NOT NULL,
    visibility_class TEXT NOT NULL DEFAULT 'internal',
    created_at       TEXT NOT NULL,
    UNIQUE(document_id,record_type,record_id,inclusion_reason)
);
CREATE INDEX idx_document_sources_doc ON generated_document_sources(document_id);
CREATE TRIGGER trg_document_sources_immutable_update BEFORE UPDATE ON generated_document_sources
BEGIN SELECT RAISE(ABORT,'generated document sources are immutable'); END;
CREATE TRIGGER trg_document_sources_immutable_delete BEFORE DELETE ON generated_document_sources
BEGIN SELECT RAISE(ABORT,'generated document sources are immutable'); END;

CREATE TRIGGER trg_commitment_scope_insert BEFORE INSERT ON commitments
WHEN (NEW.program_id IS NOT NULL AND NOT EXISTS (
        SELECT 1 FROM programs p WHERE p.id=NEW.program_id AND p.account_id=NEW.account_id))
  OR (NEW.account_review_id IS NOT NULL AND NOT EXISTS (
        SELECT 1 FROM account_reviews r WHERE r.id=NEW.account_review_id AND r.account_id=NEW.account_id))
BEGIN SELECT RAISE(ABORT,'commitment context belongs to a different account'); END;
CREATE TRIGGER trg_commitment_scope_update BEFORE UPDATE OF account_id,program_id,account_review_id ON commitments
WHEN (NEW.program_id IS NOT NULL AND NOT EXISTS (
        SELECT 1 FROM programs p WHERE p.id=NEW.program_id AND p.account_id=NEW.account_id))
  OR (NEW.account_review_id IS NOT NULL AND NOT EXISTS (
        SELECT 1 FROM account_reviews r WHERE r.id=NEW.account_review_id AND r.account_id=NEW.account_id))
BEGIN SELECT RAISE(ABORT,'commitment context belongs to a different account'); END;
CREATE TRIGGER trg_decision_scope_insert BEFORE INSERT ON decisions
WHEN (NEW.program_id IS NOT NULL AND NOT EXISTS (
        SELECT 1 FROM programs p WHERE p.id=NEW.program_id AND p.account_id=NEW.account_id))
  OR (NEW.account_review_id IS NOT NULL AND NOT EXISTS (
        SELECT 1 FROM account_reviews r WHERE r.id=NEW.account_review_id AND r.account_id=NEW.account_id))
BEGIN SELECT RAISE(ABORT,'decision context belongs to a different account'); END;
CREATE TRIGGER trg_decision_scope_update BEFORE UPDATE OF account_id,program_id,account_review_id ON decisions
WHEN (NEW.program_id IS NOT NULL AND NOT EXISTS (
        SELECT 1 FROM programs p WHERE p.id=NEW.program_id AND p.account_id=NEW.account_id))
  OR (NEW.account_review_id IS NOT NULL AND NOT EXISTS (
        SELECT 1 FROM account_reviews r WHERE r.id=NEW.account_review_id AND r.account_id=NEW.account_id))
BEGIN SELECT RAISE(ABORT,'decision context belongs to a different account'); END;

PRAGMA foreign_keys = ON;
