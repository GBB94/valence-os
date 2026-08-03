import { useCallback, useEffect, useState } from "react";
import { api } from "../api";
import { AgeChip, Empty, Loading, useToast } from "../ui";

const emptyProfile = { legal_name: "", aliases: [], listing_status: "private", identifiers: [],
  watch_tier: "standard", source_include: [], source_exclude: [], topic_include: [], topic_exclude: [],
  languages: ["en"], cadence_days: 7, hiring_cluster_min: 5, hiring_window_days: 21,
  convergence_max_gap_days: 120 };

function Status({ value }) {
  const glyph = { proposed: "◇", confirmed: "●", dismissed: "×", invalidated: "!" }[value] || "○";
  return <span className="badge">{glyph} {String(value).replaceAll("_", " ")}</span>;
}

export default function CompanyIntel({ accountId, reloadKey, openCopilot }) {
  const toast = useToast();
  const [data, setData] = useState(null);
  const [busy, setBusy] = useState(false);
  const [editingWatch, setEditingWatch] = useState(false);
  const [tick, setTick] = useState(0);

  const load = useCallback(async () => {
    if (!accountId) return;
    try { setData(await api.companyWorkspace(accountId)); }
    catch (e) { toast(e.message, "err"); }
  }, [accountId, toast]);
  useEffect(() => { load(); }, [load, reloadKey, tick]);
  const refresh = () => setTick((n) => n + 1);

  async function act(fn, success) {
    setBusy(true);
    try { await fn(); toast(success); refresh(); }
    catch (e) { toast(e.message, "err"); }
    finally { setBusy(false); }
  }

  if (!data) return <Loading what="company intelligence" />;
  if (!data.company) return <ProfileSetup accountId={accountId} onSaved={refresh} />;
  const proposed = data.events.filter((e) => e.status === "proposed");
  const confirmed = data.events.filter((e) => e.status === "confirmed");

  return <div>
    <div className="card" style={{ padding: 16 }}>
      <div className="actions">
        <div>
          <h2 style={{ margin: 0 }}>{data.company.legal_name}</h2>
          <div className="rowmeta">{data.company.listing_status} · {data.watch?.watch_tier || "standard"} watch · span-cited public fixtures only</div>
        </div>
        <div className="spacer" />
        <button className="btn ghost" disabled={busy} onClick={() => act(() => api.evaluateCompanyIntel(accountId), "Convergence evaluated")}>Evaluate convergence</button>
        <button className="btn ghost" disabled={!confirmed.length} onClick={() => openCopilot?.("company_brief", "Give me the grounded company brief")}>Run company brief</button>
        <button className="btn ghost" onClick={() => setEditingWatch((v) => !v)}>Edit watch</button>
        <button className="btn" disabled={busy} onClick={() => act(() => api.syncCompanyIntel(), "Company fixtures synced")}>Sync public fixtures</button>
      </div>
      <div className="rowmeta" style={{ marginTop: 10 }}>
        Identity: {data.identifiers.length ? data.identifiers.map((x) => `${x.scheme}: ${x.value}`).join(" · ") : "no external identifier"}
      </div>
    </div>

    {editingWatch && <ProfileSetup accountId={accountId} initial={data} onSaved={() => { setEditingWatch(false); refresh(); }} />}

    {proposed.length > 0 && <div className="card">
      <div className="card-h"><h3>Review queue</h3><span className="badge">◇ {proposed.length} proposed</span></div>
      <div style={{ padding: 12 }} className="rowmeta">Proposed events are excluded from briefs, overlays, and convergence; Today shows only review debt for aging proposals.</div>
    </div>}

    <div className="card">
      <div className="card-h"><h3>Cited event feed</h3><div className="spacer" /><span className="rowmeta">{confirmed.length} confirmed · {proposed.length} awaiting review</span></div>
      {!data.events.length ? <Empty title="No public artifacts yet">Sync the mock boundary to load cited proposals.</Empty> :
        <div>{data.events.map((event) => <Event key={event.id} event={event} busy={busy} targets={data.map_targets}
          onConfirm={() => act(async () => {
            await api.confirmCompanyEvent(event.id, { actor: "operator" });
            const accountLink = event.links?.find((l) => l.account_target_id && l.status === "proposed");
            if (accountLink) await api.confirmCompanyEventLink(event.id, accountLink.id, { actor: "operator" });
          }, "Event and account link confirmed")}
          onDismiss={() => act(() => api.dismissCompanyEvent(event.id, { actor: "operator", reason: "Not relevant after operator review" }), "Event dismissed")}
          onChanged={refresh} />)}</div>}
    </div>

    <div className="card">
      <div className="card-h"><h3>Active convergence</h3></div>
      {!data.convergences.some((x) => x.status === "active") ? <div className="rowmeta" style={{ padding: 14 }}>No independently sourced target has two qualifying event kinds.</div> :
        data.convergences.filter((x) => x.status === "active").map((x) => <div key={x.id} style={{ padding: 16, borderTop: "1px solid var(--line-hairline)" }}>
          <div><span className="badge">◆ active</span> {x.target_kind}</div><div className="rowmeta" style={{ marginTop: 5 }}>{x.explanation}</div>
        </div>)}
    </div>

    <div className="card">
      <div className="card-h"><h3>Hiring facts</h3><div className="spacer" /><span className="rowmeta">posting-level, never a score</span></div>
      {!data.hiring.length ? <div className="rowmeta" style={{ padding: 14 }}>No active posting observations.</div> : data.hiring.map((p) =>
        <div key={p.id} style={{ padding: 16, borderTop: "1px solid var(--line-hairline)" }}>
          {p.title} <span className="badge">{p.state}</span><div className="rowmeta">{p.function_label} · {p.region_label} · last seen {p.last_seen_on} <AgeChip date={p.last_seen_on} /></div>
        </div>)}
    </div>

    <KeywordManager accountId={accountId} keywords={data.link_keywords || []}
      useCases={data.map_targets?.use_cases || []} onChanged={refresh} />
  </div>;
}

