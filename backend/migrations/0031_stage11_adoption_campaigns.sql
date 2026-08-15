-- Migration 0031 — Stage 11.0: adoption campaign core (ADOPTION-CAMPAIGN-SPEC.md §§2-5, 11)
--
-- A campaign is a time-boxed, measurable intervention against ONE stable cohort inside an
-- existing program. It adds one concept and links to records that already exist; nothing here
-- clones a task, a comms entry, a champion, or a milestone.
--
-- The §5 measurement contract is the part that needs schema support rather than convention,
-- because it is where the module would otherwise render numbers that look like evidence:
--
--   * The baseline locks a SERIES, not a point. `baseline_trajectory_json` freezes the ordered
--     prior observation IDs at readiness. A lone baseline cannot distinguish "the intervention
--     moved it" from "it was already moving," and the delta renders identically either way.
--   * Comparators must be DISJOINT from the treated cohort. Population views overlap segments by
--     construction here — that is what population_view_segments is for — so without a check a
--     "control" can contain the treated. Enforced by trigger below.
--   * A campaign converted from a stalled-cohort signal was selected BECAUSE its latest reading
--     fell. Measuring it again after that trough captures rebound, not effect. The origin is
--     recorded (`created_from_signal_episode_id`) so the service can attach the standing
--     regression-to-the-mean caution rather than leaving the reader to infer it.
--
-- Trust boundaries unchanged: the unit is a segment or privacy-safe view. There is no recipient
-- list, no named-person activation field, no individual funnel, and no send path.

PRAGMA foreign_keys = ON;

-- --- §2 identity and lifecycle -----------------------------------------------------------------
CREATE TABLE adoption_campaigns (
    id              TEXT PRIMARY KEY,
    account_id      TEXT NOT NULL REFERENCES accounts(id),
    program_id      TEXT NOT NULL REFERENCES programs(id),

    -- Exactly one stable cohort. Free-text audiences are what the population model replaced.
    segment_id      TEXT REFERENCES population_segments(id),
    view_id         TEXT REFERENCES population_views(id),
    use_case_id     TEXT NOT NULL REFERENCES use_cases(id),
    cell_id         TEXT REFERENCES whitespace_cells(id),

    name            TEXT NOT NULL,
    target_behavior TEXT NOT NULL,          -- cohort-level, plain language
    hypothesis      TEXT NOT NULL,          -- "If we do X at Y moment, this cohort should do Z because..."

    planned_start_on TEXT NOT NULL,
    planned_end_on   TEXT NOT NULL,
    evaluation_on    TEXT,                  -- must fall after the intervention window

    -- One canonical internal owner; delivery ownership stays on the linked records.
    internal_owner_person_id  TEXT NOT NULL REFERENCES persons(id),
    client_sponsor_person_id  TEXT REFERENCES persons(id),
    lead_champion_person_id   TEXT REFERENCES persons(id),

    evaluation_design TEXT NOT NULL DEFAULT 'descriptive'
        CHECK (evaluation_design IN ('descriptive','pre_post','comparator')),

    status          TEXT NOT NULL DEFAULT 'draft'
        CHECK (status IN ('draft','ready','active','paused','completed','cancelled')),

    -- Readiness exceptions are reason-logged, never silent (§2.3).
    baseline_gap_reason      TEXT,
    sponsor_gap_reason       TEXT,
    -- §11.2: a second active campaign on the same cohort+use case+primary target confounds both
    -- evaluations. Permitted, but only when the operator says so out loud.
    concurrent_intervention_reason TEXT,
    -- §5.1: a cohort already at its target is not a lift opportunity; say which it is.
    already_met_reason       TEXT,

    pause_reason    TEXT,
    resume_condition TEXT,
    cancel_reason   TEXT,

    completion_outcome TEXT CHECK (completion_outcome IS NULL OR completion_outcome IN
        ('target_met','improved_not_met','no_demonstrated_change','regressed','inconclusive')),
    completion_reviewed_on TEXT,
    completion_note TEXT,

    -- Provenance for the §5.2 selection-effect caution.
    created_from_signal_episode_id TEXT REFERENCES signal_episodes(id),
    diagnosis_source_reference_id  TEXT REFERENCES source_references(id),
    diagnosis_source_interaction_id TEXT REFERENCES interactions(id),

    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL,
    archived        INTEGER NOT NULL DEFAULT 0,
    archived_at     TEXT,
    archived_by     TEXT,

    CHECK ((segment_id IS NOT NULL AND view_id IS NULL)
        OR (segment_id IS NULL AND view_id IS NOT NULL)),
    CHECK (planned_end_on >= planned_start_on),
    CHECK (evaluation_on IS NULL OR evaluation_on >= planned_end_on),
    CHECK (status <> 'paused' OR pause_reason IS NOT NULL),
    CHECK (status <> 'cancelled' OR cancel_reason IS NOT NULL),
    CHECK (status <> 'completed' OR (completion_outcome IS NOT NULL AND completion_reviewed_on IS NOT NULL))
);
CREATE INDEX idx_campaign_account ON adoption_campaigns(account_id, status);
CREATE INDEX idx_campaign_cohort ON adoption_campaigns(segment_id, view_id, use_case_id);

