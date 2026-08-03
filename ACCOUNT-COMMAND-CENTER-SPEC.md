# Valence OS account command center and unified activity specification

**Status:** Release 2 Slices 2.0–2.4 implemented, 2026-08-03

**Parent authority:** `UX-FOUNDATION-SPEC.md`

**Related authorities:** `DESIGN-GUIDE.md`, `ACCOUNT-COPILOT-SPEC.md`, `INTERNAL-OPS-SPEC.md`, `COMPANY-INTEL-SPEC.md`

**Scope:** The account Overview command center, its Operate/Prepare/Leadership lenses, the unified account-activity read model, and account change checkpoints.

## 1. Decision

The account Overview becomes one command center with three switchable lenses:

- **Operate** is the default for a new operator. It answers what changed, what needs attention, and what happens next.
- **Prepare** organizes the account around an upcoming meeting and produces a source-grounded preparation workflow.
- **Leadership** organizes the same account facts around health, forecast, movement, risk, and explicit asks.

The lenses are not separate dashboards and do not own separate facts. They are presentations over one account-orientation response and one typed activity projection. The projection reads canonical records and append-only domain events; it does not become a second event source of truth. If query cost later requires an index, that index remains a rebuildable projection.

The UI labels the third lens **Leadership**, rather than the ambiguous **Review**, because the same screen also contains the distinct action “Mark changes reviewed.”

## 2. Outcomes

Within ten seconds of opening an account, the operator can:

1. Tell whether important account state changed since the prior visit or explicit review.
2. See the few decisions, blockers, commitments, and near-term events that deserve action.
3. Switch focus without losing account or program scope or learning a different interaction model.
4. Prepare for a specific meeting from attendees, recent interactions, open threads, and evidence gaps.
5. Give a leadership update framed as what moved, what is stuck, and what is needed.
6. Open the native record behind every summary rather than treating the command center as new truth.
7. Read customer, internal, external, and planned activity on one time axis without confusing recorded time, effective time, and scheduled time.

## 3. Non-goals

- Replacing the eight account workspace tabs in this release.
- Adding a ninth workspace tab. The command center replaces the Overview body.
- Creating a generic customizable dashboard or movable widget system.
- Persisting an all-purpose event stream as canonical truth.
- Computing a composite account-health score.
- Auto-generating or auto-sending a brief when a lens opens.
- Treating a proposed company-intelligence event as confirmed account fact.
- Adding real calendar, email, CRM, or LLM connections.
- Moving Objectives, corporate hierarchy, or Growth Thesis into Release 2.

## 4. Shared screen architecture

The sticky account context header remains unchanged and visible in every lens. It continues to own account name, program selector, delivery status, commercial status, renewal, and phase.

Below the existing Overview tab strip, the command center has:

1. A compact title row with the account's short context, lens selector, data-current-through stamp, and global account actions.
2. One active lens panel.
3. A consistent path from every summarized row to its native record or native workspace tab.

The title row preserves **Log interaction**, **Export**, and **New program**. Status summaries continue to open the existing governed status editor. Programs remain reachable from the persistent selector and Plan; people remain reachable from the People tab. Release 2 extracts and reuses these actions before retiring the current `AccountDetail` body, so the redesign cannot silently remove a workflow.

The selector uses the semantic keys `operate`, `prepare`, and `leadership`. It is a real tablist with a single tab stop, Left/Right arrow navigation, Home/End support, `aria-controls`, and a named tabpanel. Changing it writes the URL and does not reload the account context.

### 4.1 Addressability and preference

Account Overview accepts these additive query parameters:

- `program=:programId` — the existing program scope.
- `lens=operate|prepare|leadership` — the active lens.
- `meeting=:calendarEventId` — valid only with `lens=prepare` and only for an event in the current account/program scope.

Examples:

- `/accounts/acc-terravance/overview?lens=operate`
- `/accounts/acc-terravance/overview?program=prog-tv-europe&lens=prepare&meeting=cal-tv-qbr`
- `/accounts/acc-terravance/overview?lens=leadership`

