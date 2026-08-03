import { useState } from "react";
import { SlideOver, useToast } from "./ui";

export function SavedViewBar({ model, children }) {
  const toast = useToast();
  const [saving, setSaving] = useState(false);
  return (
    <>
      <div className="viewbar" role="group" aria-label="View and filters">
        <label className="view-picker">
          <span className="rowmeta">View</span>
          <select value={model.activeId} onChange={(event) => model.activate(event.target.value)}>
            {model.views.map((view) => <option key={view.id} value={view.id}>{view.label}</option>)}
          </select>
        </label>
        {model.modified && <span className="badge">Modified</span>}
        <button className="btn small" onClick={() => setSaving(true)}>Save view</button>
        {model.canDelete && <button className="btn small ghost" onClick={() => {
          if (model.remove(model.activeId)) toast("View deleted");
          else toast("This browser could not delete the view.", "err");
        }}>Delete view</button>}
        <div className="spacer" />
        {children}
      </div>
      {saving && <SaveViewPanel onClose={() => setSaving(false)} onSave={(name) => {
        const saved = model.save(name);
        if (saved) setSaving(false);
        return saved;
      }} />}
    </>
  );
}

function SaveViewPanel({ onClose, onSave }) {
  const toast = useToast();
  const [name, setName] = useState("");
  function save() {
    if (!name.trim()) { toast("Name the view before saving it.", "err"); return; }
    if (!onSave(name.trim())) { toast("This browser could not save the view.", "err"); return; }
    toast("View saved");
  }
  return (
    <SlideOver title="Save this view" onClose={onClose}
      footer={<><button className="btn" onClick={onClose}>Cancel</button><button className="btn primary" onClick={save}>Save view</button></>}>
      <div className="field">
        <label>View name <span className="req">*</span></label>
        <input value={name} maxLength={80} onChange={(event) => setName(event.target.value)} autoFocus placeholder="e.g. Commercial risk" />
      </div>
      <div className="hint">Saves the current filters in this browser. Account records are not copied.</div>
    </SlideOver>
  );
}
