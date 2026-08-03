-- Migration 0035 — Stage 13: adoption comms, sessions, and attendance
--
-- A sequence is a plan over canonical comms entries. Nothing here sends, schedules, opens,
-- clicks, or records named-person product usage. Actual sends are explicit operator facts;
-- attendance is observable deployment engagement with a privacy-safe cohort rollup.

PRAGMA foreign_keys = OFF;
BEGIN;

CREATE TABLE comms_sequences (
    id                  TEXT PRIMARY KEY,
    program_id          TEXT NOT NULL REFERENCES programs(id),
    name                TEXT NOT NULL,
    purpose             TEXT,
    moment_id           TEXT REFERENCES deployment_moments(id),
    cancelled_at        TEXT,
    cancellation_reason TEXT,
    created_at          TEXT NOT NULL,
    updated_at          TEXT NOT NULL,
    archived            INTEGER NOT NULL DEFAULT 0,
    archived_at         TEXT,
    archived_by         TEXT,
    CHECK ((cancelled_at IS NULL AND cancellation_reason IS NULL)
        OR (cancelled_at IS NOT NULL AND cancellation_reason IS NOT NULL))
);
CREATE INDEX idx_comms_sequence_program ON comms_sequences(program_id, created_at);

ALTER TABLE comms_entries ADD COLUMN sequence_id TEXT REFERENCES comms_sequences(id);
ALTER TABLE comms_entries ADD COLUMN wave_number INTEGER;
ALTER TABLE comms_entries ADD COLUMN follows_entry_id TEXT REFERENCES comms_entries(id);
ALTER TABLE comms_entries ADD COLUMN offset_days INTEGER;
ALTER TABLE comms_entries ADD COLUMN segment_id TEXT REFERENCES population_segments(id);
ALTER TABLE comms_entries ADD COLUMN view_id TEXT REFERENCES population_views(id);
ALTER TABLE comms_entries ADD COLUMN sent_at TEXT;

CREATE UNIQUE INDEX idx_comms_wave_number
    ON comms_entries(sequence_id, wave_number)
    WHERE archived=0 AND sequence_id IS NOT NULL AND wave_number IS NOT NULL;
CREATE INDEX idx_comms_sequence ON comms_entries(sequence_id, wave_number, send_date);

CREATE TRIGGER trg_comms_sequence_scope_insert BEFORE INSERT ON comms_sequences
WHEN NEW.moment_id IS NOT NULL AND NOT EXISTS (
    SELECT 1 FROM deployment_moments m
    WHERE m.id=NEW.moment_id AND m.program_id=NEW.program_id AND m.archived=0)
BEGIN SELECT RAISE(ABORT,'comms sequence moment belongs to a different program'); END;
CREATE TRIGGER trg_comms_sequence_scope_update BEFORE UPDATE OF program_id,moment_id ON comms_sequences
WHEN NEW.moment_id IS NOT NULL AND NOT EXISTS (
    SELECT 1 FROM deployment_moments m
    WHERE m.id=NEW.moment_id AND m.program_id=NEW.program_id AND m.archived=0)
BEGIN SELECT RAISE(ABORT,'comms sequence moment belongs to a different program'); END;

CREATE TRIGGER trg_comms_wave_scope_insert BEFORE INSERT ON comms_entries
WHEN (NEW.sequence_id IS NOT NULL AND NOT EXISTS (
        SELECT 1 FROM comms_sequences s
        WHERE s.id=NEW.sequence_id AND s.program_id=NEW.program_id
          AND s.archived=0 AND s.cancelled_at IS NULL))
  OR (NEW.moment_id IS NOT NULL AND NOT EXISTS (
        SELECT 1 FROM deployment_moments m
        WHERE m.id=NEW.moment_id AND m.program_id=NEW.program_id AND m.archived=0))
  OR (NEW.segment_id IS NOT NULL AND NEW.view_id IS NOT NULL)
  OR (NEW.segment_id IS NOT NULL AND NOT EXISTS (
        SELECT 1 FROM programs p JOIN population_segments x ON x.account_id=p.account_id
        WHERE p.id=NEW.program_id AND x.id=NEW.segment_id AND x.archived=0))
  OR (NEW.view_id IS NOT NULL AND NOT EXISTS (
        SELECT 1 FROM programs p JOIN population_views x ON x.account_id=p.account_id
        WHERE p.id=NEW.program_id AND x.id=NEW.view_id AND x.archived=0))
  OR (NEW.sequence_id IS NULL AND
        (NEW.wave_number IS NOT NULL OR NEW.follows_entry_id IS NOT NULL OR NEW.offset_days IS NOT NULL))
  OR (NEW.sequence_id IS NOT NULL AND (NEW.wave_number IS NULL OR NEW.wave_number < 1))
  OR (NEW.follows_entry_id IS NULL AND NEW.offset_days IS NOT NULL)
  OR (NEW.follows_entry_id IS NOT NULL AND (NEW.offset_days IS NULL OR NEW.offset_days < 0))
  OR (NEW.follows_entry_id IS NOT NULL AND NOT EXISTS (
        SELECT 1 FROM comms_entries p
        WHERE p.id=NEW.follows_entry_id AND p.sequence_id=NEW.sequence_id AND p.archived=0))
  OR (NEW.sequence_id IS NOT NULL AND NEW.status='sent' AND NEW.sent_at IS NULL)
  OR (NEW.sequence_id IS NOT NULL AND NEW.status<>'sent' AND NEW.sent_at IS NOT NULL)
