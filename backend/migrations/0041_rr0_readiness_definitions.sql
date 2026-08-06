-- Migration 0041 — RR-0: versioned relationship-readiness pillar and requirement definitions.
--
-- RELATIONSHIP-READINESS-SPEC.md §2.4. Two governed-definition tables and nothing else:
--
--   * There is deliberately NO readiness state table. Readiness is a query-time projection over
--     accepted canonical records (§2.4, §5.1). A stored state table would immediately become a
--     second source of truth that drifts from the evidence it claims to summarize.
--   * There is deliberately NO score, weight, rank, or composite column anywhere in this file.
--     §0.3 forbids a composite health score, and §11.1 asserts its absence by introspection —
--     which only works if the schema never offers a column to put one in.
--   * Definition rows CONFIGURE an allowlisted evaluator; they never create executable behavior
--     (§2.3). An unknown evaluator key or unsupported version fails closed in code. The trigger
--     below only enforces the shape of the configuration, not the existence of the evaluator.
--
-- Mock-only data; the seeded thresholds are versioned defaults, not benchmarks (§1.3).
PRAGMA foreign_keys = ON;

-- --- pillars -----------------------------------------------------------------------------------
-- A pillar is a stable readiness category. Its state is aggregated from its requirement results
-- by the versioned evaluator; it is never manually editable.
CREATE TABLE readiness_pillar_definitions (
    id                       TEXT PRIMARY KEY,
    key                      TEXT NOT NULL,
    version                  INTEGER NOT NULL CHECK (version >= 1),
    label                    TEXT NOT NULL,
    purpose                  TEXT NOT NULL,

    -- §1.2 governance metadata, NOT a UI tier and NOT a weight. Nothing may multiply by this.
    research_class           TEXT NOT NULL
                               CHECK (research_class IN ('core_hypothesis','supporting_hypothesis')),

    default_scope            TEXT NOT NULL
                               CHECK (default_scope IN ('account','program','account_rollup')),

    evaluator_key            TEXT NOT NULL,
    evaluator_version        INTEGER NOT NULL CHECK (evaluator_version >= 1),

    -- {"foundation":"optional","launch":"required",...} over programs.phase (§3.2).
    phase_applicability_json TEXT NOT NULL DEFAULT '{}',
    display_order            INTEGER NOT NULL DEFAULT 0,

    -- §1.3: a superseded version stays readable so historical results remain interpretable.
    active_from              TEXT NOT NULL,
    retired_at               TEXT,
    governance_note          TEXT NOT NULL,

    created_at               TEXT NOT NULL,
    updated_at               TEXT NOT NULL,
    archived                 INTEGER NOT NULL DEFAULT 0,
    archived_at              TEXT,
    archived_by              TEXT,

    UNIQUE (key, version),
    CHECK (retired_at IS NULL OR retired_at >= active_from),
    CHECK (json_valid(phase_applicability_json))
);

-- At most one live version per pillar key. Retiring the old row is what makes room for the new
-- one, so a definition upgrade is an explicit, previewable act (§7.4) rather than a silent race.
CREATE UNIQUE INDEX idx_readiness_pillar_live
    ON readiness_pillar_definitions(key) WHERE retired_at IS NULL AND archived = 0;

