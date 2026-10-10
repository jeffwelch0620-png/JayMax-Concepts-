import React, { useEffect, useRef, useState } from "react";
import * as api from "../lib/api";
import { Field, cardCls, inpCls, btnAcc, btnGhost } from "./common";
const detail=e=>typeof e?.response?.data?.detail==='string'?e.response.data.detail:e.message||'Opening source failed';

export function PrepOpeningStock({ restaurantId }) {
  const [data,setData]=useState(null),[mode,setMode]=useState('initial'),[count,setCount]=useState(''),[decision,setDecision]=useState(''),[note,setNote]=useState(''),[before,setBefore]=useState(false);
  const [review,setReview]=useState(null),[approved,setApproved]=useState(false),[busy,setBusy]=useState(false),[error,setError]=useState(''),[message,setMessage]=useState('');
  const pending=useRef(null),alive=useRef(true);
  useEffect(()=>{let active=true;alive.current=true;api.nativePrepOpeningSetup(restaurantId).then(d=>active&&setData(d)).catch(e=>active&&setError(detail(e)));return()=>{active=false;alive.current=false;};},[restaurantId]);
  const frozen=busy||!!pending.current;
  const current=data?.decisions.filter(d=>d.kind==='initial'&&!data.decisions.some(n=>n.predecessor_id===d.id))||[];
  function edit(fn){fn();setReview(null);setApproved(false);setMessage('');setError('');}
  async function refresh(){if(pending.current)return;setBusy(true);setError('');setReview(null);setApproved(false);try{const d=await api.nativePrepOpeningSetup(restaurantId);if(alive.current){setData(d);setCount('');setDecision('');setBefore(false);}}catch(e){if(alive.current)setError(detail(e));}finally{if(alive.current)setBusy(false);}}
  async function preview(){
    if(!note.trim()||(mode==='initial'?(!count||!before):!decision)){setError('Select the count or opening decision and add evidence; new opening stock requires confirmation that activity has not begun.');return;}
    setBusy(true);setReview(null);setApproved(false);setError('');
    try{const payload=mode==='initial'?{count_id:count,before_activity_confirmed:before,note}:{reason:note};
      const d=mode==='initial'?await api.previewNativePrepOpening(restaurantId,payload):await api.previewNativePrepOpeningVoid(restaurantId,decision,payload);
      if(alive.current)setReview({...d,payload,mode,decision});
    }catch(e){if(alive.current)setError(detail(e));}finally{if(alive.current)setBusy(false);}
  }
  async function save(){
    if(!pending.current&&(!review||!approved))return;setBusy(true);setError('');
    try{if(!pending.current)pending.current={key:crypto.randomUUID(),mode:review.mode,decision:review.decision,body:{[review.mode==='initial'?'opening':'change']:review.payload,expected_review_hash:review.reviewHash,reviewed:true}};
      const p=pending.current;const r=p.mode==='initial'?await api.saveNativePrepOpening(restaurantId,p.body,p.key):await api.voidNativePrepOpening(restaurantId,p.decision,p.body,p.key);
      if(!r.event?.id||r.event.store_id!==({papa_leonis:'papa'}[restaurantId]||restaurantId)||r.event.kind!==(p.mode==='initial'?'initial':'void')||r.event.review_hash!==p.body.expected_review_hash||(r.event.predecessor_id||null)!==(p.mode==='initial'?null:p.decision))throw new Error('Opening decision was not confirmed. Retry the same record.');
      if(!alive.current)return;pending.current=null;setReview(null);setApproved(false);setCount('');setDecision('');setBefore(false);setNote('');setMode('initial');setMessage('Opening decision saved. No production or Food Cost was added.');
      try{const d=await api.nativePrepOpeningSetup(restaurantId);if(alive.current)setData(d);}catch(e){if(alive.current)setError(`Decision saved; refresh failed: ${detail(e)}`);}
    }catch(e){if(alive.current){setError(detail(e));if([409,422].includes(e?.response?.status)){pending.current=null;setReview(null);setApproved(false);}}}finally{if(alive.current)setBusy(false);}
  }
  return <section aria-label="Opening prep stock" className={`${cardCls} space-y-4`}>
    <h2 className="text-lg font-semibold">Opening prep stock</h2>
    <p>Establish existing prep from a complete physical count before recorded production or waste begins. This is opening stock, not new production; no raw ingredients or Food Cost are deducted.</p>
    <p>Quantities come from the reviewed count. Original producing recipe and analytical costs remain unknown. A later count cannot reset source lots.</p>
    {error&&<p role="alert">{error}</p>}{message&&<p role="status">{message}</p>}
    <button disabled={frozen} className={btnGhost} onClick={refresh}>Refresh opening stock</button>
    {data&&<>
      <fieldset disabled={frozen} className="space-y-3">
        <Field label="Opening action"><select aria-label="Opening action" className={inpCls} value={mode} onChange={e=>edit(()=>{setMode(e.target.value);setCount('');setDecision('');setNote('');setBefore(false);})}><option value="initial">Establish opening stock</option><option value="void">Void erroneous opening decision</option></select></Field>
        {mode==='initial'?<>
          <Field label="Opening physical prep count"><select aria-label="Opening physical prep count" className={inpCls} value={count} onChange={e=>edit(()=>{setCount(e.target.value);setBefore(false);})}><option value="">Select complete physical prep count</option>{data.counts.map(c=><option key={c.id} value={c.id}>{c.performed_at} · {c.id}</option>)}</select></Field>
          <label><input aria-label="Confirm opening before activity" type="checkbox" checked={before} onChange={e=>edit(()=>setBefore(e.target.checked))}/> I confirm this count is before recorded prep and waste activity</label>
        </>:<>
          <Field label="Current opening decision"><select aria-label="Current opening decision" className={inpCls} value={decision} onChange={e=>edit(()=>setDecision(e.target.value))}><option value="">Select current opening decision</option>{current.map(d=><option key={d.id} value={d.id}>{d.id}</option>)}</select></Field>
          <p>Resolve dependent prep or waste before voiding. Correct an unused source by voiding, correcting its count and establishing a fresh opening before any activity history.</p>
        </>}
        <Field label="Opening evidence or correction reason"><input aria-label="Opening evidence or correction reason" className={inpCls} value={note} onChange={e=>edit(()=>setNote(e.target.value))}/></Field>
        <button className={btnAcc} onClick={preview}>Review opening stock</button>
      </fieldset>
      {review&&<div aria-label="Opening stock review" className={`${cardCls} space-y-2`}>
        <p>{review.review.kind} · physical count {review.review.count.performed_at}. Complete scope: {review.review.count.review_snapshot.scope.length} items; source lots: {review.review.lots.length}.</p>
        <ul>{review.review.lots.map(l=><li key={l.product_id}>{review.review.count.review_snapshot.definitions?.find(d=>d.product.product_id===l.product_id)?.product.name||l.product_id}: {l.quantity} {l.base_unit}{review.review.kind==='void'?' after reversal':''}</li>)}</ul>
        {review.review.lots.length===0&&<p>All observed quantities are zero; no artificial source lots will be created.</p>}
        <p>Opening stock adds no production, raw usage or accounting value. Costs are not calculated.</p>
        <label><input aria-label="Approve opening stock review" type="checkbox" checked={approved} disabled={frozen} onChange={e=>setApproved(e.target.checked)}/> I reviewed the full count and its derived sources</label>
        <button className={btnAcc} disabled={busy||(!approved&&!pending.current)} onClick={save}>{pending.current?'Retry same opening decision':'Save reviewed opening stock'}</button>
      </div>}
      <h3 className="font-semibold">Opening decision history</h3>
      {data.decisions.length===0&&<p>No opening prep stock established.</p>}
      {data.decisions.map(d=><article key={d.id} className={cardCls}><p>{d.kind} · {d.id} · {d.reason}</p><p>Physical count: {d.count_id}. Derived source lots: {d.review_snapshot.lots.length}.</p></article>)}
    </>}
  </section>;
}
