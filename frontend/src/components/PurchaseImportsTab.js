import React, { useEffect, useMemo, useRef, useState } from "react";
import * as api from "../lib/api";
import { PageTitle, Field, cardCls, inpCls, btnAcc, btnGhost } from "./common";
import { ManualPurchaseEntry } from "./ManualPurchaseEntry";
import { InventoryUnitSetup } from "./InventoryUnitSetup";
import { purchaseRecoveryOutcome, validatePurchaseDocument } from "../lib/purchaseRecovery";
import { pendingPurchaseJournal, pendingPurchaseRecord } from "../lib/pendingPurchases";
import { pendingCorrectionJournal, pendingCorrectionRecord, correctionRecoveryOutcome } from "../lib/pendingCorrections";
import { PURCHASE_BASE_UNITS as units } from "../lib/purchaseContract";

const errorText = e => {
  const detail = e?.response?.data?.detail;
  return typeof detail === "string" ? detail : detail?.reasons?.join("; ") || detail?.message || e.message || "Request failed. Please retry.";
};
const empty = value => value === "" || value == null ? null : value;

function RetainedCorrectionEvidence({ record: r }) {
  return <>
    <h4>{r.documentNumber || r.versionId}</h4><p>Reason: {r.body.reason}</p>
    <p>Received date: {r.body.received_date || "Not stated"} · Previous correction: {r.body.expected_correction_id || "Initial invoice"}</p>
    {r.body.lines.map(l => <p key={l.line_id}>Retained line {l.line_id}: {l.item_code || l.classification} · {l.received_quantity ?? "No quantity"} {l.received_unit} · conversion {l.base_units_per_received_unit ?? "Not applicable"} · {l.note}</p>)}
    {["before", "after"].map(side => <div key={side}><p>{side === "before" ? "Original entries to reverse" : "Reviewed replacement entries"}</p>{r.comparison[side].map((l, i) => <p key={`${l.line_id}:${i}`}>{l.item_code || l.classification} · {l.base_quantity} {l.base_unit} · food amount {l.inventory_cost_amount} · {l.inventory_record_date}</p>)}</div>)}
    <p>Separate fees: {r.comparison.feesBefore ?? "Not stated"} → {r.comparison.feesAfter ?? "Not stated"} · Separate tax: {r.comparison.taxBefore ?? "Not stated"} → {r.comparison.taxAfter ?? "Not stated"}</p>
  </>;
}

