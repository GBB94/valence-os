-- Migration 0036 — Stage 14 company intelligence foundation.
-- Public artifacts remain mock-only.  Identity, evidence spans, review state, and convergence
-- composition are explicit so downstream attention is reproducible and correction-aware.
PRAGMA foreign_keys = ON;

CREATE TABLE company_entities (
    id TEXT PRIMARY KEY,
    legal_name TEXT NOT NULL,
    entity_type TEXT NOT NULL DEFAULT 'company' CHECK (entity_type IN ('company','subsidiary','division')),
    parent_entity_id TEXT REFERENCES company_entities(id),
    jurisdiction TEXT,
    hq_country TEXT,
    fiscal_year_end_month INTEGER CHECK (fiscal_year_end_month IS NULL OR fiscal_year_end_month BETWEEN 1 AND 12),
    listing_status TEXT NOT NULL DEFAULT 'private' CHECK (listing_status IN ('public','private','subsidiary')),
    aliases_json TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
    archived INTEGER NOT NULL DEFAULT 0, archived_at TEXT, archived_by TEXT
);

CREATE TABLE company_identifiers (
    id TEXT PRIMARY KEY,
    company_entity_id TEXT NOT NULL REFERENCES company_entities(id),
    scheme TEXT NOT NULL CHECK (scheme IN ('domain','cik','lei','ticker','provider')),
    provider TEXT NOT NULL DEFAULT '',
    jurisdiction TEXT NOT NULL DEFAULT '',
    value TEXT NOT NULL,
    valid_from TEXT, valid_to TEXT,
    created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
    archived INTEGER NOT NULL DEFAULT 0, archived_at TEXT, archived_by TEXT
);
CREATE UNIQUE INDEX idx_company_identifier_active
 ON company_identifiers(scheme,provider,jurisdiction,value) WHERE archived=0 AND valid_to IS NULL;

CREATE TABLE account_company_links (
    id TEXT PRIMARY KEY,
    account_id TEXT NOT NULL REFERENCES accounts(id),
    company_entity_id TEXT NOT NULL REFERENCES company_entities(id),
    relationship TEXT NOT NULL CHECK (relationship IN ('primary','parent','subsidiary','division','acquisition_target')),
    valid_from TEXT, valid_to TEXT,
    created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
    archived INTEGER NOT NULL DEFAULT 0, archived_at TEXT, archived_by TEXT
);
CREATE UNIQUE INDEX idx_account_company_primary
 ON account_company_links(account_id) WHERE relationship='primary' AND valid_to IS NULL AND archived=0;
CREATE INDEX idx_account_company_entity ON account_company_links(company_entity_id,account_id);

CREATE TABLE company_watch_profiles (
    id TEXT PRIMARY KEY,
    account_id TEXT NOT NULL UNIQUE REFERENCES accounts(id),
    watch_tier TEXT NOT NULL DEFAULT 'standard' CHECK (watch_tier IN ('standard','elevated','paused')),
    source_include_json TEXT NOT NULL DEFAULT '[]', source_exclude_json TEXT NOT NULL DEFAULT '[]',
    topic_include_json TEXT NOT NULL DEFAULT '[]', topic_exclude_json TEXT NOT NULL DEFAULT '[]',
    languages_json TEXT NOT NULL DEFAULT '["en"]', cadence_days INTEGER NOT NULL DEFAULT 7 CHECK (cadence_days > 0),
    hiring_cluster_min INTEGER NOT NULL DEFAULT 5 CHECK (hiring_cluster_min >= 2),
    hiring_window_days INTEGER NOT NULL DEFAULT 21 CHECK (hiring_window_days > 0),
    convergence_max_gap_days INTEGER NOT NULL DEFAULT 120 CHECK (convergence_max_gap_days > 0),
    created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
    archived INTEGER NOT NULL DEFAULT 0, archived_at TEXT, archived_by TEXT
);

CREATE TABLE company_event_kinds (
    id TEXT PRIMARY KEY, key TEXT NOT NULL UNIQUE, label TEXT NOT NULL,
    direction TEXT NOT NULL CHECK (direction IN ('expansion','contraction','neutral')),
    default_decay_days INTEGER NOT NULL CHECK (default_decay_days > 0),
    decay_source_note TEXT, requires_derivation INTEGER NOT NULL DEFAULT 0 CHECK (requires_derivation IN (0,1)),
    active INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0,1)), display_order INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
    archived INTEGER NOT NULL DEFAULT 0, archived_at TEXT, archived_by TEXT
);

