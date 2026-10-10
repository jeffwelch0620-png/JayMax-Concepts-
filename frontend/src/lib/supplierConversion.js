// Advisory catalog comparison only. Verified native profiles remain authoritative.
const units = {
  lb: ["mass", 453.59237], oz: ["mass", 28.349523125], kg: ["mass", 1000], g: ["mass", 1],
  gal: ["volume", 3785.411784], fl_oz: ["volume", 29.5735295625], l: ["volume", 1000], ml: ["volume", 1],
  qt: ["volume", 946.352946], pt: ["volume", 473.176473], cup: ["volume", 236.5882365], each: ["count", 1], dozen: ["count", 12],
};
const unitName = value => ({ "fl oz": "fl_oz", ct: "each" }[value] || value);
export function supplierPackFactor(row, baseUnit) {
  const count = Number(row.packCount), quantity = Number(row.unitQty);
  const from = units[unitName(row.unitUOM)], to = units[unitName(baseUnit)];
  if (!Number.isFinite(count) || !Number.isFinite(quantity) || count <= 0 || quantity <= 0 || !from || !to || from[0] !== to[0]) return null;
  const factor = count * quantity * from[1] / to[1];
  return Number.isFinite(factor) && factor > 0 ? factor : null;
}
export function supplierConversionMismatch(row, baseUnit) {
  const stored = Number(row.basePerPurchaseUnit), implied = supplierPackFactor(row, baseUnit);
  // Ignore floating-point representation noise, not physical differences.
  return Number.isFinite(stored) && stored > 0 && implied !== null
    && Math.abs(stored - implied) > Math.max(stored, implied) * 1e-10;
}
export function supplierReviewSaved(item, row, form) {
  const saved = item?.vendorSkus?.find(s => s.id === row.id);
  if (!item?.itemCode || !saved || (item.classification && item.classification !== "raw")) return false;
  const equal = (a, b) => String(a ?? "") === String(b ?? "");
  return ["vendor", "vendorSku", "purchaseUnit", "packDescription", "packCount", "unitQty", "unitUOM"]
    .every(key => equal(saved[key], row[key]))
    && ["purchaseUnit", "packCount", "unitQty", "unitUOM"].every(key => equal(item[key], form[key]));
}
