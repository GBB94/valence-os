# Valence OS — Internal Operating Layer Spec
### Forecasts, internal reviews, asks, coordination, and upward reporting

*Zach McCall · July 2026 · v2 · Codebase-aware successor to the original Internal Ops addendum*

---

## 0. Purpose, authority, and outcome

Valence OS already runs the client-facing half of a deep enterprise account: execution, relationships, evidence, expansion, renewal, and generated client artifacts. This module adds the internal operating layer required to run the same accounts inside Valence: the forecast Zach stands behind, the asks and escalations that unblock it, the account reviews leadership runs, the colleagues who share coverage, the product feedback that must make a round trip, and the reporting rhythm that makes a five-account book legible upward.

The product principle is unchanged from v1:

> **Internal commitments receive the same ledger treatment as client commitments.**

This document is an additive scope authority alongside `PHASE-3-SPEC.md` and `EXPANSION-ENGINE-SPEC.md`. It does not weaken either document's trust boundaries, counting rules, evidence rules, or source-authority decisions. Where this document changes existing information architecture or generalizes an existing record, it says so explicitly.

The intended outcome is operational, not decorative: from live mock data, Zach can defend the forecast, walk into an internal review already prepared for the hard questions, see internal dependencies before they become misses, hand temporary coverage to a colleague, and produce leadership-ready reporting without rebuilding the truth in slides or Slack.

### 0.1 Success statement

The module is complete when the mock five-account portfolio can demonstrate, end to end:

1. a weekly forecast submission with period-scoped categories, evidence gaps, movement since the prior submission, and leadership help needed;
2. a one-page account brief and full review packet generated from live records plus one dated operator point of view;
3. a monthly portfolio brief whose red claims all trace to records already in the system;
4. a two-week coverage brief that a colleague can operate from;
5. an overdue leadership commitment and an aging internal ask surfacing correctly in Today;
6. a complete escalation chain with no automatic outbound communication;
7. one product need aggregated across at least two accounts and closed back to both requesters; and
8. forecast calibration rendered after two closed mock periods without a composite score or blended currencies.

### 0.2 Non-goals

This scope does **not** add:

- multi-user accounts, permissions, approvals, or colleague logins;
- automatic email, Slack, calendar, CRM, or product-system writes;
- a second task or commitment system;
- stage-derived forecast probabilities or an opaque confidence score;
- currency conversion, blended cross-currency totals, or invented recurring-revenue semantics;
- AI-authored account judgment presented as operator judgment;
- a new top-level navigation destination; or
- real client, employee, or product data.

The single-editor rule remains: colleagues and leadership receive generated outputs; they do not log in.

---

## 1. Standing rules and invariants

### 1.1 Trust and data boundaries

All existing standing rules remain binding:

- mock/synthetic data only until the applicable `CONNECTIONS.md` approval exists;
- no named individual's Nadia usage anywhere in schema, code, fixtures, or output;
- no sensitive personal data; internal-person notes remain professional and work-related;
- client-facing artifacts select only affirmatively promoted, sourced records by construction;
- internal artifacts may include internal records, but each artifact is stamped `audience=internal` and is never auto-sent;
- canonical CRM and contract facts remain read-only locally; operational forecast calls are labeled, dated overlays rather than edits to canonical records;
- every material mutation is audited; operational records soft-delete; event and transition logs are append-only;
- contractual dates are dates, scheduled execution times are UTC timestamps; and
- stale or missing data renders unknown or missing, never silently good.

### 1.2 Financial honesty

Every forecast amount carries:

- currency;
- revenue basis (`annual_recurring`, `term_total`, or `one_time`);
- source or rationale;
- author; and
- assessment date.

The rollup groups by currency and basis. It never sums unlike bases, converts currencies, or uses `expansion_opportunities.expected_value` as a defensible forecast amount: that legacy field is an untyped illustrative number. Where an amount can be derived from a current contract or a priced growth-plan line with compatible units, the derived source is named. Otherwise the operator supplies a dated forecast assertion.

Weighted pipeline uses an explicit, dated probability on the forecast entry. There is no stage-to-probability table. Entries without a probability remain visibly excluded from the weighted subtotal rather than receiving a default.

### 1.3 Status honesty

Delivery/value and commercial status remain independent and no composite account-health score is introduced. This scope makes the status history and response discipline explicit:

- each assessment is an append-only event with rationale and criteria version;
- amber (`at_risk`) requires a recovery owner, action, and due date;
- red (`off_track`) requires the same plus either a linked leadership decision ask or a documented reason leadership action is not applicable;
- the current columns on `accounts` remain a compatibility projection, updated transactionally from the latest assessment; and
- every report uses assessment events, not an unaudited mutable value.

### 1.4 No-surprises invariant

A generated internal report may contain a red-treated claim only when that claim carries an origin reference to at least one pre-existing record:

- an open risk or issue;
- an active attention item;
- an `off_track` status assessment event;
- a severe escalation event; or
- a declined or overdue internal ask whose policy maps it to red treatment.

The rule runs both ways: report-eligible red origins must appear in the relevant report unless the generator records a typed exclusion and reason.

Generation is deterministic:

- preview returns `generation_blockers[]` with the offending claim and accepted origin types;
- saving a draft returns HTTP `409` while blockers exist;
- the UI offers links to create or open the missing record; and
- the generator never silently creates a risk, changes a status, or downgrades a red claim to make itself pass.

### 1.5 Scope integrity

Every account-scoped relationship is checked at the API and database layers. A forecast, ask, roster row, feedback occurrence, review, or commitment may not link records from another account. Every new account-scoped table is added in the same stage to:

- account export/restore and its registry guard;
- global search;
- source-reference lookup where applicable;
- Operations health/record counts;
- audit coverage; and
- mock seed teardown/reset behavior.

Operational links do not use unchecked `linked_type` + `linked_id` pairs. Load-bearing relationships use real nullable foreign-key columns with XOR/at-least-one checks, or a join table whose allowed targets are explicit foreign-key columns. Where a generic typed reference is unavoidable for a frozen provenance manifest, the type is allow-listed, existence is verified at generation time, and the reference is immutable afterward.

---

## 2. Reconciliation with the current codebase

This is an extension, not a greenfield subsystem.

| Existing primitive | Reuse in this scope | Required change |
|---|---|---|
| `expansion_opportunities` + five-slot qualification | forecast evidence for expansion | no timeless category column; forecast calls live per period |
| current `contract_versions` + renewal center | renewal facts and timing | forecast entry provides the operational renewal call without mutating canonical contract data |
| funding pools, ask calendars, growth-plan lines | budget, decision process, priced expansion evidence | evidence checker reports missing or stale links |
| `commitments`, `decisions`, Ledger, and Today | internal review commitments and decisions | allow account-level context and record internal direction/review provenance |
| `persons.affiliation='valence'` | internal owners, requesters, roster members | roster joins existing Valence people; no parallel employee table |
| interaction participants | contribution and executive-touch history | capture UI includes active roster members as participants |
| `attention_state` and derived queue | ask aging, overdue leadership commitments, feedback follow-up | add derived trigger families; do not persist duplicate queue objects |
| `generated_documents` draft → reviewed → sent/discarded | every internal artifact | widen document kinds and preserve frozen source manifests |
| jobs and scheduled weekly generation | forecast/report schedules | new handlers create drafts only; never transmit |
| `exec_pairings` and cadence analytics | executive coverage | portfolio view composes existing derived touch facts |
| audit log | status trajectory and material history | purpose-built event tables are added only where the current snapshot is insufficient for period math or chain reconstruction |
| Accounts destination and seven-tab workspace | portfolio and account internal views | Accounts gains a `Book / Internal` segment; account workspace gains an eighth `Internal` tab |

### 2.1 Intentional departures from v1

These changes make the original scope implementable without changing its goals:

1. **Forecast category is period-scoped.** A single category column on an opportunity cannot honestly describe what was called in two different quarters. The current call lives on a forecast entry for one period; its transitions are appended to a change log.
2. **Renewal is not forced into an expansion-opportunity record.** A forecast entry targets either an opportunity or a current contract version, exactly one. Contract truth remains canonical and read-only.
3. **Review commitments generalize the existing ledger.** They do not create an `internal_tasks` island. Commitments and decisions gain account-level context and explicit review provenance.
4. **Product feedback separates theme from occurrence.** One portfolio feedback item can have several sourced account occurrences. Aggregation is therefore relational and explainable, not fuzzy matching over Slack-like text.
5. **Escalation is a policy-driven state of an ask.** The ask remains the work record; escalation instances and events capture severity and chain without duplicating the request.
6. **Status history becomes first-class.** Audit remains the forensic log, but reporting and trajectory should not parse generic before/after JSON to understand governance state.

---

## 3. Forecast layer

### 3.1 Periods and entries

