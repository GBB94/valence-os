# Valence OS — Phase 3 end-to-end demo

This is the reproducible Stage 8 walkthrough for the Phase 3 definition of done. It takes one
brand-new synthetic account from assignment to a delivered expansion business case using only the
local app, fixture adapters, and mock data. The automated companion is
`backend/tests/test_phase3_stage8_connections_demo.py`.

## Reset and start

```bash
cd backend
.venv/bin/python -m app.seed --reset
.venv/bin/python -m uvicorn app.main:app --port 8000
```

Build the frontend first when `frontend/dist` is absent. Keep `EXTRACTOR_BACKEND=mock`; do not add
credentials. Open `http://localhost:8000` and keep Operations available as the final governance
check.

## 1. Assign and onboard the account

1. Create the synthetic account **Bluepeak Demo**.
2. Start its onboarding pack with Europe in scope, a kickoff 40 days before today, and program
   **Manager Enablement Launch**.
3. Paste this intake and review the proposals one at a time:

   > Met with Aisha Kone (Champion). They use Ascend as the incumbent.
   > Go-live target is 2026-10-01. What is the works-council timeline?

4. Accept the stakeholder and incumbent proposals. The explicit Champion role fills the seeded
   placeholder instead of creating a duplicate. Confirm that parsing alone wrote nothing.
5. Confirm seven milestones, three prep tasks, launch checklists, and six Europe placeholders.

Expected: the Plan is useful immediately; overdue checklist work and unidentified placeholders
appear once each in Today with a plain-language reason.

## 2. Identify one person and leave one exposure open

1. Open the Champion person created from intake, set title **VP of Learning** and email
   `aisha.kone@example-bluepeak.test`. Confirm it retained the placeholder's node ID and edges.
2. Leave the IT-security placeholder unidentified and past its find-by date.
3. Add Aisha's program role and a dated influence/relationship assessment with an evidence note.
4. Sync mock org-change enrichment. Confirm Aisha's synthetic title-change proposal; verify the
   person record changes only after confirmation.

Expected: People shows the known champion and the cross-hatched unknown position simultaneously;
the open placeholder remains in Today without masquerading as a stale relationship.

## 3. Ingest communications through the job table

1. In Ledger → Communications, sync the synthetic inbox.
2. Confirm Aisha's direct question is associated and flagged; the newsletter is not.
3. Mark Aisha's message responded and confirm its Today item clears.
4. Ingest `kickoff-call.txt` with attendee Aisha Kone and keyword `bluepeak`.
5. Ingest it again with an unknown attendee to show the low-confidence item landing in Capture.

Expected: every ingestion job succeeds; no extraction proposal writes a domain record before human
acceptance; the low-confidence association is visible instead of guessed.

## 4. Review extended extraction proposals

Run the offline mock extractor on:

> Our new VP of IT is Dana Okafor. Two other regions also want to roll out to their teams.
> Let's align the launch to the fall performance review. Manager activation improved by 20%
> in the pilot.

Review the source span for each proposal, then accept the placeholder fill, pull signal, deployment
moment, and value-story candidate individually. Keep the value story internal at first.

Expected: Dana fills the IT position, demand is attached to the account, the review moment appears
on Plan, and the story exists without becoming client-visible automatically.

## 5. Establish people coverage and evidence

1. Log an advocacy-without-us event for Aisha and advance her champion pipeline to Validate.
2. Leave a second candidate below Validate so the single-thread signal is honest.
3. Add a synthetic signed scorecard source, one aggregate population segment, an activation metric,
   its agreed target, and a fresh observation over the bar.
4. Promote only the sourced target/story/cell intended for client use.

Expected: People answers the layer, cadence, champion, path, and exposure questions with dated
evidence. The value ledger reads **realized**; stale or unscoped evidence cannot satisfy it.

## 6. Build the commercial path

1. Add a whitespace cell for the segment and move its facts with reasons from White → Proven.
2. Add a current synthetic contract, fiscal map, funding pool, and back-scheduled ask calendar.
3. Record a signed-paper operational agreement whose activation target unlocks a pre-priced seat
   band. Evaluate agreements.
4. Confirm one earned event fires, enters Today, and does not duplicate on re-evaluation. Action it
   to draft the expansion opportunity.
5. Fill the five qualification links: value target, budget owner, ask calendar, validated champion,
   and the program's compliance path. There is no score.
6. Add the opportunity as a sourced line on an account growth plan. Confirm the committed and
   probability-weighted views and the explicit unfunded gap.

Expected: Commercial answers where the next seats live, what evidence earned them, who funds them,
and every dated dependency to signature. An overlapping population would withhold the totals rather
than double-count.

## 7. Generate, review, and deliver artifacts

1. Generate a pre-call brief, kickoff deck, value review/QBR, champion kit, and expansion business
   case as drafts.
2. Export the value review/QBR as `.pptx` and verify its generated/current-through stamp.
3. Inspect the client artifacts: raw notes, stakeholder judgments, negative/internal stories,
   probability, competitive notes, and unsourced growth lines must not appear.
4. Review the expansion business case as **operator**, then mark it **sent**. This records delivery;
   the app transmits nothing.
5. Run plays, complete one fired run with an effectiveness note, and run the scheduled weekly update.

Expected: the business case is delivered with an auditable frozen body; the weekly update remains a
draft for review; the champion handoff date is recorded only when its kit is marked sent.

## 8. Renewal, governance, and final checks

1. Open the renewal center and confirm the T-minus timeline, value case, risks, fiscal context, and
   only fully qualified expansion opportunities eligible to ride the paper.
2. Open the mutual plan and verify it contains only promoted sourced joint fields.
3. Open Operations. Every boundary in `CONNECTIONS.md` must appear in local/mock mode. No real mode
   may be active without an approval decision reference.
4. Run the automated proof:

   ```bash
   cd backend
   .venv/bin/python -m pytest tests/test_phase3_stage8_connections_demo.py
   .venv/bin/python -m pytest
   ```

Pass means the account reached a delivered expansion business case, every background and adapter
step remained local/mock, the business case and QBR respected client-visibility construction, all
new records stayed account-scoped, the trust-boundary tests passed, and the capture flow was not
made slower.
