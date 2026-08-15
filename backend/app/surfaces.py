"""The surface registry (`SURFACE-USAGE-SPEC.md` §4) — what this platform puts on screen.

This is the taxonomy for Stage 17, and it is **code rather than a table**, for the reason the
`(intent, target_type)` allowlist is code: a registry row is a claim about what a surface is *for*,
and widening it should be a review beside the thing it describes, not a data edit nobody sees.

Read §1 before adding to this file. The measurement it feeds is built for **n = 1**, so the signal
is engagement *given exposure* — of the times a surface was on screen, how often was it operated —
and never a share of users. Two counters stay separate all the way through (`rendered`, `engaged`)
because collapsing them into one "usage" number destroys the only diagnosis the feature exists to
make: a surface shown two hundred times and never touched is clutter, and one never shown at all is
a navigation problem. Those need opposite responses.

Four fields carry more weight than they look like they do.

- **`cadence` is a declaration of what the surface is for, not an observation.** A QBR pack is
  `quarterly` because that is when a QBR happens. Getting it wrong produces a wrong window, which
  produces a wrong observation, so it is written when the surface is built by whoever built it and
  `_validate` requires one. `event_driven` and `unscheduled` can never be observed as unused by
  elapsed time at all (§6.4) — only against their own trigger.
- **`reaches`, `provides` and `explains_refusal` are declarations, not observations.** They are what
  makes §7.7's safety check computable without a static-analysis project: a surface may not be
  retired while it is the only offered route to a record type, a governed command, or a refusal
  explanation. Hiding the last path to something breaks no page and raises no error — it just makes
  something unreachable, and the usage data would never say so, because the thing that stopped
  happening stopped emitting events too.
- **`instrumented`** is either `True` or a sentence saying why not. An unexplained gap fails a test
  (§11.1), because a tracking plan that rots into a wiki nobody honours is the failure mode the
  research keeps naming.

There is deliberately **no `retirement` or `current_state` field**. The current action is derived
from `surface_retirement_notes` (§7.3); a copy here would make a code constant and a database row
two authorities on the same question.

`SURFACE-USAGE-SPEC.md` §17.1's rule is inherited unchanged and is the one that matters most: nothing
about which screens the operator uses may be read by account status, pillar state, ranking, or any
customer-facing surface. `tests/test_surface_registry.py` asserts no domain module imports this
one for anything but its own registration.
"""
from __future__ import annotations

from dataclasses import dataclass, field

# §4. A cadence says how often the surface is *meant* to matter. The two at the end are not
# slower cadences — they are the absence of one, and §6.4 handles them by trigger instead.
CADENCES = ("session", "daily", "weekly", "monthly", "quarterly", "event_driven", "unscheduled")

# §7.4. `kind` is not decoration: it decides which retirement actions are even available, which is
# how a simplification pass avoids breaking navigation. Collapsing a modal is a no-op that looks
# like it worked; retiring a field group hides data that exists.
KINDS = ("section", "panel", "tab", "command", "field_group")

# §6.2. A window covers a surface when it contains at least *two* expected occurrences. Two rather
# than one, because a single expected occurrence that did not happen is indistinguishable from a
# week the operator was away.
WINDOW_DAYS = {"session": 14, "daily": 14, "weekly": 28, "monthly": 90, "quarterly": 210}


@dataclass(frozen=True)
class Surface:
    """One registered surface. Frozen: the registry is a constant, not a place to accumulate state."""

    key: str
    label: str
    route: str
    kind: str
    cadence: str
    added_on: str
    # Record types this surface offers a route to. Empty is a valid answer only when
    # `renders_no_records` says why — see `_validate`.
    reaches: tuple[str, ...] = ()
    # Governed commands reachable only from here.
    provides: tuple[str, ...] = ()
    # Renders a withheld or refused reason (the D-153 family). A surface carrying one may only be
    # retired if another offered surface carries the same refusal.
    explains_refusal: bool = False
    # `True` (a named semantic action emits engagement), `GENERIC` (engagement is observed by the
    # wrapper's operated-signal — real, but coarse), or a sentence naming why neither holds
    # (§11.1, amended 2026-08-15 / D-366). `GENERIC` is a distinct value rather than `True`
    # because the two claims differ: semantic engagement says *which* operation happened, the
    # generic signal only says a control inside the surface was operated. A reader weighing a
    # retirement gets told which kind of evidence backs the zero.
    instrumented: bool | str = True
    # Required exactly when `reaches` is empty. See `_validate` for why this exists at all.
    renders_no_records: str | None = None
    review_on: str | None = None
    # Set when the code is deleted; the entry stays, so the answer to "why doesn't this app have X"
    # survives the code that used to be X (§7.9).
    removed_on: str | None = None
    # §6.4. Names an allowlisted evaluator in `surface_triggers.py` that counts how often the
    # condition which should have summoned this surface was true. Permitted *only* on a cadence with
    # no window, because a scheduled surface is already covered by elapsed time and a trigger there
    # would be a second answer to one question. `None` on an event-driven surface is the honest
    # "cannot be computed" case §6.4 names, and leaves it unobservable rather than read as unused.
    trigger: str | None = field(default=None)
    # `table.column` pairs a `field_group` displays, and required of one. §7.6 refuses to retire a
    # field group that holds data and names the count, which is only computable if the group says
    # which columns it shows. Inferring them from JSX is a static-analysis project this repo does not
    # need, and a declaration is a claim a code review sees change (D-302).
    data_columns: tuple[str, ...] = ()


