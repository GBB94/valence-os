"""Relationship readiness API (RELATIONSHIP-READINESS-SPEC.md §7). Read-only by construction.

Every route here projects; none writes. There is deliberately no endpoint that stores a pillar
state, because a stored state would become a second source of truth that could disagree with the
records it was derived from.
"""
import sqlite3

from fastapi import APIRouter, Depends, HTTPException, Query

from .. import readiness
from ..deps import get_conn

router = APIRouter(prefix="/api", tags=["readiness"])


@router.get("/accounts/{account_id}/readiness")
def account_readiness(account_id: str, program_id: str | None = Query(default=None),
                      as_of: str | None = Query(default=None),
                      conn: sqlite3.Connection = Depends(get_conn)):
    """§7.1. Omitting `program_id` reports each program separately rather than merging them."""
    return readiness.evaluate(conn, account_id, program_id, as_of)


@router.get("/accounts/{account_id}/readiness/{pillar_key}")
def pillar_detail(account_id: str, pillar_key: str, program_id: str | None = Query(default=None),
                  as_of: str | None = Query(default=None),
                  conn: sqlite3.Connection = Depends(get_conn)):
    """§7.2 — one pillar with every component, its evidence, and the gap that would close it."""
    return readiness.pillar_evidence(conn, account_id, pillar_key, program_id, as_of)


@router.get("/readiness/definitions")
def definitions(conn: sqlite3.Connection = Depends(get_conn)):
    """§7.3 — the live definition set plus the evaluator allowlist, so what the app is measuring
    (and which code it is allowed to run) is inspectable rather than implicit."""
    pillars = []
    for p in conn.execute(
        "SELECT * FROM readiness_pillar_definitions "
        "WHERE retired_at IS NULL AND archived = 0 ORDER BY display_order, key"
    ).fetchall():
        p = dict(p)
        p["requirements"] = [dict(r) for r in conn.execute(
            "SELECT * FROM readiness_requirement_definitions "
            "WHERE pillar_key = ? AND pillar_version = ? AND retired_at IS NULL AND archived = 0 "
            "ORDER BY rowid",
            (p["key"], p["version"]),
        ).fetchall()]
        pillars.append(p)
    return {
        "pillars": pillars,
        "supported_evaluators": readiness.supported_requirement_evaluators(),
    }


@router.post("/readiness/definition-upgrades/preview")
def preview_upgrade(body: dict, conn: sqlite3.Connection = Depends(get_conn)):
    """§7.4 — show which scopes a proposed evaluator version would move, and change nothing.

    A threshold is a policy change. This makes its blast radius visible before it is adopted, and
    refuses a version that is not in the allowlisted registry.
    """
    pillar_key = (body or {}).get("pillar_key")
    version = (body or {}).get("evaluator_version")
    if not pillar_key or version is None:
        raise HTTPException(status_code=422,
                            detail="pillar_key and evaluator_version are required")
    try:
        version = int(version)
    except (TypeError, ValueError):
        raise HTTPException(status_code=422, detail="evaluator_version must be an integer")
    return readiness.preview_definition_upgrade(conn, pillar_key, version)
