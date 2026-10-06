import React, { act } from "react";
import { createRoot } from "react-dom/client";
import { PrepObservations } from "./PrepObservations";
import * as api from "../lib/api";
jest.mock("../lib/api");

let root, container;
const data = { products: [{ id: "pv", product_id: "protein", name: "Prepared protein", base_unit: "lb" }, { id: "sv", product_id: "sauce", name: "Prepared sauce", base_unit: "gal" }],
  profiles: [{ id: "pu", product_version_id: "pv", source_unit: "lb", base_units_per_source_unit: "1" }, { id: "su", product_version_id: "sv", source_unit: "gal", base_units_per_source_unit: "1" }],
  rawItems: [{ code: "raw", name: "Purchased protein", base_unit: "lb" }, { code: "missing", name: "Needs unit review", base_unit: null }],
  lots: [{ id: "lot", product_id: "protein", base_unit: "lb", remainingRecordedQuantity: "43" }], events: [], policy: null };
const click = async el => { await act(async () => el.click()); };
const button = text => [...container.querySelectorAll("button")].find(x => x.textContent === text);
const input = async (label, value) => {
  const el = container.querySelector(`[aria-label="${label}"]`);
  await act(async () => { Object.getOwnPropertyDescriptor(el.tagName === "SELECT" ? HTMLSelectElement.prototype : HTMLInputElement.prototype, "value").set.call(el, value); el.dispatchEvent(new Event(el.tagName === "SELECT" ? "change" : "input", { bubbles: true })); });
};
const render = async () => { await act(async () => root.render(<PrepObservations restaurantId="berts" />)); };
beforeEach(() => {
  jest.clearAllMocks(); global.IS_REACT_ACT_ENVIRONMENT = true;
  Object.defineProperty(global, "crypto", { configurable: true, value: { randomUUID: jest.fn(() => "observation-key") } });
  api.nativePrepObservationSetup.mockResolvedValue(data);
  api.previewNativePrepObservation.mockImplementation(async (rid, purpose, body) => ({ reviewHash: "hash", review: { purpose, kind: "initial", business_date: body.business_date,
    baseQuantity: body.quantity || null, base_unit: body.source_unit, lines: (body.lines || []).map((l, i) => ({ ...l, product_id: data.products[i].product_id, base_quantity: l.quantity, base_unit: data.products[i].base_unit })) } }));
  api.saveNativePrepObservation.mockImplementation(async (rid, purpose) => ({ event: { id: "event", store_id: "berts", purpose, kind: "initial", review_hash: "hash", predecessor_id: null } }));
  container = document.createElement("div"); document.body.appendChild(container); root = createRoot(container);
});
afterEach(async () => { await act(async () => root.unmount()); container.remove(); });
async function time() {
  await input("Observed at (timestamp with offset)", "2026-10-05T12:00:00-04:00"); await input("Observation calendar date (YYYY-MM-DD)", "2026-10-05");
  await input("Location timezone", "America/New_York"); await input("Observation evidence / note", "Measured observation"); await click(container.querySelector('[aria-label="Confirm observation calendar day"]'));
}
async function waste() {
  await render(); await time(); await input("Purchased waste item", "raw"); await input("Measured waste quantity", "5"); await input("Waste category", "storage_spoilage"); await click(container.querySelector('[aria-label="Confirm separate waste"]'));
}
async function count() {
  await render(); await input("Observation journal", "count"); await time();
  await input("Count measurement 1", "pu"); await input("Physical prep quantity 1", "42"); await input("Count evidence 1", "Weighed protein");
  await input("Count measurement 2", "su"); await input("Physical prep quantity 2", "0"); await input("Count evidence 2", "Observed empty sauce stock"); await click(container.querySelector('[aria-label="Confirm full prep scope"]'));
}
async function approve() { await click(button("Review observation")); await click(container.querySelector('[aria-label="Confirm observation review"]')); }