# The middle instrumentation state (D-366): the wrapper's generic operated-signal covers this
# surface, so `engaged` is readable — a zero genuinely means no control inside it was operated —
# but the events say only `operated`, never which operation. Wiring a named semantic action
# upgrades a surface to `instrumented=True` and silences the generic signal at that call site.
GENERIC = "generic"


def _s(key, label, route, kind, cadence, **kw) -> Surface:
    # Every non-command surface sits inside the `<Surface>` wrapper, and since D-366 the wrapper
    # itself emits `operated` engagement for any interactive control operated inside it. So the
    # default is GENERIC, not an uninstrumented sentence: the zero is readable, and what remains
    # per-surface work is naming the operation (upgrading to `instrumented=True`), not making the
    # counter mean anything at all. Commands are different: their only event is the
    # explicitly-wired invocation itself.
    if kind != "command" and "instrumented" not in kw:
        kw["instrumented"] = GENERIC
    added_on = kw.pop("added_on", "2026-08-06")
    return Surface(key=key, label=label, route=route, kind=kind, cadence=cadence,
                   added_on=added_on, **kw)


# --- the registry -----------------------------------------------------------------------------
#
# Slice 1 registered the surfaces carrying the most traffic; Slice 4 added the rest (§13). That was
# the honest order: a registry entry with no instrumentation behind it is a row whose zero means
# "nobody wired this up", and a report full of those is worse than no report.
#
# `instrumented=True` means both halves are present: the wrapper observes exposure and a deliberate
# operation emits engagement. A wrapper alone keeps the default sentence above. That distinction is
# intentionally conservative: an incomplete surface reads as unknowable, never as unused.

