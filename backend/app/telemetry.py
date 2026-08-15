"""Account Path Slice 7 — the product-measurement adapter boundary (`ACCOUNT-PATH-SPEC.md` §17).

Product events are **operational diagnostics**. Nothing in this module may be read by account
status, pillar state, ranking, generated outputs, or any customer-facing surface (§17.1), and
`tests/test_account_path_slice7.py` asserts that no domain module imports it.

Three rules carry the design:

- **Measurement never blocks work (§17.8).** `record()` cannot raise. Every failure — validation,
  a disabled setting, a locked database, a missing table — returns a reason and is dropped.
- **The contract is an allowlist, not a filter.** An event name must be one of the sixteen in
  §17.3 or one of the six `ACCOUNT-INTAKE-SPEC.md` §17 amends in, and each carries its own set of
  permitted property keys. A property the event does not
  declare is rejected rather than trimmed, because a trimmed payload is one nobody notices.
- **Values are shaped, not merely typed.** Every string property must be a lower-case slug. That
  is what structurally excludes the things §17.2 prohibits — titles, descriptions, transcript
  text, source spans, person names, email addresses, document contents, free-form notes. A rule
  that only forbade a list of key names would be defeated by the next key nobody thought of.

`ACCOUNT-PATH-SPEC.md` §17.3 asks for two behaviours from one condition: an unknown event is
*rejected in development* and *ignored with a diagnostic in production*. `validate()` raises;
`record()` swallows. The API route picks which one the caller sees, from `strict_mode()`.
"""
from __future__ import annotations

import json
import logging
import os
import re
import sqlite3

from . import surfaces
from .db import new_id, now_utc

log = logging.getLogger("valence.telemetry")

SCHEMA_VERSION = 1
STRICT_ENV = "VALENCE_OS_TELEMETRY_STRICT"

# Shape rules. A slug covers every legitimate value: reason codes, phases, source types, coverage
# words, enum states. It cannot express a sentence, a name, or an address.
_SLUG = re.compile(r"^[a-z0-9][a-z0-9_.:-]{0,63}$")
_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,63}$")
_SESSION = re.compile(r"^[a-z0-9][a-z0-9-]{7,63}$")
_TIMESTAMP = re.compile(r"^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})(\.\d+)?(Z|\+00:00)?$")
_MAX_INT = 100_000
_MAX_PROPERTIES = 12

# Context every event may carry. Kept short deliberately: a shared bag is where an unbounded
# property eventually lands.
_COMMON = ("scope_mode", "current_phase")

