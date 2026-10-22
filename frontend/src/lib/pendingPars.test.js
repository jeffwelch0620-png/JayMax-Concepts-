import {pendingParJournal,pendingParRecord,checkedParStatus} from './pendingPars';

const unit='11111111-1111-4111-8111-111111111111',key='22222222-2222-4222-8222-222222222222';
const prior={id:'33333333-3333-4333-8333-333333333333',revision:1,quantity:'6',base_quantity:'30',unit_profile_id:unit,factor:'5',source_unit:'bag',base_unit:'lb'};
const submitted={key,code:'F01',version:0,body:{action:'confirm',quantity:'6',unit_profile_id:unit,coverage_note:'Fictional coverage',verified:true},
  profile:{id:unit,source_unit:'bag',base_unit:'lb',base_units_per_source_unit:'5',arbitrary:'not retained'},prior:null};
function storage(){const map=new Map();return {getItem:k=>map.get(k)??null,setItem:(k,v)=>map.set(k,v),map};}

test('retains only bounded request evidence and survives journal recreation for the same actor and store',()=>{
  const s=storage(),r=pendingParRecord({...submitted,token:'never retain'});
  const journal=pendingParJournal('actor','berts',()=>s);journal.save(r);
  expect(pendingParJournal('actor','berts',()=>s).list()).toEqual([r]);expect(JSON.stringify(r)).not.toContain('arbitrary');
  expect(JSON.stringify(r)).not.toContain('token');expect(pendingParJournal('other','berts',()=>s).list()).toEqual([]);
  expect(pendingParJournal('actor','rudds',()=>s).list()).toEqual([]);
});

test('different exact requests for one product and reused keys cannot replace retained evidence',()=>{
  const s=storage(),j=pendingParJournal('actor','berts',()=>s),r=pendingParRecord(submitted);j.save(r);j.save(r);
  expect(()=>j.save({...r,body:{...r.body,quantity:'7'}})).toThrow();
  expect(()=>j.save({...r,code:'F02'})).toThrow();expect(j.list()).toEqual([r]);
  expect(()=>j.clear({...r,body:{...r.body,quantity:'8'}})).toThrow();j.clear(r);expect(j.list()).toEqual([]);
});

test('withdrawal retains the original quantities and expected predecessor without a current profile',()=>{
  const r=pendingParRecord({...submitted,version:1,body:{action:'withdraw',coverage_note:'Withdraw fictional target',verified:true},prior});
  expect(r.profile).toBeNull();expect(r.prior).toEqual(prior);
  expect(()=>pendingParRecord({...submitted,version:2,body:r.body,prior})).toThrow();
});

test.each(['0','0.000000000001','9999999999999999.999999999999'])('exact supported quantity %s is never round-tripped through Number',quantity=>{
  expect(pendingParRecord({...submitted,body:{...submitted.body,quantity}}).body.quantity).toBe(quantity);
});

test.each(['-1','1e400','10000000000000000','1.1234567890123'])('invalid submitted quantity %s is refused',quantity=>{
  expect(()=>pendingParRecord({...submitted,body:{...submitted.body,quantity}})).toThrow();
});

test('failed storage readback and corrupt schema never silently reset a journal',()=>{
  const s=storage(),r=pendingParRecord(submitted),j=pendingParJournal('actor','berts',()=>s);
  s.setItem=()=>{};expect(()=>j.save(r)).toThrow();
  s.map.set('jaymax:pending-pars:v1:actor:berts','{"schema":99}');expect(()=>j.list()).toThrow();
  expect(s.map.size).toBe(1);
});

test.each(['Café item 01','x'.repeat(200)])('retains canonical product code %s without narrowing the catalog contract',code=>{
  const r=pendingParRecord({...submitted,code});expect(r.code).toBe(code);
  const s=storage(),j=pendingParJournal('actor','berts',()=>s);j.save(r);
  expect(()=>pendingParRecord({...submitted,code:'x'.repeat(201)})).toThrow();
  expect(j.list()).toEqual([r]);
});

test('status mismatches, incomplete proof and ineligible revision claims stay held',()=>{
  const r=pendingParRecord(submitted),base={store_id:'berts',item_code:'F01',actor:'actor',request_key:key,expected_revision:0,
    outcome:'retry_available',review:null,current_review:null,message:'Exact retry only'};
  expect(checkedParStatus(base,r,'actor','berts')).toBe(base);
  for(const changed of [{actor:'other'},{store_id:'rudds'},{item_code:'F02'},{request_key:unit},{expected_revision:1},
    {outcome:'unknown'},{outcome:'saved_current'},{outcome:'not_saved_superseded'},{message:''}]){
    expect(()=>checkedParStatus({...base,...changed},r,'actor','berts')).toThrow();
  }
});
