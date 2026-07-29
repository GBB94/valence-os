-- Migration 0010 — tags on source references (Section 5O: "Files & context library …
-- link-first, tagged, searchable"). The one remaining §5O piece. Tags stored as a
-- comma-separated text field, consistent with the tag pattern elsewhere (e.g. value
-- stories) — tags are a tag, not an object (Section 11). No new object type.

ALTER TABLE source_references ADD COLUMN tags TEXT;
