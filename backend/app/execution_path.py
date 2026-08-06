"""Account Path Slice 1 — the Execution Path read model (`ACCOUNT-PATH-SPEC.md` section 10).

A query-time projection over canonical records. It writes nothing: no visit state, no review
checkpoint, no phase change, no audit event, and no readiness row — readiness is itself a
projection with nothing to write to. Rebuilding it from the same records must produce the same
answer, so nothing here may depend on projection state.

Two rules carry most of the design:

- **Native records stay authoritative.** Every row names the record it came from and opens it.
  Account Path never asserts completion in its own words.
- **Suppression is shared, not duplicated.** Snooze writes the queue's `attention_state` overlay
  through the queue's own key format. Account Path does not invent a second expiry rule.
"""
from __future__ import annotations

import os
import sqlite3
from datetime import date, timedelta

from fastapi import HTTPException

from . import checklist_compatibility, path_links, playbooks, queue, readiness
from .db import now_utc

# The canonical program lifecycle, in order. `closed` is terminal, presented after renewal.
PHASE_ORDER = ("foundation", "launch", "programmatic", "expansion", "renewal", "closed")
PHASE_LABELS = {
    "foundation": "Foundation", "launch": "Launch", "programmatic": "Programmatic",
    "expansion": "Expansion", "renewal": "Renewal", "closed": "Closed",
}
PHASE_STATES = ("complete", "current", "future", "blocked", "waived", "not_applicable", "unknown")
URGENCIES = ("now", "soon", "later")
# Matches `readiness.py` exactly: the two services must not describe the same condition with
# different words.
COVERAGE = ("complete", "partial", "unavailable")

# Windows. These are operational horizons, not benchmarks: they decide when preparation work
# becomes visible, and the reason text always states the window so it is never a hidden threshold.
DUE_SOON_DAYS = 7        # matches the existing account command-center attention horizon
EVENT_LEAD_DAYS = 14     # preparation window for a dated milestone or confirmed moment

# Section 10.5, highest band first. Readiness gaps are deliberately absent: a required condition
# with no accepted native record is a suggestion, and ranking a suggestion against real work would
# let it outrank an overdue Task.
BANDS = {
    "operator_blocker": 1,
    "current_gate_item": 2,
    "overdue_operator_task": 3,
    "overdue_commitment_follow_up": 3,
    "contract_decision_window": 4,
    "operator_task_due_soon": 5,
    "commitment_follow_up_due_soon": 5,
    "milestone_preparation": 6,
    "moment_preparation": 6,
    "latest_interaction_action": 7,
    "open_operator_work": 8,
}

# --- ranking rule versions (§17.6) ----------------------------------------------------------
#
# Ranking changes are governed: propose, fixture, compare old against new over seeded accounts,
# review the surprises, version, deploy behind a flag, and record the version in the response and
# in telemetry. That process needs two things this module must provide — a named ruleset the
# response can cite, and the ability to rank the same account under a ruleset that is not live.
#
# `v2-candidate-notice-first` is a *candidate*. It exists to be compared, not to be deployed: a
# contract decision window is time-irreversible in a way an overdue Task is not, which is an
# arguable reason to lift it above the overdue bands — and arguable is exactly what step 5 asks
# somebody to look at. `active_ranking_version()` will not return a candidate without the flag
# being set explicitly, so shipping the candidate does not ship the rule change.
RANKING_RULE_ENV = "VALENCE_OS_RANKING_RULES"
DEFAULT_RANKING_VERSION = "v1-2026-08-04"

RANKING_RULE_VERSIONS: dict[str, dict] = {
    DEFAULT_RANKING_VERSION: {
        "status": "active",
        "summary": "Section 10.5 as first written: blockers, then the current gate, then overdue "
                   "operator work, then the contract decision window.",
        "bands": BANDS,
    },
    "v2-candidate-notice-first": {
        "status": "candidate",
        "summary": "Lifts the contract decision window above overdue operator work, on the "
                   "argument that a notice date cannot be recovered once missed.",
        "bands": {**BANDS, "contract_decision_window": 3, "overdue_operator_task": 4,
                  "overdue_commitment_follow_up": 4},
    },
}


def active_ranking_version() -> str:
    """The live ruleset. A candidate is selectable only by setting the flag to its exact name."""
    requested = (os.environ.get(RANKING_RULE_ENV, "") or "").strip()
    if requested and requested in RANKING_RULE_VERSIONS:
        return requested
    return DEFAULT_RANKING_VERSION


def ranking_bands(version: str) -> dict:
    entry = RANKING_RULE_VERSIONS.get(version)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"unknown ranking rule version '{version}'")
    return entry["bands"]

# Section 6.5 source labels. Deliberately not called provenance: `RELATIONSHIP-READINESS-SPEC.md`
# uses that word for evidence *quality*, which decides whether a record can satisfy a requirement.
# A requirement row can carry both, so the two never share a name or a chip.
PROVENANCE_KINDS = (
    "interaction", "leadership_review", "program_standard", "account_standard",
    "onboarding_standard", "contract", "manual",
)

_ADAPTERS = (
    "programs", "tasks", "commitments", "risks_issues", "milestones", "phase_gates",
    "checklists", "deployment_moments", "contract_dates", "latest_interaction", "readiness",
)

# Where each record type is edited. Shape matches the app-wide `openWorkspaceTarget` contract.
_TARGET_TAB = {
    "task": "ledger", "commitment": "ledger", "risk": "ledger", "issue": "ledger",
    "milestone": "ledger", "interaction": "ledger",
    "phase_gate": "plan", "phase_gate_item": "plan", "checklist_item": "plan",
    "deployment_moment": "plan",
    "contract_version": "commercial",
}


def _target(record_type: str, record_id: str) -> dict:
    return {"tab": _TARGET_TAB[record_type], "record_type": record_type, "record_id": record_id}


def _today() -> str:
    return now_utc()[:10]


def _days(from_iso: str, to_iso: str) -> int:
    return (date.fromisoformat(to_iso) - date.fromisoformat(from_iso)).days


def _shift(iso: str, days: int) -> str:
    return (date.fromisoformat(iso) + timedelta(days=days)).isoformat()


def _pretty_date(iso: str | None) -> str:
    if not iso:
        return "an undated moment"
    return date.fromisoformat(iso[:10]).strftime("%b %-d")


