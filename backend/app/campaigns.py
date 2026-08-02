"""Adoption campaigns — cohort-level interventions (ADOPTION-CAMPAIGN-SPEC.md, Stage 11.0).

A campaign answers the one question the rest of the system cannot: *what deliberate intervention
are we running to change adoption in this cohort, why should it work, and did the behaviour change
afterward?*

Most of this module is the §5 measurement contract, because that is the only place a campaign can
lie. The product boundaries are enforced by schema (migration 0031); the honesty rules live here:

**The baseline is a series, not a point.** Locking one observation cannot distinguish "the
intervention moved it" from "it was already moving" — the delta renders identically either way.
Readiness freezes the ordered prior observations, which already exist.

**Selection effects are named, not hand-waved.** A campaign converted from a stalled-cohort signal
was selected *because* its latest reading fell. Measuring it again after that trough captures
rebound. Banning the word "caused" does not fix this: the rendered delta *is* the artifact. Every
evaluation therefore carries `cautions` — machine-readable, not a footnote the UI may drop.

**Missing is not zero, stale is not current, and a retracted number is not evidence.** Sub-floor
cohorts suppress, stale observations render unknown, and a baseline archived by an import rollback
invalidates the comparison rather than continuing to show a delta.

Nothing here sends anything.
"""
from __future__ import annotations

import json
import sqlite3
from datetime import date

from fastapi import HTTPException

from . import expansion, repo, stage9
from .db import new_id, now_utc

# §5.1 — how many prior observations to freeze as the baseline trajectory.
BASELINE_LOOKBACK = 4

# Statuses a campaign may hold, and the transitions the service permits. Status is never patched
# generically; each move is a dedicated call that writes append-only history.
TRANSITIONS = {
    "draft": {"ready", "cancelled"},
    "ready": {"active", "draft", "cancelled"},
    "active": {"paused", "completed", "cancelled"},
    "paused": {"active", "completed", "cancelled"},
    "completed": set(),
    "cancelled": set(),
}


def _today() -> str:
    return now_utc()[:10]


def _cohort(campaign: dict) -> tuple[str | None, str | None]:
    return campaign.get("segment_id"), campaign.get("view_id")


# --- §5.1 baseline ------------------------------------------------------------------------------
def _observations(conn, definition_id: str, segment_id: str | None, view_id: str | None) -> list[dict]:
    """Every observation for this metric and population, oldest first, archived included.

    Deliberately unfiltered: the callers below need to see retracted and non-comparable rows in
    order to *say so*. Filtering them out in SQL is what let a withdrawn number read as "no
    change" and a redefined metric read as a delta.
    """
    return [repo.row_to_dict(r) for r in conn.execute(
        "SELECT * FROM metric_observations WHERE definition_id=? "
        "AND IFNULL(population_segment_id,'')=IFNULL(?,'') "
        "AND IFNULL(population_view_id,'')=IFNULL(?,'') ORDER BY current_through",
        (definition_id, segment_id, view_id))]


def _basis(observation: dict) -> dict:
    """The identity a value must share to be arithmetically comparable to another."""
    return {"definition_version": observation.get("definition_version"),
            "unit": observation.get("unit") or None}


def _incomparable_reason(row: dict, basis: dict | None, program_id: str | None) -> str | None:
    """Why this observation may not be differenced against `basis`, or None if it may (§5.1).

    §5.1 requires a match on definition, definition *version*, unit and population, and requires
    a program-scoped observation to belong to the campaign's program. Each of these is a distinct
    way to produce a delta between two numbers that were never the same measurement: a redefined
    metric, a unit change (0.40 fraction against 62.0 percent reads as +61.6), or another
    programme's reading of the same cohort.
    """
    if program_id and row.get("program_id") and row["program_id"] != program_id:
        return "belongs to a different programme"
    if basis is None:
        return None
    if row.get("definition_version") != basis["definition_version"]:
        return (f"uses metric definition version {row.get('definition_version')}, "
                f"not {basis['definition_version']}")
    if (row.get("unit") or None) != basis["unit"]:
        return (f"is recorded in {row.get('unit') or 'no stated unit'}, "
                f"not {basis['unit'] or 'no stated unit'}")
    return None


def _comparable(rows: list[dict], *, basis: dict | None, program_id: str | None,
                live_only: bool = True, through: str | None = None) -> list[dict]:
    return [r for r in rows
            if not (live_only and r.get("archived"))
            and not (through and (r.get("current_through") or "") > through)
            and _incomparable_reason(r, basis, program_id) is None]


def baseline_snapshot(conn: sqlite3.Connection, campaign: dict, value_target: dict) -> dict:
    """The locked point plus the series it sits in, frozen at readiness (§5.1)."""
    program_id = campaign.get("program_id")
    segment_id, view_id = _cohort(campaign)
    rows = _comparable(_observations(conn, value_target["definition_id"], segment_id, view_id),
                       basis=None, program_id=program_id)
    if not rows:
        return {"baseline_observation_id": None, "trajectory": [], "reason": "no observation for this cohort"}
    latest = rows[-1]
    # The trajectory has to be comparable to the point it sits behind, or it cannot answer the
    # question it exists for — "was this cohort already moving?". A prior reading on a different
    # definition version or unit is a different measurement, not an earlier one.
    prior = _comparable(rows[:-1], basis=_basis(latest), program_id=program_id)[-BASELINE_LOOKBACK:]
    return {
        "baseline_observation_id": latest["id"],
        "trajectory": [{"observation_id": r["id"], "value": r["value"],
                        "current_through": r["current_through"]} for r in prior],
        "reason": None,
    }


def _stale(conn, observation: dict, as_of: str | None = None) -> bool:
    """Was this observation stale *at the moment the judgement was made*?

    `as_of` is today for a live campaign — "is this on track" is a question about now. For a
    finished campaign it is the evaluation date, because the evidence was fresh when the outcome
    was recorded and the result is a historical fact. Judging a closed campaign against today
    would turn every completed record into `unknown` as it aged, which is not honesty, just decay.
    """
    d = conn.execute("SELECT stale_after_days FROM metric_definitions WHERE id=?",
                     (observation["definition_id"],)).fetchone()
    if not d or not observation.get("current_through"):
        return True
    try:
        return (date.fromisoformat(as_of or _today())
                - date.fromisoformat(observation["current_through"])).days > d["stale_after_days"]
    except ValueError:
        return True


