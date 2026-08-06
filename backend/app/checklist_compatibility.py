"""Checklist → plan-instance compatibility migration (`ACCOUNT-PATH-SPEC.md` §13.5).

Two rules do most of the work here, and both are about refusing to guess:

**Only an exact `template_key` maps.** §13.5.2 forbids fuzzy label matching, and the reason is not
tidiness — a checklist label and a requirement label can read almost identically while meaning
different things, and a wrong mapping silently attaches a completed tick to a condition nobody
ever checked. An unmatched item stays legible as a legacy row instead.

**A tick is a planning fact, never evidence.** A `done` checklist item lands as
`recorded_complete` on the instance and nothing more. No readiness state moves, because readiness
has no writable state to move; if the underlying record really satisfies the condition, readiness
is already reporting `met` from the record itself, and if it is not, a checkbox from the old
surface is not the thing that should change its mind.

The migration runs on demand per account, is idempotent, and deletes nothing. `checklist_items`
stays exactly where it is until a separate deprecation decision (§13.5, closing note).
"""
from __future__ import annotations

import json
import sqlite3

from fastapi import HTTPException

from . import audit, playbooks
from .db import new_id, now_utc

PLAYBOOK_KEY, PLAYBOOK_VERSION = playbooks.COMPATIBILITY_PLAYBOOK


def _mapping(conn: sqlite3.Connection) -> dict[str, dict]:
    return {r["template_key"]: dict(r) for r in conn.execute(
        "SELECT * FROM readiness_checklist_requirement_map"
    ).fetchall()}


def _scope_key(row: dict) -> tuple[str, str]:
    return (row["account_id"], row["program_id"] or "")