class _Ctx:
    """Everything the adapters share. Built once per request; read-only throughout."""

    def __init__(self, conn: sqlite3.Connection, account: dict, program: dict | None,
                 today: str, bands: dict | None = None) -> None:
        self.conn = conn
        # The ruleset this request is ranking under (§17.6). Carried on the context rather than
        # read from the module global, so comparing two versions is a second call and never a
        # mutation of shared state.
        self.bands = bands or BANDS
        self.account = account
        self.account_id = account["id"]
        self.program = program
        self.program_id = program["id"] if program else None
        self.today = today
        self.soon = _shift(today, DUE_SOON_DAYS)
        self.lead = _shift(today, EVENT_LEAD_DAYS)
        self.programs: list[dict] = []
        self.latest_interaction: dict | None = None
        self.overlays = queue._latest_overlays(conn)
        self.queue_keys = queue.keys_for_objects(conn, today)
        self._persons: dict[str, dict | None] = {}

    # --- shared lookups -------------------------------------------------------------------

    def person(self, person_id: str | None) -> dict | None:
        """Resolve an owner label, failing closed outside the account.

        A foreign reference resolves to None rather than carrying another account's label here.
        """
        if not person_id:
            return None
        if person_id not in self._persons:
            row = self.conn.execute(
                "SELECT id,name,affiliation FROM persons WHERE id=? AND archived=0 "
                "AND (affiliation='valence' OR account_id=?)", (person_id, self.account_id)
            ).fetchone()
            self._persons[person_id] = (
                {"id": row["id"], "name": row["name"],
                 "party": "valence" if row["affiliation"] == "valence" else "customer"}
                if row else None
            )
        return self._persons[person_id]

    def program_name(self, program_id: str | None) -> str | None:
        for row in self.programs:
            if row["id"] == program_id:
                return row["name"]
        return None

    def scoped_program_ids(self) -> list[str]:
        return [self.program_id] if self.program_id else [p["id"] for p in self.programs]


# --- candidate construction ---------------------------------------------------------------

def _snooze_key(ctx: _Ctx, object_type: str, object_id: str) -> tuple[str | None, list[str]]:
    """The key Snooze writes, plus every key that can currently suppress this object.

    Section 6.1: reuse the Today queue's own key when the queue already surfaces the object, so
    "not now" here means "not now" there too. Otherwise mint `account_path:{type}:{id}` — but only
    when `queue.snooze()` would accept it, because a control that 422s on click is worse than no
    control at all.
    """
    queue_keys = ctx.queue_keys.get((object_type, object_id), [])
    fallback = f"account_path:{object_type}:{object_id}"
    if queue_keys:
        # The intent is about the object, not the trigger that found it: every queue key that
        # points here can suppress it, and the primary key is the highest-priority one.
        primary = sorted(queue_keys, key=lambda k: (queue.PRIORITY.get(k.split(":", 1)[0], 99), k))[0]
        return primary, [*queue_keys, fallback]
    if queue.snoozable_object_type(object_type):
        return fallback, [fallback]
    return None, []


def _candidate(ctx: _Ctx, *, source_type: str, source_id: str, title: str, reason: str,
               reason_code: str, updated_at: str, recorded_at: str, group: str,
               due_date: str | None = None, owner: dict | None = None,
               responsible_party: dict | None = None, program_id: str | None = None,
               provenance: dict, eligible: bool = True,
               native_target: dict | None = None, phase: str | None = None) -> dict:
    snooze_key, suppression_keys = _snooze_key(ctx, source_type, source_id)
    if due_date and due_date < ctx.today:
        urgency = "now"
    elif due_date and due_date <= ctx.soon:
        urgency = "soon"
    else:
        urgency = "later"
    return {
        "id": f"{source_type}:{source_id}",
        "snooze_key": snooze_key,
        "source_type": source_type,
        "source_id": source_id,
        "title": title,
        "reason": reason,
        "reason_code": reason_code,
        "band": ctx.bands[reason_code],
        "urgency": urgency,
        "due_date": due_date,
        "owner": owner,
        "responsible_party": responsible_party,
        "program_id": program_id,
        "program_name": ctx.program_name(program_id),
        # The phase this item genuinely belongs to, or null. Only a gate item has one: it hangs
        # off a gate, and a gate has a phase. A Task belongs to a program, not to whatever phase
        # that program happens to be in today, so stamping one on would fabricate an attribution
        # the record does not carry — and the path's phase filter reads this field.
        "phase": phase,
        # §15.8. Filled in only where an accepted explicit relation supports the claim; null is the
        # default so the field's presence never implies a gate connection nobody recorded.
        "gate_impact": None,
        "provenance": provenance,
        "native_target": native_target if native_target is not None
        else _target(source_type, source_id),
        "_updated_at": updated_at,
        "_recorded_at": recorded_at,
        "_group": group,
        "_eligible": eligible,
        "_suppression_keys": suppression_keys,
    }


def _source_label(ctx: _Ctx, row: dict, default_kind: str, default_label: str) -> dict:
    """Where the item came from, in the plain language of section 6.5."""
    interaction_id = row.get("source_interaction_id")
    if interaction_id:
        hit = ctx.conn.execute(
            "SELECT occurred_on,type FROM interactions WHERE id=? AND archived=0", (interaction_id,)
        ).fetchone()
        if hit:
            kind = (hit["type"] or "interaction").replace("_", " ")
            return {"kind": "interaction", "label": f"From {_pretty_date(hit['occurred_on'])} {kind}",
                    "interaction_id": interaction_id}
    if row.get("account_review_id"):
        return {"kind": "leadership_review", "label": "From leadership review", "interaction_id": None}
    return {"kind": default_kind, "label": default_label, "interaction_id": None}


# --- source adapters ------------------------------------------------------------------------
# Each returns normalized candidates and is run independently, so one failure names itself in
# coverage instead of blanking the page.

def _adapt_programs(ctx: _Ctx) -> list[dict]:
    sql = "SELECT * FROM programs WHERE account_id=? AND archived=0"
    params: list = [ctx.account_id]
    if ctx.program_id:
        sql += " AND id=?"
        params.append(ctx.program_id)
    ctx.programs = [dict(r) for r in ctx.conn.execute(sql + " ORDER BY name", tuple(params))]
    return []


def _adapt_tasks(ctx: _Ctx) -> list[dict]:
    program_ids = ctx.scoped_program_ids()
    if not program_ids:
        return []
    marks = ",".join("?" * len(program_ids))
    out = []
    for row in ctx.conn.execute(
        f"SELECT * FROM tasks WHERE program_id IN ({marks}) AND archived=0 AND status='open'",
        tuple(program_ids),
    ):
        row = dict(row)
        due = row["due_date"]
        # An unowned Task is still eligible. Excluding it would hide real work behind a
        # data-entry gap, so it renders `Unassigned` instead (section 6.1).
        owner = ctx.person(row["internal_owner_id"])
        if due and due < ctx.today:
            code = "overdue_operator_task"
            reason = f"Operator task is {_days(due, ctx.today)} days overdue"
        elif due and due <= ctx.soon:
            code = "operator_task_due_soon"
            reason = f"Operator task is due {_pretty_date(due)}, within {DUE_SOON_DAYS} days"
        else:
            code = "open_operator_work"
            reason = "Open operator task with no due date" if not due else \
                f"Open operator task due {_pretty_date(due)}"
        out.append(_candidate(
            ctx, source_type="task", source_id=row["id"], title=row["description"],
            reason=reason, reason_code=code, updated_at=row["updated_at"],
            recorded_at=row["created_at"], group="you_own", due_date=due, owner=owner,
            program_id=row["program_id"],
            provenance=_source_label(ctx, row, "manual", "Added manually"),
        ))
    return out


