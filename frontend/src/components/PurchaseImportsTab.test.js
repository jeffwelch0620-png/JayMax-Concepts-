import React, { act } from "react";
import { createRoot } from "react-dom/client";
import { PurchaseDocumentReview, PurchaseCorrectionReview, PurchaseImportsTab } from "./PurchaseImportsTab";
import * as api from "../lib/api";

jest.mock("../lib/api", () => ({
  purchaseCapabilities: jest.fn(), purchaseItems: jest.fn(), purchaseFiles: jest.fn(),
  purchaseHistory: jest.fn(), capturePurchase: jest.fn(), postPurchase: jest.fn(),
  previewPurchaseCorrection: jest.fn(), correctPurchase: jest.fn(), purchaseCorrections: jest.fn(),
  purchaseVendors: jest.fn(), captureManualPurchase: jest.fn(), capturePurchaseSource: jest.fn(),
}));

const doc = {
  id: "document-1", status: "awaiting_review", errors: [],
  header: { vendor_id: "pfg", document_number: "TEST-1", document_type: "invoice", invoice_date: "2026-10-01", confirmed_currency: "USD", fees_source: "1", tax_source: "2" },
  totals: { lineTotal: "40", statedTotal: "43", difference: "0" },
  lines: [{ id: "line-1", description_snapshot: "Synthetic food", shipped_quantity_source: "2", extended_amount_source: "40" }],
};
let container, root;
beforeEach(() => {
  global.IS_REACT_ACT_ENVIRONMENT = true;
  Object.defineProperty(global, "crypto", { configurable: true, value: { randomUUID: jest.fn(() => "same-request-key") } });
  container = document.createElement("div"); document.body.appendChild(container); root = createRoot(container);
  jest.clearAllMocks();
});

const postedDoc = { ...doc, status: "posted", correctionAvailable: true, sourceErrors: [],
  currentMappings: [{ line_id: "line-1", classification: "food", movement_kind: "receipt", item_code: "food", base_unit: "lb",
    received_quantity: "2", received_unit: "case", base_units_per_received_unit: "20", inventory_record_date: "2026-10-04" }] };
const correctionPlan = { planHash: "reviewed-plan", status: "ready", initialBatchId: "batch-1", previousCorrectionId: null,
  review: { reason: "Verified delivered quantities", confirmed_currency: "USD", received_date: "2026-10-04", lines: [] },
  before: [{ line_id: "line-1", item_code: "food", base_quantity: "40", inventory_cost_amount: "40", inventory_record_date: "2026-10-04" }],
  after: [{ line_id: "line-1", item_code: "food", base_quantity: "60", inventory_cost_amount: "40", inventory_record_date: "2026-10-04" }],
  blocks: [], affectedPeriods: [], legacyClosedPeriods: [], linkedDocuments: [],
  separateComponents: { before: { fees_source: "1", tax_source: "2" }, after: { fees_source: "1", tax_source: "2" } } };
const button = text => [...container.querySelectorAll("button")].find(b => b.textContent === text);
async function correctionForm() {
  await click(button("Review correction"));
  await input(container.querySelector('[aria-label="Correction reason"]'), "Verified delivered quantities");
  await input(container.querySelector('[aria-label="Received quantity 1"]'), "3");
  await input(container.querySelector('[aria-label="Note 1"]'), "Counted and converted delivered quantity");
  await click(container.querySelector('[aria-label="Confirm USD currency"]'));
  await click(container.querySelector('fieldset input[type="checkbox"]'));
  await click(button("Preview invoice correction"));
}

test("correction review starts from current mappings and previews before posting", async () => {
  const preview = jest.fn().mockResolvedValue(correctionPlan), correct = jest.fn();
  await act(async () => root.render(<PurchaseCorrectionReview document={postedDoc} items={[{ code: "food", name: "Food" }]} history={[]} onPreview={preview} onCorrect={correct} />));
  await click(button("Review correction"));
  expect(container.querySelector('[aria-label="Received quantity 1"]').value).toBe("2");
  expect(container.querySelector('[aria-label="Received date"]').value).toBe("2026-10-04");
  expect(container.querySelector('fieldset input[type="checkbox"]').checked).toBe(false);
  await input(container.querySelector('[aria-label="Correction reason"]'), "Verified delivered quantities");
  await input(container.querySelector('[aria-label="Received quantity 1"]'), "3");
  await input(container.querySelector('[aria-label="Note 1"]'), "Counted quantity");
  await click(container.querySelector('[aria-label="Confirm USD currency"]'));
  await click(container.querySelector('fieldset input[type="checkbox"]')); await click(button("Preview invoice correction"));
  expect(preview.mock.calls[0][1].lines[0].received_quantity).toBe("3");
  expect(correct).not.toHaveBeenCalled(); expect(container.textContent).toContain("Reverse original entry");
  expect(container.textContent).toContain("Separate tax: 2 → 2");
});

