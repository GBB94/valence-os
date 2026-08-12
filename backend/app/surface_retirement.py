"""Stage 17 Slice 3 — recorded causes and reversible retirement (`SURFACE-USAGE-SPEC.md` §7).

This is the half of Stage 17 that changes the product, and it is the half that can break something.
The ways it goes wrong are silent: a page still renders, a link still resolves, and something you
needed is just no longer reachable. Nothing in the usage data would ever say so, because the thing
that stopped happening stopped emitting events too. So almost everything here is a refusal.

The rules that carry the weight, each of which reads as pedantry until the day it fires:

- **A cause is recorded before anything moves** (§7.1). The report never proposes a removal; it
  states an observation and asks which of the competing explanations you believe. The vocabulary is
  closed and has no `other`, because a cause code with an escape hatch collects the escape hatch.
  `narrow_but_needed` exists so the vocabulary can express a reason to *keep* — a form that can only
  agree with itself is not a review.
- **The current action is derived, never stored** (§7.3): the latest note per surface. A
  `current_state` column would be a second copy of the answer, and it would win silently.
- **Every action is reversible and `restore` is a first-class command** (§7.2). Restoring writes a
  new row rather than deleting the one it reverses, so a mistaken retirement is visible in the
  record rather than quietly absent from it.
- **`kind` determines which actions exist** (§7.4). Collapsing a modal is a no-op that looks like it
  worked; retiring a tab that deleted its route would scatter dead links found one at a time over
  the following month, each looking like a different bug.
- **A field group holding data is never retired** (§7.6), and the refusal names the count, because a
  refusal you can act on beats one you argue with.
- **No retirement may make a record type, a governed command, or a refusal explanation unreachable**
  (§7.7), evaluated over the whole proposed *set* — two retirements that are each individually safe
  can between them empty a `reaches` set.
- **Nothing here deletes code, and Slice 3 ships no deletion** (§7.9).

Failing closed is right throughout: a wrongly-blocked retirement costs a `collapse` instead; a
wrongly-allowed one costs a refusal nobody can read.
"""
from __future__ import annotations

import sqlite3

from . import audit, surfaces, telemetry
from .db import new_id, now_utc

# §7.1's seven. Closed, ordered as the spec lists them, and with no `other`.
CAUSE_CODES = ("not_needed", "not_found", "misunderstood", "hard_to_use",
               "narrow_but_needed", "superseded", "demo_artifact")

CAUSE_MEANINGS = {
    "not_needed": "The job it does is not a job you have.",
    "not_found": "You did not know it was there, or where.",
    "misunderstood": "You knew it was there and expected it to do something else.",
    "hard_to_use": "You wanted it and it was not worth the effort.",
    "narrow_but_needed": "Rarely relevant, essential when it is. Keep.",
    "superseded": "Another surface does this better now.",
    "demo_artifact": "Only ever exercised while building or demonstrating.",
}

# §7.2's three, escalating, plus the rollback command and the no-op that records a cause without
# moving anything. `none` is what `narrow_but_needed` is usually recorded with.
ACTIONS = ("collapse", "demote", "retire", "restore", "none")
HIDING_ACTIONS = ("collapse", "demote", "retire")

ACTION_MEANINGS = {
    "collapse": ("Stays exactly where it is, closed by default, one click to open. Fixed location, "
                 "varying expansion — the disclosure keeps your spatial memory of the screen."),
    "demote": ("Stays in its current location, closed by default and visually de-emphasized. "
               "It remains one click away; nothing is relocated automatically."),
    "retire": ("No longer offered. The route still resolves, the code is not deleted, and Restore "
               "puts it back."),
    "restore": "Returns the surface to being offered, and says so in the record.",
    "none": "A cause recorded without moving anything.",
}

# §7.4's matrix, as data rather than as branches, so the table in the spec and the behaviour in the
# app are one thing. The trap each row avoids is in the spec; the consequence is here.
AVAILABLE_ACTIONS = {
    "section": ("collapse", "demote", "retire"),
    # A panel has no resting presence, so there is nothing to close and nothing to move. Retiring it
    # stops its *trigger* rendering.
    "panel": ("retire",),
    # A tab cannot be collapsed. Retiring it drops it from the strip; §7.5 keeps the route.
    "tab": ("demote", "retire"),
    # Retiring a command drops it from menus and toolbars and keeps the keyboard shortcut: muscle
    # memory outlives menus, and a shortcut that silently stops working reads as a bug.
    "command": ("demote", "retire"),
    # §7.6. `retire` is absent by construction, not by a check that could be skipped.
    "field_group": ("collapse", "demote"),
}


