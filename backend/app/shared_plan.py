"""Account Path Slice 6 — the client-safe projection behind the shared plan.

`ACCOUNT-PATH-SPEC.md` §16. This module is the *only* place a customer-facing joint plan is built.
Preview, the API response, the markdown body, and every export read the same object, because §16.7
asks for a preview that cannot differ from the artifact and the cheapest way to guarantee that is
to have one projection rather than two that agree by inspection.

Four rules shape the code, and each is why a more obvious version was rejected:

- **Safety is a property of the query, not of a filter.** Every SELECT here names its columns.
  There is no `SELECT *` in this file and a test asserts its absence, because §16.5's rule — do not
  serialize full rows and filter them downstream — is only enforceable if the internal column never
  enters the process in the first place. A stance, a rationale, a probability, and a ranking reason
  cannot leak from a renderer that was never handed them.

- **Withhold rather than guess.** A promoted requirement whose live readiness is `conflicted`,
  `unknown`, stale-but-met, waived, or suppressed does not appear in the artifact. The operator
  promoted it in good faith; the state simply is not sayable to a customer today. Rendering a
  stale `met` as "complete" is exactly the carried-forward-good-state failure the freshness
  language exists to prevent, and a client plan is the worst possible place to commit it. Every
  withheld row is named in `diagnostics`, so this is silence in the artifact and never silence to
  the operator.

- **The client-facing status is derived on every read.** Nothing here is stored. Migration 0047
  added visibility, a label, an owner and a promotion stamp — no state, no freshness, no coverage.
  The five words a customer sees (§16.3) are computed from the live records each time, which is the
  only reason demotion, closure, retraction and staleness take effect without a rebuild.

- **A blocker must itself be shared before it can be named.** `blocked` is claimed only from a
  promoted blocking record. Otherwise the existence of internal work would leak through a status
  word, which is the same leak by a quieter route.

Internal phase vocabulary (`foundation`, `expansion`, `renewal`, …) never crosses this boundary.
§16.5 asks for a "current shared phase/milestone summary" and the milestone half of that answers it
without telling a customer which commercial motion they are an instance of.
"""
from __future__ import annotations

import sqlite3

from . import playbooks, repo
from .db import new_id, now_utc

TEMPLATE_KEY = "mutual_action_plan"
# v1 is `output_gen.mutual_action_plan` — one flat mixed table. §16.5 replaces it with a grouped
# plan, which changes what a reader sees, so it is a new template version rather than an edit.
TEMPLATE_VERSION = 2
AUDIENCE = "client_facing"
DOCUMENT_KIND = "mutual_action_plan"

# §16.3. The whole external status vocabulary. Anything an evaluator says that does not map cleanly
# onto one of these is withheld rather than approximated.
CLIENT_STATUSES = ("not_started", "in_progress", "complete", "blocked", "not_applicable")

PURPOSE = ("The joint plan for this engagement. It lists only what both sides have agreed to share "
           "and shows each item's owner, date, and current status.")

# --- column allowlists (§16.5) --------------------------------------------------------------------
# Every one of these is the complete set of fields this module is allowed to know about for that
# record type. Widening one is a deliberate act with a diff, which is the point.
# A milestone has no `source_reference_id` — its only provenance column is the interaction.
_MILESTONE_COLS = "id, program_id, name, target_date, status, source_interaction_id"
_COMMITMENT_COLS = ("id, program_id, description, responsible_party_id, internal_owner_id, due_date, "
                    "status, source_reference_id, source_interaction_id")
_TASK_COLS = ("id, program_id, description, internal_owner_id, due_date, status, "
              "source_reference_id, source_interaction_id")
_LINK_COLS = "milestone_id, program_id, task_id, commitment_id, relation"
_PLAN_CLIENT_COLS = ("id, program_id, requirement_key, client_label, client_owner_person_id, "
                     "client_promoted_on, due_date")


def _rows(conn, sql, params=()):
    return [dict(r) for r in conn.execute(sql, tuple(params)).fetchall()]


def _qmarks(values) -> str:
    return ",".join("?" * len(values))


def _safe(value) -> str:
    return str(value if value not in (None, "") else "—").replace("|", "\\|").replace("\n", " ")


def _count(n: int, noun: str) -> str:
    """A customer reads this export, so a count reads as a sentence rather than as `item(s)`."""
    return f"{n} {noun}" if n == 1 else f"{n} {noun}s"


# --- people ---------------------------------------------------------------------------------------

def _people(conn, account_id: str) -> dict[str, dict]:
    """Name and side only.

    A person row carries stance, influence, relationship strength and free-text observations. None
    of that is selected here, so no amount of downstream carelessness can put it in front of a
    customer. `account_id IS NULL` is the internal side of the relationship (§16.5's "Valence
    owner"); a person belonging to a *different* account is not loaded at all.
    """
    rows = _rows(conn, "SELECT id, name, account_id FROM persons "
                       "WHERE archived = 0 AND (account_id = ? OR account_id IS NULL)", (account_id,))
    return {r["id"]: {"name": r["name"], "side": "customer" if r["account_id"] else "valence"}
            for r in rows}


