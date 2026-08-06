-- Migration 0019 — Stage 5.5: funding intelligence (EXPANSION-ENGINE-SPEC.md §4, §10)
--
-- "Deals are won in the value case and lost in the funding mechanics." Three things here:
--
--   1. FUNDING POOLS replace the free-text expansion_opportunities.funding_source. Two places
--      to record who pays is one place too many, and a string cannot link to the stakeholder
--      who controls the money. Existing values are backfilled into real pools per account so
--      nothing is lost; the old column stays as a read-only legacy record of what was typed.
--
--   2. FISCAL MAPS reference canonical contract data rather than restating it. Procurement
--      lead time already lives on contract_versions as synced CRM data (source-authority rule):
--      the fiscal map points at the contract, it does not keep a second copy that can drift.
--
--   3. CONTRACT REVENUE SEMANTICS. `price` was a bare REAL with no currency, no period, and no
--      recurring/one-off distinction. That is under-modeled for the renewal case, the funding
--      waterfall, the pre-priced seat bands, and the growth plan's weighted views — all of
--      which currently rest on a number whose units are undefined. NRR falls out of this; it
--      is not the reason for it. Overlay-only: the canonical copy stays read-only, and the new
--      columns describe what the canonical number MEANS rather than replacing it.
--
-- The ask calendar's steps are TYPED LINKS to tasks, milestones, and compliance items, not a
-- fourth parallel to-do system — an ask step is a real piece of work or it is decoration.

PRAGMA foreign_keys = ON;

-- --- contract revenue semantics (§10) ------------------------------------------------------
ALTER TABLE contract_versions ADD COLUMN currency TEXT;                 -- ISO 4217, e.g. "EUR"
ALTER TABLE contract_versions ADD COLUMN price_basis TEXT
    CHECK (price_basis IS NULL OR price_basis IN ('arr','tcv','one_time','monthly'));
ALTER TABLE contract_versions ADD COLUMN term_months INTEGER;
-- Derived ARR is stored explicitly rather than inferred at every call site, because inferring
-- it differently in two places is how a revenue number quietly disagrees with itself.
ALTER TABLE contract_versions ADD COLUMN derived_arr REAL;

-- Contraction and churn are DATED EVENTS, not states inferred from a missing row. An account
-- that shrank in March and an account whose record was never updated are different facts.
CREATE TABLE revenue_events (
    id            TEXT PRIMARY KEY,
    account_id    TEXT NOT NULL REFERENCES accounts(id),
    contract_version_id TEXT REFERENCES contract_versions(id),
    kind          TEXT NOT NULL CHECK (kind IN
                    ('expansion','contraction','churn','renewal_flat','price_change')),
    amount        REAL,                 -- signed, in `currency`; the direction is in `kind`
    currency      TEXT,
    seats_delta   INTEGER,
    effective_on  TEXT NOT NULL,
    reason        TEXT,
    source_reference_id TEXT REFERENCES source_references(id),
    created_at    TEXT NOT NULL,
    updated_at    TEXT NOT NULL,
    archived      INTEGER NOT NULL DEFAULT 0,
    archived_at   TEXT,
    archived_by   TEXT
);
CREATE INDEX idx_revenue_event_account ON revenue_events(account_id, effective_on);

