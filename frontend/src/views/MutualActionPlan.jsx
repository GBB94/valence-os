/**
 * The shared plan (ACCOUNT-PATH-SPEC.md §16.5) and the promotion preview that fills it (§16.4).
 *
 * Two documents live on this page and the boundary between them is structural, not stylistic.
 * `artifact` is the customer's document: the server projected it through an allowlist, and every
 * word rendered below comes from it unchanged. `diagnostics` is the operator's document: unshared
 * counts, withheld items and their reasons, the source manifest. Nothing crosses.
 *
 * The one thing this file must never grow is a derivation. There is no place here that computes a
 * status, decides what is safe, or re-reads a native record — §16.5 forbids serializing rows and
 * filtering them in the frontend, and the way to keep that true is to never have the rows.
 *
 * `PromotionPreview` is exported because promotion happens on the native item (the ledger), not
 * here. It renders the server's preview of one record so §16.4's step 2 sits between opening the
 * item and confirming, rather than being a sentence in a tooltip.
 */
import { useEffect, useState } from "react";
import { api } from "../api";
import { Card, Empty, Input, Loading, PageHeader, SlideOver, useToast, fmtDate } from "../ui";
import {
  isEmptyPlan, manifestSummary, previewVerdict, stampLine, staleSourceNote, statusChip,
  unsharedSummary, withheldSentence, withheldSummary,
} from "../sharedPlan";

/** One client-safe status, as a mark, a symbol, and a word. Never colour alone. */
function Status({ status }) {
  const chip = statusChip(status);
  return (
    <span className="plan-status">
      <span className={`state-mark ${chip.mark}`} aria-hidden="true" />
      <span className="plan-status-symbol" aria-hidden="true">{chip.symbol}</span>
      {chip.label}
    </span>
  );
}

function OwnerPair({ item }) {
  const both = [item.customer_owner, item.valence_owner].filter(Boolean);
  if (!both.length) return <span className="rowmeta">Not assigned</span>;
  return (
    <span className="plan-owners">
      {item.customer_owner && <span>{item.customer_owner}</span>}
      {item.customer_owner && item.valence_owner && <span className="rowmeta"> with </span>}
      {item.valence_owner && <span className="rowmeta">{item.valence_owner}</span>}
    </span>
  );
}

