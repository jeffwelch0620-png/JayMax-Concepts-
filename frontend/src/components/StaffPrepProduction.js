import React,{useEffect,useRef,useState} from "react";
import * as api from "../lib/api";
import {useRetainedDraft} from "../lib/saveIntegrity";
import {validAssignmentState} from "./StaffPrepTasks";
import {cardCls,inpCls,btnGhost} from "./common";
const storeId=rid=>rid==="papa_leonis"?"papa":rid;
const uid=v=>typeof v==="string"&&/^[a-f0-9]{8}(-[a-f0-9]{4}){3}-[a-f0-9]{12}$/i.test(v);
const hash=v=>typeof v==="string"&&/^[a-f0-9]{64}$/.test(v);
const numeric=new Set(["quantity","factor","planned_batches","output_quantity","included_loss_quantity","base_quantity","usableBaseOutput"]);
const exact=v=>{const m=/^([+-]?)(\d+)(?:\.(\d+))?(?:[eE]([+-]?\d{1,2}))?$/.exec(String(v));if(!m)throw new Error("Invalid quantity");const shift=48+Number(m[4]||0)-(m[3]||"").length;const digits=BigInt(m[2]+(m[3]||""));if(shift<0)throw new Error("Unsupported quantity precision");return (m[1]==="-"?-1n:1n)*digits*10n**BigInt(shift);};
export function productionSame(a,b,key=""){
  if(a===null||b===null)return a===b;
  if(numeric.has(key)){try{return exact(a)===exact(b);}catch{return false;}}
  if(key==="performed_at"&&typeof a==="string"&&typeof b==="string")return a.replace(/Z$/,"+00:00")===b.replace(/Z$/,"+00:00");
  if(Array.isArray(a)||Array.isArray(b))return Array.isArray(a)&&Array.isArray(b)&&a.length===b.length&&a.every((v,i)=>productionSame(v,b[i]));
  if(a&&b&&typeof a==="object"&&typeof b==="object"){const keys=Object.keys(a);return keys.length===Object.keys(b).length&&keys.every(k=>productionSame(a[k],b[k],k));}
  return a===b;
}
export function validProductionHistory(h,store){
  return uid(h?.root_id)&&Array.isArray(h.events)&&h.events.length>0&&new Set(h.events.map(e=>e.id)).size===h.events.length
    &&h.events.every((e,i)=>uid(e.id)&&e.store_id===store&&e.root_id===h.root_id&&e.revision===i+1&&e.predecessor_id===(i?h.events[i-1].id:null)
      &&(i!==0||e.id===h.root_id)&&["submit","withdraw"].includes(e.kind)&&uid(e.task_id)&&uid(e.staff_member_id)&&uid(e.assignment_id)
      &&hash(e.review_hash)&&uid(e.request_key)&&e.review_snapshot?.identity_verified===false&&e.review_snapshot.productionEffect==="none"
      &&e.review_snapshot.submission?.root_id===e.root_id&&e.review_snapshot.submission.expected_revision===i
      &&e.review_snapshot.submission.kind===e.kind&&e.review_snapshot.submission.task_id===e.task_id&&e.review_snapshot.submission.staff_member_id===e.staff_member_id)
    &&Array.isArray(h.decisions)&&new Set(h.decisions.map(d=>d.submission_id)).size===h.decisions.length
    &&h.decisions.every(d=>uid(d.id)&&d.store_id===store&&["accepted","rejected"].includes(d.decision)&&hash(d.review_hash)&&uid(d.request_key)
      &&h.events.some(e=>e.id===d.submission_id&&e.kind==="submit"&&productionSame(d.review_snapshot?.submission?.review_snapshot,e.review_snapshot)));
}
function validBatchReview(p,b,original=null){
  try{const r=p?.review;
    return hash(p?.reviewHash)&&r?.kind==="initial"&&r.revision===1&&r.predecessor_id===null&&r.root_id===null&&r.recipe_version_id===b.recipe_version_id
      &&r.business_date===b.business_date&&r.timezone_name===b.timezone_name&&productionSame(r.batch,b)&&exact(r.usableBaseOutput)>0n
      &&(!original||exact(r.usableBaseOutput)===exact(original.review.usableBaseOutput))&&typeof r.outputUnit==="string"
      &&Array.isArray(r.inputs)&&r.inputs.length===b.inputs.length&&r.inputs.every((x,i)=>{
        const v=b.inputs[i];return x.recipe_line_id===v.recipe_line_id&&productionSame(x.quantity,v.quantity,"quantity")&&productionSame(x.factor,v.factor,"factor")
          &&x.source_unit===v.source_unit&&x.measurement_basis===v.measurement_basis&&x.evidence===v.evidence&&x.source_batch_id===v.source_batch_id
          &&exact(x.base_quantity)===exact(v.quantity)*exact(v.factor)/10n**48n;
      })&&Array.isArray(r.movements)&&r.movements.length===b.inputs.length+1&&r.movements.every((m,i)=>m.side==="apply"&&m.reverses_movement_id===null
        &&(i===b.inputs.length?m.kind==="output"&&exact(m.quantity)===exact(r.usableBaseOutput):m.recipe_line_id===b.inputs[i].recipe_line_id&&m.source_batch_id===b.inputs[i].source_batch_id&&exact(m.quantity)===-exact(r.inputs[i].base_quantity)));
  }catch{return false;}
}
export function validProductionState(s,rid,day,track,staffId=null){return s?.store_id===storeId(rid)&&s.day===day&&s.track===track
  &&s.selected_member_id===staffId&&s.accountingEffect==="none"&&Array.isArray(s.submissions)&&new Set(s.submissions.map(h=>h.root_id)).size===s.submissions.length
  &&s.submissions.every(h=>validProductionHistory(h,storeId(rid))&&h.events.every(e=>e.review_snapshot.day===day&&e.review_snapshot.track===track&&(!staffId||e.staff_member_id===staffId)));}