# §17.3, with the bounded metadata each one is allowed to carry. Adding a key here is the review
# point for "is this still diagnostics?" — which is the reason the list is explicit per event
# rather than one shared schema.
EVENTS: dict[str, tuple[str, ...]] = {
    "account_path_viewed": (
        "has_next_move", "empty_state_variant", "coverage_status", "readiness_coverage",
        "program_count", "you_own_count", "waiting_count",
    ),
    "next_move_opened": ("source_type", "reason_code", "band", "urgency", "owner_side",
                         "due_state"),
    "next_move_snoozed": ("source_type", "reason_code", "snooze_days", "snooze_key_present"),
    # Named for what it observes, not for what we hope it means. Account Path never closes
    # anything (§7.1), so the only thing the client can see is that a recommended row it watched
    # somebody open is absent from a later complete-coverage response. A cancellation, an archival
    # and an aged-out band window all produce that absence too, and calling the count
    # `next_move_completed` made a funnel whose purpose is "was the recommendation acted on"
    # answer with cancellations included — the metric arguing for its own success.
    "next_move_left_list": ("source_type", "reason_code", "urgency", "due_state"),
    "successor_action_created": ("source_type", "reason_code", "successor_type"),
    "execution_group_opened": ("group", "item_count"),
    "program_path_filtered": ("filter", "phase", "result_count"),
    "requirement_opened": ("pillar", "requirement_state", "freshness", "applicability",
                           "coverage"),
    "requirement_action_created": ("pillar", "action_type", "from_suggestion"),
    "proposal_review_opened": ("intent", "target_type", "proposal_count", "run_status"),
    # `bulk` is a bounded boolean, and it is here rather than in a separate `proposals_accept_all`
    # event on purpose: each item in a run-scoped accept-all genuinely *is* an acceptance, so
    # emitting a different event for it would leave the acceptance funnel undercounting by however
    # much the batch path is used. The flag is what lets a later reader separate the two without
    # the counts disagreeing.
    "proposal_accepted": ("intent", "target_type", "edited", "bulk"),
    "proposal_rejected": ("intent", "target_type", "reason_code"),
    "phase_readiness_opened": ("gate_state", "next_phase", "blocking_count"),
    "phase_transition_completed": ("from_phase", "to_phase", "waived_count", "override"),
    "execution_native_target_opened": ("source_type", "target_tab", "from_surface"),
    "execution_path_retry": ("failure_kind", "omitted_source", "attempt"),

    # --- ACCOUNT-INTAKE-SPEC.md §17 (D-246) — the drop zone's six -----------------------------
    # The amendment §17 asked for, and the reason it is an amendment rather than a new module: a
    # second event store would have its own contract, and two contracts about what may leave a
    # record eventually disagree. Sixteen becomes twenty-two here and in `frontend/src/telemetry.js`.
    #
    # §17's property rule is narrower than the surrounding events, and deliberately so: **a
    # filename is document content by another name**. So none of these carries a filename, a
    # kind, a size, a byte count, or a proposal count — only the account id and session token
    # every event already carries, plus a reason code where the operator was told "no". `kind`
    # and `proposal_count` were both considered and left out: they can be added at this review
    # point later, and they cannot be un-collected.
    "drop_zone_shown": (),
    "drop_received": (),
    # The only one §17 gives a property, and the code is the drop's own `outcome` vocabulary —
    # already a bounded five-value enum the schema checks, so nothing new is being invented to
    # measure with.
    "drop_refused": ("reason_code",),
    "drop_drafted": (),
    # No reason code, though "was it HTML-only or all-quoted?" is the diagnostic somebody will
    # eventually want. There is no such code on the server — only the operator's sentence — and
    # the client deriving one by matching that prose would be a view reconstructing server
    # semantics from a sentence the server authored (D-153). It gets a column first, or not at all.
    "drop_no_proposals": (),
    "drop_receipt_opened": (),

    # --- SURFACE-USAGE-SPEC.md §5 (Stage 17) — the six that observe our own surfaces -----------
    # Twenty-two becomes twenty-eight, here and in `frontend/src/telemetry.js`. Again an amendment
    # rather than a second module, for the reason the drop zone's six were: one contract about what
    # may leave a record, or eventually two that disagree.
    #
    # These carry a `surface` or `command` naming a row in `surfaces.REGISTRY`, and an unregistered
    # slug is **rejected rather than stored** (§5). A stored unknown surface is worse than a dropped
    # event: it appears in the §9 report as a row with counts nobody can act on, and the obvious
    # repair — inventing a registry entry to match the data — is how the registry stops describing
    # the app and starts describing the telemetry.
    #
    # `label` is never here. It is on the registry row, the client joins the two for display, and
    # `SENSITIVE_KEYS` blocks the key outright — so human copy has exactly one path to a screen and
    # none to the sink.
    "surface_rendered": ("surface", "route", "kind", "render_reason", "position"),
    "surface_engaged": ("surface", "route", "kind", "engagement"),
    # Separate from `surface_engaged` with `engagement='dismissed'`, though it could have been a
    # value there. §6.3's clutter reading turns on distinguishing "operated" from "got rid of", and
    # a dismissal folded in as one more engagement value would make the clutter case count as
    # engagement — the surface scoring best on the axis meant to find it.
    "surface_dismissed": ("surface", "route", "dismiss_kind"),
    "command_invoked": ("command", "route", "entry_point"),
    "navigation_landed": ("route", "entry_point", "is_first_of_session"),
    # The audit trail for a simplification pass, in the same sink as the evidence for it. `cause_code`
    # is §7.1's closed seven, so the reason a surface was collapsed stays a bounded code and never
    # becomes the operator's sentence — that lives on `surface_retirement_notes`, which is a record
    # and not a diagnostic.
    #
    # It declares **both** `surface` and `command` because a command is retirable too (§7.4), and
    # §5's two vocabularies are not interchangeable — naming a command in the `surface` property
    # would be exactly the confusion `test_the_two_vocabularies_are_not_interchangeable` forbids.
    # The alternative was to drop command retirements from the sink, which would leave the funnel
    # quietly under-counting the one action it exists to record.
    "retirement_action_applied": ("surface", "command", "action", "cause_code"),
}

