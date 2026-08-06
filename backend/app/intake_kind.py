"""Kind detection and per-kind segmentation for the account drop zone (ACCOUNT-INTAKE-SPEC.md §7).

**Routing is never the model's decision.** Which parser runs decides which text is treated as new
versus quoted, and therefore what gets drafted at all. A model-chosen route is a route the document
can choose for itself, which is the plainest possible instance of the OWASP LLM01 indirect-injection
pattern: a paragraph that says "this is a transcript" would be selecting its own reader. So
detection is regex and structure over the first few dozen lines, it is a pure function, and it is
tested against fixtures.

**Detection never fails.** Anything unrecognized is `notes`, which is the safest route — it treats
the whole body as new text and lets the extractor propose conservatively over material a human
chose to drop.

Nothing in this module touches the database, the network, or the extractor.
"""
from __future__ import annotations

import re

from .email_thread import split_quoted

KINDS = ("notes", "email_paste", "email_file", "transcript")

# --- transcript ------------------------------------------------------------------------------
# WEBVTT header, an SRT cue index followed by a timecode, or a bare `hh:mm:ss` speaker line. Each
# is a *structural* marker: a document that merely mentions a time does not match.
_VTT_HEADER = re.compile(r"^\s*WEBVTT\b", re.I)
_VTT_CUE = re.compile(r"^\s*(?:\d{1,2}:)?\d{1,2}:\d{2}[.,]\d{3}\s*-->\s*(?:\d{1,2}:)?\d{1,2}:\d{2}[.,]\d{3}")
_SRT_INDEX = re.compile(r"^\s*\d+\s*$")
_SPEAKER_TIME = re.compile(r"^\s*(?:\[|\()?\d{1,2}:\d{2}(?::\d{2})?(?:\]|\))?\s+\S")

# --- pasted email ----------------------------------------------------------------------------
# A pasted thread keeps its client's header block even though it has lost its RFC-822 envelope.
# Two header lines are required, not one: "From: the finance team, we heard…" is ordinary prose.
_HEADER_LINE = re.compile(r"^\s*(From|Sent|To|Cc|Subject|Date|Reply-To):\s*\S", re.I)
_ATTRIBUTION = re.compile(r"^\s*On\b.{4,200}\bwrote:\s*$", re.I)
_ORIGINAL = re.compile(r"^\s*-{2,}\s*(Original Message|Forwarded message)\s*-{2,}\s*$", re.I)

_SCAN_LINES = 40


def detect_kind(text: str, filename: str | None = None) -> str:
    """`notes` | `email_paste` | `transcript`. Deterministic, local, and total.

    Extension is a hint, not the answer: a `.txt` holding a pasted thread is a thread, and a `.vtt`
    that somehow holds prose is still read as prose. Structure decides; the extension only breaks
    a tie the text itself does not.
    """
    lines = (text or "").replace("\r\n", "\n").split("\n")
    head = lines[:_SCAN_LINES]
    ext = _extension(filename)

    # `.eml` is the one place the extension *is* the answer rather than a hint, and the reason is
    # that it names a container rather than a content shape: an `.eml` is RFC-822 by definition and
    # its body can be anything, so structure has nothing to decide. In practice `process_drop`
    # routes `.eml` on bytes before anything is decoded (§7.3) and never reaches here — the rule is
    # stated anyway so that a `.eml` arriving down the text path is not silently read as notes,
    # which would hand its raw MIME headers to the extractor as prose.
    if ext == ".eml":
        return "email_file"
    if ext in (".vtt", ".srt") or _looks_transcript(head):
        return "transcript"
    if _looks_email(head):
        return "email_paste"
    return "notes"


def _extension(filename: str | None) -> str:
    name = (filename or "").strip().lower()
    dot = name.rfind(".")
    return name[dot:] if dot > 0 else ""


def _looks_transcript(head: list[str]) -> bool:
    if any(_VTT_HEADER.match(line) for line in head[:3]):
        return True
    if any(_VTT_CUE.match(line) for line in head):
        return True
    # Two or more timestamped speaker turns. One is a meeting note mentioning a time.
    if sum(1 for line in head if _SPEAKER_TIME.match(line)) >= 2:
        return True
    # SRT without a timecode in the first 40 lines is not a thing we need to guess at.
    return False


