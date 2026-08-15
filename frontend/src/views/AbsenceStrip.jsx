import { useEffect, useState } from "react";
import { api } from "../api";
import { SlideOver, useToast, rowActivation } from "../ui";
import { ABSENCE_WINDOWS, absenceItems, absenceRecordLabel, normalizeWindow } from "../portfolioAbsence";

/**
 * The absence strip on Today (VISIBILITY-SPEC §4) — where we are not looking.
 *
 * It sits above the queue because it is the same surface's question asked in the negative: the
 * queue ranks what exists, this counts what does not. It is not a new destination and does not
 * propose one.
 *
 * Deliberately hueless. Every other count on this screen carries a band colour, and that is right
 * for attention bands; it is wrong here. A colour ramp across four counters would be read as a
 * grade, which is the composite score this spec refuses. Zero gets the same treatment as sixty-two:
 * it is the only value here that is good news, and it still gets no hue.
 */
export default function AbsenceStrip({ reloadKey, onOpenAccount }) {
  const toast = useToast();
  const [data, setData] = useState(null);
  const [days, setDays] = useState(null);
  const [open, setOpen] = useState(null); // the counter whose list is showing

  useEffect(() => {
    let cancelled = false;
    api.portfolioAbsence(days === null ? undefined : days)
      .then((payload) => { if (!cancelled) setData(payload); })
      .catch((error) => { if (!cancelled) toast(error.message, "err"); });
    return () => { cancelled = true; };
  }, [reloadKey, days]);

  if (!data) return null;
  const items = absenceItems(data);
  if (!items.length) return null;
  const windowDays = data.window?.days ?? null;

  return (
    <section className="absence-strip" aria-label="Portfolio coverage gaps">
      <div className="absence-strip-head">
        <h2>Where you are not looking</h2>
        <label className="absence-window">
          <span>Window</span>
          <select value={windowDays ?? ""} aria-label="Absence window in days"
            onChange={(event) => setDays(normalizeWindow(event.target.value, data.window?.default_days))}>
            {ABSENCE_WINDOWS.map((option) => (
              <option key={option} value={option}>{option} days</option>
            ))}
          </select>
        </label>
      </div>
      <ul className="absence-counters">
        {items.map((item) => (
          <li key={item.key}>
            {/* The number opens the list it counted. A count an operator cannot open is an
                accusation they have no way to answer (§4.2, rule 4). */}
            <button type="button" className="absence-counter" onClick={() => setOpen(item)}
              disabled={item.count === 0}>
              <span className="absence-count">{item.count}</span>
              {/* The server's sentence, unedited — including its own copy of the number, so the
                  count and the window it was computed over can never be shown apart. */}
              <span className="absence-sentence">{item.sentence}</span>
            </button>
          </li>
        ))}
      </ul>
      <p className="absence-basis">{data.basis}</p>

      {open && (
        <SlideOver title={open.sentence} onClose={() => setOpen(null)}>
          <ul className="absence-list">
            {open.records.map((record) => {
              const label = absenceRecordLabel(record, open.recordKind);
              const accountId = open.recordKind === "program" ? record.account_id : record.id;
              return (
                <li key={record.id}>
                  <div className="absence-list-row"
                    {...rowActivation(() => { setOpen(null); onOpenAccount?.(accountId); })}>
                    <span>{label.primary}</span>
                    {label.secondary && <span className="rowmeta">{label.secondary}</span>}
                  </div>
                </li>
              );
            })}
          </ul>
        </SlideOver>
      )}
    </section>
  );
}
