-- Migration 0049 — the shared plan's record kinds join the artifact-source allowlist.
--
-- `trg_document_source_type_allowlist` (0029, re-stated in 0030 and 0034) refuses any
-- `generated_document_sources.record_type` it does not recognise, which is exactly right: an
-- artifact's provenance is only useful if the type vocabulary is closed, and a typo that silently
-- becomes a new type is a manifest nobody can query.
--
-- ACCOUNT-PATH-SPEC.md §16 introduces four kinds that can now enter a client-facing artifact and
-- were therefore missing from a list written before the Account Path existed:
--
--   * `task` — §16.2 allows a promoted Task appropriate for joint execution.
--   * `growth_plan_line` — §16.2 allows a promoted growth line supported by its native contract.
--   * `source_reference` — the cited document behind a shared item. Its *label* is what a customer
--     reads; its identity belongs in the manifest so a later reader can find the citation.
--   * `readiness_plan_instance` — a shared readiness item (§16.3).
--
-- Deliberately still absent: `risk`, `issue`, `extraction_proposal`, and anything readiness derives
-- rather than records. A risk can be a source for an *internal* packet and already is; none of
-- these four additions changes what may be promoted, only what a manifest may name once it has.
PRAGMA foreign_keys = ON;

DROP TRIGGER IF EXISTS trg_document_source_type_allowlist;
CREATE TRIGGER trg_document_source_type_allowlist BEFORE INSERT ON generated_document_sources
WHEN NEW.record_type NOT IN (
 'account','account_growth_plan','account_review','attention_state','calendar_event','champion_candidate',
 'commitment','contract_version','copilot_run','decision','escalation','forecast_change_event','forecast_entry',
 'forecast_period','growth_plan_line','interaction','internal_ask','internal_ask_event','internal_roster',
 'issue','milestone','operational_agreement','operator_view','product_feedback_occurrence',
 'readiness_plan_instance','report_origin_exclusion','revenue_event','risk','source_reference',
 'status_assessment','task','value_target'
)
BEGIN SELECT RAISE(ABORT,'generated document source type is not allow-listed'); END;
