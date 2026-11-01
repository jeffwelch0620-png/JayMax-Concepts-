import React, { act } from "react";
import { createRoot } from "react-dom/client";
import { AcceptanceQueue } from "./AcceptanceQueue";
import * as api from "../lib/api";

jest.mock("../lib/api", () => ({ __esModule: true, acceptanceQueue: jest.fn(), staffPrepProductionEnabled: true, staffPrepCountsEnabled: true }));
jest.mock("../lib/calc", () => ({ todayISO: () => "2026-11-01" }));
jest.mock("./StaffPrepProduction", () => ({ StaffProductionDecisions: p => <div data-testid={`decisions-${p.track}`} /> }));
jest.mock("./StaffPrepCounts", () => ({ StaffPrepCountReview: () => <div data-testid="prep-count-review" /> }));
let root, container;
beforeEach(() => { global.IS_REACT_ACT_ENVIRONMENT = true; root = createRoot(container = document.createElement("div")); document.body.appendChild(container); jest.clearAllMocks(); });
afterEach(async () => { await act(async () => root.unmount()); container.remove(); });
const q = id => container.querySelector(`[data-testid="${id}"]`);
const queue = changes => ({ store_id: "berts", day: "2026-11-01", can_accept: true, can_send_back: false,
  waiting: { output: 1, prep_counts: 0, nightly_counts: 0 },
  output: [{ id: "s1", staff_name: "Invented cook A", task_name: "Invented marinara", track: "daily", recorded_at: "2026-11-01T15:00:00Z", identity_verified: true }],
  prep_counts: [], nightly_counts: [], shortages: [], ...changes });

test("a Shift Leader sees what's waiting, can accept, and is told who sends work back", async () => {
  api.acceptanceQueue.mockResolvedValue(queue());
  await act(async () => root.render(<AcceptanceQueue rid="berts" />));
  expect(api.acceptanceQueue).toHaveBeenCalledWith("berts", "2026-11-01");
  expect(q("queue-summary").textContent).toBe("1 output report · 0 prep counts · 0 nightly counts");
  expect(container.textContent).toContain("Sending work back or reassigning a task needs a Kitchen Manager");
  expect(q("queue-output").textContent).toContain("Invented cook A · Invented marinara");
  expect(q("decisions-daily")).not.toBeNull();            // decided on its own review
  expect(q("prep-count-review")).toBeNull();              // no prep counts waiting
});

test("shortage notes are shown beside the work, and nothing waiting says so", async () => {
  api.acceptanceQueue.mockResolvedValue(queue({ can_send_back: true, waiting: { output: 0, prep_counts: 0, nightly_counts: 0 }, output: [],
    shortages: [{ id: "r1", staff_name: "Invented cook B", reason: "equipment", note: "Invented slicer down", short_quantity: "2",
      task_snapshot: { name: "Invented onions", source_unit: "qt" }, reported_at: "2026-11-01T16:00:00Z" }] }));
  await act(async () => root.render(<AcceptanceQueue rid="berts" />));
  expect(q("queue-summary").textContent).toBe("Nothing waiting.");
  expect(q("queue-shortages").textContent).toContain("Invented cook B · Invented onions: Equipment problem (2 qt short). Invented slicer down");
  expect(container.textContent).toContain("You can accept work, send it back and reassign tasks.");
});

test("a queue for another date is not shown", async () => {
  api.acceptanceQueue.mockResolvedValue(queue({ day: "2026-10-31" }));
  await act(async () => root.render(<AcceptanceQueue rid="berts" />));
  expect(q("queue-summary")).toBeNull();
  expect(container.querySelector('[role="alert"]').textContent).toContain("not confirmed");
});
