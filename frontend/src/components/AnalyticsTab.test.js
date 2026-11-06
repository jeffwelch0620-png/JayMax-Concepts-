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
