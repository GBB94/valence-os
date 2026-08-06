"""Account Path Slice 5 — gate readiness and governed phase advancement.

`ACCOUNT-PATH-SPEC.md` §15.5–§15.6. Two operations that look like one and are deliberately not:

- **Reading** recomputes, from live records, whether the approved gate contract is satisfied. It
  writes nothing, including nothing that would make a second read disagree with the first.
- **Advancing** is a separate, explicit command. `ready` never advances anything (§15.9). Opening
  the Account Path never advances anything. The only thing that moves a program's phase is an
  operator asking for it, with the exact readiness answer they were shown in their hand.

The stamp is what makes the second point enforceable. It is a digest of the material content of a
readiness answer — states, gate statuses, blockers, coverage — so a transition submitted against an
answer that has since changed is refused rather than applied to a situation nobody reviewed. It is
recomputed on every read and stored only inside the append-only history, where it is a record of
what the operator saw and never a cached verdict.

One asymmetry is intentional and easy to get backwards: a clean advance marks the gate passed,
because its conditions were met. An **override does not**, because they were not. The gap survives
the transition, which is the whole difference between advancing anyway and pretending.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3

from fastapi import HTTPException

from . import audit, playbooks, readiness
from .db import new_id, now_utc

# The approved phase graph, in order. Normal advancement is one step along it (§15.6).
PHASE_ORDER = ("foundation", "launch", "programmatic", "expansion", "renewal", "closed")
PHASE_LABELS = {
    "foundation": "Foundation", "launch": "Launch", "programmatic": "Programmatic",
    "expansion": "Expansion", "renewal": "Renewal", "closed": "Closed",
}
READINESS_STATES = ("passed", "ready", "blocked", "insufficient_data")
OUTCOMES = ("proposed", "completed", "waived", "rejected")
MIN_REASON_LENGTH = playbooks.MIN_REASON_LENGTH

# States that leave a required condition outstanding. `met` is the only one that does not, and
# `not_applicable` is not a gap because the question was withdrawn, not answered.
_GAP_STATES = ("thin", "unknown", "conflicted")


def _program(conn: sqlite3.Connection, program_id: str) -> dict:
    row = conn.execute("SELECT * FROM programs WHERE id = ? AND archived = 0",
                       (program_id,)).fetchone()
    if row is None:
        raise HTTPException(404, "program not found")
    return dict(row)


def _next_phase(phase: str) -> str | None:
    index = PHASE_ORDER.index(phase) if phase in PHASE_ORDER else None
    if index is None or index + 1 >= len(PHASE_ORDER):
        return None
    return PHASE_ORDER[index + 1]


def _stamp(payload: dict) -> str:
    """A digest of the material answer, not of the whole response.

    Deliberately excludes prose, labels, and evidence lists: those change when a description is
    edited, and refusing a transition because someone fixed a typo would train operators to
    resubmit without rereading, which is the opposite of what the check is for.
    """
    material = {
        "phase": payload["current_phase"],
        "next": payload["proposed_next_phase"],
        "readiness": payload["readiness"],
        "coverage": payload["coverage"],
        "gates": sorted((g["id"], g["status"]) for g in payload["gates"]),
        "gate_items": sorted(i["id"] for i in payload["open_gate_items"]),
        "requirements": sorted(
            (r["requirement_key"], str(r["state"]), str(r["freshness"]),
             str(r["applicability"]), r["necessity"])
            for r in payload["requirements"]
        ),
        "blockers": sorted((b["type"], b["id"]) for b in payload["blocking_records"]),
        "as_of": payload["as_of"],
    }
    digest = hashlib.sha256(json.dumps(material, sort_keys=True).encode("utf-8")).hexdigest()
    return f"pr1:{digest[:32]}"


def phase_readiness(conn: sqlite3.Connection, program_id: str, as_of: str | None = None) -> dict:
    """§15.5. Whether this program's current-phase gate contract is satisfied. Writes nothing."""
    program = _program(conn, program_id)
    account_id = program["account_id"]
    as_of = as_of or now_utc()[:10]
    result = readiness.evaluate(conn, account_id, program_id, as_of=as_of)
    merged = playbooks.merged_plan(conn, account_id, program_id, readiness_result=result)
    by_instance = {row["instance_id"]: row for row in merged["requirements"]}

    gates = [dict(r) for r in conn.execute(
        "SELECT * FROM phase_gates WHERE program_id = ? AND gates_phase = ? AND archived = 0 "
        "ORDER BY name", (program_id, program["phase"]),
    )]
    gate_ids = [g["id"] for g in gates]

    # --- linked requirements ---------------------------------------------------------------------
    requirements: list[dict] = []
    coverage_failures: list[str] = []
    evaluator_versions: list[dict] = []
    if gate_ids:
        marks = ",".join("?" for _ in gate_ids)
        for row in conn.execute(
            f"SELECT l.*, pg.name AS gate_name FROM gate_requirement_links l "
            f"JOIN phase_gates pg ON pg.id = l.gate_id "
            f"WHERE l.gate_id IN ({marks}) AND l.archived = 0 ORDER BY l.created_at",
            tuple(gate_ids),
        ):
            row = dict(row)
            reading = by_instance.get(row["plan_instance_id"])
            if reading is None:
                # The plan instance was archived after the gate linked it. Reported, never
                # silently dropped: a gate quietly losing a condition is how a gate passes for
                # the wrong reason.
                coverage_failures.append(f"gate_requirement:{row['plan_instance_id']}")
                requirements.append({
                    "link_id": row["id"], "gate_id": row["gate_id"],
                    "gate_name": row["gate_name"], "plan_instance_id": row["plan_instance_id"],
                    "requirement_key": None, "label": "Unavailable requirement",
                    "necessity": row["necessity"], "state": None, "freshness": None,
                    "applicability": None, "reason": (
                        "This gate references a plan instance that is no longer live, so no "
                        "state can be read for it."
                    ), "missing": [], "evidence": [], "evaluator_key": None,
                    "evaluator_version": None, "is_gap": True, "available": False,
                })
                continue
            state = reading.get("state")
            necessity = row["necessity"]
            is_gap = (
                necessity == "required"
                and reading.get("applicability") != "not_applicable"
                and not reading.get("waiver")
                and (state is None or state in _GAP_STATES)
            )
            requirements.append({
                "link_id": row["id"], "gate_id": row["gate_id"], "gate_name": row["gate_name"],
                "plan_instance_id": row["plan_instance_id"],
                "requirement_key": reading.get("requirement_key"),
                "label": reading.get("label"),
                "definition_of_done": reading.get("definition_of_done"),
                "necessity": necessity,
                # Four independent axes, carried verbatim. Gate readiness never restates one of
                # them in its own words (§10.4 of the path spec).
                "state": state, "freshness": reading.get("freshness"),
                "applicability": reading.get("applicability"),
                "reason": reading.get("reason"),
                "missing": reading.get("missing") or [],
                "evidence": reading.get("evidence") or [],
                "waiver": reading.get("waiver"),
                "applicability_override": reading.get("applicability_override"),
                "due_date": reading.get("due_date"),
                "evaluator_key": reading.get("evaluator_key"),
                "evaluator_version": reading.get("evaluator_version"),
                "is_gap": is_gap, "available": True,
            })
            if reading.get("evaluator_key"):
                evaluator_versions.append({
                    "requirement_key": reading.get("requirement_key"),
                    "evaluator_key": reading["evaluator_key"],
                    "evaluator_version": reading.get("evaluator_version"),
                })

    # Read from the response's own coverage block, not from the pillars. `readiness.evaluate`
    # pops each pillar's `coverage_failures` as it collects them, so a per-pillar read here would
    # always find nothing and every gate would report `coverage: complete` no matter how many
    # evaluators were unreadable.
    coverage_failures.extend((result.get("coverage") or {}).get("failed_evaluators") or [])

    # --- open linked actions ---------------------------------------------------------------------
    instance_ids = [r["plan_instance_id"] for r in requirements]
    open_actions: list[dict] = []
    if instance_ids:
        marks = ",".join("?" for _ in instance_ids)
        for row in conn.execute(
            f"SELECT * FROM readiness_requirement_action_links "
            f"WHERE plan_instance_id IN ({marks}) AND archived = 0 ORDER BY created_at",
            tuple(instance_ids),
        ):
            row = dict(row)
            kind = "task" if row["task_id"] else "commitment"
            table = "tasks" if kind == "task" else "commitments"
            record = conn.execute(
                f"SELECT id, description, status, due_date FROM {table} "
                f"WHERE id = ? AND archived = 0 AND status = 'open'",
                (row["task_id"] or row["commitment_id"],),
            ).fetchone()
            if record is None:
                continue
            open_actions.append({
                "type": kind, "id": record["id"], "description": record["description"],
                "due_date": record["due_date"], "relation": row["relation"],
                "plan_instance_id": row["plan_instance_id"],
            })

    # --- blockers and legacy gate items ------------------------------------------------------------
    blocking: list[dict] = []
    for table, kind in (("risks", "risk"), ("issues", "issue")):
        for row in conn.execute(
            f"SELECT id, description FROM {table} "
            f"WHERE program_id = ? AND archived = 0 AND status = 'open' AND is_blocker = 1 "
            f"ORDER BY created_at", (program_id,),
        ):
            blocking.append({"type": kind, "id": row["id"], "description": row["description"]})

    open_items: list[dict] = []
    if gate_ids:
        marks = ",".join("?" for _ in gate_ids)
        for row in conn.execute(
            f"SELECT id, gate_id, description FROM phase_gate_items "
            f"WHERE gate_id IN ({marks}) AND complete = 0 ORDER BY id", tuple(gate_ids),
        ):
            open_items.append({"id": row["id"], "gate_id": row["gate_id"],
                               "description": row["description"]})

    # --- missing and stale evidence ----------------------------------------------------------------
    missing_evidence = [
        {"requirement_key": r["requirement_key"], "label": r["label"], "missing": r["missing"]}
        for r in requirements if r["missing"]
    ]
    stale_evidence = [
        {"requirement_key": r["requirement_key"], "label": r["label"],
         "freshness": r["freshness"], "reason": r["reason"]}
        for r in requirements if r["freshness"] == "stale"
    ]

    # --- the verdict -------------------------------------------------------------------------------
    gate_open = [g for g in gates if g["status"] == "open"]
    unmet = [r for r in requirements if r["is_gap"]]
    coverage = "complete" if not coverage_failures else "partial"
    # A gap nobody could evaluate is not the same fact as a gap the records established, and
    # `blocked` claims the second one. Separating them keeps `blocked` meaning "we read this and
    # it is not satisfied" rather than "something went wrong while reading it".
    #
    # Classify on the row's own `available` flag rather than re-deriving unreadability from
    # `coverage_failures`: that list carries two vocabularies — bare evaluator keys from
    # `readiness.evaluate`, and `gate_requirement:<instance_id>` from the archived-instance branch
    # above — and a membership test can only understand one of them. The row that branch builds
    # carries `state: None` and `evaluator_key: None`, so it failed both conjuncts and landed in
    # `determined`. That is not a rare input: `playbooks.instantiate` archives *every* instance of
    # a superseded plan, so one ordinary playbook upgrade turned every gate link on the program
    # into a `blocked` verdict claiming conditions were read and found unsatisfied.
    unreadable_keys = set(coverage_failures)
    unreadable = [r for r in unmet
                  if not r["available"]
                  or (r["state"] == "unknown" and r.get("evaluator_key") in unreadable_keys)]
    # Excluded by link identity, not by requirement key. Two gates can link two instances of the
    # same requirement key; excluding by key would drop the second one's established gap along
    # with the first one's unreadable row, which fails in the dangerous direction.
    unreadable_links = {r["link_id"] for r in unreadable}
    determined = [r for r in unmet if r["link_id"] not in unreadable_links]
    if not gates:
        # No gate is defined for this phase. That is not "ready": there is no approved contract to
        # satisfy, so the honest answer is that the question cannot be settled from records.
        state = "insufficient_data"
        summary = (f"No phase gate is defined for the "
                   f"{PHASE_LABELS.get(program['phase'], program['phase'])} phase, so there is no "
                   f"approved contract to evaluate.")
    elif not gate_open:
        state = "passed"
        summary = f"{_plural(len(gates), 'gate')} for this phase already recorded as settled."
    elif determined or blocking or open_items:
        state = "blocked"
        parts = []
        if determined:
            parts.append(f"{_plural(len(determined), 'required condition')} outstanding")
        if blocking:
            parts.append(f"{_plural(len(blocking), 'open blocker')}")
        if open_items:
            parts.append(f"{_plural(len(open_items), 'incomplete gate item')}")
        if unreadable:
            parts.append(f"{_plural(len(unreadable), 'condition')} that could not be evaluated")
        summary = f"{'; '.join(parts).capitalize()}."
    elif coverage != "complete":
        # Everything readable says yes, and something was not readable. That is not the same
        # answer, and collapsing it into `ready` would be the carried-forward-good-state failure.
        state = "insufficient_data"
        summary = (f"Every condition that could be evaluated is satisfied, but "
                   f"{_plural(len(coverage_failures), 'condition')} could not be evaluated at all.")
    elif not requirements:
        state = "insufficient_data"
        summary = ("The gate has no linked requirements, so nothing was evaluated. Link the "
                   "conditions this gate depends on.")
    else:
        state = "ready"
        summary = (f"All {len(requirements)} linked conditions are satisfied and no blocker is "
                   f"open. Advancing is still an explicit decision.")

    payload = {
        "program_id": program_id,
        "account_id": account_id,
        "program_name": program["name"],
        "current_phase": program["phase"],
        "current_phase_label": PHASE_LABELS.get(program["phase"], program["phase"]),
        "proposed_next_phase": _next_phase(program["phase"]),
        "proposed_next_phase_label": PHASE_LABELS.get(_next_phase(program["phase"]) or "", None),
        # Every phase the transition route would accept, so a non-adjacent move is a visible,
        # labelled choice that the dialog can mark as an override rather than a hidden capability
        # only reachable by hand-posting.
        "phase_options": [{"key": p, "label": PHASE_LABELS.get(p, p)} for p in PHASE_ORDER],
        "gates": [{"id": g["id"], "name": g["name"], "status": g["status"],
                   "gates_phase": g["gates_phase"], "waiver_reason": g["waiver_reason"],
                   "passed_on": g["passed_on"]} for g in gates],
        "requirements": requirements,
        "open_actions": open_actions,
        "blocking_records": blocking,
        "open_gate_items": open_items,
        "missing_evidence": missing_evidence,
        "stale_evidence": stale_evidence,
        "readiness": state,
        "summary": summary,
        "coverage": coverage,
        "coverage_failures": sorted(set(coverage_failures)),
        "evaluator_versions": evaluator_versions,
        "as_of": as_of,
        # Said in the payload, not only in the docs: nothing about reading this moved the program.
        "advances_automatically": False,
    }
    payload["readiness_stamp"] = _stamp(payload)
    return payload


