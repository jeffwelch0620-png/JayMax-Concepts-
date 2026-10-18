import { itemDerived, buildPeriodReport, fmtPlanningCost } from './calc';

const food = vendorSkus => ({ controlNumber:'TEST', name:'Fictional food', salesTracked:true,
  currentStock:1, par:2, packCount:'1', unitQty:'1', unitUOM:'each',
  portionSize:'1', portionUOM:'each', vendorSkus });
const report = item => buildPeriodReport({ periodStart:'2026-10-01', periodEnd:'2026-10-31',
  dishSales:{plate:'1'}, itemCounts:{TEST:{beginning:2,ending:1}} }, [item], [],
  [{id:'plate',name:'Fictional priced plate',lines:[{controlNumber:'TEST',qty:1}]}], []);

test.each([null, undefined, '', ' '])('missing price %p keeps portions known and dependent costs unknown', price => {
  const item=food([{price}]), original=JSON.stringify(item);
  expect(itemDerived(item)).toMatchObject({price:null,priceMissing:true,portionsPerUnit:1,
    costPerPortion:null,rangeUnavailable:false});
  expect(fmtPlanningCost(itemDerived(item).costPerPortion)).toBe('Unknown');
  expect(report(item)).toMatchObject({actualCogs:null,theoreticalCogs:null,liveInventoryValue:null,orderExposure:null});
  expect(JSON.stringify(item)).toBe(original);
});

test.each([{skus:[]}, {skus:[{price:'90',available:false,preferred:true}]}])('absence of an available supplier is unknown, not free: %j', ({skus}) => {
  expect(itemDerived(food(skus))).toMatchObject({price:null,priceMissing:true,costPerPortion:null});
  expect(report(food(skus)).orderExposure).toBeNull();
});

test.each([0, '0', '0E-10'])('explicit zero %p remains a known zero throughout planning', price => {
  const item=food([{price}]);
  expect(itemDerived(item)).toMatchObject({price:0,priceMissing:false,costPerPortion:0,rangeUnavailable:false});
  expect(fmtPlanningCost(itemDerived(item).costPerPortion)).toBe('$0.00');
  expect(report(item)).toMatchObject({actualCogs:0,theoreticalCogs:0,liveInventoryValue:0,orderExposure:0});
  expect(item.vendorSkus[0].price).toBe(price);
});

test('missing price does not hide a separate unsafe portion calculation', () => {
  expect(itemDerived({...food([{price:null}]),portionSize:'1e-400'}))
    .toMatchObject({priceMissing:true,rangeUnavailable:true,costPerPortion:null});
});

test('a free supplier price does not establish sales coverage when menu definitions are absent', () => {
  const result=buildPeriodReport({dishSales:{}},[food([{price:0}])],[],[],[]);
  expect(result.theoreticalCogs).toBeNull();
  expect(result.trackedRows[0].usageIssues).toContain('Menu definitions are unavailable; sales coverage is unconfirmed');
});
