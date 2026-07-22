# Account OS: Scoping Document
### Custom tooling for managing F100 deployments and expansions at Valence
*Zach McCall · July 2026 · v3.2 (final) · SCOPE FROZEN — next action is Stage 0, defined by its completion test in Section 9*

> v3.1 resolves the contradictions and operational-behavior gaps from the second engineering review. Per that review's own conclusion and the author's: the conceptual model now stops expanding. Remaining uncertainty gets resolved by the first weeks inside Valence, not more desk scoping.

---

## 0. Background (read this first if you're new to the context)

**Who and what this is for.** The author is an Engagement Manager at Valence, a company that sells Nadia, an AI coaching product, to Fortune 100/500 enterprises. The job: take a small number of very large accounts (enterprise clients on the order of tens of thousands of employees), run product rollouts inside them, prove measurable value, grow the paid contract, and own the renewal. The commercial motion often involves expanding from an initial paid population into materially larger ones; AGCO, for example, contemplated growth from roughly 1,000 to 3,000 licenses. Each account is a multi-month program involving many named people on the client side (HR executives, program owners, IT, legal), rollout plans, usage metrics, a business case, and a commercial close.

**The problem.** All of that state currently lives across call transcripts, slide decks, spreadsheets, Slack, and memory. There is no single place that answers: where does this account stand, who matters, what did we commit to, what's at risk, and what has to happen next. Existing CS platforms are built for teams running hundreds of accounts; this is one operator running a few very deep ones.

**What the tool is.** An internal, single-editor web app: an execution ledger (interactions, commitments, decisions, risks) on top of a structured model of accounts, programs, people, and metrics, with a file/context library, generators for recurring outputs (QBR skeletons, weekly team updates), visualizations, and, last, AI-assisted capture.

**Domain terms** (glossary in Appendix A): a *QBR* is the quarterly business review with the client; a *champion* is the client executive sponsoring the deal; the *budget owner* funds an expansion; a *deployment moment* is a recurring client event the product embeds into; a *play* is a predefined response to a trigger; a *pull signal* is unprompted client demand.

---

## 1. Purpose and design principles

One canonical system Zach lives in daily that can brief the team in minutes. Built from scratch (Python backend, JavaScript frontend). The prototype does not depend on purchasing a third-party customer-success platform; in production, Account OS complements rather than replaces Valence's canonical CRM, analytics, and document systems.

**Single-editor, not single-user.** Zach is the only direct operator in the initial version. Other Valence team members receive deliberately generated outputs (team updates, QBR materials), not access to the underlying workspace. Production authorization and record-level visibility must be revisited before any direct read access is added.

**Design principles**
1. **The 30-second rule wins every tie.** Updatable in under 30 seconds when something moves. Any object, field, or classification that threatens capture speed gets cut or demoted to a tag. Where structure and speed conflict, the Capture Inbox (Section 3) absorbs the conflict.
2. Encode the playbook we already believe in: adoption drives usage, expansion converts it to paid seats.
3. Every module answers a question actually asked before a call, a QBR, or an internal update.
4. Prompt action, not just display data. Signals fire plays, and every signal explains itself.
5. **Source-agnostic inputs, explicit source authority.** Ingestion paths are swappable adapters (manual entry always available, CSV import default, API when one exists); every synced field knows which external system is canonical for it (Section 3).
6. **Ledger before visuals.** The boring operational records come before the charts, because they are what makes the tool trustworthy in a difficult renewal.
7. **Honest about freshness.** Stale data is never presented as current. Metric-derived indicators automatically become unknown when their inputs pass the stale threshold. Manually assessed delivery and commercial statuses remain visible, but the interface warns when the assessment is older than the reassessment interval (30 days initially) or its supporting evidence is stale.

**How it's used: four concrete scenarios**

*Morning check (daily, 2 minutes).* Open the portfolio home. See a renewal window opening in 100 days on one account, a stakeholder untouched for three weeks on another, a play fired overnight, and two untriaged notes from yesterday's calls. Act, triage, or snooze each.

*Pre-call prep (5 minutes).* Open the program, glance at the overview, check who's on the call and what they care about, scan open commitments involving them, search for the last transcript where they spoke.

