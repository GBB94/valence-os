"""Account Path Slice 5 — typed relationships, evidence, and successor-action closure.

`ACCOUNT-PATH-SPEC.md` §15.1–§15.3 and §15.7. This module owns the third layer of the Account
Path. Slice 3 stores *when* a condition was expected; `readiness.py` computes *whether* it is
true; this stores *which records an operator says are connected*. Four rules run through all of it,
and each one is the reason a more obvious design was rejected:

- **A link is a fact, not an inference.** The service may propose likely links, but text similarity
  never becomes a durable relationship (§15.2). Every row carries an actor and a timestamp and
  there is no confidence column: a link was accepted or it does not exist.
- **Advancing is not proving.** An open Task can `advance` a requirement all day without being
  evidence of it. That separation is why the action links and the evidence links are two tables
  rather than one with a flag — a single table would make "is this done?" a matter of remembering
  which flag to read.
- **A requirement cannot cite its own suggestion.** `readiness.py` emits a `suggested_action`
  template for a thin requirement. An action created from that template is recorded with
  `origin='suggested_action'`, and attaching it back to the *same* requirement as evidence is
  refused. Otherwise a condition would satisfy itself by having asked for something.
- **Nothing here stores a state.** Attaching evidence writes a link. What that link means is
  recomputed by the evaluators on every read, which is the only reason retraction, supersession,
  staleness, and archival can change an answer without a rebuild step (§15.3).
"""
from __future__ import annotations

import json
import sqlite3

from fastapi import HTTPException

from . import audit, execution_ops
from .db import new_id, now_utc

ACTION_RELATIONS = ("advances", "blocks", "follow_up_for")
MILESTONE_RELATIONS = ("advances", "blocks")
LINK_ORIGINS = ("operator", "suggested_action", "accepted_proposal")
NECESSITIES = ("required", "optional")
SOURCE_TYPES = ("interaction", "extraction_proposal")
MIN_REASON_LENGTH = 10          # mirrors playbooks.MIN_REASON_LENGTH and the CHECKs in 0046

# --- the evidence allowlist (§15.3) --------------------------------------------------------------
# `scope` names the columns the record carries, which decides how much of §15.2's scope validation
# is even answerable. `metric_definition` and `source_reference` are library records shared across
# accounts; they carry no scope and validating one against an account would invent a boundary the
# schema does not have. That is stated here rather than silently skipped.
_EVIDENCE_SOURCES: dict[str, dict] = {
    "decision":          {"table": "decisions", "label": "description", "scope": "account"},
    "stakeholder_role":  {"table": "stakeholder_roles", "label": "role", "scope": "program"},
    "metric_definition": {"table": "metric_definitions", "label": "name", "scope": "library"},
    "metric_observation": {"table": "metric_observations", "label": "period_label",
                           "scope": "program"},
    "value_target":      {"table": "value_targets", "label": "unit", "scope": "account_only"},
    "value_story":       {"table": "value_stories", "label": "outcome", "scope": "account"},
    "interaction":       {"table": "interactions", "label": "summary", "scope": "account"},
    "task":              {"table": "tasks", "label": "description", "scope": "program_only"},
    "commitment":        {"table": "commitments", "label": "description", "scope": "account"},
    "document":          {"table": "generated_documents", "label": "title", "scope": "account"},
    "source_reference":  {"table": "source_references", "label": "label", "scope": "library"},
    # Canonical fields are not rows. The id is `<table>.<column>`; provenance is the record itself.
    "account_field":     {"table": None, "label": None, "scope": "account_only"},
    "program_field":     {"table": None, "label": None, "scope": "program_only"},
}

EVIDENCE_TYPES = tuple(_EVIDENCE_SOURCES)

# Canonical fields an operator may cite. An allowlist, not reflection: letting a caller name any
# column would turn evidence into an arbitrary read of the schema.
_ACCOUNT_FIELDS = {
    "accounts.short_context", "accounts.incumbent_note", "accounts.delivery_status",
    "accounts.delivery_status_rationale", "accounts.delivery_status_change_condition",
    "accounts.commercial_status", "accounts.commercial_status_rationale",
    "accounts.commercial_status_change_condition",
}
_PROGRAM_FIELDS = {
    "programs.kickoff_date", "programs.onboarded_at", "programs.launch_definition",
    "programs.success_criteria", "programs.problem_statement", "programs.in_scope_population",
    "programs.out_of_scope_population", "programs.expansion_hypothesis",
    "programs.explicit_exclusions", "programs.sponsor_person_id", "programs.governance_steering",
    "programs.governance_rhythm", "programs.next_qbr_date",
}


# --- small helpers -------------------------------------------------------------------------------

def _actor(actor_id: str | None) -> str:
    return actor_id or audit.DEFAULT_ACTOR


def _reason(value: str | None, field: str = "reason") -> str:
    text = (value or "").strip()
    if len(text) < MIN_REASON_LENGTH:
        raise HTTPException(422, f"{field} must be at least {MIN_REASON_LENGTH} characters")
    return text


