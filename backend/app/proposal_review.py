"""Duplicate matching, conflict preview, and optimistic concurrency — RR §6.6 and §6.7.

Two things happen here and they are deliberately not the same thing:

  * **One check is enforcement.** §6.6 requires that repeated acceptance return the existing
    resolved target or a stable conflict, and never create a duplicate canonical record. That is
    `already_resolved()`, and the accept path must honour it.
  * **Every other check is a suggestion.** §6.7's closing line: possible matches are suggestions,
    not automatic merges. `match_candidates()` therefore returns rows for a human to read and
    never blocks, merges, or re-ranks anything. A near-match that silently swallowed a proposal
    would lose real work the operator never saw.

Scope is the third rule, and it fails closed. Matching is restricted to the same account/program
(§6.7's opening clause). Several execution tables — tasks, risks, issues, deployment moments — carry
only `program_id`, so when a run has no program there is no way to bound the query to one account.
This module returns no candidates in that case rather than widening the search: a cross-account
match is a trust-boundary breach, and no amount of usefulness offsets it.
"""
from __future__ import annotations

import json

from . import proposals

# Where each allowlisted target lives, what its human-readable line is, and how it is scoped.
# A target absent from `_TABLE` gets no content matching at all — the honest answer when this
# module does not know how to compare two of them.
_TABLE = {
    "task": "tasks", "commitment": "commitments", "risk": "risks", "issue": "issues",
    "decision": "decisions", "pull_signal": "pull_signals", "milestone": "milestones",
    "deployment_moment": "deployment_moments", "value_story": "value_stories", "person": "persons",
}
_TEXT_FIELD = {
    "task": "description", "commitment": "description", "risk": "description",
    "issue": "description", "decision": "description", "pull_signal": "description",
    "deployment_moment": "name", "value_story": "outcome", "person": "name",
    "milestone": "name",
}
# The payload key that carries the same text as `_TEXT_FIELD`. `create_*` proposals all speak
# "description"; the native column does not always agree.
_PAYLOAD_TEXT_KEY = {"deployment_moment": "name", "value_story": "outcome", "person": "name",
                     "milestone": "name"}
_ACCOUNT_COL = {"commitment", "decision", "pull_signal", "value_story", "person"}
_PROGRAM_COL = {"task", "commitment", "risk", "issue", "decision", "pull_signal",
                "deployment_moment", "value_story", "milestone"}
# Targets whose duplicates are identified by more than their text (§6.7 check 3 and check 5).
# `milestone` is deliberately absent: the check requires at least two agreeing fields, and a
# milestone's only identity field beyond its name is `target_date`. An entry here would name a
# check that can never fire, which reads as coverage that does not exist. Name equality within the
# program is the real duplicate signal, and it runs.
_IDENTITY_FIELDS = {
    "task": ("internal_owner_id", "due_date"),
    "commitment": ("responsible_party_id", "internal_owner_id", "due_date"),
    "deployment_moment": ("event_date",),
}


def _scope_clause(target_type: str, account_id: str | None, program_id: str | None):
    """(sql, params) restricting a target table to this run's scope, or None when it cannot be.

    Returning None is the fail-closed branch: the caller skips the check entirely rather than
    running an unscoped query.
    """
    if target_type in _ACCOUNT_COL and account_id:
        if target_type in _PROGRAM_COL and program_id:
            return "account_id=? AND (program_id IS NULL OR program_id=?)", (account_id, program_id)
        return "account_id=?", (account_id,)
    if target_type in _PROGRAM_COL and program_id:
        return "program_id=?", (program_id,)
    return None


def _payload_text(target_type: str, payload: dict) -> str:
    key = _PAYLOAD_TEXT_KEY.get(target_type, "description")
    return proposals.normalize_text(payload.get(key) or payload.get("description") or payload.get("name") or "")


def _label(target_type: str, row) -> str:
    return (row[_TEXT_FIELD[target_type]] or "").strip() or f"{target_type} {row['id']}"


def _payload_of(prop) -> dict:
    raw = prop["payload_json"] if "payload_json" in prop.keys() else None
    return json.loads(raw) if raw else {}