*Post-call capture (1 minute).* Quick-entry logs the interaction: who attended, rough notes on what moved. Classify what's obvious; leave the rest untriaged for later. Optionally paste the transcript afterward and approve AI-extracted updates (v4).

*QBR prep (quarterly).* Hit generate. Get a skeleton with metrics vs. targets, risk status, approved value stories, and open commitments pre-filled, stamped with what data it reflects and as of when, with internal-only records excluded by construction.

---

## 2. Trust boundaries (non-negotiable)

These come first because getting them wrong would put the tool in conflict with what Valence sells.

**Individual coaching usage is off-limits.** Valence's public commitment is that individual coaching interactions are confidential and organizations receive aggregated, anonymized reporting. This tool must never become a shadow capability for seeing whether a named person is privately using the coach. Therefore:
- The tool tracks **champion engagement with the deployment** (attends meetings, sends comms, advocates internally, responds to asks), which is observable relationship data.
- It stores **aggregate cohort usage** only, as supplied by the Valence Data team.
- It has **no field anywhere for a named individual's product usage.** This is a schema-level prohibition, not a policy note.
- The QBR generator ingests only Valence-approved aggregate insights. It never derives themes from coaching content itself.
- As Nadia becomes more proactive and context-aware (calendar, meeting, and team signals), Account OS tracks **which capabilities are enabled for a deployment** but never ingests the underlying private context.

**Stakeholder assessments are personal data.** Tags like supporter/skeptic, influence, and relationship strength describe identifiable people. They exist for a defined business purpose, access is limited to the operator, they are written as professional judgments with an evidence note and a date, and they fall under the same retention and hosting rules as everything else (Section 7).

**Internal vs. client-visible, by safe default.** Object types carry default visibility rules: raw notes, stakeholder judgments, commercial strategy, incumbent-vendor notes, negotiation positions, and AI-generated interpretations default to internal only. Records inherit their type's default unless explicitly promoted (client working materials / approved for QBR-executive presentation / externally referenceable). Client-facing generators include only records affirmatively classified for the intended audience, by construction, not by operator vigilance. No per-note classification decision is ever required at capture time.

**No real client data before hosting approval.** Mock data until the production environment is cleared (Section 7).

---

## 3. Data ingestion & capture flow

Three paths, all landing in the same normalized model:

**A. Post-call quick entry, with progressive structuring.** One form, under a minute, creating an Interaction record: program, participants, rough notes. Quick entry does not require every item to be classified perfectly: ambiguous notes enter a **Capture Inbox** attached to the interaction and are converted later into commitments, decisions, risks, issues, opportunities, or value stories without retyping. Untriaged items stay visible in the attention queue until resolved. Last-touch dates derive from interactions automatically; they are never hand-edited.

**B. AI-assisted transcript ingestion (v4).** Paste or upload a transcript; the system proposes structured updates for approval. Security model, since uploaded documents are untrusted input:
- Runs through an approved model and approved data-processing path. The extraction process has no browsing, external connectors, arbitrary tool permissions, or outbound access beyond the specifically approved model endpoint and required internal services.
- Output is a strict validated JSON schema of predefined mutation types only; nothing writes without per-item human acceptance.
- Every proposed fact carries a source span; model and prompt versions are recorded in the audit log.
- Document content is treated as data, never as instructions.

**C. Structured import / API adapters.** Every adapter implements one contract: validate, preview with field mapping, flag duplicates, run idempotently, record the import batch, allow rollback, and report source freshness.

**Data freshness is an interface behavior, not metadata.** Every synced module shows current-through date, expected refresh cadence, and last successful import. Data past its stale threshold renders any dependent status as **unknown** (not carried-forward green), and stale or failed sources create attention-queue items.

**Source authority matrix.** Working assignment, to confirm on the job:

| Data | Canonical system | Account OS stores |
|---|---|---|
| Contract value, official renewal date, opportunity records | CRM / RevOps | Synced copy + link, read-only locally |
| Usage metrics, metric definitions | Valence Data team | Synced observations + definition version, read-only locally |
| Original transcripts and client files | Approved document system | Link + summary by default (Section 7) |
| Execution state: interactions, commitments, decisions, risks, plays, relationship judgments | **Account OS** | Native, editable |

