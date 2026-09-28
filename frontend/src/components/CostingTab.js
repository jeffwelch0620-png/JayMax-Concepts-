import React, { useEffect, useMemo, useState } from "react";
import { Plus, Trash2, Save } from "lucide-react";
import { MENU_CATEGORIES, UOM_OPTIONS, nextMenuCode, normalizeRecipeSchema, recipeCostSummary, itemDerived, uid, fmtMoney, num, FREQS } from "../lib/calc";
import { PageTitle, Field, SectionLabel, Pill, cardCls, inpCls, btnAcc, btnGhost, btnDanger } from "./common";

function emptyDish(type = "menu") {
  return { id: null, recipeType: type, name: "", menuCategory: MENU_CATEGORIES[0].name, menuCode: "", description: "", photoUrl: "", price: "", targetPct: 30, yieldQty: type === "prep" ? "" : 1, yieldUOM: type === "prep" ? "fl oz" : "each", procedure: "", equipment: "", shelfLife: "", portionNote: "", prepPar: 0, frequency: "daily", lines: [] };
}

export function CostingTab({ items, dishes, persist, showToast, focusDish }) {
  const normalizedRecipes = useMemo(() => dishes.map(normalizeRecipeSchema), [dishes]);
  const [dish, setDish] = useState(emptyDish());
  const [pickType, setPickType] = useState("item");
  const [pickCN, setPickCN] = useState(items[0]?.controlNumber || "");
  const [pickRecipeId, setPickRecipeId] = useState("");
  const [pickQty, setPickQty] = useState(1);

  const prepRecipes = normalizedRecipes.filter((r) => r.recipeType === "prep" && r.id !== dish.id);
  useEffect(() => { if (!pickCN && items.length) setPickCN(items[0].controlNumber); }, [items, pickCN]);
  useEffect(() => { if (!pickRecipeId && prepRecipes.length) setPickRecipeId(prepRecipes[0].id); }, [prepRecipes.length, pickRecipeId]);

  useEffect(() => {
    if (!focusDish) return;
    if (focusDish.id) { const found = dishes.find((d) => d.id === focusDish.id); if (found) setDish(normalizeRecipeSchema(found)); }
    else setDish(emptyDish("menu"));
  }, [focusDish, dishes]);

  function switchType(type) { setDish((d) => ({ ...emptyDish(type), id: d.id && d.recipeType === type ? d.id : null })); }
  function onCategoryChange(catName) {
    const cat = MENU_CATEGORIES.find((c) => c.name === catName);
    const menuOnly = dishes.filter((x) => (x.recipeType || "menu") !== "prep");
    setDish((d) => ({ ...d, menuCategory: catName, menuCode: cat ? nextMenuCode(cat.code, menuOnly) : d.menuCode }));
  }
  function addLine() {
    const qty = Number(pickQty) || 0;
    if (!qty) return;
    if (pickType === "prep") {
      const sub = prepRecipes.find((r) => r.id === pickRecipeId);
      if (!sub) return;
      setDish((d) => ({ ...d, lines: [...d.lines, { sourceType: "prep", recipeId: sub.id, qty }] }));
    } else {
      const item = items.find((i) => i.controlNumber === pickCN);
      if (!item) return;
      setDish((d) => ({ ...d, lines: [...d.lines, { sourceType: "item", controlNumber: pickCN, qty }] }));
    }
  }
  function removeLine(idx) { setDish((d) => ({ ...d, lines: d.lines.filter((_, i) => i !== idx) })); }

  const lineDetails = (dish.lines || []).map((rawLine) => {
    const l = rawLine.sourceType ? rawLine : { ...rawLine, sourceType: "item", qty: rawLine.qty ?? rawLine.qtyPortions ?? 0 };
    const qty = Number(l.qty ?? l.qtyPortions) || 0;
    if (l.sourceType === "prep") {
      const sub = normalizedRecipes.find((r) => r.id === l.recipeId);
      const s = recipeCostSummary(sub, items, normalizedRecipes);
      return { ...l, qty, name: sub ? `PREP — ${sub.name}` : "Deleted prep recipe", usageUOM: sub?.yieldUOM || "units", unitCost: s.costPerYieldUnit, cost: s.costPerYieldUnit * qty, cycle: s.cycle };
    }
    const item = items.find((i) => i.controlNumber === l.controlNumber);
    const cpp = item ? itemDerived(item).costPerPortion : 0;
    return { ...l, qty, name: item ? `${item.controlNumber} — ${item.name}` : "Deleted item", usageUOM: item?.portionUOM ? `${item.portionUOM} portions` : "portions", unitCost: cpp, cost: cpp * qty };
  });
  const totalCost = lineDetails.reduce((s, l) => s + l.cost, 0);
  const yieldQty = dish.recipeType === "prep" ? Number(dish.yieldQty) || 0 : 1;
  const costPerYieldUnit = dish.recipeType === "prep" && yieldQty > 0 ? totalCost / yieldQty : totalCost;
  const targetPct = Number(dish.targetPct) || 0;
  const suggestedPrice = dish.recipeType === "menu" && targetPct > 0 ? totalCost / (targetPct / 100) : 0;
  const cycleDetected = lineDetails.some((l) => l.cycle);

  async function saveDish() {
    if (!dish.name.trim()) return;
    if (dish.recipeType === "prep" && !(Number(dish.yieldQty) > 0)) { showToast("Prep recipes need a batch yield greater than zero"); return; }
    if (cycleDetected) { showToast("Recipe cycle detected — remove the circular prep-recipe reference"); return; }
    const menuOnly = dishes.filter((x) => (x.recipeType || "menu") !== "prep");
    const cat = MENU_CATEGORIES.find((c) => c.name === dish.menuCategory);
    const code = dish.recipeType === "menu" ? (String(dish.menuCode || "").trim() || (cat ? nextMenuCode(cat.code, menuOnly) : "")) : "";
    const saved = normalizeRecipeSchema({ ...dish, id: dish.id || uid(dish.recipeType === "prep" ? "prep" : "dish"), name: dish.name.trim(), menuCode: code, price: dish.recipeType === "menu" ? Number(dish.price) || 0 : 0, yieldQty: dish.recipeType === "prep" ? Number(dish.yieldQty) || 0 : 1, prepPar: Number(dish.prepPar) || 0 });
    const exists = dishes.some((d) => d.id === saved.id);
    const next = exists ? dishes.map((d) => d.id === saved.id ? saved : d) : [...dishes, saved];
    await persist(next);
    showToast(saved.recipeType === "prep" ? "Prep recipe saved" : "Menu item saved");
    setDish(saved);
  }
  async function deleteDish(id) {
    const usedBy = dishes.filter((r) => (r.lines || []).some((l) => l.sourceType === "prep" && l.recipeId === id));
    if (usedBy.length) { showToast(`Can't delete — used by ${usedBy.length} recipe${usedBy.length !== 1 ? "s" : ""}`); return; }
    await persist(dishes.filter((d) => d.id !== id));
    if (dish.id === id) setDish(emptyDish());
    showToast("Recipe deleted");
  }

  const typeBtn = (t) => dish.recipeType === t ? btnAcc : btnGhost;

  return (
    <div className="fade-slide-in" data-testid="costing-tab">
      <PageTitle>Recipe & Menu Costing</PageTitle>
      <div className={`${cardCls} p-5 mb-5`}>
        <SectionLabel>Recipe Type</SectionLabel>
        <div className="flex gap-2 mb-4">
          <button className={typeBtn("menu")} onClick={() => switchType("menu")} data-testid="recipe-type-menu">Menu Item</button>
          <button className={typeBtn("prep")} onClick={() => switchType("prep")} data-testid="recipe-type-prep">Prep / Sub-Recipe</button>
        </div>

        <div className="grid gap-3 mb-3" style={{ gridTemplateColumns: "2fr 1fr 1fr" }}>
          <Field label={dish.recipeType === "prep" ? "Prep Recipe Name" : "Menu Item Name"}>
            <input className={inpCls} data-testid="recipe-name-input" value={dish.name} onChange={(e) => setDish((d) => ({ ...d, name: e.target.value }))} placeholder={dish.recipeType === "prep" ? "e.g. Alfredo Sauce" : "e.g. Grilled Chicken Alfredo"} />
          </Field>
          {dish.recipeType === "menu" ? (
            <>
              <Field label="Menu Category"><select className={inpCls} data-testid="recipe-category-select" value={dish.menuCategory} onChange={(e) => onCategoryChange(e.target.value)}>{MENU_CATEGORIES.map((c) => <option key={c.code} value={c.name}>{c.name} ({c.code})</option>)}</select></Field>
              <Field label="Menu Code"><input className={inpCls} value={dish.menuCode} onChange={(e) => setDish((d) => ({ ...d, menuCode: e.target.value }))} /></Field>
            </>
          ) : (
            <>
              <Field label="Batch Yield"><input type="number" step="0.01" className={inpCls} data-testid="recipe-yield-input" value={dish.yieldQty} onChange={(e) => setDish((d) => ({ ...d, yieldQty: e.target.value }))} placeholder="128" /></Field>
              <Field label="Yield Unit"><select className={inpCls} value={dish.yieldUOM} onChange={(e) => setDish((d) => ({ ...d, yieldUOM: e.target.value }))}>{UOM_OPTIONS.map((u) => <option key={u} value={u}>{u}</option>)}</select></Field>
            </>
          )}
        </div>
        <Field label="Description / Production Notes"><textarea className={`${inpCls} w-full resize-y`} rows={2} value={dish.description} onChange={(e) => setDish((d) => ({ ...d, description: e.target.value }))} /></Field>
        {dish.recipeType === "menu" ? (
          <div className="grid grid-cols-2 gap-3 mt-3">
            <Field label="Menu Price ($)"><input type="number" step="0.01" className={inpCls} data-testid="recipe-price-input" value={dish.price} onChange={(e) => setDish((d) => ({ ...d, price: e.target.value }))} /></Field>
            <Field label="Target Food Cost %"><input type="number" step="0.1" className={inpCls} value={dish.targetPct} onChange={(e) => setDish((d) => ({ ...d, targetPct: e.target.value }))} /></Field>
          </div>
        ) : (
          <div className="grid grid-cols-2 gap-3 mt-3">
            <Field label="Prep Par (yield units on hand)"><input type="number" step="1" className={inpCls} data-testid="recipe-prep-par" value={dish.prepPar} onChange={(e) => setDish((d) => ({ ...d, prepPar: e.target.value }))} /></Field>
            <Field label="Prep Frequency"><select className={inpCls} data-testid="recipe-prep-frequency" value={dish.frequency || "daily"} onChange={(e) => setDish((d) => ({ ...d, frequency: e.target.value }))}>{FREQS.map((f) => <option key={f.id} value={f.id}>{f.label}</option>)}</select></Field>
          </div>
        )}
        <div className="grid grid-cols-2 gap-3 mt-3">
          <Field label="Equipment / Station"><input className={inpCls} value={dish.equipment || ""} onChange={(e) => setDish((d) => ({ ...d, equipment: e.target.value }))} placeholder="e.g. 12 qt pot, immersion blender" /></Field>
          <Field label={dish.recipeType === "prep" ? "Shelf Life / Hold" : "Portion / Plating Note"}>
            <input className={inpCls} value={dish.recipeType === "prep" ? (dish.shelfLife || "") : (dish.portionNote || "")}
              onChange={(e) => setDish((d) => dish.recipeType === "prep" ? ({ ...d, shelfLife: e.target.value }) : ({ ...d, portionNote: e.target.value }))}
              placeholder={dish.recipeType === "prep" ? "e.g. 5 days refrigerated" : "e.g. 6 oz sauce, 8 oz chicken"} />
          </Field>
        </div>
        <div className="mt-3"><Field label="Procedure / Method"><textarea className={`${inpCls} w-full resize-y`} rows={5} value={dish.procedure || ""} onChange={(e) => setDish((d) => ({ ...d, procedure: e.target.value }))} placeholder="Numbered or step-by-step kitchen procedure..." /></Field></div>

        <SectionLabel className="mt-4">Ingredients</SectionLabel>
        <div className="flex gap-2.5 items-end flex-wrap mb-3.5">
          <Field label="Source"><select className={inpCls} data-testid="ingredient-source" value={pickType} onChange={(e) => setPickType(e.target.value)}><option value="item">Inventory Item</option><option value="prep" disabled={!prepRecipes.length}>Prep / Sub-Recipe</option></select></Field>
          {pickType === "item" ? (
            <Field label="Ingredient (Internal Control #)"><select className={inpCls} data-testid="ingredient-item" value={pickCN} onChange={(e) => setPickCN(e.target.value)}>{items.map((it) => <option key={it.controlNumber} value={it.controlNumber}>{it.controlNumber} — {it.name}</option>)}</select></Field>
          ) : (
            <Field label="Prep Recipe"><select className={inpCls} data-testid="ingredient-prep" value={pickRecipeId} onChange={(e) => setPickRecipeId(e.target.value)}>{prepRecipes.map((r) => <option key={r.id} value={r.id}>{r.name} ({r.yieldUOM})</option>)}</select></Field>
          )}
          <Field label={pickType === "item" ? "Portions Used" : "Yield Units Used"}><input type="number" step="0.01" className={`${inpCls} w-28`} data-testid="ingredient-qty" value={pickQty} onChange={(e) => setPickQty(e.target.value)} /></Field>
          <button className={btnGhost} onClick={addLine} data-testid="ingredient-add"><Plus size={15} /> Add</button>
        </div>
        {lineDetails.length > 0 && (
          <table className="ops-table mb-3.5">
            <thead><tr><th>Ingredient / Sub-Recipe</th><th>Qty</th><th>Unit Cost</th><th>Extended Cost</th><th></th></tr></thead>
            <tbody>
              {lineDetails.map((l, i) => (
                <tr key={i}><td>{l.name}</td><td className="num">{num(l.qty, 2)} {l.usageUOM}</td><td className="num">{fmtMoney(l.unitCost)}</td><td className="num">{fmtMoney(l.cost)}</td>
                  <td><button aria-label={`Remove ${l.name}`} className="text-red-400 hover:text-red-300" onClick={() => removeLine(i)}><Trash2 size={13} /></button></td></tr>
              ))}
            </tbody>
          </table>
        )}
        {cycleDetected && <div className="p-2.5 bg-red-500/10 text-red-400 rounded-lg mb-3 font-bold border border-red-500/30">Circular recipe reference detected. A prep recipe cannot ultimately contain itself.</div>}
        {lineDetails.length > 0 && (
          <div className="flex gap-7 flex-wrap px-3.5 py-3 bg-[#0F1626] rounded-lg mb-3.5 border border-[#28354A]" data-testid="cost-summary">
            <div><div className="text-[11px] text-slate-500 uppercase">{dish.recipeType === "prep" ? "Batch Cost" : "Total Plate Cost"}</div><div className="text-lg font-bold num" style={{ color: "var(--acc)" }}>{fmtMoney(totalCost)}</div></div>
            {dish.recipeType === "prep" ? (
              <div><div className="text-[11px] text-slate-500 uppercase">Cost per {dish.yieldUOM}</div><div className="text-lg font-bold num" style={{ color: "var(--acc)" }}>{fmtMoney(costPerYieldUnit)}</div></div>
            ) : (
              <>
                <div><div className="text-[11px] text-slate-500 uppercase">Food Cost %</div><div className="text-lg font-bold num" style={{ color: "var(--acc)" }}>{Number(dish.price) > 0 ? num((totalCost / Number(dish.price)) * 100, 1) + "%" : "—"}</div></div>
                <div><div className="text-[11px] text-slate-500 uppercase">Suggested Price ({targetPct || 0}% FC)</div><div className="text-lg font-bold num" style={{ color: "var(--acc)" }}>{fmtMoney(suggestedPrice)}</div></div>
              </>
            )}
          </div>
        )}
        <button className={btnAcc} onClick={saveDish} data-testid="save-recipe-button"><Save size={15} /> Save {dish.recipeType === "prep" ? "Prep Recipe" : "Menu Item"}</button>
      </div>

      {normalizedRecipes.length > 0 && (
        <div>
          <SectionLabel>Saved Recipes ({normalizedRecipes.length})</SectionLabel>
          <div className={`${cardCls} overflow-hidden`}>
            <div className="overflow-x-auto">
              <table className="ops-table">
                <thead><tr><th>Type</th><th>Code</th><th>Name</th><th>Yield / Price</th><th>Calculated Cost</th><th></th></tr></thead>
                <tbody>
                  {normalizedRecipes.map((r) => {
                    const s = recipeCostSummary(r, items, normalizedRecipes);
                    return (
                      <tr key={r.id} data-testid={`recipe-row-${r.id}`}>
                        <td>{r.recipeType === "prep" ? <Pill color="#EAB308" bg="rgba(234,179,8,0.12)">PREP</Pill> : <Pill color="#10B981" bg="rgba(16,185,129,0.12)">MENU</Pill>}</td>
                        <td>{r.menuCode || "—"}</td>
                        <td className="font-semibold text-slate-200">{r.name}</td>
                        <td className="num">{r.recipeType === "prep" ? `${num(r.yieldQty, 2)} ${r.yieldUOM}` : fmtMoney(r.price)}</td>
                        <td className="num">{r.recipeType === "prep" ? `${fmtMoney(s.costPerYieldUnit)} / ${r.yieldUOM}` : fmtMoney(s.totalCost)}</td>
                        <td>
                          <div className="flex gap-1.5">
                            <button className={btnGhost} data-testid={`load-recipe-${r.id}`} onClick={() => setDish(r)}>Load</button>
                            <button aria-label={`Delete ${r.name}`} className={btnDanger} data-testid={`delete-recipe-${r.id}`} onClick={() => deleteDish(r.id)}><Trash2 size={14} /></button>
                          </div>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
