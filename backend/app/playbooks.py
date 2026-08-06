"""Account Path Slice 3 — playbooks, plan instances, and governed exceptions.

`ACCOUNT-PATH-SPEC.md` §13. This module owns the planning layer that
`RELATIONSHIP-READINESS-SPEC.md` §0.4 declines to store: which conditions a plan pins, at which
definition versions, and when each is due. It owns none of the judgment.

The division is the whole design, and it is easy to get backwards:

- **Readiness says what is true; a plan says when it was expected.** The merged row carries the
  four readiness axes verbatim and adds a due date beside them. A due date never moves a state, and
  an overdue requirement is overdue and `thin`, not "failing".
- **A version, once instantiated, is frozen.** Editing a template writes a new playbook version.
  Moving an account onto it is an explicit, previewed upgrade, so nobody's active plan changes
  under them because someone edited a template.
- **Suppression is governed and subtractive.** `not_applicable` and `waiver` both require a reason
  and an actor, both are read back inside `readiness.py`, and neither can mark anything met.
- **Compatibility carries the checkbox, not the conclusion.** A `done` legacy checklist item
  becomes `recorded_complete` on a plan instance. It never becomes evidence and never becomes a
  readiness state; if the underlying record really satisfies the condition, readiness is already
  reporting `met` on its own and does not need the tick.
"""
from __future__ import annotations

import json
import sqlite3
from datetime import date, timedelta

from fastapi import HTTPException

from . import audit, readiness, short_ref
from .db import new_id, now_utc

EXCEPTION_KINDS = ("not_applicable", "waiver")
MIN_REASON_LENGTH = 10          # mirrors the CHECK in migration 0042, as a friendly 422
COMPATIBILITY_PLAYBOOK = ("checklist-compatibility", 1)


# --- small helpers -------------------------------------------------------------------------------

def _today() -> str:
    return now_utc()[:10]


def _iso(value: str, field: str) -> str:
    try:
        return date.fromisoformat(str(value)[:10]).isoformat()
    except (TypeError, ValueError):
        raise HTTPException(422, f"{field} must be an ISO date (YYYY-MM-DD), got {value!r}")


def _shift(anchor: str, offset_days: int | None) -> str | None:
    if offset_days is None:
        return None
    return (date.fromisoformat(anchor) + timedelta(days=int(offset_days))).isoformat()


def _account(conn: sqlite3.Connection, account_id: str) -> dict:
    row = conn.execute(
        "SELECT id, name FROM accounts WHERE id = ? AND archived = 0", (account_id,)
    ).fetchone()
    if row is None:
        raise HTTPException(404, "account not found")
    return dict(row)


def _program(conn: sqlite3.Connection, account_id: str, program_id: str | None) -> dict | None:
    """A foreign or archived program is an error, never a silent fall back to account scope."""
    if not program_id:
        return None
    row = conn.execute(
        "SELECT * FROM programs WHERE id = ? AND account_id = ? AND archived = 0",
        (program_id, account_id),
    ).fetchone()
    if row is None:
        raise HTTPException(404, "program not found on this account")
    return dict(row)


# --- playbook library ----------------------------------------------------------------------------

def _playbook(conn: sqlite3.Connection, key: str, version: int) -> dict:
    row = conn.execute(
        "SELECT * FROM readiness_playbook_definitions "
        "WHERE key = ? AND version = ? AND archived = 0", (key, version),
    ).fetchone()
    if row is None:
        raise HTTPException(404, f"playbook {key} v{version} not found")
    row = dict(row)
    if row["retired_at"] and row["retired_at"] <= _today():
        raise HTTPException(422, f"playbook {key} v{version} was retired on {row['retired_at']}")
    row["allowed_anchors"] = json.loads(row["allowed_anchors_json"] or "[]")
    return row


def _entries(conn: sqlite3.Connection, key: str, version: int) -> list[dict]:
    # VISIBILITY-SPEC §7.4 — derived over every entry in the table rather than over this
    # playbook's, so an entry keeps the same spoken name whichever playbook you reached it from.
    refs = short_ref.playbook_entry_refs(conn)
    rows = conn.execute(
        "SELECT e.*, d.pillar_key, d.label, d.definition_of_done, d.default_scope AS requirement_scope "
        "FROM readiness_playbook_entries e "
        "JOIN readiness_requirement_definitions d "
        "  ON d.key = e.requirement_key AND d.version = e.requirement_version "
        "WHERE e.playbook_key = ? AND e.playbook_version = ? "
        "ORDER BY e.display_order, e.requirement_key",
        (key, version),
    ).fetchall()
    out = []
    for r in rows:
        r = dict(r)
        r["ref"] = refs.get(r["id"])
        out.append(r)
    return out