export function PurchaseDocumentReview({ document, items, history, onPost, onCheckSaved, onInspectSaved, busy, correctionMode = false }) {
  const mappings = correctionMode ? document.currentMappings || [] : [];
  const retained = !correctionMode ? document.pendingRequest : null;
  const [receivedDate, setReceivedDate] = useState(retained?.body.received_date ?? mappings.find(m => m.movement_kind === "receipt")?.inventory_record_date ?? "");
  const [currencyConfirmed, setCurrencyConfirmed] = useState(retained?.body.confirmed_currency === "USD");
  const [reviews, setReviews] = useState(() => Object.fromEntries(document.lines.map(line => {
    const retainedLine = retained?.body.lines.find(r => r.line_id === line.id);
    if (retainedLine) return [line.id, { ...retainedLine,
      item_code: retainedLine.item_code ?? "", base_unit: retainedLine.base_unit ?? "", received_quantity: retainedLine.received_quantity ?? "",
      received_unit: retainedLine.received_unit ?? "", base_units_per_received_unit: retainedLine.base_units_per_received_unit ?? "",
      movement_date: retainedLine.movement_date ?? "", original_line_id: retainedLine.original_line_id ?? "" }];
    const m = mappings.find(r => r.line_id === line.id);
    const u = line.unitProfileSuggestion;
    return [line.id, {
      line_id: line.id, classification: m?.classification || "food", movement_kind: m?.movement_kind || (document.header.document_type === "credit" ? "price_credit" : "receipt"),
      item_code: m?.item_code || u?.item_code || "", base_unit: m?.base_unit || u?.base_unit || "", received_quantity: m?.received_quantity ?? line.shipped_quantity_source ?? "", received_unit: m?.received_unit || u?.source_unit || "",
      base_units_per_received_unit: m?.base_units_per_received_unit || u?.base_units_per_source_unit || "", movement_date: m?.inventory_record_date || "", original_line_id: m?.credit_original_line_id || "", verified: false, note: "",
    }];
  })));
  const [error, setError] = useState("");
  const [savedStatus, setSavedStatus] = useState("");
  const [checkingSaved, setCheckingSaved] = useState(false);
  const [savedDetails, setSavedDetails] = useState(null), [detailsError, setDetailsError] = useState("");
  const request = useRef(retained ? { key: retained.key, body: retained.body } : null);
  function change(id, patch) {
    // Freeze a submitted review until its outcome is known. Retry the same key.
    setReviews(r => ({ ...r, [id]: { ...r[id], ...patch, verified: patch.verified ?? false } }));
  }
  async function post() {
    setError("");
    setSavedStatus("");
    if (!request.current) {
      const lines = document.lines.map(line => {
        const r = reviews[line.id];
        if (!r.verified || !r.note.trim()) throw new Error("Confirm each line and add a review note.");
        return { ...r, item_code: empty(r.item_code), base_unit: empty(r.base_unit),
          received_quantity: r.classification === "food" && ["receipt", "physical_return"].includes(r.movement_kind) ? empty(r.received_quantity) : null,
          received_unit: empty(r.received_unit), base_units_per_received_unit: empty(r.base_units_per_received_unit),
          movement_date: empty(r.movement_date), original_line_id: empty(r.original_line_id) };
      });
      if (!currencyConfirmed) throw new Error("Confirm the invoice currency.");
      request.current = { key: crypto.randomUUID(), body: { confirmed_currency: "USD", received_date: empty(receivedDate), lines } };
    }
    try { await onPost(document.id, request.current.body, request.current.key); }
    catch (e) { if (correctionMode) request.current = null; setError(errorText(e)); }
  }
  async function checkSaved() {
    setCheckingSaved(true); setSavedStatus(""); setError(""); setSavedDetails(null);
    try {
      const outcome = await onCheckSaved(document.id, request.current.key);
      if (outcome?.kind === "awaiting_review") setSavedStatus("No posted outcome was visible in this read. Keep this review frozen and retry the same request, or check again.");
    } catch (e) { setSavedStatus(`Saved status could not be confirmed: ${errorText(e)}`); }
    finally { setCheckingSaved(false); }
  }
  const recovery = document.recovery;
  const corrected = recovery?.kind === "saved_corrected";
  const posted = document.status === "posted" || corrected;
  const blockedRetry = ["held", "other_request"].includes(recovery?.kind);
  const frozen = posted || busy || !!request.current;
  const header = document.header;
  return <section className={`${cardCls} p-4 space-y-4`} aria-label={`Invoice ${header.document_number}`}>
    <h3 className="text-lg font-semibold">{header.vendor_id} · {header.document_number} · {corrected ? "original purchase saved; since corrected" : document.status.replaceAll("_", " ")}</h3>
    <p className="text-sm text-slate-400">Supplier date: {header.invoice_date || "Missing"} · Line total: {document.totals.lineTotal ?? "Missing"} · Supplier total: {document.totals.statedTotal ?? "Missing"} {header.confirmed_currency}</p>
    <p className="text-sm">Fees: {header.fees_source ?? "Not separately stated"} · Tax: {header.tax_source ?? "Not separately stated"} · Unexplained difference: {document.totals.difference ?? "Unknown"}</p>
    {!corrected && !!document.errors.length && <div role="alert" className="text-amber-300">Held for review: {document.errors.join("; ")}</div>}
    {corrected && <p role="status">Your original purchase was saved and has since been corrected. Review the current saved purchase and correction history.</p>}
    {recovery?.kind === "other_request" && <p role="alert">This invoice was posted by a different request or version. Your frozen review is retained. Compare it with the saved purchase and correction history before making changes.</p>}
    {recovery?.kind === "held" && <p role="alert">Held for review: {recovery.document.errors.join("; ") || "The source needs manager review."} Check its status again after the source or correction history has been reviewed. Your original request is retained.</p>}
    {!posted && <Field label="Date goods were received (inventory date of record)"><input type="date" aria-label="Received date" className={inpCls} value={receivedDate} disabled={frozen} onChange={e => setReceivedDate(e.target.value)} /></Field>}
    {!posted && <label className="text-sm flex gap-2"><input aria-label="Confirm USD currency" type="checkbox" checked={currencyConfirmed} disabled={frozen} onChange={e => setCurrencyConfirmed(e.target.checked)} />I verified that the supplier amounts are in USD.</label>}
    {document.lines.map((line, index) => {
      const r = reviews[line.id]; const food = r.classification === "food"; const physical = ["receipt", "physical_return"].includes(r.movement_kind);
      return <fieldset key={line.id} disabled={frozen} className="border border-slate-700 rounded-lg p-3 space-y-3">
        <legend className="text-sm font-semibold">Line {index + 1}: {line.description_snapshot || "No description"}</legend>
        <p className="text-xs text-slate-400">SKU {line.vendor_sku_snapshot || "—"} · Pack {line.pack_description_raw || "—"} · Ordered {line.ordered_quantity_source ?? "—"} · Shipped {line.shipped_quantity_source ?? "—"} · Weight {line.weight_source ?? "—"} · Billed {line.extended_amount_source ?? "—"} · Pricing unit {line.pricing_unit_raw || line.vendor_uom_raw || "—"}</p>
        {!!line.suggestions?.length && <p className="text-xs text-slate-400">SKU matches to verify: {line.suggestions.map(s => `${s.name} (${s.item_code})`).join(", ")}</p>}
        {!posted && <>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
            <Field label="Classification"><select aria-label={`Classification ${index + 1}`} className={inpCls} value={r.classification} onChange={e => change(line.id, { classification: e.target.value, movement_kind: e.target.value === "food" ? "receipt" : "no_inventory", item_code: "", base_unit: "" })}>{["food", "nonfood", "fee", "tax"].map(v => <option key={v}>{v}</option>)}</select></Field>
            {food && <>
              <Field label="Inventory movement"><select className={inpCls} value={r.movement_kind} onChange={e => change(line.id, { movement_kind: e.target.value })}>{["receipt", "physical_return", "price_credit", "no_inventory"].map(v => <option value={v} key={v}>{v.replaceAll("_", " ")}</option>)}</select></Field>
              <Field label="Inventory item"><select aria-label={`Item ${index + 1}`} className={inpCls} value={r.item_code} onChange={e => change(line.id, { item_code: e.target.value })}><option value="">Choose an item</option>{items.map(it => <option key={it.code} value={it.code}>{it.name} ({it.code})</option>)}</select></Field>
              <Field label="Fixed inventory unit"><select className={inpCls} value={r.base_unit} onChange={e => change(line.id, { base_unit: e.target.value })}><option value="">Choose a unit</option>{units.map(u => <option key={u}>{u}</option>)}</select></Field>
              {physical && <>
                <Field label="Actual quantity received / returned"><input aria-label={`Received quantity ${index + 1}`} className={inpCls} value={r.received_quantity} onChange={e => change(line.id, { received_quantity: e.target.value })} inputMode="decimal" /></Field>
                <Field label="Received quantity unit (case, lb, each…)"><input className={inpCls} value={r.received_unit} onChange={e => change(line.id, { received_unit: e.target.value })} /></Field>
                <Field label="Inventory units per received unit"><input className={inpCls} value={r.base_units_per_received_unit} onChange={e => change(line.id, { base_units_per_received_unit: e.target.value })} inputMode="decimal" /></Field>
              </>}
              {["physical_return", "price_credit"].includes(r.movement_kind) && <Field label="Return / credit inventory date"><input type="date" className={inpCls} value={r.movement_date} onChange={e => change(line.id, { movement_date: e.target.value })} /></Field>}
              {r.movement_kind === "price_credit" && <Field label="Original purchase"><select className={inpCls} value={r.original_line_id} onChange={e => change(line.id, { original_line_id: e.target.value })}><option value="">Choose original receipt</option>{history.filter(h => h.current_receipt !== false && h.vendor_id === header.vendor_id && h.item_code === r.item_code && Number(h.base_quantity) > 0).map(h => <option key={h.fact_id || h.line_id} value={h.line_id}>{h.document_number} · {h.description_snapshot} · {h.inventory_record_date}</option>)}</select></Field>}
            </>}
            <Field label="Review note"><input aria-label={`Note ${index + 1}`} className={inpCls} value={r.note} onChange={e => change(line.id, { note: e.target.value })} /></Field>
          </div>
          <label className="text-sm flex gap-2"><input type="checkbox" checked={r.verified} onChange={e => change(line.id, { verified: e.target.checked })} />I verified the classification, item, quantity and conversion for this line.</label>
        </>}
      </fieldset>;
    })}
    {error && <p role="alert" className="text-red-300">{error}</p>}
    {savedStatus && <p role="status">{savedStatus}</p>}
    {retained?.needsCheck && <p role="status">Restored submitted review. Check saved status before retrying; no purchase is sent automatically.</p>}
    {(recovery?.document?.header?.posted_batch_id || header.posted_batch_id) && onInspectSaved && <button className={btnGhost} disabled={busy || checkingSaved} onClick={async () => {
      setDetailsError(""); setSavedDetails(null);
      try { setSavedDetails(await onInspectSaved(document.id)); } catch (e) { setDetailsError(errorText(e)); }
    }}>Show saved purchase and correction history</button>}
    {detailsError && <p role="alert">{detailsError}</p>}
    {savedDetails && <div aria-label="Saved purchase comparison" className="space-y-3">
      <p>Current saved purchase: {savedDetails.document.header.document_number}. These values are read-only.</p>
      <div className="overflow-auto"><table className="text-sm w-full"><thead><tr>{["Item / classification", "Received quantity", "Received unit", "Inventory unit", "Conversion", "Inventory date", "Review note"].map(h => <th key={h}>{h}</th>)}</tr></thead><tbody>{savedDetails.document.currentMappings.map(m => <tr key={m.id || m.line_id}><td>{m.item_code || m.classification}</td><td>{m.received_quantity ?? "—"}</td><td>{m.received_unit || "—"}</td><td>{m.base_unit || "—"}</td><td>{m.base_units_per_received_unit ?? "—"}</td><td>{m.inventory_record_date || "—"}</td><td>{m.decision_note || "—"}</td></tr>)}</tbody></table></div>
      {!savedDetails.document.currentMappings.length && <p>Posted line review details are unavailable. Check the purchase history below.</p>}
      {!savedDetails.corrections.length ? <p>No corrections recorded.</p> : savedDetails.corrections.map(c => <p key={c.id}>{c.corrected_at} · {c.reason} · Previous correction: {c.previous_correction_id || "Initial invoice"}</p>)}
    </div>}
    {!posted && <div className="flex gap-3 flex-wrap">
      <button className={btnAcc} disabled={busy || checkingSaved || blockedRetry || retained?.needsCheck || !currencyConfirmed || document.status === "held" || document.lines.some(l => !reviews[l.id].verified || !reviews[l.id].note.trim())} onClick={() => post().catch(e => setError(errorText(e)))}>{correctionMode ? "Preview invoice correction" : request.current ? "Retry same purchase posting" : "Confirm and post purchase"}</button>
      {request.current && !correctionMode && onCheckSaved && <button className={btnGhost} disabled={busy || checkingSaved} onClick={checkSaved}>{checkingSaved ? "Checking saved status…" : "Check saved status"}</button>}
      {request.current && !busy && <p className="text-xs text-slate-400">This review is frozen until the saved outcome is confirmed. Retry safely or reopen the captured file to check its status.</p>}
    </div>}
  </section>;
}

