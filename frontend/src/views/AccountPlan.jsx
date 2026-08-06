/**
 * The account plan surface (ACCOUNT-PATH-SPEC.md §13.3–§13.5, §13.9).
 *
 * This is the operator's way into the planning layer. Before it, the nine routes in
 * `routers/playbooks.py` had no caller: a plan could be instantiated by a seed script and by
 * nothing else, so an account without one showed an empty readiness panel with no explanation and
 * no way in. That absence is the first thing this surface renders.
 *
 * What it writes: it starts a plan, and it applies an upgrade the operator has previewed. Both
 * state an *expectation* — when a condition is due — and neither asserts that anything happened.
 * There is no completion control anywhere on this surface, for the same reason the requirement
 * panel has none: readiness is a projection, and a tick here would be the stored second source of
 * truth `RELATIONSHIP-READINESS-SPEC.md` §2 forbids. Every state, freshness, and applicability word
 * on screen is copied from the readiness reading the server merged in.
 *
 * The stage grouping comes from `../planSetup.js` and partitions the server's order without
 * re-sorting it (§6: the client never re-ranks).
 */
import { useCallback, useEffect, useMemo, useState } from "react";
import { api } from "../api";
import { Btn, Card, Loading, SlideOver, fmtDate, useToast } from "../ui";
import {
  activePlanKeys, anchorRequirement, compatibilityReport, latestPerKey, openCount, planPresence,
  planStages, startableVersions, unmappedLegacy, upgradeOffers,
} from "../planSetup";
import { RequirementPanel, RequirementRow } from "./RequirementDetail";
import PlanTimeline from "./PlanTimeline";

function today() { return new Date().toISOString().slice(0, 10); }

