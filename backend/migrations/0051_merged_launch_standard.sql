-- Migration 0051 — one merged launch standard (Zach, 2026-08-05).
--
-- Three separate lists were each claiming to be "the standard work a new account needs":
--
--   * `launch_plan.yaml` seeded 7 milestones at kickoff+0/14/30/45/60/75/90.
--   * `launch_checklist.yaml` seeded 20 `checklist_items` at the same offsets.
--   * `readiness_playbook_entries` scheduled 7 relationship requirements.
--
-- Twelve of the twenty checklist items restated a milestone or a readiness requirement outright,
-- at the same date or a later one. That is why the Plan tab could show a live plan with six
-- overdue conditions and, directly underneath it, a panel reading "Not onboarded yet": two
-- standards disagreeing about the same account in the same viewport.
--
-- The merge keeps each of the three mechanisms doing the one thing it is actually for, and
-- deletes the duplication between them rather than the mechanisms:
--
--   * A **milestone** is a dated deployment event with success criteria. Unchanged.
--   * A **readiness requirement** is a condition of the relationship, evaluated from evidence
--     with no writable state. `enterprise-launch v3` below is the merged set.
--   * A **phase gate item** is operational setup: a thing somebody does, ticked when done.
--
-- The operational steps become gate items rather than requirement definitions because a
-- requirement definition must hang off one of the six readiness pillars, and "trace the IT /
-- legal path" is not a fact about the relationship. Forcing it into a pillar to win a tidier
-- list would corrupt the pillar reading, which is the one thing readiness is for.
--
-- `checklist_items` is NOT dropped and no row is deleted. ACCOUNT-PATH-SPEC.md §13.5 requires a
-- separate deprecation decision once every reader uses the canonical contract; onboarding simply
-- stops creating new ones, and existing rows stay readable through the legacy disclosure the
-- Plan surface already renders.

-- --- gate items gain the four fields a checklist item had that they lacked -------------------
--
-- `complete` and `completed_on` already exist on this table and are what a checklist tick was:
-- an operator-recorded planning fact, not a readiness state. Nothing added here is a state, a
-- freshness, a coverage or an applicability value — a gate item says *when something is
-- expected* and *whether somebody did it*, and readiness independently says whether the
-- relationship condition it might contribute to is true. The Slice 3 schema-introspection rule
-- holds for the same reason it held for the plan tables.

ALTER TABLE phase_gate_items ADD COLUMN template_key    TEXT;
ALTER TABLE phase_gate_items ADD COLUMN detail          TEXT;
-- The account/program field this step's answer should fill (`program.success_criteria`, …), as
-- `checklist_items.fills_field` did for the §1e first-call questions. Nothing is ever inferred from
-- a completion: the operator supplies the value on `PATCH /api/gate-items/{id}` and that patches
-- exactly the one field named here. A tick alone writes nothing but the tick.
ALTER TABLE phase_gate_items ADD COLUMN fills_field     TEXT;
ALTER TABLE phase_gate_items ADD COLUMN due_offset_days INTEGER;
ALTER TABLE phase_gate_items ADD COLUMN due_date        TEXT;

CREATE INDEX idx_gate_items_due ON phase_gate_items(due_date) WHERE complete = 0;
-- Idempotency for the onboarding seed: re-running it cannot double a gate's items.
CREATE UNIQUE INDEX idx_gate_items_template
    ON phase_gate_items(gate_id, template_key) WHERE template_key IS NOT NULL;

-- --- enterprise-launch v3: the merged readiness standard --------------------------------------
--
-- v3 does not retire v2 (§13.9: playbook versions do not retire each other), so every plan
-- already instantiated stays exactly where it is and moving is an explicit previewed upgrade.
--
-- Against v2 this changes one thing: `budget_authority_evidence` returns as a **required** entry
-- at kickoff+30. It was optional-and-undated in v1 and absent from v2, while the checklist
-- carried "Identify the budget owner" at day 0 and "Scorecard and budget owner named" at day 14
-- — the same condition, twice, in the list that could not evaluate it. The requirement can be
-- evaluated from evidence; the checkbox never could.
--
-- `breadth_layer_spread` stays optional, as in v2. Making it required here would be a change of
-- standard smuggled in under a merge.

INSERT INTO readiness_playbook_definitions
    (id, key, version, label, purpose, kind, default_anchor, allowed_anchors_json,
     default_scope, active_from, governance_note, created_at, updated_at)
VALUES (
    'pbk-enterprise-launch-v3', 'enterprise-launch', 3, 'Enterprise launch',
    'The relationship conditions a launch is expected to establish, on dates relative to kickoff. '
    || 'Operational setup lives on the phase gate and deployment events live on milestones; this '
    || 'playbook holds only what readiness can evaluate from evidence.',
    'onboarding', 'kickoff', '["kickoff"]', 'program',
    '2026-08-05',
    'Merged launch standard (Zach, 2026-08-05). Supersedes nothing: v1 and v2 remain instantiable '
    || 'and every existing plan stays on its own version until an operator previews and applies '
    || 'the upgrade.',
    '2026-08-05T00:00:00+00:00', '2026-08-05T00:00:00+00:00'
);

INSERT INTO readiness_playbook_entries
    (id, playbook_key, playbook_version, requirement_key, requirement_version,
     display_order, necessity, offset_days, note, created_at, updated_at)
VALUES
    ('pbe-el3-exec-identified', 'enterprise-launch', 3, 'exec_identified', 1,
     10, 'required', 14, NULL, '2026-08-05T00:00:00+00:00', '2026-08-05T00:00:00+00:00'),
    ('pbe-el3-breadth-contacts', 'enterprise-launch', 3, 'breadth_engaged_contacts', 1,
     20, 'required', 30, NULL, '2026-08-05T00:00:00+00:00', '2026-08-05T00:00:00+00:00'),
    ('pbe-el3-champion-primary', 'enterprise-launch', 3, 'champion_primary_validated', 1,
     30, 'required', 30, NULL, '2026-08-05T00:00:00+00:00', '2026-08-05T00:00:00+00:00'),
    ('pbe-el3-budget-authority', 'enterprise-launch', 3, 'budget_authority_evidence', 1,
     40, 'required', 30,
     'Replaces the two checklist items that asked for the budget owner by hand. Evidence of who '
     || 'controls the funding line is a condition readiness can evaluate; a tick was not.',
     '2026-08-05T00:00:00+00:00', '2026-08-05T00:00:00+00:00'),
    ('pbe-el3-value-baseline', 'enterprise-launch', 3, 'value_baseline_locked', 1,
     50, 'required', 45,
     'Subsumes the checklist''s "Metric definitions agreed" (d14) and "Baselines captured" (d30): '
     || 'the metric_ready evaluator already requires definition, baseline, owner and cadence.',
     '2026-08-05T00:00:00+00:00', '2026-08-05T00:00:00+00:00'),
    ('pbe-el3-exec-engaged', 'enterprise-launch', 3, 'exec_engaged', 1,
     60, 'required', 45, NULL, '2026-08-05T00:00:00+00:00', '2026-08-05T00:00:00+00:00'),
    ('pbe-el3-layer-spread', 'enterprise-launch', 3, 'breadth_layer_spread', 1,
     70, 'optional', 45, NULL, '2026-08-05T00:00:00+00:00', '2026-08-05T00:00:00+00:00'),
    ('pbe-el3-champion-second', 'enterprise-launch', 3, 'champion_second_thread', 1,
     80, 'required', 60, NULL, '2026-08-05T00:00:00+00:00', '2026-08-05T00:00:00+00:00');
