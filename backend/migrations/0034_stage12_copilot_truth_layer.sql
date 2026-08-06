-- Migration 0034 — Stage 12: Account Copilot truth layer
-- (ACCOUNT-COPILOT-SPEC.md §§9, 10, 12, 13)
--
-- The copilot is a read-only analyst. These tables persist the bounded question/run contract,
-- the exact record snapshots the answer saw, claim-level support, corrections, and explicit
-- writing rules. They do not create a generic tool, action, memory, or outbound-message surface.

PRAGMA foreign_keys = OFF;
BEGIN;

-- Generated-document kinds had become a CHECK list that required a parent-table rebuild every
-- time a governed artifact was added. A lookup keeps the set explicit while making additions data.
CREATE TABLE document_kinds (
    id               TEXT PRIMARY KEY,
    label            TEXT NOT NULL,
    allowed_audience TEXT NOT NULL CHECK (allowed_audience IN ('internal','client_facing','either')),
    created_at       TEXT NOT NULL
);
INSERT INTO document_kinds(id,label,allowed_audience,created_at) VALUES
 ('pre_call_brief','Pre-call brief','internal',datetime('now')),
 ('business_case','Business case','client_facing',datetime('now')),
 ('champion_kit','Champion kit','client_facing',datetime('now')),
 ('value_review','Value review','client_facing',datetime('now')),
 ('kickoff_deck','Kickoff deck','client_facing',datetime('now')),
 ('team_update','Team update','internal',datetime('now')),
 ('internal_account_brief','Internal account brief','internal',datetime('now')),
 ('internal_review_packet','Internal review packet','internal',datetime('now')),
 ('internal_challenge_sheet','Internal challenge sheet','internal',datetime('now')),
 ('forecast_submission','Forecast submission','internal',datetime('now')),
 ('monthly_portfolio_brief','Monthly portfolio brief','internal',datetime('now')),
 ('colleague_call_brief','Colleague call brief','internal',datetime('now')),
 ('coverage_brief','Coverage brief','internal',datetime('now')),
 ('coverage_return_brief','Coverage return brief','internal',datetime('now')),
 ('copilot_internal_note','Copilot internal note','internal',datetime('now'));

CREATE TABLE writing_style_profiles (
    id               TEXT PRIMARY KEY,
    name             TEXT NOT NULL,
    audience         TEXT NOT NULL CHECK (audience IN ('internal','client_facing')),
    version          INTEGER NOT NULL CHECK (version > 0),
    rules_json       TEXT NOT NULL,
    sample_text      TEXT,
    effective_on     TEXT NOT NULL,
    author           TEXT NOT NULL,
    supersedes_id    TEXT REFERENCES writing_style_profiles(id),
    is_active        INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0,1)),
    created_at       TEXT NOT NULL,
    updated_at       TEXT NOT NULL,
    archived         INTEGER NOT NULL DEFAULT 0,
    archived_at      TEXT,
    archived_by      TEXT,
    UNIQUE(audience,version),
    CHECK (supersedes_id IS NULL OR supersedes_id <> id)
);
CREATE UNIQUE INDEX idx_style_one_active_audience
    ON writing_style_profiles(audience) WHERE is_active=1 AND archived=0;
CREATE TRIGGER trg_style_content_frozen BEFORE UPDATE OF
 name,audience,version,rules_json,sample_text,effective_on,author,supersedes_id
 ON writing_style_profiles
BEGIN SELECT RAISE(ABORT,'writing style versions are immutable; supersede instead'); END;
CREATE TRIGGER trg_style_no_delete BEFORE DELETE ON writing_style_profiles
BEGIN SELECT RAISE(ABORT,'writing style versions cannot be deleted'); END;

