-- Migration 0004 — v1 commercial & deployment control
-- Expansion opportunities, contract versions + renewal motion, phase gates,
-- deployment moments + light comms entries, compliance/readiness checklist,
-- scope-change entries, and the governance-cadence fields deferred from v0.
-- Canonical CRM/contract data is modeled as a synced read-only copy + editable
-- overlay (Section 3 source-authority matrix); we never recompute it.

PRAGMA foreign_keys = ON;

-- Governance cadence lived on Program in Section 4 but was deferred to v1.
ALTER TABLE programs ADD COLUMN governance_steering TEXT;   -- steering forum
ALTER TABLE programs ADD COLUMN governance_rhythm   TEXT;   -- working rhythm
ALTER TABLE programs ADD COLUMN next_qbr_date       TEXT;   -- date

-- Expansion opportunity: several per account. Staged budget; closed => outcome + reason.
CREATE TABLE expansion_opportunities (
    id                  TEXT PRIMARY KEY,
    account_id          TEXT NOT NULL REFERENCES accounts(id),
    name                TEXT NOT NULL,            -- named audience or use case
    use_case            TEXT,
    target_seats        INTEGER,
    expected_value      REAL,                     -- illustrative; not a synced CRM field
    sponsor_person_id   TEXT REFERENCES persons(id),
    budget_owner_person_id TEXT REFERENCES persons(id),
    funding_source      TEXT,
    supporting_evidence TEXT,
    decision_date       TEXT,
    budget_state        TEXT NOT NULL DEFAULT 'conceptually_supported'
        CHECK (budget_state IN ('conceptually_supported','in_planning','formally_allocated',
                                'requisition_created','procurement_approved','executed')),
    blockers            TEXT,
    next_action         TEXT,
    status              TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open','closed')),
    outcome             TEXT CHECK (outcome IN ('won','lost','deferred','merged','no_decision')),
    outcome_reason      TEXT,
    source_interaction_id TEXT REFERENCES interactions(id),
    created_at          TEXT NOT NULL,
    updated_at          TEXT NOT NULL,
    archived            INTEGER NOT NULL DEFAULT 0,
    archived_at         TEXT,
    archived_by         TEXT,
    -- closing an opportunity requires an outcome and a reason (Section 4)
    CHECK (status = 'open' OR (outcome IS NOT NULL AND outcome_reason IS NOT NULL))
);
CREATE INDEX idx_expansion_account ON expansion_opportunities(account_id, status);

-- Contract version: seats, price, dates, renewal mechanics; versioned, never overwritten.
-- Canonical fields come from CRM/RevOps (synced, read-only locally); operational
-- interpretation lives in the overlay_* fields with rationale/author/date.
CREATE TABLE contract_versions (
    id                     TEXT PRIMARY KEY,
    account_id             TEXT NOT NULL REFERENCES accounts(id),
    version_label          TEXT NOT NULL,          -- e.g. "v1", "amendment-2"
    seats                  INTEGER,
    price                  REAL,
    start_date             TEXT,
    end_date               TEXT,
    renewal_date           TEXT,                   -- canonical, contractual date
    notice_period_days     INTEGER,
    procurement_lead_days  INTEGER,
    amendments             TEXT,
    -- source authority: canonical copy is read-only locally
    source_system          TEXT DEFAULT 'crm',
    source_identifier      TEXT,
    editable_locally       INTEGER NOT NULL DEFAULT 0,
    supersedes_id          TEXT REFERENCES contract_versions(id),
    is_current             INTEGER NOT NULL DEFAULT 1,
    -- operational overlay (never overwrites canonical); rationale/author/date required if set
    overlay_expected_decision_date TEXT,
    overlay_rationale      TEXT,
    overlay_author         TEXT,
    overlay_assessed_on    TEXT,
    created_at             TEXT NOT NULL,
    updated_at             TEXT NOT NULL,
    archived               INTEGER NOT NULL DEFAULT 0,
    archived_at            TEXT,
    archived_by            TEXT,
    CHECK (overlay_expected_decision_date IS NULL
           OR (overlay_rationale IS NOT NULL AND overlay_assessed_on IS NOT NULL))
);
CREATE INDEX idx_contracts_account ON contract_versions(account_id, is_current);