function KeywordManager({ accountId, keywords, useCases, onChanged }) {
  const toast = useToast();
  const [phrase, setPhrase] = useState("");
  const [useCase, setUseCase] = useState("");
  async function save() {
    if (!phrase.trim() || !useCase) return;
    try { await api.createCompanyLinkKeyword(accountId, { phrase: phrase.trim(), use_case_id: useCase }); setPhrase(""); toast("Governed mapping keyword added"); onChanged(); }
    catch (e) { toast(e.message, "err"); }
  }
  return <div className="card">
    <div className="card-h"><h3>Mapping vocabulary</h3><div className="spacer" /><span className="rowmeta">governed suggestions only</span></div>
    <div style={{ padding: 14 }}>
      <div className="actions"><input value={phrase} onChange={(e) => setPhrase(e.target.value)} placeholder="Public-language phrase" />
        <select value={useCase} onChange={(e) => setUseCase(e.target.value)}><option value="">Map to use case…</option>{useCases.map((row) => <option key={row.id} value={row.id}>{row.name}</option>)}</select>
        <button className="btn small" disabled={!phrase.trim() || !useCase} onClick={save}>Add keyword</button></div>
      <div className="rowmeta" style={{ marginTop: 8 }}>{keywords.length ? keywords.map((row) => `${row.phrase} → ${row.use_case_name}`).join(" · ") : "No keyword mappings yet."}</div>
    </div>
  </div>;
}