-- Rebuild the parent with a kind FK and immutable style-version provenance. Foreign keys are
-- disabled only for this transaction; foreign_key_check is run by migration tests afterward.
DROP TRIGGER IF EXISTS trg_gendoc_program_account_insert;
DROP TRIGGER IF EXISTS trg_gendoc_program_account_update;
DROP TRIGGER IF EXISTS trg_gendoc_person_account_insert;
DROP TRIGGER IF EXISTS trg_internal_ask_scope;
DROP TRIGGER IF EXISTS trg_internal_ask_scope_update;
DROP INDEX IF EXISTS idx_gendoc_account;
DROP INDEX IF EXISTS idx_gendoc_status;
CREATE TABLE generated_documents_stage12 (
    id            TEXT PRIMARY KEY,
    account_id    TEXT REFERENCES accounts(id),
    program_id    TEXT REFERENCES programs(id),
    kind          TEXT NOT NULL REFERENCES document_kinds(id),
    title         TEXT NOT NULL,
    body_markdown TEXT NOT NULL,
    status        TEXT NOT NULL DEFAULT 'draft' CHECK (status IN ('draft','reviewed','sent','discarded')),
    reviewed_on   TEXT,
    reviewed_by   TEXT,
    generated_at            TEXT NOT NULL,
    data_current_through    TEXT,
    missing_or_stale_note   TEXT,
    audience      TEXT NOT NULL DEFAULT 'internal' CHECK (audience IN ('internal','client_facing')),
    audience_profile TEXT NOT NULL DEFAULT 'working' CHECK (audience_profile IN ('working','leadership')),
    source_job_id TEXT,
    source_interaction_id TEXT REFERENCES interactions(id),
    writing_style_profile_id TEXT REFERENCES writing_style_profiles(id),
    created_at    TEXT NOT NULL,
    updated_at    TEXT NOT NULL,
    archived      INTEGER NOT NULL DEFAULT 0,
    archived_at   TEXT,
    archived_by   TEXT,
    CHECK (status IN ('draft','discarded') OR (reviewed_on IS NOT NULL AND reviewed_by IS NOT NULL))
);
INSERT INTO generated_documents_stage12
(id,account_id,program_id,kind,title,body_markdown,status,reviewed_on,reviewed_by,
 generated_at,data_current_through,missing_or_stale_note,audience,audience_profile,
 source_job_id,source_interaction_id,writing_style_profile_id,
 created_at,updated_at,archived,archived_at,archived_by)
SELECT id,account_id,program_id,kind,title,body_markdown,status,reviewed_on,reviewed_by,
       generated_at,data_current_through,missing_or_stale_note,audience,audience_profile,
       source_job_id,source_interaction_id,NULL,
       created_at,updated_at,archived,archived_at,archived_by
FROM generated_documents;
DROP TABLE generated_documents;
ALTER TABLE generated_documents_stage12 RENAME TO generated_documents;
CREATE INDEX idx_gendoc_account ON generated_documents(account_id,kind,generated_at);
CREATE INDEX idx_gendoc_status ON generated_documents(status) WHERE archived=0;
CREATE TRIGGER trg_gendoc_program_account_insert BEFORE INSERT ON generated_documents
WHEN NEW.account_id IS NOT NULL AND NEW.program_id IS NOT NULL AND NOT EXISTS (
    SELECT 1 FROM programs p WHERE p.id=NEW.program_id AND p.account_id=NEW.account_id)
BEGIN SELECT RAISE(ABORT,'document program belongs to a different account'); END;
CREATE TRIGGER trg_gendoc_program_account_update BEFORE UPDATE OF account_id,program_id ON generated_documents
WHEN NEW.account_id IS NOT NULL AND NEW.program_id IS NOT NULL AND NOT EXISTS (
    SELECT 1 FROM programs p WHERE p.id=NEW.program_id AND p.account_id=NEW.account_id)
BEGIN SELECT RAISE(ABORT,'document program belongs to a different account'); END;
CREATE TRIGGER trg_gendoc_kind_audience_insert BEFORE INSERT ON generated_documents
WHEN NOT EXISTS (
    SELECT 1 FROM document_kinds k WHERE k.id=NEW.kind
      AND (k.allowed_audience='either' OR k.allowed_audience=NEW.audience))
