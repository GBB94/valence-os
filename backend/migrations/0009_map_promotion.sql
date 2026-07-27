-- Migration 0009 — Mutual Action Plan (Section 5N) support
-- A single client-visible / promotion flag on the execution objects that can appear on a
-- joint client-facing plan. Default 0: everything stays internal by inherited safe default
-- (Section 2). The MAP includes ONLY affirmatively-promoted records, enforced in the
-- generator, not by convention — the same visibility-by-construction model the QBR and
-- team update already use. No new object type.

ALTER TABLE commitments ADD COLUMN client_visible INTEGER NOT NULL DEFAULT 0;
ALTER TABLE tasks       ADD COLUMN client_visible INTEGER NOT NULL DEFAULT 0;
ALTER TABLE milestones  ADD COLUMN client_visible INTEGER NOT NULL DEFAULT 0;
