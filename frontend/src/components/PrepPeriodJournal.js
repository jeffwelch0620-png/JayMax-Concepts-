import React, { useEffect, useRef, useState } from "react";
import * as api from "../lib/api";
import { Field, cardCls, inpCls, btnAcc, btnGhost } from "./common";
const blank=()=>({opening_count_id:'',closing_count_id:'',opening_cutoff:'',closing_cutoff:'',cutoffs_confirmed:false});
const detail=e=>typeof e?.response?.data?.detail==='string'?e.response.data.detail:e.message||'Saved prep period failed';

function Snapshot({report}) {
  return <div className="space-y-2">
    <p>{report.opening.performed_at} to {report.closing.performed_at}. Coverage remains partial; service use and Toast sales are incomplete. Final expected stock and unexplained variance are unavailable.</p>
    {report.prepared.map(p=><article key={p.product_id} className={cardCls}>
      <p>{p.name} ({p.base_unit}): opening {p.openingQuantity} + recorded production {p.recordedProduction} − closing {p.closingQuantity} = observed depletion {p.observedDepletion}.</p>
      <p>Use in other prep: measured {p.recordedNestedUseMeasured}, estimated {p.recordedNestedUseEstimated}; separate waste {p.recordedWaste}; service use or unrecorded loss {p.serviceUseOrUnrecordedLoss}.</p>
      {!!p.flags.length&&<p role="alert">Recorded activity and counts conflict. Negative quantities are retained for investigation.</p>}
    </article>)}
    {report.rawExplanations.map(r=><p key={r.raw_item_code}>{r.raw_item_code} ({r.base_unit}): measured gross prep input {r.recordedGrossPrepUseMeasured}, estimated {r.recordedGrossPrepUseEstimated}; separate raw waste {r.recordedStandaloneRawWaste}. Included trim {r.annotatedIncludedTrim} is already in gross use.</p>)}
    {report.scopeHandoff.zeroAdditions.map(z=><p key={z.product_id}>Zero addition {z.product_id}: {z.base_quantity} {z.base_unit} at opening. Evidence: {z.evidence}. No stock source is created.</p>)}
    <p>Analytical costs remain uncalculated. Purchased-inventory Food Cost is unchanged.</p>
  </div>;
}

