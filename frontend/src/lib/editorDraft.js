// Catalog and recipe arrays are compared by value, not by render identity.
export function equalEditorValue(a, b) {
  if (Object.is(a, b)) return true;
  if (a == null || b == null || typeof a !== "object" || typeof b !== "object") return false;
  if (Array.isArray(a) !== Array.isArray(b)) return false;
  const keys = Object.keys(a);
  return keys.length === Object.keys(b).length
    && keys.every(key => Object.prototype.hasOwnProperty.call(b, key) && equalEditorValue(a[key], b[key]));
}

export function snapshotEditorValue(value) {
  if (Array.isArray(value)) return value.map(snapshotEditorValue);
  if (value && typeof value === "object") return Object.fromEntries(Object.entries(value).map(([key, v]) => [key, snapshotEditorValue(v)]));
  return value;
}

// Fields with coupled meaning are reconciled together. Arrays are atomic:
// positional merging must not reassign supplier or ingredient identities.
export function mergeEditorFields(base, draft, latest, groups = []) {
  if (!base || !draft || !latest) return { conflicts: ["Original saved record is unavailable"] };
  const coupled = new Set(groups.flatMap(group => group.fields));
  const fields = new Set([...Object.keys(base), ...Object.keys(draft), ...Object.keys(latest)]);
  const all = [...groups, ...[...fields].filter(key => !coupled.has(key)).map(key => ({ label: key, fields: [key] }))];
  const data = { ...latest }, conflicts = [];
  const select = (record, keys) => Object.fromEntries(keys.map(key => [key, record[key]]));
  for (const group of all) {
    const before = select(base, group.fields), edited = select(draft, group.fields), saved = select(latest, group.fields);
    if (equalEditorValue(edited, before)) continue;
    if (!equalEditorValue(saved, before) && !equalEditorValue(edited, saved)) { conflicts.push(group.label); continue; }
    for (const key of group.fields) {
      if (Object.prototype.hasOwnProperty.call(draft, key)) data[key] = draft[key];
      else delete data[key];
    }
  }
  return { data, conflicts };
}
