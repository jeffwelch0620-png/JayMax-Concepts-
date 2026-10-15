import React, { act } from "react";
import { createRoot } from "react-dom/client";
import { PurchaseDocumentReview, PurchaseCorrectionReview, PurchaseImportsTab } from "./PurchaseImportsTab";
import * as api from "../lib/api";
import { readStateWithDeadline, STATE_READ_TIMEOUT_MS } from "../lib/stateRead";
import { pendingPurchaseJournal, pendingPurchaseRecord } from "../lib/pendingPurchases";

jest.mock("../lib/api", () => ({
  purchaseCapabilities: jest.fn(), purchaseItems: jest.fn(), purchaseFiles: jest.fn(), purchaseFile: jest.fn(), purchaseFileDocument: jest.fn(), checkPurchaseSavedStatus: jest.fn(),
  purchaseHistory: jest.fn(), capturePurchase: jest.fn(), postPurchase: jest.fn(),
  previewPurchaseCorrection: jest.fn(), correctPurchase: jest.fn(), purchaseCorrections: jest.fn(),
  purchaseVendors: jest.fn(), captureManualPurchase: jest.fn(), capturePurchaseSource: jest.fn(),
}));

const doc = {
  id: "document-1", status: "awaiting_review", errors: [],
  currentSource: { documentId: "identity-1", versionId: "document-1", fileId: "file-1", revision: 1 },
  header: { document_id: "identity-1", revision: 1, vendor_id: "pfg", document_number: "TEST-1", document_type: "invoice", invoice_date: "2026-10-01", confirmed_currency: "USD", fees_source: "1", tax_source: "2" },
  totals: { lineTotal: "40", statedTotal: "43", difference: "0" },
  lines: [{ id: "line-1", description_snapshot: "Synthetic food", shipped_quantity_source: "2", extended_amount_source: "40" }],
};
let container, root;
beforeEach(() => {
  global.IS_REACT_ACT_ENVIRONMENT = true;
  Object.defineProperty(global, "crypto", { configurable: true, value: { randomUUID: jest.fn(() => "00000000-0000-4000-8000-000000000001") } });
  container = document.createElement("div"); document.body.appendChild(container); root = createRoot(container);
  sessionStorage.clear();
  jest.clearAllMocks();
});

const postedDoc = { ...doc, status: "posted", correctionAvailable: true, sourceErrors: [],
  currentMappings: [{ line_id: "line-1", classification: "food", movement_kind: "receipt", item_code: "food", base_unit: "lb",
    received_quantity: "2", received_unit: "case", base_units_per_received_unit: "20", inventory_record_date: "2026-10-04", decision_note: "Synthetic confirmed mapping" }] };
const correctionPlan = { planHash: "1".repeat(64), status: "ready", initialBatchId: "batch-1", previousCorrectionId: null,
  review: { reason: "Verified delivered quantities", confirmed_currency: "USD", received_date: "2026-10-04", lines: [{ line_id: "line-1", classification: "food", movement_kind: "receipt", item_code: "food", base_unit: "lb", received_quantity: "3", received_unit: "case", base_units_per_received_unit: "20", movement_date: null, original_line_id: null, verified: true, note: "Counted and converted delivered quantity" }] },
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
  expect(correct.mock.calls[0][1].expected_plan_hash).toBe(correctionPlan.planHash);
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
  await act(async () => root.render(<PurchaseImportsTab actorId="test-owner" restaurantId="berts" restaurantName="Test" />));
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
  await act(async () => root.render(<PurchaseImportsTab actorId="test-owner" restaurantId="berts" restaurantName="Test" />));
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
  await act(async () => root.render(<PurchaseImportsTab actorId="test-owner" restaurantId="berts" restaurantName="Test" />));
  const picker = container.querySelector('[aria-label="Invoice file"]');
  Object.defineProperty(picker, "files", { value: [new File(["Synthetic"], "synthetic.csv")], configurable: true });
  await act(async () => picker.dispatchEvent(new Event("change", { bubbles: true })));
  await click([...container.querySelectorAll("button")].find(b => b.textContent === "Capture / retry file"));
  await input(container.querySelector('[aria-label="Note 1"]'), "Verified synthetic line");
  await click(container.querySelector('[aria-label="Confirm USD currency"]'));
  await click(container.querySelector('fieldset input[type="checkbox"]'));
  await click([...container.querySelectorAll("button")].find(b => b.textContent === "Confirm and post purchase"));
  expect(container.textContent).toContain("Saved outcome was not confirmed");
  expect(container.textContent).not.toContain("Your purchase was saved and confirmed.");
});

const savedPurchase = { ...doc, status: "posted", header: { ...doc.header,
  posted_batch_id: "batch-1", posted_version_id: doc.id, initial_posted_version_id: doc.id,
  posted_request_key: "00000000-0000-4000-8000-000000000001", current_correction_id: null }, currentMappings: postedDoc.currentMappings };
const retainedFile = { id: "file-1", original_filename: "TEST-ONLY-recovery.csv", captured_at: "2026-10-11", documents: [doc], parse_errors: [], source_record_count: 1 };
const correctedPurchase = (reissued = true) => ({ ...savedPurchase,
  status: reissued ? "held" : "posted", errors: reissued ? ["A different version was already posted; correction review is required"] : [],
  header: { ...savedPurchase.header, posted_version_id: reissued ? "replacement-1" : doc.id, current_correction_id: "correction-1" } });
async function openRecoveryReview() {
  api.purchaseCapabilities.mockResolvedValue({ enabled: true }); api.purchaseItems.mockResolvedValue([]);
  api.purchaseFiles.mockResolvedValue([retainedFile]); api.purchaseHistory.mockResolvedValue([]);
  api.purchaseFile.mockResolvedValue(retainedFile);
  await act(async () => root.render(<PurchaseImportsTab actorId="test-owner" key="berts" restaurantId="berts" restaurantName="Test" />));
  await click(button("TEST-ONLY-recovery.csv · 2026-10-11"));
  await input(container.querySelector('[aria-label="Received date"]'), "2026-10-11");
  await input(container.querySelector('[aria-label="Note 1"]'), "TEST ONLY retained reviewed quantity");
  await click(container.querySelector('[aria-label="Confirm USD currency"]'));
  await click(container.querySelector('fieldset input[type="checkbox"]'));
}

test("checking a committed purchase resolves an unknown outcome without another post", async () => {
  api.postPurchase.mockRejectedValue(new Error("Response lost"));
  api.checkPurchaseSavedStatus.mockResolvedValue(savedPurchase);
  await openRecoveryReview(); await click(button("Confirm and post purchase"));
  await click(button("Check saved status"));
  expect(api.checkPurchaseSavedStatus).toHaveBeenCalledWith("berts", doc.id);
  expect(api.postPurchase).toHaveBeenCalledTimes(1);
  expect(container.textContent).toContain("Your purchase was saved and confirmed.");
  expect(button("Retry same purchase posting")).toBeUndefined();
  expect(button("Confirm and post purchase")).toBeUndefined();
});

