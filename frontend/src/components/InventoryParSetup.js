import React,{useEffect,useMemo,useRef,useState} from 'react';
import * as api from '../lib/api';
import {useInventoryPars,parDecimal,checkedParSave} from '../lib/inventoryPars';
import {useRetainedDraft} from '../lib/saveIntegrity';
import {pendingParJournal,pendingParRecord,checkedParStatus} from '../lib/pendingPars';
import {canonicalStoreId} from '../lib/purchaseContract';
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
const blank={code:'',quantity:'',unit_profile_id:'',coverage_note:'',version:0,verified:false};
const discardable=['held','retry_available','not_saved_superseded'];
export function InventoryParSetup(props){return <ParForm key={`${props.actorId}:${canonicalStoreId(props.rid)}`} {...props}/>;}
function ParForm({rid,actorId,drafts,onSaved,showToast=()=>{}}){
  const {data,error,reading,refresh}=useInventoryPars(rid);
  const [draft,setDraft]=useRetainedDraft(`inventory-par:${actorId}:${rid}`,blank,drafts);
  const journal=useMemo(()=>pendingParJournal(actorId,rid),[actorId,rid]);
  const initial=useMemo(()=>{try{return {records:journal.list(),error:''};}catch(e){return {records:[],error:e.message};}},[journal]);
  const [records,setRecords]=useState(initial.records),[unavailable,setUnavailable]=useState(!!initial.error);
  const [checks,setChecks]=useState({}),[busy,setBusy]=useState(false),[failure,setFailure]=useState(initial.error);
  const [discard,setDiscard]=useState(null);
  const [discardNotice,setDiscardNotice]=useState('');
  const scope=useMemo(()=>({active:true,actorId,rid}),[actorId,rid]);
  const sending=useRef(false);
  useEffect(()=>{scope.active=true;return()=>{scope.active=false;};},[scope]);
  const row=data?.items.find(r=>r.code===draft.code),profile=row?.count_profile;
  const frozen=busy||records.length>0||unavailable||!!discard;
  function loadRecords(){
    try{const next=journal.list();if(scope.active){setRecords(next);setUnavailable(false);}return next;}
    catch(e){if(scope.active){setUnavailable(true);setFailure(e.message);}throw e;}
  }
  function retained(record){
    if(!scope.active)throw new Error('The signed-in user or location changed.');
    try{return journal.current(record);}catch(e){setUnavailable(true);throw e;}
  }
  async function run(action){
    if(sending.current||!scope.active)return;
    sending.current=true;setBusy(true);setFailure('');
    try{await action();}catch(e){if(scope.active)setFailure(typeof e?.response?.data?.detail==='string'?e.response.data.detail:e.message||'Par outcome is uncertain. Keep the retained request.');}
    finally{sending.current=false;if(scope.active)setBusy(false);}
  }
  function change(key,value){setDraft(p=>({...p,[key]:value,verified:false}));}
  async function reviewLatest(){
    await run(async()=>{
      if(loadRecords().length)return;
      const current=await refresh();if(!current||!scope.active)return;
      setDraft(p=>({...p,version:current.items.find(r=>r.code===p.code)?.review?.revision||0,verified:false}));
      setFailure('Compare your retained quantity and unit with the latest review, then confirm again.');
    });
  }
  async function resolved(record,result){
    retained(record);
    // Verified saves are not retried because local cleanup or reference reads fail.
    try{journal.clear(record);loadRecords();}
    catch(e){setUnavailable(true);setFailure('Par saved, but retained-request cleanup failed. Keep this tab open; do not submit another review.');return;}
    setChecks(p=>({...p,[record.key]:null}));
    setDraft(p=>p.code===record.code?{...p,version:result.current_review.revision,verified:false}:p);
    showToast(result.outcome==='saved_superseded'?'Your par review was saved; a later review is now current.':'Par review saved; order quantities remain manual.');
    const current=await refresh();if(!scope.active)return;
    if(!current)setFailure('Par saved, but its reference refresh failed. Reload the location before another item edit.');
    try{await onSaved?.();}catch(e){if(scope.active)setFailure('Par saved, but the catalog refresh failed. Reload the location before another item edit.');}
  }
  async function inspect(record){
    retained(record);setChecks(p=>({...p,[record.key]:null}));
    const result=await api.checkInventoryParStatus(rid,record.code,record.body,record.version,record.key);
    if(!scope.active)return null;
    retained(record);
    const checked=checkedParStatus(result,record,actorId,rid);
    setChecks(p=>({...p,[record.key]:checked}));return checked;
  }
  async function send(record){
    retained(record);
    const result=await api.reviewInventoryPar(rid,record.code,record.body,record.version,record.key);
    if(!scope.active)return;
    retained(record);checkedParSave(result,record,rid);
    const checked=checkedParStatus({...result,store_id:canonicalStoreId(rid),item_code:record.code,actor:actorId,expected_revision:record.version,
      outcome:result.current_review?.id===result.review?.id?'saved_current':'saved_superseded'},record,actorId,rid);
    await resolved(record,checked);
  }
  async function save(action){
    await run(async()=>{
      if(reading||loadRecords().length)return;
      if(!row||!data.available||!draft.verified||!draft.coverage_note.trim())throw new Error('Choose a product, describe its coverage period and explicitly confirm the review.');
      if(action==='confirm'&&(!profile||profile.id!==draft.unit_profile_id||!parDecimal(draft.quantity)))throw new Error('Enter a nonnegative exact quantity and select the current verified count unit.');
      const body=action==='withdraw'?{action,coverage_note:draft.coverage_note.trim(),verified:true}:
        {action,quantity:draft.quantity.trim(),unit_profile_id:draft.unit_profile_id,coverage_note:draft.coverage_note.trim(),verified:true};
      const record=pendingParRecord({key:window.crypto.randomUUID(),code:draft.code,version:draft.version,body,profile,prior:row.review});
      // Persist and read back before the first network write.
      try{journal.save(record);loadRecords();}catch(e){setUnavailable(true);throw e;}
      await send(record);
    });
  }
  async function check(record){await run(async()=>{const result=await inspect(record);if(result?.outcome.startsWith('saved_'))await resolved(record,result);});}
  async function retry(record){
    await run(async()=>{
      if(checks[record.key]?.outcome!=='retry_available')return;
      const latest=await inspect(record);
      if(latest?.outcome.startsWith('saved_'))await resolved(record,latest);
      else if(latest?.outcome==='retry_available')await send(record);
    });
  }
  async function reviewSuperseded(record){
    await run(async()=>{
      const latest=await inspect(record);if(!latest)return;
      if(latest.outcome.startsWith('saved_')){await resolved(record,latest);return;}
      if(latest.outcome!=='not_saved_superseded')return;
      const current=await refresh();if(!current||!scope.active)return;
      const item=current.items.find(r=>r.code===record.code);
      if(!item?.review||item.review.revision<latest.current_review.revision)throw new Error('Current par values were not confirmed. Keep the retained request.');
      retained(record);
      try{journal.clear(record);loadRecords();}catch(e){setUnavailable(true);throw e;}
      setChecks(p=>({...p,[record.key]:null}));
      setDraft({...blank,code:record.code,quantity:record.body.quantity??record.prior.quantity,
        unit_profile_id:record.body.unit_profile_id??record.prior.unit_profile_id,coverage_note:record.body.coverage_note,version:item.review.revision});
      setFailure('Another review advanced this product. Compare these retained values with the current review and confirm again.');
    });
  }
  async function discardRetained(){
    await run(async()=>{
      if(!discard)return;
      const latest=await inspect(discard);if(!latest)return;
      if(latest.outcome.startsWith('saved_')){setDiscard(null);await resolved(discard,latest);return;}
      if(!discardable.includes(latest.outcome))return;
      // A negative read does not cancel an in-flight write. Read current values
      // before removing only local recovery evidence; never create a new command.
      const current=await refresh();if(!scope.active)return;
      if(!current)throw new Error('Current par values could not be refreshed. The retained request has not been discarded.');
      retained(discard);
      try{journal.clear(discard);loadRecords();}catch(e){setUnavailable(true);throw e;}
      setChecks(p=>({...p,[discard.key]:null}));
      setDraft(p=>p.code===discard.code?{...blank}:{...p,version:current.items.find(r=>r.code===p.code)?.review?.revision||0,verified:false});
      setDiscard(null);
      setDiscardNotice('Recovery record removed from this tab only. The earlier request was not cancelled and may still complete. Review the current par before entering and confirming a new review.');
    });
  }
  return <section className={`${cardCls} p-4 space-y-3`} data-testid="inventory-par-setup">
    <h3>Purchased inventory targets (pars)</h3>
    <p>Set a location stock target in a verified stocking/count unit. Its fixed physical quantity is retained independently of supplier pack sizes. This does not record stock, change Food Cost or generate an order.</p>
    <button type="button" className={btnGhost} disabled={frozen||reading} onClick={reviewLatest}>Reload latest par review</button>
    {(error||failure)&&<p role="alert">{failure||error}</p>}
    {discardNotice&&<p role="status">{discardNotice}</p>}
    {unavailable&&<button type="button" disabled={busy} onClick={()=>run(async()=>{loadRecords();})}>Read retained par requests again</button>}
    {records.map(record=><section key={record.key} aria-label={`Retained par review ${record.code}`} className="border p-3">
      <p>Retained {record.body.action} review for {record.code}. {record.body.quantity??record.prior?.quantity} {record.profile?.source_unit||'in the previously reviewed unit'}. {record.body.coverage_note}</p>
      <p>Check the saved outcome before retrying. Closing this view does not cancel an earlier request. Recovery is limited to this tab and this account.</p>
      {checks[record.key]&&<p role="status">{checks[record.key].message||checks[record.key].outcome.replaceAll('_',' ')}</p>}
      <button type="button" disabled={busy||unavailable||!!discard} onClick={()=>check(record)}>Check saved par status</button>
      <button type="button" disabled={busy||unavailable||!!discard||checks[record.key]?.outcome!=='retry_available'} onClick={()=>retry(record)}>Retry same par review</button>
      {checks[record.key]?.outcome==='not_saved_superseded'&&<button type="button" disabled={busy||unavailable||!!discard} onClick={()=>reviewSuperseded(record)}>Review current par and retained values</button>}
      {discardable.includes(checks[record.key]?.outcome)&&<button type="button" disabled={busy||unavailable||!!discard} onClick={()=>setDiscard(record)}>Discard this tab's retained par request</button>}
    </section>)}
    {discard&&<section role="dialog" aria-modal="true" aria-label="Confirm retained par request discard" className="border p-3">
      <p>Remove this tab's recovery record for {discard.code}?</p>
      <p>Action: {discard.body.action}. Quantity: {discard.body.quantity??discard.prior.quantity} {discard.profile?.source_unit??discard.prior.source_unit}. Physical quantity: {discard.body.action==='withdraw'?`${discard.prior.base_quantity} ${discard.prior.base_unit}`:`conversion ${discard.profile.base_units_per_source_unit} ${discard.profile.base_unit} per ${discard.profile.source_unit}`}.</p>
      <p>Review note: {discard.body.coverage_note}</p>
      <p>This removes only this tab's recovery record. It does not delete saved par history or cancel the original request. An earlier attempt may still complete; check the current par before entering a new review. Confirmation checks status again and refreshes current values. A saved request is resolved as saved.</p>
      <button type="button" disabled={busy} onClick={()=>setDiscard(null)}>Keep retained par request</button>
      <button type="button" disabled={busy||unavailable} onClick={discardRetained}>Confirm discard retained par request</button>
    </section>}
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

  </section>;
}