class RetirementRefused(ValueError):
    """A refusal with a sentence an operator can act on. Never a bare error code."""


# --- the derived current action (§7.3) -----------------------------------------------------------

def current_actions(conn: sqlite3.Connection) -> dict[str, dict]:
    """Latest note per surface. One query, and the only definition of "what is this surface now".

    Ordered by `recorded_on` then `rowid`, because a batch writes every note in one transaction with
    one timestamp and the tie has to break somewhere deterministic.
    """
    rows = conn.execute(
        "SELECT n.* FROM surface_retirement_notes n WHERE n.rowid = ("
        "  SELECT m.rowid FROM surface_retirement_notes m WHERE m.surface_key = n.surface_key "
        "  ORDER BY m.recorded_on DESC, m.rowid DESC LIMIT 1)").fetchall()
    return {row["surface_key"]: dict(row) for row in rows}


def offered_keys(conn: sqlite3.Connection) -> set[str]:
    """Surfaces still offered. `collapse` and `demote` are still offered — they are still reachable.

    Only `retire` removes a surface from what is offered, which is what makes the §7.7 check about
    reachability rather than about prominence.
    """
    current = current_actions(conn)
    return {key for key in surfaces.KEYS
            if current.get(key, {}).get("action") != "retire"}


def state_of(conn: sqlite3.Connection) -> dict[str, dict]:
    """The per-surface retirement state the wrapper reads, for every registered surface.

    Every key is present, including the ones with no note, because a caller that has to distinguish
    "not retired" from "absent from the response" will eventually get it wrong in the direction that
    hides something.
    """
    current = current_actions(conn)
    out = {}
    for surface in surfaces.REGISTRY:
        note = current.get(surface.key)
        action = (note or {}).get("action") or "none"
        out[surface.key] = {
            "surface": surface.key,
            "action": action if action in ACTIONS else "none",
            "cause_code": (note or {}).get("cause_code"),
            "recorded_on": (note or {}).get("recorded_on"),
            "batch_id": (note or {}).get("batch_id"),
            "available_actions": list(AVAILABLE_ACTIONS.get(surface.kind, ())),
            # §7.5's banner text, authored here so the view renders a sentence rather than composes
            # one. A retired route still resolves and says when and why it stopped being offered.
            "retired_notice": (
                f"You retired this view on {(note or {}).get('recorded_on', '')[:10]}."
                if action == "retire" else None),
        }
    return out


# --- §7.6 a field group holding data is never retired --------------------------------------------

def _data_count(conn: sqlite3.Connection, surface) -> int:
    """Rows with a non-null value in any of a field group's declared columns.

    The columns are declared on the registry row rather than inferred, for the same reason `reaches`
    is: inferring them from the code is a static-analysis project this repo does not need, and a
    declaration is a claim a code review sees change.
    """
    total = 0
    for spec in surface.data_columns:
        table, _, column = spec.partition(".")
        if not table or not column:
            continue
        try:
            row = conn.execute(
                f"SELECT COUNT(*) FROM {table} WHERE {column} IS NOT NULL").fetchone()
        except sqlite3.Error:
            # A declared column that does not exist is a registry bug, and the safe reading of an
            # unanswerable "does this hold data" is that it might. Counting it as one row keeps the
            # refusal in place rather than letting a typo unlock a retirement.
            return 1
        total += int(row[0])
    return total


def field_group_refusal(conn: sqlite3.Connection, surface) -> str | None:
    """§7.6's refusal, naming the count. Returns None when the group holds nothing."""
    if surface.kind != "field_group":
        return None
    count = _data_count(conn, surface)
    if count == 0:
        # Still not retirable — `retire` is absent from the matrix for this kind. This branch only
        # says the *data* objection does not apply.
        return None
    return (f"Retiring this would hide {count} record{'s' if count != 1 else ''} that have a value "
            f"here. Collapse instead.")


# --- §7.7 the safety check ----------------------------------------------------------------------