-- Append-only. Status is never patched generically; dedicated transitions write here.
CREATE TABLE adoption_campaign_state_history (
    id          TEXT PRIMARY KEY,
    campaign_id TEXT NOT NULL REFERENCES adoption_campaigns(id),
    from_status TEXT,
    to_status   TEXT NOT NULL,
    reason      TEXT NOT NULL,
    actor       TEXT,
    changed_on  TEXT NOT NULL,
    created_at  TEXT NOT NULL
);
CREATE INDEX idx_campaign_history ON adoption_campaign_state_history(campaign_id, changed_on);

-- --- §3 barrier diagnosis ----------------------------------------------------------------------
-- Cohort-level professional observations. Deliberately no "affected user" person id.
CREATE TABLE adoption_campaign_barriers (
    id          TEXT PRIMARY KEY,
    campaign_id TEXT NOT NULL REFERENCES adoption_campaigns(id),
    category    TEXT NOT NULL CHECK (category IN ('capability','opportunity','motivation','unknown')),
    description TEXT NOT NULL,
    confidence  TEXT NOT NULL DEFAULT 'hypothesis'
        CHECK (confidence IN ('observed','reported','hypothesis')),
    observed_on TEXT NOT NULL,
    source_reference_id  TEXT REFERENCES source_references(id),
    source_interaction_id TEXT REFERENCES interactions(id),
    is_primary  INTEGER NOT NULL DEFAULT 0,
    state       TEXT NOT NULL DEFAULT 'open' CHECK (state IN ('open','addressed','ruled_out')),
    resolution_note TEXT,
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL,
    archived    INTEGER NOT NULL DEFAULT 0,
    archived_at TEXT,
    archived_by TEXT,
    -- Even "we don't know yet" is a dated claim with a source (§2.3).
    CHECK (source_reference_id IS NOT NULL OR source_interaction_id IS NOT NULL)
);
CREATE INDEX idx_campaign_barrier ON adoption_campaign_barriers(campaign_id, state);
CREATE UNIQUE INDEX idx_campaign_primary_barrier ON adoption_campaign_barriers(campaign_id)
    WHERE is_primary = 1 AND archived = 0;