# --- §5.2 evaluation ------------------------------------------------------------------------------
def evaluate(conn: sqlite3.Connection, campaign: dict, target: dict) -> dict:
    """The honest readout for one campaign target.

    Returns `cautions` as structured records rather than prose, so a caller cannot render the
    delta while quietly dropping the reason it might be an artifact.
    """
    segment_id, view_id = _cohort(campaign)
    account_id = campaign["account_id"]
    cautions: list[dict] = []

    # Privacy floor first — a sub-floor cohort's metric never leaves the service, whatever the
    # evaluation design says (§5.1, and the same rule Stage 5.5 enforces).
    suppression = expansion.cohort_suppression_reason(conn, segment_id, view_id)
    if suppression:
        return {"status": "suppressed", "value": None, "baseline_value": None, "delta": None,
                "cautions": [{"kind": "cohort_suppressed", "detail": suppression}],
                "design": campaign["evaluation_design"]}

    vt = repo.get_row(conn, "value_targets", target["value_target_id"])
    baseline = (repo.row_to_dict(conn.execute(
        "SELECT * FROM metric_observations WHERE id=?", (target["baseline_observation_id"],)).fetchone())
        if target.get("baseline_observation_id") else None)

    # A baseline retracted by an import rollback invalidates the whole comparison (§5.1). It is
    # archived, not deleted, so it is still readable — which is exactly why this must be checked.
    if baseline and baseline.get("archived"):
        return {"status": "invalidated", "value": None, "baseline_value": None, "delta": None,
                "design": campaign["evaluation_design"],
                "cautions": [{"kind": "baseline_retracted",
                              "detail": f"baseline observation {baseline['id']} was archived by an "
                                        f"import rollback; the comparison cannot stand"}]}

    # A finished campaign is measured at its window, not at "whatever landed since". Taking the
    # newest observation forever would let movement months after the campaign ended flow into its
    # delta — silently re-attributing later change to an intervention that had already stopped.
    finished = campaign["status"] in ("completed", "cancelled")
    # The judgement moment is when the operator actually reviewed it — not a planned evaluation
    # date, which may still be in the future and would make recent evidence look "stale" by
    # measuring its age against a date that has not arrived.
    cutoff = (campaign.get("completion_reviewed_on") or campaign.get("evaluation_on")
              or campaign["planned_end_on"])
    window = min(cutoff, _today()) if finished else None

    program_id = campaign.get("program_id")
    # The baseline sets the basis: a post value is only differenceable against the exact
    # measurement the baseline was. With no baseline locked there is nothing to difference, so
    # only the programme rule applies.
    basis = _basis(baseline) if baseline else None
    everything = _observations(conn, vt["definition_id"], segment_id, view_id)

    # §5.1 — the retraction rule runs both ways. If the reading we would show has since been
    # archived by an import rollback, the comparison cannot stand. Filtering archived rows out in
    # SQL instead would silently fall back to an older observation and render the withdrawal as
    # "no change", which is the opposite of what happened.
    with_retracted = _comparable(everything, basis=basis, program_id=program_id,
                                 live_only=False, through=window)
    if with_retracted and with_retracted[-1].get("archived"):
        retracted = with_retracted[-1]
        return {"status": "invalidated", "value": None,
                "baseline_value": baseline["value"] if baseline else None, "delta": None,
                "design": campaign["evaluation_design"],
                "cautions": [{"kind": "post_observation_retracted",
                              "detail": f"the most recent observation {retracted['id']} "
                                        f"(current through {retracted.get('current_through')}) was "
                                        f"archived by an import rollback; the comparison cannot stand"}]}

    rows = _comparable(everything, basis=basis, program_id=program_id, through=window)
    current = rows[-1] if rows else None
    if not current:
        return {"status": "no_evidence", "value": None, "baseline_value": None, "delta": None,
                "design": campaign["evaluation_design"],
                "cautions": [{"kind": "no_observation", "detail": "no observation for this cohort"}]}
    if _stale(conn, current, window):
        return {"status": "unknown", "value": None,
                "baseline_value": baseline["value"] if baseline else None, "delta": None,
                "current_through": current["current_through"],
                "design": campaign["evaluation_design"],
                "cautions": [{"kind": "stale_evidence",
                              "detail": "observation is past its freshness threshold"}]}

    delta = None
    if baseline and baseline["value"] is not None and current["value"] is not None:
        delta = round(current["value"] - baseline["value"], 6)

    # A newer reading exists but is not the same measurement. Excluding it is correct; excluding
    # it silently is not — the operator would see an older value presented as the latest and have
    # no way to know a redefinition, a unit change or another programme's data was the reason.
    live = [r for r in everything
            if not r.get("archived") and not (window and (r.get("current_through") or "") > window)]
    if live and live[-1]["id"] != current["id"]:
        newer = live[-1]
        cautions.append({
            "kind": "incomparable_observation",
            "detail": f"a more recent observation {newer['id']} (current through "
                      f"{newer.get('current_through')}) was excluded because it "
                      f"{_incomparable_reason(newer, basis, program_id)}",
        })

    trajectory = json.loads(target.get("baseline_trajectory_json") or "[]")

    # §5.2 — the campaign was selected because its reading fell, so some rebound is expected with
    # no intervention at all. This is the finding that made v2 of the spec necessary.
    if campaign.get("created_from_signal_episode_id") and campaign["evaluation_design"] == "pre_post":
        cautions.append({
            "kind": "regression_to_the_mean",
            "detail": "selected on a declining reading; some rebound is expected without "
                      "intervention. Prefer a comparator design.",
        })
    if campaign["evaluation_design"] == "pre_post" and not trajectory:
        cautions.append({
            "kind": "no_prior_trajectory",
            "detail": "no prior observations were available to lock, so this delta cannot show "
                      "whether the cohort was already moving",
        })

    # §5.2 seasonality — a window overlapping a recurring moment moves on the calendar.
    seasonal = conn.execute(
        "SELECT name FROM deployment_moments WHERE program_id=? AND archived=0 "
        "AND event_date IS NOT NULL AND event_date BETWEEN ? AND ? LIMIT 1",
        (campaign["program_id"], campaign["planned_start_on"],
         campaign.get("evaluation_on") or campaign["planned_end_on"])).fetchone()
    if seasonal:
        cautions.append({
            "kind": "seasonal_window",
            "detail": f"the evaluation window contains deployment moment '{seasonal['name']}'; "
                      f"only a comparator design controls for calendar-driven movement",
        })

    # §5.2 comparator — the treated delta beside an untreated one over the same window. This is
    # the design that absorbs both regression to the mean and seasonality, which is why the UI
    # proposes it for signal-triggered campaigns.
    comparator = None
    if campaign["evaluation_design"] == "comparator":
        comparator = _comparator_delta(conn, campaign, target, vt)
        if comparator is None:
            cautions.append({"kind": "no_comparator",
                             "detail": "comparator design selected but no comparator population "
                                       "is set, so this reads as a bare pre/post"})
        elif comparator.get("delta") is None:
            cautions.append({"kind": "comparator_no_evidence",
                             "detail": comparator.get("reason") or
                                       "comparator population has no comparable observations"})

    met = (current["value"] >= vt["target_value"] if vt["direction"] == "at_least"
           else current["value"] <= vt["target_value"])
    return {
        "status": "met" if met else "not_met",
        "value": current["value"], "baseline_value": baseline["value"] if baseline else None,
        "delta": delta, "unit": current.get("unit"), "current_through": current["current_through"],
        "target_value": vt["target_value"], "direction": vt["direction"],
        "baseline_trajectory": trajectory,
        "design": campaign["evaluation_design"],
        "comparator": comparator,
        "cautions": cautions,
        # Never a causal claim, whatever the delta says.
        "interpretation_note": "Observed before/after values only. The app does not assert that "
                               "the campaign caused this change.",
    }


