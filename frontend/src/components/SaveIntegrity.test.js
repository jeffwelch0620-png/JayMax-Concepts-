import React, { act } from "react";
import { createRoot } from "react-dom/client";
import { SalesTrackingTab } from "./SalesTrackingTab";
import { SetupTab } from "./SetupTab";
import { AdjustmentsTab } from "./AdjustmentsTab";
import { CostingTab } from "./CostingTab";
import { PrepTab } from "./PrepTab";
import { InvoicesTab } from "./InvoicesTab";
import * as api from "../lib/api";

jest.mock("../lib/api", () => ({ __esModule: true, prepPlanningEnabled: false, listVendorContacts: jest.fn(() => Promise.resolve([])), putVendorContact: jest.fn(), listPrepItems: jest.fn(), getPrepList: jest.fn(), getCountSession: jest.fn(), deletePrepItem: jest.fn(), prepReport: jest.fn(), getProjections: jest.fn(), listOverrides: jest.fn(), getStaffPin: jest.fn(), getParRecs: jest.fn(), deleteOverride: jest.fn() }));
const item = { controlNumber: "F01", name: "Invented food", storageArea: "Freezer", purchaseUnit: "case", packCount: 1, unitQty: 10, unitUOM: "lb", portionSize: 4, portionUOM: "oz", salesTracked: true, vendorSkus: [{ id: "sku", vendor: "PFG", price: 10, preferred: true }] };
const period = { periodStart: "2026-10-01", periodEnd: "2026-10-07", dishSales: { dish: "2" }, itemCounts: {} };
const recipe = { id: "dish", name: "Invented dish", recipeType: "menu", menuCategory: "Appetizers", menuCode: "A1", description: "", photoUrl: "", price: 0, targetPct: 30, procedure: "", equipment: "", shelfLife: "", portionNote: "", lines: [{ sourceType: "item", controlNumber: "F01", qty: 1 }] };
const deferred = () => { let resolve; const promise = new Promise(a => { resolve = a; }); return { promise, resolve }; };
let root, container, save, periods, success, errors, drafts;
const render = element => act(async () => root.render(element));
const find = id => container.querySelector(`[data-testid="${id}"]`);
const click = element => act(async () => element.click());
async function input(id, value) {
  await act(async () => {
    const element = find(id);
    Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value").set.call(element, value);
    element.dispatchEvent(new Event("input", { bubbles: true }));
  });
}
const sales = (overrides = {}) => <SalesTrackingTab rid="berts" revision={10} drafts={drafts} actualMode items={[item]} dishes={[recipe]} purchases={[]} adjustments={[]} salesPeriod={period} persist={save} reportingPeriods={[]} persistReportingPeriods={periods} showToast={success} showError={errors} {...overrides} />;
const setup = () => <SetupTab rid="berts" drafts={drafts} items={[item]} areas={[{ name: "Freezer", prefix: "F" }]} persistItems={save} persistAreas={save} showToast={success} showError={errors} />;
const adjustments = () => <AdjustmentsTab rid="berts" drafts={drafts} items={[item]} adjustments={[{ id: "old", date: "2026-10-01", controlNumber: "F01", reason: "waste", qty: 1 }]} persist={save} showToast={success} showError={errors} />;
const costing = overrides => <CostingTab rid="berts" drafts={drafts} items={[item]} dishes={[recipe]} persist={save} showToast={success} showError={errors} {...overrides} />;
beforeEach(() => {
  global.IS_REACT_ACT_ENVIRONMENT = true; jest.useFakeTimers(); jest.clearAllMocks();
  api.listVendorContacts.mockResolvedValue([]); api.listPrepItems.mockResolvedValue([]); api.getPrepList.mockResolvedValue({ list: null });
  api.prepPlanningEnabled = false;
  api.getProjections.mockResolvedValue([]); api.listOverrides.mockResolvedValue([]); api.getStaffPin.mockResolvedValue({ staffPin: "", custom: true }); api.getParRecs.mockResolvedValue([]);
  container = document.createElement("div"); document.body.appendChild(container); root = createRoot(container);
  save = jest.fn().mockResolvedValue({ revision: 11 }); periods = jest.fn().mockResolvedValue({ revision: 12 }); success = jest.fn(); errors = jest.fn(); drafts = new Map();
  jest.spyOn(window, "confirm").mockReturnValue(true);
});
afterEach(async () => { await act(async () => root.unmount()); container.remove(); jest.useRealTimers(); jest.restoreAllMocks(); });

