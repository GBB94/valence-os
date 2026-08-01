import { useEffect, useState } from "react";
import { api } from "../api";
import { SegTabs, useToast, AgeChip, Empty, fmtDate } from "../ui";
import StakeholderGraph from "./StakeholderGraph";
import PersonCard from "./PersonCard";
import OrgChanges from "./OrgChanges";

// The People tab (Comprehensive Spec Part 3). Map is the existing stakeholder graph + coverage;
// the Stage-5 panels add the champion pipeline (§3.4), influence paths (§3.5), executive alignment
// (§3.8) and the role-based messaging library (§3.12). Meeting dynamics (§3.13) render on the
// person card and inside exec alignment.
const TABS = [["map", "Map"], ["champions", "Champions"], ["influence", "Influence"], ["exec", "Exec alignment"], ["changes", "Org changes"], ["messaging", "Messaging"]];
const LAYER_ORDER = ["executive", "economic", "operational", "technical_gating", "user_advocate"];
const LAYER_LABEL = { executive: "Executive", economic: "Economic", operational: "Operational", technical_gating: "Technical & gating", user_advocate: "User & advocate" };
const STAGES = ["identify", "develop", "validate", "arm", "maintain"];

export default function People({ accounts, accountId, setAccountId, reloadKey }) {
  const [sub, setSub] = useState("map");
  return (
    <div>
      <div style={{ marginBottom: 12 }}>
        <SegTabs tabs={TABS} value={sub} onChange={setSub} />
      </div>
      {sub === "map" && <StakeholderGraph accounts={accounts} accountId={accountId} setAccountId={setAccountId} reloadKey={reloadKey} />}
      {sub === "champions" && <Champions accountId={accountId} reloadKey={reloadKey} />}
      {sub === "influence" && <Influence accountId={accountId} reloadKey={reloadKey} />}
      {sub === "exec" && <ExecAlignment accountId={accountId} reloadKey={reloadKey} />}
      {sub === "changes" && <OrgChanges accountId={accountId} reloadKey={reloadKey} />}
      {sub === "messaging" && <Messaging />}
    </div>
  );
}

const sel = { height: 30, borderRadius: 6, border: "1px solid var(--line-strong)", padding: "0 8px", background: "var(--bg-surface)" };
const H = ({ children }) => <div className="rowmeta" style={{ textTransform: "uppercase", letterSpacing: ".04em", marginBottom: 6 }}>{children}</div>;