def _one_of(value, allowed, field):
    if value not in allowed:
        raise HTTPException(422, f"{field} must be one of {', '.join(allowed)}")
    return value


def _row(conn, table, id_, *, what):
    row = conn.execute(f"SELECT * FROM {table} WHERE id = ?", (id_,)).fetchone()
    if row is None:
        raise HTTPException(404, f"{what} not found")
    row = dict(row)
    if row.get("archived"):
        raise HTTPException(422, f"{what} is archived and cannot be linked")
    return row


def _plan_instance(conn: sqlite3.Connection, plan_instance_id: str) -> dict:
    row = conn.execute(
        "SELECT * FROM readiness_plan_instances WHERE id = ? AND archived = 0",
        (plan_instance_id,),
    ).fetchone()
    if row is None:
        raise HTTPException(404, "plan instance not found")
    return dict(row)


def _definition(conn: sqlite3.Connection, key: str, version: int) -> dict:
    row = conn.execute(
        "SELECT * FROM readiness_requirement_definitions WHERE key = ? AND version = ?",
        (key, version),
    ).fetchone()
    if row is None:
        raise HTTPException(404, f"requirement definition {key} v{version} not found")
    return dict(row)


def _action(conn: sqlite3.Connection, task_id: str | None,
            commitment_id: str | None) -> tuple[str, dict]:
    """Resolve exactly one native action. Two ids or none is a request error, not a preference."""
    if bool(task_id) == bool(commitment_id):
        raise HTTPException(422, "exactly one of task_id or commitment_id is required")
    if task_id:
        return "task", _row(conn, "tasks", task_id, what="task")
    return "commitment", _row(conn, "commitments", commitment_id, what="commitment")


def _action_scope(conn: sqlite3.Connection, kind: str, row: dict) -> tuple[str | None, str | None]:
    """(account_id, program_id) for an action. A Task carries only a program, so its account is
    the program's — resolved, never assumed."""
    program_id = row.get("program_id")
    account_id = row.get("account_id")
    if not account_id and program_id:
        program = conn.execute("SELECT account_id FROM programs WHERE id = ?",
                               (program_id,)).fetchone()
        account_id = program["account_id"] if program else None
    return account_id, program_id


def _check_scope(*, expect_account: str, expect_program: str | None,
                 got_account: str | None, got_program: str | None, what: str) -> None:
    """§15.2 — both sides, both directions.

    An account-scoped plan instance accepts work from any program on that account: the requirement
    genuinely is account-wide. A program-scoped one does not accept another program's work, and
    neither accepts another account's under any circumstance.
    """
    if got_account != expect_account:
        raise HTTPException(422, f"{what} belongs to another account")
    if expect_program and got_program and got_program != expect_program:
        raise HTTPException(422, f"{what} belongs to another program")
    if expect_program and not got_program:
        raise HTTPException(422, f"{what} is account-scoped and this requirement is program-scoped")


# --- requirement ↔ action (§15.1.1) ---------------------------------------------------------------

def link_action(conn: sqlite3.Connection, plan_instance_id: str, *,
                task_id: str | None = None, commitment_id: str | None = None,
                relation: str = "advances", origin: str = "operator",
                source_type: str | None = None, source_id: str | None = None,
                note: str | None = None, actor_id: str | None = None) -> dict:
    """Connect a scheduled requirement to a native Task or Commitment.

    `advances` records intent, not achievement. Whether the linked work satisfies the condition is
    decided later, by the requirement's own evaluator, and only for evaluators that read closure.
    """
    instance = _plan_instance(conn, plan_instance_id)
    _one_of(relation, ACTION_RELATIONS, "relation")
    _one_of(origin, LINK_ORIGINS, "origin")
    if source_type is not None:
        _one_of(source_type, SOURCE_TYPES, "source_type")
        if not source_id:
            raise HTTPException(422, "source_id is required when source_type is set")

    kind, row = _action(conn, task_id, commitment_id)
    account_id, program_id = _action_scope(conn, kind, row)
    _check_scope(expect_account=instance["account_id"], expect_program=instance["program_id"],
                 got_account=account_id, got_program=program_id, what=kind)

    existing = conn.execute(
        "SELECT * FROM readiness_requirement_action_links "
        "WHERE plan_instance_id = ? AND ifnull(task_id,'') = ? AND ifnull(commitment_id,'') = ? "
        "  AND relation = ? AND archived = 0",
        (plan_instance_id, task_id or "", commitment_id or "", relation),
    ).fetchone()
    if existing is not None:
        # Idempotent rather than a 409: the caller asked for a relationship that already exists,
        # and there is exactly one of it. Nothing is written and nothing is duplicated.
        return {"link": _public_action_link(dict(existing)), "created": False}

    link_id = new_id()
    stamp = now_utc()
    with conn:
        conn.execute(
            "INSERT INTO readiness_requirement_action_links "
            "(id, plan_instance_id, account_id, program_id, task_id, commitment_id, relation, "
            " origin, source_type, source_id, note, actor_id, created_at, updated_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (link_id, plan_instance_id, instance["account_id"], instance["program_id"],
             task_id, commitment_id, relation, origin, source_type, source_id,
             note, _actor(actor_id), stamp, stamp),
        )
        after = dict(conn.execute(
            "SELECT * FROM readiness_requirement_action_links WHERE id = ?", (link_id,)
        ).fetchone())
        audit.record(conn, object_type="requirement_action_link", object_id=link_id,
                     action="create", after=after, actor_id=_actor(actor_id))
    return {"link": _public_action_link(after), "created": True}