test("polling leaves a dirty sales draft and its original revision intact", async () => {
  await render(sales()); await input("dish-sales-dish", "17");
  await render(sales({ revision: 20, salesPeriod: { ...period, dishSales: { dish: "99" } } }));
  expect(find("dish-sales-dish").value).toBe("17"); expect(container.querySelector('[role="alert"]').textContent).toContain("changed");
  await act(async () => jest.advanceTimersByTime(700));
  expect(save).toHaveBeenCalledWith({ ...period, dishSales: { dish: "17" } }, 10);
});
test.each([409, 422, 500, "offline"])("failed sales %s retains entries for retry and navigation", async status => {
  save.mockRejectedValueOnce({ response: { status }, message: "Save failed" });
  await render(sales()); await input("dish-sales-dish", "17"); await act(async () => jest.advanceTimersByTime(700));
  expect(find("dish-sales-dish").value).toBe("17"); expect(find("retry-sales-save")).not.toBeNull(); expect(success).not.toHaveBeenCalled();
  await render(<p>Other tab</p>); await render(sales()); expect(find("dish-sales-dish").value).toBe("17");
  await click(find("retry-sales-save")); expect(find("retry-sales-save")).toBeNull();
});
test("leaving before debounce keeps a draft without sending to another location or duplicating on unmount", async () => {
  await render(sales()); await input("dish-sales-dish", "17"); await render(<p>Other location</p>);
  await act(async () => jest.advanceTimersByTime(700)); expect(save).not.toHaveBeenCalled();
  await render(sales({ rid: "rudds" })); expect(find("dish-sales-dish").value).toBe("2");
  await render(<p>Other tab</p>); await render(sales()); expect(find("dish-sales-dish").value).toBe("17");
  await click(find("retry-sales-save")); await render(<p>Other tab</p>); expect(save).toHaveBeenCalledTimes(1);
});
test("typing during a pending sales save survives acknowledgement and is saved once next", async () => {
  const pending = deferred(); save.mockReturnValueOnce(pending.promise).mockResolvedValueOnce({ revision: 12 });
  await render(sales()); await input("dish-sales-dish", "17"); await act(async () => jest.advanceTimersByTime(700));
  await input("dish-sales-dish", "18"); await act(async () => pending.resolve({ revision: 11 }));
  expect(find("dish-sales-dish").value).toBe("18");
  await act(async () => jest.advanceTimersByTime(700));
  expect(save).toHaveBeenLastCalledWith({ ...period, dishSales: { dish: "18" } }, 11); expect(save).toHaveBeenCalledTimes(2);
});
test("late sales acknowledgement after leaving retains draft for explicit review on return", async () => {
  const pending = deferred(); save.mockReturnValueOnce(pending.promise);
  await render(sales()); await input("dish-sales-dish", "17"); await act(async () => jest.advanceTimersByTime(700));
  await render(<p>Other tab</p>); await act(async () => pending.resolve({ revision: 11 }));
  await render(sales()); expect(find("dish-sales-dish").value).toBe("17"); expect(find("retry-sales-save")).not.toBeNull(); expect(success).not.toHaveBeenCalled();
});
test("next working period failure preserves current entries", async () => {
  save.mockResolvedValueOnce({ revision: 11 }).mockResolvedValueOnce(null);
  await render(sales()); await click(find("next-period-button"));
  expect(find("dish-sales-dish").value).toBe("2"); expect(find("period-start").value).toBe(period.periodStart); expect(success).not.toHaveBeenCalled();
});
test("next working period changes only after both saves are confirmed", async () => {
  save.mockResolvedValueOnce({ revision: 11 }).mockResolvedValueOnce({ revision: 12 });
  await render(sales()); await click(find("next-period-button"));
  expect(find("period-start").value).toBe("2026-10-08"); expect(find("dish-sales-dish").value).toBe(""); expect(success).toHaveBeenCalledTimes(1);
});
test("invalid close dates send no write; snapshot failure sends no success", async () => {
  await render(sales({ actualMode: false, salesPeriod: { ...period, periodStart: "2026-10-09" } }));
  await click(find("save-period-button")); expect(save).not.toHaveBeenCalled(); expect(periods).not.toHaveBeenCalled();
  await render(sales({ actualMode: false })); periods.mockResolvedValueOnce(null);
  await click(find("save-period-button")); expect(success).not.toHaveBeenCalled(); expect(find("dish-sales-dish").value).toBe("2");
});
test("discarding a retained draft explicitly loads latest polled sales", async () => {
  await render(sales()); await input("dish-sales-dish", "17");
  await render(sales({ revision: 20, salesPeriod: { ...period, dishSales: { dish: "99" } } }));
  await click(find("discard-sales-draft")); expect(find("dish-sales-dish").value).toBe("99");
  await act(async () => jest.advanceTimersByTime(700)); expect(save).not.toHaveBeenCalled();
});
test("explicit retry reads fresh data and merges independent fields at the returned revision", async () => {
  const latest = { ...period, dishSales: { dish: "2", other: "99" }, itemCounts: { F01: { ending: "5" } } };
  const loadLatestSales = jest.fn().mockResolvedValue({ data: latest, revision: 20 });
  await render(sales({ loadLatestSales })); await input("dish-sales-dish", "17");
  await click(find("retry-sales-save"));
  expect(loadLatestSales).toHaveBeenCalledTimes(1);
  expect(save).toHaveBeenCalledWith({ ...latest, dishSales: { dish: "17", other: "99" } }, 20);
  expect(find("retry-sales-save")).toBeNull();
});
test.each(["field", "period", "unavailable"])("retry refuses %s conflicts and retains the draft", async kind => {
  const latest = kind === "unavailable" ? null : { revision: 20, data: kind === "field"
    ? { ...period, dishSales: { dish: "99" } } : { ...period, periodStart: "2026-10-08" } };
  await render(sales({ loadLatestSales: jest.fn().mockResolvedValue(latest) })); await input("dish-sales-dish", "17");
  await click(find("retry-sales-save")); expect(save).not.toHaveBeenCalled();
  expect(find("dish-sales-dish").value).toBe("17"); expect(find("retry-sales-save")).not.toBeNull();
  expect(errors).toHaveBeenCalled();
});
test("typing during retry's fresh read keeps the later edit and the merged remote field", async () => {
  const reading = deferred(); const loadLatestSales = jest.fn().mockReturnValue(reading.promise);
  await render(sales({ loadLatestSales })); await input("dish-sales-dish", "17"); await click(find("retry-sales-save"));
  await input("dish-sales-dish", "18");
  await act(async () => reading.resolve({ revision: 20, data: { ...period, dishSales: { dish: "2", other: "99" } } }));
  expect(find("dish-sales-dish").value).toBe("18");
  await act(async () => jest.advanceTimersByTime(700));
  expect(save).toHaveBeenLastCalledWith({ ...period, dishSales: { dish: "18", other: "99" } }, 11);
});
test("leaving during retry's fresh read sends no write and retains the original location draft", async () => {
  const reading = deferred();
  await render(sales({ loadLatestSales: jest.fn().mockReturnValue(reading.promise) }));
  await input("dish-sales-dish", "17"); await click(find("retry-sales-save")); await render(<p>Other location</p>);
  await act(async () => reading.resolve({ revision: 20, data: period }));
  expect(save).not.toHaveBeenCalled(); expect(drafts.get("sales:berts").data.dishSales.dish).toBe("17");
});
test.each([null, {}, { revision: 11, ok: false }])("item save %j retains form; failed delete and area save do not claim success", async result => {
  save.mockResolvedValue(result); await render(setup()); await input("item-name-input", "New food"); await click(find("item-submit-button"));
  expect(find("item-name-input").value).toBe("New food"); expect(success).not.toHaveBeenCalled();
  await click(find("delete-item-F01")); expect(find("setup-item-row-F01")).not.toBeNull();
  await input("new-area-name", "Walk-in"); await input("new-area-prefix", "WI"); await click(find("add-area-button"));
  expect(find("new-area-name").value).toBe("Walk-in"); expect(success).not.toHaveBeenCalled(); expect(container.querySelector('[role="alert"]')).not.toBeNull();
});
test("item form survives leaving and later successful save clears it", async () => {
  await render(setup()); await input("item-name-input", "Draft food"); await render(<p>Other tab</p>); await render(setup());
  expect(find("item-name-input").value).toBe("Draft food"); await click(find("item-submit-button")); expect(find("item-name-input").value).toBe(""); expect(success).toHaveBeenCalledTimes(1);
});
test("item acknowledgement cannot clear typing performed after submission", async () => {
  const pending = deferred(); save.mockReturnValueOnce(pending.promise);
  await render(setup()); await input("item-name-input", "First"); await click(find("item-submit-button"));
  await input("item-name-input", "Second"); await act(async () => pending.resolve({ revision: 11 }));
  expect(find("item-name-input").value).toBe("Second");
});
test("adjustment failure retains quantity and note; delete failure leaves saved record visible", async () => {
  save.mockRejectedValue(new Error("Offline")); await render(adjustments()); await input("adj-qty", "3"); await input("adj-note", "Dropped pan");
  await click(find("log-adjustment-button")); expect(find("adj-qty").value).toBe("3"); expect(find("adj-note").value).toBe("Dropped pan"); expect(success).not.toHaveBeenCalled();
  await click(find("adj-delete-old")); expect(find("adj-row-old")).not.toBeNull(); expect(success).not.toHaveBeenCalled();
  await render(<p>Other tab</p>); await render(adjustments()); expect(find("adj-note").value).toBe("Dropped pan");
});

