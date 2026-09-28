import React, { useEffect, useMemo, useState } from "react";
import { Plus, Trash2 } from "lucide-react";
import { ADJUSTMENT_REASONS, adjustmentReason, adjustmentValue, todayISO, fmtDate, fmtMoney, num, uid } from "../lib/calc";
import { PageTitle, EmptyState, Field, SectionLabel, Pill, cardCls, inpCls, btnAcc } from "./common";

export function AdjustmentsTab({ items, adjustments, persist, showToast }) {
  const orderItems = useMemo(() => [...items].sort((a, b) => (a.storageArea || "").localeCompare(b.storageArea || "") || (a.name || "").localeCompare(b.name || "")), [items]);
  const [form, setForm] = useState({ date: todayISO(), controlNumber: orderItems[0]?.controlNumber || "", reason: "waste", qtyBasis: "purchase", qty: "", note: "" });
  const [filterReason, setFilterReason] = useState("All");
  const [search, setSearch] = useState("");

  useEffect(() => {
    if (!form.controlNumber && orderItems.length) setForm((f) => ({ ...f, controlNumber: orderItems[0].controlNumber }));
  }, [orderItems, form.controlNumber]);

  const selectedItem = items.find((it) => it.controlNumber === form.controlNumber);
  const selectedReason = adjustmentReason(form.reason);
  const previewValue = selectedItem ? adjustmentValue({ ...form, qty: Number(form.qty) || 0 }, selectedItem) : 0;

  async function addAdjustment() {
    if (!form.controlNumber) return showToast("Choose an inventory item");
    if (!(Number(form.qty) > 0)) return showToast("Enter a quantity greater than zero");
    const rec = {
      id: uid("adj"), date: form.date || todayISO(), controlNumber: form.controlNumber,
      reason: form.reason, qtyBasis: form.qtyBasis, qty: Number(form.qty), note: form.note.trim(), createdAt: new Date().toISOString(),
    };
    await persist([...adjustments, rec]);
    setForm((f) => ({ ...f, qty: "", note: "" }));
    showToast("Adjustment logged");
  }

  async function deleteAdjustment(id) {
    if (!window.confirm("Delete this adjustment?")) return;
    await persist(adjustments.filter((a) => a.id !== id));
    showToast("Adjustment deleted");
  }

  const filtered = [...adjustments].filter((a) => {
    const item = items.find((it) => it.controlNumber === a.controlNumber);
    const hay = `${a.controlNumber} ${item?.name || ""} ${a.note || ""}`.toLowerCase();
    return (filterReason === "All" || a.reason === filterReason) && (!search.trim() || hay.includes(search.trim().toLowerCase()));
  }).sort((a, b) => (b.date || "").localeCompare(a.date || "") || (b.createdAt || "").localeCompare(a.createdAt || ""));

  const totalWasteValue = adjustments.reduce((sum, a) => {
    const item = items.find((it) => it.controlNumber === a.controlNumber);
    if (!item || adjustmentReason(a.reason).direction !== "remove") return sum;
    return sum + adjustmentValue(a, item);
  }, 0);
  const last30 = new Date(); last30.setDate(last30.getDate() - 30);
  const last30ISO = last30.toISOString().slice(0, 10);
  const last30Value = adjustments.reduce((sum, a) => {
    const item = items.find((it) => it.controlNumber === a.controlNumber);
    if (!item || a.date < last30ISO || adjustmentReason(a.reason).direction !== "remove") return sum;
    return sum + adjustmentValue(a, item);
  }, 0);

  return (
    <div className="fade-slide-in" data-testid="adjustments-tab">
      <PageTitle>Waste / Inventory Adjustments</PageTitle>
      <div className="grid gap-3 mb-5" style={{ gridTemplateColumns: "repeat(auto-fit,minmax(180px,1fr))" }}>
        <div className={`${cardCls} p-4`}><div className="text-[11px] text-slate-500 uppercase font-bold">Adjustment Records</div><div className="text-2xl font-bold num" style={{ color: "var(--acc)" }}>{adjustments.length}</div></div>
        <div className={`${cardCls} p-4`}><div className="text-[11px] text-slate-500 uppercase font-bold">Removal Value — Last 30 Days</div><div className="text-2xl font-bold num text-red-400">{fmtMoney(last30Value)}</div></div>
        <div className={`${cardCls} p-4`}><div className="text-[11px] text-slate-500 uppercase font-bold">Removal Value — All Logged</div><div className="text-2xl font-bold num" style={{ color: "var(--acc)" }}>{fmtMoney(totalWasteValue)}</div></div>
      </div>

      <div className={`${cardCls} p-5 mb-5`}>
        <SectionLabel>Log Waste or Adjustment</SectionLabel>
        <div className="grid gap-3 items-end" style={{ gridTemplateColumns: "150px minmax(220px,2fr) minmax(160px,1fr) 140px 130px" }}>
          <Field label="Date"><input type="date" className={inpCls} data-testid="adj-date" value={form.date} onChange={(e) => setForm({ ...form, date: e.target.value })} /></Field>
          <Field label="Inventory Item"><select className={inpCls} data-testid="adj-item" value={form.controlNumber} onChange={(e) => setForm({ ...form, controlNumber: e.target.value })}>{orderItems.map((it) => <option key={it.controlNumber} value={it.controlNumber}>{it.controlNumber} — {it.name}</option>)}</select></Field>
          <Field label="Reason"><select className={inpCls} data-testid="adj-reason" value={form.reason} onChange={(e) => setForm({ ...form, reason: e.target.value })}>{ADJUSTMENT_REASONS.map((r) => <option key={r.id} value={r.id}>{r.label}</option>)}</select></Field>
          <Field label="Quantity Basis"><select className={inpCls} value={form.qtyBasis} onChange={(e) => setForm({ ...form, qtyBasis: e.target.value })}><option value="purchase">Purchase units</option><option value="portion">Recipe portions</option></select></Field>
          <Field label={`Qty (${form.qtyBasis === "portion" ? `${selectedItem?.portionSize || ""} ${selectedItem?.portionUOM || "portion"}`.trim() + " portions" : selectedItem?.purchaseUnit || "purchase units"})`}>
            <input type="number" min="0" step="0.01" className={inpCls} data-testid="adj-qty" value={form.qty} onChange={(e) => setForm({ ...form, qty: e.target.value })} placeholder="0" />
          </Field>
        </div>
        <div className="mt-3"><Field label="Note (optional)"><input className={`${inpCls} w-full`} data-testid="adj-note" value={form.note} onChange={(e) => setForm({ ...form, note: e.target.value })} placeholder="What happened? e.g. dropped pan, cooler temp issue, staff meal..." /></Field></div>
        <div className="flex items-center justify-between gap-3 mt-3.5 flex-wrap">
          <div className="text-xs text-slate-500">{selectedReason.direction === "remove" ? "Removes" : "Adds"} inventory for variance explanation. Estimated value at current preferred cost: <strong className="num">{fmtMoney(previewValue)}</strong>.</div>
          <button className={btnAcc} onClick={addAdjustment} data-testid="log-adjustment-button"><Plus size={15} /> Log Adjustment</button>
        </div>
      </div>

      <div className="flex gap-2.5 mb-3 flex-wrap">
        <input className={`${inpCls} min-w-[240px]`} data-testid="adj-search" value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Search item or note..." />
        <select className={inpCls} value={filterReason} onChange={(e) => setFilterReason(e.target.value)}><option value="All">All reasons</option>{ADJUSTMENT_REASONS.map((r) => <option key={r.id} value={r.id}>{r.label}</option>)}</select>
      </div>

      <SectionLabel>Adjustment History ({filtered.length})</SectionLabel>
      {filtered.length === 0 ? <EmptyState text="No waste or adjustments logged yet." /> : (
        <div className={`${cardCls} overflow-hidden`}>
          <div className="overflow-x-auto">
            <table className="ops-table">
              <thead><tr><th>Date</th><th>Item</th><th>Reason</th><th>Qty</th><th>Est. Value</th><th>Note</th><th></th></tr></thead>
              <tbody>
                {filtered.map((a) => {
                  const item = items.find((it) => it.controlNumber === a.controlNumber);
                  const reason = adjustmentReason(a.reason);
                  return (
                    <tr key={a.id} data-testid={`adj-row-${a.id}`}>
                      <td>{fmtDate(a.date)}</td>
                      <td className="font-semibold text-slate-200">{a.controlNumber} — {item?.name || "Deleted item"}</td>
                      <td><Pill color={reason.direction === "remove" ? "#EF4444" : "#10B981"} bg={reason.direction === "remove" ? "rgba(239,68,68,0.12)" : "rgba(16,185,129,0.12)"}>{reason.label}</Pill></td>
                      <td className="num">{reason.direction === "add" ? "+" : "−"}{num(a.qty, 2)} {a.qtyBasis === "portion" ? `${item?.portionSize || ""} ${item?.portionUOM || "portion"} portions` : (item?.purchaseUnit || "units")}</td>
                      <td className="num">{item ? fmtMoney(adjustmentValue(a, item)) : "—"}</td>
                      <td>{a.note || "—"}</td>
                      <td><button aria-label={`Delete adjustment for ${a.controlNumber}`} className="text-red-400 hover:text-red-300" data-testid={`adj-delete-${a.id}`} onClick={() => deleteAdjustment(a.id)}><Trash2 size={13} /></button></td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}
