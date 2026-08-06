"""Whitespace map, value ledger, and funding intelligence endpoints (Stage 5.5).

Two invariants are enforced here rather than in the UI, because a rule that lives in a form is
not a rule:

  * **Cell facts move only with a reason** (§1.3). There is no PATCH path to the four facts;
    they change through /set-fact, which writes cell_state_history in the same transaction.
    A Declined cell reopens through /reopen, so "the reason changed" is a transition with a
    record rather than an edit that erases the original decline.

  * **The base partition stays MECE** (§1.1). Segment headcounts cannot exceed the account's
    total FTE, and re-cutting the partition is a supersede with a stated reason, not an update.
"""
import sqlite3

from fastapi import APIRouter, Depends, HTTPException

from .. import audit, expansion, repo
from ..db import new_id, now_utc
from ..deps import get_conn
from ..schemas import (
    AccountSettingsPut, AskCalendarCreate, AskStepPatch, AudienceTagCreate, CellCreate,
    CellEvidenceLink, CellPatch, CellReopen, CellSetFact, ContractRevenuePatch, FiscalMapPut,
    FundingPoolCreate, FundingPoolPatch, HeadcountObservationCreate, PartitionCreate,
    PopulationViewCreate, RevenueEventCreate, SegmentCreate, SegmentPatch, UseCaseCreate,
    ValueTargetCreate, ValueTargetEvidenceLink, ValueTargetSupersede,
)

router = APIRouter(prefix="/api", tags=["expansion"])

# Polymorphic links can't carry a foreign key, so the check has to be explicit. "Typed link"
# has to mean the object exists, or the type annotation is decoration and the UI renders
# evidence and work items that were never there.
_LINK_TABLES = {"value_story": "value_stories", "metric_observation": "metric_observations",
                "task": "tasks", "milestone": "milestones", "compliance_item": "compliance_items"}


def _require_program_account(conn: sqlite3.Connection, program_id: str, account_id: str) -> dict:
    program = repo.get_row(conn, "programs", program_id)
    if program["account_id"] != account_id:
        raise HTTPException(422, f"program {program_id} belongs to a different account")
    return program


def _require_person_account(conn: sqlite3.Connection, person_id: str | None, account_id: str) -> None:
    if not person_id:
        return
    person = repo.get_row(conn, "persons", person_id)
    if person.get("account_id") != account_id:
        raise HTTPException(422, f"person {person_id} belongs to a different account")


def _require_source(conn: sqlite3.Connection, source_id: str | None) -> None:
    if source_id:
        repo.get_row(conn, "source_references", source_id)


def _currency(value: str | None, field: str = "currency") -> str | None:
    if value is None:
        return None
    normalized = value.upper()
    if len(normalized) != 3 or not normalized.isalpha():
        raise HTTPException(422, f"{field} must be a three-letter ISO 4217 code")
    return normalized


def _require_linked(conn: sqlite3.Connection, object_type: str, object_id: str,
                    account_id: str | None = None) -> None:
    table = _LINK_TABLES[object_type]
    row = conn.execute(f"SELECT * FROM {table} WHERE id=?", (object_id,)).fetchone()
    if not row:
        raise HTTPException(422, f"no {object_type} with id {object_id}")
    if account_id:
        row = dict(row)
        linked_account = row.get("account_id")
        if linked_account is None and row.get("program_id"):
            program = conn.execute("SELECT account_id FROM programs WHERE id=?",
                                   (row["program_id"],)).fetchone()
            linked_account = program["account_id"] if program else None
        if linked_account is None and object_type == "metric_observation":
            population_table = ("population_segments" if row.get("population_segment_id")
                                else "population_views" if row.get("population_view_id") else None)
            population_id = row.get("population_segment_id") or row.get("population_view_id")
            if population_table:
                population = conn.execute(
                    f"SELECT account_id FROM {population_table} WHERE id=?", (population_id,)).fetchone()
                linked_account = population["account_id"] if population else None
        if linked_account != account_id:
            raise HTTPException(422, f"{object_type} {object_id} belongs to a different account")


def _auto_link_target_observations(conn: sqlite3.Connection, target: dict) -> None:
    """Link only exact stable-identity observations inside the target's agreed window."""
    where = ("archived=0 AND definition_id=? AND IFNULL(population_segment_id,'')=IFNULL(?, '') "
             "AND IFNULL(population_view_id,'')=IFNULL(?, '') AND current_through <= ?")
    params = [target["definition_id"], target.get("segment_id"), target.get("view_id"),
              target["timeframe_end"]]
    if not target.get("segment_id") and not target.get("view_id"):
        programs = [p["id"] for p in repo.list_rows(
            conn, "programs", where="account_id=?", params=(target["account_id"],))]
        if not programs:
            return
        where += f" AND program_id IN ({','.join('?' * len(programs))})"
        params += programs
    if target.get("timeframe_start"):
        where += " AND current_through >= ?"
        params.append(target["timeframe_start"])
    ts = now_utc()
    with conn:
        for obs in conn.execute(f"SELECT id FROM metric_observations WHERE {where}", params):
            conn.execute("INSERT OR IGNORE INTO value_target_evidence "
                         "(id,target_id,object_type,object_id,note,created_at,updated_at) "
                         "VALUES (?,?,'metric_observation',?,'Auto-linked by stable population identity',?,?)",
                         (new_id(), target["id"], obs["id"], ts, ts))


