# Valence OS Account Path and execution-plan specification

**Status:** Proposed, 2026-08-04

**Parent authorities:** `UX-FOUNDATION-SPEC.md`, `ACCOUNT-COMMAND-CENTER-SPEC.md`

**Related authorities:** `DESIGN-GUIDE.md`, `PHASE-3-SPEC.md`, `ACCOUNT-COPILOT-SPEC.md`, `INTERNAL-OPS-SPEC.md`

**Adjacent work:** The account-pillar scorecard and transcript/email propose-and-accept workflow being specified in the Pre-call Brief research stream. This specification defines the execution surface that consumes those contracts; it does not independently define or persist a second pillar model.

**Scope:** The account-level experience that answers what should happen next, where each program is in its lifecycle, what was agreed in the latest interaction, which standard account requirements remain unevidenced, and which milestones or decisions are approaching.

## 1. Decision

Add an **Account Path** to the existing Account Overview **Operate** lens. It is not a ninth account tab, a replacement for the execution ledger, or a generic project-management product.

Account Path composes existing canonical records into three related layers:

1. **Conditions** — the account or program requirements that must become true. The pillar scorecard and current phase-gate/checklist records supply these conditions.
2. **Sequence** — phases, milestones, dependencies, and important decision dates that explain when the conditions matter.
3. **Actions** — the specific operator or customer work that advances the current condition or gate.

The default Operate view must make one recommended next move visually dominant, explain why it was selected, show the current path, and keep the remaining work scannable through progressive disclosure.

No summary becomes canonical truth. Account Path is a query-time, rebuildable projection over existing records. Native records remain the only edit and closure targets.

## 2. Product outcomes

Within ten seconds of opening an account, the operator can answer:

1. What is the single most important thing I can do next?
2. Why is it next, who owns it, and when is it due?
3. Which phase and gate is each active program working toward?
4. What did the latest meaningful interaction add or change?
5. Which standard account requirements are still missing or unsupported?
6. What is waiting on the customer, and what is my follow-up responsibility?
7. What milestone, decision, launch moment, review, notice, or renewal is approaching?
8. What evidence proves that a requirement or milestone is actually complete?

The experience should feel like a guided operating plan, not a database report. The operator should rarely need to decide which tab to inspect merely to discover the next action.

## 3. Non-goals

- Adding a new top-level or account-workspace tab.
- Replacing Tasks, Commitments, Milestones, Phase Gates, Checklists, Risks, Issues, or the Mutual Action Plan as native records.
- Creating a second task table for “plan tasks.”
- Treating every pillar as a task or every task as a pillar requirement.
- Showing every task on the account timeline.
- Computing a composite health score or an opaque AI priority score.
- Automatically accepting transcript/email extractions or silently changing canonical fields.
- Marking work complete merely because a checkbox was clicked when the native record requires evidence or acknowledgement.
- Assuming an account has one lifecycle phase when it has multiple active programs.
- Building a configurable dashboard, movable-widget system, or customer portal in the first release.
- Rebuilding the existing Today queue. Today remains the cross-account morning screen; Account Path explains execution within one account.

## 4. Vocabulary and boundaries

### 4.1 Account Path

The complete internal execution presentation for an account and its selected program scope. It includes the next move, phase path, current work, customer waits, requirements, and upcoming gates.

### 4.2 Requirement

A condition that must be evidenced, waived, or marked not applicable. Examples include “metric of record agreed,” “budget owner identified,” and “technical access validated.” A requirement is not necessarily an action.

### 4.3 Action

A concrete unit of work represented by an existing native record, normally a Task or Commitment. A checklist item may act as an action during the compatibility period. A recommended action generated from an unevidenced requirement remains a suggestion until accepted into a native record.

### 4.4 Milestone

A meaningful checkpoint with objective success criteria and an optional target date. Milestones summarize progress; they do not replace the work attached to them.

### 4.5 Gate

A decision boundary between phases. A gate passes when its required conditions are complete, is explicitly waived with a reason, or remains blocked. Phase status must not be inferred solely from elapsed time.

### 4.6 Pillar

A durable dimension of account readiness or success defined by the adjacent pillar-scorecard specification. Account Path may display pillar-derived gaps and link actions to them, but it must consume the canonical pillar contract rather than define another taxonomy.

### 4.7 Proposed update

A non-canonical suggestion extracted from a transcript, email, or other source. It must be visibly proposed and must be accepted, edited, or rejected before it can modify canonical account state.

## 5. Experience architecture

### 5.1 Relationship to existing surfaces

- **Today** answers “Across my portfolio, what needs me?”
- **Account Overview / Operate** answers “For this account, what should I do next and why?”
- **Plan** remains the complete native view for timelines, phase gates, deployment moments, checklists, and execution editing.
- **Ledger** remains the complete chronological and typed record of account work.
- **Prepare** remains meeting-oriented and uses the same accepted actions and evidence.
- **Leadership** remains review-oriented and uses the same milestones, blockers, and commitments.
- **Mutual Action Plan** remains the explicitly client-visible subset of promoted Tasks, Commitments, and Milestones.

Account Path can link into these surfaces but must not duplicate their editing controls wholesale.

### 5.2 Operate information hierarchy

The Operate lens is revised to use this order:

1. **Next best move** — one dominant, operator-actionable item with an explanation.
2. **Account path** — program phase rail or account-scope program lanes, current gate, and upcoming milestone.
3. **From the latest interaction** — accepted call-derived actions plus a proposed-update count when the adjacent workflow is connected.
4. **You own** — the remaining operator-owned actions, capped at five by default.
5. **Waiting on customer** — customer responsibilities paired with the Valence follow-up owner and date.
6. **Account essentials** — the few current-phase requirements that remain unevidenced, blocked, or proposed.
7. **Upcoming gates and dates** — milestones, deployment moments, reviews, contract dates, and meaningful meetings.
8. **Since last review** — material changes using the existing explicit review checkpoint.
9. **Current point of view** — the existing append-only operator view.
10. **Since last visit** — retained as a low-emphasis, collapsed personal-recency section.

This order supersedes only the visual order in `ACCOUNT-COMMAND-CENTER-SPEC.md` section 5.1. Existing activity semantics, checkpoints, truth boundaries, program scoping, and native-target rules remain authoritative.

### 5.3 Wide layout

Use a full-width orientation band followed by the existing two-thirds/one-third content grid:

- **Orientation band:** Next best move and Account Path.
- **Main column:** From latest interaction, You own, Since last review.
- **Side column:** Waiting on customer, Account essentials, Upcoming gates, Current point of view.

The page must not become a grid of equally prominent cards. Only Next best move receives primary emphasis. Section containers use restrained hierarchy, compact rows, and no decorative metric tiles.

### 5.4 Narrow layout

At the existing split-screen breakpoint:

1. Next best move
2. Vertical Account Path
3. From latest interaction
4. You own
5. Waiting on customer
6. Account essentials
7. Upcoming gates
8. Since last review
9. Current point of view
10. Since last visit

No information is hidden solely because of viewport width. Horizontal phase labels become a vertical path rather than a horizontally scrolling control.

## 6. Visual and interaction specification

### 6.1 Next best move

The panel contains:

- A small eyebrow: `NEXT BEST MOVE`.
- A concise verb-led title.
- One sentence explaining the deterministic selection reason.
- Owner, due date/window, program, and provenance.
- One primary action that opens the native record or performs an already-governed native action.
- At most one secondary action such as Snooze or Open source.

It must not include an AI sparkle treatment or imply probabilistic ranking. Suggested language may be AI-assisted later, but selection and reason remain rules-based.

When there is no eligible operator action, show one of these explicit states:

- **Waiting on customer** — no operator-owned action is due, but a customer responsibility is open.
- **Prepare for the next gate** — no urgent item exists; show the earliest incomplete current-phase requirement.
- **Account is caught up** — required current work is complete and no near-term event needs preparation.
- **Insufficient plan data** — no program, phase, milestone, gate, or requirement is recorded; provide a link to Plan or Onboarding.

### 6.2 Program phase path

For a selected program, display:

