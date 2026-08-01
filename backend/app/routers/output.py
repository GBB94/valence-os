import re
import sqlite3
from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel

from .. import decks, generators, output_gen, repo
from ..db import now_utc
from ..deps import get_conn

router = APIRouter(prefix="/api", tags=["output"])


@router.get("/accounts/{account_id}/history")
def account_history(account_id: str, person_id: str | None = None, program_id: str | None = None,
                    conn: sqlite3.Connection = Depends(get_conn)):
    return output_gen.account_history(conn, account_id, person_id=person_id, program_id=program_id)


@router.get("/team-update")
def team_update(since: str | None = None, conn: sqlite3.Connection = Depends(get_conn)):
    return output_gen.team_update(conn, since=since)


@router.get("/accounts/{account_id}/qbr")
def qbr(account_id: str, conn: sqlite3.Connection = Depends(get_conn)):
    return output_gen.qbr(conn, account_id)


# --- Stage 6: finished artifacts (PHASE-3-SPEC.md Part 5) ------------------------------------
# Generators return the document; nothing is persisted unless the caller asks for a draft, and
# nothing is ever sent. `/documents` is the review queue.

@router.get("/accounts/{account_id}/pre-call-brief")
def pre_call_brief(account_id: str, program_id: str | None = None, person_ids: str | None = None,
                   conn: sqlite3.Connection = Depends(get_conn)):
    ids = [p for p in (person_ids or "").split(",") if p]
    return generators.pre_call_brief(conn, account_id, program_id=program_id, person_ids=ids or None)


@router.get("/accounts/{account_id}/business-case")
def business_case(account_id: str, conn: sqlite3.Connection = Depends(get_conn)):
    return generators.business_case(conn, account_id)


@router.get("/accounts/{account_id}/value-review")
def value_review(account_id: str, conn: sqlite3.Connection = Depends(get_conn)):
    return generators.value_review(conn, account_id)


@router.get("/accounts/{account_id}/champion-kit")
def champion_kit(account_id: str, conn: sqlite3.Connection = Depends(get_conn)):
    return generators.champion_kit(conn, account_id)


@router.get("/accounts/{account_id}/kickoff-deck")
def kickoff_deck(account_id: str, program_id: str | None = None,
                 conn: sqlite3.Connection = Depends(get_conn)):
    return generators.kickoff_deck(conn, account_id, program_id=program_id)


class GenerateReq(BaseModel):
    kind: Literal["pre_call_brief", "business_case", "value_review", "champion_kit", "kickoff_deck"]
    program_id: str | None = None


@router.post("/accounts/{account_id}/documents", status_code=201)
def create_document(account_id: str, b: GenerateReq, conn: sqlite3.Connection = Depends(get_conn)):
    """Generate and save as a DRAFT. Review is a separate, human step."""
    if b.program_id:
        program = repo.get_row(conn, "programs", b.program_id)
        if program["account_id"] != account_id:
            raise HTTPException(422, "program belongs to a different account")
    kwargs = {"program_id": b.program_id} if b.kind in ("pre_call_brief", "kickoff_deck") else {}
    doc = generators.generate(conn, b.kind, account_id, **kwargs)
    return generators.save_draft(conn, doc, program_id=b.program_id)


@router.get("/documents")
def list_documents(account_id: str | None = None, status: str | None = None,
                   conn: sqlite3.Connection = Depends(get_conn)):
    where, params = "1=1", []
    if account_id:
        where += " AND account_id=?"; params.append(account_id)
    if status:
        where += " AND status=?"; params.append(status)
    return repo.list_rows(conn, "generated_documents",
                          where=f"{where} ORDER BY generated_at DESC", params=tuple(params))


@router.get("/documents/{doc_id}")
def get_document(doc_id: str, conn: sqlite3.Connection = Depends(get_conn)):
    return repo.get_row(conn, "generated_documents", doc_id)


class DocReview(BaseModel):
    status: Literal["reviewed", "sent", "discarded"]
    reviewed_by: str | None = None


class DocEdit(BaseModel):
    title: str | None = None
    body_markdown: str | None = None


