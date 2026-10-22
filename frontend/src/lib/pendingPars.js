// This tab's submitted par requests only. Never credentials or authority to save.
import {canonicalStoreId} from './purchaseContract';
import {sameOrderDecimal} from './orderIntegrity';
import {checkedParSave,checkedParReview,parDecimal} from './inventoryPars';

const id=v=>typeof v==='string'&&/^[A-Za-z0-9_.-]{1,160}$/.test(v);
const productCode=v=>typeof v==='string'&&v.trim().length>0&&v.length<=200;
const uuid=v=>typeof v==='string'&&/^[a-f0-9]{8}(-[a-f0-9]{4}){3}-[a-f0-9]{12}$/i.test(v);
const exact=(v,keys)=>v&&typeof v==='object'&&!Array.isArray(v)&&Object.keys(v).length===keys.length&&keys.every(k=>Object.hasOwn(v,k));
const text=v=>typeof v==='string'&&v.trim().length>0&&v.length<=160;
const decimal=v=>typeof v==='string'&&v.length<=80&&/^\+?(?:\d+(?:\.\d*)?|\.\d+)(?:e[+-]?\d+)?$/i.test(v)&&Number.isFinite(Number(v))&&Number(v)>=0&&(Number(v)!==0||sameOrderDecimal(v,'0'));
const failure=()=>new Error('Par recovery is unavailable or invalid. Keep this tab open; no new par review will be sent.');
const stable=v=>JSON.stringify(sort(v));
function sort(v){return Array.isArray(v)?v.map(sort):v&&typeof v==='object'?Object.fromEntries(Object.keys(v).sort().map(k=>[k,sort(v[k])])):v;}
const profileKeys=['id','source_unit','base_unit','base_units_per_source_unit'];
const priorKeys=['id','revision','quantity','base_quantity','unit_profile_id','factor','source_unit','base_unit'];
const take=(v,keys)=>v?Object.fromEntries(keys.map(k=>[k,v[k]])):null;

function valid(r){
  if(!exact(r,['key','code','version','body','profile','prior'])||!uuid(r.key)||!productCode(r.code)||!Number.isSafeInteger(r.version)||r.version<0||r.version>=2147483647)throw failure();
  const b=r.body;
  if(!b||!['confirm','withdraw'].includes(b.action)||b.verified!==true||typeof b.coverage_note!=='string'||!b.coverage_note.trim()||b.coverage_note.length>2000)throw failure();
  if(b.action==='confirm'){
    if(!exact(b,['action','quantity','unit_profile_id','coverage_note','verified'])||!parDecimal(b.quantity)||!uuid(b.unit_profile_id)
      ||!exact(r.profile,profileKeys)||r.profile.id!==b.unit_profile_id||!profileKeys.every(k=>text(r.profile[k]))||!decimal(r.profile.base_units_per_source_unit)||Number(r.profile.base_units_per_source_unit)<=0||r.prior!==null)throw failure();
  }else if(!exact(b,['action','coverage_note','verified'])||r.profile!==null||!exact(r.prior,priorKeys)||!uuid(r.prior.id)||r.version<1||r.prior.revision!==r.version
    ||!uuid(r.prior.unit_profile_id)||!decimal(r.prior.quantity)||!decimal(r.prior.base_quantity)||!decimal(r.prior.factor)||Number(r.prior.factor)<=0||!text(r.prior.source_unit)||!text(r.prior.base_unit))throw failure();
  return r;
}

export function pendingParRecord(submitted){
  const body=submitted.body;
  return valid(JSON.parse(JSON.stringify({key:submitted.key,code:submitted.code,version:submitted.version,body,
    profile:body.action==='confirm'?take(submitted.profile,profileKeys):null,
    prior:body.action==='withdraw'?take(submitted.prior,priorKeys):null})));
}

export function pendingParJournal(actorId,rid,storage=()=>window.sessionStorage){
  rid=canonicalStoreId(rid);
  const key=`jaymax:pending-pars:v1:${actorId}:${rid}`;
  function read(){
    try{
      if(!id(actorId)||!id(rid))throw failure();
      const raw=storage().getItem(key);
      if(raw===null)return [];
      if(new Blob([raw]).size>128*1024)throw failure();
      const v=JSON.parse(raw);
      if(!exact(v,['schema','actorId','restaurantId','records'])||v.schema!==1||v.actorId!==actorId||v.restaurantId!==rid||!Array.isArray(v.records)||v.records.length>32
        ||new Set(v.records.map(r=>r?.code)).size!==v.records.length||new Set(v.records.map(r=>r?.key)).size!==v.records.length)throw failure();
      return v.records.map(valid);
    }catch{throw failure();}
  }
  function write(records){
    const raw=JSON.stringify({schema:1,actorId,restaurantId:rid,records});
    if(records.length>32||new Blob([raw]).size>128*1024)throw failure();
    try{storage().setItem(key,raw);if(storage().getItem(key)!==raw)throw failure();}catch{throw failure();}
  }
  return {list:read,save(record){
    valid(record);const records=read(),old=records.find(r=>r.code===record.code);
    if(old){if(stable(old)!==stable(record))throw failure();return old;}
    if(records.some(r=>r.key===record.key))throw failure();
    write([...records,record]);return record;
  },current(record){
    valid(record);const found=read().find(r=>r.key===record.key);
    if(!found||stable(found)!==stable(record))throw failure();return found;
  },clear(record){
    const records=read(),found=records.find(r=>r.key===record.key);
    if(!found||stable(found)!==stable(record))throw failure();write(records.filter(r=>r.key!==record.key));
  }};
}

export function checkedParStatus(result,record,actorId,rid){
  valid(record);
  if(!result||result.store_id!==canonicalStoreId(rid)||result.item_code!==record.code||result.actor!==actorId||result.request_key!==record.key||result.expected_revision!==record.version
    ||!['saved_current','saved_superseded','retry_available','not_saved_superseded','held'].includes(result.outcome))throw failure();
  const current=result.current_review;
  if(current)checkedParReview(current,rid,record.code);
  if(result.outcome.startsWith('saved_')){
    const saved=checkedParSave(result,record,rid);
    if(saved.actor!==actorId||saved.request_key!==record.key||!current||current.revision<saved.revision||(result.outcome==='saved_current'?stable(current)!==stable(saved):(current.id===saved.id||current.revision<=saved.revision)))throw failure();
  }else{
    if(result.review!==null||typeof result.message!=='string'||!result.message.trim())throw failure();
    if(result.outcome==='retry_available'&&(current?.revision||0)!==record.version)throw failure();
    if(result.outcome==='not_saved_superseded'&&(!current||current.revision<=record.version))throw failure();
  }
  return result;
}