REGISTRY: tuple[Surface, ...] = (
    # --- today ---------------------------------------------------------------------------------
    _s("today.queue", "Attention queue", "today", "section", "session",
       reaches=("commitment", "risk", "issue", "task", "internal_ask"),
       explains_refusal=True, instrumented=True),
    # VISIBILITY-SPEC §4. Weekly rather than session: it answers "where am I not looking", which is
    # a question you ask when you step back, not one you ask every time you open the app.
    _s("today.absence", "Where you are not looking", "today", "section", "weekly",
       reaches=("account", "program")),
    _s("today.saved_views", "Saved views", "today", "section", "weekly",
       renders_no_records="A filter control over the queue. It renders no record of its own; the "
                          "rows it narrows belong to today.queue.", instrumented=True),

    # --- accounts ------------------------------------------------------------------------------
    _s("accounts.book", "Account book", "accounts", "section", "session",
       reaches=("account",), instrumented=True),
    _s("accounts.portfolio_analytics", "Portfolio analytics", "accounts", "panel", "monthly",
       reaches=("account", "program")),

    # --- account overview (the command centre) --------------------------------------------------
    #
    # `overview.*` is the largest group because the overview is three lenses on one route, and a
    # lens is not a route: switching from Operate to Leadership does not change the URL, so a
    # per-route count would say the overview was busy without saying which of the three anyone
    # actually reads. That is precisely the question §6 exists to answer, so each lens's sections
    # are registered individually.
    _s("overview.account_path", "Next best move", "account.overview", "section", "session",
       reaches=("commitment", "risk", "issue", "task", "phase_gate_item"),
       explains_refusal=True),
    # Unscheduled, not session: the drop zone matters exactly when the operator has a document in
    # hand, and elapsed days say nothing about how often that is true (§6.4).
    _s("overview.intake_drop", "Drop a document", "account.overview", "section", "unscheduled",
       reaches=("extraction_run",), explains_refusal=True),
    _s("overview.readiness_summary", "Relationship readiness", "account.overview", "section",
       "weekly", reaches=("readiness_requirement", "readiness_exception"),
       explains_refusal=True, instrumented=True),
    _s("overview.next_on_account", "Next on account", "account.overview", "section", "weekly",
       reaches=("interaction", "milestone"), instrumented=True),
    _s("overview.current_point_of_view", "Current point of view", "account.overview", "section",
       "weekly", reaches=("status_assessment",), instrumented=True),
    _s("overview.since_last_visit", "Since last visit", "account.overview", "section", "session",
       reaches=("interaction", "commitment", "risk", "issue"), instrumented=True),
    # The Leadership lens. Quarterly rather than weekly: it is the surface you open before a review
    # conversation, and a fortnight of silence on it is not a finding.
    _s("overview.where_account_stands", "Where the account stands", "account.overview", "section",
       "quarterly", reaches=("status_assessment", "forecast_entry"), instrumented=True),
    _s("overview.what_moved", "What moved", "account.overview", "section", "quarterly",
       reaches=("interaction", "decision", "commitment", "milestone")),
    _s("overview.what_is_stuck", "What is stuck", "account.overview", "section", "quarterly",
       reaches=("risk", "issue", "milestone")),

    # --- account ledger -------------------------------------------------------------------------
    _s("ledger.records", "Records ledger", "account.ledger", "section", "session",
       reaches=("interaction", "commitment", "task", "decision", "risk", "issue",
                "capture_inbox_item")),
    _s("ledger.activity", "Activity timeline", "account.ledger", "section", "weekly",
       reaches=("interaction", "commitment_change", "decision_change", "risk_change",
                "issue_change", "task_change", "milestone_change"),
       explains_refusal=True),
    _s("ledger.communications", "Communications", "account.ledger", "section", "weekly",
       reaches=("comms_entry", "comm_message", "interaction")),
    # Unscheduled with a real trigger: a transcript arrives when it arrives, but "a document
    # produced proposals" is a fact in our own data, so this one is observable where the drop zone
    # above it is not.
    _s("ledger.extraction", "Extract from a transcript", "account.ledger", "section", "unscheduled",
       trigger="extraction_run_landed",
       reaches=("extraction_run", "extraction_proposal"), explains_refusal=True),

    # --- account people ---------------------------------------------------------------------------
    _s("people.stakeholder_map", "Stakeholder map", "account.people", "section", "weekly",
       reaches=("person", "stakeholder_role")),
    _s("people.champions", "Champions", "account.people", "section", "monthly",
       reaches=("person", "advocacy_event", "advocacy_tag")),
    _s("people.person_card", "Person card", "account.people", "panel", "weekly",
       reaches=("person", "advocacy_event", "advocacy_tag", "interaction"), instrumented=True),
    _s("people.influence", "Influence and relationships", "account.people", "section", "monthly",
       reaches=("person", "stakeholder_role", "relationship_edge")),
    _s("people.exec_alignment", "Executive alignment", "account.people", "section", "monthly",
       reaches=("exec_pairing", "person", "succession_record")),
    # The org-change surface is the clearest case for §6.4: a book with no departures makes it look
    # dead, and elapsed days would call that disuse. Its trigger is a count of flags raised.
    _s("people.org_changes", "Org changes", "account.people", "section", "event_driven",
       trigger="org_change_flagged", reaches=("org_change_flag", "person"),
       explains_refusal=True, instrumented=True),
    _s("people.messaging", "Messaging", "account.people", "section", "monthly",
       reaches=("messaging_entry",)),

    # --- account plan ----------------------------------------------------------------------------
    _s("plan.timeline", "Launch timeline", "account.plan", "section", "weekly",
       reaches=("milestone", "readiness_plan_instance", "readiness_plan_entry"), instrumented=True),
    _s("plan.requirement_detail", "Requirement detail", "account.plan", "panel", "weekly",
       reaches=("readiness_requirement", "readiness_evidence_link", "readiness_exception"),
       explains_refusal=True, instrumented=True),
    _s("plan.checklists", "Checklists", "account.plan", "section", "weekly",
       reaches=("checklist_item", "compliance_item")),
    _s("plan.calendar", "Calendar", "account.plan", "section", "weekly",
       reaches=("calendar_event", "deployment_moment")),
    _s("plan.adoption_comms", "Communication sequences", "account.plan", "section", "monthly",
       reaches=("comms_sequence", "comms_entry"), explains_refusal=True),
    _s("plan.campaigns", "Adoption campaigns", "account.plan", "section", "monthly",
       reaches=("adoption_campaign", "adoption_campaign_target"), explains_refusal=True),
    _s("plan.program_detail", "Program detail", "account.plan", "panel", "weekly",
       reaches=("program", "phase_gate_item", "milestone")),

    # --- account commercial ------------------------------------------------------------------------
    _s("commercial.whitespace", "Whitespace", "account.commercial", "section", "monthly",
       reaches=("whitespace_cell", "expansion_opportunity")),
    _s("commercial.value_ledger", "Value ledger", "account.commercial", "section", "monthly",
       reaches=("value_target", "value_story")),
    _s("commercial.funding", "Funding", "account.commercial", "section", "quarterly",
       reaches=("funding_pool", "recovered_spend")),
    _s("commercial.signals", "Expansion signals", "account.commercial", "section", "event_driven",
       trigger="expansion_signal", reaches=("pull_signal",)),
    _s("commercial.company_intel", "Company intel", "account.commercial", "section", "event_driven",
       trigger="company_event_confirmed",
       reaches=("company_event", "company_convergence", "intel_document"),
       explains_refusal=True),
    # §6.4's own worked example, and §9.3's confound: a growth surface looks dead in a book with no
    # renewals approaching. The trigger is what stops that reading.
    _s("commercial.growth", "Growth and renewal", "account.commercial", "section", "event_driven",
       trigger="renewal_approaching",
       reaches=("account_growth_plan", "growth_plan_line", "contract_version")),
    _s("commercial.pipeline", "Expansion pipeline", "account.commercial", "section", "monthly",
       reaches=("expansion_opportunity", "contract_version")),

    # --- account evidence ---------------------------------------------------------------------------
    _s("evidence.value_library", "Value library", "account.evidence", "section", "monthly",
       reaches=("value_story", "value_target")),
    _s("evidence.metrics", "Metrics and benchmarks", "account.evidence", "section", "monthly",
       reaches=("metric_observation", "metric_definition", "benchmark"),
       explains_refusal=True),

    # --- account outputs ----------------------------------------------------------------------------
    _s("outputs.artifacts", "Artifacts", "account.outputs", "section", "monthly",
       reaches=("generated_document", "source_reference")),
    _s("outputs.qbr", "QBR pack", "account.outputs", "section", "quarterly",
       reaches=("generated_document",), explains_refusal=True),
    _s("outputs.team_update", "Team update", "account.outputs", "section", "weekly",
       reaches=("generated_document",)),
    _s("outputs.mutual_action_plan", "Mutual action plan", "account.outputs", "section", "monthly",
       reaches=("milestone", "commitment"), explains_refusal=True),

    # --- account internal ---------------------------------------------------------------------------
    _s("internal.forecast", "Forecast", "account.internal", "section", "monthly",
       reaches=("forecast_entry", "forecast_submission"), explains_refusal=True),
    _s("internal.asks", "Asks and escalations", "account.internal", "section", "weekly",
       reaches=("internal_ask", "escalation_instance"), explains_refusal=True),
    _s("internal.reviews", "Leadership reviews", "account.internal", "section", "quarterly",
       reaches=("account_review", "status_assessment")),
    _s("internal.coverage", "Coverage", "account.internal", "section", "monthly",
       reaches=("internal_roster", "person")),

    # --- library --------------------------------------------------------------------------------
    _s("library.sources", "Files and context", "library", "section", "monthly",
       reaches=("source_reference",)),
    _s("library.playbooks", "Playbook library", "library", "section", "quarterly",
       reaches=("readiness_playbook_definition", "readiness_playbook_entry")),

    # --- coach ----------------------------------------------------------------------------------
    # Stage 18 inherits the measurement boundary rather than adding content-shaped events. The
    # completed-review and practice surfaces are event-driven because they matter when analysis
    # creates something to inspect, not because a week elapsed.
    _s("coach.home", "Coaching focus", "coach", "section", "daily",
       reaches=("coaching_goal", "coaching_session"), instrumented=True,
       added_on="2026-08-11"),
    _s("coach.intake", "Review a call", "coach", "section", "unscheduled",
       reaches=("coaching_session", "coaching_source"), explains_refusal=True,
       instrumented=True, added_on="2026-08-11"),
    _s("coach.review", "Coaching review", "coach", "section", "event_driven",
       trigger="coaching_run_completed", reaches=("coaching_run", "coaching_observation"),
       explains_refusal=True, instrumented=True, added_on="2026-08-11"),
    _s("coach.practice", "Targeted practice", "coach", "section", "event_driven",
       trigger="coaching_priority_available", reaches=("coaching_session", "coaching_observation"),
       explains_refusal=True, instrumented=True, added_on="2026-08-11"),
    _s("coach.history", "Coaching history", "coach", "section", "weekly",
       reaches=("coaching_session", "coaching_goal"), instrumented=True,
       added_on="2026-08-11"),

    # --- global ------------------------------------------------------------------------------------
    # The copilot is reachable from every route, so its route is `global` rather than the tab it
    # happened to be opened over. Event-driven: you ask it when you have a question, and a
    # fortnight without one is not evidence of anything.
    _s("global.copilot", "Account copilot", "global", "panel", "event_driven",
       reaches=("copilot_run",), explains_refusal=True),

    # --- operations -----------------------------------------------------------------------------
    _s("operations.measurement", "Product measurement", "operations", "section", "monthly",
       # Deliberately no table name anywhere in this module. Stage 7's §17.1 test is a substring
       # check over the whole source tree, and it is right to be that blunt — telling a mention
       # apart from a read needs a Python parser, and the safe direction is to fail on both.
       renders_no_records="Reports counts over the measurement sink, which is a diagnostic and "
                          "not a record type. §17.1 forbids it being read as one."),
    # The report registers itself. Not a joke: it is a surface with a cadence like any other, and a
    # registry that quietly exempted the thing doing the measuring would be the one place where an
    # unused screen could never be found. Its own row is read the same way as every other.
    _s("operations.surface_usage", "Surface usage", "operations", "section", "monthly",
       renders_no_records="Reports counts per registered surface. A registry row is a declaration "
                          "in code, not a record type this or any surface can reach."),
    _s("operations.copilot_governance", "Copilot governance", "operations", "section", "monthly",
       reaches=("copilot_configuration", "copilot_feedback")),

    # --- commands --------------------------------------------------------------------------------
    # A command has no render event because it has no resting presence (§3); a command never invoked
    # in a covered window is simply unused, with the discoverability caveat intact.
    _s("command.log_interaction", "Log interaction", "global", "command", "session",
       renders_no_records="A capture command. It creates an interaction rather than rendering one."),
    _s("command.export_team_update", "Export team update", "account.outputs", "command", "weekly",
       renders_no_records="Produces a generated document; the records it reads are rendered by the "
                          "surfaces it is invoked from."),
    _s("command.start_plan", "Start a plan from a playbook", "account.plan", "command", "quarterly",
       renders_no_records="Instantiates a plan. The instances it creates are rendered by "
                          "plan.timeline."),
    _s("command.review_call", "Start private call review", "coach", "command", "unscheduled",
       renders_no_records="Starts a private coaching session. The resulting session is rendered "
                          "by the Coach workspace.", added_on="2026-08-11"),
)


