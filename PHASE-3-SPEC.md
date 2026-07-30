# Valence OS — Phase 3 Comprehensive Spec
### From working skeleton to a feature-complete account operating system
*Zach McCall · July 2026 · v1 · Supersedes the earlier PHASE-3-SPEC.md and PEOPLE-MODULE-SPEC.md by consolidating both. Companion to the scoping doc (v3.2), DESIGN-GUIDE.md, and CLAUDE.md.*

---

# Part 0 — Ground rules

## 0.1 Operating rules for this phase

**The prior evidence gates are retired.** Zach has run enterprise account launches before; that pattern knowledge is the evidence. Build to feature-complete now; tweak from real use later. Overbuilding is explicitly not a concern for this phase.

**One rule replaces the old gates: build everything, connect nothing real.** Every feature is built and tested end to end against synthetic data, mock inboxes, fixture recordings, and .ics fixtures. Nothing points at a real work email, real recordings, real calendars, or real client files until hosting and data handling are cleared at Valence. Every external connection is an adapter with a mock implementation now and a config swap later, tracked in the CONNECTIONS.md registry (Part 6).

**Unchanged and still binding:**
- Trust boundaries: no table, column, or view anywhere for a named individual's product usage; client-facing outputs include only affirmatively promoted records, by construction; stakeholder assessments are professional judgments with a date and an evidence note; no sensitive personal data on people (nothing on health, family, politics, or anything a works council would blink at; rapport notes stay professional).
- DESIGN-GUIDE.md governs every new surface.
- Tests green at every step; decisions logged in decisions.md; mock data only, including tests, seeds, and commit messages.

## 0.2 Reconciliation with the current build

Verified against the repo (migration 0010, 67 tests, all numbered phases complete).

**Already built; this spec extends rather than creates:** pluggable transcript extraction (mock / local LLM / Claude API) under the security model; plays trigger engine with effectiveness notes and notifications; a pre-call briefing; QBR generator; team update; MAP via ★-promotion; files and context library; phase gates; stakeholder graph with coverage sidebar and power-interest toggle; cmd-K palette; global FTS5 search; account export/restore.

**Previously deferred, now prerequisite:** the job table and single in-process worker. Transcription, email sync, association runs, enrichment checks, and scheduled generation are background work.

**Task zero, before any feature code:**
1. Amend CLAUDE.md: this spec is the current scope authority; trust boundaries, data rules, and design rules unchanged; the frozen-scope and stopping-point language is superseded. Present the diff for approval before committing.
2. Update HANDOFF.md to reflect the new phase.
3. Whitelist new dependencies: python-pptx (deck export), an email parsing library, an ics parser, a transcription adapter interface (mock implementation only).
4. Log the regime change in decisions.md.
5. Build the job table and worker per §7 of the scoping doc (queued/processing/succeeded/failed, retries, timestamps, input/output refs).

---

# Part 1 — Account onboarding pack (the "new account play")

The moment an account is assigned is the moment of maximum busyness and maximum setup value. Creating an account triggers a guided flow that seeds everything below in one pass.

**1.1 Intake.** A single form or paste box for what sales hands over: deal context, sales notes, named contacts, seat count, contract dates, incumbent vendors, known dates. An AI-assisted parse (same approval pattern as extraction: proposed records, human accepts each) converts pasted sales notes into draft stakeholders, dates, incumbent entries, and open questions. Nothing writes without acceptance.

**1.2 Seeded project plan.** A program is created with the standard phase structure, governance cadence placeholders, and a milestone set from the launch template: kickoff call, tech setup complete, HR soft launch, organic launch, first programmatic integration, first value readout, day-90 step-back. All dates relative to the kickoff date and editable.

**1.3 Kickoff scheduling.** A kickoff milestone with a date picker that writes calendar entries through the calendar adapter. Prep tasks auto-created and back-scheduled: deck ready minus 3 days, agenda sent minus 2 days, internal alignment minus 1 day.

**1.4 Kickoff deck skeleton.** Generates a deck outline (markdown, plus pptx export per Part 5) with the consistent framework sections prepopulated: who we are and how we work, the deployment approach (three workstreams), the proposed 30/60/90, success metrics to agree, roles and cadence, next steps. Two marked slots pull from the account record: deal context and sales-notes highlights, and the stakeholder list as currently known. The skeleton is a template file in the repo, editable without code changes.

**1.5 First-call question list.** Seeded from a template: success definition, budget owner, metric of record, talent calendar, incumbent status, IT/legal path, works-council exposure. Each question is a checklist item that, when answered, prompts filling the corresponding account field.

