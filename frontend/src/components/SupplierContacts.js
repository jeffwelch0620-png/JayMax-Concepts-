import React,{useEffect,useRef,useState} from "react";
import * as api from "../lib/api";
import {useRetainedDraft} from "../lib/saveIntegrity";
import {cardCls,inpCls,btnGhost,SectionLabel} from "./common";

const empty={vendorId:"",email:"",note:"",legacyVendor:null,verified:false,baseVersion:0,vendorVersion:0,pending:null,entries:{}};
const storeId=rid=>rid==="papa_leonis"?"papa":rid;
export function SupplierContacts({rid,drafts,onSaved,showToast=()=>{}}){
  const [data,setData]=useState(null),[error,setError]=useState(""),[busy,setBusy]=useState(false),[reading,setReading]=useState(false);
  const [draft,setDraft]=useRetainedDraft(`supplier-contact:${rid}`,empty,drafts);
  const epoch=useRef(0);
  const readSequence=useRef(0);
  useEffect(()=>{const id=++epoch.current;load(id);return()=>{epoch.current++;};},[rid]); // eslint-disable-line react-hooks/exhaustive-deps
  async function load(id=epoch.current,rebase=false){
    const sequence=++readSequence.current;setReading(true);
    try{
      const result=await api.supplierContacts(rid);
      if(epoch.current!==id||readSequence.current!==sequence)return;
      if(result?.store_id!==storeId(rid)||!Array.isArray(result.contacts)||!Array.isArray(result.legacy_contacts)||result.contacts.some(c=>c.store_id!==storeId(rid)||!c.vendor_id||typeof c.order_email!=="string"||!Number.isSafeInteger(c.version)||c.version<0||!Number.isSafeInteger(c.vendor_version)||c.vendor_version<1))throw new Error("Supplier contact read was not confirmed.");
      setData(result);
      if(rebase)setDraft(previous=>{const c=result.contacts.find(row=>row.vendor_id===previous.vendorId);return c?{...previous,baseVersion:c.version,vendorVersion:c.vendor_version}:previous;});
      setError(rebase?"Versions refreshed. Review your retained email against the saved email before saving.":"");
    }catch(e){if(epoch.current===id&&readSequence.current===sequence)setError(e?.response?.data?.detail||e.message||"Contact read failed.");}
    finally{if(epoch.current===id&&readSequence.current===sequence)setReading(false);}
  }
  function choose(vendorId){
    const c=data.contacts.find(row=>row.vendor_id===vendorId);
    setDraft(previous=>{const {entries,...editing}=previous;const retained={...entries,...(previous.vendorId?{[previous.vendorId]:editing}:{})};
      return {...(retained[vendorId]||{...empty,vendorId,email:c?.order_email||"",baseVersion:c?.version||0,vendorVersion:c?.vendor_version||0}),entries:retained};});
    setError("");
  }
  async function save(){
    if(busy||reading)return;
    const id=epoch.current;
    let submitted=draft.pending;
    if(!submitted){
      if(!draft.vendorId||!draft.note.trim()){setError("Choose a supplier and record the reason for this edit.");return;}
      if(draft.legacyVendor&&!draft.verified){setError("Verify the preserved contact belongs to the selected supplier.");return;}
      submitted={key:window.crypto.randomUUID(),vendor:draft.vendorId,version:draft.baseVersion,
        body:{order_email:draft.email.trim(),expected_vendor_version:draft.vendorVersion,note:draft.note.trim(),legacy_vendor:draft.legacyVendor,verified:draft.verified}};
      setDraft(previous=>({...previous,pending:submitted}));
    }
    setBusy(true);setError("");
    try{
      const response=await api.saveSupplierContact(rid,submitted.vendor,submitted.body,submitted.version,submitted.key);
      if(epoch.current!==id)return;
      const saved=response?.contact,current=response?.current_contact;
      if(response.request_key!==submitted.key||saved?.store_id!==storeId(rid)||saved.vendor_id!==submitted.vendor||saved.order_email!==submitted.body.order_email||saved.version!==submitted.version+1||!saved.event_id||current?.store_id!==storeId(rid)||current.vendor_id!==saved.vendor_id||typeof current.order_email!=="string"||!Number.isSafeInteger(current.version)||current.version<saved.version||!current.event_id||(current.version===saved.version&&(current.order_email!==saved.order_email||current.event_id!==saved.event_id)))throw new Error("Supplier contact save was not confirmed. Your exact request is retained for retry.");
      setData(previous=>({...previous,contacts:previous.contacts.map(c=>c.vendor_id===current.vendor_id?{...c,...current}:c),legacy_contacts:previous.legacy_contacts.filter(c=>c.vendor!==submitted.body.legacy_vendor)}));
      setDraft(previous=>previous.pending?.key===submitted.key?{...previous,email:current.order_email,baseVersion:current.version,pending:null,legacyVendor:null,verified:false}:previous);
      showToast(response.replayed?"Contact save confirmed; current saved email displayed.":"Supplier contact saved.");
      try{await onSaved?.();}catch(e){if(epoch.current===id)setError("Contact saved, but the catalog refresh failed. Refresh the location before another catalog edit.");}
    }catch(e){
      if(epoch.current!==id)return;
      setError(e?.response?.data?.detail||e.message||"Contact save was not confirmed; retry the same request.");
      if([400,403,404,409,422,428].includes(e?.response?.status))setDraft(previous=>({...previous,pending:null}));
    }finally{if(epoch.current===id)setBusy(false);}
  }
  const selected=data?.contacts.find(c=>c.vendor_id===draft.vendorId),locked=busy||reading||!!draft.pending;
  return <div className={`${cardCls} p-4 mb-6`}>
    <SectionLabel>Supplier Order Contacts</SectionLabel>
    <p>Contacts are saved separately for this location. Saving a contact sends no email.</p>
    {error&&<p role="alert">{error}</p>}
    {!data?<p>Contact records awaiting a confirmed read.</p>:<>
      <label>Supplier<select aria-label="Contact supplier" className={inpCls} value={draft.vendorId} disabled={locked} onChange={e=>choose(e.target.value)}><option value="">Choose supplier</option>{data.contacts.map(c=><option key={c.vendor_id} value={c.vendor_id}>{c.vendor_name}{!c.vendor_active?" (inactive)":""}</option>)}</select></label>
      {selected&&<>
        <p>Saved email: {selected.order_email||"No saved email"}. Contact version {selected.version}.</p>
        <label>Order email<input aria-label="Supplier order email" className={inpCls} value={draft.email} disabled={locked} onChange={e=>setDraft(previous=>({...previous,email:e.target.value}))}/></label>
        <label>Reason<textarea aria-label="Contact edit reason" className={inpCls} value={draft.note} disabled={locked} onChange={e=>setDraft(previous=>({...previous,note:e.target.value}))}/></label>
        {!!data.legacy_contacts.length&&<label>Preserved name-based contact<select aria-label="Preserved contact" className={inpCls} disabled={locked} value={draft.legacyVendor||""} onChange={e=>{const legacy=data.legacy_contacts.find(c=>c.vendor===e.target.value);setDraft(previous=>({...previous,legacyVendor:legacy?.vendor||null,email:legacy?legacy.raw_record.order_email:previous.email,verified:false}));}}><option value="">Separate manual edit</option>{data.legacy_contacts.map(c=><option key={c.vendor} value={c.vendor}>{c.vendor}: {c.raw_record.order_email||"blank"}</option>)}</select></label>}
        {draft.legacyVendor&&<label><input type="checkbox" aria-label="Verify preserved supplier contact" disabled={locked} checked={draft.verified} onChange={e=>setDraft(previous=>({...previous,verified:e.target.checked}))}/>I verified this preserved contact belongs to the selected supplier; the entered email is reviewed.</label>}
        <button className={btnGhost} disabled={busy||reading||!selected.vendor_active} onClick={save}>{draft.pending?"Retry the same contact save":"Save reviewed contact"}</button>
      </>}
      <button className={btnGhost} disabled={locked} onClick={()=>load(epoch.current,true)}>Refresh contact versions</button>
      {!!data.legacy_contacts.length&&<p>{data.legacy_contacts.length} preserved name-based contact(s) await explicit supplier mapping. They have not been assigned automatically.</p>}
    </>}
  </div>;
}
