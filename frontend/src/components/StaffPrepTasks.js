import React,{useEffect,useRef,useState} from "react";
import * as api from "../lib/api";
import {useRetainedDraft} from "../lib/saveIntegrity";
import {todayISO} from "../lib/calc";
import {cardCls,inpCls,btnGhost} from "./common";
import {StaffProductionSubmission} from "./StaffPrepProduction";
const storeId=rid=>rid==="papa_leonis"?"papa":rid;
const uid=v=>typeof v==="string"&&/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(v);
const ordered=v=>Array.isArray(v)?v.map(ordered):v&&typeof v==="object"?Object.fromEntries(Object.keys(v).sort().map(k=>[k,ordered(v[k])])):v;
const same=(a,b)=>JSON.stringify(ordered(a))===JSON.stringify(ordered(b));
const errorText=e=>typeof e?.response?.data?.detail==="string"?e.response.data.detail:e.message||"Prep task read or save was not confirmed.";
const blank=()=>({task_id:"",staff_member_id:"",note:"",review:null,confirmed:false,pending:null,rejected:false});
const validHistory=(rows,task,store)=>Array.isArray(rows)&&rows.every((h,i)=>uid(h.id)&&h.store_id===store&&h.task_id===task&&h.revision===i+1&&h.predecessor_id===(i?rows[i-1].id:null));
export function validAssignmentState(s,rid,day,track){
  const store=storeId(rid),e=s?.execution;
  return s?.store_id===store&&s.day===day&&s.track===track&&e?.store_id===store&&e.prep_date===day&&e.track===track
    &&["draft","released"].includes(e.status)&&Number.isSafeInteger(e.revision)&&e.revision>=0
    &&Array.isArray(e.tasks)&&Array.isArray(e.task_progress)&&Array.isArray(s.members)&&Array.isArray(s.assignments)
    &&s.members.every(m=>uid(m.id)&&m.store_id===store&&typeof m.name==="string"&&typeof m.active==="boolean")
    &&s.assignments.length===e.tasks.length&&new Set(s.assignments.map(a=>a.task_id)).size===s.assignments.length
    &&s.assignments.every(a=>e.tasks.some(t=>t.id===a.task_id)&&Array.isArray(a.history)&&typeof a.roster_changed==="boolean"
      &&validHistory(a.history,a.task_id,store)
      &&same(a.current,a.history.at(-1)||null)&&(!a.current_member||(a.current_member.id===a.current?.staff_member_id&&s.members.some(m=>same(m,a.current_member)))));
}
export function validAssignmentAck(ack,pending,rid,day,track){
  const a=ack?.assignment,p=pending.review.review,b=p.assignment;
  return uid(a?.id)&&a.store_id===storeId(rid)&&a.task_id===b.task_id&&a.staff_member_id===b.staff_member_id
    &&a.note===b.note&&a.revision===b.expected_revision+1&&a.predecessor_id===p.predecessor_id
    &&a.request_key===pending.key&&a.review_hash===pending.body.expected_review_hash&&same(a.review_snapshot,p)
    &&validHistory(ack.assignment_history,a.task_id,storeId(rid))&&ack.assignment_history.some(h=>same(h,a))&&validAssignmentState(ack.current,rid,day,track);
}
export function StaffPrepAssignments(props){return <AssignmentForm key={`${props.rid}:${props.day}:${props.track}`} {...props}/>;}
function AssignmentForm({rid,day,track,drafts}){
  const privateCache=useRef(new Map()),cache=drafts||privateCache.current,key=`prep-assign:${rid}:${day}:${track}`;
  const [draft,edit,clear]=useRetainedDraft(key,blank(),cache);
  const [data,setData]=useState(null),[busy,setBusy]=useState(false),[error,setError]=useState(""),[message,setMessage]=useState("");
  const epoch=useRef(0),sequence=useRef(0),frozen=busy||!!draft.pending;
  async function refresh(){const id=epoch.current,seq=++sequence.current;
    try{const s=await api.staffPrepTaskSetup(rid,day,track);if(id!==epoch.current||seq!==sequence.current)return;
      if(!validAssignmentState(s,rid,day,track))throw new Error("Assignment readback is incomplete or belongs to another plan.");setData(s);setError("");
    }catch(e){if(id===epoch.current&&seq===sequence.current){setData(null);setError(errorText(e));}}
  }
  useEffect(()=>{++epoch.current;refresh();return()=>{++epoch.current;++sequence.current;};},[]); // eslint-disable-line react-hooks/exhaustive-deps
  const set=(k,v)=>{edit(d=>({...d,[k]:v,review:null,confirmed:false}));setMessage("");};
  async function preview(){const id=epoch.current;setBusy(true);setError("");
    try{const current=data.assignments.find(a=>a.task_id===draft.task_id)?.current;
      const body={task_id:draft.task_id,staff_member_id:draft.staff_member_id||null,expected_revision:current?.revision||0,note:draft.note.trim()};
      const p=await api.previewStaffPrepAssignment(rid,day,track,body);if(id!==epoch.current)return;
      if(!/^[a-f0-9]{64}$/.test(p?.reviewHash)||p.review?.store_id!==storeId(rid)||p.review.day!==day||p.review.track!==track
        ||!same(p.review.assignment,body)||p.review.task?.id!==body.task_id||p.review.accountingEffect!=="none"||p.review.productionEffect!=="none"
        ||(body.staff_member_id?p.review.member?.id!==body.staff_member_id:p.review.member!==null))throw new Error("Assignment preview did not match the selected task and staff.");
      edit(d=>({...d,review:p,confirmed:false}));
    }catch(e){if(id===epoch.current)setError(errorText(e));}finally{if(id===epoch.current)setBusy(false);}
  }
  async function save(){if(!draft.pending&&(!draft.review||!draft.confirmed))return;const id=epoch.current;
    const pending=draft.pending||{key:crypto.randomUUID(),body:{assignment:draft.review.review.assignment,expected_review_hash:draft.review.reviewHash,reviewed:true},review:draft.review};
    const submitted={...draft,pending,rejected:false};edit(submitted);setBusy(true);setError("");
    try{const ack=await api.saveStaffPrepAssignment(rid,day,track,pending.body,pending.key);if(id!==epoch.current||!cache.has(key))return;
      if(!validAssignmentAck(ack,pending,rid,day,track))throw new Error("Assignment save was not confirmed. Retry the same request.");
      ++sequence.current;if(clear(submitted,blank())){setData(ack.current);setMessage("Assignment saved and confirmed. Production and Food Cost are unchanged.");}
    }catch(e){if(id===epoch.current&&cache.has(key)){setError(errorText(e));if([409,422].includes(e?.response?.status))edit(d=>({...d,rejected:true}));}}
    finally{if(id===epoch.current)setBusy(false);}
  }
  return <section className={`${cardCls} p-3`} aria-label="Prep staff assignments"><h3>Staff assignments</h3>
    <p>Assign the released dated task to an active roster identity. Staff names and shared PIN access do not grant manager permissions.</p>
    {error&&<p role="alert">{error}</p>}{message&&<p role="status">{message}</p>}
    <button className={btnGhost} disabled={frozen} onClick={refresh}>Refresh staff assignments</button>
    {data&&<><p>{day} · {track} · {data.execution.status}</p><ul>{data.assignments.map(a=><li key={a.task_id}>{data.execution.tasks.find(t=>t.id===a.task_id)?.task_snapshot?.name}: {a.current_member?.name||"Unassigned"}{a.roster_changed?" · roster changed; review assignment":""} · assignment revision {a.current?.revision||0}</li>)}</ul>
    <fieldset disabled={frozen||data.execution.status!=="released"}>
      <label>Prep assignment task<select className={inpCls} aria-label="Prep assignment task" value={draft.task_id} onChange={e=>set("task_id",e.target.value)}><option value="">Select task</option>{data.execution.tasks.filter(t=>t.included&&t.planned_quantity!==null&&Number(t.planned_quantity)>0).map(t=><option key={t.id} value={t.id}>{t.task_snapshot.name} · {t.planned_quantity} {t.task_snapshot.source_unit}</option>)}</select></label>
      <label>Assigned staff<select className={inpCls} aria-label="Assigned staff" value={draft.staff_member_id} onChange={e=>set("staff_member_id",e.target.value)}><option value="">Remove current assignment</option>{data.members.filter(m=>m.active).map(m=><option key={m.id} value={m.id}>{m.name}</option>)}</select></label>
      <label>Assignment reason<input className={inpCls} aria-label="Assignment reason" value={draft.note} onChange={e=>set("note",e.target.value)}/></label>
      <button className={btnGhost} onClick={preview}>Review staff assignment</button>
    </fieldset></>}
    {draft.review&&<article aria-label="Staff assignment review"><p>{draft.review.review.task.task_snapshot.name} → {draft.review.review.member?.name||"Unassigned"} · {day} · {track}. {draft.review.review.assignment.note}</p>
      <label><input type="checkbox" aria-label="Confirm staff assignment" disabled={frozen} checked={draft.confirmed} onChange={e=>edit(d=>({...d,confirmed:e.target.checked}))}/> I reviewed the task, staff identity and assignment history.</label>
      <button className={btnGhost} disabled={busy||(!draft.pending&&!draft.confirmed)} onClick={save}>{draft.pending?"Retry same staff assignment":"Save reviewed staff assignment"}</button></article>}
    {draft.pending&&draft.rejected&&<button className={btnGhost} disabled={busy} onClick={()=>{edit(d=>({...d,pending:null,review:null,confirmed:false,rejected:false}));refresh();}}>Revise rejected staff assignment</button>}
  </section>;
}
export function StaffPrepTaskPlan({rid,pin,staffId,track,drafts}){
  const [day,setDay]=useState(todayISO()),[mine,setMine]=useState(false),[data,setData]=useState(null),[error,setError]=useState("");
  const epoch=useRef(0),seq=useRef(0);
  async function load(){const id=epoch.current,n=++seq.current;setData(null);setError("");const member=mine?(staffId||null):null;
    try{const s=await api.staffPrepTaskPlan(rid,{pin,day,track,staff_member_id:member});if(id!==epoch.current||n!==seq.current)return;
      if(s?.store_id!==storeId(rid)||s.day!==day||s.track!==track||s.selected_member_id!==member||s.identity_verified!==false
        ||!["draft","released"].includes(s.status)||!Array.isArray(s.tasks)||new Set(s.tasks.map(t=>t.id)).size!==s.tasks.length
        ||(s.status!=="released"&&s.tasks.length)||s.tasks.some(t=>!uid(t.id)||typeof t.name!=="string"||!/^\d+(\.\d+)?$/.test(t.quantity)||Number(t.quantity)<=0||typeof t.source_unit!=="string"||t.progress?.task_id!==t.id
        ||typeof t.base_unit!=="string"||typeof t.progress.reviewed_base_quantity!=="string"||!/^\d+(\.\d+)?$/.test(t.progress.reviewed_base_quantity)
        ||!["open","in_progress","complete","needs_review"].includes(t.progress.status)||(member&&t.assigned_member?.id!==member)))throw new Error("Staff prep plan was not confirmed for this date and location.");
      setData(s);
    }catch(e){if(id===epoch.current&&n===seq.current)setError(errorText(e));}
  }
  useEffect(()=>{++epoch.current;load();return()=>{++epoch.current;++seq.current;};},[rid,day,track,pin,staffId,mine]); // eslint-disable-line react-hooks/exhaustive-deps
  return <section className={`${cardCls} p-4`} aria-label="Released staff prep plan"><h3>Released prep plan</h3>
    <p>Choose the location calendar date. Planned quantities are expected output. A manager records measured production and reviews completion.</p>
    <label>Staff prep date<input className={inpCls} type="date" aria-label="Staff prep date" value={day} onChange={e=>setDay(e.target.value)}/></label>
    {staffId&&<label><input type="checkbox" aria-label="Show my roster assignments" checked={mine} onChange={e=>setMine(e.target.checked)}/> Show assignments for my selected roster name (claimed identity)</label>}
    <button className={btnGhost} onClick={load}>Refresh released prep plan</button>{error&&<p role="alert">{error}</p>}
    {data&&<><p>{data.day} · {data.track} · {data.status}</p>{data.tasks.length===0&&<p>{data.status==="released"?"No included tasks for this selection.":"No released plan for this selected date."}</p>}
      <ul>{data.tasks.map(t=><li key={t.id}>{t.name}: {t.quantity} {t.source_unit} planned · {t.assigned_member?.name||"Unassigned"} · {t.progress.status}{t.roster_changed?" · assignment needs roster review":""}<p>Task {t.id} · measured reviewed output {t.progress.reviewed_base_quantity} {t.base_unit}.</p></li>)}</ul></>}
    {api.staffPrepProductionEnabled&&staffId&&data&&<StaffProductionSubmission rid={rid} day={day} track={track} staffId={staffId} pin={pin} plan={data} drafts={drafts}/>}
  </section>;
}