**1.6 Relationship seeding.** Every new account starts with placeholder positions per Part 3.3 (champion, budget owner, CHRO, IT security lead, legal/DPO, works-council contact where Europe is in scope), so day one shows who is missing, not an empty map.

---

# Part 2 — Launch checklists with falling-behind escalation

Time-phased launch checklists generalize the existing phase gates, seeded per account from editable template files:

- **First call:** the 1.5 question list.
- **First two weeks:** metric definitions agreed, scorecard and budget owner named, comms plan drafted, tech setup started, compliance lanes opened.
- **First 30 days:** HR soft launch done, baselines captured, first cohort activated, governance cadence running.
- **First 90 days:** organic launch, programmatic integrations identified, value stories captured, step-back scheduled.

**Escalation behavior.** Every item carries a due window relative to kickoff. Past its window it fires into Today with the standard attention treatment; more than a week past, it renders in the risk treatment and appears on the account overview. Falling behind must be impossible to miss without being nagging: one line in the queue, one marker on the overview, nothing else. Adding a Valence-specific item is a template edit, not a schema change.

---

# Part 3 — Relationship intelligence (the People module, feature-complete)

Built on the existing People tab. The trust boundaries in 0.1 apply to every feature here.

## 3.1 The layer model

Every stakeholder role carries a **layer**, because an F100 account is managed in horizontal bands:

| Layer | Who | What they need from us |
|---|---|---|
| **Executive** | CHRO, CFO-adjacent execs, BU presidents | Strategy alignment, the business metric of record, brief and rare touches |
| **Economic** | Budget owner, procurement, finance gatekeepers | ROI, funding path, contract mechanics, timeline certainty |
| **Operational** | Program owners, HRBP leads, day-to-day partners | Execution reliability, responsiveness, making them look good |
| **Technical & gating** | IT security, legal/DPO, works council contacts | Clean answers, early engagement, no surprises |
| **User & advocate** | Managers, HRBPs, early adopters, story sources | Value in their own work, recognition, a voice upward |

Layer lives on the role (per program), and drives defaults everywhere: cadence targets, quadrant expectations, briefing content, messaging.

**Layer-lane chart view.** A second org-chart layout alongside the reporting hierarchy: horizontal bands by layer, reporting and influence edges drawn across bands, placeholders rendered in their expected band. An empty or stale band is visible as a band.

## 3.2 Role taxonomy

