import { captureRecord, captureRecoveryOutcome, normalizedManual, pendingCaptureJournal } from "./pendingCaptures";

export const key = "00000000-0000-4000-8000-000000000001";
export const manual = () => ({ vendor_id: "fictional", document_type: "invoice", documents: { document_number: "TEST ONLY", tax_source: "" }, parties: {},
  lines: [{ fields: { vendor_sku_snapshot: "00001", extended_amount_source: "40.00" }, extra_fields: [{ label: "Note", value: "" }, { label: "Note", value: "same label" }] }],
  extra_fields: [], attachment_ids: [], verified_source: true, evidence_note: "Fictional fixture only" });
const file = () => captureRecord("csv", { kind: "csv", sha256: "a".repeat(64), byteCount: 3, filename: "synthetic.csv" }, key);
beforeEach(() => sessionStorage.clear());
test("exact manual fields survive reconstruction and remain separate by user and canonical location", () => {
  const record = captureRecord("manual", manual(), key);
  pendingCaptureJournal("owner", "berts").save(record);
  expect(pendingCaptureJournal("owner", "berts").list()).toEqual([record]);
  expect(pendingCaptureJournal("other", "berts").list()).toEqual([]);
  expect(pendingCaptureJournal("owner", "rudds").list()).toEqual([]);
  expect(record.body.lines[0].extra_fields).toHaveLength(2);
  expect(record.body.documents.tax_source).toBe("");
});
test("keys cannot change body, and clear requires the exact retained record", () => {
  const journal = pendingCaptureJournal("owner", "berts"), record = file();
  journal.save(record); journal.save(record); expect(journal.list()).toHaveLength(1);
  expect(() => journal.save({ ...record, body: { ...record.body, sha256: "b".repeat(64) } })).toThrow();
  expect(() => journal.clear({ ...record, kind: "source" })).toThrow();
  journal.clear(record); expect(journal.list()).toEqual([]);
});
test("invalid envelopes, credentials and foreign identities fail closed without overwriting storage", () => {
  const journal = pendingCaptureJournal("owner", "berts"); journal.save(file());
  const name = sessionStorage.key(0), raw = sessionStorage.getItem(name), envelope = JSON.parse(raw);
  for (const value of [{ ...envelope, actorId: "other" }, { ...envelope, records: [file(), file()] }, { ...envelope, token: "synthetic" }, { ...envelope, records: [{ ...file(), body: { ...file().body, sourceBytes: "abc" } }] }]) {
    sessionStorage.setItem(name, JSON.stringify(value)); expect(() => journal.list()).toThrow();
    expect(sessionStorage.getItem(name)).toBe(JSON.stringify(value));
  }
});
test("quota, readback and size limits prevent an unretained submission", () => {
  const store = { getItem: jest.fn(() => null), setItem: jest.fn(() => { throw new Error("quota"); }) };
  expect(() => pendingCaptureJournal("owner", "berts", () => store).save(file())).toThrow();
  store.setItem.mockImplementation(() => {});
  expect(() => pendingCaptureJournal("owner", "berts", () => store).save(file())).toThrow();
  const record = captureRecord("manual", { ...manual(), extra_fields: Array.from({ length: 230 }, () => ({ label: "x", value: "x".repeat(10000) })) }, key);
  expect(() => pendingCaptureJournal("owner", "berts").save(record)).toThrow();
  expect(sessionStorage.length).toBe(0);
});
test("manual attachment normalization preserves source fields and permits no extra root properties", () => {
  const body = { ...manual(), attachment_ids: [key, key] };
  expect(normalizedManual(body).attachment_ids).toEqual([key]);
  expect(() => captureRecord("manual", { ...body, authorization: "synthetic" }, key)).toThrow();
  expect(() => captureRecord("csv", { ...file().body, filename: "../other.csv" }, key)).toThrow();
});
test("the 32-request cap preserves all earlier records", () => {
  const journal = pendingCaptureJournal("owner", "berts");
  for (let i = 0; i < 32; i++) journal.save({ ...file(), key: `00000000-0000-4000-8000-${String(i).padStart(12, "0")}` });
  const before = journal.list();
  expect(() => journal.save({ ...file(), key: "ffffffff-ffff-4fff-8fff-ffffffffffff" })).toThrow();
  expect(journal.list()).toEqual(before);
});
test("status requires request, user, location, kind, exact source and a valid saved file id", () => {
  const record = file(), status = { kind: "csv", requestKey: key, actorId: "owner", storeId: "berts", sourceSha256: record.body.sha256, outcome: "saved", fileId: key };
  expect(captureRecoveryOutcome(status, record, "owner", "berts")).toBe(status);
  for (const patch of [{ requestKey: "other" }, { actorId: "other" }, { storeId: "rudds" }, { kind: "source" }, { sourceSha256: "b".repeat(64) }, { outcome: "saved", fileId: null }, { outcome: "retry_available", fileId: key }]) {
    expect(() => captureRecoveryOutcome({ ...status, ...patch }, record, "owner", "berts")).toThrow();
  }
  const mr = captureRecord("manual", manual(), key), ms = { ...status, kind: "manual", manualRecord: mr.body };
  expect(captureRecoveryOutcome(ms, mr, "owner", "berts")).toBe(ms);
  expect(() => captureRecoveryOutcome({ ...ms, manualRecord: { ...mr.body, evidence_note: "changed" } }, mr, "owner", "berts")).toThrow();
});
