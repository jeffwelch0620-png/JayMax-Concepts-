import { UOM_FAMILY } from "./planningUnits";
import { planningNumber, planningProduct, planningQuotient, planningSum } from "./planningNumbers";

const quantity = value => typeof value === "string" || typeof value === "number" ? planningNumber(value) : null;
const supportedUnit = value => typeof value === "string" && Object.hasOwn(UOM_FAMILY, value);
const blankQuantity = value => value == null || (typeof value === "string" && value.trim() === "");

// Quantity-only planning for the current working period. No prices, physical
// profiles, counts or writes; this is not versioned historical sales evidence.
export function expectedSalesUsage(items, recipes, dishSales) {
  const tracked = items.filter(item => item.salesTracked);
  const totals = new Map(tracked.map(item => [item, 0]));
  const problems = new Map(tracked.map(item => [item, []]));
  const globalIssues = [];
  const addGlobal = issue => {
    globalIssues.push(issue);
    tracked.forEach(item => problems.get(item).push(issue));
  };
  const unique = (rows, value) => {
    const matches = rows.filter(value);
    return matches.length === 1 ? matches[0] : null;
  };
  const invalid = message => ({ usage: null, issues: [message] });
  const memo = new Map();
  function expand(recipe, stack = new Set()) {
    if (!recipe || !recipe.id) return invalid("Recipe identity is missing");
    if (stack.has(recipe.id)) return invalid("Circular prep recipe reference");
    if (stack.size >= 100) return invalid("Recipe nesting exceeds the supported depth of 100");
    if (memo.has(recipe)) {
      const saved = memo.get(recipe);
      return stack.size + saved.depth > 100 ? invalid("Recipe nesting exceeds the supported depth of 100") : saved;
    }
    const type = recipe.recipeType || "menu";
    if (!["prep", "menu"].includes(type)) return invalid("Invalid recipe type");
    if (type === "prep" && (!(quantity(recipe.yieldQty) > 0) || !supportedUnit(recipe.yieldUOM))) {
      return invalid("Confirm a positive prep yield and supported yield unit");
    }
    if (type === "menu" && ((recipe.yieldQty != null && quantity(recipe.yieldQty) !== 1) ||
      (recipe.yieldUOM != null && recipe.yieldUOM !== "each"))) return invalid("Menu definitions are one serving (yield 1 each)");
    if (!Array.isArray(recipe.lines) || !recipe.lines.length) return invalid("Recipe ingredients are missing");
    const next = new Set(stack); next.add(recipe.id);
    const usage = new Map();
    let depth = 1;
    for (const line of recipe.lines) {
      if (!line || typeof line !== "object") return invalid("Ingredient details are missing");
      const qty = quantity(line.qty ?? line.qtyPortions);
      if (!(qty > 0)) return invalid("Ingredient quantities must be finite and greater than zero");
      const source = line.sourceType || "item";
      let contributions;
      if (source === "item") {
        // A supplied canonical key is authoritative; never fall back to an alias
        // when that key is absent from this restaurant or is ambiguous.
        const item = line.itemCode ? unique(items, item => item.itemCode === line.itemCode)
          : line.controlNumber ? unique(items, item => item.controlNumber === line.controlNumber) : null;
        if (line.recipeId || !item) return invalid("Inventory ingredient identity is missing or ambiguous at this restaurant");
        if (line.uom != null && line.uom !== "portion") return invalid("Inventory recipe quantities must be portions");
        contributions = new Map([[item, qty]]);
      } else if (source === "prep") {
        const child = unique(recipes, row => row?.id === line.recipeId);
        if (line.itemCode || line.controlNumber || !child || child.recipeType !== "prep") return invalid("Select one retained prep recipe at this restaurant");
        if (line.uom != null && line.uom !== child.yieldUOM) return invalid("Sub-recipe quantity unit must match its defined yield unit");
        const expanded = expand(child, next);
        if (!expanded.usage) return expanded;
        depth = Math.max(depth, expanded.depth + 1);
        const fraction = planningQuotient(qty, child.yieldQty);
        if (fraction == null) return invalid("Prep usage is outside the supported calculation range");
        contributions = new Map([...expanded.usage].map(([item, amount]) => [item, planningProduct(amount, fraction)]));
      } else return invalid("Invalid ingredient source type");
      for (const [item, amount] of contributions) {
        const total = planningSum([usage.get(item) ?? 0, amount]);
        if (total == null) return invalid("Ingredient usage is outside the supported calculation range");
        usage.set(item, total);
      }
    }
    const result = { usage, issues: [], depth }; memo.set(recipe, result); return result;
  }
  const menus = recipes.filter(recipe => recipe && (recipe.recipeType || "menu") !== "prep");
  const sales = dishSales && typeof dishSales === "object" && !Array.isArray(dishSales) ? dishSales : {};
  const unmatchedSales = [];
  if (!menus.length) addGlobal("Menu definitions are unavailable; sales coverage is unconfirmed");
  for (const [id, sold] of Object.entries(sales)) {
    // A blank key for a missing menu carries no quantity evidence. Keep the
    // original record untouched; meaningful unmatched quantities need review.
    if (!menus.some(menu => menu.id === id) && !blankQuantity(sold) && quantity(sold) !== 0) {
      unmatchedSales.push({ id, quantity: sold });
      addGlobal(`Sales entry ${id}: no matching menu definition; review or remove this working entry`);
    }
  }
  for (const menu of menus) {
    const label = menu.name || menu.id || "Unnamed menu";
    if (!menu.id || !unique(menus, row => row.id === menu.id)) {
      addGlobal(`${label}: menu identity is missing or ambiguous`); continue;
    }
    const sold = quantity(Object.hasOwn(sales, menu.id) ? sales[menu.id] : null);
    // An explicit zero contributes no usage even if an unused old definition
    // needs repair. A blank is not evidence that nothing was sold.
    if (sold === 0) continue;
    const expanded = expand(menu);
    if (!expanded.usage) {
      const guidance = blankQuantity(sales[menu.id])
        ? "If this menu had no sales, enter a confirmed 0; otherwise repair its recipe."
        : "Repair this menu's recipe before using its expected usage.";
      expanded.issues.forEach(issue => addGlobal(`${label}: ${issue}. ${guidance}`)); continue;
    }
    for (const item of tracked) {
      const amount = expanded.usage.get(item) ?? 0;
      if (amount === 0) continue;
      if (sold == null || sold < 0) {
        problems.get(item).push(`${label}: enter a confirmed nonnegative sales quantity (zero if none)`); continue;
      }
      const total = planningSum([totals.get(item), planningProduct(amount, sold)]);
      if (total == null) problems.get(item).push(`${label}: expected usage is outside the supported calculation range`);
      else totals.set(item, total);
    }
  }
  const rows = tracked.map(item => {
    const issues = [...new Set(problems.get(item))];
    return { item, portions: issues.length ? null : totals.get(item), complete: !issues.length, issues };
  });
  return { rows, unmatchedSales, complete: !globalIssues.length && rows.every(row => row.complete),
    issues: [...new Set([...globalIssues, ...rows.flatMap(row => row.issues)])] };
}
