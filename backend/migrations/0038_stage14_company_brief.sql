-- Migration 0038 — admit the fixed, grounded company_brief copilot workflow.
PRAGMA foreign_keys = OFF;
BEGIN;

DROP TRIGGER IF EXISTS trg_copilot_program_scope_insert;
DROP TRIGGER IF EXISTS trg_copilot_program_scope_update;
DROP TRIGGER IF EXISTS trg_copilot_run_answer_frozen;
DROP TRIGGER IF EXISTS trg_copilot_run_no_delete;
DROP TRIGGER IF EXISTS trg_copilot_supported_completion;
DROP TRIGGER IF EXISTS trg_copilot_source_scope_insert;
DROP TRIGGER IF EXISTS trg_copilot_source_program_scope_insert;
DROP TRIGGER IF EXISTS trg_copilot_claim_source_same_run;
DROP TRIGGER IF EXISTS trg_copilot_feedback_same_run;
DROP TRIGGER IF EXISTS trg_copilot_source_frozen_update;
DROP TRIGGER IF EXISTS trg_copilot_source_frozen_delete;
DROP TRIGGER IF EXISTS trg_copilot_claim_frozen_update;
DROP TRIGGER IF EXISTS trg_copilot_claim_frozen_delete;
DROP TRIGGER IF EXISTS trg_copilot_claim_source_frozen_update;
DROP TRIGGER IF EXISTS trg_copilot_claim_source_frozen_delete;
DROP INDEX IF EXISTS idx_copilot_idempotent_inflight_or_success;
DROP INDEX IF EXISTS idx_copilot_scope_created;
DROP INDEX IF EXISTS idx_copilot_status;

CREATE TABLE copilot_runs_stage14 (
    id TEXT PRIMARY KEY,
    scope_type TEXT NOT NULL CHECK (scope_type IN ('program','account','portfolio')),
    account_id TEXT REFERENCES accounts(id), program_id TEXT REFERENCES programs(id),
    query_text TEXT NOT NULL,
    intent TEXT NOT NULL CHECK (intent IN ('fact','synthesis','changes','weekly','draft','company_brief')),
    time_window_start TEXT, time_window_end TEXT,
    status TEXT NOT NULL DEFAULT 'queued' CHECK (status IN ('queued','running','completed','abstained','failed')),
    evidence_state TEXT CHECK (evidence_state IN ('supported','partial','conflicted','insufficient')),
    answer_markdown TEXT, gaps_json TEXT NOT NULL DEFAULT '[]',
    resolved_entities_json TEXT NOT NULL DEFAULT '[]', readers_json TEXT NOT NULL DEFAULT '[]',
    excluded_json TEXT NOT NULL DEFAULT '[]', failure_class TEXT, failure_detail TEXT,
    backend TEXT NOT NULL DEFAULT 'mock', model_version TEXT NOT NULL, prompt_version TEXT NOT NULL,
    retrieval_version TEXT NOT NULL, validator_version TEXT NOT NULL,
    packet_hash TEXT, packet_bytes INTEGER, input_tokens INTEGER, output_tokens INTEGER,
    validator_attempts INTEGER NOT NULL DEFAULT 0, retrieval_rounds INTEGER NOT NULL DEFAULT 0,
    latency_ms INTEGER, cache_hit INTEGER NOT NULL DEFAULT 0 CHECK (cache_hit IN (0,1)),
    configuration_id TEXT NOT NULL REFERENCES copilot_configurations(id),
    context_run_id TEXT REFERENCES copilot_runs_stage14(id), golden_case_id TEXT, job_id TEXT,
    retry_of_run_id TEXT REFERENCES copilot_runs_stage14(id), idempotency_key TEXT NOT NULL,
    reviewed_at TEXT, review_cursor TEXT,
    visibility TEXT NOT NULL DEFAULT 'internal' CHECK (visibility='internal'), generated_at TEXT,
    created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
    archived INTEGER NOT NULL DEFAULT 0, archived_at TEXT, archived_by TEXT,
    CHECK ((scope_type='portfolio' AND account_id IS NULL AND program_id IS NULL) OR
           (scope_type='account' AND account_id IS NOT NULL AND program_id IS NULL) OR
           (scope_type='program' AND account_id IS NOT NULL AND program_id IS NOT NULL)),
    CHECK (status<>'completed' OR (answer_markdown IS NOT NULL AND evidence_state IS NOT NULL AND generated_at IS NOT NULL)),
    CHECK (status<>'abstained' OR (evidence_state='insufficient' AND answer_markdown IS NULL AND failure_detail IS NOT NULL))
);
INSERT INTO copilot_runs_stage14 SELECT * FROM copilot_runs;
DROP TABLE copilot_runs;
ALTER TABLE copilot_runs_stage14 RENAME TO copilot_runs;

