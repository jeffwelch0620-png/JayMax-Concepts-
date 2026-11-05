import React,{useEffect,useRef,useState} from "react";
import * as api from "../lib/api";
import {useRetainedDraft} from "../lib/saveIntegrity";
import {inpCls,btnGhost} from "./common";

// M2 Bulk daily pars (Jeff 2026-11-04): each store chooses window pars (Monday run = weekday par,
// Thursday run = weekend par) or daily pars (a run adds up the daily pars for the days it covers).
// Only an owner or admin can switch; the server enforces it and refuses daily mode until every
// active to-par Bulk item has its seven daily pars.
export const MODE_TEXT={window:"Weekday / weekend pars: the Monday run uses the weekday par, the Thursday run the weekend par.",
  daily:"Daily pars: the Monday run adds up Monday to Wednesday, the Thursday run Thursday to Sunday."};
const storeId=rid=>rid==="papa_leonis"?"papa":rid;
const blank={note:"",pending:null};
export function BulkParMode(props){return <ModePanel key={props.rid} {...props}/>;}
// plans: the saved plan ids, so the list of items still missing daily pars refreshes after a plan save.
function ModePanel({rid,drafts,plans="",onMode=()=>{},showToast=()=>{}}){
  const [data,setData]=useState(null),[error,setError]=useState(""),[busy,setBusy]=useState(false);
  const [draft,setDraft]=useRetainedDraft(`bulk-par-mode:${rid}`,blank,drafts);
  const epoch=useRef(0),readSequence=useRef(0);
  useEffect(()=>{epoch.current++;return()=>{epoch.current++;};},[]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(()=>{load(epoch.current);},[plans]); // eslint-disable-line react-hooks/exhaustive-deps
  async function load(id){
    const sequence=++readSequence.current;
    try{
      const result=await api.bulkParMode(rid);
      if(epoch.current!==id||sequence!==readSequence.current)return;
      if(result?.store_id!==storeId(rid)||!["window","daily"].includes(result.mode)||!Number.isSafeInteger(result.revision)||!Array.isArray(result.history)||!Array.isArray(result.missing_daily_pars))throw new Error("Bulk par mode read was not confirmed.");
      setData(result);onMode(result.mode);setError("");
    }catch(e){if(epoch.current===id&&sequence===readSequence.current)setError(e?.response?.data?.detail||e.message||"Bulk par mode read failed.");}
  }
  async function change(){
    if(busy||!data)return;
    const id=epoch.current;let submitted=draft.pending;
    if(!submitted){
      if(!draft.note.trim()){setError("Record the reason for switching Bulk pars.");return;}
      submitted={key:window.crypto.randomUUID(),version:data.revision,body:{mode:data.mode==="daily"?"window":"daily",note:draft.note.trim()}};
      setDraft(previous=>({...previous,pending:submitted}));
    }
    setBusy(true);setError("");
    try{
      const response=await api.saveBulkParMode(rid,submitted.body,submitted.version,submitted.key);
      if(epoch.current!==id)return;
      if(response?.request_key!==submitted.key||response.mode!==submitted.body.mode||!Number.isSafeInteger(response.revision)||response.revision<submitted.version+1||!Array.isArray(response.history))throw new Error("Bulk par mode switch was not confirmed. The exact request is retained for retry.");
      setDraft(previous=>previous.pending?.key===submitted.key?blank:previous);
      showToast(response.replayed?"Bulk par mode switch confirmed.":"Bulk par mode switched.");
      await load(id);
    }catch(e){if(epoch.current!==id)return;setError(e?.response?.data?.detail||e.message||"Bulk par mode switch was not confirmed.");if([400,403,404,409,422,428].includes(e?.response?.status))setDraft(previous=>({...previous,pending:null}));}
    finally{if(epoch.current===id)setBusy(false);}
  }
  if(!data)return <div aria-label="Bulk par mode"><p>{error||"Bulk par mode awaiting a confirmed read."}</p></div>;
  const toDaily=data.mode==="window",blocked=toDaily&&data.missing_daily_pars.length>0&&!draft.pending;
  return <div aria-label="Bulk par mode" className="mb-4">
    <p><strong>Bulk pars at this store:</strong> {MODE_TEXT[data.mode]} Bulk runs stay on Monday and Thursday either way.</p>
    {error&&<p role="alert">{error}</p>}
    {toDaily&&data.missing_daily_pars.length>0&&<p>Before switching to daily pars, enter daily pars for: {data.missing_daily_pars.join(", ")}.</p>}
    <label>Reason for switching<textarea aria-label="Bulk par mode reason" className={inpCls} value={draft.note} disabled={busy||!!draft.pending} onChange={e=>setDraft(previous=>({...previous,note:e.target.value}))}/></label>
    <button className={btnGhost} disabled={busy||blocked} onClick={change}>{draft.pending?"Retry the same Bulk par switch":toDaily?"Switch to daily pars":"Switch back to weekday / weekend pars"}</button>
    <p>Only an owner or admin can switch. Saved Bulk drafts for upcoming runs are flagged for review after a switch.</p>
    {!!data.history.length&&<details><summary>Switch history ({data.history.length})</summary><ul>{[...data.history].reverse().map(h=><li key={h.id}>Version {h.revision}: {h.mode==="daily"?"daily pars":"weekday / weekend pars"}, {h.recorded_at} by {h.actor}. {h.note}</li>)}</ul></details>}
  </div>;
}
