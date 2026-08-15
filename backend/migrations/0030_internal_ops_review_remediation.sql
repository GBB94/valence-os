-- Migration 0030 — Stage 10 external-review remediation.
PRAGMA foreign_keys = ON;

-- Forecast renewals are calls on the current commercial truth, not historical copies.
DROP TRIGGER trg_forecast_entry_scope_insert;
DROP TRIGGER trg_forecast_entry_scope_update;
CREATE TRIGGER trg_forecast_entry_scope_insert BEFORE INSERT ON forecast_entries
WHEN (NEW.opportunity_id IS NOT NULL AND NOT EXISTS
        (SELECT 1 FROM expansion_opportunities o WHERE o.id=NEW.opportunity_id AND o.account_id=NEW.account_id))
 OR (NEW.contract_version_id IS NOT NULL AND NOT EXISTS
        (SELECT 1 FROM contract_versions c WHERE c.id=NEW.contract_version_id AND c.account_id=NEW.account_id AND c.is_current=1))
 OR (NEW.renewal_budget_owner_person_id IS NOT NULL AND NOT EXISTS
        (SELECT 1 FROM persons p WHERE p.id=NEW.renewal_budget_owner_person_id AND p.account_id=NEW.account_id))
BEGIN SELECT RAISE(ABORT,'forecast entry target must belong to the account and renewal contracts must be current'); END;
CREATE TRIGGER trg_forecast_entry_scope_update BEFORE UPDATE OF account_id,opportunity_id,contract_version_id,renewal_budget_owner_person_id ON forecast_entries
WHEN (NEW.opportunity_id IS NOT NULL AND NOT EXISTS
        (SELECT 1 FROM expansion_opportunities o WHERE o.id=NEW.opportunity_id AND o.account_id=NEW.account_id))
 OR (NEW.contract_version_id IS NOT NULL AND NOT EXISTS
        (SELECT 1 FROM contract_versions c WHERE c.id=NEW.contract_version_id AND c.account_id=NEW.account_id AND c.is_current=1))
 OR (NEW.renewal_budget_owner_person_id IS NOT NULL AND NOT EXISTS
        (SELECT 1 FROM persons p WHERE p.id=NEW.renewal_budget_owner_person_id AND p.account_id=NEW.account_id))
BEGIN SELECT RAISE(ABORT,'forecast entry target must belong to the account and renewal contracts must be current'); END;

-- The account UI raises high-severity escalations. A same-severity general fallback
-- prevents a high instance from silently snapshotting the medium ladder.
INSERT OR IGNORE INTO escalation_defaults
(id,ask_type,severity,path_type,threshold_business_hours,destination_function_id,destination_role,
 expected_response_hours,next_step,created_at,updated_at)
VALUES
('esc-general-high','general','high','hierarchical',8,'function-other','accountable_leader',4,
 'Escalate to the accountable leader with dated facts and a proposed decision.',datetime('now'),datetime('now'));

-- A reverse no-surprises exclusion is explicit, typed, reasoned, time-boxed, and
-- append-only. The service verifies the one unavoidable derived attention key.
CREATE TABLE report_red_origin_exclusions (
    id TEXT PRIMARY KEY,
    report_kind TEXT NOT NULL CHECK (report_kind IN ('monthly_portfolio_brief')),
    origin_type TEXT NOT NULL CHECK (origin_type IN
        ('risk','issue','status_assessment','escalation','internal_ask','attention_item')),
    risk_id TEXT REFERENCES risks(id),
    issue_id TEXT REFERENCES issues(id),
    status_assessment_id TEXT REFERENCES account_status_assessments(id),
    escalation_id TEXT REFERENCES escalation_instances(id),
    internal_ask_id TEXT REFERENCES internal_asks(id),
    attention_item_key TEXT,
    reason TEXT NOT NULL,
    excluded_by TEXT NOT NULL,
    effective_on TEXT NOT NULL,
    expires_on TEXT NOT NULL,
    created_at TEXT NOT NULL,
    CHECK (expires_on>=effective_on),
    CHECK (
      (origin_type='risk' AND risk_id IS NOT NULL AND issue_id IS NULL AND status_assessment_id IS NULL AND escalation_id IS NULL AND internal_ask_id IS NULL AND attention_item_key IS NULL)
      OR (origin_type='issue' AND risk_id IS NULL AND issue_id IS NOT NULL AND status_assessment_id IS NULL AND escalation_id IS NULL AND internal_ask_id IS NULL AND attention_item_key IS NULL)
      OR (origin_type='status_assessment' AND risk_id IS NULL AND issue_id IS NULL AND status_assessment_id IS NOT NULL AND escalation_id IS NULL AND internal_ask_id IS NULL AND attention_item_key IS NULL)
      OR (origin_type='escalation' AND risk_id IS NULL AND issue_id IS NULL AND status_assessment_id IS NULL AND escalation_id IS NOT NULL AND internal_ask_id IS NULL AND attention_item_key IS NULL)
      OR (origin_type='internal_ask' AND risk_id IS NULL AND issue_id IS NULL AND status_assessment_id IS NULL AND escalation_id IS NULL AND internal_ask_id IS NOT NULL AND attention_item_key IS NULL)
      OR (origin_type='attention_item' AND risk_id IS NULL AND issue_id IS NULL AND status_assessment_id IS NULL AND escalation_id IS NULL AND internal_ask_id IS NULL AND attention_item_key IS NOT NULL)
    )
);
CREATE INDEX idx_report_red_exclusions_active
ON report_red_origin_exclusions(report_kind,effective_on,expires_on,origin_type);
CREATE TRIGGER trg_report_red_exclusion_immutable_update BEFORE UPDATE ON report_red_origin_exclusions
BEGIN SELECT RAISE(ABORT,'report red-origin exclusions are append-only'); END;
CREATE TRIGGER trg_report_red_exclusion_immutable_delete BEFORE DELETE ON report_red_origin_exclusions
BEGIN SELECT RAISE(ABORT,'report red-origin exclusions are append-only'); END;

-- Keep document provenance closed while admitting the new governed origin types.
DROP TRIGGER trg_document_source_type_allowlist;
CREATE TRIGGER trg_document_source_type_allowlist BEFORE INSERT ON generated_document_sources
WHEN NEW.record_type NOT IN (
 'account','account_growth_plan','account_review','attention_state','calendar_event','champion_candidate',
 'commitment','contract_version','decision','escalation','forecast_change_event','forecast_entry',
 'forecast_period','interaction','internal_ask','internal_ask_event','internal_roster',
 'issue','milestone','operational_agreement','operator_view','product_feedback_occurrence',
 'report_origin_exclusion','revenue_event','risk','status_assessment','value_target'
)
BEGIN SELECT RAISE(ABORT,'generated document source type is not allow-listed'); END;
