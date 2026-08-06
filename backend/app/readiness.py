"""Relationship readiness evaluation (RELATIONSHIP-READINESS-SPEC.md §§2-5).

A query-time projection over accepted canonical records. It writes nothing, stores no state, and
produces no composite score: six independent pillars, each explaining itself down to the records
that decided it.

Three rules in here are load-bearing and non-obvious:

  * **Program evidence never leaks.** `stakeholder_roles`, `advocacy_events`, and `interactions`
    are all program-scoped (or program-nullable), and an F100 account runs several programs at
    once. A champion validated by advocacy in Program A is not a champion in Program B, so this
    module resolves advocacy per program rather than calling `people_core.effective_role`, which
    is person-scoped and would carry the validation across every program the person touches.
  * **A defaulted stakeholder layer is not layer evidence.** `people_core.resolved_layer()` falls
    back to a per-role default, so three people whose layer was never assessed would otherwise
    span three "layers" (champion->operational, budget_owner->economic, sponsor->executive) and
    satisfy breadth from defaults alone. The breadth spread component requires an explicitly
    assessed layer and reports a defaulted one as `unsupported` provenance (§5.3).
  * **State and freshness are independent (§3.4).** A component carries its own window, so one
    fresh component can never make a stale required component look current, and a known identity
    with stale engagement stays thin+stale rather than collapsing to unknown.

Evaluators are deterministic, allowlisted, and versioned. A definition row configures an
evaluator; it cannot create one. An unknown key or unsupported version fails closed into partial
coverage rather than silently dropping a pillar (§2.3, §3.5).

One input is not a canonical record: the operator exceptions §3.2 delegates to Account Path
(`ACCOUNT-PATH-SPEC.md` §13.2). They are read here rather than adapted on top, because an
applicability decision that lived outside the evaluator would be a second answer to the question
this module already answers. Both kinds subtract and neither adds — a `not_applicable` decision
stops a requirement being evaluated, a `waiver` silences the outstanding ask while the state keeps
telling the truth, and there is no exception kind that can mark anything `met`.
"""
from __future__ import annotations

import json
import sqlite3
from datetime import date, timedelta

from fastapi import HTTPException

from . import db, people_core, short_ref

# --- contract vocabularies (§3) ----------------------------------------------------------------
STATES = ("met", "thin", "unknown", "conflicted", "not_applicable")
FRESHNESS = ("current", "stale", "mixed", "undated", "not_applicable")
COVERAGE = ("complete", "partial", "unavailable")
APPLICABILITY = ("required", "optional", "not_due", "not_applicable")
# §5.3 — provenance quality, separate from business state. `unsupported` evidence can explain why
# a condition is thin; it can never satisfy an evidence-required component.
PROVENANCE = ("confirmed_source", "operator_recorded", "unsupported")

# Advocacy kinds that validate a champion (§3.2 of the people spec, reused deliberately).
_CHAMPION_EVIDENCE_KINDS = people_core._CHAMPION_EVIDENCE


class _Ctx:
    """Everything an evaluator may read. Evaluators receive this and never touch globals."""

    def __init__(self, conn, account_id, program_id, as_of, program):
        self.conn = conn
        self.account_id = account_id
        self.program_id = program_id
        self.as_of = as_of
        self.program = program
        # Resolved once per scope. Evaluators never see these: an exception decides whether a
        # requirement is evaluated at all, and letting an evaluator read one would let a
        # suppression reach inside the evidence it is supposed to stand outside of.
        self.exceptions = _live_exceptions(conn, account_id, program_id, as_of)
        self._cache: dict = {}

    def cached(self, key, fn):
        if key not in self._cache:
            self._cache[key] = fn()
        return self._cache[key]


# --- dates ---------------------------------------------------------------------------------------

def _as_of(value: str | None) -> str:
    return value or db.now_utc()[:10]


def _age_days(as_of: str, when: str | None) -> int | None:
    if not when:
        return None
    try:
        return (date.fromisoformat(as_of) - date.fromisoformat(when[:10])).days
    except ValueError:
        return None


def _freshness(as_of: str, when: str | None, window_days: int | None) -> str:
    """Per-component freshness. A component with no window is an identity fact, not a dated one.

    The window is the interval ending at `as_of`, so a date in the future falls outside it exactly
    as an ancient one does. A negative age is `stale`, never `current`: `age <= window_days` alone
    would let a mistyped or planned 2099 date assert that a condition is true today, which is the
    carried-forward-good-state failure the freshness language exists to prevent. Evidence loaders
    bound their own queries at `as_of` as well; this is the floor under them, not the only guard.
    """
    if window_days is None:
        return "not_applicable"
    if not when:
        return "undated"
    age = _age_days(as_of, when)
    if age is None:
        return "undated"
    return "current" if 0 <= age <= window_days else "stale"


def _window_for(definition: dict) -> int | None:
    """The dated window this requirement is judged against, keyed by the definition's own key."""
    policy = json.loads(definition["freshness_policy_json"] or "{}")
    entry = policy.get(definition["key"]) or {}
    return entry.get("window_days")


def _component(
    *, key, state, freshness="not_applicable", assessed_through=None,
    evidence=None, provenance=None, reason=None, missing=None,
) -> dict:
    return {
        "key": key,
        "state": state,
        "freshness": freshness,
        "assessed_through": assessed_through,
        "evidence": evidence or [],
        "provenance": provenance,
        "reason": reason,
        "missing": missing or [],
    }


# §5.3/§8.3 — where each evidence kind is actually edited, so a component's evidence opens the
# native record rather than naming it. The shape matches the app-wide `openWorkspaceTarget`
# contract, and the map is deliberately explicit rather than derived from the type name: three of
# these kinds are not records at all, and guessing a route for them would send an operator to a
# tab that cannot show what they clicked.
#
# `(tab, subview)` — a `None` subview means the tab has one view. A kind absent from this map ships
# `native_target: null`, and the view renders plain text: `account_field`/`program_field` name a
# column on a record the pillar already identifies, and `source_reference` is provenance for
# another record rather than a record with a home of its own.
_EVIDENCE_TARGET = {
    "person": ("people", "map"),
    "stakeholder_role": ("people", "map"),
    "champion_candidate": ("people", "champions"),
    "advocacy_event": ("people", "champions"),
    "metric_definition": ("evidence", None),
    "metric_observation": ("evidence", None),
    "value_target": ("evidence", None),
    "value_story": ("evidence", None),
    "expansion_opportunity": ("commercial", "pipeline"),
    "funding_pool": ("commercial", "funding"),
    "task": ("ledger", None), "commitment": ("ledger", None),
    "risk": ("ledger", None), "issue": ("ledger", None),
    "milestone": ("ledger", None), "interaction": ("ledger", None),
    "decision": ("ledger", None),
    "document": ("outputs", None),
}


def _ev_target(kind: str, id_: str) -> dict | None:
    route = _EVIDENCE_TARGET.get(kind)
    if not route:
        return None
    tab, subview = route
    return {"tab": tab, "subview": subview, "record_type": kind, "record_id": id_}


def _ev(kind: str, id_: str, label: str, provenance: str = "operator_recorded") -> dict:
    return {"type": kind, "id": id_, "label": label, "provenance": provenance,
            "native_target": _ev_target(kind, id_)}


def _plural(count: int, singular: str, plural: str | None = None) -> str:
    """Counts appear in operator-facing sentences; "1 record(s)" reads as generated text."""
    return f"{count} {singular if count == 1 else (plural or singular + 's')}"


# --- operator exceptions (§3.2, delegated to ACCOUNT-PATH-SPEC.md §13.2) --------------------------

# `not_applicable` first: it removes the question, so it beats a waiver of the same question no
# matter which scope each was decided in. Scope specificity only breaks ties within one kind.
def _exception_rank(row: dict) -> tuple:
    return (0 if row["kind"] == "not_applicable" else 1, 0 if row["program_id"] else 1, row["id"])


def _live_exceptions(conn, account_id: str, program_id: str | None,
                     as_of: str) -> dict[str, dict]:
    """Live exceptions for this scope, keyed by requirement key.

    An account-wide decision (`program_id IS NULL`) applies in every program scope; a
    program-scoped one never reaches another program, and never reaches account scope — an
    operator who excused a condition on one program has not excused it on the account.

    A lapsed waiver simply stops applying. It is not revoked and it stays in the history, but an
    expiry that kept suppressing after its date would be a permanent gap wearing a temporary label.
    """
    rows = conn.execute(
        "SELECT * FROM readiness_exceptions "
        "WHERE account_id = ? AND archived = 0 AND revoked_at IS NULL "
        "  AND (program_id IS NULL OR program_id = ?) "
        "ORDER BY decided_on, id",
        (account_id, program_id),
    ).fetchall()
    live: dict[str, dict] = {}
    for row in rows:
        row = dict(row)
        if row["expires_on"] and row["expires_on"] < as_of:
            continue
        key = row["requirement_key"]
        held = live.get(key)
        if held is None or _exception_rank(row) < _exception_rank(held):
            live[key] = row
    return live


def _exception_public(row: dict) -> dict:
    return {
        "exception_id": row["id"],
        "kind": row["kind"],
        "reason": row["reason"],
        "actor_id": row["actor_id"],
        "decided_on": row["decided_on"],
        "expires_on": row["expires_on"],
        "scope": "program" if row["program_id"] else "account",
        "program_id": row["program_id"],
    }


def _suppressed_component(definition: dict, exception: dict) -> dict:
    """A requirement an operator has marked not applicable.

    It carries no evidence and asks for nothing. It is reported rather than dropped, because a
    condition that vanished from the list would be indistinguishable from one nobody thought of.
    """
    component = _component(
        key=definition["key"], state="not_applicable",
        reason=(f"Marked not applicable on {exception['decided_on']}: {exception['reason']}"),
    )
    component["applicability_override"] = _exception_public(exception)
    return component


# --- shared evidence readers ---------------------------------------------------------------------
# Each is cached per evaluation so six evaluators do not re-run the same query.

def _scope_programs(ctx: _Ctx) -> list[str]:
    """Program ids in scope. A supplied program narrows to exactly one; otherwise every live
    program on the account (used only by account-scoped requirements)."""
    if ctx.program_id:
        return [ctx.program_id]
    rows = ctx.conn.execute(
        "SELECT id FROM programs WHERE account_id=? AND archived=0", (ctx.account_id,)
    ).fetchall()
    return [r["id"] for r in rows]


def _engaged_people(ctx: _Ctx, *, include_account_level: bool = False) -> dict[str, dict]:
    """Non-placeholder client people with a meaningful accepted touch, newest touch per person.

    Program scope means `interactions.program_id = ?` strictly. An interaction with a null
    program is an account-level touch (D-09); it is admitted only when the requirement definition
    explicitly opts in, so a program pillar cannot quietly absorb account-wide evidence.
    """
    cache_key = ("engaged", include_account_level)

    def load():
        # `occurred_on <= as_of`: readiness answers "is this true now", and a meeting that has not
        # happened yet is a plan, not evidence. Without the bound a future-dated interaction would
        # both create the engagement and date it as the newest touch.
        where = ["i.account_id = ?", "i.archived = 0", "i.meaningful_touch = 1",
                 "i.occurred_on <= ?",
                 "p.affiliation = 'client'", "p.is_placeholder = 0", "p.archived = 0"]
        params: list = [ctx.account_id, ctx.as_of]
        if ctx.program_id:
            if include_account_level:
                where.append("(i.program_id = ? OR i.program_id IS NULL)")
            else:
                where.append("i.program_id = ?")
            params.append(ctx.program_id)
        rows = ctx.conn.execute(
            "SELECT ip.person_id, p.name, MAX(i.occurred_on) AS last_touch, "
            "       MAX(i.source_reference_id IS NOT NULL) AS has_source, "
            "       COUNT(*) AS touches "
            "FROM interactions i "
            "JOIN interaction_participants ip ON ip.interaction_id = i.id "
            "JOIN persons p ON p.id = ip.person_id "
            f"WHERE {' AND '.join(where)} GROUP BY ip.person_id, p.name",
            tuple(params),
        ).fetchall()
        return {
            r["person_id"]: {
                "person_id": r["person_id"], "name": r["name"], "last_touch": r["last_touch"],
                "provenance": "confirmed_source" if r["has_source"] else "operator_recorded",
                "touches": r["touches"],
            }
            for r in rows
        }

    return ctx.cached(cache_key, load)