test("an awaiting-review saved-status read preserves the original frozen retry", async () => {
  const status = "awaiting_review";
  api.postPurchase.mockRejectedValue(new Error("Response lost"));
  api.checkPurchaseSavedStatus.mockResolvedValue({ ...doc, status });
  await openRecoveryReview(); await click(button("Confirm and post purchase"));
  const original = api.postPurchase.mock.calls[0];
  await click(button("Check saved status"));
  expect(container.textContent).toContain("No posted outcome was visible in this read");
  expect(container.querySelector("fieldset").disabled).toBe(true);
  expect(container.querySelector('[aria-label="Received date"]').value).toBe("2026-10-11");
  expect(container.querySelector('[aria-label="Note 1"]').value).toBe("TEST ONLY retained reviewed quantity");
  expect(api.postPurchase).toHaveBeenCalledTimes(1);
  await click(button("Retry same purchase posting"));
  expect(api.postPurchase.mock.calls[1]).toEqual(original);
  expect(crypto.randomUUID).toHaveBeenCalledTimes(1);
});

test.each([true, false])("a corrected purchase (reissued=%s) resolves a lost response through a read without posting again", async reissued => {
  api.postPurchase.mockRejectedValue(new Error("Response lost"));
  api.checkPurchaseSavedStatus.mockResolvedValue(correctedPurchase(reissued));
  await openRecoveryReview(); await click(button("Confirm and post purchase")); await click(button("Check saved status"));
  expect(container.textContent).toContain("Your original purchase was saved and has since been corrected");
  expect(container.textContent).not.toContain("Held for review");
  expect(button("Retry same purchase posting")).toBeUndefined();
  expect(button("Confirm and post purchase")).toBeUndefined();
  expect(api.postPurchase).toHaveBeenCalledTimes(1);
});

test.each([true, false])("the exact retry receipt resolves a corrected purchase (reissued=%s)", async reissued => {
  api.postPurchase.mockRejectedValueOnce(new Error("Response lost")).mockResolvedValueOnce({ batchId: "batch-1", document: correctedPurchase(reissued) });
  await openRecoveryReview(); await click(button("Confirm and post purchase")); await click(button("Retry same purchase posting"));
  expect(api.postPurchase.mock.calls[1]).toEqual(api.postPurchase.mock.calls[0]);
  expect(container.textContent).toContain("Your original purchase was saved and has since been corrected");
  expect(button("Retry same purchase posting")).toBeUndefined();
});

test("a held status shows its reasons and blocks posting until a fresh read clears the hold", async () => {
  api.postPurchase.mockRejectedValue(new Error("Response lost"));
  api.checkPurchaseSavedStatus.mockResolvedValueOnce({ ...doc, status: "held", errors: ["Earlier purchase uses this invoice number"] }).mockResolvedValueOnce(doc);
  await openRecoveryReview(); await click(button("Confirm and post purchase")); await click(button("Check saved status"));
  expect(container.textContent).toContain("Earlier purchase uses this invoice number");
  expect(container.textContent).not.toContain("No posted outcome was visible");
  expect(button("Retry same purchase posting").disabled).toBe(true);
  await click(button("Retry same purchase posting")); expect(api.postPurchase).toHaveBeenCalledTimes(1);
  await click(button("Check saved status")); expect(button("Retry same purchase posting").disabled).toBe(false);
  await click(button("Retry same purchase posting")); expect(api.postPurchase.mock.calls[1]).toEqual(api.postPurchase.mock.calls[0]);
  expect(crypto.randomUUID).toHaveBeenCalledTimes(1);
});

test("two independent clients retain the losing client's reviewed date, quantity and note", async () => {
  const winnerRoot = root, winnerContainer = container;
  let receipt;
  crypto.randomUUID.mockReturnValueOnce("00000000-0000-4000-8000-000000000002").mockReturnValueOnce("00000000-0000-4000-8000-000000000003");
  api.postPurchase.mockImplementationOnce(async (_store, _id, body, key) => {
    receipt = { ...savedPurchase, header: { ...savedPurchase.header, posted_request_key: key },
      currentMappings: [{ ...postedDoc.currentMappings[0], inventory_record_date: body.received_date }] };
    return { batchId: "batch-1", document: receipt };
  }).mockRejectedValue(new Error("Already posted; correction review is required"));
  await openRecoveryReview(); await input(container.querySelector('[aria-label="Received date"]'), "2026-10-10");
  await click(button("Confirm and post purchase"));
  expect(container.textContent).toContain("Your purchase was saved and confirmed");
  container = document.createElement("div"); document.body.appendChild(container); root = createRoot(container);
  try {
    await openRecoveryReview(); await input(container.querySelector('[aria-label="Received quantity 1"]'), "7");
    await click(container.querySelector('fieldset input[type="checkbox"]'));
    await click(button("Confirm and post purchase"));
    api.checkPurchaseSavedStatus.mockResolvedValue(receipt);
    await click(button("Check saved status"));
    expect(container.textContent).toContain("posted by a different request or version");
    expect(container.textContent).not.toContain("Your purchase was saved");
    expect(container.querySelector('[aria-label="Received date"]').value).toBe("2026-10-11");
    expect(container.querySelector('[aria-label="Received quantity 1"]').value).toBe("7");
    expect(container.querySelector('[aria-label="Note 1"]').value).toBe("TEST ONLY retained reviewed quantity");
    expect(container.querySelector("fieldset").disabled).toBe(true);
    expect(button("Retry same purchase posting").disabled).toBe(true);
    api.purchaseFileDocument.mockResolvedValue(receipt); api.purchaseCorrections.mockResolvedValue([]);
    await click(button("Show saved purchase and correction history"));
    expect(container.querySelector('[aria-label="Saved purchase comparison"]').textContent).toContain("2026-10-10");
    expect(container.querySelector('[aria-label="Received date"]').value).toBe("2026-10-11");
    expect(api.postPurchase).toHaveBeenCalledTimes(2);
    expect(api.postPurchase.mock.calls[1][3]).toBe("00000000-0000-4000-8000-000000000003");
  } finally { await act(async () => winnerRoot.unmount()); winnerContainer.remove(); }
});

test("the same key on a different original version cannot close this review", async () => {
  api.postPurchase.mockRejectedValue(new Error("Response lost"));
  api.checkPurchaseSavedStatus.mockResolvedValue({ ...savedPurchase, header: { ...savedPurchase.header, initial_posted_version_id: "other-original", current_correction_id: "correction-1" } });
  await openRecoveryReview(); await click(button("Confirm and post purchase")); await click(button("Check saved status"));
  expect(container.textContent).toContain("posted by a different request or version");
  expect(container.textContent).not.toContain("Your original purchase was saved");
  expect(container.querySelector('[aria-label="Note 1"]').value).toBe("TEST ONLY retained reviewed quantity");
  expect(button("Retry same purchase posting").disabled).toBe(true);
});

