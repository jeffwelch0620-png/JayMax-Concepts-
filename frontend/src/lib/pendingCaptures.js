import { canonicalStoreId } from "./purchaseContract";

const MAX_BYTES = 2 * 1024 * 1024, MAX_RECORDS = 32;
const uuid = v => typeof v === "string" && /^[0-9a-f]{8}(-[0-9a-f]{4}){3}-[0-9a-f]{12}$/i.test(v);
const id = v => typeof v === "string" && /^[A-Za-z0-9_.-]{1,160}$/.test(v);
const exact = (v, keys) => v && typeof v === "object" && !Array.isArray(v) && Object.keys(v).length === keys.length && keys.every(k => Object.hasOwn(v, k));
const text = (v, max) => typeof v === "string" && v.length <= max;
const fields = v => v && typeof v === "object" && !Array.isArray(v) && Object.keys(v).length <= 100 && Object.values(v).every(s => text(s, 10000));
const extras = (v, max) => Array.isArray(v) && v.length <= max && v.every(r => exact(r, ["label", "value"]) && text(r.label, 200) && text(r.value, 10000));
const fail = () => new Error("Source recovery is unavailable or invalid. Keep this tab open and resolve the retained source before submitting again.");
export const stableCaptureValue = v => JSON.stringify(sort(v));
function sort(v) {
  if (Array.isArray(v)) return v.map(sort);
  return v && typeof v === "object" ? Object.fromEntries(Object.keys(v).sort().map(k => [k, sort(v[k])])) : v;
}
export function normalizedManual(body) {
  return { ...body, attachment_ids: [...new Set(body.attachment_ids)].sort() };
}
function valid(r) {
  if (!exact(r, ["key", "kind", "body"]) || !uuid(r.key) || !["manual", "csv", "source"].includes(r.kind)) throw fail();
  const b = r.body;
  if (r.kind === "manual") {
    if (!exact(b, ["vendor_id", "document_type", "documents", "parties", "lines", "extra_fields", "attachment_ids", "verified_source", "evidence_note"])
      || !text(b.vendor_id, 100) || !b.vendor_id || !["invoice", "credit"].includes(b.document_type) || !fields(b.documents)
      || !b.parties || typeof b.parties !== "object" || Array.isArray(b.parties) || Object.keys(b.parties).length > 5 || !Object.values(b.parties).every(fields)
      || !Array.isArray(b.lines) || !b.lines.length || b.lines.length > 1000 || !b.lines.every(l => exact(l, ["fields", "extra_fields"]) && fields(l.fields) && extras(l.extra_fields, 200))
      || !extras(b.extra_fields, 500) || !Array.isArray(b.attachment_ids) || b.attachment_ids.length > 20 || !b.attachment_ids.every(uuid)
      || b.verified_source !== true || !text(b.evidence_note, 2000) || !b.evidence_note.trim()) throw fail();
  } else if (!exact(b, ["kind", "sha256", "byteCount", "filename"]) || b.kind !== r.kind
    || typeof b.sha256 !== "string" || !/^[a-f0-9]{64}$/.test(b.sha256) || !Number.isInteger(b.byteCount) || b.byteCount < 1 || b.byteCount > 12 * 1024 * 1024
    || !text(b.filename, 255) || !b.filename || /[/\\]/.test(b.filename)) throw fail();
  return r;
}
export function captureRecord(kind, body, key) {
  return valid(JSON.parse(JSON.stringify({ key, kind, body: kind === "manual" ? normalizedManual(body) : body })));
}
export function pendingCaptureJournal(actorId, restaurantId, storage = () => window.sessionStorage) {
  restaurantId = canonicalStoreId(restaurantId);
  const key = `jaymax:pending-captures:v1:${actorId}:${restaurantId}`;
  function read() {
    if (!id(actorId) || !id(restaurantId)) throw fail();
    try {
      const raw = storage().getItem(key);
      if (raw === null) return [];
      if (new Blob([raw]).size > MAX_BYTES) throw fail();
      const value = JSON.parse(raw);
      if (!exact(value, ["schema", "actorId", "restaurantId", "records"]) || value.schema !== 1 || value.actorId !== actorId || value.restaurantId !== restaurantId
        || !Array.isArray(value.records) || value.records.length > MAX_RECORDS || new Set(value.records.map(r => r?.key)).size !== value.records.length) throw fail();
      return value.records.map(valid);
    } catch { throw fail(); }
  }
  function write(records) {
    const raw = JSON.stringify({ schema: 1, actorId, restaurantId, records });
    if (records.length > MAX_RECORDS || new Blob([raw]).size > MAX_BYTES) throw fail();
    try { storage().setItem(key, raw); if (storage().getItem(key) !== raw) throw fail(); } catch { throw fail(); }
  }
  return { list: read, save(record) {
    valid(record);
    const records = read(), found = records.find(r => r.key === record.key);
    if (found) { if (stableCaptureValue(found) !== stableCaptureValue(record)) throw fail(); return found; }
    write([...records, record]); return record;
  }, clear(record) {
    const records = read(), found = records.find(r => r.key === record.key);
    if (!found || stableCaptureValue(found) !== stableCaptureValue(record)) throw fail();
    write(records.filter(r => r.key !== record.key));
  } };
}
export async function captureFileIdentity(file, kind) {
  if (!file || !file.size || file.size > 12 * 1024 * 1024) throw new Error("Select a nonempty source no larger than 12 MB.");
  const digest = await crypto.subtle.digest("SHA-256", await file.arrayBuffer());
  return { kind, filename: file.name, byteCount: file.size, sha256: Array.from(new Uint8Array(digest), b => b.toString(16).padStart(2, "0")).join("") };
}
export function captureRecoveryOutcome(result, record, actorId, restaurantId) {
  if (!result || result.kind !== record.kind || result.requestKey !== record.key || result.actorId !== actorId || result.storeId !== canonicalStoreId(restaurantId)
    || !["saved", "retry_available"].includes(result.outcome) || typeof result.sourceSha256 !== "string" || !/^[a-f0-9]{64}$/.test(result.sourceSha256)
    || (result.outcome === "saved" ? !uuid(result.fileId) : result.fileId !== null)
    || (record.kind === "manual" ? stableCaptureValue(result.manualRecord) !== stableCaptureValue(record.body) : result.sourceSha256 !== record.body.sha256)) throw fail();
  return result;
}