def _owner_pair(people: dict, *person_ids) -> dict:
    """Sort the named owners onto the two sides of the plan. Unknown ids simply produce no owner."""
    pair = {"customer_owner": None, "valence_owner": None}
    for pid in person_ids:
        person = people.get(pid) if pid else None
        if not person:
            continue
        slot = "customer_owner" if person["side"] == "customer" else "valence_owner"
        if pair[slot] is None:
            pair[slot] = person["name"]
    return pair


# --- source labels --------------------------------------------------------------------------------

def _source_label(conn, row: dict, manifest: list, dates: list) -> str | None:
    """An externally-safe label for where an item came from (§16.5, last bullet).

    A `source_references` label is a document title an operator already wrote for citation. An
    interaction contributes its *date only* — its subject line, participants and body are internal,
    and §16.2 forbids raw transcripts, emails and spans outright.
    """
    ref_id = row.get("source_reference_id")
    if ref_id:
        found = conn.execute("SELECT id, label, created_at FROM source_references "
                             "WHERE id = ? AND archived = 0", (ref_id,)).fetchone()
        if found:
            manifest.append({"type": "source_reference", "id": found["id"]})
            dates.append(found["created_at"][:10])
            return found["label"]
    interaction_id = row.get("source_interaction_id")
    if interaction_id:
        found = conn.execute("SELECT id, occurred_on FROM interactions WHERE id = ? AND archived = 0",
                             (interaction_id,)).fetchone()
        if found:
            manifest.append({"type": "interaction", "id": found["id"]})
            dates.append(found["occurred_on"][:10])
            return f"Agreed in a meeting on {found['occurred_on'][:10]}"
    return None


# --- status derivation ----------------------------------------------------------------------------

def _action_status(kind: str, status: str) -> str:
    """The five-word vocabulary, derived and never stored.

    `not_started` is deliberately unreachable for an action: `open` does not distinguish untouched
    from underway, and inventing that distinction for a customer-facing plan would be a guess with
    a schedule attached to it.
    """
    if kind == "task":
        return {"done": "complete", "cancelled": "not_applicable"}.get(status, "in_progress")
    return "complete" if status == "closed" else "in_progress"


def _milestone_status(milestone: dict, advancing: list, blocking: list) -> str:
    if milestone["raw_status"] == "complete":
        return "complete"
    # Only a *promoted* blocker can be named. An open internal task blocking a shared milestone
    # stays invisible, because "blocked" would otherwise announce the existence of work the
    # customer was never shown.
    if any(a["client_status"] not in ("complete", "not_applicable") for a in blocking):
        return "blocked"
    # Any advancing action the customer can already see as underway or finished makes the
    # milestone underway. Requiring a *completed* one read `not_started` on a milestone whose own
    # shared actions render `In progress` directly beneath it — a document disagreeing with itself
    # — and `_action_status` above has already settled the question the other way: `open` is
    # reported as `in_progress` because inventing the untouched/underway distinction would be a
    # guess. `not_applicable` is excluded, so a milestone whose only advancing actions were
    # cancelled still reads `not_started` rather than being talked into progress by them.
    if any(a["client_status"] in ("complete", "in_progress") for a in advancing):
        return "in_progress"
    return "not_started"


def _requirement_status(reading: dict) -> tuple[str | None, str | None]:
    """Map a live readiness reading onto the external vocabulary, or refuse to.

    Returns `(status, withheld_reason)`. Exactly one of the two is set. The refusals are the
    interesting half: they are the cases where an honest external word does not exist. Each
    reason is written to complete the sentence "held back because ...", so the operator surface
    can state it without reformatting a clause it did not author.
    """
    if reading.get("legacy"):
        return None, "it is pinned to a retired requirement definition, so no state is claimed"
    if reading.get("applicability_override"):
        return None, "it is suppressed by an internal exception, whose rationale is internal (§16.2)"
    if reading.get("waiver"):
        return None, "it carries a waiver, and waiver rationale is internal unless authored for sharing"
    if reading.get("applicability") == "not_applicable":
        return "not_applicable", None
    state = reading.get("state")
    if state == "conflicted":
        return None, "readiness is conflicted, and a customer plan is no place to guess between sources"
    if state in (None, "unknown"):
        return None, "no readiness reading is available in this scope"
    if state == "not_applicable":
        return "not_applicable", None
    if state == "met":
        # A stale `met` is the carried-forward good state the freshness language exists to prevent.
        if reading.get("freshness") == "stale":
            return None, "the evidence behind it is past its freshness window"
        return "complete", None
    if state == "thin":
        return "in_progress", None
    return None, f"this build does not map the readiness state {state!r}"