test("read-only comparison follows the corrected version and shows correction evidence", async () => {
  const recovery = correctedPurchase();
  api.postPurchase.mockRejectedValue(new Error("Response lost")); api.checkPurchaseSavedStatus.mockResolvedValue(recovery);
  api.purchaseFileDocument.mockResolvedValue({ ...recovery, id: "replacement-1", status: "posted", errors: [],
    currentMappings: [{ ...postedDoc.currentMappings[0], received_quantity: "3", decision_note: "Verified supplier reissue" }] });
  api.purchaseCorrections.mockResolvedValue([{ id: "correction-1", corrected_at: "2026-10-11", reason: "Verified supplier reissue", previous_correction_id: null }]);
  await openRecoveryReview(); await click(button("Confirm and post purchase")); await click(button("Check saved status"));
  await click(button("Show saved purchase and correction history"));
  expect(api.purchaseFileDocument).toHaveBeenCalledWith("berts", "replacement-1");
  expect(api.purchaseCorrections).toHaveBeenCalledWith("berts", doc.id);
  expect(container.querySelector('[aria-label="Saved purchase comparison"]').textContent).toContain("Verified supplier reissue");
  expect(api.postPurchase).toHaveBeenCalledTimes(1); expect(api.correctPurchase).not.toHaveBeenCalled();
});

test("a changed comparison read retains the competing frozen review without showing stale details", async () => {
  api.postPurchase.mockRejectedValue(new Error("Response lost"));
  const other = { ...savedPurchase, header: { ...savedPurchase.header, posted_request_key: "other-key" } };
  api.checkPurchaseSavedStatus.mockResolvedValue(other);
  api.purchaseFileDocument.mockResolvedValue({ ...other, header: { ...other.header, current_correction_id: "new-correction" } });
  api.purchaseCorrections.mockResolvedValue([]);
  await openRecoveryReview(); await click(button("Confirm and post purchase")); await click(button("Check saved status"));
  await click(button("Show saved purchase and correction history"));
  expect(container.textContent).toContain("details changed or could not be confirmed");
  expect(container.querySelector('[aria-label="Saved purchase comparison"]')).toBeNull();
  expect(container.querySelector('[aria-label="Received date"]').value).toBe("2026-10-11");
  expect(button("Retry same purchase posting").disabled).toBe(true);
});

test("comparison displays the persisted decision note while retaining the competing user's frozen note", async () => {
  api.postPurchase.mockRejectedValue(new Error("Response lost"));
  const other = { ...savedPurchase, header: { ...savedPurchase.header, posted_request_key: "other-key" },
    currentMappings: [{ ...postedDoc.currentMappings[0], decision_note: "TEST ONLY original delivered-unit verification" }] };
  api.checkPurchaseSavedStatus.mockResolvedValue(other);
  api.purchaseFileDocument.mockResolvedValue(other); api.purchaseCorrections.mockResolvedValue([]);
  await openRecoveryReview(); await click(button("Confirm and post purchase")); await click(button("Check saved status"));
  await click(button("Show saved purchase and correction history"));
  const saved = container.querySelector('[aria-label="Saved purchase comparison"]');
  expect(saved.querySelector('tbody tr td:last-child').textContent).toBe("TEST ONLY original delivered-unit verification");
  expect(container.querySelector('[aria-label="Note 1"]').value).toBe("TEST ONLY retained reviewed quantity");
  expect(button("Retry same purchase posting").disabled).toBe(true);
  expect(api.postPurchase).toHaveBeenCalledTimes(1); expect(api.correctPurchase).not.toHaveBeenCalled();
});

test("a malformed persisted decision note cannot replace the comparison or frozen review", async () => {
  api.postPurchase.mockRejectedValue(new Error("Response lost"));
  const other = { ...savedPurchase, header: { ...savedPurchase.header, posted_request_key: "other-key" },
    currentMappings: [{ ...postedDoc.currentMappings[0], decision_note: { unexpected: "Malformed note" } }] };
  api.checkPurchaseSavedStatus.mockResolvedValue(other);
  api.purchaseFileDocument.mockResolvedValue(other); api.purchaseCorrections.mockResolvedValue([]);
  await openRecoveryReview(); await click(button("Confirm and post purchase")); await click(button("Check saved status"));
  await click(button("Show saved purchase and correction history"));
  expect(container.querySelector('[aria-label="Saved purchase comparison"]')).toBeNull();
  expect(container.textContent).toContain("details changed or could not be confirmed");
  expect(container.querySelector('[aria-label="Note 1"]').value).toBe("TEST ONLY retained reviewed quantity");
  expect(api.postPurchase).toHaveBeenCalledTimes(1);
});

test("an unauthorized saved-status read keeps the original request and review", async () => {
  api.postPurchase.mockRejectedValue(new Error("Response lost"));
  api.checkPurchaseSavedStatus.mockRejectedValue({ response: { status: 401, data: { detail: "Authentication required" } } });
  await openRecoveryReview(); await click(button("Confirm and post purchase"));
  await click(button("Check saved status"));
  expect(container.textContent).toContain("Saved status could not be confirmed: Authentication required");
  expect(container.textContent).not.toContain("Your purchase was saved and confirmed.");
  expect(container.querySelector("fieldset").disabled).toBe(true);
  await click(button("Retry same purchase posting"));
  expect(api.postPurchase.mock.calls[1]).toEqual(api.postPurchase.mock.calls[0]);
});

test.each([
  ["different document", { ...savedPurchase, id: "other-document" }],
  ["missing batch", { ...savedPurchase, header: { ...savedPurchase.header, posted_batch_id: null } }],
  ["different posted version", { ...savedPurchase, header: { ...savedPurchase.header, posted_version_id: "other-version" } }],
  ["unknown status", { ...doc, status: "unexpected" }],
  ["missing request identity", { ...savedPurchase, header: { ...savedPurchase.header, posted_request_key: null } }],
  ["malformed correction identity", { ...savedPurchase, header: { ...savedPurchase.header, current_correction_id: {} } }],
])("a saved-status read with %s cannot resolve the frozen outcome", async (_label, readback) => {
  api.postPurchase.mockRejectedValue(new Error("Response lost")); api.checkPurchaseSavedStatus.mockResolvedValue(readback);
  await openRecoveryReview(); await click(button("Confirm and post purchase"));
  await click(button("Check saved status"));
  expect(container.textContent).toContain("Saved document status was not confirmed");
  expect(container.textContent).not.toContain("Your purchase was saved and confirmed.");
  expect(button("Retry same purchase posting")).toBeDefined();
  expect(api.postPurchase).toHaveBeenCalledTimes(1);
});