test("closed periods and linked credits hold the correction and allow a fresh preview", async () => {
  const held = { ...correctionPlan, status: "held", blocks: ["Reopen affected periods", "Linked credit held"],
    affectedPeriods: [{ id: "closed-1", period_start: "2026-10-01", period_end_exclusive: "2026-10-08" }],
    linkedDocuments: [{ line_id: "credit-1", document_number: "CREDIT-1" }] };
  const preview = jest.fn().mockResolvedValue(held), correct = jest.fn();
  await act(async () => root.render(<PurchaseCorrectionReview document={postedDoc} items={[]} history={[]} onPreview={preview} onCorrect={correct} />));
  await correctionForm(); expect(button("Confirm reversal and replacement").disabled).toBe(true);
  expect(container.textContent).toContain("2026-10-01 to before 2026-10-08"); expect(container.textContent).toContain("CREDIT-1");
  await click(button("Confirm reversal and replacement")); expect(correct).not.toHaveBeenCalled();
  await click(button("Revise / refresh correction")); expect(container.querySelector('[aria-label="Correction comparison"]')).toBeNull();
  expect(container.querySelector("fieldset").disabled).toBe(false);
});

test("a failed correction freezes the review and retries its exact body and key", async () => {
  const preview = jest.fn().mockResolvedValue(correctionPlan), correct = jest.fn().mockRejectedValue(new Error("Connection lost"));
  await act(async () => root.render(<PurchaseCorrectionReview document={postedDoc} items={[]} history={[]} onPreview={preview} onCorrect={correct} />));
  await correctionForm(); await click(button("Confirm reversal and replacement"));
  expect(container.textContent).toContain("Connection lost"); expect(button("Revise / refresh correction")).toBeUndefined();
  expect(container.querySelector('[aria-label="Correction reason"]').disabled).toBe(true);
  await click(button("Retry same invoice correction")); expect(correct.mock.calls[1]).toEqual(correct.mock.calls[0]);
  expect(correct.mock.calls[0][1].expected_plan_hash).toBe("reviewed-plan");
});

test("a failed or incomplete read-only preview can be edited and retried", async () => {
  const preview = jest.fn().mockResolvedValueOnce({ status: "ready" }).mockResolvedValueOnce(correctionPlan);
  await act(async () => root.render(<PurchaseCorrectionReview document={postedDoc} items={[]} history={[]} onPreview={preview} onCorrect={jest.fn()} />));
  await correctionForm(); expect(container.textContent).toContain("Correction preview was not confirmed");
  expect(container.querySelector("fieldset").disabled).toBe(false);
  await click(button("Preview invoice correction")); expect(preview).toHaveBeenCalledTimes(2);
  expect(container.querySelector('[aria-label="Correction comparison"]')).not.toBeNull();
});

test("an incomplete correction acknowledgement cannot announce success", async () => {
  api.purchaseCapabilities.mockResolvedValue({ enabled: true }); api.purchaseItems.mockResolvedValue([]);
  api.purchaseFiles.mockResolvedValue([]); api.purchaseHistory.mockResolvedValue([]);
  api.capturePurchase.mockResolvedValue({ id: "file-1", original_filename: "synthetic.csv", captureStatus: "captured", documents: [postedDoc], parse_errors: [], source_sha256: "abc", source_record_count: 1 });
  api.previewPurchaseCorrection.mockResolvedValue(correctionPlan);
  api.correctPurchase.mockResolvedValue({ correctionId: "correction-1", correction: { reviewed_plan: correctionPlan } });
  await act(async () => root.render(<PurchaseImportsTab restaurantId="berts" restaurantName="Test" />));
  const picker = container.querySelector('[aria-label="Invoice file"]'); Object.defineProperty(picker, "files", { value: [new File(["Synthetic"], "synthetic.csv")], configurable: true });
  await act(async () => picker.dispatchEvent(new Event("change", { bubbles: true })));
  await click(button("Capture / retry file")); await correctionForm(); await click(button("Confirm reversal and replacement"));
  expect(container.textContent).toContain("Saved correction was not confirmed"); expect(container.textContent).not.toContain("Invoice correction saved and confirmed");
});

