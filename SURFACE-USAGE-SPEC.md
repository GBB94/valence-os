# SURFACE-USAGE-SPEC.md — surface usage and retirement evidence

**Status:** proposed, additive. Stage 17. Not yet approved; nothing here is built.
**Authority:** additive to `ACCOUNT-PATH-SPEC.md` §17 (local product measurement), which stays the
authority for the sink, the allowlist discipline, retention, and the §17.5 caveat. This document
extends that layer from *"was the recommendation acted on"* to *"which parts of this platform earn
their place on the screen"*. It adds no new sink and no new boundary.

---

## 1. Does this make sense?

Yes, and the machinery is mostly built. Migration 0050 already gives you a local `product_events`
table, a sixteen-event allowlist in `telemetry.py`, slug-only property values, a rotating session
token, no person identifiers, bounded retention, an off switch that discards what was collected, and
a `CONNECTIONS.md` row (`product_telemetry_sink`) recording that pointing it anywhere external is a
data-handling conversation rather than a config change. None of that needs rebuilding.

What's missing is that today's sixteen events measure **one feature** — the account path — rather
than **the platform's surfaces**. So the question "which parts do I not need" cannot be asked of the
data at all: most of the app emits nothing, and silence from an uninstrumented surface is
indistinguishable from silence from an unwanted one.

Three things about your situation change the design substantially, and it is worth being blunt about
them before the spec, because two of them are why the obvious build would mislead you.

**You are n = 1.** Every framework in the literature is built on *breadth* — what share of users
touch a feature. Pendo's finding that 80% of features are rarely or never used, the 5–10%-of-users
threshold, the "segment first, a 4% feature may be a daily ritual for your top ten accounts" warning
— all of it assumes a population. You have one operator and a synthetic dataset. Counting your own
clicks and calling it adoption would be measuring what you happened to demo last week.

The metric that survives n = 1 is **engagement given exposure**: of the times a surface was on your
screen, how often did you operate it. That is a within-surface ratio, not a cross-user comparison,
so a single operator does not weaken it. A card rendered 200 times and never once touched is a real
finding about that card whether one person or a thousand saw it. **That ratio is the primary signal
in this spec, and raw volume is deliberately secondary.**

**A low number has at least three causes and the data cannot tell them apart.** Microsoft's "usage
fallacy" post and UserVoice both land in the same place: a feature may go unused because it is
hidden, because it looks like it does something else, because it is hard to use once found, or
because it is genuinely useful in narrow circumstances that have not come up yet. Usage data is
*directional* — it says there might be an action here, not what the action is. So this spec never
renders a verdict. It renders evidence plus the competing explanations, and requires you to record
which one you believe, dated, before anything moves. That is the same discipline as a stakeholder
assessment carrying a date and an evidence note.

**Cadence is the trap.** A QBR surface used once a quarter and a dead surface look identical in a
30-day window, and today's retention is 90 days. Any report that shows both as "0 uses" has produced
a confident-looking lie. §6 makes the observation window a first-class axis that can withhold a
reading entirely.

---

## 2. What the research says, and what we take

