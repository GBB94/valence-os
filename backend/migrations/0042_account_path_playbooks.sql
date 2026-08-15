-- Migration 0042 — Account Path Slice 3: playbooks, plan instances, and governed exceptions.
--
-- ACCOUNT-PATH-SPEC.md §13. This is the planning layer RELATIONSHIP-READINESS-SPEC.md §0.4
-- deliberately declines to store. Five rules shape every table below, and each one is the reason a
-- more obvious design was rejected:
--
--   * **A plan instance schedules a requirement; it never states one.** There is no `state`,
--     `met`, `freshness`, `coverage`, or `applicability` column anywhere in this file. Readiness
--     computes those live from accepted records (RR §2), and a stored copy here would be the
--     second source of truth that specification exists to prevent. The Slice 3 introspection test
--     asserts the absence by name, which only works because nothing here offers a column to fill.
--   * **`recorded_complete` is a planning fact, not evidence.** It carries a legacy checkbox
--     across the compatibility migration (§13.5.5) so the operator does not lose the tick they
--     made. Readiness never reads it, and no evaluator may. A checkbox is not evidence.
--   * **Playbook versions do not retire each other.** Unlike the definition tables in 0041 there
--     is no "at most one live version" index: an account stays on the version it instantiated
--     until an explicit, previewed upgrade moves it, so several versions are selectable at once.
--   * **`necessity` is a planning stance, not readiness applicability.** It decides one thing —
--     whether an entry may be excluded at instantiation. It never enters the readiness
--     applicability axis, which is derived from program phase and from the exceptions below.
--   * **An exception can suppress, never satisfy.** `kind` offers exactly two values and neither
--     of them asserts a condition is met. There is deliberately no `satisfied` or `override_state`
--     kind, because an operator decision that could manufacture `met` would fabricate evidence.
--
-- Mock-only data. The seeded playbooks are versioned templates, not benchmarks.
PRAGMA foreign_keys = ON;

-- --- playbook definitions -----------------------------------------------------------------------
-- A playbook is an ordered, versioned set of readiness requirement definitions pinned at exact
-- versions, plus relative timing. Editing a template creates a NEW version; it never rewrites an
-- instantiated plan (§13.9).
CREATE TABLE readiness_playbook_definitions (
    id                    TEXT PRIMARY KEY,
    key                   TEXT NOT NULL,
    version               INTEGER NOT NULL CHECK (version >= 1),
    label                 TEXT NOT NULL,
    purpose               TEXT NOT NULL,

    kind                  TEXT NOT NULL CHECK (kind IN
                            ('onboarding','adoption','expansion','renewal','compatibility','other')),

    -- The anchor an instantiation normally uses, and the full set it may use. A request naming an
    -- anchor outside this list is rejected: a relative rule whose anchor nobody agreed to is not a
    -- rule, it is a guess about when the work is due.
    default_anchor        TEXT NOT NULL,
    allowed_anchors_json  TEXT NOT NULL DEFAULT '[]',

    default_scope         TEXT NOT NULL CHECK (default_scope IN ('account','program')),

    active_from           TEXT NOT NULL,
    retired_at            TEXT,
    governance_note       TEXT NOT NULL,

    created_at            TEXT NOT NULL,
    updated_at            TEXT NOT NULL,
    archived              INTEGER NOT NULL DEFAULT 0,
    archived_at           TEXT,
    archived_by           TEXT,

    UNIQUE (key, version),
    CHECK (json_valid(allowed_anchors_json)),
    CHECK (retired_at IS NULL OR retired_at >= active_from)
);
CREATE INDEX idx_readiness_playbook_key ON readiness_playbook_definitions(key, version);

