import React, { act } from "react";
import { createRoot } from "react-dom/client";
import { PurchaseSourceCapture } from "./PurchaseSourceCapture";
import * as api from "../lib/api";
import { captureRecord, pendingCaptureJournal } from "../lib/pendingCaptures";

jest.mock("../lib/api", () => ({ checkCaptureSavedStatus: jest.fn(), purchaseFile: jest.fn(), captureManualPurchase: jest.fn(), capturePurchase: jest.fn(), capturePurchaseSource: jest.fn() }));
const key = "00000000-0000-4000-8000-000000000001", fileId = "00000000-0000-4000-8000-000000000002";
const body = () => ({ vendor_id: "fictional", document_type: "invoice", documents: { document_number: "TEST ONLY", tax_source: "" }, parties: {},
  lines: [{ fields: { vendor_sku_snapshot: "00001" }, extra_fields: [{ label: "Note", value: "" }, { label: "Note", value: "second" }] }],
  extra_fields: [], attachment_ids: [], verified_source: true, evidence_note: "Fictional only" });
const record = () => captureRecord("manual", body(), key);
const status = (r, outcome = "saved") => ({ kind: r.kind, requestKey: r.key, actorId: "owner", storeId: "berts", sourceSha256: r.kind === "manual" ? "a".repeat(64) : r.body.sha256,
  outcome, fileId: outcome === "saved" ? fileId : null, ...(r.kind === "manual" ? { manualRecord: r.body } : {}) });
