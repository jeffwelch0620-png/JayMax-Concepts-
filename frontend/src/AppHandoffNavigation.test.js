import React, { act } from "react";
import { createRoot } from "react-dom/client";
import App from "./App";
import * as api from "./lib/api";
import { useStoreState } from "./lib/useStoreState";
import { resetComponentApiMock } from "./testHelpers/componentApiMock";
import { overviewFixture } from "./testFixtures/managerOverview";
jest.mock("./lib/api", () => require("./testHelpers/componentApiMock").createComponentApiMock());
jest.mock("./lib/useStoreState", () => ({ useStoreState: jest.fn() }));
jest.mock("./lib/calc", () => ({ ...jest.requireActual("./lib/calc"), todayISO: () => "2026-10-26" }));
jest.mock("./components/AiAssistant", () => ({ AiAssistant: () => null }));
jest.mock("./components/ManagerHandoffTab", () => ({ ManagerHandoffTab: props => <p data-testid="receiving-handoff">{JSON.stringify({ rid: props.rid, actor: props.user.id, focus: props.initialContext })}</p> }));
let root, container;
const button = text => [...container.querySelectorAll("button")].find(b => b.textContent === text);
const click = el => act(async () => el.click());
beforeEach(() => {
  global.IS_REACT_ACT_ENVIRONMENT = true; window.sessionStorage.clear(); resetComponentApiMock(api);
  Object.assign(api, { managerHandoffEnabled: true, actualInventoryEnabled: true, prepExecutionEnabled: true });
  api.currentSession.mockReturnValue({ user: { id: "usr_manager", role: "manager", locations: ["berts", "rudds"] } });
  api.actualCounts.mockImplementation(async rid => overviewFixture(rid).counts);
  api.prepExecution.mockImplementation(async (rid, day, track) => overviewFixture(rid, day, track).prep);
  useStoreState.mockImplementation(() => ({ state: null, isCurrent: () => true }));
  container = document.createElement("div"); document.body.appendChild(container); root = createRoot(container);
});
afterEach(async () => { await act(async () => root.unmount()); container.remove(); });
test("overview handoff link preserves the selected day/track independently of legacy state loading", async () => {
  await act(async () => root.render(<App/>)); await click(container.querySelector('[data-testid="nav-tab-managerOverview"]'));
  const date = container.querySelector('[aria-label="Manager overview date"]');
  await act(async () => { Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value").set.call(date, "2026-10-25"); date.dispatchEvent(new Event("input", { bubbles: true })); });
  await click(button("Open dated manager handoff"));
  expect(JSON.parse(container.querySelector('[data-testid="receiving-handoff"]').textContent)).toEqual({ rid: "berts", actor: "usr_manager", focus: { rid: "berts", day: "2026-10-25", track: "bulk" } });
  await click(container.querySelector('[data-testid="nav-tab-managerHandoff"]'));
  expect(JSON.parse(container.querySelector('[data-testid="receiving-handoff"]').textContent).focus).toBeNull();
  await click(container.querySelector('[data-testid="location-tab-rudds"]'));
  await click(container.querySelector('[data-testid="nav-tab-managerHandoff"]'));
  expect(JSON.parse(container.querySelector('[data-testid="receiving-handoff"]').textContent)).toEqual({ rid: "rudds", actor: "usr_manager", focus: null });
  expect(api.saveHandoff).not.toHaveBeenCalled();
});
test.each(["staff", "readonly"])("%s has no manager handoff entry", async role => {
  api.currentSession.mockReturnValue({ user: { id: "usr_other", role, locations: ["berts"] } });
  await act(async () => root.render(<App/>)); expect(container.querySelector('[data-testid="nav-tab-managerHandoff"]')).toBeNull();
});
test("capability off preserves overview reads and hides both handoff entry points", async () => {
  api.managerHandoffEnabled = false; await act(async () => root.render(<App/>));
  expect(container.querySelector('[data-testid="nav-tab-managerHandoff"]')).toBeNull();
  await click(container.querySelector('[data-testid="nav-tab-managerOverview"]'));
  expect(button("Open dated manager handoff")).toBeUndefined(); expect(api.handoffDay).not.toHaveBeenCalled();
});
