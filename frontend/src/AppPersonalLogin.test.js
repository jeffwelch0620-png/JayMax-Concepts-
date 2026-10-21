import React, { act } from "react";
import { createRoot } from "react-dom/client";
import App from "./App";
import * as api from "./lib/api";

jest.mock("./lib/api", () => ({ currentSession: jest.fn(() => null), authLogin: jest.fn(), storeSession: jest.fn(), SESSION_EXPIRED_EVENT: "test-only-session-expired" }));
jest.mock("./lib/useStoreState", () => ({ useStoreState: (loc, session, initial) => ({ state: initial, isCurrent: () => true }) }));
jest.mock("./lib/push", () => ({ pushSupported: () => false }));
jest.mock("./components/DashboardTab", () => ({ DashboardTab: () => <p>TEST ONLY personal workspace</p> }));

test("staff portal returns to the real personal-login form and accepts its own session response", async () => {
  global.IS_REACT_ACT_ENVIRONMENT = true;
  api.authLogin.mockResolvedValue({ user: { id: "usr_test_only", email: "owner@example.test", role: "owner", locations: ["berts"] }, token: "test-only-personal-response" });
  const container = document.createElement("div"); document.body.appendChild(container);
  const root = createRoot(container);
  try {
    await act(async () => root.render(<App />));
    const staff = [...container.querySelectorAll("button")].find(b => b.textContent === "Staff sign-in with PIN");
    await act(async () => staff.click());
    await act(async () => container.querySelector('[data-testid="staff-personal-login"]').click());
    expect(container.querySelector('[data-testid="staff-sheet"]')).toBeNull();
    expect(container.querySelector('[data-testid="login-notice"]').textContent).toContain("personal account");
    for (const [type, value] of [["email", "owner@example.test"], ["password", "fictional-personal-password-only"]]) {
      const input = container.querySelector(`input[type="${type}"]`);
      await act(async () => {
        Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value").set.call(input, value);
        input.dispatchEvent(new Event("input", { bubbles: true }));
      });
    }
    await act(async () => container.querySelector("form").dispatchEvent(new Event("submit", { bubbles: true, cancelable: true })));
    expect(api.authLogin).toHaveBeenCalledWith("owner@example.test", "fictional-personal-password-only");
    expect(container.querySelector('[data-testid="sign-out"]').textContent).toContain("owner@example.test");
    expect(container.textContent).toContain("TEST ONLY personal workspace");
    expect(api.storeSession).not.toHaveBeenCalled();
  } finally {
    await act(async () => root.unmount()); container.remove();
  }
});
