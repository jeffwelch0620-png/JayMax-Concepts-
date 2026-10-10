import React, { act } from "react";
import { createRoot } from "react-dom/client";
import { InventoryUnitSetup } from "./InventoryUnitSetup";
import { NativeOrderReceiving } from "./NativeOrderReceiving";
import { PurchaseOrdersTab } from "./PurchaseOrdersTab";
import * as api from "../lib/api";

jest.mock("../lib/api", () => ({ nativePurchasesEnabled: true, nativeUnitSetup: jest.fn(), saveNativeUnitProfile: jest.fn(),
  nativeOrderReceiptSetup: jest.fn(), purchaseFileDocument: jest.fn(), previewNativeOrderReceipt: jest.fn(), linkNativeOrderReceipt: jest.fn(),
  listOrders: jest.fn(), listVendorContacts: jest.fn(), receiveOrder: jest.fn() }));
let container, root;
const unitData = { items: [{ code: "food", name: "Invented food", native_base_unit: "lb", countSource: { unit: "case", hash: "source-hash", snapshot: { item: { pack_count: "4", unit_qty: "5", unit_uom: "lb" } } }, supplierProducts: [] }], profiles: [], baseUnits: ["lb"] };
const setup = { order: { status: "sent" }, lines: [{ id: "order-line", item_code: "food", name: "Invented food", qty: "1", unit: "case", position: 0 }], history: [], invoices: [{ document_version_id: "invoice", document_number: "TEST-1" }] };
const doc = { lines: [{ id: "source-line", description_snapshot: "Invented food" }], currentMappings: [{ line_id: "source-line", classification: "food", movement_kind: "receipt", item_code: "food", base_quantity: "40", base_unit: "lb", inventory_record_date: "2026-10-04" }] };
const plan = { status: "ready", planHash: "plan-hash", blocks: [], receiptLines: [], comparison: [{ po_line_id: "order-line", name: "Invented food", orderedBaseQuantity: "20", receivedBase: "40", differenceBase: "20", baseUnit: "lb" }], review: { document_version_id: "invoice", lines: [], complete_order: false, variances_reviewed: true, note: "Checked" } };
beforeEach(() => {
  global.IS_REACT_ACT_ENVIRONMENT = true; Object.defineProperty(global, "crypto", { configurable: true, value: { randomUUID: () => "frozen-key" } });
  container = document.createElement("div"); document.body.appendChild(container); root = createRoot(container); jest.clearAllMocks();
  api.nativeUnitSetup.mockResolvedValue(unitData); api.nativeOrderReceiptSetup.mockResolvedValue(setup); api.purchaseFileDocument.mockResolvedValue(doc); api.previewNativeOrderReceipt.mockResolvedValue(plan);
});
afterEach(async () => { await act(async () => root.unmount()); container.remove(); });
const button = text => [...container.querySelectorAll("button")].find(b => b.textContent === text);
async function click(el) { await act(async () => el.click()); }
async function input(label, value) {
  const el = container.querySelector(`[aria-label="${label}"]`), proto = el.tagName === "SELECT" ? HTMLSelectElement.prototype : HTMLInputElement.prototype;
  await act(async () => { Object.getOwnPropertyDescriptor(proto, "value").set.call(el, value); el.dispatchEvent(new Event(el.tagName === "SELECT" ? "change" : "input", { bubbles: true })); });
}
async function receiveForm() {
  await act(async () => root.render(<NativeOrderReceiving restaurantId="berts" orderRef="po_test" />));
  await input("Order received invoice", "invoice"); await input("Match receipt source-line", "order-line"); await input("Order receipt evidence", "Checked receipt");
  await click(container.querySelector('[aria-label="Review received order quantities"]')); await click(button("Preview delivery comparison"));
}

test("unit setup requires an entered physical factor and does not adopt catalog metadata", async () => {
  await act(async () => root.render(<InventoryUnitSetup restaurantId="berts" />)); await input("Unit setup item", "food");
  expect(container.querySelector('[aria-label="Verified physical conversion"]').value).toBe("");
  expect(api.saveNativeUnitProfile).not.toHaveBeenCalled();
});
test("unit review interruption retries unchanged decimal text and source fingerprint", async () => {
  api.saveNativeUnitProfile.mockRejectedValueOnce(new Error("Connection lost")).mockResolvedValueOnce({ profile: { id: "profile", item_code: "food", base_unit: "lb" } });
  await act(async () => root.render(<InventoryUnitSetup restaurantId="berts" />)); await input("Unit setup item", "food");
  await input("Verified physical conversion", "20.000000000001"); await input("Unit conversion evidence", "Weighed case");
  await click(container.querySelector('[aria-label="Confirm physical conversion"]')); await click(button("Save verified unit conversion"));
  expect(container.textContent).toContain("Connection lost"); await click(button("Retry same unit review"));
  expect(api.saveNativeUnitProfile.mock.calls[1]).toEqual(api.saveNativeUnitProfile.mock.calls[0]);
  expect(api.saveNativeUnitProfile.mock.calls[0][1].base_units_per_source_unit).toBe("20.000000000001");
});
test("order comparison shows base-unit variance before linking and never calls stock receiving", async () => {
  await receiveForm(); expect(container.textContent).toContain("ordered 20 lb; received total 40 lb; difference 20");
  expect(api.linkNativeOrderReceipt).not.toHaveBeenCalled(); expect(api.receiveOrder).not.toHaveBeenCalled();
  expect(api.previewNativeOrderReceipt.mock.calls[0][2].complete_order).toBe(false);
});