A **forecast period** defines the interval leadership is asking about. It carries a name, start/end dates, submission cadence, timezone, and status (`draft`, `open`, `locked`, `closed`). Periods may not overlap within the same cadence unless explicitly marked as a different scenario type.

A **forecast entry** belongs to one period and one account, and targets exactly one of:

- an expansion opportunity; or
- a current contract version representing the renewal motion.

Its category is one of:

- `commit` — Zach is stating it will close in the period;
- `best_case` — it can close if named conditions resolve;
- `pipeline` — real motion, not ready for the call;
- `omitted` — deliberately excluded, with a required reason.

Category remains independent of commercial stage, budget state, qualification completeness, and growth-plan status.

Each entry also records forecast amount, currency, revenue basis, optional probability, amount/probability rationale, author, assessment date, expected decision date, and operator help-needed note. Source links point to the target, priced line/contract evidence, and any interaction supporting the call.

`forecast_entry_sources` uses explicit nullable foreign keys for the supported evidence families (interaction, source reference, growth-plan line, revenue event, and ask calendar), with exactly one populated per row and database-enforced account scope. It is not a free-form polymorphic link table.

### 3.2 Evidence rules

Evidence rules are soft: they never block the operator from choosing a category. They return named gaps and make unsupported calls visually risky.

**Expansion Commit requires:**

1. `budget_state` at `formally_allocated` or beyond;
2. a named budget owner belonging to the same account;
3. a meaningful interaction containing that budget owner within the prior 30 days;
4. a linked ask calendar with a target or required step inside the forecast period; and
5. a defensible amount with currency and basis.

**Renewal Commit requires:**

1. a current contract version with renewal or operational expected-decision date in the period;
2. a named renewal budget owner on the forecast entry;
3. engagement with that owner within the prior 30 days;
4. a sourced renewal-position assertion (`confirmed_intent`, `commercial_review`, or `procurement_in_progress`); and
5. a defensible amount with currency and basis.

The renewal-position assertion is an operational forecast fact on the entry, not a canonical contract edit.

**Best Case requires:**

- expansion: at least three of the existing five qualification slots complete;
- renewal: at least three of the five renewal evidence elements above complete; and
- both target types: every unresolved condition is named.

Pipeline has no completeness threshold. Omitted requires `omitted_reason` and is excluded from totals.

The checker returns structured evidence:

```text
rule_key · satisfied · record_id(s) · observed_on · freshness · explanation
```

The UI renders missing rules by name. It never emits a composite evidence score.

### 3.3 Change log and submissions

Every category change appends a **forecast change event** containing before, after, changed-at, actor, the commercial event that drove the move, and optional source interaction/reference. A change cannot be saved with an empty driver. Correcting a mistaken event appends a correction; history is never overwritten.

A **forecast submission** freezes the current entry set and source manifest at a timestamp. The generated artifact leads with:

1. movement since the previous submission in the same period;
2. current totals grouped by currency and revenue basis: closed, commit, best case, pipeline, weighted pipeline, and excluded-from-weighting count;
3. every unsupported Commit/Best Case call and its named evidence gaps;
4. help-needed items linked to internal asks; and
5. entry-level record links.

Submission artifacts use the existing generated-document review workflow. Creating one never changes entry categories.

### 3.4 Opening lock and accuracy

Locking a period creates an immutable **opening snapshot** of every active entry, amount, category, probability, and source manifest. Unlocking is not supported; a bad lock is superseded by a new scenario/period with a reason.

Closing a period computes actuals from dated source facts:

- won expansion outcomes and compatible revenue events for opportunities;
- renewal completion from the superseding/current contract or a typed renewal outcome event;
- no close inferred merely from a changed forecast category.

Calibration reports counts and denominators per period:

- Commit closed / Commit at opening;
- Best Case closed / Best Case at opening;
- Pipeline closed / Pipeline at opening;
- forecast amount vs. compatible actual amount by currency and revenue basis; and
- entries excluded because actual amount units were unavailable or incompatible.

Rates may be displayed per period because the denominator is explicit. There is no composite forecaster score and no benchmark unless a versioned, sourced benchmark record is later approved.

### 3.5 Forecast schema

Use the next available migration number (currently expected to be `0026`) for:

- `forecast_periods`
- `forecast_entries`
- `forecast_entry_sources`
- `forecast_change_events`
- `forecast_submissions`
- `forecast_submission_lines`
- `forecast_opening_snapshots`
- `forecast_opening_lines`
- `renewal_outcome_events`

Key constraints:

- exactly one target FK on each forecast entry;
- target, source, owner, and ask-calendar account scope enforced by triggers;
- one live entry per target per period;
- omitted reason required for `omitted`;
- amount fields non-negative and currency three-letter uppercase;
- probability requires author and assessment date;
- snapshots/submission lines immutable after creation; and
- only the explicit lock/close service can transition period state.

---

## 4. Internal asks and escalation

### 4.1 Ask record

An **internal ask** is a first-class account record containing:

- concise need and success condition;
- account and optional opportunity/forecast-entry/review/generated-document links;
- requested-by Valence person;
- requested-from Valence person and/or internal function;
- needed-by date;
- linked revenue amount with currency/basis or a link to the forecast entry that supplies it;
- type (`general`, `data_request`, `product`, `legal`, `deal_desk`, `executive`, `pricing`);
- status (`raised`, `acknowledged`, `in_progress`, `delivered`, `declined`);
- current owner; and
- source interaction/reference when captured from another record.

`declined` requires a reason. `delivered` requires delivered-on, delivered-by, and a completion note or artifact link. Status transitions append events and cannot move backward without a reasoned reopen event.

At least one requested-from target is required. Opportunity, forecast-entry, review, feedback-occurrence, and blocked-document relationships use explicit foreign keys and same-account triggers. Additional blocked/generated documents use a dedicated join table with a real `generated_documents` foreign key.

An ask linked to a Commit entry displays inherited urgency but does not copy or persist the forecast category. If the forecast entry changes, the treatment changes on read.

### 4.2 Functions and policies

Internal functions are portfolio-global, editable seed data: Data, Product, Legal, Deal Desk, Finance/Pricing, Executive Sponsor, Support, and Other. They are not people and do not receive logins.

An **escalation policy** is versioned and defines, per ask type and severity:

- functional or hierarchical path;
- elapsed business-time threshold;
- destination function/person role;
- expected response window; and
- next step if unresolved.

Policy edits never rewrite the policy version attached to an existing escalation.

Elapsed business time reuses the account's existing timezone and business-hours settings. This module does not introduce a second calendar-hours implementation.

### 4.3 Escalation chain

Escalation does not create another ask. An **escalation instance** links to the ask and records severity, policy version, path type, opened-at, resolved-at, and resolution. Every step appends an **escalation event**: raised to whom/function, when, why the threshold fired, what response occurred, and who recorded it.

No event sends a message. The UI produces a suggested, factual escalation note; the operator records that they escalated externally.

Derived Today behavior:

- ask past needed-by and not terminal;
- ask unacknowledged past its policy threshold;
- active escalation whose current ladder step is overdue;
- Commit-linked ask entering its warning window; and
- delivered ask whose dependent artifact/forecast evidence still reads incomplete.

Queue dedupe keys use the ask/escalation ID and condition episode. Resolving a queue item does not close the underlying ask.

### 4.4 Data requests

`data_request` asks add structured optional fields:

- metric definition;
- population segment/view;
- requested cohort cut or period;
- requested current-through date;
- blocked deliverable/document;
- expected delivery format; and
- result source reference.

They render as a filtered lane of the same ask ledger, not a separate workflow.

### 4.5 Ask and escalation schema

Add:

- `internal_functions`
- `internal_asks`
- `internal_ask_events`
- `internal_ask_documents`
- `escalation_policies`
- `escalation_policy_steps`
- `escalation_instances`
- `escalation_events`

Every chain event is append-only. Current ask/escalation status is a transactionally maintained projection for fast reads.

---

## 5. Internal account reviews

### 5.1 Review record and point of view

An **account review** belongs to an account, has scheduled/held dates, review type, chair, Valence participants, status (`planned`, `held`, `cancelled`), and optional source interaction. A held review requires an interaction so its participants and factual notes remain in the main ledger.

The operator's point of view is a separate append-only record: account, paragraph, author, assessed-on, and supersedes link. It is the only manually authored section of the one-page brief. The generator never substitutes AI text when it is missing; it prints a named gap.

### 5.2 One-page account brief

The generated brief contains, in this order:

1. delivery/value and commercial status, rationale, assessment age, and trajectory since the prior review;
2. the latest dated operator point of view;
3. growth-plan bridge: target, named lines, compatible funded/projected totals, overlap exclusions, and unfunded gap;
4. top three open risks with owner, mitigation, and freshness;
5. champion picture and single-thread exposure;
6. renewal/notice/decision countdown;
7. forecast position and unsupported calls; and
8. top internal asks/help needed.

