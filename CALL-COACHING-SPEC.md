# CALL-COACHING-SPEC.md — Personal Call Coach

**Status:** Stage 18 authority; private text-first release built and hardened 2026-08-11
(D-343…D-351).
**Product owner:** Zach. This is intentionally a single-operator product, not a manager enablement
platform.
**Authority:** additive to `ACCOUNT-INTAKE-SPEC.md`, `ACCOUNT-PATH-SPEC.md`,
`RELATIONSHIP-READINESS-SPEC.md`, `ACCOUNT-COPILOT-SPEC.md`, `UX-FOUNDATION-SPEC.md`, and the
standing trust and design rules in `CLAUDE.md` and `DESIGN-GUIDE.md`.
**Research basis:** feedback and deliberate-practice research; ICF coaching competencies; official
conversation-intelligence and roleplay patterns from Gong, Zoom, Microsoft, HubSpot, and Yoodli;
the Valence interview archive; and an adversarial trace of the current interaction, intake,
extraction, proposal, readiness, Account Path, and account-output boundaries.

**Built boundary:** “the first release” in this document means §§18.0–18.4 as tightened after the
Stage 17 Surface Usage review. §18.5 is an evidence-gated follow-on and §18.6 is explicitly outside
this authority. The built release is deterministic and local: it proves the product, privacy, and
write-boundary contracts without sending coaching content to a real model. Real-model, audio,
transcription, calendar, voice, and live-call connections remain closed in `CONNECTIONS.md`.

**Built-flow correction:** analysis creates only the private session and coaching run. Logging an
Interaction and drafting possible account facts are separate post-analysis commands, off until Zach
presses them, and each returns its own receipt. This ordering is intentional: a successful private
review can never be presented as failed because a later account write failed.

---

## 0. Settled product calls

Zach settled the three product choices on 2026-08-10:

1. **First release modes:** post-call review **and** targeted rehearsal.
2. **Visibility:** private by default.
3. **Primary home:** a global Coach workspace, with optional account and program linkage.

One further instruction governs the whole design: **build primarily for Zach.** The first release
therefore has no manager dashboard, team hierarchy, coaching assignments, employee leaderboard,
certification workflow, sharing matrix, or generalized enterprise administration. Those are not
quietly anticipated through premature abstractions. A future multi-user product would require a
new privacy and identity review rather than activating hidden controls.

The recommended defaults in this document are therefore settled unless Zach changes one:

- Text-first review and rehearsal. Audio recording, transcription, and live prompts remain later
  governed connections.
- A coaching session may be standalone, account-linked, program-linked, or linked to an existing
  account Interaction.
- Coaching is private interpretation. It never becomes account truth.
- Account facts extracted from a linked call use the existing `extraction_runs` /
  `extraction_proposals` store and the existing `ProposalReview` decision surface.
- A rehearsal is practice, never a customer interaction, meaningful touch, commitment, decision,
  or readiness event.
- The coach shows no overall score, numeric confidence, sentiment, emotion, personality,
  authenticity, or deception judgment.
- Every material observation about a completed call is grounded in an exact source span.
- The common path ends in one selected behavior and an immediate practice attempt, not a report.

---

## 1. Product outcome

The Call Coach turns a completed call or a difficult call moment into a private, repeatable
improvement loop.

After a completed call, Zach can paste the transcript or choose a supported text file, identify himself, state what the
call needed to accomplish, and receive a small number of evidence-backed observations. The coach
names what to repeat, what to change, why it matters, and which one behavior deserves attention
first. Zach can then rehearse that exact moment and evaluate the new attempt only on the selected
skill.

When the call belongs to an account, the coach also considers the accepted account context and the
six independent relationship-readiness pillars. It may explain that the call surfaced or failed to
surface relevant evidence; it may not calculate or write readiness. In a separate, explicit action,
the same retained transcript may draft account updates through the existing proposal workflow.

When the call does not belong to an account, it remains a first-class standalone coaching session.
No placeholder account, synthetic person, fake Interaction, or generic "Miscellaneous" account is
created to make the schema happy.

### 1.1 The ten-second outcome

Within ten seconds of opening a completed analysis, Zach can answer:

1. What is the single most useful thing to improve next?
2. Which exact moment supports that conclusion?
3. Why did it matter in this kind of call?
4. What did I do well enough to repeat intentionally?
5. What would a better version sound like?
6. Can I practice it now?
7. If this was account-linked, what possible account facts are waiting for separate review?

### 1.2 The behavior-change loop

Every completed review implements the same loop:

1. **Aim** — define the call type, intended outcome, and coaching focus.
2. **Reflect** — Zach records what he thought worked, what was difficult, and whether he got the
   intended outcome. Reflection is encouraged and skippable; it never blocks urgent review.
3. **Observe** — the coach returns exact, checkable moments rather than general impressions.
4. **Prioritize** — one behavior is visually dominant; the rest recedes.
5. **Model** — the coach supplies a stronger question, line, recap, or structure.
6. **Practice** — Zach immediately retries the moment in one focused text attempt.
7. **Carry forward** — Zach may keep one active coaching goal and revisit it on a comparable call.

The product is incomplete if it stops after step 4.

---

## 2. Non-goals

The first release does not:

- Act as a therapist, mental-health service, crisis service, or clinical coach.
- Describe itself as a "life coach" in UI copy. It may feel continuous and personal while staying
  professionally scoped as **Coach** or **Call Coach**.
- Monitor Nadia users, ingest private Nadia conversations, or infer named-person product usage.
- Evaluate Zach for employment, compensation, promotion, certification, or discipline.
- Evaluate client participants, rank them, or infer their personality, intelligence, honesty,
  emotion, mental state, or intent.
- Produce an overall call score, letter grade, health score, leaderboard, or weighted rubric total.
- Treat talk ratio, filler words, question count, speaking pace, or call length as universal quality
  measures.
- Run live during a customer call.
- Record or transcribe audio.
- Browse the web, invoke tools, or follow instructions found inside the transcript.
- Send a message, schedule a meeting, update a CRM, or create account records automatically.
- Turn a rehearsal into an Interaction or use it to update relationship freshness.
- Make coaching sessions client-visible, include them in the Mutual Action Plan, QBR, team update,
  account export, or leadership review.
- Create a second proposal store or a second place where proposals can be accepted or rejected.
- Make a causal claim that a coached behavior produced a renewal, expansion, or other business
  result.
- Build configurable rubric administration in the first release.

---

## 3. Existing boundaries and the honest delta

### 3.1 Interaction remains account-required

`interactions.account_id` is deliberately non-null (D-09), and
`routers/interactions.py:create_interaction` validates the account and participant scope. It feeds
the account history, last-touch calculations, activity projections, Account Path, and exports.

**This spec does not make `Interaction.account_id` nullable.** A standalone coached call is not an
account Interaction. Weakening that invariant would force every account consumer to understand a
new non-account state and would risk standalone participants appearing in account-safe outputs.

### 3.2 The proposal store is reused, not widened into coaching

`extraction_runs.account_id` is already nullable at the database layer, but current extraction
requests require an account and every proposal target is an account-domain record. Coaching
observations are not proposals: "ask a cleaner decision question" is neither a Task nor a fact the
account agreed to.

Therefore:

- Coaching results live in the coaching domain defined here.
- Account updates from a linked completed call live in the existing extraction run and proposal
  tables.
- `ProposalReview` remains the only resolution surface.
- The two may be composed on the coaching results screen as separate read models; neither is copied
  into the other.

### 3.3 Intake utilities are reused below the account route

The account drop zone currently owns an account-scoped receipt and route. Its reusable lower-level
capabilities are byte screening, size enforcement, kind detection, text/VTT/SRT parsing, content
hashing, safe source handling, extraction, and exact-span grounding.