def _roles(ctx: _Ctx) -> list[dict]:
    """Stakeholder roles in scope, with the layer left RAW so a defaulted layer stays visible."""

    def load():
        programs = _scope_programs(ctx)
        if not programs:
            return []
        placeholders = ",".join("?" * len(programs))
        rows = ctx.conn.execute(
            "SELECT sr.*, p.name AS person_name, p.is_placeholder, pr.name AS program_name "
            "FROM stakeholder_roles sr "
            "JOIN persons p ON p.id = sr.person_id "
            "JOIN programs pr ON pr.id = sr.program_id "
            f"WHERE sr.program_id IN ({placeholders}) AND sr.archived = 0 "
            "  AND p.archived = 0 AND p.affiliation = 'client'",
            tuple(programs),
        ).fetchall()
        out = []
        for r in rows:
            r = dict(r)
            # The distinction the whole breadth pillar rests on: was this layer assessed, or is it
            # the role's default standing in for an assessment nobody made?
            r["layer_explicit"] = r["layer"] is not None
            r["layer_resolved"] = people_core.resolved_layer(r)
            out.append(r)
        return out

    return ctx.cached("roles", load)


def _program_advocacy(ctx: _Ctx) -> dict[str, list[dict]]:
    """Champion-validating advocacy, resolved PER PROGRAM.

    `people_core.has_champion_evidence` deliberately ignores program, because a person card is
    account-wide. Readiness is not: §11.2 requires that contacts from another program do not
    satisfy the selected program, so advocacy with a different (or null) program does not
    validate a champion here.
    """

    def load():
        programs = _scope_programs(ctx)
        if not programs:
            return {}
        placeholders = ",".join("?" * len(programs))
        kinds = ",".join("?" * len(_CHAMPION_EVIDENCE_KINDS))
        # Bounded at `as_of` for the same reason interactions are: a scheduled advocacy event is a
        # commitment to validate a champion, not a validation of one.
        rows = ctx.conn.execute(
            "SELECT * FROM advocacy_events "
            f"WHERE archived = 0 AND kind IN ({kinds}) AND program_id IN ({placeholders}) "
            "  AND occurred_on <= ? "
            "ORDER BY occurred_on DESC",
            (*_CHAMPION_EVIDENCE_KINDS, *programs, ctx.as_of),
        ).fetchall()
        by_person: dict[str, list[dict]] = {}
        for r in rows:
            by_person.setdefault(r["person_id"], []).append(dict(r))
        return by_person

    return ctx.cached("advocacy", load)


def _validated_champions(ctx: _Ctx, config: dict) -> list[dict]:
    """People holding a champion role in scope, split by whether program advocacy validates them."""

    def load():
        advocacy = _program_advocacy(ctx)
        window = config.get("advocacy_window_days")
        out = []
        for role in _roles(ctx):
            if role["role"] != "champion" or role["is_placeholder"]:
                continue
            events = advocacy.get(role["person_id"], [])
            if window is not None:
                events = [
                    e for e in events
                    if (age := _age_days(ctx.as_of, e["occurred_on"])) is not None and age <= window
                ]
            out.append({"role": role, "events": events, "validated": bool(events)})
        return out

    return ctx.cached(("champions", json.dumps(config, sort_keys=True)), load)


def _executives(ctx: _Ctx, config: dict) -> list[dict]:
    exec_layer = config.get("executive_layer", "executive")
    require_explicit = config.get("require_explicit_layer", False)
    out = []
    for role in _roles(ctx):
        if role["is_placeholder"]:
            continue
        if require_explicit and not role["layer_explicit"]:
            continue
        if role["layer_resolved"] == exec_layer:
            out.append(role)
    return out


def _budget_owner_candidates(ctx: _Ctx, config: dict) -> list[dict]:
    """Every accepted record that names a budget owner, kept separate so disagreement is visible.

    Three independent records can name a budget owner. §4.5 forbids silently picking one, so this
    returns them all and the evaluator reports `conflicted` when they disagree.
    """

    def load():
        authority_roles = tuple(config.get("authority_roles") or ["budget_owner"])
        found: list[dict] = []
        placeholders = ",".join("?" * len(authority_roles))
        for role in _roles(ctx):
            if role["role"] in authority_roles and not role["is_placeholder"]:
                found.append({
                    "person_id": role["person_id"], "person_name": role["person_name"],
                    "source_type": "stakeholder_role", "source_id": role["id"],
                    "label": (f"{role['person_name']} — {people_core.role_label(role['role'])} "
                              f"on {role['program_name']}"),
                    "provenance": "operator_recorded",
                })
        rows = ctx.conn.execute(
            "SELECT fp.id, fp.name, fp.status, p.id AS person_id, p.name AS person_name "
            "FROM funding_pools fp JOIN persons p ON p.id = fp.owner_person_id "
            "WHERE fp.account_id = ? AND fp.archived = 0 AND p.archived = 0 "
            "  AND p.is_placeholder = 0 AND fp.status != 'unavailable'",
            (ctx.account_id,),
        ).fetchall()
        for r in rows:
            found.append({
                "person_id": r["person_id"], "person_name": r["person_name"],
                "source_type": "funding_pool", "source_id": r["id"],
                "label": f"{r['person_name']} owns funding pool “{r['name']}” ({r['status']})",
                "provenance": "operator_recorded",
            })
        rows = ctx.conn.execute(
            "SELECT eo.id, eo.name, p.id AS person_id, p.name AS person_name "
            "FROM expansion_opportunities eo JOIN persons p ON p.id = eo.budget_owner_person_id "
            "WHERE eo.account_id = ? AND eo.archived = 0 AND eo.status = 'open' "
            "  AND p.archived = 0 AND p.is_placeholder = 0",
            (ctx.account_id,),
        ).fetchall()
        for r in rows:
            found.append({
                "person_id": r["person_id"], "person_name": r["person_name"],
                "source_type": "expansion_opportunity", "source_id": r["id"],
                "label": f"{r['person_name']} is budget owner on “{r['name']}”",
                "provenance": "operator_recorded",
            })
        return found

    return ctx.cached(("budget", json.dumps(config, sort_keys=True)), load)


def _locked_baseline(ctx: _Ctx) -> dict | None:
    """The only baseline that counts: one explicitly locked by an adoption campaign target.

    §4.4 forbids inferring a baseline from date order, and no typed baseline relation exists on
    `metric_observations` yet, so an account with observations but no locked baseline reports the
    missing lock rather than guessing which observation was "before".
    """

    def load():
        where = ["act.archived = 0", "ac.archived = 0", "act.baseline_observation_id IS NOT NULL",
                 "act.baseline_locked_on IS NOT NULL", "mo.archived = 0", "ac.account_id = ?"]
        params: list = [ctx.account_id]
        if ctx.program_id:
            where.append("ac.program_id = ?")
            params.append(ctx.program_id)
        row = ctx.conn.execute(
            "SELECT act.id AS target_id, act.baseline_locked_on, ac.name AS campaign_name, "
            "       ac.program_id AS campaign_program_id, mo.* "
            "FROM adoption_campaign_targets act "
            "JOIN adoption_campaigns ac ON ac.id = act.campaign_id "
            "JOIN metric_observations mo ON mo.id = act.baseline_observation_id "
            f"WHERE {' AND '.join(where)} ORDER BY act.baseline_locked_on DESC LIMIT 1",
            tuple(params),
        ).fetchone()
        return dict(row) if row else None

    return ctx.cached("baseline", load)


def _open_opportunities(ctx: _Ctx) -> list[dict]:
    def load():
        rows = ctx.conn.execute(
            "SELECT * FROM expansion_opportunities "
            "WHERE account_id = ? AND archived = 0 AND status = 'open' ORDER BY created_at",
            (ctx.account_id,),
        ).fetchall()
        return [dict(r) for r in rows]

    return ctx.cached("opportunities", load)


def _touch_component(ctx, definition, component_key, people, window, *, label_noun,
                     include_account_level=False):
    """Shared engagement component: identity is assumed, recency is what is being judged."""
    if not people:
        return _component(
            key=component_key, state="unknown",
            reason=f"No {label_noun} is identified, so engagement cannot be assessed.",
            missing=[f"Identify {'an' if label_noun[0] in 'aeiou' else 'a'} {label_noun}"],
        )
    engaged = _engaged_people(ctx, include_account_level=include_account_level)
    best = None
    for person in people:
        row = engaged.get(person["person_id"])
        if row and (best is None or (row["last_touch"] or "") > (best["last_touch"] or "")):
            best = row
    if best is None:
        names = ", ".join(sorted({p["person_name"] for p in people}))
        return _component(
            key=component_key, state="thin", freshness="undated",
            reason=f"{names} is recorded as {label_noun} but has no meaningful touch in scope.",
            missing=[f"Record a meaningful interaction with the {label_noun}"],
            evidence=[_ev("person", p["person_id"], p["person_name"]) for p in people],
        )
    fresh = _freshness(ctx.as_of, best["last_touch"], window)
    met = fresh == "current"
    return _component(
        key=component_key,
        state="met" if met else "thin",
        freshness=fresh,
        assessed_through=best["last_touch"],
        provenance=best["provenance"],
        reason=(f"{best['name']} was last engaged on {best['last_touch']}."
                if met else
                f"{best['name']} was last engaged on {best['last_touch']}, outside the "
                f"{window}-day window."),
        missing=[] if met else [f"Record a current meaningful touch with the {label_noun}"],
        evidence=[_ev("person", best["person_id"], best["name"], best["provenance"])],
    )


# --- requirement evaluators (§4) -----------------------------------------------------------------

def _eval_breadth_contacts(ctx: _Ctx, definition: dict) -> dict:
    config = json.loads(definition["evaluator_config_json"])
    window = config.get("touch_window_days")
    minimum = config.get("min_contacts", 3)
    engaged = _engaged_people(ctx)
    current = {
        pid: row for pid, row in engaged.items()
        if _freshness(ctx.as_of, row["last_touch"], window) == "current"
    }
    newest = max((r["last_touch"] or "" for r in engaged.values()), default=None) or None
    if not engaged:
        return _component(
            key="breadth_engaged_contacts", state="unknown",
            reason="No meaningful interactions with client people are recorded in this scope.",
            missing=["Record interactions with the client contacts"],
        )
    evidence = [
        _ev("person", r["person_id"], f"{r['name']} — last touch {r['last_touch']}", r["provenance"])
        for r in sorted(engaged.values(), key=lambda r: r["last_touch"] or "", reverse=True)
    ]
    if len(current) >= minimum:
        return _component(
            key="breadth_engaged_contacts", state="met", freshness="current", assessed_through=newest,
            evidence=evidence, provenance="operator_recorded",
            reason=f"{len(current)} client people have a meaningful touch inside {window} days.",
        )
    stale_only = len(engaged) >= minimum and len(current) < minimum
    return _component(
        key="breadth_engaged_contacts", state="thin",
        freshness="stale" if stale_only else _freshness(ctx.as_of, newest, window),
        assessed_through=newest, evidence=evidence, provenance="operator_recorded",
        reason=(f"{len(engaged)} contacts are recorded but only {len(current)} have a touch "
                f"inside {window} days." if stale_only else
                f"Only {len(current)} of the {minimum} required contacts are currently engaged."),
        missing=[f"Engage at least {minimum} client contacts inside the touch window"],
    )


