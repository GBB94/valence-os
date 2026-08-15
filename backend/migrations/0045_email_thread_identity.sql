-- 0045 — Account Path Slice 4 §14.8: email message identity, thread identity, and the association
-- gate that stands between a low-confidence email and account state.
--
-- Three things get columns here, and each one is a fact the app cannot recompute later:
--
--   * **Thread identity.** `thread_id` is the root of the message's `References` header. Subject
--     is NOT an identity — two unrelated "Re: Quick question" messages are not one conversation,
--     and a subject-keyed thread would merge them and then attribute one account's material to
--     another. See `app/email_thread.thread_key`.
--   * **The new-text hash.** An email reply carries the whole conversation below it. The extractor
--     reads only what this message added, and `new_text_hash` is the hash of exactly that — it is
--     what gives the run its §6.6 source-version identity. Hashing the raw body instead would make
--     every reply in a thread unique material and re-propose the whole history each time.
--   * **The association decision.** `confidence` already recorded how sure the resolver was.
--     Nothing recorded whether a human had *agreed*, so there was no way to express §14.8's rule
--     that a low-confidence association cannot change account state. `association_confirmed_at`
--     and `association_confirmed_by` are that agreement.
--
-- No proposal payload lands here. Proposals drafted from an email are rows in
-- `extraction_proposals` like every other proposal (RR §6.1) — this table stays the lightweight
-- comm record it has been since 0015.

ALTER TABLE comm_messages ADD COLUMN message_id             TEXT;
ALTER TABLE comm_messages ADD COLUMN thread_id              TEXT;
ALTER TABLE comm_messages ADD COLUMN in_reply_to            TEXT;
ALTER TABLE comm_messages ADD COLUMN cc_addrs               TEXT;
ALTER TABLE comm_messages ADD COLUMN attachments            TEXT;
ALTER TABLE comm_messages ADD COLUMN new_text_hash          TEXT;
ALTER TABLE comm_messages ADD COLUMN quoted_chars           INTEGER NOT NULL DEFAULT 0;
ALTER TABLE comm_messages ADD COLUMN association_confirmed_at TEXT;
ALTER TABLE comm_messages ADD COLUMN association_confirmed_by TEXT;
ALTER TABLE comm_messages ADD COLUMN extraction_run_id      TEXT REFERENCES extraction_runs(id);

CREATE INDEX idx_comm_thread ON comm_messages(thread_id, occurred_at);

-- One extraction per distinct new text within a thread. A reply that quotes an earlier message
-- verbatim and adds nothing has the same new text as … nothing, and is skipped before it gets
-- here; two messages that genuinely say the same new thing in one thread are the case this index
-- catches. Partial, because a message with no resolved thread or no extracted text has neither.
CREATE UNIQUE INDEX idx_comm_thread_newtext ON comm_messages(thread_id, new_text_hash)
    WHERE thread_id IS NOT NULL AND new_text_hash IS NOT NULL;