def archive_action_link(conn: sqlite3.Connection, link_id: str, *, reason: str,
                        actor_id: str | None = None) -> dict:
    """§15.2 — archival, never deletion. A link that influenced a gate stays readable afterwards."""
    return _archive(conn, "readiness_requirement_action_links", link_id,
                    object_type="requirement_action_link", reason=reason, actor_id=actor_id,
                    public=_public_action_link)


# --- requirement ↔ evidence (§15.1.2, §15.3) ------------------------------------------------------

def _resolve_evidence(conn: sqlite3.Connection, instance: dict, evidence_type: str,
                      evidence_id: str) -> str:
    """Validate the cited record and return its display label. Raises on anything unlinkable."""
    spec = _EVIDENCE_SOURCES.get(evidence_type)
    if spec is None:
        raise HTTPException(422, f"{evidence_type} is not a supported evidence type")

    if spec["table"] is None:                       # canonical field citation
        allowed = _ACCOUNT_FIELDS if evidence_type == "account_field" else _PROGRAM_FIELDS
        if evidence_id not in allowed:
            raise HTTPException(422, f"{evidence_id} is not an allowlisted {evidence_type}")
        if evidence_type == "program_field" and not instance["program_id"]:
            raise HTTPException(422, "a program field cannot be evidence for an account-scoped "
                                     "requirement")
        return evidence_id.split(".", 1)[1].replace("_", " ")

    row = _row(conn, spec["table"], evidence_id, what=evidence_type.replace("_", " "))
    scope = spec["scope"]
    if scope != "library":
        account_id = row.get("account_id")
        program_id = row.get("program_id")
        if account_id is None and program_id:
            program = conn.execute("SELECT account_id FROM programs WHERE id = ?",
                                   (program_id,)).fetchone()
            account_id = program["account_id"] if program else None
        if account_id is None and scope in ("program", "program_only"):
            # A record whose scope cannot be resolved is not silently accepted: an unplaceable
            # citation is exactly the kind of thing that later reads as a cross-account link.
            raise HTTPException(422, f"{evidence_type} has no resolvable account scope")
        if account_id is not None:
            _check_scope(expect_account=instance["account_id"],
                         expect_program=instance["program_id"],
                         got_account=account_id, got_program=program_id, what=evidence_type)
    label = row.get(spec["label"]) or evidence_id
    return str(label)[:180]


def attach_evidence(conn: sqlite3.Connection, plan_instance_id: str, *, evidence_type: str,
                    evidence_id: str, note: str | None = None, reviewed_on: str | None = None,
                    review_note: str | None = None, actor_id: str | None = None) -> dict:
    """Attach an accepted record as evidence for a scheduled requirement.

    Two refusals and one downgrade, all from §15.3:

    - An **open** Task or Commitment is refused. Advancing is not proving, and letting an open item
      count would make `Resolve` optional (§15.9). The caller is pointed at the `advances` link.
    - A Task or Commitment that this same requirement *suggested* is refused, whatever its status:
      a condition may not satisfy itself by having asked for something (§15.2).
    - Anything outside the definition's `allowed_evidence_types` is **downgraded, not refused**. It
      attaches as context with `supporting = 0`, stays visible on the record, and can never change
      derived state.
    """
    instance = _plan_instance(conn, plan_instance_id)
    definition = _definition(conn, instance["requirement_key"], instance["requirement_version"])
    label = _resolve_evidence(conn, instance, evidence_type, evidence_id)

    if evidence_type in ("task", "commitment"):
        table = "tasks" if evidence_type == "task" else "commitments"
        status = conn.execute(f"SELECT status FROM {table} WHERE id = ?",
                              (evidence_id,)).fetchone()["status"]
        if status == "open":
            raise HTTPException(422, (
                f"this {evidence_type} is still open, so it is not evidence that the condition is "
                "met. Link it as an action that advances the requirement instead; it becomes "
                "citable when its governed closure is recorded."
            ))
        column = "task_id" if evidence_type == "task" else "commitment_id"
        suggested = conn.execute(
            f"SELECT 1 FROM readiness_requirement_action_links "
            f"WHERE plan_instance_id = ? AND {column} = ? AND origin = 'suggested_action' "
            f"  AND archived = 0 LIMIT 1",
            (plan_instance_id, evidence_id),
        ).fetchone()
        if suggested is not None:
            raise HTTPException(422, (
                "this requirement suggested that action, so it cannot also be the evidence that "
                "the requirement is satisfied. Cite the record the work produced instead."
            ))

    allowed = json.loads(definition["allowed_evidence_types_json"] or "[]")
    supporting = 1 if (not allowed or evidence_type in allowed) else 0
    if reviewed_on and not review_note:
        raise HTTPException(422, "review_note is required when reviewed_on is set")

    existing = conn.execute(
        "SELECT * FROM readiness_requirement_evidence_links "
        "WHERE plan_instance_id = ? AND evidence_type = ? AND evidence_id = ? "
        "  AND archived = 0 AND retracted_at IS NULL",
        (plan_instance_id, evidence_type, evidence_id),
    ).fetchone()
    if existing is not None:
        return {"evidence": _public_evidence_link(dict(existing)), "created": False}

    link_id = new_id()
    stamp = now_utc()
    with conn:
        conn.execute(
            "INSERT INTO readiness_requirement_evidence_links "
            "(id, plan_instance_id, account_id, program_id, evidence_type, evidence_id, "
            " evidence_label, supporting, reviewed_on, reviewed_by, review_note, actor_id, "
            " created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (link_id, plan_instance_id, instance["account_id"], instance["program_id"],
             evidence_type, evidence_id, label, supporting,
             reviewed_on, _actor(actor_id) if reviewed_on else None,
             review_note or note, _actor(actor_id), stamp, stamp),
        )
        after = dict(conn.execute(
            "SELECT * FROM readiness_requirement_evidence_links WHERE id = ?", (link_id,)
        ).fetchone())
        audit.record(conn, object_type="requirement_evidence_link", object_id=link_id,
                     action="create", after=after, actor_id=_actor(actor_id))
    return {"evidence": _public_evidence_link(after), "created": True}


