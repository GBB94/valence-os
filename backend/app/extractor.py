"""Transcript extractor — v4.

Swappable behind one interface so a real LLM can replace the mock later WITHOUT
changing callers. The mock is a deterministic, purely-local function: no network,
no tools, no outbound calls. It only ever emits proposals of a strict, predefined
mutation shape; nothing here writes to the database. Document content is treated as
DATA to pattern-match, never as instructions to follow.
"""
from __future__ import annotations

import re

MODEL_VERSION = "mock-extractor-1"
PROMPT_VERSION = "cue-rules-1"

# Ordered cue rules: first match per sentence wins. Each yields a strict mutation type.
_RULES = [
    ("create_commitment", re.compile(r"\b(will|i'?ll|we'?ll|going to|commit to|agreed to send|by (mon|tue|wed|thu|fri|next|end of))\b", re.I)),
    ("create_decision", re.compile(r"\b(decided|we agreed|decision:|agreed that|signed off)\b", re.I)),
    ("create_risk", re.compile(r"\b(risk|concern|worried|may slip|at risk|jeopardi|could delay|blocker|blocked)\b", re.I)),
    ("create_issue", re.compile(r"\b(issue|broken|not working|failing|problem|bug)\b", re.I)),
    ("create_task", re.compile(r"\b(action item|action:|to-?do|follow up|follow-up|next step)\b", re.I)),
]
_BLOCKER = re.compile(r"\b(block|blocked|blocker|cannot proceed|halt)\b", re.I)


def _sentences(text: str) -> list[str]:
    # split on line breaks and sentence terminators; keep it boring and deterministic
    parts = re.split(r"(?<=[.!?])\s+|\n+", text.strip())
    return [p.strip(" -•\t") for p in parts if len(p.strip()) > 8]


class MockExtractor:
    model_version = MODEL_VERSION
    prompt_version = PROMPT_VERSION

    def extract(self, transcript: str) -> list[dict]:
        proposals = []
        seen = set()
        for sent in _sentences(transcript):
            key = sent.lower()
            if key in seen:
                continue
            for mutation_type, pattern in _RULES:
                if pattern.search(sent):
                    payload = {"description": _clean(sent)}
                    if mutation_type == "create_risk":
                        payload["is_blocker"] = bool(_BLOCKER.search(sent))
                        payload["severity"] = "high" if payload["is_blocker"] else "medium"
                    proposals.append({
                        "mutation_type": mutation_type,
                        "payload": payload,
                        "source_span": sent,
                        "confidence": "high" if mutation_type in ("create_commitment", "create_decision") else "medium",
                    })
                    seen.add(key)
                    break
        return proposals


def _clean(sentence: str) -> str:
    # strip a leading speaker label like "Dana:" so the description reads cleanly
    return re.sub(r"^[A-Z][a-zA-Z .]{0,30}:\s*", "", sentence).strip()


# Swap point: return a real LLM-backed extractor here once approved (Section 12 Q3).
def get_extractor():
    return MockExtractor()
