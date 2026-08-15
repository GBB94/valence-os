"""Strict, model-neutral contract for Call Coach output.

Completed-call feedback is small, exact-cited, and about the operator-confirmed speaker only. This
module contains no database access and no model client, so the same validator gates mock, manual,
and any future approved provider.
"""
from __future__ import annotations

import re
from typing import Any

CONTRACT_VERSION = "call-coach-v1"
PROMPT_VERSION = "call-coach-prompt-v1"
MODEL_VERSION = "deterministic-local-v1"
MAX_SOURCE_BYTES = 1_048_576
MAX_OBSERVATIONS_PER_KIND = 2

FORBIDDEN_KEYS = frozenset({
    "score", "rating", "confidence", "sentiment", "emotion", "personality", "deception",
    "authenticity", "quality", "probability", "percentile", "talk_ratio", "filler_words",
})
FORBIDDEN_TEXT = re.compile(
    r"\b(sentiment|emotion(?:al)? state|personality|deception|lie detector|authenticity score|"
    r"confidence score|talk[- ]?ratio|filler[- ]?word score)\b", re.IGNORECASE)

TURN_RE = re.compile(
    r"^(?:\[(?P<timestamp>[^\]]{1,24})\]\s*)?"
    r"(?P<speaker>[^:\n]{1,60}):\s*(?P<text>.+)$"
)


def transcript_turns(source: str) -> list[dict]:
    """Parse conservative `Speaker: text` lines while retaining exact character offsets."""
    turns: list[dict] = []
    offset = 0
    for raw in source.splitlines(keepends=True):
        line = raw.rstrip("\r\n")
        match = TURN_RE.match(line.strip())
        if match:
            text = match.group("text").strip()
            # Locate inside the original line, not the stripped copy. Exact source text is the
            # citation, so offset arithmetic is checked again by the validator before persistence.
            local = line.find(text)
            turns.append({
                "speaker": match.group("speaker").strip(),
                "timestamp": match.group("timestamp"),
                "text": text,
                "start": offset + local,
                "end": offset + local + len(text),
            })
        offset += len(raw)
    if turns:
        return turns

    # Notes or scripts without speaker labels still have exact-citable paragraphs. They are
    # content-only: caller must not attribute them to a person.
    offset = 0
    for raw in source.splitlines(keepends=True):
        text = raw.strip()
        if text:
            local = raw.find(text)
            turns.append({"speaker": None, "timestamp": None, "text": text,
                          "start": offset + local, "end": offset + local + len(text)})
        offset += len(raw)
    return turns


def speaker_keys(source: str) -> list[str]:
    return list(dict.fromkeys(turn["speaker"] for turn in transcript_turns(source)
                              if turn["speaker"]))


def _walk(value: Any, path: str = "output"):
    if isinstance(value, dict):
        for key, child in value.items():
            lowered = str(key).lower()
            if lowered in FORBIDDEN_KEYS or any(token in lowered for token in FORBIDDEN_KEYS):
                raise ValueError(f"{path}.{key} is not part of the coaching contract")
            yield from _walk(child, f"{path}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from _walk(child, f"{path}[{index}]")
    elif isinstance(value, str) and FORBIDDEN_TEXT.search(value):
        raise ValueError(f"{path} contains a prohibited inference")


def validate(output: dict, source: str, coached_speaker: str | None) -> dict:
    """Validate shape, evidence, speaker fidelity, and prohibited inference classes."""
    list(_walk(output))
    observations = output.get("observations")
    if not isinstance(observations, list):
        raise ValueError("output.observations must be a list")
    strengths = sum(item.get("kind") == "strength" for item in observations)
    opportunities = sum(item.get("kind") == "opportunity" for item in observations)
    if strengths > MAX_OBSERVATIONS_PER_KIND or opportunities > MAX_OBSERVATIONS_PER_KIND:
        raise ValueError("coaching output exceeds the two-by-two observation limit")
    priority_count = sum(bool(item.get("is_top_priority")) for item in observations)
    if priority_count > 1:
        raise ValueError("coaching output has more than one top priority")

    for index, item in enumerate(observations):
        if item.get("kind") not in {"strength", "opportunity"}:
            raise ValueError(f"observation {index} has an unknown kind")
        if item.get("impact_type") not in {"observed", "inferred"}:
            raise ValueError(f"observation {index} has an unknown impact type")
        start, end = item.get("source_start"), item.get("source_end")
        span = item.get("source_span")
        if not isinstance(start, int) or not isinstance(end, int) or start < 0 or end <= start:
            raise ValueError(f"observation {index} has invalid source offsets")
        if source[start:end] != span:
            raise ValueError(f"observation {index} is not an exact source citation")
        source_speaker = item.get("source_speaker_key")
        if coached_speaker and source_speaker != coached_speaker:
            raise ValueError(f"observation {index} evaluates a speaker other than the coached speaker")
        if not coached_speaker and source_speaker is not None:
            raise ValueError(f"observation {index} attributes an unconfirmed speaker")
    return output
