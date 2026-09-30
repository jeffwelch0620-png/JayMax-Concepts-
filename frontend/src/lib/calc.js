// Pure business logic ported from the audited BertsInventorySystem.jsx (UOM engine,
// costing, variance, invoice import) — unchanged behavior, now shared by all locations.

export const RESTAURANTS = [
  { id: "berts", name: "Bert's Hometown Grill & Pizzeria", short: "Bert's", location: "Madisonville, TN", accent: "#F97316" },
  { id: "rudds", name: "Rudd's Pies and Fries", short: "Rudd's", location: "", accent: "#EAB308" },
  { id: "papa_leonis", name: "Papa Leoni's Pizza", short: "Papa Leoni's", location: "", accent: "#E11D48" },
];
export const OWNER = { id: "owner", name: "Ownership Dashboard", short: "Ownership", accent: "#06B6D4" };
export const FREQS = [
  { id: "daily", label: "Daily" },
  { id: "biweekly", label: "Biweekly" },
  { id: "weekly", label: "Weekly" },
];

// Standard kitchen holding vessels — capacities are practical starting points (fl oz);
// adjust per item since the capacity is expressed in the source item's portion unit.
export const VESSELS = [
  { name: "1/9 Pan", capacity: 20 },
  { name: "1/6 Pan", capacity: 40 },
  { name: "1/4 Pan", capacity: 90 },
  { name: "1/3 Pan", capacity: 128 },
  { name: "1/2 Pan", capacity: 192 },
  { name: "Full Hotel Pan", capacity: 416 },
  { name: "Cambro 2 qt", capacity: 64 },
  { name: "Cambro 4 qt", capacity: 128 },
  { name: "Cambro 6 qt", capacity: 192 },
  { name: "Cambro 8 qt", capacity: 256 },
  { name: "Cambro 12 qt", capacity: 384 },
  { name: "Cambro 18 qt", capacity: 576 },
  { name: "Cambro 22 qt", capacity: 704 },
  { name: "Deli Container 16 oz", capacity: 16 },
  { name: "Deli Container 32 oz", capacity: 32 },
  { name: "Squeeze Bottle 16 oz", capacity: 16 },
  { name: "Squeeze Bottle 32 oz", capacity: 32 },
  { name: "Custom Vessel", capacity: 0 },
];

export const MENU_CATEGORIES = [
  { name: "Grill", code: "GR" }, { name: "Sandwich", code: "SA" }, { name: "Pasta", code: "PA" },
  { name: "Pizza", code: "PZ" }, { name: "Fryer/Appetizers", code: "FR" }, { name: "Salads", code: "SL" },
  { name: "Specials", code: "SP" }, { name: "Desserts", code: "DS" }, { name: "Drinks", code: "DR" },
];
export function nextMenuCode(code, dishes) {
  const nums = dishes.filter((d) => d.menuCode && d.menuCode.startsWith(code + "-"))
    .map((d) => parseInt(d.menuCode.split("-")[1], 10)).filter((n) => !isNaN(n));
  const max = nums.length ? Math.max(...nums) : 0;
  return code + "-" + String(max + 1).padStart(3, "0");
}

export const DEFAULT_STORAGE_AREAS = [
  { name: "Salad Bar Room", prefix: "SB" }, { name: "Shed", prefix: "SH" }, { name: "Office", prefix: "OF" },
  { name: "Prep Room", prefix: "PR" }, { name: "Walk-in", prefix: "WI" }, { name: "Counter", prefix: "CT" },
];
export const VENDORS = ["US Foods", "PFG", "Sysco", "Webstaurant", "Other"];
export const PURCHASE_UNITS = ["case", "box", "bag", "each", "gal", "bucket", "tub", "ct", "flat", "lb"];
export const ITEM_TYPES = [{ id: "portion", label: "Portion-based" }, { id: "usage", label: "Usage-based" }];

export const UOM_FAMILY = {
  lb: "weight", oz: "weight", kg: "weight", g: "weight",
  gal: "volume", qt: "volume", pt: "volume", cup: "volume", "fl oz": "volume", l: "volume", ml: "volume",
  each: "count", ct: "count", dozen: "count",
};
export const CONV_TO_BASE = {
  lb: 16, oz: 1, kg: 35.27396195, g: 0.03527396195,
  gal: 128, qt: 32, pt: 16, cup: 8, "fl oz": 1, l: 33.814, ml: 0.033814,
  each: 1, ct: 1, dozen: 12,
};
export const UOM_OPTIONS = Object.keys(UOM_FAMILY);

