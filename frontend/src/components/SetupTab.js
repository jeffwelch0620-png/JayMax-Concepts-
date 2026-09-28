import React, { useState, useEffect } from "react";
import { Plus, Trash2, Star, X } from "lucide-react";
import { DEFAULT_STORAGE_AREAS, VENDORS, PURCHASE_UNITS, ITEM_TYPES, UOM_OPTIONS, nextControlNumber, itemDerived, isCountActive, isOrderEnabled, uid, fmtMoney, num } from "../lib/calc";
import * as api from "../lib/api";
import { PageTitle, EmptyState, Field, SectionLabel, Pill, cardCls, inpCls, btnAcc, btnGhost, btnDanger } from "./common";

function emptyForm(areas) {
  return {
    name: "", storageArea: (areas[0] || DEFAULT_STORAGE_AREAS[0]).name, countActive: true, orderEnabled: true, salesTracked: false, itemType: "portion",
    purchaseUnit: "case", packCount: "", unitQty: "", unitUOM: "lb",
    portionSize: "", portionUOM: "oz", par: "", currentStock: "",
    vendorSkus: [{ id: uid("vs"), vendor: VENDORS[0], vendorSku: "", packDescription: "", purchaseUnit: "case", packCount: "", unitQty: "", unitUOM: "lb", price: "", priceUpdatedAt: "", priceSource: "manual", available: true, preferred: true }],
  };
}

