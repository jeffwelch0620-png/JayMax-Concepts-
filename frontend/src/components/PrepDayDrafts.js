import React,{useEffect,useRef,useState} from "react";
import * as api from "../lib/api";
import {useRetainedDraft} from "../lib/saveIntegrity";
import {todayISO} from "../lib/calc";
import {cardCls,inpCls,btnGhost,SectionLabel} from "./common";
import {PrepExecution} from "./PrepExecution";
import {StaffPrepAssignments} from "./StaffPrepTasks";
import {StaffProductionDecisions} from "./StaffPrepProduction";
const storeId=rid=>rid==="papa_leonis"?"papa":rid;
const decimal=value=>String(value).trim().replace(/^\+/,"").replace(/^\./,"0.").replace(/^0+(?=\d)/,"").replace(/(\.\d*?)0+$/, "$1").replace(/\.$/,"");
const stable=value=>JSON.stringify(value&&typeof value==="object"?Array.isArray(value)?value.map(v=>JSON.parse(stable(v))):Object.fromEntries(Object.keys(value).sort().map(k=>[k,JSON.parse(stable(value[k]))])):value);
const blank=track=>({loaded:false,version:0,inputs:{track,day_group:"weekday",count_event_id:null,overrides:[],note:""},preview:null,reviewed:false,pending:null});
export function PrepDayDrafts({rid,track="daily",drafts,showToast=()=>{}}){
  const [day,setDay]=useState(todayISO());
  return <div className={`${cardCls} p-4`}><SectionLabel>Dated Prep Drafts</SectionLabel>
    <p>Reviewed Track 2 tasks. Saving a draft records no production and leaves Food Cost unchanged. Manager execution is available when enabled.</p>
    <label>Service date<input aria-label="Prep draft date" className={inpCls} type="date" value={day} onChange={e=>setDay(e.target.value)}/></label>
    {day&&<DraftForm key={`${rid}:${day}:${track}`} rid={rid} day={day} track={track} drafts={drafts} showToast={showToast}/>}
  </div>;
}
function DraftForm({rid,day,track,drafts,showToast}){
  const [data,setData]=useState(null),[error,setError]=useState(""),[busy,setBusy]=useState(false),[reading,setReading]=useState(false);
  const [draft,setDraft]=useRetainedDraft(`prep-day:${rid}:${day}:${track}`,blank(track),drafts);
  const epoch=useRef(0),readSequence=useRef(0);
  const validSnapshot=r=>r?.store_id===storeId(rid)&&r.prep_date===day&&r.track===track&&r.status==="draft"&&r.execution_ready===false
    &&r.inputs?.track===track&&["weekday","weekend"].includes(r.inputs.day_group)&&typeof r.inputs.note==="string"&&Array.isArray(r.inputs.overrides)
    &&Array.isArray(r.tasks)&&Number.isSafeInteger(r.unresolved_tasks)&&r.unresolved_tasks>=0&&r.unresolved_tasks<=r.tasks.length
    &&r.tasks.every(t=>typeof t.product_id==="string"&&typeof t.name==="string"&&typeof t.source_unit==="string"&&(t.planned_quantity===null||/^(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?$/.test(t.planned_quantity)));
  useEffect(()=>{const id=++epoch.current;load(id);return()=>{epoch.current++;};},[]); // eslint-disable-line react-hooks/exhaustive-deps
  async function load(id=epoch.current,rebase=false){
    const sequence=++readSequence.current;setReading(true);
    try{
      const result=await api.prepDayDraft(rid,day,track);
      if(epoch.current!==id||sequence!==readSequence.current)return;
      if(result?.store_id!==storeId(rid)||result.prep_date!==day||result.track!==track||!["plans","products","unitProfiles"].every(k=>Array.isArray(result.planning?.[k]))||!Array.isArray(result.counts)||(result.current&&(!Number.isSafeInteger(result.current.revision)||result.current.revision<1||result.current.store_id!==storeId(rid)||!validSnapshot(result.current.review_snapshot))))throw new Error("Dated prep draft read was not confirmed.");
      setData(result);
      setDraft(previous=>!previous.loaded?{...previous,loaded:true,version:result.current?.revision||0,inputs:result.current?.review_snapshot?.inputs||previous.inputs}:rebase?{...previous,version:result.current?.revision||0,preview:null,reviewed:false}:previous);
      setError(rebase?"Version refreshed. Review retained day overrides against the current standing plans before previewing.":"");
    }catch(e){if(epoch.current===id&&sequence===readSequence.current)setError(e?.response?.data?.detail||e.message||"Dated draft read failed.");}
    finally{if(epoch.current===id&&sequence===readSequence.current)setReading(false);}
  }
  function change(key,value){setDraft(previous=>({...previous,inputs:{...previous.inputs,[key]:value},preview:null,reviewed:false}));}
  function override(plan,patch){
    const existing=draft.inputs.overrides.find(o=>o.planning_version_id===plan.id);
    const value={planning_version_id:plan.id,kind:"fixed_quantity",quantity:"",reason:"",...existing,...patch};
    change("overrides",[...draft.inputs.overrides.filter(o=>o.planning_version_id!==plan.id),...(value.kind==="auto"?[]:[{...value,quantity:value.kind==="omit"?null:value.quantity}])]);
  }
  async function preview(){
    if(busy||reading||draft.pending)return;const id=epoch.current;
    const body={...draft.inputs,note:draft.inputs.note.trim(),overrides:draft.inputs.overrides.map(o=>({...o,reason:o.reason.trim(),quantity:o.kind==="omit"?null:decimal(o.quantity)})).sort((a,b)=>a.planning_version_id.localeCompare(b.planning_version_id))};
    if(!body.note||body.overrides.some(o=>!o.reason||(o.kind!=="omit"&&!/^\d+(?:\.\d+)?$/.test(o.quantity)))){setError("Record a draft reason and a reviewed nonnegative decimal quantity/reason for each override.");return;}
    setBusy(true);setError("");
    try{
      const p=await api.previewPrepDayDraft(rid,day,body,draft.version);
      if(epoch.current!==id)return;
      if(!/^[a-f0-9]{64}$/.test(p?.reviewHash)||!validSnapshot(p.review)||p.review.base_revision!==draft.version||stable(p.review.inputs)!==stable(body))throw new Error("Dated draft preview was not confirmed.");
      setDraft(previous=>({...previous,preview:p,reviewed:false}));
    }catch(e){if(epoch.current===id)setError(e?.response?.data?.detail||e.message||"Draft preview failed.");}
    finally{if(epoch.current===id)setBusy(false);}
  }
  async function save(){
    if(busy||reading)return;const id=epoch.current;let submitted=draft.pending;
    if(!submitted){
      if(!draft.preview||!draft.reviewed){setError("Preview the dated tasks and confirm your review before saving.");return;}
      submitted={key:window.crypto.randomUUID(),version:draft.version,body:{draft:draft.preview.review.inputs,expected_review_hash:draft.preview.reviewHash,reviewed:true}};
      setDraft(previous=>({...previous,pending:submitted}));
    }
    setBusy(true);setError("");
    try{
      const response=await api.savePrepDayDraft(rid,day,submitted.body,submitted.version,submitted.key);
      if(epoch.current!==id)return;
      const saved=response?.draft,current=response?.current_draft;
      if(response.request_key!==submitted.key||saved?.store_id!==storeId(rid)||saved.revision!==submitted.version+1||!saved.id||saved.review_hash!==submitted.body.expected_review_hash||!validSnapshot(saved.review_snapshot)||stable(saved.review_snapshot?.inputs)!==stable(submitted.body.draft)||saved.status!=="draft"||current?.store_id!==storeId(rid)||current.list_id!==saved.list_id||!current.id||!Number.isSafeInteger(current.revision)||current.revision<saved.revision||!validSnapshot(current.review_snapshot)||current.status!=="draft"||(current.revision===saved.revision&&(current.id!==saved.id||current.review_hash!==saved.review_hash)))throw new Error("Dated draft save was not confirmed. The exact request is retained for retry.");
      setData(previous=>({...previous,current}));
      setDraft(previous=>previous.pending?.key===submitted.key?{...previous,version:current.revision,inputs:current.review_snapshot.inputs,preview:null,reviewed:false,pending:null}:previous);
      showToast(response.replayed?"Dated prep save confirmed; current saved draft displayed.":"Dated prep draft saved.");
    }catch(e){if(epoch.current!==id)return;setError(e?.response?.data?.detail||e.message||"Dated draft save was not confirmed.");if([400,403,404,409,422,428].includes(e?.response?.status))setDraft(previous=>({...previous,pending:null,preview:null,reviewed:false}));}
    finally{if(epoch.current===id)setBusy(false);}
  }
  const released=data?.execution_status==="released";
  const locked=busy||reading||!!draft.pending||released,plans=data?.planning.plans.filter(p=>p.active&&p.track===track)||[];
  const shown=draft.preview?.review||data?.current?.review_snapshot;
  return <div>{error&&<p role="alert">{error}</p>}{!data?<p>Dated planning awaiting a confirmed read.</p>:<>
    <p>Saved draft version {data.current?.revision||0}.{data.current?.source_changed?(released?" Source settings or physical count changed since this released version; manager review required.":" Source settings or physical count changed; preview a new version."):""}</p>
    <fieldset disabled={locked}>
      <label>Par group<select aria-label="Prep draft par group" className={inpCls} value={draft.inputs.day_group} onChange={e=>change("day_group",e.target.value)}><option value="weekday">Weekday pars</option><option value="weekend">Weekend pars</option></select></label>
      <label>Prior-day physical prep count<select aria-label="Prep draft count" className={inpCls} value={draft.inputs.count_event_id||""} onChange={e=>change("count_event_id",e.target.value||null)}><option value="">No count selected; to-par amounts stay unknown</option>{data.counts.map(c=><option key={c.id} value={c.id} disabled={!c.latest}>{c.business_date} · {c.performed_at} · {c.timezone_name}{c.latest?" (latest)":" (older)"}</option>)}</select></label>
      <p>One-day overrides use each standing plan's verified quantity unit. They do not change its usual par or recipe.</p>
      {plans.map(p=>{const o=draft.inputs.overrides.find(row=>row.planning_version_id===p.id),name=data.planning.products.find(v=>v.product_id===p.product_id)?.name||p.product_id,unit=data.planning.unitProfiles.find(u=>u.id===p.unit_profile_id)?.source_unit||"historical unit";
        return <div key={p.id} className="my-3"><label>{name} ({unit})<select aria-label={`Day override ${p.id}`} className={inpCls} value={o?.kind||"auto"} onChange={e=>override(p,{kind:e.target.value})}><option value="auto">Standing schedule</option><option value="fixed_quantity">Set output quantity</option><option value="target_par">Set target par</option><option value="omit">Omit this day</option></select></label>{o&&<>{o.kind!=="omit"&&<input aria-label={`Day quantity ${p.id}`} className={inpCls} inputMode="decimal" value={o.quantity??""} onChange={e=>override(p,{quantity:e.target.value})}/>}<input aria-label={`Day reason ${p.id}`} className={inpCls} placeholder="Override reason" value={o.reason} onChange={e=>override(p,{reason:e.target.value})}/></>}</div>;})}
      {draft.inputs.overrides.filter(o=>!plans.some(p=>p.id===o.planning_version_id)).map(o=><p key={o.planning_version_id}>Retained override refers to an older standing plan. <button className={btnGhost} onClick={()=>change("overrides",draft.inputs.overrides.filter(row=>row!==o))}>Remove outdated override</button></p>)}
      <label>Draft reason<textarea aria-label="Prep draft reason" className={inpCls} value={draft.inputs.note} onChange={e=>change("note",e.target.value)}/></label>
    </fieldset>
    <button className={btnGhost} disabled={locked} onClick={preview}>Preview dated tasks</button>
    {shown&&<><p>{shown.unresolved_tasks} task(s) have an unknown quantity. {released?"Released for manager execution.":"Draft awaiting release."}</p><div className="overflow-auto"><table className="ops-table"><thead><tr><th>Prep item</th><th>Mode</th><th>Output quantity</th><th>Review</th></tr></thead><tbody>{shown.tasks.map(t=><tr key={t.product_id}><td>{t.name}</td><td>{t.included?t.mode:"omitted"}</td><td>{t.planned_quantity??"Unknown"} {t.source_unit}</td><td>{t.issue||t.override_reason||"Reviewed source versions"}</td></tr>)}</tbody></table></div></>}
    {draft.preview&&<label><input type="checkbox" aria-label="Review dated prep draft" disabled={locked} checked={draft.reviewed} onChange={e=>setDraft(previous=>({...previous,reviewed:e.target.checked}))}/>I reviewed the tasks, units, count source, overrides and any unknown quantities.</label>}
    <button className={btnGhost} disabled={busy||reading||(!draft.pending&&(released||!draft.preview))} onClick={save}>{draft.pending?"Retry the same dated save":"Save reviewed dated draft"}</button>
    <button className={btnGhost} disabled={busy||reading||!!draft.pending} onClick={()=>load(epoch.current,true)}>Refresh dated draft versions</button>
    {released&&<p>Released draft is held for execution. Reopen it before editing.</p>}
    {api.prepExecutionEnabled&&<PrepExecution key={data.current?.id||"none"} rid={rid} day={day} track={track} drafts={drafts} showToast={showToast} onChange={()=>load(epoch.current,true)}/>}
    {api.staffPrepTasksEnabled&&<StaffPrepAssignments rid={rid} day={day} track={track} drafts={drafts}/>}
    {api.staffPrepProductionEnabled&&<StaffProductionDecisions rid={rid} day={day} track={track} drafts={drafts}/>}
  </>}</div>;
}
