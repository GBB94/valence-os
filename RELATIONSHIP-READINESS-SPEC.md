# Valence OS — Relationship Readiness & Governed Proposals

### Final companion specification for `ACCOUNT-PATH-SPEC.md`

*v2 · August 2026 · implementation candidate*

This specification defines two shared capabilities that Account Path consumes:

1. A deterministic, evidence-backed relationship-readiness model.
2. A governed propose-and-accept workflow for intelligence extracted from calls, transcripts, and email.

It supersedes the first Relationship Readiness draft. It does not supersede `ACCOUNT-PATH-SPEC.md`; the two documents divide ownership explicitly in §0.4 and share the contracts in §§3, 7, and 11.

The product intent remains unchanged: tell the operator what is known, what is weak, what is stale, and what evidence is missing—without a composite health score and without allowing extracted content to write canonical account state until a human accepts it.

---

## 0. Decision, authority, and boundaries

### 0.1 Decision

Build a single loop over the existing system:

**source → extraction run → governed proposals → operator review → canonical records → deterministic readiness evaluation → Account Overview / Account Path**

Readiness is a query-time projection over accepted records. Proposals are inert until accepted. A proposal can create, update, or eventually link canonical records, but it cannot directly set a readiness state.

### 0.2 Product contract

The operator can open an account or program and understand:

- Which relationship conditions are evidenced.
- Which are thin, stale, conflicted, unknown, not due, or not applicable.
- Exactly which accepted records produced each conclusion.
- What action or evidence would resolve the gap.
- Which new facts from recent conversations are awaiting review.

### 0.3 Non-negotiable boundaries

- **No composite health score.** Pillars remain independent. No sum, grade, weighted average, traffic-light rollup, or hidden ranking score is stored or rendered.
- **No automatic canonical writes.** Extraction proposes; an operator accepts, edits and accepts, rejects, or resolves against an existing record.
- **No product-usage claims about named people.** Relationship evidence concerns professional roles, interactions, advocacy, commitments, commercial authority, and aggregate/value evidence.
- **No inferred durable relationships from text similarity.** Matching can suggest a link or duplicate; acceptance creates the relationship.
- **No automatic phase advancement.** Readiness can support a gate decision but cannot change `programs.phase` merely by recomputing.
- **No second action object.** Tasks, Commitments, Risks, Issues, Decisions, Milestones, and other native records remain canonical.
- **No second proposal inbox.** Existing extraction proposals are the compatibility foundation.
- **No real provider or model enabled by this spec.** Real call, email, transcript, or extraction connections remain fail-closed governance decisions.

### 0.4 Ownership with Account Path

| Capability | This spec owns | Account Path owns |
|---|---|---|
| Pillars | Stable pillar keys, versions, scope, applicability, evidence rules, evaluator contracts | How current pillar gaps appear in the execution path |
| Requirements | Canonical requirement definitions and deterministic evaluation | Playbook templates, plan instances, due-date anchoring, and current-phase presentation |
| Evidence | Allowed evidence types, evidence-component results, freshness, conflicts, provenance | Requirement detail, links to work, gate presentation |
| Proposals | Canonical proposal shape, persistence, review operations, conflicts, idempotency | Up to three scoped previews and placement of accepted native work |
| Actions | Suggested native action template only | Creation, ownership grouping, timeline placement, and next-move ranking |
| Phase gates | Evidence result supplied to gate evaluators | Governed phase-readiness and transition flow |

There must be one canonical requirement definition per condition. Account Path may adapt this service response, but it must not reimplement a readiness rule or maintain a second status for the same condition.

### 0.5 Current-system reconciliation

This design reuses what already exists:

- `extraction_runs` and `extraction_proposals` are the canonical proposal persistence foundation.
- Existing extraction run, manual-paste, accept, and reject endpoints remain supported during migration.
- `backend/app/ingestion.py` already associates recordings/transcripts and email with Accounts, Programs, Interactions, communication records, and source references.
- The existing Extraction review UI remains the complete proposal-review surface or evolves into its successor.
- `capture_inbox_items` remain manual interaction notes with `untriaged | converted | dismissed` status. They do not become a second copy of extraction proposals.
- `stakeholder_roles`, `advocacy_events`, `champion_candidates`, `interactions`, `funding_pools`, `expansion_opportunities`, `metric_observations`, `value_targets`, `value_stories`, and explicit evidence links remain canonical evidence sources.

The UI may present manual capture items and extraction proposals in one combined review experience. That is a read-model composition, not persistence duplication.

---

## 1. Research posture

