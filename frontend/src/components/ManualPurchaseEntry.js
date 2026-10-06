import React, { useRef, useState } from "react";
import { Field, cardCls, inpCls, btnAcc, btnGhost } from "./common";

const headerFields = [["document_number", "Invoice / receipt number"], ["invoice_date", "Supplier invoice / receipt date"],
  ["customer_number", "Supplier customer number"], ["account_number", "Account number"], ["vendor_branch_reference", "Supplier branch"],
  ["subtotal_source", "Subtotal of all printed lines"], ["fees_source", "Additional fees outside printed lines"],
  ["tax_source", "Additional tax outside printed lines"], ["discount_source", "Invoice discount"], ["total_source", "Supplier total"]];
const lineFields = [["vendor_sku_snapshot", "Supplier product code"], ["description_snapshot", "Description"],
  ["pack_description_raw", "Pack description"], ["shipped_quantity_source", "Supplier shipped quantity"],
  ["pricing_unit_raw", "Supplier pricing unit"], ["unit_price_source", "Supplier unit price"], ["extended_amount_source", "Printed line amount"]];
const newLine = () => ({ fields: Object.fromEntries(lineFields.map(([k]) => [k, ""])), extra_fields: [] });

export function ManualPurchaseEntry({ vendors, files, onCapture, busy }) {
  const [vendor, setVendor] = useState(""), [type, setType] = useState("invoice");
  const [header, setHeader] = useState(Object.fromEntries(headerFields.map(([k]) => [k, ""])));
  const [lines, setLines] = useState([newLine()]), [extras, setExtras] = useState([]);
  const [attachments, setAttachments] = useState([]), [note, setNote] = useState(""), [verified, setVerified] = useState(false);
  const [error, setError] = useState(""); const pending = useRef(null);
  const frozen = busy || !!pending.current;
  function change(fn) { fn(); setVerified(false); }
  function extraRows(values, setValues, label) {
    return <div className="space-y-2"><p>{label}</p>{values.map((v, i) => <div className="flex gap-2" key={i}>
      <input aria-label={`${label} label ${i + 1}`} placeholder="Source label" className={inpCls} disabled={frozen} value={v.label} onChange={e => change(() => setValues(values.map((r, n) => n === i ? { ...r, label: e.target.value } : r)))} />
      <input aria-label={`${label} value ${i + 1}`} placeholder="Exact source value" className={inpCls} disabled={frozen} value={v.value} onChange={e => change(() => setValues(values.map((r, n) => n === i ? { ...r, value: e.target.value } : r)))} />
    </div>)}<button className={btnGhost} disabled={frozen} onClick={() => change(() => setValues([...values, { label: "", value: "" }]))}>Add {label.toLowerCase()}</button></div>;
  }
  async function capture() {
    setError("");
    try {
      if (!pending.current) {
        if (!vendor || !verified || !note.trim()) throw new Error("Select a supplier, explain the source, and confirm the entered details.");
        pending.current = { key: crypto.randomUUID(), body: { vendor_id: vendor, document_type: type, documents: header,
          parties: {}, lines, extra_fields: extras, attachment_ids: attachments, verified_source: true, evidence_note: note } };
      }
      const result = await onCapture(pending.current.body, pending.current.key);
      if (!result?.id || result.captureStatus !== "captured" || !result.manualRecord || !Array.isArray(result.documents)) throw new Error("Source capture was not confirmed. Retry the same entry.");
    } catch (e) {
      const detail = e?.response?.data?.detail;
      setError(typeof detail === "string" ? detail : e.message || "Source capture failed. Retry the same entry.");
    }
  }
  return <section className={`${cardCls} p-4 space-y-4`} aria-label="Manual purchase source entry">
    <h3 className="font-semibold">Manual purchases / other suppliers</h3>
    <p className="text-sm">Enter the supplier's printed figures as shown. Blanks remain unknown; enter 0 only when confirmed. Attach a retained receipt when available, or explain the evidence for a manual record. Inventory quantities and received dates are reviewed in the next step.</p>
    <Field label="Registered supplier"><select aria-label="Manual supplier" className={inpCls} disabled={frozen} value={vendor} onChange={e => change(() => setVendor(e.target.value))}><option value="">Select supplier</option>{vendors.map(v => <option key={v.id} value={v.id}>{v.name}</option>)}</select></Field>
    {!vendors.length && <p>Add this supplier in Vendor Master first.</p>}
    <Field label="Document type"><select aria-label="Manual document type" className={inpCls} disabled={frozen} value={type} onChange={e => change(() => setType(e.target.value))}><option value="invoice">Invoice / receipt</option><option value="credit">Credit</option></select></Field>
    <div className="grid md:grid-cols-2 gap-3">{headerFields.map(([k, label]) => <Field key={k} label={label}><input aria-label={label} className={inpCls} disabled={frozen} value={header[k]} onChange={e => change(() => setHeader({ ...header, [k]: e.target.value }))} /></Field>)}</div>
    <p className="text-xs">Fees and tax already printed as their own lines belong among the lines below; additional totals above apply only to amounts outside those lines. Discounts need an allocation policy and are held for review.</p>
    {lines.map((line, i) => <fieldset key={i} disabled={frozen} className="border border-slate-700 p-3 space-y-3"><legend>Source line {i + 1}</legend><div className="grid md:grid-cols-2 gap-3">{lineFields.map(([k, label]) => <Field key={k} label={label}><input aria-label={`${label} ${i + 1}`} className={inpCls} value={line.fields[k]} onChange={e => change(() => setLines(lines.map((r, n) => n === i ? { ...r, fields: { ...r.fields, [k]: e.target.value } } : r)))} /></Field>)}</div>
      {extraRows(line.extra_fields, values => setLines(lines.map((r, n) => n === i ? { ...r, extra_fields: values } : r)), `Line ${i + 1} additional source field`)}
      {lines.length > 1 && <button className={btnGhost} onClick={() => change(() => setLines(lines.filter((_, n) => n !== i)))}>Remove unsubmitted line {i + 1}</button>}
    </fieldset>)}
    <button className={btnGhost} disabled={frozen} onClick={() => change(() => setLines([...lines, newLine()]))}>Add source line</button>
    {extraRows(extras, setExtras, "Additional invoice field")}
    <p className="text-xs">Use additional fields for addresses, terms, order references and any other details. Duplicate labels and blank values are retained.</p>
    <div className="max-h-40 overflow-auto">{files.map(f => <label key={f.id} className="block"><input type="checkbox" aria-label={`Attach ${f.original_filename}`} disabled={frozen} checked={attachments.includes(f.id)} onChange={e => change(() => setAttachments(e.target.checked ? [...attachments, f.id] : attachments.filter(id => id !== f.id)))} /> {f.original_filename}</label>)}</div>
    <Field label="Source evidence and any unstated identity details"><textarea aria-label="Manual source evidence" className={inpCls} disabled={frozen} value={note} onChange={e => change(() => setNote(e.target.value))} /></Field>
    <label><input aria-label="Confirm manual source details" type="checkbox" disabled={frozen} checked={verified} onChange={e => setVerified(e.target.checked)} /> I checked these source details. This saves a source record for purchase review.</label>
    <button className={btnAcc} disabled={busy || (!pending.current && !verified)} onClick={capture}>{pending.current ? "Retry same manual source" : "Retain manual source for review"}</button>
    {pending.current && <p>Entry frozen until its saved outcome is confirmed. Retry the same entry or reopen its retained source record.</p>}
    {error && <p role="alert" className="text-red-300">{error}</p>}
  </section>;
}