let container, root, captured, props;
beforeEach(() => {
  global.IS_REACT_ACT_ENVIRONMENT = true; sessionStorage.clear(); jest.resetAllMocks();
  Object.defineProperty(global, "crypto", { configurable: true, value: { randomUUID: () => key, subtle: { digest: jest.fn(async (_, bytes) => new Uint8Array(32).fill(new Uint8Array(bytes)[0]).buffer) } } });
  container = document.createElement("div"); document.body.appendChild(container); root = createRoot(container); captured = jest.fn();
  props = { restaurantId: "berts", actorId: "owner", manualReady: true, vendors: [{ id: "fictional", name: "Fictional" }], files: [], busy: false, onBusy: jest.fn(), onCaptured: captured };
});
afterEach(async () => { await act(async () => root.unmount()); container.remove(); });
const button = text => [...container.querySelectorAll("button")].find(b => b.textContent === text);
const click = el => act(async () => el.click());
const render = async () => act(async () => root.render(<PurchaseSourceCapture {...props} />));
const retained = () => pendingCaptureJournal("owner", "berts");
async function input(label, value) {
  const el = container.querySelector(`[aria-label="${label}"]`), proto = el.tagName === "SELECT" ? HTMLSelectElement.prototype : el.tagName === "TEXTAREA" ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype;
  await act(async () => { Object.getOwnPropertyDescriptor(proto, "value").set.call(el, value); el.dispatchEvent(new Event(el.tagName === "SELECT" ? "change" : "input", { bubbles: true })); });
}
function saved(r) { api.checkCaptureSavedStatus.mockResolvedValue(status(r)); api.purchaseFile.mockResolvedValue({ id: fileId, source_sha256: status(r).sourceSha256, captureStatus: "captured", documents: [], ...(r.kind === "manual" ? { manualRecord: r.body } : {}) }); }
test("reload restores exact manual request without resending, and a saved read clears it", async () => {
  const r = record(); retained().save(r); saved(r); await render();
  expect(api.captureManualPurchase).not.toHaveBeenCalled(); expect(api.checkCaptureSavedStatus).not.toHaveBeenCalled();
  await click(button("Check source saved status"));
  expect(api.checkCaptureSavedStatus).toHaveBeenCalledWith("berts", r); expect(retained().list()).toEqual([]); expect(captured).toHaveBeenCalledTimes(1);
});
test("before-commit read allows only an explicit identical manual retry; lost ack is reconciled", async () => {
  const r = record(); retained().save(r); api.checkCaptureSavedStatus.mockResolvedValue(status(r, "retry_available")); await render();
  expect(button("Retry retained source")).toBeUndefined(); await click(button("Check source saved status"));
  expect(api.captureManualPurchase).not.toHaveBeenCalled(); saved(r); api.captureManualPurchase.mockRejectedValue(new Error("dropped response"));
  await click(button("Retry retained source"));
  expect(api.captureManualPurchase).toHaveBeenCalledWith("berts", r.body, r.key); expect(retained().list()).toEqual([]); expect(captured).toHaveBeenCalledTimes(1);
});
test("failed or mismatched reads retain the request and do not enable retry", async () => {
  const r = record(); retained().save(r); api.checkCaptureSavedStatus.mockRejectedValue(new Error("timeout")); await render();
  await click(button("Check source saved status")); expect(retained().list()).toEqual([r]); expect(button("Retry retained source")).toBeUndefined();
  api.checkCaptureSavedStatus.mockResolvedValue({ ...status(r), actorId: "other" }); await click(button("Check source saved status"));
  expect(retained().list()).toEqual([r]); expect(api.purchaseFile).not.toHaveBeenCalled(); expect(captured).not.toHaveBeenCalled();
});
test("storage denial blocks manual submission before the command", async () => {
  await render(); await input("Manual supplier", "fictional"); await input("Manual source evidence", "Fictional only");
  await click(container.querySelector('[aria-label="Confirm manual source details"]'));
  const spy = jest.spyOn(Storage.prototype, "setItem").mockImplementation(() => { throw new Error("quota"); });
  try { await click(button("Retain manual source for review")); expect(api.captureManualPurchase).not.toHaveBeenCalled(); } finally { spy.mockRestore(); }
});
test("submitted manual request is retained before POST and malformed ack never clears it", async () => {
  await render(); await input("Manual supplier", "fictional"); await input("Manual source evidence", "Fictional only");
  await click(container.querySelector('[aria-label="Confirm manual source details"]'));
  api.captureManualPurchase.mockImplementation(async (_, b, k) => { expect(retained().list()[0]).toEqual(captureRecord("manual", b, k)); return {}; });
  api.checkCaptureSavedStatus.mockRejectedValue(new Error("offline")); await click(button("Retain manual source for review"));
  expect(retained().list()).toHaveLength(1); expect(captured).not.toHaveBeenCalled();
});
test("late user switch results do not clear old records or display another user's saved source", async () => {
  const r = record(); retained().save(r); let finish;
  api.checkCaptureSavedStatus.mockImplementation(() => new Promise(resolve => { finish = resolve; })); await render();
  await act(async () => button("Check source saved status").click());
  await act(async () => root.render(<div>Other signed-in user</div>));
  await act(async () => finish(status(r))); expect(retained().list()).toEqual([r]); expect(captured).not.toHaveBeenCalled();
});
test("file retry requires same filename and exact bytes, preserves its key, and stores no bytes", async () => {
  const r = captureRecord("csv", { kind: "csv", filename: "synthetic.csv", byteCount: 3, sha256: "01".repeat(32) }, key);
  retained().save(r); api.checkCaptureSavedStatus.mockResolvedValue(status(r, "retry_available")); await render(); await click(button("Check source saved status"));
  await click(button("Retry retained source")); expect(api.capturePurchase).not.toHaveBeenCalled();
  const choose = async value => act(async () => { const el = container.querySelector(`[aria-label="Reselect source ${key}"]`); Object.defineProperty(el, "files", { configurable: true, value: [value] }); el.dispatchEvent(new Event("change", { bubbles: true })); });
  const source = n => ({ name: "synthetic.csv", size: 3, arrayBuffer: async () => new Uint8Array([n, 0, 0]).buffer });
  await choose(source(2)); await click(button("Retry retained source")); expect(api.capturePurchase).not.toHaveBeenCalled();
  await choose({ ...source(1), name: "other.csv" }); await click(button("Retry retained source")); expect(api.capturePurchase).not.toHaveBeenCalled();
  await choose(source(1)); saved(r); await click(button("Retry retained source")); expect(api.capturePurchase.mock.calls[0][2]).toBe(key); expect(retained().list()).toEqual([]);
});
test("a request that finishes during discard is opened as saved rather than forgotten", async () => {
  const r = record(); retained().save(r); api.checkCaptureSavedStatus.mockResolvedValue(status(r, "retry_available")); await render();
  await click(button("Check source saved status")); await click(button("Discard retained source request")); saved(r);
  await click(button("Confirm discard source request")); expect(captured).toHaveBeenCalledTimes(1); expect(api.captureManualPurchase).not.toHaveBeenCalled();
});
test.each([{ actorId: "other" }, { restaurantId: "rudds" }])("identity change %j holds a late result and resets the visible recovery scope", async patch => {
  const r = record(); retained().save(r); let finish;
  api.checkCaptureSavedStatus.mockImplementation(() => new Promise(resolve => { finish = resolve; })); await render();
  await act(async () => button("Check source saved status").click());
  props = { ...props, ...patch }; await render();
  expect(container.querySelector('[aria-label="Retained source captures"]')).toBeNull();
  await act(async () => finish(status(r)));
  expect(retained().list()).toEqual([r]); expect(captured).not.toHaveBeenCalled();
});
test("a mismatched saved file cannot clear the request or announce success", async () => {
  const r = record(); retained().save(r); saved(r);
  api.purchaseFile.mockResolvedValue({ id: fileId, source_sha256: "b".repeat(64), captureStatus: "captured", documents: [], manualRecord: r.body });
  await render(); await click(button("Check source saved status"));
  expect(retained().list()).toEqual([r]); expect(captured).not.toHaveBeenCalled(); expect(button("Retry retained source")).toBeUndefined();
});