def _adapt_commitments(ctx: _Ctx) -> list[dict]:
    sql = ("SELECT * FROM commitments WHERE account_id=? AND archived=0 AND status='open'")
    params: list = [ctx.account_id]
    if ctx.program_id:
        # Account-wide commitments stay visible in a selected program scope (section 7.4).
        sql += " AND (program_id=? OR program_id IS NULL)"
        params.append(ctx.program_id)
    out = []
    for row in ctx.conn.execute(sql, tuple(params)):
        row = dict(row)
        due = row["due_date"]
        owner = ctx.person(row["internal_owner_id"])
        responsible = ctx.person(row["responsible_party_id"])
        customer_owned = row["commitment_class"] == "client" and (
            responsible is None or responsible["party"] == "customer"
        )
        if due < ctx.today:
            code, reason = "overdue_commitment_follow_up", \
                f"Commitment is {_days(due, ctx.today)} days overdue and needs an internal follow-up"
        elif due <= ctx.soon:
            code, reason = "commitment_follow_up_due_soon", \
                f"Commitment is due {_pretty_date(due)}, within {DUE_SOON_DAYS} days"
        else:
            code, reason = "open_operator_work", f"Open commitment due {_pretty_date(due)}"
        out.append(_candidate(
            ctx, source_type="commitment", source_id=row["id"], title=row["description"],
            reason=reason, reason_code=code, updated_at=row["updated_at"],
            recorded_at=row["created_at"],
            # A customer responsibility keeps its internal follow-up owner and stays visible;
            # it is simply never the operator's own next move.
            group="waiting_on_customer" if customer_owned else "you_own",
            due_date=due, owner=owner, responsible_party=responsible,
            program_id=row["program_id"],
            provenance=_source_label(ctx, row, "account_standard", "Account standard"),
        ))
    return out


def _adapt_risks_issues(ctx: _Ctx) -> list[dict]:
    program_ids = ctx.scoped_program_ids()
    if not program_ids:
        return []
    marks = ",".join("?" * len(program_ids))
    out = []
    for table, source_type, open_state, noun in (
        ("risks", "risk", "open", "Risk"), ("issues", "issue", "open", "Issue"),
    ):
        for row in ctx.conn.execute(
            f"SELECT * FROM {table} WHERE program_id IN ({marks}) AND archived=0 AND status=?",
            (*program_ids, open_state),
        ):
            row = dict(row)
            owner = ctx.person(row["internal_owner_id"])
            # Risks and Issues carry no responsible-party field: they are internal records, so
            # every one of them is operator-side. An unowned blocker is still a blocker.
            if row["is_blocker"]:
                code = "operator_blocker"
                reason = f"{noun} is an unresolved blocker" + (
                    "" if owner else " with no internal owner")
            else:
                code, reason = "open_operator_work", f"Open {noun.lower()} on this program"
            out.append(_candidate(
                ctx, source_type=source_type, source_id=row["id"], title=row["description"],
                reason=reason, reason_code=code, updated_at=row["updated_at"],
                recorded_at=row["created_at"], group="you_own", owner=owner,
                program_id=row["program_id"],
                provenance=_source_label(ctx, row, "manual", "Added manually"),
            ))
    return out


def _adapt_milestones(ctx: _Ctx) -> list[dict]:
    program_ids = ctx.scoped_program_ids()
    if not program_ids:
        return []
    marks = ",".join("?" * len(program_ids))
    out = []
    for row in ctx.conn.execute(
        f"SELECT * FROM milestones WHERE program_id IN ({marks}) AND archived=0 "
        "AND status='upcoming'", tuple(program_ids),
    ):
        row = dict(row)
        target = row["target_date"]
        in_window = bool(target) and target <= ctx.lead
        if not in_window and not row["at_risk"]:
            continue
        if row["at_risk"]:
            reason = "Milestone is flagged at risk"
        else:
            reason = (f"Milestone lands {_pretty_date(target)}, inside the "
                      f"{EVENT_LEAD_DAYS}-day preparation window")
        out.append(_candidate(
            ctx, source_type="milestone", source_id=row["id"],
            title=f"Prepare for {row['name']}", reason=reason,
            reason_code="milestone_preparation", updated_at=row["updated_at"],
            recorded_at=row["created_at"], group="you_own", due_date=target,
            program_id=row["program_id"],
            provenance=_source_label(ctx, row, "program_standard", "Program standard"),
        ))
    return out


def _adapt_phase_gates(ctx: _Ctx) -> list[dict]:
    """Incomplete items on the gate for each in-scope program's *current* phase.

    A gate item carries neither owner nor due date, so it always falls to the end of tie-breaks
    2 and 3 — band 2 order is decided almost entirely by stable identity.
    """
    out = []
    for program in ctx.programs:
        gate = ctx.conn.execute(
            "SELECT * FROM phase_gates WHERE program_id=? AND archived=0 AND gates_phase=? "
            "AND status='open' ORDER BY name LIMIT 1", (program["id"], program["phase"]),
        ).fetchone()
        if gate is None:
            continue
        for row in ctx.conn.execute(
            "SELECT * FROM phase_gate_items WHERE gate_id=? AND complete=0 ORDER BY id",
            (gate["id"],),
        ):
            row = dict(row)
            out.append(_candidate(
                ctx, source_type="phase_gate_item", source_id=row["id"],
                title=row["description"],
                reason=(f"Incomplete item on the {PHASE_LABELS.get(program['phase'], program['phase'])} "
                        f"gate “{gate['name']}”"),
                reason_code="current_gate_item", updated_at=row["updated_at"],
                recorded_at=row["created_at"], group="you_own", program_id=program["id"],
                phase=gate["gates_phase"],
                provenance={"kind": "program_standard", "label": "Program standard",
                            "interaction_id": None},
            ))
    return out


def _adapt_deployment_moments(ctx: _Ctx) -> list[dict]:
    program_ids = ctx.scoped_program_ids()
    if not program_ids:
        return []
    marks = ",".join("?" * len(program_ids))
    out = []
    for row in ctx.conn.execute(
        f"SELECT * FROM deployment_moments WHERE program_id IN ({marks}) AND archived=0 "
        "AND outcome IS NULL AND event_date IS NOT NULL AND event_date<=? AND event_date>=?",
        (*program_ids, ctx.lead, ctx.today),
    ):
        row = dict(row)
        out.append(_candidate(
            ctx, source_type="deployment_moment", source_id=row["id"],
            title=f"Prepare for {row['name']}",
            reason=(f"Confirmed moment on {_pretty_date(row['event_date'])}, inside the "
                    f"{EVENT_LEAD_DAYS}-day preparation window"),
            reason_code="moment_preparation", updated_at=row["updated_at"],
            recorded_at=row["created_at"], group="you_own", due_date=row["event_date"],
            program_id=row["program_id"],
            provenance={"kind": "program_standard", "label": "Program standard",
                        "interaction_id": None},
        ))
    return out


