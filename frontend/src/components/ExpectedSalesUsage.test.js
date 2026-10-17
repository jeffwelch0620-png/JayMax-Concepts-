import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import { SalesTrackingTab } from './SalesTrackingTab';

const item={itemCode:'global_food',controlNumber:'LOCAL',name:'Fictional food',salesTracked:true,vendorSkus:[]};
const menu={id:'menu',name:'Fictional menu',recipeType:'menu',lines:[{sourceType:'item',itemCode:'global_food',qty:2}]};
const period={periodStart:'2026-10-01',periodEnd:'2026-10-07',dishSales:{},itemCounts:{LOCAL:{beginning:999,ending:0}}};
let root,container,save,close;
beforeEach(()=>{
  global.IS_REACT_ACT_ENVIRONMENT=true;jest.useFakeTimers();
  container=document.createElement('div');document.body.appendChild(container);root=createRoot(container);
  save=jest.fn().mockResolvedValue({revision:2});close=jest.fn();
});
afterEach(async()=>{await act(async()=>root.unmount());container.remove();jest.useRealTimers();});
async function render(sales={},dishes=[menu],items=[item],key='test'){
  await act(async()=>root.render(<SalesTrackingTab key={key} rid="berts" actualMode items={items} dishes={dishes}
    purchases={[]} adjustments={[]} salesPeriod={{...period,dishSales:sales}} persist={save}
    reportingPeriods={[]} persistReportingPeriods={close} showToast={jest.fn()}/>));
}
const usage=(code='LOCAL')=>container.querySelector(`[data-testid="expected-usage-${code}"]`);

test('blank sales are unknown, explicit zero is known, and rendering never saves or closes accounting',async()=>{
  await render();expect(usage().textContent).toBe('Unknown');expect(container.textContent).toContain('Blank quantities are unknown');
  expect(container.querySelector('[data-testid="save-period-button"]')).toBeNull();
  expect(container.querySelector('[data-testid="beginning-LOCAL"]')).toBeNull();
  expect(container.querySelector('[data-testid="variance-table"]').textContent).not.toContain('Actual');
  await render({menu:'0'},[menu],[item],'zero');expect(usage().textContent).toBe('0.0');
  expect(container.querySelector('[data-testid="expected-sales-incomplete"]')).toBeNull();
  await act(async()=>jest.advanceTimersByTime(1000));expect(save).not.toHaveBeenCalled();expect(close).not.toHaveBeenCalled();
});
test('canonical nested usage works without any supplier prices or verified physical profile',async()=>{
  const prep={id:'prep',name:'Fictional prep',recipeType:'prep',yieldQty:4,yieldUOM:'lb',
    lines:[{sourceType:'item',itemCode:'global_food',qty:8,uom:'portion'}]};
  await render({menu:3},[{...menu,lines:[{sourceType:'prep',recipeId:'prep',qty:2,uom:'lb'}]},prep]);
  expect(usage().textContent).toBe('12.0');expect(container.textContent).not.toContain('supplier price');
  expect(save).not.toHaveBeenCalled();expect(close).not.toHaveBeenCalled();
});
test('a broken recipe cannot produce a partial expected total and still leaves the sales editor usable',async()=>{
  const broken={id:'bad',name:'Broken fictional menu',lines:[{sourceType:'prep',recipeId:'missing',qty:1}]};
  await render({menu:2,bad:1},[menu,broken]);
  expect(usage().textContent).toBe('Unknown');expect(usage().title).toContain('retained prep recipe');
  expect(container.querySelector('[data-testid="dish-sales-menu"]').disabled).toBe(false);
  expect(container.querySelector('[data-testid="expected-sales-incomplete"]').textContent).toContain('Broken fictional menu');
  expect(save).not.toHaveBeenCalled();expect(close).not.toHaveBeenCalled();
});
test.each([['null line',[null]], ['wrong shape',{unexpected:'shape'}]])('malformed ingredient list %s shows review guidance without crashing the native panel',async (_,lines)=>{
  await render({menu:2},[{...menu,lines}]);
  expect(usage().textContent).toBe('Unknown');
  expect(container.querySelector('[data-testid="dish-sales-menu"]').disabled).toBe(false);
  expect(container.querySelector('[data-testid="expected-sales-incomplete"]')).not.toBeNull();
  expect(save).not.toHaveBeenCalled();expect(close).not.toHaveBeenCalled();
});
test('missing sales for an independently mapped item do not erase a confirmed item total',async()=>{
  const other={...item,itemCode:'other_food',controlNumber:'OTHER',name:'Other fictional food'};
  const otherMenu={...menu,id:'other',name:'Other fictional menu',lines:[{sourceType:'item',itemCode:'other_food',qty:1}]};
  await render({menu:2},[menu,otherMenu],[item,other]);
  expect(usage().textContent).toBe('4.0');expect(usage('OTHER').textContent).toBe('Unknown');
});
test('editing an unknown sales quantity updates the estimate and preserves the existing debounced save contract',async()=>{
  await render();const field=container.querySelector('[data-testid="dish-sales-menu"]');
  await act(async()=>{Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set.call(field,'3');field.dispatchEvent(new Event('input',{bubbles:true}));});
  expect(usage().textContent).toBe('6.0');expect(save).not.toHaveBeenCalled();
  await act(async()=>jest.advanceTimersByTime(700));
  expect(save).toHaveBeenCalledTimes(1);expect(save.mock.calls[0][0]).toEqual({...period,dishSales:{menu:'3'}});
  expect(close).not.toHaveBeenCalled();
});
