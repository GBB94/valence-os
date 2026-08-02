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

from . import expansion, repo
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
def _observation_query(conn, target: dict, campaign: dict):
    """Observations matching the target's stable identity, oldest first.

    Matches on definition, version, unit and population identity — never on a free-text cohort
    label, which is what made realization uncomputable before Stage 5.5.
    """
    segment_id, view_id = _cohort(campaign)
    return conn.execute(
        "SELECT * FROM metric_observations WHERE archived=0 AND definition_id=? "
        "AND IFNULL(population_segment_id,'')=IFNULL(?,'') "
        "AND IFNULL(population_view_id,'')=IFNULL(?,'') "
        "ORDER BY current_through",
        (target["definition_id"], segment_id, view_id)).fetchall()


def baseline_snapshot(conn: sqlite3.Connection, campaign: dict, value_target: dict) -> dict:
    """The locked point plus the series it sits in, frozen at readiness (§5.1)."""
    rows = [repo.row_to_dict(r) for r in _observation_query(conn, value_target, campaign)]
    if not rows:
        return {"baseline_observation_id": None, "trajectory": [], "reason": "no observation for this cohort"}
    latest = rows[-1]
    prior = rows[-(BASELINE_LOOKBACK + 1):-1]
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

    rows = [repo.row_to_dict(r) for r in _observation_query(conn, vt, campaign)]
    # A finished campaign is measured at its window, not at "whatever landed since". Taking the
    # newest observation forever would let movement months after the campaign ended flow into its
    # delta — silently re-attributing later change to an intervention that had already stopped.
    finished = campaign["status"] in ("completed", "cancelled")
    # The judgement moment is when the operator actually reviewed it — not a planned evaluation
    # date, which may still be in the future and would make recent evidence look "stale" by
    # measuring its age against a date that has not arrived.
    cutoff = (campaign.get("completion_reviewed_on") or campaign.get("evaluation_on")
              or campaign["planned_end_on"])
    if finished:
        cutoff = min(cutoff, _today())
        rows = [r for r in rows if (r.get("current_through") or "") <= cutoff]
    current = rows[-1] if rows else None
    if not current:
        return {"status": "no_evidence", "value": None, "baseline_value": None, "delta": None,
                "design": campaign["evaluation_design"],
                "cautions": [{"kind": "no_observation", "detail": "no observation for this cohort"}]}
    if _stale(conn, current, cutoff if finished else None):
        return {"status": "unknown", "value": None,
                "baseline_value": baseline["value"] if baseline else None, "delta": None,
                "current_through": current["current_through"],
                "design": campaign["evaluation_design"],
                "cautions": [{"kind": "stale_evidence",
                              "detail": "observation is past its freshness threshold"}]}

    delta = None
    if baseline and baseline["value"] is not None and current["value"] is not None:
        delta = round(current["value"] - baseline["value"], 6)

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

    rows = [repo.row_to_dict(r) for r in conn.execute(
        "SELECT * FROM metric_observations WHERE archived=0 AND definition_id=? "
        "AND IFNULL(population_segment_id,'')=IFNULL(?,'') "
        "AND IFNULL(population_view_id,'')=IFNULL(?,'') "
        "AND current_through >= ? AND current_through <= ? ORDER BY current_through",
        (value_target["definition_id"], seg, view, baseline_from, cutoff))]
    if len(rows) < 2:
        return {"delta": None, "reason": "comparator needs two observations spanning the window"}
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
