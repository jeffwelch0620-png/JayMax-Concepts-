import React, { act } from "react";
import { createRoot } from "react-dom/client";
import { SchedulingTab } from "./SchedulingTab";
import { StaffSheet } from "./StaffSheet";
import * as api from "../lib/api";

jest.mock("../lib/api", () => ({ listStaffTasks: jest.fn(), createStaffTask: jest.fn(), deleteStaffTask: jest.fn(), verifyStaffPin: jest.fn(), staffTaskInbox: jest.fn(), staffCompleteStaffTask: jest.fn(), actualInventoryEnabled: true, staffCountDrafts: jest.fn() }));
jest.mock("../lib/push", () => ({ pushSupported: () => false }));
const gone = { response: { status: 410, data: { detail: "Retained tasks" } } };
const history = { id: "old", title: "Invented historical count", taskType: "count", assignedTo: "Invented cook", dueDate: "2026-10-01", status: "pending", basis: "legacy_staff_task_archive", identityBasis: "legacy_text", archived: true, operational: false };
let container, root;
beforeEach(() => {
  global.IS_REACT_ACT_ENVIRONMENT = true;
  container = document.createElement("div"); document.body.appendChild(container); root = createRoot(container);
  jest.resetAllMocks(); api.verifyStaffPin.mockResolvedValue({ ok: true }); api.staffCountDrafts.mockResolvedValue([]);
});
afterEach(async () => { await act(async () => root.unmount()); container.remove(); });
const render = element => act(async () => root.render(element));
const click = selector => act(async () => container.querySelector(selector).click());
test("retired manager queue explicitly requests labeled history without write controls", async () => {
  api.listStaffTasks.mockRejectedValueOnce(gone).mockResolvedValueOnce([history]);
  await render(<SchedulingTab rid="berts" />);
  expect(api.listStaffTasks.mock.calls).toEqual([["berts"], ["berts", true]]);
  expect(container.textContent).toContain("Historical: pending");
  expect(container.textContent).toContain("Invented cook");
  expect(container.querySelector('[data-testid="assign-task-panel"]')).toBeNull();
  expect(container.querySelector('[data-testid="delete-assigned-task-old"]')).toBeNull();
  expect(api.createStaffTask).not.toHaveBeenCalled(); expect(api.deleteStaffTask).not.toHaveBeenCalled();
});
test("failed archive or unlabeled history cannot become current work or a confirmed empty list", async () => {
  api.listStaffTasks.mockRejectedValueOnce(gone).mockRejectedValueOnce(new Error("Offline"));
  await render(<SchedulingTab rid="berts" />);
  expect(container.querySelector('[role="alert"]').textContent).toContain("Offline");
  expect(container.textContent).not.toContain("No tasks assigned");
  expect(container.querySelector('[data-testid="assign-task-panel"]')).toBeNull();
  api.listStaffTasks.mockRejectedValueOnce(gone).mockResolvedValueOnce([{ ...history, archived: false }]);
  await click('[data-testid="tasks-refresh"]');
  expect(container.querySelector('[role="alert"]').textContent).toContain("was not confirmed");
  expect(container.querySelector('[data-testid="assigned-task-list"]')).toBeNull();
});
test("ordinary load failures disable assignment and preserve retry", async () => {
  api.listStaffTasks.mockRejectedValueOnce(new Error("Offline")); await render(<SchedulingTab rid="berts" />);
  expect(container.querySelector('[data-testid="assign-task-submit"]').disabled).toBe(true);
  expect(container.textContent).not.toContain("No tasks assigned");
  api.listStaffTasks.mockResolvedValueOnce([]); await click('[data-testid="tasks-refresh"]');
  expect(container.querySelector('[role="alert"]')).toBeNull();
  expect(container.textContent).toContain("No tasks assigned");
  expect(container.querySelector('[data-testid="assign-task-submit"]').disabled).toBe(false);
});
test("a late task response cannot replace another location or request its archive", async () => {
  let reject;
  api.listStaffTasks.mockReturnValueOnce(new Promise((resolve, fail) => { reject = fail; })).mockResolvedValueOnce([{ ...history, id: "new", title: "Current Rudds task" }]);
  await render(<SchedulingTab rid="berts" />); await render(<SchedulingTab rid="rudds" />);
  await act(async () => reject(gone));
  expect(container.textContent).toContain("Current Rudds task");
  expect(container.querySelector('[data-testid="task-archive-notice"]')).toBeNull();
  expect(api.listStaffTasks.mock.calls).toEqual([["berts"], ["rudds"]]);
});
async function unlock() {
  await render(<StaffSheet />); await click('[data-testid="staff-store-berts"]'); await click('[data-testid="staff-unlock-button"]');
}
test("retired employee inbox directs staff to reviewed counts without legacy completion", async () => {
  api.staffTaskInbox.mockRejectedValueOnce(gone); await unlock();
  expect(container.querySelector('[data-testid="staff-tasks-retired"]')).not.toBeNull();
  expect(container.querySelector('[data-testid="staff-tasks-empty"]')).toBeNull();
  await click('[data-testid="staff-jump-counts"]');
  expect(api.staffCountDrafts).toHaveBeenCalledWith("berts", "");
  expect(api.staffCompleteStaffTask).not.toHaveBeenCalled();
});
test("inbox failure clears stale completion instead of implying no tasks", async () => {
  api.staffTaskInbox.mockResolvedValueOnce({ date: "2026-10-01", tasks: [history] }); await unlock();
  api.staffTaskInbox.mockRejectedValueOnce(new Error("Offline")); await click('[data-testid="staff-refresh"]');
  expect(container.textContent).toContain("Tasks could not be loaded");
  expect(container.querySelector('[data-testid="staff-tasks-empty"]')).toBeNull();
  expect(container.querySelector('[data-testid="staff-task-done-old"]')).toBeNull();
});
