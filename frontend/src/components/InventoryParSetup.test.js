import React,{act} from 'react';
import {createRoot} from 'react-dom/client';
import {InventoryParSetup} from './InventoryParSetup';
import {NativeOrderPlanner} from './NativeOrderPlanner';
import {checkedPars,parDecimal} from '../lib/inventoryPars';
import * as api from '../lib/api';
import {pendingParJournal} from '../lib/pendingPars';
jest.mock('../lib/api',()=>({inventoryPars:jest.fn(),reviewInventoryPar:jest.fn(),checkInventoryParStatus:jest.fn(),orderWorkflowEnabled:true,
  createVersionedOrder:jest.fn(),currentSession:()=>({user:{email:'owner@example.invalid'}})}));
jest.mock('./NativeInventoryPosition',()=>({NativeInventoryPosition:()=>null}));
const code='fictional_food',unit='11111111-1111-4111-8111-111111111111',key='22222222-2222-4222-8222-222222222222',actorId='actor-1';
const profile={id:unit,profile_kind:'count',store_id:'berts',item_code:code,source_unit:'bag',base_unit:'lb',base_units_per_source_unit:'5',stale:false};
const saved={id:'33333333-3333-4333-8333-333333333333',store_id:'berts',item_code:code,revision:1,quantity:'6',source_unit:'bag',factor:'5',base_quantity:'30',base_unit:'lb',
  unit_profile_id:unit,confirmed:true,actor:actorId,request_key:key,recorded_at:'2026-10-18T04:00:00Z',coverage_note:'Through next fictional delivery'};
const row={code,name:'Fictional food',legacy_quantity:'2',active:true,review:null,status:'unconfirmed',count_profile:profile};
const result=(review=null,status=review?'confirmed':'unconfirmed')=>({store_id:'berts',available:true,items:[{...row,review,status}]});
let root,container,toast;
const button=text=>[...container.querySelectorAll('button')].find(b=>b.textContent===text);
const click=el=>act(async()=>el.click());
async function fill(label,value){
  const el=container.querySelector(`[aria-label="${label}"]`);
  const type=el.tagName==='SELECT'?HTMLSelectElement:el.tagName==='TEXTAREA'?HTMLTextAreaElement:HTMLInputElement;
  await act(async()=>{Object.getOwnPropertyDescriptor(type.prototype,'value').set.call(el,value);el.dispatchEvent(new Event(el.tagName==='SELECT'?'change':'input',{bubbles:true}));});
}
async function form(quantity='6'){
  await fill('Par product',code);await fill('Par quantity',quantity);await fill('Par stocking unit',unit);
  await fill('Par coverage note','Through next fictional delivery');await click(container.querySelector('[aria-label="Confirm par review"]'));
}
beforeEach(async()=>{
  jest.clearAllMocks();window.sessionStorage.clear();global.IS_REACT_ACT_ENVIRONMENT=true;
  Object.defineProperty(window,'crypto',{value:{randomUUID:()=> key},configurable:true});
  api.inventoryPars.mockResolvedValue(result());
  api.reviewInventoryPar.mockImplementation(async(rid,code,body,version,key)=>{const review={...saved,request_key:key,quantity:body.quantity,base_quantity:body.quantity==='0'?'0':'30',revision:version+1,confirmed:body.action==='confirm'};return {request_key:key,review,current_review:review};});
  api.checkInventoryParStatus.mockImplementation(async(rid,code,body,version,key)=>({store_id:rid,item_code:code,actor:actorId,request_key:key,expected_revision:version,outcome:'retry_available',review:null,current_review:null,message:'No saved request visible; exact retry only.'}));
  container=document.createElement('div');document.body.appendChild(container);root=createRoot(container);toast=jest.fn();
  await act(async()=>root.render(<InventoryParSetup actorId={actorId} rid="berts" drafts={new Map()} showToast={toast}/>));
});
afterEach(async()=>{await act(async()=>root.unmount());container.remove();});

