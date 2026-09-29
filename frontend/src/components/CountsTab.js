import React, { useEffect, useMemo, useState } from "react";
import { Save, History, X, ChevronDown, ChevronRight } from "lucide-react";
import { isCountActive, num, todayISO } from "../lib/calc";
import { PageTitle, EmptyState, cardCls, inpCls, btnAcc, btnGhost } from "./common";
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
  const [draft, setDraft] = useState({});
  const [submittedBy, setSubmittedBy] = useState("");
  const countItems = useMemo(() => items.filter(isCountActive), [items]);
  useEffect(() => {
    const d = {};
    countItems.forEach((it) => (d[it.controlNumber] = it.currentStock));
    setDraft(d);
  }, [countItems]);

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
  useEffect(() => { if (historyOpen) loadHistory(); /* eslint-disable-next-line react-hooks/exhaustive-deps */ }, [historyOpen, historyFrom, historyTo]);

  if (countItems.length === 0) return <EmptyState text="No items are included in the biweekly count. Enable them in Item Setup first." />;

  function updateDraft(cn, val) { setDraft((p) => ({ ...p, [cn]: val })); }

  function applyLocally(entries) {
    const byControlNumber = new Map(entries.map((e) => [e.controlNumber, e]));
    onCountsApplied(items.map((it) => {
      const hit = byControlNumber.get(it.controlNumber);
      return hit ? { ...it, currentStock: hit.newStock, lastCounted: todayISO() } : it;
    }));
  }

  async function saveOne(cn) {
    if (!submittedBy.trim()) { showToast("Enter your name before saving"); return; }
    const onHand = Number(draft[cn]) || 0;
    try {
      await api.submitCounts(rid, { submittedBy: submittedBy.trim(), counts: [{ controlNumber: cn, onHand }] });
      applyLocally([{ controlNumber: cn, newStock: onHand }]);
      showToast("Count saved");
    } catch (e) { showToast(e?.response?.data?.detail || "Couldn't save count"); }
  }
  async function saveAll() {
    if (!submittedBy.trim()) { showToast("Enter your name before saving"); return; }
    const counts = countItems.map((it) => ({ controlNumber: it.controlNumber, onHand: draft[it.controlNumber] !== undefined ? Number(draft[it.controlNumber]) || 0 : it.currentStock }));
    try {
      await api.submitCounts(rid, { submittedBy: submittedBy.trim(), counts });
      applyLocally(counts.map((c) => ({ controlNumber: c.controlNumber, newStock: c.onHand })));
      showToast("All counts saved");
    } catch (e) { showToast(e?.response?.data?.detail || "Couldn't save counts"); }
  }

  return (
    <>
    <div className="fade-slide-in" data-testid="counts-tab">
      <PageTitle right={
        <div className="flex items-end gap-2 flex-wrap">
          <label className="flex flex-col gap-1 text-xs text-slate-400 font-semibold">Counted By
            <input className={`${inpCls} w-40`} data-testid="counted-by-input" placeholder="Your name" value={submittedBy} onChange={(e) => setSubmittedBy(e.target.value)} />
          </label>
          <button className={btnGhost} onClick={() => setHistoryOpen(true)} data-testid="count-history-button"><History size={14} /> Count History</button>
          <button data-testid="save-all-counts-button" className={btnAcc} onClick={saveAll}><Save size={15} /> Save All Counts</button>
        </div>
      }>
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
                            <div className="font-semibold text-slate-200 text-sm">{fmtDateTime(h.submittedAt)}</div>
                            <div className="text-xs text-slate-500">By {h.submittedBy} · {h.source === "staff_pwa" ? "Staff portal" : "Management"}</div>
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
                                <td className="num font-bold">{num(it.newStock, 1)} {it.purchaseUnit}</td>
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
