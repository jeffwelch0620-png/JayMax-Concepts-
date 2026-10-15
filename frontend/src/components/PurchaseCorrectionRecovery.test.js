import React, { act } from "react";
import { createRoot } from "react-dom/client";
import { PurchaseImportsTab } from "./PurchaseImportsTab";
import * as api from "../lib/api";
import { pendingCorrectionJournal, pendingCorrectionRecord } from "../lib/pendingCorrections";
import { resetComponentApiMock } from "../testHelpers/componentApiMock";
jest.mock("../lib/api", () => require("../testHelpers/componentApiMock").createComponentApiMock());

const KEY = "00000000-0000-4000-8000-000000000001", HASH = "a".repeat(64);
const line = { line_id: "line-1", classification: "food", movement_kind: "receipt", item_code: "food", base_unit: "each", received_quantity: "2.00", received_unit: "each", base_units_per_received_unit: "1", movement_date: null, original_line_id: null, verified: true, note: "TEST ONLY counted" };
const body = { confirmed_currency: "USD", received_date: "2026-10-15", reason: "TEST ONLY correction", lines: [line], expected_plan_hash: HASH, expected_initial_batch_id: "batch-1", expected_correction_id: null };
const doc = { id: "version-1", status: "posted", errors: [], sourceErrors: [], correctionAvailable: true,
  header: { document_id: "identity-1", document_number: "TEST ONLY", posted_batch_id: "batch-1" }, totals: { lineTotal: "1", statedTotal: "1", difference: "0" },
  lines: [{ id: "line-1", description_snapshot: "TEST ONLY food" }], currentMappings: [{ ...line, received_quantity: "1", inventory_record_date: "2026-10-15", decision_note: "TEST ONLY" }] };
const row = { line_id: "line-1", item_code: "food", base_quantity: "1", base_unit: "each", inventory_cost_amount: "1", inventory_record_date: "2026-10-15" };
const plan = { status: "ready", planHash: HASH, initialBatchId: "batch-1", previousCorrectionId: null,
  review: { confirmed_currency: "USD", received_date: "2026-10-15", reason: "TEST ONLY correction", lines: [line] },
  before: [row], after: [{ ...row, base_quantity: "2" }], separateComponents: { before: { fees_source: "0", tax_source: "0" }, after: { fees_source: "0", tax_source: "0" } }, blocks: [], affectedPeriods: [], legacyClosedPeriods: [], linkedDocuments: [] };
