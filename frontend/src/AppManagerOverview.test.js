import React, { act } from "react";
import { createRoot } from "react-dom/client";
import App from "./App";
import * as api from "./lib/api";
import { useStoreState } from "./lib/useStoreState";
import { b1Owner as owner, b1Fixture } from "./testFixtures/managerB1";
jest.mock("./lib/api", () => ({ currentSession: jest.fn(), actualInventoryEnabled: true, prepExecutionEnabled: true,
  staffPrepTasksEnabled: false, managerHandoffEnabled: false, prepExecution: jest.fn(), SESSION_EXPIRED_EVENT: "test-expired" }));
jest.mock("./lib/useStoreState", () => ({ useStoreState: jest.fn() }));
jest.mock("./components/AiAssistant", () => ({ AiAssistant: () => null }));
jest.mock("./components/OwnerDashboard", () => ({ OwnerDashboard: () => <p>Owner group</p> }));
jest.mock("./components/ActualInventoryTab", () => ({ ActualInventoryTab: props => <p>TEST ONLY Actual Inventory {props.restaurantId} {props.view || "counts"}</p> }));
jest.mock("./components/PrepTab", () => ({ PrepTab: props => <p>TEST ONLY prep context {JSON.stringify(props.initialContext)}</p> }));
let root, container;
const click = text => act(async () => [...container.querySelectorAll("button")].find(b => b.textContent === text).click());
beforeEach(() => {
  global.IS_REACT_ACT_ENVIRONMENT = true; jest.clearAllMocks();
  api.prepExecution.mockResolvedValue(b1Fixture().prep);
  useStoreState.mockImplementation((loc, session, initial) => ({ state: initial, isCurrent: () => true }));
  container = document.createElement("div"); document.body.appendChild(container); root = createRoot(container);
});
afterEach(async () => { await act(async () => root.unmount()); container.remove(); });
async function render(role) { api.currentSession.mockReturnValue({ user: { ...owner, role } }); await act(async () => root.render(<App/>)); }
test.each(["owner", "manager"])("T07/T10/T12 %s enters real B1; existing global Prep and Counts navigation remains independent", async role => {
  await render(role); if (role === "owner") {
    expect(container.textContent).toContain("Owner group");
    expect(container.querySelector('[data-testid="nav-tab-managerOverview"]')).toBeNull();
    await act(async () => container.querySelector('[data-testid="location-tab-berts"]').click());
  }
  await click("Manager overview");
  const overview=container.querySelector('[data-testid="manager-overview"]');
  expect(overview.textContent).toContain("Remaining: 1 lb");
  expect(overview.querySelectorAll("input,select,textarea,form,a")).toHaveLength(0);
  expect([...overview.querySelectorAll("button")].map(b=>b.textContent)).toEqual(["Refresh manager overview"]);
  expect(api.prepExecution).toHaveBeenCalledWith("berts","2026-10-26","daily");
  await click("Prep");expect(container.textContent).toContain("TEST ONLY prep context null");
  await click("Enter Counts");expect(container.textContent).toContain("Actual Inventory berts counts");
  await click("Manager overview");expect(container.textContent).toContain("Remaining: 1 lb");
});
test.each(["staff", "readonly", "unknown"])("T07 %s cannot enter manager overview", async role => {
  await render(role); expect(container.querySelector('[data-testid="nav-tab-managerOverview"]')).toBeNull();expect(api.prepExecution).not.toHaveBeenCalled();
});
test("T09 overview remains accessible when unrelated shared-state loading fails", async () => {
  useStoreState.mockReturnValue({ state: null, isCurrent: () => true, loadError: "TEST ONLY shared-state unavailable" });
  await render("manager"); expect(container.textContent).toContain("shared-state unavailable");
  await click("Manager overview"); expect(container.textContent).toContain("Remaining: 1 lb");
});