def _eval_breadth_layers(ctx: _Ctx, definition: dict) -> dict:
    config = json.loads(definition["evaluator_config_json"])
    minimum = config.get("min_layers", 2)
    require_explicit = config.get("require_explicit_layer", True)
    window = _window_for(definition)
    engaged = _engaged_people(ctx)
    roles = [r for r in _roles(ctx) if r["person_id"] in engaged and not r["is_placeholder"]]
    if not roles:
        return _component(
            key="breadth_layer_spread", state="unknown",
            reason="No engaged contact holds a stakeholder role in this scope.",
            missing=["Record stakeholder roles for the engaged contacts"],
        )
    explicit = [r for r in roles if r["layer_explicit"]]
    defaulted = [r for r in roles if not r["layer_explicit"]]
    counted = explicit if require_explicit else roles
    layers = sorted({r["layer_resolved"] for r in counted})
    evidence = [
        _ev("stakeholder_role", r["id"],
            f"{r['person_name']} — {people_core.LAYER_LABELS.get(r['layer_resolved'], r['layer_resolved'])}"
            + ("" if r["layer_explicit"] else " (defaulted from role, not assessed)"),
            "operator_recorded" if r["layer_explicit"] else "unsupported")
        for r in roles
    ]
    if len(layers) >= minimum:
        return _component(
            key="breadth_layer_spread", state="met", freshness=_freshness(ctx.as_of, None, window),
            evidence=evidence, provenance="operator_recorded",
            reason=("Engaged contacts span "
                    + ", ".join(people_core.LAYER_LABELS.get(l, l) for l in layers) + "."),
        )
    # The false positive this component exists to prevent: enough people, one layer — or enough
    # apparent layers that were never actually assessed.
    if require_explicit and defaulted and len({r["layer_resolved"] for r in roles}) >= minimum:
        return _component(
            key="breadth_layer_spread", state="thin", evidence=evidence, provenance="unsupported",
            reason=(f"{len(defaulted)} engaged contacts have no assessed stakeholder layer; the "
                    "spread would rest on role defaults rather than evidence."),
            missing=["Assess the stakeholder layer for the engaged contacts"],
        )
    named = ", ".join(people_core.LAYER_LABELS.get(l, l) for l in layers) or "no assessed layer"
    return _component(
        key="breadth_layer_spread", state="thin", evidence=evidence, provenance="operator_recorded",
        reason=f"Engaged contacts sit in {named}; breadth requires at least {minimum} layers.",
        missing=[f"Engage a contact in a different stakeholder layer"],
    )


def _eval_champion_primary(ctx: _Ctx, definition: dict) -> dict:
    config = json.loads(definition["evaluator_config_json"])
    window = config.get("touch_window_days")
    champions = _validated_champions(ctx, config)
    if not champions:
        return _component(
            key="champion_primary_validated", state="unknown",
            reason="No champion is identified in this scope.",
            missing=["Identify a champion"],
        )
    validated = [c for c in champions if c["validated"]]
    if not validated:
        names = ", ".join(sorted({c["role"]["person_name"] for c in champions}))
        return _component(
            key="champion_primary_validated", state="thin",
            evidence=[_ev("stakeholder_role", c["role"]["id"], c["role"]["person_name"])
                      for c in champions],
            provenance="unsupported",
            reason=(f"{names} is tagged champion but has no advocacy evidence in this program, "
                    "so the relationship reads as coach."),
            missing=["Record an advocacy event for the tagged champion in this program"],
        )
    engaged = _engaged_people(ctx)
    best, best_touch = None, None
    for c in validated:
        row = engaged.get(c["role"]["person_id"])
        touch = row["last_touch"] if row else None
        if best is None or (touch or "") > (best_touch or ""):
            best, best_touch = c, touch
    fresh = _freshness(ctx.as_of, best_touch, window)
    evidence = [_ev("stakeholder_role", best["role"]["id"], best["role"]["person_name"])]
    evidence += [
        _ev("advocacy_event", e["id"], f"{e['kind'].replace('_', ' ')} on {e['occurred_on']}",
            "confirmed_source" if e["source_reference_id"] else "operator_recorded")
        for e in best["events"][:3]
    ]
    if fresh == "current":
        return _component(
            key="champion_primary_validated", state="met", freshness=fresh, assessed_through=best_touch,
            evidence=evidence, provenance="operator_recorded",
            reason=(f"{best['role']['person_name']} is validated by advocacy in this program and "
                    f"was last engaged on {best_touch}."),
        )
    return _component(
        key="champion_primary_validated", state="thin", freshness=fresh, assessed_through=best_touch,
        evidence=evidence, provenance="operator_recorded",
        reason=(f"{best['role']['person_name']} is a validated champion but was last engaged "
                f"{'on ' + best_touch if best_touch else 'never'}."),
        missing=["Record a current meaningful touch with the champion"],
    )


def _eval_champion_second_thread(ctx: _Ctx, definition: dict) -> dict:
    config = json.loads(definition["evaluator_config_json"])
    window = config.get("touch_window_days")
    allowed_roles = set(config.get("allowed_roles") or [])
    allowed_stages = set(config.get("allowed_candidate_stages") or [])
    primary_ids = {c["role"]["person_id"] for c in _validated_champions(ctx, config) if c["validated"]}
    engaged = _engaged_people(ctx)

    candidates: list[dict] = []
    for role in _roles(ctx):
        if role["is_placeholder"] or role["person_id"] in primary_ids:
            continue
        if role["role"] in allowed_roles:
            candidates.append({
                "person_id": role["person_id"], "person_name": role["person_name"],
                "why": role["role"], "evidence": _ev("stakeholder_role", role["id"],
                                                     f"{role['person_name']} — {people_core.role_label(role['role'])}"),
            })
    programs = _scope_programs(ctx)
    if programs and allowed_stages:
        placeholders = ",".join("?" * len(programs))
        stages = ",".join("?" * len(allowed_stages))
        rows = ctx.conn.execute(
            "SELECT cc.*, p.name AS person_name FROM champion_candidates cc "
            "JOIN persons p ON p.id = cc.person_id "
            f"WHERE cc.archived = 0 AND cc.program_id IN ({placeholders}) "
            f"  AND cc.stage IN ({stages}) AND p.archived = 0 AND p.is_placeholder = 0",
            (*programs, *sorted(allowed_stages)),
        ).fetchall()
        for r in rows:
            if r["person_id"] in primary_ids:
                continue
            candidates.append({
                "person_id": r["person_id"], "person_name": r["person_name"],
                "why": f"champion candidate at {r['stage']}",
                "evidence": _ev("champion_candidate", r["id"],
                                f"{r['person_name']} — candidate at {r['stage']}"),
            })

    if not candidates:
        return _component(
            key="champion_second_thread", state="unknown",
            reason=("No second relationship thread exists: the program depends on a single "
                    "relationship."),
            missing=["Develop a second champion, sponsor, or budget owner relationship"],
        )
    best, best_touch = None, None
    for c in candidates:
        row = engaged.get(c["person_id"])
        touch = row["last_touch"] if row else None
        if best is None or (touch or "") > (best_touch or ""):
            best, best_touch = c, touch
    fresh = _freshness(ctx.as_of, best_touch, window)
    evidence = [c["evidence"] for c in candidates[:4]]
    if fresh == "current":
        return _component(
            key="champion_second_thread", state="met", freshness=fresh, assessed_through=best_touch,
            evidence=evidence, provenance="operator_recorded",
            reason=f"{best['person_name']} ({best['why']}) was last engaged on {best_touch}.",
        )
    return _component(
        key="champion_second_thread", state="thin", freshness=fresh, assessed_through=best_touch,
        evidence=evidence, provenance="operator_recorded",
        reason=(f"{best['person_name']} ({best['why']}) exists as a second thread but was last "
                f"engaged {'on ' + best_touch if best_touch else 'never'}."),
        missing=["Record a current meaningful touch with the second thread"],
    )


def _eval_exec_identified(ctx: _Ctx, definition: dict) -> dict:
    config = json.loads(definition["evaluator_config_json"])
    execs = _executives(ctx, config)
    if not execs:
        return _component(
            key="exec_identified", state="unknown",
            reason="No executive-layer stakeholder is identified in this scope.",
            missing=["Identify the executive sponsor"],
        )
    return _component(
        key="exec_identified", state="met", provenance="operator_recorded",
        evidence=[_ev("stakeholder_role", r["id"],
                      f"{r['person_name']} — {people_core.role_label(r['role'])}")
                  for r in execs],
        reason=", ".join(sorted({r["person_name"] for r in execs})) + " is at the executive layer.",
    )


def _eval_exec_engaged(ctx: _Ctx, definition: dict) -> dict:
    config = json.loads(definition["evaluator_config_json"])
    execs = _executives(ctx, config)
    people = [{"person_id": r["person_id"], "person_name": r["person_name"]} for r in execs]
    return _touch_component(
        ctx, definition, "exec_engaged", people, config.get("touch_window_days"),
        label_noun="executive sponsor",
        include_account_level=config.get("include_account_level_touches", False),
    )


def _eval_exec_value_link(ctx: _Ctx, definition: dict) -> dict:
    config = json.loads(definition["evaluator_config_json"])
    # §4.3: free-text similarity between persons.metric_judged_on and metric_definitions.owner is
    # not a link. Until RR-3 delivers the typed relation there is nothing that could satisfy this,
    # and the honest answer is to say so rather than to approximate one.
    if not config.get("relation_available", False):
        execs = _executives(ctx, config)
        noted = [r for r in execs if (r.get("cares_about") or r.get("value_for_them"))]
        return _component(
            key="exec_value_link", state="unknown", provenance="unsupported",
            evidence=[_ev("stakeholder_role", r["id"],
                          f"{r['person_name']} — value notes recorded", "unsupported")
                      for r in noted],
            reason=("No typed link between an executive and the metric they own exists yet, so "
                    "value alignment cannot be evidenced (RR-3)."),
            missing=["Link the executive to the metric or value target they sponsor"],
        )
    return _component(key="exec_value_link", state="unknown",
                      reason="Typed stakeholder-to-metric evidence is not yet implemented.")


def _eval_value_baseline(ctx: _Ctx, definition: dict) -> dict:
    baseline = _locked_baseline(ctx)
    if baseline:
        return _component(
            key="value_baseline_locked", state="met", provenance="confirmed_source",
            assessed_through=baseline["baseline_locked_on"],
            evidence=[_ev("metric_observation", baseline["id"],
                          f"Baseline {baseline['period_label'] or ''} locked on "
                          f"{baseline['baseline_locked_on']} for “{baseline['campaign_name']}”",
                          "confirmed_source")],
            reason=(f"A baseline observation is locked on {baseline['baseline_locked_on']} for "
                    f"“{baseline['campaign_name']}”."),
        )
    # A negotiated target is not a baseline (§4.4) — say so explicitly when one exists, because
    # "we agreed a target" is exactly the record an operator would otherwise expect to count.
    targets = ctx.conn.execute(
        "SELECT id, target_value, unit FROM value_targets "
        "WHERE account_id = ? AND archived = 0 AND status = 'active' LIMIT 3",
        (ctx.account_id,),
    ).fetchall()
    if targets:
        return _component(
            key="value_baseline_locked", state="unknown", provenance="unsupported",
            evidence=[_ev("value_target", t["id"],
                          f"Target {t['target_value']}{(' ' + t['unit']) if t['unit'] else ''}",
                          "unsupported")
                      for t in targets],
            reason=("Value targets are agreed but no baseline observation is locked; a negotiated "
                    "target bar is not a pre-deployment measurement."),
            missing=["Lock a baseline observation"],
        )
    return _component(
        key="value_baseline_locked", state="unknown",
        reason="No locked baseline observation exists in this scope.",
        missing=["Lock a baseline observation before measuring impact"],
    )