BEGIN SELECT RAISE(ABORT,'document kind is not allowed for that audience'); END;
CREATE TRIGGER trg_gendoc_kind_audience_update BEFORE UPDATE OF kind,audience ON generated_documents
WHEN NOT EXISTS (
    SELECT 1 FROM document_kinds k WHERE k.id=NEW.kind
      AND (k.allowed_audience='either' OR k.allowed_audience=NEW.audience))
BEGIN SELECT RAISE(ABORT,'document kind is not allowed for that audience'); END;
CREATE TRIGGER trg_gendoc_person_account_insert BEFORE INSERT ON generated_document_people
WHEN NOT EXISTS (
    SELECT 1 FROM generated_documents gd JOIN persons p ON p.id=NEW.person_id
    WHERE gd.id=NEW.document_id AND gd.account_id=p.account_id)
BEGIN SELECT RAISE(ABORT,'document person belongs to a different account'); END;
CREATE TRIGGER trg_internal_ask_scope BEFORE INSERT ON internal_asks
WHEN NOT EXISTS (SELECT 1 FROM persons p WHERE p.id=NEW.requested_by_person_id AND p.affiliation='valence')
 OR (NEW.requested_from_person_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM persons p WHERE p.id=NEW.requested_from_person_id AND p.affiliation='valence'))
 OR (NEW.current_owner_person_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM persons p WHERE p.id=NEW.current_owner_person_id AND p.affiliation='valence'))
 OR (NEW.opportunity_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM expansion_opportunities o WHERE o.id=NEW.opportunity_id AND o.account_id=NEW.account_id))
 OR (NEW.forecast_entry_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM forecast_entries e WHERE e.id=NEW.forecast_entry_id AND e.account_id=NEW.account_id))
 OR (NEW.account_review_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM account_reviews r WHERE r.id=NEW.account_review_id AND r.account_id=NEW.account_id))
 OR (NEW.generated_document_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM generated_documents d WHERE d.id=NEW.generated_document_id AND d.account_id=NEW.account_id))
 OR (NEW.feedback_occurrence_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM product_feedback_occurrences o WHERE o.id=NEW.feedback_occurrence_id AND o.account_id=NEW.account_id))
 OR (NEW.source_interaction_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM interactions i WHERE i.id=NEW.source_interaction_id AND i.account_id=NEW.account_id))
BEGIN SELECT RAISE(ABORT,'internal ask link is outside its account or Valence roster'); END;
CREATE TRIGGER trg_internal_ask_scope_update BEFORE UPDATE OF
 account_id,requested_by_person_id,requested_from_person_id,current_owner_person_id,
 opportunity_id,forecast_entry_id,account_review_id,generated_document_id,
 feedback_occurrence_id,source_interaction_id ON internal_asks
WHEN NOT EXISTS (SELECT 1 FROM persons p WHERE p.id=NEW.requested_by_person_id AND p.affiliation='valence')
 OR (NEW.requested_from_person_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM persons p WHERE p.id=NEW.requested_from_person_id AND p.affiliation='valence'))
 OR (NEW.current_owner_person_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM persons p WHERE p.id=NEW.current_owner_person_id AND p.affiliation='valence'))
 OR (NEW.opportunity_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM expansion_opportunities o WHERE o.id=NEW.opportunity_id AND o.account_id=NEW.account_id))
 OR (NEW.forecast_entry_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM forecast_entries e WHERE e.id=NEW.forecast_entry_id AND e.account_id=NEW.account_id))
 OR (NEW.account_review_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM account_reviews r WHERE r.id=NEW.account_review_id AND r.account_id=NEW.account_id))
 OR (NEW.generated_document_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM generated_documents d WHERE d.id=NEW.generated_document_id AND d.account_id=NEW.account_id))
 OR (NEW.feedback_occurrence_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM product_feedback_occurrences o WHERE o.id=NEW.feedback_occurrence_id AND o.account_id=NEW.account_id))
 OR (NEW.source_interaction_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM interactions i WHERE i.id=NEW.source_interaction_id AND i.account_id=NEW.account_id))