def review_evidence(conn: sqlite3.Connection, link_id: str, *, reviewed_on: str,
                    review_note: str, actor_id: str | None = None) -> dict:
    """§15.4's `manual_evidence_review` — a dated reviewer decision, recorded on the link itself.

    The date is the point. `manual_evidence_review` is the evaluator for conditions automation
    cannot settle, so the review has to age like any other dated fact rather than standing forever.
    """
    before = _live_evidence(conn, link_id)
    note = _reason(review_note, "review_note")
    stamp = now_utc()
    with conn:
        conn.execute(
            "UPDATE readiness_requirement_evidence_links "
            "SET reviewed_on = ?, reviewed_by = ?, review_note = ?, updated_at = ? WHERE id = ?",
            (reviewed_on, _actor(actor_id), note, stamp, link_id),
        )
        after = dict(conn.execute(
            "SELECT * FROM readiness_requirement_evidence_links WHERE id = ?", (link_id,)
        ).fetchone())
        audit.record(conn, object_type="requirement_evidence_link", object_id=link_id,
                     action="update", before=before, after=after, actor_id=_actor(actor_id))
    return {"evidence": _public_evidence_link(after)}


def retract_evidence(conn: sqlite3.Connection, link_id: str, *, reason: str,
                     superseded_by_id: str | None = None,
                     actor_id: str | None = None) -> dict:
    """§15.3 — withdraw support without hiding that it was ever claimed.

    Retracting is deliberately not archiving. The row stays visible and explicitly withdrawn, so
    an operator reading the requirement later sees that a claim was made and taken back, which is
    a different fact from the claim never existing.
    """
    before = _live_evidence(conn, link_id)
    text = _reason(reason)
    if superseded_by_id:
        replacement = conn.execute(
            "SELECT plan_instance_id FROM readiness_requirement_evidence_links WHERE id = ?",
            (superseded_by_id,),
        ).fetchone()
        if replacement is None:
            raise HTTPException(404, "superseding evidence link not found")
        if replacement["plan_instance_id"] != before["plan_instance_id"]:
            raise HTTPException(422, "superseding evidence must be on the same requirement")
    stamp = now_utc()
    with conn:
        conn.execute(
            "UPDATE readiness_requirement_evidence_links "
            "SET retracted_at = ?, retracted_by = ?, retracted_reason = ?, superseded_by_id = ?, "
            "    updated_at = ? WHERE id = ?",
            (stamp, _actor(actor_id), text, superseded_by_id, stamp, link_id),
        )
        after = dict(conn.execute(
            "SELECT * FROM readiness_requirement_evidence_links WHERE id = ?", (link_id,)
        ).fetchone())
        audit.record(conn, object_type="requirement_evidence_link", object_id=link_id,
                     action="archive", before=before, after=after, actor_id=_actor(actor_id))
    return {"evidence": _public_evidence_link(after)}


def _live_evidence(conn: sqlite3.Connection, link_id: str) -> dict:
    row = conn.execute(
        "SELECT * FROM readiness_requirement_evidence_links WHERE id = ? AND archived = 0",
        (link_id,),
    ).fetchone()
    if row is None:
        raise HTTPException(404, "evidence link not found")
    return dict(row)


# --- milestone ↔ action (§15.1.3) -----------------------------------------------------------------

