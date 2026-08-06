# Account Path — comprehensive review (Slices 1–7 + Stage 15 foundation)

**Status:** point-in-time review. **Not an authority and not a status source** — `ACCOUNT-PATH-SPEC.md`
is the authority and `HANDOFF.md` carries current state. Every count and file reference below is as
of the date given; the suites have grown since.
**Reviewer:** independent read of the uncommitted work on `punch-4-cleanup`
**Date:** 2026-08-05
**Supersedes:** the two incremental reports delivered earlier in this session (Slices 1–6, then Slice 7).

---

## 1. Scope and method

Under review is the whole additive build sitting uncommitted on `punch-4-cleanup`: `RELATIONSHIP-READINESS-SPEC.md` (Stage 15, RR-0 through RR-2) and `ACCOUNT-PATH-SPEC.md` Slices 1–7. Roughly 6,000 lines of new Python, ten migrations (0041–0050), and the frontend surfaces that render them.

Method was source reading against the spec's own stated invariants, plus running both suites, plus forming falsifiable hypotheses about where the design could have gone wrong and then checking each one in the code. The disproved hypotheses are recorded in §5 alongside the confirmed ones, because a review that only lists what it found tells you nothing about what it looked for.

This review changed no files.

### Verification state

| Suite | Command | Result |
|---|---|---|
| Backend | `uv run --with pytest --with eval_type_backport pytest -q` | **660 passed, 0 failed** |
| Frontend | `node --test "src/*.test.js"` | **138 passed, 0 failed** |

Both green as of the final run. The suite moved during the review (3 failures → 1 → 0) because the implementing session was still working; every finding below was re-verified against the current working tree immediately before writing this.

---

## 2. Headline

**The architecture is right, and it is right for the hard reason rather than the easy one.**

The central discipline — readiness and the path are *query-time projections, never stored state* — is not merely asserted in comments. It is enforced three separate ways: schema-introspection tests that walk table names and fail on a forbidden column, a Python-side `(intent, target_type)` allowlist that sits beside the write path instead of in a SQL `CHECK` where it would rot, and triggers that hold the client-visibility invariant against a hand-typed `UPDATE` as well as against the endpoint. Migration 0048 is the strongest single signal in the diff: 0047 added `generated_documents.source_manifest_json`, the author found while wiring the writer that `generated_document_sources` had held exactly that since 0026, and 0048 *drops the column* with a comment naming the failure it would have been ("a second store of the same fact, free to disagree with the first — D-139, D-143, D-149"). Recognising your own duplicate source of truth one slice after writing it, and removing it rather than leaving it unused, is the behaviour the whole spec is trying to produce.

The trust boundaries hold. I found no table, column, or field anywhere in migrations 0041–0050 for a named individual's product usage. Client-facing output is built from promoted records rather than built whole and filtered late. Telemetry carries no person identifier and structurally cannot carry free text.

**The defects are all one shape.** Every material finding below is an instance of *honest uncertainty collapsing into a confident state* — a failed adapter reported as "nothing is recorded", an unreadable condition reported as "outstanding", a field named `missing_or_stale_sources` that never checks staleness, a disappeared row counted as a completion, two rankings averaged into one funnel. This is precisely the failure mode the specs spend most of their prose refusing, which is what makes these worth fixing as a set: each one is a place where the guard was written and then bypassed by an input the author did not have in view.

---

## 3. Findings

Severity is about what a reader of the app would wrongly believe, not about code aesthetics.

### 3.1 [High] An unreadable gate condition is reported as `blocked`

**`backend/app/phase_readiness.py:240–243`**

`coverage_failures` accumulates two different kinds of string from two different places:

- `readiness.evaluate`'s `coverage.failed_evaluators` — bare **evaluator keys** (`readiness.py:2112`).
- The archived-plan-instance branch — `f"gate_requirement:{row['plan_instance_id']}"` (`phase_readiness.py:118`).

The classifier only understands the first kind:

```python
unreadable_keys = set(coverage_failures)
unreadable = {r["requirement_key"] for r in unmet
              if r["state"] == "unknown" and r.get("evaluator_key") in unreadable_keys}
determined = [r for r in unmet if r["requirement_key"] not in unreadable]
```