BEGIN SELECT RAISE(ABORT,'internal ask link is outside its account or Valence roster'); END;

CREATE TABLE copilot_configurations (
    id                TEXT PRIMARY KEY,
    label             TEXT NOT NULL,
    backend           TEXT NOT NULL CHECK (backend='mock'),
    model_version     TEXT NOT NULL,
    prompt_version    TEXT NOT NULL,
    retrieval_version TEXT NOT NULL,
    validator_version TEXT NOT NULL,
    status            TEXT NOT NULL CHECK (status IN ('candidate','passed','active','retired')),
    evaluation_version TEXT,
    evaluation_json   TEXT,
    evaluated_at      TEXT,
    previous_config_id TEXT REFERENCES copilot_configurations(id),
    activated_at      TEXT,
    created_at        TEXT NOT NULL,
    updated_at        TEXT NOT NULL
);
CREATE UNIQUE INDEX idx_copilot_one_active_config
    ON copilot_configurations(status) WHERE status='active';
INSERT INTO copilot_configurations
(id,label,backend,model_version,prompt_version,retrieval_version,validator_version,status,
 evaluation_version,evaluation_json,evaluated_at,activated_at,created_at,updated_at)
VALUES
('copilot-mock-v1','Deterministic mock v1','mock','copilot-mock-v1','copilot-prompt-v1',
 'copilot-retrieval-v1','copilot-validator-v1','active','copilot-golden-v1',
 '{"passed":true,"bootstrap":"validated by repository acceptance suite"}',datetime('now'),datetime('now'),
 datetime('now'),datetime('now'));
CREATE TRIGGER trg_copilot_config_versions_frozen BEFORE UPDATE OF
 backend,model_version,prompt_version,retrieval_version,validator_version
 ON copilot_configurations
BEGIN SELECT RAISE(ABORT,'copilot configuration versions are immutable'); END;
CREATE TRIGGER trg_copilot_config_no_delete BEFORE DELETE ON copilot_configurations
BEGIN SELECT RAISE(ABORT,'copilot configurations cannot be deleted'); END;
CREATE TRIGGER trg_copilot_config_active_insert BEFORE INSERT ON copilot_configurations
WHEN NEW.status='active' AND (
  NEW.evaluation_version IS NULL OR NEW.evaluated_at IS NULL OR
  COALESCE(json_extract(NEW.evaluation_json,'$.passed'),0)<>1)
BEGIN SELECT RAISE(ABORT,'active copilot configuration requires a passing evaluation'); END;
CREATE TRIGGER trg_copilot_config_active_update BEFORE UPDATE OF status ON copilot_configurations
WHEN NEW.status='active' AND (
  NEW.evaluation_version IS NULL OR NEW.evaluated_at IS NULL OR
  COALESCE(json_extract(NEW.evaluation_json,'$.passed'),0)<>1)
BEGIN SELECT RAISE(ABORT,'active copilot configuration requires a passing evaluation'); END;

CREATE TABLE copilot_entity_aliases (
    id          TEXT PRIMARY KEY,
    account_id  TEXT REFERENCES accounts(id),
    record_type TEXT NOT NULL CHECK (record_type IN ('person','program','population_segment','population_view')),
    record_id   TEXT NOT NULL,
    alias       TEXT NOT NULL COLLATE NOCASE,
    created_by  TEXT NOT NULL,
    created_at  TEXT NOT NULL,
    archived    INTEGER NOT NULL DEFAULT 0 CHECK (archived IN (0,1)),
    UNIQUE(account_id,record_type,alias)
);
CREATE INDEX idx_copilot_alias_scope ON copilot_entity_aliases(account_id,alias) WHERE archived=0;
CREATE UNIQUE INDEX idx_copilot_global_alias_unique
    ON copilot_entity_aliases(record_type,alias) WHERE account_id IS NULL AND archived=0;
