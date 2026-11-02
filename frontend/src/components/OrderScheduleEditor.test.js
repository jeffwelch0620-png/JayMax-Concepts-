import React, { act } from "react";
import { createRoot } from "react-dom/client";
import { OrderScheduleEditor } from "./OrderScheduleEditor";
import * as api from "../lib/api";

jest.mock("../lib/api", () => ({ __esModule: true, changeOrderSchedule: jest.fn() }));
let root, container, keys;
beforeEach(() => {
  global.IS_REACT_ACT_ENVIRONMENT = true; keys = 0;
  Object.defineProperty(global, "crypto", { configurable: true, value: { randomUUID: () => `key-${++keys}` } });
  root = createRoot(container = document.createElement("div")); document.body.appendChild(container); jest.clearAllMocks();
});
afterEach(async () => { await act(async () => root.unmount()); container.remove(); });
const q = id => container.querySelector(`[data-testid="${id}"]`);
const button = t => [...container.querySelectorAll("button")].find(b => b.textContent === t);
const click = el => act(async () => el.click());
async function set(label, value) {
  const e = container.querySelector(`[aria-label="${label}"]`);
  const proto = e.tagName === "SELECT" ? HTMLSelectElement.prototype : HTMLInputElement.prototype;
  await act(async () => { Object.getOwnPropertyDescriptor(proto, "value").set.call(e, value); e.dispatchEvent(new Event(e.tagName === "SELECT" ? "change" : "input", { bubbles: true })); });
}
const schedule = (extra = {}) => ({ can_edit: true, ready: true, vendors: [{ id: "pfg", name: "PFG" }, { id: "us_foods", name: "US Foods" }],
  days: [{ order_weekday: 3, count_due: "12:00", order_due: "15:00", count_due_label: "12:00 PM", order_due_label: "3:00 PM", delivery_weekday: 4, vendor_ids: ["us_foods"] }],
  upcoming: [{ cycle_date: "2026-11-26", change: null, moved_to: null, delivery_date: "2026-11-27", reason: null },
             { cycle_date: "2026-12-03", change: "skip", moved_to: null, delivery_date: "2026-12-04", reason: "Inventory day" }], ...extra });
const render = (s = schedule(), onChanged = jest.fn()) => act(async () => root.render(<OrderScheduleEditor rid="berts" schedule={s} onChanged={onChanged} />));

test("hidden from anyone but an owner or the Ops Lead", async () => {
  await render(schedule({ can_edit: false }));
  expect(container.textContent).toBe("");
});

test("skip needs a reason; a lost reply retries with the same key; then it reloads", async () => {
  const onChanged = jest.fn();
  api.changeOrderSchedule.mockRejectedValueOnce(new Error("Network Error")).mockResolvedValue({});
  await render(schedule(), onChanged);
  await click(q("schedule-open"));
  expect(q("schedule-days").textContent).toContain("Thursday: count by 12:00 PM, order by 3:00 PM, delivery Friday · US Foods");
  expect(q("schedule-upcoming").textContent).toContain("skipped (Inventory day)");
  await click(button("Skip"));
  expect(api.changeOrderSchedule).not.toHaveBeenCalled();
  expect(container.querySelector('[role="alert"]').textContent).toContain("Say why");
  await set("Reason for the schedule change", "Thanksgiving");
  await click(button("Skip")); await click(button("Skip"));
  expect(api.changeOrderSchedule.mock.calls.map(c => [c[1], c[2]])).toEqual([
    [{ kind: "skip", cycle_date: "2026-11-26", reason: "Thanksgiving" }, "key-1"], [{ kind: "skip", cycle_date: "2026-11-26", reason: "Thanksgiving" }, "key-1"]]);
  expect(onChanged).toHaveBeenCalledTimes(1);
});

test("move a cycle with its delivery date, put one back, and set a weekly day", async () => {
  api.changeOrderSchedule.mockResolvedValue({});
  await render();
  await click(q("schedule-open"));
  await set("Reason for the schedule change", "Thanksgiving");
  await click(button("Move…"));
  await set("New order date", "2026-11-25");
  await click(button("Save move"));
  expect(api.changeOrderSchedule.mock.calls[0][1]).toEqual({ kind: "move", cycle_date: "2026-11-26", moved_to: "2026-11-25", delivery_date: "2026-11-27", reason: "Thanksgiving" });
  await set("Reason for the schedule change", "Open after all");
  await click(button("Put back"));
  expect(api.changeOrderSchedule.mock.calls[1][1]).toEqual({ kind: "restore", cycle_date: "2026-12-03", reason: "Open after all" });
  await set("Reason for the schedule change", "PFG adds Mondays");
  await set("Order day", "0"); await set("Delivery day", "1");
  expect(button("Save order day").disabled).toBe(true);                  // a supplier is still needed
  await click(container.querySelector('[aria-label="Supplier PFG"]'));
  await click(button("Save order day"));
  expect(api.changeOrderSchedule.mock.calls[2][1]).toEqual({ kind: "set_day", order_weekday: 0, count_due: "12:00", order_due: "15:00", delivery_weekday: 1, vendor_ids: ["pfg"], reason: "PFG adds Mondays" });
});
