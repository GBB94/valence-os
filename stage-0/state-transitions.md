# State transitions — v0

Valid statuses for each stateful object, the closure rules from the Section 4 "definitions of done" paragraph, and who/what can trigger each move. In v0 the only human trigger is the operator (single editor); "system" means a derived/automatic effect.

Closure always records **date, closer, and a short note** (Section 4). Nothing is hard-deleted — `archive` is available from every state (soft-delete, CLAUDE.md) and is not drawn on every diagram.

---

## Commitment

Closes when **the receiving party acknowledges completion** — not when work merely looks done.

```mermaid
stateDiagram-v2
    [*] --> open
    open --> closed : operator records acknowledgement\n(acknowledged_by, closed_on, close_note)
    closed --> open : operator reopens (correction)
```

- `open → closed`: operator, and only after the receiving party acknowledges. Requires `acknowledged_by_id`, `closed_on`, `close_note`.
- `overdue` is **not** a status — it is derived (`open AND due_date < today`) and drives the queue.
- Reopen allowed for correction; logged in audit.

## Task

Complete when **its deliverable exists**.

```mermaid
stateDiagram-v2
    [*] --> open
    open --> done : operator (deliverable exists)
    open --> cancelled : operator (no longer needed)
    done --> open : operator reopens
```

- `open → done`: operator; requires `closed_on`, `close_note`.
- `open → cancelled`: operator; requires `close_note` (why dropped).

## Risk

Closes when the risk is **no longer possible or relevant — not when mitigation begins**.

```mermaid
stateDiagram-v2
    [*] --> open
    open --> closed : operator\n(close_reason: no_longer_possible | no_longer_relevant)
    closed --> open : operator reopens (recurred)
```

- Adding `mitigation` text does **not** change status — explicit guard, since conflating the two is the named failure mode.
- `open → closed`: requires `close_reason`, `closed_on`, `close_note`.

## Issue

Resolves when the **condition is removed or an accepted workaround is operating**.

```mermaid
stateDiagram-v2
    [*] --> open
    open --> resolved : operator\n(resolution_type: condition_removed | workaround_operating)
    resolved --> open : operator reopens (recurred)
```

- `open → resolved`: requires `resolution_type`, `resolved_on`, `resolution_note`.

## Milestone

Completes when its **success criteria are met**.

```mermaid
stateDiagram-v2
    [*] --> upcoming
    upcoming --> complete : operator (criteria met)
    complete --> upcoming : operator reopens
```

- `at_risk` is a flag on `upcoming`, not a separate state. Set manually by operator, or surfaced by the queue when `upcoming AND target_date < today`.
- `upcoming → complete`: requires `completed_on`, `completion_note`.

## Decision

A decision is a **logged fact**, not an open/close lifecycle. It can only be superseded.

```mermaid
stateDiagram-v2
    [*] --> recorded
    recorded --> superseded : operator records a newer decision\n(new Decision.supersedes_id points here)
```

- `recorded → superseded`: set automatically when a new Decision cites this one via `supersedes_id`. The old decision is retained, never edited away.

## CaptureInboxItem

```mermaid
stateDiagram-v2
    [*] --> untriaged
    untriaged --> converted : operator converts\n(→ task|commitment|decision|risk|issue, no retype)
    untriaged --> dismissed : operator dismisses (not actionable)
```

- `untriaged` items remain in the attention queue until they leave this state.
- `converted`: records `converted_to_type`, `converted_to_id`, `resolved_on`, `resolved_by`.
- `dismissed`: records `resolved_on`, `resolved_by` (dismissal is auditable, not silent).

## Program (phase)

Phase is operator-judged; there is **no automatic phase advance in v0** (phase gates that would gate this are v1).

```mermaid
stateDiagram-v2
    [*] --> foundation
    foundation --> launch
    launch --> programmatic
    programmatic --> expansion
    expansion --> renewal
    renewal --> closed
    programmatic --> renewal
    launch --> closed : (abandoned)
    programmatic --> closed
    expansion --> closed
```

- All phase moves: operator only. Phases are not strictly linear — an account can skip (e.g. Programmatic → Renewal) or close early. Backward moves are allowed but audit-logged (unusual, worth a trail).
- `→ closed`: on program close, capture lessons learned, open commitments at handoff, successor brief (Section 4 lifecycle) — these are notes in v0, not new objects.

## Account (two statuses)

Two independent hand-judged statuses; **no composite** (Section 11). Each value carries rationale, `assessed_on`, and change condition.

```mermaid
stateDiagram-v2
    direction LR
    state "delivery_status" as d {
        [*] --> unknown
        unknown --> on_track
        on_track --> at_risk
        at_risk --> off_track
        off_track --> at_risk
        at_risk --> on_track
    }
```

(Commercial status has the identical shape and is fully independent — the whole point is that excellent delivery can coexist with weak commercial, or vice versa.)

- Any move: operator only. Requires updating `*_rationale`, `*_assessed_on`, `*_change_condition`.
- **Freshness rule (Section 1.7):** the interface warns when `assessed_on` is older than the 30-day reassessment interval. This is a UI warning, not an automatic status change — a manual status is *not* auto-set to unknown (only *metric-derived* indicators do that, and there are none in v0).

## AttentionState (queue overlay)

```mermaid
stateDiagram-v2
    [*] --> active : (no row — item is live)
    active --> snoozed : operator (needs return date OR resurface condition)
    active --> resolved : operator (needs closure OR linked successor)
    snoozed --> active : snooze_until passes, OR resurface_condition true,\nOR underlying facts materially change
    resolved --> active : underlying object reopens / new trigger fires
```

See `attention-rules.md` for what "materially change" means per trigger.
