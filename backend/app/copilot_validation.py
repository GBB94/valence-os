"""Deterministic validation for claim support, scope, privacy, and writing style."""
from __future__ import annotations

import re

VALIDATOR_VERSION = "copilot-validator-v1"


def validate_answer(packet: dict, output: dict) -> list[str]:
    if output.get("abstain"):
        return [] if not output.get("answer_markdown") else ["an abstention cannot carry a factual answer body"]
    errors: list[str] = []
    by_packet = {item["packet_id"]: item for item in packet["items"]}
    for claim in output.get("claims") or []:
        packet_ids = claim.get("packet_ids") or []
        if claim.get("kind") in ("fact", "calculation") and not packet_ids:
            errors.append(f"claim {claim.get('sequence')} has no citation")
            continue
        if any(pid not in by_packet for pid in packet_ids):
            errors.append(f"claim {claim.get('sequence')} cites a packet id not retrieved for this run")
            continue
        if claim.get("kind") == "fact":
            statements = {by_packet[pid]["statement"] for pid in packet_ids}
            if claim.get("claim_text") not in statements:
                errors.append(f"claim {claim.get('sequence')} is not entailed by its cited snapshot")
        if claim.get("kind") == "recommendation":
            if not claim.get("claim_text", "").startswith("Suggested move:"):
                errors.append(f"claim {claim.get('sequence')} does not label the recommendation")
            elif not any(
                    claim["claim_text"] == f"Suggested move: {by_packet[pid]['fields'].get('next_action')}"
                    for pid in packet_ids if pid in by_packet):
                errors.append(f"claim {claim.get('sequence')} recommendation is not present in its cited snapshot")
    for item in packet["items"]:
        if item["freshness_state"] in ("stale", "suppressed") and "value" in item["fields"]:
            errors.append(f"{item['packet_id']} leaks a numeric value in {item['freshness_state']} evidence")
    text = output.get("answer_markdown") or ""
    in_gaps = False
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.lower() == "### evidence gaps":
            in_gaps = True
            continue
        if not stripped or stripped.startswith("#") or in_gaps:
            continue
        if not stripped.startswith("-"):
            errors.append("answer contains factual prose outside the claim-and-citation schema")
            continue
        cited = re.findall(r"\[(p\d{3})\]", stripped)
        if not cited or any(pid not in by_packet for pid in cited):
            errors.append("answer contains an uncited or invented factual bullet")
    if re.search(r"https?://", text):
        errors.append("model-created URLs are not permitted")
    return errors


def lint_style(text: str, rules: dict) -> list[str]:
    errors = []
    if rules.get("no_em_dash") and "—" in text:
        errors.append("style rule: em dashes are not allowed")
    maximum = rules.get("max_characters")
    if maximum is not None and len(text) > int(maximum):
        errors.append(f"style rule: text exceeds {maximum} characters")
    max_headings = rules.get("max_headings")
    if max_headings is not None and sum(1 for line in text.splitlines() if line.startswith("#")) > int(max_headings):
        errors.append(f"style rule: text exceeds {max_headings} headings")
    for phrase in rules.get("banned_phrases") or []:
        if phrase.lower() in text.lower():
            errors.append(f"style rule: banned phrase '{phrase}'")
    for heading in rules.get("required_headings") or []:
        if not any(line.lstrip("# ").strip().lower() == heading.lower() for line in text.splitlines()):
            errors.append(f"style rule: missing heading '{heading}'")
    return errors
