import { useEffect, useState } from "react";
import { api } from "../api";
import { Card, Empty, SegTabs, useToast } from "../ui";

const day = (offset = 0) => {
  const d = new Date();
  d.setDate(d.getDate() + offset);
  return d.toISOString().slice(0, 10);
};

export default function PortfolioInternal({ onOpen }) {
  const toast = useToast();
  const [section, setSection] = useState("overview");
  const [analytics, setAnalytics] = useState(null);
  const [periods, setPeriods] = useState([]);
  const [feedback, setFeedback] = useState([]);
  const [accounts, setAccounts] = useState([]);
  const [preview, setPreview] = useState(null);
  const [showPeriod, setShowPeriod] = useState(false);
  const [showFeedback, setShowFeedback] = useState(false);
  async function load() {
    const [a, p, f, ac, pr] = await Promise.all([
      api.internalAnalytics(),
      api.forecastPeriods(),
      api.productFeedback(),
      api.accounts(),
      api.monthlyInternalPreview(),
    ]);
    setAnalytics(a);
    setPeriods(p);
    setFeedback(f);
    setAccounts(ac);
    setPreview(pr);
  }
  // load is intentionally a one-shot portfolio snapshot; actions call reload explicitly.
  /* oxlint-disable react-hooks/exhaustive-deps -- initial portfolio snapshot; actions reload. */
  useEffect(() => {
    load().catch((e) => toast(e.message, "err"));
  }, []);
  /* oxlint-enable react-hooks/exhaustive-deps */
  async function monthly() {
    try {
      await api.generateMonthlyInternal();
      toast("Monthly portfolio draft generated");
      load();
    } catch (e) {
      toast(e.message, "err");
      load();
    }
  }
  return (
    <div className="stack">
      <div className="actions">
        <SegTabs
          tabs={[
            ["overview", "Overview"],
            ["forecast", "Forecast"],
            ["coverage", "Coverage"],
            ["feedback", "Feedback"],
          ]}
          value={section}
          onChange={setSection}
        />
        <div className="spacer" />
        <button className="btn primary" onClick={monthly}>
          Generate monthly brief
        </button>
      </div>
      {section === "overview" && (
        <Overview
          data={analytics}
          preview={preview}
          onOpen={onOpen}
          reload={load}
        />
      )}{" "}
      {section === "overview" && <Calibration data={analytics} />}{" "}
      {section === "forecast" && (
        <Forecast
          periods={periods}
          reload={load}
          show={showPeriod}
          setShow={setShowPeriod}
        />
      )}{" "}
      {section === "coverage" && <Coverage data={analytics} onOpen={onOpen} />}{" "}
      {section === "coverage" && <ExecCoverage data={analytics} />}{" "}
      {section === "feedback" && (
        <Feedback
          rows={feedback}
          accounts={accounts}
          reload={load}
          show={showFeedback}
          setShow={setShowFeedback}
        />
      )}{" "}
    </div>
  );
}