test('legacy numbers stay unconfirmed and are not copied into a target',async()=>{
  await fill('Par product',code);
  expect(container.textContent).toContain('Unconfirmed legacy value: 2; unit not established');
  expect(container.querySelector('[aria-label="Par quantity"]').value).toBe('');
  expect(api.reviewInventoryPar).not.toHaveBeenCalled();
});
test('explicit zero uses a confirmed unit and server-reviewed save acknowledgement',async()=>{
  await form('0');await click(button('Confirm inventory par'));
  expect(api.reviewInventoryPar).toHaveBeenCalledWith('berts',code,{action:'confirm',quantity:'0',unit_profile_id:unit,coverage_note:'Through next fictional delivery',verified:true},0,key);
  expect(toast).toHaveBeenCalledTimes(1);expect(container.textContent).not.toContain('Retained confirm review');
});
test.each(['','-1','1e400','1.1234567890123'])('invalid quantity %p is refused without a write',async value=>{
  await form(value);await click(button('Confirm inventory par'));
  expect(api.reviewInventoryPar).not.toHaveBeenCalled();expect(container.textContent).toContain('nonnegative exact quantity');
});
test('lost response freezes the body and retries the exact request',async()=>{
  api.reviewInventoryPar.mockRejectedValueOnce(new Error('Lost response'));
  await form();await click(button('Confirm inventory par'));
  const original=api.reviewInventoryPar.mock.calls[0];
  expect(container.querySelector('[aria-label="Par quantity"]').closest('fieldset').disabled).toBe(true);
  expect(toast).not.toHaveBeenCalled();await click(button('Check saved par status'));await click(button('Retry same par review'));
  expect(api.reviewInventoryPar.mock.calls[1]).toEqual(original);expect(toast).toHaveBeenCalledTimes(1);
});
test('a mismatched acknowledgement is not called success',async()=>{
  api.reviewInventoryPar.mockResolvedValue({request_key:key,review:{...saved,quantity:'999'}});
  await form();await click(button('Confirm inventory par'));
  expect(toast).not.toHaveBeenCalled();expect(button('Retry same par review')).toBeDefined();
});
test('conflict retains typed values until explicit latest review and reconfirmation',async()=>{
  api.reviewInventoryPar.mockRejectedValueOnce({response:{status:409,data:{detail:'Par changed'}}});
  await form();await click(button('Confirm inventory par'));
  expect(container.querySelector('[aria-label="Par quantity"]').value).toBe('6');
  api.inventoryPars.mockResolvedValue(result({...saved,revision:2,quantity:'8',base_quantity:'40'}));
  api.checkInventoryParStatus.mockResolvedValue({store_id:'berts',item_code:code,actor:actorId,request_key:key,expected_revision:0,outcome:'not_saved_superseded',review:null,current_review:{...saved,revision:2},message:'Another review advanced this product.'});
  await click(button('Check saved par status'));await click(button('Review current par and retained values'));
  expect(container.querySelector('[aria-label="Confirm par review"]').checked).toBe(false);
  expect(container.querySelector('[aria-label="Par quantity"]').value).toBe('6');
  await click(container.querySelector('[aria-label="Confirm par review"]'));await click(button('Confirm inventory par'));
  expect(api.reviewInventoryPar.mock.calls[1][3]).toBe(2);
});
test('an unavailable installation has no confirmation controls',async()=>{
  api.inventoryPars.mockResolvedValue({...result(),available:false});await click(button('Reload latest par review'));
  expect(button('Confirm inventory par')).toBeUndefined();expect(container.textContent).toContain('awaiting installation');
  expect(api.reviewInventoryPar).not.toHaveBeenCalled();
});
test('late old-location acknowledgements cannot change the current location',async()=>{
  let finish;api.reviewInventoryPar.mockImplementation(()=>new Promise(resolve=>{finish=resolve;}));
  await form();act(()=>button('Confirm inventory par').click());
  api.inventoryPars.mockResolvedValue({store_id:'rudds',available:true,items:[]});
  await act(async()=>root.render(<InventoryParSetup actorId={actorId} rid="rudds" showToast={toast}/>));
  await act(async()=>finish({request_key:key,review:saved}));
  expect(toast).not.toHaveBeenCalled();expect(container.textContent).not.toContain('Confirmed target');
});
test('order planning displays the same explicit basis and never fills a suggested order',async()=>{
  api.inventoryPars.mockResolvedValue(result(saved));
  const items=[{itemCode:code,controlNumber:'F01',name:'Fictional food',classification:'raw',orderEnabled:true,par:'2',countUnit:'case',
    vendorSkus:[{id:'vendor-a',vendorId:'a',vendor:'A',vendorSku:'A1',purchaseUnit:'case',price:'10'}]}];
  await act(async()=>root.render(<NativeOrderPlanner rid="berts" items={items}/>));
  expect(container.textContent).toContain('6 bag = 30 lb');expect(container.textContent).toContain('Confirmed target');
  expect(container.querySelector(`[aria-label="Order quantity ${code}"]`).value).toBe('');
  expect(api.createVersionedOrder).not.toHaveBeenCalled();expect(api.reviewInventoryPar).not.toHaveBeenCalled();
});
test('wrong-location and malformed reads fail closed',()=>{
  for(const bad of [{...result(),store_id:'rudds'},result(saved,'unknown'),result({...saved,store_id:'rudds'}),result({...saved,base_quantity:'NaN'}),result({...saved,factor:'99'}),result({...saved,actor:{}}),{...result(),items:[row,row]}]){
    expect(()=>checkedPars(bad,'berts')).toThrow();
  }
});
test('small exact decimal strings from PostgreSQL remain valid without underflow coercion',()=>{
  expect(checkedPars(result({...saved,quantity:'1E-12',base_quantity:'5E-12'}),'berts').items[0].review.quantity).toBe('1E-12');
  expect(()=>checkedPars(result({...saved,quantity:'1E-400'}),'berts')).toThrow();
});
test('the largest permitted target is validated without rounding through Number',()=>{
  expect(parDecimal('9999999999999999.999999999999')).toBe(true);
  expect(parDecimal('10000000000000000')).toBe(false);
  expect(parDecimal('0.000000000001')).toBe(true);
});
test('a saved par refreshes the catalog revision without treating a refresh failure as an uncertain save',async()=>{
  const refresh=jest.fn().mockRejectedValue(new Error('Fictional read failure'));
  await act(async()=>root.render(<InventoryParSetup actorId={actorId} rid="berts" showToast={toast} onSaved={refresh}/>));
  await form();await click(button('Confirm inventory par'));
  expect(refresh).toHaveBeenCalledTimes(1);expect(toast).toHaveBeenCalledTimes(1);
  expect(container.textContent).toContain('Par saved, but the catalog refresh failed');
  expect(button('Retry same par review')).toBeUndefined();
});
test('an uncertain retained command remains retryable when its remounted reference read fails',async()=>{
  const drafts=new Map();
  await act(async()=>root.render(<InventoryParSetup actorId={actorId} rid="berts" drafts={drafts} showToast={toast}/>));
  api.reviewInventoryPar.mockRejectedValueOnce(new Error('Lost response'));
  await form();await click(button('Confirm inventory par'));const original=api.reviewInventoryPar.mock.calls[0];
  await act(async()=>root.render(<div/>));api.inventoryPars.mockRejectedValue(new Error('Fictional read outage'));
  await act(async()=>root.render(<InventoryParSetup actorId={actorId} rid="berts" drafts={drafts} showToast={toast}/>));
  expect(container.textContent).toContain('Par review unavailable');
  await click(button('Check saved par status'));await click(button('Retry same par review'));
  expect(api.reviewInventoryPar.mock.calls[1]).toEqual(original);expect(toast).toHaveBeenCalledTimes(1);
});