Selection is deterministic. “Top” means documented ordering by severity/urgency then age, never an AI ranking.

### 5.3 Full packet and challenge sheet

The full packet adds:

- whitespace map;
- value-realization ledger;
- operational-trigger progress;
- forecast by category;
- People coverage and executive-touch exposure;
- open asks/escalations;
- product-feedback occurrences; and
- prior review decisions and commitments.

The **challenge sheet** is generated from explicit rules:

- unsupported Commit or Best Case entry;
- category downgrade since prior submission;
- status older than its reassessment threshold;
- status movement without its required response record;
- high-severity risk with no mitigation/owner;
- expired or stale source behind a material claim;
- overdue review commitment;
- aging ask/escalation; and
- renewal or works-council timing conflict.

Each question includes the source IDs that caused it. AI may improve phrasing only through the existing proposed/reviewed mechanism; the deterministic question and source list remain canonical.

### 5.4 Review decisions and commitments

The main ledger is generalized rather than duplicated:

- `commitments` and `decisions` gain direct `account_id`;
- `program_id` becomes optional for account-level internal records and remains populated for existing program records;
- database checks enforce that any program belongs to the direct account;
- review-created rows may link `account_review_id`;
- commitments gain `commitment_class`: `client`, `leadership_to_operator`, `operator_to_internal`, or `internal_peer`;
- existing rows backfill to `client` unless their responsible party is unambiguously Valence, in which case migration code records the chosen mapping in the decision log; and
- client visibility continues to default false and remains governed by the existing promotion path.

Today resolves account context directly when no program exists. Ledger, person cards, account history, generators, search, and export all include account-level commitments and decisions.

Review-completion analytics report counts and denominators by commitment class. They do not infer direction from names or affiliations after migration.

### 5.5 Review schema

Add:

- `account_reviews`
- `account_review_participants`
- `operator_views`

Generalize:

- `commitments`
- `decisions`

Widen generated-document kinds with:

- `internal_account_brief`
- `internal_review_packet`
- `internal_challenge_sheet`

---

## 6. Status governance and internal reporting

### 6.1 Versioned criteria

Status criteria are editable, versioned records per dimension and account scope. A criterion version contains written green/amber/red/unknown criteria, effective date, author, and source/rationale. Accounts may inherit portfolio defaults or select an account-specific version.

An assessment stores the exact criteria version used. Changing criteria does not restate history.

Add:

- `status_criteria_versions`
- `account_status_assessments`

Backfill one assessment from each existing non-unknown account status, preserving the current assessed date and rationale. Unknown defaults need no fabricated historical event.

### 6.2 Weekly team update

Replace the current activity dump with the operator format, per account:

- **What moved:** forecast category changes, status changes, material decisions, closed risks, delivered asks, and wins since the prior generated update;
- **What is stuck:** open blockers, overdue commitments, aging asks/escalations, unsupported Commit/Best Case calls, and stale material evidence;
- **What I need:** active internal asks, leadership decisions, executive touches, and Data requests;
- **Next seven days:** material asks, renewals/notices, review dates, and commitments.

Account-level interactions and commitments are included even when an account has no program. The generator may produce a clean “no material movement” row; it must not silently omit an active account merely because the account has no program-scoped records.

### 6.3 Monthly portfolio brief

One internal page across the book:

1. forecast movement and totals grouped by compatible units;
2. account statuses with prior-state arrows and assessment freshness;
3. top risks and red-origin links;
4. top internal asks/escalations;
5. executive-touch coverage;
6. wins worth repeating upward; and
7. data gaps/exclusions.

The report runs the no-surprises validator before a draft can be saved.

### 6.4 Templates and source manifests

Report format is editable without code changes, but field selection and safety rules remain code-owned.

Add versioned `report_templates` seeded from repository YAML files. A template controls headings, labels, ordering, and optional sections. It cannot introduce an unapproved query or bypass audience/no-surprises checks.

Each template declares one audience profile: `operator`, `team`, `leader`, or `skip_level`. Code owns the field allow-list for each profile. A higher-level profile removes detail from the same selected records; it cannot query a different truth set or override a record's visibility. Raw notes and source-span text are excluded from recurring reports unless a named generator section explicitly requires and labels them.

Every internal generated document stores an immutable source manifest:

```text
record_type · record_id · updated_at/version · inclusion_reason · visibility_class
```

Editing a draft changes presentation text, not its frozen source manifest. Regeneration creates a new draft.

Add:

- `report_templates`
- `generated_document_sources`

Widen generated-document kinds with:

- `forecast_submission`
- `monthly_portfolio_brief`
- revised `team_update`

---

## 7. Team coordination and briefing

### 7.1 Internal roster

An **account roster** links an existing Valence person to an account with:

- role (`account_lead`, `supporting_em`, `advisor`, `executive_sponsor`, `data_partner`, `product_partner`, `legal_partner`, `support_partner`, `other`);
- standing responsibilities;
- primary/backup flag;
- active-from and active-through dates;
- expected touch cadence where applicable; and
- briefing scope/notes.

The same person may have different roles on different accounts. A roster row does not grant access.

Add:

- `account_internal_roster`
- `roster_role_defaults` as editable seed data

### 7.2 Contribution visibility

Existing interaction participation remains the source of truth. Capture and ingestion association must permit active roster members as Valence participants. Derived views answer:

- last touch by any Valence executive;
- last participation by each roster member;
- accounts with no executive touch inside the configured cadence;
- account activity concentrated in one internal person; and
- upcoming meetings with missing expected internal coverage.

No contribution score or leaderboard is introduced.

### 7.3 Briefing packs

Generated internal artifacts:

- **role-scoped call brief:** current context, the records relevant to the roster role, attendees, open commitments/asks, and talking points;
- **coverage brief:** live commitments both directions, next 14 days of dates, open asks/escalations, active risks, forecast calls, renewal facts, key people, and “three things that break if ignored”; and
- **return brief:** what changed during the coverage window, generated from event history.

The “three things” are deterministic: highest-severity unresolved item, nearest contractual/forecast date, and highest-value unsupported or blocked forecast item, with tie-breaking documented. Operator edits remain possible in draft.

Widen generated-document kinds with:

- `colleague_call_brief`
- `coverage_brief`
- `coverage_return_brief`

---

## 8. Product feedback loop

### 8.1 Theme and occurrence model

A **product feedback item** is the portfolio-level theme Product can act on: title, problem statement, type, owner function/person, current status (`logged`, `submitted`, `roadmapped`, `shipped`, `declined`), product reference/link, and status rationale.

A **feedback occurrence** is one account's sourced request:

- account and stakeholder;
- source interaction/reference and source span;
- account/revenue context via forecast/growth-plan links rather than copied untyped numbers;
- workaround and impact;
- captured-by/on;
- acknowledgment state; and
- resolution-close-loop state.

An occurrence belongs to exactly one theme. Moving it to another theme appends an event with a reason. This makes “three of five accounts asked for X” a query with record links and denominator, not a text-similarity claim.

### 8.2 Closing the loop twice

Derived Today items fire:

1. after capture until the requesting stakeholder has an acknowledgment touch recorded; and
2. when a theme becomes `shipped` or `declined` until every active occurrence has a resolution touch recorded.

A touch is an existing interaction linked to the occurrence. The system suggests content from the source and resolution record but never sends it.

`declined` requires a reason. `shipped` requires a product reference or release note source. Status transitions append events.

### 8.3 Feedback schema

Add:

- `product_feedback_items`
- `product_feedback_occurrences`
- `product_feedback_events`
- `product_feedback_touches`

An internal ask of type `product` may link a theme/occurrence, but the records remain distinct: the ask tracks Valence's internal dependency; feedback tracks the client's need and loop closure.

---

## 9. Portfolio internal analytics

The Accounts destination gains a `Book / Internal` segmented view. This is not a fifth top-level navigation item.

The Internal portfolio view contains small, drillable measures with explicit denominators and exclusions:

- forecast calibration by period and category;
- forecast movement count and amount by compatible currency/basis;
- ask acknowledgment and resolution time by internal function;
- open asks past needed-by by function;
- escalation age and resolution time by severity/path;
- review commitment completion by commitment class;
- executive-touch coverage across active accounts;
- roster concentration/exposure counts;
- product-feedback themes by status and account count; and
- acknowledgment/resolution-loop completion for feedback occurrences.

Rules:

- no composite score;
- no ranking people by performance;
- medians plus raw counts for turnaround where sample sizes support them;
- “insufficient data” distinct from zero;
- record IDs supplied for every drill-down;
- no cross-currency sum or implied benchmark; and
- benchmarks, if ever added, are versioned and sourced data.

---

## 10. Information architecture and interaction design

### 10.1 Navigation amendment

The top-level navigation remains Today, Accounts, Library, Operations.

The account workspace becomes:

```text
Overview · Ledger · People · Plan · Commercial · Evidence · Internal · Outputs
```