CREATE TABLE intel_sync_runs (
    id TEXT PRIMARY KEY, provider TEXT NOT NULL, mode TEXT NOT NULL DEFAULT 'mock_json' CHECK (mode='mock_json'),
    status TEXT NOT NULL CHECK (status IN ('running','completed','partial','failed')),
    created_count INTEGER NOT NULL DEFAULT 0, skipped_count INTEGER NOT NULL DEFAULT 0,
    unmatched_count INTEGER NOT NULL DEFAULT 0, corrected_count INTEGER NOT NULL DEFAULT 0,
    retracted_count INTEGER NOT NULL DEFAULT 0, error_count INTEGER NOT NULL DEFAULT 0,
    started_at TEXT NOT NULL, completed_at TEXT, detail_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
    archived INTEGER NOT NULL DEFAULT 0, archived_at TEXT, archived_by TEXT
);

CREATE TABLE intel_sync_items (
    id TEXT PRIMARY KEY, run_id TEXT NOT NULL REFERENCES intel_sync_runs(id), fixture TEXT,
    provider TEXT NOT NULL, external_id TEXT, company_entity_id TEXT REFERENCES company_entities(id),
    outcome TEXT NOT NULL CHECK (outcome IN ('created','skipped','unmatched','corrected','retracted','error')),
    detail TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
    archived INTEGER NOT NULL DEFAULT 0, archived_at TEXT, archived_by TEXT
);

CREATE TABLE intel_documents (
    id TEXT PRIMARY KEY, company_entity_id TEXT NOT NULL REFERENCES company_entities(id),
    provider TEXT NOT NULL, external_id TEXT NOT NULL, version INTEGER NOT NULL DEFAULT 1 CHECK (version > 0),
    kind TEXT NOT NULL CHECK (kind IN ('earnings_call','annual_report','press_release','job_posting','news_article','leadership_announcement','regulatory_filing','other_public')),
    language TEXT NOT NULL DEFAULT 'en',
    title TEXT NOT NULL, publisher TEXT NOT NULL, published_on TEXT, retrieved_at TEXT NOT NULL,
    url TEXT NOT NULL, content_hash TEXT NOT NULL,
    source_role TEXT NOT NULL DEFAULT 'original' CHECK (source_role IN ('original','republication','commentary')),
    canonical_source_key TEXT NOT NULL, origin_group TEXT NOT NULL,
    correction_state TEXT NOT NULL DEFAULT 'active' CHECK (correction_state IN ('active','superseded','retracted')),
    superseded_by_id TEXT REFERENCES intel_documents(id), source_reference_id TEXT REFERENCES source_references(id),
    created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
    archived INTEGER NOT NULL DEFAULT 0, archived_at TEXT, archived_by TEXT
);
CREATE UNIQUE INDEX idx_intel_document_provider_version
 ON intel_documents(provider,external_id,version) WHERE archived=0;
CREATE INDEX idx_intel_document_company ON intel_documents(company_entity_id,published_on);

CREATE TABLE intel_document_spans (
    id TEXT PRIMARY KEY, document_id TEXT NOT NULL REFERENCES intel_documents(id), locator TEXT NOT NULL,
    excerpt TEXT NOT NULL, excerpt_hash TEXT NOT NULL, section TEXT, speaker TEXT,
    created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
    archived INTEGER NOT NULL DEFAULT 0, archived_at TEXT, archived_by TEXT
);

CREATE TABLE company_events (
    id TEXT PRIMARY KEY, account_id TEXT NOT NULL REFERENCES accounts(id),
    company_entity_id TEXT NOT NULL REFERENCES company_entities(id), kind_id TEXT NOT NULL REFERENCES company_event_kinds(id),
    status TEXT NOT NULL DEFAULT 'proposed' CHECK (status IN ('proposed','confirmed','dismissed','superseded','retracted','invalidated')),
    summary TEXT NOT NULL, canonical_occurrence_key TEXT NOT NULL,
    occurred_on TEXT, occurred_precision TEXT NOT NULL DEFAULT 'day' CHECK (occurred_precision IN ('day','month','quarter','year','unknown')),
    observed_at TEXT NOT NULL, effective_from TEXT, effective_to TEXT, expires_on TEXT,
    provider TEXT NOT NULL, external_id TEXT NOT NULL, derivation_version TEXT NOT NULL DEFAULT 'fixture-v1',
    org_change_flag_id TEXT REFERENCES org_change_flags(id), confirmed_at TEXT, confirmed_by TEXT,
    dismissal_reason TEXT, invalidation_reason TEXT,
    created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
    archived INTEGER NOT NULL DEFAULT 0, archived_at TEXT, archived_by TEXT
);
CREATE UNIQUE INDEX idx_company_event_provider
 ON company_events(provider,external_id,derivation_version) WHERE archived=0;
