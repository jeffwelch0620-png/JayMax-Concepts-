import React, { act } from "react";
import { createRoot } from "react-dom/client";
import { BulkSupply, RequestCard, nextRunDate, storeName } from "./BulkSupply";
import * as api from "../lib/api";

jest.mock("../lib/api", () => ({ __esModule: true, bulkSupply: jest.fn(), prepPlanning: jest.fn(), prepDayDraft: jest.fn(), previewBulkRequest: jest.fn(), sendBulkRequest: jest.fn(), signBulkStep: jest.fn() }));
const line = { ordinal: 1, product_id: "ranch-b", name: "Ranch", base_unit: "bucket", requested_base_quantity: "5", sent_base_quantity: null, held_base_quantity: null, packaging: null, accepted_base_quantity: null, shortfall_base_quantity: null };
const request = (changes = {}) => ({ id: "req-1", store_id: "berts", maker_store_id: "rudds", run_date: "2026-11-05", kind: "scheduled", status: "requested", events: [], lines: [line], ...changes });
let root, container;
beforeEach(() => {
  global.IS_REACT_ACT_ENVIRONMENT = true; Object.defineProperty(global, "crypto", { configurable: true, value: { randomUUID: () => "stable-key" } });
  root = createRoot(container = document.createElement("div")); document.body.appendChild(container); jest.clearAllMocks();
});
afterEach(async () => { await act(async () => root.unmount()); container.remove(); });
const render = el => act(async () => root.render(el));
const click = el => act(async () => el.click());
const button = text => [...container.querySelectorAll("button")].find(b => b.textContent === text);
async function input(label, value) { const el = container.querySelector(`[aria-label="${label}"]`); await act(async () => { Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value").set.call(el, value); el.dispatchEvent(new Event("input", { bubbles: true })); }); }
async function choose(label, value) { const el = container.querySelector(`[aria-label="${label}"]`); await act(async () => { el.value = value; el.dispatchEvent(new Event("change", { bubbles: true })); }); }

test("Bulk runs are Monday and Thursday", () => {
  expect(nextRunDate("2026-11-01")).toBe("2026-11-02"); // Sunday -> Monday
  expect(nextRunDate("2026-11-03")).toBe("2026-11-05"); // Tuesday -> Thursday
  expect(nextRunDate("2026-11-05")).toBe("2026-11-05");
});

test("the requesting store previews par minus count and sends the reviewed request", async () => {
  api.bulkSupply.mockResolvedValue({ store_id: "berts", maker_store_id: "rudds", makes_for: [], requests: [], open_shortfalls: [] });
  api.prepDayDraft.mockResolvedValue({ counts: [{ id: "count-1", latest: true }] });
  api.previewBulkRequest.mockResolvedValue({ reviewHash: "a".repeat(64), review: { lines: [{ ordinal: 1, name: "Ranch", target_par: "5", source_unit: "bucket", base_unit: "bucket", counted_base_quantity: "2", requested_base_quantity: "3" }] } });
  api.sendBulkRequest.mockResolvedValue({ request: request() });
  await render(<BulkSupply rid="berts" />);
  expect(api.prepDayDraft).not.toHaveBeenCalled(); // forms open on demand
  await click(button("Send Bulk count"));
  expect(container.textContent).toContain("Held at Rudd's"); // store names, not ids
  expect(container.textContent).toMatch(/Par group \((Monday|Thursday) run\)/); // the run day is shown next to the par choice
  await input("Bulk request note", "Wednesday close");
  await click(button("Preview request"));
  expect(api.previewBulkRequest.mock.calls[0][1]).toMatchObject({ kind: "scheduled", day_group: "weekday", count_event_id: "count-1", note: "Wednesday close" });
  expect(container.textContent).toContain("3 bucket");
  expect(button("Send request").disabled).toBe(true);
  await click(container.querySelector('[aria-label="Review Bulk request"]'));
  await click(button("Send request"));
  expect(api.sendBulkRequest).toHaveBeenCalledWith("berts", expect.objectContaining({ expected_review_hash: "a".repeat(64), reviewed: true }), "stable-key");
});

test("a spot request retry resends the exact reviewed payload", async () => {
  api.bulkSupply.mockResolvedValue({ store_id: "berts", maker_store_id: "rudds", makes_for: [], requests: [], open_shortfalls: [] });
  api.prepPlanning.mockResolvedValue({ products: [{ product_id: "ranch-b", name: "Ranch" }], unitProfiles: [{ id: "u", source_unit: "bucket" }], plans: [{ product_id: "ranch-b", unit_profile_id: "u", active: true, track: "bulk" }] });
  api.previewBulkRequest.mockResolvedValueOnce({ reviewHash: "b".repeat(64) }).mockResolvedValue({ reviewHash: "c".repeat(64) });
  api.sendBulkRequest.mockRejectedValueOnce(new Error("Network lost")).mockResolvedValue({ request: request({ kind: "spot" }) });
  await render(<BulkSupply rid="berts" />);
  await click(button("Spot request"));
  await choose("Spot item 1", "ranch-b"); await input("Spot amount 1", "2"); await input("Spot reason 1", "Short Thursday"); await input("Spot note", "Lunch rush");
  await click(button("Send spot request"));
  await click(button("Retry the same request"));
  expect(api.previewBulkRequest).toHaveBeenCalledTimes(1);
  expect(api.sendBulkRequest.mock.calls[1]).toEqual(api.sendBulkRequest.mock.calls[0]);
  expect(api.sendBulkRequest.mock.calls[0][1].expected_review_hash).toBe("b".repeat(64));
});

test("the maker signs off sent and held amounts with packaging; held counts toward the owner's par", async () => {
  api.signBulkStep.mockResolvedValue({ request: request({ status: "sent" }) });
  const changed = jest.fn();
  await render(<RequestCard rid="rudds" store="rudds" request={request()} onChange={changed} />);
  expect(button("Cancel request")).toBeUndefined();
  await click(button("Sign off what was made"));
  await input("Sent Ranch", "3"); await input("Held Ranch", "2"); await input("Bulk sign-off note", "Invented Bulk lead");
  expect(button("Sign off made").disabled).toBe(true); // packaging required for anything made
  await input("Packaging Ranch", "5 x 1 gal buckets");
  await click(button("Sign off made"));
  expect(api.signBulkStep).toHaveBeenCalledWith("rudds", "req-1", { action: "fulfill", handoff: "delivery", note: "Invented Bulk lead",
    lines: [{ ordinal: 1, base_quantity: "3", held_base_quantity: "2", packaging: "5 x 1 gal buckets" }] }, "stable-key");
  expect(changed).toHaveBeenCalled();

  const sent = request({ status: "sent", events: [{ action: "fulfill", handoff: "pickup" }], lines: [{ ...line, sent_base_quantity: "3", held_base_quantity: "2", packaging: "5 x 1 gal buckets" }] });
  await render(<RequestCard rid="berts" store="berts" request={sent} onChange={changed} />);
  expect(container.textContent).toContain("pickup");
  await click(button("Accept delivery"));
  await input("Bulk sign-off note", "Invented manager");
  await click(button("Accept delivery"));
  expect(api.signBulkStep.mock.calls[1][2]).toEqual({ action: "accept", note: "Invented manager", lines: [{ ordinal: 1, base_quantity: "3" }] });

  const accepted = request({ status: "accepted", lines: [{ ...line, sent_base_quantity: "3", held_base_quantity: "2", accepted_base_quantity: "3", shortfall_base_quantity: "0" }] });
  await render(<RequestCard rid="berts" store="berts" request={accepted} onChange={changed} />);
  expect([...container.querySelectorAll("tbody td")].pop().textContent).toBe("—"); // no shortfall: 3 here + 2 held meets the par of 5
  expect(button("Accept delivery")).toBeUndefined();
});

test("store ids read as names, and a save in flight says Saving, not Retry", async () => {
  expect([storeName("berts"), storeName("rudds"), storeName("papa"), storeName("unknown")]).toEqual(["Bert's", "Rudd's", "Papa Leoni's", "unknown"]);
  let finish; api.signBulkStep.mockReturnValue(new Promise(resolve => { finish = resolve; }));
  await render(<RequestCard rid="rudds" store="rudds" request={request()} onChange={jest.fn()} />);
  await click(button("Sign off what was made"));
  await input("Packaging Ranch", "5 x 1 gal buckets"); await input("Bulk sign-off note", "Invented Bulk lead");
  await click(button("Sign off made"));
  expect(button("Saving…").disabled).toBe(true);
  expect(button("Retry the same sign-off")).toBeUndefined();
  await act(async () => finish({ request: request({ status: "sent" }) }));
});
