# Wireframes — v0 screens (rough)

ASCII sketches only, deliberately unpolished (the brief says rough is correct). These fix layout and information priority, not visual design. They follow Section 6: persistent left sidebar, compact top bar with global search, detail as slide-over, compact rows, keyboard-first (cmd-K), status color reserved for status. Six v0 screens: portfolio home, account/program overview, interaction quick entry, capture inbox triage, execution board, history.

Shared shell:

```
┌───────────────┬──────────────────────────────────────────────────────────────┐
│ ACCOUNT OS    │  ⌕ search…                             ⌘K  ·  Sam Rivera      │  top bar
├───────────────┼──────────────────────────────────────────────────────────────┤
│ ▸ Home        │                                                                │
│ ▾ Accounts    │                     [ main view here ]                         │
│   Terravance  │                                                                │
│   Northwind   │                                                                │
│   Bluepeak    │                                                                │
│ ─────────     │                                                                │
│ Execution     │                                                                │
│ History       │                                                                │
└───────────────┴──────────────────────────────────────────────────────────────┘
```

---

## 1. Portfolio home (the morning screen — Module A)

A ranked, explainable queue. Not a wall of charts (Section 6b). Each row states why, age, due, next action. Snooze/Resolve inline (no blocking modal).

```
Portfolio                                                   7 items · updated just now
────────────────────────────────────────────────────────────────────────────────────
PRIORITY  ITEM                                          WHY / AGE          NEXT ACTION
────────────────────────────────────────────────────────────────────────────────────
● overdue Terravance · cohort summary (commit.)         due 07-16 · 6d     close / chase   [snooze][resolve]
● overdue Northwind · nomination list (client commit.)  due 07-15 · 7d     chase client    [snooze][resolve]
▲ blocker Terravance/Europe · works-council pending      raised 07-12 · 10d escalate        [snooze][resolve]
▲ mstone  Terravance/Europe · go-live at risk           target 09-15       recover         [snooze][resolve]
· stale   Bluepeak · champion untouched                 37d no touch       reach out       [snooze][resolve]
· task    Northwind · SSO follow-up                     due 07-21 · 1d      do              [snooze][resolve]
· task    Bluepeak · scoping memo                       due 07-25          do              [snooze][resolve]
────────────────────────────────────────────────────────────────────────────────────
   ● = highest band   ▲ = mid   · = low        [ show snoozed (0) ]
```

Snooze inline expands a one-line control: `snooze until [date]  or  when [condition] ▸`. Refuses empty. Resolve requires closure or "link successor action ▸".

---

## 2. Account / program overview (Module B, v0 subset)

Account header with the **two statuses** (no renewal countdown / structured incumbent — those are v1). Program list below with phase, next milestone, top risk.

```
Terravance Agricultural Systems                                     [edit statuses]
────────────────────────────────────────────────────────────────────────────────
 Delivery:  ● on track     assessed 07-15 · "adoption to plan"       (7d ago)
 Commercial:▲ at risk       assessed 07-15 · "expansion unproven"     (7d ago)
 Incumbent: MentorWorks (note)                     last touch: 07-12
────────────────────────────────────────────────────────────────────────────────
 PROGRAMS
  Global Coaching Rollout      programmatic   next: —            top risk: —
  Europe Deployment            launch         next: go-live 09-15 top risk: works council ▲
  Seat Expansion (1k→3k)       expansion      next: —            top risk: —
────────────────────────────────────────────────────────────────────────────────
 [+ interaction]  [+ program]
```

Clicking a program opens its overview (same header pattern, program-scoped) as a slide-over; clicking a status opens the assessment editor (value, rationale, assessed_on, change condition). A status assessed >30 days ago shows a "reassess" warning (Section 1.7).

---

## 3. Interaction quick entry (the 30-second path)

One form. Minimal required fields. Auto-save; non-blocking toast. Ambiguous notes go straight to the inbox from here.