### 1.1 Decision

The six seeded pillars are **operating hypotheses informed by adjacent evidence**, not validated causal predictors of Valence renewal or expansion.

The evidence base supports the direction of travel:

- Buying and expansion relationships are safer when they are not single-threaded.
- A role label is weaker than observed advocacy or economic authority.
- Satisfaction or anecdote is weaker than comparable business-outcome evidence.
- A mutual plan is stronger than a vendor-authored opportunity hypothesis.

However, much of the cited research concerns new-logo sales, B2B buying groups, or vendor-authored customer-success practice. It does not validate the exact Valence thresholds or prove post-sale causality.

### 1.2 Research labels

Definitions carry one of two internal research labels:

- `core_hypothesis` — supported by multiple adjacent signals and directly relevant to the operating model.
- `supporting_hypothesis` — logically useful or practitioner-supported, but less directly validated.

These labels are governance metadata, not UI tiers and not weights. The primary UI does not show “Tier 1” or “Tier 2.” Research detail can appear in an explanation panel.

### 1.3 Threshold governance

Starter thresholds such as three contacts, two stakeholder layers, or a 45-day touch window are versioned defaults—not timeless best practices.

Every threshold change must:

1. Create a new requirement-definition or evaluator version.
2. Preview affected account/program states.
3. Record the rationale and source basis.
4. Preserve the previous version for historical interpretation.
5. Be recalibrated against real Valence account outcomes when sufficient data exists.

No UI copy may describe a pillar as predictive, causal, or benchmarked unless that claim has a separately governed source and applicable population.

### 1.4 Research basis

- Multithreading and sales-team research: https://www.gong.io/resources/guides/the-data-backed-guide-to-multi-threading-and-team-selling
- Buying-group consensus and conflict: https://www.gartner.com/en/newsroom/press-releases/2025-05-07-gartner-sales-survey-finds-74-percent-of-b2b-buyer-teams-demonstrate-unhealthy-conflict-during-the-decision-process
- Sponsor-change operating practice: https://www.gainsight.com/blog/a-guide-to-executive-sponsor-change/
- Mutual-action-plan practice: https://www.getaccept.com/blog/mutual-action-plans

Vendor claims without a disclosed method, applicable population, or traceable primary source may inform a hypothesis but may not define a displayed benchmark.

---

## 2. Canonical pillar and requirement model

### 2.1 Pillars versus requirements

A **pillar** is a stable relationship-readiness category, such as Champion continuity.

A **requirement definition** is a versioned, evaluatable condition under a pillar, such as “A validated champion has a current meaningful touch” or “A viable second thread exists.”

Account Path playbooks reference requirement-definition versions. A pillar summary aggregates its current requirement results according to the versioned evaluator; it does not invent a separate manually editable state.

### 2.2 Definition contract

Each pillar definition has:

- Stable `key` and integer `version`.
- Label and plain-language purpose.
- `research_class`.
- Default scope: `account`, `program`, or `account_rollup`.
- Phase applicability defaults.
- Display order.
- Active/retired dates.
- Evaluator key and evaluator version.

Each requirement definition has:

- Stable `key` and integer `version`.
- Parent pillar key/version.
- Label, purpose, and definition of done.
- Default scope.
- Required/optional applicability by program phase.
- Allowed evidence types.
- Evaluator key, version, and validated configuration.
- Component-specific freshness policy.
- Suggested native action template, if one exists.
- Active/retired dates and governance rationale.

### 2.3 Code registry and governed metadata

Evaluator implementations live in an allowlisted code registry. Definition rows configure supported evaluators; they do not create executable behavior by themselves.

- An unknown evaluator key or unsupported version fails closed.
- Adding a new label or changing display order can be data-only.
- Adding a new derivation requires code, tests, and a supported definition row.
- Changing evaluator behavior requires a new evaluator version and an affected-state preview.

This avoids false configurability where adding a database row appears to add a working pillar even though no derivation exists.

### 2.4 Suggested persistence

Use the next available migration number at implementation time. Final DDL should follow repository audit, archival, and account/program-integrity conventions.

```sql
readiness_pillar_definitions (
  id, key, version, label, purpose, research_class,
  default_scope, evaluator_key, evaluator_version,
  phase_applicability_json, display_order,
  active_from, retired_at, governance_note,
  created_at, updated_at, archived, archived_at, archived_by,
  UNIQUE(key, version)
)

readiness_requirement_definitions (
  id, key, version, pillar_key, pillar_version,
  label, purpose, definition_of_done, default_scope,
  evaluator_key, evaluator_version, evaluator_config_json,
  allowed_evidence_types_json, freshness_policy_json,
  phase_applicability_json, suggested_action_json,
  active_from, retired_at, governance_note,
  created_at, updated_at, archived, archived_at, archived_by,
  UNIQUE(key, version)
)
```