`Foundation → Launch → Programmatic → Expansion → Renewal`

`Closed` is a terminal state presented after Renewal or as a terminal branch, not as ordinary active work.

Each phase supports these display states:

- `complete`
- `current`
- `future`
- `blocked`
- `waived`
- `not_applicable`
- `unknown`

The component combines shape, icon, label, and text; state never depends on color alone. The current phase is visually focused. Completed phases are quieter, future phases are outlined, and blocked phases include a named reason.

The path is not a wizard and does not force sequential navigation. Clicking a phase filters the supporting requirements and actions without changing canonical phase state.

### 6.3 All-program account scope

An account with multiple active programs must not receive a fabricated aggregate phase.

When `program=all`:

- Display one compact path lane per active program.
- Sort lanes by nearest blocked/at-risk milestone, then target date, then program name.
- Show at most three lanes initially with “View all programs” for the remainder.
- Identify account-wide requirements separately from program requirements.
- Keep account-wide contract dates and internal review facts visible.

### 6.4 Action rows

Default action rows contain:

- Status or urgency marker.
- Verb-led action title.
- Short reason or definition of done.
- Program when account scope includes multiple programs.
- Responsible party and internal follow-up owner where applicable.
- Due date or relative window.
- Provenance chip.
- Native-record action.

Optional detail shown in a side panel:

- Linked milestone, gate, requirement, and pillar.
- Dependency or blocker.
- Source interaction or source reference.
- Closure rule and evidence.
- Audit history.

### 6.5 Provenance labels

Use plain, specific labels:

- `From Feb 27 onboarding call`
- `Account standard`
- `Program standard`
- `Added manually`
- `From leadership review`
- `Proposed from transcript`

Proposed and accepted items must never share the same visual state. Proposed items include explicit Accept, Edit, and Reject controls supplied by the adjacent workflow.

### 6.6 Timeline treatment

Account Overview shows a compact path and upcoming gates, not a miniature Gantt chart.

The complete Plan timeline should eventually show:

- Phase bands or program bars.
- Milestones as diamonds.
- Gate and decision markers.
- Dependencies and blockers.
- Today marker.
- Week resolution for a 90-day launch and month resolution toward renewal.

Individual actions remain in lists or boards. Selecting a phase or milestone filters the related actions.

### 6.7 Motion

- Use the existing 200–300ms expo-out interaction timing.
- Phase focus, row hover, and panel reveal move no more than 4px.
- The path can animate its active line on initial load, but never loops.
- Mouse spotlights remain ornamental and must not obscure status or selection.
- Respect `prefers-reduced-motion`; all meaning remains present without animation.

## 7. Canonical data and trust model

### 7.1 Native records remain authoritative

| Concept | Canonical source |
|---|---|
| Operator work | `tasks` |
| Customer responsibility and Valence follow-up | `commitments` |
| Lifecycle checkpoint | `milestones` |
| Phase decision boundary | `phase_gates`, `phase_gate_items` |
| Compatibility-period standard requirement | `checklist_items` |
| Blocking condition | `issues`, `risks` |
| Recurring customer moment | `deployment_moments` |
| Contractual dates | current `contract_versions` record |
| Interaction provenance | `interactions`, `source_references` |
| Cross-account urgency | existing attention projection and `attention_state` |
| Pillar readiness | adjacent pillar-scorecard contract |
| Unaccepted extraction | adjacent proposed-update contract |

Account Path does not write to any of these merely because it was opened or filtered.

### 7.2 Completion semantics

- A Task is complete according to the native task closure contract.
- A Commitment closes only with the existing acknowledgement/closure semantics.
- A Milestone completes only when its success criteria are met and the completion is recorded.
- A Phase Gate passes or is waived through its native governed flow.
- A requirement becomes evidenced, waived, or not applicable according to the eventual pillar/playbook contract.
- During the compatibility period, a completed checklist item is displayed as recorded completion, not automatically elevated to “evidenced” unless it has a supporting canonical field or source.

### 7.3 No duplicate work

The projection deduplicates wrapper and native records by `(source_type, source_id)` or the existing native target. An attention item pointing to a Task does not create a second visible action. A proposed transcript item that matches an existing Task or Commitment should propose a link or update rather than a duplicate record.

### 7.4 Program and account scope

- Program records remain program-scoped.
- Commitments and decisions retain their supported account-wide forms.
- Account-wide requirements remain visible in every program scope with an `Account-wide` label.
- Another program's actions do not enter the selected program path.
- `program=all` displays program lanes and grouped actions; it does not merge phases or gate status.

## 8. Target technical architecture

```text
canonical execution records      phase/checklist records
account activity projection      contract/calendar records
pillar scorecard contract        proposed-update contract
             \                       /
              execution_path query service
                        |
             deterministic selection and grouping
                        |
             Account Overview / Operate presentation
                        |
                 native targets for all writes
```

The `execution_path` service is a query-time adapter layer similar to `account_activity`. It may share adapters and native-target helpers but should remain a separate response optimized for normative plan state rather than chronological activity.

If measured query cost later requires caching, the cache must be fully rebuildable from canonical records and must not accept writes as a source of truth.

## 9. Delivery plan

### Slice 1 — Execution Path read model **(execute immediately)**

Build a migration-free backend aggregation endpoint over existing canonical records. It supplies the next-move candidates, phase path, accepted latest-interaction actions, operator work, customer waits, compatibility requirements, and upcoming gates.

### Slice 2 — Operate Account Path UI **(execute immediately)**

Replace the current weak `Needs action`/`Next on account` hierarchy with the Next best move orientation band, program path, and grouped execution sections. Preserve existing review checkpoints, activity coverage, point of view, and native links.

### Slice 3 — Playbook and pillar integration

Consume the canonical pillar taxonomy and requirement states from the adjacent work. Replace compatibility-only checklist interpretation with versioned account/program requirements, evidence links, exceptions, and pillar-derived next-condition suggestions.

### Slice 4 — Transcript and email proposals

Consume the adjacent propose-and-accept contract. Show proposed call actions separately, support accept/edit/reject, and connect accepted items to native Tasks, Commitments, Milestones, requirements, and fields without duplication.

### Slice 5 — Evidence, dependencies, and governed advancement

Add explicit requirement evidence, action-to-requirement links, milestone/gate dependencies, objective completion tests, and governed phase advancement. Surface blockers without automatically changing a program's manually governed phase.

### Slice 6 — Shared-plan and output extensions

Allow explicitly promoted milestones, commitments, and suitable requirements to enrich the Mutual Action Plan and generated updates. Internal-only requirements, reasons, and proposed items remain excluded by construction.

### Slice 7 — Measurement and refinement

Instrument whether operators open the recommended item, complete or snooze it, clear current-phase requirements, and reach gates on time. Use this evidence to refine deterministic priority rules. Do not optimize toward clicks alone.

### 9.1 Dependency and review order

Reviewers should evaluate the initiative in this order:

1. **Core product decisions:** sections 1–8 — conditions, sequence, actions, truth boundaries, multi-program behavior, and Operate hierarchy.
2. **Immediate release:** Slices 1–2 — these can be approved and built independently because they are read-only and migration-free.
3. **Adjacent-contract alignment:** Slice 3 against the approved pillar/playbook contract; Slice 4 against the approved propose-and-accept contract.
4. **Governance model:** Slice 5 after Slices 3–4 stabilize, because evidence, linking, and phase advancement depend on their canonical identities.
5. **External projection:** Slice 6 after client-safe fields and evidence rules exist.
6. **Evaluation:** the Slice 7 telemetry adapter can be scaffolded after Slice 2, but full metrics and rule refinement should follow Slice 5.

The review should explicitly resolve these implementation gates:

- Whether the pillar contract supplies versioned playbook instances or Account Path must add that capability to the same canonical model.
- The exact allowlist of canonical fields that transcript/email proposals may update.
- Whether the typed relationship tables proposed in Slice 5 already exist in the pillar model or must be added.
- Whether requirement summaries belong in the client-facing Mutual Action Plan at all; the safe default is no until affirmatively approved.
- Whether Slice 7 initially persists local product events or uses a non-persistent adapter during usability validation.

