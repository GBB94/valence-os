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

## 13. Migration and compatibility strategy

Slices 1–2 require no schema migration.

When the pillar/playbook contract is approved:

1. Preserve current `checklist_items` as historical launch records.
2. Map template keys to new stable requirement keys where deterministic.
3. Do not silently promote free-text checklist completion into evidence.
4. Keep unmatched checklist items accessible and visibly legacy/compatibility-sourced.
5. Version future playbook requirements so new templates do not retroactively rewrite active account plans.
6. Allow explicit account/program overrides and `not_applicable` reasons.

## 14. Rollout and observability

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

## 15. End-to-end acceptance scenarios

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

## 16. Definition of done

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

Slices 1–2 satisfy the immediate release when the migration-free read model and revised Operate UI meet their detailed acceptance criteria. Slices 3–7 remain the approved high-level path and should receive implementation-level addenda only after their adjacent contracts are finalized.