Do not add a stored pillar-state table. State remains a rebuildable projection over accepted canonical records and explicit evidence links.

Account Path’s playbook and plan-instance tables reference exact requirement-definition versions. This spec does not introduce competing playbook or plan-instance storage.

---

## 3. Scope, applicability, state, freshness, and coverage

### 3.1 Scope

The service contract is:

```python
readiness.evaluate(conn, account_id, program_id=None, as_of=None)
```

- A supplied `program_id` must belong to the account and must not silently fall back when unknown, foreign, or archived.
- Omitted `program_id` means account/all-program scope.
- All-program responses preserve separate program assessments. They do not merge evidence from Program A and Program B into a synthetic `met` state.
- Account-scoped requirements can be inherited into a program view when the definition explicitly allows it.
- Program-scoped requirements never become account-wide facts merely because one program satisfies them.

### 3.2 Applicability

Applicability is independent from evidence state:

- `required`
- `optional`
- `not_due`
- `not_applicable`

Phase rules can derive `required`, `optional`, or `not_due`. An operator-set `not_applicable` decision requires a reason, actor, and date through the Account Path governed flow. It never fabricates evidence.

Example: Active expansion plan is normally `not_due` during Foundation unless an active expansion opportunity already exists or the playbook explicitly requires early expansion planning.

### 3.3 Pillar state

Readiness uses:

- `met` — every required evidence component currently satisfies the evaluator.
- `thin` — some relevant evidence exists, but the complete condition is not satisfied.
- `unknown` — the system lacks enough accepted evidence to decide.
- `conflicted` — accepted canonical records disagree on a deciding fact.
- `not_applicable` — the governed applicability result excludes the condition.

`thin` is not a percentage and `unknown` is not a negative judgment.

### 3.4 Freshness

Freshness is separate from state:

- `current`
- `stale`
- `mixed`
- `undated`
- `not_applicable`

Freshness is evaluated per evidence component. A pillar does not use the newest evidence date to make every required component appear current.

A known identity may remain known while engagement becomes stale. For example, “Aisha is the recorded budget owner, but no current engagement evidence exists” is normally `thin + stale`, not `unknown`.

### 3.5 Coverage

Every evaluation returns coverage independently from business state:

- `complete` — all required adapters/evaluators ran.
- `partial` — one or more sources or evaluators failed or were unavailable.
- `unavailable` — the result cannot be evaluated safely.

Coverage includes warnings and failed source/evaluator keys. Partial coverage cannot silently produce `met`, suppress canonical Account Path work, or claim the account is caught up.

### 3.6 Mapping to Account Path requirement states

Account Path retains its execution-oriented requirement states. The adapter maps readiness without losing detail:

| Readiness result | Account Path default mapping |
|---|---|
| `met` with allowed accepted evidence | `evidenced` |
| `thin` | `in_progress` when relevant work/evidence exists; otherwise `not_started` |
| `unknown` | `not_started` with an insufficient-evidence reason |
| `conflicted` | `blocked` with the conflicting records named |
| `not_applicable` | `not_applicable` with the governed reason |

Freshness remains a separate field. A stale `met` may map to `in_progress` or an evidence gap according to the requirement’s versioned rule; it is never silently carried forward as current evidence.

---

## 4. Seeded pillar definitions

The initial six pillars remain independent. The rules below are starter evaluator contracts and must be implemented as versioned definitions.

### 4.1 Stakeholder breadth

**Default scope:** program  
**Research class:** `core_hypothesis`

Starter `met` rule:

- At least three distinct, non-placeholder client people.
- Each has a meaningful accepted touch within the configured window.
- The set spans at least two resolved stakeholder **layers**.

The system currently has a governed role/layer taxonomy, not a reliable client business-function taxonomy. “Two functions” must not be inferred from free-text titles. A later sourced client-function field can replace or supplement the layer proxy through a new evaluator version.

`thin` examples:

- One or two current relationships.
- Three contacts concentrated in one layer.
- Required relationships exist but one or more required touch components are stale.

`unknown` means no reliable accepted contact/touch evidence exists. Placeholder people never count.

### 4.2 Champion continuity

**Default scope:** program  
**Research class:** `core_hypothesis`

Starter `met` rule:

- One current primary champion whose `people_core.effective_role` resolves to `champion` based on accepted advocacy evidence.
- A distinct viable second thread in the same program.
- Both required engagement components meet their configured freshness rules.

A raw `stakeholder_roles.role='champion'` value without advocacy evidence resolves as coach and cannot satisfy the primary-champion component.

A champion candidate at `identify` or `develop` does not satisfy continuity. A candidate at a later evidence-gated stage may qualify as the second thread only if the evaluator version explicitly permits it.

The starter second-thread definition may include a validated second champion, executive sponsor, budget owner, or program owner with accepted relationship evidence. The response names which path satisfied it; it does not reduce them to a numeric score.

### 4.3 Executive sponsorship

**Default scope:** program with explicitly inheritable account relationships  
**Research class:** `core_hypothesis`

Components:

1. A non-placeholder executive-layer stakeholder is identified.
2. The executive has a current meaningful interaction or accepted relationship evidence.
3. The executive is explicitly linked to the metric/value outcome they own or sponsor.

Free-text similarity between `persons.metric_judged_on` and `metric_definitions.owner` is not an explicit link.

Until a typed stakeholder-to-metric/value relationship exists, the evaluator can report identified and engaged components but cannot claim full value alignment. The pillar therefore caps at `thin` unless accepted explicit linkage evidence exists.

### 4.4 Quantified value

**Default scope:** program where the measurement is program-specific; otherwise account  
**Research class:** `core_hypothesis`

Starter `met` rule:

- An explicit baseline observation is locked or linked.
- A later comparison observation exists.
- Both use the same metric definition and compatible definition version.
- Program, population/cohort, unit, and measurement basis are comparable.
- The comparison is current under the metric’s own freshness rule.
- Supporting evidence is accepted and not archived, retracted, or suppressed.

`value_targets` are negotiated target bars, not baseline observations. A target may support agreement on the goal but cannot satisfy the baseline component.

`value_stories` with `measured_operational` or `correlated_business` evidence can support the narrative/result component, but they do not fabricate a baseline. `anecdote`, `client_quote`, satisfaction, or NPS-only evidence remains `thin` when relevant and `unknown` when no comparable measurement basis exists.

Where an adoption campaign already has an explicit locked baseline observation, the evaluator reuses it. Any broader baseline/after relationship added later must be an explicit typed relation, not inferred solely by dates.

### 4.5 Budget owner identified

**Default scope:** account, with optional program/opportunity relationship  
**Research class:** `supporting_hypothesis`

Components:

1. A non-placeholder person has accepted budget authority evidence.
2. The authority is tied to a relevant funding pool, expansion opportunity, operational agreement, or other allowlisted commercial record.
3. Engagement freshness is evaluated separately from identity/authority.

Budget-owner facts may appear in stakeholder roles, funding pools, and expansion opportunities. If accepted current records name different people for the same commercial scope, the pillar is `conflicted`; it does not choose one silently.

An inferred title, a champion without authority evidence, or an unconfirmed potential funding source cannot produce `met`.

### 4.6 Active expansion plan

**Default scope:** program/opportunity  
**Research class:** `supporting_hypothesis`

Starter `met` rule:

- An open expansion opportunity exists in scope.
- It has a named client-side owner or sponsor.
- It has a dated next action or explicit linked milestone.
- It has a live, applicable budget state.
- Accepted source evidence demonstrates client acknowledgement or co-ownership.

An operator-authored internal hypothesis alone is `thin`, even when its fields are populated. Free-text `supporting_evidence` can provide context but does not automatically prove mutuality.

This pillar is normally `not_due` in early phases unless an active opportunity makes it relevant. Full mutual-plan claims should use the typed evidence/relationship model delivered with the Account Path Slice 5 integration.

---

## 5. Evaluation and evidence response

### 5.1 Deterministic evaluation

Models may propose canonical facts, but models never calculate accepted readiness state. Evaluators are deterministic, allowlisted, versioned, and testable.

Each evaluator:

- Reads accepted, non-archived canonical records.
- Validates account/program scope.
- Produces independent evidence components.
- Applies component-specific freshness.
- Reports conflicts rather than resolving them through precedence hidden from the user.
- Returns coverage independently from state.
- Writes nothing.

### 5.2 Response shape

