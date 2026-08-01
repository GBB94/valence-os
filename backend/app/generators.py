"""Stage 6 generators — finished artifacts, not read-only views
(PHASE-3-SPEC.md Part 5; EXPANSION-ENGINE-SPEC.md §8).

Every generator here obeys three rules that are enforced in the query, not by review:

**Promotion, by construction.** A client-facing artifact contains only affirmatively promoted
records. The generator never fetches an unpromoted row and filters it later, because a filter
that runs after the fetch is one refactor away from being dropped. `audience` on the returned
document says which rule set produced it.

**Stamping.** Every artifact carries generated-at, data-current-through, and what was missing
or stale at the time. A document is a claim about a moment; a reader who cannot see the moment
cannot judge the claim.

**Typed content.** Facts, interpretations, hypotheses and recommendations are labeled as such.
An operator's judgment rendered in the same weight as a measured number is how a deck loses an
argument in procurement.

The generators return structured dicts AND markdown. Markdown is the stored form (migration
0020) because it is diffable and re-renderable; .pptx is produced on download by app/decks.py.
"""
from __future__ import annotations

import sqlite3
from fastapi import HTTPException

from . import cadence, expansion, jobs, onboarding, people_core, repo
from .db import now_utc

# Content types, per the Section 3 security model / Module K rules.
FACT = "confirmed_fact"
INTERP = "internal_interpretation"
HYPOTH = "open_hypothesis"
ACTION = "recommended_action"


def _stamp(conn, missing: list[str] | None = None, current_through: list[str] | None = None) -> dict:
    dated = sorted(d[:10] for d in (current_through or []) if d)
    return {"generated_at": now_utc(), "data_current_through": dated[0] if dated else None,
            "missing_or_stale_sources": missing or []}


def _source(conn: sqlite3.Connection, source_id: str | None) -> dict | None:
    if not source_id:
        return None
    row = conn.execute("SELECT id, label, url, locator, created_at FROM source_references "
                       "WHERE id=? AND archived=0", (source_id,)).fetchone()
    return dict(row) if row else None


def _source_text(source: dict | None) -> str:
    if not source:
        return "—"
    where = source.get("locator") or source.get("url")
    return source["label"] + (f" · {where}" if where else "")


def _target_source(conn: sqlite3.Connection, target: dict) -> dict | None:
    source = _source(conn, target.get("source_reference_id"))
    if source or not target.get("source_interaction_id"):
        return source
    row = conn.execute("SELECT occurred_on, summary FROM interactions WHERE id=? AND archived=0",
                       (target["source_interaction_id"],)).fetchone()
    return ({"id": target["source_interaction_id"],
             "label": f"Interaction {row['occurred_on']}", "locator": row["summary"],
             "created_at": row["occurred_on"]} if row else None)


def _agreement_source(conn: sqlite3.Connection, agreement: dict) -> dict | None:
    source = _source(conn, agreement.get("source_reference_id"))
    if source or not agreement.get("source_interaction_id"):
        return source
    row = conn.execute("SELECT occurred_on FROM interactions WHERE id=? AND archived=0",
                       (agreement["source_interaction_id"],)).fetchone()
    return ({"id": agreement["source_interaction_id"],
             "label": f"Interaction {row['occurred_on']}", "locator": None,
             "created_at": row["occurred_on"]} if row else None)


def _md_table(headers: list[str], rows: list[list]) -> list[str]:
    if not rows:
        return ["_None._", ""]
    def safe(value):
        if value is None or value == "":
            return "—"
        return str(value).replace("|", "\\|").replace("\r", " ").replace("\n", " ")
    out = ["| " + " | ".join(safe(h) for h in headers) + " |",
           "|" + "|".join("---" for _ in headers) + "|"]
    out += ["| " + " | ".join(safe(c) for c in r) + " |" for r in rows]
    out.append("")
    return out


