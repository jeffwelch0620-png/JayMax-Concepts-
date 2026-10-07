import React, { useEffect, useRef, useState } from "react";
import * as api from "../lib/api";
import { useRetainedDraft } from "../lib/saveIntegrity";
import { quantityText } from "./StaffPrepCounts";
import { Field, cardCls, inpCls, btnAcc, btnGhost } from "./common";

const uid = value => typeof value === "string" && /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(value);
const hash = value => typeof value === "string" && /^[0-9a-f]{64}$/.test(value);
const SCALE = 10n ** 48n;
const fixed = value => {
  if (typeof value !== "string" || !/^-?\d{1,96}(\.\d{1,48})?([eE][+-]?\d{1,2})?$/.test(value)) throw new Error("Invalid exact quantity");
  const negative = value.startsWith("-"),[coefficient,exponent="0"]=value.replace(/^-/ ,"").split(/[eE]/),[whole,fraction=""]=coefficient.split(".");
  const digits=BigInt(whole+fraction),shift=48+Number(exponent)-fraction.length;
  const divisor=shift<0?10n**BigInt(-shift):1n;
  if(digits%divisor!==0n)throw new Error("Quantity exceeds supported exact precision");
  const result=shift>=0?digits*10n**BigInt(shift):digits/divisor;
  return negative ? -result : result;
};
const canonical = value => Array.isArray(value) ? value.map(canonical) : value && typeof value === "object" ? Object.fromEntries(Object.keys(value).sort().map(k => [k, canonical(value[k])])) : value;
const same = (a,b) => JSON.stringify(canonical(a)) === JSON.stringify(canonical(b));
const numeric = new Set(["quantity","factor","base_quantity","usable_quantity","usable_base_quantity","storage_delta","service_delta","stated_capacity","brimful_capacity","usable_capacity"]);
function equalField(key, a, b) {
  if (a === null || b === null) return a === b;
  if (numeric.has(key)) { try { return fixed(String(a)) === fixed(String(b)); } catch { return false; } }
  if (key === "performed_at") return Number.isFinite(Date.parse(a)) && Date.parse(a) === Date.parse(b);
  return same(a,b);
}
function matchingFacts(result, facts) {
  return Object.entries(facts).every(([key,value]) => equalField(key, result[key], key === "root_id" && value === null ? result.id : value));
}
function validWastePair(pair,move,fill,store,original=null) {
  try {
    const l=pair?.link,e=pair?.event,p=e?.review_snapshot;
    if (!uid(e?.id)||!uid(l?.command_id)||l.command_id!==move.command_id||l.move_id!==move.id||l.observation_id!==e.id||l.store_id!==store||e.store_id!==store
      ||e.purpose!=="waste"||e.product_id!==fill.product_id||e.source_batch_id!==fill.source_batch_id||e.base_unit!==fill.base_unit||e.raw_item_code!==null
      ||!hash(e.review_hash)||p?.container_fill_id!==fill.id||p.kind!==e.kind||p.purpose!==e.purpose||p.reason!==e.reason||e.reason!==move.note
      ||!equalField("performed_at",e.performed_at,move.performed_at)||e.business_date!==move.business_date||e.timezone_name!==move.timezone_name
      ||!["product_id","source_batch_id","base_unit","raw_item_code","performed_at","business_date","timezone_name","predecessor_id","revision"].every(k=>equalField(k,e[k],p[k]))
      ||!Array.isArray(p.movements)||p.movements.length!==1)return false;
    const m=p.movements[0],q=fixed(move.storage_delta)+fixed(move.service_delta);
    if(m.product_id!==fill.product_id||m.source_batch_id!==fill.source_batch_id||m.base_unit!==fill.base_unit||m.raw_item_code!==null||fixed(m.quantity)!==q)return false;
    if(move.action==="waste")return e.kind==="initial"&&e.predecessor_id===null&&e.root_id===e.id&&e.revision===1&&l.undo_of_command_id===null
      &&p.body?.measurement_basis==="measured"&&p.body.already_included_in_batch===false&&p.body.source_kind==="prepared"
      &&equalField("quantity",p.body.quantity,move.quantity)&&equalField("factor",p.factor,fill.factor)&&equalField("factor",p.body.factor,fill.factor)
      &&fixed(p.baseQuantity)===-q&&m.side==="apply"&&m.reverses_movement_id===null
      &&["storage_spoilage","service_discard","other"].includes(p.body.category)
      &&!(p.body.category==="storage_spoilage"&&move.compartment!=="storage")&&!(p.body.category==="service_discard"&&move.compartment!=="service");
    return e.kind==="void"&&original&&e.predecessor_id===original.event.id&&e.root_id===original.event.root_id&&e.revision===original.event.revision+1
      &&l.undo_of_command_id===original.link.command_id&&p.body===null&&m.side==="reverse"&&uid(m.reverses_movement_id);
  }catch{return false;}
}
export function validContainerState(state, store) {
  try {
    const f=state.fill;
    if (!uid(f.id) || f.store_id !== store || !uid(f.profile_id) || !uid(f.source_batch_id) || !Array.isArray(state.moves) || state.revision !== state.moves.length) return false;
    if (fixed(f.quantity) * fixed(f.factor) / SCALE !== fixed(f.base_quantity) || fixed(f.base_quantity) <= 0n) return false;
    let storage=fixed(f.base_quantity), service=0n;
    const ids=new Set(); let voided=false;
    for (const [i,m] of state.moves.entries()) {
      if (!uid(m.id) || ids.has(m.id) || m.fill_id !== f.id || m.store_id !== store || m.revision !== i+1 || voided) return false;
      ids.add(m.id); const ds=fixed(m.storage_delta),dv=fixed(m.service_delta);
      const q=m.quantity === null ? null : fixed(m.quantity) * fixed(f.factor) / SCALE;
      if (m.action === "send" && !(q>0n && ds === -q && dv === q)) return false;
      else if (m.action === "return" && !(q>0n && ds === q && dv === -q)) return false;
      else if (m.action === "unpack" && !(q>0n && ds === -q && dv === 0n)) return false;
      else if (m.action === "waste") {
        if (!(q>0n)||!(m.compartment==="storage"?ds===-q&&dv===0n:m.compartment==="service"&&ds===0n&&dv===-q))return false;
      }
      else if (m.action === "void_fill") { if (i !== 0 || ds !== -fixed(f.base_quantity) || dv !== 0n || q !== null) return false; voided=true; }
      else if (m.action === "undo") {
        const prior=state.moves[i-1]; if (!prior || prior.id !== m.target_move_id || !["send","return","unpack"].includes(prior.action) || ds !== -fixed(prior.storage_delta) || dv !== -fixed(prior.service_delta) || q !== null) return false;
      } else if (m.action === "undo_waste") {
        const prior=state.moves[i-1];if(!prior||prior.id!==m.target_move_id||prior.action!=="waste"||m.compartment!==prior.compartment||ds!==-fixed(prior.storage_delta)||dv!==-fixed(prior.service_delta)||q!==null||!equalField("performed_at",m.performed_at,prior.performed_at))return false;
      } else if (!["send","return","unpack"].includes(m.action)) return false;
      storage+=ds;service+=dv;if(storage<0n || service<0n)return false;
    }
    const losses=state.moves.filter(m=>["waste","undo_waste"].includes(m.action)),history=state.waste_history||[];
    if(!Array.isArray(history)||history.length!==losses.length||new Set(history.map(p=>p.link?.move_id)).size!==losses.length
      ||losses.some((m,i)=>history[i]?.link?.move_id!==m.id||!validWastePair(history[i],m,f,store,m.action==="undo_waste"?history.find(p=>p.link?.move_id===m.target_move_id):null)))return false;
    return fixed(state.storage)===storage && fixed(state.service)===service && fixed(state.allocated)===storage+service && state.voided===voided;
  } catch { return false; }
}
export function validContainerAck(ack, pending, store) {
  const c=ack?.command,r=ack?.result,p=pending?.review?.review;
  if (!p || !uid(c?.id) || !uid(r?.id) || c.store_id !== store || r.store_id !== store || c.result_id !== r.id || r.command_id !== c.id
    || c.request_key !== pending.key || c.action !== p.action || c.review_hash !== pending.body.expected_review_hash || !same(c.review_snapshot,p) || !matchingFacts(r,p.facts)) return false;
  if(["waste","undo_waste"].includes(p.action)) {
    const l=ack.waste_link,e=ack.waste_event;
    if(!hash(c.request_fingerprint)||typeof c.recorded_by!=="string"||!c.recorded_by.trim()||!hash(p.wasteReviewHash)||e?.review_hash!==p.wasteReviewHash||!same(e.review_snapshot,p.waste)||e.request_key!==c.request_key||e.request_fingerprint!==c.request_fingerprint||e.recorded_by!==c.recorded_by
      ||!same(ack.current?.waste_history?.slice(0,(p.sources.before.waste_history||[]).length),p.sources.before.waste_history||[])
      ||l?.command_id!==c.id||l.move_id!==r.id||l.observation_id!==e.id||!ack.current?.waste_history?.some(x=>same(x.link,l)&&same(x.event,e)))return false;
  }
  if (p.table === "container_fills") return validContainerState(ack.current,store) && same(ack.current.fill,r);
  if (p.table === "container_moves") return validContainerState(ack.current,store) && ack.current.fill.id === r.fill_id && same(ack.current.fill,p.sources.before.fill)
    && same(ack.current.moves.slice(0,p.sources.before.moves.length),p.sources.before.moves) && ack.current.moves.some(m => same(m,r));
  return ack.current === null;
}
export function validContainerWasteReview(p,body,store) {
  try {
    const s=p.sources.before,f=s.fill,m=p.facts,w=p.waste,stub="00000000-0000-4000-8000-000000000000";
    if(!validContainerState(s,store)||f.id!==body.fill_id||m.fill_id!==body.fill_id||m.action!==body.action||m.revision!==s.revision+1
      ||!["performed_at","business_date","timezone_name","note"].every(k=>equalField(k,m[k],body[k])))return false;
    const original=body.action==="undo_waste"?s.waste_history?.find(x=>x.link.move_id===body.target_move_id):null;
    if(body.action==="undo_waste"&&(s.moves.at(-1)?.id!==body.target_move_id||s.moves.at(-1)?.action!=="waste"||m.target_move_id!==body.target_move_id))return false;
    const event={...w,id:stub,root_id:w.kind==="initial"?stub:w.root_id,store_id:store,review_snapshot:w,review_hash:p.wasteReviewHash};
    const move={...m,id:stub,command_id:stub},link={command_id:stub,move_id:stub,observation_id:stub,store_id:store,undo_of_command_id:body.action==="waste"?null:original?.link.command_id};
    return validWastePair({event,link},move,f,store,original)
      &&(body.action==="waste"?m.compartment===body.compartment&&equalField("quantity",m.quantity,body.quantity):m.compartment===s.moves.at(-1).compartment)
      &&fixed(p.sources.after.storage)===fixed(s.storage)+fixed(m.storage_delta)&&fixed(p.sources.after.service)===fixed(s.service)+fixed(m.service_delta)
      &&fixed(p.sources.after.storage)>=0n&&fixed(p.sources.after.service)>=0n;
  }catch{return false;}
}
const errorText = e => typeof e?.response?.data?.detail === "string" ? e.response.data.detail : e.message || "Container save was not confirmed; the draft is retained.";
const initial = () => ({ action:"definition", predecessor_id:"", name:"",capacity_unit:"l",stated_capacity:"",brimful_capacity:"",usable_capacity:"",evidence:"",
  definition_id:"",product_version_id:"",unit_profile_id:"",usable_quantity:"",profile_id:"",source_batch_id:"",label:"",quantity:"",fill_id:"",target_move_id:"",
  performed_at:"",business_date:"",timezone_name:"America/New_York",note:"",compartment:"storage",category:"storage_spoilage",confirmed:false,review:null,pending:null,rejected:false });