The Coach reuses or extracts those utilities. It does not call an account route with a fake account,
and it does not make `intake_drops.account_id` nullable. A direct coaching source gets its own
private source record because a standalone source has no account drop receipt to belong to.

### 3.4 Copilot and readiness remain separate authorities

Account context is assembled deterministically before the model runs. The coach never asks a model
to discover which account records it may read. The six readiness pillars arrive from the existing
deterministic evaluator, with state, freshness, coverage, and applicability still independent.

The model may use that response to coach the conversation. It may not recalculate it, translate it
into a score, or write a pillar state.

---

## 4. Vocabulary

### 4.1 Coaching session

The durable private container for one review or one rehearsal attempt. It carries the coaching aim,
scope, self-reflection, and links to its source and analysis runs.

### 4.2 Review

A post-call analysis of a completed transcript or sufficiently detailed call notes. A prepared
script is not presented as a completed call and cannot support claims about actual listening,
follow-up, reactions, decisions, or outcomes.

### 4.3 Rehearsal

A targeted practice attempt linked to one coaching goal or observation. It assesses only the chosen
skill. It is not evidence that a real conversation occurred.

### 4.4 Coaching source

The retained normalized text used by a coaching run: paste, `.txt`, `.md`, `.vtt`, or `.srt` in the
first release. Original bytes are never persisted. The source may later be deleted without deleting
the session's private observations; citations then clearly state that their source is no longer
available for verification.

### 4.5 Coaching run

One versioned model execution over one immutable source hash, one rubric version, and—when linked—
one account-context snapshot. A rerun creates another run; it never overwrites the earlier analysis.

### 4.6 Coaching observation

A private, cited strength or opportunity concerning Zach's observable behavior in the call. It
contains the situation, behavior, likely impact, and a repeatable or improved alternative. It is not
an account fact.

### 4.7 Coaching goal

The one behavior Zach chooses to carry forward. The product may recommend it; only Zach activates
it. At most one goal is active in the first release so the home screen does not become a second task
manager.

### 4.8 Account implication

A private interpretation of how a completed call relates to the existing account context, such as
"the conversation did not establish a decision metric." It is cited to the call and stamped with
the account-context snapshot. It does not satisfy, change, or conflict a canonical record by itself.

### 4.9 Proposed account update

An existing `extraction_proposal` produced, on explicit request, from an account-linked completed
call. It follows the existing citation, validation, conflict, acceptance, rejection, supersession,
and audit rules without alteration.

---

## 5. Information architecture

### 5.1 Global destination

Add **Coach** to the primary rail between Today and Accounts:

1. Today
2. Coach
3. Accounts
4. Library
5. Operations

This is the one intentional exception to the standing preference against new top-level
destinations. Zach explicitly chose a global workspace because standalone calls are first-class.
Hiding history behind a modal would make the personal learning loop hard to revisit.

Routes:

- `/coach` — private Coach home.
- `/coach/new` — start a completed-call review.
- `/coach/new?mode=rehearsal` — start a standalone single-attempt rehearsal.
- `/coach/sessions/{session_id}` — session and latest run.
- `/coach/sessions/{session_id}?practice={observation_id}` — open the exact observation's targeted
  practice composer.
- `/coach/new?account={account_id}&program={program_id}` — account-prefilled entry.
- `/coach/new?interaction={interaction_id}` — review an existing account interaction when a
  retained transcript is supplied or linked.
- `/accounts/{account_id}/ledger?section=proposals&run={extraction_run_id}` — open Proposal Review
  for the exact account-fact draft run.

The route codec bounds every opaque identifier and drops unsupported modes, sections, and query
keys. Account, program, Interaction, session, observation, and run ownership is validated again at
the API command that reads or writes the record.

### 5.2 Entry points

The same new-session flow is reachable from:

- The Coach home primary action: **Review a call**.
- The command palette: **Coach a call**.
- An account's Operate lens: **Coach a call for this account**.
- A completed account Interaction: **Coach this call**.
- A completed coaching review: **Practice this**.

Every entry point pre-fills context but lands in one flow. No account tab grows a separate coaching
implementation.

### 5.3 Coach home

The home screen is deliberately personal and small:

1. **Active focus** — the one coaching goal, the originating moment, and Practice again.
2. **Start** — Review a call and Practice a line.
3. **Recent sessions** — newest first, labeled Standalone or with account/program context.
4. **Continue** — failed analyses with retry and unfinished work through recent sessions.

There are no metric tiles, streaks, grades, percentile comparisons, or gamified pressure. A compact
history filter may select All / Standalone / Account-linked / Rehearsals. Search matches session
title and Zach-authored focus, never raw transcript text.

---

## 6. New review flow

The flow is one page with progressive disclosure, not a multi-step wizard that prevents quick use.

### 6.1 Choose mode

Two choices:

- **Review a completed call** — default.
- **Practice a difficult moment** — starts the rehearsal flow in §11.

### 6.2 Choose scope

The built form has two visible scope choices:

- **Standalone** — default from the global Coach home.
- **Account** — choose account; program remains optional.

An existing Interaction can arrive pre-linked through its routed entry. The current local release
does not add a second recent-Interaction picker inside Coach.

If launched from an account, account and current program are prefilled but visible and changeable.
Switching that intake to standalone practice clears account, program, and Interaction scope rather
than hiding retained values. The transcript never chooses its own account, even when it names one.

### 6.3 Add source

Accepted in the first release:

- Paste transcript or detailed notes.
- `.txt` or `.md`.
- `.vtt` or `.srt` with cue timestamps.

The idle control states the size cap and accepted formats before failure. It supports paste and a
keyboard-operable file picker. Audio and video are refused by name:

> Audio and video are not transcribed here yet. Add a transcript to continue.

The first-release cap is the existing 1 MB text limit. The server, not the browser, owns the limit
and refusal copy.

### 6.4 Identify the coached speaker

The parser lists structurally detected speaker labels. Zach selects himself. The selection is a
human assertion and is stored on the session; the model may not decide which person is Zach.

If speaker labels are absent or unreliable:

- Zach may continue with **speaker unknown**.
- Speaker-unknown review may coach call structure and content but may not claim talk balance,
  interruption, question ownership, or who made a statement.

### 6.5 Frame the call

Required:

- Call type.
- Intended outcome, in Zach's words.

Optional:

- Whether the intended outcome was achieved.
- Call date if it is not linked to an Interaction.
- A private session title; otherwise derive a non-sensitive title from type and date, not transcript
  content.

The first release offers the call types in §9. The selected type determines the rubric. `Other`
uses the universal rubric and asks for a one-line description.

### 6.6 Account actions

Analysis has no account-write checkbox and performs no account write. After a successful
account-linked completed-call review, two explicit independent commands appear:

- **Log Interaction** — absent when the review already has one and never offered for rehearsal.
- **Draft account updates** — sends the retained source to the existing proposal store and never
  accepts a proposal.

Neither command is default-on. Each shows its own success receipt and can fail or retry without
changing the successful coaching result. Interaction logging calls the shared native
`interaction_ops.create` path and is idempotent once linked. Drafting is idempotent per coaching run:
a retry returns the existing extraction-run receipt instead of producing duplicate proposals.

### 6.7 Self-reflection

Before results appear, invite four short answers:

- What worked?
- Where did it get difficult?
- Did you get the outcome you wanted?
- What would you change?

**Skip for now** is always visible. Reflection is stored privately and sent as operator context,
clearly separated from the call source. The model may compare Zach's reflection with observable
moments but may not call disagreement a lack of self-awareness.

### 6.8 Submit and processing

Submitting performs, in order:

1. Validate scope and source.
2. Normalize text and compute content hash.
3. Persist the private session and source.
4. Snapshot account context when applicable.
5. Enqueue `coaching_analyze` in the existing in-process jobs table.

Interaction logging and proposal drafting happen only later through §6.6. Their state is not folded
into the analysis request, so a partial account-action failure cannot make the private review look
unsaved or invite a duplicate session on resubmit.