test("correction history exposes reasons and predecessor links without modifying entries", async () => {
  const history = jest.fn().mockResolvedValue([{ id: "c-2", reason: "Verified supplier reissue", corrected_by: "Manager", corrected_at: "2026-10-04", previous_correction_id: "c-1", reviewed_plan: correctionPlan }]);
  const correct = jest.fn();
  await act(async () => root.render(<PurchaseCorrectionReview document={postedDoc} items={[]} history={[]} onPreview={jest.fn()} onCorrect={correct} onHistory={history} />));
  await click(button("Show correction history")); expect(history).toHaveBeenCalledWith("document-1");
  expect(container.textContent).toContain("Verified supplier reissue"); expect(container.textContent).toContain("c-1"); expect(correct).not.toHaveBeenCalled();
});
afterEach(async () => { await act(async () => root.unmount()); container.remove(); });
async function input(node, value) {
  await act(async () => {
    Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value").set.call(node, value);
    node.dispatchEvent(new Event("input", { bubbles: true }));
    node.dispatchEvent(new Event("change", { bubbles: true }));
  });
}
async function click(node) { await act(async () => node.click()); }

test("held totals cannot be posted", async () => {
  const post = jest.fn();
  await act(async () => root.render(<PurchaseDocumentReview document={{ ...doc, status: "held", errors: ["Unexplained difference"] }} items={[]} history={[]} onPost={post} />));
  expect(container.textContent).toContain("Unexplained difference");
  expect(container.querySelector("button").disabled).toBe(true);
  await click(container.querySelector("button")); expect(post).not.toHaveBeenCalled();
});

test("a failed post retains the exact review and retries the same key", async () => {
  const post = jest.fn().mockRejectedValue(new Error("Connection lost"));
  await act(async () => root.render(<PurchaseDocumentReview document={doc} items={[]} history={[]} onPost={post} />));
  await input(container.querySelector('[aria-label="Received date"]'), "2026-10-04");
  await input(container.querySelector('[aria-label="Note 1"]'), "Verified synthetic line");
  await click(container.querySelector('[aria-label="Confirm USD currency"]'));
  await click(container.querySelector('fieldset input[type="checkbox"]'));
  await click(container.querySelector("button"));
  expect(post).toHaveBeenCalledTimes(1);
  expect(container.textContent).toContain("Connection lost");
  expect(container.querySelector('[aria-label="Note 1"]').disabled).toBe(false); // inherited fieldset disabling
  expect(container.querySelector("fieldset").disabled).toBe(true);
  await click(container.querySelector("button"));
  expect(post).toHaveBeenCalledTimes(2);
  expect(post.mock.calls[1]).toEqual(post.mock.calls[0]);
  expect(post.mock.calls[0][1].received_date).toBe("2026-10-04");
});

test("capture failure never displays success and retry uses the original upload key", async () => {
  api.purchaseCapabilities.mockResolvedValue({ enabled: true }); api.purchaseItems.mockResolvedValue([]);
  api.purchaseFiles.mockResolvedValue([]); api.purchaseHistory.mockResolvedValue([]);
  api.capturePurchase.mockRejectedValueOnce(new Error("Capture interrupted")).mockResolvedValueOnce({ id: "file-1", original_filename: "synthetic.csv", captureStatus: "captured", documents: [], parse_errors: [], source_sha256: "abc", source_record_count: 0 });
  await act(async () => root.render(<PurchaseImportsTab restaurantId="berts" restaurantName="Test" />));
  const picker = container.querySelector('[aria-label="Invoice file"]');
  Object.defineProperty(picker, "files", { value: [new File(["Synthetic"], "synthetic.csv")], configurable: true });
  await act(async () => picker.dispatchEvent(new Event("change", { bubbles: true })));
  const button = [...container.querySelectorAll("button")].find(b => b.textContent === "Capture / retry file");
  await click(button);
  expect(container.textContent).toContain("Capture interrupted");
  expect(container.textContent).not.toContain("Original file retained.");
  await click(button);
  expect(api.capturePurchase.mock.calls[1]).toEqual(api.capturePurchase.mock.calls[0]);
  expect(container.textContent).toContain("Original file retained.");
});