# --- settings -------------------------------------------------------------------------------
@router.put("/accounts/{account_id}/settings")
def put_settings(account_id: str, b: AccountSettingsPut, conn: sqlite3.Connection = Depends(get_conn)):
    repo.get_row(conn, "accounts", account_id)
    ts, values = now_utc(), b.model_dump()
    with conn:
        conn.execute(
            "INSERT INTO account_settings (account_id,min_cohort_size,pull_signal_window_days,"
            "signal_cooldown_days,signal_hysteresis_pct,priority_response_hours,champion_quiet_days,"
            "business_timezone,business_day_start_hour,business_day_end_hour,created_at,updated_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(account_id) DO UPDATE SET "
            "min_cohort_size=excluded.min_cohort_size,pull_signal_window_days=excluded.pull_signal_window_days,"
            "signal_cooldown_days=excluded.signal_cooldown_days,signal_hysteresis_pct=excluded.signal_hysteresis_pct,"
            "priority_response_hours=excluded.priority_response_hours,champion_quiet_days=excluded.champion_quiet_days,"
            "business_timezone=excluded.business_timezone,business_day_start_hour=excluded.business_day_start_hour,"
            "business_day_end_hour=excluded.business_day_end_hour,"
            "updated_at=excluded.updated_at",
            (account_id, values["min_cohort_size"], values["pull_signal_window_days"],
             values["signal_cooldown_days"], values["signal_hysteresis_pct"],
             values["priority_response_hours"], values["champion_quiet_days"], values["business_timezone"],
             values["business_day_start_hour"], values["business_day_end_hour"], ts, ts))
    return {"account_id": account_id, **values}


@router.get("/accounts/{account_id}/settings")
def get_settings(account_id: str, conn: sqlite3.Connection = Depends(get_conn)):
    repo.get_row(conn, "accounts", account_id)
    from .. import stage7
    return stage7.settings(conn, account_id)


# --- portfolio-global vocabularies ------------------------------------------------------------
@router.post("/audience-tags", status_code=201)
def create_audience_tag(b: AudienceTagCreate, conn: sqlite3.Connection = Depends(get_conn)):
    return repo.insert(conn, "audience_tags", b.model_dump(), object_type="audience_tag")


@router.get("/audience-tags")
def list_audience_tags(conn: sqlite3.Connection = Depends(get_conn)):
    return repo.list_rows(conn, "audience_tags", where="1=1 ORDER BY name")


@router.post("/use-cases", status_code=201)
def create_use_case(b: UseCaseCreate, conn: sqlite3.Connection = Depends(get_conn)):
    if b.account_id:
        repo.get_row(conn, "accounts", b.account_id)
    return repo.insert(conn, "use_cases", b.model_dump(), object_type="use_case")


@router.get("/use-cases")
def list_use_cases(account_id: str | None = None, conn: sqlite3.Connection = Depends(get_conn)):
    where = "account_id IS NULL" if not account_id else "(account_id IS NULL OR account_id = ?)"
    params = () if not account_id else (account_id,)
    rows = repo.list_rows(conn, "use_cases", where=f"{where} ORDER BY display_order, name", params=params)
    for r in rows:
        r["portfolio_comparable"] = r["account_id"] is None
    return rows


# --- the base partition (§1.1) -----------------------------------------------------------------
@router.post("/population-partitions", status_code=201)
def create_partition(b: PartitionCreate, conn: sqlite3.Connection = Depends(get_conn)):
    """Creating a partition when one is active supersedes it — a versioned event needing a reason,
    because re-cutting the base re-bases every historical number computed against it."""
    repo.get_row(conn, "accounts", b.account_id)
    current = conn.execute(
        "SELECT * FROM population_partitions WHERE account_id=? AND status='active'",
        (b.account_id,)).fetchone()
    values = b.model_dump()
    if current:
        if not values.get("reason"):
            raise HTTPException(422, "superseding the active partition requires a reason: "
                                     "re-basing changes every number computed against it")
        values["version"] = current["version"] + 1
        values["supersedes_id"] = current["id"]
        with conn:
            conn.execute("UPDATE population_partitions SET status='superseded', updated_at=? WHERE id=?",
                         (now_utc(), current["id"]))
    return repo.insert(conn, "population_partitions", values, object_type="population_partition")


@router.get("/accounts/{account_id}/population-partition")
def get_partition(account_id: str, conn: sqlite3.Connection = Depends(get_conn)):
    row = repo.row_to_dict(conn.execute(
        "SELECT * FROM population_partitions WHERE account_id=? AND status='active'",
        (account_id,)).fetchone())
    if not row:
        raise HTTPException(404, "no active partition for this account")
    row["segments"] = repo.list_rows(conn, "population_segments",
                                     where="partition_id=? ORDER BY is_unallocated, display_order, name",
                                     params=(row["id"],))
    return row


