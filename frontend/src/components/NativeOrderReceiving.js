import React, { useEffect, useRef, useState } from "react";
import * as api from "../lib/api";
import { Field, inpCls, btnAcc, btnGhost } from "./common";
import { NativeOrderReconciliation } from "./NativeOrderReconciliation";

export function NativeOrderReceiving({ restaurantId, orderRef, onSaved }) {
  const [data, setData] = useState(null), [version, setVersion] = useState(""), [source, setSource] = useState(null), [choices, setChoices] = useState({});
  const [note, setNote] = useState(""), [complete, setComplete] = useState(false), [reviewed, setReviewed] = useState(false), [plan, setPlan] = useState(null);
  const [busy, setBusy] = useState(false), [error, setError] = useState(""), [message, setMessage] = useState("");
  const [conflict, setConflict] = useState(false);
  const [reconciling, setReconciling] = useState(null);
  const pending = useRef(null), mounted = useRef(true), epoch = useRef(0);
  useEffect(() => {
    mounted.current = true;
    api.nativeOrderReceiptSetup(restaurantId, orderRef).then(d => mounted.current && setData(d)).catch(e => mounted.current && setError(e?.response?.data?.detail || e.message));
    return () => { mounted.current = false; epoch.current += 1; };
  }, [restaurantId, orderRef]);
  const frozen = busy || !!plan || !!pending.current;
  async function selectInvoice(id) {
    setVersion(id); setSource(null); setChoices({}); setReviewed(false); setError(""); const requestEpoch = ++epoch.current;
    if (!id) return;
    setBusy(true);
    try {
      const doc = await api.purchaseFileDocument(restaurantId, id);
      if (mounted.current && requestEpoch === epoch.current) { setSource(doc); setChoices(Object.fromEntries(doc.currentMappings.filter(m => m.classification === "food" && m.movement_kind === "receipt").map(m => [m.line_id, ""]))); }
    } catch (e) { if (mounted.current) setError(e?.response?.data?.detail || e.message); }
    finally { if (mounted.current) setBusy(false); }
  }
  async function preview() {
    setBusy(true); setError("");
    try {
      if (!source || !reviewed || !note.trim()) throw new Error("Select the posted invoice and review this delivery.");
      const body = { document_version_id: version, lines: Object.entries(choices).map(([source_line_id, target]) => ({ source_line_id, po_line_id: target || null, verified: true })), complete_order: complete, variances_reviewed: true, note };
      const r = await api.previewNativeOrderReceipt(restaurantId, orderRef, body);
      if (!r.planHash || !Array.isArray(r.comparison) || !Array.isArray(r.receiptLines) || !r.review) throw new Error("Receiving comparison was not confirmed.");
      setPlan(r);
    } catch (e) { setError(e?.response?.data?.detail || e.message); }
    finally { setBusy(false); }
  }
  async function confirm() {
    setBusy(true); setError("");
    try {
      if (!pending.current) pending.current = { key: crypto.randomUUID(), body: { ...plan.review, expected_plan_hash: plan.planHash } };
      const r = await api.linkNativeOrderReceipt(restaurantId, orderRef, pending.current.body, pending.current.key);
      if (!r.receipt?.id || r.receipt.reviewed_plan?.planHash !== pending.current.body.expected_plan_hash || r.receipt.reviewed_plan?.poRef !== orderRef) throw new Error("Saved delivery link was not confirmed. Retry the same review.");
      setMessage("Delivery linked to its recorded purchase. No second inventory quantity or cost was added.");
      try { await onSaved?.(r); } catch (e) { setError(`Delivery saved; order-list refresh failed: ${e.message}`); }
    } catch (e) { setError(e?.response?.data?.detail || e.message); setConflict(e?.response?.status === 409); }
    finally { setBusy(false); }
  }
  async function refreshReview() {
    setBusy(true);
    try {
      const d = await api.nativeOrderReceiptSetup(restaurantId, orderRef);
      setData(d); pending.current = null; setPlan(null); setVersion(""); setSource(null); setChoices({});
      setReviewed(false); setConflict(false); setError("");
    } catch (e) { setError(e?.response?.data?.detail || e.message); }
    finally { setBusy(false); }
  }
  return <section className="mt-3 border border-sky-500/30 rounded p-3 space-y-3" aria-label="Native order receiving">
    <h3 className="font-semibold">Invoice-linked delivery review</h3><p>Post the verified received-date purchase in Invoice Master first. Receiving links that purchase to this order and compares physical quantities; order estimates do not become food cost.</p>
    {data?.history.map(h => <div key={h.id}><p>{h.confirmed_at} · {h.note} · {h.stale ? "Linked invoice changed — reconciliation required" : "Invoice link current"} · comparison revision {h.reconciliation_revision || 0}</p>{h.reviewed_plan.comparison.map(r => <p key={r.po_line_id}>{r.name}: {r.receivedBase} {r.baseUnit} received against {r.orderedBaseQuantity} {r.baseUnit} ordered at that review · difference {r.differenceBase}</p>)}
      {!!h.reconciliations?.length && <details><summary>Earlier comparison history</summary>
        <p>Original review: {h.original_reviewed_plan?.receiptLines.map(l => `${l.base_quantity} ${l.base_unit}`).join(", ")}</p>
        {h.reconciliations.map(n => <p key={n.id}>Revision {n.revision} · {n.confirmed_at} · {n.confirmed_by} · {n.note} · {n.reviewed_plan.receiptLines.map(l => `${l.base_quantity} ${l.base_unit}`).join(", ") || "No purchased-food receipts"}</p>)}
      </details>}
      {h.stale && data.reconciliationReady && <button className={btnGhost} disabled={frozen || !!reconciling} onClick={() => setReconciling(h.id)}>Reconcile corrected invoice</button>}
    </div>)}
    {reconciling && <NativeOrderReconciliation key={reconciling} restaurantId={restaurantId} orderRef={orderRef} receiptId={reconciling} onClose={() => setReconciling(null)} onSaved={async r => {
      const d = await api.nativeOrderReceiptSetup(restaurantId, orderRef); setData(d);
      await onSaved?.(r);
    }} />}
    {data && !reconciling && ["sent", "receiving"].includes(data.order.status) && <>
      <Field label="Current posted invoice"><select aria-label="Order received invoice" className={inpCls} disabled={frozen} value={version} onChange={e => selectInvoice(e.target.value)}><option value="">Choose recorded purchase</option>{data.invoices.map(i => <option key={i.document_version_id} value={i.document_version_id}>{i.document_number}</option>)}</select></Field>
      {source?.currentMappings.filter(m => m.classification === "food" && m.movement_kind === "receipt").map(m => <Field key={m.line_id} label={`${source.lines.find(l => l.id === m.line_id)?.description_snapshot || m.item_code}: ${m.base_quantity} ${m.base_unit}, received ${m.inventory_record_date}`}><select aria-label={`Match receipt ${m.line_id}`} className={inpCls} value={choices[m.line_id]} disabled={frozen} onChange={e => { setChoices(c => ({ ...c, [m.line_id]: e.target.value })); setReviewed(false); }}><option value="">Not on this order — retained as invoice extra</option>{data.lines.filter(l => l.item_code === m.item_code).map(l => <option key={l.id} value={l.id}>{l.name} · ordered {l.qty} {l.unit} · line {l.position + 1}</option>)}</select></Field>)}
      <Field label="Delivery evidence and explanations"><input aria-label="Order receipt evidence" className={inpCls} disabled={frozen} value={note} onChange={e => { setNote(e.target.value); setReviewed(false); }} /></Field>
      <label className="block"><input aria-label="Finish purchase order" type="checkbox" disabled={frozen} checked={complete} onChange={e => { setComplete(e.target.checked); setReviewed(false); }} /> No further deliveries are expected for this order, including reviewed shortages.</label>
      <label className="block"><input aria-label="Review received order quantities" type="checkbox" disabled={frozen} checked={reviewed} onChange={e => setReviewed(e.target.checked)} /> I reviewed the receipt matches, extras, shortages and overages.</label>
      {!plan && <button className={btnAcc} disabled={busy || !reviewed} onClick={preview}>Preview delivery comparison</button>}
    </>}
    {plan && <div aria-label="Delivery comparison">{plan.comparison.map(r => <p key={r.po_line_id}>{r.name}: ordered {r.orderedBaseQuantity} {r.baseUnit}; received total {r.receivedBase} {r.baseUnit}; difference {r.differenceBase}</p>)}{plan.blocks.map(b => <p role="alert" key={b}>{b}</p>)}
      <button className={btnAcc} disabled={busy || plan.status !== "ready" || !!message} onClick={confirm}>{pending.current ? "Retry same delivery link" : "Confirm invoice-linked delivery"}</button>
      {!pending.current && <button className={btnGhost} disabled={busy} onClick={() => { setPlan(null); setReviewed(false); }}>Revise delivery review</button>}
    </div>}
    {conflict && <button className={btnGhost} disabled={busy} onClick={refreshReview}>Refresh changed delivery review</button>}
    {error && <p role="alert">{error}</p>}{message && <p role="status">{message}</p>}
  </section>;
}
