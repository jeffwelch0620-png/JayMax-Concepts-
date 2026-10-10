import React, { act } from "react";
import { createRoot } from "react-dom/client";
import { NativeOrderReconciliation } from "./NativeOrderReconciliation";
import { NativeOrderReceiving } from "./NativeOrderReceiving";
import * as api from "../lib/api";

jest.mock("../lib/api", () => ({ nativeOrderReconciliationSetup: jest.fn(), previewNativeOrderReconciliation: jest.fn(),
  reconcileNativeOrderReceipt: jest.fn(), nativeOrderReceiptSetup: jest.fn(), receiveOrder: jest.fn() }));
let container, root;
const setup = { order: { status: "received" }, receipt: { stale: true, reconciliation_revision: 0, reviewed_plan: { receiptLines: [
  { source_line_id: "old-line", description: "Invented food", base_quantity: "40", base_unit: "lb", receivedDate: "2026-10-04" }] } },
  lines: [{ id: "order-line", name: "Invented food", item_code: "food", qty: "4", unit: "case", position: 0 }],
  document: { id: "version", header: { document_number: "TEST-1" }, lines: [{ id: "line", description_snapshot: "Invented corrected food" }],
    currentMappings: [{ line_id: "line", classification: "food", movement_kind: "receipt", item_code: "food", base_quantity: "60", base_unit: "lb", inventory_record_date: "2026-10-04" }] } };
const plan = { status: "ready", planHash: "review-hash", receiptId: "receipt", poRef: "order", blocks: [], warnings: [], otherStaleReceiptIds: [],
  comparison: [{ po_line_id: "order-line", name: "Invented food", beforeReceivedBase: "40", receivedBase: "60", orderedBaseQuantity: "80", differenceBase: "-20", baseUnit: "lb" }],
  review: { document_version_id: "version", lines: [{ source_line_id: "line", po_line_id: "order-line", verified: true }], variances_reviewed: true, note: "Reviewed" } };
const saved = { reconciliation: { id: "new-review", receipt_id: "receipt", reviewed_plan: { planHash: "review-hash", poRef: "order" } } };
beforeEach(() => {
  global.IS_REACT_ACT_ENVIRONMENT = true; Object.defineProperty(global, "crypto", { configurable: true, value: { randomUUID: () => "review-key" } });
  container = document.createElement("div"); document.body.appendChild(container); root = createRoot(container); jest.clearAllMocks();
  api.nativeOrderReconciliationSetup.mockResolvedValue(setup); api.previewNativeOrderReconciliation.mockResolvedValue(plan); api.reconcileNativeOrderReceipt.mockResolvedValue(saved);
});
afterEach(async () => { await act(async () => root.unmount()); container.remove(); });
const button = text => [...container.querySelectorAll("button")].find(b => b.textContent === text);
async function click(el) { await act(async () => el.click()); }
async function input(label, value) {
  const el = container.querySelector(`[aria-label="${label}"]`), proto = el.tagName === "SELECT" ? HTMLSelectElement.prototype : HTMLInputElement.prototype;
  await act(async () => { Object.getOwnPropertyDescriptor(proto, "value").set.call(el, value); el.dispatchEvent(new Event(el.tagName === "SELECT" ? "change" : "input", { bubbles: true })); });
}
async function form(onSaved = jest.fn()) {
  await act(async () => root.render(<NativeOrderReconciliation restaurantId="berts" orderRef="order" receiptId="receipt" onSaved={onSaved} onClose={jest.fn()} />));
  await input("Reconcile receipt line", "order-line"); await input("Reconciliation evidence", "Reviewed corrected delivery");
  await click(container.querySelector('[aria-label="Review corrected order comparison"]')); await click(button("Preview corrected order comparison"));
}

test("corrected physical quantities require fresh review and preview before confirmation", async () => {
  await act(async () => root.render(<NativeOrderReconciliation restaurantId="berts" orderRef="order" receiptId="receipt" />));
  expect(container.querySelector('[aria-label="Reconcile receipt line"]').value).toBe("");
  expect(container.querySelector('[aria-label="Review corrected order comparison"]').checked).toBe(false);
  expect(button("Preview corrected order comparison").disabled).toBe(true);
  await input("Reconcile receipt line", "order-line"); await input("Reconciliation evidence", "Checked source");
  await click(container.querySelector('[aria-label="Review corrected order comparison"]')); await click(button("Preview corrected order comparison"));
  expect(container.textContent).toContain("previously received 40 lb; corrected total 60 lb; ordered 80 lb; difference -20");
  expect(api.reconcileNativeOrderReceipt).not.toHaveBeenCalled(); expect(api.receiveOrder).not.toHaveBeenCalled();
});