export function PrepContainers(props) { return <PrepContainerForm key={props.rid} {...props}/>; }
function PrepContainerForm({ rid, drafts }) {
  const privateCache=useRef(new Map()),cache=drafts || privateCache.current;
  const [draft,edit,clear] = useRetainedDraft(`prep-containers:${rid}`,initial(),cache);
  const [data,setData]=useState(null),[busy,setBusy]=useState(false),[error,setError]=useState(""),[message,setMessage]=useState("");
  const active=useRef(false),readSequence=useRef(0);
  const store=rid === "papa_leonis" ? "papa" : rid, frozen=busy || !!draft.pending;
  async function refresh() {
    const seq=++readSequence.current;
    try {
      const d=await api.prepContainers(rid);
      if (!active.current || seq!==readSequence.current) return;
      if (d.store_id!==store || ![d.definitions,d.profiles,d.products,d.units,d.lots,d.fills].every(Array.isArray) || d.fills.some(f=>!validContainerState(f,store))
        || d.lots.some(l=>{try{return fixed(l.remainingRecordedQuantity)<0n || fixed(l.containerStorage)<0n || fixed(l.containerService)<0n || fixed(l.totalRemainingRecordedQuantity)!==fixed(l.remainingRecordedQuantity)+fixed(l.containerStorage)+fixed(l.containerService);}catch{return true;}})) throw new Error("Container readback is incomplete or belongs to another location.");
      setData(d);
    } catch(e) { if(active.current && seq===readSequence.current)setError(errorText(e)); }
  }
  useEffect(()=> {active.current=true;refresh();return()=>{active.current=false;++readSequence.current;};},[rid]); // eslint-disable-line react-hooks/exhaustive-deps
  const set=(key,value)=>{edit(d=>({...d,[key]:value,review:null,confirmed:false}));setError("");setMessage("");};
  const selected=data?.fills.find(x=>x.fill.id===draft.fill_id);
  function body() {
    const qty=(key,optional=false)=>{
      if(optional && !draft[key].trim())return null;
      const text=quantityText(draft[key]);if(!text || fixed(text)<=0n)throw new Error("Enter a positive measured quantity with at most 12 decimal places.");return text;
    };
    const action=draft.action;
    if(action==="definition")return {action,predecessor_id:draft.predecessor_id||null,name:draft.name.trim(),capacity_unit:draft.capacity_unit,stated_capacity:qty("stated_capacity",true),brimful_capacity:qty("brimful_capacity",true),usable_capacity:qty("usable_capacity",true),evidence:draft.evidence.trim()};
    if(action==="profile")return {action,predecessor_id:draft.predecessor_id||null,definition_id:draft.definition_id,product_version_id:draft.product_version_id,unit_profile_id:draft.unit_profile_id,usable_quantity:qty("usable_quantity"),evidence:draft.evidence.trim(),product_fill_measured:true};
    if(!draft.confirmed)throw new Error("Confirm the measurement and location calendar day.");
    const stamp={performed_at:draft.performed_at.trim(),business_date:draft.business_date,timezone_name:draft.timezone_name.trim(),calendar_date_confirmed:true,note:draft.note.trim()};
    if(action==="fill")return {...stamp,action,profile_id:draft.profile_id,source_batch_id:draft.source_batch_id,label:draft.label.trim(),quantity:qty("quantity"),contents_measured:true};
    if(action==="waste")return {...stamp,action,fill_id:draft.fill_id,quantity:qty("quantity"),compartment:draft.compartment,category:draft.category,contents_measured:true};
    return {...stamp,action,fill_id:draft.fill_id,quantity:["send","return","unpack"].includes(action)?qty("quantity"):null,target_move_id:["undo","undo_waste"].includes(action)?draft.target_move_id:null};
  }
  async function preview() {
    setBusy(true);setError("");
    try {
      const b=body(),p=await api.previewPrepContainer(rid,b);
      if(!active.current)return;
      if(!hash(p.reviewHash) || p.review?.store_id!==store || p.review.action!==b.action || p.review.accountingEffect!=="none" || p.review.consumptionEffect!=="none"
        || !same(Object.keys(p.review.body).sort(),Object.keys(b).sort()) || !Object.entries(b).every(([k,v])=>equalField(k,p.review.body[k],v)) || !p.review.facts)throw new Error("Container preview did not match your measurements.");
      if(["waste","undo_waste"].includes(b.action)&&(!hash(p.review.wasteReviewHash)||p.review.waste?.container_fill_id!==b.fill_id
        ||p.review.wasteEffect!==(b.action==="waste"?"measured_loss":"reverse_loss")||p.review.waste.kind!==(b.action==="waste"?"initial":"void")
        ||(b.action==="waste"&&(!equalField("quantity",p.review.waste.body?.quantity,b.quantity)||p.review.waste.body.category!==b.category))))throw new Error("Paired waste preview did not match the measured loss.");
      if(["waste","undo_waste"].includes(b.action)&&!validContainerWasteReview(p.review,b,store))throw new Error("Paired waste preview did not match the pinned contents and conversion.");
      edit(d=>({...d,review:p,confirmed:false}));
    } catch(e){if(active.current)setError(errorText(e));}
    finally{if(active.current)setBusy(false);}
  }
  async function save() {
    if(!draft.pending && (!draft.review || !draft.confirmed))return;
    const pending=draft.pending || {key:crypto.randomUUID(),body:{body:draft.review.review.body,expected_review_hash:draft.review.reviewHash,reviewed:true},review:draft.review};
    const submitted={...draft,pending,rejected:false};edit(submitted);setBusy(true);setError("");
    try {
      const ack=await api.savePrepContainer(rid,pending.body,pending.key);
      if(!active.current || !cache.has(`prep-containers:${rid}`))return;
      if(!validContainerAck(ack,pending,store))throw new Error("Container acknowledgement did not match the saved request. Retry the same command.");
      ++readSequence.current;
      if(clear(submitted,initial())){setMessage(["waste","undo_waste"].includes(pending.body.body.action)?"Container contents and waste journal saved together. Track 1 Food Cost is unchanged.":"Container command saved. Physical transfers do not count as consumption or change Food Cost.");refresh();}
    }catch(e){if(active.current && cache.has(`prep-containers:${rid}`)){setError(errorText(e));if([409,422].includes(e?.response?.status))edit(d=>({...d,rejected:true}));}}
    finally{if(active.current)setBusy(false);}
  }
  const field=(key,label,type="text",readonly=false)=><Field key={key} label={label}><input className={inpCls} aria-label={label} type={type} value={draft[key]} readOnly={readonly} onChange={e=>set(key,e.target.value)}/></Field>;
  const select=(key,label,options)=><Field label={label}><select aria-label={label} className={inpCls} value={draft[key]} onChange={e=>set(key,e.target.value)}><option value="">Select {label.toLowerCase()}</option>{options.map(o=><option key={o.id} value={o.id} disabled={o.disabled}>{o.label}</option>)}</select></Field>;
  const defs=data?.definitions || [],profiles=data?.profiles || [];
  return <section className={`${cardCls} space-y-3`} aria-label="Measured prep containers">
    <h2>Prep containers, service transfers and measured waste</h2><p>Measured contents stay in Track 2. Send moves storage to service; return moves it back. Unpack releases recorded contents to their original lot. Waste records measured loss once and reduces container contents in the same save. Track 1 Food Cost remains independent.</p>
    <p>Capacity references are separate from actual contents. Each food needs a measured usable fill profile; volume never implies food weight.</p>
    {error && <p role="alert">{error}</p>}{message && <p role="status">{message}</p>}
    <button className={btnGhost} disabled={frozen} onClick={refresh}>Refresh containers</button>
    {data && <fieldset disabled={frozen} className="space-y-3">
      <Field label="Container action"><select className={inpCls} aria-label="Container action" value={draft.action} onChange={e=>{edit({...initial(),action:e.target.value});setError("");}}>{["definition","profile","fill","send","return","unpack","void_fill","undo",...(data.directWasteSupported?["waste","undo_waste"]:[])].map(a=><option key={a} value={a}>{({definition:"Container capacity reference",profile:"Measured product fill profile",fill:"Record measured fill",send:"Send contents to service",return:"Return contents to storage",unpack:"Unpack to original lot",void_fill:"Void unused erroneous fill",undo:"Undo latest erroneous movement",waste:"Record measured container waste",undo_waste:"Reverse latest erroneous container waste"})[a]}</option>)}</select></Field>
      {draft.action==="definition" && <>{select("predecessor_id","Previous container definition",defs.filter(d=>d.current).map(d=>({id:d.id,label:`${d.name} · revision ${d.revision}`})))}{field("name","Container name")}{select("capacity_unit","Capacity reference unit",["lb","oz","g","kg","fl_oz","ml","l","gal","each"].map(id=>({id,label:id})))}{field("stated_capacity","Stated capacity (optional)")}{field("brimful_capacity","Measured brimful capacity (optional)")}{field("usable_capacity","Measured usable capacity (optional)")}{field("evidence","Capacity evidence")}</>}
      {draft.action==="profile" && <>{select("predecessor_id","Previous product fill profile",profiles.filter(p=>p.current).map(p=>({id:p.id,label:`${p.id} · revision ${p.revision}`})))}{select("definition_id","Container definition",defs.filter(d=>d.current).map(d=>({id:d.id,label:d.name})))}{select("product_version_id","Prepared product",data.products.map(p=>({id:p.id,label:p.name})))}{select("unit_profile_id","Verified food measurement",data.units.filter(p=>p.product_version_id===draft.product_version_id).map(p=>({id:p.id,label:`${p.source_unit} · factor ${p.base_units_per_source_unit}`})))}{field("usable_quantity","Measured usable food quantity")}{field("evidence","Food fill evidence")}<p>Enter a measured food-specific fill limit in the selected verified unit.</p></>}
      {draft.action==="fill" && <>{select("profile_id","Product fill profile",profiles.filter(p=>p.current).map(p=>({id:p.id,label:`${defs.find(d=>d.id===p.definition_id)?.name} · ${data.products.find(x=>x.product_id===p.product_id)?.name} · up to ${p.usable_quantity} ${p.source_unit}`,disabled:p.reviewNeeded})))}{select("source_batch_id","Recorded source lot",data.lots.filter(l=>l.product_id===profiles.find(p=>p.id===draft.profile_id)?.product_id).map(l=>({id:l.id,label:`${l.id} · ${l.remainingRecordedQuantity} ${l.base_unit} uncontained`})))}{field("label","Filled container label")}{field("quantity","Measured contents quantity")}</>}
      {!["definition","profile","fill"].includes(draft.action) && <>{select("fill_id","Filled container",data.fills.map(s=>({id:s.fill.id,label:`${s.fill.label} · ${s.storage} storage / ${s.service} service ${s.fill.base_unit}`,disabled:s.voided})))}{selected && <p>Original measured unit: {profiles.find(p=>p.id===selected.fill.profile_id)?.source_unit} · factor {selected.fill.factor} {selected.fill.base_unit}.</p>}{["send","return","unpack","waste"].includes(draft.action) && field("quantity","Movement quantity in original measured unit")}{["undo","undo_waste"].includes(draft.action) && select("target_move_id","Latest movement to undo",selected?.moves.slice(-1).filter(m=>draft.action==="undo_waste"?m.action==="waste":["send","return","unpack"].includes(m.action)).map(m=>({id:m.id,label:`${m.action} · ${m.quantity} · ${m.performed_at}`})) || [])}</>}
      {draft.action==="waste" && <>{select("compartment","Waste source compartment",["storage","service"].map(id=>({id,label:id})))}{select("category","Waste category",["storage_spoilage","service_discard","other"].filter(id=>id==="other"||(draft.compartment==="storage"?id==="storage_spoilage":id==="service_discard")).map(id=>({id,label:id.replaceAll("_"," ")})))}<p>Measure the loss in the original fill unit. Do not include loss already recorded in batch production. Changing compartments requires the matching category.</p></>}
      {draft.action==="undo_waste" && <p>Reverse only an erroneous latest waste measurement. The paired void restores its recorded contents at the original timestamp; later activity holds reversal for review.</p>}
      {!["definition","profile"].includes(draft.action) && <>{field("performed_at","Physical timestamp with offset")}{field("business_date","Location calendar date","date")}{field("timezone_name","Location timezone")}{field("note","Measurement or correction evidence")}<label><input type="checkbox" aria-label="Confirm measured contents and calendar day" checked={draft.confirmed} onChange={e=>edit(d=>({...d,confirmed:e.target.checked}))}/> I measured these contents and confirm the calendar day. Undo and void retain the original timestamp.</label></>}
      <button className={btnAcc} onClick={preview}>Review container command</button>
    </fieldset>}
    {draft.review && <article aria-label="Container command review" className={cardCls}><p>{draft.review.review.action} · location {store}</p>
      {draft.review.review.facts.name && <p>{draft.review.review.facts.name}: stated {draft.review.review.facts.stated_capacity ?? "unknown"}; brimful {draft.review.review.facts.brimful_capacity ?? "unknown"}; usable {draft.review.review.facts.usable_capacity ?? "unknown"} {draft.review.review.facts.capacity_unit}</p>}
      {draft.review.review.facts.usable_base_quantity && <p>Verified food fill limit: {draft.review.review.facts.usable_quantity} {draft.review.review.facts.source_unit} = {draft.review.review.facts.usable_base_quantity} {draft.review.review.facts.base_unit}.</p>}
      {draft.review.review.facts.base_quantity && <p>Actual measured fill: {draft.review.review.facts.quantity} × {draft.review.review.facts.factor} = {draft.review.review.facts.base_quantity} {draft.review.review.facts.base_unit} from lot {draft.review.review.facts.source_batch_id}.</p>}
      {draft.review.review.sources.after && <p>After movement: {draft.review.review.sources.after.storage} storage / {draft.review.review.sources.after.service} service {draft.review.review.sources.before.fill.base_unit}.</p>}
      {draft.review.review.waste && <p>{draft.review.review.action==="waste"?`Measured waste: ${draft.review.review.waste.body.quantity} × ${draft.review.review.waste.factor} = ${draft.review.review.waste.baseQuantity} ${draft.review.review.waste.base_unit} · ${draft.review.review.facts.compartment} · ${draft.review.review.waste.body.category}.`:`Void waste entry ${draft.review.review.waste.predecessor_id} and restore its recorded contents.`} Contents and the waste journal save together; there is one loss withdrawal.</p>}
      <p>No purchased inventory or consumption entry.</p><label><input type="checkbox" aria-label="Confirm container review" checked={draft.confirmed} disabled={frozen} onChange={e=>edit(d=>({...d,confirmed:e.target.checked}))}/> I reviewed the quantity, source, unit and history.</label>
      <button className={btnAcc} disabled={busy || (!draft.confirmed && !draft.pending)} onClick={save}>{draft.pending?"Retry same container command":"Save reviewed container command"}</button>
    </article>}
    {draft.pending && draft.rejected && <button className={btnGhost} disabled={busy} onClick={()=>{edit(d=>({...d,pending:null,review:null,confirmed:false,rejected:false}));setMessage("Rejected command retained for revision; review current facts before saving again.");refresh();}}>Revise rejected container command</button>}
    {data?.fills.some(s=>s.waste_history?.length) && <div aria-label="Paired container waste history"><h3>Measured waste journal links</h3>{data.fills.flatMap(s=>(s.waste_history||[]).map(p=><p key={p.link.command_id}>{s.fill.label} · waste event {p.event.id} · {p.event.kind} · {p.event.review_snapshot.body?.category||"paired reversal"} · {p.event.performed_at} · {p.event.reason}</p>))}</div>}
    {data && <div aria-label="Container contents history"><h3>Recorded lot quantities</h3><p>Uncontained output plus storage and service contents are a recorded allocation projection. Physical prep counts remain separate observations.</p><ul>{data.lots.map(l=><li key={l.id}>{l.id}: {l.remainingRecordedQuantity} uncontained + {l.containerStorage} stored + {l.containerService} in service = {l.totalRemainingRecordedQuantity} {l.base_unit} remaining recorded output.</li>)}</ul><h3>Recorded contents and movement history</h3>{data.fills.length===0 && <p>No measured container contents yet.</p>}{data.fills.map(s=><article className={cardCls} key={s.fill.id}><p>{s.fill.label} · {s.fill.id} · {s.storage} storage / {s.service} service {s.fill.base_unit}{s.voided?" · voided":""}</p><p>Original measured fill {s.fill.quantity} {profiles.find(p=>p.id===s.fill.profile_id)?.source_unit}; pinned profile {s.fill.profile_id}; source lot {s.fill.source_batch_id}.</p><ul>{s.moves.map(m=><li key={m.id}>{m.action} · {m.performed_at} · storage {m.storage_delta}, service {m.service_delta} · {m.note}</li>)}</ul></article>)}</div>}
  </section>;
}
