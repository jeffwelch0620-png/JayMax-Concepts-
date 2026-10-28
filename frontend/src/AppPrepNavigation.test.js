import React, { act } from "react";
import { createRoot } from "react-dom/client";
import App from "./App";
import * as api from "./lib/api";
import { useStoreState } from "./lib/useStoreState";
import { resetComponentApiMock } from "./testHelpers/componentApiMock";
import { overviewFixture } from "./testFixtures/managerOverview";

jest.mock("./lib/api", () => require("./testHelpers/componentApiMock").createComponentApiMock());
jest.mock("./lib/useStoreState", () => ({ useStoreState: jest.fn() }));
// Test-only caller of the retained App callback. B1 has no editable destination.
// Real B1 no-escape behavior is covered by AppManagerOverview/ManagerOverviewTab.
jest.mock("./components/ManagerOverviewTab", () => ({ManagerOverviewTab: props =>
  <button onClick={() => props.onOpenPrep({rid:props.rid,day:"2026-10-25",track:"bulk"})}>TEST ONLY existing prep callback</button>}));
// A different fictional today makes a stale historical date observable.
jest.mock("./lib/calc", () => ({ ...jest.requireActual("./lib/calc"), todayISO: () => "2026-10-26" }));
jest.mock("./components/AiAssistant", () => ({ AiAssistant: () => null }));
jest.mock("./components/ActualInventoryTab", () => ({ ActualInventoryTab: () => <p>TEST ONLY count workflow</p> }));
jest.mock("./components/Login", () => ({ Login: props => <button onClick={() => props.onLogin({ user: {
  id: "TEST-ONLY-second-manager", role: "manager", locations: ["berts"], email: "second@example.invalid",
} })}>TEST ONLY personal sign-in</button> }));

const today = "2026-10-26", overviewDay = "2026-10-25";
let root, container;
const input = label => container.querySelector(`[aria-label="${label}"]`);
const click = text => act(async () => [...container.querySelectorAll("button")].find(b => b.textContent === text).click());
const clickId = id => act(async () => container.querySelector(`[data-testid="${id}"]`).click());
async function set(label, value) {
  const el = input(label);
  await act(async () => {
    const proto = el.tagName === "TEXTAREA" ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype;
    Object.getOwnPropertyDescriptor(proto, "value").set.call(el, value);
    el.dispatchEvent(new Event("input", { bubbles: true }));
  });
}
async function openDatedPrep() {
  await clickId("nav-tab-managerOverview");
  await click("TEST ONLY existing prep callback");
}
function expectPrep(rid, day, track) {
  expect(input("Prep draft date").value).toBe(day);
  expect(api.prepDayDraft).toHaveBeenLastCalledWith(rid, day, track);
  expect(api.listPrepItems).toHaveBeenLastCalledWith(rid, track);
}
beforeEach(async () => {
  global.IS_REACT_ACT_ENVIRONMENT = true;
  window.sessionStorage.clear(); resetComponentApiMock(api);
  Object.assign(api, { nativePurchasesEnabled: true, actualInventoryEnabled: true,
    prepDayTasksEnabled: true, prepExecutionEnabled: true, isPostgres: true });
  api.currentSession.mockReturnValue({ user: { id: "TEST-ONLY-manager", role: "manager",
    locations: ["berts", "rudds"], email: "manager@example.invalid" } });
  api.listPrepItems.mockResolvedValue([]);
  api.actualCounts.mockImplementation(async rid => overviewFixture(rid).counts);
  api.prepDayDraft.mockImplementation(async (rid, day, track) => ({ store_id: rid, prep_date: day, track,
    current: null, counts: [], planning: { plans: [], products: [], unitProfiles: [] } }));
  api.prepExecution.mockImplementation(async (rid, day, track) => ({ store_id: rid, prep_date: day, track,
    revision: 0, status: "draft", draft_version_id: null, draft: null, release: null,
    tasks: [], completions: [], history: [], progress_supported: true, task_progress: [] }));
  api.nativePrepBatchSetup.mockResolvedValue({ events: [] });
  useStoreState.mockImplementation((loc, session, initial) => ({ state: initial, isCurrent: () => true }));
  container = document.createElement("div"); document.body.appendChild(container); root = createRoot(container);
  await act(async () => root.render(<App/>));
});
afterEach(async () => { await act(async () => root.unmount()); container.remove(); });

test("manual Prep entry uses today/daily, while reopening the dated bulk workflow restores its unsent draft", async () => {
  await openDatedPrep(); expectPrep("berts", overviewDay, "bulk");
  await set("Prep draft reason", "TEST ONLY retained bulk draft");
  await clickId("nav-tab-dashboard"); await clickId("nav-tab-prep");
  expectPrep("berts", today, "daily"); expect(input("Prep draft reason").value).toBe("");
  await openDatedPrep(); expectPrep("berts", overviewDay, "bulk");
  expect(input("Prep draft reason").value).toBe("TEST ONLY retained bulk draft");
  expect(api.savePrepDayDraft).not.toHaveBeenCalled(); expect(api.savePrepExecution).not.toHaveBeenCalled();
});
test("clicking the active Prep tab also returns to ordinary entry, without deleting the dated draft", async () => {
  await openDatedPrep(); await set("Prep draft reason", "TEST ONLY active-tab draft");
  await clickId("nav-tab-prep"); expectPrep("berts", today, "daily");
  await openDatedPrep(); expect(input("Prep draft reason").value).toBe("TEST ONLY active-tab draft");
});
test("restaurant changes clear the one-time focus and keep drafts scoped to their restaurant", async () => {
  await openDatedPrep(); await set("Prep draft reason", "TEST ONLY Bert's draft");
  await clickId("location-tab-rudds"); await clickId("nav-tab-prep");
  expectPrep("rudds", today, "daily"); expect(input("Prep draft reason").value).toBe("");
  await clickId("location-tab-berts"); await openDatedPrep();
  expect(input("Prep draft reason").value).toBe("TEST ONLY Bert's draft");
});
test("a new personal session cannot inherit the previous person's focus or unsent draft", async () => {
  await openDatedPrep(); await set("Prep draft reason", "TEST ONLY first-person draft");
  await act(async () => window.dispatchEvent(new Event(api.SESSION_EXPIRED_EVENT)));
  await click("TEST ONLY personal sign-in"); await clickId("nav-tab-prep");
  expectPrep("berts", today, "daily"); expect(input("Prep draft reason").value).toBe("");
  await openDatedPrep(); expect(input("Prep draft reason").value).toBe("");
});