# --- §6.6 enforcement -----------------------------------------------------------------------------
def already_resolved(conn, prop, run) -> dict | None:
    """The prior resolution of this exact proposal, if there is one.

    Identity is the fingerprint (§6.6's second identity), scoped to the same account **and the same
    program**. The fingerprint covers what is proposed and where it was read, not where it lands, so
    the same sentence extracted under two programs of one account fingerprints alike. Matching on
    account alone would then close program B's proposal against program A's record — no duplicate
    is created, which is what the check is for, but program B silently ends up with no record at
    all. Scoping strictly can at worst let a genuine duplicate through to a human, which is the
    survivable direction.

    This is the one check that is not a suggestion: acceptance must return this existing target
    instead of creating a second canonical record. It matches only proposals that actually resolved
    to something — a rejected twin is not a resolution, and re-proposing after a rejection is a
    legitimate second opinion, not a duplicate.
    """
    fingerprint = prop["proposal_fingerprint"]
    if not fingerprint:
        return None
    row = conn.execute(
        "SELECT p.id, p.status, p.resolved_target_type, p.resolved_target_id, p.resolved_at "
        "FROM extraction_proposals p JOIN extraction_runs r ON r.id = p.run_id "
        "WHERE p.proposal_fingerprint=? AND p.id<>? AND p.status IN ('accepted','resolved_existing') "
        "AND r.account_id IS ? AND r.program_id IS ? AND p.resolved_target_id IS NOT NULL "
        "ORDER BY p.resolved_at LIMIT 1",
        (fingerprint, prop["id"], run.get("account_id"), run.get("program_id")),
    ).fetchone()
    if not row:
        return None
    return {"proposal_id": row["id"], "status": row["status"],
            "target_type": row["resolved_target_type"], "target_id": row["resolved_target_id"],
            "resolved_at": row["resolved_at"]}


# --- §6.7 suggestions -----------------------------------------------------------------------------
def match_candidates(conn, prop, run, limit: int = 5) -> list[dict]:
    """Deterministic possible duplicates for one proposal. Never merges, never blocks.

    Ordered by how specific the evidence is, not by a score: an identical prior resolution first,
    then identical content, then an identity match on owners and dates. There is no similarity
    threshold anywhere in here, because a tunable threshold is a silent policy nobody reviews.
    """
    target_type = prop["target_type"]
    account_id, program_id = run.get("account_id"), run.get("program_id")
    payload = _payload_of(prop)
    out: list[dict] = []

    prior = already_resolved(conn, prop, run)
    if prior:
        out.append({
            "check": "identical_source_proposal", "kind": "proposal",
            "target_type": prior["target_type"], "id": prior["target_id"],
            "label": f"already resolved on {prior['resolved_at'] or 'an earlier review'}",
            "why": "The same source sentence, target, and extractor were reviewed before.",
            "suggests": "use_existing",
        })

    table = _TABLE.get(target_type)
    scope = _scope_clause(target_type, account_id, program_id) if table else None
    if not scope:
        return out[:limit]
    where, params = scope
    text = _payload_text(target_type, payload)
    rows = conn.execute(
        f"SELECT * FROM {table} WHERE {where} AND COALESCE(archived,0)=0 "
        "ORDER BY created_at DESC LIMIT 200", params).fetchall()

    for row in rows:
        if prop["target_id"] and row["id"] == prop["target_id"]:
            continue                                  # the record being updated is not its own duplicate
        row_text = proposals.normalize_text(row[_TEXT_FIELD[target_type]])
        if text and row_text == text:
            out.append({
                "check": "exact_content", "kind": "record", "target_type": target_type,
                "id": row["id"], "label": _label(target_type, row),
                "why": "An existing record already says exactly this.",
                "suggests": "use_existing",
            })
            continue
        fields = _IDENTITY_FIELDS.get(target_type)
        if not fields:
            continue
        supplied = [f for f in fields if payload.get(f)]
        # Every identity field the proposal supplied has to agree, and it has to supply at least
        # two. One matching due date is a coincidence; an owner AND a date is an identity.
        if len(supplied) >= 2 and all(row[f] == payload[f] for f in supplied):
            out.append({
                "check": "identity_fields", "kind": "record", "target_type": target_type,
                "id": row["id"], "label": _label(target_type, row),
                "why": "Same " + ", ".join(supplied.copy()) + " on an existing record.",
                "suggests": "review",
            })

    # §6.7 check 4, for updates only: somebody already accepted a newer value for this target.
    if prop["intent"] == "update" and prop["target_id"]:
        newer = conn.execute(
            "SELECT p.id, p.resolved_at FROM extraction_proposals p "
            "JOIN extraction_runs r ON r.id = p.run_id "
            "WHERE p.target_type=? AND p.resolved_target_id=? AND p.id<>? AND p.status='accepted' "
            "AND p.resolved_at > ? AND r.account_id IS ? ORDER BY p.resolved_at DESC LIMIT 1",
            (target_type, prop["target_id"], prop["id"], prop["created_at"], account_id)).fetchone()
        if newer:
            out.append({
                "check": "newer_accepted_value", "kind": "proposal", "target_type": target_type,
                "id": prop["target_id"], "label": f"updated on {newer['resolved_at']}",
                "why": "A later proposal was accepted against this record after this one was drafted.",
                "suggests": "review",
            })
    return out[:limit]