-- --- §5 measurement --------------------------------------------------------------------------
CREATE TABLE adoption_campaign_targets (
    id            TEXT PRIMARY KEY,
    campaign_id   TEXT NOT NULL REFERENCES adoption_campaigns(id),
    value_target_id TEXT NOT NULL REFERENCES value_targets(id),
    role          TEXT NOT NULL CHECK (role IN ('primary','secondary','guardrail')),

    -- The locked point...
    baseline_observation_id TEXT REFERENCES metric_observations(id),
    baseline_locked_on      TEXT,
    -- ...and the series it sits in (§5.1). Ordered observation IDs, oldest first.
    baseline_trajectory_json TEXT,

    -- Comparator design only. Must be disjoint from the treated cohort (trigger below).
    comparator_segment_id TEXT REFERENCES population_segments(id),
    comparator_view_id    TEXT REFERENCES population_views(id),

    created_at    TEXT NOT NULL,
    updated_at    TEXT NOT NULL,
    archived      INTEGER NOT NULL DEFAULT 0,
    archived_at   TEXT,
    archived_by   TEXT,
    CHECK (comparator_segment_id IS NULL OR comparator_view_id IS NULL)
);
CREATE UNIQUE INDEX idx_campaign_primary_target ON adoption_campaign_targets(campaign_id)
    WHERE role = 'primary' AND archived = 0;
CREATE UNIQUE INDEX idx_campaign_target_unique ON adoption_campaign_targets(campaign_id, value_target_id)
    WHERE archived = 0;

-- --- §4 the intervention sequence ---------------------------------------------------------------
-- Typed nullable FKs plus exactly-one CHECK. An unchecked type/id pair is explicitly not
-- acceptable (§4.1) — this codebase has already been bitten by dangling polymorphic links.
-- No second due date, owner, or completion status: those derive from the linked record, so the
-- campaign can never disagree with the Ledger or Plan.
CREATE TABLE adoption_campaign_plan_links (
    id              TEXT PRIMARY KEY,
    campaign_id     TEXT NOT NULL REFERENCES adoption_campaigns(id),
    sequence        INTEGER NOT NULL DEFAULT 0,
    intervention_kind TEXT NOT NULL CHECK (intervention_kind IN
        ('enablement','workflow_embed','champion_action','communication','reinforcement','discovery')),
    intended_barrier_id TEXT REFERENCES adoption_campaign_barriers(id),
    purpose         TEXT,
    cue             TEXT,                    -- §4.3 cue-action-reinforcement
    is_reinforcement INTEGER NOT NULL DEFAULT 0,

    task_id         TEXT REFERENCES tasks(id),
    commitment_id   TEXT REFERENCES commitments(id),
    milestone_id    TEXT REFERENCES milestones(id),
    comms_entry_id  TEXT REFERENCES comms_entries(id),
    deployment_moment_id TEXT REFERENCES deployment_moments(id),
    calendar_event_id TEXT REFERENCES calendar_events(id),
    generated_document_id TEXT REFERENCES generated_documents(id),
    messaging_entry_id TEXT REFERENCES messaging_entries(id),

    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL,
    archived        INTEGER NOT NULL DEFAULT 0,
    archived_at     TEXT,
    archived_by     TEXT,

    CHECK ((task_id IS NOT NULL) + (commitment_id IS NOT NULL) + (milestone_id IS NOT NULL)
         + (comms_entry_id IS NOT NULL) + (deployment_moment_id IS NOT NULL)
         + (calendar_event_id IS NOT NULL) + (generated_document_id IS NOT NULL)
         + (messaging_entry_id IS NOT NULL) = 1)
);
CREATE INDEX idx_campaign_plan ON adoption_campaign_plan_links(campaign_id, sequence);

-- --- §5.3 checkpoints ---------------------------------------------------------------------------
CREATE TABLE adoption_campaign_checkpoints (
    id            TEXT PRIMARY KEY,
    campaign_id   TEXT NOT NULL REFERENCES adoption_campaigns(id),
    scheduled_on  TEXT NOT NULL,
    held_on       TEXT,
    observations_reviewed_json TEXT,        -- the exact observation IDs looked at
    assessment    TEXT CHECK (assessment IS NULL OR assessment IN ('on_track','at_risk','unknown')),
    decision      TEXT CHECK (decision IS NULL OR decision IN ('continue','adjust','pause','complete')),
    reason        TEXT,
    source_interaction_id TEXT REFERENCES interactions(id),
    source_reference_id   TEXT REFERENCES source_references(id),
    next_evidence_on TEXT,
    created_at    TEXT NOT NULL,
    updated_at    TEXT NOT NULL,
    archived      INTEGER NOT NULL DEFAULT 0,
    archived_at   TEXT,
    archived_by   TEXT,
    -- A held checkpoint asserts something; it needs its assessment, decision, and reason.
    CHECK (held_on IS NULL OR (assessment IS NOT NULL AND decision IS NOT NULL AND reason IS NOT NULL))
);
CREATE INDEX idx_campaign_checkpoint ON adoption_campaign_checkpoints(campaign_id, scheduled_on);

