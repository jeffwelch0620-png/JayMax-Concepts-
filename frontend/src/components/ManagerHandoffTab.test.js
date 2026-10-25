import React, { act } from "react";
import { createRoot } from "react-dom/client";
import { webcrypto } from "crypto";
import { TextEncoder } from "util";
import { ManagerHandoffTab } from "./ManagerHandoffTab";
import * as api from "../lib/api";
import { resetComponentApiMock } from "../testHelpers/componentApiMock";
import { handoffJournal, handoffFingerprint } from "../lib/managerHandoff";
import { handoffOwner as user, handoffBody as body, handoffDay as day, handoffState as state,
  handoffNote as note, handoffReceipt as receipt, handoffId } from "../testFixtures/managerHandoff";
jest.mock("../lib/api", () => require("../testHelpers/componentApiMock").createComponentApiMock());
jest.mock("../lib/calc", () => ({ ...jest.requireActual("../lib/calc"), todayISO: () => "2026-10-25" }));
let root, container, drafts, showToast;
const input = label => container.querySelector(`[aria-label="${label}"]`);
const button = text => [...container.querySelectorAll("button")].find(b => b.textContent === text);
const flush = () => act(async () => { await new Promise(resolve => setTimeout(resolve, 20)); });
const click = async text => { await act(async () => button(text).click()); await flush(); };
const render = async (props = {}) => { await act(async () => root.render(<ManagerHandoffTab rid="berts" user={user} drafts={drafts} showToast={showToast} {...props}/>)); await flush(); };
async function set(label, value) {
  const el = input(label), proto = el.tagName === "TEXTAREA" ? HTMLTextAreaElement.prototype : el.tagName === "SELECT" ? HTMLSelectElement.prototype : HTMLInputElement.prototype;
  await act(async () => { Object.getOwnPropertyDescriptor(proto, "value").set.call(el, value); el.dispatchEvent(new Event(el.tagName === "SELECT" ? "change" : "input", { bubbles: true })); });
}
async function retained() {
  const b = body(); const r = { key: handoffId, body: b, version: 0, fingerprint: await handoffFingerprint(user.id, "berts", b, 0) };
  handoffJournal(user.id, "berts").save(r); return r;
}
beforeAll(() => { Object.defineProperty(window, "crypto", { configurable: true, value: webcrypto }); global.TextEncoder = TextEncoder; });
beforeEach(() => {
  global.IS_REACT_ACT_ENVIRONMENT = true; window.sessionStorage.clear(); resetComponentApiMock(api);
  drafts = new Map(); showToast = jest.fn(); api.handoffDay.mockResolvedValue(state());
  api.saveHandoff.mockImplementation(async (rid, b, version, key) => {
    const r = handoffJournal(user.id, rid).read(); expect(r).toMatchObject({ key, version, body: b }); return receipt(r);
  });
  container = document.createElement("div"); document.body.appendChild(container); root = createRoot(container);
});
afterEach(async () => { await act(async () => root.unmount()); container.remove(); jest.restoreAllMocks(); });
test("save persists exact request first, then submit and correct append explicit commands", async () => {
  await render(); expect(drafts.size).toBe(0); expect(container.textContent).toContain("does not transfer responsibility");
  await set("Handoff summary", "TEST ONLY production summary"); await set("Handoff next note", "Check portions");
  await click("Save handoff draft"); expect(showToast).toHaveBeenCalledTimes(1); expect(drafts.size).toBe(0);
  expect(handoffJournal(user.id, "berts").read()).toBeNull();
  await set("Handoff summary", "Edited draft"); expect(button("Submit saved handoff note").disabled).toBe(true);
  await click("Save handoff draft"); await click("Submit saved handoff note");
  expect(api.saveHandoff.mock.calls.map(c => c[1].action)).toEqual(["create_draft", "save_draft", "submit"]);
  await set("Handoff summary", "Corrected production report"); await set("Handoff correction reason", "Measured later");
  await click("Save handoff correction"); expect(api.saveHandoff.mock.calls[3][1]).toMatchObject({ action: "correct", correction_reason: "Measured later" });
});
test("blank or invalid input and unavailable storage never send a mutation", async () => {
  await render(); await click("Save handoff draft"); expect(api.saveHandoff).not.toHaveBeenCalled();
  await set("Handoff summary", "Valid text"); jest.spyOn(Storage.prototype, "setItem").mockImplementation(() => { throw Error(); });
  await click("Save handoff draft"); expect(api.saveHandoff).not.toHaveBeenCalled(); expect(container.textContent).toContain("not confirmed");
});
test("lost response freezes editing and exact retry keeps key, version and content", async () => {
  api.saveHandoff.mockRejectedValueOnce(Error("response dropped")); await render(); await set("Handoff summary", "TEST ONLY dropped");
  await click("Save handoff draft"); const original = handoffJournal(user.id, "berts").read(); expect(original).toBeTruthy();
  expect(input("Handoff summary").closest("fieldset").disabled).toBe(true); expect(input("Handoff date").disabled).toBe(true);
  await click("Retry exact handoff request"); expect(api.saveHandoff.mock.calls[1]).toEqual(api.saveHandoff.mock.calls[0]);
  expect(handoffJournal(user.id, "berts").read()).toBeNull();
});
test("reload and same personal account recover via receipt without another command or rollback", async () => {
  const r = await retained(), newer = note({ revision: 3, action: "save_draft", summary: "Newer manager report", actor_id: "usr_other" });
  api.handoffDay.mockResolvedValue(state({ current: newer })); api.handoffStatus.mockResolvedValue({ ...receipt(r, newer), outcome: "saved" });
  await render(); expect(container.querySelector('[aria-label="Retained handoff request"] h2').textContent).toBe("Retained request · 2026-10-25 · bulk"); await click("Check retained handoff status");
  expect(api.saveHandoff).not.toHaveBeenCalled(); expect(input("Handoff summary").value).toBe(newer.summary);
  expect(handoffJournal(user.id, "berts").read()).toBeNull();
});
test("unconfirmed status holds the exact request until explicit discard and fresh read", async () => {
  const r = await retained(); api.handoffStatus.mockResolvedValue({ ...receipt(r), current: null, outcome: "unconfirmed" });
  await render(); await click("Check retained handoff status"); expect(handoffJournal(user.id, "berts").read()).toEqual(r);
  expect(container.textContent).toContain("original may still complete"); jest.spyOn(window, "confirm").mockReturnValue(true);
  await click("Discard browser recovery"); expect(button("Save handoff draft")).toBeUndefined();
  await click("Refresh handoff note"); expect(button("Save handoff draft")).toBeTruthy(); expect(api.saveHandoff).not.toHaveBeenCalled();
});
test("a receipt can clear recovery while the separate day read remains unavailable", async () => {
  const r = await retained(); api.handoffDay.mockRejectedValue(Error()); api.handoffStatus.mockResolvedValue({ ...receipt(r), outcome: "saved" });
  await render(); await click("Check retained handoff status"); expect(handoffJournal(user.id, "berts").read()).toBeNull();
  expect(container.textContent).toContain("Awaiting a confirmed"); expect(button("Save handoff draft")).toBeUndefined();
});
test("stale drafts require explicit review/rebase and retain text across panel remounts", async () => {
  api.handoffDay.mockResolvedValue(state({ current: note() })); await render(); await set("Handoff summary", "Unsaved manager text");
  api.handoffDay.mockResolvedValue(state({ current: note({ revision: 2, action: "save_draft", summary: "Other edit" }) }));
  await click("Refresh handoff note"); expect(input("Handoff summary").value).toBe("Unsaved manager text");
  expect(button("Save handoff draft").disabled).toBe(true); await click("Review current version and keep edits");
  await click("Save handoff draft"); expect(api.saveHandoff.mock.calls[0][2]).toBe(2);
});
test("corrupt or altered retained content blocks mutation before reads", async () => {
  const r = await retained(); const key = `jaymax:manager-handoff:v1:${user.id}:berts`;
  const wrapper = JSON.parse(window.sessionStorage.getItem(key)); wrapper.request.body.summary = "altered without matching hash";
  window.sessionStorage.setItem(key, JSON.stringify(wrapper)); await render();
  expect(container.textContent).toContain("Browser recovery is unavailable"); expect(api.handoffDay).not.toHaveBeenCalled(); expect(api.saveHandoff).not.toHaveBeenCalled(); expect(r).toBeTruthy();
});
test("account switch and late responses cannot overwrite another account's form or recovery", async () => {
  let resolve; api.saveHandoff.mockImplementation(() => new Promise(r => { resolve = r; })); await render();
  await set("Handoff summary", "First account text"); await click("Save handoff draft"); const r = handoffJournal(user.id, "berts").read();
  const other = { id: "usr_second", role: "owner", locations: [] }; api.handoffDay.mockResolvedValue(state({ actor_id: other.id }));
  await render({ user: other }); await act(async () => resolve(receipt(r))); await flush();
  expect(input("Handoff summary").value).toBe(""); expect(handoffJournal(user.id, "berts").read()).toEqual(r); expect(showToast).not.toHaveBeenCalled();
});
test("history is explicit and invalid or changed pages never become accepted evidence", async () => {
  api.handoffDay.mockResolvedValue(state({ current: note() })); await render();
  api.handoffHistory.mockResolvedValue({ store_id: "berts", actor_id: user.id, note_id: handoffId, current_revision: 1, after: 0, rows: [receipt(await retained()).accepted], next_after: null });
  await click("Refresh handoff history"); expect(container.textContent).toContain("complete for this read");
  api.handoffHistory.mockResolvedValue({ store_id: "rudds" }); await click("Refresh handoff history");
  expect(container.textContent).toContain("History changed or could not be confirmed"); expect(api.saveHandoff).not.toHaveBeenCalled();
});
test("missing timezone read holds the form and invalid personal role never reads", async () => {
  api.handoffDay.mockResolvedValue(state({ settings: null })); await render(); expect(button("Save handoff draft")).toBeUndefined();
  api.handoffDay.mockClear(); await render({ user: { ...user, role: "staff" } }); expect(api.handoffDay).not.toHaveBeenCalled();
});
test("a refused fresh authorization never displays retained note text or permits a write", async () => {
  const r = await retained(); api.handoffDay.mockRejectedValue({ response: { status: 403 } });
  await render(); expect(container.textContent).not.toContain(r.body.summary);
  expect(button("Retry exact handoff request").disabled).toBe(true); expect(input("Handoff summary")).toBeNull();
  api.handoffStatus.mockRejectedValue({ response: { status: 403 } }); await click("Check retained handoff status");
  expect(container.textContent).not.toContain(r.body.summary); expect(handoffJournal(user.id, "berts").read()).toEqual(r); expect(api.saveHandoff).not.toHaveBeenCalled();
});
test("previous submitted production summary and next-shift text remain distinct across missing days", async () => {
  api.handoffDay.mockResolvedValue(state({ previous: note({ business_date: "2026-10-23", status: "submitted", action: "submit",
    first_submitted_at: "2026-10-23T14:00:00Z", summary: "TEST ONLY previous batch report", next_shift_note: "TEST ONLY verify chilled portions" }) }));
  await render(); const previous = container.querySelector('[aria-label="Previous submitted handoff"]');
  expect(previous.textContent).toContain("2026-10-23"); expect(previous.textContent).toContain("TEST ONLY previous batch report");
  expect(previous.textContent).toContain("TEST ONLY verify chilled portions"); expect(api.saveHandoff).not.toHaveBeenCalled();
});
