"""The canonical proposal contract — RELATIONSHIP-READINESS-SPEC.md §6.

Every proposal in this app, whoever drafted it, is one row in `extraction_proposals` shaped by the
rules below. There is deliberately no second proposal model (§6.1): no `intake_items`, no payloads
hanging off `capture_inbox_items`.

Three rules do the real work here, and each rejects a more obvious design:

  * **Intent is separate from target.** The pre-RR-2 `mutation_type` fused the verb and the noun
    into one enum, which is why it could only ever create — expressing "correct this Task's owner"
    would have meant inventing `update_task_owner`, then one enum value per field forever.
    `INTENTS` and `TARGET_ALLOWLIST` split them.
  * **The allowlist is a pair, not two lists.** `(intent, target_type)` is allowed together or not
    at all. A target that can legally be created is not thereby updatable: an update needs an
    audited patch path AND a field allowlist, and most targets have neither yet.
  * **A proposal can never assert a readiness state.** `FORBIDDEN_FIELDS` and the absence of any
    readiness target from the allowlist are both enforced here rather than left to review, because
    the field a proposal would need is exactly the one somebody adds for convenience.

Nothing in this module writes. It decides what a proposal *is* and whether it is expressible;
acceptance still runs through the native audited services (§6.8).
"""
from __future__ import annotations

import hashlib
import json
import re

# --- §6.2 intent ---------------------------------------------------------------------------------
INTENTS = ("create", "update", "link", "close", "no_change")

# `link` and `close` are in the vocabulary and in the migration's CHECK, and no proposal may carry
# them. The original reason — "until Slice 5 exists" — expired when Slice 5 landed, and the reason
# that replaced it is stronger: Slice 5 made linking and closing *governed operator commands*, with
# scope checks on both sides, an explicit refusal when an open action is offered as evidence, and a
# successor note stating that closing an action records no evidence. A proposal that carried
# `link` or `close` would assert a relationship or a closure and route around all of it. The
# vocabulary is fixed by the specification; the enabled subset is not.
DEFERRED_INTENTS = frozenset({"link", "close"})
DEFERRED_INTENT_REASON = ("'{intent}' proposals are disabled: relating and closing records are "
                          "governed operator commands, and a proposal may not assert either")

# --- §6.3 allowlisted targets --------------------------------------------------------------------
# A `(intent, target_type)` pair is listed here only when a native, audited write path and a strict
# payload schema already exist for it — §6.3's closing condition. This is the whole allowlist:
# anything absent is rejected, so widening it is a code change reviewed next to the write path it
# needs, never a data change.
TARGET_ALLOWLIST: dict[str, frozenset[str]] = {
    "task":              frozenset({"create", "no_change"}),
    "commitment":        frozenset({"create", "no_change"}),
    "risk":              frozenset({"create", "no_change"}),
    "issue":             frozenset({"create", "no_change"}),
    "decision":          frozenset({"create", "no_change"}),
    # The one update the app can already perform: filling a placeholder person names a position
    # that was known but unattributed. It patches through `repo.patch`, which audits.
    "person":            frozenset({"create", "update", "no_change"}),
    "pull_signal":       frozenset({"create", "no_change"}),
    "deployment_moment": frozenset({"create", "no_change"}),
    "value_story":       frozenset({"create", "no_change"}),
}

# For an `update`, the payload may name only these fields. An unlisted field is not silently
# dropped — it fails the proposal, because a partially-applied update is worse than a rejected one.
UPDATE_FIELD_ALLOWLIST: dict[str, frozenset[str]] = {
    # Identity of a position that already existed. `is_placeholder` is not here: it is a
    # consequence of naming somebody, decided by the accept path, not something a source asserts.
    # `description` is listed because it is not decoration on this target: the legacy
    # `fill_placeholder` accept path falls back to it when the extractor found no explicit `name`,
    # so it really can set the person's name and must be allowlisted as such rather than waved
    # through as narrative.
    "person": frozenset({"name", "title", "placeholder_person_id", "description"}),
}

# Fields no proposal may set on any target, whatever the intent. Each is either a trust boundary or
# a state the app must compute rather than accept from a source (§6.3, closing paragraph).
FORBIDDEN_FIELDS: dict[str, frozenset[str]] = {
    # Promotion to a client-facing artifact is an operator act. A source that could set it would
    # publish itself.
    "value_story": frozenset({"visibility_class", "identifiable", "evidence_tier"}),
    # Derived from interactions, never asserted (CLAUDE.md).
    "*": frozenset({"last_touch_at", "archived", "archived_at", "archived_by",
                    # Readiness is a query-time projection. No proposal may name one.
                    "requirement_key", "pillar", "readiness_state", "composite_status", "phase"}),
}