# --- §6.7 conflict preview / optimistic concurrency -----------------------------------------------
def conflict_preview(conn, prop, run, overrides: dict | None = None,
                     target_id: str | None = None) -> dict | None:
    """What an `update` would change, and whether it is safe to apply.

    `stale` is decided by comparing the target's `updated_at` against the `expected_target_updated_at`
    the proposal was drafted with — not by comparing dates on the sources. A source can be older than
    the record and still be right; what makes an update unsafe is that the record moved underneath
    it. Both source dates ride along anyway because §6.7 requires the reviewer to see them.

    `target_id` overrides the proposal's own target for the case the placeholder-fill path creates:
    the extractor names a person by text and the row is only chosen at accept time. That target
    still deserves the check, and skipping it because the draft could not name the row is how a
    stale update reaches a record nobody re-read.

    When a proposal carries no `expected_target_updated_at` it falls back to its own `created_at`.
    A proposal drafted before the record was last edited is exactly the situation the check exists
    for, and the alternative — no expectation, therefore never stale — makes the guard unreachable
    on every proposal the extractor writes.

    Returns None for anything that is not an update against an existing record.
    """
    target_id = target_id or prop["target_id"]
    if prop["intent"] != "update" or not target_id:
        return None
    target_type = prop["target_type"]
    table = _TABLE.get(target_type)
    if not table:
        return None
    row = conn.execute(f"SELECT * FROM {table} WHERE id=?", (target_id,)).fetchone()
    if not row:
        return {"target_type": target_type, "target_id": target_id, "missing": True,
                "stale": True, "fields": [],
                "reason": "The record this proposal updates no longer exists."}

    payload = {**_payload_of(prop), **(overrides or {})}
    keys = row.keys()
    fields = []
    for field in sorted(set(payload) - proposals.SCOPE_KEYS):
        if field not in keys:
            continue
        current, proposed = row[field], payload[field]
        fields.append({"field": field, "current": current, "proposed": proposed,
                       "changed": current != proposed})

    expected = prop["expected_target_updated_at"] or prop["created_at"]
    stale = bool(expected and row["updated_at"] and row["updated_at"] > expected)
    return {
        "target_type": target_type,
        "target_id": target_id,
        "target_updated_at": row["updated_at"],
        "expected_target_updated_at": expected,
        "stale": stale,
        "fields": fields,
        "source_dates": {
            # When the material behind the proposal was observed, and when the material behind the
            # record's current value was. Two different questions from "which is newer in the DB".
            "proposed": _source_date(conn, run.get("interaction_id")) or (prop["created_at"] or "")[:10],
            "current": _source_date(conn, row["source_interaction_id"] if "source_interaction_id" in keys else None),
        },
        "reason": ("This record changed after the proposal was drafted; review the values before "
                   "applying." if stale else None),
    }


def _source_date(conn, interaction_id):
    if not interaction_id:
        return None
    row = conn.execute("SELECT occurred_on FROM interactions WHERE id=?", (interaction_id,)).fetchone()
    return row["occurred_on"] if row else None
