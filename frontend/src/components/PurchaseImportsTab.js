import React, { useEffect, useRef, useState } from "react";
import * as api from "../lib/api";
import { PageTitle, Field, cardCls, inpCls, btnAcc, btnGhost } from "./common";
import { ManualPurchaseEntry } from "./ManualPurchaseEntry";
import { InventoryUnitSetup } from "./InventoryUnitSetup";

const units = ["lb", "oz", "g", "kg", "fl_oz", "ml", "l", "gal", "each"];
const errorText = e => {
  const detail = e?.response?.data?.detail;
  return typeof detail === "string" ? detail : detail?.reasons?.join("; ") || detail?.message || e.message || "Request failed. Please retry.";
};
const empty = value => value === "" || value == null ? null : value;

export function PurchaseDocumentReview({ document, items, history, onPost, busy, correctionMode = false }) {
  const mappings = correctionMode ? document.currentMappings || [] : [];
  const [receivedDate, setReceivedDate] = useState(mappings.find(m => m.movement_kind === "receipt")?.inventory_record_date || "");
  const [currencyConfirmed, setCurrencyConfirmed] = useState(false);
  const [reviews, setReviews] = useState(() => Object.fromEntries(document.lines.map(line => {
    const m = mappings.find(r => r.line_id === line.id);
    const u = line.unitProfileSuggestion;
    return [line.id, {
      line_id: line.id, classification: m?.classification || "food", movement_kind: m?.movement_kind || (document.header.document_type === "credit" ? "price_credit" : "receipt"),
      item_code: m?.item_code || u?.item_code || "", base_unit: m?.base_unit || u?.base_unit || "", received_quantity: m?.received_quantity ?? line.shipped_quantity_source ?? "", received_unit: m?.received_unit || u?.source_unit || "",
      base_units_per_received_unit: m?.base_units_per_received_unit || u?.base_units_per_source_unit || "", movement_date: m?.inventory_record_date || "", original_line_id: m?.credit_original_line_id || "", verified: false, note: "",
    }];
  })));
  const [error, setError] = useState("");
  const request = useRef(null);
  function change(id, patch) {
    // Freeze a submitted review until its outcome is known. Retry the same key.
    setReviews(r => ({ ...r, [id]: { ...r[id], ...patch, verified: patch.verified ?? false } }));
  }
  async function post() {
    setError("");
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
  const posted = document.status === "posted";
  const frozen = posted || busy || !!request.current;
  const header = document.header;
  return <section className={`${cardCls} p-4 space-y-4`} aria-label={`Invoice ${header.document_number}`}>
    <h3 className="text-lg font-semibold">{header.vendor_id} · {header.document_number} · {document.status.replaceAll("_", " ")}</h3>
    <p className="text-sm text-slate-400">Supplier date: {header.invoice_date || "Missing"} · Line total: {document.totals.lineTotal ?? "Missing"} · Supplier total: {document.totals.statedTotal ?? "Missing"} {header.confirmed_currency}</p>
    <p className="text-sm">Fees: {header.fees_source ?? "Not separately stated"} · Tax: {header.tax_source ?? "Not separately stated"} · Unexplained difference: {document.totals.difference ?? "Unknown"}</p>
    {!!document.errors.length && <div role="alert" className="text-amber-300">Held for review: {document.errors.join("; ")}</div>}
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
    {!posted && <div className="flex gap-3 flex-wrap">
      <button className={btnAcc} disabled={busy || !currencyConfirmed || document.status === "held" || document.lines.some(l => !reviews[l.id].verified || !reviews[l.id].note.trim())} onClick={() => post().catch(e => setError(errorText(e)))}>{correctionMode ? "Preview invoice correction" : request.current ? "Retry same purchase posting" : "Confirm and post purchase"}</button>
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
    try { await onCorrect(document.id, pending.current.body, pending.current.key); }
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

export function PurchaseImportsTab({ restaurantId, restaurantName }) {
  const [files, setFiles] = useState([]), [items, setItems] = useState([]), [history, setHistory] = useState([]);
  const [selected, setSelected] = useState(null), [sourceRows, setSourceRows] = useState(null);
  const [busy, setBusy] = useState(false), [error, setError] = useState(""), [message, setMessage] = useState("");
  const [ready, setReady] = useState(false), [more, setMore] = useState(false);
  const [reportingReady, setReportingReady] = useState(false);
  const [previewEpoch, setPreviewEpoch] = useState(0);
  const [manualReady, setManualReady] = useState(false), [vendors, setVendors] = useState([]);
  const [uploadKind, setUploadKind] = useState("csv"), [manualEpoch, setManualEpoch] = useState(0);
  const [unitsReady, setUnitsReady] = useState(false);
  const upload = useRef(null), mounted = useRef(true);
  useEffect(() => {
    mounted.current = true;
    Promise.all([api.purchaseCapabilities(restaurantId), api.purchaseItems(restaurantId)]).then(async ([capabilities, list]) => {
      if (!mounted.current) return;
      setReady(capabilities.enabled); setReportingReady(!!capabilities.reportingReady); setItems(list);
      setManualReady(!!capabilities.manualReady);
      setUnitsReady(!!capabilities.unitsReady);
      if (capabilities.manualReady) {
        const suppliers = await api.purchaseVendors(restaurantId);
        if (mounted.current) setVendors(suppliers);
      }
      if (capabilities.enabled) {
        const [f, h] = await Promise.all([api.purchaseFiles(restaurantId), api.purchaseHistory(restaurantId)]);
        if (mounted.current) { setFiles(f); setMore(f.length === 200); setHistory(h); }
      }
    }).catch(e => mounted.current && setError(errorText(e)));
    return () => { mounted.current = false; };
  }, [restaurantId]);
  async function action(fn) {
    setBusy(true); setError(""); setMessage("");
    try { await fn(); } catch (e) { setError(errorText(e)); } finally { if (mounted.current) setBusy(false); }
  }
  async function capture() {
    if (!upload.current) return;
    await action(async () => {
      const captureFn = upload.current.kind === "source" ? api.capturePurchaseSource : api.capturePurchase;
      const result = await captureFn(restaurantId, upload.current.file, upload.current.key);
      if (!result.id || result.captureStatus !== "captured" || !Array.isArray(result.documents)) throw new Error("Source capture was not confirmed. Retry the same file.");
      if (!mounted.current) return;
      setSelected(result); setPreviewEpoch(n => n + 1); setSourceRows(null); setMessage("Original file retained. Review each invoice before posting.");
      upload.current = null;
      const f = await api.purchaseFiles(restaurantId); setFiles(f); setMore(f.length === 200);
    });
  }
  async function captureManual(body, key) {
    setBusy(true); setError(""); setMessage("");
    try {
      const result = await api.captureManualPurchase(restaurantId, body, key);
      if (!result?.id || result.captureStatus !== "captured" || !result.manualRecord || !Array.isArray(result.documents)) throw new Error("Source capture was not confirmed. Retry the same entry.");
      if (!mounted.current) return result;
      setSelected(result); setPreviewEpoch(n => n + 1); setManualEpoch(n => n + 1); setSourceRows(null);
      setMessage("Manual source retained. Review every purchase line before posting to inventory.");
      api.purchaseFiles(restaurantId).then(f => { if (mounted.current) { setFiles(f); setMore(f.length === 200); } }).catch(e => mounted.current && setError(`Source retained; file-list refresh failed: ${errorText(e)}`));
      return result;
    } finally { if (mounted.current) setBusy(false); }
  }
  async function post(id, body, key) {
    setBusy(true);
    try {
      const result = await api.postPurchase(restaurantId, id, body, key);
      if (!result.batchId || result.document?.status !== "posted") throw new Error("Saved outcome was not confirmed. Retry this request.");
      if (!mounted.current) return;
      setSelected(s => ({ ...s, documents: s.documents.map(d => d.id === id ? result.document : d) }));
      setMessage("Purchase posted and confirmed. Taxes and fees remain separate.");
      // History refresh is independent of the confirmed posting outcome.
      api.purchaseHistory(restaurantId).then(h => mounted.current && setHistory(h)).catch(e => mounted.current && setError(`Purchase saved; history refresh failed: ${errorText(e)}`));
    } finally { if (mounted.current) setBusy(false); }
  }
  async function previewCorrection(id, body) {
    setBusy(true);
    try { return await api.previewPurchaseCorrection(restaurantId, id, body); }
    finally { if (mounted.current) setBusy(false); }
  }
  async function correct(id, body, key) {
    setBusy(true);
    try {
      const result = await api.correctPurchase(restaurantId, id, body, key);
      if (!result.correctionId || result.correction?.id !== result.correctionId || result.correction?.initial_batch_id !== body.expected_initial_batch_id || result.correction?.previous_correction_id !== body.expected_correction_id || result.correction?.reviewed_plan?.planHash !== body.expected_plan_hash || result.document?.id !== id || typeof result.isCurrent !== "boolean" || (result.isCurrent && result.document.status !== "posted")) throw new Error("Saved correction was not confirmed. Retry this request.");
      if (!mounted.current) return;
      setSelected(s => ({ ...s, documents: s.documents.map(d => d.id === id ? result.document : d) })); setPreviewEpoch(n => n + 1);
      setMessage(result.isCurrent ? "Invoice correction saved and confirmed. Original entries and source files are retained." : "This correction was already saved and has a later replacement. Review the current invoice history.");
      api.purchaseHistory(restaurantId).then(h => mounted.current && setHistory(h)).catch(e => mounted.current && setError(`Correction saved; history refresh failed: ${errorText(e)}`));
    } finally { if (mounted.current) setBusy(false); }
  }
  return <div className="space-y-5">
    <PageTitle>Invoice Master · {restaurantName}</PageTitle>
    <p className="text-sm text-amber-200">{reportingReady
      ? "Confirmed received-date purchases feed Actual Inventory reports. Food Cost requires complete physical counts and confirmed count values. Taxes and fees remain separate."
      : "Purchase review is in build testing. These received-date purchase records are not yet included in Food Cost reports; count scope and historical valuation still need to be connected."}</p>
    {error && <p role="alert" className="text-red-300">{error}</p>}{message && <p role="status" className="text-emerald-300">{message}</p>}
    {!ready ? <p className="text-slate-400">Purchase review setup is awaiting enablement.</p> : <>
      <div className={`${cardCls} p-4 flex gap-3 flex-wrap items-center`}>
        {manualReady && <select aria-label="Source upload type" className={inpCls} disabled={busy} value={uploadKind} onChange={e => { setUploadKind(e.target.value); upload.current = null; }}><option value="csv">PFG / US Foods CSV</option><option value="source">Other invoice / receipt source</option></select>}
        <label className="text-sm">{uploadKind === "csv" ? "PFG or US Foods original CSV" : "Retain original receipt, PDF, photo or other supplier file"} <input key={uploadKind} aria-label="Invoice file" type="file" accept={uploadKind === "csv" ? ".csv,text/csv" : undefined} disabled={busy} onChange={e => { const f = e.target.files?.[0]; upload.current = f ? { file: f, key: crypto.randomUUID(), kind: uploadKind } : null; setMessage(f ? `Ready to capture ${f.name}` : ""); }} /></label>
        <button className={btnAcc} disabled={busy} onClick={capture}>Capture / retry file</button>
      </div>
      {manualReady && <ManualPurchaseEntry key={`${restaurantId}:${manualEpoch}`} vendors={vendors} files={files} onCapture={captureManual} busy={busy} />}
      {unitsReady && <InventoryUnitSetup key={restaurantId} restaurantId={restaurantId} />}
      <div className={`${cardCls} p-4 space-y-2`}>
        <h3 className="font-semibold">Captured files</h3>
        {files.map(f => <button key={f.id} className={`${btnGhost} mr-2`} disabled={busy} onClick={() => action(async () => { setSelected(await api.purchaseFile(restaurantId, f.id)); setPreviewEpoch(n => n + 1); setSourceRows(null); })}>{f.original_filename} · {f.captured_at.slice(0, 10)}</button>)}
        {more && <button className={btnGhost} disabled={busy} onClick={() => action(async () => { const f = await api.purchaseFiles(restaurantId, files.length); setFiles([...files, ...f]); setMore(f.length === 200); })}>Older files</button>}
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
              const blob = await api.purchaseSource(restaurantId, f.id); const url = URL.createObjectURL(blob); const link = document.createElement("a"); link.href = url; link.download = f.original_filename; link.click(); URL.revokeObjectURL(url);
            })}>Download attached source: {f.original_filename}</button>)}
          </div>}
          <button className={`${btnGhost} mr-2`} disabled={busy} onClick={() => action(async () => {
            const blob = await api.purchaseSource(restaurantId, selected.id); const url = URL.createObjectURL(blob);
            const link = document.createElement("a"); link.href = url; link.download = selected.original_filename; link.click(); URL.revokeObjectURL(url);
          })}>Download original file</button>
          {selected.parse_run_id && !selected.manualRecord && <button className={btnGhost} disabled={busy} onClick={() => action(async () => setSourceRows(await api.purchaseRawRows(restaurantId, selected.id)))}>Show all source fields</button>}
          {sourceRows && <div className="overflow-auto max-h-96"><table className="text-xs"><thead><tr><th>Record</th>{sourceRows.headers.map((h, i) => <th className="px-2" key={i}>{h} [{i + 1}]</th>)}</tr></thead><tbody>{sourceRows.rows.map(row => <tr key={row.row_ordinal}><td>{row.row_ordinal}</td>{row.raw_values.map((v, i) => <td className="border border-slate-700 p-2 whitespace-nowrap" key={i}>{v}</td>)}</tr>)}</tbody></table>{sourceRows.nextOffset != null && <button className={btnGhost} disabled={busy} onClick={() => action(async () => setSourceRows(await api.purchaseRawRows(restaurantId, selected.id, sourceRows.nextOffset)))}>Next source records</button>}</div>}
        </div>
        {selected.documents.map(d => <PurchaseDocumentReview key={`${previewEpoch}:${selected.id}:${d.id}:${d.status}`} document={d} items={items} history={history} onPost={post} busy={busy} />)}
        {selected.documents.filter(d => d.correctionAvailable).map(d => <PurchaseCorrectionReview key={`correction:${previewEpoch}:${d.id}`} document={d} items={items} history={history} onPreview={previewCorrection} onCorrect={correct} onHistory={id => api.purchaseCorrections(restaurantId, id)} busy={busy} />)}
      </>}
      <div className={`${cardCls} p-4 overflow-auto`}><h3 className="font-semibold mb-2">Food purchase history</h3><table className="text-sm w-full"><thead><tr>{["Received / movement date", "Invoice", "Entry", "Item", "Quantity", "Inventory unit", "Food amount"].map(h => <th className="text-left p-2" key={h}>{h}</th>)}</tr></thead><tbody>{history.map(h => <tr key={h.fact_id || h.line_id}><td className="p-2">{h.inventory_record_date}</td><td>{h.document_number}</td><td>{h.fact_kind || "initial"}</td><td>{h.description_snapshot}</td><td>{h.base_quantity}</td><td>{h.base_unit}</td><td>{h.inventory_cost_amount}</td></tr>)}</tbody></table></div>
    </>}
  </div>;
}
