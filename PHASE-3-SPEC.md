# Valence OS — Phase 3 Spec: Feature-Complete Build
### From working skeleton to a full account operating system
*Zach McCall · July 2026 · v1 · Supersedes the Phase 2 evidence gates*

---

## 0. Operating rules for this phase

**The prior evidence gates are retired.** Zach has run enterprise account launches before; that pattern knowledge is the evidence. Build to feature-complete now; tweak from real use later.

**One rule replaces them all: build everything, connect nothing real.** Every feature is built and tested end to end against synthetic data, mock inboxes, and sample recordings. Nothing points at a real work email, real call recordings, real calendars, or real client files until hosting and data handling are cleared at Valence. Every external connection is an adapter with a mock implementation now and a config-swap to the real source later. Section 9 maintains the registry of these switches.

**Unchanged and still binding:** the trust boundaries (no individual product usage anywhere; internal-only records excluded from client-facing outputs by construction; stakeholder judgments carry date and evidence), the design guide, tests green, decisions logged.

---

## 0b. Reconciliation with the current build (read before estimating)

Verified against the repo as of migration 0010, 67 tests, all numbered phases complete.

**Already built, so the sections below extend rather than create:** pluggable transcript extraction (mock / local LLM / Claude API) under the security model → Section 5 extends it. Plays trigger engine with effectiveness notes and notifications → Section 7 adds triggers. A pre-call briefing → Section 6 upgrades it. QBR generator, team update, MAP (★-promotion), files library, phase gates, stakeholder graph with coverage sidebar, cmd-K palette, global search, account export/restore all exist and are foundations here, not deliverables.

**Previously deferred, now prerequisite:** the job table and single in-process worker (§7/8 of the scoping doc) were deliberately skipped because all work was synchronous. Transcription, email sync, association runs, and scheduled generation are background work, so the job infrastructure is the first engineering task of this phase.

**Task zero: update the standing documents, or the agent will fight this spec.** CLAUDE.md still enforces the frozen scope and forbids v4-style features and external wiring; HANDOFF.md declares the current state the intended stopping point. Before any Phase 3 code: amend CLAUDE.md to reference this spec as the current authority (trust boundaries, design rules, and mock-only data unchanged; scope rules superseded), update HANDOFF.md, and add the newly permitted dependencies explicitly (python-pptx for deck export, an email parsing library, an ics parser, and a transcription adapter interface with a mock implementation). Log the regime change in decisions.md.

---

## 1. Guided account onboarding

The moment an account is assigned is the moment of maximum busyness and maximum setup value. Creating an account triggers a guided onboarding flow that seeds everything below in one pass.

**1a. Intake.** A single form or paste-box for what sales hands over: deal context, sales notes, named contacts, seat count, contract dates, incumbent vendors, known dates. An AI-assisted parse (same approval pattern as transcript extraction: proposed records, human accepts each) converts pasted sales notes into draft stakeholders, dates, incumbent entries, and open questions. Nothing writes without acceptance.

**1b. Seeded project plan.** A program is created with the standard phase structure, governance cadence placeholders, and a milestone set from the launch template: kickoff call, tech setup complete, HR soft launch, organic launch, first programmatic integration, first value readout, day-90 step-back. All dates relative to the kickoff date and editable.

**1c. Kickoff scheduling.** A kickoff milestone with a date picker that generates calendar entries through the calendar adapter (mock now, real later). Prep tasks auto-created and back-scheduled from the kickoff date: deck ready minus 3 days, agenda sent minus 2 days, internal alignment minus 1 day.

**1d. Kickoff deck skeleton.** Generates a deck outline (markdown now, pptx export as part of Section 6) with the consistent framework sections prepopulated: who we are and how we work, the deployment approach (three workstreams), the proposed 30/60/90, success metrics to agree on, roles and cadence, next steps. Two clearly marked slots pull from the account record: deal context and sales-notes highlights, and the stakeholder list as currently known. The skeleton is a template file in the repo so Zach can evolve it without code changes.