function ActionTable({ rows, caption }) {
  return (
    <table className="plan-table">
      <caption className="sr-only">{caption}</caption>
      <thead>
        <tr>
          <th scope="col">What</th>
          <th scope="col" style={{ width: "26%" }}>Owner</th>
          <th scope="col" className="num" style={{ width: "7rem" }}>Due</th>
          <th scope="col" style={{ width: "9rem" }}>Status</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((row) => (
          <tr key={`${row.kind}:${row.id}`}>
            <td>
              <div className="cell-title">{row.what}</div>
              {row.source && <div className="rowmeta">{row.source}</div>}
            </td>
            <td><OwnerPair item={row} /></td>
            <td className="rowmeta num">{row.due ? fmtDate(row.due) : "—"}</td>
            <td><Status status={row.client_status} /></td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

/** Joint actions, grouped by the milestone they sit under (§16.5). */
function MilestoneGroup({ group }) {
  return (
    <section className="plan-group">
      <div className="plan-group-h">
        <h4>{group.milestone}</h4>
        {/* The "Other agreed work" bucket is not a milestone and carries no status. Rendering the
            unknown treatment there would claim something could not be read, when in fact there was
            never anything to read. */}
        {group.client_status && <Status status={group.client_status} />}
        <div className="spacer" />
        {group.target_date && <span className="rowmeta mono">{fmtDate(group.target_date)}</span>}
      </div>
      {group.source && <div className="rowmeta plan-group-source">{group.source}</div>}
      {group.actions.length === 0
        ? <div className="rowmeta plan-group-empty">No shared actions under this milestone yet.</div>
        : <ActionTable rows={group.actions} caption={`Joint actions for ${group.milestone}`} />}
    </section>
  );
}

function ProgramBlock({ program }) {
  return (
    <Card className="plan-program">
      <div className="card-h"><h3>{program.name}</h3></div>
      {program.groups.map((group) => (
        <MilestoneGroup key={group.milestone_id || group.milestone} group={group} />
      ))}
      {program.requirements.length > 0 && (
        <section className="plan-group">
          <div className="plan-group-h"><h4>Agreed conditions</h4></div>
          <ActionTable rows={program.requirements} caption={`Agreed conditions for ${program.name}`} />
        </section>
      )}
    </Card>
  );
}

function SimpleBlock({ title, note, children }) {
  return (
    <Card className="plan-block">
      <div className="card-h"><h3>{title}</h3></div>
      {note && <div className="rowmeta">{note}</div>}
      {children}
    </Card>
  );
}

/**
 * §16.4 step 2 — exactly what a customer would see for this record, before it is promoted.
 *
 * The verdict comes from the server's own projection, so a record the plan would withhold cannot
 * be confirmed past a reassuring button here.
 */
export function PromotionPreview({ objectType, objectId, promoted, onClose, onDone }) {
  const toast = useToast();
  const [preview, setPreview] = useState(null);
  const [label, setLabel] = useState("");
  const [error, setError] = useState(null);
  const [saving, setSaving] = useState(false);
  const needsLabel = objectType === "requirement";

  useEffect(() => {
    let live = true;
    setPreview(null); setError(null);
    api.mapPromotionPreview(objectType, objectId, needsLabel ? label : undefined)
      .then((p) => { if (live) setPreview(p); })
      .catch((e) => { if (live) setError(e.message); });
    return () => { live = false; };
  }, [objectType, objectId, label, needsLabel]);

  const verdict = preview ? previewVerdict(preview) : null;
  const canConfirm = !promoted && verdict?.ok && (!needsLabel || label.trim());

  async function confirm(next) {
    setSaving(true);
    try {
      await api.mapPromote({
        object_type: objectType, object_id: objectId, client_visible: next,
        ...(needsLabel && next ? { client_label: label.trim() } : {}),
      });
      toast(next ? "Added to the shared plan" : "Removed from the shared plan");
      onDone?.();
      onClose();
    } catch (e) { toast(e.message, "err"); } finally { setSaving(false); }
  }

  return (
    <SlideOver
      title={promoted ? "Remove from the shared plan" : "Preview what the customer would see"}
      onClose={onClose}
      footer={
        <div className="actions">
          <div className="spacer" />
          <button className="btn ghost" onClick={onClose}>Cancel</button>
          {promoted
            ? <button className="btn" disabled={saving} onClick={() => confirm(false)}>Remove from plan</button>
            : <button className="btn primary" disabled={!canConfirm || saving} onClick={() => confirm(true)}>
                Confirm and share
              </button>}
        </div>
      }
    >
      {needsLabel && (
        <Input
          label="Label the customer will read"
          hint={"The internal wording of a readiness requirement is written for us. A shared plan "
            + "needs one written for them, and there is no default."}
          value={label}
          onChange={(e) => setLabel(e.target.value)}
          placeholder="e.g. Executive sponsor confirmed"
        />
      )}

      {error && <div className="rowmeta plan-withheld-reason">{error}</div>}
      {!preview && !error && <Loading what="preview" />}

      {preview && verdict && (
        <>
          <div className={`plan-verdict tone-${verdict.mark}`}>
            <div className="plan-verdict-h">
              <span className={`state-mark ${verdict.mark}`} aria-hidden="true" />
              <strong>{verdict.label}</strong>
            </div>
            {verdict.detail && <div className="rowmeta">{verdict.detail}</div>}
          </div>
          {verdict.ok && (
            <dl className="kv">
              <dt>What</dt><dd>{preview.what}</dd>
              <dt>Owner</dt><dd><OwnerPair item={preview} /></dd>
              <dt>Due</dt><dd className="mono">{preview.due ? fmtDate(preview.due) : "—"}</dd>
              <dt>Status</dt><dd><Status status={preview.client_status} /></dd>
              <dt>Source</dt><dd>{preview.source || "—"}</dd>
            </dl>
          )}
          <div className="rowmeta">
            Nothing else from this record travels. Notes, internal reasoning, evidence, and
            commercial detail stay where they are.
          </div>
        </>
      )}
    </SlideOver>
  );
}

/** The operator's half: what is not shared, what was held back, and what a saved copy would cite. */
function Diagnostics({ diagnostics }) {
  const unshared = unsharedSummary(diagnostics);
  const withheld = withheldSummary(diagnostics);
  const manifest = manifestSummary(diagnostics);
  const notes = (diagnostics || {}).notes || [];

  return (
    <Card className="plan-diagnostics">
      <div className="card-h">
        <h3>Not on this plan</h3>
        <div className="spacer" />
        <span className="rowmeta">Internal — never rendered into the shared document.</span>
      </div>
      {unshared
        ? <p className="plan-diag-line">{unshared}</p>
        : <p className="plan-diag-line rowmeta">Every native record in scope is either shared or closed.</p>}

      {withheld.length > 0 && (
        <div className="plan-withheld">
          <h4>Promoted but held back</h4>
          {withheld.map((group) => (
            <div key={group.key} className="plan-withheld-group">
              <ul>{group.items.map((item) => (
                <li key={`${item.kind}:${item.id}`}>
                  <span className="state-mark warn" aria-hidden="true" />
                  {item.label}
                </li>
              ))}</ul>
              <div className="rowmeta plan-withheld-reason">{withheldSentence(group.reason)}</div>
            </div>
          ))}
        </div>
      )}

      {manifest.length > 0 && (
        <div className="plan-manifest">
          <h4>Sources a saved copy would cite</h4>
          <div className="rowmeta">{manifest.map((row) => row.label).join(" · ")}</div>
        </div>
      )}

      {notes.length > 0 && (
        <ul className="plan-diag-notes">{notes.map((note, i) => <li key={i} className="rowmeta">{note}</li>)}</ul>
      )}
    </Card>
  );
}

export default function MutualActionPlan({ accounts, accountId, setAccountId, reloadKey }) {
  const toast = useToast();
  const [payload, setPayload] = useState(null);
  const [saving, setSaving] = useState(false);

  async function load() {
    if (!accountId) return;
    setPayload(null);
    try { setPayload(await api.accountMap(accountId)); } catch (e) { toast(e.message, "err"); }
  }
  useEffect(() => { load(); }, [accountId, reloadKey]);

  const artifact = payload?.artifact;

  async function copy() {
    try { await navigator.clipboard.writeText(artifact.markdown); toast("Copied to clipboard"); }
    catch { toast("Copy failed", "err"); }
  }

  async function saveDocument() {
    setSaving(true);
    try {
      const r = await api.mapSaveDocument(accountId);
      toast(`Saved as a draft with ${r.source_count} source${r.source_count === 1 ? "" : "s"}`);
    } catch (e) { toast(e.message, "err"); } finally { setSaving(false); }
  }

  if (!accounts.length) return <Empty title="No accounts yet">Create an account first.</Empty>;

  const empty = artifact ? isEmptyPlan(artifact) : false;
  const stale = artifact ? staleSourceNote(artifact) : null;

  return (
    <div className="plan-page">
      {/* The purpose sentence is the artifact's own opening line, not a page subtitle, so it sits
          below the header rather than inside it — sharing the header row squeezed the title into
          two lines and pushed the controls off the edge. */}
      <PageHeader
        title="Mutual action plan"
        eyebrow="CLIENT-FACING"
        meta={artifact ? stampLine(artifact) : null}
        className="plan-header"
      >
        {/* One cluster, so a wrap moves the whole control set rather than splitting the account
            picker away from the buttons that act on the account it picked. */}
        <div className="plan-actions">
          <select value={accountId || ""} onChange={(e) => setAccountId(e.target.value)}
                  className="plan-account-select" aria-label="Account">
            {accounts.map((a) => <option key={a.id} value={a.id}>{a.name}</option>)}
          </select>
          <button className="btn" onClick={load}>Refresh</button>
          <button className="btn" onClick={copy} disabled={!artifact || empty}>Copy markdown</button>
          <button className="btn primary" onClick={saveDocument} disabled={!artifact || empty || saving}>
            Save as draft
          </button>
        </div>
      </PageHeader>

      {artifact?.purpose && <p className="plan-purpose">{artifact.purpose}</p>}

      {!payload ? <Loading what="mutual action plan" /> : (
        <>
          {stale && (
            <div className="plan-stale">
              <span className="state-mark unknown" aria-hidden="true" />
              {stale}
            </div>
          )}

          {empty ? (
            <div className="placeholder">
              Nothing has been shared to this plan yet. Open a commitment, task, or milestone in the
              ledger and share it — the preview shows exactly what the customer would read first.
            </div>
          ) : (
            <div className="plan-body">
              {artifact.programs.map((program) => (
                <ProgramBlock key={program.program_id} program={program} />
              ))}

              {artifact.account_requirements.length > 0 && (
                <SimpleBlock title="Agreed conditions across the account">
                  <ActionTable rows={artifact.account_requirements}
                               caption="Agreed conditions across the account" />
                </SimpleBlock>
              )}

              {artifact.upcoming_milestones.length > 0 && (
                <SimpleBlock title="Confirmed upcoming milestones">
                  <table className="plan-table">
                    <caption className="sr-only">Confirmed upcoming milestones</caption>
                    <thead>
                      <tr>
                        <th scope="col">Milestone</th>
                        <th scope="col" style={{ width: "30%" }}>Program</th>
                        <th scope="col" className="num" style={{ width: "7rem" }}>Target</th>
                      </tr>
                    </thead>
                    <tbody>
                      {artifact.upcoming_milestones.map((m) => (
                        <tr key={`${m.program}:${m.name}:${m.target_date}`}>
                          <td className="cell-title">{m.name}</td>
                          <td className="rowmeta">{m.program || "—"}</td>
                          <td className="rowmeta num">{m.target_date ? fmtDate(m.target_date) : "—"}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </SimpleBlock>
              )}

              {artifact.growth_lines.length > 0 && (
                <SimpleBlock title="Agreed next steps on scope"
                             note="Each line is supported by its own signed or agreed record.">
                  <table className="plan-table">
                    <caption className="sr-only">Agreed next steps on scope</caption>
                    <thead>
                      <tr>
                        <th scope="col">Line</th>
                        <th scope="col" style={{ width: "22%" }}>Population</th>
                        <th scope="col" className="num" style={{ width: "6rem" }}>Seats</th>
                        <th scope="col" className="num" style={{ width: "7rem" }}>Ask by</th>
                      </tr>
                    </thead>
                    <tbody>
                      {artifact.growth_lines.map((line) => (
                        <tr key={line.id}>
                          <td>
                            <div className="cell-title">{line.name}</div>
                            {line.source && <div className="rowmeta">{line.source}</div>}
                          </td>
                          <td className="rowmeta">{line.population || "—"}</td>
                          <td className="rowmeta num">{line.seats ?? "—"}</td>
                          <td className="rowmeta num">{line.ask_date ? fmtDate(line.ask_date) : "—"}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </SimpleBlock>
              )}

              {artifact.pre_agreed_triggers.length > 0 && (
                <SimpleBlock title="Pre-agreed triggers"
                             note="What both sides already agreed would happen, and when.">
                  <ul className="plan-triggers">
                    {artifact.pre_agreed_triggers.map((t) => (
                      <li key={t.id}>
                        <div className="cell-title">{t.name}</div>
                        <div className="rowmeta">
                          {[t.authority === "contractual" ? "Contractual" : "Operational",
                            t.seat_band_min != null && t.seat_band_max != null
                              ? `${t.seat_band_min}–${t.seat_band_max} seats` : null,
                            t.effective_on ? `from ${fmtDate(t.effective_on)}` : null,
                            t.source].filter(Boolean).join(" · ")}
                        </div>
                        {t.agreed_process && <div className="plan-trigger-process">{t.agreed_process}</div>}
                      </li>
                    ))}
                  </ul>
                </SimpleBlock>
              )}

              {artifact.note && <div className="rowmeta plan-foot">{artifact.note}</div>}
            </div>
          )}

          <Diagnostics diagnostics={payload.diagnostics} />
        </>
      )}
    </div>
  );
}