# --- Pre-call brief (Part 5) --------------------------------------------------------------------
def pre_call_brief(conn: sqlite3.Connection, account_id: str, *,
                   program_id: str | None = None, person_ids: list[str] | None = None) -> dict:
    """Everything the operator needs in the two minutes before a call.

    Internal by construction: it carries stances, raw judgments, and unanswered-email flags,
    none of which are client-facing. It is assembled from person cards (§3.10) rather than
    re-querying people, so the brief and the card can never disagree about someone.
    """
    acct = repo.get_row(conn, "accounts", account_id)
    today = now_utc()[:10]

    if program_id:
        program = repo.get_row(conn, "programs", program_id)
        if program["account_id"] != account_id:
            raise HTTPException(422, "program belongs to a different account")
    pids = ([program_id] if program_id else
            [p["id"] for p in repo.list_rows(conn, "programs", where="account_id=?",
                                               params=(account_id,))])

    # Attendees: explicit list, else everyone with a role on the program / account.
    if person_ids:
        people = []
        for pid in person_ids:
            person = repo.get_row(conn, "persons", pid)
            if person.get("account_id") != account_id:
                raise HTTPException(422, f"person {pid} belongs to a different account")
            if pids and not conn.execute(
                    "SELECT 1 FROM stakeholder_roles WHERE archived=0 AND person_id=? AND "
                    f"program_id IN ({','.join('?' * len(pids))})", (pid, *pids)).fetchone():
                raise HTTPException(422, f"person {pid} is not a stakeholder in this scope")
            people.append(person)
    else:
        where = "sr.archived=0 AND pr.account_id=?"
        params: list = [account_id]
        if program_id:
            where += " AND sr.program_id=?"
            params.append(program_id)
        people = [dict(r) for r in conn.execute(
            f"SELECT DISTINCT pe.* FROM stakeholder_roles sr JOIN programs pr ON pr.id=sr.program_id "
            f"JOIN persons pe ON pe.id=sr.person_id WHERE {where} AND pe.archived=0 "
            f"AND pe.account_id=? ORDER BY pe.name", (*params, account_id))]

    attendees, missing = [], []
    for p in people:
        card = people_core.person_card(conn, p["id"])
        scoped_roles = [r for r in card.get("roles") or [] if r.get("program_id") in pids]
        primary = (scoped_roles or [None])[0]
        # person_card's role dicts are shaped for display and carry no person_id; cadence_state
        # needs one to look up the last meaningful touch.
        state = cadence.cadence_state(conn, {**primary, "person_id": p["id"]}, today) if primary else None
        last = cadence.last_meaningful_touch(conn, p["id"])
        if p.get("is_placeholder"):
            missing.append(f"{p['name']} is still an unidentified position")
        attendees.append({
            "person_id": p["id"], "name": p["name"], "title": p["title"],
            "is_placeholder": bool(p.get("is_placeholder")),
            "role": (primary or {}).get("effective_role") or (primary or {}).get("role"),
            "layer": (primary or {}).get("layer"),
            # Stance is a dated judgment, never an unqualified label.
            "stance": (primary or {}).get("stance"), "type": INTERP,
            "stance_assessed_on": (primary or {}).get("stance_assessed_on"),
            "cares_about": (primary or {}).get("cares_about"),
            "last_touch": last, "cadence": state,
            "open_commitments": [c for c in (card.get("open_commitments") or [])
                                 if c.get("program_id") in pids],
            "suggested_touch": cadence.suggested_touch(
                conn, p["id"], p["name"], (primary or {}).get("cares_about")),
        })

    pq = ",".join("?" * len(pids)) or "''"

    live_risks = [{"description": r["description"], "severity": r["severity"],
                   "is_blocker": bool(r["is_blocker"]), "type": FACT}
                  for r in conn.execute(
                      f"SELECT * FROM risks WHERE archived=0 AND status='open' AND program_id IN ({pq}) "
                      f"ORDER BY is_blocker DESC, severity", pids)] if pids else []

    gate_items = [{"description": g["description"], "gate": g["gname"], "type": FACT}
                  for g in conn.execute(
                      f"SELECT gi.description, pg.name gname FROM phase_gate_items gi "
                      f"JOIN phase_gates pg ON pg.id=gi.gate_id "
                      f"WHERE gi.complete=0 AND pg.program_id IN ({pq}) AND pg.status<>'passed'",
                      pids)] if pids else []

    # Unanswered priority email (4.3). Comm messages carry their own flag + reason.
    unanswered = [{"subject": m["subject"], "from": m["from_addr"], "reason": m["flag_reason"],
                   "occurred_on": m["occurred_on"], "type": FACT}
                  for m in repo.list_rows(
                      conn, "comm_messages",
                      where="account_id=? AND needs_response=1 AND responded=0 ORDER BY occurred_on",
                      params=(account_id,))]

    # Talking points: open first-call questions carried on the checklist, plus what the
    # attendees care about. Recommendations, labeled as such.
    open_questions = [c["label"] for c in repo.list_rows(
        conn, "checklist_items",
        where="account_id=? AND status<>'done' AND section LIKE '%question%' ORDER BY due_date",
        params=(account_id,))]
    talking_points = [{"point": q, "type": ACTION} for q in open_questions]
    for a in attendees:
        if a["cares_about"]:
            talking_points.append({"point": f"{a['name']} cares about: {a['cares_about']}",
                                   "type": ACTION})

    doc = {
        "kind": "pre_call_brief", "audience": "internal",
        "account_id": account_id, "account_name": acct["name"], "program_id": program_id,
        "attendees": attendees, "live_risks": live_risks, "gate_items_due": gate_items,
        "unanswered_email": unanswered, "talking_points": talking_points,
        "stamp": _stamp(conn, missing, [
            x for a in attendees for x in (a.get("stance_assessed_on"), a.get("last_touch")) if x]),
    }
    doc["markdown"] = _render_brief(doc)
    return doc


