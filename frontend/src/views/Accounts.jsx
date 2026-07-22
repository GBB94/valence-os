import { useState } from "react";
import { api } from "../api";
import { Empty, useToast } from "../ui";

export default function Accounts({ accounts, onOpen, onChanged }) {
  const toast = useToast();
  const [adding, setAdding] = useState(false);
  const [name, setName] = useState("");
  const [ctx, setCtx] = useState("");

  async function create() {
    if (!name.trim()) return;
    try {
      const a = await api.createAccount({ name: name.trim(), short_context: ctx || null });
      toast("Account created");
      setName(""); setCtx(""); setAdding(false);
      onChanged?.();
      onOpen(a.id);
    } catch (e) {
      toast(e.message, "err");
    }
  }

  return (
    <div>
      <div className="actions" style={{ marginBottom: 16 }}>
        <h1>Accounts</h1>
        <div className="spacer" />
        <button className="btn primary" onClick={() => setAdding((v) => !v)}>New account</button>
      </div>

      {adding && (
        <div className="card" style={{ padding: 14, marginBottom: 14 }}>
          <div className="grid2">
            <div className="field">
              <label>Name <span className="req">*</span></label>
              <input value={name} onChange={(e) => setName(e.target.value)} placeholder="Enterprise name (mock)" autoFocus />
            </div>
            <div className="field">
              <label>Short context</label>
              <input value={ctx} onChange={(e) => setCtx(e.target.value)} placeholder="One line" />
            </div>
          </div>
          <div className="actions">
            <button className="btn primary" onClick={create}>Create account</button>
            <button className="btn" onClick={() => setAdding(false)}>Cancel</button>
          </div>
        </div>
      )}

      <div className="card">
        {accounts.length === 0 ? (
          <Empty title="No accounts yet">Create your first account to start capturing.</Empty>
        ) : (
          <table>
            <thead>
              <tr><th>Account</th><th>Context</th><th style={{ width: 90 }}>Programs</th></tr>
            </thead>
            <tbody>
              {accounts.map((a) => (
                <tr key={a.id} className="clickable" onClick={() => onOpen(a.id)}>
                  <td><strong>{a.name}</strong></td>
                  <td className="subtle">{a.short_context || <span className="rowmeta">—</span>}</td>
                  <td className="rowmeta">{a.program_count ?? "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
