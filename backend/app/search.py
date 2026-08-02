"""Global search (Section 8) — FTS5 over native records and stored summaries.

The index is rebuilt on demand from current data (few-thousand-row scale, so a full
reindex is sub-millisecond and always fresh — no triggers to keep in sync). This is
the operator's own single-editor tool, so their internal notes are searchable to them.
"""
from __future__ import annotations

import sqlite3

# Each source: (object_type, SQL selecting id, account_id, program_id, title, body).
# account_id/program_id may be NULL; body is the free text to index.
_SOURCES = [
    ("account", "SELECT id, id AS account_id, NULL AS program_id, name AS title, "
                "COALESCE(name,'')||' '||COALESCE(short_context,'')||' '||COALESCE(incumbent_note,'') AS body "
                "FROM accounts WHERE archived=0"),
    ("program", "SELECT id, account_id, id AS program_id, name AS title, "
                "COALESCE(name,'')||' '||COALESCE(problem_statement,'')||' '||COALESCE(success_criteria,'')||' '||"
                "COALESCE(expansion_hypothesis,'')||' '||COALESCE(region,'')||' '||COALESCE(audience,'') AS body "
                "FROM programs WHERE archived=0"),
    ("person", "SELECT id, account_id, NULL, name AS title, "
               "COALESCE(name,'')||' '||COALESCE(title,'')||' '||COALESCE(email,'') AS body "
               "FROM persons WHERE archived=0"),
    ("interaction", "SELECT id, account_id, program_id, COALESCE(summary,'(interaction)') AS title, "
                    "COALESCE(summary,'')||' '||COALESCE(raw_notes,'')||' '||COALESCE(follow_up,'') AS body "
                    "FROM interactions WHERE archived=0"),
    ("commitment", "SELECT c.id, c.account_id, c.program_id, c.description AS title, c.description AS body "
                   "FROM commitments c WHERE c.archived=0"),
    ("risk", "SELECT r.id, p.account_id, r.program_id, r.description AS title, "
             "COALESCE(r.description,'')||' '||COALESCE(r.mitigation,'') AS body "
             "FROM risks r JOIN programs p ON p.id=r.program_id WHERE r.archived=0"),
    ("issue", "SELECT i.id, p.account_id, i.program_id, i.description AS title, i.description AS body "
              "FROM issues i JOIN programs p ON p.id=i.program_id WHERE i.archived=0"),
    ("decision", "SELECT d.id, d.account_id, d.program_id, d.description AS title, "
                 "COALESCE(d.description,'')||' '||COALESCE(d.rationale,'') AS body "
                 "FROM decisions d WHERE d.archived=0"),
    ("task", "SELECT t.id, p.account_id, t.program_id, t.description AS title, t.description AS body "
             "FROM tasks t JOIN programs p ON p.id=t.program_id WHERE t.archived=0"),
    ("milestone", "SELECT m.id, p.account_id, m.program_id, m.name AS title, "
                  "COALESCE(m.name,'')||' '||COALESCE(m.success_criteria,'') AS body "
                  "FROM milestones m JOIN programs p ON p.id=m.program_id WHERE m.archived=0"),
    ("value_story", "SELECT id, account_id, program_id, outcome AS title, "
                    "COALESCE(outcome,'')||' '||COALESCE(tags,'') AS body FROM value_stories WHERE archived=0"),
    ("expansion_opportunity", "SELECT id, account_id, NULL, name AS title, "
                              "COALESCE(name,'')||' '||COALESCE(use_case,'')||' '||COALESCE(blockers,'')||' '||"
                              "COALESCE(next_action,'') AS body FROM expansion_opportunities WHERE archived=0"),
    ("capture_inbox_item", "SELECT ci.id, i.account_id, i.program_id, ci.raw_text AS title, ci.raw_text AS body "
                           "FROM capture_inbox_items ci JOIN interactions i ON i.id=ci.interaction_id "
                           "WHERE ci.archived=0 AND ci.status='untriaged'"),
    ("scope_change", "SELECT s.id, p.account_id, s.program_id, s.description AS title, s.description AS body "
                     "FROM scope_changes s JOIN programs p ON p.id=s.program_id WHERE s.archived=0"),
    # --- Stage 4-5 records that were built but never indexed -------------------------------
    ("comm_message", "SELECT id, account_id, program_id, COALESCE(subject,'(message)') AS title, "
                     "COALESCE(subject,'')||' '||COALESCE(summary,'') AS body "
                     "FROM comm_messages WHERE archived=0"),
    ("pull_signal", "SELECT id, account_id, program_id, description AS title, description AS body "
                    "FROM pull_signals WHERE archived=0"),
    ("checklist_item", "SELECT id, account_id, program_id, label AS title, "
                       "COALESCE(label,'')||' '||COALESCE(detail,'')||' '||COALESCE(answer_note,'') AS body "
                       "FROM checklist_items WHERE archived=0"),
    # --- Stage 5.5 -------------------------------------------------------------------------
    # A whitespace cell's searchable text is its population and use case, so "DACH change
    # management" finds the cell rather than only the records hanging off it.
    ("whitespace_cell", "SELECT wc.id, wc.account_id, NULL, "
                        "COALESCE(ps.name, pv.name,'')||' — '||uc.name AS title, "
                        "COALESCE(ps.name,'')||' '||COALESCE(pv.name,'')||' '||uc.name||' '||"
                        "COALESCE(wc.next_action,'')||' '||COALESCE(wc.notes,'')||' '||"
                        "COALESCE(wc.blocker_note,'')||' '||COALESCE(wc.declined_reason,'') AS body "
                        "FROM whitespace_cells wc JOIN use_cases uc ON uc.id=wc.use_case_id "
                        "LEFT JOIN population_segments ps ON ps.id=wc.segment_id "
                        "LEFT JOIN population_views pv ON pv.id=wc.view_id WHERE wc.archived=0"),
    ("value_target", "SELECT vt.id, vt.account_id, NULL, md.name AS title, "
                     "md.name||' '||COALESCE(vt.notes,'')||' '||COALESCE(vt.not_accepted_reason,'') AS body "
                     "FROM value_targets vt JOIN metric_definitions md ON md.id=vt.definition_id "
                     "WHERE vt.archived=0 AND vt.status='active'"),
    ("funding_pool", "SELECT id, account_id, NULL, name AS title, "
                     "COALESCE(name,'')||' '||COALESCE(kind,'')||' '||COALESCE(notes,'') AS body "
                     "FROM funding_pools WHERE archived=0"),
    # --- Stage 11: adoption campaigns ---------------------------------------------------------
    # The searchable text is the behaviour and hypothesis, because that is how an operator
    # remembers a campaign ("the one about manager 1:1s"), not by its name.
    ("adoption_campaign", "SELECT id, account_id, program_id, name AS title, "
                          "COALESCE(name,'')||' '||COALESCE(target_behavior,'')||' '||"
                          "COALESCE(hypothesis,'') AS body "
                          "FROM adoption_campaigns WHERE archived=0"),
    ("adoption_campaign_retrospective",
     "SELECT r.id, c.account_id, c.program_id, "
     "'Retrospective — '||c.name AS title, "
     "COALESCE(r.barrier_note,'')||' '||COALESCE(r.what_to_reuse,'')||' '||"
     "COALESCE(r.what_to_change,'')||' '||COALESCE(r.follow_on_note,'') AS body "
     "FROM adoption_campaign_retrospectives r "
     "JOIN adoption_campaigns c ON c.id=r.campaign_id WHERE c.archived=0"),
    ("adoption_campaign_barrier", "SELECT b.id, c.account_id, c.program_id, "
                                  "b.description AS title, "
                                  "b.category||' '||COALESCE(b.description,'') AS body "
                                  "FROM adoption_campaign_barriers b "
                                  "JOIN adoption_campaigns c ON c.id=b.campaign_id "
                                  "WHERE b.archived=0"),
    ("population_segment", "SELECT id, account_id, NULL, name AS title, "
                           "COALESCE(name,'')||' '||COALESCE(business_unit,'')||' '||COALESCE(region,'') AS body "
                           "FROM population_segments WHERE archived=0"),
    # --- Stage 7 ---------------------------------------------------------------------------
    ("calendar_event", "SELECT id, account_id, program_id, title, "
                       "COALESCE(title,'')||' '||COALESCE(purpose,'')||' '||COALESCE(location,'') AS body "
                       "FROM calendar_events WHERE archived=0"),
    ("org_change_flag", "SELECT id, account_id, NULL, summary AS title, "
                        "COALESCE(summary,'')||' '||COALESCE(kind,'')||' '||COALESCE(new_title,'')||' '||"
                        "COALESCE(new_company,'') AS body FROM org_change_flags WHERE archived=0"),
    ("signal_episode", "SELECT id, account_id, program_id, kind AS title, "
                       "COALESCE(explanation,'')||' '||COALESCE(held_reason,'') AS body "
                       "FROM signal_episodes WHERE status IN ('open','held')"),
    # --- Stage 7.5 -------------------------------------------------------------------------
    ("operational_agreement", "SELECT id,account_id,NULL,name AS title, "
                              "COALESCE(name,'')||' '||COALESCE(agreed_process,'')||' '||COALESCE(notes,'') AS body "
                              "FROM operational_agreements WHERE archived=0"),
    ("growth_plan_line", "SELECT id,account_id,NULL,name AS title, "
                         "COALESCE(name,'')||' '||COALESCE(notes,'') AS body "
                         "FROM growth_plan_lines WHERE archived=0"),
    # --- Stage 9 ---------------------------------------------------------------------------
    ("playbook_entry", "SELECT pe.id,pe.account_id,NULL,uc.name||' — '||pe.motion_run AS title, "
                       "uc.name||' '||pe.motion_run||' '||COALESCE(pe.evidence_summary,'')||' '||"
                       "COALESCE(pe.message_summary,'')||' '||COALESCE(pe.what_worked,'')||' '||"
                       "COALESCE(pe.what_differently,'') AS body FROM playbook_entries pe "
                       "JOIN use_cases uc ON uc.id=pe.use_case_id WHERE pe.archived=0"),
    ("internal_ask", "SELECT id,account_id,NULL,need AS title,COALESCE(need,'')||' '||COALESCE(success_condition,'') AS body FROM internal_asks WHERE archived=0"),
    ("product_feedback", "SELECT i.id,NULL,NULL,i.title,COALESCE(i.title,'')||' '||COALESCE(i.problem_statement,'') AS body FROM product_feedback_items i WHERE i.archived=0"),
    # --- Stage 10 internal operating layer -----------------------------------------------
    ("forecast_entry", "SELECT fe.id,fe.account_id,NULL,"
                       "COALESCE(o.name,c.version_label,'Forecast call') AS title,"
                       "fe.category||' '||COALESCE(fe.amount_rationale,'')||' '||"
                       "COALESCE(fe.probability_rationale,'')||' '||COALESCE(fe.unresolved_conditions,'')||' '||"
                       "COALESCE(fe.help_needed_note,'') AS body FROM forecast_entries fe "
                       "LEFT JOIN expansion_opportunities o ON o.id=fe.opportunity_id "
                       "LEFT JOIN contract_versions c ON c.id=fe.contract_version_id WHERE fe.archived=0"),
    ("account_review", "SELECT id,account_id,NULL,review_type||' review' AS title,"
                       "review_type||' '||status||' '||COALESCE(scheduled_on,'')||' '||COALESCE(held_on,'') AS body "
                       "FROM account_reviews WHERE archived=0"),
    ("operator_view", "SELECT id,account_id,NULL,'Operator point of view' AS title,body "
                      "FROM operator_views WHERE archived=0"),
    ("status_assessment", "SELECT id,account_id,NULL,dimension||' — '||value AS title,"
                          "COALESCE(rationale,'')||' '||COALESCE(recovery_action,'')||' '||"
                          "COALESCE(leadership_not_applicable_reason,'') AS body "
                          "FROM account_status_assessments WHERE archived=0"),
    ("internal_roster", "SELECT r.id,r.account_id,NULL,p.name||' — '||r.role AS title,"
                        "p.name||' '||r.role||' '||r.standing_responsibilities||' '||COALESCE(r.briefing_scope,'') AS body "
                        "FROM account_internal_roster r JOIN persons p ON p.id=r.person_id WHERE r.archived=0"),
    ("product_feedback_occurrence", "SELECT o.id,o.account_id,NULL,i.title AS title,"
                                    "i.title||' '||COALESCE(o.source_span,'')||' '||COALESCE(o.workaround,'')||' '||COALESCE(o.impact,'') AS body "
                                    "FROM product_feedback_occurrences o JOIN product_feedback_items i ON i.id=o.feedback_item_id WHERE o.archived=0"),
    ("escalation", "SELECT e.id,a.account_id,NULL,'Escalation — '||a.need AS title,"
                   "a.need||' '||e.severity||' '||e.path_type||' '||e.next_step||' '||COALESCE(e.resolution,'') AS body "
                   "FROM escalation_instances e JOIN internal_asks a ON a.id=e.ask_id WHERE e.archived=0"),
    ("generated_document", "SELECT id,account_id,program_id,title,COALESCE(title,'')||' '||COALESCE(body_markdown,'') AS body "
                           "FROM generated_documents WHERE status<>'discarded'"),
    ("copilot_run", "SELECT id,account_id,program_id,query_text AS title,"
                    "COALESCE(query_text,'')||' '||COALESCE(answer_markdown,'') AS body "
                    "FROM copilot_runs WHERE archived=0 AND status='completed'"),
]