def _check_fte(conn, partition_id: str, extra: int = 0, exclude_segment: str | None = None):
    """§1.1 — the partition cannot claim more people than the company has."""
    p = repo.row_to_dict(conn.execute("SELECT * FROM population_partitions WHERE id=?",
                                      (partition_id,)).fetchone())
    if not p or p["total_fte"] is None:
        return
    q = "SELECT COALESCE(SUM(headcount),0) s FROM population_segments WHERE partition_id=? AND archived=0"
    params = [partition_id]
    if exclude_segment:
        q += " AND id<>?"
        params.append(exclude_segment)
    allocated = conn.execute(q, params).fetchone()["s"]
    if allocated + extra > p["total_fte"]:
        raise HTTPException(422, f"segment headcounts would total {allocated + extra}, exceeding the "
                                 f"account's {p['total_fte']} FTE — the base partition must stay "
                                 f"within the company (§1.1)")


@router.post("/population-segments", status_code=201)
def create_segment(b: SegmentCreate, conn: sqlite3.Connection = Depends(get_conn)):
    p = repo.row_to_dict(conn.execute("SELECT * FROM population_partitions WHERE id=?",
                                      (b.partition_id,)).fetchone())
    if not p:
        raise HTTPException(404, f"partition not found: {b.partition_id}")
    values = b.model_dump()
    _require_source(conn, b.source_reference_id)
    values["is_unallocated"] = 1 if values["is_unallocated"] else 0
    values["account_id"] = p["account_id"]
    # The unallocated remainder is still part of the company. Exempting it from the cap let a
    # 5,000-person remainder sit inside a 1,000-FTE partition, which breaks the reconciliation
    # the remainder exists to make honest.
    _check_fte(conn, b.partition_id, extra=values.get("headcount") or 0)
    return repo.insert(conn, "population_segments", values, object_type="population_segment")


@router.patch("/population-segments/{segment_id}")
def patch_segment(segment_id: str, b: SegmentPatch, conn: sqlite3.Connection = Depends(get_conn)):
    seg = repo.get_row(conn, "population_segments", segment_id)
    if b.headcount is not None:
        _check_fte(conn, seg["partition_id"], extra=b.headcount, exclude_segment=segment_id)
    return repo.patch(conn, "population_segments", segment_id, b.model_dump(),
                      object_type="population_segment")


@router.post("/population-headcount-observations", status_code=201)
def create_headcount_obs(b: HeadcountObservationCreate, conn: sqlite3.Connection = Depends(get_conn)):
    seg = repo.get_row(conn, "population_segments", b.segment_id)
    _require_source(conn, b.source_reference_id)
    values = {**b.model_dump(), "account_id": seg["account_id"]}
    return repo.insert(conn, "population_headcount_observations", values,
                       object_type="population_headcount_observation")


@router.get("/population-segments/{segment_id}/headcount-history")
def headcount_history(segment_id: str, conn: sqlite3.Connection = Depends(get_conn)):
    repo.get_row(conn, "population_segments", segment_id)
    rows = repo.list_rows(conn, "population_headcount_observations",
                          where="segment_id=? ORDER BY period_label", params=(segment_id,))
    return {"segment_id": segment_id, "observations": rows,
            # The land-and-leave detector (§3.2) switches on at two comparable periods.
            "comparable_periods": len(rows),
            "detector_ready": len(rows) >= 2}


# --- composite views (§1.1) ---------------------------------------------------------------------
@router.post("/population-views", status_code=201)
def create_view(b: PopulationViewCreate, conn: sqlite3.Connection = Depends(get_conn)):
    """Refuses to build a view whose estimated headcount is below the account's cohort floor —
    a composite that narrow is identifying by linkage even with no named-usage field (§1.2)."""
    repo.get_row(conn, "accounts", b.account_id)
    active_segment_ids = {s["id"] for s in expansion.active_segments(conn, b.account_id)}
    for segment_id in b.segment_ids:
        if segment_id not in active_segment_ids:
            raise HTTPException(422, f"segment {segment_id} is not in this account's active partition")
    for tag_id in b.tag_ids:
        repo.get_row(conn, "audience_tags", tag_id)
    floor = expansion.min_cohort_size(conn, b.account_id)
    if b.estimated_headcount is not None and b.estimated_headcount < floor:
        raise HTTPException(422, f"estimated headcount {b.estimated_headcount} is below this "
                                 f"account's minimum cohort size of {floor}: a cohort that small "
                                 f"can single out individuals (§1.2)")
    values = b.model_dump()
    segment_ids = values.pop("segment_ids")
    tag_ids = values.pop("tag_ids")
    view = repo.insert(conn, "population_views", values, object_type="population_view")
    with conn:
        for sid in segment_ids:
            conn.execute("INSERT OR IGNORE INTO population_view_segments (view_id, segment_id) VALUES (?,?)",
                         (view["id"], sid))
        for tid in tag_ids:
            conn.execute("INSERT OR IGNORE INTO population_view_tags (view_id, tag_id) VALUES (?,?)",
                         (view["id"], tid))
    view["segment_ids"], view["tag_ids"] = segment_ids, tag_ids
    view["additive"] = False
    view["non_additive_reason"] = "Composite views overlap their constituent segments (§1.1)."
    return view


