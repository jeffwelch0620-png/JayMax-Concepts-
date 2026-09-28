import React, { useEffect, useRef, useState } from "react";
import { Save, Plus } from "lucide-react";
import { normalizeRecipeSchema, rawPortionsForRecipe, itemDerived, adjustmentSignedPortions, todayISO, fmtDate, num, workweekRange, shiftWorkweek } from "../lib/calc";
import { PageTitle, EmptyState, Field, SectionLabel, Pill, cardCls, inpCls, btnAcc, btnGhost } from "./common";

export function SalesTrackingTab({ items, dishes, purchases, adjustments, salesPeriod, persist, reportingPeriods, persistReportingPeriods, showToast }) {
  const trackedItems = items.filter((it) => it.salesTracked);
  const [local, setLocal] = useState(salesPeriod);
  const saveTimer = useRef(null);
  // Always holds the latest `local` so the unmount cleanup below (a `[]`-deps
  // effect, which only ever sees the `local` from the FIRST render) can flush
  // the real pending edit instead of a stale one.
  const localRef = useRef(local);
  localRef.current = local;

  useEffect(() => { setLocal(salesPeriod); }, [salesPeriod]);
  useEffect(() => () => {
    // A pending debounced save must be FLUSHED on unmount (e.g. switching tabs),
    // not just cancelled — cancelling silently discards the user's last edit.
    if (saveTimer.current) {
      clearTimeout(saveTimer.current);
      persist(localRef.current);
    }
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  function queuePersist(next) {
    setLocal(next);
    clearTimeout(saveTimer.current);
    saveTimer.current = setTimeout(() => persist(next), 700);
  }

  function updateDishSales(dishId, val) { queuePersist({ ...local, dishSales: { ...local.dishSales, [dishId]: val } }); }
  function updateItemCount(cn, field, val) {
    const current = local.itemCounts[cn] || {};
    queuePersist({ ...local, itemCounts: { ...local.itemCounts, [cn]: { ...current, [field]: val } } });
  }
  function updatePeriod(field, val) { queuePersist({ ...local, [field]: val }); }

  async function savePeriodSnapshot() {
    clearTimeout(saveTimer.current);
    await persist(local);
    if (!local.periodStart || !local.periodEnd) { showToast("Choose a start and end date first"); return; }
    const existing = reportingPeriods.find((p) => p.periodStart === local.periodStart && p.periodEnd === local.periodEnd);
    const snapshot = {
      ...JSON.parse(JSON.stringify(local)),
      id: existing?.id || ("period_" + Date.now().toString(36)),
      name: existing?.name || `${fmtDate(local.periodStart)} – ${fmtDate(local.periodEnd)}`,
      savedAt: new Date().toISOString(), status: "closed",
    };
    const next = existing ? reportingPeriods.map((p) => p.id === existing.id ? snapshot : p) : [...reportingPeriods, snapshot];
    await persistReportingPeriods(next);
    showToast(existing ? "Reporting period updated" : "Reporting period saved");
  }

  async function loadPeriodSnapshot(id) {
    const p = reportingPeriods.find((x) => x.id === id);
    if (!p) return;
    const next = { periodStart: p.periodStart, periodEnd: p.periodEnd, dishSales: { ...(p.dishSales || {}) }, itemCounts: { ...(p.itemCounts || {}) } };
    setLocal(next);
    await persist(next);
    showToast("Reporting period loaded into working period");
  }

  async function startNextWorkweek() {
    const cur = local.periodEnd ? new Date(local.periodEnd + "T00:00:00") : new Date();
    const start = new Date(cur); start.setDate(start.getDate() + 1);
    const end = new Date(start); end.setDate(end.getDate() + 6);
    const iso = (d) => new Date(d.getTime() - d.getTimezoneOffset() * 60000).toISOString().slice(0, 10);
    const next = { periodStart: iso(start), periodEnd: iso(end), dishSales: {}, itemCounts: {} };
    setLocal(next);
    await persist(next);
    showToast("New workweek period started (Wednesday–Tuesday)");
  }

  const thisWW = workweekRange();
  const lastWW = shiftWorkweek(thisWW, -1);
  const onThisWW = local.periodStart === thisWW.start && local.periodEnd === thisWW.end;
  const onLastWW = local.periodStart === lastWW.start && local.periodEnd === lastWW.end;
  const dayCount = local.periodStart && local.periodEnd ? Math.round((new Date(local.periodEnd) - new Date(local.periodStart)) / 86400000) + 1 : 0;
  function applyRange(range) {
    queuePersist({ ...local, periodStart: range.start, periodEnd: range.end });
    showToast(`Period set: ${fmtDate(range.start)} – ${fmtDate(range.end)}`);
  }

  const periodPurchaseQty = (cn) => purchases
    .filter((p) => p.controlNumber === cn && p.invoiceDate >= local.periodStart && p.invoiceDate <= local.periodEnd)
    .reduce((s, p) => s + (Number(p.qty) || 0), 0);
  const periodAdjustments = (cn) => adjustments
    .filter((a) => a.controlNumber === cn && a.date >= local.periodStart && a.date <= local.periodEnd);

  const normalizedRecipes = dishes.map(normalizeRecipeSchema);
  const rows = trackedItems.map((it) => {
    const d = itemDerived(it);
    let theoreticalPortions = 0;
    normalizedRecipes.filter((dish) => dish.recipeType !== "prep").forEach((dish) => {
      const qtySold = Number(local.dishSales[dish.id]) || 0;
      theoreticalPortions += rawPortionsForRecipe(dish, it.controlNumber, items, normalizedRecipes) * qtySold;
    });
    const counts = local.itemCounts[it.controlNumber] || {};
    const beginning = counts.beginning !== undefined && counts.beginning !== "" ? Number(counts.beginning) : null;
    const ending = counts.ending !== undefined && counts.ending !== "" ? Number(counts.ending) : null;
    const purchased = periodPurchaseQty(it.controlNumber);
    const actualUnits = (beginning !== null && ending !== null) ? (beginning + purchased - ending) : null;
    const actualPortions = actualUnits !== null ? actualUnits * d.portionsPerUnit : null;
    const delta = actualPortions !== null ? actualPortions - theoreticalPortions : null;
    const explainedPortions = periodAdjustments(it.controlNumber).reduce((sum, a) => sum + adjustmentSignedPortions(a, it), 0);
    const unexplainedDelta = delta !== null ? delta - explainedPortions : null;
    const unexplainedPct = (unexplainedDelta !== null && theoreticalPortions > 0) ? (unexplainedDelta / theoreticalPortions) * 100 : null;
    return { it, theoreticalPortions, purchased, actualPortions, delta, explainedPortions, unexplainedDelta, unexplainedPct, hasCounts: beginning !== null && ending !== null };
  });

  if (trackedItems.length === 0) return <EmptyState text="No items are flagged for sales tracking yet. Toggle 'Track against Toast sales' on an item in Item Setup." />;

  return (
    <div className="fade-slide-in" data-testid="sales-tab">
      <PageTitle>Sales Tracking — Actual Use vs. Sales</PageTitle>

      <div className={`${cardCls} p-5 mb-5`}>
        <SectionLabel>Period</SectionLabel>
        <div className="flex gap-2 flex-wrap mb-3 items-center" data-testid="period-presets">
          <button className={onThisWW ? btnAcc : btnGhost} onClick={() => applyRange(thisWW)} data-testid="preset-this-workweek">This Workweek (Wed–Tue)</button>
          <button className={onLastWW ? btnAcc : btnGhost} onClick={() => applyRange(lastWW)} data-testid="preset-last-workweek">Last Workweek</button>
          {!onThisWW && !onLastWW && <Pill testId="custom-range-pill" color="#06B6D4" bg="rgba(6,182,212,0.12)">Custom range</Pill>}
          <span className="text-xs text-slate-500" data-testid="period-range-label">{fmtDate(local.periodStart)} – {fmtDate(local.periodEnd)}{dayCount ? ` · ${dayCount} days` : ""}</span>
        </div>
        <div className="flex gap-3 flex-wrap mb-1">
          <Field label="Custom Range — Start"><input type="date" className={inpCls} data-testid="period-start" value={local.periodStart} onChange={(e) => updatePeriod("periodStart", e.target.value)} /></Field>
          <Field label="Custom Range — End"><input type="date" className={inpCls} data-testid="period-end" value={local.periodEnd} onChange={(e) => updatePeriod("periodEnd", e.target.value)} /></Field>
        </div>
        <div className="flex gap-2 flex-wrap mt-3">
          <button className={btnAcc} onClick={savePeriodSnapshot} data-testid="save-period-button"><Save size={14} /> Save / Close Period</button>
          <button className={btnGhost} onClick={startNextWorkweek} data-testid="next-period-button"><Plus size={14} /> Start Next Workweek (Wed–Tue)</button>
          {reportingPeriods.length > 0 && (
            <select className={inpCls} defaultValue="" data-testid="load-period-select" onChange={(e) => { if (e.target.value) loadPeriodSnapshot(e.target.value); e.target.value = ""; }}>
              <option value="">Load saved period…</option>
              {[...reportingPeriods].sort((a, b) => (b.periodEnd || "").localeCompare(a.periodEnd || "")).map((p) => (
                <option key={p.id} value={p.id}>{p.name || `${fmtDate(p.periodStart)} – ${fmtDate(p.periodEnd)}`}</option>
              ))}
            </select>
          )}
        </div>
        <div className="text-xs text-slate-500 mt-2">Purchases logged in Invoice Master within this window are pulled in automatically. Entries auto-save as you type. Save/Close preserves this period's sales and beginning/ending counts for dashboard reporting.</div>
      </div>

      {dishes.filter((d) => (d.recipeType || "menu") !== "prep").length > 0 && (
        <div className={`${cardCls} p-5 mb-5`}>
          <SectionLabel>Toast Sales — Qty Sold per Dish</SectionLabel>
          <table className="ops-table">
            <thead><tr><th>Dish</th><th>Qty Sold (Toast)</th></tr></thead>
            <tbody>
              {dishes.filter((d) => (d.recipeType || "menu") !== "prep").map((d) => (
                <tr key={d.id}>
                  <td className="font-semibold text-slate-200">{d.name}</td>
                  <td><input type="number" step="1" className={`${inpCls} w-24`} data-testid={`dish-sales-${d.id}`} value={local.dishSales[d.id] ?? ""} onChange={(e) => updateDishSales(d.id, e.target.value)} /></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <div className={`${cardCls} p-5 mb-5`}>
        <SectionLabel>Period Counts (Purchase Units)</SectionLabel>
        <table className="ops-table">
          <thead><tr><th>Item</th><th>Beginning Count</th><th>Ending Count</th><th>Purchased (period)</th></tr></thead>
          <tbody>
            {trackedItems.map((it) => {
              const counts = local.itemCounts[it.controlNumber] || {};
              return (
                <tr key={it.controlNumber}>
                  <td className="font-semibold text-slate-200">{it.controlNumber} — {it.name}</td>
                  <td><input type="number" step="0.1" className={`${inpCls} w-24`} data-testid={`beginning-${it.controlNumber}`} value={counts.beginning ?? ""} onChange={(e) => updateItemCount(it.controlNumber, "beginning", e.target.value)} /></td>
                  <td><input type="number" step="0.1" className={`${inpCls} w-24`} data-testid={`ending-${it.controlNumber}`} value={counts.ending ?? ""} onChange={(e) => updateItemCount(it.controlNumber, "ending", e.target.value)} /></td>
                  <td className="num">{num(periodPurchaseQty(it.controlNumber))} {it.purchaseUnit}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      <SectionLabel>Variance</SectionLabel>
      <div className={`${cardCls} overflow-hidden`}>
        <div className="overflow-x-auto">
          <table className="ops-table" data-testid="variance-table">
            <thead><tr><th>Item</th><th>Theoretical</th><th>Actual</th><th>Raw Delta</th><th>Explained Adjustments</th><th>Unexplained</th><th>Unexplained %</th></tr></thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.it.controlNumber}>
                  <td className="font-semibold text-slate-200">{r.it.controlNumber} — {r.it.name}</td>
                  <td className="num">{num(r.theoreticalPortions, 1)}</td>
                  <td className="num">{r.hasCounts ? num(r.actualPortions, 1) : <span className="text-slate-500">enter counts</span>}</td>
                  <td className="num">{r.delta !== null ? num(r.delta, 1) : "—"}</td>
                  <td className="num">{num(r.explainedPortions, 1)}</td>
                  <td className="num font-bold">{r.unexplainedDelta !== null ? num(r.unexplainedDelta, 1) : "—"}</td>
                  <td>
                    {r.unexplainedPct !== null ? (
                      <span className="num font-bold" style={{ color: Math.abs(r.unexplainedPct) < 10 ? "#10B981" : (r.unexplainedPct > 0 ? "#EF4444" : "#F59E0B") }}>
                        {r.unexplainedPct > 0 ? "+" : ""}{num(r.unexplainedPct, 1)}%
                      </span>
                    ) : "—"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
      <div className="text-xs text-slate-500 mt-2.5">
        Raw Delta is Actual Use minus Theoretical Use. Explained Adjustments applies logged waste, spoilage, employee meals, comps, prep loss, transfers, and count corrections. Unexplained is what remains after those known movements are accounted for.
      </div>
    </div>
  );
}