# --- compatibility with the pre-RR-2 enum ---------------------------------------------------------
# `mutation_type` stays populated until every reader is normalized (§6.5). This is the only place
# the two vocabularies meet, in both directions, so they cannot drift apart in separate call sites.
LEGACY_MUTATIONS: dict[str, tuple[str, str]] = {
    "create_commitment":        ("create", "commitment"),
    "create_risk":              ("create", "risk"),
    "create_decision":          ("create", "decision"),
    "create_task":              ("create", "task"),
    "create_issue":             ("create", "issue"),
    # The one legacy mutation that patches a record it did not create.
    "fill_placeholder":         ("update", "person"),
    "log_pull_signal":          ("create", "pull_signal"),
    "create_deployment_moment": ("create", "deployment_moment"),
    "create_value_story":       ("create", "value_story"),
}
_LEGACY_BY_PAIR = {pair: mt for mt, pair in LEGACY_MUTATIONS.items()}


def legacy_pair(mutation_type: str) -> tuple[str, str]:
    """(intent, target_type) for a pre-RR-2 mutation."""
    try:
        return LEGACY_MUTATIONS[mutation_type]
    except KeyError:
        raise ValueError(f"unknown mutation_type '{mutation_type}'") from None


def legacy_mutation(intent: str, target_type: str) -> str | None:
    """The `mutation_type` a normalized pair maps back to, or None when it has no legacy name.

    A new pair with no legacy equivalent returns None rather than a plausible-looking invention:
    the column's CHECK would reject the invention anyway, and a wrong legacy label read by the old
    UI is worse than an absent one. Such pairs are why the column is nullable from RR-2 forward.
    """
    return _LEGACY_BY_PAIR.get((intent, target_type))


# --- validation -----------------------------------------------------------------------------------
class ProposalError(ValueError):
    """A proposal that cannot be expressed. Callers surface this as a 422, never as a warning."""


def check_pair(intent: str, target_type: str) -> None:
    """Raise unless this exact (intent, target) pair is allowed right now."""
    if intent not in INTENTS:
        raise ProposalError(f"'{intent}' is not a proposal intent")
    if intent in DEFERRED_INTENTS:
        raise ProposalError(DEFERRED_INTENT_REASON.format(intent=intent))
    allowed = TARGET_ALLOWLIST.get(target_type)
    if allowed is None:
        # Fails closed by name, so the operator can see which target was refused and the log says
        # what is missing: a native write path, not a permission.
        raise ProposalError(f"'{target_type}' is not an allowlisted proposal target")
    if intent not in allowed:
        raise ProposalError(f"'{intent}' is not allowed on a {target_type} proposal")


def check_payload(intent: str, target_type: str, payload: dict) -> None:
    """Raise on any field this proposal may not set. Never edits the payload."""
    if not isinstance(payload, dict):
        raise ProposalError("proposal payload must be an object")
    banned = FORBIDDEN_FIELDS.get("*", frozenset()) | FORBIDDEN_FIELDS.get(target_type, frozenset())
    hit = sorted(set(payload) & banned)
    if hit:
        raise ProposalError(f"a proposal may not set {', '.join(hit)} on a {target_type}")
    if intent == "update":
        allowed = UPDATE_FIELD_ALLOWLIST.get(target_type, frozenset())
        # Scope keys are context, not edits: they say which record, not what to change.
        extra = sorted(set(payload) - allowed - SCOPE_KEYS)
        if extra:
            raise ProposalError(
                f"a {target_type} update may not change {', '.join(extra)} "
                f"(allowlisted: {', '.join(sorted(allowed)) or 'none'})")


SCOPE_KEYS = frozenset({"account_id", "program_id", "id", "target_id"})


# --- §6.6 identity ---------------------------------------------------------------------------------
def content_hash(text: str) -> str:
    """Hash of the source material itself, so a correction or retranscription reads as new."""
    return "sha256:" + hashlib.sha256((text or "").encode("utf-8")).hexdigest()


