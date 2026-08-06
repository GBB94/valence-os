"""Account-scoped proposal read model — RR §7.2, §8.1, §0.5.

This module composes. It stores nothing, and that is the whole point of it existing separately.

§0.5 is explicit that extraction proposals must not be copied into `capture_inbox_items`, and the
reason is the same one behind D-141 and D-143: a copy is a second source of truth that can disagree
with the original. So the combined review experience the UI wants is assembled here, at query time,
from two stores that keep their own identities:

  * `extraction_proposals` — machine-drafted, cited, resolved with accept / reject / use-existing /
    supersede.
  * `capture_inbox_items` — hand-typed notes, resolved with convert / dismiss.

They are returned side by side, each carrying its own `kind` and its own status vocabulary. An
`untriaged` note is never restated as `proposed`. Flattening the two vocabularies would read as one
store, and a reader who could not tell them apart could not tell which command applies to which
item — which is exactly the confusion that copying rows would have caused.

Grouping is by **run**, not by interaction (§7.2's "by source"). Two runs over one interaction — a
retranscription, or a rerun after an extractor upgrade — are different sources with different
content hashes, and collapsing them would hide that a proposal came from superseded material.

Counts here are derived on every call. Nothing in this module writes a count back.
"""
from __future__ import annotations

import sqlite3
from datetime import date

from . import proposal_review, proposals as proposals_mod, repo
from .db import now_utc

# When unreviewed proposals stop being a backlog and start being a Today item (§8.1). Two
# independent thresholds, because the two failure modes are different: a small pile left for weeks
# is as much a problem as a large pile that arrived this morning.
REVIEW_DEBT_AGE_DAYS = 7
REVIEW_DEBT_COUNT = 10

_OPEN_PROPOSAL_STATUSES = ("proposed",)


def _days_between(earlier: str | None, later: str) -> int:
    if not earlier:
        return 0
    try:
        return max(0, (date.fromisoformat(later[:10]) - date.fromisoformat(earlier[:10])).days)
    except ValueError:
        return 0


def _run_source(run: dict, interaction: dict | None) -> dict:
    """The provenance block §7.2 calls "exact": what was read, where it came from, and by what.

    `source_version_key` rides along because it, not `external_id`, is what makes two reads of the
    same reference distinguishable — a retranscription of one recording keeps the external id and
    changes the hash.
    """
    return {
        "run_id": run["id"],
        "kind": run.get("source_kind"),
        "provider": run.get("provider"),
        "external_id": run.get("external_id"),
        "content_hash": run.get("content_hash"),
        "source_version_key": run.get("source_version_key"),
        "source_reference_id": run.get("source_reference_id"),
        "interaction_id": run.get("interaction_id"),
        "interaction": interaction,
        "program_id": run.get("program_id"),
        "extractor": {
            "backend": run.get("extractor_backend"),
            "model_version": run.get("model_version"),
            "prompt_version": run.get("prompt_version"),
        },
        "run_status": run.get("status"),
        "created_at": run.get("created_at"),
    }


def _interaction(conn: sqlite3.Connection, interaction_id: str | None) -> dict | None:
    if not interaction_id:
        return None
    row = conn.execute(
        "SELECT id, occurred_on, type, summary FROM interactions WHERE id=?", (interaction_id,)
    ).fetchone()
    return dict(row) if row else None


def _proposal_item(conn, row: sqlite3.Row, run: dict, *, with_matches: bool) -> dict:
    """One proposal in the §6.4 normalized shape, plus the two review aids §7.2 requires.

    `conflict` and `match_candidates` are computed here rather than stored: both are statements
    about the *current* state of a target record, and a stored answer would age into a lie the
    moment somebody edited that record.
    """
    item = proposals_mod.normalized(repo.row_to_dict(row), run)
    item["kind"] = "extraction_proposal"
    item["conflict"] = proposal_review.conflict_preview(conn, row, run)
    item["match_candidates"] = (
        proposal_review.match_candidates(conn, row, run) if with_matches else [])
    return item


def _capture_item(row: sqlite3.Row) -> dict:
    """A manual note in the combined view, keeping its own status words and its own commands.

    Deliberately not shaped like a proposal: no intent, no target type, no citation. A hand-typed
    line has none of those, and inventing them would make an operator's own note look machine-cited.
    """
    return {
        "kind": "capture_item",
        "id": row["id"],
        "interaction_id": row["interaction_id"],
        "text": row["raw_text"],
        "status": row["status"],                     # untriaged | converted | dismissed
        "converted_to": ({"type": row["converted_to_type"], "id": row["converted_to_id"]}
                         if row["converted_to_id"] else None),
        "created_at": row["created_at"],
        "commands": ["convert", "dismiss"],
    }


