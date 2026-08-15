# Valence OS — Account Copilot Spec
### Grounded account questions, change briefs, weekly planning, and source-safe drafting
*v1 accepted · August 2026 · researched, codebase-reconciled, and **Stage 12 scope authority***

This document defines the capstone AI layer after Adoption Campaign Stage 11. Zach accepted it as
Stage 12 under D-105. Acceptance authorizes the numbered mock-only build; it does not connect or
approve a real model endpoint.

The codebase is ready for this layer in a way it was not earlier. It now has structured account facts,
append-only histories, a deterministic attention queue, Stage 10 briefs and forecasts, Stage 11
campaigns, FTS5 search, a job worker, generated-document source manifests, and a fail-closed LLM
adapter. What it does not have is a trustworthy way to ask a cross-record question, understand what
changed, plan the week from those facts, or turn an answer into a source-governed draft.

---

## 0. Decision, boundary, and sequencing

### 0.1 Recommendation

Build the Account Copilot only after Stages 11.1 and 11.2 are complete; that precondition is met.
The first release is a **grounded, read-only analyst implemented as predefined workflows**, not an
autonomous agent. It may answer, summarize, compare, explain, and draft into an existing review-gated
artifact. It never writes an operational record, sends a message, changes a forecast, schedules a
meeting, or chooses an account action on its own.

This sequencing preserves the original rationale for ranking the copilot third: its quality depends
more on the completeness and integrity of the structured system than on model cleverness.

### 0.2 One-sentence product contract

For an explicit account or portfolio scope, the operator can ask a question, see a concise answer in
their working style, verify every material factual claim against current native records, see what is
missing, stale, conflicted, or suppressed, and route supported material into an existing draft
workflow without granting the model write or send authority.

### 0.3 What the copilot is not

- **Not a second search box.** FTS discovers candidate records; the copilot resolves their current
  state from canonical tables and explains the result.
- **Not model-generated SQL.** The model receives a small allow-list of typed read operations. It
  never emits or executes arbitrary SQL.
- **Not a second priority engine.** Today, forecast rules, renewal timing, campaign readiness, and
  escalation policy remain canonical. The weekly cockpit composes and explains them.
- **Not a new document system.** Drafting uses `generated_documents`, its audience rules, review
  lifecycle, and immutable source manifests.
- **Not a memory system.** V1 keeps bounded session context and explicit saved runs. It does not
  silently learn durable facts or preferences from chat.
- **Not an autonomous agent.** No open-ended tools, recursive planning loop, outbound connector, or
  irreversible action is available to the model.
- **Not a replacement for the operator's judgment.** Recommendations are labeled as synthesis or
  suggestion, never stored as account truth unless the operator records them through an existing
  governed workflow.
- **Not an external-research assistant.** V1 answers from Valence OS records only. Web research would
  be a separate connection, source-authority, and trust decision.

### 0.4 Reconciliation with the built system

| Existing capability | Reuse | What the copilot adds |
|---|---|---|
| SQLite native records | Canonical facts and current state | Typed, account-scoped read contracts |
| FTS5 global search | Candidate discovery and lexical matching | Query planning plus canonical hydration |
| Today / queue | Explainable priorities | Weekly composition; never a competing rank |
| audit and domain histories | Dated changes and before/after facts | One normalized material-change feed |
| Stage 10 reports and briefs | Deterministic sections and change logic | Natural-language entry and cited synthesis |
| generated documents | Draft, review, audience, source manifest | Source-safe drafting and style application |
| extraction proposal pattern | Strict schema, model/prompt provenance, human acceptance | Safety precedent; no operational proposals in V1 |
| jobs worker | Durable long-running AI work and visible failure | Copilot answer and drafting jobs |
| connection registry | Fail-closed external endpoint approval | Separate copilot payload class and runtime switch |
| source references | Original evidence locator | Claim-level links through native records to sources |
| portfolio export/restore | Portable account graph | Runs, claim support, feedback, and style version |

---

## 1. Research-derived design principles

The research supports a narrow, inspectable copilot. It does not support putting a fluent model in
front of the database and treating fluency as reliability.

1. **Prefer workflows over agents.** Anthropic's production guidance recommends the simplest
   solution that works and distinguishes predictable code-orchestrated workflows from agents that
   dynamically control their own process. The four jobs here are bounded enough for workflows:
   classify intent, retrieve through typed readers, generate from a bounded packet, validate claims.
2. **Grounding requires more than retrieval.** Retrieving a relevant record does not mean the final
   answer used it correctly. Retrieval quality, answer groundedness, relevance, completeness, and
   citation support are evaluated separately.
3. **Citations are claims, not decorations.** Research on citation-enabled generation finds that even
   strong systems frequently leave claims unsupported. Each material claim therefore links to the
   exact retrieved record snapshot that supports it, and unsupported claims fail validation.
4. **Access control happens before the model.** Account, audience, privacy, freshness, and archival
   rules filter the context packet before any text reaches an LLM. The model is never asked to enforce
   those rules.
5. **Retrieved content is untrusted data.** Notes, transcripts, emails, and linked summaries may
   contain instructions. They are delimited, size-bounded, origin-labeled, and unavailable to tool
   control. Retrieval failure never falls back to an ungrounded answer.
6. **Evidence coverage is more honest than model confidence.** V1 shows `supported`, `partial`,
   `conflicted`, or `insufficient evidence`. It does not present an uncalibrated probability that an
   answer is correct.
7. **Correction must be cheap and explicit.** The operator can mark a claim wrong, identify a missing
   source, or correct a canonical record. Feedback never silently rewrites memory or account facts.