def _adapt_contract_dates(ctx: _Ctx) -> list[dict]:
    """Notice, procurement, and decision preparation inside the lead window the contract configures.

    The windows come from the record (`notice_period_days`, `procurement_lead_days`, the operator
    overlay decision date), never from a constant here.
    """
    row = ctx.conn.execute(
        "SELECT * FROM contract_versions WHERE account_id=? AND archived=0 AND is_current=1 "
        "ORDER BY created_at DESC LIMIT 1", (ctx.account_id,),
    ).fetchone()
    if row is None:
        return []
    row = dict(row)
    windows: list[tuple[str, str]] = []
    if row["renewal_date"]:
        if row["notice_period_days"]:
            windows.append((_shift(row["renewal_date"], -int(row["notice_period_days"])),
                            f"notice is due {row['notice_period_days']} days before renewal"))
        if row["procurement_lead_days"]:
            windows.append((_shift(row["renewal_date"], -int(row["procurement_lead_days"])),
                            f"procurement needs {row['procurement_lead_days']} days of lead time"))
    if row["overlay_expected_decision_date"]:
        windows.append((row["overlay_expected_decision_date"],
                        "the recorded expected decision date"))
    open_windows = [(start, why) for start, why in windows if start <= ctx.today]
    if not open_windows:
        return []
    start, why = min(open_windows)
    deadline = row["renewal_date"] or row["overlay_expected_decision_date"]
    if deadline and deadline < ctx.today:
        return []
    return [_candidate(
        ctx, source_type="contract_version", source_id=row["id"],
        title=f"Prepare the {row['version_label']} renewal decision",
        reason=f"Inside the contract lead window — {why}",
        reason_code="contract_decision_window", updated_at=row["updated_at"],
        recorded_at=row["created_at"], group="you_own", due_date=deadline,
        provenance={"kind": "contract", "label": "From the current contract",
                    "interaction_id": None},
    )]


def _adapt_latest_interaction(ctx: _Ctx) -> list[dict]:
    """The latest meaningful interaction in scope. Its accepted actions are matched, not inferred."""
    sql = ("SELECT * FROM interactions WHERE account_id=? AND archived=0 AND meaningful_touch=1")
    params: list = [ctx.account_id]
    if ctx.program_id:
        sql += " AND (program_id=? OR program_id IS NULL)"
        params.append(ctx.program_id)
    row = ctx.conn.execute(
        sql + " ORDER BY occurred_on DESC, COALESCE(occurred_at_time,'') DESC, id DESC LIMIT 1",
        tuple(params),
    ).fetchone()
    if row is None:
        return []
    row = dict(row)
    ctx.latest_interaction = {
        "interaction_id": row["id"],
        # The title names the kind of touch; the operator's own summary stays intact beside it
        # rather than being truncated into a heading.
        "title": (row["type"] or "interaction").replace("_", " ").capitalize(),
        "summary": row["summary"],
        "occurred_on": row["occurred_on"],
        "occurred_at_time": row["occurred_at_time"],
        "native_target": _target("interaction", row["id"]),
        "accepted_actions": [],
    }
    return []


def _adapt_readiness(ctx: _Ctx) -> dict:
    """Readiness passes through in its own vocabulary; Account Path does not restate it.

    Its four axes stay independent and its coverage stays its own — a pillar the app could not
    evaluate says nothing about whether the Task list is complete.
    """
    return readiness.evaluate(ctx.conn, ctx.account_id, ctx.program_id)


def _requirement_rows(ctx: _Ctx, readiness_result: dict | None) -> dict:
    """Slice 3 (§13.6) — readiness readings with the plan layer's due dates beside them.

    Three separations are load-bearing here and none of them is cosmetic:

    - **A due date never moves a state.** It is carried alongside the four readiness axes and is
      allowed to say `overdue`, which is a statement about the plan, not about the evidence.
    - **`met` + `stale` is not a gap.** Freshness stays visible on a met requirement, but only
      `state` decides whether something is outstanding. Folding the two would invent work.
    - **A suggestion is not work.** Suggested actions ride on the requirement row and never enter
      `you_own`; the eight bands rank canonical records only.
    """
    plan = playbooks.merged_plan(ctx.conn, ctx.account_id, ctx.program_id, readiness_result)
    by_key = {}
    for row in plan["requirements"]:
        by_key[(row["scope"]["program_id"], row["requirement_key"])] = row

    readings = playbooks._readiness_readings(readiness_result or {})
    suggestions = _pillar_suggestions(readiness_result)
    linked = _requirement_action_links(ctx)

    out: list[dict] = []
    seen: set[tuple[str | None, str]] = set()
    for (program_id, key), reading in readings.items():
        if reading["requirement_key"] is None:
            continue  # a whole-pillar answer; it has no requirement identity to schedule
        instance = _instance_for(ctx, by_key, program_id, key)
        out.append(_requirement_row(ctx, reading, instance, suggestions, linked))
        seen.add((program_id, key))
        if instance is not None:
            seen.add(((instance["scope"] or {}).get("program_id"), key))
    for (program_id, key), instance in by_key.items():
        # Scheduled but unread: a legacy pin, or a pillar readiness declined to evaluate. It is
        # listed with no state rather than dropped, because a silently missing requirement reads
        # as one nobody planned.
        if (program_id, key) in seen or (None, key) in seen:
            continue
        out.append(_requirement_row(ctx, None, instance, suggestions, linked))

    out.sort(key=_requirement_sort_key)
    gaps = [r for r in out if r["is_gap"]]
    return {
        "requirements": out,
        "gaps": gaps,
        "current_phase_gaps": [r for r in gaps if r["current_phase"]],
        "counts": {"total": len(out), "gaps": len(gaps),
                   "current_phase_gaps": len([r for r in gaps if r["current_phase"]]),
                   "stale_but_met": len([r for r in out
                                         if r["state"] == "met" and r["freshness"] == "stale"]),
                   "suppressed": len([r for r in out if r["applicability_override"]]),
                   "waived": len([r for r in out if r["waiver"]])},
        "legacy_items": checklist_compatibility.legacy_items(ctx.conn, ctx.account_id,
                                                             ctx.program_id),
        "plans": playbooks.list_plans(ctx.conn, ctx.account_id, ctx.program_id)["plans"],
    }


def _instance_for(ctx: _Ctx, by_key: dict, program_id: str | None, key: str) -> dict | None:
    """Match a readiness reading to the plan instance that scheduled it.

    In a selected program scope readiness reports every pillar under that one program, so a reading
    with no program of its own still belongs to it. In all-programs scope it does not, and the
    account fallback is the only one allowed — matching an account-scoped reading to some
    program's instance there would put one program's due date on another program's condition.
    """
    scopes = [program_id]
    if program_id is not None:
        scopes.append(None)
    elif ctx.program_id:
        scopes.append(ctx.program_id)
    for scope in scopes:
        hit = by_key.get((scope, key))
        if hit is not None:
            return hit
    return None


# `state` decides what is outstanding. `not_applicable` and `met` are settled; `not_due` never
# reaches here because readiness reports it as applicability, not as a state.
GAP_STATES = {"conflicted": 0, "unknown": 1, "thin": 2}


