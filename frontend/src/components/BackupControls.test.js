import React, { act } from "react";
import { createRoot } from "react-dom/client";
import { BackupControls } from "./BackupControls";

let container, root;
beforeEach(() => {
  global.IS_REACT_ACT_ENVIRONMENT = true;
  container = document.createElement("div"); document.body.appendChild(container); root = createRoot(container);
});
afterEach(async () => { await act(async () => root.unmount()); container.remove(); });

test("native inventory cannot download an incomplete backup or start legacy restore", async () => {
  const backup = jest.fn(), restore = jest.fn();
  await act(async () => root.render(<BackupControls nativeMode onBackup={backup} onRestore={restore} />));
  for (const button of container.querySelectorAll("button")) {
    expect(button.disabled).toBe(true); await act(async () => button.click());
  }
  expect(backup).not.toHaveBeenCalled(); expect(restore).not.toHaveBeenCalled();
  expect(container.querySelector('[role="status"]').textContent).toContain("physical counts and closed reports");
});

test("legacy mode retains existing backup and restore actions", async () => {
  const backup = jest.fn(), restore = jest.fn();
  await act(async () => root.render(<BackupControls nativeMode={false} onBackup={backup} onRestore={restore} />));
  const buttons = container.querySelectorAll("button");
  await act(async () => { buttons[0].click(); buttons[1].click(); });
  expect(backup).toHaveBeenCalledTimes(1); expect(restore).toHaveBeenCalledTimes(1);
  expect(container.querySelector('[role="status"]')).toBeNull();
});