-- --- playbook entries ---------------------------------------------------------------------------
-- One requirement definition, pinned at an exact version, with its relative timing. The foreign key
-- is on (key, version) rather than on the definition id so a later definition version cannot be
-- picked up silently by an existing playbook version.
CREATE TABLE readiness_playbook_entries (
    id                   TEXT PRIMARY KEY,
    playbook_key         TEXT NOT NULL,
    playbook_version     INTEGER NOT NULL,

    requirement_key      TEXT NOT NULL,
    requirement_version  INTEGER NOT NULL,

    display_order        INTEGER NOT NULL DEFAULT 0,
    -- See the header note: planning stance only. `optional` entries are the only ones an
    -- instantiation may exclude.
    necessity            TEXT NOT NULL DEFAULT 'required'
                           CHECK (necessity IN ('required','optional')),
    -- Days from the plan's anchor date. NULL means the entry carries no date of its own,
    -- which is a real answer: not every condition is time-boxed, and inventing an offset so the
    -- column is full would put a fabricated due date in front of an operator.
    offset_days          INTEGER,
    note                 TEXT,

    created_at           TEXT NOT NULL,
    updated_at           TEXT NOT NULL,

    UNIQUE (playbook_key, playbook_version, requirement_key),
    FOREIGN KEY (playbook_key, playbook_version)
        REFERENCES readiness_playbook_definitions(key, version),
    FOREIGN KEY (requirement_key, requirement_version)
        REFERENCES readiness_requirement_definitions(key, version)
);
CREATE INDEX idx_readiness_playbook_entry_book
    ON readiness_playbook_entries(playbook_key, playbook_version, display_order);

-- --- plans --------------------------------------------------------------------------------
-- The act of instantiating a playbook version against one scope: which version, which anchor, who
-- decided, and what they excluded. Keeping this separate from the per-requirement rows is what lets
-- §13.4's duplicate rule ("one active instance per playbook and scope") be a database constraint
-- rather than a convention, and what gives an upgrade a chain to record.
CREATE TABLE readiness_plans (
    id                          TEXT PRIMARY KEY,
    account_id                  TEXT NOT NULL REFERENCES accounts(id),
    program_id                  TEXT REFERENCES programs(id),

    playbook_key                TEXT NOT NULL,
    playbook_version            INTEGER NOT NULL,

    anchor_type                 TEXT NOT NULL,
    anchor_date                 TEXT NOT NULL,
    excluded_requirements_json  TEXT NOT NULL DEFAULT '[]',

    status                      TEXT NOT NULL DEFAULT 'active'
                                  CHECK (status IN ('active','superseded')),
    supersedes_id               TEXT REFERENCES readiness_plans(id),

    actor_id                    TEXT NOT NULL,
    note                        TEXT,

    created_at                  TEXT NOT NULL,
    updated_at                  TEXT NOT NULL,
    archived                    INTEGER NOT NULL DEFAULT 0,
    archived_at                 TEXT,
    archived_by                 TEXT,

    FOREIGN KEY (playbook_key, playbook_version)
        REFERENCES readiness_playbook_definitions(key, version),
    CHECK (json_valid(excluded_requirements_json))
);

-- `ifnull(program_id,'')` because SQL NULLs do not collide in a unique index, so without it an
-- account-scoped plan could be instantiated any number of times.
CREATE UNIQUE INDEX idx_readiness_plan_live
    ON readiness_plans(account_id, ifnull(program_id,''), playbook_key)
    WHERE status = 'active' AND archived = 0;

