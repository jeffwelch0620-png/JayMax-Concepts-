import React, { useEffect, useRef, useState } from "react";
import * as api from "../lib/api";
import { NativeOrderReceiving } from "./NativeOrderReceiving";
import { PageTitle, cardCls, inpCls, btnAcc, btnGhost } from "./common";
const actions = { draft:["submit","archive"],pending:["approve","reject"],approved:["send"],rejected:["reopen","archive"],sent:[],receiving:[],received:[] };
export function NativeOrderWorkflow({ rid, showToast, onInventoryChange }) {
  const [orders,setOrders]=useState([]),[note,setNote]=useState(""),[error,setError]=useState(""),[busy,setBusy]=useState(false),[pending,setPending]=useState(null);
  const alive=useRef(true),reads=useRef(0);
  async function load() {
    if (pending || busy) return;
    const read=++reads.current;setError("");
    try {
      const list=await api.listOrders(rid);
      if (!alive.current || read!==reads.current) return;
      if (!Array.isArray(list) || list.some(p=>!Number.isSafeInteger(p.orderVersion) || p.orderVersion<=0 || !Array.isArray(p.lines))) throw new Error("Versioned orders were not confirmed. Check workflow enablement.");
      setOrders(list);
    } catch(e) { if (alive.current && read===reads.current) setError(e?.response?.data?.detail || e.message || "Could not load orders."); }
  }
  useEffect(()=>{alive.current=true;load();return()=>{alive.current=false;++reads.current;};},[rid]); // eslint-disable-line react-hooks/exhaustive-deps
  async function command(po,action) {
    if (busy || (pending && pending.ref!==po?.id)) return;
    const attempt=pending || {ref:po.id,version:po.orderVersion,key:crypto.randomUUID(),body:{action,note:note.trim()}};
    setPending(attempt);setBusy(true);setError("");
    try {
      const response=await api.orderCommand(rid,attempt.ref,attempt.body,attempt.version,attempt.key);
      const saved=response?.order;
      const target={submit:"pending",approve:"approved",reject:"rejected",reopen:"draft",send:"sent",reorder:"draft"}[attempt.body.action];
      if (response?.request_key!==attempt.key || !saved?.id || saved.restaurantId!==rid || !Number.isSafeInteger(saved.orderVersion) || saved.orderVersion<=0 || !Array.isArray(saved.lines) || (attempt.body.action==="archive" ? (!saved.archivedAt || saved.id!==attempt.ref || saved.orderVersion<=attempt.version) : saved.status!==target || (attempt.body.action!=="reorder" && (saved.id!==attempt.ref || saved.orderVersion<=attempt.version)))) throw new Error("Order command was not confirmed.");
      if (!alive.current) return;
      const current=response.current_order || (response.replayed ? null : saved);
      if (!current || current.id!==saved.id || current.restaurantId!==rid || !Number.isSafeInteger(current.orderVersion) || current.orderVersion<saved.orderVersion || !Array.isArray(current.lines)) throw new Error("Current order read-back was not confirmed.");
      setPending(null);setNote("");
      setOrders(list=>current.archivedAt ? list.filter(p=>p.id!==current.id) : attempt.body.action==="reorder" ? [current,...list.filter(p=>p.id!==current.id)] : list.map(p=>p.id===current.id ? current : p));
      showToast?.(attempt.body.action==="send" ? "Marked as sent. No supplier message was sent by this action." : attempt.body.action==="archive" ? "Order archived with its history retained." : "Order command saved.");
      onInventoryChange?.();
    } catch(e) {
      if (!alive.current) return;
      if (e?.response?.status>=400 && e.response.status<500) setPending(null);
      const detail=e?.response?.data?.detail;
      setError(typeof detail==="string" ? detail : e.message || "Order action failed. Your note is retained.");
    } finally {if(alive.current)setBusy(false);}
  }
  return <section className="space-y-4">
    <PageTitle>Reviewed Purchase Orders</PageTitle>
    <p>Review a current order before changing its state. Prices are planning estimates; invoice-linked receiving records purchases independently. Actions use the signed-in reviewer. Archiving retains the draft and its history.</p>
    <button className={btnGhost} disabled={busy || !!pending} onClick={load}>Refresh reviewed orders</button>
    <label className="block">Review / rejection note<textarea aria-label="Order command note" className={inpCls} value={note} disabled={busy || !!pending} onChange={e=>setNote(e.target.value)} /></label>
    {pending && <button className={btnAcc} disabled={busy} onClick={()=>command({id:pending.ref})}>Retry the same order command</button>}
    {pending && <p>Awaiting confirmation. A retry uses the same request and cannot repeat the transition or create another draft.</p>}
    {error && <p role="alert">{error}</p>}
    {orders.map(po=><div key={po.id} className={`${cardCls} p-4`}>
      <h2>{po.vendor} · {po.status} · {po.id}</h2><p>Version {po.orderVersion} · Estimate {po.total==null ? "unknown / incomplete" : `$${po.total}`} · Created by {po.creatorActor || "unverified legacy identity"}</p>
      <ul>{po.lines.map((l,i)=><li key={i}>{l.name} · {l.vendorSku} · {l.qty} {l.purchaseUnit} · {l.unitCost==null ? "Price unknown" : `$${l.unitCost} per ${l.purchaseUnit}`}</li>)}</ul>
      <div className="flex gap-2">{(actions[po.status]||[]).map(a=><button key={a} className={btnAcc} disabled={busy || !!pending || (a==="reject" && !note.trim())} onClick={()=>command(po,a)}>{a}</button>)}
        <button className={btnGhost} disabled={busy || !!pending || !note.trim()} onClick={()=>command(po,"reorder")}>Create reviewed reorder</button>
      </div>
      {!pending && ["sent","receiving","received"].includes(po.status) && <NativeOrderReceiving key={`${po.id}:${po.orderVersion}`} restaurantId={rid} orderRef={po.id} onSaved={()=>{load();onInventoryChange?.();}} />}
    </div>)}
    {!orders.length && <p>No active orders loaded. Create a reviewed draft in Order Planning.</p>}
  </section>;
}
