import React, { act } from "react";
import { createRoot } from "react-dom/client";
import { PhysicalCountForm, ActualPeriodView, ReopenPeriodForm, ScopeHandoffReview, ActualInventoryTab } from "./ActualInventoryTab";
import * as api from "../lib/api";
import { SalesTrackingTab } from "./SalesTrackingTab";

const scope = { header: { id: "scope-1", revision: 1 }, items: [{ item_code: "food", base_unit: "lb", name_snapshot: "Synthetic food", location_notes: "All raw storage" }] };
const report = { status: "incomplete", errors: ["Missing confirmed value"], warnings: [], rows: [], openingValue: null, closingValue: null,
  actualFoodCost: null, netPurchaseCost: "40.00", openingSnapshotId: "opening", closingSnapshotId: "closing", reportHash: "abc",
  openingCountDate: "2026-10-01", closingCountDate: "2026-10-08", openingTiming: "before_receipts", closingTiming: "before_receipts", receivedFrom: "2026-10-01", receivedBefore: "2026-10-08" };
let root, container;
beforeEach(() => {
  global.IS_REACT_ACT_ENVIRONMENT = true;
  Object.defineProperty(global, "crypto", { configurable: true, value: { randomUUID: () => "stable-request-key" } });
  container = document.createElement("div"); document.body.appendChild(container); root = createRoot(container);
});
afterEach(async () => { await act(async () => root.unmount()); container.remove(); jest.restoreAllMocks(); });
async function input(label, value) {
  const node = container.querySelector(`[aria-label="${label}"]`);
  await act(async () => {
    Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value").set.call(node, value);
    node.dispatchEvent(new Event("input", { bubbles: true })); node.dispatchEvent(new Event("change", { bubbles: true }));
  });
}
async function select(label, value) {
  await act(async () => { const node = container.querySelector(`[aria-label="${label}"]`); node.value = value; node.dispatchEvent(new Event("change", { bubbles: true })); });
}
async function click(node) { await act(async () => node.click()); }
async function countHeader() { await input("Physical count date", "2026-10-01"); await select("Count timing", "before_receipts"); await input("Count note", "Measured physical inventory"); }
async function reason(value) {
  const node = container.querySelector('[aria-label="Correction reason"]');
  await act(async () => { Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, "value").set.call(node, value); node.dispatchEvent(new Event("input", { bubbles: true })); });
}
const plan = { firstClosureId: "first-closed", planHash: "reviewed-plan", affectedPeriods: [
  { id: "first-closed", periodStart: "2026-10-01", receivedBefore: "2026-10-08", actualFoodCost: "55.00" },
  { id: "later-closed", periodStart: "2026-10-08", receivedBefore: "2026-10-15", actualFoodCost: "15.00" },
] };

test("blank physical quantities and values are saved as missing, never zero", async () => {
  const save = jest.fn().mockResolvedValue({ header: { id: "snapshot-1", status: "incomplete" }, lines: [{}] });
  await act(async () => root.render(<PhysicalCountForm scope={scope} onSave={save} />)); await countHeader(); await click(container.querySelector("button"));
  const line = save.mock.calls[0][0].lines[0];
  expect(line.counted_quantity).toBeNull(); expect(line.inventory_value).toBeNull(); expect(line.base_units_per_counted_unit).toBeNull(); expect(line.confirmed).toBe(false);
  expect(container.textContent).toContain("Count saved and confirmed · incomplete");
  expect(container.textContent).toContain("completed recount");
});

test("failed count save preserves exact decimal values and the request key", async () => {
  const save = jest.fn().mockRejectedValue(new Error("Connection lost"));
  await act(async () => root.render(<PhysicalCountForm scope={scope} onSave={save} />)); await countHeader();
  await input("Quantity food", "1.50"); await input("Value food", "45.00"); await input("Evidence food", "Verified quantity and value");
  await click(container.querySelector('[aria-label="Confirm food"]')); await click(container.querySelector("button"));
  expect(container.textContent).toContain("Connection lost"); expect(container.textContent).not.toContain("Count saved and confirmed");
  expect(container.querySelector("fieldset").disabled).toBe(true);
  await click(container.querySelector("button")); expect(save.mock.calls[1]).toEqual(save.mock.calls[0]);
  expect(save.mock.calls[0][0].lines[0].inventory_value).toBe("45.00");
});

