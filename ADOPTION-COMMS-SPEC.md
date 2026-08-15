# Valence OS — Adoption Comms, Sessions, and Attendance Spec
### Planned waves and privacy-safe session engagement
*v2 · August 2026 · **accepted as Stage 13 authority** (Zach, 2026-08-02, D-108) · additive after Stage 12*

**What changed after adversarial review.** The product boundary survived, but the original schema did
not. This accepted version makes sequence lifecycle fully derived, separates planned and actual send
facts, prevents cyclic or duplicate wave ordering, and distinguishes audience attendees from
facilitators before computing a cohort rollup. It also makes the invitation wave mandatory for an
attendance calculation and names the export/search/audit surfaces the first draft omitted.

Authority it is additive to: `ADOPTION-CAMPAIGN-SPEC.md` (Stage 11), `PHASE-3-SPEC.md`,
`EXPANSION-ENGINE-SPEC.md`. Binding as always: `CLAUDE.md` trust boundaries, mock-only data, and the
standing no-auto-send rule.

---

## 0. Decision and boundary

Stage 11 built the campaign as an orchestration and measurement spine: a cohort, a diagnosed
barrier, an ordered intervention assembled from records that already exist, and an honest readout.
It deliberately did not clone the records it links to.

One of those linked records never got built out. `comms_entries` has not been touched since
migration 0004 and still carries a single free-text `audience`, a `sender`, and a `send_date`. So
the thing an adoption launch actually *is* — a sequence of sends to successive slices of a cohort,
with sessions attached and attendance measured against who was invited — has no representation. The
campaign can point at a comms entry; it cannot describe a wave.

This stage closes that gap and nothing else. Three pieces:

1. **waves and sequences** on the existing comms layer, with audience moved onto the population model;
2. **sessions** — webinar and office hours as first-class calendar purposes;
3. **cohort attendance**, measured against invited, under the privacy floor.

**The boundary, stated once.** This stage adds planning and measurement. It adds no capability to
send anything, and no adapter changes. Every gate in `CONNECTIONS.md` stays exactly where it is.

---

## 1. What a wave is, and who owns it

**A wave is a `comms_entry`.** Not a new object. A wave is one message, to one audience slice,
through one channel, on one date — which is precisely what a comms entry already is.

What is missing is the thing that holds waves together, so the stage adds exactly one table:
`comms_sequences`. A sequence is a named, program-scoped plan; a comms entry may belong to one.

**Waves live in the comms layer, not in the campaign.** This is the load-bearing decision. A
campaign links to a comms entry today (`adoption_campaign_plan_links.comms_entry_id`); if waves
became campaign-owned, a moment-driven wave and a campaign-driven wave would stop being the same
object, and the module would have cloned the very thing Stage 11 refused to clone. A sequence can
be reached from a deployment moment, from a campaign, or from neither, and it is the same sequence
in all three cases.

**A standalone comms entry stays valid.** `sequence_id` is nullable. Nothing existing has to be
migrated into a sequence to keep working — the one-off "send the launch note" entry is a sequence of
one that never needed a parent.

---

## 2. Audience: from free text to the population model

`comms_entries.audience` is a string. That is why cohort attendance cannot exist: there is nothing
to roll a count up *to*.

The stage adds `segment_id` and `view_id`, following the pattern the whitespace map, value targets,
and campaigns all already use — at most one of the two, never both.

**`audience` stays, and stays useful.** Not every send targets a modeled cohort; "everyone who
joined the December kickoff" is a legitimate audience and a bad segment. So the population columns
are nullable and the free-text label remains. The consequence is stated plainly rather than hidden:
**the attendance rollup in §5 is available exactly when the audience is a modeled cohort, and
absent — not zero, not estimated — when it is not.**

**Cross-scope guard.** `comms_entries` is program-scoped; `population_segments` and
`population_views` are account-scoped. A population must belong to the program's account. This is
the recurring defect class in this repository — look a row up by id, then trust the caller about
where it belongs — so it is enforced by trigger, with the API check as the readable error, exactly
as migration 0031 does for campaigns.

---

## 3. Sequences without automation