test("a confirmed adjustment clears its retained draft after leaving the form", async () => {
  const pending = deferred(); save.mockReturnValueOnce(pending.promise);
  await render(adjustments()); await input("adj-qty", "3"); await click(find("log-adjustment-button"));
  await render(<p>Another location</p>); await act(async () => pending.resolve({ revision: 11 }));
  await render(adjustments()); expect(find("adj-qty").value).toBe("");
  await click(find("log-adjustment-button")); expect(save).toHaveBeenCalledTimes(1); expect(drafts.has("adjustment:berts")).toBe(false);
});

test.each([false, true])("A to B to A acknowledgement preserves newer typing (%s)", async newer => {
  const pending = deferred(); save.mockReturnValueOnce(pending.promise);
  await render(adjustments()); await input("adj-qty", "3"); await click(find("log-adjustment-button"));
  await render(<AdjustmentsTab rid="rudds" key="rudds" drafts={drafts} items={[item]} adjustments={[]} persist={save} showToast={success} showError={errors} />);
  await input("adj-qty", "9");
  await render(adjustments()); if (newer) await input("adj-qty", "4");
  await act(async () => pending.resolve({ revision: 11 }));
  expect(find("adj-qty").value).toBe(newer ? "4" : "");
  expect(drafts.has("adjustment:berts")).toBe(newer);
  expect(drafts.get("adjustment:rudds").qty).toBe("9"); expect(save).toHaveBeenCalledTimes(1);
});
test("recipe failure and polling preserve draft; deletion never claims unconfirmed success", async () => {
  save.mockResolvedValue(null); const focus = { id: "dish" };
  await render(costing({ focusDish: focus })); await input("recipe-name-input", "Edited recipe");
  await render(costing({ focusDish: focus, dishes: [{ ...recipe, name: "Polling value" }] })); expect(find("recipe-name-input").value).toBe("Edited recipe");
  await click(find("save-recipe-button")); expect(find("recipe-name-input").value).toBe("Edited recipe"); expect(success).not.toHaveBeenCalled();
  expect(save).toHaveBeenCalledTimes(1);
  await click(find("delete-recipe-dish")); expect(find("recipe-row-dish")).not.toBeNull(); expect(success).not.toHaveBeenCalled();
});

