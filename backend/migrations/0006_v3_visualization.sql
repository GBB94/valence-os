-- Migration 0006 — v3 visualization support
-- Adds the graph attributes deferred from v0 (influence, relationship strength) to
-- stakeholder roles, and the relationship edges named in Section 4 (reports-to,
-- sponsors, influences). These are stakeholder assessments, so they carry a date and
-- an evidence note (Section 2 trust boundary), enforced in the API.
-- Budget-waterfall and richer metric views are derived (no new tables).

PRAGMA foreign_keys = ON;

ALTER TABLE stakeholder_roles ADD COLUMN influence TEXT
    CHECK (influence IN ('low','medium','high'));
ALTER TABLE stakeholder_roles ADD COLUMN relationship_strength TEXT
    CHECK (relationship_strength IN ('weak','medium','strong'));
ALTER TABLE stakeholder_roles ADD COLUMN graph_assessed_on TEXT;
ALTER TABLE stakeholder_roles ADD COLUMN graph_evidence_note TEXT;

-- Relationship edges between people (reporting hierarchy + influence/sponsorship overlay).
CREATE TABLE relationship_edges (
    id            TEXT PRIMARY KEY,
    account_id    TEXT NOT NULL REFERENCES accounts(id),
    from_person_id TEXT NOT NULL REFERENCES persons(id),
    to_person_id   TEXT NOT NULL REFERENCES persons(id),
    type          TEXT NOT NULL CHECK (type IN ('reports_to','sponsors','influences')),
    program_id    TEXT REFERENCES programs(id),
    note          TEXT,
    created_at    TEXT NOT NULL,
    updated_at    TEXT NOT NULL,
    archived      INTEGER NOT NULL DEFAULT 0,
    archived_at   TEXT,
    archived_by   TEXT
);
CREATE INDEX idx_edges_account ON relationship_edges(account_id);

-- Optional: recovered incumbent-vendor spend feeds the budget waterfall (incumbent
-- displacement). Stored per account as a labeled figure with a source note.
CREATE TABLE recovered_spend (
    id          TEXT PRIMARY KEY,
    account_id  TEXT NOT NULL REFERENCES accounts(id),
    label       TEXT NOT NULL,
    amount      REAL NOT NULL,
    source_note TEXT,
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL,
    archived    INTEGER NOT NULL DEFAULT 0,
    archived_at TEXT,
    archived_by TEXT
);