def reindex(conn: sqlite3.Connection) -> int:
    with conn:
        conn.execute("DELETE FROM search_index")
        n = 0
        for object_type, select in _SOURCES:
            try:
                rows = conn.execute(select).fetchall()
            except sqlite3.OperationalError:
                continue  # a table from a not-yet-applied migration; skip
            for r in rows:
                conn.execute(
                    "INSERT INTO search_index (object_type, object_id, account_id, program_id, title, body) "
                    "VALUES (?,?,?,?,?,?)",
                    (object_type, r[0], r[1], r[2], (r[3] or "")[:200], r[4] or ""),
                )
                n += 1
    return n


def search(
    conn: sqlite3.Connection,
    q: str,
    limit: int = 30,
    *,
    account_id: str | None = None,
    program_id: str | None = None,
    record_types: list[str] | tuple[str, ...] | None = None,
) -> list[dict]:
    """Search inside an explicit SQL scope.

    The optional filters are part of the FTS query itself. Callers building an LLM context must
    never fetch a portfolio result set and trim it in application code; doing so would put the
    access boundary after retrieval. The unscoped default remains for the operator's global search.
    """
    q = (q or "").strip()
    if not q:
        return []
    reindex(conn)  # always fresh at this scale
    # Turn a plain query into a prefix MATCH so partial words hit; escape quotes.
    terms = [t.replace('"', '') for t in q.split() if t.strip()]
    if not terms:
        return []
    match = " ".join(f'"{t}"*' for t in terms)
    where = ["search_index MATCH ?"]
    params: list[object] = [match]
    if account_id is not None:
        where.append("account_id = ?")
        params.append(account_id)
    if program_id is not None:
        where.append("program_id = ?")
        params.append(program_id)
    clean_types = sorted({t for t in (record_types or []) if t})
    if clean_types:
        where.append(f"object_type IN ({','.join('?' for _ in clean_types)})")
        params.extend(clean_types)
    params.append(max(1, min(limit, 100)))
    try:
        rows = conn.execute(
            "SELECT object_type, object_id, account_id, program_id, title, "
            "snippet(search_index, 5, '[', ']', '…', 8) AS snip "
            f"FROM search_index WHERE {' AND '.join(where)} "
            "ORDER BY bm25(search_index), object_type, object_id LIMIT ?",
            tuple(params),
        ).fetchall()
    except sqlite3.OperationalError:
        return []
    names = {r["id"]: r["name"] for r in conn.execute("SELECT id, name FROM accounts")}
    return [
        {"object_type": r["object_type"], "object_id": r["object_id"], "account_id": r["account_id"],
         "account_name": names.get(r["account_id"]), "program_id": r["program_id"],
         "title": r["title"], "snippet": r["snip"]}
        for r in rows
    ]
