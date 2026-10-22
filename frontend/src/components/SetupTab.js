import React, { useState, useEffect, useRef } from "react";
import { confirmSave, useRetainedDraft } from "../lib/saveIntegrity";
import { equalEditorValue, snapshotEditorValue, mergeEditorFields } from "../lib/editorDraft";
import { supplierConversionMismatch, supplierReviewSaved } from "../lib/supplierConversion";
import { Plus, Trash2, Star, X } from "lucide-react";
import { DEFAULT_STORAGE_AREAS, VENDORS, PURCHASE_UNITS, ITEM_TYPES, UOM_OPTIONS, UOM_FAMILY, nextControlNumber, itemDerived, itemPlanningCost, isCountActive, isOrderEnabled, uid, fmtPlanningCost, num } from "../lib/calc";
import * as api from "../lib/api";
import { NativeInventoryPosition } from "./NativeInventoryPosition";
import { InventoryParSetup } from "./InventoryParSetup";
import { PreparedItemSetup } from "./PreparedItemSetup";
import { PreparedBatchLedger } from "./PreparedBatchLedger";
import { PrepObservations } from "./PrepObservations";
import { PrepPeriodComparison } from "./PrepPeriodComparison";
import { PrepOpeningStock } from "./PrepOpeningStock";
import { PrepPeriodJournal } from "./PrepPeriodJournal";
import { SharedCatalogLink } from "./SharedCatalogLink";
import { SupplierPriceHistory } from "./SupplierPriceHistory";
import { SupplierContacts } from "./SupplierContacts";
import { PrepPlanning } from "./PrepPlanning";
import { PageTitle, EmptyState, Field, SectionLabel, Pill, cardCls, inpCls, btnAcc, btnGhost, btnDanger } from "./common";

function emptyForm(areas) {
  return {
    draftToken: uid("item-draft"), receiptReviewRequired: false, draftRevision: null, draftBase: null, name: "", storageArea: (areas[0] || DEFAULT_STORAGE_AREAS[0]).name, active: true, countActive: true, orderEnabled: true, salesTracked: false, itemType: "portion",
    purchaseUnit: "case", packCount: "", unitQty: "", unitUOM: "lb",
    portionSize: "", portionUOM: "oz", par: "", currentStock: "",
    vendorSkus: [{ id: uid("vs"), vendor: VENDORS[0], vendorSku: "", packDescription: "", purchaseUnit: "case", packCount: "", unitQty: "", unitUOM: "lb", price: "", priceUpdatedAt: "", priceSource: "manual", available: true, preferred: true }],
  };
}

function itemForm(it, revision) {
  return {
    draftToken: uid("item-draft"), receiptReviewRequired: false, draftRevision: revision, draftBase: snapshotEditorValue(it),
    name: it.name, storageArea: it.storageArea, active: it.active !== false,
    countActive: isCountActive(it), orderEnabled: isOrderEnabled(it), salesTracked: it.salesTracked, itemType: it.itemType,
    purchaseUnit: it.purchaseUnit, packCount: it.packCount ?? "", unitQty: it.unitQty ?? "", unitUOM: it.unitUOM,
    portionSize: it.portionSize ?? "", portionUOM: it.portionUOM, par: it.par, currentStock: it.currentStock,
    vendorSkus: snapshotEditorValue(it.vendorSkus || []),
  };
}
function itemFields(form) {
  const optionalDecimal = value => value === "" || value == null ? null : String(value);
  return {
    name: form.name.trim(), storageArea: form.storageArea, active: form.active,
    countActive: form.countActive, orderEnabled: form.orderEnabled, salesTracked: form.salesTracked, itemType: form.itemType,
    purchaseUnit: form.purchaseUnit, packCount: optionalDecimal(form.packCount), unitQty: optionalDecimal(form.unitQty), unitUOM: form.unitUOM,
    portionSize: optionalDecimal(form.portionSize), portionUOM: form.portionUOM,
    par: optionalDecimal(form.par) ?? "0", currentStock: Number(form.currentStock) || 0,
    vendorSkus: form.vendorSkus.map(v => ({ ...v, price: v.price === "" || v.price == null ? null : v.price,
      vendorSku: String(v.vendorSku || "").trim(), packDescription: String(v.packDescription ?? ""),
      purchaseUnit: v.purchaseUnit || form.purchaseUnit || "case", packCount: optionalDecimal(v.packCount),
      unitQty: optionalDecimal(v.unitQty), unitUOM: v.unitUOM || null })),
  };
}
const ITEM_GROUPS = [
  { label: "pack, portion and supplier details", fields: ["itemType", "purchaseUnit", "packCount", "unitQty", "unitUOM", "portionSize", "portionUOM", "vendorSkus"] },
  { label: "catalog participation", fields: ["active", "countActive", "orderEnabled", "salesTracked"] },
];

