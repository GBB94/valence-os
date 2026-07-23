-- Migration 0003 — v0.3 attention slice
-- (a) The two account statuses (delivery/value + commercial), each hand-judged
--     with rationale, assessed date, and the condition that would change it.
--     No composite score (Section 11). Enum {on_track, at_risk, off_track, unknown}
--     confirmed by Zach 2026-07-22 (PA-1). unknown = honest default before assessment.
-- (b) attention_state: the snooze/resolve OVERLAY on the derived queue. Queue items
--     are recomputed each render; only the operator's overlay is stored (D-06).

PRAGMA foreign_keys = ON;

ALTER TABLE accounts ADD COLUMN delivery_status TEXT NOT NULL DEFAULT 'unknown'
    CHECK (delivery_status IN ('on_track','at_risk','off_track','unknown'));
ALTER TABLE accounts ADD COLUMN delivery_status_rationale TEXT;
ALTER TABLE accounts ADD COLUMN delivery_status_assessed_on TEXT;
ALTER TABLE accounts ADD COLUMN delivery_status_change_condition TEXT;

ALTER TABLE accounts ADD COLUMN commercial_status TEXT NOT NULL DEFAULT 'unknown'
    CHECK (commercial_status IN ('on_track','at_risk','off_track','unknown'));
ALTER TABLE accounts ADD COLUMN commercial_status_rationale TEXT;
ALTER TABLE accounts ADD COLUMN commercial_status_assessed_on TEXT;
ALTER TABLE accounts ADD COLUMN commercial_status_change_condition TEXT;

CREATE TABLE attention_state (
    id                    TEXT PRIMARY KEY,
    item_key              TEXT NOT NULL,   -- stable: trigger_type:object_type:object_id
    state                 TEXT NOT NULL CHECK (state IN ('snoozed','resolved')),
    snooze_until          TEXT,            -- required if snoozed and no condition
    resurface_condition   TEXT,            -- required if snoozed and no date
    successor_action_type TEXT CHECK (successor_action_type IN ('task','commitment')),
    successor_action_id   TEXT,
    created_at            TEXT NOT NULL,   -- overlay timestamp; underlying change after this resurfaces the item
    created_by            TEXT,
    -- snoozing needs a return date OR a resurfacing condition; resolving needs a successor link
    CHECK (
        (state = 'snoozed' AND (snooze_until IS NOT NULL OR resurface_condition IS NOT NULL))
        OR
        (state = 'resolved' AND successor_action_id IS NOT NULL)
    )
);
-- One live overlay per item; latest wins. (No unique constraint so history is kept;
-- the builder reads the most recent row per item_key.)
CREATE INDEX idx_attention_item ON attention_state(item_key, created_at);