The row that branch builds carries `state: None` (not `"unknown"`), `evaluator_key: None`, and `requirement_key: None` (`phase_readiness.py:122–129`). It fails both conjuncts, lands in `determined`, and the verdict at line 253 reports:

> **blocked** — "1 required condition outstanding."

That sentence claims the condition was read and found unsatisfied. It was never read at all. The `insufficient_data` branch at line 265 — written for exactly this case, with the comment "collapsing it into `ready` would be the carried-forward-good-state failure" — is unreachable whenever the only coverage failure is an archived instance. Line 263 (`if unreadable: parts.append(...)`) is dead code for that input.

**Repro:** link a plan instance to a phase gate, archive the instance, read gate readiness. Expected `insufficient_data`; actual `blocked`.

**Secondary issue in the same three lines:** `unreadable` is a set of `requirement_key`s and `determined` filters by key, so two gates linking two different instances of the same requirement key are not separable — excluding one excludes both. Keying on `plan_instance_id` or `link_id` would be correct.

**Suggested fix:** classify on the row rather than reconstructing it — the branch already knows it produced an unreadable row (`available: False`). `unreadable = [r for r in unmet if not r["available"] or (r["state"] == "unknown" and r.get("evaluator_key") in unreadable_keys)]`, and filter `determined` by identity rather than by requirement key.

---

### 3.2 [Medium] A failed `programs` adapter reports "no program is recorded"

**`backend/app/execution_path.py:963–968`**

```python
if not ctx.programs:
    return {"variant": "insufficient_plan_data",
            "message": "No program, phase, gate, or milestone is recorded for this account.",
            "requirement": None}
```

The adapter harness (`execution_path.py:1062–1076`) catches a failing source, appends it to `coverage.omitted_sources`, and leaves `ctx.programs == []`. So a transient failure in the programs adapter renders a positive factual claim about the account's records — the operator is told nothing is planned when the truth is that the planner could not be read.

The ordering compounds it: `not ctx.programs` is tested first, so the `coverage_incomplete` variant at line 978 ("Some sources could not be read, so caught-up cannot be claimed") is unreachable for the one failure that most needs it.

This is the same rule §11's coverage design gets right elsewhere — `coverage.omitted_sources` names the adapter and canonical work is never suppressed. The empty state is the one place that reads `[]` as a fact rather than as an absence of information.

**Suggested fix:** test `coverage_ok` before `not ctx.programs`, or make the first branch conditional on `coverage_ok`.

---

### 3.3 [Medium] `missing_or_stale_sources` never checks staleness

**`backend/app/shared_plan.py:483–486`**

```python
"missing_or_stale_sources": ([] if current_through else
                             ["no sourced items have been shared to this plan"]),
```

The field has exactly two possible values, and neither is produced by comparing a source to a freshness window. `current_through` is `min(dates)` over whatever was collected; if any source has a date, the list is empty and the artifact tells the customer nothing is stale.

This matters more here than it would elsewhere because this is the **client-facing** artifact and Slice 6's whole thesis is withhold-with-a-stated-reason rather than downgrade. The field name is a promise the code does not keep, and the promise is being made to a customer. `_requirement_status` does honour the rule (a stale `met` is withheld, not shown `Complete`) — this stamp is the one place the freshness discipline is nominal.

