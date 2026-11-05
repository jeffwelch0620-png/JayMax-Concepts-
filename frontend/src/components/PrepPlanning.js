import React,{useEffect,useRef,useState} from "react";
import * as api from "../lib/api";
import {useRetainedDraft} from "../lib/saveIntegrity";
import {cardCls,inpCls,btnGhost,SectionLabel} from "./common";
import {BulkParMode} from "./BulkParMode";

const DAYS=["Mon","Tue","Wed","Thu","Fri","Sat","Sun"],noDailyPars=()=>DAYS.map(()=>"");
const blank={product:"",recipe_version_id:"",unit_profile_id:"",track:"daily",schedule:"daily",weekday_par:"0",weekend_par:"0",recur_days:[],fixed_quantity:"",daily_pars:noDailyPars(),note:"",verified:false,version:0,pending:null,entries:{}};
const fields=["recipe_version_id","unit_profile_id","track","schedule","weekday_par","weekend_par","recur_days","fixed_quantity","daily_pars"];
const storeId=rid=>rid==="papa_leonis"?"papa":rid;
const QUANTITY=/^\+?(?:\d+(?:\.\d*)?|\.\d+)$/;
// The server writes some decimals in exponent form ("1E-7"); spell them out exactly, without floating point.
export function plain(value){
  const m=/^\+?(\d+)(?:\.(\d*))?[eE]([+-]?\d+)$/.exec(String(value).trim());
  if(!m)return String(value).trim();
  const digits=m[1]+(m[2]||""),point=m[1].length+Number(m[3]);
  return point<=0?`0.${"0".repeat(-point)}${digits}`:point>=digits.length?digits+"0".repeat(point-digits.length):`${digits.slice(0,point)}.${digits.slice(point)}`;
}
const decimal=value=>plain(value).replace(/^\+/,"").replace(/^\./,"0.").replace(/^0+(?=\d)/,"").replace(/(\.\d*?)0+$/, "$1").replace(/\.$/,"");
const sameList=(a,b)=>(a??null)===null||(b??null)===null?(a??null)===(b??null):a.length===b.length&&a.every((v,n)=>decimal(v)===decimal(b[n]));
const equal=(a,b,k)=>k==="recur_days"?JSON.stringify(a)===JSON.stringify(b):k==="daily_pars"?sameList(a,b):["weekday_par","weekend_par","fixed_quantity"].includes(k)?(a==null||b==null?a===b:decimal(a)===decimal(b)):a===b;
// Exact decimal sum of plain decimal strings (no floating point), for showing a run's daily-par target.
export function sumDecimals(values){
  const parts=values.map(v=>decimal(v).split(".")),scale=Math.max(0,...parts.map(([,f=""])=>f.length));
  const total=parts.reduce((s,[i,f=""])=>s+BigInt(i+f.padEnd(scale,"0")),0n).toString().padStart(scale+1,"0");
  return decimal(scale?`${total.slice(0,-scale)}.${total.slice(-scale)}`:total);
}
// Each Bulk run covers these days (Monday first): backend/prep_day_tasks.py BULK_RUN_DAYS.
const RUNS=[["Monday run (Mon to Wed)",[0,1,2]],["Thursday run (Thu to Sun)",[3,4,5,6]]];
const bulkToPar=d=>d.track==="bulk"&&d.schedule==="daily";
function editing(plan,product){
  const quantities=plan?{weekday_par:plain(plan.weekday_par??""),weekend_par:plain(plan.weekend_par??""),fixed_quantity:plan.fixed_quantity==null?"":plain(plan.fixed_quantity)}:{};
  return {...blank,product,...(plan?Object.fromEntries(fields.map(k=>[k,plan[k]??""])):{}),...quantities,note:"",daily_pars:plan?.daily_pars?plan.daily_pars.map(plain):noDailyPars(),version:plan?.revision||0,verified:false};
}
export function PrepPlanning(props){return <PlanningForm key={props.rid} {...props}/>;}
function PlanningForm({rid,drafts,showToast=()=>{}}){
  const [data,setData]=useState(null),[error,setError]=useState(""),[busy,setBusy]=useState(false),[reading,setReading]=useState(false),[parMode,setParMode]=useState(null);
  const [draft,setDraft]=useRetainedDraft(`prep-planning:${rid}`,blank,drafts);
  const epoch=useRef(0),readSequence=useRef(0);
  useEffect(()=>{const id=++epoch.current;load(id);return()=>{epoch.current++;};},[]); // eslint-disable-line react-hooks/exhaustive-deps
  async function load(id=epoch.current,rebase=false){
    const sequence=++readSequence.current;setReading(true);
    try{
      const result=await api.prepPlanning(rid);
      if(epoch.current!==id||sequence!==readSequence.current)return;
      if(result?.store_id!==storeId(rid)||!["products","recipes","unitProfiles","plans","legacy_sources"].every(k=>Array.isArray(result[k]))||result.plans.some(p=>p.store_id!==storeId(rid)||!p.product_id||!Number.isSafeInteger(p.revision)||p.revision<1))throw new Error("Prep planning read was not confirmed.");
      setData(result);
      if(rebase)setDraft(previous=>({...previous,version:result.plans.find(p=>p.product_id===previous.product)?.revision||0}));
      setError(rebase?"Version refreshed. Compare your retained entries with the saved plan and verify them before saving.":"");
      if(rebase)setDraft(previous=>({...previous,verified:false}));
    }catch(e){if(epoch.current===id&&sequence===readSequence.current)setError(e?.response?.data?.detail||e.message||"Prep planning read failed.");}
    finally{if(epoch.current===id&&sequence===readSequence.current)setReading(false);}
  }
  function choose(product){
    setDraft(previous=>{const {entries,...entry}=previous,retained={...entries,...(previous.product?{[previous.product]:entry}:{})};
      return {...(retained[product]||editing(data.plans.find(p=>p.product_id===product),product)),entries:retained};});setError("");
  }
  function change(key,value){setDraft(previous=>({...previous,[key]:value,verified:false}));}
  async function save(action="save"){
    if(busy||reading)return;
    const id=epoch.current;let submitted=draft.pending;
    if(!submitted){
      if(!draft.product||!draft.note.trim()){setError("Choose a prepared product and record the reason for this change.");return;}
      if(action==="save"&&(!draft.verified||!draft.recipe_version_id||!draft.unit_profile_id)){setError("Select a reviewed recipe and verified unit, and confirm the planning values.");return;}
      if(action==="save"&&[draft.weekday_par,draft.weekend_par,...(draft.schedule==="recurring"?[draft.fixed_quantity]:[])].some(value=>!QUANTITY.test(String(value).trim()))){setError("Enter quantities as nonnegative decimal numbers in the selected unit.");return;}
      // Daily pars only belong to a to-par Bulk item: all seven or none, and required once the store uses daily pars.
      const daily=bulkToPar(draft)?draft.daily_pars.map(v=>String(v).trim()):[],anyDaily=daily.some(v=>v!=="");
      if(action==="save"&&(anyDaily||(bulkToPar(draft)&&parMode==="daily"))&&daily.some(v=>!QUANTITY.test(v))){setError(parMode==="daily"?"This store uses daily Bulk pars; enter a par for each day, Monday to Sunday (zero is allowed).":"Enter all seven daily pars, Monday to Sunday (zero is allowed), or leave all seven blank.");return;}
      const body=action==="retire"?{action,note:draft.note.trim()}:{action,...Object.fromEntries(fields.map(k=>[k,draft[k]])),weekday_par:String(draft.weekday_par).trim(),weekend_par:String(draft.weekend_par).trim(),recur_days:[...draft.recur_days].sort((a,b)=>a-b),fixed_quantity:draft.schedule==="recurring"?String(draft.fixed_quantity).trim():null,daily_pars:anyDaily?daily:null,note:draft.note.trim(),verified:true};
      submitted={key:window.crypto.randomUUID(),product:draft.product,version:draft.version,body,prior:data.plans.find(p=>p.product_id===draft.product)};
      setDraft(previous=>({...previous,pending:submitted}));
    }
    setBusy(true);setError("");
    try{
      const response=await api.savePrepPlan(rid,submitted.product,submitted.body,submitted.version,submitted.key);
      if(epoch.current!==id)return;
      const saved=response?.plan,current=response?.current_plan,expected=submitted.body.action==="save"?submitted.body:submitted.prior;
      if(response.request_key!==submitted.key||saved?.store_id!==storeId(rid)||saved.product_id!==submitted.product||saved.revision!==submitted.version+1||!saved.id||saved.active!==(submitted.body.action==="save")||saved.note!==submitted.body.note||!expected||fields.some(k=>!equal(saved[k],expected[k],k))||current?.store_id!==storeId(rid)||current.product_id!==submitted.product||!Number.isSafeInteger(current.revision)||current.revision<saved.revision||!current.id||typeof current.active!=="boolean"||(current.revision===saved.revision&&(current.id!==saved.id||current.active!==saved.active||fields.some(k=>!equal(current[k],saved[k],k)))))throw new Error("Prep planning save was not confirmed. The exact request is retained for retry.");
      setData(previous=>({...previous,plans:[...previous.plans.filter(p=>p.product_id!==current.product_id),current]}));
      setDraft(previous=>previous.pending?.key===submitted.key?{...editing(current,submitted.product),entries:previous.entries}:previous);
      showToast(response.replayed?"Prep planning save confirmed; current saved plan displayed.":"Prep planning saved.");
    }catch(e){if(epoch.current!==id)return;setError(e?.response?.data?.detail||e.message||"Prep planning save was not confirmed.");if([400,403,404,409,422,428].includes(e?.response?.status))setDraft(previous=>({...previous,pending:null,verified:false}));}
    finally{if(epoch.current===id)setBusy(false);}
  }
  const locked=busy||reading||!!draft.pending,plan=data?.plans.find(p=>p.product_id===draft.product),recipe=data?.recipes.find(r=>r.id===draft.recipe_version_id);
  return <div className={`${cardCls} p-4 mb-6`}>
    <SectionLabel>Prep Planning Settings</SectionLabel>
    <p>Track 2 planning uses reviewed prep units. Task execution is awaiting its next workflow step. Purchased inventory and Food Cost stay unchanged.</p>
    {error&&<p role="alert">{error}</p>}
    {!data?<p>Planning settings awaiting a confirmed read.</p>:<>
      <BulkParMode rid={rid} drafts={drafts} showToast={showToast} onMode={setParMode} plans={data.plans.map(p=>p.id).sort().join(",")}/>
      <label>Prepared product<select aria-label="Planning product" className={inpCls} value={draft.product} disabled={locked} onChange={e=>choose(e.target.value)}><option value="">Choose prepared product</option>{data.products.map(p=><option key={p.product_id} value={p.product_id}>{p.name}</option>)}</select></label>
      {draft.product&&<>
        <p>Saved version {plan?.revision||0}: {plan?plan.active?"active":"retired":"no plan"}. Saved weekday / weekend par: {plan?`${plan.weekday_par} / ${plan.weekend_par}`:"none"}.{plan?.daily_pars?` Saved daily pars (Mon to Sun): ${plan.daily_pars.map(plain).join(", ")}.`:""}{plan?.reviewNeeded?" Definition changed; planning needs review.":""}</p>
        <fieldset disabled={locked}>
          <label>Recipe<select aria-label="Planning recipe" className={inpCls} value={draft.recipe_version_id} onChange={e=>{change("recipe_version_id",e.target.value);change("unit_profile_id","");}}><option value="">Choose reviewed recipe</option>{data.recipes.filter(r=>r.product_id===draft.product).map(r=><option key={r.id} value={r.id} disabled={r.reviewNeeded}>Recipe version {r.revision}{r.reviewNeeded?" (review required)":""}</option>)}</select></label>
          <label>Quantity unit<select aria-label="Planning unit" className={inpCls} value={draft.unit_profile_id} onChange={e=>change("unit_profile_id",e.target.value)}><option value="">Choose verified unit</option>{data.unitProfiles.filter(p=>p.product_version_id===recipe?.product_version_id).map(p=><option key={p.id} value={p.id}>{p.source_unit} ({p.base_units_per_source_unit} base units)</option>)}</select></label>
          <label>Planning track<select aria-label="Planning track" className={inpCls} value={draft.track} onChange={e=>change("track",e.target.value)}><option value="daily">Daily</option><option value="bulk">Bulk</option>{rid==="berts"&&<option value="salad">Salad Bar</option>}</select></label>
          <label>Schedule<select aria-label="Planning schedule" className={inpCls} value={draft.schedule} onChange={e=>{change("schedule",e.target.value);change("recur_days",[]);change("fixed_quantity","");}}><option value="daily">Daily to par</option><option value="recurring">Recurring fixed quantity</option><option value="on_demand">On demand</option></select></label>
          {["weekday_par","weekend_par"].map(k=><label key={k}>{k==="weekday_par"?"Weekday par":"Weekend par"}<input aria-label={k==="weekday_par"?"Planning weekday par":"Planning weekend par"} className={inpCls} inputMode="decimal" value={draft[k]} onChange={e=>change(k,e.target.value)}/></label>)}
          {bulkToPar(draft)&&<div aria-label="Planning daily pars">
            <p>Daily pars, Monday to Sunday, in the selected unit. {parMode==="daily"?"This store uses daily pars, so all seven are required.":"Used once this store switches to daily pars; leave blank until then if you like."} Enter each day fresh rather than splitting the weekday or weekend par.</p>
            {DAYS.map((day,n)=><label key={day}>{day}<input aria-label={`Planning daily par ${day}`} className={inpCls} inputMode="decimal" value={draft.daily_pars[n]} onChange={e=>change("daily_pars",draft.daily_pars.map((v,m)=>m===n?e.target.value:v))}/></label>)}
            {draft.daily_pars.every(v=>QUANTITY.test(String(v).trim()))&&<p>{RUNS.map(([label,days])=>`${label}: ${sumDecimals(days.map(d=>String(draft.daily_pars[d]).trim()))}`).join("; ")}.</p>}
          </div>}
          {draft.schedule==="recurring"&&<><p>Recurring days (Monday through Sunday):</p>{["Mon","Tue","Wed","Thu","Fri","Sat","Sun"].map((day,n)=><label key={day}><input type="checkbox" aria-label={`Planning ${day}`} checked={draft.recur_days.includes(n)} onChange={()=>change("recur_days",draft.recur_days.includes(n)?draft.recur_days.filter(d=>d!==n):[...draft.recur_days,n].sort())}/>{day}</label>)}<label>Fixed quantity<input aria-label="Planning fixed quantity" className={inpCls} value={draft.fixed_quantity} onChange={e=>change("fixed_quantity",e.target.value)}/></label></>}
          <label>Reason<textarea aria-label="Planning edit reason" className={inpCls} value={draft.note} onChange={e=>change("note",e.target.value)}/></label>
          <label><input type="checkbox" aria-label="Verify planning values" checked={draft.verified} onChange={e=>setDraft(previous=>({...previous,verified:e.target.checked}))}/>I reviewed these quantities in the selected verified unit.</label>
        </fieldset>
        <button className={btnGhost} disabled={busy||reading||(!draft.pending&&recipe?.reviewNeeded)} onClick={()=>save()}>{draft.pending?"Retry the same planning save":"Save reviewed plan"}</button>
        {plan?.active&&!draft.pending&&<button className={btnGhost} disabled={locked} onClick={()=>save("retire")}>Retire plan with history</button>}
      </>}
      <button className={btnGhost} disabled={locked} onClick={()=>load(epoch.current,true)}>Refresh planning versions</button>
      {!!data.legacy_sources.length&&<details><summary>{data.legacy_sources.length} retained legacy standing prep record(s)</summary><p>All original fields are preserved. Container capacities and old pars have not been adopted automatically.</p><pre className="overflow-auto">{JSON.stringify(data.legacy_sources,null,2)}</pre></details>}
    </>}
  </div>;
}