```json
{
  "scope": {
    "account_id": "acc-bluepeak",
    "program_id": "prog-bluepeak-launch"
  },
  "as_of": "2026-08-04",
  "coverage": {
    "status": "complete",
    "warnings": [],
    "failed_evaluators": []
  },
  "pillars": [
    {
      "key": "champion_continuity",
      "definition_version": 1,
      "evaluator_version": 1,
      "label": "Champion continuity",
      "research_class": "core_hypothesis",
      "scope": "program",
      "applicability": "required",
      "state": "thin",
      "freshness": "mixed",
      "reason": "A validated champion is current; the second thread is stale",
      "components": [
        {
          "key": "primary_champion",
          "state": "met",
          "freshness": "current",
          "assessed_through": "2026-07-30",
          "evidence": [
            {"type": "advocacy_event", "id": "adv-1", "label": "Presented internally"}
          ]
        },
        {
          "key": "second_thread",
          "state": "thin",
          "freshness": "stale",
          "assessed_through": "2026-05-15",
          "evidence": [
            {"type": "stakeholder_role", "id": "role-2", "label": "Executive sponsor"}
          ]
        }
      ],
      "missing": ["Record a current meaningful touch with the second thread"],
      "suggested_action": {
        "native_type": "task",
        "title": "Re-engage the second relationship thread"
      }
    }
  ]
}
```

`suggested_action` is a template, not open work. It enters Account Path ownership only after the operator creates or accepts a native Task or Commitment.

### 5.3 Evidence confidence and provenance

Evidence includes a provenance quality separate from business state:

- `confirmed_source` — supported by an accepted source reference, interaction, or explicit evidence record.
- `operator_recorded` — accepted manual record without an external/source artifact.
- `unsupported` — structurally present but insufficient for an evidence-required component.

Unsupported evidence can explain why a condition is thin; it cannot silently satisfy an evidence-required definition.

---

## 6. Canonical proposal architecture

### 6.1 Reuse decision

Widen `extraction_runs` and `extraction_proposals`; do not add parallel `intake_runs`, `intake_items`, or proposal payloads to `capture_inbox_items`.

Source adapters should reuse:

- `source_references` for provenance.
- `interactions` for calls/meetings when applicable.
- `comm_messages` for email identity and threads.
- Existing association confidence and low-confidence triage.
- Existing extraction persistence and review endpoints during compatibility migration.

### 6.2 Proposal intent

Separate intent from native target:

- `create`
- `update`
- `link`
- `close`
- `no_change`

The first widening enables `create` and allowlisted `update`. `link` and `close` remain disabled until the typed relationship and governed closure contracts from Account Path Slice 5 exist. `no_change` is normally hidden but retained for audit/deduplication where useful.

### 6.3 Allowlisted targets

Initial targets may include:

- Task, Commitment, Risk, Issue, and Decision.
- Interaction or source association correction.
- Stakeholder role and allowlisted dated/evidenced relationship fields.
- Champion candidate.
- Pull signal, funding signal, expansion signal/opportunity field.
- Value story.
- Other targets only after a strict payload schema and native write path exist.

No proposal may directly set a pillar, requirement, composite status, program phase, named-person product usage, or client-visible artifact state.

### 6.4 Normalized proposal contract

```json
{
  "id": "proposal-789",
  "run_id": "run-456",
  "account_id": "acc-bluepeak",
  "program_id": "prog-bluepeak-launch",
  "source": {
    "kind": "interaction",
    "id": "int-123",
    "source_reference_id": "src-123",
    "external_id": "provider-item-42",
    "content_hash": "sha256:...",
    "label": "August 3 onboarding call",
    "span": "Aisha will send the HR calendar by Friday",
    "locator": "00:14:22-00:14:31"
  },
  "intent": "create",
  "target_type": "commitment",
  "target_id": null,
  "expected_target_updated_at": null,
  "payload": {
    "description": "Send the HR calendar",
    "responsible_party_id": "person-aisha",
    "internal_owner_id": "person-zach",
    "due_date": "2026-08-07"
  },
  "status": "proposed",
  "confidence": "high",
  "validation_warnings": [],
  "match_candidates": [],
  "resolved_target": null,
  "proposal_fingerprint": "sha256:...",
  "created_at": "2026-08-04T14:30:00Z"
}
```

Confidence is explanatory metadata. It never auto-accepts, ranks above canonical work, or relaxes validation.

### 6.5 Suggested schema widening

Final migration mechanics must preserve existing rows and APIs during rollout. SQLite CHECK changes may require table reconstruction and compatibility backfill.

`extraction_runs` should add or normalize:

- Provider/source kind.
- External source identity and content hash.
- Backend/model/prompt versions.
- Run status supporting `running | completed | partial | failed` while preserving compatibility with current rows.
- Counts and structured error/coverage detail.

