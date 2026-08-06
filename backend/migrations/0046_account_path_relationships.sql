-- Migration 0046 — Account Path Slice 5: typed relationships, evidence links, and phase history.
--
-- ACCOUNT-PATH-SPEC.md §15. Slice 3 stored *when* a condition was expected; readiness computes
-- *whether* it is true. This migration stores the third thing neither of them holds: which records
-- an operator has explicitly said are connected. Five rules shape every table here.
--
--   * **A link is an operator-recorded fact, never a derived one.** §15.2: the service may suggest
--     likely links, but text similarity never becomes a durable relationship without acceptance.
--     Every row therefore carries an actor and a timestamp, and there is no "confidence" column —
--     a link either was accepted or does not exist.
--   * **Still no stored state.** There is no `state`, `met`, `freshness`, `coverage`, or
--     `applicability` column in this file either, for the same reason as 0042. A link says two
--     records are related; readiness still decides, live, whether that satisfies anything. The
--     Slice 5 introspection test asserts the absence by name.
--   * **Typed columns, not a polymorphic pair.** An action is a Task or a Commitment, and the two
--     live in different tables, so the obvious `(target_type, target_id)` design would be a pair
--     SQLite cannot enforce a foreign key across — the exact case §15.1 says to avoid. Each link
--     table instead carries one nullable FK column per legal target and a CHECK that exactly one
--     is set. It is wordier and it is actually enforced.
--   * **Archive, never delete.** §15.2: a relationship that influenced a gate or a transition has
--     to stay readable afterwards, so `archived` is the only way a link goes away. The uniqueness
--     indexes are partial on `archived = 0`, so re-linking after an archive is allowed and the
--     history survives.
--   * **A requirement cannot cite its own suggestion as proof.** `origin` on a requirement-action
--     link records where the action came from. An action created *from* a requirement's own
--     suggested-action template is marked `suggested_action`, and the evidence path refuses it for
--     that requirement — otherwise a condition would satisfy itself by having asked for something.
--
-- `program_phase_events` is the one table here that records the *content* of a readiness answer,
-- and it is worth being exact about why that is not a second source of truth: it is an append-only
-- record of what the operator was shown at the moment they advanced or overrode a gate. Nothing
-- reads it as current state — `phase_readiness.py` recomputes live on every call — and the column
-- is named `unmet_at_transition_json` rather than anything resembling a status so a future reader
-- cannot mistake it for one. Triggers make the table genuinely append-only.
--
-- Mock-only data. No seed rows here: every relationship in this file is an operator action.
PRAGMA foreign_keys = ON;

-- --- requirement ↔ action ------------------------------------------------------------------------
-- Connects a plan instance (the scheduled requirement) to a native Task or Commitment.
--
-- `relation` is three values and they are not interchangeable:
--   * `advances`      — doing this moves the condition forward. Being open advances nothing; only
--                       governed closure can, and only where the evaluator allows it (§15.9).
--   * `blocks`        — this record is why the condition cannot be met yet.
--   * `follow_up_for` — this exists *because* of the condition; it is downstream of it, not proof
--                       of it. This is the relation a successor action takes (§15.7).
CREATE TABLE readiness_requirement_action_links (
    id                 TEXT PRIMARY KEY,
    plan_instance_id   TEXT NOT NULL REFERENCES readiness_plan_instances(id),

    -- Denormalised for scope checks and for the partial indexes below. Validated against the plan
    -- instance on every write; a mismatch is a 422, not a repair.
    account_id         TEXT NOT NULL REFERENCES accounts(id),
    program_id         TEXT REFERENCES programs(id),

    task_id            TEXT REFERENCES tasks(id),
    commitment_id      TEXT REFERENCES commitments(id),

    relation           TEXT NOT NULL CHECK (relation IN ('advances','blocks','follow_up_for')),

    -- Where the action came from. `suggested_action` is load-bearing: see the header.
    origin             TEXT NOT NULL DEFAULT 'operator'
                         CHECK (origin IN ('operator','suggested_action','accepted_proposal')),

    -- Optional provenance: the interaction or proposal that produced the link.
    source_type        TEXT CHECK (source_type IN ('interaction','extraction_proposal')),
    source_id          TEXT,

    note               TEXT,
    actor_id           TEXT NOT NULL,
    created_at         TEXT NOT NULL,
    updated_at         TEXT NOT NULL,
    archived           INTEGER NOT NULL DEFAULT 0,
    archived_at        TEXT,
    archived_by        TEXT,
    archived_reason    TEXT,

    CHECK ((task_id IS NOT NULL) + (commitment_id IS NOT NULL) = 1),
    CHECK (source_type IS NULL OR source_id IS NOT NULL),
    CHECK (archived = 0 OR archived_at IS NOT NULL)
);