# §5. Properties whose value must name a registry row. Held as a mapping rather than checked at
# each call site so that adding an event carrying a surface cannot forget the check.
_REGISTRY_PROPERTIES = {"surface": surfaces.is_surface, "command": surfaces.is_command}

# The §5 six are the only events with a property that must be *present*. Everywhere else an absent
# property is a legitimately unknown one; here it is a broken emitter, and an event with no surface
# on it is a row the report cannot attribute to anything and can only silently inflate a total.
_REQUIRED: dict[str, tuple[str, ...]] = {
    "surface_rendered": ("surface", "route"),
    "surface_engaged": ("surface", "engagement"),
    "surface_dismissed": ("surface", "dismiss_kind"),
    "command_invoked": ("command", "entry_point"),
    "navigation_landed": ("route",),
    "retirement_action_applied": ("action", "cause_code"),
}

# Events that must carry at least one of a set. Only `retirement_action_applied` has one, because it
# is the only event that can be about either vocabulary. Expressed as an either-or rather than by
# relaxing `_REQUIRED` to nothing, so an action recorded against neither is still a broken emitter.
_REQUIRED_ONE_OF: dict[str, tuple[str, ...]] = {
    "retirement_action_applied": ("surface", "command"),
}

# §5's closed vocabularies. Checked rather than merely slug-shaped, because each one is read as a
# category in §6 — an unexpected value would not fail, it would quietly open a new bucket.
_ENUMS: dict[str, frozenset[str]] = {
    "render_reason": frozenset({"navigation", "restore", "filter_change"}),
    # `operated` (D-366) is the generic seventh: emitted only by the wrapper's own listener when
    # an interactive control inside a surface is operated and no semantic action is wired there.
    # It is a separate value, never a synonym for the six, so a report reader can tell "we know
    # which operation" apart from "we know a control was touched".
    "engagement": frozenset({"opened", "filtered", "expanded", "edited", "dismissed",
                             "followed_link", "operated"}),
    "dismiss_kind": frozenset({"collapsed", "closed", "hidden"}),
    "entry_point": frozenset({"toolbar", "keyboard", "menu", "empty_state", "navigation",
                              "link", "restore"}),
    "kind": frozenset(surfaces.KINDS),
    "action": frozenset({"collapse", "demote", "retire", "restore"}),
    # §7.1. Seven, closed, and no `other`: a cause code with an escape hatch collects the escape
    # hatch, and "why was this removed" is exactly the question a later reader needs answered.
    "cause_code": frozenset({"not_needed", "not_found", "misunderstood", "hard_to_use",
                             "narrow_but_needed", "superseded", "demo_artifact"}),
}

# Names that must never appear as a property key, whatever an event declares. The per-event
# allowlist already makes these unreachable; this list exists so the *reason* a caller sees names
# the trust boundary rather than saying "unknown key", and so a future event definition cannot
# quietly introduce one. `test_no_allowlisted_property_is_sensitive` fails if the two ever agree.
SENSITIVE_KEYS = frozenset({
    "title", "name", "person", "person_name", "owner_name", "stakeholder", "email",
    "email_address", "description", "note", "notes", "text", "body", "content", "transcript",
    "snippet", "span", "source_span", "quote", "comment", "summary", "rationale", "reason_text",
    "label", "message", "subject", "account_name", "program_name", "document",
})