/** Start a plan. The only fields are the three the API needs; nothing here is a state. */
function StartPlan({ accountId, programId, library, activeKeys, onStarted }) {
  const toast = useToast();
  const options = useMemo(
    () => latestPerKey(startableVersions(library, { hasProgram: !!programId, activeKeys })),
    [library, programId, activeKeys],
  );
  const [choice, setChoice] = useState(null);
  const [anchorDate, setAnchorDate] = useState("");
  const [busy, setBusy] = useState(false);
  const [kickoffDate, setKickoffDate] = useState(null);

  // Read the program's own kickoff date so the form can say whether the blank-date fallback is
  // actually available here, rather than offering it and failing on submit.
  useEffect(() => {
    if (!programId) { setKickoffDate(null); return undefined; }
    let live = true;
    api.program(programId)
      .then((p) => { if (live) setKickoffDate(p?.kickoff_date || null); })
      .catch(() => { if (live) setKickoffDate(null); });
    return () => { live = false; };
  }, [programId]);

  const selected = options.find((o) => `${o.key}:${o.version}` === choice) || options[0] || null;
  const anchor = anchorRequirement(selected, kickoffDate);
  const blocked = anchor.required && !anchorDate;

  if (!options.length) {
    return (
      <p className="rowmeta">
        {programId
          ? "Every program-scoped playbook is already active here."
          : "No account-scoped playbook is available to start. Select a program to plan its launch."}
      </p>
    );
  }

  async function start() {
    if (!selected) return;
    setBusy(true);
    try {
      await api.createPlanInstances(accountId, {
        playbook_key: selected.key,
        playbook_version: selected.version,
        program_id: programId || null,
        anchor_type: selected.defaultAnchor,
        // Left blank, the server resolves a kickoff anchor from the program's own kickoff date.
        // Sending an empty string instead of null would fail date validation.
        anchor_date: anchorDate || null,
      });
      toast("Plan started");
      onStarted?.();
    } catch (e) {
      toast(e.message, "err");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="aplan-start">
      <label className="aplan-field">
        <span>Playbook</span>
        <select value={choice ?? (selected ? `${selected.key}:${selected.version}` : "")}
          onChange={(e) => setChoice(e.target.value)}>
          {options.map((o) => (
            <option key={`${o.key}:${o.version}`} value={`${o.key}:${o.version}`}>
              {o.label} v{o.version}
            </option>
          ))}
        </select>
      </label>
      <label className="aplan-field">
        <span>{anchor.label}{anchor.required ? " (required)" : ""}</span>
        <input type="date" value={anchorDate} required={anchor.required}
          onChange={(e) => setAnchorDate(e.target.value)} />
      </label>
      <Btn variant="primary" onClick={start} disabled={busy || !selected || blocked}>
        {busy ? "Starting…" : "Start plan"}
      </Btn>
      {selected && (
        <p className="rowmeta aplan-start-note">
          Schedules {selected.requiredCount} required
          {selected.entryCount > selected.requiredCount
            && ` and ${selected.entryCount - selected.requiredCount} optional`}
          {" "}condition{selected.entryCount === 1 ? "" : "s"} from
          the {selected.defaultAnchor} date. Nothing is marked complete — a plan states when
          something is expected, not whether it has happened.
          {" "}{anchor.hint}
        </p>
      )}
    </div>
  );
}

/** The previewed diff. Applying is a separate, explicit act (§13.9). */
function UpgradePreview({ accountId, offer, onClose, onApplied }) {
  const toast = useToast();
  const [diff, setDiff] = useState(null);
  const [failed, setFailed] = useState(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    let live = true;
    api.previewPlanUpgrade(accountId, {
      playbook_key: offer.playbookKey, to_version: offer.toVersion,
      program_id: offer.programId,
    }).then((d) => { if (live) setDiff(d); })
      // Shown in the panel, not only as a toast: a toast leaves the slide-over reading
      // "Loading the upgrade diff…" forever, which says the request is still in flight.
      .catch((e) => { if (live) setFailed(e.message); });
    return () => { live = false; };
  }, [accountId, offer]);

  async function apply() {
    setBusy(true);
    try {
      await api.applyPlanUpgrade(accountId, {
        playbook_key: offer.playbookKey, to_version: offer.toVersion,
        program_id: offer.programId,
      });
      toast(`Upgraded to v${offer.toVersion}`);
      onApplied?.();
      onClose();
    } catch (e) {
      toast(e.message, "err");
    } finally {
      setBusy(false);
    }
  }

  const groups = diff ? [
    ["Added", diff.additions, (r) => `${r.label} — due ${fmtDate(r.due_date) || "no date"}`],
    ["Removed", diff.removals, (r) => r.label || r.requirement_key],
    ["Dates moved", diff.timing_changes,
      (r) => `${r.label}: ${fmtDate(r.from_due_date) || "no date"} → ${fmtDate(r.to_due_date) || "no date"}`],
    ["Necessity changed", diff.necessity_changes,
      (r) => `${r.label}: ${r.from_necessity} → ${r.to_necessity}`],
    ["Definition version changed", diff.definition_changes,
      (r) => `${r.label}: v${r.from_version} → v${r.to_version}`],
  ].filter(([, rows]) => rows && rows.length) : [];

  return (
    <SlideOver
      title={`Upgrade ${offer.playbookKey} v${offer.fromVersion} → v${offer.toVersion}`}
      onClose={onClose}
      footer={diff && (
        <Btn variant="primary" onClick={apply} disabled={busy}>
          {busy ? "Applying…" : `Apply v${offer.toVersion}`}
        </Btn>
      )}
    >
      {failed ? (
        <Card className="aplan-warn">
          <strong>The diff could not be read.</strong>
          <p className="rowmeta">{failed} Nothing has been changed.</p>
        </Card>
      ) : !diff ? <Loading what="the upgrade diff" /> : (
        <>
          {/* Named outright rather than left to be inferred from the removals list: an upgrade
              drops rows, and a dropped row takes its recorded tick with it. */}
          {diff.recorded_complete_at_risk?.length > 0 && (
            <Card className="aplan-warn">
              <strong>{diff.recorded_complete_at_risk.length} recorded tick
                {diff.recorded_complete_at_risk.length === 1 ? "" : "s"} will be dropped.</strong>
              <p className="rowmeta">
                These requirements leave the plan in v{offer.toVersion}, and the completion recorded
                against them goes with them: {diff.recorded_complete_at_risk.join(", ")}. The
                evidence in the underlying records is untouched.
              </p>
            </Card>
          )}
          {groups.length === 0
            ? <p className="rowmeta">v{offer.toVersion} schedules exactly what v{offer.fromVersion} does. Applying it changes nothing.</p>
            : groups.map(([title, rows, render]) => (
              <section key={title} className="aplan-diff-group">
                <h3>{title} <span className="rowmeta">({rows.length})</span></h3>
                <ul>{rows.map((r) => <li key={r.requirement_key}>{render(r)}</li>)}</ul>
              </section>
            ))}
          <p className="rowmeta">
            {diff.retained_keys?.length || 0} condition
            {diff.retained_keys?.length === 1 ? "" : "s"} carry over unchanged. Anchored to
            the {diff.anchor_type} date {fmtDate(diff.anchor_date)}.
          </p>
        </>
      )}
    </SlideOver>
  );
}