test("a pending saved-status read blocks retry and a failed read releases only the check", async () => {
  let rejectRead;
  api.postPurchase.mockRejectedValue(new Error("Response lost"));
  api.checkPurchaseSavedStatus.mockImplementation(() => new Promise((_resolve, reject) => { rejectRead = reject; }));
  await openRecoveryReview(); await click(button("Confirm and post purchase"));
  await click(button("Check saved status"));
  expect(button("Retry same purchase posting").disabled).toBe(true);
  expect(button("Checking saved status…").disabled).toBe(true);
  await click(button("Retry same purchase posting")); expect(api.postPurchase).toHaveBeenCalledTimes(1);
  await act(async () => rejectRead(new Error("Read interrupted")));
  expect(button("Check saved status").disabled).toBe(false);
  expect(button("Retry same purchase posting").disabled).toBe(false);
  expect(container.querySelector("fieldset").disabled).toBe(true);
});

test("a saved-status timeout releases the check while retaining the exact original retry", async () => {
  jest.useFakeTimers();
  try {
    api.postPurchase.mockRejectedValue(new Error("Response lost"));
    api.checkPurchaseSavedStatus.mockImplementation(() => readStateWithDeadline(() => new Promise(() => {}), "Saved status timed out"));
    await openRecoveryReview(); await click(button("Confirm and post purchase")); await click(button("Check saved status"));
    await act(async () => jest.advanceTimersByTime(STATE_READ_TIMEOUT_MS));
    expect(container.textContent).toContain("Saved status could not be confirmed: Saved status timed out");
    expect(button("Check saved status").disabled).toBe(false);
    expect(container.querySelector("fieldset").disabled).toBe(true);
    await click(button("Retry same purchase posting"));
    expect(api.postPurchase.mock.calls[1]).toEqual(api.postPurchase.mock.calls[0]);
  } finally { jest.useRealTimers(); }
});

test.each([
  ["wrong document", { batchId: "batch-1", document: { ...savedPurchase, id: "other-document" } }],
  ["wrong batch", { batchId: "other-batch", document: savedPurchase }],
  ["missing batch identity", { batchId: "batch-1", document: { ...savedPurchase, header: doc.header } }],
  ["different request", { batchId: "batch-1", document: { ...savedPurchase, header: { ...savedPurchase.header, posted_request_key: "other-key" } } }],
])("a posting acknowledgement with %s cannot announce success", async (_label, result) => {
  api.postPurchase.mockResolvedValue(result);
  await openRecoveryReview(); await click(button("Confirm and post purchase"));
  expect(container.textContent).toContain("Saved outcome was not confirmed");
  expect(container.textContent).not.toContain("Your purchase was saved and confirmed.");
  expect(container.querySelector("fieldset").disabled).toBe(true);
});

test("a matching posting receipt confirms success even if history refresh fails", async () => {
  api.postPurchase.mockResolvedValue({ batchId: "batch-1", document: savedPurchase });
  await openRecoveryReview(); api.purchaseHistory.mockRejectedValue(new Error("Read interrupted"));
  await click(button("Confirm and post purchase"));
  expect(container.textContent).toContain("Your purchase was saved and confirmed.");
  expect(container.textContent).toContain("Saved purchase history refresh failed");
  expect(button("Retry same purchase posting")).toBeUndefined();
});

test("reopening after remount reads a saved purchase without offering another post", async () => {
  api.postPurchase.mockRejectedValue(new Error("Response lost"));
  await openRecoveryReview(); await click(button("Confirm and post purchase"));
  await act(async () => root.render(<div>Another screen</div>));
  api.purchaseFile.mockResolvedValue({ ...retainedFile, documents: [savedPurchase] });
  await act(async () => root.render(<PurchaseImportsTab actorId="test-owner" key="berts" restaurantId="berts" restaurantName="Test" />));
  await click(button("TEST-ONLY-recovery.csv · 2026-10-11"));
  expect(container.textContent).toContain("pfg · TEST-1 · posted");
  expect(button("Confirm and post purchase")).toBeUndefined();
  expect(button("Retry same purchase posting")).toBeUndefined();
  expect(api.postPurchase).toHaveBeenCalledTimes(1);
});

test("a late saved-status read cannot populate a different location", async () => {
  let resolveRead;
  api.postPurchase.mockRejectedValue(new Error("Response lost"));
  api.checkPurchaseSavedStatus.mockImplementation(() => new Promise(resolve => { resolveRead = resolve; }));
  await openRecoveryReview(); await click(button("Confirm and post purchase")); await click(button("Check saved status"));
  api.purchaseFiles.mockResolvedValue([]);
  await act(async () => root.render(<PurchaseImportsTab actorId="test-owner" key="rudds" restaurantId="rudds" restaurantName="Other test location" />));
  await act(async () => resolveRead(savedPurchase));
  expect(container.textContent).toContain("Invoice Master · Other test location");
  expect(container.textContent).not.toContain("Your purchase was saved and confirmed.");
  expect(container.textContent).not.toContain("TEST-1");
  expect(api.postPurchase).toHaveBeenCalledTimes(1);
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
  await act(async () => root.render(<PurchaseImportsTab actorId="test-owner" restaurantId="berts" restaurantName="Test" />));
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
  await act(async () => root.render(<PurchaseImportsTab actorId="test-owner" restaurantId="berts" restaurantName="Test" />));
  await selectValue("Source upload type", "source");
  const picker = container.querySelector('[aria-label="Invoice file"]'), source = new File(["Invented source"], "synthetic.pdf");
  Object.defineProperty(picker, "files", { value: [source], configurable: true });
  await act(async () => picker.dispatchEvent(new Event("change", { bubbles: true })));
  await click(button("Capture / retry file"));
  expect(api.capturePurchaseSource).toHaveBeenCalledWith("berts", source, "00000000-0000-4000-8000-000000000001");
  expect(api.capturePurchase).not.toHaveBeenCalled(); expect(api.postPurchase).not.toHaveBeenCalled();
});

async function remountSubmittedReview(actorId = "test-owner", restaurantId = "berts") {
  await act(async () => root.render(<div>Signed out</div>));
  await act(async () => root.render(<PurchaseImportsTab key={`${actorId}:${restaurantId}`} actorId={actorId} restaurantId={restaurantId} restaurantName="TEST ONLY resumed" />));
}

test("a submitted review is retained before the first network request and restores its exact retry after reload", async () => {
  api.postPurchase.mockImplementation(async (_store, id, body, key) => {
    const retained = pendingPurchaseJournal("test-owner", "berts").list()[0];
    expect(retained.versionId).toBe(id); expect(retained.key).toBe(key); expect(JSON.stringify(retained.body)).toBe(JSON.stringify(body));
    throw new Error("Response lost");
  });
  api.checkPurchaseSavedStatus.mockResolvedValue(doc);
  await openRecoveryReview(); await click(button("Confirm and post purchase")); const original = api.postPurchase.mock.calls[0];
  await remountSubmittedReview(); expect(api.postPurchase).toHaveBeenCalledTimes(1);
  expect(button("Restore submitted review: TEST-1")).toBeDefined();
  await click(button("Restore submitted review: TEST-1"));
  expect(container.querySelector('[aria-label="Received date"]').value).toBe("2026-10-11");
  expect(container.querySelector('[aria-label="Note 1"]').value).toBe("TEST ONLY retained reviewed quantity");
  expect(container.querySelector("fieldset").disabled).toBe(true);
  expect(api.postPurchase).toHaveBeenCalledTimes(1);
  await click(button("Retry same purchase posting")); expect(api.postPurchase.mock.calls[1]).toEqual(original);
});