test("incomplete Food Cost stays incomplete and cannot close", async () => {
  const close = jest.fn(); await act(async () => root.render(<ActualPeriodView report={report} onClose={close} />));
  await click(container.querySelector('[aria-label="Confirm period review"]'));
  const button = container.querySelector("button"); expect(button.disabled).toBe(true); await click(button); expect(close).not.toHaveBeenCalled();
  expect(container.textContent).toContain("Missing confirmed value"); expect(container.textContent).toContain("Incomplete");
});

test("a failed close retries the exact reviewed report and key", async () => {
  const close = jest.fn().mockRejectedValue(new Error("Close interrupted"));
  await act(async () => root.render(<ActualPeriodView report={{ ...report, status: "complete", errors: [], openingValue: "60.00", closingValue: "45.00", actualFoodCost: "55.00" }} onClose={close} />));
  await click(container.querySelector('[aria-label="Confirm period review"]')); await click(container.querySelector("button"));
  expect(container.textContent).toContain("Close interrupted"); await click(container.querySelector("button"));
  expect(close.mock.calls[1]).toEqual(close.mock.calls[0]); expect(close.mock.calls[0][0].expected_report_hash).toBe("abc");
});

test("native sales mode cannot edit counts or close accounting periods", async () => {
  await act(async () => root.render(<SalesTrackingTab actualMode items={[{ controlNumber: "food", name: "Synthetic food", salesTracked: true, vendorSkus: [] }]}
    dishes={[]} purchases={[]} adjustments={[]} salesPeriod={{ periodStart: "2026-10-01", periodEnd: "2026-10-07", dishSales: {}, itemCounts: {} }}
    persist={jest.fn()} reportingPeriods={[]} persistReportingPeriods={jest.fn()} showToast={jest.fn()} />));
  expect(container.textContent).toContain("Expected Usage"); expect(container.textContent).not.toContain("Beginning Count");
  expect(container.querySelector('[data-testid="save-period-button"]')).toBeNull();
  expect(container.querySelector('[data-testid="variance-table"]').textContent).not.toContain("Actual");
});

test("reopening requires a reason and review of the full affected chain", async () => {
  const reopen = jest.fn(); await act(async () => root.render(<ReopenPeriodForm plan={plan} onReopen={reopen} />));
  expect(container.textContent).toContain("2 affected periods"); expect(container.textContent).toContain("2026-10-15");
  expect(container.querySelector("button").disabled).toBe(true);
  await reason("Correct closing count"); expect(container.querySelector("button").disabled).toBe(true);
  await click(container.querySelector('[aria-label="Review affected periods"]')); expect(container.querySelector("button").disabled).toBe(false);
  expect(reopen).not.toHaveBeenCalled();
});

test("lost reopening response retries the exact reason, chain fingerprint and key", async () => {
  const reopen = jest.fn().mockRejectedValueOnce(new Error("Response lost")).mockResolvedValue({ status: "reopened", event: { id: "event-1", plan_snapshot: plan } });
  await act(async () => root.render(<ReopenPeriodForm plan={plan} onReopen={reopen} />));
  await reason("Correct closing count"); await click(container.querySelector('[aria-label="Review affected periods"]')); await click(container.querySelector("button"));
  expect(container.textContent).toContain("Response lost"); expect(container.textContent).not.toContain("Periods reopened and confirmed");
  expect(container.querySelector("fieldset").disabled).toBe(true);
  await click(container.querySelector("button")); expect(reopen.mock.calls[1]).toEqual(reopen.mock.calls[0]);
  expect(reopen.mock.calls[0][0].expected_plan_hash).toBe("reviewed-plan"); expect(container.textContent).toContain("Periods reopened and confirmed");
});

test("replacement close carries the preserved original report reference", async () => {
  const close = jest.fn().mockResolvedValue({});
  await act(async () => root.render(<ActualPeriodView report={{ ...report, status: "complete", errors: [], openingValue: "60", closingValue: "30", actualFoodCost: "70", supersedesClosureId: "original-closed" }} onClose={close} />));
  expect(container.textContent).toContain("Close replacement period");
  await click(container.querySelector('[aria-label="Confirm period review"]')); await click(container.querySelector("button"));
  expect(close.mock.calls[0][0].supersedes_closure_id).toBe("original-closed");
});

const handoff = { status: "ready", errors: [], anchorClosureId: "anchor", newOpeningSnapshotId: "new-opening", planHash: "handoff-plan",
  oldScopeRevision: 1, newScopeRevision: 2, countDate: "2026-10-08", timing: "before_receipts", oldValue: "45.00", newValue: "45.00",
  rows: [{ itemCode: "food", name: "Synthetic food", change: "carried", baseUnit: "lb", oldQuantity: "30.00", newQuantity: "30.00", oldValue: "45.00", newValue: "45.00" },
    { itemCode: "new", name: "New food", change: "added", baseUnit: "each", oldQuantity: null, newQuantity: "0", oldValue: null, newValue: "0.00" }] };

