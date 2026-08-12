"""The canonical program lifecycle vocabulary — one authority for phase order and labels.

`execution_path.py` (Account Path ranking, phase-gate filtering) and `phase_readiness.py` (phase
advancement and its gates) each carried an identical copy of this tuple. Two copies of a lifecycle
are how a ranking and a transition eventually disagree about what "the next phase" means, so the
graph lives here and both import it. `schemas.Phase` (the pydantic `Literal` on program create) is
asserted against this tuple by an architecture test rather than derived from it, because a
`Literal` must be spelled out to validate.

This module deliberately holds only the shared lifecycle: readiness states, execution urgencies,
band names, and presentation-specific wording stay with their owners, because those are different
vocabularies that happen to mention phases, not the phase graph itself.
"""
from __future__ import annotations

# The canonical program lifecycle, in order. `closed` is terminal, presented after renewal.
# Normal advancement is one step along it (ACCOUNT-PATH-SPEC.md §15.6).
PHASE_ORDER = ("foundation", "launch", "programmatic", "expansion", "renewal", "closed")
PHASE_LABELS = {
    "foundation": "Foundation", "launch": "Launch", "programmatic": "Programmatic",
    "expansion": "Expansion", "renewal": "Renewal", "closed": "Closed",
}


def next_phase(phase: str) -> str | None:
    """The single next step along the graph, or None at the end (or off the graph)."""
    index = PHASE_ORDER.index(phase) if phase in PHASE_ORDER else None
    if index is None or index + 1 >= len(PHASE_ORDER):
        return None
    return PHASE_ORDER[index + 1]
