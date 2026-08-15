-- Migration 0050 — Account Path Slice 7: local product measurement (ACCOUNT-PATH-SPEC.md §17.4).
--
-- §17.4 offers an explicit either/or — persist a `product_events` table, or keep an in-memory /
-- local-file adapter. This chooses to persist, because §17.5's questions are not answerable any
-- other way: "which requirement gaps recur across accounts", "do gates reach ready before their
-- target dates", "which reason codes are routinely bypassed" are all questions about a trend, and
-- an in-memory adapter in a single-editor desktop app forgets everything at every restart. The
-- churn the alternative guards against is not present here: a few thousand domain rows, one
-- operator, one writer.
--
-- Four things this schema deliberately does NOT do.
--
--  1. **No foreign keys.** `account_id` and `program_id` are bounded internal identifiers, not
--     relations. A real FK would let a diagnostic row block or complicate a domain mutation —
--     deleting an account, restoring an import — and §17.8 says measurement can never block work.
--     A dangling identifier in telemetry is a row you cannot join; a blocked delete is a bug.
--
--  2. **No event-name CHECK.** The allowlist lives in `app/telemetry.py` beside the write path,
--     the same placement RELATIONSHIP-READINESS-SPEC.md chose for its `(intent, target_type)`
--     pair. §17.3 requires an unknown event to be *rejected in development and ignored with a
--     diagnostic in production* — two behaviours from one condition. A CHECK constraint can only
--     raise, and raising in production is exactly the blocked-work case that is prohibited.
--
--  3. **No audit trigger, and these rows never reach `audit_events`.** Opening a page is not a
--     domain mutation (§17.4). Telemetry is written with plain SQL rather than through `repo`,
--     so it cannot acquire an audit row by accident.
--
--  4. **No free text, enforced structurally.** The adapter validates every property key and
--     value, but the adapter is code and code can be bypassed. The CHECKs below are the backstop
--     that survives a caller who writes this table directly: bounded length, valid JSON, and no
--     `@` anywhere in the payload. Every allowlisted property value is a lower-case slug, an
--     integer, or a boolean, so `@` cannot appear legitimately — and an email address is the
--     single most likely thing to leak into a "just this once" property.
--
-- `ranking_rule_version` is a column rather than a property because §17.6 makes it the axis the
-- whole refinement process pivots on: step 4 compares old and new ordering, step 7 records the
-- version in both the response and telemetry. The one dimension every refinement query groups by
-- should not have to be dug out of a JSON blob.
PRAGMA foreign_keys = ON;

CREATE TABLE product_events (
    id                   TEXT PRIMARY KEY,
    event_name           TEXT NOT NULL,
    schema_version       INTEGER NOT NULL,
    occurred_at          TEXT NOT NULL,
    -- Pseudonymous and local: minted by the browser per session, never derived from an operator
    -- identity, never joined to `persons`.
    session_id           TEXT NOT NULL,
    account_id           TEXT,
    program_id           TEXT,
    ranking_rule_version TEXT,
    properties_json      TEXT NOT NULL DEFAULT '{}',
    created_at           TEXT NOT NULL,
    CHECK (json_valid(properties_json)),
    CHECK (length(properties_json) <= 512),
    CHECK (instr(properties_json, '@') = 0),
    CHECK (length(session_id) <= 64),
    CHECK (length(event_name) <= 64)
);

CREATE INDEX idx_product_events_name_time ON product_events(event_name, occurred_at);
CREATE INDEX idx_product_events_account ON product_events(account_id, occurred_at);
CREATE INDEX idx_product_events_session ON product_events(session_id, occurred_at);

-- §17.4: "A local setting can disable measurement", and "retention is bounded and documented".
-- Both live here rather than in an environment variable so the operator can turn measurement off
-- from the application they are actually using.
CREATE TABLE product_telemetry_settings (
    id             TEXT PRIMARY KEY CHECK (id='singleton'),
    enabled        INTEGER NOT NULL DEFAULT 1 CHECK (enabled IN (0,1)),
    retention_days INTEGER NOT NULL DEFAULT 90 CHECK (retention_days BETWEEN 1 AND 400),
    updated_at     TEXT NOT NULL
);
INSERT INTO product_telemetry_settings (id, enabled, retention_days, updated_at)
VALUES ('singleton', 1, 90, datetime('now'));
