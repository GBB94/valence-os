# HANDOFF — Valence OS

_Written 2026-07-29 for a fresh session with no conversation history and kept current. Read this, then `CLAUDE.md`, then the active specs named there. It tells you what exists, what was deliberately left out, what is gated, how to run it, and the lines you must not cross._

## VISIBILITY-SPEC Slice 1 — decay on persisted copilot runs (2026-08-06, D-251…D-258)

**Read D-251 before you build anything else from this spec.** `VISIBILITY-SPEC.md` is *not* named in
`CLAUDE.md`'s authority chain. Slice 1 was built on Zach's instruction "continue building with what's
specc'ed out" after everything in the named chain was finished — that is an instruction, not a
formal naming, and the difference matters under D-239. **Slices 2–6 are not started.** Slice 6 is the
one with a migration and stays held for the schema conversation regardless.

`copilot_runs` is the only table that persists generated prose and re-opens it by id, so it is the
only place a February answer can render in August at full weight. Past the evidence window for its
scope, a completed run's body is withheld and the server authors the reason. **No migration.**

New or changed: `ANSWER_WINDOW_DAYS`, `_age_days`, `answer_freshness`, `detail(..., reveal=)`, and
the `list_runs` projection in `app/copilot_service.py`; the `reveal` query param in
`routers/copilot.py`; `api.copilotRun(id, {reveal})`; new `src/copilotFreshness.js`; the withheld
branch in `views/CopilotPanel.jsx`; `.copilot-withheld` in `index.css`. New suites:
`tests/test_visibility_run_decay.py` (12), `src/copilotFreshness.test.js` (7). **807 backend, 263
frontend** (was 795 / 256), lint exit 0, clean build.

What you must not undo:

- **Nothing is stored.** `freshness` is computed on every read from `generated_at` and `scope_type`.
  `test_this_slice_stores_nothing` asserts no freshness column on `copilot_runs` and no freshness or
  decay table. A cached "still current" would disagree with the date, silently and in the flattering
  direction.
- **Withheld, not dimmed, and `withheld` ≠ `revealed`.** Revealing re-reads the same row; it starts
  no run and clears no flag. If you ever find yourself rendering `answer_markdown` behind opacity
  instead of behind the control, that is the failure this slice exists to prevent.
- **The claims and sources block is never withheld.** It is assembled before the withholding, in both
  `detail` and the reveal path. The evidence is what makes the refusal checkable.
- **The refusal sentence is the server's, framed by `sharedPlan.withheldSentence`.** Do not add a
  second frame in `copilotFreshness.js`; a frontend test asserts identity against that function.
- **`draft-preview` and `draft` 409 on a withheld run.** They previously would have taken
  `answer_markdown=None` and produced a hollow document. The 409 reuses the server's clause verbatim.
- **The scope windows are 14 / 30 / 45 and the number rides on the payload.** The sentence names the
  window; it does not refer to "the threshold".

## The account drop zone, Slice 4 — milestones, and §17's six events (2026-08-06, D-242…D-247)

The last slice of `ACCOUNT-INTAKE-SPEC.md`. All four are now built. It adds the second proposal
route — `("create", "milestone")` — and the measurement §17 deferred. **No migration**, which makes
§19's "with its own migration" estimate stale rather than conservative; both specs are corrected.

New or changed: `PROPOSAL_KINDS` / `KIND_PAIRS` / `find_date` / `screen_undraftable` and the
appended-last cue rule in `app/extractor.py`; `_TARGET_SCHEMA`, `_STAGE5_TARGETS`, and the
`target_type`-based dispatch in `routers/ai.py`; `milestone` in four maps in `app/proposal_review.py`;
six events in `app/telemetry.py`; `dropEvent` + `clientRefusalCode` in `src/intakeDrop.js`; the
`TEXT_FIELD` map and the `create:milestone` date requirement in `src/proposalReview.js`; tracking
calls in `AccountIntakeDrop.jsx`. Suites: **795 backend, 256 frontend, clean build** (was 767 / 245).

What you must not undo:

- **`mutation_type` is NULL on a milestone proposal, and that is the design.** Migration 0043 made
  the column nullable precisely so a normalized pair with no legacy name could be stored, and the
  0043 CHECK still lists exactly nine values — a test asserts `"milestone"` appears nowhere in the
  `extraction_proposals` DDL. Every dispatch reads `target_type`; do not reintroduce a `create_`
  prefix strip, which raises on the None. `_persist_run` accepts either vocabulary and translates in
  **one** place, because five tests in `test_readiness_review_fixes.py` still call it with legacy
  dicts and a second translation site is how the two would drift.
- **A milestone proposal may carry a name and a date and nothing else.** `at_risk`, `completed_on`,
  `completion_note`, and `completed` are rejected at validation *and* at accept time. A proposal
  that could assert completion would be a document asserting a state.
- **Neither the date nor the program is ever guessed.** `find_date` takes ISO, `1 October 2026`, and
  `October 1, 2026` — no slash forms, and `None` when a sentence carries two candidates. A relative
  phrase is not a date. A missing program is a 422 from `MilestoneCreate`, the same one every other
  execution target gets. Each refusal is a server-authored sentence in its own coverage key.
- **The six drop events carry no filename, kind, size, or count.** A filename is document content by
  another name. Only `drop_refused` has a property, and it is the drop's own `outcome` enum.
  Client-side refusals get two codes, not three: an oversized file is *sent* so the server can author
  that refusal, and it returns as `rejected_kind` — a third code would double-count it.

## The account drop zone, Slice 3 — grounding, accept-all, duplicates (2026-08-06, D-226…D-238)

The review-speed slice, and it is **not** scoped to dropped material: an extraction started from an
interaction gets the same split view and the same batch key. `ACCOUNT-INTAKE-SPEC.md` §11.2, §11.4,
and §12 are the authority; all three are marked built. **No migration** —
`intake_drops.duplicate_of_id` already existed from 0052 and was simply never written.

New or changed: `app/proposal_grounding.py` (new), the §12 duplicate check and `prior_drop` in
`app/intake_drop.py`, `run_id` + `scope` on `proposal_read.proposed_updates`, `_accept_blocker` and
`POST /api/extraction/runs/{run_id}/accept-all` in `routers/ai.py`, `bulk` on `proposal_accepted` in
`app/telemetry.py`, `frontend/src/proposalGrounding.js` (new), `acceptAllState` /
`acceptAllBlocker` in `src/proposalReview.js`, the split view and bulk bar in `ProposalReview.jsx`,
and the duplicate line in `AccountIntakeDrop.jsx`. Suites: **767 backend, 245 frontend, clean
build** (was 742 / 229).

What you must not undo:

- **The marked passage is byte-identical to the span, or nothing is marked.** There are two match
  strategies — exact, then whitespace-normalized with a per-character map back to the original
  offsets — and no third. No similarity threshold, ever: a highlight on nearly-the-quote presents
  different words as the ones the draft cited, and that is worse than no highlight. `segmentsOf`
  falls back to one unmarked segment on any malformed location for the same reason.
- **A run has a retained document iff a drop points at it.** `interactions.raw_notes` is sitting
  right there and is not a fallback — the run's `content_hash` is over the text handed to the
  extractor, so nothing links the two, and `raw_notes` is mutable afterwards. Presenting it would be
  a fabricated provenance claim. `never_captured` and `deleted` are separate states with separate
  sentences, and neither removes the span.
- **Every grounding sentence is authored on the server.** `proposalGrounding.js` selects and orders;
  it never writes one. The test asserts note identity, not a substring match (D-153).
- **Duplicate detection runs after `screen()` and before any parse.** Move it earlier and a
  re-dropped PDF is told "you dropped this before" instead of "paste the text" — true, useless, and
  it hides the working path. Move it later and the whole pipeline runs to produce a second copy of
  records that already exist. `rejected_kind` and `parse_failed` are deliberately not duplicable.
- **A duplicate names the earlier drop and offers its drafts.** Silent dedupe and a failed upload are
  indistinguishable from the operator's chair. It carries the earlier `comm_message_id` but **not**
  its `extraction_run_id` — reporting "drafted 6 updates" twice is the double count §12 prevents —
  and it stores **no snapshot**, because a second copy would make §5's deletion not a deletion.
- **`prior_drop` is earliest, live, account-scoped, tie-broken on `rowid`.** Not `id`: timestamps are
  second-resolution and ids are random hex, so ordering by id picks an arbitrary drop from that
  second and the "earliest" guarantee that keeps the chain flat silently stops holding.
- **Accept-all is all-or-nothing and scoped to a run.** `_accept_blocker` is a dry run of the accept
  path in its own order, writing nothing; everything is checked before anything is written. A batch
  that fails on its fourth item has already created three records nobody chose. There is no
  account-wide variant, and the route table test says so.
- **"Every item `proposed`" is read over the run's *open* items.** Reading it over all items disables
  the batch permanently after one rejection — a rule that punishes reviewing.