def _comparator_delta(conn: sqlite3.Connection, campaign: dict, target: dict,
                      value_target: dict) -> dict | None:
    """The untreated cohort's movement over the same window, or None if none is configured.

    The comparator is held to the same rules as the treated cohort: it must clear the privacy
    floor, and its observations must match the same definition and unit. Schema guarantees it is
    disjoint from the treated population (trigger `trg_campaign_comparator_disjoint_insert`) —
    without that a "control" containing the treated cohort would quietly absorb the effect it
    exists to isolate.
    """
    seg, view = target.get("comparator_segment_id"), target.get("comparator_view_id")
    if not seg and not view:
        return None
    suppression = expansion.cohort_suppression_reason(conn, seg, view)
    if suppression:
        return {"delta": None, "reason": f"comparator {suppression}", "suppressed": True}

    # The window runs from the treated cohort's own baseline date, not from planned_start_on: a
    # baseline is routinely locked slightly before the campaign opens, and anchoring on the start
    # date silently excludes the comparator's matching pre-reading.
    baseline_from = campaign["planned_start_on"]
    if target.get("baseline_observation_id"):
        row = conn.execute("SELECT current_through FROM metric_observations WHERE id=?",
                           (target["baseline_observation_id"],)).fetchone()
        if row and row["current_through"]:
            baseline_from = min(baseline_from, row["current_through"])
    cutoff = campaign.get("evaluation_on") or campaign["planned_end_on"]

    # Held to the treated cohort's basis, not merely to the same definition: a comparator delta
    # measured on a different definition version or unit is not a control, it is a second
    # incompatible number placed beside the first.
    basis = None
    if target.get("baseline_observation_id"):
        b = conn.execute("SELECT * FROM metric_observations WHERE id=?",
                         (target["baseline_observation_id"],)).fetchone()
        if b:
            basis = _basis(repo.row_to_dict(b))
    rows = [r for r in _comparable(_observations(conn, value_target["definition_id"], seg, view),
                                   basis=basis, program_id=campaign.get("program_id"),
                                   through=cutoff)
            if (r.get("current_through") or "") >= baseline_from]
    if len(rows) < 2:
        return {"delta": None, "reason": "comparator needs two comparable observations spanning the window"}
    first, last = rows[0], rows[-1]
    if first["value"] is None or last["value"] is None:
        return {"delta": None, "reason": "comparator observations carry no value"}
    return {
        "delta": round(last["value"] - first["value"], 6),
        "from_value": first["value"], "to_value": last["value"],
        "from_through": first["current_through"], "to_through": last["current_through"],
        "population_kind": "segment" if seg else "view",
        "note": "Association, not causation. Both cohorts moved over the same window.",
    }


# --- §2.3 readiness -------------------------------------------------------------------------------
# (field, message, waivable-by-reason-column)
_NON_WAIVABLE = [
    ("target_behavior", "a cohort-level target behaviour"),
    ("hypothesis", "an intervention hypothesis"),
    ("planned_start_on", "a planned start date"),
    ("planned_end_on", "a planned end date"),
    ("evaluation_on", "an evaluation date after the intervention window"),
    ("internal_owner_person_id", "a canonical internal owner"),
]


