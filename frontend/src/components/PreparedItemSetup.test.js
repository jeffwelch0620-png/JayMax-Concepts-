import React, { act } from "react";
import { createRoot } from "react-dom/client";
import { PreparedItemSetup } from "./PreparedItemSetup";
import * as api from "../lib/api";
jest.mock("../lib/api");

let root, container;
const data = {
  products: [{ id: "pv", product_id: "protein", name: "Prepared protein", base_unit: "lb" }, { id: "av", product_id: "sauce", name: "Sauce A", base_unit: "gal" }],
  profiles: [{ id: "pu", product_version_id: "pv", source_unit: "lb", base_units_per_source_unit: "1", revision: 1 }, { id: "au", product_version_id: "av", source_unit: "gal", base_units_per_source_unit: "1", revision: 1 }],
  recipes: [{ id: "ar", product_id: "sauce", product_version_id: "av", revision: 1, reviewNeeded: false }],
  rawItems: [{ code: "food", name: "Purchased protein", base_unit: "lb" }, { code: "unknown", name: "Unverified item", base_unit: null }],
  legacySources: [{ sourceType: "dish", sourceId: "legacy", name: "Old protein recipe", hash: "source-hash", mappingState: "unreviewed", issues: ["Ingredient physical unit is missing"], snapshot: { header: { recipe_type: "prep" }, lines: [{ id: "line", item_code: "food", qty: "60", uom: null }] } }],
  baseUnits: ["lb", "gal", "each"]
};
const input = async (label, value) => {
  const el = container.querySelector(`[aria-label="${label}"]`);
  await act(async () => { Object.getOwnPropertyDescriptor(el.tagName === "SELECT" ? HTMLSelectElement.prototype : HTMLInputElement.prototype, "value").set.call(el, value); el.dispatchEvent(new Event(el.tagName === "SELECT" ? "change" : "input", { bubbles: true })); });
};
const click = async el => { await act(async () => el.click()); };
const button = text => [...container.querySelectorAll("button")].find(b => b.textContent === text);
const render = async () => { await act(async () => root.render(<PreparedItemSetup restaurantId="berts" />)); };

beforeEach(() => {
  jest.clearAllMocks(); global.IS_REACT_ACT_ENVIRONMENT = true;
  Object.defineProperty(global, "crypto", { configurable: true, value: { randomUUID: jest.fn(() => "review-key") } });
  api.nativePrepSetup.mockResolvedValue(data);
  api.previewNativePrepRecipe.mockImplementation(async (rid, body) => ({ reviewHash: "review-hash", review: { product: { id: body.product_version_id }, revision: 1, usableBaseYield: "48", lines: body.lines.map((l, i) => ({ ...l, line_number: i + 1, base_quantity: "60", base_unit: "lb" })) } }));
  api.saveNativePrepRecipe.mockResolvedValue({ recipe: { id: "saved", store_id: "berts", product_version_id: "pv", review_hash: "review-hash" } });
  container = document.createElement("div"); document.body.appendChild(container); root = createRoot(container);
});
afterEach(async () => { await act(async () => root.unmount()); container.remove(); });

async function recipeForm() {
  await render(); await input("Prepared item", "pv"); await input("Usable yield measurement", "pu"); await input("Usable yield quantity", "48"); await input("Prep method", "Trim measured input"); await input("Recipe review evidence", "Verified usable yield");
  await input("Ingredient 1 item", "food"); await input("Ingredient 1 quantity", "60"); await input("Ingredient 1 unit", "lb"); await input("Ingredient 1 conversion", "1"); await input("Ingredient 1 evidence", "Measured gross input");
}

test("missing units are visible and no conversions or saves are assumed", async () => {
  await render(); expect(container.textContent).toContain("physical unit is missing"); expect(container.textContent).toContain("60 unit missing");
  await input("Prepared item", "pv"); expect(container.querySelector('[aria-label="Verified lb per measurement"]').value).toBe("");
  expect(api.saveNativePrepProfile).not.toHaveBeenCalled(); expect(api.saveNativePrepRecipe).not.toHaveBeenCalled();
});

test("new prepared identity requires fixed unit and explicit confirmation", async () => {
  api.saveNativePrepProduct.mockResolvedValue({ product: { id: "bag", name: "Eight-piece bag", base_unit: "each", store_id: "berts" } });
  await render(); await input("Prepared item name", "Eight-piece bag"); await input("Prepared inventory unit", "each"); await input("Prepared identity evidence", "Eight individual pieces per prepared bag");
  expect(button("Save prepared item").disabled).toBe(true); await click(container.querySelector('[aria-label="Confirm prepared identity"]')); await click(button("Save prepared item"));
  expect(api.saveNativePrepProduct.mock.calls[0][1]).toEqual({ name: "Eight-piece bag", base_unit: "each", note: "Eight individual pieces per prepared bag", verified: true });
  expect(container.textContent).toContain("Verified definition saved");
});

test("uncertain identity save retries the exact body and key with editing held", async () => {
  api.saveNativePrepProduct.mockRejectedValueOnce(new Error("Connection lost")).mockResolvedValueOnce({ product: { id: "bag", name: "Bag", base_unit: "each", store_id: "berts" } });
  await render(); await input("Prepared item name", "Bag"); await input("Prepared inventory unit", "each"); await input("Prepared identity evidence", "Counted contents");
  await click(container.querySelector('[aria-label="Confirm prepared identity"]')); await click(button("Save prepared item"));
  expect(container.querySelector('[aria-label="Prepared item name"]').disabled).toBe(true); await click(button("Retry same definition review"));
  expect(api.saveNativePrepProduct.mock.calls[1]).toEqual(api.saveNativePrepProduct.mock.calls[0]);
});