export const ADJUSTMENT_REASONS = [
  { id: "waste", label: "Waste", direction: "remove" }, { id: "spoilage", label: "Spoilage", direction: "remove" },
  { id: "employee_meal", label: "Employee Meal", direction: "remove" }, { id: "comp", label: "Comp / Giveaway", direction: "remove" },
  { id: "prep_loss", label: "Prep Loss", direction: "remove" }, { id: "transfer_out", label: "Transfer Out", direction: "remove" },
  { id: "transfer_in", label: "Transfer In", direction: "add" },
  { id: "count_correction_remove", label: "Count Correction — Remove", direction: "remove" },
  { id: "count_correction_add", label: "Count Correction — Add", direction: "add" },
  { id: "other_remove", label: "Other — Remove", direction: "remove" }, { id: "other_add", label: "Other — Add", direction: "add" },
];
export function adjustmentReason(id) { return ADJUSTMENT_REASONS.find((r) => r.id === id) || ADJUSTMENT_REASONS[0]; }

export function todayISO() {
  const d = new Date();
  return new Date(d.getTime() - d.getTimezoneOffset() * 60000).toISOString().slice(0, 10);
}
export function workweekRange(refISO) {
  const d = refISO ? new Date(refISO + "T00:00:00") : new Date();
  const diff = (d.getDay() - 3 + 7) % 7; // workweek starts Wednesday
  const start = new Date(d); start.setDate(d.getDate() - diff);
  const end = new Date(start); end.setDate(start.getDate() + 6);
  const iso = (x) => new Date(x.getTime() - x.getTimezoneOffset() * 60000).toISOString().slice(0, 10);
  return { start: iso(start), end: iso(end) };
}
export function shiftWorkweek(range, weeks) {
  const s = new Date(range.start + "T00:00:00"); s.setDate(s.getDate() + weeks * 7);
  const e = new Date(range.end + "T00:00:00"); e.setDate(e.getDate() + weeks * 7);
  const iso = (x) => new Date(x.getTime() - x.getTimezoneOffset() * 60000).toISOString().slice(0, 10);
  return { start: iso(s), end: iso(e) };
}
export function fmtDate(iso) {
  if (!iso) return "—";
  // Accepts a date ("2026-09-30") or a full timestamp from Postgres ("2026-09-30T18:04:00+00:00").
  const d = new Date(String(iso).slice(0, 10) + "T00:00:00");
  return isNaN(d) ? "—" : d.toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });
}
export function fmtMoney(n) {
  if (n === null || n === undefined || isNaN(n)) return "$0.00";
  return "$" + Number(n).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}
export function num(n, d = 2) {
  if (n === null || n === undefined || isNaN(n)) return "0";
  return Number(n).toFixed(d).replace(/\.00$/, "");
}
export function uid(prefix = "id") { return prefix + "_" + Date.now().toString(36) + "_" + Math.random().toString(36).slice(2, 7); }

export function nextControlNumber(prefix, items) {
  const nums = items.filter((it) => it.controlNumber && it.controlNumber.startsWith(prefix + "-"))
    .map((it) => parseInt(it.controlNumber.split("-")[1], 10)).filter((n) => !isNaN(n));
  const max = nums.length ? Math.max(...nums) : 0;
  return prefix + "-" + String(max + 1).padStart(3, "0");
}

export function calcPortionsPerUnit(yieldQty, yieldUOM, portionSize, portionUOM) {
  const yq = Number(yieldQty) || 0, ps = Number(portionSize) || 0;
  // Missing portion size/UOM is a data gap (silently yields $0 cost downstream),
  // distinct from `mismatch` below (portion size IS entered, but its unit doesn't
  // convert against the pack unit) — callers should flag these two cases differently.
  if (!yq || !ps) return { value: 0, mismatch: false, needsPortion: true };
  const famY = UOM_FAMILY[yieldUOM], famP = UOM_FAMILY[portionUOM];
  if (famY && famP && famY === famP) {
    const totalBase = yq * CONV_TO_BASE[yieldUOM], portionBase = ps * CONV_TO_BASE[portionUOM];
    return { value: portionBase > 0 ? totalBase / portionBase : 0, mismatch: false, needsPortion: false };
  }
  return { value: yq / ps, mismatch: yieldUOM !== portionUOM, needsPortion: false };
}