class TelemetryRejected(ValueError):
    """A payload that does not meet the §17.2 contract. Raised only by `validate()`."""


def strict_mode() -> bool:
    """§17.3. Development rejects an invalid event; production ignores it with a diagnostic.

    This is a local single-editor build, so the default is development. The route reads this;
    `record()` never does, because an internal caller must not be able to fail a user action.
    """
    return (os.environ.get(STRICT_ENV, "1") or "").strip().lower() not in {"0", "false", "no"}


# --- validation -----------------------------------------------------------------------------

def _check_value(key: str, value) -> None:
    if isinstance(value, bool):
        return
    if isinstance(value, int):
        if not (0 <= value <= _MAX_INT):
            raise TelemetryRejected(f"property '{key}' is outside the bounded integer range")
        return
    if isinstance(value, str):
        if not _SLUG.match(value):
            raise TelemetryRejected(
                f"property '{key}' is not a bounded slug value; titles, names, addresses, and "
                f"free text may not be measured (§17.2)")
        return
    raise TelemetryRejected(f"property '{key}' must be a slug, an integer, or a boolean")


def validate(event_name: str, *, account_id=None, program_id=None, occurred_at=None,
             session_id=None, properties=None, ranking_rule_version=None) -> dict:
    """Return the row this event would write, or raise `TelemetryRejected`.

    Pure: it reads no database and writes nothing, so the same payload always gets the same
    verdict whether it arrived from the API, from a test, or from a future internal caller.
    """
    if event_name not in EVENTS:
        raise TelemetryRejected(f"unknown event '{event_name}' is not in the §17.3 allowlist")

    props = properties or {}
    if not isinstance(props, dict):
        raise TelemetryRejected("properties must be an object")
    props = {k: v for k, v in props.items() if v is not None}
    if len(props) > _MAX_PROPERTIES:
        raise TelemetryRejected("too many properties for one event")

    allowed = set(EVENTS[event_name]) | set(_COMMON)
    for key, value in props.items():
        if key in SENSITIVE_KEYS:
            raise TelemetryRejected(
                f"property '{key}' names customer or person content and can never be measured "
                f"(§17.2)")
        if key not in allowed:
            raise TelemetryRejected(f"property '{key}' is not declared by '{event_name}'")
        _check_value(key, value)
        # §5. The registry is the vocabulary; an unregistered slug is rejected, not stored.
        checker = _REGISTRY_PROPERTIES.get(key)
        if checker is not None and not checker(value):
            raise TelemetryRejected(
                f"'{value}' is not a registered {key}; SURFACE-USAGE-SPEC.md §5 rejects an "
                f"unregistered slug rather than storing it")
        if key in _ENUMS and isinstance(value, str) and value not in _ENUMS[key]:
            raise TelemetryRejected(f"property '{key}' has a value outside its closed vocabulary")

    for key in _REQUIRED.get(event_name, ()):
        if key not in props:
            raise TelemetryRejected(f"'{event_name}' requires the '{key}' property")

    one_of = _REQUIRED_ONE_OF.get(event_name, ())
    if one_of and not any(key in props for key in one_of):
        raise TelemetryRejected(
            f"'{event_name}' requires one of {', '.join(one_of)}")
    if len(one_of) > 1 and sum(1 for key in one_of if key in props) > 1:
        # Both would mean one row counted under two vocabularies, and §6 reads them separately.
        raise TelemetryRejected(
            f"'{event_name}' names more than one of {', '.join(one_of)}")

    for label, value in (("account_id", account_id), ("program_id", program_id),
                         ("ranking_rule_version", ranking_rule_version)):
        if value is not None and not _ID.match(str(value)):
            raise TelemetryRejected(f"{label} is not a bounded internal identifier")

    if session_id is not None and not _SESSION.match(str(session_id)):
        raise TelemetryRejected("session_id must be a pseudonymous local slug")
    if occurred_at is None:
        stamped = now_utc()
    else:
        match = _TIMESTAMP.match(str(occurred_at))
        if not match:
            raise TelemetryRejected("occurred_at must be an ISO-8601 UTC timestamp")
        # Normalised to the application's own timestamp form. A browser sends `...Z`; every other
        # timestamp in this database is `...+00:00`, and two spellings of the same instant sort
        # differently, which would make a retention cutoff and a funnel window disagree.
        stamped = f"{match.group(1)}+00:00"

    payload = json.dumps(props, sort_keys=True, separators=(",", ":"))
    if len(payload) > 512:
        raise TelemetryRejected("property payload exceeds the bounded size")

    return {
        "id": new_id(),
        "event_name": event_name,
        "schema_version": SCHEMA_VERSION,
        "occurred_at": stamped,
        "session_id": session_id or "local-session",
        "account_id": account_id,
        "program_id": program_id,
        "ranking_rule_version": ranking_rule_version,
        "properties_json": payload,
        "created_at": now_utc(),
    }


