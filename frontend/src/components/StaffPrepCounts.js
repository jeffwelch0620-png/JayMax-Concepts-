import React, { useEffect, useRef, useState } from "react";
import * as api from "../lib/api";
import { useRetainedDraft } from "../lib/saveIntegrity";
import { cardCls, inpCls, btnAcc, btnGhost, Field } from "./common";

const store = rid => rid === "papa_leonis" ? "papa" : rid;
const stable = value => JSON.stringify(value && typeof value === "object" ? Array.isArray(value) ? value.map(v => JSON.parse(stable(v))) : Object.fromEntries(Object.keys(value).sort().map(k => [k, JSON.parse(stable(value[k]))])) : value);
const hash = value => typeof value === "string" && /^[a-f0-9]{64}$/.test(value);
const decimal = value => typeof value === "string" && /^\d+(?:\.\d+)?$/.test(value);
const errorText = e => typeof e?.response?.data?.detail === "string" ? e.response.data.detail : e.message || "Count outcome could not be confirmed.";
const sorted = rows => [...rows].sort((a,b) => a.product_id.localeCompare(b.product_id));
const sameTime = (a,b) => Number.isFinite(Date.parse(a)) && Date.parse(a) === Date.parse(b);
export const quantityText = value => {
  const text = String(value).trim();
  if (!/^\d{1,16}(?:\.\d{1,12})?$/.test(text)) throw new Error("Use a nonnegative measured decimal with at most 16 whole and 12 fractional digits.");
  const [whole, fraction = ""] = text.split(".");
  const f = fraction.replace(/0+$/, "");
  return (whole.replace(/^0+(?=\d)/, "") || "0") + (f ? `.${f}` : "");
};
export function validPrepCountReview(r, rid) {
  const s = r?.sheet, snap = s?.sheet_snapshot, items = snap?.items;
  return !!s?.id && s.store_id === store(rid) && snap?.store_id === store(rid) && hash(r.reviewHash)
    && snap.stamp?.business_date === s.business_date && snap.stamp.timezone_name === s.timezone_name && sameTime(snap.stamp.performed_at,s.performed_at)
    && Array.isArray(items) && items.length > 0 && new Set(items.map(i => i.product_id)).size === items.length
    && items.every(i => i.product_id && i.product_version_id && i.profile_id && i.name && i.base_unit && i.counted_unit && decimal(i.factor) && /[1-9]/.test(i.factor))
    && Array.isArray(r.errors) && Array.isArray(r.history)
    && r.history.every(h => h.sheet_id === s.id && h.store_id === s.store_id && Number.isSafeInteger(h.revision) && h.revision > 0 && Array.isArray(h.quantities))
    && (!r.latest || (r.history[0]?.id === r.latest.id && stable(r.history[0]) === stable(r.latest)))
    && (!r.decision || (r.decision.sheet_id === s.id && r.decision.store_id === s.store_id && ["accepted","rejected"].includes(r.decision.decision)));
}