def _render_brief(d: dict) -> str:
    s = d["stamp"]
    md = [f"# Pre-call brief — {d['account_name']}", "",
          f"_Internal. Generated {s['generated_at']} · current through {s['data_current_through']}_", ""]
    if s["missing_or_stale_sources"]:
        md += ["> **Known gaps:** " + "; ".join(s["missing_or_stale_sources"]), ""]

    md += ["## Who is in the room", ""]
    for a in d["attendees"]:
        head = f"**{a['name']}**" + (f" — {a['title']}" if a["title"] else "")
        if a["is_placeholder"]:
            head += " _(position, not yet identified)_"
        md.append(head)
        bits = []
        if a["role"]:
            bits.append(a["role"].replace("_", " "))
        if a["stance"]:
            bits.append(f"stance: {a['stance']} (judgment, as of {a['stance_assessed_on'] or 'undated'})")
        if a["last_touch"]:
            bits.append(f"last touch {a['last_touch']}")
        if a["cadence"] and a["cadence"].get("overdue"):
            over = a["cadence"].get("overdue_by")
            bits.append(f"**cadence overdue** by {over}d" if over else "**never touched**")
        md.append("- " + " · ".join(bits) if bits else "- _no assessment on file_")
        for c in a["open_commitments"]:
            owner = "they owe" if c.get("direction") == "theirs" else "we owe"
            md.append(f"    - {owner}: {c['description']} (due {c.get('due_date') or '—'})")
        md.append("")

    md += ["## Live risks", ""]
    md += _md_table(["Risk", "Severity", "Blocker"],
                    [[r["description"], r["severity"], "yes" if r["is_blocker"] else ""]
                     for r in d["live_risks"]])
    md += ["## Gate items still open", ""]
    md += _md_table(["Item", "Gate"], [[g["description"], g["gate"]] for g in d["gate_items_due"]])
    md += ["## Unanswered, flagged", ""]
    md += _md_table(["Subject", "From", "Why flagged", "When"],
                    [[m["subject"], m["from"], m["reason"], m["occurred_on"]]
                     for m in d["unanswered_email"]])
    md += ["## Suggested talking points", "", "_Recommendations, not facts._", ""]
    md += [f"- {t['point']}" for t in d["talking_points"]] or ["_None._"]
    return "\n".join(md)


