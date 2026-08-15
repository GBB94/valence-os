"""Stage 17 Slice 1 — the registry, its drift tests, and the six new events.

`SURFACE-USAGE-SPEC.md` §11 asks for five drift tests. They exist because the failure mode for a
tracking plan is not that it is wrong on the day it is written — it is that the app moves and the
plan does not, and six months later the report describes a product that no longer exists. Every test
here is a way for that drift to fail loudly instead of quietly.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from app import surfaces, telemetry

REPO = Path(__file__).resolve().parents[2]
APP = REPO / "backend" / "app"
CLIENT_REGISTRY = REPO / "frontend" / "src" / "surfaces.js"
FRONTEND_SRC = REPO / "frontend" / "src"


# --- §11.1 the registry is internally coherent ------------------------------------------------

def test_every_surface_declares_a_kind_a_cadence_and_a_route():
    assert surfaces.REGISTRY, "the registry is empty"
    for row in surfaces.REGISTRY:
        assert row.kind in surfaces.KINDS
        assert row.cadence in surfaces.CADENCES
        assert row.route and row.route == row.route.strip()
        assert row.added_on and re.match(r"^\d{4}-\d{2}-\d{2}$", row.added_on)


def test_a_surface_is_instrumented_or_says_why_not():
    """§11.1. The unexplained gap is the thing being prevented, not the gap itself.

    A surface can legitimately be hard to instrument. What it may not be is silently uninstrumented,
    because a zero in the report then means two different things — nobody used it, and nobody wired
    it up — and only one of those is a reason to remove anything.
    """
    for row in surfaces.REGISTRY:
        assert row.instrumented is True or (isinstance(row.instrumented, str) and row.instrumented.strip()), (
            f"{row.key} is neither instrumented nor accompanied by a reason")


def test_no_duplicate_keys_and_no_duplicate_labels():
    keys = [row.key for row in surfaces.REGISTRY]
    assert len(keys) == len(set(keys))
    # Two surfaces with the same label produce a report an operator cannot read, whatever the keys
    # say. The registry is the taxonomy, and a taxonomy with two identical names is not one.
    labels = [row.label for row in surfaces.REGISTRY]
    assert len(labels) == len(set(labels)), "two surfaces share a label"


# --- §11.5 an empty `reaches` has to be argued for ---------------------------------------------

def test_an_empty_reaches_carries_a_stated_reason():
    """§11.5 asks that a surface whose route renders records declares a non-empty `reaches`.

    There is no way to check "renders records" from the outside without a static-analysis project,
    so the rule is inverted into one that *is* checkable: an empty `reaches` must be accompanied by
    a sentence saying why it is empty. That turns the default from a shrug into a claim somebody
    signed, which is the same move `instrumented="<reason>"` makes.
    """
    for row in surfaces.REGISTRY:
        if row.reaches:
            assert not row.renders_no_records, f"{row.key} both reaches records and denies it"
            continue
        assert (row.renders_no_records or "").strip(), (
            f"{row.key} declares no record types and gives no reason")
        # A reason is a sentence, not a shrug.
        assert len(row.renders_no_records.split()) >= 5, f"{row.key} gives a placeholder reason"


def test_a_malformed_registry_fails_at_import():
    """The guard is not decoration — an entry missing its reason must actually raise."""
    bad = surfaces.Surface(key="x.y", label="X", route="today", kind="section",
                           cadence="weekly", added_on="2026-08-06")
    with pytest.raises(ValueError, match="empty"):
        surfaces._validate((bad,))
    unknown_kind = surfaces.Surface(key="x.y", label="X", route="today", kind="widget",
                                    cadence="weekly", added_on="2026-08-06", reaches=("account",))
    with pytest.raises(ValueError, match="kind"):
        surfaces._validate((unknown_kind,))


# --- §11.2 the client mirror does not drift ------------------------------------------------------

def _client_registry() -> dict[str, dict]:
    """Parse `SURFACES` out of the client mirror without running a JS engine."""
    text = CLIENT_REGISTRY.read_text(encoding="utf-8")
    body = text.split("export const SURFACES = Object.freeze({", 1)[1].split("});", 1)[0]
    rows = {}
    pattern = re.compile(
        r'"(?P<key>[^"]+)":\s*\{\s*route:\s*"(?P<route>[^"]*)",\s*kind:\s*"(?P<kind>[^"]*)",'
        r'\s*label:\s*"(?P<label>[^"]*)"\s*\}')
    for match in pattern.finditer(body):
        rows[match.group("key")] = {"route": match.group("route"), "kind": match.group("kind"),
                                    "label": match.group("label")}
    return rows


def test_the_client_registry_matches_the_server():
    client = _client_registry()
    server = {row.key: {"route": row.route, "kind": row.kind, "label": row.label}
              for row in surfaces.REGISTRY}
    assert client == server, "frontend/src/surfaces.js has drifted from app/surfaces.py"


def test_the_client_event_names_include_the_six_new_ones():
    text = (FRONTEND_SRC / "telemetry.js").read_text(encoding="utf-8")
    body = text.split("export const EVENT_NAMES = Object.freeze([", 1)[1].split("]);", 1)[0]
    client = re.findall(r'"([a-z0-9_]+)"', body)
    assert client == list(telemetry.EVENTS), "the client and server event lists have drifted"
    for name in ("surface_rendered", "surface_engaged", "surface_dismissed", "command_invoked",
                 "navigation_landed", "retirement_action_applied"):
        assert name in client


# --- §11.3 every wrapped surface key in the views is registered ---------------------------------

def test_every_surface_key_used_in_the_views_is_registered():
    """The drift that actually happens: a view is renamed or copied and its key stops existing.

    Scanning the source is the only check that sees a call site nobody exercised in a test.
    """
    used = set()
    for path in FRONTEND_SRC.rglob("*.jsx"):
        for match in re.finditer(r'surfaceKey="([^"]+)"', path.read_text(encoding="utf-8")):
            used.add(match.group(1))
    assert used, "no surface keys found in the views — the wrapper is not wired up"
    unknown = sorted(used - surfaces.KEYS)
    assert not unknown, f"views reference unregistered surfaces: {unknown}"
    commands = sorted(used & surfaces.COMMAND_KEYS)
    assert not commands, f"a command is not a rendered surface: {commands}"


def test_every_registered_non_command_surface_is_wrapped_somewhere():
    """The other direction. A registry row with no call site is a row that can only ever read zero.

    §13 says Slice 1 registers roughly the twenty highest-traffic surfaces and instruments them; a
    row registered but not wrapped would be exactly the "nobody wired this up" zero the previous
    test's rule exists to keep out of the report.
    """
    wrapped = set()
    for path in FRONTEND_SRC.rglob("*.jsx"):
        for match in re.finditer(r'surfaceKey="([^"]+)"', path.read_text(encoding="utf-8")):
            wrapped.add(match.group(1))
    missing = sorted(key for key in surfaces.SURFACE_KEYS
                     if key not in wrapped and surfaces.BY_KEY[key].instrumented is True)
    assert not missing, f"registered but never wrapped: {missing}"


def test_instrumented_means_a_surface_exposes_a_semantic_engagement_path():
    """A `<Surface>` wrapper proves exposure only; it does not make descendant controls engage.

    `instrumented=True` is therefore reserved for wrappers that consume the render prop's
    `engage`. Keeping both directions equal prevents a newly wrapped surface from silently entering
    the retirement report as "shown, never operated" before anybody defines what operation means.
    """
    wired = set()
    pattern = re.compile(
        r'<Surface\s+surfaceKey="([^"]+)">\s*\{\(\{\s*engage(?:\s*,[^}]*)?\s*\}\)\s*=>')
    for path in FRONTEND_SRC.rglob("*.jsx"):
        wired.update(pattern.findall(path.read_text(encoding="utf-8")))
    declared = {row.key for row in surfaces.REGISTRY
                if row.kind != "command" and row.instrumented is True}
    assert declared == wired, (
        "instrumented surfaces and semantic engage render-props have drifted: "
        f"declared only={sorted(declared - wired)}, wired only={sorted(wired - declared)}")


def test_every_registered_command_is_invoked_somewhere():
    invoked = set()
    for path in list(FRONTEND_SRC.rglob("*.jsx")) + list(FRONTEND_SRC.rglob("*.js")):
        text = path.read_text(encoding="utf-8")
        for match in re.finditer(r'commandProperties\(\s*"([^"]+)"', text):
            invoked.add(match.group(1))
    missing = sorted(surfaces.COMMAND_KEYS - invoked)
    assert not missing, f"registered commands with no call site: {missing}"


# --- §11.4 / §17.1 nothing domain-facing may read this ------------------------------------------

def test_no_domain_module_imports_the_registry():
    """§17.1, inherited unchanged. Which screens the operator uses may never reach an account.

    `telemetry.py` is the sink and is allowed; nothing else in `app/` is. The check is on the import
    rather than on a usage, because an import is the point at which the coupling becomes possible —
    and this is a rule about what could be built next, not only about what was built today.
    """
    # `telemetry.py` screens slugs against it; `surface_usage.py` reads it to build the §8 report.
    # `surface_triggers.py` reads domain tables to count §6.4's conditions — that is the measurement
    # feature reading the domain, which is the *permitted* direction. The rule is one-way on purpose:
    # a count of renewals may inform the report, and nothing in the report may inform an account.
    allowed = {"telemetry.py", "surfaces.py", "surface_usage.py", "surface_retirement.py",
               "surface_triggers.py"}
    offenders = []
    for path in sorted(APP.rglob("*.py")):
        if path.name in allowed:
            continue
        text = path.read_text(encoding="utf-8")
        if re.search(r"^\s*(from\s+\.+\s*import\s+surfaces|from\s+\.*surfaces\s+import|import\s+app\.surfaces)",
                     text, re.MULTILINE):
            offenders.append(str(path.relative_to(REPO)))
    assert not offenders, f"domain modules may not read the surface registry: {offenders}"


def test_no_score_rating_or_health_anywhere_in_stage_17():
    """§6's rule, asserted rather than promised.

    The single most likely wrong turn here is a composite "usage score" — it is what every vendor
    analytics product ships, it is easy, and it is exactly the thing that would let a screen be
    removed because a number went down rather than because somebody understood why. The four axes
    never combine, so no name for a combination may exist.
    """
    forbidden = re.compile(r"\b(usage_score|surface_score|usage_index|surface_rating|"
                           r"surface_health|engagement_score)\b")
    for path in (APP / "surfaces.py", APP / "telemetry.py", CLIENT_REGISTRY,
                 FRONTEND_SRC / "telemetry.js", FRONTEND_SRC / "Surface.jsx"):
        assert not forbidden.search(path.read_text(encoding="utf-8")), f"a score appears in {path}"


# --- §5 the six events -------------------------------------------------------------------------

def test_the_six_events_are_declared_with_their_properties():
    assert len(telemetry.EVENTS) == 28, "the allowlist should now hold twenty-eight events"
    assert set(telemetry.EVENTS["surface_rendered"]) == {
        "surface", "route", "kind", "render_reason", "position"}
    assert set(telemetry.EVENTS["surface_engaged"]) == {"surface", "route", "kind", "engagement"}
    assert set(telemetry.EVENTS["surface_dismissed"]) == {"surface", "route", "dismiss_kind"}
    assert set(telemetry.EVENTS["command_invoked"]) == {"command", "route", "entry_point"}
    assert set(telemetry.EVENTS["navigation_landed"]) == {
        "route", "entry_point", "is_first_of_session"}
    # Both vocabularies, because a command is retirable too (§7.4) and naming one in the `surface`
    # property is exactly the confusion the next test forbids. Exactly one of the two is required.
    assert set(telemetry.EVENTS["retirement_action_applied"]) == {
        "surface", "command", "action", "cause_code"}
    with pytest.raises(telemetry.TelemetryRejected, match="requires one of"):
        telemetry.validate("retirement_action_applied",
                           properties={"action": "retire", "cause_code": "not_needed"})
    with pytest.raises(telemetry.TelemetryRejected, match="more than one of"):
        telemetry.validate("retirement_action_applied",
                           properties={"surface": "today.queue",
                                       "command": "command.log_interaction",
                                       "action": "retire", "cause_code": "not_needed"})


def test_an_unregistered_surface_slug_is_rejected_not_stored():
    """§5's rule, and the reason it is a rejection.

    A stored unknown surface appears in the report as a row nobody can act on, and the obvious
    repair — adding a registry entry to match the data — is how the registry stops describing the
    app and starts describing the telemetry.
    """
    with pytest.raises(telemetry.TelemetryRejected, match="not a registered surface"):
        telemetry.validate("surface_rendered", properties={
            "surface": "today.a_surface_that_never_existed", "route": "today",
            "kind": "section", "render_reason": "navigation"})


def test_a_command_key_is_not_a_surface_key_and_the_reverse():
    """The two vocabularies are separate, and each event names which one it takes."""
    with pytest.raises(telemetry.TelemetryRejected, match="not a registered surface"):
        telemetry.validate("surface_rendered", properties={
            "surface": "command.log_interaction", "route": "global", "kind": "command",
            "render_reason": "navigation"})
    with pytest.raises(telemetry.TelemetryRejected, match="not a registered command"):
        telemetry.validate("command_invoked", properties={
            "command": "today.queue", "route": "today", "entry_point": "toolbar"})


def test_a_value_outside_a_closed_vocabulary_is_rejected():
    for properties, bad in (
        ({"surface": "today.queue", "route": "today", "kind": "section",
          "render_reason": "scrolled"}, "surface_rendered"),
        ({"surface": "today.queue", "route": "today", "kind": "section",
          "engagement": "hovered"}, "surface_engaged"),
        ({"surface": "today.queue", "route": "today", "dismiss_kind": "ignored"},
         "surface_dismissed"),
        ({"surface": "today.queue", "action": "delete", "cause_code": "not_needed"},
         "retirement_action_applied"),
        # §7.1's seven cause codes are closed and carry no `other`, because a cause code with an
        # escape hatch collects the escape hatch.
        ({"surface": "today.queue", "action": "retire", "cause_code": "other"},
         "retirement_action_applied"),
    ):
        with pytest.raises(telemetry.TelemetryRejected, match="closed vocabulary"):
            telemetry.validate(bad, properties=properties)


def test_a_surface_event_without_its_surface_is_rejected():
    """An event the report cannot attribute to anything can only inflate a total."""
    with pytest.raises(telemetry.TelemetryRejected, match="requires the 'surface' property"):
        telemetry.validate("surface_engaged", properties={"engagement": "opened"})
    with pytest.raises(telemetry.TelemetryRejected, match="requires the 'engagement' property"):
        telemetry.validate("surface_engaged", properties={"surface": "today.queue"})


def test_a_label_can_never_travel_with_an_event():
    """`label` lives on the registry row and reaches a screen, never the sink.

    It is in `SENSITIVE_KEYS` already; this asserts the two halves agree, because the registry is
    the first place in this codebase where human copy sits next to a measurement payload.
    """
    assert "label" in telemetry.SENSITIVE_KEYS
    with pytest.raises(telemetry.TelemetryRejected, match="person content"):
        telemetry.validate("surface_rendered", properties={
            "surface": "today.queue", "route": "today", "kind": "section",
            "render_reason": "navigation", "label": "Attention queue"})


def test_a_valid_surface_event_round_trips():
    row = telemetry.validate("surface_rendered", account_id="acc-1", properties={
        "surface": "overview.account_path", "route": "account.overview", "kind": "section",
        "render_reason": "navigation", "position": 0})
    assert row["event_name"] == "surface_rendered"
    payload = json.loads(row["properties_json"])
    assert payload["surface"] == "overview.account_path"
    assert payload["position"] == 0
    # No label, no title, no account name — only strings this repo authored.
    assert set(payload) == {"surface", "route", "kind", "render_reason", "position"}


def test_navigation_landed_takes_a_route_without_a_surface():
    row = telemetry.validate("navigation_landed", properties={
        "route": "account.people", "entry_point": "navigation", "is_first_of_session": True})
    assert json.loads(row["properties_json"])["route"] == "account.people"


# --- §6.2 window coverage is a refusal, not a zero ----------------------------------------------

def test_event_driven_and_unscheduled_have_no_elapsed_time_window():
    """§6.4. These two can never be observed as unused by elapsed time at all.

    `None` rather than `0`, because a caller that treats the answer as a number will conclude that
    every window covers them — the confident lie §6.2 exists to prevent.
    """
    assert surfaces.window_days("event_driven") is None
    assert surfaces.window_days("unscheduled") is None
    assert surfaces.window_days("session") == 14
    assert surfaces.window_days("weekly") == 28
    assert surfaces.window_days("monthly") == 90
    assert surfaces.window_days("quarterly") == 210


def test_the_public_row_carries_the_window_and_never_a_state():
    """§7.3. Current retirement action is derived from the notes table, never stored here.

    A `state` on the registry row would be a code constant and a database row claiming authority
    over the same question, and the code constant would win silently.
    """
    row = surfaces.public(surfaces.BY_KEY["today.queue"])
    assert row["window_days"] == 14
    for forbidden in ("state", "current_state", "retirement", "status", "score"):
        assert forbidden not in row