-- --- requirements ------------------------------------------------------------------------------
-- A requirement definition is the evaluatable condition under a pillar. Account Path playbooks
-- reference these exact (key, version) pairs; there is one canonical definition per condition
-- (§0.4) so no second status for the same condition can exist.
CREATE TABLE readiness_requirement_definitions (
    id                        TEXT PRIMARY KEY,
    key                       TEXT NOT NULL,
    version                   INTEGER NOT NULL CHECK (version >= 1),

    pillar_key                TEXT NOT NULL,
    pillar_version            INTEGER NOT NULL,

    label                     TEXT NOT NULL,
    purpose                   TEXT NOT NULL,
    definition_of_done        TEXT NOT NULL,

    default_scope             TEXT NOT NULL
                                CHECK (default_scope IN ('account','program','account_rollup')),

    evaluator_key             TEXT NOT NULL,
    evaluator_version         INTEGER NOT NULL CHECK (evaluator_version >= 1),
    -- Validated configuration for the evaluator: thresholds, windows, allowed stages. Thresholds
    -- live here rather than in code so §1.3 threshold governance is a definition version bump.
    evaluator_config_json     TEXT NOT NULL DEFAULT '{}',

    allowed_evidence_types_json TEXT NOT NULL DEFAULT '[]',
    -- Per-component freshness. §3.4: freshness is evaluated per component, so one fresh component
    -- can never make a stale required component look current.
    freshness_policy_json     TEXT NOT NULL DEFAULT '{}',
    phase_applicability_json  TEXT NOT NULL DEFAULT '{}',
    -- A template only. It becomes work when an operator creates a native Task/Commitment (§5.2).
    suggested_action_json     TEXT,

    active_from               TEXT NOT NULL,
    retired_at                TEXT,
    governance_note           TEXT NOT NULL,

    created_at                TEXT NOT NULL,
    updated_at                TEXT NOT NULL,
    archived                  INTEGER NOT NULL DEFAULT 0,
    archived_at               TEXT,
    archived_by               TEXT,

    UNIQUE (key, version),
    FOREIGN KEY (pillar_key, pillar_version)
        REFERENCES readiness_pillar_definitions(key, version),
    CHECK (retired_at IS NULL OR retired_at >= active_from),
    CHECK (json_valid(evaluator_config_json)),
    CHECK (json_valid(allowed_evidence_types_json)),
    CHECK (json_valid(freshness_policy_json)),
    CHECK (json_valid(phase_applicability_json)),
    CHECK (suggested_action_json IS NULL OR json_valid(suggested_action_json))
);

CREATE UNIQUE INDEX idx_readiness_requirement_live
    ON readiness_requirement_definitions(key) WHERE retired_at IS NULL AND archived = 0;
CREATE INDEX idx_readiness_requirement_pillar
    ON readiness_requirement_definitions(pillar_key, pillar_version);

-- A live requirement may not hang off a retired pillar version: that would leave a condition
-- evaluatable under a definition the operator has already replaced.
CREATE TRIGGER trg_readiness_requirement_live_pillar_insert
BEFORE INSERT ON readiness_requirement_definitions
WHEN NEW.retired_at IS NULL AND EXISTS (
    SELECT 1 FROM readiness_pillar_definitions p
     WHERE p.key = NEW.pillar_key AND p.version = NEW.pillar_version
       AND (p.retired_at IS NOT NULL OR p.archived = 1))
BEGIN
    SELECT RAISE(ABORT, 'live requirement definition cannot reference a retired pillar version');
END;

CREATE TRIGGER trg_readiness_requirement_live_pillar_update
BEFORE UPDATE ON readiness_requirement_definitions
WHEN NEW.retired_at IS NULL AND EXISTS (
    SELECT 1 FROM readiness_pillar_definitions p
     WHERE p.key = NEW.pillar_key AND p.version = NEW.pillar_version
       AND (p.retired_at IS NOT NULL OR p.archived = 1))
BEGIN
    SELECT RAISE(ABORT, 'live requirement definition cannot reference a retired pillar version');
END;

-- --- seed: the six pillars (§4) ----------------------------------------------------------------
-- research_class records how well-evidenced the hypothesis is; it is governance metadata only and
-- the UI does not render it as a tier (§1.2).
INSERT INTO readiness_pillar_definitions
 (id,key,version,label,purpose,research_class,default_scope,evaluator_key,evaluator_version,
  phase_applicability_json,display_order,active_from,governance_note,created_at,updated_at)
