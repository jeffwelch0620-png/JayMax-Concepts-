import React, { act } from "react";
import { createRoot } from "react-dom/client";
import { StaffSheet } from "./StaffSheet";
import { InvoicesTab } from "./InvoicesTab";
import { NativePurchaseHistory } from "./NativePurchaseHistory";
import * as api from "../lib/api";

jest.mock("../lib/api", () => ({ __esModule: true, nativePurchasesEnabled: true, actualInventoryEnabled: true, verifyStaffPin: jest.fn(), staffTaskInbox: jest.fn(), staffCounts: jest.fn(), staffSaveCounts: jest.fn(), purchaseHistory: jest.fn(), staffCountDrafts: jest.fn() }));
jest.mock("../lib/push", () => ({ pushSupported: () => false }));
jest.mock("./PurchaseImportsTab", () => ({ PurchaseImportsTab: ({ restaurantId }) => <p>Native source review for {restaurantId}</p> }));
let container, root;
const fact = (id, kind, quantity, amount) => ({ fact_id: id, line_id: "source-line", mapping_id: id, fact_kind: kind, inventory_record_date: "2026-10-04", item_code: "food", vendor_id: "supplier", document_number: "TEST", description_snapshot: "Invented food", base_quantity: quantity, base_unit: "lb", inventory_cost_amount: amount });
beforeEach(() => {
  global.IS_REACT_ACT_ENVIRONMENT = true; container = document.createElement("div"); document.body.appendChild(container); root = createRoot(container); jest.clearAllMocks();
  api.actualInventoryEnabled = true; api.nativePurchasesEnabled = true;
  api.staffCountDrafts.mockResolvedValue([]);
  api.verifyStaffPin.mockResolvedValue({ ok: true }); api.staffTaskInbox.mockResolvedValue({ tasks: [] }); api.staffCounts.mockResolvedValue({ items: [] }); api.purchaseHistory.mockResolvedValue([]);
});
afterEach(async () => { await act(async () => root.unmount()); container.remove(); });
const render = element => act(async () => root.render(element));
const click = element => act(async () => element.click());
const button = text => [...container.querySelectorAll("button")].find(b => b.textContent === text);
async function staff() {
  await render(<StaffSheet />); await click(container.querySelector('[data-testid="staff-store-berts"]')); await click(container.querySelector('[data-testid="staff-unlock-button"]'));
}
test("native direct invoice mounts route to source review without legacy save props", async () => {
  const save = jest.fn(); await render(<InvoicesTab rid="papa_leonis" persistPurchases={save} />);
  expect(container.textContent).toContain("Native source review for papa_leonis"); expect(save).not.toHaveBeenCalled();
});
test("missing restaurant cannot expose a legacy invoice form", async () => {
  await render(<InvoicesTab />); expect(container.querySelector('[role="alert"]').textContent).toContain("Invoice Master"); expect(container.querySelector('input[type="file"]')).toBeNull();
});
test("staff handoff preserves manager source review and suppresses old actual-count requests", async () => {
  await staff(); expect(container.textContent).toContain("Give all supplier invoices, receipts and credits to your manager");
  await click(container.querySelector('[data-testid="staff-view-counts"]'));
  expect(container.textContent).toContain("No open count sheets"); expect(api.staffCountDrafts).toHaveBeenCalledWith("berts", ""); expect(api.staffCounts).not.toHaveBeenCalled(); expect(api.staffSaveCounts).not.toHaveBeenCalled();
});
test("staff counts continue in purchase-only mode", async () => {
  api.actualInventoryEnabled = false; await staff(); await click(container.querySelector('[data-testid="staff-view-counts"]'));
  expect(api.staffCounts).toHaveBeenCalledWith("berts", ""); expect(container.querySelector('[data-testid="staff-actual-count-handoff"]')).toBeNull();
});
test("posted history shows signed correction events and exact amounts without a legacy price calculation", async () => {
  api.purchaseHistory.mockResolvedValue([fact("a", "initial", "40", "40.00"), fact("b", "reversal", "-40", "-40.00"), fact("c", "replacement", "60.000000000001", "55.001")]);
  await render(<NativePurchaseHistory restaurantId="berts" />);
  expect(api.purchaseHistory).toHaveBeenCalledWith("berts"); expect(container.querySelectorAll("tbody tr")).toHaveLength(3);
  expect(container.textContent).toContain("Reversal"); expect(container.textContent).toContain("Replacement"); expect(container.textContent).toContain("60.000000000001 lb"); expect(container.textContent).toContain("55.001");
});
test("failed or malformed native history never falls back to old purchases", async () => {
  api.purchaseHistory.mockRejectedValueOnce(new Error("Offline")).mockResolvedValueOnce({ purchases: [] });
  await render(<NativePurchaseHistory restaurantId="berts" />); expect(container.querySelector('[role="alert"]').textContent).toBe("Offline");
  await click(button("Refresh purchase history")); expect(container.textContent).toContain("was not confirmed"); expect(container.textContent).not.toContain("No purchases have been posted");
});
test("a zero-food no-movement posting can appear without inventing a date or item", async () => {
  api.purchaseHistory.mockResolvedValue([{ ...fact("zero", "initial", "0", "0"), inventory_record_date: null, item_code: null, base_unit: null }]);
  await render(<NativePurchaseHistory restaurantId="berts" />);
  expect(container.querySelector('[role="alert"]')).toBeNull(); expect(container.textContent).toContain("No inventory movement date"); expect(container.textContent).toContain("No inventory item");
});
test("late location response cannot replace another restaurant's ledger", async () => {
  let complete;
  api.purchaseHistory.mockReturnValueOnce(new Promise(resolve => { complete = resolve; })).mockResolvedValueOnce([fact("new", "initial", "2", "3")]);
  await render(<NativePurchaseHistory restaurantId="berts" />); await render(<NativePurchaseHistory restaurantId="rudds" />);
  await act(async () => complete([fact("old", "initial", "999", "999")]));
  expect(container.textContent).toContain("2 lb"); expect(container.textContent).not.toContain("999");
});
