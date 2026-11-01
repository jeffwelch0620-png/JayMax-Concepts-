import React, { act } from "react";
import { createRoot } from "react-dom/client";
import { OrderCalendar } from "./OrderCalendar";
import * as api from "../lib/api";

jest.mock("../lib/api", () => ({ __esModule: true, orderCalendar: jest.fn(), recordLateCount: jest.fn() }));
let root, container, keys;
beforeEach(() => {
  global.IS_REACT_ACT_ENVIRONMENT = true; keys = 0;
  Object.defineProperty(global, "crypto", { configurable: true, value: { randomUUID: () => `key-${++keys}` } });
  root = createRoot(container = document.createElement("div")); document.body.appendChild(container); jest.clearAllMocks();
});
afterEach(async () => { await act(async () => root.unmount()); container.remove(); });
const render = () => act(async () => root.render(<OrderCalendar rid="berts" />));
const q = id => container.querySelector(`[data-testid="${id}"]`);
const button = t => [...container.querySelectorAll("button")].find(b => b.textContent === t);
async function type(label, value) { const e = container.querySelector(`[aria-label="${label}"]`); await act(async () => { Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value").set.call(e, value); e.dispatchEvent(new Event("input", { bubbles: true })); }); }

const view = (cal = {}, extra = {}) => ({ store_id: "berts", installed: true, can_create: true, can_approve: false, on_order: [], ...extra,
  calendar: { cycle_date: "2026-11-04", today: "2026-11-04", count_due_label: "12:00 PM", order_due_label: "3:00 PM", delivery_date: "2026-11-05",
    count: { status: "overdue", needs_reason: true }, notes: [],
    vendors: [{ vendor_id: "pfg", name: "PFG", status: "done", drafts: 0 }, { vendor_id: "us_foods", name: "US Foods", status: "overdue", drafts: 1 }], ...cal } });

test("shows today's cycle: count overdue, one order done, one overdue with a draft", async () => {
  api.orderCalendar.mockResolvedValue(view());
  await render();
  const text = q("order-calendar").textContent;
  expect(text).toContain("Today's order"); expect(text).toContain("count by 12:00 PM, orders by 3:00 PM");
  expect(q("order-calendar-steps").textContent).toBe("Count: OverduePFG order: DoneUS Foods order: Overdue · 1 draft not submitted");
});

test("a late count asks for a reason; a retry reuses its key", async () => {
  api.orderCalendar.mockResolvedValueOnce(view()).mockResolvedValue(view({ count: { status: "late", needs_reason: false }, notes: [{ kind: "count_late", reason: "Walk-in repair" }] }));
  api.recordLateCount.mockRejectedValueOnce(new Error("Network Error")).mockResolvedValue({});
  await render();
  await type("Why is the count late", "Walk-in repair");
  await act(async () => button("Save reason").click());
  await act(async () => button("Save reason").click());
  expect(api.recordLateCount.mock.calls.map(c => [c[1], c[2]])).toEqual([[{ cycle_date: "2026-11-04", reason: "Walk-in repair" }, "key-1"], [{ cycle_date: "2026-11-04", reason: "Walk-in repair" }, "key-1"]]);
  expect(q("late-count")).toBeNull();
  expect(q("order-calendar").textContent).toContain("Late count: Walk-in repair");
});

test("on-order list warns when a later count may already include the delivery", async () => {
  api.orderCalendar.mockResolvedValue(view({ count: { status: "upcoming", needs_reason: false } }, { on_order: [
    { ref: "po_1", vendor_name: "PFG", status: "sent", expected_delivery: "2026-11-02", maybe_counted: true, latest_count_date: "2026-11-02" },
    { ref: "po_2", vendor_name: "US Foods", status: "approved", expected_delivery: "2026-11-05", maybe_counted: false, latest_count_date: "2026-11-02" }] }));
  await render();
  const list = q("on-order").textContent;
  expect(list).toContain("PFG · sent · due Monday, Nov 2"); expect(list).toContain("Confirm its receipt so it isn't counted twice.");
  expect(list.match(/counted twice/g)).toHaveLength(1);
});

test("Papa's (no calendar) and a store before the migration", async () => {
  api.orderCalendar.mockResolvedValueOnce({ store_id: "berts", installed: true, calendar: null, on_order: [] });
  await render();
  expect(q("order-calendar").textContent).toContain("No order calendar is set for this location.");
  api.orderCalendar.mockResolvedValueOnce({ store_id: "berts", installed: false });
  await act(async () => button("Refresh").click());
  expect(q("order-calendar")).toBeNull();
});