test('reload retains the exact request, checks without writing and resolves a lost committed response',async()=>{
  api.reviewInventoryPar.mockRejectedValueOnce(new Error('Lost committed response'));
  await form();await click(button('Confirm inventory par'));
  const original=api.reviewInventoryPar.mock.calls[0];
  await act(async()=>root.render(<div/>));
  await act(async()=>root.render(<InventoryParSetup actorId={actorId} rid="berts" drafts={new Map()} showToast={toast}/>));
  expect(container.textContent).toContain('Retained confirm review');expect(api.reviewInventoryPar).toHaveBeenCalledTimes(1);
  expect(button('Retry same par review').disabled).toBe(true);
  api.checkInventoryParStatus.mockResolvedValue({store_id:'berts',item_code:code,actor:actorId,request_key:key,expected_revision:0,
    outcome:'saved_current',review:saved,current_review:saved});
  await click(button('Check saved par status'));
  expect(api.checkInventoryParStatus.mock.calls[0]).toEqual(original);
  expect(api.reviewInventoryPar).toHaveBeenCalledTimes(1);expect(pendingParJournal(actorId,'berts').list()).toEqual([]);
  expect(toast).toHaveBeenCalledTimes(1);
});

test.each([401,403,409,429,503])('HTTP %p never erases an unresolved request',async status=>{
  api.reviewInventoryPar.mockRejectedValueOnce({response:{status,data:{detail:'Fictional refusal'}}});
  await form();await click(button('Confirm inventory par'));
  expect(pendingParJournal(actorId,'berts').list()).toHaveLength(1);
  expect(button('Retry same par review').disabled).toBe(true);
});

