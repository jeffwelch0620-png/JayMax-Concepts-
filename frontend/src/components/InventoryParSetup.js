import React,{useEffect,useRef,useState} from 'react';
import * as api from '../lib/api';
import {useInventoryPars,parDecimal,checkedParSave} from '../lib/inventoryPars';
import {useRetainedDraft} from '../lib/saveIntegrity';
import {cardCls,inpCls,btnGhost} from './common';

export function InventoryParReference({row,legacy}){
  const p=row?.review;
  return <div data-testid={`par-reference-${row?.code||'unconfirmed'}`}>
    {p?<><span>{p.quantity} {p.source_unit} = {p.base_quantity} {p.base_unit}</span><br/>
      <span className={row.status==='confirmed'?'text-slate-300':'text-amber-300'}>{row.status==='confirmed'?'Confirmed target':row.status==='needs_review'?'Needs review: count conversion changed':'Unconfirmed: review withdrawn'}</span>
      <div className="text-xs">{p.coverage_note} · Reviewed by {p.actor} · {p.recorded_at}</div></>:
      <span className="text-amber-300">Unconfirmed legacy value: {row?.legacy_quantity??legacy??'not set'}; unit not established</span>}
  </div>;
}
const blank={code:'',quantity:'',unit_profile_id:'',coverage_note:'',version:0,verified:false,pending:null};
export function InventoryParSetup(props){return <ParForm key={props.rid} {...props}/>;}
function ParForm({rid,drafts,onSaved,showToast=()=>{}}){
  const {data,error,reading,refresh}=useInventoryPars(rid);
  const [draft,setDraft]=useRetainedDraft(`inventory-par:${rid}`,blank,drafts);
  const [busy,setBusy]=useState(false),[failure,setFailure]=useState('');
  const mounted=useRef(false);
  useEffect(()=>{mounted.current=true;return()=>{mounted.current=false;};},[]);
  const row=data?.items.find(r=>r.code===draft.code),profile=row?.count_profile;
  const frozen=busy||!!draft.pending;
  function change(key,value){setDraft(p=>({...p,[key]:value,verified:false}));}
  async function reviewLatest(){
    const current=await refresh();
    if(!current||!mounted.current)return;
    setDraft(p=>({...p,version:current.items.find(r=>r.code===p.code)?.review?.revision||0,verified:false}));
    setFailure('Compare your retained quantity and unit with the latest review, then confirm again.');
  }
  async function save(action){
    if(busy||reading)return;
    let submitted=draft.pending;
    if(!submitted){
      if(!row||!data.available||!draft.verified||!draft.coverage_note.trim()){setFailure('Choose a product, describe its coverage period and explicitly confirm the review.');return;}
      if(action==='confirm'&&(!profile||profile.id!==draft.unit_profile_id||!parDecimal(draft.quantity))){setFailure('Enter a nonnegative exact quantity and select the current verified count unit.');return;}
      const body=action==='withdraw'?{action,coverage_note:draft.coverage_note.trim(),verified:true}:
        {action,quantity:draft.quantity.trim(),unit_profile_id:draft.unit_profile_id,coverage_note:draft.coverage_note.trim(),verified:true};
      submitted={key:window.crypto.randomUUID(),code:draft.code,version:draft.version,body,profile,prior:row.review};
      setDraft(p=>({...p,pending:submitted}));
    }
    setBusy(true);setFailure('');
    try{
      checkedParSave(await api.reviewInventoryPar(rid,submitted.code,submitted.body,submitted.version,submitted.key),submitted,rid);
      if(!mounted.current)return;
      setDraft(p=>({...p,pending:null,version:submitted.version+1,verified:false}));
      showToast('Par review saved; order quantities remain manual.');
      await refresh();
      if(mounted.current){
        try{await onSaved?.();}
        catch(e){if(mounted.current)setFailure('Par saved, but the catalog refresh failed. Reload the location before another item edit.');}
      }
    }catch(e){
      if(!mounted.current)return;
      if(e?.response?.status>=400&&e.response.status<500)setDraft(p=>({...p,pending:null,verified:false}));
      setFailure(typeof e?.response?.data?.detail==='string'?e.response.data.detail:e.message||'Par save outcome is uncertain; retry the same review.');
    }finally{if(mounted.current)setBusy(false);}
  }
  return <section className={`${cardCls} p-4 space-y-3`} data-testid="inventory-par-setup">
    <h3>Purchased inventory targets (pars)</h3>
    <p>Set a location stock target in a verified stocking/count unit. Its fixed physical quantity is retained independently of supplier pack sizes. This does not record stock, change Food Cost or generate an order.</p>
    <button type="button" className={btnGhost} disabled={frozen||reading} onClick={reviewLatest}>Reload latest par review</button>
    {(error||failure)&&<p role="alert">{failure||error}</p>}
    {!data?<p>Par review unavailable until a confirmed read.</p>:!data.available?<p>Reviewed par storage is awaiting installation. Existing numbers have unconfirmed units. Manual ordering remains available.</p>:<>
      <fieldset disabled={frozen||reading} className="space-y-2">
        <label>Purchased product<select aria-label="Par product" className={inpCls} value={draft.code} onChange={e=>{
          const next=data.items.find(r=>r.code===e.target.value);setDraft({...blank,code:e.target.value,version:next?.review?.revision||0});setFailure('');
        }}><option value="">Choose a purchased product</option>{data.items.map(r=><option key={r.code} value={r.code}>{r.name} ({r.code})</option>)}</select></label>
        {row&&<InventoryParReference row={row}/>}
        <label>Par quantity<input aria-label="Par quantity" className={inpCls} inputMode="decimal" value={draft.quantity} onChange={e=>change('quantity',e.target.value)}/></label>
        <label>Par stocking unit<select aria-label="Par stocking unit" className={inpCls} value={draft.unit_profile_id} onChange={e=>change('unit_profile_id',e.target.value)}><option value="">Choose a verified count unit</option>{profile&&<option value={profile.id}>{profile.source_unit} ({profile.base_units_per_source_unit} {profile.base_unit})</option>}</select></label>
        {row&&!profile&&<p>Confirm this item's physical count conversion in Invoice Master → Verified inventory units first. Catalog pack text is not a verified conversion.</p>}
        <label>Coverage period and review reason<textarea aria-label="Par coverage note" className={inpCls} value={draft.coverage_note} onChange={e=>change('coverage_note',e.target.value)}/></label>
        <label><input aria-label="Confirm par review" type="checkbox" checked={draft.verified} onChange={e=>setDraft(p=>({...p,verified:e.target.checked}))}/> I reviewed this stock target, unit and coverage period. Zero is an explicit target.</label>
      </fieldset>
      <button type="button" className={btnGhost} disabled={frozen||reading||!row||!profile||!draft.verified} onClick={()=>save('confirm')}>Confirm inventory par</button>
      {row?.review?.confirmed&&<button type="button" className={btnGhost} disabled={frozen||reading||!draft.verified} onClick={()=>save('withdraw')}>Withdraw par confirmation</button>}
    </>}
    {draft.pending&&<><p>Save outcome is uncertain. Entries are held; retry the original review before starting another.</p><button type="button" className={btnGhost} disabled={busy||reading} onClick={()=>save()}>Retry same par review</button></>}
  </section>;
}