def _eval_value_comparison(ctx: _Ctx, definition: dict) -> dict:
    config = json.loads(definition["evaluator_config_json"])
    window = config.get("comparison_window_days")
    baseline = _locked_baseline(ctx)
    if not baseline:
        return _component(
            key="value_comparison_observation", state="unknown",
            reason="Without a locked baseline there is nothing to compare an after-measurement to.",
            missing=["Lock a baseline observation first"],
        )
    # `metric_observations` has no account column, so candidates are constrained to this account's
    # programs. Without that, another account's observation on the same shared metric definition
    # could be read as this account's after-measurement.
    programs = _scope_programs(ctx)
    if not programs:
        return _component(
            key="value_comparison_observation", state="unknown",
            reason="No live program in scope to hold a comparable observation.",
            missing=["Record an after-measurement against the baseline's program"],
        )
    placeholders = ",".join("?" * len(programs))
    rows = ctx.conn.execute(
        "SELECT * FROM metric_observations "
        f"WHERE definition_id = ? AND archived = 0 AND id != ? AND program_id IN ({placeholders}) "
        "ORDER BY COALESCE(current_through, period_label) DESC",
        (baseline["definition_id"], baseline["id"], *programs),
    ).fetchall()
    later, mismatched = [], []
    for r in rows:
        r = dict(r)
        base_when = baseline["current_through"] or baseline["period_label"] or ""
        when = r["current_through"] or r["period_label"] or ""
        if when <= base_when:
            continue
        reasons = []
        if config.get("require_same_definition_version", True) and \
                r["definition_version"] != baseline["definition_version"]:
            reasons.append(f"metric definition version {r['definition_version']} differs from the "
                           f"baseline's {baseline['definition_version']}")
        if config.get("require_same_cohort", True) and r["cohort_label"] != baseline["cohort_label"]:
            reasons.append("cohort differs from the baseline")
        if config.get("require_same_unit", True) and r["unit"] != baseline["unit"]:
            reasons.append("unit differs from the baseline")
        if r["program_id"] != baseline["program_id"]:
            reasons.append("program differs from the baseline")
        (mismatched if reasons else later).append({"row": r, "reasons": reasons})

    if later:
        best = later[0]["row"]
        when = best["current_through"] or best["period_label"]
        fresh = _freshness(ctx.as_of, when, window)
        evidence = [_ev("metric_observation", best["id"],
                        f"{best['period_label'] or 'observation'} = {best['value']}"
                        f"{(' ' + best['unit']) if best['unit'] else ''}", "confirmed_source")]
        if fresh == "current":
            return _component(
                key="value_comparison_observation", state="met", freshness=fresh, assessed_through=when,
                evidence=evidence, provenance="confirmed_source",
                reason=(f"A comparable observation on the same definition, version, cohort, and "
                        f"unit is current through {when}."),
            )
        return _component(
            key="value_comparison_observation", state="thin", freshness=fresh, assessed_through=when,
            evidence=evidence, provenance="confirmed_source",
            reason=f"The most recent comparable observation is current only through {when}.",
            missing=["Record a current after-measurement"],
        )
    if mismatched:
        first = mismatched[0]
        return _component(
            key="value_comparison_observation", state="thin", provenance="unsupported",
            evidence=[_ev("metric_observation", m["row"]["id"],
                          f"{m['row']['period_label'] or 'observation'} — not comparable",
                          "unsupported") for m in mismatched[:3]],
            reason=("Later observations exist but are not comparable: "
                    + "; ".join(first["reasons"]) + "."),
            missing=["Record an after-measurement on the same basis as the baseline"],
        )
    return _component(
        key="value_comparison_observation", state="unknown",
        reason="No observation later than the locked baseline exists.",
        missing=["Record an after-measurement"],
    )


def _eval_budget_authority(ctx: _Ctx, definition: dict) -> dict:
    config = json.loads(definition["evaluator_config_json"])
    found = _budget_owner_candidates(ctx, config)
    if not found:
        return _component(
            key="budget_authority_evidence", state="unknown",
            reason="No accepted record names a person with budget authority.",
            missing=["Record who holds the budget"],
        )
    people = {f["person_id"] for f in found}
    evidence = [_ev(f["source_type"], f["source_id"], f["label"], f["provenance"]) for f in found]
    if len(people) > 1:
        names = ", ".join(sorted({f["person_name"] for f in found}))
        return _component(
            key="budget_authority_evidence", state="conflicted", evidence=evidence,
            provenance="operator_recorded",
            reason=(f"Accepted records disagree on who holds the budget: {names}. The conflict is "
                    "reported rather than resolved."),
            missing=["Reconcile the conflicting budget-owner records"],
        )
    only = found[0]
    return _component(
        key="budget_authority_evidence", state="met", evidence=evidence, provenance="operator_recorded",
        reason=(f"{only['person_name']} is named as budget owner across "
                f"{_plural(len(found), 'record')}."),
    )


def _eval_budget_engagement(ctx: _Ctx, definition: dict) -> dict:
    config = json.loads(definition["evaluator_config_json"])
    authority_config = {"authority_roles": ["budget_owner", "financial_gatekeeper"]}
    found = _budget_owner_candidates(ctx, authority_config)
    seen, people = set(), []
    for f in found:
        if f["person_id"] not in seen:
            seen.add(f["person_id"])
            people.append({"person_id": f["person_id"], "person_name": f["person_name"]})
    return _touch_component(ctx, definition, "budget_owner_engagement", people,
                            config.get("touch_window_days"), label_noun="budget owner")


def _eval_expansion_open(ctx: _Ctx, definition: dict) -> dict:
    opportunities = _open_opportunities(ctx)
    if not opportunities:
        return _component(
            key="expansion_opportunity_open", state="unknown",
            reason="No open expansion opportunity exists on this account.",
            missing=["Open an expansion opportunity"],
        )
    return _component(
        key="expansion_opportunity_open", state="met", provenance="operator_recorded",
        evidence=[_ev("expansion_opportunity", o["id"], o["name"]) for o in opportunities],
        reason=(f"{_plural(len(opportunities), 'open expansion opportunity', 'open expansion '
                        'opportunities')} on this account."),
    )


def _eval_expansion_ownership(ctx: _Ctx, definition: dict) -> dict:
    config = json.loads(definition["evaluator_config_json"])
    opportunities = _open_opportunities(ctx)
    if not opportunities:
        return _component(key="expansion_client_ownership", state="unknown",
                          reason="No open expansion opportunity to co-own.",
                          missing=["Open an expansion opportunity"])
    sponsored = []
    for o in opportunities:
        if not o["sponsor_person_id"]:
            continue
        person = ctx.conn.execute(
            "SELECT id, name, is_placeholder, affiliation FROM persons WHERE id=? AND archived=0",
            (o["sponsor_person_id"],),
        ).fetchone()
        if person and not person["is_placeholder"] and person["affiliation"] == "client":
            sponsored.append((o, dict(person)))
    if not sponsored:
        return _component(
            key="expansion_client_ownership", state="thin", provenance="unsupported",
            evidence=[_ev("expansion_opportunity", o["id"], f"{o['name']} — no client sponsor",
                          "unsupported") for o in opportunities],
            reason=("No open opportunity names a non-placeholder client sponsor, so the expansion "
                    "is an internal hypothesis."),
            missing=["Name the client sponsor for the expansion"],
        )
    # A sponsor name is not acknowledgement. §4.6 holds full mutuality back until the RR-3 typed
    # relation exists; a source interaction is the strongest thing available and still only thin.
    acknowledged = [
        (o, p) for o, p in sponsored
        if config.get("accept_source_interaction", True) and o["source_interaction_id"]
    ]
    evidence = [_ev("expansion_opportunity", o["id"], f"{o['name']} — sponsored by {p['name']}")
                for o, p in sponsored]
    if acknowledged and config.get("relation_available", False):
        return _component(key="expansion_client_ownership", state="met", evidence=evidence,
                          provenance="confirmed_source",
                          reason="Client co-ownership is evidenced by a typed acknowledgement.")
    return _component(
        key="expansion_client_ownership", state="thin", provenance="operator_recorded", evidence=evidence,
        reason=(f"{sponsored[0][1]['name']} is named as client sponsor, but co-ownership is not "
                "evidenced by an accepted client acknowledgement (RR-3)."),
        missing=["Record accepted evidence of client acknowledgement"],
    )


def _eval_expansion_next_step(ctx: _Ctx, definition: dict) -> dict:
    opportunities = _open_opportunities(ctx)
    if not opportunities:
        return _component(key="expansion_dated_next_step", state="unknown",
                          reason="No open expansion opportunity.",
                          missing=["Open an expansion opportunity"])
    dated = [o for o in opportunities if o["decision_date"]]
    if dated:
        return _component(
            key="expansion_dated_next_step", state="met", provenance="operator_recorded",
            assessed_through=max(o["decision_date"] for o in dated),
            evidence=[_ev("expansion_opportunity", o["id"],
                          f"{o['name']} — decision {o['decision_date']}") for o in dated],
            reason="The expansion carries a dated decision point.",
        )
    undated_next = [o for o in opportunities if o["next_action"]]
    if undated_next:
        return _component(
            key="expansion_dated_next_step", state="thin", freshness="undated", provenance="operator_recorded",
            evidence=[_ev("expansion_opportunity", o["id"], f"{o['name']} — next action undated")
                      for o in undated_next],
            reason="A next action is recorded but carries no date, so the plan cannot be paced.",
            missing=["Date the next step"],
        )
    return _component(
        key="expansion_dated_next_step", state="thin", freshness="undated", provenance="unsupported",
        evidence=[_ev("expansion_opportunity", o["id"], o["name"], "unsupported")
                  for o in opportunities],
        reason="The expansion has neither a decision date nor a next action.",
        missing=["Record a dated next step"],
    )


def _eval_expansion_budget_state(ctx: _Ctx, definition: dict) -> dict:
    config = json.loads(definition["evaluator_config_json"])
    live = set(config.get("live_budget_states") or [])
    opportunities = _open_opportunities(ctx)
    if not opportunities:
        return _component(key="expansion_budget_state", state="unknown",
                          reason="No open expansion opportunity.",
                          missing=["Open an expansion opportunity"])
    in_state = [o for o in opportunities if o["budget_state"] in live]
    evidence = [_ev("expansion_opportunity", o["id"], f"{o['name']} — {o['budget_state'].replace('_', ' ')}")
                for o in opportunities]
    if in_state:
        return _component(
            key="expansion_budget_state", state="met", evidence=evidence, provenance="operator_recorded",
            reason=f"Budget state is {in_state[0]['budget_state']}.",
        )
    return _component(
        key="expansion_budget_state", state="thin", evidence=evidence, provenance="operator_recorded",
        reason=(f"Budget state is \u201c{opportunities[0]['budget_state'].replace('_', ' ')}\u201d, "
                "which indicates support "
                "rather than committed money."),
        missing=["Advance the expansion to a live budget state"],
    )


# --- generic definition-of-done evaluators (ACCOUNT-PATH-SPEC.md §15.4) ---------------------------
# The evaluators above answer one named readiness question each. These eight answer a *shape* of
# question, configured per definition. They are still allowlisted the same way — a definition row
# picks one and supplies its configuration; it cannot introduce behaviour — and they still read
# canonical records rather than any stored state.
#
# Every one of them fails closed. A configuration that names a field, record type, or child
# evaluator this code does not know returns `unknown` with the offending name in the reason,
# because a condition nobody can evaluate must not read as one that is satisfied.

def _plan_instances_for(ctx: _Ctx, definition: dict) -> list[dict]:
    """The scheduled instances of this requirement in scope. Empty is normal: a definition can be
    evaluated with no plan behind it, and the evaluators that need links say so themselves."""
    sql = ("SELECT * FROM readiness_plan_instances "
           "WHERE account_id = ? AND requirement_key = ? AND archived = 0")
    params: list = [ctx.account_id, definition["key"]]
    if ctx.program_id:
        sql += " AND (program_id = ? OR program_id IS NULL)"
        params.append(ctx.program_id)
    return [dict(r) for r in ctx.conn.execute(sql, tuple(params))]


def _live_evidence_links(ctx: _Ctx, instances: list[dict]) -> list[dict]:
    """Evidence an operator attached and has not withdrawn.

    Retracted, superseded, and archived links are excluded *here*, at read time, which is the whole
    reason §15.3 works without a rebuild: withdrawing support changes the next answer because the
    next answer never looked anywhere else.
    """
    if not instances:
        return []
    marks = ",".join("?" for _ in instances)
    return [dict(r) for r in ctx.conn.execute(
        f"SELECT * FROM readiness_requirement_evidence_links "
        f"WHERE plan_instance_id IN ({marks}) AND archived = 0 AND retracted_at IS NULL "
        f"ORDER BY created_at",
        tuple(i["id"] for i in instances),
    )]