export function StaffPrepQuantityForm({ rid, review, pin = "", counterName = "", drafts, onSubmit, onChange=()=>{} }) {
  const items = review.sheet.sheet_snapshot.items;
  const [draft,edit] = useRetainedDraft(`staff-prep-submit:${rid}:${review.sheet.id}`, {
    name:counterName, note:"", rows:Object.fromEntries(items.map(i => [i.product_id,{ product_id:i.product_id, quantity:"", evidence:"" }])), pending:null, saved:null
  }, drafts);
  const [busy,setBusy] = useState(false), [error,setError] = useState(""), [rejected,setRejected] = useState(false);
  const alive = useRef(true), flight = useRef(false);
  useEffect(() => { alive.current=true; return () => { alive.current=false; }; }, []);
  const change = (key,value) => edit(p => ({...p,[key]:value,saved:null}));
  async function submit() {
    if (flight.current) return;
    let pending = draft.pending;
    try {
      if (!pending) {
        if (!draft.name.trim() || !draft.note.trim()) throw new Error("Enter the counter name and measurement note.");
        pending = { key:crypto.randomUUID(), review, body:{ counter_name:draft.name.trim(), note:draft.note.trim(), expected_review_hash:review.reviewHash,
          lines:sorted(items.map(i => ({ product_id:i.product_id, quantity:draft.rows[i.product_id].quantity.trim() === "" ? null : quantityText(draft.rows[i.product_id].quantity), evidence:draft.rows[i.product_id].evidence.trim() }))) } };
        edit(p => ({...p,pending}));
      }
      flight.current=true; setBusy(true); setError(""); setRejected(false);
      const result = await onSubmit({...pending.body,pin},pending.key);
      if (!alive.current || (drafts && drafts.get(`staff-prep-submit:${rid}:${review.sheet.id}`)?.pending?.key!==pending.key)) return;
      const s = result?.submission;
      if (!s?.id || s.sheet_id !== review.sheet.id || s.store_id !== store(rid) || s.request_key !== pending.key
        || stable(s.submitted_body) !== stable(pending.body) || !validPrepCountReview(result.current,rid) || result.current.sheet.id !== review.sheet.id
        || !result.current.history.some(h => h.id === s.id && stable(h) === stable(s))) throw new Error("Prep quantity submission was not confirmed. The exact request is retained.");
      edit(p => ({...p,pending:null,saved:{revision:s.revision,current:result.current}}));
      onChange(result.current);
    } catch(e) { if (alive.current) { setError(errorText(e)); setRejected([409,422].includes(e?.response?.status)); } }
    finally { flight.current=false; if (alive.current) setBusy(false); }
  }
  return <section className={`${cardCls} p-4 space-y-3`} aria-label="Staff prep measurement sheet">
    <h3>Prepared inventory count · {review.sheet.business_date}</h3>
    <p>Physical boundary: {review.sheet.sheet_snapshot.stamp.performed_at} · {review.sheet.timezone_name}</p>
    <p>{review.sheet.sheet_snapshot.stamp.note}</p>
    <p>Count every listed prepared item in the issued units. Blank means unknown; 0 means measured empty. Manager acceptance is required before planning uses these quantities. Actual purchased inventory and Food Cost stay independent.</p>
    <p>A counter name records claimed attribution. A shared PIN does not verify an individual identity.</p>
    {!!review.errors.length && <p role="alert">{review.errors.join("; ")}</p>}
    <fieldset disabled={busy || !!draft.pending || !!review.decision || !!review.errors.length} className="space-y-3">
      <Field label="Counter name"><input className={inpCls} aria-label="Prep counter name" value={draft.name} onChange={e=>change("name",e.target.value)}/></Field>
      <Field label="Measurement note"><input className={inpCls} aria-label="Prep measurement note" value={draft.note} onChange={e=>change("note",e.target.value)}/></Field>
      {items.map(i=><div key={i.product_id}><p>{i.name} · {i.counted_unit} · {i.factor} {i.base_unit} per counted unit</p>
        <input className={inpCls} inputMode="decimal" aria-label={`Prep quantity ${i.product_id}`} value={draft.rows[i.product_id]?.quantity ?? ""} onChange={e=>change("rows",{...draft.rows,[i.product_id]:{...draft.rows[i.product_id],quantity:e.target.value}})}/>
        <input className={inpCls} aria-label={`Prep evidence ${i.product_id}`} placeholder="All storage locations / measurement evidence" value={draft.rows[i.product_id]?.evidence || ""} onChange={e=>change("rows",{...draft.rows,[i.product_id]:{...draft.rows[i.product_id],evidence:e.target.value}})}/>
      </div>)}
    </fieldset>
    {error && <p role="alert">{error}</p>}
    {draft.saved && <p role="status">Prep measurement revision {draft.saved.revision} saved and confirmed. Latest recorded revision: {draft.saved.current.latest?.revision}. Manager review is separate.</p>}
    <button className={btnAcc} disabled={busy || (!draft.pending && (!!review.decision || !!review.errors.length))} onClick={submit}>{draft.pending ? "Retry same prep submission" : "Submit prep quantities for review"}</button>
    {rejected && draft.pending && <button className={btnGhost} onClick={()=>{edit(p=>({...p,pending:null}));setRejected(false);setError("Request was rejected. Refresh this sheet and review the retained entries before a new submission.");}}>Revise rejected prep request</button>}
  </section>;
}

