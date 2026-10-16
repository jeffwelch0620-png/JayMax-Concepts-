import { itemDerived, itemPlanningCost, recipeCostSummary, buildPeriodReport, fmtPlanningCost, vendorUnitsForShortfall } from './calc';
import { planningProduct, planningQuotient } from './planningNumbers';

const food = () => ({controlNumber:'TEST',name:'Fictional',salesTracked:true,currentStock:1,par:2,
  packCount:'1',unitQty:'1',unitUOM:'each',portionSize:'1',portionUOM:'each',
  vendorSkus:[{price:'1',packCount:'1',unitQty:'1',unitUOM:'each'}]});
const dish={id:'dish',name:'Fictional plate',price:10,lines:[{controlNumber:'TEST',qty:1}]};

test.each(['1e400','1e-400'])('unsafe price %s remains unavailable through preview, recipes and report totals', price => {
  const item=food(); item.vendorSkus[0].price=price;
  expect(itemDerived(item)).toMatchObject({rangeUnavailable:true,costPerPortion:null});
  expect(itemPlanningCost(item).cost).toBeNull();
  expect(recipeCostSummary(dish,[item],[dish])).toMatchObject({complete:false,totalCost:null,costPerYieldUnit:null});
  const report=buildPeriodReport({periodStart:'2026-10-01',periodEnd:'2026-10-31',itemCounts:{TEST:{beginning:2,ending:1}}},[item],[],[dish],
    [{controlNumber:'TEST',date:'2026-10-10',qty:1,qtyBasis:'portion',reason:'waste'}]);
  for(const key of ['theoreticalCogs','actualCogs','explainedCost','unexplainedCost','liveInventoryValue','orderExposure']) expect(report[key]).toBeNull();
  expect(report.wasteByReason.Waste).toBeNull(); expect(report.menuProfitability[0].cost).toBeNull();
  expect(fmtPlanningCost(report.actualCogs)).toBe('Unknown');
  expect(item.vendorSkus[0].price).toBe(price);
});

test.each([
  ['packCount','1e400'],['unitQty','1e-400'],['portionSize','1e-400'],
])('unsafe %s does not become a zero preview', (key,value) => {
  const item=food();item[key]=value;
  if(key!=='portionSize')item.vendorSkus[0][key]=value;
  expect(itemDerived(item)).toMatchObject({rangeUnavailable:true,costPerPortion:null});
  expect(itemPlanningCost(item).cost).toBeNull();
  if(key !== 'portionSize') expect(vendorUnitsForShortfall(item,item.vendorSkus[0],1).units).toBeNull();
});

test('finite operands with unsafe arithmetic and nested costs stay unavailable; real zero stays zero', () => {
  for(const result of [planningProduct(1e308,2),planningProduct(1e-308,1e-308),planningQuotient(1e308,1e-308),planningQuotient(1e-308,1e308)]) expect(result).toBeNull();
  const item=food();item.vendorSkus[0].price='1e308';
  const prep={...dish,id:'prep',recipeType:'prep',yieldQty:1,yieldUOM:'each',lines:[{controlNumber:'TEST',qty:2}]};
  const parent={...dish,lines:[{sourceType:'prep',recipeId:'prep',qty:1}]};
  expect(recipeCostSummary(parent,[item],[prep,parent]).totalCost).toBeNull();
  item.vendorSkus[0].price='0E-10';
  expect(itemPlanningCost(item).cost).toBe(0);
  expect(recipeCostSummary(dish,[item],[dish])).toMatchObject({complete:true,totalCost:0});
  expect(fmtPlanningCost(0)).toBe('$0.00');
});