/** Legacy checklist items no requirement covers — the seam between the two standard-work systems. */
function LegacyItems({ accountId, payload, onRan }) {
  const toast = useToast();
  const [report, setReport] = useState(null);
  const [open, setOpen] = useState(false);
  const legacy = unmappedLegacy(payload);

  async function run(dryRun) {
    try {
      const r = await api.checklistCompatibility(accountId, { dry_run: dryRun });
      setReport(r);
      if (!dryRun) { toast("Compatibility mapping run"); onRan?.(); }
    } catch (e) { toast(e.message, "err"); }
  }

  const read = compatibilityReport(report);

  return (
    <Card className="aplan-legacy">
      <button className="aplan-disclosure" aria-expanded={open} onClick={() => setOpen((v) => !v)}>
        <span aria-hidden="true">{open ? "▾" : "▸"}</span>
        Legacy checklist items ({legacy.openCount} open of {legacy.total})
      </button>
      {open && (
        <>
          <p className="rowmeta">
            These came from the onboarding checklist and no playbook requirement maps to them. They
            carry a tick and a date and nothing else — no state, no freshness, no applicability —
            because a synthesised reading here would be a weaker second source beside the projection.
          </p>
          {/* Said before the buttons, not discovered afterwards from a larger number. The list
              above is the selected scope; the mapping route takes no program and works on the
              whole account, writing each item into its own scope. */}
          <p className="rowmeta">
            The list above is this scope. Mapping runs across the whole account and files each item
            in the scope it already belongs to.
          </p>
          {legacy.total === 0
            ? <p className="rowmeta">Every checklist item in this scope maps to a requirement.</p>
            : (
              <ul className="aplan-legacy-list">
                {legacy.items.map((i) => (
                  <li key={i.checklist_item_id}>
                    <span className={`state-mark ${i.status === "done" ? "ok" : "unknown"}`}
                      aria-hidden="true" />
                    <span className={i.status === "done" ? "aplan-legacy-done" : undefined}>
                      {i.label}
                    </span>
                    <span className="rowmeta">
                      {i.section?.replace(/_/g, " ")}
                      {i.due_date ? ` · due ${fmtDate(i.due_date)}` : ""}
                      {` · ${i.status}`}
                    </span>
                  </li>
                ))}
              </ul>
            )}
          <div className="aplan-actions">
            <Btn size="small" onClick={() => run(true)}>Preview mapping</Btn>
            <Btn size="small" onClick={() => run(false)} disabled={!read?.dryRun}>Run mapping</Btn>
          </div>
          {read && (
            <div className="aplan-compat">
              <p>{read.headline}</p>
              {read.notes.map((n) => (
                // The tone class is emitted only where a rule exists for it. A `tone-neutral` that
                // styles nothing is a class name that reads as a decision and makes none.
                <p key={n.key} className={n.tone === "warn" ? "rowmeta tone-warn" : "rowmeta"}>
                  <span className={`state-mark ${n.tone === "warn" ? "warn" : "neutral"}`}
                    aria-hidden="true" />
                  {n.text}
                </p>
              ))}
            </div>
          )}
        </>
      )}
    </Card>
  );
}

