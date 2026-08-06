"""Grounding for one proposal — ACCOUNT-INTAKE-SPEC.md §11.2.

The split view's server half: given a proposal, say where its quote came from and hand back enough
of the source to read around it. That is the whole job, and every rule below exists because the
alternative is a citation that lies.

**The quote is the citation; the document is context.** `extraction_proposals.source_span` is the
quoted text itself, written at draft time and never rewritten. It survives the source being deleted,
which is why §5 can null a snapshot without destroying the evidence behind a live proposal. So this
module never *replaces* the span with a located passage — it locates the span and says how well it
matched, and a failure to locate degrades the display without removing the citation.

**Two match strategies and no third.** Exact, then whitespace-normalized — because a mail client
rewraps lines and a paste collapses a double newline, and refusing to see through that would mark
most real quotes as unlocatable. Nothing fuzzier ships. A highlight that lands on text which is
*nearly* the quote is worse than no highlight at all: it presents different words as the ones the
draft cited, and the operator has no way to tell. When neither strategy matches, `found` is false
and the pane says so.

**A run has a snapshot iff a drop points at it.** `extraction_runs` stores no source text and never
has; `intake_drops.snapshot_text` is the only retained source text in the system. There is a
tempting shortcut here — an extraction started from an interaction has `interactions.raw_notes`
sitting right there — and taking it would be wrong twice over: the run's `content_hash` is over the
text handed to the extractor, not over `raw_notes`, so nothing links the two; and `raw_notes` is a
mutable field an operator can edit afterwards. Presenting it as "the source this was drafted from"
would be a fabricated provenance claim. Where there is no snapshot, the pane says there is no
snapshot (§11.2 anticipates exactly this: "every run predating this feature").

**Windowing is subtractive, so the server states it.** Showing 6,000 characters of a 400,000
character transcript is an "I did not show you this" statement, and D-153's rule applies to it the
same way it applies to a refusal: the sentence is authored here, never composed in the view.
"""
from __future__ import annotations

import sqlite3

from . import repo

# Characters either side of the match. A 1 MB snapshot is inside the cap and does not belong in a
# slide-over; a few thousand characters is a screenful of surrounding context either way.
WINDOW = 3000

_DELETED = ("Source text was deleted on {date}. This quote is what the draft was made from.")
_NEVER_CAPTURED = ("No source text was kept for this run. Only dropped and pasted documents keep a "
                   "copy — everything else was read straight from its source. This quote is what "
                   "the draft was made from.")
_NOT_FOUND = ("That quote is not in the retained text as written, so nothing is highlighted below. "
              "The quote itself is unchanged — it is what the draft was made from.")
_TRUNCATED = ("Showing {shown} of {total} characters, around the quote.")
_TRUNCATED_HEAD = ("Showing the first {shown} of {total} characters.")
_MULTIPLE = ("That passage appears {count} times in this document. The first is marked.")


# --- locating ------------------------------------------------------------------------------------

def _normalized(text: str) -> tuple[str, list[int]]:
    """Whitespace-collapsed text, plus the original offset of every character kept.

    The index list is what makes the second strategy safe. Matching on a normalized copy and then
    reporting normalized offsets would highlight the wrong characters of the original by however
    much whitespace was collapsed before the match — a highlight that is off by a line reads as a
    citation of the line beside the one that was quoted.
    """
    out: list[str] = []
    index: list[int] = []
    prev_space = False
    for i, ch in enumerate(text):
        if ch.isspace():
            if prev_space:
                continue
            out.append(" ")
            prev_space = True
        else:
            out.append(ch)
            prev_space = False
        index.append(i)
    return "".join(out), index


def locate(text: str | None, span: str | None) -> dict | None:
    """Where `span` sits in `text`, or None when it cannot be found either way.

    Offsets are into `text` as given. The caller re-bases them if it windows.
    """
    if not text or not span:
        return None

    at = text.find(span)
    if at >= 0:
        return {"start": at, "end": at + len(span), "match": "exact",
                "occurrences": text.count(span)}

    flat, index = _normalized(text)
    needle = " ".join(span.split())
    if not needle:
        return None
    at = flat.find(needle)
    if at < 0:
        return None
    end = at + len(needle)
    return {"start": index[at], "end": index[end - 1] + 1, "match": "whitespace_normalized",
            "occurrences": flat.count(needle)}


# --- the document --------------------------------------------------------------------------------