@router.get("/accounts/{account_id}/population-views")
def list_views(account_id: str, conn: sqlite3.Connection = Depends(get_conn)):
    views = repo.list_rows(conn, "population_views", where="account_id=? ORDER BY name",
                           params=(account_id,))
    for v in views:
        v["segment_ids"] = [r["segment_id"] for r in conn.execute(
            "SELECT segment_id FROM population_view_segments WHERE view_id=?", (v["id"],))]
        v["tag_ids"] = [r["tag_id"] for r in conn.execute(
            "SELECT tag_id FROM population_view_tags WHERE view_id=?", (v["id"],))]
        v["additive"] = False
    return views


# --- whitespace cells (§1.3) ----------------------------------------------------------------------
@router.post("/whitespace-cells", status_code=201)
def create_cell(b: CellCreate, conn: sqlite3.Connection = Depends(get_conn)):
    if bool(b.segment_id) == bool(b.view_id):
        raise HTTPException(422, "a cell's row is exactly one of segment_id or view_id: the "
                                 "rollup rules depend on knowing which (§1.1)")
    repo.get_row(conn, "accounts", b.account_id)
    uc = repo.get_row(conn, "use_cases", b.use_case_id)
    if uc["account_id"] and uc["account_id"] != b.account_id:
        raise HTTPException(422, "that use case belongs to a different account")
    # The row must belong to the account the cell claims. Without this the map happily
    # aggregates another customer's population into this account's rollup — the same
    # look-up-by-id-and-trust-the-caller defect as D-82/D-85.
    row = repo.get_row(conn, "population_segments" if b.segment_id else "population_views",
                       b.segment_id or b.view_id)
    if row["account_id"] != b.account_id:
        raise HTTPException(422, f"that {'segment' if b.segment_id else 'view'} belongs to a "
                                 f"different account")
    _require_person_account(conn, b.sponsor_person_id, b.account_id)
    _require_source(conn, b.source_reference_id)
    if b.client_visible and not b.source_reference_id:
        raise HTTPException(422, "a client-visible whitespace cell requires a source reference")
    return repo.insert(conn, "whitespace_cells", b.model_dump(), object_type="whitespace_cell")


@router.get("/accounts/{account_id}/whitespace")
def get_whitespace(account_id: str, conn: sqlite3.Connection = Depends(get_conn)):
    return expansion.whitespace_map(conn, account_id)


@router.get("/accounts/{account_id}/whitespace/next-seats")
def get_next_seats(account_id: str, limit: int = 10, conn: sqlite3.Connection = Depends(get_conn)):
    repo.get_row(conn, "accounts", account_id)
    return expansion.next_seats(conn, account_id, limit)


@router.get("/whitespace-cells/{cell_id}")
def get_cell(cell_id: str, conn: sqlite3.Connection = Depends(get_conn)):
    cell = repo.get_row(conn, "whitespace_cells", cell_id)
    cell["state"] = expansion.derive_state(cell)
    cell["state_label"], cell["state_move"] = expansion.STATE_LABELS[cell["state"]]
    cell["history"] = [repo.row_to_dict(r) for r in conn.execute(
        "SELECT * FROM cell_state_history WHERE cell_id=? ORDER BY changed_on DESC, created_at DESC",
        (cell_id,))]
    cell["evidence"] = [repo.row_to_dict(r) for r in conn.execute(
        "SELECT * FROM cell_evidence_links WHERE cell_id=?", (cell_id,))]
    return cell


@router.patch("/whitespace-cells/{cell_id}")
def patch_cell(cell_id: str, b: CellPatch, conn: sqlite3.Connection = Depends(get_conn)):
    """Non-state fields only. The four facts move through /set-fact, which requires a reason."""
    existing = repo.get_row(conn, "whitespace_cells", cell_id)
    if "sponsor_person_id" in b.model_fields_set:
        _require_person_account(conn, b.sponsor_person_id, existing["account_id"])
    if "source_reference_id" in b.model_fields_set:
        _require_source(conn, b.source_reference_id)
    visible = b.client_visible if "client_visible" in b.model_fields_set else existing.get("client_visible")
    source = (b.source_reference_id if "source_reference_id" in b.model_fields_set
              else existing.get("source_reference_id"))
    if visible and not source:
        raise HTTPException(422, "a client-visible whitespace cell requires a source reference")
    cell = repo.patch(conn, "whitespace_cells", cell_id, b.model_dump(),
                      object_type="whitespace_cell",
                      allow_null=set(b.model_fields_set) & {"estimated_seats", "sponsor_person_id",
                                                            "next_action", "notes", "source_reference_id"})
    cell["state"] = expansion.derive_state(cell)
    return cell


_FACT_VALUES = {
    "penetration": {"none", "pilot", "paid"},
    "evidence_state": {"none", "anecdotal", "measured"},
    "blocker_state": {"clear", "gated"},
    "pursuit_outcome": {"none", "declined", "won", "deferred"},
}