BEGIN SELECT RAISE(ABORT,'invalid comms wave scope, order, population, or send state'); END;

CREATE TRIGGER trg_comms_wave_scope_update BEFORE UPDATE OF
 program_id,moment_id,sequence_id,wave_number,follows_entry_id,offset_days,segment_id,view_id,status,sent_at
 ON comms_entries
WHEN (NEW.sequence_id IS NOT NULL AND NOT EXISTS (
        SELECT 1 FROM comms_sequences s
        WHERE s.id=NEW.sequence_id AND s.program_id=NEW.program_id
          AND s.archived=0 AND s.cancelled_at IS NULL))
  OR (NEW.moment_id IS NOT NULL AND NOT EXISTS (
        SELECT 1 FROM deployment_moments m
        WHERE m.id=NEW.moment_id AND m.program_id=NEW.program_id AND m.archived=0))
  OR (NEW.segment_id IS NOT NULL AND NEW.view_id IS NOT NULL)
  OR (NEW.segment_id IS NOT NULL AND NOT EXISTS (
        SELECT 1 FROM programs p JOIN population_segments x ON x.account_id=p.account_id
        WHERE p.id=NEW.program_id AND x.id=NEW.segment_id AND x.archived=0))
  OR (NEW.view_id IS NOT NULL AND NOT EXISTS (
        SELECT 1 FROM programs p JOIN population_views x ON x.account_id=p.account_id
        WHERE p.id=NEW.program_id AND x.id=NEW.view_id AND x.archived=0))
  OR (NEW.sequence_id IS NULL AND
        (NEW.wave_number IS NOT NULL OR NEW.follows_entry_id IS NOT NULL OR NEW.offset_days IS NOT NULL))
  OR (NEW.sequence_id IS NOT NULL AND (NEW.wave_number IS NULL OR NEW.wave_number < 1))
  OR (NEW.follows_entry_id IS NULL AND NEW.offset_days IS NOT NULL)
  OR (NEW.follows_entry_id IS NOT NULL AND (NEW.offset_days IS NULL OR NEW.offset_days < 0))
  OR (NEW.follows_entry_id IS NOT NULL AND NOT EXISTS (
        SELECT 1 FROM comms_entries p
        WHERE p.id=NEW.follows_entry_id AND p.sequence_id=NEW.sequence_id AND p.archived=0))
  OR (NEW.sequence_id IS NOT NULL AND NEW.status='sent' AND NEW.sent_at IS NULL)
  OR (NEW.sequence_id IS NOT NULL AND NEW.status<>'sent' AND NEW.sent_at IS NOT NULL)
BEGIN SELECT RAISE(ABORT,'invalid comms wave scope, order, population, or send state'); END;

CREATE TRIGGER trg_comms_wave_no_cycle_insert BEFORE INSERT ON comms_entries
WHEN NEW.follows_entry_id=NEW.id
BEGIN SELECT RAISE(ABORT,'comms wave predecessor chain cannot cycle'); END;
CREATE TRIGGER trg_comms_wave_no_cycle_update BEFORE UPDATE OF follows_entry_id,sequence_id ON comms_entries
WHEN NEW.follows_entry_id IS NOT NULL AND EXISTS (
    WITH RECURSIVE predecessors(id) AS (
        SELECT NEW.follows_entry_id
        UNION ALL
        SELECT c.follows_entry_id FROM comms_entries c
        JOIN predecessors p ON c.id=p.id
        WHERE c.follows_entry_id IS NOT NULL
    ) SELECT 1 FROM predecessors WHERE id=NEW.id)