-- One active identical relationship (§15.2). Two different relations between the same pair are
-- legal — a task can advance one requirement and block another — so `relation` is in the key.
CREATE UNIQUE INDEX idx_req_action_link_live
    ON readiness_requirement_action_links(
        plan_instance_id, ifnull(task_id,''), ifnull(commitment_id,''), relation)
    WHERE archived = 0;
CREATE INDEX idx_req_action_link_instance
    ON readiness_requirement_action_links(plan_instance_id) WHERE archived = 0;
CREATE INDEX idx_req_action_link_task ON readiness_requirement_action_links(task_id);
CREATE INDEX idx_req_action_link_commitment ON readiness_requirement_action_links(commitment_id);

-- --- requirement ↔ evidence ----------------------------------------------------------------------
-- §15.3. An accepted record an operator says supports the condition. This is deliberately a
-- *different table* from the action links above: advancing a condition and proving one are not the
-- same claim, and collapsing them is how an open task ends up counting as completion.
--
-- `evidence_type` is checked against the requirement definition's `allowed_evidence_types_json` in
-- Python on every write, so a definition governs what may be attached to it. Anything outside that
-- list can still be attached with `supporting = 0` as context and can never change derived state
-- (§15.3, last paragraph).
--
-- There is no `state` here and no cached verdict. Retraction, supersession, staleness, and
-- archival all take effect because the read path recomputes — never because someone remembered to
-- update a flag.
CREATE TABLE readiness_requirement_evidence_links (
    id                 TEXT PRIMARY KEY,
    plan_instance_id   TEXT NOT NULL REFERENCES readiness_plan_instances(id),

    account_id         TEXT NOT NULL REFERENCES accounts(id),
    program_id         TEXT REFERENCES programs(id),

    -- The evidence record, by kind. Kept as a checked pair rather than N nullable FK columns
    -- because the allowlist spans nine tables and the write path resolves each one explicitly;
    -- the trade-off is recorded in decisions.md rather than hidden here.
    evidence_type      TEXT NOT NULL
                         CHECK (evidence_type IN (
                             'decision','stakeholder_role','metric_definition','metric_observation',
                             'value_target','value_story','interaction','task','commitment',
                             'document','source_reference','account_field','program_field')),
    evidence_id        TEXT NOT NULL,
    evidence_label     TEXT NOT NULL,

    -- 0 means "attached as context". §15.3: unsupported evidence can be attached but cannot change
    -- derived state, and an operator still wants it on the record.
    supporting         INTEGER NOT NULL DEFAULT 1 CHECK (supporting IN (0,1)),

    -- §15.4's `manual_evidence_review`: a dated reviewer decision where automation cannot
    -- establish sufficiency. Absent on evidence that no evaluator asked a human to judge.
    reviewed_on        TEXT,
    reviewed_by        TEXT,
    review_note        TEXT,

    -- §15.3 retraction. Retracting is not archiving: the row stays visible and explicitly withdrawn.
    retracted_at       TEXT,
    retracted_by       TEXT,
    retracted_reason   TEXT,
    superseded_by_id   TEXT REFERENCES readiness_requirement_evidence_links(id),

    actor_id           TEXT NOT NULL,
    created_at         TEXT NOT NULL,
    updated_at         TEXT NOT NULL,
    archived           INTEGER NOT NULL DEFAULT 0,
    archived_at        TEXT,
    archived_by        TEXT,

    CHECK (retracted_at IS NULL OR retracted_reason IS NOT NULL),
    CHECK (reviewed_on IS NULL OR reviewed_by IS NOT NULL)
);

CREATE UNIQUE INDEX idx_req_evidence_link_live
    ON readiness_requirement_evidence_links(plan_instance_id, evidence_type, evidence_id)
    WHERE archived = 0 AND retracted_at IS NULL;
CREATE INDEX idx_req_evidence_link_instance
    ON readiness_requirement_evidence_links(plan_instance_id) WHERE archived = 0;
CREATE INDEX idx_req_evidence_link_record
    ON readiness_requirement_evidence_links(evidence_type, evidence_id);

-- --- milestone ↔ action --------------------------------------------------------------------------
-- §15.1.3. Same shape and the same reasons as the requirement links; separate table because the
-- left-hand side is a different canonical object with its own completion contract.
CREATE TABLE milestone_action_links (
    id              TEXT PRIMARY KEY,
    milestone_id    TEXT NOT NULL REFERENCES milestones(id),

    account_id      TEXT NOT NULL REFERENCES accounts(id),
    program_id      TEXT NOT NULL REFERENCES programs(id),

    task_id         TEXT REFERENCES tasks(id),
    commitment_id   TEXT REFERENCES commitments(id),

    relation        TEXT NOT NULL CHECK (relation IN ('advances','blocks')),

    note            TEXT,
    actor_id        TEXT NOT NULL,
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL,
    archived        INTEGER NOT NULL DEFAULT 0,
    archived_at     TEXT,
    archived_by     TEXT,
    archived_reason TEXT,

    CHECK ((task_id IS NOT NULL) + (commitment_id IS NOT NULL) = 1),
    CHECK (archived = 0 OR archived_at IS NOT NULL)
);
CREATE UNIQUE INDEX idx_milestone_action_link_live
    ON milestone_action_links(milestone_id, ifnull(task_id,''), ifnull(commitment_id,''), relation)
    WHERE archived = 0;