None of these gates should block Slices 1–2. A review outcome for each later slice should be recorded as `approved`, `approved with conditions`, `revise`, or `defer`, with the owning specification named for every condition.

## 10. Slice 1 detailed specification — Execution Path read model

### 10.1 Endpoint

Add:

`GET /api/accounts/{account_id}/execution-path?program_id={program_id}`

`program_id` is optional. Omitted means account/all-program scope. An unknown, archived, or foreign program returns `404` rather than silently falling back to all programs.

The endpoint is read-only. It must not update visit state, review checkpoints, phase state, proposed items, or canonical records.

### 10.2 Response contract

```json
{
  "stamp": {
    "data_current_through": "2026-08-04T14:30:00Z",
    "generated_at": "2026-08-04T14:30:02Z"
  },
  "scope": {
    "account_id": "acc-bluepeak",
    "program_id": "prog-bluepeak-launch",
    "mode": "program"
  },
  "program_paths": [
    {
      "program_id": "prog-bluepeak-launch",
      "program_name": "Manager coaching launch",
      "current_phase": "launch",
      "steps": [
        {
          "key": "foundation",
          "label": "Foundation",
          "state": "complete",
          "target_date": null,
          "gate_id": "gate-foundation",
          "missing_count": 0,
          "blocking_reason": null
        }
      ],
      "next_gate": null,
      "next_milestone": null
    }
  ],
  "next_move": {
    "id": "task:task-123",
    "source_type": "task",
    "source_id": "task-123",
    "title": "Confirm the metric of record with Aisha",
    "reason": "Operator task is 3 days overdue",
    "reason_code": "overdue_operator_task",
    "urgency": "now",
    "due_date": "2026-08-01",
    "owner": {"id": "person-zach", "name": "Zach", "party": "valence"},
    "responsible_party": null,
    "program_id": "prog-bluepeak-launch",
    "provenance": {"kind": "interaction", "label": "From Jul 31 onboarding call"},
    "native_target": {"tab": "ledger", "type": "task", "id": "task-123"}
  },
  "latest_interaction": {
    "interaction_id": "int-456",
    "title": "Onboarding call",
    "occurred_at": "2026-07-31T15:00:00Z",
    "accepted_actions": [{"id": "task:task-123"}]
  },
  "work": {
    "you_own": [],
    "waiting_on_customer": [],
    "account_essentials": [],
    "upcoming_gates": []
  },
  "integration": {
    "pillars": "not_connected",
    "proposed_updates": "not_connected"
  },
  "coverage": {
    "status": "complete",
    "included_sources": [],
    "omitted_sources": [],
    "warnings": []
  }
}
```

New enum values are explicit and closed in the backend schema. The frontend must render unknown future enum values as `Unknown`, record a diagnostic, and avoid treating them as complete.

### 10.3 Source adapters

Slice 1 reads:

- Active programs and current program phase.
- Open Tasks.
- Open Commitments and their internal follow-up owners.
- Open Risks and Issues, with blocker state.
- Upcoming or at-risk Milestones.
- Phase Gates and Phase Gate Items.
- Open Checklist Items.
- Deployment Moments with dates.
- Current contract notice, decision, and renewal dates.
- Existing account-command-center attention and upcoming projections where they already normalize supported sources.
- Interactions referenced by Tasks, Commitments, Milestones, Risks, and Issues.

Every adapter returns a normalized internal candidate with source identity, scope, owner, responsible party, dates, state, reason code, provenance, and native target.

### 10.4 Eligibility for Next best move

An item is eligible when it represents an action the Valence operator can take or a governed follow-up the operator owns.

Eligible examples:

- An open Task assigned to a Valence person.
- The internal follow-up side of an open customer Commitment.
- An unresolved blocker with a Valence owner.
- An incomplete item on the current phase gate, or a current-phase checklist item whose label is itself a supported operator action.
- Preparation for a milestone or contract date inside its governed lead window.

Ineligible as the primary move:

- A customer-owned responsibility with no Valence follow-up action.
- A completed, cancelled, closed, waived, or not-applicable item.
- A future-phase requirement that is not a prerequisite and is outside its lead window.
- A proposed extraction that has not been accepted.
- An item from another program when a program is selected.
- An unsupported field gap with no safe action.

When only customer-owned work remains, `next_move` is null and the response supplies the `waiting_on_customer` empty-state variant rather than pretending the customer task is the operator's task.

### 10.5 Deterministic priority

Candidates sort by this tuple:

1. Priority band.
2. Due date, oldest/earliest first; missing dates last within a band.
3. Source recorded/created timestamp, oldest first.
4. Stable source identity.

Priority bands, highest first:

1. Operator-owned active blocker.
2. Incomplete item that is explicitly part of the current phase gate.
3. Overdue operator Task or follow-up on an overdue Commitment.
4. Contractual notice/decision preparation inside its configured lead window.
5. Operator Task or Commitment follow-up due within seven days.
6. Required incomplete condition for the current phase.
7. Preparation action for the next milestone or confirmed meeting.
8. Open accepted action from the latest meaningful interaction.
9. Remaining operator-owned open work.

The response exposes `reason_code` and a user-facing `reason`. Tests assert both membership and order. AI does not participate in ranking.

### 10.6 Latest-interaction actions

Find the latest meaningful, non-archived Interaction in scope. Include accepted canonical Tasks, Commitments, Milestones, Risks, and Issues whose `source_interaction_id` matches it.

- Do not include raw notes as actions.
- Do not infer unaccepted actions from body text in Slice 1.
- Sort blockers, then overdue/due work, then undated work.
- If the latest interaction produced no accepted action, return an empty list rather than “No action was agreed.” Absence of a record is not proof of absence.

### 10.7 Account essentials compatibility adapter

Until the pillar/playbook contract lands, open `checklist_items` supply compatibility requirements.

- Current or elapsed checklist sections appear before future sections.
- A checklist completion is labeled `Recorded complete` unless a supported field, answer source, or native closure supplies evidence.
- `na` appears as `Not applicable`; it never counts as incomplete.
- Account-wide items remain visible in selected program scope.
- The response marks each item `compatibility_source: true` so the UI and future migration can distinguish it.

Phase Gate Items may also appear as requirements but take precedence over duplicate checklist labels because they are closer to governed phase advancement.

### 10.8 Program path derivation

The program's canonical `phase` determines `current`; Account Path does not advance it.

- Phases before current display `complete` only when the available governed gate record supports completion; otherwise `unknown`.
- The canonical current phase displays `blocked` for an open program-level blocker Risk/Issue. A merely open gate or incomplete gate item means the phase is current, not blocked.
- Future phases display `future`.
- Passed gates display completion; waived gates display `waived` with their reason available in details.
- Missing gates do not imply completion.

Slice 1 must prefer honest `unknown` states over reconstructing unsupported historical phase completion.

### 10.9 Coverage and partial failure

Adapter failure must not turn into a blank page or false caught-up state.

- The service attempts independent source adapters.
- `coverage.status` is `complete`, `partial`, or `failed`.
- Partial responses list omitted sources and warnings.
- `Account is caught up` is legal only when every source required for eligibility succeeded.
- A failed pillar or proposed-update integration in later slices cannot suppress canonical execution work.

### 10.10 Slice 1 backend acceptance criteria

- The endpoint returns one explainable Next best move for a seeded program with eligible work.
- A blocker that gates the current phase wins over a merely overdue non-blocking task.
- An overdue operator action wins over a future requirement.
- Customer responsibility appears under Waiting on customer and retains its internal follow-up owner.
- All-program scope produces separate program paths and no aggregate phase.
- Selected-program scope excludes other programs while retaining supported account-wide facts.
- Latest-interaction actions include only canonical records linked to that interaction.
- Proposed records never appear as accepted actions.
- Duplicate attention/native records appear once.
- Missing gates produce Unknown rather than Complete.
- A failed adapter produces named partial coverage and prevents a false caught-up state.
- Opening the endpoint creates no audit event and changes no record.

