-- Migration 0023 — Phase 3 Stage 7.5: five-slot qualification, operational agreements,
-- renewal command center inputs, and account growth plans.
--
-- Renewal is a read model over existing facts, not another status table. Operational triggers
-- stay outside the canonical contract copy. Growth-plan probability is a dated operator
-- assumption, never a governed stage score. Composite population overlap remains visible and
-- prevents additive totals rather than being silently discounted.

PRAGMA foreign_keys = ON;

-- Five slots on the existing opportunity. Budget owner already exists. Compliance is scoped
-- through a program because compliance_items are program records, not account records.
ALTER TABLE expansion_opportunities ADD COLUMN qualification_value_target_id TEXT REFERENCES value_targets(id);
ALTER TABLE expansion_opportunities ADD COLUMN qualification_ask_calendar_id TEXT REFERENCES ask_calendars(id);
ALTER TABLE expansion_opportunities ADD COLUMN qualification_champion_person_id TEXT REFERENCES persons(id);
ALTER TABLE expansion_opportunities ADD COLUMN qualification_program_id TEXT REFERENCES programs(id);

CREATE TABLE operational_agreements (
    id                    TEXT PRIMARY KEY,
    account_id            TEXT NOT NULL REFERENCES accounts(id),
    contract_version_id   TEXT NOT NULL REFERENCES contract_versions(id),
    name                  TEXT NOT NULL,
    source_kind           TEXT NOT NULL CHECK (source_kind IN ('signed_paper','agreed_conversation')),
    source_reference_id   TEXT REFERENCES source_references(id),
    source_interaction_id TEXT REFERENCES interactions(id),
    value_target_id       TEXT NOT NULL REFERENCES value_targets(id),
    effective_on          TEXT NOT NULL,
    expires_on            TEXT,
    seat_band_min         INTEGER NOT NULL CHECK (seat_band_min > 0),
    seat_band_max         INTEGER NOT NULL CHECK (seat_band_max >= seat_band_min),
    unit_price            REAL,
    currency              TEXT,
    agreed_process        TEXT NOT NULL,
    budget_owner_person_id TEXT REFERENCES persons(id),
    action_window_days    INTEGER NOT NULL DEFAULT 14 CHECK (action_window_days > 0),
    status                TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active','withdrawn','expired')),
    client_visible        INTEGER NOT NULL DEFAULT 0,
    notes                 TEXT,
    created_at            TEXT NOT NULL,
    updated_at            TEXT NOT NULL,
    archived              INTEGER NOT NULL DEFAULT 0,
    archived_at           TEXT,
    archived_by           TEXT,
    CHECK ((source_kind='signed_paper' AND source_reference_id IS NOT NULL)
        OR (source_kind='agreed_conversation' AND source_interaction_id IS NOT NULL)),
    CHECK (currency IS NULL OR (length(currency)=3 AND currency=upper(currency))),
    CHECK (client_visible=0 OR source_reference_id IS NOT NULL OR source_interaction_id IS NOT NULL)
);
CREATE INDEX idx_operational_agreement_account ON operational_agreements(account_id,status);

CREATE TABLE operational_agreement_events (
    id                    TEXT PRIMARY KEY,
    agreement_id          TEXT NOT NULL REFERENCES operational_agreements(id),
    account_id            TEXT NOT NULL REFERENCES accounts(id),
    value_at_fire         REAL NOT NULL,
    threshold_at_fire     REAL NOT NULL,
    freshness_as_of       TEXT NOT NULL,
    risk_note             TEXT,
    status                TEXT NOT NULL DEFAULT 'fired' CHECK (status IN ('fired','actioned','dismissed')),
    opportunity_id        TEXT REFERENCES expansion_opportunities(id),
    fired_at              TEXT NOT NULL,
    action_due_on         TEXT NOT NULL,
    actioned_at           TEXT,
    dismissal_reason      TEXT,
    created_at            TEXT NOT NULL,
    updated_at            TEXT NOT NULL,
    UNIQUE (agreement_id)
);
CREATE INDEX idx_operational_event_account ON operational_agreement_events(account_id,status,action_due_on);

CREATE TABLE account_growth_plans (
    id             TEXT PRIMARY KEY,
    account_id     TEXT NOT NULL REFERENCES accounts(id),
    name           TEXT NOT NULL,
    target_seats   INTEGER NOT NULL CHECK (target_seats > 0),
    target_date    TEXT NOT NULL,
    status         TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active','superseded','closed')),
    notes          TEXT,
    created_at     TEXT NOT NULL,
    updated_at     TEXT NOT NULL,
    archived       INTEGER NOT NULL DEFAULT 0,
    archived_at    TEXT,
    archived_by    TEXT
);
CREATE UNIQUE INDEX idx_growth_plan_active ON account_growth_plans(account_id)
    WHERE status='active' AND archived=0;