**Sources:**
[Microsoft — The Usage Fallacy](https://learn.microsoft.com/it-it/archive/blogs/nadyne/the-usage-fallacy) ·
[Pendo — the art and science of removing features](https://www.pendo.io/pendo-blog/the-art-and-science-of-removing-features-from-your-product/) ·
[UserVoice — removing features](https://uservoice.com/blog/removing-features) ·
[Product Teacher — how to deprecate a feature](https://www.productteacher.com/articles/how-to-deprecate-a-feature) ·
[AppStudio — feature sunset decision framework](https://www.appstudio.ca/blog/feature-sunset-the-decision-framework-for-product-teams/) ·
[Segment Academy — naming conventions](https://segment.com/academy/collecting-data/naming-conventions-for-clean-data/) ·
[Amplitude — event taxonomy](https://amplitude.com/explore/data/event-taxonomy) ·
[Growth Method — object-action framework](https://growthmethod.com/object-action-framework/) ·
[UX Tigers — progressive disclosure](https://www.uxtigers.com/post/progressive-disclosure) ·
[MIT 6.831 lecture 14 — adaptive and split menus](https://ocw.mit.edu/courses/6-831-user-interface-design-and-implementation-spring-2011/7e721676578869e33403137f45d6926f_MIT6_831S11_lec14.pdf) ·
[Microsoft Win32 UX guide — progressive disclosure controls](https://learn.microsoft.com/en-us/windows/win32/uxguide/ctrl-progressive-disclosure-controls)

### 2.1 Sunset frameworks

| Finding | Taken? |
|---|---|
| Usage data is directional — it signals there might be an action, not what it is. | **Yes.** §7 records a cause before anything moves; §8 forbids the app rendering a recommendation to remove. |
| 30–90 day interaction window, with the reminder that not every feature is meant to be used daily or even monthly. | **Yes, generalised.** §6 makes the window per-surface and derived from a declared cadence rather than a global 90 days. |
| "Consistently low for 90 days → investigate" and "<5–10% of users → on thin ice". | **Adapted.** The percentage-of-users half is meaningless at n = 1 and is dropped rather than faked. |
| Segment before cutting — aggregates hide the people who will feel the removal. | **Adapted.** No user segments exist; the analogous split is per-account-shape (§9.3): a surface used only on renewal-stage accounts looks dead in a book where nothing is renewing. |
| Test discoverability by making the feature more prominent — if exposure lifts usage, the problem was findability. | **Yes**, as the `not_rendered` diagnosis in §6.3, which is a navigation finding rather than a value one. |
| Cost-versus-value trend, opportunity cost, inverted RICE. | **Out of scope.** No maintenance-cost data exists here and inventing an effort score would be a made-up number in a repo that forbids composite scores. |
| Define exit criteria at launch; make review recurring rather than reactive. | **Yes**, as the optional `review_on` field in the surface registry (§4). |
| Gradual sunset in phases — hide, then disable, then archive — with rollback criteria. | **Yes**, as the three escalating actions in §7.2. |

### 2.2 Event taxonomy

The object-action convention (`Object Actioned`, past tense) is endorsed across Segment, Amplitude,
Mixpanel and mParticle, and the existing sixteen events already follow it — `account_path_viewed`,
`next_move_opened`, `proposal_accepted`. New events keep it.

Three findings are load-bearing here rather than stylistic:

- **Static names only; variable data belongs in properties, never in event names.** This is both a
  taxonomy rule and, in this codebase, a trust-boundary rule: an event name built from a route
  string would put arbitrary text into the sink, and `event_name` has no slug constraint — only a
  64-character cap. So the surface identifier is a **property whose value must be in a static
  registry** (§4), never a dynamic event name.
- **Keep the schema small** — past roughly thirty core events, taxonomies get confusing and
  duplicative. Sixteen exist; this adds six, for twenty-two. That budget is stated so the next
  addition has to argue for itself.
- **Taxonomies rot from locally rational choices under deadline.** The fix the research keeps
  reaching for is turning the tracking plan from a document into a gate in CI. §11 does that: a test
  fails when a registered surface has no instrumentation and no explicit exemption, and when an
  emitted surface slug is not in the registry.

### 2.3 Progressive disclosure, and why nothing here is automatic

This is the finding that most changes the shape of the output.

Office 2000/2003 adaptive menus showed a frequently-used subset and expanded to the full list. They
are a standard teaching example of failure: positions learned through use shift as frequencies
change, new items appear on expansion with almost no contrast against the old ones so the user
re-scans the whole menu, and infrequent items became bothersome enough that users disliked the
pattern. The patent literature records the same reception.

The diagnosis in the current writing is precise, and it is not "hiding is bad": **progressive
disclosure keeps every control in a fixed, learnable location and varies only how much is expanded,
and stability is half the benefit.** Adaptive reordering breaks spatial memory; user-driven
customisation does not, because the user did the moving and knows where things landed.

So:

> **The app never adapts its own layout.** No frequency-based reordering, no automatic hiding, no
> personalised menus, ever. This spec produces *evidence* and a *proposed change*; every change to
> what renders is applied by you, once, explicitly, and stays where you put it.

That single rule is why §7's actions are operator commands with audit rows rather than a setting
called "adaptive UI", and it is a non-goal in §12 as well, because it is exactly the feature a
future session would think it was being helpful by adding.

---

## 3. What gets measured

Two counters per surface, deliberately independent, in the manner of `views`,
`views_with_next_move` and `views_with_incomplete_coverage` being three separate counters rather
than one rate (D-156…D-161):

- **Rendered** — the surface was mounted and visible. Not "the route was open": a card below the
  fold that never entered the viewport did not expose anything, so render counts fire on
  intersection, once per mount.
- **Engaged** — something on it was *operated*: a control activated, a row opened, a filter changed,
  a disclosure expanded, a value edited. Scrolling is not engagement. Hovering is not engagement.

Merging these into one "usage" number destroys the only diagnosis this feature exists to make. Their
combinations are the four observations in §6.3.

A third, thinner counter exists for commands rather than surfaces: **invoked** — a named command ran
(export, print, start plan, run comparison). Commands have no render event because they have no
persistent presence; a command that is never invoked in a covered window is simply unused, with the
discoverability caveat intact.

**Not measured, at all:** dwell time, mouse movement, scroll depth, keystroke timing, or anything
resembling attention tracking. They are noise at this scale, the research warns against
interaction-level events inflating volume and obscuring patterns, and dwell time on a screen showing
one account's material is closer to behavioural data about an operator than to a diagnostic.

---

## 4. The surface registry

A static registry in `backend/app/surfaces.py`, mirrored to the client. It is the taxonomy, and it
is code, for the same reason the `(intent, target_type)` allowlist is code: widening it should be a
review beside the thing it describes, not a data edit.

```python
Surface(
    key="plan.timeline",              # slug; the only value that may appear in an event property
    label="Launch timeline",          # human copy for the report — never sent to the sink
    route="account.plan",             # the route group it belongs to (§9.2 screen weight)
    kind="section",                   # section | panel | tab | command | field_group
    cadence="weekly",                 # session|daily|weekly|monthly|quarterly|event_driven|unscheduled
    added_on="2026-08-05",
    review_on=None,                   # optional exit-criteria date (§2.1)
    instrumented=True,                # or a stated reason, see §11
    reaches=("milestone",),           # record types this surface offers a route to — §7.7
    provides=(),                      # governed commands reachable only from here — §7.7
    explains_refusal=False,           # renders a withheld/refused reason — §7.7
    removed_on=None,                  # set when the code is deleted; the entry stays — §7.9
)
```

`reaches`, `provides` and `explains_refusal` are declarations, not observations, and they are what
makes the §7.7 safety check computable without static analysis. They are also the fields most likely
to be left at their defaults by a hurried registration, which is why §11's drift tests treat an
empty `reaches` on a surface whose route renders records as a failure rather than a valid answer.

There is no `retirement` field here. The current action is derived from `surface_retirement_notes`
(§7.3); putting a copy in the registry would make a code constant and a database row two authorities
on the same question.

`cadence` is the field that does the real work, and it is a **declaration of what the surface is
for**, not an observation. A QBR pack is `quarterly` because that is when a QBR happens; a renewal
panel is `event_driven` because it has no schedule at all and only matters when a renewal is
approaching. Getting a cadence wrong produces a wrong window, which produces a wrong observation —
so the registry entry is written when the surface is built, by whoever built it, and a test requires
every registered surface to declare one.

`event_driven` and `unscheduled` surfaces can **never** be observed as unused by elapsed time alone.
They are only observable against their own trigger — §6.4.

---

## 5. Events

Six additions to `telemetry.EVENTS`, following the existing object-action convention and the same
per-event property allowlist. Every property value remains a bounded slug, an integer, or a boolean;
`SENSITIVE_KEYS` still applies; `label` is already on that list, so a surface's human copy is
structurally unable to reach the sink.

| Event | Properties |
|---|---|
| `surface_rendered` | `surface`, `route`, `kind`, `render_reason` (`navigation`, `restore`, `filter_change`), `position` |
| `surface_engaged` | `surface`, `route`, `kind`, `engagement` (`opened`, `filtered`, `expanded`, `edited`, `dismissed`, `followed_link`) |
| `surface_dismissed` | `surface`, `route`, `dismiss_kind` (`collapsed`, `closed`, `hidden`) |
| `command_invoked` | `command`, `route`, `entry_point` (`toolbar`, `keyboard`, `menu`, `empty_state`) |
| `navigation_landed` | `route`, `entry_point`, `is_first_of_session` |
| `retirement_action_applied` | `surface`, `action` (`collapse`, `demote`, `retire`, `restore`), `cause_code` |

`surface` and `command` values must exist in the §4 registry. Validation rejects an unregistered
slug rather than storing it — an unknown surface in the data is worse than a dropped event, because
it would appear in the report as a row nobody can act on.

`position` is an integer ordinal, present so §9.2 can ask whether the things you never engage with
are the ones sitting below everything else. It is the one property here that exists to challenge the
data's own interpretation.

---

## 6. Reading it: four axes, and a window that can refuse

The same discipline as readiness: independent axes, never combined, no composite score, and a
reading withheld with a stated reason rather than downgraded to a neighbouring one.

### 6.1 The axes

1. **Exposure** — render count in the window.
2. **Engagement** — engagement count in the window, and `last_engaged_on`.
3. **Window coverage** — whether the observation window covers enough of this surface's declared
   cadence to say anything at all.
4. **Cause** — the operator's recorded explanation, if one exists (§7.1). Never inferred.

These stay separate in the response and on screen. There is **no usage score**, and a test asserts
that no column, response field, or CSS class in this feature is named `score`, `rating`, `health`, or
`usage_index`. A single number would be read as a kill order, which is precisely the reading the
usage-fallacy literature says the data cannot support.

### 6.2 Window coverage — the rule that stops the confident lie

A window covers a surface when it contains **at least two** of that surface's expected occurrences:

| Cadence | Covered when the window is at least |
|---|---|
| `session` / `daily` | 14 days |
| `weekly` | 28 days |
| `monthly` | 90 days |
| `quarterly` | 210 days |
| `event_driven` | never by elapsed time — §6.4 |
| `unscheduled` | never by elapsed time — §6.4 |

Two occurrences rather than one, because a single expected occurrence that did not happen is
indistinguishable from a week you were on holiday.

When the window does not cover the cadence, the surface reports **`insufficient_window`** and its
counts are shown greyed with the sentence *"Observed for 34 days; a monthly surface needs 90 before
this says anything."* Nothing else is claimed. This is the same move as withholding a stale `met`
rather than showing it as `Complete` (D-151…D-155): a reading with no honest basis is withheld, not
softened into the nearest available one.

### 6.3 The four observations

Mutually exclusive. `insufficient_window` wins over all of them.

| Observation | Means | The likely fix |
|---|---|---|
| `engaged` | Operated at least once in a covered window. | Nothing. |
| `rendered_not_engaged` | Shown repeatedly, never operated. | **The clutter case.** This is the visual-optimisation finding: it costs you screen every time and returns nothing. |
| `not_rendered` | Never even displayed in a covered window. | **The reachability case.** A navigation or entry-point problem, not a value one. Removing it would be removing something you have never seen. |
| `insufficient_window` | The window cannot cover this cadence. | Wait, or observe it against its trigger (§6.4). |

The distinction between the middle two is the entire practical value of separating render from
engage, and it is why `not_rendered` must never be presented as a stronger removal signal than
`rendered_not_engaged` — it is a weaker one. The research's "test by making it more prominent; if
exposure lifts usage the problem was discoverability" applies to `not_rendered` and to nothing else.

### 6.4 Event-driven surfaces

A renewal panel, a churn-risk view, an escalation surface: these have no cadence, and elapsed time
says nothing about them. They are observed against their **trigger** instead — the count of times
the condition that should summon them was true in the window, from domain data rather than
telemetry.

> Renewal panel — the condition was true 4 times; rendered 4 times; engaged 0 times.

That is a real `rendered_not_engaged` reading. Without the trigger count it would be
`insufficient_window` forever, which would make every event-driven surface permanently unobservable
and therefore permanently safe — the opposite of useful. Where a trigger count cannot be computed,
the surface says so and stays unobservable rather than being scored on elapsed days.

---

## 7. Stripping things out

This is the half of the feature that actually changes the product, and it is scoped in more detail
than the measurement half because it is the half that can break something. Measurement is additive
and reversible by deleting rows; retirement removes things from your screen, and the ways that goes
wrong are silent — a page still renders, a link still resolves, and something you needed is just no
longer reachable.

### 7.0 The honest limit, first

Hiding surfaces reduces **visual** load. It does not reduce the number of concepts you have to hold,
because the model underneath is the same size. Collapse twelve cards and the app looks calmer; it is
not simpler in the sense that matters when you come back to it after two weeks away.

The two moves that genuinely simplify are **merging two surfaces that answer the same question** and
**removing a record type nobody needs**. Neither one falls out of usage data: two surfaces both
touched weekly can be answering the same question in two places, and counts will call both of them
healthy. Telemetry finds *clutter*. It is blind to *redundancy*.

So the complement to the whole measurement layer is a cheap manual pass with no instrumentation at
all: for each record type, list every registered surface that renders it. Three or more, ask why.
That takes twenty minutes against the §4 registry, finds the thing counts never will, and it is in
Slice 4 as a recurring checklist item rather than a feature.

Stated here rather than in a footnote because the risk with this build is that the report becomes
the only place simplification is thought about, and the report cannot see the biggest wins.

### 7.1 A cause is recorded before anything moves

The report never proposes a removal. It surfaces an observation and asks you to record which of the
competing explanations you believe, from a fixed vocabulary drawn straight from the usage-fallacy
literature:

| `cause_code` | Meaning |
|---|---|
| `not_needed` | The job it does is not a job you have. |
| `not_found` | You did not know it was there, or where. |
| `misunderstood` | You knew it was there and expected it to do something else. |
| `hard_to_use` | You wanted it and it was not worth the effort. |
| `narrow_but_needed` | Rarely relevant, essential when it is. Keep. |
| `superseded` | Another surface does this better now. |
| `demo_artifact` | Only ever exercised while building or demonstrating. |

Recorded as a dated note with the observation attached, in `surface_retirement_notes`. A cause is an
operator judgement carrying a date and its evidence, exactly like a stakeholder assessment, and for
the same reason: an undated judgement about a moving system is not evidence of anything.

`narrow_but_needed` is in the list because without it the vocabulary would only be able to express
reasons to remove, and a form that can only agree with itself is not a review.

### 7.2 Three actions, escalating, all reversible

Applied explicitly, never automatically, never by frequency, each writing an audit row and setting
`surfaces[key].retirement`:

1. **Collapse** — stays exactly where it is, closed by default, one click to open. Fixed location,
   varying expansion: the progressive-disclosure pattern that preserves spatial memory. This is the
   right first action for almost every `rendered_not_engaged` surface, and it is what "optimize
   visually" mostly means in practice. Uses the existing `About this page` disclosure pattern
   (D-137) rather than a new mechanism.
2. **Demote** — moved behind a disclosure or into a secondary group. A one-time relocation you chose
   and can therefore remember. Never a reorder that repeats itself as counts change.
3. **Retire** — no longer rendered. Requires a `decisions.md` entry naming the surface, the
   observation window, the recorded cause, and the restore path. Code is not deleted at this step;
   the surface stops mounting, and a `restore` action puts it back. Deleting the code is an ordinary
   change made later, once retirement has held.

**Rollback is a first-class command,** per the sunset literature's insistence on defined rollback
criteria: `restore` returns a surface to its previous state and emits
`retirement_action_applied` with `action=restore`, so a mistaken retirement is visible in the record
rather than quietly undone.

### 7.3 One wrapper does both jobs

The mechanism is a single component, `<Surface surfaceKey="plan.timeline">`, added once per surface.
It does three things: emits `surface_rendered` on intersection, hands down the callback that emits
`surface_engaged`, and reads the current retirement action to decide how to render.

Instrumentation and retirement being the *same* wrapper is the load-bearing choice. The obvious
build instruments everything in Slice 1, then comes back months later and threads a second
"can this be hidden" concern through the same forty files. One wrapper means the second pass never
happens, and it means a surface cannot be retirable without being measurable — which is exactly the
coupling you want, since retiring something you never measured is guessing with extra steps.

Current action is **derived**, not stored as its own state: the latest `surface_retirement_notes`
row per `surface_key` by `recorded_on`. One small query, cached per request. There is no
`surfaces.current_state` column, for the reason the rest of this codebase has none — a second copy
of the answer is a second thing that can disagree with the record it came from.

### 7.4 Each kind retires differently

`kind` is not decoration; it determines which actions are even available, and getting this wrong is
how a simplification pass breaks navigation.

| Kind | Collapse | Demote | Retire means | The trap it avoids |
|---|---|---|---|---|
| `section` | ✅ closed by default, in place | ✅ moved behind a disclosure, once | Stops mounting on its route | — |
| `panel` (slide-over, modal) | ❌ meaningless — it has no resting presence | ❌ | Its trigger stops rendering | Collapsing a modal is a no-op that looks like it worked |
| `tab` | ❌ | ✅ moved to the end of the tab strip | Drops from the tab strip, **but the route keeps resolving** | §7.5 |
| `command` | ❌ | ✅ toolbar → overflow menu | Drops from menus and toolbars, **keyboard shortcut retained** | Muscle memory outlives menus; a shortcut that silently stops working reads as a bug |
| `field_group` | ✅ | ✅ | **Never.** See §7.6 | Hiding a field group hides data that exists |

### 7.5 A retired tab keeps its URL

Retiring a tab removes it from the tab strip. It does **not** remove the route. `/accounts/{id}/value`
still resolves and renders the tab's content beneath a line reading *"You retired this view on 12
September. [Restore]"*.

Every link in this app is a path, bookmarks are paths, and the copilot, the receipt, the queue and
the plan all deep-link across tabs. A retirement that deleted routes would turn a tidy-up into a
scatter of dead links discovered one at a time over the following month, each looking like a
different bug. The rule is general: **retirement changes what is offered, never what resolves.**

### 7.6 A field group is never retired while it holds data

If any record has a non-null value in a field group, that group may be collapsed but not retired.
Collapsing hides it behind one click; retiring makes stored data unreachable through the UI while it
sits in the database being exported, counted and reasoned over by everything else.

This is checkable rather than a matter of care: the retire action runs a non-null count over the
group's columns and refuses with the count in the message — *"Retiring this would hide 34 records
that have a value here. Collapse instead."* A refusal that names the number is one you can act on;
"cannot retire" is one you argue with.

### 7.7 The safety check, made computable

A surface may not be retired while it is the **only** offered route to a record type, a governed
command, or a refusal explanation. Hiding the last path to the evidence panel breaks no page and
raises no error — it just makes something unreachable, and nothing in the usage data would ever say
so, because the thing that stopped happening stopped emitting events too.

Making that checkable needs the registry to **declare** what each surface reaches, because inferring
it from the code is a static-analysis project this repo does not need:

```python
reaches = ("commitment", "risk")   # record types this surface offers a route to
provides = ("evidence_review",)    # governed commands reachable only from here
explains_refusal = True            # renders a withheld/refused reason (D-153 family)
```

The check is then a set difference over the currently-offered surfaces, run at apply time and
asserted in a test over the registry as a whole: no combination of retirements may empty any
`reaches` or `provides` set, and a surface with `explains_refusal` may only be retired if another
offered surface carries the same refusal. Failing closed here is right — a wrongly-blocked
retirement costs you a `collapse` instead; a wrongly-allowed one costs you a refusal nobody can read.

### 7.8 Changes apply as a reviewed batch

Stripping one card a week never feels like the product got simpler. One sitting where nine things
collapse and three retire does, and it is also the only way the §7.7 check can be meaningful — it
has to evaluate the *set*, since two retirements that are each individually safe can between them
empty a `reaches` set.

So the **Simplify** flow is: the report proposes, you record causes, you stage actions, and then one
screen shows the whole batch with a per-route preview of what each affected screen will look like
afterwards. Apply writes one `batch_id` across every note in the set.

- **Undo the batch** — one action, available for 14 days, reverting every action in it.
- **Restore one surface** — available forever, independent of the batch.

The preview renders the same way the app will, from the same wrapper, for the reason the shared-plan
promotion preview runs the same projection as the export (D-151…D-155): a preview built by a
different path is a preview that can disagree with the thing it previews.

### 7.9 Deleting code is a later, separate change

Retirement stops a surface being offered. It does not delete anything, and Slice 3 ships no deletion.

Code removal is an ordinary change made afterwards, on its own, once a retirement has held through
**two full observation windows for that surface's cadence** — so a monthly surface waits six months,
which is the point rather than an inconvenience. It carries its own `decisions.md` entry naming the
surface, the retirement date, and the records it rendered.

One category can never be deleted even when retirement has held indefinitely: **any surface that is
the only renderer of a record type with rows in the database.** Hiding the Value ledger is a
preference; deleting its view while `value_stories` has rows makes real records unreachable through
the product while they continue to exist, get exported, and get counted. Removing the record type is
a different and much larger decision, and it is not one this feature is allowed to make by
increments.

The registry keeps the entry after code removal, marked `removed_on`, so the surface's history — its
counts, its recorded cause, its retirement — survives the code. Otherwise the answer to "why doesn't
this app have X" is lost at exactly the moment somebody proposes rebuilding it.

---

## 8. The report

An Operations sub-view, **Surface usage**, beside the existing measurement panel.

- Default order is **navigation order**, not least-used-first. A leaderboard sorted by disuse reads
  as a kill list, and the top row would be whichever surface has the least honest window. Sorting by
  disuse is available as an explicit control; it is not the default view.
- Columns: surface, route, cadence, window covered, rendered, engaged, last engaged, observation,
  recorded cause. Every status pairs a word with a shape or label — never colour alone.
- `insufficient_window` rows render with the cross-hatched unknown treatment the design guide
  already uses for stale data, because that is exactly what they are: not-yet-knowable, not zero.
- The §17.5-style caveat renders **beside the numbers**, server-authored, not in a tooltip:

  > These counts describe exposure and engagement on your own screen. They cannot say whether a
  > surface is valuable — a low count can mean it was never found, was misunderstood, or is rarely
  > relevant and essential when it is. Record a cause before changing anything.

- A **screen-weight** view groups by route: sections rendered, sections engaged, and the
  never-engaged list for that screen. This is the direct answer to "optimize visually" — a screen
  rendering eleven sections of which two are ever touched is a layout finding, and it is legible in
  one row per screen in a way that a per-surface table is not.

---

## 9. Scope, honesty, and the things that will mislead you

### 9.1 Demo traffic

Building and demonstrating this product generates events indistinguishable from using it. There is
no clean fix at n = 1, so the spec takes two partial ones: the `demo_artifact` cause code exists so
you can mark a surface whose entire history is you showing it to someone, and the report states its
window's start date prominently so you can discount a period you know was a build week. It does not
attempt to detect demo sessions — a heuristic that silently discarded half the data would be worse
than data you know to read carefully.

### 9.2 Position confounds engagement

`position` is recorded so the report can say when the never-engaged surfaces are also the ones that
sit last on their screen. That is a layout finding, not a value finding, and conflating them would
retire good surfaces for the crime of being at the bottom.

### 9.3 Portfolio shape confounds cadence

A renewal surface looks dead in a book with no renewals approaching. §6.4's trigger counts are the
answer where they can be computed; where they cannot, the surface stays unobservable and says so.

### 9.4 The rollup, and why raw retention does not move

Answering "is this quarterly surface used" needs a longer history than the current 90-day raw
retention. Raising raw retention would keep session-linked rows for a year, which is more
behavioural detail than the question requires.

Instead, a monthly rollup: per surface, per calendar month, `rendered`, `engaged`,
`last_engaged_on`. **No session id, no account id, no properties.** Rollups retain for 36 months;
raw events keep their existing 90-day purge. The rollup carries strictly less than the rows it
summarises, which is what justifies its longer life.

The off switch loses none of its force: disabling measurement deletes the rollups too, in the same
transaction as `DELETE FROM product_events`. A rollup that survived the off switch would be exactly
the loophole that makes "measurement is disabled" and "there is measurement data" both true at once.

---

## 10. Data model

Migration `0052` (or `0053` if the drop-intake spec lands first).

```sql
CREATE TABLE surface_usage_months (
  id             TEXT PRIMARY KEY,
  surface_key    TEXT NOT NULL,          -- must exist in the §4 registry
  month          TEXT NOT NULL,          -- 'YYYY-MM'
  rendered       INTEGER NOT NULL DEFAULT 0,
  engaged        INTEGER NOT NULL DEFAULT 0,
  last_engaged_on TEXT,
  updated_at     TEXT NOT NULL,
  UNIQUE (surface_key, month)
);

CREATE TABLE surface_retirement_notes (
  id            TEXT PRIMARY KEY,
  surface_key   TEXT NOT NULL,
  cause_code    TEXT NOT NULL,           -- §7.1 vocabulary, validated in Python
  observed_from TEXT NOT NULL,           -- the window this judgement was made against
  observed_to   TEXT NOT NULL,
  rendered      INTEGER NOT NULL,        -- the counts as they stood, frozen
  engaged       INTEGER NOT NULL,
  action        TEXT,                    -- collapse | demote | retire | restore | none
  batch_id      TEXT,                    -- §7.8; one id across a reviewed set
  note          TEXT,                    -- operator prose, internal-only, never to the sink
  recorded_on   TEXT NOT NULL,
  recorded_by   TEXT NOT NULL
);
```

The table is **append-only**: undoing a batch and restoring a surface both write new rows rather
than updating or deleting old ones, and the current action is the latest row per surface (§7.3).
That is what makes "I hid this in September and put it back in November" legible six months later,
which is the question that actually gets asked.

Two more things about this schema are deliberate and should not be tidied away later:

- **`surface_retirement_notes` freezes the counts.** A judgement made against 200 renders and 0
  engagements is not the same judgement six months later when the numbers have moved. Recomputing
  them on read would let the record silently change its own basis.
- **No `state` column on either table, and no score anywhere.** A schema-introspection test asserts
  it, in the manner of migrations 0042, 0046 and 0050. `action` is permitted because it records an
  operator command that was applied, not a status of the surface.

The registry itself is code, not a table. A registry row is a claim about what a surface *is for*,
and it belongs beside the surface in version control where a code review sees it change.

---

## 11. Instrumentation drift is a test failure

The research's recurring warning is that tracking plans rot into wikis nobody honours. Three tests
turn the plan into a gate:

1. **Every registered surface is instrumented**, or carries `instrumented="<reason>"` naming why not.
   An unexplained gap fails.
2. **Every emitted `surface` / `command` slug is in the registry.** Validation rejects at write time
   and a test asserts the rejection.
3. **Every registered surface declares a cadence** from the fixed vocabulary.
4. **No possible set of retirements empties a `reaches` or `provides` set**, and every
   `explains_refusal` surface has at least one offered peer carrying the same refusal (§7.7). Run
   over the registry as a whole, not just the currently-applied set, so the check fails when a
   registration makes something *retirable into unreachability* — not later, when someone retires it.
5. **A surface whose route renders records declares a non-empty `reaches`.** An empty tuple is a
   valid answer only for surfaces that render no record type, and the test requires that to be true
   rather than assumed.

Retirement-behaviour tests, all pure and fixture-driven:

- A retired `tab` still resolves its route and renders the restore banner (§7.5).
- A retired `command` keeps its keyboard shortcut.
- `collapse` and `demote` are unavailable on a `panel`; `retire` is unavailable on a `field_group`
  with any non-null value, and the refusal message carries the count (§7.6).
- Applying a batch writes one `batch_id`; undo writes new rows rather than deleting; the derived
  current action returns to what it was.
- The batch preview and the applied result render identically from the same wrapper (§7.8).

A further test asserts that no domain module imports `surfaces.py` for anything but its own
registration — the §17.1 rule that measurement can never be read by account status, pillar state,
ranking, or any customer-facing surface applies here unchanged. Nothing about which screens you use
may ever influence what the app says about an account.

---

## 12. Non-goals

- **No adaptive UI.** No frequency-based reordering, no automatic hiding, no personalised menus.
  §2.3 is the reason and it is the most important line in this document.
- No usage score, health score, or composite index.
- No dwell time, scroll depth, mouse movement, or attention proxy.
- No export, no network path, no vendor. `product_telemetry_sink` stays `local`; adding a sink is the
  approval conversation.
- No person identifier, ever — and at n = 1 the session token remains rotating rather than becoming
  a de facto operator id.
- No automatic removal of anything, at any threshold.
- **No code deletion by this feature, in any slice.** Retirement changes what is offered; deleting
  code is a later ordinary change under §7.9.
- No route removal. A retired tab keeps resolving (§7.5) — this feature never creates a dead link.
- No removal of a record type. That is a separate decision and is explicitly out of reach of an
  accumulation of retirements.
- No second telemetry table, no second settings switch, no second off button.

---

## 13. Build order

| Slice | Contents |
|---|---|
| **1** | Surface registry, the three drift tests, `surface_rendered` / `surface_engaged` on the ~20 highest-traffic surfaces. No report yet — instrument first, so the first report has something honest to show. |
| **2** | Monthly rollup, window-coverage logic, the four observations, the Operations report with its caveat and cross-hatched unknowns. |
| **3** | Cause codes, retirement notes, the three actions plus restore, per-kind rules (§7.4–7.6), the §7.7 safety check, the batch Simplify flow with preview and 14-day undo. **No code deletion.** |
| **4** | Screen-weight view, event-driven trigger counts, remaining surfaces instrumented, the §7.0 redundancy checklist, both-theme screenshots, `decisions.md`, `HANDOFF.md`. |

Slice 2 will report almost nothing useful for the first month, and that is correct rather than a
defect. The honest first output of this feature is *"observed for 11 days; nothing here is knowable
yet"* — and a feature whose first screen says that is a feature you can trust the month it starts
saying something else.

---

## 14. Calls needed before Slice 1

1. **Scope of instrumentation** — the ~20 highest-traffic surfaces first (recommended), or every
   surface in the app in one pass?
2. **The rollup's 36-month retention** — acceptable, or shorter?
3. **`retire` semantics** — stop rendering but keep the code (recommended, reversible), or treat a
   retirement as a licence to delete the code in the same slice?
4. **Batch undo window** — 14 days (recommended: long enough to cover a fortnight away, short enough
   that "undo everything" stops being the reflex), or longer? Single-surface restore is permanent
   either way.
5. **The two-window hold before code deletion** (§7.9) — six months for a monthly surface is the
   consequence, and it is deliberate. Accept, or set a flat hold period regardless of cadence?