export function validProductionReview(p,body,rid,day,track,manager=false,selected=null){
  const r=p?.review;if(!hash(p?.reviewHash)||r?.store_id!==storeId(rid)||r.day!==day||r.track!==track||r.accountingEffect!=="none")return false;
  if(!manager)return productionSame(r.submission,body.submission)&&r.identity_verified===false&&r.productionEffect==="none"
    &&(body.submission.kind==="withdraw"?r.batch===null:r.sources?.assignment?.id===body.submission.assignment_id&&r.sources.assignment.staff_member_id===body.submission.staff_member_id
      &&r.sources.task?.id===body.submission.task_id&&validBatchReview(r.batch,body.submission.batch));
  return productionSame(r.decision,body)&&selected&&productionSame(r.submission,selected)
    &&(body.decision==="rejected"?r.batch===null&&r.sources===null&&r.productionEffect==="none":r.productionEffect==="record_once"
      &&r.batch?.review?.staff_submission_id===selected.id&&validBatchReview(r.batch,selected.review_snapshot.submission.batch,selected.review_snapshot.batch)
      &&r.sources?.task?.id===selected.task_id&&r.sources.assignment?.id===selected.assignment_id&&r.sources.assignment.staff_member_id===selected.staff_member_id);
}
function staffReceiptView(value){
  if(Array.isArray(value))return value.map(staffReceiptView);
  if(value&&typeof value==="object")return Object.fromEntries(Object.entries(value)
    .filter(([key])=>!["submitted_by","recorded_by","issued_by","actor","email"].includes(key)).map(([key,item])=>[key,staffReceiptView(item)]));
  return value;
}
export function validProductionAck(ack,pending,rid,day,track,manager=false){
  // A pre-upgrade pending staff preview may contain private audit identities.
  // Keep its original request/hash while comparing the public response projection.
  if(!manager){ack=staffReceiptView(ack);pending={...pending,review:staffReceiptView(pending.review)};}
  const r=pending.review.review,store=storeId(rid),record=manager?ack?.decision:ack?.submission;
  if(!uid(record?.id)||record.store_id!==store||record.request_key!==pending.key||!hash(record.request_fingerprint)||record.review_hash!==pending.body.expected_review_hash||!productionSame(record.review_snapshot,r)
    ||!validProductionHistory(ack.history,store))return false;
  if(!manager){const b=r.submission;return record.root_id===b.root_id&&record.task_id===b.task_id&&record.staff_member_id===b.staff_member_id&&record.assignment_id===b.assignment_id
    &&record.revision===b.expected_revision+1&&record.predecessor_id===r.predecessor_id&&record.kind===b.kind&&record.note===b.note
    &&record.submitted_by===r.submitted_by&&record.credential_kind===r.credential_kind&&ack.productionEffect==="none"&&ack.history.events.some(e=>productionSame(e,record));}
  const d=r.decision,b=ack.batch_event,e=ack.execution_event,f=ack.finish_event;
  if(record.submission_id!==d.submission_id||record.decision!==d.decision||record.task_complete!==d.task_complete||record.note!==d.note
    ||!ack.history.decisions.some(x=>productionSame(x,record))||!validAssignmentState(ack.current,rid,day,track))return false;
  if(d.decision==="rejected")return b===null&&e===null&&f===null&&record.batch_event_id===null&&record.execution_event_id===null&&record.finish_event_id===null;
  if(!uid(b?.id)||b.id!==record.batch_event_id||b.store_id!==store||b.kind!=="initial"||b.source_kind!=="production"||b.root_id!==b.id||b.predecessor_id!==null
    ||b.request_key!==pending.key||b.request_fingerprint!==record.request_fingerprint||b.recorded_by!==record.recorded_by||b.review_hash!==r.batch.reviewHash||!productionSame(b.review_snapshot,r.batch.review)
    ||b.recipe_version_id!==r.submission.review_snapshot.submission.batch.recipe_version_id||b.business_date!==day
    ||!uid(e?.id)||e.id!==record.execution_event_id||e.store_id!==store||e.action!=="link"||e.batch_event_id!==b.id||e.batch_root_id!==b.id||e.task_id!==r.submission.task_id
    ||e.actor!==record.recorded_by||e.reason!==d.note||e.request_key!==pending.key||e.request_fingerprint!==record.request_fingerprint||e.review_snapshot?.staff_submission_id!==d.submission_id
    ||!productionSame(e.review_snapshot.batch,b)||!productionSame(e.review_snapshot.progress_before,r.sources.progress))return false;
  return d.task_complete?uid(f?.id)&&f.id===record.finish_event_id&&f.action==="finish"&&f.store_id===store&&f.task_id===e.task_id&&f.predecessor_id===e.id&&f.revision===e.revision+1
    &&f.actor===record.recorded_by&&f.reason===d.note&&f.request_fingerprint===record.request_fingerprint&&f.review_snapshot?.staff_submission_id===d.submission_id:f===null&&record.finish_event_id===null;
}
const blank=()=>({task_id:"",root_id:"",event_id:"",kind:"submit",batch:null,note:"",decision:"accepted",task_complete:false,review:null,confirmed:false,pending:null,rejected:false});
const errorText=e=>typeof e?.response?.data?.detail==="string"?e.response.data.detail:e.message||"Production save was not confirmed.";
export function StaffProductionSubmission(props){return <ProductionForm key={`${props.rid}:${props.day}:${props.track}:${props.staffId}`} {...props}/>;}
export function StaffProductionDecisions(props){return <ProductionForm key={`${props.rid}:${props.day}:${props.track}:manager`} {...props} manager/>;}
function ProductionForm({rid,day,track,staffId=null,pin="",plan=null,drafts,manager=false}){
  const ownCache=useRef(new Map()),cache=drafts||ownCache.current,key=`${manager?"prep-production-decision":"staff-production-submit"}:${rid}:${day}:${track}:${staffId||"manager"}`;
  const [draft,edit,clear]=useRetainedDraft(key,blank(),cache),[data,setData]=useState(null),[busy,setBusy]=useState(false),[error,setError]=useState(""),[message,setMessage]=useState("");
  const epoch=useRef(0),seq=useRef(0),frozen=busy||!!draft.pending;
  async function load(){const id=epoch.current,n=++seq.current;setData(null);setError("");
    try{const s=manager?await api.staffProductionReviewSetup(rid,day,track):await api.staffProductionSetup(rid,day,track,staffId,pin);if(id!==epoch.current||n!==seq.current)return;
      if(!validProductionState(s,rid,day,track,manager?null:staffId)||(!manager&&(s.identity_verified!==false||!Array.isArray(s.setup?.recipes)||!Array.isArray(s.setup?.lots))))throw new Error("Production history was not confirmed for this date and location.");setData(s);
    }catch(e){if(id===epoch.current&&n===seq.current)setError(errorText(e));}
  }
  useEffect(()=>{++epoch.current;load();return()=>{++epoch.current;++seq.current;};},[pin]); // eslint-disable-line react-hooks/exhaustive-deps
  const update=(key,value)=>{edit(d=>({...d,[key]:value,review:null,confirmed:false}));setMessage("");};
  const roots=data?.submissions||[],selectedRoot=roots.find(h=>h.events.some(e=>e.id===draft.event_id)),selected=selectedRoot?.events.find(e=>e.id===draft.event_id);
  const task=plan?.tasks.find(t=>t.id===draft.task_id),recipe=data?.setup?.recipes.find(r=>r.id===draft.batch?.recipe_version_id);
  function chooseTask(id){const t=plan.tasks.find(t=>t.id===id),r=data.setup.recipes.find(r=>r.id===t?.recipe_version_id);
    edit({...blank(),task_id:id,root_id:crypto.randomUUID(),batch:r?{recipe_version_id:r.id,planned_batches:"",output_quantity:"",performed_at:"",business_date:day,timezone_name:data.setup.policy?.timezone_name||"",
      calendar_date_confirmed:false,single_output_confirmed:false,note:"",inputs:r.lines.map(l=>({recipe_line_id:l.id,quantity:"",source_unit:l.source_unit,factor:l.factor,measurement_basis:"",source_batch_id:null,included_loss_quantity:null,loss_evidence:null,evidence:""}))}:null});}
  function chooseRevision(id){const h=roots.find(h=>h.events.at(-1).id===id),s=h?.events.at(-1);if(!s){edit(blank());return;}
    edit({...blank(),task_id:s.task_id,root_id:s.root_id,event_id:s.id,batch:s.review_snapshot.submission.batch,note:""});}
  function batchField(k,v){update("batch",{...draft.batch,[k]:v});}
  function inputField(i,k,v){batchField("inputs",draft.batch.inputs.map((x,j)=>j===i?{...x,[k]:v}:x));}
  function body(){if(manager)return {submission_id:draft.event_id,decision:draft.decision,task_complete:draft.task_complete,note:draft.note.trim()};
    const previous=selectedRoot?.events.at(-1),assignment=draft.kind==="withdraw"?previous?.assignment_id:task?.assignment;
    return {submission:{root_id:draft.root_id,expected_revision:previous?.revision||0,task_id:draft.task_id,staff_member_id:staffId,assignment_id:assignment,
      kind:draft.kind,batch:draft.kind==="withdraw"?null:{...draft.batch,note:draft.batch?.note.trim()},note:draft.note.trim()}};
  }
  async function preview(){const id=epoch.current;setBusy(true);setError("");edit(d=>({...d,review:null,confirmed:false}));
    try{const b=body(),p=manager?await api.previewStaffProductionDecision(rid,day,track,b):await api.previewStaffProduction(rid,day,track,b,pin);if(id!==epoch.current)return;
      if(!validProductionReview(p,b,rid,day,track,manager,selected))throw new Error("Production review did not match the retained measurements and assignment.");edit(d=>({...d,review:p,confirmed:false}));
    }catch(e){if(id===epoch.current)setError(errorText(e));}finally{if(id===epoch.current)setBusy(false);}
  }
  async function save(){if(!draft.pending&&(!draft.review||!draft.confirmed))return;const id=epoch.current;
    const p=draft.pending||{key:crypto.randomUUID(),review:draft.review,body:{...(manager?draft.review.review.decision:{submission:draft.review.review.submission}),reviewed:true,expected_review_hash:draft.review.reviewHash}};
    const submitted={...draft,pending:p,rejected:false};edit(submitted);setBusy(true);setError("");
    try{const ack=manager?await api.decideStaffProduction(rid,day,track,p.body,p.key):await api.submitStaffProduction(rid,day,track,p.body,p.key,pin);if(id!==epoch.current||!cache.has(key))return;
      if(!validProductionAck(ack,p,rid,day,track,manager))throw new Error("Production save was not confirmed. Retry the same request.");
      if(clear(submitted,blank())){setMessage(manager?(ack.decision.decision==="accepted"?"Measured production accepted and linked once. Food Cost is unchanged.":"Submission rejected; no production recorded."):"Submission saved for manager review; no production recorded.");await load();}
    }catch(e){if(id===epoch.current&&cache.has(key)){setError(errorText(e));if([409,422].includes(e?.response?.status))edit(d=>({...d,rejected:true}));}}
    finally{if(id===epoch.current)setBusy(false);}
  }
  return <section className={`${cardCls} p-3`} aria-label={manager?"Staff production decisions":"Staff measured production"}><h3>{manager?"Review staff production":"Submit measured production"}</h3>
    <p>{manager?"Inspect measured output and gross inputs before accepting. Choose explicitly whether the task is finished.":"Selected roster name is claimed identity. Submitting measurements creates no inventory until a manager accepts them."}</p>
    {error&&<p role="alert">{error}</p>}{message&&<p role="status">{message}</p>}<button className={btnGhost} disabled={frozen} onClick={load}>Refresh production submissions</button>
    {data&&<><ul>{roots.map(h=><li key={h.root_id}>Submission {h.root_id} Ã‚Â· revision {h.events.at(-1).revision} Ã‚Â· {h.events.at(-1).kind} Ã‚Â· {h.events.at(-1).kind==="withdraw"?"withdrawn":h.decisions.find(d=>d.submission_id===h.events.at(-1).id)?.decision||"awaiting review"}</li>)}</ul>
    <fieldset disabled={frozen}>
      <label>{manager?"Pending production submission":"Revise production submission"}<select className={inpCls} aria-label={manager?"Pending production submission":"Revise production submission"} value={draft.event_id} onChange={e=>manager?update("event_id",e.target.value):chooseRevision(e.target.value)}><option value="">{manager?"Choose submission":"New measured production"}</option>{roots.filter(h=>h.events.at(-1).kind==="submit"&&!h.decisions.some(d=>d.decision==="accepted")&&(manager?!h.decisions.some(d=>d.submission_id===h.events.at(-1).id):true)).map(h=><option key={h.root_id} value={h.events.at(-1).id}>{h.root_id} Ã‚Â· revision {h.events.at(-1).revision}</option>)}</select></label>
      {manager?<><label>Production decision<select className={inpCls} aria-label="Production decision" value={draft.decision} onChange={e=>{update("decision",e.target.value);update("task_complete",false);}}><option value="accepted">Accept measured production</option><option value="rejected">Reject submission</option></select></label>
        <label><input type="checkbox" aria-label="Finish task on acceptance" disabled={draft.decision!=="accepted"} checked={draft.task_complete} onChange={e=>update("task_complete",e.target.checked)}/> Finish this task after accepting this measured batch</label>
        {selected&&<Measurements batch={selected.review_snapshot.submission.batch} unit={selected.review_snapshot.batch?.review.outputUnit}/>}</>:<>
        <label>Assigned production task<select className={inpCls} aria-label="Assigned production task" disabled={!!draft.event_id} value={draft.task_id} onChange={e=>chooseTask(e.target.value)}><option value="">Select assigned task</option>{(plan?.tasks||[]).filter(t=>t.assigned_member?.id===staffId&&!t.roster_changed&&!t.progress.closed&&!t.progress.needs_review).map(t=><option key={t.id} value={t.id}>{t.name} Ã‚Â· {t.quantity} {t.source_unit} planned</option>)}</select></label>
        {draft.event_id&&<label>Submission action<select aria-label="Submission action" value={draft.kind} onChange={e=>update("kind",e.target.value)}><option value="submit">Revise measured submission</option><option value="withdraw">Withdraw pending submission</option></select></label>}
        {draft.batch&&draft.kind==="submit"&&<><p>Measured usable output unit: {recipe?.outputUnit||"review required"}. Planned output is not a measurement.</p>
          {[["planned_batches","Recipe batches prepared"],["output_quantity","Measured usable production"],["performed_at","Production time with offset"],["timezone_name","Production timezone"],["note","Production measurement evidence"]].map(([k,label])=><label key={k}>{label}<input className={inpCls} aria-label={label} value={draft.batch[k]} onChange={e=>batchField(k,e.target.value)}/></label>)}
          <p>Physical calendar date: {day}</p>
          {draft.batch.inputs.map((x,i)=>{const l=recipe?.lines.find(l=>l.id===x.recipe_line_id);return <fieldset key={x.recipe_line_id}><legend>Ingredient {i+1} Ã‚Â· {l?.raw_item_code||"prepared ingredient"} Ã‚Â· {x.source_unit}</legend>
            <label>Gross ingredient {i+1}<input aria-label={`Gross ingredient ${i+1}`} value={x.quantity} onChange={e=>inputField(i,"quantity",e.target.value)}/></label>
            <label>Ingredient basis {i+1}<select aria-label={`Ingredient basis ${i+1}`} value={x.measurement_basis} onChange={e=>inputField(i,"measurement_basis",e.target.value)}><option value="">Select basis</option><option value="measured">Measured</option><option value="recipe_estimate">Recipe estimate</option></select></label>
            <label>Ingredient evidence {i+1}<input aria-label={`Ingredient evidence ${i+1}`} value={x.evidence} onChange={e=>inputField(i,"evidence",e.target.value)}/></label>
            {l?.source_kind==="prepared"&&<label>Source lot {i+1}<select aria-label={`Source lot ${i+1}`} value={x.source_batch_id||""} onChange={e=>inputField(i,"source_batch_id",e.target.value||null)}><option value="">Select measured lot</option>{data.setup.lots.filter(v=>v.product_id===l.source_snapshot?.recipe?.product_id).map(v=><option key={v.id} value={v.id}>{v.id} Ã‚Â· {v.remainingRecordedQuantity} {v.base_unit} unallocated</option>)}</select></label>}
            <label>Included loss {i+1}<input aria-label={`Included loss ${i+1}`} value={x.included_loss_quantity??""} onChange={e=>inputField(i,"included_loss_quantity",e.target.value||null)}/></label>
            <label>Included loss evidence {i+1}<input aria-label={`Included loss evidence ${i+1}`} value={x.loss_evidence||""} onChange={e=>inputField(i,"loss_evidence",e.target.value||null)}/></label>
          </fieldset>;})}
          <label><input type="checkbox" aria-label="Confirm production calendar date" checked={draft.batch.calendar_date_confirmed} onChange={e=>batchField("calendar_date_confirmed",e.target.checked)}/> Confirm this location calendar date and timezone</label>
          <label><input type="checkbox" aria-label="Confirm single usable output" checked={draft.batch.single_output_confirmed} onChange={e=>batchField("single_output_confirmed",e.target.checked)}/> One usable output, with no unmapped recoverable byproducts</label>
        </>}
      </>}
      <label>Production review reason<input className={inpCls} aria-label="Production review reason" value={draft.note} onChange={e=>update("note",e.target.value)}/></label>
      <button className={btnGhost} disabled={manager?!draft.event_id:!draft.root_id} onClick={preview}>Review production record</button>
    </fieldset></>}
    {draft.review&&<article aria-label="Production record review"><p>{manager?draft.review.review.decision.decision:draft.review.review.submission.kind} Ã‚Â· {day} Ã‚Â· {track} Ã‚Â· {draft.review.review.productionEffect}</p>
      <Measurements batch={manager?draft.review.review.submission.review_snapshot.submission.batch:draft.review.review.submission.batch} unit={draft.review.review.batch?.review.outputUnit}/>
      {manager&&draft.review.review.decision.decision==="accepted"&&<p>{draft.review.review.decision.task_complete?"Accept this batch and finish the task.":"Accept this partial batch; task remains open."}</p>}
      <label><input type="checkbox" aria-label="Confirm production review" disabled={frozen} checked={draft.confirmed} onChange={e=>edit(d=>({...d,confirmed:e.target.checked}))}/> I reviewed the measured quantities, source lots and history.</label>
      <button className={btnGhost} disabled={busy||(!draft.pending&&!draft.confirmed)} onClick={save}>{draft.pending?"Retry same production record":"Save reviewed production record"}</button>
    </article>}
    {draft.pending&&draft.rejected&&<button className={btnGhost} disabled={busy} onClick={()=>{edit(d=>({...d,pending:null,review:null,confirmed:false,rejected:false}));load();}}>Revise rejected production record</button>}
  </section>;
}
function Measurements({batch,unit}){return batch?<div aria-label="Submitted production measurements"><p>Usable output {batch.output_quantity} Ã‚Â· prepared {batch.performed_at} Ã‚Â· {batch.timezone_name}. {batch.note}</p><ul>{batch.inputs.map((x,i)=><li key={x.recipe_line_id}>Ingredient {i+1}: {x.quantity} {x.source_unit} Ã‚Â· {x.measurement_basis}. {x.evidence} Ã‚Â· included loss {x.included_loss_quantity??"unknown"}{x.source_batch_id?` Ã‚Â· lot ${x.source_batch_id}`:""}</li>)}</ul></div>:null;}