-- --- §11.2 cross-account and integrity rules ----------------------------------------------------
-- Relationship constraints single-column foreign keys cannot express. The recurring defect class
-- in this repo is "look a row up by id, then trust the caller about which account it belongs to."

CREATE TRIGGER trg_campaign_scope_insert BEFORE INSERT ON adoption_campaigns
WHEN NOT EXISTS (SELECT 1 FROM programs p WHERE p.id=NEW.program_id AND p.account_id=NEW.account_id)
  OR (NEW.segment_id IS NOT NULL AND NOT EXISTS (
        SELECT 1 FROM population_segments s WHERE s.id=NEW.segment_id AND s.account_id=NEW.account_id))
  OR (NEW.view_id IS NOT NULL AND NOT EXISTS (
        SELECT 1 FROM population_views v WHERE v.id=NEW.view_id AND v.account_id=NEW.account_id))
  OR (NEW.cell_id IS NOT NULL AND NOT EXISTS (
        SELECT 1 FROM whitespace_cells c WHERE c.id=NEW.cell_id AND c.account_id=NEW.account_id
          AND c.use_case_id=NEW.use_case_id
          AND IFNULL(c.segment_id,'')=IFNULL(NEW.segment_id,'')
          AND IFNULL(c.view_id,'')=IFNULL(NEW.view_id,'')))
  OR (NEW.use_case_id IS NOT NULL AND EXISTS (
        SELECT 1 FROM use_cases u WHERE u.id=NEW.use_case_id
          AND u.account_id IS NOT NULL AND u.account_id<>NEW.account_id))
BEGIN SELECT RAISE(ABORT, 'campaign program, population, cell, or use case belongs to a different account'); END;

CREATE TRIGGER trg_campaign_scope_update BEFORE UPDATE OF
account_id, program_id, segment_id, view_id, cell_id, use_case_id ON adoption_campaigns
WHEN NOT EXISTS (SELECT 1 FROM programs p WHERE p.id=NEW.program_id AND p.account_id=NEW.account_id)
  OR (NEW.segment_id IS NOT NULL AND NOT EXISTS (
        SELECT 1 FROM population_segments s WHERE s.id=NEW.segment_id AND s.account_id=NEW.account_id))
  OR (NEW.view_id IS NOT NULL AND NOT EXISTS (
        SELECT 1 FROM population_views v WHERE v.id=NEW.view_id AND v.account_id=NEW.account_id))
BEGIN SELECT RAISE(ABORT, 'campaign program or population belongs to a different account'); END;

-- Client people belong to the account; the internal owner is Valence (§6).
CREATE TRIGGER trg_campaign_people_insert BEFORE INSERT ON adoption_campaigns
WHEN NOT EXISTS (SELECT 1 FROM persons p WHERE p.id=NEW.internal_owner_person_id AND p.affiliation='valence')
  OR (NEW.client_sponsor_person_id IS NOT NULL AND NOT EXISTS (
        SELECT 1 FROM persons p WHERE p.id=NEW.client_sponsor_person_id AND p.account_id=NEW.account_id))
  OR (NEW.lead_champion_person_id IS NOT NULL AND NOT EXISTS (
        SELECT 1 FROM persons p WHERE p.id=NEW.lead_champion_person_id AND p.account_id=NEW.account_id))
BEGIN SELECT RAISE(ABORT, 'campaign internal owner must be Valence and client people must belong to the account'); END;