# --- promoted records -----------------------------------------------------------------------------

def _promoted_actions(conn, program_ids: list[str], people: dict,
                      manifest: list, dates: list) -> list[dict]:
    if not program_ids:
        return []
    marks = _qmarks(program_ids)
    actions: list[dict] = []
    for row in _rows(conn, f"SELECT {_COMMITMENT_COLS} FROM commitments "
                           f"WHERE archived = 0 AND client_visible = 1 AND program_id IN ({marks}) ",
                     program_ids):
        actions.append({
            "kind": "commitment", "id": row["id"], "program_id": row["program_id"],
            "what": row["description"], "due": row["due_date"],
            "client_status": _action_status("commitment", row["status"]),
            **_owner_pair(people, row["responsible_party_id"], row["internal_owner_id"]),
            "source": _source_label(conn, row, manifest, dates),
        })
        manifest.append({"type": "commitment", "id": row["id"]})
    for row in _rows(conn, f"SELECT {_TASK_COLS} FROM tasks "
                           f"WHERE archived = 0 AND client_visible = 1 AND program_id IN ({marks}) ",
                     program_ids):
        actions.append({
            "kind": "task", "id": row["id"], "program_id": row["program_id"],
            "what": row["description"], "due": row["due_date"],
            "client_status": _action_status("task", row["status"]),
            **_owner_pair(people, row["internal_owner_id"]),
            "source": _source_label(conn, row, manifest, dates),
        })
        manifest.append({"type": "task", "id": row["id"]})
    return actions


def _promoted_milestones(conn, program_ids: list[str], manifest: list, dates: list) -> list[dict]:
    if not program_ids:
        return []
    out = []
    for row in _rows(conn, f"SELECT {_MILESTONE_COLS} FROM milestones "
                           f"WHERE archived = 0 AND client_visible = 1 "
                           f"AND program_id IN ({_qmarks(program_ids)})", program_ids):
        # `at_risk` and `completion_note` are not selected: the first is an internal judgment and
        # the second routinely explains an internal reason for a slip.
        out.append({"id": row["id"], "program_id": row["program_id"], "name": row["name"],
                    "target_date": row["target_date"], "raw_status": row["status"],
                    "source": _source_label(conn, row, manifest, dates)})
        manifest.append({"type": "milestone", "id": row["id"]})
    return out


def _links(conn, program_ids: list[str]) -> list[dict]:
    if not program_ids:
        return []
    return _rows(conn, f"SELECT {_LINK_COLS} FROM milestone_action_links "
                       f"WHERE archived = 0 AND program_id IN ({_qmarks(program_ids)})", program_ids)


def _growth_lines(conn, account_id: str, people: dict, manifest: list, dates: list) -> list[dict]:
    """§16.2 allows promoted growth-plan lines "already supported by their native contracts".

    Probability, funding tactics, competitive notes and pricing assumptions are not selected, so
    the commercial half of a growth line cannot reach an external reader.
    """
    out = []
    for row in _rows(conn,
                     "SELECT gl.id, gl.name, gl.seat_count, gl.ask_date, gl.status, "
                     "gl.budget_owner_person_id, gl.source_reference_id, "
                     "COALESCE(ps.name, pv.name) AS population "
                     "FROM growth_plan_lines gl "
                     "JOIN account_growth_plans gp ON gp.id = gl.plan_id "
                     "LEFT JOIN population_segments ps ON ps.id = gl.segment_id "
                     "LEFT JOIN population_views pv ON pv.id = gl.view_id "
                     "WHERE gl.account_id = ? AND gp.status = 'active' AND gl.archived = 0 "
                     "AND gl.client_visible = 1 AND gl.source_reference_id IS NOT NULL",
                     (account_id,)):
        out.append({"id": row["id"], "name": row["name"], "seats": row["seat_count"],
                    "population": row["population"], "ask_date": row["ask_date"],
                    **_owner_pair(people, row["budget_owner_person_id"]),
                    "source": _source_label(conn, row, manifest, dates)})
        manifest.append({"type": "growth_plan_line", "id": row["id"]})
    return out


def _triggers(conn, account_id: str, manifest: list, dates: list) -> list[dict]:
    out = []
    for row in _rows(conn,
                     "SELECT id, name, source_kind, seat_band_min, seat_band_max, effective_on, "
                     "expires_on, agreed_process, source_reference_id, source_interaction_id "
                     "FROM operational_agreements "
                     "WHERE account_id = ? AND archived = 0 AND status = 'active' "
                     "AND client_visible = 1 "
                     "AND (source_reference_id IS NOT NULL OR source_interaction_id IS NOT NULL) "
                     "ORDER BY effective_on", (account_id,)):
        label = _source_label(conn, row, manifest, dates)
        if not label:
            continue
        out.append({"id": row["id"], "name": row["name"],
                    "authority": "contractual" if row["source_kind"] == "signed_paper" else "operational",
                    "seat_band_min": row["seat_band_min"], "seat_band_max": row["seat_band_max"],
                    "effective_on": row["effective_on"], "expires_on": row["expires_on"],
                    "agreed_process": row["agreed_process"], "source": label})
        manifest.append({"type": "operational_agreement", "id": row["id"]})
    return out


