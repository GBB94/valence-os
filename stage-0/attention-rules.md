# Attention rules — Module A portfolio queue (v0)

The queue is **rules-based and explainable, not an opaque score** (Module A). Every item states *why* it appeared, its *age*, its *due date* (if any), and its *next action*. Ranking is deterministic and in a fixed priority order.

## v0 scope of triggers

Module A lists nine deterministic sources in priority order. Several depend on objects that don't exist until later phases; those are **out of v0** and marked so. v0 ships the subset whose source objects exist in the v0 model.

| # | Priority | Trigger | In v0? | Why (source objects) |
|---|---|---|---|---|
| 1 | highest | Overdue client commitments | ✅ | Commitment (v0.2) |
| 2 | | Active blockers | ✅ | Risk/Issue with `is_blocker` (v0.2) |
| 3 | | Renewal / notice windows | ❌ v1 | needs Contract / renewal motion |
| 4 | | Failed or stale imports | ❌ v2 | needs import adapters |
| 5 | | Fired plays | ❌ v4 | needs play engine |
| 6 | | At-risk upcoming milestones | ✅ | Milestone (v0.2) |
| 7 | | Untriaged inbox items | ✅ | CaptureInboxItem (v0.1) |
| 8 | | Stale stakeholder relationships | ✅ | StakeholderRole + Interaction (v0.1) |
| 9 | lowest | Open tasks | ✅ | Task (v0.2) |

Within a priority band, items sort by **age descending** (oldest first), then by due date ascending.

## The v0 rules in detail

Each row: the exact condition that generates the item, its priority band, what **resolves** it, and what makes a **snoozed** item **resurface**.

### 1. Overdue client commitment  — *priority 1*
- **Trigger:** `commitment.status = open AND due_date < today`. (Emphasis on client-`responsible_party` commitments, but any open overdue commitment appears — none may be hidden from the morning queue, per success criteria.)
- **Shows:** description, program, responsible party, internal owner, due date, days overdue, next action = "chase / close / renegotiate due date".
- **Resolves when:** commitment moves `open → closed`, or is archived with note.
- **Snooze resurface:** `snooze_until` passes; OR a *later* interaction touches this commitment; OR due_date is renegotiated (a new overdue date recomputes age). Snoozing a still-overdue commitment cannot hide it past its return date.

### 2. Active blocker  — *priority 2*
- **Trigger:** `(risk OR issue).status = open AND is_blocker = true`.
- **Shows:** description, program, owner, age since raised, next action = "drive to closure / escalate".
- **Resolves when:** the risk closes / issue resolves, or `is_blocker` is cleared (with note).
- **Snooze resurface:** `snooze_until` passes; OR `resurface_condition` becomes true; OR a new interaction references the blocker.

### 3. At-risk upcoming milestone  — *priority 3 (band 6 overall)*
- **Trigger:** `milestone.status = upcoming AND (at_risk = true OR target_date < today)`.
- **Shows:** name, program, target date, days past/until, why-at-risk (flagged vs overdue), next action = "recover / re-baseline / complete".
- **Resolves when:** milestone completes, or `at_risk` cleared and target_date moved forward with note.
- **Snooze resurface:** `snooze_until` passes; OR target_date arrives/passes; OR still incomplete at a re-baselined date.

### 4. Untriaged inbox item  — *priority 4 (band 7)*
- **Trigger:** `capture_inbox_item.status = untriaged`.
- **Shows:** raw text excerpt, source interaction, age, next action = "convert or dismiss".
- **Resolves when:** item converts or is dismissed.
- **Snooze resurface:** `snooze_until` passes. (Success criterion pressure: fewer than five untriaged items older than three business days — the queue should make an aging item climb, so age-based sort matters here.)
- **Guard:** an untriaged item older than **3 business days** gets a visible "aging" mark even while snoozed.

### 5. Stale stakeholder relationship  — *priority 5 (band 8)*
- **Trigger:** a StakeholderRole where the person is senior (role ∈ {champion, budget_owner, program_owner}) AND `days_since_touch > 21` (three weeks; matches the morning-check scenario). Threshold configurable, not a hard-coded benchmark in copy.
- **Shows:** person, role, program, days since last meaningful touch, next action = "reach out / schedule".
- **Resolves when:** a new meaningful interaction includes that person (last-touch is derived, so this resolves automatically).
- **Snooze resurface:** `snooze_until` passes; OR `days_since_touch` crosses a further threshold (e.g. still cold after the snooze window).

### 6. Open task  — *priority 6 (band 9, lowest)*
- **Trigger:** `task.status = open`. (Overdue open tasks — `due_date < today` — sort to the top of this band.)
- **Shows:** description, program, owner, due date if any, age, next action = "do / reassign / close".
- **Resolves when:** task moves `open → done` or `cancelled`.
- **Snooze resurface:** `snooze_until` passes; OR due_date passes.

## Snooze and resolve rules (Module A, non-negotiable)

- **Snoozing requires** a `snooze_until` **date** or a `resurface_condition`. The UI refuses a snooze with neither. Snooze must never become a way to permanently hide risk.
- **Resolving requires** either the underlying object reaches a closed/resolved state **or** a **linked successor action** (a task or commitment). "Resolve" with no closure and no successor is refused.
- A snoozed item **always resurfaces** when its underlying facts materially change, even before `snooze_until`. "Materially change" per trigger is defined in each rule above (new interaction, renegotiated date, crossed threshold, reopened object).
- Snooze/resolve decisions are stored in **AttentionState** (see field dictionary §14) and are audit-logged; the queue item itself is recomputed each render.

## Explainability contract

Every rendered item carries a machine-generated `because` string built from the trigger, e.g.:
- "Overdue 6 days — client commitment 'send anonymized cohort summary' was due 2026-07-16."
- "No meaningful touch with Dana Okafor (champion) in 24 days."

No item may appear without a `because`. This is enforced in the queue builder, not by convention.