CREATE TABLE growth_plan_lines (
    id                    TEXT PRIMARY KEY,
    plan_id               TEXT NOT NULL REFERENCES account_growth_plans(id),
    account_id            TEXT NOT NULL REFERENCES accounts(id),
    name                  TEXT NOT NULL,
    segment_id            TEXT REFERENCES population_segments(id),
    view_id               TEXT REFERENCES population_views(id),
    opportunity_id        TEXT REFERENCES expansion_opportunities(id),
    budget_owner_person_id TEXT REFERENCES persons(id),
    funding_pool_id       TEXT REFERENCES funding_pools(id),
    ask_calendar_id       TEXT REFERENCES ask_calendars(id),
    seat_count            INTEGER NOT NULL CHECK (seat_count > 0),
    seat_price_low        REAL,
    seat_price_high       REAL,
    probability           REAL NOT NULL DEFAULT 0.5 CHECK (probability >= 0 AND probability <= 1),
    probability_author    TEXT NOT NULL,
    probability_assessed_on TEXT NOT NULL,
    ask_date              TEXT,
    status                TEXT NOT NULL DEFAULT 'planned' CHECK (status IN
                          ('planned','committed','funded','slipped','declined')),
    client_visible        INTEGER NOT NULL DEFAULT 0,
    source_reference_id   TEXT REFERENCES source_references(id),
    competitive_notes     TEXT,
    notes                 TEXT,
    created_at            TEXT NOT NULL,
    updated_at            TEXT NOT NULL,
    archived              INTEGER NOT NULL DEFAULT 0,
    archived_at           TEXT,
    archived_by           TEXT,
    CHECK ((segment_id IS NULL) <> (view_id IS NULL)),
    CHECK (seat_price_low IS NULL OR seat_price_low >= 0),
    CHECK (seat_price_high IS NULL OR seat_price_high >= 0),
    CHECK (seat_price_low IS NULL OR seat_price_high IS NULL OR seat_price_high >= seat_price_low),
    CHECK (client_visible=0 OR source_reference_id IS NOT NULL)
);
CREATE INDEX idx_growth_line_plan ON growth_plan_lines(plan_id,status);

-- Account-scope invariants must survive callers which bypass the API.
CREATE TRIGGER trg_opportunity_qualification_scope_insert BEFORE INSERT ON expansion_opportunities
WHEN (NEW.qualification_value_target_id IS NOT NULL AND NOT EXISTS (
        SELECT 1 FROM value_targets v WHERE v.id=NEW.qualification_value_target_id AND v.account_id=NEW.account_id))
  OR (NEW.qualification_ask_calendar_id IS NOT NULL AND NOT EXISTS (
        SELECT 1 FROM ask_calendars a WHERE a.id=NEW.qualification_ask_calendar_id
        AND a.account_id=NEW.account_id AND (a.opportunity_id IS NULL OR a.opportunity_id=NEW.id)))
  OR (NEW.qualification_champion_person_id IS NOT NULL AND NOT EXISTS (
        SELECT 1 FROM persons p WHERE p.id=NEW.qualification_champion_person_id AND p.account_id=NEW.account_id))
  OR (NEW.qualification_program_id IS NOT NULL AND NOT EXISTS (
        SELECT 1 FROM programs p WHERE p.id=NEW.qualification_program_id AND p.account_id=NEW.account_id))
  OR (NEW.budget_owner_person_id IS NOT NULL AND NOT EXISTS (
        SELECT 1 FROM persons p WHERE p.id=NEW.budget_owner_person_id AND p.account_id=NEW.account_id))
  OR (NEW.funding_pool_id IS NOT NULL AND NOT EXISTS (
        SELECT 1 FROM funding_pools f WHERE f.id=NEW.funding_pool_id AND f.account_id=NEW.account_id))
BEGIN SELECT RAISE(ABORT, 'opportunity qualification belongs to a different account'); END;

