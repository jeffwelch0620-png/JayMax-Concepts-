import React, { act } from "react";
import { createRoot } from "react-dom/client";
import { StoreTransfers, TransferCard } from "./StoreTransfers";
import * as api from "../lib/api";

jest.mock("../lib/api", () => ({ __esModule: true, actualTransfers: jest.fn(), previewActualTransfer: jest.fn(), sendActualTransfer: jest.fn(), stepActualTransfer: jest.fn() }));
const transfer = (changes = {}) => ({ id: "t-1", from_store_id: "berts", to_store_id: "rudds", item_code: "flour", name: "Flour, all purpose", base_unit: "lb",
  sent_base_quantity: "10", sent_date: "2026-10-30", kind: "lend", note: "Rudd's ran out", status: "sent", ...changes });
let root, container;
beforeEach(() => {
  global.IS_REACT_ACT_ENVIRONMENT = true; Object.defineProperty(global, "crypto", { configurable: true, value: { randomUUID: () => "stable-key" } });
  root = createRoot(container = document.createElement("div")); document.body.appendChild(container); jest.clearAllMocks();
});
afterEach(async () => { await act(async () => root.unmount()); container.remove(); });
const render = el => act(async () => root.render(el));
const click = el => act(async () => el.click());
const button = text => [...container.querySelectorAll("button")].find(b => b.textContent === text);
async function input(label, value) { const el = container.querySelector(`[aria-label="${label}"]`); await act(async () => { Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value").set.call(el, value); el.dispatchEvent(new Event("input", { bubbles: true })); }); }
async function choose(label, value) { const el = container.querySelector(`[aria-label="${label}"]`); await act(async () => { el.value = value; el.dispatchEvent(new Event("change", { bubbles: true })); }); }

test("the sending store previews the cost and sends the reviewed transfer", async () => {
  api.actualTransfers.mockResolvedValue({ store_id: "berts", transfers: [], items: [{ code: "flour", name: "Flour, all purpose", base_unit: "lb" }], stores: [{ id: "rudds", name: "Rudd's Pies and Fries" }] });
  api.previewActualTransfer.mockResolvedValue({ reviewHash: "a".repeat(64), review: { name: "Flour, all purpose", base_unit: "lb", to_store_id: "rudds", estimated_cost_amount: "6.50",
    cost: { cost_amount: "32.50", base_quantity: "50", record_date: "2026-10-27" } } });
  api.sendActualTransfer.mockResolvedValue({ transfer: transfer() });
  await render(<StoreTransfers rid="berts" />);
  await click(button("Send to another store"));
  expect(container.querySelector('[aria-label="Transfer to store"]').textContent).toBe("Rudd's");
  await choose("Transfer item", "flour"); await input("Transfer amount", "10"); await input("Transfer note", "Rudd's ran out");
  await click(button("Preview transfer"));
  expect(api.previewActualTransfer.mock.calls[0][1]).toMatchObject({ to_store_id: "rudds", item_code: "flour", sent_base_quantity: "10", kind: "lend" });
  expect(container.textContent).toContain("about $6.50 at your latest purchase cost");
  expect(button("Send transfer").disabled).toBe(true);
  await click(container.querySelector('[aria-label="Review store transfer"]'));
  await click(button("Send transfer"));
  expect(api.sendActualTransfer).toHaveBeenCalledWith("berts", expect.objectContaining({ expected_review_hash: "a".repeat(64), reviewed: true }), "stable-key");
});

test("the receiving store confirms what arrived; the sender can only cancel", async () => {
  api.stepActualTransfer.mockResolvedValue({ transfer: transfer({ status: "received" }) });
  const changed = jest.fn();
  await render(<TransferCard rid="berts" store="berts" transfer={transfer()} onChange={changed} />);
  expect(button("Confirm what arrived")).toBeUndefined();
  expect(button("Cancel transfer")).toBeDefined();
  await render(<TransferCard rid="rudds" store="rudds" transfer={transfer()} onChange={changed} />);
  expect(button("Cancel transfer")).toBeUndefined();
  await click(button("Confirm what arrived"));
  await input("Received Flour, all purpose", "8"); await input("Transfer receipt note", "Invented manager");
  await click(button("Confirm received"));
  expect(api.stepActualTransfer).toHaveBeenCalledWith("rudds", "t-1", expect.objectContaining({ action: "receive", received_base_quantity: "8", note: "Invented manager" }), "stable-key");
  expect(changed).toHaveBeenCalled();
  await render(<TransferCard rid="rudds" store="rudds" transfer={transfer({ status: "received", received_base_quantity: "8", record_date: "2026-10-30", transfer_cost_amount: "5.20", short_base_quantity: "2" })} onChange={changed} />);
  expect(container.textContent).toContain("received 8 lb on 2026-10-30 for $5.20 · 2 lb short (stays in the sending store's usage)");
});

test("inputs are frozen while a preview is pending and after a lost send, so a retry cannot double a transfer", async () => {
  api.actualTransfers.mockResolvedValue({ store_id: "berts", transfers: [], items: [{ code: "flour", name: "Flour, all purpose", base_unit: "lb" }], stores: [{ id: "rudds", name: "Rudd's" }] });
  let answer; api.previewActualTransfer.mockReturnValue(new Promise(resolve => { answer = resolve; }));
  api.sendActualTransfer.mockRejectedValueOnce(new Error("Network lost")).mockResolvedValue({ transfer: transfer() });
  await render(<StoreTransfers rid="berts" />);
  await click(button("Send to another store"));
  await choose("Transfer item", "flour"); await input("Transfer amount", "10"); await input("Transfer note", "Rudd's ran out");
  await click(button("Preview transfer"));
  expect(container.querySelector('[aria-label="Transfer amount"]').closest("fieldset").disabled).toBe(true);
  expect(button("Checking…")).toBeDefined();
  await act(async () => answer({ reviewHash: "b".repeat(64), review: { name: "Flour, all purpose", base_unit: "lb", to_store_id: "rudds", estimated_cost_amount: "6.50",
    cost: { cost_amount: "32.50", base_quantity: "50", record_date: "2026-10-27" } } }));
  expect(container.textContent).toContain("10 lb of Flour, all purpose");
  await click(container.querySelector('[aria-label="Review store transfer"]'));
  await click(button("Send transfer"));
  expect(container.querySelector('[aria-label="Transfer amount"]').closest("fieldset").disabled).toBe(true);
  expect(button("Send to another store").disabled).toBe(true); // the form can't be hidden and its retry key lost
  await click(button("Retry the same transfer"));
  expect(button("Send to another store").disabled).toBe(false);
  expect(api.sendActualTransfer.mock.calls[1]).toEqual(api.sendActualTransfer.mock.calls[0]);
});

test("a failed list refresh shows its error but keeps an unresolved send and its retry", async () => {
  api.actualTransfers.mockResolvedValueOnce({ store_id: "berts", transfers: [transfer({ id: "t-old" })], items: [{ code: "flour", name: "Flour, all purpose", base_unit: "lb" }], stores: [{ id: "rudds", name: "Rudd's" }] })
    .mockRejectedValue(new Error("Network down"));
  api.previewActualTransfer.mockResolvedValue({ reviewHash: "c".repeat(64), review: { name: "Flour, all purpose", base_unit: "lb", to_store_id: "rudds", estimated_cost_amount: "6.50",
    cost: { cost_amount: "32.50", base_quantity: "50", record_date: "2026-10-27" } } });
  api.sendActualTransfer.mockRejectedValue(new Error("Network lost"));
  api.stepActualTransfer.mockResolvedValue({ transfer: transfer({ id: "t-old", status: "cancelled" }) });
  await render(<StoreTransfers rid="berts" />);
  await click(button("Send to another store"));
  await choose("Transfer item", "flour"); await input("Transfer amount", "10"); await input("Transfer note", "Rudd's ran out");
  await click(button("Preview transfer"));
  await click(container.querySelector('[aria-label="Review store transfer"]'));
  await click(button("Send transfer"));
  await click(button("Cancel transfer")); // another listed transfer changes, so the list refreshes and the refresh fails
  expect(container.textContent).toContain("Couldn't refresh transfers: Network down");
  expect(button("Retry the same transfer")).toBeDefined();
});