CREATE UNIQUE INDEX idx_copilot_idempotent_inflight_or_success ON copilot_runs(idempotency_key)
 WHERE status IN ('queued','running','completed') AND archived=0;
CREATE INDEX idx_copilot_scope_created ON copilot_runs(scope_type,account_id,program_id,created_at);
CREATE INDEX idx_copilot_status ON copilot_runs(status,created_at) WHERE archived=0;

CREATE TRIGGER trg_copilot_program_scope_insert BEFORE INSERT ON copilot_runs
WHEN NEW.scope_type='program' AND NOT EXISTS (
 SELECT 1 FROM programs p WHERE p.id=NEW.program_id AND p.account_id=NEW.account_id AND p.archived=0)
BEGIN SELECT RAISE(ABORT,'copilot program belongs to a different account'); END;
CREATE TRIGGER trg_copilot_program_scope_update BEFORE UPDATE OF scope_type,account_id,program_id ON copilot_runs
WHEN NEW.scope_type='program' AND NOT EXISTS (
 SELECT 1 FROM programs p WHERE p.id=NEW.program_id AND p.account_id=NEW.account_id AND p.archived=0)
BEGIN SELECT RAISE(ABORT,'copilot program belongs to a different account'); END;
CREATE TRIGGER trg_copilot_run_answer_frozen BEFORE UPDATE OF
 scope_type,account_id,program_id,query_text,intent,time_window_start,time_window_end,
 status,evidence_state,answer_markdown,gaps_json,resolved_entities_json,readers_json,excluded_json,
 failure_class,failure_detail,backend,model_version,prompt_version,retrieval_version,
 validator_version,packet_hash,packet_bytes,input_tokens,output_tokens,validator_attempts,
 retrieval_rounds,latency_ms,cache_hit,configuration_id,context_run_id,golden_case_id,
 job_id,retry_of_run_id,idempotency_key,visibility,generated_at ON copilot_runs
WHEN OLD.status IN ('completed','abstained')
BEGIN SELECT RAISE(ABORT,'completed copilot runs are immutable'); END;
CREATE TRIGGER trg_copilot_run_no_delete BEFORE DELETE ON copilot_runs
BEGIN SELECT RAISE(ABORT,'copilot runs cannot be deleted; archive instead'); END;
CREATE TRIGGER trg_copilot_supported_completion BEFORE UPDATE OF status,evidence_state ON copilot_runs
WHEN NEW.status='completed' AND NEW.evidence_state='supported' AND (
 NOT EXISTS (SELECT 1 FROM copilot_claims c WHERE c.run_id=NEW.id) OR
 EXISTS (SELECT 1 FROM copilot_claims c WHERE c.run_id=NEW.id AND c.kind IN ('fact','calculation')
   AND (c.support_state<>'supported' OR NOT EXISTS (
     SELECT 1 FROM copilot_claim_sources cs WHERE cs.claim_id=c.id)))
)
BEGIN SELECT RAISE(ABORT,'supported copilot answers require supported, cited factual claims'); END;

