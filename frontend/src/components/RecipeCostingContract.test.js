import React, { act } from "react";
import { createRoot } from "react-dom/client";
import { CostingTab } from "./CostingTab";
import { RecipeCardsTab } from "./RecipeCardsTab";

const item = { controlNumber: "R01", itemCode: "global_food", name: "Invented food", packCount: 1, unitQty: 10, unitUOM: "lb", portionSize: 4, portionUOM: "oz", vendorSkus: [{ price: null, preferred: true }] };
const recipe = { id: "plate", recipeType: "menu", name: "Unpriced plate", price: 10, targetPct: 30, yieldQty: 1, yieldUOM: "each", lines: [{ sourceType: "item", controlNumber: "R01", itemCode: "global_food", qty: 1 }] };
let root, container, save, success, error;
beforeEach(() => {
  global.IS_REACT_ACT_ENVIRONMENT = true;
  container = document.createElement("div"); document.body.appendChild(container); root = createRoot(container);
  save = jest.fn().mockResolvedValue({ revision: 8 }); success = jest.fn(); error = jest.fn();
});
afterEach(async () => { await act(async () => root.unmount()); container.remove(); });
const costing = dish => <CostingTab rid="rudds" items={[item]} dishes={[dish]} focusDish={{ id: dish.id }} persist={save} showToast={success} showError={error} />;

test("an uncatalogued price shows unknown total, percentage and suggested price but preserves a valid recipe", async () => {
  await act(async () => root.render(costing(recipe)));
  const summary = container.querySelector('[data-testid="cost-summary"]');
  expect(summary.textContent.match(/Unknown/g)).toHaveLength(3);
  expect(container.querySelector('[data-testid="recipe-cost-incomplete"]').textContent).toContain("Actual Food Cost");
  await act(async () => container.querySelector('[data-testid="save-recipe-button"]').click());
  expect(save).toHaveBeenCalledTimes(1); expect(success).toHaveBeenCalledTimes(1);
});
test("invalid loaded recipe keeps its draft and makes no write or success announcement", async () => {
  await act(async () => root.render(costing({ ...recipe, lines: [{ ...recipe.lines[0], qty: -1 }] })));
  await act(async () => container.querySelector('[data-testid="save-recipe-button"]').click());
  expect(save).not.toHaveBeenCalled(); expect(success).not.toHaveBeenCalled(); expect(error).toHaveBeenCalled();
  expect(container.querySelector('[data-testid="recipe-name-input"]').value).toBe(recipe.name);
});

test("a new recipe uses its acknowledged database identity on the next save", async () => {
  const temporary = { ...recipe, id: "dish-local" };
  const canonical = "abc00000-0000-4000-8000-000000000001";
  save.mockImplementation(async rows => ({ revision: 8, clientIds: { "dish-local": canonical }, dishes: rows.map(row => ({ ...row, id: canonical })) }));
  await act(async () => root.render(costing(temporary)));
  await act(async () => container.querySelector('[data-testid="save-recipe-button"]').click());
  await act(async () => root.render(<CostingTab rid="rudds" items={[item]} dishes={[{ ...temporary, id: canonical }]} persist={save} showToast={success} showError={error} />));
  await act(async () => container.querySelector('[data-testid="save-recipe-button"]').click());
  expect(save).toHaveBeenCalledTimes(2);
  expect(save.mock.calls[1][0]).toHaveLength(1);
  expect(save.mock.calls[1][0][0].id).toBe(canonical);
});
test("printed recipe card reports incomplete cost without inventing zero dollars", async () => {
  await act(async () => root.render(<RecipeCardsTab items={[item]} dishes={[recipe]} />));
  expect(container.querySelector('[role="status"]').textContent).toContain("incomplete");
  expect(container.textContent).toContain("Unknown"); expect(container.textContent).not.toContain("$0.00");
});