@router.post("/whitespace-cells/{cell_id}/set-fact")
def set_fact(cell_id: str, b: CellSetFact, conn: sqlite3.Connection = Depends(get_conn)):
    """Change one stored fact, with a reason, appending to cell_state_history (§1.3).

    The composite state is never written — it is recomputed from the facts on every read — so
    this history is the audit trail of what actually changed rather than of a status string.
    """
    cell = repo.get_row(conn, "whitespace_cells", cell_id)
    if b.value not in _FACT_VALUES[b.fact]:
        raise HTTPException(422, f"{b.value!r} is not a valid {b.fact}: "
                                 f"expected one of {sorted(_FACT_VALUES[b.fact])}")
    before_state = expansion.derive_state(cell)
    changes = {b.fact: b.value, "updated_at": now_utc()}

    if b.fact == "blocker_state":
        if b.value == "gated":
            if not b.blocker_lane:
                raise HTTPException(422, "gating a cell requires a lane: a gate no one can act "
                                         "on is not a gate")
            changes["blocker_lane"] = b.blocker_lane
            changes["blocker_owner_person_id"] = b.blocker_owner_person_id
            _require_person_account(conn, b.blocker_owner_person_id, cell["account_id"])
        else:
            changes["blocker_lane"] = None
            changes["blocker_owner_person_id"] = None
    if b.fact == "pursuit_outcome":
        if b.value == "declined":
            changes["declined_reason"] = b.reason
            changes["declined_on"] = b.declined_on or now_utc()[:10]
            # A fresh decline supersedes any earlier reopen.
            changes["reopened_on"] = None
            changes["reopened_reason"] = None
        elif b.value == "deferred":
            changes["deferred_until"] = b.deferred_until
        else:
            changes["declined_reason"] = None
            changes["declined_on"] = None

    sets = ", ".join(f"{k}=?" for k in changes)
    with conn:
        conn.execute(f"UPDATE whitespace_cells SET {sets} WHERE id=?", (*changes.values(), cell_id))
        after = repo.get_row(conn, "whitespace_cells", cell_id)
        after_state = expansion.derive_state(after)
        conn.execute(
            "INSERT INTO cell_state_history (id, cell_id, fact, before_value, after_value, reason, "
            "changed_on, actor, created_at, derived_state_before, derived_state_after) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (new_id(), cell_id, b.fact, cell[b.fact], b.value, b.reason,
             now_utc()[:10], audit.DEFAULT_ACTOR, now_utc(), before_state, after_state))
        audit.record(conn, object_type="whitespace_cell", object_id=cell_id, action="update",
                     before=cell, after=after)
    after["state"] = expansion.derive_state(after)
    after["state_label"], after["state_move"] = expansion.STATE_LABELS[after["state"]]
    after["previous_state"] = before_state
    return after


@router.post("/whitespace-cells/{cell_id}/reopen")
def reopen_cell(cell_id: str, b: CellReopen, conn: sqlite3.Connection = Depends(get_conn)):
    """Reopen a Declined cell because its reason changed (§1.3).

    Clears the pursuit outcome but leaves BOTH the original decline and this reopen in history —
    "we were told no, and here is what changed" is the useful record, not a blank slate.
    """
    cell = repo.get_row(conn, "whitespace_cells", cell_id)
    if cell["pursuit_outcome"] != "declined":
        raise HTTPException(422, "only a declined cell can be reopened")
    when = b.reopened_on or now_utc()[:10]
    before_state = expansion.derive_state(cell)
    with conn:
        conn.execute("UPDATE whitespace_cells SET pursuit_outcome='none', reopened_on=?, "
                     "reopened_reason=?, updated_at=? WHERE id=?", (when, b.reason, now_utc(), cell_id))
        after = repo.get_row(conn, "whitespace_cells", cell_id)
        after_state = expansion.derive_state(after)
        conn.execute(
            "INSERT INTO cell_state_history (id, cell_id, fact, before_value, after_value, reason, "
            "changed_on, actor, created_at, derived_state_before, derived_state_after) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (new_id(), cell_id, "reopened", "declined", "none", b.reason, when,
             audit.DEFAULT_ACTOR, now_utc(), before_state, after_state))
        audit.record(conn, object_type="whitespace_cell", object_id=cell_id, action="update",
                     before=cell, after=after)
    after["state"] = expansion.derive_state(after)
    after["state_label"], after["state_move"] = expansion.STATE_LABELS[after["state"]]
    return after


@router.post("/whitespace-cells/{cell_id}/evidence", status_code=201)
def link_cell_evidence(cell_id: str, b: CellEvidenceLink, conn: sqlite3.Connection = Depends(get_conn)):
    cell = repo.get_row(conn, "whitespace_cells", cell_id)
    _require_linked(conn, b.object_type, b.object_id, cell["account_id"])
    ts = now_utc()
    with conn:
        conn.execute("INSERT OR IGNORE INTO cell_evidence_links "
                     "(id, cell_id, object_type, object_id, note, created_at, updated_at) "
                     "VALUES (?,?,?,?,?,?,?)",
                     (new_id(), cell_id, b.object_type, b.object_id, b.note, ts, ts))
    return {"cell_id": cell_id, **b.model_dump()}