URL state wins over preference state. A lens selection is stored as the operator's browser-local presentation preference, using the same reasoning as theme, density, and saved views. With no `lens` parameter, the saved preference is used; a new or corrupt preference falls back to Operate. Selecting a meeting always writes both `lens=prepare` and `meeting=...`. An invalid or out-of-scope meeting is removed with `replaceState` and Prepare falls back to its unselected state.

### 4.2 Layout rules

- Use a small number of aligned panels and semantic lists/tables, not a grid of KPI tiles.
- The primary question occupies the leading two-thirds of the wide layout; near-term context occupies the remaining third.
- At the existing split-screen breakpoint, each lens becomes one ordered column without hiding content.
- Collapse depth within a section, not the entire answer. Default state shows at most five rows per section and links to the complete native view.
- Loading is per section after the shared orientation response resolves. A failed secondary section does not blank the whole account.
- Empty states distinguish “none,” “not recorded,” “not connected,” “not selected,” and “insufficient evidence.”
- No lens changes record visibility. All three are internal-only account workspaces.

## 5. Lens contracts

### 5.1 Operate — complete first

Operate is the full Release 2 reference implementation and the default for new operators. Its order is:

1. **Since your last review** — material changes recorded after the effective explicit checkpoint, grouped into Decisions, Movement, Risks/blockers, External change, and Completed/closed. The heading exposes the checkpoint date and a scope-specific “Mark changes reviewed” action.
2. **Since your last visit** — a lighter personal recency band. It never clears or advances the explicit review checkpoint.
3. **Needs action** — overdue commitments, open blockers, governed amber/red recovery actions, overdue internal asks, and near-term commitments. Each row states the deterministic trigger reason.
4. **Next on the account** — upcoming calendar events, reviews, deployment moments, milestones, commitments, and contractual dates on one ordered list.
5. **Current point of view** — the latest append-only operator view, its assessed date, and a link to Internal → Reviews. Missing point of view is named as not recorded.

Rules:

- No opaque AI ranking. Section membership and ordering are deterministic and testable.
- The two independent account statuses remain independent; the command center does not derive a roll-up color or score.
- A late-entered interaction appears as new based on when it was recorded, while its activity row remains positioned at the meeting's actual date.
- Marking changes reviewed advances only the visible account/program scope and only to the response's frozen `data_current_through` timestamp, never to the client clock at click time.
- A section can say “No material changes since …” only after all required adapters succeeded. Partial coverage names the omitted sources.

### 5.2 Prepare — implemented

Prepare starts with the next upcoming associated meeting. The operator may select another upcoming or recently completed meeting from the account calendar. With no meeting selected or available, it shows a meeting selector and an explicit no-associated-meeting state; it does not fabricate an agenda.

For a selected meeting, the order is:

1. **Meeting identity** — title, time, purpose, program, location, organizer, and association confidence where applicable.
2. **Attendees** — known people first, with professional role/layer, stance freshness, last meaningful touch, and response status. Unknown invitees remain unknown and are never silently matched.
3. **What changed since the last meaningful interaction with these attendees** — activity projection filtered to attendee context where the underlying record supports that relationship.
4. **Open threads** — commitments, decisions needed, blockers, relevant internal asks, and recent customer follow-up.
5. **Evidence gaps** — stale, missing, conflicted, or insufficient inputs that would weaken the conversation.
6. **Suggested preparation actions** — explicit buttons to log an interaction, open the existing deterministic pre-call brief, or open Copilot with a meeting-preparation intent. Nothing runs automatically.

The implemented version filters recent context to attendee relationships supported by the native record, excludes the baseline last-touch interaction, names partial activity coverage, and falls back to an explicit evidence gap when a relationship cannot be established. Meeting selection and brief preview are reads: opening Prepare never creates a document, sends a brief, or mutates canonical records.

### 5.3 Leadership — implemented

Leadership presents the same facts as an internal review, not a second forecast system. Its order is:

1. **Where the account stands** — delivery and commercial status with rationale, assessed date, recovery action, recovery owner, and leadership response where governed.
2. **What moved** — forecast transitions, decisions, meaningful interactions, closed blockers, completed milestones, and confirmed external changes in the selected window.
3. **What is stuck** — open blockers, overdue commitments, overdue asks, at-risk milestones, and evidence gaps.
4. **What I need** — active internal asks and escalations with owner/function, needed-by date, state, and explicit next action.
5. **Near-term commitments** — the next account review, renewal/notice dates, material meetings, and commitments.
6. **Point of view and review trail** — latest operator view and account-review provenance, with links to Internal rather than duplicated editing controls.

The implemented version uses an explicit internal source allowlist. Governed statuses, forecast, asks/escalations, contract dates, point of view, and account reviews remain visibly account-wide; movement, blockers, milestones, meetings, and commitments obey the selected program scope while retaining direct account records. Missing or unsupported inputs become named evidence gaps. Opening Leadership and drafting through Copilot are explicit, separate actions; opening the lens performs no write and creates or sends no update.

## 6. Unified activity read model

### 6.1 Architecture

Add a backend `account_activity` service whose adapters normalize existing source records into a typed projection. The projection is query-time and rebuildable:

```text
canonical records + append-only domain events + verified audit transitions
                              ↓
                    ActivityItem adapters
                              ↓
             filter · group · paginate · summarize
                              ↓
             command center and Activity consumers
```

The projection must not write an event merely because it was read. If scale becomes a measured problem, a materialized table may cache the exact projection contract, but it must be fully regenerable and never accepted as an input to a native write flow.

### 6.2 `ActivityItem` contract

Every item has:

```json
{
  "id": "interaction:int-tv-7:recorded",
  "account_id": "acc-terravance",
  "program_id": "prog-tv-europe",
  "source_type": "interaction",
  "source_id": "int-tv-7",
  "event_kind": "interaction_recorded",
  "stream": "customer",
  "state": "confirmed",
  "title": "Governance working session",
  "summary": "Decision rights and the evidence gap were reviewed.",
  "display_at": "2026-07-29T14:00:00Z",
  "recorded_at": "2026-07-31T09:12:00Z",
  "temporal_kind": "occurred",
  "temporal_precision": "datetime",
  "direction": "past",
  "materiality": "material",
  "status": null,
  "reason": "Meaningful customer interaction recorded",
  "actor": null,
  "owner": null,
  "participants": [],
  "source_reference": null,
  "native_target": {"tab": "ledger", "record_type": "interaction", "record_id": "int-tv-7"}
}
```

Contract rules:

- `display_at` controls chronology. It is the business occurrence, effective, due, or scheduled time. Contractual and due dates remain ISO dates rather than being fabricated into UTC instants.
- `recorded_at` controls “since” comparisons. It is when Valence learned or recorded the event.
- `temporal_kind` is one of `occurred`, `effective`, `recorded`, `scheduled`, or `due`; the UI prints the distinction.
- `temporal_precision` is `date` or `datetime` and must match `display_at`. A source without a timezone does not gain one during normalization.
- `direction` is derived relative to the server's stamped `as_of`, never the browser clock.
- `stream` is one of `customer`, `internal`, `external`, or `unknown`. Planning is temporal state, not a stream: a future customer meeting remains customer activity, not an unrelated fourth category. An interaction without resolvable participants stays unknown rather than being guessed into customer or internal activity.
- `state` is one of `confirmed`, `proposed`, `superseded`, `retracted`, `dismissed`, `invalidated`, or `unknown`. Proposed items are visibly proposed and excluded from confirmed-fact summaries.
- `materiality` is `material` or `context`. It comes from an explicit adapter rule, never a model score.
- `reason` explains why the item appears or why it is material.
- `native_target` resolves to the owning tab/record. The command center does not become the editor of every source type.
- Stable IDs are derived from source type, source ID, and semantic transition. Pagination must not depend on list position.

### 6.3 Initial adapter coverage

The first complete projection includes:

| Source | Activity semantics | Material by default |
|---|---|---|
| Interactions | customer/internal occurrence plus recorded time | meaningful customer touch |
| Decisions | recorded/superseded decision | yes |
| Commitments | created, due, closed | overdue, due soon, or closed |
| Tasks | created, due, done/cancelled | overdue or done |
| Risks and issues | created, blocker, closed/resolved | blocker or high severity |
| Milestones | target, at-risk, completed | at-risk or completed |
| Account status assessments | new governed assessment | changed value, amber, or red |
| Forecast change events | append-only category transition | yes |
| Internal ask events | append-only transition | overdue, delivered, declined, reopened |
| Account reviews | scheduled, held, cancelled | held or due soon |
| Calendar events | scheduled occurrence and attendance facts | within the near-term window |
| Deployment moments | planned business event | within the near-term window |
| Comms entries | planned, operator-recorded sent, cancelled | sent or due soon |
| Company events | observed/occurred external change | confirmed material; proposed is context only |

Contractual renewal and notice dates are exposed in `Next on the account` but remain annotations derived from the current contract version, not synthetic activity history.

Later adapters may add campaign transitions, org-change resolution, signal episodes, generated-document review, and evidence refresh. They cannot be counted as covered until their native account scope and transition history are proven.

### 6.4 Transition truth and audit use

Prefer a source's append-only domain event table when one exists (`forecast_change_events`, `internal_ask_events`, status assessments, immutable company artifacts). Use current canonical rows for native occurrences and future dates. Use `audit_events` only for object types whose writes are demonstrably complete and whose before/after payload can reconstruct the semantic transition.

An `updated_at` timestamp alone is not enough to claim what changed. If a source lacks trustworthy transition history, the projection may show its current snapshot and recorded date, but must not invent a transition such as “risk escalated” or “meeting moved.” Adapter tests list the supported transitions explicitly.

### 6.5 Grouping and deduplication

- A source interaction and records created from it remain distinct facts but render as one expandable activity group.
- A domain event and its audit entry collapse to the domain event; audit is fallback, not a duplicate row.
- Scheduled and completion semantics for the same record use different stable IDs.
- A confirmed company event supersedes its proposed presentation without erasing the review history.
- Corrections, supersessions, and retractions remain visible and point to the corrected record.

### 6.6 API

`GET /api/accounts/{account_id}/activity`

Query parameters:

- `program_id`
- repeatable `stream`
- repeatable `source_type`
- repeatable `event_kind`
- `state`
- `direction=past|future|all`
- `materiality=material|context`
- `recorded_after`
- `display_from`, `display_to`
- `cursor`, `limit` (default 50, maximum 200)

Response:

```json
{
  "stamp": {
    "generated_at": "2026-08-03T15:00:00Z",
    "data_current_through": "2026-08-03T15:00:00Z",
    "as_of": "2026-08-03T15:00:00Z",
    "coverage": ["interaction", "decision", "commitment"],
    "omitted": []
  },
  "items": [],
  "next_cursor": null,
  "facets": {},
  "matched_count": 0
}
```

The stamp also returns `projection_duration_ms` plus one `adapter_metrics` entry per requested adapter with status, item count, and duration. These are read evidence, not persisted telemetry or an SLA. Facets describe the complete scoped projection before active filters, so a filter control cannot disappear merely because it is selected.

Cursor ordering is `(display_at DESC, recorded_at DESC, id DESC)` for past activity and `(display_at ASC, recorded_at ASC, id ASC)` for future activity. Filter validation fails closed with 422. An invalid program or one outside the account returns 422.

## 7. Account orientation read

Add `GET /api/accounts/{account_id}/command-center?program_id=...&recorded_after=...`.

This endpoint is a bounded orchestration read, not a new repository. It returns:

- a frozen stamp and adapter coverage;
- both governed statuses and recovery fields;
- latest operator point of view;
- latest explicit review checkpoint;
- material activity since `recorded_after` and since review;
- deterministic attention rows with trigger reasons;
- upcoming account events and commitments;
- next associated meeting and its attendee resolution;
- Leadership groups (`what_moved`, `what_is_stuck`, `what_i_need`);
- native targets for all rows.

The server returns the data needed by all three lenses in one stable contract. `lens` remains presentation state and is not sent to this endpoint. Meeting-specific expansion may use `GET /api/accounts/{account_id}/meeting-prep/{event_id}` so selecting a meeting does not refetch unrelated sections.

The response contains a `coverage` block per section. A source-adapter failure yields `partial` with named omissions. It never yields an unqualified empty success.

