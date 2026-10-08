import { buildPeriodReport, fmtPlanningCost, itemPlanningCost, normalizeRecipeSchema, recipeCostSummary } from "./calc";

const food = { controlNumber: "LOCAL", itemCode: "global_food", name: "Invented food", packCount: 4, unitQty: 5, unitUOM: "lb", portionSize: 4, portionUOM: "oz", vendorSkus: [{ price: "80.00", preferred: true, available: true }] };
const plate = { id: "plate", recipeType: "menu", name: "Plate", price: 10, yieldQty: 1, yieldUOM: "each", lines: [{ sourceType: "item", itemCode: "global_food", controlNumber: "OLD_ALIAS", qty: 2 }] };
const summarize = (recipe = plate, items = [food], recipes = [recipe]) => recipeCostSummary(recipe, items, recipes);

test("canonical product identity overrides an old local alias without changing quantities", () => {
  expect(summarize()).toMatchObject({ complete: true, valid: true, totalCost: 2, costPerYieldUnit: 2 });
  const competing = { ...food, itemCode: "wrong_product", controlNumber: "OLD_ALIAS", vendorSkus: [{ price: 800, preferred: true }] };
  expect(summarize(plate, [competing, food]).totalCost).toBe(2);
});
test.each([null, undefined, "", " ", "NaN", "Infinity", -1, true])("missing or invalid supplier price %p never produces a trusted zero", price => {
  const result = summarize(plate, [{ ...food, vendorSkus: [{ price, preferred: true }] }]);
  expect(result).toMatchObject({ complete: false, valid: true, totalCost: null, costPerYieldUnit: null });
  expect(result.issues.length).toBeGreaterThan(0);
});
test("explicit free price remains valid; current costing selects only available suppliers", () => {
  expect(itemPlanningCost({ ...food, vendorSkus: [{ price: "0", preferred: true }] }).cost).toBe(0);
  expect(itemPlanningCost({ ...food, vendorSkus: [{ price: 80, preferred: true, available: false }, { price: 60, available: true }] }).cost).toBe(0.75);
  expect(itemPlanningCost({ ...food, vendorSkus: [{ price: 80, preferred: true, available: false }] }).cost).toBeNull();
});
test.each([{ portionSize: 0 }, { portionSize: -1 }, { portionSize: "Infinity" }, { portionUOM: "fl oz" }, { unitUOM: "unknown" }, { packCount: 0 }, { unitQty: null }])("invalid or incompatible physical metadata %p is uncosted", changes => {
  expect(summarize(plate, [{ ...food, ...changes }]).totalCost).toBeNull();
});
test("different supplier packs and price preference change planning cost only", () => {
  const alternate = { ...food, currentStock: 7, basePerCountUnit: 20, vendorSkus: [{ price: 40, packCount: 1, unitQty: 10, unitUOM: "lb", preferred: true }] };
  expect(summarize(plate, [alternate]).totalCost).toBe(2);
  expect(alternate.currentStock).toBe(7); expect(alternate.basePerCountUnit).toBe(20);
});
test.each([0, -1, null, "", true, "NaN", "Infinity"])("invalid ingredient quantity %p cannot form a valid recipe", qty => {
  expect(summarize({ ...plate, lines: [{ ...plate.lines[0], qty }] })).toMatchObject({ valid: false, complete: false, totalCost: null });
});
test("missing ingredients and ambiguous source fields are invalid rather than free", () => {
  expect(summarize(plate, []).valid).toBe(false);
  expect(summarize({ ...plate, lines: [{ ...plate.lines[0], recipeId: "also-prep" }] }).valid).toBe(false);
  expect(summarize({ ...plate, lines: [] }).totalCost).toBeNull();
  expect(summarize({ ...plate, lines: [{ ...plate.lines[0], uom: "lb" }] }).valid).toBe(false);
});
test("nested partial prices poison the aggregate; missing yields and cycles remain explicit", () => {
  const prep = { ...plate, id: "prep", recipeType: "prep", yieldQty: 4, yieldUOM: "qt" };
  const menu = { ...plate, lines: [{ sourceType: "prep", recipeId: "prep", qty: 2 }] };
  expect(summarize(menu, [food], [menu, prep]).totalCost).toBe(1);
  expect(summarize(menu, [{ ...food, vendorSkus: [{ price: null }] }], [menu, prep]).totalCost).toBeNull();
  expect(summarize(menu, [food], [menu, { ...prep, yieldQty: null }]).valid).toBe(false);
  const cyclic = { ...prep, lines: [{ sourceType: "prep", recipeId: "prep", qty: 1 }] };
  expect(summarize(menu, [food], [menu, cyclic])).toMatchObject({ cycle: true, valid: false, totalCost: null });
  expect(normalizeRecipeSchema({ recipeType: "prep", yieldQty: null }).yieldQty).toBeNull();
});
test("an unpriced ingredient cannot yield an apparently profitable menu estimate", () => {
  const report = buildPeriodReport({}, [{ ...food, vendorSkus: [{ price: null }] }], [], [plate], []);
  expect(report.menuProfitability[0]).toMatchObject({ cost: null, contribution: null, foodCostPct: null, costComplete: false });
  expect(fmtPlanningCost(null)).toBe("Unknown"); expect(fmtPlanningCost(0)).toBe("$0.00"); expect(fmtPlanningCost("2.10")).toBe("$2.10");
});
test("missing selling price retains unknown contribution even when ingredients are priced", () => {
  const report = buildPeriodReport({}, [food], [], [{ ...plate, price: null }], []);
  expect(report.menuProfitability[0]).toMatchObject({ cost: 2, contribution: null, price: null, foodCostPct: null });
});

test("unknown profitability sorts after a verified zero food cost", () => {
  const report = buildPeriodReport({}, [{ ...food, vendorSkus: [{ price: 0 }] }], [], [{ ...plate, id: "unknown", price: null }, { ...plate, id: "free" }], []);
  expect(report.menuProfitability.map(row => row.recipe.id)).toEqual(["free", "unknown"]);
  expect(report.menuProfitability[0].foodCostPct).toBe(0);
  expect(report.menuProfitability[1].foodCostPct).toBeNull();
});
test("excessively nested prep is held rather than causing a costing recursion failure", () => {
  const recipes = Array.from({ length: 101 }, (_, i) => ({ id: `prep-${i}`, recipeType: "prep", yieldQty: 1, yieldUOM: "qt", lines: i === 100 ? plate.lines : [{ sourceType: "prep", recipeId: `prep-${i + 1}`, qty: 1 }] }));
  expect(summarize(recipes[0], [food], recipes)).toMatchObject({ valid: false, totalCost: null });
});