export function StaffPrepCountDrafts({ rid, pin, counterName, drafts }) {
  const privateDrafts = useRef(new Map()), cache = drafts || privateDrafts.current;
  const sequence = useRef(0);
  const [reviews,setReviews] = useState([]), [error,setError] = useState(""), [loading,setLoading] = useState(true), [epoch,setEpoch] = useState(0);
  useEffect(()=>{
    let active=true; const serial=++sequence.current; setLoading(true); setError("");
    api.staffPrepCountDrafts(rid,pin).then(rows=>{
      if (!Array.isArray(rows) || rows.some(r=>!validPrepCountReview(r,rid))) throw new Error("Issued prep count sheets were not confirmed.");
      if (active && sequence.current===serial) setReviews(rows);
    }).catch(e=>active && sequence.current===serial && setError(errorText(e))).finally(()=>active && sequence.current===serial && setLoading(false));
    return ()=>{active=false;};
  },[rid,pin,epoch]);
  const shown = reviews.filter(r=>validPrepCountReview(r,rid));
  for (const [key,d] of cache.entries()) if (key.startsWith(`staff-prep-submit:${rid}:`) && d.pending && !shown.some(r=>r.sheet.id===d.pending.review.sheet.id)) shown.push(d.pending.review);
  return <section className="space-y-4"><h2>Manager-issued prep counts</h2><button className={btnGhost} onClick={()=>setEpoch(e=>e+1)}>Refresh prep count sheets</button>
    {error && <p role="alert">{error}</p>}{loading && <p>Loading prep count sheets…</p>}
    {!loading && !error && !shown.length && <p>No open prep count sheets. Ask your manager to issue one in Prep.</p>}
    {shown.map(r=><StaffPrepQuantityForm key={`${rid}:${r.sheet.id}`} rid={rid} review={r} pin={pin} counterName={counterName} drafts={cache} onSubmit={(body,key)=>api.submitStaffPrepCountDraft(rid,r.sheet.id,body,key)} onChange={current=>{sequence.current++;setLoading(false);setReviews(rows=>[current,...rows.filter(r=>r.sheet.id!==current.sheet.id)]);}}/>)}
  </section>;
}

