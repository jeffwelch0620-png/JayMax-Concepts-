import React, { act } from "react";
import { createRoot } from "react-dom/client";
import { ManualForecast } from "./ManualForecast";
import { AiAssistant } from "./AiAssistant";
import * as api from "../lib/api";
jest.mock("../lib/api", () => ({ getProjections: jest.fn(), getProjectionReview: jest.fn(), putProjection: jest.fn(), aiHistory: jest.fn(), aiCapabilities: jest.fn(), aiClear: jest.fn(), streamChat: jest.fn() }));
const deferred = () => { let resolve, reject; const promise = new Promise((a, b) => { resolve = a; reject = b; }); return { promise, resolve, reject }; };
const version = "a".repeat(64), nextVersion = "b".repeat(64);
const review = (rid, date, projection = null, sourceVersion = version) => ({ restaurantId: rid, storeId: rid === "papa_leonis" ? "papa" : rid, date, projection, sourceVersion, basis: "manual_sales_forecast", accounting: false });
const caps = (rid, write = false) => ({ storeId: rid === "papa_leonis" ? "papa" : rid, basis: "ai_conversation_storage", accounting: false, historyAvailable: true, chatAvailable: write, clearAvailable: write });
let root, container, drafts, toast;
const find = id => container.querySelector(`[data-testid="${id}"]`);
const render = value => act(async () => root.render(value));
const click = id => act(async () => find(id).click());
async function input(id, value) { await act(async () => {
  const element = find(id); Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value").set.call(element, value);
  element.dispatchEvent(new Event("input", { bubbles: true }));
}); }
const forecast = (rid = "berts") => <ManualForecast key={rid} rid={rid} drafts={drafts} showToast={toast}/>;
const assistant = (rid = "berts", open = true) => <AiAssistant rid={rid} setRid={jest.fn()} open={open} onClose={jest.fn()}/>;
beforeEach(() => {
  global.IS_REACT_ACT_ENVIRONMENT = true; jest.clearAllMocks();
  Element.prototype.scrollIntoView = jest.fn();
  api.getProjections.mockResolvedValue([]);
  api.getProjectionReview.mockImplementation((rid, date) => Promise.resolve(review(rid, date)));
  api.putProjection.mockImplementation((rid, body) => Promise.resolve({ ok: true, ...review(rid, body.date, { ...review(rid, body.date, null, nextVersion), ...body, enteredBy: "signed actor", updatedAt: "2026-10-09T00:00:00Z" }, nextVersion) }));
  api.aiHistory.mockImplementation(rid => Promise.resolve([{ restaurantId: rid, role: "user", content: `${rid} retained history` }]));
  api.aiCapabilities.mockImplementation(rid => Promise.resolve(caps(rid)));
  api.aiClear.mockResolvedValue({ ok: true });
  container = document.createElement("div"); document.body.appendChild(container); root = createRoot(container);
  drafts = new Map(); toast = jest.fn();
});
afterEach(async () => { await act(async () => root.unmount()); container.remove(); });

