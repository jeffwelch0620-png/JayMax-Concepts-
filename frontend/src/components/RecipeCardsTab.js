import React, { useEffect, useMemo, useState } from "react";
import { Printer } from "lucide-react";
import { normalizeRecipeSchema, recipeCostSummary, fmtPlanningCost, num } from "../lib/calc";
import { PageTitle, EmptyState, Field, SectionLabel, cardCls, inpCls, btnAcc, btnGhost } from "./common";

export function RecipeCardsTab({ items, dishes }) {
  const recipes = useMemo(() => dishes.map(normalizeRecipeSchema), [dishes]);
  const [selectedId, setSelectedId] = useState(recipes.find((r) => r.recipeType === "prep")?.id || recipes[0]?.id || "");
  const [scale, setScale] = useState(1);
  const selected = recipes.find((r) => r.id === selectedId) || recipes[0] || null;

  useEffect(() => {
    if (!selectedId && recipes.length) setSelectedId(recipes[0].id);
    if (selectedId && !recipes.some((r) => r.id === selectedId)) setSelectedId(recipes[0]?.id || "");
  }, [recipes, selectedId]);

  const safeScale = Math.max(0.01, Number(scale) || 1);
  const summary = selected ? recipeCostSummary(selected, items, recipes) : { totalCost: 0, costPerYieldUnit: 0 };
  const scaledCost = summary.totalCost == null ? null : summary.totalCost * safeScale;
  const scaledYield = selected?.recipeType === "prep" ? (Number(selected.yieldQty) || 0) * safeScale : safeScale;

  const ingredientRows = selected ? summary.lines.map((line, key) => ({ key, code: line.sourceType === "prep" ? "PREP" : line.controlNumber || "—", name: line.name, qty: line.qty == null ? null : line.qty * safeScale, uom: line.usageUOM, cost: line.cost == null ? null : line.cost * safeScale })) : [];

  if (!recipes.length) return <EmptyState text="No recipes yet. Build recipes in Menu Costing, then print production cards here." />;

  return (
    <div className="fade-slide-in" data-testid="recipe-cards-tab">
      <PageTitle>Kitchen Recipe & Production Cards</PageTitle>
      <div className={`${cardCls} p-5 mb-4 recipe-card-controls`}>
        <div className="grid gap-3 items-end" style={{ gridTemplateColumns: "minmax(240px,2fr) 1fr" }}>
          <Field label="Recipe">
            <select className={inpCls} data-testid="recipe-card-select" value={selected?.id || ""} onChange={(e) => { setSelectedId(e.target.value); setScale(1); }}>
              <optgroup label="Prep / Production Recipes">{recipes.filter((r) => r.recipeType === "prep").map((r) => <option key={r.id} value={r.id}>{r.name}</option>)}</optgroup>
              <optgroup label="Menu Recipes">{recipes.filter((r) => r.recipeType !== "prep").map((r) => <option key={r.id} value={r.id}>{r.menuCode ? `${r.menuCode} — ` : ""}{r.name}</option>)}</optgroup>
            </select>
          </Field>
          <Field label="Custom Batch Multiplier"><input type="number" min="0.01" step="0.25" className={inpCls} data-testid="recipe-card-scale" value={scale} onChange={(e) => setScale(e.target.value)} /></Field>
        </div>
        <div className="flex gap-2 flex-wrap mt-3">
          {[0.5, 1, 1.5, 2, 3, 4].map((v) => (
            <button key={v} className={Number(scale) === v ? btnAcc : btnGhost} onClick={() => setScale(v)} data-testid={`scale-${v}`}>{v}×</button>
          ))}
          <button className={`${btnAcc} ml-auto`} onClick={() => window.print()} data-testid="print-card-button"><Printer size={15} /> Print Card</button>
        </div>
      </div>

      {selected && (
        <div className={`${cardCls} overflow-hidden recipe-print-card`}>
          <div className="px-6 py-4 flex justify-between gap-4 flex-wrap print-muted" style={{ background: "var(--acc)" }}>
            <div>
              <div className="font-display text-2xl font-bold text-[#0B0F17]">{selected.name}</div>
              <div className="text-xs mt-1 text-[#0B0F17]/70 font-semibold">{selected.recipeType === "prep" ? "PREP / PRODUCTION RECIPE" : `MENU RECIPE${selected.menuCode ? ` • ${selected.menuCode}` : ""}`}</div>
            </div>
            <div className="text-right"><div className="text-[11px] text-[#0B0F17]/70 font-bold">BATCH SCALE</div><div className="text-[22px] font-extrabold num text-[#0B0F17]">{num(safeScale, 2)}×</div></div>
          </div>
          <div className="p-6">
            {!summary.complete && <div role="status" className="text-amber-300 mb-3">Planning cost is incomplete: {summary.issues.join("; ")}</div>}
            <div className="grid gap-2.5 mb-4" style={{ gridTemplateColumns: "repeat(4,minmax(0,1fr))" }}>
              <div className="border border-[#28354A] rounded-lg p-2.5 bg-[#0F1626] print-muted"><span className="block text-[10px] uppercase tracking-wider text-slate-500 mb-1 font-bold">Yield</span><strong className="text-sm text-slate-200 num">{selected.recipeType === "prep" ? `${num(scaledYield, 2)} ${selected.yieldUOM}` : `${num(safeScale, 2)} serving${safeScale === 1 ? "" : "s"}`}</strong></div>
              <div className="border border-[#28354A] rounded-lg p-2.5 bg-[#0F1626] print-muted"><span className="block text-[10px] uppercase tracking-wider text-slate-500 mb-1 font-bold">Planning Batch Cost</span><strong className="text-sm text-slate-200 num">{fmtPlanningCost(scaledCost)}</strong></div>
              <div className="border border-[#28354A] rounded-lg p-2.5 bg-[#0F1626] print-muted"><span className="block text-[10px] uppercase tracking-wider text-slate-500 mb-1 font-bold">{selected.recipeType === "prep" ? `Cost / ${selected.yieldUOM}` : "Estimated Food Cost"}</span><strong className="text-sm text-slate-200 num">{selected.recipeType === "prep" ? fmtPlanningCost(summary.costPerYieldUnit) : (summary.complete && Number(selected.price) > 0 ? `${num((summary.totalCost / Number(selected.price)) * 100, 1)}%` : "Unknown")}</strong></div>
              <div className="border border-[#28354A] rounded-lg p-2.5 bg-[#0F1626] print-muted"><span className="block text-[10px] uppercase tracking-wider text-slate-500 mb-1 font-bold">{selected.recipeType === "prep" ? "Shelf Life / Hold" : "Portion / Plate"}</span><strong className="text-sm text-slate-200">{selected.recipeType === "prep" ? (selected.shelfLife || "—") : (selected.portionNote || "—")}</strong></div>
            </div>
            {selected.equipment && <div className="mb-3.5 text-[13px] text-slate-300"><strong>Equipment / Station:</strong> {selected.equipment}</div>}
            <SectionLabel>Ingredients</SectionLabel>
            <div className="overflow-x-auto">
              <table className="ops-table">
                <thead><tr><th>Control #</th><th>Ingredient</th><th>Scaled Qty</th><th>Unit</th><th className="recipe-cost-col">Cost</th></tr></thead>
                <tbody>
                  {ingredientRows.map((r) => (
                    <tr key={r.key}><td className="font-bold" style={{ color: "var(--acc)" }}>{r.code}</td><td className="font-semibold text-slate-200">{r.name}</td><td className="num">{num(r.qty, 2)}</td><td>{r.uom}</td><td className="num recipe-cost-col">{fmtPlanningCost(r.cost)}</td></tr>
                  ))}
                </tbody>
              </table>
            </div>
            <div className="mt-5">
              <SectionLabel>Procedure / Method</SectionLabel>
              <div className="whitespace-pre-wrap min-h-[90px] leading-relaxed px-3.5 py-3 bg-[#0F1626] border border-[#28354A] rounded-lg text-sm text-slate-300 print-muted">{selected.procedure || "No procedure entered yet. Add the kitchen method in Menu Costing."}</div>
            </div>
            {selected.description && <div className="mt-3.5 text-xs text-slate-500"><strong>Description:</strong> {selected.description}</div>}
            <div className="grid grid-cols-3 gap-4 mt-7 pt-4 border-t border-[#28354A] text-xs text-slate-400">
              <div>Prepared by: __________________</div><div>Date: __________</div><div>Verified by: __________________</div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
