-- Migration 0032 — Stage 11.1: campaign orchestration (ADOPTION-CAMPAIGN-SPEC.md §§4.3, 5.3, 7)
--
-- One nullable column and its scope trigger. §11.1 is explicit that this is deliberately NOT a
-- second association table: `play_runs` already points at its signal episode, so another join
-- table would model the same relationship twice and give two places for it to disagree.
--
-- The dedupe rule lives in the unique index below rather than in service code. A campaign linked
-- to an episode prevents another draft for that episode; a later recurrence may propose a new
-- campaign only after the condition cleared and re-armed, which Stage 7 already tracks through
-- `condition_cleared_at`. Enforcing it here means a raw INSERT cannot route around it.

PRAGMA foreign_keys = ON;

ALTER TABLE signal_episodes ADD COLUMN adoption_campaign_id TEXT REFERENCES adoption_campaigns(id);

-- One campaign per episode. Partial so historical/archived rows do not block a legitimate
-- re-proposal after the condition genuinely recurred.
CREATE UNIQUE INDEX idx_episode_campaign_once ON signal_episodes(id)
    WHERE adoption_campaign_id IS NOT NULL;
CREATE INDEX idx_episode_by_campaign ON signal_episodes(adoption_campaign_id)
    WHERE adoption_campaign_id IS NOT NULL;

CREATE TRIGGER trg_episode_campaign_scope_insert
BEFORE UPDATE OF adoption_campaign_id ON signal_episodes
WHEN NEW.adoption_campaign_id IS NOT NULL AND NOT EXISTS (
    SELECT 1 FROM adoption_campaigns c
    WHERE c.id = NEW.adoption_campaign_id AND c.account_id = NEW.account_id)
BEGIN SELECT RAISE(ABORT, 'signal episode and campaign belong to different accounts'); END;

-- §5.3 — adjusting an intervention appends or supersedes future plan links; it never rewrites the
-- hypothesis or the locked baseline. `superseded_by_link_id` records the replacement so the
-- original intent stays legible: "we tried X, then swapped it for Y" is the learning, and
-- deleting X throws that away.
ALTER TABLE adoption_campaign_plan_links ADD COLUMN superseded_by_link_id TEXT
    REFERENCES adoption_campaign_plan_links(id);
ALTER TABLE adoption_campaign_plan_links ADD COLUMN superseded_on TEXT;
ALTER TABLE adoption_campaign_plan_links ADD COLUMN supersede_reason TEXT;
ALTER TABLE adoption_campaign_plan_links ADD COLUMN adjusted_at_checkpoint_id TEXT
    REFERENCES adoption_campaign_checkpoints(id);

-- A superseded link records why and when, or the supersede is an unexplained edit.
CREATE TRIGGER trg_plan_link_supersede_reason
BEFORE UPDATE OF superseded_by_link_id ON adoption_campaign_plan_links
WHEN NEW.superseded_by_link_id IS NOT NULL
 AND (NEW.supersede_reason IS NULL OR NEW.superseded_on IS NULL)
BEGIN SELECT RAISE(ABORT, 'superseding a plan item records a reason and a date'); END;

-- A replacement cannot come from another campaign.
CREATE TRIGGER trg_plan_link_supersede_scope
BEFORE UPDATE OF superseded_by_link_id ON adoption_campaign_plan_links
WHEN NEW.superseded_by_link_id IS NOT NULL AND NOT EXISTS (
    SELECT 1 FROM adoption_campaign_plan_links l
    WHERE l.id = NEW.superseded_by_link_id AND l.campaign_id = NEW.campaign_id)
BEGIN SELECT RAISE(ABORT, 'a plan item can only be superseded within its own campaign'); END;