test("supplier response cannot clear an email entered while contacts are loading", async () => {
  const pending = deferred(); api.listVendorContacts.mockReturnValueOnce(pending.promise);
  await render(setup()); const id = [...container.querySelectorAll('input[type="email"]')][0].dataset.testid;
  await input(id, "draft@example.test"); await act(async () => pending.resolve([]));
  expect(find(id).value).toBe("draft@example.test");
  api.putVendorContact.mockResolvedValueOnce({});
  await click(find(id.replace("input", "save"))); expect(success).not.toHaveBeenCalled(); expect(find(id).value).toBe("draft@example.test");
  await render(<p>Other tab</p>); await render(setup()); expect(find(id).value).toBe("draft@example.test");
});
const legacyInvoice = () => <InvoicesTab rid="berts" items={[item]} purchases={[]} persistPurchases={save} persistItems={periods} showToast={success} showError={errors} />;
async function manualInvoice() {
  await render(legacyInvoice()); await click(find("invoice-mode-manual"));
  await input("invoice-number-input", "SYNTHETIC-TEST"); await input("invoice-line-qty", "2"); await input("invoice-line-cost", "10");
  await click([...container.querySelectorAll("button")].find(b => b.textContent.includes("Add Line")));
}
test("legacy invoice purchase failure retains original form and never attempts catalog save", async () => {
  save.mockResolvedValueOnce(null); await manualInvoice(); await click(find("save-invoice-button"));
  expect(find("invoice-number-input").value).toBe("SYNTHETIC-TEST"); expect(container.textContent).toContain("Invented food"); expect(periods).not.toHaveBeenCalled(); expect(success).not.toHaveBeenCalled();
});
test("partial legacy invoice failure is disclosed and cannot be resubmitted", async () => {
  periods.mockResolvedValueOnce(null); await manualInvoice(); await click(find("save-invoice-button"));
  expect(container.querySelector('[role="alert"]').textContent).toContain("Purchase history saved"); expect(find("invoice-number-input").value).toBe("SYNTHETIC-TEST"); expect(success).not.toHaveBeenCalled();
  await click(find("save-invoice-button")); expect(save).toHaveBeenCalledTimes(1);
});