def list_playbooks(conn: sqlite3.Connection) -> dict:
    """§13.3 — the library, with every version still selectable.

    Unlike the definition tables, more than one version of a playbook is live at a time: an account
    stays on the version it instantiated until an explicit upgrade moves it, so the version it is
    on has to remain readable.
    """
    out = []
    for row in conn.execute(
        "SELECT * FROM readiness_playbook_definitions WHERE archived = 0 "
        "ORDER BY key, version"
    ).fetchall():
        row = dict(row)
        row["allowed_anchors"] = json.loads(row["allowed_anchors_json"] or "[]")
        row.pop("allowed_anchors_json", None)
        row["entries"] = _entries(conn, row["key"], row["version"])
        out.append(row)
    return {"playbooks": out}


# --- plans and instantiation ------------------------------------------------------------------

def _active_plan(conn: sqlite3.Connection, account_id: str, program_id: str | None,
                       playbook_key: str) -> dict | None:
    row = conn.execute(
        "SELECT * FROM readiness_plans "
        "WHERE account_id = ? AND ifnull(program_id,'') = ? AND playbook_key = ? "
        "  AND status = 'active' AND archived = 0",
        (account_id, program_id or "", playbook_key),
    ).fetchone()
    return dict(row) if row else None


def instantiate(conn: sqlite3.Connection, account_id: str, *, playbook_key: str,
                playbook_version: int, anchor_type: str | None = None,
                anchor_date: str | None = None, program_id: str | None = None,
                excluded: list[str] | None = None, actor_id: str | None = None,
                note: str | None = None, upgrade: bool = False,
                compatibility: bool = False) -> dict:
    """§13.4 — instantiate a playbook version against one scope.

    Nothing is marked complete here. Instantiating a plan states an expectation; it says nothing
    about what has happened, and a plan that seeded itself as partly done would be asserting
    evidence it has never seen.
    """
    _account(conn, account_id)
    program = _program(conn, account_id, program_id)
    playbook = _playbook(conn, playbook_key, int(playbook_version))

    if (playbook_key, int(playbook_version)) == COMPATIBILITY_PLAYBOOK and not compatibility:
        raise HTTPException(
            422,
            "the checklist-compatibility playbook is instantiated by the compatibility migration, "
            "not by hand",
        )

    if playbook["default_scope"] == "program" and program is None:
        raise HTTPException(422, f"playbook {playbook_key} is program-scoped and needs a program_id")
    if playbook["default_scope"] == "account" and program is not None:
        raise HTTPException(422, f"playbook {playbook_key} is account-scoped; omit program_id")

    anchor_type = anchor_type or playbook["default_anchor"]
    if anchor_type not in playbook["allowed_anchors"]:
        raise HTTPException(
            422,
            f"anchor {anchor_type!r} is not allowed by {playbook_key} v{playbook_version} "
            f"(allowed: {', '.join(playbook['allowed_anchors'])})",
        )
    if not anchor_date and anchor_type == "kickoff" and program and program.get("kickoff_date"):
        anchor_date = program["kickoff_date"]
    if not anchor_date:
        raise HTTPException(422, f"anchor_date is required for the {anchor_type} anchor")
    anchor_date = _iso(anchor_date, "anchor_date")

    entries = _entries(conn, playbook_key, int(playbook_version))
    if not entries:
        raise HTTPException(422, f"playbook {playbook_key} v{playbook_version} has no entries")

    excluded = list(excluded or [])
    known = {e["requirement_key"] for e in entries}
    optional = {e["requirement_key"] for e in entries if e["necessity"] == "optional"}
    unknown = [k for k in excluded if k not in known]
    if unknown:
        raise HTTPException(422, f"not in this playbook version: {', '.join(sorted(unknown))}")
    # Only optional entries may be dropped. Excluding a required one would let the plan quietly
    # disagree with the playbook it claims to be an instance of.
    forced = [k for k in excluded if k not in optional]
    if forced:
        raise HTTPException(
            422, f"required entries cannot be excluded: {', '.join(sorted(forced))}; "
                 "mark the requirement not applicable instead, which records a reason and an actor",
        )

    existing = _active_plan(conn, account_id, program_id, playbook_key)
    if existing and not upgrade:
        raise HTTPException(
            409,
            f"an active {playbook_key} plan already exists for this scope "
            f"(v{existing['playbook_version']}); use the upgrade route to move it",
        )

    carried: dict[str, dict] = {}
    if existing:
        # An upgrade keeps the operator-recorded facts it can honestly keep: a legacy tick and the
        # record it came from. Nothing evaluative is carried, because nothing evaluative is stored.
        for row in conn.execute(
            "SELECT * FROM readiness_plan_instances WHERE plan_id = ? AND archived = 0",
            (existing["id"],),
        ).fetchall():
            carried[row["requirement_key"]] = dict(row)

    ts = now_utc()
    actor = actor_id or audit.DEFAULT_ACTOR
    plan_id = new_id()
    created: list[dict] = []
    with conn:
        if existing:
            conn.execute(
                "UPDATE readiness_plans SET status = 'superseded', updated_at = ? "
                "WHERE id = ?", (ts, existing["id"]),
            )
            conn.execute(
                "UPDATE readiness_plan_instances SET archived = 1, archived_at = ?, "
                "archived_by = ?, updated_at = ? WHERE plan_id = ?",
                (ts, actor, ts, existing["id"]),
            )
            # The audit vocabulary is the fixed five from migration 0001; the specific verb rides
            # in the payload rather than widening a constraint every reader already relies on.
            audit.record(conn, object_type="readiness_plan",
                         object_id=existing["id"], action="update",
                         before={"status": "active"},
                         after={"status": "superseded", "event": "superseded_by_upgrade"},
                         actor_id=actor)
        conn.execute(
            "INSERT INTO readiness_plans "
            "(id,account_id,program_id,playbook_key,playbook_version,anchor_type,anchor_date,"
            " excluded_requirements_json,status,supersedes_id,actor_id,note,created_at,updated_at) "
            "VALUES (?,?,?,?,?,?,?,?,'active',?,?,?,?,?)",
            (plan_id, account_id, program_id, playbook_key, int(playbook_version),
             anchor_type, anchor_date, json.dumps(sorted(excluded)),
             existing["id"] if existing else None, actor, note, ts, ts),
        )
        for entry in entries:
            if entry["requirement_key"] in excluded:
                continue
            prior = carried.get(entry["requirement_key"])
            due_rule = {"anchor": anchor_type, "offset_days": entry["offset_days"]}
            row = {
                "id": new_id(),
                "plan_id": plan_id,
                "account_id": account_id,
                "program_id": program_id,
                "playbook_key": playbook_key,
                "playbook_version": int(playbook_version),
                "requirement_key": entry["requirement_key"],
                "requirement_version": entry["requirement_version"],
                "pillar_key": entry["pillar_key"],
                "necessity": entry["necessity"],
                "due_rule_json": json.dumps(due_rule),
                "due_date": _shift(anchor_date, entry["offset_days"]),
                "recorded_complete": prior["recorded_complete"] if prior else 0,
                "recorded_complete_on": prior["recorded_complete_on"] if prior else None,
                "recorded_complete_note": prior["recorded_complete_note"] if prior else None,
                "compatibility_source_type": prior["compatibility_source_type"] if prior else None,
                "compatibility_source_id": prior["compatibility_source_id"] if prior else None,
                "created_at": ts,
                "updated_at": ts,
            }
            conn.execute(
                f"INSERT INTO readiness_plan_instances ({', '.join(row)}) "
                f"VALUES ({', '.join('?' * len(row))})", tuple(row.values()),
            )
            created.append(row)
        audit.record(conn, object_type="readiness_plan", object_id=plan_id,
                     action="create",
                     before={"playbook_version": existing["playbook_version"]} if existing else None,
                     after={"playbook_key": playbook_key, "playbook_version": int(playbook_version),
                            "anchor_type": anchor_type, "anchor_date": anchor_date,
                            "excluded": sorted(excluded), "instances": len(created),
                            "event": "upgrade" if existing else "instantiate"},
                     actor_id=actor)
    return plan(conn, plan_id)