export function SetupTab({ items, persistItems, areas, persistAreas, showToast, rid }) {
  const [form, setForm] = useState(() => emptyForm(areas));
  const [editingCN, setEditingCN] = useState(null);
  const [newArea, setNewArea] = useState({ name: "", prefix: "" });
  const [reviewOnly, setReviewOnly] = useState(false);
  const [vendorEmails, setVendorEmails] = useState({});
  const reviewCount = items.filter((it) => it.needsReview).length;

  useEffect(() => {
    if (!rid) return;
    api.listVendorContacts(rid).then((list) => {
      const m = {}; (list || []).forEach((c) => (m[c.vendor] = c.orderEmail || "")); setVendorEmails(m);
    }).catch(() => {});
  }, [rid]);

  async function saveVendorEmail(vendor) {
    try { await api.putVendorContact(rid, vendor, (vendorEmails[vendor] || "").trim()); showToast(`${vendor} order email saved`); }
    catch (e) { showToast(e?.response?.data?.detail || "Couldn't save that email"); }
  }

  function update(field, val) { setForm((f) => ({ ...f, [field]: val })); }

  function startEdit(it) {
    setEditingCN(it.controlNumber);
    setForm({
      name: it.name, storageArea: it.storageArea, countActive: isCountActive(it), orderEnabled: isOrderEnabled(it), salesTracked: it.salesTracked, itemType: it.itemType,
      purchaseUnit: it.purchaseUnit, packCount: it.packCount, unitQty: it.unitQty, unitUOM: it.unitUOM,
      portionSize: it.portionSize, portionUOM: it.portionUOM, par: it.par, currentStock: it.currentStock,
      vendorSkus: (it.vendorSkus || []).map((v) => ({ ...v })),
    });
  }
  function cancelEdit() { setEditingCN(null); setForm(emptyForm(areas)); }

  function addVendorRow() {
    setForm((f) => ({ ...f, vendorSkus: [...f.vendorSkus, { id: uid("vs"), vendor: VENDORS[0], vendorSku: "", packDescription: "", purchaseUnit: f.purchaseUnit || "case", packCount: f.packCount || "", unitQty: f.unitQty || "", unitUOM: f.unitUOM || "lb", price: "", priceUpdatedAt: "", priceSource: "manual", available: true, preferred: f.vendorSkus.length === 0 }] }));
  }
  function updateVendorRow(id, field, val) {
    setForm((f) => ({ ...f, vendorSkus: f.vendorSkus.map((v) => v.id === id ? { ...v, [field]: val } : v) }));
  }
  function setPreferred(id) {
    setForm((f) => ({ ...f, vendorSkus: f.vendorSkus.map((v) => ({ ...v, preferred: v.id === id })) }));
  }
  function removeVendorRow(id) {
    setForm((f) => {
      const remaining = f.vendorSkus.filter((v) => v.id !== id);
      if (remaining.length && !remaining.some((v) => v.preferred)) remaining[0].preferred = true;
      return { ...f, vendorSkus: remaining };
    });
  }

  const previewCN = editingCN || (form.storageArea ? nextControlNumber(areas.find((a) => a.name === form.storageArea)?.prefix || "XX", items) : "");
  const preview = itemDerived({ purchaseUnit: form.purchaseUnit, packCount: form.packCount, unitQty: form.unitQty, unitUOM: form.unitUOM, portionSize: form.portionSize, portionUOM: form.portionUOM, vendorSkus: form.vendorSkus });

  async function submit(e) {
    e.preventDefault();
    if (!form.name.trim() || form.vendorSkus.length === 0) return;
    const cleanSkus = form.vendorSkus.map((v) => ({
      ...v, price: Number(v.price) || 0, vendorSku: String(v.vendorSku || "").trim(), packDescription: String(v.packDescription || "").trim(),
      purchaseUnit: v.purchaseUnit || form.purchaseUnit || "case", packCount: Number(v.packCount) || 0,
      unitQty: Number(v.unitQty) || 0, unitUOM: v.unitUOM || form.unitUOM || "each",
    }));
    const record = {
      controlNumber: previewCN, name: form.name.trim(), storageArea: form.storageArea,
      active: form.countActive, countActive: form.countActive, orderEnabled: form.orderEnabled,
      salesTracked: form.salesTracked, itemType: form.itemType,
      purchaseUnit: form.purchaseUnit, packCount: Number(form.packCount) || 0, unitQty: Number(form.unitQty) || 0, unitUOM: form.unitUOM,
      portionSize: Number(form.portionSize) || 0, portionUOM: form.portionUOM,
      par: Number(form.par) || 0, currentStock: Number(form.currentStock) || 0,
      lastCounted: items.find((i) => i.controlNumber === editingCN)?.lastCounted || "",
      needsReview: false,
      vendorSkus: cleanSkus,
    };
    const exists = items.some((it) => it.controlNumber === record.controlNumber);
    const next = exists ? items.map((it) => it.controlNumber === record.controlNumber ? record : it) : [...items, record];
    await persistItems(next);
    showToast(exists ? "Item updated" : `Item ${record.controlNumber} added`);
    cancelEdit();
  }

  async function deleteItem(cn) {
    if (!window.confirm(`Delete ${cn}? This cannot be undone.`)) return;
    await persistItems(items.filter((it) => it.controlNumber !== cn));
    if (editingCN === cn) cancelEdit();
    showToast("Item deleted");
  }

  async function addArea() {
    const name = newArea.name.trim(), prefix = newArea.prefix.trim().toUpperCase();
    if (!name || !prefix) return;
    if (areas.some((a) => a.name === name)) { showToast("That storage area already exists"); return; }
    await persistAreas([...areas, { name, prefix }]);
    setNewArea({ name: "", prefix: "" });
    showToast("Storage area added");
  }

  const previewBg = preview.mismatch ? "bg-red-500/10 text-red-400" : preview.needsPortion ? "bg-amber-500/10 text-amber-400" : "bg-[#0F1626] text-slate-300";

  return (
    <div className="fade-slide-in" data-testid="setup-tab">
      <PageTitle>Item Setup</PageTitle>
      <form onSubmit={submit} className={`${cardCls} p-5 mb-6`}>
        <div className="flex justify-between items-center mb-4 flex-wrap gap-2">
          <SectionLabel className="mb-0">{editingCN ? `Editing ${editingCN}` : "New Item"}</SectionLabel>
          <Pill testId="control-number-preview" color="var(--acc)" bg="rgba(249,115,22,0.12)">Control #: {previewCN || "—"}</Pill>
        </div>
        <div className="grid gap-3 mb-4" style={{ gridTemplateColumns: "repeat(auto-fit, minmax(160px, 1fr))" }}>
          <Field label="Item Name"><input data-testid="item-name-input" className={inpCls} value={form.name} onChange={(e) => update("name", e.target.value)} placeholder="e.g. Ground Beef 80/20" /></Field>
          <Field label="Storage Area">
            <select data-testid="storage-area-select" className={inpCls} value={form.storageArea} onChange={(e) => update("storageArea", e.target.value)}>
              {areas.map((a) => <option key={a.name} value={a.name}>{a.prefix ? `${a.name} (${a.prefix})` : a.name}</option>)}
            </select>
          </Field>
          <Field label="Item Type">
            <select className={inpCls} value={form.itemType} onChange={(e) => update("itemType", e.target.value)}>
              {ITEM_TYPES.map((t) => <option key={t.id} value={t.id}>{t.label}</option>)}
            </select>
          </Field>
        </div>
        <div className="flex gap-5 mb-4 flex-wrap">
          <label className="text-[13px] flex items-center gap-1.5 font-semibold text-slate-300"><input type="checkbox" data-testid="count-active-toggle" checked={form.countActive} onChange={(e) => update("countActive", e.target.checked)} /> Include in Biweekly Inventory Count</label>
          <label className="text-[13px] flex items-center gap-1.5 font-semibold text-slate-300"><input type="checkbox" data-testid="order-enabled-toggle" checked={form.orderEnabled} onChange={(e) => update("orderEnabled", e.target.checked)} /> Include in Order Generator</label>
          <label className="text-[13px] flex items-center gap-1.5 font-semibold text-slate-300"><input type="checkbox" data-testid="sales-tracked-toggle" checked={form.salesTracked} onChange={(e) => update("salesTracked", e.target.checked)} /> Track against Toast sales</label>
        </div>

        <SectionLabel>Purchasing</SectionLabel>
        <div className="grid gap-3 mb-4" style={{ gridTemplateColumns: "repeat(auto-fit, minmax(140px, 1fr))" }}>
          <Field label="Purchase Unit"><select className={inpCls} value={form.purchaseUnit} onChange={(e) => update("purchaseUnit", e.target.value)}>{PURCHASE_UNITS.map((u) => <option key={u} value={u}>{u}</option>)}</select></Field>
          <Field label="Par Level (purchase units)"><input type="number" step="0.5" className={inpCls} value={form.par} onChange={(e) => update("par", e.target.value)} /></Field>
          <Field label="Current Stock (purchase units)"><input type="number" step="0.5" className={inpCls} value={form.currentStock} onChange={(e) => update("currentStock", e.target.value)} /></Field>
        </div>

        <SectionLabel>Portion Breakdown (per Purchase Unit)</SectionLabel>
        <div className="grid gap-3" style={{ gridTemplateColumns: "repeat(auto-fit, minmax(140px, 1fr))" }}>
          <Field label="Pack Count"><input type="number" step="1" className={inpCls} value={form.packCount} onChange={(e) => update("packCount", e.target.value)} placeholder="e.g. 4" /></Field>
          <Field label="Size per Pack"><input type="number" step="0.01" className={inpCls} value={form.unitQty} onChange={(e) => update("unitQty", e.target.value)} placeholder="e.g. 5" /></Field>
          <Field label="Size Unit"><select className={inpCls} value={form.unitUOM} onChange={(e) => update("unitUOM", e.target.value)}>{UOM_OPTIONS.map((u) => <option key={u} value={u}>{u}</option>)}</select></Field>
          <Field label="Portion Size"><input type="number" step="0.01" className={inpCls} value={form.portionSize} onChange={(e) => update("portionSize", e.target.value)} placeholder="e.g. 6" /></Field>
          <Field label="Portion Unit"><select className={inpCls} value={form.portionUOM} onChange={(e) => update("portionUOM", e.target.value)}>{UOM_OPTIONS.map((u) => <option key={u} value={u}>{u}</option>)}</select></Field>
        </div>
        {form.packCount ? (
          <div className={`mt-3 px-3.5 py-2.5 rounded-lg text-[13.5px] flex gap-5 flex-wrap ${previewBg}`} data-testid="portion-preview">
            {preview.needsPortion ? (
              <span className="font-semibold">⚠ Portion Size isn't set — cost per portion will show $0.00 until it is</span>
            ) : (
              <>
                <span><strong className="num">{num(preview.portionsPerUnit, 1)}</strong> portions per {form.purchaseUnit}</span>
                <span><strong className="num">{fmtMoney(preview.costPerPortion)}</strong> cost per portion (preferred vendor)</span>
                {preview.mismatch && <span className="font-semibold">⚠ size unit and portion unit aren't the same measure type</span>}
              </>
            )}
          </div>
        ) : null}

        <SectionLabel className="mt-4">Vendor SKUs</SectionLabel>
        <div className="flex flex-col gap-2 mb-2.5">
          {form.vendorSkus.map((v, idx) => (
            <div key={v.id} className="flex gap-2 flex-wrap items-end p-2.5 bg-[#0F1626] rounded-lg border border-[#28354A]" data-testid={`vendor-sku-row-${idx}`}>
              <button type="button" title="Set preferred" data-testid={`vendor-preferred-${idx}`} onClick={() => setPreferred(v.id)} className="pb-2 text-amber-400 hover:scale-110 transition">
                <Star size={18} fill={v.preferred ? "#EAB308" : "none"} />
              </button>
              <Field label="Vendor"><select className={inpCls} value={v.vendor} onChange={(e) => updateVendorRow(v.id, "vendor", e.target.value)}>{VENDORS.map((ve) => <option key={ve} value={ve}>{ve}</option>)}</select></Field>
              <Field label="Vendor SKU"><input className={`${inpCls} w-28`} value={v.vendorSku} onChange={(e) => updateVendorRow(v.id, "vendorSku", e.target.value)} placeholder="—" /></Field>
              <Field label="Pack Description"><input className={`${inpCls} w-32`} value={v.packDescription} onChange={(e) => updateVendorRow(v.id, "packDescription", e.target.value)} placeholder="e.g. 4/5lb" /></Field>
              <Field label="Purchase Unit"><select className={inpCls} value={v.purchaseUnit || form.purchaseUnit} onChange={(e) => updateVendorRow(v.id, "purchaseUnit", e.target.value)}>{PURCHASE_UNITS.map((u) => <option key={u} value={u}>{u}</option>)}</select></Field>
              <Field label="Pack Count"><input type="number" step="1" className={`${inpCls} w-20`} value={v.packCount ?? ""} onChange={(e) => updateVendorRow(v.id, "packCount", e.target.value)} /></Field>
              <Field label="Qty / Pack"><input type="number" step="0.01" className={`${inpCls} w-20`} value={v.unitQty ?? ""} onChange={(e) => updateVendorRow(v.id, "unitQty", e.target.value)} /></Field>
              <Field label="Pack UOM"><select className={inpCls} value={v.unitUOM || form.unitUOM} onChange={(e) => updateVendorRow(v.id, "unitUOM", e.target.value)}>{UOM_OPTIONS.map((u) => <option key={u} value={u}>{u}</option>)}</select></Field>
              <Field label="Price ($)"><input type="number" step="0.01" className={`${inpCls} w-24`} value={v.price} onChange={(e) => updateVendorRow(v.id, "price", e.target.value)} /></Field>
              <Field label="Price Date"><input type="date" className={inpCls} value={v.priceUpdatedAt || ""} onChange={(e) => updateVendorRow(v.id, "priceUpdatedAt", e.target.value)} /></Field>
              <label className="text-xs flex items-center gap-1 pb-2 text-slate-400"><input type="checkbox" checked={v.available !== false} onChange={(e) => updateVendorRow(v.id, "available", e.target.checked)} /> Available</label>
              <button type="button" aria-label={`Remove vendor SKU${v.vendor ? ` for ${v.vendor}` : ""}`} className={`${btnDanger} mb-0.5`} onClick={() => removeVendorRow(v.id)} disabled={form.vendorSkus.length === 1}><Trash2 size={14} /></button>
            </div>
          ))}
        </div>
        <button type="button" className={`${btnGhost} mb-4`} data-testid="add-vendor-sku-button" onClick={addVendorRow}><Plus size={14} /> Add Vendor SKU</button>

        <div className="flex gap-2.5">
          <button type="submit" className={btnAcc} data-testid="item-submit-button"><Plus size={15} /> {editingCN ? "Save Changes" : "Add Item"}</button>
          {editingCN && <button type="button" className={btnGhost} onClick={cancelEdit}><X size={15} /> Cancel</button>}
        </div>
      </form>

      <div className={`${cardCls} p-4 mb-6`}>
        <SectionLabel>Storage Areas</SectionLabel>
        <div className="flex gap-2 flex-wrap items-end">
          {areas.map((a) => <Pill key={a.name} color="#94A3B8" bg="#1E293B">{a.prefix ? `${a.prefix} — ${a.name}` : a.name}</Pill>)}
          <input className={`${inpCls} w-40`} placeholder="New area name" value={newArea.name} onChange={(e) => setNewArea((s) => ({ ...s, name: e.target.value }))} data-testid="new-area-name" />
          <input className={`${inpCls} w-20`} placeholder="Prefix" maxLength={3} value={newArea.prefix} onChange={(e) => setNewArea((s) => ({ ...s, prefix: e.target.value }))} data-testid="new-area-prefix" />
          <button className={btnGhost} onClick={addArea} data-testid="add-area-button"><Plus size={14} /> Add Area</button>
        </div>
      </div>

      <div className={`${cardCls} p-4 mb-6`} data-testid="vendor-emails-card">
        <SectionLabel>Supplier Order Emails</SectionLabel>
        <div className="text-[11px] text-slate-500 mb-3">Saved addresses are used as the default recipient when emailing a Purchase Order to a supplier (editable at send time).</div>
        <div className="grid gap-2.5" style={{ gridTemplateColumns: "repeat(auto-fit,minmax(280px,1fr))" }}>
          {VENDORS.map((v) => (
            <div key={v} className="flex items-end gap-2" data-testid={`vendor-email-row-${v}`}>
              <Field label={v} className="flex-1">
                <input type="email" className={inpCls} placeholder="orders@vendor.com" value={vendorEmails[v] || ""} onChange={(e) => setVendorEmails((m) => ({ ...m, [v]: e.target.value }))} data-testid={`vendor-email-input-${v}`} />
              </Field>
              <button className={btnGhost} onClick={() => saveVendorEmail(v)} data-testid={`vendor-email-save-${v}`}>Save</button>
            </div>
          ))}
        </div>
      </div>

      {items.length === 0 ? <EmptyState text="No items yet — add your first one above." /> : (
        <>
        {reviewCount > 0 && (
          <div className="flex items-center gap-3 mb-3" data-testid="review-filter-bar">
            <Pill color="#F59E0B" bg="rgba(245,158,11,0.12)">{reviewCount} imported items need review</Pill>
            <label className="text-[13px] flex items-center gap-1.5 text-slate-400">
              <input type="checkbox" data-testid="review-only-toggle" checked={reviewOnly} onChange={(e) => setReviewOnly(e.target.checked)} /> Needs review only
            </label>
            <span className="text-[11px] text-slate-500">Imported from the YTD analysis — open each item, confirm vendors/pack/par, and save to clear the flag. Portion sizes are empty until you set them.</span>
          </div>
        )}
        <div className={`${cardCls} overflow-hidden`}>
          <div className="overflow-x-auto">
            <table className="ops-table">
              <thead><tr><th>Control #</th><th>Item</th><th>Vendors</th><th>Cost/Portion</th><th>Count</th><th></th></tr></thead>
              <tbody>
                {items.filter((it) => !reviewOnly || it.needsReview).map((it) => {
                  const d = itemDerived(it);
                  return (
                    <tr key={it.controlNumber} data-testid={`setup-item-row-${it.controlNumber}`}>
                      <td className="font-bold" style={{ color: "var(--acc)" }}>{it.controlNumber}</td>
                      <td className="font-semibold text-slate-200">
                        {it.name} {it.needsReview && <Pill testId={`review-pill-${it.controlNumber}`} color="#F59E0B" bg="rgba(245,158,11,0.12)">REVIEW</Pill>}
                      </td>
                      <td>{(it.vendorSkus || []).map((v) => v.vendor).join(", ")}</td>
                      <td className="num">
                        {fmtMoney(d.costPerPortion)}
                        {d.needsPortion && <Pill testId={`needs-portion-${it.controlNumber}`} color="#F59E0B" bg="rgba(245,158,11,0.12)">NO PORTION DATA</Pill>}
                      </td>
                      <td>{isCountActive(it) ? <Pill color="#10B981" bg="rgba(16,185,129,0.12)">Y</Pill> : <Pill color="#64748B" bg="#1E293B">N</Pill>}</td>
                      <td>
                        <div className="flex gap-1.5">
                          <button className={btnGhost} data-testid={`edit-item-${it.controlNumber}`} onClick={() => startEdit(it)}>Edit</button>
                          <button aria-label={`Delete ${it.name}`} className={btnDanger} data-testid={`delete-item-${it.controlNumber}`} onClick={() => deleteItem(it.controlNumber)}><Trash2 size={14} /></button>
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
        </>
      )}
    </div>
  );
}