test("an incomplete posting acknowledgement cannot announce success", async () => {
  api.purchaseCapabilities.mockResolvedValue({ enabled: true }); api.purchaseItems.mockResolvedValue([]);
  api.purchaseFiles.mockResolvedValue([]); api.purchaseHistory.mockResolvedValue([]);
  api.capturePurchase.mockResolvedValue({ id: "file-1", original_filename: "synthetic.csv", captureStatus: "captured", documents: [doc], parse_errors: [], source_sha256: "abc", source_record_count: 1 });
  api.postPurchase.mockResolvedValue({ batchId: "batch-1", document: { ...doc, status: "awaiting_review" } });
  await act(async () => root.render(<PurchaseImportsTab restaurantId="berts" restaurantName="Test" />));
  const picker = container.querySelector('[aria-label="Invoice file"]');
  Object.defineProperty(picker, "files", { value: [new File(["Synthetic"], "synthetic.csv")], configurable: true });
  await act(async () => picker.dispatchEvent(new Event("change", { bubbles: true })));
  await click([...container.querySelectorAll("button")].find(b => b.textContent === "Capture / retry file"));
  await input(container.querySelector('[aria-label="Note 1"]'), "Verified synthetic line");
  await click(container.querySelector('[aria-label="Confirm USD currency"]'));
  await click(container.querySelector('fieldset input[type="checkbox"]'));
  await click([...container.querySelectorAll("button")].find(b => b.textContent === "Confirm and post purchase"));
  expect(container.textContent).toContain("Saved outcome was not confirmed");
  expect(container.textContent).not.toContain("Purchase posted and confirmed.");
});

async function selectValue(label, value) {
  const el = container.querySelector(`[aria-label="${label}"]`);
  await act(async () => { Object.getOwnPropertyDescriptor(HTMLSelectElement.prototype, "value").set.call(el, value); el.dispatchEvent(new Event("change", { bubbles: true })); });
}

test("manual source capture opens retained details without posting inventory", async () => {
  api.purchaseCapabilities.mockResolvedValue({ enabled: true, manualReady: true }); api.purchaseItems.mockResolvedValue([]);
  api.purchaseFiles.mockResolvedValue([]); api.purchaseHistory.mockResolvedValue([]);
  api.purchaseVendors.mockResolvedValue([{ id: "other", name: "Invented supplier" }]);
  api.captureManualPurchase.mockImplementation(async (store, body) => ({ id: "manual-file", original_filename: "manual-source.json", captureStatus: "captured", documents: [], manualRecord: body }));
  await act(async () => root.render(<PurchaseImportsTab restaurantId="berts" restaurantName="Test" />));
  await selectValue("Manual supplier", "other");
  await input(container.querySelector('[aria-label="Invoice / receipt number"]'), "MANUAL-1");
  const note = container.querySelector('[aria-label="Manual source evidence"]');
  await act(async () => { Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, "value").set.call(note, "Invented receipt"); note.dispatchEvent(new Event("input", { bubbles: true })); });
  await click(container.querySelector('[aria-label="Confirm manual source details"]'));
  await click(button("Retain manual source for review"));
  expect(api.captureManualPurchase).toHaveBeenCalledTimes(1); expect(api.postPurchase).not.toHaveBeenCalled();
  expect(container.textContent).toContain("Manual source retained.");
  expect(container.querySelector('[aria-label="Retained manual source details"]').textContent).toContain("MANUAL-1");
  expect(container.querySelector('[aria-label="Manual source evidence"]').value).toBe("");
});

test("other receipt upload retains source bytes without the vendor CSV parser route", async () => {
  api.purchaseCapabilities.mockResolvedValue({ enabled: true, manualReady: true }); api.purchaseItems.mockResolvedValue([]);
  api.purchaseFiles.mockResolvedValue([]); api.purchaseHistory.mockResolvedValue([]); api.purchaseVendors.mockResolvedValue([]);
  api.capturePurchaseSource.mockResolvedValue({ id: "attachment", original_filename: "synthetic.pdf", captureStatus: "captured", documents: [] });
  await act(async () => root.render(<PurchaseImportsTab restaurantId="berts" restaurantName="Test" />));
  await selectValue("Source upload type", "source");
  const picker = container.querySelector('[aria-label="Invoice file"]'), source = new File(["Invented source"], "synthetic.pdf");
  Object.defineProperty(picker, "files", { value: [source], configurable: true });
  await act(async () => picker.dispatchEvent(new Event("change", { bubbles: true })));
  await click(button("Capture / retry file"));
  expect(api.capturePurchaseSource).toHaveBeenCalledWith("berts", source, "same-request-key");
  expect(api.capturePurchase).not.toHaveBeenCalled(); expect(api.postPurchase).not.toHaveBeenCalled();
});
