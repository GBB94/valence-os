-- Migration 0017 — Stage 5.5: the whitespace map (EXPANSION-ENGINE-SPEC.md §1)
--
-- The counting rule (§1.1) is enforced in the schema, not by convention, because a
-- whitespace map that can double-count is worse than no map:
--   * A seat is one person-license, owned by the ROW axis.
--   * population_segments are the ONE additive dimension: mutually exclusive, collectively
--     exhaustive over the account's total FTE, with an explicit unallocated remainder.
--     Only segments carry authoritative headcount and only segment headcounts sum.
--   * population_views ("DACH frontline managers") are composites over segments + audience
--     tags. They OVERLAP by construction, so they are never additive; the column exists to
--     say so and the service refuses to sum them.
--   * use_cases are entitlements ON a seat, not separate seat inventories. Cell seat
--     estimates are therefore non-additive ACROSS a row (the same manager appears in
--     performance reviews and change management), and additive DOWN a column over segments.
--
-- audience_tags and use_cases are PORTFOLIO-GLOBAL (§1.2, §11): cross-account "how was this
-- shape won elsewhere" is impossible if every account names its audiences differently.
-- Account-specific use cases are permitted but flagged non-comparable rather than hidden.
--
-- Cell state (§1.3) stores FOUR INDEPENDENT FACTS; the single heatmap state is DERIVED in
-- app/expansion.py under documented precedence and is never written. v1's six states could
-- not express "paid but unevidenced" — the exact churn-risk state the value ledger exists to
-- catch — because they conflated penetration, evidence, gating, and pursuit outcome.
--
-- Trust boundaries unchanged: cohorts and cells, never individuals; no field anywhere for a
-- named person's product usage. §1.2's minimum-cohort-size floor is added here as a setting
-- because "aggregate" stops being non-identifying once a composite narrows far enough.

PRAGMA foreign_keys = ON;

-- --- per-account settings ----------------------------------------------------------------
-- The cohort privacy floor is a setting, not a constant: it is a judgment about identifiability
-- that differs by account size and jurisdiction, and hard-coding it would make it invisible.
CREATE TABLE account_settings (
    account_id      TEXT PRIMARY KEY REFERENCES accounts(id),
    min_cohort_size INTEGER NOT NULL DEFAULT 25,   -- below this, cohort-derived values render suppressed
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL
);

-- --- portfolio-global vocabularies (§1.2, §11) --------------------------------------------
-- Audience tags reference the People-module taxonomy in spirit (0013 layers/roles) rather than
-- inventing a parallel vocabulary: these are deployment audiences, not buying-committee roles.
CREATE TABLE audience_tags (
    id          TEXT PRIMARY KEY,
    name        TEXT NOT NULL,
    slug        TEXT NOT NULL UNIQUE,        -- stable key for cross-account shape matching
    description TEXT,
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL,
    archived    INTEGER NOT NULL DEFAULT 0,
    archived_at TEXT,
    archived_by TEXT
);

CREATE TABLE use_cases (
    id          TEXT PRIMARY KEY,
    name        TEXT NOT NULL,
    slug        TEXT NOT NULL,
    description TEXT,
    -- NULL = portfolio-global and comparable across accounts (§11 shape matching).
    -- Non-NULL = account-specific; still usable, but excluded from cross-account results
    -- and labeled as excluded rather than silently dropped.
    account_id  TEXT REFERENCES accounts(id),
    display_order INTEGER NOT NULL DEFAULT 0,
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL,
    archived    INTEGER NOT NULL DEFAULT 0,
    archived_at TEXT,
    archived_by TEXT
);
CREATE UNIQUE INDEX idx_use_case_slug_global ON use_cases(slug) WHERE account_id IS NULL;
CREATE UNIQUE INDEX idx_use_case_slug_account ON use_cases(account_id, slug) WHERE account_id IS NOT NULL;

-- --- the base partition (§1.1) — the only additive dimension ------------------------------
-- Versioned: re-basing the partition re-bases every historical number, so it is an event with
-- a reason, not an edit. Exactly one active partition per account.
CREATE TABLE population_partitions (
    id          TEXT PRIMARY KEY,
    account_id  TEXT NOT NULL REFERENCES accounts(id),
    version     INTEGER NOT NULL DEFAULT 1,
    basis       TEXT,                         -- how it was cut, e.g. "business unit x region"
    total_fte   INTEGER,                      -- the account's own headcount; segments sum to this
    fte_source  TEXT,                         -- a claim, so it carries provenance
    fte_as_of   TEXT,
    status      TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active','superseded')),
    supersedes_id TEXT REFERENCES population_partitions(id),
    reason      TEXT,                         -- why it was re-cut (required by the API on supersede)
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);
CREATE UNIQUE INDEX idx_partition_active ON population_partitions(account_id) WHERE status = 'active';

