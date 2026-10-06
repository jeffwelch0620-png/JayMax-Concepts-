import React, { act } from "react";
import { createRoot } from "react-dom/client";
import { PrepPeriodComparison } from "./PrepPeriodComparison";
import * as api from "../lib/api";
jest.mock("../lib/api");
let root, container;
const counts=[{id:'a',performed_at:'2026-10-05T13:00:00+00:00',timezone_name:'America/New_York',revision:1},{id:'b',performed_at:'2026-10-05T17:00:00+00:00',timezone_name:'America/New_York',revision:2}];
const report={store_id:'berts',opening:counts[0],closing:counts[1],prepared:[{product_id:'protein',name:'Prepared protein',base_unit:'lb',openingQuantity:'10',closingQuantity:'23',recordedProduction:'48',observedDepletion:'35',recordedNestedUseMeasured:'20',recordedNestedUseEstimated:'0',recordedWaste:'5',serviceUseOrUnrecordedLoss:'10.000000000001',flags:[]}],
  rawExplanations:[{raw_item_code:'raw',base_unit:'lb',recordedGrossPrepUseMeasured:'60',recordedGrossPrepUseEstimated:'0',recordedStandaloneRawWaste:'3',recordedRawExplanation:'63',annotatedIncludedTrim:'12',unannotatedInputs:1}],boundaryEvents:{opening:[],closing:[]},includedEvents:[{}]};
const button=text=>[...container.querySelectorAll('button')].find(b=>b.textContent===text);
const click=async el=>act(async()=>el.click());
const select=async(label,value)=>act(async()=>{const el=container.querySelector(`[aria-label="${label}"]`);Object.getOwnPropertyDescriptor(HTMLSelectElement.prototype,'value').set.call(el,value);el.dispatchEvent(new Event('change',{bubbles:true}));});
async function render(rid='berts'){await act(async()=>root.render(<PrepPeriodComparison restaurantId={rid}/>));}
async function choices(){await select('Opening prep count','a');await select('Closing prep count','b');await select('Opening activity cutoff','after_all');await select('Closing activity cutoff','before_all');await click(container.querySelector('[aria-label="Confirm prep period cutoffs"]'));}
beforeEach(()=>{jest.clearAllMocks();global.IS_REACT_ACT_ENVIRONMENT=true;api.nativePrepPeriodCounts.mockResolvedValue({store_id:'berts',counts});api.previewNativePrepPeriod.mockResolvedValue({report,reportHash:'hash'});container=document.createElement('div');document.body.appendChild(container);root=createRoot(container);});
afterEach(async()=>{await act(async()=>root.unmount());container.remove();});
test('period cutoffs are blank and explicit timing confirmation is required',async()=>{
  await render();expect(container.querySelector('[aria-label="Opening activity cutoff"]').value).toBe('');await click(button('Compare prep period'));
  expect(api.previewNativePrepPeriod).not.toHaveBeenCalled();expect(container.textContent).toContain('confirm their timing');
});
test('reports preserve precise decimal strings and distinguish missing service use from waste',async()=>{
  await render();await choices();await click(button('Compare prep period'));
  expect(api.previewNativePrepPeriod).toHaveBeenCalledWith('berts',{opening_count_id:'a',closing_count_id:'b',opening_cutoff:'after_all',closing_cutoff:'before_all',cutoffs_confirmed:true});
  expect(container.textContent).toContain('Service use or unrecorded loss: 10.000000000001');expect(container.textContent).toContain('final expected stock and unexplained variance remain unavailable');expect(container.textContent).toContain('is not deducted again');expect(container.textContent).toContain('Food Cost is unchanged');
});
test('changing boundaries invalidates the displayed comparison and approval',async()=>{
  await render();await choices();await click(button('Compare prep period'));await select('Closing activity cutoff','after_all');
  expect(container.querySelector('[aria-label="Prep period results"]')).toBeNull();expect(container.querySelector('[aria-label="Confirm prep period cutoffs"]').checked).toBe(false);
});
test('same counts and stale count errors never display a successful empty report',async()=>{
  await render();await choices();await select('Closing prep count','a');await click(button('Compare prep period'));expect(api.previewNativePrepPeriod).not.toHaveBeenCalled();
  await select('Closing prep count','b');await click(container.querySelector('[aria-label="Confirm prep period cutoffs"]'));
  api.previewNativePrepPeriod.mockRejectedValue({response:{status:409,data:{detail:'Count changed; refresh current generation'}}});await click(button('Compare prep period'));expect(container.textContent).toContain('Count changed');expect(container.querySelector('[aria-label="Prep period results"]')).toBeNull();
});
test('negative depletion conflicts are retained and refresh clears old results',async()=>{
  api.previewNativePrepPeriod.mockResolvedValue({report:{...report,prepared:[{...report.prepared[0],serviceUseOrUnrecordedLoss:'-3',flags:['recorded_use_exceeds_observed_depletion']}]}});
  await render();await choices();await click(button('Compare prep period'));expect(container.textContent).toContain('Service use or unrecorded loss: -3');expect(container.textContent).toContain('negative differences have been retained');
  await click(button('Refresh period counts'));expect(container.querySelector('[aria-label="Prep period results"]')).toBeNull();expect(container.querySelector('[aria-label="Opening prep count"]').value).toBe('');
});
test('foreign location response and failed setup remain visible failures',async()=>{
  api.previewNativePrepPeriod.mockResolvedValue({report:{...report,store_id:'rudds'}});await render();await choices();await click(button('Compare prep period'));expect(container.textContent).toContain('location was not confirmed');
  api.nativePrepPeriodCounts.mockRejectedValue(new Error('Count setup unavailable'));await click(button('Refresh period counts'));expect(container.textContent).toContain('Count setup unavailable');
});