`extraction_proposals` should add or normalize:

- `intent` and `target_type`, backfilled from `mutation_type`.
- Optional `target_id` and `expected_target_updated_at` for updates.
- Source reference, exact source span, and locator.
- Validated payload JSON.
- Proposal fingerprint.
- Validation warnings.
- Rejection reason.
- Resolution status including `accepted`, `rejected`, `resolved_existing`, and `superseded`.
- Created/updated/resolved target type and ID.

Retain or expose legacy `mutation_type` until every reader uses the normalized contract.

### 6.6 Idempotency

`external_id` alone is insufficient. A provider item can be corrected, retranscribed, or reprocessed with a new extractor.

Use both:

1. A source-version identity derived from provider, external ID, content hash, and source kind.
2. A proposal fingerprint derived from normalized intent, target type, scoped payload, source span/locator, and extractor/prompt version as appropriate.

Repeated acceptance returns the existing resolved target or a stable conflict. It never creates a duplicate canonical record.

### 6.7 Duplicate and conflict handling

Before acceptance, deterministic matching is restricted to the same account/program scope and checks:

1. An identical source proposal already resolved.
2. Exact normalized target content.
3. Owner/responsible-party/date identity for Tasks and Commitments.
4. A newer accepted value for the same target field.
5. Known target-specific unique identities.

Possible matches are suggestions, not automatic merges.

Review resolutions:

- Accept.
- Edit and accept.
- Reject with a reason.
- Use existing.
- Supersede with a newer proposal where allowed.

For updates, the UI shows current value, proposed value, both source dates, and the target’s current `updated_at`. A stale proposal returns a conflict preview instead of overwriting newer state.

### 6.8 Security and trust

- Source content is untrusted data even after prompt-injection screening.
- Extractor output must pass strict schema validation.
- Every proposal requires source provenance appropriate to its type.
- Acceptance revalidates the final edited payload against the native service schema.
- Acceptance executes through native audited insert/patch/closure/link operations in one transaction.
- Cross-account or cross-program targets are rejected.
- A low-confidence or unresolved source association cannot mutate account state.
- There is no first-release “Accept all.”

Prompt-injection screening is defense in depth, not a guarantee that content is safe or true.

---

## 7. API contracts

### 7.1 Readiness

```text
GET /api/accounts/{account_id}/readiness?program_id={program_id}&as_of={date}
GET /api/accounts/{account_id}/readiness/{pillar_key}/evidence?program_id={program_id}
```

Unknown, archived, or foreign programs return `404` or a scoped validation error; they do not fall back to account scope.

### 7.2 Proposal reads

```text
GET /api/accounts/{account_id}/proposed-updates
    ?program_id={program_id}
    &source_interaction_id={interaction_id}
    &status=proposed

GET /api/extraction/runs/{run_id}
```

The account endpoint groups proposals by source and target type and returns exact provenance, warnings, conflicts, and match candidates.

### 7.3 Proposal commands

```text
POST /api/extraction/proposals/{proposal_id}/accept
POST /api/extraction/proposals/{proposal_id}/reject
POST /api/extraction/proposals/{proposal_id}/resolve-existing
POST /api/extraction/proposals/{proposal_id}/supersede
```

Existing accept/reject routes remain compatible. Edit-and-accept supplies allowlisted overrides to `accept` and revalidates them transactionally.

### 7.4 Evaluator-version preview

Before changing an active evaluator/definition version, expose an internal operation equivalent to:

```text
POST /api/readiness/definition-upgrades/preview
```

It reports affected account/program scopes and state transitions without applying the new version.

---

## 8. Information architecture and UI

### 8.1 Placement

No new top-level destination is added.

- **Account Overview / Operate** shows a compact readiness summary.
- **Account Path / Account essentials** consumes the same response and shows at most three current-phase required gaps.
- **Plan requirement detail** shows the complete condition, evidence, freshness, missing components, and governed actions.
- **Extraction/Inbox review** remains the full proposal-review experience.
- **Overview** may show up to three proposals from the latest interaction plus a review-all link.
- **Today** shows one deduplicated proposal-review-debt item per account when thresholds are exceeded.
- **Operations** shows runs, proposal outcomes, failures, freshness, coverage, and connection modes.

### 8.2 Reusable components

Implement one data contract with presentation modes:

- `ReadinessSummary mode="compact"` — at most three relevant gaps for Overview/Account essentials.
- `ReadinessSummary mode="all"` — all independent pillars in the focused detail view.
- `ReadinessDetail` — component evidence, freshness, conflicts, definition of done, and suggested action.
- `ProposalPreview` — scoped pending count and latest-source previews.