const record = () => pendingCorrectionRecord(doc, body, KEY, plan);
const journal = (actor = "owner-1", store = "berts") => pendingCorrectionJournal(actor, store);
const status = (outcome = "retry_available") => ({ versionId: "version-1", documentId: "identity-1", actorId: "owner-1", requestKey: KEY, initialBatchId: "batch-1", expectedCorrectionId: null, planHash: HASH, outcome, message: `TEST ONLY ${outcome}`, correctionId: "correction-1" });
const receipt = () => ({ correctionId: "correction-1", correction: { id: "correction-1", initial_batch_id: "batch-1", previous_correction_id: null, reviewed_plan: { planHash: HASH }, idempotency_key: KEY, corrected_by: "owner-1", replacement_version_id: "version-1" }, isCurrent: true, document: { ...doc, header: { ...doc.header, current_correction_id: "correction-1" } } });
let root, container;
beforeEach(() => {
  global.IS_REACT_ACT_ENVIRONMENT = true; sessionStorage.clear(); resetComponentApiMock(api);
  Object.defineProperty(global, "crypto", { configurable: true, value: { randomUUID: () => KEY } });
  api.purchaseCapabilities.mockResolvedValue({ enabled: true }); api.purchaseItems.mockResolvedValue([{ code: "food", name: "TEST ONLY food" }]);
  api.purchaseFiles.mockResolvedValue([{ id: "file-1", original_filename: "TEST ONLY.csv", captured_at: "2026-10-15" }]); api.purchaseHistory.mockResolvedValue([]);
  api.purchaseFile.mockResolvedValue({ id: "file-1", documents: [doc] }); api.previewPurchaseCorrection.mockResolvedValue(plan);
  api.checkCorrectionSavedStatus.mockResolvedValue(status()); api.correctPurchase.mockResolvedValue(receipt());
  container = document.createElement("div"); document.body.appendChild(container); root = createRoot(container);
});
afterEach(async () => { jest.restoreAllMocks(); await act(async () => root.unmount()); container.remove(); });
const button = text => [...container.querySelectorAll("button")].find(b => b.textContent === text);
const click = async el => { await act(async () => el.click()); };
const render = async (actor = "owner-1", store = "berts") => { await act(async () => root.render(<PurchaseImportsTab actorId={actor} restaurantId={store} restaurantName="TEST ONLY" />)); };
async function input(label, value) {
  const el = container.querySelector(`[aria-label="${label}"]`);
  await act(async () => { Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value").set.call(el, value); el.dispatchEvent(new Event("input", { bubbles: true })); });
}
async function preview() {
  await render(); await click(button("TEST ONLY.csv · 2026-10-15")); await click(button("Review correction"));
  await input("Correction reason", body.reason); await input("Received quantity 1", "2.00"); await input("Note 1", line.note);
  await click(container.querySelector('[aria-label="Confirm USD currency"]')); await click(container.querySelector('fieldset input[type="checkbox"]'));
  await click(button("Preview invoice correction"));
}

test("a new correction is durably retained before transport and acknowledgement loss keeps it recoverable", async () => {
  api.correctPurchase.mockImplementation(async (_store, _version, sent, key) => {
    expect(journal().list()[0].body).toEqual(sent); expect(journal().list()[0].key).toBe(key); throw new Error("Dropped acknowledgement");
  });
  await preview(); await click(button("Confirm reversal and replacement"));
  expect(container.textContent).toContain("Dropped acknowledgement"); expect(journal().list()).toEqual([record()]);
  expect(button("Retry exact retained correction").disabled).toBe(true); expect(api.correctPurchase).toHaveBeenCalledTimes(1);
});
test("quota failure prevents the first correction request and preserves editable evidence", async () => {
  await preview(); jest.spyOn(Storage.prototype, "setItem").mockImplementation(() => { throw new Error("quota"); });
  await click(button("Confirm reversal and replacement")); expect(api.correctPurchase).not.toHaveBeenCalled();
  expect(container.textContent).toContain("No correction will be sent"); expect(container.textContent).toContain(body.reason);
});
test("reload and same-user sign-in recover the exact request only after fresh status and manual retry", async () => {
  journal().save(record()); await render();
  expect(api.correctPurchase).not.toHaveBeenCalled(); expect(api.checkCorrectionSavedStatus).not.toHaveBeenCalled();
  expect(container.textContent).toContain("2.00 each"); expect(button("Retry exact retained correction").disabled).toBe(true);
  await render("another-user"); expect(button("Check saved correction status")).toBeUndefined();
  await render(); await click(button("Check saved correction status")); expect(api.correctPurchase).not.toHaveBeenCalled();
  expect(api.checkCorrectionSavedStatus).toHaveBeenCalledWith("berts", "version-1", body, KEY);
  await click(button("Retry exact retained correction")); expect(api.correctPurchase).toHaveBeenCalledWith("berts", "version-1", body, KEY);
  expect(journal().list()).toEqual([]); expect(container.textContent).toContain("Invoice correction saved and confirmed");
});
test.each(["saved", "saved_replaced"])("%s status resolves only this request without resending or clearing other invoices", async outcome => {
  journal().save(record()); journal().save({ ...record(), key: "00000000-0000-4000-8000-000000000002", versionId: "version-2", documentId: "identity-2", documentNumber: "OTHER" });
  api.checkCorrectionSavedStatus.mockResolvedValue(status(outcome)); await render();
  await click([...container.querySelectorAll("button")].find(b => b.textContent === "Check saved correction status"));
  expect(journal().list()).toHaveLength(1); expect(journal().list()[0].documentId).toBe("identity-2");
  expect(api.correctPurchase).not.toHaveBeenCalled(); expect(container.textContent).toContain(outcome === "saved" ? "saved and confirmed" : "later replacement");
});
test.each(["held", "other_request"])("%s retains frozen values and refuses retry or a new correction", async outcome => {
  journal().save(record()); api.checkCorrectionSavedStatus.mockResolvedValue(status(outcome)); await render();
  await click(button("Check saved correction status")); expect(button("Retry exact retained correction").disabled).toBe(true);
  await click(button("TEST ONLY.csv · 2026-10-15")); expect(button("Review correction")).toBeUndefined();
  expect(journal().list()).toEqual([record()]); expect(api.correctPurchase).not.toHaveBeenCalled();
});
test.each(["failed", "malformed", "foreign"])("a %s fresh read removes earlier retry permission and retains the request", async kind => {
  journal().save(record()); await render(); await click(button("Check saved correction status"));
  expect(button("Retry exact retained correction").disabled).toBe(false);
  if (kind === "failed") api.checkCorrectionSavedStatus.mockRejectedValue(new Error("Read unavailable"));
  else api.checkCorrectionSavedStatus.mockResolvedValue(kind === "foreign" ? { ...status(), actorId: "other" } : {});
  await click(button("Check saved correction status")); expect(button("Retry exact retained correction").disabled).toBe(true);
  expect(journal().list()).toEqual([record()]); expect(api.correctPurchase).not.toHaveBeenCalled();
});
test("a late status read after changing actor or location cannot resolve the old request or populate the new workspace", async () => {
  journal().save(record()); let resolve;
  api.checkCorrectionSavedStatus.mockImplementation(() => new Promise(r => { resolve = r; })); await render();
  await click(button("Check saved correction status")); await render("other", "rudds");
  await act(async () => resolve(status("saved")));
  expect(journal().list()).toEqual([record()]); expect(container.textContent).not.toContain("Your invoice correction was saved");
  expect(api.correctPurchase).not.toHaveBeenCalled();
});
test("a late commit after a negative status read is reconciled by exact retry without a fresh key", async () => {
  journal().save(record()); await render(); await click(button("Check saved correction status"));
  // Transport returns the already-saved outcome, representing a commit after the read.
  await click(button("Retry exact retained correction")); expect(api.correctPurchase.mock.calls[0][3]).toBe(KEY);
  expect(api.correctPurchase.mock.calls[0][2]).toEqual(body); expect(journal().list()).toEqual([]);
});
test("failed retry and malformed acknowledgement both require another status read", async () => {
  journal().save(record()); await render(); await click(button("Check saved correction status"));
  api.correctPurchase.mockRejectedValueOnce(new Error("Connection lost")).mockResolvedValueOnce({ correctionId: "incomplete" });
  await click(button("Retry exact retained correction")); expect(button("Retry exact retained correction").disabled).toBe(true);
  await click(button("Check saved correction status")); await click(button("Retry exact retained correction"));
  expect(container.textContent).toContain("Saved correction was not confirmed"); expect(journal().list()).toEqual([record()]);
  expect(api.correctPurchase.mock.calls[0]).toEqual(api.correctPurchase.mock.calls[1]);
});
test("failed cleanup keeps saved evidence and prevents retry", async () => {
  journal().save(record()); api.checkCorrectionSavedStatus.mockResolvedValue(status("saved")); await render();
  jest.spyOn(Storage.prototype, "setItem").mockImplementation(() => { throw new Error("quota"); });
  await click(button("Check saved correction status")); expect(container.textContent).toContain("Correction saved; retained-review cleanup failed");
  expect(button("Retry exact retained correction").disabled).toBe(true); expect(api.correctPurchase).not.toHaveBeenCalled();
});
test("late mutation acknowledgement after an actor/location change keeps the original journal for later recovery", async () => {
  journal().save(record()); let resolve;
  api.correctPurchase.mockImplementation(() => new Promise(r => { resolve = r; }));
  await render(); await click(button("Check saved correction status")); await click(button("Retry exact retained correction"));
  await render("other", "rudds"); await act(async () => resolve(receipt()));
  expect(journal().list()).toEqual([record()]); expect(container.textContent).not.toContain("Invoice correction saved and confirmed");
});
test.each(["idempotency_key", "corrected_by", "replacement_version_id"])("a mismatched acknowledgement %s cannot clear the request", async field => {
  journal().save(record()); const bad = receipt(); bad.correction[field] = "other"; api.correctPurchase.mockResolvedValue(bad);
  await render(); await click(button("Check saved correction status")); await click(button("Retry exact retained correction"));
  expect(journal().list()).toEqual([record()]); expect(container.textContent).toContain("Saved correction was not confirmed");
});
test.each(["document_id", "posted_batch_id", "current_correction_id"])("a foreign or inconsistent acknowledgement header %s stays retained", async field => {
  journal().save(record()); const bad = receipt(); bad.document.header[field] = "other"; api.correctPurchase.mockResolvedValue(bad);
  await render(); await click(button("Check saved correction status")); await click(button("Retry exact retained correction"));
  expect(journal().list()).toEqual([record()]); expect(container.textContent).toContain("Saved correction was not confirmed");
});

test.each(["held", "other_request", "retry_available"])("%s can be explicitly discarded after two fresh reads without sending a command", async outcome => {
  journal().save(record()); journal().save({ ...record(), key: "00000000-0000-4000-8000-000000000002", versionId: "version-2", documentId: "identity-2" });
  api.checkCorrectionSavedStatus.mockResolvedValue(status(outcome)); await render();
  await click(button("TEST ONLY.csv · 2026-10-15")); expect(button("Review correction")).toBeUndefined();
  await click(button("Discard retained correction"));
  const dialog = container.querySelector('[aria-label="Confirm retained correction discard"]');
  expect(dialog.textContent).toContain(body.reason); expect(dialog.textContent).toContain("Original entries to reverse");
  expect(dialog.textContent).toContain("Reviewed replacement entries"); expect(dialog.textContent).toContain("does not cancel");
  expect(journal().list()).toHaveLength(2); expect(button("Retry exact retained correction").disabled).toBe(true);
  await click(button("Confirm discard retained correction"));
  expect(api.checkCorrectionSavedStatus).toHaveBeenCalledTimes(2);
  expect(api.checkCorrectionSavedStatus.mock.calls[0]).toEqual(api.checkCorrectionSavedStatus.mock.calls[1]);
  expect(journal().list().map(r => r.documentId)).toEqual(["identity-2"]); expect(api.correctPurchase).not.toHaveBeenCalled();
  expect(container.textContent).toContain("Source and period holds still apply");
  await click(button("TEST ONLY.csv · 2026-10-15")); expect(button("Review correction")).toBeDefined();
});

test("discarding a held request allows a fresh review with a new key, not automatic reuse or retry", async () => {
  journal().save(record()); api.checkCorrectionSavedStatus.mockResolvedValue(status("held")); await render();
  await click(button("Discard retained correction")); await click(button("Confirm discard retained correction"));
  const nextKey = "00000000-0000-4000-8000-000000000002";
  global.crypto.randomUUID = () => nextKey;
  api.correctPurchase.mockImplementation(async (_store, _version, sent, key) => {
    expect(key).toBe(nextKey); expect(journal().list()[0].key).toBe(nextKey);
    return { ...receipt(), correction: { ...receipt().correction, idempotency_key: nextKey } };
  });
  await preview(); await click(button("Confirm reversal and replacement"));
  expect(api.previewPurchaseCorrection).toHaveBeenCalledTimes(1); expect(api.correctPurchase).toHaveBeenCalledTimes(1);
  expect(journal().list()).toEqual([]);
});

test("cancelling discard preserves exact evidence and grants no retry permission", async () => {
  journal().save(record()); await render(); await click(button("Check saved correction status"));
  expect(button("Retry exact retained correction").disabled).toBe(false);
  await click(button("Discard retained correction")); await click(button("Keep retained correction"));
  expect(journal().list()).toEqual([record()]); expect(button("Retry exact retained correction").disabled).toBe(true);
  expect(api.correctPurchase).not.toHaveBeenCalled();
});

test.each(["saved", "saved_replaced"])("%s refuses discard both before the dialog and after a late original commit", async outcome => {
  journal().save(record()); api.checkCorrectionSavedStatus.mockResolvedValue(status(outcome)); await render();
  await click(button("Discard retained correction")); expect(button("Confirm discard retained correction")).toBeUndefined();
  expect(journal().list()).toEqual([record()]); expect(container.textContent).toContain("It was not discarded");
  api.checkCorrectionSavedStatus.mockResolvedValueOnce(status("held")).mockResolvedValue(status(outcome));
  await click(button("Discard retained correction")); await click(button("Confirm discard retained correction"));
  expect(journal().list()).toEqual([record()]); expect(api.correctPurchase).not.toHaveBeenCalled();
  expect(button("Retry exact retained correction").disabled).toBe(true);
  await click(button("Check saved correction status")); expect(journal().list()).toEqual([]);
});

test.each(["failed", "malformed", "foreign"])("%s confirmation read never discards and removes any earlier retry permission", async kind => {
  journal().save(record()); await render(); await click(button("Check saved correction status"));
  await click(button("Discard retained correction"));
  if (kind === "failed") api.checkCorrectionSavedStatus.mockRejectedValue(new Error("Read unavailable"));
  else api.checkCorrectionSavedStatus.mockResolvedValue(kind === "foreign" ? { ...status(), actorId: "other" } : {});
  await click(button("Confirm discard retained correction")); expect(journal().list()).toEqual([record()]);
  expect(button("Retry exact retained correction").disabled).toBe(true); expect(api.correctPurchase).not.toHaveBeenCalled();
});

test.each(["prepare", "confirm"])("a late %s discard read after actor/location change cannot clear either journal", async phase => {
  journal().save(record()); journal("other", "rudds").save(record()); await render();
  if (phase === "confirm") await click(button("Discard retained correction"));
  let resolve; api.checkCorrectionSavedStatus.mockImplementation(() => new Promise(r => { resolve = r; }));
  await click(button(phase === "confirm" ? "Confirm discard retained correction" : "Discard retained correction"));
  await render("other", "rudds"); await act(async () => resolve(status("held")));
  expect(journal().list()).toEqual([record()]); expect(journal("other", "rudds").list()).toEqual([record()]);
  expect(button("Confirm discard retained correction")).toBeUndefined(); expect(api.correctPurchase).not.toHaveBeenCalled();
});

test("a changed retained record during confirmation is preserved", async () => {
  journal().save(record()); await render(); await click(button("Discard retained correction"));
  let resolve; api.checkCorrectionSavedStatus.mockImplementation(() => new Promise(r => { resolve = r; }));
  await click(button("Confirm discard retained correction"));
  journal().clear(doc.id, KEY); const changed = { ...record(), body: { ...body, reason: "Another retained review" } }; journal().save(changed);
  await act(async () => resolve(status("held"))); expect(journal().list()).toEqual([changed]);
  expect(container.textContent).toContain("retained correction changed"); expect(api.correctPurchase).not.toHaveBeenCalled();
});

test("failed discard storage write keeps the evidence and holds retry", async () => {
  journal().save(record()); await render(); await click(button("Discard retained correction"));
  jest.spyOn(Storage.prototype, "setItem").mockImplementation(() => { throw new Error("quota"); });
  await click(button("Confirm discard retained correction")); expect(journal().list()).toEqual([record()]);
  expect(container.textContent).toContain("storage is unavailable or full");
  expect(button("Retry exact retained correction").disabled).toBe(true); expect(api.correctPurchase).not.toHaveBeenCalled();
});

test("the 32-request cap is shown in the correction form without sending or deleting older requests", async () => {
  for (let n = 0; n < 32; n++) journal().save({ ...record(), documentId: `cap-${n}`, versionId: `cap-${n}`, key: `00000000-0000-4000-8000-${String(n + 2).padStart(12, "0")}` });
  await preview(); await click(button("Confirm reversal and replacement"));
  expect(container.textContent).toContain("32-request limit"); expect(journal().list()).toHaveLength(32);
  expect(api.correctPurchase).not.toHaveBeenCalled();
});