test("unknown counts and waste are blank and unverified raw units are held", async () => {
  await render(); expect(container.querySelector('[aria-label="Measured waste quantity"]').value).toBe("");
  expect(container.querySelector('[aria-label="Purchased waste item"] option[value="missing"]').disabled).toBe(true);
  await input("Observation journal", "count"); expect(container.querySelector('[aria-label="Physical prep quantity 1"]').value).toBe("");
  expect(container.textContent).toContain("do not reset recorded batch balances"); expect(api.saveNativePrepObservation).not.toHaveBeenCalled();
});
test("separate measured raw waste requires preview and review without extra Food Cost deduction", async () => {
  await waste(); await click(button("Review observation")); expect(button("Save reviewed observation").disabled).toBe(true);
  const body = api.previewNativePrepObservation.mock.calls[0][2]; expect(body).toMatchObject({ raw_item_code: "raw", quantity: "5", source_unit: "lb", factor: "1", already_included_in_batch: false });
  await click(container.querySelector('[aria-label="Confirm observation review"]')); await click(button("Save reviewed observation")); expect(container.textContent).toContain("Observation saved");
});
test("physical count preserves explicit zero and full prepared scope", async () => {
  await count(); await approve(); await click(button("Save reviewed observation"));
  const body = api.saveNativePrepObservation.mock.calls[0][2].body;
  expect(body.complete_scope_confirmed).toBe(true); expect(body.lines.map(l => l.quantity)).toEqual(["42", "0"]);
  expect(body.lines[0]).not.toHaveProperty("product_id"); expect(container.textContent).toContain("Food Cost remains unchanged");
});
test("prepared waste selects the exact source lot and frozen verified profile", async () => {
  await waste(); await input("Waste source type", "prepared"); await input("Prepared waste item", "pv"); await input("Waste measured unit", "pu"); await input("Waste source lot", "lot");
  await input("Measured waste quantity", "5.000000000001"); await input("Waste category", "service_discard"); await click(container.querySelector('[aria-label="Confirm separate waste"]')); await approve();
  await click(button("Save reviewed observation")); expect(api.saveNativePrepObservation.mock.calls[0][2].body).toMatchObject({ raw_item_code: null, product_version_id: "pv", profile_id: "pu", source_batch_id: "lot", quantity: "5.000000000001", factor: "1" });
});
test("editing a count after preview invalidates its approval", async () => {
  await count(); await approve(); await input("Physical prep quantity 1", "40"); expect(button("Save reviewed observation")).toBeUndefined(); expect(api.saveNativePrepObservation).not.toHaveBeenCalled();
});
test("a missing physical count is held with a clear message and never submitted as zero", async () => {
  await count(); await input("Physical prep quantity 1", ""); await click(button("Review observation"));
  expect(container.textContent).toContain("Unknown is not zero"); expect(api.previewNativePrepObservation).not.toHaveBeenCalled();
});
test("uncertain acknowledgment freezes journal switching and refresh, then retries the exact request", async () => {
  api.saveNativePrepObservation.mockRejectedValueOnce(new Error("Connection lost")); await count(); await approve(); await click(button("Save reviewed observation"));
  expect(container.querySelector('[aria-label="Observation journal"]').closest('fieldset[disabled]')).not.toBeNull(); expect(button("Refresh observation setup").disabled).toBe(true);
  await click(button("Retry same observation")); expect(api.saveNativePrepObservation.mock.calls[1]).toEqual(api.saveNativePrepObservation.mock.calls[0]);
});
test("wrong purpose in acknowledgment retains exact retry and definite conflicts require a new review", async () => {
  api.saveNativePrepObservation.mockResolvedValueOnce({ event: { id: "wrong", store_id: "berts", purpose: "count", kind: "initial", review_hash: "hash" } });
  await waste(); await approve(); await click(button("Save reviewed observation")); expect(container.textContent).toContain("Saved observation was not confirmed");
  api.saveNativePrepObservation.mockRejectedValueOnce({ response: { status: 409, data: { detail: "Source changed" } } }); await click(button("Retry same observation")); expect(button("Save reviewed observation")).toBeUndefined();
});
test("count correction retains historical scope instead of adding newer prepared items", async () => {
  const event = { id: "old", root_id: "root", purpose: "count", kind: "initial", revision: 1, business_date: "2026-10-05", review_snapshot: {
    body: { performed_at: "2026-10-05T12:00:00-04:00", business_date: "2026-10-05", timezone_name: "America/New_York", note: "Old full scope" },
    lines: [{ product_id: "protein", product_version_id: "pv", profile_id: "pu", quantity: "42", evidence: "Weighed" }] } };
  api.nativePrepObservationSetup.mockResolvedValue({ ...data, events: [event] });
  api.previewNativePrepObservationChange.mockResolvedValue({ reviewHash: "changed-hash", review: { purpose: "count", kind: "replacement", business_date: "2026-10-05", lines: [] } });
  api.saveNativePrepObservationChange.mockResolvedValue({ event: { id: "new", store_id: "berts", purpose: "count", kind: "replacement", predecessor_id: "old", review_hash: "changed-hash" } });
  await render(); await input("Observation journal", "count"); await input("Observation action", "replacement"); await input("Current observation", "old");
  expect(container.querySelector('[aria-label="Physical prep quantity 2"]')).toBeNull(); await input("Physical prep quantity 1", "40"); await input("Observation correction reason", "Same-scope recount");
  await click(container.querySelector('[aria-label="Confirm observation calendar day"]')); await click(container.querySelector('[aria-label="Confirm full prep scope"]')); await approve(); await click(button("Save reviewed observation"));
  expect(api.saveNativePrepObservationChange.mock.calls[0][3].change.replacement.lines).toHaveLength(1); expect(container.textContent).toContain("Observation saved");
});
test("void observation submits no replacement quantities and requires a separate reason", async () => {
  api.nativePrepObservationSetup.mockResolvedValue({ ...data, events: [{ id: "old", root_id: "root", purpose: "waste", kind: "initial", revision: 1, business_date: "2026-10-05", review_snapshot: { body: null } }] });
  api.previewNativePrepObservationChange.mockResolvedValue({ reviewHash: "void-hash", review: { purpose: "waste", kind: "void", business_date: "2026-10-05", lines: [] } });
  api.saveNativePrepObservationChange.mockResolvedValue({ event: { id: "new", store_id: "berts", purpose: "waste", kind: "void", predecessor_id: "old", review_hash: "void-hash" } });
  await render(); await input("Observation action", "void"); await input("Current observation", "old"); await input("Observation correction reason", "Entered in error"); await approve(); await click(button("Save reviewed observation"));
  expect(api.saveNativePrepObservationChange.mock.calls[0][3].change).toEqual({ kind: "void", reason: "Entered in error", replacement: null });
});
