import { adjustmentSignedPortions, adjustmentValue, buildPeriodReport, calcPortionsPerUnit, itemDerived, itemPlanningCost, recipeCostSummary } from './calc';
import { planningNumber } from './planningNumbers';

const food = (changes = {}) => ({ itemCode: 'canonical', controlNumber: 'TEST', name: 'Fictional food', salesTracked: true,
  packCount: 1, unitQty: 5, unitUOM: 'lb', portionSize: 4, portionUOM: 'oz', currentStock: 1,
  vendorSkus: [{ price: 20, available: true, preferred: true }], ...changes });
const plate = (changes = {}) => ({ id: 'plate', recipeType: 'menu', name: 'Fictional plate', price: 10,
  lines: [{ sourceType: 'item', itemCode: 'canonical', qty: 2 }], ...changes });
const period = { periodStart: '2026-10-01', periodEnd: '2026-10-31', dishSales: { plate: 2 }, itemCounts: { TEST: { beginning: 2, ending: 1 } } };
const adjustment = { id: 'waste', controlNumber: 'TEST', date: '2026-10-10', qty: 1, qtyBasis: 'purchase', reason: 'waste' };

test.each([
  { portionUOM: 'fl oz' }, { portionUOM: 'unknown', unitUOM: 'unknown' },
  { unitUOM: null }, { packCount: 0 }, { packCount: -1, unitQty: -5 },
  { portionSize: null }, { portionSize: 0 }, { portionSize: -1 },
  { unitUOM: ['lb'], portionUOM: ['oz'] },
])('incomplete or incompatible metadata %p never becomes a monetary estimate', change => {
  const item = food(change), before = JSON.stringify(item);
  expect(itemDerived(item).costPerPortion).toBeNull();
  expect(itemPlanningCost(item).cost).toBeNull();
  expect(adjustmentValue(adjustment, item)).toBeNull();
  const report = buildPeriodReport(period, [item], [], [plate()], [adjustment]);
  for (const key of ['theoreticalCogs', 'actualCogs', 'explainedCost', 'unexplainedCost']) expect(report[key]).toBeNull();
  expect(report.wasteByReason.Waste).toBeNull();
  expect(JSON.stringify(item)).toBe(before);
});

test('valid cost and explicit free price remain known; conversion never defaults to each', () => {
  expect(calcPortionsPerUnit(5, 'lb', 4, 'oz').value).toBe(20);
  expect(itemDerived(food()).costPerPortion).toBe(1);
  expect(itemDerived(food({ vendorSkus: [{ price: 0 }] })).costPerPortion).toBe(0);
  expect(itemDerived(food({ vendorSkus: [{ price: -1 }] })).costPerPortion).toBeNull();
  expect(itemDerived(food({ vendorSkus: [null] })).costPerPortion).toBeNull();
  expect(planningNumber([])).toBeNull(); expect(planningNumber([1])).toBeNull();
});

test.each([[], [null], ['bad'], {}, [{ itemCode: 'missing', controlNumber: 'TEST', qty: 1 }],
  [{ itemCode: 'canonical', qty: 0 }],
  [{ sourceType: 'prep', recipeId: 'missing', qty: 1 }]])('malformed recipe lines %p do not give a partial or free report', lines => {
  const menu = plate({ lines });
  expect(recipeCostSummary(menu, [food()], [menu]).totalCost).toBeNull();
  expect(buildPeriodReport(period, [food()], [], [menu], []).menuProfitability[0].cost).toBeNull();
  expect(buildPeriodReport(period, [food()], [], [menu], []).theoreticalCogs).toBeNull();
});

test('canonical-only lines cost correctly; ambiguous inventory and prep identities stay unknown', () => {
  expect(recipeCostSummary(plate(), [food()], []).totalCost).toBe(2);
  expect(recipeCostSummary(plate({ lines: [{ itemCode: 'canonical', controlNumber: 'OLD_ALIAS', qty: 2 }] }), [food()], []).totalCost).toBe(2);
  expect(recipeCostSummary(plate(), [food(), food()], []).totalCost).toBeNull();
  const prep = plate({ id: 'prep', recipeType: 'prep', yieldQty: 2, yieldUOM: 'each' });
  const menu = plate({ lines: [{ sourceType: 'prep', recipeId: 'prep', qty: 1 }] });
  expect(recipeCostSummary(menu, [food()], [prep]).totalCost).toBe(1);
  expect(recipeCostSummary(menu, [food()], [prep, prep]).totalCost).toBeNull();
  const broken = { ...prep, yieldQty: null };
  expect(buildPeriodReport(period, [food()], [], [menu, broken], []).theoreticalCogs).toBeNull();
});