test("rejected invalid unit input can be corrected without losing safe network retry behavior", async () => {
  api.saveNativeUnitProfile.mockRejectedValue({ response: { status: 422, data: { detail: [{ msg: "Enter a positive decimal conversion" }] } } });
  await act(async () => root.render(<InventoryUnitSetup restaurantId="berts" />)); await input("Unit setup item", "food");
  await input("Verified physical conversion", "invalid"); await input("Unit conversion evidence", "Measured pack");
  await click(container.querySelector('[aria-label="Confirm physical conversion"]')); await click(button("Save verified unit conversion"));
  expect(container.textContent).toContain("Enter a positive decimal conversion");
  expect(container.querySelector('[aria-label="Verified physical conversion"]').disabled).toBe(false);
  expect(container.querySelector('[aria-label="Confirm physical conversion"]').checked).toBe(false);
  expect(button("Save verified unit conversion").disabled).toBe(true);
});
test("interrupted delivery link keeps the exact preview and request key", async () => {
  api.linkNativeOrderReceipt.mockRejectedValueOnce(new Error("Link interrupted")).mockResolvedValueOnce({ receipt: { id: "receipt", reviewed_plan: { planHash: "plan-hash", poRef: "po_test" } } });
  await receiveForm(); await click(button("Confirm invoice-linked delivery"));
  expect(container.textContent).toContain("Link interrupted"); await click(button("Retry same delivery link"));
  expect(api.linkNativeOrderReceipt.mock.calls[1]).toEqual(api.linkNativeOrderReceipt.mock.calls[0]);
  expect(container.textContent).toContain("No second inventory quantity or cost was added.");
});
test("incomplete delivery acknowledgement cannot announce success", async () => {
  api.linkNativeOrderReceipt.mockResolvedValue({ receipt: { id: "unconfirmed" } });
  await receiveForm(); await click(button("Confirm invoice-linked delivery"));
  expect(container.textContent).toContain("Saved delivery link was not confirmed"); expect(container.textContent).not.toContain("Delivery linked to its recorded purchase.");
});

test("confirmed delivery conflict requires a fresh comparison while connection errors keep the retry", async () => {
  api.linkNativeOrderReceipt.mockRejectedValue({ response: { status: 409, data: { detail: "Invoice changed" } } });
  await receiveForm(); await click(button("Confirm invoice-linked delivery"));
  await click(button("Refresh changed delivery review"));
  expect(container.querySelector('[aria-label="Order received invoice"]').disabled).toBe(false);
  expect(container.querySelector('[aria-label="Order received invoice"]').value).toBe("");
  expect(container.querySelector('[aria-label="Delivery comparison"]')).toBeNull();
  expect(api.nativeOrderReceiptSetup).toHaveBeenCalledTimes(2);
});

test("unit source conflict refresh clears the old factor and requires another verification", async () => {
  api.saveNativeUnitProfile.mockRejectedValue({ response: { status: 409, data: { detail: "Pack changed" } } });
  await act(async () => root.render(<InventoryUnitSetup restaurantId="berts" />)); await input("Unit setup item", "food");
  await input("Verified physical conversion", "20"); await input("Unit conversion evidence", "Checked pack");
  await click(container.querySelector('[aria-label="Confirm physical conversion"]')); await click(button("Save verified unit conversion"));
  await click(button("Refresh changed unit setup"));
  expect(container.querySelector('[aria-label="Verified physical conversion"]').value).toBe("");
  expect(container.querySelector('[aria-label="Confirm physical conversion"]').checked).toBe(false);
  expect(button("Save verified unit conversion").disabled).toBe(true);
});
test("held comparisons and stale invoice history remain visible", async () => {
  api.nativeOrderReceiptSetup.mockResolvedValue({ ...setup, history: [{ id: "prior", note: "Earlier delivery", stale: true, reviewed_plan: { comparison: [] } }] });
  api.previewNativeOrderReceipt.mockResolvedValue({ ...plan, status: "held", blocks: ["Reconcile earlier invoice"] });
  await receiveForm(); expect(container.textContent).toContain("Linked invoice changed — reconciliation required");
  expect(button("Confirm invoice-linked delivery").disabled).toBe(true);
});
test("native Purchase Orders screen opens invoice review instead of its old quantity form", async () => {
  api.listOrders.mockResolvedValue([{ id: "po_test", vendor: "Invented supplier", status: "sent", createdBy: "Manager", total: 40, lines: [], history: [] }]); api.listVendorContacts.mockResolvedValue([]);
  await act(async () => root.render(<PurchaseOrdersTab rid="berts" showToast={jest.fn()} />));
  await click(container.querySelector('[data-testid="po-receive-po_test"]'));
  expect(container.querySelector('[aria-label="Native order receiving"]')).not.toBeNull();
  expect(container.querySelector('[data-testid="po-receive-form-po_test"]')).toBeNull(); expect(api.receiveOrder).not.toHaveBeenCalled();
});