test.each(["saved", "corrected"])("reauthentication and remount recognize an own %s receipt without another post", async kind => {
  api.postPurchase.mockRejectedValue(new Error("Response lost"));
  api.checkPurchaseSavedStatus.mockResolvedValue(kind === "saved" ? savedPurchase : correctedPurchase(true));
  await openRecoveryReview(); await click(button("Confirm and post purchase"));
  await remountSubmittedReview(); await click(button("Restore submitted review: TEST-1"));
  expect(api.postPurchase).toHaveBeenCalledTimes(1);
  expect(button("Retry same purchase posting")).toBeUndefined();
  expect(button("Confirm and post purchase")).toBeUndefined();
  expect(pendingPurchaseJournal("test-owner", "berts").list()).toEqual([]);
  expect(container.textContent).toContain(kind === "saved" ? "Your purchase was saved and confirmed" : "Your original purchase was saved and has since been corrected");
});

test.each(["held", "other request"])("a restored %s retains the exact original review and prevents another initial post", async kind => {
  api.postPurchase.mockRejectedValue(new Error("Response lost"));
  api.checkPurchaseSavedStatus.mockResolvedValue(kind === "held" ? { ...doc, status: "held", errors: ["Newer source needs review"] }
    : { ...savedPurchase, header: { ...savedPurchase.header, posted_request_key: "different-request" } });
  await openRecoveryReview(); await click(button("Confirm and post purchase")); const original = pendingPurchaseJournal("test-owner", "berts").list();
  await remountSubmittedReview(); await click(button("Restore submitted review: TEST-1"));
  expect(button("Retry same purchase posting").disabled).toBe(true);
  expect(container.querySelector('[aria-label="Note 1"]').value).toBe("TEST ONLY retained reviewed quantity");
  expect(pendingPurchaseJournal("test-owner", "berts").list()).toEqual(original); expect(api.postPurchase).toHaveBeenCalledTimes(1);
});

test("a failed fresh read after restoration keeps retry blocked until a successful check", async () => {
  api.postPurchase.mockRejectedValue(new Error("Response lost"));
  api.checkPurchaseSavedStatus.mockRejectedValueOnce({ response: { status: 401, data: { detail: "Authentication required" } } }).mockResolvedValueOnce(doc);
  await openRecoveryReview(); await click(button("Confirm and post purchase")); const original = api.postPurchase.mock.calls[0];
  await remountSubmittedReview(); await click(button("Restore submitted review: TEST-1"));
  expect(button("Retry same purchase posting").disabled).toBe(true); expect(container.querySelector("fieldset").disabled).toBe(true);
  expect(container.textContent).toContain("Authentication required"); expect(pendingPurchaseJournal("test-owner", "berts").list()).toHaveLength(1);
  await click(button("Check saved status")); expect(button("Retry same purchase posting").disabled).toBe(false);
  await click(button("Retry same purchase posting")); expect(api.postPurchase.mock.calls[1]).toEqual(original);
});

test("another signed-in user cannot restore or see the prior user's submitted notes", async () => {
  api.postPurchase.mockRejectedValue(new Error("Response lost"));
  await openRecoveryReview(); await click(button("Confirm and post purchase")); await remountSubmittedReview("other-user");
  expect(button("Restore submitted review: TEST-1")).toBeUndefined(); expect(container.textContent).not.toContain("retained reviewed quantity");
  expect(pendingPurchaseJournal("test-owner", "berts").list()).toHaveLength(1); expect(api.postPurchase).toHaveBeenCalledTimes(1);
});

test("a late restored-status read cannot resolve or expose a different user's workspace", async () => {
  let resolveRead; api.postPurchase.mockRejectedValue(new Error("Response lost"));
  api.checkPurchaseSavedStatus.mockImplementation(() => new Promise(resolve => { resolveRead = resolve; }));
  await openRecoveryReview(); await click(button("Confirm and post purchase")); await remountSubmittedReview();
  await click(button("Restore submitted review: TEST-1"));
  await act(async () => root.render(<PurchaseImportsTab actorId="other-user" restaurantId="berts" restaurantName="Other user" />));
  await act(async () => resolveRead({ ...doc, status: "held", errors: ["Prior user's hold"] }));
  expect(container.textContent).not.toContain("Prior user's hold"); expect(container.textContent).not.toContain("retained reviewed quantity");
  expect(button("Restore submitted review: TEST-1")).toBeUndefined(); expect(api.postPurchase).toHaveBeenCalledTimes(1);
});

test("a storage write failure blocks the first posting while retaining the in-memory retry key", async () => {
  api.postPurchase.mockRejectedValue(new Error("Response lost")); await openRecoveryReview();
  const fail = jest.spyOn(Storage.prototype, "setItem").mockImplementation(() => { throw new Error("quota"); });
  try { await click(button("Confirm and post purchase")); expect(api.postPurchase).not.toHaveBeenCalled(); expect(container.textContent).toContain("No new posting will be sent"); }
  finally { fail.mockRestore(); }
  await click(button("Retry same purchase posting")); expect(api.postPurchase).toHaveBeenCalledTimes(1);
  expect(crypto.randomUUID).toHaveBeenCalledTimes(1);
});

test("a corrupted recovery record blocks new posting and is never silently removed", async () => {
  api.postPurchase.mockRejectedValue(new Error("Response lost")); await openRecoveryReview(); await click(button("Confirm and post purchase"));
  const key = [...Array(sessionStorage.length)].map((_, i) => sessionStorage.key(i)).find(k => k.startsWith("jaymax:pending-purchases:"));
  sessionStorage.setItem(key, "broken JSON"); await remountSubmittedReview();
  expect(container.textContent).toContain("No new posting will be sent"); expect(sessionStorage.getItem(key)).toBe("broken JSON");
  expect(api.postPurchase).toHaveBeenCalledTimes(1);
});


test("a late captured-file read cannot populate a replacement user's workspace", async () => {
  let resolveFile;
  api.purchaseCapabilities.mockResolvedValue({ enabled: true }); api.purchaseItems.mockResolvedValue([]);
  api.purchaseFiles.mockResolvedValue([retainedFile]); api.purchaseHistory.mockResolvedValue([]);
  api.purchaseFile.mockImplementation(() => new Promise(resolve => { resolveFile = resolve; }));
  await act(async () => root.render(<PurchaseImportsTab actorId="test-owner" restaurantId="berts" restaurantName="Original user" />));
  await click(button("TEST-ONLY-recovery.csv · 2026-10-11"));
  await act(async () => root.render(<PurchaseImportsTab actorId="other-user" restaurantId="berts" restaurantName="Replacement user" />));
  await act(async () => resolveFile(retainedFile));
  expect(container.querySelector('[aria-label="Invoice TEST-1"]')).toBeNull();
  expect(container.textContent).toContain("Replacement user"); expect(button("TEST-ONLY-recovery.csv · 2026-10-11").disabled).toBe(false);
  expect(api.postPurchase).not.toHaveBeenCalled();
});