---

## 7. Results experience

### 7.1 Information hierarchy

Order is fixed:

1. **Call frame** — type, intended outcome, scope, date, coached speaker, privacy, and coverage.
2. **Start here** — one dominant coaching priority.
3. **Practice this** — the shortest path into a targeted rehearsal.
4. **Keep doing** — up to two cited strengths.
5. **Try next time** — up to two cited opportunities, including the top priority.
6. **Account lens** — account-linked reviews only, visually separate and private.
7. **Possible account updates** — explicit commands, receipts, and an exact Proposal Review link.
8. **Source and privacy** — retained/deleted state, local backend, deletion, and archive controls.

Only **Start here** receives high visual emphasis. The page must not become a bento grid of equally
important cards.

### 7.2 Start here

The top-priority card contains:

- Skill label.
- One-sentence finding.
- Exact cited moment.
- Why it mattered for this call's goal and type.
- A stronger alternative.
- **Practice this** primary action.
- **Make this my focus** secondary action.
- Useful / Inaccurate response controls.

If no supported opportunity survives validation, the card says so. It may recommend repeating a
supported strength or asking Zach for more complete source material; it does not invent a criticism
to fill the design.

### 7.3 Observation shape

Every strength and opportunity renders the same checkable anatomy:

- **Situation:** where in the call this occurred.
- **Behavior:** what Zach observably said or did.
- **Impact:** what happened next, when observable; otherwise a clearly labeled likely impact.
- **Alternative:** what to repeat or try instead.
- **Evidence:** exact quote and optional timestamp.

The product never writes "you were defensive," "they trusted you," or "the client was frustrated"
as observed fact. It may write "you answered before asking what made the deadline important" or
"the client repeated the deadline concern after the answer," because those are checkable.

### 7.4 Source-moment interaction

Opening an observation displays one modal with the exact retained source passage highlighted and
the behavior, impact, and alternative beside it. If the source snapshot was deleted, the exact
quoted span remains and the modal states that surrounding context is unavailable. The dialog has a
labeled close control, closes from the backdrop, and never relies on highlight color alone.

### 7.5 Account lens

The account lens is not a scorecard. It answers four questions:

1. Which current account objective or gap was this call relevant to?
2. What did the conversation explicitly establish?
3. What remains unestablished or ambiguous?
4. What question or move would improve the next account conversation?

Each statement carries a call citation, an account-context reference, or both. The section displays
the deterministic readiness response's current wording and snapshot time separately from the
coach's interpretation.

Permitted:

> The call named Colleen as the rollout sponsor, but did not connect her sponsorship to an agreed
> value metric. Executive sponsorship currently remains thin in the readiness view.

Forbidden:

> This call raised executive sponsorship to 72%.

The account lens never offers a control that changes readiness.

### 7.6 Possible account updates

Before either bridge is used, this section offers only **Log Interaction** and **Draft account
updates** where applicable. After a command succeeds it shows that command's receipt. Once drafting
has produced an extraction run, **Open Proposal Review** links to the one `ProposalReview` surface,
scoped to that exact run.

It has no accept, reject, edit, resolve, or accept-all controls. The coaching page is not a second
proposal decision surface.

---

## 8. Structured coaching contract

Every backend returns strict JSON. The wire contract is versioned independently from the prompt and
model.

```json
{
  "contract_version": "coach-1",
  "call_frame": {
    "call_type": "deployment_working",
    "intended_outcome": "Agree the launch approach and immediate owners",
    "outcome_reading": "partial"
  },
  "summary": "The team resolved the launch-shape disagreement but left success measures implicit.",
  "top_priority_key": "obs-2",
  "observations": [
    {
      "key": "obs-2",
      "kind": "opportunity",
      "skill_key": "decision_clarity",
      "headline": "Name the decision criteria before solving the rollout",
      "situation": "When the April 15 date first appeared",
      "behavior": "The discussion moved into launch options before clarifying what the date governed.",
      "impact": {
        "type": "observed",
        "text": "The date had to be revisited later before the team could distinguish a preference from a constraint."
      },
      "alternative": "Before we design around April 15, what decision or dependency does that date actually control?",
      "evidence": [{
        "speaker": "Zach",
        "quote": "Before we get into the launch plan...",
        "start_char": 812,
        "end_char": 850,
        "timestamp": "08:36"
      }]
    }
  ],
  "account_lens": {
    "status": "supported",
    "observations": []
  },
  "practice": {
    "skill_key": "decision_clarity",
    "prompt": "Reopen the deadline discussion and clarify the governing decision in two questions."
  },
  "coverage": {
    "source": "complete",
    "speaker_attribution": "confirmed_by_operator",
    "timestamps": "available",
    "account_context": "partial",
    "omitted": ["budget authority source unavailable"]
  }
}
```

### 8.1 Hard validators

Post-model validation enforces:

- Exactly one contract version from an allowlist.
- Up to two strengths and up to two opportunities.
- `top_priority_key` resolves to a supported opportunity, or is null.
- Every completed-call observation has at least one exact source span.
- Every source quote is byte-identical to the normalized retained source at the claimed offsets.
- Speaker identity matches the operator-confirmed mapping or is `unknown`.
- `impact.type` is `observed` or `inferred`; inferred impact copy is presented as possibility.
- Skill keys exist in the selected rubric version.
- Account-pillar keys exist in the supplied deterministic account snapshot.
- No output field names or values encode score, grade, percentile, confidence number, sentiment,
  emotion, personality, authenticity, or deception.
- No observation targets a non-coached participant for evaluation.
- Alternative phrasing is never rendered as something actually said.

An invalid observation is dropped and reported in coverage. If the top priority is dropped, the
validator selects the first surviving supported opportunity in rubric priority order. It does not
ask the model to repair evidence silently.

### 8.2 Exact grounding

There is no fuzzy quote matching. The model returns quote and offsets; the server locates the exact
quote in the normalized snapshot and stamps canonical offsets. When a quote appears multiple times,
the supplied offsets or timestamp must disambiguate it. Otherwise the observation is unlocatable and
does not render as grounded.

The source may be normalized once for line endings and cue metadata before hashing. That normalized
snapshot is the citation authority for the entire run and never changes in place.

### 8.3 Source bounds

The local release accepts one retained UTF-8 source up to 1 MB and reads that snapshot as a whole.
It implements no hidden chunking, overlap, or partial-range synthesis. Sources over the cap are
refused before persistence. `coverage.whole_source_read` is true for a completed local analysis;
`partial` is reserved for restricted attribution or insufficient material, not an unimplemented
chunk pipeline. Any future real-model chunking requires its own deterministic range and omission
contract before it can claim whole-call coverage.

---

## 9. Rubric system

### 9.1 Why one universal scorecard is rejected

A discovery call, executive update, risk-recovery conversation, and internal alignment call have
different jobs. A high seller talk ratio may be a warning in discovery and entirely appropriate in
a short presentation. A large question count can indicate curiosity or an interrogation. The rubric
therefore follows the declared call type and intended outcome.

### 9.2 Versioned code-owned definitions

Initial rubrics live as reviewed YAML or Python definitions under the backend, not editable database
rows. Each definition has:

- Stable key and integer version.
- Label and purpose.
- Applicable call types.
- Ordered skill keys.
- Observable positive and negative anchors.
- Evidence requirements.
- Non-applicable conditions.
- Account-lens mappings where relevant.
- Governance note and sources.

A configuration entry may select an allowlisted rubric and can never create executable prompt
behavior. Changing criteria creates a new version. Historical sessions retain their stamped version;
trends never compare different versions without an explicit caveat.

### 9.3 Universal skills

Every call type draws from a small common library, but applies only relevant skills:

- `framing_and_outcome` — establishes why the conversation is happening and what needs to result.
- `curiosity_and_questions` — uses purposeful questions rather than a checklist interrogation.
- `listening_and_followup` — follows the other person's answer rather than pivoting immediately.
- `synthesis` — compresses complexity and tests shared understanding.
- `constructive_challenge` — surfaces disagreement or risk directly and respectfully.
- `decision_clarity` — distinguishes facts, preferences, constraints, decisions, and open questions.
- `stakeholder_strategy` — identifies roles, influence, ownership, and missing voices without
  inferring authority from titles alone.
- `value_and_measurement` — links activity to an explicit outcome, baseline, target, population, and
  decision bar where the call requires it.
- `commercial_clarity` — surfaces authority, funding, procurement, timing, and decision mechanics
  when commercially applicable.
- `ownership_and_next_steps` — ends with named owners, dates, dependencies, and follow-up.
- `clarity_and_concision` — makes the point understandable without grading style or personality.
- `trust_and_safety` — acknowledges concerns, protects appropriate boundaries, and avoids promises
  the source cannot support.

### 9.4 Initial call types

#### Account kickoff / onboarding

Primary questions:

- Was the desired deployment outcome explicit?
- Were scope, exclusions, roles, and decision rights clarified?
- Was the scorecard or measurement-discovery action named?
- Were governance rhythm, immediate dependencies, and next checkpoint confirmed?

#### Deployment working session

Primary questions:

- Did the conversation distinguish organic, programmatic, technical, and commercial work?
- Were tensions converted into choices or parallel workstreams rather than blurred?
- Did each workstream leave with owner, date, and definition of done?
- Were risks and unresolved dependencies surfaced without turning every concern into a blocker?

#### Stakeholder discovery

Primary questions:

- Did Zach understand the person's goals, constraints, and metric?
- Did follow-up questions respond to what the person actually said?
- Did the call establish role or influence through evidence rather than title inference?
- Did it identify a meaningful next relationship move?

#### Executive sponsor review / QBR

Primary questions:

- Did the call begin with the executive-relevant outcome and decision?
- Were facts, interpretations, hypotheses, and recommendations distinguishable?
- Was value supported by comparable evidence rather than satisfaction alone?
- Was the executive ask clear and tied to their owned outcome?

#### Renewal / expansion

Primary questions:

- Was the value bar the client accepted made explicit?
- Were budget authority, funding source, procurement, and decision timing established?
- Did the plan demonstrate client acknowledgement or co-ownership?
- Did the close produce a mutual next step rather than an internal hope?

#### Risk recovery

Primary questions:

- Was the concern acknowledged before solutioning?
- Did the conversation establish cause, consequence, and recovery ownership?
- Were promises bounded to what Zach could actually commit?
- Was an escalation or confirmation point explicit?

#### Internal alignment

Primary questions:

- Was disagreement made discussable?
- Were decision rights clear?
- Did the group commit after the decision?
- Was the external message and owner explicit?

#### Interview / networking / other standalone

Uses the universal skills plus a user-authored outcome. It does not load account pillars or assume a
sales methodology.

### 9.5 Relationship-readiness lens

Account-linked completed calls may receive a read-only lens over the six existing pillars:

- Stakeholder breadth.
- Champion continuity.
- Executive sponsorship.
- Quantified value.
- Budget owner identified.
- Active expansion plan.

For each applicable pillar, the coach may report:

- `advanced_evidence` — the call explicitly said something that may support an account proposal.
- `clarified` — the call resolved ambiguity in the coaching context.
- `missed_opportunity` — a relevant question or confirmation was not established, with evidence for
  the conversational moment rather than a claim that the absent fact is false.
- `not_relevant` — the call type and stated outcome did not call for this pillar.
- `unable_to_assess` — source or context coverage was insufficient.

These are coaching labels, not readiness states. They are never aggregated.

---

## 10. Account linkage and truth boundaries

### 10.1 Scope is a human choice

The account and program come from Zach's selection or the launch context. The transcript cannot
rescope itself. Mentions of other accounts are reported and remain in the selected scope, matching
the account intake rule.

### 10.2 Account-context snapshot

The account-aware coaching run stores the exact internal context object it received and a
`data_current_through` stamp. The allowlist may contain:

- Account and selected program identity, problem statement, phase, launch definition, and success
  criteria.
- Deterministic readiness response with all four independent axes.
- Account Path next move and current gate.
- Accepted stakeholder roles, professional cares-about/value fields, and dated evidence.
- Open commitments, tasks, risks, issues, milestones, and customer waits.
- Accepted value targets, comparable observations, and value stories with their evidence class.
- Current opportunity, budget, funding, procurement, and renewal facts.
- Recent accepted interactions and confirmed company-intelligence events when relevant.

It excludes:

- Draft proposals.
- Untriaged capture notes.
- Named-person Nadia usage or private Nadia content.
- Client-visible artifacts as an authority over their canonical source records.
- Product telemetry.
- Other accounts.
- Archived, retracted, suppressed, or inaccessible records.

Every omitted or failed adapter is named in context coverage. A partial account context may still
support call coaching but cannot support a complete account-gap claim.

### 10.3 Logging a new Interaction

The current router logic is refactored into a shared `interaction_ops.create` function used by both
QuickEntry and Coach. It retains every existing validation and audit behavior. The route becomes a
thin schema/HTTP wrapper.

Rules:

- A review linked to an existing Interaction never creates a second one.
- A new account-linked completed call creates an Interaction only when Zach presses the
  post-analysis command.
- A standalone review never creates one.
- A rehearsal never creates one, even when it uses account context.
- Repeating the command returns the already-linked native Interaction rather than creating another.
- Failure to create the Interaction cannot fabricate a touch or change the completed coaching run;
  the action remains available for retry.

### 10.4 Drafting account updates

When explicitly requested after analysis, the same normalized source text goes through the existing extractor and
`_persist_run` with:

- Selected account/program.
- Created or existing interaction ID when available.
- `source_kind='other'`, the existing extraction vocabulary's honest value for this governed bridge.
- A local provider identifier for the coaching source and stable external ID equal to the coaching
  session ID.
- The content hash shared with the coaching run.

`proposal_grounding` adds a governed resolver for that local provider so Proposal Review can load
the exact coaching source snapshot without copying it into `intake_drops` or `interactions.raw_notes`.
Deleted source, never-retained source, and unlocatable span degrade distinctly, as they do for account
intake.

The selected coaching run must belong to the session. If it already carries an extraction-run link,
the command returns that link and its proposal count with `already_drafted: true`; it does not call
the extractor again. The result action routes to the account Ledger's Proposal Review section with
that exact extraction-run ID and opens the section automatically.

### 10.5 Linking a standalone review later

**Link to account** is explicit and previewed. It:

1. Validates account and optional program.
2. Shows which private session metadata will gain the link.
3. Records actor, time, prior scope, and new scope in audit.
4. Creates a new account-context coaching run; it does not rewrite the standalone run.
5. Separately offers Log Interaction and Draft account updates.

No historical observation becomes an account fact. A new account-aware run may disagree with the
standalone run because it saw more context; both remain visible with their run stamps.

### 10.6 Removing an account link

Unlinking removes future account context and navigation association; it does not erase an existing
Interaction or resolved proposal. The preview names those surviving account records before Zach
confirms. The original context snapshot remains on the historical run because deleting what the
model saw would make the analysis unauditable.

---

## 11. Targeted rehearsal

### 11.1 First-release experience

Rehearsal is text-first and single-attempt in the built local release. Zach types the line or short
response he plans to say. Multi-turn roleplay, voice capture, and live speech analysis are separate
later capabilities.

Entry paths:

- Practice this from the top priority or any observation.
- Practice again from the active goal; the exact originating observation opens prefilled.
- Start a standalone practice from Coach home.

One attempt is evaluated against one skill. The result offers Return to review or New practice and
does not expand into a general chat assistant.

### 11.2 Practice frame

Before evaluation, show:

- Skill being practiced.
- Objective.
- The attempt text.
- For targeted practice, the originating observation and alternative through the parent review.

No simulated counterpart is present in the local release, so the coach makes no persona or reaction
prediction.

### 11.3 Practice feedback

After the attempt, return only:

- Did the target behavior appear? `observed | partial | not_observed | unable_to_assess`.
- Exact attempt quote.
- One adjustment.
- Return to the originating review or begin a new practice.

There is no overall score and no unrelated feedback. A decision-clarity drill does not grade filler
words, rapport, or commercial discovery.

### 11.4 Account boundary

Targeted practice may retain its parent account/program linkage for private lineage, but the local
evaluator reads only the attempt and selected skill. Rehearsal output:

- Creates no Interaction.
- Updates no last-touch date.
- Produces no extraction proposals.
- Satisfies no readiness evidence.
- Enters no account history, leadership review, QBR, MAP, or team update.

The UI carries a persistent **Practice — not an account event** label.

---

## 12. Data model

One migration adds five tables. None replaces or widens an existing domain table.

### 12.1 `coaching_sessions`

```sql
coaching_sessions (
  id TEXT PRIMARY KEY,
  mode TEXT NOT NULL CHECK (mode IN ('review','rehearsal')),
  parent_session_id TEXT REFERENCES coaching_sessions(id),
  origin_observation_id TEXT REFERENCES coaching_observations(id),
  account_id TEXT REFERENCES accounts(id),
  program_id TEXT REFERENCES programs(id),
  interaction_id TEXT REFERENCES interactions(id),
  title TEXT NOT NULL,
  call_type TEXT NOT NULL,
  call_date TEXT,
  intended_outcome TEXT NOT NULL,
  coaching_focus TEXT,
  coached_speaker_key TEXT,
  speaker_status TEXT NOT NULL CHECK (speaker_status IN
    ('confirmed_by_operator','unknown','not_applicable')),
  reflection_worked TEXT,
  reflection_difficult TEXT,
  reflection_outcome TEXT,
  reflection_change TEXT,
  created_by TEXT NOT NULL,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  archived INTEGER NOT NULL DEFAULT 0,
  archived_at TEXT,
  archived_by TEXT
)
```

API validation enforces account/program/interaction ownership. SQL cannot express those cross-table
checks safely. A rehearsal launched from an observation records both `parent_session_id` and
`origin_observation_id`, which preserves the exact comparison point. A standalone practice started
from Coach home may leave both fields null; its required intended outcome and coaching focus define
the drill. Review sessions must leave both rehearsal-lineage fields null. These mode-specific rules
are enforced in the service and covered by constraint tests because a blanket parent requirement
would incorrectly block standalone practice.

### 12.2 `coaching_sources`

```sql
coaching_sources (
  id TEXT PRIMARY KEY,
  session_id TEXT NOT NULL UNIQUE REFERENCES coaching_sessions(id),
  source_kind TEXT NOT NULL CHECK (source_kind IN
    ('paste','notes','script','txt','md','vtt','srt','practice_transcript')),
  filename TEXT,
  byte_length INTEGER NOT NULL,
  content_hash TEXT NOT NULL,
  snapshot_text TEXT,
  snapshot_deleted_at TEXT,
  snapshot_deleted_by TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
)
```

Bytes are never persisted. Filename is private document content and never enters telemetry,
notifications, or client-facing output.

### 12.3 `coaching_runs`

```sql
coaching_runs (
  id TEXT PRIMARY KEY,
  session_id TEXT NOT NULL REFERENCES coaching_sessions(id),
  job_id TEXT REFERENCES jobs(id),
  source_content_hash TEXT NOT NULL,
  contract_version TEXT NOT NULL,
  rubric_key TEXT NOT NULL,
  rubric_version INTEGER NOT NULL,
  extractor_backend TEXT,
  model_version TEXT NOT NULL,
  prompt_version TEXT NOT NULL,
  extraction_run_id TEXT REFERENCES extraction_runs(id),
  status TEXT NOT NULL CHECK (status IN
    ('queued','running','completed','partial','failed')),
  summary TEXT,
  account_context_snapshot_json TEXT,
  account_lens_json TEXT,
  practice_json TEXT,
  coverage_json TEXT,
  error_json TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  finished_at TEXT
)
```

Run status describes processing, never Zach's skill or the call's quality. Counts are derived from
observation rows.

### 12.4 `coaching_observations`

```sql
coaching_observations (
  id TEXT PRIMARY KEY,
  run_id TEXT NOT NULL REFERENCES coaching_runs(id),
  kind TEXT NOT NULL CHECK (kind IN ('strength','opportunity')),
  skill_key TEXT NOT NULL,
  headline TEXT NOT NULL,
  situation TEXT NOT NULL,
  behavior TEXT NOT NULL,
  impact_type TEXT NOT NULL CHECK (impact_type IN ('observed','inferred')),
  impact_text TEXT NOT NULL,
  alternative TEXT NOT NULL,
  source_span TEXT NOT NULL,
  source_start INTEGER NOT NULL,
  source_end INTEGER NOT NULL,
  source_timestamp TEXT,
  source_speaker_key TEXT,
  is_top_priority INTEGER NOT NULL DEFAULT 0,
  ordinal INTEGER NOT NULL,
  operator_response TEXT CHECK (operator_response IN
    ('useful','inaccurate','dismissed')),
  operator_note TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  CHECK (source_start >= 0 AND source_end > source_start)
)
```

A partial unique index permits at most one `is_top_priority=1` observation per run.

### 12.5 `coaching_goals`

```sql
coaching_goals (
  id TEXT PRIMARY KEY,
  source_observation_id TEXT NOT NULL REFERENCES coaching_observations(id),
  skill_key TEXT NOT NULL,
  behavior TEXT NOT NULL,
  status TEXT NOT NULL CHECK (status IN
    ('active','completed','replaced','abandoned')),
  revisit_after TEXT,
  completed_at TEXT,
  created_by TEXT NOT NULL,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
)
```

A partial unique index permits one active goal. Activating another goal explicitly marks the prior
one `replaced`; it never silently closes it.

### 12.6 No stored trend or score tables

Trends are derived over observations and rehearsal sessions sharing the same skill, call type, and
rubric version. No weekly score, rolling average, streak, percentile, or skill-state table exists.

---

## 13. API contract

### 13.1 Configuration and history

- `GET /api/coaching/config`
  - Accepted source kinds and server-enforced limits.
  - Available call types and rubric versions.
  - Active backend/model mode.
  - Connection gates for model, transcription, and live coaching.
- `GET /api/coaching/sessions?account_id=&mode=&limit=`
  - Private session summaries only; never source text.
- `GET /api/coaching/sessions/{session_id}`
  - Session, immutable run history, latest run, observations, goal, processing coverage, and the
    existing extraction-run link when account drafts were requested.

### 13.2 Create and analyze

- `POST /api/coaching/sessions`
  - JSON text or base64 bytes, matching the account intake transport convention.
  - Mode, scope, speaker selection, frame, and reflection.
  - Returns the created private session and queued coaching run. Interaction logging and account
    draft extraction remain separate, explicit API calls; a create cannot smuggle those writes.
- `POST /api/coaching/sessions/{session_id}/runs`
  - Reruns against the same source with current or explicitly selected rubric.
  - Creates a new immutable run.
- `POST /api/coaching/sessions/{session_id}/retry`
  - Retries a failed job without creating a duplicate source or Interaction.

### 13.3 Feedback and goals

- `PATCH /api/coaching/observations/{observation_id}/response`
  - `useful | inaccurate | dismissed`, optional private note.
- `POST /api/coaching/goals`
  - Activates an observation as the one current focus and marks a prior active goal replaced.
- `POST /api/coaching/goals/{goal_id}/complete`
  - Completes only the active focus; makes no claim that the skill is mastered.