def _linked_actions(ctx: _Ctx, instances: list[dict], relation: str = "advances") -> list[dict]:
    if not instances:
        return []
    marks = ",".join("?" for _ in instances)
    rows = ctx.conn.execute(
        f"SELECT * FROM readiness_requirement_action_links "
        f"WHERE plan_instance_id IN ({marks}) AND relation = ? AND archived = 0 "
        f"ORDER BY created_at",
        (*[i["id"] for i in instances], relation),
    ).fetchall()
    out = []
    for row in rows:
        row = dict(row)
        kind = "task" if row["task_id"] else "commitment"
        table = "tasks" if kind == "task" else "commitments"
        record = ctx.conn.execute(
            f"SELECT * FROM {table} WHERE id = ? AND archived = 0",
            (row["task_id"] or row["commitment_id"],),
        ).fetchone()
        if record is None:
            continue
        out.append({"kind": kind, "link": row, "record": dict(record)})
    return out


def _apply_evidence_links(ctx: _Ctx, definition: dict, component: dict,
                          instances: list[dict]) -> dict:
    """Fold attached evidence into a component that the canonical records already decided.

    Two separate jobs, and conflating them was the trap:

    - Every live link is **cited**, supporting or not, so an operator sees what was attached.
    - Only a *supporting* link — one whose kind the definition allows — can satisfy an
      `evidence_required` configuration. A context attachment is visible and inert (§15.3).

    A supporting link never upgrades a state on its own. If the records say the condition is thin,
    attaching a document does not make it met; the definition's evaluator is still the only thing
    that decides.
    """
    links = _live_evidence_links(ctx, instances)
    if links:
        component["evidence"] = list(component.get("evidence") or []) + [
            _ev(link["evidence_type"], link["evidence_id"],
                link["evidence_label"] + ("" if link["supporting"] else " (context only)"),
                provenance="operator_recorded" if link["supporting"] else "unsupported")
            for link in links
        ]
    config = json.loads(definition["evaluator_config_json"] or "{}")
    if not config.get("evidence_required"):
        return component
    supporting = [link for link in links if link["supporting"]]
    if supporting:
        return component
    if component["state"] == "met":
        component["state"] = "thin"
        component["reason"] = (
            f"{component['reason']} This requirement also asks for attached evidence, and none "
            "of an allowed kind is attached."
        ).strip()
    component["missing"] = list(component.get("missing") or []) + [
        "Attach supporting evidence of an allowed kind"
    ]
    return component


def _generic(ctx: _Ctx, definition: dict, fn) -> dict:
    instances = _plan_instances_for(ctx, definition)
    component = fn(ctx, definition, instances)
    return _apply_evidence_links(ctx, definition, component, instances)


def _unknown(definition: dict, reason: str) -> dict:
    return _component(key=definition["key"], state="unknown", reason=reason)


# --- field_present --------------------------------------------------------------------------------
# Column allowlists rather than reflection. Reading whatever column a configuration names would
# turn a requirement definition into an arbitrary query against the schema, including columns that
# exist for reasons nothing to do with readiness.
_FIELD_SCOPES = {
    # Contractual dates are deliberately absent: they live on `contract_versions`, which is a
    # versioned record, and reading "the" renewal date off an account would flatten that.
    "account": ("accounts", {
        "short_context", "incumbent_note", "delivery_status", "delivery_status_rationale",
        "delivery_status_change_condition", "commercial_status", "commercial_status_rationale",
        "commercial_status_change_condition",
    }),
    "program": ("programs", {
        "kickoff_date", "onboarded_at", "launch_definition", "success_criteria",
        "problem_statement", "in_scope_population", "out_of_scope_population",
        "expansion_hypothesis", "explicit_exclusions", "sponsor_person_id",
        "governance_steering", "governance_rhythm", "next_qbr_date",
    }),
}


def _eval_field_present(ctx: _Ctx, definition: dict, instances: list[dict]) -> dict:
    config = json.loads(definition["evaluator_config_json"] or "{}")
    scope = config.get("scope", "program")
    fields = list(config.get("fields") or [])
    if scope not in _FIELD_SCOPES:
        return _unknown(definition, f"Configured scope “{scope}” is not account or program.")
    if not fields:
        return _unknown(definition, "No fields are configured for this requirement.")
    table, allowed = _FIELD_SCOPES[scope]
    unknown_fields = [f for f in fields if f not in allowed]
    if unknown_fields:
        return _unknown(definition,
                        f"Configured field(s) not available for evaluation: "
                        f"{', '.join(sorted(unknown_fields))}.")

    if scope == "account":
        rows = [ctx.conn.execute("SELECT * FROM accounts WHERE id = ?",
                                 (ctx.account_id,)).fetchone()]
        labels = {ctx.account_id: "Account"}
    else:
        program_ids = _scope_programs(ctx)
        if not program_ids:
            return _component(key=definition["key"], state="unknown",
                              reason="No live program is in scope for this requirement.")
        marks = ",".join("?" for _ in program_ids)
        rows = ctx.conn.execute(f"SELECT * FROM programs WHERE id IN ({marks})",
                                tuple(program_ids)).fetchall()
        labels = {r["id"]: r["name"] for r in rows}

    window = _window_for(definition)
    dated_by = config.get("dated_by")
    if dated_by and dated_by not in allowed:
        return _unknown(definition, f"Configured dated_by field “{dated_by}” is not available.")

    missing, evidence, dates = [], [], []
    for row in rows:
        if row is None:
            continue
        row = dict(row)
        for field in fields:
            value = row.get(field)
            pretty = field.replace("_", " ")
            if value in (None, ""):
                # Named per record, not per field: "Record the kickoff date" is unactionable when
                # three programs are in scope and only one is missing it.
                missing.append(f"Record {pretty} on {labels.get(row['id'], row['id'])}")
            else:
                evidence.append(_ev(f"{scope}_field", f"{table}.{field}",
                                    f"{labels.get(row['id'], row['id'])} — {pretty}"))
        if dated_by:
            dates.append(row.get(dated_by))

    freshness = _freshness(ctx.as_of, min([d for d in dates if d], default=None), window)
    if missing:
        return _component(
            key=definition["key"], state="thin", freshness=freshness, evidence=evidence,
            provenance="operator_recorded" if evidence else None,
            reason=f"{_plural(len(missing), 'required field')} not recorded.", missing=missing,
        )
    return _component(
        key=definition["key"], state="met", freshness=freshness, evidence=evidence,
        provenance="operator_recorded",
        assessed_through=min([d for d in dates if d], default=None),
        reason=f"{_plural(len(fields), 'field')} recorded.",
    )


# --- role_present ---------------------------------------------------------------------------------

def _eval_role_present(ctx: _Ctx, definition: dict, instances: list[dict]) -> dict:
    config = json.loads(definition["evaluator_config_json"] or "{}")
    roles = [r for r in (config.get("roles") or [])]
    minimum = int(config.get("min_count", 1))
    require_assessment = bool(config.get("require_assessment", True))
    if not roles:
        return _unknown(definition, "No roles are configured for this requirement.")
    program_ids = _scope_programs(ctx)
    if not program_ids:
        return _component(key=definition["key"], state="unknown",
                          reason="No live program is in scope for this requirement.")
    marks = ",".join("?" for _ in program_ids)
    role_marks = ",".join("?" for _ in roles)
    rows = [dict(r) for r in ctx.conn.execute(
        f"SELECT sr.*, p.name AS person_name FROM stakeholder_roles sr "
        f"JOIN persons p ON p.id = sr.person_id "
        f"WHERE sr.program_id IN ({marks}) AND sr.role IN ({role_marks}) AND sr.archived = 0 "
        f"  AND p.archived = 0",
        (*program_ids, *roles),
    )]
    window = _window_for(definition)
    label = ", ".join(r.replace("_", " ") for r in roles)
    if not rows:
        return _component(
            key=definition["key"], state="unknown",
            reason=f"No {label} is recorded in scope.",
            missing=[f"Record a {label}"],
        )
    # A role without a dated, evidenced assessment is a name in a box. CLAUDE.md requires both on
    # every stakeholder judgement, so a bare role is `thin`, not `met`.
    assessed = [r for r in rows if r["stance_assessed_on"] and r["stance_evidence_note"]] \
        if require_assessment else rows
    evidence = [_ev("stakeholder_role", r["id"],
                    f"{r['person_name']} — {r['role'].replace('_', ' ')}") for r in rows]
    newest = max([r["stance_assessed_on"] for r in assessed if r["stance_assessed_on"]],
                 default=None)
    freshness = _freshness(ctx.as_of, newest, window)
    if len(assessed) >= minimum and freshness != "stale":
        return _component(
            key=definition["key"], state="met", freshness=freshness, evidence=evidence,
            provenance="operator_recorded", assessed_through=newest,
            reason=f"{_plural(len(assessed), 'assessed ' + label)} in scope.",
        )
    if freshness == "stale":
        return _component(
            key=definition["key"], state="thin", freshness=freshness, evidence=evidence,
            provenance="operator_recorded", assessed_through=newest,
            reason=f"The {label} assessment is older than the window for this requirement.",
            missing=[f"Reassess the {label} stance with a dated evidence note"],
        )
    return _component(
        key=definition["key"], state="thin", freshness=freshness, evidence=evidence,
        provenance="operator_recorded", assessed_through=newest,
        reason=(f"{_plural(len(rows), 'matching role')} recorded, "
                f"{len(assessed)} with a dated assessment; {minimum} required."),
        missing=[f"Record a dated stance and evidence note for the {label}"],
    )


# --- record_exists --------------------------------------------------------------------------------
# The allowlist is the point. `record_exists` reaching an arbitrary table would let a definition
# assert readiness from anything in the database, including the proposal store and the audit log.
_RECORD_SOURCES = {
    "decision":          {"table": "decisions", "scope": "account", "date": "decided_on",
                          "label": "description"},
    "risk":              {"table": "risks", "scope": "program", "date": "created_at",
                          "label": "description"},
    "issue":             {"table": "issues", "scope": "program", "date": "created_at",
                          "label": "description"},
    "milestone":         {"table": "milestones", "scope": "program", "date": "target_date",
                          "label": "name"},
    "value_target":      {"table": "value_targets", "scope": "account_only", "date": "accepted_on",
                          "label": "unit"},
    "value_story":       {"table": "value_stories", "scope": "account", "date": "created_at",
                          "label": "outcome"},
    "interaction":       {"table": "interactions", "scope": "account", "date": "occurred_on",
                          "label": "summary"},
    "metric_observation": {"table": "metric_observations", "scope": "program",
                           "date": "current_through", "label": "period_label"},
    "document":          {"table": "generated_documents", "scope": "account", "date": "generated_at",
                          "label": "title"},
    "expansion_opportunity": {"table": "expansion_opportunities", "scope": "account",
                              "date": "created_at", "label": "name"},
}

# Filters a definition may apply, per record type. Also an allowlist, for the same reason.
_RECORD_FILTERS = {
    "decision": {"status"}, "risk": {"status", "severity"}, "issue": {"status"},
    "milestone": {"status"}, "value_target": {"status", "direction"},
    "value_story": {"evidence_tier", "visibility_class"}, "interaction": {"type"},
    "metric_observation": {"cohort_label"}, "document": {"kind", "status"},
    "expansion_opportunity": {"status", "budget_state"},
}


def _record_scope_clause(ctx: _Ctx, spec: dict) -> tuple[str, list]:
    if spec["scope"] == "account_only":
        return "account_id = ?", [ctx.account_id]
    program_ids = _scope_programs(ctx)
    if spec["scope"] == "program":
        if not program_ids:
            return "0 = 1", []
        return f"program_id IN ({','.join('?' for _ in program_ids)})", list(program_ids)
    # "account": the record carries both, and a program scope narrows without excluding the
    # account-level rows that legitimately have no program.
    clause, params = "account_id = ?", [ctx.account_id]
    if ctx.program_id:
        clause += " AND (program_id = ? OR program_id IS NULL)"
        params.append(ctx.program_id)
    return clause, params