# --- settings -------------------------------------------------------------------------------

def settings(conn: sqlite3.Connection) -> dict:
    row = conn.execute(
        "SELECT enabled,retention_days,updated_at,rollup_retention_months,measuring_since "
        "FROM product_telemetry_settings WHERE id='singleton'"
    ).fetchone()
    if row is None:  # pragma: no cover - the migration seeds the singleton
        return {"enabled": False, "retention_days": 90, "updated_at": None,
                "rollup_retention_months": 36, "measuring_since": None}
    return {"enabled": bool(row["enabled"]), "retention_days": int(row["retention_days"]),
            "updated_at": row["updated_at"],
            # §9.4's two retentions sit side by side in the response for the same reason they sit
            # side by side in migration 0055: the rollup outliving the raw events is a claim about
            # carrying strictly less, and it should be visible next to the thing it differs from.
            "rollup_retention_months": int(row["rollup_retention_months"]),
            "measuring_since": row["measuring_since"]}


def set_settings(conn: sqlite3.Connection, *, enabled=None, retention_days=None) -> dict:
    current = settings(conn)
    new_enabled = current["enabled"] if enabled is None else bool(enabled)
    new_retention = current["retention_days"] if retention_days is None else int(retention_days)
    if not 1 <= new_retention <= 400:
        raise ValueError("retention_days must be between 1 and 400")
    stamp = now_utc()
    # Switching measurement on starts a new observation period. It is recorded rather than inferred
    # from the earliest surviving row, because inferring it would make a quiet month look like a
    # short window — the inversion of the rule §6.2 exists to enforce (SURFACE-USAGE-SPEC.md §9.1).
    since = current["measuring_since"]
    if new_enabled and not current["enabled"]:
        since = stamp
    # Turning measurement off discards what was already collected. Leaving it in place would make
    # "measurement is disabled" and "there is measurement data" both true at once — and that applies
    # to the monthly rollup exactly as it does to the raw events, so the setting and both deletes
    # are ONE transaction. They were two: the flag committed on its own, and anything that stopped
    # the process in between left the installation reporting measurement off with every event still
    # sitting in the table. That is not a stale read, it is exactly the loophole the off switch
    # exists to close, and it would have been invisible from the settings screen (§9.4).
    with conn:
        conn.execute(
            "UPDATE product_telemetry_settings SET enabled=?,retention_days=?,updated_at=?,"
            "measuring_since=? WHERE id='singleton'",
            (1 if new_enabled else 0, new_retention, stamp, since))
        if not new_enabled:
            conn.execute("DELETE FROM product_events")
            conn.execute("DELETE FROM surface_usage_months")
            conn.execute("UPDATE product_telemetry_settings "
                         "SET surface_rollup_watermark=0, measuring_since=NULL "
                         "WHERE id='singleton'")
    return settings(conn)