# --- the value ledger (§2) --------------------------------------------------------------------
@router.post("/value-targets", status_code=201)
def create_value_target(b: ValueTargetCreate, conn: sqlite3.Connection = Depends(get_conn)):
    if b.segment_id and b.view_id:
        raise HTTPException(422, "a value target names one population: segment_id or view_id, not both")
    repo.get_row(conn, "accounts", b.account_id)
    repo.get_row(conn, "metric_definitions", b.definition_id)
    if b.segment_id:
        segment = repo.get_row(conn, "population_segments", b.segment_id)
        if segment["account_id"] != b.account_id:
            raise HTTPException(422, "that population segment belongs to a different account")
    if b.view_id:
        view = repo.get_row(conn, "population_views", b.view_id)
        if view["account_id"] != b.account_id:
            raise HTTPException(422, "that population view belongs to a different account")
    _require_person_account(conn, b.accepted_by_person_id, b.account_id)
    _require_source(conn, b.source_reference_id)
    if b.source_interaction_id:
        interaction = repo.get_row(conn, "interactions", b.source_interaction_id)
        if interaction["account_id"] != b.account_id:
            raise HTTPException(422, "source interaction belongs to a different account")
    values = b.model_dump()
    values["client_accepted"] = 1 if values["client_accepted"] else 0
    if values["client_accepted"] and not (values["accepted_by_person_id"] and values["accepted_on"]):
        raise HTTPException(422, "an accepted target needs who accepted it and when: otherwise "
                                 "it is an aspiration, not a bar")
    if values["client_visible"] and not (values["client_accepted"] and
                                           (values["source_reference_id"] or values["source_interaction_id"])):
        raise HTTPException(422, "a client-visible target requires client acceptance and a source")
    target = repo.insert(conn, "value_targets", values, object_type="value_target")
    _auto_link_target_observations(conn, target)
    return target


@router.get("/accounts/{account_id}/ledger")
def get_ledger(account_id: str, conn: sqlite3.Connection = Depends(get_conn)):
    return expansion.ledger(conn, account_id)


@router.get("/accounts/{account_id}/value-gaps")
def get_value_gaps(account_id: str, conn: sqlite3.Connection = Depends(get_conn)):
    repo.get_row(conn, "accounts", account_id)
    return {"account_id": account_id, "gaps": expansion.value_gaps(conn, account_id)}


@router.post("/value-targets/{target_id}/supersede", status_code=201)
def supersede_target(target_id: str, b: ValueTargetSupersede, conn: sqlite3.Connection = Depends(get_conn)):
    """A renegotiated bar creates a new version; the old one stays readable as `superseded`,
    because "we hit the target" only means something against the target agreed at the time."""
    old = repo.get_row(conn, "value_targets", target_id)
    if old["status"] != "active":
        raise HTTPException(422, f"target is {old['status']}, not active")
    # Validate the replacement BEFORE retiring the old bar. The two writes used to be separate
    # transactions, so a replacement that failed its CHECK (accepted without who/when) left the
    # account with a superseded target and nothing superseding it — the bar silently vanished.
    if b.client_accepted and not (b.accepted_by_person_id and b.accepted_on):
        raise HTTPException(422, "an accepted target needs who accepted it and when: otherwise "
                                 "it is an aspiration, not a bar")
    _require_person_account(conn, b.accepted_by_person_id, old["account_id"])
    if b.client_visible and not (b.client_accepted and
                                  (old.get("source_reference_id") or old.get("source_interaction_id"))):
        raise HTTPException(422, "a client-visible target requires client acceptance and a source")
    values = {k: old[k] for k in (
        "account_id", "definition_id", "segment_id", "view_id", "unit", "direction",
        "timeframe_start", "origin", "source_interaction_id", "source_reference_id")}
    values.update({
        "target_value": b.target_value, "timeframe_end": b.timeframe_end,
        "accepted_by_person_id": b.accepted_by_person_id, "accepted_on": b.accepted_on,
        "client_accepted": 1 if b.client_accepted else 0,
        "client_visible": 1 if b.client_visible else 0,
        "version": old["version"] + 1, "supersedes_id": target_id, "notes": b.reason,
    })
    ts = now_utc()
    new_row = {"id": new_id(), "created_at": ts, "updated_at": ts, **values}
    cols = ", ".join(new_row)
    with conn:  # one transaction: either the bar moves or nothing does
        conn.execute(f"INSERT INTO value_targets ({cols}) VALUES ({','.join('?' * len(new_row))})",
                     tuple(new_row.values()))
        conn.execute("UPDATE value_targets SET status='superseded', updated_at=? WHERE id=?",
                     (ts, target_id))
        audit.record(conn, object_type="value_target", object_id=new_row["id"], action="create",
                     before=old, after=new_row)
    target = repo.get_row(conn, "value_targets", new_row["id"])
    _auto_link_target_observations(conn, target)
    return target