test('another signed-in user cannot see or acknowledge the retained request',async()=>{
  let finish;api.reviewInventoryPar.mockImplementation(()=>new Promise(resolve=>{finish=resolve;}));
  await form();act(()=>button('Confirm inventory par').click());
  await act(async()=>root.render(<InventoryParSetup actorId="another-user" rid="berts" showToast={toast}/>));
  await act(async()=>finish({request_key:key,review:saved,current_review:saved}));
  expect(toast).not.toHaveBeenCalled();expect(container.textContent).not.toContain('Retained confirm review');
  expect(pendingParJournal(actorId,'berts').list()).toHaveLength(1);
  await act(async()=>root.render(<InventoryParSetup actorId={actorId} rid="berts" drafts={new Map()} showToast={toast}/>));
  expect(container.textContent).toContain('Retained confirm review');expect(api.reviewInventoryPar).toHaveBeenCalledTimes(1);
});

test('a later saved review is reported without restoring the older target',async()=>{
  api.reviewInventoryPar.mockRejectedValueOnce(new Error('Lost response'));await form();await click(button('Confirm inventory par'));
  const later={...saved,id:'44444444-4444-4444-8444-444444444444',revision:2,quantity:'9',base_quantity:'45'};
  api.checkInventoryParStatus.mockResolvedValue({store_id:'berts',item_code:code,actor:actorId,request_key:key,expected_revision:0,outcome:'saved_superseded',review:saved,current_review:later});
  api.inventoryPars.mockResolvedValue(result(later));await click(button('Check saved par status'));
  expect(api.reviewInventoryPar).toHaveBeenCalledTimes(1);expect(toast).toHaveBeenCalledWith('Your par review was saved; a later review is now current.');
  expect(container.textContent).toContain('9 bag = 45 lb');
});

test('a delayed commit after the first status read is resolved by retry preflight without a second write',async()=>{
  api.reviewInventoryPar.mockRejectedValueOnce(new Error('Lost response'));await form();await click(button('Confirm inventory par'));
  await click(button('Check saved par status'));
  api.checkInventoryParStatus.mockResolvedValue({store_id:'berts',item_code:code,actor:actorId,request_key:key,expected_revision:0,outcome:'saved_current',review:saved,current_review:saved});
  await click(button('Retry same par review'));
  expect(api.reviewInventoryPar).toHaveBeenCalledTimes(1);expect(pendingParJournal(actorId,'berts').list()).toHaveLength(0);
});

test('storage quota failure before sending refuses the write',async()=>{
  await form();const spy=jest.spyOn(Storage.prototype,'setItem').mockImplementation(()=>{throw new Error('Quota');});
  try{await click(button('Confirm inventory par'));expect(api.reviewInventoryPar).not.toHaveBeenCalled();expect(container.textContent).toContain('recovery is unavailable');}
  finally{spy.mockRestore();}
});

test('corrupt recovery storage blocks a fresh form without deleting its evidence',async()=>{
  const storageKey=`jaymax:pending-pars:v1:${actorId}:berts`;
  window.sessionStorage.setItem(storageKey,'bad-json');
  await act(async()=>root.render(<div/>));await act(async()=>root.render(<InventoryParSetup actorId={actorId} rid="berts"/>));
  expect(container.textContent).toContain('recovery is unavailable');expect(api.reviewInventoryPar).not.toHaveBeenCalled();
  expect(window.sessionStorage.getItem(storageKey)).toBe('bad-json');
});

test('journal cleanup failure after a confirmed save cannot enable another write',async()=>{
  await form();api.reviewInventoryPar.mockImplementation(async()=>{
    jest.spyOn(Storage.prototype,'setItem').mockImplementation(()=>{throw new Error('Cleanup quota');});
    return {request_key:key,review:saved,current_review:saved};
  });
  try{await click(button('Confirm inventory par'));expect(container.textContent).toContain('Par saved, but retained-request cleanup failed');expect(button('Retry same par review').disabled).toBe(true);expect(api.reviewInventoryPar).toHaveBeenCalledTimes(1);}
  finally{jest.restoreAllMocks();}
});