def migrate_account(conn: sqlite3.Connection, account_id: str, *, dry_run: bool = False,
                    actor_id: str | None = None) -> dict:
    """Map one account's checklist items onto plan instances and report what happened.

    Returns the §13.5.7 report whether or not anything is written, so `dry_run` is a real preview
    of the same computation rather than a second code path that might disagree with it.
    """
    playbooks._account(conn, account_id)
    mapping = _mapping(conn)
    actor = actor_id or audit.DEFAULT_ACTOR
    ts = now_utc()

    items = [dict(r) for r in conn.execute(
        "SELECT * FROM checklist_items WHERE account_id = ? AND archived = 0 "
        "ORDER BY section, due_date, label", (account_id,),
    ).fetchall()]

    entries = {e["requirement_key"]: e for e in
               playbooks._entries(conn, PLAYBOOK_KEY, PLAYBOOK_VERSION)}

    mapped: list[dict] = []
    unmatched: list[dict] = []
    ambiguous: list[dict] = []
    # One scope can hold one instance of a requirement. Two checklist items in the same scope that
    # map to the same requirement are a genuine ambiguity about which one the plan means, so the
    # first is taken and the rest are reported rather than silently overwriting each other.
    claimed: dict[tuple[str, str, str], dict] = {}
    for item in items:
        target = mapping.get(item["template_key"] or "")
        if target is None:
            unmatched.append({"checklist_item_id": item["id"], "template_key": item["template_key"],
                              "label": item["label"], "section": item["section"],
                              "status": item["status"], "program_id": item["program_id"],
                              "reason": "no exact template_key mapping"})
            continue
        if target["requirement_key"] not in entries:
            unmatched.append({"checklist_item_id": item["id"], "template_key": item["template_key"],
                              "label": item["label"], "section": item["section"],
                              "status": item["status"], "program_id": item["program_id"],
                              "reason": (f"{target['requirement_key']} is mapped but is not in "
                                         f"{PLAYBOOK_KEY} v{PLAYBOOK_VERSION}")})
            continue
        slot = (*_scope_key(item), target["requirement_key"])
        held = claimed.get(slot)
        if held is not None:
            ambiguous.append({
                "requirement_key": target["requirement_key"],
                "program_id": item["program_id"],
                "kept_checklist_item_id": held["item"]["id"],
                "kept_label": held["item"]["label"],
                "other_checklist_item_id": item["id"],
                "other_label": item["label"],
                "reason": ("two checklist items in this scope map to the same requirement; the "
                           "earlier one was used and this one was left as a legacy item"),
            })
            continue
        claimed[slot] = {"item": item, "target": target}

    # Existing instances from a previous run, so a rerun updates rather than duplicates.
    existing = {}
    for row in conn.execute(
        "SELECT * FROM readiness_plan_instances WHERE account_id = ? AND playbook_key = ? "
        "  AND archived = 0", (account_id, PLAYBOOK_KEY),
    ).fetchall():
        row = dict(row)
        existing[(row["account_id"], row["program_id"] or "", row["requirement_key"])] = row

    plans: dict[tuple[str, str], str] = {}
    created = updated = unchanged = 0
    carried_ticks: list[dict] = []
    writes: list[tuple] = []

    for slot, claim in sorted(claimed.items()):
        item, target = claim["item"], claim["target"]
        entry = entries[target["requirement_key"]]
        prior = existing.get(slot)
        recorded = 1 if item["status"] == "done" else 0
        # §13.5.4: an `na` checklist item carries its note across as a proposed exception rather
        # than being applied. Suppressing a condition is a governed decision with an actor, and a
        # migration is not an operator.
        proposed_exception = None
        if item["status"] == "na":
            proposed_exception = {
                "requirement_key": target["requirement_key"],
                "program_id": item["program_id"],
                "kind": "not_applicable",
                "suggested_reason": (item["answer_note"] or "").strip() or None,
                "source_checklist_item_id": item["id"],
            }
        fields = {
            "requirement_version": target["requirement_version"],
            "pillar_key": entry["pillar_key"],
            "necessity": entry["necessity"],
            "due_rule_json": json.dumps({"anchor": "kickoff",
                                         "offset_days": item["due_offset_days"]}),
            "due_date": item["due_date"],
            "recorded_complete": recorded,
            "recorded_complete_on": item["done_on"] if recorded else None,
            "recorded_complete_note": (f"Carried from the {item['section']} checklist item "
                                       f"“{item['label']}”." if recorded else None),
            "compatibility_source_type": "checklist_item",
            "compatibility_source_id": item["id"],
        }
        if prior is None:
            created += 1
            writes.append(("insert", slot, item, fields))
        elif any(prior[k] != v for k, v in fields.items()):
            updated += 1
            writes.append(("update", slot, prior, fields))
        else:
            unchanged += 1
        row = {
            "requirement_key": target["requirement_key"],
            "requirement_version": target["requirement_version"],
            "pillar_key": entry["pillar_key"],
            "program_id": item["program_id"],
            "checklist_item_id": item["id"],
            "template_key": item["template_key"],
            "label": item["label"],
            "due_date": item["due_date"],
            "recorded_complete": bool(recorded),
            "proposed_exception": proposed_exception,
        }
        mapped.append(row)
        if recorded:
            carried_ticks.append(row)

    if not dry_run and writes:
        with conn:
            for kind, slot, source, fields in writes:
                account, program, requirement_key = slot
                program = program or None
                if kind == "insert":
                    plan_id = plans.get((account, program or ""))
                    if plan_id is None:
                        plan_id = _ensure_plan(conn, account, program, source, actor,
                                                           ts)
                        plans[(account, program or "")] = plan_id
                    instance_id = new_id()
                    row = {"id": instance_id, "plan_id": plan_id,
                           "account_id": account, "program_id": program,
                           "playbook_key": PLAYBOOK_KEY, "playbook_version": PLAYBOOK_VERSION,
                           "requirement_key": requirement_key, **fields,
                           "created_at": ts, "updated_at": ts}
                    conn.execute(
                        f"INSERT INTO readiness_plan_instances ({', '.join(row)}) "
                        f"VALUES ({', '.join('?' * len(row))})", tuple(row.values()),
                    )
                    audit.record(conn, object_type="readiness_plan_instance",
                                 object_id=instance_id, action="create",
                                 after={**{k: row[k] for k in
                                           ("requirement_key", "recorded_complete",
                                            "compatibility_source_id")},
                                        "event": "checklist_compatibility_migration"},
                                 actor_id=actor)
                else:
                    sets = ", ".join(f"{k} = ?" for k in fields)
                    conn.execute(
                        f"UPDATE readiness_plan_instances SET {sets}, updated_at = ? WHERE id = ?",
                        (*fields.values(), ts, source["id"]),
                    )
                    audit.record(conn, object_type="readiness_plan_instance",
                                 object_id=source["id"], action="update",
                                 before={k: source[k] for k in fields},
                                 after={**fields,
                                        "event": "checklist_compatibility_migration"},
                                 actor_id=actor)

    # Reported separately from `unmatched`, and the separation is the point rather than tidiness.
    # `unmatched` is a partition of `items`: every checklist item lands in exactly one of mapped,
    # unmatched, or ambiguous, which is what lets a reader trust "mapped N of M". These are not
    # checklist items at all — they are instances this migration already created, whose source has
    # since gone. Appended to `unmatched` they broke the partition (the count could exceed
    # `checklist_items`) and inherited a reason that was untrue of them: they have no template key
    # to match, and they were not left as they are.
    orphaned: list[dict] = []
    for slot, row in sorted(existing.items()):
        if slot not in claimed:
            # The source item was archived or remapped. The instance stays — deleting it would
            # remove the only trace that the tick was ever carried — but it is reported.
            orphaned.append({"instance_id": row["id"],
                             "requirement_key": row["requirement_key"],
                             "checklist_item_id": row["compatibility_source_id"],
                             "recorded_complete": bool(row["recorded_complete"]),
                             "program_id": row["program_id"],
                             "reason": "a migrated instance whose source checklist item is gone"})

    return {
        "account_id": account_id,
        "dry_run": dry_run,
        "playbook": {"key": PLAYBOOK_KEY, "version": PLAYBOOK_VERSION},
        "counts": {"checklist_items": len(items), "mapped": len(mapped),
                   "unmatched": len(unmatched), "ambiguous": len(ambiguous),
                   "orphaned": len(orphaned),
                   "created": created, "updated": updated, "unchanged": unchanged},
        "mapped": mapped,
        "unmatched": unmatched,
        "ambiguous": ambiguous,
        "orphaned": orphaned,
        # §13.5.7. Every one of these carried a `done` tick from the old surface while readiness,
        # reading the records, does not report the condition met. That gap is the whole reason the
        # tick is not treated as evidence, and naming it is more useful than hiding it.
        "evidence_missing": _evidence_missing(conn, account_id, carried_ticks),
    }


