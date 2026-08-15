# Valence OS — Adoption Campaign Engine Spec
### Cohort-level interventions that turn deployment intent into sustained behavior
*v2 · August 2026 · **accepted as Stage 11 authority** (Zach, 2026-08-01, D-99) · additive addendum after Stage 10*

**What changed in v2 (adversarial review against the built system).** v1's product boundaries were
sound and are unchanged; the revisions are all in the measurement contract, where the spec would
have rendered numbers that look like evidence and are not:

- **Regression to the mean is now named and mitigated (§5.2).** `_stalled_candidates` selects a
  cohort *because* its latest reading fell, then v1 locked the baseline at that trough and reported
  a bare pre/post delta. A noisy metric measured after a trough rises with no intervention at all.
  Signal-triggered `pre_post` now renders the pre-campaign trajectory with a standing caution, and
  the UI proposes `comparator` as the default design.
- **The baseline locks a series, not a point (§5.1).** Prior observations already exist — the
  stalled signal requires two — so capturing them costs nothing and is what lets a reader tell
  "the intervention moved it" from "it was already moving."
- **Comparators must be disjoint from the treated cohort (§5.2).** Views overlap segments by
  construction here, so v1 permitted a control that contains the treated. Reuses
  `stage75._members()`.
- **A rolled-back baseline invalidates the comparison (§5.1).** Import rollback archives
  observations; v1 would have kept showing a delta from a retracted number.
- **Seasonality is called out (§5.2)** because the module targets review cycles and survey seasons.
- **§7.1's migration-risk justification was factually wrong and is corrected** —
  `signal_episodes.kind` has no CHECK; the deferral now stands on scope grounds.
- **§8's cited Stage 9 matching rule was a live bug when v2 was drafted and has since been fixed
  (D-94)**; the section now records the corrected invariant rather than a prerequisite.

## 0. Decision, boundary, and sequencing

Valence OS already knows the account, program, target population, deployment moment, champion,
aggregate metric, value target, execution work, and expansion cell. What it cannot currently answer
is: **what deliberate intervention are we running to change adoption in this cohort, why should it
work, and did the behavior change afterward?**

That missing layer is an adoption campaign. It is not marketing automation and it is not another
project plan. A campaign is a time-boxed, measurable intervention inside an existing program,
against one stable cohort and use case, assembled from records the app already owns.

This proposal follows Stage 10. It does not interleave with the in-progress Internal Ops migrations.
*Accepted 2026-08-01 (D-99): this document now sits at the repository root and is named in the
`CLAUDE.md` authority chain. The acceptance condition below is satisfied and retained for history.*

If accepted, it becomes the Stage 11 authority only after moving to the repository root and updating
`CLAUDE.md`, `README.md`, `HANDOFF.md`, and `decisions.md` in one deliberate scope change.

### 0.1 The one-sentence product contract

For a named aggregate cohort, the operator can diagnose the adoption barrier, state the behavior to
change, lock the evidence bar, sequence interventions through existing execution records, and learn
whether the cohort improved—without storing named-person usage or pretending correlation is causation.

### 0.2 What a campaign is not

- **Not a Program.** A program remains the bounded deployment or commercial motion. One program may
  contain several campaigns over time or across cohorts.
- **Not a Play.** A play is a trigger and proposed response. A campaign is the accepted execution
  instance with dates, people, evidence, interventions, and an outcome.
- **Not a Deployment moment.** A moment is a client event or workflow anchor. A campaign may align
  to one or more moments.
- **Not a task list.** Tasks, commitments, milestones, communications, calendar events, and generated
  artifacts remain canonical. A campaign orders and explains links to them; it does not clone them.
- **Not a user-level journey.** The unit is a segment or privacy-safe population view. There is no
  recipient list, named-person activation field, individual funnel, or user-level message history.
- **Not a sending system.** Communications remain planned/recorded locally. No email, Teams message,
  in-product prompt, or notification is sent automatically.