- **`run_id` is a filter on the one queue.** Same composition, same commands, and what it withholds
  (other runs' proposals, all manual capture) is counted and stated. A narrowed queue that looked
  like an empty account would be the worst version of D-160's rule.
- **`bulk` is a property on `proposal_accepted`, never its own event.** Each batch item genuinely is
  an acceptance; a separate event leaves the funnel undercounting by however much the batch is used.
- **`a` lives in the existing keydown handler.** A second `window` listener is how two handlers start
  disagreeing about focus — the §11.4 note about `j`/`k` applies to this key too.
- **The citation mark carries no hue.** Neutral surface lift + left rule + primary-ink weight. A
  status hue would read as "verified"; the accent belongs to interaction.

Two bugs in existing code that these tests found, both now fixed: `proposed_updates` rebound its own
`run_id` parameter as a loop variable (so an *unfiltered* read reported itself narrowed and dropped
manual capture), and `prior_drop`'s `id` tie-break above.

**The screenshot pair is captured (2026-08-06, D-248…D-250).** Eleven images in
`design-screenshots/stage-16/` — drop zone, drag-over, review slide-over, duplicate receipt, and a
degraded citation, each in both themes, plus a 620px narrow shot.

This paragraph previously said capture was blocked at the environment's capture layer. **It was
not.** `browser_open_local_preview` cannot be screenshotted, but `browser_open_session` with
`headless: true` captures fine; one failing code path had been generalized into a fact about the
environment, and that reading is what kept the pair unwritten. If you hit *"Current display surface
not available for capture"*, switch tools rather than recording a blocker.

Capturing found two rendering defects that the suite, the token audit, and DOM inspection had all
passed over — `Accept all 3` silently clipped to `Accept all`, and the grounding split never stacked
inside the 480px slide-over, rendering a `sha256:` hash one character per line. Both fixed;
`design-screenshots/stage-16/VERIFICATION.md` has the measurements, the container-query rationale,
and the two states still uncaptured (`never_captured` and unlocatable citations). Contrast measured
live in both themes, all ≥ 4.5:1 (floor 4.81 light / 5.71 dark).

## The account drop zone, Slice 2 — `.eml` (2026-08-06, D-219…D-225)

A dropped `.eml` now takes the **same** path a synced message does: `source_reference` →
`comm_message` with thread identity and `new_text_hash` → one extraction run over new text only.
`ACCOUNT-INTAKE-SPEC.md` §7.3 and §7.4 are the authority; both are marked built.

New or changed: `adapters.parse_eml_bytes` (+ `_decode_part`, and `_body` now returning
`(text, body_source)`), `ingestion.DropOrigin` and the origin-aware `ingest_email_message`,
`association.pick_program` (promoted and account-scoped), migration 0053, the `_process_eml` branch
in `app/intake_drop.py`, and `email_file` in `intake_kind`, `src/intakeDrop.js`, and the receipt.
Suites: **742 backend, 229 frontend, clean build.**

What you must not undo:

- **One ingestion path, differing only by origin.** Both dedupe checks live *outside* the
  `DropOrigin` branch, and that is load-bearing: dropping a message the mock inbox already synced is
  a no-op precisely because the check is shared. A `.eml`-shaped copy of `ingest_email_message`
  would grow its own answer to "have we seen this?" within a slice.
- **`read_whole_thread` is refused for a `.eml`, not honoured and not ignored.** The quoted history
  is made of messages that each carry their own `Message-ID`, so each is already a record or will be
  when it syncs. The test asserts the behaviour, not the label: a commitment appearing only in the
  quoted history still produces no proposal.
- **The sender header is the parse guard.** `email.message_from_bytes` never raises — it happily
  returns a headerless message whose body is the whole file. Guard on `from_addr` or a renamed
  `notes.txt` mints a `comm_message` with nobody on the other end, skewing the very reciprocity
  counts §7.4 exists to protect.
- **`_hash_bytes` decodes with `latin-1`.** Not an encoding claim: it is the one codec that maps
  every byte to a distinct character. `utf-8` + `errors="replace"` collapses undecodable bytes to a
  single character, so two different non-UTF-8 messages would hash the same and the second would be
  reported a duplicate and never read.
- **`pick_program` is scoped to the account.** Without the JOIN to `programs`, a person holding a
  stakeholder role in another account's program puts this client's material under that client's
  program. Unreachable while the account was inferred from the same people; reachable the moment a
  caller supplies the account independently, which is what a drop does.
- **A duplicate on another account is named, never linked.** `comm_message_id` stays NULL. A receipt
  in this account must not hold a handle on another client's record; re-scoping is the operator's act.
- **HTML-only is still correspondence.** The `comm_message` is created and only extraction is
  skipped, because declining to read markup is a fact about our parser, not about whether the message
  happened. That is why `_body` returns `body_source` at all.

The both-theme pair was captured on 2026-08-06 and covers this slice too; see the Slice 3 section
above and `design-screenshots/stage-16/VERIFICATION.md`. Nothing in Slice 2 changed the drop zone's
visual design — it adds one `rowmeta` line to the receipt.

Next: Slice 3 is the grounding split view inside `ProposalReview`, run-scoped accept-all, and
duplicate detection. Slice 4 is `("create","milestone")` plus telemetry.

## The account drop zone, Slice 1 (2026-08-06, D-210…D-218)

`ACCOUNT-INTAKE-SPEC.md` is the additive authority. Drop a file or paste a thread on an account's
Operate lens; it is screened, routed to a parser, read, and turned into **drafts in the store that
already exists**. Nothing is written to a tracker until the operator accepts it in `ProposalReview`.

New: migration 0052 (`intake_drops`), `app/intake_kind.py`, `app/intake_drop.py`,
`app/routers/intake_drops.py`, `src/intakeDrop.js`, `src/views/AccountIntakeDrop.jsx`, and
`document_drop_intake` in `CONNECTIONS.md`. Suites: **719 backend, 225 frontend, clean build.**

Screenshots could not be captured when this slice landed, so both themes were verified by computing
rendered colours and contrast in the running app instead: every string ≥ 4.5:1 in light and dark
(lowest 4.81), and drag-over differs by border style, colour, background, **and** label text. **The
pair was captured on 2026-08-06** — `dropzone-{light,dark}.png` and `dragover-{light,dark}.png` in
`design-screenshots/stage-16/` — and the measured values held. The capture path was never broken;
the wrong browser tool was being used. See D-248.

What you must not undo:

- **The receipt resolves nothing.** No accept, reject, resolve, supersede, or apply — on the router
  or in the view. There is one review surface and it is `ProposalReview`; two surfaces that both
  resolve proposals would eventually disagree about what a command means. Two tests enforce this,
  one over `router.routes` and one over the view-model's key names.
- **One proposal store.** A drop writes `extraction_runs` + `extraction_proposals` through the
  existing `_persist_run`. `intake_drops` stores only what a run does not — filename, detected kind,
  byte length, snapshot and its deletion stamps, the new/quoted split, outcome, and foreign keys. It
  has no `coverage_json`, no payload, no status, no proposal count. `test_rr2_proposals` now asserts
  that by column rather than by table-name prefix.
- **Routing is regex and structure, never the model's decision.** A document that could select its
  own parser could decide which of its own text counts as new — the plainest indirect-injection
  shape there is. `intake_kind` touches no database, no network, and no extractor.
- **Every refusal and every coverage sentence is authored on the server.** The client selects and
  orders that text and never composes any of it, including the client-side pre-screen, which repeats
  `/api/intake/limits` verbatim. A view that can compose part of an "I did not do this" statement is
  a view that can soften one.
- **Binary formats refuse by name, not generically.** PDF, Office, images, and audio each get their
  own sentence saying what to do instead. (`.eml` refused with "not yet" rather than "not ever";
  Slice 2 accepts it, and `.msg` inherited its own reason rather than `.eml`'s — D-224.)
- **A document naming another account is reported and does not move.** There is no version of
  automatic re-scoping that is safe: a source that could redirect itself into another client's queue
  is the injection payload writing itself.
- **`coverage.named_not_proposed` and `coverage.refused` are honestly empty.** They need entity
  recognition the app does not have. `skipped` is real because those characters are counted.

The one bug worth carrying forward: `email_thread.split_quoted` is written for a message body a MIME
parser already stripped, so a leading `From:` means quoted history to it. A **paste** still carries
the newest message's own header block, and the unmodified function classified whole pastes as
already-read — producing "Nothing drafted" rather than an error, which is the failure mode that
looks like a verdict. `intake_kind.strip_leading_headers` fixes it and reports the block under its
own coverage reason. Two header keys are required, so prose beginning "From: the finance team…"
keeps its first line.

Slice 2 (above) built exactly that: the `parse_eml_bytes` refactor and a dropped email creating a
`comm_message` through `ingestion.ingest_email_message`, so dropped and synced mail cannot diverge
in the correspondence-derived relationship-health counts.

## Account plan surface review pass (2026-08-05, D-196…D-205)

An adversarial read of `views/AccountPlan.jsx`, `planSetup.js`, and the planning layer they call.
Ten holes; eight fixed, two recorded as unreachable-today. Suites: **684 backend, 213 frontend,
clean build.**

The two that mattered, and the shape they share — a control that cannot be reached:

- **Starting any plan locked out every other one.** `list_plans` returns an account-wide plan inside
  a program scope deliberately, `planPresence.started` counted all of them, and `StartPlan` rendered
  only when nothing was started. One account plan hid the picker for every program; one program plan
  hid it at account level. `AccountPlan.jsx` is the only caller of the route, so there was no other
  way in. The picker is now independent of the list, and `activePlanKeys(payload, programId)` is
  scope-exact where `presence.plans` cannot be.
- **A condition that does not apply read as overdue.** `stageOf` settled on `applicability_override`
  — how an *operator's* exception arrives — but never on the `applicability` axis, which is how an
  *evaluator's* arrives. `not_applicable` now settles either way; `not_due` deliberately does not,
  because the plan and readiness disagreeing is information.

Also fixed: a failed load leaving a permanent spinner (D-172's defect, one level up in the same
file); orphaned migrated instances split out of `unmatched` into their own `orphaned` list so the
partition — and "mapped N of M" — stays honest; the compatibility panel now says its number counts
the whole account while the list above it is one program; removals in the upgrade diff carry a
label; a swallowed error no longer discards a typed fill value; four dead class names.

Left alone on purpose: `merged_plan.overdue` still means "past its date and not met", which is true
of a not-applicable row on both counts. Narrowing it would change a field the execution path also
reads (D-205).

## The launch timeline (2026-08-05, D-189…D-195)

The primary element of the Plan tab: the merged standard drawn against one shared time axis, in
three swim lanes (setup steps, conditions, deployment events). `src/planTimeline.js` is the whole
of the geometry, ordering, status wording and accessible naming — 27 tests; `src/views/
PlanTimeline.jsx` draws what it returns and decides nothing.

What you must not undo:

- **Shape codes the kind, colour does not.** Square/circle/diamond, named in the legend and in
  every marker's accessible name. Status hue is spent only on overdue and flagged-at-risk markers,
  and both also gain a ring. `markerLabel`/`clusterLabel` are composed in the module so a view
  cannot ship a marker whose colour says something its name does not. Do not add a lane colour.
- **The module computes no state.** Readiness axes pass through untouched. The only derived value
  is `late`, a date comparison, and it is reported *beside* a reading, never instead of one.
- **Coincident dates cluster, they do not stack.** `clusterPoints` collapses a lane's same-date
  rows into one marker with a count, and the caption lists every member. A cluster is `done` only
  when all its members are. Reverting to one marker per row re-hides five day-zero setup steps
  behind three visible squares (D-191).
- **The axis is bounded and states the cost.** 45 days back / 120 forward, always containing today;
  everything outside is counted in `window.clipped` and named in a sentence `timelineNotice`
  authors whole. Do not compose that sentence in a view.
- **Points, never bars.** All 23 things are moments; a bar would assert a start nobody recorded.

The Plan payload (`GET /api/accounts/{id}/plan-instances`) now ships **three** arrays —
`requirements`, `setup_items`, `milestones` (`phase_readiness.plan_milestones`). Three and not one:
each kind keeps its own vocabulary and only the dates are shared. Screenshots in
`design-screenshots/launch-timeline/` (both themes). Contrast audited in both: light ≥ 5.43, dark
≥ 5.53, floor 4.5.

## One merged launch standard (2026-08-05, D-182…D-188)

Migration 0051 merges the three lists that each claimed to be the standard work of a launch.
Onboarding no longer seeds `checklist_items`; it seeds **8 phase-gate items + 8 readiness
requirements + 7 milestones = 23 dated things**, each appearing exactly once. Twelve of the old
twenty checklist items were a requirement or a milestone wearing a checkbox, several of them at a
*later* date than the record they duplicated — so the checklist could report work outstanding that a
milestone had already marked done. `app/templates/launch_gates.yaml` names all twelve exits, which
is what makes the merge auditable; it is the editable seed file, so change the standard there rather
than in code.

**Read the counts as exact.** `test_onboard_seeds_one_merged_standard` asserts `== 8` / `== 7`, not
`> 15`. A floor assertion is what let the old checklist grow a second copy of the budget owner and a
third copy of the launch milestones without a test noticing.

**Two behaviours had to be carried forward, not dropped** (D-183). The checklist escalated into
Today after a week past due — queue block 7b now does that for gate items via `gate_item_overdue`,
restricted to gates still `open`, because re-raising the items of a passed or waived gate argues with
the operator who settled it. And PHASE-3-SPEC.md §1e's `fills_field` put a first-call answer into the
field it asked about — `PATCH /api/gate-items/{id}` now does that, plus the date push the queue's own
"do it, mark it done, or push the date" was already promising. **Nothing is inferred from a
completion**: the operator supplies `fill_value`, and a tick alone writes only the tick.

**On the Plan tab the merge is one reading order, not one row type** (D-185). Gate items and
requirements share the six horizons and are partitioned by the same `planStages`, but ride in
separate arrays (`rows` / `setup`), are counted separately in the header, and are drawn differently.
A gate item is the one row here with a completion control, because it asks "did somebody do this?"
and only an operator can answer that; a tick on a requirement would be the stored second source of
truth the projection rule forbids. `phase_readiness.setup_items` ships `state`, `freshness` and
`applicability` explicitly null — the absence is the claim. Do not merge the arrays or the counts:
"11 things open" invites eleven ticks, and eight of them are conditions no tick can satisfy.

**One account is onboarded in the seed and the rest are not, on purpose** (D-187). Every seeded
account was assembled from YAML and none had been through `seed_onboarding`, so the Plan surface
filed every setup step under "No date on this plan" — the horizons worked and had nothing to sort.
`_seed_onboarded_launch_demo` runs the real flow on **Bluepeak** with a kickoff four days back and
ticks three day-zero items through the router, so the scene spans settled / overdue / due-now / next.
The seed is not covered by pytest (it needs the real DB); if you change onboarding, run
`python -m app.seed --reset` and look at the Plan tab.

Both-theme captures in `design-screenshots/merged-launch-standard/`; contrast floors measured live
over the Plan surface — light 5.44, dark 5.53, nothing under 4.5.

## Account Path review pass (2026-08-05, D-173…D-181)

`ACCOUNT-PATH-REVIEW.md` audited the finished Account Path. Nine findings were accepted and fixed;
five were rejected with reasons, all recorded in `decisions.md`. Backend 682 green, frontend 174
green, build clean. The three worth carrying forward:

- **A gate verdict no longer says `blocked` about a condition it could not read.** `coverage_failures`
  carries two vocabularies — bare evaluator keys and `gate_requirement:<instance_id>` — and the
  classifier understood one, so a row with `state: None` was counted as an established gap. Because
  `playbooks.instantiate` archives **every** instance of a superseded plan, one ordinary playbook
  upgrade produced a false `blocked` on every gate link. Classification is now on the row's own
  `available` flag, excluded by `link_id` rather than `requirement_key`.
- **`next_move_completed` is now `next_move_left_list`, in the spec too.** The path sees only that a
  recommended row is absent; closure, cancellation, archival and ageing out all produce that
  absence and the client never learns which. Do not reintroduce a completion word here. The funnel
  returns `by_rule_version` and labels an aggregate that spans more than one ordering.
- **Known gap, decided: a playbook upgrade orphans every gate requirement link it archives.**
  `playbooks.instantiate` archives every instance of the superseded plan and nothing re-points the
  gate links at the successor instances. Zach's call (2026-08-05) is to **leave it**: the gate now
  reports `insufficient_data` and names the conditions it could not read, so the failure is visible
  and an operator re-links by hand. Do not "fix" this by having the upgrade silently re-point links
  — v2 of `enterprise-launch` drops `budget_authority_evidence`, so some links have no successor to
  point at, and a carry-forward that quietly dropped those would recreate the exact defect D-173
  closed. If it is ever picked up, it belongs in the upgrade **preview** as a named, previewed
  action, not in `instantiate`.

## Account Path Slice 7 — measurement and refinement (2026-08-05, D-156…D-161)

Slice 7 of `ACCOUNT-PATH-SPEC.md` §17 is built. **The Account Path is now complete: Slices 1–7 are
all built.** Migration 0050 adds one table.

**Measurement never leaves the installation, and that is what makes the default acceptable.**
`app/telemetry.py` records sixteen named events with an account id, a reason code, a ranking rule
version, and a rotating session token — no person id, no free text, no record content, and no
adapter, because an event never reaches a network boundary. It is still registered in
`CONNECTIONS.md` as `product_telemetry_sink` (`gate_status: local`), because the day somebody points
it at a vendor, behavioural data about how an account is worked starts leaving the installation —
that is the data-handling conversation, not a config change, and registering it while it is local is
what makes the allowlist reviewable beforehand. The §17.4 setting in Operations turns it off *and
discards what was already collected*, which
the button says on its face rather than leaving to be discovered. Do not add a field that identifies
a person, and do not add an export: both would turn this into the class of data CLAUDE.md §2 forbids.

Read the funnel as two counters, not one. `views_with_next_move` is separate from `views` because a
completion rate over all views is diluted by accounts that were never offered anything, and
`views_with_incomplete_coverage` is separate because a view where a source failed is not evidence
about ranking quality. Every event carries `ranking_rule_version` so a funnel spanning an ordering
change cannot silently average two orderings. **The §17.5 caveat renders on screen beside the
numbers** — counts describe use, not recommendation quality — and §17.5's actual answer is a
periodic qualitative review by a person. Do not add a numeric quality score here.

`VALENCE_OS_RANKING_RULES` selects the active ruleset at process start. `POST
/api/telemetry/ranking-rules/compare` builds every account's path under both versions and diffs the
ordering, **writing nothing and selecting nothing** — a button that switched the live ordering would
be a deployment decision wearing a click. It returns moved rows with from/to positions and reason
codes rather than a similarity score, because that is what a person can review.

**The comparison honestly reports `0 of 5 accounts reorder` against the seed until 2026-09-06.**
That is elapsed time, not a defect: `v2-candidate-notice-first` only moves
`contract_decision_window`, Terravance is the only seeded account with a contract, and its earliest
lead window opens at `renewal − procurement_lead_days` = 2026-09-06. **Do not "fix" this by seeding
an overlay dated to the seed run** — that was written and removed (D-161), because
`stage-0/seed-data/terravance.yaml` already carries a coherent overlay and overwriting it would make
the demo reproducible by contradicting the scenario it demonstrates.

`frontend/src/telemetry.js` keeps its own copy of the event names so a typo at a call site is a
visible no-op rather than a discarded request; a backend test reads `EVENT_NAMES` out of the JS
source and asserts set equality with `app.telemetry.EVENTS`. **`measure.js` is untestable by
construction** — it imports `api.js`, which reads `import.meta.env` and throws under bare
`node --test` — so every rule lives in the pure `telemetry.js` and `measure.js` is browser wiring only.

One defect worth carrying forward (D-160): `coverageNotice()` dropped `coverage.warnings` on a
complete read, so a **snoozed row vanished with no statement that anything was hidden** — the Slice 3
rule that a suppression is subtractive and always reported, read backwards. A complete-but-
subtractive read now renders a quiet `rowmeta` line with no status hue (a withheld row is not a
failure); an unreadable source keeps its callout. The test that should have caught it passed a
`warnings` entry to make a point about `coverage.readiness`, a different field, and so asserted
nothing. Fifth consecutive slice where a green pure-module suite said nothing about what renders.

Validation: 660 backend tests and 138 frontend tests green; production build clean; four both-theme
PNGs with the audit in `design-screenshots/account-path/VERIFICATION.md`. Contrast measured live over
54 nodes per theme: light floor 5.44, dark 5.53. The two Operations cards add **no CSS**.

## Account Path Slice 6 — shared plans and generated outputs (2026-08-05, D-151…D-155)

Slice 6 of `ACCOUNT-PATH-SPEC.md` §16 is built. There is
**no migration**: the shared plan stores nothing, and the promotion columns it reads already existed.

`backend/app/shared_plan.py` projects `(artifact, diagnostics, manifest)`. The `artifact` is the
customer's document, `diagnostics` is the operator's, and the split is structural — the artifact is
built from promoted records only, rather than built whole and filtered on the way out. Keep it that
way: a filter applied late is one refactor away from being applied in the wrong order, and a leaked
row is invisible because the artifact still looks complete. `GET /api/accounts/{id}/map` returns
both; **this is a v2 shape** — the old flat `items` list is gone, so anything reading the MAP now
reads `["artifact"]["markdown"]` or `["artifact"]["growth_lines"]`.

`_requirement_status` maps a readiness reading onto the five client-facing status words **or refuses
and says why**. The near-misses are the point: a `met` whose evidence is stale is withheld rather
than shown as `Complete`, a `conflicted` reading is withheld rather than resolved in the customer's
favour, and legacy pins, suppressions, and waivers are withheld because their rationale is internal.
An unrecognized readiness state falls through to a refusal naming it, never to a default.

Each refusal is authored on the server as a lower-case clause completing "held back because …", and
the sentence frame is `frontend/src/sharedPlan.js:withheldSentence` so the node suite can pin it.
**Do not compose any part of a refusal in the view** — a view that formats one is a view that can
soften one. `GET /api/map/promotion-preview` runs the same projection as the export, so the preview
an operator confirms is the real output; it is mounted in the ledger, before sharing. The client-label
field appears for a requirement only, because §16.3 needs a label written for a customer while a
commitment's description is already the shared text.

Validation: 621 backend tests (37 in `test_account_path_slice6.py`) and 117 frontend tests green;
production build clean; six both-theme PNGs with the audit in
`design-screenshots/account-path/VERIFICATION.md`. Contrast measured live over both themes: plan
light floor 4.81, dark 5.32; slide-over light 5.44, dark 5.32.

**Theme trap, now confirmed twice:** setting `data-theme` on the root does *not* switch the app —
`App.jsx:48` owns that attribute from its own state and overwrites it. Write `valence-theme` to
`localStorage` and reload.

The demo scene comes from `seed._seed_shared_plan_demo`, which builds it through the app's own write
paths and **deliberately leaves work unpromoted**, including one requirement promoted while its
readiness reads `unknown`. That is not seed rot — it is how the withheld-with-a-reason path stays
visible outside the tests.

## Account Path Slice 5 — evidence, relationships, and governed advancement (2026-08-05, D-149/D-150)

Slice 5 of `ACCOUNT-PATH-SPEC.md` §15 is built.

Migration `0046` adds four link tables — `readiness_requirement_action_links`,
`requirement_evidence_links`, `milestone_action_links`, `gate_requirement_links` — and **not one of
them has a `state`, `status`, `met`, `freshness`, or `coverage` column**. That is the load-bearing
rule of the slice: a link table is exactly where somebody caches "this requirement is satisfied" to
avoid re-evaluating, and the cached copy disagrees with readiness the moment the underlying record
changes. Closing a linked Task settles the Task; the condition is still whatever the records say on
the next read, and the UI says so in those words. Writes go through
`backend/app/routers/path_links.py` — note the payload shapes, which are easy to guess wrong: an
action link takes `task_id` **or** `commitment_id` (never `action_type`/`action_id`), and evidence
takes `evidence_type` + `evidence_id`. Waiving a gate is deliberately not routed there;
`POST /api/phase-gates/{gate_id}/waive` already exists and `delivery.py` delegates to
`phase_readiness.waive_gate` so there is exactly one waive path.

Governed advancement lives in `backend/app/phase_readiness.py`. A gate verdict distinguishes
`blocked` (evaluated, unsatisfied) from `insufficient_data` (could not be evaluated) — making that
distinction true required fixing `readiness.evaluate`, which **popped** each pillar's
`coverage_failures` while aggregating them, so every gate reported `coverage: complete` regardless.
An advance carries the `readiness_stamp` of the payload the operator actually read. An override
records the unmet conditions and satisfies none of them; a waiver moves no phase.

Two things a linked action does **not** do, both asserted by tests: it does not become evidence for
the requirement, and evidence of a kind the definition does not accept attaches with
`supporting: false` and a sentence saying it cannot change the state. A count-based evaluator stays
`thin` no matter what is attached, because the count is the count.

Validation: 584 backend tests (37 in `test_account_path_slice5.py`) and 103 frontend tests green;
production build clean; **both-theme PNGs delivered** — 8 for Slice 5 and the 4 owed from Slice 4 —
with the full audit in `design-screenshots/account-path/VERIFICATION.md`. Contrast measured live
over 239 nodes across both themes: light floor 4.81, dark floor 5.12, nothing under 4.5.

**Read D-150 before touching the requirement surfaces.** Rendering caught a defect the suite could
not: `_requirement_row` correctly drops a requirement from `current_phase_gaps` once an action is
linked (§13.6), but `AccountEssentialsGaps` is the only mount of `RequirementPanel` and lists only
the gaps — so linking an action removed the condition from the one surface that can add evidence or
revoke a decision. The `.req-tracked` disclosure over `trackedRequirements()` is the route back, and
it must stay a disclosure: if it becomes a second queue it reinstates the duplication §13.6 removed.

## Account Path Slice 4 — transcript and email proposals, one review surface (2026-08-05, D-148)

Slice 4 of `ACCOUNT-PATH-SPEC.md` is built. It is the review half of the RR-2 proposal store and the
§14.8 email boundaries underneath it.

Reviewing a proposal now happens in exactly one place. `frontend/src/views/ProposalReview.jsx` is
the only surface in the app that accepts, rejects, resolves, or supersedes anything, and both entry
points open it: the Overview card's `Review all` (in a slide-over) and the Extraction screen after a
run. `Extraction.jsx` kept its ingest half — paste text, run the configured extractor — and lost its
own row-level accept/reject, which was the last reader of the legacy `mutation_type` enum in the
frontend. That enum could only ever describe creations, so its commands had already drifted from
what Overview offered for the same proposal.

The commands are `Accept as drafted` / `Apply my edits`, `Reject`, `Use existing record`,
`Supersede`, and `Open source`. Each is offered only when it can succeed and carries the reason when
it cannot, wired through `aria-describedby` so the reason is announced and not merely printed.
Nothing is preselected and nothing is ranked by model confidence. The decision rules live in
`frontend/src/proposalReview.js` as pure functions with 19 tests; the component holds no policy.

§14.8's email boundaries are in `backend/app/email_thread.py` and migration `0045`. The extraction
boundary for an email is its **new text** — what this sender added above the quote — and the §6.6
content hash is a hash of that, not of the raw body. This is the non-obvious half: without it, a
five-message thread is read five times and the same commitment is drafted five times. Deduplicating
proposals afterwards cannot fix it, because two readings of one sentence in different messages have
different references, locators, and spans, and so fingerprint apart correctly. Thread identity comes
from the `References` root, never the subject. Attachments are referenced by name and never read.
An email whose association is unresolved proposes nothing until an operator confirms it.

Validation: 547 backend tests and 75 frontend tests green at the time; production build clean. Both
themes were verified by computed-style audit on a real load into each theme (37 leaf nodes in the
open review surface, 0 below 4.5:1, tokens resolving in both). The PNGs owed here were captured
during Slice 5 and are in `design-screenshots/account-path/` as `slice4-review-{light,dark}.png` and
`slice4-decision-{light,dark}.png`. Two caveats worth carrying: an imperative `data-theme` flip does not fully recompute
styles in that headless engine, so audit each theme by reloading into it; and `:focus-visible` never
matches there because the offscreen window holds no focus, which makes focus-ring checks by that
route inconclusive rather than failing.

## Release 2 — adversarial review and critical fixes (2026-08-03, D-126/D-127)

An independent adversarial review of Release 2 found three critical defects, all reproduced
against a live database before fixing and re-verified after: cross-account person labels leaking
into account-scoped activity/command-center/leadership responses; a single unnormalizable source
row (an empty calendar title, which the column permits) taking down every lens with a 500 instead
of degrading to partial coverage; and migration 0039's checkpoint trigger making an account
permanently un-restorable once a program was archived. All three are fixed with regression tests
verified to fail against the pre-fix code. Fixing the leak also closed its root cause — the
interaction write path accepted a foreign `participant_id`, which additionally made the account
un-exportable. A separate latent bug surfaced during verification: `company_intel` derived "today"
in local time while SQLite and every other module use UTC, so expiry comparisons disagreed with
the database every evening in a US timezone.

The seven remaining findings from that review are now closed (D-128): the prohibited numeric
confidence percentage in Prepare, the discarded `native_target.record_id` (Ledger now selects the
focused record), the stakeholder payload missing its evidence notes, the lens tablist selecting
without moving focus, "Since your last visit" being advanced by unrelated saves, the Leadership
lens dropping the stale-assessment outline, and the `event_kind` filter returning 422 when an
account had no matching row.

**Outstanding (D-129): the contrast auditor is blind to the new gradient surfaces.** The command
center uses `background-clip: text` headings and `spotlight-surface` gradient cards; the
computed-style walk used in these reviews reads only `background-color`, so it cannot score them
and its readings there are artifacts. No automated contrast evidence currently covers those
surfaces in either theme — a gradient-aware check or a recorded manual audit is still owed.

## Account command center Release 2 — implemented (2026-08-03, D-117–D-123)

Account Overview is now one addressable Operate/Prepare/Leadership command center over a shared account/program scope. Operate is complete: it separates material changes since durable review from browser-local changes since visit, exposes deterministic overdue/blocker/status/ask/review attention with reasons, orders confirmed upcoming account moments, and shows the latest dated operator point of view. Sections default to five rows, name partial adapter coverage, retain exact temporal and trust state, and link back to native workspace tabs. Export, capture, program creation, People/Plan reachability, and governed status editing remain available.

Prepare is also complete. It defaults to the next scoped meeting, supports addressable upcoming/recent selection, preserves direct account meetings inside a program filter, and rejects out-of-scope meeting IDs without leaking their identity. It composes canonical calendar, people, stakeholder-role, activity, execution, ask, risk, communication, company-intelligence, and generator contracts at query time; there is no new meeting truth store. Known attendees receive only recorded role/stance/touch context, unknown invitees stay unknown, and Valence colleagues do not create customer evidence noise. Attendee-related changes exclude the baseline last-touch interaction. A separate bounded public-context section is shared with the deterministic pre-call brief and admits only confirmed, non-expired facts through confirmed account/attendee links with exact sources. Open threads remain deterministically ordered, weak inputs become named evidence gaps, and pre-call preview/Copilot are explicit actions. Opening the lens or previewing the brief creates and sends nothing.

Leadership is complete as a read-only internal review, not a second forecast or team-update generator. It presents delivery and commercial independently with governed recovery responses; exposes active forecast units, period, unresolved conditions, and deterministic evidence support; separates cursor-based material movement from blockers, overdue work, at-risk milestones, and evidence gaps; names active asks with owners, deadlines, escalation state, and next actions; and carries contractual notice/renewal dates plus operator-view and account-review provenance. Status, forecast, asks, contract, and review facts are explicitly account-wide. Program-aware movement and execution exclude other programs while retaining direct account records. Cross-account person/ask references are rejected at write time and fail closed on read. Missed notices, stale views, and absent statuses/forecast are named rather than silently omitted. No schema or leadership truth store was added, and opening the lens creates neither a checkpoint nor a document.

The typed query-time projection now covers interactions, execution, status assessments, forecast transitions, internal asks, account reviews/operator views, calendar, deployment moments, communications, and company events. It remains rebuildable and structurally excludes raw notes. Proposed company events retain proposed state and cannot enter material change summaries. One append-only table stores per-actor account/program review checkpoints; a frozen server stamp prevents client-clock drift, equivalent UTC timestamp forms are idempotent, and account-scoped Copilot review advances the same cursor only when it is newer. Program review cannot clear another program or direct account activity. Export/restore includes the checkpoints.

Slice 2.4 completes the consumer/evidence loop without changing taxonomy. Ledger now has a Records/Activity subview: Records preserves capture, conversion, closure, and mutual-plan actions; Activity is a read-only cross-source chronology with scoped stream/source/state/direction/materiality filters, explicitly loaded-page search, stable cursor pagination, separate effective and recorded time, native provenance, and partial-coverage states. Interaction origins and records created from them remain distinct facts inside an expandable group. Company activity, Search, Prepare, and Copilot now converge on the same addressable Commercial/Company event route instead of landing on Whitespace or Overview. The cited feed expands every live span, counts distinct source documents, and retracts a chosen source. Company-brief coverage is computed independently by retrieval time, and expired events cannot enter active briefs. The API returns scoped facets, pre-cursor matched count, and per-adapter status/item/time measurements. A read-only 30-run sample over all five seeded accounts (150 projections, ten adapters) measured 0.089 ms median, 0.235 ms p95, and 1.988 ms max, with 17 items on the largest account. There is no evidence for a materialized activity table. There is also no product-usage evidence for replacing the eight established tabs with the directional five-job model, so both changes remain deferred until measured behavior justifies them.

Validation: all 364 backend tests and 15 frontend unit tests pass; frontend lint exits zero with the repository's existing warnings; the production build succeeds. The in-app browser exposed no target, so no fresh both-theme rendered pass is claimed. `ACCOUNT-COMMAND-CENTER-SPEC.md` remains the Release 2 authority; Release 3 stays directional rather than implicitly authorized.

## UX foundation Release 1 — implemented (2026-08-03, D-116)

`UX-FOUNDATION-SPEC.md` is the additive staged UX authority created after the full-app adversarial product review. Release 1 deliberately preserves the current eight account tabs while fixing the low-regret foundation: a pure route codec and History API wrapper make Today, Accounts, account tab/program scope, Library, and Operations directly loadable, refresh-safe, and Back/Forward-aware. FastAPI's static mount now falls back to `index.html` only for extensionless non-API navigation paths, so missing assets and unknown APIs stay real 404s. A missing account route recovers to Accounts rather than hanging on a loading state.

Today and the Accounts Book now share one saved-view contract with built-in presets, named browser-local custom views, modified-state feedback, safe corrupt-preference fallback, and an accessible save slide-over. Today adds account and text filtering; Accounts adds text/status filtering, status-aware sorting, and visible delivery/commercial assessments in the Book. Browser-local persistence is deliberate for the current single-editor product and stores presentation state only.

Validation: 353 backend tests and 8 frontend unit tests pass; frontend lint exits zero with the repository's pre-existing warnings; production build succeeds; direct FastAPI smoke requests return the SPA for all canonical routes and JSON 404 for an unknown API. No fresh both-theme rendered pass is claimed because the in-app browser exposed no target in this session. Release 2 is now detailed in `ACCOUNT-COMMAND-CENTER-SPEC.md` (D-117) but remains unimplemented; Release 3 (outcomes, hierarchy, and Growth Thesis) remains directional.

## Stage 14 — company intelligence implemented (2026-08-02, D-110/D-111)

`COMPANY-INTEL-SPEC.md` v2 is accepted and implemented as migrations 0036–0038. The architecture separates canonical companies from account records; stores provider-scoped immutable public artifact versions and exact evidence spans; keeps imported events and map links proposal-first; derives posting-level hiring clusters; persists independent convergence composition; bridges only convergence into Stage 7; and adds a fixed-section, claim-cited `company_brief` copilot intent. Corrections/retractions invalidate unsupported derivatives, and the public-source and extraction boundaries remain separate local-only registry entries.

The account Commercial workspace now has a Company sub-tab for identity/watch setup, mock sync, proposal review, cited feed, hiring facts, convergence evaluation, and brief launch. The whitespace map has an off-by-default outside-in flag overlay that annotates row/column headers without altering cell state. Search, account export/restore, Today review debt/convergence, Operations counts, and connection governance are integrated.

Validation: all 352 backend tests pass, including 17 Stage 14 adversarial cases (13 from the build, 4 from the post-build review, D-112); frontend lint exits zero (repository-pre-existing warnings remain), the production build succeeds, and the Company and Operations surfaces were exercised in a 1440×1000 rendered browser in dark and light themes with no horizontal overflow. The rendered flow confirmed both events, opened convergence with exact composition, exposed map/source controls and the full watch policy, and showed Operations freshness/review/sync measures. A rapid concurrent navigation pass also remained clean under the request-level SQLite serialization guard.

## Design review mechanical tail — completed (2026-08-03, D-115)

The focused primitives pass following D-113 is complete across 45 frontend files. Numeric/date
columns now share `.num` (mono, tabular, right-aligned); every rendered table header declares
`scope="col"` or `scope="row"`; generic save copy names its outcome; and the blocking
`window.prompt()` flows in Delivery, Library, and Playbook Library are accessible `SlideOver`
forms. The top-bar capture affordance is secondary so a view can own its one primary action,
repeated row actions are secondary, and selected-state button groups use `.selected` with
`aria-pressed` rather than borrowing `.primary`.

Shared `Loading` and `DueChip` treatments replace the repeated view scaffolds and the future-date
misread in checklists/find-by dates. Form controls inherit the application face globally; palette
results expose combobox/listbox/option semantics; the recorded off-scale spacing patterns and raw
10px graph/timeline/waterfall labels are gone. Static guards find no missing table scopes, blocking
prompts, generic Save/Submit/OK labels, or handoff-listed off-scale spacing. Validation: 352 backend
tests pass; frontend lint exits zero (the repository's pre-existing warnings remain); production
build succeeds. A fresh rendered both-theme pass was not captured because this session exposed no
in-app browser target; D-113's preceding full-app both-theme audit remains the latest rendered
evidence, and this limitation is tooling evidence rather than a claim that a new visual pass ran.

## What this is

Valence OS is an internal, single-editor web app for one Valence Engagement Manager to run a few very deep Fortune-100 accounts end to end. `Valence-OS-Scoping-Doc.md` is the original foundation; the completed Phase 3 and Expansion Engine specs and the additive Stage 10 Internal Ops spec deliberately extend it. `CLAUDE.md` defines the current authority chain and binding trust boundaries.

**Status: Phase 3 through Stage 14 is implemented.** `ADOPTION-CAMPAIGN-SPEC.md` governs completed Stage 11, `ACCOUNT-COPILOT-SPEC.md` governs completed mock-only Stage 12, `ADOPTION-COMMS-SPEC.md` governs completed Stage 13, and `COMPANY-INTEL-SPEC.md` governs completed mock-only Stage 14. No real sending, calendar write, public-artifact retrieval, extraction, or Copilot adapter exists; all external connections remain gated and mock-only. Stage 14 has rendered pointer-flow and both-theme verification; a dedicated screen-reader/keyboard-only audit remains a release-hardening task rather than a Stage 14 functional gap.

**The prior "do not resume building" guidance is retired by the Phase 3 spec.** Building to feature-complete is now the instruction; the evidence gates are gone. What stays binding: the §2 trust boundaries, the design guide, mock-only data, tests green, decisions logged. The single remaining gate is **data governance, not scope** — every external connection is a mock adapter until hosting/data-handling is cleared at Valence (see `CONNECTIONS.md`, and `PHASE-3-SPEC.md §9`). Phase 3 progress and the newly permitted dependencies are logged in `decisions.md` (regime change: D-73).

**Phase 3 progress (build order in `PHASE-3-SPEC.md §10`):**
- **Task Zero — done.** Docs regime change; job table (migration 0011) + single in-process worker (`app/jobs.py`, env-gated `VALENCE_OS_WORKER`, default off) + jobs API. D-73/D-74.
- **Stage 1 — done.** Guided onboarding, launch checklists, org-chart placeholders (migration 0012). New backend: `app/onboarding.py`, `app/intake.py`, `app/routers/onboarding.py`, editable templates under `app/templates/`. Two new queue triggers (`checklist_overdue`, `unidentified_placeholder`). Frontend: onboarding wizard (`Onboarding.jsx`, fires on account create), checklists panel in the Plan tab (`Checklists.jsx`), placeholder nodes + coverage on the graph. Screenshots in `design-screenshots/stage-1/` (both themes). D-75. **86 tests pass.**
- **Build order reordered by the Comprehensive Spec (Part 7), D-76.** New trust boundary in force: professional observations only, no sensitive personal data (D-76).
- **Stage 2 — done.** People module core (migration 0013): layer model on stakeholder roles + layer-lane graph view; full buying-committee role taxonomy (table recreated to widen the enum); evidence-enforced coach-vs-champion (`advocacy_events`, computed at read time); person profile card (`GET /api/persons/{id}/card`, `PersonCard.jsx`) assembling roles/stance-trajectory/commitments/edges/history/advocacy; new `app/people_core.py`. Screenshots in `design-screenshots/stage-2/`. D-77. **94 tests pass.**
- **Stage 3 — done.** Cadence engine + relationship health + coverage analytics (migration 0014, `app/cadence.py`): per-role cadence targets (derived by quadrant, floored for seniors, overridable), the `cadence_overdue` queue trigger (replaces `stale_stakeholder`) with content-carrying suggested touches, health panel on the person card, and coverage compliance/layer-heat/detractor-watch in the sidebar. Stage 7 later replaced the honest reciprocity/attendance unknowns with observable comm/calendar counts. Screenshots in `design-screenshots/stage-3/`. D-78. **102 tests passed at that point.**
- **Stage 4 — done (core).** Communications ingestion + shared association engine (migration 0015): mock email (.eml) / recording adapters (`app/adapters.py`, fixtures under `app/fixtures/`), one association engine that learns from corrections (`app/association.py`, supersede-not-delete hints), ingestion through the job table (`app/ingestion.py`: `sync_emails`, `ingest_recording`), `comm_messages` threaded onto the ledger, priority flagging + the `unanswered_email` queue trigger, and a Comms panel in the Ledger tab. **Deferred to Stage 5 (D-79):** the §4.4 new extraction targets (placeholder-fill, pull-signal, deployment-moment, value-story) + the review-screen redesign — folded in with their consumers. Screenshots in `design-screenshots/stage-4/`. **108 tests pass.**
- **Stage 5 — done.** Relationship intelligence (migration 0016): champion development pipeline (`champion_candidates`, evidence-gated validate/arm/maintain, single-thread-risk analytic), influence paths (pure BFS over `relationship_edges`, two-hop-strong beats one-hop-weak, one-click intro task), executive alignment (`exec_pairings` + derived last-touch + unpaired-exec exposure), role-based messaging library (`messaging_entries`, seeded from `app/templates/messaging_library.yaml`), meeting dynamics (derived attendance/went-quiet, on the person card), and the **deferred §4.4 extraction targets** (placeholder-fill, pull-signal, deployment-moment, value-story) with a keyboard-driven review-screen redesign. New backend: `app/people_analytics.py`, `app/routers/relationships.py`. Frontend: `People.jsx` wrapper with Champions/Influence/Exec/Messaging sub-tabs. D-80. **118 tests pass.** (Screenshots flaked — see `design-screenshots/stage-5/VERIFICATION.md`.)
- **Stage 5.5 — done.** Whitespace map, value realization ledger, funding intelligence (migrations 0017-0019, `app/expansion.py`, `app/routers/expansion.py`). Segments are the only additive dimension; composite views never enter totals. Paid seats live as explicit row inventory because overlapping use-case cells have no derivable union (legacy rows keep a visibly labelled max estimate until corrected). Cell state remains derived from four reason-logged facts. Aggregate metric evidence uses stable segment/view IDs and the target's agreed timeframe. ARR is derived once; revenue events enforce sign/currency. The Commercial UI includes fresh-account setup plus source, promotion, and evidence controls. D-84/D-86/D-88.
- **Stage 6 — done and adversarially hardened.** Finished artifacts (migrations 0020-0021, `app/generators.py`, `app/decks.py`) share an editable draft → reviewed → sent/discarded workflow and render PPTX/PDF without re-querying. Pre-call briefs are internal and program-scoped; client artifacts require promotion and provenance, compute rollups only from shared rows, and carry honest freshness. Champion kits link to intended champions and record handoff only when marked sent. Weekly updates recur into the same review queue; nothing is auto-sent. D-87/D-88.
- **Stage 7 — done and adversarially tested.** Migration 0022 replaces forever-deduped plays with condition episodes: clear/re-arm is required before recurrence; threshold signals carry direction/hysteresis/freshness; pull windows and dismissal cooldowns are account settings; terminal actions do not reopen while the same source condition persists. Client pull always surfaces, while vendor-initiated calendar/usage motions can be visibly held behind unrealized value. Mock `.ics`, enrichment JSON, and HRIS-shaped CSV adapters run through the job table. Org-change rows are proposals until confirmation; departure confirmation snapshots the relationship and opens a successor placeholder. Calendar attendance and comm reciprocity are observable counts only; priority response thresholds count configured local business hours. Signals/Calendar/Org changes ship in the existing Commercial/Plan/People IA; export, search, Operations, and kickoff scheduling are wired. D-89. **208 tests pass.** The in-app browser was unavailable; the honest static verification and recapture note is in `design-screenshots/stage-7/VERIFICATION.md`.
- **Stage 7.5 — done and adversarially tested.** Migration 0023 adds five linked qualification slots without a score; operational agreements stay outside the canonical contract and distinguish signed-paper authority from an agreed conversation; a realized target creates exactly one earned event, fires the expansion play, enters attention, and atomically drafts the expansion paper when actioned. The renewal center is derived continuously from contract, fiscal, value, penetration, risk, and qualification records. Growth-plan probabilities carry author/date; overlapping populations withhold totals; the mutual twin queries only promoted sourced joint fields and cannot select internal probability, funding, or competitive fields. D-90. **216 tests pass.** Browser verification was unavailable; see `design-screenshots/stage-7.5/VERIFICATION.md`.
- **Stage 8 — done and executable.** `CONNECTIONS.md` names all eleven external boundaries, their active local/mock modes, fixture sets, switches, real-mode requirements, and approval contract. `app/connections.py` is the runtime twin: Operations renders it and the optional API extractor now fails closed unless both explicit approval and a decision-log reference are configured. `docs/runbooks/phase-3-demo.md` is backed by a full API test that takes a newly assigned synthetic account through onboarding, communications, extraction review, people/evidence, an earned trigger, five-slot qualification, growth/renewal, and a delivered expansion case. The demo exposed and fixed intake-created duplicate people, internal-ID-coupled org fixtures, and the missing succession soft-delete columns (migration 0024). D-91. **220 tests pass.** The in-app browser remained unavailable; see `design-screenshots/stage-8/VERIFICATION.md`.
- **Stage 9 — done and adversarially tested.** Migration 0025 closes the missing commercial facts that analytics need: cell transitions snapshot their derived state, growth lines can name the exact whitespace cell/use case, funded lines carry a dated funded fact, and price bands may state currency plus annual-recurring/term/one-time basis. Portfolio analytics report counts, denominators, record ids, explicit zero vs. insufficient data, overlap exclusions, and actual/projected revenue only where units support it; currencies are never blended and no portfolio NRR percentage is manufactured. The playbook captures one structured entry per Proven/Penetrated/Declined transition, derives and snapshots global audience tags from the transitioned cell, excludes account-specific use cases from cross-account matching and portfolio-play promotion, and ranks exact shape → tag overlap → use case with a visible reason. Empty tag sets are use-case-only rather than false exact matches; no-op facts cannot create transition prompts; velocity uses the latest Proven episode; learned plays fire only for matching evidence shapes. Export/restore and global search include the new records. D-92–D-94. **229 tests pass.** The in-app browser remained unavailable; see `design-screenshots/stage-9/VERIFICATION.md`.

**Stage 10 — implemented and externally adversarially reviewed.** Migrations 0026–0030 land the integrity rebuilds, internal operating layer, and review remediation. Forecast calls are period-scoped, evidence-explicit, opening-snapshot-frozen while live calls remain mutable until close, submission-frozen, and calibrated from dated outcomes without cross-unit blending. Internal asks have append-only transitions and escalation instances that snapshot same-severity editable defaults against the Valence calendar. Reviews use account-level commitment/decision provenance, governed status history, deterministic challenge sheets, immutable source manifests, and a bidirectional blocking no-surprises check. Roster coverage is interaction-derived and framed as account exposure; role-scoped call, 14-day handoff, and return briefs are generated from live evidence. Product feedback separates portfolio themes from sourced account occurrences and closes both acknowledgment and resolution loops through recorded interactions. The account and portfolio Internal views expose the workflows without removing Stage 9 Portfolio Analytics. Search, Library, Operations counts, person context, Ledger, Today, export/restore, weekly reporting, and analytics include the new records. No outbound path was added. D-96/D-98. **Both-theme capture is complete** — twelve screenshots in `design-screenshots/stage-10/`, covering the six required views. Rendering them surfaced two defects the suite could not see (an undefined `.risk-text` class, so an unsupported Commit carried no risk treatment; and evidence named as a machine `rule_key` rather than the written explanation the checker already returns), both fixed. D-102. Live keyboard tab-through is still not verified; see `design-screenshots/stage-10/VERIFICATION.md`.

**Stage 10 adversarial hardening — migration 0029.** Raw-SQL and restore paths now enforce Valence-only review/status/roster ownership, update-time account scope for asks and feedback occurrences, immutable applied escalation rules and feedback touches, renewal outcome scope, and a closed generated-source type vocabulary.

**Stage 10 external-review remediation — migration 0030.** Leadership wins exclude churn/contraction and show them as headwinds; forecast totals compute dated Closed actuals and withhold unknown units; calibration distinguishes not-closed from unresolved; the no-surprises validator enumerates every eligible red origin and append-only time-boxed exclusions; current-contract and same-severity escalation rules hold at the database boundary; all five derived ask treatments reach Today; held-review and exclusion controls are usable; Stage 9 Portfolio Analytics is reachable; and the Internal JSX views are formatted for review. The focused Stage 10 suite now has nine adversarial tests, including two-period calibration, two-account feedback, frozen snapshots/documents, exact-unit totals, reverse no-surprises, terminal asks, held reviews, and a socket-level no-outbound guard.

The §0 pre-existing export/search gaps are closed. The export registry now covers the full account graph through migration 0025—including the intentional opportunity/ask-calendar cycle and Stage 9 learning records—and is guarded by schema introspection; source-citation discovery and search cover Stage 9 records. Operations remains intentionally lightweight but now reports every connection boundary from the executable registry.

**Stage 5.5 hardened after adversarial review (2026-07-31, D-86).** Eleven findings, all reproduced, all fixed — most importantly a **reintroduction of the D-82 account-scoping bug** (an account-wide value target read another account's observation) and a rollup that counted superseded partition generations, reporting 1,100 addressable seats against a 1,000-FTE partition. Also: cross-account whitespace cells, a failed supersede destroying the bar, the unallocated remainder bypassing the FTE cap, unvalidated "typed" links, a fiscal map that was stored and ignored by back-scheduling, and export dropping headcount provenance. The cohort floor was partially rebuilt: metric values for sub-floor populations are now suppressed (the real control, previously absent), while density suppression is documented as a display convention rather than privacy — its operands were always visible.

**Expansion review follow-up (2026-07-31, D-93).** The cohort privacy floor now applies at both ingress and every generic metric read boundary, not only inside the value ledger: direct/CSV ingestion refuses newly identified sub-floor populations, and legacy rows return explicit suppression metadata with null values/targets in account lists, scoreboard/sparklines, observation history, QBR, and signal evaluation. Source-citation discovery also retains population-only observations instead of requiring a program join.

**Stage 9 review hardening (2026-07-31, D-94).** Cell shape is now observed rather than authored: entry tags snapshot the transitioned view, tagless segment cells cannot compare as exact audience shapes, and misleading supplied tags are rejected. Only real derived-state transitions prompt learning, velocity uses the latest qualifying Proven episode, and plays promoted from the library are scoped to cells matching their linked evidence instead of firing against every expansion signal. A UTC/local-date mismatch in the Stage 7.5 renewal test was also removed after the full validation run exposed its evening-only one-day failure.

**Six Stage 1-5 defects fixed from an adversarial review (2026-07-31, D-85).** Cross-account onboarding (A's launch pack could seed B's program), a partial write leaving an orphan program on a bad kickoff date, `fill_placeholder` creating a duplicate person instead of filling the placeholder, accept-then-reject corrupting the audit trail, duplicate key-date capture proposals, and one job drain burning two retry attempts against its own documented contract. A seventh finding ("association can mix account and program") **did not reproduce** — `association.resolve` returns a consistent account/program pair — and was rejected rather than "fixed." Regression tests in `tests/test_review_fixes.py`. Three of the six are the same shape as the QBR bug below: look a row up by id, never check it belongs where the caller says.

**Two client-facing QBR defects fixed (2026-07-31, D-82).** `output_gen.qbr` was selecting metric observations with no account scoping — one account's QBR could render another's numbers — and was including open commitments without the `client_visible` promotion filter that `mutual_action_plan` applies. Both are trust-boundary violations in a client-facing generator, and neither was caught by the suite; one existing test was in fact asserting the buggy behavior. Fixed with regression tests verified to fail against the pre-fix code.

**Running backend test count: 369** (was 67 at Phase 2 close). Backend still requires Python 3.12 (`.venv/bin/python -m pytest`).

## How to run / seed / test

Repo lives at `~/Desktop/Claude Projects/valence-os` (moved out of `~/Documents`, which is macOS-TCC-blocked — do not move it back). Backend is Python 3.12 + FastAPI + raw `sqlite3`; frontend is React (Vite).

```bash
# Backend (from backend/)
.venv/bin/python -m uvicorn app.main:app --port 8000
#   ^ run uvicorn as a module. The .venv/bin/uvicorn console script has a stale
#     hardcoded shebang from before the repo moved and will fail — use -m uvicorn.

# Seed / reset mock data (from backend/)
.venv/bin/python -m app.seed --reset      # wipe DB, apply migrations, load mock accounts
.venv/bin/python -m app.seed              # load into existing DB

# Tests (from backend/) — 584 tests, all green
.venv/bin/python -m pytest
#   ^ with -q this prints no "N passed" summary line; run it bare (or read the exit code).

# Frontend unit tests (from frontend/) — 103 tests over the pure JS modules, all green
node --test src/*.test.js
#   ^ pure modules only. There is no React renderer and no jsdom here, so a passing suite
#     says nothing about whether a surface renders — render it before calling a slice done.

# Frontend dev (from frontend/) — Vite on :5173, proxies API to :8000
npm run dev
npm run build                             # emits frontend/dist, served by the API in prod-ish mode
```

- DB path override: env var `VALENCE_OS_DB`; default file `valence_os.sqlite`.
- Migrations live in `backend/migrations/` as numbered `NNNN_*.sql`. The runner in `app/db.py` applies any file whose version isn't in `schema_migrations`. **Every schema change is a migration — no manual DB surgery.** Latest is `0045_email_thread_identity.sql`.
- Git: commit as `git -c user.name='Sam' -c user.email='noreply@example.test' commit`, trailer `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`, then `git push -q origin main`. Private repo `github.com/GBB94/valence-os`, `gh` authed as `GBB94`.

## What's built (by module → doc section)

Backend routers are in `backend/app/routers/`, frontend views in `frontend/src/views/`. The table below is the pre-Phase-3 foundation (migrations 0001–0010); completed Phase 3 and Expansion Engine additions are migrations 0011–0025 and are summarized above.

| Area | Doc | Built |
|---|---|---|
| Capture / interactions / inbox | §5A, v0.1 | interactions, source references (link-first), capture inbox → convert-without-retype |
| Execution objects | §5B, v0.2 | commitments (two owners), tasks, risks, issues, decisions, milestones — soft-delete, close/resolve flows |
| Attention queue | §5C, v0.3 | rules-based, explainable ranking; stakeholder-coverage sidebar |
| Output generators | §5D, v0.4 | weekly team update, QBR — **client-safe by construction** |
| Commercial & deployment | §5G–J, v1 | expansion opportunities (staged budget), contract versions (canonical + overlay), phase gates, deployment moments, compliance items, scope changes, governance |
| Data & evidence | §5K–L, v2 | metric definitions + observations (freshness → stale renders **unknown**), versioned/sourced benchmarks, value-story library (incl. negative evidence), CSV import (preview/commit/rollback), operations screen |
| Visualization | §6b, v3 | stakeholder graph (Cytoscape), budget waterfall (Recharts), sparklines + bullet charts, timeline swimlanes |
| AI & automation | §5M, v4 | **pluggable** transcript extractor proposing structured updates for per-item accept/reject; plays trigger engine; notifications |
| Global search / cmd-K | §6 | SQLite FTS5 (migration 0008) |
| Portfolio export/restore | — | account export/import bundle |
| Mutual Action Plan | §5N | client-visible ★ promotion flag (migration 0009); MAP assembled from promoted items only |
| Files & context library | §5O | link-first, searchable, **tagged** source references + who-cites-each (migration 0010 = tags) |

The pluggable extractor (`app/extractor.py`): `get_extractor(backend)` returns a **mock** or an `api` backend; manual paste has its own endpoint. All three funnel through `validate_proposals()`, a strict predefined mutation set. **The mock extractor is the only one wired.** The `api` backend code exists but is dormant — see gated items.

## Design system & information architecture (2026-07-30 redesign)

The frontend was fully redesigned to **`DESIGN-GUIDE.md`** (repo root), which is now the standing design authority and **supersedes scoping-doc §6**. Read it before any frontend change. Highlights a future session must respect:

- **Tokens are law.** `frontend/src/tokens.css` is the single source of raw values (both theme palettes, `--sp-*` spacing, radii, type, motion). No raw hex or arbitrary pixels outside it. The one exception: canvas/SVG charts resolve tokens via `getComputedStyle` with a mirror-value fallback (SVG/canvas attributes can't take `var()`).
- **Fonts are self-hosted** (vendored IBM Plex woff2 under `frontend/src/assets/fonts`) — no CDN, no font npm dependency.
- **Three-state theme** (System/Light/Dark) via `data-theme` on `<html>` + a pre-paint script in `index.html`. Both themes are first-class; a change that only works in one is not done.
- **Navigation is four destinations** — Today, Accounts, Library, Operations — plus the **account workspace** (sticky context header + eight tabs: Overview, Ledger, People, Plan, Commercial, Evidence, Outputs, Internal). Program is a filter, not a nav branch. Capture is global (`c` shortcut / top bar), never a destination. Don't add a top-level destination without asking.
- **The Ledger** (`frontend/src/views/Ledger.jsx`) is one merged chronological master-detail table (interactions + execution objects + untriaged capture). **Today** is grouped by urgency band with the attention rail.
- **Freshness language** (`AgeChip`, `Unknown` in `ui.jsx`) appears on dated records; stale metric-derived values render Unknown, never carried-forward — this is a trust boundary, not decoration.
- **Colour carries meaning only:** status hues (green/amber/red) for state, the indigo accent for interaction, financial tokens for the waterfall (the single exception; it never shares a screen with status). State never rides on colour alone — badges pair colour with a shape.
- Shared primitives live in `frontend/src/ui.jsx` (`Btn`, `Badge`, `Card`, `PageHeader`, `SegTabs`, `Tooltip`, `AgeChip`, `Unknown`, `SlideOver`, `Empty`).

The redesign shipped as eight stacked PRs (`redesign-a-foundation` … `redesign-h-close`, PRs #1–#8). It changed **no backend, no behavior, and no schema**, and the §2 trust boundaries were re-verified (67/67) after the restructure. Open audit item: an automated contrast/keyboard pass in both themes (the browser extension wouldn't connect during the build, so verification was by build + review + a manual click-through).

## What's deferred, and why

- **Job table + in-process worker (§7/8).** ~~Deliberately not built.~~ **Built in Phase 3 Task Zero** (migration 0011, `app/jobs.py`; env-gated auto-worker `VALENCE_OS_WORKER`, default off — tests drive jobs synchronously). The Phase 3 spec made it a prerequisite because transcription/email-sync/association/scheduled generation are background work. This deferral is retired.
- **Real external connections stay mock.** Every external touchpoint is a local/mock adapter — the **real Claude-API extractor** (`api` backend in `app/extractor.py`) is present but fails closed behind `app/connections.py`; email/transcription/calendar/enrichment/notification adapters remain local/fixture-backed. Flipping any switch requires the Valence hosting/data-handling conversation, a new `decisions.md` entry, and both approval configuration values defined in `CONNECTIONS.md`. §12 decision #3 (may AI call an external LLM?) is still open. **Do not wire any external API, key, or real source.**
- **No numbered implementation stage remains.** Stage 10 is complete; production connections remain gated.
- **§11 "declined" items.** Stay declined. Do not reintroduce them as "improvements."

## Gated on the five open decisions (§12)

None of these block the current mock-data build; **all** must be answered at Valence before production architecture that's expensive to reverse:

1. Store complete transcripts, or only references/summaries/approved extracts?
2. Which systems are canonical for CRM, usage metrics, contracts, client docs?
3. May AI processing call an external LLM, or must it use an approved Valence service/environment? _(blocks wiring the real extractor)_
4. Approved internal stack: identity, hosting, database, storage, logging, backups?
5. Personal tool, or a credible path to other Engagement Managers using it?

Production-mode items (SSO/MFA, approved hosting/DB, encryption at rest, off-site backups) are gated on these plus hosting approval. Don't build them speculatively.

## Invariants a future session must not break

These are enforced in code and in tests. If you touch nearby code, keep them true:

1. **No individual product-usage data, ever.** No table, column, or field for a named individual's usage of the Nadia product. Champion engagement = deployment engagement (meetings, comms, advocacy), never product usage. Cohort usage is aggregate only. Guarded by `test_capture_v0_1.py::test_no_individual_usage_field_anywhere` — do not weaken it.
2. **Client-facing output is safe by construction.** Team update, QBR, and MAP generators include only affirmatively promoted / non-negative records, enforced in the generator code, not by convention. Internal-only fields are never even queried into a client artifact. (Tested: a planted "INTERNAL" record never appears in output.)
3. **Stakeholder assessments carry a date + evidence.** Stance, influence, relationship strength always require an assessed-on date and an evidence note.
4. **Mock/synthetic data only.** No real client names, people, transcripts, or figures anywhere — including tests, seeds, comments, commit messages.
5. **No hard-coded benchmarks.** Benchmarks are data: versioned, sourced, with population and period. Stale metric-derived indicators render **unknown**, never carried-forward good state. Metrics are ingested, never recomputed.
6. **Scope follows the authority chain.** Phase 3 and Expansion Engine work through Stage 9 is complete. Stages 10–13 follow `INTERNAL-OPS-SPEC.md`, `ADOPTION-CAMPAIGN-SPEC.md`, `ACCOUNT-COPILOT-SPEC.md`, and `ADOPTION-COMMS-SPEC.md`. New objects or fields outside the additive specs still require asking Zach first; the `stage-0/field-dictionary.md` fence applies where the specs are silent.
7. **Stage discipline.** Build one numbered stage at a time. Each stage lands with tests, both-theme screenshots, a `decisions.md` entry, and a HANDOFF update before the next begins. If the browser surface is unavailable, record the missing visual/keyboard evidence explicitly rather than claiming it. (The old "do not build absent a new instruction" rule is superseded — the standing instruction is to build to feature-complete in the spec's order.)

## Where to look

- `PHASE-3-SPEC.md` + `EXPANSION-ENGINE-SPEC.md` — completed scope through Stage 9.
- `INTERNAL-OPS-SPEC.md` — **implemented additive scope authority** for Stages 10.0–10.5.
- `ADOPTION-CAMPAIGN-SPEC.md` — **implemented additive scope authority** for Stages 11.0–11.2 (D-99–D-104). Its §5 measurement contract is the binding, non-obvious part.
- `ACCOUNT-COPILOT-SPEC.md` — **implemented additive scope authority** for Stages 12.0–12.3 (D-105/D-106). It is a mock-only, read-only workflow layer; a real model remains a separate governance decision.
- `ADOPTION-COMMS-SPEC.md` — **implemented additive scope authority** for Stages 13.0–13.2 (D-108/D-109). Sequences are plans over canonical comms records; attendance is cohort-scoped deployment engagement, never product usage.

**Stage 11.0 — done.** Adoption campaigns (migration 0031, `app/campaigns.py`, `app/routers/campaigns.py`, `Campaigns.jsx` in the Plan tab). A campaign is a time-boxed intervention against one stable cohort; it links to existing tasks, comms, moments and documents rather than cloning them, and plan state is derived from the linked record so it cannot disagree with the Ledger. The measurement contract is the substance: the baseline locks a **series** not a point, comparators are enforced disjoint from the treated cohort at both trigger and API, signal-triggered pre/post carries the regression-to-the-mean caution, a rolled-back baseline renders `invalidated`, sub-floor cohorts suppress, and a finished campaign is measured at its own window and judged for freshness as of the date it was reviewed. Cautions are structured records rendered beside the number, never below the fold. Status has no generic patch — each transition is its own reason-logged endpoint writing append-only history. Search and export/restore are wired. Screenshots in `design-screenshots/stage-11/`. D-100.

**Stage 11.1 — done.** Orchestration (migration 0032). A signal episode converts to a **draft** campaign and never a running one; the episode carries a nullable `adoption_campaign_id` rather than a second association table, and a partial unique index enforces one campaign per episode so a recurrence may only propose again after the condition clears. Signal-triggered campaigns default to a comparator design, and choosing pre/post in that flow warns inline. Exactly one Today item per campaign (`campaign_evidence_gap`), raised only when a checkpoint is due *and* evidence has gone quiet — linked tasks keep their own items and are never duplicated. Plan adjustment supersedes rather than deletes, recording the replacement, reason, date and checkpoint, and never touching the hypothesis or locked baseline. D-101.

**Stage 11.2 — done.** Migration 0033 adds immutable retrospectives and per-intervention verdicts; matching uses frozen completed-campaign shapes and the Stage 9 exact/tag/use-case ranking rules. Portfolio learning reports counts and denominators, never account/person rankings or a health score, and now renders in Operations. Search, export/restore, seed, campaign panels, and both-theme campaign screenshots are wired. D-104. **Reconciled after a concurrent duplicate build (D-107):** the Stage 9 ranking is now called via `stage9.rank_shape()` rather than inlined a third time, and a retrospective must carry a verdict for every plan item — `skipped` included — because omission, not deletion, is how a failed intervention disappears from `§9`'s realization counts.

**Stage 12.0–12.3 — done, rendered.** Migration 0034 replaces the generated-document kind CHECK with governed `document_kinds`, versions writing styles and Copilot configurations, and freezes runs, snapshots, claims, citations, and append-only corrections. Scoped FTS and material-change readers constrain SQL before hydration; readers expose only allowlisted native fields, quarantine instruction-like prose, suppress stale/private numbers, and reuse Today without creating a second priority order. Exact names, governed aliases, bounded fuzzy candidates, and same-scope follow-up context are inspectable. “What changed” starts at the latest explicitly reviewed cursor. The panel opens frozen source fields before canonical navigation and previews style-linted internal notes before any document write; client-audience parameters are rejected. Operations owns correction review plus evaluated configuration activation and rollback. The 13-case golden suite executes through ordinary jobs and blocks activation on any hard-gate failure. **322 tests pass; frontend lint and production build pass.** No real model or outbound action exists. D-106. **A later session drove the panel live in a real browser** (D-107): `fact` returned a cited claim with an "Answer with gaps" coverage badge and no numeric confidence, `changes` abstained rather than answering from generic context, `weekly` cited every suggested move and carried "do not auto-send", and both themes resolve with body contrast 15.8:1 dark / 16.9:1 light. **Rendered and captured 2026-08-05** (D-166…D-168): four both-theme PNGs of the `fact` and `changes` runs; panel contrast measured over 20 text nodes per theme, light floor 5.85 / dark floor 8.38, none under 4.5:1; no numeric confidence badge in either theme. The pass found **two real defects, both fixed** — a `||`-over-a-nullable-column in the change feed that killed every `changes` run with a bare `failed` badge and no reason, now COALESCEd and backed by a schema-introspection test that asserts the rule rather than the two columns, plus a fail-closed guard so an unreadable item is named and downgrades coverage instead of aborting the run; and an answer body that rendered raw markdown, now parsed into block elements with text-node children (not HTML — retrieved prose is untrusted). Focus containment and Escape were exercised; native tab traversal order still cannot be driven, as no hardware key primitive is exposed. Outstanding: a narrow-viewport pass and a rendered conflicted/disambiguation response. See `design-screenshots/stage-12/VERIFICATION.md`.

**Stage 13.0–13.2 — done, rendered.** Migration 0035 adds one plan object (`comms_sequences`) while preserving `comms_entries` as the canonical wave. Planned `send_date` and operator-recorded immutable `sent_at` are distinct; status and downstream expected dates derive from facts, duplicate numbers/cross-sequence predecessors/cycles are rejected, and one late sequence raises one Today row. Webinar and office-hours events link to the invitation wave. Attendance counts only explicit audience attendees, excludes facilitators/observers, and withholds unknown, incomplete, unknown-size, or sub-floor readouts. Search, Operations counts, audit, seed, export/restore, the Plan panel, and campaign-derived wave state are wired. **334 backend tests pass; frontend lint and production build pass.** The seeded API returns a running two-wave sequence and a known `19 of 25` webinar readout while excluding its facilitator. **Rendered and captured 2026-08-05** (D-169…D-171): three both-theme PNGs, with **all four** attendance treatments drawn in one view — `known` (`19 of 25 attended`), `unknown` (no linked invitation wave), `incomplete` (an unclassified attendee role), and `suppressed` (invited audience 8 below the account floor of 25). Three mock sessions were added to the seed so each is reachable in the running app, because a withheld readout that has never been drawn is not verified. Every withheld row renders in the cross-hatched `.unknown-fill` treatment with a text label and a stated reason, in both themes — no status hue, no state by color alone. Card contrast measured over 62 text nodes per theme: light floor 4.82, dark floor 4.87, none under 4.5:1. The pass found **one real defect, fixed**: the shared `SlideOver` never restored focus to the control that opened it — it re-captured its opener from inside the panel and fired the restore at a detached node — now captured during render and guarded on `isConnected`, with the same rule applied to `CopilotPanel`; verified live on four callers. Outstanding: a narrow-viewport pass, and submitting a create through the sequence/wave slide-overs. Reported but not fixed: `Field` gives inputs no programmatic label (app-wide and pre-existing, four copies), and `CalendarPanel` prints an uncapped attendee list. See `design-screenshots/stage-13/VERIFICATION.md`. D-109.

**Test clock discipline.** `test_internal_ops.py::test_today_derives_policy_commit_warning_and_delivered_evidence_gap` failed reproducibly at three consecutive commits (including Stage 10's own) while UTC sat past the local date boundary, then passed again. Cause: fixtures derived dates from the *local* clock while the code and SQLite's `date('now')` use UTC, so between 20:00 and midnight US time a fixture is a day behind the system under test — tests pinning an exact boundary (`needed_by = today`) fail every evening and pass every morning. The Stage 10 session landed `tests/conftest.py` with a shared `utc_day()` helper while this was being written, which is the right fix: one clock for fixture and code.

**Stage 15.0–15.1 (RR-0/RR-1) — done.** `RELATIONSHIP-READINESS-SPEC.md` is the additive authority (D-139). Migration 0041 adds versioned `readiness_pillar_definitions` / `readiness_requirement_definitions` (6 pillars, 15 requirements) with at-most-one-live-version partial indexes and retired-pillar triggers. `app/readiness.py` is a query-time projection — it writes nothing, stores no state, and produces no composite score — resolving `(evaluator_key, evaluator_version)` against a hard-coded allowlist so a definition row configures an evaluator but can never create one; an unknown key fails closed into `coverage: partial` naming the missing evaluator. Four routes in `app/routers/readiness.py` (summary, pillar detail, definitions + allowlist, upgrade preview that applies nothing). `Readiness.jsx` renders compact (≤3 required gaps, ordered conflicted→unknown→thin, with an accent "N more" into the full in-scope set) inside the command center's Operate lens, and a detail slide-over showing every component's evidence, provenance, definition-of-done, and gap.

The three rules to preserve when touching this: **do not call `people_core.effective_role`** (person-scoped, so a champion validated in one program would read as a champion in all of them); **do not trust `people_core.resolved_layer`** for the breadth spread (it defaults per role, so three unassessed people would span three "layers" from defaults alone); and **state and freshness are independent** — each component carries its own window. Both `people_core` defenses live in versioned evaluator config (`require_explicit_layer`, etc.), not in code, so changing either is a definition upgrade with a previewable blast radius.

Two defects were found only by a live smoke test, not by the 32 tests written first, and both now have regression tests: an account-scoped pillar read `optional` in the all-programs view (no single phase to read), which would have let compact mode silently drop a required budget-owner gap — account scope now takes the **strongest** applicability across live programs; and that path then raised on the phase it could not name. **403 backend tests pass; frontend production build passes.** Both themes verified live on the seeded account (compact card and detail slide-over, `acc-terravance`). Note `AccountDetail.jsx` is dead code — the Overview tab renders `AccountCommandCenter`; anything added to the former will never render.

**Account Path Slices 1–2 — done (2026-08-04, D-141/D-142).** `ACCOUNT-PATH-SPEC.md` is the authority; Slices 3–7 remain proposed and unapproved. **No migration and no new table** — `GET /api/accounts/{id}/execution-path` (`app/execution_path.py`, `app/routers/execution_path.py`) is a query-time projection running eleven independent source adapters over canonical records. A failing adapter names itself in `coverage.omitted_sources` instead of blanking the page and can never suppress canonical work; a test counts `audit_events` around a request to assert the endpoint writes nothing.

Ranking is **8 deterministic bands with a 4-part tie-break** (band → has-due → due date → recorded time → stable id), and the band ships on the wire so the client groups without re-ranking. Band 7 is a *promotion* of residual band-8 work linked to the latest interaction, not a parallel rule. Snooze reuses the queue's `attention_state` overlay through `queue.snoozable_object_type()` / `keys_for_objects` / `suppression_state` — Account Path has no suppression store of its own — and a `phase_gate_item` ships `snooze_key: null` (no `_object_table` entry) rendering `Open source` instead of a button that would 422.

Frontend: `views/AccountPath.jsx` renders the orientation band (Next best move + program lanes) and the execution groups inside the Operate lens; `src/accountPath.js` holds every presentation rule as a pure module (15 tests) because the harness is `node --test src/*.test.js` with no React renderer. **The Operate lens's "Needs action" list was deleted, not moved** — it ranked the same records a second way. Only a `phase_gate_item` carries a `phase`, so the phase filter narrows to gate items and says so in a callout rather than reassigning work to a phase its record never claimed.

**444 backend tests pass (41 in `tests/test_account_path_slice1.py`); frontend 31 tests, lint, and production build pass.** Both themes, a 620px width, contrast (floor 4.80), focus, and reduced motion verified live — `design-screenshots/account-path/VERIFICATION.md`.

**Account Path Slice 3 — done (2026-08-05, D-143).** Approved by Zach; Slices 4–7 were approved the same day and are also built (see their own sections above). This is the first Account Path slice with a migration. **0042 adds six tables and none of them stores an evaluation**: `readiness_playbook_definitions` / `readiness_playbook_entries` (versioned templates), `readiness_plans` + `readiness_plan_instances` (a scope's live plan and the requirements it schedules), `readiness_exceptions` (governed `not_applicable` and waivers), and `readiness_checklist_requirement_map`. A schema-introspection test walks all six and fails on any column named or suffixed `state`, `met`, `freshness`, `coverage`, `applicability`, `score`, or `weight` — a cached evaluation would be the second source of truth `RELATIONSHIP-READINESS-SPEC.md` §2 forbids.

The line to hold: **a plan says when something was expected; readiness says whether it is true.** A due date rides beside the four readiness axes and may say `overdue`, which is a claim about the plan. A legacy checkbox becomes `recorded_complete`, never a state. A suppression is subtractive and reported, never dropped — a fully-suppressed pillar returns `not_applicable` rather than `met`, and `suppressed_count`/`waived_count` ship on the wire. Unlike readiness definitions, **playbook versions do not retire each other**: an account stays pinned to the version it instantiated, so `enterprise-launch` v1 and v2 both ship live and an upgrade is an explicit previewed action (`preview_upgrade` returns additions, removals, timing, definition, and necessity changes and writes nothing).

`app/playbooks.py` (instantiate / preview_upgrade / apply_upgrade / set_exception / revoke / merged_plan), `app/checklist_compatibility.py` (exact `template_key` matching only — label matching is what §13.5.2 forbids; `na` *proposes* an exception and never applies one; nothing is deleted), `app/routers/playbooks.py`, and the plan layer in `execution_path.py::_requirement_rows`, guarded like every other adapter. Frontend: `src/requirementDetail.js` (15 pure tests) and `views/RequirementDetail.jsx` — the four axes in a fixed four-cell grid, never a combined badge, and **no status control**, asserted by `requirementControls()` enumerating every write as `navigate`/`create`/`governed` against a `native_record` or an `exception`.

Two traps for a future session. `readiness.evaluate(conn, account, program_id)` puts **all** pillars in the top-level `pillars` list when a program is given and leaves `programs` empty — matching a reading to its plan instance by `(program_id, key)` alone silently blanks every due date; use `_instance_for`, which adds `ctx.program_id` as a fallback scope *only* in single-program scope. And `audit_events.action` is CHECKed to `create|update|archive|convert|close` (migration 0001); a custom verb rides in the `after` payload as `"event"` rather than widening a constraint every reader depends on.

**Rendering it caught five defects the pure-module tests could not (D-144), and the pattern is worth carrying forward: three of them existed because `RequirementDetail.jsx` hand-rolled its action row instead of rendering `requirementControls()`, so the tests asserting the controls were not exercising the surface.** The worst was a vocabulary drift — `exceptionHistoryRows()` mapped `active`/`expired` while `playbooks._exception_status` emits `live`/`revoked`/`lapsed`, so a live waiver read as unrecognised and *lost its revoke control while still suppressing the requirement*. A test now reads `backend/app/playbooks.py` and asserts every status the Python emits has a label, and an unknown status fails closed and is never `live`. Also fixed: `View all N` clipped in the narrow aside and routing to a page that lists no requirements (it expands in place now); a suppressed requirement with no route back to its decision (the `<details>` disclosure over `suppressedRequirements()` is that route); a bare red due date with no word beside it (`planStatus().due_label`); and `.card`'s `overflow: hidden` clipping the vertical edges off the focus ring of every full-bleed row — `.readiness-row.clickable:focus-visible` now takes `outline-offset: -2px`, which also repairs the readiness pillar lists that class came from. **This harness has no React renderer or jsdom, so a pure-module test cannot see any of this; render the surface before calling a frontend slice done.**

Captures, the live contrast/focus/reduced-motion/620px audit, and the defect list are in
`design-screenshots/account-path/VERIFICATION.md`.

**474 backend tests pass (30 in `tests/test_account_path_slice3.py`); frontend 46 tests, lint, and the production build pass.**

**Stage 15 RR-2 — canonical proposal widening — done (2026-08-05, D-145/D-146).** Migration 0043 widens `extraction_runs` and `extraction_proposals` and **adds no table**: §6.1 explicitly forbids parallel `intake_runs`/`intake_items` and forbids hanging proposal payloads off `capture_inbox_items`. The split that matters is `intent` (create/update/link/close/no_change) from `target_type`; the old `mutation_type` fused verb and noun, which is why it could only ever create. `mutation_type` stays populated because `Extraction.jsx` still reads it (§6.5). `created_object_*` → `resolved_target_*`.

Three rules to preserve. **`intent` has a SQL CHECK; `target_type` deliberately does not** — the allowlist lives in `app/proposals.py` next to the native write path a target needs to be legal at all, so widening it is a code change reviewed beside that path, never a data change. It is a **pair** allowlist: `(intent, target_type)` is permitted together or not at all, because creatable does not imply updatable. **`link` and `close` are in the vocabulary and in the CHECK but disabled in Python** until Account Path Slice 5's typed relationship and governed closure contracts exist. **No proposal may assert a readiness state** — no `pillar`/`requirement_key`/`state`/`phase` column, no readiness target in the allowlist, and `FORBIDDEN_FIELDS` on the payload; readiness is a projection (D-139) and a proposal that could write one would fabricate evidence.

`app/proposal_review.py` separates the one binding check from the suggestions: `already_resolved()` is enforcement (repeated acceptance returns the existing target or a stable conflict, never a duplicate), while `match_candidates()` never blocks or merges — §6.7 makes matches suggestions, and a near-match that silently swallowed a proposal would lose work nobody saw. It **fails closed on scope**: several execution tables carry only `program_id`, so a run with no program returns no candidates rather than widening the query across accounts.

`app/proposal_read.py` is the combined review, and it **writes nothing** — a test counts `capture_inbox_items` across the whole flow. §0.5's realistic violation is not an INSERT but a merged response shape that flattens both stores into one row type and then needs a stored copy to stay aligned, so each side keeps its own `kind`, status vocabulary (`untriaged` is never restated as `proposed`), and command set. Grouping is by **run, not interaction** — a retranscription is a different source with a different content hash. The program filter is `AND program_id = ?` with no `IS NULL` fallback: a null-program run is account-level work, not work in every program. Counts are derived on every call; §6.5 suggested storing them and 0043 deliberately does not.

Two routes on the AI router: `GET /api/accounts/{id}/proposed-updates` (grouped by source then target type, with provenance, warnings, conflicts, and match candidates) and `.../proposed-updates/preview` (§8.1, capped at 3, matches skipped on purpose). `latest_source_preview()` picks the newest run **that still has unresolved proposals**, not simply the newest, or a fully-reviewed run would render an empty card while older proposals waited unseen. Review debt is **one queue item per account** at priority 3 on the existing derived-queue path (D-19) — per-proposal items would bury every other trigger the moment one transcript was extracted.

Frontend: `src/proposalPreview.js` (9 pure tests) and `views/ProposalPreview.jsx` in the Operate lens below readiness. The card offers **no accept/reject control** by design. A proposal is styled proposed-and-cited: new `.state-mark.draft` (dashed) and `.quiet`, never a status hue and never the accent.

**513 backend tests pass (20 in `tests/test_rr2_proposals.py`, 19 in `tests/test_rr2_read_model.py`); frontend 55 tests and the production build pass.** Both themes captured on the card and the combined review, contrast floors 5.44 light / 5.12 dark over 28 text nodes, no horizontal overflow — `design-screenshots/stage-15/VERIFICATION.md`. Rendering again caught what the pure-module tests could not: a duplicated date in the source line and card meta lines missing the card gutter.

**Adversarial review pass — done (2026-08-05, D-147).** An external review read RR-0/RR-1/RR-2 and the Account Path against their specs and found **seven defects the 513-test suite passed**. Every one was reproduced as a failing test before it was fixed — `tests/test_readiness_review_fixes.py`, 13 tests — and the shape they share is the thing to carry forward: not one was a crash. Each was the app stating something confidently that its own records did not entail, which is precisely the failure mode a green suite is worst at catching.

Three of them were in `readiness.py`. An **account-scoped pillar's evidence was filtered by the selected program**, so `budget_owner` read `met` on the account and `unknown` inside a program — `evaluate()` used one `_Ctx.program_id` for both scope selection and evidence loading, and `run(..., account_wide_evidence=True)` now separates them (the scope program still decides phase and applicability; program-scoped pillars are untouched and a test asserts they still differ per program). **`_freshness()` had no lower bound**, so a meeting dated 2099 produced a negative age, passed the window, and asserted a condition true today; `_engaged_people` and `_program_advocacy` were loading those future rows in the first place and now bound on `occurred_on <= as_of`. And **`preview_definition_upgrade()` diffed the current definitions against themselves** — it could only ever report "nothing changes". The candidate version is now plumbed through `evaluate(..., evaluator_override=...)`. Read the honest limit before extending it: `_PILLAR_EVALUATORS` is a registry **gate**, not a dispatch table, so no *allowlisted* candidate can produce a different answer until a v2 evaluator exists; the test asserts the override plumbing (an unregistered version fails closed to `unknown` and lands in `coverage.failed_evaluators`), not a transition the registry cannot yet produce.

Three were on the proposal path. **§6.7's optimistic concurrency was unreachable in the running app** — `target_id` and `expected_target_updated_at` were written by no production path, so `conflict_preview()` returned `None` for every drafted proposal and the placeholder fill patched whatever it found; the extractor stamps both at draft time now and a stale fill returns 409 `stale_proposal`. `updated_at` is second-precision, so a sub-second race is still undetectable — that is a clock limit, not the defect. **Accept-time overrides could name a foreign `account_id`/`program_id`**, writing one account's proposal into another; `_require_scope_of_run()` rejects that with 422 before any write. And **`already_resolved()` matched on fingerprint alone**, closing one program's proposal against another program's record — it carries `AND r.program_id IS ?` now.

**Migration 0044** closes the reverse direction of 0041's guard: 0041 blocked a live requirement against a retired pillar, and nothing blocked retiring a pillar that still had live requirements. Same illegal pair, easier path.

Also fixed: `RequirementDetail`'s create-action form read owners from the account detail, which by construction holds no internal colleagues (null `account_id`), leaving the internal-owner select permanently empty while a commitment cannot save without one — it fetches `api.persons` beside the account now, behind a liveness flag. The compact readiness empty state pointed at an affordance its own branch never renders.

**`design-screenshots/stage-15/VERIFICATION.md` carried a false claim** — that each `met` component *links* its evidence records. At the time it did not; `Readiness.jsx` rendered plain `<li>` items and `Add evidence` opened the generic Ledger. The bullet was corrected and a dated paragraph said plainly that §5.3's drill-through to the native record was unbuilt.

**That drill-through is now built (D-162…D-165).** `readiness._EVIDENCE_TARGET` sits beside `_ev()` — the single point every evidence item passes through — and maps eighteen kinds to a `(tab, subview)` pair stamped onto each item as `native_target`; `Readiness.jsx` exports one `EvidenceItem` that `RequirementDetail.jsx` also uses, so the pillar detail and the Slice-5 requirement panel share one implementation. Three things to know before extending it. **The map is an allowlist, not a derivation** — `account_field`, `program_field` and `source_reference` deliberately ship `native_target: null` and render as plain text, because their id is a column or a provenance pointer rather than a record id, and `test_readiness_evidence_targets.py` asserts those three *by name* so an unrouted kind must be a written-down decision rather than an omission. **The People tab's sub-panel is now navigation state**, not local state, because a `champion_candidate` was landing on People's default Map — the right tab, the wrong panel. And **`navigation.js` validates `section` per tab**, since it is one nav field shared by Commercial and People; a merged allowlist would round-trip `?section=pipeline` onto People and blank it. `setTab` was left alone on purpose — preserving `section` across a tab switch was tried and reverted. Both routes were clicked through live (`funding_pool` → Commercial/Funding, `advocacy_event` → People/Champions); both-theme captures and the measured contrast are the third section of `design-screenshots/stage-15/VERIFICATION.md`.

**Two open product decisions, deliberately not resolved in code:** the Operate lens renders a readiness card in both the sidebar and the main column, and the combined review's `View all` target may be the wrong surface. Both are judgement calls about what an operator should see. Also raised and deliberately kept: `execution_path.py`'s `data_current_through: now_utc()` — the path is a projection over a local DB with no ingestion lag, so generation time *is* source currency, `AccountPath.jsx` derives `today` from it, and omitted sources are already named separately.

**526 backend tests pass; frontend 55 tests, lint, and the production build pass.**