export function PurchaseCorrectionReview({ document, items, history, onPreview, onCorrect, onHistory, busy }) {
  const [editing, setEditing] = useState(false), [reason, setReason] = useState("");
  const [plan, setPlan] = useState(null), [epoch, setEpoch] = useState(0), [savedHistory, setSavedHistory] = useState(null);
  const [error, setError] = useState(""); const pending = useRef(null);
  async function preview(id, body) {
    if (!reason.trim()) throw new Error("Explain why this invoice needs correction.");
    const result = await onPreview(id, { ...body, reason });
    if (!result.planHash || !result.initialBatchId || !result.review || !Array.isArray(result.before) || !Array.isArray(result.after) || !result.separateComponents || !["ready", "held"].includes(result.status)) throw new Error("Correction preview was not confirmed. Try again.");
    setPlan(result); setError("");
  }
  async function confirm() {
    setError("");
    if (!pending.current) pending.current = { key: crypto.randomUUID(), body: { ...plan.review,
      expected_plan_hash: plan.planHash, expected_initial_batch_id: plan.initialBatchId, expected_correction_id: plan.previousCorrectionId } };
    try { await onCorrect(document.id, pending.current.body, pending.current.key, plan); }
    catch (e) { setError(errorText(e)); }
  }
  return <section className={`${cardCls} p-4 space-y-3`} aria-label="Posted invoice correction">
    <p className="text-sm">Corrections retain the original invoice. Its current entries are reversed and the reviewed replacement is saved together.</p>
    {!editing && <button className={btnGhost} disabled={busy} onClick={() => setEditing(true)}>Review correction</button>}
    {onHistory && <button className={btnGhost} disabled={busy} onClick={async () => {
      try { setSavedHistory(await onHistory(document.id)); setError(""); } catch (e) { setError(errorText(e)); }
    }}>Show correction history</button>}
    {savedHistory && <div>{savedHistory.length === 0 ? <p>No corrections recorded.</p> : savedHistory.map(c => <div key={c.id} className="border border-slate-700 p-3">
      <p>{c.corrected_at} · {c.corrected_by} · {c.reason}</p>
      <p>{c.reviewed_plan.before.length} original entries reversed · {c.reviewed_plan.after.length} replacement entries · Previous correction: {c.previous_correction_id || "Initial invoice"}</p>
    </div>)}</div>}
    {editing && <>
      <Field label="Reason and evidence for this correction"><input aria-label="Correction reason" className={inpCls} value={reason} disabled={busy || !!plan || !!pending.current} onChange={e => setReason(e.target.value)} /></Field>
      <PurchaseDocumentReview key={epoch} document={{ ...document, status: "awaiting_review", errors: document.sourceErrors || [] }} items={items} history={history} onPost={preview} busy={busy} correctionMode />
    </>}
    {plan && <div className="space-y-3" aria-label="Correction comparison">
      <h3 className="font-semibold">Review reversal and replacement</h3>
      <p>Reason: {plan.review.reason}</p>
      <div className="overflow-auto"><table className="text-sm w-full"><thead><tr>{["Action", "Item / classification", "Quantity", "Unit", "Food amount", "Inventory date"].map(h => <th className="text-left p-2" key={h}>{h}</th>)}</tr></thead><tbody>{[...plan.before.map(r => ({ ...r, action: "Reverse" })), ...plan.after.map(r => ({ ...r, action: "Replace" }))].map((r, i) => <tr key={`${r.action}:${r.line_id}`}><td className="p-2">{r.action} original entry</td><td>{r.item_code || r.classification} · {r.description}</td><td>{r.base_quantity}</td><td>{r.base_unit || "—"}</td><td>{r.inventory_cost_amount}</td><td>{r.inventory_record_date || "—"}</td></tr>)}</tbody></table></div>
      <p className="text-xs">Reversals cancel the quantities and food amounts shown above. Taxes and fees stay outside food amounts.</p>
      <p>Separate fees: {plan.separateComponents.before.fees_source ?? "Not stated"} → {plan.separateComponents.after.fees_source ?? "Not stated"} · Separate tax: {plan.separateComponents.before.tax_source ?? "Not stated"} → {plan.separateComponents.after.tax_source ?? "Not stated"}</p>
      {plan.blocks.map(b => <p role="alert" className="text-amber-300" key={b}>{b}</p>)}
      {plan.affectedPeriods.map(p => <p key={p.id}>Closed period: {p.period_start} to before {p.period_end_exclusive}. Reopen it and later periods on the Actual Inventory dashboard, then refresh this preview.</p>)}
      {plan.legacyClosedPeriods.map(p => <p key={p.id}>Legacy closed period: {p.period_start} through {p.period_end}. Reconciliation required.</p>)}
      {plan.linkedDocuments.map(d => <p key={d.line_id}>Linked document: {d.document_number}. Receipt correction is held for reconciliation.</p>)}
      <button className={btnAcc} disabled={busy || plan.status !== "ready"} onClick={confirm}>{pending.current ? "Retry same invoice correction" : "Confirm reversal and replacement"}</button>
      {!pending.current && <button className={btnGhost} disabled={busy} onClick={() => { setPlan(null); setEpoch(n => n + 1); }}>Revise / refresh correction</button>}
      {pending.current && <p className="text-xs">Review frozen until the saved outcome is confirmed. Retry the same correction or reopen the file to inspect history.</p>}
    </div>}
    {error && <p role="alert" className="text-red-300">{error}</p>}
  </section>;
}

