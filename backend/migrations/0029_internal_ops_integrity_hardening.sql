-- Migration 0029 — adversarial integrity hardening for Stage 10.
PRAGMA foreign_keys = ON;

CREATE TRIGGER trg_account_review_scope_insert BEFORE INSERT ON account_reviews
WHEN (NEW.chair_person_id IS NOT NULL AND NOT EXISTS
        (SELECT 1 FROM persons p WHERE p.id=NEW.chair_person_id AND p.affiliation='valence'))
  OR (NEW.source_interaction_id IS NOT NULL AND NOT EXISTS
        (SELECT 1 FROM interactions i WHERE i.id=NEW.source_interaction_id AND i.account_id=NEW.account_id))
BEGIN SELECT RAISE(ABORT,'review chair must be Valence and source interaction must belong to the account'); END;
CREATE TRIGGER trg_account_review_scope_update BEFORE UPDATE OF account_id,chair_person_id,source_interaction_id ON account_reviews
WHEN (NEW.chair_person_id IS NOT NULL AND NOT EXISTS
        (SELECT 1 FROM persons p WHERE p.id=NEW.chair_person_id AND p.affiliation='valence'))
  OR (NEW.source_interaction_id IS NOT NULL AND NOT EXISTS
        (SELECT 1 FROM interactions i WHERE i.id=NEW.source_interaction_id AND i.account_id=NEW.account_id))
BEGIN SELECT RAISE(ABORT,'review chair must be Valence and source interaction must belong to the account'); END;

CREATE TRIGGER trg_status_recovery_owner_valence BEFORE INSERT ON account_status_assessments
WHEN NEW.recovery_owner_person_id IS NOT NULL AND NOT EXISTS
 (SELECT 1 FROM persons p WHERE p.id=NEW.recovery_owner_person_id AND p.affiliation='valence')
BEGIN SELECT RAISE(ABORT,'status recovery owner must be a Valence person'); END;

CREATE TRIGGER trg_roster_valence_update BEFORE UPDATE OF person_id ON account_internal_roster
WHEN NOT EXISTS (SELECT 1 FROM persons p WHERE p.id=NEW.person_id AND p.affiliation='valence')
BEGIN SELECT RAISE(ABORT,'roster members must be Valence people'); END;

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

CREATE TRIGGER trg_feedback_occurrence_scope_update BEFORE UPDATE OF
 account_id,stakeholder_person_id,source_interaction_id,forecast_entry_id,growth_plan_line_id
 ON product_feedback_occurrences
WHEN NOT EXISTS (SELECT 1 FROM persons p WHERE p.id=NEW.stakeholder_person_id AND p.account_id=NEW.account_id)
 OR (NEW.source_interaction_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM interactions i WHERE i.id=NEW.source_interaction_id AND i.account_id=NEW.account_id))
 OR (NEW.forecast_entry_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM forecast_entries f WHERE f.id=NEW.forecast_entry_id AND f.account_id=NEW.account_id))
 OR (NEW.growth_plan_line_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM growth_plan_lines g WHERE g.id=NEW.growth_plan_line_id AND g.account_id=NEW.account_id))
BEGIN SELECT RAISE(ABORT,'feedback occurrence link belongs to a different account'); END;

CREATE TRIGGER trg_feedback_owner_valence_update BEFORE UPDATE OF owner_person_id ON product_feedback_items
WHEN NEW.owner_person_id IS NOT NULL AND NOT EXISTS
 (SELECT 1 FROM persons p WHERE p.id=NEW.owner_person_id AND p.affiliation='valence')
BEGIN SELECT RAISE(ABORT,'feedback owner must be a Valence person'); END;

CREATE TRIGGER trg_feedback_touches_immutable_update BEFORE UPDATE ON product_feedback_touches
BEGIN SELECT RAISE(ABORT,'feedback touches are append-only'); END;
CREATE TRIGGER trg_feedback_touches_immutable_delete BEFORE DELETE ON product_feedback_touches
BEGIN SELECT RAISE(ABORT,'feedback touches are append-only'); END;

CREATE TRIGGER trg_escalation_snapshot_immutable BEFORE UPDATE OF
 ask_id,default_id,severity,path_type,threshold_business_hours,destination_function_id,
 destination_role,expected_response_hours,next_step,opened_at,opened_by ON escalation_instances
BEGIN SELECT RAISE(ABORT,'applied escalation rules are immutable'); END;

CREATE TRIGGER trg_renewal_outcome_scope_update BEFORE UPDATE OF account_id,contract_version_id ON renewal_outcome_events
WHEN NOT EXISTS (SELECT 1 FROM contract_versions c WHERE c.id=NEW.contract_version_id AND c.account_id=NEW.account_id)
BEGIN SELECT RAISE(ABORT,'renewal outcome contract belongs to a different account'); END;

CREATE TRIGGER trg_document_source_type_allowlist BEFORE INSERT ON generated_document_sources
WHEN NEW.record_type NOT IN (
 'account','account_growth_plan','account_review','calendar_event','champion_candidate',
 'commitment','contract_version','decision','forecast_change_event','forecast_entry',
 'forecast_period','interaction','internal_ask','internal_ask_event','internal_roster',
 'issue','milestone','operational_agreement','operator_view','product_feedback_occurrence',
 'revenue_event','risk','status_assessment','value_target'
)
BEGIN SELECT RAISE(ABORT,'generated document source type is not allow-listed'); END;
