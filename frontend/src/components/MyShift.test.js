import React, { act } from "react";
import { createRoot } from "react-dom/client";
import { MyShift } from "./MyShift";
import * as api from "../lib/api";

jest.mock("../lib/api", () => ({ __esModule: true, staffStation: jest.fn(), confirmStaffStation: jest.fn() }));
jest.mock("./StaffPrepTasks", () => ({ StaffPrepTaskPlan: (p) => <div data-testid="task-plan">{p.personal ? "personal" : "shared"}:{p.staffId}</div> }));
jest.mock("../lib/calc", () => ({ todayISO: () => "2026-11-01" }));
let root, container, keys;
const stations = [{ code: "GRILL", name: "Grill", active: true }, { code: "PREP", name: "Prep", active: true }];
beforeEach(() => {
  global.IS_REACT_ACT_ENVIRONMENT = true; keys = 0;
  Object.defineProperty(global, "crypto", { configurable: true, value: { randomUUID: () => `key-${++keys}` } });
  root = createRoot(container = document.createElement("div")); document.body.appendChild(container); jest.clearAllMocks();
});
afterEach(async () => { await act(async () => root.unmount()); container.remove(); });
const render = el => act(async () => root.render(el));
const q = id => container.querySelector(`[data-testid="${id}"]`);
async function choose(value) { const el = q("my-station-select"); await act(async () => { el.value = value; el.dispatchEvent(new Event("change", { bubbles: true })); }); }

test("a cook picks their station and sees their own tasks", async () => {
  api.staffStation.mockResolvedValueOnce({ staff_member_id: "m-a", business_date: "2026-11-01", station_code: null, stations })
    .mockResolvedValueOnce({ staff_member_id: "m-a", business_date: "2026-11-01", station_code: "PREP", stations });
  api.confirmStaffStation.mockResolvedValue({ station_code: "PREP" });
  await render(<MyShift rid="berts" staffId="m-a" staffName="Invented cook A" track="daily" setTrack={() => {}} />);
  expect(container.textContent).toContain("Pick your station");
  expect(q("task-plan").textContent).toBe("personal:m-a");
  await choose("PREP");
  await act(async () => q("my-station-confirm").click());
  expect(api.confirmStaffStation).toHaveBeenCalledWith("berts", { staff_member_id: "m-a", station_code: "PREP", business_date: "2026-11-01" }, "key-1");
  expect(container.textContent).toContain("You're on Prep");
});

test("a retry after a lost reply reuses its key; a different station is a new request", async () => {
  api.staffStation.mockResolvedValue({ staff_member_id: "m-a", business_date: "2026-11-01", station_code: null, stations });
  api.confirmStaffStation.mockRejectedValueOnce(new Error("Network Error")).mockRejectedValueOnce(new Error("Network Error"));
  await render(<MyShift rid="berts" staffId="m-a" staffName="Invented cook A" track="daily" setTrack={() => {}} />);
  await choose("GRILL");
  await act(async () => q("my-station-confirm").click());
  await act(async () => q("my-station-confirm").click());
  expect(api.confirmStaffStation.mock.calls.map(c => c[2])).toEqual(["key-1", "key-1"]);
  await choose("PREP");
  await act(async () => q("my-station-confirm").click());
  expect(api.confirmStaffStation.mock.calls[2][2]).toBe("key-2");
  expect(container.querySelector('[role="alert"]')).toBeNull();
});