test("a confirmed purchase stays confirmed if its local recovery cleanup cannot be saved", async () => {
  let failure;
  api.postPurchase.mockImplementation(async () => {
    failure = jest.spyOn(Storage.prototype, "setItem").mockImplementation(() => { throw new Error("storage denied"); });
    return { batchId: "batch-1", document: savedPurchase };
  });
  try {
    await openRecoveryReview(); await click(button("Confirm and post purchase"));
    expect(container.textContent).toContain("Your purchase was saved and confirmed");
    expect(container.textContent).toContain("retained-review cleanup failed"); expect(button("Retry same purchase posting")).toBeUndefined();
    expect(pendingPurchaseJournal("test-owner", "berts").list()).toHaveLength(1); expect(api.postPurchase).toHaveBeenCalledTimes(1);
  } finally { failure?.mockRestore(); }
});

async function submittedForDiscard() {
  api.postPurchase.mockReset().mockRejectedValue(new Error("Response lost"));
  await openRecoveryReview(); await click(button("Confirm and post purchase"));
  return pendingPurchaseJournal("test-owner", "berts").list();
}
const discardButton = () => button("Discard retained review: TEST-1");
const confirmDiscardButton = () => button("Confirm discard retained review");
async function verifyFreshReview(date = "2026-10-12") {
  await input(container.querySelector('[aria-label="Received date"]'), date);
  await input(container.querySelector('[aria-label="Note 1"]'), "TEST ONLY revised receipt");
  await click(container.querySelector('[aria-label="Confirm USD currency"]'));
  await click(container.querySelector('fieldset input[type="checkbox"]'));
}

test("a held review is discarded only on confirmation and a second read, then a corrected review uses a new key", async () => {
  crypto.randomUUID.mockReturnValueOnce("00000000-0000-4000-8000-000000000001").mockReturnValue("00000000-0000-4000-8000-000000000002");
  const original = await submittedForDiscard();
  api.checkPurchaseSavedStatus.mockReset().mockResolvedValueOnce({ ...doc, status: "held", errors: ["Review source"] }).mockResolvedValue(doc);
  await click(discardButton());
  expect(pendingPurchaseJournal("test-owner", "berts").list()).toEqual(original);
  expect(container.textContent).toContain("does not cancel the earlier request");
  await click(confirmDiscardButton());
  expect(api.checkPurchaseSavedStatus).toHaveBeenCalledTimes(2);
  expect(pendingPurchaseJournal("test-owner", "berts").list()).toEqual([]);
  expect(container.querySelector("fieldset").disabled).toBe(false);
  await verifyFreshReview();
  api.postPurchase.mockRejectedValue(new Error("Synthetic response lost"));
  await click(button("Confirm and post purchase"));
  expect(api.postPurchase).toHaveBeenCalledTimes(2);
  expect(api.postPurchase.mock.calls[1][2].received_date).toBe("2026-10-12");
  expect(api.postPurchase.mock.calls[1][3]).not.toBe(original[0].key);
  expect(api.checkPurchaseSavedStatus).toHaveBeenCalledTimes(3);
});

test("discarding another request's review opens the posted purchase and correction path without a post", async () => {
  await submittedForDiscard();
  const other = { ...savedPurchase, correctionAvailable: true, sourceErrors: [], header: { ...savedPurchase.header, posted_request_key: "other-request" } };
  api.checkPurchaseSavedStatus.mockReset().mockResolvedValue(other);
  await click(discardButton()); await click(confirmDiscardButton());
  expect(pendingPurchaseJournal("test-owner", "berts").list()).toEqual([]);
  expect(button("Confirm and post purchase")).toBeUndefined();
  expect(button("Review correction")).toBeDefined();
  expect(button("Show saved purchase and correction history")).toBeDefined();
  expect(discardButton()).toBeUndefined(); expect(api.postPurchase).toHaveBeenCalledTimes(1);
});

test("discard does not make a still-held invoice postable", async () => {
  await submittedForDiscard();
  api.checkPurchaseSavedStatus.mockReset().mockResolvedValue({ ...doc, status: "held", errors: ["Review latest source"] });
  await click(discardButton()); await click(confirmDiscardButton());
  expect(pendingPurchaseJournal("test-owner", "berts").list()).toEqual([]);
  expect(button("Confirm and post purchase").disabled).toBe(true);
  expect(container.textContent).toContain("Review latest source");
  expect(api.postPurchase).toHaveBeenCalledTimes(1);
});

test("discarding a superseded held version opens the newer source version for an explicit review", async () => {
  crypto.randomUUID.mockReturnValueOnce("00000000-0000-4000-8000-000000000001").mockReturnValue("00000000-0000-4000-8000-000000000002");
  await submittedForDiscard();
  const currentSource = { documentId: "identity-1", versionId: "latest-version", fileId: "latest-file", revision: 2 };
  const latest = { ...doc, id: "latest-version", header: { ...doc.header, revision: 2 }, currentSource,
    lines: [{ ...doc.lines[0], id: "latest-line", vendor_sku_snapshot: "TEST-R2" }] };
  const superseded = { ...doc, currentSource, status: "held", errors: ["A newer source version exists"] };
  // The original captured file still contains only R1, as it did in the live test.
  api.purchaseFile.mockImplementation(async (_store, fileId) => fileId === "latest-file"
    ? { ...retainedFile, id: "latest-file", documents: [latest] } : { ...retainedFile, documents: [superseded] });
  api.checkPurchaseSavedStatus.mockReset()
    .mockResolvedValueOnce(superseded)
    .mockResolvedValueOnce(superseded)
    .mockResolvedValue(latest);
  await click(discardButton()); await click(confirmDiscardButton());
  expect(api.purchaseFile).toHaveBeenLastCalledWith("berts", "latest-file");
  expect(pendingPurchaseJournal("test-owner", "berts").list()).toEqual([]);
  expect(container.textContent).toContain("TEST-R2");
  expect(api.postPurchase).toHaveBeenCalledTimes(1);
  expect(container.querySelector("fieldset").disabled).toBe(false);
  await verifyFreshReview(); await click(button("Confirm and post purchase"));
  expect(api.postPurchase).toHaveBeenCalledTimes(2);
  expect(api.postPurchase.mock.calls[1][1]).toBe("latest-version");
  expect(api.postPurchase.mock.calls[1][2].lines[0].line_id).toBe("latest-line");
  expect(api.postPurchase.mock.calls[1][3]).toBe("00000000-0000-4000-8000-000000000002");
});