def plan(conn: sqlite3.Connection, plan_id: str) -> dict:
    row = conn.execute(
        "SELECT * FROM readiness_plans WHERE id = ? AND archived = 0", (plan_id,)
    ).fetchone()
    if row is None:
        raise HTTPException(404, "plan not found")
    row = dict(row)
    row["excluded_requirements"] = json.loads(row.pop("excluded_requirements_json") or "[]")
    row["instances"] = [_instance_public(dict(r)) for r in conn.execute(
        "SELECT * FROM readiness_plan_instances WHERE plan_id = ? AND archived = 0 "
        "ORDER BY (due_date IS NULL), due_date, requirement_key", (plan_id,),
    ).fetchall()]
    return row


def _instance_public(row: dict) -> dict:
    row = dict(row)
    row["due_rule"] = json.loads(row.pop("due_rule_json") or "{}")
    row["recorded_complete"] = bool(row["recorded_complete"])
    row["archived"] = bool(row["archived"])
    return row


def list_plans(conn: sqlite3.Connection, account_id: str,
                     program_id: str | None = None) -> dict:
    _account(conn, account_id)
    sql = ("SELECT * FROM readiness_plans WHERE account_id = ? AND archived = 0")
    params: list = [account_id]
    if program_id:
        # An account-wide plan stays visible inside a program scope: it is in force there too.
        sql += " AND (program_id = ? OR program_id IS NULL)"
        params.append(program_id)
    rows = [plan(conn, r["id"]) for r in
            conn.execute(sql + " ORDER BY status, playbook_key, created_at", tuple(params))]
    return {"plans": rows}


