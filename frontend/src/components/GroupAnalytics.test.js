import React, { act } from "react";
import { createRoot } from "react-dom/client";
import { GroupAnalytics } from "./GroupAnalytics";
import * as api from "../lib/api";

jest.mock("../lib/api", () => ({ analyticsSummary: jest.fn() }));

const sales = over => ({ available: true, net_sales: "7000.00", orders: 350, average_check: "20.00", days: 7, range_days: 7, before_net_sales: "6500.00",
  compared_days: 7, latest_day: "2026-11-06", stale: false, missing_days: 0, needs_review: 0, ...over });
const summary = { start: "2026-10-31", end: "2026-11-06", timezone_name: "America/New_York", stores: [
  { store_id: "berts", sales: sales(), waste: { available: true, entries: 4, items: 3 },
    prep_vs_sales: { available: true, covered_percent: 80, missing_count: 2, largest_gap: { name: "Invented fries", unit: "lb", gap: "14", gap_percent: 44 } } },
  { store_id: "rudds", sales: sales({ before_net_sales: null, compared_days: 0, missing_days: 2 }), waste: { available: true, entries: 1, items: 1 },
    prep_vs_sales: { available: true, covered_percent: null, missing_count: 1, largest_gap: null } },
  { store_id: "papa", sales: { available: false }, waste: { available: false }, prep_vs_sales: { available: false } }] };

async function render(ui) {
  global.IS_REACT_ACT_ENVIRONMENT = true;
  const container = document.createElement("div"); document.body.appendChild(container);
  const root = createRoot(container);
  await act(async () => root.render(ui));
  return { container, done: async () => { await act(async () => root.unmount()); container.remove(); } };
}
const text = (c, id) => c.querySelector(`[data-testid="${id}"]`).textContent;

test("each store's last 7 days: sales against the week before, Toast freshness, waste and prep against sales", async () => {
  api.analyticsSummary.mockResolvedValue(summary);
  const onOpen = jest.fn();
  const { container, done } = await render(<GroupAnalytics onOpenLocation={onOpen} />);
  try {
    expect(text(container, "group-analytics")).toContain("2026-10-31 to 2026-11-06");
    expect(text(container, "group-sales-berts")).toBe("$7,000");
    expect(text(container, "group-store-berts")).toContain("+8% against the 7 days before");
    expect(text(container, "group-gap-berts")).toContain("Invented fries +14 lb (+44%)");
    expect(text(container, "group-store-berts")).toContain("4 records on 3 items");
    expect(text(container, "group-toast-berts")).toContain("Every day arrived from Toast");
    expect(text(container, "group-store-rudds")).toContain("No complete stretch before to compare");
    expect(text(container, "group-toast-rudds")).toContain("2 days not arrived from Toast");
    expect(text(container, "group-gap-rudds")).toContain("None to show");
    expect(text(container, "group-store-papa")).toContain("Sales are not set up for this store yet.");
    await act(async () => container.querySelector('[data-testid="group-store-papa"] button').click());
    expect(onOpen).toHaveBeenCalledWith("papa_leonis");
  } finally { await done(); }
});

test("early in the morning the week isn't called whole while yesterday is still due", async () => {
  api.analyticsSummary.mockResolvedValue({ ...summary, stores: [{ ...summary.stores[0], sales: sales({ days: 6 }) }] });
  const { container, done } = await render(<GroupAnalytics />);
  try {
    expect(text(container, "group-toast-berts")).toContain("6 of 7 days in; the newest isn't due from Toast yet");
  } finally { await done(); }
});

test("a refused or failed summary says so", async () => {
  api.analyticsSummary.mockRejectedValue({ response: { data: { detail: "Analytics is visible to the General Manager and above" } } });
  const { container, done } = await render(<GroupAnalytics />);
  try {
    expect(text(container, "group-analytics-error")).toContain("General Manager and above");
  } finally { await done(); }
});