@router.patch("/documents/{doc_id}")
def edit_document(doc_id: str, b: DocEdit, conn: sqlite3.Connection = Depends(get_conn)):
    """Artifacts are editable while draft; review freezes the exact body that was approved."""
    doc = repo.get_row(conn, "generated_documents", doc_id)
    if doc["status"] != "draft":
        raise HTTPException(409, "only a draft document can be edited")
    changes = {k: v for k, v in b.model_dump().items() if v is not None}
    if not changes:
        return doc
    return repo.patch(conn, "generated_documents", doc_id, changes,
                      object_type="generated_document")


@router.post("/documents/{doc_id}/status")
def set_document_status(doc_id: str, b: DocReview, conn: sqlite3.Connection = Depends(get_conn)):
    """Move a draft along. Nothing in this app transmits anything — 'sent' is the operator
    asserting they sent it, recorded so the artifact's history is honest about that."""
    doc = repo.get_row(conn, "generated_documents", doc_id)
    if b.status in ("reviewed", "sent") and not b.reviewed_by:
        raise HTTPException(422, "reviewing or sending a document records who did it")
    allowed = {
        "draft": {"reviewed", "sent", "discarded"},
        "reviewed": {"sent", "discarded"},
        "sent": set(), "discarded": set(),
    }
    if b.status not in allowed[doc["status"]]:
        raise HTTPException(409, f"cannot move a {doc['status']} document to {b.status}")
    changes = {"status": b.status}
    if b.status in ("reviewed", "sent"):
        changes.update({"reviewed_on": now_utc()[:10], "reviewed_by": b.reviewed_by})
    updated = repo.patch(conn, "generated_documents", doc_id, changes,
                         object_type="generated_document")
    if b.status == "sent" and doc["kind"] == "champion_kit":
        with conn:
            conn.execute("UPDATE generated_document_people SET shared_on=? "
                         "WHERE document_id=? AND shared_on IS NULL", (now_utc()[:10], doc_id))
    return updated


