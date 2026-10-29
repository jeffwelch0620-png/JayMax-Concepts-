import React, { act } from "react";
import { createRoot } from "react-dom/client";
import { PrepTab } from "./PrepTab";
import * as api from "../lib/api";
jest.mock("../lib/api", () => ({ __esModule: true, listPrepItems: jest.fn().mockResolvedValue([]), getPrepList: jest.fn(() => new Promise(() => {})), prepDayDraft: jest.fn(), prepDayTasksEnabled: true }));
jest.mock("../lib/calc", () => ({ ...jest.requireActual("../lib/calc"), todayISO: () => "2026-10-25" }));
let root, container;
beforeEach(() => {
  global.IS_REACT_ACT_ENVIRONMENT = true; jest.clearAllMocks();
  api.listPrepItems.mockResolvedValue([]);
  api.prepDayDraft.mockImplementation((rid, day, track) => Promise.resolve({ store_id: rid, prep_date: day, track, current: null, counts: [], planning: { plans: [], products: [], unitProfiles: [] } }));
  container = document.createElement("div"); document.body.appendChild(container); root = createRoot(container);
});
afterEach(async () => { await act(async () => root.unmount()); container.remove(); });
const render = initialContext => act(async () => root.render(<PrepTab rid="berts" initialContext={initialContext} items={[]} dishes={[]} prepStock={[]} prepLogs={[]} drafts={new Map()}/>));
test("overview entry carries date and bulk track into the actual dated draft reader", async () => {
  await render({ rid: "berts", day: "2026-10-24", track: "bulk" });
  expect(container.querySelector('[aria-label="Prep draft date"]').value).toBe("2026-10-24");
  expect(api.prepDayDraft.mock.calls[0].slice(0, 3)).toEqual(["berts", "2026-10-24", "bulk"]);
  expect(api.listPrepItems).toHaveBeenCalledWith("berts", "bulk");
});
test.each([undefined, { rid: "rudds", day: "2026-10-24", track: "bulk" }, { rid: "berts", day: "invalid", track: "bulk" }])("ordinary or invalid entry preserves today/daily defaults %#", async entry => {
  await render(entry); expect(container.querySelector('[aria-label="Prep draft date"]').value).toBe("2026-10-25");
  expect(api.prepDayDraft.mock.calls[0].slice(0, 3)).toEqual(["berts", "2026-10-25", "daily"]);
});
test("Salad Bar appears at Bert's with the native workflow and opens its own dated draft", async () => {
  await render({ rid: "berts", day: "2026-10-24", track: "salad" });
  expect(container.querySelector('[data-testid="prep-track-salad"]')).not.toBeNull();
  expect(api.prepDayDraft.mock.calls[0].slice(0, 3)).toEqual(["berts", "2026-10-24", "salad"]);
});
test("Salad Bar is hidden at other stores and without the native workflow", async () => {
  await act(async () => root.render(<PrepTab rid="rudds" items={[]} dishes={[]} prepStock={[]} prepLogs={[]} drafts={new Map()}/>));
  expect(container.querySelector('[data-testid="prep-track-salad"]')).toBeNull();
  api.prepDayTasksEnabled = false; api.getPrepList.mockReturnValue(new Promise(() => {}));
  try {
    await render({ rid: "berts", day: "2026-10-24", track: "salad" });
    expect(container.querySelector('[data-testid="prep-track-salad"]')).toBeNull();
    expect(api.listPrepItems).not.toHaveBeenCalledWith("berts", "salad");
  } finally { api.prepDayTasksEnabled = true; }
});
