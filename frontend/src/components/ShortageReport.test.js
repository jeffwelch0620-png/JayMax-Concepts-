import React, { act } from "react";
import { createRoot } from "react-dom/client";
import { ShortageReport } from "./ShortageReport";
import * as api from "../lib/api";

jest.mock("../lib/api", () => ({ __esModule: true, reportShortage: jest.fn() }));
let root, container, keys;
const task = { id: "t-1", name: "Invented marinara", source_unit: "qt" };
beforeEach(() => {
  global.IS_REACT_ACT_ENVIRONMENT = true; keys = 0;
  Object.defineProperty(global, "crypto", { configurable: true, value: { randomUUID: () => `key-${++keys}` } });
  root = createRoot(container = document.createElement("div")); document.body.appendChild(container); jest.clearAllMocks();
});
afterEach(async () => { await act(async () => root.unmount()); container.remove(); });
const q = sel => container.querySelector(sel);
async function setValue(sel, value) {
  const el = q(sel), proto = el.tagName === "SELECT" ? window.HTMLSelectElement.prototype : window.HTMLInputElement.prototype;
  await act(async () => { Object.getOwnPropertyDescriptor(proto, "value").set.call(el, value); el.dispatchEvent(new Event(el.tagName === "SELECT" ? "change" : "input", { bubbles: true })); });
}
const click = sel => act(async () => q(sel).click());
async function openForm() {
  await act(async () => root.render(<ShortageReport rid="berts" day="2026-11-01" track="daily" task={task} staffId="m-a" />));
  await click('[data-testid="shortage-open-t-1"]');
}

test("a cook sends a shortage note with a reason, an optional amount and a note", async () => {
  api.reportShortage.mockResolvedValue({ replayed: false });
  await openForm();
  await click('[data-testid="shortage-send-t-1"]');
  expect(q('[role="alert"]').textContent).toContain("Choose why");
  await setValue('select[aria-label="Why are you short?"]', "out_of_ingredient");
  await setValue('input[aria-label="Note for the Shift Leader"]', "Out of invented basil");
  await setValue('input[aria-label^="How much short"]', "2");
  await click('[data-testid="shortage-send-t-1"]');
  expect(api.reportShortage).toHaveBeenCalledWith("berts", { day: "2026-11-01", track: "daily", task_id: "t-1", staff_member_id: "m-a",
    reason: "out_of_ingredient", note: "Out of invented basil", short_quantity: "2" }, "key-1");
  expect(q('[role="status"]').textContent).toContain("Sent to the Shift Leader");
});

test("a retry after a lost reply reuses its key; editing makes a new report", async () => {
  api.reportShortage.mockRejectedValueOnce(new Error("Network Error")).mockRejectedValueOnce(new Error("Network Error")).mockResolvedValue({});
  await openForm();
  await setValue('select[aria-label="Why are you short?"]', "equipment");
  await setValue('input[aria-label="Note for the Shift Leader"]', "Invented slicer down");
  await click('[data-testid="shortage-send-t-1"]');
  await click('[data-testid="shortage-send-t-1"]');
  await setValue('input[aria-label="Note for the Shift Leader"]', "Invented slicer down, using knife");
  await click('[data-testid="shortage-send-t-1"]');
  expect(api.reportShortage.mock.calls.map(c => c[2])).toEqual(["key-1", "key-1", "key-2"]);
  expect(api.reportShortage.mock.calls[0][1].short_quantity).toBeUndefined();   // left blank
});
