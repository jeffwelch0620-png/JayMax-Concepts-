import React, { act } from "react";
import { createRoot } from "react-dom/client";
import { PreparedBatchLedger } from "./PreparedBatchLedger";
import * as api from "../lib/api";
jest.mock("../lib/api");

let root, container;
const recipe = { id: "recipe", revision: 1, outputUnit: "lb", reviewNeeded: false, review_snapshot: { product: { name: "Prepared protein" } },
  lines: [{ id: "line", source_kind: "raw", raw_item_code: "protein", source_unit: "lb", factor: "1" }] };
const data = { recipes: [recipe], events: [], lots: [], policy: null };
const coverage = { waste: "not_installed", containers: "not_installed", tasks: "not_installed", staffProduction: "not_installed", periods: "not_installed" };
const preview = (rid, body) => Promise.resolve({ reviewHash: "hash", review: { kind: "initial", business_date: body.business_date, timezone_name: body.timezone_name,
  usableBaseOutput: body.output_quantity, standardBaseOutput: "48", base_unit: "lb", inputs: body.inputs.map(x => ({ ...x, base_quantity: x.quantity,
    base_unit: "lb", standardBaseQuantity: "60", includedLossBaseQuantity: x.included_loss_quantity })) } });
const button = text => [...container.querySelectorAll("button")].find(x => x.textContent === text);
const click = async x => { await act(async () => x.click()); };
const input = async (label, value) => {
  const el = container.querySelector(`[aria-label="${label}"]`);
  await act(async () => { Object.getOwnPropertyDescriptor(el.tagName === "SELECT" ? HTMLSelectElement.prototype : HTMLInputElement.prototype, "value").set.call(el, value); el.dispatchEvent(new Event(el.tagName === "SELECT" ? "change" : "input", { bubbles: true })); });
};
const render = async () => { await act(async () => root.render(<PreparedBatchLedger restaurantId="berts" />)); };
beforeEach(() => {
  jest.clearAllMocks(); global.IS_REACT_ACT_ENVIRONMENT = true;
  Object.defineProperty(global, "crypto", { configurable: true, value: { randomUUID: jest.fn(() => "batch-key") } });
  api.nativePrepBatchSetup.mockResolvedValue(data); api.previewNativePrepBatch.mockImplementation(preview);
  api.saveNativePrepBatch.mockResolvedValue({ event: { id: "batch", store_id: "berts", kind: "initial", review_hash: "hash", predecessor_id: null } });
  container = document.createElement("div"); document.body.appendChild(container); root = createRoot(container);
});
afterEach(async () => { await act(async () => root.unmount()); container.remove(); });
async function form() {
  await render(); await input("Approved recipe", "recipe"); await input("Planned recipe batches", "1"); await input("Measured usable output (lb)", "48");
  await input("Prepared at (ISO timestamp with offset)", "2026-10-05T10:00:00-04:00"); await input("Preparation calendar date (YYYY-MM-DD)", "2026-10-05");
  await input("Location timezone (for example America/New_York)", "America/New_York"); await input("Batch evidence / note", "Measured output");
  await input("Gross input 1", "60"); await input("Input basis 1", "measured"); await input("Input evidence 1", "Scale measurement");
  const boxes = container.querySelectorAll('input[type="checkbox"]'); await click(boxes[0]); await click(boxes[1]);
}
async function approve() { await click(button("Review batch quantities")); await click(container.querySelector('[aria-label="Batch quantity review"] input[type="checkbox"]')); }