@router.get("/documents/{doc_id}/pptx")
def document_pptx(doc_id: str, conn: sqlite3.Connection = Depends(get_conn)):
    """Render the stored markdown to .pptx. Binaries are never persisted — the markdown is the
    artifact, so a template change re-renders every past deck instead of stranding them."""
    doc = repo.get_row(conn, "generated_documents", doc_id)
    blob = decks.render(doc["body_markdown"], title=doc["title"],
                        subtitle=f"{doc['status'].upper()} · Generated {doc['generated_at']} · "
                                 f"current through {doc['data_current_through'] or 'unknown'}")
    filename = re.sub(r"[^A-Za-z0-9]+", "-", doc["title"]).strip("-").lower() + ".pptx"
    return Response(
        content=blob,
        media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'})


@router.get("/documents/{doc_id}/pdf")
def document_pdf(doc_id: str, conn: sqlite3.Connection = Depends(get_conn)):
    doc = repo.get_row(conn, "generated_documents", doc_id)
    blob = decks.render_pdf(doc["body_markdown"], title=doc["title"],
                            subtitle=f"{doc['status'].upper()} · Generated {doc['generated_at']} · "
                                     f"current through {doc['data_current_through'] or 'unknown'}")
    filename = re.sub(r"[^A-Za-z0-9]+", "-", doc["title"]).strip("-").lower() + ".pdf"
    return Response(content=blob, media_type="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="{filename}"'})


class RoiModelPut(BaseModel):
    seat_price: float | None = None
    seat_price_currency: str | None = None
    seat_price_basis: str | None = None
    retention_uplift_pct: float | None = None
    retention_note: str | None = None
    recovered_spend_id: str | None = None
    assumptions_note: str | None = None
    author: str | None = None
    assessed_on: str | None = None


@router.get("/accounts/{account_id}/roi-model")
def get_roi_model(account_id: str, conn: sqlite3.Connection = Depends(get_conn)):
    repo.get_row(conn, "accounts", account_id)
    row = conn.execute("SELECT * FROM roi_models WHERE account_id=?", (account_id,)).fetchone()
    return dict(row) if row else None


@router.get("/accounts/{account_id}/recovered-spend")
def account_recovered_spend(account_id: str, conn: sqlite3.Connection = Depends(get_conn)):
    repo.get_row(conn, "accounts", account_id)
    return repo.list_rows(conn, "recovered_spend", where="account_id=? ORDER BY label",
                          params=(account_id,))


@router.put("/accounts/{account_id}/roi-model")
def put_roi_model(account_id: str, b: RoiModelPut, conn: sqlite3.Connection = Depends(get_conn)):
    repo.get_row(conn, "accounts", account_id)
    values = b.model_dump()
    if values.get("seat_price") is not None and values["seat_price"] < 0:
        raise HTTPException(422, "seat price cannot be negative")
    if values.get("retention_uplift_pct") is not None and not -100 <= values["retention_uplift_pct"] <= 100:
        raise HTTPException(422, "retention uplift must be between -100% and 100%")
    if values.get("seat_price") is not None:
        currency = (values.get("seat_price_currency") or "").upper()
        if len(currency) != 3 or not currency.isalpha():
            raise HTTPException(422, "seat-price currency must be a three-letter ISO 4217 code")
        if not values.get("seat_price_basis"):
            raise HTTPException(422, "seat price requires a stated basis")
        values["seat_price_currency"] = currency
    if any(values.get(k) is not None for k in
           ("seat_price", "retention_uplift_pct", "recovered_spend_id", "assumptions_note")):
        if not values.get("author") or not values.get("assessed_on"):
            raise HTTPException(422, "ROI assumptions require an author and assessment date")
    if values.get("recovered_spend_id"):
        spend = repo.get_row(conn, "recovered_spend", values["recovered_spend_id"])
        if spend["account_id"] != account_id:
            raise HTTPException(422, "recovered spend belongs to a different account")
        if not spend.get("source_note"):
            raise HTTPException(422, "recovered spend needs a source note before it can enter a client kit")
        if values.get("seat_price_currency") and spend.get("currency") and \
                spend["currency"] != values["seat_price_currency"]:
            raise HTTPException(422, "recovered spend and seat-price currencies do not match")
    ts = now_utc()
    cols = ", ".join(values)
    qs = ", ".join("?" for _ in values)
    updates = ", ".join(f"{k}=excluded.{k}" for k in values)
    with conn:
        conn.execute(f"INSERT INTO roi_models (account_id,{cols},created_at,updated_at) "
                     f"VALUES (?,{qs},?,?) ON CONFLICT(account_id) DO UPDATE SET "
                     f"{updates},updated_at=excluded.updated_at",
                     (account_id, *values.values(), ts, ts))
    return dict(conn.execute("SELECT * FROM roi_models WHERE account_id=?", (account_id,)).fetchone())


class WeeklyScheduleReq(BaseModel):
    run_at: str | None = None
    since: str | None = None
    recurring: bool = True


@router.post("/weekly-team-update/schedule", status_code=201)
def schedule_weekly_team_update(b: WeeklyScheduleReq,
                                conn: sqlite3.Connection = Depends(get_conn)):
    if b.run_at:
        try:
            parsed = datetime.fromisoformat(b.run_at.replace("Z", "+00:00"))
        except ValueError:
            raise HTTPException(422, "run_at must be an ISO-8601 timestamp")
        if parsed.tzinfo is None:
            raise HTTPException(422, "run_at must include a timezone")
    return generators.schedule_weekly_update(conn, run_at=b.run_at, since=b.since,
                                             recurring=b.recurring)


@router.get("/accounts/{account_id}/kickoff-deck/pptx")
def kickoff_pptx(account_id: str, program_id: str | None = None,
                 conn: sqlite3.Connection = Depends(get_conn)):
    """The §1d kickoff skeleton as a real deck, from the same markdown the outline shows."""
    doc = generators.kickoff_deck(conn, account_id, program_id=program_id)
    blob = decks.render(doc["markdown"], title=f"Kickoff — {doc['account_name']}",
                        subtitle=f"Generated {now_utc()} · draft for adaptation")
    return Response(
        content=blob,
        media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
        headers={"Content-Disposition": 'attachment; filename="kickoff-deck.pptx"'})