def _eval_record_exists(ctx: _Ctx, definition: dict, instances: list[dict]) -> dict:
    config = json.loads(definition["evaluator_config_json"] or "{}")
    record_type = config.get("record_type")
    spec = _RECORD_SOURCES.get(record_type)
    if spec is None:
        return _unknown(definition,
                        f"Record type “{record_type}” is not available to this evaluator.")
    filters = dict(config.get("where") or {})
    unsupported = set(filters) - _RECORD_FILTERS.get(record_type, set())
    if unsupported:
        return _unknown(definition,
                        f"Filter(s) not available on {record_type}: "
                        f"{', '.join(sorted(unsupported))}.")
    minimum = int(config.get("min_count", 1))
    clause, params = _record_scope_clause(ctx, spec)
    for column, value in sorted(filters.items()):
        clause += f" AND {column} = ?"
        params.append(value)
    rows = [dict(r) for r in ctx.conn.execute(
        f"SELECT * FROM {spec['table']} WHERE archived = 0 AND {clause} "
        f"ORDER BY {spec['date']} DESC", tuple(params),
    )]
    label = record_type.replace("_", " ")
    if not rows:
        return _component(
            key=definition["key"], state="unknown",
            reason=f"No matching {label} exists in scope.",
            missing=[f"Record a {label} that satisfies this condition"],
        )
    window = _window_for(definition)
    newest = rows[0].get(spec["date"])
    freshness = _freshness(ctx.as_of, newest[:10] if newest else None, window)
    evidence = [_ev(record_type, r["id"], str(r.get(spec["label"]) or r["id"])[:120])
                for r in rows[:5]]
    if len(rows) >= minimum and freshness != "stale":
        return _component(
            key=definition["key"], state="met", freshness=freshness, evidence=evidence,
            provenance="operator_recorded", assessed_through=newest[:10] if newest else None,
            reason=f"{_plural(len(rows), label)} in scope.",
        )
    return _component(
        key=definition["key"], state="thin", freshness=freshness, evidence=evidence,
        provenance="operator_recorded", assessed_through=newest[:10] if newest else None,
        reason=(f"The most recent {label} is outside this requirement's window."
                if freshness == "stale"
                else f"{_plural(len(rows), label)} in scope; {minimum} required."),
        missing=[f"Record a current {label}"],
    )


# --- record_closed --------------------------------------------------------------------------------
# Governed closure only, and only for statuses that mean the work happened. A cancelled Task is
# closed and proves nothing; treating it as completion is exactly how "Resolve" becomes a way to
# clear the board (§15.7).
_CLOSED_STATUSES = {"task": {"done"}, "commitment": {"closed"}}


def _eval_record_closed(ctx: _Ctx, definition: dict, instances: list[dict]) -> dict:
    config = json.loads(definition["evaluator_config_json"] or "{}")
    minimum = int(config.get("min_count", 1))
    linked = _linked_actions(ctx, instances, "advances")
    if not instances:
        return _component(
            key=definition["key"], state="unknown",
            reason="This requirement is not scheduled by a plan, so it has no linked actions.",
            missing=["Instantiate a playbook that schedules this requirement"],
        )
    if not linked:
        return _component(
            key=definition["key"], state="unknown",
            reason="No action is linked to this requirement.",
            missing=["Link the task or commitment that advances this requirement"],
        )
    evidence = [_ev(item["kind"], item["record"]["id"],
                    f"{item['record']['description'][:110]} — {item['record']['status']}")
                for item in linked]
    closed = [item for item in linked
              if item["record"]["status"] in _CLOSED_STATUSES[item["kind"]]]
    window = _window_for(definition)
    newest = max([item["record"]["closed_on"] for item in closed if item["record"]["closed_on"]],
                 default=None)
    freshness = _freshness(ctx.as_of, newest, window)
    if len(closed) >= minimum and freshness != "stale":
        return _component(
            key=definition["key"], state="met", freshness=freshness, evidence=evidence,
            provenance="operator_recorded", assessed_through=newest,
            reason=f"{_plural(len(closed), 'linked action')} closed through the governed flow.",
        )
    if freshness == "stale":
        return _component(
            key=definition["key"], state="thin", freshness=freshness, evidence=evidence,
            provenance="operator_recorded", assessed_through=newest,
            reason="The linked action closed outside this requirement's window.",
            missing=["Repeat the work this requirement asks for"],
        )
    open_items = [item for item in linked if item not in closed]
    return _component(
        key=definition["key"], state="thin", freshness=freshness, evidence=evidence,
        provenance="operator_recorded",
        # Spelled out because it is the single most common misreading of the Path: a linked action
        # is intent, and intent is not completion.
        reason=(f"{_plural(len(open_items), 'linked action')} still open; "
                f"{minimum} closed required."),
        missing=[f"Close: {item['record']['description'][:80]}" for item in open_items[:3]],
    )


# --- metric_ready ---------------------------------------------------------------------------------

def _eval_metric_ready(ctx: _Ctx, definition: dict, instances: list[dict]) -> dict:
    """Definition, baseline, owner, and cadence — four separate facts, reported separately.

    The count matters: a metric with an owner and no baseline is not "half ready", it is missing a
    baseline, and the operator needs to be told which one. Nothing here recomputes a metric value
    (CLAUDE.md); it only reports whether the definition around it is complete.
    """
    config = json.loads(definition["evaluator_config_json"] or "{}")
    require = set(config.get("require") or ("definition", "baseline", "owner", "cadence"))
    program_ids = _scope_programs(ctx)
    if not program_ids:
        return _component(key=definition["key"], state="unknown",
                          reason="No live program is in scope for this requirement.")
    marks = ",".join("?" for _ in program_ids)
    rows = [dict(r) for r in ctx.conn.execute(
        f"SELECT DISTINCT md.* FROM metric_definitions md "
        f"JOIN metric_observations mo ON mo.definition_id = md.id "
        f"WHERE mo.program_id IN ({marks}) AND md.archived = 0 AND mo.archived = 0 "
        f"ORDER BY md.name",
        tuple(program_ids),
    )]
    if "definition" in require and not rows:
        return _component(
            key=definition["key"], state="unknown",
            reason="No metric definition has an observation in this scope.",
            missing=["Define the metric this requirement measures"],
        )
    window = _window_for(definition)
    best, best_gaps, best_through = None, None, None
    for row in rows:
        observation = ctx.conn.execute(
            f"SELECT * FROM metric_observations WHERE definition_id = ? "
            f"AND program_id IN ({marks}) AND archived = 0 "
            f"ORDER BY ifnull(current_through,'') DESC LIMIT 1",
            (row["id"], *program_ids),
        ).fetchone()
        gaps = []
        if "baseline" in require and (observation is None or not observation["current_through"]):
            gaps.append(f"Record a dated baseline observation for {row['name']}")
        if "owner" in require and not (row["owner"] or "").strip():
            gaps.append(f"Name an owner for {row['name']}")
        if "cadence" in require and row["stale_after_days"] is None:
            gaps.append(f"Set a refresh cadence for {row['name']}")
        through = observation["current_through"] if observation else None
        if best is None or len(gaps) < len(best_gaps):
            best, best_gaps, best_through = row, gaps, through
        if not gaps:
            break
    evidence = [_ev("metric_definition", best["id"], best["name"])] if best else []
    if best_through:
        evidence.append(_ev("metric_observation", best["id"], f"Current through {best_through}"))
    freshness = _freshness(ctx.as_of, best_through, window)
    if best and not best_gaps and freshness != "stale":
        return _component(
            key=definition["key"], state="met", freshness=freshness, evidence=evidence,
            provenance="confirmed_source", assessed_through=best_through,
            reason=f"{best['name']} has a definition, baseline, owner, and cadence.",
        )
    if best and not best_gaps:
        return _component(
            key=definition["key"], state="thin", freshness=freshness, evidence=evidence,
            provenance="confirmed_source", assessed_through=best_through,
            reason=f"{best['name']} is fully defined but its latest observation is stale.",
            missing=[f"Refresh the {best['name']} observation"],
        )
    return _component(
        key=definition["key"], state="thin", freshness=freshness, evidence=evidence,
        provenance="operator_recorded", assessed_through=best_through,
        reason=(f"{_plural(len(best_gaps or []), 'part', 'parts')} of the metric definition "
                "outstanding."),
        missing=best_gaps or ["Define the metric this requirement measures"],
    )


# --- milestone_complete ---------------------------------------------------------------------------

def _eval_milestone_complete(ctx: _Ctx, definition: dict, instances: list[dict]) -> dict:
    """A Milestone reaches a requirement only through an action they both link to.

    There is no requirement-to-milestone table and this evaluator does not invent one. The path is
    explicit and two hops long: an action `advances` this requirement, and the same action
    `advances` the milestone. That is the same explicit-relation rule §15.8 applies to the timeline
    dependency lines, and it is why a milestone that merely shares a program cannot be claimed here.
    """
    config = json.loads(definition["evaluator_config_json"] or "{}")
    minimum = int(config.get("min_count", 1))
    if not instances:
        return _component(
            key=definition["key"], state="unknown",
            reason="This requirement is not scheduled by a plan, so it has no linked milestones.",
            missing=["Instantiate a playbook that schedules this requirement"],
        )
    marks = ",".join("?" for _ in instances)
    rows = [dict(r) for r in ctx.conn.execute(
        f"SELECT DISTINCT m.* FROM readiness_requirement_action_links l "
        f"JOIN milestone_action_links ml "
        f"  ON ml.archived = 0 AND ml.relation = 'advances' "
        f"  AND ((ml.task_id IS NOT NULL AND ml.task_id = l.task_id) "
        f"    OR (ml.commitment_id IS NOT NULL AND ml.commitment_id = l.commitment_id)) "
        f"JOIN milestones m ON m.id = ml.milestone_id AND m.archived = 0 "
        f"WHERE l.plan_instance_id IN ({marks}) AND l.archived = 0 AND l.relation = 'advances' "
        f"ORDER BY m.target_date",
        tuple(i["id"] for i in instances),
    )]
    if not rows:
        return _component(
            key=definition["key"], state="unknown",
            reason="No milestone is linked to this requirement through a shared action.",
            missing=["Link the milestone this requirement depends on to its action"],
        )
    evidence = [_ev("milestone", r["id"], f"{r['name']} — {r['status']}") for r in rows]
    complete = [r for r in rows if r["status"] == "complete"]
    window = _window_for(definition)
    newest = max([r["completed_on"] for r in complete if r["completed_on"]], default=None)
    freshness = _freshness(ctx.as_of, newest, window)
    if len(complete) >= minimum:
        return _component(
            key=definition["key"], state="met", freshness=freshness, evidence=evidence,
            provenance="operator_recorded", assessed_through=newest,
            reason=f"{_plural(len(complete), 'linked milestone')} complete.",
        )
    return _component(
        key=definition["key"], state="thin", freshness=freshness, evidence=evidence,
        provenance="operator_recorded",
        reason=(f"{_plural(len(rows), 'linked milestone')} not yet complete; "
                f"{minimum} required."),
        missing=[f"Complete: {r['name']}" for r in rows if r["status"] != "complete"][:3],
    )


# --- manual_evidence_review -----------------------------------------------------------------------

def _eval_manual_evidence_review(ctx: _Ctx, definition: dict, instances: list[dict]) -> dict:
    """A dated reviewer decision, for conditions automation cannot settle.

    The date is what makes this an evaluator rather than a checkbox. A review ages against the
    requirement's own freshness window exactly like any other dated fact, so "someone looked at
    this once in March" stops counting when March stops being current.
    """
    config = json.loads(definition["evaluator_config_json"] or "{}")
    minimum = int(config.get("min_count", 1))
    links = [link for link in _live_evidence_links(ctx, instances)
             if link["supporting"] and link["reviewed_on"]]
    if not links:
        return _component(
            key=definition["key"], state="unknown",
            reason="No reviewed evidence is attached to this requirement.",
            missing=["Attach evidence and record a dated review decision"],
        )
    window = _window_for(definition)
    newest = max(link["reviewed_on"] for link in links)
    freshness = _freshness(ctx.as_of, newest, window)
    evidence = [_ev(link["evidence_type"], link["evidence_id"],
                    f"{link['evidence_label']} — reviewed {link['reviewed_on']}")
                for link in links]
    if len(links) >= minimum and freshness != "stale":
        return _component(
            key=definition["key"], state="met", freshness=freshness, evidence=evidence,
            provenance="operator_recorded", assessed_through=newest,
            reason=f"{_plural(len(links), 'reviewed evidence record')} attached.",
        )
    return _component(
        key=definition["key"], state="thin", freshness=freshness, evidence=evidence,
        provenance="operator_recorded", assessed_through=newest,
        reason=("The review of this evidence is older than the requirement's window."
                if freshness == "stale"
                else f"{_plural(len(links), 'reviewed record')}; {minimum} required."),
        missing=["Record a current review decision for this evidence"],
    )