# --- version upgrade -------------------------------------------------------------------------------

def _definition_label(conn: sqlite3.Connection, key: str, version: int) -> str:
    """The definition's own label for a pinned version, or the key humanised the same way
    `merged_plan` humanises it when the definition is no longer readable."""
    row = conn.execute(
        "SELECT label FROM readiness_requirement_definitions WHERE key = ? AND version = ?",
        (key, version),
    ).fetchone()
    return row["label"] if row else key.replace("_", " ").capitalize()


# VISIBILITY-SPEC §5. The population the instantiation counts are taken over, named once so the
# label and the query can never describe different sets. Live plans everywhere — not this
# account's — because the question the preview is answering is "has this step ever fired at all",
# and one account's silence is not an answer to it.
_ENTRY_USAGE_SCOPE = "live plans across every account"

_ENTRY_USAGE_SQL = """
SELECT i.requirement_key AS requirement_key,
       i.requirement_version AS requirement_version,
       COUNT(*) AS instantiated,
       SUM(CASE WHEN i.recorded_complete = 1 THEN 1 ELSE 0 END) AS recorded_complete
FROM readiness_plan_instances i
JOIN readiness_plans p ON p.id = i.plan_id
WHERE i.archived = 0 AND p.archived = 0 AND p.status = 'active'
GROUP BY i.requirement_key, i.requirement_version
"""


def _entry_usage(conn: sqlite3.Connection, entries: list[dict]) -> list[dict]:
    """§5.1 — two planning counts per entry of the incoming version, and nothing else.

    Both counts come from `readiness_plan_instances`, which stores planning facts: an instantiation
    is a row a plan created, and `recorded_complete` is an operator-recorded tick carried across
    from a legacy checkbox. **Neither is a readiness state and no evaluator runs here** (§5.1.2) —
    reading one would be both expensive and a category error, since the preview is a question about
    the plan and readiness has its own surface and its own vocabulary.

    `recorded_complete` of 0 across every instantiation is a count. It is not "not working", not
    "broken", and not a failure rate; nothing here divides one number by the other. The operator
    draws the inference (§5.1.5).
    """
    totals = {(row["requirement_key"], row["requirement_version"]): row
              for row in conn.execute(_ENTRY_USAGE_SQL).fetchall()}
    out = []
    for entry in entries:
        key = (entry["requirement_key"], entry["requirement_version"])
        row = totals.get(key)
        out.append({
            "requirement_key": entry["requirement_key"],
            "requirement_version": entry["requirement_version"],
            "label": entry["label"],
            "ref": entry.get("ref"),
            "necessity": entry["necessity"],
            # Zero, never absent (§5.1.4). A step that has never fired is exactly what an operator
            # deciding whether to keep it needs to see, and an omitted row would hide it.
            "instantiated_on_plans": int(row["instantiated"]) if row else 0,
            "recorded_complete_count": int(row["recorded_complete"] or 0) if row else 0,
        })
    return out


