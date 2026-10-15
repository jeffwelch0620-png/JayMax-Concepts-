// Submitted correction evidence only. Never persist credentials, file bytes or
// authority to post. Recovery requires a fresh server read and an explicit retry.
import { canonicalStoreId, PURCHASE_BASE_UNITS } from "./purchaseContract";

const PREFIX = "jaymax:pending-corrections:v1:";
const MAX_BYTES = 2 * 1024 * 1024, MAX_RECORDS = 32;
const id = v => typeof v === "string" && /^[A-Za-z0-9_.-]{1,160}$/.test(v);
const uuid = v => typeof v === "string" && /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(v);
const scalar = v => v === null || typeof v === "string" || (typeof v === "number" && Number.isFinite(v));
const exact = (v, keys) => v && typeof v === "object" && !Array.isArray(v) && Object.keys(v).length === keys.length && keys.every(k => Object.hasOwn(v, k));
const lineKeys = ["line_id", "classification", "movement_kind", "item_code", "base_unit", "received_quantity", "received_unit", "base_units_per_received_unit", "movement_date", "original_line_id", "verified", "note"];
const bodyKeys = ["confirmed_currency", "received_date", "lines", "reason", "expected_plan_hash", "expected_initial_batch_id", "expected_correction_id"];
const rowKeys = ["line_id", "item_code", "classification", "description", "base_quantity", "base_unit", "inventory_cost_amount", "inventory_record_date"];
const take = (v, keys) => Object.fromEntries(keys.map(k => [k, v[k] ?? null]));
const failure = message => Object.assign(new Error(`${message || "Submitted correction recovery is corrupt or invalid."} No correction will be sent.`), { code: "correction_recovery_held" });

function valid(r) {
  if (!exact(r, ["versionId", "documentId", "documentNumber", "key", "body", "comparison"]) || !id(r.versionId) || !id(r.documentId)
    || typeof r.documentNumber !== "string" || !uuid(r.key) || !exact(r.body, bodyKeys)
    || r.body.confirmed_currency !== "USD" || !(r.body.received_date === null || (typeof r.body.received_date === "string" && /^\d{4}-\d{2}-\d{2}$/.test(r.body.received_date)))
    || typeof r.body.reason !== "string" || !r.body.reason.trim() || r.body.reason.length > 2000
    || typeof r.body.expected_plan_hash !== "string" || !/^[0-9a-f]{64}$/.test(r.body.expected_plan_hash) || !id(r.body.expected_initial_batch_id)
    || !(r.body.expected_correction_id === null || id(r.body.expected_correction_id))
    || !Array.isArray(r.body.lines) || !r.body.lines.length || r.body.lines.length > 2000
    || new Set(r.body.lines.map(l => l?.line_id)).size !== r.body.lines.length
    || !r.body.lines.every(l => exact(l, lineKeys) && id(l.line_id) && l.verified === true && typeof l.note === "string" && !!l.note.trim()
      && ["food", "nonfood", "fee", "tax"].includes(l.classification)
      && ["receipt", "physical_return", "price_credit", "no_inventory"].includes(l.movement_kind)
      && (l.base_unit === null || PURCHASE_BASE_UNITS.includes(l.base_unit)) && lineKeys.every(k => k === "verified" || scalar(l[k])))
    || !exact(r.comparison, ["before", "after", "feesBefore", "feesAfter", "taxBefore", "taxAfter"])
    || !["before", "after"].every(k => Array.isArray(r.comparison[k]) && r.comparison[k].length > 0 && r.comparison[k].length <= 2000
      && r.comparison[k].every(row => exact(row, rowKeys) && id(row.line_id) && Object.values(row).every(scalar)))
    || !["feesBefore", "feesAfter", "taxBefore", "taxAfter"].every(k => scalar(r.comparison[k]))) throw failure();
  return r;
}