def source_version_key(*, source_kind: str, provider: str | None = None,
                       external_id: str | None = None, hash_: str | None = None) -> str | None:
    """Provider + external id + content hash + source kind, or None when there is no identity.

    §6.6 is explicit that `external_id` alone is insufficient: a provider item can be corrected,
    retranscribed, or reprocessed. So a key without a content hash is not returned at all. None
    means "this run cannot be deduplicated", which sends the material to review — the safe end.
    Returning a weaker key would silently suppress a corrected transcript as a duplicate.
    """
    if not hash_:
        return None
    return "|".join([source_kind or "", provider or "", external_id or "", hash_])


_WS = re.compile(r"\s+")


def _normalize_value(v):
    if isinstance(v, str):
        return _WS.sub(" ", v).strip().casefold()
    if isinstance(v, dict):
        return {k: _normalize_value(x) for k, x in sorted(v.items()) if x not in (None, "", [], {})}
    if isinstance(v, list):
        return [_normalize_value(x) for x in v]
    return v


def normalize_text(value: str | None) -> str:
    """Case- and whitespace-insensitive form of a free-text field, for content comparison."""
    return _WS.sub(" ", value or "").strip().casefold()


def scoped_payload(payload: dict | None) -> dict:
    """The payload reduced to what identifies a proposal: absent values dropped, text normalized.

    Whitespace and case are dropped because two extractions of the same sentence must fingerprint
    alike; nothing else is dropped, because a differing due date IS a different proposal.
    """
    return _normalize_value(dict(payload or {}))


def proposal_fingerprint(*, intent: str, target_type: str, payload: dict | None,
                         target_id: str | None = None, source_span: str | None = None,
                         source_locator: str | None = None,
                         extractor_version: str | None = None) -> str:
    """§6.6's second identity: what is being proposed, about what, from where, by which extractor.

    The extractor version is included deliberately. A new extractor reading the same sentence is a
    new proposal worth reviewing, not a duplicate to suppress — the source-version key already
    handles the same extractor re-reading the same material.
    """
    material = {
        "intent": intent, "target_type": target_type, "target_id": target_id or None,
        "payload": scoped_payload(payload),
        "span": _normalize_value(source_span) or None,
        "locator": (source_locator or "").strip() or None,
        "extractor": extractor_version or None,
    }
    blob = json.dumps(material, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return "sha256:" + hashlib.sha256(blob.encode("utf-8")).hexdigest()


# --- §6.4 normalized read shape ---------------------------------------------------------------------
def normalized(row: dict, run: dict | None = None) -> dict:
    """The §6.4 contract for one stored proposal, joined to its run for source and scope.

    `confidence` rides along as explanatory metadata only. It never auto-accepts, never ranks above
    canonical work, and never relaxes validation — which is why nothing in this module reads it.
    """
    run = run or {}
    payload = row.get("payload")
    if payload is None:
        payload = json.loads(row["payload_json"]) if row.get("payload_json") else {}
    warnings = row.get("validation_warnings_json")
    return {
        "id": row["id"],
        "run_id": row["run_id"],
        "account_id": run.get("account_id"),
        "program_id": run.get("program_id"),
        "source": {
            "kind": run.get("source_kind"),
            "id": run.get("interaction_id"),
            "source_reference_id": row.get("source_reference_id") or run.get("source_reference_id"),
            "external_id": run.get("external_id"),
            "content_hash": run.get("content_hash"),
            "span": row.get("source_span"),
            "locator": row.get("source_locator"),
        },
        "intent": row.get("intent"),
        "target_type": row.get("target_type"),
        "target_id": row.get("target_id"),
        "expected_target_updated_at": row.get("expected_target_updated_at"),
        "payload": payload,
        "status": row["status"],
        "confidence": row.get("confidence"),
        "validation_warnings": json.loads(warnings) if warnings else [],
        "match_candidates": row.get("match_candidates") or [],
        "resolved_target": (
            {"type": row["resolved_target_type"], "id": row["resolved_target_id"],
             "at": row.get("resolved_at")}
            if row.get("resolved_target_type") and row.get("resolved_target_id") else None),
        "proposal_fingerprint": row.get("proposal_fingerprint"),
        "rejection_reason": row.get("rejection_reason"),
        "superseded_by_id": row.get("superseded_by_id"),
        # Retained per §6.5 until every reader is normalized.
        "mutation_type": row.get("mutation_type"),
        "created_at": row["created_at"],
    }