export function preferredSku(item) {
  const skus = item.vendorSkus || [];
  return skus.find((s) => s.preferred) || skus[0] || null;
}
export function isCountActive(item) { return item.countActive !== undefined ? !!item.countActive : item.active !== false; }
export function isOrderEnabled(item) { return item.orderEnabled !== false; }
export function vendorPack(item, sku) {
  return {
    purchaseUnit: sku?.purchaseUnit || item.purchaseUnit || "case",
    packCount: Number(sku?.packCount ?? item.packCount) || 0,
    unitQty: Number(sku?.unitQty ?? item.unitQty) || 0,
    unitUOM: sku?.unitUOM || item.unitUOM || "each",
  };
}
export function normalizeItemSchema(item) {
  const vendorSkus = (item.vendorSkus || []).map((s) => ({
    ...s,
    purchaseUnit: s.purchaseUnit || item.purchaseUnit || "case",
    packCount: s.packCount ?? item.packCount ?? 0,
    unitQty: s.unitQty ?? item.unitQty ?? 0,
    unitUOM: s.unitUOM || item.unitUOM || "each",
    priceUpdatedAt: s.priceUpdatedAt || "",
    priceSource: s.priceSource || (Number(s.price) ? "manual" : ""),
    available: s.available !== false,
  }));
  return { ...item, countActive: item.countActive !== undefined ? !!item.countActive : item.active !== false, orderEnabled: item.orderEnabled !== false, vendorSkus };
}

export function itemDerived(item) {
  const pref = preferredSku(item);
  const pack = vendorPack(item, pref);
  const packTotal = pack.packCount * pack.unitQty;
  const { value: portionsPerUnit, mismatch, needsPortion } = calcPortionsPerUnit(packTotal, pack.unitUOM, item.portionSize, item.portionUOM);
  const price = pref ? Number(pref.price) || 0 : 0;
  const costPerPortion = portionsPerUnit > 0 ? price / portionsPerUnit : 0;
  return { portionsPerUnit, costPerPortion, mismatch, needsPortion, preferred: pref, price, pack };
}

export const STATUS_COLORS = { out: "#EF4444", critical: "#EF4444", low: "#F59E0B", ok: "#10B981" };
export function statusOf(item) {
  const stock = Number(item.currentStock) || 0, par = Number(item.par) || 0;
  if (stock <= 0) return { key: "out", label: "Out", color: STATUS_COLORS.out };
  if (par > 0 && stock < par * 0.5) return { key: "critical", label: "Critical", color: STATUS_COLORS.critical };
  if (par > 0 && stock < par) return { key: "low", label: "Low", color: STATUS_COLORS.low };
  return { key: "ok", label: "OK", color: STATUS_COLORS.ok };
}

export function adjustmentSignedPortions(adj, item) {
  const d = itemDerived(item);
  const qty = Number(adj.qty) || 0;
  const portions = adj.qtyBasis === "portion" ? qty : qty * (Number(d.portionsPerUnit) || 0);
  return adjustmentReason(adj.reason).direction === "add" ? -portions : portions;
}
export function adjustmentValue(adj, item) {
  return Math.abs(adjustmentSignedPortions(adj, item)) * (Number(itemDerived(item).costPerPortion) || 0);
}

