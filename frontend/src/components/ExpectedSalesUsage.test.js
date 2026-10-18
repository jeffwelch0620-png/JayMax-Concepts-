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
async function render(sales={},dishes=[menu],items=[item],key='test',options={}){
  await act(async()=>root.render(<SalesTrackingTab key={key} rid="berts" actualMode items={items} dishes={dishes}
    purchases={[]} adjustments={[]} salesPeriod={{...period,dishSales:sales}} persist={save}
    reportingPeriods={[]} persistReportingPeriods={close} showToast={jest.fn()} {...options}/>));
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

const removal=id=>container.querySelector(`[aria-label="Remove sales entry ${id}"]`);
test('stale working-period IDs are listed while blank unmatched entries do not hold usage or save',async()=>{
  await render({menu:2,retired:'5',blank:''});
  expect(usage().textContent).toBe('Unknown');
  expect(container.querySelector('[data-testid="unmatched-sales-retired"]').textContent).toContain('Stored quantity: 5');
  expect(removal('retired')).not.toBeNull();expect(removal('blank')).toBeNull();
  expect(container.querySelector('[data-testid="load-period-select"]')).toBeNull();
  await act(async()=>jest.advanceTimersByTime(1000));expect(save).not.toHaveBeenCalled();
});
test('cancelling removal preserves the entry and all totals without a save',async()=>{
  const confirmation=jest.spyOn(window,'confirm').mockReturnValue(false);
  try {
    await render({menu:2,retired:'5'});
    await act(async()=>removal('retired').click());
    expect(confirmation).toHaveBeenCalledWith(expect.stringContaining('retired'));
    expect(removal('retired')).not.toBeNull();expect(usage().textContent).toBe('Unknown');
    await act(async()=>jest.advanceTimersByTime(1000));expect(save).not.toHaveBeenCalled();
  } finally {confirmation.mockRestore();}
});
test('confirmed removal deletes only that key through the revisioned save and keeps unrelated drafts',async()=>{
  const confirmation=jest.spyOn(window,'confirm').mockReturnValue(true);
  const drafts=new Map([['other:berts',{untouched:'fictional draft'}]]);
  try {
    await render({menu:2,retired:'5',blank:''},[menu],[item],'test',{revision:7,drafts});
    await act(async()=>removal('retired').click());
    expect(usage().textContent).toBe('4.0');expect(removal('retired')).toBeNull();
    expect(container.textContent).toContain('Unsaved sales draft');expect(save).not.toHaveBeenCalled();
    expect(drafts.get('sales:berts').data.dishSales).toEqual({menu:2,blank:''});
    expect(drafts.get('sales:berts').base.dishSales.retired).toBe('5');
    await act(async()=>jest.advanceTimersByTime(700));
    expect(save).toHaveBeenCalledTimes(1);
    expect(save).toHaveBeenCalledWith({...period,dishSales:{menu:2,blank:''}},7);
    expect(drafts.has('sales:berts')).toBe(false);expect(drafts.get('other:berts')).toEqual({untouched:'fictional draft'});
    expect(close).not.toHaveBeenCalled();
  } finally {confirmation.mockRestore();}
});
test.each(['network failure','revision conflict'])('%s retains a removal draft across remount and never automatically resubmits',async reason=>{
  const confirmation=jest.spyOn(window,'confirm').mockReturnValue(true);
  const drafts=new Map();save.mockRejectedValue(new Error(reason));
  try {
    await render({menu:2,retired:'5'},[menu],[item],'test',{revision:7,drafts});
    await act(async()=>removal('retired').click());
    await act(async()=>jest.advanceTimersByTime(700));
    expect(save).toHaveBeenCalledTimes(1);expect(container.textContent).toContain(reason);
    expect(drafts.get('sales:berts').data.dishSales).toEqual({menu:2});
    expect(drafts.get('sales:berts').base.dishSales.retired).toBe('5');
    await render({menu:2,retired:'5'},[menu],[item],'remount',{revision:7,drafts});
    expect(container.textContent).toContain('Unsaved sales draft');expect(usage().textContent).toBe('4.0');
    await act(async()=>jest.advanceTimersByTime(1000));expect(save).toHaveBeenCalledTimes(1);
    expect(close).not.toHaveBeenCalled();
  } finally {confirmation.mockRestore();}
});
test('retry refuses a competing change to the removed entry and retains the removal draft',async()=>{
  const confirmation=jest.spyOn(window,'confirm').mockReturnValue(true);
  const drafts=new Map();save.mockRejectedValueOnce(new Error('revision conflict'));
  const latest=jest.fn().mockResolvedValue({revision:8,data:{...period,dishSales:{menu:2,retired:'7'}}});
  try {
    await render({menu:2,retired:'5'},[menu],[item],'test',{revision:7,drafts,loadLatestSales:latest});
    await act(async()=>removal('retired').click());
    await act(async()=>jest.advanceTimersByTime(700));
    await act(async()=>container.querySelector('[data-testid="retry-sales-save"]').click());
    expect(latest).toHaveBeenCalledTimes(1);expect(save).toHaveBeenCalledTimes(1);
    expect(container.textContent).toContain('dishSales.retired');
    expect(drafts.get('sales:berts').data.dishSales).toEqual({menu:2});
    expect(drafts.get('sales:berts').revision).toBe(7);expect(close).not.toHaveBeenCalled();
  } finally {confirmation.mockRestore();}
});
test('removal is disabled while a sales save is in flight',async()=>{
  const confirmation=jest.spyOn(window,'confirm').mockReturnValue(true);
  let finish;save.mockImplementation(()=>new Promise(resolve=>{finish=resolve;}));
  try {
    await render({menu:2,retired:'5',another:'6'});
    await act(async()=>removal('retired').click());
    await act(async()=>jest.advanceTimersByTime(700));
    expect(removal('another').disabled).toBe(true);
    await act(async()=>removal('another').click());expect(confirmation).toHaveBeenCalledTimes(1);
    await act(async()=>finish({revision:2}));expect(removal('another').disabled).toBe(false);
  } finally {confirmation.mockRestore();}
});
test('blank broken-menu guidance provides a confirmed-zero recovery choice',async()=>{
  await render({},[{...menu,lines:[]}]);
  expect(container.querySelector('[data-testid="expected-sales-incomplete"]').textContent).toContain('If this menu had no sales, enter a confirmed 0');
  const field=container.querySelector('[data-testid="dish-sales-menu"]');
  await act(async()=>{Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set.call(field,'0');field.dispatchEvent(new Event('input',{bubbles:true}));});
  expect(usage().textContent).toBe('0.0');expect(container.querySelector('[data-testid="expected-sales-incomplete"]')).toBeNull();
});
