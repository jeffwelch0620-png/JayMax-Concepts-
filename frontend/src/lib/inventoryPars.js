import {useCallback,useEffect,useRef,useState} from 'react';
import * as api from './api';
import {canonicalStoreId} from './purchaseContract';
import {sameOrderDecimal} from './orderIntegrity';

export const parDecimal=value=>typeof value==='string' && /^\+?(?:\d{1,16}(?:\.\d{1,12})?|\.\d{1,12})$/.test(value.trim());
const evidenceDecimal=(value,maximum)=>typeof value==='string' && value.length<=80 && /^\+?(?:\d+(?:\.\d*)?|\.\d+)(?:e[+-]?\d+)?$/i.test(value) && Number.isFinite(Number(value)) && Number(value)>=0 && Number(value)<=maximum && (Number(value)!==0||sameOrderDecimal(value,'0'));
const text=value=>typeof value==='string'&&value.trim().length>0;
function checkedReview(p,rid,code){
  if(!p||p.store_id!==canonicalStoreId(rid)||p.item_code!==code||!['id','source_unit','base_unit','unit_profile_id','actor','recorded_at','coverage_note'].every(key=>text(p[key]))||!Number.isSafeInteger(p.revision)||p.revision<1||typeof p.confirmed!=='boolean'||!evidenceDecimal(p.quantity,1e16)||!evidenceDecimal(p.base_quantity,1e32)||!evidenceDecimal(p.factor,1e16)||Number(p.factor)<=0)throw new Error('Saved par review was not confirmed.');
  return p;
}
export function checkedPars(result,rid){
  if(result?.store_id!==canonicalStoreId(rid)||typeof result.available!=='boolean'||!Array.isArray(result.items))throw new Error('Inventory par read was not confirmed.');
  const seen=new Set();
  for(const row of result.items){
    if(!text(row?.code)||!text(row?.name)||typeof row.legacy_quantity!=='string'||seen.has(row.code)||!['confirmed','unconfirmed','needs_review'].includes(row.status))throw new Error('Inventory par identities or review states need review.');
    seen.add(row.code);
    const p=row.review;
    if(p)checkedReview(p,rid,row.code);
    const unit=row.count_profile;
    if(unit&&(unit.store_id!==result.store_id||unit.item_code!==row.code||unit.profile_kind!=='count'||!['id','source_unit','base_unit'].every(key=>text(unit[key]))||unit.stale||!evidenceDecimal(unit.base_units_per_source_unit,1e16)||Number(unit.base_units_per_source_unit)<=0))throw new Error('Par count unit was not confirmed.');
    if(row.status==='confirmed' && (!result.available||!p?.confirmed||!unit||unit.id!==p.unit_profile_id||unit.source_unit!==p.source_unit||unit.base_unit!==p.base_unit||!sameOrderDecimal(unit.base_units_per_source_unit,p.factor)))throw new Error('Par conversion needs review.');
    if(row.status==='needs_review'&&!p?.confirmed||row.status==='unconfirmed'&&p?.confirmed)throw new Error('Par review status was not confirmed.');
  }
  return result;
}
export function checkedParSave(result,submitted,rid){
  const p=checkedReview(result?.review,rid,submitted.code);
  const unit=submitted.profile;
  if(result?.request_key!==submitted.key||p.revision!==submitted.version+1||p.confirmed!==(submitted.body.action==='confirm')||p.coverage_note!==submitted.body.coverage_note||
    (p.confirmed&&(!unit||p.base_unit!==unit.base_unit||p.source_unit!==unit.source_unit||!sameOrderDecimal(p.factor,unit.base_units_per_source_unit)))||
    (!p.confirmed&&(!submitted.prior||!sameOrderDecimal(p.quantity,submitted.prior.quantity)||!sameOrderDecimal(p.base_quantity,submitted.prior.base_quantity)||p.unit_profile_id!==submitted.prior.unit_profile_id))||
    (p.confirmed&&(!sameOrderDecimal(p.quantity,submitted.body.quantity)||p.unit_profile_id!==submitted.body.unit_profile_id)))throw new Error('Par save was not confirmed. Retain and retry the same request.');
  return p;
}
export function useInventoryPars(rid){
  const [data,setData]=useState(null),[error,setError]=useState(''),[reading,setReading]=useState(false);
  const epoch=useRef(0),sequence=useRef(0);
  const refresh=useCallback(async()=>{
    const id=epoch.current,read=++sequence.current;setReading(true);
    try{
      const result=checkedPars(await api.inventoryPars(rid),rid);
      if(id===epoch.current&&read===sequence.current){setData(result);setError('');return result;}
    }catch(e){if(id===epoch.current&&read===sequence.current){setData(null);setError(typeof e?.response?.data?.detail==='string'?e.response.data.detail:e.message||'Par information unavailable.');}}
    finally{if(id===epoch.current&&read===sequence.current)setReading(false);}
    return null;
  },[rid]);
  useEffect(()=>{const generation=++epoch.current;setData(null);refresh();return()=>{epoch.current=generation+1;};},[refresh]);
  return {data:data?.store_id===canonicalStoreId(rid)?data:null,error,reading,refresh};
}