CREATE TRIGGER trg_campaign_people_update BEFORE UPDATE OF
internal_owner_person_id, client_sponsor_person_id, lead_champion_person_id ON adoption_campaigns
WHEN NOT EXISTS (SELECT 1 FROM persons p WHERE p.id=NEW.internal_owner_person_id AND p.affiliation='valence')
  OR (NEW.client_sponsor_person_id IS NOT NULL AND NOT EXISTS (
        SELECT 1 FROM persons p WHERE p.id=NEW.client_sponsor_person_id AND p.account_id=NEW.account_id))
  OR (NEW.lead_champion_person_id IS NOT NULL AND NOT EXISTS (
        SELECT 1 FROM persons p WHERE p.id=NEW.lead_champion_person_id AND p.account_id=NEW.account_id))
BEGIN SELECT RAISE(ABORT, 'campaign internal owner must be Valence and client people must belong to the account'); END;

-- A target must belong to the same account AND name the same population as the campaign; a
-- cross-population target would measure a cohort the campaign never touched.
CREATE TRIGGER trg_campaign_target_scope_insert BEFORE INSERT ON adoption_campaign_targets
WHEN NOT EXISTS (
    SELECT 1 FROM adoption_campaigns c JOIN value_targets vt ON vt.id=NEW.value_target_id
    WHERE c.id=NEW.campaign_id AND vt.account_id=c.account_id
      AND IFNULL(vt.segment_id,'')=IFNULL(c.segment_id,'')
      AND IFNULL(vt.view_id,'')=IFNULL(c.view_id,''))
BEGIN SELECT RAISE(ABORT, 'campaign target belongs to a different account or population'); END;

-- §5.2 — the control cannot contain the treated. Views overlap segments by construction, so
-- both sides resolve to base-segment sets before comparison.
CREATE TRIGGER trg_campaign_comparator_disjoint_insert BEFORE INSERT ON adoption_campaign_targets
WHEN (NEW.comparator_segment_id IS NOT NULL OR NEW.comparator_view_id IS NOT NULL)
 AND EXISTS (
    SELECT 1 FROM adoption_campaigns c WHERE c.id=NEW.campaign_id AND (
        -- comparator segment is, or is inside, the treated cohort
        (NEW.comparator_segment_id IS NOT NULL AND (
            NEW.comparator_segment_id = c.segment_id
         OR NEW.comparator_segment_id IN (SELECT segment_id FROM population_view_segments
                                          WHERE view_id = c.view_id)))
        -- comparator view shares any base segment with the treated cohort
     OR (NEW.comparator_view_id IS NOT NULL AND (
            c.segment_id IN (SELECT segment_id FROM population_view_segments
                             WHERE view_id = NEW.comparator_view_id)
         OR EXISTS (SELECT 1 FROM population_view_segments a
                    JOIN population_view_segments b ON a.segment_id=b.segment_id
                    WHERE a.view_id = NEW.comparator_view_id AND b.view_id = c.view_id)))))
BEGIN SELECT RAISE(ABORT, 'comparator population overlaps the treated cohort'); END;

CREATE TRIGGER trg_campaign_barrier_source_insert BEFORE INSERT ON adoption_campaign_barriers
WHEN (NEW.source_interaction_id IS NOT NULL AND NOT EXISTS (
        SELECT 1 FROM adoption_campaigns c JOIN interactions i ON i.id=NEW.source_interaction_id
        WHERE c.id=NEW.campaign_id AND i.account_id=c.account_id))
BEGIN SELECT RAISE(ABORT, 'barrier source interaction belongs to a different account'); END;

-- State history is append-only; a rewritten transition log is not a log.
CREATE TRIGGER trg_campaign_history_immutable BEFORE UPDATE ON adoption_campaign_state_history
BEGIN SELECT RAISE(ABORT, 'campaign state history is append-only'); END;
CREATE TRIGGER trg_campaign_history_no_delete BEFORE DELETE ON adoption_campaign_state_history
BEGIN SELECT RAISE(ABORT, 'campaign state history is append-only'); END;
