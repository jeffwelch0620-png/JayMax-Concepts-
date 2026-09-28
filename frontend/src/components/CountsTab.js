import React, { useEffect, useMemo, useState } from "react";
import { Save } from "lucide-react";
import { isCountActive, num, todayISO } from "../lib/calc";
import { PageTitle, EmptyState, cardCls, inpCls, btnAcc, btnGhost } from "./common";

export function CountsTab({ items, persist, showToast }) {
  const [draft, setDraft] = useState({});
  const countItems = useMemo(() => items.filter(isCountActive), [items]);
  useEffect(() => {
    const d = {};
    countItems.forEach((it) => (d[it.controlNumber] = it.currentStock));
    setDraft(d);
  }, [countItems]);

  if (countItems.length === 0) return <EmptyState text="No items are included in the biweekly count. Enable them in Item Setup first." />;

  function updateDraft(cn, val) { setDraft((p) => ({ ...p, [cn]: val })); }

  async function saveOne(cn) {
    const next = items.map((it) => it.controlNumber === cn ? { ...it, currentStock: Number(draft[cn]) || 0, lastCounted: todayISO() } : it);
    await persist(next);
    showToast("Count saved");
  }
  async function saveAll() {
    const next = items.map((it) => isCountActive(it) ? ({ ...it, currentStock: draft[it.controlNumber] !== undefined ? Number(draft[it.controlNumber]) || 0 : it.currentStock, lastCounted: todayISO() }) : it);
    await persist(next);
    showToast("All counts saved");
  }

  return (
    <div className="fade-slide-in" data-testid="counts-tab">
      <PageTitle right={<button data-testid="save-all-counts-button" className={btnAcc} onClick={saveAll}><Save size={15} /> Save All Counts</button>}>
        Physical Count Entry
      </PageTitle>
      {/* Desktop / tablet table */}
      <div className={`${cardCls} overflow-hidden hidden md:block`}>
        <div className="overflow-x-auto">
          <table className="ops-table">
            <thead><tr><th>Control #</th><th>Item</th><th>Current Count</th><th>Par</th><th></th></tr></thead>
            <tbody>
              {countItems.map((it) => (
                <tr key={it.controlNumber} data-testid={`count-row-${it.controlNumber}`}>
                  <td className="font-bold" style={{ color: "var(--acc)" }}>{it.controlNumber}</td>
                  <td className="font-semibold text-slate-200">{it.name}</td>
                  <td>
                    <input data-testid={`count-input-${it.controlNumber}`} type="number" step="0.1" className={`${inpCls} w-24`} value={draft[it.controlNumber] ?? ""} onChange={(e) => updateDraft(it.controlNumber, e.target.value)} />
                    {" "}<span className="text-xs text-slate-500">{it.purchaseUnit}</span>
                  </td>
                  <td className="num">{num(it.par)} {it.purchaseUnit}</td>
                  <td><button data-testid={`count-save-${it.controlNumber}`} className={btnGhost} onClick={() => saveOne(it.controlNumber)}>Save</button></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* Mobile card layout */}
      <div className="md:hidden flex flex-col gap-2.5" data-testid="counts-mobile-list">
        {countItems.map((it) => (
          <div key={it.controlNumber} className={`${cardCls} p-3.5`} data-testid={`count-card-${it.controlNumber}`}>
            <div className="flex items-start justify-between gap-2 mb-2.5">
              <div className="min-w-0">
                <div className="font-bold text-xs" style={{ color: "var(--acc)" }}>{it.controlNumber}</div>
                <div className="font-semibold text-slate-200 text-sm leading-snug break-words">{it.name}</div>
              </div>
              <div className="text-right shrink-0">
                <div className="text-[10px] uppercase tracking-wide text-slate-500 font-bold">Par</div>
                <div className="num text-sm text-slate-300">{num(it.par)} {it.purchaseUnit}</div>
              </div>
            </div>
            <div className="flex items-center gap-2">
              <div className="flex items-center gap-1.5 flex-1">
                <input data-testid={`count-input-${it.controlNumber}`} type="number" step="0.1" inputMode="decimal" className={`${inpCls} flex-1 w-full`} value={draft[it.controlNumber] ?? ""} onChange={(e) => updateDraft(it.controlNumber, e.target.value)} placeholder="Count" />
                <span className="text-xs text-slate-500 shrink-0">{it.purchaseUnit}</span>
              </div>
              <button data-testid={`count-save-${it.controlNumber}`} className={btnGhost} onClick={() => saveOne(it.controlNumber)}>Save</button>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