def _evidence_missing(conn: sqlite3.Connection, account_id: str,
                      carried: list[dict]) -> list[dict]:
    if not carried:
        return []
    from . import readiness  # local: readiness imports nothing from here, and this keeps it that way

    out = []
    by_scope: dict[str | None, dict] = {}
    for row in carried:
        scope = row["program_id"]
        if scope not in by_scope:
            by_scope[scope] = playbooks._readiness_readings(
                readiness.evaluate(conn, account_id, scope)
            )
        reading = playbooks._reading_for(by_scope[scope], scope, row["requirement_key"],
                                        row["pillar_key"])
        state = (reading or {}).get("state")
        if state == "met":
            continue
        out.append({**row, "readiness_state": state,
                    "note": ("the checklist recorded this complete; readiness reports "
                             f"{state or 'no reading'} from the underlying records")})
    return out


def _ensure_plan(conn: sqlite3.Connection, account_id: str, program_id: str | None,
                       item: dict, actor: str, ts: str) -> str:
    row = conn.execute(
        "SELECT id FROM readiness_plans "
        "WHERE account_id = ? AND ifnull(program_id,'') = ? AND playbook_key = ? "
        "  AND status = 'active' AND archived = 0",
        (account_id, program_id or "", PLAYBOOK_KEY),
    ).fetchone()
    if row is not None:
        return row["id"]
    anchor = None
    if program_id:
        got = conn.execute("SELECT kickoff_date FROM programs WHERE id = ?", (program_id,)).fetchone()
        anchor = got["kickoff_date"] if got else None
    anchor = anchor or item["due_date"] or ts[:10]
    plan_id = new_id()
    conn.execute(
        "INSERT INTO readiness_plans "
        "(id,account_id,program_id,playbook_key,playbook_version,anchor_type,anchor_date,"
        " excluded_requirements_json,status,actor_id,note,created_at,updated_at) "
        "VALUES (?,?,?,?,?,'kickoff',?,'[]','active',?,?,?,?)",
        (plan_id, account_id, program_id, PLAYBOOK_KEY, PLAYBOOK_VERSION, anchor, actor,
         "Created by the checklist compatibility migration.", ts, ts),
    )
    audit.record(conn, object_type="readiness_plan", object_id=plan_id,
                 action="create", after={"playbook_key": PLAYBOOK_KEY,
                                         "playbook_version": PLAYBOOK_VERSION,
                                         "program_id": program_id,
                                         "event": "checklist_compatibility_migration"},
                 actor_id=actor)
    return plan_id


def legacy_items(conn: sqlite3.Connection, account_id: str,
                 program_id: str | None = None) -> list[dict]:
    """§13.5.6 — checklist items with no mapped requirement, still readable in the plan view.

    They are returned as what they are: legacy rows with a status, carrying no readiness axes at
    all. Giving them a synthesised state would put a second, weaker source of truth beside the
    projection.
    """
    mapping = _mapping(conn)
    sql = "SELECT * FROM checklist_items WHERE account_id = ? AND archived = 0"
    params: list = [account_id]
    if program_id:
        sql += " AND (program_id = ? OR program_id IS NULL)"
        params.append(program_id)
    out = []
    for row in conn.execute(sql + " ORDER BY section, due_date, label", tuple(params)).fetchall():
        row = dict(row)
        if (row["template_key"] or "") in mapping:
            continue
        out.append({
            "checklist_item_id": row["id"], "label": row["label"], "detail": row["detail"],
            "section": row["section"], "status": row["status"], "due_date": row["due_date"],
            "done_on": row["done_on"], "program_id": row["program_id"],
            "legacy": True, "state": None, "freshness": None, "applicability": None,
        })
    return out