test('missing cost guidance is not mislabeled as arithmetic overflow', () => {
  const result = recipeCostSummary(plate(), [food({ vendorSkus: [{ price: null }] })], []);
  expect(result.issues.join(' ')).toMatch(/supplier price/);
  expect(result.issues.join(' ')).not.toMatch(/numeric range/);
});

test.each([null, '', ' ', -1, true, 'NaN'])('invalid adjustment quantity %p is unknown', qty => {
  expect(adjustmentValue({ ...adjustment, qty }, food())).toBeNull();
});

test('unknown mappings and bases poison removal totals; valid zero stays zero', () => {
  expect(adjustmentValue(adjustment, null)).toBeNull();
  expect(adjustmentValue({ ...adjustment, qtyBasis: 'bogus' }, food())).toBeNull();
  expect(adjustmentSignedPortions({ ...adjustment, reason: 'bogus' }, food())).toBeNull();
  const report = buildPeriodReport(period, [food()], [], [plate()], [adjustment, { ...adjustment, controlNumber: 'MISSING' }]);
  expect(report.wasteByReason.Waste).toBeNull();
  expect(adjustmentValue({ ...adjustment, qty: 0 }, food())).toBe(0);
});

test('explicit zero extended price is not replaced; missing purchase evidence is unknown', () => {
  const purchase = { invoiceDate: '2026-10-10', qty: 2, unitCost: 20, extendedCost: 0 };
  const report = row => buildPeriodReport(period, [], [row], [], []);
  expect(report(purchase).purchaseSpend).toBe(0);
  expect(report({ ...purchase, extendedCost: null }).purchaseSpend).toBe(40);
  expect(report({ ...purchase, extendedCost: null, unitCost: null }).purchaseSpend).toBeNull();
});

const independentItems = ['A1', 'B1'].map(code => food({ itemCode: code, controlNumber: code }));
const independentMenus = ['Pizza', 'Salad'].map((name, i) => plate({ id: name, name, lines: [{ itemCode: independentItems[i].itemCode, qty: 1 }] }));
const independentPeriod = sales => ({ ...period, dishSales: sales, itemCounts: { A1: { beginning: 10, ending: 5 }, B1: { beginning: 10, ending: 5 } } });
test.each([undefined, null, '', ' ', -1, 'bad'])('unrelated incomplete sales %p cannot erase known item usage or variance', sold => {
  const report = buildPeriodReport(independentPeriod({ Pizza: '5', Salad: sold }), independentItems, [], independentMenus, []);
  expect(report.trackedRows[0]).toMatchObject({ theoreticalPortions: 5, theoreticalCost: 5, unexplainedCost: 95 });
  expect(report.trackedRows[1]).toMatchObject({ theoreticalPortions: null, unexplainedCost: null });
  expect(report.trackedRows[1].usageIssues.join(' ')).toContain('Salad');
  expect(report.theoreticalCogs).toBeNull(); expect(report.unexplainedCost).toBeNull();
});
test('confirmed zero is known and a broken graph holds every row until its sale is confirmed zero', () => {
  const zero = buildPeriodReport(independentPeriod({ Pizza: '5', Salad: '0' }), independentItems, [], independentMenus, []);
  expect(zero.trackedRows.map(row => row.theoreticalPortions)).toEqual([5, 0]);
  const broken = { ...independentMenus[1], lines: [{ sourceType: 'prep', recipeId: 'missing', qty: 1 }] };
  const report = sales => buildPeriodReport(independentPeriod(sales), independentItems, [], [independentMenus[0], broken], []);
  expect(report({ Pizza: '5', Salad: '1' }).trackedRows.every(row => row.theoreticalPortions === null)).toBe(true);
  expect(report({ Pizza: '5', Salad: '0' }).trackedRows.map(row => row.theoreticalPortions)).toEqual([5, 0]);
});