function Event({ event, busy, onConfirm, onDismiss, targets, onChanged }) {
  const evidence = event.evidence?.[0];
  const toast = useToast();
  const [target, setTarget] = useState("");
  async function addLink() {
    if (!target) return;
    const [kind, id] = target.split(":", 2);
    const field = { account: "account_target_id", segment: "segment_id", view: "view_id",
      use_case: "use_case_id", cell: "cell_id", person: "person_id" }[kind];
    try { await api.createCompanyEventLink(event.id, { [field]: id, rationale: "Operator mapped from Company workspace." }); toast("Map link proposed"); onChanged(); }
    catch (e) { toast(e.message, "err"); }
  }
  async function linkAction(link, action) {
    try {
      if (action === "confirm") await api.confirmCompanyEventLink(event.id, link.id, { actor: "operator" });
      else await api.dismissCompanyEventLink(event.id, link.id, { actor: "operator", reason: "Dismissed during mapping review" });
      toast(`Link ${action}ed`); onChanged();
    } catch (e) { toast(e.message, "err"); }
  }
  return <article style={{ padding: 16, borderTop: "1px solid var(--line-hairline)" }}>
    <div className="actions"><Status value={event.status} /><span className="badge">{event.direction === "contraction" ? "▼" : event.direction === "expansion" ? "▲" : "—"} {event.kind_label}</span><div className="spacer" />{event.occurred_on
      ? <span className="rowmeta">{event.occurred_on} <AgeChip date={event.occurred_on} /></span>
      : <span className="unknown-chip"><span className="unknown-hatch" aria-hidden="true" />date unknown</span>}</div>
    <div style={{ marginTop: 9 }}>{event.summary}</div>
    {evidence && <blockquote style={{ margin: "12px 0 0", padding: "8px 12px", borderLeft: "3px solid var(--line-strong)", background: "var(--bg-sunken)" }}>
      <div>“{evidence.excerpt}”</div>
      <div className="rowmeta" style={{ marginTop: 5 }}>{evidence.publisher} · {evidence.published_on
        ? <>{evidence.published_on} <AgeChip date={evidence.published_on} /></>
        : "publication date unknown"} · {evidence.locator}</div>
    </blockquote>}
    {event.status === "proposed" && <div className="actions" style={{ marginTop: 10 }}>
      <button className="btn small" disabled={busy} onClick={onConfirm}>Confirm event</button>
      <button className="btn small ghost" disabled={busy} onClick={onDismiss}>Dismiss</button>
    </div>}
    {event.status === "confirmed" && <div style={{ marginTop: 12 }}>
      <div className="rowmeta">Map links are separate proposals; they never edit whitespace facts.</div>
      {event.links?.filter((link) => link.status !== "dismissed").map((link) => <div className="actions" key={link.id} style={{ marginTop: 6 }}>
        <Status value={link.status} /><span className="rowmeta">{link.rationale}</span><div className="spacer" />
        {link.status === "proposed" && <><button className="btn small" onClick={() => linkAction(link, "confirm")}>Confirm link</button><button className="btn small ghost" onClick={() => linkAction(link, "dismiss")}>Dismiss</button></>}
      </div>)}
      <div className="actions" style={{ marginTop: 8 }}>
        <select value={target} onChange={(e) => setTarget(e.target.value)}>
          <option value="">Choose map target…</option>
          <option value={`account:${event.account_id}`}>Account-wide</option>
          {Object.entries(targets || {}).flatMap(([kind, rows]) => rows.map((row) =>
            <option key={`${kind}:${row.id}`} value={`${kind === "use_cases" ? "use_case" : kind === "people" ? "person" : kind.slice(0, -1)}:${row.id}`}>{kind.replace("_", " ")}: {row.name}</option>))}
        </select>
        <button className="btn small ghost" onClick={addLink} disabled={!target}>Propose link</button>
        <button className="btn small ghost" onClick={async () => { try { await api.suggestCompanyEventLinks(event.id); toast("Suggestions refreshed"); onChanged(); } catch (e) { toast(e.message, "err"); } }}>Suggest links</button>
      </div>
    </div>}
    {evidence && event.status !== "invalidated" && <div className="actions" style={{ marginTop: 8 }}>
      <button className="btn small ghost" disabled={busy} onClick={async () => {
        try { await api.retractIntelDocument(evidence.document_id, { actor: "operator", reason: "Retracted during source review" }); toast("Source retracted and derivatives reevaluated"); onChanged(); }
        catch (e) { toast(e.message, "err"); }
      }}>Retract source</button>
    </div>}
  </article>;
}