**1e. First-call question list.** Seeded from a template: the things to understand in call one (success definition, budget owner, metric of record, talent calendar, incumbent status, IT/legal path, works-council exposure). Each question is a checklist item that, when answered, prompts filling the corresponding account field. The template is editable; per-account additions welcome.

---

## 2. Launch checklists with falling-behind escalation

Generalize phase gates into time-phased launch checklists, seeded per account from templates:

- **First call:** the Section 1e question list.
- **First two weeks:** metric definitions agreed, scorecard and budget owner named, comms plan drafted, tech setup started, compliance lanes opened.
- **First 30 days:** HR soft launch done, baselines captured, first cohort activated, governance cadence running.
- **First 90 days:** per the standard plan (organic launch, programmatic integrations identified, value stories captured, step-back scheduled).

**Escalation behavior.** Every checklist item carries a due window relative to kickoff. An item past its window fires into Today with the standard attention treatment; an item more than a week past renders in the risk treatment and appears on the account overview. Falling behind must be impossible to miss without being nagging: one line in the queue, one marker on the overview, nothing else.

Templates live as editable seed files. Adding a Valence-specific item (e.g., works-council packet requested) is a file edit, not a schema change.

---

## 3. Org chart with unknown positions

Extend the stakeholder map with a **placeholder node type**: a position Zach knows must exist but hasn't identified, e.g., "VP of IT, name unknown" or "CHRO, not yet met." Placeholders render in the cross-hatched unknown treatment, sized by expected influence, and connect into the reporting structure like any node.

- Each placeholder carries: expected title, why it matters, and a find-by date. Past the date, it fires into Today ("Still haven't identified the budget owner's boss").
- Converting a placeholder to a real person is one action that preserves edges.
- The coverage sidebar counts placeholders as exposure: "3 senior relationships active, 2 critical positions unidentified."
- Seed templates per account type: every new account starts with placeholders for champion, budget owner, CHRO, IT security lead, legal/DPO, and works-council contact where Europe is in scope. Knowing who you're missing on day one is the point.

---

## 4. Communications ingestion (recordings and email)

Built fully now against mock sources; flipped to real sources later via Section 9.

**4a. Call recordings/transcripts.** A watch-folder or upload endpoint accepts recordings or transcripts. The pipeline: transcribe if audio (adapter; mock returns fixture transcripts), auto-associate to an account and program by matching attendee names/emails and account keywords against the stakeholder registry, create a draft Interaction, and run the extraction pass (Section 5). Association confidence is shown; low-confidence items land in the capture inbox for manual assignment instead of guessing silently.

**4b. Email.** An email adapter (mock inbox now: a folder of .eml fixtures; real provider later) syncs messages, auto-associates by sender/recipient against stakeholder emails, and threads them onto the account's ledger as lightweight comm records: from, to, date, subject, one-line AI summary, link to the original. Full bodies stored only per the link-first rules; the summary is the working record.

**4c. Priority flagging.** A rules-plus-AI pass flags emails needing response: named stakeholder asking a direct question, commitment-related language, renewal or procurement keywords, anything from the champion or budget owner unanswered beyond a threshold (default 24h business time). Flagged items fire into Today with the reason stated ("Colleen asked about the April date, unanswered 26h"). Thresholds and VIP lists are per-account settings.

**4d. The association engine is shared.** One service resolves people and accounts for both recordings and email, learns from manual corrections (a correction updates the matching hints), and never hard-deletes an association, only supersedes it.

---

## 5. AI extraction pipeline (extend the existing one)

The pluggable extraction pipeline already exists (mock / local LLM / Claude API) under the required security model. This phase extends it rather than builds it:

- **New input type:** email bodies flow through the same extraction path as transcripts, producing the same proposal types.
- **New extraction targets:** proposed placeholder-fills for the org chart (Section 3), pull signals, deployment-moment references, and value-story candidates, alongside the existing commitments/decisions/risks/stakeholders.
- **Upgraded review screen:** a single keyboard-driven review surface per interaction, accept/edit/reject per item, source span visible for every proposal, nothing writes otherwise. This becomes one of the highest-frequency screens in the app and deserves corresponding design care.