- `POST /api/coaching/sessions/{session_id}/rehearsals`
  - Creates a child single-attempt rehearsal session from an observation/goal.

### 13.4 Account linkage

- `POST /api/coaching/sessions/{session_id}/link-preview`
- `POST /api/coaching/sessions/{session_id}/link`
- `POST /api/coaching/sessions/{session_id}/unlink-preview`
- `POST /api/coaching/sessions/{session_id}/unlink`
- `POST /api/coaching/sessions/{session_id}/log-interaction`
- `POST /api/coaching/sessions/{session_id}/draft-account-updates`
  - Run-scoped and idempotent; returns the existing receipt on retry.

Preview and mutation stay separate where the action has surviving account consequences.

### 13.5 Privacy controls

- `DELETE /api/coaching/sources/{source_id}/snapshot`
  - Nulls retained text; preserves hash, run, observations, and explicit degraded citation state.
- `DELETE /api/coaching/sessions/{session_id}`
  - Soft-archives the private session and removes it from Coach history.

No share endpoint exists in the first release.

---

## 14. Model and security boundary

### 14.1 Separate connection class

Call coaching is a new payload class in `CONNECTIONS.md`. Approval of transcript extraction or
Copilot does not approve coaching payloads. The default implementation is mock/manual and local.
Connecting a real model requires the existing Valence hosting/data-handling gate.

### 14.2 Untrusted input

Transcript, source metadata, reflection, account records, and retrieved prose are untrusted data.
They cannot:

- Change the system instruction.
- Select a tool or connector.
- Select an account.
- Choose the coached speaker.
- Change the rubric.
- Add output fields.
- Cause a write.
- Request another account's context.

The coaching backend has no tools, browser, arbitrary retrieval, or outbound access beyond the
approved model call. Output passes the strict validator in §8 before persistence.

### 14.3 Data minimization

Only the context required by the selected rubric enters the model payload. A standalone call sends
no account data. An account-linked risk-recovery call does not receive the entire value library merely
because it exists. The context builder records which sections it supplied and omitted.

### 14.4 Privacy by construction

- Coaching tables are absent from account export.
- Account Ledger reads no coaching table.
- QBR, MAP, team update, leadership review, search index, attention queue, readiness, and company
  intelligence read no coaching table.
- Rehearsal reads may use account context but no domain module imports coaching.
- Product telemetry carries no transcript, filename, quote, observation, skill, reflection, call
  title, participant, call type, or coaching goal.
- Backups include private coaching because they back up the local database; the Operations copy says
  this explicitly.

### 14.5 Source deletion and retention

The first release has no automatic expiry. Automatic deletion could silently remove the evidence
behind an active goal. Zach may delete the retained snapshot at any time. The source panel states:

- What is retained.
- Where it is stored.
- Which model/backend processed it.
- Whether the source can still ground observations and account proposals.

Audio, when later considered, requires separate consent, recording, retention, and deletion design.

---

## 15. Failure and empty states

Every failure is local, specific, and recoverable.

### 15.1 Source states

- **Empty:** "Add a transcript or detailed notes to begin."
- **Unsupported kind:** names the kind and accepted alternatives.
- **Too large:** states the enforced limit before suggesting a smaller source.
- **Undecodable:** no replacement characters are persisted or quoted.
- **Duplicate:** identifies the prior private session with same content hash; offers Open prior or
  Analyze again with a reason. Duplicate does not silently suppress a deliberately different rubric.
- **Source deleted:** observations remain, with "Source deleted; this quote can no longer be
  verified against the full transcript."

### 15.2 Analysis states

- **Too little material:** asks for transcript or more detailed notes; does not grade fragments.
- **Speaker unresolved:** offers mapping or restricted content-only review.
- **No timestamps:** uses ordered passages and never fabricates time.
- **Partial transcript:** names omitted ranges; avoids whole-call absence claims.
- **Model unavailable:** preserves draft and offers retry/manual mode.
- **Invalid model output:** run fails with validator reason; invalid observations never render.
- **No supported opportunity:** says that explicitly and foregrounds a strength or source limitation.

### 15.3 Account states

- **Account context unavailable:** review can continue as general coaching; account lens says what was
  omitted.
- **Program outside account:** 422 before any link or Interaction write.
- **Interaction outside account:** fail closed without disclosing it.
- **Interaction creation failed:** coaching draft survives; no meaningful touch is recorded.
- **Proposal extraction failed:** coaching survives; the independent action remains retryable.
- **Account action partially completed:** each command reports only its own receipt. Reopening the
  review reads the linked Interaction and extraction run from stored state; retries do not recreate
  either bridge.
- **Existing open proposals:** new run remains separate and Proposal Review shows match/conflict
  candidates under its existing rules.
- **Account archived after review:** session remains private and labels the historical link archived.

### 15.4 Rehearsal states

- **No target skill:** choose one observation or write a practice goal.
- **Attempt too short:** ask for a complete sentence that performs the target behavior; do not score
  absence.
- **Unsupported skill:** refuse the unknown key rather than silently mapping it to another skill.

---

## 16. Visual and interaction design

### 16.1 Character

Coach follows the existing refined dark/light design system: atmospheric page depth, precise focus
states, restrained glass/elevation, and fast expo-out transitions. Its personality comes from calm
focus and evidence interaction, not decorative dashboards.

### 16.2 Hierarchy

- One dominant Start here panel.
- One accent action at a time.
- Strength and opportunity use words and icons, not green/red judgment blocks.
- Account implications are visually separate from personal coaching and proposals.
- Dense transcript content uses the utility face; coaching headlines use the existing restrained
  display hierarchy.
- Long prose is limited to readable measure; source context uses a focused modal rather than a
  permanently split transcript pane.

### 16.3 Motion

- Targeted practice scrolls into view and source highlighting appears without theatrical delay.
- No animated score rings, confetti, streaks, bouncing coach avatar, or simulated typing delays.
- Processing uses honest stage labels rather than a theatrical conversation.
- Reduced-motion removes scroll animation and ambient movement without removing focus.

### 16.4 Copy

Use direct, non-judgmental language:

- "Start here," not "Biggest weakness."
- "Try next time," not "Failed criteria."
- "The source supports," not "The AI knows."
- "Likely impact," not "They felt."
- "Make this my focus," not "Assign remediation."
- "Practice — not an account event," wherever rehearsal uses account context.

---

## 17. Evaluation and product measurement

This is a personal improvement tool. Success is not the number of generated observations.

### 17.1 Quality measures

- **Citation fidelity:** every rendered completed-call observation locates exactly in the retained
  source. Release gate: 100% across the golden set.
- **Speaker fidelity:** no observation attributes a line to Zach without an operator-confirmed mapping.
- **Top-priority usefulness:** Zach marks the dominant observation Useful more often than Inaccurate
  or Dismissed across the first ten representative reviews. Report counts, not a percentage that
  implies a population.
- **Actionability:** Zach can enter a relevant practice attempt directly from every supported top
  priority.
- **Account separation:** zero coaching observations in account outputs or deterministic readiness.
- **Proposal integrity:** account updates retain current proposal validation, citation, conflict, and
  human-decision behavior.

### 17.2 Behavior-loop measures

Derived privately from coaching records:

- Reviews completed.
- Top priorities marked Useful / Inaccurate / Dismissed as separate counts.
- Goals activated, replaced, completed, or abandoned as separate counts.
- Rehearsals started and completed.
- Comparable later observations for the same skill and rubric version.

No composite adoption or quality score is calculated. These records are for Zach's own reflection,
not an organizational report.

### 17.3 Surface telemetry

Coach surfaces register with Stage 17 so reachability and retirement safety work. Existing generic
`surface_rendered` / `surface_engaged` events are sufficient. Coaching-specific semantic telemetry is
not added in the first release; the private domain rows answer the product questions more accurately
without exporting content-shaped properties.

The built registry contract is exact:

- `coach.home` — daily scheduled surface.
- `coach.intake` — unscheduled intake; no invented trigger proxy.
- `coach.review` — event-driven on `coaching_run_completed`.
- `coach.practice` — event-driven on `coaching_priority_available`.
- `coach.history` — weekly scheduled surface.
- `command.review_call` — global command, separate from surfaces.

The two trigger evaluators are measurement-side reads over coaching status/priority rows. Coaching
domain code never imports telemetry. Their counts decide whether a usage window is observable and
are never divided by renders or engagements. Measurements carry only registry keys, route/kind,
closed-vocabulary operation, position, and scope shape—never transcript, title, speaker, account
name, quote, observation, skill, reflection, or goal. This inherits Stage 17's fail-towards-showing
retirement behavior and its refusal to combine rendered and engaged into a score or rate.

### 17.4 Golden call set

Before enabling a real model, create a local, synthetic or approved fixture set covering:

1. AGCO-style deployment planning with a launch-strategy tension.
2. Kickoff that lacks a success metric.
3. Excellent stakeholder discovery with no commercial purpose.
4. Executive review rich in anecdotes but weak in comparable evidence.
5. Renewal call with authority and timing ambiguity.
6. Risk-recovery call where Zach acknowledges before solutioning.
7. Internal disagreement resolved through synthesis and commitment.
8. Standalone interview/networking call.
9. Transcript with ambiguous speakers and no timestamps.
10. Malicious transcript containing prompt-injection instructions.
11. Partial/chunk failure.
12. Rehearsal that invents a persona detail unless constrained.

Each fixture has human-authored acceptable observations, unacceptable inferences, relevant rubric,
and account-write expectations. The model need not reproduce exact prose; it must stay within the
acceptable evidence and boundary set.

---

## 18. Implementation plan

Sections 18.0–18.4 are the complete Stage 18 release and are built. They are retained as an
implementation manifest, not an invitation to add the governed capabilities in §18.6.

### 18.0 Integrity foundations — built

**Goal:** establish the private domain and prevent it from leaking into account truth before a model
can produce anything.

Deliverables:

- Migration with the five §12 tables and indexes.
- Schema-introspection tests proving `interactions.account_id` remains non-null and no coaching table
  is read by account output modules.
- Coaching source parser and strict response contract owned by the private coaching domain.
- Private source create/read/delete lifecycle.
- Session scope validation and audit.
- Versioned rubric definitions and response schemas.
- Deterministic local coaching backend with exact-citation validation.
- `coaching_analyze` job registration using the existing worker.
- `CONNECTIONS.md` entry with real-model gate closed.

Acceptance:

- Standalone session persists with every account/program/interaction field null.
- Account session rejects a foreign program or Interaction.
- Bytes never persist.
- Deleting snapshot preserves session/run/observations and degrades grounding explicitly.
- Prompt injection cannot alter schema, account scope, rubric, or write anything.
- No coaching row appears in account export, QBR, MAP, team update, Ledger, readiness, or search.

The boundary is acceptance-tested before the UI path is considered complete.

### 18.1 Global Coach and source intake — built

**Goal:** make standalone and linked sources easy to create and revisit.

Deliverables:

- Coach rail destination, route codec, breadcrumb, help copy, and command-palette entry.
- Coach home with active focus, start actions, and recent sessions.
- New review page implementing scope, source, speaker, frame, and reflection sections. Account
  actions deliberately appear only on the completed result.
- Paste and file browse for TXT/MD/VTT/SRT, server limits, refusal copy, and processing state.
- Optional account, program, and existing-Interaction scope through the same contract.
- Responsive, keyboard, focus, and reduced-motion behavior.
- Surface registry entries and generic usage instrumentation.

Acceptance:

- A standalone transcript reaches a queued analysis without selecting an account.
- An account-launched review is visibly prefilled but changeable.
- The transcript cannot select or change scope.
- Audio/video refuse before decode and explain the transcript alternative.
- Unknown speaker continues in restricted mode with named limitations.
- Narrow layout remains usable split-screened beside a call.

### 18.2 Coaching analysis and review — built

**Goal:** deliver the evidence-to-practice loop with no account mutation.

Deliverables:

- Universal and initial call-type rubrics from §9.
- Context-free standalone coaching prompt and strict validator.
- One bounded source (1 MB maximum) with explicit restricted/partial coverage.
- Results page with fixed §7 hierarchy.
- Exact source highlighting and observation-to-source navigation.
- Useful / Inaccurate / Dismissed response capture.
- Active coaching goal lifecycle.
- Active focus routes to its exact prefilled practice composer and can be completed from Coach home.
- Deterministic local backend; real backend remains separately gated.

Acceptance:

- At most two strengths and two opportunities render.
- One supported opportunity is dominant or the absence is stated.
- Every observation resolves to an exact source passage.
- Inferred impact is labeled and never presented as observed reaction.
- The coached speaker is the only person evaluated.
- No numeric score/confidence/sentiment/emotion field exists in API or UI.
- Restricted coverage cannot produce speaker-specific claims.
- Zach can make one observation his focus in one action.

### 18.3 Account-aware review and proposal bridge — built

**Goal:** use account context without mixing coaching, readiness, and canonical facts.

Deliverables:

- Deterministic account-context builder and stored snapshot.
- Relationship-readiness lens with coaching-only labels.
- Shared `interaction_ops.create` refactor and parity tests against QuickEntry.
- Optional Interaction logging from new account reviews.
- Optional call to existing extraction and `_persist_run`.
- Coaching-source resolver in proposal grounding.
- Idempotent extraction-run receipt and exact deep link into the opened Proposal Review section.
- Late link/unlink preview and audited actions.

Acceptance:

- Account context includes only allowlisted, accepted, in-scope records and names omissions.
- Current readiness wording is consumed verbatim and never recalculated.
- Coaching implications update no readiness or domain table.
- Rehearsals create no Interaction, proposal, touch, or account history row.
- New completed calls use the same native Interaction validations as QuickEntry.
- Drafted facts appear only in existing Proposal Review with exact call citations.
- Retrying the draft command creates no duplicate extraction run, and a run from another coaching
  session is rejected.
- Coaching page exposes no proposal resolution command.
- Linking later creates a new run rather than rewriting standalone history.

### 18.4 Targeted rehearsal — built

**Goal:** make the top coaching observation immediately practicable.

Deliverables:

- Bounded, text-first retry of one selected moment.
- Focused practice evaluator and exact attempt citations.
- Return-to-review and new-practice paths.
- Persistent Practice — not an account event labeling.

Acceptance:

- Practice evaluates only the selected skill.
- No simulated statement enters account extraction or context.
- A too-short attempt receives insufficient coverage, not a poor grade.
- The completed loop is reachable from Start here without returning to Coach home.

### 18.5 Personal history and trends — specified, intentionally not in Stage 18

**Goal:** help Zach notice repeated patterns without pretending a small sample is a score.

Deliverables:

- History filters and stable session titles.
- Skill history over comparable call type + rubric version only.
- Active-focus review and practice-again flow.
- Counts of response and goal outcomes, no ratios or grades.
- Selected side-by-side source moments from two sessions.

Entry gate:

- At least ten real or approved representative reviews exist.
- Zach confirms which history questions he actually wants answered.
- Rubric churn is low enough that a comparison is honest.

This slice is intentionally not detailed into charts before use data exists. Building a dashboard
first would optimize a coaching model that has not yet proved useful.

### 18.6 Later governed capabilities — not authorized by this spec

- Audio upload and transcription.
- Calendar/meeting recording connections.
- Voice rehearsal.
- Live call prompts.
- Sharing a selected coaching moment.
- Manager/team coaching.
- Aggregated organizational insights.

Each needs its own scope, consent, retention, accessibility, and connection decision.

---

## 19. Test matrix

### 19.1 Schema and boundary tests