## 8. Review and visit checkpoints

### 8.1 Explicit review

Add an append-only `account_change_checkpoints` table:

| Field | Rule |
|---|---|
| `id` | generated primary key |
| `account_id` | required account FK |
| `scope_type` | `account` or `program` |
| `program_id` | required only for `program`, and must belong to the account |
| `reviewed_through` | required UTC timestamp from a frozen server response |
| `actor_id` | required operator identity |
| `source_type` | `command_center` or `copilot_run` |
| `source_id` | nullable source run ID; required for `copilot_run` |
| `created_at` | required UTC timestamp |

Rows are immutable, uniquely idempotent for their scope/source/through-time, and indexed by `(account_id, program_id, actor_id, reviewed_through)`. The latest checkpoint is the maximum reviewed-through value, not merely the latest insertion time. A request cannot move the checkpoint backward or beyond the current server time.

`POST /api/accounts/{account_id}/change-checkpoints` accepts `scope_type`, optional `program_id`, the frozen response's `reviewed_through`, and source metadata. The server validates the timestamp and scope and returns the new latest checkpoint. A repeated request is idempotent; no signed token or server-side read-session cache is introduced for a correctness boundary that is not a security boundary.

Account and program checkpoints compose deliberately:

- In All programs, the latest account checkpoint is the cursor. Program-only reviews do not imply that the other programs were reviewed.
- In a program filter, program-bound items use the later of the latest account checkpoint and that program's checkpoint.
- Direct account-level items always use the account checkpoint, even while a program is selected.
- “Mark Acme Europe changes reviewed” advances only the program checkpoint. If direct account-level changes remain, the UI says so instead of clearing them invisibly.
- “Mark account changes reviewed” in All programs advances the account checkpoint across the complete visible account scope.

Marking an account-scoped Copilot change brief reviewed also writes this generic checkpoint. Existing reviewed account-scoped Copilot runs are backfilled during migration. Program and portfolio Copilot cursors remain unchanged until those scopes receive their own command-center semantics.

### 8.2 Last visit

Last visit is personal presentation recency, not account truth. In the current single-editor release it remains browser-local, keyed by account plus program scope and versioned. The Overview reads the prior value before writing the successful render's server timestamp. Switching lenses during the same Overview visit does not advance it. A failed load does not advance it. Clearing browser preferences removes visit recency but cannot remove the durable review checkpoint.

The UI labels the distinction exactly:

- “Since your last review · 31 Jul” — durable and operator-advanced.
- “Since your last visit · yesterday” — browser-local and automatically advanced.

Neither heading says “unread,” because activity is not a message inbox and other native views do not share read state.

## 9. Deterministic attention rules

Operate and Leadership reuse native status rather than inventing a new priority model. Initial inclusion rules are:

1. Open blocker.
2. Overdue commitment, task, internal ask, milestone, contractual notice, or scheduled review.
3. Off-track assessment with its required recovery response and leadership ask.
4. At-risk assessment with its required recovery response.
5. Commitment, ask, milestone, meeting, review, renewal, or notice due within seven days.
6. Confirmed external change recorded since the review checkpoint.
7. Evidence gap explicitly returned by a governed generator or status/review source.

Ordering is severity band, due date, recorded date, and stable ID. Every item prints its inclusion reason. Counts are labels, not scorecards. Unknown dates sort after known dates inside the same band and render as unknown.

## 10. Trust and evidence boundaries

- Raw interaction notes never enter the command-center or activity projection. Interaction summaries are allowed; raw notes remain native-record detail.
- Named individual product usage remains impossible. Attendee context uses meetings, communications, professional roles, and explicitly dated stakeholder assessments only.
- Proposed company events are visibly proposed and cannot support a confirmed change summary, leadership claim, or generated brief.
- Stale metric-derived evidence renders unknown and enters the evidence-gap section; it never carries forward a favorable state.
- Client-facing output generators receive no new query source from this release.
- Copilot remains read-only, evidence-cited, explicitly invoked, and mock-connected. A lens never starts a run on load.
- Native source references and record links survive normalization. Summaries do not strip provenance.
- Program filtering applies before aggregation. An account-level record remains visible and labeled account-level; it is not falsely assigned to the selected program.