8. **Structured retrieval precedes semantic infrastructure.** At a few thousand rows, typed SQL
   readers plus FTS5 are the baseline. Embeddings add privacy, integrity, deletion, and isolation
   obligations; they enter scope only if a labeled evaluation set proves systematic lexical failure.
9. **No single quality score.** A polished answer can be relevant but ungrounded, or grounded but
   incomplete. Quality stays decomposed, matching the repository's rejection of composite health
   scores.
10. **Model changes are product changes.** Model, prompt, retrieval-contract, validator, and style
    versions are recorded and run against the golden set before a new configuration becomes active.

### 1.1 Research basis

- [NIST AI RMF Generative AI Profile](https://www.nist.gov/publications/artificial-intelligence-risk-management-framework-generative-artificial-intelligence)
  — lifecycle governance, testing, monitoring, provenance, and human oversight.
- [OWASP RAG Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/RAG_Security_Cheat_Sheet.html)
  — context isolation, access-control inheritance, attribution, output validation, logging, and
  fail-closed retrieval.
- [OWASP LLM06: Excessive Agency](https://genai.owasp.org/llmrisk/llm062025-excessive-agency/)
  — minimum tools and permissions, constrained functionality, and human approval for high-impact
  actions.
- [Anthropic, Building effective agents](https://www.anthropic.com/engineering/building-effective-agents)
  — workflows before agents and simple composable patterns before frameworks.
- [Anthropic, Contextual Retrieval](https://www.anthropic.com/engineering/contextual-retrieval)
  — lexical and semantic retrieval can be complementary when corpus scale and evaluation justify it.
- [Microsoft RAG evaluators](https://learn.microsoft.com/en-us/azure/ai-foundry/concepts/evaluation-evaluators/rag-evaluators)
  — separate retrieval, groundedness, relevance, and completeness evaluation.
- [Microsoft Research, Guidelines for Human-AI Interaction](https://www.microsoft.com/en-us/research/project/guidelines-for-human-ai-interaction/)
  — make capabilities and limitations clear, scope service when uncertain, explain behavior, support
  correction, and provide user control.
- [Gao et al., Enabling Large Language Models to Generate Text with Citations](https://aclanthology.org/2023.emnlp-main.398/)
  — citation correctness and completeness are distinct, measurable failure modes.
- [OWASP, Memory is a feature and an attack surface](https://genai.owasp.org/2026/05/13/memory-is-a-feature-it-is-also-an-attack-surface/)
  — persistent context can carry poisoned or stale instructions into later sessions.

These sources shape controls and workflow. No external accuracy, productivity, or model-performance
number becomes a product claim or a hard-coded benchmark.

---

## 2. User jobs and the answer contract

### 2.1 Supported jobs

V1 supports four explicit intents.

1. **Fact retrieval:** “What did we promise DACH IT security, and where does it stand?”
2. **Cross-record synthesis:** “What is blocking the European manager rollout?”
3. **Temporal comparison:** “What changed in Meridian since last Friday?”
4. **Planning and drafting:** “What needs my attention this week?” and “Draft the internal note from
   this answer.”

The planner classifies each request into a strict intent schema. It may combine compatible intents,
such as a fact answer followed by an internal draft, but it cannot invent a new tool or audience.

### 2.2 Scope is always visible and enforced

Every run has exactly one scope:

- `program` — one program inside one account;
- `account` — one account and all its current programs; or
- `portfolio` — all accounts, explicitly selected.

The current account workspace supplies the default account scope. Portfolio scope is never inferred
from phrases like “all customers”; the operator selects it or confirms an explicit disambiguation.
The scope chip remains visible beside the question and answer. Account filters are applied inside
each typed reader, before records enter the context packet.

### 2.3 Three answer modes

- **Answer:** factual synthesis supported by native records.
- **Answer with gaps:** the supported portion plus named missing, stale, suppressed, or conflicting
  evidence.
- **Abstain:** no defensible answer. The response states what was searched and the smallest next step
  that would make the question answerable.

The system never substitutes general model knowledge for missing account evidence.

### 2.4 Claims and evidence

A **material claim** is any statement about a person, commitment, status, date, amount, outcome,
metric, risk, decision, cause, recommendation premise, or account comparison. Every material claim
has:

`claim kind · claim text · support state · cited run-source ids`

Claim kinds are `fact`, `calculation`, `inference`, and `recommendation`.

- Facts cite the native record carrying the fact.
- Calculations cite every input and name the deterministic calculation.
- Inferences cite their premises and are labeled “Inference.”
- Recommendations cite their premises and are labeled “Suggested move,” never account truth.

Pure connective or formatting text does not need a citation. A record being retrieved is not enough;
the cited snapshot must actually entail the claim. The validator rejects a citation to a merely
related record.

### 2.5 Freshness, privacy, and authority

- Stale metric-derived facts enter the packet as `unknown`, never with their previous numeric value.
- Cohort-suppressed values never enter the packet, answer, log excerpt, or model payload.
- Superseded decisions, value targets, contracts, and assessments are historical context, not current
  truth, unless the question explicitly asks for history.
- Canonical external values and operational overlays stay labeled separately.
- Negative evidence remains retrievable and cannot be filtered out to make an answer more favorable.
- A conflict between two current-looking records produces `conflicted`; the model does not silently
  pick the more convenient one.

---

## 3. Architecture: deterministic control plane, bounded model

```mermaid
flowchart LR
    Q[Question + explicit scope] --> P[Strict intent plan]
    P --> R[Allow-listed typed readers]
    R --> C[Filtered context packet]
    C --> M[Mock or approved LLM]
    M --> S[Structured answer + claim map]
    S --> V[Deterministic validation]
    V -->|pass| A[Answer with native-record citations]
    V -->|fail| X[Retry once with errors, then abstain]
    A --> F[Feedback or existing draft workflow]
```

The model operates inside the pipeline; it does not control the pipeline.

### 3.1 Strict intent plan

The first step emits validated JSON:

`intent · scope · entities · time window · requested audience · reader names · output mode`

Unknown reader names, scope changes, client-facing requests without a permitted generator, and
unsupported output modes fail schema validation. Common prompt starters may bypass model planning
and use a predefined plan directly.

**The planner sees only trusted input.** It receives the operator's question, the selected scope, and
governed vocabularies — never retrieved prose. Retrieved content reaches only the generation step,
which has no tool access and cannot alter the plan. This is the privilege separation behind the
dual-LLM and CaMeL results: an injected instruction inside a note can only influence text that is
about to be schema-validated, never the control flow that decides what to read. Delimiting untrusted
content (§9.2) reduces the model's chance of obeying an injection; keeping it out of the planner
removes the path structurally, and is the stronger of the two controls.

### 3.2 Allow-listed typed readers

The initial reader set is deliberately small:

- `search_records(query, account_id?, program_id?, record_types?)`
- `get_record(record_type, record_id, expected_account_id?)`
- `get_account_snapshot(account_id, as_of?)`
- `get_people_context(account_id, names_or_roles)`
- `get_commitment_context(account_id, entities, state?, time_window?)`
- `get_commercial_context(account_id, entities, as_of?)`
- `get_evidence_context(account_id, population_or_metric, as_of?)`
- `get_campaign_context(account_id, population_or_use_case, as_of?)`
- `get_material_changes(scope, after_cursor, through?)`
- `get_week_inputs(scope, week_start)`

Each reader owns its joins, archive rules, current-record logic, freshness, privacy suppression, and
serialization. Readers return stable record identifiers plus only the fields needed for the intent.
There is no generic `run_sql`, raw database handle, file reader, web fetch, email sender, calendar
writer, or arbitrary URL tool.

### 3.3 Retrieval order

1. Resolve exact identifiers and governed vocabularies.
2. Query structured readers for current facts.
3. Use FTS5 to discover additional candidate records and hydrate them through typed readers.
4. Rank deterministically by exact entity match, record authority, currentness, date, and lexical
   relevance.
5. Build a bounded packet and record every included or excluded candidate reason.

FTS snippets are discovery aids, not evidence. `search.py` currently indexes internal raw notes for
the single operator; the copilot context builder treats those strings as untrusted and never exposes
them across accounts or into a client-facing workflow.

### 3.4 Context packet

Every item sent to the model contains:

`packet id · record type · record id · account id · record version · authority · freshness state · visibility · fields · origin label`

Untrusted prose is wrapped in explicit data delimiters and size-limited. The packet begins and ends
with the system contract that retrieved text is evidence, never instruction. The packet is stored as
an immutable retrieval manifest. Provenance uses record identifiers, content hashes, and the minimum
field snapshot needed to support the answer; sensitive excerpts follow the source's retention rules.
A full raw note, transcript, attachment, or email is not duplicated into the run merely because it
was retrieved.

### 3.5 Generation and validation

The model returns structured output: answer sections, material claims, claim kinds, cited packet ids,
named gaps, and optional suggested follow-up questions. Server validation enforces:

- every cited packet id was actually retrieved for this run;
- every source belongs to the run scope;
- suppressed or forbidden fields are absent;
- factual and calculation claims have citations;
- client-facing drafting routes only through a permitted generator;
- output size, link format, and supported record types are bounded; and
- model-created record identifiers, URLs, and citations are rejected.

One repair call may receive validator errors and the same context packet. A second failure produces
an abstention with a diagnostic; it never returns the raw invalid output.

**A retrieval-shaped failure gets a retrieval-shaped repair.** Re-generating against the same packet
can fix a malformed citation or an uncited claim, but it cannot fix a packet that never contained the
evidence — the second call sees exactly what the first one did. The repair step therefore branches on
the validator's failure class:

| Failure class | Repair |
|---|---|
| Malformed output, uncited claim, forbidden field, bad link format | Re-generate once against the same packet with the validator errors |
| Cited packet id absent, claim unsupported by any retrieved record, or the planner's named entity resolved to nothing | **One** additional retrieval round, then re-generate |

The second retrieval round is bounded and deterministic: it may re-run the readers already named in
the plan with widened identifiers or time window, and it may add readers from the allow-list, but it
cannot change scope, audience, or output mode, and it does not re-plan from model output. At most one
extra round runs per turn; a third failure abstains.

This is the hybrid the current literature converges on — classic single-pass retrieval by default,
with a second pass triggered only by explicit failure signals rather than on every query. It buys the
main benefit of agentic retrieval (recovering from a bad first retrieval) without adopting a control
loop the model steers, so §1.1's "workflows over agents" still holds. The trigger conditions are
code, not model judgment, and every extra round is recorded on the run so the cost is visible.

### 3.6 Fast path and job path

Retrieval preview and deterministic cockpit sections are synchronous. Every external model call,
multi-account synthesis, and drafting operation runs through the existing job table. The UI receives
a durable queued run, remains usable, and shows success or an actionable failure. The mock backend is
deterministic and runs the same contracts without a network call.

### 3.7 Provider mechanisms behind these contracts

This document stays provider-neutral about *what* is required. The repository is not: `app/extractor.py`
already speaks to the Claude API through the official SDK, and `CONNECTIONS.md` governs that one
boundary. Naming the mechanisms that implement the contracts above keeps the build from re-inventing
them and makes the cost and latency gates measurable rather than aspirational.

- **Schema enforcement is a request parameter, not a post-hoc check.** The strict intent plan (§3.1)
  and the structured answer (§3.5) are constrained decoding — the answer envelope via the structured
  output format, and each typed reader via strict tool definitions with `additionalProperties: false`
  and an explicit `required` list. Server-side validation in §3.5 still runs and is still the
  authority; constraining the decode means it has far less to reject, and a malformed envelope stops
  being a routine failure mode.
- **The context packet is the cache prefix, and that constrains its assembly order.** Caching is a
  prefix match: any byte change invalidates everything after it. The packet must therefore be
  assembled stable-content-first — system contract, reader definitions, then records in a
  deterministic order — with the operator's question and any per-run identifiers last. Serialization
  must be deterministic (sorted keys, stable record ordering); a timestamp or a set iteration inside
  the prefix silently makes every run a cache miss. Cache hit rate is a first-class run metric
  (§9.5), because a packet that never caches is the difference between a copilot that is affordable
  and one that is not.
- **Determinism is not available through sampling.** Current models reject `temperature`, `top_p`,
  and `top_k`. The deterministic-mock guarantee holds because the mock does not call a model; for the
  real backend, reproducibility comes from the frozen packet, the pinned model/prompt/retrieval
  versions already required by §1.10, and schema constraint — not from a sampling parameter. No part
  of this design may assume byte-identical answers across two real-mode runs.
- **A model refusal is its own failure class.** The API can return a successful response whose stop
  reason is a refusal, with an empty or partial body. Code that reads the first content block
  unconditionally breaks on it. Refusal is recorded distinctly from validator failure, retrieval
  failure, and timeout, because the operator response differs: a refusal means the question or its
  evidence tripped a policy classifier, not that the records were missing.
- **Reasoning depth is the latency lever.** Thinking is on by default on current models and is billed
  and counted inside the output ceiling. The effort level — not a token budget — is how §10.3's
  latency and consumption gates get tuned, and it is part of the pinned configuration that §1.10
  replays against the golden set.
- **Model identifiers are configuration with an expiry.** The active model is named in the connection
  registry (§9.1), pinned per run (§12.1), and reviewed when a generation ships. `EXTRACTOR_MODEL`
  currently defaults to a previous-generation model; the copilot must not inherit a stale default by
  copying that pattern.

None of this changes the governance position. Every mechanism here is exercised against the mock
adapter first, and none of it makes the real endpoint reachable — that remains the separate decision
in §9.1.

---

## 4. Grounded account questions

### 4.1 Entity resolution

Names like “DACH IT security” may refer to a population view, compliance lane, person role, program,
or several of them. Resolution order is exact native name, alias/governed vocabulary, exact FTS
title, then bounded fuzzy candidates. Multiple defensible candidates produce a disambiguation choice;
the copilot does not quietly choose one.

Entity resolution is recorded in the run so the operator can see that “DACH” meant population view
`pv-…`, not every record containing the word.

### 4.2 Current-state questions

“Where does it stand?” resolves through the record's domain lifecycle, not its last free-text mention.
For example:

- commitments use acknowledgement-based closure;
- opportunities use budget state;
- campaigns use reason-logged lifecycle and derived linked-plan state;
- value targets use fresh observations and their realization rules;
- risks and issues keep their distinct closure contracts; and
- contracts use the current version only unless history is requested.

The context service calls those existing domain services where available rather than rebuilding their
logic in copilot code.

### 4.3 Answer presentation

The default answer is short:

1. direct answer;
2. current state and dated evidence;
3. open gaps or conflicts;
4. suggested next move, when requested; and
5. source chips opening the exact native records.

Every answer shows scope, generated time, data-current-through, evidence state, model/prompt version
in details, and whether any expected source class was unavailable.

---

## 5. What changed since

### 5.1 One normalized material-change feed

The copilot does not summarize the append-only audit table directly. Audit entries are too generic,
and several domains already carry richer events. A code-owned change-feed service normalizes:

- forecast change events and submissions;
- account status assessments and trajectory;
- commitment, decision, risk, issue, task, and milestone transitions;
- internal ask and escalation events;
- renewal outcomes and contract-version changes;
- whitespace cell fact transitions;
- signal episode open/close/dismiss/convert events;
- campaign lifecycle, checkpoint, and evaluation changes;
- metric import, rollback, freshness, and value-target state changes;
- funding, operational-agreement, and growth-plan changes; and
- newly generated or reviewed material artifacts.

Each normalized item includes:

`event kind · account · occurred_at · effective_on if different · record ids · before · after · reason · source authority`

This is a derived read model in code, not a second event table unless performance or export evidence
later proves one necessary.

### 5.2 Cursor semantics

“Since last time” means one of:

- since the operator's last viewed change cursor for this scope;
- since a named saved run or generated document;
- since an explicit timestamp/date; or
- since the start of the current business week.

The interpreted boundary is shown in the answer. Saving a run may advance the cursor only after the
operator selects “Mark reviewed”; opening the panel does not silently consume changes.

### 5.3 Materiality and ordering

Materiality remains deterministic. Contractual dates, blockers, state transitions, commitment
closures, forecast movement, client pull, evidence invalidation, and completed outcomes rank ahead of
copy edits. AI may phrase the list; it may not decide that an otherwise reportable red event is
unimportant. Stage 10's no-surprises rules remain in force.

---

## 6. Weekly cockpit

The cockpit is a conversational entry into existing operating truth, not a dashboard or a second
queue. It assembles one week at a time from:

1. **Fixed dates:** contractual, fiscal, procurement, calendar, campaign, ask, and milestone dates.
2. **Deterioration risk:** overdue commitments, blockers, stale evidence, slipping forecast, and
   campaign readiness gaps.
3. **Customer pull:** unanswered pull signals, champion asks, and client-requested campaign work.
4. **Commercial movement:** forecast changes, funding steps, trigger events, renewal and expansion
   paper.
5. **Value and adoption:** undemonstrated targets, campaign checkpoints, and newly realized evidence.
6. **Internal leverage:** leadership decisions, overdue internal asks, escalations, and product
   feedback follow-through.

The deterministic section builder records why each item appears and which native rule ranked it.
The model may compress, group, and produce a readable plan. It cannot reprioritize a contractual date
below a stylistically interesting suggestion.

The cockpit offers only safe actions:

- open the source record;
- open the existing edit/create workflow;
- create a source-grounded internal draft; or
- dismiss the answer suggestion without changing the underlying queue item.

It does not time-block the calendar, auto-create tasks, change due dates, resolve attention items, or
send a briefing.

---

## 7. Drafting in the operator's working voice

### 7.1 Existing artifact machinery remains canonical

A copilot answer can seed an existing artifact kind only when that artifact's generator already
supports the requested audience and facts. The generator re-queries its approved source set and
creates a new `generated_documents` draft with an immutable source manifest. It does not copy the
copilot prose and citations blindly.

Internal free-form notes may be drafted from the run's supported claims and saved as an internal-only
run answer. A new client-facing document kind is out of scope unless a real recurring artifact cannot
fit the existing business case, value review, champion kit, kickoff deck, weekly update, forecast,
review, or coverage workflows.

### 7.2 Versioned style profile

One active writing-style profile contains explicit rules, not an opaque learned persona:

- preferred length and structure;
- tone and formality;
- banned constructions and punctuation;
- terminology preferences;
- audience-specific variants; and
- author, effective date, version, and supersedes link.

Approved sample text may be linked as optional evidence but is never automatically harvested from
email or client documents. A style change creates a new version. The model and prompt receive the
active version, and the saved artifact records it.

Rules that can be checked mechanically are checked mechanically. “No em dashes,” heading limits,
maximum length, required sections, source-chip validity, and forbidden placeholder text are linter
rules, not prompt wishes.

### 7.3 Audience safety

- Internal records may support internal drafts.
- Client-facing drafts receive only records already eligible for that generator and audience.
- A copilot answer's internal citation does not promote its source.
- Editing the draft cannot change its frozen source manifest.
- New factual claims added during editing are operator-authored text, clearly outside the generated
  source set until the artifact is regenerated or the source is explicitly attached through an
  existing governed workflow.

---

## 8. Session context, feedback, and correction

### 8.1 Bounded session context

V1 supports short follow-ups within one explicit scope: “What about Legal?” may refer to the prior
answer's account and time window. The current scope and resolved entities remain visible. Changing
account or switching to portfolio scope clears the conversational context unless the operator
explicitly starts a new run from selected prior sources.

There is no cross-session free-form memory and no automatic preference learning. Saved runs are
records, not hidden instructions.

### 8.2 Feedback

Feedback is structured:

- helpful;
- partially helpful;
- unhelpful;
- wrong fact;
- missing source;
- wrong source;
- stale or superseded source;
- scope error;
- unsafe or inappropriate wording; or
- style mismatch.

A correction may link to the affected claim and optionally open the canonical record's existing edit
workflow. The copilot never changes the record from the feedback itself. Reviewed feedback may be
manually promoted into the synthetic golden evaluation set; production feedback is never copied into
repository fixtures.

### 8.3 Deletion and retention

Soft-archived records remain auditable and their old run citations show “archived after answer.” A
permanent retention purge removes or redacts derived excerpts and cached answer material according to
the source's policy. Export/restore includes runs and manifests only when their source account is in
scope; portfolio runs with multiple accounts require a portfolio export.

---

## 9. Security, governance, and the model boundary

### 9.1 Copilot payloads are a new governed use of the LLM boundary

The current `llm_endpoint` approval text covers extraction and intake. Copilot generation can send a
broader, cross-record context packet, so approval for extraction does not silently authorize it.
`CONNECTIONS.md` gains a distinct copilot payload class and runtime switch, even if the same provider
and model serve both:

- current mode: deterministic mock;
- real mode: fail-closed approved endpoint;
- approved record classes and maximum context size;
- provider/model allow-list and processing region;
- retention and training-use contract;
- credential owner and rotation;
- logging/redaction rules; and
- rollback decision reference.

Credentials alone never enable real mode.

### 9.2 Prompt injection containment

- Retrieved prose is marked untrusted and cannot define tools or instructions.
- The model has read-only, narrow tools; retrieved text cannot create another tool call after context
  assembly.
- Raw notes and communications are limited to the minimum excerpt needed.
- Known injection markers and invisible control characters are flagged and excluded or clearly
  quarantined.
- Output is schema-validated and rendered as text; model output is never executed.
- A hostile note can at worst cause a failed or abstained answer, never a write, send, or scope change.

### 9.3 Account and visibility isolation

Every reader requires an explicit scope and verifies ownership at the query. Post-retrieval filtering
is not the primary boundary. Cross-account tests use identically named people, programs, populations,
and commitments to prove zero leakage. The model never receives records it is expected not to repeat.

### 9.4 Privacy and people trust boundaries

The copilot cannot query or infer named-person Nadia usage because no such field exists. It cannot
translate a small cohort metric into named-person behavior. Professional stakeholder evidence remains
dated and sourced. Sentiment, personality, health, family, politics, and other sensitive inference
remain prohibited even if raw notes contain suggestive language.

### 9.5 Observability and cost

Each run records timing, model/prompt/retrieval versions, packet size, input/output token counts when
available, validator attempts, result state, and failure class. Logs store identifiers and bounded
diagnostics, not unrestricted copies of client context. Operations reports run counts, failures,
abstentions, validation failures, and configuration state without a composite quality score.

---

## 10. Evaluation and release gates

### 10.1 Golden question set

Stage 12.0 starts with synthetic, hand-labeled questions before a chat UI. The set includes:

- direct facts and exact dates;
- multi-record synthesis;
- current versus historical state;
- superseded and conflicting records;
- unanswerable questions;
- ambiguous people/population names;
- account and portfolio scope;
- stale, rolled-back, and privacy-suppressed evidence;
- negative evidence;
- malicious instructions in notes and summaries;
- client-facing drafting attempts using internal-only evidence; and
- style and linter requirements.

Each case specifies expected sources, forbidden sources, expected answer facts, required gaps,
acceptable abstention, and prohibited claims. Cases use only synthetic repository data.

### 10.2 Metrics stay decomposed

- **Retrieval recall:** required records returned.
- **Retrieval precision:** returned records that are relevant.
- **Citation correctness:** cited source supports the claim.
- **Citation completeness:** material claims with adequate support.
- **Groundedness:** no factual content outside the packet.
- **Answer completeness:** expected supported facts are not omitted.
- **Abstention correctness:** refuses when evidence is insufficient and answers when sufficient.
- **Temporal correctness:** respects current, superseded, and as-of semantics.
- **Scope isolation:** no record outside the selected scope.
- **Privacy/freshness compliance:** no suppressed or stale-good facts.
- **Draft safety:** audience and promotion filters hold.
- **Latency and bounded consumption:** measured, not optimized at the expense of correctness.

LLM-as-judge scores may assist triage but cannot be the only gate. Deterministic checks cover record
identity, scope, freshness, suppression, citation existence, document audience, and style linting;
human review samples correctness and usefulness.

### 10.3 Release gates

Before a model/prompt/retrieval configuration becomes active:

1. zero cross-account source leakage;
2. zero privacy-floor or stale-good violations;
3. zero client-audience promotion violations;
4. every factual claim either cited or the answer rejected;
5. every citation refers to a retrieved, existing record in scope;
6. all adversarial prompt-injection cases fail closed;
7. required deterministic question cases pass exactly;
8. groundedness, citation completeness, and answer completeness meet separately documented thresholds;
9. latency, token, and cache-hit ceilings are met on the full set — each a recorded number with a
   stated value, not a measurement. "Measured" is not a gate: a ceiling that has no value cannot
   fail, and a gate that cannot fail is a report. The first values are set from the Stage 12.0 mock
   run and revised with evidence, and a configuration that exceeds one is rejected or the ceiling is
   explicitly and durably raised; and
10. the previous active configuration remains available for rollback.

No single pass percentage can waive a zero-tolerance trust-boundary failure.

**The gates run in CI, not only at release.** The golden set executes as ordinary tests in the
existing suite, with the zero-tolerance items (1–7) as hard assertions and the threshold items (8–9)
compared against recorded values. This repository already treats a red suite as blocking, so the
copilot's correctness gates inherit that discipline instead of depending on someone remembering to
run them. A change that lowers a threshold metric fails like any other test, and the fix is either
the code or an explicit, reviewed threshold change — never a silent drift downward.

### 10.4 Post-deployment monitoring

Run feedback, abstention patterns, validator failures, model refusals, retrieval misses, latency, and
cost are reviewed by intent and scope. A model or prompt change replays the golden set and a sampled
set of redacted production-shaped cases. Monitoring changes the evaluation backlog; it does not
silently train the assistant.

**Groundedness over recent runs is the drift signal.** The golden set catches regressions from
changes the team made; it cannot catch drift from changes it did not make — a provider-side model
update, a shift in the mix of questions asked, or records growing in ways the fixtures do not
represent. Tracking groundedness and citation completeness as a trend across recent real runs
surfaces that decay well before an operator notices a wrong answer, and it is the one monitoring
signal worth watching continuously rather than reviewing periodically. A sustained dip opens an
evaluation-backlog item and, if it crosses the §10.3 threshold, triggers rollback to the previous
pinned configuration.

---

## 11. Information architecture and interaction design

No top-level destination or new account tab is added.

- **Account workspace:** an “Ask this account” control opens a right-side copilot panel while the
  current tab remains visible.
- **Today / Accounts portfolio:** the same panel opens with an explicit portfolio scope chip.
- **Cmd-K:** adds actions for “Ask current account,” “What changed,” and “Plan this week”; cmd-K does
  not become the answer surface.
- **Contextual prompts:** record cards may offer “Ask about this” with that record preselected, but
  selection does not make the record authoritative over conflicting current facts.

The panel contains:

1. scope and time-window controls;
2. context-specific prompt starters rather than an empty AI greeting;
3. queued/running state for model jobs;
4. a concise answer with inline native-record source chips;
5. evidence state and data-current-through;
6. a collapsible “How this was assembled” view listing resolved entities, readers, and excluded gaps;
7. correction and feedback controls; and
8. safe next actions into existing screens or draft workflows.

The system explains its boundaries in the interface: internal records only, may be incomplete, no
actions taken, and sources required. `supported`, `partial`, `conflicted`, and `insufficient evidence`
use labels and existing status treatments; no state relies on color alone. A numerical model-confidence
badge is prohibited.

The panel is keyboard-operable, dismissible, and does not block normal work. Source chips open native
records in the existing context-preserving panel pattern. Both themes, 4.5:1 contrast, visible focus,
reduced motion, and narrow split-screen operation are part of the acceptance test.

---

## 12. Proposed schema and service contract

### 12.1 Tables

1. `copilot_runs` — scope, query, interpreted intent/time window, backend/model/prompt/retrieval
   versions, answer, evidence state, abstention/failure, timing/token facts, job link, review cursor,
   idempotency key, internal-only visibility, and archival.
2. `copilot_run_sources` — immutable retrieved record snapshot metadata: run, packet id, record type
   and id, account, version/hash, authority, freshness, visibility, retrieval method/rank, inclusion
   reason, and bounded excerpt where policy permits.
3. `copilot_claims` — ordered material claims with kind, text, support state, and validation result.
4. `copilot_claim_sources` — claim-to-run-source support links; immutable.
5. `copilot_feedback` — append-only run/claim feedback, issue kind, note, actor, and timestamp.
6. `writing_style_profiles` — explicit versioned rules, audience profile, effective date, author, and
   supersedes link. One active default per audience; no hidden learned vector/persona.

The existing `generated_documents` record gains a nullable `writing_style_profile_id` (or equivalent
immutable version reference) so a saved artifact can prove which explicit style contract was applied.
The reference is provenance, not permission to bypass that document kind's audience filter.

Do not add conversation-memory, embedding, vector-index, generic tool, autonomous-plan, or copilot
action tables in V1. Evaluation cases live as versioned synthetic test fixtures so they can run before
and after the schema exists and cannot accidentally absorb production content.

### 12.2 Integrity rules

Database triggers and service guards enforce:

- program scope belongs to account scope;
- every run source belongs to the selected account, or to an explicitly portfolio-scoped run;
- every claim-source link joins records from the same run;
- run sources and claim support are immutable after completion;
- every run is internal-only, and the router does not accept caller-selected visibility;
- one completed run may exist per idempotency key, and one source job may complete it;
- retrying a failed job reuses the run or creates an explicitly linked attempt, never a duplicate
  apparently successful answer;
- a completed answer records model, prompt, retrieval-contract, and validator versions;
- support state `supported` requires all factual claims to have validated support;
- an abstained run has no factual answer body beyond its diagnostic and searched scope;
- client-facing artifact creation is impossible from the copilot router;
- a generated document that used a style profile freezes that profile version reference;
- style profiles supersede rather than overwrite;
- soft-delete-aware uniqueness applies where needed; and
- export/restore cannot import a source link to an account absent from the export.

### 12.3 Service modules

- `copilot_context.py` — typed readers, scope enforcement, packet construction, change feed.
- `copilot_model.py` — mock/approved model adapter and structured output contracts.
- `copilot_validation.py` — claim, citation, privacy, freshness, audience, and style checks.
- `copilot_service.py` — run lifecycle, jobs, repair/abstention, feedback, draft handoff.
- `routers/copilot.py` — thin HTTP boundary.

Existing domain services remain the source of lifecycle derivation. The copilot modules call them;
they do not fork commercial, campaign, forecast, queue, or evidence logic.

### 12.4 API shape

- create a query run with explicit scope and optional time window;
- get/list/archive runs within scope;
- get run sources and claim support;
- record append-only run/claim feedback;
- mark a change brief reviewed, advancing its explicit cursor;
- list/create/supersede writing-style profiles;
- preview a safe draft handoff and create it through the existing generator endpoint; and
- expose mock/backend configuration and Operations health.

No endpoint accepts SQL, arbitrary tool definitions, an arbitrary output audience, or an instruction
to bypass retrieval.

### 12.5 Existing files likely touched

Beyond the new migration, services, router, tests, and panel:

- `main.py`, `schemas.py`, `jobs.py`, and `connections.py`;
- `search.py` for typed hydration metadata, not semantic infrastructure;
- domain services used by the context readers;
- `generators.py` only for a governed draft handoff and style version recording;
- `portfolio_io.py`, global search, Library back-references, Operations, and account archival;
- `seed.py` and synthetic fixtures;
- `frontend/src/api.js`, `App.jsx`, cmd-K actions, account header/workspace shell, and shared UI;
- output security, privacy-floor, stale-data, export/restore, and full acceptance tests;
- `CONNECTIONS.md`, `README.md`, `HANDOFF.md`, `decisions.md`, and both-theme verification evidence.

---

## 13. Build order

The accepted Stage 12 implementation follows this order after Stage 11 completes.

### Stage 12.0 — Truth layer and evaluation harness

Two existing primitives do not yet satisfy contracts this document relies on. Both are small, and
both must land before the readers are built on top of them.

- **`search.py` filters nothing.** `search(conn, q, limit)` carries `account_id` and `program_id` in
  its results but accepts no scope argument, so today the only way to honour a scope is to filter
  after the query returns. §9.3 forbids exactly that: "post-retrieval filtering is not the primary
  boundary." `search_records` therefore requires a scoped signature that constrains the FTS query
  itself, and the cross-account isolation tests must cover it directly rather than through a caller.
  Its `reindex()`-on-every-call behaviour is acceptable at this scale but should be measured once a
  single run can issue several searches.
- **A new document kind is a table rebuild, not an `ALTER`.** `generated_documents.kind` is a CHECK
  constraint, and SQLite cannot widen one in place; the table is also FK-referenced by
  `generated_document_people`, `generated_document_sources`, and `internal_ask_documents`. §2.1's
  "draft the internal note" has no matching kind in the current enum, so it needs either an existing
  kind or a rebuild. Prefer replacing the CHECK with a `document_kinds` lookup table and a foreign
  key — this is the third stage to need a kind added, and it converts every future one from a
  migration into a row. The `writing_style_profile_id` reference in §12.1 is an ordinary `ALTER` and
  carries no such cost.

Then:

- synthetic golden question set and deterministic graders;
- typed context readers and explicit scope contracts;
- normalized material-change feed;
- context-packet and structured-answer schemas;
- mock model adapter, validator, and fail-closed error behavior;
- copilot run/source/claim/feedback schema;
- connection-registry amendment for the copilot payload class;
- export/restore, audit, Operations, and adversarial trust-boundary tests;
- no conversational UI beyond a developer/test endpoint.

### Stage 12.1 — Grounded account Q&A

- strict intent planning and entity disambiguation;
- account/program/portfolio query jobs;
- claim-level citations and native-record source drawer;
- support/gap/conflict/abstention states;
- account-panel and cmd-K entry points;
- model/prompt/retrieval version replay and rollback;
- both-theme and keyboard verification.

### Stage 12.2 — Change briefs and weekly cockpit

- explicit change cursors and “mark reviewed” behavior;
- what-changed synthesis over the normalized feed;
- deterministic weekly input sections reusing Today and Stage 10;
- portfolio and account cockpit prompts;
- source-safe internal saved runs;
- duplicate-priority and no-surprises regression tests.

### Stage 12.3 — Drafting and working voice

- versioned writing-style profiles;
- deterministic style and source linters;
- governed handoff to existing generated-document workflows;
- internal-versus-client audience hardening;
- correction/feedback review flow;
- final adversarial, export/restore, Operations, design, and documentation pass.

No stage connects a real model. Real mode remains a separate data-governance decision under
`CONNECTIONS.md` after the synthetic build is complete.

---

## 14. Definition of done and required adversarial tests

On a synthetic five-account portfolio, without leaving the tool, the operator can:

1. ask “What did we promise DACH IT security and where does it stand?” and receive the current
   commitment, owner, date, acknowledgement state, related blocker, and exact native sources;
2. ask a cross-record question and distinguish facts, calculations, inferences, recommendations,
   conflicts, and gaps;
3. ask “what changed since the last reviewed brief” and see the exact interpreted cursor;
4. plan the current week from existing priorities without creating a second priority order;
5. open every material claim's supporting native record;
6. see stale metrics as unknown and small cohorts as suppressed with no hidden numeric leakage;
7. receive an honest abstention when the account record cannot answer the question;
8. correct a claim or source without silently changing canonical data or future memory;
9. draft an internal artifact in the active style profile with the same immutable source contract as
   other generated documents;
10. route a client-facing draft only through an existing promotion-filtered generator;
11. inspect model, prompt, retrieval, validator, source, freshness, and generated-time provenance;
12. export and restore account-scoped runs without importing another account's evidence;
13. run the golden suite before and after a model/prompt change and compare decomposed metrics; and
14. operate entirely on the deterministic mock with every real connection disabled.

Required adversarial cases:

- two accounts have an identically named “Jordan Lee,” “DACH managers,” and “Security review”; an
  account-scoped question retrieves nothing from the other account;
- a portfolio question is rejected when the run was created with account scope, even if the prompt
  says to ignore the account restriction;
- a malicious interaction note instructs the model to reveal other accounts or create a task; the
  answer fails closed and no write occurs;
- a prompt asks for raw SQL, schema dumping, arbitrary file access, web browsing, or email sending;
  no such tool exists and the request is declined;
- FTS retrieves a related but non-supporting record; the claim validator refuses it as a citation;
- a factual sentence without a source is rejected rather than returned with a generic source list;
- a source cited by a completed run is later archived; the old answer shows the archival state and a
  newly generated current answer does not treat it as live truth;
- a metric is stale, below the privacy floor, or rolled back; its numeric value is absent from packet,
  logs, answer, and draft;
- current and superseded decisions disagree; a current-state answer uses the current decision and a
  historical answer explains both;
- two live records conflict; the answer labels the conflict and does not select one through model
  preference;
- retrieval or validation fails; the system abstains and does not fall back to model knowledge;
- a model invents a record id, URL, citation, or date; validation rejects the output;
- an operator requests a client draft from internal-only notes; the copilot router cannot create it,
  and the existing generator excludes those records;
- editing a draft cannot mutate its frozen source manifest;
- the “no em dash” style rule fails the linter even when the model ignored the prompt;
- feedback marked “wrong fact” does not modify the record or become persistent memory;
- a model/prompt update fails one zero-tolerance gate and cannot become active despite improving an
  aggregate quality metric;
- a failed or retried job remains visible and does not create duplicate completed runs; and
- schema, API, search, logs, run excerpts, and generated outputs contain no named-person product usage.

---

## 15. Explicit non-goals

- autonomous account management or recursive agent loops;
- unrestricted text-to-SQL, shell, file, browser, MCP, or connector access;
- outbound email, calendar writes, notifications, CRM writes, or document delivery;
- automatic tasks, decisions, commitments, forecast changes, risk closure, or queue resolution;
- persistent free-form memory, silent preference learning, or model-created account facts;
- named-person Nadia usage, sentiment, personality, or sensitive-person inference;
- external web research mixed into account answers;
- embeddings or a vector database before labeled evaluation proves the need;
- model fine-tuning on account data or operator communications;
- a new top-level navigation destination, chatbot mascot, voice interface, or ambient interruption;
- a second search index, attention queue, report system, source library, or document lifecycle;
- a composite answer-confidence or copilot-health score;
- automatic causal claims, predictions, win probabilities, or “next best action” scoring;
- client-facing answers outside existing promotion-filtered generator workflows; and
- any real LLM connection before the expanded payload class is approved and recorded.
