-- Migration 0055 — Stage 17 Slice 2: the monthly surface-usage rollup (SURFACE-USAGE-SPEC.md §9.4).
--
-- The spec's §10 says "Migration 0054". It was written before VISIBILITY Slice 6 landed
-- `0054_advocacy_tags.sql`, so the next free number is 0055 and Slice 3's retirement notes take
-- 0056. The numbering rule is not stale even though the number in the text is (D-278).
--
-- **Why a rollup exists at all.** Answering "is this quarterly surface used" needs more history
-- than the 90-day raw purge keeps. The obvious move — raise `retention_days` — would keep
-- session-linked rows for a year, which is far more behavioural detail than the question needs.
-- This table instead keeps strictly less than the rows it summarises, and that is precisely what
-- justifies its longer life: no session id, no account id, no properties, no event ids. A month, a
-- surface, two counts, and a date.
--
-- Four things this schema deliberately does not do.
--
--  1. **No `state`, `status`, `observation`, or score column.** §6 reads on four axes that never
--     combine, and the observation (`engaged` / `rendered_not_engaged` / `not_rendered` /
--     `insufficient_window`) is computed at query time from the counts and the window. Storing it
--     would be a second source of truth over the same question, in the manner migrations 0042,
--     0046, and 0050 each refused; a schema-introspection test asserts the absence, and the same
--     test forbids `score`, `rating`, `health`, and `usage_index` by name.
--
--  2. **No account id.** Which accounts an operator looks at while using a section is a different
--     and more sensitive question than whether the section is used, and this table exists for the
--     second one. The raw events carry `account_id` for §17.5's funnel and are purged at 90 days;
--     the thing that lives for three years does not carry it.
--
--  3. **No foreign key to anything, and no CHECK on `surface_key`.** The registry is Python (§10:
--     "the registry itself is code, not a table"), so a CHECK could only duplicate it and then
--     disagree with it. `app/telemetry.py` rejects an unregistered slug at write time, which is
--     where the one copy of that rule lives.
--
--  4. **No trigger to maintain it.** The fold runs in Python so it is testable and so it cannot
--     fire inside a domain transaction it has no business being in.
--
-- Retention is 36 months for this table and unchanged at 90 days for `product_events`. Disabling
-- measurement deletes this table's rows in the same transaction as the raw ones — a rollup that
-- survived the off switch would be the loophole that makes "measurement is disabled" and "there is
-- measurement data" both true at once (§9.4).
PRAGMA foreign_keys = ON;

CREATE TABLE surface_usage_months (
    -- Deterministic: '<surface_key>:<month>'. A re-fold updates the row it already wrote rather
    -- than racing a lookup, which is what makes the fold idempotent.
    id              TEXT PRIMARY KEY,
    surface_key     TEXT NOT NULL,
    month           TEXT NOT NULL,
    rendered        INTEGER NOT NULL DEFAULT 0,
    engaged         INTEGER NOT NULL DEFAULT 0,
    -- A date, not a timestamp. The question is "when was this last operated", and a time of day
    -- narrows a single-operator installation's activity in a way the answer does not need.
    last_engaged_on TEXT,
    updated_at      TEXT NOT NULL,
    UNIQUE (surface_key, month),
    CHECK (length(surface_key) <= 64),
    CHECK (month GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]'),
    CHECK (rendered >= 0),
    CHECK (engaged >= 0),
    CHECK (last_engaged_on IS NULL
           OR last_engaged_on GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]')
);

CREATE INDEX idx_surface_usage_months_surface ON surface_usage_months(surface_key, month);
CREATE INDEX idx_surface_usage_months_month ON surface_usage_months(month);

-- §9.4's 36 months, stored beside the raw retention it deliberately differs from rather than as a
-- constant in Python, so the two numbers are visible next to each other when either is questioned.
ALTER TABLE product_telemetry_settings
    ADD COLUMN rollup_retention_months INTEGER NOT NULL DEFAULT 36
    CHECK (rollup_retention_months BETWEEN 1 AND 120);

-- The fold is **incremental and monotone**, not a recompute. A recompute over the raw window would
-- silently *lower* a month's counts as that month aged past the 90-day purge, and a rollup that
-- shrinks on its own is worse than no rollup: the number an operator wrote a retirement note
-- against would stop matching the table it came from. So the fold advances a watermark over
-- `product_events.rowid` — monotone under insert, unaffected by purge — and adds to the stored
-- counts rather than replacing them.
ALTER TABLE product_telemetry_settings
    ADD COLUMN surface_rollup_watermark INTEGER NOT NULL DEFAULT 0;

-- §9.1 asks the report to state its window's start date prominently, so you can discount a period
-- you know was a build week. That start date has to be recorded rather than inferred: inferring it
-- from the earliest surviving row would make a quiet month look like a short window, which is the
-- one direction §6.2 exists to prevent. Set when measurement is switched on, cleared when it is
-- switched off — the off switch discards what was collected, so the observation period restarts.
ALTER TABLE product_telemetry_settings ADD COLUMN measuring_since TEXT;
UPDATE product_telemetry_settings SET measuring_since = datetime('now') WHERE enabled = 1;