function Overview({ data, preview, onOpen, reload }) {
  if (!data)
    return (
      <Card>
        <div style={{ padding: 14 }}>Loading internal portfolio…</div>
      </Card>
    );
  const overdue = data.asks_by_function.reduce(
    (n, x) => n + x.past_needed_by,
    0,
  );
  return (
    <div className="stack">
      {preview && !preview.validation.valid && (
        <Card>
          <div className="card-h">
            <h3>Monthly brief blocked by no-surprises</h3>
          </div>
          <div style={{ padding: 12 }}>
            {preview.validation.blockers.map((b) => (
              <div className="actions" key={`${b.account_id}:${b.dimension}`}>
                <span>
                  <strong>
                    {b.account_name} · {b.dimension}
                  </strong>{" "}
                  — {b.reason}
                </span>
                <div className="spacer" />
                <button
                  className="btn small"
                  onClick={() => onOpen(b.account_id, "internal")}
                >
                  Create governed response
                </button>
              </div>
            ))}
          </div>
        </Card>
      )}
      {preview && (
        <RedOrigins validation={preview.validation} reload={reload} />
      )}
      <div className="grid3">
        <Metric
          label="Closed forecast periods"
          value={data.forecast_calibration.length}
        />
        <Metric label="Internal asks past needed-by" value={overdue} />
        <Metric label="Feedback themes" value={data.feedback_themes.length} />
      </div>
      <Card>
        <div className="card-h">
          <h3>Ask turnaround by function</h3>
        </div>
        {!data.asks_by_function.length ? (
          <Empty title="Insufficient data">
            No internal asks are recorded yet.
          </Empty>
        ) : (
          <table>
            <thead>
              <tr>
                <th>Function</th>
                <th>Open</th>
                <th>Past due</th>
                <th>Median acknowledgment</th>
                <th>Median resolution</th>
                <th>Samples</th>
              </tr>
            </thead>
            <tbody>
              {data.asks_by_function.map((r) => (
                <tr key={r.function_id}>
                  <td>{r.function_id}</td>
                  <td>{r.open}</td>
                  <td>{r.past_needed_by}</td>
                  <td>
                    {r.median_acknowledgment_hours == null
                      ? "Insufficient data"
                      : `${r.median_acknowledgment_hours}h`}
                  </td>
                  <td>
                    {r.median_resolution_days == null
                      ? "Insufficient data"
                      : `${r.median_resolution_days}d`}
                  </td>
                  <td>
                    {r.acknowledged_count} ack · {r.delivered_count} delivered
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Card>
      <Card>
        <div className="card-h">
          <h3>Escalation hygiene</h3>
        </div>
        {!data.escalations.length ? (
          <Empty title="Insufficient data">
            No escalations are recorded yet.
          </Empty>
        ) : (
          <table>
            <thead>
              <tr>
                <th>Severity / path</th>
                <th>Function</th>
                <th>Open</th>
                <th>Resolved</th>
                <th>Median hours</th>
              </tr>
            </thead>
            <tbody>
              {data.escalations.map((r) => (
                <tr key={`${r.severity}:${r.path_type}:${r.function_id}`}>
                  <td>
                    {r.severity} · {r.path_type}
                  </td>
                  <td>{r.function_id}</td>
                  <td>{r.open}</td>
                  <td>{r.resolved_count}</td>
                  <td>
                    {r.median_resolution_hours == null
                      ? "Insufficient data"
                      : r.median_resolution_hours.toFixed(1)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Card>
      <Card>
        <div className="card-h">
          <h3>Review commitment completion</h3>
        </div>
        {!data.review_commitments.length ? (
          <Empty title="Insufficient data">
            No two-way internal review commitments yet.
          </Empty>
        ) : (
          <table>
            <thead>
              <tr>
                <th>Direction</th>
                <th>Open</th>
                <th>Closed</th>
                <th>Completion</th>
                <th>On time</th>
              </tr>
            </thead>
            <tbody>
              {data.review_commitments.map((r) => (
                <tr key={r.commitment_class}>
                  <td>{r.commitment_class.replaceAll("_", " ")}</td>
                  <td>{r.open}</td>
                  <td>{r.closed}</td>
                  <td>
                    {r.completion_fraction}
                    {r.completion_rate == null
                      ? " · Insufficient data"
                      : ` · ${Math.round(r.completion_rate * 100)}%`}
                  </td>
                  <td>
                    {r.on_time_rate == null
                      ? "Insufficient data"
                      : `${Math.round(r.on_time_rate * 100)}%`}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Card>
    </div>
  );
}

function RedOrigins({ validation, reload }) {
  const toast = useToast();
  const [selected, setSelected] = useState(null);
  const [reason, setReason] = useState("");
  const [expiresOn, setExpiresOn] = useState(day(30));
  const origins = validation.included_red_origins || [];
  const excluded = validation.excluded_red_origins || [];
  if (!origins.length && !excluded.length) return null;
  async function exclude() {
    try {
      await api.excludeInternalReportOrigin({
        origin_type: selected.type,
        origin_id: selected.id,
        reason,
        expires_on: expiresOn,
      });
      toast("Typed report exclusion recorded");
      setSelected(null);
      setReason("");
      reload();
    } catch (e) {
      toast(e.message, "err");
    }
  }
  return (
    <Card>
      <div className="card-h">
        <h3>Report-eligible red origins</h3>
      </div>
      <table>
        <thead>
          <tr>
            <th>Account</th>
            <th>Origin</th>
            <th>Treatment</th>
          </tr>
        </thead>
        <tbody>
          {origins.map((o) => (
            <tr key={`${o.type}:${o.id}`}>
              <td>{o.account_name}</td>
              <td>
                <strong>{o.label}</strong>
                <div className="rowmeta">
                  {o.type} · {o.id}
                </div>
              </td>
              <td>
                <button className="btn small" onClick={() => setSelected(o)}>
                  Record exclusion
                </button>
              </td>
            </tr>
          ))}
          {excluded.map((x) => (
            <tr key={x.exclusion.id}>
              <td>{x.origin.account_name}</td>
              <td>{x.origin.label}</td>
              <td>
                Excluded through {x.exclusion.expires_on}
                <div className="rowmeta">{x.exclusion.reason}</div>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {selected && (
        <div style={{ padding: 12 }}>
          <strong>Exclude {selected.label}</strong>
          <Field label="Typed reason">
            <input value={reason} onChange={(e) => setReason(e.target.value)} />
          </Field>
          <Field label="Expires on">
            <input
              type="date"
              value={expiresOn}
              onChange={(e) => setExpiresOn(e.target.value)}
            />
          </Field>
          <div className="actions">
            <button
              className="btn primary"
              disabled={!reason.trim()}
              onClick={exclude}
            >
              Record exclusion
            </button>
            <button className="btn" onClick={() => setSelected(null)}>
              Cancel
            </button>
          </div>
        </div>
      )}
    </Card>
  );
}
function Metric({ label, value }) {
  return (
    <Card>
      <div style={{ padding: 14 }}>
        <div className="rowmeta">{label}</div>
        <div style={{ fontSize: "var(--t-display)", fontWeight: 650 }}>
          {value}
        </div>
      </div>
    </Card>
  );
}

function Calibration({ data }) {
  if (!data?.forecast_calibration?.length) return null;
  return (
    <Card>
      <div className="card-h">
        <h3>Forecast calibration by closed period</h3>
      </div>
      <table>
        <thead>
          <tr>
            <th>Period</th>
            <th>Commit outcomes</th>
            <th>Best Case outcomes</th>
            <th>Amount exclusions</th>
          </tr>
        </thead>
        <tbody>
          {data.forecast_calibration.map((x) => (
            <tr key={x.period.id}>
              <td>{x.period.name}</td>
              <td>{x.calibration.categories.commit.display}</td>
              <td>{x.calibration.categories.best_case.display}</td>
              <td>{x.calibration.amount_exclusions.length}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </Card>
  );
}

function ExecCoverage({ data }) {
  if (!data?.exec_touch_coverage) return null;
  return (
    <Card>
      <div className="card-h">
        <h3>Executive-touch coverage</h3>
      </div>
      <table>
        <thead>
          <tr>
            <th>Account</th>
            <th>Exec sponsor</th>
            <th>Evidence</th>
          </tr>
        </thead>
        <tbody>
          {data.exec_touch_coverage.map((x) => (
            <tr key={x.account_id}>
              <td>{x.account_name}</td>
              <td>
                {x.has_exec_sponsor
                  ? x.sponsors.map((s) => s.person_name).join(", ")
                  : "Missing"}
              </td>
              <td>
                {x.has_evidenced_exec_touch
                  ? "Meaningful touch recorded"
                  : "No meaningful touch recorded"}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </Card>
  );
}

function Forecast({ periods, reload, show, setShow }) {
  const toast = useToast();
  const [f, setF] = useState({
    name: "",
    starts_on: day(),
    ends_on: day(90),
    cadence: "quarterly",
    scenario_type: "operating",
    timezone: "America/New_York",
  });
  async function save() {
    try {
      await api.createForecastPeriod(f);
      toast("Forecast period opened");
      setShow(false);
      reload();
    } catch (e) {
      toast(e.message, "err");
    }
  }
  async function action(p, which) {
    try {
      if (which === "lock") await api.lockForecastPeriod(p.id);
      if (which === "submit") await api.submitForecast(p.id);
      if (which === "close") await api.closeForecastPeriod(p.id);
      toast(
        which === "submit" ? "Forecast draft generated" : `Period ${which}d`,
      );
      reload();
    } catch (e) {
      toast(e.message, "err");
    }
  }
  return (
    <Card>
      <div className="card-h">
        <h3>Forecast periods</h3>
        <div className="spacer" />
        <button className="btn primary small" onClick={() => setShow(!show)}>
          New period
        </button>
      </div>
      {show && (
        <div style={{ padding: 12 }}>
          <div className="grid2">
            <Field label="Name">
              <input
                value={f.name}
                onChange={(e) => setF({ ...f, name: e.target.value })}
              />
            </Field>
            <Field label="Cadence">
              <select
                value={f.cadence}
                onChange={(e) => setF({ ...f, cadence: e.target.value })}
              >
                {["weekly", "monthly", "quarterly", "annual", "custom"].map(
                  (x) => (
                    <option key={x}>{x}</option>
                  ),
                )}
              </select>
            </Field>
            <Field label="Starts">
              <input
                type="date"
                value={f.starts_on}
                onChange={(e) => setF({ ...f, starts_on: e.target.value })}
              />
            </Field>
            <Field label="Ends">
              <input
                type="date"
                value={f.ends_on}
                onChange={(e) => setF({ ...f, ends_on: e.target.value })}
              />
            </Field>
          </div>
          <button className="btn primary" onClick={save}>
            Open period
          </button>
        </div>
      )}
      {!periods.length ? (
        <Empty title="No forecast periods">
          Open the period leadership is asking about.
        </Empty>
      ) : (
        <table>
          <thead>
            <tr>
              <th>Period</th>
              <th>Dates</th>
              <th>Status</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            {periods.map((p) => (
              <tr key={p.id}>
                <td>
                  <strong>{p.name}</strong>
                  <div className="rowmeta">
                    {p.cadence} · {p.scenario_type}
                  </div>
                </td>
                <td>
                  {p.starts_on} → {p.ends_on}
                </td>
                <td>{p.status}</td>
                <td>
                  <div className="actions">
                    {p.status === "open" && (
                      <button
                        className="btn small"
                        onClick={() => action(p, "lock")}
                      >
                        Lock opening
                      </button>
                    )}
                    {p.status !== "closed" && (
                      <button
                        className="btn small"
                        onClick={() => action(p, "submit")}
                      >
                        Generate submission
                      </button>
                    )}
                    {p.status === "locked" && (
                      <button
                        className="btn small"
                        onClick={() => action(p, "close")}
                      >
                        Close period
                      </button>
                    )}
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </Card>
  );
}

function Coverage({ data, onOpen }) {
  if (!data) return null;
  return (
    <Card>
      <div className="card-h">
        <h3>Book coverage exposure</h3>
      </div>
      <table>
        <thead>
          <tr>
            <th>Account</th>
            <th>Recent internal participants</th>
            <th>Treatment</th>
          </tr>
        </thead>
        <tbody>
          {data.coverage_exposure.map((r) => (
            <tr
              key={r.account_id}
              className="clickable"
              onClick={() => onOpen(r.account_id, "internal")}
            >
              <td>
                <strong>{r.account_name}</strong>
              </td>
              <td>{r.recent_internal_participant_count}</td>
              <td>
                {r.single_thread_exposed
                  ? "Single-thread exposed"
                  : "Covered by multiple colleagues"}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </Card>
  );
}

function Feedback({ rows, accounts, reload, show, setShow }) {
  const toast = useToast();
  const [f, setF] = useState({
    title: "",
    problem_statement: "",
    feedback_type: "feature",
  });
  const [capture, setCapture] = useState({
    feedback_item_id: "",
    account_id: "",
    stakeholder_person_id: "",
    source_interaction_id: "",
    source_span: "",
    captured_on: day(),
  });
  const [stakeholders, setStakeholders] = useState([]);
  const [interactions, setInteractions] = useState([]);
  const [transition, setTransition] = useState({
    item_id: "",
    status: "submitted",
    reason: "",
    product_reference: "",
  });
  const [touch, setTouch] = useState({
    occurrence_id: "",
    touch_type: "acknowledgment",
    interaction_id: "",
  });
  async function save() {
    try {
      await api.createProductFeedback(f);
      toast("Feedback theme logged");
      setShow(false);
      reload();
    } catch (e) {
      toast(e.message, "err");
    }
  }
  async function chooseAccount(accountId) {
    setCapture({
      ...capture,
      account_id: accountId,
      stakeholder_person_id: "",
      source_interaction_id: "",
    });
    setTouch({ ...touch, occurrence_id: "", interaction_id: "" });
    if (!accountId) {
      setStakeholders([]);
      setInteractions([]);
      return;
    }
    try {
      const [p, h] = await Promise.all([
        api.persons(accountId),
        api.history(accountId),
      ]);
      setStakeholders(p.filter((x) => x.account_id === accountId));
      setInteractions(h.interactions);
    } catch (e) {
      toast(e.message, "err");
    }
  }
  async function addOccurrence() {
    try {
      await api.addFeedbackOccurrence(capture.feedback_item_id, {
        account_id: capture.account_id,
        stakeholder_person_id: capture.stakeholder_person_id,
        source_interaction_id: capture.source_interaction_id,
        source_span: capture.source_span || null,
        captured_on: capture.captured_on,
      });
      toast("Sourced account occurrence added; acknowledgment is now queued");
      reload();
    } catch (e) {
      toast(e.message, "err");
    }
  }
  async function moveTheme() {
    try {
      await api.setFeedbackStatus(transition.item_id, {
        status: transition.status,
        reason: transition.reason,
        product_reference:
          transition.status === "shipped" ? transition.product_reference : null,
      });
      toast("Product feedback status recorded");
      reload();
    } catch (e) {
      toast(e.message, "err");
    }
  }
  async function closeLoop() {
    try {
      await api.recordFeedbackTouch(touch.occurrence_id, {
        touch_type: touch.touch_type,
        interaction_id: touch.interaction_id,
      });
      toast("Client feedback touch recorded");
      reload();
    } catch (e) {
      toast(e.message, "err");
    }
  }
  const accountOccurrences = rows
    .flatMap((r) =>
      r.occurrences.map((o) => ({
        ...o,
        theme_title: r.title,
        theme_status: r.status,
      })),
    )
    .filter((o) => o.account_id === capture.account_id);
  return (
    <div className="stack">
      <Card>
        <div className="card-h">
          <h3>Product feedback across the book</h3>
          <div className="spacer" />
          <button className="btn primary small" onClick={() => setShow(!show)}>
            Log theme
          </button>
        </div>
        {show && (
          <div style={{ padding: 12 }}>
            <Field label="Theme">
              <input
                value={f.title}
                onChange={(e) => setF({ ...f, title: e.target.value })}
              />
            </Field>
            <Field label="Client problem">
              <textarea
                value={f.problem_statement}
                onChange={(e) =>
                  setF({ ...f, problem_statement: e.target.value })
                }
              />
            </Field>
            <button className="btn primary" onClick={save}>
              Log theme
            </button>
          </div>
        )}
        {!rows.length ? (
          <Empty title="No feedback themes">
            Aggregate sourced client needs here.
          </Empty>
        ) : (
          <table>
            <thead>
              <tr>
                <th>Theme</th>
                <th>Status</th>
                <th>Accounts</th>
                <th>Loop</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.id}>
                  <td>
                    <strong>{r.title}</strong>
                    <div className="rowmeta">{r.problem_statement}</div>
                  </td>
                  <td>{r.status}</td>
                  <td>{r.account_count}</td>
                  <td>
                    {r.occurrences.filter((x) => x.acknowledged).length}/
                    {r.occurrences.length} acknowledged ·{" "}
                    {
                      r.occurrences.filter((x) => x.resolution_closed_loop)
                        .length
                    }
                    /{r.occurrences.length} resolved
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Card>
      {rows.length > 0 && (
        <Card>
          <div className="card-h">
            <h3>Route feedback and close the loop</h3>
          </div>
          <div style={{ padding: 12 }}>
            <h4>Add sourced account occurrence</h4>
            <div className="grid2">
              <Field label="Theme">
                <select
                  value={capture.feedback_item_id}
                  onChange={(e) =>
                    setCapture({ ...capture, feedback_item_id: e.target.value })
                  }
                >
                  <option value="">Select</option>
                  {rows.map((r) => (
                    <option key={r.id} value={r.id}>
                      {r.title}
                    </option>
                  ))}
                </select>
              </Field>
              <Field label="Account">
                <select
                  value={capture.account_id}
                  onChange={(e) => chooseAccount(e.target.value)}
                >
                  <option value="">Select</option>
                  {accounts.map((a) => (
                    <option key={a.id} value={a.id}>
                      {a.name}
                    </option>
                  ))}
                </select>
              </Field>
              <Field label="Stakeholder">
                <select
                  value={capture.stakeholder_person_id}
                  onChange={(e) =>
                    setCapture({
                      ...capture,
                      stakeholder_person_id: e.target.value,
                    })
                  }
                >
                  <option value="">Select</option>
                  {stakeholders.map((p) => (
                    <option key={p.id} value={p.id}>
                      {p.name}
                    </option>
                  ))}
                </select>
              </Field>
              <Field label="Source interaction">
                <select
                  value={capture.source_interaction_id}
                  onChange={(e) =>
                    setCapture({
                      ...capture,
                      source_interaction_id: e.target.value,
                    })
                  }
                >
                  <option value="">Select</option>
                  {interactions.map((i) => (
                    <option key={i.id} value={i.id}>
                      {i.occurred_on} · {i.summary || i.type}
                    </option>
                  ))}
                </select>
              </Field>
            </div>
            <Field label="Verbatim source span">
              <input
                value={capture.source_span}
                onChange={(e) =>
                  setCapture({ ...capture, source_span: e.target.value })
                }
              />
            </Field>
            <button className="btn primary" onClick={addOccurrence}>
              Add occurrence
            </button>
            <h4>Update portfolio theme</h4>
            <div className="grid2">
              <Field label="Theme">
                <select
                  value={transition.item_id}
                  onChange={(e) =>
                    setTransition({ ...transition, item_id: e.target.value })
                  }
                >
                  <option value="">Select</option>
                  {rows.map((r) => (
                    <option key={r.id} value={r.id}>
                      {r.title}
                    </option>
                  ))}
                </select>
              </Field>
              <Field label="New status">
                <select
                  value={transition.status}
                  onChange={(e) =>
                    setTransition({ ...transition, status: e.target.value })
                  }
                >
                  {["submitted", "roadmapped", "shipped", "declined"].map(
                    (x) => (
                      <option key={x}>{x}</option>
                    ),
                  )}
                </select>
              </Field>
              <Field label="Reason">
                <input
                  value={transition.reason}
                  onChange={(e) =>
                    setTransition({ ...transition, reason: e.target.value })
                  }
                />
              </Field>
              {transition.status === "shipped" && (
                <Field label="Release reference">
                  <input
                    value={transition.product_reference}
                    onChange={(e) =>
                      setTransition({
                        ...transition,
                        product_reference: e.target.value,
                      })
                    }
                  />
                </Field>
              )}
            </div>
            <button className="btn" onClick={moveTheme}>
              Record status
            </button>
            <h4>Record acknowledgment or resolution</h4>
            <div className="grid2">
              <Field label="Account occurrence">
                <select
                  value={touch.occurrence_id}
                  onChange={(e) =>
                    setTouch({ ...touch, occurrence_id: e.target.value })
                  }
                >
                  <option value="">Select account above first</option>
                  {accountOccurrences.map((o) => (
                    <option key={o.id} value={o.id}>
                      {o.theme_title} · {o.stakeholder_name}
                    </option>
                  ))}
                </select>
              </Field>
              <Field label="Touch type">
                <select
                  value={touch.touch_type}
                  onChange={(e) =>
                    setTouch({ ...touch, touch_type: e.target.value })
                  }
                >
                  <option value="acknowledgment">Acknowledgment</option>
                  <option value="resolution">Resolution</option>
                </select>
              </Field>
              <Field label="Recorded interaction">
                <select
                  value={touch.interaction_id}
                  onChange={(e) =>
                    setTouch({ ...touch, interaction_id: e.target.value })
                  }
                >
                  <option value="">Select</option>
                  {interactions.map((i) => (
                    <option key={i.id} value={i.id}>
                      {i.occurred_on} · {i.summary || i.type}
                    </option>
                  ))}
                </select>
              </Field>
            </div>
            <button className="btn" onClick={closeLoop}>
              Record touch
            </button>
          </div>
        </Card>
      )}
    </div>
  );
}
function Field({ label, children }) {
  return (
    <div className="field">
      <label>{label}</label>
      {children}
    </div>
  );
}