# --- promoted requirements ------------------------------------------------------------------------

def _client_source_for_requirement(conn, instance_id: str, promoted_action_ids: set[str],
                                   reading: dict) -> tuple[str | None, list]:
    """§16.3's "at least one accepted source or jointly acknowledged record", externally sayable.

    A requirement's own evidence is internal by default — §16.2 forbids evidence that is not
    independently client-visible — so it can *qualify* a requirement without ever being quoted. Two
    things qualify: a linked action the customer can already see, or a `met` state resting on a
    confirmed source. Everything else has no external source and is withheld.
    """
    linked = _rows(conn, "SELECT task_id, commitment_id FROM readiness_requirement_action_links "
                         "WHERE plan_instance_id = ? AND archived = 0 AND relation = 'advances'",
                   (instance_id,))
    used = []
    for row in linked:
        action_id = row["task_id"] or row["commitment_id"]
        if action_id in promoted_action_ids:
            used.append({"type": "task" if row["task_id"] else "commitment", "id": action_id})
    if used:
        return "Tracked by shared plan items", used
    if reading.get("state") == "met" and reading.get("provenance") == "confirmed_source":
        # The label says a confirmed source exists without naming it. Naming it would be the span
        # leak §16.2 closes.
        return "Confirmed source on file", []
    return None, []


def _promoted_requirements(conn, account_id: str, promoted_action_ids: set[str],
                           people: dict, manifest: list,
                           withheld: list) -> list[dict]:
    """The client-safe requirement projection (§16.3).

    `playbooks.merged_plan` supplies the live reading. Its rows carry the operator's world —
    definition-of-done text, evidence diagnostics, missing-item lists, suggested actions — and this
    function copies *seven named keys* out of it rather than the row, so none of that can travel.
    """
    client_rows = {
        r["id"]: r for r in _rows(
            conn, f"SELECT {_PLAN_CLIENT_COLS} FROM readiness_plan_instances "
                  f"WHERE account_id = ? AND archived = 0 AND client_visible = 1", (account_id,))
    }
    if not client_rows:
        return []
    merged = playbooks.merged_plan(conn, account_id)
    out = []
    for row in merged["requirements"]:
        promoted = client_rows.get(row["instance_id"])
        if not promoted:
            continue
        label = (promoted["client_label"] or "").strip()
        status, refusal = _requirement_status(row)
        source, used_actions = _client_source_for_requirement(
            conn, row["instance_id"], promoted_action_ids, row)
        if refusal is None and source is None:
            refusal = "no client-visible source or shared action supports it yet"
        if refusal:
            withheld.append({"kind": "requirement", "id": row["instance_id"],
                             "label": label or row["requirement_key"], "reason": refusal})
            continue
        out.append({
            "kind": "requirement", "id": row["instance_id"],
            "program_id": promoted["program_id"],
            "what": label,
            "due": promoted["due_date"],
            "client_status": status,
            **_owner_pair(people, promoted["client_owner_person_id"]),
            "source": source,
        })
        manifest.append({"type": "readiness_plan_instance", "id": row["instance_id"]})
        manifest.extend(used_actions)
    return out


# --- the projection -------------------------------------------------------------------------------

