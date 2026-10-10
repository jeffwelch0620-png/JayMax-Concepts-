import React, { useEffect, useRef, useState } from "react";
import * as api from "../lib/api";
import { useRetainedDraft } from "../lib/saveIntegrity";
import { cardCls, inpCls, btnAcc, btnGhost } from "./common";
const empty = { item: "", control: "", area: "", countUnit: "", factor: "", suppliers: [], verified: false };
export function SharedCatalogLink({ restaurantId, drafts, onLinked, showToast }) {
  const [form, edit, clear] = useRetainedDraft(`shared-catalog:${restaurantId}`, empty, drafts);
  const [data, setData] = useState(null), [error, setError] = useState(""), [busy, setBusy] = useState(false), [uncertain, setUncertain] = useState(false);
  const alive = useRef(true), reads = useRef(0);
  async function load() {
    const read = ++reads.current; setData(null); setError("");
    try {
      const result = await api.sharedCatalog(restaurantId);
      if (!alive.current || read !== reads.current) return;
      if (!Array.isArray(result?.products) || !Number.isSafeInteger(result?.revision) || result.revision < 0) throw new Error("Shared catalog was not confirmed.");
      setData(result); edit(f => ({ ...f, verified: false }));
    } catch (e) { if (alive.current && read === reads.current) setError(e?.response?.data?.detail || e.message || "Could not load shared products."); }
  }
  useEffect(() => { alive.current = true; load(); return () => { alive.current = false; ++reads.current; }; }, [restaurantId]); // eslint-disable-line react-hooks/exhaustive-deps
  const chosen = data?.products.find(p => p.item_code === form.item);
  const blocked = busy || uncertain || !chosen || chosen.linked || !form.control.trim() || !form.countUnit.trim() || !(Number(form.factor) > 0) || !Number.isFinite(Number(form.factor)) || !form.suppliers.length || !form.verified;
  function change(key, value) { edit(f => ({ ...f, [key]: value, verified: false })); }
  async function submit(e) {
    e.preventDefault(); if (blocked) return;
    const submitted = form; setBusy(true); setError("");
    try {
      const saved = await api.linkSharedItem(restaurantId, { item_code: chosen.item_code, control_number: form.control.trim(), storage_area: form.area || null,
        count_unit: form.countUnit.trim(), base_per_count_unit: form.factor, vendor_item_ids: form.suppliers,
        verified: true, expected_catalog_hash: chosen.catalog_hash }, data.revision);
      if (!saved?.ok || saved.itemCode !== chosen.item_code || saved.controlNumber !== form.control.trim() || !Number.isSafeInteger(saved.revision) || saved.revision <= data.revision) throw new Error("Product link was not confirmed.");
      if (!alive.current) return;
      clear(submitted, empty); showToast?.("Product linked. Review this location's count and supplier unit profiles before use."); onLinked?.(); await load();
    } catch (e) {
      if (!alive.current) return;
      if (!(e?.response?.status >= 400 && e.response.status < 500)) setUncertain(true);
      setError(e?.response?.data?.detail || e.message || "Product link failed. Your entry is retained.");
    } finally { if (alive.current) setBusy(false); }
  }
  return <section className={`${cardCls} p-5 mb-6`} data-testid="shared-catalog-link">
    <h2 className="font-semibold">Use an existing purchased product at this location</h2>
    <p>Match the product and supplier SKU explicitly. Location prices, pars, count settings and stock remain independent. No stock, opening value or verified conversion is copied.</p>
    <button type="button" className={btnGhost} disabled={busy} onClick={load}>Refresh shared products</button>
    <form onSubmit={submit} className="space-y-3 mt-3">
      <select aria-label="Shared purchased product" className={inpCls} value={form.item} disabled={busy || uncertain || !data} onChange={e => { change("item",e.target.value); change("suppliers",[]); }}>
        <option value="">Choose by product identity and supplier SKU</option>{data?.products.map(p => <option key={p.item_code} value={p.item_code}>{p.name} · {p.item_code}{p.linked ? " · already linked here" : ""}</option>)}
      </select>
      {chosen && <div><p>Catalog unit reference: {chosen.base_unit}. Review physical units at this location before counting. {chosen.linked && "This product is already registered here; use Item Setup to edit location settings."}</p>
        {chosen.supplier_products.map(s => <label className="block" key={s.id}><input aria-label={`Link supplier ${s.id}`} type="checkbox" checked={form.suppliers.includes(s.id)} disabled={busy || uncertain || chosen.linked} onChange={e => change("suppliers",e.target.checked ? [...form.suppliers,s.id] : form.suppliers.filter(id => id !== s.id))} /> {s.vendor_name} · {s.vendor_sku} · {s.vendor_description || "Description unavailable"} · {s.purchase_unit}</label>)}
      </div>}
      {[['control','Location control number','Linked product control number'],['area','Storage area','Linked product storage area'],['countUnit','Physical count unit','Linked product count unit'],['factor','Base units per count unit','Linked product physical factor']].map(([key,label,aria]) => <label className="block" key={key}>{label}<input aria-label={aria} className={inpCls} value={form[key]} disabled={busy || uncertain} onChange={e => change(key,e.target.value)} /></label>)}
      <label className="block"><input aria-label="Confirm shared product identity" type="checkbox" checked={form.verified} disabled={busy || uncertain} onChange={e => edit(f => ({ ...f,verified:e.target.checked }))} /> I confirmed the product, supplier SKUs and physical count unit.</label>
      <button className={btnAcc} disabled={blocked}>Link product to this location</button>
    </form>
    {error && <p role="alert">{error}</p>}
    {uncertain && <p>The save outcome is uncertain. Refresh shared products and check Item Setup before attempting another link. Your entry is retained.</p>}
  </section>;
}
