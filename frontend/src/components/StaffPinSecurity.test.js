import React, { act } from "react";
import { createRoot } from "react-dom/client";
import { StaffSheet } from "./StaffSheet";
import * as api from "../lib/api";

jest.mock("../lib/api", () => ({ verifyStaffPin: jest.fn(), identifyStaffMember: jest.fn(),
  staffTaskInbox: jest.fn(), staffPrepsheet: jest.fn(), staffCounts: jest.fn(), storeSession: jest.fn(),
  staffPrepTasksEnabled: false, actualInventoryEnabled: false, staffPrepCountsEnabled: false }));
jest.mock("../lib/push", () => ({ pushSupported: () => false }));
const member = { id: "test-only-owner-admin", name: "TEST ONLY Claimed Manager", role: "owner_admin" };
let root, container;
beforeEach(() => {
  global.IS_REACT_ACT_ENVIRONMENT = true;
  jest.resetAllMocks();
  api.verifyStaffPin.mockResolvedValue({ ok: true, staff: [member] });
  api.identifyStaffMember.mockResolvedValue({ ok: true, name: member.name, role: member.role,
    session: { token: "unexpected-old-response", user: { role: "manager" } } });
  api.staffTaskInbox.mockResolvedValue({ tasks: [] });
  api.staffPrepsheet.mockResolvedValue({ listId: null, tasks: [] });
  api.staffCounts.mockResolvedValue({ date: "2026-10-21", items: [] });
  container = document.createElement("div"); document.body.appendChild(container); root = createRoot(container);
});
afterEach(async () => { await act(async () => root.unmount()); container.remove(); });
const render = props => act(async () => root.render(<StaffSheet {...props} />));
const click = selector => act(async () => container.querySelector(selector).click());
async function unlock() {
  await click('[data-testid="staff-store-berts"]');
  const field = container.querySelector('[data-testid="staff-pin-entry"]');
  await act(async () => {
    Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value").set.call(field, "4826");
    field.dispatchEvent(new Event("input", { bubbles: true }));
  });
  await click('[data-testid="staff-unlock-button"]');
}

test("claimed owner/admin selection ignores even an old response carrying a session", async () => {
  const elevate = jest.fn(); const login = jest.fn();
  await render({ onElevate: elevate, onPersonalLogin: login }); await unlock();
  await click(`[data-testid="staff-roster-pick-${member.id}"]`);
  expect(api.identifyStaffMember).toHaveBeenCalledWith("berts", "4826", member.id);
  expect(elevate).not.toHaveBeenCalled(); expect(api.storeSession).not.toHaveBeenCalled();
  expect(login).not.toHaveBeenCalled();
  expect(container.querySelector('[data-testid="staff-pin-gate"]')).toBeNull();
  expect(container.textContent).toContain("requires personal sign-in");
});

test("manager/owner action goes to personal login without verifying a PIN or minting a session", async () => {
  const login = jest.fn(); await render({ onPersonalLogin: login });
  await click('[data-testid="staff-personal-login"]');
  expect(login).toHaveBeenCalledTimes(1);
  expect(api.verifyStaffPin).not.toHaveBeenCalled(); expect(api.storeSession).not.toHaveBeenCalled();
});

test.each([
  [403, "Staff PIN portal is disabled. Ask a manager to set a PIN."],
  [429, "Too many staff PIN attempts. Try again later."],
  [503, "Staff PIN verification is temporarily unavailable."]
])("PIN refusal %s keeps the portal locked and gives the server's safe message", async (status, detail) => {
  api.verifyStaffPin.mockRejectedValue({ response: { status, data: { detail } } });
  await render(); await unlock();
  expect(container.textContent).toContain(detail);
  expect(container.querySelector('[data-testid="staff-pin-gate"]')).toBeTruthy();
  expect(api.staffTaskInbox).not.toHaveBeenCalled(); expect(api.identifyStaffMember).not.toHaveBeenCalled();
});

test("configured-PIN tasks, prep and counts still use staff paths without elevation", async () => {
  await render(); await unlock(); await click(`[data-testid="staff-roster-pick-${member.id}"]`);
  expect(api.staffTaskInbox).toHaveBeenCalled();
  await click('[data-testid="staff-view-prep"]'); expect(api.staffPrepsheet).toHaveBeenCalled();
  await click('[data-testid="staff-view-counts"]'); expect(api.staffCounts).toHaveBeenCalled();
  expect(api.storeSession).not.toHaveBeenCalled();
});