def preview_upgrade(conn: sqlite3.Connection, account_id: str, *, playbook_key: str,
                    to_version: int, program_id: str | None = None) -> dict:
    """§13.4/§13.9 — additions, removals, timing changes, and definition changes, applying nothing.

    The point is that nothing about an active plan moves invisibly. An operator sees which
    conditions arrive, which leave, which dates shift and by how much, and which pinned definition
    versions change, before deciding.
    """
    _account(conn, account_id)
    _program(conn, account_id, program_id)
    current = _active_plan(conn, account_id, program_id, playbook_key)
    if current is None:
        raise HTTPException(404, f"no active {playbook_key} plan in this scope to upgrade")
    to_version = int(to_version)
    if to_version == current["playbook_version"]:
        raise HTTPException(422, f"this scope is already on {playbook_key} v{to_version}")
    _playbook(conn, playbook_key, to_version)

    anchor = current["anchor_date"]
    before = {r["requirement_key"]: dict(r) for r in conn.execute(
        "SELECT * FROM readiness_plan_instances WHERE plan_id = ? AND archived = 0",
        (current["id"],),
    ).fetchall()}
    after = {e["requirement_key"]: e for e in _entries(conn, playbook_key, to_version)}

    additions, removals, timing, definitions, necessity, retained = [], [], [], [], [], []
    for key, entry in sorted(after.items(), key=lambda kv: kv[1]["display_order"]):
        old = before.get(key)
        new_due = _shift(anchor, entry["offset_days"])
        if old is None:
            additions.append({"requirement_key": key, "label": entry["label"],
                              "pillar_key": entry["pillar_key"],
                              "requirement_version": entry["requirement_version"],
                              "necessity": entry["necessity"], "due_date": new_due})
            continue
        retained.append(key)
        if (old["due_date"] or None) != (new_due or None):
            timing.append({"requirement_key": key, "label": entry["label"],
                           "from_due_date": old["due_date"], "to_due_date": new_due,
                           "from_offset_days": json.loads(old["due_rule_json"] or "{}")
                           .get("offset_days"),
                           "to_offset_days": entry["offset_days"]})
        if old["requirement_version"] != entry["requirement_version"]:
            definitions.append({"requirement_key": key, "label": entry["label"],
                                "from_version": old["requirement_version"],
                                "to_version": entry["requirement_version"]})
        if old["necessity"] != entry["necessity"]:
            necessity.append({"requirement_key": key, "label": entry["label"],
                              "from_necessity": old["necessity"],
                              "to_necessity": entry["necessity"]})
    for key, old in sorted(before.items()):
        if key not in after:
            removals.append({"requirement_key": key, "pillar_key": old["pillar_key"],
                             # Named in the same words as every other group. The instance row
                             # stores no label, so it is read from the definition version the plan
                             # pinned — and where that definition has been retired, humanised the
                             # way `merged_plan` humanises the same key, rather than shown raw. The
                             # removals are the rows that take a recorded tick with them, so they
                             # are the last ones that should read as an internal key.
                             "label": _definition_label(conn, key, old["requirement_version"]),
                             "due_date": old["due_date"],
                             "recorded_complete": bool(old["recorded_complete"])})

    return {
        "applied": False,
        "scope": {"account_id": account_id, "program_id": program_id},
        "playbook_key": playbook_key,
        "from_version": current["playbook_version"],
        "to_version": to_version,
        "anchor_type": current["anchor_type"],
        "anchor_date": anchor,
        "additions": additions,
        "removals": removals,
        "timing_changes": timing,
        "definition_changes": definitions,
        "necessity_changes": necessity,
        "retained_keys": sorted(retained),
        # Named explicitly so nobody has to infer it from an empty diff: an upgrade removes rows,
        # and a removed row takes its recorded tick with it.
        "recorded_complete_at_risk": [r["requirement_key"] for r in removals
                                      if r["recorded_complete"]],
        # VISIBILITY-SPEC §5. How each entry of the incoming version has actually been used, so a
        # step nobody has ever ticked is visible at the moment of deciding to keep it. The scope
        # sentence is authored here because a count over this account and a count over every
        # account are different numbers, and only the server knows which one it ran (§5.1.3).
        "entry_usage": _entry_usage(conn, list(after.values())),
        "entry_usage_scope": _ENTRY_USAGE_SCOPE,
    }


def apply_upgrade(conn: sqlite3.Connection, account_id: str, *, playbook_key: str,
                  to_version: int, program_id: str | None = None,
                  excluded: list[str] | None = None, actor_id: str | None = None,
                  note: str | None = None) -> dict:
    """Move a scope onto a new playbook version, keeping the anchor it was instantiated with."""
    current = _active_plan(conn, account_id, program_id, playbook_key)
    if current is None:
        raise HTTPException(404, f"no active {playbook_key} plan in this scope to upgrade")
    preview = preview_upgrade(conn, account_id, playbook_key=playbook_key,
                              to_version=int(to_version), program_id=program_id)
    result = instantiate(
        conn, account_id, playbook_key=playbook_key, playbook_version=int(to_version),
        anchor_type=current["anchor_type"], anchor_date=current["anchor_date"],
        program_id=program_id, excluded=excluded, actor_id=actor_id, note=note, upgrade=True,
        compatibility=(playbook_key, int(to_version)) == COMPATIBILITY_PLAYBOOK,
    )
    return {"applied": True, "plan": result, "diff": {**preview, "applied": True}}


# --- exceptions --------------------------------------------------------------------------------

def _requirement_definition(conn: sqlite3.Connection, requirement_key: str) -> dict:
    row = conn.execute(
        "SELECT * FROM readiness_requirement_definitions "
        "WHERE key = ? AND retired_at IS NULL AND archived = 0", (requirement_key,)
    ).fetchone()
    if row is None:
        raise HTTPException(404, f"no live requirement definition for {requirement_key!r}")
    return dict(row)