def _requirement_sort_key(row: dict) -> tuple:
    return (
        0 if row["is_gap"] else 1,
        0 if row["current_phase"] else 1,
        0 if row["applicability"] == "required" else 1,
        GAP_STATES.get(row["state"], 9),
        0 if row["due_date"] else 1,
        row["due_date"] or "",
        row["pillar_key"] or "",
        row["requirement_key"],
    )


def _requirement_row(ctx: _Ctx, reading: dict | None, instance: dict | None,
                     suggestions: dict, linked: dict) -> dict:
    reading = reading or {}
    instance = instance or {}
    key = reading.get("requirement_key") or instance.get("requirement_key")
    # The plan's own scope wins when there is one: it is a recorded fact about where the
    # requirement was scheduled, where the reading's scope is an artefact of how it was queried.
    program_id = ((instance.get("scope") or {}).get("program_id")
                  or reading.get("program_id"))
    pillar_key = reading.get("pillar_key") or instance.get("pillar_key")
    # Suggestions are keyed by the scope readiness answered in, which is not always the scope the
    # plan scheduled in. Looking them up by the display scope would silently drop them.
    suggestion_scope = reading.get("program_id")
    state = reading.get("state")
    applicability = reading.get("applicability")
    due_date = instance.get("due_date")
    link = linked.get((program_id, key))
    is_gap = (
        state in GAP_STATES
        and applicability == "required"
        and not reading.get("applicability_override")
        and not reading.get("waiver")
        # §13.6: a requirement whose next step is already a linked native record is that record's
        # work, not a second copy of it. Until Slice 5 stores the link this set is empty, and an
        # empty set is the honest answer — matching on labels is exactly what §13.5.2 forbids.
        and link is None
    )
    return {
        "id": f"requirement:{program_id or 'account'}:{key}",
        "requirement_key": key,
        "requirement_version": reading.get("requirement_version")
        or instance.get("requirement_version"),
        "label": reading.get("label") or instance.get("label"),
        "definition_of_done": reading.get("definition_of_done")
        or instance.get("definition_of_done"),
        "pillar_key": pillar_key,
        "pillar_label": reading.get("pillar_label") or instance.get("pillar_label"),
        # Four independent axes, never merged into a badge (RELATIONSHIP-READINESS-SPEC.md §3.4).
        "state": state,
        "freshness": reading.get("freshness"),
        "applicability": applicability,
        "assessed_through": reading.get("assessed_through"),
        "provenance": reading.get("provenance"),
        "reason": reading.get("reason") or instance.get("reason"),
        "evidence": reading.get("evidence") or [],
        "missing": reading.get("missing") or [],
        "applicability_override": reading.get("applicability_override"),
        "waiver": reading.get("waiver"),
        "evaluated": bool(reading.get("evaluated")),
        "legacy": bool(instance.get("legacy")),
        # Plan layer. Present only when a playbook actually schedules this requirement.
        "instance_id": instance.get("instance_id"),
        "necessity": instance.get("necessity"),
        "due_date": due_date,
        "due_rule": instance.get("due_rule"),
        "overdue": bool(due_date and due_date < ctx.today and state != "met"),
        "recorded_complete": bool(instance.get("recorded_complete")),
        "recorded_complete_on": instance.get("recorded_complete_on"),
        "compatibility_source": instance.get("compatibility_source"),
        "playbook": instance.get("playbook"),
        "program_id": program_id,
        "program_name": reading.get("program_name") or ctx.program_name(program_id),
        "scope_label": "Account-wide" if program_id is None else "Program",
        "current_phase": applicability == "required",
        "is_gap": is_gap,
        "linked_action": link,
        # Kept separate from canonical work on purpose: this is a proposal for a Task, not a Task.
        "suggested_action": suggestions.get((suggestion_scope, pillar_key)),
        "create_action_prefill": _create_action_prefill(ctx, reading, instance, suggestions,
                                                        suggestion_scope, pillar_key,
                                                        program_id),
    }


def _pillar_suggestions(readiness_result: dict | None) -> dict:
    out: dict[tuple[str | None, str], dict] = {}
    if not readiness_result:
        return out
    for pillar in readiness_result.get("pillars", []):
        if pillar.get("suggested_action"):
            out[(None, pillar["key"])] = pillar["suggested_action"]
    for entry in readiness_result.get("programs", []):
        for pillar in entry.get("pillars", []):
            if pillar.get("suggested_action"):
                out[(entry.get("program_id"), pillar["key"])] = pillar["suggested_action"]
    return out


def _create_action_prefill(ctx: _Ctx, reading: dict, instance: dict, suggestions: dict,
                           suggestion_scope: str | None, pillar_key: str | None,
                           program_id: str | None) -> dict | None:
    """§13.8 — what a native Task form opens with. Every field stays editable.

    `linked` is false because it describes *this suggestion*, which has not been acted on. Slice 5
    stores the requirement-action link and the panel now creates one on save, but the suggestion
    itself is still a proposal: it stays out of the ranked queue, and flipping this to true would
    claim a relationship that does not exist until somebody saves the form.
    """
    suggestion = suggestions.get((suggestion_scope, pillar_key))
    if not suggestion:
        return None
    label = reading.get("label") or instance.get("label") or ""
    return {
        "record_type": suggestion.get("record_type", "task"),
        "title": suggestion.get("title") or (f"Close the {label} gap" if label else None),
        "detail": suggestion.get("detail") or reading.get("definition_of_done"),
        "program_id": program_id,
        "due_date": instance.get("due_date"),
        "requirement_key": reading.get("requirement_key") or instance.get("requirement_key"),
        "linked": False,
        "link_note": "Saving creates the native record and links it to this condition as "
                     "'advances'. The link is a relationship, not evidence — closing the action "
                     "does not set a state.",
    }


def _requirement_action_links(ctx: _Ctx) -> dict:
    """The requirement→native-action links §13.6 dedupes against.

    Slice 5 stores them, and only an explicit `advances` link counts — a `blocks` link is the
    reason a requirement is stuck and a `follow_up_for` link is downstream of it, so neither means
    "this requirement's work is already represented by a record". Matching on labels remains
    forbidden (§13.5.2); an unlinked requirement stays a gap until an operator says otherwise.
    """
    return path_links.requirement_action_index(ctx.conn, ctx.account_id)


def _gate_impact(ctx: _Ctx) -> dict:
    """`(source_type, source_id) -> the open gate this action helps unblock` (§15.8).

    Three narrowings, each removing a way the claim could be untrue: the relation must be
    `advances` (a `blocks` link is the opposite claim), the gate must still be `open` (unblocking a
    passed gate is not news), and the gate must be for the program's *current* phase (a future
    phase's gate is not what is in the way today).
    """
    out: dict[tuple[str, str], dict] = {}
    if not ctx.programs:
        return out
    marks = ",".join("?" for _ in ctx.programs)
    rows = ctx.conn.execute(
        f"SELECT l.task_id, l.commitment_id, pg.name AS gate_name, pg.gates_phase "
        f"FROM readiness_requirement_action_links l "
        f"JOIN gate_requirement_links g "
        f"  ON g.plan_instance_id = l.plan_instance_id AND g.archived = 0 "
        f"  AND g.necessity = 'required' "
        f"JOIN phase_gates pg ON pg.id = g.gate_id AND pg.archived = 0 AND pg.status = 'open' "
        f"JOIN programs p ON p.id = pg.program_id AND p.phase = pg.gates_phase "
        f"WHERE l.archived = 0 AND l.relation = 'advances' AND p.id IN ({marks})",
        tuple(p["id"] for p in ctx.programs),
    ).fetchall()
    for row in rows:
        key = ("task", row["task_id"]) if row["task_id"] else ("commitment", row["commitment_id"])
        phase = PHASE_LABELS.get(row["gates_phase"], row["gates_phase"])
        out.setdefault(key, {"gate_name": row["gate_name"], "gates_phase": row["gates_phase"],
                             "label": f"{phase} gate “{row['gate_name']}”"})
    return out