# --- Expansion business case (Part 5 + EXPANSION-ENGINE-SPEC §§1, 2, 4, 9) ----------------------
def business_case(conn: sqlite3.Connection, account_id: str) -> dict:
    """The day-75 artifact, built continuously.

    This is the generator the Stage 5.5 re-sequencing existed for: every section below reads a
    real record rather than a placeholder. Scorecard from value targets, evidence by tier,
    waterfall from funding pools, lines from whitespace cells.

    Client-facing, so promotion is enforced in the query: only `qbr_exec` /
    `externally_referenceable`, non-negative value stories, and only client-accepted targets.
    """
    acct = repo.get_row(conn, "accounts", account_id)
    led = expansion.ledger(conn, account_id)
    funding = expansion.funding_view(conn, account_id)
    wmap = expansion.whitespace_map(conn, account_id)

    # Scorecard: the bar the client themselves accepted. An internal target is not a promise
    # they made, so it has no place in a document arguing they got what was promised.
    scorecard = []
    missing = []
    source_dates = []
    for target in led["targets"]:
        if not (target.get("client_accepted") and target.get("client_visible")):
            continue
        source = _target_source(conn, target)
        if not source:
            missing.append(f"{target['metric']} / {target['population']} is promoted but has no source")
            continue
        target = {**target, "source": source}
        scorecard.append(target)
        source_dates += [target["realization"].get("current_through"), source.get("created_at")]
        if target["realization"].get("stale"):
            missing.append(f"{target['metric']} / {target['population']}: "
                           f"stale — {target['realization'].get('reason') or 'freshness window exceeded'}")
    if not scorecard:
        missing.append("no client-accepted value targets — the scorecard is empty")

    stories = repo.list_rows(
        conn, "value_stories",
        where="account_id=? AND is_negative=0 AND source_reference_id IS NOT NULL "
              "AND visibility_class IN ('qbr_exec','externally_referenceable') "
              "ORDER BY evidence_tier DESC",
        params=(account_id,))
    evidence = [{"outcome": v["outcome"], "evidence_tier": v["evidence_tier"],
                 "source": _source(conn, v["source_reference_id"]),
                 "type": FACT if v["evidence_tier"] in ("measured_operational", "correlated_business")
                 else INTERP} for v in stories]
    source_dates += [e["source"].get("created_at") for e in evidence if e.get("source")]

    # Funding waterfall: confirmed and committed pools are the credible money.
    pools = [{"name": p["name"], "kind": p["kind"], "status": p["status"],
              "amount": p["amount"], "currency": p["currency"], "owner": p["owner_name"],
              "type": FACT if p["status"] in ("committed", "confirmed") else HYPOTH,
              "source": _source(conn, p.get("source_reference_id"))}
             for p in funding["funding_pools"]
             if p["status"] != "unavailable" and p.get("client_visible") and p.get("source_reference_id")]
    source_dates += [p["source"].get("created_at") for p in pools if p.get("source")]

    # Named lines: Proven and Target cells only. A paid-but-unevidenced cell is NOT an expansion
    # line — it is already bought, and listing it here would pad the ask with seats the client
    # has paid for while quietly implying value we have not demonstrated. Those cells belong in
    # the value review's gap section, which is where they appear.
    lines = []
    for row in wmap["segment_rows"]:
        for slot in row["cells"]:
            c = slot["cell"]
            if (c and c["state"] in ("proven", "target") and c.get("client_visible")
                    and c.get("source_reference_id")):
                source = _source(conn, c["source_reference_id"])
                lines.append({"population": row["name"], "use_case": slot["use_case"],
                              "state": c["state_label"], "next_action": c["next_action"],
                              "estimated_seats": c["estimated_seats"],
                              "source": source,
                              "type": HYPOTH if c["state"] == "target" else INTERP})
                if source:
                    source_dates.append(source.get("created_at"))
    if not lines:
        missing.append("no Proven or Target cells — there is no argued expansion yet")

    # The account-wide whitespace total is internal commercial intelligence. A client-facing
    # ask may only summarize rows whose cell was affirmatively promoted above. De-duplicate by
    # segment because multiple use cases in the same population are not additive inventories.
    shared_rows = {}
    for row in wmap["segment_rows"]:
        promoted = [slot for slot in row["cells"] if slot["cell"] and
                    slot["cell"].get("client_visible") and
                    slot["cell"].get("source_reference_id")]
        if not promoted:
            continue
        motions = [slot["use_case"] for slot in promoted
                   if slot["cell"]["state"] in ("proven", "target")]
        shared_rows[row["id"]] = {
            "population": row["name"],
            "seats": max((row["headcount"] or 0) - (row["paid_seats"] or 0), 0),
            "paid": row["paid_seats"] or 0,
            "addressable": row["headcount"] or 0,
            "motion": motions[0] if motions else None,
        }
    ranked_shared = sorted(shared_rows.values(), key=lambda r: -r["seats"])
    ask = {
        "unpenetrated_seats": sum(r["seats"] for r in ranked_shared),
        "top_populations": ranked_shared[:3],
        "type": ACTION,
    }

    triggers = []
    for agreement in repo.list_rows(
            conn, "operational_agreements",
            where="account_id=? AND status='active' AND client_visible=1 ORDER BY effective_on",
            params=(account_id,)):
        source = _agreement_source(conn, agreement)
        if not source:
            continue
        trigger_target = repo.get_row(conn, "value_targets", agreement["value_target_id"])
        triggers.append({**agreement, "source": source, "target": trigger_target,
                         "realization": expansion.target_realization(conn, trigger_target),
                         "contractual": agreement["source_kind"] == "signed_paper"})
        source_dates.append(source.get("created_at"))
    if not triggers:
        missing.append("no pre-agreed expansion triggers on the current contract")

    doc = {
        "kind": "business_case", "audience": "client_facing",
        "account_id": account_id, "account_name": acct["name"],
        "scorecard": scorecard, "evidence": evidence, "funding": pools,
        "lines": lines, "ask": ask, "pre_agreed_triggers": triggers,
        "penetration": {"paid_seats": sum(r["paid"] for r in ranked_shared),
                        "addressable_seats": sum(r["addressable"] for r in ranked_shared),
                        "type": FACT},
        "stamp": _stamp(conn, missing, source_dates),
        "excluded_note": "Internal-only records, negative evidence, and targets the client did "
                         "not accept are excluded by construction, not by review.",
    }
    doc["markdown"] = _render_business_case(doc)
    return doc