The existing guarantees carry forward unchanged: strict JSON schema of predefined mutation types, per-item human acceptance, model and prompt versions in the audit log, content treated as data never instructions.

---

## 6. Generators, upgraded to finished artifacts

Everything the tool hands to someone else becomes one click and genuinely finished:

- **Pre-call brief, upgraded.** The existing briefing extends to pull from the new sources: attendees with stances and last touches, open commitments involving them, unanswered flagged emails, live risks, gate items due, and suggested talking points from open first-call questions. Target: the five-minute prep scenario fully automated.
- **Kickoff and QBR decks as real .pptx** (python-pptx), from the skeleton templates plus live data, honoring the visibility rules (internal-only never renders) and the stamping rules (generated-at, data-current-through, confirmed fact vs. interpretation vs. recommendation).
- **Champion enablement kit.** Per account: a one-page value summary and the ROI model with current inputs (seat price assumption, retention math, recovered vendor budget), exportable as pptx/pdf, drawing only records approved for client presentation.
- **Expansion business case builder.** Assembles the commercial view into a document: the scorecard vs. agreed bar, value stories by evidence tier, the funding waterfall, named expansion lines, the ask. The day-75 artifact, pre-built continuously instead of at day 75.
- **Weekly team update**, now schedulable: generated on a timer through the job table, saved as a draft for review, never auto-sent.

---

## 7. Plays engine: new triggers on the existing engine

The trigger engine, play runs, effectiveness notes, and notifications already exist. This phase adds triggers: gate/checklist item overdue (Section 2 escalation), unanswered priority email past threshold (Section 4c), placeholder position past its find-by date (Section 3), champion gone quiet, stalled cohort across observations, and expansion signal (unit crossing the agreed bar; pull signals logged). The existing renewal-window trigger stays. Notification delivery beyond in-app remains an adapter (mock now, real later).

---

## 8. Calendar integration

A calendar adapter (mock now: an .ics fixture set) that reads meetings for association and prep-brief targeting, and writes kickoff, governance cadence, and QBR entries. Real connection is a Section 9 switch.

---

## 9. The real-data switch registry

One file, `CONNECTIONS.md`, listing every adapter, its current mode, what real connection requires, and what approval gates it: transcription source, email provider, calendar, notification channel, LLM endpoint, file storage, hosting itself. Each entry names the mock fixture set that proves the feature works. Flipping any switch to real requires the hosting/data-handling conversation at Valence to have happened, and the flip is recorded in decisions.md. This is the single remaining gate in the project, and it is a data-governance gate, not an evidence gate.

---

## 10. Build order

0. **Task zero:** update CLAUDE.md, HANDOFF.md, and decisions.md per Section 0b, then build the job table and in-process worker.
1. **Onboarding pack + checklists + placeholders** (Sections 1-3): pure product, no adapters, immediately demonstrable.
2. **Association engine + email/recording ingestion on mocks** (Section 4), running through the job table.
3. **Extraction extensions + upgraded review UI** (Section 5).
4. **Generators to finished artifacts** (Section 6).
5. **New triggers + calendar adapter** (Sections 7-8).
6. **CONNECTIONS.md registry + end-to-end demo script**: a full mock account run from assignment to expansion case, exercising every feature.

Each stage: tests, screenshots in both themes, HANDOFF.md updated. Design guide governs all new surfaces; the review screen (Section 5) and onboarding flow (Section 1) are the two new screens that deserve the most design care, since they are the highest-frequency and first-impression surfaces respectively.

---

## 11. Definition of done for Phase 3

A brand-new mock account can go from "assigned" to "expansion business case delivered" entirely inside the tool: intake parsed, plan seeded, kickoff scheduled and decked, first-call questions answered into fields, checklists ticking with one deliberately missed item escalating correctly, a mock recording and mock emails ingested and associated, extraction proposals reviewed and accepted, placeholders on the org chart with one converted to a real person, a pre-call brief generated, a QBR pptx exported with correct visibility exclusions, plays fired and resolved, and CONNECTIONS.md accurately describing every switch still in mock. The 30-second capture rule still holds everywhere. Trust boundaries verified by the existing tests plus new ones covering the generators and ingestion paths.