test("held item-list handoffs display missing balances and cannot be accepted", async () => {
  const accept = jest.fn();
  await act(async () => root.render(<ScopeHandoffReview plan={{ ...handoff, status: "held", errors: ["Confirm the new item's zero balance"], newValue: null,
    rows: [{ ...handoff.rows[1], newQuantity: null, newValue: null }] }} onAccept={accept} />));
  expect(container.textContent).toContain("Incomplete"); expect(container.textContent).toContain("Not in old list");
  await input("Handoff evidence", "Reviewed all stock"); await click(container.querySelector('[aria-label="Confirm item-list handoff"]'));
  expect(container.querySelector("button").disabled).toBe(true); await click(container.querySelector("button")); expect(accept).not.toHaveBeenCalled();
});

test("handoff retry preserves the reviewed plan and does not claim success on lost response", async () => {
  const accept = jest.fn().mockRejectedValueOnce(new Error("Response lost")).mockResolvedValue({ status: "accepted", bridge: { id: "handoff-1", plan_snapshot: handoff } });
  await act(async () => root.render(<ScopeHandoffReview plan={handoff} onAccept={accept} />));
  expect(container.querySelector("button").disabled).toBe(true);
  await input("Handoff evidence", "Reviewed retained quantity and value; new stock is zero"); await click(container.querySelector('[aria-label="Confirm item-list handoff"]')); await click(container.querySelector("button"));
  expect(container.textContent).toContain("Response lost"); expect(container.textContent).not.toContain("handoff saved and confirmed");
  expect(container.querySelector("fieldset").disabled).toBe(true);
  await click(container.querySelector("button")); expect(accept.mock.calls[1]).toEqual(accept.mock.calls[0]);
  expect(accept.mock.calls[0][0].expected_plan_hash).toBe("handoff-plan"); expect(container.textContent).toContain("handoff saved and confirmed");
});

test("handoff response must confirm the same reviewed plan before showing saved", async () => {
  const accept = jest.fn().mockResolvedValue({ status: "accepted", bridge: { id: "different", plan_snapshot: { planHash: "wrong-plan" } } });
  await act(async () => root.render(<ScopeHandoffReview plan={handoff} onAccept={accept} />));
  await input("Handoff evidence", "Verified stock"); await click(container.querySelector('[aria-label="Confirm item-list handoff"]')); await click(container.querySelector("button"));
  expect(container.textContent).toContain("was not confirmed"); expect(container.textContent).not.toContain("handoff saved and confirmed");
});

test("period close includes its reviewed opening handoff reference", async () => {
  const close = jest.fn().mockResolvedValue({});
  await act(async () => root.render(<ActualPeriodView report={{ ...report, status: "complete", errors: [], openingValue: "45.00", closingValue: "30.00", actualFoodCost: "15.00", openingBridgeId: "handoff-1" }} onClose={close} />));
  expect(container.textContent).toContain("reviewed item-list handoff"); await click(container.querySelector('[aria-label="Confirm period review"]')); await click(container.querySelector("button"));
  expect(close.mock.calls[0][0].opening_bridge_id).toBe("handoff-1");
});

test("physical count entry selects the requested historical item-list version", async () => {
  const newer = { header: { id: "scope-2", revision: 2, note: "Added food" }, items: [...scope.items, { item_code: "new", base_unit: "each", name_snapshot: "New food", location_notes: "Raw storage" }] };
  jest.spyOn(api, "actualSetup").mockResolvedValue({ scope: newer, scopes: [newer.header, scope.header], items: [] });
  jest.spyOn(api, "actualCounts").mockResolvedValue([]); jest.spyOn(api, "actualClosed").mockResolvedValue([]); jest.spyOn(api, "actualHandoffs").mockResolvedValue([]);
  jest.spyOn(api, "staffCountSheets").mockResolvedValue([]);
  const fetchScope = jest.spyOn(api, "actualScopeDetails").mockResolvedValue(scope);
  await act(async () => root.render(<ActualInventoryTab restaurantId="berts" view="counts" />));
  expect(container.querySelector('[aria-label="Quantity new"]')).not.toBeNull();
  await select("Count item-list version", "scope-1"); expect(fetchScope).toHaveBeenCalledWith("berts", "scope-1");
  expect(container.querySelector('[aria-label="Quantity new"]')).toBeNull(); expect(container.querySelector('[aria-label="Quantity food"]')).not.toBeNull();
});