- Coaching tables and indexes match §12.
- `interactions.account_id` remains NOT NULL.
- One active goal and one top priority per run.
- Rehearsal launched from an observation preserves parent and origin; standalone practice may have
  neither.
- No stored score, trend, readiness, freshness, applicability, emotion, sentiment, or confidence
  column exists in coaching tables.
- Coaching source can survive account archive and cannot FK to a foreign program/interaction through
  the API.

### 19.2 Source and grounding tests

- Paste/TXT/MD/VTT/SRT detection and parsing.
- Audio/video refusal.
- UTF-8 failure without replacement-character persistence.
- Same content hash is stable across transport.
- Exact quote locates once, repeated quote requires disambiguation, altered quote fails.
- Snapshot deletion degrades rather than erases observations.
- Oversized sources refuse before persistence; completed local runs state that the whole retained
  source was read.

### 19.3 Coaching contract tests

- Too many observations rejected or clipped by deterministic validator with coverage note.
- Unknown skill key rejected.
- Missing source span rejected.
- Non-coached participant evaluation rejected.
- Inferred impact labeled.
- Numeric score/confidence/sentiment/emotion output rejected.
- Prompt injection text remains data.
- No-opportunity output renders honestly.

### 19.4 Account integration tests

- Standalone analysis performs zero account reads.
- Program and Interaction ownership validation.
- Interaction-create parity with QuickEntry.
- Rehearsal produces no touch or proposal.
- Account context excludes drafts, private Nadia data, other programs, and other accounts.
- Readiness response is passed through without state translation.
- Proposal run uses existing store and review commands.
- Proposal grounding resolves coaching source and degrades after deletion.
- Coaching UI route table exposes no accept/reject/resolve endpoint.
- Account export and client outputs exclude coaching by construction.

### 19.5 UI and accessibility tests

- Route round-trip for home, review/rehearsal intake, session practice focus, and exact Proposal
  Review run.
- Keyboard-operable paste/file source intake.
- Speaker selection accessible by label.
- Labeled source-moment dialog and close control.
- State not conveyed by color.
- Reduced motion.
- Narrow viewport and zoom to 200%.
- Loading, partial, failed, source-deleted, and empty states.

### 19.6 Golden behavior tests

For every §17.4 fixture:

- At least one acceptable top-priority path or an honest insufficiency outcome.
- Zero forbidden inferences.
- All citations exact.
- Call-type rubric applicable.
- Expected account-write boundary preserved.
- Rehearsal remains restricted to its selected skill.

---

## 20. Release gates

### 20.1 Built local gate

- Focused Stage 18 boundary, API, navigation, source, and Surface Usage tests green.
- Full repository validation after the hardening pass: 1,025 backend tests and 336 frontend tests;
  frontend lint exits successfully with the standing warning set, and the production build passes.
- Exact citation fidelity is enforced by contract and acceptance tests; the larger golden set is a
  gate for a real model, not a pretense that the deterministic backend has been clinically scored.
- Automated route, contract, responsive-style, lint, and build checks pass. A rendered click-through
  remains outstanding because no in-app browser was attached to the validation session; the handoff
  states this explicitly rather than claiming a visual gate that did not run.
- No account/client-output leakage.
- Backup and source-deletion behavior documented.
- `CONNECTIONS.md`, `decisions.md`, `HANDOFF.md`, and `CLAUDE.md` authority chain updated with the
  built boundary and closed external gates.

### 20.2 Real-model gate

- Valence-approved hosting and data-processing path.
- Explicit coaching payload classification.
- Provider retention and training-use policy documented.
- Model/prompt version and deletion semantics verified.
- Golden-set evaluation against the proposed model.
- Runtime switch fails closed.
- Manual/local mode remains available.

### 20.3 Audio/live gate

Not inherited from the real-model gate. Requires separate consent, recording notice, transcription,
retention, participant access, deletion, and live-distraction review.

---

## 21. Research translated into product rules

| Research/platform pattern | Product decision |
|---|---|
| Effective feedback answers where am I going, how am I going, and where next | Intended outcome + cited observation + immediate practice |
| Deliberate practice requires a defined skill, feedback, reflection, and repetition | One active focus and bounded rehearsal, not a static report |
| Coaching standards emphasize trust, listening, awareness, and client-owned growth | Private default, self-reflection, Zach activates the goal |
| Gong/Zoom use call-type scorecards and timestamped evidence | Versioned call-type rubrics and exact source moments |
| HubSpot uses clips/playlists to teach concrete examples | Later private example history, not a leaderboard |
| Yoodli joins feedback to roleplay | Practice this is part of the first release |
| Conversation metrics vary by call type | No universal talk ratio, question count, filler-word, or pace grade |
| Workplace analytics create monitoring and employment risk | No manager mode, employment use, emotion inference, or hidden sharing |
| Existing Valence OS treats external text as untrusted and facts as proposals | Strict no-tool coaching call; account facts remain cited proposals |
| Readiness is deterministic and independent across six pillars | Account lens consumes readiness and never scores or writes it |

Primary references:

- Hattie & Timperley, *The Power of Feedback*:
  https://educacion.udd.cl/files/2018/04/The-Power-of-Feedback.pdf
- Ericsson et al., deliberate-practice review:
  https://pmc.ncbi.nlm.nih.gov/articles/PMC6824411/
- International Coaching Federation core competencies:
  https://coachingfederation.org/resource/2019-icf-core-competencies/
- AHRQ OARS communication skills:
  https://www.ahrq.gov/evidencenow/tools/oars-model.html
- Gong scorecards and call-type examples:
  https://help.gong.io/docs/all-about-scorecards
- Gong 2025 talk/listen and question analysis:
  https://www.gong.io/blog/talk-to-listen-conversion-ratio
- Zoom evidence-linked coaching scorecards:
  https://support.zoom.com/hc/en/article?id=zm_kb&sysparm_article=KB0058647
- HubSpot coaching playlists:
  https://knowledge.hubspot.com/calling/use-coaching-playlists-to-train-your-team
- Yoodli personal coaching and roleplay overview:
  https://support.yoodli.ai/en/articles/9550461-yoodli-overview
- Microsoft Conversation Intelligence use and employment warning:
  https://learn.microsoft.com/en-us/dynamics365/sales/dynamics365-sales-insights-app
- ICO workplace-monitoring guidance:
  https://ico.org.uk/for-organisations/uk-gdpr-guidance-and-resources/employment/monitoring-workers/data-protection-and-monitoring-workers/
- NIST AI RMF Core, targeted scope and human oversight:
  https://airc.nist.gov/airmf-resources/airmf/5-sec-core/

Vendor findings are treated as product-pattern evidence and observational benchmarks, not universal
causal laws. The golden set and Zach's own Useful/Inaccurate responses decide whether the resulting
coach is valuable in this workflow.

---

## 22. Definition of done

The initial Call Coach is complete when Zach can:

1. Open Coach globally.
2. Paste a standalone completed call without selecting an account.
3. Identify himself and the intended outcome.
4. Receive one prioritized, exact-cited coaching observation plus a small set of strengths and
   opportunities.
5. Mark the observation useful or inaccurate and make it his active focus.
6. Practice that exact skill in a bounded rehearsal and receive focused cited feedback.
7. Repeat the same flow for an account-linked call using current account context.
8. Optionally log that completed call as one native Interaction.
9. Optionally draft account facts into the existing Proposal Review workflow.
10. Verify that neither the coaching review nor rehearsal appears in readiness, Ledger, account
    outputs, client materials, or account export.
11. Delete the retained source while preserving an honest, degraded private coaching history.
12. Revisit his active focus and recent sessions from Coach home without seeing a grade, leaderboard,
    or wall of analytics.

If any one of items 4, 6, 9, or 10 fails, the product is not a call coach layered safely on Valence
OS; it is either a transcript report, a roleplay toy, a competing ingestion path, or a privacy leak.