-- --- plan instances -----------------------------------------------------------------------------
-- One scheduled requirement. The resolved `due_date` and the rule that produced it are both kept:
-- the date is what the operator works to, the rule is what an upgrade re-resolves and what explains
-- the date when the anchor later moves.
CREATE TABLE readiness_plan_instances (
    id                         TEXT PRIMARY KEY,
    plan_id              TEXT NOT NULL REFERENCES readiness_plans(id),

    account_id                 TEXT NOT NULL REFERENCES accounts(id),
    program_id                 TEXT REFERENCES programs(id),

    playbook_key               TEXT NOT NULL,
    playbook_version           INTEGER NOT NULL,

    requirement_key            TEXT NOT NULL,
    requirement_version        INTEGER NOT NULL,
    pillar_key                 TEXT NOT NULL,

    necessity                  TEXT NOT NULL CHECK (necessity IN ('required','optional')),

    -- {"anchor":"kickoff","offset_days":14} — preserved verbatim (§13.4).
    due_rule_json              TEXT NOT NULL DEFAULT '{}',
    due_date                   TEXT,

    -- §13.5.5. An operator-recorded planning fact carried across from a legacy checkbox. It is not
    -- evidence, no evaluator reads it, and it never becomes a readiness state.
    recorded_complete          INTEGER NOT NULL DEFAULT 0 CHECK (recorded_complete IN (0,1)),
    recorded_complete_on       TEXT,
    recorded_complete_note     TEXT,

    -- Provenance for a row created by the checklist compatibility migration, so the report can be
    -- rebuilt and the rerun stays idempotent.
    compatibility_source_type  TEXT,
    compatibility_source_id    TEXT,

    created_at                 TEXT NOT NULL,
    updated_at                 TEXT NOT NULL,
    archived                   INTEGER NOT NULL DEFAULT 0,
    archived_at                TEXT,
    archived_by                TEXT,

    UNIQUE (plan_id, requirement_key),
    FOREIGN KEY (requirement_key, requirement_version)
        REFERENCES readiness_requirement_definitions(key, version),
    CHECK (json_valid(due_rule_json)),
    CHECK (recorded_complete = 0 OR recorded_complete_on IS NOT NULL)
);
CREATE INDEX idx_readiness_plan_instance_scope
    ON readiness_plan_instances(account_id, ifnull(program_id,''), requirement_key)
    WHERE archived = 0;
CREATE INDEX idx_readiness_plan_instance_compat
    ON readiness_plan_instances(compatibility_source_type, compatibility_source_id);

-- --- exceptions ---------------------------------------------------------------------------------
-- The operator decision RELATIONSHIP-READINESS-SPEC.md §3.2 delegates here, plus waivers (§13.2.7).
-- The two kinds do different things on purpose:
--
--   * `not_applicable` — the condition does not apply in this scope. Readiness stops evaluating it
--     and reports it as suppressed. It cannot make a pillar `met`: when every one of a pillar's
--     requirements is suppressed the pillar reports `not_applicable`, not readiness.
--   * `waiver` — the condition applies and the gap is knowingly accepted for now. The component
--     keeps its real state; only the outstanding ask is silenced. Waiving something does not make
--     the relationship ready, and the state must keep saying so.
--
-- A reason is structurally required. An unexplained suppression is indistinguishable from a bug.
CREATE TABLE readiness_exceptions (
    id                TEXT PRIMARY KEY,
    account_id        TEXT NOT NULL REFERENCES accounts(id),
    program_id        TEXT REFERENCES programs(id),

    requirement_key   TEXT NOT NULL,
    plan_instance_id  TEXT REFERENCES readiness_plan_instances(id),

    kind              TEXT NOT NULL CHECK (kind IN ('not_applicable','waiver')),
    reason            TEXT NOT NULL CHECK (length(trim(reason)) >= 10),
    actor_id          TEXT NOT NULL,
    decided_on        TEXT NOT NULL,
    -- A waiver that never expires is a silent permanent gap, so the service requires one; the
    -- column stays nullable because a `not_applicable` decision is not time-boxed.
    expires_on        TEXT,

    revoked_at        TEXT,
    revoked_by        TEXT,
    revoked_reason    TEXT,

    created_at        TEXT NOT NULL,
    updated_at        TEXT NOT NULL,
    archived          INTEGER NOT NULL DEFAULT 0,
    archived_at       TEXT,
    archived_by       TEXT,

    CHECK (expires_on IS NULL OR expires_on >= decided_on),
    CHECK (revoked_at IS NULL OR revoked_reason IS NOT NULL)
);
CREATE UNIQUE INDEX idx_readiness_exception_live
    ON readiness_exceptions(account_id, ifnull(program_id,''), requirement_key, kind)
    WHERE revoked_at IS NULL AND archived = 0;
CREATE INDEX idx_readiness_exception_history
    ON readiness_exceptions(account_id, requirement_key, decided_on);