-- --- funding pools (§4) ---------------------------------------------------------------------
CREATE TABLE funding_pools (
    id            TEXT PRIMARY KEY,
    account_id    TEXT NOT NULL REFERENCES accounts(id),
    name          TEXT NOT NULL,
    kind          TEXT NOT NULL DEFAULT 'other' CHECK (kind IN (
                    'recovered_vendor_spend',   -- incumbent displacement; links to recovered_spend
                    'central_ld_budget', 'chro_discretionary', 'bu_cross_charge',
                    'transformation_program', 'other')),
    owner_person_id TEXT REFERENCES persons(id),   -- who controls the money
    status        TEXT NOT NULL DEFAULT 'potential' CHECK (status IN
                    ('potential','confirmed','committed','exhausted','unavailable')),
    amount        REAL,
    currency      TEXT,
    available_from TEXT,
    available_until TEXT,
    -- recovered_vendor_spend pools point at the existing record rather than duplicating it.
    recovered_spend_id TEXT REFERENCES recovered_spend(id),
    notes         TEXT,
    created_at    TEXT NOT NULL,
    updated_at    TEXT NOT NULL,
    archived      INTEGER NOT NULL DEFAULT 0,
    archived_at   TEXT,
    archived_by   TEXT
);
CREATE INDEX idx_funding_pool_account ON funding_pools(account_id, status);

-- Supersedes the free-text funding_source (kept, unused, as a record of what was typed).
ALTER TABLE expansion_opportunities ADD COLUMN funding_pool_id TEXT REFERENCES funding_pools(id);

-- --- the fiscal map (§4) --------------------------------------------------------------------
-- Entered once, confirmed annually. `confirmed_on` exists so a stale fiscal map renders with
-- the freshness language like every other dated claim, instead of silently guiding an ask.
CREATE TABLE fiscal_maps (
    account_id             TEXT PRIMARY KEY REFERENCES accounts(id),
    fiscal_year_end        TEXT,          -- MM-DD
    planning_window_start  TEXT,          -- MM-DD
    planning_window_end    TEXT,          -- MM-DD
    budget_request_deadline TEXT,         -- MM-DD
    -- Procurement lead time is canonical on contract_versions; point at it, never copy it.
    procurement_lead_contract_id TEXT REFERENCES contract_versions(id),
    works_council_lead_days INTEGER,
    notes                  TEXT,
    confirmed_on           TEXT,
    confirmed_by           TEXT,
    created_at             TEXT NOT NULL,
    updated_at             TEXT NOT NULL
);

-- --- the ask calendar (§4) ------------------------------------------------------------------
-- Back-scheduled from a target close date. Steps are typed links to real work objects.
CREATE TABLE ask_calendars (
    id             TEXT PRIMARY KEY,
    account_id     TEXT NOT NULL REFERENCES accounts(id),
    opportunity_id TEXT REFERENCES expansion_opportunities(id),
    name           TEXT NOT NULL,
    target_close_date TEXT NOT NULL,
    status         TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active','closed','abandoned')),
    created_at     TEXT NOT NULL,
    updated_at     TEXT NOT NULL,
    archived       INTEGER NOT NULL DEFAULT 0,
    archived_at    TEXT,
    archived_by    TEXT
);
CREATE INDEX idx_ask_calendar_account ON ask_calendars(account_id, status);

CREATE TABLE ask_calendar_steps (
    id           TEXT PRIMARY KEY,
    calendar_id  TEXT NOT NULL REFERENCES ask_calendars(id),
    kind         TEXT NOT NULL CHECK (kind IN (
                   'business_case_delivered','budget_owner_sponsorship','budget_window',
                   'procurement','works_council','signature','other')),
    label        TEXT NOT NULL,
    due_date     TEXT NOT NULL,
    owner_person_id TEXT REFERENCES persons(id),
    -- A step is a real work object or it is decoration. Optional, because back-scheduling
    -- produces the dates first and the operator attaches the work as it is created.
    linked_type  TEXT CHECK (linked_type IS NULL OR linked_type IN ('task','milestone','compliance_item')),
    linked_id    TEXT,
    status       TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','done','late','skipped')),
    completed_on TEXT,
    display_order INTEGER NOT NULL DEFAULT 0,
    created_at   TEXT NOT NULL,
    updated_at   TEXT NOT NULL,
    CHECK (linked_type IS NULL OR linked_id IS NOT NULL)
);
CREATE INDEX idx_ask_step_calendar ON ask_calendar_steps(calendar_id, due_date);