export function SetupTab({ items, revision = 0, persistItems, areas, persistAreas, showToast, showError = () => {}, drafts, rid, actorId, onCatalogLinked, onVerifySupplier }) {
  const [form, editForm, clearForm, , reconcileForm] = useRetainedDraft(`item:${rid}`, emptyForm(areas), drafts);
  const [editingKey, setEditingCN, clearEditing] = useRetainedDraft(`item-edit:${rid}`, null, drafts);
  const editingCN = editingKey || form.draftBase?.controlNumber || null;
  const [newArea, setNewArea, clearArea] = useRetainedDraft(`area:${rid}`, { name: "", prefix: "" }, drafts);
  const [error, setError] = useState("");
  const [reviewing, setReviewing] = useState(false);
  const currentForm = useRef(form); currentForm.current = form;
  const mounted = useRef(false);
  useEffect(() => { mounted.current = true; return () => { mounted.current = false; }; }, []);
  const fail = message => { setError(message); showError(message); };
  const [reviewOnly, setReviewOnly] = useState(false);
  const [vendorEmails, setVendorEmails, loadVendorEmails, emailDirty] = useRetainedDraft(`vendor-emails:${rid}`, {}, drafts);
  const reviewCount = items.filter((it) => it.needsReview).length;
  const editedItem = items.find(it => it.controlNumber === editingCN);
  const sharedProduct = api.catalogMappingEnabled && (items.find(it => it.controlNumber === editingCN)?.sharedStoreCount || 0) > 1;

  useEffect(() => {
    if (!rid || api.supplierContactsEnabled) return;
    let active = true;
    api.listVendorContacts(rid).then((list) => {
      if (!active) return;
      const m = {}; (list || []).forEach((c) => (m[c.vendor] = c.orderEmail || "")); if (!emailDirty) loadVendorEmails(vendorEmails, m);
    }).catch(() => {});
    return () => { active = false; };
  }, [rid]); // eslint-disable-line react-hooks/exhaustive-deps

  async function saveVendorEmail(vendor) {
    try {
      const email = (vendorEmails[vendor] || "").trim();
      const result = await api.putVendorContact(rid, vendor, email);
      if (result?.ok !== true || result.vendor !== vendor || result.orderEmail !== email) throw new Error("Supplier email save was not confirmed. Your entry is retained.");
      showToast(`${vendor} order email saved`);
    }
    catch (e) { fail(e?.response?.data?.detail || "Couldn't save that email"); }
  }

  // Keep the opening snapshot/version with the retained form. New drafts may
  // append to the latest catalog; existing drafts must first match their base.
  function setForm(change) {
    editForm(current => ({ ...change(current), draftRevision: current.draftRevision ?? (editingCN ? null : revision) }));
  }
  function update(field, val) { setForm((f) => ({ ...f, [field]: val })); }

  function startEdit(it) {
    setEditingCN(it.controlNumber);
    editForm(itemForm(it, revision)); setError("");
  }
  function cancelEdit() { clearEditing(editingCN, null); clearForm(form, emptyForm(areas)); setError(""); }

  async function reviewLatest() {
    const submitted = form;
    setReviewing(true);
    try {
      const saved = onCatalogLinked ? await onCatalogLinked() : { items, revision };
      if (!mounted.current || currentForm.current !== submitted) return;
      if (!saved || !Number.isSafeInteger(saved.revision) || !Array.isArray(saved.items)) throw new Error("Latest catalog data was not confirmed. Your draft is retained.");
      const latest = saved.items.find(it => it.controlNumber === editingCN);
      if (!latest || !submitted.draftBase || latest.itemCode !== submitted.draftBase.itemCode) throw new Error("The original item was removed or its identity changed. Your draft is retained.");
      const merged = mergeEditorFields(itemFields(itemForm(submitted.draftBase)), itemFields(submitted), itemFields(itemForm(latest)), ITEM_GROUPS);
      if (merged.conflicts.length) throw new Error(`Conflicting item changes: ${merged.conflicts.join(", ")}. Review these fields or cancel; your draft is retained.`);
      editForm({ ...itemForm(latest, saved.revision), ...merged.data }); setError("");
    } catch (e) { if (mounted.current) fail(e.message || "Couldn't review latest catalog data. Your draft is retained."); }
    finally { if (mounted.current) setReviewing(false); }
  }

  function addVendorRow() {
    setForm((f) => ({ ...f, vendorSkus: [...f.vendorSkus, { id: uid("vs"), vendor: VENDORS[0], vendorSku: "", packDescription: "", purchaseUnit: f.purchaseUnit || "case", packCount: f.packCount || "", unitQty: f.unitQty || "", unitUOM: f.unitUOM || "lb", price: "", priceUpdatedAt: "", priceSource: "manual", available: true, preferred: f.vendorSkus.length === 0 }] }));
  }
  function updateVendorRow(id, field, val) {
    setForm((f) => ({ ...f, vendorSkus: f.vendorSkus.map((v) => v.id === id ? { ...v, [field]: val, ...(field === "vendor" ? { vendorId: undefined, basePerPurchaseUnit: undefined } : {}) } : v) }));
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
  const previewItem = { name: form.name || "This item", purchaseUnit: form.purchaseUnit, packCount: form.packCount, unitQty: form.unitQty, unitUOM: form.unitUOM, portionSize: form.portionSize, portionUOM: form.portionUOM, vendorSkus: form.vendorSkus };
  const preview = itemDerived(previewItem);
  const previewCost = itemPlanningCost(previewItem);
  const previewSourceUnit = preview.preferred?.unitUOM || form.unitUOM;
  const previewUnitsKnown = preview.pack.packCount > 0 && preview.pack.unitQty > 0 &&
    Number(form.portionSize) > 0 && preview.portionsPerUnit > 0 && !preview.mismatch &&
    !!UOM_FAMILY[previewSourceUnit] && UOM_FAMILY[previewSourceUnit] === UOM_FAMILY[form.portionUOM];

  async function submit(e) {
    e.preventDefault();
    if (!form.name.trim() || form.vendorSkus.length === 0) return;
    if (form.receiptReviewRequired) { fail("The item was created; your later typing is retained. Reload latest and keep my changes before saving again."); return; }
    if (editingCN && (!form.draftBase || !editedItem || editedItem.itemCode !== form.draftBase.itemCode || !equalEditorValue(form.draftBase, editedItem))) {
      fail("This item changed while the form was open. Your draft is retained. Reload latest and keep my changes to review independent edits, or cancel.");
      return;
    }
    const record = {
      ...items.find(i => i.controlNumber === editingCN),
      controlNumber: previewCN, ...itemFields(form),
      lastCounted: items.find((i) => i.controlNumber === editingCN)?.lastCounted || "",
      needsReview: false,
    };
    const exists = items.some((it) => it.controlNumber === record.controlNumber);
    const next = exists ? items.map((it) => it.controlNumber === record.controlNumber ? record : it) : [...items, record];
    setError("");
    // Latest list + unchanged edited record (or a new record) can safely use
    // this render's revision. The store/server still reject an unseen race.
    let acknowledgement;
    if (!(await confirmSave(async () => { acknowledgement = await persistItems(next, revision); return acknowledgement; }, fail))) return;
    showToast(exists ? "Item updated" : `Item ${record.controlNumber} added`);
    if (clearForm(form, emptyForm(areas))) clearEditing(editingKey, null);
    else if (!editingCN) {
      const canonical = acknowledgement.items?.find(row => row.controlNumber === record.controlNumber);
      const base = snapshotEditorValue({ ...record, itemCode: canonical?.itemCode ?? (api.isPostgres ? `${rid}_${record.controlNumber}` : record.itemCode) });
      reconcileForm(current => current.draftToken === form.draftToken,
        current => ({ ...current, draftBase: base, draftRevision: revision, receiptReviewRequired: true }));
    }
  }

  async function deleteItem(cn) {
    if (!window.confirm(`Retire ${cn} from ordering and sales? Its history and physical counts will remain available.`)) return;
    if (!(await confirmSave(() => persistItems(items.map(it => it.controlNumber === cn ? { ...it, active: false, orderEnabled: false, salesTracked: false } : it)), fail))) return;
    if (editingCN === cn) cancelEdit();
    showToast("Item retired; history and physical counts retained");
  }

  async function addArea() {
    const name = newArea.name.trim(), prefix = newArea.prefix.trim().toUpperCase();
    if (!name || !prefix) return;
    if (areas.some((a) => a.name === name)) { showToast("That storage area already exists"); return; }
    if (!(await confirmSave(() => persistAreas([...areas, { name, prefix }]), fail))) return;
    clearArea(newArea, { name: "", prefix: "" });
    showToast("Storage area added");
  }

  const previewBg = preview.mismatch ? "bg-red-500/10 text-red-400" : previewCost.cost == null ? "bg-amber-500/10 text-amber-400" : "bg-[#0F1626] text-slate-300";

  return (
    <div className="fade-slide-in" data-testid="setup-tab">
      <PageTitle>Item Setup</PageTitle>
      {api.catalogMappingEnabled && <SharedCatalogLink key={`catalog-${rid}`} restaurantId={rid} drafts={drafts} onLinked={onCatalogLinked} showToast={showToast} />}
      {error && <p role="alert">{error}</p>}
      {api.actualInventoryEnabled && <NativeInventoryPosition key={`inventory-position-${rid}`} restaurantId={rid} />}
      {api.actualInventoryEnabled && <InventoryParSetup rid={rid} actorId={actorId} drafts={drafts} onSaved={onCatalogLinked} showToast={showToast}/>}
      {api.prepSetupEnabled && <PreparedItemSetup key={`prep-${rid}`} restaurantId={rid} />}
      {api.prepPlanningEnabled && <PrepPlanning rid={rid} drafts={drafts} showToast={showToast}/>}
      {api.prepBatchesEnabled && <PreparedBatchLedger key={`prep-batches-${rid}`} restaurantId={rid} />}
      {api.prepObservationsEnabled && <PrepObservations key={`prep-observations-${rid}`} restaurantId={rid} />}
      {api.prepObservationsEnabled && <PrepPeriodComparison key={`prep-periods-${rid}`} restaurantId={rid} />}
      {api.prepObservationsEnabled && <PrepPeriodJournal key={`prep-journal-${rid}`} restaurantId={rid} />}
      {api.prepObservationsEnabled && <PrepOpeningStock key={`prep-openings-${rid}`} restaurantId={rid} />}
      {api.catalogMappingEnabled && !editingCN && <SupplierPriceHistory key={`supplier-prices-${rid}`} restaurantId={rid} items={items} drafts={drafts} onSaved={onCatalogLinked} showToast={showToast} />}
      <form onSubmit={submit} className={`${cardCls} p-5 mb-6`}>
        {sharedProduct && <p>This product is shared across locations. Product and pack changes require shared catalog review; location flags, pars and supplier prices remain editable.</p>}
        <div className="flex justify-between items-center mb-4 flex-wrap gap-2">
          <SectionLabel className="mb-0">{editingCN ? `Editing ${editingCN}` : "New Item"}</SectionLabel>
          <Pill testId="control-number-preview" color="var(--acc)" bg="rgba(249,115,22,0.12)">Control #: {previewCN || "—"}</Pill>
        </div>
        <div className="grid gap-3 mb-4" style={{ gridTemplateColumns: "repeat(auto-fit, minmax(160px, 1fr))" }}>
          <Field label="Item Name"><input data-testid="item-name-input" className={inpCls} disabled={sharedProduct} value={form.name} onChange={(e) => update("name", e.target.value)} placeholder="e.g. Ground Beef 80/20" /></Field>
          <Field label="Storage Area">
            <select data-testid="storage-area-select" className={inpCls} value={form.storageArea} onChange={(e) => update("storageArea", e.target.value)}>
              {areas.map((a) => <option key={a.name} value={a.name}>{a.prefix ? `${a.name} (${a.prefix})` : a.name}</option>)}
            </select>
          </Field>
          <Field label="Item Type">
            <select className={inpCls} disabled={sharedProduct} value={form.itemType} onChange={(e) => update("itemType", e.target.value)}>
              {ITEM_TYPES.map((t) => <option key={t.id} value={t.id}>{t.label}</option>)}
            </select>
          </Field>
        </div>
        <div className="flex gap-5 mb-4 flex-wrap">
          <label className="text-[13px] flex items-center gap-1.5 font-semibold text-slate-300"><input type="checkbox" data-testid="item-active-toggle" checked={form.active} onChange={(e) => update("active", e.target.checked)} /> Active catalog item</label>
          <label className="text-[13px] flex items-center gap-1.5 font-semibold text-slate-300"><input type="checkbox" data-testid="count-active-toggle" checked={form.countActive} onChange={(e) => update("countActive", e.target.checked)} /> Include in Biweekly Inventory Count</label>
          <label className="text-[13px] flex items-center gap-1.5 font-semibold text-slate-300"><input type="checkbox" data-testid="order-enabled-toggle" checked={form.orderEnabled} onChange={(e) => update("orderEnabled", e.target.checked)} /> Include in Order Generator</label>
          <label className="text-[13px] flex items-center gap-1.5 font-semibold text-slate-300"><input type="checkbox" data-testid="sales-tracked-toggle" checked={form.salesTracked} onChange={(e) => update("salesTracked", e.target.checked)} /> Track against Toast sales</label>
        </div>

        <SectionLabel>Purchasing</SectionLabel>
        <div className="grid gap-3 mb-4" style={{ gridTemplateColumns: "repeat(auto-fit, minmax(140px, 1fr))" }}>
          <Field label="Purchase Unit"><select className={inpCls} disabled={sharedProduct} value={form.purchaseUnit} onChange={(e) => update("purchaseUnit", e.target.value)}>{PURCHASE_UNITS.map((u) => <option key={u} value={u}>{u}</option>)}</select></Field>
          {api.actualInventoryEnabled ? <Field label="Previous par (unit unconfirmed)"><input type="text" className={inpCls} value={form.par ?? ""} readOnly/><span>Retained reference only. Review the explicit target in Purchased inventory targets above.</span></Field> : <Field label="Par Level (purchase units)"><input type="text" inputMode="decimal" className={inpCls} value={form.par ?? ""} onChange={(e) => update("par", e.target.value)} /></Field>}
          {api.actualInventoryEnabled ? <p className="text-sm" data-testid="setup-native-count-note">Physical stock and explicit inventory values are recorded in Actual Inventory. Item Setup does not set on-hand quantities.</p> : <Field label="Current Stock (purchase units)"><input type="number" step="0.5" className={inpCls} value={form.currentStock ?? ""} onChange={(e) => update("currentStock", e.target.value)} /></Field>}
        </div>

        <SectionLabel>Portion Breakdown (per Purchase Unit)</SectionLabel>
        <div className="grid gap-3" style={{ gridTemplateColumns: "repeat(auto-fit, minmax(140px, 1fr))" }}>
          <Field label="Pack Count"><input type="text" inputMode="decimal" className={inpCls} disabled={sharedProduct} value={form.packCount ?? ""} onChange={(e) => update("packCount", e.target.value)} placeholder="e.g. 4" /></Field>
          <Field label="Size per Pack"><input type="text" inputMode="decimal" className={inpCls} disabled={sharedProduct} value={form.unitQty ?? ""} onChange={(e) => update("unitQty", e.target.value)} placeholder="e.g. 5" /></Field>
          <Field label="Size Unit"><select className={inpCls} disabled={sharedProduct} value={form.unitUOM} onChange={(e) => update("unitUOM", e.target.value)}>{UOM_OPTIONS.map((u) => <option key={u} value={u}>{u}</option>)}</select></Field>
          <Field label="Portion Size"><input type="text" inputMode="decimal" className={inpCls} disabled={sharedProduct} value={form.portionSize ?? ""} onChange={(e) => update("portionSize", e.target.value)} placeholder="e.g. 6" /></Field>
          <Field label="Portion Unit"><select className={inpCls} disabled={sharedProduct} value={form.portionUOM} onChange={(e) => update("portionUOM", e.target.value)}>{UOM_OPTIONS.map((u) => <option key={u} value={u}>{u}</option>)}</select></Field>
        </div>
        {form.packCount ? (
          <div className={`mt-3 px-3.5 py-2.5 rounded-lg text-[13.5px] flex gap-5 flex-wrap ${previewBg}`} data-testid="portion-preview">
            {preview.rangeUnavailable ? <span>Outside supported calculation range. Portions and cost unavailable.</span> : preview.needsPortion ? (
              <span className="font-semibold">⚠ Portion Size isn't set — review portion details before using cost per portion.</span>
            ) : !previewUnitsKnown ? (
              <span className="font-semibold">Portions and cost unavailable — {preview.mismatch
                ? "⚠ size unit and portion unit aren't the same measure type"
                : "confirm positive pack/portion quantities and compatible supported units."}</span>
            ) : (
              <>
                <span><strong className="num">{num(preview.portionsPerUnit, 1)}</strong> portions per {form.purchaseUnit}</span>
                <span><strong className="num">{fmtPlanningCost(previewCost.cost)}</strong> cost per portion (preferred vendor)</span>
                {preview.priceMissing && <span>Supplier planning price is unknown.</span>}
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
              <Field label="Vendor"><select className={inpCls} disabled={sharedProduct} value={v.vendor} onChange={(e) => updateVendorRow(v.id, "vendor", e.target.value)}>{VENDORS.map((ve) => <option key={ve} value={ve}>{ve}</option>)}</select></Field>
              <Field label="Vendor SKU"><input className={`${inpCls} w-28`} disabled={sharedProduct} value={v.vendorSku} onChange={(e) => updateVendorRow(v.id, "vendorSku", e.target.value)} placeholder="—" /></Field>
              <Field label="Pack Description"><input className={`${inpCls} w-32`} disabled={sharedProduct} value={v.packDescription} onChange={(e) => updateVendorRow(v.id, "packDescription", e.target.value)} placeholder="e.g. 4/5lb" /></Field>
              <Field label="Purchase Unit"><select className={inpCls} disabled={sharedProduct} value={v.purchaseUnit || form.purchaseUnit} onChange={(e) => updateVendorRow(v.id, "purchaseUnit", e.target.value)}>{PURCHASE_UNITS.map((u) => <option key={u} value={u}>{u}</option>)}</select></Field>
              <Field label="Pack Count"><input type="text" inputMode="decimal" className={`${inpCls} w-20`} disabled={sharedProduct} value={v.packCount ?? ""} onChange={(e) => updateVendorRow(v.id, "packCount", e.target.value)} /></Field>
              <Field label="Qty / Pack"><input type="text" inputMode="decimal" className={`${inpCls} w-20`} disabled={sharedProduct} value={v.unitQty ?? ""} onChange={(e) => updateVendorRow(v.id, "unitQty", e.target.value)} /></Field>
              <Field label="Pack UOM"><select className={inpCls} disabled={sharedProduct} value={v.unitUOM || form.unitUOM} onChange={(e) => updateVendorRow(v.id, "unitUOM", e.target.value)}>{UOM_OPTIONS.map((u) => <option key={u} value={u}>{u}</option>)}</select></Field>
              <Field label="Price ($)"><input aria-label={`Supplier price ${v.id}`} type="text" inputMode="decimal" className={`${inpCls} w-24`} value={v.price ?? ""} onChange={(e) => updateVendorRow(v.id, "price", e.target.value)} /></Field>
              <Field label="Price Recorded"><input type="date" className={inpCls} value={(v.priceUpdatedAt || "").slice(0, 10)} readOnly /></Field>
              <label className="text-xs flex items-center gap-1 pb-2 text-slate-400"><input type="checkbox" checked={v.available !== false} onChange={(e) => updateVendorRow(v.id, "available", e.target.checked)} /> Available</label>
              <button type="button" aria-label={`Remove vendor SKU${v.vendor ? ` for ${v.vendor}` : ""}`} className={`${btnDanger} mb-0.5`} onClick={() => removeVendorRow(v.id)} disabled={form.vendorSkus.length === 1}><Trash2 size={14} /></button>
              {api.nativePurchasesEnabled && <div className="w-full text-xs space-y-2">
                {supplierConversionMismatch(v, editedItem?.baseUnit) && <p role="status">Stored conversion differs from pack details: confirm or keep. Stored values are unchanged.</p>}
                <p>{v.basePerPurchaseUnit == null ? "Catalog conversion unknown." : `Catalog conversion: ${v.basePerPurchaseUnit} ${editedItem?.baseUnit || "inventory units"} per purchase unit.`} Physical conversions are confirmed in Invoice Master → Verified inventory units.</p>
                {onVerifySupplier && <button type="button" className={btnGhost} data-testid={`verify-supplier-${idx}`}
                  disabled={!supplierReviewSaved(editedItem, v, form)} onClick={() => onVerifySupplier({ itemCode: editedItem.itemCode, skuId: v.id })}>Review verified conversion</button>}
                {!supplierReviewSaved(editedItem, v, form) && <p>Save the item and supplier pack details before reviewing a purchased inventory conversion.</p>}
              </div>}
            </div>
          ))}
        </div>
        <button type="button" className={`${btnGhost} mb-4`} data-testid="add-vendor-sku-button" disabled={sharedProduct} onClick={addVendorRow}><Plus size={14} /> Add Vendor SKU</button>

        <div className="flex gap-2.5">
          <button type="submit" className={btnAcc} data-testid="item-submit-button"><Plus size={15} /> {editingCN ? "Save Changes" : "Add Item"}</button>
          {editingCN && <button type="button" className={btnGhost} disabled={reviewing} data-testid="review-item-draft" onClick={reviewLatest}>Reload latest and keep my changes</button>}
          {(editingCN || form.draftRevision != null) && <button type="button" className={btnGhost} onClick={cancelEdit}><X size={15} /> Cancel</button>}
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

      {api.supplierContactsEnabled ? <SupplierContacts key={`supplier-contacts-${rid}`} rid={rid} drafts={drafts} onSaved={onCatalogLinked} showToast={showToast}/> : <div className={`${cardCls} p-4 mb-6`} data-testid="vendor-emails-card">
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
      </div>}

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
                  const planningCost = itemPlanningCost(it);
                  return (
                    <tr key={it.controlNumber} data-testid={`setup-item-row-${it.controlNumber}`}>
                      <td className="font-bold" style={{ color: "var(--acc)" }}>{it.controlNumber}</td>
                      <td className="font-semibold text-slate-200">
                        {it.name} {it.needsReview && <Pill testId={`review-pill-${it.controlNumber}`} color="#F59E0B" bg="rgba(245,158,11,0.12)">REVIEW</Pill>}
                      </td>
                      <td>{(it.vendorSkus || []).map((v) => v.vendor).join(", ")}</td>
                      <td className="num" data-testid={`setup-cost-${it.controlNumber}`} title={planningCost.issues.join("; ")}>
                        {fmtPlanningCost(planningCost.cost)}
                        {d.needsPortion && <Pill testId={`needs-portion-${it.controlNumber}`} color="#F59E0B" bg="rgba(245,158,11,0.12)">NO PORTION DATA</Pill>}
                      </td>
                      <td>{isCountActive(it) ? <Pill color="#10B981" bg="rgba(16,185,129,0.12)">Y</Pill> : <Pill color="#64748B" bg="#1E293B">N</Pill>}</td>
                      <td>
                        <div className="flex gap-1.5">
                          <button className={btnGhost} data-testid={`edit-item-${it.controlNumber}`} onClick={() => startEdit(it)}>Edit</button>
                          <button aria-label={`Retire ${it.name}`} className={btnDanger} data-testid={`delete-item-${it.controlNumber}`} onClick={() => deleteItem(it.controlNumber)}><Trash2 size={14} /></button>
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
