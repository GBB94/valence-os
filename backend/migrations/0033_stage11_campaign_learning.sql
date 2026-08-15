-- Migration 0033 — Stage 11.2: campaign retrospectives and derived shape snapshots
-- (ADOPTION-CAMPAIGN-SPEC.md §§8-9)
--
-- Two tables, and both exist for reasons that are easy to get wrong:
--
--   * **The retrospective is the only thing that crosses an account boundary.** §13.14 permits a
--     cross-account match to expose the structured retrospective and safe shape metadata, and
--     nothing else — no source records, people, client wording, or observations. That makes these
--     columns a publication surface, not private notes, which is why the service scans the free
--     text for account and person names before accepting it.
--
--   * **The shape is frozen, not derived at read.** A view's audience tags, a segment's
--     membership, and a use case's scope all change over time. Deriving the shape live would
--     silently rewrite what a completed campaign *was* every time someone retagged a population,
--     and the portfolio's "repeated shape" counts would drift with it. Matching a NEW campaign
--     uses live tags; a FINISHED campaign carries the shape it actually ran with.
--
-- Neither table may be archived. §9 requires that negative, no-change, and inconclusive outcomes
-- stay queryable; a soft-delete on a retrospective naming a failed intervention would be the
-- obvious way to quietly clean up the portfolio view.

PRAGMA foreign_keys = ON;

-- --- §8 the completion retrospective ------------------------------------------------------------
CREATE TABLE adoption_campaign_retrospectives (
    id            TEXT PRIMARY KEY,
    campaign_id   TEXT NOT NULL REFERENCES adoption_campaigns(id),

    -- What was actually in the way, as opposed to what was diagnosed up front. The gap between
    -- this and the campaign's primary barrier is the single most useful thing here.
    barrier_actually_present TEXT NOT NULL CHECK (barrier_actually_present IN
        ('capability','opportunity','motivation','mixed','none_found','unknown')),
    barrier_note  TEXT NOT NULL,

    -- §8: what to reuse, what to change, whether something should follow.
    what_to_reuse TEXT NOT NULL,
    what_to_change TEXT NOT NULL,
    follow_on     TEXT NOT NULL DEFAULT 'none' CHECK (follow_on IN
        ('none','repeat_same_cohort','different_cohort','different_intervention','escalate','stop')),
    follow_on_note TEXT,

    -- "Which message and layer were used" (§8). The layer derives from the entry rather than
    -- being retyped here, so it cannot disagree with the library.
    messaging_entry_id TEXT REFERENCES messaging_entries(id),

    -- The derived shape, frozen at write. See the header note on why this is stored.
    shape_json    TEXT NOT NULL,

    reviewed_on   TEXT NOT NULL,
    author        TEXT,
    created_at    TEXT NOT NULL,
    updated_at    TEXT NOT NULL,
    archived      INTEGER NOT NULL DEFAULT 0,
    archived_at   TEXT,
    archived_by   TEXT,

    CHECK (follow_on = 'none' OR follow_on_note IS NOT NULL)
);
CREATE UNIQUE INDEX idx_campaign_retrospective_once
    ON adoption_campaign_retrospectives(campaign_id);

-- --- §8 per-intervention verdicts ---------------------------------------------------------------
-- A row per plan item, not a prose paragraph. "Which intervention appeared to help; which
-- intervention failed or was skipped" is a query in §9 (realization by intervention kind), and a
-- paragraph cannot answer it. Failed and skipped are first-class verdicts precisely because the
-- portfolio is worth nothing if it only remembers what worked.
CREATE TABLE adoption_campaign_retrospective_interventions (
    id               TEXT PRIMARY KEY,
    retrospective_id TEXT NOT NULL REFERENCES adoption_campaign_retrospectives(id),
    plan_link_id     TEXT NOT NULL REFERENCES adoption_campaign_plan_links(id),
    verdict          TEXT NOT NULL CHECK (verdict IN
        ('appeared_to_help','appeared_not_to_help','failed','skipped','unclear')),
    note             TEXT NOT NULL,
    created_at       TEXT NOT NULL,
    updated_at       TEXT NOT NULL,
    archived         INTEGER NOT NULL DEFAULT 0,
    archived_at      TEXT,
    archived_by      TEXT
);
CREATE UNIQUE INDEX idx_retrospective_intervention_once
    ON adoption_campaign_retrospective_interventions(retrospective_id, plan_link_id);
CREATE INDEX idx_retrospective_by_link
    ON adoption_campaign_retrospective_interventions(plan_link_id);

-- --- integrity ----------------------------------------------------------------------------------
-- Only a completed campaign has a completion retrospective. A draft or active campaign writing
-- one would put a "what we learned" record against an outcome that does not exist yet, and §9
-- counts retrospectives against completions.
CREATE TRIGGER trg_retrospective_requires_completion
BEFORE INSERT ON adoption_campaign_retrospectives
FOR EACH ROW WHEN (SELECT status FROM adoption_campaigns WHERE id = NEW.campaign_id) <> 'completed'
BEGIN
    SELECT RAISE(ABORT, 'a retrospective belongs to a completed campaign');
END;

-- The verdict must be about an intervention this campaign actually ran. Without this, a
-- retrospective could credit another campaign's plan item and the §9 rollup by intervention kind
-- would count it twice.
CREATE TRIGGER trg_retrospective_intervention_scope
BEFORE INSERT ON adoption_campaign_retrospective_interventions
FOR EACH ROW WHEN (SELECT l.campaign_id FROM adoption_campaign_plan_links l
                   WHERE l.id = NEW.plan_link_id)
          IS NOT (SELECT r.campaign_id FROM adoption_campaign_retrospectives r
                  WHERE r.id = NEW.retrospective_id)
BEGIN
    SELECT RAISE(ABORT, 'that plan item belongs to a different campaign');
END;

-- The shape is a historical fact about the campaign as it ran. Editing prose is fine; editing the
-- shape would let a finished campaign be re-labelled into a different match tier after the fact.
CREATE TRIGGER trg_retrospective_shape_frozen
BEFORE UPDATE OF shape_json ON adoption_campaign_retrospectives
FOR EACH ROW WHEN NEW.shape_json <> OLD.shape_json
BEGIN
    SELECT RAISE(ABORT, 'the derived shape is frozen at completion');
END;

-- §9: negative, no-change, and inconclusive outcomes cannot be hidden from analytics. Correcting
-- a verdict is an audited update; making the record disappear is not available.
CREATE TRIGGER trg_retrospective_no_archive
BEFORE UPDATE OF archived ON adoption_campaign_retrospectives
FOR EACH ROW WHEN NEW.archived = 1
BEGIN
    SELECT RAISE(ABORT, 'a retrospective cannot be archived; outcomes stay queryable');
END;

CREATE TRIGGER trg_retrospective_intervention_no_archive
BEFORE UPDATE OF archived ON adoption_campaign_retrospective_interventions
FOR EACH ROW WHEN NEW.archived = 1
BEGIN
    SELECT RAISE(ABORT, 'an intervention verdict cannot be archived; failures stay queryable');
END;

CREATE TRIGGER trg_retrospective_no_delete
BEFORE DELETE ON adoption_campaign_retrospectives
BEGIN
    SELECT RAISE(ABORT, 'retrospectives are append-only');
END;

CREATE TRIGGER trg_retrospective_intervention_no_delete
BEFORE DELETE ON adoption_campaign_retrospective_interventions
BEGIN
    SELECT RAISE(ABORT, 'intervention verdicts are append-only');
END;