CREATE INDEX idx_milestone_action_link_milestone
    ON milestone_action_links(milestone_id) WHERE archived = 0;

-- --- gate ↔ requirement ----------------------------------------------------------------------------
-- §15.1.4. Which scheduled requirements a phase gate depends on, and whether each is required to
-- pass it. `necessity` here is the gate's demand — it is not readiness applicability and it is not
-- the plan instance's own `necessity`, which governs only whether an entry could be excluded at
-- instantiation. A gate may require a condition the plan listed as optional; that is the point of
-- having both.
CREATE TABLE gate_requirement_links (
    id               TEXT PRIMARY KEY,
    gate_id          TEXT NOT NULL REFERENCES phase_gates(id),
    plan_instance_id TEXT NOT NULL REFERENCES readiness_plan_instances(id),

    account_id       TEXT NOT NULL REFERENCES accounts(id),
    program_id       TEXT NOT NULL REFERENCES programs(id),

    necessity        TEXT NOT NULL CHECK (necessity IN ('required','optional')),

    note             TEXT,
    actor_id         TEXT NOT NULL,
    created_at       TEXT NOT NULL,
    updated_at       TEXT NOT NULL,
    archived         INTEGER NOT NULL DEFAULT 0,
    archived_at      TEXT,
    archived_by      TEXT,
    archived_reason  TEXT,

    CHECK (archived = 0 OR archived_at IS NOT NULL)
);
CREATE UNIQUE INDEX idx_gate_requirement_link_live
    ON gate_requirement_links(gate_id, plan_instance_id) WHERE archived = 0;
CREATE INDEX idx_gate_requirement_link_gate
    ON gate_requirement_links(gate_id) WHERE archived = 0;

-- --- program phase events ---------------------------------------------------------------------------
-- §15.1.5 and §15.6. Append-only history of every proposed, completed, waived, or rejected phase
-- transition, including the ones that did not move the program.
--
-- `unmet_at_transition_json` and `readiness_stamp` record what the operator was shown when they
-- acted. They are evidence about a *decision*, not about the account: no read path treats them as
-- current, and `phase_readiness.py` recomputes from live records every time it is called. An
-- override that records four unmet requirements does not make them met and does not make them
-- unmet later — it records that four were outstanding and the operator proceeded anyway (§15.6).
CREATE TABLE program_phase_events (
    id                       TEXT PRIMARY KEY,
    program_id               TEXT NOT NULL REFERENCES programs(id),
    account_id               TEXT NOT NULL REFERENCES accounts(id),

    outcome                  TEXT NOT NULL
                               CHECK (outcome IN ('proposed','completed','waived','rejected')),

    from_phase               TEXT NOT NULL
                               CHECK (from_phase IN ('foundation','launch','programmatic',
                                                     'expansion','renewal','closed')),
    to_phase                 TEXT NOT NULL
                               CHECK (to_phase IN ('foundation','launch','programmatic',
                                                   'expansion','renewal','closed')),

    gate_id                  TEXT REFERENCES phase_gates(id),

    -- The readiness answer the operator acted on, so a stale one can be rejected (§15.6).
    readiness_stamp          TEXT NOT NULL,
    readiness_as_of          TEXT NOT NULL,

    -- 1 when the operator proceeded past unmet conditions. An override requires a reason.
    is_override              INTEGER NOT NULL DEFAULT 0 CHECK (is_override IN (0,1)),
    reason                   TEXT,

    -- What was outstanding at the moment of the decision. History, not status. See header.
    unmet_at_transition_json TEXT NOT NULL DEFAULT '[]',

    actor_id                 TEXT NOT NULL,
    created_at               TEXT NOT NULL,

    CHECK (json_valid(unmet_at_transition_json)),
    CHECK (is_override = 0 OR (reason IS NOT NULL AND length(trim(reason)) >= 10)),
    CHECK (outcome <> 'waived' OR (reason IS NOT NULL AND length(trim(reason)) >= 10))
);
CREATE INDEX idx_program_phase_event_program
    ON program_phase_events(program_id, created_at);

-- Append-only for real, not by convention. A history that can be edited is not a history, and this
-- one is read by Plan and by Leadership review provenance (§15.6).
CREATE TRIGGER trg_program_phase_event_no_update
BEFORE UPDATE ON program_phase_events
BEGIN
    SELECT RAISE(ABORT, 'program_phase_events is append-only');
END;

CREATE TRIGGER trg_program_phase_event_no_delete
BEFORE DELETE ON program_phase_events
BEGIN
    SELECT RAISE(ABORT, 'program_phase_events is append-only');
END;