export function PrepCountDecision({ rid, review, drafts, onChange=()=>{} }) {
  const [draft,edit] = useRetainedDraft(`prep-count-decision:${rid}:${review.sheet.id}`,{ decision:"accepted",note:"",preview:null,confirmed:false,pending:null,saved:null },drafts);
  const [busy,setBusy]=useState(false),[error,setError]=useState(""),[rejected,setRejected]=useState(false); const alive=useRef(true),flight=useRef(false);
  useEffect(()=>{alive.current=true;return()=>{alive.current=false;};},[]);
  const change=(key,value)=>edit(p=>({...p,[key]:value,preview:null,confirmed:false,saved:null}));
  async function preview() {
    if (flight.current || draft.pending) return; flight.current=true;setBusy(true);setError("");
    try {
      const body={decision:draft.decision,note:draft.note.trim(),reviewed:true};
      const p=await api.previewStaffPrepCountDecision(rid,review.sheet.id,body); if(!alive.current)return;
      if (!validPrepCountReview(p?.current,rid) || p.current.sheet.id!==review.sheet.id || p.current.reviewHash!==review.reviewHash || stable(p.decision)!==stable(body)
        || (body.decision==="accepted" ? !hash(p.observation?.reviewHash) || p.observation.review?.purpose!=="count" || p.observation.review.kind!=="initial"
          || !sameTime(p.observation.review.performed_at,review.sheet.performed_at) || p.observation.review.business_date!==review.sheet.business_date
          || p.observation.review.timezone_name!==review.sheet.timezone_name || p.observation.review.reason!==body.note
          || p.observation.review.lines?.length!==review.sheet.sheet_snapshot.items.length || p.observation.review.lines.some(l=>{
            const i=review.sheet.sheet_snapshot.items.find(i=>i.product_id===l.product_id),q=review.latest?.quantities.find(q=>q.product_id===l.product_id);
            return !i || !q || l.product_version_id!==i.product_version_id || l.profile_id!==i.profile_id || l.factor!==i.factor || l.quantity!==q.quantity || l.evidence!==q.evidence || !decimal(l.base_quantity);
          }) : p.observation!==null)) throw new Error("Prep count decision preview was not confirmed.");
      edit(d=>({...d,preview:p,confirmed:false}));
    }catch(e){if(alive.current)setError(errorText(e));}finally{flight.current=false;if(alive.current)setBusy(false);}
  }
  async function save() {
    if(flight.current)return;let pending=draft.pending;
    if(!pending){if(!draft.confirmed || !draft.preview || draft.preview.current.reviewHash!==review.reviewHash){setError("Refresh and review the latest submission before deciding.");return;}
      pending={key:crypto.randomUUID(),preview:draft.preview,body:{...draft.preview.decision,expected_review_hash:draft.preview.current.reviewHash,expected_observation_hash:draft.preview.observation?.reviewHash || null}};edit(p=>({...p,pending}));}
    flight.current=true;setBusy(true);setError("");setRejected(false);
    try{
      const r=await api.decideStaffPrepCountSheet(rid,review.sheet.id,pending.body,pending.key);if(!alive.current || (drafts && drafts.get(`prep-count-decision:${rid}:${review.sheet.id}`)?.pending?.key!==pending.key))return;const d=r?.decision;
      if(!d?.id || d.sheet_id!==review.sheet.id || d.store_id!==store(rid) || d.request_key!==pending.key || d.decision!==pending.body.decision || d.note!==pending.body.note
        || d.review_snapshot?.current?.reviewHash!==pending.body.expected_review_hash || d.submission_id!==(pending.preview.current.latest?.id || null)
        || !validPrepCountReview(r.current,rid) || r.current.sheet.id!==review.sheet.id || stable(r.current.decision)!==stable(d)
        || (d.decision==="accepted" ? !r.observation?.id || d.observation_id!==r.observation.id || r.observation.store_id!==store(rid)
          || r.observation.review_hash!==pending.body.expected_observation_hash || stable(r.observation.review_snapshot)!==stable(pending.preview.observation.review)
          : r.observation!==null || d.observation_id!==null))throw new Error("Prep count decision was not confirmed. The exact request is retained.");
      edit(p=>({...p,pending:null,preview:null,confirmed:false,saved:d.decision}));onChange(r.current);
    }catch(e){if(alive.current){setError(errorText(e));setRejected([409,422].includes(e?.response?.status));}}finally{flight.current=false;if(alive.current)setBusy(false);}
  }
  return <section className={`${cardCls} p-4 space-y-3`}><h3>Review prep count · {review.sheet.business_date}</h3>
    <p>Submission revision {review.latest?.revision || "none"} · {review.latest?.counter_name || "no measurements"} · {review.latest?.credential_kind || ""}</p>
    {!!review.errors.length && <p role="alert">{review.errors.join("; ")}</p>}
    {review.sheet.sheet_snapshot.items.map(i=>{const q=review.latest?.quantities.find(q=>q.product_id===i.product_id);return <p key={i.product_id}>{i.name}: {q?.quantity ?? "Unknown"} {i.counted_unit} · {q?.evidence || "No measurement evidence"}</p>;})}
    {review.decision && <p>Recorded decision: {review.decision.decision}. Accepted observations use the native correction/void journal for later changes.</p>}
    <fieldset disabled={busy || !!draft.pending || !!review.decision}>
      <select className={inpCls} aria-label="Prep count decision" value={draft.decision} onChange={e=>change("decision",e.target.value)}><option value="accepted">Accept as prep observation</option><option value="rejected">Reject sheet</option></select>
      <input className={inpCls} aria-label="Prep count decision note" value={draft.note} onChange={e=>change("note",e.target.value)}/>
      <button className={btnGhost} disabled={!draft.note.trim()} onClick={preview}>Preview prep count decision</button>
    </fieldset>
    {draft.preview && <div><p>{draft.preview.observation ? "Acceptance records a full physical prep observation; no inventory movement or Food Cost change." : "Rejection records no physical observation."}</p>
      {draft.preview.observation?.review.lines.map(l=><p key={l.product_id}>Measured base quantity: {l.base_quantity} {l.base_unit}</p>)}
      <label><input type="checkbox" aria-label="Confirm prep count decision" checked={draft.confirmed} disabled={busy || !!draft.pending} onChange={e=>edit(p=>({...p,confirmed:e.target.checked}))}/>I reviewed these measurements and this decision.</label></div>}
    {error && <p role="alert">{error}</p>}{draft.saved && <p role="status">Prep count decision confirmed: {draft.saved}. Actual accounting inventory was unchanged.</p>}
    <button className={btnAcc} disabled={busy || (!draft.pending && (!draft.confirmed || !!review.decision))} onClick={save}>{draft.pending ? "Retry same prep count decision" : "Save reviewed prep count decision"}</button>
    {rejected && draft.pending && <button className={btnGhost} onClick={()=>{edit(p=>({...p,pending:null,preview:null,confirmed:false}));setRejected(false);setError("Request was rejected. Refresh the latest sheet and preview a new decision.");}}>Review a revised prep count decision</button>}
  </section>;
}