CREATE TRIGGER trg_copilot_alias_target_insert BEFORE INSERT ON copilot_entity_aliases
WHEN (NEW.record_type='person' AND NOT EXISTS (
        SELECT 1 FROM persons p WHERE p.id=NEW.record_id AND p.account_id IS NEW.account_id AND p.archived=0))
  OR (NEW.record_type='program' AND NOT EXISTS (
        SELECT 1 FROM programs p WHERE p.id=NEW.record_id AND p.account_id IS NEW.account_id AND p.archived=0))
  OR (NEW.record_type='population_segment' AND NOT EXISTS (
        SELECT 1 FROM population_segments p WHERE p.id=NEW.record_id AND p.account_id IS NEW.account_id AND p.archived=0))
  OR (NEW.record_type='population_view' AND NOT EXISTS (
        SELECT 1 FROM population_views p WHERE p.id=NEW.record_id AND p.account_id IS NEW.account_id AND p.archived=0))
BEGIN SELECT RAISE(ABORT,'copilot alias target is missing or outside its account'); END;
CREATE TRIGGER trg_copilot_alias_target_update BEFORE UPDATE OF account_id,record_type,record_id
 ON copilot_entity_aliases
BEGIN SELECT RAISE(ABORT,'copilot alias targets are immutable; archive and replace'); END;

CREATE TABLE copilot_runs (
    id                    TEXT PRIMARY KEY,
    scope_type            TEXT NOT NULL CHECK (scope_type IN ('program','account','portfolio')),
    account_id            TEXT REFERENCES accounts(id),
    program_id            TEXT REFERENCES programs(id),
    query_text            TEXT NOT NULL,
    intent                TEXT NOT NULL CHECK (intent IN ('fact','synthesis','changes','weekly','draft')),
    time_window_start     TEXT,
    time_window_end       TEXT,
    status                TEXT NOT NULL DEFAULT 'queued' CHECK (status IN ('queued','running','completed','abstained','failed')),
    evidence_state        TEXT CHECK (evidence_state IN ('supported','partial','conflicted','insufficient')),
    answer_markdown       TEXT,
    gaps_json             TEXT NOT NULL DEFAULT '[]',
    resolved_entities_json TEXT NOT NULL DEFAULT '[]',
    readers_json          TEXT NOT NULL DEFAULT '[]',
    excluded_json         TEXT NOT NULL DEFAULT '[]',
    failure_class         TEXT,
    failure_detail        TEXT,
    backend               TEXT NOT NULL DEFAULT 'mock',
    model_version         TEXT NOT NULL,
    prompt_version        TEXT NOT NULL,
    retrieval_version     TEXT NOT NULL,
    validator_version     TEXT NOT NULL,
    packet_hash           TEXT,
    packet_bytes          INTEGER,
    input_tokens          INTEGER,
    output_tokens         INTEGER,
    validator_attempts    INTEGER NOT NULL DEFAULT 0,
    retrieval_rounds      INTEGER NOT NULL DEFAULT 0,
    latency_ms            INTEGER,
    cache_hit             INTEGER NOT NULL DEFAULT 0 CHECK (cache_hit IN (0,1)),
    configuration_id      TEXT NOT NULL REFERENCES copilot_configurations(id),
    context_run_id        TEXT REFERENCES copilot_runs(id),
    golden_case_id        TEXT,
    job_id                TEXT,
    retry_of_run_id       TEXT REFERENCES copilot_runs(id),
    idempotency_key       TEXT NOT NULL,
    reviewed_at           TEXT,
    review_cursor         TEXT,
    visibility            TEXT NOT NULL DEFAULT 'internal' CHECK (visibility='internal'),
    generated_at          TEXT,
    created_at            TEXT NOT NULL,
    updated_at            TEXT NOT NULL,
    archived              INTEGER NOT NULL DEFAULT 0,
    archived_at           TEXT,
    archived_by           TEXT,
    CHECK (
      (scope_type='portfolio' AND account_id IS NULL AND program_id IS NULL) OR
      (scope_type='account' AND account_id IS NOT NULL AND program_id IS NULL) OR
      (scope_type='program' AND account_id IS NOT NULL AND program_id IS NOT NULL)
    ),
    CHECK (status<>'completed' OR
      (answer_markdown IS NOT NULL AND evidence_state IS NOT NULL AND generated_at IS NOT NULL)),
    CHECK (status<>'abstained' OR
      (evidence_state='insufficient' AND answer_markdown IS NULL AND failure_detail IS NOT NULL))
);
CREATE UNIQUE INDEX idx_copilot_idempotent_inflight_or_success
    ON copilot_runs(idempotency_key)
    WHERE status IN ('queued','running','completed') AND archived=0;
