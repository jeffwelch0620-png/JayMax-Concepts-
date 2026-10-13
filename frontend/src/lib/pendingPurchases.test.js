import { pendingPurchaseJournal, pendingPurchaseRecord } from "./pendingPurchases";

const KEY = "00000000-0000-4000-8000-000000000001";
const source = { id: "file-1", original_filename: "TEST ONLY.csv", byte_count: 10, source_record_count: 1, source_sha256: "synthetic", source_bytes: "DO_NOT_CACHE_SOURCE" };
const document = { id: "version-1", header: { document_id: "identity-1", document_number: "TEST ONLY", vendor_id: "pfg", document_type: "invoice", token: "DO_NOT_CACHE_TOKEN" },
  totals: { lineTotal: "1", statedTotal: "1", difference: "0" }, lines: [{ id: "line-1", description_snapshot: "TEST ONLY Food" }] };
const body = { confirmed_currency: "USD", received_date: "2026-10-12", lines: [{ line_id: "line-1", classification: "food", movement_kind: "receipt", item_code: "food", base_unit: "each",
  received_quantity: "1.00", received_unit: "each", base_units_per_received_unit: "1", movement_date: null, original_line_id: null, verified: true, note: "TEST ONLY verified receipt" }] };
const record = (versionId = "version-1", key = KEY) => pendingPurchaseRecord(source, { ...document, id: versionId }, body, key);
let values, storage;
beforeEach(() => { values = new Map(); storage = { getItem: key => values.get(key) ?? null, setItem: (key, value) => values.set(key, value) }; });
const journal = (actor = "owner-1", store = "berts") => pendingPurchaseJournal(actor, store, () => storage);

test("reload keeps the exact reviewed body and key without credentials or source bytes", () => {
  const original = record(); journal().save(original);
  expect(journal().list()).toEqual([original]);
  expect(JSON.stringify(journal().list()[0].body)).toBe(JSON.stringify(body));
  const raw = [...values.values()][0];
  expect(raw).not.toContain("DO_NOT_CACHE_TOKEN"); expect(raw).not.toContain("DO_NOT_CACHE_SOURCE");
  expect(journal().list()[0].body.lines[0].received_quantity).toBe("1.00");
});

test("another actor or restaurant cannot inherit the pending review; store aliases agree", () => {
  journal().save(record()); expect(journal("owner-2").list()).toEqual([]); expect(journal("owner-1", "rudds").list()).toEqual([]);
  journal("owner-1", "papa_leonis").save(record()); expect(journal("owner-1", "papa").list()).toEqual([record()]);
});

test("a retry cannot replace its key, reviewed types, value or body ordering", () => {
  journal().save(record()); const before = [...values.entries()];
  for (const changed of [{ ...record(), key: "00000000-0000-4000-8000-000000000002" },
    { ...record(), body: { ...body, lines: [{ ...body.lines[0], received_quantity: 1 }] } },
    { ...record(), body: { lines: body.lines, received_date: body.received_date, confirmed_currency: "USD" } }]) {
    expect(() => journal().save(changed)).toThrow("No new posting will be sent");
    expect([...values.entries()]).toEqual(before);
  }
});

test.each([
  ["unknown schema", v => { v.schema = 2; }],
  ["wrong actor", v => { v.actorId = "owner-2"; }],
  ["wrong location", v => { v.restaurantId = "rudds"; }],
  ["duplicate version", v => { v.records.push(v.records[0]); }],
  ["invalid key", v => { v.records[0].key = "bad"; }],
  ["foreign line", v => { v.records[0].body.lines[0].line_id = "other-line"; }],
  ["unconfirmed line", v => { v.records[0].body.lines[0].verified = false; }],
  ["malformed date", v => { v.records[0].body.received_date = ["2026-10-12"]; }],
  ["unknown body field", v => { v.records[0].body.token = "forbidden"; }],
  ["malformed source", v => { v.records[0].source.id = null; }],
])("a %s record blocks new writes instead of silently dropping recovery", (_label, change) => {
  journal().save(record()); const [key, raw] = [...values.entries()][0], value = JSON.parse(raw); change(value);
  values.set(key, JSON.stringify(value)); const before = [...values.entries()];
  expect(() => journal().list()).toThrow("No new posting will be sent");
  expect(() => journal().save(record("version-2"))).toThrow(); expect([...values.entries()]).toEqual(before);
});

test("a quota failure or discarded write refuses submission and preserves earlier reviews", () => {
  journal().save(record()); const before = [...values.entries()];
  storage.setItem = () => { throw new Error("quota"); };
  expect(() => journal().save(record("version-2"))).toThrow(); expect([...values.entries()]).toEqual(before);
  storage.setItem = () => {};
  expect(() => journal().save(record("version-2"))).toThrow(); expect([...values.entries()]).toEqual(before);
});

test("clearing one confirmed request preserves the other and rejects the wrong key", () => {
  journal().save(record()); journal().save(record("version-2"));
  expect(() => journal().clear("version-1", "wrong-key")).toThrow(); expect(journal().list()).toHaveLength(2);
  journal().clear("version-1", KEY); expect(journal().list()).toEqual([record("version-2")]);
});

test("unavailable storage and missing identity fail closed", () => {
  expect(() => pendingPurchaseJournal("owner-1", "berts", () => { throw new Error("denied"); }).list()).toThrow();
  expect(() => pendingPurchaseJournal(undefined, "berts", () => storage).list()).toThrow();
  expect(() => journal("owner-1", "invalid/store").list()).toThrow();
});

test("malformed JSON and excessive records or bytes cannot become an empty journal", () => {
  journal().save(record()); const [key] = [...values.keys()]; values.set(key, "broken JSON"); expect(() => journal().list()).toThrow();
  values.clear(); for (let n = 0; n < 32; n++) journal().save(record(`version-${n}`));
  expect(() => journal().save(record("version-33"))).toThrow("32 unresolved retained reviews"); expect(journal().list()).toHaveLength(32);
  values.clear(); const huge = record(); huge.body.lines[0].note = "X".repeat(2 * 1024 * 1024);
  expect(() => journal().save(huge)).toThrow("2 MiB recovery limit"); expect(journal().list()).toEqual([]);
});

test("a valid new location can retain and clear a review without joining a client store allowlist", () => {
  for (const store of ["new-location_5", "comm"]) {
    journal("owner-1", store).save(record());
    expect(journal("owner-1", store).list()).toEqual([record()]);
    expect(journal("owner-2", store).list()).toEqual([]);
    journal("owner-1", store).clear("version-1", KEY);
    expect(journal("owner-1", store).list()).toEqual([]);
  }
});

test("storage errors identify unavailable storage separately from invalid recovery records", () => {
  expect(() => pendingPurchaseJournal("owner-1", "berts", () => { throw new Error("denied"); }).list()).toThrow("storage is unavailable");
  journal().save(record()); const [key] = [...values.keys()]; values.set(key, "invalid JSON");
  expect(() => journal().list()).toThrow("corrupt or invalid");
});