export function pendingCorrectionRecord(document, body, key, plan) {
  if (plan?.status !== "ready" || plan.planHash !== body.expected_plan_hash || plan.initialBatchId !== body.expected_initial_batch_id
    || plan.previousCorrectionId !== body.expected_correction_id) throw failure();
  return valid(JSON.parse(JSON.stringify({ versionId: document.id, documentId: document.header.document_id,
    documentNumber: document.header.document_number || "", key, body,
    comparison: { before: plan.before.map(r => take(r, rowKeys)), after: plan.after.map(r => take(r, rowKeys)),
      feesBefore: plan.separateComponents.before.fees_source ?? null, feesAfter: plan.separateComponents.after.fees_source ?? null,
      taxBefore: plan.separateComponents.before.tax_source ?? null, taxAfter: plan.separateComponents.after.tax_source ?? null } })));
}

export function pendingCorrectionJournal(actorId, restaurantId, storage = () => window.sessionStorage) {
  restaurantId = canonicalStoreId(restaurantId);
  const key = `${PREFIX}${actorId}:${restaurantId}`;
  function read() {
    if (!id(actorId) || !id(restaurantId)) throw failure("A valid signed-in user and restaurant are required.");
    try {
      const raw = storage().getItem(key);
      if (raw === null) return [];
      if (new Blob([raw]).size > MAX_BYTES) throw failure();
      const v = JSON.parse(raw);
      if (!exact(v, ["schema", "actorId", "restaurantId", "records"]) || v.schema !== 1 || v.actorId !== actorId || v.restaurantId !== restaurantId
        || !Array.isArray(v.records) || v.records.length > MAX_RECORDS || new Set(v.records.map(r => r?.documentId)).size !== v.records.length
        || new Set(v.records.map(r => r?.key)).size !== v.records.length) throw failure();
      return v.records.map(valid);
    } catch (e) { if (e.code === "correction_recovery_held") throw e; throw failure("Browser correction recovery storage is unavailable or invalid. Keep this tab open."); }
  }
  function write(records) {
    if (records.length > MAX_RECORDS) throw failure("Resolve a retained correction before exceeding this tab's 32-request limit.");
    const raw = JSON.stringify({ schema: 1, actorId, restaurantId, records });
    if (new Blob([raw]).size > MAX_BYTES) throw failure("Retained corrections exceed this tab's 2 MiB limit.");
    try { storage().setItem(key, raw); if (storage().getItem(key) !== raw) throw new Error("readback"); }
    catch { throw failure("Browser correction recovery storage is unavailable or full. Keep this tab open."); }
  }
  return { list: read,
    save(record) {
      valid(record);
      const records = read(), found = records.find(r => r.documentId === record.documentId);
      if (found) { if (JSON.stringify(found) !== JSON.stringify(record)) throw failure("Another correction review is already retained for this invoice."); return found; }
      if (records.some(r => r.key === record.key)) throw failure("This request key is already retained for another invoice.");
      write([...records, record]); return record;
    },
    clear(versionId, requestKey) {
      const records = read(), found = records.find(r => r.versionId === versionId);
      if (!found) return;
      if (found.key !== requestKey) throw failure();
      write(records.filter(r => r !== found));
    },
  };
}

export function correctionRecoveryOutcome(result, record, actorId) {
  if (!result || result.versionId !== record.versionId || result.documentId !== record.documentId || result.actorId !== actorId
    || result.requestKey !== record.key || result.initialBatchId !== record.body.expected_initial_batch_id
    || result.expectedCorrectionId !== record.body.expected_correction_id || result.planHash !== record.body.expected_plan_hash
    || !["saved", "saved_replaced", "retry_available", "held", "other_request"].includes(result.outcome)
    || (["saved", "saved_replaced"].includes(result.outcome) ? !id(result.correctionId) : typeof result.message !== "string" || !result.message.trim())) {
    throw failure("Saved correction status was not confirmed. Check again; the original request is retained.");
  }
  return result;
}
