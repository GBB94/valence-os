"""Email thread and quoted-text boundaries — ACCOUNT-PATH-SPEC.md §14.8.

This module exists for one reason, and it is the non-obvious half of §14.8: **repeated thread
history must not produce duplicate proposals.** An email reply carries the whole conversation
below it. Hand a five-message thread to an extractor message by message and it reads the first
message five times, drafts the same commitment five times, and the operator rejects four of them
by hand — every time anybody replies.

Deduplicating the *proposals* afterwards cannot fix that, and it is worth being precise about why,
because the proposal fingerprint looks like it should. Two readings of one sentence in different
messages are genuinely different rows: different source reference, different locator, different
span offsets. They fingerprint apart, correctly. The duplication has to be prevented at the point
where the material is chosen — read only what this message *added* — which is what `split_quoted`
does and nothing downstream can do for it.

So the extraction boundary for an email is its **new text**, and the content hash that gives the
run its §6.6 source-version identity is a hash of that new text, not of the raw body. A reply that
adds one line hashes as one line.

Nothing here reaches a network. Parsing is over fixture `.eml` files (`adapters.py`), and every
rule below is a text rule with no provider behind it.
"""
from __future__ import annotations

import re

# Quote boundaries, most specific first. Each marks the start of quoted history: everything from
# the first match onward is somebody else's earlier message, not what this sender wrote.
#
# These are matched per line rather than over the whole body because a boundary is a line-level
# event; a regex over the joined text would let a `>` inside a sentence open a quote block.
_BOUNDARIES = (
    # Outlook / Exchange
    re.compile(r"^\s*-{2,}\s*Original Message\s*-{2,}\s*$", re.I),
    re.compile(r"^\s*_{5,}\s*$"),
    # Gmail / Apple Mail attribution, on one line or wrapped onto the next.
    re.compile(r"^\s*On .{4,120}\bwrote:\s*$", re.I),
    re.compile(r"^\s*On .{4,200},?\s*$", re.I),          # only when the next line is `… wrote:`
    # Header block that begins a forwarded or quoted message.
    re.compile(r"^\s*From:\s*.+$", re.I),
    re.compile(r"^\s*-{2,}\s*Forwarded message\s*-{2,}\s*$", re.I),
    re.compile(r"^\s*Sent from my \w+", re.I),           # signature, not history, but never new text
)
_WROTE_TAIL = re.compile(r"\bwrote:\s*$", re.I)
_QUOTE_PREFIX = re.compile(r"^\s*>")
# A `From:` line only opens a quoted header block when the message metadata follows it. On its own
# it is ordinary prose ("From: the finance team, we heard...") and must not truncate the message.
_HEADER_FOLLOW = re.compile(r"^\s*(Sent|Date|To|Cc|Subject|Reply-To):", re.I)


def _boundary_index(lines: list[str]) -> int | None:
    """Index of the first line that begins quoted history, or None if the body is all new text."""
    for i, line in enumerate(lines):
        if _QUOTE_PREFIX.match(line):
            return i
        for pattern in _BOUNDARIES:
            if not pattern.match(line):
                continue
            if pattern.pattern.startswith(r"^\s*From:"):
                # Require a second header line within the next three, or this is prose.
                if not any(_HEADER_FOLLOW.match(x) for x in lines[i + 1:i + 4]):
                    continue
            if pattern.pattern.startswith(r"^\s*On ") and not _WROTE_TAIL.search(line):
                # A wrapped attribution: "On Tuesday, 4 August 2026," / "Ada Lovelace wrote:".
                if not any(_WROTE_TAIL.search(x) for x in lines[i + 1:i + 3]):
                    continue
            return i
    return None


def split_quoted(body: str) -> tuple[str, str]:
    """`(new_text, quoted_text)` for one message body.

    `new_text` is what this sender actually added. It is the only thing an extractor may read, and
    it is what the run's content hash covers.

    A body that is *entirely* quoted returns `("", …)`. That is a real case — a bare forward with
    no comment — and it must produce no extraction run at all rather than an empty one, because an
    empty run over a thread everybody has already read is review debt with nothing in it.
    """
    if not body:
        return "", ""
    lines = body.replace("\r\n", "\n").split("\n")
    idx = _boundary_index(lines)
    if idx is None:
        return body.strip(), ""
    return "\n".join(lines[:idx]).strip(), "\n".join(lines[idx:]).strip()


_SUBJECT_PREFIX = re.compile(r"^\s*((re|fw|fwd|aw|sv)\s*(\[\d+\])?\s*:\s*)+", re.I)


def normalize_subject(subject: str | None) -> str:
    """Subject with any stack of `Re:` / `Fwd:` prefixes removed. **Display only.**

    Deliberately not an identity: two unrelated messages titled "Re: Quick question" are not one
    thread, and a subject-keyed thread would merge them and then attribute one account's material
    to another. `thread_key` uses headers only.
    """
    return _SUBJECT_PREFIX.sub("", subject or "").strip()


def _ids(header: str | None) -> list[str]:
    return [m.strip("<>") for m in re.findall(r"<[^>]+>", header or "") if m.strip("<>")]


def thread_key(*, message_id: str | None, in_reply_to: str | None = None,
               references: str | None = None) -> str | None:
    """Stable identity for the conversation this message belongs to.

    The root of `References` is the thread, because it is the one id every message in the thread
    carries. `In-Reply-To` names only the immediate parent, so keying on it would split one
    conversation into a chain of two-message threads. A message with neither header starts its own
    thread and keys on its own id.

    Returns None only when the message has no id either — an unidentifiable message, which the
    caller must not thread rather than guessing it into an existing conversation.
    """
    refs = _ids(references)
    if refs:
        return refs[0]
    parent = _ids(in_reply_to)
    if parent:
        return parent[0]
    return (message_id or "").strip("<>") or None
