import { useEffect, useMemo, useRef, useState } from "react";

import { api } from "../api";
import { extractSpeakers, LENS_LABELS, sourceKindForFile, sourceParts } from "../coach";
import { measure } from "../measure";
import { commandProperties } from "../surfaces";
import { Surface } from "../Surface";
import { Badge, Btn, Card, Empty, Input, Loading, PageHeader, SegTabs, useToast } from "../ui";

const PILLAR_LABELS = {
  stakeholder_breadth: "Stakeholder breadth", champion_continuity: "Champion continuity",
  executive_sponsorship: "Executive sponsorship", quantified_value: "Quantified value",
  budget_owner: "Budget owner", active_expansion_plan: "Expansion plan",
};

export default function Coach({ accounts, nav, go }) {
  if (nav.coachView === "new") {
    return <NewReview accounts={accounts} nav={nav} go={go} />;
  }
  if (nav.coachView === "session" && nav.coachSessionId) {
    return <SessionReview key={nav.coachSessionId} sessionId={nav.coachSessionId}
      focusObservationId={nav.coachObservationId} accounts={accounts} go={go} />;
  }
  return <CoachHome accounts={accounts} go={go} />;
}

function startReview(go, entryPoint = "toolbar", accountId = null) {
  const properties = commandProperties("command.review_call", entryPoint);
  if (properties) measure()("command_invoked", properties);
  go({ dest: "coach", coachView: "new", coachAccountId: accountId || undefined });
}

function CoachHome({ go }) {
  const toast = useToast();
  const [data, setData] = useState(null);
  const [error, setError] = useState("");
  const [busyGoal, setBusyGoal] = useState(false);
  async function load() {
    try { setData(await api.coachingSessions()); setError(""); }
    catch (e) { setError(e.message); }
  }
  useEffect(() => { load(); }, []);
  async function completeFocus() {
    if (!data?.active_goal || busyGoal) return;
    setBusyGoal(true);
    try {
      await api.completeCoachingGoal(data.active_goal.id);
      toast("Focus completed");
      await load();
    } catch (e) { setError(e.message); }
    finally { setBusyGoal(false); }
  }
  const sessions = data?.sessions || [];
  return (
    <div className="content coach-page">
      <PageHeader eyebrow="Private workspace" title="Coach"
        subtitle="Turn one real moment into one behavior you can practice now.">
        <Btn variant="primary" onClick={() => startReview(go)}>Review a call</Btn>
      </PageHeader>
      {error && <div className="error">{error}</div>}
      <div className="coach-home-grid">
        <Surface surfaceKey="coach.home">{({ engage }) => (
          <Card className="coach-focus-card" spotlight>
            <div className="coach-card-kicker">Your current focus</div>
            {data?.active_goal ? <>
              <h2>{data.active_goal.headline}</h2>
              <p className="coach-lead">{data.active_goal.behavior}</p>
              <div className="coach-card-actions">
                <Btn variant="primary" onClick={() => {
                  engage("followed_link");
                  go({ dest: "coach", coachView: "session", coachSessionId: data.active_goal.session_id,
                    coachObservationId: data.active_goal.source_observation_id });
                }}>Practice this</Btn>
                <Btn variant="ghost" disabled={busyGoal} onClick={completeFocus}>
                  {busyGoal ? "Completing…" : "Mark complete"}
                </Btn>
                <Badge>{data.active_goal.skill_key.replaceAll("_", " ")}</Badge>
              </div>
            </> : <Empty title="Choose one behavior to work on">
              Review a call, mark the most useful observation, and Coach will keep it here—not turn it into a score.
              <div className="actions"><Btn onClick={() => { engage("opened"); startReview(go); }}>Start a review</Btn></div>
            </Empty>}
          </Card>
        )}</Surface>
        <Card className="coach-start-card" spotlight>
          <div className="coach-card-kicker">Two ways to improve</div>
          <button className="coach-path" onClick={() => startReview(go)}>
            <span className="coach-path-icon" aria-hidden="true">↗</span>
            <span><strong>Review a completed call</strong><small>Ground feedback in exact transcript moments.</small></span>
          </button>
          <button className="coach-path" onClick={() => go({ dest: "coach", coachView: "new", coachMode: "rehearsal" })}>
            <span className="coach-path-icon" aria-hidden="true">◇</span>
            <span><strong>Practice a line</strong><small>Run a private, text-first targeted rehearsal.</small></span>
          </button>
        </Card>
      </div>
      <Surface surfaceKey="coach.history">{({ engage }) => (
        <section className="coach-history">
          <div className="section-title-row"><div><div className="coach-card-kicker">Recent work</div><h2>Coaching history</h2></div>
            <span className="muted">{sessions.length} session{sessions.length === 1 ? "" : "s"}</span></div>
          {!data ? <Loading what="coaching history" /> : sessions.length === 0 ?
            <Empty title="No reviews yet">Your completed reviews and practice attempts will stay private here.</Empty> :
            <div className="coach-session-list">{sessions.map((session) => (
              <button key={session.id} className="coach-session-row" onClick={() => {
                engage("opened"); go({ dest: "coach", coachView: "session", coachSessionId: session.id });
              }}>
                <span className={`coach-mode-mark ${session.mode}`} aria-hidden="true" />
                <span className="coach-session-copy"><strong>{session.title}</strong>
                  <small>{session.latest_summary || (session.latest_status === "queued" ? "Waiting to analyze" : "Open session")}</small></span>
                <span className="coach-session-meta">{session.account_name || "Standalone"}<br />{session.call_date || session.created_at.slice(0, 10)}</span>
                <span aria-hidden="true">›</span>
              </button>
            ))}</div>}
        </section>
      )}</Surface>
    </div>
  );
}