CREATE TRIGGER trg_opportunity_qualification_scope_update BEFORE UPDATE OF
qualification_value_target_id,qualification_ask_calendar_id,qualification_champion_person_id,
qualification_program_id,budget_owner_person_id,funding_pool_id ON expansion_opportunities
WHEN (NEW.qualification_value_target_id IS NOT NULL AND NOT EXISTS (
        SELECT 1 FROM value_targets v WHERE v.id=NEW.qualification_value_target_id AND v.account_id=NEW.account_id))
  OR (NEW.qualification_ask_calendar_id IS NOT NULL AND NOT EXISTS (
        SELECT 1 FROM ask_calendars a WHERE a.id=NEW.qualification_ask_calendar_id
        AND a.account_id=NEW.account_id AND (a.opportunity_id IS NULL OR a.opportunity_id=NEW.id)))
  OR (NEW.qualification_champion_person_id IS NOT NULL AND NOT EXISTS (
        SELECT 1 FROM persons p WHERE p.id=NEW.qualification_champion_person_id AND p.account_id=NEW.account_id))
  OR (NEW.qualification_program_id IS NOT NULL AND NOT EXISTS (
        SELECT 1 FROM programs p WHERE p.id=NEW.qualification_program_id AND p.account_id=NEW.account_id))
  OR (NEW.budget_owner_person_id IS NOT NULL AND NOT EXISTS (
        SELECT 1 FROM persons p WHERE p.id=NEW.budget_owner_person_id AND p.account_id=NEW.account_id))
  OR (NEW.funding_pool_id IS NOT NULL AND NOT EXISTS (
        SELECT 1 FROM funding_pools f WHERE f.id=NEW.funding_pool_id AND f.account_id=NEW.account_id))
BEGIN SELECT RAISE(ABORT, 'opportunity qualification belongs to a different account'); END;

CREATE TRIGGER trg_ask_calendar_opportunity_scope_insert BEFORE INSERT ON ask_calendars
WHEN NEW.opportunity_id IS NOT NULL AND NOT EXISTS (
    SELECT 1 FROM expansion_opportunities o WHERE o.id=NEW.opportunity_id AND o.account_id=NEW.account_id)
BEGIN SELECT RAISE(ABORT, 'ask calendar opportunity belongs to a different account'); END;

CREATE TRIGGER trg_ask_calendar_opportunity_scope_update BEFORE UPDATE OF account_id,opportunity_id ON ask_calendars
WHEN NEW.opportunity_id IS NOT NULL AND NOT EXISTS (
    SELECT 1 FROM expansion_opportunities o WHERE o.id=NEW.opportunity_id AND o.account_id=NEW.account_id)
BEGIN SELECT RAISE(ABORT, 'ask calendar opportunity belongs to a different account'); END;

CREATE TRIGGER trg_agreement_scope_insert BEFORE INSERT ON operational_agreements
WHEN NOT EXISTS (SELECT 1 FROM contract_versions c WHERE c.id=NEW.contract_version_id AND c.account_id=NEW.account_id)
  OR NOT EXISTS (SELECT 1 FROM value_targets v WHERE v.id=NEW.value_target_id AND v.account_id=NEW.account_id)
  OR (NEW.budget_owner_person_id IS NOT NULL AND NOT EXISTS (
        SELECT 1 FROM persons p WHERE p.id=NEW.budget_owner_person_id AND p.account_id=NEW.account_id))
  OR (NEW.source_interaction_id IS NOT NULL AND NOT EXISTS (
        SELECT 1 FROM interactions i WHERE i.id=NEW.source_interaction_id AND i.account_id=NEW.account_id))
BEGIN SELECT RAISE(ABORT, 'operational agreement relation belongs to a different account'); END;

CREATE TRIGGER trg_agreement_event_scope_insert BEFORE INSERT ON operational_agreement_events
WHEN NOT EXISTS (SELECT 1 FROM operational_agreements a
                 WHERE a.id=NEW.agreement_id AND a.account_id=NEW.account_id)
  OR (NEW.opportunity_id IS NOT NULL AND NOT EXISTS (
        SELECT 1 FROM expansion_opportunities o WHERE o.id=NEW.opportunity_id AND o.account_id=NEW.account_id))
BEGIN SELECT RAISE(ABORT, 'operational agreement event belongs to a different account'); END;

CREATE TRIGGER trg_agreement_event_scope_update BEFORE UPDATE OF agreement_id,account_id,opportunity_id
ON operational_agreement_events
WHEN NOT EXISTS (SELECT 1 FROM operational_agreements a
                 WHERE a.id=NEW.agreement_id AND a.account_id=NEW.account_id)
  OR (NEW.opportunity_id IS NOT NULL AND NOT EXISTS (
        SELECT 1 FROM expansion_opportunities o WHERE o.id=NEW.opportunity_id AND o.account_id=NEW.account_id))
BEGIN SELECT RAISE(ABORT, 'operational agreement event belongs to a different account'); END;

