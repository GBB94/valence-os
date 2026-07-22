-- Migration 0002 — v0.2 execution slice
-- Tasks, commitments (two owners), decisions, risks, issues, milestones.
-- Domain person refs (owners, responsible party, decided_by, acknowledged_by) FK to persons;
-- actor/closer fields (closed_by, resolved_by, completed_by) are plain TEXT operator identity (D-11).
-- Closures record date, closer, and a note (Section 4 definitions of done).

PRAGMA foreign_keys = ON;

CREATE TABLE tasks (
    id                    TEXT PRIMARY KEY,
    program_id            TEXT NOT NULL REFERENCES programs(id),
    description           TEXT NOT NULL,
    internal_owner_id     TEXT REFERENCES persons(id),
    due_date              TEXT,
    status                TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open','done','cancelled')),
    closed_on             TEXT,
    closed_by             TEXT,
    close_note            TEXT,
    source_interaction_id TEXT REFERENCES interactions(id),
    source_reference_id   TEXT REFERENCES source_references(id),
    created_at            TEXT NOT NULL,
    updated_at            TEXT NOT NULL,
    archived              INTEGER NOT NULL DEFAULT 0,
    archived_at           TEXT,
    archived_by           TEXT
);
CREATE INDEX idx_tasks_program ON tasks(program_id, status);

CREATE TABLE commitments (
    id                    TEXT PRIMARY KEY,
    program_id            TEXT NOT NULL REFERENCES programs(id),
    description           TEXT NOT NULL,
    responsible_party_id  TEXT NOT NULL REFERENCES persons(id),   -- who performs it (often client)
    internal_owner_id     TEXT NOT NULL REFERENCES persons(id),   -- Valence follow-up owner (never null)
    due_date              TEXT NOT NULL,                          -- success criterion: always present
    status                TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open','closed')),
    acknowledged_by_id    TEXT REFERENCES persons(id),            -- receiving party who acknowledged
    closed_on             TEXT,
    closed_by             TEXT,
    close_note            TEXT,
    source_interaction_id TEXT REFERENCES interactions(id),
    source_reference_id   TEXT REFERENCES source_references(id),
    created_at            TEXT NOT NULL,
    updated_at            TEXT NOT NULL,
    archived              INTEGER NOT NULL DEFAULT 0,
    archived_at           TEXT,
    archived_by           TEXT
);
CREATE INDEX idx_commitments_program ON commitments(program_id, status);
CREATE INDEX idx_commitments_due ON commitments(status, due_date);

CREATE TABLE decisions (
    id                    TEXT PRIMARY KEY,
    program_id            TEXT NOT NULL REFERENCES programs(id),
    description           TEXT NOT NULL,
    decided_on            TEXT,
    decided_by_id         TEXT REFERENCES persons(id),
    rationale             TEXT,
    supersedes_id         TEXT REFERENCES decisions(id),
    status                TEXT NOT NULL DEFAULT 'recorded' CHECK (status IN ('recorded','superseded')),
    source_interaction_id TEXT REFERENCES interactions(id),
    source_reference_id   TEXT REFERENCES source_references(id),
    created_at            TEXT NOT NULL,
    updated_at            TEXT NOT NULL,
    archived              INTEGER NOT NULL DEFAULT 0,
    archived_at           TEXT,
    archived_by           TEXT
);
CREATE INDEX idx_decisions_program ON decisions(program_id);

CREATE TABLE risks (
    id                    TEXT PRIMARY KEY,
    program_id            TEXT NOT NULL REFERENCES programs(id),
    description           TEXT NOT NULL,
    severity              TEXT NOT NULL DEFAULT 'medium' CHECK (severity IN ('low','medium','high')),
    is_blocker            INTEGER NOT NULL DEFAULT 0,
    mitigation            TEXT,                                   -- note: mitigation != closure
    status                TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open','closed')),
    close_reason          TEXT CHECK (close_reason IN ('no_longer_possible','no_longer_relevant')),
    closed_on             TEXT,
    closed_by             TEXT,
    close_note            TEXT,
    internal_owner_id     TEXT REFERENCES persons(id),
    source_interaction_id TEXT REFERENCES interactions(id),
    source_reference_id   TEXT REFERENCES source_references(id),
    created_at            TEXT NOT NULL,
    updated_at            TEXT NOT NULL,
    archived              INTEGER NOT NULL DEFAULT 0,
    archived_at           TEXT,
    archived_by           TEXT,
    -- closing a risk requires a reason (Section 4: closes when no longer possible/relevant)
    CHECK (status = 'open' OR close_reason IS NOT NULL)
);
CREATE INDEX idx_risks_program ON risks(program_id, status);

CREATE TABLE issues (
    id                    TEXT PRIMARY KEY,
    program_id            TEXT NOT NULL REFERENCES programs(id),
    description           TEXT NOT NULL,
    is_blocker            INTEGER NOT NULL DEFAULT 0,
    status                TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open','resolved')),
    resolution_type       TEXT CHECK (resolution_type IN ('condition_removed','workaround_operating')),
    resolved_on           TEXT,
    resolved_by           TEXT,
    resolution_note       TEXT,
    internal_owner_id     TEXT REFERENCES persons(id),
    source_interaction_id TEXT REFERENCES interactions(id),
    source_reference_id   TEXT REFERENCES source_references(id),
    created_at            TEXT NOT NULL,
    updated_at            TEXT NOT NULL,
    archived              INTEGER NOT NULL DEFAULT 0,
    archived_at           TEXT,
    archived_by           TEXT,
    -- resolving an issue requires how (condition removed vs workaround)
    CHECK (status = 'open' OR resolution_type IS NOT NULL)
);
CREATE INDEX idx_issues_program ON issues(program_id, status);

CREATE TABLE milestones (
    id                    TEXT PRIMARY KEY,
    program_id            TEXT NOT NULL REFERENCES programs(id),
    name                  TEXT NOT NULL,
    target_date           TEXT,
    success_criteria      TEXT,
    at_risk               INTEGER NOT NULL DEFAULT 0,
    status                TEXT NOT NULL DEFAULT 'upcoming' CHECK (status IN ('upcoming','complete')),
    completed_on          TEXT,
    completed_by          TEXT,
    completion_note       TEXT,
    source_interaction_id TEXT REFERENCES interactions(id),
    created_at            TEXT NOT NULL,
    updated_at            TEXT NOT NULL,
    archived              INTEGER NOT NULL DEFAULT 0,
    archived_at           TEXT,
    archived_by           TEXT
);
CREATE INDEX idx_milestones_program ON milestones(program_id, status);