The Internal tab contains sub-tabs:

```text
Forecast · Asks · Reviews · Team · Feedback
```

The Accounts destination contains:

```text
Book · Internal
```

Outputs remains the place for generated artifacts and review-state workflow. Internal views link to their current generated drafts rather than duplicating an artifact library.

### 10.2 Surface rules

- tables are the primary surface;
- category and status always pair color with text and shape;
- Forecast uses existing status-shape conventions but category is never described as account health;
- freshness language appears on every dated assertion/evidence check;
- risk treatment names the missing rule, never just a warning icon;
- all row actions work by keyboard and preserve visible focus;
- no inline arbitrary hex or spacing values; tokens only;
- both themes and reduced motion are first-class; and
- no new expressive dashboard graphics where a drillable table or small chart is clearer.

### 10.3 Capture paths

Global capture gains proposed conversion targets for:

- internal ask;
- review commitment/decision;
- product-feedback occurrence; and
- forecast change event.

As with existing extraction, these are strict predefined proposals, source spans remain visible, and nothing writes until accepted. Manual creation remains available from the relevant Internal sub-tab.

---

## 11. API and service boundaries

Keep domain logic out of routers. Add focused services:

- `app/internal_forecast.py`
- `app/internal_asks.py`
- `app/internal_reviews.py`
- `app/internal_reporting.py`
- `app/internal_roster.py`
- `app/product_feedback.py`

Add routers:

- `routers/internal_forecast.py`
- `routers/internal_asks.py`
- `routers/internal_reviews.py`
- `routers/internal_reporting.py`
- `routers/internal_roster.py`
- `routers/product_feedback.py`

Representative routes:

```text
GET/POST   /api/forecast-periods
POST       /api/forecast-periods/{id}/lock
POST       /api/forecast-periods/{id}/close
GET/POST   /api/forecast-periods/{id}/entries
PATCH      /api/forecast-entries/{id}
POST       /api/forecast-entries/{id}/category
GET        /api/forecast-entries/{id}/evidence
POST       /api/forecast-periods/{id}/submissions

GET/POST   /api/accounts/{id}/internal-asks
POST       /api/internal-asks/{id}/status
POST       /api/internal-asks/{id}/escalations
POST       /api/escalations/{id}/events

GET/POST   /api/accounts/{id}/reviews
POST       /api/account-reviews/{id}/hold
GET/POST   /api/accounts/{id}/operator-views
GET        /api/account-reviews/{id}/challenge-sheet

GET/POST   /api/accounts/{id}/internal-roster
GET        /api/accounts/{id}/coverage-brief

GET/POST   /api/product-feedback
POST       /api/product-feedback/{id}/occurrences
POST       /api/product-feedback/{id}/status
POST       /api/product-feedback-occurrences/{id}/touches

GET        /api/portfolio/internal-analytics
GET        /api/internal-reports/{kind}/preview
POST       /api/internal-reports/{kind}/documents
```

Transition endpoints enforce lifecycles; generic patch endpoints cannot change category, period state, ask status, escalation state, review held state, feedback status, or generated-document review state.

---

## 12. Build sequence

Each stage is a complete vertical slice: migration, schema models, services, routers, frontend, mock seed, export/search/Operations integration, adversarial tests, both-theme screenshots, HANDOFF update, README status, and decision-log entry. The existing suite must remain green at every stage.

### Stage 10.0 — Integrity foundations

- reserve and document the next migration sequence;
- add versioned status criteria and assessment history;
- backfill existing status snapshots;
- generalize account-level commitments and decisions;
- fix the weekly update to include account-level records and adopt the operator format;
- add report-template/source-manifest primitives; and
- add reusable no-surprises validation.

This stage lands first because later generators and review commitments otherwise build on known-invalid primitives.

### Stage 10.1 — Forecast

- periods, entries, sources, evidence checks, change events;
- submission snapshots and generated forecast artifact;
- opening lock, close, and two-period mock calibration;
- account Internal → Forecast UI;
- portfolio forecast slice; and
- exact evidence/account-scope/currency tests.

### Stage 10.2 — Asks and escalation

- internal functions, asks, events, policies, ladders, escalation chain;
- Data-request lane;
- Today triggers and help-needed forecast links;
- account Internal → Asks UI; and
- policy-version, chain-integrity, and no-auto-send tests.

### Stage 10.3 — Reviews and reporting

- reviews, participants, operator views;
- one-page brief, full packet, challenge sheet;
- monthly portfolio brief;
- no-surprises blocking UI;
- status trajectory and response enforcement; and
- exact artifact/source-manifest tests.