def _plural(count: int, singular: str, plural: str | None = None) -> str:
    return f"{count} {singular if count == 1 else (plural or singular + 's')}"


# --- transitions (§15.6) ---------------------------------------------------------------------------

def _unmet_snapshot(current: dict) -> list[dict]:
    """What was outstanding when the operator acted. History about a decision, never a status.

    Stored under `unmet_at_transition_json` — a name chosen so a future reader cannot mistake it
    for live state. Readiness recomputes these conditions on every read and is the only thing that
    says what is true now.
    """
    return [
        {"requirement_key": r["requirement_key"], "label": r["label"],
         "necessity": r["necessity"], "state": r["state"], "freshness": r["freshness"],
         "applicability": r["applicability"]}
        for r in current["requirements"] if r["is_gap"]
    ] + [
        {"requirement_key": None, "label": item["description"], "necessity": "required",
         "state": None, "freshness": None, "applicability": "required",
         "gate_item_id": item["id"]}
        for item in current["open_gate_items"]
    ]


def _record_event(conn: sqlite3.Connection, program: dict, *, outcome: str, from_phase: str,
                  to_phase: str, current: dict, gate_id: str | None, is_override: bool,
                  reason: str | None, actor_id: str | None) -> str:
    event_id = new_id()
    conn.execute(
        "INSERT INTO program_phase_events "
        "(id, program_id, account_id, outcome, from_phase, to_phase, gate_id, readiness_stamp, "
        " readiness_as_of, is_override, reason, unmet_at_transition_json, actor_id, created_at) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (event_id, program["id"], program["account_id"], outcome, from_phase, to_phase, gate_id,
         current["readiness_stamp"], current["as_of"], 1 if is_override else 0, reason,
         json.dumps(_unmet_snapshot(current)), actor_id or audit.DEFAULT_ACTOR, now_utc()),
    )
    return event_id