def safety_refusals(conn: sqlite3.Connection, proposed: set[str]) -> list[dict]:
    """What the proposed set of retirements would make unreachable. Evaluated as a set.

    Two retirements that are each individually safe can between them empty a `reaches` set, which is
    exactly why §7.8 applies changes as a reviewed batch and why this takes a set rather than a key.

    "A surface with `explains_refusal` may only be retired if another offered surface carries the
    same refusal" needs a reading the registry can compute: there is no refusal identifier, so a
    peer counts when it also sets `explains_refusal` **and** shares at least one reached record
    type. A surface that explains a refusal and reaches nothing therefore has no possible peer and
    cannot be retired — which is the fail-closed direction, and the right one: a wrongly-blocked
    retirement costs a `collapse`, a wrongly-allowed one costs a refusal nobody can read.
    """
    still_offered = offered_keys(conn) - set(proposed)
    remaining = [surfaces.BY_KEY[key] for key in still_offered if key in surfaces.BY_KEY]

    reachable: set[str] = set()
    provided: set[str] = set()
    refusal_peers: list[surfaces.Surface] = []
    for surface in remaining:
        reachable.update(surface.reaches)
        provided.update(surface.provides)
        if surface.explains_refusal:
            refusal_peers.append(surface)

    refusals = []
    for key in sorted(proposed):
        surface = surfaces.BY_KEY.get(key)
        if surface is None:
            continue
        lost_records = sorted(set(surface.reaches) - reachable)
        if lost_records:
            refusals.append({
                "surface": key, "rule": "reaches",
                "message": (f"{surface.label} is the only offered route to "
                            f"{', '.join(r.replace('_', ' ') for r in lost_records)}. Retiring it "
                            f"would make {'those' if len(lost_records) > 1 else 'that'} "
                            f"unreachable. Collapse instead."),
                "unreachable": lost_records,
            })
        lost_commands = sorted(set(surface.provides) - provided)
        if lost_commands:
            refusals.append({
                "surface": key, "rule": "provides",
                "message": (f"{surface.label} is the only place "
                            f"{', '.join(c.replace('_', ' ') for c in lost_commands)} can be run "
                            f"from. Collapse instead."),
                "unreachable": lost_commands,
            })
        if surface.explains_refusal:
            peer = next((p for p in refusal_peers if set(p.reaches) & set(surface.reaches)), None)
            if peer is None:
                refusals.append({
                    "surface": key, "rule": "explains_refusal",
                    "message": (f"{surface.label} is where a withheld or refused reason is read, "
                                f"and no other offered surface carries the same refusal. Retiring "
                                f"it would leave a refusal nobody can read."),
                    "unreachable": [],
                })
    return refusals


# --- writing a note (§7.1, §7.2, §7.8) -----------------------------------------------------------

def _emit(conn: sqlite3.Connection, surface: surfaces.Surface, action: str, cause_code: str) -> None:
    """Record the §17 event for one applied action. Called outside the write transaction.

    `record()` never raises, but a sink write must not be able to hold a canonical write open, and a
    measurement failure must never roll back an operator's command.

    `none` is deliberately absent from the event's `action` enum: nothing moved, so there is no
    action to count, and counting one would put a row in the funnel that changed nothing. And a
    command is named by `command` while a surface is named by `surface` — §5's two vocabularies are
    not interchangeable, and the sink rejects a command slug offered as a surface.
    """
    if action == "none":
        return
    vocabulary = "command" if surface.kind == "command" else "surface"
    telemetry.record(conn, "retirement_action_applied",
                     properties={vocabulary: surface.key, "action": action,
                                 "cause_code": cause_code})


def _validate(surface_key: str, cause_code: str, action: str) -> surfaces.Surface:
    surface = surfaces.BY_KEY.get(surface_key)
    if surface is None:
        raise RetirementRefused(f"'{surface_key}' is not a registered surface.")
    if cause_code not in CAUSE_CODES:
        raise RetirementRefused(
            f"'{cause_code}' is not one of the seven recorded causes. The list is closed and has "
            f"no 'other': {', '.join(CAUSE_CODES)}.")
    if action not in ACTIONS:
        raise RetirementRefused(f"'{action}' is not an action. {', '.join(ACTIONS)}.")
    if action in HIDING_ACTIONS and action not in AVAILABLE_ACTIONS.get(surface.kind, ()):
        raise RetirementRefused(
            f"{action.title()} is not available for a {surface.kind}. "
            f"{surface.label} offers: {', '.join(AVAILABLE_ACTIONS.get(surface.kind, ())) or 'none'}.")
    return surface


