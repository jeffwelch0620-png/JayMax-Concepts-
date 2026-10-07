import React,{useEffect,useRef,useState} from "react";
import * as api from "../lib/api";
import {useRetainedDraft} from "../lib/saveIntegrity";
import {inpCls,btnGhost,SectionLabel} from "./common";
const storeId=rid=>rid==="papa_leonis"?"papa":rid;
const stable=value=>JSON.stringify(value&&typeof value==="object"?Array.isArray(value)?value.map(v=>JSON.parse(stable(v))):Object.fromEntries(Object.keys(value).sort().map(k=>[k,JSON.parse(stable(value[k]))])):value);
const blank=()=>({action:"release",task_id:"",batch_event_id:"",link_event_id:"",task_outcome:"",reason:"",preview:null,reviewed:false,pending:null});

export function PrepExecution({rid,day,track,drafts,showToast=()=>{},onChange=()=>{}}){
  const [data,setData]=useState(null),[batches,setBatches]=useState([]),[error,setError]=useState(""),[busy,setBusy]=useState(false);
  const [draft,setDraft]=useRetainedDraft(`prep-execution:${rid}:${day}:${track}`,blank(),drafts);
  const epoch=useRef(0),sequence=useRef(0);
  const validState=s=>s?.store_id===storeId(rid)&&s.prep_date===day&&s.track===track&&Number.isSafeInteger(s.revision)&&s.revision>=0
    &&["draft","released"].includes(s.status)&&Array.isArray(s.tasks)&&Array.isArray(s.completions)&&Array.isArray(s.history)
    &&(!s.progress_supported||(Array.isArray(s.task_progress)&&s.task_progress.length===s.tasks.length&&new Set(s.task_progress.map(p=>p.task_id)).size===s.tasks.length&&s.task_progress.every(p=>s.tasks.some(t=>t.id===p.task_id)&&typeof p.closed==="boolean"&&typeof p.needs_review==="boolean"&&Array.isArray(p.links)&&["open","in_progress","complete","needs_review"].includes(p.status)&&["reviewed_base_quantity","effective_base_quantity"].every(k=>typeof p[k]==="string"&&/^\d+(?:\.\d+)?$/.test(p[k])))))
    &&(s.draft===null?s.draft_version_id===null:s.draft?.id===s.draft_version_id&&s.draft?.store_id===storeId(rid)&&s.draft.review_snapshot?.prep_date===day&&s.draft.review_snapshot?.track===track)
    &&(s.status!=="released"||(typeof s.release?.id==="string"&&s.release.draft_version_id===s.draft_version_id&&s.release.action==="release"));
  useEffect(()=>{const id=++epoch.current;load(id);return()=>{epoch.current++;};},[]); // eslint-disable-line react-hooks/exhaustive-deps
  async function load(id=epoch.current){
    const serial=++sequence.current;setBusy(true);
    try{
      const s=await api.prepExecution(rid,day,track);
      if(epoch.current!==id||sequence.current!==serial)return;
      if(!validState(s))throw new Error("Prep execution read was not confirmed.");
      setData(s);setError("");
      // Candidate batches are a separate read; their failure cannot erase an execution acknowledgement.
      const b=await api.nativePrepBatchSetup(rid);
      if(epoch.current!==id||sequence.current!==serial)return;
      if(!Array.isArray(b?.events))throw new Error("Production batch choices were not confirmed.");
      setBatches(b.events.filter(e=>e.store_id===storeId(rid)&&e.business_date===day&&e.kind!=="void"&&e.source_kind==="production"));
    }catch(e){if(epoch.current===id&&sequence.current===serial)setError(e?.response?.data?.detail||e.message||"Execution read failed.");}
    finally{if(epoch.current===id&&sequence.current===serial)setBusy(false);}
  }
  function change(key,value){setDraft(p=>({...p,[key]:value,preview:null,reviewed:false}));}
  async function preview(){
    if(busy||draft.pending||!data?.draft_version_id)return;const id=epoch.current;
    const taskCommand=["complete","link","finish","reconcile"].includes(draft.action),batchCommand=["complete","link","reconcile"].includes(draft.action);
    const command={action:draft.action,draft_version_id:data.draft_version_id,reason:draft.reason.trim(),task_id:taskCommand?draft.task_id:null,batch_event_id:batchCommand?draft.batch_event_id:null};
    const extended=["link","finish","reconcile"].includes(draft.action);
    if(extended)Object.assign(command,{link_event_id:draft.action==="reconcile"?draft.link_event_id:null,task_complete:draft.action==="reconcile"?draft.task_outcome==="complete":null});
    if(!command.reason||(taskCommand&&!command.task_id)||(batchCommand&&!command.batch_event_id)||(command.action==="reconcile"&&(!command.link_event_id||!draft.task_outcome))){setError("Record a reason and select this command's task, production evidence and reconciliation outcome.");return;}
    setBusy(true);setError("");
    try{
      const p=await api.previewPrepExecution(rid,day,track,command,data.revision);
      if(epoch.current!==id)return;
      const r=p?.review;
      if(!/^[a-f0-9]{64}$/.test(p?.reviewHash)||r?.store_id!==storeId(rid)||r.prep_date!==day||r.track!==track||r.base_revision!==data.revision
         ||stable(r.command)!==stable(command)||r.draft_review_hash!==data.draft.review_hash||r.status_after!==(command.action==="reopen"?"draft":"released")
         ||(taskCommand&&r.task?.id!==command.task_id)||(batchCommand&&(r.batch?.id!==command.batch_event_id||r.batch?.store_id!==storeId(rid)||r.batch?.business_date!==day))
         ||(extended&&stable(r.progress_before)!==stable(data.task_progress.find(t=>t.task_id===command.task_id)))
         ||(command.action==="reconcile"&&r.original_link?.id!==command.link_event_id))throw new Error("Prep execution preview was not confirmed.");
      setDraft(previous=>({...previous,preview:p,reviewed:false}));
    }catch(e){if(epoch.current===id)setError(e?.response?.data?.detail||e.message||"Execution preview failed.");}
    finally{if(epoch.current===id)setBusy(false);}
  }
  async function save(){
    if(busy)return;const id=epoch.current;let sent=draft.pending;
    if(!sent){
      if(!draft.preview||!draft.reviewed){setError("Preview and confirm the execution evidence first.");return;}
      sent={key:window.crypto.randomUUID(),version:draft.preview.review.base_revision,body:{command:draft.preview.review.command,expected_review_hash:draft.preview.reviewHash,reviewed:true}};
      setDraft(previous=>({...previous,pending:sent}));
    }
    setBusy(true);setError("");
    try{
      const r=await api.savePrepExecution(rid,day,track,sent.body,sent.version,sent.key);
      if(epoch.current!==id)return;
      const e=r?.event;
      if(r?.request_key!==sent.key||!e?.id||e.store_id!==storeId(rid)||e.revision!==sent.version+1||e.review_hash!==sent.body.expected_review_hash
         ||e.action!==sent.body.command.action||e.draft_version_id!==sent.body.command.draft_version_id||stable(e.review_snapshot?.command)!==stable(sent.body.command)
         ||(["link","finish","reconcile"].includes(sent.body.command.action)&&r.current?.progress_supported!==true)
         ||!validState(r.current)||r.current.revision<e.revision||r.current.draft?.list_id!==e.list_id
         ||!r.current.history.some(h=>h.id===e.id&&h.review_hash===e.review_hash&&h.revision===e.revision))throw new Error("Prep execution save was not confirmed. The exact command is retained for retry.");
      setData(r.current);
      setDraft(previous=>previous.pending?.key===sent.key?blank():previous);
      showToast(r.replayed?"Prep command confirmed; current execution displayed.":"Prep execution command saved.");
      onChange();
    }catch(e){
      if(epoch.current!==id)return;
      setError(e?.response?.data?.detail||e.message||"Execution save was not confirmed.");
      if([400,403,404,409,422,428].includes(e?.response?.status))setDraft(p=>({...p,pending:null,preview:null,reviewed:false}));
    }finally{if(epoch.current===id)setBusy(false);}
  }
  const locked=busy||!!draft.pending;
  const tasks=data?.tasks.filter(t=>{
    if(!t.included||t.planned_quantity===null||/^0(?:\.0+)?$/.test(t.planned_quantity))return false;
    const p=data.task_progress?.find(p=>p.task_id===t.id),links=data.completions.filter(c=>c.task_id===t.id);
    if(draft.action==="reconcile")return links.some(c=>c.needs_review);
    if(draft.action==="complete")return links.length===0;
    return p?!p.closed&&!p.needs_review:links.length===0;
  })||[];
  const selected=tasks.find(t=>t.id===draft.task_id);
  const reviews=data?.completions.filter(c=>c.task_id===draft.task_id&&c.needs_review)||[],chosenLink=reviews.find(c=>c.execution_id===draft.link_event_id);
  const choices=draft.action==="reconcile"?(chosenLink?[chosenLink.effective_batch]:[]):batches.filter(b=>b.product_id===selected?.product_id&&b.recipe_version_id===selected?.recipe_version_id&&!data?.completions.some(c=>c.effective_batch.root_id===b.root_id));
  return <div className="mt-5"><SectionLabel>Manager Prep Execution</SectionLabel>
    <p>Release a reviewed saved draft, link each measured batch once, and finish explicitly. Review corrected production before proceeding. Food Cost stays based on purchased inventory.</p>
    {error&&<p role="alert">{error}</p>}
    {data?<><p>Execution version {data.revision} · {data.status} · saved draft {data.draft?.revision||0}.</p>
      {data.completions.map(c=><p key={c.execution_id}>Production linked: {data.tasks.find(t=>t.id===c.task_id)?.task_snapshot.name||c.task_id} · measured {c.effective_batch.review_snapshot?.usableBaseOutput??"voided"} {c.effective_batch.base_unit}{c.needs_review?" · Batch corrected or voided; manager review required.":""}</p>)}
      {data.progress_supported&&data.task_progress.map(p=><p key={p.task_id}>{data.tasks.find(t=>t.id===p.task_id)?.task_snapshot.name} · {p.status} · planned {p.planned_base_quantity??"Unknown"}, current recorded {p.effective_base_quantity}, reviewed {p.reviewed_base_quantity} {data.tasks.find(t=>t.id===p.task_id)?.task_snapshot.base_unit}. Production quantity does not automatically finish a task.</p>)}
      <fieldset disabled={locked||!data.draft_version_id}>
        <label>Command<select aria-label="Prep execution action" className={inpCls} value={draft.action} onChange={e=>change("action",e.target.value)}><option value="release">Release saved draft</option><option value="reopen">Reopen before production linkage</option><option value="complete">Link one batch and finish task</option>{data.progress_supported&&<><option value="link">Add partial production batch</option><option value="finish">Finish reviewed task progress</option><option value="reconcile">Review corrected or voided production</option></>}</select></label>
        {["complete","link","finish","reconcile"].includes(draft.action)&&<><label>Task<select aria-label="Prep execution task" className={inpCls} value={draft.task_id} onChange={e=>{setDraft(p=>({...p,task_id:e.target.value,batch_event_id:"",link_event_id:"",task_outcome:"",preview:null,reviewed:false}));}}><option value="">Select task</option>{tasks.map(t=><option key={t.id} value={t.id}>{t.task_snapshot.name} · planned {t.planned_quantity} {t.task_snapshot.source_unit}</option>)}</select></label>
        {draft.action==="reconcile"&&<><label>Original production link<select aria-label="Prep reconciliation link" className={inpCls} value={draft.link_event_id||""} onChange={e=>setDraft(p=>({...p,link_event_id:e.target.value,batch_event_id:"",task_outcome:"",preview:null,reviewed:false}))}><option value="">Select changed production</option>{reviews.map(c=><option key={c.execution_id} value={c.execution_id}>{c.execution_id} · current {c.effective_batch.kind} · {c.effective_batch.id}</option>)}</select></label>
        <label>Task after review<select aria-label="Prep reconciliation outcome" className={inpCls} value={draft.task_outcome||""} onChange={e=>change("task_outcome",e.target.value)}><option value="">Choose task outcome</option><option value="open">Keep or reopen task for more production</option><option value="complete" disabled={chosenLink?.effective_batch.kind==="void"}>Task is finished with corrected production</option></select></label></>}
        {draft.action!=="finish"&&<><label>Reviewed production<select aria-label="Prep execution batch" className={inpCls} value={draft.batch_event_id} onChange={e=>change("batch_event_id",e.target.value)}><option value="">Select measured batch</option>{choices.map(b=><option key={b.id} value={b.id}>{b.performed_at} · {b.kind==="void"?"voided":b.review_snapshot.usableBaseOutput} {b.base_unit} · {b.id}</option>)}</select></label><p>Record measured production first. Each whole batch belongs to one task; planned output is not automatically recorded as actual output.</p></>}</>}
        <label>Reason<textarea aria-label="Prep execution reason" className={inpCls} value={draft.reason} onChange={e=>change("reason",e.target.value)}/></label>
      </fieldset>
      <button className={btnGhost} disabled={locked||!data.draft_version_id} onClick={preview}>Preview prep command</button>
      {draft.preview&&<><p>Review {draft.preview.review.command.action} against this exact saved draft.{draft.preview.review.batch?draft.preview.review.batch.kind==="void"?" Voided production: task must reopen.":` Measured output: ${draft.preview.review.batch.review_snapshot.usableBaseOutput} ${draft.preview.review.batch.base_unit}.`:""}{draft.preview.review.original_link?` Original linked output: ${draft.preview.review.original_link.review_snapshot?.batch?.review_snapshot?.usableBaseOutput}. Reviewed recipe version: ${draft.preview.review.batch.recipe_version_id}. Task outcome: ${draft.preview.review.command.task_complete?"finished":"open"}.`:""}</p><label><input type="checkbox" aria-label="Review prep execution" disabled={locked} checked={draft.reviewed} onChange={e=>setDraft(p=>({...p,reviewed:e.target.checked}))}/>I reviewed this command and its production evidence.</label></>}
      <button className={btnGhost} disabled={busy||(!draft.pending&&(!draft.preview||!draft.reviewed))} onClick={save}>{draft.pending?"Retry same prep command":"Save reviewed prep command"}</button>
    </>:<p>Execution awaiting a confirmed read.</p>}
    <button className={btnGhost} disabled={locked} onClick={()=>{setDraft(p=>({...p,preview:null,reviewed:false}));load();}}>Refresh prep execution</button>
  </div>;
}