def _adapt_checklists(ctx: _Ctx) -> list[dict]:
    """Open checklist items, as a *supplement* below readiness.

    `checklist_items.section` is time from kickoff (`first_call` … `first_90_days`), not a program
    phase, so a checklist item cannot answer "is this required in the current phase" and is never
    labeled a current-phase requirement.
    """
    sql = "SELECT * FROM checklist_items WHERE account_id=? AND archived=0 AND status='open'"
    params: list = [ctx.account_id]
    if ctx.program_id:
        sql += " AND (program_id=? OR program_id IS NULL)"
        params.append(ctx.program_id)
    order = {"first_call": 0, "first_two_weeks": 1, "first_30_days": 2, "first_90_days": 3}
    rows = [dict(r) for r in ctx.conn.execute(sql, tuple(params))]
    rows.sort(key=lambda r: (order.get(r["section"], 9), r["due_date"] or "9999-12-31", r["id"]))
    return [{
        "id": f"checklist_item:{r['id']}",
        "source_type": "checklist_item",
        "source_id": r["id"],
        "title": r["label"],
        "detail": r["detail"],
        "section": r["section"],
        "due_date": r["due_date"],
        "overdue": bool(r["due_date"] and r["due_date"] < ctx.today),
        "program_id": r["program_id"],
        "program_name": ctx.program_name(r["program_id"]),
        "scope_label": "Account-wide" if r["program_id"] is None else "Program",
        "source_label": "Standard onboarding requirement",
        "native_target": _target("checklist_item", r["id"]),
        # Lets the UI and the Slice 3 migration tell a compatibility-period requirement from a
        # readiness one. A checkbox is not evidence and never reaches a readiness state.
        "compatibility_source": True,
    } for r in rows]


# --- program path ---------------------------------------------------------------------------

def _program_path(ctx: _Ctx, program: dict, blockers: list[dict]) -> dict:
    """Derived, never advanced. Honest `unknown` beats reconstructed history."""
    current = program["phase"]
    current_index = PHASE_ORDER.index(current) if current in PHASE_ORDER else None
    gates = {}
    for row in ctx.conn.execute(
        "SELECT * FROM phase_gates WHERE program_id=? AND archived=0 ORDER BY created_at",
        (program["id"],),
    ):
        gates.setdefault(row["gates_phase"], dict(row))
    incomplete = {}
    for phase, gate in gates.items():
        incomplete[phase] = ctx.conn.execute(
            "SELECT COUNT(*) c FROM phase_gate_items WHERE gate_id=? AND complete=0", (gate["id"],)
        ).fetchone()["c"]

    program_blockers = [b for b in blockers if b["program_id"] == program["id"]]
    steps = []
    for index, phase in enumerate(PHASE_ORDER):
        gate = gates.get(phase)
        blocking_reason = None
        if current_index is None:
            state = "unknown"
        elif index < current_index:
            # A missing gate never implies completion. Without a governed record we say so.
            if gate is None:
                state = "unknown"
            elif gate["status"] == "waived":
                state = "waived"
                blocking_reason = gate["waiver_reason"]
            elif gate["status"] == "passed":
                state = "complete"
            else:
                state = "unknown"
        elif index == current_index:
            if program_blockers:
                state = "blocked"
                blocking_reason = program_blockers[0]["title"]
            else:
                # An open gate or an incomplete item means the phase is current, not blocked.
                state = "current"
        else:
            state = "future"
        if phase == "closed" and current != "closed":
            state = "not_applicable"
        steps.append({
            "key": phase,
            "label": PHASE_LABELS[phase],
            "state": state,
            "target_date": None,
            "gate_id": gate["id"] if gate else None,
            "gate_status": gate["status"] if gate else None,
            "missing_count": incomplete.get(phase, 0) if gate else 0,
            "blocking_reason": blocking_reason,
        })

    next_gate = None
    gate = gates.get(current)
    if gate and gate["status"] == "open":
        next_gate = {
            "gate_id": gate["id"], "name": gate["name"], "phase": current,
            "missing_count": incomplete.get(current, 0),
            "native_target": _target("phase_gate", gate["id"]),
        }
    milestone = ctx.conn.execute(
        "SELECT * FROM milestones WHERE program_id=? AND archived=0 AND status='upcoming' "
        "ORDER BY (target_date IS NULL), target_date, id LIMIT 1", (program["id"],),
    ).fetchone()
    next_milestone = None
    if milestone is not None:
        next_milestone = {
            "milestone_id": milestone["id"], "name": milestone["name"],
            "target_date": milestone["target_date"], "at_risk": bool(milestone["at_risk"]),
            "native_target": _target("milestone", milestone["id"]),
        }
    return {
        "program_id": program["id"],
        "program_name": program["name"],
        "current_phase": current,
        "steps": steps,
        "next_gate": next_gate,
        "next_milestone": next_milestone,
    }


# --- assembly -------------------------------------------------------------------------------

def _sort_key(candidate: dict) -> tuple:
    """Section 10.5: band, then due date (missing last), then recorded time, then stable identity."""
    due = candidate["due_date"]
    return (candidate["band"], 0 if due else 1, due or "", candidate["_recorded_at"],
            candidate["id"])


def _empty_state(ctx: _Ctx, work: dict, coverage_ok: bool, readiness_result: dict | None) -> dict:
    """One explicit state, never a silent blank (section 6.1)."""
    # Coverage first, because `ctx.programs == []` has two causes and only one of them is a fact.
    # The adapter harness leaves it empty when `_adapt_programs` raises, so reading it as "nothing
    # is planned" would state a positive claim about the account's records on the strength of a
    # failed read — and it would do so by shadowing `coverage_incomplete`, the one variant written
    # for exactly this case.
    if not coverage_ok and not ctx.programs:
        return {"variant": "coverage_incomplete",
                "message": "Some sources could not be read, so caught-up cannot be claimed.",
                "requirement": None}
    if not ctx.programs:
        return {"variant": "insufficient_plan_data",
                "message": "No program, phase, gate, or milestone is recorded for this account.",
                "requirement": None}
    if work["waiting_on_customer"]:
        return {"variant": "waiting_on_customer",
                "message": "No operator-owned action is due. A customer responsibility is open.",
                "requirement": None}
    gap = _earliest_required_gap(readiness_result)
    if gap is not None:
        return {"variant": "prepare_for_next_gate",
                "message": "Nothing is urgent. The earliest incomplete condition for this phase is below.",
                "requirement": gap}
    if not coverage_ok:
        return {"variant": "coverage_incomplete",
                "message": "Some sources could not be read, so caught-up cannot be claimed.",
                "requirement": None}
    return {"variant": "caught_up",
            "message": "Required current work is complete and no near-term event needs preparation.",
            "requirement": None}


