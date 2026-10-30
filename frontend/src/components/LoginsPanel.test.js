import React, { act } from "react";
import { createRoot } from "react-dom/client";
import { LoginsPanel } from "./LoginsPanel";
import * as api from "../lib/api";

jest.mock("../lib/api", () => ({ __esModule: true, currentSession: jest.fn(), listLogins: jest.fn(), createLogin: jest.fn(), setLoginAccess: jest.fn(), resetLoginPassword: jest.fn(), deleteLogin: jest.fn() }));
let root, container;
beforeEach(() => {
  global.IS_REACT_ACT_ENVIRONMENT = true;
  root = createRoot(container = document.createElement("div")); document.body.appendChild(container); jest.clearAllMocks();
  api.currentSession.mockReturnValue({ user: { id: "usr_owner", role: "owner" } });
});
afterEach(async () => { await act(async () => root.unmount()); container.remove(); });
const render = el => act(async () => root.render(el));
const click = el => act(async () => el.click());
const byTest = id => container.querySelector(`[data-testid="${id}"]`);
const button = text => [...container.querySelectorAll("button")].find(b => b.textContent === text);
async function input(el, value) { await act(async () => { Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value").set.call(el, value); el.dispatchEvent(new Event("input", { bubbles: true })); }); }
async function choose(el, value) { await act(async () => { el.value = value; el.dispatchEvent(new Event("change", { bubbles: true })); }); }

test("a new login can be given a position, which sets its access class", async () => {
  api.listLogins.mockResolvedValue([]);
  api.createLogin.mockResolvedValue({});
  await render(<LoginsPanel />);
  await input(byTest("login-add-email"), "km.berts@example.invalid");
  await input(byTest("login-add-password"), "invented-password-123");
  await choose(byTest("login-add-position"), "KM");
  expect(byTest("login-add-role")).toBeNull(); // the position decides manager / staff / owner
  await click(byTest("login-add-loc-berts"));
  await click(byTest("login-add-submit"));
  expect(api.createLogin).toHaveBeenCalledWith(expect.objectContaining({ email: "km.berts@example.invalid", position: "KM", role: "manager", locations: ["berts"] }));
});

test("an existing login's position and stores can be changed", async () => {
  api.listLogins.mockResolvedValue([{ id: "usr_1", email: "lead@example.invalid", role: "manager", locations: ["rudds"], position: null }]);
  api.setLoginAccess.mockResolvedValue({ id: "usr_1", role: "manager", position: "BPM", locations: ["berts", "rudds"] });
  await render(<LoginsPanel showToast={jest.fn()} />);
  expect(byTest("login-usr_1").textContent).toContain("manager");
  await click(byTest("login-edit-usr_1"));
  await choose(byTest("login-position-usr_1"), "BPM");
  await click([...byTest("login-access-usr_1").querySelectorAll("input[type=checkbox]")][0]); // Bert's
  await click(button("Save"));
  expect(api.setLoginAccess).toHaveBeenCalledWith("usr_1", { position: "BPM", locations: ["rudds", "berts"] });
  expect(api.listLogins).toHaveBeenCalledTimes(2);
});