CREATE INDEX idx_copilot_scope_created ON copilot_runs(scope_type,account_id,program_id,created_at);
CREATE INDEX idx_copilot_status ON copilot_runs(status,created_at) WHERE archived=0;

CREATE TABLE copilot_run_sources (
    id                TEXT PRIMARY KEY,
    run_id            TEXT NOT NULL REFERENCES copilot_runs(id),
    packet_id         TEXT NOT NULL,
    record_type       TEXT NOT NULL,
    record_id         TEXT NOT NULL,
    account_id        TEXT REFERENCES accounts(id),
    program_id        TEXT REFERENCES programs(id),
    record_version    TEXT NOT NULL,
    content_hash      TEXT NOT NULL,
    authority         TEXT NOT NULL,
    freshness_state   TEXT NOT NULL CHECK (freshness_state IN ('current','historical','stale','suppressed','unknown')),
    visibility        TEXT NOT NULL CHECK (visibility IN ('internal','client_eligible')),
    retrieval_method  TEXT NOT NULL,
    retrieval_rank    INTEGER NOT NULL CHECK (retrieval_rank > 0),
    inclusion_reason  TEXT NOT NULL,
    fields_json       TEXT NOT NULL,
    excerpt           TEXT,
    was_archived      INTEGER NOT NULL DEFAULT 0 CHECK (was_archived IN (0,1)),
    created_at        TEXT NOT NULL,
    UNIQUE(run_id,packet_id)
);
CREATE INDEX idx_copilot_sources_run ON copilot_run_sources(run_id,retrieval_rank);
CREATE INDEX idx_copilot_sources_record ON copilot_run_sources(record_type,record_id);

CREATE TABLE copilot_claims (
    id                TEXT PRIMARY KEY,
    run_id            TEXT NOT NULL REFERENCES copilot_runs(id),
    sequence          INTEGER NOT NULL CHECK (sequence > 0),
    kind              TEXT NOT NULL CHECK (kind IN ('fact','calculation','inference','recommendation')),
    claim_text        TEXT NOT NULL,
    support_state     TEXT NOT NULL CHECK (support_state IN ('supported','partial','conflicted','unsupported')),
    validation_result TEXT NOT NULL,
    created_at        TEXT NOT NULL,
    UNIQUE(run_id,sequence)
);

CREATE TABLE copilot_claim_sources (
    id                TEXT PRIMARY KEY,
    claim_id          TEXT NOT NULL REFERENCES copilot_claims(id),
    run_source_id     TEXT NOT NULL REFERENCES copilot_run_sources(id),
    support_note      TEXT NOT NULL,
    created_at        TEXT NOT NULL,
    UNIQUE(claim_id,run_source_id)
);

