import React, { act } from "react";
import { createRoot } from "react-dom/client";
import { PrepCorrectionReview } from "./PrepCorrectionReview";
import * as api from "../lib/api";
jest.mock("../lib/api");

let root, container, onResult;
const result = (store = "berts", id = "batch") => ({ store_id: store, selectedEventId: id, readOnly: true, track1Writeback: false,
  reviewHash: "a".repeat(64), gate: { status: "held", reason: "Waste uses this output" }, coverage: { waste: "installed", containers: "installed", tasks: "not_installed", staffProduction: "not_installed", periods: "installed" },
  lots: [{ id, kind: "initial", revision: 1, recordedAllocatedQuantity: ".25", base_unit: "lb" }], preparedInputHistory: [],
  containers: [{ fill: { id: "fill", label: "Sauce pan", base_unit: "lb" }, storage: "1.75", service: "0", moves: [{ id: "move", action: "waste", performed_at: "2026-10-08" }], nextPreviewAction: "undo_waste", reviewNote: "Use paired reversal" }],
  wasteHistory: [{ id: "loss", kind: "initial", current: true }], taskLinks: [{ id: "link", task_id: "task", needsReconciliation: true, reconciliationSupported: true }],
  staffDecisions: [{ id: "accepted" }], savedPeriods: [{ id: "period", reopened: false, freshness: { status: "stale" }, effect: "Reopen affected and following periods" }] });
const render = async (store = "berts", id = "batch") => { await act(async () => root.render(<PrepCorrectionReview restaurantId={store} eventId={id} onResult={onResult} />)); };
const refresh = async () => { await act(async () => container.querySelector("button").click()); };
beforeEach(() => { jest.resetAllMocks(); global.IS_REACT_ACT_ENVIRONMENT = true; onResult = jest.fn(); container = document.createElement("div"); document.body.appendChild(container); root = createRoot(container); });
afterEach(async () => { await act(async () => root.unmount()); container.remove(); });
test("shows holds, paired waste, task reconciliation and stale periods without a write", async () => {
  api.nativePrepCorrectionReview.mockResolvedValue(result()); await render();
  expect(container.textContent).toContain("Waste uses this output"); expect(container.textContent).toContain("paired waste reversal");
  expect(container.textContent).toContain("reconciliation needed now"); expect(container.textContent).toContain("stale");
  expect(container.textContent).toContain("Track 1 purchased inventory and Food Cost remain unchanged");
  expect(api.saveNativePrepBatchChange).not.toHaveBeenCalled(); expect(onResult.mock.calls.at(-1)[0].restaurantId).toBe("berts");
});
test("failed refresh clears old dependency evidence and can be retried", async () => {
  api.nativePrepCorrectionReview.mockResolvedValueOnce(result()).mockRejectedValueOnce(new Error("Connection lost")).mockResolvedValueOnce(result());
  await render(); await refresh(); expect(container.textContent).toContain("Connection lost"); expect(container.textContent).not.toContain("Sauce pan");
  expect(onResult.mock.calls.at(-1)).toEqual([null]); await refresh(); expect(container.textContent).toContain("Sauce pan");
});
test("wrong location or record acknowledgment never enables a correction", async () => {
  api.nativePrepCorrectionReview.mockResolvedValue(result("rudds")); await render();
  expect(container.textContent).toContain("was not confirmed"); expect(onResult.mock.calls.at(-1)).toEqual([null]);
});
test("late response from a former location cannot replace the active failure", async () => {
  let release; api.nativePrepCorrectionReview.mockImplementationOnce(() => new Promise(resolve => { release = resolve; })).mockRejectedValueOnce(new Error("Rudds unavailable"));
  await render(); await render("rudds", "other"); await act(async () => release(result()));
  expect(container.textContent).toContain("Rudds unavailable"); expect(container.textContent).not.toContain("Sauce pan"); expect(onResult.mock.calls.at(-1)).toEqual([null]);
});
test("malformed journal coverage is held instead of becoming correction evidence", async () => {
  api.nativePrepCorrectionReview.mockResolvedValue({ ...result(), coverage: { containers: false } }); await render();
  expect(container.textContent).toContain("was not confirmed"); expect(onResult.mock.calls.at(-1)).toEqual([null]);
});

test("missing journal coverage cannot become correction evidence", async () => {
  const incomplete = result(); delete incomplete.coverage.waste;
  api.nativePrepCorrectionReview.mockResolvedValue(incomplete); await render();
  expect(container.textContent).toContain("was not confirmed"); expect(onResult.mock.calls.at(-1)).toEqual([null]);
});

test("malformed container movements are held before rendering or approving a correction", async () => {
  const malformed = result(); malformed.containers[0].moves = null;
  api.nativePrepCorrectionReview.mockResolvedValue(malformed); await render();
  expect(container.textContent).toContain("was not confirmed"); expect(onResult.mock.calls.at(-1)).toEqual([null]);
  expect(container.textContent).not.toContain("Sauce pan");
});
