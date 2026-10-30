import React, { act } from "react";
import { createRoot } from "react-dom/client";
import { BulkSupply, RequestCard, nextRunDate } from "./BulkSupply";
import * as api from "../lib/api";

jest.mock("../lib/api", () => ({ __esModule: true, bulkSupply: jest.fn(), prepPlanning: jest.fn(), prepDayDraft: jest.fn(), previewBulkRequest: jest.fn(), sendBulkRequest: jest.fn(), signBulkStep: jest.fn() }));
const line = { ordinal: 1, product_id: "chili-b", name: "Chili", base_unit: "oz", requested_base_quantity: "18", sent_base_quantity: null, packaging: null, accepted_base_quantity: null, shortfall_base_quantity: null };
const request = (changes = {}) => ({ id: "req-1", store_id: "berts", maker_store_id: "rudds", run_date: "2026-11-02", kind: "scheduled", status: "requested", events: [], lines: [line], ...changes });
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

test("Bulk runs are Monday and Thursday", () => {
  expect(nextRunDate("2026-11-01")).toBe("2026-11-02"); // Sunday -> Monday
  expect(nextRunDate("2026-11-03")).toBe("2026-11-05"); // Tuesday -> Thursday
  expect(nextRunDate("2026-11-05")).toBe("2026-11-05");
});

test("the requesting store previews par minus count and sends the reviewed request", async () => {
  api.bulkSupply.mockResolvedValue({ store_id: "berts", maker_store_id: "rudds", makes_for: [], requests: [], open_shortfalls: [] });
  api.prepPlanning.mockResolvedValue({ products: [], unitProfiles: [], plans: [] });
  api.prepDayDraft.mockResolvedValue({ counts: [{ id: "count-1", latest: true }] });
  api.previewBulkRequest.mockResolvedValue({ reviewHash: "a".repeat(64), review: { lines: [{ ordinal: 1, name: "Chili", target_par: "4", source_unit: "quart", base_unit: "oz", counted_base_quantity: "110", requested_base_quantity: "18" }] } });
  api.sendBulkRequest.mockResolvedValue({ request: request() });
  await render(<BulkSupply rid="berts" />);
  await input("Bulk request note", "Sunday close");
  await click(button("Preview request"));
  expect(api.previewBulkRequest.mock.calls[0][1]).toMatchObject({ kind: "scheduled", day_group: "weekday", count_event_id: "count-1", note: "Sunday close" });
  expect(container.textContent).toContain("18 oz");
  expect(button("Send request").disabled).toBe(true);
  await click(container.querySelector('[aria-label="Review Bulk request"]'));
  await click(button("Send request"));
  expect(api.sendBulkRequest).toHaveBeenCalledWith("berts", expect.objectContaining({ expected_review_hash: "a".repeat(64), reviewed: true }), "stable-key");
});

test("the maker signs off amounts and packaging, then the requester accepts and sees the shortfall", async () => {
  api.signBulkStep.mockResolvedValue({ request: request({ status: "sent" }) });
  const changed = jest.fn();
  await render(<RequestCard rid="rudds" store="rudds" request={request()} onChange={changed} />);
  expect(button("Cancel request")).toBeUndefined();
  await click(button("Sign off what was sent"));
  await input("Sent Chili", "15"); await input("Bulk sign-off note", "Invented Bulk lead");
  expect(button("Sign off sent").disabled).toBe(true); // packaging required for anything sent
  await input("Packaging Chili", "3 x 5 lb bags");
  await click(button("Sign off sent"));
  expect(api.signBulkStep).toHaveBeenCalledWith("rudds", "req-1", { action: "fulfill", handoff: "delivery", note: "Invented Bulk lead", lines: [{ ordinal: 1, base_quantity: "15", packaging: "3 x 5 lb bags" }] }, "stable-key");
  expect(changed).toHaveBeenCalled();

  const sent = request({ status: "sent", events: [{ action: "fulfill", handoff: "pickup" }], lines: [{ ...line, sent_base_quantity: "15", packaging: "3 x 5 lb bags" }] });
  await render(<RequestCard rid="berts" store="berts" request={sent} onChange={changed} />);
  expect(container.textContent).toContain("pickup");
  await click(button("Accept delivery"));
  await input("Bulk sign-off note", "Invented manager");
  await click(button("Accept delivery"));
  expect(api.signBulkStep.mock.calls[1][2]).toEqual({ action: "accept", note: "Invented manager", lines: [{ ordinal: 1, base_quantity: "15" }] });

  const accepted = request({ status: "accepted", lines: [{ ...line, sent_base_quantity: "15", accepted_base_quantity: "15", shortfall_base_quantity: "3" }] });
  await render(<RequestCard rid="berts" store="berts" request={accepted} onChange={changed} />);
  expect(container.textContent).toContain("3 oz");
  expect(button("Accept delivery")).toBeUndefined();
});
