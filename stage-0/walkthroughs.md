# Walkthroughs — the four Section 1 scenarios on the seed data

Run against the seed accounts with **today = 2026-07-22**. Each step names the objects and fields it touches. Gaps/contradictions surfaced here are numbered **G1–G6** and collected at the bottom — surfacing these is the point of Stage 0.

Scope caveat: two of the four scenarios (pre-call prep's transcript search, QBR prep) reach into later-phase capabilities. Where a step needs something v0 doesn't have, it's marked **[out of v0]** and the gap is logged — the walkthrough still shows how far v0 gets.

---

## 1. Morning check (daily, ~2 min) — the portfolio home

Open **Module A portfolio home**. The queue builder computes items from the seed (see `attention-rules.md`), ranked:

| # | Item (`because`) | Trigger | Objects/fields touched |
|---|---|---|---|
| 1 | "Overdue 6 days — 'send anonymized cohort summary' due 2026-07-16" | overdue commitment | `Commitment cm-tv-cohort-summary` (status, due_date, responsible_party, internal_owner) |
| 2 | "Overdue 7 days — Northwind nomination list due 2026-07-15" | overdue commitment | `Commitment cm-nw-nominations` |
| 3 | "Active blocker — Europe launch pending works-council consultation" | active blocker | `Risk rk-tv-europe-works-council` (is_blocker, status) |
| 4 | "Europe go-live at risk — flagged, target 2026-09-15" | at-risk milestone | `Milestone ms-tv-europe-launch` (at_risk, status, target_date) |
| 5 | "No meaningful touch with Aisha Kone (champion) in 37 days" | stale stakeholder | `StakeholderRole sr-bp-1` + derived `days_since_touch` from `Interaction int-bp-intro` |
| 6 | "Open task — follow up with IT on SSO (due 2026-07-21, 1 day over)" | open task | `Task tk-nw-sso` |
| 7 | "Open task — draft Bluepeak scoping memo (due 2026-07-25)" | open task | `Task tk-bp-scope` |

**Act / triage / snooze each.** Example actions:
- Item 1: operator closes it after sending → `Commitment.status → closed`, `acknowledged_by`, `closed_on`, `close_note`. Item leaves queue.
- Item 4: operator snoozes to the next steering date → **AttentionState** row (`snooze_until = 2026-08-01`). Refused if no date/condition given.
- Item 5: operator resolves by scheduling a call → allowed only via a **linked successor** (a new Task "schedule Bluepeak check-in") because the underlying staleness isn't yet closed.

*Touches:* Commitment, Risk, Milestone, StakeholderRole, Interaction (derived last-touch), Task, AttentionState, AuditEvent (each change logged).

**No gaps** — v0 covers the morning check fully for the triggers whose objects exist. (Renewal-window, stale-import, and fired-play rows are simply absent, correctly, until v1/v2/v4.)

---

## 2. Pre-call prep (~5 min) — before the Terravance expansion call

Goal: prep for a call with **Henrik Vale (budget owner, skeptic)** on the expansion.

1. Open **Program `prog-tv-expansion`** overview → phase `expansion`, `expansion_hypothesis` ("grow ~1,000 → ~3,000…"), `problem_statement`. *Touches Program.*
2. "Who's on the call and what they care about": open **StakeholderRole sr-3** → role `budget_owner`, stance `skeptic` (dated 2026-07-12, evidence "won't fund 3k without measured outcomes"), `cares_about` "ROI per seat", `value_for_them`. *Touches StakeholderRole + Person.*
3. Scan **open commitments involving Henrik**: query commitments where `responsible_party_id = p-tv-budget OR internal_owner_id = p-tv-budget`. In the seed there are none directly on him — **G3**: commitments are program-scoped and person-linked only via the two owner fields, so "commitments involving a participant who is neither owner" (e.g. someone who agreed to something in a meeting but isn't an owner) aren't queryable. Acceptable for v0 (owners are the accountable axis), logged.
4. "Search for the last transcript where they spoke" → **[out of v0]**. v0 stores `Interaction.summary` + `raw_notes` + a `SourceReference` *link* to a transcript, but full-transcript search is FTS over stored summaries only (Section 8), and transcript *content* isn't ingested until v4. **G4:** pre-call prep's "last transcript where they spoke" is partially served (find the interaction + open the linked artifact) but not searchable by spoken content in v0. Logged; v0 delivers "last interaction Henrik attended" via `interaction_participant`.

*Result:* v0 supports pre-call prep for structured facts (phase, stance, owned commitments, last interaction). Transcript-content search is a v4 capability; the gap is expected, not a v0 defect.

---

## 3. Post-call capture (~1 min) — the 30-second rule under test

Just finished a call on the **Terravance Europe** program. Quick entry:

1. **Module: interaction quick entry.** One form: pick program `prog-tv-europe`, participants (Lucia, Sofie, Sam), date defaults today, type `call`, a line of `summary`, paste rough `raw_notes`. Save → **Interaction** created, `meaningful_touch = true`. *This is the whole required path — under a minute.*
2. Two things came up but aren't cleanly classified yet → drop each into the **Capture Inbox** as `CaptureInboxItem` (status `untriaged`) attached to the new interaction. No classification forced at capture time (Section 2 / principle 1). *Touches CaptureInboxItem.raw_text.*
3. Done. Last-touch for the Europe program and for Lucia/Sofie updates automatically (derived from the interaction) — **not** hand-edited.

**Timing check:** the required capture (step 1) touches only Interaction + participants; classification is deferred to the inbox. This honors "the 30-second capture rule wins every tie." **No gap.**

Later triage (not on the clock): open the inbox items and convert — e.g. "Sofie needs DPO sign-off before launch" → convert to **Commitment** (responsible `p-tv-legal`, internal owner `p-val-operator`, due date), pre-filled from `raw_text`, no retype. Inbox item → `converted`.

---

## 4. QBR prep (quarterly) — **[largely out of v0]**

"Hit generate, get a skeleton with metrics vs. targets, risk status, approved value stories, and open commitments pre-filled, stamped…"

Walking it against v0:
- **Open commitments pre-filled** → ✅ available (query open commitments by program).
- **Risk status** → ✅ available (open risks by program).
- **Metrics vs. targets** → **[out of v0]** — metric definitions/observations are v2. **G5.**
- **Approved value stories** → **[out of v0]** — value-story library is v2. **G5.**
- **Internal-only records excluded by construction** → the QBR *generator* is v2 (Module K); v0 has no client-facing generator. **G5.**
- The v0 output that *does* exist is the **weekly team update export** (Module L, internal) — see acceptance test.

**G5 (expected):** full QBR prep is a v2 capability. v0 deliberately ships only the internal team update. This is not a v0 defect — Section 9 sequences QBR after metrics and value stories exist. Logged so the boundary is explicit.

**Trust-boundary note (holds in v0 too):** even the team update export must exclude internal-only records by construction (raw notes, stakeholder judgments), enforced in generator code, not by operator vigilance (Section 2). v0's export honors this — see acceptance test step 5.

---

## Gaps, contradictions, and decisions surfaced

| ID | Type | Description | Disposition |
|---|---|---|---|
| **G1** | Scope tension | The brief's seed asks for "an expansion opportunity from ~1,000 → ~3,000 seats," but the **Expansion-opportunity object is v1**, not v0. | Modeled the expansion as a **Program in `expansion` phase** with `expansion_hypothesis` holding the target. No new object introduced. **Confirm this is the intended v0 representation.** |
| **G2** | Model gap | `Interaction.program_id` is required, but some interactions are **account-level** (exec relationship not tied to one program). | **Resolved 2026-07-22:** `program_id` nullable, `account_id` required on every interaction. Exec-level touches spanning programs are valid. |
| **G3** | Model limit | Commitments link to people only via the two owner fields, so "commitments involving person X" misses non-owner participants. | Accepted for v0 (owners are the accountable axis). No change. |
| **G4** | Phase boundary | Pre-call "last transcript where they spoke" needs transcript-content search (v4). | v0 delivers "last interaction attended" + linked artifact. Expected boundary. |
| **G5** | Phase boundary | Full QBR prep needs metrics (v2) + value stories (v2) + QBR generator (v2). | v0 ships the internal team update only. Expected boundary. |
| **G6** | Silent-in-doc | Delivery/commercial **status values are not enumerated** in the doc. | Proposed `{on_track, at_risk, off_track, unknown}` (PA-1). **Confirm.** |

The three that genuinely need your decision before v0.1 code: **G1**, **G2**, **G6** (and the proposed additions PA-1..PA-4 in the field dictionary). G3/G4/G5 are expected phase boundaries, logged for completeness.
