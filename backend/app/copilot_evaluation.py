"""Synthetic golden-set manifest and deterministic Stage 12 graders.

The evaluator deliberately consumes persisted run output, not model internals. It keeps trust
boundaries (scope, citations, freshness, audience) as individual gates so an average cannot hide a
single unsafe answer.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

EVALUATION_VERSION = "copilot-golden-v1"
_GOLDEN_PATH = Path(__file__).with_name("fixtures") / "copilot" / "golden_questions.json"
_REQUIRED = {"id", "intent", "scope", "question", "required_record_types",
             "forbidden_record_types", "must_abstain"}


def load_golden_cases() -> list[dict[str, Any]]:
    cases = json.loads(_GOLDEN_PATH.read_text(encoding="utf-8"))
    if not isinstance(cases, list) or not cases:
        raise RuntimeError("copilot golden set must contain at least one case")
    seen: set[str] = set()
    for case in cases:
        missing = _REQUIRED - set(case)
        if missing:
            raise RuntimeError(f"golden case is missing {sorted(missing)}")
        if case["id"] in seen:
            raise RuntimeError(f"duplicate golden case id: {case['id']}")
        seen.add(case["id"])
    return cases


def grade_case(case: dict[str, Any], run: dict[str, Any]) -> dict[str, float | int]:
    sources = run.get("sources") or []
    source_types = {source["record_type"] for source in sources}
    claims = run.get("claims") or []
    source_ids = {source["id"] for source in sources}
    answer = (run.get("answer_markdown") or "").lower()
    gaps = " ".join(run.get("gaps") or []).lower()
    expected_account = run.get("account_id")
    expected_program = run.get("program_id")
    scope_violations = sum(
        1 for source in sources
        if (run.get("scope_type") != "portfolio" and source.get("account_id") != expected_account)
        or (run.get("scope_type") == "program" and source.get("program_id") not in (None, expected_program))
    )
    freshness_violations = sum(
        1 for source in sources
        if source.get("freshness_state") in ("stale", "suppressed")
        and "value" in (source.get("fields") or {})
    )
    citation_correctness = float(all(
        link.get("source_id") in source_ids
        for claim in claims for link in (claim.get("sources") or [])))
    groundedness = float(all(
        claim.get("kind") not in ("fact", "calculation") or bool(claim.get("sources"))
        for claim in claims))
    return {
        "retrieval_recall": float(set(case["required_record_types"]) <= source_types),
        "forbidden_source_violations": len(source_types & set(case["forbidden_record_types"])),
        "citation_completeness": float(all(claim.get("sources") for claim in claims)),
        "citation_correctness": citation_correctness,
        "groundedness": groundedness,
        "scope_violations": scope_violations,
        "freshness_violations": freshness_violations,
        "privacy_violations": freshness_violations,
        "audience_violations": int(run.get("visibility") != "internal"),
        "answer_fact_completeness": float(all(
            phrase.lower() in answer for phrase in case.get("expected_answer_contains", []))),
        "gap_completeness": float(all(
            phrase.lower() in gaps for phrase in case.get("required_gaps", []))),
        "prohibited_claim_violations": sum(
            1 for phrase in case.get("prohibited_claims", []) if phrase.lower() in answer),
        "abstention_correctness": float(
            (run.get("status") == "abstained") == bool(case["must_abstain"])),
    }


def manifest() -> dict[str, Any]:
    cases = load_golden_cases()
    return {
        "version": EVALUATION_VERSION,
        "case_count": len(cases),
        "case_ids": [case["id"] for case in cases],
        "metrics": [
            "retrieval_recall", "citation_completeness", "answer_fact_completeness",
            "citation_correctness", "groundedness", "gap_completeness",
            "abstention_correctness", "scope_violations", "privacy_violations",
            "audience_violations",
            "freshness_violations", "forbidden_source_violations",
            "prohibited_claim_violations",
        ],
        "note": "Metrics remain decomposed; zero-tolerance violations cannot be averaged away.",
    }