@router.post("/value-targets/{target_id}/evidence", status_code=201)
def link_target_evidence(target_id: str, b: ValueTargetEvidenceLink,
                         conn: sqlite3.Connection = Depends(get_conn)):
    target = repo.get_row(conn, "value_targets", target_id)
    _require_linked(conn, b.object_type, b.object_id, target["account_id"])
    ts = now_utc()
    with conn:
        conn.execute("INSERT OR IGNORE INTO value_target_evidence "
                     "(id, target_id, object_type, object_id, note, created_at, updated_at) "
                     "VALUES (?,?,?,?,?,?,?)",
                     (new_id(), target_id, b.object_type, b.object_id, b.note, ts, ts))
    return {"target_id": target_id, **b.model_dump()}


# --- funding intelligence (§4) --------------------------------------------------------------------
@router.post("/funding-pools", status_code=201)
def create_pool(b: FundingPoolCreate, conn: sqlite3.Connection = Depends(get_conn)):
    repo.get_row(conn, "accounts", b.account_id)
    _require_person_account(conn, b.owner_person_id, b.account_id)
    _require_source(conn, b.source_reference_id)
    if b.recovered_spend_id:
        spend = repo.get_row(conn, "recovered_spend", b.recovered_spend_id)
        if spend["account_id"] != b.account_id:
            raise HTTPException(422, "recovered spend belongs to a different account")
    if b.client_visible and not b.source_reference_id:
        raise HTTPException(422, "a client-visible funding pool requires a source reference")
    values = b.model_dump()
    values["currency"] = _currency(values.get("currency"))
    return repo.insert(conn, "funding_pools", values, object_type="funding_pool")


@router.patch("/funding-pools/{pool_id}")
def patch_pool(pool_id: str, b: FundingPoolPatch, conn: sqlite3.Connection = Depends(get_conn)):
    existing = repo.get_row(conn, "funding_pools", pool_id)
    if "owner_person_id" in b.model_fields_set:
        _require_person_account(conn, b.owner_person_id, existing["account_id"])
    if "source_reference_id" in b.model_fields_set:
        _require_source(conn, b.source_reference_id)
    visible = b.client_visible if "client_visible" in b.model_fields_set else existing.get("client_visible")
    source = (b.source_reference_id if "source_reference_id" in b.model_fields_set
              else existing.get("source_reference_id"))
    if visible and not source:
        raise HTTPException(422, "a client-visible funding pool requires a source reference")
    return repo.patch(conn, "funding_pools", pool_id, b.model_dump(), object_type="funding_pool",
                      allow_null=set(b.model_fields_set) & {"owner_person_id", "amount", "notes",
                                                            "source_reference_id"})


@router.put("/accounts/{account_id}/fiscal-map")
def put_fiscal_map(account_id: str, b: FiscalMapPut, conn: sqlite3.Connection = Depends(get_conn)):
    repo.get_row(conn, "accounts", account_id)
    ts = now_utc()
    fields = b.model_dump()
    if b.procurement_lead_contract_id:
        contract = repo.get_row(conn, "contract_versions", b.procurement_lead_contract_id)
        if contract["account_id"] != account_id:
            raise HTTPException(422, "procurement contract belongs to a different account")
    cols = ", ".join(fields)
    placeholders = ", ".join("?" for _ in fields)
    updates = ", ".join(f"{k}=excluded.{k}" for k in fields)
    with conn:
        conn.execute(
            f"INSERT INTO fiscal_maps (account_id, {cols}, created_at, updated_at) "
            f"VALUES (?, {placeholders}, ?, ?) "
            f"ON CONFLICT(account_id) DO UPDATE SET {updates}, updated_at=excluded.updated_at",
            (account_id, *fields.values(), ts, ts))
    return repo.row_to_dict(conn.execute("SELECT * FROM fiscal_maps WHERE account_id=?",
                                         (account_id,)).fetchone())


@router.get("/accounts/{account_id}/funding")
def get_funding(account_id: str, conn: sqlite3.Connection = Depends(get_conn)):
    return expansion.funding_view(conn, account_id)


@router.post("/ask-calendars", status_code=201)
def create_ask_calendar(b: AskCalendarCreate, conn: sqlite3.Connection = Depends(get_conn)):
    """Creates the calendar AND back-schedules the whole dependency chain in one call — the
    point of the artifact is that the dates exist before anyone has to ask for them (§4)."""
    repo.get_row(conn, "accounts", b.account_id)
    # Parse and compute before the first write. A malformed close date must not leave an orphaned
    # calendar behind simply because repo.insert commits independently.
    steps = expansion.back_schedule(conn, b.account_id, b.target_close_date, b.include_works_council)
    if b.opportunity_id:
        opportunity = repo.get_row(conn, "expansion_opportunities", b.opportunity_id)
        if opportunity["account_id"] != b.account_id:
            raise HTTPException(422, "opportunity belongs to a different account")
    ts = now_utc()
    cal_id = new_id()
    cal_values = {
        "id": cal_id, "account_id": b.account_id, "name": b.name,
        "target_close_date": b.target_close_date, "opportunity_id": b.opportunity_id,
        "status": "active", "created_at": ts, "updated_at": ts,
    }
    with conn:
        conn.execute(
            "INSERT INTO ask_calendars (id, account_id, opportunity_id, name, target_close_date, "
            "status, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?)",
            (cal_id, b.account_id, b.opportunity_id, b.name, b.target_close_date,
             "active", ts, ts))
        audit.record(conn, object_type="ask_calendar", object_id=cal_id, action="create",
                     after=cal_values)
        for s in steps:
            conn.execute(
                "INSERT INTO ask_calendar_steps (id, calendar_id, kind, label, due_date, "
                "display_order, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?)",
                (new_id(), cal_id, s["kind"], s["label"], s["due_date"], s["display_order"], ts, ts))
    return expansion.ask_calendar_status(conn, cal_id)