Each synced field carries: source system, source identifier, import timestamp, and an editable-locally flag. The tool must not quietly become a competing CRM.

**Operational overlay on canonical data.** Canonical fields are never overwritten locally. Where execution requires a different forecast or interpretation, Account OS stores a clearly labeled operational overlay alongside the canonical value, with rationale, author, and assessment date. Example: CRM renewal date December 31; Account OS expected decision date October 15; explanation, procurement requires ten weeks. Applies especially to renewal timing, projected seats, likely contract value, opportunity stage, and procurement timelines.

**Open unknowns for the first weeks on the job:** where usage analytics live and their format, the Data team's canonical metric definitions, which CRM/RevOps systems hold contract data, and export permissions for each.

---

## 4. Core object model

Organized in layers, deliberately at half the dosage a program office would use; principle 1 wins ties.

### Organization layer
- **Account**: the enterprise relationship. Name, key dates, incumbent vendors (who holds coaching/L&D budget today, contract timing, displacement status), and **two statuses, not one**: a *delivery/value status* and a *commercial status*, each manually judged with a rationale, date assessed, and the condition that would change it. One flag conceals the most common real story: excellent adoption, weak expansion economics (or the reverse).
- **Program**: the primary operating object; a bounded deployment or commercial motion. Phase lives here (Foundation / Launch / Programmatic / Expansion / Renewal / Closed), because an F100 account will genuinely be in several states at once. Region, audience, and use case are attributes, not hierarchy levels. Each program carries: problem statement, in-scope and out-of-scope population, launch definition, success criteria, expansion hypothesis, explicit exclusions, sponsor, governance cadence (steering forum, working rhythm, QBR dates). Scope changes get a lightweight **scope-change entry**: what changed, who agreed, date, source interaction. No full change-request module.
- **Phase gates**: configurable checklists of what must be true to advance, seeded per program and editable. A gate passes when items are complete or an authorized person explicitly waives them, with waiver reason recorded.

### Relationship layer
- **Person** and **stakeholder role per program** (champion, budget owner, program owner, IT, legal/DPO, works council contact). Stance (supporter/skeptic/unconverted) with date and evidence note; what they care about and what the product does for them specifically. Relationship edges: reports to, sponsors, influences, owns program X.
- **Interaction**: the foundational record. Date, type, participants, program, summary, links to records created from it, source artifact link, follow-up, meaningful-touch flag. The chronological account history is a first-class output.

### Execution layer
- **Milestone**, **task**, **commitment**, **decision**, **issue**, **risk**. Assumptions and dependencies are tags, not objects.
- **Commitments carry two owners**: the *responsible party* (who performs it, often the client) and the *internal owner* (the Valence person accountable for driving it). This prevents client-owned actions from quietly disappearing. No full RACI.
- **Definitions of done** are objective: a task is complete when its deliverable exists; a commitment closes when the receiving party acknowledges completion; a milestone completes when its success criteria are met; a risk closes when no longer possible or relevant, not when mitigation begins; an issue resolves when the condition is removed or an accepted workaround is operating. Closures record date, closer, and a short note.
- **Deployment moments** (generalizing talent-calendar moments): recurring client events the product embeds into. Types include talent-calendar events (reviews, calibrations, survey action planning), recurring manager workflows, business events, and proactive-coaching or comms campaigns. Each carries client-side owner, comms hook, integration status, outcome. Light comms entries (audience, message, sender, channel, date, status) hang off moments and programs.

### Commercial layer
- **Contract version**: seats, price, dates, renewal mechanics, amendments; versioned, never overwritten.
- **Renewal motion** per contract: notice period, procurement lead time, renewal-prep play firing 90-120 days out.
- **Expansion opportunity**: several per account. Named audience or use case, target seats, expected value, sponsor, budget owner, funding source, supporting evidence, decision date, stage, blockers, next action. Budget is a staged state: conceptually supported → in planning → formally allocated → requisition created → procurement approved → executed. **Closed opportunities require an outcome (won / lost / deferred / merged / no decision) and a reason.**