# --- validation, run at import ------------------------------------------------------------------
#
# At import rather than only in a test, because a malformed registry should fail the process that
# depends on it rather than wait for a suite somebody may not have run. The tests in §11 assert the
# same rules independently — they are the gate; this is the guard.

def _validate(registry: tuple[Surface, ...]) -> None:
    seen: set[str] = set()
    for s in registry:
        if s.key in seen:
            raise ValueError(f"duplicate surface key '{s.key}'")
        seen.add(s.key)
        if s.kind not in KINDS:
            raise ValueError(f"surface '{s.key}' has unknown kind '{s.kind}'")
        if s.cadence not in CADENCES:
            raise ValueError(f"surface '{s.key}' has unknown cadence '{s.cadence}'")
        if s.instrumented is not True and not isinstance(s.instrumented, str):
            raise ValueError(f"surface '{s.key}' must be instrumented or say why not")
        if isinstance(s.instrumented, str) and not s.instrumented.strip():
            raise ValueError(f"surface '{s.key}' gives an empty reason for not being instrumented")
        # §11.5. An empty `reaches` is a valid answer only for a surface that renders no record
        # type, and the test requires that to be *true* rather than assumed. Demanding a sentence
        # is the cheapest way to make the difference between "renders nothing" and "nobody filled
        # this in" survive a hurried registration — which §4 names as the likeliest failure.
        if not s.reaches and not (s.renders_no_records or "").strip():
            raise ValueError(
                f"surface '{s.key}' declares no record types and gives no reason; an empty "
                f"`reaches` must say why it is empty (§11.5)")
        if s.reaches and s.renders_no_records:
            raise ValueError(
                f"surface '{s.key}' both declares record types and claims to render none")
        # §7.6. A field group that cannot say which columns it shows cannot have its "does this hold
        # data" question answered, and an unanswerable safety question is not a reason to proceed.
        if s.kind == "field_group" and not s.data_columns:
            raise ValueError(
                f"field group '{s.key}' declares no `data_columns`; §7.6 cannot count what it "
                f"would hide")
        if s.kind != "field_group" and s.data_columns:
            raise ValueError(
                f"surface '{s.key}' is a {s.kind} and may not declare `data_columns`")
        for spec in s.data_columns:
            if spec.count(".") != 1 or not all(spec.split(".")):
                raise ValueError(f"surface '{s.key}' has a malformed data column '{spec}'")
        # §6.4. A trigger is the coverage rule for a surface that has no schedule. Declaring one on
        # a scheduled surface would give it two coverage answers, and the report would then have to
        # pick — which is the composite this whole feature refuses to build. The *name* is validated
        # in `surface_triggers.py`, at read time and in a test: an unrecognised name has to fail
        # closed into "unobservable" rather than at import, because that is the state a registry
        # that outlived its evaluator is actually in.
        if s.trigger and s.cadence not in ("event_driven", "unscheduled"):
            raise ValueError(
                f"surface '{s.key}' is {s.cadence} and is covered by elapsed time; a trigger would "
                f"be a second answer to the same question (§6.4)")
        if s.trigger is not None and not str(s.trigger).strip():
            raise ValueError(f"surface '{s.key}' declares an empty trigger")