// --- §3.4 champion development pipeline --------------------------------------
function Champions({ accountId, reloadKey }) {
  const toast = useToast();
  const [pipe, setPipe] = useState(null);
  const [people, setPeople] = useState([]);
  const [tick, setTick] = useState(0);
  const [addPid, setAddPid] = useState("");
  const [card, setCard] = useState(null);

  const load = () => api.championPipeline(accountId).then(setPipe).catch((e) => toast(e.message, "err"));
  useEffect(() => { if (accountId) { load(); api.persons(accountId).then((ps) => setPeople(ps.filter((p) => p.affiliation === "client"))).catch(() => {}); } }, [accountId, reloadKey, tick]);
  if (!pipe) return <div className="subtle">Loading…</div>;

  const inPipeline = new Set(pipe.candidates.map((c) => c.person_id));
  const addable = people.filter((p) => !inPipeline.has(p.id) && !p.is_placeholder);

  const add = async () => {
    if (!addPid) return;
    try { await api.createChampion({ person_id: addPid, stage: "identify" }); setAddPid(""); toast("Candidate added"); setTick((t) => t + 1); }
    catch (e) { toast(e.message, "err"); }
  };
  const move = async (cand, stage) => {
    try { await api.patchChampion(cand.id, { stage }); toast(`→ ${stage}`); setTick((t) => t + 1); }
    catch (e) { toast(e.message, "err"); }
  };
  const logAdvocacy = async (cand) => {
    try { await api.createAdvocacyEvent({ person_id: cand.person_id, kind: "advocacy_without_us", occurred_on: new Date().toISOString().slice(0, 10), note: "Advocated for us without us in the room" }); toast("Advocacy logged"); setTick((t) => t + 1); }
    catch (e) { toast(e.message, "err"); }
  };

  return (
    <div>
      <div className="actions" style={{ marginBottom: 10 }}>
        <h1 style={{ margin: 0 }}>Champion pipeline</h1>
        <div className="spacer" />
        <select value={addPid} onChange={(e) => setAddPid(e.target.value)} style={sel}>
          <option value="">+ add candidate…</option>
          {addable.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
        </select>
        <button className="btn small primary" onClick={add} disabled={!addPid}>Add</button>
      </div>

      {pipe.single_thread_risk && (
        <div className="card" style={{ padding: 12, marginBottom: 12, borderLeft: "3px solid var(--status-warn)" }}>
          <strong style={{ color: "var(--status-warn)" }}>▲ Single-thread risk</strong>
          <div className="rowmeta" style={{ marginTop: 2 }}>
            {pipe.validated_count} validated champion{pipe.validated_count === 1 ? "" : "s"} — develop a second so the account isn't one relationship deep. A champion is only "validated" with a logged advocacy-without-us event.
          </div>
        </div>
      )}

      <div style={{ display: "grid", gridTemplateColumns: "repeat(5, 1fr)", gap: 8 }}>
        {STAGES.map((stage) => (
          <div key={stage} className="card" style={{ padding: 8 }}>
            <H>{stage} <span className="rowmeta">({pipe.counts[stage]})</span></H>
            {(pipe.by_stage[stage] || []).map((c) => (
              <div key={c.id} className="card" style={{ padding: 8, marginBottom: 6 }}>
                <div style={{ fontWeight: 600, fontSize: 13, cursor: "pointer" }} onClick={() => setCard(c.person_id)}>{c.person_name}</div>
                <div className="rowmeta">{c.person_title || "—"}</div>
                <div className="rowmeta" style={{ marginTop: 4, display: "flex", alignItems: "center", gap: 6 }}>
                  <span className={c.has_evidence ? "badge" : "badge"} style={{ borderColor: c.has_evidence ? "var(--status-ok)" : "var(--status-unknown)", color: c.has_evidence ? "var(--status-ok)" : "var(--ink-tertiary)" }}>
                    {c.has_evidence ? `● ${c.evidence_count} evidence` : "○ no evidence"}
                  </span>
                  {c.decay_alert && <span className="badge" style={{ borderColor: "var(--status-warn)", color: "var(--status-warn)" }}>◐ decay</span>}
                </div>
                <div style={{ display: "flex", gap: 4, marginTop: 6, flexWrap: "wrap" }}>
                  <select value={c.stage} onChange={(e) => move(c, e.target.value)} style={{ ...sel, height: 24, fontSize: 11, flex: 1 }}>
                    {STAGES.map((s) => <option key={s} value={s}>{s}</option>)}
                  </select>
                  {!c.has_evidence && <button className="btn small ghost" title="log advocacy-without-us to validate" onClick={() => logAdvocacy(c)}>+ev</button>}
                </div>
              </div>
            ))}
            {(pipe.by_stage[stage] || []).length === 0 && <div className="rowmeta" style={{ fontStyle: "italic" }}>—</div>}
          </div>
        ))}
      </div>
      <div className="rowmeta" style={{ marginTop: 8 }}>identify → develop → validate → arm → maintain. Validate and beyond require a logged advocacy-without-us event (the same evidence gate as coach-vs-champion).</div>
      {card && <PersonCard personId={card} onClose={() => setCard(null)} onChanged={() => setTick((t) => t + 1)} />}
    </div>
  );
}

// --- §3.5 influence paths ---------------------------------------------------
function Influence({ accountId, reloadKey }) {
  const toast = useToast();
  const [detail, setDetail] = useState(null);
  const [target, setTarget] = useState("");
  const [res, setRes] = useState(null);
  useEffect(() => { if (accountId) api.account(accountId).then(setDetail).catch(() => {}); }, [accountId, reloadKey]);
  useEffect(() => { if (accountId && target) api.influencePaths(accountId, target).then(setRes).catch((e) => toast(e.message, "err")); else setRes(null); }, [accountId, target]);

  const people = (detail?.people || []).filter((p) => p.affiliation === "client");
  const programs = detail?.programs || [];
  const createIntroTask = async (path) => {
    const pid = programs[0]?.id;
    if (!pid) { toast("Add a program first", "err"); return; }
    try { await api.createTask({ program_id: pid, description: path.action }); toast("Intro task created"); }
    catch (e) { toast(e.message, "err"); }
  };

  return (
    <div>
      <div className="actions" style={{ marginBottom: 10 }}>
        <h1 style={{ margin: 0 }}>Influence paths</h1>
        <div className="spacer" />
        <span className="rowmeta">path to:</span>
        <select value={target} onChange={(e) => setTarget(e.target.value)} style={sel}>
          <option value="">— pick a target —</option>
          {people.map((p) => <option key={p.id} value={p.id}>{p.name}{p.title ? ` · ${p.title}` : ""}</option>)}
        </select>
      </div>
      {!target && <div className="rowmeta">Pick someone you haven't met. The map finds the shortest credible warm-intro path — a two-hop path through strong relationships beats a one-hop through a weak one.</div>}
      {res && res.already_known && (
        <div className="card" style={{ padding: 14 }}>
          <strong>{res.target_name}</strong> — you already have a <span className="badge">{res.our_strength}</span> relationship. No intro needed.
        </div>
      )}
      {res && !res.already_known && (res.paths?.length ? res.paths.map((path, i) => (
        <div key={i} className="card" style={{ padding: 14, marginBottom: 8, borderLeft: i === 0 ? "3px solid var(--accent)" : undefined }}>
          <div style={{ display: "flex", alignItems: "center", gap: 6, flexWrap: "wrap", fontSize: 14 }}>
            {path.path.map((n, j) => (
              <span key={n.id} style={{ display: "flex", alignItems: "center", gap: 6 }}>
                <span style={{ fontWeight: j === 0 || j === path.path.length - 1 ? 600 : 400 }}>{n.name}</span>
                {j < path.path.length - 1 && <span className="rowmeta">→</span>}
              </span>
            ))}
          </div>
          <div className="rowmeta" style={{ marginTop: 4 }}>
            {path.hops} hop{path.hops === 1 ? "" : "s"} · via <strong>{path.seed_name}</strong> (<span className="badge">{path.seed_strength}</span> relationship){i === 0 ? " · best" : ""}
          </div>
          <div style={{ marginTop: 8, display: "flex", alignItems: "center", gap: 8 }}>
            <span style={{ fontSize: 13 }}>{path.action}</span>
            <button className="btn small primary" onClick={() => createIntroTask(path)}>Create task</button>
          </div>
        </div>
      )) : <Empty title="No path found">No relationship edges reach this person yet. Add reporting/influence edges on the map, or find a new thread.</Empty>)}
    </div>
  );
}

// --- §3.8 executive alignment -----------------------------------------------
function ExecAlignment({ accountId, reloadKey }) {
  const toast = useToast();
  const [align, setAlign] = useState(null);
  const [detail, setDetail] = useState(null);
  const [tick, setTick] = useState(0);
  const [vp, setVp] = useState(""); const [cp, setCp] = useState("");
  useEffect(() => { if (accountId) { api.execAlignment(accountId).then(setAlign).catch((e) => toast(e.message, "err")); api.account(accountId).then(setDetail).catch(() => {}); } }, [accountId, reloadKey, tick]);
  if (!align) return <div className="subtle">Loading…</div>;
  const valence = (detail?.people || []).filter((p) => p.affiliation === "valence");
  const clients = (detail?.people || []).filter((p) => p.affiliation === "client" && !p.is_placeholder);

  const addPairing = async () => {
    if (!vp || !cp) { toast("Pick both executives", "err"); return; }
    try { await api.createExecPairing({ account_id: accountId, valence_person_id: vp, client_person_id: cp }); setVp(""); setCp(""); toast("Pairing added"); setTick((t) => t + 1); }
    catch (e) { toast(e.message, "err"); }
  };

  return (
    <div>
      <h1 style={{ marginTop: 0 }}>Executive alignment</h1>
      <div className="card" style={{ marginBottom: 12 }}>
        <div className="card-h"><h3>Pairings</h3></div>
        {align.pairings.length === 0 ? <Empty title="No pairings yet">Pair a Valence executive with each senior client executive.</Empty> : (
          <table>
            <thead><tr><th>Valence owner</th><th>Client executive</th><th>Last exec touch</th><th>Next planned</th></tr></thead>
            <tbody>
              {align.pairings.map((p) => (
                <tr key={p.id}>
                  <td>{p.valence_name}</td>
                  <td>{p.client_name}<div className="rowmeta">{p.client_title || ""}</div></td>
                  <td>{p.last_touch ? <AgeChip date={p.last_touch} /> : <span className="rowmeta">none</span>}</td>
                  <td className="rowmeta">{p.next_touch_planned ? fmtDate(p.next_touch_planned) : "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
        <div style={{ display: "flex", gap: 6, padding: 10, alignItems: "center", flexWrap: "wrap", borderTop: "1px solid var(--line-hairline)" }}>
          <select value={vp} onChange={(e) => setVp(e.target.value)} style={sel}><option value="">Valence exec…</option>{valence.map((x) => <option key={x.id} value={x.id}>{x.name}</option>)}</select>
          <span className="rowmeta">↔</span>
          <select value={cp} onChange={(e) => setCp(e.target.value)} style={sel}><option value="">Client exec…</option>{clients.map((x) => <option key={x.id} value={x.id}>{x.name}</option>)}</select>
          <button className="btn small primary" onClick={addPairing}>Pair</button>
        </div>
      </div>

      <div className="card" style={{ padding: 14 }}>
        <H>Exposure — unpaired client executives ({align.exposure_count})</H>
        {align.unpaired_execs.length === 0 ? <div className="rowmeta">Every senior client executive is paired.</div> :
          align.unpaired_execs.map((e) => (
            <div key={e.person_id} className="rowmeta" style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
              <span><span className="dot warn" /> {e.name} · {e.title || (e.layer || "").replace(/_/g, " ")}</span>
              <span className="badge" style={{ borderColor: "var(--status-warn)", color: "var(--status-warn)" }}>no exec owner</span>
            </div>
          ))}
      </div>
    </div>
  );
}

// --- §3.12 role-based messaging library -------------------------------------
function Messaging() {
  const toast = useToast();
  const [entries, setEntries] = useState(null);
  const load = () => api.messagingLibrary().then((r) => setEntries(r.entries)).catch((e) => toast(e.message, "err"));
  useEffect(() => { load(); }, []);
  if (!entries) return <div className="subtle">Loading…</div>;
  const byLayer = {};
  entries.forEach((e) => { (byLayer[e.layer] ||= []).push(e); });

  return (
    <div>
      <h1 style={{ marginTop: 0 }}>Messaging library</h1>
      <div className="rowmeta" style={{ marginBottom: 12 }}>Per layer and role: the value proposition in their terms, proof points, objections + responses, and approved artifacts. Feeds the deck generator and the suggested-touch content.</div>
      {LAYER_ORDER.filter((l) => byLayer[l]).map((l) => (
        <div key={l} className="card" style={{ marginBottom: 10 }}>
          <div className="card-h"><h3>{LAYER_LABEL[l]}</h3></div>
          {byLayer[l].map((e) => (
            <div key={e.id} style={{ padding: 12, borderBottom: "1px solid var(--line-hairline)" }}>
              <div style={{ display: "flex", gap: 8, alignItems: "center", marginBottom: 4 }}>
                {e.role && <span className="badge">{e.role.replace(/_/g, " ")}</span>}
                <span className="badge" style={{ borderColor: "var(--data-muted)", color: "var(--ink-tertiary)" }}>{e.visibility_class.replace(/_/g, " ")}</span>
              </div>
              {e.value_prop && <div style={{ fontSize: 13, marginBottom: 4 }}>{e.value_prop}</div>}
              {e.proof_points && <div className="rowmeta"><strong>Proof:</strong> {e.proof_points}</div>}
              {e.objections && <div className="rowmeta"><strong>Objections:</strong> {e.objections}</div>}
              {e.artifacts_note && <div className="rowmeta"><strong>Artifacts:</strong> {e.artifacts_note}</div>}
            </div>
          ))}
        </div>
      ))}
      {entries.length === 0 && <Empty title="No messaging entries">Seed the playbook or add entries per layer.</Empty>}
    </div>
  );
}
