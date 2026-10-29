import React, { act } from "react";
import { createRoot } from "react-dom/client";
import { ManagerOverviewTab } from "./ManagerOverviewTab";
import { overviewFixture, overviewTestOwner as owner, OVERVIEW_TEST_DAY as day } from "../testFixtures/managerOverview";
jest.mock("../lib/calc", () => ({ ...jest.requireActual("../lib/calc"), todayISO: () => "2026-10-25" }));
let root, container, api, onOpenCounts, onOpenPrep;
const button = text => [...container.querySelectorAll("button")].find(b => b.textContent === text);
const input = label => container.querySelector(`[aria-label="${label}"]`);
const render = (props = {}) => act(async () => root.render(<ManagerOverviewTab rid="berts" user={owner} readApi={api} onOpenCounts={onOpenCounts} onOpenPrep={onOpenPrep} {...props}/>));
const click = el => act(async () => el.click());
async function set(label, value) {
  const el = input(label);
  await act(async () => {
    Object.getOwnPropertyDescriptor(el.tagName === "SELECT" ? HTMLSelectElement.prototype : HTMLInputElement.prototype, "value").set.call(el, value);
    el.dispatchEvent(new Event(el.tagName === "SELECT" ? "change" : "input", { bubbles: true }));
  });
}
beforeEach(() => {
  global.IS_REACT_ACT_ENVIRONMENT = true; window.sessionStorage.clear();
  api = { actualInventoryEnabled: true, prepExecutionEnabled: true,
    actualCounts: jest.fn(rid => Promise.resolve(overviewFixture(rid).counts)),
    prepExecution: jest.fn((rid, date, track) => Promise.resolve(overviewFixture(rid, date, track).prep)),
    saveState: jest.fn(), commitPrepExecution: jest.fn(), staffIdentify: jest.fn() };
  onOpenCounts = jest.fn(); onOpenPrep = jest.fn();
  container = document.createElement("div"); document.body.appendChild(container); root = createRoot(container);
});
afterEach(async () => { await act(async () => root.unmount()); container.remove(); });
test("Bert's today/bulk view uses fictional reads and explicit historical/review labels", async () => {
  await render();
  expect(input("Manager overview date").value).toBe(day); expect(input("Manager overview track").value).toBe("bulk");
  expect(container.textContent).toContain("TEST ONLY Bulk Sauce"); expect(container.textContent).toContain("In progress");
  expect(container.textContent).toContain("Manager review required"); expect(container.textContent).toContain("not live on-hand inventory");
  expect(container.textContent).toContain("does not calculate Food Cost");
  await click(button("Open Actual Inventory")); await click(button("Open dated prep workflow"));
  expect(onOpenCounts).toHaveBeenCalledWith({ rid: "berts" }); expect(onOpenPrep).toHaveBeenCalledWith({ rid: "berts", day, track: "bulk" });
  expect(api.saveState).not.toHaveBeenCalled(); expect(api.commitPrepExecution).not.toHaveBeenCalled(); expect(api.staffIdentify).not.toHaveBeenCalled();
});
test("missing counts and empty prep never become zero value or complete work", async () => {
  api.actualCounts.mockResolvedValue([]);
  const { prep } = overviewFixture(); Object.assign(prep, { draft: null, draft_version_id: null, status: "draft", tasks: [], task_progress: [], completions: [] });
  api.prepExecution.mockResolvedValue(prep); await render();
  expect(container.textContent).toContain("Inventory value is unavailable"); expect(container.textContent).toContain("No dated plan saved");
  expect(container.textContent).toContain("does not confirm that prep is complete"); expect(container.textContent).not.toContain("$0");
});
test("mixed-scope count error leaves valid prep available and permits explicit refresh", async () => {
  api.actualCounts.mockResolvedValue(overviewFixture("rudds").counts); await render();
  expect(container.textContent).toContain("could not be confirmed"); expect(container.textContent).toContain("TEST ONLY Bulk Sauce");
  api.actualCounts.mockResolvedValue(overviewFixture().counts); await click(button("Refresh manager overview"));
  expect(container.textContent).toContain("After that day’s receipts");
});
test("late prior-day reads cannot replace selected-day data or navigation", async () => {
  let resolve; api.prepExecution.mockReturnValueOnce(new Promise(r => { resolve = r; })); await render();
  await set("Manager overview date", "2026-10-26");
  const older = overviewFixture().prep; older.tasks[0].task_snapshot.name = "STALE DAY SHOULD NOT APPEAR";
  await act(async () => resolve(older)); expect(container.textContent).not.toContain("STALE DAY");
  await click(button("Open dated prep workflow")); expect(onOpenPrep).toHaveBeenLastCalledWith({ rid: "berts", day: "2026-10-26", track: "bulk" });
});
test("a prior refresh cannot replace a newer refresh", async () => {
  let resolve; api.prepExecution.mockReturnValueOnce(new Promise(r => { resolve = r; })); await render();
  await click(button("Refresh manager overview"));
  const stale = overviewFixture().prep; stale.tasks[0].task_snapshot.name = "STALE REFRESH";
  await act(async () => resolve(stale)); expect(container.textContent).not.toContain("STALE REFRESH");
});
test("restaurant changes load only that restaurant's remembered date and track", async () => {
  await render(); await set("Manager overview date", "2026-10-24"); await set("Manager overview track", "daily");
  window.sessionStorage.setItem(`manager-overview:${owner.id}:rudds`, JSON.stringify({ day: "2026-10-23", track: "bulk" }));
  api.prepExecution.mockClear(); await render({ rid: "rudds" });
  // The overview card and the prep detail panel each read the selected day once.
  expect(api.prepExecution.mock.calls.length).toBeGreaterThan(0);
  api.prepExecution.mock.calls.forEach(call => expect(call).toEqual(["rudds", "2026-10-23", "bulk"]));
  await render(); expect(input("Manager overview date").value).toBe("2026-10-24"); expect(input("Manager overview track").value).toBe("daily");
});
test("actor change and reload keep preferences isolated and store no source data", async () => {
  await render(); await set("Manager overview track", "daily");
  const saved = JSON.parse(window.sessionStorage.getItem(`manager-overview:${owner.id}:berts`));
  expect(saved).toEqual({ day, track: "daily" });
  await render({ user: { ...owner, id: "other-person" } }); expect(input("Manager overview track").value).toBe("bulk");
  await act(async () => root.unmount()); root = createRoot(container); await render();
  expect(input("Manager overview track").value).toBe("daily");
});
test("scope revocation hides old results immediately and late reads stay hidden", async () => {
  let resolve; api.prepExecution.mockReturnValueOnce(new Promise(r => { resolve = r; })); await render();
  api.actualCounts.mockClear(); api.prepExecution.mockClear();
  await render({ user: { ...owner, role: "manager", locations: ["rudds"] } });
  await act(async () => resolve(overviewFixture().prep));
  expect(container.querySelector('[aria-label="Dated prep work"]')).toBeNull(); expect(container.querySelector('[role="alert"]')).not.toBeNull();
  expect(api.actualCounts).not.toHaveBeenCalled(); expect(api.prepExecution).not.toHaveBeenCalled();
});
test("blank date refuses reads and actions, with no stale result shown", async () => {
  await render(); api.actualCounts.mockClear(); api.prepExecution.mockClear(); await set("Manager overview date", "");
  expect(container.textContent).not.toContain("TEST ONLY Bulk Sauce"); expect(button("Refresh manager overview").disabled).toBe(true);
  expect(api.actualCounts).not.toHaveBeenCalled(); expect(api.prepExecution).not.toHaveBeenCalled();
});
test("disabled workflows do not issue reads or enable their navigation", async () => {
  api.actualInventoryEnabled = api.prepExecutionEnabled = false; await render();
  expect(button("Open Actual Inventory").disabled).toBe(true); expect(button("Open dated prep workflow").disabled).toBe(true);
  expect(api.actualCounts).not.toHaveBeenCalled(); expect(api.prepExecution).not.toHaveBeenCalled();
});
test("blocked browser storage cannot prevent a read-only overview", async () => {
  const getter = jest.spyOn(window, "sessionStorage", "get").mockImplementation(() => { throw new Error("Storage blocked"); });
  try { await render(); expect(container.textContent).toContain("TEST ONLY Bulk Sauce"); }
  finally { getter.mockRestore(); }
});
