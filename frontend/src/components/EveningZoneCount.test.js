import React, { act } from "react";
import { createRoot } from "react-dom/client";
import { EveningZoneCount, ZoneCountForm, ZoneLayoutForm, countStamp } from "./EveningZoneCount";
import * as api from "../lib/api";

jest.mock("../lib/api", () => ({ __esModule: true, nativePrepObservationSetup: jest.fn(), saveNativePrepZones: jest.fn(), previewNativePrepObservation: jest.fn(), saveNativePrepObservation: jest.fn() }));
const products = [{ id: "v-cuc", product_id: "cuc", name: "Sliced cucumbers" }, { id: "v-ranch", product_id: "ranch", name: "Ranch dressing" }];
const profiles = [{ id: "u-cuc", product_version_id: "v-cuc", source_unit: "quarter pan" }, { id: "u-ranch", product_version_id: "v-ranch", source_unit: "quart" }];
const layout = { header: { id: "layout-1", revision: 1 }, zones: [
  { zone_code: "walk-in", name: "Walk-in", walk_position: 1, product_ids: ["cuc", "ranch"] },
  { zone_code: "salad-station", name: "Salad station", walk_position: 2, product_ids: ["cuc"] }] };
const setup = { products, profiles, policy: null, zoneLayout: layout, proposedZoneLayout: { zones: layout.zones } };
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
const now = () => new Date("2026-10-06T01:30:00Z");

test("count stamp uses the store's own calendar day and offset", () => {
  expect(countStamp("America/New_York", now())).toEqual({ performed_at: "2026-10-05T21:30:00-04:00", business_date: "2026-10-05", timezone_name: "America/New_York" });
  expect(countStamp("America/New_York", new Date("2026-12-01T03:00:00Z")).performed_at).toBe("2026-11-30T22:00:00-05:00");
});

test("zone count walks zones in order, totals multi-zone items and sends zone quantities", async () => {
  const preview = jest.fn().mockResolvedValue({ reviewHash: "a".repeat(64), review: { lines: [{ product_id: "cuc", quantity: "3.5" }, { product_id: "ranch", quantity: "2" }] } });
  const save = jest.fn().mockResolvedValue({ event: { id: "count-1" } });
  await render(<ZoneCountForm setup={setup} onPreview={preview} onSave={save} now={now} />);
  expect([...container.querySelectorAll("h4")].map(h => h.textContent)).toEqual(["1. Walk-in", "2. Salad station"]);
  await input("Count Sliced cucumbers in Walk-in", "2"); expect(container.textContent).toContain("Total incomplete quarter pan across 2 zones");
  await input("Count Sliced cucumbers in Salad station", "1.5"); expect(container.textContent).toContain("Total 3.5 quarter pan across 2 zones");
  expect(button("Review totals").disabled).toBe(true);
  await input("Count Ranch dressing in Walk-in", "0"); await input("Evening count note", "Closing count, invented manager");
  await click(button("Review totals"));
  expect(preview.mock.calls[0][0]).toMatchObject({ zone_layout_id: "layout-1", business_date: "2026-10-05", timezone_name: "America/New_York", calendar_date_confirmed: true, complete_scope_confirmed: true,
    lines: [{ product_version_id: "v-cuc", profile_id: "u-cuc", zones: [{ zone_code: "walk-in", quantity: "2" }, { zone_code: "salad-station", quantity: "1.5" }] },
            { product_version_id: "v-ranch", profile_id: "u-ranch", zones: [{ zone_code: "walk-in", quantity: "0" }] }] });
  expect(preview.mock.calls[0][0].lines[0]).not.toHaveProperty("quantity");
  expect(container.textContent).toContain("Sliced cucumbers 3.5");
  await click(button("Save evening count"));
  expect(save.mock.calls[0][0]).toEqual({ body: preview.mock.calls[0][0], expected_review_hash: "a".repeat(64), reviewed: true });
  expect(container.textContent).toContain("Evening prep count saved for 2026-10-05");
});

test("interrupted save retries the identical request", async () => {
  const preview = jest.fn().mockResolvedValue({ reviewHash: "b".repeat(64), review: { lines: [] } });
  const save = jest.fn().mockRejectedValueOnce(new Error("Network")).mockResolvedValue({ event: { id: "count-1" } });
  await render(<ZoneCountForm setup={setup} onPreview={preview} onSave={save} now={now} />);
  for (const [l, v] of [["Count Sliced cucumbers in Walk-in", "1"], ["Count Sliced cucumbers in Salad station", "1"], ["Count Ranch dressing in Walk-in", "1"], ["Evening count note", "Invented"]]) await input(l, v);
  await click(button("Review totals")); await click(button("Save evening count"));
  expect(container.textContent).toContain("Network"); await click(button("Retry same count save"));
  expect(save.mock.calls[1]).toEqual(save.mock.calls[0]);
});

test("items outside every zone block the count", async () => {
  await render(<ZoneCountForm setup={{ ...setup, zoneLayout: { ...layout, zones: [{ ...layout.zones[1] }] } }} onPreview={jest.fn()} onSave={jest.fn()} now={now} />);
  expect(container.textContent).toContain("Not in any zone yet: Ranch dressing");
});

test("zone setup requires every item placed and saves zones in walk order", async () => {
  const save = jest.fn().mockResolvedValue(undefined);
  await render(<ZoneLayoutForm products={products} proposal={{ zones: [{ name: "Walk-in", product_ids: ["cuc"] }] }} onSave={save} />);
  await click(button("Save count zones")); expect(container.textContent).toContain("Place every prepared item in a zone: Ranch dressing");
  await input("New zone name", "Salad station"); await click(button("Add zone"));
  await click(container.querySelector('[aria-label="Ranch dressing in zone 1"]')); await click(container.querySelector('[aria-label="Sliced cucumbers in zone 2"]'));
  await click(container.querySelector('[aria-label="Move zone 2 up"]'));
  await click(button("Save count zones"));
  expect(save.mock.calls[0][0].zones).toEqual([{ name: "Salad station", product_ids: ["cuc"] }, { name: "Walk-in", product_ids: ["cuc", "ranch"] }]);
});

test("first visit offers zone setup from the proposal", async () => {
  api.nativePrepObservationSetup.mockResolvedValue({ ...setup, zoneLayout: null });
  await render(<EveningZoneCount rid="berts" />);
  expect(container.textContent).toContain("Set up evening count zones");
  expect(container.querySelector('[aria-label="Zone name 1"]').value).toBe("Walk-in");
});
