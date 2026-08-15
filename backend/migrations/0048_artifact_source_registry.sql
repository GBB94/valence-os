-- Migration 0048 — one registry for an artifact's sources, not two.
--
-- Migration 0047 added `generated_documents.source_manifest_json` to satisfy §16.6's "included
-- source identities". That was a mistake, found while wiring the writer: `generated_document_sources`
-- has held exactly this since migration 0026, it is already written by the internal review packet,
-- the account brief, the portfolio brief and the scheduled team update, and it carries two things a
-- JSON blob does not — `record_version`, so a later reader can tell the snapshot apart from the
-- live row, and `visibility_class`, which is the field the client/internal boundary is audited on.
--
-- Keeping both would have created the failure this codebase has refused three times now (D-139,
-- D-143, D-149): a second store of the same fact, free to disagree with the first. The column is
-- removed rather than left unused, because a dead column is an invitation to write to it.
--
-- Template identity stays on `generated_documents` (`template_key`, `template_version`) — that is a
-- property of the artifact itself, not of a source, and it has nowhere else to live.
--
-- No data is lost: the column was added and dropped in the same slice and nothing ever wrote to it.
PRAGMA foreign_keys = ON;

ALTER TABLE generated_documents DROP COLUMN source_manifest_json;