def readiness(conn: sqlite3.Connection, campaign_id: str) -> dict:
    """What still blocks `ready`, and which gaps a reason may waive (§2.3).

    The point of the split is that an activity list must not be able to masquerade as a campaign:
    identity, hypothesis, dates, owner, a real intervention, reinforcement and an evaluation date
    are non-waivable. Baseline and sponsor gaps are waivable *with a stated reason*, because
    sometimes you genuinely start before the data lands and saying so is better than pretending.
    """
    c = repo.get_row(conn, "adoption_campaigns", campaign_id)
    blocking, waived = [], []

    for field, label in _NON_WAIVABLE:
        if not c.get(field):
            blocking.append(f"needs {label}")

    targets = repo.list_rows(conn, "adoption_campaign_targets",
                             where="campaign_id=?", params=(campaign_id,))
    primary = next((t for t in targets if t["role"] == "primary"), None)
    if not primary:
        blocking.append("needs a primary value target")

    barriers = repo.list_rows(conn, "adoption_campaign_barriers",
                              where="campaign_id=?", params=(campaign_id,))
    if not barriers:
        blocking.append("needs at least one diagnosed barrier with dated evidence")

    links = repo.list_rows(conn, "adoption_campaign_plan_links",
                           where="campaign_id=?", params=(campaign_id,))
    # A messaging-library reference is guidance, not an intervention (§4.1).
    actionable = [l for l in links if not l["messaging_entry_id"]]
    if not actionable:
        blocking.append("needs at least one actionable linked intervention")
    if not any(l["is_reinforcement"] for l in links):
        blocking.append("needs a reinforcement step after the intervention")

    if not repo.list_rows(conn, "adoption_campaign_checkpoints",
                          where="campaign_id=?", params=(campaign_id,)):
        blocking.append("needs at least one measurement checkpoint")

    # Waivable gaps.
    if primary and not primary.get("baseline_observation_id"):
        (waived if c.get("baseline_gap_reason") else blocking).append(
            "baseline observation is missing" + (" (waived)" if c.get("baseline_gap_reason") else
                                                 " — lock one or record why it is missing"))
    if not c.get("client_sponsor_person_id"):
        (waived if c.get("sponsor_gap_reason") else blocking).append(
            "client sponsor not secured" + (" (waived)" if c.get("sponsor_gap_reason") else
                                            " — name one or record the gap"))

    # §5.1 — a cohort already at its bar is not a lift opportunity. Say which it is.
    already_met = None
    if primary:
        ev = evaluate(conn, c, primary)
        if ev["status"] == "met" and not c.get("already_met_reason"):
            already_met = ("the cohort already meets this target; choose a sustain target, "
                           "supersede it with a sourced higher bar, or record why this campaign "
                           "is about maintaining rather than increasing the behaviour")
            blocking.append(already_met)

    # §11.2 — concurrent campaigns on the same cohort confound both evaluations.
    confounds = _concurrent(conn, c)
    if confounds and not c.get("concurrent_intervention_reason"):
        blocking.append(f"another active campaign targets this cohort and use case "
                        f"({confounds[0]['name']}); record why both are running")

    return {"campaign_id": campaign_id, "ready": not blocking,
            "blocking": blocking, "waived": waived, "confounded_by": confounds}


def _concurrent(conn: sqlite3.Connection, campaign: dict) -> list[dict]:
    segment_id, view_id = _cohort(campaign)
    return [repo.row_to_dict(r) for r in conn.execute(
        "SELECT id,name FROM adoption_campaigns WHERE archived=0 AND id<>? AND account_id=? "
        "AND program_id=? AND use_case_id=? AND status IN ('ready','active') "
        "AND IFNULL(segment_id,'')=IFNULL(?,'') AND IFNULL(view_id,'')=IFNULL(?,'')",
        (campaign["id"], campaign["account_id"], campaign["program_id"],
         campaign["use_case_id"], segment_id, view_id))]


# --- lifecycle --------------------------------------------------------------------------------
def transition(conn: sqlite3.Connection, campaign_id: str, to_status: str, *,
               reason: str, actor: str = "operator", extra: dict | None = None) -> dict:
    """Move a campaign, writing append-only history in the same transaction.

    There is no generic status patch: every move is checked against TRANSITIONS and carries a
    reason, so "why is this paused" is always answerable from the record.
    """
    c = repo.get_row(conn, "adoption_campaigns", campaign_id)
    current = c["status"]
    if to_status not in TRANSITIONS[current]:
        raise HTTPException(422, f"cannot move a {current} campaign to {to_status}")
    if to_status == "ready":
        # Lock first, THEN check. Readiness asks "what is still missing after we captured
        # everything available" — checking before locking reports a missing baseline for a
        # campaign whose observations are sitting right there.
        _lock_baselines(conn, c)
        r = readiness(conn, campaign_id)
        if not r["ready"]:
            raise HTTPException(422, "campaign is not ready: " + "; ".join(r["blocking"]))

    changes = {"status": to_status, "updated_at": now_utc(), **(extra or {})}
    ts = now_utc()
    with conn:
        sets = ", ".join(f"{k}=?" for k in changes)
        conn.execute(f"UPDATE adoption_campaigns SET {sets} WHERE id=?",
                     (*changes.values(), campaign_id))
        conn.execute(
            "INSERT INTO adoption_campaign_state_history "
            "(id,campaign_id,from_status,to_status,reason,actor,changed_on,created_at) "
            "VALUES (?,?,?,?,?,?,?,?)",
            (new_id(), campaign_id, current, to_status, reason, actor, _today(), ts))
    return repo.get_row(conn, "adoption_campaigns", campaign_id)


def _lock_baselines(conn: sqlite3.Connection, campaign: dict) -> None:
    """Freeze the baseline point AND its trajectory at readiness (§5.1)."""
    ts = now_utc()
    with conn:
        for t in repo.list_rows(conn, "adoption_campaign_targets",
                                where="campaign_id=?", params=(campaign["id"],)):
            if t.get("baseline_observation_id"):
                continue
            vt = repo.get_row(conn, "value_targets", t["value_target_id"])
            snap = baseline_snapshot(conn, campaign, vt)
            conn.execute(
                "UPDATE adoption_campaign_targets SET baseline_observation_id=?, "
                "baseline_locked_on=?, baseline_trajectory_json=?, updated_at=? WHERE id=?",
                (snap["baseline_observation_id"], _today() if snap["baseline_observation_id"] else None,
                 json.dumps(snap["trajectory"]), ts, t["id"]))


