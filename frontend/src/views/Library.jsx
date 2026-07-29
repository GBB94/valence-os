import { useEffect, useState } from "react";
import { api } from "../api";
import { SlideOver, Empty, useToast, fmtDate } from "../ui";

// Files & context library (Section 5O): link-first, searchable list of source references,
// each showing the records that cite it. Tags (§5O's last bit) need a schema field — held.
const TYPES = ["file", "transcript_span", "meeting", "crm_record", "data_report", "manual_entry"];
const TYPE_LABEL = { file: "file", transcript_span: "transcript", meeting: "meeting", crm_record: "CRM record", data_report: "data report", manual_entry: "manual entry" };

export default function Library({ reloadKey }) {
  const toast = useToast();
  const [q, setQ] = useState("");
  const [type, setType] = useState("");
  const [data, setData] = useState(null);
  const [adding, setAdding] = useState(false);
  const [tick, setTick] = useState(0);

  async function load() {
    try { setData(await api.library({ q, type })); } catch (e) { toast(e.message, "err"); }
  }
  useEffect(() => { const t = setTimeout(load, 160); return () => clearTimeout(t); }, [q, type, reloadKey, tick]);

  return (
    <div>
      <div className="actions" style={{ marginBottom: 12 }}>
        <h1>Files &amp; context</h1>
        <div className="spacer" />
        <button className="btn primary" onClick={() => setAdding(true)}>Add link</button>
      </div>
      <div className="actions" style={{ marginBottom: 12 }}>
        <input placeholder="Search files, links, accounts…" value={q} onChange={(e) => setQ(e.target.value)} style={{ flex: 1, maxWidth: 360, height: 30, borderRadius: 6, border: "1px solid var(--border-strong)", padding: "0 10px" }} />
        <select value={type} onChange={(e) => setType(e.target.value)} style={{ height: 30, borderRadius: 6, border: "1px solid var(--border-strong)", padding: "0 8px" }}>
          <option value="">all types</option>
          {TYPES.map((t) => <option key={t} value={t}>{TYPE_LABEL[t]}</option>)}
        </select>
      </div>
      <div className="rowmeta" style={{ marginBottom: 12 }}>Link-first: pointers to originals, not copies. Tagging arrives once we add a tags field (§5O).</div>

      <div className="card">
        {!data ? <div className="subtle" style={{ padding: 12 }}>Loading…</div> :
          data.sources.length === 0 ? <Empty title="No files yet">Add a link to a deck, transcript, or CRM record.</Empty> : (
          <table>
            <thead><tr><th>Label</th><th style={{ width: 110 }}>Type</th><th>Cited by</th><th style={{ width: 70 }}></th></tr></thead>
            <tbody>
              {data.sources.map((s) => (
                <tr key={s.id}>
                  <td>{s.label}{s.locator ? <span className="rowmeta"> · {s.locator}</span> : null}
                    {s.accounts.length ? <div className="rowmeta">{s.accounts.join(", ")}</div> : null}</td>
                  <td><span className="badge">{TYPE_LABEL[s.type] || s.type}</span></td>
                  <td className="rowmeta">
                    {s.citation_count === 0 ? "—" : s.citations.slice(0, 3).map((c, i) => (
                      <span key={i}>{i ? " · " : ""}<span className="badge" style={{ marginRight: 3 }}>{c.object_type}</span>{(c.label || "").slice(0, 24)}</span>
                    ))}
                    {s.citation_count > 3 && <span> +{s.citation_count - 3}</span>}
                  </td>
                  <td>{s.url ? <a href={s.url} target="_blank" rel="noreferrer">open ↗</a> : <span className="rowmeta">no link</span>}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {adding && <AddSource onClose={() => setAdding(false)} onSaved={() => { setAdding(false); setTick((t) => t + 1); }} />}
    </div>
  );
}

function AddSource({ onClose, onSaved }) {
  const toast = useToast();
  const [f, setF] = useState({ type: "file", label: "", url: "", locator: "" });
  const set = (k) => (e) => setF({ ...f, [k]: e.target.value });
  async function save() {
    if (!f.label.trim()) { toast("Label is required", "err"); return; }
    try { await api.createSourceReference({ type: f.type, label: f.label.trim(), url: f.url || null, locator: f.locator || null }); toast("Link added"); onSaved(); }
    catch (e) { toast(e.message, "err"); }
  }
  return (
    <SlideOver title="Add a link" onClose={onClose}
      footer={<><button className="btn" onClick={onClose}>Cancel</button><button className="btn primary" onClick={save}>Add</button></>}>
      <div className="field"><label>Type</label><select value={f.type} onChange={set("type")}>{TYPES.map((t) => <option key={t} value={t}>{TYPE_LABEL[t]}</option>)}</select></div>
      <div className="field"><label>Label <span className="req">*</span></label><input value={f.label} onChange={set("label")} placeholder="e.g. June steering deck" autoFocus /></div>
      <div className="field"><label>URL (link-first)</label><input value={f.url} onChange={set("url")} placeholder="https://…" /></div>
      <div className="field"><label>Locator</label><input value={f.locator} onChange={set("locator")} placeholder="e.g. slide 4, 00:12:30" /></div>
      <div className="hint">Link-first: point to the approved original location; don't upload copies.</div>
    </SlideOver>
  );
}
