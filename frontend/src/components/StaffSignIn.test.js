import React, { act } from "react";
import { createRoot } from "react-dom/client";
import { StaffSignIn } from "./StaffSignIn";
import * as api from "../lib/api";

jest.mock("../lib/api", () => ({ __esModule: true, rememberedStaff: jest.fn(), rememberStaff: jest.fn(), staffSignInNames: jest.fn(), staffSignIn: jest.fn(), keepStaffSession: jest.fn() }));
let root, container;
beforeEach(() => {
  jest.useFakeTimers(); global.IS_REACT_ACT_ENVIRONMENT = true;
  root = createRoot(container = document.createElement("div")); document.body.appendChild(container); jest.clearAllMocks();
  api.rememberedStaff.mockReturnValue(null);
});
afterEach(async () => { await act(async () => root.unmount()); container.remove(); jest.useRealTimers(); });
const render = el => act(async () => root.render(el));
const q = id => container.querySelector(`[data-testid="${id}"]`);
async function type(id, value) {
  const el = q(id);
  const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, "value").set;
  await act(async () => { setter.call(el, value); el.dispatchEvent(new Event("input", { bubbles: true })); });
}
const click = id => act(async () => q(id).click());
const settle = () => act(async () => { jest.advanceTimersByTime(250); await Promise.resolve(); });

test("names appear from 2 letters and an employee signs in with their PIN", async () => {
  api.staffSignInNames.mockResolvedValue([{ id: "m-a", name: "Invented cook A" }]);
  api.staffSignIn.mockResolvedValue({ token: "t", staff_member_id: "m-a", name: "Invented cook A" });
  const onSignedIn = jest.fn();
  await render(<StaffSignIn rid="berts" setRid={() => {}} onSignedIn={onSignedIn} />);
  await type("staff-name-entry", "i"); await settle();
  expect(api.staffSignInNames).not.toHaveBeenCalled();             // the roster is never listed
  await type("staff-name-entry", "in"); await settle();
  expect(api.staffSignInNames).toHaveBeenCalledWith("berts", "in");
  await click("staff-name-m-a");
  await click("staff-remember-me");
  await type("staff-pin-entry", "7350");
  await click("staff-sign-in-button");
  expect(api.staffSignIn).toHaveBeenCalledWith("berts", { staff_member_id: "m-a", pin: "7350" });
  expect(api.rememberStaff).toHaveBeenCalledWith("berts", { id: "m-a", name: "Invented cook A" });
  expect(onSignedIn).toHaveBeenCalled();
});

test("a first PIN is replaced before signing in", async () => {
  api.rememberedStaff.mockReturnValue({ rid: "berts", id: "m-a", name: "Invented cook A" });
  api.staffSignIn
    .mockRejectedValueOnce({ response: { status: 409, data: { detail: { code: "pin_change_required", message: "Choose your own PIN" } } } })
    .mockResolvedValueOnce({ token: "t", staff_member_id: "m-a", name: "Invented cook A" });
  const onSignedIn = jest.fn();
  await render(<StaffSignIn rid="berts" setRid={() => {}} onSignedIn={onSignedIn} />);
  expect(q("staff-sign-in-name").textContent).toContain("Invented cook A");   // remembered: no typing
  await type("staff-pin-entry", "4821");
  await click("staff-sign-in-button");
  expect(q("staff-new-pin")).not.toBeNull();
  await type("staff-new-pin-entry", "7350"); await type("staff-new-pin-confirm", "7351");
  await click("staff-sign-in-button");
  expect(q("staff-error").textContent).toContain("don't match");
  await type("staff-new-pin-confirm", "7350");
  await click("staff-sign-in-button");
  expect(api.staffSignIn).toHaveBeenLastCalledWith("berts", { staff_member_id: "m-a", pin: "4821", new_pin: "7350" });
  expect(onSignedIn).toHaveBeenCalled();
});

test("a wrong PIN or a lockout shows the server's message, and Not you? forgets the name", async () => {
  api.rememberedStaff.mockReturnValue({ rid: "berts", id: "m-a", name: "Invented cook A" });
  api.staffSignIn.mockRejectedValue({ response: { status: 423, data: { detail: "Too many wrong PINs. Try again after 14:30, or ask a manager to unlock you." } } });
  await render(<StaffSignIn rid="berts" setRid={() => {}} onSignedIn={() => {}} />);
  await type("staff-pin-entry", "1111");
  await click("staff-sign-in-button");
  expect(q("staff-error").textContent).toContain("ask a manager to unlock");
  expect(q("staff-pin-entry").value).toBe("");
  await click("staff-not-me");
  expect(api.rememberStaff).toHaveBeenCalledWith("berts", null);
  expect(q("staff-name-entry")).not.toBeNull();
});

test("a sign-in abandoned with Not you? never keeps or uses its session", async () => {
  api.rememberedStaff.mockReturnValue({ rid: "berts", id: "m-a", name: "Invented cook A" });
  let finish;
  api.staffSignIn.mockReturnValue(new Promise(r => { finish = r; }));
  const onSignedIn = jest.fn();
  await render(<StaffSignIn rid="berts" setRid={() => {}} onSignedIn={onSignedIn} />);
  await type("staff-pin-entry", "7350");
  await click("staff-sign-in-button");
  await click("staff-sign-in-button");                                // a second tap while pending is ignored
  expect(api.staffSignIn).toHaveBeenCalledTimes(1);
  await click("staff-not-me");
  await act(async () => finish({ token: "t", staff_member_id: "m-a", name: "Invented cook A", rid: "berts" }));
  expect(api.keepStaffSession).not.toHaveBeenCalled();
  expect(onSignedIn).not.toHaveBeenCalled();
});

test("changing stores while a sign-in is pending lets the employee sign in at the new store", async () => {
  api.rememberedStaff.mockReturnValue({ rid: "berts", id: "m-a", name: "Invented cook A" });
  let finish;
  api.staffSignIn.mockReturnValueOnce(new Promise(r => { finish = r; }));
  await render(<StaffSignIn rid="berts" setRid={() => {}} onSignedIn={() => {}} />);
  await type("staff-pin-entry", "7350");
  await click("staff-sign-in-button");
  expect(q("staff-sign-in-button").disabled).toBe(true);
  await render(<StaffSignIn rid="rudds" setRid={() => {}} onSignedIn={() => {}} />);
  expect(q("staff-sign-in-button").disabled).toBe(false);
  await act(async () => finish({ token: "t", staff_member_id: "m-a", name: "Invented cook A", rid: "berts" }));
  expect(q("staff-sign-in-button").disabled).toBe(false);
  expect(api.keepStaffSession).not.toHaveBeenCalled();
});