**Suggested fix:** either compute it (compare each source's date against the requirement/record freshness threshold already available to `_requirement_status`), or rename the field to `data_current_through_note` so it stops claiming a check that is not happening.

---

### 3.4 [Medium] The promotion preview and the export disagree on scope

**`backend/app/shared_plan.py:686–691`**

```python
promoted_actions = {
    r["id"] for r in _rows(conn, "SELECT id FROM tasks WHERE client_visible = 1 AND archived = 0")
} | {
    r["id"] for r in _rows(conn, "SELECT id FROM commitments WHERE client_visible = 1 AND archived = 0")
}
```

Portfolio-wide, no account filter. `_project` scopes to the account's programs. The spec's stated reason for the preview existing is that it *runs the same projection as the export, so it cannot drift from it* (D-151…D-155). Here it does not: a requirement whose supporting action is a promoted task on a **different account** can show a source in the preview that the export will not produce.

Nothing leaks into a customer artifact — `_project` still scopes correctly, so the export is right and the preview is wrong. But the preview is what an operator reads before deciding to promote, and its whole value is being a faithful dry run.

**Suggested fix:** pass the account through and scope both selects, matching `_project`.

---

### 3.5 [Medium] The funnel averages across ranking rule versions

**`backend/app/telemetry.py:257–302`**

Every count in `funnel()` — `views`, `opened`, `completed`, `snoozed`, `offered`, `by_reason`, `coverage_failures` — is computed with no `GROUP BY` on and no filter by `ranking_rule_version`. The `rule_versions` block in the response is disclosure only.

D-156…D-161 is explicit that *every event carries its ranking rule version so a funnel cannot average two orderings*. The column is faithfully recorded on every event; the reader then ignores it. Flip `VALENCE_OS_RANKING_RULES` for a week and the funnel silently blends the before and after into one open rate — which is exactly the comparison the flag exists to make possible and exactly the one this makes unreadable.

Compounding it: **`rule_versions` is never rendered.** `frontend/src/views/Operations.jsx:212–300` renders the funnel numbers and the §17.5 caveat (correctly, at line 269) but no version disclosure anywhere, so the operator has no on-screen signal that the numbers span two orderings.

**Suggested fix:** group the counts by `ranking_rule_version` and return per-version blocks, or accept a `ranking_rule_version` filter parameter. Render the versions present beside the numbers either way.

---

### 3.6 [Medium] `next_move_completed` measures disappearance, not completion

**`frontend/src/telemetry.js:237–246`**

`completedMove` is the one deriver that infers rather than reads, and its docstring says so and names three excluded cases (snoozed, wrong scope, incomplete coverage) — all three are genuinely handled, which is more care than most instrumentation gets.

The residual is still wrong for a fourth case the docstring does not name. A row can vanish from a `coverage: complete` response for reasons that are not a completion:

- the task was **cancelled** (`shared_plan.py:156` maps `cancelled` → `not_applicable`, so the domain does distinguish it — the event does not);
- the task was **archived**;
- the row aged out of the band window or the plan instance was archived.

Each is counted as `next_move_completed`. In a funnel whose stated purpose is "was the recommendation acted on", a cancellation counted as an action is the metric arguing for its own success. The §17.5 caveat renders on screen, which limits the damage, but the caveat is about clicks not being quality — it does not say the completion count includes cancellations.

**Suggested fix:** the cheapest honest fix is to rename the event and the derived properties to `next_move_left_the_list` with a `disappearance` framing, and let the caveat carry it. The more useful fix is to have the path response echo, for a row that left, why it left — the server already knows.

---

### 3.7 [Question] Measurement is on by default while every other class fails closed

**`backend/migrations/0050_product_events.sql`** seeds `product_telemetry_settings` with `enabled = 1`.

Registering the sink in `CONNECTIONS.md` as `product_telemetry_sink` with `gate_status: local` was the right call and the reasoning in the spec is sound — pointing it at a vendor would be a data-handling conversation, not a config change. The events genuinely contain no person id and no free text, and `record()` genuinely cannot raise.

The question is consistency rather than correctness: every other class in the registry fails closed and requires an affirmative flip. This one collects from first boot. I do not think that is wrong — it never leaves the installation and `set_settings(enabled=False)` deletes what was collected, which is a stronger guarantee than most opt-outs offer. But it is the only default-on entry in the registry, and if that was a deliberate call it deserves a line in `decisions.md` saying so, because the next person to read `CONNECTIONS.md` will read the pattern and not the exception.

---

### 3.8 [Low] `compare_rule_versions` compares positions, not orderings

**`backend/app/execution_path.py:1231–1268`**

The comparison reports positional shifts and only inspects `you_own`. Two consequences:

- One insertion near the top shifts every row below it and reports as widespread reordering, when logically nothing changed relative order.
- `waiting_on_customer` and `next_move` are not compared at all, and `next_move` is the output the ranking exists to produce.

D-161's rule — *a comparison that reports no reordering is reported honestly rather than manufactured by seeding around it* — is respected, which is the harder half. This is the easier half done loosely.

**Suggested fix:** compare pairwise order (count of inverted pairs) rather than index deltas, and include `next_move` identity in the diff.

---

### 3.9 [Low] A milestone with work underway reads `not_started` to the customer

**`backend/app/shared_plan.py:160–170`**

```python
if any(a["client_status"] == "complete" for a in advancing):
    return "in_progress"
return "not_started"
```

A milestone with three promoted, in-progress advancing actions and none yet complete renders as `not_started` on the customer-facing plan. The function directly above documents why `not_started` is unreachable for an *action* ("`open` does not distinguish untouched from underway, and inventing that distinction for a customer-facing plan would be a guess") — the same reasoning applies here and reaches the opposite conclusion: `not_started` in the presence of visible in-progress work is itself the guess.

**Suggested fix:** `if advancing: return "in_progress"` before the fallback, or return `not_started` only when `not advancing`.

---

### 3.10 [Low] An unrecognized status renders verbatim on the client-facing surface

**`frontend/src/sharedPlan.js`** — `statusChip` falls through to `String(status)`.

Slice 6 is careful everywhere else that an unrecognized readiness state falls through to a refusal *naming* it rather than being softened. This is the mirror-image slip on the view side: an unmapped internal enum value renders as raw text to a customer. Small, but it is on the one surface where a leaked internal word is a real problem.

**Suggested fix:** fall through to a neutral label plus the withheld treatment, not to the raw string.

---

### 3.11 Smaller items

| | Location | Note |
|---|---|---|
| a | `backend/app/proposals.py` | `DEFERRED_INTENTS = {"link", "close"}` carries the reason "until the typed relationship and governed closure contracts of Account Path Slice 5 exist". Slice 5 exists (`path_links.py`, migration 0046). The deferral may still be right, but the stated reason is now false and will mislead the next reader. |
| b | `backend/app/telemetry.py` | `purge_expired()` runs on every write, and `product_events` has no `occurred_at`-leading index. Fine at a few thousand rows; it is a full scan per event. |
| c | `backend/app/telemetry.py:278–281` | `offered` matches `json_extract(...,'$.has_next_move')=1`, which depends on how `json.dumps` spells `True`. It works, but it is coupled to a serialization detail rather than to the value. |
| d | `backend/app/telemetry.py:175` | `session_id or "local-session"` — a missing session silently joins a shared bucket. Harmless, but it makes "how many sessions" unanswerable rather than obviously incomplete. |
| e | `frontend/src/measure.js` | Explicitly not unit-tested, and the reasoning (everything with a rule in it lives in the pure `telemetry.js`) is sound. `takeCompletedMove`'s take-once semantics and the module-level `openedMove` are the residual untested logic. |
| f | `backend/app/phase_readiness.py:118` | `coverage_failures` mixes two string vocabularies (bare evaluator keys and `gate_requirement:<id>`) in one list, which is the proximate cause of 3.1. Two lists, or tagged entries, would make the classifier's bug impossible to write. |

---

## 4. The cross-cutting pattern

Findings 3.1, 3.2, 3.3, 3.5, and 3.6 are the same defect wearing five costumes:

| Truth | Reported as |
|---|---|
| the adapter failed | "no program is recorded" |
| the condition could not be read | "1 required condition outstanding" |
| no source was checked for staleness | "no stale sources" |
| two orderings were in play | one open rate |
| the row disappeared | "completed" |

In every case the guard exists, is documented, and is bypassed by an input that was not in view when the guard was written. That is a good sign about the codebase — the author knows exactly what the failure looks like, which is why the fixes are all small — and a bad sign about the specific seams: each bug lives at a boundary where one module's vocabulary is reconstructed by another (`coverage_failures` re-parsed as evaluator keys, `ctx.programs == []` re-read as a fact, a row's absence re-read as a closure).