def _project(conn: sqlite3.Connection, account_id: str) -> tuple[dict, dict, list]:
    """Build the artifact, the operator diagnostics, and the source manifest in one pass."""
    account = repo.get_row(conn, "accounts", account_id)
    today = now_utc()[:10]
    manifest: list[dict] = []
    dates: list[str] = []
    withheld: list[dict] = []

    # `phase` is deliberately not selected. §16.5 wants a shared summary, not a disclosure of which
    # commercial motion the customer is an instance of.
    programs = _rows(conn, "SELECT id, name FROM programs WHERE account_id = ? AND archived = 0 "
                           "ORDER BY name", (account_id,))
    program_ids = [p["id"] for p in programs]
    people = _people(conn, account_id)

    actions = _promoted_actions(conn, program_ids, people, manifest, dates)
    milestones = _promoted_milestones(conn, program_ids, manifest, dates)
    action_index = {a["id"]: a for a in actions}
    promoted_action_ids = set(action_index)
    milestone_index = {m["id"]: m for m in milestones}

    advancing: dict[str, list] = {m["id"]: [] for m in milestones}
    blocking: dict[str, list] = {m["id"]: [] for m in milestones}
    claimed: set[str] = set()
    for link in _links(conn, program_ids):
        milestone = milestone_index.get(link["milestone_id"])
        action = action_index.get(link["task_id"] or link["commitment_id"])
        if not milestone or not action:
            # Either half unpromoted means the relationship is internal. It is not mentioned, not
            # counted, and not hinted at by a status word.
            continue
        (advancing if link["relation"] == "advances" else blocking)[milestone["id"]].append(action)
        if link["relation"] == "advances":
            claimed.add(action["id"])

    requirements = _promoted_requirements(conn, account_id, promoted_action_ids, people,
                                          manifest, withheld)

    by_program = []
    for program in programs:
        groups = []
        for milestone in sorted((m for m in milestones if m["program_id"] == program["id"]),
                                key=lambda m: (m["target_date"] or "9999-12-31", m["name"])):
            group_actions = sorted(advancing[milestone["id"]],
                                   key=lambda a: (a["due"] or "9999-12-31", a["what"]))
            groups.append({
                "milestone_id": milestone["id"], "milestone": milestone["name"],
                "target_date": milestone["target_date"],
                "client_status": _milestone_status(milestone, advancing[milestone["id"]],
                                                   blocking[milestone["id"]]),
                "source": milestone["source"],
                "actions": [{k: a[k] for k in ("kind", "id", "what", "due", "client_status",
                                               "customer_owner", "valence_owner", "source")}
                            for a in group_actions],
            })
        loose = sorted((a for a in actions
                        if a["program_id"] == program["id"] and a["id"] not in claimed),
                       key=lambda a: (a["due"] or "9999-12-31", a["what"]))
        if loose:
            groups.append({
                "milestone_id": None, "milestone": "Other agreed work", "target_date": None,
                "client_status": None, "source": None,
                "actions": [{k: a[k] for k in ("kind", "id", "what", "due", "client_status",
                                               "customer_owner", "valence_owner", "source")}
                            for a in loose],
            })
        program_requirements = sorted(
            (r for r in requirements if r["program_id"] == program["id"]),
            key=lambda r: (r["due"] or "9999-12-31", r["what"]))
        if groups or program_requirements:
            by_program.append({"program_id": program["id"], "name": program["name"],
                               "groups": groups, "requirements": program_requirements})

    account_requirements = sorted((r for r in requirements if r["program_id"] is None),
                                  key=lambda r: (r["due"] or "9999-12-31", r["what"]))

    upcoming = sorted(
        ({"name": m["name"], "target_date": m["target_date"],
          "program": next((p["name"] for p in programs if p["id"] == m["program_id"]), None),
          "source": m["source"]}
         for m in milestones
         if m["raw_status"] == "upcoming" and (m["target_date"] or "") >= today),
        key=lambda m: (m["target_date"] or "9999-12-31", m["name"]))

    complete = sum(1 for m in milestones if m["raw_status"] == "complete")
    shared_items = (sum(len(g["actions"]) for p in by_program for g in p["groups"])
                    + len(requirements))
    growth_lines = _growth_lines(conn, account_id, people, manifest, dates)
    triggers = _triggers(conn, account_id, manifest, dates)
    current_through = min(dates) if dates else None

    # The two halves of this field are answered separately, because only one of them can be
    # answered honestly from here.
    #
    # **Missing** is a fact the projection already holds. `_source_label` returns None when an
    # item has no external record behind it, and that item still ships — with an empty Source
    # cell. Naming the count is the difference between a column that is empty and a document that
    # says nothing is missing. Synthetic group rows ("Other agreed work") are excluded: their
    # `source: None` is a heading with no record, not a record with no source.
    #
    # **Stale** is not answerable here, and is not faked. These sources are meetings, decisions and
    # operator-written references; none carries a freshness threshold the way a metric does through
    # `metric_definitions.stale_after_days`, and inventing one would be the hard-coded benchmark
    # the data rules forbid. The freshness discipline is enforced upstream instead —
    # `_requirement_status` withholds a stale `met` rather than showing `Complete` — so what
    # reaches this artifact has already been filtered, and the stamp does not claim a second check
    # that never ran. Before this the field was `[]` whenever any source date existed at all,
    # which read as "we checked and nothing is missing" on a document going to a customer.
    sourced_items = ([a for p in by_program for g in p["groups"] for a in g["actions"]]
                     + [r for p in by_program for r in p["requirements"]]
                     + account_requirements)
    unsourced = sum(1 for item in sourced_items if not item.get("source"))
    source_gaps: list[str] = []
    if not current_through:
        source_gaps.append("no sourced items have been shared to this plan")
    if unsourced:
        source_gaps.append(f"{_count(unsourced, 'shared item')} "
                           f"{'carries' if unsourced == 1 else 'carry'} no source on record")

    artifact = {
        "template": {"key": TEMPLATE_KEY, "version": TEMPLATE_VERSION},
        "audience": AUDIENCE,
        "account_id": account_id,
        "account_name": account["name"],
        "purpose": PURPOSE,
        "stamp": {
            "generated_at": now_utc(),
            "data_current_through": current_through,
            "missing_or_stale_sources": source_gaps,
        },
        "summary": {
            "programs": len(by_program),
            "shared_items": shared_items,
            "milestones_complete": complete,
            "milestones_shared": len(milestones),
            "next_milestone": (upcoming[0] if upcoming else None),
        },
        "programs": by_program,
        "account_requirements": account_requirements,
        "upcoming_milestones": upcoming,
        "growth_lines": growth_lines,
        "pre_agreed_triggers": triggers,
        "note": ("Only items both sides have agreed to share appear here. They are selected by the "
                 "query that builds this plan, not filtered out of a longer list."),
    }
    artifact["markdown"] = render_markdown(artifact)

    diagnostics = {
        "withheld": withheld,
        "unshared_counts": _unshared_counts(conn, account_id, program_ids),
        "source_manifest": manifest,
        "notes": [
            "Decisions are not in the §16.2 shareable set, so a confirmed decision cannot be "
            "promoted onto this plan. Milestones carry the upcoming block on their own.",
            "A withheld requirement was promoted by an operator but has no state that can be "
            "stated honestly to a customer today. Nothing about it reaches the artifact.",
        ],
    }
    return artifact, diagnostics, manifest