# --- all_of / any_of ------------------------------------------------------------------------------

def _child_definition(definition: dict, child: dict) -> dict:
    """A child evaluator runs against the parent's definition row with the child's configuration.

    The freshness policy is deliberately inherited: a composite is judged against one window, so a
    child cannot quietly assert a longer one and make the whole condition look current.
    """
    return dict(
        definition,
        evaluator_config_json=json.dumps(child.get("config") or {}),
    )


def _eval_composite(ctx: _Ctx, definition: dict, instances: list[dict], *, mode: str) -> dict:
    config = json.loads(definition["evaluator_config_json"] or "{}")
    children = list(config.get("evaluators") or [])
    if not children:
        return _unknown(definition, f"No child evaluators are configured for this {mode}.")
    results, unresolved = [], []
    for child in children:
        key = (child.get("evaluator_key"), int(child.get("evaluator_version", 1)))
        fn = _COMPOSABLE_EVALUATORS.get(key)
        if fn is None:
            unresolved.append(f"{key[0]} v{key[1]}")
            continue
        results.append((child, fn(ctx, _child_definition(definition, child), instances)))
    if unresolved:
        # Fails closed as one unit. Reporting the resolvable children's verdict while silently
        # dropping the rest would answer a narrower question than the definition asked.
        return _unknown(definition,
                        f"Child evaluator(s) not in the allowlisted registry: "
                        f"{', '.join(sorted(unresolved))}.")
    evidence, missing = [], []
    for _child, result in results:
        evidence.extend(result["evidence"])
        missing.extend(result["missing"])
    met = [r for _c, r in results if r["state"] == "met"]
    freshness = _aggregate_freshness([r for _c, r in results])
    satisfied = len(met) == len(results) if mode == "all_of" else bool(met)
    if satisfied:
        return _component(
            key=definition["key"], state="met", freshness=freshness, evidence=evidence,
            provenance="operator_recorded",
            reason=(f"All {len(results)} parts of this condition are satisfied."
                    if mode == "all_of"
                    else f"{_plural(len(met), 'part')} of this condition is satisfied."),
        )
    unknowns = [r for _c, r in results if r["state"] == "unknown"]
    return _component(
        key=definition["key"],
        # `unknown` only when nothing is known at all. A composite with one satisfied part is thin,
        # not unknown: the operator has partial ground and the difference is actionable.
        state="unknown" if len(unknowns) == len(results) else "thin",
        freshness=freshness, evidence=evidence,
        provenance="operator_recorded" if evidence else None,
        reason=(f"{len(met)} of {len(results)} parts satisfied."
                if mode == "all_of"
                else f"None of the {len(results)} alternatives is satisfied."),
        missing=missing,
    )


# Composable children. `all_of`/`any_of` are absent on purpose: allowing them here would let a
# configuration nest itself into unbounded recursion, and no requirement in the spec needs it.
_COMPOSABLE_EVALUATORS: dict[tuple[str, int], callable] = {
    ("field_present", 1): _eval_field_present,
    ("role_present", 1): _eval_role_present,
    ("record_exists", 1): _eval_record_exists,
    ("record_closed", 1): _eval_record_closed,
    ("metric_ready", 1): _eval_metric_ready,
    ("milestone_complete", 1): _eval_milestone_complete,
    ("manual_evidence_review", 1): _eval_manual_evidence_review,
}


# --- the allowlisted registry (§2.3) --------------------------------------------------------------
# A definition row selects an entry here. It cannot add one. An unrecognized (key, version) pair
# fails closed into partial coverage rather than being skipped silently.
_REQUIREMENT_EVALUATORS: dict[tuple[str, int], callable] = {
    # Generic definition-of-done evaluators (ACCOUNT-PATH-SPEC.md §15.4).
    ("field_present", 1): lambda c, d: _generic(c, d, _eval_field_present),
    ("role_present", 1): lambda c, d: _generic(c, d, _eval_role_present),
    ("record_exists", 1): lambda c, d: _generic(c, d, _eval_record_exists),
    ("record_closed", 1): lambda c, d: _generic(c, d, _eval_record_closed),
    ("metric_ready", 1): lambda c, d: _generic(c, d, _eval_metric_ready),
    ("milestone_complete", 1): lambda c, d: _generic(c, d, _eval_milestone_complete),
    ("manual_evidence_review", 1): lambda c, d: _generic(c, d, _eval_manual_evidence_review),
    ("all_of", 1): lambda c, d: _generic(
        c, d, lambda cx, df, ins: _eval_composite(cx, df, ins, mode="all_of")),
    ("any_of", 1): lambda c, d: _generic(
        c, d, lambda cx, df, ins: _eval_composite(cx, df, ins, mode="any_of")),
    # Relationship-readiness pillar evaluators (RELATIONSHIP-READINESS-SPEC.md §2.3).
    ("breadth_engaged_contacts", 1): _eval_breadth_contacts,
    ("breadth_layer_spread", 1): _eval_breadth_layers,
    ("champion_primary_validated", 1): _eval_champion_primary,
    ("champion_second_thread", 1): _eval_champion_second_thread,
    ("exec_identified", 1): _eval_exec_identified,
    ("exec_engaged", 1): _eval_exec_engaged,
    ("exec_value_link", 1): _eval_exec_value_link,
    ("value_baseline_locked", 1): _eval_value_baseline,
    ("value_comparison_observation", 1): _eval_value_comparison,
    ("budget_authority_evidence", 1): _eval_budget_authority,
    ("budget_owner_engagement", 1): _eval_budget_engagement,
    ("expansion_opportunity_open", 1): _eval_expansion_open,
    ("expansion_client_ownership", 1): _eval_expansion_ownership,
    ("expansion_dated_next_step", 1): _eval_expansion_next_step,
    ("expansion_budget_state", 1): _eval_expansion_budget_state,
}

_PILLAR_EVALUATORS: set[tuple[str, int]] = {
    ("stakeholder_breadth", 1), ("champion_continuity", 1), ("executive_sponsorship", 1),
    ("quantified_value", 1), ("budget_owner", 1), ("active_expansion_plan", 1),
}


def supported_requirement_evaluators() -> list[dict]:
    return [{"evaluator_key": k, "evaluator_version": v}
            for k, v in sorted(_REQUIREMENT_EVALUATORS)]


# --- aggregation (§2.1, §3.3, §3.4) ---------------------------------------------------------------

def _aggregate_state(components: list[dict]) -> tuple[str, str]:
    """Pillar state from its component results, plus the sentence that names the deciding one.

    Suppressed components are excluded from the judgment but not from the list. When every one of
    them is suppressed the pillar is `not_applicable` — there is nothing left to be ready about —
    and never `met`, which is the difference between an operator excusing a condition and an
    operator satisfying it.
    """
    components = [c for c in components if c["state"] != "not_applicable"]
    if not components:
        return "not_applicable", "Every condition in this pillar is marked not applicable."
    states = [c["state"] for c in components]
    if "conflicted" in states:
        c = next(c for c in components if c["state"] == "conflicted")
        return "conflicted", c["reason"]
    if states and all(s == "met" for s in states):
        # Component reasons are already complete sentences, so they join as sentences. A
        # semicolon here produced "…4 records.; Henrik…".
        return "met", " ".join(c["reason"] for c in components if c["reason"])
    if states and all(s == "unknown" for s in states):
        return "unknown", next((c["reason"] for c in components if c["reason"]), "")
    deciding = next((c for c in components if c["state"] in ("thin", "unknown")), None)
    return "thin", (deciding["reason"] if deciding else "")


def _aggregate_freshness(components: list[dict]) -> str:
    values = {c["freshness"] for c in components} - {"not_applicable"}
    if not values:
        return "not_applicable"
    if values == {"current"}:
        return "current"
    if values == {"stale"}:
        return "stale"
    if values == {"undated"}:
        return "undated"
    return "mixed"


# Strongest first: an account-scoped pillar takes the strongest applicability across the account's
# live programs. There is one budget-owner answer per account, so if any live program's phase
# requires it, the account requires it — reporting `optional` because no single program is selected
# would hide a required gap behind a scope choice.
_APPLICABILITY_RANK = {"required": 0, "optional": 1, "not_due": 2, "not_applicable": 3}


def _phase_applicability(pillar: dict, phase: str) -> str:
    mapping = json.loads(pillar["phase_applicability_json"] or "{}")
    value = mapping.get(phase, "optional")
    return value if value in APPLICABILITY else "optional"


def _applicability(ctx: _Ctx, pillar: dict) -> str:
    """Phase drives applicability; it never fabricates evidence (§3.2)."""
    if ctx.program:
        return _phase_applicability(pillar, ctx.program["phase"])
    phases = [r["phase"] for r in ctx.conn.execute(
        "SELECT phase FROM programs WHERE account_id = ? AND archived = 0", (ctx.account_id,)
    ).fetchall()]
    if not phases:
        return "optional"
    return min((_phase_applicability(pillar, p) for p in phases),
               key=lambda v: _APPLICABILITY_RANK[v])


# --- evaluation ----------------------------------------------------------------------------------

def _load_definitions(conn) -> list[dict]:
    # §7.4. Derived over the whole definition table, not over the pillars being loaded, so the
    # token names the same row on every surface. No column is added for it.
    refs = short_ref.requirement_refs(conn)
    pillars = conn.execute(
        "SELECT * FROM readiness_pillar_definitions "
        "WHERE retired_at IS NULL AND archived = 0 ORDER BY display_order, key"
    ).fetchall()
    out = []
    for p in pillars:
        p = dict(p)
        p["requirements"] = []
        for r in conn.execute(
            "SELECT * FROM readiness_requirement_definitions "
            "WHERE pillar_key = ? AND pillar_version = ? AND retired_at IS NULL AND archived = 0 "
            "ORDER BY rowid",
            (p["key"], p["version"]),
        ).fetchall():
            r = dict(r)
            r["ref"] = refs.get(f"{r['key']}:{r['version']}")
            p["requirements"].append(r)
        out.append(p)
    return out


def _resolve_program(conn, account_id: str, program_id: str | None) -> dict | None:
    """§3.1: an unknown, foreign, or archived program is an error, never a silent fallback to
    account scope — falling back would answer a different question than the one asked."""
    if not program_id:
        return None
    row = conn.execute(
        "SELECT * FROM programs WHERE id = ? AND account_id = ? AND archived = 0",
        (program_id, account_id),
    ).fetchone()
    if row is None:
        raise HTTPException(
            status_code=404,
            detail="program not found on this account (readiness does not fall back to account scope)",
        )
    return dict(row)