test.each([
  undefined,
  { ...doc.currentSource, documentId: "foreign-identity" },
  { ...doc.currentSource, fileId: null },
  { ...doc.currentSource, versionId: "" },
  { ...doc.currentSource, revision: "1" },
  { ...doc.currentSource, versionId: "another-version", revision: 1 },
  { ...doc.currentSource, revision: 2 },
])("an absent or malformed current-source pointer preserves the exact retained review", async currentSource => {
  const original = await submittedForDiscard();
  api.checkPurchaseSavedStatus.mockReset().mockResolvedValue({ ...doc, currentSource });
  await click(discardButton());
  expect(confirmDiscardButton()).toBeUndefined();
  expect(container.textContent).toContain("Current source was not confirmed");
  expect(pendingPurchaseJournal("test-owner", "berts").list()).toEqual(original);
  expect(api.postPurchase).toHaveBeenCalledTimes(1);
});

test.each(["wrong-file", "wrong-version", "wrong-identity", "wrong-revision", "duplicate", "newer-pointer", "fetch-failure", "final-pointer"])(
  "a %s current-source reopening failure preserves the original command", async failure => {
    const original = await submittedForDiscard();
    const currentSource = { documentId: "identity-1", versionId: "latest-version", fileId: "latest-file", revision: 2 };
    const superseded = { ...doc, currentSource, status: "held", errors: ["A newer source version exists"] };
    const latest = { ...doc, id: "latest-version", currentSource, header: { ...doc.header, revision: 2 } };
    const later = { ...currentSource, fileId: "revision-3-file", versionId: "revision-3", revision: 3 };
    const returned = { ...latest,
      ...(failure === "wrong-version" ? { id: "foreign-version" } : {}),
      ...(failure === "wrong-identity" ? { header: { ...latest.header, document_id: "foreign-identity" } } : {}),
      ...(failure === "wrong-revision" ? { header: { ...latest.header, revision: 1 } } : {}),
      ...(failure === "newer-pointer" ? { currentSource: later } : {}) };
    api.checkPurchaseSavedStatus.mockReset().mockResolvedValueOnce(superseded)
      .mockResolvedValue(failure === "final-pointer" ? { ...superseded, currentSource: later } : superseded);
    await click(discardButton());
    api.purchaseFile.mockReset();
    if (failure === "fetch-failure") api.purchaseFile.mockRejectedValue(new Error("Latest source unavailable"));
    else api.purchaseFile.mockResolvedValue({ ...retainedFile, id: failure === "wrong-file" ? "file-1" : "latest-file",
      documents: failure === "duplicate" ? [returned, returned] : [returned] });
    await click(confirmDiscardButton());
    expect(pendingPurchaseJournal("test-owner", "berts").list()).toEqual(original);
    expect(confirmDiscardButton()).toBeDefined();
    expect(api.postPurchase).toHaveBeenCalledTimes(1);
  });

test("discard leaves another submitted invoice in the same source frozen with its exact command", async () => {
  const original = await submittedForDiscard();
  const other = { ...doc, id: "other-version", header: { ...doc.header, document_id: "other-identity", document_number: "TEST-2" } };
  const record = pendingPurchaseRecord(retainedFile, other, original[0].body, original[0].key);
  pendingPurchaseJournal("test-owner", "berts").save(record);
  api.purchaseFile.mockResolvedValue({ ...retainedFile, documents: [doc, other] });
  api.checkPurchaseSavedStatus.mockReset().mockResolvedValue(doc);
  await click(discardButton()); await click(confirmDiscardButton());
  expect(pendingPurchaseJournal("test-owner", "berts").list()).toEqual([record]);
  expect(container.querySelector('[aria-label="Invoice TEST-2"] fieldset').disabled).toBe(true);
  expect(container.querySelector('[aria-label="Invoice TEST-2"] [aria-label="Note 1"]').value).toBe(original[0].body.lines[0].note);
  expect(api.postPurchase).toHaveBeenCalledTimes(1);
});

test.each(["saved", "corrected"])("discard refuses an own %s outcome in the initial fresh read", async kind => {
  const original = await submittedForDiscard();
  api.checkPurchaseSavedStatus.mockReset().mockResolvedValue(kind === "saved" ? savedPurchase : correctedPurchase());
  await click(discardButton());
  expect(confirmDiscardButton()).toBeUndefined();
  expect(container.textContent).toContain("review was not discarded");
  expect(pendingPurchaseJournal("test-owner", "berts").list()).toEqual(original);
  expect(api.postPurchase).toHaveBeenCalledTimes(1);
});

test.each(["saved", "corrected"])("an own %s outcome arriving during confirmation refuses discard", async kind => {
  const original = await submittedForDiscard();
  api.checkPurchaseSavedStatus.mockReset().mockResolvedValueOnce(doc).mockResolvedValue(kind === "saved" ? savedPurchase : correctedPurchase());
  await click(discardButton()); await click(confirmDiscardButton());
  expect(container.textContent).toContain("review was not discarded");
  expect(pendingPurchaseJournal("test-owner", "berts").list()).toEqual(original);
  expect(api.postPurchase).toHaveBeenCalledTimes(1);
});

test("cancelling discard keeps the exact retained body and key and performs no second read", async () => {
  const original = await submittedForDiscard();
  api.checkPurchaseSavedStatus.mockReset().mockResolvedValue(doc);
  await click(discardButton()); await click(button("Keep retained review"));
  expect(confirmDiscardButton()).toBeUndefined();
  expect(pendingPurchaseJournal("test-owner", "berts").list()).toEqual(original);
  expect(api.checkPurchaseSavedStatus).toHaveBeenCalledTimes(1);
});

test.each(["initial", "confirmation"])("failed %s discard read preserves recovery without any post", async phase => {
  const original = await submittedForDiscard();
  api.checkPurchaseSavedStatus.mockReset();
  if (phase === "confirmation") api.checkPurchaseSavedStatus.mockResolvedValueOnce(doc);
  api.checkPurchaseSavedStatus.mockRejectedValue(new Error("Synthetic timeout or expired session"));
  await click(discardButton());
  if (phase === "confirmation") await click(confirmDiscardButton());
  expect(pendingPurchaseJournal("test-owner", "berts").list()).toEqual(original);
  expect(container.textContent).toContain("Synthetic timeout or expired session");
  expect(api.postPurchase).toHaveBeenCalledTimes(1);
});

test.each([
  { ...doc, status: "unknown" },
  { ...doc, header: { ...doc.header, document_id: "foreign-invoice" } },
  { ...doc, errors: ["Contradictory status"] },
])("malformed or foreign discard status is refused", async result => {
  const original = await submittedForDiscard();
  api.checkPurchaseSavedStatus.mockReset().mockResolvedValue(result);
  await click(discardButton());
  expect(confirmDiscardButton()).toBeUndefined();
  expect(pendingPurchaseJournal("test-owner", "berts").list()).toEqual(original);
});

