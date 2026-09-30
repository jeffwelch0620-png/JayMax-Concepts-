import React, { useEffect, useMemo, useState } from "react";
import { History, X, ChevronDown, ChevronRight } from "lucide-react";
import { isCountActive, num, todayISO, fmtDate } from "../lib/calc";
import { PageTitle, EmptyState, cardCls, inpCls, btnGhost } from "./common";
import { useCountSheet, CountSheetControls, CountSheetBanner, CountSheetList, SaveAllCountsButton } from "./CountSheet";
import * as api from "../lib/api";

function isoDaysAgo(n) {
  const d = new Date();
  d.setDate(d.getDate() - n);
  return new Date(d.getTime() - d.getTimezoneOffset() * 60000).toISOString().slice(0, 10);
}
function fmtDateTime(iso) {
  if (!iso) return "—";
  return new Date(iso).toLocaleString("en-US", { month: "short", day: "numeric", year: "numeric", hour: "numeric", minute: "2-digit" });
}

export function CountsTab({ rid, items, onCountsApplied, showToast }) {
  const [submittedBy, setSubmittedBy] = useState("");
  const countItems = useMemo(() => items.filter(isCountActive).map((it) => ({ ...it, unit: it.purchaseUnit })), [items]);

  async function submit(entries, countDate) {
    const result = await api.submitCounts(rid, { submittedBy: submittedBy.trim(), countDate, counts: entries });
    const skipped = new Set(result.notApplied || []);
    const byControlNumber = new Map(entries.filter((e) => !skipped.has(e.controlNumber)).map((e) => [e.controlNumber, e]));
    onCountsApplied(items.map((it) => {
      const hit = byControlNumber.get(it.controlNumber);
      return hit ? { ...it, currentStock: hit.onHand, lastCounted: countDate } : it;
    }));
    return result;
  }
  const sheet = useCountSheet(countItems, submit);

  async function run(action) {
    if (!submittedBy.trim()) { showToast("Enter your name before saving"); return; }
    const r = await action();
    if (r.error) { showToast(r.error); return; }
    showToast(r.notApplied.length
      ? `Saved ${r.saved}. ${r.notApplied.length} already had a newer count, so on-hand wasn't changed.`
      : r.saved === 1 ? "Count saved" : `${r.saved} counts saved`);
  }

  // ---------------- Count History (management-only; not exposed on the PWA staff portal) ----------------
  const [historyOpen, setHistoryOpen] = useState(false);
  const [historyFrom, setHistoryFrom] = useState(() => isoDaysAgo(30));
  const [historyTo, setHistoryTo] = useState(() => todayISO());
  const [history, setHistory] = useState(null);
  const [historyErr, setHistoryErr] = useState("");
  const [expandedSubmission, setExpandedSubmission] = useState(null);

  async function loadHistory() {
    setHistoryErr("");
    try { setHistory(await api.itemCountSubmissionHistory(rid, historyFrom, historyTo)); }
    catch (e) { setHistory([]); setHistoryErr(e?.response?.data?.detail || "Couldn't load count history"); }
  }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => { if (historyOpen) loadHistory(); }, [historyOpen, historyFrom, historyTo]);

  if (countItems.length === 0) return <EmptyState text="No items are included in the biweekly count. Enable them in Item Setup first." />;

  return (
    <>
    <div className="fade-slide-in" data-testid="counts-tab">
      <PageTitle right={
        <div className="flex items-end gap-2 flex-wrap">
          <CountSheetControls sheet={sheet} name={submittedBy} setName={setSubmittedBy} nameTestId="counted-by-input" />
          <button className={btnGhost} onClick={() => setHistoryOpen(true)} data-testid="count-history-button"><History size={14} /> Count History</button>
          <SaveAllCountsButton sheet={sheet} onClick={() => run(sheet.saveAll)} testId="save-all-counts-button" />
        </div>
      }>
        Physical Count Entry
      </PageTitle>
      <CountSheetBanner sheet={sheet} />
      <CountSheetList sheet={sheet} showPar onSaveOne={(it) => run(() => sheet.saveOne(it))} />
    </div>

      {historyOpen && (
        <div className="fixed inset-0 z-[70] flex items-center justify-center bg-black/60 backdrop-blur-sm p-4" data-testid="count-history-modal">
          <div className={`${cardCls} w-full max-w-2xl max-h-[85vh] overflow-y-auto p-5 bg-[#161F30]`}>
            <div className="flex justify-between items-center mb-4">
              <div className="font-display font-bold text-slate-100 text-lg">Count History</div>
              <button onClick={() => setHistoryOpen(false)} className="p-1 text-slate-400 hover:text-white transition" data-testid="count-history-close"><X size={20} /></button>
            </div>
            <div className="flex gap-2 items-end mb-4 flex-wrap">
              <label className="flex flex-col gap-1 text-xs text-slate-400 font-semibold">From
                <input type="date" className={inpCls} value={historyFrom} onChange={(e) => setHistoryFrom(e.target.value)} data-testid="count-history-from" />
              </label>
              <label className="flex flex-col gap-1 text-xs text-slate-400 font-semibold">To
                <input type="date" className={inpCls} value={historyTo} onChange={(e) => setHistoryTo(e.target.value)} data-testid="count-history-to" />
              </label>
            </div>
            {historyErr && <div className="text-red-400 text-xs mb-3" data-testid="count-history-error">{historyErr}</div>}
            {!history ? (
              <div className="text-slate-500 text-sm py-6 text-center">Loading…</div>
            ) : history.length === 0 ? (
              <div className="text-slate-500 text-sm py-6 text-center" data-testid="count-history-empty">No counts submitted in this range.</div>
            ) : (
              <div className="flex flex-col gap-2" data-testid="count-history-list">
                {history.map((h) => {
                  const open = expandedSubmission === h.id;
                  return (
                    <div key={h.id} className="border border-[#28354A] rounded-lg overflow-hidden">
                      <button className="w-full flex items-center justify-between gap-3 px-3 py-2.5 hover:bg-white/[0.03] text-left" onClick={() => setExpandedSubmission(open ? null : h.id)} data-testid={`count-history-row-${h.id}`}>
                        <div className="flex items-center gap-2">
                          {open ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
                          <div>
                            <div className="font-semibold text-slate-200 text-sm">{h.countDate ? `Count for ${fmtDate(h.countDate)}` : fmtDateTime(h.submittedAt)}</div>
                            <div className="text-xs text-slate-500">By {h.submittedBy} · {h.source === "staff_pwa" ? "Staff portal" : "Management"}{h.countDate ? ` · entered ${fmtDateTime(h.submittedAt)}` : ""}</div>
                          </div>
                        </div>
                        <div className="text-xs text-slate-400 font-semibold">{h.itemCount} item{h.itemCount !== 1 ? "s" : ""}</div>
                      </button>
                      {open && (
                        <table className="ops-table" data-testid={`count-history-items-${h.id}`}>
                          <thead><tr><th>Item</th><th>Area</th><th>Previous</th><th>New</th></tr></thead>
                          <tbody>
                            {h.items.map((it) => (
                              <tr key={it.controlNumber}>
                                <td>{it.controlNumber} — {it.name}</td>
                                <td>{it.storageArea}</td>
                                <td className="num">{num(it.previousStock, 1)} {it.purchaseUnit}</td>
                                <td className="num font-bold">{num(it.newStock, 1)} {it.purchaseUnit}{it.applied === false && <span className="block text-[10.5px] font-normal text-amber-400">history only (newer count exists)</span>}</td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      )}
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        </div>
      )}
    </>
  );
}