def _reason(value: str | None, field: str = "reason") -> str:
    text = (value or "").strip()
    if len(text) < MIN_REASON_LENGTH:
        raise HTTPException(422, f"{field} must be at least {MIN_REASON_LENGTH} characters")
    return text


def transition(conn: sqlite3.Connection, program_id: str, *, expected_current_phase: str,
               requested_next_phase: str, readiness_stamp: str, actor_id: str | None = None,
               override: bool = False, reason: str | None = None,
               as_of: str | None = None) -> dict:
    """§15.6. Move the canonical program phase, atomically, against a checked readiness answer."""
    program = _program(conn, program_id)
    if requested_next_phase not in PHASE_ORDER:
        raise HTTPException(422, f"requested_next_phase must be one of {', '.join(PHASE_ORDER)}")
    if requested_next_phase == program["phase"]:
        raise HTTPException(422, "the program is already in that phase")
    if program["phase"] != expected_current_phase:
        # Someone else moved it. Told, not corrected: applying a transition to a phase the caller
        # did not think the program was in is how two operators overwrite each other.
        raise HTTPException(409, (
            f"the program is in the {PHASE_LABELS.get(program['phase'], program['phase'])} phase, "
            f"not {PHASE_LABELS.get(expected_current_phase, expected_current_phase)}"
        ))

    current = phase_readiness(conn, program_id, as_of=as_of)
    if readiness_stamp != current["readiness_stamp"]:
        raise HTTPException(409, (
            "the readiness answer has changed since it was read. Reload the gate and review the "
            "current conditions before advancing."
        ))

    adjacent = _next_phase(program["phase"]) == requested_next_phase
    text = _reason(reason) if (override or not adjacent) else (reason or None)
    if not adjacent and not override:
        raise HTTPException(422, (
            f"{PHASE_LABELS.get(requested_next_phase, requested_next_phase)} is not the next phase "
            f"after {PHASE_LABELS.get(program['phase'], program['phase'])}. A non-adjacent move is "
            f"an override and needs a reason."
        ))

    satisfied = current["readiness"] in ("ready", "passed")
    if not satisfied and not override:
        # Recorded before refusing, in its own transaction. An attempt that was turned away is a
        # real part of a gate's history and it is exactly the part a later review asks about.
        with conn:
            _record_event(conn, program, outcome="rejected", from_phase=program["phase"],
                          to_phase=requested_next_phase, current=current, gate_id=None,
                          is_override=False, reason=None, actor_id=actor_id)
        raise HTTPException(422, {
            "message": ("This gate is not satisfied, so the phase cannot advance. Record an "
                        "override with a reason if you are proceeding anyway."),
            "readiness": current["readiness"], "summary": current["summary"],
            "unmet": _unmet_snapshot(current),
        })

    before = dict(program)
    stamp = now_utc()
    gate_id = next((g["id"] for g in current["gates"] if g["status"] == "open"), None)
    with conn:
        event_id = _record_event(
            conn, program, outcome="completed", from_phase=program["phase"],
            to_phase=requested_next_phase, current=current, gate_id=gate_id,
            is_override=bool(override), reason=text, actor_id=actor_id)
        conn.execute("UPDATE programs SET phase = ?, updated_at = ? WHERE id = ?",
                     (requested_next_phase, stamp, program_id))
        if satisfied and not override:
            # Its conditions were met, so the gate is passed. On an override this is skipped on
            # purpose: the gate stays open because its conditions are still not met, and the
            # program has simply moved past it (§15.6).
            conn.execute(
                "UPDATE phase_gates SET status = 'passed', passed_on = ?, updated_at = ? "
                "WHERE program_id = ? AND gates_phase = ? AND status = 'open' AND archived = 0",
                (current["as_of"], stamp, program_id, before["phase"]),
            )
        after = dict(conn.execute("SELECT * FROM programs WHERE id = ?", (program_id,)).fetchone())
        # The audit vocabulary is the coarse create/update/archive/convert/close set; the specific
        # verb lives in the `program_phase_events` row, which is append-only and richer.
        audit.record(conn, object_type="program", object_id=program_id, action="update",
                     before=before, after=after, actor_id=actor_id)

    return {
        "event_id": event_id,
        "program_id": program_id,
        "from_phase": before["phase"],
        "to_phase": requested_next_phase,
        "is_override": bool(override),
        "reason": text,
        "unmet_at_transition": _unmet_snapshot(current),
        # Restated in the response because it is the thing an override most invites misreading:
        # the conditions listed above are still unmet, and readiness still says so.
        "note": ("The conditions recorded above remain unmet. This transition does not change "
                 "their readiness state." if override else
                 "The gate for the previous phase is recorded as passed."),
        "gate_passed": bool(satisfied and not override and gate_id),
    }


