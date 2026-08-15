-- Migration 0022 — Phase 3 Stage 7: recurring signals, calendar, and org change.
--
-- The old plays engine permanently deduped (play, object).  That made a condition which
-- resolved and later recurred impossible to fire twice.  Stage 7 makes the condition episode
-- explicit and dedupes a play against the episode instead.  External data remains mock-only.

PRAGMA foreign_keys = ON;

ALTER TABLE account_settings ADD COLUMN pull_signal_window_days INTEGER NOT NULL DEFAULT 90
    CHECK (pull_signal_window_days > 0);
ALTER TABLE account_settings ADD COLUMN signal_cooldown_days INTEGER NOT NULL DEFAULT 30
    CHECK (signal_cooldown_days >= 0);
ALTER TABLE account_settings ADD COLUMN signal_hysteresis_pct REAL NOT NULL DEFAULT 0.05
    CHECK (signal_hysteresis_pct >= 0 AND signal_hysteresis_pct < 1);
ALTER TABLE account_settings ADD COLUMN priority_response_hours INTEGER NOT NULL DEFAULT 24
    CHECK (priority_response_hours > 0);
ALTER TABLE account_settings ADD COLUMN champion_quiet_days INTEGER NOT NULL DEFAULT 45
    CHECK (champion_quiet_days > 0);
ALTER TABLE account_settings ADD COLUMN business_timezone TEXT NOT NULL DEFAULT 'America/New_York';
ALTER TABLE account_settings ADD COLUMN business_day_start_hour INTEGER NOT NULL DEFAULT 9
    CHECK (business_day_start_hour >= 0 AND business_day_start_hour < 24);
ALTER TABLE account_settings ADD COLUMN business_day_end_hour INTEGER NOT NULL DEFAULT 17
    CHECK (business_day_end_hour > business_day_start_hour AND business_day_end_hour <= 24);

ALTER TABLE pull_signals ADD COLUMN cell_id TEXT REFERENCES whitespace_cells(id);
ALTER TABLE pull_signals ADD COLUMN signal_kind TEXT NOT NULL DEFAULT 'client_pull'
    CHECK (signal_kind IN ('client_pull','champion_ask'));
ALTER TABLE pull_signals ADD COLUMN requested_by_person_id TEXT REFERENCES persons(id);
CREATE INDEX idx_pull_cell ON pull_signals(cell_id, occurred_on, status);

-- One row is one contiguous period during which a condition is true.  `condition_key` is the
-- stable identity of the condition; only one open/held episode may exist for it at a time.
CREATE TABLE signal_episodes (
    id                  TEXT PRIMARY KEY,
    account_id          TEXT REFERENCES accounts(id),
    program_id          TEXT REFERENCES programs(id),
    cell_id             TEXT REFERENCES whitespace_cells(id),
    kind                TEXT NOT NULL,
    condition_key       TEXT NOT NULL,
    object_type         TEXT,
    object_id           TEXT,
    source_kind         TEXT NOT NULL CHECK (source_kind IN
                        ('attention','relationship','usage','pull','calendar','org_change','headcount')),
    source_id           TEXT,
    status              TEXT NOT NULL DEFAULT 'open' CHECK (status IN
                        ('open','held','dismissed','converted','attached','closed')),
    explanation         TEXT NOT NULL,
    context_json        TEXT,
    threshold_value     REAL,
    current_value       REAL,
    rearm_value         REAL,
    direction           TEXT CHECK (direction IS NULL OR direction IN ('at_least','at_most')),
    freshness_as_of     TEXT,
    held_reason         TEXT,
    dismissal_reason    TEXT,
    cooldown_until      TEXT,
    opened_at           TEXT NOT NULL,
    closed_at           TEXT,
    condition_cleared_at TEXT,             -- recurrence is impossible until absence is observed
    last_evaluated_at   TEXT NOT NULL,
    created_at          TEXT NOT NULL,
    updated_at          TEXT NOT NULL
);
CREATE INDEX idx_signal_account ON signal_episodes(account_id, status, kind);
CREATE INDEX idx_signal_condition ON signal_episodes(condition_key, opened_at);
CREATE UNIQUE INDEX idx_signal_one_active ON signal_episodes(condition_key)
    WHERE status IN ('open','held');

