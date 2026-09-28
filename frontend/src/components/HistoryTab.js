import React, { useEffect, useState } from "react";
import { Search, Star } from "lucide-react";
import { preferredSku, priceAsOf, fmtDate, fmtMoney, num } from "../lib/calc";
import { PageTitle, EmptyState, SectionLabel, cardCls, inpCls } from "./common";

export function HistoryTab({ items, purchases, focusControlNumber }) {
  const [search, setSearch] = useState("");
  const [selectedCN, setSelectedCN] = useState(items[0]?.controlNumber || "");

  useEffect(() => { if (!selectedCN && items.length > 0) setSelectedCN(items[0].controlNumber); }, [items, selectedCN]);
  useEffect(() => { if (focusControlNumber) setSelectedCN(focusControlNumber); }, [focusControlNumber]);

  const filteredItems = items.filter((it) => it.name.toLowerCase().includes(search.toLowerCase()) || it.controlNumber.toLowerCase().includes(search.toLowerCase()));
  const selected = items.find((it) => it.controlNumber === selectedCN);
  const history = purchases.filter((p) => p.controlNumber === selectedCN).sort((a, b) => b.invoiceDate.localeCompare(a.invoiceDate));
  const currentPrice = history.length ? Number(history[0].unitCost) : (selected ? Number((preferredSku(selected) || {}).price) || 0 : 0);

  const windows = [30, 60, 90, 180].map((d) => {
    const past = priceAsOf(purchases, selectedCN, d);
    const delta = past !== null ? currentPrice - past : null;
    const pct = (past !== null && past !== 0) ? (delta / past) * 100 : null;
    return { days: d, past, delta, pct };
  });

  if (items.length === 0) return <EmptyState text="No items yet. Add items in Item Setup first." />;

  return (
    <div className="fade-slide-in" data-testid="history-tab">
      <PageTitle>Price History</PageTitle>
      <div className="grid gap-4" style={{ gridTemplateColumns: "260px 1fr" }}>
        <div className={`${cardCls} overflow-hidden max-h-[520px] flex flex-col`}>
          <div className="p-2.5">
            <div className="relative">
              <Search size={14} className="absolute left-2 top-2.5 text-slate-500" />
              <input className={`${inpCls} w-full pl-7 text-[13px]`} data-testid="history-search" placeholder="Search…" value={search} onChange={(e) => setSearch(e.target.value)} />
            </div>
          </div>
          <div className="overflow-y-auto">
            {filteredItems.map((it) => (
              <div key={it.controlNumber} onClick={() => setSelectedCN(it.controlNumber)} data-testid={`history-item-${it.controlNumber}`}
                className="px-3 py-2.5 cursor-pointer text-[13px] border-l-[3px] transition-colors"
                style={{ background: selectedCN === it.controlNumber ? "#1A2438" : "transparent", borderLeftColor: selectedCN === it.controlNumber ? "var(--acc)" : "transparent" }}>
                <div className="font-bold text-[11.5px]" style={{ color: "var(--acc)" }}>{it.controlNumber}</div>
                <div className="text-slate-300">{it.name}</div>
              </div>
            ))}
          </div>
        </div>

        {selected && (
          <div>
            <div className={`${cardCls} p-5 mb-4`}>
              <div className="flex justify-between items-center mb-3.5">
                <div>
                  <div className="font-bold text-base text-slate-100">{selected.name}</div>
                  <div className="text-xs text-slate-500">{selected.controlNumber}</div>
                </div>
                <div className="text-xl font-bold num" style={{ color: "var(--acc)" }} data-testid="history-current-price">{fmtMoney(currentPrice)}</div>
              </div>

              <div className="mb-4">
                <SectionLabel>Vendors on File</SectionLabel>
                {(selected.vendorSkus || []).length === 0 ? (
                  <div className="text-[13px] text-slate-500">No vendors set up for this item yet.</div>
                ) : (
                  <div className="border border-[#28354A] rounded-lg overflow-hidden">
                    <table className="ops-table">
                      <thead><tr><th>Vendor</th><th>SKU</th><th>Most Recent Qty</th><th>Most Recent Price</th><th>Date</th></tr></thead>
                      <tbody>
                        {selected.vendorSkus.map((vs) => {
                          const vendorHistory = history.filter((p) => p.vendor === vs.vendor);
                          const latest = vendorHistory[0];
                          return (
                            <tr key={vs.id}>
                              <td className="font-semibold text-slate-200">
                                {vs.preferred && <Star size={12} fill="#EAB308" color="#EAB308" className="inline mr-1 -mt-0.5" />}
                                {vs.vendor}
                              </td>
                              <td>{vs.vendorSku || "—"}</td>
                              <td className="num">{latest ? `${num(latest.qty)} ${latest.unit}` : "—"}</td>
                              <td className="num font-bold">{fmtMoney(latest ? latest.unitCost : vs.price)}{!latest && <span className="font-normal text-[11px] text-slate-500"> (on file, no purchases yet)</span>}</td>
                              <td>{latest ? fmtDate(latest.invoiceDate) : "—"}</td>
                            </tr>
                          );
                        })}
                      </tbody>
                    </table>
                  </div>
                )}
              </div>
              <div className="grid grid-cols-4 gap-3">
                {windows.map((w) => {
                  const trendColor = w.past === null ? "#64748B" : w.delta > 0 ? "#EF4444" : w.delta < 0 ? "#10B981" : "#94A3B8";
                  const cardBg = w.past === null ? "#0F1626" : w.delta > 0 ? "rgba(239,68,68,0.08)" : w.delta < 0 ? "rgba(16,185,129,0.08)" : "#0F1626";
                  return (
                    <div key={w.days} className="rounded-xl px-2.5 py-4 text-center border-2" style={{ background: cardBg, borderColor: trendColor }} data-testid={`history-window-${w.days}`}>
                      <div className="text-[13px] uppercase tracking-wide font-extrabold" style={{ color: trendColor }}>{w.days}-Day</div>
                      {w.past === null ? <div className="text-[13px] text-slate-500 mt-2">No data</div> : (
                        <>
                          <div className="text-[13px] text-slate-400 mt-1.5">was {fmtMoney(w.past)}</div>
                          <div className="font-extrabold text-xl num mt-1" style={{ color: trendColor }}>
                            {w.delta > 0 ? "▲" : w.delta < 0 ? "▼" : "–"} {fmtMoney(Math.abs(w.delta))}
                          </div>
                          {w.pct !== null && <div className="font-bold text-sm num" style={{ color: trendColor }}>{w.pct > 0 ? "+" : ""}{num(w.pct, 1)}%</div>}
                        </>
                      )}
                    </div>
                  );
                })}
              </div>
            </div>

            <SectionLabel>All Purchases ({history.length})</SectionLabel>
            {history.length === 0 ? <EmptyState text="No purchases logged for this item yet." /> : (
              <div className={`${cardCls} overflow-hidden`}>
                <table className="ops-table">
                  <thead><tr><th>Date</th><th>Vendor</th><th>Invoice #</th><th>Qty</th><th>Unit Cost</th></tr></thead>
                  <tbody>{history.map((p) => <tr key={p.id}><td>{fmtDate(p.invoiceDate)}</td><td>{p.vendor}</td><td>{p.invoiceNumber}</td><td className="num">{p.qty} {p.unit}</td><td className="num">{fmtMoney(p.unitCost)}</td></tr>)}</tbody>
                </table>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