def _unshared_counts(conn, account_id: str, program_ids: list[str]) -> dict:
    """How much of the native plan is *not* shared — counts only, no descriptions.

    This exists so an operator previewing the plan can tell an empty plan apart from a plan they
    forgot to promote into. It is diagnostics, never artifact.
    """
    if not program_ids:
        return {"milestones": 0, "commitments": 0, "tasks": 0, "requirements": 0}
    marks = _qmarks(program_ids)
    def count(sql, params):
        return conn.execute(sql, tuple(params)).fetchone()[0]
    return {
        "milestones": count(f"SELECT COUNT(*) FROM milestones WHERE archived = 0 "
                            f"AND client_visible = 0 AND program_id IN ({marks})", program_ids),
        "commitments": count(f"SELECT COUNT(*) FROM commitments WHERE archived = 0 "
                             f"AND client_visible = 0 AND program_id IN ({marks})", program_ids),
        "tasks": count(f"SELECT COUNT(*) FROM tasks WHERE archived = 0 "
                       f"AND client_visible = 0 AND program_id IN ({marks})", program_ids),
        "requirements": count("SELECT COUNT(*) FROM readiness_plan_instances WHERE archived = 0 "
                              "AND client_visible = 0 AND account_id = ?", (account_id,)),
    }


# --- rendering ------------------------------------------------------------------------------------

_STATUS_WORDS = {"not_started": "Not started", "in_progress": "In progress", "complete": "Complete",
                 "blocked": "Blocked", "not_applicable": "Not applicable"}


def _action_table(lines: list[str], actions: list[dict]) -> None:
    lines += ["| Item | Your owner | Valence owner | Due | Status | Source |",
              "|---|---|---|---|---|---|"]
    for a in actions:
        lines.append("| " + " | ".join((
            _safe(a["what"]), _safe(a["customer_owner"]), _safe(a["valence_owner"]),
            _safe(a["due"]), _safe(_STATUS_WORDS.get(a["client_status"])), _safe(a["source"]))) + " |")