def link_milestone_action(conn: sqlite3.Connection, milestone_id: str, *,
                          task_id: str | None = None, commitment_id: str | None = None,
                          relation: str = "advances", note: str | None = None,
                          actor_id: str | None = None) -> dict:
    milestone = _row(conn, "milestones", milestone_id, what="milestone")
    _one_of(relation, MILESTONE_RELATIONS, "relation")
    program = conn.execute("SELECT * FROM programs WHERE id = ? AND archived = 0",
                           (milestone["program_id"],)).fetchone()
    if program is None:
        raise HTTPException(422, "milestone belongs to an archived program")

    kind, row = _action(conn, task_id, commitment_id)
    account_id, program_id = _action_scope(conn, kind, row)
    _check_scope(expect_account=program["account_id"], expect_program=program["id"],
                 got_account=account_id, got_program=program_id, what=kind)

    existing = conn.execute(
        "SELECT * FROM milestone_action_links "
        "WHERE milestone_id = ? AND ifnull(task_id,'') = ? AND ifnull(commitment_id,'') = ? "
        "  AND relation = ? AND archived = 0",
        (milestone_id, task_id or "", commitment_id or "", relation),
    ).fetchone()
    if existing is not None:
        return {"link": _public_milestone_link(dict(existing)), "created": False}

    link_id, stamp = new_id(), now_utc()
    with conn:
        conn.execute(
            "INSERT INTO milestone_action_links "
            "(id, milestone_id, account_id, program_id, task_id, commitment_id, relation, note, "
            " actor_id, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (link_id, milestone_id, program["account_id"], program["id"], task_id, commitment_id,
             relation, note, _actor(actor_id), stamp, stamp),
        )
        after = dict(conn.execute("SELECT * FROM milestone_action_links WHERE id = ?",
                                  (link_id,)).fetchone())
        audit.record(conn, object_type="milestone_action_link", object_id=link_id,
                     action="create", after=after, actor_id=_actor(actor_id))
    return {"link": _public_milestone_link(after), "created": True}


def archive_milestone_link(conn: sqlite3.Connection, link_id: str, *, reason: str,
                           actor_id: str | None = None) -> dict:
    return _archive(conn, "milestone_action_links", link_id, object_type="milestone_action_link",
                    reason=reason, actor_id=actor_id, public=_public_milestone_link)


# --- gate ↔ requirement (§15.1.4) -----------------------------------------------------------------

def link_gate_requirement(conn: sqlite3.Connection, gate_id: str, *, plan_instance_id: str,
                          necessity: str = "required", note: str | None = None,
                          actor_id: str | None = None) -> dict:
    """Declare which scheduled conditions a phase gate depends on.

    `necessity` here is the *gate's* demand. It is not the plan instance's `necessity`, which only
    governs whether the entry could be excluded at instantiation, and it is not readiness
    applicability. A gate may require a condition the plan scheduled as optional — that is the
    reason both values exist rather than one being derived from the other.
    """
    gate = _row(conn, "phase_gates", gate_id, what="phase gate")
    _one_of(necessity, NECESSITIES, "necessity")
    program = conn.execute("SELECT * FROM programs WHERE id = ? AND archived = 0",
                           (gate["program_id"],)).fetchone()
    if program is None:
        raise HTTPException(422, "gate belongs to an archived program")
    instance = _plan_instance(conn, plan_instance_id)
    if instance["account_id"] != program["account_id"]:
        raise HTTPException(422, "requirement belongs to another account")
    if instance["program_id"] and instance["program_id"] != program["id"]:
        raise HTTPException(422, "requirement belongs to another program")

    existing = conn.execute(
        "SELECT * FROM gate_requirement_links "
        "WHERE gate_id = ? AND plan_instance_id = ? AND archived = 0",
        (gate_id, plan_instance_id),
    ).fetchone()
    if existing is not None:
        return {"link": _public_gate_link(dict(existing)), "created": False}

    link_id, stamp = new_id(), now_utc()
    with conn:
        conn.execute(
            "INSERT INTO gate_requirement_links "
            "(id, gate_id, plan_instance_id, account_id, program_id, necessity, note, actor_id, "
            " created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
            (link_id, gate_id, plan_instance_id, program["account_id"], program["id"],
             necessity, note, _actor(actor_id), stamp, stamp),
        )
        after = dict(conn.execute("SELECT * FROM gate_requirement_links WHERE id = ?",
                                  (link_id,)).fetchone())
        audit.record(conn, object_type="gate_requirement_link", object_id=link_id,
                     action="create", after=after, actor_id=_actor(actor_id))
    return {"link": _public_gate_link(after), "created": True}


def archive_gate_link(conn: sqlite3.Connection, link_id: str, *, reason: str,
                      actor_id: str | None = None) -> dict:
    return _archive(conn, "gate_requirement_links", link_id, object_type="gate_requirement_link",
                    reason=reason, actor_id=actor_id, public=_public_gate_link)