export function PrepPeriodJournal({restaurantId}) {
  const [data,setData]=useState(null),[counts,setCounts]=useState([]),[mode,setMode]=useState('close'),[form,setForm]=useState(blank),[from,setFrom]=useState(''),[reason,setReason]=useState(''),[zeros,setZeros]=useState({});
  const [review,setReview]=useState(null),[approved,setApproved]=useState(false),[busy,setBusy]=useState(false),[error,setError]=useState(''),[message,setMessage]=useState('');
  const pending=useRef(null),alive=useRef(true),location=({papa_leonis:'papa'}[restaurantId]||restaurantId);
  async function load() {
    const [d,c]=await Promise.all([api.nativePrepPeriodJournal(restaurantId),api.nativePrepPeriodCounts(restaurantId)]);
    if(d.store_id!==location||c.store_id!==location)throw new Error('Saved period location was not confirmed.');
    if(alive.current){setData(d);setCounts(c.counts);}
  }
  useEffect(()=>{let active=true;alive.current=true;
    Promise.all([api.nativePrepPeriodJournal(restaurantId),api.nativePrepPeriodCounts(restaurantId)]).then(([d,c])=>{
      if(!active)return;if(d.store_id!==location||c.store_id!==location)throw new Error('Saved period location was not confirmed.');setData(d);setCounts(c.counts);
    }).catch(e=>active&&setError(detail(e)));return()=>{active=false;alive.current=false;};
  },[restaurantId,location]);
  const frozen=busy||!!pending.current;
  const opening=counts.find(c=>c.id===form.opening_count_id),closing=counts.find(c=>c.id===form.closing_count_id);
  const additions=(closing?.scope||[]).filter(id=>!(opening?.scope||[]).includes(id));
  const current=data?.closures.filter(c=>c.freshness.status!=='reopened')||[];
  function edit(fn){fn();setReview(null);setApproved(false);setError('');setMessage('');}
  function boundary(patch){edit(()=>{setForm(f=>({...f,cutoffs_confirmed:false,...patch}));setZeros({});});}
  async function refresh(){if(pending.current)return;setBusy(true);setError('');setReview(null);setApproved(false);try{await load();if(alive.current){setForm(blank());setZeros({});setFrom('');}}catch(e){if(alive.current)setError(detail(e));}finally{if(alive.current)setBusy(false);}}
  async function preview(){
    if(!reason.trim()||(mode==='close'?(!form.opening_count_id||!form.closing_count_id||form.opening_count_id===form.closing_count_id||!form.opening_cutoff||!form.closing_cutoff||!form.cutoffs_confirmed||additions.some(id=>!zeros[id]?.confirmed||!zeros[id]?.evidence?.trim())):!from)){
      setError('Select boundaries and confirm their timing and added zeros, or choose a saved period to reopen. Add a review reason.');return;
    }
    setBusy(true);setError('');setReview(null);setApproved(false);
    const submission=mode==='close'?{period:form,zero_additions:additions.map(id=>({product_id:id,zero_at_opening_confirmed:true,evidence:zeros[id].evidence})),reason}:{from_closure_id:from,reason};
    try{const d=await (mode==='close'?api.previewNativePrepPeriodClose:api.previewNativePrepPeriodReopen)(restaurantId,submission);
      if(d.review?.store_id!==location||!d.reviewHash)throw new Error('Reviewed period location was not confirmed.');
      if(alive.current)setReview({...d,submission,mode});
    }catch(e){if(alive.current)setError(detail(e));}finally{if(alive.current)setBusy(false);}
  }
  async function save(){
    if(!pending.current&&(!review||!approved))return;setBusy(true);setError('');
    try{if(!pending.current)pending.current={key:crypto.randomUUID(),mode:review.mode,body:{submission:review.submission,expected_review_hash:review.reviewHash,reviewed:true}};
      const p=pending.current;const r=await (p.mode==='close'?api.saveNativePrepPeriodClose:api.saveNativePrepPeriodReopen)(restaurantId,p.body,p.key);
      if(!r.event?.id||r.event.store_id!==location||r.event.review_hash!==p.body.expected_review_hash||(p.mode==='close'&&r.event.closing_count_id!==p.body.submission.period.closing_count_id)||(p.mode==='reopen'&&r.event.closure_ids?.[0]!==p.body.submission.from_closure_id))throw new Error('Saved analytical period was not confirmed. Retry the same request.');
      if(!alive.current)return;pending.current=null;setReview(null);setApproved(false);setForm(blank());setZeros({});setFrom('');setReason('');setMessage(p.mode==='close'?'Analytical snapshot saved. Coverage remains partial.':'Analytical periods reopened; original snapshots retained.');
      try{await load();}catch(e){if(alive.current)setError(`Saved; refresh failed: ${detail(e)}`);}
    }catch(e){if(alive.current){setError(detail(e));if([409,422].includes(e?.response?.status)){pending.current=null;setReview(null);setApproved(false);}}}finally{if(alive.current)setBusy(false);}
  }
  return <section aria-label="Saved prep analytical periods" className={`${cardCls} space-y-4`}>
    <h2 className="text-lg font-semibold">Saved prep analytical periods</h2>
    <p>Retain reviewed count comparisons. Adjacent periods must share the same count and cutoff. Source changes flag saved results for reopening; original snapshots remain available.</p>
    <p>Only new items verified as zero at the opening boundary can join a changed scope. Existing quantities carry through unchanged. Nonzero opening additions and removals require further reconciliation.</p>
    {error&&<p role="alert">{error}</p>}{message&&<p role="status">{message}</p>}
    <button className={btnGhost} disabled={frozen} onClick={refresh}>Refresh saved prep periods</button>
    {data&&<>
      <fieldset disabled={frozen} className="space-y-3">
        <Field label="Saved period action"><select aria-label="Saved period action" className={inpCls} value={mode} onChange={e=>edit(()=>{setMode(e.target.value);setForm(blank());setZeros({});setFrom('');})}><option value="close">Save analytical snapshot</option><option value="reopen">Reopen affected and following periods</option></select></Field>
        {mode==='close'?<>
          {['opening','closing'].map(key=><div key={key}>
            <Field label={`${key} saved-period count`}><select aria-label={`${key} saved-period count`} className={inpCls} value={form[`${key}_count_id`]} onChange={e=>boundary({[`${key}_count_id`]:e.target.value})}><option value="">Choose physical prep count</option>{counts.map(c=><option key={c.id} value={c.id}>{c.performed_at} · revision {c.revision}</option>)}</select></Field>
            <Field label={`${key} saved-period cutoff`}><select aria-label={`${key} saved-period cutoff`} className={inpCls} value={form[`${key}_cutoff`]} onChange={e=>boundary({[`${key}_cutoff`]:e.target.value})}><option value="">Choose timing</option><option value="before_all">Before all activity at this instant</option><option value="after_all">After all activity at this instant</option></select></Field>
          </div>)}
          <label><input aria-label="Confirm saved period cutoffs" type="checkbox" checked={form.cutoffs_confirmed} onChange={e=>edit(()=>setForm(f=>({...f,cutoffs_confirmed:e.target.checked})))}/> I confirmed both count cutoffs</label>
          {opening&&closing&&additions.map(id=><div key={id} className={cardCls}>
            <p>Added item: {closing.definitions?.find(d=>d.product.product_id===id)?.product.name||id}</p>
            <label><input aria-label={`Confirm added zero ${id}`} type="checkbox" checked={zeros[id]?.confirmed||false} onChange={e=>edit(()=>setZeros(z=>({...z,[id]:{...z[id],confirmed:e.target.checked}})))}/> This item was measured zero at the opening boundary</label>
            <input aria-label={`Added zero evidence ${id}`} className={inpCls} placeholder="Evidence for zero at opening" value={zeros[id]?.evidence||''} onChange={e=>edit(()=>setZeros(z=>({...z,[id]:{...z[id],evidence:e.target.value}})))}/>
          </div>)}
        </>:<Field label="Earliest affected saved period"><select aria-label="Earliest affected saved period" className={inpCls} value={from} onChange={e=>edit(()=>setFrom(e.target.value))}><option value="">Choose active period</option>{current.map(c=><option key={c.id} value={c.id}>Period {c.ordinal} · {c.freshness.status}</option>)}</select></Field>}
        <Field label="Analytical period review reason"><input aria-label="Analytical period review reason" className={inpCls} value={reason} onChange={e=>edit(()=>setReason(e.target.value))}/></Field>
        <button className={btnAcc} onClick={preview}>Review analytical period action</button>
      </fieldset>
      {review&&<div aria-label="Analytical period action review" className={`${cardCls} space-y-2`}>
        {review.mode==='close'?<Snapshot report={review.review.report}/>:<><p>Reopen these periods and preserve their original results:</p><ul>{review.review.snapshots.map(s=><li key={s.id}>{s.id} · {s.freshness.status} · {s.freshness.reason}</li>)}</ul></>}
        <label><input aria-label="Approve analytical period action" type="checkbox" disabled={frozen} checked={approved} onChange={e=>setApproved(e.target.checked)}/> I reviewed the quantities, scope and incomplete coverage, or the full reopening list</label>
        <button className={btnAcc} disabled={busy||(!approved&&!pending.current)} onClick={save}>{pending.current?'Retry same analytical period action':'Save reviewed analytical period action'}</button>
      </div>}
      <h3 className="font-semibold">Saved snapshot history</h3>
      {data.closures.length===0&&<p>No analytical periods saved.</p>}
      {data.closures.map(c=><details key={c.id} className={cardCls}><summary>Period {c.ordinal} · {c.freshness.status} · {c.reason}</summary>{c.chain_status==='requires_reopening'&&<p role="alert">This period is affected by changed evidence in its chain. Reopen it together with the earliest affected period and all following periods.</p>}<p>{c.freshness.reason} · Saved by {c.recorded_by} at {c.recorded_at}</p><Snapshot report={c.review_snapshot.report}/></details>)}
      {data.reopenings.map(r=><p key={r.id}>Reopened {r.closure_ids.length} periods: {r.reason} · {r.recorded_by} · {r.recorded_at}</p>)}
    </>}
  </section>;
}