def _earliest_required_gap(readiness_result: dict | None) -> dict | None:
    """The `Prepare for the next gate` candidate: a required condition that is not yet met.

    It is a suggestion, not work. It never enters `you_own`, and turning it into a Task is the
    governed `Create action` step, not something this projection does.
    """
    if not readiness_result:
        return None
    pillars = list(readiness_result.get("pillars", []))
    for entry in readiness_result.get("programs", []):
        for pillar in entry.get("pillars", []):
            pillars.append({**pillar, "program_id": entry.get("program_id"),
                            "program_name": entry.get("program_name")})
    order = {"conflicted": 0, "unknown": 1, "thin": 2}
    gaps = [p for p in pillars
            if p.get("applicability") == "required" and p.get("state") in order]
    if not gaps:
        return None
    gaps.sort(key=lambda p: (order[p["state"]], p["key"]))
    gap = gaps[0]
    return {
        "pillar_key": gap["key"],
        "label": gap["label"],
        "state": gap["state"],
        "freshness": gap.get("freshness"),
        "applicability": gap.get("applicability"),
        "scope": gap.get("scope"),
        "reason": gap.get("reason"),
        "program_id": gap.get("program_id"),
        "program_name": gap.get("program_name"),
        "suggested_action": gap.get("suggested_action"),
    }


def build_execution_path(conn: sqlite3.Connection, account_id: str, *,
                         program_id: str | None = None,
                         ranking_version: str | None = None) -> dict:
    """The section 10.2 response. Read-only from first statement to last.

    `ranking_version` is the §17.6 feature flag made explicit for the comparison harness. It is
    deliberately not a query parameter: a client that could pick its own ruleset would produce a
    reason sentence the recorded rule version does not explain.
    """
    version = ranking_version or active_ranking_version()
    bands = ranking_bands(version)
    account = conn.execute(
        "SELECT id,name FROM accounts WHERE id=? AND archived=0", (account_id,)
    ).fetchone()
    if account is None:
        raise HTTPException(status_code=404, detail="account not found")
    program = None
    if program_id:
        # An unknown, archived, or foreign program is an error, never a silent fallback to all
        # programs: falling back would answer a different question than the one asked.
        row = conn.execute(
            "SELECT * FROM programs WHERE id=? AND account_id=? AND archived=0",
            (program_id, account_id),
        ).fetchone()
        if row is None:
            raise HTTPException(
                status_code=404,
                detail="program not found on this account (Account Path does not fall back to "
                       "account scope)",
            )
        program = dict(row)

    today = _today()
    ctx = _Ctx(conn, dict(account), program, today, bands=bands)
    omitted: list[dict] = []
    warnings: list[str] = []
    included: list[str] = []
    candidates: list[dict] = []
    readiness_result: dict | None = None
    checklist_rows: list[dict] = []

    def run(name: str, fn):
        nonlocal readiness_result, checklist_rows
        try:
            result = fn(ctx)
        except HTTPException:
            raise
        except Exception as exc:  # one bad adapter must not blank the page
            omitted.append({"source": name, "detail": f"{type(exc).__name__}: {exc}"})
            warnings.append(f"{name} could not be read; its items are missing from this view")
            return
        included.append(name)
        if name == "readiness":
            readiness_result = result
        elif name == "checklists":
            checklist_rows = result
        elif result:
            candidates.extend(result)

    # `programs` first: every other scope query depends on it.
    for name in _ADAPTERS:
        run(name, globals()[f"_adapt_{name}"])

    # Suppression, using the queue's overlays and the queue's resurfacing rules.
    live: list[dict] = []
    suppressed_count = 0
    for candidate in candidates:
        state = queue.suppression_state(
            conn, candidate["_suppression_keys"], candidate["_updated_at"], today,
            overlays=ctx.overlays,
        )
        if state is None:
            live.append(candidate)
        else:
            suppressed_count += 1

    # Dedupe by native identity: a wrapper record never creates a second visible action.
    seen: set[str] = set()
    deduped: list[dict] = []
    for candidate in sorted(live, key=_sort_key):
        if candidate["id"] in seen:
            continue
        seen.add(candidate["id"])
        deduped.append(candidate)

    # Band 7 exists only as a promotion: open work linked to the latest meaningful interaction
    # outranks the rest of the residual pile.
    latest = ctx.latest_interaction
    if latest:
        linked = _interaction_links(ctx, latest["interaction_id"])
        for candidate in deduped:
            # `ctx.bands`, not `BANDS`: under a candidate ruleset (§17.6) the module default would
            # promote the row into a band the rest of this request is not ranking by.
            if candidate["band"] == ctx.bands["open_operator_work"] and \
                    (candidate["source_type"], candidate["source_id"]) in linked:
                candidate["band"] = ctx.bands["latest_interaction_action"]
                candidate["reason_code"] = "latest_interaction_action"
                candidate["reason"] = f"Accepted action from {latest['title']}"
        deduped.sort(key=_sort_key)
        latest["accepted_actions"] = [
            {"id": c["id"], "source_type": c["source_type"], "source_id": c["source_id"],
             "title": c["title"], "due_date": c["due_date"], "urgency": c["urgency"],
             "native_target": c["native_target"]}
            for c in sorted(deduped, key=lambda c: (
                0 if c["reason_code"] == "operator_blocker" else 1,
                0 if c["due_date"] else 1, c["due_date"] or "", c["id"]))
            if (c["source_type"], c["source_id"]) in linked
        ]

    # §15.8 — gate impact, and only from an accepted explicit relation. A Task may say it unblocks
    # the Launch gate when an operator linked it to a requirement that gate depends on, and never
    # because its wording resembles one. The claim is attached after ranking on purpose: it is a
    # reason an item matters, not a new band, and letting it re-rank would put a suggestion-shaped
    # claim above overdue work.
    try:
        impact = _gate_impact(ctx)
        for candidate in deduped:
            hit = impact.get((candidate["source_type"], candidate["source_id"]))
            if hit:
                candidate["gate_impact"] = hit
                candidate["reason"] = f"{candidate['reason']} · Unblocks the {hit['label']}"
    except Exception as exc:
        omitted.append({"source": "gate_impact", "detail": f"{type(exc).__name__}: {exc}"})
        warnings.append("gate relationships could not be read; no gate impact is claimed here")

    # Slice 3's plan layer runs after the adapters because it reads the readiness result. It is
    # guarded the same way they are: a failure here omits the plan layer and leaves every
    # canonical row exactly where it was (§13.9, "failed or partial readiness coverage cannot
    # suppress canonical execution work").
    requirements: dict | None = None
    try:
        requirements = _requirement_rows(ctx, readiness_result)
        included.append("plan_instances")
    except HTTPException:
        raise
    except Exception as exc:
        omitted.append({"source": "plan_instances", "detail": f"{type(exc).__name__}: {exc}"})
        warnings.append("plan instances could not be read; due dates are missing from this view")

    coverage_ok = not omitted
    eligible = [c for c in deduped if c["_group"] == "you_own" and c["_eligible"]]
    next_move = _public(eligible[0]) if eligible else None

    work = {
        "you_own": [_public(c) for c in deduped if c["_group"] == "you_own"],
        "waiting_on_customer": [_public(c) for c in deduped if c["_group"] == "waiting_on_customer"],
        "account_essentials": {
            "readiness": readiness_result,
            # The full in-scope set. The UI shows at most three current-phase gaps and links to
            # the rest (§13.6); truncating here would make `View all` a lie.
            "requirements": requirements,
            "checklist_supplements": checklist_rows,
        },
        "upcoming_gates": _upcoming_gates(ctx),
    }
    program_blockers = [c for c in deduped if c["reason_code"] == "operator_blocker"]
    program_paths = [_program_path(ctx, p, program_blockers) for p in ctx.programs]

    status = "complete" if coverage_ok else ("unavailable" if not included else "partial")
    if suppressed_count:
        # Reads on screen, so it is a sentence rather than a count with a plural in brackets.
        warnings.append(
            f"{suppressed_count} item is snoozed and is not shown here" if suppressed_count == 1
            else f"{suppressed_count} items are snoozed and are not shown here")

    return {
        "stamp": {"data_current_through": now_utc(), "generated_at": now_utc()},
        "scope": {
            "account_id": account_id, "account_name": ctx.account["name"],
            "program_id": program_id,
            "program_name": program["name"] if program else None,
            "mode": "program" if program_id else "all_programs",
        },
        # §17.6 step 7. The client echoes this back on every path event, so a later review can
        # tell which ordering an operator was actually looking at when they opened or skipped a
        # row. Without it, an ordering change silently reinterprets every event recorded before it.
        "ranking_rules": {
            "version": version,
            "status": RANKING_RULE_VERSIONS[version]["status"],
            "summary": RANKING_RULE_VERSIONS[version]["summary"],
            "flag": RANKING_RULE_ENV,
            "available_versions": sorted(RANKING_RULE_VERSIONS),
        },
        "program_paths": program_paths,
        "next_move": next_move,
        "empty_state": None if next_move else _empty_state(ctx, work, coverage_ok, readiness_result),
        "latest_interaction": latest,
        "work": work,
        "integration": {
            # Readiness ships with Slice 1. It falls back to `not_connected` only if its own
            # adapter failed, and that failure can never suppress canonical execution work.
            "pillars": "connected" if readiness_result is not None else "not_connected",
            "plan_instances": "connected" if requirements is not None else "not_connected",
            # §13.8: the durable requirement→action link is Slice 5's table, and it now exists.
            "requirement_actions": "connected",
            "proposed_updates": "not_connected",
        },
        "coverage": {
            "status": status,
            "included_sources": included,
            "omitted_sources": omitted,
            "warnings": warnings,
            # Reported beside execution coverage, never folded into it (§13.6). A pillar the app
            # could not evaluate says nothing about whether the Task list is complete, and one
            # combined number would make each claim unreadable.
            "readiness": (readiness_result or {}).get("coverage"),
        },
    }


