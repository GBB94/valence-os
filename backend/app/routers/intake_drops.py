"""The account drop zone API — ACCOUNT-INTAKE-SPEC.md §15.

Five endpoints, and the shape of the list is the design: **nothing here accepts, rejects, edits,
resolves, or supersedes a proposal.** A drop drafts; `ProposalReview` is the one place a drafted
proposal becomes a decision. Two surfaces that both resolve proposals would eventually disagree
about what a command means, so this router deliberately has no route that could become the second
one — asserted in the test suite over the route table rather than by reading the code.

**Why base64 rather than multipart.** The bytes have to reach the server as bytes, because §6's
ordering (screen → detect → parse from bytes) exists so that Slice 2's `.eml` can decode per MIME
part instead of being flattened to UTF-8 at the door. Multipart would mean adding `python-multipart`
to a codebase that has never had an upload; base64 in the existing JSON body needs no dependency and
no second request shape. The 33% inflation is irrelevant against a 1 MB cap.

The bytes are never persisted (§5). They exist for the life of this request, the decoded *text* is
what lands on `intake_drops.snapshot_text`, and nothing binary reaches disk.
"""
import base64
import sqlite3

from fastapi import APIRouter, Depends, HTTPException, Query

from .. import intake_drop, repo
from ..deps import get_conn
from ..schemas import IntakeDropCreate

router = APIRouter(prefix="/api", tags=["intake-drops"])


@router.get("/intake/limits")
def intake_limits():
    """What may be dropped, the caps, and the refusal copy — from one server-side source.

    A UI that hard-coded the accepted extensions would drift the day a kind is added, and would
    state a limit the server does not enforce.
    """
    return intake_drop.limits()


@router.post("/accounts/{account_id}/intake/drops", status_code=201)
def create_drop(account_id: str, b: IntakeDropCreate,
                conn: sqlite3.Connection = Depends(get_conn)):
    """One dropped item, in the account whose page it was dropped on.

    The account comes from the path and is never read from the text (§8). There is no association
    step and no confidence gate on scope: a human chose this page one second ago.
    """
    if (b.text is None) == (b.content_b64 is None):
        raise HTTPException(422, "send exactly one of `text` or `content_b64`")
    if b.text is not None:
        raw = b.text.encode("utf-8")
    else:
        try:
            raw = base64.b64decode(b.content_b64, validate=True)
        except (ValueError, TypeError):
            raise HTTPException(422, "content_b64 is not valid base64")
    try:
        return intake_drop.process_drop(
            conn, account_id=account_id, raw=raw, filename=b.filename,
            program_id=b.program_id, read_whole_thread=bool(b.read_whole_thread),
            backend=b.backend)
    except ValueError as e:
        raise HTTPException(422, str(e))


@router.get("/accounts/{account_id}/intake/drops")
def list_drops(account_id: str, limit: int = Query(default=20, ge=1, le=100),
               conn: sqlite3.Connection = Depends(get_conn)):
    """Recent receipts, newest first. Archived drops are excluded."""
    repo.get_row(conn, "accounts", account_id)
    return {"drops": intake_drop.list_drops(conn, account_id, limit=limit)}


@router.get("/intake/drops/{drop_id}")
def get_drop(drop_id: str, conn: sqlite3.Connection = Depends(get_conn)):
    """The receipt, its coverage, and the retained source text (§11.1)."""
    return intake_drop.read_drop(conn, drop_id)


@router.delete("/intake/drops/{drop_id}/snapshot")
def delete_snapshot(drop_id: str, conn: sqlite3.Connection = Depends(get_conn)):
    """§5. Nulls the text; keeps the drop, its hash, its run, and every proposal drawn from it."""
    return intake_drop.delete_snapshot(conn, drop_id)


@router.delete("/intake/drops/{drop_id}", status_code=204)
def archive_drop(drop_id: str, conn: sqlite3.Connection = Depends(get_conn)):
    """Soft-delete, per CLAUDE.md. The run and its proposals are untouched — a drop record is a
    receipt, and discarding the receipt does not withdraw what it drafted."""
    repo.archive(conn, "intake_drops", drop_id, object_type="intake_drop")