CREATE INDEX idx_company_event_feed ON company_events(account_id,status,occurred_on);

CREATE TABLE company_event_evidence (
    id TEXT PRIMARY KEY, event_id TEXT NOT NULL REFERENCES company_events(id),
    span_id TEXT NOT NULL REFERENCES intel_document_spans(id),
    evidence_role TEXT NOT NULL DEFAULT 'original' CHECK (evidence_role IN ('original','corroborating','derived')),
    created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
    archived INTEGER NOT NULL DEFAULT 0, archived_at TEXT, archived_by TEXT,
    UNIQUE(event_id,span_id)
);

CREATE TABLE company_link_keywords (
    id TEXT PRIMARY KEY, account_id TEXT REFERENCES accounts(id),
    phrase TEXT NOT NULL, use_case_id TEXT NOT NULL REFERENCES use_cases(id),
    created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
    archived INTEGER NOT NULL DEFAULT 0, archived_at TEXT, archived_by TEXT
);
CREATE UNIQUE INDEX idx_company_link_keyword_global ON company_link_keywords(lower(phrase),use_case_id)
 WHERE account_id IS NULL AND archived=0;
CREATE UNIQUE INDEX idx_company_link_keyword_account ON company_link_keywords(account_id,lower(phrase),use_case_id)
 WHERE account_id IS NOT NULL AND archived=0;

CREATE TABLE company_event_links (
    id TEXT PRIMARY KEY, event_id TEXT NOT NULL REFERENCES company_events(id),
    account_target_id TEXT REFERENCES accounts(id), segment_id TEXT REFERENCES population_segments(id),
    view_id TEXT REFERENCES population_views(id), use_case_id TEXT REFERENCES use_cases(id),
    cell_id TEXT REFERENCES whitespace_cells(id), person_id TEXT REFERENCES persons(id),
    status TEXT NOT NULL DEFAULT 'proposed' CHECK (status IN ('proposed','confirmed','dismissed')),
    rationale TEXT NOT NULL, suggested_by TEXT NOT NULL DEFAULT 'operator' CHECK (suggested_by IN ('operator','matcher')),
    confirmed_at TEXT, confirmed_by TEXT, dismissal_reason TEXT,
    created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
    archived INTEGER NOT NULL DEFAULT 0, archived_at TEXT, archived_by TEXT,
    CHECK ((account_target_id IS NOT NULL)+(segment_id IS NOT NULL)+(view_id IS NOT NULL)+
           (use_case_id IS NOT NULL)+(cell_id IS NOT NULL)+(person_id IS NOT NULL)=1)
);
CREATE INDEX idx_company_event_links_event ON company_event_links(event_id,status);

CREATE TABLE hiring_postings (
    id TEXT PRIMARY KEY, account_id TEXT NOT NULL REFERENCES accounts(id),
    company_entity_id TEXT NOT NULL REFERENCES company_entities(id), provider TEXT NOT NULL, external_id TEXT NOT NULL,
    normalized_posting_key TEXT NOT NULL, title TEXT NOT NULL, function_label TEXT NOT NULL, region_label TEXT NOT NULL,
    first_seen_on TEXT NOT NULL, last_seen_on TEXT NOT NULL,
    state TEXT NOT NULL DEFAULT 'active' CHECK (state IN ('active','closed','unknown')),
    document_id TEXT NOT NULL REFERENCES intel_documents(id), span_id TEXT REFERENCES intel_document_spans(id),
    created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
    archived INTEGER NOT NULL DEFAULT 0, archived_at TEXT, archived_by TEXT
);
CREATE UNIQUE INDEX idx_hiring_posting_provider ON hiring_postings(provider,external_id) WHERE archived=0;
CREATE INDEX idx_hiring_cluster ON hiring_postings(account_id,function_label,region_label,last_seen_on,state);