test('withdrawal survives reload using its frozen predecessor quantities and units',async()=>{
  api.inventoryPars.mockResolvedValue(result(saved));
  await act(async()=>root.render(<div/>));await act(async()=>root.render(<InventoryParSetup actorId={actorId} rid="berts"/>));
  api.reviewInventoryPar.mockRejectedValueOnce(new Error('Lost withdrawal response'));
  await form();await click(button('Withdraw par confirmation'));
  const original=api.reviewInventoryPar.mock.calls[0],record=pendingParJournal(actorId,'berts').list()[0];
  expect(record.body.action).toBe('withdraw');expect(record.prior.base_unit).toBe('lb');expect(record.profile).toBeNull();
  const withdrawn={...saved,id:'55555555-5555-4555-8555-555555555555',revision:2,confirmed:false,predecessor_id:saved.id};
  api.checkInventoryParStatus.mockResolvedValue({store_id:'berts',item_code:code,actor:actorId,request_key:key,expected_revision:1,outcome:'saved_current',review:withdrawn,current_review:withdrawn});
  await act(async()=>root.render(<div/>));await act(async()=>root.render(<InventoryParSetup actorId={actorId} rid="berts"/>));
  api.inventoryPars.mockResolvedValue(result(withdrawn,'unconfirmed'));
  await click(button('Check saved par status'));
  expect(api.checkInventoryParStatus.mock.calls[0]).toEqual(original);expect(api.reviewInventoryPar).toHaveBeenCalledTimes(1);
  expect(pendingParJournal(actorId,'berts').list()).toEqual([]);
});

test('contradictory saved-current proof is retained without another write',async()=>{
  api.reviewInventoryPar.mockRejectedValueOnce(new Error('Lost response'));await form();await click(button('Confirm inventory par'));
  api.checkInventoryParStatus.mockResolvedValue({store_id:'berts',item_code:code,actor:actorId,request_key:key,expected_revision:0,outcome:'saved_current',review:saved,current_review:{...saved,quantity:'9',base_quantity:'45'}});
  await click(button('Check saved par status'));
  expect(pendingParJournal(actorId,'berts').list()).toHaveLength(1);expect(toast).not.toHaveBeenCalled();expect(button('Retry same par review').disabled).toBe(true);
});

function recoveryStatus(record,outcome='held',current_review=null){
  return {store_id:'berts',item_code:record.code,actor:actorId,request_key:record.key,expected_revision:record.version,
    outcome,review:null,current_review,message:'Count conversion changed or is unconfirmed.'};
}
async function prepareDiscard(){
  api.reviewInventoryPar.mockRejectedValueOnce({response:{status:409,data:{detail:'Count conversion changed'}}});
  await form();await click(button('Confirm inventory par'));
  const record=pendingParJournal(actorId,'berts').list()[0];
  expect(button("Discard this tab's retained par request")).toBeUndefined();
  api.checkInventoryParStatus.mockResolvedValue(recoveryStatus(record));
  await click(button('Check saved par status'));await click(button("Discard this tab's retained par request"));
  return record;
}

test('held conversion refusal can be discarded locally after fresh status and current-value reads',async()=>{
  const record=await prepareDiscard();
  const dialog=container.querySelector('[role="dialog"]');
  expect(dialog.textContent).toContain(code);expect(dialog.textContent).toContain('6 bag');
  expect(dialog.textContent).toContain(record.body.coverage_note);expect(dialog.textContent).toContain('may still complete');
  expect(pendingParJournal(actorId,'berts').list()).toEqual([record]);
  await click(button('Confirm discard retained par request'));
  expect(api.checkInventoryParStatus).toHaveBeenCalledTimes(2);expect(api.inventoryPars).toHaveBeenCalledTimes(2);
  expect(api.reviewInventoryPar).toHaveBeenCalledTimes(1);expect(toast).not.toHaveBeenCalled();
  expect(pendingParJournal(actorId,'berts').list()).toEqual([]);expect(container.querySelector('[role="dialog"]')).toBeNull();
  expect(container.querySelector('fieldset').disabled).toBe(false);expect(container.querySelector('[aria-label="Par product"]').value).toBe('');
  expect(container.querySelector('[aria-label="Par quantity"]').value).toBe('');expect(container.querySelector('[aria-label="Confirm par review"]').checked).toBe(false);
  expect(button('Confirm inventory par').disabled).toBe(true);expect(container.textContent).toContain('was not cancelled and may still complete');
});