test("unit acknowledgment must match the exact decimal conversion", async () => {
  api.saveNativePrepProfile.mockResolvedValue({ profile: { id: "wrong", store_id: "berts", product_version_id: "pv", source_unit: "pan", base_units_per_source_unit: "1" } });
  await render(); await input("Prepared item", "pv"); await input("Prep measurement label", "pan"); await input("Verified lb per measurement", "1.000000000001"); await input("Prep unit evidence", "Measured fill");
  await click(container.querySelector('[aria-label="Confirm prep unit"]')); await click(button("Save prep unit version"));
  expect(container.textContent).toContain("Saved definition was not confirmed"); expect(container.textContent).not.toContain("Verified definition saved");
  expect(api.saveNativePrepProfile.mock.calls[0][1].factor).toBe("1.000000000001");
});

test("recipe preview retains entered units and cannot approve before review", async () => {
  await recipeForm(); await input("Existing prep source", "dish:legacy"); await click(button("Preview recipe version"));
  expect(api.previewNativePrepRecipe.mock.calls[0][1].lines[0]).toMatchObject({ quantity: "60", source_unit: "lb", factor: "1", raw_item_code: "food" });
  expect(api.previewNativePrepRecipe.mock.calls[0][1].legacy.expected_source_hash).toBe("source-hash");
  expect(button("Approve recipe version").disabled).toBe(true); expect(api.saveNativePrepRecipe).not.toHaveBeenCalled();
  await click(container.querySelector('[aria-label="Confirm recipe review"]')); await click(button("Approve recipe version"));
  expect(api.saveNativePrepRecipe.mock.calls[0][1].expected_review_hash).toBe("review-hash");
});

test("editing a reviewed quantity removes the old approval", async () => {
  await recipeForm(); await click(button("Preview recipe version")); await click(container.querySelector('[aria-label="Confirm recipe review"]'));
  await input("Ingredient 1 quantity", "61"); expect(button("Approve recipe version")).toBeUndefined(); expect(api.saveNativePrepRecipe).not.toHaveBeenCalled();
});

test("prepared ingredient selects its reviewed recipe and profile without raw identity", async () => {
  await recipeForm(); await input("Ingredient 1 type", "prepared"); await input("Ingredient 1 recipe", "ar"); await input("Ingredient 1 prep unit", "au"); await input("Ingredient 1 quantity", "2"); await input("Ingredient 1 evidence", "Existing two gallons");
  await click(button("Preview recipe version"));
  expect(api.previewNativePrepRecipe.mock.calls[0][1].lines[0]).toMatchObject({ raw_item_code: null, prepared_recipe_id: "ar", prepared_profile_id: "au", source_unit: "gal", factor: "1" });
  expect(container.textContent).toContain("without another withdrawal");
});

test("uncertain recipe approval holds and retries exact reviewed payload", async () => {
  api.saveNativePrepRecipe.mockRejectedValueOnce(new Error("Connection lost"));
  await recipeForm(); await click(button("Preview recipe version")); await click(container.querySelector('[aria-label="Confirm recipe review"]')); await click(button("Approve recipe version"));
  expect(container.querySelector('[aria-label="Ingredient 1 quantity"]').disabled).toBe(true); await click(button("Retry same definition review"));
  expect(api.saveNativePrepRecipe.mock.calls[1]).toEqual(api.saveNativePrepRecipe.mock.calls[0]);
});

test("stale approval clears the preview and requires fresh review", async () => {
  api.saveNativePrepRecipe.mockRejectedValue({ response: { status: 409, data: { detail: "Source changed" } } });
  await recipeForm(); await click(button("Preview recipe version")); await click(container.querySelector('[aria-label="Confirm recipe review"]')); await click(button("Approve recipe version"));
  expect(container.textContent).toContain("Source changed"); expect(button("Approve recipe version")).toBeUndefined(); expect(button("Refresh prep setup").disabled).toBe(false);
});

test("wrong-location acknowledgment is not reported as saved", async () => {
  api.saveNativePrepRecipe.mockResolvedValue({ recipe: { id: "saved", store_id: "rudds", product_version_id: "pv", review_hash: "review-hash" } });
  await recipeForm(); await click(button("Preview recipe version")); await click(container.querySelector('[aria-label="Confirm recipe review"]')); await click(button("Approve recipe version"));
  expect(container.textContent).toContain("Saved definition was not confirmed"); expect(container.textContent).not.toContain("Verified definition saved");
});

test("history reads earlier versions and clears when selection changes", async () => {
  api.nativePrepHistory.mockResolvedValue({ productVersions: [{ id: "pv", name: "Protein", revision: 1, base_unit: "lb" }], unitProfiles: [], recipeVersions: [{ id: "old", revision: 1, usable_base_yield: "48", note: "Old verified yield" }] });
  await render(); await input("Prepared item", "pv"); await click(button("Show prepared item history")); expect(container.textContent).toContain("Old verified yield");
  await input("Prepared item", "av"); expect(container.querySelector('[aria-label="Prepared item history"]')).toBeNull();
});

test("unmapped purchased items cannot be chosen for recipe promotion", async () => {
  await recipeForm(); expect(container.querySelector('option[value="unknown"]').disabled).toBe(true);
});
