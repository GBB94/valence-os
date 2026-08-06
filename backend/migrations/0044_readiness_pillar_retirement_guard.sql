-- 0044 — close the reverse direction of migration 0041's pillar/requirement guard.
--
-- 0041 blocks writing a live requirement definition against a retired pillar version. It does not
-- block the same illegal pair arriving from the other side: retiring or archiving a pillar version
-- that still has live requirements hanging off it. The resulting rows are exactly the state 0041
-- exists to prevent — a condition still evaluatable under a definition the operator has already
-- replaced — and a one-directional guard reads as protection while leaving the easier path open.
--
-- Retiring a pillar is therefore an explicit two-step: retire its requirements, then the pillar.
-- That is the same discipline the readiness spec applies to definition versions generally — a
-- version change is a previewed action, never a side effect of touching one row.

CREATE TRIGGER trg_readiness_pillar_retire_with_live_requirements
BEFORE UPDATE ON readiness_pillar_definitions
WHEN (NEW.retired_at IS NOT NULL OR NEW.archived = 1)
 AND (OLD.retired_at IS NULL AND OLD.archived = 0)
 AND EXISTS (
    SELECT 1 FROM readiness_requirement_definitions r
     WHERE r.pillar_key = OLD.key AND r.pillar_version = OLD.version
       AND r.retired_at IS NULL AND r.archived = 0)
BEGIN
    SELECT RAISE(ABORT, 'cannot retire a pillar version that still has live requirement definitions');
END;