def render_markdown(artifact: dict) -> str:
    """The exported body. It reads the artifact and never the database, so an export cannot
    contain a field the API response did not (§16.7)."""
    stamp = artifact["stamp"]
    summary = artifact["summary"]
    L = [f"# Mutual action plan — {artifact['account_name']}", "",
         artifact["purpose"], "",
         f"_Generated {stamp['generated_at']} · data current through "
         f"{stamp['data_current_through'] or 'no sourced items yet'}_", ""]
    if stamp["missing_or_stale_sources"]:
        L += ["> " + "; ".join(stamp["missing_or_stale_sources"]), ""]
    L += ["## Where the plan stands", "",
          f"- {_count(summary['shared_items'], 'shared item')} across "
          f"{_count(summary['programs'], 'programme')}",
          f"- {summary['milestones_complete']} of "
          f"{_count(summary['milestones_shared'], 'shared milestone')} complete"]
    if summary["next_milestone"]:
        nxt = summary["next_milestone"]
        L.append(f"- Next milestone: **{nxt['name']}** — {nxt['target_date'] or 'no date agreed'}")
    L.append("")

    if not artifact["programs"] and not artifact["account_requirements"]:
        L += ["_No items have been shared to this plan yet._", ""]
    for program in artifact["programs"]:
        L += [f"## {program['name']}", ""]
        for group in program["groups"]:
            heading = group["milestone"]
            if group["client_status"]:
                heading += f" — {_STATUS_WORDS.get(group['client_status'], group['client_status'])}"
            if group["target_date"]:
                heading += f" (target {group['target_date']})"
            L += [f"### {heading}", ""]
            if group["actions"]:
                _action_table(L, group["actions"])
            else:
                L.append("_No shared actions under this milestone yet._")
            L.append("")
        if program["requirements"]:
            L += ["### Agreed readiness items", ""]
            _action_table(L, program["requirements"])
            L.append("")

    if artifact["account_requirements"]:
        L += ["## Across the account", ""]
        _action_table(L, artifact["account_requirements"])
        L.append("")

    if artifact["upcoming_milestones"]:
        L += ["## Confirmed upcoming milestones", "", "| Milestone | Programme | Target | Source |",
              "|---|---|---|---|"]
        for m in artifact["upcoming_milestones"]:
            L.append("| " + " | ".join((_safe(m["name"]), _safe(m["program"]),
                                        _safe(m["target_date"]), _safe(m["source"]))) + " |")
        L.append("")

    if artifact["growth_lines"]:
        L += ["## Agreed growth lines", "", "| Line | Population | Seats | Owner | Date | Source |",
              "|---|---|---|---|---|---|"]
        for g in artifact["growth_lines"]:
            owner = g["customer_owner"] or g["valence_owner"]
            L.append("| " + " | ".join((
                _safe(g["name"]), _safe(g["population"]), f"{g['seats']:,}" if g["seats"] else "—",
                _safe(owner), _safe(g["ask_date"]), _safe(g["source"]))) + " |")
        L.append("")

    if artifact["pre_agreed_triggers"]:
        L += ["## Pre-agreed expansion triggers", "",
              "| Agreement | Authority | Seat band | Effective | Process | Source |",
              "|---|---|---|---|---|---|"]
        for t in artifact["pre_agreed_triggers"]:
            band = (f"{t['seat_band_min']:,}–{t['seat_band_max']:,}"
                    if t["seat_band_min"] is not None and t["seat_band_max"] is not None else "—")
            L.append("| " + " | ".join((
                _safe(t["name"]), _safe(t["authority"]), band, _safe(t["effective_on"]),
                _safe(t["agreed_process"]), _safe(t["source"]))) + " |")
        L.append("")

    L += ["---", "", artifact["note"]]
    return "\n".join(L)


# --- public surface -------------------------------------------------------------------------------

def build(conn: sqlite3.Connection, account_id: str) -> dict:
    """The client-safe artifact alone. This is what an export renders."""
    artifact, _, _ = _project(conn, account_id)
    return artifact


def preview(conn: sqlite3.Connection, account_id: str) -> dict:
    """§16.7 — the operator view. `artifact` here is the same object an export receives; the
    operator-only reasoning sits beside it in `diagnostics` and never inside it."""
    artifact, diagnostics, _ = _project(conn, account_id)
    return {"artifact": artifact, "diagnostics": diagnostics}


def promotion_preview(conn: sqlite3.Connection, object_type: str, object_id: str,
                      client_label: str | None = None) -> dict:
    """§16.4 step 2 — exactly what a customer would see for one record, before promoting it.

    Built by projecting the record through the same helpers the plan uses, so the preview cannot
    promise a projection the plan would not produce.
    """
    people = _people(conn, _account_of(conn, object_type, object_id))
    manifest: list[dict] = []
    dates: list[str] = []
    if object_type == "commitment":
        row = _one(conn, f"SELECT {_COMMITMENT_COLS} FROM commitments WHERE id = ?", object_id)
        return {"kind": "commitment", "what": row["description"], "due": row["due_date"],
                "client_status": _action_status("commitment", row["status"]),
                **_owner_pair(people, row["responsible_party_id"], row["internal_owner_id"]),
                "source": _source_label(conn, row, manifest, dates)}
    if object_type == "task":
        row = _one(conn, f"SELECT {_TASK_COLS} FROM tasks WHERE id = ?", object_id)
        return {"kind": "task", "what": row["description"], "due": row["due_date"],
                "client_status": _action_status("task", row["status"]),
                **_owner_pair(people, row["internal_owner_id"]),
                "source": _source_label(conn, row, manifest, dates)}
    if object_type == "milestone":
        row = _one(conn, f"SELECT {_MILESTONE_COLS} FROM milestones WHERE id = ?", object_id)
        return {"kind": "milestone", "what": row["name"], "due": row["target_date"],
                "client_status": "complete" if row["status"] == "complete" else "not_started",
                "customer_owner": None, "valence_owner": None,
                "source": _source_label(conn, row, manifest, dates)}
    if object_type == "requirement":
        return _requirement_promotion_preview(conn, object_id, client_label, people, manifest)
    raise ValueError(f"unknown object type {object_type!r}")