**"Follow-up sequence" here does not mean what it means in a marketing tool.** In every comparable
product that phrase names a scheduler that fires. Here it names a *plan*: waves in order, with
derived expectations, that a person executes. No code path introduced by this stage sends anything,
schedules anything to be sent, or transitions a wave to `sent` without an operator saying so.

This is the single most likely place in the whole system for the no-auto-send rule to erode, because
the vocabulary invites it. It is therefore a tested invariant, not a convention (§9).

**Wave ordering and dates.** A comms entry gains `wave_number`, `follows_entry_id`, `offset_days`,
and `sent_at`. The existing `send_date` remains the explicitly planned date for backwards
compatibility; `sent_at` is the operator-recorded UTC fact. Where a wave follows another, its
expected send date is **derived** from the predecessor's actual `sent_at` plus the offset — never
stored, never back-filled. Until the predecessor is sent, the successor's date is provisional and
derives from the predecessor's current expected date. A sequence cannot contain a cycle or two live
waves with the same number.

**Sent is an explicit, immutable transition.** A generic patch cannot make a wave sent. The
dedicated operator action records `sent_at` and changes status in one audited transaction. Once
sent, message, audience, channel, sender, population, sequence, and ordering fields are historical
facts and cannot be edited; correction is a new superseding wave, never a rewrite.

**Sequence status is derived.** It is not stored. A cancelled sequence has a reasoned
`cancelled_at` fact; otherwise it is `complete` when every live wave is sent or cancelled,
`running` once at least one is sent, and `planned` before that. This removes the first draft's
contradiction between a stored status column and a service-described derived status.

This is the ask-calendar pattern from `EXPANSION-ENGINE-SPEC.md` §4, which already back-schedules a
chain of steps from a target date. Same discipline, opposite direction: the ask calendar schedules
backwards from a deadline, a comms sequence schedules forwards from a send. Reusing the shape means
one mental model, not two.

**Attention.** An overdue sequence raises **one** item, not one per wave. This is the Stage 11.1
lesson (D-101) applied directly: a campaign raising an item per child double-counted the same work
and trained the operator to skim the queue. A sequence with four late waves is one problem.

---

## 4. Sessions: webinar and office hours

`calendar_events.purpose` is currently `kickoff | governance | qbr | deployment_moment | other`. A
webinar and an office-hours session both land in `other`, which is why neither can be counted.

The stage adds `webinar` and `office_hours` to the CHECK.

**And it flags the pattern rather than repeating it.** D-106 replaced `generated_documents.kind`
with a governed `document_kinds` lookup table precisely because that CHECK had been rebuilt
repeatedly by successive stages. This is the first extension of `calendar_events.purpose`, so a
CHECK rebuild is still the proportionate move — but the rule from D-106 carries: **if a third stage
needs another purpose, replace the CHECK with a lookup rather than rebuilding it again.** Written
down here so the next session inherits the trigger condition instead of rediscovering it.

A session links to its sequence and, optionally, to the wave that invited people to it. A webinar
or office-hours event may exist without an invitation wave, but its cohort attendance is then
**unavailable**, not guessed from another wave in the sequence.

---

## 5. Attendance as a cohort measure

`calendar_event_attendees` already carries what is needed: a row per attendee with
`response_status` and `attendance_status` (`invited | attended | no_show | unknown`). Per-person
attendance is already computed in `cadence.py` and `people_analytics.py`.

What does not exist is the cohort rollup: *of the audience members invited from this cohort, how
many came?* The event's invitation wave supplies the cohort identity. It is not inferred from the
sequence because different waves may target different slices.

`calendar_event_attendees` therefore gains one factual classification:
`attendance_scope = audience | facilitator | observer | unknown`. Existing rows backfill to
`unknown`, not `audience`. Only explicit `audience` rows enter the denominator; facilitators and
observers do not, and an unknown classification makes the rollup incomplete rather than silently
counting an internal presenter as part of the cohort.

### 5.1 The trust boundary, restated

Attendance is **deployment engagement** — meetings, comms, advocacy — which `CLAUDE.md` §2
explicitly permits. It is **not product usage**. No table, column, or field introduced by this stage
may record whether a named individual used Nadia, and the attendance rollup may never be joined to
usage data. The existing test asserting no individual-usage field anywhere must still pass
unchanged.

### 5.2 The privacy floor, and why the existing helper is not enough on its own