-- The mock calendar stores only scheduling and observable attendance facts.  It does not store
-- meeting bodies or infer sentiment.  `direction=written` is an event the app would send to a
-- real calendar after the governance gate is opened; today it remains a local record.
CREATE TABLE calendar_events (
    id                  TEXT PRIMARY KEY,
    external_id         TEXT,
    account_id          TEXT REFERENCES accounts(id),
    program_id          TEXT REFERENCES programs(id),
    cell_id             TEXT REFERENCES whitespace_cells(id),
    direction           TEXT NOT NULL DEFAULT 'read' CHECK (direction IN ('read','written')),
    purpose             TEXT NOT NULL DEFAULT 'other' CHECK (purpose IN
                        ('kickoff','governance','qbr','deployment_moment','other')),
    title               TEXT NOT NULL,
    starts_at           TEXT NOT NULL,
    ends_at             TEXT,
    location            TEXT,
    organizer_email     TEXT,
    association_confidence REAL,
    source_reference_id TEXT REFERENCES source_references(id),
    created_at          TEXT NOT NULL,
    updated_at          TEXT NOT NULL,
    archived            INTEGER NOT NULL DEFAULT 0,
    archived_at         TEXT,
    archived_by         TEXT
);
CREATE UNIQUE INDEX idx_calendar_external ON calendar_events(external_id)
    WHERE external_id IS NOT NULL AND archived=0;
CREATE INDEX idx_calendar_account ON calendar_events(account_id, starts_at);

CREATE TABLE calendar_event_attendees (
    event_id             TEXT NOT NULL REFERENCES calendar_events(id),
    person_id            TEXT REFERENCES persons(id),
    name                 TEXT,
    email                TEXT,
    response_status      TEXT NOT NULL DEFAULT 'unknown' CHECK (response_status IN
                         ('accepted','declined','tentative','needs_action','unknown')),
    attendance_status    TEXT NOT NULL DEFAULT 'unknown' CHECK (attendance_status IN
                         ('invited','attended','no_show','unknown')),
    created_at           TEXT NOT NULL,
    PRIMARY KEY (event_id, email)
);
CREATE INDEX idx_calendar_attendee_person ON calendar_event_attendees(person_id, event_id);

-- Change detection is proposal-first.  Confirmation is the only operation allowed to mutate a
-- person or create succession work; the adapter itself can only add `proposed` rows.
CREATE TABLE org_change_flags (
    id                  TEXT PRIMARY KEY,
    account_id          TEXT NOT NULL REFERENCES accounts(id),
    person_id           TEXT REFERENCES persons(id),
    cell_id             TEXT REFERENCES whitespace_cells(id),
    kind                TEXT NOT NULL CHECK (kind IN
                        ('title_change','departure','arrival','email_bounce','domain_change','restructure')),
    status              TEXT NOT NULL DEFAULT 'proposed' CHECK (status IN
                        ('proposed','confirmed','dismissed')),
    summary             TEXT NOT NULL,
    old_title           TEXT,
    new_title           TEXT,
    person_name         TEXT,
    new_company         TEXT,
    occurred_on         TEXT,
    source_reference_id TEXT REFERENCES source_references(id),
    confirmed_at        TEXT,
    confirmed_by        TEXT,
    dismissal_reason    TEXT,
    external_id         TEXT,
    created_at          TEXT NOT NULL,
    updated_at          TEXT NOT NULL,
    archived            INTEGER NOT NULL DEFAULT 0,
    archived_at         TEXT,
    archived_by         TEXT
);
CREATE UNIQUE INDEX idx_org_change_external ON org_change_flags(external_id)
    WHERE external_id IS NOT NULL AND archived=0;
CREATE INDEX idx_org_change_account ON org_change_flags(account_id, status, occurred_on);