- **Not an attribution engine.** The app reports observed before/after and comparator facts. It never
  writes “the campaign caused X” unless that claim arrives as externally sourced evidence.

### 0.3 Reconciliation with the built system

| Existing capability | Reuse | What the campaign adds |
|---|---|---|
| `programs` | Required parent and operating context | Multiple measurable interventions inside one program |
| population segments/views | Exact cohort identity and privacy floor | One required target cohort; no free-text audience |
| whitespace cells | Optional cohort × use-case target and cross-account shape | Campaign-to-cell link with account/population enforcement |
| value targets + metric observations | Measurement bar, baseline, current value, freshness | Locked baseline and campaign evaluation window |
| deployment moments | Workflow/calendar anchor | Ordered intervention link and timing rationale |
| tasks, commitments, milestones | Canonical work and ownership | Ordered plan links; completion remains derived from the child record |
| comms entries + calendar events | Planned/recorded touches | Ordered communication and live-event links; no auto-send |
| champions + stakeholder roles | Sponsor, champion, delivery owner | Campaign roles without inventing a second people model |
| messaging library | Role/layer-specific message guidance | Which message was used and why, via a link rather than copied prose |
| plays + signal episodes | Explainable detection and recurrence | Explicit operator conversion into a draft campaign |
| generated artifacts + MAP | Existing client-safe materials and joint milestones | Links only; no new document kind or parallel mutual-plan machinery |
| playbook library | Cell-shape learning from expansion transitions | Completed campaigns become their own queryable evidence set |
| Stage 10 product feedback | Friction themes and closed-loop learning | Optional barrier evidence and outcome feedback link |

## 1. Research-derived design principles

The research supports the module, but it does not justify importing an enterprise change-management
suite into a five-account personal tool.

1. **Start with the behavior and the barrier.** The COM-B model frames behavior as requiring
   capability, opportunity, and motivation. The app uses those three categories only as a compact
   diagnosis vocabulary; it does not implement a proprietary assessment or score.
2. **Anchor adoption in work, not awareness alone.** Microsoft’s adoption guidance combines
   organizational engagement, training, champions, community, and governance. A campaign therefore
   needs an intervention sequence that can mix enablement, workflow embedding, champion action,
   communication, and reinforcement.
3. **Target a cohort and an observable outcome.** Product-adoption guidance distinguishes breadth,
   depth, and return behavior and recommends segment-specific intervention. Valence OS does not
   adopt any vendor formula: the Data team’s versioned metric definition remains canonical.
4. **Triggers should propose a response, not become the response.** Customer-success adoption
   playbooks commonly trigger on an adoption change or lack of recent intervention. That maps to the
   existing signal/play engine, with explicit human acceptance before a campaign exists.
5. **Planning needs reinforcement.** Behavior-change research supports specific action/coping plans
   and repeated reinforcement. Every campaign therefore states the cue, action, likely barrier, and
   reinforcement step rather than ending at launch communication.
6. **Privacy is structural.** Microsoft’s own adoption reporting emphasizes organizational and group
   aggregates. This module inherits the repository’s stronger rule: cohorts only, suppression below
   the configured floor, and no named-person product usage anywhere.

Research basis:

- [Microsoft 365 adoption journey and champion resources](https://adoption.microsoft.com/en-us/microsoft-365/)
- [Microsoft Adoption Score privacy and organizational-level measurement](https://learn.microsoft.com/en-us/microsoft-365/admin/adoption/adoption-score?view=o365-worldwide)
- [Prosci ADKAR overview, including reinforcement](https://www.prosci.com/methodology/adkar)
- [COM-B / Behaviour Change Wheel original paper](https://pubmed.ncbi.nlm.nih.gov/21513547/)
- [Pendo feature-adoption dimensions](https://www.pendo.io/glossary/feature-adoption/)
- [Gainsight adoption playbooks](https://www.gainsight.com/marketplace/item/adoption-playbooks/)
- [Systematic review of reinforced implementation intentions](https://pmc.ncbi.nlm.nih.gov/articles/PMC6235272/)

No external benchmark or claimed lift from those sources is stored or hard-coded. They shape the
workflow only.

## 2. Campaign identity and lifecycle

### 2.1 Required identity

Every campaign belongs to exactly one account and program and targets exactly one stable population
segment or population view. It may also link to the matching whitespace cell. If a cell is linked,
its account and population must match the campaign, and its use case supplies the campaign use case.
Without a cell, the campaign names a portfolio-global or account-specific `use_case_id` directly.

Each campaign carries:

- name;
- account, program, target population, and use case;
- target behavior in plain language at cohort level;
- intervention hypothesis: “If we do X at Y moment, this cohort should do Z because …”;
- planned start and end dates;
- one canonical internal owner on the campaign;
- client sponsor and lead campaign champion where known;
- evaluation design and primary value target;
- status and append-only state history;
- source references for the diagnosis and any client-agreed plan.

### 2.2 Lifecycle

| Status | Meaning | Entry rule |
|---|---|---|
| `draft` | Being formed; gaps are expected | Created manually or from an accepted signal/play |
| `ready` | The intervention and measurement contract are defensible | Readiness check passes or each exception is reason-logged |
| `active` | The planned intervention window has started | Explicit operator action; never time-triggered automatically |
| `paused` | Work intentionally stopped | Pause reason, owner, and resume condition/date required |
| `completed` | Outcome reviewed after the evaluation window | Completion outcome, dated review, and evidence required |
| `cancelled` | Will not run or stopped without evaluation | Cancellation reason and date required |

Status is never patched generically. Dedicated transition endpoints enforce the rules and append
history. A completed or cancelled campaign is immutable except for archival and an additive
retrospective amendment.

### 2.3 Readiness contract

A campaign is ready when it has:

1. stable cohort and use-case identity;
2. target behavior and intervention hypothesis;
3. active dates and internal owner;
4. primary value target with compatible population identity;
5. a fresh, privacy-safe baseline observation locked by record ID — plus its prior-trajectory
   snapshot where prior observations exist (§5.1) — or a reason explaining why the campaign is
   deliberately starting without one;
6. at least one diagnosed barrier with dated evidence;
7. at least one actionable linked intervention (not merely a messaging-library reference) and one
   later reinforcement/checkpoint step;
8. a client sponsor or an explicit “sponsor not yet secured” gap;
9. a measurement/evaluation date after the intervention window.

Identity, target behavior/hypothesis, dates, internal owner, primary value target, an actionable
intervention, reinforcement, and evaluation date are non-waivable. Baseline and client sponsor gaps
may be waived only with a reason; a barrier may remain `unknown`, but the uncertainty itself needs a
dated source. This keeps the Internal Ops soft-evidence posture without allowing an activity list to
masquerade as an adoption campaign. The operator cannot accidentally mistake “active” for
“measurable.”

## 3. Barrier diagnosis

Campaigns fail when the tool records activity but not why behavior is not changing. A campaign has
one or more cohort-level barrier observations:

| Category | Question | Typical intervention |
|---|---|---|
| `capability` | Does the cohort know how to perform the desired behavior? | enablement, examples, office hours, practice |
| `opportunity` | Does workflow, access, timing, policy, or manager support permit it? | workflow embedding, gate removal, manager action |
| `motivation` | Does the cohort see sufficient relevance, trust, or social proof? | champion story, value framing, peer proof, reinforcement |
| `unknown` | Evidence is not strong enough to diagnose yet | discovery workshop, aggregate survey, observation plan |

Each barrier carries a description, observed-on date, source reference or interaction, confidence
(`observed`, `reported`, `hypothesis`), and resolution state. These are professional, cohort-level
observations. The schema offers no person ID for “affected user” and no field for individual usage.

A campaign may address several barriers, but one is marked primary. The interface does not compute
a readiness or ADKAR score.

## 4. The intervention sequence

### 4.1 Reuse canonical execution records

The campaign plan is an ordered list of typed links. Each item points to exactly one existing record:

- task;
- commitment;
- milestone;
- comms entry;
- deployment moment;
- calendar event;
- generated document;
- messaging-library entry.

The association stores sequence, intervention kind, intended barrier, purpose, and whether the item
is the reinforcement step. It does **not** store a second due date, owner, send status, or completion
status. Those derive from the linked object where that object has an operational state, so the
campaign cannot disagree with the Ledger or Plan. A messaging-library reference supplies message
guidance only and never satisfies the readiness requirement for an actionable intervention.

Typed nullable foreign keys plus an exactly-one `CHECK` are required. An unchecked
`linked_type`/`linked_id` pair is not acceptable.

### 4.2 Intervention vocabulary

The compact initial vocabulary is:

- `enablement`;
- `workflow_embed`;
- `champion_led`;
- `manager_reinforcement`;
- `communication`;
- `office_hours_or_live_support`;
- `friction_removal`;
- `social_proof`;
- `measurement`.

This is an intervention classification, not a new task type. It exists to compare completed
campaigns and to prevent a plan containing five communications from masquerading as a strategy.

### 4.3 Cue–action–reinforcement discipline

At least one plan item names the cue or deployment moment it responds to. At least one later item is
marked reinforcement. The campaign view renders the sequence as a table, not a journey diagram:

`cue/date → intervention → owner → linked record state → intended barrier → evidence checkpoint`

No plan item sends or closes itself. Scheduled jobs may create a draft or Today item, never an
external action.

## 5. Measurement and honest evaluation

### 5.1 The measurement contract

The primary outcome is an existing `value_target`; optional secondary and guardrail targets use the
same table. Campaign target links declare `primary`, `secondary`, or `guardrail` and cannot point
across accounts or populations.

The baseline locks an exact metric-observation record when the campaign becomes ready. The app may
compare ingested values but never recomputes the metric definition. The current/post observation is
selected only when it matches definition, definition version, population identity, unit, and the
campaign’s evaluation window. A program-scoped observation must either belong to the campaign
program or be explicitly account/cohort-scoped with no conflicting program.

**The baseline locks a series, not a point.** Alongside the single baseline record, readiness
captures every prior observation for the same definition/version/population within a configurable
look-back (default four periods), stored as an ordered snapshot of observation IDs. This costs
nothing — the observations already exist — and it is what makes §5.2 honest. A lone baseline point
cannot distinguish "the intervention moved it" from "it was already moving," and the delta renders
identically either way.

**A retracted baseline invalidates the comparison.** Metric observations are archived, not deleted,
when an import batch is rolled back (`UPDATE metric_observations SET archived=1 ... WHERE
import_batch_id=?`). A campaign whose locked baseline or post observation has since been archived
must render the evaluation as `invalidated` with the retracted record named — never continue showing
a delta computed from a number the Data team has withdrawn. Checked at read time, like freshness,
rather than trusted at write time.

If the baseline already meets the primary target, readiness flags the campaign as unnecessary until
the operator chooses a sustain target, supersedes the target with a sourced higher bar, or records a
specific reason the campaign is about maintaining rather than increasing the behavior. The app does
not manufacture “lift” from a cohort that began above the stated goal.

Stale observations render unknown. Suppressed cohorts render suppressed. Missing data is not zero.

### 5.2 Evaluation designs

| Design | What the app may say |
|---|---|
| `descriptive` | Current value and trend during the campaign; no lift statement |
| `pre_post` | Exact baseline, exact post value, arithmetic delta, **and the pre-campaign trajectory**; no causal claim |
| `comparator` | Target-cohort delta beside a Data-team-provided aggregate comparator delta; still labeled association, not causation |

Comparator populations must be stable segments/views, pass the privacy floor, and carry compatible
observations. There is no randomized-experiment builder and no named-person assignment.

**Comparators must be disjoint from the treated cohort.** Population views overlap segments *by
construction* in this schema — that is the whole point of `population_view_segments` — so nothing
stops a comparator view from containing the target segment, making the control include the treated.
Resolve both sides to their base-segment sets and reject any intersection. `stage75._members()`
already does exactly this resolution for growth-line overlap; reuse it rather than writing a second
one.

**Selection effects are named, not hand-waved.** `_stalled_candidates` fires when the latest
observation is at or below the previous one — that is selection on a downward move. A campaign
converted from that episode locks its baseline at the trough, and a noisy metric measured again
after a trough tends to rise **with no intervention at all**. Banning the word "caused" does not fix
this: the rendered delta *is* the artifact, and an operator will read it as effect.

So, for any campaign whose `created_from_signal_episode_id` is set:

- `pre_post` renders the delta beside the locked pre-campaign trajectory, carrying the standing
  caution: *"selected on a declining reading; some rebound is expected without intervention."*
- the UI proposes `comparator` as the default design, because a shared-trend comparator absorbs both
  regression to the mean and seasonality.

**Seasonality is a first-class confound here, not an edge case.** This module explicitly targets
performance reviews and engagement-survey action planning — cycles whose metrics move on the
calendar regardless of intervention. Any evaluation window overlapping a deployment moment of a
recurring kind is labeled as such, and `comparator` is the only design that may be described as
controlling for it.

### 5.3 Checkpoints and adjustment

A campaign checkpoint records:

- scheduled and held dates;
- the exact observations reviewed;
- operator assessment (`on_track`, `at_risk`, `unknown`);
- decision (`continue`, `adjust`, `pause`, `complete`);
- reason and source interaction/reference;
- next evidence date.

Adjusting the intervention appends plan links or supersedes future ones; it does not rewrite the
original hypothesis or baseline. A campaign with stale/missing evidence past its checkpoint creates
one explainable attention item. Existing overdue linked tasks and commitments keep their own Today
items; the campaign must not duplicate them.

### 5.4 Completion outcomes

Completion records one outcome:

- `target_met`;
- `improved_not_met`;
- `no_demonstrated_change`;
- `regressed`;
- `inconclusive`.

The outcome is a judgment backed by exact observation IDs and/or sourced qualitative evidence. The
UI always shows the underlying numerator/value, denominator where available, unit, population,
current-through date, and sample limitations. There is no campaign score.

## 6. People, champions, and client co-ownership

The campaign stores one canonical internal owner, one optional client sponsor, and one optional lead
campaign champion as typed FKs to the existing People module. That is enough coordination for v1;
additional delivery and evidence ownership stays on linked tasks and commitments. Client people must
belong to the campaign account, and the internal owner must have Valence affiliation. A validated
champion remains evidence-gated by the existing advocacy rule. Naming a lead campaign champion does
not upgrade their champion-pipeline stage.

The strongest campaign is client-led. The plan may therefore link a client commitment and champion
kit, and promoted joint milestones can continue to appear in the existing Mutual Action Plan. The
campaign does not create a second client-facing twin.

## 7. Signals, plays, and pacing

### 7.1 What may propose a campaign

- a fresh stalled-cohort episode;
- a new deployment/calendar moment for an eligible population;
- a sponsor/champion request;

Stage 10 product-feedback occurrences and a Target whitespace cell may inform a manually created
draft and barrier diagnosis, but they do not become new signal kinds in v1.

*Corrected from draft v1:* the original justification — that adding a kind "would require rebuilding
the referenced `signal_episodes` table merely to widen a CHECK" — is factually wrong.
`signal_episodes.kind` is a bare `TEXT NOT NULL`; the CHECK is on `source_kind`, a different column.
A new kind inserts with no migration at all, verified behaviourally. The deferral stands on scope
grounds only: each new kind needs its own candidate function, condition key, clear/re-arm rule, and
adversarial tests, and two more of those is not v1 work. Note also that `source_kind` **is** checked,
so a genuinely new *source* would need the table rebuild the original text described — the constraint
is real, just on the other column.

A signal explains the cohort, behavior, current evidence, and why the campaign is being proposed.
The operator may dismiss it, attach it to an existing campaign, or convert it to a **draft**. The
episode receives a typed campaign FK; no signal creates a ready/active campaign.

### 7.2 Episode and dedupe rules

Campaign proposals inherit Stage 7 episode semantics: one open condition, explicit clear/re-arm,
freshness gate, and dismissal cooldown. A campaign linked to an episode prevents another draft for
the same episode. A later recurrence may propose a new campaign only after the condition cleared.

### 7.3 Commercial boundary

Campaign evidence may strengthen a whitespace cell or value target, but campaign completion never
changes penetration, evidence state, opportunity stage, or forecast category automatically. Those
records keep their existing reason-logged transitions. Adoption activity is not revenue evidence by
itself.

## 8. Learning across five accounts

Completed campaigns are queryable by:

- global use case;
- audience-tag shape derived from the target population view;
- primary barrier;
- intervention kinds;
- completion outcome;
- duration and time to a fresh post observation.

Opening a new campaign surfaces nearest completed campaigns using the existing Stage 9 ranking
discipline: exact global use case + non-empty equal audience-tag set, then tag overlap, then use case
only. Account-specific use cases remain excluded from cross-account matching. The result explains
why each match appears.

**The rule this inherits was a live bug and is now fixed (D-94).** `stage9.matches()` previously
ranked `set() == set()` as tier 1 "Exact use case and audience-tag shape," so two unrelated untagged
populations matched at the strongest tier — reproduced with "DACH manufacturing" against "UK retail
frontline." Exact matching now requires a *non-empty* equal tag set (`target_tags and entry_tags ==
target_tags`); tagless cells fall through to an honest use-case-only match. Campaign matching
inherits the corrected ranking, so there is no prerequisite here — but the invariant is worth
restating, because it is the difference between "we have done this exact shape before" and "we have
used this feature before," and only one of those justifies copying a motion.

The completion retrospective adds:

- what barrier was actually present;
- which intervention appeared to help;
- which intervention failed or was skipped;
- which message and layer were used;
- what should be reused or changed;
- whether a different campaign should follow.

V1 does not promote campaigns into plays. The completed-campaign evidence set must first show that a
repeatable trigger and intervention sequence actually exists; a later spec can then extend the play
taxonomy once, deliberately, instead of guessing at it now.

## 9. Portfolio analytics

Across the small portfolio, report exact records and denominators:

- campaigns by lifecycle state;
- outcomes as counts (`target_met`, `improved_not_met`, and so on);
- median days from activation to first fresh post observation, with `n`;
- target realization by intervention kind and barrier, as count over count;
- campaigns started without a baseline or sponsor;
- campaigns with stale/missing evidence past checkpoint;
- repeated campaign shapes and where they differ in outcome.

V1 shows counts and denominators, not percentages—the portfolio is too small for a percentage to add
clarity. Do not rank client people, internal colleagues, accounts, or cohorts. Do not create an
“adoption health score.”

## 10. Information architecture and interaction design

No top-level destination or account-workspace tab is added.

- **Plan** gains an Adoption campaigns panel below the program selector. It answers what campaign is
  running, which behavior it targets, and what happens next.
- **Campaign detail** uses the existing dense instrument language: a compact header, exact outcome
  readout, readiness gaps, ordered intervention table, barrier register, and checkpoint history.
- **Today** shows one campaign-level attention row only for measurement/readiness/decision gaps that
  no linked child record already represents.
- **Evidence** continues to show canonical metrics/value targets. It may link back to campaigns that
  cite them, but does not gain a second scoreboard.
- **Commercial** shows only the campaign link on a cell/opportunity where relevant; it does not host
  campaign execution.
- **Outputs/MAP** continue to use existing promotion and visibility rules.

V1 adds no `generated_documents.kind`. Campaign detail is a live internal operating surface;
client-shareable material continues through existing champion-kit, kickoff, value-review, QBR, and
MAP workflows. This avoids another rebuild of the FK-referenced generated-document table.

Every dated fact uses the freshness language. Status uses the existing label + shape + status-color
pairing. The campaign sequence is a semantic table with keyboard-operable row actions. No funnel,
journey map, or decorative lifecycle visualization is needed.

## 11. Proposed schema and service contract

### 11.1 Tables

1. `adoption_campaigns` — identity, scope, hypothesis, dates, canonical internal owner, optional
   client sponsor/lead champion, evaluation design, lifecycle, exception reasons, completion outcome,
   and archival.
2. `adoption_campaign_state_history` — transition, reason, actor, timestamp; append-only.
3. `adoption_campaign_barriers` — category, description, evidence confidence/date/source, state.
4. `adoption_campaign_targets` — value-target role, locked baseline observation, and the ordered
   baseline-trajectory snapshot (§5.1). A comparator target additionally names its comparator
   population, which a trigger rejects if it shares any base segment with the treated cohort (§5.2).
5. `adoption_campaign_plan_links` — sequence and intervention meaning around exactly one typed FK.
6. `adoption_campaign_checkpoints` — dated evidence review and decision.
7. `adoption_campaign_retrospectives` — one completion learning record plus derived shape snapshot.
8. `adoption_campaign_retrospective_tags` — portfolio-global audience-tag snapshot.

Stage 11.1 adds nullable `signal_episodes.adoption_campaign_id REFERENCES adoption_campaigns(id)` and
an account-scope trigger. Conversion atomically marks the episode attached to the campaign.
`play_runs` already points to its signal episode, so another association table would duplicate the
same relationship; the unchecked legacy `object_type/object_id` pair is not extended for new work.

Do not add a campaign-template table in v1. A completed campaign is the evidence-bearing reusable
source; consulting its structured sequence is enough until repeated use proves a second abstraction
is needed.

### 11.2 Cross-account and integrity rules

Database triggers and API guards enforce:

- program, population, cell, people, value targets, observations, and linked records belong to the
  campaign account;
- cell population/use case agrees with the campaign;
- baseline and post observations match target definition/version/population/unit;
- exactly one segment/view and exactly one linked plan-record FK;
- a trigger/API guard rejects a second active campaign for the same account + program + population +
  use case + primary target unless `concurrent_intervention_reason` is present; the UI then labels
  both evaluations confounded;
- one live retrospective per completed campaign;
- soft-delete-aware unique indexes use `WHERE archived=0`;
- audit events cover every material write and lifecycle transition.

### 11.3 API shape

- list/create/get campaigns under an account;
- patch draft content only;
- dedicated ready/activate/pause/resume/complete/cancel endpoints;
- add/resolve barriers;
- attach/detach typed plan links;
- record checkpoints;
- convert/attach/dismiss a proposal from a signal episode;
- list nearest completed campaigns as evidence for a new draft;
- portfolio campaign analytics.

The service module owns all derivation and transition logic. Routers stay thin. Search, Library
back-references, export/restore, audit history, and account deletion/archival coverage are part of
the first slice, not cleanup work.

## 12. Build order

### Stage 11.0 — Campaign core

- schema through checkpoints and state history;
- service + thin router + Pydantic schemas;
- Plan-panel list/detail/create flow;
- readiness and lifecycle transitions;
- aggregate measurement, freshness, privacy suppression, and cross-account guards;
- search, export/restore, audit, source back-references;
- mock seed with one active and one completed campaign;
- both-theme screenshots.

### Stage 11.1 — Orchestration

- typed links to existing execution/comms/moments/calendar/artifacts/messaging records;
- signal/play conversion to draft with episode dedupe;
- campaign-level Today rules without duplicate child alerts;
- checkpoint adjustment flow and MAP-safe reuse;
- no auto-send regression tests.

### Stage 11.2 — Learning and portfolio view

- retrospective and derived shape snapshots;
- nearest-campaign matching with explainable evidence links;
- portfolio counts/denominators and time-to-evidence;
- final adversarial privacy, causality, and client-visibility review.

## 13. Definition of done and required adversarial tests

On a synthetic account, without leaving the tool, the operator can:

1. create a campaign for an exact program, cohort, use case, and value target;
2. explain the primary capability/opportunity/motivation barrier with dated evidence;
3. lock a fresh aggregate baseline, or activate only after recording why it is missing;
4. assemble an ordered intervention from existing tasks, commitments, communications, moments,
   calendar events, messaging, and artifacts without duplicating their state;
5. see the cue, intervention, owner, barrier, reinforcement step, and measurement checkpoint;
6. convert a fresh stalled-cohort signal into one draft campaign, never an active one;
7. see stale evidence as unknown and a below-floor cohort as suppressed, never zero;
8. compare baseline and post observations with exact units and dates without a causal claim;
9. pause, resume, complete, or cancel only through reason-logged transitions;
10. complete with a defensible outcome and a retrospective that preserves failed interventions;
11. find the nearest-shaped completed campaigns elsewhere with an explicit match reason;
12. consult a nearest-shaped campaign without copying people, dates, evidence, account language,
   sources, or execution records into the new account;
13. export and restore the entire campaign graph and find it through global search;
14. render no named-person product usage field in schema, API, UI, export, search, or generated text;
15. send nothing externally and leak no internal diagnosis through QBR, MAP, or client artifacts.

Required adversarial cases:

- a campaign cell from another account is rejected;
- a target and baseline with mismatched populations are rejected;
- a comparator population sharing any base segment with the treated cohort is rejected, including
  the case where the comparator is a view that *contains* the target segment;
- a signal-triggered `pre_post` campaign renders its pre-campaign trajectory and the
  regression-to-the-mean caution; the delta never appears alone;
- a campaign whose locked baseline observation is later archived by an import rollback renders
  `invalidated` and names the retracted record, rather than continuing to show its delta;
- an evaluation window overlapping a recurring deployment moment is labelled seasonal, and only
  `comparator` may be described as controlling for it;
- a composite view below the privacy floor is suppressed at read and refused for a new observation;
- stale data cannot produce “on track” or “target met”;
- two concurrent campaigns against the same target require an explicit confounding reason;
- linked-task completion changes the campaign plan readout without updating the campaign row;
- an overdue linked task creates one Today item, not a second campaign duplicate;
- a dismissed signal cannot create another draft until its episode clears and re-arms;
- account-specific use cases never cross-match or promote into portfolio plays;
- cross-account campaign matches expose only the structured retrospective and safe shape metadata,
  never source records, people, client wording, or observations from the source account;
- negative/no-change/inconclusive outcomes remain queryable and cannot be hidden from analytics;
- a hostile imported note can propose structured records only and cannot activate or send a campaign.

## 14. Explicit non-goals

- marketing automation, bulk email, in-product messaging, or recipient lists;
- named-user funnels, usage histories, nudges, or “power user” identification;
- survey authoring or individual response storage;
- LMS/course management;
- experiment randomization or causal-inference claims;
- a second task, milestone, communications, champion, metric, MAP, or playbook system;
- campaign ROI attribution beyond existing sourced revenue/value facts;
- campaign templates before completed-campaign reuse proves the need;
- campaign-to-play promotion before repeated completed campaigns prove a stable trigger and action;
- cross-account cloning of campaign plans or execution records;
- new navigation destinations or a generic campaign dashboard;
- AI-authored campaign activation, status transitions, or external messages.