test("interrupted reconciliation retries the exact reviewed body and key", async () => {
  api.reconcileNativeOrderReceipt.mockRejectedValueOnce(new Error("Interrupted response")).mockResolvedValueOnce(saved);
  const onSaved = jest.fn(); await form(onSaved); await click(button("Confirm corrected order comparison"));
  expect(button("Close reconciliation review").disabled).toBe(true);
  await click(button("Retry same reconciliation"));
  expect(api.reconcileNativeOrderReceipt.mock.calls[1]).toEqual(api.reconcileNativeOrderReceipt.mock.calls[0]);
  expect(container.textContent).toContain("Purchase quantities and food cost were not posted again.");
  expect(onSaved).toHaveBeenCalledTimes(1);
});

test("leaving a receipt unselected cannot silently treat it as an extra", async () => {
  await act(async () => root.render(<NativeOrderReconciliation restaurantId="berts" orderRef="order" receiptId="receipt" />));
  await input("Reconciliation evidence", "Reviewed extras"); await click(container.querySelector('[aria-label="Review corrected order comparison"]'));
  expect(button("Preview corrected order comparison").disabled).toBe(true);
  await input("Reconcile receipt line", "extra"); await click(container.querySelector('[aria-label="Review corrected order comparison"]'));
  await click(button("Preview corrected order comparison"));
  expect(api.previewNativeOrderReconciliation.mock.calls[0][3].lines[0].po_line_id).toBeNull();
});

test("incomplete acknowledgement cannot announce reconciliation success", async () => {
  api.reconcileNativeOrderReceipt.mockResolvedValue({ reconciliation: { id: "uncertain" } });
  const onSaved = jest.fn(); await form(onSaved); await click(button("Confirm corrected order comparison"));
  expect(container.textContent).toContain("Saved reconciliation was not confirmed"); expect(onSaved).not.toHaveBeenCalled();
  expect(container.textContent).not.toContain("Order comparison reconciled.");
});

test("confirmed conflict refreshes the corrected source and requires another review", async () => {
  api.reconcileNativeOrderReceipt.mockRejectedValue({ response: { status: 409, data: { detail: "Correction changed" } } });
  await form(); await click(button("Confirm corrected order comparison")); await click(button("Refresh changed reconciliation"));
  expect(container.querySelector('[aria-label="Corrected order comparison"]')).toBeNull();
  expect(container.querySelector('[aria-label="Review corrected order comparison"]').checked).toBe(false);
  expect(container.querySelector('[aria-label="Reconcile receipt line"]').value).toBe("");
  expect(api.nativeOrderReconciliationSetup).toHaveBeenCalledTimes(2);
});

test("a zero-food correction shows removal warning and sends an empty reviewed line list", async () => {
  api.nativeOrderReconciliationSetup.mockResolvedValue({ ...setup, document: { ...setup.document, currentMappings: [] } });
  await act(async () => root.render(<NativeOrderReconciliation restaurantId="berts" orderRef="order" receiptId="receipt" />));
  expect(container.textContent).toContain("removes the previous delivery quantity from this order comparison only");
  await input("Reconciliation evidence", "Food was reclassified"); await click(container.querySelector('[aria-label="Review corrected order comparison"]'));
  await click(button("Preview corrected order comparison")); expect(api.previewNativeOrderReconciliation.mock.calls[0][3].lines).toEqual([]);
});

test("other stale comparisons stay visible and held plans cannot be confirmed", async () => {
  api.previewNativeOrderReconciliation.mockResolvedValue({ ...plan, status: "held", blocks: ["Source changed"], otherStaleReceiptIds: ["other"] });
  await form(); expect(button("Confirm corrected order comparison").disabled).toBe(true);
  expect(container.textContent).toContain("Other linked invoices still need reconciliation");
});

test("completed order exposes reconciliation and retained original/replacement history", async () => {
  api.nativeOrderReceiptSetup.mockResolvedValue({ order: { status: "received" }, lines: [], invoices: [], reconciliationReady: true,
    history: [{ id: "receipt", stale: true, note: "Original delivery", reconciliation_revision: 1,
      reviewed_plan: { comparison: [] }, original_reviewed_plan: { receiptLines: [{ base_quantity: "40", base_unit: "lb" }] },
      reconciliations: [{ id: "prior", revision: 1, note: "Corrected source", reviewed_plan: { receiptLines: [{ base_quantity: "60", base_unit: "lb" }] } }] }] });
  await act(async () => root.render(<NativeOrderReceiving restaurantId="berts" orderRef="order" />));
  expect(container.textContent).toContain("Original review: 40 lb"); expect(container.textContent).toContain("Corrected source");
  await click(button("Reconcile corrected invoice")); expect(container.querySelector('[aria-label="Corrected invoice reconciliation"]')).not.toBeNull();
  expect(container.querySelector('[aria-label="Order received invoice"]')).toBeNull();
});

test("a saved reconciliation remains acknowledged if list refresh fails", async () => {
  await form(jest.fn().mockRejectedValue(new Error("Refresh unavailable"))); await click(button("Confirm corrected order comparison"));
  expect(container.textContent).toContain("Reconciliation saved; order refresh failed");
  expect(container.textContent).toContain("Order comparison reconciled."); expect(button("Retry same reconciliation").disabled).toBe(true);
});