CREATE TABLE succession_records (
    id                    TEXT PRIMARY KEY,
    account_id            TEXT NOT NULL REFERENCES accounts(id),
    departed_person_id    TEXT REFERENCES persons(id),
    successor_person_id   TEXT REFERENCES persons(id),
    successor_placeholder_id TEXT REFERENCES persons(id),
    org_change_flag_id    TEXT REFERENCES org_change_flags(id),
    status                TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open','completed')),
    departed_to           TEXT,
    relationship_snapshot_json TEXT,
    transfer_note         TEXT,
    occurred_on           TEXT,
    completed_at          TEXT,
    created_at            TEXT NOT NULL,
    updated_at            TEXT NOT NULL
);
CREATE INDEX idx_succession_account ON succession_records(account_id, status);

-- Recreate both play tables together: play_runs references play_definitions, and SQLite cannot
-- widen the trigger CHECK in place.  Existing history is preserved with a null episode link.
CREATE TABLE play_definitions_new (
    id            TEXT PRIMARY KEY,
    name          TEXT NOT NULL,
    trigger_kind  TEXT NOT NULL CHECK (trigger_kind IN
                  ('renewal_window','overdue_commitment','stale_stakeholder','active_blocker',
                   'checklist_overdue','unanswered_email','unidentified_placeholder',
                   'no_second_champion','champion_gone_quiet','stalled_cohort',
                   'expansion_signal','org_change_confirmed','calendar_moment','land_and_leave',
                   'cadence_overdue')),
    action_template TEXT NOT NULL,
    active        INTEGER NOT NULL DEFAULT 1,
    created_at    TEXT NOT NULL,
    updated_at    TEXT NOT NULL,
    archived      INTEGER NOT NULL DEFAULT 0,
    archived_at   TEXT,
    archived_by   TEXT
);
INSERT INTO play_definitions_new SELECT * FROM play_definitions;

CREATE TABLE play_runs_new (
    id              TEXT PRIMARY KEY,
    play_id         TEXT NOT NULL REFERENCES play_definitions_new(id),
    account_id      TEXT REFERENCES accounts(id),
    signal_episode_id TEXT REFERENCES signal_episodes(id),
    trigger_context TEXT,
    action_text     TEXT,
    status          TEXT NOT NULL DEFAULT 'fired' CHECK (status IN ('fired','completed','dismissed')),
    effectiveness   TEXT CHECK (effectiveness IN ('effective','unclear','ineffective')),
    effectiveness_note TEXT,
    dedupe_key      TEXT,
    fired_at        TEXT NOT NULL,
    completed_at    TEXT
);
INSERT INTO play_runs_new (
    id,play_id,account_id,trigger_context,action_text,status,effectiveness,
    effectiveness_note,dedupe_key,fired_at,completed_at)
SELECT id,play_id,account_id,trigger_context,action_text,status,effectiveness,
       effectiveness_note,dedupe_key,fired_at,completed_at FROM play_runs;

DROP TABLE play_runs;
DROP TABLE play_definitions;
ALTER TABLE play_definitions_new RENAME TO play_definitions;
ALTER TABLE play_runs_new RENAME TO play_runs;
CREATE INDEX idx_playruns_status ON play_runs(status);
CREATE UNIQUE INDEX idx_playruns_dedupe ON play_runs(dedupe_key)
    WHERE dedupe_key IS NOT NULL;
CREATE UNIQUE INDEX idx_playruns_episode ON play_runs(play_id, signal_episode_id)
    WHERE signal_episode_id IS NOT NULL;

-- Cross-account protections for every new typed link.  A plain FK proves that a row exists; it
-- does not prove that it belongs to the account named by the parent row.
CREATE TRIGGER trg_pull_signal_cell_account_insert BEFORE INSERT ON pull_signals
WHEN NEW.cell_id IS NOT NULL AND NOT EXISTS (
    SELECT 1 FROM whitespace_cells c WHERE c.id=NEW.cell_id AND c.account_id=NEW.account_id)
BEGIN SELECT RAISE(ABORT, 'pull signal cell belongs to a different account'); END;

CREATE TRIGGER trg_pull_signal_scope_insert BEFORE INSERT ON pull_signals
WHEN (NEW.program_id IS NOT NULL AND NOT EXISTS (
        SELECT 1 FROM programs p WHERE p.id=NEW.program_id AND p.account_id=NEW.account_id))
  OR (NEW.requested_by_person_id IS NOT NULL AND NOT EXISTS (
        SELECT 1 FROM persons p WHERE p.id=NEW.requested_by_person_id AND p.account_id=NEW.account_id))
