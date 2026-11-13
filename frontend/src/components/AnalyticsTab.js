import React, { useEffect, useRef, useState } from "react";
import * as api from "../lib/api";
import { prepTracks, prepTrackLabel } from "../lib/prepTracks";
import { cardCls, inpCls, btnGhost, EmptyState, Field, MetricCard, PageTitle, SectionLabel } from "./common";
import { MenuPortions } from "./MenuPortions";

// M6 analytics (Jeff 2026-11-06): how prep, counts and orders went over a date range, for the
// General Manager and above. A read only; backend/analytics.py works out every number.
const STORES = { berts: "Bert's", rudds: "Rudd's", papa: "Papa Leone's" };
const storeName = id => STORES[id] || id;
const num = v => v === null || v === undefined ? "–" : Number(v).toLocaleString(undefined, { maximumFractionDigits: 2 });
const qty = (v, unit) => `${num(v)} ${unit || ""}`.trim();
const wait = m => m === null || m === undefined ? "–" : m < 60 ? `${m} min` : `${(m / 60).toFixed(1)} h`;
const pct = (part, whole) => whole ? `${Math.round(part / whole * 100)}%` : "–";
const money = v => v === null || v === undefined ? "–" : `$${Number(v).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
// Change against the same number of days just before the range, e.g. "+4% vs 2026-11-03 – 2026-11-09".
const change = (now, then) => !Number(then) ? null : `${Number(now) >= Number(then) ? "+" : ""}${Math.round((Number(now) - Number(then)) / Number(then) * 100)}%`;
// The local calendar day: toISOString is UTC, which is already tomorrow on an Eastern evening.
const isoDay = d => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
const daysAgo = n => { const d = new Date(); d.setDate(d.getDate() - n); return isoDay(d); };
const STATUS = { done: "On time", late: "Late", overdue: "Not done", due: "Due today", upcoming: "Upcoming" };
const REASONS = { out_of_ingredient: "Out of an ingredient", ran_out_of_time: "Ran out of time", equipment: "Equipment", other: "Other" };
const WASTE = { storage_spoilage: "Storage spoilage", service_discard: "Service discard", other: "Other waste" };

const Grid = ({ children }) => <div className="grid gap-3 mb-3" style={{ gridTemplateColumns: "repeat(auto-fit,minmax(170px,1fr))" }}>{children}</div>;

function Table({ head, rows, testId }) {
  if (!rows.length) return null;
  return (
    <div className={`${cardCls} overflow-x-auto mb-2`} data-testid={testId}>
      <table className="w-full text-sm">
        <thead><tr className="text-left text-[11px] uppercase tracking-[0.06em] text-slate-500">{head.map(h => <th key={h} className="px-3 py-2 font-bold">{h}</th>)}</tr></thead>
        <tbody>{rows.map((r, i) => <tr key={i} className="border-t border-jm-line text-slate-300">{r.map((c, j) => <td key={j} className="px-3 py-2 whitespace-nowrap">{c}</td>)}</tr>)}</tbody>
      </table>
    </div>
  );
}

function Section({ title, note, children, testId }) {
  return (
    <section className="mb-7" data-testid={testId}>
      <SectionLabel>{title}</SectionLabel>
      {note && <p className="text-xs text-slate-500 -mt-1 mb-2">{note}</p>}
      {children}
    </section>
  );
}

const Unavailable = ({ part }) => part?.store_wide
  ? <p className="text-sm text-slate-500">Store-wide: choose All tracks to see it.</p>
  : <p className="text-sm text-slate-500">Not set up at this store yet.</p>;

function Throughput({ t }) {
  if (!t?.available) return <Unavailable part={t} />;
  return <>
    <Grid>
      <MetricCard testId="analytics-tasks" label="Prep tasks" value={num(t.tasks)} sub={`${t.lists.released} released lists`} />
      <MetricCard testId="analytics-met-plan" label="Made to plan" value={pct(t.met_plan, t.tasks)} sub={`${t.met_plan} of ${t.tasks} tasks`} tone={t.tasks && t.met_plan === t.tasks ? "good" : "normal"} />
      <MetricCard testId="analytics-short" label="Short of plan" value={num(t.short)} sub="past days, made less than planned" tone={t.short ? "warn" : "good"} />
      <MetricCard label="Lists not released" value={num(t.lists.not_released)} sub="through today" tone={t.lists.not_released ? "warn" : "normal"} />
    </Grid>
    <Table head={["Track", "Tasks", "Made to plan", "Short", "Average % of plan", "Needs review"]}
      rows={t.tracks.map(s => [prepTrackLabel(s.track), s.tasks, s.met_plan, s.short, s.average_percent_of_plan === null ? "–" : `${s.average_percent_of_plan}%`, s.needs_review])} />
    <Table testId="analytics-short-tasks" head={["Day", "Track", "Item", "Planned", "Made", "Short by"]}
      rows={t.short_tasks.map(r => [r.prep_date, prepTrackLabel(r.track), r.name, qty(r.planned, r.unit), qty(r.made, r.unit), qty(r.short_by, r.unit)])} />
  </>;
}

function Shortages({ s }) {
  if (!s?.available) return <Unavailable part={s} />;
  return <>
    <Grid>
      <MetricCard testId="analytics-shortages" label="Shortage notes" value={num(s.reports)} sub={`${s.verified} from signed-in cooks`} tone={s.reports ? "warn" : "good"} />
      {Object.entries(s.by_reason).map(([k, v]) => <MetricCard key={k} label={REASONS[k] || k} value={num(v)} />)}
    </Grid>
    <Table head={["Day", "Track", "Item", "Reason", "Amount"]}
      rows={s.latest.map(r => [r.business_date, prepTrackLabel(r.track), r.name || "–", REASONS[r.reason] || r.reason, num(r.short_quantity)])} />
  </>;
}

function Waste({ w }) {
  if (!w?.available) return <Unavailable part={w} />;
  return <>
    <Grid>
      <MetricCard testId="analytics-waste" label="Waste records" value={num(w.entries)} sub={`${w.items} items`} tone={w.entries ? "warn" : "good"} />
      {Object.entries(w.by_reason).map(([k, v]) => <MetricCard key={k} label={WASTE[k] || k} value={num(v)} />)}
    </Grid>
    <Table testId="analytics-waste-items" head={["Item", "Kind", "Track", "Records", "Amount"]}
      rows={w.top_items.map(r => [r.name, r.kind === "prep" ? "Prep" : "Purchased", r.track ? prepTrackLabel(r.track) : "–", r.entries, qty(r.quantity, r.unit)])} />
  </>;
}

function Acceptance({ a }) {
  const parts = [["output", "Cook output"], ["prep_counts", "Prep counts"], ["nightly_counts", "Nightly counts"]];
  return <Table testId="analytics-acceptance" head={["Work", "Decided", "Accepted", "Sent back", "Still waiting", "Median wait", "Longest wait"]}
    rows={parts.filter(([k]) => a?.[k]?.available).map(([k, label]) => {
      const p = a[k];
      return [label, p.decided, p.accepted, p.sent_back, p.waiting, wait(p.median_minutes), wait(p.longest_minutes)];
    })} />;
}

function Transfers({ t }) {
  const b = t?.bulk, s = t?.store;
  return <>
    {b?.available && !b.store_wide && <>
      <Grid>
        <MetricCard testId="analytics-bulk" label="Bulk requests" value={num(b.requests)} sub={`${b.accepted} accepted · ${b.open} open · ${b.cancelled} cancelled`} />
        <MetricCard label="Bulk lines short" value={num(b.lines_short)} sub="still owed, or sent but not accepted" tone={b.lines_short ? "warn" : "good"} />
      </Grid>
      <Table testId="analytics-bulk-differences" head={["Run", "From", "To", "Item", "Asked", "Sent", "Held", "Accepted", "Still owed"]}
        rows={b.differences.map(r => [r.run_date, storeName(r.from_store_id), storeName(r.to_store_id), r.name, qty(r.requested, r.unit), qty(r.sent, r.unit), qty(r.held, r.unit), qty(r.accepted, r.unit), qty(r.still_owed, r.unit)])} />
    </>}
    {s?.available && !s.store_wide && <>
      <Grid>
        <MetricCard testId="analytics-transfers" label="Store transfers" value={num(s.transfers)} sub={`${s.received} received · ${s.open} open · ${s.cancelled} cancelled`} />
        <MetricCard label="Received short" value={num(s.received_short)} tone={s.received_short ? "warn" : "good"} />
      </Grid>
      <Table testId="analytics-transfer-differences" head={["Sent", "From", "To", "Item", "Sent", "Received", "Short", "Cost of short"]}
        rows={s.differences.map(r => [r.sent_date, storeName(r.from_store_id), storeName(r.to_store_id), r.name, qty(r.sent, r.unit), qty(r.received, r.unit), qty(r.short, r.unit), r.short_cost === null ? "–" : `$${num(r.short_cost)}`])} />
    </>}
    {!(b?.available && !b.store_wide) && !(s?.available && !s.store_wide) && <Unavailable part={b?.store_wide ? b : s} />}
  </>;
}

function OnTime({ o }) {
  if (!o?.available || o.store_wide) return <Unavailable part={o} />;
  if (!o.has_calendar) return <p className="text-sm text-slate-500">This store has no order calendar.</p>;
  const total = c => Object.values(c).reduce((x, y) => x + y, 0);
  return <>
    <Grid>
      <MetricCard testId="analytics-cycles" label="Order cycles" value={num(o.cycles)} />
      <MetricCard testId="analytics-counts-on-time" label="Counts on time" value={pct(o.counts.done, total(o.counts))} sub={`${o.counts.late} late · ${o.counts.overdue} not done`} tone={o.counts.late || o.counts.overdue ? "warn" : "good"} />
      <MetricCard testId="analytics-orders-on-time" label="Orders on time" value={pct(o.orders.done, total(o.orders))} sub={`${o.orders.late} late · ${o.orders.overdue} not done`} tone={o.orders.late || o.orders.overdue ? "warn" : "good"} />
    </Grid>
    <Table testId="analytics-cycle-list" head={["Cycle", "Count", "Orders"]}
      rows={o.cycle_list.map(c => [c.moved_from ? `${c.cycle_date} (moved from ${c.moved_from})` : c.cycle_date, STATUS[c.count] || c.count,
        c.orders.map(v => `${v.name}: ${STATUS[v.status] || v.status}`).join(" · ")])} />
    <Table head={["Cycle", "What", "Supplier", "Reason"]}
      rows={o.late_reasons.map(n => [n.cycle_date, n.kind === "count_late" ? "Late count" : "Late order", n.name || "–", n.reason])} />
  </>;
}

function DataHealth({ s }) {
  const missing = s.missing_days || [], review = s.needs_review || [];
  if (!s.stale && !missing.length && !review.length) {
    return <p className="text-xs text-slate-500 mb-2" data-testid="analytics-sales-health">Every day in the range has arrived from Toast{s.latest_day ? ` (latest ${s.latest_day})` : ""}.</p>;
  }
  return <div className="text-sm text-jm-warn mb-2" data-testid="analytics-sales-health">
    {s.stale && <p>Toast sales are behind: the latest day saved is {s.latest_day || "none"}. The morning sync may have failed.</p>}
    {missing.length > 0 && <p>Not arrived from Toast yet: {missing.join(", ")}.</p>}
    {review.length > 0 && <p>Needs review: {review.map(r => `${r.business_date} (${r.problems.join(", ") || "check"})`).join("; ")}.</p>}
  </div>;
}

function SaladBar({ b }) {
  return <>
    <Grid>
      <MetricCard testId="analytics-salad-covers" label="Salad Bar covers" value={num(b.covers)} sub="items and add-ons named Salad Bar" />
      <MetricCard label="Salad Bar sales" value={money(b.amount)} />
    </Grid>
    <Table testId="analytics-salad-days" head={["Day", "Covers", "Sales"]} rows={b.by_day.map(r => [r.business_date, num(r.quantity), money(r.amount)])} />
  </>;
}

function Sales({ s }) {
  if (!s?.available || s.store_wide) return <Unavailable part={s} />;
  if (s.track_only) {
    return <>
      <DataHealth s={s} />
      {Number(s.salad_bar.covers) ? <SaladBar b={s.salad_bar} /> : <p className="text-sm text-slate-500">No Salad Bar sales in this range.</p>}
    </>;
  }
  const t = s.totals, b = s.before, since = `vs ${b.start} – ${b.end}`;
  // No change is shown when the earlier days are missing or need review: it would compare against a partial total.
  const vs = (now, then) => b.complete && change(now, then) ? `${change(now, then)} ${since}` : undefined;
  return <>
    <DataHealth s={s} />
    <Grid>
      <MetricCard testId="analytics-net-sales" label="Net sales" value={money(t.net_sales)}
        sub={vs(t.net_sales, b.net_sales) || (b.complete ? `${t.open_days} days open` : `${t.open_days} days open · earlier days incomplete, no comparison`)} />
      <MetricCard testId="analytics-orders" label="Orders" value={num(t.orders)} sub={vs(t.orders, b.orders)} />
      <MetricCard testId="analytics-average-check" label="Average order" value={money(t.average_check)} sub={b.complete && b.average_check ? `${money(b.average_check)} before` : undefined} />
      <MetricCard label="Discounts and refunds" value={money(Number(t.discounts) + Number(t.refunds))} sub={`${money(t.discounts)} discounts · ${money(t.refunds)} refunds`} />
    </Grid>
    {Number(s.salad_bar.covers) > 0 && <SaladBar b={s.salad_bar} />}
    <Table testId="analytics-sales-days" head={["Day", "Net sales", "Orders", "Average order", "Toast data"]}
      rows={s.by_day.map(r => [r.business_date, money(r.net_sales), num(r.orders), money(r.average_check), r.status === "complete" ? "Complete" : "Needs review"])} />
    <Table testId="analytics-top-items" head={["Best sellers", "Sold", "Net sales"]} rows={s.top_items.map(r => [r.name, num(r.quantity), money(r.net_sales)])} />
  </>;
}

// Prep against sales (M6, backend/menu_portions.py): what was made, wasted and counted for each prep item
// against what Toast sales imply was used, through the menu portions owners set.
const signed = (v, unit) => v === null || v === undefined ? "–" : `${Number(v) > 0 ? "+" : ""}${qty(v, unit)}`;

function PrepVsSales({ p, onPortions, showing }) {
  if (!p?.available) return <Unavailable part={p} />;
  const c = p.coverage;
  const incomplete = p.sales_days_complete < p.range_days;
  return <>
    <Grid>
      <MetricCard testId="analytics-portion-coverage" label="Sales covered by portions" value={c.covered_percent === null ? "–" : `${c.covered_percent}%`}
        sub={`${p.missing_count} menu items missing portions`} tone={p.missing_count ? "warn" : "good"} />
      <MetricCard label="Prep items compared" value={num(p.items.filter(r => r.has_portions).length)} sub={`${num(p.item_count)} prep items in the range`} />
      <MetricCard label="Modifiers with portions" value={num(p.modifiers_with_portions)} sub="add-ons that use prep" />
    </Grid>
    {incomplete && <p className="text-sm text-jm-warn mb-2" data-testid="analytics-prep-sales-days">Toast data is complete for {p.sales_days_complete} of {p.range_days} days, so sales may imply too little.</p>}
    <Table testId="analytics-prep-sales" head={["Prep item", "Track", "Made", "Wasted", "Used", "Sales imply", "Gap", "Counts"]}
      rows={p.items.map(r => [r.name, r.track ? prepTrackLabel(r.track) : "–", qty(r.made, r.unit), qty(r.wasted, r.unit), qty(r.used, r.unit),
        r.has_portions ? qty(r.implied, r.unit) : "No portions yet",
        r.gap === null ? "–" : `${signed(r.gap, r.unit)}${r.gap_percent === null ? "" : ` (${r.gap_percent > 0 ? "+" : ""}${r.gap_percent}%)`}`,
        r.counts_used ? `${num(r.opening)} → ${num(r.closing)}` : "Not counted"])} />
    <p className="text-xs text-slate-500 mb-2">Used = made − used in other prep − wasted, plus the change in on-hand when the item was counted the night before the range and on its last day, each after that day's last prep and waste. A positive gap means more left the shelf than sales explain (bigger portions, waste not recorded, staff meals); a negative gap means sales imply more than was made. Bulk sent to or received from another store isn't counted yet.</p>
    <Table testId="analytics-missing-portions" head={["Missing portions", "Sold", "Net sales"]} rows={p.missing_items.map(m => [m.name, num(m.quantity), money(m.amount)])} />
    <button className={btnGhost} onClick={onPortions} data-testid="analytics-portions-toggle">{showing ? "Hide menu portions" : "Menu portions"}</button>
  </>;
}

export { isoDay };

export function AnalyticsTab({ rid }) {
  const [start, setStart] = useState(daysAgo(6));
  const [end, setEnd] = useState(daysAgo(0));
  const [track, setTrack] = useState("");
  const [data, setData] = useState(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const latest = useRef(0);
  const [portions, setPortions] = useState(false);
  const load = () => {
    // Only the newest request may fill the page: an older range or track answering late is dropped.
    const ask = ++latest.current;
    setLoading(true); setError("");
    api.analyticsReport(rid, { start, end, track: track || undefined })
      .then(d => { if (ask === latest.current) setData(d); })
      .catch(e => { if (ask === latest.current) setError(e?.response?.data?.detail || "Analytics could not be loaded"); })
      .finally(() => { if (ask === latest.current) setLoading(false); });
  };
  useEffect(load, [rid, start, end, track]); // eslint-disable-line react-hooks/exhaustive-deps
  return (
    <div data-testid="analytics-tab">
      <PageTitle right={<button className={btnGhost} onClick={load} disabled={loading}>{loading ? "Loading…" : "Refresh"}</button>}>Analytics</PageTitle>
      <div className="flex flex-wrap gap-3 mb-5">
        <Field label="From"><input type="date" className={inpCls} value={start} max={end} onChange={e => setStart(e.target.value)} data-testid="analytics-start" /></Field>
        <Field label="To"><input type="date" className={inpCls} value={end} min={start} onChange={e => setEnd(e.target.value)} data-testid="analytics-end" /></Field>
        <Field label="Track">
          <select className={inpCls} value={track} onChange={e => setTrack(e.target.value)} data-testid="analytics-track">
            <option value="">All tracks</option>
            {prepTracks(rid).map(t => <option key={t.id} value={t.id}>{t.label}</option>)}
          </select>
        </Field>
      </div>
      {error ? <p role="alert" className="text-sm text-jm-bad">{error}</p> : !data ? <EmptyState text="Loading analytics…" /> : <>
        <Section testId="analytics-sales-section" title="Sales" note="From Toast, one business day at a time, counted the way Toast's Sales Summary counts them. Net sales are after discounts and refunds, before tax and tips."><Sales s={data.sales} /></Section>
        <Section testId="analytics-prep-sales-section" title="Prep against sales" note="Each prep item made, wasted and counted against what Toast sales imply was used, through the menu portions. In the item's own unit.">
          <PrepVsSales p={data.prep_vs_sales} onPortions={() => setPortions(!portions)} showing={portions} />
          {portions && data.prep_vs_sales?.available && <div className="mt-3"><MenuPortions rid={rid} onChanged={load} /></div>}
        </Section>
        <Section testId="analytics-throughput" title="Prep made against plan" note="Released prep lists: each task's planned amount against what was made and accepted, in the item's own unit."><Throughput t={data.throughput} /></Section>
        <Section testId="analytics-shortages-section" title="Shortages" note="Notes cooks sent the Shift Leader."><Shortages s={data.shortages} /></Section>
        <Section testId="analytics-waste-section" title="Waste" note="Waste records, including container waste, at their latest correction."><Waste w={data.waste} /></Section>
        <Section testId="analytics-acceptance-section" title="Acceptance timing" note="From when staff sent work in to when a manager accepted or sent it back, by the day it was decided. Counts are store-wide."><Acceptance a={data.acceptance} /></Section>
        <Section testId="analytics-transfers-section" title="Transfers" note="Bulk supply and store-to-store transfers where this store sends or receives."><Transfers t={data.transfers} /></Section>
        <Section testId="analytics-on-time-section" title="Counts and orders on time" note="Each order cycle under the schedule that stood that day, skips and moves included."><OnTime o={data.on_time} /></Section>
      </>}
    </div>
  );
}