def _evaluate_pillar(ctx: _Ctx, pillar: dict) -> dict:
    result = {
        "key": pillar["key"],
        "definition_version": pillar["version"],
        "evaluator_version": pillar["evaluator_version"],
        "label": pillar["label"],
        "purpose": pillar["purpose"],
        "research_class": pillar["research_class"],
        "scope": pillar["default_scope"],
        "applicability": _applicability(ctx, pillar),
    }
    if (pillar["evaluator_key"], pillar["evaluator_version"]) not in _PILLAR_EVALUATORS:
        result.update({
            "state": "unknown", "freshness": "not_applicable", "components": [],
            "reason": (f"Pillar evaluator {pillar['evaluator_key']} v{pillar['evaluator_version']} "
                       "is not in the allowlisted registry."),
            "missing": [], "suggested_action": None,
            "suppressed_count": 0, "waived_count": 0,
            "coverage_failures": [pillar["evaluator_key"]],
        })
        return result
    if result["applicability"] in ("not_applicable", "not_due"):
        # Not evaluated on purpose: an inapplicable condition must not read as a missing one.
        # At account scope there is no single phase to name — applicability took the strongest
        # answer across the live programs, so reaching here means *every* one of them said so.
        if ctx.program:
            phase_clause = f"the {ctx.program['phase']} phase"
        else:
            phase_clause = "any live program's current phase"
        result.update({
            "state": "not_applicable" if result["applicability"] == "not_applicable" else "unknown",
            "freshness": "not_applicable", "components": [], "missing": [],
            "suggested_action": None, "suppressed_count": 0, "waived_count": 0,
            "reason": (f"Not applicable in {phase_clause}."
                       if result["applicability"] == "not_applicable"
                       else f"Not due during {phase_clause}."),
        })
        return result

    components, failures, missing, action = [], [], [], None
    for definition in pillar["requirements"]:
        exception = ctx.exceptions.get(definition["key"])
        if exception is not None and exception["kind"] == "not_applicable":
            component = _suppressed_component(definition, exception)
        else:
            evaluator = _REQUIREMENT_EVALUATORS.get(
                (definition["evaluator_key"], definition["evaluator_version"])
            )
            if evaluator is None:
                # Fails closed as a component rather than by disappearing. A condition nobody
                # could evaluate has to keep its label, its key, and the evaluator that was
                # asked for, or the gap becomes invisible in exactly the pillar that has one.
                failures.append(definition["evaluator_key"])
                component = _component(
                    key=definition["key"], state="unknown",
                    reason=(f"Evaluator {definition['evaluator_key']} "
                            f"v{definition['evaluator_version']} is not in the allowlisted "
                            "registry."),
                )
            else:
                component = evaluator(ctx, definition)
                if exception is not None:
                    # A waiver leaves the state exactly where the evidence put it. It only records
                    # that the gap is knowingly accepted, so the ask stops being outstanding while
                    # the pillar keeps reporting thin.
                    component["waiver"] = _exception_public(exception)
                    component["missing"] = []
        component["label"] = definition["label"]
        component["definition_key"] = definition["key"]
        component["definition_version"] = definition["version"]
        component["definition_of_done"] = definition["definition_of_done"]
        # §15.4/§15.5 — which evaluator produced this, at which version. Gate readiness reports it
        # so a change in a state can be attributed to a rule change rather than to the account.
        component["evaluator_key"] = definition["evaluator_key"]
        component["evaluator_version"] = definition["evaluator_version"]
        # VISIBILITY-SPEC §7.2. What the definition row *configured*, carried out beside the key
        # that names the evaluator — set here rather than inside either branch, because the case
        # that most needs it is the one where no evaluator ran: an unallowlisted key fails closed
        # into `coverage: partial` and until now nothing on screen said what had been asked for.
        # This is configuration, not a reading; it never carries a state, and the operand values
        # are rendered verbatim rather than described, so nothing here can restate the evaluator.
        component["evaluator_config"] = json.loads(definition["evaluator_config_json"] or "{}")
        # §7.4. A name to say out loud, never a sort key and never an ordering.
        component["ref"] = definition.get("ref")
        components.append(component)
        missing.extend(component["missing"])
        if action is None and component["state"] not in ("met", "not_applicable") \
                and not component.get("waiver") and definition["suggested_action_json"]:
            action = json.loads(definition["suggested_action_json"])

    state, reason = _aggregate_state(components)
    suppressed = [c for c in components if c.get("applicability_override")]
    waived = [c for c in components if c.get("waiver")]
    if suppressed and len(suppressed) == len(components):
        # Nothing is left to evaluate, so the pillar's applicability follows the decision rather
        # than the program phase — otherwise a fully excused pillar would keep reading `required`
        # and Account Path would keep listing it as a gap.
        result["applicability"] = "not_applicable"
    elif suppressed:
        verb = "is" if len(suppressed) == 1 else "are"
        reason = (f"{reason} {len(suppressed)} of {len(components)} conditions in this pillar "
                  f"{verb} marked not applicable by an operator decision.")
    if waived:
        verb = "is" if len(waived) == 1 else "are"
        reason = f"{reason} {_plural(len(waived), 'accepted gap')} {verb} waived."
    result.update({
        "state": state,
        "freshness": _aggregate_freshness(components),
        "reason": reason.strip(),
        "components": components,
        "missing": missing,
        "suggested_action": action,
        "suppressed_count": len(suppressed),
        "waived_count": len(waived),
        # Every unresolvable evaluator is named, not just the first: an operator cannot fix code
        # that the response will not identify.
        "coverage_failures": failures,
    })
    return result


def evaluate(conn: sqlite3.Connection, account_id: str, program_id: str | None = None,
             as_of: str | None = None,
             evaluator_override: dict[str, int] | None = None) -> dict:
    """The §5.2 response. Writes nothing; every conclusion links to the records that produced it.

    `evaluator_override` maps a pillar key to an evaluator version to run *instead of* the live
    definition's. It exists for §7.4's upgrade preview and nothing else: a preview that cannot run
    the candidate cannot preview anything. It only swaps which allowlisted evaluator executes — it
    cannot introduce one, and it writes nothing, so a preview stays a read.
    """
    account = conn.execute(
        "SELECT id, name FROM accounts WHERE id = ? AND archived = 0", (account_id,)
    ).fetchone()
    if account is None:
        raise HTTPException(status_code=404, detail="account not found")
    program = _resolve_program(conn, account_id, program_id)
    as_of = _as_of(as_of)

    definitions = _load_definitions(conn)
    for pillar in definitions:
        candidate = (evaluator_override or {}).get(pillar["key"])
        if candidate is not None:
            pillar["evaluator_version"] = candidate
    if not definitions:
        return {
            "scope": {"account_id": account_id, "program_id": program_id},
            "as_of": as_of,
            "coverage": {"status": "unavailable", "warnings": ["no live pillar definitions"],
                         "failed_evaluators": []},
            "pillars": [], "programs": [],
        }

    warnings: list[str] = []
    failed: list[str] = []

    def run(scope_program: dict | None, keys: set[str], *,
            account_wide_evidence: bool = False) -> list[dict]:
        """Evaluate `keys` in one scope. `account_wide_evidence` unpins the evidence scope from
        the view's program while leaving phase (and therefore applicability) pinned to it."""
        evidence_program = None if account_wide_evidence or not scope_program else scope_program
        ctx = _Ctx(conn, account_id, evidence_program["id"] if evidence_program else None, as_of,
                   scope_program)
        out = []
        for pillar in definitions:
            if pillar["key"] not in keys:
                continue
            evaluated = _evaluate_pillar(ctx, pillar)
            failed.extend(evaluated.pop("coverage_failures", []))
            out.append(evaluated)
        return out

    program_keys = {p["key"] for p in definitions if p["default_scope"] == "program"}
    account_keys = {p["key"] for p in definitions if p["default_scope"] != "program"}

    if program:
        # An account-scoped pillar is one answer per account. Evaluating it inside the selected
        # program would recompute it from that program's evidence alone, so the same account-level
        # truth would read `met` beside one program and `unknown` beside its sibling — a scope
        # choice silently changing a fact about the account. Evidence is therefore gathered
        # account-wide and inherited into the program view; only applicability responds to the
        # selected program's phase, which is the one thing a phase is entitled to decide (§3.2).
        # Suppressions follow the evidence for the same reason: the account view already applies
        # only account-wide exceptions to these pillars, so letting one program's waiver reach them
        # here would reintroduce the disagreement from the other side.
        by_key = {p["key"]: p for p in run(program, program_keys)}
        by_key.update({p["key"]: p for p in run(program, account_keys,
                                                account_wide_evidence=True)})
        pillars = [by_key[d["key"]] for d in definitions if d["key"] in by_key]
        programs_out: list[dict] = []
    else:
        # §3.1: all-program scope keeps each program's assessment separate. Merging Program A's
        # champion with Program B's executive would manufacture a `met` that is true of neither.
        pillars = run(None, account_keys)
        programs_out = []
        rows = conn.execute(
            "SELECT * FROM programs WHERE account_id = ? AND archived = 0 ORDER BY name",
            (account_id,),
        ).fetchall()
        for row in rows:
            row = dict(row)
            programs_out.append({
                "program_id": row["id"], "program_name": row["name"], "phase": row["phase"],
                "pillars": run(row, program_keys),
            })
        if not rows and program_keys:
            warnings.append("no live programs on this account; program-scoped pillars not evaluated")

    status = "complete"
    if failed:
        status = "partial"
        warnings.append("one or more evaluators are unavailable; results are incomplete")
    return {
        "scope": {"account_id": account_id, "account_name": account["name"],
                  "program_id": program["id"] if program else None,
                  "program_name": program["name"] if program else None,
                  "phase": program["phase"] if program else None},
        "as_of": as_of,
        "coverage": {"status": status, "warnings": warnings,
                     "failed_evaluators": sorted(set(failed))},
        "pillars": pillars,
        "programs": programs_out,
    }


def pillar_evidence(conn: sqlite3.Connection, account_id: str, pillar_key: str,
                    program_id: str | None = None, as_of: str | None = None) -> dict:
    """One pillar in full: every component, its evidence, and what would resolve the gap."""
    result = evaluate(conn, account_id, program_id, as_of)
    for pillar in result["pillars"]:
        if pillar["key"] == pillar_key:
            return {"scope": result["scope"], "as_of": result["as_of"],
                    "coverage": result["coverage"], "pillar": pillar}
    for entry in result["programs"]:
        for pillar in entry["pillars"]:
            if pillar["key"] == pillar_key:
                return {"scope": {**result["scope"], "program_id": entry["program_id"],
                                  "program_name": entry["program_name"]},
                        "as_of": result["as_of"], "coverage": result["coverage"],
                        "pillar": pillar}
    raise HTTPException(status_code=404, detail="pillar not found")


def preview_definition_upgrade(conn: sqlite3.Connection, pillar_key: str,
                               evaluator_version: int) -> dict:
    """§7.4 — what changes if this evaluator version is activated, without activating it.

    The point is that a threshold change is never invisible: an operator sees which accounts and
    programs move, and in which direction, before the definition is switched.
    """
    live = conn.execute(
        "SELECT * FROM readiness_pillar_definitions "
        "WHERE key = ? AND retired_at IS NULL AND archived = 0", (pillar_key,)
    ).fetchone()
    if live is None:
        raise HTTPException(status_code=404, detail="no live definition for that pillar key")
    if (pillar_key, evaluator_version) not in _PILLAR_EVALUATORS:
        raise HTTPException(
            status_code=422,
            detail=(f"evaluator {pillar_key} v{evaluator_version} is not in the allowlisted "
                    "registry; a definition row cannot introduce executable behavior"),
        )
    # The whole point of the endpoint: run both evaluators over the same records and diff them.
    # Reporting the live state on both sides would make `changed_count` structurally zero, so the
    # governance step would report "nothing moves" for every upgrade, including the ones that move
    # everything.
    override = {pillar_key: evaluator_version}
    transitions = []
    accounts = conn.execute("SELECT id, name FROM accounts WHERE archived = 0").fetchall()
    for account in accounts:
        current = evaluate(conn, account["id"])
        candidate = evaluate(conn, account["id"], evaluator_override=override)

        def _state(result, program_id=None):
            source = result["pillars"] if program_id is None else next(
                (e["pillars"] for e in result["programs"] if e["program_id"] == program_id), [])
            for pillar in source:
                if pillar["key"] == pillar_key:
                    return pillar["state"]
            return None

        before, after = _state(current), _state(candidate)
        if before is not None or after is not None:
            transitions.append({
                "account_id": account["id"], "account_name": account["name"],
                "program_id": None, "from_state": before, "to_state": after,
            })
        for entry in current["programs"]:
            before = _state(current, entry["program_id"])
            after = _state(candidate, entry["program_id"])
            if before is None and after is None:
                continue
            transitions.append({
                "account_id": account["id"], "account_name": account["name"],
                "program_id": entry["program_id"], "program_name": entry["program_name"],
                "from_state": before, "to_state": after,
            })
    return {
        "pillar_key": pillar_key,
        "current_version": live["version"],
        "current_evaluator_version": live["evaluator_version"],
        "candidate_evaluator_version": evaluator_version,
        "applied": False,
        "affected_scopes": transitions,
        "changed_count": sum(1 for t in transitions if t["from_state"] != t["to_state"]),
    }
