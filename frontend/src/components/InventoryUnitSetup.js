import React, { useEffect, useRef, useState } from "react";
import * as api from "../lib/api";
import { Field, cardCls, inpCls, btnAcc } from "./common";

export function InventoryUnitSetup({ restaurantId }) {
  const [data, setData] = useState(null), [itemCode, setItem] = useState(""), [kind, setKind] = useState("count"), [skuId, setSku] = useState("");
  const [base, setBase] = useState(""), [factor, setFactor] = useState(""), [note, setNote] = useState(""), [verified, setVerified] = useState(false);
  const [busy, setBusy] = useState(false), [error, setError] = useState(""), [message, setMessage] = useState("");
  const [conflict, setConflict] = useState(false);
  const pending = useRef(null), mounted = useRef(true);
  useEffect(() => {
    mounted.current = true;
    api.nativeUnitSetup(restaurantId).then(d => mounted.current && setData(d)).catch(e => mounted.current && setError(e?.response?.data?.detail || e.message));
    return () => { mounted.current = false; };
  }, [restaurantId]);
  const item = data?.items.find(i => i.code === itemCode);
  const source = kind === "count" ? item?.countSource : item?.supplierProducts.find(s => s.id === skuId);
  const frozen = busy || !!pending.current;
  function change(fn) { fn(); setVerified(false); setMessage(""); }
  async function save() {
    setError(""); setBusy(true);
    try {
      if (!pending.current) {
        if (!source || !base || !factor || !note.trim() || !verified) throw new Error("Choose the item and verify its physical unit conversion.");
        pending.current = { key: crypto.randomUUID(), body: { item_code: itemCode, profile_kind: kind, vendor_item_id: kind === "purchase" ? skuId : null,
          base_unit: base, base_units_per_source_unit: factor, expected_source_hash: source.hash, verified: true, note } };
      }
      const r = await api.saveNativeUnitProfile(restaurantId, pending.current.body, pending.current.key);
      if (!r.profile?.id || r.profile.item_code !== pending.current.body.item_code || r.profile.base_unit !== pending.current.body.base_unit) throw new Error("Saved unit review was not confirmed. Retry the same review.");
      pending.current = null; setVerified(false); setMessage("Unit conversion saved. Counts and invoice lines still require their own confirmation.");
      try { const d = await api.nativeUnitSetup(restaurantId); if (mounted.current) setData(d); } catch (e) { setError(`Review saved; refresh failed: ${e.message}`); }
    } catch (e) { if (mounted.current) {
      const detail = e?.response?.data?.detail;
      setError(typeof detail === "string" ? detail : (Array.isArray(detail) ? detail.map(d => d.msg).join("; ") : e.message || "Unit review failed"));
      setConflict(e?.response?.status === 409);
      if (e?.response?.status === 422) { pending.current = null; setVerified(false); }
    } }
    finally { if (mounted.current) setBusy(false); }
  }
  async function refreshReview() {
    setBusy(true);
    try {
      const d = await api.nativeUnitSetup(restaurantId);
      setData(d); pending.current = null; setConflict(false); setVerified(false); setFactor(""); setError("");
      setBase(d.items.find(i => i.code === itemCode)?.native_base_unit || "");
    } catch (e) { setError(e?.response?.data?.detail || e.message); }
    finally { setBusy(false); }
  }
  return <section className={`${cardCls} p-4 space-y-3`} aria-label="Inventory unit setup"><h3 className="font-semibold">Verified inventory units</h3>
    <p>Keep physical inventory units separate from recipe portions. Enter the number of fixed inventory units in one count container or supplier purchase unit. If storage mixes different case packs, count in the fixed unit or verify the measured conversion for that count.</p>
    {data && <>
      <Field label="Purchased inventory item"><select aria-label="Unit setup item" className={inpCls} value={itemCode} disabled={frozen} onChange={e => change(() => { setItem(e.target.value); setBase(data.items.find(i => i.code === e.target.value)?.native_base_unit || ""); setSku(""); setFactor(""); })}><option value="">Choose item</option>{data.items.map(i => <option key={i.code} value={i.code}>{i.name}</option>)}</select></Field>
      <Field label="Conversion purpose"><select aria-label="Unit profile purpose" className={inpCls} value={kind} disabled={frozen} onChange={e => change(() => { setKind(e.target.value); setFactor(""); })}><option value="count">Physical count container</option><option value="purchase">Supplier purchase unit</option></select></Field>
      {kind === "purchase" && <Field label="Supplier product"><select aria-label="Unit setup supplier product" className={inpCls} value={skuId} disabled={frozen} onChange={e => change(() => { setSku(e.target.value); setFactor(""); })}><option value="">Choose supplier product</option>{item?.supplierProducts.map(s => <option key={s.id} value={s.id}>{s.name} · {s.snapshot.supplierProduct.vendor_sku} · {s.unit}</option>)}</select></Field>}
      {source && <p>Source unit: {source.unit}. Catalog pack: {source.snapshot.supplierProduct?.pack_count ?? source.snapshot.item.pack_count ?? "Unknown"} × {source.snapshot.supplierProduct?.unit_qty ?? source.snapshot.item.unit_qty ?? "Unknown"} {source.snapshot.supplierProduct?.unit_uom || source.snapshot.item.unit_uom || "Unknown"}. Prior catalog conversions are references and are not adopted automatically.</p>}
      <Field label="Fixed inventory unit"><select aria-label="Unit setup base unit" className={inpCls} value={base} disabled={frozen || !!item?.native_base_unit} onChange={e => change(() => setBase(e.target.value))}><option value="">Choose physical unit</option>{data.baseUnits.map(u => <option key={u} value={u}>{u}</option>)}</select></Field>
      <Field label={`Verified ${base || "inventory units"} per ${source?.unit || "source unit"}`}><input aria-label="Verified physical conversion" className={inpCls} value={factor} disabled={frozen} onChange={e => change(() => setFactor(e.target.value))} /></Field>
      <Field label="Measurement or pack evidence"><input aria-label="Unit conversion evidence" className={inpCls} value={note} disabled={frozen} onChange={e => change(() => setNote(e.target.value))} /></Field>
      <label><input aria-label="Confirm physical conversion" type="checkbox" checked={verified} disabled={frozen} onChange={e => setVerified(e.target.checked)} /> I verified this physical conversion.</label>
      <button className={btnAcc} disabled={busy || (!pending.current && !verified)} onClick={save}>{pending.current ? "Retry same unit review" : "Save verified unit conversion"}</button>
      {data.profiles.map(p => <p key={p.id}>{data.items.find(i => i.code === p.item_code)?.name || p.item_code}: 1 {p.source_unit} = {p.base_units_per_source_unit} {p.base_unit} · {p.profile_kind === "count" ? "Counts" : "Purchases"} · {p.stale ? "Setup changed — verify again" : "Verified"} · revision {p.revision}</p>)}
    </>}
    {conflict && <button className={btnAcc} disabled={busy} onClick={refreshReview}>Refresh changed unit setup</button>}
    {item?.issues?.map(issue => <p role="alert" key={issue}>{issue} Update the item setup before verifying this source.</p>)}
    {error && <p role="alert">{error}</p>}{message && <p role="status">{message}</p>}
  </section>;
}