def set_exception(conn: sqlite3.Connection, account_id: str, *, requirement_key: str, kind: str,
                  reason: str, program_id: str | None = None, decided_on: str | None = None,
                  expires_on: str | None = None, actor_id: str | None = None) -> dict:
    """§13.2/§13.7 — record a `not_applicable` decision or a waiver, with reason and actor.

    Neither kind can satisfy the requirement. `not_applicable` stops it being evaluated;
    `waiver` leaves the state exactly where the evidence put it and only silences the outstanding
    ask. There is deliberately no third kind.
    """
    _account(conn, account_id)
    _program(conn, account_id, program_id)
    definition = _requirement_definition(conn, requirement_key)
    if kind not in EXCEPTION_KINDS:
        raise HTTPException(422, f"kind must be one of {', '.join(EXCEPTION_KINDS)}")
    reason = (reason or "").strip()
    if len(reason) < MIN_REASON_LENGTH:
        raise HTTPException(
            422, f"reason must be at least {MIN_REASON_LENGTH} characters; an unexplained "
                 "suppression is indistinguishable from a bug",
        )
    decided_on = _iso(decided_on or _today(), "decided_on")
    if kind == "waiver":
        # A waiver with no end date is a permanent gap wearing a temporary label.
        if not expires_on:
            raise HTTPException(422, "a waiver must carry an expiry date")
        expires_on = _iso(expires_on, "expires_on")
        if expires_on < decided_on:
            raise HTTPException(422, "expires_on cannot precede decided_on")
    elif expires_on:
        expires_on = _iso(expires_on, "expires_on")

    actor = actor_id or audit.DEFAULT_ACTOR
    ts = now_utc()
    prior = conn.execute(
        "SELECT * FROM readiness_exceptions "
        "WHERE account_id = ? AND ifnull(program_id,'') = ? AND requirement_key = ? AND kind = ? "
        "  AND revoked_at IS NULL AND archived = 0",
        (account_id, program_id or "", requirement_key, kind),
    ).fetchone()

    exception_id = new_id()
    with conn:
        if prior is not None:
            # Replacing a decision revokes the old one rather than editing it: the panel shows a
            # history, and a history that is silently rewritten is not one.
            conn.execute(
                "UPDATE readiness_exceptions SET revoked_at = ?, revoked_by = ?, "
                "revoked_reason = 'superseded by a later decision', updated_at = ? WHERE id = ?",
                (ts, actor, ts, prior["id"]),
            )
            audit.record(conn, object_type="readiness_exception", object_id=prior["id"],
                         action="update", before=dict(prior),
                         after={"revoked_at": ts, "event": "superseded_by_later_decision"},
                         actor_id=actor)
        conn.execute(
            "INSERT INTO readiness_exceptions "
            "(id,account_id,program_id,requirement_key,plan_instance_id,kind,reason,actor_id,"
            " decided_on,expires_on,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (exception_id, account_id, program_id, requirement_key,
             _instance_id_for(conn, account_id, program_id, requirement_key), kind, reason, actor,
             decided_on, expires_on, ts, ts),
        )
        audit.record(conn, object_type="readiness_exception", object_id=exception_id,
                     action="create",
                     after={"account_id": account_id, "program_id": program_id,
                            "requirement_key": requirement_key, "kind": kind, "reason": reason,
                            "decided_on": decided_on, "expires_on": expires_on},
                     actor_id=actor)
    return {"exception": _exception_row(conn, exception_id),
            "requirement": {"key": requirement_key, "label": definition["label"],
                            "pillar_key": definition["pillar_key"]}}


def _instance_id_for(conn: sqlite3.Connection, account_id: str, program_id: str | None,
                     requirement_key: str) -> str | None:
    """The plan instance this decision annotates, if a plan happens to cover the requirement.

    It is a convenience link, not a precondition: a condition can be excused whether or not anyone
    has instantiated a playbook that schedules it.
    """
    row = conn.execute(
        "SELECT id FROM readiness_plan_instances "
        "WHERE account_id = ? AND ifnull(program_id,'') = ? AND requirement_key = ? "
        "  AND archived = 0 ORDER BY created_at DESC LIMIT 1",
        (account_id, program_id or "", requirement_key),
    ).fetchone()
    return row["id"] if row else None


def revoke_exception(conn: sqlite3.Connection, exception_id: str, *, reason: str,
                     actor_id: str | None = None) -> dict:
    row = conn.execute(
        "SELECT * FROM readiness_exceptions WHERE id = ? AND archived = 0", (exception_id,)
    ).fetchone()
    if row is None:
        raise HTTPException(404, "exception not found")
    if row["revoked_at"]:
        raise HTTPException(409, "exception is already revoked")
    reason = (reason or "").strip()
    if len(reason) < MIN_REASON_LENGTH:
        raise HTTPException(422, f"reason must be at least {MIN_REASON_LENGTH} characters")
    actor = actor_id or audit.DEFAULT_ACTOR
    ts = now_utc()
    with conn:
        conn.execute(
            "UPDATE readiness_exceptions SET revoked_at = ?, revoked_by = ?, revoked_reason = ?, "
            "updated_at = ? WHERE id = ?", (ts, actor, reason, ts, exception_id),
        )
        audit.record(conn, object_type="readiness_exception", object_id=exception_id,
                     action="update", before=dict(row),
                     after={"revoked_at": ts, "revoked_reason": reason, "event": "revoke"},
                     actor_id=actor)
    return _exception_row(conn, exception_id)