**The generalizable fix is to stop reconstructing.** Where a producer already knows the distinction, carry it: the archived-instance branch already sets `available: False`; the adapter harness already knows `coverage_ok`; the path response already knows why a row left. Three of the five findings close by reading the flag that already exists instead of re-deriving it.

---

## 5. What holds — including what I tried to break

The findings above are the exception. The bulk of this build is correct, and several of the things most likely to be wrong turned out to be right for stated reasons.

### Hypotheses I formed and disproved

| Suspected | Actual |
|---|---|
| `phase_readiness` reads `coverage_failures` from pillars, which `readiness.evaluate` has already popped | Deliberately reads `result["coverage"]["failed_evaluators"]` instead, with the reasoning documented at the call site (`phase_readiness.py:170–174`) |
| `merged_plan` at account scope cannot resolve program-scoped instances | `evaluate(account, None)` populates `programs_out` per program; resolution is correct |
| Telemetry `completedMove` false-positives from a server-side list cap | `you_own` is uncapped server-side (`execution_path.py:1165`) |
| `tasks.program_id` nullable → preview/export divergence | `NOT NULL` since migration 0002 |
| Migrations 0041–0050 store a readiness state somewhere | Grepped every one for `state`/`status`/`met`/`freshness`/`coverage`/`applicability` columns. The only `status` columns are `readiness_plans.status` (plan lifecycle, not readiness) and the two proposal-status columns in 0043, both with explicit CHECK vocabularies. **The no-stored-state rule holds across all ten migrations.** |