# --- read model ---------------------------------------------------------------------------------
def detail(conn: sqlite3.Connection, campaign_id: str) -> dict:
    c = repo.get_row(conn, "adoption_campaigns", campaign_id)
    names = {p["id"]: p["name"] for p in repo.list_rows(conn, "persons", where="1=1")}
    segments = {s["id"]: s["name"] for s in repo.list_rows(conn, "population_segments", where="1=1")}
    views = {v["id"]: v["name"] for v in repo.list_rows(conn, "population_views", where="1=1")}
    use_cases = {u["id"]: u["name"] for u in repo.list_rows(conn, "use_cases", where="1=1")}

    targets = []
    for t in repo.list_rows(conn, "adoption_campaign_targets",
                            where="campaign_id=? ORDER BY role", params=(campaign_id,)):
        vt = repo.get_row(conn, "value_targets", t["value_target_id"])
        definition = repo.get_row(conn, "metric_definitions", vt["definition_id"])
        targets.append({**t, "metric": definition["name"], "target_value": vt["target_value"],
                        "direction": vt["direction"],
                        "baseline_trajectory": json.loads(t.get("baseline_trajectory_json") or "[]"),
                        "evaluation": evaluate(conn, c, t)})

    return {
        **c,
        "population": segments.get(c["segment_id"]) or views.get(c["view_id"]),
        "population_kind": "segment" if c["segment_id"] else "view",
        "use_case": use_cases.get(c["use_case_id"]),
        "internal_owner_name": names.get(c["internal_owner_person_id"]),
        "client_sponsor_name": names.get(c["client_sponsor_person_id"]),
        "lead_champion_name": names.get(c["lead_champion_person_id"]),
        "barriers": repo.list_rows(conn, "adoption_campaign_barriers",
                                   where="campaign_id=? ORDER BY is_primary DESC, observed_on",
                                   params=(campaign_id,)),
        "targets": targets,
        "plan": plan(conn, campaign_id),
        "checkpoints": repo.list_rows(conn, "adoption_campaign_checkpoints",
                                      where="campaign_id=? ORDER BY scheduled_on",
                                      params=(campaign_id,)),
        "history": [repo.row_to_dict(r) for r in conn.execute(
            "SELECT * FROM adoption_campaign_state_history WHERE campaign_id=? "
            "ORDER BY changed_on DESC, created_at DESC", (campaign_id,))],
        "readiness": readiness(conn, campaign_id),
        "retrospective": retrospective_for(conn, campaign_id),
        "stamp": {"generated_at": now_utc(), "data_current_through": _today()},
    }


# Linked record -> (table, label column, state column). Completion is DERIVED from the linked
# record (§4.1) so the campaign can never disagree with the Ledger or Plan.
_LINK_SOURCES = {
    "task_id": ("tasks", "description", "status"),
    "commitment_id": ("commitments", "description", "status"),
    "milestone_id": ("milestones", "name", "status"),
    "comms_entry_id": ("comms_entries", "message", "status"),
    "deployment_moment_id": ("deployment_moments", "name", "integration_status"),
    "calendar_event_id": ("calendar_events", "summary", None),
    "generated_document_id": ("generated_documents", "title", "status"),
    "messaging_entry_id": ("messaging_entries", "value_prop", None),
}


def plan(conn: sqlite3.Connection, campaign_id: str) -> list[dict]:
    out = []
    for link in repo.list_rows(conn, "adoption_campaign_plan_links",
                               where="campaign_id=? ORDER BY sequence, created_at",
                               params=(campaign_id,)):
        row = dict(link)
        for column, (table, label_col, state_col) in _LINK_SOURCES.items():
            if not link.get(column):
                continue
            linked = conn.execute(f"SELECT * FROM {table} WHERE id=?", (link[column],)).fetchone()
            row["linked_type"] = table[:-1] if table.endswith("s") else table
            row["linked_id"] = link[column]
            row["linked_label"] = (linked[label_col] if linked else None)
            # Derived, never stored on the campaign.
            row["linked_status"] = (linked[state_col] if linked and state_col else None)
            row["linked_missing"] = linked is None
            break
        out.append(row)
    return out


# --- §7 signal -> draft campaign ------------------------------------------------------------
def propose_from_episode(conn: sqlite3.Connection, episode_id: str, values: dict) -> dict:
    """Convert a signal episode into a DRAFT campaign — never a ready or active one.

    §7.1 is explicit that no signal creates a running campaign. The operator still has to
    diagnose the barrier, name the intervention and lock a baseline; the episode only supplies
    the cohort, the evidence and the reason it was proposed.

    The dedupe rule (§7.2) inherits Stage 7's episode semantics rather than inventing a second
    one: one campaign per episode, and a later recurrence may propose again only after the
    condition cleared and re-armed.
    """
    episode = conn.execute("SELECT * FROM signal_episodes WHERE id=?", (episode_id,)).fetchone()
    if not episode:
        raise HTTPException(404, "signal episode not found")
    episode = repo.row_to_dict(episode)
    if episode.get("adoption_campaign_id"):
        raise HTTPException(409, "this episode already produced a campaign; a new one may be "
                                 "proposed once the condition clears and recurs")
    if episode["status"] == "held":
        raise HTTPException(409, episode.get("held_reason") or "signal is held")
    if episode["status"] not in ("open", "attached"):
        raise HTTPException(409, f"signal episode is already {episode['status']}")

    # The cohort comes from the episode's cell where it has one; otherwise the caller names it.
    cell = repo.get_row(conn, "whitespace_cells", episode["cell_id"]) if episode.get("cell_id") else None
    payload = dict(values)
    if cell:
        payload.setdefault("segment_id", cell.get("segment_id"))
        payload.setdefault("view_id", cell.get("view_id"))
        payload.setdefault("use_case_id", cell["use_case_id"])
        payload.setdefault("cell_id", cell["id"])
    payload["account_id"] = episode["account_id"]
    payload.setdefault("program_id", episode.get("program_id"))
    payload["created_from_signal_episode_id"] = episode_id
    payload.setdefault("name", f"Adoption campaign — {episode['kind'].replace('_', ' ')}")
    # The signal's own explanation is the starting diagnosis, not a finished one.
    payload.setdefault("hypothesis", f"Proposed from a signal: {episode['explanation']} "
                                     f"State the intervention and why it should work.")
    payload.setdefault("target_behavior", "State the cohort-level behaviour to change.")

    ts = now_utc()
    campaign = repo.insert(conn, "adoption_campaigns", payload, object_type="adoption_campaign")
    with conn:
        conn.execute("UPDATE signal_episodes SET status='attached', adoption_campaign_id=?, "
                     "updated_at=? WHERE id=?", (campaign["id"], ts, episode_id))
        conn.execute(
            "INSERT INTO adoption_campaign_state_history (id,campaign_id,from_status,to_status,"
            "reason,actor,changed_on,created_at) VALUES (?,?,NULL,'draft',?,?,?,?)",
            (new_id(), campaign["id"],
             f"Converted from signal episode: {episode['explanation']}",
             "operator", _today(), ts))
    return {"episode_id": episode_id, "campaign": repo.get_row(conn, "adoption_campaigns", campaign["id"])}