def _fetch_runs(conn, account_id, program_id, source_interaction_id,
                run_id=None) -> dict[str, dict]:
    sql = ("SELECT * FROM extraction_runs WHERE account_id=? ")
    params: list = [account_id]
    if program_id:
        # A run with no program is account-level work, not work in every program. Narrowing to a
        # program excludes it rather than sweeping it in.
        sql += "AND program_id=? "
        params.append(program_id)
    if source_interaction_id:
        sql += "AND interaction_id=? "
        params.append(source_interaction_id)
    if run_id:
        sql += "AND id=? "
        params.append(run_id)
    sql += "ORDER BY created_at DESC"
    return {r["id"]: repo.row_to_dict(r) for r in conn.execute(sql, params)}


# ACCOUNT-INTAKE-SPEC.md §11.4. Authored here because it is a subtractive statement (D-160): the
# response is complete for the scope it was asked for, and the operator still needs to know the
# account has work this view is not showing. Composing it in the view would let a view soften it.
def _narrowed_note(proposals: int, capture: int) -> str | None:
    if not proposals and not capture:
        return None
    parts = []
    if proposals:
        parts.append(f"{proposals} pending update{'' if proposals == 1 else 's'}")
    if capture:
        parts.append(f"{capture} capture note{'' if capture == 1 else 's'}")
    return (f"This account has {' and '.join(parts)} from other sources. "
            "They are not shown here — this is one source's drafts.")


def proposed_updates(conn: sqlite3.Connection, account_id: str, *, program_id: str | None = None,
                     source_interaction_id: str | None = None, run_id: str | None = None,
                     status: str = "proposed",
                     include_capture: bool = True, with_matches: bool = True) -> dict:
    """§7.2 — every proposal for one account, grouped by source then target type.

    `status` accepts a comma-separated list, or `all`, so review history stays readable (an RR-2
    exit criterion) without a second endpoint.

    `run_id` narrows to one run (ACCOUNT-INTAKE-SPEC.md §11.4), which is what makes a run-scoped
    accept-all a statement about something the operator can see. It is a **filter on this
    composition**, not a second one: same grouping, same per-item conflict and match candidates,
    same command set. What it leaves out is reported in `scope`, because a response the server calls
    complete can still be subtractive and a narrowed queue that looked like an empty account would
    be the worst possible version of this.
    """
    repo.get_row(conn, "accounts", account_id)
    if program_id:
        repo.get_row(conn, "programs", program_id)
    if run_id:
        run = repo.get_row(conn, "extraction_runs", run_id)
        # Scope is checked here rather than trusted from the query string: a run id from another
        # account would otherwise render that account's drafts under this account's heading.
        if run["account_id"] != account_id:
            raise ValueError("that extraction run belongs to a different account")
    statuses = None if status in (None, "", "all") else [s.strip() for s in status.split(",") if s.strip()]

    runs = _fetch_runs(conn, account_id, program_id, source_interaction_id, run_id)
    groups: list[dict] = []
    by_target: dict[str, int] = {}
    by_status: dict[str, int] = {}
    total = 0

    # `rid`, not `run_id`: rebinding the parameter here would leave it holding the last run in the
    # loop, and every scope statement below would then describe a narrowing nobody asked for.
    for rid, run in runs.items():
        sql = "SELECT * FROM extraction_proposals WHERE run_id=? "
        params: list = [rid]
        if statuses:
            sql += f"AND status IN ({','.join('?' * len(statuses))}) "
            params.extend(statuses)
        sql += "ORDER BY created_at, rowid"
        rows = conn.execute(sql, params).fetchall()
        if not rows:
            continue
        interaction = _interaction(conn, run.get("interaction_id"))
        targets: dict[str, list] = {}
        for row in rows:
            item = _proposal_item(conn, row, run, with_matches=with_matches)
            targets.setdefault(row["target_type"] or "unknown", []).append(item)
            by_target[row["target_type"] or "unknown"] = by_target.get(row["target_type"] or "unknown", 0) + 1
            by_status[row["status"]] = by_status.get(row["status"], 0) + 1
            total += 1
        groups.append({
            "source": _run_source(run, interaction),
            "count": len(rows),
            "targets": [{"target_type": t, "count": len(v), "proposals": v}
                        for t, v in sorted(targets.items())],
        })

    capture: list[dict] = []
    # A capture note belongs to an interaction, not to an extraction run, so there is no honest way
    # to include one in a run's slice. It is withheld and counted below rather than quietly dropped.
    if include_capture and not run_id:
        sql = ("SELECT c.* FROM capture_inbox_items c JOIN interactions i ON i.id=c.interaction_id "
               "WHERE i.account_id=? AND c.archived=0 AND c.status='untriaged' ")
        params = [account_id]
        if program_id:
            sql += "AND i.program_id=? "
            params.append(program_id)
        if source_interaction_id:
            sql += "AND c.interaction_id=? "
            params.append(source_interaction_id)
        sql += "ORDER BY c.created_at DESC LIMIT 50"
        capture = [_capture_item(r) for r in conn.execute(sql, params)]

    scope = {"run_id": run_id, "narrowed": bool(run_id),
             "withheld": {"proposals": 0, "manual_capture": 0}, "note": None}
    if run_id:
        elsewhere = conn.execute(
            "SELECT COUNT(*) c FROM extraction_proposals p JOIN extraction_runs r ON r.id=p.run_id "
            "WHERE r.account_id=? AND p.run_id<>? AND p.status='proposed'",
            (account_id, run_id)).fetchone()["c"]
        notes = conn.execute(
            "SELECT COUNT(*) c FROM capture_inbox_items c JOIN interactions i ON i.id=c.interaction_id "
            "WHERE i.account_id=? AND c.archived=0 AND c.status='untriaged'",
            (account_id,)).fetchone()["c"]
        scope["withheld"] = {"proposals": elsewhere, "manual_capture": notes}
        scope["note"] = _narrowed_note(elsewhere, notes)

    return {
        "account_id": account_id,
        "program_id": program_id,
        "source_interaction_id": source_interaction_id,
        "status": status,
        "scope": scope,
        "groups": groups,
        # A composed view, not a merged store: two lists, two status vocabularies, two command sets.
        "manual_capture": capture,
        "counts": {
            "proposals": total,
            "manual_capture": len(capture),
            "by_target_type": by_target,
            "by_status": by_status,
        },
        "resolutions": ["accept", "edit_and_accept", "reject", "use_existing", "supersede"],
    }


