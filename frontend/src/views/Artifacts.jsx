/* Stage 6 artifacts — generate, review, download (PHASE-3-SPEC.md Part 5).

   The screen is built around one rule from the spec: nothing is auto-sent. A generator
   produces a preview; saving makes a DRAFT; a human moves it to reviewed or sent. The status
   chip is therefore load-bearing rather than decoration, and "Send" records an operator
   assertion (this app transmits nothing) rather than performing one.

   Audience is shown on every artifact because the promotion rules differ by generator — the
   brief carries stances and never leaves the building; the champion kit is stricter than the
   QBR. A reader who cannot see which rule set produced a document cannot trust it. */
import { useEffect, useState } from "react";
import { api } from "../api";
import { AgeChip, Empty, Loading, SegTabs, SlideOver, useToast } from "../ui";

const KINDS = [
  ["pre_call_brief", "Pre-call brief", "Internal. Who is in the room, what is open, what to raise."],
  ["business_case", "Business case", "The day-75 artifact: the bar, the evidence, the funding, the ask."],
  ["value_review", "Value review", "The QBR's forward half: progress, gaps, and where value goes next."],
  ["champion_kit", "Champion kit", "For a champion to present without us. Strictest evidence rule."],
  ["kickoff_deck", "Kickoff deck", "Client-facing kickoff skeleton from the selected program."],
];
const STATUS = {
  draft:     { glyph: "○", hue: "--status-unknown", label: "Draft" },
  reviewed:  { glyph: "◐", hue: "--status-warn",    label: "Reviewed" },
  sent:      { glyph: "●", hue: "--status-ok",      label: "Sent" },
  discarded: { glyph: "✕", hue: "--status-risk",    label: "Discarded" },
};