### 10.11 Slice 1 tests

Add focused service and router tests for:

- Priority band ordering and deterministic ties.
- Operator/customer ownership split.
- Program/all-program scope.
- Latest-interaction provenance.
- Checklist compatibility behavior.
- Gate and phase state derivation.
- Dedupe by native identity.
- Contract-date lead windows.
- Partial coverage.
- Empty-state selection.
- Read purity.

## 11. Slice 2 detailed specification — Operate Account Path UI

### 11.1 Component boundary

Create focused presentation components rather than growing one monolithic lens:

- `AccountPathOrientation`
- `NextBestMove`
- `ProgramPath`
- `ProgramPathLane`
- `ExecutionGroup`
- `ExecutionRow`
- `ProvenanceChip`
- `ExecutionCoverageNotice`

`OperateLens` owns order and navigation callbacks. Components receive normalized response objects and do not query native records independently.

### 11.2 Loading sequence

1. Existing account orientation and activity request begins.
2. Execution Path request begins in parallel.
3. The header and lens switcher render when account orientation is available.
4. Account Path sections use bounded skeletons matching final height.
5. Existing activity sections remain usable if Execution Path fails.

A failed Execution Path request shows a compact error with Retry and links to native Plan/Ledger surfaces. It must not blank the account.

### 11.3 Orientation band layout

At wide widths:

- Next best move occupies approximately three-fifths.
- Program Path occupies approximately two-fifths.
- Both share one aligned surface or two visually joined surfaces; avoid oversized independent blocks.
- Total initial height should remain approximately 150–220px for a selected program.

At account/all-program scope, the orientation band may grow to show up to three compact program lanes but should remain below the first viewport on common desktop dimensions.

### 11.4 Next best move behavior

- The entire title/summary region may open the native target, but explicit buttons remain keyboard reachable.
- The primary button label is object-specific: `Open task`, `Follow up`, `Resolve blocker`, `Prepare`, or `Open requirement`.
- Snooze uses the existing governed attention action only when the source supports it.
- Resolve/complete uses the existing native closure flow and never applies a generic optimistic checkbox.
- After a successful native update, refresh Execution Path and affected activity sections.
- Announce the new recommended move through an `aria-live="polite"` region without stealing focus.

### 11.5 Execution groups

- Render a maximum of five rows per group by default.
- `View all` opens or filters the relevant native view; it does not expand indefinitely in Overview.
- Omit an empty Latest interaction group unless there is a meaningful explicit empty state to show.
- Empty You own plus non-empty Waiting on customer uses the waiting variant in Next best move.
- Account essentials shows at most three current-phase gaps before `View all`.
- Upcoming gates shows the next three confirmed items, ordered by date.

### 11.6 Status and urgency language

Use direct language:

- `Blocks current gate`
- `9 days overdue`
- `Due Friday`
- `Waiting on Aisha`
- `Needed before launch`
- `Evidence not recorded`
- `Proposed — review required`
- `Recorded complete`

Avoid generic labels such as `At risk` without a reason, and avoid presenting `Unknown` as neutral good news.

### 11.7 Accessibility

- Phase paths use an ordered list with textual state available to assistive technology.
- Interactive phases use real buttons and expose the selected filter with `aria-current="step"` or the appropriate selected state.
- Arrow-key navigation is optional; normal tab order must remain complete and logical.
- Every icon has an accessible name or is hidden when redundant.
- Focus rings follow the shared accent focus token and remain visible over elevated surfaces.
- Color is never the sole carrier of phase, urgency, proposal, or completion state.
- Truncated action and milestone labels expose the complete label through an accessible title/details path.
- Reduced-motion mode removes line drawing, fades, parallax, and hover translation.

### 11.8 Responsive and density behavior

- No horizontal page scrolling at the existing minimum supported width.
- Path becomes vertical before labels become unreadable.
- Owner and due metadata wrap beneath the title rather than forcing narrow columns.
- Primary actions remain at least 40px high on touch layouts.
- Compact density may reduce row padding but cannot remove reason, owner, or due-state meaning.

### 11.9 Analytics events

Record product telemetry, not canonical account activity:

- `account_path_viewed`
- `next_move_opened`
- `next_move_snoozed`
- `execution_group_opened`
- `program_path_filtered`
- `execution_native_target_opened`
- `execution_path_retry`

Include account/program scope, source type, reason code, and current phase where permitted. Do not include raw notes, transcript text, or confidential action descriptions in analytics payloads.

### 11.10 Slice 2 frontend acceptance criteria

- Next best move is the first and strongest content after the account/lens header.
- A selected program shows a readable completed/current/future path.
- All-program scope shows separate lanes and never an aggregate phase.
- Call-derived accepted actions display their interaction provenance.
- Customer responsibilities are visually separated from operator work.
- Account essentials distinguish missing evidence from ordinary tasks.
- Every summarized item opens its native record or native workspace destination.
- Existing Since last review checkpoints and Mark reviewed behavior still work.
- Current point of view remains available.
- Since last visit remains present but visually subordinate.
- Partial coverage is named and cannot appear as caught up.
- Keyboard, focus, contrast, narrow-width, and reduced-motion checks pass.

### 11.11 Slice 2 tests

Add component/integration coverage for:

- Normal selected-program rendering.
- Multi-program account rendering.
- Waiting-on-customer variant.
- Caught-up and insufficient-plan-data variants.
- Partial and failed coverage.
- Native target callbacks.
- Review-checkpoint regression.
- Responsive path orientation.
- Keyboard and accessible-name behavior.
- Reduced-motion class/media behavior.

## 12. Later-slice integration contracts

### 12.1 Pillar scorecard

The pillar system should eventually provide Account Path with:

- Stable pillar and requirement keys.
- Account/program scope.
- Required/optional applicability.
- `not_started`, `in_progress`, `evidenced`, `blocked`, and `not_applicable` states.
- Accepted evidence references.
- Evidence freshness where relevant.
- Current-phase relevance.
- Suggested action template, if one exists.
- Definition of done.

Account Path may turn a missing requirement into a recommended **suggestion**, but the suggestion must be accepted into a native action before it becomes operator work.

### 12.2 Proposed transcript/email updates

The proposed-update system should provide:

- Proposal identity and source span/reference.
- Proposed native target type.
- Proposed field changes.
- Proposed action title, owner, responsible party, due date, and scope.
- Duplicate/match candidates.
- Accept, edit, reject, and supersede state.

Account Path displays proposal counts and previews but delegates all mutation to the governed proposal workflow.

### 12.3 Requirement evidence

The long-term requirement model must support evidence links rather than copying evidence text. Evidence can point to accepted canonical fields, interactions, decisions, stakeholder roles, metrics, documents, or other governed records. Retraction or supersession must recalculate the derived requirement presentation.

### 12.4 Action linkage

Later slices may require an additive join model that links native actions to requirements, milestones, gates, and pillars. Any such join must link existing records rather than create a generic replacement action object.

## 13. Slice 3 detailed specification — Playbook and pillar integration

### 13.1 Entry gate and ownership

Slice 3 begins only after the adjacent pillar-scorecard specification approves:

- Stable pillar and requirement keys.
- Requirement states and applicability semantics.
- Account-wide versus program-specific scope.
- Evidence and freshness rules.
- Versioning and override behavior.

That specification owns the canonical taxonomy and persistence model. Account Path owns how those accepted states become a readable execution plan. If the adjacent contract uses different names, Account Path adapts at the service boundary; it must not create a competing pillar table or translate the same condition into a second manually maintained status.

### 13.2 Minimum canonical capabilities

Regardless of final table names, the approved model must support these capabilities:

1. **Versioned definitions** — a pillar and requirement definition has a stable key, version, label, purpose, default scope, and definition of done.
2. **Versioned playbooks** — an onboarding, adoption, expansion, renewal, or other plan template pins an ordered set of requirement definitions and relative timing rules.
3. **Plan instances** — an account or program explicitly instantiates a playbook version. Later template edits do not silently rewrite the active plan.
4. **Applicability** — each instantiated requirement is required, optional, or not applicable; not applicable requires a reason and actor.
5. **Derived state** — state is computed from accepted records and evidence wherever possible. Manual assessment, if allowed by the pillar contract, is separately labeled and dated.
6. **Evidence links** — evidence references canonical objects rather than copying their content.
7. **Exceptions** — waivers and overrides preserve who, when, and why.
8. **Ordering and timing** — requirements can be associated with a lifecycle phase, relative date rule, milestone, or gate.
9. **Upgrade history** — applying a newer playbook version is an explicit reviewed action with a recorded diff.

### 13.3 Playbook structure

A playbook requirement should expose this normalized contract to Account Path:

```json
{
  "instance_id": "reqinst-bluepeak-metric",
  "definition_key": "success.metric_of_record",
  "pillar_key": "outcomes",
  "label": "Metric of record agreed",
  "scope": {"account_id": "acc-bluepeak", "program_id": "prog-bluepeak-launch"},
  "phase": "foundation",
  "requirement_level": "required",
  "state": "not_started",
  "state_reason": "No accepted metric definition is linked",
  "definition_of_done": "A named metric, owner, baseline, and reporting cadence are accepted",
  "due_rule": {"anchor": "kickoff", "offset_days": 14},
  "due_date": "2026-08-14",
  "evidence": [],
  "suggested_action": {
    "title": "Confirm the metric of record with the program sponsor",
    "native_type": "task"
  },
  "playbook": {"key": "enterprise-launch", "version": 2},
  "updated_at": "2026-08-04T14:30:00Z"
}
```

`suggested_action` is a template, not an open Task. It is eligible for the `Prepare for the next gate` empty-state recommendation but is not mixed into `you_own` until accepted into a native record.

### 13.4 Plan instantiation

The pillar/playbook service should expose a governed operation equivalent to:

`POST /api/accounts/{account_id}/plan-instances`

Input:

- Playbook key and version.
- Optional program scope.
- Anchor type and date, normally kickoff, launch, contract start, or renewal.
- Explicitly excluded optional requirements.

Behavior:

- Validate account/program ownership.
- Reject duplicate active instances for the same playbook and scope unless the request is an explicit version upgrade.
- Resolve relative dates once at instantiation while preserving the original rule.
- Return a preview diff before an upgrade applies.
- Record the selected version, actor, anchor, and exclusions.
- Never mark requirements complete during instantiation merely because old checklist text looks similar.

The existing guided onboarding flow may call this operation after the approved model lands. Until then it continues seeding existing milestones and checklist items.

### 13.5 Checklist compatibility migration

Migration is conservative and reviewable:

1. Match existing `checklist_items.template_key` to stable requirement keys using an explicit mapping file.
2. Match only exact known keys; never fuzzy-match labels.
3. Create plan instances pinned to the migration playbook version.
4. Carry due dates and `na` reasons when they are structurally supported.
5. Translate `done` into `recorded_complete`, not `evidenced`, unless accepted supporting evidence exists.
6. Keep unmatched checklist items readable as legacy requirements.
7. Produce a per-account migration report: mapped, unmatched, ambiguous, and evidence missing.
8. Make the migration idempotent and safe to rerun.

Do not delete `checklist_items` in this slice. Removal requires a separate deprecation decision after all readers and exports use the canonical requirement contract.

### 13.6 Account Path integration

The Execution Path service adds a pillar/playbook adapter that:

- Groups incomplete requirements by current phase and pillar.
- Includes required current-phase conditions before optional or future conditions.
- Exposes explicit evidence and freshness gaps.
- Provides suggested actions separately from canonical work.
- Deduplicates a requirement when a linked native Task or Commitment already represents its next step.
- Preserves account-wide requirements in selected program scope.
- Reports pillar coverage independently from canonical execution coverage.

Account essentials shows at most three current-phase gaps. `View all` opens a focused requirements view in Plan; it does not introduce a new Account Overview editing surface.

### 13.7 Requirement detail experience

Opening a requirement shows a side panel with:

- Requirement label and pillar.
- Why it matters in the current phase.
- State and state reason.
- Definition of done.
- Due date and original relative rule.
- Accepted evidence and source links.
- Missing evidence.
- Linked Tasks, Commitments, Milestones, and Gate.
- Applicability/waiver history.
- `Create action` when a supported suggested action exists.
- `Add evidence` and `Mark not applicable` only through governed flows.

Do not expose a generic status dropdown that can overwrite a derived evidence state.

### 13.8 Creating an action from a requirement

`Create action` opens a prefilled native Task or Commitment form. The operator can edit:

- Title/description.
- Internal owner.
- Responsible customer party when creating a Commitment.
- Due date.
- Program scope.
- Source interaction/reference where available.

Saving creates the native record and a requirement-action link in Slice 5. Until Slice 5 lands, the UI can create the native action and return to the requirement, but it must not claim a durable link exists.

### 13.9 Slice 3 acceptance criteria

- A program can instantiate an approved playbook version from a kickoff anchor.
- Relative dates resolve correctly and preserve their source rules.
- Editing a template does not mutate an existing plan instance.
- Account and program requirements remain independently scoped.
- Current-phase required gaps appear in Account essentials in stable order.
- Suggested actions are visually distinct from open Tasks and Commitments.
- A completed legacy checklist item is not falsely labeled evidenced.
- Not-applicable requirements record a reason and actor.
- An upgrade preview shows additions, removals, timing changes, and definition changes before applying.
- Failed or partial pillar coverage cannot suppress canonical execution work.

### 13.10 Slice 3 tests

- Playbook instantiation and duplicate prevention.
- Relative date anchors and boundary dates.
- Version pinning and upgrade preview/application.
- Account/program scope validation.
- Required/optional/not-applicable ordering.
- Derived versus manual state labeling.
- Exact-key checklist migration, unmatched records, and idempotency.
- Evidence-safe compatibility status.
- Execution Path adapter dedupe and partial coverage.
- Requirement detail accessibility and native-action prefill.

## 14. Slice 4 detailed specification — Transcript and email proposals

### 14.1 Entry gate and reuse

Slice 4 begins after the adjacent propose-and-accept specification approves its canonical proposal shape. It must reuse the existing security boundary:

- Inputs are treated as data, never instructions.
- Extraction runs record model and prompt versions.
- Every proposal retains a source span or source reference.
- Strict schemas validate allowed mutations.
- Nothing writes without explicit human acceptance.
- Accepted proposals point to the created or updated canonical object.

Existing `extraction_runs`, `extraction_proposals`, acceptance endpoints, rejection endpoints, and audit behavior remain the compatibility foundation. The approved proposal contract may replace or widen them, but Account Path must not add a second inbox.

### 14.2 Supported proposal intents

The long-term contract must distinguish intent from native target:

- `create` — create a Task, Commitment, Milestone, Risk, Issue, Decision, requirement exception, deployment moment, or other allowlisted record.
- `update` — propose a change to an allowlisted canonical field.
- `link` — connect existing records, such as evidence to a requirement or an action to a milestone.
- `close` — propose governed completion with the native closure payload.
- `no_change` — record that extracted content matches current state; normally hidden from the operator.

Slice 4 initially enables create and allowlisted update intents. Link and close intents remain behind Slice 5 because they depend on governed relationship and completion contracts.

### 14.3 Proposal response contract

Account Path consumes a normalized proposal shape:

```json
{
  "id": "proposal-789",
  "account_id": "acc-bluepeak",
  "program_id": "prog-bluepeak-launch",
  "source": {
    "kind": "interaction",
    "id": "int-456",
    "label": "Jul 31 onboarding call",
    "span": "Aisha will send the HR calendar by Friday"
  },
  "intent": "create",
  "target_type": "commitment",
  "payload": {
    "description": "Send the HR calendar",
    "responsible_party_id": "person-aisha",
    "internal_owner_id": "person-zach",
    "due_date": "2026-08-07"
  },
  "status": "proposed",
  "confidence": "high",
  "match_candidates": [],
  "created_target": null,
  "created_at": "2026-08-04T14:30:00Z"
}
```