VALUES
 ('rpd-breadth-1','stakeholder_breadth',1,'Stakeholder breadth',
  'Whether the relationship reaches enough people across enough stakeholder layers to survive one departure.',
  'core_hypothesis','program','stakeholder_breadth',1,
  '{"foundation":"optional","launch":"required","programmatic":"required","expansion":"required","renewal":"required","closed":"not_applicable"}',
  10,'2026-08-04','Seeded RR-0. Adjacent buying-group evidence; thresholds are versioned defaults, not benchmarks.',
  datetime('now'),datetime('now')),

 ('rpd-champion-1','champion_continuity',1,'Champion continuity',
  'Whether advocacy survives the loss of any single relationship.',
  'core_hypothesis','program','champion_continuity',1,
  '{"foundation":"optional","launch":"required","programmatic":"required","expansion":"required","renewal":"required","closed":"not_applicable"}',
  20,'2026-08-04','Seeded RR-0. Champion-departure practice is directional, not a validated Valence predictor.',
  datetime('now'),datetime('now')),

 ('rpd-exec-1','executive_sponsorship',1,'Executive sponsorship',
  'Whether an executive is engaged and the value is tied to an outcome they own.',
  'core_hypothesis','program','executive_sponsorship',1,
  '{"foundation":"optional","launch":"required","programmatic":"required","expansion":"required","renewal":"required","closed":"not_applicable"}',
  30,'2026-08-04','Seeded RR-0. Caps at thin until an explicit stakeholder-to-metric relation exists (RR-3).',
  datetime('now'),datetime('now')),

 ('rpd-value-1','quantified_value',1,'Quantified value',
  'Whether a business outcome has been measured against a locked baseline rather than asserted.',
  'core_hypothesis','program','quantified_value',1,
  '{"foundation":"not_due","launch":"optional","programmatic":"required","expansion":"required","renewal":"required","closed":"not_applicable"}',
  40,'2026-08-04','Seeded RR-0. Caps at thin without an explicitly locked baseline observation.',
  datetime('now'),datetime('now')),

 ('rpd-budget-1','budget_owner',1,'Budget owner identified',
  'Whether a named person with evidenced budget authority is tied to a commercial record.',
  'supporting_hypothesis','account','budget_owner',1,
  '{"foundation":"optional","launch":"optional","programmatic":"required","expansion":"required","renewal":"required","closed":"not_applicable"}',
  50,'2026-08-04','Seeded RR-0. Practitioner-supported rather than independently validated.',
  datetime('now'),datetime('now')),

 -- Scope is account, not program: expansion_opportunities carries account_id and no program_id,
 -- so pretending this is program-scoped evidence would invent a link the data cannot support.
 -- Applicability is still driven by the in-scope program's phase (§3.2), which is why this pillar
 -- reads not_due in foundation/launch.
 ('rpd-expansion-1','active_expansion_plan',1,'Active expansion plan',
  'Whether an expansion is co-owned with the client rather than an internal hypothesis.',
  'supporting_hypothesis','account','active_expansion_plan',1,
  '{"foundation":"not_due","launch":"not_due","programmatic":"optional","expansion":"required","renewal":"required","closed":"not_applicable"}',
  60,'2026-08-04','Seeded RR-0. Mutual-plan practice is vendor-authored; treated as a supporting hypothesis.',
  datetime('now'),datetime('now'));

-- --- seed: requirement definitions (§4.1-4.6) --------------------------------------------------
-- Every threshold below is an evaluator_config value, never a literal in code (§1.3).
INSERT INTO readiness_requirement_definitions
 (id,key,version,pillar_key,pillar_version,label,purpose,definition_of_done,default_scope,
  evaluator_key,evaluator_version,evaluator_config_json,allowed_evidence_types_json,
  freshness_policy_json,phase_applicability_json,suggested_action_json,
  active_from,governance_note,created_at,updated_at)