-- --- checklist compatibility map ------------------------------------------------------------------
-- §13.5.1-2: the explicit mapping, exact keys only. It lives here rather than in code so adding a
-- mapping is a reviewed migration rather than an edit to a running service, and so a reader can
-- see the entire set of claims the compatibility migration is allowed to make.
--
-- Labels are deliberately NOT matched. "Baselines captured" and "Lock a baseline" describe the same
-- intent to a human and different things to an evaluator, and a fuzzy match would silently create a
-- plan instance for a requirement nobody agreed to.
CREATE TABLE readiness_checklist_requirement_map (
    template_key         TEXT PRIMARY KEY,
    requirement_key      TEXT NOT NULL,
    requirement_version  INTEGER NOT NULL,
    note                 TEXT NOT NULL,
    created_at           TEXT NOT NULL,
    FOREIGN KEY (requirement_key, requirement_version)
        REFERENCES readiness_requirement_definitions(key, version)
);

-- --- seed: playbooks ------------------------------------------------------------------------------
INSERT INTO readiness_playbook_definitions
 (id,key,version,label,purpose,kind,default_anchor,allowed_anchors_json,default_scope,
  active_from,governance_note,created_at,updated_at)
VALUES
 ('rpb-launch-1','enterprise-launch',1,'Enterprise launch',
  'The readiness conditions a launching program is expected to close, paced from kickoff.',
  'onboarding','kickoff','["kickoff","launch","contract_start"]','program',
  '2026-08-05','Seeded Slice 3. Offsets are versioned planning defaults, not benchmarks.',
  datetime('now'),datetime('now')),

 -- v2 exists from the start so an upgrade preview has a real diff to show: it adds the second
 -- relationship thread, pulls the executive touch forward, and drops the layer spread to optional.
 ('rpb-launch-2','enterprise-launch',2,'Enterprise launch',
  'The readiness conditions a launching program is expected to close, paced from kickoff.',
  'onboarding','kickoff','["kickoff","launch","contract_start"]','program',
  '2026-08-05','Seeded Slice 3. Revises v1 timing and adds champion continuity cover.',
  datetime('now'),datetime('now')),

 ('rpb-renewal-1','renewal-readiness',1,'Renewal readiness',
  'The commercial and value conditions expected to be evidenced before a renewal decision.',
  'renewal','renewal','["renewal","contract_start"]','account',
  '2026-08-05','Seeded Slice 3.',
  datetime('now'),datetime('now')),

 -- The migration playbook. Its entries are the exact requirement keys the checklist map can reach,
 -- so a compatibility instance is always pinned to a reviewed version (§13.5.3).
 ('rpb-compat-1','checklist-compatibility',1,'Checklist compatibility',
  'Carries legacy onboarding checklist items onto pinned requirement definitions during the compatibility period.',
  'compatibility','kickoff','["kickoff"]','program',
  '2026-08-05','Seeded Slice 3. Not for manual instantiation; the compatibility migration owns it.',
  datetime('now'),datetime('now'));

INSERT INTO readiness_playbook_entries
 (id,playbook_key,playbook_version,requirement_key,requirement_version,display_order,necessity,
  offset_days,note,created_at,updated_at)
