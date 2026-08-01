-- Migration 0027 — Internal Ops Stage 10.1: period-scoped forecast ledger.
PRAGMA foreign_keys = ON;

CREATE TABLE forecast_periods (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    starts_on TEXT NOT NULL,
    ends_on TEXT NOT NULL,
    cadence TEXT NOT NULL CHECK (cadence IN ('weekly','monthly','quarterly','annual','custom')),
    scenario_type TEXT NOT NULL DEFAULT 'operating',
    timezone TEXT NOT NULL DEFAULT 'America/New_York',
    status TEXT NOT NULL DEFAULT 'draft' CHECK (status IN ('draft','open','locked','closed')),
    locked_at TEXT,
    locked_by TEXT,
    closed_at TEXT,
    closed_by TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    archived INTEGER NOT NULL DEFAULT 0,
    archived_at TEXT,
    archived_by TEXT,
    CHECK (ends_on>=starts_on),
    CHECK (status NOT IN ('locked','closed') OR locked_at IS NOT NULL),
    CHECK (status<>'closed' OR closed_at IS NOT NULL)
);
CREATE INDEX idx_forecast_period_dates ON forecast_periods(starts_on,ends_on,status);

CREATE TABLE forecast_entries (
    id TEXT PRIMARY KEY,
    period_id TEXT NOT NULL REFERENCES forecast_periods(id),
    account_id TEXT NOT NULL REFERENCES accounts(id),
    opportunity_id TEXT REFERENCES expansion_opportunities(id),
    contract_version_id TEXT REFERENCES contract_versions(id),
    category TEXT NOT NULL CHECK (category IN ('commit','best_case','pipeline','omitted')),
    amount REAL CHECK (amount IS NULL OR amount>=0),
    currency TEXT CHECK (currency IS NULL OR (length(currency)=3 AND currency=upper(currency))),
    price_basis TEXT CHECK (price_basis IS NULL OR price_basis IN ('arr','tcv','one_time','monthly')),
    probability REAL CHECK (probability IS NULL OR (probability>=0 AND probability<=1)),
    probability_rationale TEXT,
    amount_rationale TEXT,
    author TEXT NOT NULL,
    assessed_on TEXT NOT NULL,
    expected_decision_date TEXT,
    help_needed_note TEXT,
    renewal_budget_owner_person_id TEXT REFERENCES persons(id),
    renewal_position TEXT CHECK (renewal_position IS NULL OR renewal_position IN
        ('confirmed_intent','commercial_review','procurement_in_progress','unknown')),
    unresolved_conditions TEXT,
    omitted_reason TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    archived INTEGER NOT NULL DEFAULT 0,
    archived_at TEXT,
    archived_by TEXT,
    CHECK ((opportunity_id IS NOT NULL) <> (contract_version_id IS NOT NULL)),
    CHECK (category<>'omitted' OR omitted_reason IS NOT NULL),
    CHECK (probability IS NULL OR probability_rationale IS NOT NULL)
);
CREATE UNIQUE INDEX idx_forecast_entry_opportunity_live
ON forecast_entries(period_id,opportunity_id) WHERE opportunity_id IS NOT NULL AND archived=0;
CREATE UNIQUE INDEX idx_forecast_entry_contract_live
ON forecast_entries(period_id,contract_version_id) WHERE contract_version_id IS NOT NULL AND archived=0;
CREATE INDEX idx_forecast_entry_account ON forecast_entries(account_id,period_id,category);

CREATE TABLE forecast_entry_sources (
    id TEXT PRIMARY KEY,
    entry_id TEXT NOT NULL REFERENCES forecast_entries(id),
    interaction_id TEXT REFERENCES interactions(id),
    source_reference_id TEXT REFERENCES source_references(id),
    growth_plan_line_id TEXT REFERENCES growth_plan_lines(id),
    revenue_event_id TEXT REFERENCES revenue_events(id),
    ask_calendar_id TEXT REFERENCES ask_calendars(id),
    note TEXT,
    created_at TEXT NOT NULL,
    CHECK ((interaction_id IS NOT NULL)+(source_reference_id IS NOT NULL)+
           (growth_plan_line_id IS NOT NULL)+(revenue_event_id IS NOT NULL)+
           (ask_calendar_id IS NOT NULL)=1)
);
CREATE INDEX idx_forecast_sources_entry ON forecast_entry_sources(entry_id);