def _archive(conn: sqlite3.Connection, table: str, link_id: str, *, object_type: str,
             reason: str, actor_id: str | None, public) -> dict:
    row = conn.execute(f"SELECT * FROM {table} WHERE id = ?", (link_id,)).fetchone()
    if row is None:
        raise HTTPException(404, "link not found")
    before = dict(row)
    if before["archived"]:
        return {"link": public(before), "archived": False}
    text = _reason(reason)
    stamp = now_utc()
    with conn:
        conn.execute(
            f"UPDATE {table} SET archived = 1, archived_at = ?, archived_by = ?, "
            f"archived_reason = ?, updated_at = ? WHERE id = ?",
            (stamp, _actor(actor_id), text, stamp, link_id),
        )
        after = dict(conn.execute(f"SELECT * FROM {table} WHERE id = ?", (link_id,)).fetchone())
        audit.record(conn, object_type=object_type, object_id=link_id, action="archive",
                     before=before, after=after, actor_id=_actor(actor_id))
    return {"link": public(after), "archived": True}


# --- public shapes --------------------------------------------------------------------------------

def _action_ref(row: dict) -> dict:
    return {"type": "task" if row["task_id"] else "commitment",
            "id": row["task_id"] or row["commitment_id"]}


def _public_action_link(row: dict) -> dict:
    return {
        "id": row["id"], "plan_instance_id": row["plan_instance_id"],
        "action": _action_ref(row), "relation": row["relation"], "origin": row["origin"],
        "source": ({"type": row["source_type"], "id": row["source_id"]}
                   if row["source_type"] else None),
        "note": row["note"], "actor_id": row["actor_id"], "created_at": row["created_at"],
        "archived": bool(row["archived"]), "archived_at": row["archived_at"],
        "archived_reason": row["archived_reason"],
    }


def _public_evidence_link(row: dict) -> dict:
    return {
        "id": row["id"], "plan_instance_id": row["plan_instance_id"],
        "evidence_type": row["evidence_type"], "evidence_id": row["evidence_id"],
        "label": row["evidence_label"],
        # False means "attached as context". The definition did not allow this kind, so it is on
        # the record and cannot move the state (§15.3).
        "supporting": bool(row["supporting"]),
        "reviewed_on": row["reviewed_on"], "reviewed_by": row["reviewed_by"],
        "review_note": row["review_note"],
        "retracted_at": row["retracted_at"], "retracted_reason": row["retracted_reason"],
        "superseded_by_id": row["superseded_by_id"],
        "actor_id": row["actor_id"], "created_at": row["created_at"],
        "archived": bool(row["archived"]),
    }


def _public_milestone_link(row: dict) -> dict:
    return {
        "id": row["id"], "milestone_id": row["milestone_id"], "action": _action_ref(row),
        "relation": row["relation"], "note": row["note"], "actor_id": row["actor_id"],
        "created_at": row["created_at"], "archived": bool(row["archived"]),
        "archived_reason": row["archived_reason"],
    }


def _public_gate_link(row: dict) -> dict:
    return {
        "id": row["id"], "gate_id": row["gate_id"], "plan_instance_id": row["plan_instance_id"],
        "necessity": row["necessity"], "note": row["note"], "actor_id": row["actor_id"],
        "created_at": row["created_at"], "archived": bool(row["archived"]),
        "archived_reason": row["archived_reason"],
    }


# --- reads (§15.8) --------------------------------------------------------------------------------

def _describe_actions(conn: sqlite3.Connection, rows: list[dict], public_fn) -> list[dict]:
    """Attach each action's live status so the caller never has to guess from the relation."""
    out = []
    for row in rows:
        ref = _action_ref(row)
        table = "tasks" if ref["type"] == "task" else "commitments"
        record = conn.execute(
            f"SELECT description, status, due_date, closed_on, close_note, archived "
            f"FROM {table} WHERE id = ?", (ref["id"],)
        ).fetchone()
        public = public_fn(row)
        public["action"] = dict(ref, **({
            "description": record["description"], "status": record["status"],
            "due_date": record["due_date"], "closed_on": record["closed_on"],
            "close_note": record["close_note"], "archived": bool(record["archived"]),
        } if record else {"description": None, "status": "unknown", "due_date": None,
                          "closed_on": None, "close_note": None, "archived": False}))
        out.append(public)
    return out


def requirement_links(conn: sqlite3.Connection, plan_instance_id: str) -> dict:
    """Everything linked to one scheduled requirement — §15.8's requirement detail panel."""
    _plan_instance(conn, plan_instance_id)
    actions = [dict(r) for r in conn.execute(
        "SELECT * FROM readiness_requirement_action_links "
        "WHERE plan_instance_id = ? AND archived = 0 ORDER BY created_at", (plan_instance_id,)
    )]
    evidence = [dict(r) for r in conn.execute(
        "SELECT * FROM readiness_requirement_evidence_links "
        "WHERE plan_instance_id = ? AND archived = 0 ORDER BY created_at", (plan_instance_id,)
    )]
    gates = [dict(r) for r in conn.execute(
        "SELECT g.*, pg.name AS gate_name, pg.gates_phase, pg.status AS gate_status "
        "FROM gate_requirement_links g JOIN phase_gates pg ON pg.id = g.gate_id "
        "WHERE g.plan_instance_id = ? AND g.archived = 0 ORDER BY g.created_at",
        (plan_instance_id,)
    )]
    return {
        "plan_instance_id": plan_instance_id,
        "actions": _describe_actions(conn, actions, _public_action_link),
        "evidence": [_public_evidence_link(r) for r in evidence],
        "gates": [dict(_public_gate_link(r), gate_name=r["gate_name"],
                       gates_phase=r["gates_phase"], gate_status=r["gate_status"])
                  for r in gates],
    }