VALUES
 -- enterprise-launch v1
 ('rpe-l1-a','enterprise-launch',1,'breadth_engaged_contacts',1,10,'required',30,
  'Breadth is expected inside the first month of the launch.',datetime('now'),datetime('now')),
 ('rpe-l1-b','enterprise-launch',1,'breadth_layer_spread',1,20,'required',45,NULL,
  datetime('now'),datetime('now')),
 ('rpe-l1-c','enterprise-launch',1,'champion_primary_validated',1,30,'required',30,NULL,
  datetime('now'),datetime('now')),
 ('rpe-l1-d','enterprise-launch',1,'exec_identified',1,40,'required',14,NULL,
  datetime('now'),datetime('now')),
 ('rpe-l1-e','enterprise-launch',1,'exec_engaged',1,50,'required',60,NULL,
  datetime('now'),datetime('now')),
 ('rpe-l1-f','enterprise-launch',1,'value_baseline_locked',1,60,'required',45,
  'A baseline locked before the deployment changes the population it measures.',
  datetime('now'),datetime('now')),
 ('rpe-l1-g','enterprise-launch',1,'budget_authority_evidence',1,70,'optional',NULL,
  'Optional during launch; the renewal playbook requires it.',datetime('now'),datetime('now')),

 -- enterprise-launch v2 — additions, removals, and timing changes against v1.
 ('rpe-l2-a','enterprise-launch',2,'breadth_engaged_contacts',1,10,'required',30,NULL,
  datetime('now'),datetime('now')),
 ('rpe-l2-b','enterprise-launch',2,'breadth_layer_spread',1,20,'optional',45,
  'Dropped to optional in v2: the spread is often unassessable inside the launch window.',
  datetime('now'),datetime('now')),
 ('rpe-l2-c','enterprise-launch',2,'champion_primary_validated',1,30,'required',30,NULL,
  datetime('now'),datetime('now')),
 ('rpe-l2-d','enterprise-launch',2,'champion_second_thread',1,35,'required',60,
  'Added in v2: single-thread launches were the recurring failure.',
  datetime('now'),datetime('now')),
 ('rpe-l2-e','enterprise-launch',2,'exec_identified',1,40,'required',14,NULL,
  datetime('now'),datetime('now')),
 ('rpe-l2-f','enterprise-launch',2,'exec_engaged',1,50,'required',45,
  'Pulled forward from 60 days in v1.',datetime('now'),datetime('now')),
 ('rpe-l2-g','enterprise-launch',2,'value_baseline_locked',1,60,'required',45,NULL,
  datetime('now'),datetime('now')),

 -- renewal-readiness v1
 ('rpe-r1-a','renewal-readiness',1,'budget_authority_evidence',1,10,'required',-120,
  'Evidenced four months before the renewal date.',datetime('now'),datetime('now')),
 ('rpe-r1-b','renewal-readiness',1,'budget_owner_engagement',1,20,'required',-90,NULL,
  datetime('now'),datetime('now')),
 ('rpe-r1-c','renewal-readiness',1,'value_baseline_locked',1,30,'required',-120,NULL,
  datetime('now'),datetime('now')),
 ('rpe-r1-d','renewal-readiness',1,'value_comparison_observation',1,40,'required',-60,
  'The after-measurement has to exist before the decision conversation, not during it.',
  datetime('now'),datetime('now')),
 ('rpe-r1-e','renewal-readiness',1,'exec_engaged',1,50,'required',-60,NULL,
  datetime('now'),datetime('now')),

 -- checklist-compatibility v1 — exactly the requirement keys the map below can reach.
 ('rpe-c1-a','checklist-compatibility',1,'budget_authority_evidence',1,10,'optional',NULL,
  'Carried from the legacy onboarding checklist.',datetime('now'),datetime('now')),
 ('rpe-c1-b','checklist-compatibility',1,'value_baseline_locked',1,20,'optional',NULL,
  'Carried from the legacy onboarding checklist.',datetime('now'),datetime('now'));

-- --- seed: the checklist map ----------------------------------------------------------------------
-- Deliberately small. Every mapping below is a claim that the legacy item and the requirement mean
-- the same condition; the items with no honest counterpart stay unmatched and remain readable as
-- legacy rows (§13.5.6) rather than being forced onto an approximate key.
--
-- Two template keys point at `budget_authority_evidence` on purpose. Both legacy items really do
-- ask for the budget owner, and one scope can only hold one instance of a requirement — so the
-- collision is reported in the `ambiguous` bucket rather than resolved silently.
INSERT INTO readiness_checklist_requirement_map
 (template_key,requirement_key,requirement_version,note,created_at)
VALUES
 ('first_call:Identify the budget owner','budget_authority_evidence',1,
  'Exact key match: the first-call question and the requirement ask for the same named person.',
  datetime('now')),
 ('first_two_weeks:Scorecard and budget owner named','budget_authority_evidence',1,
  'Exact key match; collides with the first-call item, which the report surfaces as ambiguous.',
  datetime('now')),
 ('first_30_days:Baselines captured','value_baseline_locked',1,
  'Exact key match: both mean a baseline measurement recorded before the deployment changes it.',
  datetime('now'));