_validate(REGISTRY)

BY_KEY: dict[str, Surface] = {s.key: s for s in REGISTRY}
KEYS: frozenset[str] = frozenset(BY_KEY)
# Commands are addressed by the `command` property rather than `surface`, so the two vocabularies
# are separated here once instead of at every call site.
COMMAND_KEYS: frozenset[str] = frozenset(s.key for s in REGISTRY if s.kind == "command")
SURFACE_KEYS: frozenset[str] = frozenset(s.key for s in REGISTRY if s.kind != "command")
# Declared routes in **registry order**, which is navigation order — §8's default for the report and
# for the screen-weight view, and never least-used-first. `dict.fromkeys` rather than `sorted` for
# exactly that reason: alphabetical would put `accounts` above `today` and read as a ranking of
# nothing. Commands are excluded because a command has no resting presence on a screen (§3) and
# would inflate a route's section count with something that occupies no space on it.
ROUTES: tuple[str, ...] = tuple(dict.fromkeys(s.route for s in REGISTRY if s.kind != "command"))


def get(key: str) -> Surface | None:
    return BY_KEY.get(key)


def is_surface(key) -> bool:
    """§5. A `surface` property value must name a registered non-command surface.

    Validation rejects an unregistered slug rather than storing it: an unknown surface in the data
    is worse than a dropped event, because it appears in the report as a row nobody can act on.
    """
    return isinstance(key, str) and key in SURFACE_KEYS


def is_command(key) -> bool:
    return isinstance(key, str) and key in COMMAND_KEYS


def window_days(cadence: str) -> int | None:
    """§6.2 — the days a window needs before it can say anything about this cadence.

    `None` for `event_driven` and `unscheduled`, which can never be covered by elapsed time. That
    is a refusal, not a missing value, and a caller that treats it as zero has produced exactly the
    confident lie §6.2 exists to prevent.
    """
    return WINDOW_DAYS.get(cadence)


def public(surface: Surface) -> dict:
    """The registry row as the client reads it. `label` is here and never in an event payload —
    `SENSITIVE_KEYS` already blocks it at the sink, so this is the only path human copy travels."""
    return {
        "key": surface.key, "label": surface.label, "route": surface.route,
        "kind": surface.kind, "cadence": surface.cadence,
        "window_days": window_days(surface.cadence),
        "reaches": list(surface.reaches), "provides": list(surface.provides),
        "explains_refusal": surface.explains_refusal,
        "instrumented": surface.instrumented is True,
        "review_on": surface.review_on, "removed_on": surface.removed_on,
    }


def listing() -> list[dict]:
    return [public(s) for s in REGISTRY]