def purge_expired(conn: sqlite3.Connection, retention_days: int | None = None) -> int:
    """§17.4 bounded retention. Cheap enough to run on write at this scale.

    Folds before it deletes, and then deletes only what the fold has already read. Retention runs
    on every write; the 36-month rollup was only advanced on a report read. An installation nobody
    opened the usage report in for a quarter therefore purged raw events that had never reached
    `surface_usage_months`, and because that rollup is monotone and never recomputed, the counts
    were not merely stale — they were gone, with no gap anywhere to say so. Silent loss in the one
    table whose whole purpose is to be the durable record.

    The `rowid <= watermark` clause is what makes that structural rather than a matter of call
    order: an unfolded surface event cannot be deleted by this statement even if the fold above it
    failed outright, in which case the mark simply does not advance and the rows wait. Only the two
    folded event names are held back — the other fourteen reach no rollup, so gating them on a mark
    they never advance would keep them past their retention for nothing.

    Failing towards keeping data: a fold that raises leaves rows to be purged next time, while a
    delete that ran anyway would have destroyed the only copy.
    """
    try:
        from . import surface_usage          # lazily: `surface_retirement` imports this module
        surface_usage.fold(conn)
    except Exception as exc:  # noqa: BLE001 - see above; the watermark clause covers the failure
        log.warning("surface rollup fold before purge failed, purging folded rows only: %s", exc)

    days = retention_days if retention_days is not None else settings(conn)["retention_days"]
    cutoff = conn.execute("SELECT datetime('now', ?)", (f"-{int(days)} days",)).fetchone()[0]
    row = conn.execute("SELECT surface_rollup_watermark FROM product_telemetry_settings "
                       "WHERE id='singleton'").fetchone()
    watermark = int(row[0]) if row else 0
    with conn:
        cursor = conn.execute(
            "DELETE FROM product_events WHERE occurred_at < ? AND ("
            "  event_name NOT IN ('surface_rendered','surface_engaged') OR rowid <= ?)",
            (cutoff.replace(" ", "T"), watermark))
    return cursor.rowcount or 0


# --- the write path -------------------------------------------------------------------------

def record(conn: sqlite3.Connection, event_name: str, **fields) -> dict:
    """Record one event. Never raises — a measurement failure is not a user-facing failure.

    Returns `{"recorded": bool, "reason": str | None}` so a caller that wants to know can look,
    and a caller that does not can ignore it. There is no exception path on purpose: the moment
    this can throw, a page that opens fine with measurement off starts failing with it on.
    """
    try:
        if not settings(conn)["enabled"]:
            return {"recorded": False, "reason": "measurement is disabled"}
        row = validate(event_name, **fields)
        columns = ",".join(row)
        with conn:
            conn.execute(f"INSERT INTO product_events ({columns}) "
                         f"VALUES ({','.join('?' for _ in row)})", tuple(row.values()))
        purge_expired(conn)
        return {"recorded": True, "reason": None, "id": row["id"]}
    except TelemetryRejected as exc:
        log.warning("product event rejected: %s", exc)
        return {"recorded": False, "reason": str(exc)}
    except Exception as exc:  # noqa: BLE001 - a diagnostic sink must never surface its own faults
        log.warning("product event dropped: %s", exc)
        return {"recorded": False, "reason": "measurement sink unavailable"}


# --- the read path (§17.5) ------------------------------------------------------------------

def _count(conn: sqlite3.Connection, sql: str, params=()) -> int:
    return int(conn.execute(sql, params).fetchone()[0])


