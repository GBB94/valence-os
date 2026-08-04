-- Migration 0040 — a program-scoped checkpoint must survive its program being archived.
--
-- 0039's trigger required the referenced program to be live (`p.archived=0`).  That predicate
-- belongs on the write path, where it already lives: insert_change_checkpoint resolves the
-- program through repo.get_row, which 404s on an archived row.  In the trigger it also gates
-- *restore*, and portfolio_io.import_account is INSERT-only and replays archived programs
-- verbatim.  The effect was that archiving a program made its account permanently
-- un-restorable — the import aborted with a message ("belongs to another account") that was
-- also untrue, since the program did belong to the account.
--
-- The account-boundary check is the part that must be enforced in SQLite; archival state is a
-- workflow concern, not an integrity one.
PRAGMA foreign_keys = ON;

DROP TRIGGER IF EXISTS trg_change_checkpoint_program_insert;

CREATE TRIGGER trg_change_checkpoint_program_insert BEFORE INSERT ON account_change_checkpoints
WHEN NEW.program_id IS NOT NULL AND NOT EXISTS (
    SELECT 1 FROM programs p WHERE p.id=NEW.program_id AND p.account_id=NEW.account_id)
BEGIN SELECT RAISE(ABORT,'checkpoint program belongs to another account'); END;
