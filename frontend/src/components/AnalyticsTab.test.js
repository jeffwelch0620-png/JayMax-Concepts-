import React, { act } from "react";
import { createRoot } from "react-dom/client";
import { AnalyticsTab, isoDay } from "./AnalyticsTab";
import * as api from "../lib/api";

jest.mock("../lib/api", () => ({ analyticsReport: jest.fn() }));

const report = tasks => ({ throughput: { available: true, lists: { released: 1, not_released: 0 }, tasks, met_plan: tasks, short: 0, tracks: [], short_tasks: [] },
  shortages: { available: false }, waste: { available: false }, acceptance: {}, transfers: {}, on_time: { available: false } });

test("the default range uses the local calendar day, not UTC", () => {
  expect(isoDay(new Date(2026, 10, 6, 23, 30))).toBe("2026-11-06");   // 11:30 PM local is already Nov 7 in UTC west of Greenwich
  expect(isoDay(new Date(2026, 0, 2, 0, 5))).toBe("2026-01-02");
});

test("waste tiles name the waste category, not the manager's note", async () => {
  global.IS_REACT_ACT_ENVIRONMENT = true;
  api.analyticsReport.mockResolvedValue({ ...report(0), waste: { available: true, entries: 3, items: 2,
    by_reason: { storage_spoilage: 2, service_discard: 1 }, top_items: [] } });
  const container = document.createElement("div"); document.body.appendChild(container);
  const root = createRoot(container);
  try {
    await act(async () => root.render(<AnalyticsTab rid="berts" />));
    const text = container.querySelector('[data-testid="analytics-waste-section"]').textContent;
    expect(text).toContain("Storage spoilage");
    expect(text).toContain("Service discard");
    expect(text).not.toContain("storage_spoilage");
  } finally {
    await act(async () => root.unmount()); container.remove();
  }
});

test("sales show totals against the days before and say when Toast is behind", async () => {
  global.IS_REACT_ACT_ENVIRONMENT = true;
  api.analyticsReport.mockResolvedValue({ ...report(0), sales: { available: true,
    totals: { net_sales: "1100.00", orders: 50, average_check: "22.00", discounts: "10.00", refunds: "5.90", days: 2, open_days: 2 },
    before: { net_sales: "1000.00", orders: 50, average_check: "20.00", start: "2026-11-01", end: "2026-11-02", complete: true },
    by_day: [{ business_date: "2026-11-03", net_sales: "600.00", orders: 25, average_check: "24.00", status: "complete" },
      { business_date: "2026-11-04", net_sales: "500.00", orders: 25, average_check: "20.00", status: "needs review" }],
    top_items: [{ name: "Hamburger Steak", quantity: "12", net_sales: "180.00" }],
    salad_bar: { covers: "9", amount: "53.91", by_day: [{ business_date: "2026-11-03", quantity: "9", amount: "53.91" }] },
    latest_day: "2026-11-04", missing_days: ["2026-11-05"], stale: true,
    needs_review: [{ business_date: "2026-11-04", problems: ["refund without item detail"] }] } });
  const container = document.createElement("div"); document.body.appendChild(container);
  const root = createRoot(container);
  try {
    await act(async () => root.render(<AnalyticsTab rid="berts" />));
    const text = container.querySelector('[data-testid="analytics-sales-section"]').textContent;
    expect(container.querySelector('[data-testid="analytics-net-sales"]').textContent).toContain("$1,100.00");
    expect(container.querySelector('[data-testid="analytics-net-sales"]').textContent).toContain("+10% vs 2026-11-01 – 2026-11-02");
    expect(container.querySelector('[data-testid="analytics-average-check"]').textContent).toContain("$22.00");
    expect(container.querySelector('[data-testid="analytics-salad-covers"]').textContent).toContain("9");
    const health = container.querySelector('[data-testid="analytics-sales-health"]').textContent;
    expect(health).toContain("Toast sales are behind");
    expect(health).toContain("2026-11-05");
    expect(health).toContain("refund without item detail");
    expect(text).toContain("Hamburger Steak");
    expect(text).toContain("Needs review");
  } finally {
    await act(async () => root.unmount()); container.remove();
  }
});

test("no change is shown against incomplete earlier days", async () => {
  global.IS_REACT_ACT_ENVIRONMENT = true;
  api.analyticsReport.mockResolvedValue({ ...report(0), sales: { available: true,
    totals: { net_sales: "200.00", orders: 10, average_check: "20.00", discounts: "0", refunds: "0", days: 2, open_days: 2 },
    before: { net_sales: "100.00", orders: 5, average_check: "20.00", start: "2026-11-01", end: "2026-11-02", complete: false },
    by_day: [], top_items: [], salad_bar: { covers: "0", amount: "0", by_day: [] }, latest_day: "2026-11-04", missing_days: [], stale: false, needs_review: [] } });
  const container = document.createElement("div"); document.body.appendChild(container);
  const root = createRoot(container);
  try {
    await act(async () => root.render(<AnalyticsTab rid="berts" />));
    const tile = container.querySelector('[data-testid="analytics-net-sales"]').textContent;
    expect(tile).not.toContain("%");
    expect(tile).toContain("earlier days incomplete");
    expect(container.querySelector('[data-testid="analytics-average-check"]').textContent).not.toContain("before");
  } finally {
    await act(async () => root.unmount()); container.remove();
  }
});

test("a prep track shows sales as store-wide", async () => {
  global.IS_REACT_ACT_ENVIRONMENT = true;
  api.analyticsReport.mockResolvedValue({ ...report(0), sales: { available: true, store_wide: true } });
  const container = document.createElement("div"); document.body.appendChild(container);
  const root = createRoot(container);
  try {
    await act(async () => root.render(<AnalyticsTab rid="berts" />));
    expect(container.querySelector('[data-testid="analytics-sales-section"]').textContent).toContain("Store-wide");
  } finally {
    await act(async () => root.unmount()); container.remove();
  }
});

test("an older range answering late never replaces the newer one", async () => {
  global.IS_REACT_ACT_ENVIRONMENT = true;
  const pending = [];
  api.analyticsReport.mockImplementation(() => new Promise(resolve => pending.push(resolve)));
  const container = document.createElement("div"); document.body.appendChild(container);
  const root = createRoot(container);
  try {
    await act(async () => root.render(<AnalyticsTab rid="berts" />));
    const select = container.querySelector('[data-testid="analytics-track"]');
    await act(async () => {
      Object.getOwnPropertyDescriptor(HTMLSelectElement.prototype, "value").set.call(select, "bulk");
      select.dispatchEvent(new Event("change", { bubbles: true }));
    });
    expect(api.analyticsReport).toHaveBeenLastCalledWith("berts", expect.objectContaining({ track: "bulk" }));
    await act(async () => pending[1](report(2)));   // the Bulk answer first
    await act(async () => pending[0](report(9)));   // then the first, All tracks, request late
    expect(container.querySelector('[data-testid="analytics-tasks"]').textContent).toContain("2");
    expect(container.querySelector('[data-testid="analytics-tasks"]').textContent).not.toContain("9");
  } finally {
    await act(async () => root.unmount()); container.remove();
  }
});