BEGIN SELECT RAISE(ABORT,'comms wave predecessor chain cannot cycle'); END;

CREATE TRIGGER trg_comms_sent_immutable BEFORE UPDATE OF
 program_id,moment_id,audience,message,sender,channel,send_date,status,sequence_id,wave_number,
 follows_entry_id,offset_days,segment_id,view_id,sent_at ON comms_entries
WHEN OLD.sequence_id IS NOT NULL AND OLD.status='sent'
BEGIN SELECT RAISE(ABORT,'sent comms waves are immutable; add a correcting wave'); END;

CREATE TRIGGER trg_comms_cancelled_sequence_frozen BEFORE UPDATE OF
 program_id,moment_id,audience,message,sender,channel,send_date,status,sequence_id,wave_number,
 follows_entry_id,offset_days,segment_id,view_id,sent_at ON comms_entries
WHEN OLD.sequence_id IS NOT NULL AND EXISTS (
    SELECT 1 FROM comms_sequences s WHERE s.id=OLD.sequence_id AND s.cancelled_at IS NOT NULL)
BEGIN SELECT RAISE(ABORT,'cancelled comms sequences are immutable'); END;

-- calendar_events.purpose is a governed CHECK. This is its first extension; D-108 says the next
-- extension replaces it with a lookup instead of rebuilding this parent again.
DROP TRIGGER IF EXISTS trg_calendar_program_account_insert;
DROP TRIGGER IF EXISTS trg_calendar_scope_insert;
DROP TRIGGER IF EXISTS trg_calendar_scope_update;
DROP TRIGGER IF EXISTS trg_calendar_attendee_account_insert;
DROP TRIGGER IF EXISTS trg_calendar_attendee_account_update;
DROP INDEX IF EXISTS idx_calendar_external;
DROP INDEX IF EXISTS idx_calendar_account;

CREATE TABLE calendar_events_stage13 (
    id                  TEXT PRIMARY KEY,
    external_id         TEXT,
    account_id          TEXT REFERENCES accounts(id),
    program_id          TEXT REFERENCES programs(id),
    cell_id             TEXT REFERENCES whitespace_cells(id),
    direction           TEXT NOT NULL DEFAULT 'read' CHECK (direction IN ('read','written')),
    purpose             TEXT NOT NULL DEFAULT 'other' CHECK (purpose IN
                        ('kickoff','governance','qbr','deployment_moment','webinar','office_hours','other')),
    title               TEXT NOT NULL,
    starts_at           TEXT NOT NULL,
    ends_at             TEXT,
    location            TEXT,
    organizer_email     TEXT,
    association_confidence REAL,
    source_reference_id TEXT REFERENCES source_references(id),
    comms_sequence_id   TEXT REFERENCES comms_sequences(id),
    invited_by_entry_id TEXT REFERENCES comms_entries(id),
    created_at          TEXT NOT NULL,
    updated_at          TEXT NOT NULL,
    archived            INTEGER NOT NULL DEFAULT 0,
    archived_at         TEXT,
    archived_by         TEXT
);
INSERT INTO calendar_events_stage13
(id,external_id,account_id,program_id,cell_id,direction,purpose,title,starts_at,ends_at,
 location,organizer_email,association_confidence,source_reference_id,
 comms_sequence_id,invited_by_entry_id,created_at,updated_at,archived,archived_at,archived_by)
SELECT id,external_id,account_id,program_id,cell_id,direction,purpose,title,starts_at,ends_at,
       location,organizer_email,association_confidence,source_reference_id,
       NULL,NULL,created_at,updated_at,archived,archived_at,archived_by
FROM calendar_events;
DROP TABLE calendar_events;
ALTER TABLE calendar_events_stage13 RENAME TO calendar_events;
CREATE UNIQUE INDEX idx_calendar_external ON calendar_events(external_id)
    WHERE external_id IS NOT NULL AND archived=0;
CREATE INDEX idx_calendar_account ON calendar_events(account_id, starts_at);
CREATE INDEX idx_calendar_sequence ON calendar_events(comms_sequence_id, starts_at);