def propose(conn: sqlite3.Connection, program_id: str, *, requested_next_phase: str,
            note: str | None = None, actor_id: str | None = None,
            as_of: str | None = None) -> dict:
    """Record that an advance was proposed, without moving anything.

    Useful precisely when the answer is `blocked`: it puts the intent and the conditions of the
    moment into the append-only history so a later review can see when the team first expected to
    advance, and what was in the way.
    """
    program = _program(conn, program_id)
    if requested_next_phase not in PHASE_ORDER:
        raise HTTPException(422, f"requested_next_phase must be one of {', '.join(PHASE_ORDER)}")
    current = phase_readiness(conn, program_id, as_of=as_of)
    with conn:
        event_id = _record_event(conn, program, outcome="proposed", from_phase=program["phase"],
                                 to_phase=requested_next_phase, current=current, gate_id=None,
                                 is_override=False, reason=note, actor_id=actor_id)
    return {"event_id": event_id, "program_id": program_id, "outcome": "proposed",
            "readiness": current["readiness"], "phase_unchanged": program["phase"]}


def waive_gate(conn: sqlite3.Connection, gate_id: str, *, reason: str,
               actor_id: str | None = None, as_of: str | None = None) -> dict:
    """§15.6 — waiving a gate is distinct from completing its requirements.

    It settles the gate and moves nothing. The linked requirements keep whatever state the evidence
    gives them: a waiver accepts a gap, it does not fill one, which is the same rule Slice 3
    applies to a requirement-level waiver one level down.
    """
    gate = conn.execute("SELECT * FROM phase_gates WHERE id = ? AND archived = 0",
                        (gate_id,)).fetchone()
    if gate is None:
        raise HTTPException(404, "phase gate not found")
    gate = dict(gate)
    if gate["status"] != "open":
        raise HTTPException(409, f"gate is already {gate['status']}")
    text = _reason(reason)
    program = _program(conn, gate["program_id"])
    current = phase_readiness(conn, program["id"], as_of=as_of)
    stamp = now_utc()
    with conn:
        conn.execute(
            "UPDATE phase_gates SET status = 'waived', waiver_reason = ?, waived_by = ?, "
            "updated_at = ? WHERE id = ?",
            (text, actor_id or audit.DEFAULT_ACTOR, stamp, gate_id),
        )
        event_id = _record_event(
            conn, program, outcome="waived",
            # from == to on purpose. A waiver is not a movement, and recording a destination phase
            # would put a transition in the history that never happened.
            from_phase=program["phase"], to_phase=program["phase"], current=current,
            gate_id=gate_id, is_override=False, reason=text, actor_id=actor_id)
        after = dict(conn.execute("SELECT * FROM phase_gates WHERE id = ?", (gate_id,)).fetchone())
        audit.record(conn, object_type="phase_gate", object_id=gate_id, action="close",
                     before=gate, after=after, actor_id=actor_id)
    return {"event_id": event_id, "gate_id": gate_id, "status": "waived", "reason": text,
            "phase_unchanged": program["phase"],
            "unmet_at_waiver": _unmet_snapshot(current),
            "note": ("Waiving accepts these gaps. It does not satisfy them, and readiness still "
                     "reports them as outstanding.")}