def _looks_email(head: list[str]) -> bool:
    if any(_ORIGINAL.match(line) or _ATTRIBUTION.match(line) for line in head):
        return True
    return sum(1 for line in head if _HEADER_LINE.match(line)) >= 2


# --- segmentation ------------------------------------------------------------------------------

_FOLDED = re.compile(r"^[ \t]+\S")


def strip_leading_headers(body: str) -> tuple[str, str]:
    """`(header_block, rest)` for a **pasted** thread. Returns `("", body)` when there is no block.

    This exists because `email_thread.split_quoted` is written for one message body that has
    already lost its envelope — a MIME parser hands it the body alone. A pasted thread has not:
    the operator selected the whole message in their mail client, so it begins with the *newest*
    message's own `From: / To: / Date: / Subject:` block.

    Without this, `split_quoted`'s `From:` boundary matches line 0, the entire paste is classified
    as quoted history, `new_text` is empty, and the drop reports "Nothing drafted" — the primary
    use case failing in the most misleading way available, since the receipt would blame the
    document rather than the parse. The header block belongs to the newest message and is
    scaffolding, not history, so it is stripped here and reported under its own coverage reason
    rather than folded into the quoted count.

    Two distinct header keys are required, the same discipline `_looks_email` and
    `email_thread._HEADER_FOLLOW` already use: a document opening "From: the finance team, we
    heard…" is prose and must not lose its first line.
    """
    lines = (body or "").replace("\r\n", "\n").split("\n")
    start = 0
    while start < len(lines) and not lines[start].strip():
        start += 1

    keys, end = set(), start
    while end < len(lines):
        line = lines[end]
        match = _HEADER_LINE.match(line)
        if match:
            keys.add(match.group(1).lower())
            end += 1
            continue
        # A folded continuation ("To: a@x,\n    b@y") only counts once a header has opened.
        if end > start and _FOLDED.match(line):
            end += 1
            continue
        break

    if len(keys) < 2:
        return "", body
    return "\n".join(lines[:end]).strip(), "\n".join(lines[end:])


_CUE_INDEX = re.compile(r"^\s*\d+\s*$")
_CUE_TIME = re.compile(r"-->")
_VTT_NOTE = re.compile(r"^\s*(WEBVTT|NOTE|STYLE|REGION)\b", re.I)


def segment(text: str, kind: str) -> tuple[str, str]:
    """`(new_text, set_aside_text)` for one dropped document.

    `new_text` is the only thing that may reach the extractor. `set_aside_text` is counted and
    reported on the receipt but never read — §14's coverage exists so a subtractive answer says so.

    - `email_paste` uses `email_thread.split_quoted`, unchanged. This is the case where "extract
      everything" is most tempting and most wrong: eight replies means the same commitment drafted
      eight times, and the 30-second capture rule loses every time an operator triages one fact
      twice. A body that is entirely quoted returns `("", …)` and must produce no run at all.
    - `transcript` strips cue numbers, timecodes and VTT block headers, keeping speaker labels and
      what was said. The stripped scaffolding is not "skipped content" in any meaningful sense, so
      it is returned as set-aside rather than silently dropped and the receipt can be accurate
      about the character counts.
    - `notes` is the whole body, which is what makes it the safe fallback.
    """
    body = (text or "").replace("\r\n", "\n")
    if kind == "email_paste":
        return split_quoted(body)
    if kind == "transcript":
        return _strip_cues(body)
    return body.strip(), ""


def _strip_cues(body: str) -> tuple[str, str]:
    kept, dropped = [], []
    for line in body.split("\n"):
        if _CUE_TIME.search(line) or _CUE_INDEX.match(line) or _VTT_NOTE.match(line):
            dropped.append(line)
            continue
        kept.append(line)
    # Collapse the blank runs the cue blocks leave behind, so the extractor sees paragraphs rather
    # than a page of empty lines.
    text = re.sub(r"\n{3,}", "\n\n", "\n".join(kept)).strip()
    return text, "\n".join(dropped).strip()


def read_whole_thread(text: str) -> tuple[str, str]:
    """The operator's explicit *Read the whole thread* override (§7.2).

    It exists because "only the newest message" is right by default and wrong sometimes — a thread
    forwarded to you for the first time is all new to this account. It is an operator act, never a
    heuristic, and it is recorded in coverage so the receipt says which reading was used.
    """
    return (text or "").replace("\r\n", "\n").strip(), ""