test("forecasts require reviewed dates and send exact decimal strings, including zero", async () => {
  await render(forecast()); await input("projection-amount", "0");
  expect(find("projection-save-button").disabled).toBe(true);
  await click("projection-review-button"); await click("projection-save-button");
  expect(api.putProjection).toHaveBeenCalledWith("berts", expect.objectContaining({ amount: "0" }), version);
  expect(toast).toHaveBeenCalledTimes(1); expect(find("projection-amount").value).toBe("");
});
test.each([409, "offline", "bad-ack"])("forecast failure %s retains its draft and requires another review", async reason => {
  if (reason === "bad-ack") api.putProjection.mockResolvedValueOnce({ ok: true });
  else api.putProjection.mockRejectedValueOnce(new Error(String(reason)));
  await render(forecast()); await input("projection-amount", "123.45"); await input("projection-note", "Retain this");
  await click("projection-review-button"); await click("projection-save-button");
  expect(find("projection-amount").value).toBe("123.45"); expect(find("projection-save-button").disabled).toBe(true); expect(toast).not.toHaveBeenCalled();
  await render(<p>Other tab</p>); await render(forecast());
  expect(find("projection-note").value).toBe("Retain this"); expect(find("projection-save-button").disabled).toBe(true);
  await click("projection-review-button"); await click("projection-save-button"); expect(toast).toHaveBeenCalledTimes(1);
});
test("late forecast reads and saves cannot change another location; typing during save survives", async () => {
  const pendingRead = deferred(); api.getProjectionReview.mockReturnValueOnce(pendingRead.promise);
  await render(forecast()); const day = find("projection-date").value;
  await click("projection-review-button"); await render(forecast("rudds"));
  await act(async () => pendingRead.resolve(review("berts", day)));
  expect(find("projection-save-button").disabled).toBe(true);
  await render(forecast()); await input("projection-amount", "10.01"); await click("projection-review-button");
  const save = deferred(); api.putProjection.mockReturnValueOnce(save.promise);
  await click("projection-save-button"); await input("projection-amount", "11.01");
  await act(async () => save.resolve({ ok: true, ...review("berts", day, { ...review("berts", day, null, nextVersion), amount: "10.01", note: "" }, nextVersion) }));
  expect(find("projection-amount").value).toBe("11.01");
  await click("projection-save-button"); expect(api.putProjection).toHaveBeenLastCalledWith("berts", expect.objectContaining({ amount: "11.01" }), nextVersion);
});
test("forecast invalid or wrong-scope review sends no write; Papa maps to its PostgreSQL store", async () => {
  api.getProjectionReview.mockImplementationOnce((rid, day) => Promise.resolve(review("rudds", day)));
  await render(forecast()); await input("projection-amount", "1.001"); await click("projection-review-button");
  expect(find("projection-save-button").disabled).toBe(true); expect(api.putProjection).not.toHaveBeenCalled();
  await render(forecast("papa_leonis")); await click("projection-review-button"); await input("projection-amount", "1.001"); await click("projection-save-button");
  expect(api.putProjection).not.toHaveBeenCalled(); await input("projection-amount", "9.10"); await click("projection-save-button"); expect(toast).toHaveBeenCalledTimes(1);
});
test("a forecast acknowledgement after navigation preserves the original location draft", async () => {
  await render(forecast()); await input("projection-amount", "10.01"); await click("projection-review-button");
  const day = find("projection-date").value, pending = deferred(); api.putProjection.mockReturnValueOnce(pending.promise);
  await click("projection-save-button"); await render(forecast("rudds"));
  await act(async () => pending.resolve({ ok: true, ...review("berts", day, { ...review("berts", day, null, nextVersion), amount: "10.01", note: "" }, nextVersion) }));
  expect(find("projection-amount").value).toBe(""); expect(toast).not.toHaveBeenCalled();
  await render(forecast()); expect(find("projection-amount").value).toBe("10.01"); expect(find("projection-save-button").disabled).toBe(true);
});
test("AI failed reads remain unknown and retry loads read-only retained history", async () => {
  api.aiHistory.mockRejectedValueOnce(new Error("Offline history")); await render(assistant());
  expect(container.textContent).toContain("Offline history"); expect(find("ai-message-0")).toBeNull(); expect(find("ai-clear-button").disabled).toBe(true);
  await click("ai-history-retry"); expect(find("ai-message-0").textContent).toContain("berts retained history");
  expect(find("ai-assistant-send-button").disabled).toBe(true); expect(find("ai-readonly-status")).not.toBeNull(); expect(api.streamChat).not.toHaveBeenCalled();
});
test.each(["rejected", "unconfirmed"])("failed AI clear %s retains displayed history", async reason => {
  api.aiCapabilities.mockImplementation(rid => Promise.resolve(caps(rid, true)));
  if (reason === "rejected") api.aiClear.mockRejectedValueOnce(new Error("Clear failed")); else api.aiClear.mockResolvedValueOnce(null);
  await render(assistant()); await click("ai-clear-button");
  expect(find("ai-message-0").textContent).toContain("berts retained history"); expect(container.querySelector('[role="alert"]')).not.toBeNull();
  await click("ai-clear-button"); expect(find("ai-message-0")).toBeNull();
});
test("late AI history and streaming callbacks cannot populate another location", async () => {
  const history = deferred(); api.aiHistory.mockReturnValueOnce(history.promise);
  await render(assistant()); await render(assistant("rudds"));
  await act(async () => history.resolve([{ restaurantId: "berts", role: "user", content: "Late Berts" }]));
  expect(container.textContent).not.toContain("Late Berts"); expect(find("ai-message-0").textContent).toContain("rudds retained history");
  api.aiCapabilities.mockImplementation(rid => Promise.resolve(caps(rid, true)));
  await render(assistant("berts")); let callbacks; const stream = deferred(); api.streamChat.mockImplementation((rid, text, options) => { callbacks = options; return stream.promise; });
  await input("ai-assistant-input-field", "Invented request"); await click("ai-assistant-send-button");
  await render(assistant("papa_leonis")); expect(callbacks.signal.aborted).toBe(true);
  await act(async () => { callbacks.onDelta("Late Berts answer"); callbacks.onDone(); stream.resolve(); });
  expect(container.textContent).not.toContain("Late Berts answer"); expect(find("ai-message-0").textContent).toContain("papa_leonis retained history");
});
test.each(["provider-error", "empty-response"])("AI %s retains input through refresh and requires history review", async failure => {
  api.aiCapabilities.mockImplementation(rid => Promise.resolve(caps(rid, true)));
  api.streamChat.mockImplementation(async (rid, text, callbacks) => { if (failure === "provider-error") callbacks.onError("Unavailable provider"); callbacks.onDone(); });
  await render(assistant()); await input("ai-assistant-input-field", "Keep my question"); await click("ai-assistant-send-button");
  expect(find("ai-assistant-input-field").value).toBe("Keep my question"); expect(find("ai-assistant-send-button").disabled).toBe(true);
  expect(container.querySelector('[role="alert"]').textContent).toContain("retained");
  await click("ai-history-retry"); expect(find("ai-assistant-input-field").value).toBe("Keep my question"); expect(find("ai-assistant-send-button").disabled).toBe(false);
});