Extend roles to the full buying committee: executive sponsor, financial gatekeeper, procurement, technical evaluator, legal/compliance, end-user voice, **coach** (gives information but won't advocate), **champion** (advocates with influence), and **detractor/blocker**. The coach-vs-champion distinction is enforced by evidence: a champion tag requires at least one logged instance of advocacy without us in the room; otherwise the system labels them coach and says why. Role expectations feed the pre-call brief: the financial gatekeeper's card leads with ROI state, the technical evaluator's with open security items.

## 3.3 Placeholder positions (the unknown-people feature)

A placeholder node type: a position that must exist but isn't identified. "VP of IT, name unknown." Renders in the cross-hatched unknown treatment, sized by expected influence, connected into the structure like any node. Each carries expected title, why it matters, and a find-by date; past the date, it fires into Today. Converting a placeholder to a real person is one action that preserves edges. The coverage sidebar counts placeholders as exposure.

## 3.4 Champion development pipeline

Per candidate: **identify → develop → validate → arm → maintain.**
- Identify: flagged from stance, influence, and engagement signals.
- Develop: value delivered to them personally, logged against their name.
- Validate: logged validation events (presented internally without us, secured a meeting we couldn't, defended us to a skeptic), each with source.
- Arm: linked to the champion enablement kit; tracks what they've been given and when it goes stale against current data.
- Maintain: cadence per 3.6, decay alert if engagement drops.

Every account shows champion count by stage and fires a play if no validated champion exists beyond the primary (single-thread risk, measured).

## 3.5 Influence paths

Pick any target, person or placeholder, and the map highlights the shortest credible paths to them: reporting and influence edges weighted by relationship strength, so a two-hop path through strong relationships ranks above a one-hop through a weak one. The output is an action: "Ask Dike to introduce you" becomes a task with one click. Multithreading as route-planning.

## 3.6 Cadence engine

Every stakeholder gets a target touch cadence, defaulted by layer and power-interest quadrant, overridable per person: manage closely, 2 weeks; keep satisfied, 6 weeks in executive-brief format; keep informed, monthly and can be one-to-many; monitor, quarterly pulse. The engine compares derived last-meaningful-touch against target and renders on the freshness ramp. Overdue relationships fire into Today with a **suggested next touch that carries content, not just contact**, pulled from what they care about, open items involving them, and wins not yet shared. "Ping Colleen" is banned; "Share the Brazil activation numbers with Colleen, she's presenting to the CHRO next month" is the standard. Cadence compliance per account is a visible number.

## 3.7 Relationship health, measured

Per person, an evidence-based panel, never a single opaque score: recency and frequency vs. cadence target; **reciprocity** (do they initiate, respond quickly, accept meetings, derived from our own correspondence via the comms and calendar adapters, counts and response-time distributions only); **attendance pattern** (invited vs. attended vs. ghosted); **stance trend** (the dated stance history as a timeline); **wins delivered**. Every element shows evidence and freshness, and feeds that person's pre-call card.

## 3.8 Executive alignment map

Which Valence executive owns which client executive, last exec-to-exec touch, next planned one. Unpaired client executives above a seniority line render as exposure. QBR and steering-forum attendance by layer is tracked; an Executive-layer meeting with no Executive-layer client attendance is a surfaced signal.

## 3.9 Org change detection and succession

- **Change flags:** an enrichment adapter (mock fixtures now) surfaces title changes, departures, and arrivals for tracked people; email bounce and domain-change heuristics as fallback. Every flag is a proposal to confirm, never an auto-edit.
- **Departure play:** fires the champion-loss play, captures the relationship record before it staleness, tags where they went (a departed champion elsewhere is a future account), opens a successor placeholder.
- **New-leader play:** a first-90-days engagement checklist: intro path via 3.5, tailored brief, an early win to offer.
- **Succession record:** when a role passes to a new person, history, preferences, and open items transfer visibly.

## 3.10 The person profile card

One screen per human, the unit the pre-call brief assembles from: name, title, layer, roles by program, stance trajectory, what they care about and the metric they are judged on, communication preferences (professional observations only), wins delivered, objections raised and status, open commitments both directions, influence edges, cadence state, full interaction history filtered to them.

## 3.11 Coverage and white-space analytics

- **Multithread ratio:** active VP+ relationships per account, single-thread alert at one.
- **Layer heat:** per-layer active / stale / placeholder counts on the layer-lane view.
- **Program coverage:** which programs have all key roles filled and in-cadence.
- **Detractor watch:** open detractors by influence, each with an owner and conversion plan status; a high-influence detractor with no plan is an attention item.

## 3.12 Role-based messaging library

Per layer and role: the value proposition in their terms, proof points that land, known objections and responses, current approved artifacts (visibility-classified). Feeds the deck generator's audience sections and 3.6's suggested-touch content. Seeded from the Valence playbook: exec, the business metric of record and scale; economic, the ROI model and funding path; technical, certifications and data handling; HRBP, what Nadia does for them.

## 3.13 Meeting dynamics

From attendee lists and transcripts via the extraction pipeline, professional observations only: who was present, who spoke on our items, who committed, who stopped showing up. Rendered as an attendance strip on governance and on person cards. No sentiment inference; the system counts observable facts and leaves interpretation to the operator's dated judgments.

---

# Part 4 — Communications ingestion

Built fully on mock sources; flipped later via Part 6.

**4.1 Call recordings and transcripts.** A watch folder or upload endpoint accepts recordings or transcripts, through the job table: transcribe if audio (adapter; mock returns fixture transcripts), auto-associate to account and program by matching attendees and keywords against the stakeholder registry, create a draft Interaction, run extraction (4.4). Association confidence is shown; low-confidence items land in the capture inbox for manual assignment, never guessed silently.

**4.2 Email.** An email adapter (mock inbox: a folder of .eml fixtures) syncs messages, auto-associates by sender and recipient against stakeholder emails, and threads them onto the ledger as lightweight comm records: from, to, date, subject, one-line AI summary, link to the original. Full bodies only per the link-first rules; the summary is the working record.

**4.3 Priority flagging.** A rules-plus-AI pass flags emails needing response: a named stakeholder asking a direct question, commitment language, renewal or procurement keywords, anything from the champion or budget owner unanswered past a threshold (default 24 business hours). Flags fire into Today with the reason stated ("Colleen asked about the April date, unanswered 26h"). Thresholds and VIP lists are per-account settings.

**4.4 Extraction extensions.** The existing pluggable pipeline gains: email bodies as an input type; new targets (placeholder-fills, pull signals, deployment-moment references, value-story candidates, alongside commitments, decisions, risks, stakeholders); and an upgraded review screen: one keyboard-driven surface per interaction, accept/edit/reject per item, source span visible on every proposal, nothing writes otherwise. Existing guarantees carry forward: strict JSON schema of predefined mutation types, per-item human acceptance, model and prompt versions audited, content treated as data never instructions.

**4.5 The shared association engine.** One service resolves people and accounts for recordings, email, and calendar; learns from manual corrections (a correction updates matching hints); never hard-deletes an association, only supersedes.

---

# Part 5 — Generators, upgraded to finished artifacts

- **Pre-call brief, upgraded.** Extends the existing briefing with the new sources: attendees with stances, cadence state, and last touches; open commitments involving them; unanswered flagged emails; live risks; gate items due; suggested talking points from open first-call questions; assembled from the person cards.
- **Kickoff and QBR decks as real .pptx** (python-pptx) from the skeleton templates plus live data, honoring visibility rules (internal-only never renders) and stamping rules (generated-at, data-current-through, confirmed fact vs. interpretation vs. recommendation).
- **Champion enablement kit.** Per account: a one-page value summary and the ROI model with current inputs (seat price assumption, retention math, recovered vendor budget), exportable pptx/pdf, drawing only records approved for client presentation, linked to 3.4's arm stage.
- **Expansion business case builder.** Assembles the commercial view into a document: scorecard vs. agreed bar, value stories by evidence tier, funding waterfall, named expansion lines, the ask. The day-75 artifact, built continuously.
- **Weekly team update, schedulable.** Generated on a timer through the job table, saved as a draft for review, never auto-sent.

---

# Part 6 — Plays, calendar, and the real-data switch registry

**6.1 New triggers on the existing plays engine:** gate/checklist item overdue (Part 2), unanswered priority email past threshold (4.3), placeholder past its find-by date (3.3), no validated second champion (3.4), champion gone quiet, stalled cohort across observations, expansion signal (unit crossing the agreed bar; pull signals logged), org-change flag confirmed (3.9). The renewal-window trigger stays. Notification delivery beyond in-app remains an adapter.

**6.2 Calendar adapter.** Mock: an .ics fixture set. Reads meetings for association, attendance metrics, and prep-brief targeting; writes kickoff, governance cadence, and QBR entries.

**6.3 CONNECTIONS.md, the single remaining gate.** One file listing every adapter, its current mode, its mock fixture set, what a real connection requires, and what approval gates it: transcription source, email provider, calendar, enrichment source, notification channel, LLM endpoint, file storage, hosting itself. Flipping any switch to real requires the hosting and data-handling conversation at Valence to have happened, and the flip is recorded in decisions.md. This is a data-governance gate, not an evidence gate.

---

# Part 7 — Build order

0. **Task zero** (0.2): CLAUDE.md diff for approval, HANDOFF.md, dependencies, decisions.md, then the job table and worker.
1. **Onboarding pack + checklists** (Parts 1-2): pure product, immediately demonstrable.
2. **People module core** (3.1-3.3, 3.10): layers, taxonomy, placeholders, person card. These upgrade everything downstream.
3. **Cadence + health + coverage** (3.6, 3.7, 3.11): the maintenance system.
4. **Association engine + ingestion on mocks** (Part 4), through the job table.
5. **Champion pipeline, influence paths, exec alignment, messaging library, meeting dynamics** (3.4, 3.5, 3.8, 3.12, 3.13).
6. **Generators to finished artifacts** (Part 5).
7. **New triggers, calendar, change detection** (6.1, 6.2, 3.9).
8. **CONNECTIONS.md + the end-to-end demo script.**

Each stage: tests, screenshots in both themes, HANDOFF.md updated. The extraction review screen, the onboarding flow, the layer-lane view, and the person card are the four new surfaces deserving the most design care.

---

# Part 8 — Definition of done

A brand-new mock account travels from "assigned" to "expansion business case delivered" entirely inside the tool:

1. Intake pasted and parsed; plan seeded; kickoff scheduled and decked; first-call questions answered into fields.
2. Placeholders seeded; one converted to a real person preserving edges; one left past its find-by date and escalating correctly.
3. Checklists ticking, with one deliberately missed item escalating through Today and the overview.
4. A mock recording and mock emails ingested through the job table, associated (one low-confidence case landing in the inbox), extraction proposals reviewed and accepted, including one placeholder-fill and one pull signal.
5. A priority email flag firing and clearing on reply.
6. The People tab answering, with dated evidence: who matters at every layer, who is overdue and what to bring them, who the validated champions are, the path to someone we haven't met, what changed in their org, and where we are exposed.
7. A pre-call brief generated from person cards; a QBR exported as .pptx with visibility exclusions verified by test; the champion kit and expansion business case generated.
8. Plays fired and resolved with effectiveness notes; the scheduled team update produced as a draft.
9. CONNECTIONS.md accurately describing every switch still in mock.
10. The 30-second capture rule still holds everywhere; trust-boundary tests pass, extended to cover the new ingestion paths and generators.