CREATE TABLE population_segments (
    id             TEXT PRIMARY KEY,
    partition_id   TEXT NOT NULL REFERENCES population_partitions(id),
    account_id     TEXT NOT NULL REFERENCES accounts(id),
    name           TEXT NOT NULL,
    business_unit  TEXT,
    region         TEXT,
    -- Headcount is a CLAIM (§1.2): it never renders without its source and date.
    headcount      INTEGER,
    headcount_source TEXT,
    headcount_as_of  TEXT,
    source_reference_id TEXT REFERENCES source_references(id),
    -- The visible remainder that keeps the partition honest. Exactly one per partition; it is
    -- what stops the map quietly claiming 30,000 addressable seats in a 20,000-person company.
    is_unallocated INTEGER NOT NULL DEFAULT 0,
    display_order  INTEGER NOT NULL DEFAULT 0,
    created_at     TEXT NOT NULL,
    updated_at     TEXT NOT NULL,
    archived       INTEGER NOT NULL DEFAULT 0,
    archived_at    TEXT,
    archived_by    TEXT
);
CREATE INDEX idx_segment_partition ON population_segments(partition_id, display_order);
CREATE UNIQUE INDEX idx_segment_unallocated ON population_segments(partition_id)
    WHERE is_unallocated = 1 AND archived = 0;

-- Headcount over time (§3.2). Ships now, with the adapter, so the series starts accruing —
-- the land-and-leave detector needs two comparable periods and no scope decision creates
-- elapsed time. `source_kind` records provenance because manual entry and an HRIS feed are
-- different claims about the same number.
CREATE TABLE population_headcount_observations (
    id           TEXT PRIMARY KEY,
    segment_id   TEXT NOT NULL REFERENCES population_segments(id),
    account_id   TEXT NOT NULL REFERENCES accounts(id),
    period_label TEXT NOT NULL,                -- e.g. "2026-Q2"
    headcount    INTEGER NOT NULL,
    source_kind  TEXT NOT NULL DEFAULT 'manual_entry'
                 CHECK (source_kind IN ('manual_entry','hris_adapter','client_stated','estimate')),
    source_note  TEXT,
    observed_on  TEXT NOT NULL,
    source_reference_id TEXT REFERENCES source_references(id),
    created_at   TEXT NOT NULL,
    updated_at   TEXT NOT NULL,
    archived     INTEGER NOT NULL DEFAULT 0,
    archived_at  TEXT,
    archived_by  TEXT
);
CREATE UNIQUE INDEX idx_headcount_period ON population_headcount_observations(segment_id, period_label)
    WHERE archived = 0;

-- --- composite views (§1.1) — never additive ----------------------------------------------
CREATE TABLE population_views (
    id             TEXT PRIMARY KEY,
    account_id     TEXT NOT NULL REFERENCES accounts(id),
    name           TEXT NOT NULL,              -- "DACH frontline managers"
    -- Estimated, not derived: audience tags cut across segments, so this cannot be computed
    -- from segment headcounts. It is a claim and carries provenance like every other claim.
    estimated_headcount INTEGER,
    headcount_source    TEXT,
    headcount_as_of     TEXT,
    created_at     TEXT NOT NULL,
    updated_at     TEXT NOT NULL,
    archived       INTEGER NOT NULL DEFAULT 0,
    archived_at    TEXT,
    archived_by    TEXT
);
CREATE INDEX idx_view_account ON population_views(account_id);

CREATE TABLE population_view_segments (
    view_id    TEXT NOT NULL REFERENCES population_views(id),
    segment_id TEXT NOT NULL REFERENCES population_segments(id),
    PRIMARY KEY (view_id, segment_id)
);

CREATE TABLE population_view_tags (
    view_id TEXT NOT NULL REFERENCES population_views(id),
    tag_id  TEXT NOT NULL REFERENCES audience_tags(id),
    PRIMARY KEY (view_id, tag_id)
);