The rollup reuses `expansion.cohort_suppression_reason` rather than growing a second floor. But that
helper alone is insufficient here, for two reasons that only bite when the number is derived from a
list of named people:

**Unknown headcount currently reads as safe.** `cohort_suppression_reason` returns `None` when the
population's headcount is `NULL`. That is defensible for a metric observation, where an absent
headcount means the floor cannot be evaluated. It is wrong for a count derived from named
individuals: "we cannot prove this is safe" must not render as "this is safe." **For attendance, an
unknown cohort size suppresses.**

**The floor must apply to the displayed denominator, not the nominal cohort.** A segment of 400
people may have had 3 attendees invited to a session. "1 of 3 attended" identifies individuals
regardless of how large the segment nominally is. **The invited count is itself subject to the
floor.**

So the rule is: suppress when the cohort is below the floor, **or** the cohort size is unknown,
**or** the explicit audience invited count for this session is below the floor. Suppress — never
zero, never rounded, never "<5". If any attendee remains `attendance_scope=unknown`, the result is
`incomplete` and does not render a rate.

### 5.3 Freshness

A session in the future has no attendance. It renders **unknown**, never `0 attended`, under the
same freshness language every other dated record uses. A past session whose attendance was never
recorded is also unknown — not zero. Nothing here may render an absence of data as a bad outcome.

### 5.4 Visibility

Attendance is internal by default, like every other operational interpretation. It reaches a
client-facing artifact only through the existing affirmative-promotion path, enforced in the
generator, not by convention.

---

## 6. Information architecture

No new top-level destination. Navigation stays Today / Accounts / Library / Operations.

- **Sequences and waves** render in the existing program **Comms** panel — that is where comms
  entries already live.
- **The campaign Plan tab** shows a linked wave with its state *derived from the comms entry*, never
  stored on the campaign. This is the Stage 11 §4.1 rule and it is not relaxed: the campaign must
  not be able to disagree with the Comms panel.
- **Attendance** renders on the session and on the sequence, with the suppression treatment where
  the floor applies and the cross-hatched unknown treatment where evidence is missing.
- **Both themes are first-class**, per `DESIGN-GUIDE.md`. Status uses a shape or a label as well as
  a colour.

---

## 7. Proposed schema

Sketch, not final DDL. One new table; two altered.

```sql
CREATE TABLE comms_sequences (
    id           TEXT PRIMARY KEY,
    program_id   TEXT NOT NULL REFERENCES programs(id),
    name         TEXT NOT NULL,
    purpose      TEXT,                         -- why this sequence exists, plain language
    moment_id    TEXT REFERENCES deployment_moments(id),
    cancelled_at TEXT,
    cancellation_reason TEXT,
    created_at   TEXT NOT NULL, updated_at TEXT NOT NULL,
    archived     INTEGER NOT NULL DEFAULT 0, archived_at TEXT, archived_by TEXT
);

ALTER TABLE comms_entries ADD COLUMN sequence_id      TEXT REFERENCES comms_sequences(id);
ALTER TABLE comms_entries ADD COLUMN wave_number      INTEGER;
ALTER TABLE comms_entries ADD COLUMN follows_entry_id TEXT REFERENCES comms_entries(id);
ALTER TABLE comms_entries ADD COLUMN offset_days      INTEGER;
ALTER TABLE comms_entries ADD COLUMN segment_id       TEXT REFERENCES population_segments(id);
ALTER TABLE comms_entries ADD COLUMN view_id          TEXT REFERENCES population_views(id);
ALTER TABLE comms_entries ADD COLUMN sent_at           TEXT;   -- UTC fact, explicit operator action

-- calendar_events.purpose CHECK rebuilt to add 'webinar' and 'office_hours' (§4).
ALTER TABLE calendar_events ADD COLUMN comms_sequence_id TEXT REFERENCES comms_sequences(id);
ALTER TABLE calendar_events ADD COLUMN invited_by_entry_id TEXT REFERENCES comms_entries(id);
ALTER TABLE calendar_event_attendees ADD COLUMN attendance_scope TEXT NOT NULL DEFAULT 'unknown'
    CHECK (attendance_scope IN ('audience','facilitator','observer','unknown'));
```

Triggers, expressing what single-column FKs cannot:

- a wave's population must belong to the program's account;
- `follows_entry_id` must reference a wave in the same sequence;
- a wave chain may not cycle and live `wave_number` values are unique within a sequence;
- at most one of `segment_id` / `view_id`;
- a sequence's moment must belong to the same program.
- a session's sequence and invitation wave must agree with its account/program scope.

Service contract: `comms.sequence(conn, id)` returns waves in order with **derived** expected dates
and derived status; `comms.attendance(conn, sequence_id | event_id)` returns
`{state, invited, attended, no_show, unknown, suppression_reason}` where state is
`known | unknown | incomplete | suppressed`; any state other than `known` withholds a rate, and a
non-null `suppression_reason` means every count is `None`.

The first slice also updates audit, account export/restore, search, and Operations counts. A new
operational object is not complete while those generic surfaces silently omit it.

---

## 8. Build order

**13.0 — waves.** `comms_sequences`, the `comms_entries` columns, triggers, derived dates, the
service, the Comms panel, and the campaign Plan tab reading derived wave state.

**13.1 — sessions and attendance.** The purpose CHECK rebuild, session links, the attendance rollup
with the three-part floor from §5.2, freshness treatment, and the UI.

**13.2 — attention and closeout.** One Today item per overdue sequence, seed data, both-theme
screenshots, and the adversarial pass in §9.

Each sub-stage lands with tests, a decision entry, and a HANDOFF update before the next begins.

---

## 9. Definition of done and required adversarial tests

On a synthetic account, without leaving the tool, the operator can plan a multi-wave launch against
a modeled cohort, attach a webinar and an office-hours session, record what was actually sent and
who actually came, and see attendance against invited without a causal claim or a privacy leak.

Required adversarial cases:

- a wave whose population belongs to another account is rejected, at both the API and the trigger;
- **no code path introduced by this stage sends anything** — asserted the same way the existing
  no-auto-send tests are, and extended to cover sequence advance;
- a wave cannot transition to `sent` except by an explicit operator action recording `sent_on`;
- a wave following an unsent predecessor renders a **provisional** date, labelled as such, and that
  date changes when the predecessor's actual send date changes;
- `follows_entry_id` pointing at a wave in another sequence is rejected;
- cyclic predecessor chains and duplicate live wave numbers are rejected;
- a cohort **below the floor** suppresses attendance rather than showing `0`;
- a cohort with **unknown headcount** suppresses (§5.2 — the case the existing helper permits);
- an **invited count below the floor** suppresses even when the segment is large;
- a **future session** renders attendance as unknown, never `0 attended`;
- a past session with no recorded attendance renders unknown, never `0`;
- a facilitator is excluded from the cohort denominator and any unclassified attendee makes the
  rollup incomplete rather than being silently counted;
- no schema, API, UI, export, search, or generated text gains a named-individual product-usage
  field — the existing assertion still passes;
- attendance cannot be joined to product usage anywhere;
- an **overdue sequence raises one Today item**, not one per wave, and does not duplicate the items
  its linked tasks already raise;
- a **sent** wave cannot be edited into a different message or audience after the fact — what was
  sent is a historical fact;
- client-facing artifacts contain no wave-level audience tactics unless affirmatively promoted;
- the campaign Plan tab's wave state always equals the comms entry's, because it is derived.

---

## 10. Explicit non-goals

- **Sending.** No email, calendar, or messaging write path. `CONNECTIONS.md` is unchanged.
- **Per-person open, click, or read tracking.** Declined outright. It is not product usage, so it
  would not violate the letter of §2 — but it is the same shape of individual surveillance the trust
  boundaries exist to prevent, and a works council would read it the same way. Attendance is a
  meeting someone chose to join; an open pixel is not.
- **A/B testing or variant analysis.** The cohorts are too small for a difference to mean anything,
  and the honest-measurement rules in `ADOPTION-CAMPAIGN-SPEC.md` §5 would have to be restated for a
  second surface.
- **A template engine.** The role-based messaging library from Stage 5 already exists; a wave
  references it rather than growing a parallel one.
- **Auto-scheduling or auto-advance.** A sequence never moves itself forward.
- **Promoting sequences into plays.** Same reasoning as `ADOPTION-CAMPAIGN-SPEC.md` §8: the evidence
  that a repeatable wave pattern exists has to come first.
