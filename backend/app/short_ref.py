"""Short reference ids for configuration objects (VISIBILITY-SPEC.md §7.4).

Playbook entries and requirement definitions are the objects two people end up discussing out
loud — "the one about executive touch, version 2, the required one, the one with the thirty-day
offset". A four-character token settles that in one word. There is no new column: the token is
**derived from the id the row already has**, on every read.

Two properties make it safe to say out loud, and both are the reason this lives on the server:

- It is **unique across the whole population**, not merely within whatever list is on screen. A
  reference that collides is worse than none, because two people would each be certain they were
  talking about the same object. Uniqueness is guaranteed by construction: the width grows until
  no two ids in the set collide, and if two ids are genuinely identical they keep their full id.
- It is **stable across surfaces**. The same definition gets the same token in the plan, in the
  readiness detail, and in the definitions listing, because all three derive it from the same
  complete set rather than from the subset each happens to render.

It is a name, never a sort key and never an ordering. Nothing may read meaning into the letters
beyond "this is that row".
"""
import re

MAX_WIDTH = 8

_SEGMENT = re.compile(r"[^A-Za-z0-9]+")


def _segments(value: str) -> list[str]:
    return [part for part in _SEGMENT.split(value or "") if part]


def _candidate(value: str, width: int) -> str:
    segments = _segments(value)
    if not segments:
        return (value or "").upper()
    return "".join(segment[:width] for segment in segments).upper()


def short_refs(ids) -> dict[str, str]:
    """`{id: ref}` for a complete population of ids.

    Widen uniformly rather than per-id: a screen where one row reads `RBC1` and its neighbour
    reads `RRBRCO1` looks like two different kinds of thing. One vocabulary, one width.
    """
    unique = list(dict.fromkeys(str(value) for value in ids if value))
    if not unique:
        return {}
    for width in range(1, MAX_WIDTH + 1):
        refs = {value: _candidate(value, width) for value in unique}
        if len(set(refs.values())) == len(unique):
            return refs
    # Exhausted: two ids agree for the first `MAX_WIDTH` characters of every segment. The full id
    # is the honest fallback — long, unambiguous, and never a token that names two rows.
    collapsed = {value: _candidate(value, MAX_WIDTH) for value in unique}
    seen: dict[str, int] = {}
    for ref in collapsed.values():
        seen[ref] = seen.get(ref, 0) + 1
    return {value: (value.upper() if seen[ref] > 1 else ref)
            for value, ref in collapsed.items()}


def requirement_refs(conn) -> dict[str, str]:
    """Keyed by `(key, version)`, because that is how every other surface names a definition."""
    rows = conn.execute(
        "SELECT id, key, version FROM readiness_requirement_definitions ORDER BY id"
    ).fetchall()
    by_id = short_refs([row["id"] for row in rows])
    return {f"{row['key']}:{row['version']}": by_id.get(row["id"]) for row in rows}


def playbook_entry_refs(conn) -> dict[str, str]:
    rows = conn.execute("SELECT id FROM readiness_playbook_entries ORDER BY id").fetchall()
    return short_refs([row["id"] for row in rows])
