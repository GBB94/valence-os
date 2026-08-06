-- Migration 0047 — Account Path Slice 6: shared plans and stamped artifacts.
--
-- ACCOUNT-PATH-SPEC.md §16. Slice 6 adds no new record type and no second copy of anything. What
-- it adds is the smallest amount of storage a client-facing projection genuinely cannot derive:
-- an affirmative promotion flag, the client-safe words an operator chose, and the identity of the
-- template that rendered an artifact. Four rules shape this file.
--
--   * **Promotion is affirmative, per record, and defaults to no.** `client_visible` is 0 for every
--     existing and future plan instance. There is no bulk flag, no "share the whole pillar", and no
--     inherited visibility from the program — §16.1 makes visibility opt-in per record, and a
--     default of 1 anywhere would make the opt-in decorative.
--   * **Still no stored state.** The columns added to `readiness_plan_instances` are
--     `client_visible`, `client_label`, `client_owner_person_id`, `client_promoted_on`, and
--     `client_promoted_by`. None of them is a state, a freshness, a coverage, or an applicability,
--     and the Slice 3 introspection test (which walks every `readiness_plan%` table by name) still
--     passes unchanged. The client-facing *status* a customer sees is derived on every read from
--     live readiness — storing it here is exactly the cache D-139/D-143/D-149 refused three times.
--   * **A client-safe label is required by the database, not by the API.** §16.3 needs a label
--     confirmed safe for external eyes; the canonical requirement label is written for operators
--     and may name an internal condition. A trigger refuses `client_visible = 1` without a non-
--     empty `client_label` and a recorded promoter, so the constraint holds against a hand-typed
--     UPDATE as well as against the endpoint.
--   * **An artifact records the template that made it.** §16.6 requires template/version on every
--     generated artifact. Without it a stored markdown body is unattributable the moment a renderer
--     changes, and "regenerate this and compare" stops being answerable. `source_manifest_json`
--     holds the identities of the records that entered the artifact — not their content, which is
--     already in the body — so a reader can ask what a past artifact was built from after the
--     underlying records have moved on.
--
-- Demotion needs no storage at all: `client_visible` returns to 0, the audit log records the
-- change like any other patch, and a previously generated artifact is a frozen markdown body in
-- `generated_documents` that nothing rewrites. That is the §16.8 immutability criterion, and it is
-- a property of where the body already lives rather than something this migration adds.
--
-- Mock-only data. The one seed row is a document-kind vocabulary entry.
PRAGMA foreign_keys = ON;

-- --- client visibility on a scheduled requirement ------------------------------------------------
ALTER TABLE readiness_plan_instances ADD COLUMN client_visible INTEGER NOT NULL DEFAULT 0;
ALTER TABLE readiness_plan_instances ADD COLUMN client_label TEXT;
ALTER TABLE readiness_plan_instances ADD COLUMN client_owner_person_id TEXT REFERENCES persons(id);
ALTER TABLE readiness_plan_instances ADD COLUMN client_promoted_on TEXT;
ALTER TABLE readiness_plan_instances ADD COLUMN client_promoted_by TEXT;

CREATE INDEX idx_plan_instance_client ON readiness_plan_instances(account_id, client_visible)
    WHERE archived = 0 AND client_visible = 1;

-- SQLite cannot add a CHECK constraint to an existing table, and rebuilding a table that six other
-- migrations reference to gain one would be a far larger change than the rule deserves. Triggers
-- hold the same invariant on both write paths.
CREATE TRIGGER trg_plan_instance_client_label_insert
BEFORE INSERT ON readiness_plan_instances
WHEN NEW.client_visible = 1 AND (
    NEW.client_label IS NULL OR trim(NEW.client_label) = ''
    OR NEW.client_promoted_on IS NULL OR NEW.client_promoted_by IS NULL)
BEGIN
    SELECT RAISE(ABORT, 'a client-visible requirement needs a client-safe label and a recorded promoter');
END;

CREATE TRIGGER trg_plan_instance_client_label_update
BEFORE UPDATE OF client_visible, client_label, client_promoted_on, client_promoted_by
ON readiness_plan_instances
WHEN NEW.client_visible = 1 AND (
    NEW.client_label IS NULL OR trim(NEW.client_label) = ''
    OR NEW.client_promoted_on IS NULL OR NEW.client_promoted_by IS NULL)
BEGIN
    SELECT RAISE(ABORT, 'a client-visible requirement needs a client-safe label and a recorded promoter');
END;

-- The client-facing owner is a named person on either side of the relationship, but it must belong
-- to this account. A promoted requirement naming somebody from a different customer is the same
-- cross-account leak the Release 2 review found in person labels (D-126).
CREATE TRIGGER trg_plan_instance_client_owner_scope
BEFORE UPDATE OF client_owner_person_id ON readiness_plan_instances
WHEN NEW.client_owner_person_id IS NOT NULL AND NOT EXISTS (
    SELECT 1 FROM persons p WHERE p.id = NEW.client_owner_person_id
      AND (p.account_id = NEW.account_id OR p.account_id IS NULL))
BEGIN
    SELECT RAISE(ABORT, 'client owner belongs to a different account');
END;

-- --- artifact provenance --------------------------------------------------------------------------
ALTER TABLE generated_documents ADD COLUMN template_key TEXT;
ALTER TABLE generated_documents ADD COLUMN template_version INTEGER;
ALTER TABLE generated_documents ADD COLUMN source_manifest_json TEXT NOT NULL DEFAULT '[]';

INSERT OR IGNORE INTO document_kinds (id, label, allowed_audience, created_at)
VALUES ('mutual_action_plan', 'Mutual action plan', 'client_facing', datetime('now'));