def _exception_status(row: dict, as_of: str) -> str:
    if row["revoked_at"]:
        return "revoked"
    if row["expires_on"] and row["expires_on"] < as_of:
        return "lapsed"
    return "live"


def _exception_row(conn: sqlite3.Connection, exception_id: str, as_of: str | None = None) -> dict:
    row = conn.execute("SELECT * FROM readiness_exceptions WHERE id = ?",
                       (exception_id,)).fetchone()
    if row is None:
        raise HTTPException(404, "exception not found")
    row = dict(row)
    row["status"] = _exception_status(row, as_of or _today())
    row["scope"] = "program" if row["program_id"] else "account"
    row["archived"] = bool(row["archived"])
    return row


def exception_history(conn: sqlite3.Connection, account_id: str, requirement_key: str,
                      program_id: str | None = None, as_of: str | None = None) -> list[dict]:
    """§13.7 — every decision ever recorded for this requirement in this scope, newest first.

    Revoked and lapsed rows stay. A suppression that disappeared once it stopped applying would
    leave a state change in the record with nothing to explain it.
    """
    as_of = as_of or _today()
    rows = conn.execute(
        "SELECT * FROM readiness_exceptions "
        "WHERE account_id = ? AND requirement_key = ? AND archived = 0 "
        "  AND (program_id IS NULL OR program_id = ?) "
        "ORDER BY decided_on DESC, created_at DESC", (account_id, requirement_key, program_id),
    ).fetchall()
    out = []
    for row in rows:
        row = dict(row)
        row["status"] = _exception_status(row, as_of)
        row["scope"] = "program" if row["program_id"] else "account"
        row["archived"] = bool(row["archived"])
        out.append(row)
    return out


# --- the merged plan view (§13.3, §13.6) ----------------------------------------------------------

def _readiness_readings(result: dict) -> dict[tuple[str | None, str], dict]:
    """Flatten a readiness response into one reading per (program, requirement key).

    A pillar that was not evaluated — inapplicable, not due, or unreadable — still contributes a
    reading for each of its requirement definitions, carrying the pillar's own words. Dropping it
    would leave a scheduled requirement with no reading at all, which reads as an omission rather
    than as the deliberate silence it is.
    """
    readings: dict[tuple[str | None, str], dict] = {}

    def absorb(pillar: dict, program_id: str | None, program_name: str | None) -> None:
        shared = {
            "pillar_key": pillar["key"], "pillar_label": pillar["label"],
            "pillar_state": pillar["state"], "applicability": pillar["applicability"],
            "pillar_scope": pillar.get("scope"),
            "program_id": program_id, "program_name": program_name,
        }
        if pillar.get("components"):
            for component in pillar["components"]:
                key = component.get("definition_key") or component["key"]
                readings[(program_id, key)] = {
                    **shared,
                    "requirement_key": key,
                    "requirement_version": component.get("definition_version"),
                    "label": component.get("label"),
                    "definition_of_done": component.get("definition_of_done"),
                    "state": component["state"],
                    "freshness": component["freshness"],
                    "assessed_through": component.get("assessed_through"),
                    "provenance": component.get("provenance"),
                    "reason": component.get("reason"),
                    "evidence": component.get("evidence") or [],
                    "missing": component.get("missing") or [],
                    "applicability_override": component.get("applicability_override"),
                    "waiver": component.get("waiver"),
                    # Which evaluator produced this state, carried verbatim rather than
                    # re-derived. A caller that has to tell "unsatisfied" apart from
                    # "unreadable" needs the evaluator's identity, and the component is the
                    # only place that knows it.
                    "evaluator_key": component.get("evaluator_key"),
                    "evaluator_version": component.get("evaluator_version"),
                    # And what it was configured with (VISIBILITY-SPEC §7.2), for the same
                    # reason one step further: the identity says which rule was asked for, the
                    # configuration says what it was asked to look for, and only the second
                    # survives an evaluator that could not be resolved at all.
                    "evaluator_config": component.get("evaluator_config"),
                    "ref": component.get("ref"),
                    "evaluated": True,
                }
            return
        # No components: the pillar answered as a whole. Its requirement keys are unknown from
        # here, so the caller matches by pillar instead (see `_reading_for`).
        readings[(program_id, f"pillar:{pillar['key']}")] = {
            **shared, "requirement_key": None, "requirement_version": None,
            "label": pillar["label"], "definition_of_done": None,
            "state": pillar["state"], "freshness": pillar["freshness"],
            "assessed_through": None, "provenance": None, "reason": pillar.get("reason"),
            "evidence": [], "missing": [], "applicability_override": None, "waiver": None,
            "evaluated": False,
        }

    for pillar in result.get("pillars", []):
        absorb(pillar, None, None)
    for entry in result.get("programs", []):
        for pillar in entry.get("pillars", []):
            absorb(pillar, entry.get("program_id"), entry.get("program_name"))
    return readings