def preview(conn: sqlite3.Connection, staged: list[dict], *, today: str | None = None) -> dict:
    """§7.8's whole-batch preview. Runs the same checks and the same projection Apply runs.

    A preview built by a different path is a preview that can disagree with the thing it previews —
    the reason the shared-plan promotion preview runs the same projection as the export
    (D-151…D-155). `apply_batch` calls this and refuses if it returns any refusal.
    """
    from . import surface_usage

    items, refusals = [], []
    retiring: set[str] = set()

    for entry in staged:
        key = (entry or {}).get("surface")
        cause = (entry or {}).get("cause_code")
        action = (entry or {}).get("action") or "none"
        try:
            surface = _validate(key, cause, action)
        except RetirementRefused as exc:
            refusals.append({"surface": key, "rule": "vocabulary", "message": str(exc),
                             "unreachable": []})
            continue
        if action == "retire":
            group_refusal = field_group_refusal(conn, surface)
            if group_refusal:
                refusals.append({"surface": key, "rule": "field_group_holds_data",
                                 "message": group_refusal, "unreachable": []})
                continue
            retiring.add(key)
        items.append({"surface": key, "label": surface.label, "route": surface.route,
                      "kind": surface.kind, "cause_code": cause, "action": action,
                      "action_meaning": ACTION_MEANINGS[action],
                      "cause_meaning": CAUSE_MEANINGS[cause]})

    refusals.extend(safety_refusals(conn, retiring))
    blocked = {refusal["surface"] for refusal in refusals}

    report = surface_usage.report(conn, today=today)
    counts = {row["surface"]: row for row in report["surfaces"]}
    for item in items:
        row = counts.get(item["surface"], {})
        # The counts as they stand, carried into the preview so the operator sees the basis of the
        # judgement they are about to freeze into the note.
        item["rendered"] = row.get("rendered", 0)
        item["engaged"] = row.get("engaged", 0)
        item["observation"] = row.get("observation")
        item["blocked"] = item["surface"] in blocked

    # §7.4's per-route preview: what each affected screen offers afterwards.
    routes: dict[str, dict] = {}
    still = offered_keys(conn) - {i["surface"] for i in items
                                  if i["action"] == "retire" and not i["blocked"]}
    for item in items:
        route = routes.setdefault(item["route"], {"route": item["route"], "changed": [],
                                                  "still_offered": []})
        route["changed"].append({"surface": item["surface"], "label": item["label"],
                                 "action": item["action"], "blocked": item["blocked"]})
    for route in routes.values():
        route["still_offered"] = sorted(
            surfaces.BY_KEY[key].label for key in still
            if surfaces.BY_KEY[key].route == route["route"])

    return {
        "window": report["window"],
        "items": items,
        "refusals": refusals,
        "applicable": [item for item in items if not item["blocked"]],
        "routes": sorted(routes.values(), key=lambda r: r["route"]),
        "caveat": surface_usage.CAVEAT,
        # §7.9, stated in the payload so a client cannot present retirement as deletion.
        "code_deletion": ("Nothing here deletes code. A retired surface stops being offered, its "
                          "route keeps resolving, and Restore puts it back."),
    }


def apply_batch(conn: sqlite3.Connection, staged: list[dict], *, actor: str | None = None,
                today: str | None = None, batch_id: str | None = None) -> dict:
    """Apply a reviewed set. All-or-nothing: any refusal and nothing is written.

    Partial application is the failure mode worth designing against here — half a simplification
    pass leaves the app in a state nobody chose, and the undo has to guess what was meant.
    """
    planned = preview(conn, staged, today=today)
    if planned["refusals"]:
        raise RetirementRefused(planned["refusals"][0]["message"])
    if not planned["items"]:
        raise RetirementRefused("Nothing was staged.")

    batch = batch_id or f"batch-{new_id()}"
    stamp = now_utc()
    window = planned["window"]
    with conn:
        for item in planned["items"]:
            note_id = new_id()
            conn.execute(
                "INSERT INTO surface_retirement_notes "
                "(id,surface_key,cause_code,observed_from,observed_to,rendered,engaged,action,"
                " batch_id,note,recorded_on,recorded_by) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                (note_id, item["surface"], item["cause_code"], window["from"], window["to"],
                 item["rendered"], item["engaged"], item["action"], batch,
                 (next((s.get("note") for s in staged
                        if s.get("surface") == item["surface"]), None) or None),
                 stamp, actor or audit.DEFAULT_ACTOR))
            # `update` rather than a sixth verb. The audit vocabulary is a closed five and adding to
            # it would be a migration that rebuilt the table for a nuance the `after` payload
            # already carries — and `archive` would be wrong for `collapse` and unreversible for
            # `restore`, which has no `unarchive` to pair with.
            audit.record(conn, object_type="surface", object_id=item["surface"], action="update",
                         after={"retirement_action": item["action"],
                                "cause_code": item["cause_code"], "batch_id": batch,
                                "rendered": item["rendered"], "engaged": item["engaged"]},
                         actor_id=actor)
    # Outside the transaction: `record()` never raises, but a sink write must not be able to hold a
    # canonical write open, and a measurement failure must never roll back an operator's command.
    # `none` is deliberately absent from the event's `action` enum — nothing moved, so there is no
    # action to count, and counting one would put a row in the funnel that changed nothing.
    for item in planned["items"]:
        _emit(conn, surfaces.BY_KEY[item["surface"]], item["action"], item["cause_code"])
    return {"batch_id": batch, "recorded_on": stamp, "applied": len(planned["items"]),
            "items": planned["items"]}


