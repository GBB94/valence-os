import { useEffect, useState } from "react";
import { api } from "../api";
import { Empty, useToast, fmtDate } from "../ui";

export default function Inbox({ reloadKey, onCountChange }) {
  const toast = useToast();
  const [items, setItems] = useState(null);

  async function load() {
    try {
      const rows = await api.inbox("untriaged");
      setItems(rows);
      onCountChange?.(rows.length);
    } catch (e) {
      toast(e.message, "err");
    }
  }
  useEffect(() => { load(); }, [reloadKey]);

  async function dismiss(id) {
    try {
      await api.dismissInbox(id);
      toast("Item dismissed");
      load();
    } catch (e) {
      toast(e.message, "err");
    }
  }

  if (!items) return <div className="subtle">Loading…</div>;

  return (
    <div>
      <div className="actions" style={{ marginBottom: 4 }}>
        <h1>Capture inbox</h1>
        <div className="spacer" />
        <span className="badge">{items.length} untriaged</span>
      </div>
      <div className="rowmeta" style={{ marginBottom: 14 }}>
        Untriaged notes stay here until resolved. Converting to a commitment / risk / task arrives in v0.2; for now you can dismiss non-actionable notes.
      </div>

      <div className="card">
        {items.length === 0 ? (
          <Empty title="Inbox clear">No untriaged notes. Capture drops ambiguous notes here.</Empty>
        ) : (
          <table>
            <thead>
              <tr><th style={{width:150}}>From</th><th>Note</th><th style={{width:70}}>Age</th><th style={{width:150}}></th></tr>
            </thead>
            <tbody>
              {items.map((it) => {
                const days = ageInDays(it.created_at);
                return (
                  <tr key={it.id}>
                    <td className="rowmeta">
                      {fmtDate(it.interaction?.occurred_on)}<br />
                      {it.interaction?.summary ? it.interaction.summary.slice(0, 30) + "…" : ""}
                    </td>
                    <td>{it.raw_text}</td>
                    <td className={days >= 3 ? "" : "rowmeta"}>
                      {days}d {days >= 3 && <span className="dot warn" title="aging" />}
                    </td>
                    <td>
                      <div className="actions">
                        <button className="btn small" disabled title="Arrives in v0.2">Convert</button>
                        <button className="btn small ghost" onClick={() => dismiss(it.id)}>Dismiss</button>
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}

function ageInDays(iso) {
  if (!iso) return 0;
  const then = new Date(iso).getTime();
  return Math.max(0, Math.floor((Date.now() - then) / 86400000));
}