def funnel(conn: sqlite3.Connection, account_id: str | None = None) -> dict:
    """The §17.5 funnel, as counts an operator can read beside a qualitative review.

    Deliberately not a score. §17.5 ends with "clicks alone do not define success", so this
    returns the raw denominators — views, opens, outcomes, bypassed reason codes, coverage
    failures — and states in the response that a click-through number is not a quality number.
    """
    where, params = ("", ())
    if account_id:
        where, params = (" AND account_id=?", (account_id,))

    def block(extra_where: str = "", extra_params: tuple = ()) -> dict:
        """One funnel's worth of counts over a scope. Called once for every ordering in the data."""
        w = where + extra_where
        p = (*params, *extra_params)

        def n(event: str) -> int:
            return _count(conn, f"SELECT COUNT(*) FROM product_events WHERE event_name=?{w}",
                          (event, *p))

        offered = _count(
            conn,
            "SELECT COUNT(*) FROM product_events WHERE event_name='account_path_viewed' "
            f"AND json_extract(properties_json,'$.has_next_move')=1{w}", p)
        coverage_failures = _count(
            conn,
            "SELECT COUNT(*) FROM product_events WHERE event_name='account_path_viewed' "
            f"AND json_extract(properties_json,'$.coverage_status') IN ('partial','unavailable')"
            f"{w}", p)

        reason_rows = conn.execute(
            "SELECT json_extract(properties_json,'$.reason_code') code, event_name, COUNT(*) n "
            "FROM product_events WHERE event_name IN "
            f"('next_move_opened','next_move_left_list','next_move_snoozed'){w} "
            "AND json_extract(properties_json,'$.reason_code') IS NOT NULL "
            "GROUP BY 1, 2", p).fetchall()
        by_reason: dict[str, dict] = {}
        for row in reason_rows:
            entry = by_reason.setdefault(row["code"], {"reason_code": row["code"], "opened": 0,
                                                       "left_list": 0, "snoozed": 0})
            entry[{"next_move_opened": "opened", "next_move_left_list": "left_list",
                   "next_move_snoozed": "snoozed"}[row["event_name"]]] += row["n"]

        return {
            "totals": {
                "views": n("account_path_viewed"),
                "views_with_next_move": offered,
                "next_move_opened": n("next_move_opened"),
                "next_move_left_list": n("next_move_left_list"),
                "next_move_snoozed": n("next_move_snoozed"),
                "successor_actions_created": n("successor_action_created"),
                "views_with_incomplete_coverage": coverage_failures,
            },
            "by_reason_code": sorted(by_reason.values(), key=lambda r: r["reason_code"]),
        }

    rule_versions = [
        {"ranking_rule_version": r[0], "events": r[1]} for r in conn.execute(
            "SELECT ranking_rule_version, COUNT(*) FROM product_events "
            f"WHERE ranking_rule_version IS NOT NULL{where} GROUP BY 1 ORDER BY 1", params)
    ]

    caveat = ("Counts describe use, not recommendation quality. §17.5 requires a periodic "
              "qualitative review of whether the recommendation was correct; a click-through "
              "rate cannot answer that and must not be reported as if it could.")
    if len(rule_versions) > 1:
        # The whole reason every event carries its ranking rule version (D-156…D-161) is so a
        # funnel cannot average two orderings. Recording the column and then reading past it is
        # the same failure with an extra step, so when the data spans more than one ordering the
        # aggregate says so and `by_rule_version` carries the separable numbers.
        caveat += (" These aggregate counts span more than one ranking ruleset and therefore "
                   "describe no single ordering; read `by_rule_version` instead.")

    return {
        "scope": {"account_id": account_id},
        "settings": settings(conn),
        **block(),
        "by_rule_version": [
            {"ranking_rule_version": v["ranking_rule_version"],
             **block(" AND ranking_rule_version=?", (v["ranking_rule_version"],))}
            for v in rule_versions
        ],
        "spans_multiple_rule_versions": len(rule_versions) > 1,
        "rule_versions": rule_versions,
        # Stated in the payload, not just in a doc, because this is the number most likely to be
        # quoted on its own.
        "caveat": caveat,
    }
