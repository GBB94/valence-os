-- Migration 0037 — Stage 14 bridge into the recurring signal episode system.
PRAGMA foreign_keys = OFF;
BEGIN;

DROP INDEX IF EXISTS idx_signal_account;
DROP INDEX IF EXISTS idx_signal_condition;
DROP INDEX IF EXISTS idx_signal_one_active;

CREATE TABLE signal_episodes_stage14 (
    id TEXT PRIMARY KEY,
    account_id TEXT REFERENCES accounts(id), program_id TEXT REFERENCES programs(id),
    cell_id TEXT REFERENCES whitespace_cells(id), kind TEXT NOT NULL, condition_key TEXT NOT NULL,
    object_type TEXT, object_id TEXT,
    source_kind TEXT NOT NULL CHECK (source_kind IN
      ('attention','relationship','usage','pull','calendar','org_change','headcount','company')),
    source_id TEXT,
    status TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open','held','dismissed','converted','attached','closed')),
    explanation TEXT NOT NULL, context_json TEXT, threshold_value REAL, current_value REAL,
    rearm_value REAL, direction TEXT CHECK (direction IS NULL OR direction IN ('at_least','at_most')),
    freshness_as_of TEXT, held_reason TEXT, dismissal_reason TEXT, cooldown_until TEXT,
    opened_at TEXT NOT NULL, closed_at TEXT, condition_cleared_at TEXT,
    last_evaluated_at TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
    adoption_campaign_id TEXT REFERENCES adoption_campaigns(id)
);
INSERT INTO signal_episodes_stage14 SELECT * FROM signal_episodes;
DROP TABLE signal_episodes;
ALTER TABLE signal_episodes_stage14 RENAME TO signal_episodes;
CREATE INDEX idx_signal_account ON signal_episodes(account_id,status,kind);
CREATE INDEX idx_signal_condition ON signal_episodes(condition_key,opened_at);
CREATE UNIQUE INDEX idx_signal_one_active ON signal_episodes(condition_key) WHERE status IN ('open','held');

-- Dropping the table dropped its dependent objects; recreate the 0022 integrity triggers and the
-- 0032 campaign indexes/trigger verbatim so the rebuild does not silently weaken enforcement.
CREATE UNIQUE INDEX idx_episode_campaign_once ON signal_episodes(id)
    WHERE adoption_campaign_id IS NOT NULL;
CREATE INDEX idx_episode_by_campaign ON signal_episodes(adoption_campaign_id)
    WHERE adoption_campaign_id IS NOT NULL;

CREATE TRIGGER trg_signal_cell_account_insert BEFORE INSERT ON signal_episodes
WHEN (NEW.cell_id IS NOT NULL AND NOT EXISTS (
        SELECT 1 FROM whitespace_cells c WHERE c.id=NEW.cell_id AND c.account_id=NEW.account_id))
  OR (NEW.program_id IS NOT NULL AND NEW.account_id IS NOT NULL AND NOT EXISTS (
        SELECT 1 FROM programs p WHERE p.id=NEW.program_id AND p.account_id=NEW.account_id))
BEGIN SELECT RAISE(ABORT, 'signal cell belongs to a different account'); END;

CREATE TRIGGER trg_signal_scope_update BEFORE UPDATE OF account_id,program_id,cell_id ON signal_episodes
WHEN (NEW.cell_id IS NOT NULL AND NOT EXISTS (
        SELECT 1 FROM whitespace_cells c WHERE c.id=NEW.cell_id AND c.account_id=NEW.account_id))
  OR (NEW.program_id IS NOT NULL AND NEW.account_id IS NOT NULL AND NOT EXISTS (
        SELECT 1 FROM programs p WHERE p.id=NEW.program_id AND p.account_id=NEW.account_id))
BEGIN SELECT RAISE(ABORT, 'signal relation belongs to a different account'); END;

CREATE TRIGGER trg_episode_campaign_scope_insert
BEFORE UPDATE OF adoption_campaign_id ON signal_episodes
WHEN NEW.adoption_campaign_id IS NOT NULL AND NOT EXISTS (
    SELECT 1 FROM adoption_campaigns c
    WHERE c.id = NEW.adoption_campaign_id AND c.account_id = NEW.account_id)
BEGIN SELECT RAISE(ABORT, 'signal episode and campaign belong to different accounts'); END;

CREATE TABLE signal_episode_company_events (
    id TEXT PRIMARY KEY, signal_episode_id TEXT NOT NULL REFERENCES signal_episodes(id),
    convergence_id TEXT NOT NULL REFERENCES company_convergences(id),
    event_id TEXT NOT NULL REFERENCES company_events(id),
    created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
    archived INTEGER NOT NULL DEFAULT 0, archived_at TEXT, archived_by TEXT,
    UNIQUE(signal_episode_id,event_id)
);

COMMIT;
PRAGMA foreign_keys = ON;