def _render_business_case(d: dict) -> str:
    s = d["stamp"]
    md = [f"# Expansion business case — {d['account_name']}", "",
          f"_Generated {s['generated_at']} · current through {s['data_current_through']}_", ""]
    if s["missing_or_stale_sources"]:
        md += ["> **Gaps in this case:** " + "; ".join(s["missing_or_stale_sources"]), ""]

    p = d["penetration"]
    md += ["## Where we are", "",
           f"{p['paid_seats']:,} paid seats of {p['addressable_seats']:,} addressable.", ""]

    md += ["## Against the bar you set", ""]
    md += _md_table(["Metric", "Population", "Bar", "Current", "Status", "Source"],
                    [[t["metric"], t["population"],
                      ("≤ " if t["direction"] == "at_most" else "≥ ") + str(t["target_value"]),
                      t["realization"]["value"] if t["realization"]["value"] is not None else "unknown",
                      t["realization"]["status"].replace("_", " "), _source_text(t.get("source"))]
                     for t in d["scorecard"]])

    md += ["## Evidence", ""]
    md += _md_table(["Outcome", "Tier", "Type", "Source"],
                    [[e["outcome"], e["evidence_tier"].replace("_", " "),
                      e["type"].replace("_", " "), _source_text(e.get("source"))]
                     for e in d["evidence"]])

    md += ["## How it gets funded", ""]
    md += _md_table(["Funding source", "Owner", "Amount", "Status", "Evidence"],
                    [[f["name"], f["owner"], f"{f['currency'] or ''} {f['amount']:,.0f}".strip()
                      if f["amount"] else "—", f["status"], _source_text(f.get("source"))]
                     for f in d["funding"]])

    md += ["## Named lines", ""]
    md += _md_table(["Population", "Use case", "State", "Next action", "Source"],
                    [[l["population"], l["use_case"], l["state"], l["next_action"],
                     _source_text(l.get("source"))] for l in d["lines"]])

    md += ["## Pre-agreed expansion triggers", ""]
    md += _md_table(["Agreement", "Bar", "Seat band", "Process", "Source"],
                    [[t["name"], t["target"]["target_value"] if t.get("target") else "linked target",
                      f"{t['seat_band_min']:,}–{t['seat_band_max']:,}", t["agreed_process"],
                      _source_text(t.get("source"))] for t in d["pre_agreed_triggers"]])

    a = d["ask"]
    md += ["## The ask", "", f"_Recommendation._ {a['unpenetrated_seats']:,} seats remain "
           f"unpenetrated. The nearest three:", ""]
    md += [f"- **{t['population']}** — {t['seats']:,} seats" + (f", via {t['motion']}" if t["motion"] else "")
           for t in a["top_populations"]] or ["_No unpenetrated populations on record._"]
    md += ["", f"_{d['excluded_note']}_"]
    return "\n".join(md)


# --- Value review — the QBR, reframed (EXPANSION-ENGINE-SPEC §8) ---------------------------------
def value_review(conn: sqlite3.Connection, account_id: str) -> dict:
    """The QBR's forward-looking half, on top of the corrected generator (D-82).

    "Backward-looking status reports are where QBRs go to die." So: progress against the
    client's own bar, the gaps and the plan to close them, and the expansion frame — value
    achieved here, projected value there — drawn from cells adjacent to realized targets.
    """
    from . import output_gen

    base = output_gen.qbr(conn, account_id)          # metrics, benchmarks, promoted stories
    led = expansion.ledger(conn, account_id)
    wmap = expansion.whitespace_map(conn, account_id)

    accepted = [{**t, "source": _target_source(conn, t)} for t in led["targets"]
                if t.get("client_accepted") and t.get("client_visible") and
                _target_source(conn, t)]
    realized = [t for t in accepted if t["realization"]["status"] == "realized"]

    # The expansion frame: "value achieved here, projected there." Adjacency to proof is what
    # makes a projection arguable rather than hopeful, and it runs along BOTH axes:
    #   - same population, different use case  ("it worked for DACH, widen what DACH uses")
    #   - same use case, different population  ("performance reviews worked, take them to Nordics")
    # The second is usually the stronger argument, so it is named separately rather than folded
    # into one boolean the reader has to interpret.
    proven_populations = {t["population"] for t in realized}
    proven_use_cases = set()
    for row in wmap["segment_rows"]:
        if row["name"] not in proven_populations:
            continue
        for slot in row["cells"]:
            c = slot["cell"]
            if c and c["state"] in ("penetrated", "proven"):
                proven_use_cases.add(slot["use_case"])

    adjacent = []
    for row in wmap["segment_rows"]:
        for slot in row["cells"]:
            c = slot["cell"]
            if (c and c["state"] in ("proven", "target") and c.get("client_visible")
                    and c.get("source_reference_id")):
                same_pop = row["name"] in proven_populations
                same_uc = slot["use_case"] in proven_use_cases
                adjacent.append({
                    "population": row["name"], "use_case": slot["use_case"],
                    "state": c["state_label"],
                    "adjacent_to_proof": same_pop or same_uc,
                    "basis": ("this use case is already proven elsewhere in the account" if same_uc
                              else "this population already has a realized outcome" if same_pop
                              else "no adjacent proof yet"),
                    "type": HYPOTH,
                })
    adjacent.sort(key=lambda x: not x["adjacent_to_proof"])

    # Exec attendance by layer (§8). A value review without Economic-layer attendance flags
    # the next one — computed, not remembered.
    layers = [r["layer"] for r in conn.execute(
        "SELECT DISTINCT sr.layer FROM stakeholder_roles sr "
        "JOIN programs pr ON pr.id=sr.program_id "
        "WHERE pr.account_id=? AND sr.archived=0 AND sr.layer IS NOT NULL", (account_id,))]
    economic_covered = "economic" in layers

    triggers = []
    for agreement in repo.list_rows(
            conn, "operational_agreements",
            where="account_id=? AND status='active' AND client_visible=1 ORDER BY effective_on",
            params=(account_id,)):
        source = _agreement_source(conn, agreement)
        if source:
            target = repo.get_row(conn, "value_targets", agreement["value_target_id"])
            triggers.append({**agreement, "target": target,
                             "realization": expansion.target_realization(conn, target),
                             "source": source,
                             "contractual": agreement["source_kind"] == "signed_paper"})
    if not triggers:
        base["stamp"]["missing_or_stale_sources"].append(
            "no pre-agreed expansion triggers on the current contract")

    doc = {
        **base,
        "kind": "value_review", "audience": "client_facing",
        "progress_against_your_bar": accepted,
        "value_gaps": [g for g in led["value_gaps"] if conn.execute(
            "SELECT 1 FROM whitespace_cells WHERE id=? AND client_visible=1 "
            "AND source_reference_id IS NOT NULL", (g["cell_id"],)).fetchone()],
        "expansion_frame": adjacent,
        "pre_agreed_triggers": triggers,
        "attendance": {
            "layers_on_record": sorted(layers),
            "economic_layer_covered": economic_covered,
            "flag": None if economic_covered else
                    "No Economic-layer stakeholder on record — flag the next review",
            "type": INTERP,
        },
    }
    doc["markdown"] = _render_value_review(doc)
    return doc