/**
 * One operational setup step from the merged launch standard (migration 0051).
 *
 * This is the one row on this surface that carries a completion control, and the distinction is the
 * point rather than an inconsistency. A gate item asks "did somebody do this?" — a question only an
 * operator can answer and nothing else records. A requirement asks "is this true of the
 * relationship?", which readiness answers from evidence, so a tick there would be the stored second
 * source of truth the projection rule forbids. The two are drawn differently for that reason: no
 * state badge here, no freshness, no applicability, because a gate item has none of them.
 *
 * `fills_field` items ask for a value as well as a tick. Ticking without supplying one is allowed
 * and writes nothing but the tick — the conversation happened even when nobody wrote down what it
 * produced, and inventing a value from a completion is exactly what the server refuses to do.
 */
function SetupRow({ item, onToggle }) {
  const [value, setValue] = useState("");
  const [busy, setBusy] = useState(false);
  const settled = item.gate_status === "passed" || item.gate_status === "waived";
  const field = item.fills_field?.split(".")[1]?.replace(/_/g, " ");

  async function toggle() {
    setBusy(true);
    try {
      await onToggle(item, { complete: !item.complete, fill_value: value || null });
      setValue("");
    } catch {
      // The caller has already said what went wrong. Keeping what was typed is this row's job:
      // nothing was written, so the operator should not have to type it a second time.
    } finally { setBusy(false); }
  }

  return (
    <div className="aplan-setup-row">
      <div className="aplan-setup-head">
        {/* A checkbox, not a status hue: this is an action control and the accent is for
            interaction. The label carries the meaning, so nothing here is colour-only. */}
        <label className="aplan-setup-tick">
          <input type="checkbox" checked={item.complete} disabled={busy || settled}
            onChange={toggle} />
          <span className={item.complete ? "aplan-setup-done" : undefined}>{item.description}</span>
        </label>
        <div className="spacer" />
        <span className="rowmeta">{item.gate_name}</span>
      </div>
      {item.detail && <p className="rowmeta">{item.detail}</p>}
      <div className="req-row-meta">
        <span className="rowmeta">Setup step</span>
        {item.due_date && <span className="rowmeta">Due {fmtDate(item.due_date)}</span>}
        {item.complete && item.completed_on && (
          <span className="rowmeta">Done {fmtDate(item.completed_on)}</span>
        )}
        {settled && <span className="rowmeta">Gate {item.gate_status}</span>}
      </div>
      {field && !item.complete && !settled && (
        <label className="aplan-field aplan-setup-fill">
          {/* The bare field name, because `.aplan-field > span` capitalizes every word and a
              sentence here rendered as "Record The Incumbent Note". The explanation is the
              placeholder's job. */}
          <span>{field}</span>
          <input value={value} onChange={(e) => setValue(e.target.value)}
            placeholder="Optional — ticking without this writes only the tick" />
        </label>
      )}
    </div>
  );
}