### Slice by slice

**Stage 15 / RR-0–RR-2 (readiness, proposals).** Four independent axes are carried verbatim end to end; I found no place where one is restated in another's vocabulary. Unknown evaluator keys fail closed into `coverage: partial` rather than dropping a pillar. `proposals.py` keeps `intent` and `target_type` separate with the allowlist in Python beside the write path. `proposal_read.py` composes rather than copies — two lists, two status vocabularies, two command sets, counts derived on every call — and its docstring names why grouping is by *run* rather than by interaction (a retranscription is a different source). `proposal_review.py` gets the sharpest call in the slice right: `already_resolved` scopes to account **and** program with a paragraph explaining that account-only scoping would close program B's proposal against program A's record, and that the survivable direction is letting a genuine duplicate reach a human. `_scope_clause` returning `None` — skipping the check rather than running an unscoped query — is the correct fail-closed choice.

**Slice 1–2 (projection, ranking, coverage).** Eight deterministic bands computed once on the server. Adapter isolation is real: `run(name, fn)` per-adapter try/except, failures named in `coverage.omitted_sources`, canonical work never suppressed. `snooze_key: null` with `Open source` offered when no valid three-part key exists. `accountPath.js:coverageNotice` now implements D-160 — a `complete` response with warnings reports the snoozed/subtractive case rather than returning null, so a withheld row is always stated.

**Slice 3 (playbooks, plans, checklist compatibility).** `checklist_compatibility.py` is a highlight. Exact `template_key` matching only, with the reason stated (a checklist label and a requirement label can read almost identically while meaning different things). A `done` tick lands as `recorded_complete` and moves no readiness state. An `na` item becomes a *proposed* exception rather than an applied one, because "a migration is not an operator". `dry_run` runs the same computation rather than a second code path. Two items mapping to one requirement in one scope is reported as `ambiguous` rather than silently overwriting. And `evidence_missing` deliberately surfaces the gap between a carried tick and what readiness actually reads — publishing your own migration's disagreement with the records is the opposite of the usual instinct.

**Slice 5 (typed links, evidence, closure).** `path_links.py` is the strongest module in the build. Action links and evidence links are two tables rather than one with a flag, because "a single table would make 'is this done?' a matter of remembering which flag to read". No confidence column anywhere — a link was accepted or it does not exist. An open Task is refused as evidence and the error text points the operator at the `advances` link. A requirement cannot cite its own `suggested_action`. Evidence of a kind the definition does not accept is *downgraded* to `supporting: false`, not refused. Retraction is deliberately not archival, so a withdrawn claim stays visible as a withdrawn claim. `_check_scope` runs both directions on both sides. `requirement_action_index` counts only `advances` for the §13.6 dedupe, with the reason stated. `close_with_successor` carries links forward as `follow_up_for` and returns an explicit `requirement_note` saying closing an action does not record evidence. Migration 0046's four link tables carry no `state`/`status`/`met`/`freshness`/`coverage` column — verified by grep.

**Slice 6 (shared plan).** `_project` returns structurally separate `artifact` and `diagnostics` documents; the artifact is built from promoted records rather than built whole and filtered late. Column allowlists (`_MILESTONE_COLS`, `_TASK_COLS`, `_PLAN_CLIENT_COLS`) constrain what can reach a client surface at the query, not at the render. `_requirement_status` withholds with a stated reason rather than downgrading — a stale `met` is withheld, a `conflicted` reading is never resolved in the customer's favour, an unrecognized state falls through to a refusal naming it. Refusal clauses are authored server-side with the sentence frame in `sharedPlan.js:withheldSentence`. Migration 0047's triggers hold the client-label and promoter invariant against a hand-typed `UPDATE`, and the cross-account owner check closes the D-126 leak class. And, again, 0048 removing 0047's own duplicate store.

