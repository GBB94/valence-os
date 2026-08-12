"""Versioned, code-owned Call Coach rubrics.

The rubric describes what evidence to look for; it never authorizes a score. Changing a rubric is
a reviewed code change and existing runs retain the key/version they used.
"""
from __future__ import annotations

UNIVERSAL_SKILLS = {
    "framing_outcome": "Frame the purpose and a useful outcome",
    "curiosity_questions": "Use purposeful questions to surface what matters",
    "listening_follow_up": "Follow the answer instead of returning to the script",
    "synthesis": "Synthesize what was heard and test the synthesis",
    "constructive_challenge": "Name a tension or challenge with care",
    "decision_clarity": "Separate preferences, constraints, decisions, and open questions",
    "stakeholder_strategy": "Clarify influence, ownership, sponsorship, and missing voices",
    "value_measurement": "Connect work to evidence, outcomes, and measurement",
    "commercial_clarity": "Make budget, authority, timing, and tradeoffs discussable",
    "ownership_next_steps": "Leave explicit owners, actions, dates, and follow-through",
    "clarity_concision": "Make the intervention easy to understand and act on",
    "trust_safety": "Create enough trust to surface risk and disagreement honestly",
}


def _rubric(label: str, priorities: tuple[str, ...], watch_for: tuple[str, ...]) -> dict:
    return {"version": 1, "label": label, "priorities": priorities, "watch_for": watch_for}


RUBRICS = {
    "account_kickoff": _rubric(
        "Account kickoff",
        ("framing_outcome", "stakeholder_strategy", "value_measurement", "ownership_next_steps"),
        ("shared outcome", "governance", "success measure", "owner and date"),
    ),
    "deployment_session": _rubric(
        "Deployment session",
        ("decision_clarity", "constructive_challenge", "ownership_next_steps", "trust_safety"),
        ("constraint versus preference", "launch risk", "decision", "owner and date"),
    ),
    "stakeholder_discovery": _rubric(
        "Stakeholder discovery",
        ("curiosity_questions", "listening_follow_up", "synthesis", "stakeholder_strategy"),
        ("follow-up question", "tested synthesis", "missing stakeholder", "business consequence"),
    ),
    "executive_qbr": _rubric(
        "Executive review / QBR",
        ("framing_outcome", "value_measurement", "constructive_challenge", "decision_clarity"),
        ("decision required", "comparable evidence", "risk", "executive ask"),
    ),
    "renewal_expansion": _rubric(
        "Renewal or expansion",
        ("commercial_clarity", "value_measurement", "stakeholder_strategy", "ownership_next_steps"),
        ("authority", "budget", "timing", "value proof", "next commercial step"),
    ),
    "risk_recovery": _rubric(
        "Risk recovery",
        ("trust_safety", "listening_follow_up", "constructive_challenge", "ownership_next_steps"),
        ("acknowledgement", "root cause", "recovery owner", "check-back date"),
    ),
    "internal_alignment": _rubric(
        "Internal alignment",
        ("synthesis", "decision_clarity", "constructive_challenge", "ownership_next_steps"),
        ("disagreement", "decision rule", "single owner", "escalation condition"),
    ),
    "interview_networking": _rubric(
        "Interview or networking",
        ("framing_outcome", "curiosity_questions", "listening_follow_up", "clarity_concision"),
        ("specific question", "follow-up", "relevant story", "clear close"),
    ),
    "other": _rubric(
        "Other call",
        ("framing_outcome", "listening_follow_up", "synthesis", "ownership_next_steps"),
        ("purpose", "follow-up", "tested understanding", "clear next step"),
    ),
}


def get(key: str) -> dict:
    return RUBRICS.get(key, RUBRICS["other"])


def listing() -> list[dict]:
    return [{"key": key, **value} for key, value in RUBRICS.items()]
