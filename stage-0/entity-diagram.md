# Entity diagram — v0 (execution ledger)

Scope note: this diagram contains **only the objects named in Section 4** of the scoping doc, and **only the subset that v0 needs** (Section 9 v0 list). Objects named in Section 4 but deferred to a later phase are listed under "Deferred (not v0)" at the bottom — they are named so the boundary is explicit, and are deliberately absent from the diagram so nothing is scaffolded ahead.

## Diagram

```mermaid
erDiagram
    ACCOUNT ||--o{ PROGRAM : "has"
    ACCOUNT ||--o{ PERSON : "employs (client people)"

    PROGRAM ||--o{ STAKEHOLDER_ROLE : "has"
    PERSON  ||--o{ STAKEHOLDER_ROLE : "is"

    PROGRAM ||--o{ INTERACTION : "logs"
    INTERACTION }o--o{ PERSON : "participants"
    INTERACTION ||--o{ CAPTURE_INBOX_ITEM : "yields"

    PROGRAM ||--o{ TASK : ""
    PROGRAM ||--o{ COMMITMENT : ""
    PROGRAM ||--o{ DECISION : ""
    PROGRAM ||--o{ RISK : ""
    PROGRAM ||--o{ ISSUE : ""
    PROGRAM ||--o{ MILESTONE : ""

    COMMITMENT }o--|| PERSON : "responsible_party"
    COMMITMENT }o--|| PERSON : "internal_owner"
    TASK      }o--o| PERSON : "internal_owner"
    RISK      }o--o| PERSON : "internal_owner"
    ISSUE     }o--o| PERSON : "internal_owner"

    CAPTURE_INBOX_ITEM }o--o| TASK       : "converts to"
    CAPTURE_INBOX_ITEM }o--o| COMMITMENT : "converts to"
    CAPTURE_INBOX_ITEM }o--o| DECISION   : "converts to"
    CAPTURE_INBOX_ITEM }o--o| RISK       : "converts to"
    CAPTURE_INBOX_ITEM }o--o| ISSUE      : "converts to"

    SOURCE_REFERENCE }o--o{ INTERACTION : "cited by"
    SOURCE_REFERENCE }o--o{ COMMITMENT  : "cited by"
    SOURCE_REFERENCE }o--o{ DECISION    : "cited by"

    INTERACTION ..> COMMITMENT : "source_interaction"
    INTERACTION ..> RISK       : "source_interaction"
    INTERACTION ..> DECISION   : "source_interaction"
    INTERACTION ..> ISSUE      : "source_interaction"
    INTERACTION ..> TASK       : "source_interaction"
```

Two cross-cutting mechanisms are not drawn as domain entities because they are not domain objects — they are infrastructure the standing rules (CLAUDE.md) require from the first table:

- **Attention state** — a persisted overlay (snooze / resolve) keyed to a *derived* queue item. The queue itself is computed from the objects above; only the operator's snooze/resolution decisions are stored. See `attention-rules.md`.
- **Audit event** — append-only log of material changes (actor, timestamp, object, before/after, source). Points at any object; never edited by the user.

## Prose walkthrough

The model is three layers plus glue.

**Organization.** An **Account** is one enterprise relationship (e.g. a global manufacturer). It carries the two hand-judged statuses — *delivery/value* and *commercial* — that Section 11 uses in place of a composite health score. An account has one or more **Programs**. Program is the primary operating object: a bounded deployment or commercial motion with a **phase** (Foundation → Launch → Programmatic → Expansion → Renewal → Closed). A large account is genuinely in several phases at once, which is why phase lives on Program, not Account. Region, audience, and use case are program *attributes*, not hierarchy levels — there is no six-level org tree (Section 11).

**Relationship.** A **Person** is a named human — a client executive or a Valence colleague (distinguished by an affiliation flag, so a commitment's internal owner can be represented without a second object type). A person's role and stance are **per program**, not global, because the same executive can be a champion on one program and a skeptic on another. That association is the **StakeholderRole**: role (champion, budget owner, program owner, IT, legal/DPO, works-council contact), and a stance (supporter / skeptic / unconverted) that — per the Section 2 trust boundary — always carries a date and an evidence note. An **Interaction** is the foundational record: a call/meeting/email tied to a program, with participants, a summary, and a meaningful-touch flag. Last-touch dates are *derived* from interactions and never hand-edited.

**Execution.** From interactions flow the ledger objects: **Task**, **Commitment**, **Decision**, **Risk**, **Issue**, **Milestone**. The distinctive one is Commitment, which carries **two owners** — the *responsible party* (who performs it, often the client) and the *internal owner* (the Valence person accountable for driving it) — so client-owned actions cannot quietly disappear. Assumptions and dependencies are tags on these, not their own objects (Section 11).

**Glue.** Quick entry drops ambiguous notes into the **Capture Inbox** attached to their interaction; each item is later converted — without retyping — into exactly one execution object (task, commitment, decision, risk, or issue). A **SourceReference** is a reusable pointer (file, transcript span, meeting, manual entry) cited by interactions, commitments, and decisions. The **attention state** overlay and **audit event** log sit underneath everything.

## Deferred (named in Section 4, not in v0)

Present in the scoping doc, intentionally excluded from v0 so nothing is built ahead of its slice:

- **Phase gate** → v1
- **Deployment moment**, light comms entries → v1
- **Scope-change entry** → v1
- **Contract version**, **renewal motion** → v1
- **Expansion opportunity** → v1 *(see gap G1: the AGCO-style 1k→3k expansion is modeled in v0 as a `Program` in the `Expansion` phase, not as this object)*
- **Metric definition**, **metric observation** → v2
- **Value story** (incl. negative evidence), **benchmark** → v2
- **Import batch** → v2
- **Play definition**, **play run** → v4
- **Job** → deferred until the first long-running task exists (v2 imports / QBR, v4 AI); no job is needed for v0's synchronous team-update export
- Stakeholder **influence** / **relationship-strength** encodings → v3 (needed by the graph; v0 stores stance only)
