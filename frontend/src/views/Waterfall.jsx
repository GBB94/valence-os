import { useEffect, useMemo, useState } from "react";
import { BarChart, Bar, XAxis, YAxis, Cell, ResponsiveContainer, LabelList } from "recharts";
import { api } from "../api";
import { useThemeTick, cssVar } from "../ui";

// Budget waterfall (Section 6b / DESIGN-GUIDE §8): anchored start/end bars, floating increments,
// on the financial-direction tokens — the single documented exception to status-only color.
// This screen shows NO status indicators, per that same rule.
const money = (v) => "$" + Number(v).toLocaleString();

export default function Waterfall({ accountId }) {
  const [data, setData] = useState(null);
  const tick = useThemeTick();
  const COLOR = useMemo(() => ({
    start: cssVar("--fin-total", "#5A6070"), total: cssVar("--fin-total", "#5A6070"),
    add: cssVar("--fin-positive", "#1F8A54"), subtract: cssVar("--fin-negative", "#C0392F"),
  }), [tick]);
  useEffect(() => { if (accountId) api.waterfall(accountId).then(setData).catch(() => setData(null)); }, [accountId]);
  if (!data || data.steps.length <= 1) return null;

  // build floating bars: base (transparent) + delta (visible)
  let running = 0;
  const rows = data.steps.map((s) => {
    if (s.kind === "start" || s.kind === "total") {
      const r = { name: s.label, base: 0, delta: s.amount, kind: s.kind, display: s.amount };
      running = s.amount;
      return r;
    }
    const base = s.amount >= 0 ? running : running + s.amount;
    const r = { name: s.label, base, delta: Math.abs(s.amount), kind: s.amount >= 0 ? "add" : "subtract", display: s.amount };
    running += s.amount;
    return r;
  });

  return (
    <div className="card">
      <div className="card-h"><h3>Budget waterfall</h3><div className="spacer" /><span className="rowmeta">current → recovered spend → expansion → total</span></div>
      <div style={{ padding: 12 }}>
        <ResponsiveContainer width="100%" height={280}>
          <BarChart data={rows} margin={{ top: 20, right: 10, left: 10, bottom: 30 }}>
            <XAxis dataKey="name" tick={{ fontSize: 11 }} interval={0} angle={-12} textAnchor="end" height={50} />
            <YAxis tickFormatter={(v) => "$" + (v / 1000) + "k"} tick={{ fontSize: 11 }} />
            <Bar dataKey="base" stackId="a" fill="transparent" />
            <Bar dataKey="delta" stackId="a" radius={[2, 2, 0, 0]}>
              {rows.map((r, i) => <Cell key={i} fill={COLOR[r.kind]} />)}
              <LabelList dataKey="display" position="top" formatter={money} className="mono" style={{ fontSize: 10, fill: "var(--ink-secondary)" }} />
            </Bar>
          </BarChart>
        </ResponsiveContainer>
        <div className="rowmeta">Positive = additions, negative = subtractions, neutral = anchors — financial direction only. No status indicators share this screen.</div>
      </div>
    </div>
  );
}