CREATE TRIGGER trg_copilot_source_scope_insert BEFORE INSERT ON copilot_run_sources
WHEN EXISTS (SELECT 1 FROM copilot_runs r WHERE r.id=NEW.run_id AND r.scope_type<>'portfolio'
 AND NEW.account_id IS NOT r.account_id)
BEGIN SELECT RAISE(ABORT,'copilot source is outside the run scope'); END;
CREATE TRIGGER trg_copilot_source_program_scope_insert BEFORE INSERT ON copilot_run_sources
WHEN NEW.program_id IS NOT NULL AND EXISTS (
 SELECT 1 FROM copilot_runs r WHERE r.id=NEW.run_id AND r.scope_type='program' AND NEW.program_id IS NOT r.program_id)
BEGIN SELECT RAISE(ABORT,'copilot source is outside the run program scope'); END;
CREATE TRIGGER trg_copilot_claim_source_same_run BEFORE INSERT ON copilot_claim_sources
WHEN (SELECT c.run_id FROM copilot_claims c WHERE c.id=NEW.claim_id)
 IS NOT (SELECT s.run_id FROM copilot_run_sources s WHERE s.id=NEW.run_source_id)
BEGIN SELECT RAISE(ABORT,'copilot claim source belongs to a different run'); END;
CREATE TRIGGER trg_copilot_feedback_same_run BEFORE INSERT ON copilot_feedback
WHEN (NEW.claim_id IS NOT NULL AND (SELECT c.run_id FROM copilot_claims c WHERE c.id=NEW.claim_id) IS NOT NEW.run_id)
 OR (NEW.run_source_id IS NOT NULL AND (SELECT s.run_id FROM copilot_run_sources s WHERE s.id=NEW.run_source_id) IS NOT NEW.run_id)
BEGIN SELECT RAISE(ABORT,'copilot feedback target belongs to a different run'); END;
CREATE TRIGGER trg_copilot_source_frozen_update BEFORE UPDATE ON copilot_run_sources
WHEN (SELECT status FROM copilot_runs WHERE id=OLD.run_id) IN ('completed','abstained')
BEGIN SELECT RAISE(ABORT,'completed copilot run sources are immutable'); END;
CREATE TRIGGER trg_copilot_source_frozen_delete BEFORE DELETE ON copilot_run_sources
WHEN (SELECT status FROM copilot_runs WHERE id=OLD.run_id) IN ('completed','abstained')
BEGIN SELECT RAISE(ABORT,'completed copilot run sources are immutable'); END;
CREATE TRIGGER trg_copilot_claim_frozen_update BEFORE UPDATE ON copilot_claims
WHEN (SELECT status FROM copilot_runs WHERE id=OLD.run_id) IN ('completed','abstained')
BEGIN SELECT RAISE(ABORT,'completed copilot claims are immutable'); END;
CREATE TRIGGER trg_copilot_claim_frozen_delete BEFORE DELETE ON copilot_claims
WHEN (SELECT status FROM copilot_runs WHERE id=OLD.run_id) IN ('completed','abstained')
BEGIN SELECT RAISE(ABORT,'completed copilot claims are immutable'); END;
CREATE TRIGGER trg_copilot_claim_source_frozen_update BEFORE UPDATE ON copilot_claim_sources
WHEN (SELECT r.status FROM copilot_runs r JOIN copilot_claims c ON c.run_id=r.id WHERE c.id=OLD.claim_id)
 IN ('completed','abstained')
BEGIN SELECT RAISE(ABORT,'completed copilot claim support is immutable'); END;
CREATE TRIGGER trg_copilot_claim_source_frozen_delete BEFORE DELETE ON copilot_claim_sources
WHEN (SELECT r.status FROM copilot_runs r JOIN copilot_claims c ON c.run_id=r.id WHERE c.id=OLD.claim_id)
 IN ('completed','abstained')
BEGIN SELECT RAISE(ABORT,'completed copilot claim support is immutable'); END;

COMMIT;
PRAGMA foreign_keys = ON;