test('cancelling local discard retains evidence and sends no fresh check or write',async()=>{
  const record=await prepareDiscard();await click(button('Keep retained par request'));
  expect(container.querySelector('[role="dialog"]')).toBeNull();expect(pendingParJournal(actorId,'berts').list()).toEqual([record]);
  expect(api.checkInventoryParStatus).toHaveBeenCalledTimes(1);expect(api.reviewInventoryPar).toHaveBeenCalledTimes(1);
  expect(container.querySelector('fieldset').disabled).toBe(true);
});

test.each(['retry_available','not_saved_superseded'])('fresh %s permits local discard without resubmitting',async outcome=>{
  const record=await prepareDiscard(),current=outcome==='not_saved_superseded'?{...saved,revision:2}:null;
  api.checkInventoryParStatus.mockResolvedValue(recoveryStatus(record,outcome,current));
  api.inventoryPars.mockResolvedValue(result(current));await click(button('Confirm discard retained par request'));
  expect(pendingParJournal(actorId,'berts').list()).toEqual([]);expect(api.reviewInventoryPar).toHaveBeenCalledTimes(1);
  expect(container.querySelector('[aria-label="Confirm par review"]').checked).toBe(false);
});

test.each(['saved_current','saved_superseded'])('fresh %s during discard resolves the committed request as saved',async outcome=>{
  const record=await prepareDiscard(),current=outcome==='saved_current'?saved:{...saved,id:'44444444-4444-4444-8444-444444444444',revision:2};
  api.checkInventoryParStatus.mockResolvedValue({...recoveryStatus(record,outcome,current),review:saved});
  api.inventoryPars.mockResolvedValue(result(current));await click(button('Confirm discard retained par request'));
  expect(toast).toHaveBeenCalledTimes(1);expect(pendingParJournal(actorId,'berts').list()).toEqual([]);
  expect(api.reviewInventoryPar).toHaveBeenCalledTimes(1);expect(container.textContent).not.toContain('Recovery record removed');
  expect(container.querySelector('[role="dialog"]')).toBeNull();
});

test.each(['network','401','invalid proof'])('discard keeps evidence when its fresh status fails: %s',async failure=>{
  const record=await prepareDiscard();
  if(failure==='invalid proof')api.checkInventoryParStatus.mockResolvedValue({...recoveryStatus(record),actor:'another-user'});
  else api.checkInventoryParStatus.mockRejectedValueOnce(failure==='401'?{response:{status:401,data:{detail:'Authentication required'}}}:new Error('Read failed'));
  await click(button('Confirm discard retained par request'));
  expect(pendingParJournal(actorId,'berts').list()).toEqual([record]);expect(container.querySelector('fieldset').disabled).toBe(true);
  expect(api.inventoryPars).toHaveBeenCalledTimes(1);expect(api.reviewInventoryPar).toHaveBeenCalledTimes(1);expect(toast).not.toHaveBeenCalled();
});

test('held request survives reload and needs a new explicit check before discard',async()=>{
  const record=await prepareDiscard();await act(async()=>root.render(<div/>));
  await act(async()=>root.render(<InventoryParSetup actorId={actorId} rid="berts" drafts={new Map()}/>));
  expect(container.textContent).toContain('Retained confirm review');expect(container.querySelector('[role="dialog"]')).toBeNull();
  expect(button("Discard this tab's retained par request")).toBeUndefined();expect(pendingParJournal(actorId,'berts').list()).toEqual([record]);
  await click(button('Check saved par status'));expect(button("Discard this tab's retained par request")).toBeDefined();
});

test('discard retains the request if the current-value refresh fails',async()=>{
  const record=await prepareDiscard();api.inventoryPars.mockRejectedValueOnce(new Error('Current read failed'));
  await click(button('Confirm discard retained par request'));
  expect(pendingParJournal(actorId,'berts').list()).toEqual([record]);expect(container.textContent).toContain('has not been discarded');
  expect(container.querySelector('[role="dialog"]')).not.toBeNull();expect(api.reviewInventoryPar).toHaveBeenCalledTimes(1);
});