export default function AccountPlan({ accountId, programId, reloadKey, onChanged }) {
  const toast = useToast();
  const [payload, setPayload] = useState(null);
  const [library, setLibrary] = useState(null);
  const [failed, setFailed] = useState(null);
  const [tick, setTick] = useState(0);
  const [selected, setSelected] = useState(null);
  const [upgrade, setUpgrade] = useState(null);
  const [showSettled, setShowSettled] = useState(false);
  const [showStart, setShowStart] = useState(false);
  const now = today();

  const refresh = useCallback(() => { setTick((t) => t + 1); onChanged?.(); }, [onChanged]);

  useEffect(() => {
    if (!accountId) return undefined;
    let live = true;
    setPayload(null);
    setFailed(null);
    Promise.all([
      api.planInstances(accountId, programId || null),
      library ? Promise.resolve(library) : api.playbooks(),
    ]).then(([p, lib]) => {
      if (!live) return;
      setPayload(p);
      setLibrary(lib);
      // Held in state as well as toasted, for the reason D-172 recorded one level down in this
      // file: a toast comes and goes, and what it leaves behind is a spinner still asserting the
      // request is in flight. The tab has to be able to say the plan could not be read.
    }).catch((e) => { if (live) { setFailed(e.message); toast(e.message, "err"); } });
    return () => { live = false; };
    // `library` is intentionally not a dependency: it is fetched once and reused across scopes.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [accountId, programId, reloadKey, tick]);

  if (failed) {
    return (
      <Card className="aplan-warn">
        <strong>The plan could not be read.</strong>
        <p className="rowmeta">{failed} Nothing has been changed.</p>
        <div className="actions">
          <Btn size="small" onClick={() => setTick((t) => t + 1)}>Try again</Btn>
        </div>
      </Card>
    );
  }
  if (!payload || !library) return <Loading what="the plan" />;

  const presence = planPresence(payload);
  // Scope-exact, not every plan the payload carries. `list_plans` returns an account-wide plan
  // inside a program scope on purpose, and feeding those keys to the picker would suppress a
  // program playbook because an unrelated account one shares its key.
  const activeKeys = activePlanKeys(payload, programId);
  const offers = upgradeOffers(payload, library);
  const stages = planStages(payload, now);
  const open = openCount(payload, now);
  const hasSetup = (payload.setup_items || []).length > 0;

  // Rethrows after toasting. Swallowing the error resolved the row's `await`, which then cleared
  // the value the operator had typed into the fill field — losing their input on the one path where
  // they still need it, because nothing was written.
  async function toggleSetup(item, body) {
    try {
      await api.patchGateItem(item.gate_item_id, body);
      toast(body.complete ? "Setup step marked done" : "Setup step reopened");
      refresh();
    } catch (e) { toast(e.message, "err"); throw e; }
  }

  return (
    <div className="aplan-surface">
      <Card className="aplan-head">
        <div className="actions">
          <h2>Plan</h2>
          <div className="spacer" />
          {/* Two numbers, not one. A single "9 open" invites the reader to treat nine ticks as the
              way to clear it, and eight of them are conditions no tick can satisfy. */}
          {(presence.started || open.setup > 0) && (
            <span className="rowmeta">
              {open.requirements} condition{open.requirements === 1 ? "" : "s"} open
              {" · "}{open.setup} setup step{open.setup === 1 ? "" : "s"} open
            </span>
          )}
        </div>
        {presence.started ? (
          <ul className="aplan-instances">
            {presence.plans.map((p) => (
              <li key={p.id}>
                <strong>{p.playbook_key} v{p.playbook_version}</strong>
                <span className="rowmeta">
                  {p.program_id ? "program" : "account"} scope · anchored to
                  the {p.anchor_type} date {fmtDate(p.anchor_date)}
                </span>
                {p.excluded_requirements?.length > 0 && (
                  <span className="rowmeta">
                    {p.excluded_requirements.length} optional condition
                    {p.excluded_requirements.length === 1 ? "" : "s"} excluded at instantiation
                  </span>
                )}
              </li>
            ))}
          </ul>
        ) : (
          <p className="rowmeta">{presence.reason}</p>
        )}
        {/* Offered whether or not a plan is already listed, because the list and the picker answer
            different questions. The list shows what governs this scope — including an account-wide
            plan, which is in force inside a program too — while the picker asks what is left to
            start *here*. Reading the second off the first meant one account plan anywhere hid the
            control for every program on the account, and the reverse: whichever was started first
            locked out the other permanently, with no other route to the write. Collapsed when a
            plan already exists, so the common case stays quiet and the absence stays immediate. */}
        {presence.started ? (
          <>
            <button className="aplan-disclosure" aria-expanded={showStart}
              onClick={() => setShowStart((v) => !v)}>
              <span aria-hidden="true">{showStart ? "▾" : "▸"}</span>
              Start another plan {programId ? "for this program" : "for this account"}
            </button>
            {showStart && (
              <StartPlan accountId={accountId} programId={programId} library={library}
                activeKeys={activeKeys} onStarted={refresh} />
            )}
          </>
        ) : (
          <StartPlan accountId={accountId} programId={programId} library={library}
            activeKeys={activeKeys} onStarted={refresh} />
        )}
      </Card>

      {/* Primary, directly beneath the plan's identity: the first question on this tab is "where
          are we", and the stage cards below answer the second one, "what is owed now". It opens
          the same requirement panel the stage rows do, so there is one detail surface. */}
      <PlanTimeline payload={payload} today={now} onOpenCondition={setSelected} />

      {offers.map((offer) => (
        <Card key={offer.planId} className="aplan-upgrade">
          <div className="actions">
            <span>
              <strong>{offer.playbookKey}</strong> <span className="rowmeta">{offer.text}</span>
            </span>
            <div className="spacer" />
            <Btn size="small" onClick={() => setUpgrade(offer)}>Preview upgrade</Btn>
          </div>
          <p className="rowmeta">
            Versions do not retire each other. This plan stays on v{offer.fromVersion} until the
            diff is reviewed and applied.
          </p>
        </Card>
      ))}

      {/* Gated on whether there is anything to show, not on whether a plan exists. The two gates
          disagreed: requirements with no active plan were filed into dated horizons when a setup
          item happened to exist, and were announced but never listed when one did not. The head
          card above already says what governs the scope. */}
      {(presence.started || hasSetup || presence.requirementCount > 0) && stages.map((stage) => {
        const count = stage.rows.length + stage.setup.length;
        if (stage.key === "settled") {
          if (!count) return null;
          return (
            <Card key={stage.key} className="aplan-stage aplan-stage-settled">
              <button className="aplan-disclosure" aria-expanded={showSettled}
                onClick={() => setShowSettled((v) => !v)}>
                <span aria-hidden="true">{showSettled ? "▾" : "▸"}</span>
                {stage.title} ({count})
              </button>
              {showSettled && (
                <>
                  <p className="rowmeta">{stage.blurb}</p>
                  {stage.rows.map((row) => (
                    <RequirementRow key={row.instance_id} row={row} today={now}
                      onOpen={setSelected} />
                  ))}
                  {stage.setup.map((item) => (
                    <SetupRow key={item.gate_item_id} item={item} onToggle={toggleSetup} />
                  ))}
                </>
              )}
            </Card>
          );
        }
        // An empty horizon is only worth a line for the two that mean something: "nothing is
        // overdue" is information, "nothing is scheduled beyond 45 days" is noise.
        if (!count && !["overdue", "now"].includes(stage.key)) return null;
        return (
          <Card key={stage.key} className={`aplan-stage aplan-stage-${stage.key}`}>
            <div className="actions">
              <h3>{stage.title}</h3>
              <div className="spacer" />
              <span className="rowmeta">{count}</span>
            </div>
            <p className="rowmeta">{stage.blurb}</p>
            {count === 0 && <p className="rowmeta aplan-stage-clear">Nothing here.</p>}
            {stage.rows.map((row) => (
              <RequirementRow key={row.instance_id} row={row} today={now} onOpen={setSelected} />
            ))}
            {/* Setup steps sit under the conditions in the same horizon, in their own block. One
                reading order, two kinds of row — merging the arrays would force one status
                vocabulary onto both, and the weaker one always wins that. */}
            {stage.setup.length > 0 && (
              <div className="aplan-setup-group">
                {/* Just "Setup steps". The card title and blurb already state the horizon, and
                    repeating it here printed "due in this window" above the undated stage —
                    a heading asserting a date for rows that have none. */}
                <h4 className="rowmeta">Setup steps</h4>
                {stage.setup.map((item) => (
                  <SetupRow key={item.gate_item_id} item={item} onToggle={toggleSetup} />
                ))}
              </div>
            )}
          </Card>
        );
      })}

      <LegacyItems accountId={accountId} payload={payload} onRan={refresh} />

      {selected && (
        <RequirementPanel row={selected} accountId={accountId} coverage={payload.coverage}
          today={now} onClose={() => setSelected(null)} onChanged={refresh} />
      )}
      {upgrade && (
        <UpgradePreview accountId={accountId} offer={upgrade}
          onClose={() => setUpgrade(null)} onApplied={refresh} />
      )}
    </div>
  );
}
