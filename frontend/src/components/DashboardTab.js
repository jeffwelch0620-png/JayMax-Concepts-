import React, { useMemo, useState } from "react";
import { Search } from "lucide-react";
import { buildPeriodReport, isCountActive, isOrderEnabled, statusOf, preferredSku, fmtMoney, fmtDate, num } from "../lib/calc";
import { MetricCard, PageTitle, EmptyState, Field, SectionLabel, cardCls, inpCls } from "./common";
import { DashboardPrepWindow } from "./DashboardPrepWindow";

export function DashboardTab({ rid, items, purchases, dishes, adjustments, salesPeriod, reportingPeriods, onOpenHistory, flaggedOnly, setFlaggedOnly }) {
  const [selectedPeriodId, setSelectedPeriodId] = useState("current");
  const [search, setSearch] = useState("");
  const [areaFilter, setAreaFilter] = useState("All");
  const [showInactive, setShowInactive] = useState(false);
  const selectedPeriod = selectedPeriodId === "current" ? salesPeriod : (reportingPeriods.find((p) => p.id === selectedPeriodId) || salesPeriod);
  const report = useMemo(() => buildPeriodReport(selectedPeriod, items, purchases, dishes, adjustments), [selectedPeriod, items, purchases, dishes, adjustments]);

  const filtered = useMemo(() => items.filter((it) => {
    const q = search.toLowerCase();
    const mS = it.name.toLowerCase().includes(q) || it.controlNumber.toLowerCase().includes(q);
    const mA = areaFilter === "All" || it.storageArea === areaFilter;
    const mI = showInactive || isCountActive(it);
    const mF = !flaggedOnly || (isOrderEnabled(it) && statusOf(it).key !== "ok");
    return mS && mA && mI && mF;
  }), [items, search, areaFilter, showInactive, flaggedOnly]);
  const areaNames = useMemo(() => [...new Set(items.map((it) => it.storageArea))].sort(), [items]);
  const topVariance = [...report.trackedRows].filter((r) => r.unexplainedCost !== null).sort((a, b) => Math.abs(b.unexplainedCost) - Math.abs(a.unexplainedCost)).slice(0, 8);
  const wasteRows = Object.entries(report.wasteByReason).sort((a, b) => b[1] - a[1]);
  const countCoverage = report.trackedRows.length ? Math.round((report.usableRows.length / report.trackedRows.length) * 100) : 0;

  if (items.length === 0) return <EmptyState text="No items yet. Head to Item Setup to add your first item." />;

  return (
    <div className="fade-slide-in" data-testid="dashboard-tab">
      <div className="flex justify-between gap-3 flex-wrap items-end mb-4">
        <div>
          <PageTitle>Management Dashboard</PageTitle>
          <div className="text-slate-500 text-xs -mt-4">Period reporting uses saved beginning/ending counts, purchases, recipe-driven theoretical usage, and logged adjustments.</div>
        </div>
        <Field label="Reporting Period">
          <select data-testid="period-select" className={inpCls} value={selectedPeriodId} onChange={(e) => setSelectedPeriodId(e.target.value)}>
            <option value="current">Current Working Period — {fmtDate(salesPeriod.periodStart)} to {fmtDate(salesPeriod.periodEnd)}</option>
            {[...reportingPeriods].sort((a, b) => (b.periodEnd || "").localeCompare(a.periodEnd || "")).map((p) => (
              <option key={p.id} value={p.id}>{p.name || `${fmtDate(p.periodStart)} – ${fmtDate(p.periodEnd)}`}</option>
            ))}
          </select>
        </Field>
      </div>

      <div className="grid gap-3 mb-5" style={{ gridTemplateColumns: "repeat(auto-fit,minmax(170px,1fr))" }}>
        <MetricCard testId="metric-purchases" label="Purchases" value={fmtMoney(report.purchaseSpend)} sub={`${report.periodPurchases.length} invoice lines`} />
        <MetricCard testId="metric-actual-cogs" label="Actual COGS" value={report.usableRows.length ? fmtMoney(report.actualCogs) : "Needs counts"} sub={`${countCoverage}% tracked-count coverage`} tone={report.usableRows.length ? "normal" : "warn"} />
        <MetricCard testId="metric-theo-cogs" label="Theoretical COGS" value={fmtMoney(report.theoreticalCogs)} sub="from menu sales + recipes" />
        <MetricCard testId="metric-variance" label="Unexplained Variance" value={report.usableRows.length ? fmtMoney(report.unexplainedCost) : "Needs counts"} sub="after known adjustments" tone={Math.abs(report.unexplainedCost) > 0 ? "warn" : "good"} />
        <MetricCard testId="metric-inv-value" label="Live Inventory Value" value={fmtMoney(report.liveInventoryValue)} sub="current stock × preferred price" />
        <MetricCard testId="metric-order-exposure" label="Next Order Exposure" value={fmtMoney(report.orderExposure)} sub="preferred-vendor estimate" />
      </div>

      <DashboardPrepWindow items={items} dishes={dishes} rid={rid} />

      {report.usableRows.length === 0 && (
        <div className="bg-amber-500/10 border border-amber-500/40 rounded-lg px-3.5 py-2.5 text-amber-300 text-xs mb-5" data-testid="counts-incomplete-banner">
          <b>Period counts are incomplete.</b> Purchases, theoretical usage, waste and live inventory can still be shown, but Actual COGS and variance require beginning + ending counts in Sales Tracking.
        </div>
      )}

      <div className="grid gap-4 mb-5" style={{ gridTemplateColumns: "repeat(auto-fit,minmax(330px,1fr))" }}>
        <div className={`${cardCls} p-5`} data-testid="variance-card">
          <SectionLabel>Top Unexplained Variance</SectionLabel>
          {topVariance.length === 0 ? <div className="text-slate-500 text-[13px]">No completed variance rows for this period.</div> : (
            <table className="ops-table"><thead><tr><th>Item</th><th>Portions</th><th>$ Impact</th></tr></thead>
              <tbody>{topVariance.map((r) => (
                <tr key={r.item.controlNumber}>
                  <td><button onClick={() => onOpenHistory(r.item.controlNumber)} className="font-bold hover:underline" style={{ color: "var(--acc)" }}>{r.item.controlNumber}</button> — {r.item.name}</td>
                  <td className="num">{num(r.unexplainedPortions, 1)}</td>
                  <td className="num font-bold" style={{ color: (r.unexplainedCost || 0) > 0 ? "#EF4444" : "#10B981" }}>{fmtMoney(r.unexplainedCost)}</td>
                </tr>))}
              </tbody></table>
          )}
        </div>
        <div className={`${cardCls} p-5`} data-testid="waste-card">
          <SectionLabel>Waste / Adjustments by Reason</SectionLabel>
          {wasteRows.length === 0 ? <div className="text-slate-500 text-[13px]">No adjustments logged in this period.</div> : (
            <div>{wasteRows.map(([reason, value]) => (
              <div key={reason} className="flex justify-between gap-3 py-2 border-b border-[#22304A] text-sm">
                <span className="text-slate-300">{reason}</span><b className="num">{fmtMoney(value)}</b>
              </div>))}
            </div>
          )}
        </div>
      </div>

      <div className="grid gap-4 mb-6" style={{ gridTemplateColumns: "repeat(auto-fit,minmax(330px,1fr))" }}>
        <div className={`${cardCls} p-5`} data-testid="price-alerts-card">
          <SectionLabel>Price Change Alerts (≥5%)</SectionLabel>
          {report.priceAlerts.length === 0 ? <div className="text-slate-500 text-[13px]">No material two-purchase price changes found.</div> : (
            <table className="ops-table"><thead><tr><th>Item</th><th>Prior</th><th>Latest</th><th>Change</th></tr></thead>
              <tbody>{report.priceAlerts.slice(0, 8).map((a) => (
                <tr key={a.item.controlNumber}>
                  <td>{a.item.controlNumber} — {a.item.name}</td>
                  <td className="num">{fmtMoney(a.prior.unitCost)}</td>
                  <td className="num">{fmtMoney(a.latest.unitCost)}</td>
                  <td className="num font-bold" style={{ color: a.pct > 0 ? "#EF4444" : "#10B981" }}>{a.pct > 0 ? "+" : ""}{num(a.pct, 1)}%</td>
                </tr>))}
              </tbody></table>
          )}
        </div>
        <div className={`${cardCls} p-5`} data-testid="food-cost-variance-card">
          <SectionLabel>Menu Profitability — Highest Food Cost %</SectionLabel>
          {report.menuProfitability.length === 0 ? <div className="text-slate-500 text-[13px]">Add menu prices and recipe ingredients to calculate profitability.</div> : (
            <table className="ops-table"><thead><tr><th>Menu Item</th><th>Plate Cost</th><th>Price</th><th>Food Cost</th></tr></thead>
              <tbody>{report.menuProfitability.slice(0, 8).map((m) => (
                <tr key={m.recipe.id}>
                  <td>{m.recipe.menuCode || "—"} — {m.recipe.name}</td>
                  <td className="num">{fmtMoney(m.cost)}</td>
                  <td className="num">{fmtMoney(m.price)}</td>
                  <td className="num font-bold" style={{ color: m.foodCostPct !== null && m.foodCostPct > (Number(m.recipe.targetPct) || 30) ? "#EF4444" : "#10B981" }}>{m.foodCostPct === null ? "—" : `${num(m.foodCostPct, 1)}%`}</td>
                </tr>))}
              </tbody></table>
          )}
        </div>
      </div>

      <SectionLabel>Live Inventory Status</SectionLabel>
      {flaggedOnly && (
        <div className="flex items-center justify-between bg-red-500/10 border border-red-500/40 rounded-lg px-3.5 py-2 mb-3.5 text-[13px] text-red-400 font-semibold" data-testid="flagged-filter-banner">
          <span>Showing only order-enabled items that need attention</span>
          <button onClick={() => setFlaggedOnly(false)} className="underline font-bold" data-testid="clear-flagged-filter">Clear filter</button>
        </div>
      )}
      <div className="flex gap-2.5 mb-3.5 flex-wrap items-center">
        <div className="relative flex-1 min-w-[220px]">
          <Search size={15} className="absolute left-2.5 top-2.5 text-slate-500" />
          <input data-testid="inventory-search" className={`${inpCls} w-full pl-8`} placeholder="Search name or control #…" value={search} onChange={(e) => setSearch(e.target.value)} />
        </div>
        <select data-testid="area-filter" className={inpCls} value={areaFilter} onChange={(e) => setAreaFilter(e.target.value)}>
          <option value="All">All Storage Areas</option>
          {areaNames.map((a) => <option key={a} value={a}>{a}</option>)}
        </select>
        <label className="text-[13px] flex items-center gap-1.5 text-slate-400"><input type="checkbox" checked={showInactive} onChange={(e) => setShowInactive(e.target.checked)} /> Show excluded from count</label>
        <label className="text-[13px] flex items-center gap-1.5 text-slate-400"><input type="checkbox" data-testid="flagged-only-toggle" checked={flaggedOnly} onChange={(e) => setFlaggedOnly(e.target.checked)} /> Needs attention only</label>
      </div>
      <div className={`${cardCls} overflow-hidden`} data-testid="inventory-status-table">
        <div className="overflow-x-auto">
          <table className="ops-table">
            <thead><tr><th></th><th>Item Code</th><th>Item</th><th>Area</th><th>Vendor</th><th>Stock</th><th>Par</th></tr></thead>
            <tbody>
              {filtered.map((it) => {
                const st = statusOf(it), pref = preferredSku(it);
                return (
                  <tr key={it.controlNumber} style={{ opacity: isCountActive(it) ? 1 : 0.5 }} data-testid={`inventory-row-${it.controlNumber}`}>
                    <td><span className="w-2.5 h-2.5 rounded-full inline-block" style={{ background: isOrderEnabled(it) ? st.color : "#475569" }} title={st.label} /></td>
                    <td><button onClick={() => onOpenHistory(it.controlNumber)} className="font-bold hover:underline" style={{ color: "var(--acc)" }}>{it.controlNumber}</button></td>
                    <td className="font-semibold text-slate-200">{it.name}</td>
                    <td>{it.storageArea}</td>
                    <td>{pref?.vendor || "—"}</td>
                    <td className="num">{num(it.currentStock)} {it.purchaseUnit}</td>
                    <td className="num">{num(it.par)} {it.purchaseUnit}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