Confidence is supporting metadata, not an acceptance shortcut or ranking signal.

### 14.4 Account proposal inbox

Add or adapt a read endpoint equivalent to:

`GET /api/accounts/{account_id}/proposed-updates?program_id={program_id}&source_interaction_id={interaction_id}&status=proposed`

The response groups proposals by source and then target type. It includes exact source provenance, validation warnings, and duplicate/match candidates.

Account Path uses only:

- Proposed count for the current scope.
- Up to three proposals from the latest interaction.
- A link to review all proposals.

The complete review experience remains in the existing Extraction/Inbox workflow or its approved successor.

### 14.5 Review interactions

Each proposal supports:

- **Accept** — applies the validated payload through the native service and records the created/updated object.
- **Edit and accept** — edits only allowlisted payload fields, revalidates, then applies in one transaction.
- **Reject** — records rejection without changing canonical state.
- **Open source** — opens the interaction or source reference at the supporting span where possible.
- **Use existing** — links the proposal to a confirmed duplicate/match and records that resolution without creating another record.

There is no one-click “Accept all” in the first release. A later batch flow may accept a selected set only after every item independently validates and the entire batch preview is visible.

### 14.6 Duplicate and conflict handling

Before acceptance, perform deterministic matching within the same account/program scope:

1. Exact source proposal already accepted.
2. Exact normalized target type and description/title.
3. Same responsible party/owner and due date for Tasks or Commitments.
4. Same canonical field with a newer accepted value.
5. Same milestone name and target date.

Possible matches are suggestions, not automatic merges. A conflict must show current value, proposed value, source dates, and available resolutions. Older evidence never silently overwrites a newer accepted record.

Acceptance is idempotent. Repeating an accepted request returns the created/updated target or a stable conflict; it never creates a duplicate.

### 14.7 Accepted action placement

After acceptance:

- Created Tasks and Commitments enter the appropriate Account Path group after refresh.
- Accepted records linked to the latest interaction appear under From latest interaction.
- The proposal disappears from the proposed preview but remains in proposal history.
- The next-move engine reruns using the canonical record; the proposal itself is never ranked.
- The provenance chip continues pointing to the original source.

### 14.8 Email-specific boundaries

Email ingestion must preserve:

- Message identity and thread identity.
- Sender, recipients, sent time, and account/program association confidence.
- Quoted-text boundaries so repeated thread history does not produce duplicate proposals.
- Attachment/source references when they support a proposal.
- Explicit low-confidence association review before account state can be changed.

An unassociated or low-confidence email remains in the capture/association inbox and cannot enter Account Path as account work.

### 14.9 Error and concurrency behavior

- Validation errors remain attached to the proposal and explain the required correction.
- If the target changed after proposal creation, acceptance returns a conflict preview rather than overwriting it.
- Accept/edit/reject controls disable while a request is pending.
- Two concurrent accept attempts create at most one canonical target.
- Partial failure in the proposal adapter does not block canonical Account Path content.

### 14.10 Slice 4 acceptance criteria

- Latest-interaction proposals are visibly separate from accepted work.
- Every proposal shows exact source provenance.
- Accept creates or updates one allowlisted canonical record transactionally.
- Edit and accept revalidates the edited payload.
- Reject creates no canonical record.
- Use existing resolves a duplicate without creating another object.
- Accepted call actions appear in the correct owner group and latest-interaction section.
- Low-confidence account association cannot mutate account state.
- Repeated acceptance is idempotent.
- Proposed items never influence Next best move until accepted.

### 14.11 Slice 4 tests

- Strict schema rejection and allowlisted mutation coverage.
- Per-item accept, edit-and-accept, reject, and use-existing.
- Source-span and audit provenance.
- Duplicate and stale-field conflict detection.
- Transaction rollback and concurrent idempotency.
- Program/account association boundaries.
- Quoted email deduplication.
- Latest-interaction proposal/accepted placement.
- Proposal adapter partial failure.
- Keyboard and screen-reader review flow.

## 15. Slice 5 detailed specification — Evidence, relationships, and governed advancement

### 15.1 Decision

Add explicit, additive relationship records rather than inferring durable dependencies from matching text. Do not introduce a replacement “plan item” object.

The preferred relational model is narrow and typed:

1. **Requirement-action links** — connect a requirement instance to a native Task or Commitment with `advances`, `blocks`, or `follow_up_for` semantics.
2. **Requirement-evidence links** — owned by the pillar contract; connect a requirement to accepted supporting records.
3. **Milestone-action links** — connect a Milestone to Tasks or Commitments that advance or block it.
4. **Gate-requirement links** — connect a Phase Gate to required or optional requirement instances.
5. **Program phase events** — append-only history of proposed, completed, waived, or rejected phase transitions.

Separate tables are preferred over a fully polymorphic graph because SQLite cannot enforce foreign keys across arbitrary object-type/id pairs. If the approved pillar model already supplies equivalent typed relations, reuse it.

### 15.2 Relationship integrity

Every link operation must:

- Validate account and program scope on both sides.
- Reject links to archived or unsupported records.
- Enforce one active identical relationship.
- Record actor, timestamp, and optional source reference.
- Preserve link history through archival rather than destructive deletion when the relationship influenced a gate or transition.
- Prevent a requirement from using its own suggested action as evidence of completion.

Links are explicit operator actions or accepted proposals. The service may suggest likely links, but text similarity never becomes a durable relationship without acceptance.

### 15.3 Evidence rules

Evidence adapters may support:

- Canonical account/program fields with recorded provenance.
- Decisions.
- Stakeholder roles and accepted relationship evidence.
- Metric definitions, observations, value targets, and value stories.
- Interactions and source references.
- Tasks/Commitments only when their governed closure proves the requirement condition.
- Documents and artifacts with source identity.

Each requirement definition declares its allowed evidence types and evaluation rule. Unsupported evidence can be attached as context but cannot change derived state.

Evidence state recalculates at read time or through a rebuildable projection. Retraction, supersession, staleness, or archival of evidence removes its support and can return a requirement to an evidence-gap state.

### 15.4 Definition-of-done evaluators

Use deterministic evaluators for common requirement shapes:

- `field_present` — a specific accepted canonical field is populated.
- `role_present` — a required stakeholder role exists and meets freshness/evidence rules.
- `record_exists` — an allowlisted canonical record exists in scope.
- `record_closed` — a linked native action has valid governed closure.
- `metric_ready` — metric definition, baseline, owner, and cadence are present.
- `milestone_complete` — linked Milestone meets its native completion contract.
- `all_of` / `any_of` — explicit composition of other deterministic evaluators.
- `manual_evidence_review` — accepted evidence requires a dated reviewer decision where automation cannot establish sufficiency.

Evaluator versions are recorded. Changing an evaluator produces a preview of affected requirement states before rollout.

### 15.5 Gate readiness

Add a read operation equivalent to:

`GET /api/programs/{program_id}/phase-readiness`

It returns:

- Canonical current phase.
- Proposed next phase.
- Required gate requirements and states.
- Blocking program Risks/Issues.
- Open linked actions.
- Missing or stale evidence.
- Passed, blocked, ready, or insufficient-data readiness.
- Coverage and evaluator versions.

`ready` means the evidence satisfies the approved gate contract; it does not advance the phase.

### 15.6 Governed phase advancement

Add a command equivalent to:

`POST /api/programs/{program_id}/phase-transitions`

Input includes expected current phase, requested next phase, readiness version/stamp, actor, and optional override.

Rules:

- Normal advancement follows the approved phase graph one step at a time.
- The command rejects stale readiness stamps.
- A ready transition records the phase event and updates the canonical program phase in one transaction.
- An override requires a reason and explicit authority; it records unmet requirements and never marks them evidenced.
- Waiving a gate is distinct from completing its requirements.
- Opening Account Path or becoming ready never auto-advances phase.
- Phase history is append-only and visible in Plan and Leadership review provenance.

### 15.7 Successor-action closure

When an operator resolves or snoozes a surfaced action:

- Native closure rules remain authoritative.
- If the work is not actually finished, the flow can link a successor Task or Commitment.
- The previous item records its closure/snooze reason through the existing governed flow.
- The requirement or milestone remains open until its evaluator is satisfied.
- The next-move engine reruns after the transaction.

This prevents “Resolve” from becoming a way to hide incomplete account work.

### 15.8 UI changes

- Requirement details show linked actions and evidence.
- Action details show the requirement, milestone, or gate they advance.
- The path exposes `Ready to advance`, `Blocked`, or `Evidence missing` with reasons.
- A phase-advance dialog shows every required condition and the exact override consequences.
- Timeline dependency lines appear only for explicit milestone/action relationships and remain visually secondary.
- The Next best move reason can now say `Unblocks Launch gate` only when an accepted explicit relation supports the claim.

### 15.9 Slice 5 acceptance criteria

- Cross-account and cross-program links are rejected.
- A native action can advance a requirement without becoming evidence merely by being open.
- Valid governed closure can satisfy a requirement only when its evaluator allows it.
- Retracted or stale evidence recalculates requirement state.
- Phase readiness names every unmet condition and coverage gap.
- Ready state never auto-advances the program.
- Phase transition is atomic, version-checked, and append-only in history.
- Overrides record actor, reason, unmet requirements, and evidence state without falsifying completion.
- Next best move claims gate impact only from explicit relationships.

### 15.10 Slice 5 tests

- Typed relationship scope and uniqueness constraints.
- Link archival/history behavior.
- Each evaluator type and evaluator version changes.
- Evidence retraction, supersession, and staleness.
- Gate readiness under complete, blocked, and partial coverage.
- Atomic phase transition and stale-readiness rejection.
- Override and waiver semantics.
- Successor-action behavior.
- Explicit-relation ranking reason.
- Timeline and detail-panel accessibility.

## 16. Slice 6 detailed specification — Shared plans and generated outputs

### 16.1 Decision

Extend the existing Mutual Action Plan and generated outputs through affirmative promotion and narrow safe projections. Do not expose the internal Account Path screen, pillar diagnostics, proposal inbox, or evidence-gap reasoning directly to customers.

Client visibility remains opt-in per record. A record cannot become client-visible without an accepted source under the existing trust boundary.

### 16.2 Shareable content

Initially allow:

- Promoted Milestones.
- Promoted customer/Valence Commitments.
- Promoted Tasks appropriate for joint execution.
- Promoted value targets and growth-plan lines already supported by their native contracts.
- Approved requirement summaries only after the pillar model supplies a client-safe label, source, and visibility state.

Never allow:

- Proposed updates.
- Internal-only Tasks, Risks, Issues, scores, confidence, or ranking reasons.
- Stakeholder stance, internal political notes, budget tactics, or competitive notes.
- Requirement evidence that is not independently client-visible.
- Waiver/override rationale unless explicitly authored for sharing.
- Raw transcripts, emails, or source spans.

### 16.3 Client-safe requirement projection

If requirements become shareable, the canonical instance needs:

- `client_visible` default false.
- A client-safe label or confirmation that the canonical label is safe.
- Client-facing owner where relevant.
- Target date/window.
- Simple status: not started, in progress, complete, blocked, or not applicable.
- At least one accepted source or jointly acknowledged record.

Internal definition-of-done logic, evidence diagnostics, and suggested actions remain excluded by construction.

### 16.4 Promotion workflow

Promotion uses the existing pattern:

1. Open the native item.
2. Preview exactly what the customer-safe projection will show.
3. Validate source and scope.
4. Confirm promotion.
5. Record audit history.

Demotion is allowed and audited. It removes the item from future shared views without deleting the native record or previous generated artifacts.

### 16.5 Mutual Action Plan response

The shared plan should organize promoted items by program and milestone rather than expose an unstructured mixed table:

- Purpose and data-current-through stamp.
- Current shared phase/milestone summary.
- Joint actions grouped by milestone or workstream.
- Customer owner, Valence owner, due date, and simple status.
- Confirmed upcoming milestones and decisions.
- Source label appropriate for external use.

The renderer queries only allowlisted client-visible fields. It must not serialize full database rows and then filter them in the frontend.

### 16.6 Generated outputs

Enrich these outputs only through their existing source and visibility contracts:

- Mutual Action Plan.
- Client value review/QBR.
- Internal team update.
- Leadership review packet.
- Pre-call brief.

Internal outputs may include Account Path ranking reasons, evidence gaps, and proposal counts when their source rules permit. Client outputs may include only affirmed client-visible projections.

Every generated artifact records:

- Data-current-through.
- Included source identities.
- Missing/stale source warnings.
- Template/version.
- Whether the content is internal or client-facing.

### 16.7 Preview and leakage testing

Add a server-rendered or backend-projected preview operation. The preview is generated from the same safe projection used by export, preventing the UI preview from differing from the actual artifact.

Automated negative tests seed sensitive internal fields and assert they cannot appear in:

- API responses for shared plans.
- Markdown/HTML/PDF/PPT output text.
- Accessibility labels and hidden DOM.
- Analytics payloads.

### 16.8 Slice 6 acceptance criteria

- Nothing appears in a shared plan without affirmative promotion.
- Promotion requires supported source provenance.
- Proposed and internal-only records are excluded by query construction.
- Shared requirements expose only the approved client-safe projection.
- Preview and export use the same response contract.
- Demotion affects future views without rewriting historical artifacts.
- Multi-program shared plans remain grouped and readable.
- Every output is stamped and source-traceable.

### 16.9 Slice 6 tests

- Promotion/demotion authorization, source, and scope validation.
- Client-safe field allowlists.
- Negative leakage fixtures across API and renderers.
- Program/milestone grouping and ordering.
- Output stamps and source manifests.
- Historical artifact immutability after demotion.
- Empty and partial shared plans.
- Accessible external rendering.

## 17. Slice 7 detailed specification — Measurement and refinement

### 17.1 Decision

Measure whether Account Path improves execution without turning behavioral telemetry into account truth. Product events are operational diagnostics and are never read by account status, pillar state, ranking, generated outputs, or customer-facing features.

There is no current general product-telemetry foundation in the repository. Implement a small adapter boundary first so local storage can later be replaced without coupling UI components to a vendor.

### 17.2 Event contract

The telemetry adapter accepts only an enumerated event name and bounded metadata:

```json
{
  "event_name": "next_move_opened",
  "occurred_at": "2026-08-04T14:32:00Z",
  "session_id": "local-session-id",
  "account_id": "acc-bluepeak",
  "program_id": "prog-bluepeak-launch",
  "properties": {
    "source_type": "task",
    "reason_code": "overdue_operator_task",
    "current_phase": "launch",
    "scope_mode": "program"
  }
}
```

Do not send titles, descriptions, transcript text, source spans, person names, email addresses, document contents, or free-form notes.

### 17.3 Initial events

- `account_path_viewed`
- `next_move_opened`
- `next_move_snoozed`
- `next_move_completed`
- `successor_action_created`
- `execution_group_opened`
- `program_path_filtered`
- `requirement_opened`
- `requirement_action_created`
- `proposal_review_opened`
- `proposal_accepted`
- `proposal_rejected`
- `phase_readiness_opened`
- `phase_transition_completed`
- `execution_native_target_opened`
- `execution_path_retry`

Event names and property schemas are versioned and validated at the adapter boundary. Unknown events are rejected in development and ignored with a diagnostic in production.

### 17.4 Local implementation

For the current single-editor application, either:

- Persist a minimal `product_events` table with event name, timestamp, pseudonymous local session, account/program identifiers, schema version, and validated JSON properties; or
- Use an in-memory/local file adapter when persistence would create unnecessary database churn during initial usability validation.

Choose one in the implementation review. In either case:

- Telemetry failure never blocks user work.
- Events do not enter `audit_events` because opening UI is not a domain mutation.
- Retention is bounded and documented.
- Export/import excludes telemetry by default.
- A local setting can disable measurement.

### 17.5 Evaluation questions

Measure the funnel needed to answer:

1. Does the page produce an eligible explainable next move?
2. Does the operator open it or choose another action?
3. Does the action close correctly, create a successor, or get snoozed?
4. Are customer waits missing internal follow-up owners?
5. Which requirement gaps recur across accounts?
6. Do program gates reach ready state before target dates?
7. Which ranking reason codes are routinely bypassed?
8. Where do coverage failures prevent a trustworthy answer?

Clicks alone do not define success. Pair telemetry with periodic qualitative review of whether the recommendation was correct and whether the page reduced navigation effort.

### 17.6 Rule refinement process

Ranking changes follow a governed process:

1. Review aggregate reason-code outcomes and qualitative examples.
2. Write a proposed rule change and expected effect.
3. Add or update deterministic ranking fixtures.
4. Compare old and new ordering over seeded mock accounts.
5. Review surprising changes.
6. Version the ranking rules and deploy behind a feature flag.
7. Record the rule version in the Execution Path response and telemetry.

Do not introduce a learned ranking model without a separate product, explainability, privacy, and evaluation specification.

### 17.7 Usability review

Run structured walkthroughs for at least:

- New account immediately after onboarding.
- Mature multi-program account.
- Blocked launch.
- Account waiting on multiple customer owners.
- Account with incomplete/partial data.
- Renewal inside the notice window.
- Narrow split-screen layout.
- Keyboard-only and reduced-motion use.

For each walkthrough, record time and navigation needed to answer the eight Product outcomes in section 2, plus any misinterpretation of owner, phase, status, or evidence.

### 17.8 Slice 7 acceptance criteria

- Telemetry contains no free-form customer content or person identifiers beyond bounded internal record IDs.
- Measurement failure cannot block Account Path.
- Account truth and ranking never read product events.
- Event and property schemas are validated and versioned.
- Export/import excludes telemetry by default.
- Ranking fixtures can compare rule versions deterministically.
- The usability walkthrough set covers all major account states and accessibility modes.
- A documented review can distinguish recommendation quality from mere click-through.

### 17.9 Slice 7 tests

- Event allowlist and property-schema validation.
- Sensitive-property rejection.
- Disabled/failing telemetry behavior.
- Retention and export exclusion if persistence is selected.
- Rule-version response and fixture comparison.
- No product-event reads from domain/status/output services.
- Walkthrough acceptance scripts for major states.

## 18. Migration and compatibility strategy

Slices 1–2 require no schema migration.

When the pillar/playbook contract is approved:

1. Preserve current `checklist_items` as historical launch records.
2. Map template keys to new stable requirement keys where deterministic.
3. Do not silently promote free-text checklist completion into evidence.
4. Keep unmatched checklist items accessible and visibly legacy/compatibility-sourced.
5. Version future playbook requirements so new templates do not retroactively rewrite active account plans.
6. Allow explicit account/program overrides and `not_applicable` reasons.

## 19. Rollout and observability

- Ship Slices 1–2 behind a local feature flag until seeded and multi-program acceptance cases pass.
- Compare the new Next best move against the existing Needs action ordering on mock accounts.
- Log coverage warnings and ranking reason codes for debugging.
- Keep the old Operate arrangement available during validation, then remove the flag after acceptance.
- Do not run a dual-write period because the first slices are read-only projections.

Initial product measures:

- Percentage of account opens with an eligible explainable next move.
- Percentage of recommended moves opened.
- Percentage resolved or advanced to a linked successor action.
- Median current-phase overdue requirement count.
- Percentage of customer waits with a named internal follow-up owner.
- Percentage of completed milestones with objective success criteria and completion notes.
- Coverage failure/partial-response rate.

These measures diagnose usefulness and data quality; they do not become an account health score.

## 20. End-to-end acceptance scenarios

### Scenario A — onboarding call just completed

1. The latest interaction has accepted Tasks and Commitments.
2. Account Path labels them as from the onboarding call.
3. The highest-priority operator-owned prerequisite becomes Next best move.
4. Customer responsibilities appear under Waiting on customer with Valence follow-up ownership.
5. Missing standard requirements appear separately under Account essentials.
6. Proposed but unaccepted transcript items remain in the proposal workflow and never appear as accepted work.

### Scenario B — multi-program account

1. The account has one program in Launch and another in Expansion.
2. All-program scope shows two lanes with independent current phases.
3. Selecting Launch excludes Expansion actions while retaining account-wide contract dates.
4. No composite account phase or percent complete is displayed.

### Scenario C — current gate blocked

1. The current program has an open blocker Risk/Issue and an incomplete current gate.
2. The path labels the current phase Blocked by the program-level blocker and names the reason without claiming an unsupported gate dependency.
3. The operator-owned blocker action becomes Next best move.
4. Completing an unrelated overdue task does not change the gate.
5. Resolving the blocker refreshes the recommendation; it does not silently advance the program phase.

### Scenario D — waiting on customer

1. No operator-owned Task is due.
2. A customer Commitment remains open with an internal follow-up owner.
3. Next best move uses the Waiting on customer variant.
4. The UI distinguishes the customer responsibility from the operator's follow-up.
5. The customer task is never falsely presented as work the operator can complete.

### Scenario E — incomplete data

1. The program has a canonical phase but no historical gates.
2. Earlier phases show Unknown, not Complete.
3. The page names insufficient plan evidence and links to Plan/Onboarding.
4. Existing activity and point-of-view sections continue to render.

## 21. Definition of done

The Account Path initiative is complete when:

1. Every active account/program can present a clear, explainable next state without duplicating canonical work.
2. Multi-program accounts remain truthful and independently scoped.
3. Accepted call actions, customer waits, standard requirements, milestones, and blockers are visually distinct but connected.
4. The pillar scorecard supplies requirement state without becoming a second task system.
5. Transcript/email updates remain proposed until explicitly accepted.
6. Requirement and milestone completion can be supported by evidence or governed waiver/exception.
7. Overview stays readable, responsive, accessible, and materially less cluttered than the complete Plan or Ledger views.
8. Today, Prepare, Leadership, Plan, Ledger, and Mutual Action Plan all continue to consume the same canonical records and truth boundaries.
9. Automated tests cover ranking, scoping, provenance, coverage, native navigation, and read purity.

Slices 1–2 satisfy the immediate release when the migration-free read model and revised Operate UI meet their detailed acceptance criteria. Slices 3–7 now have implementation-level plans, but Slices 3–4 remain gated on approval of their adjacent pillar and propose-and-accept contracts. Any contract differences discovered in that review should update this specification before implementation rather than create compatibility logic between competing models.

## 22. Research and implementation basis

This specification is grounded in:

- Existing Valence OS execution objects, guided onboarding, relative launch templates, phase gates, command-center projections, proposal acceptance, evidence links, and client-visible promotion controls.
- The separately provided Valence interview archive, especially the phased enterprise rollout, parallel adoption/value-capture workstreams, 30/60/90 planning, stakeholder conversion, and objective completion patterns.
- [Linear Timeline](https://linear.app/docs/timeline) — keep high-level timeline planning separate from granular action execution.
- [Linear Project Milestones](https://linear.app/docs/project-milestones) — use milestones as lifecycle checkpoints that organize and filter supporting work.
- [Linear Project Templates](https://linear.app/docs/project-templates) — seed repeatable projects with predefined milestones and issues.
- [Asana Project Templates](https://help.asana.com/s/article/project-templates) — anchor reusable task timing to relative project dates.
- [Gainsight Success Plan Overview](https://support.gainsight.com/gainsight_nxt/Success_Plans/About/Success_Plan_Overview) and [Create Success Plan](https://support.gainsight.com/gainsight_nxt/Success_Plans/User_Guides/Create_Success_Plan) — connect reusable objectives, tasks, owners, due dates, and timelines within the customer record.
- [Carbon Progress Indicator](https://carbondesignsystem.com/components/progress-indicator/usage/) — distinguish completed, current, future, optional, and error states while avoiding a strict stepper when work is conditional or non-linear.

External products inform the interaction patterns, not the Valence OS truth model. The canonical object boundaries, evidence requirements, proposal approval, program scoping, and client-visibility rules in this specification remain Valence-specific.
