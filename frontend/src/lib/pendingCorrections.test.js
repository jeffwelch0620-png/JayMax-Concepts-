import { pendingCorrectionRecord, pendingCorrectionJournal, correctionRecoveryOutcome } from "./pendingCorrections";

export const KEY = "00000000-0000-4000-8000-000000000001";
export const document = { id: "version-1", header: { document_id: "identity-1", document_number: "TEST ONLY correction" } };
export const body = { confirmed_currency: "USD", received_date: "2026-10-15", reason: "TEST ONLY verified count",
  lines: [{ line_id: "line-1", classification: "food", movement_kind: "receipt", item_code: "food", base_unit: "each", received_quantity: "2.00", received_unit: "each", base_units_per_received_unit: "1", movement_date: null, original_line_id: null, verified: true, note: "TEST ONLY" }],
  expected_plan_hash: "a".repeat(64), expected_initial_batch_id: "batch-1", expected_correction_id: null };
export const plan = { status: "ready", planHash: body.expected_plan_hash, initialBatchId: "batch-1", previousCorrectionId: null,
  before: [{ line_id: "line-1", item_code: "food", base_quantity: "1", base_unit: "each", inventory_cost_amount: "1", inventory_record_date: "2026-10-15", token: "DO_NOT_CACHE" }],
  after: [{ line_id: "line-1", item_code: "food", base_quantity: "2", base_unit: "each", inventory_cost_amount: "1", inventory_record_date: "2026-10-15" }],
  separateComponents: { before: { fees_source: "0", tax_source: "0" }, after: { fees_source: "0", tax_source: "0" } } };
const record = () => pendingCorrectionRecord(document, body, KEY, plan);
let values, storage;
beforeEach(() => { values = new Map(); storage = { getItem: k => values.get(k) ?? null, setItem: (k, v) => values.set(k, v) }; });
const journal = (actor = "owner", store = "berts") => pendingCorrectionJournal(actor, store, () => storage);

test("reload preserves the exact submitted correction and safe comparison only", () => {
  const r = record(); journal().save(r); expect(journal().list()).toEqual([r]);
  expect(JSON.stringify(journal().list()[0].body)).toBe(JSON.stringify(body));
  expect([...values.values()][0]).not.toContain("DO_NOT_CACHE");
  expect(r.body.lines[0].received_quantity).toBe("2.00");
});
test("actor and restaurant boundaries preserve original records and canonical aliases", () => {
  journal().save(record()); expect(journal("another").list()).toEqual([]); expect(journal("owner", "rudds").list()).toEqual([]);
  journal("owner", "papa_leonis").save(record()); expect(journal("owner", "papa").list()).toEqual([record()]);
  expect(() => pendingCorrectionJournal(undefined, "berts", () => storage).save(record())).toThrow();
});
test("another key, body or version cannot replace an unresolved invoice correction", () => {
  journal().save(record()); const before = [...values.entries()];
  for (const changed of [{ ...record(), key: "00000000-0000-4000-8000-000000000002" }, { ...record(), versionId: "version-2" },
    { ...record(), body: { ...body, reason: "Changed reason" } }]) expect(() => journal().save(changed)).toThrow();
  expect([...values.entries()]).toEqual(before);
  expect(() => journal().clear("version-1", "wrong")).toThrow();
  journal().clear("version-1", KEY); expect(journal().list()).toEqual([]);
});
test("another invoice cannot reuse a retained correction key", () => {
  journal().save(record()); expect(() => journal().save({ ...record(), documentId: "other", versionId: "other" })).toThrow("request key");
  expect(journal().list()).toEqual([record()]);
});
test.each([
  ["schema", v => { v.schema = 2; }], ["actor", v => { v.actorId = "another"; }], ["store", v => { v.restaurantId = "rudds"; }],
  ["duplicate invoice", v => { v.records.push(v.records[0]); }], ["key", v => { v.records[0].key = "wrong"; }],
  ["unknown body field", v => { v.records[0].body.token = "secret"; }],
  ["date type", v => { v.records[0].body.received_date = ["2026-10-15"]; }],
  ["hash type", v => { v.records[0].body.expected_plan_hash = [body.expected_plan_hash]; }],
  ["line confirmation", v => { v.records[0].body.lines[0].verified = false; }],
  ["comparison shape", v => { v.records[0].comparison.before = {}; }],
])("corrupt %s holds recovery instead of returning an empty journal", (_name, mutate) => {
  journal().save(record()); const [k, raw] = [...values.entries()][0], v = JSON.parse(raw); mutate(v); storage.setItem(k, JSON.stringify(v));
  expect(() => journal().list()).toThrow("No correction will be sent");
});
test("quota, unavailable storage and silently discarded writes refuse submission", () => {
  storage.setItem = () => { throw new Error("quota"); }; expect(() => journal().save(record())).toThrow();
  storage.setItem = () => {}; expect(() => journal().save(record())).toThrow();
  expect(() => pendingCorrectionJournal("owner", "berts", () => { throw new Error("denied"); }).list()).toThrow();
});
test("record and byte budgets keep earlier retained requests", () => {
  for (let n = 0; n < 32; n++) journal().save({ ...record(), documentId: `identity-${n}`, versionId: `version-${n}`, key: `00000000-0000-4000-8000-${String(n).padStart(12, "0")}` });
  expect(() => journal().save({ ...record(), documentId: "overflow", key: "99999999-0000-4000-8000-000000000001" })).toThrow("32-request limit"); expect(journal().list()).toHaveLength(32);
  values.clear(); const huge = record(); huge.body.lines[0].note = "x".repeat(2 * 1024 * 1024);
  expect(() => journal().save(huge)).toThrow("2 MiB"); expect(journal().list()).toEqual([]);
});
const result = () => ({ actorId: "owner", versionId: "version-1", documentId: "identity-1", requestKey: KEY, initialBatchId: "batch-1", expectedCorrectionId: null, planHash: body.expected_plan_hash, outcome: "retry_available", message: "No saved outcome visible" });
test.each(["saved", "saved_replaced", "retry_available", "held", "other_request"])("status distinguishes %s without changing the journal", outcome => {
  journal().save(record()); const r = { ...result(), outcome, correctionId: "correction-1" };
  expect(correctionRecoveryOutcome(r, record(), "owner").outcome).toBe(outcome); expect(journal().list()).toHaveLength(1);
});
test.each(["actorId", "versionId", "documentId", "requestKey", "initialBatchId", "expectedCorrectionId", "planHash", "outcome"])("mismatched %s cannot authorize recovery or a retry", field => {
  expect(() => correctionRecoveryOutcome({ ...result(), [field]: "different" }, record(), "owner")).toThrow();
});