def milestone_links(conn: sqlite3.Connection, milestone_id: str) -> dict:
    """The explicit dependencies of one Milestone — §15.8's timeline dependency lines.

    Only rows from this table are returned, which is the whole point: a dependency line on the
    timeline is drawn from an accepted relationship or it is not drawn. Nothing here infers a
    dependency from a shared due date, a shared owner, or matching text.
    """
    _row(conn, "milestones", milestone_id, what="milestone")
    rows = [dict(r) for r in conn.execute(
        "SELECT * FROM milestone_action_links WHERE milestone_id = ? AND archived = 0 "
        "ORDER BY created_at", (milestone_id,)
    )]
    return {"milestone_id": milestone_id,
            "links": _describe_actions(conn, rows, _public_milestone_link)}


def action_context(conn: sqlite3.Connection, *, task_id: str | None = None,
                   commitment_id: str | None = None) -> dict:
    """§15.8 — what this action advances. The inverse read, from the action's own detail panel."""
    kind, _row_ = _action(conn, task_id, commitment_id)
    column = "task_id" if kind == "task" else "commitment_id"
    action_id = task_id or commitment_id
    requirements = [dict(r) for r in conn.execute(
        f"SELECT l.*, i.requirement_key, i.requirement_version, i.pillar_key, i.due_date, "
        f"       d.label AS requirement_label, d.definition_of_done "
        f"FROM readiness_requirement_action_links l "
        f"JOIN readiness_plan_instances i ON i.id = l.plan_instance_id "
        f"LEFT JOIN readiness_requirement_definitions d "
        f"       ON d.key = i.requirement_key AND d.version = i.requirement_version "
        f"WHERE l.{column} = ? AND l.archived = 0 AND i.archived = 0 ORDER BY l.created_at",
        (action_id,)
    )]
    milestones = [dict(r) for r in conn.execute(
        f"SELECT l.*, m.name AS milestone_name, m.status AS milestone_status, m.target_date "
        f"FROM milestone_action_links l JOIN milestones m ON m.id = l.milestone_id "
        f"WHERE l.{column} = ? AND l.archived = 0 ORDER BY l.created_at",
        (action_id,)
    )]
    # A gate reaches an action only through a requirement. Claiming otherwise would be the
    # text-similarity inference §15.2 forbids, one table further out.
    gates = [dict(r) for r in conn.execute(
        f"SELECT DISTINCT g.gate_id, g.necessity, pg.name AS gate_name, pg.gates_phase, "
        f"       pg.status AS gate_status, i.requirement_key "
        f"FROM readiness_requirement_action_links l "
        f"JOIN gate_requirement_links g ON g.plan_instance_id = l.plan_instance_id "
        f"    AND g.archived = 0 "
        f"JOIN phase_gates pg ON pg.id = g.gate_id AND pg.archived = 0 "
        f"JOIN readiness_plan_instances i ON i.id = l.plan_instance_id "
        f"WHERE l.{column} = ? AND l.archived = 0 AND l.relation = 'advances' "
        f"ORDER BY pg.name",
        (action_id,)
    )]
    return {
        "action": {"type": kind, "id": action_id},
        "requirements": [
            {"link_id": r["id"], "plan_instance_id": r["plan_instance_id"],
             "relation": r["relation"], "origin": r["origin"],
             "requirement_key": r["requirement_key"],
             "requirement_version": r["requirement_version"], "pillar_key": r["pillar_key"],
             "label": r["requirement_label"], "definition_of_done": r["definition_of_done"],
             "due_date": r["due_date"]}
            for r in requirements
        ],
        "milestones": [
            {"link_id": r["id"], "milestone_id": r["milestone_id"], "relation": r["relation"],
             "name": r["milestone_name"], "status": r["milestone_status"],
             "target_date": r["target_date"]}
            for r in milestones
        ],
        "gates": [
            {"gate_id": r["gate_id"], "name": r["gate_name"], "gates_phase": r["gates_phase"],
             "status": r["gate_status"], "necessity": r["necessity"],
             "through_requirement": r["requirement_key"]}
            for r in gates
        ],
    }