def _drop_for_run(conn: sqlite3.Connection, run_id: str) -> sqlite3.Row | None:
    """The drop this run came from, archived or not.

    Archived is deliberate. Dismissing a receipt does not withdraw the proposals it drafted — the
    router says so where it archives — so a proposal whose receipt was tidied away must not lose its
    grounding. Hiding the source of a live proposal because its receipt was dismissed would make the
    citation depend on unrelated housekeeping.
    """
    return conn.execute(
        "SELECT id, filename, detected_kind, snapshot_text, snapshot_deleted_at "
        "FROM intake_drops WHERE extraction_run_id=? ORDER BY created_at ASC, id ASC LIMIT 1",
        (run_id,)).fetchone()


def _document(conn: sqlite3.Connection, run_id: str) -> dict:
    drop = _drop_for_run(conn, run_id)
    if drop is None:
        return {"available": False, "state": "never_captured", "note": _NEVER_CAPTURED,
                "text": None, "chars": 0, "drop_id": None, "filename": None, "kind": None,
                "deleted_at": None}
    if drop["snapshot_text"] is None:
        return {"available": False, "state": "deleted",
                "note": _DELETED.format(date=str(drop["snapshot_deleted_at"] or "")[:10]),
                "text": None, "chars": 0, "drop_id": drop["id"], "filename": drop["filename"],
                "kind": drop["detected_kind"], "deleted_at": drop["snapshot_deleted_at"]}
    return {"available": True, "state": "present", "note": None, "text": drop["snapshot_text"],
            "chars": len(drop["snapshot_text"]), "drop_id": drop["id"],
            "filename": drop["filename"], "kind": drop["detected_kind"], "deleted_at": None}


def _window(text: str, at: dict | None, full: bool) -> tuple[str, int, str | None]:
    """The slice to send, its offset in the whole document, and the sentence that says so."""
    total = len(text)
    if full or total <= WINDOW * 2:
        return text, 0, None
    if at is None:
        return text[:WINDOW * 2], 0, _TRUNCATED_HEAD.format(shown=WINDOW * 2, total=total)
    start = max(0, at["start"] - WINDOW)
    end = min(total, at["end"] + WINDOW)
    return text[start:end], start, _TRUNCATED.format(shown=end - start, total=total)


def grounding(conn: sqlite3.Connection, proposal_id: str, *, full: bool = False) -> dict:
    """§11.2's payload: the quote, the retained source around it, and what is missing.

    Fetched when the source pane opens rather than with the proposal list, because a snapshot can be
    the full 1 MB cap and most proposals are decided without opening it.
    """
    prop = repo.get_row(conn, "extraction_proposals", proposal_id)
    run = repo.get_row(conn, "extraction_runs", prop["run_id"])
    span = prop["source_span"]

    doc = _document(conn, run["id"])
    at = locate(doc["text"], span) if doc["available"] else None

    notes: list[str] = []
    if doc["note"]:
        notes.append(doc["note"])
    if doc["available"] and at is None:
        notes.append(_NOT_FOUND)
    if at and at["occurrences"] > 1:
        notes.append(_MULTIPLE.format(count=at["occurrences"]))

    text, offset, truncation = ("", 0, None)
    if doc["available"]:
        text, offset, truncation = _window(doc["text"], at, full)
        if truncation:
            notes.append(truncation)

    location = None
    if at is not None:
        location = {"found": True, "start": at["start"] - offset, "end": at["end"] - offset,
                    "match": at["match"], "occurrences": at["occurrences"]}
    elif doc["available"]:
        location = {"found": False, "start": None, "end": None, "match": None, "occurrences": 0}

    return {
        "proposal_id": prop["id"],
        "run_id": run["id"],
        "account_id": run["account_id"],
        # The citation, always. It is the one field here that does not depend on anything surviving.
        "span": span,
        "locator": prop["source_locator"],
        "document": {
            "state": doc["state"],
            "available": doc["available"],
            "text": text if doc["available"] else None,
            "chars": doc["chars"],
            "window_start": offset,
            "truncated": bool(truncation),
            "drop_id": doc["drop_id"],
            "filename": doc["filename"],
            "kind": doc["kind"],
            "deleted_at": doc["deleted_at"],
        },
        "location": location,
        # Every sentence in here was authored on the server (D-153). The view orders and renders
        # them; it composes none of them, because a view that writes half of an "I did not show you
        # this" statement is a view that can soften one.
        "notes": notes,
    }