def attach_episode(conn: sqlite3.Connection, episode_id: str, campaign_id: str) -> dict:
    """Point an episode at an EXISTING campaign instead of creating a second one."""
    episode = conn.execute("SELECT * FROM signal_episodes WHERE id=?", (episode_id,)).fetchone()
    if not episode:
        raise HTTPException(404, "signal episode not found")
    campaign = repo.get_row(conn, "adoption_campaigns", campaign_id)
    if repo.row_to_dict(episode)["account_id"] != campaign["account_id"]:
        raise HTTPException(422, "the episode and campaign belong to different accounts")
    ts = now_utc()
    with conn:
        conn.execute("UPDATE signal_episodes SET status='attached', adoption_campaign_id=?, "
                     "updated_at=? WHERE id=?", (campaign_id, ts, episode_id))
    return {"episode_id": episode_id, "campaign_id": campaign_id, "status": "attached"}


# --- §5.3 checkpoint adjustment ----------------------------------------------------------------
def supersede_plan_link(conn: sqlite3.Connection, link_id: str, replacement_id: str, *,
                        reason: str, checkpoint_id: str | None = None) -> dict:
    """Replace a future plan item without erasing what was originally tried.

    "We tried X, then swapped it for Y at the mid-cycle checkpoint" is the learning §8 wants to
    query later. Deleting X would throw that away and leave a plan that looks like it always
    said Y. The hypothesis and the locked baseline are never touched here.
    """
    link = repo.get_row(conn, "adoption_campaign_plan_links", link_id)
    replacement = repo.get_row(conn, "adoption_campaign_plan_links", replacement_id)
    if replacement["campaign_id"] != link["campaign_id"]:
        raise HTTPException(422, "a plan item can only be superseded within its own campaign")
    if link.get("superseded_by_link_id"):
        raise HTTPException(409, "that plan item is already superseded")
    ts = now_utc()
    with conn:
        conn.execute(
            "UPDATE adoption_campaign_plan_links SET superseded_by_link_id=?, superseded_on=?, "
            "supersede_reason=?, adjusted_at_checkpoint_id=?, updated_at=? WHERE id=?",
            (replacement_id, _today(), reason, checkpoint_id, ts, link_id))
    return repo.get_row(conn, "adoption_campaign_plan_links", link_id)


# --- §5.3 attention ------------------------------------------------------------------------------
def attention_items(conn: sqlite3.Connection) -> list[dict]:
    """ONE explainable item per campaign whose evidence has gone quiet past its checkpoint.

    Deliberately narrow. Linked tasks and commitments already raise their own Today items when
    they go overdue; a campaign that also raised one per child would double-count the same work
    and train the operator to ignore the queue. The campaign speaks only about the thing no child
    record can: the evidence it is measured by has stopped arriving.
    """
    today = _today()
    out = []
    for c in repo.list_rows(conn, "adoption_campaigns",
                            where="status IN ('active','ready') ORDER BY planned_end_on"):
        due = conn.execute(
            "SELECT * FROM adoption_campaign_checkpoints WHERE campaign_id=? AND archived=0 "
            "AND held_on IS NULL AND scheduled_on <= ? ORDER BY scheduled_on LIMIT 1",
            (c["id"], today)).fetchone()
        if not due:
            continue
        targets = repo.list_rows(conn, "adoption_campaign_targets",
                                 where="campaign_id=? AND role='primary'", params=(c["id"],))
        if not targets:
            continue
        ev = evaluate(conn, c, targets[0])
        if ev["status"] not in ("unknown", "no_evidence", "invalidated"):
            continue
        reason = {"unknown": "its evidence is past the freshness threshold",
                  "no_evidence": "no observation has arrived for this cohort",
                  "invalidated": "its locked baseline was retracted by an import rollback"}[ev["status"]]
        out.append({
            "campaign_id": c["id"], "account_id": c["account_id"], "title": c["name"],
            "checkpoint_id": due["id"], "scheduled_on": due["scheduled_on"],
            "because": f"Checkpoint due {due['scheduled_on']} and {reason}.",
            "next_action": "Review the evidence and record the checkpoint decision.",
            "evaluation_status": ev["status"],
        })
    return out



# --- §8 completion retrospective ------------------------------------------------------------------
# The shape is derived once, here, and frozen (migration 0033). Matching a NEW campaign reads live
# tags; a FINISHED campaign carries the shape it actually ran with, so re-tagging a population later
# cannot silently re-rank history or move a completed campaign into a different match tier.
def _live_shape(conn: sqlite3.Connection, campaign: dict) -> dict:
    """Use case plus audience-tag shape for a campaign, from current data."""
    use_case = repo.get_row(conn, "use_cases", campaign["use_case_id"])
    tags = []
    if campaign.get("view_id"):
        # Only population VIEWS carry audience tags. A segment-targeted campaign has no shape beyond
        # its use case, and falls through to an honest use-case-only match rather than being padded.
        tags = [repo.row_to_dict(r) for r in conn.execute(
            "SELECT t.* FROM audience_tags t JOIN population_view_tags pvt ON pvt.tag_id=t.id "
            "WHERE pvt.view_id=? AND t.archived=0 ORDER BY t.name", (campaign["view_id"],))]
    return {
        "use_case_id": use_case["id"],
        "use_case": use_case["name"],
        # §8: account-specific use cases are excluded from cross-account matching entirely.
        "cross_account_eligible": use_case.get("account_id") is None,
        "population_kind": "segment" if campaign.get("segment_id") else "view",
        "audience_tag_ids": [t["id"] for t in tags],
        "audience_tags": [t["name"] for t in tags],
    }


