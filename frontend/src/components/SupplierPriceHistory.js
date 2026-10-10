import React, { useEffect, useRef, useState } from "react";
import * as api from "../lib/api";
import { useRetainedDraft } from "../lib/saveIntegrity";
import { cardCls, inpCls, btnAcc, btnGhost } from "./common";
const empty = { sku: "", line: "", note: "", verified: false };
export function SupplierPriceHistory({ restaurantId, items, drafts, onSaved, showToast }) {
  const [form, edit] = useRetainedDraft(`supplier-price:${restaurantId}`, empty, drafts);
  const [data, setData] = useState(null), [error, setError] = useState(""), [busy, setBusy] = useState(false), [pending, setPending] = useState(null);
  const alive = useRef(true), reads = useRef(0);
  useEffect(() => { alive.current = true; reads.current = reads.current + 1; return () => { alive.current = false; ++reads.current; }; }, [restaurantId]);
  const suppliers = items.flatMap(i => (i.vendorSkus || []).filter(s => /^[0-9a-f-]{36}$/i.test(s.id)).map(s => ({ ...s, label: `${i.controlNumber} · ${i.name} · ${s.vendor} · ${s.vendorSku}` })));
  const chosen = data?.candidates?.find(c => c.line_id === form.line);
  async function load(offset = 0) {
    if (!form.sku || busy || pending) return;
    const read = ++reads.current; setError(""); setData(null);
    try {
      const result = await api.supplierPriceReview(restaurantId, form.sku, offset);
      if (!alive.current || read !== reads.current) return;
      if (result?.current?.vendor_item_id !== form.sku || !Array.isArray(result.history) || !Array.isArray(result.candidates) || !Number.isSafeInteger(result.revision)) throw new Error("Price history was not confirmed.");
      setData(result); edit(f => ({ ...f, verified: false }));
    } catch (e) { if (alive.current && read === reads.current) setError(e?.response?.data?.detail || e.message || "Could not load prices."); }
  }
  function change(key, value) { if (busy || pending) return; ++reads.current; edit(f => ({ ...f, [key]: value, verified: false })); if (key === "sku") setData(null); }
  async function submit(e) {
    e.preventDefault();
    if (busy || (!pending && (!chosen || chosen.issues.length || !form.verified || !form.note.trim()))) return;
    const attempt = pending || { key: window.crypto.randomUUID(), sku: form.sku, price: chosen.price, date: chosen.goods_received_date, revision: data.revision,
      body: { line_id: chosen.line_id, expected_plan_hash: chosen.plan_hash, verified: true, note: form.note.trim() } };
    setPending(attempt); setBusy(true); setError("");
    try {
      const saved = await api.adoptSupplierPrice(restaurantId, attempt.sku, attempt.body, attempt.key);
      if (!saved?.event?.id || saved.event.vendor_item_id !== attempt.sku || saved.event.price !== attempt.price || saved.event.source !== "invoice" || saved.event.request_key !== attempt.key || saved.event.effective_date !== attempt.date || saved.event.basis_snapshot?.line_id !== attempt.body.line_id || !Number.isSafeInteger(saved.revision) || saved.revision <= attempt.revision) throw new Error("Price adoption was not confirmed.");
      if (!alive.current) return;
      setPending(null); setData(null); edit(f => ({ ...f, line: "", verified: false, note: "" }));
      showToast?.("Planning price saved. Actual inventory values remain unchanged."); onSaved?.();
    } catch (e) {
      if (!alive.current) return;
      if (e?.response?.status >= 400 && e.response.status < 500) setPending(null);
      const detail = e?.response?.data?.detail;
      setError(Array.isArray(detail) ? detail.join("; ") : detail || e.message || "Price save failed. Your review is retained.");
    } finally { if (alive.current) setBusy(false); }
  }
  return <section className={`${cardCls} p-5 mb-6`}>
    <h2 className="font-semibold">Supplier planning price history</h2>
    <p>Manual edits and reviewed receipt prices explain planning costs. Physical counts and received purchases determine Actual Food Cost independently. Invoice prices exclude separately classified taxes and fees.</p>
    <select aria-label="Price history supplier" className={inpCls} value={form.sku} disabled={busy || !!pending} onChange={e => change("sku", e.target.value)}>
      <option value="">Choose a product and supplier SKU</option>{suppliers.map(s => <option key={s.id} value={s.id}>{s.label}</option>)}
    </select>
    <button type="button" className={btnGhost} disabled={!form.sku || busy || !!pending} onClick={() => load()}>Load price history</button>
    {data && <>
      <p>Current planning price: {data.current.source_stale || data.current.price == null ? "Unknown / needs review" : `$${data.current.price} / ${data.current.purchase_unit}`} · Effective date: {data.current.effective_date || "Not certified"}</p>
      <ul>{data.history.map(h => <li key={h.id}>{h.price == null ? "Unknown" : `$${h.price}`} · {h.source} · effective {h.effective_date || "not certified"} · recorded {h.recorded_at} · {h.actor} · {h.note}</li>)}</ul>
      {data.offset > 0 && <button type="button" className={btnGhost} disabled={busy || !!pending} onClick={() => load(Math.max(0, data.offset - 100))}>Newer history</button>}
      {data.has_more && <button type="button" className={btnGhost} disabled={busy || !!pending} onClick={() => load(data.offset + 100)}>Older history</button>}
      <form onSubmit={submit} className="space-y-2 mt-3">
        <select aria-label="Receipt planning price" className={inpCls} value={form.line} disabled={busy || !!pending} onChange={e => change("line", e.target.value)}>
          <option value="">Choose a posted receipt to review</option>{data.candidates.map(c => <option key={c.line_id} value={c.line_id}>{c.document_number} · received {c.goods_received_date} · {c.price == null ? "held" : `$${c.price} / ${data.current.purchase_unit}`}</option>)}
        </select>
        {chosen?.issues.map(i => <p key={i}>{i}</p>)}
        <label className="block">Review note<input aria-label="Price review note" className={inpCls} value={form.note} disabled={busy || !!pending} onChange={e => change("note", e.target.value)} /></label>
        <label className="block"><input aria-label="Confirm receipt planning price" type="checkbox" checked={form.verified} disabled={busy || !!pending} onChange={e => edit(f => ({ ...f, verified: e.target.checked }))} /> I verified the received date, supplier pack conversion and planning price.</label>
        <button className={btnAcc} disabled={busy || (!pending && (!chosen || chosen.issues.length > 0 || !form.verified || !form.note.trim()))}>{pending ? "Retry the same price review" : "Adopt receipt planning price"}</button>
      </form>
    </>}
    {pending && !data && <button type="button" className={btnAcc} disabled={busy} onClick={submit}>Retry the same price review</button>}
    {pending && <p>The save outcome is awaiting confirmation. A retry uses the same request so it cannot create another price event.</p>}
    {error && <p role="alert">{error}</p>}
  </section>;
}
