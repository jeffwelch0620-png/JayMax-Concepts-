import React, { act } from "react";
import { createRoot } from "react-dom/client";
import { NativeInventoryPosition } from "./NativeInventoryPosition";
import { OrderTab } from "./OrderTab";
import { OwnerDashboard } from "./OwnerDashboard";
import { SetupTab } from "./SetupTab";
import * as api from "../lib/api";

jest.mock("../lib/api", () => ({ __esModule: true, nativePurchasesEnabled: true, actualInventoryEnabled: true, nativeOperatingSummary: jest.fn(), createOrder: jest.fn(), currentSession: () => ({ user: { email: "invented@example.invalid" } }), ownerSummary: jest.fn(), ownerPrepSummary: jest.fn(), ownerOrders: jest.fn(), ownerDiscrepancies: jest.fn(), ownerVendorScorecard: jest.fn(), listVendorContacts: jest.fn() }));
jest.mock("recharts", () => {
  const box = ({ children }) => <div>{children}</div>;
  return { BarChart: box, ResponsiveContainer: box, Bar: ({ dataKey }) => <span data-chart-key={dataKey} />, XAxis: () => null, YAxis: () => null, Tooltip: () => null, CartesianGrid: () => null, Legend: () => null };
});
let root, container;
const summary = { basis: "native_received_purchases_and_explicit_counts", items: [{ item_code: "global_food", counted_quantity: "2", counted_unit: "case", base_quantity: "40.000000000001", base_unit: "lb", inventory_value: "75.00" }], liveOnHandAvailable: false, countStatus: "complete", count: { count_date: "2026-10-04", timing: "before_receipts" }, inventoryValue: "75.00", netFoodPurchases30: "40", receivedFrom: "2026-09-06", receivedBefore: "2026-10-06" };
const item = { itemCode: "global_food", controlNumber: "FOOD", name: "Invented food", classification: "raw", orderEnabled: true, countUnit: "case", par: 10, currentStock: 0, vendorSkus: [{ id: "sku", vendor: "Invented supplier", vendorId: "synthetic", purchaseUnit: "case", vendorSku: "001", price: 10, preferred: true }] };
const store = { id: "berts", name: "Invented location", short: "B", accent: "orange", inventoryValue: null, spend30: "40", orderAlerts: null, waste30: 0, avgFoodCost: 35, itemCount: 1, dishCount: 1, prepLow: 0, topCostDishes: [], nativeInventory: { ...summary, countStatus: "count_missing", count: null, inventoryValue: null } };
beforeEach(() => {
  global.IS_REACT_ACT_ENVIRONMENT = true; root = createRoot(container = document.createElement("div")); document.body.appendChild(container); jest.clearAllMocks();
  api.actualInventoryEnabled = true; api.nativePurchasesEnabled = true;
  api.nativeOperatingSummary.mockResolvedValue(summary); api.ownerSummary.mockResolvedValue({ inventoryBasis: summary.basis, stores: [store], totals: { inventoryValue: null, spend30: "40", orderAlerts: null, waste30: 0 } });
  api.ownerPrepSummary.mockResolvedValue({ stores: [] }); api.ownerOrders.mockResolvedValue([]); api.ownerDiscrepancies.mockResolvedValue([]); api.ownerVendorScorecard.mockResolvedValue([]); api.listVendorContacts.mockResolvedValue([]);
});
afterEach(async () => { await act(async () => root.unmount()); container.remove(); });
const render = el => act(async () => root.render(el));
const click = el => act(async () => el.click());
const button = text => [...container.querySelectorAll("button")].find(b => b.textContent === text);
async function input(label, value) {
  const el = container.querySelector(`[aria-label="${label}"]`);
  const proto = el.tagName === "TEXTAREA" ? HTMLTextAreaElement.prototype : el.tagName === "SELECT" ? HTMLSelectElement.prototype : HTMLInputElement.prototype;
  await act(async () => { Object.getOwnPropertyDescriptor(proto, "value").set.call(el, value); el.dispatchEvent(new Event(el.tagName === "SELECT" ? "change" : "input", { bubbles: true })); });
}
async function planned() {
  await render(<OrderTab items={[item]} rid="berts" />);
  await input("Order quantity global_food", "1.5"); await input("Order planning evidence", "Reviewed service needs and physical stock"); await click(container.querySelector('[aria-label="Confirm reviewed order quantities"]'));
}
test("dated counts retain exact physical quantities and explicit values without live stock claims", async () => {
  await render(<NativeInventoryPosition restaurantId="berts" />);
  expect(container.textContent).toContain("40.000000000001 lb"); expect(container.textContent).toContain("75.00 USD"); expect(container.textContent).toContain("Live on-hand is unknown");
});
test("incomplete counts show unknown value and do not display partial count lines", async () => {
  api.nativeOperatingSummary.mockResolvedValue({ ...summary, countStatus: "incomplete", inventoryValue: null });
  await render(<NativeInventoryPosition restaurantId="berts" />);
  expect(container.textContent).toContain("Unavailable"); expect(container.querySelector('tbody')).toBeNull();
});
test("a failed native count read cannot substitute legacy stock or announce an empty count", async () => {
  api.nativeOperatingSummary.mockRejectedValue(new Error("Unavailable database"));
  await render(<NativeInventoryPosition restaurantId="berts" />);
  expect(container.querySelector('[role="alert"]').textContent).toBe("Unavailable database"); expect(container.textContent).not.toContain("No current-scope count");
});
test("a late count response cannot replace the newly selected location", async () => {
  let resolveFirst;
  api.nativeOperatingSummary.mockImplementation(rid => rid === "berts" ? new Promise(resolve => { resolveFirst = resolve; }) : Promise.resolve({ ...summary, inventoryValue: "123.00" }));
  await render(<NativeInventoryPosition restaurantId="berts" />);
  await render(<NativeInventoryPosition restaurantId="rudds" />);
  await act(async () => resolveFirst(summary));
  expect(container.textContent).toContain("123.00 USD"); expect(container.textContent).not.toContain("75.00 USD");
});
test("order planning starts with no quantity even when legacy stock is zero and par is ten", async () => {
  await render(<OrderTab items={[item]} rid="berts" />);
  expect(container.querySelector('[aria-label="Order quantity global_food"]').value).toBe(""); expect(api.createOrder).not.toHaveBeenCalled(); expect(container.textContent).not.toContain("Everything enabled for ordering is at or above par");
});
test("reviewed order quantities use canonical item IDs and selected supplier units", async () => {
  api.createOrder.mockImplementation((rid, body) => Promise.resolve({ ...body, id: "po_saved", restaurantId: rid, status: "draft" }));
  await planned(); await click(button("Create reviewed draft for Invented supplier"));
  expect(api.createOrder.mock.calls[0][1].lines[0]).toMatchObject({ itemCode: "global_food", qty: 1.5, purchaseUnit: "case", vendorSku: "001" });
});
test("an interrupted draft save holds retries until Purchase Orders is checked", async () => {
  api.createOrder.mockRejectedValue(new Error("Connection lost")); await planned(); await click(button("Create reviewed draft for Invented supplier"));
  expect(container.textContent).toContain("Outcome is uncertain"); expect(button("Create reviewed draft for Invented supplier").disabled).toBe(true); expect(api.createOrder).toHaveBeenCalledTimes(1);
});
test("another location's acknowledgement cannot announce a saved draft", async () => {
  const toast = jest.fn(); api.createOrder.mockImplementation((rid, body) => Promise.resolve({ ...body, id: "po_wrong", restaurantId: "rudds", status: "draft" }));
  await render(<OrderTab items={[item]} rid="berts" showToast={toast} />); await input("Order quantity global_food", "1"); await input("Order planning evidence", "Reviewed"); await click(container.querySelector('[aria-label="Confirm reviewed order quantities"]')); await click(button("Create reviewed draft for Invented supplier"));
  expect(container.textContent).toContain("Draft save was not confirmed"); expect(toast).not.toHaveBeenCalled();
});
test("changing supplier units clears quantity and review confirmation", async () => {
  await render(<OrderTab items={[{ ...item, vendorSkus: [...item.vendorSkus, { id: "other", vendor: "Other", purchaseUnit: "lb", price: 2 }] }]} rid="berts" />);
  await input("Order quantity global_food", "2"); await click(container.querySelector('[aria-label="Confirm reviewed order quantities"]')); await input("Order supplier global_food", "other");
  expect(container.querySelector('[aria-label="Order quantity global_food"]').value).toBe(""); expect(container.querySelector('[aria-label="Confirm reviewed order quantities"]').checked).toBe(false);
});
test("native ownership labels unknown counts and estimated recipe cost separately", async () => {
  await render(<OwnerDashboard />);
  expect(container.querySelector('[data-testid="owner-total-inv"]').textContent).toContain("Count unavailable"); expect(container.textContent).toContain("Estimated recipe cost %"); expect(container.textContent).not.toContain("Avg Food Cost");
  expect(container.querySelector('[data-chart-key="Inventory Value"]')).toBeNull(); expect(api.ownerVendorScorecard).not.toHaveBeenCalled();
});
test("native ownership rejects an old rollup instead of silently displaying legacy money", async () => {
  api.ownerSummary.mockResolvedValue({ stores: [store], totals: { inventoryValue: 9999 } });
  await render(<OwnerDashboard />); expect(container.querySelector('[data-testid="owner-error"]')).not.toBeNull(); expect(container.textContent).not.toContain("9999");
});
test("native Item Setup offers dated counts instead of an editable current-stock field", async () => {
  await render(<SetupTab items={[]} areas={[{ name: "Dry storage", prefix: "DR" }]} rid="berts" />);
  expect(container.querySelector('[data-testid="setup-native-count-note"]')).not.toBeNull(); expect(container.textContent).not.toContain("Current Stock (purchase units)"); expect(container.querySelector('[data-testid="native-inventory-position"]')).not.toBeNull();
});
test("disabled actual mode retains the earlier ordering screen", async () => {
  api.actualInventoryEnabled = false; await render(<OrderTab items={[item]} rid="berts" showToast={() => {}} />);
  expect(container.querySelector('[data-testid="native-order-planner"]')).toBeNull(); expect(container.textContent).toContain("Smart Order Generator");
});
