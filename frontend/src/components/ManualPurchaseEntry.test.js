import React, { act } from "react";
import { createRoot } from "react-dom/client";
import { ManualPurchaseEntry } from "./ManualPurchaseEntry";

let container, root;
beforeEach(() => {
  global.IS_REACT_ACT_ENVIRONMENT = true;
  Object.defineProperty(global, "crypto", { configurable: true, value: { randomUUID: jest.fn(() => "retained-manual-key") } });
  container = document.createElement("div"); document.body.appendChild(container); root = createRoot(container);
});
afterEach(async () => { await act(async () => root.unmount()); container.remove(); });
const button = text => [...container.querySelectorAll("button")].find(b => b.textContent === text);
async function click(el) { await act(async () => el.click()); }
async function input(label, value) {
  const el = container.querySelector(`[aria-label="${label}"]`);
  const proto = el.tagName === "SELECT" ? HTMLSelectElement.prototype : el.tagName === "TEXTAREA" ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype;
  await act(async () => { Object.getOwnPropertyDescriptor(proto, "value").set.call(el, value); el.dispatchEvent(new Event(el.tagName === "SELECT" ? "change" : "input", { bubbles: true })); });
}
async function render(capture, files = []) { await act(async () => root.render(<ManualPurchaseEntry vendors={[{ id: "other", name: "Invented supplier" }]} files={files} onCapture={capture} />)); }
async function fill() {
  await input("Manual supplier", "other"); await input("Invoice / receipt number", "MANUAL-1");
  await input("Printed line amount 1", "40.00"); await input("Manual source evidence", "Confirmed against invented receipt");
  await click(container.querySelector('[aria-label="Confirm manual source details"]'));
}

test("manual entry keeps blanks and source text and does not post inventory", async () => {
  const capture = jest.fn().mockResolvedValue({ id: "source", captureStatus: "captured", documents: [], manualRecord: {} });
  await render(capture, [{ id: "receipt", original_filename: "synthetic.pdf" }]); await fill();
  await input("Supplier product code 1", "00001");
  expect(container.querySelector('[aria-label="Confirm manual source details"]').checked).toBe(false);
  await click(container.querySelector('[aria-label="Attach synthetic.pdf"]'));
  await click(container.querySelector('[aria-label="Confirm manual source details"]'));
  await click(button("Retain manual source for review"));
  expect(capture).toHaveBeenCalledTimes(1);
  const body = capture.mock.calls[0][0]; expect(body.documents.tax_source).toBe("");
  expect(body.lines[0].fields.vendor_sku_snapshot).toBe("00001");
  expect(body.lines[0].fields.extended_amount_source).toBe("40.00");
  expect(body.attachment_ids).toEqual(["receipt"]); expect(body.received_date).toBeUndefined();
});

test("interrupted capture freezes its inputs and retries the exact same request", async () => {
  const capture = jest.fn().mockRejectedValueOnce(new Error("Connection interrupted")).mockResolvedValueOnce({ id: "source", captureStatus: "captured", documents: [], manualRecord: {} });
  await render(capture); await fill(); await click(button("Retain manual source for review"));
  expect(container.textContent).toContain("Connection interrupted");
  expect(container.querySelector('[aria-label="Invoice / receipt number"]').disabled).toBe(true);
  await click(button("Retry same manual source")); expect(capture.mock.calls[1]).toEqual(capture.mock.calls[0]);
  expect(container.textContent).not.toContain("Connection interrupted");
});

test("incomplete acknowledgement retains a safe retry", async () => {
  const capture = jest.fn().mockResolvedValue({ id: "source", documents: [] });
  await render(capture); await fill(); await click(button("Retain manual source for review"));
  expect(container.textContent).toContain("Source capture was not confirmed");
  expect(button("Retry same manual source")).toBeDefined();
});

test("additional labels may repeat and blank values remain present", async () => {
  const capture = jest.fn().mockResolvedValue({ id: "source", captureStatus: "captured", documents: [], manualRecord: {} });
  await render(capture); await fill();
  await click(button("Add additional invoice field")); await input("Additional invoice field label 1", "Route");
  await click(button("Add additional invoice field")); await input("Additional invoice field label 2", "Route");
  await input("Additional invoice field value 2", "0002");
  await click(container.querySelector('[aria-label="Confirm manual source details"]')); await click(button("Retain manual source for review"));
  expect(capture.mock.calls[0][0].extra_fields).toEqual([{ label: "Route", value: "" }, { label: "Route", value: "0002" }]);
});
