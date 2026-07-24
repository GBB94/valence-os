-- Migration 0008 — global search (Section 8: SQLite FTS5 over native records + summaries)
-- A standalone FTS5 index. At this scale (a few thousand rows) it is rebuilt on demand
-- from the current native records rather than kept in sync by per-table triggers — boring
-- and always fresh. object_id/account_id are stored (UNINDEXED) for navigation.

CREATE VIRTUAL TABLE search_index USING fts5(
    object_type,
    object_id   UNINDEXED,
    account_id  UNINDEXED,
    program_id  UNINDEXED,
    title,
    body,
    tokenize = 'porter unicode61'
);