**Slice 7 (measurement).** Sixteen enumerated events with per-event property allowlists. The slug rule (`^[a-z0-9][a-z0-9_.:-]{0,63}$`) excludes free text *structurally*; `SENSITIVE_KEYS` exists only to name the trust boundary in the rejection message, which is the right relationship between the two. Migration 0050's three CHECKs (`json_valid`, `length <= 512`, `instr(properties_json,'@') = 0`) are a bypass backstop for a hand-typed insert. `test_no_domain_module_reads_product_events` enforces the isolation by test rather than by convention. `record()` genuinely cannot raise. Disabling deletes what was collected. `currentPhase` refuses to stamp a phase on a multi-program account, for the same reason the path refuses to attribute a phase to a Task. `telemetry.test.js` feeds the derivers bodies full of titles and person names and asserts none survives — pointing the tests at the exact place a leak would occur. The candidate ruleset ships non-live and is comparable but not selectable from the UI.

**Email threading (§14.8).** `email_thread.py` gets the non-obvious half right and explains why the obvious half cannot work: deduplicating *proposals* after the fact cannot fix repeated thread history, because two readings of one sentence in different messages have different source references, locators, and span offsets, and therefore correctly fingerprint apart. The fix has to be at material selection. `normalize_subject` is marked display-only with the reason (two unrelated "Re: Quick question" messages are not one thread); `thread_key` uses the `References` root because it is the one id every message carries. A wholly-quoted body produces no run at all rather than an empty one.

### Documentation quality

Worth saying plainly: the module docstrings in this build are the best-executed part of it. They consistently record *the design that was rejected and why*, not what the code does. `path_links.py`'s four rules, `proposal_review.py`'s enforcement-vs-suggestion split, `email_thread.py`'s explanation of why fingerprinting cannot solve threading, migration 0048's admission of its own predecessor's mistake — these are the artifacts that will keep the invariants alive after the specs are stale. Preserve that standard.

---

## 6. What I did not read

Stated so the coverage of this review is legible:

- **Read in full:** `path_links.py`, `shared_plan.py`, `phase_readiness.py`, `checklist_compatibility.py`, `proposal_read.py`, `proposal_review.py`, `proposals.py`, `email_thread.py`, `telemetry.py`, `routers/telemetry.py`, `telemetry.js`, `measure.js`, `accountPath.js`, `sharedPlan.js`, migrations 0047/0048/0049/0050.
- **Read in part:** `execution_path.py` (bands, empty state, adapter harness, ranking comparison — not the full candidate-assembly path), `playbooks.py` (readings, `merged_plan` — not the full instantiate/upgrade path), `readiness.py` (~600 of 2,160 lines: `evaluate()`, coverage assembly, pillar retirement — **not the individual evaluators**).
- **Structurally checked only:** migrations 0041–0046 (grepped for forbidden columns and inspected triggers; not read line by line).
- **Not read:** the JSX views other than the `Operations.jsx` funnel section and the Account Path sections. **No screenshots were taken, and neither theme was visually verified** — the design-guide requirement that a change working in only one theme is not done has not been checked by this review.
- **Not exercised:** no manual UI walkthrough, and no seed-data run of the shared-plan export against a populated account.

The evaluator bodies in `readiness.py` and the both-theme visual check are the two largest remaining gaps. The evaluators are where a fifth instance of the §4 pattern would most plausibly hide.

---

## 7. Suggested order

1. **3.1** — a wrong `blocked` verdict on a governance gate is the one finding that could drive a real decision the wrong way.
2. **3.2** — same class, one line, and it restores an unreachable branch.
3. **3.4**, **3.9**, **3.10** — small, and all three are on the client-facing path where the cost of being wrong is external.
4. **3.3** — decide: implement the check or rename the field. Either is fine; the current state is the only one that is not.
5. **3.5 / 3.6** — measurement honesty. Neither affects operator decisions today, and both get harder to fix once there is history to reinterpret.
6. **3.7** — a `decisions.md` line, not a code change.
7. **3.8** and **3.11** — cleanup.

None of these is architectural. The build is sound; these are seams.