const prep = () => <PrepTab rid="berts" drafts={drafts} showError={errors} showToast={success} items={[item]} dishes={[{ ...recipe, recipeType: "prep", yieldQty: 4, yieldUOM: "lb", prepPar: 0 }]} persistDishes={save} prepStock={[]} prepLogs={[]} salesPeriod={period} />;
test("installed schema holds legacy count, list, overrides and advice screens with frontend flags off", async () => {
  await render(<PrepTab rid="berts" drafts={drafts} items={[item]} dishes={[]} prepCapabilities={{ countsAvailable: false, listsAvailable: false, reportingAvailable: false }} />);
  expect(find("prep-list-unavailable")).not.toBeNull(); expect(api.getPrepList).not.toHaveBeenCalled();
  await click(find("prep-subtab-count")); expect(find("prep-count-unavailable")).not.toBeNull(); expect(api.getCountSession).not.toHaveBeenCalled();
  await click(find("prep-subtab-planning"));
  expect(find("prep-overrides-unavailable")).not.toBeNull(); expect(find("prep-advisor-unavailable")).not.toBeNull();
  expect(api.getParRecs).not.toHaveBeenCalled(); expect(api.listOverrides).not.toHaveBeenCalled();
  expect(find("projection-save-button")).not.toBeNull(); expect(find("staff-pin-card")).not.toBeNull(); expect(save).not.toHaveBeenCalled();
});
test("failed list and count reads show the hold reason without generating or displaying a false empty list", async () => {
  api.getPrepList.mockRejectedValue({response:{status:410,data:{detail:"Use reviewed dated prep tasks"}}});
  api.getCountSession.mockRejectedValue({response:{status:409,data:{detail:"Use manager-issued prep sheets"}}});
  await render(prep()); expect(find("prep-list-load-error").textContent).toContain("Use reviewed dated prep tasks"); expect(find("generate-prep-list-button")).toBeNull();
  await click(find("prep-subtab-count")); expect(find("count-load-error").textContent).toContain("manager-issued prep sheets"); expect(find("count-loading")).toBeNull();
});
test("a late prep-list response for another location cannot replace the current load failure", async () => {
  const old=deferred(); api.getPrepList.mockReturnValueOnce(old.promise).mockRejectedValueOnce(new Error("Offline"));
  await render(prep()); await render(<PrepTab rid="rudds" drafts={drafts} items={[]} dishes={[]} prepStock={[]} prepLogs={[]} />);
  await act(async () => old.resolve({list:{id:"old",tasks:[],status:"released"}}));
  expect(find("prep-list-load-error")).not.toBeNull(); expect(find("list-status-pill")).toBeNull();
});
test("a held legacy override deletion retains its row and reports no success", async () => {
  api.listOverrides.mockResolvedValue([{ id: "held", date: "2026-10-08", type: "add", customName: "Invented catering", batches: 1 }]);
  api.deleteOverride.mockRejectedValue({ response: { status: 409, data: { detail: "Use reviewed day adjustments" } } });
  await render(prep()); await click(find("prep-subtab-planning")); await click(find("override-delete-held"));
  expect(find("override-row-held")).not.toBeNull(); expect(errors).toHaveBeenCalledWith("Use reviewed day adjustments"); expect(success).not.toHaveBeenCalledWith("Override removed");
});
test("a retired prep state cannot display an empty balance or legacy stock controls", async () => {
  await render(<PrepTab rid="berts" drafts={drafts} items={[item]} dishes={[]} prepStock={null} prepLogs={null} prepReadStatus={{ available: false, message: "Historical prep figures are retained for review." }} />);
  await click(find("prep-subtab-inventory"));
  expect(find("prep-inventory-unavailable").textContent).toContain("Historical prep figures");
  expect(find("prep-inventory-log")).toBeNull(); expect(api.prepReport).not.toHaveBeenCalled();
});
test("prep setting edits send no per-keystroke write and failure retains draft across navigation", async () => {
  await render(prep()); await click(find("prep-subtab-inventory")); await input("prep-par-dish", "17"); expect(save).not.toHaveBeenCalled();
  expect(container.textContent).toContain("Unsaved prep settings");
  save.mockResolvedValueOnce(null); await click(find("prep-save-meta-dish")); expect(find("prep-par-dish").value).toBe("17"); expect(success).not.toHaveBeenCalled();
  await render(<p>Other tab</p>); await render(prep()); await click(find("prep-subtab-inventory")); expect(find("prep-par-dish").value).toBe("17");
  await click(find("prep-save-meta-dish")); expect(save.mock.calls[1][0][0].prepPar).toBe(17); expect(success).toHaveBeenCalledTimes(1);
  expect(container.textContent).not.toContain("Unsaved prep settings");
});
test("held standing prep removal does not report a successful deletion", async () => {
  api.listPrepItems.mockResolvedValue([{id:"standing",name:"Invented portions",sourceType:"item",vesselName:"bag",schedule:"daily"}]);
  api.deletePrepItem.mockRejectedValue({response:{status:409,data:{detail:"Legacy standing metadata retained"}}});
  await render(prep()); await click(find("delete-prep-item-standing"));
  expect(success).toHaveBeenCalledWith("Legacy standing metadata retained"); expect(success).not.toHaveBeenCalledWith("Prep item removed"); expect(find("standing-item-standing")).not.toBeNull();
});
test("native prep planning keeps legacy standing metadata controls read-only", async () => {
  api.prepPlanningEnabled = true; api.listPrepItems.mockResolvedValue([{id:"standing",name:"Invented portions",sourceType:"item",vesselName:"bag",schedule:"daily"}]);
  await render(prep()); expect(find("add-prep-item-button").disabled).toBe(true); expect(find("delete-prep-item-standing").disabled).toBe(true); expect(find("schedule-daily-standing").disabled).toBe(true);
});
test("prep acknowledgement cannot erase settings typed while saving", async () => {
  const pending = deferred(); save.mockReturnValueOnce(pending.promise);
  await render(prep()); await click(find("prep-subtab-inventory")); await input("prep-par-dish", "17"); await click(find("prep-save-meta-dish"));
  await input("prep-par-dish", "18"); await act(async () => pending.resolve({ revision: 11 })); expect(find("prep-par-dish").value).toBe("18");
  await render(<p>Other tab</p>); await render(prep()); await click(find("prep-subtab-inventory")); expect(find("prep-par-dish").value).toBe("18");
});
test("focused recipe draft survives returning to the same tab", async () => {
  const focus = { id: "dish", nonce: 1 }; await render(costing({ focusDish: focus })); await input("recipe-name-input", "Draft recipe");
  await render(<p>Other tab</p>); await render(costing({ focusDish: focus })); expect(find("recipe-name-input").value).toBe("Draft recipe");
});
