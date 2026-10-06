import React, { useCallback, useEffect, useRef, useState } from "react";
import * as api from "../lib/api";
import { Field, inpCls, btnAcc, btnGhost } from "./common";

function detail(e) {
  const d = e?.response?.data?.detail;
  return typeof d === "string" ? d : Array.isArray(d) ? d.map(r => r.msg).join("; ") : e.message || "Reconciliation failed";
}

export function NativeOrderReconciliation({ restaurantId, orderRef, receiptId, onSaved, onClose }) {
  const [data, setData] = useState(null), [choices, setChoices] = useState({}), [note, setNote] = useState("");
  const [reviewed, setReviewed] = useState(false), [plan, setPlan] = useState(null), [busy, setBusy] = useState(false);
  const [error, setError] = useState(""), [message, setMessage] = useState(""), [conflict, setConflict] = useState(false);
  const pending = useRef(null), mounted = useRef(false), generation = useRef(0);
  const accept = useCallback(d => {
    if (!d.receipt || !d.document?.id || !Array.isArray(d.document.currentMappings)) throw new Error("Current linked invoice could not be confirmed.");
    setData(d);
    // Every line needs a fresh match; previous selections do not verify a corrected source.
    setChoices(Object.fromEntries(d.document.currentMappings.filter(m => m.classification === "food" && m.movement_kind === "receipt").map(m => [m.line_id, ""])));
  }, []);
  useEffect(() => {
    mounted.current = true; const turn = ++generation.current;
    api.nativeOrderReconciliationSetup(restaurantId, orderRef, receiptId).then(d => { if (mounted.current && turn === generation.current) accept(d); })
      .catch(e => { if (mounted.current && turn === generation.current) setError(detail(e)); });
    return () => { mounted.current = false; generation.current += 1; };
  }, [restaurantId, orderRef, receiptId, accept]);
  const frozen = busy || !!plan || !!pending.current || !!message;
  const lines = data?.document.currentMappings.filter(m => m.classification === "food" && m.movement_kind === "receipt") || [];
  async function preview() {
    setBusy(true); setError("");
    try {
      if (!data || !reviewed || !note.trim() || Object.values(choices).some(v => !v)) throw new Error("Choose an order match or explicitly confirm an extra for every corrected receipt, then review the comparison.");
      const body = { document_version_id: data.document.id, lines: Object.entries(choices).map(([source_line_id, match]) => ({ source_line_id, po_line_id: match === "extra" ? null : match, verified: true })), variances_reviewed: true, note };
      const r = await api.previewNativeOrderReconciliation(restaurantId, orderRef, receiptId, body);
      if (!r.planHash || !Array.isArray(r.comparison) || !r.review || r.receiptId !== receiptId || r.poRef !== orderRef) throw new Error("Corrected comparison was not confirmed.");
      if (mounted.current) setPlan(r);
    } catch (e) { if (mounted.current) setError(detail(e)); }
    finally { if (mounted.current) setBusy(false); }
  }
  async function confirm() {
    setBusy(true); setError("");
    try {
      if (!pending.current) pending.current = { key: crypto.randomUUID(), body: { ...plan.review, expected_plan_hash: plan.planHash } };
      const r = await api.reconcileNativeOrderReceipt(restaurantId, orderRef, receiptId, pending.current.body, pending.current.key);
      if (!r.reconciliation?.id || r.reconciliation.receipt_id !== receiptId || r.reconciliation.reviewed_plan?.planHash !== pending.current.body.expected_plan_hash || r.reconciliation.reviewed_plan?.poRef !== orderRef) throw new Error("Saved reconciliation was not confirmed. Retry this same review.");
      if (mounted.current) setMessage("Order comparison reconciled. Purchase quantities and food cost were not posted again.");
      try { await onSaved?.(r); } catch (e) { if (mounted.current) setError(`Reconciliation saved; order refresh failed: ${e.message}`); }
    } catch (e) { if (mounted.current) { setError(detail(e)); setConflict(e?.response?.status === 409); } }
    finally { if (mounted.current) setBusy(false); }
  }
  async function refresh() {
    setBusy(true);
    try {
      const d = await api.nativeOrderReconciliationSetup(restaurantId, orderRef, receiptId);
      if (mounted.current) { accept(d); pending.current = null; setPlan(null); setReviewed(false); setConflict(false); setError(""); }
    } catch (e) { if (mounted.current) setError(detail(e)); }
    finally { if (mounted.current) setBusy(false); }
  }
  return <section aria-label="Corrected invoice reconciliation" className="border border-amber-500/40 p-3 rounded space-y-3">
    <h4 className="font-semibold">Review corrected invoice against this order</h4>
    <p>This replaces one delivery comparison and retains its earlier history. It leaves the order's completion status and original ordered quantity unchanged. Track 1 follows the invoice correction independently.</p>
    {data && <>
      <p>Invoice {data.document.header?.document_number} · previous comparison revision {data.receipt.reconciliation_revision || 0}</p>
      {data.receipt.reviewed_plan.receiptLines.map(l => <p key={l.source_line_id}>Previous delivery: {l.description || l.item_code} · {l.base_quantity} {l.base_unit} · received {l.receivedDate}</p>)}
      {!lines.length && <p role="alert">The corrected invoice has no purchased-food receipts. Confirming removes the previous delivery quantity from this order comparison only.</p>}
      {lines.map(l => <Field key={l.line_id} label={`${data.document.lines.find(s => s.id === l.line_id)?.description_snapshot || l.item_code}: corrected ${l.base_quantity} ${l.base_unit}, received ${l.inventory_record_date}`}>
        <select aria-label={`Reconcile receipt ${l.line_id}`} className={inpCls} disabled={frozen} value={choices[l.line_id]} onChange={e => { setChoices(c => ({ ...c, [l.line_id]: e.target.value })); setReviewed(false); }}>
          <option value="">Choose order match or confirm extra</option><option value="extra">Retain as off-order extra</option>{data.lines.filter(s => s.item_code === l.item_code).map(s => <option key={s.id} value={s.id}>{s.name} · ordered {s.qty} {s.unit} · line {s.position + 1}</option>)}
        </select></Field>)}
      <Field label="Reconciliation evidence"><input aria-label="Reconciliation evidence" className={inpCls} disabled={frozen} value={note} onChange={e => { setNote(e.target.value); setReviewed(false); }} /></Field>
      <label><input aria-label="Review corrected order comparison" type="checkbox" disabled={frozen} checked={reviewed} onChange={e => setReviewed(e.target.checked)} /> I reviewed every corrected receipt, extras and shortages against the frozen order.</label>
      {!plan && <button className={btnAcc} disabled={busy || !reviewed || !data.receipt.stale || Object.values(choices).some(v => !v)} onClick={preview}>Preview corrected order comparison</button>}
    </>}
    {plan && <div aria-label="Corrected order comparison">{plan.comparison.map(r => <p key={r.po_line_id}>{r.name}: previously received {r.beforeReceivedBase} {r.baseUnit}; corrected total {r.receivedBase} {r.baseUnit}; ordered {r.orderedBaseQuantity} {r.baseUnit}; difference {r.differenceBase}</p>)}
      {plan.blocks.map(b => <p role="alert" key={b}>{b}</p>)}{plan.warnings?.map(w => <p role="alert" key={w}>{w}</p>)}
      {!!plan.otherStaleReceiptIds?.length && <p role="alert">Other linked invoices still need reconciliation before another delivery can be linked.</p>}
      <button className={btnAcc} disabled={busy || plan.status !== "ready" || !!message} onClick={confirm}>{pending.current ? "Retry same reconciliation" : "Confirm corrected order comparison"}</button>
      {!pending.current && <button className={btnGhost} disabled={busy} onClick={() => { setPlan(null); setReviewed(false); }}>Revise corrected comparison</button>}
    </div>}
    {conflict && <button className={btnGhost} disabled={busy} onClick={refresh}>Refresh changed reconciliation</button>}
    <button className={btnGhost} disabled={busy || (!!pending.current && !message)} onClick={onClose}>Close reconciliation review</button>
    {error && <p role="alert">{error}</p>}{message && <p role="status">{message}</p>}
  </section>;
}