def _render_value_review(d: dict) -> str:
    s = d["stamp"]
    md = [f"# Value review — {d['account_name']}", "",
          f"_Generated {s['generated_at']} · current through {s['data_current_through']}_", ""]
    if s.get("missing_or_stale_sources"):
        md += ["> **Unknown or stale at generation:** " + ", ".join(s["missing_or_stale_sources"]), ""]

    md += ["## Current evidence", ""]
    md += _md_table(["Metric", "Value", "Target", "Current through", "Source"],
                    [[m["name"], m["value"], m["target"], m["current_through"],
                      _source_text(m.get("source"))] for m in d.get("metrics", [])])
    md += ["## Value stories", ""]
    md += _md_table(["Outcome", "Evidence", "Source"],
                    [[v["outcome"], v["evidence_tier"].replace("_", " "),
                      _source_text(v.get("source"))] for v in d.get("value_stories", [])])
    md += ["## Joint commitments", ""]
    md += _md_table(["Commitment", "Due", "Source"],
                    [[c["description"], c["due_date"], _source_text(c.get("source"))]
                     for c in d.get("open_commitments", [])])

    md += ["## Progress against the bar you set", ""]
    md += _md_table(["Metric", "Population", "Bar", "Current", "Status", "By", "Source"],
                    [[t["metric"], t["population"],
                      ("≤ " if t["direction"] == "at_most" else "≥ ") + str(t["target_value"]),
                      t["realization"]["value"] if t["realization"]["value"] is not None else "unknown",
                      t["realization"]["status"].replace("_", " "), t["timeframe_end"],
                      _source_text(t.get("source"))]
                     for t in d["progress_against_your_bar"]])

    md += ["## Where value is not yet demonstrated", ""]
    md += _md_table(["Cohort", "Use case", "Why"],
                    [[g["population"], g["use_case"], g["because"]] for g in d["value_gaps"]])

    md += ["## Value achieved here, projected there", "",
           "_Hypotheses. Cells adjacent to a realized outcome are listed first._", ""]
    md += _md_table(["Population", "Use case", "State", "Why this one"],
                    [[a["population"], a["use_case"], a["state"], a["basis"]]
                     for a in d["expansion_frame"]])

    md += ["## Pre-agreed expansion triggers", ""]
    md += _md_table(["Agreement", "Current", "Bar", "Fresh through", "Seat band", "Source"],
                    [[t["name"], t["realization"].get("value"), t["target"]["target_value"],
                      t["realization"].get("current_through"),
                      f"{t['seat_band_min']:,}–{t['seat_band_max']:,}", _source_text(t.get("source"))]
                     for t in d["pre_agreed_triggers"]])

    md += ["", f"_{d['excluded_note']}_"]
    return "\n".join(md)