CREATE TABLE copilot_feedback (
    id                TEXT PRIMARY KEY,
    run_id            TEXT NOT NULL REFERENCES copilot_runs(id),
    claim_id          TEXT REFERENCES copilot_claims(id),
    run_source_id     TEXT REFERENCES copilot_run_sources(id),
    issue_kind        TEXT NOT NULL CHECK (issue_kind IN (
      'helpful','partially_helpful','unhelpful','wrong_fact','missing_source','wrong_source',
      'stale_or_superseded_source','scope_error','unsafe_wording','style_mismatch')),
    note              TEXT,
    actor             TEXT NOT NULL,
    created_at        TEXT NOT NULL
);
CREATE INDEX idx_copilot_feedback_run ON copilot_feedback(run_id,created_at);

CREATE TABLE copilot_feedback_reviews (
    id              TEXT PRIMARY KEY,
    feedback_id     TEXT NOT NULL UNIQUE REFERENCES copilot_feedback(id),
    disposition     TEXT NOT NULL CHECK (disposition IN ('confirmed','dismissed','canonical_record_updated','evaluation_backlog')),
    resolution_note TEXT NOT NULL,
    reviewed_by     TEXT NOT NULL,
    reviewed_at     TEXT NOT NULL
);
CREATE TRIGGER trg_copilot_feedback_review_no_update BEFORE UPDATE ON copilot_feedback_reviews
BEGIN SELECT RAISE(ABORT,'copilot feedback reviews are append-only'); END;
CREATE TRIGGER trg_copilot_feedback_review_no_delete BEFORE DELETE ON copilot_feedback_reviews
BEGIN SELECT RAISE(ABORT,'copilot feedback reviews are append-only'); END;

-- Scope is a database boundary too. A program run cannot be smuggled into another account, and
-- an account-scoped source cannot carry another account into the packet.
CREATE TRIGGER trg_copilot_program_scope_insert BEFORE INSERT ON copilot_runs
WHEN NEW.scope_type='program' AND NOT EXISTS (
  SELECT 1 FROM programs p WHERE p.id=NEW.program_id AND p.account_id=NEW.account_id AND p.archived=0)
BEGIN SELECT RAISE(ABORT,'copilot program belongs to a different account'); END;
CREATE TRIGGER trg_copilot_program_scope_update BEFORE UPDATE OF scope_type,account_id,program_id ON copilot_runs
WHEN NEW.scope_type='program' AND NOT EXISTS (
  SELECT 1 FROM programs p WHERE p.id=NEW.program_id AND p.account_id=NEW.account_id AND p.archived=0)
BEGIN SELECT RAISE(ABORT,'copilot program belongs to a different account'); END;
CREATE TRIGGER trg_copilot_source_scope_insert BEFORE INSERT ON copilot_run_sources
WHEN EXISTS (
  SELECT 1 FROM copilot_runs r WHERE r.id=NEW.run_id AND r.scope_type<>'portfolio'
    AND NEW.account_id IS NOT r.account_id)
BEGIN SELECT RAISE(ABORT,'copilot source is outside the run scope'); END;
CREATE TRIGGER trg_copilot_source_program_scope_insert BEFORE INSERT ON copilot_run_sources
WHEN NEW.program_id IS NOT NULL AND EXISTS (
  SELECT 1 FROM copilot_runs r WHERE r.id=NEW.run_id AND r.scope_type='program'
    AND NEW.program_id IS NOT r.program_id)
BEGIN SELECT RAISE(ABORT,'copilot source is outside the run program scope'); END;
CREATE TRIGGER trg_copilot_claim_source_same_run BEFORE INSERT ON copilot_claim_sources
WHEN (SELECT c.run_id FROM copilot_claims c WHERE c.id=NEW.claim_id)
   IS NOT (SELECT s.run_id FROM copilot_run_sources s WHERE s.id=NEW.run_source_id)
