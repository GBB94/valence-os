-- Migration 0014 — Phase 3 Stage 3: cadence engine (Comprehensive Spec §3.6)
-- Every stakeholder role gets a target touch cadence, defaulted by power-interest quadrant
-- (and floored for senior roles), overridable per role. The engine compares derived
-- last-meaningful-touch against the target; overdue relationships fire into Today with a
-- content-carrying suggested touch. Only the override is stored; state is derived.

PRAGMA foreign_keys = ON;

ALTER TABLE stakeholder_roles ADD COLUMN cadence_target_days INTEGER;  -- null = use the derived default