export function StaffPrepCountReview({ rid, drafts }) {
  const [data,setData]=useState(null),[error,setError]=useState(""),[busy,setBusy]=useState(false),[rejected,setRejected]=useState(false);
  const [draft,edit]=useRetainedDraft(`prep-count-issue:${rid}`,{ performed_at:"",business_date:"",timezone_name:"America/New_York",calendar_date_confirmed:false,note:"",units:{},preview:null,confirmed:false,pending:null },drafts);
  const epoch=useRef(0),sequence=useRef(0),flight=useRef(false);
  useEffect(()=>{const id=++epoch.current;load(id);return()=>{epoch.current++;};},[]); // eslint-disable-line react-hooks/exhaustive-deps
  async function load(id=epoch.current){const serial=++sequence.current;
    try{const d=await api.staffPrepCountSetup(rid);if(epoch.current!==id || sequence.current!==serial)return;
      if(d?.store_id!==store(rid) || !Array.isArray(d.products) || !Array.isArray(d.profiles) || !Array.isArray(d.sheets) || d.sheets.some(r=>!validPrepCountReview(r,rid)))throw new Error("Prep count setup was not confirmed.");
      setData(d);setError("");
    }catch(e){if(epoch.current===id && sequence.current===serial)setError(errorText(e));}}
  function change(key,value){edit(p=>({...p,[key]:value,preview:null,confirmed:false}));}
  async function preview(){if(flight.current || draft.pending || !data)return;flight.current=true;setBusy(true);setError("");const id=epoch.current;
    try{const body={performed_at:draft.performed_at.trim(),business_date:draft.business_date,timezone_name:draft.timezone_name.trim(),calendar_date_confirmed:draft.calendar_date_confirmed,note:draft.note.trim(),units:data.products.map(p=>({product_version_id:p.id,profile_id:draft.units[p.product_id] || ""})).sort((a,b)=>a.product_version_id.localeCompare(b.product_version_id))};
      const p=await api.previewStaffPrepCountSheet(rid,body);if(epoch.current!==id)return;
      const stamp={...body};delete stamp.units;
      if(!hash(p?.reviewHash) || p.review?.store_id!==store(rid) || !sameTime(p.review.stamp?.performed_at,stamp.performed_at)
        || stable({...p.review.stamp,performed_at:stamp.performed_at})!==stable(stamp) || p.review.items?.length!==data.products.length
        || new Set(p.review.items.map(i=>i.product_id)).size!==data.products.length
        || p.review.items.some(i=>{
          const product=data.products.find(p=>p.product_id===i.product_id),profile=data.profiles.find(u=>u.id===i.profile_id);
          return !body.units.some(u=>u.profile_id===i.profile_id && u.product_version_id===i.product_version_id)
            || product?.id!==i.product_version_id || product?.name!==i.name || product?.base_unit!==i.base_unit
            || profile?.source_unit!==i.counted_unit || profile?.base_units_per_source_unit!==i.factor || !decimal(i.factor);
        }))throw new Error("Issued prep scope preview was not confirmed.");
      edit(d=>({...d,preview:{...p,body},confirmed:false}));
    }catch(e){if(epoch.current===id)setError(errorText(e));}finally{flight.current=false;if(epoch.current===id)setBusy(false);}}
  async function issue(){if(flight.current)return;let pending=draft.pending;if(!pending){if(!draft.confirmed || !draft.preview)return;
      pending={key:crypto.randomUUID(),body:{sheet:draft.preview.body,expected_review_hash:draft.preview.reviewHash,reviewed:true},snapshot:draft.preview.review};edit(p=>({...p,pending}));}
    flight.current=true;setBusy(true);setError("");setRejected(false);const id=epoch.current;
    try{const r=await api.issueStaffPrepCountSheet(rid,pending.body,pending.key);if(epoch.current!==id || (drafts && drafts.get(`prep-count-issue:${rid}`)?.pending?.key!==pending.key))return;
      if(!r?.sheet?.id || r.sheet.store_id!==store(rid) || r.sheet.request_key!==pending.key || r.sheet.review_hash!==pending.body.expected_review_hash
        || stable(r.sheet.sheet_snapshot)!==stable(pending.snapshot) || !validPrepCountReview(r.current,rid) || stable(r.current.sheet)!==stable(r.sheet))throw new Error("Prep count sheet issue was not confirmed. The exact request is retained.");
      sequence.current++;setData(d=>({...d,sheets:[r.current,...d.sheets.filter(s=>s.sheet.id!==r.sheet.id)]}));edit(p=>({...p,pending:null,preview:null,confirmed:false,note:""}));
    }catch(e){if(epoch.current===id){setError(errorText(e));setRejected([409,422].includes(e?.response?.status));}}finally{flight.current=false;if(epoch.current===id)setBusy(false);}}
  return <section className="space-y-4"><h2>Staff prep counts · Track 2</h2><p>Issue one full prepared-inventory sheet for a fixed physical boundary. Daily and bulk planning can both use its accepted observation. Purchased-item counts remain in Actual Inventory.</p>
    <button className={btnGhost} onClick={()=>load()}>Refresh prep count review</button>{error && <p role="alert">{error}</p>}
    {data ? <><fieldset className={`${cardCls} p-4 space-y-3`} disabled={busy || !!draft.pending}>
      <Field label="Physical time with UTC offset"><input className={inpCls} aria-label="Prep sheet physical time" placeholder="2026-10-07T22:00:00-04:00" value={draft.performed_at} onChange={e=>change("performed_at",e.target.value)}/></Field>
      <input type="date" className={inpCls} aria-label="Prep sheet business date" value={draft.business_date} onChange={e=>change("business_date",e.target.value)}/>
      <input className={inpCls} aria-label="Prep sheet timezone" value={draft.timezone_name} onChange={e=>change("timezone_name",e.target.value)}/>
      <label><input type="checkbox" aria-label="Prep sheet calendar confirmed" checked={draft.calendar_date_confirmed} onChange={e=>change("calendar_date_confirmed",e.target.checked)}/>I confirmed the location calendar date.</label>
      <input className={inpCls} aria-label="Prep sheet instructions" placeholder="Storage locations / instructions" value={draft.note} onChange={e=>change("note",e.target.value)}/>
      {data.products.map(p=><Field key={p.product_id} label={p.name}><select className={inpCls} aria-label={`Prep sheet unit ${p.product_id}`} value={draft.units[p.product_id] || ""} onChange={e=>change("units",{...draft.units,[p.product_id]:e.target.value})}><option value="">Choose verified count unit</option>{data.profiles.filter(u=>u.product_version_id===p.id).map(u=><option key={u.id} value={u.id}>{u.source_unit} · {u.base_units_per_source_unit} {p.base_unit}</option>)}</select></Field>)}
      <button className={btnGhost} disabled={!data.products.length} onClick={preview}>Preview issued prep sheet</button>
    </fieldset>
    {draft.preview && <div>{draft.preview.review.items.map(i=><p key={i.product_id}>{i.name} · {i.counted_unit} · {i.factor} {i.base_unit} per count unit</p>)}<label><input type="checkbox" aria-label="Confirm issued prep sheet" checked={draft.confirmed} disabled={busy || !!draft.pending} onChange={e=>edit(p=>({...p,confirmed:e.target.checked}))}/>I reviewed the full scope and units.</label></div>}
    <button className={btnAcc} disabled={busy || (!draft.pending && !draft.confirmed)} onClick={issue}>{draft.pending ? "Retry same prep sheet issue" : "Issue reviewed prep sheet"}</button>
    {rejected && draft.pending && <button className={btnGhost} onClick={()=>{edit(p=>({...p,pending:null,preview:null,confirmed:false}));setRejected(false);setError("Request was rejected. Refresh definitions and review a new issue preview.");}}>Review a revised prep sheet issue</button>}
    {data.sheets.map(r=><PrepCountDecision key={`${rid}:${r.sheet.id}`} rid={rid} review={r} drafts={drafts} onChange={current=>{sequence.current++;setData(d=>({...d,sheets:d.sheets.map(s=>s.sheet.id===current.sheet.id?current:s)}));}}/>)}
    </> : <p>Loading prep count review…</p>}
  </section>;
}