### Measurement layer
- **Metric definition** (name, meaning, source system, owner, version, population; formula details as optional notes) and **metric observation** (definition version, program/cohort, period, value, source, import batch). Definitions come from the Data team; the tool ingests, it does not recompute.
- **No hard-coded benchmarks.** Valence's own materials describe Delta's 75% differently across pieces, and the ADI power-user outcome appears as both 28% and 31%. Benchmarks are versioned, sourced claims with population and period attached.
- **Value story**: outcome, tags, evidence tier (anecdote / client quote / measured operational outcome / correlated business outcome), visibility class, identifiable-vs-anonymized. **The library also captures negative evidence**: objections, sponsor reservations, adoption friction, failed interventions, declined populations, value claims the client did not accept. Without it, generated QBRs develop optimism bias.
- **Source reference**: reusable pointer (file, transcript span, meeting, CRM record, Data report, manual entry). Required on client-facing factual claims, metrics, commitments, decisions, and attributed value stories. Recommendations and proposed future actions are clearly labeled as such rather than presented as sourced facts; the audit log covers everything else.

### Intelligence layer
- **Play definition and play run**. A play run records trigger, actions generated, completion, and (from v4) a light effectiveness note: outcome and an operator assessment of effective / unclear / ineffective, so the playbook improves rather than just automating. **Capture-inbox item**, **import batch**, **job**, **audit event** (Section 7).

### Lifecycle
- Programs and accounts close: renewal completed or lost, lessons learned, open commitments at handoff, retained records and deletion date, successor brief.

---

## 5. Modules

**A. Portfolio home (the morning screen, ships in v0).** Cross-account attention queue. **Ranking is rules-based and explainable, not an opaque score.** Deterministic sources, in priority order: overdue client commitments, active blockers, renewal/notice windows, failed or stale imports, fired plays, at-risk upcoming milestones, untriaged inbox items, stale stakeholder relationships, open tasks. Every item states why it appeared, its age, due date, and next action. **Snoozing requires a return date or resurfacing condition; resolving requires closure or a linked successor action.** Snooze must never become a way to permanently hide risk.

**B. Account & program overview.** Account header (delivery status, commercial status, renewal countdown, incumbent status) above the program list, each with phase, gate status, next milestone, top risk.

**C. Stakeholder map** (per account, program-filterable), per Section 6; sidebar coverage measure (active VP+ relationships, days since last derived touch, second owner for the business case).

**D. History / interaction timeline.** The chronological ledger, filterable by person or program.

**E. Execution board.** Open tasks, commitments (with both owners), issues, gate checklists, and the capture inbox triage view.

**F. Timeline.** Swimlane view, program-scoped, deployment moments plotted, extended through renewal.

**G. Metrics scoreboard.** Observations vs. targets vs. baselines by definition version, with freshness stamps; stale = unknown.

**H. Commercial view.** Expansion opportunities with stages, staged budget states, and closed-outcome reasons; contract versions; funding waterfall.

**I. Risk register & play queue.**

**J. Value & story library** with evidence tiers, visibility classes, and negative evidence; feeds the QBR and champion enablement kit.

**K. QBR generator.** Assembles from live data. Output stamped: generated at, data current through, missing or stale sources; content typed as confirmed fact / internal interpretation / open hypothesis / recommended action; internal-only records excluded by construction. Logs new commitments on save.

**L. Team update export.** One-click weekly internal status; same stamping rules.

**M. Compliance & readiness checklist.** Per-region and per-program lanes: IT security, legal/DPO, works council, channel and integration setup (Teams, web, Slack, mobile, deeper M365 integrations; track which apply per deployment), localization QA, trust comms, HR-boundary definition.

**N. Mutual action plan.** Client-facing joint plan; visibility rules apply.

**O. Files & context library.** Link-first, tagged, searchable.

**P. Operations screen (minimal).** Failed jobs, failed imports, backup status and last restore test, storage usage, search-index health. A single-editor tool still needs to say when it is broken without reading server logs.

---

## 6. Design direction (research-backed)

### 6a. Overall look and feel