def _requirement_promotion_preview(conn, instance_id: str, client_label: str | None,
                                   people: dict, manifest: list) -> dict:
    row = _one(conn, f"SELECT {_PLAN_CLIENT_COLS}, account_id FROM readiness_plan_instances "
                     "WHERE id = ?", instance_id)
    merged = playbooks.merged_plan(conn, row["account_id"])
    reading = next((r for r in merged["requirements"] if r["instance_id"] == instance_id), {})
    # Scoped exactly as `_project` scopes `_promoted_actions`, and for the reason the preview
    # exists: §16.7 makes preview-equals-export a contract rather than a convention. A portfolio-
    # wide scan is a superset — a promoted task on another account, or one in an archived program
    # on this account, would show a source here that the export will not produce, so the dry run
    # would over-promise in the one place an operator reads it to decide whether to promote.
    program_ids = [p["id"] for p in _rows(
        conn, "SELECT id FROM programs WHERE account_id = ? AND archived = 0", (row["account_id"],))]
    promoted_actions: set[str] = set()
    if program_ids:
        marks = _qmarks(program_ids)
        promoted_actions = {
            r["id"] for r in _rows(conn, f"SELECT id FROM tasks WHERE client_visible = 1 "
                                         f"AND archived = 0 AND program_id IN ({marks})", program_ids)
        } | {
            r["id"] for r in _rows(conn, f"SELECT id FROM commitments WHERE client_visible = 1 "
                                         f"AND archived = 0 AND program_id IN ({marks})", program_ids)
        }
    status, refusal = _requirement_status(reading)
    source, _ = _client_source_for_requirement(conn, instance_id, promoted_actions, reading)
    if refusal is None and source is None:
        refusal = "no client-visible source or shared action supports it yet"
    label = (client_label or row["client_label"] or "").strip()
    return {
        "kind": "requirement",
        "what": label,
        "due": row["due_date"],
        "client_status": status,
        **_owner_pair(people, row["client_owner_person_id"]),
        "source": source,
        # Present tense, and honest: promotion is still allowed, but this is what the customer
        # would see today — which is nothing.
        "withheld_reason": refusal,
        "would_appear": refusal is None and bool(label),
    }


def _one(conn, sql: str, object_id: str) -> dict:
    row = conn.execute(sql, (object_id,)).fetchone()
    if not row:
        raise KeyError(object_id)
    return dict(row)


def _account_of(conn, object_type: str, object_id: str) -> str:
    if object_type == "commitment":
        return _one(conn, "SELECT account_id FROM commitments WHERE id = ?", object_id)["account_id"]
    if object_type == "requirement":
        return _one(conn, "SELECT account_id FROM readiness_plan_instances WHERE id = ?",
                    object_id)["account_id"]
    table = {"task": "tasks", "milestone": "milestones"}[object_type]
    program_id = _one(conn, f"SELECT program_id FROM {table} WHERE id = ?", object_id)["program_id"]
    return _one(conn, "SELECT account_id FROM programs WHERE id = ?", program_id)["account_id"]


# §16.6's "included source identities". Why the record type carries the reason rather than each
# append site: the reason is a property of *how this template uses that kind of record*, and it is
# the same every time, so writing it out at nine call sites would only create nine chances to
# disagree.
_INCLUSION_REASON = {
    "source_reference": "cited source for a shared item",
    "interaction": "meeting where a shared item was agreed",
    "milestone": "shared milestone",
    "commitment": "shared commitment",
    "task": "shared task",
    "growth_plan_line": "shared growth line",
    "operational_agreement": "pre-agreed expansion trigger",
    "readiness_plan_instance": "shared readiness item",
}


def record_sources(conn: sqlite3.Connection, document_id: str, manifest: list) -> int:
    """Write the manifest into `generated_document_sources` — the registry the internal artifacts
    already use (§16.6). Identities only: the content is in the frozen body, and a second copy
    would be a second thing to disagree with.

    `visibility_class` is `client_facing` here because every row in this manifest earned its place
    by being promoted. That is a statement about the *record*, not about the manifest, which is an
    internal audit trail and is never rendered to a customer.
    """
    seen, rows = set(), []
    for entry in manifest:
        key = (entry["type"], entry["id"])
        if key in seen:
            continue
        seen.add(key)
        rows.append(key)
    rows.sort()
    stamp = now_utc()
    with conn:
        for record_type, record_id in rows:
            conn.execute(
                "INSERT OR IGNORE INTO generated_document_sources"
                "(id,document_id,record_type,record_id,record_version,inclusion_reason,"
                "visibility_class,created_at) VALUES (?,?,?,?,?,?,?,?)",
                (new_id(), document_id, record_type, record_id, None,
                 _INCLUSION_REASON.get(record_type, "included in the shared plan"),
                 "client_facing", stamp))
    return len(rows)


def project_for_document(conn: sqlite3.Connection, account_id: str) -> tuple[dict, list]:
    """The artifact plus its raw manifest, for saving a stamped `generated_documents` row."""
    artifact, _, manifest = _project(conn, account_id)
    return artifact, manifest