CREATE TABLE hiring_observations (
    id TEXT PRIMARY KEY, account_id TEXT NOT NULL REFERENCES accounts(id), function_label TEXT NOT NULL,
    region_label TEXT NOT NULL, postings_count INTEGER NOT NULL CHECK (postings_count >= 0), observed_on TEXT NOT NULL,
    derivation_version TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
    archived INTEGER NOT NULL DEFAULT 0, archived_at TEXT, archived_by TEXT,
    UNIQUE(account_id,function_label,region_label,observed_on,derivation_version)
);

CREATE TABLE company_convergences (
    id TEXT PRIMARY KEY, account_id TEXT NOT NULL REFERENCES accounts(id),
    target_kind TEXT NOT NULL CHECK (target_kind IN ('account','segment','view','use_case')),
    target_id TEXT NOT NULL, condition_key TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('active','closed')),
    rule_version TEXT NOT NULL, explanation TEXT NOT NULL,
    first_evaluated_at TEXT NOT NULL, last_evaluated_at TEXT NOT NULL, closed_at TEXT,
    created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
    archived INTEGER NOT NULL DEFAULT 0, archived_at TEXT, archived_by TEXT
);
CREATE UNIQUE INDEX idx_company_convergence_active ON company_convergences(condition_key)
 WHERE status='active' AND archived=0;

CREATE TABLE company_convergence_events (
    id TEXT PRIMARY KEY, convergence_id TEXT NOT NULL REFERENCES company_convergences(id),
    event_id TEXT NOT NULL REFERENCES company_events(id), origin_group TEXT NOT NULL,
    created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
    archived INTEGER NOT NULL DEFAULT 0, archived_at TEXT, archived_by TEXT,
    UNIQUE(convergence_id,event_id)
);

-- Artifact versions are immutable. Correction state and soft-deletion are the only mutable facts.
CREATE TRIGGER trg_intel_document_immutable BEFORE UPDATE OF
 company_entity_id,provider,external_id,version,kind,title,publisher,published_on,retrieved_at,url,
 content_hash,language,source_role,canonical_source_key,origin_group,source_reference_id ON intel_documents
BEGIN SELECT RAISE(ABORT,'intel document versions are immutable; supersede instead'); END;
CREATE TRIGGER trg_intel_span_immutable_update BEFORE UPDATE ON intel_document_spans
BEGIN SELECT RAISE(ABORT,'intel evidence spans are immutable'); END;
CREATE TRIGGER trg_intel_span_immutable_delete BEFORE DELETE ON intel_document_spans
BEGIN SELECT RAISE(ABORT,'intel evidence spans are immutable'); END;

CREATE TRIGGER trg_company_event_evidence_scope BEFORE INSERT ON company_event_evidence
WHEN NOT EXISTS (
 SELECT 1 FROM company_events e
 JOIN account_company_links acl ON acl.account_id=e.account_id AND acl.company_entity_id=e.company_entity_id
 JOIN intel_document_spans s ON s.id=NEW.span_id
 JOIN intel_documents d ON d.id=s.document_id AND d.company_entity_id=e.company_entity_id
 WHERE e.id=NEW.event_id AND acl.archived=0 AND acl.valid_to IS NULL AND d.archived=0 AND d.correction_state='active'
)
BEGIN SELECT RAISE(ABORT,'company event evidence is outside the linked company or is not live'); END;

CREATE TRIGGER trg_company_event_confirm_evidence BEFORE UPDATE OF status ON company_events
WHEN NEW.status='confirmed' AND (
 NEW.occurred_on IS NULL OR NEW.expires_on IS NULL OR NEW.occurred_on > date('now') OR
 NOT EXISTS (SELECT 1 FROM company_event_evidence ee JOIN intel_document_spans s ON s.id=ee.span_id
   JOIN intel_documents d ON d.id=s.document_id
   WHERE ee.event_id=NEW.id AND ee.archived=0 AND s.archived=0 AND d.archived=0 AND d.correction_state='active')
)
BEGIN SELECT RAISE(ABORT,'confirmed company events require a non-future date, expiry, and live evidence span'); END;

