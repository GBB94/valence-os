"""The client-facing joint plan and the promotions that fill it (ACCOUNT-PATH-SPEC.md §16).

Everything a customer could see is projected by `shared_plan`; this module only decides who may
promote what. The split matters: a promotion endpoint that also rendered would eventually grow its
own idea of what is safe, and §16.7 needs preview and export to be the same object rather than two
that agree today.
"""
import sqlite3

from fastapi import APIRouter, Depends, HTTPException, Query

from .. import audit, generators, repo, shared_plan
from ..db import now_utc
from ..deps import get_conn
from ..schemas import MapPromote

router = APIRouter(prefix="/api", tags=["map"])

_TABLE = {"commitment": "commitments", "task": "tasks", "milestone": "milestones",
          "requirement": "readiness_plan_instances"}


def _validate_source(conn, object_type: str, before: dict) -> None:
    """§16.1 — a record cannot become client-visible without an accepted source in scope.

    A requirement is checked differently and deliberately so: its source is the live readiness
    reading and the shared actions attached to it, not a column on the row. `shared_plan` is the
    only thing that knows how to ask that question, and it answers it again at render time — which
    is why a requirement whose support disappears later leaves the plan on its own.
    """
    if object_type == "requirement":
        return
    source_ref = before.get("source_reference_id")
    source_interaction = before.get("source_interaction_id")
    if not source_ref and not source_interaction:
        raise HTTPException(422, "a client-visible plan item needs a source")
    if source_ref:
        repo.get_row(conn, "source_references", source_ref)
    if source_interaction:
        interaction = repo.get_row(conn, "interactions", source_interaction)
        program = repo.get_row(conn, "programs", before["program_id"])
        if interaction["account_id"] != program["account_id"] or \
                (interaction.get("program_id") and interaction["program_id"] != before["program_id"]):
            raise HTTPException(422, "source interaction belongs to a different scope")


@router.post("/map/promote")
def promote(b: MapPromote, conn: sqlite3.Connection = Depends(get_conn)):
    """Promote (or demote) a record onto the client-facing mutual action plan.

    Demotion writes nothing but the flag and an audit row. It never touches the native record and
    never rewrites an artifact that was already generated — a generated document is a frozen body,
    so the §16.8 immutability criterion is a property of where that body lives rather than
    something this endpoint has to remember.
    """
    table = _TABLE[b.object_type]
    before = repo.get_row(conn, table, b.object_id)
    fields: dict = {"client_visible": 1 if b.client_visible else 0, "updated_at": now_utc()}
    if b.client_visible:
        _validate_source(conn, b.object_type, before)
        if b.object_type == "requirement":
            label = (b.client_label or before.get("client_label") or "").strip()
            if not label:
                # The canonical requirement label is written for operators and routinely names an
                # internal condition. §16.3 asks for a label confirmed safe for external eyes, and
                # confirmation means somebody typed one.
                raise HTTPException(422, "a shared requirement needs a client-safe label")
            fields.update({"client_label": label,
                           "client_promoted_on": now_utc(),
                           "client_promoted_by": b.actor_id or "operator"})
            if b.client_owner_person_id is not None:
                owner = repo.get_row(conn, "persons", b.client_owner_person_id)
                if owner["account_id"] not in (None, before["account_id"]):
                    raise HTTPException(422, "client owner belongs to a different account")
                fields["client_owner_person_id"] = b.client_owner_person_id
    elif b.object_type == "requirement":
        # Demotion clears the promoter stamp too. Leaving it behind would read as a live promotion
        # in every later audit of who shared what.
        fields.update({"client_promoted_on": None, "client_promoted_by": None})
    assignments = ", ".join(f"{k}=?" for k in fields)
    with conn:
        conn.execute(f"UPDATE {table} SET {assignments} WHERE id=?",
                     (*fields.values(), b.object_id))
        after = repo.get_row(conn, table, b.object_id)
        audit.record(conn, object_type=b.object_type, object_id=b.object_id, action="update",
                     before=before, after=after)
    return after


@router.get("/map/promotion-preview")
def promotion_preview(object_type: str = Query(...), object_id: str = Query(...),
                      client_label: str | None = Query(default=None),
                      conn: sqlite3.Connection = Depends(get_conn)):
    """§16.4 step 2 — exactly what a customer would see, before anything is promoted."""
    if object_type not in _TABLE:
        raise HTTPException(422, f"cannot promote a {object_type}")
    try:
        return shared_plan.promotion_preview(conn, object_type, object_id, client_label)
    except KeyError as exc:
        raise HTTPException(404, f"no such {object_type}") from exc


@router.get("/accounts/{account_id}/map")
def account_map(account_id: str, conn: sqlite3.Connection = Depends(get_conn)):
    """The operator's view of the shared plan.

    `artifact` is the same object an export renders; `diagnostics` is the operator's half and is
    never merged into it. Returning one dict with a `client_safe` flag on each field would have put
    the boundary in the reader's hands, which is where §16.5 says it must not be.
    """
    return shared_plan.preview(conn, account_id)


@router.post("/accounts/{account_id}/map/document", status_code=201)
def save_map_document(account_id: str, conn: sqlite3.Connection = Depends(get_conn)):
    """Freeze the current shared plan as a stamped draft (§16.6).

    Draft, never sent. The stamp records the template that rendered it and the identities that
    entered it, so a reader months later can tell what this body was built from without having to
    trust that the underlying records still say the same thing.
    """
    account = repo.get_row(conn, "accounts", account_id)
    artifact, manifest = shared_plan.project_for_document(conn, account_id)
    stamp = artifact["stamp"]
    doc = repo.insert(conn, "generated_documents", {
        "account_id": account_id,
        "kind": shared_plan.DOCUMENT_KIND,
        "title": f"Mutual action plan — {account['name']}",
        "body_markdown": artifact["markdown"],
        "status": "draft",
        "generated_at": stamp["generated_at"],
        "data_current_through": stamp["data_current_through"],
        "missing_or_stale_note": "; ".join(stamp["missing_or_stale_sources"]) or None,
        "audience": shared_plan.AUDIENCE,
        "audience_profile": "working",
        **generators.template_stamp(shared_plan.TEMPLATE_KEY),
    }, object_type="generated_document")
    recorded = shared_plan.record_sources(conn, doc["id"], manifest)
    return {"document": doc, "source_count": recorded}