CREATE TRIGGER trg_agreement_scope_update BEFORE UPDATE OF account_id,contract_version_id,value_target_id,
budget_owner_person_id,source_interaction_id ON operational_agreements
WHEN NOT EXISTS (SELECT 1 FROM contract_versions c WHERE c.id=NEW.contract_version_id AND c.account_id=NEW.account_id)
  OR NOT EXISTS (SELECT 1 FROM value_targets v WHERE v.id=NEW.value_target_id AND v.account_id=NEW.account_id)
  OR (NEW.budget_owner_person_id IS NOT NULL AND NOT EXISTS (
        SELECT 1 FROM persons p WHERE p.id=NEW.budget_owner_person_id AND p.account_id=NEW.account_id))
  OR (NEW.source_interaction_id IS NOT NULL AND NOT EXISTS (
        SELECT 1 FROM interactions i WHERE i.id=NEW.source_interaction_id AND i.account_id=NEW.account_id))
BEGIN SELECT RAISE(ABORT, 'operational agreement relation belongs to a different account'); END;

CREATE TRIGGER trg_growth_line_scope_insert BEFORE INSERT ON growth_plan_lines
WHEN NOT EXISTS (SELECT 1 FROM account_growth_plans g WHERE g.id=NEW.plan_id AND g.account_id=NEW.account_id)
  OR (NEW.segment_id IS NOT NULL AND NOT EXISTS (
        SELECT 1 FROM population_segments s WHERE s.id=NEW.segment_id AND s.account_id=NEW.account_id))
  OR (NEW.view_id IS NOT NULL AND NOT EXISTS (
        SELECT 1 FROM population_views v WHERE v.id=NEW.view_id AND v.account_id=NEW.account_id))
  OR (NEW.opportunity_id IS NOT NULL AND NOT EXISTS (
        SELECT 1 FROM expansion_opportunities o WHERE o.id=NEW.opportunity_id AND o.account_id=NEW.account_id))
  OR (NEW.funding_pool_id IS NOT NULL AND NOT EXISTS (
        SELECT 1 FROM funding_pools f WHERE f.id=NEW.funding_pool_id AND f.account_id=NEW.account_id))
  OR (NEW.ask_calendar_id IS NOT NULL AND NOT EXISTS (
        SELECT 1 FROM ask_calendars a WHERE a.id=NEW.ask_calendar_id AND a.account_id=NEW.account_id))
  OR (NEW.budget_owner_person_id IS NOT NULL AND NOT EXISTS (
        SELECT 1 FROM persons p WHERE p.id=NEW.budget_owner_person_id AND p.account_id=NEW.account_id))
BEGIN SELECT RAISE(ABORT, 'growth plan line relation belongs to a different account'); END;

CREATE TRIGGER trg_growth_line_scope_update BEFORE UPDATE OF plan_id,account_id,segment_id,view_id,
opportunity_id,budget_owner_person_id,funding_pool_id,ask_calendar_id ON growth_plan_lines
WHEN NOT EXISTS (SELECT 1 FROM account_growth_plans g WHERE g.id=NEW.plan_id AND g.account_id=NEW.account_id)
  OR (NEW.segment_id IS NOT NULL AND NOT EXISTS (
        SELECT 1 FROM population_segments s WHERE s.id=NEW.segment_id AND s.account_id=NEW.account_id))
  OR (NEW.view_id IS NOT NULL AND NOT EXISTS (
        SELECT 1 FROM population_views v WHERE v.id=NEW.view_id AND v.account_id=NEW.account_id))
  OR (NEW.opportunity_id IS NOT NULL AND NOT EXISTS (
        SELECT 1 FROM expansion_opportunities o WHERE o.id=NEW.opportunity_id AND o.account_id=NEW.account_id))
  OR (NEW.funding_pool_id IS NOT NULL AND NOT EXISTS (
        SELECT 1 FROM funding_pools f WHERE f.id=NEW.funding_pool_id AND f.account_id=NEW.account_id))
  OR (NEW.ask_calendar_id IS NOT NULL AND NOT EXISTS (
        SELECT 1 FROM ask_calendars a WHERE a.id=NEW.ask_calendar_id AND a.account_id=NEW.account_id))
  OR (NEW.budget_owner_person_id IS NOT NULL AND NOT EXISTS (
        SELECT 1 FROM persons p WHERE p.id=NEW.budget_owner_person_id AND p.account_id=NEW.account_id))
BEGIN SELECT RAISE(ABORT, 'growth plan line relation belongs to a different account'); END;