# --- Champion enablement kit (Part 5) --------------------------------------------------------
def champion_kit(conn: sqlite3.Connection, account_id: str) -> dict:
    """A one-page value summary plus the ROI model, for a champion to carry internally.

    The champion is going to put this in front of their own executives with our name on it, so
    the promotion rule is at its strictest here: externally-referenceable evidence only, not
    even `qbr_exec`. ROI inputs render labeled as assumptions with their author and date.
    """
    acct = repo.get_row(conn, "accounts", account_id)
    missing = []

    stories = repo.list_rows(
        conn, "value_stories",
        where="account_id=? AND is_negative=0 AND source_reference_id IS NOT NULL "
              "AND visibility_class='externally_referenceable' "
              "ORDER BY evidence_tier DESC",
        params=(account_id,))
    if not stories:
        missing.append("no externally-referenceable value stories — nothing here is safe to "
                       "hand a champion yet")

    roi = repo.row_to_dict(conn.execute("SELECT * FROM roi_models WHERE account_id=?",
                                        (account_id,)).fetchone())
    recovered = None
    if roi and roi.get("recovered_spend_id"):
        recovered = repo.row_to_dict(conn.execute(
            "SELECT * FROM recovered_spend WHERE id=?", (roi["recovered_spend_id"],)).fetchone())
        if recovered and recovered.get("account_id") != account_id:
            raise HTTPException(422, "ROI model references recovered spend from another account")
        if recovered and not recovered.get("source_note"):
            missing.append("recovered vendor spend has no source note and was excluded")
            recovered = None
    if not roi:
        missing.append("no ROI model on file — the economics section is empty")

    # Armed champions are the audience; naming them lets the operator see who has the kit.
    armed = repo.list_rows(conn, "champion_candidates",
                           where="account_id=? AND stage IN ('arm','maintain')", params=(account_id,))
    names = {p["id"]: p["name"] for p in repo.list_rows(conn, "persons", where="1=1")}

    doc = {
        "kind": "champion_kit", "audience": "client_facing",
        "account_id": account_id, "account_name": acct["name"],
        "value_summary": [{"outcome": v["outcome"], "evidence_tier": v["evidence_tier"],
                           "source": _source(conn, v["source_reference_id"]), "type": FACT}
                          for v in stories],
        "roi": ({**roi, "recovered_spend": recovered, "type": INTERP} if roi else None),
        "for_champions": [{"person_id": c["person_id"], "name": names.get(c["person_id"]),
                           "stage": c["stage"]} for c in armed],
        "stamp": _stamp(conn, missing, [
            *(s.get("created_at") for s in (_source(conn, v["source_reference_id"])
                                             for v in stories) if s),
            roi.get("assessed_on") if roi else None,
        ]),
        "excluded_note": "Externally-referenceable evidence only — stricter than the QBR rule, "
                         "because a champion presents this without us in the room.",
    }
    doc["markdown"] = _render_champion_kit(doc)
    return doc


def _render_champion_kit(d: dict) -> str:
    s = d["stamp"]
    md = [f"# {d['account_name']} — value summary", "",
          f"_Generated {s['generated_at']} · current through {s['data_current_through']}_", ""]
    if s["missing_or_stale_sources"]:
        md += ["> **Not ready to hand over:** " + "; ".join(s["missing_or_stale_sources"]), ""]

    md += ["## What has been delivered", ""]
    md += _md_table(["Outcome", "Evidence", "Source"],
                    [[v["outcome"], v["evidence_tier"].replace("_", " "),
                      _source_text(v.get("source"))] for v in d["value_summary"]])

    md += ["## The economics", ""]
    r = d["roi"]
    if not r:
        md += ["_No ROI model on file._", ""]
    else:
        md += ["_Assumptions, not measurements — "
               f"recorded by {r.get('author') or 'unknown'} on {r.get('assessed_on') or 'an unknown date'}._", ""]
        rows = []
        if r.get("seat_price") is not None:
            rows.append(["Seat price", f"{r.get('seat_price_currency') or ''} {r['seat_price']:,.2f}".strip(),
                         r.get("seat_price_basis") or "assumption"])
        if r.get("retention_uplift_pct") is not None:
            rows.append(["Retention uplift", f"{r['retention_uplift_pct']}%", r.get("retention_note") or "assumption"])
        if r.get("recovered_spend"):
            rs = r["recovered_spend"]
            rows.append(["Recovered vendor spend", ((rs.get("currency") or "") + " " +
                         (f"{rs.get('amount'):,.0f}" if rs.get("amount") is not None else "—")).strip(),
                         rs.get("source_note") or rs.get("label") or ""])
        md += _md_table(["Input", "Value", "Basis"], rows)
        if r.get("assumptions_note"):
            md += [f"_{r['assumptions_note']}_", ""]

    if d["for_champions"]:
        md += ["## Prepared for", ""]
        md += [f"- {c['name']} ({c['stage']})" for c in d["for_champions"]] + [""]
    md += [f"_{d['excluded_note']}_"]
    return "\n".join(md)