CREATE TABLE forecast_change_events (
    id TEXT PRIMARY KEY,
    entry_id TEXT NOT NULL REFERENCES forecast_entries(id),
    category_before TEXT NOT NULL,
    category_after TEXT NOT NULL,
    driver TEXT NOT NULL,
    actor TEXT NOT NULL,
    changed_at TEXT NOT NULL,
    source_interaction_id TEXT REFERENCES interactions(id),
    source_reference_id TEXT REFERENCES source_references(id),
    corrects_event_id TEXT REFERENCES forecast_change_events(id),
    created_at TEXT NOT NULL,
    CHECK (category_before<>category_after)
);
CREATE INDEX idx_forecast_changes_entry ON forecast_change_events(entry_id,changed_at);

CREATE TABLE forecast_submissions (
    id TEXT PRIMARY KEY,
    period_id TEXT NOT NULL REFERENCES forecast_periods(id),
    document_id TEXT NOT NULL REFERENCES generated_documents(id),
    submitted_at TEXT NOT NULL,
    actor TEXT NOT NULL,
    baseline_kind TEXT NOT NULL CHECK (baseline_kind IN ('none','opening','previous_submission')),
    prior_submission_id TEXT REFERENCES forecast_submissions(id),
    created_at TEXT NOT NULL
);
CREATE INDEX idx_forecast_submissions_period ON forecast_submissions(period_id,submitted_at);

CREATE TABLE forecast_submission_lines (
    id TEXT PRIMARY KEY,
    submission_id TEXT NOT NULL REFERENCES forecast_submissions(id),
    entry_id TEXT NOT NULL REFERENCES forecast_entries(id),
    account_id TEXT NOT NULL REFERENCES accounts(id),
    target_type TEXT NOT NULL CHECK (target_type IN ('opportunity','renewal')),
    target_id TEXT NOT NULL,
    category TEXT NOT NULL,
    amount REAL,
    currency TEXT,
    price_basis TEXT,
    probability REAL,
    evidence_json TEXT NOT NULL,
    help_needed_note TEXT,
    source_manifest_json TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL,
    UNIQUE(submission_id,entry_id)
);

CREATE TABLE forecast_opening_snapshots (
    id TEXT PRIMARY KEY,
    period_id TEXT NOT NULL UNIQUE REFERENCES forecast_periods(id),
    locked_at TEXT NOT NULL,
    locked_by TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE forecast_opening_lines (
    id TEXT PRIMARY KEY,
    snapshot_id TEXT NOT NULL REFERENCES forecast_opening_snapshots(id),
    entry_id TEXT NOT NULL,
    account_id TEXT NOT NULL REFERENCES accounts(id),
    target_type TEXT NOT NULL CHECK (target_type IN ('opportunity','renewal')),
    target_id TEXT NOT NULL,
    category TEXT NOT NULL,
    amount REAL,
    currency TEXT,
    price_basis TEXT,
    probability REAL,
    source_manifest_json TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL,
    UNIQUE(snapshot_id,entry_id)
);

CREATE TABLE renewal_outcome_events (
    id TEXT PRIMARY KEY,
    account_id TEXT NOT NULL REFERENCES accounts(id),
    contract_version_id TEXT NOT NULL REFERENCES contract_versions(id),
    outcome TEXT NOT NULL CHECK (outcome IN ('renewed','churned','deferred','unresolved')),
    occurred_on TEXT NOT NULL,
    actual_amount REAL CHECK (actual_amount IS NULL OR actual_amount>=0),
    currency TEXT CHECK (currency IS NULL OR (length(currency)=3 AND currency=upper(currency))),
    price_basis TEXT CHECK (price_basis IS NULL OR price_basis IN ('arr','tcv','one_time','monthly')),
    source_reference_id TEXT REFERENCES source_references(id),
    note TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    archived INTEGER NOT NULL DEFAULT 0,
    archived_at TEXT,
    archived_by TEXT
);

-- Account-scope checks for all typed links.
CREATE TRIGGER trg_forecast_entry_scope_insert BEFORE INSERT ON forecast_entries
WHEN (NEW.opportunity_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM expansion_opportunities o WHERE o.id=NEW.opportunity_id AND o.account_id=NEW.account_id))
 OR (NEW.contract_version_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM contract_versions c WHERE c.id=NEW.contract_version_id AND c.account_id=NEW.account_id))
 OR (NEW.renewal_budget_owner_person_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM persons p WHERE p.id=NEW.renewal_budget_owner_person_id AND p.account_id=NEW.account_id))