BEGIN SELECT RAISE(ABORT,'copilot claim source belongs to a different run'); END;
CREATE TRIGGER trg_copilot_feedback_same_run BEFORE INSERT ON copilot_feedback
WHEN (NEW.claim_id IS NOT NULL AND
      (SELECT c.run_id FROM copilot_claims c WHERE c.id=NEW.claim_id) IS NOT NEW.run_id)
  OR (NEW.run_source_id IS NOT NULL AND
      (SELECT s.run_id FROM copilot_run_sources s WHERE s.id=NEW.run_source_id) IS NOT NEW.run_id)
BEGIN SELECT RAISE(ABORT,'copilot feedback target belongs to a different run'); END;

CREATE TRIGGER trg_copilot_run_answer_frozen BEFORE UPDATE OF
 scope_type,account_id,program_id,query_text,intent,time_window_start,time_window_end,
 status,evidence_state,answer_markdown,gaps_json,resolved_entities_json,readers_json,excluded_json,
 failure_class,failure_detail,backend,model_version,prompt_version,retrieval_version,
 validator_version,packet_hash,packet_bytes,input_tokens,output_tokens,validator_attempts,
 retrieval_rounds,latency_ms,cache_hit,configuration_id,context_run_id,golden_case_id,
 job_id,retry_of_run_id,idempotency_key,visibility,generated_at
 ON copilot_runs
WHEN OLD.status IN ('completed','abstained')
BEGIN SELECT RAISE(ABORT,'completed copilot runs are immutable'); END;
CREATE TRIGGER trg_copilot_run_no_delete BEFORE DELETE ON copilot_runs
BEGIN SELECT RAISE(ABORT,'copilot runs cannot be deleted; archive instead'); END;

-- Once an answer is complete, its evidence contract is frozen. Archival of the native record is
-- shown dynamically through the detail service; the saved snapshot itself never mutates.
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
CREATE TRIGGER trg_copilot_supported_completion BEFORE UPDATE OF status,evidence_state ON copilot_runs
WHEN NEW.status='completed' AND NEW.evidence_state='supported' AND (
  NOT EXISTS (SELECT 1 FROM copilot_claims c WHERE c.run_id=NEW.id) OR
  EXISTS (
    SELECT 1 FROM copilot_claims c WHERE c.run_id=NEW.id
      AND c.kind IN ('fact','calculation')
      AND (c.support_state<>'supported' OR NOT EXISTS (
        SELECT 1 FROM copilot_claim_sources cs WHERE cs.claim_id=c.id))
  )
)
BEGIN SELECT RAISE(ABORT,'supported copilot answers require supported, cited factual claims'); END;
CREATE TRIGGER trg_copilot_feedback_no_update BEFORE UPDATE ON copilot_feedback
BEGIN SELECT RAISE(ABORT,'copilot feedback is append-only'); END;
CREATE TRIGGER trg_copilot_feedback_no_delete BEFORE DELETE ON copilot_feedback
BEGIN SELECT RAISE(ABORT,'copilot feedback is append-only'); END;

-- A drafted internal note points to the validated run, not a hand-copied generic source list.
-- The run in turn freezes the exact native-record snapshots behind every claim.
DROP TRIGGER IF EXISTS trg_document_source_type_allowlist;
CREATE TRIGGER trg_document_source_type_allowlist BEFORE INSERT ON generated_document_sources
WHEN NEW.record_type NOT IN (
 'account','account_growth_plan','account_review','attention_state','calendar_event','champion_candidate',
 'commitment','contract_version','copilot_run','decision','escalation','forecast_change_event','forecast_entry',
 'forecast_period','interaction','internal_ask','internal_ask_event','internal_roster',
 'issue','milestone','operational_agreement','operator_view','product_feedback_occurrence',
 'report_origin_exclusion','revenue_event','risk','status_assessment','value_target'
)
BEGIN SELECT RAISE(ABORT,'generated document source type is not allow-listed'); END;

COMMIT;
PRAGMA foreign_keys = ON;