def undo_batch(conn: sqlite3.Connection, batch_id: str, *, actor: str | None = None,
               today: str | None = None, undo_window_days: int = 14) -> dict:
    """§7.8's 14-day batch undo. Writes reversing rows; never deletes the rows it reverses.

    The window is on the batch and not on the single-surface restore, which is permanent. Long
    enough to cover a fortnight away, short enough that "undo everything" stops being the reflex.

    The reversing rows carry no `batch_id`, exactly like §7.2's single-surface restore: they are
    restores, not a sitting anybody can undo. Stamping them with the id of the batch they reverse
    would put them inside the set this function selects, so a second undo would read its own output
    and reverse that too — two rows becoming four becoming eight, each pass duplicating the audit
    trail and the funnel events with it. What a row belongs to is the question the id answers, so an
    undo asks the state of each surface instead: one already offered has nothing left to reverse, and
    is reported rather than written. That also covers the mixed sitting, where one surface of three
    was already restored on its own.
    """
    rows = conn.execute(
        "SELECT * FROM surface_retirement_notes WHERE batch_id=? ORDER BY rowid", (batch_id,)
    ).fetchall()
    if not rows:
        raise RetirementRefused(f"No batch '{batch_id}' was recorded.")

    applied_on = rows[0]["recorded_on"][:10]
    now = (today or now_utc())[:10]
    elapsed = conn.execute("SELECT julianday(?) - julianday(?)", (now, applied_on)).fetchone()[0]
    if elapsed is not None and elapsed > undo_window_days:
        raise RetirementRefused(
            f"This batch was applied on {applied_on}, more than {undo_window_days} days ago. "
            f"Restore surfaces one at a time — single-surface restore never expires.")

    # A row is reversible only while it is still *the* current decision for its surface. Anything
    # else has been decided again since, and reversing it would silently overwrite the newer
    # decision with an older one — a batch undo is a way back from this sitting, not a way to win an
    # argument with a later one.
    current = current_actions(conn)
    pending, already_offered, superseded = [], [], []
    for row in rows:
        latest = current.get(row["surface_key"])
        if latest is not None and latest["id"] == row["id"]:
            pending.append(row)
        elif latest is None or latest.get("action") in (None, "none", "restore"):
            already_offered.append(row["surface_key"])
        else:
            superseded.append(row["surface_key"])
    if not pending:
        if not superseded:
            raise RetirementRefused(
                f"Every surface in this sitting is already offered as normal, so there is nothing "
                f"left to undo. Its {len(rows)} change{'' if len(rows) == 1 else 's'} "
                f"{'has' if len(rows) == 1 else 'have'} been reversed already.")
        if not already_offered:
            raise RetirementRefused(
                f"Every surface in this sitting has been decided again since, so undoing it would "
                f"replace {'that newer decision' if len(superseded) == 1 else 'those newer '
                          'decisions'} with an older one. Restore surfaces one at a time instead — "
                f"single-surface restore never expires.")
        raise RetirementRefused(
            f"Nothing in this sitting is still in the state it left the surfaces in: "
            f"{len(already_offered)} {'is' if len(already_offered) == 1 else 'are'} already offered "
            f"as normal and {len(superseded)} {'has' if len(superseded) == 1 else 'have'} been "
            f"decided again since. Restore surfaces one at a time instead — single-surface restore "
            f"never expires.")

    stamp = now_utc()
    restored = []
    with conn:
        for row in pending:
            conn.execute(
                "INSERT INTO surface_retirement_notes "
                "(id,surface_key,cause_code,observed_from,observed_to,rendered,engaged,action,"
                " batch_id,note,recorded_on,recorded_by) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                (new_id(), row["surface_key"], row["cause_code"], row["observed_from"],
                 row["observed_to"], row["rendered"], row["engaged"], "restore", None,
                 f"Undid batch {batch_id}.", stamp, actor or audit.DEFAULT_ACTOR))
            audit.record(conn, object_type="surface", object_id=row["surface_key"],
                         action="update",
                         after={"retirement_action": "restore", "batch_id": batch_id,
                                "undo": True},
                         actor_id=actor)
            restored.append(row["surface_key"])
    for row in pending:
        surface = surfaces.BY_KEY.get(row["surface_key"])
        if surface is not None:
            _emit(conn, surface, "restore", row["cause_code"])
    # Stated rather than dropped: an undo that reverses fewer surfaces than the sitting held is a
    # subtractive answer, and a subtractive answer nobody is told about reads as a complete one.
    # The two reasons stay separate sentences — "already put back" and "decided again since" are
    # different facts, and one of them is a conflict the operator may want to look at.
    clauses = []
    if already_offered:
        clauses.append(f"{len(already_offered)} {'was' if len(already_offered) == 1 else 'were'} "
                       f"already offered as normal")
    if superseded:
        clauses.append(f"{len(superseded)} {'has' if len(superseded) == 1 else 'have'} been "
                       f"decided again since and {'was' if len(superseded) == 1 else 'were'} left "
                       f"at that newer decision")
    return {"batch_id": batch_id, "restored": restored, "already_offered": already_offered,
            "superseded": superseded, "recorded_on": stamp,
            "note": (None if not clauses else
                     f"Of the {len(rows)} surfaces in this sitting, {' and '.join(clauses)}.")}


