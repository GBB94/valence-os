-- Migration 0039 — Release 2 account command-center review checkpoints.
-- Explicit review is durable and append-only; browser-local last-visit recency remains a
-- presentation preference and deliberately does not live here.
PRAGMA foreign_keys = ON;

CREATE TABLE account_change_checkpoints (
    id               TEXT PRIMARY KEY,
    account_id       TEXT NOT NULL REFERENCES accounts(id),
    scope_type       TEXT NOT NULL CHECK (scope_type IN ('account','program')),
    program_id       TEXT REFERENCES programs(id),
    reviewed_through TEXT NOT NULL,
    actor_id         TEXT NOT NULL,
    source_type      TEXT NOT NULL CHECK (source_type IN ('command_center','copilot_run')),
    source_id        TEXT,
    created_at       TEXT NOT NULL,
    CHECK ((scope_type='account' AND program_id IS NULL) OR
           (scope_type='program' AND program_id IS NOT NULL)),
    CHECK ((source_type='copilot_run' AND source_id IS NOT NULL) OR
           source_type='command_center')
);
CREATE INDEX idx_change_checkpoint_scope
 ON account_change_checkpoints(account_id,scope_type,program_id,actor_id,reviewed_through);
CREATE UNIQUE INDEX idx_change_checkpoint_idempotent
 ON account_change_checkpoints(
    account_id,scope_type,COALESCE(program_id,''),actor_id,reviewed_through,
    source_type,COALESCE(source_id,''));

CREATE TRIGGER trg_change_checkpoint_program_insert BEFORE INSERT ON account_change_checkpoints
WHEN NEW.program_id IS NOT NULL AND NOT EXISTS (
    SELECT 1 FROM programs p WHERE p.id=NEW.program_id AND p.account_id=NEW.account_id AND p.archived=0)
BEGIN SELECT RAISE(ABORT,'checkpoint program belongs to another account'); END;
CREATE TRIGGER trg_change_checkpoint_immutable_update BEFORE UPDATE ON account_change_checkpoints
BEGIN SELECT RAISE(ABORT,'change checkpoints are append-only'); END;
CREATE TRIGGER trg_change_checkpoint_immutable_delete BEFORE DELETE ON account_change_checkpoints
BEGIN SELECT RAISE(ABORT,'change checkpoints are append-only'); END;

-- Existing reviewed account-scoped change briefs already represent explicit review. Program and
-- portfolio Copilot cursors keep their current semantics until those scopes gain command centers.
INSERT INTO account_change_checkpoints
(id,account_id,scope_type,program_id,reviewed_through,actor_id,source_type,source_id,created_at)
SELECT 'checkpoint-copilot-'||id,account_id,'account',NULL,review_cursor,'p-val-operator',
       'copilot_run',id,reviewed_at
FROM copilot_runs
WHERE scope_type='account' AND intent='changes' AND reviewed_at IS NOT NULL
  AND review_cursor IS NOT NULL AND archived=0;
