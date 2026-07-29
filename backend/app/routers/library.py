import sqlite3

from fastapi import APIRouter, Depends

from .. import repo
from ..deps import get_conn

router = APIRouter(prefix="/api", tags=["library"])

# Tables that cite a source reference, with how to derive the citing record's account + label.
_CITERS = [
    ("interaction", "SELECT id, source_reference_id, account_id, COALESCE(summary,'(interaction)') label FROM interactions WHERE archived=0 AND source_reference_id IS NOT NULL"),
    ("commitment", "SELECT c.id, c.source_reference_id, p.account_id, c.description label FROM commitments c JOIN programs p ON p.id=c.program_id WHERE c.archived=0 AND c.source_reference_id IS NOT NULL"),
    ("decision", "SELECT d.id, d.source_reference_id, p.account_id, d.description label FROM decisions d JOIN programs p ON p.id=d.program_id WHERE d.archived=0 AND d.source_reference_id IS NOT NULL"),
    ("task", "SELECT t.id, t.source_reference_id, p.account_id, t.description label FROM tasks t JOIN programs p ON p.id=t.program_id WHERE t.archived=0 AND t.source_reference_id IS NOT NULL"),
    ("risk", "SELECT r.id, r.source_reference_id, p.account_id, r.description label FROM risks r JOIN programs p ON p.id=r.program_id WHERE r.archived=0 AND r.source_reference_id IS NOT NULL"),
    ("issue", "SELECT i.id, i.source_reference_id, p.account_id, i.description label FROM issues i JOIN programs p ON p.id=i.program_id WHERE i.archived=0 AND i.source_reference_id IS NOT NULL"),
    ("value_story", "SELECT id, source_reference_id, account_id, outcome label FROM value_stories WHERE archived=0 AND source_reference_id IS NOT NULL"),
    ("metric_observation", "SELECT mo.id, mo.source_reference_id, p.account_id, md.name label FROM metric_observations mo JOIN programs p ON p.id=mo.program_id JOIN metric_definitions md ON md.id=mo.definition_id WHERE mo.archived=0 AND mo.source_reference_id IS NOT NULL"),
]


@router.get("/library")
def library(q: str = "", type: str = "", account_id: str = "", conn: sqlite3.Connection = Depends(get_conn)):
    """Files & context library (Section 5O): link-first, searchable list of source references,
    each with the records that cite it. (Tags — the last §5O bit — need a schema field; held.)"""
    names = {a["id"]: a["name"] for a in repo.list_rows(conn, "accounts", where="1=1")}
    # citations per source reference
    cites: dict[str, list] = {}
    for object_type, sql in _CITERS:
        try:
            rows = conn.execute(sql).fetchall()
        except sqlite3.OperationalError:
            continue
        for r in rows:
            cites.setdefault(r["source_reference_id"], []).append({
                "object_type": object_type, "object_id": r["id"],
                "account_id": r["account_id"], "account_name": names.get(r["account_id"]),
                "label": (r["label"] or "")[:60],
            })

    refs = repo.list_rows(conn, "source_references", where="1=1 ORDER BY created_at DESC")
    out = []
    ql = q.strip().lower()
    for s in refs:
        s["citations"] = cites.get(s["id"], [])
        s["citation_count"] = len(s["citations"])
        s["accounts"] = sorted({c["account_name"] for c in s["citations"] if c["account_name"]})
        if type and s["type"] != type:
            continue
        if account_id and account_id not in {c["account_id"] for c in s["citations"]}:
            continue
        if ql and ql not in (s.get("label", "") + " " + (s.get("url") or "") + " " + " ".join(s["accounts"])).lower():
            continue
        out.append(s)
    return {"count": len(out), "sources": out}