-- --- whitespace cells (§1.3) ---------------------------------------------------------------
-- A cell's row is EITHER a base segment (additive) or a composite view (non-additive), never
-- both and never neither — enforced below, because the rollup rules depend on knowing which.
CREATE TABLE whitespace_cells (
    id             TEXT PRIMARY KEY,
    account_id     TEXT NOT NULL REFERENCES accounts(id),
    segment_id     TEXT REFERENCES population_segments(id),
    view_id        TEXT REFERENCES population_views(id),
    use_case_id    TEXT NOT NULL REFERENCES use_cases(id),

    -- The four independent facts. The heatmap state is DERIVED from these (never stored):
    -- see app/expansion.py:derive_state for the precedence.
    penetration    TEXT NOT NULL DEFAULT 'none'  CHECK (penetration    IN ('none','pilot','paid')),
    evidence_state TEXT NOT NULL DEFAULT 'none'  CHECK (evidence_state IN ('none','anecdotal','measured')),
    blocker_state  TEXT NOT NULL DEFAULT 'clear' CHECK (blocker_state  IN ('clear','gated')),
    pursuit_outcome TEXT NOT NULL DEFAULT 'none'
                   CHECK (pursuit_outcome IN ('none','declined','won','deferred')),

    -- Gating detail. The lane matters because a gated cell is worked in the compliance lane,
    -- not the sales lane — that is why Blocked takes precedence in the derived state.
    blocker_lane   TEXT CHECK (blocker_lane IS NULL OR blocker_lane IN
                     ('works_council','it','legal','localization','other')),
    blocker_owner_person_id TEXT REFERENCES persons(id),
    blocker_note   TEXT,

    -- Pursuit detail. A decline is only meaningful with a reason and a date; reopening is an
    -- explicit event (reopened_on + reason) so "the reason changed" is a transition, not an edit.
    declined_reason TEXT,
    declined_on     TEXT,
    reopened_on     TEXT,
    reopened_reason TEXT,
    deferred_until  TEXT,

    estimated_seats INTEGER,        -- non-additive across a row (§1.1); the service labels it
    paid_seats      INTEGER NOT NULL DEFAULT 0,
    sponsor_person_id TEXT REFERENCES persons(id),
    next_action     TEXT,
    notes           TEXT,

    created_at     TEXT NOT NULL,
    updated_at     TEXT NOT NULL,
    archived       INTEGER NOT NULL DEFAULT 0,
    archived_at    TEXT,
    archived_by    TEXT,

    CHECK ((segment_id IS NOT NULL AND view_id IS NULL)
        OR (segment_id IS NULL AND view_id IS NOT NULL)),
    -- A gate without a lane is an assertion no one can act on.
    CHECK (blocker_state = 'clear' OR blocker_lane IS NOT NULL),
    -- A decline without a reason and a date is not a decision, it is a mood.
    CHECK (pursuit_outcome <> 'declined' OR (declined_reason IS NOT NULL AND declined_on IS NOT NULL))
);
CREATE INDEX idx_cell_account ON whitespace_cells(account_id, use_case_id);
CREATE UNIQUE INDEX idx_cell_segment_usecase ON whitespace_cells(segment_id, use_case_id)
    WHERE segment_id IS NOT NULL AND archived = 0;
CREATE UNIQUE INDEX idx_cell_view_usecase ON whitespace_cells(view_id, use_case_id)
    WHERE view_id IS NOT NULL AND archived = 0;

-- Every fact change is appended with a reason. The composite state is never written, so this
-- is the audit trail of the four facts rather than of a status string.
CREATE TABLE cell_state_history (
    id          TEXT PRIMARY KEY,
    cell_id     TEXT NOT NULL REFERENCES whitespace_cells(id),
    fact        TEXT NOT NULL CHECK (fact IN
                  ('penetration','evidence_state','blocker_state','pursuit_outcome','reopened')),
    before_value TEXT,
    after_value  TEXT,
    reason      TEXT NOT NULL,
    changed_on  TEXT NOT NULL,
    actor       TEXT,
    created_at  TEXT NOT NULL
);
CREATE INDEX idx_cell_history ON cell_state_history(cell_id, changed_on);

-- Cells link to the evidence that justifies their evidence_state. Free-text supporting_evidence
-- on opportunities was one of the seams the review flagged; cells get typed links from the start.
CREATE TABLE cell_evidence_links (
    id          TEXT PRIMARY KEY,
    cell_id     TEXT NOT NULL REFERENCES whitespace_cells(id),
    object_type TEXT NOT NULL CHECK (object_type IN ('value_story','metric_observation')),
    object_id   TEXT NOT NULL,
    note        TEXT,
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);
CREATE UNIQUE INDEX idx_cell_evidence ON cell_evidence_links(cell_id, object_type, object_id);
