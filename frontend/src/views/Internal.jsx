import { useEffect, useMemo, useState } from "react";
import { api } from "../api";
import { Card, Empty, SegTabs, useToast } from "../ui";

const today = () => new Date().toISOString().slice(0, 10);
const day = (offset) => {
  const d = new Date();
  d.setDate(d.getDate() + offset);
  return d.toISOString().slice(0, 10);
};

export default function Internal({ accountId, reloadKey, onChanged }) {
  const [section, setSection] = useState("forecast");
  return (
    <div className="stack">
      <SegTabs
        tabs={[
          ["forecast", "Forecast"],
          ["asks", "Asks"],
          ["reviews", "Reviews"],
          ["coverage", "Coverage"],
        ]}
        value={section}
        onChange={setSection}
      />
      {section === "forecast" && (
        <Forecast accountId={accountId} reloadKey={reloadKey} />
      )}
      {section === "asks" && (
        <Asks
          accountId={accountId}
          reloadKey={reloadKey}
          onChanged={onChanged}
        />
      )}
      {section === "reviews" && (
        <>
          <Reviews accountId={accountId} reloadKey={reloadKey} />
          <FeedbackSummary accountId={accountId} reloadKey={reloadKey} />
        </>
      )}
      {section === "coverage" && (
        <Coverage accountId={accountId} reloadKey={reloadKey} />
      )}
    </div>
  );
}