export function PurchaseImportsTab({ restaurantId, restaurantName, actorId, unitReviewFocus, onUnitReviewSaved }) {
  const [files, setFiles] = useState([]), [items, setItems] = useState([]), [history, setHistory] = useState([]);
  const [selected, setSelected] = useState(null), [sourceRows, setSourceRows] = useState(null);
  const [busy, setBusy] = useState(false), [error, setError] = useState(""), [message, setMessage] = useState("");
  const [ready, setReady] = useState(false), [more, setMore] = useState(false);
  const [reportingReady, setReportingReady] = useState(false);
  const [previewEpoch, setPreviewEpoch] = useState(0);
  const [manualReady, setManualReady] = useState(false), [vendors, setVendors] = useState([]);
  const [uploadKind, setUploadKind] = useState("csv"), [manualEpoch, setManualEpoch] = useState(0);
  const [unitsReady, setUnitsReady] = useState(false);
  const upload = useRef(null);
  const scope = useMemo(() => ({ active: true, restaurantId, actorId }), [restaurantId, actorId]);
  const journal = useMemo(() => pendingPurchaseJournal(actorId, restaurantId), [actorId, restaurantId]);
  const correctionJournal = useMemo(() => pendingCorrectionJournal(actorId, restaurantId), [actorId, restaurantId]);
  const [pendingCorrections, setPendingCorrections] = useState([]), [correctionChecks, setCorrectionChecks] = useState({});
  const [correctionRecoveryUnavailable, setCorrectionRecoveryUnavailable] = useState(false);
  const [correctionDiscard, setCorrectionDiscard] = useState(null);
  const [pendingPurchases, setPendingPurchases] = useState([]), [recoveryUnavailable, setRecoveryUnavailable] = useState(false);
  const [discardReview, setDiscardReview] = useState(null);
  function refreshCorrections() {
    try { const records = correctionJournal.list(); if (scope.active) { setPendingCorrections(records); setCorrectionRecoveryUnavailable(false); } return records; }
    catch (e) { if (scope.active) { setCorrectionRecoveryUnavailable(true); setError(errorText(e)); } throw e; }
  }
  function currentCorrection(record) {
    if (!scope.active) throw new Error("The signed-in user or restaurant changed. Reopen this correction.");
    const current = refreshCorrections().find(r => r.versionId === record.versionId && r.key === record.key);
    if (!current || JSON.stringify(current) !== JSON.stringify(record)) throw new Error("The retained correction changed. Check its saved status again.");
    return current;
  }
  function clearCorrection(record) {
    correctionJournal.clear(record.versionId, record.key); refreshCorrections();
  }
  async function checkCorrection(record) {
    await action(async () => {
      const current = currentCorrection(record);
      setCorrectionChecks(s => ({ ...s, [current.key]: null }));
      const result = await api.checkCorrectionSavedStatus(restaurantId, current.versionId, current.body, current.key);
      if (!scope.active) return;
      currentCorrection(current);
      const outcome = correctionRecoveryOutcome(result, current, actorId);
      setCorrectionChecks(s => ({ ...s, [current.key]: outcome }));
      if (["saved", "saved_replaced"].includes(outcome.outcome)) {
        setMessage(outcome.outcome === "saved" ? "Your invoice correction was saved and confirmed."
          : "Your invoice correction was saved and has a later replacement. Review the current invoice history.");
        // A saved result closes only this exact request. Read failures never do.
        try { clearCorrection(current); }
        catch (e) { setCorrectionRecoveryUnavailable(true); throw new Error(`Correction saved; retained-review cleanup failed: ${errorText(e)}`); }
        setSelected(null);
        api.purchaseHistory(restaurantId).then(h => scope.active && setHistory(h)).catch(e => scope.active && setError(`Correction saved; history refresh failed: ${errorText(e)}`));
      }
    });
  }
  async function retryCorrection(record) {
    if (correctionChecks[record.key]?.outcome !== "retry_available") return;
    await action(async () => {
      const current = currentCorrection(record);
      setCorrectionChecks(s => ({ ...s, [current.key]: null }));
      await sendCorrection(current);
    });
  }
  async function correctionDiscardStatus(record) {
    const current = currentCorrection(record);
    setCorrectionChecks(s => ({ ...s, [current.key]: null }));
    const result = await api.checkCorrectionSavedStatus(restaurantId, current.versionId, current.body, current.key);
    if (!scope.active) return null;
    currentCorrection(current);
    const outcome = correctionRecoveryOutcome(result, current, actorId);
    // Preparing/confirming discard never grants retry permission from this read.
    if (["saved", "saved_replaced"].includes(outcome.outcome)) {
      throw new Error("Your original correction was saved. It was not discarded. Use Check saved correction status to inspect and resolve it.");
    }
    return { record: current, outcome };
  }
  async function prepareCorrectionDiscard(record) {
    setCorrectionDiscard(null);
    await action(async () => {
      const choice = await correctionDiscardStatus(record);
      if (choice) setCorrectionDiscard(choice);
    });
  }
  async function confirmCorrectionDiscard() {
    const choice = correctionDiscard;
    if (!choice || !scope.active) return;
    setCorrectionDiscard(null);
    await action(async () => {
      // The earlier read only opened the dialog. Check again at confirmation:
      // the original request may have committed while the dialog was open.
      const checked = await correctionDiscardStatus(choice.record);
      if (!checked) return;
      currentCorrection(checked.record);
      clearCorrection(checked.record);
      setSelected(null); setPreviewEpoch(n => n + 1); setSourceRows(null);
      setMessage("Retained correction discarded from this tab only. Reopen the current invoice and preview again. No source, purchase or accounting history was deleted. Discard does not cancel the original request; it may still complete. Source and period holds still apply.");
    });
  }
  function refreshPending() {
    try { const records = journal.list(); if (scope.active) { setPendingPurchases(records); setRecoveryUnavailable(false); } return records; }
    catch (e) { if (scope.active) { setRecoveryUnavailable(true); setError(errorText(e)); } throw e; }
  }
  function resolvePending(id, key) {
    try { journal.clear(id, key); refreshPending(); }
    catch (e) { if (scope.active) { setRecoveryUnavailable(true); setError(`Purchase saved; retained-review cleanup failed: ${errorText(e)}`); } }
  }
  function retainFile(result) {
    const records = refreshPending();
    return { ...result, documents: result.documents.map(d => {
      const record = records.find(r => r.versionId === d.id);
      if (!record) return d;
      let outcome;
      try { outcome = purchaseRecoveryOutcome(d, record.versionId, record.key); }
      catch { return { ...record.document, pendingRequest: { key: record.key, body: record.body, needsCheck: true } }; }
      if (["saved", "saved_corrected"].includes(outcome.kind)) {
        resolvePending(record.versionId, record.key);
        return { ...d, recovery: outcome };
      }
      return { ...record.document, recovery: outcome, pendingRequest: { key: record.key, body: record.body, needsCheck: false } };
    }) };
  }
  useEffect(() => {
    scope.active = true;
    setSelected(null); setPendingPurchases([]); setDiscardReview(null); setReady(false); setError(""); setMessage("");
    setBusy(false); setFiles([]); setItems([]); setHistory([]); setSourceRows(null); upload.current = null;
    setPendingCorrections([]); setCorrectionChecks({}); setCorrectionDiscard(null);
    try { setPendingCorrections(correctionJournal.list()); setCorrectionRecoveryUnavailable(false); }
    catch (e) { setCorrectionRecoveryUnavailable(true); setError(errorText(e)); }
    try { setPendingPurchases(journal.list()); setRecoveryUnavailable(false); }
    catch (e) { setRecoveryUnavailable(true); setError(errorText(e)); }
    Promise.all([api.purchaseCapabilities(restaurantId), api.purchaseItems(restaurantId)]).then(async ([capabilities, list]) => {
      if (!scope.active) return;
      setReady(capabilities.enabled); setReportingReady(!!capabilities.reportingReady); setItems(list);
      setManualReady(!!capabilities.manualReady);
      setUnitsReady(!!capabilities.unitsReady);
      if (capabilities.manualReady) {
        const suppliers = await api.purchaseVendors(restaurantId);
        if (scope.active) setVendors(suppliers);
      }
      if (capabilities.enabled) {
        const [f, h] = await Promise.all([api.purchaseFiles(restaurantId), api.purchaseHistory(restaurantId)]);
        if (scope.active) { setFiles(f); setMore(f.length === 200); setHistory(h); }
      }
    }).catch(e => scope.active && setError(errorText(e)));
    return () => { scope.active = false; };
  }, [restaurantId, scope, journal, correctionJournal]);
  async function action(fn) {
    if (!scope.active) return;
    setBusy(true); setError(""); setMessage("");
    try { await fn(); } catch (e) { if (scope.active) setError(errorText(e)); } finally { if (scope.active) setBusy(false); }
  }
  async function capture() {
    if (!upload.current) return;
    await action(async () => {
      const captureFn = upload.current.kind === "source" ? api.capturePurchaseSource : api.capturePurchase;
      const result = await captureFn(restaurantId, upload.current.file, upload.current.key);
      if (!result.id || result.captureStatus !== "captured" || !Array.isArray(result.documents)) throw new Error("Source capture was not confirmed. Retry the same file.");
      if (!scope.active) return;
      setSelected(result); setPreviewEpoch(n => n + 1); setSourceRows(null); setMessage("Original file retained. Review each invoice before posting.");
      upload.current = null;
      const f = await api.purchaseFiles(restaurantId); if (scope.active) { setFiles(f); setMore(f.length === 200); }
    });
  }
  async function captureManual(body, key) {
    setBusy(true); setError(""); setMessage("");
    try {
      const result = await api.captureManualPurchase(restaurantId, body, key);
      if (!result?.id || result.captureStatus !== "captured" || !result.manualRecord || !Array.isArray(result.documents)) throw new Error("Source capture was not confirmed. Retry the same entry.");
      if (!scope.active) return result;
      setSelected(result); setPreviewEpoch(n => n + 1); setManualEpoch(n => n + 1); setSourceRows(null);
      setMessage("Manual source retained. Review every purchase line before posting to inventory.");
      api.purchaseFiles(restaurantId).then(f => { if (scope.active) { setFiles(f); setMore(f.length === 200); } }).catch(e => scope.active && setError(`Source retained; file-list refresh failed: ${errorText(e)}`));
      return result;
    } finally { if (scope.active) setBusy(false); }
  }
  function applyRecovery(id, outcome) {
    const own = ["saved", "saved_corrected"].includes(outcome.kind);
    // Only our original request may close this review. Keep the submitted
    // fields and component key intact for a hold or another request's posting.
    setSelected(s => ({ ...s, documents: s.documents.map(d => d.id === id ? { ...(own ? outcome.document : d), recovery: outcome,
      ...(!own && d.pendingRequest ? { pendingRequest: { ...d.pendingRequest, needsCheck: false } } : {}) } : d) }));
    if (own) setMessage(outcome.kind === "saved_corrected"
      ? "Your original purchase was saved and has since been corrected. Review the correction history."
      : "Your purchase was saved and confirmed. Taxes and fees remain separate.");
    if (outcome.document.header.posted_batch_id) api.purchaseHistory(restaurantId)
      .then(h => scope.active && setHistory(h))
      .catch(e => scope.active && setError(`Saved purchase history refresh failed: ${errorText(e)}`));
  }
  async function post(id, body, key) {
    if (!scope.active) throw new Error("The signed-in user or restaurant changed. Reopen this review before posting.");
    setBusy(true);
    setMessage("");
    try {
      const document = selected.documents.find(d => d.id === id);
      if (document.discardedRequestKey && !journal.list().some(r => r.versionId === id)) {
        const result = await api.checkPurchaseSavedStatus(restaurantId, id);
        if (!scope.active) return;
        const outcome = purchaseRecoveryOutcome(result, id, document.discardedRequestKey);
        if (result.header.document_id !== document.header.document_id) throw new Error("Saved document identity was not confirmed.");
        if (outcome.kind !== "awaiting_review") {
          setSelected(s => ({ ...s, documents: s.documents.map(d => d.id === id ? result : d) }));
          setPreviewEpoch(n => n + 1);
          const notice = "The invoice changed after discard. Review its current saved status or hold; no new posting was sent.";
          setMessage(notice);
          throw new Error(notice);
        }
      }
      const record = pendingPurchaseRecord(selected, document, body, key);
      const submitted = journal.save(record); refreshPending();
      const result = await api.postPurchase(restaurantId, id, submitted.body, submitted.key);
      if (!result?.batchId || result.document?.header?.posted_batch_id !== result.batchId) throw new Error("Saved outcome was not confirmed. Retry this request.");
      let outcome;
      try { outcome = purchaseRecoveryOutcome(result.document, id, key); }
      catch { throw new Error("Saved outcome was not confirmed. Retry this request."); }
      if (!["saved", "saved_corrected"].includes(outcome.kind)) throw new Error("Saved outcome was not confirmed. Retry this request.");
      resolvePending(id, key);
      if (!scope.active) return;
      applyRecovery(id, outcome);
    } catch (e) {
      // An earlier request can commit after a negative read. Reconcile a conflict
      // without resending or interpreting another request's batch as our save.
      if (e?.response?.status === 409 && scope.active) {
        try { await checkSaved(id, key); } catch { /* Keep the original command on a failed read. */ }
      }
      throw e;
    } finally { if (scope.active) setBusy(false); }
  }
  async function checkSaved(id, key) {
    setBusy(true);
    setMessage("");
    try {
      const result = await api.checkPurchaseSavedStatus(restaurantId, id);
      const outcome = purchaseRecoveryOutcome(result, id, key);
      if (["saved", "saved_corrected"].includes(outcome.kind)) resolvePending(id, key);
      if (!scope.active) return;
      applyRecovery(id, outcome);
      return outcome;
    } finally { if (scope.active) setBusy(false); }
  }
  async function restorePending(record) {
    await action(async () => {
      const current = refreshPending().find(r => r.versionId === record.versionId && r.key === record.key);
      if (!current) throw new Error("This retained review is no longer available. Reopen its saved source.");
      setSelected({ ...current.source, documents: [{ ...current.document,
        pendingRequest: { key: current.key, body: current.body, needsCheck: true } }] });
      setPreviewEpoch(n => n + 1); setSourceRows(null);
      await checkSaved(current.versionId, current.key);
    });
  }
  function currentRetained(record) {
    const current = refreshPending().find(r => r.versionId === record.versionId && r.key === record.key);
    if (!current) throw new Error("This retained review is no longer available. Reopen its saved source.");
    if (JSON.stringify(current.body) !== JSON.stringify(record.body)) throw new Error("The retained review changed. Restore it before trying again.");
    return current;
  }
  function discardOutcome(result, record) {
    const outcome = purchaseRecoveryOutcome(result, record.versionId, record.key);
    if (result.header.document_id !== record.document.header.document_id) throw new Error("Saved document identity was not confirmed. The retained review was not discarded.");
    if (result.status === "awaiting_review" && (result.errors.length || result.header.posted_batch_id)) throw new Error("Saved document status was not confirmed. The retained review was not discarded.");
    if (["saved", "saved_corrected"].includes(outcome.kind)) throw new Error("Your original request was saved. The review was not discarded; restore it to inspect the saved purchase.");
    return outcome;
  }
  function discardSource(outcome, record) {
    // Already-posted reviews keep the existing saved-purchase/correction path.
    if (outcome.kind === "other_request") return null;
    const source = outcome.document.currentSource;
    if (!source || source.documentId !== record.document.header.document_id
      || typeof source.versionId !== "string" || !source.versionId
      || typeof source.fileId !== "string" || !source.fileId
      || !Number.isSafeInteger(source.revision) || source.revision < 1
      || !Number.isSafeInteger(outcome.document.header.revision) || outcome.document.header.revision < 1
      || source.revision < outcome.document.header.revision
      || ((source.versionId === record.versionId) !== (source.revision === outcome.document.header.revision))) {
      throw new Error("Current source was not confirmed. The retained review was not discarded. Reload or check again.");
    }
    return source;
  }
  function sameSource(a, b) {
    return a?.documentId === b?.documentId && a?.versionId === b?.versionId
      && a?.fileId === b?.fileId && a?.revision === b?.revision;
  }
  async function prepareDiscard(record) {
    await action(async () => {
      const current = currentRetained(record);
      const result = await api.checkPurchaseSavedStatus(restaurantId, current.versionId);
      if (!scope.active) return;
      const outcome = discardOutcome(result, current);
      setDiscardReview({ record: current, outcome, source: discardSource(outcome, current) });
    });
  }
  async function confirmDiscard() {
    const choice = discardReview;
    if (!choice || !scope.active) return;
    await action(async () => {
      const current = currentRetained(choice.record);
      // Fetch the source before the second status read so a failed reopening
      // cannot consume the recovery copy. Confirmation never trusts cached status.
      const fileId = choice.source?.fileId ?? current.source.id;
      const file = await api.purchaseFile(restaurantId, fileId);
      if (!scope.active) return;
      if (file?.id !== fileId || !Array.isArray(file.documents)) throw new Error("Saved source was not confirmed. The retained review was not discarded.");
      for (const document of file.documents) {
        if (typeof document?.id !== "string" || !document.id || typeof document.header?.document_id !== "string" || !document.header.document_id) throw new Error("Saved source identity was not confirmed. The retained review was not discarded.");
        validatePurchaseDocument(document, document.id);
      }
      const candidates = file.documents.filter(d => d.header.document_id === current.document.header.document_id
        && (!choice.source || (d.id === choice.source.versionId && d.header.revision === choice.source.revision)));
      if (candidates.length !== 1) throw new Error("Saved source identity was not confirmed. The retained review was not discarded.");
      const sourceDocument = candidates[0];
      if (choice.source && !sameSource(sourceDocument.currentSource, choice.source)) throw new Error("Current source changed. The retained review was not discarded. Cancel and check again.");
      const result = await api.checkPurchaseSavedStatus(restaurantId, current.versionId);
      if (!scope.active) return;
      const outcome = discardOutcome(result, current);
      if (outcome.kind !== "other_request" && !sameSource(discardSource(outcome, current), choice.source)) throw new Error("Current source changed. The retained review was not discarded. Cancel and check again.");
      currentRetained(current);
      journal.clear(current.versionId, current.key);
      refreshPending();
      const reopened = retainFile(file);
      setSelected({ ...reopened, documents: reopened.documents.map(d => d.id === current.versionId
        ? { ...outcome.document, discardedRequestKey: current.key }
        : d.header.document_id === current.document.header.document_id
          ? { ...d, discardedRequestKey: current.key, ...(outcome.kind === "other_request" ? { recovery: outcome } : {}) } : d) });
      setPreviewEpoch(n => n + 1); setSourceRows(null); setDiscardReview(null);
      setMessage(outcome.kind === "other_request"
        ? "Retained review discarded. This invoice already has a saved purchase; inspect it and use correction review if needed."
        : "Retained review discarded. Review the current source again before posting. Discard did not cancel the earlier request; it may still complete.");
      if (outcome.document.header.posted_batch_id) api.purchaseHistory(restaurantId)
        .then(h => scope.active && setHistory(h))
        .catch(e => scope.active && setError(`Saved purchase history refresh failed: ${errorText(e)}`));
    });
  }
  async function inspectSaved(id) {
    setBusy(true);
    try {
      const original = selected.documents.find(d => d.id === id);
      const known = original.recovery?.document || original;
      const currentId = known.header.posted_version_id;
      const current = validatePurchaseDocument(await api.purchaseFileDocument(restaurantId, currentId), currentId);
      const corrections = await api.purchaseCorrections(restaurantId, id);
      const scalar = value => value == null || ["string", "number"].includes(typeof value);
      const fields = ["id", "line_id", "item_code", "classification", "received_quantity", "received_unit", "base_unit", "base_units_per_received_unit", "inventory_record_date", "decision_note"];
      if (current.status !== "posted" || current.header.posted_version_id !== currentId
        || current.header.posted_batch_id !== known.header.posted_batch_id
        || !known.header.document_id || current.header.document_id !== known.header.document_id
        || current.header.current_correction_id !== known.header.current_correction_id
        || !Array.isArray(current.currentMappings) || !current.currentMappings.every(m => m && fields.every(f => scalar(m[f])) && typeof m.line_id === "string")
        || !Array.isArray(corrections) || !corrections.every(c => c && typeof c.id === "string" && typeof c.reason === "string" && typeof c.corrected_at === "string" && scalar(c.previous_correction_id))) {
        throw new Error("Saved purchase details changed or could not be confirmed. Check saved status again.");
      }
      return { document: current, corrections };
    } finally { if (scope.active) setBusy(false); }
  }
  async function loadSourceRows(offset = 0) {
    const rows = await api.purchaseRawRows(restaurantId, selected.id, offset);
    if (scope.active) setSourceRows(rows);
  }
  async function previewCorrection(id, body) {
    if (!scope.active) throw new Error("The signed-in user or restaurant changed. Reopen this correction.");
    const documentId = selected.documents.find(d => d.id === id)?.header.document_id;
    if (refreshCorrections().some(r => r.documentId === documentId)) throw new Error("Resolve the retained submitted correction before starting another review.");
    setBusy(true);
    try { return await api.previewPurchaseCorrection(restaurantId, id, body); }
    finally { if (scope.active) setBusy(false); }
  }
  async function correct(id, body, key, plan) {
    if (!scope.active) throw new Error("The signed-in user or restaurant changed. Reopen this correction.");
    setBusy(true);
    try {
      const document = selected.documents.find(d => d.id === id);
      const record = correctionJournal.save(pendingCorrectionRecord(document, body, key, plan));
      refreshCorrections();
      await sendCorrection(record);
    } catch (e) { if (scope.active) setError(errorText(e)); throw e; }
    finally { if (scope.active) setBusy(false); }
  }
  async function sendCorrection(record) {
      const { versionId: id, body, key } = currentCorrection(record);
      const result = await api.correctPurchase(restaurantId, id, body, key);
      if (!result.correctionId || result.correction?.id !== result.correctionId || result.correction?.idempotency_key !== key
        || result.correction?.corrected_by !== actorId || result.correction?.replacement_version_id !== id
        || result.document?.header?.document_id !== record.documentId || result.document?.header?.posted_batch_id !== body.expected_initial_batch_id
        || (result.isCurrent && result.document?.header?.current_correction_id !== result.correctionId)
        || result.correction?.initial_batch_id !== body.expected_initial_batch_id || result.correction?.previous_correction_id !== body.expected_correction_id || result.correction?.reviewed_plan?.planHash !== body.expected_plan_hash || result.document?.id !== id || typeof result.isCurrent !== "boolean" || (result.isCurrent && result.document.status !== "posted")) throw new Error("Saved correction was not confirmed. Retry this request.");
      if (!scope.active) return;
      try { clearCorrection(record); }
      catch (e) { setCorrectionRecoveryUnavailable(true); throw new Error(`Correction saved; retained-review cleanup failed: ${errorText(e)}`); }
      setSelected(s => s && ({ ...s, documents: s.documents.map(d => d.id === id ? result.document : d) })); setPreviewEpoch(n => n + 1);
      setMessage(result.isCurrent ? "Invoice correction saved and confirmed. Original entries and source files are retained." : "This correction was already saved and has a later replacement. Review the current invoice history.");
      api.purchaseHistory(restaurantId).then(h => scope.active && setHistory(h)).catch(e => scope.active && setError(`Correction saved; history refresh failed: ${errorText(e)}`));
  }
  return <div className="space-y-5">
    <PageTitle>Invoice Master · {restaurantName}</PageTitle>
    <p className="text-sm text-amber-200">{reportingReady
      ? "Confirmed received-date purchases feed Actual Inventory reports. Food Cost requires complete physical counts and confirmed count values. Taxes and fees remain separate."
      : "Purchase review is in build testing. These received-date purchase records are not yet included in Food Cost reports; count scope and historical valuation still need to be connected."}</p>
    {error && <p role="alert" className="text-red-300">{error}</p>}{message && <p role="status" className="text-emerald-300">{message}</p>}
    {!ready ? <p className="text-slate-400">Purchase review setup is awaiting enablement.</p> : <>
      {!!pendingCorrections.length && <section aria-label="Retained submitted corrections" className={`${cardCls} p-4 space-y-4`}>
        <h3>Submitted invoice corrections retained in this tab</h3>
        <p>These frozen requests survive reload and sign-in by the same user in this tab. Check saved status before explicitly retrying. Nothing is sent automatically. New-tab or browser-restart recovery is not guaranteed.</p>
        {pendingCorrections.map(r => <div key={r.key} className="space-y-2 border border-slate-700 p-3">
          <RetainedCorrectionEvidence record={r} />
          {correctionChecks[r.key]?.message && <p role="status">{correctionChecks[r.key].message}</p>}
          <button className={btnGhost} disabled={busy || correctionRecoveryUnavailable || !!correctionDiscard} onClick={() => checkCorrection(r)}>Check saved correction status</button>
          <button className={btnAcc} disabled={busy || correctionRecoveryUnavailable || !!correctionDiscard || correctionChecks[r.key]?.outcome !== "retry_available"} onClick={() => retryCorrection(r)}>Retry exact retained correction</button>
          <button className={btnGhost} disabled={busy || correctionRecoveryUnavailable || !!correctionDiscard || !!discardReview} onClick={() => prepareCorrectionDiscard(r)}>Discard retained correction</button>
          <p>No saved outcome in a read does not cancel an earlier request. Discard requires fresh status and confirmation and removes only this tab's retained copy.</p>
        </div>)}
      </section>}
      {correctionDiscard && <section aria-label="Confirm retained correction discard" className={`${cardCls} p-4 space-y-3`}>
        <h3>Discard retained correction from this tab?</h3>
        <p>The latest read showed {correctionDiscard.outcome.outcome.replaceAll("_", " ")}: {correctionDiscard.outcome.message}</p>
        <RetainedCorrectionEvidence record={correctionDiscard.record} />
        <p>This removes only the frozen request from this tab. It does not delete source files, purchases or accounting history and does not cancel the original request, which may still complete. Confirmation checks status again. Source and period holds still apply; reopen the current invoice and preview before any new correction.</p>
        <button className={btnGhost} disabled={busy} onClick={() => setCorrectionDiscard(null)}>Keep retained correction</button>
        <button className={btnAcc} disabled={busy || correctionRecoveryUnavailable} onClick={confirmCorrectionDiscard}>Confirm discard retained correction</button>
      </section>}
      {!!pendingPurchases.length && <section aria-label="Retained submitted purchases" className={`${cardCls} p-4 space-y-2`}>
        <h3>Submitted reviews retained in this tab</h3>
        <p>These reviews survive a reload and sign-in by the same user in this tab. Restore a review to check its saved outcome before retrying. Keep this tab open until the outcome is confirmed; recovery in a new tab or after a browser restart is not guaranteed.</p>
        {pendingPurchases.map(r => <div key={r.versionId} className="flex gap-3 flex-wrap">
          <button className={btnGhost} disabled={busy || !!discardReview} onClick={() => restorePending(r)}>Restore submitted review: {r.document.header.document_number || r.versionId}</button>
          <button className={btnGhost} disabled={busy || !!discardReview} onClick={() => prepareDiscard(r)}>Discard retained review: {r.document.header.document_number || r.versionId}</button>
        </div>)}
      </section>}
      {discardReview && <section aria-label="Confirm retained review discard" className={`${cardCls} p-4 space-y-3`}>
        <h3>Discard retained review for {discardReview.record.document.header.document_number}</h3>
        <p>The latest read showed {discardReview.outcome.kind.replaceAll("_", " ")}. This removes only this tab's frozen review. It does not delete a source, purchase or history, and does not cancel the earlier request. That request may still complete.</p>
        <p>Confirm to check status again and reopen the current source. If already posted, inspect the saved purchase and use correction review. Nothing will be posted automatically.</p>
        <button className={btnGhost} disabled={busy} onClick={() => setDiscardReview(null)}>Keep retained review</button>
        <button className={btnAcc} disabled={busy} onClick={confirmDiscard}>Confirm discard retained review</button>
      </section>}
      <div className={`${cardCls} p-4 flex gap-3 flex-wrap items-center`}>
        {manualReady && <select aria-label="Source upload type" className={inpCls} disabled={busy} value={uploadKind} onChange={e => { setUploadKind(e.target.value); upload.current = null; }}><option value="csv">PFG / US Foods CSV</option><option value="source">Other invoice / receipt source</option></select>}
        <label className="text-sm">{uploadKind === "csv" ? "PFG or US Foods original CSV" : "Retain original receipt, PDF, photo or other supplier file"} <input key={uploadKind} aria-label="Invoice file" type="file" accept={uploadKind === "csv" ? ".csv,text/csv" : undefined} disabled={busy} onChange={e => { const f = e.target.files?.[0]; upload.current = f ? { file: f, key: crypto.randomUUID(), kind: uploadKind } : null; setMessage(f ? `Ready to capture ${f.name}` : ""); }} /></label>
        <button className={btnAcc} disabled={busy} onClick={capture}>Capture / retry file</button>
      </div>
      {manualReady && <ManualPurchaseEntry key={`${restaurantId}:${manualEpoch}`} vendors={vendors} files={files} onCapture={captureManual} busy={busy} />}
      {unitsReady && <InventoryUnitSetup key={restaurantId} restaurantId={restaurantId} focus={unitReviewFocus} onSaved={onUnitReviewSaved} />}
      <div className={`${cardCls} p-4 space-y-2`}>
        <h3 className="font-semibold">Captured files</h3>
        {files.map(f => <button key={f.id} className={`${btnGhost} mr-2`} disabled={busy} onClick={() => action(async () => { const result = await api.purchaseFile(restaurantId, f.id); if (!scope.active) return; setSelected(retainFile(result)); setPreviewEpoch(n => n + 1); setSourceRows(null); })}>{f.original_filename} · {f.captured_at.slice(0, 10)}</button>)}
        {more && <button className={btnGhost} disabled={busy} onClick={() => action(async () => { const f = await api.purchaseFiles(restaurantId, files.length); if (scope.active) { setFiles([...files, ...f]); setMore(f.length === 200); } })}>Older files</button>}
      </div>
      {selected && <>
        <div className={`${cardCls} p-4 space-y-2`}>
          <p>{selected.original_filename} · {selected.byte_count} bytes retained · {selected.source_record_count} source records</p>
          <p className="text-xs text-slate-500 break-all">File fingerprint: {selected.source_sha256}</p>
          {!!selected.parse_errors?.length && <p role="alert" className="text-amber-300">{selected.parse_errors.join("; ")}</p>}
          {selected.manualRecord && <div aria-label="Retained manual source details"><h3 className="font-semibold">Retained manual source details</h3><p>Supplier: {vendors.find(v => v.id === selected.manualRecord.vendor_id)?.name || selected.manualRecord.vendor_id} · {selected.manualRecord.document_type}</p><p>Source evidence: {selected.manualRecord.evidence_note}</p>
            <dl>{Object.entries(selected.manualRecord.documents).map(([k, v]) => <div key={k}><dt className="inline">{k.replace(/_(source|snapshot|raw|text)$/g, "").replace(/_/g, " ")}: </dt><dd className="inline whitespace-pre-wrap">{v === "" ? "Blank in source record" : v}</dd></div>)}</dl>
            {selected.manualRecord.extra_fields.map((f, i) => <p key={i} className="whitespace-pre-wrap">{f.label}: {f.value === "" ? "Blank in source record" : f.value}</p>)}
            {Object.entries(selected.manualRecord.parties).map(([role, fields]) => <div key={role}><p>{role.replace(/_/g, " ")}</p>{Object.entries(fields).map(([k, v]) => <p key={k}>{k.replace(/_/g, " ")}: {v}</p>)}</div>)}
            {selected.manualRecord.lines.map((line, i) => <details key={i}><summary>Entered source line {i + 1}</summary>{Object.entries(line.fields).map(([k, v]) => <p key={k} className="whitespace-pre-wrap">{k.replace(/_(source|snapshot|raw|text)$/g, "").replace(/_/g, " ")}: {v === "" ? "Blank in source record" : v}</p>)}{line.extra_fields.map((f, n) => <p key={n} className="whitespace-pre-wrap">{f.label}: {f.value === "" ? "Blank in source record" : f.value}</p>)}</details>)}
            {selected.attachments?.map(f => <button className={btnGhost} key={f.id} disabled={busy} onClick={() => action(async () => {
              const blob = await api.purchaseSource(restaurantId, f.id); if (!scope.active) return; const url = URL.createObjectURL(blob); const link = document.createElement("a"); link.href = url; link.download = f.original_filename; link.click(); URL.revokeObjectURL(url);
            })}>Download attached source: {f.original_filename}</button>)}
          </div>}
          <button className={`${btnGhost} mr-2`} disabled={busy} onClick={() => action(async () => {
            const blob = await api.purchaseSource(restaurantId, selected.id); if (!scope.active) return; const url = URL.createObjectURL(blob);
            const link = document.createElement("a"); link.href = url; link.download = selected.original_filename; link.click(); URL.revokeObjectURL(url);
          })}>Download original file</button>
          {selected.parse_run_id && !selected.manualRecord && <button className={btnGhost} disabled={busy} onClick={() => action(() => loadSourceRows())}>Show all source fields</button>}
          {sourceRows && <div className="overflow-auto max-h-96"><table className="text-xs"><thead><tr><th>Record</th>{sourceRows.headers.map((h, i) => <th className="px-2" key={i}>{h} [{i + 1}]</th>)}</tr></thead><tbody>{sourceRows.rows.map(row => <tr key={row.row_ordinal}><td>{row.row_ordinal}</td>{row.raw_values.map((v, i) => <td className="border border-slate-700 p-2 whitespace-nowrap" key={i}>{v}</td>)}</tr>)}</tbody></table>{sourceRows.nextOffset != null && <button className={btnGhost} disabled={busy} onClick={() => action(() => loadSourceRows(sourceRows.nextOffset))}>Next source records</button>}</div>}
        </div>
        {selected.documents.map(d => <PurchaseDocumentReview key={`${previewEpoch}:${selected.id}:${d.id}:${d.status}`} document={d} items={items} history={history} onPost={post} onCheckSaved={checkSaved} onInspectSaved={inspectSaved} busy={busy || recoveryUnavailable || !!discardReview} />)}
        {selected.documents.filter(d => d.correctionAvailable && !pendingCorrections.some(r => r.documentId === d.header.document_id)).map(d => <PurchaseCorrectionReview key={`correction:${previewEpoch}:${scope.actorId}:${d.id}`} document={d} items={items} history={history} onPreview={previewCorrection} onCorrect={correct} onHistory={id => api.purchaseCorrections(restaurantId, id)} busy={busy || correctionRecoveryUnavailable || !!correctionDiscard} />)}
      </>}
      <div className={`${cardCls} p-4 overflow-auto`}><h3 className="font-semibold mb-2">Food purchase history</h3><table className="text-sm w-full"><thead><tr>{["Received / movement date", "Invoice", "Entry", "Item", "Quantity", "Inventory unit", "Food amount"].map(h => <th className="text-left p-2" key={h}>{h}</th>)}</tr></thead><tbody>{history.map(h => <tr key={h.fact_id || h.line_id}><td className="p-2">{h.inventory_record_date}</td><td>{h.document_number}</td><td>{h.fact_kind || "initial"}</td><td>{h.description_snapshot}</td><td>{h.base_quantity}</td><td>{h.base_unit}</td><td>{h.inventory_cost_amount}</td></tr>)}</tbody></table></div>
    </>}
  </div>;
}
