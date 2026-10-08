// Reconcile an explicit retry; never assign edits to a different sales period.
const missing = Symbol("missing sales field");
const object = value => value !== null && typeof value === "object" && !Array.isArray(value);
function equal(a, b) {
  if (a === b) return true;
  if (!object(a) || !object(b)) return false;
  const keys = Object.keys(a);
  return keys.length === Object.keys(b).length && keys.every(key => Object.prototype.hasOwnProperty.call(b, key) && equal(a[key], b[key]));
}
export function mergeSalesDraft(base, draft, latest) {
  if (!object(base) || !object(draft) || !object(latest)) return { conflicts: ["Original sales data is unavailable; review the retained entries."] };
  if (base.periodStart !== latest.periodStart || base.periodEnd !== latest.periodEnd) {
    return { conflicts: ["Sales period dates changed; review the retained entries before replacing the period."] };
  }
  const conflicts = [];
  function merge(before, edited, saved, path) {
    if (equal(edited, before)) return saved;
    if (equal(saved, before) || equal(edited, saved)) return edited;
    if ((object(before) || before === missing) && object(edited) && object(saved)) {
      const result = {}, original = before === missing ? {} : before;
      const keys = new Set([...Object.keys(original), ...Object.keys(edited), ...Object.keys(saved)]);
      const get = (value, key) => Object.prototype.hasOwnProperty.call(value, key) ? value[key] : missing;
      for (const key of keys) {
        const value = merge(get(original, key), get(edited, key), get(saved, key), path ? `${path}.${key}` : key);
        if (value !== missing) result[key] = value;
      }
      return result;
    }
    conflicts.push(path); return edited;
  }
  const data = merge(base, draft, latest, "");
  return { data, conflicts };
}
