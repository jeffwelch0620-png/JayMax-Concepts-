import React, { act } from "react";
import { createRoot } from "react-dom/client";
import { MenuPortions } from "./MenuPortions";
import * as api from "../lib/api";

jest.mock("../lib/api", () => ({ menuPortions: jest.fn(), menuPortionHistory: jest.fn(), saveMenuPortion: jest.fn() }));

const FRIES = "11111111-1111-4111-8111-111111111111", PLATE = "22222222-2222-4222-8222-222222222222", TEA = "33333333-3333-4333-8333-333333333333";
const menu = canEdit => ({ available: true, days: 90, can_edit: canEdit, store_id: "berts",
  products: [{ product_id: FRIES, name: "Invented fries", base_unit: "lb", track: "daily" }],
  sold: [{ kind: "item", guid: PLATE, name: "Invented Plate", quantity: "20", amount: "200.00", no_prep: false, lines: [], status: "missing", changes: 0 },
         { kind: "item", guid: TEA, name: "Invented Tea", quantity: "30", amount: "60.00", no_prep: true, lines: [], status: "no_prep", changes: 1 }] });

let keys = 0;
async function render(ui) {
  global.IS_REACT_ACT_ENVIRONMENT = true;
  Object.defineProperty(global, "crypto", { configurable: true, value: { randomUUID: () => `key-${++keys}` } });
  const container = document.createElement("div"); document.body.appendChild(container);
  const root = createRoot(container);
  await act(async () => root.render(ui));
  return { container, done: async () => { await act(async () => root.unmount()); container.remove(); } };
}
const change = (el, value) => {
  const setter = Object.getOwnPropertyDescriptor(Object.getPrototypeOf(el), "value").set;
  setter.call(el, value); el.dispatchEvent(new Event(el.tagName === "SELECT" ? "change" : "input", { bubbles: true }));
};

test("an owner sets a portion from the start and a retry keeps the same key", async () => {
  api.menuPortions.mockResolvedValue(menu(true));
  api.menuPortionHistory.mockResolvedValue({ available: true, changes: [] });
  api.saveMenuPortion.mockRejectedValueOnce({ response: { data: { detail: "Network error" } } }).mockResolvedValue({ saved: 1, replayed: false });
  const onChanged = jest.fn();
  const { container, done } = await render(<MenuPortions rid="berts" onChanged={onChanged} />);
  try {
    expect(container.textContent).toContain("1 are missing");
    expect(container.querySelector('[data-testid="portion-list"]').textContent).not.toContain("Invented Tea");   // filter: missing
    await act(async () => container.querySelector(`[data-testid="portion-edit-${PLATE}"]`).click());
    await act(async () => container.querySelector('[data-testid="portion-add-line"]').click());
    await act(async () => change(container.querySelector('[data-testid="portion-product-0"]'), FRIES));
    await act(async () => change(container.querySelector('[data-testid="portion-quantity-0"]'), "1.5"));
    expect(container.querySelector('[data-testid="portion-editor"]').textContent).toContain("lb");
    await act(async () => container.querySelector('[data-testid="portion-save"]').click());
    expect(container.querySelector('[role="alert"]').textContent).toContain("Network error");
    await act(async () => container.querySelector('[data-testid="portion-save"]').click());
    const [first, second] = api.saveMenuPortion.mock.calls;
    expect(first[1]).toEqual({ sold_kind: "item", sold_guid: PLATE, sold_name: "Invented Plate", no_prep: false, reason: "", effective_from: null,
      lines: [{ product_id: FRIES, base_quantity: "1.5" }] });
    expect(second[2]).toBe(first[2]);
    expect(onChanged).toHaveBeenCalled();
  } finally { await done(); }
});

test("a dated change needs its date, and a General Manager only reads", async () => {
  api.menuPortions.mockResolvedValue(menu(true));
  api.menuPortionHistory.mockResolvedValue({ available: true, changes: [] });
  api.saveMenuPortion.mockClear();
  let view = await render(<MenuPortions rid="berts" />);
  try {
    await act(async () => view.container.querySelector(`[data-testid="portion-edit-${PLATE}"]`).click());
    await act(async () => view.container.querySelector('[data-testid="portion-no-prep"]').click());
    await act(async () => change(view.container.querySelector('[data-testid="portion-applies"]'), "date"));
    await act(async () => view.container.querySelector('[data-testid="portion-save"]').click());
    expect(view.container.querySelector('[role="alert"]').textContent).toContain("Choose the date");
    expect(api.saveMenuPortion).not.toHaveBeenCalled();
  } finally { await view.done(); }
  api.menuPortions.mockResolvedValue(menu(false));
  view = await render(<MenuPortions rid="berts" />);
  try {
    expect(view.container.textContent).toContain("Only an owner or the Operations & Integration Lead");
    expect(view.container.querySelector(`[data-testid="portion-edit-${PLATE}"]`)).toBeNull();
  } finally { await view.done(); }
});