BEGIN SELECT RAISE(ABORT,'forecast entry link belongs to a different account'); END;
CREATE TRIGGER trg_forecast_entry_scope_update BEFORE UPDATE OF account_id,opportunity_id,contract_version_id,renewal_budget_owner_person_id ON forecast_entries
WHEN (NEW.opportunity_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM expansion_opportunities o WHERE o.id=NEW.opportunity_id AND o.account_id=NEW.account_id))
 OR (NEW.contract_version_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM contract_versions c WHERE c.id=NEW.contract_version_id AND c.account_id=NEW.account_id))
 OR (NEW.renewal_budget_owner_person_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM persons p WHERE p.id=NEW.renewal_budget_owner_person_id AND p.account_id=NEW.account_id))
BEGIN SELECT RAISE(ABORT,'forecast entry link belongs to a different account'); END;
CREATE TRIGGER trg_forecast_source_scope BEFORE INSERT ON forecast_entry_sources
WHEN NOT EXISTS (
 SELECT 1 FROM forecast_entries e WHERE e.id=NEW.entry_id AND
   (NEW.interaction_id IS NULL OR EXISTS (SELECT 1 FROM interactions i WHERE i.id=NEW.interaction_id AND i.account_id=e.account_id)) AND
   (NEW.growth_plan_line_id IS NULL OR EXISTS (SELECT 1 FROM growth_plan_lines g WHERE g.id=NEW.growth_plan_line_id AND g.account_id=e.account_id)) AND
   (NEW.revenue_event_id IS NULL OR EXISTS (SELECT 1 FROM revenue_events r WHERE r.id=NEW.revenue_event_id AND r.account_id=e.account_id)) AND
   (NEW.ask_calendar_id IS NULL OR EXISTS (SELECT 1 FROM ask_calendars a WHERE a.id=NEW.ask_calendar_id AND a.account_id=e.account_id)))
BEGIN SELECT RAISE(ABORT,'forecast source belongs to a different account'); END;
CREATE TRIGGER trg_renewal_outcome_scope BEFORE INSERT ON renewal_outcome_events
WHEN NOT EXISTS (SELECT 1 FROM contract_versions c WHERE c.id=NEW.contract_version_id AND c.account_id=NEW.account_id)
BEGIN SELECT RAISE(ABORT,'renewal outcome contract belongs to a different account'); END;

-- Frozen forecast artifacts are append-only.
CREATE TRIGGER trg_forecast_submission_lines_immutable_update BEFORE UPDATE ON forecast_submission_lines BEGIN SELECT RAISE(ABORT,'forecast submission lines are immutable'); END;
CREATE TRIGGER trg_forecast_submission_lines_immutable_delete BEFORE DELETE ON forecast_submission_lines BEGIN SELECT RAISE(ABORT,'forecast submission lines are immutable'); END;
CREATE TRIGGER trg_forecast_opening_lines_immutable_update BEFORE UPDATE ON forecast_opening_lines BEGIN SELECT RAISE(ABORT,'forecast opening lines are immutable'); END;
CREATE TRIGGER trg_forecast_opening_lines_immutable_delete BEFORE DELETE ON forecast_opening_lines BEGIN SELECT RAISE(ABORT,'forecast opening lines are immutable'); END;
CREATE TRIGGER trg_forecast_changes_immutable_update BEFORE UPDATE ON forecast_change_events BEGIN SELECT RAISE(ABORT,'forecast change events are append-only'); END;
CREATE TRIGGER trg_forecast_changes_immutable_delete BEFORE DELETE ON forecast_change_events BEGIN SELECT RAISE(ABORT,'forecast change events are append-only'); END;