export function downloadCSV(filename, rows) {
  const csv = rows.map((r) => r.map((cell) => {
    const s = String(cell ?? "");
    return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
  }).join(",")).join("\n");
  const blob = new Blob([csv], { type: "text/csv;charset=utf-8;" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url; a.download = filename;
  document.body.appendChild(a); a.click(); document.body.removeChild(a);
  URL.revokeObjectURL(url);
}
export function downloadJSON(filename, data) {
  const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json;charset=utf-8;" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url; a.download = filename;
  document.body.appendChild(a); a.click(); document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

export function parseCSV(text) {
  const rows = [];
  let row = [], field = "", inQuotes = false;
  for (let i = 0; i < text.length; i++) {
    const c = text[i];
    if (inQuotes) {
      if (c === '"') { if (text[i + 1] === '"') { field += '"'; i++; } else inQuotes = false; }
      else field += c;
    } else {
      if (c === '"' && field === "") inQuotes = true;
      else if (c === ",") { row.push(field); field = ""; }
      else if (c === "\n" || c === "\r") {
        if (c === "\r" && text[i + 1] === "\n") i++;
        row.push(field); field = "";
        if (row.length > 1 || row[0] !== "") rows.push(row);
        row = [];
      } else field += c;
    }
  }
  if (field !== "" || row.length) { row.push(field); rows.push(row); }
  return rows;
}

export function priceAsOf(purchases, controlNumber, daysAgo) {
  const cutoff = new Date();
  cutoff.setDate(cutoff.getDate() - daysAgo);
  // Correct for local timezone offset before slicing to a date, same as todayISO()/
  // workweekRange() above — raw toISOString() converts to UTC first, which can shift
  // the date by a day depending on time-of-day in US timezones.
  const cutoffISO = new Date(cutoff.getTime() - cutoff.getTimezoneOffset() * 60000).toISOString().slice(0, 10);
  const relevant = purchases.filter((p) => p.controlNumber === controlNumber && p.invoiceDate <= cutoffISO)
    .sort((a, b) => b.invoiceDate.localeCompare(a.invoiceDate));
  return relevant.length ? Number(relevant[0].unitCost) : null;
}

export function toISODate(mdY) {
  if (!mdY) return "";
  const parts = String(mdY).trim().split("/");
  if (parts.length !== 3) return String(mdY).trim();
  const [m, d, y] = parts;
  return `${y.padStart(4, "0")}-${m.padStart(2, "0")}-${d.padStart(2, "0")}`;
}
const UNIT_MAP = { CS: "case", LB: "lb", EA: "each", BX: "box", BG: "bag", CT: "ct", GAL: "gal", DZ: "dozen" };
export function mapPurchaseUnit(u) {
  const key = String(u || "").trim().toUpperCase();
  return UNIT_MAP[key] || (u ? String(u).trim().toLowerCase() : "case");
}
export function rowsToObjects(headers, dataRows) {
  return dataRows.filter((r) => r.some((c) => c !== "")).map((r) => {
    const o = {};
    headers.forEach((h, i) => { o[h] = r[i]; });
    return o;
  });
}
// A shipped qty of 0 (backorder) is a real value, not a missing one — only fall
// back to the ordered qty when the shipped field itself is absent/blank.
function qtyOrFallback(shipped, ordered) {
  const s = Number(shipped);
  if (shipped !== undefined && shipped !== null && shipped !== "" && !Number.isNaN(s)) return s;
  return Number(ordered) || 0;
}
export function detectVendorFormat(headers) {
  const set = new Set(headers.map((h) => h.trim()));
  if (set.has("Product #") && set.has("Customer OpCo") && set.has("Invoice Number")) return "pfg";
  if (set.has("ProductNumber") && set.has("DocumentNumber") && set.has("PricingUnit")) return "usfoods";
  return null;
}
export function normalizePFGRows(objs) {
  return objs.map((o) => ({
    vendor: "PFG", vendorSku: (o["Product #"] || "").trim(), description: (o["Product Description"] || "").trim(),
    packDescription: (o["Pack Size"] || "").trim(), qty: qtyOrFallback(o["Qty Shipped"], o["Qty Ordered"]),
    unit: mapPurchaseUnit(o["UOM"]), unitCost: Number(o["Unit Price"]) || 0, extendedCost: Number(o["Ext. Price"]) || 0,
    invoiceNumber: (o["Invoice Number"] || "").trim(), invoiceDate: toISODate(o["Invoice Date"]),
  })).filter((r) => r.description && r.invoiceNumber);
}
export function normalizeUSFoodsRows(objs) {
  return objs.map((o) => ({
    vendor: "US Foods", vendorSku: (o["ProductNumber"] || "").trim(), description: (o["ProductDescription"] || "").trim(),
    packDescription: (o["PackingSize"] || "").trim(), qty: qtyOrFallback(o["QtyShip"], o["QtyOrder"]),
    unit: mapPurchaseUnit(o["PricingUnit"]), unitCost: Number(o["UnitPrice"]) || 0, extendedCost: Number(o["ExtendedPrice"]) || 0,
    invoiceNumber: (o["DocumentNumber"] || "").trim(), invoiceDate: toISODate(o["DocumentDate"]),
  })).filter((r) => r.description && r.invoiceNumber);
}
export function matchRowToItem(row, items) {
  let match = items.find((it) => (it.vendorSkus || []).some((v) => v.vendor === row.vendor && v.vendorSku && v.vendorSku.trim() !== "" && v.vendorSku.trim() === row.vendorSku));
  if (match) return { item: match, matchedBy: "sku" };
  match = items.find((it) => it.name.trim().toLowerCase() === row.description.trim().toLowerCase());
  if (match) return { item: match, matchedBy: "name" };
  return { item: null, matchedBy: null };
}
const STOP_TOKENS = new Set(["AND", "THE", "OF", "IN", "A", "TO"]);
function tokenize(s) {
  const toks = (String(s || "").toUpperCase().match(/[A-Z0-9]+/g) || []);
  return new Set(toks.filter((t) => t.length > 1 && !STOP_TOKENS.has(t)));
}
export function suggestMatch(description, items) {
  const invToks = tokenize(description);
  if (invToks.size === 0) return null;
  let best = null, bestScore = 0, bestOverlap = 0;
  items.forEach((it) => {
    const toks = tokenize(it.name);
    let overlap = 0;
    invToks.forEach((t) => { if (toks.has(t)) overlap++; });
    const score = overlap / invToks.size;
    if (score > bestScore || (score === bestScore && overlap > bestOverlap)) { best = it; bestScore = score; bestOverlap = overlap; }
  });
  // A single-token description ("BUTTER") can never clear a flat 2-token bar —
  // scale the bar down for short descriptions instead of excluding them entirely.
  const minOverlap = invToks.size === 1 ? 1 : 2;
  if (!best || bestOverlap < minOverlap) return null;
  return { item: best, score: bestScore };
}

/* ---------- Recipes ---------- */
export function normalizeRecipeSchema(r) {
  return {
    ...r,
    recipeType: r.recipeType || "menu",
    yieldQty: r.yieldQty ?? 1,
    yieldUOM: r.yieldUOM || "each",
    procedure: r.procedure || "",
    equipment: r.equipment || "",
    shelfLife: r.shelfLife || "",
    portionNote: r.portionNote || "",
    prepPar: r.prepPar ?? 0,
    frequency: r.frequency || "daily",
    lines: (r.lines || []).map((l) => l.sourceType ? l : ({ ...l, sourceType: "item", qty: l.qty ?? l.qtyPortions ?? 0 })),
  };
}
export function recipeCostSummary(recipe, items, recipes, stack = new Set()) {
  if (!recipe) return { totalCost: 0, costPerYieldUnit: 0, cycle: false };
  const key = recipe.id || recipe.name || "draft";
  if (stack.has(key)) return { totalCost: 0, costPerYieldUnit: 0, cycle: true };
  const nextStack = new Set(stack); nextStack.add(key);
  let cycle = false;
  const totalCost = (recipe.lines || []).reduce((sum, rawLine) => {
    const l = rawLine.sourceType ? rawLine : { ...rawLine, sourceType: "item", qty: rawLine.qty ?? rawLine.qtyPortions ?? 0 };
    const qty = Number(l.qty ?? l.qtyPortions) || 0;
    if (l.sourceType === "prep") {
      const sub = recipes.find((r) => r.id === l.recipeId);
      const subSummary = recipeCostSummary(sub, items, recipes, nextStack);
      if (subSummary.cycle) cycle = true;
      return sum + subSummary.costPerYieldUnit * qty;
    }
    const item = items.find((i) => i.controlNumber === l.controlNumber);
    return sum + (item ? itemDerived(item).costPerPortion * qty : 0);
  }, 0);
  const yieldQty = Number(recipe.yieldQty) || 1;
  return { totalCost, costPerYieldUnit: yieldQty > 0 ? totalCost / yieldQty : 0, cycle };
}
export function rawPortionsForRecipe(recipe, targetCN, items, recipes, stack = new Set()) {
  if (!recipe) return 0;
  const key = recipe.id || recipe.name || "draft";
  if (stack.has(key)) return 0;
  const nextStack = new Set(stack); nextStack.add(key);
  return (recipe.lines || []).reduce((sum, rawLine) => {
    const l = rawLine.sourceType ? rawLine : { ...rawLine, sourceType: "item", qty: rawLine.qty ?? rawLine.qtyPortions ?? 0 };
    const qty = Number(l.qty ?? l.qtyPortions) || 0;
    if (l.sourceType === "item") return sum + (l.controlNumber === targetCN ? qty : 0);
    const sub = recipes.find((r) => r.id === l.recipeId);
    if (!sub) return sum;
    const subYield = Number(sub.yieldQty) || 1;
    return sum + rawPortionsForRecipe(sub, targetCN, items, recipes, nextStack) * (qty / subYield);
  }, 0);
}

/* ---------- Order generator helpers ---------- */
export function canonicalCountPack(item) {
  return { purchaseUnit: item.purchaseUnit || "case", packCount: Number(item.packCount) || 0, unitQty: Number(item.unitQty) || 0, unitUOM: item.unitUOM || "each" };
}
export function packBaseAmount(pack) {
  const qty = (Number(pack.packCount) || 0) * (Number(pack.unitQty) || 0);
  const factor = CONV_TO_BASE[pack.unitUOM];
  const family = UOM_FAMILY[pack.unitUOM];
  if (!qty || !factor || !family) return null;
  return { amount: qty * factor, family };
}
export function vendorUnitsForShortfall(item, sku, shortfallCountUnits) {
  const countBase = packBaseAmount(canonicalCountPack(item));
  const vendorBase = packBaseAmount(vendorPack(item, sku));
  if (countBase && vendorBase && countBase.family === vendorBase.family && vendorBase.amount > 0) {
    const neededBase = shortfallCountUnits * countBase.amount;
    const units = Math.ceil(neededBase / vendorBase.amount);
    return { units: Math.max(0, units), conversionKnown: true, neededBase, orderedBase: Math.max(0, units) * vendorBase.amount, overageBase: Math.max(0, units) * vendorBase.amount - neededBase };
  }
  return { units: Math.max(0, Math.ceil(shortfallCountUnits)), conversionKnown: false, neededBase: null, orderedBase: null, overageBase: null };
}

/* ---------- Period report (dashboard) ---------- */
export function buildPeriodReport(period, items, purchases, dishes, adjustments) {
  const start = period?.periodStart || todayISO();
  const end = period?.periodEnd || todayISO();
  const normalizedRecipes = dishes.map(normalizeRecipeSchema);
  const periodPurchases = purchases.filter((p) => p.invoiceDate >= start && p.invoiceDate <= end);
  const periodAdjustmentsAll = adjustments.filter((a) => a.date >= start && a.date <= end);
  const purchaseSpend = periodPurchases.reduce((sum, p) => sum + (Number(p.extendedCost) || ((Number(p.qty) || 0) * (Number(p.unitCost) || 0))), 0);

  const trackedRows = items.filter((it) => it.salesTracked).map((it) => {
    const d = itemDerived(it);
    const purchaseQty = periodPurchases.filter((p) => p.controlNumber === it.controlNumber).reduce((sum, p) => sum + (Number(p.qty) || 0), 0);
    let theoreticalPortions = 0;
    normalizedRecipes.filter((r) => r.recipeType !== "prep").forEach((recipe) => {
      const sold = Number(period?.dishSales?.[recipe.id]) || 0;
      theoreticalPortions += rawPortionsForRecipe(recipe, it.controlNumber, items, normalizedRecipes) * sold;
    });
    const counts = period?.itemCounts?.[it.controlNumber] || {};
    const beginning = counts.beginning !== undefined && counts.beginning !== "" ? Number(counts.beginning) : null;
    const ending = counts.ending !== undefined && counts.ending !== "" ? Number(counts.ending) : null;
    const actualUnits = beginning !== null && ending !== null ? beginning + purchaseQty - ending : null;
    const actualPortions = actualUnits !== null ? actualUnits * d.portionsPerUnit : null;
    const rawDelta = actualPortions !== null ? actualPortions - theoreticalPortions : null;
    const itemAdjustments = periodAdjustmentsAll.filter((a) => a.controlNumber === it.controlNumber);
    const explainedPortions = itemAdjustments.reduce((sum, a) => sum + adjustmentSignedPortions(a, it), 0);
    const unexplainedPortions = rawDelta !== null ? rawDelta - explainedPortions : null;
    return {
      item: it, beginning, ending, purchaseQty, theoreticalPortions, actualPortions, explainedPortions, unexplainedPortions,
      theoreticalCost: theoreticalPortions * d.costPerPortion,
      actualCost: actualPortions !== null ? actualPortions * d.costPerPortion : null,
      explainedCost: explainedPortions * d.costPerPortion,
      unexplainedCost: unexplainedPortions !== null ? unexplainedPortions * d.costPerPortion : null,
      hasCounts: beginning !== null && ending !== null,
    };
  });

  const usableRows = trackedRows.filter((r) => r.hasCounts);
  const theoreticalCogs = trackedRows.reduce((sum, r) => sum + r.theoreticalCost, 0);
  const actualCogs = usableRows.reduce((sum, r) => sum + (r.actualCost || 0), 0);
  const explainedCost = trackedRows.reduce((sum, r) => sum + r.explainedCost, 0);
  const unexplainedCost = usableRows.reduce((sum, r) => sum + (r.unexplainedCost || 0), 0);

  const wasteByReason = {};
  periodAdjustmentsAll.forEach((a) => {
    const it = items.find((i) => i.controlNumber === a.controlNumber);
    if (!it) return;
    const label = adjustmentReason(a.reason).label;
    wasteByReason[label] = (wasteByReason[label] || 0) + adjustmentValue(a, it);
  });

  const priceAlerts = [];
  items.forEach((it) => {
    const hist = purchases.filter((p) => p.controlNumber === it.controlNumber && Number(p.unitCost) > 0)
      .sort((a, b) => (a.invoiceDate || "").localeCompare(b.invoiceDate || ""));
    if (hist.length < 2) return;
    const latest = hist[hist.length - 1], prior = hist[hist.length - 2];
    const latestCost = Number(latest.unitCost) || 0, priorCost = Number(prior.unitCost) || 0;
    if (!priorCost) return;
    const pct = ((latestCost - priorCost) / priorCost) * 100;
    if (Math.abs(pct) >= 5) priceAlerts.push({ item: it, latest, prior, pct, change: latestCost - priorCost });
  });
  priceAlerts.sort((a, b) => Math.abs(b.pct) - Math.abs(a.pct));

  const menuProfitability = normalizedRecipes.filter((r) => r.recipeType !== "prep").map((r) => {
    const c = recipeCostSummary(r, items, normalizedRecipes);
    const price = Number(r.price) || 0;
    return { recipe: r, cost: c.totalCost, price, foodCostPct: price > 0 ? (c.totalCost / price) * 100 : null, contribution: price - c.totalCost };
  }).sort((a, b) => (b.foodCostPct || 0) - (a.foodCostPct || 0));

  const liveInventoryValue = items.reduce((sum, it) => sum + (Number(it.currentStock) || 0) * (Number(itemDerived(it).price) || 0), 0);
  const orderExposure = items.filter((it) => isOrderEnabled(it) && (Number(it.currentStock) || 0) < (Number(it.par) || 0)).reduce((sum, it) => {
    const shortfall = Math.max(0, (Number(it.par) || 0) - (Number(it.currentStock) || 0));
    const sku = preferredSku(it);
    if (!sku) return sum;
    const calc = vendorUnitsForShortfall(it, sku, shortfall);
    return sum + calc.units * (Number(sku.price) || 0);
  }, 0);

  return { start, end, periodPurchases, periodAdjustmentsAll, purchaseSpend, trackedRows, usableRows, theoreticalCogs, actualCogs, explainedCost, unexplainedCost, wasteByReason, priceAlerts, menuProfitability, liveInventoryValue, orderExposure };
}