## 11. Failure, empty, and stale states

Required states:

- **Complete/no rows:** “No material changes since 31 Jul.”
- **Partial coverage:** “Changes are incomplete — Company and Forecast could not be read.”
- **No checkpoint:** “No review checkpoint yet” with an explanation of Mark changes reviewed.
- **No visit preference:** “First visit in this browser.”
- **No upcoming meeting:** Prepare offers the meeting selector and link to Plan; it does not render an empty brief.
- **Unassociated calendar event:** named as unassociated and excluded from account Prepare.
- **Stale point of view/status:** age and reassessment treatment from the design guide.
- **Backend unavailable:** preserve the account header and provide section-level retry.

## 12. Accessibility and interaction acceptance

- Lens tabs support keyboard arrow navigation and visible focus; browser Back/Forward restores the prior lens and meeting.
- Focus moves to the active panel heading only when activation came from keyboard; pointer activation does not unexpectedly move focus.
- Each activity group is operable without hover and announces stream, state, temporal meaning, and date.
- Proposed/confirmed, overdue/upcoming, and risk status are never color-only.
- “Mark changes reviewed” names the exact through-time in its confirmation and returns focus after completion.
- All empty, partial, loading, and error states are announced without replacing the persistent account context.
- Both themes meet the existing contrast floor; reduced motion removes animated panel transitions.

## 13. Delivery sequence

### Slice 2.0 — contracts and navigation

- Extend the route codec for `lens` and `meeting`, with pure unit tests.
- Upgrade `SegTabs` to the keyboard contract rather than creating a one-off selector.
- Add typed frontend constants and browser-local lens/visit preference helpers.
- Add the `ActivityItem` schema and adapter registry with no UI dependency.

### Slice 2.1 — Operate reference implementation

- Add the activity and command-center services/endpoints.
- Cover interactions, execution records, status assessments, forecast changes, internal asks, reviews, calendar, deployment moments, comms, and confirmed/proposed company events.
- Add explicit account checkpoints and bridge account-scoped Copilot review.
- Replace the Overview body with the Operate lens.
- Preserve status editing, export, capture, programs, and people through native links/actions rather than dropping their workflows.

### Slice 2.2 — Prepare

- Add calendar meeting selection and meeting-specific read.
- Resolve attendees without guessing.
- Add open threads, recent context, evidence gaps, pre-call generator, and explicit Copilot entry point.

### Slice 2.3 — Leadership

- Add account-scoped movement/stuck/need groups.
- Integrate governed status recovery, forecast, asks/escalations, review trail, and near-term commitments.

### Slice 2.4 — activity consumer and evidence review

- Reuse the projection in the existing Ledger/likely future Activity surface without changing the workspace taxonomy yet.
- Record source coverage and query cost.
- Reassess whether materialization or the five-job navigation is justified by measured behavior.

Implemented evidence:

- Ledger retains its mutable **Records** view and adds an **Activity** subview over the typed projection. No ninth account tab or parallel editor is introduced.
- Activity exposes scoped stream, source, state, direction, and materiality filters; local search is explicitly limited to loaded pages; effective and recorded time remain separately visible; partial coverage is named; and every row opens its native record.
- A source interaction and records created from it retain distinct activity IDs but render as one keyboard-operable expandable group when both are loaded.
- Adapter coverage, item count, and elapsed projection time are returned per read. A 30-run read-only sample across all five seeded accounts (150 projections, ten adapters) measured 0.089 ms median, 0.235 ms p95, and 1.988 ms maximum, with 17 items on the largest account.
- Those measurements do not justify materialization. The projection remains query-time and rebuildable; reconsider only with representative evidence of sustained latency or lock contention, not a speculative scale concern.
- The five-job navigation remains directional. No product-usage evidence currently shows that replacing the eight established tabs would reduce task switching or improve completion, so Release 2 preserves the taxonomy and gathers experience through the Ledger subview.

## 14. Acceptance criteria

### Shared command center