function NewReview({ accounts, nav, go }) {
  const toast = useToast();
  const [config, setConfig] = useState(null);
  const [programs, setPrograms] = useState([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [mode, setMode] = useState(nav.coachMode === "rehearsal" ? "rehearsal" : "review");
  const [form, setForm] = useState({
    title: "", call_type: "account_kickoff", call_date: new Date().toISOString().slice(0, 10),
    intended_outcome: "", coaching_focus: "ownership_next_steps", text: "", source_kind: "paste",
    filename: null, account_id: nav.coachAccountId || "", program_id: nav.programId || "",
    interaction_id: nav.interactionId || "", coached_speaker_key: "", speaker_status: "unknown",
    reflection_worked: "", reflection_difficult: "", reflection_outcome: "", reflection_change: "",
  });
  useEffect(() => { api.coachingConfig().then(setConfig).catch((e) => setError(e.message)); }, []);
  useEffect(() => {
    if (!form.account_id) { setPrograms([]); return; }
    api.account(form.account_id).then((account) => setPrograms(account.programs || [])).catch(() => setPrograms([]));
  }, [form.account_id]);
  const speakers = useMemo(() => extractSpeakers(form.text), [form.text]);
  function set(key, value) { setForm((current) => ({ ...current, [key]: value })); }
  function chooseAccount(value) {
    setForm((current) => ({ ...current, account_id: value, program_id: "" }));
  }
  function changeMode(next) {
    setMode(next);
    if (next === "rehearsal") {
      // Standalone practice has no hidden account scope. Targeted practice created from a review
      // keeps lineage through its dedicated endpoint instead of smuggling scope through this form.
      setForm((current) => ({ ...current, account_id: "", program_id: "", interaction_id: "" }));
    }
  }
  function chooseSpeaker(value) {
    setForm((current) => ({ ...current, coached_speaker_key: value,
      speaker_status: value ? "confirmed_by_operator" : "unknown" }));
  }
  async function readFile(file) {
    if (!file) return;
    const kind = sourceKindForFile(file.name);
    if (!kind) { setError("Use a TXT, MD, VTT, or SRT transcript. Audio and document files are intentionally refused."); return; }
    if (config && file.size > config.max_source_bytes) { setError("That transcript is larger than the 1 MB limit."); return; }
    setError("");
    const text = await file.text();
    setForm((current) => ({ ...current, text, filename: file.name, source_kind: kind,
      coached_speaker_key: "", speaker_status: "unknown" }));
  }
  async function submit(engage) {
    setError(""); setBusy(true);
    try {
      const practice = mode === "rehearsal";
      const created = await api.createCoachingSession({
        ...form, mode, title: form.title || (practice ? "Standalone practice" : "Call review"),
        source_kind: practice ? "practice_transcript" : form.source_kind,
        speaker_status: practice ? "not_applicable" : form.speaker_status,
        coached_speaker_key: practice ? null : form.coached_speaker_key || null,
        account_id: practice ? null : form.account_id || null,
        program_id: practice ? null : form.program_id || null,
        interaction_id: practice ? null : form.interaction_id || null,
      });
      engage("edited");
      await api.runJobs();
      toast(practice ? "Practice analyzed" : "Call review ready");
      go({ dest: "coach", coachView: "session", coachSessionId: created.id });
    } catch (e) { setError(e.message); setBusy(false); }
  }
  return (
    <div className="content coach-page coach-new-page">
      <PageHeader eyebrow="Private by default" title={mode === "review" ? "Review a call" : "Practice a line"}
        subtitle="The source stays in Coach. Account facts move only through Proposal Review." />
      <SegTabs tabs={[["review", "Completed call"], ["rehearsal", "Standalone practice"]]}
        value={mode} onChange={changeMode} ariaLabel="Coaching mode" />
      <Surface surfaceKey="coach.intake">{({ engage }) => (
        <div className="coach-intake-layout">
          <main className="coach-form-stack">
            <Card className="coach-form-card" spotlight>
              <div className="coach-step"><span>1</span><div><h2>{mode === "review" ? "Add the call" : "Write the attempt"}</h2>
                <p>{mode === "review" ? "Paste a transcript or choose a supported text file." : "Type the line or short response you want to rehearse."}</p></div></div>
              <Input as="textarea" label={mode === "review" ? "Transcript or notes" : "Practice attempt"} required
                rows={12} value={form.text} onChange={(e) => set("text", e.target.value)}
                placeholder={mode === "review" ? "Zach: What would make this launch successful?\nAisha: …" : "Type exactly what you would say…"} />
              {mode === "review" && <div className="coach-file-row"><label className="btn small">
                Choose transcript<input className="sr-only" type="file" accept=".txt,.md,.vtt,.srt,text/plain,text/vtt"
                  onChange={(e) => readFile(e.target.files?.[0])} /></label>
                <span className="muted">{form.filename || "TXT · MD · VTT · SRT · 1 MB max"}</span></div>}
            </Card>
            <Card className="coach-form-card" spotlight>
              <div className="coach-step"><span>2</span><div><h2>Frame the work</h2><p>Coach needs the job of the call before judging a behavior.</p></div></div>
              <div className="form-grid two">
                <Input label="Title" value={form.title} onChange={(e) => set("title", e.target.value)}
                  placeholder={mode === "review" ? "Bluepeak onboarding call" : "Practice the close"} />
                {mode === "review" ? <Input as="select" label="Call type" value={form.call_type}
                  onChange={(e) => set("call_type", e.target.value)}>{(config?.call_types || []).map((item) =>
                    <option key={item.key} value={item.key}>{item.label}</option>)}</Input> :
                  <Input as="select" label="Skill to practice" value={form.coaching_focus}
                    onChange={(e) => set("coaching_focus", e.target.value)}>{(config?.skills || []).map((item) =>
                      <option key={item.key} value={item.key}>{item.label}</option>)}</Input>}
              </div>
              <Input as="textarea" label={mode === "review" ? "What did this call need to accomplish?" : "What should this attempt accomplish?"}
                required rows={3} value={form.intended_outcome} onChange={(e) => set("intended_outcome", e.target.value)} />
              {mode === "review" && <div className="form-grid two">
                <Input as="select" label="Which speaker is you?" value={form.coached_speaker_key}
                  onChange={(e) => chooseSpeaker(e.target.value)}>
                  <option value="">Unknown — content-only review</option>
                  {speakers.map((speaker) => <option key={speaker} value={speaker}>{speaker}</option>)}
                </Input>
                <Input label="Call date" type="date" value={form.call_date} onChange={(e) => set("call_date", e.target.value)} />
              </div>}
            </Card>
            {mode === "review" && <Card className="coach-form-card" spotlight>
              <div className="coach-step"><span>3</span><div><h2>Add context only if it belongs</h2>
                <p>Standalone is a complete path. Linking is your decision, never the transcript's.</p></div></div>
              <div className="form-grid two">
                <Input as="select" label="Account" value={form.account_id} onChange={(e) => chooseAccount(e.target.value)}>
                  <option value="">Standalone — no account</option>{accounts.map((a) => <option key={a.id} value={a.id}>{a.name}</option>)}
                </Input>
                <Input as="select" label="Program" value={form.program_id} disabled={!form.account_id}
                  onChange={(e) => set("program_id", e.target.value)}><option value="">All programs</option>
                  {programs.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}</Input>
              </div>
              {form.account_id && <div className="coach-boundary-note">
                Analysis stays private. After the review, you can separately log an Interaction or
                draft possible account facts—with a receipt for each action.
              </div>}
            </Card>}
            {mode === "review" && <details className="coach-reflection"><summary>Your reflection <span>optional</span></summary>
              <div className="form-grid two"><Input as="textarea" label="What worked?" rows={3} value={form.reflection_worked} onChange={(e) => set("reflection_worked", e.target.value)} />
                <Input as="textarea" label="What felt difficult?" rows={3} value={form.reflection_difficult} onChange={(e) => set("reflection_difficult", e.target.value)} />
                <Input as="textarea" label="What outcome did you see?" rows={3} value={form.reflection_outcome} onChange={(e) => set("reflection_outcome", e.target.value)} />
                <Input as="textarea" label="What would you change?" rows={3} value={form.reflection_change} onChange={(e) => set("reflection_change", e.target.value)} /></div>
            </details>}
          </main>
          <aside className="coach-submit-panel">
            <Card spotlight><div className="coach-card-kicker">Before analysis</div>
              <ul className="coach-trust-list"><li>Only your confirmed speaker is evaluated.</li><li>Every observation links to exact text.</li>
                <li>No overall grade, sentiment, or personality inference.</li><li>Practice never becomes an account event.</li></ul>
              {error && <div className="error">{error}</div>}
              <Btn variant="primary" disabled={busy || !form.text.trim() || !form.intended_outcome.trim()}
                onClick={() => submit(engage)}>{busy ? "Analyzing…" : mode === "review" ? "Review this call" : "Evaluate this attempt"}</Btn>
              <Btn variant="ghost" onClick={() => go({ dest: "coach", coachView: "home" })}>Cancel</Btn>
            </Card>
          </aside>
        </div>
      )}</Surface>
    </div>
  );
}

function SessionReview({ sessionId, focusObservationId, accounts, go }) {
  const toast = useToast();
  const [session, setSession] = useState(null);
  const [error, setError] = useState("");
  const [selected, setSelected] = useState(null);
  const [practiceFor, setPracticeFor] = useState(null);
  const [attempt, setAttempt] = useState("");
  const [linkAccount, setLinkAccount] = useState("");
  const [busy, setBusy] = useState(false);
  const [accountReceipt, setAccountReceipt] = useState(null);
  const routedPractice = useRef(null);
  async function load({ driveJobs = false } = {}) {
    try { if (driveJobs) await api.runJobs(); setSession(await api.coachingSession(sessionId)); }
    catch (e) { setError(e.message); }
  }
  useEffect(() => { load({ driveJobs: true }); }, [sessionId]);
  useEffect(() => {
    const status = session?.latest_run?.status;
    if (!["queued", "running"].includes(status)) return undefined;
    const timer = setTimeout(() => load({ driveJobs: true }), 700);
    return () => clearTimeout(timer);
  }, [session?.latest_run?.status]);
  useEffect(() => {
    if (!focusObservationId || !session || routedPractice.current === focusObservationId) return;
    const observation = session.runs?.flatMap((item) => item.observations || [])
      .find((item) => item.id === focusObservationId);
    routedPractice.current = focusObservationId;
    if (!observation) { setError("That coaching focus is no longer available in this review."); return; }
    setPracticeFor(observation);
    setAttempt(observation.alternative);
    requestAnimationFrame(() => document.getElementById("coach-practice-composer")?.scrollIntoView({ block: "center" }));
  }, [focusObservationId, session]);
  if (!session) return <div className="content"><Loading what="coaching review" />{error && <div className="error">{error}</div>}</div>;
  const run = session.latest_run;
  const observations = run?.observations || [];
  const top = observations.find((item) => item.is_top_priority);
  const strengths = observations.filter((item) => item.kind === "strength");
  const opportunities = observations.filter((item) => item.kind === "opportunity" && item.id !== top?.id);
  const isPractice = session.mode === "rehearsal";
  async function respond(item, response) {
    await api.respondCoachingObservation(item.id, { response }); toast("Response saved"); load();
  }
  async function activate(item) {
    await api.createCoachingGoal({ observation_id: item.id }); toast("Current focus updated"); load();
  }
  async function practice(item, engage) {
    if (!attempt.trim()) return;
    setBusy(true);
    try {
      engage("edited");
      const created = await api.createCoachingRehearsal(session.id, { origin_observation_id: item.id, attempt_text: attempt });
      await api.runJobs();
      go({ dest: "coach", coachView: "session", coachSessionId: created.id });
    } catch (e) { setError(e.message); setBusy(false); }
  }
  async function link() {
    if (!linkAccount) return;
    const preview = await api.previewCoachingLink(session.id, { account_id: linkAccount });
    if (!window.confirm(preview.consequences.join("\n"))) return;
    setBusy(true); await api.linkCoachingSession(session.id, { account_id: linkAccount }); await api.runJobs(); await load(); setBusy(false);
  }
  async function unlink() {
    const preview = await api.previewCoachingUnlink(session.id);
    if (!window.confirm(preview.survives.join("\n"))) return;
    await api.unlinkCoachingSession(session.id); load();
  }
  async function draft() {
    setBusy(true); setError("");
    try {
      const result = await api.draftCoachingAccountUpdates(session.id, run?.id);
      setAccountReceipt({ kind: "proposals", message: `${result.proposal_count} account draft${result.proposal_count === 1 ? "" : "s"} ready for review.`,
        runId: result.extraction_run_id });
      toast(result.note); await load();
    } catch (e) { setError(e.message); }
    finally { setBusy(false); }
  }
  async function logInteraction() {
    setBusy(true); setError("");
    try {
      const interaction = await api.logCoachingInteraction(session.id);
      setAccountReceipt({ kind: "interaction", message: "Interaction logged to the account.", id: interaction.id });
      toast("Interaction logged"); await load();
    } catch (e) { setError(e.message); }
    finally { setBusy(false); }
  }
  return (
    <div className="content coach-page coach-results">
      <PageHeader eyebrow={isPractice ? "Practice — not an account event" : "Private coaching review"}
        title={session.title} subtitle={session.intended_outcome}>
        <Btn variant="ghost" onClick={() => go({ dest: "coach", coachView: "home" })}>Coach home</Btn>
      </PageHeader>
      <SessionSurface practice={isPractice}>{(engage) => (
        <>
          <div className="coach-call-frame">
            <span><small>Call type</small>{session.call_type.replaceAll("_", " ")}</span>
            <span><small>Scope</small>{session.account?.name || "Standalone"}</span>
            <span><small>Coached speaker</small>{session.coached_speaker_key || (isPractice ? "Practice attempt" : "Unconfirmed · content only")}</span>
            <span><small>Source</small>{session.source?.snapshot_present ? `${session.source.source_kind} · retained locally` : "Source deleted"}</span>
          </div>
          {error && <div className="error">{error}</div>}
          {["queued", "running"].includes(run?.status) && <Card><Loading what="coaching analysis" /></Card>}
          {run?.status === "failed" && <Card><Empty title="Analysis did not complete">{run.error?.message || "The local analysis failed."}
            <div className="actions"><Btn onClick={async () => { await api.retryCoachingSession(session.id); load({ driveJobs: true }); }}>Retry</Btn></div></Empty></Card>}
          {isPractice && run?.practice && <PracticeResult run={run} session={session} go={go} engage={engage} />}
          {!isPractice && ["completed", "partial"].includes(run?.status) && <>
            <section className="coach-priority-section">
              <div className="coach-card-kicker">Start here</div>
              {top ? <Card className="coach-priority-card" spotlight>
                <div className="coach-priority-heading"><span className="coach-priority-number">01</span><div>
                  <Badge>{top.skill_key.replaceAll("_", " ")}</Badge><h2>{top.headline}</h2></div></div>
                <p className="coach-lead">{top.alternative}</p>
                <button className="coach-quote" onClick={() => { engage("opened"); setSelected(top); }}>
                  <span>“{top.source_span}”</span><small>Open exact moment →</small></button>
                <div className="coach-card-actions"><Btn variant="primary" onClick={() => { engage("followed_link"); setPracticeFor(top); setAttempt(top.alternative); }}>Practice this</Btn>
                  <Btn onClick={() => activate(top)}>Make this my focus</Btn>
                  <div className="spacer" /><FeedbackButtons item={top} respond={respond} /></div>
              </Card> : <Card><Empty title="No safe priority yet">The source did not contain enough attributable text to select a next behavior.</Empty></Card>}
            </section>
            {practiceFor && <Card id="coach-practice-composer" className="coach-practice-composer" spotlight>
              <div className="coach-card-kicker">Targeted practice</div><h2>Try the moment again</h2>
              <p className="muted">Only {practiceFor.skill_key.replaceAll("_", " ")} will be evaluated. This creates no Interaction or account evidence.</p>
              <Input as="textarea" label="What would you say?" rows={5} value={attempt} onChange={(e) => setAttempt(e.target.value)} />
              <div className="actions"><Btn variant="primary" disabled={busy || !attempt.trim()} onClick={() => practice(practiceFor, engage)}>{busy ? "Evaluating…" : "Evaluate attempt"}</Btn>
                <Btn variant="ghost" onClick={() => {
                  setPracticeFor(null);
                  if (focusObservationId) go({ dest: "coach", coachView: "session", coachSessionId: session.id });
                }}>Cancel</Btn></div>
            </Card>}
            <div className="coach-two-column">
              <ObservationGroup title="Keep doing" items={strengths} tone="strength" onOpen={(item) => { engage("opened"); setSelected(item); }} respond={respond} activate={activate} />
              <ObservationGroup title="Try next time" items={opportunities} tone="opportunity" onOpen={(item) => { engage("opened"); setSelected(item); }} respond={respond} activate={activate} />
            </div>
            {run.account_lens?.length > 0 && <AccountLens rows={run.account_lens} />}
            <Card className="coach-account-actions">
              <div><div className="coach-card-kicker">Account boundary</div><h2>Possible account updates</h2>
                <p>{session.account ? "Account facts stay drafts until you decide them in Proposal Review." : "This review is standalone. Link it only if the call genuinely belongs to an account."}</p></div>
              <div className="coach-card-actions">{session.account ? <>
                {!session.interaction_id && <Btn disabled={busy} onClick={logInteraction}>Log Interaction</Btn>}
                {!run.extraction_run_id && <Btn disabled={busy} onClick={draft}>Draft account updates</Btn>}
                {run.extraction_run_id && <Btn variant="primary" onClick={() => go({
                  dest: "account", accountId: session.account_id, tab: "ledger", section: "proposals",
                  programId: session.program_id || undefined, proposalRunId: run.extraction_run_id,
                })}>Open Proposal Review</Btn>}
                <Btn variant="ghost" onClick={unlink}>Unlink account</Btn>
              </> : <><select value={linkAccount} onChange={(e) => setLinkAccount(e.target.value)}><option value="">Choose account…</option>
                {accounts.map((a) => <option key={a.id} value={a.id}>{a.name}</option>)}</select><Btn disabled={!linkAccount || busy} onClick={link}>Link and reanalyze</Btn></>}</div>
              {accountReceipt && <div className="coach-account-receipt" role="status">✓ {accountReceipt.message}</div>}
            </Card>
          </>}
          <Card className="coach-source-control">
            <div><div className="coach-card-kicker">Source & privacy</div><h2>{session.source?.snapshot_present ? "Retained locally" : "Source text deleted"}</h2>
              <p>{session.source?.snapshot_present ? `${session.source.byte_length} bytes · ${run?.extractor_backend || "local"} backend · observations remain private.` : "Quoted spans remain, but surrounding context can no longer be reopened or reanalyzed."}</p></div>
            <div className="coach-card-actions">{session.source?.snapshot_present && <Btn variant="danger" onClick={async () => {
              if (!window.confirm("Delete the retained source text? Existing quoted spans remain, but context and reruns will be unavailable.")) return;
              await api.deleteCoachingSource(session.source.id); load();
            }}>Delete source text</Btn>}<Btn variant="ghost" onClick={async () => {
              if (!window.confirm("Archive this private coaching session?")) return;
              await api.archiveCoachingSession(session.id); go({ dest: "coach", coachView: "home" });
            }}>Archive session</Btn></div>
          </Card>
        </>
      )}</SessionSurface>
      {selected && <SourceMoment source={session.source?.snapshot_text} observation={selected} onClose={() => setSelected(null)} />}
    </div>
  );
}

function SessionSurface({ practice, children }) {
  if (practice) {
    return <Surface surfaceKey="coach.practice">{({ engage }) => children(engage)}</Surface>;
  }
  return <Surface surfaceKey="coach.review">{({ engage }) => children(engage)}</Surface>;
}

function FeedbackButtons({ item, respond }) {
  return <div className="coach-feedback" aria-label="Was this useful?">
    <button className={item.operator_response === "useful" ? "active" : ""} onClick={() => respond(item, "useful")}>Useful</button>
    <button className={item.operator_response === "inaccurate" ? "active" : ""} onClick={() => respond(item, "inaccurate")}>Inaccurate</button>
    <button className={item.operator_response === "dismissed" ? "active" : ""} onClick={() => respond(item, "dismissed")}>Dismiss</button>
  </div>;
}

function ObservationGroup({ title, items, tone, onOpen, respond, activate }) {
  return <section><div className="coach-card-kicker">{title}</div><div className="coach-observation-stack">
    {items.length === 0 ? <Card><span className="muted">No additional {tone === "strength" ? "strength" : "opportunity"} was needed.</span></Card> : items.map((item) =>
      <Card key={item.id} className={`coach-observation ${tone}`} spotlight><Badge>{item.skill_key.replaceAll("_", " ")}</Badge>
        <h3>{item.headline}</h3><p>{item.behavior}</p><p className="muted"><strong>Why it matters:</strong> {item.impact_text}</p>
        <button className="coach-inline-quote" onClick={() => onOpen(item)}>“{item.source_span}” <span>View moment</span></button>
        <div className="coach-card-actions"><Btn size="small" onClick={() => activate(item)}>Make focus</Btn><div className="spacer" /><FeedbackButtons item={item} respond={respond} /></div>
      </Card>)}</div></section>;
}

function PracticeResult({ run, session, go, engage }) {
  const practice = run.practice;
  const labels = { observed: "Behavior observed", partial: "Partly there", not_observed: "Try again", unable_to_assess: "Not enough to assess" };
  return <Card className="coach-practice-result" spotlight><div className="coach-card-kicker">Focused result</div>
    <div className="coach-practice-status"><span className={`coach-status-shape ${practice.result}`} aria-hidden="true" /><div><h2>{labels[practice.result]}</h2>
      <p>Evaluated only for <strong>{practice.target_behavior.replaceAll("_", " ")}</strong>.</p></div></div>
    <blockquote>“{practice.source_span}”</blockquote><div className="coach-next-adjustment"><small>One adjustment</small>{practice.adjustment}</div>
    <div className="actions">{session.parent_session_id && <Btn variant="primary" onClick={() => { engage("followed_link"); go({ dest: "coach", coachView: "session", coachSessionId: session.parent_session_id }); }}>Return to review</Btn>}
      <Btn onClick={() => go({ dest: "coach", coachView: "new", coachMode: "rehearsal" })}>New practice</Btn></div>
  </Card>;
}

function AccountLens({ rows }) {
  return <section className="coach-account-lens"><div className="coach-card-kicker">Account lens · coaching only</div><h2>What this call advanced—or left open</h2>
    <div className="coach-lens-grid">{rows.map((row) => <Card key={row.pillar_key} className={`coach-lens ${row.label}`}>
      <div className="coach-lens-head"><strong>{PILLAR_LABELS[row.pillar_key] || row.pillar_key}</strong><Badge>{LENS_LABELS[row.label] || row.label}</Badge></div>
      <p>{row.reason}</p>{row.source_span && <blockquote>“{row.source_span}”</blockquote>}
      <small>Current readiness: {row.current_readiness?.state || "not available"} · unchanged</small>
    </Card>)}</div>
  </section>;
}

function SourceMoment({ source, observation, onClose }) {
  const parts = sourceParts(source, observation);
  return <div className="modal-backdrop" role="presentation" onMouseDown={(e) => { if (e.target === e.currentTarget) onClose(); }}>
    <div className="modal coach-source-modal" role="dialog" aria-modal="true" aria-label="Exact source moment">
      <div className="modal-h"><div><div className="coach-card-kicker">Exact source moment</div><h2>{observation.headline}</h2></div><button className="iconbtn" onClick={onClose} aria-label="Close">×</button></div>
      <div className="coach-source-context">{source ? <>{parts.before}<mark>{parts.quote}</mark>{parts.after}</> : <><mark>{observation.source_span}</mark><p className="muted">The retained source was deleted, so surrounding context is unavailable.</p></>}</div>
      <div className="coach-source-analysis"><div><small>Behavior</small><p>{observation.behavior}</p></div><div><small>{observation.impact_type === "inferred" ? "Likely impact · inference" : "Observed impact"}</small><p>{observation.impact_text}</p></div><div><small>Try instead</small><p>{observation.alternative}</p></div></div>
    </div>
  </div>;
}
