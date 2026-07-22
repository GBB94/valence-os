# Field dictionary — v0 only

Every field v0 needs, and only v0. Fields whose *object* is deferred (contracts, opportunities, metrics, plays, gates, moments) are not listed. Fields that belong to a v0 object but a later slice (e.g. stakeholder influence for the v3 graph) are called out inline as deferred, not silently added.

Conventions:
- **Type** `uuid` = primary key; `datetime` = UTC timestamp; `date` = calendar date, no time (contractual/all-day); `enum(...)` = closed set; `FK→X` = foreign key; `text` = free text.
- **Req** = required at create time. Optional fields may be filled during later triage.
- Every operational object also carries the **standard soft-delete + audit columns** listed once in §0 rather than repeated per table.
- `created_at` is capture time (when the row was made); it is distinct from any domain date (e.g. an interaction's `occurred_on`).

Slice legend: **[0.1]** capture · **[0.2]** execution · **[0.3]** attention · **[0.4]** output.

---

## 0. Standard columns (every operational object)

| Field | Type | Req | Default | Notes |
|---|---|---|---|---|
| id | uuid | yes | generated | |
| created_at | datetime | yes | now() | UTC |
| updated_at | datetime | yes | now() | UTC, bumped on write |
| archived | boolean | yes | false | soft-delete / archival (CLAUDE.md) |
| archived_at | datetime | no | null | set when archived |
| archived_by | FK→Person | no | null | actor |

Audit is a separate append-only table (§14), not columns.

---

## 1. Account  **[0.1 / statuses 0.3]**

| Field | Type | Req | Default | Notes |
|---|---|---|---|---|
| name | text | yes | — | enterprise name (mock only) |
| short_context | text | no | null | one-line description |
| incumbent_note | text | no | null | free-text incumbent/L&D-budget note. **Structured incumbent (holder, contract timing, displacement status) deferred to v1.** |
| delivery_status | enum(on_track, at_risk, off_track, unknown) | yes | unknown | value judgment *(enum proposed — see PA-1)* **[0.3]** |
| delivery_status_rationale | text | no | null | why **[0.3]** |
| delivery_status_assessed_on | date | no | null | drives 30-day stale-assessment warning **[0.3]** |
| delivery_status_change_condition | text | no | null | what would change it **[0.3]** |
| commercial_status | enum(on_track, at_risk, off_track, unknown) | yes | unknown | *(enum proposed — see PA-1)* **[0.3]** |
| commercial_status_rationale | text | no | null | **[0.3]** |
| commercial_status_assessed_on | date | no | null | **[0.3]** |
| commercial_status_change_condition | text | no | null | **[0.3]** |

Derived (not stored, not editable): `last_touch` = max(interaction.occurred_on) across the account's programs.

---

## 2. Program  **[0.1]**

| Field | Type | Req | Default | Notes |
|---|---|---|---|---|
| account_id | FK→Account | yes | — | |
| name | text | yes | — | |
| phase | enum(foundation, launch, programmatic, expansion, renewal, closed) | yes | foundation | |
| region | text | no | null | attribute, not hierarchy |
| audience | text | no | null | attribute |
| use_case | text | no | null | attribute |
| problem_statement | text | no | null | |
| in_scope_population | text | no | null | |
| out_of_scope_population | text | no | null | |
| launch_definition | text | no | null | what "launched" means |
| success_criteria | text | no | null | |
| expansion_hypothesis | text | no | null | e.g. "grow ~1,000 → ~3,000 seats if value proven" (holds the AGCO-style expansion in v0 — see G1) |
| explicit_exclusions | text | no | null | |
| sponsor_person_id | FK→Person | no | null | |

Deferred to v1 (named in Section 4 under Program, not v0): governance cadence (steering forum, working rhythm, QBR dates), phase gates, scope-change entries.
Derived: `last_touch`, `next_milestone` (earliest incomplete milestone by target_date), `top_risk` (most recent open risk).

---

## 3. Person  **[0.1]**

| Field | Type | Req | Default | Notes |
|---|---|---|---|---|
| name | text | yes | — | mock only |
| affiliation | enum(client, valence) | yes | client | separates client people from Valence internal owners *(PA-2)* |
| account_id | FK→Account | no | null | set for client people; null for Valence internal |
| title | text | no | null | job title at their org |
| email | text | no | null | optional contact |

Note: a Person's role and stance are **not** here — they live per-program on StakeholderRole.

---

## 4. StakeholderRole (Person × Program)  **[0.1]**

| Field | Type | Req | Default | Notes |
|---|---|---|---|---|
| program_id | FK→Program | yes | — | |
| person_id | FK→Person | yes | — | |
| role | enum(champion, budget_owner, program_owner, it, legal_dpo, works_council_contact, other) | yes | other | |
| stance | enum(supporter, skeptic, unconverted) | no | null | if set, date + evidence required (Section 2) |
| stance_assessed_on | date | cond | null | **required when stance set** |
| stance_evidence_note | text | cond | null | **required when stance set** |
| cares_about | text | no | null | what this person cares about |
| value_for_them | text | no | null | what the product does for them |

Deferred to v3 (graph encodings, named in Section 2/6): `influence`, `relationship_strength`. Not captured in v0.
Derived: `days_since_touch` = today − max(occurred_on of interactions this person attended).

---

## 5. Interaction  **[0.1]**

| Field | Type | Req | Default | Notes |
|---|---|---|---|---|
| program_id | FK→Program | yes | — | account derived via program (see G2 re account-level interactions) |
| occurred_on | date | yes | today | interaction date |
| occurred_at_time | text | no | null | optional time note; client tz preserved as text in v0 |
| type | enum(call, meeting, email, workshop, message, other) | yes | meeting | |
| summary | text | no | null | short "what moved" |
| raw_notes | text | no | null | internal-only by default (Section 2) |
| source_reference_id | FK→SourceReference | no | null | transcript/recording link (link-first) |
| follow_up | text | no | null | free-text follow-up note |
| meaningful_touch | boolean | yes | true | feeds coverage + last-touch |

Participants: join table `interaction_participant(interaction_id, person_id)`. **[0.1]**

---

## 6. CaptureInboxItem  **[0.1 create / 0.2 convert]**

| Field | Type | Req | Default | Notes |
|---|---|---|---|---|
| interaction_id | FK→Interaction | yes | — | attached to the interaction it came from |
| raw_text | text | yes | — | the untriaged note |
| status | enum(untriaged, converted, dismissed) | yes | untriaged | |
| converted_to_type | enum(task, commitment, decision, risk, issue) | no | null | set on convert **[0.2]** |
| converted_to_id | uuid | no | null | id of created object **[0.2]** |
| resolved_on | date | no | null | convert/dismiss date |
| resolved_by | FK→Person | no | null | |

Conversion never retypes: the create form for the target object is pre-filled from `raw_text`. Untriaged items appear in the attention queue until resolved.

---

## 7. Task  **[0.2]**

| Field | Type | Req | Default | Notes |
|---|---|---|---|---|
| program_id | FK→Program | yes | — | |
| description | text | yes | — | |
| internal_owner_id | FK→Person | no | null | Valence owner |
| due_date | date | no | null | end-of-day semantics |
| status | enum(open, done, cancelled) | yes | open | done when deliverable exists |
| closed_on | date | no | null | |
| closed_by | FK→Person | no | null | |
| close_note | text | no | null | |
| source_interaction_id | FK→Interaction | no | null | |
| source_reference_id | FK→SourceReference | no | null | |

---

## 8. Commitment  **[0.2]**

| Field | Type | Req | Default | Notes |
|---|---|---|---|---|
| program_id | FK→Program | yes | — | |
| description | text | yes | — | |
| responsible_party_id | FK→Person | yes | — | who performs it (often client) |
| internal_owner_id | FK→Person | yes | — | Valence follow-up owner (success criterion: never null) |
| due_date | date | yes | — | success criterion: 100% have a due date |
| status | enum(open, closed) | yes | open | closes on receiving-party acknowledgement |
| acknowledged_by_id | FK→Person | no | null | the receiving party who acknowledged |
| closed_on | date | no | null | |
| closed_by | FK→Person | no | null | |
| close_note | text | no | null | |
| source_interaction_id | FK→Interaction | no | null | |
| source_reference_id | FK→SourceReference | no | null | |

Derived: `overdue` = status=open AND due_date < today.

---

## 9. Decision  **[0.2]**

| Field | Type | Req | Default | Notes |
|---|---|---|---|---|
| program_id | FK→Program | yes | — | |
| description | text | yes | — | what was decided |
| decided_on | date | no | today | |
| decided_by_id | FK→Person | no | null | person/forum |
| rationale | text | no | null | |
| supersedes_id | FK→Decision | no | null | records revision without deleting |
| status | enum(recorded, superseded) | yes | recorded | decisions are a log, not an open/close lifecycle |
| source_interaction_id | FK→Interaction | no | null | |
| source_reference_id | FK→SourceReference | no | null | |

---

## 10. Risk  **[0.2]**

| Field | Type | Req | Default | Notes |
|---|---|---|---|---|
| program_id | FK→Program | yes | — | |
| description | text | yes | — | |
| severity | enum(low, medium, high) | no | medium | optional; not a benchmark |
| is_blocker | boolean | yes | false | active blocker → high queue priority |
| mitigation | text | no | null | note: mitigation ≠ closure |
| status | enum(open, closed) | yes | open | closes only when no longer possible/relevant |
| close_reason | enum(no_longer_possible, no_longer_relevant) | no | null | required on close |
| closed_on | date | no | null | |
| closed_by | FK→Person | no | null | |
| close_note | text | no | null | |
| internal_owner_id | FK→Person | no | null | |
| source_interaction_id | FK→Interaction | no | null | |
| source_reference_id | FK→SourceReference | no | null | |

---

## 11. Issue  **[0.2]**

| Field | Type | Req | Default | Notes |
|---|---|---|---|---|
| program_id | FK→Program | yes | — | |
| description | text | yes | — | the condition |
| is_blocker | boolean | yes | false | active blocker → high queue priority |
| status | enum(open, resolved) | yes | open | |
| resolution_type | enum(condition_removed, workaround_operating) | no | null | required on resolve |
| resolved_on | date | no | null | |
| resolved_by | FK→Person | no | null | |
| resolution_note | text | no | null | |
| internal_owner_id | FK→Person | no | null | |
| source_interaction_id | FK→Interaction | no | null | |
| source_reference_id | FK→SourceReference | no | null | |

---

## 12. Milestone  **[0.2]**

| Field | Type | Req | Default | Notes |
|---|---|---|---|---|
| program_id | FK→Program | yes | — | |
| name | text | yes | — | |
| target_date | date | no | null | |
| success_criteria | text | no | null | completes when met |
| at_risk | boolean | yes | false | manual flag; queue also derives at-risk from overdue target |
| status | enum(upcoming, complete) | yes | upcoming | |
| completed_on | date | no | null | |
| completed_by | FK→Person | no | null | |
| completion_note | text | no | null | |
| source_interaction_id | FK→Interaction | no | null | |

---

## 13. SourceReference  **[0.1]**

| Field | Type | Req | Default | Notes |
|---|---|---|---|---|
| type | enum(file, transcript_span, meeting, crm_record, data_report, manual_entry) | yes | manual_entry | |
| label | text | yes | — | human description |
| url | text | no | null | link-first pointer |
| locator | text | no | null | span/page/timestamp within the source |

Reusable: one SourceReference may be cited by many interactions/commitments/decisions.

---

## 14. Infrastructure (present from v0, not user-authored domain objects)

### AttentionState (snooze/resolve overlay)  **[0.3]**
Queue items are *derived* every render (see `attention-rules.md`); only the operator's overlay is stored.

| Field | Type | Req | Default | Notes |
|---|---|---|---|---|
| id | uuid | yes | generated | |
| item_key | text | yes | — | stable key: `trigger_type:object_type:object_id` |
| state | enum(snoozed, resolved) | yes | — | active items have no row |
| snooze_until | date | cond | null | required if snoozed and no condition |
| resurface_condition | text | cond | null | required if snoozed and no date |
| successor_action_type | enum(task, commitment) | no | null | resolve-with-successor path |
| successor_action_id | uuid | no | null | |
| created_at | datetime | yes | now() | |
| created_by | FK→Person | yes | — | |

Resolving requires either the underlying object is closed **or** a successor action is linked. Snoozing requires `snooze_until` **or** `resurface_condition`.

### AuditEvent (append-only)  **[0.1]**

| Field | Type | Req | Default | Notes |
|---|---|---|---|---|
| id | uuid | yes | generated | |
| occurred_at | datetime | yes | now() | UTC |
| actor_id | FK→Person | yes | — | operator (single editor in v0) |
| object_type | text | yes | — | |
| object_id | uuid | yes | — | |
| action | enum(create, update, archive, convert, close) | yes | — | |
| before | text (json) | no | null | |
| after | text (json) | no | null | |
| source | enum(user) | yes | user | import/ai sources arrive v2/v4 |

---

## Proposed additions (doc is silent — flagged, not silently added)

- **PA-1 — Status enumerations.** The doc mandates delivery + commercial statuses "manually judged" but never enumerates their values. Proposed: `{on_track, at_risk, off_track, unknown}`, mapping to the Section 6 semantic status colors, with `unknown` as the honest default before first assessment. *Confirm the value set.*
- **PA-2 — `Person.affiliation` (client | valence).** Needed so a commitment's internal owner is a real Person without inventing a second "user" object. Smallest thing that keeps commitments' two-owner rule working. *Confirm.*
- **PA-3 — `Risk.is_blocker` / `Issue.is_blocker` boolean.** Module A ranks "active blockers" as a top attention source, but no object is named "blocker." Proposal: a blocker is a risk or issue flagged `is_blocker`, avoiding a new object type. *Confirm this is the intended representation.*
- **PA-4 — `Milestone.at_risk` boolean.** Queue trigger "at-risk upcoming milestones" needs a signal. Proposed: manual `at_risk` flag OR derived (incomplete past target_date). *Confirm manual+derived is acceptable.*
- **PA-5 — `Interaction.type` / task/decision/risk/issue not having a severity taxonomy.** Kept deliberately thin per the 30-second rule; noting so their thinness is a choice, not an omission.

See `../decisions.md` for the rationale trail and `README`-level gaps G1–G6 in `walkthroughs.md`.
