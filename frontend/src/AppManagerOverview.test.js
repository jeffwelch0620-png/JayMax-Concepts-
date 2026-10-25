import React, { act } from "react";
import { createRoot } from "react-dom/client";
import App from "./App";
import * as api from "./lib/api";
import { useStoreState } from "./lib/useStoreState";
import { overviewTestOwner as owner } from "./testFixtures/managerOverview";
jest.mock("./lib/api", () => ({ currentSession: jest.fn(), actualInventoryEnabled: true, prepExecutionEnabled: true, SESSION_EXPIRED_EVENT: "test-expired" }));
jest.mock("./lib/useStoreState", () => ({ useStoreState: jest.fn() }));
jest.mock("./components/AiAssistant", () => ({ AiAssistant: () => null }));
jest.mock("./components/OwnerDashboard", () => ({ OwnerDashboard: () => <p>Owner group</p> }));
jest.mock("./components/ActualInventoryTab", () => ({ ActualInventoryTab: props => <p>TEST ONLY Actual Inventory {props.restaurantId} {props.view || "counts"}</p> }));
jest.mock("./components/ManagerOverviewTab", () => ({ ManagerOverviewTab: props => <div>
  <p>TEST ONLY manager overview {props.rid}</p>
  <button onClick={() => props.onOpenPrep({ rid: props.rid, day: "2026-10-25", track: "bulk" })}>TEST ONLY open prep</button>
  <button onClick={() => props.onOpenCounts({ rid: props.rid })}>TEST ONLY open counts</button>
</div> }));
jest.mock("./components/PrepTab", () => ({ PrepTab: props => <p>TEST ONLY prep context {JSON.stringify(props.initialContext)}</p> }));
let root, container;
const click = text => act(async () => [...container.querySelectorAll("button")].find(b => b.textContent === text).click());
beforeEach(() => {
  global.IS_REACT_ACT_ENVIRONMENT = true;
  useStoreState.mockImplementation((loc, session, initial) => ({ state: initial, isCurrent: () => true }));
  container = document.createElement("div"); document.body.appendChild(container); root = createRoot(container);
});
afterEach(async () => { await act(async () => root.unmount()); container.remove(); });
async function render(role) { api.currentSession.mockReturnValue({ user: { ...owner, role } }); await act(async () => root.render(<App/>)); }
test.each(["owner", "manager"])("%s has the manager overview and retains prep scope", async role => {
  await render(role); if (role === "owner") await act(async () => container.querySelector('[data-testid="location-tab-berts"]').click());
  await click("Manager overview"); await click("TEST ONLY open prep");
  expect(container.textContent).toContain('"rid":"berts","day":"2026-10-25","track":"bulk"');
  await click("Manager overview"); await click("TEST ONLY open counts"); expect(container.textContent).toContain("Actual Inventory berts counts");
});
test.each(["staff", "readonly", "unknown"])("%s cannot enter the manager overview", async role => {
  await render(role); expect(container.querySelector('[data-testid="nav-tab-managerOverview"]')).toBeNull();
});
test("overview remains accessible when unrelated shared-state loading fails", async () => {
  useStoreState.mockReturnValue({ state: null, isCurrent: () => true, loadError: "TEST ONLY shared-state unavailable" });
  await render("manager"); expect(container.textContent).toContain("shared-state unavailable");
  await click("Manager overview"); expect(container.textContent).toContain("TEST ONLY manager overview berts");
});
