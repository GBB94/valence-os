# Acceptance test — Stage 0 completion script

From Section 9: **Stage 0 is complete when a mock call can be captured, converted into a commitment and a risk, surfaced in the attention queue, reflected in the account history, and included correctly in a generated team update — without introducing any new object type.**

This is the concrete script. It runs on the seed data (`today = 2026-07-22`) and uses **only** objects in `field-dictionary.md`. The "no new object type" invariant is checked at the end. When v0 is built, this same script becomes the executable end-to-end test; here it is the paper version.

Actors: **Sam Rivera** (operator/internal owner), client people on **Terravance / Europe Deployment**.

---

## Step 0 — Preconditions
- Seed loaded. Object-type inventory frozen at: Account, Program, Person, StakeholderRole, Interaction, CaptureInboxItem, Task, Commitment, Decision, Risk, Issue, Milestone, SourceReference, AttentionState, AuditEvent. **No other types may exist after this test.**

## Step 1 — Capture a mock call
Operator uses **interaction quick entry**:
- Program = `prog-tv-europe`, type = `call`, date = `2026-07-22`, participants = {Lucia Moretti, Sofie Larsen, Sam Rivera}, `meaningful_touch = true`.
- `summary` = "Europe readiness call: Sofie will pursue DPO sign-off; works-council slippage now threatens the Sept go-live."
- Two ambiguous notes dropped to the **Capture Inbox** (no classification forced):
  - IB-1: "Sofie to secure DPO sign-off before any EU activation."
  - IB-2: "Works-council consultation may slip past September — go-live at risk."

**Assert:** one new `Interaction (int-new)` exists; two `CaptureInboxItem` rows, status `untriaged`, `interaction_id = int-new`. AuditEvent `create` logged for each. Objects created: 3, all existing types. ✅

## Step 2 — Convert IB-1 → a Commitment (no retype)
Operator converts IB-1 via the inbox:
- Target `commitment`; `description` pre-filled from IB-1 raw text.
- `responsible_party_id = p-tv-legal` (Sofie), `internal_owner_id = p-val-operator` (Sam — the never-null Valence owner), `due_date = 2026-08-15`, `status = open`, `source_interaction_id = int-new`.

**Assert:** `Commitment (cm-new)` exists with both owners set and a due date (success criteria); `CaptureInboxItem IB-1 → converted`, `converted_to_type = commitment`, `converted_to_id = cm-new`. No new type introduced. ✅

## Step 3 — Convert IB-2 → a Risk (no retype)
Operator converts IB-2:
- Target `risk`; `description` pre-filled; `severity = high`, `is_blocker = true`, `status = open`, `internal_owner_id = p-val-operator`, `source_interaction_id = int-new`.

**Assert:** `Risk (rk-new)` exists, open, blocker; `CaptureInboxItem IB-2 → converted → rk-new`. No new type. ✅

*(Steps 2–3 satisfy "converted into a commitment and a risk.")*

## Step 4 — Surfaced in the attention queue
Re-render **portfolio home**. The queue builder (deterministic rules, `attention-rules.md`) must now include:
- **cm-new** is not yet overdue (due 08-15) → appears under "open commitments" pressure only if overdue; here it does **not** surface as overdue (correct — it's not late). It *is* visible on the execution board.
- **rk-new** has `is_blocker = true, status = open` → **surfaces as an active blocker (priority band 2)**, with `because` = "Active blocker — works-council consultation may slip past September — go-live at risk (raised 2026-07-22)."

**Assert:** rk-new appears in the queue as a blocker with a non-empty `because`, correct age (0d), and next action "escalate / drive to closure." ✅
*(This satisfies "surfaced in the attention queue." The commitment is correctly surfaced by its execution board and will enter the queue automatically once `due_date` passes — verify by advancing the clock to 2026-08-16: cm-new appears as "overdue 1 day.")*

## Step 5 — Reflected in account history
Open **History**, filter Terravance → Europe (and by person = Sofie Larsen).

**Assert:**
- `int-new` appears at the top (newest first), showing summary + participants.
- It shows **back-references** to the records created from it: cm-new and rk-new (via their `source_interaction_id = int-new`).
- Filtering by person Sofie (participant) includes this interaction (via `interaction_participant`).
- The Europe program's derived `last_touch` = 2026-07-22 (from int-new), not hand-edited. ✅

## Step 6 — Included correctly in a generated team update
Operator hits **generate weekly team update** (Module L, internal). The generator assembles from live data for the week and **excludes internal-only records by construction** (raw notes, stakeholder judgments), enforced in generator code — not operator vigilance (Section 2 / CLAUDE.md).

Expected team-update content mentioning this thread:
- Under **New this week**: the Europe readiness call (int-new) — summary line only (its `raw_notes` are internal-only and excluded).
- Under **New commitments**: cm-new "Sofie → DPO sign-off before EU activation, due 2026-08-15 (owner: Sam)".
- Under **New / open blockers**: rk-new "Europe works-council consultation may slip — go-live at risk."

**Assert (correctness of the update):**
1. cm-new and rk-new appear. ✅
2. `int-new.raw_notes` do **not** appear anywhere in the output (internal-only). ✅
3. No stakeholder stance/evidence text (e.g. Henrik's "skeptic" judgment) appears — those default internal-only. ✅
4. No field for any named individual's product usage appears (schema makes it impossible). ✅
5. Output is **stamped**: "generated 2026-07-22, data current through 2026-07-22." ✅

## Step 7 — Invariant: no new object type
Compare the live object-type inventory to Step 0's frozen list.

**Assert:** identical set. The full flow (capture → commitment + risk → queue → history → team update) used only pre-existing types. **If this assertion fails, Stage 0 is not complete.** ✅

---

## Pass criteria (all must hold)
- [ ] A call is captured in under a minute via quick entry (Interaction + two inbox items).
- [ ] Both inbox items convert without retyping — one to a Commitment (two owners + due date), one to a Risk (blocker).
- [ ] The blocker risk surfaces in the attention queue with an explaining `because`; the commitment surfaces on schedule.
- [ ] The interaction and its derived records appear in account history with correct back-references and derived last-touch.
- [ ] The weekly team update includes the new commitment and risk, excludes internal-only content by construction, is freshness-stamped, and contains no individual-usage data.
- [ ] The object-type inventory is unchanged from start to finish.

When every box is checked against the running v0, Stage 0's completion test passes and v0 is done (Section 9: "v0 is done when the full acceptance script passes"). The four v0 slices each run their relevant portion: 0.1 = Steps 1; 0.2 = Steps 2–3; 0.3 = Step 4; 0.4 = Steps 5–6.