### Stage 10.4 — Roster and coverage

- internal roster and role defaults;
- Valence participants in capture flows;
- contribution/exec-touch queries;
- call, coverage, and return briefs; and
- Accounts → Internal portfolio coverage view.

### Stage 10.5 — Product feedback and final analytics

- feedback themes, occurrences, transitions, loop-closing touches;
- acknowledgment/resolution Today triggers;
- cross-account aggregation;
- full internal analytics;
- end-to-end five-account demo; and
- final adversarial review against Section 13.

No stage flips a real connection. Any future external delivery channel is a new `CONNECTIONS.md` row and requires the standing governance approval.

---

## 13. Definition of done and required tests

The module is not done because screens render or unit tests pass. The following behaviors must be demonstrated against synthetic data.

### 13.1 Forecast

- category and stage vary independently;
- unsupported Commit is allowed but visibly names every missing rule;
- budget-owner engagement is account-scoped and expires after 30 days;
- changing category without a driver is rejected;
- opening snapshot does not change when live entries later change;
- period close uses source outcomes, not final forecast category;
- cross-currency/basis totals remain separated;
- weighted totals exclude entries without explicit probability and disclose the exclusion;
- two periods render Commit and Best Case counts/denominators; and
- forecast submission movement is relative to the previous submission, not creation time.

### 13.2 Asks and escalation

- ask status transitions are append-only and terminal rules hold;
- declined requires a reason; delivered requires completion evidence;
- Commit-linked urgency changes when the forecast category changes without copying category;
- aging ask surfaces once in Today with a stable episode key;
- escalation follows the policy version attached at opening even after policy edits;
- the complete functional/hierarchical chain survives export/restore; and
- no code path transmits a message.

### 13.3 Reviews, status, and reporting

- a held review requires an interaction and preserves participants;
- leadership-to-operator and operator-to-internal commitments both render in Ledger and Today;
- account-level commitments need no fake program and never leak into another account;
- amber without recovery owner/action/date is rejected;
- red without leadership-decision handling is rejected;
- status trajectory survives later criteria edits;
- one-page brief contains only the latest dated operator-authored point of view;
- challenge questions are reproducible from source records;
- a red claim without a valid origin blocks document creation with HTTP `409`;
- every eligible red origin appears or carries a typed exclusion reason; and
- saved document body and source manifest do not change when live data changes.

### 13.4 Roster and feedback

- roster members are existing Valence persons and cannot belong to a client account as employees;
- interaction contribution derives from participants, not a manual last-touch field;
- coverage brief includes the next 14 days, active asks, commitments, risks, and forecast calls;
- one feedback theme aggregates two account occurrences with source links;
- theme movement preserves occurrence history;
- shipped/declined status creates one unresolved close-loop condition per active occurrence;
- recording a linked touch clears only that occurrence; and
- no individual product-usage field exists anywhere.

### 13.5 End-to-end acceptance

On the seeded five-account portfolio, in under five minutes each, the operator can:

1. create a forecast submission with a movement log and linked help-needed asks;
2. generate a one-page account brief with a dated operator point of view;
3. generate a monthly portfolio brief after resolving a deliberately planted no-surprises blocker;
4. generate a two-week coverage brief for a colleague;
5. see one leadership commitment overdue in Today;
6. advance one ask through aging, escalation, response, and delivery with its chain intact;
7. aggregate one product theme across two accounts and close the loop to both; and
8. close two mock forecast periods and inspect calibration.

The automated acceptance test must plant adversarial cross-account records, internal-only text, stale evidence, incompatible currencies, overlapping growth-plan populations, and an unregistered red claim. It passes only when none leak, blend, disappear, or bypass the relevant validator.

---

## 14. Completion checklist

Before this scope is declared complete:

- all backend tests pass under the repository Python 3.12 environment;
- frontend build and lint pass with no newly introduced warnings;
- every new screen is verified in light and dark themes with keyboard focus and semantic tables;
- migration upgrade works from the current production-shaped schema and on a fresh database;
- account export/restore round-trips every new account-scoped record;
- search and Operations expose all new record families;
- mock-only and single-editor boundaries are re-audited;
- `README.md`, `HANDOFF.md`, `CLAUDE.md`, `DESIGN-GUIDE.md`, `CONNECTIONS.md`, and `decisions.md` agree with the shipped state; and
- the Section 13 acceptance demo is run from a clean database and its result recorded.
