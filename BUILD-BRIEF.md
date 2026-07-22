# Account OS — Build Brief for Claude Code

You are building Account OS, an internal single-editor web app for managing Fortune 100 enterprise accounts. The full specification is in `Account-OS-Scoping-Doc.md` in this repo. Read it in full before doing anything. It is the source of truth, and three sections of it are binding constraints, not background: Section 9 (build order), Section 11 (declined items and the frozen-scope rule), and Section 2 (trust boundaries).

Also read `CLAUDE.md`, which contains the standing rules that apply to every session on this project.

## What to do first: Stage 0 only

Your first task is Stage 0 from Section 9 of the scoping doc. Produce the following as files in a `stage-0/` directory. Do not write any application code yet.

1. `entity-diagram.md` — objects and relationships, as a Mermaid diagram plus a short prose walkthrough. Only the objects named in Section 4 of the scoping doc.
2. `field-dictionary.md` — every field required for v0, and only v0. For each: name, type, required or optional, default, and which object it belongs to. If the scoping doc is silent on a field you believe is needed, list it in a separate "proposed additions" section at the bottom rather than adding it silently.
3. `state-transitions.md` — valid statuses for each stateful object and the closure rules from the "definitions of done" paragraph in Section 4. Include who or what can trigger each transition.
4. `attention-rules.md` — the portfolio queue rules from Module A: each trigger, its priority, what resolves it, and what makes a snoozed item resurface.
5. `seed-data/` — three realistic mock accounts as structured seed files (JSON or YAML). At least one must be multi-program. Model one on a large global agriculture-equipment manufacturer running a coaching deployment: a global rollout program, a Europe program blocked on works-council review, and an expansion opportunity from roughly 1,000 toward 3,000 seats. All names, people, and figures must be fictional. Do not use real client data anywhere.
6. `walkthroughs.md` — the four usage scenarios from Section 1 (morning check, pre-call prep, post-call capture, QBR prep) walked step by step against the mock data, naming which objects and fields each step touches. Where a walkthrough exposes a gap or contradiction in the model, flag it; finding these is the purpose of Stage 0.
7. `wireframes.md` — rough layout sketches (ASCII or Mermaid) for the v0 screens only: portfolio home, account/program overview, interaction quick entry, capture inbox triage, execution board, history view. Rough is correct; do not polish.
8. `acceptance-test.md` — a concrete end-to-end script implementing the Stage 0 completion test from Section 9: a mock call is captured, converted into a commitment and a risk, surfaced in the attention queue, reflected in the account history, and included correctly in a generated team update, without introducing any new object type.

**Then stop.** Present the Stage 0 deliverables and a list of every gap, contradiction, or proposed addition you found. Wait for approval before writing application code.

## After Stage 0 is approved: v0, in slices

Build v0 in the four slices defined in Section 9, and make each slice fully usable before starting the next:

- **v0.1 Capture:** accounts, programs, people, interactions, capture inbox.
- **v0.2 Execution:** tasks, commitments (responsible party + internal owner), decisions, risks, issues, milestones.
- **v0.3 Attention:** queue rules, snooze and resolution behavior, the two account statuses.
- **v0.4 Output:** history view, weekly team update export.

At the end of each slice: run the relevant portion of the acceptance test, show what works, and wait for approval before the next slice. v0 is done when the full acceptance script passes.

Anything in v1 through v4 (expansion opportunities, contracts, phase gates, metrics, visualizations, AI ingestion, plays) is out of bounds for now. Do not scaffold ahead for it.

## Stack

Python with FastAPI, SQLite (with versioned migrations from the first table), React frontend, per Section 8 of the scoping doc. Single in-process job worker when jobs become needed. No caching layers, no queues beyond the job table, no microservices, no Docker orchestration. The dataset is a few thousand rows; boring is correct.

## How to handle ambiguity

When the scoping doc is silent, prefer the smallest thing that passes the acceptance test, and log the decision in a running `decisions.md`. When the scoping doc appears to contradict itself, stop and ask rather than picking a side. When you want a new object type or a field outside the dictionary, ask; the scope is frozen and additions require justification against the rule in Section 11.