The reference class is the modern power-user tool (Linear, Stripe's admin, Superhuman), not a marketing site and not a generic admin template.

**App shell.** Persistent left sidebar: accounts and programs, plus global views. Compact top bar with global search. Detail views open as slide-over panels so context is never lost. Elements central to the task stay in focus while chrome recedes.

**Density with hierarchy.** Compress whitespace with discipline; compact rows by default; generous spacing only where a screen has one job.

**Interaction feel.** Keyboard-first with a command palette (cmd-K). Auto-save with non-blocking toasts; no blocking modals for routine actions; actions live in context. **Routine navigation and record edits feel immediate. Long-running work (extraction, imports, AI processing, QBR generation) runs as jobs with visible progress or a durable queued state, lets the operator keep working, and ends in an actionable success or failure notification.**

**Visual system.** One quiet neutral surface with a single accent for interactive elements. **Semantic status colors (green/amber/red) are reserved for status, with one documented exception: financial charts use the standard green-additions/red-subtractions convention, and status indicators never appear on the same screen as a financial chart.** Utility face with tabular figures for data; a restrained characterful face for headers only. The signature element is the stakeholder graph; everything else stays disciplined. Avoid the AI-default looks (cream plus terracotta serif, black plus acid green, faux-broadsheet). The aesthetic reads as a purpose-built instrument: Bloomberg-for-accounts.

**Copy.** Plain verbs, sentence case, buttons say what they do. Empty states invite action; errors say what happened and how to fix it.

**Quality floor.** 4.5:1 contrast, visible keyboard focus, state never conveyed by color alone, reduced motion respected, readable split-screened next to a call. One color mode done well.

### 6b. Per-module direction

**Stakeholder map.** Network diagram with deliberate encodings: node size = influence, node color = stance, edge thickness = relationship strength, arrowheads = direction of influence. Layout anchored on the reporting hierarchy with influence/sponsorship edges overlaid in a second style; no force-directed hairballs. Click opens a detail sidebar. Toggle view: power-interest grid.

**Timeline.** Swimlanes mapped to workstreams; limited palette, color for status and key milestones only; milestones as diamonds; today marker; two timescales (weeks for the 90-day window, months to renewal).

**Budget waterfall.** Anchored start and end bars, floating intermediate changes; green additions, red subtractions, gray/blue totals (the documented exception above); limited steps, minor sources grouped with subtotals; every bar labeled; no truncated axis; ordered by narrative: current contract → recovered vendor spend → increments → expansion total.

**Metrics scoreboard.** Five-second rule; 5-9 metrics max, most important top-left, inverted pyramid. Each card: number, target, delta, sparkline, freshness stamp. Bullet charts over gauges. Bold color for state only; stale renders as unknown.

**Portfolio home.** A ranked, explainable queue, not a wall of charts.

*Sources: DronaHQ and Eleken on internal-tool UX; Linear's redesign notes on density and receding chrome; Paul Wallas on data density; Simply Stakeholders and Mural on network encoding; Lucen and Page Flows on Gantt/swimlanes; Jaspersoft, monday.com, and Sigma on waterfall conventions; Yellowfin, Domo, and CleanChart on the five-second rule and bullet charts.*

---

## 7. Security, data handling & operations

**Two modes, explicitly.**
- *Mock/local mode:* local authentication, synthetic data only, SQLite, local files.
- *Production mode (prerequisites):* approved Valence identity (SSO/MFA), approved hosting, encrypted transport and storage, access logging, retention controls, database per Valence's approved managed pattern (likely Postgres). Valence's certifications cover Nadia, not a separately built tool; this app must live inside the approved environment.

**Link-first file strategy.** Default: link and metadata to the approved original location plus a written summary or limited excerpt; copy complete files only when necessary and approved. Where files are stored: allowlisted formats, size limits, content hashing, storage outside the served directory, extraction status, secure deletion. Malware sandboxing deferred while single-uploader (Section 11).

**Deletion and archival.** Archive by default; soft-delete with actor and timestamp where deletion is needed; restoration possible; permanent purge only per retention policy. Imported observations are superseded, not deleted. Recoverable during normal operation, permanently deletable when retention demands.

**Jobs.** Extraction, imports, AI processing, and exports run through a persistent job table (queued/processing/succeeded/failed, retries, timestamps, input/output refs) with a single in-process worker.

**Append-only audit log.** Every material change: actor, timestamp, object, before/after, source (user action vs. import batch vs. AI proposal), human approval where applicable.

**Migrations and exportability.** All schema changes use versioned migrations; a dev reset/seed command exists; native data exports in documented structured formats independent of the UI, and a full account (or full system) can be exported and restored into a clean installation. The tool never traps its own information.

**Backups with recovery requirements.** RPO 24 hours initially; defined RTO; encrypted, access-controlled location; database and file store consistent; deletion propagates; periodic restore test.

**Dates and timezones.** Timestamps stored in UTC, displayed in the operator's timezone; client/event timezones preserved for meetings and deployment moments; all-day dates distinguished from timestamps; recurring moments supported; renewal and notice dates treated as contractual dates, not converted timestamps; due dates specify end-of-day.

---

## 8. Architecture

- **Backend:** Python, FastAPI. SQLite in mock/local mode; production database per approved Valence pattern.
- **Frontend:** React. Cytoscape.js for the graph, Recharts for charts.
- **Search:** SQLite FTS5 over native records and stored summaries in local mode; production search follows the production stack.
- **Ingestion:** adapter pattern with the common import contract.
- Single editor; team consumption via generated outputs.

**Scale expectations (do not over-engineer):** 3-8 accounts, a few programs each, 20-40 people per account, hundreds of files, a few thousand rows. No caching layer, no microservices. Routine operations instant; long-running work through the job table.

---

## 9. Build order

Ledger before visuals; AI last, after enough manual capture to know the extraction schema from experience.

**Stage 0 (paper, before code) — the next action.** Deliverables, not discussion: an entity diagram (objects and relationships); a field dictionary covering only v0 fields; a state-transition table (valid statuses and closure rules); an attention-rule table (trigger, priority, resolution, resurfacing); three mock accounts, at least one multi-program; the four scenario walkthroughs run on paper; rough v0 wireframes; and a concrete end-to-end acceptance script. **Stage 0 is complete when a mock call can be captured, converted into a commitment and a risk, surfaced in the attention queue, reflected in the account history, and included correctly in a generated team update, without introducing any new object type.**

**v0, the execution ledger:** accounts and programs (with both statuses), interactions, capture inbox with triage, stakeholders (stance + evidence), tasks/commitments (both owners)/decisions, risks and issues, milestones, source links, portfolio attention queue with ranking/snooze/resolve rules, post-call quick entry, team update export. Built in four internal slices, each usable before the next begins: **v0.1 capture** (accounts, programs, people, interactions, inbox) → **v0.2 execution** (tasks, commitments, decisions, risks/issues, milestones) → **v0.3 attention** (queue rules, snooze/resolution, account statuses) → **v0.4 output** (history view, weekly team update). This prevents twelve half-built tables existing before any workflow works end to end.

**v1, commercial and deployment control:** expansion opportunities (with closed outcomes), contract versions and renewal motion, phase gates, compliance/readiness checklist, deployment moments, timeline view, governance cadence, scope-change entries.

**v2, data and evidence:** metric definitions and observations, import adapters with preview/dedupe/rollback, freshness behavior (stale = unknown), value-story library with tiers, visibility classes, and negative evidence, QBR generator with stamping and visibility exclusion, provenance on client-facing claims, operations screen.

**v3, visualization:** stakeholder graph and power-interest toggle, budget waterfall, richer metric views.

**v4, AI and automation:** transcript extraction under the Section 3 security model, plays/trigger engine with effectiveness notes, notifications, briefing assistance.

---

## 10. Success criteria for the tool itself

After 60 days of real use:
- Median post-call capture under two minutes; at least 90% of meaningful interactions captured within one business day.
- Fewer than five untriaged inbox items older than three business days.
- Weekly team update generated and corrected in under five minutes.
- 100% of open commitments have a responsible party, an internal owner, and a due date; none hidden from the morning queue; every client-owned commitment has a Valence follow-up owner.
- No client-facing output contains an internal-only record; client-facing claims link to evidence; stale data is never presented as on-track.
- Every attention-queue item explains why it is present and how it resolves.
- Renewal readiness visible at least 120 days out.
- A restore test has passed; an account can be exported and restored without manual database surgery; no material job, import, or backup failure is discoverable only through server logs.
- No real client data outside approved infrastructure.
- At least ~80% of captured fields still actively used; anything below gets cut, not defended.

---

## 11. Out of scope, and review items declined with reasons

**Standing out of scope:** composite health score (two manual statuses with rationale replace it); email/comms sync; a separate CRM layer; client-facing logins.

**Declined or trimmed from review rounds, with reasons:**
- *Assumptions, dependencies, change requests as first-class objects.* Tags on risks and notes; the lightweight scope-change entry covers scope drift. Full classification ceremony kills the capture habit.
- *The full 15-field metric definition schema.* Core fields adopted; the rest as optional notes until a real dispute demands them.
- *Provenance on every field.* Client-facing claims only; the audit log covers the rest.
- *Malware sandboxing, MIME-spoofing defense.* Deferred while the operator is the only uploader and link-first is the default; mandatory revisit if the tool goes team-wide.
- *Six-level organizational hierarchy.* Account → Program with attributes.
- *Standalone change-management module.* Light comms entries on programs and moments.
- *Full field lists from review round two (nine-field queue items, twelve-field program scope, full approver workflow).* Adopted at roughly half dosage; the concepts survive, the ceremony doesn't.

The rule applied throughout: reviewers' concepts at half the reviewers' dosage, with the 30-second rule breaking ties. **The conceptual model is now frozen.** New objects require retiring an existing one or evidence from real use.

---

## 12. Open decisions (the five that gate production architecture)

1. Can the app store complete transcripts, or only references, summaries, and approved extracts?
2. Which systems are canonical for CRM, usage metrics, contracts, and client documents?
3. May AI processing call an external LLM, or must it use an approved Valence service or environment?
4. What is the approved internal stack: identity, hosting, database, storage, logging, backups?
5. Does this remain a personal tool, or is there a credible path to other Engagement Managers using it?

None block Stage 0 or v0 on mock data. All must be answered before production architecture decisions that are expensive to reverse.

---

## Appendix A: glossary

- **Nadia** — Valence's AI coaching product, delivered through channels appropriate to the client environment: Microsoft Teams, web, Slack, and mobile, with integrations varying by deployment.
- **Seat / license** — one paid employee's access; the commercial unit.
- **Activation / weekly return** — usage metrics; exact definitions ingested from the Valence Data team, never assumed.
- **Power user** — a user meeting Valence's current Data-team definition across consistency, breadth, and depth of engagement; versioned and ingested, not recalculated here.
- **Champion / budget owner** — client executive sponsoring the deal / named person who funds an expansion.
- **Multithread** — deliberately building multiple senior client relationships.
- **QBR** — quarterly business review. **MAP** — mutual action plan, jointly owned and client-visible.
- **Deployment moment** — recurring client event the product embeds into: talent-calendar events (reviews, calibrations, survey action planning), manager workflows, business events, proactive-coaching or comms campaigns.
- **Pull signal** — unprompted client demand. **Play** — predefined trigger-and-response with owner and due date.
- **Capture inbox** — holding area for untriaged post-call notes, converted into structured records later.
- **Works council** — an employee representative body present in certain jurisdictions and companies that may have consultation, information, or co-determination rights affecting workplace-technology deployments. Betriebsrat is the German term.
- **Incumbent displacement** — replacing a vendor the client already pays, freeing budget.

## Appendix B: source notes

- Business metric of record, revenue-per-employee framing, mixed pilot design, push-to-pull adoption, IT/legal on every deal, HR boundary definition: Sugrue & Goertz, NYU Coaching and Tech Summit, July 2026 (valence.co).
- Leader-modeling effects, invitation over mandate, workflow embedding, deployment-moment patterns, anonymized-theme insights: Valence adoption materials and 2026 Summit sessions (ADI, VML, WPP, Delta, Costa). Talent-calendar integration is a recurring pattern across Valence guidance and customer examples.
- Privacy posture (aggregated, anonymized reporting; individual conversations confidential; growing proactive/contextual capabilities): Valence trust, security, and product materials.
- MAPs, commitment-logging QBRs, trigger plays, renewal timing: enterprise CS practice (Aviso, RevOS, Planhat, Lyniro).
- Benchmark caution: Valence materials describe Delta's 75% inconsistently, and the ADI power-user outcome appears as both 28% and 31%; benchmarks stored versioned and sourced.
- Two-layer adoption/expansion architecture and risk deep-dives: our AGCO deck and briefs.