test('discard cleanup failure preserves the journal and blocks new writes',async()=>{
  const record=await prepareDiscard(),spy=jest.spyOn(Storage.prototype,'setItem').mockImplementation(()=>{throw new Error('Cleanup quota');});
  try{
    await click(button('Confirm discard retained par request'));
    expect(pendingParJournal(actorId,'berts').list()).toEqual([record]);expect(container.querySelector('fieldset').disabled).toBe(true);
    expect(button('Confirm discard retained par request').disabled).toBe(true);expect(api.reviewInventoryPar).toHaveBeenCalledTimes(1);
  }finally{spy.mockRestore();}
});

test.each(['actor','location'])('late discard status cannot clear the old request after a %s change',async changed=>{
  const record=await prepareDiscard();let finish;
  api.checkInventoryParStatus.mockImplementationOnce(()=>new Promise(resolve=>{finish=resolve;}));
  act(()=>button('Confirm discard retained par request').click());
  api.inventoryPars.mockResolvedValue(changed==='actor'?result():{store_id:'rudds',available:true,items:[]});
  await act(async()=>root.render(<InventoryParSetup actorId={changed==='actor'?'another-user':actorId} rid={changed==='location'?'rudds':'berts'} showToast={toast}/>));
  await act(async()=>finish(recoveryStatus(record)));
  expect(pendingParJournal(actorId,'berts').list()).toEqual([record]);expect(toast).not.toHaveBeenCalled();
  expect(container.querySelector('[role="dialog"]')).toBeNull();expect(container.textContent).not.toContain('Recovery record removed');
});

test('withdrawal discard shows frozen predecessor quantities, units and note',async()=>{
  api.inventoryPars.mockResolvedValue(result(saved));await click(button('Reload latest par review'));
  await form();api.reviewInventoryPar.mockRejectedValueOnce(new Error('Withdrawal response lost'));
  await click(button('Withdraw par confirmation'));const record=pendingParJournal(actorId,'berts').list()[0];
  api.checkInventoryParStatus.mockResolvedValue(recoveryStatus(record,'held',saved));
  await click(button('Check saved par status'));await click(button("Discard this tab's retained par request"));
  expect(container.querySelector('[role="dialog"]').textContent).toContain('withdraw. Quantity: 6 bag. Physical quantity: 30 lb');
  expect(container.querySelector('[role="dialog"]').textContent).toContain(record.body.coverage_note);
  await click(button('Confirm discard retained par request'));expect(pendingParJournal(actorId,'berts').list()).toEqual([]);
  expect(api.reviewInventoryPar).toHaveBeenCalledTimes(1);expect(container.querySelector('[aria-label="Confirm par review"]').checked).toBe(false);
});

test('a commit after the negative status can appear on refresh without being called cancelled or causing another write',async()=>{
  await prepareDiscard();api.inventoryPars.mockResolvedValue(result(saved));
  await click(button('Confirm discard retained par request'));
  await fill('Par product',code);
  expect(container.textContent).toContain('6 bag = 30 lb');expect(container.textContent).toContain('may still complete');
  expect(container.querySelector('[aria-label="Par quantity"]').value).toBe('');expect(button('Confirm inventory par').disabled).toBe(true);
  expect(api.reviewInventoryPar).toHaveBeenCalledTimes(1);expect(toast).not.toHaveBeenCalled();
});

test('discard clears only the selected request and keeps the location frozen for another retained product',async()=>{
  const record=await prepareDiscard(),other={...record,code:'other_food',key:'66666666-6666-4666-8666-666666666666'};
  pendingParJournal(actorId,'berts').save(other);await act(async()=>root.render(<div/>));
  await act(async()=>root.render(<InventoryParSetup actorId={actorId} rid="berts"/>));
  await click(button('Check saved par status'));await click(button("Discard this tab's retained par request"));await click(button('Confirm discard retained par request'));
  expect(pendingParJournal(actorId,'berts').list()).toEqual([other]);expect(container.querySelector('fieldset').disabled).toBe(true);
  expect(container.textContent).toContain('Retained confirm review for other_food');expect(api.reviewInventoryPar).toHaveBeenCalledTimes(1);
});
