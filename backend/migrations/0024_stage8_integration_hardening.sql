-- Phase 3 Stage 8: the e2e demo exposed that succession_records was the one operational
-- Stage 7 table without the soft-delete columns required by repo.list_rows/repo.archive.
ALTER TABLE succession_records ADD COLUMN archived INTEGER NOT NULL DEFAULT 0;
ALTER TABLE succession_records ADD COLUMN archived_at TEXT;
ALTER TABLE succession_records ADD COLUMN archived_by TEXT;