- Operate is the default for a new browser; the saved preference and explicit URL restore correctly.
- Switching lenses preserves account and program scope and participates in Back/Forward history.
- All lenses share one source contract and native targets; no duplicated record store exists.
- Split-screen layout retains every section in a sensible order.

### Activity and temporal correctness

- Every item has distinct display and recorded timestamps with a visible temporal label.
- A retroactively logged interaction is new since review but appears on its actual occurrence date.
- Proposed company events never appear as confirmed movement.
- Program filtering never drops direct account-level commitments/decisions and never attributes them to a program.
- Pagination is stable across equal timestamps and adapter order.
- Partial adapter failure cannot produce an unqualified “nothing changed.”

### Checkpoints

- Marking reviewed advances the visible scope to the frozen server stamp, is idempotent, and cannot move backward or into the future.
- A program-scoped review cannot clear changes from another program or direct account-level changes.
- Last visit advances only after a successful command-center read and remains independent of explicit review.
- Account-scoped Copilot review and command-center review share the same latest durable checkpoint.

### Prepare

- With no explicit selection, the next upcoming associated meeting is selected; otherwise the latest recent meeting is used.
- Program scope includes direct account meetings but excludes meetings owned by other programs.
- An explicit out-of-scope meeting fails closed without disclosing the other meeting and is removed from the URL.
- Unknown invitees remain unknown; attendee identity, stakeholder role, stance, and last touch are never inferred from names or email text.
- Recent context is attendee-related only where a canonical relationship supports it, and the baseline last-touch interaction is not repeated as a change.
- Open threads, evidence gaps, and brief eligibility are deterministic and scoped to the selected account and program.
- Opening Prepare and previewing a pre-call brief perform no write, generation, send, or document persistence.

### Leadership

- Delivery and commercial remain independent governed statuses with dated rationale, recovery ownership/action/date, and any recorded leadership response.
- Active forecast entries expose their recorded category, units, period, probability, unresolved conditions, and deterministic evidence support; no composite health score is introduced.
- Movement uses the explicit review cursor or named 30-day fallback and includes only the internal allowlist of confirmed, material events.
- Program scope excludes another program's movement, blockers, milestones, meetings, and commitments while preserving direct account records and clearly labeled account-wide facts.
- Stuck work includes blockers, overdue commitments and asks, at-risk milestones, unsupported forecast calls, stale/missing point of view, and missed contract notice or renewal dates.
- Active asks name the requested party/function, owner, deadline, escalation state, and explicit next action.
- Cross-account person and leadership-ask references fail closed, and another account's labels never enter the response.
- Opening Leadership performs no checkpoint, document, draft, send, or other mutation.

### Activity consumer and evidence review

- Records retains all existing capture, conversion, close/resolve, and mutual-plan actions; Activity is a read-only sibling view.
- Activity filters fail closed, facets remain scoped, same-day datetime range filtering is correct, and future/past ordering follows the documented tuple.
- Cursor pages concatenate to the same stable order as one unpaginated response, and `matched_count` remains the pre-cursor total.
- Direct account records remain visible in a program filter while another program's records remain absent.
- Every adapter reports covered/omitted state, item count, and elapsed duration; an adapter failure produces explicit partial coverage rather than a qualified-empty success.
- Interaction groups never merge distinct facts: origin and derived rows retain stable IDs, native targets, temporal semantics, and independent selection.
- Current measurements and the absence of usage evidence support neither a materialized activity table nor the five-job navigation rewrite.

### Trust and regression

- No raw notes, named individual product usage, or unconfirmed external claims enter a summary.
- Statuses remain independent and stale derived evidence renders unknown.
- Client-facing generators have no expanded input allowlist.
- Existing account actions, program filtering, capture, export, status editing, and native tabs remain reachable.
- Backend tests, frontend unit tests, lint, build, both-theme rendering, keyboard tab/arrow testing, and direct deep-link smoke all pass.

## 15. Schema proposals

One new table is justified in Release 2:

- `account_change_checkpoints` — durable, append-only operator acknowledgment cannot safely live in browser preferences or remain coupled to a particular Copilot run.

No unified activity table is justified initially. The read model is deliberately projected from canonical records and trustworthy transition ledgers. Materialization requires measured query latency or pagination instability, not anticipation.
