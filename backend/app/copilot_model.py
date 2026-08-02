"""Deterministic mock planner and answer adapter for the Account Copilot.

No real provider is connected by this module. The mock exercises the same structured contract as a
future approved adapter, but its output is built only from packet statements so support validation is
deterministic and CI-safe.
"""
from __future__ import annotations

import os
from typing import Any

from . import connections

MODEL_VERSION = "copilot-mock-v1"
PROMPT_VERSION = "copilot-prompt-v1"


def backend_state() -> dict:
    mode = os.environ.get("COPILOT_BACKEND", "mock").strip().lower()
    if mode != "mock":
        # Approval is necessary but not sufficient: there is intentionally no network adapter in
        # Stage 12. Selecting one cannot accidentally fall through to extraction credentials.
        connections.require_real_connection("copilot_endpoint", mode)
        raise RuntimeError("copilot real mode has no implementation; use COPILOT_BACKEND=mock")
    return {"mode": "mock", "model": MODEL_VERSION, "prompt": PROMPT_VERSION,
            "network": False, "writes": False, "tools": []}


def classify_intent(question: str, requested: str | None = None) -> str:
    if requested in {"fact", "synthesis", "changes", "weekly", "draft"}:
        return requested
    q = question.lower()
    if any(term in q for term in ("what changed", "since last", "since ")):
        return "changes"
    if any(term in q for term in ("this week", "plan my week", "attention")):
        return "weekly"
    if any(term in q for term in ("draft", "write a note")):
        return "draft"
    if any(term in q for term in ("blocking", "why", "across", "summar")):
        return "synthesis"
    return "fact"


def strict_plan(question: str, scope_type: str, account_id: str | None,
                program_id: str | None, requested_intent: str | None = None,
                time_window_start: str | None = None,
                time_window_end: str | None = None) -> dict:
    """Planner sees only trusted operator input and governed vocabulary."""
    intent = classify_intent(question, requested_intent)
    readers = ({"changes": ["get_material_changes"], "weekly": ["get_week_inputs"]}
               .get(intent, ["get_account_snapshot", "search_records"]))
    return {"intent": intent, "scope": {"type": scope_type, "account_id": account_id,
                                         "program_id": program_id},
            "entities": [], "time_window": {"start": time_window_start, "end": time_window_end},
            "requested_audience": "internal", "readers": readers, "output_mode": "answer"}


def _coverage(items: list[dict], excluded: list[dict], ambiguities: list[dict]) -> str:
    if not items:
        return "insufficient"
    if ambiguities:
        return "conflicted"
    if any(item["freshness_state"] in ("stale", "suppressed", "unknown") for item in items):
        return "partial"
    # Conflicts are intentionally narrow: two current status assessments for the same dimension
    # with different values are not silently resolved by ordering.
    statuses: dict[tuple[str | None, str], set[str]] = {}
    for item in items:
        if item["record_type"] != "status_assessment":
            continue
        f = item["fields"]
        statuses.setdefault((item.get("account_id"), f.get("dimension") or ""), set()).add(f.get("value"))
    if any(len(values) > 1 for values in statuses.values()):
        return "conflicted"
    return "partial" if excluded else "supported"


def generate(packet: dict, run: dict) -> dict[str, Any]:
    backend_state()
    items = packet["items"]
    if not items:
        return {"abstain": True, "diagnostic": "No in-scope native record supports this question.",
                "claims": [], "answer_markdown": None, "evidence_state": "insufficient",
                "gaps": ["No matching current record was found in the selected scope."]}

    evidence_state = _coverage(items, packet["excluded"], packet.get("ambiguities") or [])
    claims = []
    selected = items[:8 if run["intent"] in ("changes", "weekly") else 6]
    for sequence, item in enumerate(selected, 1):
        kind = "fact"
        text = item["statement"]
        if item["record_type"] == "attention_item" and item["fields"].get("next_action"):
            kind = "recommendation"
            text = "Suggested move: " + item["fields"]["next_action"]
        claims.append({"sequence": sequence, "kind": kind, "claim_text": text,
                       "support_state": "supported", "packet_ids": [item["packet_id"]]})

    heading = {"changes": "What changed", "weekly": "This week's operating view",
               "draft": "Grounded internal note"}.get(run["intent"], "Answer")
    lines = [f"## {heading}", ""]
    for claim in claims:
        label = "Inference: " if claim["kind"] == "inference" else ""
        lines.append(f"- {label}{claim['claim_text']} [{claim['packet_ids'][0]}]")
    gaps = []
    for ambiguity in packet.get("ambiguities") or []:
        candidates = ", ".join(
            f"{candidate['record_id']} [{candidate['packet_id']}]"
            for candidate in ambiguity["candidates"])
        gaps.append(
            f"Disambiguation required for {ambiguity['record_type']} "
            f"'{ambiguity['label']}': choose {candidates}.")
    if packet["excluded"]:
        gaps.append(f"{len(packet['excluded'])} candidate record(s) were excluded by reader or safety rules.")
    for item in items:
        if item["freshness_state"] == "stale":
            gaps.append(f"{item['record_type']} {item['record_id']} is stale; its prior number was withheld.")
        elif item["freshness_state"] == "suppressed":
            gaps.append(f"{item['record_type']} {item['record_id']} is privacy-suppressed.")
    if evidence_state == "conflicted" and not packet.get("ambiguities"):
        gaps.append("Current-looking records conflict; no preferred version was selected.")
    if gaps:
        lines += ["", "### Evidence gaps", *[f"- {gap}" for gap in gaps]]
    return {"abstain": False, "answer_markdown": "\n".join(lines), "claims": claims,
            "evidence_state": evidence_state, "gaps": gaps,
            "estimated_input_tokens": max(1, packet["packet_bytes"] // 4),
            "estimated_output_tokens": max(1, len("\n".join(lines)) // 4)}
