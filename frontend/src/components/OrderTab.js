import React, { useMemo, useState } from "react";
import { Copy, Download, ClipboardCheck } from "lucide-react";
import { isOrderEnabled, vendorPack, vendorUnitsForShortfall, todayISO, fmtDate, fmtMoney, num, downloadCSV } from "../lib/calc";
import { PageTitle, EmptyState, Banner, cardCls, inpCls, btnAcc, btnGhost } from "./common";
import * as api from "../lib/api";
import { NativeOrderPlanner } from "./NativeOrderPlanner";

export function OrderTab(props) {
  return api.actualInventoryEnabled ? <NativeOrderPlanner key={props.rid} {...props} /> : <LegacyOrderTab {...props} />;
}

function LegacyOrderTab({ items, showToast, restaurantName, rid, onCreatedPO }) {
  const orderItems = useMemo(() => items.filter((it) => isOrderEnabled(it) && (Number(it.currentStock) || 0) < (Number(it.par) || 0)), [items]);
  const [selectedSkuByItem, setSelectedSkuByItem] = useState({});

  const rows = useMemo(() => orderItems.map((it) => {
    const shortfall = Math.max(0, (Number(it.par) || 0) - (Number(it.currentStock) || 0));
    const availableSkus = (it.vendorSkus || []).filter((s) => s.available !== false);
    const preferred = availableSkus.find((s) => s.preferred) || availableSkus[0] || null;
    const pricedSkus = availableSkus.filter((s) => Number(s.price) > 0);
    const cheapest = pricedSkus.length ? [...pricedSkus].sort((a, b) => Number(a.price) - Number(b.price))[0] : null;
    const selectedId = selectedSkuByItem[it.controlNumber];
    const selected = availableSkus.find((s) => s.id === selectedId) || preferred || cheapest || availableSkus[0] || null;
    const calc = selected ? vendorUnitsForShortfall(it, selected, shortfall) : { units: Math.ceil(shortfall), conversionKnown: false };
    const price = selected ? Number(selected.price) || 0 : 0;
    const pack = vendorPack(it, selected);
    const cheapestCalc = cheapest ? vendorUnitsForShortfall(it, cheapest, shortfall) : null;
    const cheapestTotal = cheapest && cheapestCalc ? cheapestCalc.units * (Number(cheapest.price) || 0) : null;
    return {
      item: it, shortfall, availableSkus, preferred, cheapest, selected,
      suggestedQty: calc.units, conversionKnown: calc.conversionKnown, overageBase: calc.overageBase,
      vendor: selected?.vendor || "Unassigned", vendorSku: selected?.vendorSku || "",
      purchaseUnit: pack.purchaseUnit, unitCost: price, lineTotal: calc.units * price,
      priceUpdatedAt: selected?.priceUpdatedAt || "", priceSource: selected?.priceSource || "", cheapestTotal,
    };
  }), [orderItems, selectedSkuByItem]);

  const byVendor = useMemo(() => {
    const map = {};
    rows.forEach((r) => { (map[r.vendor] = map[r.vendor] || []).push(r); });
    return map;
  }, [rows]);

  function setSku(controlNumber, skuId) { setSelectedSkuByItem((p) => ({ ...p, [controlNumber]: skuId })); }
  function chooseCheapestAll() {
    const next = {};
    rows.forEach((r) => { if (r.cheapest) next[r.item.controlNumber] = r.cheapest.id; });
    setSelectedSkuByItem(next);
    showToast("Cheapest available vendor selected for priced items");
  }
  function choosePreferredAll() { setSelectedSkuByItem({}); showToast("Preferred vendors restored"); }
  const [creatingPO, setCreatingPO] = useState(null);

  async function createPO(vendor, vendorRows) {
    if (creatingPO) return;
    setCreatingPO(vendor);
    try {
      const lines = vendorRows.map((r) => ({
        controlNumber: r.item.controlNumber, itemCode: r.item.itemCode, name: r.item.name, vendorSku: r.vendorSku || "",
        qty: r.suggestedQty, purchaseUnit: r.purchaseUnit, unitCost: r.unitCost,
      }));
      await api.createOrder(rid, { vendor, createdBy: "", note: "", lines });
      showToast(`Draft PO created for ${vendor}`);
      onCreatedPO?.();
    } catch (e) { showToast("Couldn't create purchase order"); }
    finally { setCreatingPO(null); }
  }

  async function copyVendorList(vendor, vendorRows) {
    const total = vendorRows.reduce((s, r) => s + r.lineTotal, 0);
    const lines = vendorRows.map((r) => `${r.item.controlNumber} ${r.item.name}${r.vendorSku ? ` (SKU ${r.vendorSku})` : ""} — ${r.suggestedQty} ${r.purchaseUnit} (${fmtMoney(r.lineTotal)})`);
    const text = `${(restaurantName || "RESTAURANT").toUpperCase()} — ${vendor.toUpperCase()} ORDER\n${fmtDate(todayISO())}\n\n${lines.join("\n")}\n\nEstimated Total: ${fmtMoney(total)}`;
    try { await navigator.clipboard.writeText(text); showToast(`${vendor} list copied`); } catch (e) { showToast("Copy failed — select manually"); }
  }

  function downloadVendorCSV(vendor, vendorRows) {
    const data = [["Control #", "Item Name", "Vendor SKU", "Count Unit Shortfall", "Qty to Order", "Purchase Unit", "Unit Cost", "Line Total", "Price Date", "Price Source"]];
    vendorRows.forEach((r) => data.push([r.item.controlNumber, r.item.name, r.vendorSku || "", r.shortfall, r.suggestedQty, r.purchaseUnit, r.unitCost, r.lineTotal.toFixed(2), r.priceUpdatedAt, r.priceSource]));
    downloadCSV(`${vendor.replace(/\s+/g, "_")}_order_${todayISO()}.csv`, data);
    showToast(`${vendor} CSV downloaded`);
  }
  function downloadAllCSV() {
    const data = [["Vendor", "Control #", "Item Name", "Vendor SKU", "Count Unit Shortfall", "Qty to Order", "Purchase Unit", "Unit Cost", "Line Total", "Price Date", "Price Source"]];
    rows.forEach((r) => data.push([r.vendor, r.item.controlNumber, r.item.name, r.vendorSku || "", r.shortfall, r.suggestedQty, r.purchaseUnit, r.unitCost, r.lineTotal.toFixed(2), r.priceUpdatedAt, r.priceSource]));
    downloadCSV(`full_order_${todayISO()}.csv`, data);
    showToast("Combined CSV downloaded");
  }

  const grandTotal = rows.reduce((s, r) => s + r.lineTotal, 0);
  const unpriced = rows.filter((r) => !r.selected || r.unitCost <= 0).length;
  const unknownConversions = rows.filter((r) => r.selected && !r.conversionKnown).length;

  if (rows.length === 0) return <EmptyState good text="Everything enabled for ordering is at or above par. Nothing to order right now." />;

  return (
    <div className="fade-slide-in" data-testid="order-tab">
      <PageTitle
        right={
          <div className="flex gap-2 items-center flex-wrap">
            <button className={btnGhost} onClick={choosePreferredAll} data-testid="order-preferred-all">Preferred Vendors</button>
            <button className={btnGhost} onClick={chooseCheapestAll} data-testid="order-cheapest-all">Cheapest Available</button>
            <button className={btnAcc} onClick={downloadAllCSV} data-testid="order-download-all"><Download size={15} /> Download All</button>
          </div>
        }>
        Smart Order Generator
      </PageTitle>
      <div className="text-xs text-slate-500 -mt-3 mb-4">Shortfalls are measured in count units, then converted to whole vendor purchase packs.</div>

      <div className="grid gap-2.5 mb-4" style={{ gridTemplateColumns: "repeat(auto-fit,minmax(180px,1fr))" }}>
        <div className={`${cardCls} p-3`}><div className="text-[11px] text-slate-500 uppercase font-bold">Items to order</div><div className="text-2xl font-extrabold num" style={{ color: "var(--acc)" }}>{rows.length}</div></div>
        <div className={`${cardCls} p-3`}><div className="text-[11px] text-slate-500 uppercase font-bold">Estimated order</div><div className="text-2xl font-extrabold num" style={{ color: "var(--acc)" }}>{fmtMoney(grandTotal)}</div></div>
        <div className={`${cardCls} p-3`}><div className="text-[11px] text-slate-500 uppercase font-bold">Needs price</div><div className="text-2xl font-extrabold num" style={{ color: unpriced ? "#EF4444" : "#10B981" }}>{unpriced}</div></div>
        <div className={`${cardCls} p-3`}><div className="text-[11px] text-slate-500 uppercase font-bold">Pack conversion review</div><div className="text-2xl font-extrabold num" style={{ color: unknownConversions ? "#EF4444" : "#10B981" }}>{unknownConversions}</div></div>
      </div>

      {Object.entries(byVendor).map(([vendor, vendorRows]) => {
        const total = vendorRows.reduce((s, r) => s + r.lineTotal, 0);
        return (
          <div key={vendor} className="mb-6">
            <Banner title={vendor} right={
              <>
                <strong className="num">{fmtMoney(total)}</strong>
                <button className={btnGhost} onClick={() => createPO(vendor, vendorRows)} disabled={creatingPO === vendor} data-testid={`create-po-${vendor}`}><ClipboardCheck size={13} /> {creatingPO === vendor ? "Creating…" : "Create PO"}</button>
                <button className={btnGhost} onClick={() => copyVendorList(vendor, vendorRows)} data-testid={`copy-order-${vendor}`}><Copy size={13} /> Copy</button>
                <button className={btnGhost} onClick={() => downloadVendorCSV(vendor, vendorRows)} data-testid={`csv-order-${vendor}`}><Download size={13} /> CSV</button>
              </>
            } />
            <div className={`${cardCls} overflow-x-auto`}>
              <table className="ops-table">
                <thead><tr><th>Control #</th><th>Item</th><th>Shortfall</th><th>Vendor / SKU</th><th>Order</th><th>Cost</th><th>Est. Total</th></tr></thead>
                <tbody>
                  {vendorRows.map((r) => (
                    <tr key={r.item.controlNumber} data-testid={`order-row-${r.item.controlNumber}`}>
                      <td className="font-bold" style={{ color: "var(--acc)" }}>{r.item.controlNumber}</td>
                      <td className="font-semibold text-slate-200">
                        {r.item.name}
                        {!r.conversionKnown && r.selected && <div className="text-[11px] text-red-400 mt-0.5">Pack conversion incomplete — using 1:1 fallback</div>}
                      </td>
                      <td className="num">{num(r.shortfall, 1)} {r.item.purchaseUnit}</td>
                      <td className="min-w-[220px]">
                        {r.availableSkus.length ? (
                          <select className={`${inpCls} min-w-[205px]`} data-testid={`order-sku-${r.item.controlNumber}`} value={r.selected?.id || ""} onChange={(e) => setSku(r.item.controlNumber, e.target.value)}>
                            {r.availableSkus.map((s) => {
                              const c = vendorUnitsForShortfall(r.item, s, r.shortfall);
                              const t = c.units * (Number(s.price) || 0);
                              return <option key={s.id} value={s.id}>{s.vendor} — {s.vendorSku || "no SKU"} — {c.units} {vendorPack(r.item, s).purchaseUnit} / {fmtMoney(t)}{s.preferred ? " ★" : ""}</option>;
                            })}
                          </select>
                        ) : <span className="text-red-400">No vendor SKU</span>}
                        {r.cheapest && r.selected && r.cheapest.id !== r.selected.id && r.cheapestTotal !== null && r.cheapestTotal < r.lineTotal && (
                          <div className="text-[11px] text-slate-500 mt-1">Cheapest option saves {fmtMoney(r.lineTotal - r.cheapestTotal)}</div>
                        )}
                      </td>
                      <td><strong className="num">{r.suggestedQty}</strong> {r.purchaseUnit}</td>
                      <td>{r.unitCost > 0 ? <span className="num">{fmtMoney(r.unitCost)}</span> : <span className="text-red-400">price needed</span>}<div className="text-[10.5px] text-slate-500">{r.priceUpdatedAt ? fmtDate(r.priceUpdatedAt) : ""}</div></td>
                      <td className="num font-bold">{fmtMoney(r.lineTotal)}</td>
                    </tr>
                  ))}
                  <tr><td colSpan={6} className="text-right font-bold border-b-0">Vendor Total</td><td className="num font-bold border-b-0">{fmtMoney(total)}</td></tr>
                </tbody>
              </table>
            </div>
          </div>
        );
      })}
    </div>
  );
}
