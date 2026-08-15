-- Migration 0056 — Stage 17 Slice 3: recorded causes and reversible retirement
-- (SURFACE-USAGE-SPEC.md §7.1, §7.2, §10). The spec's §10 says "0054"; that number went to
-- VISIBILITY's `advocacy_tags` and the rollup took 0055 (D-278).
--
-- **The table is append-only.** Undoing a batch and restoring a surface both write new rows rather
-- than updating or deleting old ones, and the current action for a surface is the latest row by
-- `recorded_on`. That is what makes "I hid this in September and put it back in November" legible
-- six months later, which is the question that actually gets asked — and it is why `restore` is a
-- row in this table rather than a delete of the row it reverses. A mistaken retirement must be
-- visible in the record, not quietly absent from it (§7.2).
--
-- Four deliberate absences.
--
--  1. **No `state` or `current_state` column, on this table or on any registry-shaped table.** The
--     current action is derived — latest row per `surface_key` — for the reason the rest of this
--     codebase derives rather than stores: a second copy of the answer is a second thing that can
--     disagree with the record it came from (§7.3). A schema-introspection test asserts it, in the
--     manner of migrations 0042, 0046, 0050, and 0055.
--
--  2. **No score, rating, health, or usage index.** §6.1's assertion applies to every table this
--     feature adds, not only the rollup.
--
--  3. **No CHECK on `cause_code` or `action`.** Both vocabularies live in `app/surface_retirement.py`
--     beside the write path, the placement RELATIONSHIP-READINESS-SPEC.md chose for its
--     `(intent, target_type)` pair and INTAKE chose for its kind detection. A CHECK here would be a
--     second copy of a closed list, and the two would diverge the first time one was extended.
--
--  4. **No foreign key to `surface_usage_months` or to anything else.** A note freezes its counts
--     as integers precisely so it does not depend on them: a judgement made against 200 renders and
--     0 engagements is not the same judgement six months later when the numbers have moved.
--     Recomputing on read would let the record silently change its own basis, and a foreign key
--     would invite exactly that join.
--
-- `note` is operator prose and is internal-only. It never reaches the measurement sink and there is
-- no path from this table to `product_events`: the sink's per-event property allowlists carry no
-- key that could hold it, and `retirement_action_applied` carries only the surface, the action, and
-- the cause code.
PRAGMA foreign_keys = ON;

CREATE TABLE surface_retirement_notes (
    id            TEXT PRIMARY KEY,
    surface_key   TEXT NOT NULL,
    -- §7.1's seven, validated in Python. Closed, with no `other` — a cause code with an escape
    -- hatch collects the escape hatch, and then the vocabulary describes nothing.
    cause_code    TEXT NOT NULL,
    -- The window this judgement was made against. A cause is an operator judgement carrying a date
    -- and its evidence, exactly like a stakeholder assessment, and for the same reason: an undated
    -- judgement about a moving system is not evidence of anything (§7.1).
    observed_from TEXT NOT NULL,
    observed_to   TEXT NOT NULL,
    -- Frozen at the moment of the judgement. See absence 4 above.
    rendered      INTEGER NOT NULL,
    engaged       INTEGER NOT NULL,
    -- collapse | demote | retire | restore | none. Permitted where a `state` is not, because it
    -- records an operator command that was applied rather than a status of the surface.
    action        TEXT,
    -- §7.8: one id across every note in a reviewed set, so the whole sitting undoes as one.
    batch_id      TEXT,
    note          TEXT,
    recorded_on   TEXT NOT NULL,
    recorded_by   TEXT NOT NULL,
    CHECK (length(surface_key) <= 64),
    CHECK (length(cause_code) <= 32),
    CHECK (rendered >= 0),
    CHECK (engaged >= 0),
    CHECK (note IS NULL OR length(note) <= 2000)
);

-- The derived-current-action query is `ORDER BY recorded_on DESC, rowid DESC LIMIT 1` per surface,
-- so the index leads with the key and the date.
CREATE INDEX idx_surface_retirement_notes_surface ON surface_retirement_notes(surface_key, recorded_on);
CREATE INDEX idx_surface_retirement_notes_batch ON surface_retirement_notes(batch_id, recorded_on);
