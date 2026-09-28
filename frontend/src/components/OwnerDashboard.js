import React, { useEffect, useState } from "react";
import { ArrowRight, AlertTriangle, TrendingDown, RefreshCw, Check, X, ClipboardCheck, ArrowUp, ArrowDown, Minus } from "lucide-react";
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid, Legend } from "recharts";
import * as api from "../lib/api";
import { fmtMoney, num } from "../lib/calc";
import { MetricCard, PageTitle, Pill, cardCls, btnGhost, btnAcc, btnDanger } from "./common";

// up = getting worse (higher variance / slower), down = improving
function TrendArrow({ dir }) {
  if (!dir) return null;
  if (dir === "up") return <ArrowUp size={12} className="inline text-red-400 ml-1" />;
  if (dir === "down") return <ArrowDown size={12} className="inline text-emerald-400 ml-1" />;
  return <Minus size={12} className="inline text-slate-500 ml-1" />;
}

export function OwnerDashboard({ onOpenLocation, onOpenOrder }) {
  const [data, setData] = useState(null);
  const [prep, setPrep] = useState(null);
  const [pending, setPending] = useState([]);
  const [disc, setDisc] = useState([]);
  const [score, setScore] = useState([]);
  const [err, setErr] = useState("");

  function load() {
    setErr("");
    api.ownerSummary().then(setData).catch(() => setErr("Couldn't load the ownership rollup. Check that the backend is running."));
    api.ownerPrepSummary().then(setPrep).catch(() => {});
    api.ownerOrders().then(setPending).catch(() => {});
    api.ownerDiscrepancies().then(setDisc).catch(() => {});
    api.ownerVendorScorecard().then(setScore).catch(() => {});
  }
  useEffect(load, []);

  async function approve(po) {
    try { await api.approveOrder(po.restaurantId, po.id, "Ownership"); setPending((p) => p.filter((x) => x.id !== po.id)); } catch { /* noop */ }
  }
  async function reject(po) {
    const reason = window.prompt("Reason for rejecting this order?") || "";
    try { await api.rejectOrder(po.restaurantId, po.id, "Ownership", reason); setPending((p) => p.filter((x) => x.id !== po.id)); } catch { /* noop */ }
  }

  if (err) return <div className="text-red-400 text-sm p-8" data-testid="owner-error">{err}</div>;
  if (!data) return <div className="text-slate-500 text-sm p-8" data-testid="owner-loading">Loading ownership rollup…</div>;

  const { stores, totals } = data;
  const chartData = stores.map((s) => ({ name: s.short, "Inventory Value": s.inventoryValue, "30-Day Purchases": s.spend30 }));

  return (
    <div className="fade-slide-in" data-testid="owner-dashboard">
      <PageTitle right={<button className={btnGhost} onClick={load} data-testid="owner-refresh"><RefreshCw size={14} /> Refresh</button>}>
        Ownership Dashboard — All Locations
      </PageTitle>
      <div className="text-xs text-slate-500 -mt-3 mb-5">Consolidated view across Bert's Hometown Grill & Pizzeria, Rudd's Pies and Fries, and Papa Leoni's Pizza · ~$8M combined annual sales.</div>

      <div className="grid gap-3 mb-6" style={{ gridTemplateColumns: "repeat(auto-fit,minmax(190px,1fr))" }}>
        <MetricCard testId="owner-total-inv" label="Total Inventory Value" value={fmtMoney(totals.inventoryValue)} sub="all three locations" />
        <MetricCard testId="owner-total-spend" label="Purchases — Last 30 Days" value={fmtMoney(totals.spend30)} sub="group-wide" />
        <MetricCard testId="owner-total-alerts" label="Items Below Par" value={totals.orderAlerts} sub="need ordering" tone={totals.orderAlerts > 0 ? "warn" : "good"} />
        <MetricCard testId="owner-total-waste" label="Waste — Last 30 Days" value={fmtMoney(totals.waste30)} sub="logged removals" tone={totals.waste30 > 0 ? "warn" : "good"} />
      </div>

      {pending.length > 0 && (
        <div className={`${cardCls} p-5 mb-6`} data-testid="owner-pending-approvals" style={{ borderTopWidth: 2, borderTopColor: "#F59E0B" }}>
          <div className="flex items-center gap-2 mb-3">
            <ClipboardCheck size={16} className="text-amber-400" />
            <span className="text-[11px] uppercase tracking-[0.08em] text-slate-400 font-bold">Purchase Orders Awaiting Your Approval ({pending.length})</span>
          </div>
          <div className="flex flex-col gap-2.5">
            {pending.map((po) => (
              <div key={po.id} className="flex items-center justify-between gap-3 flex-wrap bg-[#0F1626] border border-[#28354A] rounded-lg px-3.5 py-3" data-testid={`owner-po-${po.id}`}>
                <div>
                  <div className="text-sm font-semibold text-slate-100">{po.restaurantName} · {po.vendor}</div>
                  <div className="text-[11px] text-slate-500">{po.lines.length} line{po.lines.length !== 1 ? "s" : ""} · {fmtMoney(po.total)}{po.createdBy ? ` · submitted by ${po.createdBy}` : ""}</div>
                </div>
                <div className="flex gap-1.5">
                  <button className={btnAcc} data-testid={`owner-approve-${po.id}`} onClick={() => approve(po)}><Check size={13} /> Approve</button>
                  <button className={btnDanger} data-testid={`owner-reject-${po.id}`} onClick={() => reject(po)}><X size={13} /> Reject</button>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {disc.length > 0 && (
        <div className={`${cardCls} p-5 mb-6`} data-testid="owner-discrepancies" style={{ borderTopWidth: 2, borderTopColor: "#EF4444" }}>
          <div className="flex items-center gap-2 mb-3">
            <TrendingDown size={16} className="text-red-400" />
            <span className="text-[11px] uppercase tracking-[0.08em] text-slate-400 font-bold">Delivery Discrepancies ({disc.length})</span>
          </div>
          <div className="flex flex-col gap-2.5">
            {disc.map((d) => (
              <div key={d.orderId} onClick={() => onOpenOrder?.(d.restaurantId, d.orderId)} className="bg-[#0F1626] border border-red-500/20 rounded-lg px-3.5 py-3 cursor-pointer hover:border-red-500/50 transition" data-testid={`disc-${d.orderId}`} title="Open this purchase order">
                <div className="flex justify-between items-center gap-2 flex-wrap">
                  <div className="text-sm font-semibold text-slate-100">{d.restaurantName} · {d.vendor} · Invoice {d.invoiceNumber}</div>
                  <div className="flex items-center gap-2">
                    <Pill color="#EF4444" bg="rgba(239,68,68,0.12)">{d.flaggedCount} flagged</Pill>
                    <ArrowRight size={13} className="text-slate-500" />
                  </div>
                </div>
                <div className="mt-1.5 flex flex-col gap-0.5">
                  {d.lines.map((l) => (
                    <div key={l.controlNumber} className="text-[11px] text-slate-400 flex justify-between gap-3">
                      <span><span style={{ color: "var(--acc)" }} className="font-bold">{l.controlNumber}</span> {l.name}</span>
                      <span className="text-amber-400 whitespace-nowrap">{!l.onInvoice ? "not on invoice" : [l.qtyDiff ? `qty ${l.qtyDiff > 0 ? "+" : ""}${num(l.qtyDiff, 1)}` : "", l.priceDiff ? `price ${l.priceDiff > 0 ? "+" : ""}${fmtMoney(l.priceDiff)}` : ""].filter(Boolean).join(", ")}</span>
                    </div>
                  ))}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {score.length > 0 && (
        <div className={`${cardCls} p-5 mb-6`} data-testid="owner-vendor-scorecard">
          <div className="text-[11px] uppercase tracking-[0.08em] text-slate-500 font-bold mb-3">Vendor Scorecard — received orders across all locations</div>
          <div className="overflow-x-auto">
            <table className="ops-table">
              <thead><tr><th>Vendor</th><th>Locations</th><th>Received</th><th>Avg Lead (days)</th><th>Price Accuracy</th><th>Avg Price Var</th><th>Total Spend</th></tr></thead>
              <tbody>
                {score.map((s) => (
                  <tr key={s.vendor} data-testid={`scorecard-${s.vendor}`}>
                    <td className="font-semibold text-slate-200">{s.vendor}</td>
                    <td className="text-slate-400 text-xs">{s.locations.join(", ")}</td>
                    <td className="num">{s.receivedOrders}</td>
                    <td className="num">{s.avgLeadDays != null ? s.avgLeadDays : "—"}<TrendArrow dir={s.leadTrend} /></td>
                    <td className="num" style={{ color: s.priceAccuratePct == null ? "#94A3B8" : (s.priceAccuratePct >= 90 ? "#10B981" : s.priceAccuratePct >= 70 ? "#F59E0B" : "#EF4444") }}>{s.priceAccuratePct != null ? `${s.priceAccuratePct}%` : "—"}</td>
                    <td className="num">{s.avgPriceVariance != null ? fmtMoney(s.avgPriceVariance) : "—"}<TrendArrow dir={s.priceVarTrend} /></td>
                    <td className="num font-bold">{fmtMoney(s.totalSpend)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="text-[10.5px] text-slate-500 mt-2">Lead time = days from "sent to supplier" to "received". Price accuracy = share of invoice-matched lines with no price discrepancy (needs an invoice # at receipt). Arrows compare the last 45 days vs the prior 45 days — <span className="text-red-400">▲</span> worse, <span className="text-emerald-400">▼</span> better.</div>
        </div>
      )}

      <div className="grid gap-4 mb-6" style={{ gridTemplateColumns: "repeat(auto-fit,minmax(300px,1fr))" }}>
        {stores.map((s) => (
          <div key={s.id} className={`${cardCls} p-5`} data-testid={`store-card-${s.id}`} style={{ borderTopWidth: 2, borderTopColor: s.accent }}>
            <div className="flex items-start justify-between gap-2 mb-3">
              <div>
                <div className="font-display font-bold text-slate-100">{s.name}</div>
                <div className="text-[11px] text-slate-500 mt-0.5">{s.itemCount} inventory items · {s.dishCount} menu items</div>
              </div>
              <span className="w-2.5 h-2.5 rounded-full mt-1 flex-shrink-0" style={{ background: s.accent }} />
            </div>
            <div className="grid grid-cols-2 gap-2 mb-3 text-xs">
              <div className="bg-[#0F1626] rounded-lg px-2.5 py-2 border border-[#28354A]"><div className="text-slate-500 text-[10px] uppercase font-bold">Inventory</div><div className="num font-bold text-slate-200">{fmtMoney(s.inventoryValue)}</div></div>
              <div className="bg-[#0F1626] rounded-lg px-2.5 py-2 border border-[#28354A]"><div className="text-slate-500 text-[10px] uppercase font-bold">30d Purchases</div><div className="num font-bold text-slate-200">{fmtMoney(s.spend30)}</div></div>
              <div className="bg-[#0F1626] rounded-lg px-2.5 py-2 border border-[#28354A]"><div className="text-slate-500 text-[10px] uppercase font-bold">Avg Food Cost</div><div className="num font-bold" style={{ color: s.avgFoodCost !== null && s.avgFoodCost > 32 ? "#EF4444" : "#10B981" }}>{s.avgFoodCost !== null ? `${num(s.avgFoodCost, 1)}%` : "—"}</div></div>
              <div className="bg-[#0F1626] rounded-lg px-2.5 py-2 border border-[#28354A]"><div className="text-slate-500 text-[10px] uppercase font-bold">Below Par</div><div className="num font-bold" style={{ color: s.orderAlerts > 0 ? "#F59E0B" : "#10B981" }}>{s.orderAlerts} items</div></div>
            </div>
            {prep && (() => { const p = prep.stores.find((x) => x.id === s.id); return p ? (
              <div className="flex gap-1.5 flex-wrap mb-3" data-testid={`prep-summary-${s.id}`}>
                <Pill color={p.countStatus === "submitted" ? "#10B981" : "#64748B"} bg={p.countStatus === "submitted" ? "rgba(16,185,129,0.12)" : "#1E293B"}>Tonight's count: {p.countStatus}</Pill>
                <Pill color="#06B6D4" bg="rgba(6,182,212,0.12)">Tasks {p.tasksDone}/{p.tasksTotal}</Pill>
                <Pill color="#94A3B8" bg="#1E293B">7d prep {fmtMoney(p.prepCost7d)}</Pill>
              </div>
            ) : null; })()}
            {(s.orderAlerts > 0 || s.prepLow > 0 || s.waste30 > 0) && (
              <div className="flex gap-1.5 flex-wrap mb-3">
                {s.orderAlerts > 0 && <Pill color="#F59E0B" bg="rgba(245,158,11,0.12)"><AlertTriangle size={10} className="inline -mt-0.5" /> {s.orderAlerts} to order</Pill>}
                {s.prepLow > 0 && <Pill color="#3B82F6" bg="rgba(59,130,246,0.12)">{s.prepLow} prep below par</Pill>}
                {s.waste30 > 0 && <Pill color="#EF4444" bg="rgba(239,68,68,0.12)"><TrendingDown size={10} className="inline -mt-0.5" /> {fmtMoney(s.waste30)} waste</Pill>}
              </div>
            )}
            {s.topCostDishes.length > 0 && (
              <div className="mb-3">
                <div className="text-[10px] uppercase tracking-wide text-slate-500 font-bold mb-1">Highest Food Cost</div>
                {s.topCostDishes.map((d) => (
                  <div key={d.code + d.name} className="flex justify-between text-xs py-1 border-b border-[#22304A] last:border-0">
                    <span className="text-slate-300">{d.code} {d.name}</span>
                    <span className="num font-bold" style={{ color: d.pct !== null && d.pct > d.target ? "#EF4444" : "#10B981" }}>{d.pct !== null ? `${num(d.pct, 1)}%` : "—"}</span>
                  </div>
                ))}
              </div>
            )}
            <button className={btnGhost} onClick={() => onOpenLocation(s.id)} data-testid={`open-location-${s.id}`}>
              Open location <ArrowRight size={13} />
            </button>
          </div>
        ))}
      </div>

      <div className={`${cardCls} p-5`} data-testid="owner-comparison-chart">
        <div className="text-[11px] uppercase tracking-[0.08em] text-slate-500 font-bold mb-3">Location Comparison — Inventory on Hand vs. 30-Day Purchases</div>
        <div className="h-64">
          <ResponsiveContainer width="100%" height="100%" minWidth={280} minHeight={240}>
            <BarChart data={chartData} margin={{ top: 4, right: 8, left: 8, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#22304A" />
              <XAxis dataKey="name" stroke="#64748B" tick={{ fill: "#94A3B8", fontSize: 12 }} />
              <YAxis stroke="#64748B" tick={{ fill: "#94A3B8", fontSize: 11 }} tickFormatter={(v) => `$${(v / 1000).toFixed(1)}k`} />
              <Tooltip contentStyle={{ background: "#161F30", border: "1px solid #28354A", borderRadius: 8, fontSize: 12 }} formatter={(v) => fmtMoney(v)} />
              <Legend wrapperStyle={{ fontSize: 12 }} />
              <Bar dataKey="Inventory Value" fill="#06B6D4" radius={[4, 4, 0, 0]} />
              <Bar dataKey="30-Day Purchases" fill="#F97316" radius={[4, 4, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>
    </div>
  );
}