test("measurements and timezone have no guessed values", async () => {
  await render(); await input("Approved recipe", "recipe");
  expect(container.querySelector('[aria-label="Gross input 1"]').value).toBe("");
  expect(container.querySelector('[aria-label="Measured usable output (lb)"]').value).toBe("");
  expect(container.querySelector('[aria-label="Location timezone (for example America/New_York)"]').value).toBe("");
  expect(api.saveNativePrepBatch).not.toHaveBeenCalled(); expect(container.textContent).toContain("Physical prep counts");
});
test("unknown trim stays null and saving requires a reviewed preview", async () => {
  await form(); await click(button("Review batch quantities"));
  expect(api.previewNativePrepBatch.mock.calls[0][1].inputs[0].included_loss_quantity).toBeNull();
  expect(button("Save reviewed batch").disabled).toBe(true); expect(container.textContent).toContain("Included loss: unknown");
  await click(container.querySelector('[aria-label="Batch quantity review"] input[type="checkbox"]')); await click(button("Save reviewed batch"));
  expect(api.saveNativePrepBatch.mock.calls[0][1].batch.inputs[0].measurement_basis).toBe("measured"); expect(container.textContent).toContain("Batch journal saved");
});
test("included trim and very precise quantities retain the entered decimal strings", async () => {
  await form(); await input("Gross input 1", "60.000000000001"); await input("Included trim/loss 1 (blank means unknown)", "12.000000000001"); await input("Loss evidence 1", "Included trim"); await approve();
  await click(button("Save reviewed batch")); const x = api.saveNativePrepBatch.mock.calls[0][1].batch.inputs[0];
  expect(x.quantity).toBe("60.000000000001"); expect(x.included_loss_quantity).toBe("12.000000000001");
});
test("editing invalidates an old review", async () => {
  await form(); await approve(); await input("Gross input 1", "61"); expect(button("Save reviewed batch")).toBeUndefined(); expect(api.saveNativePrepBatch).not.toHaveBeenCalled();
});
test("uncertain save freezes editing and refresh, then retries exactly the same key and body", async () => {
  api.saveNativePrepBatch.mockRejectedValueOnce(new Error("Connection lost")); await form(); await approve(); await click(button("Save reviewed batch"));
  expect(container.querySelector('[aria-label="Gross input 1"]').closest('fieldset[disabled]')).not.toBeNull();
  expect(button("Refresh batch setup").disabled).toBe(true); await click(button("Retry same batch record"));
  expect(api.saveNativePrepBatch.mock.calls[1]).toEqual(api.saveNativePrepBatch.mock.calls[0]); expect(container.textContent).toContain("Batch journal saved");
});
test("wrong acknowledgment retains exact retry, and definite stale response requires new review", async () => {
  api.saveNativePrepBatch.mockResolvedValueOnce({ event: { id: "wrong", store_id: "rudds", kind: "initial", review_hash: "hash" } });
  await form(); await approve(); await click(button("Save reviewed batch")); expect(container.textContent).toContain("Saved batch was not confirmed");
  api.saveNativePrepBatch.mockRejectedValueOnce({ response: { status: 409, data: { detail: "Sources changed" } } }); await click(button("Retry same batch record"));
  expect(button("Save reviewed batch")).toBeUndefined(); expect(button("Review batch quantities").disabled).toBe(false);
});
test("prepared inputs require a recorded lot and preserve its source identity", async () => {
  api.nativePrepBatchSetup.mockResolvedValue({ ...data, recipes: [{ ...recipe, lines: [{ id: "line", source_kind: "prepared", source_unit: "lb", factor: "1", source_snapshot: { recipe: { product_id: "protein" } } }] }],
    lots: [{ id: "source", product_id: "protein", base_unit: "lb", remainingRecordedQuantity: "28" }, { id: "other", product_id: "other", base_unit: "lb", remainingRecordedQuantity: "80" }] });
  await form(); const select = container.querySelector('[aria-label="Prepared source lot 1"]'); expect(select.options.length).toBe(2); expect(select.value).toBe("");
  await input("Prepared source lot 1", "source"); await approve(); await click(button("Save reviewed batch")); expect(api.saveNativePrepBatch.mock.calls[0][1].batch.inputs[0].source_batch_id).toBe("source");
});
test("void records use a reason and independent review without new quantities", async () => {
  api.nativePrepCorrectionReview.mockResolvedValue({ store_id: "berts", selectedEventId: "old", readOnly: true, track1Writeback: false,
    gate: { status: "eligible_for_preview", reason: "Review the correction" }, coverage, reviewHash: "a".repeat(64),
    lots: [], preparedInputHistory: [], containers: [], wasteHistory: [], taskLinks: [], staffDecisions: [], savedPeriods: [] });
  api.nativePrepBatchSetup.mockResolvedValue({ ...data, events: [{ id: "old", root_id: "root", kind: "initial", revision: 1, business_date: "2026-10-05", review_snapshot: { batch: null } }] });
  api.previewNativePrepBatchChange.mockResolvedValue({ reviewHash: "void-hash", review: { kind: "void", business_date: "2026-10-05", timezone_name: "America/New_York", usableBaseOutput: null, inputs: [] } });
  api.saveNativePrepBatchChange.mockResolvedValue({ event: { id: "new", store_id: "berts", kind: "void", predecessor_id: "old", review_hash: "void-hash" } });
  await render(); await input("Record action", "void"); await input("Current batch", "old"); await input("Correction reason", "Entered in error"); await approve(); await click(button("Save reviewed batch"));
  expect(api.saveNativePrepBatchChange.mock.calls[0]).toEqual(["berts", "old", { change: { kind: "void", reason: "Entered in error", replacement: null }, expected_review_hash: "void-hash", reviewed: true }, "batch-key"]);
});