def record_retrospective(conn: sqlite3.Connection, campaign_id: str, values: dict) -> dict:
    """One learning record per completed campaign, with the shape frozen at write (§8).

    Every plan item needs a verdict, including `skipped`. Omission is how a failed intervention
    actually disappears — nobody deletes it, they just do not write it up — and §9's realization
    counts by intervention kind would then be tallied over whichever ones somebody felt like
    mentioning. §13.10 asks the retrospective to preserve failed interventions; silence about one
    is not preservation.
    """
    campaign = repo.get_row(conn, "adoption_campaigns", campaign_id)
    if campaign["status"] != "completed":
        raise HTTPException(409, "a retrospective belongs to a completed campaign")
    verdicts = values.pop("interventions", []) or []
    for v in verdicts:
        link = repo.get_row(conn, "adoption_campaign_plan_links", v["plan_link_id"])
        if link["campaign_id"] != campaign_id:
            raise HTTPException(422, "that plan item belongs to a different campaign")
    covered = {v["plan_link_id"] for v in verdicts}
    missing = [link["id"] for link in repo.list_rows(
        conn, "adoption_campaign_plan_links", where="campaign_id=? ORDER BY sequence",
        params=(campaign_id,)) if link["id"] not in covered]
    if missing:
        raise HTTPException(422, "every intervention needs a verdict so failures stay on the "
                                 "record — use 'skipped' if it was never run; missing: "
                                 + ", ".join(missing))
    if values.get("messaging_entry_id"):
        repo.get_row(conn, "messaging_entries", values["messaging_entry_id"])
    try:
        row = repo.insert(conn, "adoption_campaign_retrospectives",
                          {**values, "campaign_id": campaign_id,
                           "shape_json": json.dumps(_live_shape(conn, campaign), sort_keys=True)},
                          object_type="campaign_retrospective")
    except sqlite3.IntegrityError as exc:
        raise HTTPException(422, str(exc)) from exc
    ts = now_utc()
    with conn:
        for v in verdicts:
            conn.execute(
                "INSERT INTO adoption_campaign_retrospective_interventions "
                "(id,retrospective_id,plan_link_id,verdict,note,created_at,updated_at) "
                "VALUES (?,?,?,?,?,?,?)",
                (new_id(), row["id"], v["plan_link_id"], v["verdict"], v["note"], ts, ts))
    return get_retrospective(conn, row["id"])


def get_retrospective(conn: sqlite3.Connection, retrospective_id: str) -> dict:
    row = repo.get_row(conn, "adoption_campaign_retrospectives", retrospective_id)
    verdicts = [repo.row_to_dict(r) for r in conn.execute(
        "SELECT ri.*,l.sequence,l.intervention_kind FROM adoption_campaign_retrospective_interventions ri "
        "JOIN adoption_campaign_plan_links l ON l.id=ri.plan_link_id "
        "WHERE ri.retrospective_id=? ORDER BY l.sequence", (retrospective_id,))]
    return {**row, "shape": json.loads(row["shape_json"]), "interventions": verdicts}


def retrospective_for(conn: sqlite3.Connection, campaign_id: str) -> dict | None:
    row = conn.execute("SELECT id FROM adoption_campaign_retrospectives WHERE campaign_id=?",
                       (campaign_id,)).fetchone()
    return get_retrospective(conn, row["id"]) if row else None


# --- §8 nearest completed campaigns ---------------------------------------------------------------
# The ranking discipline is Stage 9's, called rather than restated: `stage9.rank_shape`. Its tier-1
# rule was a live bug (D-94) — `set() == set()` ranked two untagged populations as an exact shape
# match, so "DACH manufacturing" matched "UK retail frontline" at the strongest tier. Exact matching
# requires a NON-EMPTY equal tag set; tagless shapes fall through to an honest use-case-only match.
# That distinction is the whole point here: it separates "we have run this exact shape before" from
# "we have used this feature before", and only one of those justifies copying a motion. A second
# copy of the rule would be a second place for it to regress, which is why this calls the original.
def nearest_campaigns(conn: sqlite3.Connection, campaign_id: str) -> dict:
    campaign = repo.get_row(conn, "adoption_campaigns", campaign_id)
    shape = _live_shape(conn, campaign)
    if not shape["cross_account_eligible"]:
        return {"campaign_id": campaign_id, "cross_account_eligible": False, "shape": shape,
                "matches": [],
                "reason": "Account-specific use cases are excluded from cross-account matching."}
    target_tags = set(shape["audience_tag_ids"])
    ranked = []
    for row in conn.execute(
            "SELECT r.*,c.name campaign_name,c.account_id,c.completion_outcome,c.completion_reviewed_on "
            "FROM adoption_campaign_retrospectives r "
            "JOIN adoption_campaigns c ON c.id=r.campaign_id "
            "WHERE r.campaign_id<>? AND c.archived=0", (campaign_id,)):
        entry = repo.row_to_dict(row)
        past = json.loads(entry["shape_json"])
        if past["use_case_id"] != shape["use_case_id"] or not past.get("cross_account_eligible"):
            continue
        entry_tags = set(past.get("audience_tag_ids") or [])
        rank, reason = stage9.rank_shape(
            target_tags, entry_tags,
            dict(zip(past.get("audience_tag_ids") or [], past.get("audience_tags") or [])))
        # §13.14: a cross-account match exposes the structured retrospective and safe shape metadata
        # only. No source records, people, client wording, or observations cross the boundary.
        ranked.append({
            "retrospective_id": entry["id"], "campaign_id": entry["campaign_id"],
            "campaign_name": entry["campaign_name"], "account_id": entry["account_id"],
            "completion_outcome": entry["completion_outcome"],
            "reviewed_on": entry["reviewed_on"],
            "barrier_actually_present": entry["barrier_actually_present"],
            "what_to_reuse": entry["what_to_reuse"], "what_to_change": entry["what_to_change"],
            "follow_on": entry["follow_on"],
            "shape": {"use_case": past["use_case"], "audience_tags": past.get("audience_tags") or [],
                      "population_kind": past.get("population_kind")},
            "match_rank": rank, "match_reason": reason,
        })
    # Most recent first within a tier, matching stage9.matches(): the newest comparable run is the
    # one worth copying, and ascending order buried it under the oldest.
    ranked.sort(key=lambda e: (e["match_rank"], _desc(e["reviewed_on"]), e["retrospective_id"]))
    return {"campaign_id": campaign_id, "cross_account_eligible": True, "shape": shape,
            "matches": ranked, "reason": None}


# --- §9 portfolio analytics -----------------------------------------------------------------------
def _desc(iso: str | None) -> str:
    """Sort key that puts the most recent ISO date first inside an ascending sort."""
    return "" if not iso else "".join(chr(ord("9") - int(ch)) if ch.isdigit() else ch for ch in iso)


def _median(values: list[float]) -> float | None:
    if not values:
        return None
    s = sorted(values)
    mid = len(s) // 2
    return s[mid] if len(s) % 2 else round((s[mid - 1] + s[mid]) / 2, 2)