CREATE TRIGGER trg_company_event_link_scope_insert BEFORE INSERT ON company_event_links
WHEN NOT EXISTS (
 SELECT 1 FROM company_events e WHERE e.id=NEW.event_id AND (
   (NEW.account_target_id IS NOT NULL AND NEW.account_target_id=e.account_id) OR
   (NEW.segment_id IS NOT NULL AND EXISTS (SELECT 1 FROM population_segments x WHERE x.id=NEW.segment_id AND x.account_id=e.account_id AND x.archived=0)) OR
   (NEW.view_id IS NOT NULL AND EXISTS (SELECT 1 FROM population_views x WHERE x.id=NEW.view_id AND x.account_id=e.account_id AND x.archived=0)) OR
   (NEW.use_case_id IS NOT NULL AND EXISTS (SELECT 1 FROM use_cases x WHERE x.id=NEW.use_case_id AND (x.account_id IS NULL OR x.account_id=e.account_id) AND x.archived=0)) OR
   (NEW.cell_id IS NOT NULL AND EXISTS (SELECT 1 FROM whitespace_cells x WHERE x.id=NEW.cell_id AND x.account_id=e.account_id AND x.archived=0)) OR
   (NEW.person_id IS NOT NULL AND EXISTS (SELECT 1 FROM persons x WHERE x.id=NEW.person_id AND x.account_id=e.account_id AND x.archived=0))
 ))
BEGIN SELECT RAISE(ABORT,'company event link target is outside the event account'); END;
CREATE TRIGGER trg_company_event_link_scope_update BEFORE UPDATE OF
 event_id,account_target_id,segment_id,view_id,use_case_id,cell_id,person_id ON company_event_links
BEGIN SELECT RAISE(ABORT,'company event link targets are immutable; archive and replace'); END;

-- Losing the final live span invalidates a confirmed event. History remains inspectable.
CREATE TRIGGER trg_intel_document_correction_propagates AFTER UPDATE OF correction_state ON intel_documents
WHEN NEW.correction_state<>'active'
BEGIN
 UPDATE company_events SET status='invalidated', invalidation_reason='last live evidence was corrected or retracted',
   updated_at=datetime('now')
 WHERE status IN ('proposed','confirmed') AND id IN (
   SELECT ee.event_id FROM company_event_evidence ee JOIN intel_document_spans s ON s.id=ee.span_id
   WHERE s.document_id=NEW.id
 ) AND NOT EXISTS (
   SELECT 1 FROM company_event_evidence ee2 JOIN intel_document_spans s2 ON s2.id=ee2.span_id
   JOIN intel_documents d2 ON d2.id=s2.document_id
   WHERE ee2.event_id=company_events.id AND ee2.archived=0 AND s2.archived=0
     AND d2.archived=0 AND d2.correction_state='active'
 );
END;

INSERT INTO company_event_kinds
 (id,key,label,direction,default_decay_days,decay_source_note,requires_derivation,active,display_order,created_at,updated_at)
VALUES
 ('cek-leadership','leadership_change','Leadership change','neutral',120,'Stage 14 governed default',0,1,10,datetime('now'),datetime('now')),
 ('cek-ma','m_and_a','M&A','expansion',540,'Stage 14 governed default',0,1,20,datetime('now'),datetime('now')),
 ('cek-funding','funding_or_investment','Funding or investment','expansion',30,'Stage 14 governed default',0,1,30,datetime('now'),datetime('now')),
 ('cek-strategy','strategic_initiative','Strategic initiative','expansion',90,'Stage 14 governed default',0,1,40,datetime('now'),datetime('now')),
 ('cek-hiring','hiring_cluster','Hiring cluster','expansion',28,'Stage 14 governed default',1,1,50,datetime('now'),datetime('now')),
 ('cek-geo','geo_or_facility_expansion','Geographic or facility expansion','expansion',180,'Stage 14 governed default',0,1,60,datetime('now'),datetime('now')),
 ('cek-restructure','restructuring_or_layoffs','Restructuring or layoffs','contraction',180,'Stage 14 governed default',0,1,70,datetime('now'),datetime('now')),
 ('cek-partner','partnership_or_alliance','Partnership or alliance','neutral',90,'Stage 14 governed default',0,1,80,datetime('now'),datetime('now')),
 ('cek-regulatory','regulatory_or_compliance','Regulatory or compliance','neutral',180,'Stage 14 governed default',0,1,90,datetime('now'),datetime('now'));