def _reading_for(readings: dict, program_id: str | None, requirement_key: str,
                 pillar_key: str) -> dict | None:
    """A program's own reading first, then the account-scoped one, then the pillar's silence.

    Falling back to the account reading is what keeps an account-wide condition visible inside a
    selected program (§13.6); falling back the other way would let one program's evidence answer
    for another, which §3.1 of the readiness spec forbids.
    """
    for scope in ([program_id, None] if program_id else [None]):
        hit = readings.get((scope, requirement_key))
        if hit:
            return hit
    for scope in ([program_id, None] if program_id else [None]):
        hit = readings.get((scope, f"pillar:{pillar_key}"))
        if hit:
            return hit
    return None


def merged_plan(conn: sqlite3.Connection, account_id: str, program_id: str | None = None,
                readiness_result: dict | None = None) -> dict:
    """§13.3 — plan instances merged with live readiness, by key and version.

    The instance contributes scheduling and exception facts only. Every evaluative field is copied
    from readiness verbatim, so there is exactly one place a state can come from.
    """
    _account(conn, account_id)
    _program(conn, account_id, program_id)
    if readiness_result is None:
        readiness_result = readiness.evaluate(conn, account_id, program_id)
    readings = _readiness_readings(readiness_result)
    live_versions = {
        (r["key"], r["version"]) for r in conn.execute(
            "SELECT key, version FROM readiness_requirement_definitions "
            "WHERE retired_at IS NULL AND archived = 0"
        ).fetchall()
    }

    sql = ("SELECT * FROM readiness_plan_instances WHERE account_id = ? AND archived = 0")
    params: list = [account_id]
    if program_id:
        sql += " AND (program_id = ? OR program_id IS NULL)"
        params.append(program_id)
    rows = [dict(r) for r in conn.execute(sql, tuple(params))]

    today = _today()
    out: list[dict] = []
    for row in rows:
        pinned_live = (row["requirement_key"], row["requirement_version"]) in live_versions
        reading = _reading_for(readings, row["program_id"] or program_id,
                               row["requirement_key"], row["pillar_key"])
        due = row["due_date"]
        merged = {
            "instance_id": row["id"],
            "requirement_key": row["requirement_key"],
            "requirement_version": row["requirement_version"],
            "pillar_key": row["pillar_key"],
            "scope": {"account_id": account_id, "program_id": row["program_id"]},
            "necessity": row["necessity"],
            "due_rule": json.loads(row["due_rule_json"] or "{}"),
            "due_date": due,
            "overdue": bool(due and due < today and (reading or {}).get("state") != "met"),
            "recorded_complete": bool(row["recorded_complete"]),
            "recorded_complete_on": row["recorded_complete_on"],
            "playbook": {"key": row["playbook_key"], "version": row["playbook_version"]},
            "compatibility_source": (
                {"type": row["compatibility_source_type"], "id": row["compatibility_source_id"]}
                if row["compatibility_source_type"] else None
            ),
            # A pinned version whose definition has been retired is shown, and shown as legacy.
            # Inventing a state for it from the current definition would be answering a question
            # the plan never asked.
            "legacy": not pinned_live,
        }
        if pinned_live and reading is not None:
            merged.update({k: reading[k] for k in (
                "label", "definition_of_done", "state", "freshness", "applicability", "reason",
                "evidence", "missing", "assessed_through", "provenance", "pillar_label",
                "applicability_override", "waiver", "evaluated", "program_name",
                # `evaluator_config` rides along with the key that names the evaluator
                # (VISIBILITY-SPEC §7.2) so the plan row can say what was configured, not only
                # which rule was asked for.
                "evaluator_key", "evaluator_version", "evaluator_config", "ref",
            ) if k in reading})
        else:
            merged.update({
                "label": row["requirement_key"].replace("_", " ").capitalize(),
                "definition_of_done": None, "state": None, "freshness": None,
                "applicability": None,
                "reason": ("This plan is pinned to a requirement definition version that is no "
                           "longer live, so no state is claimed for it."
                           if not pinned_live else
                           "No readiness reading is available in this scope."),
                "evidence": [], "missing": [], "applicability_override": None, "waiver": None,
                "evaluated": False,
            })
        out.append(merged)

    out.sort(key=lambda r: (0 if r["necessity"] == "required" else 1,
                            0 if r["due_date"] else 1, r["due_date"] or "",
                            r["pillar_key"], r["requirement_key"]))
    return {
        "scope": {"account_id": account_id, "program_id": program_id},
        "requirements": out,
        "coverage": readiness_result.get("coverage"),
    }