function FeedbackSummary({ accountId, reloadKey }) {
  const [rows, setRows] = useState([]);
  useEffect(() => {
    api
      .productFeedback(accountId)
      .then(setRows)
      .catch(() => setRows([]));
  }, [accountId, reloadKey]);
  if (!rows.length) return null;
  return (
    <Card>
      <div className="card-h">
        <h3>Product feedback from this account</h3>
      </div>
      <table>
        <thead>
          <tr>
            <th>Theme</th>
            <th>Status</th>
            <th>Loop</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => {
            const mine = r.occurrences.filter(
              (x) => x.account_id === accountId,
            );
            return (
              <tr key={r.id}>
                <td>{r.title}</td>
                <td>{r.status}</td>
                <td>
                  {mine.filter((x) => x.acknowledged).length}/{mine.length}{" "}
                  acknowledged ·{" "}
                  {mine.filter((x) => x.resolution_closed_loop).length}/
                  {mine.length} resolved
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </Card>
  );
}

function Forecast({ accountId, reloadKey }) {
  const toast = useToast();
  const [periods, setPeriods] = useState([]);
  const [entries, setEntries] = useState([]);
  const [opps, setOpps] = useState([]);
  const [contracts, setContracts] = useState([]);
  const [show, setShow] = useState(false);
  const [editId, setEditId] = useState("");
  const [move, setMove] = useState({ category: "best_case", driver: "" });
  const [f, setF] = useState({
    period_id: "",
    target: "",
    category: "pipeline",
    amount: "",
    currency: "USD",
    price_basis: "arr",
    assessed_on: today(),
    probability: "",
    probability_rationale: "",
    unresolved_conditions: "",
    omitted_reason: "",
  });
  async function load() {
    const ps = await api.forecastPeriods();
    setPeriods(ps);
    const all = await Promise.all(ps.map((p) => api.forecastEntries(p.id)));
    setEntries(all.flat().filter((e) => e.account_id === accountId));
    setOpps(await api.expansions(accountId));
    setContracts(await api.contracts(accountId));
  }
  // Actions reload explicitly; changing account or the parent reload key refreshes the slice.
  /* oxlint-disable react-hooks/exhaustive-deps -- account/reloadKey are the refresh boundary. */
  useEffect(() => {
    load().catch((e) => toast(e.message, "err"));
  }, [accountId, reloadKey]);
  /* oxlint-enable react-hooks/exhaustive-deps */
  const targets = useMemo(
    () => [
      ...opps.map((x) => ({ id: `o:${x.id}`, label: `Expansion · ${x.name}` })),
      ...contracts
        .filter((x) => x.is_current)
        .map((x) => ({
          id: `c:${x.id}`,
          label: `Renewal · ${x.version_label}`,
        })),
    ],
    [opps, contracts],
  );
  async function save() {
    try {
      const [kind, id] = f.target.split(":");
      await api.createForecastEntry(f.period_id, {
        account_id: accountId,
        opportunity_id: kind === "o" ? id : null,
        contract_version_id: kind === "c" ? id : null,
        category: f.category,
        amount: f.amount === "" ? null : Number(f.amount),
        currency: f.amount === "" ? null : f.currency,
        price_basis: f.amount === "" ? null : f.price_basis,
        probability: f.probability === "" ? null : Number(f.probability),
        probability_rationale:
          f.probability === "" ? null : f.probability_rationale,
        assessed_on: f.assessed_on,
        unresolved_conditions: f.unresolved_conditions || null,
        omitted_reason: f.omitted_reason || null,
      });
      toast("Forecast call added");
      setShow(false);
      load();
    } catch (e) {
      toast(e.message, "err");
    }
  }
  async function change() {
    try {
      await api.changeForecastCategory(editId, {
        category: move.category,
        driver: move.driver,
        omitted_reason: move.category === "omitted" ? move.driver : null,
      });
      toast("Forecast movement recorded");
      setEditId("");
      setMove({ category: "best_case", driver: "" });
      load();
    } catch (e) {
      toast(e.message, "err");
    }
  }
  return (
    <Card>
      <div className="card-h">
        <h3>Forecast calls</h3>
        <div className="spacer" />
        <button className="btn primary small" onClick={() => setShow(!show)}>
          Add call
        </button>
      </div>
      {show && (
        <div style={{ padding: 12 }}>
          <div className="grid2">
            <Field label="Period">
              <select
                value={f.period_id}
                onChange={(e) => setF({ ...f, period_id: e.target.value })}
              >
                <option value="">Select</option>
                {periods
                  .filter((p) => p.status !== "closed")
                  .map((p) => (
                    <option key={p.id} value={p.id}>
                      {p.name}
                    </option>
                  ))}
              </select>
            </Field>
            <Field label="Target">
              <select
                value={f.target}
                onChange={(e) => setF({ ...f, target: e.target.value })}
              >
                <option value="">Select</option>
                {targets.map((t) => (
                  <option key={t.id} value={t.id}>
                    {t.label}
                  </option>
                ))}
              </select>
            </Field>
            <Field label="Category">
              <select
                value={f.category}
                onChange={(e) => setF({ ...f, category: e.target.value })}
              >
                {["commit", "best_case", "pipeline", "omitted"].map((x) => (
                  <option key={x}>{x}</option>
                ))}
              </select>
            </Field>
            <Field label="Assessment date">
              <input
                type="date"
                value={f.assessed_on}
                onChange={(e) => setF({ ...f, assessed_on: e.target.value })}
              />
            </Field>
            <Field label="Amount">
              <input
                type="number"
                value={f.amount}
                onChange={(e) => setF({ ...f, amount: e.target.value })}
              />
            </Field>
            <Field label="Probability (0–1)">
              <input
                type="number"
                step=".1"
                value={f.probability}
                onChange={(e) => setF({ ...f, probability: e.target.value })}
              />
            </Field>
          </div>
          <Field label="Probability rationale">
            <input
              value={f.probability_rationale}
              onChange={(e) =>
                setF({ ...f, probability_rationale: e.target.value })
              }
            />
          </Field>
          <Field label="Unresolved conditions">
            <input
              value={f.unresolved_conditions}
              onChange={(e) =>
                setF({ ...f, unresolved_conditions: e.target.value })
              }
            />
          </Field>
          <div className="actions">
            <button className="btn primary" onClick={save}>
              Save call
            </button>
          </div>
        </div>
      )}
      {!entries.length ? (
        <Empty title="No forecast calls">
          Add an opportunity or renewal to an active period.
        </Empty>
      ) : (
        <table>
          <thead>
            <tr>
              <th>Period</th>
              <th>Category</th>
              <th>Amount</th>
              <th>Evidence</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {entries.map((e) => (
              <tr key={e.id}>
                <td>{periods.find((p) => p.id === e.period_id)?.name}</td>
                <td>
                  <strong>{e.category.replace("_", " ")}</strong>
                  {editId === e.id && (
                    <div>
                      <select
                        value={move.category}
                        onChange={(x) =>
                          setMove({ ...move, category: x.target.value })
                        }
                      >
                        {["commit", "best_case", "pipeline", "omitted"]
                          .filter((x) => x !== e.category)
                          .map((x) => (
                            <option key={x} value={x}>
                              {x.replace("_", " ")}
                            </option>
                          ))}
                      </select>
                      <input
                        placeholder="Deal event driving the move"
                        value={move.driver}
                        onChange={(x) =>
                          setMove({ ...move, driver: x.target.value })
                        }
                      />
                      <button className="btn small" onClick={change}>
                        Record movement
                      </button>
                    </div>
                  )}
                </td>
                <td>
                  {e.amount == null
                    ? "—"
                    : `${e.amount.toLocaleString()} ${e.currency} ${e.price_basis}`}
                </td>
                <td>
                  {e.evidence.supported ? (
                    <span className="subtle">Supported</span>
                  ) : (
                    // The checker already returns a written rule per gap; render that rather
                    // than the machine key, and mark it so an unsupported call is visible
                    // without reading the sentence.
                    <span className="evidence-gap">
                      <span className="state-mark risk" aria-hidden="true" />
                      <span>
                        Missing:{" "}
                        {e.evidence.missing
                          .map((x) => x.explanation)
                          .join(" ")}
                      </span>
                    </span>
                  )}
                </td>
                <td>
                  {periods.find((p) => p.id === e.period_id)?.status !==
                    "closed" && (
                    <button
                      className="btn small"
                      onClick={() => {
                        setEditId(editId === e.id ? "" : e.id);
                        setMove({
                          category:
                            e.category === "best_case"
                              ? "pipeline"
                              : "best_case",
                          driver: "",
                        });
                      }}
                    >
                      Move
                    </button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </Card>
  );
}

/* oxlint-disable react-hooks/exhaustive-deps -- account/reloadKey are the refresh boundary; mutations call load. */
function Asks({ accountId, reloadKey, onChanged }) {
  const toast = useToast();
  const [rows, setRows] = useState([]);
  const [people, setPeople] = useState([]);
  const [funcs, setFuncs] = useState([]);
  const [calls, setCalls] = useState([]);
  const [show, setShow] = useState(false);
  const [f, setF] = useState({
    need: "",
    success_condition: "",
    ask_type: "general",
    requested_by_person_id: "",
    requested_from_function_id: "",
    forecast_entry_id: "",
    needed_by: today(),
  });
  async function load() {
    const [a, p, fn, periods] = await Promise.all([
      api.internalAsks(accountId),
      api.persons(accountId),
      api.internalFunctions(),
      api.forecastPeriods(),
    ]);
    const forecast = (
      await Promise.all(
        periods
          .filter((x) => ["open", "locked"].includes(x.status))
          .map((x) => api.forecastEntries(x.id)),
      )
    )
      .flat()
      .filter((x) => x.account_id === accountId);
    setRows(a);
    setPeople(p.filter((x) => x.affiliation === "valence"));
    setFuncs(fn);
    setCalls(forecast);
  }
  useEffect(() => {
    load().catch((e) => toast(e.message, "err"));
  }, [accountId, reloadKey]);
  async function save() {
    try {
      await api.createInternalAsk(accountId, {
        ...f,
        requested_from_function_id: f.requested_from_function_id || null,
        forecast_entry_id: f.forecast_entry_id || null,
      });
      toast("Ask raised");
      setShow(false);
      load();
      onChanged?.();
    } catch (e) {
      toast(e.message, "err");
    }
  }
  async function advance(r, status) {
    try {
      const body = { status };
      if (status === "delivered")
        body.completion_note = "Delivered and verified";
      await api.setInternalAskStatus(r.id, body);
      load();
      onChanged?.();
    } catch (e) {
      toast(e.message, "err");
    }
  }
  async function escalate(r) {
    try {
      await api.escalateAsk(r.id, { severity: "high" });
      toast("Escalation opened with the configured path snapshot");
      load();
      onChanged?.();
    } catch (e) {
      toast(e.message, "err");
    }
  }
  return (
    <Card>
      <div className="card-h">
        <h3>Internal asks</h3>
        <div className="spacer" />
        <button className="btn primary small" onClick={() => setShow(!show)}>
          Raise ask
        </button>
      </div>
      {show && (
        <div style={{ padding: 12 }}>
          <Field label="What is needed">
            <input
              value={f.need}
              onChange={(e) => setF({ ...f, need: e.target.value })}
            />
          </Field>
          <Field label="Success condition">
            <input
              value={f.success_condition}
              onChange={(e) =>
                setF({ ...f, success_condition: e.target.value })
              }
            />
          </Field>
          <div className="grid2">
            <Field label="Requested by">
              <select
                value={f.requested_by_person_id}
                onChange={(e) =>
                  setF({ ...f, requested_by_person_id: e.target.value })
                }
              >
                <option value="">Select</option>
                {people.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.name}
                  </option>
                ))}
              </select>
            </Field>
            <Field label="Function">
              <select
                value={f.requested_from_function_id}
                onChange={(e) =>
                  setF({ ...f, requested_from_function_id: e.target.value })
                }
              >
                <option value="">Select</option>
                {funcs.map((x) => (
                  <option key={x.id} value={x.id}>
                    {x.name}
                  </option>
                ))}
              </select>
            </Field>
            <Field label="Needed by">
              <input
                type="date"
                value={f.needed_by}
                onChange={(e) => setF({ ...f, needed_by: e.target.value })}
              />
            </Field>
            <Field label="Linked forecast call">
              <select
                value={f.forecast_entry_id}
                onChange={(e) =>
                  setF({ ...f, forecast_entry_id: e.target.value })
                }
              >
                <option value="">None</option>
                {calls.map((x) => (
                  <option key={x.id} value={x.id}>
                    {x.category.replace("_", " ")} ·{" "}
                    {x.amount == null
                      ? "amount unknown"
                      : `${x.amount} ${x.currency}`}
                  </option>
                ))}
              </select>
            </Field>
          </div>
          <button className="btn primary" onClick={save}>
            Raise ask
          </button>
        </div>
      )}
      {!rows.length ? (
        <Empty title="No internal asks">
          Capture dependencies before they disappear into chat.
        </Empty>
      ) : (
        <table>
          <thead>
            <tr>
              <th>Need</th>
              <th>Needed by</th>
              <th>Status</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.id}>
                <td>
                  <strong>{r.need}</strong>
                  <div className="rowmeta">
                    {r.success_condition}
                    {r.commit_urgent ? " · Commit-linked" : ""}
                    {r.escalations?.length
                      ? ` · ${r.escalations.length} escalation${r.escalations.length === 1 ? "" : "s"}`
                      : ""}
                  </div>
                </td>
                <td>{r.needed_by}</td>
                <td>{r.status.replace("_", " ")}</td>
                <td>
                  <div className="actions">
                    {r.status === "raised" && (
                      <button
                        className="btn small"
                        onClick={() => advance(r, "acknowledged")}
                      >
                        Acknowledge
                      </button>
                    )}
                    {!["delivered", "declined"].includes(r.status) && (
                      <button className="btn small" onClick={() => escalate(r)}>
                        Escalate
                      </button>
                    )}
                    {!["delivered", "declined"].includes(r.status) && (
                      <button
                        className="btn small"
                        onClick={() => advance(r, "delivered")}
                      >
                        Deliver
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

function Reviews({ accountId, reloadKey }) {
  const toast = useToast();
  const [rows, setRows] = useState([]);
  const [views, setViews] = useState([]);
  const [people, setPeople] = useState([]);
  const [pov, setPov] = useState("");
  const [status, setStatus] = useState({
    dimension: "delivery",
    value: "on_track",
    rationale: "",
    recovery_owner_person_id: "",
    recovery_action: "",
    recovery_due_on: day(7),
    leadership_not_applicable_reason: "",
  });
  async function load() {
    const [r, v, p] = await Promise.all([
      api.reviews(accountId),
      api.operatorViews(accountId),
      api.persons(accountId),
    ]);
    setRows(r);
    setViews(v);
    setPeople(p.filter((x) => x.affiliation === "valence"));
  }
  useEffect(() => {
    load().catch((e) => toast(e.message, "err"));
  }, [accountId, reloadKey]);
  async function addReview() {
    try {
      await api.createReview(accountId, {
        review_type: "quarterly",
        scheduled_on: today(),
        participant_ids: [],
      });
      toast("Review planned");
      load();
    } catch (e) {
      toast(e.message, "err");
    }
  }
  async function addPov() {
    try {
      await api.createOperatorView(accountId, {
        body: pov,
        assessed_on: today(),
      });
      setPov("");
      toast("Point of view saved");
      load();
    } catch (e) {
      toast(e.message, "err");
    }
  }
  async function assess() {
    try {
      const responseNeeded = ["at_risk", "off_track"].includes(status.value);
      await api.assessInternalStatus(accountId, {
        ...status,
        assessed_on: today(),
        recovery_owner_person_id: responseNeeded
          ? status.recovery_owner_person_id
          : null,
        recovery_action: responseNeeded ? status.recovery_action : null,
        recovery_due_on: responseNeeded ? status.recovery_due_on : null,
        leadership_not_applicable_reason:
          status.value === "off_track"
            ? status.leadership_not_applicable_reason
            : null,
      });
      toast("Governed status assessment saved");
    } catch (e) {
      toast(e.message, "err");
    }
  }
  async function generate(id, kind) {
    try {
      await api.generateReviewDocument(id, kind);
      toast("Draft generated");
    } catch (e) {
      toast(e.message, "err");
    }
  }
  return (
    <div className="stack">
      <Card>
        <div className="card-h">
          <h3>Governed account status</h3>
        </div>
        <div style={{ padding: 12 }}>
          <div className="grid2">
            <Field label="Dimension">
              <select
                value={status.dimension}
                onChange={(e) =>
                  setStatus({ ...status, dimension: e.target.value })
                }
              >
                <option value="delivery">Delivery</option>
                <option value="commercial">Commercial</option>
              </select>
            </Field>
            <Field label="Status">
              <select
                value={status.value}
                onChange={(e) =>
                  setStatus({ ...status, value: e.target.value })
                }
              >
                {["on_track", "at_risk", "off_track", "unknown"].map((x) => (
                  <option key={x} value={x}>
                    {x.replace("_", " ")}
                  </option>
                ))}
              </select>
            </Field>
          </div>
          <Field label="Rationale">
            <input
              value={status.rationale}
              onChange={(e) =>
                setStatus({ ...status, rationale: e.target.value })
              }
            />
          </Field>
          {["at_risk", "off_track"].includes(status.value) && (
            <div className="grid2">
              <Field label="Recovery owner">
                <select
                  value={status.recovery_owner_person_id}
                  onChange={(e) =>
                    setStatus({
                      ...status,
                      recovery_owner_person_id: e.target.value,
                    })
                  }
                >
                  <option value="">Select</option>
                  {people.map((p) => (
                    <option key={p.id} value={p.id}>
                      {p.name}
                    </option>
                  ))}
                </select>
              </Field>
              <Field label="Recovery due">
                <input
                  type="date"
                  value={status.recovery_due_on}
                  onChange={(e) =>
                    setStatus({ ...status, recovery_due_on: e.target.value })
                  }
                />
              </Field>
              <Field label="Recovery action">
                <input
                  value={status.recovery_action}
                  onChange={(e) =>
                    setStatus({ ...status, recovery_action: e.target.value })
                  }
                />
              </Field>
              {status.value === "off_track" && (
                <Field label="Leadership handling">
                  <input
                    placeholder="Ask already raised, or why not applicable"
                    value={status.leadership_not_applicable_reason}
                    onChange={(e) =>
                      setStatus({
                        ...status,
                        leadership_not_applicable_reason: e.target.value,
                      })
                    }
                  />
                </Field>
              )}
            </div>
          )}
          <button className="btn primary" onClick={assess}>
            Save assessment
          </button>
        </div>
      </Card>
      <Card>
        <div className="card-h">
          <h3>Operator point of view</h3>
        </div>
        <div style={{ padding: 12 }}>
          {views[0] && (
            <blockquote>
              {views[0].body}
              <div className="rowmeta">
                {views[0].author} · {views[0].assessed_on}
              </div>
            </blockquote>
          )}
          <Field label="New dated view">
            <textarea value={pov} onChange={(e) => setPov(e.target.value)} />
          </Field>
          <button className="btn primary" onClick={addPov}>
            Save view
          </button>
        </div>
      </Card>
      <Card>
        <div className="card-h">
          <h3>Account reviews</h3>
          <div className="spacer" />
          <button className="btn primary small" onClick={addReview}>
            Plan review
          </button>
        </div>
        {!rows.length ? (
          <Empty title="No reviews">Plan the next leadership review.</Empty>
        ) : (
          <table>
            <thead>
              <tr>
                <th>Review</th>
                <th>Date</th>
                <th>Status</th>
                <th>Generate</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.id}>
                  <td>{r.review_type}</td>
                  <td>{r.held_on || r.scheduled_on || "—"}</td>
                  <td>{r.status}</td>
                  <td>
                    <div className="actions">
                      <button
                        className="btn small"
                        onClick={() => generate(r.id, "internal_account_brief")}
                      >
                        Brief
                      </button>
                      <button
                        className="btn small"
                        onClick={() => generate(r.id, "internal_review_packet")}
                      >
                        Packet
                      </button>
                      <button
                        className="btn small"
                        onClick={() =>
                          generate(r.id, "internal_challenge_sheet")
                        }
                      >
                        Challenge
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Card>
      {rows.some((r) => r.status === "planned") && (
        <HoldReview accountId={accountId} reviews={rows} onSaved={load} />
      )}{" "}
      {rows.length > 0 && (
        <ReviewOutcomes
          accountId={accountId}
          reviews={rows}
          people={people}
          onSaved={load}
        />
      )}
    </div>
  );
}

function HoldReview({ accountId, reviews, onSaved }) {
  const toast = useToast();
  const planned = reviews.filter((r) => r.status === "planned");
  const [interactions, setInteractions] = useState([]);
  const [reviewId, setReviewId] = useState(planned[0]?.id || "");
  const [interactionId, setInteractionId] = useState("");
  useEffect(() => {
    api
      .history(accountId)
      .then((x) => setInteractions(x.interactions))
      .catch((e) => toast(e.message, "err"));
  }, [accountId]);
  async function hold() {
    try {
      await api.holdReview(reviewId, {
        held_on: today(),
        source_interaction_id: interactionId,
      });
      toast("Review held with ledger interaction");
      onSaved();
    } catch (e) {
      toast(e.message, "err");
    }
  }
  return (
    <Card>
      <div className="card-h">
        <h3>Record a held review</h3>
      </div>
      <div style={{ padding: 12 }}>
        <div className="grid2">
          <Field label="Planned review">
            <select
              value={reviewId}
              onChange={(e) => setReviewId(e.target.value)}
            >
              {planned.map((r) => (
                <option key={r.id} value={r.id}>
                  {r.review_type} · {r.scheduled_on || "undated"}
                </option>
              ))}
            </select>
          </Field>
          <Field label="Review interaction">
            <select
              value={interactionId}
              onChange={(e) => setInteractionId(e.target.value)}
            >
              <option value="">Select the factual ledger interaction</option>
              {interactions.map((i) => (
                <option key={i.id} value={i.id}>
                  {i.occurred_on} · {i.summary || i.type}
                </option>
              ))}
            </select>
          </Field>
        </div>
        <button
          className="btn primary"
          disabled={!reviewId || !interactionId}
          onClick={hold}
        >
          Mark held
        </button>
      </div>
    </Card>
  );
}

function ReviewOutcomes({ accountId, reviews, people, onSaved }) {
  const toast = useToast();
  const [f, setF] = useState({
    account_review_id: reviews[0]?.id || "",
    commitment_class: "leadership_to_operator",
    description: "",
    responsible_party_id: "",
    internal_owner_id: "",
    due_date: day(7),
  });
  const [decision, setDecision] = useState({
    account_review_id: reviews[0]?.id || "",
    description: "",
    decided_by_id: "",
    rationale: "",
  });
  async function addCommitment() {
    try {
      await api.createCommitment({ account_id: accountId, ...f });
      toast("Review commitment added to the main ledger");
      setF({ ...f, description: "" });
      onSaved();
    } catch (e) {
      toast(e.message, "err");
    }
  }
  async function addDecision() {
    try {
      await api.createDecision({
        account_id: accountId,
        ...decision,
        decided_on: today(),
        decided_by_id: decision.decided_by_id || null,
      });
      toast("Review decision recorded");
      setDecision({ ...decision, description: "", rationale: "" });
      onSaved();
    } catch (e) {
      toast(e.message, "err");
    }
  }
  return (
    <Card>
      <div className="card-h">
        <h3>Review decisions and two-way commitments</h3>
      </div>
      <div style={{ padding: 12 }}>
        <div className="grid2">
          <Field label="Review">
            <select
              value={f.account_review_id}
              onChange={(e) => {
                setF({ ...f, account_review_id: e.target.value });
                setDecision({ ...decision, account_review_id: e.target.value });
              }}
            >
              {reviews.map((r) => (
                <option key={r.id} value={r.id}>
                  {r.review_type} · {r.held_on || r.scheduled_on || "undated"}
                </option>
              ))}
            </select>
          </Field>
          <Field label="Direction">
            <select
              value={f.commitment_class}
              onChange={(e) => setF({ ...f, commitment_class: e.target.value })}
            >
              <option value="leadership_to_operator">
                Leadership to operator
              </option>
              <option value="operator_to_internal">Operator to internal</option>
              <option value="internal_peer">Internal peer</option>
            </select>
          </Field>
          <Field label="Commitment">
            <input
              value={f.description}
              onChange={(e) => setF({ ...f, description: e.target.value })}
            />
          </Field>
          <Field label="Due">
            <input
              type="date"
              value={f.due_date}
              onChange={(e) => setF({ ...f, due_date: e.target.value })}
            />
          </Field>
          <Field label="Responsible">
            <select
              value={f.responsible_party_id}
              onChange={(e) =>
                setF({ ...f, responsible_party_id: e.target.value })
              }
            >
              <option value="">Select</option>
              {people.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.name}
                </option>
              ))}
            </select>
          </Field>
          <Field label="Follow-up owner">
            <select
              value={f.internal_owner_id}
              onChange={(e) =>
                setF({ ...f, internal_owner_id: e.target.value })
              }
            >
              <option value="">Select</option>
              {people.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.name}
                </option>
              ))}
            </select>
          </Field>
        </div>
        <button className="btn primary" onClick={addCommitment}>
          Add commitment
        </button>
        <h4>Decision</h4>
        <div className="grid2">
          <Field label="Decision">
            <input
              value={decision.description}
              onChange={(e) =>
                setDecision({ ...decision, description: e.target.value })
              }
            />
          </Field>
          <Field label="Decided by">
            <select
              value={decision.decided_by_id}
              onChange={(e) =>
                setDecision({ ...decision, decided_by_id: e.target.value })
              }
            >
              <option value="">Not recorded</option>
              {people.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.name}
                </option>
              ))}
            </select>
          </Field>
        </div>
        <Field label="Rationale">
          <input
            value={decision.rationale}
            onChange={(e) =>
              setDecision({ ...decision, rationale: e.target.value })
            }
          />
        </Field>
        <button className="btn" onClick={addDecision}>
          Record decision
        </button>
      </div>
    </Card>
  );
}

function Coverage({ accountId, reloadKey }) {
  const toast = useToast();
  const [data, setData] = useState(null);
  const [people, setPeople] = useState([]);
  const [person, setPerson] = useState("");
  async function load() {
    const [d, p] = await Promise.all([
      api.coverage(accountId),
      api.persons(accountId),
    ]);
    setData(d);
    setPeople(p.filter((x) => x.affiliation === "valence"));
  }
  useEffect(() => {
    load().catch((e) => toast(e.message, "err"));
  }, [accountId, reloadKey]);
  async function add() {
    try {
      await api.addInternalRoster(accountId, {
        person_id: person,
        role: "supporting_em",
        standing_responsibilities: "Backup account coverage",
        coverage_type: "backup",
        active_from: today(),
      });
      toast("Roster updated");
      load();
    } catch (e) {
      toast(e.message, "err");
    }
  }
  async function makeBrief(kind, rosterId) {
    try {
      if (kind === "coverage") await api.coverageBrief(accountId);
      if (kind === "call") await api.colleagueCallBrief(accountId, rosterId);
      if (kind === "return")
        await api.coverageReturnBrief(accountId, day(-14), today());
      toast("Brief generated");
    } catch (e) {
      toast(e.message, "err");
    }
  }
  if (!data)
    return (
      <Card>
        <div style={{ padding: 14 }}>Loading coverage…</div>
      </Card>
    );
  return (
    <div className="stack">
      <Card>
        <div className="card-h">
          <h3>Internal roster</h3>
          <div className="spacer" />
          <button className="btn small" onClick={() => makeBrief("return")}>
            Return brief
          </button>
          <button
            className="btn primary small"
            onClick={() => makeBrief("coverage")}
          >
            14-day coverage brief
          </button>
        </div>
        <div style={{ padding: 12 }}>
          <div className="actions">
            <select value={person} onChange={(e) => setPerson(e.target.value)}>
              <option value="">Add Valence colleague…</option>
              {people.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.name}
                </option>
              ))}
            </select>
            <button className="btn" disabled={!person} onClick={add}>
              Add backup
            </button>
          </div>
        </div>
        {data.roster.length ? (
          <table>
            <thead>
              <tr>
                <th>Person</th>
                <th>Role</th>
                <th>Coverage</th>
                <th>Responsibilities</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {data.roster.map((r) => (
                <tr key={r.id}>
                  <td>{r.person_name}</td>
                  <td>{r.role.replaceAll("_", " ")}</td>
                  <td>{r.coverage_type}</td>
                  <td>{r.standing_responsibilities}</td>
                  <td>
                    <button
                      className="btn small"
                      onClick={() => makeBrief("call", r.id)}
                    >
                      Call brief
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          <Empty title="No roster">
            Add the people who actively cover this account.
          </Empty>
        )}
      </Card>
      <Card>
        <div className="card-h">
          <h3>Coverage exposure</h3>
        </div>
        <div style={{ padding: 12 }}>
          <strong>
            {data.contribution.single_thread_exposed
              ? "Single-thread exposed"
              : "Multi-person coverage evidenced"}
          </strong>
          <div className="rowmeta">{data.contribution.basis}</div>
          <h4>Three things that break if ignored</h4>
          {data.things_that_break.map((x) => (
            <div key={`${x.kind}:${x.id}`}>
              • {x.text} <span className="rowmeta">— {x.basis}</span>
            </div>
          ))}
        </div>
      </Card>
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
/* oxlint-enable react-hooks/exhaustive-deps */