test("a held dependency review keeps the proposed batch correction unavailable", async () => {
  api.nativePrepBatchSetup.mockResolvedValue({ ...data, events: [{ id: "old", kind: "initial", review_snapshot: { batch: null } }] });
  api.nativePrepCorrectionReview.mockResolvedValue({ store_id: "berts", selectedEventId: "old", readOnly: true, track1Writeback: false,
    gate: { status: "held", reason: "Measured waste uses this lot" }, coverage, reviewHash: "a".repeat(64),
    lots: [], preparedInputHistory: [], containers: [], wasteHistory: [], taskLinks: [], staffDecisions: [], savedPeriods: [] });
  await render(); await input("Record action", "void"); await input("Current batch", "old");
  expect(button("Review batch quantities").disabled).toBe(true); expect(container.textContent).toContain("Measured waste uses this lot");
  expect(api.previewNativePrepBatchChange).not.toHaveBeenCalled(); expect(api.saveNativePrepBatchChange).not.toHaveBeenCalled();
});

test("dependency refresh failure removes the earlier quantity approval and retains the correction reason", async () => {
  api.nativePrepBatchSetup.mockResolvedValue({ ...data, events: [{ id: "old", kind: "initial", review_snapshot: { batch: null } }] });
  api.nativePrepCorrectionReview.mockResolvedValueOnce({ store_id: "berts", selectedEventId: "old", readOnly: true, track1Writeback: false,
    gate: { status: "eligible_for_preview", reason: "Review quantities" }, coverage, reviewHash: "a".repeat(64),
    lots: [], preparedInputHistory: [], containers: [], wasteHistory: [], taskLinks: [], staffDecisions: [], savedPeriods: [] }).mockRejectedValueOnce(new Error("Dependency refresh unavailable"));
  api.previewNativePrepBatchChange.mockResolvedValue({ reviewHash: "void-hash", review: { kind: "void", inputs: [], usableBaseOutput: null } });
  await render(); await input("Record action", "void"); await input("Current batch", "old"); await input("Correction reason", "Keep this explanation"); await approve();
  await click(button("Refresh dependency review")); expect(button("Save reviewed batch")).toBeUndefined(); expect(button("Review batch quantities").disabled).toBe(true);
  expect(container.querySelector('[aria-label="Correction reason"]').value).toBe("Keep this explanation"); expect(api.saveNativePrepBatchChange).not.toHaveBeenCalled();
});