def compare_rule_versions(conn: sqlite3.Connection, account_ids: list[str],
                          version_a: str, version_b: str) -> dict:
    """§17.6 step 4: rank the same seeded accounts under two rulesets and diff the ordering.

    Deterministic by construction — it is the same projection twice with a different band map, so
    a difference in output is a difference in the rules and nothing else. It reports the moved
    rows rather than a count, because step 5 asks a person to look at the surprising ones.
    """
    if version_a == version_b:
        raise HTTPException(status_code=422, detail="comparison needs two different versions")
    ranking_bands(version_a), ranking_bands(version_b)  # 404 before doing any work
    accounts = []
    for account_id in account_ids:
        a = build_execution_path(conn, account_id, ranking_version=version_a)
        b = build_execution_path(conn, account_id, ranking_version=version_b)
        order_a = [row["id"] for row in a["work"]["you_own"]]
        order_b = [row["id"] for row in b["work"]["you_own"]]
        positions_a = {row_id: i for i, row_id in enumerate(order_a)}
        moved = [
            {"id": row_id, "from_position": positions_a.get(row_id), "to_position": i,
             "reason_code": next((r["reason_code"] for r in b["work"]["you_own"]
                                  if r["id"] == row_id), None)}
            for i, row_id in enumerate(order_b) if positions_a.get(row_id) != i
        ]
        accounts.append({
            "account_id": account_id,
            "account_name": a["scope"]["account_name"],
            "next_move_changed": (a["next_move"] or {}).get("id") != (b["next_move"] or {}).get("id"),
            "next_move_before": (a["next_move"] or {}).get("id"),
            "next_move_after": (b["next_move"] or {}).get("id"),
            "moved_rows": moved,
        })
    return {
        "version_a": version_a, "version_b": version_b,
        "accounts": accounts,
        "accounts_with_changes": sum(1 for row in accounts
                                     if row["moved_rows"] or row["next_move_changed"]),
    }


def _public(candidate: dict) -> dict:
    """Strip the internal sort and suppression fields; everything else is part of the contract."""
    return {k: v for k, v in candidate.items() if not k.startswith("_")}


def _interaction_links(ctx: _Ctx, interaction_id: str) -> set[tuple[str, str]]:
    """Canonical records linked to an interaction. Body text is never mined for actions here."""
    links: set[tuple[str, str]] = set()
    for table, source_type in (
        ("tasks", "task"), ("commitments", "commitment"), ("milestones", "milestone"),
        ("risks", "risk"), ("issues", "issue"),
    ):
        for row in ctx.conn.execute(
            f"SELECT id FROM {table} WHERE source_interaction_id=? AND archived=0",
            (interaction_id,),
        ):
            links.add((source_type, row["id"]))
    return links


def _upcoming_gates(ctx: _Ctx) -> list[dict]:
    out = []
    for program in ctx.programs:
        for row in ctx.conn.execute(
            "SELECT * FROM phase_gates WHERE program_id=? AND archived=0 AND status='open' "
            "ORDER BY name", (program["id"],),
        ):
            missing = ctx.conn.execute(
                "SELECT COUNT(*) c FROM phase_gate_items WHERE gate_id=? AND complete=0",
                (row["id"],),
            ).fetchone()["c"]
            out.append({
                "gate_id": row["id"], "name": row["name"], "phase": row["gates_phase"],
                "program_id": program["id"], "program_name": program["name"],
                "is_current_phase": row["gates_phase"] == program["phase"],
                "missing_count": missing,
                "native_target": _target("phase_gate", row["id"]),
            })
    out.sort(key=lambda g: (0 if g["is_current_phase"] else 1,
                            PHASE_ORDER.index(g["phase"]) if g["phase"] in PHASE_ORDER else 9,
                            g["name"]))
    return out
