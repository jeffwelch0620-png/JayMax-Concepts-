import React, { act } from "react";
import { createRoot } from "react-dom/client";
import { BulkQuickCount } from "./BulkQuickCount";
import { BulkSupply } from "./BulkSupply";
import * as api from "../lib/api";

jest.mock("../lib/api", () => ({ __esModule: true, bulkQuickCount: jest.fn(), saveBulkQuickCount: jest.fn(), bulkSupply: jest.fn(), prepPlanning: jest.fn(), previewBulkRequest: jest.fn(), sendBulkRequest: jest.fn() }));
const item = { product_id: "ranch", profile_id: "u-ranch", name: "Invented ranch", base_unit: "qt", source_unit: "bucket", factor: "4" };
const read = (changes = {}) => ({ store_id: "berts", business_date: "2026-10-09", par_mode: "daily", maker_store_id: "rudds", days_before_next_run: [5, 6], next_run: "2026-10-12", revision: 0, items: [item], counts: [], check: null, ...changes });
const checked = (short = "36", spot = "9") => read({ revision: 1, counts: [{ id: "c1", revision: 1, lines: [{ product_id: "ranch", quantity: "4", factor: "4.000" }] }],
  check: [{ product_id: "ranch", name: "Invented ranch", base_unit: "qt", source_unit: "bucket", need_base_quantity: "52", counted_base_quantity: "16", incoming_base_quantity: "0", short_base_quantity: short, spot_quantity: spot }] });