def requirement_action_index(conn: sqlite3.Connection, account_id: str) -> dict:
    """`(program_id, requirement_key) -> linked action` for the §13.6 next-move dedupe.

    Only `advances` counts. A `blocks` link is the reason the requirement is stuck, and a
    `follow_up_for` link is downstream of it; neither is "this requirement's work is already
    represented by a record", which is the only claim the dedupe is entitled to make.
    """
    out: dict[tuple[str | None, str], dict] = {}
    rows = conn.execute(
        "SELECT l.*, i.requirement_key, i.program_id AS instance_program_id "
        "FROM readiness_requirement_action_links l "
        "JOIN readiness_plan_instances i ON i.id = l.plan_instance_id "
        "WHERE l.account_id = ? AND l.archived = 0 AND i.archived = 0 "
        "  AND l.relation = 'advances' ORDER BY l.created_at",
        (account_id,),
    ).fetchall()
    for row in rows:
        row = dict(row)
        ref = _action_ref(row)
        table = "tasks" if ref["type"] == "task" else "commitments"
        record = conn.execute(
            f"SELECT description, status, due_date FROM {table} WHERE id = ? AND archived = 0",
            (ref["id"],),
        ).fetchone()
        if record is None:
            continue        # an archived action stops standing in for the requirement's work
        key = (row["instance_program_id"], row["requirement_key"])
        out.setdefault(key, {
            "type": ref["type"], "id": ref["id"], "description": record["description"],
            "status": record["status"], "due_date": record["due_date"],
            "link_id": row["id"], "relation": row["relation"],
        })
    return out


# --- successor-action closure (§15.7) --------------------------------------------------------------

def close_with_successor(conn: sqlite3.Connection, *, action_type: str, action_id: str,
                         closure: dict | None = None, successor: dict | None = None,
                         actor_id: str | None = None) -> dict:
    """Close a linked action and, when the work is not actually finished, carry the link forward.

    This exists so `Resolve` cannot become a way to hide incomplete account work (§15.7). Native
    closure stays authoritative — this calls the same `execution_ops` path the execution router
    does — and the requirement stays exactly as open as its evaluator says it is. Nothing here
    marks anything met; the successor inherits `follow_up_for`, which is downstream of the
    condition and never evidence for it.
    """
    _one_of(action_type, ("task", "commitment"), "action_type")
    closure = dict(closure or {})
    kind, row = _action(conn, action_id if action_type == "task" else None,
                        action_id if action_type == "commitment" else None)

    requirement_links_before = [dict(r) for r in conn.execute(
        f"SELECT * FROM readiness_requirement_action_links "
        f"WHERE {'task_id' if kind == 'task' else 'commitment_id'} = ? AND archived = 0",
        (action_id,)
    )]
    milestone_links_before = [dict(r) for r in conn.execute(
        f"SELECT * FROM milestone_action_links "
        f"WHERE {'task_id' if kind == 'task' else 'commitment_id'} = ? AND archived = 0",
        (action_id,)
    )]

    if kind == "task":
        closed = execution_ops.close_task(
            conn, action_id, status=closure.get("status", "done"),
            closed_on=closure.get("closed_on"), close_note=closure.get("close_note"))
    else:
        closed = execution_ops.close_commitment(
            conn, action_id, acknowledged_by_id=closure.get("acknowledged_by_id"),
            closed_on=closure.get("closed_on"), close_note=closure.get("close_note"))

    created = None
    carried: list[dict] = []
    if successor:
        if not successor.get("description"):
            raise HTTPException(422, "successor description is required")
        target = _one_of(successor.get("type", "task"), ("task", "commitment"), "successor.type")
        payload = {
            "program_id": successor.get("program_id") or row.get("program_id"),
            "description": successor["description"],
            "due_date": successor.get("due_date"),
        }
        if target == "task":
            payload["internal_owner_id"] = successor.get("internal_owner_id")
            payload["status"] = "open"
        else:
            payload["account_id"] = successor.get("account_id") or row.get("account_id")
            payload["commitment_class"] = successor.get("commitment_class", "internal")
            payload["responsible_party_id"] = successor.get("responsible_party_id")
            payload["internal_owner_id"] = successor.get("internal_owner_id")
            payload["status"] = "open"
        created = execution_ops.create(conn, target, payload)
        new_task = created["id"] if target == "task" else None
        new_commitment = created["id"] if target == "commitment" else None
        for link in requirement_links_before:
            result = link_action(
                conn, link["plan_instance_id"], task_id=new_task, commitment_id=new_commitment,
                relation="follow_up_for", origin="operator",
                note=f"Successor to the {kind} closed on {closed['closed_on']}.",
                actor_id=actor_id)
            carried.append(result["link"])
        for link in milestone_links_before:
            result = link_milestone_action(
                conn, link["milestone_id"], task_id=new_task, commitment_id=new_commitment,
                relation=link["relation"],
                note=f"Successor to the {kind} closed on {closed['closed_on']}.",
                actor_id=actor_id)
            carried.append(result["link"])

    return {
        "closed": {"type": kind, "id": action_id, "status": closed["status"],
                   "closed_on": closed["closed_on"], "close_note": closed["close_note"]},
        "successor": ({"type": successor["type"] if successor.get("type") else "task",
                       "id": created["id"], "description": created["description"]}
                      if created else None),
        "carried_links": carried,
        # Said out loud because the operator just resolved something: closing work does not settle
        # a condition. Readiness recomputes on the next read and decides that on its own.
        "requirement_note": (
            "The linked requirements stay open until their evaluators are satisfied. Closing an "
            "action does not record evidence."
        ) if requirement_links_before else None,
    }