def history(conn: sqlite3.Connection, program_id: str) -> dict:
    """§15.6 — append-only, newest first, for Plan and Leadership review provenance."""
    _program(conn, program_id)
    rows = [dict(r) for r in conn.execute(
        "SELECT * FROM program_phase_events WHERE program_id = ? ORDER BY created_at DESC, id DESC",
        (program_id,),
    )]
    return {
        "program_id": program_id,
        "events": [{
            "id": r["id"], "outcome": r["outcome"],
            "from_phase": r["from_phase"], "to_phase": r["to_phase"],
            "from_phase_label": PHASE_LABELS.get(r["from_phase"], r["from_phase"]),
            "to_phase_label": PHASE_LABELS.get(r["to_phase"], r["to_phase"]),
            "gate_id": r["gate_id"], "is_override": bool(r["is_override"]),
            "reason": r["reason"],
            # Labelled as of-the-moment wherever it surfaces, so nothing reads it as current.
            "unmet_at_transition": json.loads(r["unmet_at_transition_json"] or "[]"),
            "readiness_as_of": r["readiness_as_of"], "readiness_stamp": r["readiness_stamp"],
            "actor_id": r["actor_id"], "created_at": r["created_at"],
        } for r in rows],
    }


def setup_items(conn: sqlite3.Connection, account_id: str,
                program_id: str | None = None) -> list[dict]:
    """The operational half of the merged launch standard (migration 0051), for the Plan surface.

    A phase gate item is a thing somebody does, ticked when done. It sits beside plan requirements
    on the Plan tab because Zach asked for *one* standard rather than three lists that could each
    claim to be it — but "beside" is the whole constraint. These rows carry `state`, `freshness`
    and `applicability` explicitly null, exactly as `checklist_compatibility.legacy_items` does: a
    tick is an operator-recorded planning fact and readiness independently says whether the
    relationship condition it might contribute to is true. Synthesising a state here so the two
    kinds of row could share a status chip is precisely the second source of truth the projection
    rule exists to prevent.

    `gate_status` travels with each row so a settled gate reads as settled rather than as work.
    """
    sql = ("SELECT gi.*, g.name gate_name, g.gates_phase, g.status gate_status, g.program_id "
           "FROM phase_gate_items gi JOIN phase_gates g ON g.id = gi.gate_id "
           "JOIN programs p ON p.id = g.program_id "
           "WHERE p.account_id = ? AND g.archived = 0 AND p.archived = 0")
    params: list = [account_id]
    if program_id:
        sql += " AND g.program_id = ?"
        params.append(program_id)
    rows = conn.execute(sql + " ORDER BY gi.due_date, gi.created_at", tuple(params)).fetchall()
    return [{
        "gate_item_id": r["id"], "gate_id": r["gate_id"], "gate_name": r["gate_name"],
        "gates_phase": r["gates_phase"], "gate_status": r["gate_status"],
        "program_id": r["program_id"], "description": r["description"], "detail": r["detail"],
        "fills_field": r["fills_field"], "due_date": r["due_date"],
        "complete": bool(r["complete"]), "completed_on": r["completed_on"],
        "setup": True, "state": None, "freshness": None, "applicability": None,
    } for r in rows]


