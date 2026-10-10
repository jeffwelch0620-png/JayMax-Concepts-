import React, { useState } from "react";
import * as api from "../lib/api";
import { isOrderEnabled, fmtMoney } from "../lib/calc";
import { PageTitle, cardCls, inpCls, btnAcc } from "./common";
import { NativeInventoryPosition } from "./NativeInventoryPosition";

export function NativeOrderPlanner({ items, rid, showToast, onCreatedPO }) {
  const [choices, setChoices] = useState({}), [note, setNote] = useState("");
  const [verified, setVerified] = useState(false), [busy, setBusy] = useState(false), [uncertain, setUncertain] = useState(false), [error, setError] = useState("");
  const frozen = busy || uncertain;
  const rows = items.filter(it => isOrderEnabled(it) && it.classification === "raw").map(item => {
    const skus = (item.vendorSkus || []).filter(s => s.available !== false);
    const choice = choices[item.itemCode] || {};
    return { item, skus, sku: skus.find(s => s.id === choice.sku) || skus.find(s => s.preferred) || skus[0], qty: choice.qty || "" };
  });
  const selected = rows.filter(r => r.qty !== "" && Number(r.qty) > 0 && Number.isFinite(Number(r.qty)));
  const vendors = [...new Set(selected.map(r => r.sku?.vendor).filter(Boolean))];
  const invalid = rows.some(r => r.qty !== "" && (!Number.isFinite(Number(r.qty)) || Number(r.qty) <= 0 || !r.sku?.vendor || !r.sku?.purchaseUnit || !r.item.itemCode));
  function change(code, patch) { setChoices(values => ({ ...values, [code]: { ...values[code], ...patch } })); setVerified(false); }
  async function create(vendor) {
    setBusy(true); setError("");
    const group = selected.filter(r => r.sku.vendor === vendor);
    try {
      const lines = group.map(r => ({ itemCode: r.item.itemCode, controlNumber: r.item.controlNumber, name: r.item.name,
        vendorSku: r.sku.vendorSku || "", qty: Number(r.qty), purchaseUnit: r.sku.purchaseUnit,
        unitCost: Number(r.sku.price) || 0 }));
      const saved = await api.createOrder(rid, { vendor, createdBy: api.currentSession()?.user?.email || "", note, lines });
      if (!saved?.id || saved.restaurantId !== rid || saved.status !== "draft" || !Array.isArray(saved.lines) || saved.lines.length !== lines.length || lines.some(line => !saved.lines.some(r => r.itemCode === line.itemCode && Number(r.qty) === line.qty && r.purchaseUnit === line.purchaseUnit))) throw new Error("Draft save was not confirmed.");
      setChoices(values => Object.fromEntries(Object.entries(values).filter(([code]) => !group.some(r => r.item.itemCode === code))));
      setVerified(false); showToast?.(`Reviewed draft created for ${vendor}`); onCreatedPO?.();
    } catch (e) {
      const status = e?.response?.status;
      if (!(status >= 400 && status < 500)) setUncertain(true);
      setError(typeof e?.response?.data?.detail === "string" ? e.response.data.detail : e.message || "Order draft could not be saved.");
    } finally { setBusy(false); }
  }
  return <section className="space-y-4" data-testid="native-order-planner">
    <PageTitle>Reviewed Order Planning</PageTitle>
    <NativeInventoryPosition restaurantId={rid} />
    <p>Enter the quantity you intend to order in the selected supplier's purchase unit. Pars and catalog prices are planning references. No shortfall or order quantity is inferred from old stock, recipe portions or a dated count.</p>
    <div className={`${cardCls} overflow-auto`}><table className="ops-table"><thead><tr><th>Item</th><th>Supplier / SKU</th><th>Par reference</th><th>Order quantity</th><th>Catalog price estimate</th></tr></thead><tbody>{rows.map(r => <tr key={r.item.itemCode}>
      <td>{r.item.name} ({r.item.controlNumber})</td>
      <td><select aria-label={`Order supplier ${r.item.itemCode}`} className={inpCls} value={r.sku?.id || ""} disabled={frozen} onChange={e => change(r.item.itemCode, { sku: e.target.value, qty: "" })}><option value="">No available supplier</option>{r.skus.map(s => <option key={s.id} value={s.id}>{s.vendor} · {s.vendorSku} · {s.purchaseUnit}</option>)}</select></td>
      <td>{r.item.par} {r.item.countUnit || "unconfirmed unit"}</td>
      <td><input aria-label={`Order quantity ${r.item.itemCode}`} className={inpCls} inputMode="decimal" value={r.qty} disabled={frozen || !r.sku?.purchaseUnit} onChange={e => change(r.item.itemCode, { qty: e.target.value })} /> {r.sku?.purchaseUnit}</td>
      <td>{Number(r.sku?.price) > 0 ? `${fmtMoney(r.sku.price)} / ${r.sku.purchaseUnit}` : "Price unconfirmed"}</td>
    </tr>)}</tbody></table></div>
    {!rows.length && <p>No purchased food items are enabled for ordering. Review Item Setup.</p>}
    <label>Order quantity evidence and planning note<textarea aria-label="Order planning evidence" className={inpCls} value={note} disabled={frozen} onChange={e => { setNote(e.target.value); setVerified(false); }} /></label>
    <label className="block"><input aria-label="Confirm reviewed order quantities" type="checkbox" checked={verified} disabled={frozen} onChange={e => setVerified(e.target.checked)} /> I reviewed these quantities and supplier units. The last count is not live on-hand.</label>
    {invalid && <p role="alert">Enter a positive quantity with a registered purchased item and available supplier, or clear that row.</p>}
    {vendors.map(vendor => <button key={vendor} className={btnAcc} disabled={frozen || invalid || !verified || !note.trim()} onClick={() => create(vendor)}>Create reviewed draft for {vendor}</button>)}
    {error && <p role="alert">{error}</p>}
    {uncertain && <p>Outcome is uncertain. Check Purchase Orders for the saved draft before creating another. Automatic retries are held to avoid duplicate drafts.</p>}
  </section>;
}
