import React, { act } from "react";
import { createRoot } from "react-dom/client";
import { StationBoard } from "./StationBoard";
import * as api from "../lib/api";

jest.mock("../lib/api", () => ({ __esModule: true, stationBoard: jest.fn(), moveStation: jest.fn(), setProductStation: jest.fn() }));
const board = (changes = {}) => ({ store_id: "berts", business_date: "2026-10-30",
  stations: [{ code: "GRILL", name: "Grill", department: "BOH", active: true }, { code: "PREP", name: "Prep", department: "BOH", active: true }],
  roster: [{ id: "m-a", name: "Invented cook A" }, { id: "m-b", name: "Invented cook B" }],
  open: [], history: [], products: [{ product_id: "p-1", name: "Marinara sauce", station_code: null }], ...changes });
let root, container;
beforeEach(() => {
  global.IS_REACT_ACT_ENVIRONMENT = true; Object.defineProperty(global, "crypto", { configurable: true, value: { randomUUID: () => "stable-key" } });
  root = createRoot(container = document.createElement("div")); document.body.appendChild(container); jest.clearAllMocks();
});
afterEach(async () => { await act(async () => root.unmount()); container.remove(); });
const render = el => act(async () => root.render(el));
async function choose(label, value) { const el = container.querySelector(`[aria-label="${label}"]`); await act(async () => { el.value = value; el.dispatchEvent(new Event("change", { bubbles: true })); }); }

test("the Shift Leader puts a cook on a station and every stint shows", async () => {
  api.stationBoard.mockResolvedValue(board());
  const onGrill = board({ open: [{ stint_id: "s1", staff_member_id: "m-a", staff_name: "Invented cook A", station_code: "GRILL", started_at: "2026-10-30T15:00:00Z" }],
    history: [{ stint_id: "s1", staff_name: "Invented cook A", station_name: "Grill", started_at: "2026-10-30T15:00:00Z", ended_at: null }] });
  api.moveStation.mockResolvedValue({ board: onGrill });
  await render(<StationBoard rid="berts" />);
  expect(container.querySelector('[data-testid="station-GRILL"]').textContent).toContain("Nobody");
  await choose("Station for Invented cook A", "GRILL");
  expect(api.moveStation).toHaveBeenCalledWith("berts", expect.any(String), { staff_member_id: "m-a", station_code: "GRILL", reason: "moved" }, "stable-key");
  expect(container.querySelector('[data-testid="station-GRILL"]').textContent).toContain("Invented cook A");
  expect(container.textContent).toContain("Station time today");
});

test("taking a cook off and ending a shift record why the stint ended", async () => {
  api.stationBoard.mockResolvedValue(board({ open: [{ stint_id: "s1", staff_member_id: "m-a", staff_name: "Invented cook A", station_code: "PREP", started_at: "2026-10-30T15:00:00Z" }] }));
  api.moveStation.mockResolvedValue({ board: board() });
  await render(<StationBoard rid="berts" />);
  await act(async () => [...container.querySelectorAll("button")].find(b => b.textContent === "End shift").click());
  expect(api.moveStation.mock.calls[0][2]).toEqual({ staff_member_id: "m-a", station_code: null, reason: "shift_end" });
});

test("a Kitchen Manager sets which station normally makes an item", async () => {
  api.stationBoard.mockResolvedValue(board());
  api.setProductStation.mockResolvedValue({ product_station: {} });
  await render(<StationBoard rid="berts" />);
  await choose("Default station for Marinara sauce", "PREP");
  expect(api.setProductStation).toHaveBeenCalledWith("berts", "p-1", { station_code: "PREP", note: "Set on the station board" }, "stable-key");
});