def restore(conn: sqlite3.Connection, surface_key: str, *, actor: str | None = None) -> dict:
    """§7.2's first-class rollback. Available forever, independent of any batch.

    Writes a `restore` row rather than deleting the note it reverses, so "I hid this in September
    and put it back in November" stays legible six months later.
    """
    surface = surfaces.BY_KEY.get(surface_key)
    if surface is None:
        raise RetirementRefused(f"'{surface_key}' is not a registered surface.")
    latest = current_actions(conn).get(surface_key)
    if latest is None or latest.get("action") in (None, "none", "restore"):
        raise RetirementRefused(f"{surface.label} is already offered as normal.")

    stamp = now_utc()
    with conn:
        conn.execute(
            "INSERT INTO surface_retirement_notes "
            "(id,surface_key,cause_code,observed_from,observed_to,rendered,engaged,action,"
            " batch_id,note,recorded_on,recorded_by) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (new_id(), surface_key, latest["cause_code"], latest["observed_from"],
             latest["observed_to"], latest["rendered"], latest["engaged"], "restore", None,
             f"Restored from {latest['action']}.", stamp, actor or audit.DEFAULT_ACTOR))
        audit.record(conn, object_type="surface", object_id=surface_key, action="update",
                     after={"retirement_action": "restore", "from_action": latest["action"]},
                     actor_id=actor)
    _emit(conn, surface, "restore", latest["cause_code"])
    return {"surface": surface_key, "action": "restore", "recorded_on": stamp,
            "reverted": latest["action"]}


def history(conn: sqlite3.Connection, surface_key: str | None = None) -> list[dict]:
    """Append-only, so the history is the table. Newest first."""
    if surface_key:
        rows = conn.execute(
            "SELECT * FROM surface_retirement_notes WHERE surface_key=? "
            "ORDER BY recorded_on DESC, rowid DESC", (surface_key,)).fetchall()
    else:
        rows = conn.execute("SELECT * FROM surface_retirement_notes "
                            "ORDER BY recorded_on DESC, rowid DESC").fetchall()
    return [dict(row) for row in rows]


def vocabulary() -> dict:
    """The two closed lists and the per-kind matrix, for a client that must not hard-code them."""
    return {
        "cause_codes": [{"code": code, "meaning": CAUSE_MEANINGS[code]} for code in CAUSE_CODES],
        "actions": [{"action": action, "meaning": ACTION_MEANINGS[action]} for action in ACTIONS],
        "available_actions_by_kind": {kind: list(actions)
                                      for kind, actions in AVAILABLE_ACTIONS.items()},
        "undo_window_days": 14,
        "restore_expires": False,
    }