VALUES
 -- 4.1 Stakeholder breadth
 ('rrd-breadth-contacts-1','breadth_engaged_contacts',1,'stakeholder_breadth',1,
  'Engaged client contacts',
  'At least a minimum number of distinct, non-placeholder client people have a recent meaningful touch.',
  'Three distinct non-placeholder client people each have a meaningful accepted interaction inside the touch window.',
  'program','breadth_engaged_contacts',1,
  '{"min_contacts":3,"touch_window_days":45}',
  '["interaction","stakeholder_role"]',
  '{"breadth_engaged_contacts":{"window_days":45}}',
  '{}',
  '{"native_type":"task","title":"Broaden the relationship beyond the current contacts"}',
  '2026-08-04','Seeded RR-0. min_contacts/touch_window are versioned defaults.',
  datetime('now'),datetime('now')),

 ('rrd-breadth-layers-1','breadth_layer_spread',1,'stakeholder_breadth',1,
  'Spread across stakeholder layers',
  'Engaged contacts span more than one stakeholder layer, so breadth is not one department restated.',
  'Engaged contacts hold explicitly assessed layers covering at least two distinct layers.',
  'program','breadth_layer_spread',1,
  -- require_explicit_layer: a layer derived from the role default is NOT layer evidence. Without
  -- this, three people whose layer was never assessed satisfy the spread from defaults alone
  -- (champion->operational, budget_owner->economic, executive_sponsor->executive).
  '{"min_layers":2,"require_explicit_layer":true}',
  '["stakeholder_role"]',
  '{"breadth_layer_spread":{"window_days":null}}',
  '{}',
  '{"native_type":"task","title":"Assess stakeholder layers for the engaged contacts"}',
  '2026-08-04','Seeded RR-0. Layer proxy stands in for client business function until a sourced function field exists (§4.1).',
  datetime('now'),datetime('now')),

 -- 4.2 Champion continuity
 ('rrd-champion-primary-1','champion_primary_validated',1,'champion_continuity',1,
  'Validated primary champion',
  'A champion validated by advocacy evidence in this program, not a role label.',
  'A non-placeholder person holds a champion role in this program with program-scoped advocacy evidence and a current meaningful touch.',
  'program','champion_primary_validated',1,
  '{"touch_window_days":45,"advocacy_window_days":180}',
  '["advocacy_event","stakeholder_role","interaction"]',
  '{"champion_primary_validated":{"window_days":45}}',
  '{}',
  '{"native_type":"task","title":"Record advocacy evidence for the tagged champion"}',
  '2026-08-04','Seeded RR-0. Advocacy is resolved program-scoped; account-level advocacy does not validate a program champion.',
  datetime('now'),datetime('now')),

 ('rrd-champion-second-1','champion_second_thread',1,'champion_continuity',1,
  'Viable second thread',
  'A distinct second relationship that would survive the primary champion leaving.',
  'A second non-placeholder person in this program is a validated champion, executive sponsor, budget owner, or program owner with a current meaningful touch, or a champion candidate at an allowed evidence stage.',
  'program','champion_second_thread',1,
  '{"touch_window_days":45,"allowed_candidate_stages":["validate","arm","maintain"],"allowed_roles":["champion","executive_sponsor","budget_owner","program_owner"]}',
  '["stakeholder_role","champion_candidate","interaction","advocacy_event"]',
  '{"champion_second_thread":{"window_days":45}}',
  '{}',
  '{"native_type":"task","title":"Develop a second relationship thread"}',
  '2026-08-04','Seeded RR-0. identify/develop stages deliberately excluded (§4.2).',
  datetime('now'),datetime('now')),

 -- 4.3 Executive sponsorship
 ('rrd-exec-identified-1','exec_identified',1,'executive_sponsorship',1,
  'Executive identified',
  'A non-placeholder executive-layer stakeholder exists in scope.',
  'A non-placeholder person holds an executive-layer stakeholder role in this program or an inheritable account relationship.',
  'program','exec_identified',1,
  '{"require_explicit_layer":false,"executive_layer":"executive"}',
  '["stakeholder_role"]',
  '{"exec_identified":{"window_days":null}}',
  '{}',
  '{"native_type":"task","title":"Identify the executive sponsor"}',
  '2026-08-04','Seeded RR-0. Identity is not engagement; freshness is evaluated on the engagement component instead.',
  datetime('now'),datetime('now')),

 ('rrd-exec-engaged-1','exec_engaged',1,'executive_sponsorship',1,
  'Executive engaged',
  'The identified executive has a current meaningful touch.',
  'The executive has a meaningful accepted interaction inside the touch window.',
  'program','exec_engaged',1,
  '{"touch_window_days":90,"include_account_level_touches":true}',
  '["interaction"]',
  '{"exec_engaged":{"window_days":90}}',
  '{}',
  '{"native_type":"task","title":"Re-engage the executive sponsor"}',
  '2026-08-04','Seeded RR-0. Wider window than operational contacts by design.',
  datetime('now'),datetime('now')),

 ('rrd-exec-value-1','exec_value_link',1,'executive_sponsorship',1,
  'Executive tied to an owned outcome',
  'The executive is explicitly linked to the metric or value outcome they sponsor.',
  'An explicit typed relation ties the executive to a metric definition or value target. Free-text similarity is not a link.',
  'program','exec_value_link',1,
  -- No typed stakeholder-to-metric relation exists yet, so this component cannot be satisfied and
  -- the pillar caps at thin (§4.3). RR-3 delivers the relation and a version bump enables met.
  '{"requires_typed_relation":true,"relation_available":false}',
  '["metric_definition","value_target"]',
  '{"exec_value_link":{"window_days":null}}',
  '{}',
  '{"native_type":"task","title":"Agree which owned metric this executive is sponsoring"}',
  '2026-08-04','Seeded RR-0. relation_available=false until RR-3; the reason is stated, never silently met.',
  datetime('now'),datetime('now')),

 -- 4.4 Quantified value
 ('rrd-value-baseline-1','value_baseline_locked',1,'quantified_value',1,
  'Locked baseline observation',
  'A pre-deployment measurement explicitly locked as the baseline.',
  'An explicitly locked baseline observation exists in scope. A negotiated value target is not a baseline.',
  'program','value_baseline_locked',1,
  '{"accept_campaign_baseline":true,"accept_inferred_by_date":false}',
  '["metric_observation","adoption_campaign_target"]',
  '{"value_baseline_locked":{"window_days":null}}',
  '{}',
  '{"native_type":"task","title":"Lock a baseline observation before measuring impact"}',
  '2026-08-04','Seeded RR-0. Only an explicitly locked baseline counts; date proximity never infers one (§4.4).',
  datetime('now'),datetime('now')),

 ('rrd-value-comparison-1','value_comparison_observation',1,'quantified_value',1,
  'Comparable after-measurement',
  'A later observation comparable to the baseline on definition, version, program, cohort, and unit.',
  'A later observation shares the baseline metric definition, a compatible definition version, the same program and cohort, and the same unit, and is current under the metric freshness rule.',
  'program','value_comparison_observation',1,
  '{"comparison_window_days":120,"require_same_definition_version":true,"require_same_cohort":true,"require_same_unit":true}',
  '["metric_observation","value_story"]',
  '{"value_comparison_observation":{"window_days":120}}',
  '{}',
  '{"native_type":"task","title":"Record a comparable after-measurement"}',
  '2026-08-04','Seeded RR-0. Mismatched version/cohort/unit is reported as not comparable, never silently compared.',
  datetime('now'),datetime('now')),

 -- 4.5 Budget owner
 ('rrd-budget-authority-1','budget_authority_evidence',1,'budget_owner',1,
  'Evidenced budget authority',
  'A named non-placeholder person has accepted budget-authority evidence.',
  'A non-placeholder person is recorded with budget authority through a stakeholder role, funding pool ownership, or an expansion opportunity budget owner.',
  'account','budget_authority_evidence',1,
  '{"authority_roles":["budget_owner","financial_gatekeeper"]}',
  '["stakeholder_role","funding_pool","expansion_opportunity"]',
  '{"budget_authority_evidence":{"window_days":null}}',
  '{}',
  '{"native_type":"task","title":"Confirm who holds the budget"}',
  '2026-08-04','Seeded RR-0. Disagreeing accepted records produce conflicted, never a silent pick (§4.5).',
  datetime('now'),datetime('now')),

 ('rrd-budget-engagement-1','budget_owner_engagement',1,'budget_owner',1,
  'Budget owner engaged',
  'Engagement with the budget owner, evaluated separately from identity.',
  'The identified budget owner has a meaningful accepted interaction inside the touch window.',
  'account','budget_owner_engagement',1,
  '{"touch_window_days":90}',
  '["interaction"]',
  '{"budget_owner_engagement":{"window_days":90}}',
  '{}',
  '{"native_type":"task","title":"Re-engage the budget owner"}',
  '2026-08-04','Seeded RR-0. Known identity with stale engagement stays thin+stale, not unknown (§3.4).',
  datetime('now'),datetime('now')),

 -- 4.6 Active expansion plan
 ('rrd-expansion-open-1','expansion_opportunity_open',1,'active_expansion_plan',1,
  'Open expansion opportunity',
  'An open expansion opportunity exists in scope.',
  'A non-archived expansion opportunity with status open exists for the account.',
  'account','expansion_opportunity_open',1,
  '{}',
  '["expansion_opportunity"]',
  '{"expansion_opportunity_open":{"window_days":null}}',
  '{}',
  '{"native_type":"task","title":"Open the expansion opportunity"}',
  '2026-08-04','Seeded RR-0.',
  datetime('now'),datetime('now')),

 ('rrd-expansion-mutual-1','expansion_client_ownership',1,'active_expansion_plan',1,
  'Client-side ownership',
  'A named client sponsor and accepted evidence of client acknowledgement.',
  'The opportunity names a non-placeholder client sponsor and carries accepted source evidence of client acknowledgement. Free-text supporting evidence does not prove mutuality.',
  'account','expansion_client_ownership',1,
  '{"requires_typed_acknowledgement":true,"relation_available":false,"accept_source_interaction":true}',
  '["expansion_opportunity","interaction","source_reference"]',
  '{"expansion_client_ownership":{"window_days":null}}',
  '{}',
  '{"native_type":"task","title":"Confirm client co-ownership of the expansion"}',
  '2026-08-04','Seeded RR-0. Full mutual-plan claims wait for the RR-3 typed relation (§4.6).',
  datetime('now'),datetime('now')),

 ('rrd-expansion-next-1','expansion_dated_next_step',1,'active_expansion_plan',1,
  'Dated next step',
  'A dated next action or linked milestone, so the plan is live rather than nominal.',
  'The opportunity has a decision date or a dated next action.',
  'account','expansion_dated_next_step',1,
  '{"require_dated":true}',
  '["expansion_opportunity","milestone"]',
  '{"expansion_dated_next_step":{"window_days":null}}',
  '{}',
  '{"native_type":"task","title":"Date the next step on the expansion"}',
  '2026-08-04','Seeded RR-0.',
  datetime('now'),datetime('now')),

 ('rrd-expansion-budget-1','expansion_budget_state',1,'active_expansion_plan',1,
  'Live budget state',
  'The opportunity sits in a budget state that indicates real commercial motion.',
  'The opportunity budget state is at or beyond the configured live threshold.',
  'account','expansion_budget_state',1,
  '{"live_budget_states":["in_planning","formally_allocated","requisition_created","procurement_approved","executed"]}',
  '["expansion_opportunity"]',
  '{"expansion_budget_state":{"window_days":null}}',
  '{}',
  '{"native_type":"task","title":"Advance the expansion budget state"}',
  '2026-08-04','Seeded RR-0. conceptually_supported is deliberately not live (§4.6).',
  datetime('now'),datetime('now'));