@router.get("/ask-calendars/{calendar_id}")
def get_ask_calendar(calendar_id: str, conn: sqlite3.Connection = Depends(get_conn)):
    return expansion.ask_calendar_status(conn, calendar_id)


@router.patch("/ask-calendar-steps/{step_id}")
def patch_ask_step(step_id: str, b: AskStepPatch, conn: sqlite3.Connection = Depends(get_conn)):
    row = conn.execute("SELECT * FROM ask_calendar_steps WHERE id=?", (step_id,)).fetchone()
    if not row:
        raise HTTPException(404, f"ask step not found: {step_id}")
    changes = {k: v for k, v in b.model_dump().items() if v is not None}
    if not changes:
        return repo.row_to_dict(row)
    if changes.get("linked_id"):
        cal = repo.get_row(conn, "ask_calendars", row["calendar_id"])
        _require_linked(conn, changes.get("linked_type") or row["linked_type"],
                        changes["linked_id"], cal["account_id"])
    changes["updated_at"] = now_utc()
    sets = ", ".join(f"{k}=?" for k in changes)
    with conn:
        conn.execute(f"UPDATE ask_calendar_steps SET {sets} WHERE id=?", (*changes.values(), step_id))
    return repo.row_to_dict(conn.execute("SELECT * FROM ask_calendar_steps WHERE id=?",
                                         (step_id,)).fetchone())


# --- revenue semantics (§10) ----------------------------------------------------------------------
@router.patch("/contracts/{contract_id}/revenue")
def patch_contract_revenue(contract_id: str, b: ContractRevenuePatch,
                           conn: sqlite3.Connection = Depends(get_conn)):
    """Attach units to the canonical price and derive ARR once, here.

    Deriving ARR at each call site is how two screens quietly disagree about revenue, so it is
    computed in one place and stored. The canonical price itself is never rewritten.
    """
    cv = repo.get_row(conn, "contract_versions", contract_id)
    changes = {k: v for k, v in b.model_dump().items() if v is not None}
    if not changes:
        return cv
    if "currency" in changes:
        changes["currency"] = _currency(changes["currency"])
    basis = changes.get("price_basis", cv["price_basis"])
    term = changes.get("term_months", cv["term_months"])
    price = cv["price"]
    arr = None
    if price is not None and basis:
        if basis == "arr":
            arr = price
        elif basis == "monthly":
            arr = price * 12
        elif basis == "tcv" and term:
            arr = price / (term / 12)
        # one_time contributes no recurring revenue, and guessing otherwise would inflate NRR.
    changes["derived_arr"] = arr
    return repo.patch(conn, "contract_versions", contract_id, changes, object_type="contract_version")


@router.post("/revenue-events", status_code=201)
def create_revenue_event(b: RevenueEventCreate, conn: sqlite3.Connection = Depends(get_conn)):
    repo.get_row(conn, "accounts", b.account_id)
    contract = None
    if b.contract_version_id:
        contract = repo.get_row(conn, "contract_versions", b.contract_version_id)
        if contract["account_id"] != b.account_id:
            raise HTTPException(422, "contract belongs to a different account")
    if b.opportunity_id:
        opportunity = repo.get_row(conn, "expansion_opportunities", b.opportunity_id)
        if opportunity["account_id"] != b.account_id:
            raise HTTPException(422, "opportunity belongs to a different account")
    _require_source(conn, b.source_reference_id)
    if b.kind == "expansion" and b.amount is not None and b.amount < 0:
        raise HTTPException(422, "expansion revenue must be positive")
    if b.kind in ("contraction", "churn") and b.amount is not None and b.amount > 0:
        raise HTTPException(422, f"{b.kind} revenue must be negative")
    if b.kind == "renewal_flat" and (b.amount or 0) != 0:
        raise HTTPException(422, "a flat renewal has zero revenue movement")
    values = b.model_dump()
    values["currency"] = _currency(values.get("currency"))
    expected_currency = (contract or {}).get("currency")
    if expected_currency and values["currency"] and values["currency"] != expected_currency:
        raise HTTPException(422, f"event currency {values['currency']} does not match contract currency "
                                 f"{expected_currency}")
    return repo.insert(conn, "revenue_events", values, object_type="revenue_event")


@router.get("/accounts/{account_id}/revenue-movement")
def get_revenue_movement(account_id: str, since: str | None = None,
                         conn: sqlite3.Connection = Depends(get_conn)):
    return expansion.revenue_movement(conn, account_id, since)