```
Log interaction                                                    esc to cancel
────────────────────────────────────────────────────────────────────────────
 Program     [ Terravance / Europe Deployment ▾ ]           Date [ 2026-07-22 ]
 Type        [ call ▾ ]                                       ☑ meaningful touch
 Participants[ Lucia Moretti ×] [ Sofie Larsen ×] [ + add ]
 Summary     [ Reviewed works-council packet; DPO terms open…            ]
 Notes       [ raw notes, internal only…                                 ]
 Source link [ paste transcript/recording URL (optional) ]
────────────────────────────────────────────────────────────────────────────
 To inbox (untriaged, triage later):
   [ + "Sofie needs DPO sign-off before launch"          ]
   [ + "Markus wants assurance on individual-usage"       ]
────────────────────────────────────────────────────────────────────────────
                                        [ save ]  ·  saved items → Capture Inbox
```

Only Program, Date, Type are required. Everything else optional; inbox lines require no classification.

---

## 4. Capture inbox triage (Module E view)

List of untriaged items. Convert without retyping → target's create form pre-fills from raw text.

```
Capture inbox                                                 2 untriaged · 0 aging
────────────────────────────────────────────────────────────────────────────────
 FROM                         NOTE                                   AGE
────────────────────────────────────────────────────────────────────────────────
 Europe call 07-22            "Sofie needs DPO sign-off before…"     0d   [convert ▾][dismiss]
 Europe call 07-22            "Markus wants assurance on indiv…"     0d   [convert ▾][dismiss]
────────────────────────────────────────────────────────────────────────────────
 convert ▾ → ( commitment | task | decision | risk | issue )
```

Choosing "commitment" opens the commitment form with `description` pre-filled, cursor on `responsible_party`. On save, inbox item → converted, linked to the new object.

---

## 5. Execution board (Module E)

Open tasks, commitments (both owners visible), decisions, risks/issues, milestones — program- or account-filterable. Compact rows.

```
Execution · Terravance ▾                              [ tasks | commit | risk | mstone ]
────────────────────────────────────────────────────────────────────────────────
 COMMITMENTS                          RESP → OWNER          DUE      STATUS
  send cohort summary                 Sam → Sam             07-16    ● overdue
  (client) nomination list [Northw.]  Owen → Sam            07-15    ● overdue
 RISKS / ISSUES
  works-council pending (blocker)     owner Sam             —        ▲ open
 MILESTONES
  Europe go-live                      —                     09-15    ▲ at risk
 TASKS
  SSO follow-up [Northwind]           Sam                   07-21    open
────────────────────────────────────────────────────────────────────────────────
 row click → slide-over detail with close/convert actions
```

Close actions capture date + closer + note inline (state-transition rules). Risk close forces a `close_reason`; issue resolve forces a `resolution_type`.

---

## 6. History / interaction timeline (Module D)

Chronological ledger, filterable by person or program. First-class output.

```
History · Terravance ▾   · person [ all ▾ ]                         newest first
────────────────────────────────────────────────────────────────────────────────
 2026-07-22  call     Europe        Reviewed works-council packet…   → 1 risk*
 2026-07-12  call     Expansion     Expansion economics; no 3k…      → 1 risk
 2026-06-28  meeting  Global        June steering forum              → 1 commit
────────────────────────────────────────────────────────────────────────────────
 * records created from this interaction shown as links (source_interaction_id back-refs)
 click a row → interaction detail (summary, participants, notes, linked records, source link)
```

Filtering by person uses `interaction_participant`; "records created from it" uses the `source_interaction_id` back-references on execution objects.

---

Notes on what's intentionally absent from v0 wireframes: stakeholder graph (v3), timeline/swimlanes (v1), metrics scoreboard (v2), commercial/waterfall (v3), QBR generator (v2), operations screen (v2). Not drawn, per "don't scaffold ahead."