def kickoff_deck(conn: sqlite3.Connection, account_id: str, *,
                 program_id: str | None = None) -> dict:
    """Saved/reviewable form of the kickoff skeleton; the direct download uses this too."""
    acct = repo.get_row(conn, "accounts", account_id)
    if program_id:
        program = repo.get_row(conn, "programs", program_id)
        if program["account_id"] != account_id:
            raise HTTPException(422, "program belongs to a different account")
    markdown = onboarding.deck_skeleton(conn, account_id, program_id)
    return {
        "kind": "kickoff_deck", "audience": "client_facing", "account_id": account_id,
        "account_name": acct["name"], "program_id": program_id, "markdown": markdown,
        # The skeleton is assembled from current operational records, not a metric snapshot.
        "stamp": _stamp(conn, current_through=[now_utc()[:10]]),
    }


# --- persistence -------------------------------------------------------------------------------
_GENERATORS = {
    "pre_call_brief": pre_call_brief,
    "business_case": business_case,
    "value_review": value_review,
    "champion_kit": champion_kit,
    "kickoff_deck": kickoff_deck,
}
_TITLES = {"pre_call_brief": "Pre-call brief", "business_case": "Expansion business case",
           "value_review": "Value review", "champion_kit": "Champion enablement kit",
           "kickoff_deck": "Kickoff deck", "team_update": "Weekly team update"}


def generate(conn: sqlite3.Connection, kind: str, account_id: str, **kwargs) -> dict:
    if kind not in _GENERATORS:
        raise HTTPException(422, f"unknown generator: {kind}")
    return _GENERATORS[kind](conn, account_id, **kwargs)


def save_draft(conn: sqlite3.Connection, doc: dict, *, source_job_id: str | None = None,
               program_id: str | None = None) -> dict:
    """Persist a generated artifact as a DRAFT. Nothing here sends anything, ever."""
    s = doc["stamp"]
    acct_name = doc.get("account_name") or "portfolio"
    saved = repo.insert(conn, "generated_documents", {
        "account_id": doc.get("account_id"), "program_id": program_id or doc.get("program_id"),
        "kind": doc["kind"], "title": f"{_TITLES.get(doc['kind'], doc['kind'])} — {acct_name}",
        "body_markdown": doc["markdown"], "status": "draft",
        "generated_at": s["generated_at"], "data_current_through": s.get("data_current_through"),
        "missing_or_stale_note": "; ".join(s.get("missing_or_stale_sources") or []) or None,
        "audience": doc.get("audience", "internal"), "source_job_id": source_job_id,
    }, object_type="generated_document")
    if doc.get("kind") == "champion_kit":
        with conn:
            for champion in doc.get("for_champions") or []:
                conn.execute(
                    "INSERT OR IGNORE INTO generated_document_people "
                    "(document_id,person_id,purpose,created_at) VALUES (?,?,?,?)",
                    (saved["id"], champion["person_id"], "champion_enablement", now_utc()),
                )
    return saved


# --- scheduled generation (Part 5: "generated on a timer, saved as a draft, never auto-sent") ---
@jobs.register("weekly_team_update")
def _weekly_team_update(conn, payload):
    """Job handler: produce the weekly update and park it in the review queue.

    Portfolio-wide, so it has no account_id. The spec's rule is the whole point of routing this
    through a job at all: it lands as a draft and waits for a human, rather than a timer
    deciding that something is fit to send.
    """
    from . import output_gen
    upd = output_gen.team_update(conn, since=payload.get("since"))
    doc = repo.insert(conn, "generated_documents", {
        "account_id": None, "kind": "team_update",
        "title": f"Weekly team update — {upd['stamp']['window_since']} to {upd['stamp']['window_until']}",
        "body_markdown": upd["markdown"], "status": "draft",
        "generated_at": upd["stamp"]["generated_at"],
        "data_current_through": upd["stamp"]["data_current_through"],
        "audience": "internal", "source_job_id": payload.get("_job_id"),
    }, object_type="generated_document")
    if payload.get("recurring"):
        from datetime import datetime, timedelta, timezone
        next_run = (datetime.now(timezone.utc) + timedelta(days=7)).isoformat(timespec="seconds")
        jobs.enqueue(conn, "weekly_team_update",
                     {"since": None, "recurring": True}, scheduled_for=next_run)
    return {"document_id": doc["id"], "accounts_covered": len(upd["sections"])}


def schedule_weekly_update(conn: sqlite3.Connection, *, run_at: str | None = None,
                           since: str | None = None, recurring: bool = True) -> dict:
    """Queue the weekly update. `run_at` is an ISO timestamp; omit to run on the next drain."""
    return jobs.enqueue(conn, "weekly_team_update",
                        {"since": since, "recurring": recurring}, scheduled_for=run_at)