test("a failed source reopening does not discard its retained review", async () => {
  const original = await submittedForDiscard();
  api.checkPurchaseSavedStatus.mockReset().mockResolvedValue(doc);
  await click(discardButton()); api.purchaseFile.mockRejectedValue(new Error("Source reopening failed"));
  await click(confirmDiscardButton());
  expect(pendingPurchaseJournal("test-owner", "berts").list()).toEqual(original);
  expect(api.checkPurchaseSavedStatus).toHaveBeenCalledTimes(1);
  expect(container.textContent).toContain("Source reopening failed");
});

test("failed discard storage write preserves the review and confirmation", async () => {
  const original = await submittedForDiscard();
  api.checkPurchaseSavedStatus.mockReset().mockResolvedValue(doc);
  await click(discardButton());
  const fail = jest.spyOn(Storage.prototype, "setItem").mockImplementation(() => { throw new Error("quota"); });
  try {
    await click(confirmDiscardButton());
    expect(pendingPurchaseJournal("test-owner", "berts").list()).toEqual(original);
    expect(confirmDiscardButton()).toBeDefined(); expect(api.postPurchase).toHaveBeenCalledTimes(1);
  } finally { fail.mockRestore(); }
});

test("a late confirmation read cannot discard or populate another user's workspace", async () => {
  const original = await submittedForDiscard(); let finish;
  api.checkPurchaseSavedStatus.mockReset().mockResolvedValueOnce(doc).mockImplementation(() => new Promise(resolve => { finish = resolve; }));
  await click(discardButton()); await click(confirmDiscardButton());
  await act(async () => root.render(<PurchaseImportsTab actorId="other-user" restaurantId="berts" restaurantName="Other user" />));
  await act(async () => finish(doc));
  expect(pendingPurchaseJournal("test-owner", "berts").list()).toEqual(original);
  expect(confirmDiscardButton()).toBeUndefined(); expect(container.querySelector('[aria-label="Invoice TEST-1"]')).toBeNull();
});

test("an original commit after discard but before revised posting is recognized without a new post", async () => {
  await submittedForDiscard();
  api.checkPurchaseSavedStatus.mockReset().mockResolvedValueOnce(doc).mockResolvedValueOnce(doc).mockResolvedValue(savedPurchase);
  await click(discardButton()); await click(confirmDiscardButton()); await verifyFreshReview();
  await click(button("Confirm and post purchase"));
  expect(api.postPurchase).toHaveBeenCalledTimes(1);
  expect(button("Confirm and post purchase")).toBeUndefined();
  expect(container.textContent).toContain("no new posting was sent");
  expect(pendingPurchaseJournal("test-owner", "berts").list()).toEqual([]);
});

test("an original commit racing the revised post produces a competing outcome, never revised success or another resend", async () => {
  crypto.randomUUID.mockReturnValueOnce("00000000-0000-4000-8000-000000000001").mockReturnValue("00000000-0000-4000-8000-000000000002");
  await submittedForDiscard();
  api.checkPurchaseSavedStatus.mockReset().mockResolvedValueOnce(doc).mockResolvedValueOnce(doc).mockResolvedValueOnce(doc).mockResolvedValue(savedPurchase);
  await click(discardButton()); await click(confirmDiscardButton()); await verifyFreshReview();
  api.postPurchase.mockRejectedValue({ response: { status: 409, data: { detail: "This invoice is already posted" } } });
  await click(button("Confirm and post purchase"));
  expect(api.postPurchase).toHaveBeenCalledTimes(2);
  expect(api.checkPurchaseSavedStatus).toHaveBeenCalledTimes(4);
  expect(button("Retry same purchase posting").disabled).toBe(true);
  expect(container.textContent).toContain("posted by a different request");
  expect(container.textContent).not.toContain("Your purchase was saved and confirmed");
  expect(pendingPurchaseJournal("test-owner", "berts").list()[0].key).toBe("00000000-0000-4000-8000-000000000002");
});

test("a full journal shows its 32-review limit and keeps all earlier reviews without sending", async () => {
  const body = { confirmed_currency: "USD", received_date: "2026-10-12", lines: [{ line_id: "line-1", classification: "food", movement_kind: "receipt", item_code: null, base_unit: null, received_quantity: "2", received_unit: null, base_units_per_received_unit: null, movement_date: null, original_line_id: null, verified: true, note: "TEST ONLY capacity fixture" }] };
  const journal = pendingPurchaseJournal("test-owner", "berts");
  for (let n = 0; n < 32; n++) journal.save(pendingPurchaseRecord(retainedFile, { ...doc, id: `version-${n}` }, body, crypto.randomUUID()));
  api.postPurchase.mockReset();
  await openRecoveryReview(); await click(button("Confirm and post purchase"));
  expect(container.textContent).toContain("32 unresolved retained reviews");
  expect(journal.list()).toHaveLength(32); expect(api.postPurchase).not.toHaveBeenCalled();
});

test("a manual-captured document posts through the journal and restores its exact reviewed command", async () => {
  api.purchaseCapabilities.mockResolvedValue({ enabled: true, manualReady: true }); api.purchaseItems.mockResolvedValue([]);
  api.purchaseFiles.mockResolvedValue([]); api.purchaseHistory.mockResolvedValue([]);
  api.purchaseVendors.mockResolvedValue([{ id: "pfg", name: "Invented supplier" }]);
  api.captureManualPurchase.mockImplementation(async (_store, body) => ({
    id: "manual-file", original_filename: "manual-source-fictional.json", captureStatus: "captured",
    byte_count: 900, source_record_count: 1, source_sha256: "fictional", documents: [doc], manualRecord: body,
  }));
  api.postPurchase.mockReset().mockRejectedValue(new Error("Response lost"));
  api.checkPurchaseSavedStatus.mockReset().mockResolvedValue(doc);
  await act(async () => root.render(<PurchaseImportsTab actorId="test-owner" restaurantId="berts" restaurantName="Test" />));
  await selectValue("Manual supplier", "pfg");
  await input(container.querySelector('[aria-label="Invoice / receipt number"]'), "TEST-1");
  const note = container.querySelector('[aria-label="Manual source evidence"]');
  await act(async () => { Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, "value").set.call(note, "TEST ONLY original source evidence"); note.dispatchEvent(new Event("input", { bubbles: true })); });
  await click(container.querySelector('[aria-label="Confirm manual source details"]')); await click(button("Retain manual source for review"));
  await verifyFreshReview(); await click(button("Confirm and post purchase"));
  const original = api.postPurchase.mock.calls[0];
  expect(pendingPurchaseJournal("test-owner", "berts").list()[0].source.original_filename).toBe("manual-source-fictional.json");
  await remountSubmittedReview(); await click(button("Restore submitted review: TEST-1")); await click(button("Retry same purchase posting"));
  expect(api.postPurchase.mock.calls[1]).toEqual(original);
  expect(api.captureManualPurchase).toHaveBeenCalledTimes(1);
});