BEGIN SELECT RAISE(ABORT, 'pull signal relation belongs to a different account'); END;

CREATE TRIGGER trg_pull_signal_scope_update BEFORE UPDATE OF account_id,program_id,cell_id,requested_by_person_id ON pull_signals
WHEN (NEW.cell_id IS NOT NULL AND NOT EXISTS (
        SELECT 1 FROM whitespace_cells c WHERE c.id=NEW.cell_id AND c.account_id=NEW.account_id))
  OR (NEW.program_id IS NOT NULL AND NOT EXISTS (
        SELECT 1 FROM programs p WHERE p.id=NEW.program_id AND p.account_id=NEW.account_id))
  OR (NEW.requested_by_person_id IS NOT NULL AND NOT EXISTS (
        SELECT 1 FROM persons p WHERE p.id=NEW.requested_by_person_id AND p.account_id=NEW.account_id))
BEGIN SELECT RAISE(ABORT, 'pull signal relation belongs to a different account'); END;

CREATE TRIGGER trg_signal_cell_account_insert BEFORE INSERT ON signal_episodes
WHEN (NEW.cell_id IS NOT NULL AND NOT EXISTS (
        SELECT 1 FROM whitespace_cells c WHERE c.id=NEW.cell_id AND c.account_id=NEW.account_id))
  OR (NEW.program_id IS NOT NULL AND NEW.account_id IS NOT NULL AND NOT EXISTS (
        SELECT 1 FROM programs p WHERE p.id=NEW.program_id AND p.account_id=NEW.account_id))
BEGIN SELECT RAISE(ABORT, 'signal cell belongs to a different account'); END;

CREATE TRIGGER trg_signal_scope_update BEFORE UPDATE OF account_id,program_id,cell_id ON signal_episodes
WHEN (NEW.cell_id IS NOT NULL AND NOT EXISTS (
        SELECT 1 FROM whitespace_cells c WHERE c.id=NEW.cell_id AND c.account_id=NEW.account_id))
  OR (NEW.program_id IS NOT NULL AND NEW.account_id IS NOT NULL AND NOT EXISTS (
        SELECT 1 FROM programs p WHERE p.id=NEW.program_id AND p.account_id=NEW.account_id))
BEGIN SELECT RAISE(ABORT, 'signal relation belongs to a different account'); END;

CREATE TRIGGER trg_calendar_program_account_insert BEFORE INSERT ON calendar_events
WHEN NEW.program_id IS NOT NULL AND NEW.account_id IS NOT NULL AND NOT EXISTS (
    SELECT 1 FROM programs p WHERE p.id=NEW.program_id AND p.account_id=NEW.account_id)
BEGIN SELECT RAISE(ABORT, 'calendar program belongs to a different account'); END;

CREATE TRIGGER trg_calendar_scope_insert BEFORE INSERT ON calendar_events
WHEN NEW.cell_id IS NOT NULL AND NOT EXISTS (
    SELECT 1 FROM whitespace_cells c WHERE c.id=NEW.cell_id AND c.account_id=NEW.account_id)
BEGIN SELECT RAISE(ABORT, 'calendar cell belongs to a different account'); END;

CREATE TRIGGER trg_calendar_scope_update BEFORE UPDATE OF account_id,program_id,cell_id ON calendar_events
WHEN (NEW.program_id IS NOT NULL AND NEW.account_id IS NOT NULL AND NOT EXISTS (
        SELECT 1 FROM programs p WHERE p.id=NEW.program_id AND p.account_id=NEW.account_id))
  OR (NEW.cell_id IS NOT NULL AND NOT EXISTS (
        SELECT 1 FROM whitespace_cells c WHERE c.id=NEW.cell_id AND c.account_id=NEW.account_id))
BEGIN SELECT RAISE(ABORT, 'calendar relation belongs to a different account'); END;