The compact mode prevents the readiness work from becoming a large scorecard that Account Path later replaces.

### 8.3 Visual rules

- Never render a composite grade, completion percentage, or giant status metric.
- Pair state color with label and glyph; color is never the only signal.
- Show freshness separately from state.
- Make `unknown`, `stale`, `conflicted`, `not_due`, and `not_applicable` visually distinguishable.
- State reasons use plain language and name the deciding component.
- Evidence opens the native record or source location.
- Suggested actions look different from accepted Tasks/Commitments.
- Proposal cards look proposed-and-cited, not asserted.
- Dense details open progressively; Overview remains calm and scannable.

### 8.4 Interaction rules

- Keyboard and screen-reader proposal review remains supported.
- Focus moves predictably after accept/reject/use-existing.
- Pending controls disable while a mutation is in flight.
- Reduced-motion preferences are respected.
- Evidence and conflict dialogs preserve focus and announce state changes.
- Full proposal payload JSON is not the default user experience.

---

## 9. Connections and governance

Reuse and correct existing connection boundaries rather than implying that fixtures constitute approved production ingestion.

### 9.1 Source connections

Calls, transcripts, and email providers require separate approved connection rows or provider-specific configuration covering:

- Provider and lawful-use approval.
- Works-council/privacy review where applicable.
- Allowed data classes.
- Retention and deletion/correction path.
- Credential owner and rotation.
- Logging and rollback.
- Attachment and quoted-thread handling.
- Association-confidence policy.

### 9.2 Extraction endpoint

The transcript/email extraction payload is a distinct LLM connection class. It does not inherit approval from Account Copilot.

Mock fixtures may include transcripts and deterministic pre-extracted proposals so that persistence and review flows can be tested without making a real model call.

### 9.3 Email-specific requirements

Email ingestion preserves:

- Message and thread identity.
- Sender, recipients, and sent time.
- Account/program association confidence.
- Quoted-text boundaries.
- Attachment/source references.
- Content hash and corrected-message identity.

Repeated thread history must not produce repeated proposals. Low-confidence email association stays in association/capture review until confirmed.

---

## 10. Delivery plan

Use `RR` slice labels to avoid assuming a migration/stage number that may conflict with parallel work.

### RR-0 — Canonical contract and compatibility migration

Deliver:

- Versioned pillar and requirement definitions.
- Allowlisted evaluator registry and version-preview mechanism.
- Scope, applicability, state, freshness, evidence-component, and coverage contracts.
- Exact compatibility plan for Account Path requirement definitions.
- Migration tests and seeded definitions.

Exit criteria:

- Account Path Slice 3’s entry gate is satisfied: stable keys, versions, scope, applicability, evidence, freshness, and override boundaries are approved.
- Unknown evaluators fail closed.
- No state table, composite score, duplicate requirement definition, or duplicate playbook model is introduced.

### RR-1 — Read-only readiness service and reusable UI

Deliver:

- Program-aware deterministic evaluation for all six pillars.
- Component-level freshness and evidence.
- Conflict and partial-coverage handling.
- Compact and all-detail UI modes.
- Evidence drill-through.
- Operations evaluation coverage.

Exit criteria:

- Hand-entered accepted records produce explainable results.
- Multi-program accounts never leak or merge program evidence.
- The Overview implementation can be consumed unchanged by Account Path’s Account essentials adapter.

### RR-2 — Canonical proposal widening

Deliver:

- Migration/backfill over existing extraction runs/proposals.
- Normalized intent/target response.
- Source and proposal fingerprints.
- Allowlisted create/update operations.
- Optimistic concurrency, duplicate matching, conflict preview, rejection reason, and Use existing.
- Combined review read model without copying proposals into `capture_inbox_items`.
- Latest-interaction preview and review-debt queue item.

Exit criteria:

- Account Path Slice 4’s entry gate is satisfied.
- Existing accepted/rejected extraction history remains readable.
- Reprocessing and repeated acceptance are idempotent.
- No second proposal persistence model exists.

### RR-3 — Explicit evidence relationships and stronger claims

Coordinate with Account Path Slice 5.

Deliver or reuse typed links for:

- Requirement evidence.
- Stakeholder-to-metric/value ownership.
- Opportunity/client acknowledgement or mutual-plan evidence.
- Requirement/action and milestone/action relationships where Account Path owns them.

Enable stronger executive-value, mutual-plan, gate-impact, and evidence-based completion claims only after the corresponding explicit links exist.