function ProfileSetup({ accountId, onSaved, initial }) {
  const toast = useToast();
  const current = initial?.watch ? { ...emptyProfile, ...initial.watch,
    legal_name: initial.company.legal_name, listing_status: initial.company.listing_status,
    hq_country: initial.company.hq_country, fiscal_year_end_month: initial.company.fiscal_year_end_month,
    aliases: initial.company.aliases || [], identifiers: (initial.identifiers || []).map(({ scheme, value, provider, jurisdiction }) => ({ scheme, value, provider, jurisdiction })) } : emptyProfile;
  const [form, setForm] = useState(current);
  const setCsv = (key, value) => setForm({ ...form, [key]: value.split(",").map((item) => item.trim()).filter(Boolean) });
  async function save() {
    if (!form.legal_name.trim()) return toast("Legal company name is required", "err");
    try { await api.putCompanyWatch(accountId, form); toast("Company identity and watch policy saved"); onSaved(); }
    catch (e) { toast(e.message, "err"); }
  }
  return <div className="card" style={{ padding: 16, maxWidth: 720 }}>
    <h2>Set up company intelligence</h2>
    <p className="subtle">Link this account to a canonical company before importing public artifacts. Identity is separate from the CRM account.</p>
    <label>Legal company name<input value={form.legal_name} onChange={(e) => setForm({ ...form, legal_name: e.target.value })} placeholder="Synthetic company name" /></label>
    <div className="actions" style={{ marginTop: 10 }}>
      <label style={{ flex: 1 }}>Listing status<select value={form.listing_status} onChange={(e) => setForm({ ...form, listing_status: e.target.value })}><option value="private">Private</option><option value="public">Public</option><option value="subsidiary">Subsidiary</option></select></label>
      <label style={{ flex: 1 }}>Watch tier<select value={form.watch_tier} onChange={(e) => setForm({ ...form, watch_tier: e.target.value })}><option value="standard">Standard</option><option value="elevated">Elevated</option><option value="paused">Paused</option></select></label>
    </div>
    <div className="actions" style={{ marginTop: 10 }}>
      <label>Cadence days<input type="number" min="1" value={form.cadence_days} onChange={(e) => setForm({ ...form, cadence_days: Number(e.target.value) })} /></label>
      <label>Hiring cluster minimum<input type="number" min="2" value={form.hiring_cluster_min} onChange={(e) => setForm({ ...form, hiring_cluster_min: Number(e.target.value) })} /></label>
      <label>Hiring window days<input type="number" min="1" value={form.hiring_window_days} onChange={(e) => setForm({ ...form, hiring_window_days: Number(e.target.value) })} /></label>
      <label>Convergence max gap<input type="number" min="1" value={form.convergence_max_gap_days} onChange={(e) => setForm({ ...form, convergence_max_gap_days: Number(e.target.value) })} /></label>
    </div>
    <div className="actions" style={{ marginTop: 10 }}>
      <label style={{ flex: 1 }}>Include source classes<input value={form.source_include.join(", ")} onChange={(e) => setCsv("source_include", e.target.value)} placeholder="earnings_call, press_release" /></label>
      <label style={{ flex: 1 }}>Exclude source classes<input value={form.source_exclude.join(", ")} onChange={(e) => setCsv("source_exclude", e.target.value)} placeholder="news_article" /></label>
    </div>
    <div className="actions" style={{ marginTop: 10 }}>
      <label style={{ flex: 1 }}>Include topics<input value={form.topic_include.join(", ")} onChange={(e) => setCsv("topic_include", e.target.value)} placeholder="strategic_initiative" /></label>
      <label style={{ flex: 1 }}>Exclude topics<input value={form.topic_exclude.join(", ")} onChange={(e) => setCsv("topic_exclude", e.target.value)} placeholder="funding_or_investment" /></label>
      <label style={{ flex: 1 }}>Languages<input value={form.languages.join(", ")} onChange={(e) => setCsv("languages", e.target.value)} placeholder="en" /></label>
    </div>
    <div className="actions" style={{ marginTop: 12 }}><button className="btn" onClick={save}>{initial ? "Save watch policy" : "Create company watch"}</button></div>
  </div>;
}