let root, container, onSpot;
beforeEach(() => {
  global.IS_REACT_ACT_ENVIRONMENT = true; Object.defineProperty(global, "crypto", { configurable: true, value: { randomUUID: () => "stable-key" } });
  root = createRoot(container = document.createElement("div")); document.body.appendChild(container); jest.clearAllMocks(); onSpot = jest.fn();
});
afterEach(async () => { await act(async () => root.unmount()); container.remove(); });
const render = el => act(async () => root.render(el));
const click = el => act(async () => el.click());
const button = text => [...container.querySelectorAll("button")].find(b => b.textContent === text);
const field = label => container.querySelector(`[aria-label="${label}"]`);
async function input(label, value) { const el = field(label); await act(async () => { Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value").set.call(el, value); el.dispatchEvent(new Event("input", { bubbles: true })); }); }

test("a quick count sends every Bulk item with the night, version and one key, then shows the check", async () => {
  api.bulkQuickCount.mockResolvedValue(read());
  await render(<BulkQuickCount rid="berts" onSpot={onSpot} />); await input("Quick count night", "2026-10-09");
  expect(api.bulkQuickCount).toHaveBeenLastCalledWith("berts", "2026-10-09");
  expect(button("Save count").disabled).toBe(true);
  await input("Quick count Invented ranch", "4"); await input("Quick count note", "Invented closer");
  api.saveBulkQuickCount.mockResolvedValue({ ...checked(), request_key: "stable-key", replayed: false });
  await click(button("Save count"));
  const [rid, body, version, key] = api.saveBulkQuickCount.mock.calls[0];
  expect([rid, body.business_date, body.note, body.lines, version, key]).toEqual(["berts", "2026-10-09", "Invented closer", [{ product_id: "ranch", profile_id: "u-ranch", quantity: "4" }], 0, "stable-key"]);
  expect(container.textContent).toContain("Days left before the Mon 2026-10-12 run: Sat, Sun.");
  expect(container.textContent).toContain("36 qt");
  await click(button("Fill in a spot request for review"));
  expect(onSpot).toHaveBeenCalledWith([{ product_id: "ranch", quantity: "9", reason: "Quick count 2026-10-09: short before the 2026-10-12 run" }], "2026-10-10");
});

test("a lost response keeps the exact count for retry, and a refusal releases it", async () => {
  api.bulkQuickCount.mockResolvedValue(read());
  await render(<BulkQuickCount rid="berts" onSpot={onSpot} />); await input("Quick count night", "2026-10-09");
  await input("Quick count Invented ranch", "4"); await input("Quick count note", "Invented closer");
  api.saveBulkQuickCount.mockRejectedValueOnce(new Error("Lost response"));
  await click(button("Save count"));
  expect(field("Quick count Invented ranch").closest("fieldset").disabled).toBe(true);
  api.saveBulkQuickCount.mockRejectedValueOnce({ response: { status: 409, data: { detail: "Quick Bulk count changed. Refresh before correcting." } } });
  await click(button("Retry the same count"));
  expect(api.saveBulkQuickCount.mock.calls[1]).toEqual(api.saveBulkQuickCount.mock.calls[0]);
  expect(container.textContent).toContain("Refresh before correcting");
  expect(button("Save count")).toBeDefined();
});

test("a saved count is shown for correction, and the Bulk kitchen is told to make its own spot prep", async () => {
  api.bulkQuickCount.mockResolvedValue({ ...checked(), maker_store_id: null });
  await render(<BulkQuickCount rid="rudds" onSpot={onSpot} />);
  expect(field("Quick count Invented ranch").value).toBe("4");
  expect(button("Save corrected count")).toBeDefined();
  expect(container.textContent).toContain("Spot prep needed before the Mon run: Invented ranch 9 bucket.");
  expect(button("Fill in a spot request for review")).toBeUndefined();
});

test("weekday / weekend pars keep the count without a check, and no shortfall needs no spot prep", async () => {
  api.bulkQuickCount.mockResolvedValue(read({ par_mode: "window", revision: 1 }));
  await render(<BulkQuickCount rid="berts" onSpot={onSpot} />);
  expect(container.textContent).toContain("so the count is kept without a check");
  api.bulkQuickCount.mockResolvedValue(checked("0", "0"));
  await render(<BulkQuickCount key="again" rid="berts" onSpot={onSpot} />);
  expect(container.textContent).toContain("No spot prep needed before the next run.");
});

test("the spot request form opens filled in from the check, for review before sending", async () => {
  api.bulkSupply.mockResolvedValue({ store_id: "berts", maker_store_id: "rudds", makes_for: [], requests: [], open_shortfalls: [] });
  api.prepPlanning.mockResolvedValue({ products: [{ product_id: "ranch", name: "Invented ranch" }], unitProfiles: [{ id: "u", source_unit: "bucket" }], plans: [{ product_id: "ranch", active: true, track: "bulk", unit_profile_id: "u" }] });
  api.bulkQuickCount.mockResolvedValue(checked());
  await render(<BulkSupply rid="berts" />);
  await click(button("Quick Bulk count")); await input("Quick count night", "2026-10-09");
  await click(button("Fill in a spot request for review"));
  expect(field("Spot amount 1").value).toBe("9");
  expect(field("Spot needed by").value).toBe("2026-10-10");
  expect(field("Spot reason 1").value).toContain("Quick count 2026-10-09");
  expect(api.sendBulkRequest).not.toHaveBeenCalled();
});

test("a stale-version refusal reloads the night's count and keeps what was typed", async () => {
  api.bulkQuickCount.mockResolvedValue(read());
  await render(<BulkQuickCount rid="berts" onSpot={onSpot} />); await input("Quick count night", "2026-10-09");
  await input("Quick count Invented ranch", "5"); await input("Quick count note", "Invented closer");
  api.bulkQuickCount.mockResolvedValue(checked());
  api.saveBulkQuickCount.mockRejectedValueOnce({ response: { status: 409, data: { detail: "Quick Bulk count changed. Refresh before correcting." } } });
  await click(button("Save count"));
  expect(container.textContent).toContain("Refresh before correcting");
  expect(field("Quick count Invented ranch").value).toBe("5");
  api.saveBulkQuickCount.mockResolvedValue({ ...checked(), revision: 2, request_key: "stable-key", replayed: false });
  await click(button("Save corrected count"));
  expect(api.saveBulkQuickCount.mock.calls[1][2]).toBe(1);
});
test("an item added after the count makes the check incomplete instead of saying no spot prep is needed", async () => {
  const data = checked("0", "0");
  data.check.push({ product_id: "slaw", name: "Invented slaw", base_unit: "qt", source_unit: "tub", counted: false, counted_base_quantity: null, incoming_base_quantity: null, need_base_quantity: null, short_base_quantity: null, spot_quantity: null });
  api.bulkQuickCount.mockResolvedValue(data);
  await render(<BulkQuickCount rid="berts" onSpot={onSpot} />);
  expect(container.textContent).toContain("Not in this count: Invented slaw.");
  expect(container.textContent).toContain("Not counted");
  expect(container.textContent).not.toContain("No spot prep needed before the next run.");
});

test("an unresolved count keeps the Bulk panel on its form so the retry key is not lost", async () => {
  api.bulkSupply.mockResolvedValue({ store_id: "berts", maker_store_id: "rudds", makes_for: [], requests: [], open_shortfalls: [] });
  api.bulkQuickCount.mockResolvedValue(read());
  await render(<BulkSupply rid="berts" />);
  await click(button("Quick Bulk count")); await input("Quick count night", "2026-10-09");
  await input("Quick count Invented ranch", "4"); await input("Quick count note", "Invented closer");
  api.saveBulkQuickCount.mockRejectedValueOnce(new Error("Lost response"));
  await click(button("Save count"));
  expect(button("Spot request").disabled).toBe(true);
  expect(button("Quick Bulk count").disabled).toBe(true);
  api.saveBulkQuickCount.mockResolvedValue({ ...checked(), request_key: "stable-key", replayed: true });
  await click(button("Retry the same count"));
  expect(button("Spot request").disabled).toBe(false);
});
test("a saved amount in a unit the item no longer uses is left blank to count fresh", async () => {
  const data = checked(); data.counts[0].lines[0].factor = "1";
  api.bulkQuickCount.mockResolvedValue(data);
  await render(<BulkQuickCount rid="berts" onSpot={onSpot} />);
  expect(field("Quick count Invented ranch").value).toBe("");
});