export default function Artifacts({ accounts, accountId, programId, setAccountId, reloadKey }) {
  const toast = useToast();
  const [kind, setKind] = useState("business_case");
  const [preview, setPreview] = useState(null);
  const [docs, setDocs] = useState([]);
  const [open, setOpen] = useState(null);
  const [tick, setTick] = useState(0);
  const [roiOpen, setRoiOpen] = useState(false);

  const meta = KINDS.find((k) => k[0] === kind);

  async function load() {
    if (!accountId) return;
    try {
      const [p, d] = await Promise.all([
        api.generatePreview(kind, accountId, programId),
        api.documents({ accountId }),
      ]);
      setPreview(p); setDocs(d);
    } catch (e) { toast(e.message, "err"); }
  }
  useEffect(() => { load(); }, [accountId, programId, kind, reloadKey, tick]);

  if (!accounts.length) return <Empty title="No accounts yet">Create an account first.</Empty>;

  return (
    <div>
      <div className="actions" style={{ marginBottom: 14 }}>
        <h1>Artifacts</h1>
        <select value={accountId || ""} onChange={(e) => setAccountId(e.target.value)} style={sel}>
          {accounts.map((a) => <option key={a.id} value={a.id}>{a.name}</option>)}
        </select>
        <div className="spacer" />
      </div>

      <div style={{ marginBottom: 14 }}>
        <SegTabs tabs={KINDS.map(([k, l]) => [k, l])} value={kind} onChange={setKind} />
      </div>

      <div className="card" style={{ marginBottom: 14 }}>
        <div className="card-h">
          <h3>{meta[1]}</h3>
          <div className="spacer" />
          {preview && (
            <span className="rowmeta" style={{ marginRight: 10 }}>
              {preview.audience === "client_facing" ? "client-facing" : "internal only"}
            </span>
          )}
          {kind === "champion_kit" && (
            <button className="btn small" onClick={() => setRoiOpen(true)}>Edit ROI inputs</button>
          )}
          <button className="btn small primary" onClick={saveDraft}>Save as draft</button>
        </div>
        <div className="rowmeta" style={{ padding: "0 12px 8px" }}>{meta[2]}</div>

        {!preview ? <Loading what="artifact preview" /> : (
          <>
            {preview.stamp?.missing_or_stale_sources?.length > 0 && (
              <div style={gapBar} role="note">
                <span aria-hidden="true" style={{ color: "var(--status-warn)" }}>▲</span>{" "}
                <span className="rowmeta">
                  Known gaps: {preview.stamp.missing_or_stale_sources.join("; ")}
                </span>
              </div>
            )}
            <Markdown text={preview.markdown} style={md} />
            <div className="rowmeta" style={{ padding: "0 12px 12px" }}>
              Generated {preview.stamp.generated_at} · current through{" "}
              {preview.stamp.data_current_through || "unknown"}
            </div>
          </>
        )}
      </div>

      <div className="card">
        <div className="card-h">
          <h3>Drafts and sent</h3>
          <div className="spacer" />
          <span className="rowmeta">{docs.length} on file</span>
        </div>
        {docs.length === 0 ? (
          <Empty title="Nothing saved yet">
            Generating shows a preview; saving keeps a dated copy you can review and send.
          </Empty>
        ) : (
          <table>
            <thead><tr>
              <th scope="col">Document</th>
              <th scope="col" style={{ width: 120 }}>Audience</th>
              <th scope="col" style={{ width: 130 }}>Status</th>
              <th scope="col" style={{ width: 120 }}>Generated</th>
              <th scope="col" style={{ width: 170 }}></th>
            </tr></thead>
            <tbody>
              {docs.map((d) => {
                const st = STATUS[d.status] || STATUS.draft;
                return (
                  <tr key={d.id}>
                    <th scope="row" style={{ textAlign: "left", fontWeight: 500 }}>
                      {d.title}
                      {d.missing_or_stale_note && (
                        <div className="rowmeta">gaps at generation: {d.missing_or_stale_note}</div>
                      )}
                    </th>
                    <td className="rowmeta">
                      {d.audience === "client_facing" ? "client-facing" : "internal"}
                    </td>
                    <td>
                      <span aria-hidden="true" style={{ color: `var(${st.hue})`, marginRight: 5 }}>
                        {st.glyph}
                      </span>
                      {st.label}
                      {d.reviewed_by && <div className="rowmeta">{d.reviewed_by} · {d.reviewed_on}</div>}
                    </td>
                    <td className="rowmeta">
                      {(d.generated_at || "").slice(0, 10)}
                      <AgeChip date={(d.data_current_through || d.generated_at || "").slice(0, 10)} />
                    </td>
                    <td>
                      <div className="actions">
                        <button className="btn small ghost" onClick={() => setOpen(d)}>Open</button>
                        <a className="btn small ghost" href={api.documentPptxUrl(d.id)}>.pptx</a>
                        <a className="btn small ghost" href={api.documentPdfUrl(d.id)}>.pdf</a>
                        {d.status === "draft" && (
                          <button className="btn small" onClick={() => setOpen(d)}>Review</button>
                        )}
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
        <div className="rowmeta" style={{ padding: "8px 12px" }}>
          Nothing here is transmitted. Marking a document sent records that you sent it.
        </div>
      </div>

      {open && <DocPanel doc={open} onClose={() => setOpen(null)}
                         onChanged={() => { setOpen(null); setTick((t) => t + 1); }} />}
      {roiOpen && <RoiPanel accountId={accountId} onClose={() => setRoiOpen(false)}
                            onSaved={() => { setRoiOpen(false); setTick((t) => t + 1); }} />}
    </div>
  );

  async function saveDraft() {
    try {
      await api.saveDocument(accountId, { kind, program_id: programId || null });
      toast("Saved as draft");
      setTick((t) => t + 1);
    } catch (e) { toast(e.message, "err"); }
  }
}

export function DocPanel({ doc, onClose, onChanged }) {
  const toast = useToast();
  const [who, setWho] = useState("");
  const [title, setTitle] = useState(doc.title);
  const [body, setBody] = useState(doc.body_markdown);

  async function move(status) {
    if (status !== "discarded" && !who.trim()) {
      toast("Record who is reviewing or sending this", "err");
      return;
    }
    try {
      await api.setDocumentStatus(doc.id, { status, reviewed_by: who || null });
      toast(`Marked ${status}`);
      onChanged();
    } catch (e) { toast(e.message, "err"); }
  }

  async function saveEdits() {
    try {
      await api.patchDocument(doc.id, { title, body_markdown: body });
      toast("Draft updated"); onChanged();
    } catch (e) { toast(e.message, "err"); }
  }

  return (
    <SlideOver title={doc.title} onClose={onClose}>
      <div className="rowmeta" style={{ marginBottom: 10 }}>
        {doc.audience === "client_facing" ? "Client-facing" : "Internal only"} · generated{" "}
        {doc.generated_at} · current through {doc.data_current_through || "unknown"}
      </div>
      {doc.missing_or_stale_note && (
        <div style={gapBar}>
          <span aria-hidden="true" style={{ color: "var(--status-warn)" }}>▲</span>{" "}
          <span className="rowmeta">Gaps at generation: {doc.missing_or_stale_note}</span>
        </div>
      )}
      {doc.status === "draft" ? (
        <>
          <label style={lbl}>Title<input value={title} onChange={(e) => setTitle(e.target.value)} style={sel} /></label>
          <label style={lbl}>Markdown
            <textarea value={body} onChange={(e) => setBody(e.target.value)} rows={16} style={{ ...sel, fontFamily: "var(--font-mono)" }} />
          </label>
          <button className="btn small" onClick={saveEdits}>Save edits</button>
        </>
      ) : <Markdown text={doc.body_markdown} style={{ ...md, maxHeight: "45vh" }} />}

      {doc.status === "draft" ? (
        <>
          <label style={lbl}>Reviewed by
            <input value={who} onChange={(e) => setWho(e.target.value)} style={sel}
                   placeholder="your name" />
          </label>
          <div className="actions" style={{ marginTop: 8 }}>
            <button className="btn small" onClick={() => move("reviewed")}>Mark reviewed</button>
            <button className="btn small" onClick={() => move("sent")}>Mark sent</button>
            <button className="btn small ghost" onClick={() => move("discarded")}>Discard</button>
          </div>
        </>
      ) : doc.status === "reviewed" ? (
        <>
          <div className="rowmeta">Reviewed by {doc.reviewed_by} on {doc.reviewed_on}.</div>
          <div className="actions" style={{ marginTop: 8 }}>
            <button className="btn small" onClick={() => move("sent")}>Mark sent</button>
            <button className="btn small ghost" onClick={() => move("discarded")}>Discard</button>
          </div>
        </>
      ) : (
        <div className="rowmeta">
          {doc.status}{doc.reviewed_by ? ` by ${doc.reviewed_by} on ${doc.reviewed_on}` : ""}.
        </div>
      )}
    </SlideOver>
  );
}

function RoiPanel({ accountId, onClose, onSaved }) {
  const toast = useToast();
  const [spend, setSpend] = useState([]);
  const [f, setF] = useState({ seat_price: "", seat_price_currency: "EUR", seat_price_basis: "",
    retention_uplift_pct: "", retention_note: "", recovered_spend_id: "",
    assumptions_note: "", author: "", assessed_on: "" });
  useEffect(() => {
    Promise.all([api.roiModel(accountId), api.recoveredSpend(accountId)]).then(([model, rows]) => {
      setSpend(rows || []);
      if (model) setF(Object.fromEntries(Object.keys(f).map((k) => [k, model[k] ?? ""])));
    }).catch((e) => toast(e.message, "err"));
  }, [accountId]);
  const set = (k) => (e) => setF({ ...f, [k]: e.target.value });
  return <SlideOver title="Champion-kit ROI inputs" onClose={onClose}>
    <div className="rowmeta" style={{ marginBottom: 10 }}>Assumptions require an author and assessment date.</div>
    <form onSubmit={async (e) => {
      e.preventDefault();
      try {
        await api.putRoiModel(accountId, { ...f,
          seat_price: f.seat_price === "" ? null : Number(f.seat_price),
          retention_uplift_pct: f.retention_uplift_pct === "" ? null : Number(f.retention_uplift_pct),
          recovered_spend_id: f.recovered_spend_id || null });
        toast("ROI inputs saved"); onSaved();
      } catch (err) { toast(err.message, "err"); }
    }}>
      <label style={lbl}>Seat price<input type="number" step="any" value={f.seat_price} onChange={set("seat_price")} style={sel} /></label>
      <label style={lbl}>Currency<input value={f.seat_price_currency} onChange={set("seat_price_currency")} style={sel} /></label>
      <label style={lbl}>Price basis<input value={f.seat_price_basis} onChange={set("seat_price_basis")} style={sel} /></label>
      <label style={lbl}>Retention uplift %<input type="number" step="any" value={f.retention_uplift_pct} onChange={set("retention_uplift_pct")} style={sel} /></label>
      <label style={lbl}>Retention basis<textarea value={f.retention_note} onChange={set("retention_note")} rows={2} style={sel} /></label>
      <label style={lbl}>Recovered spend<select value={f.recovered_spend_id} onChange={set("recovered_spend_id")} style={sel}>
        <option value="">none</option>{spend.map((r) => <option key={r.id} value={r.id}>{r.label}</option>)}
      </select></label>
      <label style={lbl}>Assumptions note<textarea value={f.assumptions_note} onChange={set("assumptions_note")} rows={3} style={sel} /></label>
      <label style={lbl}>Author<input value={f.author} onChange={set("author")} required style={sel} /></label>
      <label style={lbl}>Assessed on<input type="date" value={f.assessed_on} onChange={set("assessed_on")} required style={sel} /></label>
      <button className="btn small primary" type="submit" style={{ marginTop: 8 }}>Save ROI inputs</button>
    </form>
  </SlideOver>;
}

/* A renderer for exactly the markdown our generators emit — headings, pipe tables, bullets,
   blockquotes, emphasis. Purpose-built rather than a dependency because we control both ends:
   the generators produce this subset and nothing else, and a general parser would be a lot of
   bytes to render six constructs. Tables render as semantic tables so the artifact reads the
   same way every other table in the app does. */
function Markdown({ text, style }) {
  const lines = (text || "").split("\n");
  const out = [];
  let i = 0, key = 0;

  const inline = (s) => {
    const parts = [];
    const rx = /\*\*(.+?)\*\*|(?<![A-Za-z0-9])_(.+?)_(?![A-Za-z0-9])/g;
    let last = 0, m;
    while ((m = rx.exec(s))) {
      if (m.index > last) parts.push(s.slice(last, m.index));
      parts.push(m[1]
        ? <strong key={parts.length}>{m[1]}</strong>
        : <em key={parts.length} style={{ color: "var(--ink-secondary)" }}>{m[2]}</em>);
      last = rx.lastIndex;
    }
    if (last < s.length) parts.push(s.slice(last));
    return parts;
  };

  while (i < lines.length) {
    const line = lines[i];
    if (!line.trim()) { i++; continue; }

    if (line.startsWith("| ")) {                       // table
      const rows = [];
      while (i < lines.length && lines[i].startsWith("|")) {
        const cells = lines[i].trim().replace(/^\||\|$/g, "").split("|").map((c) => c.trim());
        if (!cells.every((c) => /^-+$/.test(c))) rows.push(cells);
        i++;
      }
      const [head, ...body] = rows;
      out.push(
        <table key={key++} style={{ marginBottom: 14 }}>
          <thead><tr>{head.map((h, n) => <th key={n} scope="col">{h}</th>)}</tr></thead>
          <tbody>{body.map((r, n) => (
            <tr key={n}>{r.map((c, m2) => (
              m2 === 0
                ? <th key={m2} scope="row" style={{ textAlign: "left", fontWeight: 500 }}>{inline(c)}</th>
                : <td key={m2}>{inline(c)}</td>
            ))}</tr>
          ))}</tbody>
        </table>);
      continue;
    }
    if (line.startsWith("# ")) { out.push(<h3 key={key++} style={{ margin: "0 0 4px" }}>{line.slice(2)}</h3>); i++; continue; }
    if (line.startsWith("## ")) { out.push(<h4 key={key++} style={h4}>{line.slice(3)}</h4>); i++; continue; }
    if (line.startsWith("> ")) {
      out.push(<blockquote key={key++} style={quote}>{inline(line.slice(2))}</blockquote>); i++; continue;
    }
    if (line.startsWith("- ")) {                        // bullet run
      const items = [];
      while (i < lines.length && lines[i].startsWith("- ")) { items.push(lines[i].slice(2)); i++; }
      out.push(<ul key={key++} style={{ margin: "0 0 12px", paddingLeft: 18 }}>
        {items.map((it, n) => <li key={n} style={{ marginBottom: 3 }}>{inline(it)}</li>)}</ul>);
      continue;
    }
    out.push(<p key={key++} style={{ margin: "0 0 12px" }}>{inline(line)}</p>);
    i++;
  }
  return <div style={style}>{out}</div>;
}

const md = {
  padding: "16px", fontSize: "var(--t-body)", lineHeight: 1.55, color: "var(--ink-primary)",
  background: "var(--bg-sunken)", borderTop: "1px solid var(--line-hairline)",
  maxHeight: "55vh", overflow: "auto",
};
const quote = {
  margin: "0 0 12px", padding: "6px 12px", borderLeft: "3px solid var(--status-warn)",
  color: "var(--ink-secondary)", fontSize: 12,
};
const h4 = {
  margin: "20px 0 6px", fontSize: "var(--t-small)", textTransform: "uppercase", letterSpacing: ".04em",
  color: "var(--ink-tertiary)",
};
const gapBar = { padding: "8px 12px", borderBottom: "1px solid var(--line-hairline)" };
const lbl = { display: "flex", flexDirection: "column", gap: 4, marginTop: 12, fontSize: 13 };
const sel = {
  padding: "6px 8px", borderRadius: "var(--r-sm)",
  border: "1px solid var(--line-hairline)", background: "var(--bg-surface)",
  color: "var(--ink-primary)",
};