def plan_milestones(conn: sqlite3.Connection, account_id: str,
                    program_id: str | None = None) -> list[dict]:
    """The deployment half of the merged launch standard (migration 0051), for the Plan timeline.

    The standard is twenty-three dated things and the Plan payload was shipping fifteen of them:
    a timeline built from requirements and setup steps alone would draw the launch with its
    deployment events missing, which is the shape of the problem the merge exists to fix — three
    lists, each able to describe a launch the others would not recognise.

    A milestone is a dated deployment event whose completion an operator records, so it carries the
    same explicit nulls a gate item does. `at_risk` travels as the operator's own flag and is never
    read as a readiness state; nothing here derives one.
    """
    sql = ("SELECT m.*, p.name program_name FROM milestones m JOIN programs p ON p.id = m.program_id "
           "WHERE p.account_id = ? AND m.archived = 0 AND p.archived = 0")
    params: list = [account_id]
    if program_id:
        sql += " AND m.program_id = ?"
        params.append(program_id)
    rows = conn.execute(sql + " ORDER BY m.target_date, m.created_at", tuple(params)).fetchall()
    return [{
        "milestone_id": r["id"], "program_id": r["program_id"], "program_name": r["program_name"],
        "name": r["name"], "success_criteria": r["success_criteria"],
        "target_date": r["target_date"], "status": r["status"],
        "complete": r["status"] == "complete", "completed_on": r["completed_on"],
        "at_risk": bool(r["at_risk"]),
        "milestone": True, "state": None, "freshness": None, "applicability": None,
    } for r in rows]