CREATE TRIGGER trg_calendar_attendee_account_insert BEFORE INSERT ON calendar_event_attendees
WHEN NEW.person_id IS NOT NULL AND NOT EXISTS (
    SELECT 1 FROM calendar_events e JOIN persons p ON p.id=NEW.person_id
    WHERE e.id=NEW.event_id AND (e.account_id IS NULL OR p.account_id=e.account_id OR p.affiliation='valence'))
BEGIN SELECT RAISE(ABORT, 'calendar attendee belongs to a different account'); END;

CREATE TRIGGER trg_calendar_attendee_account_update BEFORE UPDATE OF event_id,person_id ON calendar_event_attendees
WHEN NEW.person_id IS NOT NULL AND NOT EXISTS (
    SELECT 1 FROM calendar_events e JOIN persons p ON p.id=NEW.person_id
    WHERE e.id=NEW.event_id AND (e.account_id IS NULL OR p.account_id=e.account_id OR p.affiliation='valence'))
BEGIN SELECT RAISE(ABORT, 'calendar attendee belongs to a different account'); END;

CREATE TRIGGER trg_org_person_account_insert BEFORE INSERT ON org_change_flags
WHEN NEW.person_id IS NOT NULL AND NOT EXISTS (
    SELECT 1 FROM persons p WHERE p.id=NEW.person_id AND p.account_id=NEW.account_id)
BEGIN SELECT RAISE(ABORT, 'org-change person belongs to a different account'); END;

CREATE TRIGGER trg_org_scope_insert BEFORE INSERT ON org_change_flags
WHEN NEW.cell_id IS NOT NULL AND NOT EXISTS (
    SELECT 1 FROM whitespace_cells c WHERE c.id=NEW.cell_id AND c.account_id=NEW.account_id)
BEGIN SELECT RAISE(ABORT, 'org-change cell belongs to a different account'); END;

CREATE TRIGGER trg_org_scope_update BEFORE UPDATE OF account_id,person_id,cell_id ON org_change_flags
WHEN (NEW.person_id IS NOT NULL AND NOT EXISTS (
        SELECT 1 FROM persons p WHERE p.id=NEW.person_id AND p.account_id=NEW.account_id))
  OR (NEW.cell_id IS NOT NULL AND NOT EXISTS (
        SELECT 1 FROM whitespace_cells c WHERE c.id=NEW.cell_id AND c.account_id=NEW.account_id))
BEGIN SELECT RAISE(ABORT, 'org-change relation belongs to a different account'); END;

CREATE TRIGGER trg_succession_scope_insert BEFORE INSERT ON succession_records
WHEN (NEW.departed_person_id IS NOT NULL AND NOT EXISTS (
        SELECT 1 FROM persons p WHERE p.id=NEW.departed_person_id AND p.account_id=NEW.account_id))
  OR (NEW.successor_person_id IS NOT NULL AND NOT EXISTS (
        SELECT 1 FROM persons p WHERE p.id=NEW.successor_person_id AND p.account_id=NEW.account_id))
  OR (NEW.successor_placeholder_id IS NOT NULL AND NOT EXISTS (
        SELECT 1 FROM persons p WHERE p.id=NEW.successor_placeholder_id AND p.account_id=NEW.account_id))
BEGIN SELECT RAISE(ABORT, 'succession person belongs to a different account'); END;

CREATE TRIGGER trg_succession_scope_update BEFORE UPDATE OF account_id,departed_person_id,successor_person_id,successor_placeholder_id ON succession_records
WHEN (NEW.departed_person_id IS NOT NULL AND NOT EXISTS (
        SELECT 1 FROM persons p WHERE p.id=NEW.departed_person_id AND p.account_id=NEW.account_id))
  OR (NEW.successor_person_id IS NOT NULL AND NOT EXISTS (
        SELECT 1 FROM persons p WHERE p.id=NEW.successor_person_id AND p.account_id=NEW.account_id))
  OR (NEW.successor_placeholder_id IS NOT NULL AND NOT EXISTS (
        SELECT 1 FROM persons p WHERE p.id=NEW.successor_placeholder_id AND p.account_id=NEW.account_id))
BEGIN SELECT RAISE(ABORT, 'succession person belongs to a different account'); END;