ALTER TABLE calendar_event_attendees ADD COLUMN attendance_scope TEXT NOT NULL DEFAULT 'unknown'
    CHECK (attendance_scope IN ('audience','facilitator','observer','unknown'));

CREATE TRIGGER trg_calendar_program_account_insert BEFORE INSERT ON calendar_events
WHEN NEW.program_id IS NOT NULL AND NEW.account_id IS NOT NULL AND NOT EXISTS (
    SELECT 1 FROM programs p WHERE p.id=NEW.program_id AND p.account_id=NEW.account_id)
BEGIN SELECT RAISE(ABORT,'calendar program belongs to a different account'); END;
CREATE TRIGGER trg_calendar_scope_insert BEFORE INSERT ON calendar_events
WHEN (NEW.cell_id IS NOT NULL AND NOT EXISTS (
        SELECT 1 FROM whitespace_cells c WHERE c.id=NEW.cell_id AND c.account_id=NEW.account_id))
  OR (NEW.comms_sequence_id IS NOT NULL AND NOT EXISTS (
        SELECT 1 FROM comms_sequences s JOIN programs p ON p.id=s.program_id
        WHERE s.id=NEW.comms_sequence_id AND s.program_id=NEW.program_id
          AND p.account_id=NEW.account_id AND s.archived=0 AND s.cancelled_at IS NULL))
  OR (NEW.invited_by_entry_id IS NOT NULL AND NOT EXISTS (
        SELECT 1 FROM comms_entries e
        WHERE e.id=NEW.invited_by_entry_id AND e.sequence_id=NEW.comms_sequence_id
          AND e.program_id=NEW.program_id AND e.archived=0))
BEGIN SELECT RAISE(ABORT,'calendar relation belongs to a different account, program, or sequence'); END;
CREATE TRIGGER trg_calendar_scope_update BEFORE UPDATE OF
 account_id,program_id,cell_id,comms_sequence_id,invited_by_entry_id ON calendar_events
WHEN (NEW.program_id IS NOT NULL AND NEW.account_id IS NOT NULL AND NOT EXISTS (
        SELECT 1 FROM programs p WHERE p.id=NEW.program_id AND p.account_id=NEW.account_id))
  OR (NEW.cell_id IS NOT NULL AND NOT EXISTS (
        SELECT 1 FROM whitespace_cells c WHERE c.id=NEW.cell_id AND c.account_id=NEW.account_id))
  OR (NEW.comms_sequence_id IS NOT NULL AND NOT EXISTS (
        SELECT 1 FROM comms_sequences s JOIN programs p ON p.id=s.program_id
        WHERE s.id=NEW.comms_sequence_id AND s.program_id=NEW.program_id
          AND p.account_id=NEW.account_id AND s.archived=0 AND s.cancelled_at IS NULL))
  OR (NEW.invited_by_entry_id IS NOT NULL AND NOT EXISTS (
        SELECT 1 FROM comms_entries e
        WHERE e.id=NEW.invited_by_entry_id AND e.sequence_id=NEW.comms_sequence_id
          AND e.program_id=NEW.program_id AND e.archived=0))
BEGIN SELECT RAISE(ABORT,'calendar relation belongs to a different account, program, or sequence'); END;

CREATE TRIGGER trg_calendar_attendee_account_insert BEFORE INSERT ON calendar_event_attendees
WHEN NEW.person_id IS NOT NULL AND NOT EXISTS (
    SELECT 1 FROM calendar_events e JOIN persons p ON p.id=NEW.person_id
    WHERE e.id=NEW.event_id AND (e.account_id IS NULL OR p.account_id=e.account_id OR p.affiliation='valence'))
BEGIN SELECT RAISE(ABORT,'calendar attendee belongs to a different account'); END;
CREATE TRIGGER trg_calendar_attendee_account_update BEFORE UPDATE OF event_id,person_id ON calendar_event_attendees
WHEN NEW.person_id IS NOT NULL AND NOT EXISTS (
    SELECT 1 FROM calendar_events e JOIN persons p ON p.id=NEW.person_id
    WHERE e.id=NEW.event_id AND (e.account_id IS NULL OR p.account_id=e.account_id OR p.affiliation='valence'))
BEGIN SELECT RAISE(ABORT,'calendar attendee belongs to a different account'); END;

COMMIT;
PRAGMA foreign_keys = ON;
