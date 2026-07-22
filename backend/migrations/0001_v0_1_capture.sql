-- Migration 0001 — v0.1 capture slice
-- Tables: source_references, accounts, persons, programs, stakeholder_roles,
-- interactions, interaction_participants, capture_inbox_items, audit_events.
-- Account status columns arrive in the v0.3 migration; execution objects in v0.2.
-- All timestamps ISO-8601 UTC (text); dates YYYY-MM-DD (text). Enums via CHECK.

PRAGMA foreign_keys = ON;

-- Reusable source pointer (link-first).
CREATE TABLE source_references (
    id           TEXT PRIMARY KEY,
    type         TEXT NOT NULL CHECK (type IN ('file','transcript_span','meeting','crm_record','data_report','manual_entry')),
    label        TEXT NOT NULL,
    url          TEXT,
    locator      TEXT,
    created_at   TEXT NOT NULL,
    updated_at   TEXT NOT NULL,
    archived     INTEGER NOT NULL DEFAULT 0,
    archived_at  TEXT,
    archived_by  TEXT
);

-- Account (v0.1 columns only; delivery/commercial status columns added in v0.3).
CREATE TABLE accounts (
    id             TEXT PRIMARY KEY,
    name           TEXT NOT NULL,
    short_context  TEXT,
    incumbent_note TEXT,
    created_at     TEXT NOT NULL,
    updated_at     TEXT NOT NULL,
    archived       INTEGER NOT NULL DEFAULT 0,
    archived_at    TEXT,
    archived_by    TEXT
);

-- Person: client people (account_id set) or Valence internal (affiliation='valence', account_id null).
CREATE TABLE persons (
    id           TEXT PRIMARY KEY,
    name         TEXT NOT NULL,
    affiliation  TEXT NOT NULL DEFAULT 'client' CHECK (affiliation IN ('client','valence')),
    account_id   TEXT REFERENCES accounts(id),
    title        TEXT,
    email        TEXT,
    created_at   TEXT NOT NULL,
    updated_at   TEXT NOT NULL,
    archived     INTEGER NOT NULL DEFAULT 0,
    archived_at  TEXT,
    archived_by  TEXT
);

-- Program: primary operating object; phase lives here.
CREATE TABLE programs (
    id                     TEXT PRIMARY KEY,
    account_id             TEXT NOT NULL REFERENCES accounts(id),
    name                   TEXT NOT NULL,
    phase                  TEXT NOT NULL DEFAULT 'foundation'
                             CHECK (phase IN ('foundation','launch','programmatic','expansion','renewal','closed')),
    region                 TEXT,
    audience               TEXT,
    use_case               TEXT,
    problem_statement      TEXT,
    in_scope_population     TEXT,
    out_of_scope_population TEXT,
    launch_definition      TEXT,
    success_criteria       TEXT,
    expansion_hypothesis   TEXT,
    explicit_exclusions    TEXT,
    sponsor_person_id      TEXT REFERENCES persons(id),
    created_at             TEXT NOT NULL,
    updated_at             TEXT NOT NULL,
    archived               INTEGER NOT NULL DEFAULT 0,
    archived_at            TEXT,
    archived_by            TEXT
);

-- StakeholderRole: Person x Program with role + dated/evidenced stance.
CREATE TABLE stakeholder_roles (
    id                  TEXT PRIMARY KEY,
    program_id          TEXT NOT NULL REFERENCES programs(id),
    person_id           TEXT NOT NULL REFERENCES persons(id),
    role                TEXT NOT NULL DEFAULT 'other'
                          CHECK (role IN ('champion','budget_owner','program_owner','it','legal_dpo','works_council_contact','other')),
    stance              TEXT CHECK (stance IN ('supporter','skeptic','unconverted')),
    stance_assessed_on  TEXT,
    stance_evidence_note TEXT,
    cares_about         TEXT,
    value_for_them      TEXT,
    created_at          TEXT NOT NULL,
    updated_at          TEXT NOT NULL,
    archived            INTEGER NOT NULL DEFAULT 0,
    archived_at         TEXT,
    archived_by         TEXT,
    -- Section 2 trust boundary: stance always carries a date and an evidence note.
    CHECK (stance IS NULL OR (stance_assessed_on IS NOT NULL AND stance_evidence_note IS NOT NULL))
);

-- Interaction: foundational record. G2 ruling: account_id required, program_id nullable.
CREATE TABLE interactions (
    id                  TEXT PRIMARY KEY,
    account_id          TEXT NOT NULL REFERENCES accounts(id),
    program_id          TEXT REFERENCES programs(id),
    occurred_on         TEXT NOT NULL,
    occurred_at_time    TEXT,
    type                TEXT NOT NULL DEFAULT 'meeting'
                          CHECK (type IN ('call','meeting','email','workshop','message','other')),
    summary             TEXT,
    raw_notes           TEXT,               -- internal-only by default
    source_reference_id TEXT REFERENCES source_references(id),
    follow_up           TEXT,
    meaningful_touch    INTEGER NOT NULL DEFAULT 1,
    created_at          TEXT NOT NULL,
    updated_at          TEXT NOT NULL,
    archived            INTEGER NOT NULL DEFAULT 0,
    archived_at         TEXT,
    archived_by         TEXT
);
CREATE INDEX idx_interactions_account ON interactions(account_id, occurred_on);
CREATE INDEX idx_interactions_program ON interactions(program_id, occurred_on);

CREATE TABLE interaction_participants (
    interaction_id TEXT NOT NULL REFERENCES interactions(id),
    person_id      TEXT NOT NULL REFERENCES persons(id),
    PRIMARY KEY (interaction_id, person_id)
);

-- Capture inbox: untriaged notes attached to an interaction; converted (v0.2) or dismissed.
CREATE TABLE capture_inbox_items (
    id                TEXT PRIMARY KEY,
    interaction_id    TEXT NOT NULL REFERENCES interactions(id),
    raw_text          TEXT NOT NULL,
    status            TEXT NOT NULL DEFAULT 'untriaged' CHECK (status IN ('untriaged','converted','dismissed')),
    converted_to_type TEXT CHECK (converted_to_type IN ('task','commitment','decision','risk','issue')),
    converted_to_id   TEXT,
    resolved_on       TEXT,
    resolved_by       TEXT,   -- app-level operator identity (like audit.actor_id); not FK-coupled to seed
    created_at        TEXT NOT NULL,
    updated_at        TEXT NOT NULL,
    archived          INTEGER NOT NULL DEFAULT 0,
    archived_at       TEXT,
    archived_by       TEXT
);
CREATE INDEX idx_inbox_status ON capture_inbox_items(status);

-- Append-only audit log (CLAUDE.md). Never updated or deleted.
CREATE TABLE audit_events (
    id          TEXT PRIMARY KEY,
    occurred_at TEXT NOT NULL,
    actor_id    TEXT,
    object_type TEXT NOT NULL,
    object_id   TEXT NOT NULL,
    action      TEXT NOT NULL CHECK (action IN ('create','update','archive','convert','close')),
    before      TEXT,
    after       TEXT,
    source      TEXT NOT NULL DEFAULT 'user' CHECK (source IN ('user'))
);
CREATE INDEX idx_audit_object ON audit_events(object_type, object_id);