-- Phase gate: configurable checklist per program; passes when items complete or waived.
CREATE TABLE phase_gates (
    id            TEXT PRIMARY KEY,
    program_id    TEXT NOT NULL REFERENCES programs(id),
    name          TEXT NOT NULL,
    gates_phase   TEXT CHECK (gates_phase IN ('foundation','launch','programmatic','expansion','renewal','closed')),
    status        TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open','passed','waived')),
    waiver_reason TEXT,
    waived_by     TEXT,
    passed_on     TEXT,
    created_at    TEXT NOT NULL,
    updated_at    TEXT NOT NULL,
    archived      INTEGER NOT NULL DEFAULT 0,
    archived_at   TEXT,
    archived_by   TEXT,
    -- a waived gate must record why (Section 4)
    CHECK (status <> 'waived' OR waiver_reason IS NOT NULL)
);
CREATE TABLE phase_gate_items (
    id           TEXT PRIMARY KEY,
    gate_id      TEXT NOT NULL REFERENCES phase_gates(id),
    description  TEXT NOT NULL,
    complete     INTEGER NOT NULL DEFAULT 0,
    completed_on TEXT,
    created_at   TEXT NOT NULL,
    updated_at   TEXT NOT NULL
);
CREATE INDEX idx_gates_program ON phase_gates(program_id, status);
CREATE INDEX idx_gate_items_gate ON phase_gate_items(gate_id);

-- Deployment moment: recurring client event the product embeds into.
CREATE TABLE deployment_moments (
    id                 TEXT PRIMARY KEY,
    program_id         TEXT NOT NULL REFERENCES programs(id),
    name               TEXT NOT NULL,
    type               TEXT NOT NULL DEFAULT 'business_event'
        CHECK (type IN ('talent_calendar','manager_workflow','business_event','proactive_coaching','comms_campaign')),
    client_owner_person_id TEXT REFERENCES persons(id),
    comms_hook         TEXT,
    integration_status TEXT NOT NULL DEFAULT 'not_started'
        CHECK (integration_status IN ('not_started','in_progress','live','not_applicable')),
    event_date         TEXT,
    outcome            TEXT,
    created_at         TEXT NOT NULL,
    updated_at         TEXT NOT NULL,
    archived           INTEGER NOT NULL DEFAULT 0,
    archived_at        TEXT,
    archived_by        TEXT
);
CREATE INDEX idx_moments_program ON deployment_moments(program_id);

-- Light comms entry: hangs off a program and optionally a deployment moment.
CREATE TABLE comms_entries (
    id          TEXT PRIMARY KEY,
    program_id  TEXT NOT NULL REFERENCES programs(id),
    moment_id   TEXT REFERENCES deployment_moments(id),
    audience    TEXT,
    message     TEXT,
    sender      TEXT,
    channel     TEXT CHECK (channel IN ('teams','web','slack','mobile','email','other')),
    send_date   TEXT,
    status      TEXT NOT NULL DEFAULT 'planned' CHECK (status IN ('planned','sent','cancelled')),
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL,
    archived    INTEGER NOT NULL DEFAULT 0,
    archived_at TEXT,
    archived_by TEXT
);
CREATE INDEX idx_comms_program ON comms_entries(program_id);

-- Compliance / readiness checklist: per-program (and optional region) lanes.
CREATE TABLE compliance_items (
    id           TEXT PRIMARY KEY,
    program_id   TEXT NOT NULL REFERENCES programs(id),
    region       TEXT,
    lane         TEXT NOT NULL CHECK (lane IN ('it_security','legal_dpo','works_council',
                 'channel_setup','localization_qa','trust_comms','hr_boundary')),
    status       TEXT NOT NULL DEFAULT 'not_started'
                 CHECK (status IN ('not_started','in_progress','complete','blocked','not_applicable')),
    owner_person_id TEXT REFERENCES persons(id),
    notes        TEXT,
    created_at   TEXT NOT NULL,
    updated_at   TEXT NOT NULL,
    archived     INTEGER NOT NULL DEFAULT 0,
    archived_at  TEXT,
    archived_by  TEXT
);
CREATE INDEX idx_compliance_program ON compliance_items(program_id, lane);

-- Scope-change entry: lightweight record of what changed, who agreed, when, from where.
CREATE TABLE scope_changes (
    id                  TEXT PRIMARY KEY,
    program_id          TEXT NOT NULL REFERENCES programs(id),
    description         TEXT NOT NULL,
    agreed_by_person_id TEXT REFERENCES persons(id),
    changed_on          TEXT,
    source_interaction_id TEXT REFERENCES interactions(id),
    created_at          TEXT NOT NULL,
    updated_at          TEXT NOT NULL,
    archived            INTEGER NOT NULL DEFAULT 0,
    archived_at         TEXT,
    archived_by         TEXT
);
CREATE INDEX idx_scope_program ON scope_changes(program_id);
