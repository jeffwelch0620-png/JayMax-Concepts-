import React, { useEffect, useState } from "react";
import * as api from "../lib/api";
import { RESTAURANTS } from "../lib/calc";
import { cardCls, SectionLabel } from "./common";

// M6 dashboard tiles (Jeff 2026-11-13): the owner's Group Overview shows each store's last 7 full days
// from the same figures as its Analytics tab. Read-only; nothing here changes food or stock records.
const RID = { berts: "berts", rudds: "rudds", papa: "papa_leonis" };
const money = v => `$${Number(v || 0).toLocaleString(undefined, { maximumFractionDigits: 0 })}`;
const num = v => Number(v || 0).toLocaleString(undefined, { maximumFractionDigits: 2 });
const plural = (n, word) => `${num(n)} ${word}${Number(n) === 1 ? "" : "s"}`;

function change(s) {
  if (s.before_net_sales === null || !Number(s.before_net_sales)) return "No complete stretch before to compare";
  const pct = Math.round((Number(s.net_sales) - Number(s.before_net_sales)) / Number(s.before_net_sales) * 100);
  return `${pct > 0 ? "+" : ""}${pct}% against the ${s.compared_days} days before`;
}

function toast(s) {
  if (s.stale) return [`Toast sync is behind (newest day ${s.latest_day || "none"})`, true];
  if (s.missing_days) return [`${plural(s.missing_days, "day")} not arrived from Toast`, true];
  if (s.needs_review) return [`${plural(s.needs_review, "day")} need review`, true];
  // Before 8 AM Eastern yesterday isn't due from Toast yet, so it isn't "missing", but the week isn't whole either.
  if (s.days < s.range_days) return [`${s.days} of ${s.range_days} days in; the newest isn't due from Toast yet`, true];
  return ["Every day arrived from Toast", false];
}

function Row({ label, children, warn, testId }) {
  return (
    <div className="flex justify-between gap-3 py-1.5 border-t border-jm-line text-sm" data-testid={testId}>
      <span className="text-slate-500">{label}</span>
      <span className={`text-right ${warn ? "text-jm-warn" : "text-slate-200"}`}>{children}</span>
    </div>
  );
}

function StoreTile({ s, onOpen }) {
  const store = RESTAURANTS.find(r => r.id === RID[s.store_id]);
  const sales = s.sales, prep = s.prep_vs_sales, gap = prep.largest_gap;
  const [fresh, late] = sales.available ? toast(sales) : ["Not set up", false];
  return (
    <div className={`${cardCls} p-4`} data-testid={`group-store-${s.store_id}`}>
      <div className="flex justify-between items-baseline mb-2">
        <span className="font-semibold text-slate-100">{store?.short || s.store_id}</span>
        {onOpen && store && <button className="text-xs text-slate-400 hover:underline" onClick={() => onOpen(store.id)}>Open store</button>}
      </div>
      {sales.available ? <>
        <div className="text-2xl font-bold text-slate-100" data-testid={`group-sales-${s.store_id}`}>{money(sales.net_sales)}</div>
        <div className="text-xs text-slate-500 mb-2">{change(sales)}</div>
        <Row label="Orders · average check">{num(sales.orders)} · {sales.average_check === null ? "–" : `$${Number(sales.average_check).toFixed(2)}`}</Row>
      </> : <div className="text-sm text-slate-500 mb-2">Sales are not set up for this store yet.</div>}
      <Row label="Toast" warn={late} testId={`group-toast-${s.store_id}`}>{fresh}</Row>
      <Row label="Waste">{s.waste.available ? `${plural(s.waste.entries, "record")} on ${plural(s.waste.items, "item")}` : "Not set up"}</Row>
      <Row label="Sales with portions" warn={prep.available && prep.missing_count > 0}>
        {prep.available ? `${prep.covered_percent === null ? "–" : `${prep.covered_percent}%`} · ${plural(prep.missing_count, "menu item")} missing` : "Not set up"}
      </Row>
      <Row label="Largest prep gap" testId={`group-gap-${s.store_id}`}>
        {!prep.available ? "Not set up" : gap
          ? `${gap.name} ${Number(gap.gap) > 0 ? "+" : ""}${num(gap.gap)} ${gap.unit}${gap.gap_percent === null ? "" : ` (${gap.gap_percent > 0 ? "+" : ""}${gap.gap_percent}%)`}`
          : "None to show"}
      </Row>
    </div>
  );
}

export function GroupAnalytics({ onOpenLocation }) {
  const [data, setData] = useState(null);
  const [error, setError] = useState("");
  useEffect(() => {
    let live = true;
    api.analyticsSummary().then(d => { if (live) setData(d); })
      .catch(e => { if (live) setError(e?.response?.data?.detail?.toString?.() || "Last week's analytics could not be loaded"); });
    return () => { live = false; };
  }, []);
  if (error) return <p role="alert" className="text-sm text-jm-bad mb-6" data-testid="group-analytics-error">{error}</p>;
  if (!data) return <p className="text-sm text-slate-500 mb-6">Loading last week's analytics…</p>;
  return (
    <div className="mb-6" data-testid="group-analytics">
      <SectionLabel>Last 7 days · {data.start} to {data.end}</SectionLabel>
      <div className="grid gap-3" style={{ gridTemplateColumns: "repeat(auto-fit,minmax(240px,1fr))" }}>
        {data.stores.map(s => <StoreTile key={s.store_id} s={s} onOpen={onOpenLocation} />)}
      </div>
      <p className="text-xs text-slate-500 mt-2">From each store's Analytics tab: Toast sales through yesterday, waste records and prep against sales. A prep gap is prep used minus what sales imply, for items with menu portions.</p>
    </div>
  );
}