def _first_fresh_post(conn: sqlite3.Connection, campaign: dict, activated_on: str) -> str | None:
    """Earliest non-stale observation for the primary target after activation."""
    targets = repo.list_rows(conn, "adoption_campaign_targets",
                             where="campaign_id=? AND role='primary'", params=(campaign["id"],))
    if not targets:
        return None
    vt = repo.get_row(conn, "value_targets", targets[0]["value_target_id"])
    segment_id, view_id = _cohort(campaign)
    for row in _observations(conn, vt["definition_id"], segment_id, view_id):
        if row.get("archived") or not row.get("current_through"):
            continue
        if row["current_through"] < activated_on:
            continue
        # No staleness test here on purpose: an observation is current through its own date, so
        # comparing it against itself would pass unconditionally. "Fresh post observation" means
        # evidence whose window starts after the intervention did — which is this filter.
        return row["current_through"]
    return None


def portfolio_learning(conn: sqlite3.Connection) -> dict:
    """Counts and denominators across the book (§9).

    Deliberately no percentages: five accounts cannot support one without implying precision the
    sample does not have. No ranking of accounts, cohorts, or people, and no adoption-health score —
    the same rules the Stage 9 and Stage 10 analytics already follow.
    """
    campaigns = repo.list_rows(conn, "adoption_campaigns", where="1=1 ORDER BY name")
    by_state: dict[str, int] = {}
    outcomes: dict[str, int] = {}
    no_baseline, no_sponsor, evidence_quiet = [], [], []
    days_to_evidence: list[float] = []
    for c in campaigns:
        by_state[c["status"]] = by_state.get(c["status"], 0) + 1
        if c.get("completion_outcome"):
            outcomes[c["completion_outcome"]] = outcomes.get(c["completion_outcome"], 0) + 1
        primary = repo.list_rows(conn, "adoption_campaign_targets",
                                 where="campaign_id=? AND role='primary'", params=(c["id"],))
        if c["status"] not in ("draft", "cancelled"):
            if not primary or not primary[0].get("baseline_observation_id"):
                no_baseline.append({"campaign_id": c["id"], "name": c["name"],
                                    "reason": c.get("baseline_gap_reason") or "no stated reason"})
            if not c.get("client_sponsor_person_id"):
                no_sponsor.append({"campaign_id": c["id"], "name": c["name"],
                                   "reason": c.get("sponsor_gap_reason") or "no stated reason"})
        activated = conn.execute(
            "SELECT changed_on FROM adoption_campaign_state_history WHERE campaign_id=? "
            "AND to_status='active' ORDER BY changed_on LIMIT 1", (c["id"],)).fetchone()
        if activated and activated["changed_on"]:
            fresh = _first_fresh_post(conn, c, activated["changed_on"])
            if fresh:
                days_to_evidence.append(
                    (date.fromisoformat(fresh) - date.fromisoformat(activated["changed_on"])).days)
    for item in attention_items(conn):
        evidence_quiet.append({"campaign_id": item["campaign_id"], "name": item["title"],
                               "because": item["because"]})

    # Realization by intervention kind and barrier — count over count, never a rate.
    by_intervention: dict[str, dict] = {}
    by_barrier: dict[str, dict] = {}
    for row in conn.execute(
            "SELECT ri.verdict,l.intervention_kind,r.barrier_actually_present,c.completion_outcome "
            "FROM adoption_campaign_retrospective_interventions ri "
            "JOIN adoption_campaign_retrospectives r ON r.id=ri.retrospective_id "
            "JOIN adoption_campaign_plan_links l ON l.id=ri.plan_link_id "
            "JOIN adoption_campaigns c ON c.id=r.campaign_id"):
        d = repo.row_to_dict(row)
        met = d["completion_outcome"] == "target_met"
        for bucket, key in ((by_intervention, d["intervention_kind"] or "unspecified"),
                            (by_barrier, d["barrier_actually_present"])):
            b = bucket.setdefault(key, {"interventions_observed": 0,
                                        "in_campaigns_that_met_target": 0, "helped": 0, "failed": 0})
            b["interventions_observed"] += 1
            b["in_campaigns_that_met_target"] += int(met)
            b["helped"] += int(d["verdict"] == "appeared_to_help")
            b["failed"] += int(d["verdict"] in ("failed", "appeared_not_to_help"))

    # Repeated shapes and where they differ in outcome (§9). Keyed on the frozen shape, so a later
    # re-tag cannot merge or split history.
    shapes: dict[tuple, list[dict]] = {}
    for row in conn.execute(
            "SELECT r.shape_json,r.campaign_id,c.name,c.completion_outcome "
            "FROM adoption_campaign_retrospectives r JOIN adoption_campaigns c ON c.id=r.campaign_id"):
        d = repo.row_to_dict(row)
        s = json.loads(d["shape_json"])
        key = (s["use_case_id"], tuple(sorted(s.get("audience_tag_ids") or [])))
        shapes.setdefault(key, []).append({"campaign_id": d["campaign_id"], "name": d["name"],
                                           "outcome": d["completion_outcome"],
                                           "use_case": s["use_case"],
                                           "audience_tags": s.get("audience_tags") or []})
    repeated = [{"use_case": rows[0]["use_case"], "audience_tags": rows[0]["audience_tags"],
                 "runs": len(rows), "outcomes": sorted({r["outcome"] for r in rows if r["outcome"]}),
                 "diverged": len({r["outcome"] for r in rows if r["outcome"]}) > 1,
                 "campaigns": rows}
                for rows in shapes.values() if len(rows) > 1]

    return {
        "by_state": by_state, "outcomes": outcomes,
        "time_to_first_evidence": {
            "median_days": _median(days_to_evidence), "n": len(days_to_evidence),
            "insufficient_data": not days_to_evidence},
        "by_intervention_kind": [{"intervention_kind": k, **v} for k, v in sorted(by_intervention.items())],
        "by_barrier_present": [{"barrier": k, **v} for k, v in sorted(by_barrier.items())],
        "started_without_baseline": no_baseline, "started_without_sponsor": no_sponsor,
        "evidence_quiet_past_checkpoint": evidence_quiet,
        "repeated_shapes": repeated,
        "generated_at": now_utc(),
        "rules": {"percentages": False, "ranked_people_or_accounts": False, "health_score": False},
    }
