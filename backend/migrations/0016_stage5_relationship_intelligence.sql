-- Migration 0016 — Phase 3 Stage 5: relationship intelligence
--   §3.4 champion_candidates: the identify→develop→validate→arm→maintain pipeline. Stage is
--        operator-set, but the validate/arm/maintain stages are gated by advocacy EVIDENCE in the
--        API (the same coach-vs-champion gate as §3.2) — you cannot claim a validated champion
--        without a logged advocacy-without-us event.
--   §3.8 exec_pairings: which Valence executive owns which client executive.
--   §3.12 messaging_entries: the role-based messaging library, per layer (+ optional narrower role),
--        visibility-classified. Seeded from the Valence playbook template; editable.
--   §4.4 pull_signals: expansion/demand signals extracted from comms/transcripts (a §4.4 target),
--        also consumed by the Stage 7 expansion-signal play.
-- Trust boundaries (D-76) unchanged: professional observations only, no sensitive personal data;
-- mock data only. Nothing here stores individual product usage.

PRAGMA foreign_keys = ON;

-- --- §3.4 champion development pipeline --------------------------------------------------------
CREATE TABLE champion_candidates (
    id             TEXT PRIMARY KEY,
    person_id      TEXT NOT NULL REFERENCES persons(id),
    program_id     TEXT REFERENCES programs(id),
    account_id     TEXT NOT NULL REFERENCES accounts(id),
    stage          TEXT NOT NULL DEFAULT 'identify' CHECK (stage IN (
                     'identify','develop','validate','arm','maintain')),
    developed_note TEXT,               -- value delivered to them personally (professional observation)
    developed_on   TEXT,
    armed_note     TEXT,               -- what enablement they've been given, and when
    armed_on       TEXT,
    notes          TEXT,
    created_at     TEXT NOT NULL,
    updated_at     TEXT NOT NULL,
    archived       INTEGER NOT NULL DEFAULT 0,
    archived_at    TEXT,
    archived_by    TEXT
);
CREATE INDEX idx_champion_account ON champion_candidates(account_id, stage);
CREATE UNIQUE INDEX idx_champion_person_program
    ON champion_candidates(person_id, program_id) WHERE archived = 0;

-- --- §3.8 executive alignment map -------------------------------------------------------------
CREATE TABLE exec_pairings (
    id                 TEXT PRIMARY KEY,
    account_id         TEXT NOT NULL REFERENCES accounts(id),
    valence_person_id  TEXT NOT NULL REFERENCES persons(id),  -- affiliation='valence'
    client_person_id   TEXT NOT NULL REFERENCES persons(id),
    next_touch_planned TEXT,
    notes              TEXT,
    created_at         TEXT NOT NULL,
    updated_at         TEXT NOT NULL,
    archived           INTEGER NOT NULL DEFAULT 0,
    archived_at        TEXT,
    archived_by        TEXT
);
CREATE INDEX idx_exec_pairing_account ON exec_pairings(account_id);
CREATE UNIQUE INDEX idx_exec_pairing_client
    ON exec_pairings(client_person_id) WHERE archived = 0;

-- --- §3.12 role-based messaging library -------------------------------------------------------
CREATE TABLE messaging_entries (
    id               TEXT PRIMARY KEY,
    layer            TEXT NOT NULL CHECK (layer IN (
                       'executive','economic','operational','technical_gating','user_advocate')),
    role             TEXT,                  -- optional narrower role within the layer
    value_prop       TEXT,                  -- the value proposition in their terms
    proof_points     TEXT,                  -- proof points that land
    objections       TEXT,                  -- known objections and responses
    artifacts_note   TEXT,                  -- current approved artifacts (link-first, by convention)
    visibility_class TEXT NOT NULL DEFAULT 'internal' CHECK (visibility_class IN (
                       'internal','client_working','qbr_exec','externally_referenceable')),
    created_at       TEXT NOT NULL,
    updated_at       TEXT NOT NULL,
    archived         INTEGER NOT NULL DEFAULT 0,
    archived_at      TEXT,
    archived_by      TEXT
);
CREATE INDEX idx_messaging_layer ON messaging_entries(layer, role);

-- --- §4.4 pull / expansion-demand signals -----------------------------------------------------
CREATE TABLE pull_signals (
    id                    TEXT PRIMARY KEY,
    account_id            TEXT REFERENCES accounts(id),
    program_id            TEXT REFERENCES programs(id),
    description           TEXT NOT NULL,
    occurred_on           TEXT,
    status                TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open','actioned','dismissed')),
    source_interaction_id TEXT REFERENCES interactions(id),
    source_reference_id   TEXT REFERENCES source_references(id),
    created_at            TEXT NOT NULL,
    updated_at            TEXT NOT NULL,
    archived              INTEGER NOT NULL DEFAULT 0,
    archived_at           TEXT,
    archived_by           TEXT
);
CREATE INDEX idx_pull_account ON pull_signals(account_id, status);

-- --- widen the extraction proposal mutation set for the §4.4 targets --------------------------
-- SQLite can't alter a CHECK in place; recreate extraction_proposals (it only FKs OUT to
-- extraction_runs, nothing FKs into it). The widened enum adds the four §4.4 relationship/
-- commercial targets alongside the original v4 execution targets.
CREATE TABLE extraction_proposals_new (
    id                TEXT PRIMARY KEY,
    run_id            TEXT NOT NULL REFERENCES extraction_runs(id),
    mutation_type     TEXT NOT NULL CHECK (mutation_type IN (
                        'create_commitment','create_risk','create_decision','create_task','create_issue',
                        'fill_placeholder','log_pull_signal','create_deployment_moment','create_value_story')),
    payload_json      TEXT NOT NULL,
    source_span       TEXT,
    confidence        TEXT,
    status            TEXT NOT NULL DEFAULT 'proposed' CHECK (status IN ('proposed','accepted','rejected')),
    created_object_type TEXT,
    created_object_id TEXT,
    created_at        TEXT NOT NULL,
    updated_at        TEXT NOT NULL
);
INSERT INTO extraction_proposals_new SELECT * FROM extraction_proposals;
DROP TABLE extraction_proposals;
ALTER TABLE extraction_proposals_new RENAME TO extraction_proposals;
CREATE INDEX idx_proposals_run ON extraction_proposals(run_id, status);