### 10.1 Sequence with Account Path

```text
Account Path Slices 1–2 may proceed independently
RR-0 → Account Path Slice 3
RR-1 → Account Path readiness presentation
RR-2 → Account Path Slice 4
RR-3 ↔ Account Path Slice 5
```

---

## 11. Acceptance criteria

### 11.1 Contract and derivation

- Stable pillar and requirement keys are versioned.
- Evaluator versions are recorded and previewable before activation.
- Account and program scopes are explicit and enforced.
- Required, optional, not-due, and not-applicable semantics are independent from state.
- State and freshness are independent.
- Every deciding component explains itself and links to accepted evidence.
- Partial coverage is visible and cannot silently produce a reassuring result.
- No product-usage field, composite score, or manually editable pillar state exists.

### 11.2 Pillar false-positive tests

- Three contacts in one layer do not satisfy breadth.
- Contacts from another program do not satisfy the selected program.
- Placeholder people never count.
- A tagged champion without advocacy evidence reads as coach.
- One validated champion without a viable second thread is thin.
- A second-thread candidate below the allowed evidence stage does not satisfy continuity.
- A named executive without current engagement is thin/stale.
- An engaged executive without an explicit metric/value link does not produce full `met`.
- A value target does not count as a baseline.
- Baseline and after observations with different metric versions, populations, units, or programs do not compare.
- Anecdotal, satisfaction, or NPS-only value evidence does not produce quantified-value `met`.
- Conflicting budget owners produce `conflicted`.
- A populated internal expansion opportunity without client acknowledgement remains thin.
- Active expansion plan is not due in an early phase unless made relevant by the plan or an active opportunity.

### 11.3 Freshness and coverage tests

- A fresh component does not mask a stale required component.
- Known identity plus stale engagement remains explainable rather than collapsing to unknown.
- Undated evidence is labeled undated and follows its definition rule.
- Archived, superseded, or retracted evidence no longer supports a result.
- Evaluator/source failure returns partial or unavailable coverage.
- Partial coverage never suppresses Account Path canonical work.

### 11.4 Proposal tests

- Strict schemas reject unknown intents, targets, and fields.
- Every proposal retains exact source provenance.
- Extraction never writes canonical state.
- Accept and edit-and-accept revalidate through native services.
- Reject creates no canonical record and records its reason where required.
- Use existing resolves without creating a duplicate.
- Repeated acceptance returns the same target or stable conflict.
- Reprocessing identical source content does not re-propose resolved facts.
- Corrected content can produce a new source version without losing history.
- Older evidence never silently overwrites newer accepted state.
- Concurrent acceptance creates or updates at most one canonical target.
- Cross-account/program targets are rejected.
- Low-confidence associations cannot mutate account state.
- Prompt-injection text remains untrusted and cannot expand the allowlist.

### 11.5 UI and accessibility tests

- Overview shows no more than three current relevant gaps in compact mode.
- All pillars remain independently accessible in the detailed view.
- State, freshness, applicability, and coverage are not communicated by color alone.
- Evidence links open the correct native target or source.
- Suggested actions are not mistaken for open work.
- Proposed updates are not mistaken for accepted facts.
- Keyboard and screen-reader proposal review is complete.
- Loading, empty, partial, error, stale, conflict, and no-access states are designed and tested.

---

## 12. Explicit non-goals

- A predictive churn or expansion model.
- A composite customer-health framework.
- Automatic proposal acceptance.
- Automatic program-phase advancement.
- A generic project-management replacement.
- A new capture/proposal persistence system.
- Production Fireflies, Microsoft Graph, Gmail, or extraction-model activation.
- Individual product-usage tracking.
- Inferring client business function from titles.
- Inferring durable evidence links solely from text or dates.
- Treating vendor research as a Valence benchmark.

---

## 13. Final decision summary

This specification is ready for implementation once accepted with `ACCOUNT-PATH-SPEC.md` as its companion authority.

The build should begin with RR-0 and RR-1. Those slices establish a truthful, program-aware readiness contract and reusable UI without waiting for automated ingestion. RR-2 then upgrades the proposal system already in the product rather than creating a parallel one. Account Path consumes the resulting contracts in Slices 3–5.

The architecture succeeds only if it preserves four truths:

1. Readiness is derived from accepted evidence.
2. Weak, stale, missing, conflicted, and not-yet-applicable are different conditions.
3. Proposed intelligence is not canonical work until a human accepts it.
4. Account Path orchestrates these capabilities without duplicating their state.