def latest_source_preview(conn: sqlite3.Connection, account_id: str, *,
                          program_id: str | None = None, limit: int = 3) -> dict:
    """§8.1/§8.2 `ProposalPreview` — the scoped pending count plus the newest source's first few.

    Overview gets a calm, bounded look at the most recent extraction and a link to the real review
    surface; it never becomes a second review UI. `pending_count` counts the whole scope, not the
    previewed slice, so three cards never imply three items of work.
    """
    runs = _fetch_runs(conn, account_id, program_id, None)
    pending_count = 0
    latest_run = None
    for run_id, run in runs.items():                                # already newest-first
        n = conn.execute(
            "SELECT COUNT(*) c FROM extraction_proposals WHERE run_id=? AND status='proposed'",
            (run_id,)).fetchone()["c"]
        pending_count += n
        if n and latest_run is None:
            latest_run = run

    previews: list[dict] = []
    if latest_run:
        rows = conn.execute(
            "SELECT * FROM extraction_proposals WHERE run_id=? AND status='proposed' "
            "ORDER BY created_at, rowid LIMIT ?", (latest_run["id"], max(0, limit))).fetchall()
        # Matching is skipped here on purpose: a preview card shows what was proposed and what it
        # was drawn from. Duplicate resolution is a decision, and decisions belong on the review
        # surface where the operator can see the candidates.
        previews = [_proposal_item(conn, r, latest_run, with_matches=False) for r in rows]

    return {
        "account_id": account_id,
        "program_id": program_id,
        "pending_count": pending_count,
        "latest_source": (_run_source(latest_run, _interaction(conn, latest_run.get("interaction_id")))
                          if latest_run else None),
        "proposals": previews,
        "truncated": bool(latest_run) and pending_count > len(previews),
        "review_all_href": (f"/api/accounts/{account_id}/proposed-updates"
                            + (f"?program_id={program_id}" if program_id else "")),
    }


def review_debt(conn: sqlite3.Connection, today: str | None = None) -> list[dict]:
    """One review-debt row per account, for the Today queue (§8.1).

    Deduplicated at the account, not the run: an operator reviewing a backlog opens one surface and
    works it, so five aging runs are one piece of work and five Today items would be four lies about
    how much is waiting.

    This is an operational nudge and never evidence. Nothing here feeds readiness, and an unreviewed
    proposal states nothing about the account — only that somebody still has to look.
    """
    today = today or now_utc()[:10]
    out = []
    for r in conn.execute(
        "SELECT r.account_id, a.name aname, COUNT(*) pending, MIN(p.created_at) oldest, "
        "MAX(p.updated_at) updated_at FROM extraction_proposals p "
        "JOIN extraction_runs r ON r.id = p.run_id JOIN accounts a ON a.id = r.account_id "
        "WHERE p.status='proposed' AND r.account_id IS NOT NULL "
        "GROUP BY r.account_id, a.name"
    ):
        age = _days_between(r["oldest"], today)
        breached = []
        if age >= REVIEW_DEBT_AGE_DAYS:
            breached.append("age")
        if r["pending"] >= REVIEW_DEBT_COUNT:
            breached.append("count")
        if not breached:
            continue
        out.append({
            "account_id": r["account_id"], "account_name": r["aname"],
            "pending": r["pending"], "oldest_created_at": r["oldest"], "age_days": age,
            "updated_at": r["updated_at"], "thresholds_breached": breached,
        })
    return out
