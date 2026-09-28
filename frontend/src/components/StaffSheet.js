import React, { useState } from "react";
import { Lock, X, Check, ChevronDown, ChevronUp, ChefHat } from "lucide-react";
import { RESTAURANTS, num, fmtDate } from "../lib/calc";
import * as api from "../lib/api";
import { inpCls, btnAcc, btnGhost, cardCls, Pill } from "./common";

const TRACKS = [
  { id: "daily", label: "Daily Prep" },
  { id: "bulk", label: "Bulk Prep" },
];

export function StaffSheet({ onClose }) {
  const [rid, setRid] = useState("");
  const [track, setTrack] = useState("daily");
  const [pin, setPin] = useState("");
  const [err, setErr] = useState("");
  const [sheet, setSheet] = useState(null);
  const [completing, setCompleting] = useState(null);
  const [name, setName] = useState("");
  const [batches, setBatches] = useState(1);
  const [expanded, setExpanded] = useState({});
  const [busy, setBusy] = useState(false);
  const [unlocking, setUnlocking] = useState(false);

  const restaurant = RESTAURANTS.find((r) => r.id === rid);

  async function unlock() {
    setErr("");
    if (!rid) { setErr("Pick your restaurant first"); return; }
    setUnlocking(true);
    try {
      const v = await api.verifyStaffPin(rid, pin);
      if (!v.ok) { setErr("Wrong PIN — check with your manager"); return; }
      const s = await api.staffPrepsheet(rid, pin, track);
      setSheet(s);
    } catch (e) { setErr(e?.response?.data?.detail || "Couldn't unlock — try again"); }
    finally { setUnlocking(false); }
  }

  async function refresh() {
    try { setSheet(await api.staffPrepsheet(rid, pin, track)); } catch { /* keep current */ }
  }

  async function markDone() {
    setErr("");
    if (!name.trim()) { setErr("Enter your name so we know who prepped it"); return; }
    setBusy(true);
    try {
      await api.staffCompleteTask(rid, { pin, listId: sheet.listId, taskId: completing.id, batches: Number(batches) || 0, doneBy: name.trim() });
      setCompleting(null);
      await refresh();
    } catch (e) { setErr(e?.response?.data?.detail || "Couldn't save — tell your manager"); }
    finally { setBusy(false); }
  }

  return (
    <div className="fixed inset-0 z-[60] bg-[#0B0F17] overflow-y-auto" data-testid="staff-sheet">
      <div className="max-w-[640px] mx-auto px-4 py-6 pb-24">
        <div className="flex justify-between items-center mb-6">
          <div className="flex items-center gap-2.5">
            <span className="w-9 h-9 rounded-xl flex items-center justify-center bg-[#F97316]"><ChefHat size={18} className="text-[#0B0F17]" /></span>
            <div>
              <div className="font-display font-bold text-slate-100">Prep Sheet</div>
              <div className="text-[10px] uppercase tracking-[0.14em] text-slate-500 font-bold">Staff View — Tasks Only</div>
            </div>
          </div>
          <button onClick={onClose} className="p-2 text-slate-400 hover:text-white transition" data-testid="staff-sheet-close"><X size={20} /></button>
        </div>

        {!sheet ? (
          <div className={`${cardCls} p-6`} data-testid="staff-pin-gate">
            <div className="flex items-center gap-2 mb-4"><Lock size={16} style={{ color: "#F97316" }} /><span className="font-display font-bold text-slate-100">Enter your store's staff PIN</span></div>
            <div className="flex gap-2 mb-4 flex-wrap">
              {RESTAURANTS.map((r) => (
                <button key={r.id} onClick={() => setRid(r.id)} data-testid={`staff-store-${r.id}`}
                  className={`rounded-full px-4 py-2 text-sm font-bold border transition ${rid === r.id ? "text-[#0B0F17]" : "text-slate-400 bg-[#161F30] border-[#28354A]"}`}
                  style={rid === r.id ? { background: r.accent, borderColor: r.accent } : {}}>
                  {r.short}
                </button>
              ))}
            </div>
            <div className="flex gap-2 mb-4 flex-wrap" data-testid="staff-track-selector">
              {TRACKS.map((t) => (
                <button key={t.id} onClick={() => setTrack(t.id)} data-testid={`staff-track-${t.id}`}
                  className={t.id === track ? btnAcc : btnGhost}>
                  {t.label}
                </button>
              ))}
            </div>
            <div className="flex gap-2">
              <input type="password" inputMode="numeric" className={`${inpCls} flex-1 text-center text-xl tracking-[0.4em]`} data-testid="staff-pin-entry"
                placeholder="••••" maxLength={8} value={pin} onChange={(e) => setPin(e.target.value)}
                onKeyDown={(e) => { if (e.key === "Enter") unlock(); }} />
              <button className={btnAcc} onClick={unlock} disabled={unlocking} data-testid="staff-unlock-button">{unlocking ? "Unlocking…" : "Unlock"}</button>
            </div>
            {err && <div className="text-red-400 text-xs mt-3" data-testid="staff-error">{err}</div>}
          </div>
        ) : (
          <>
            <div className="flex justify-between items-center mb-4 flex-wrap gap-2">
              <div>
                <div className="font-display font-bold text-slate-100">{restaurant?.name} — {TRACKS.find((t) => t.id === track)?.label}</div>
                <div className="text-xs text-slate-500">Prep list for {fmtDate(sheet.date)}</div>
              </div>
              <div className="flex gap-2">
                <button className={btnGhost} onClick={refresh} data-testid="staff-refresh">Refresh</button>
                <button className={btnGhost} onClick={() => { setSheet(null); setPin(""); }} data-testid="staff-lock-button"><Lock size={13} /> Lock</button>
              </div>
            </div>

            {err && <div className="text-red-400 text-xs mb-3" data-testid="staff-error">{err}</div>}

            {sheet.tasks.length === 0 ? (
              <div className="text-center py-14 px-5 rounded-xl border border-dashed border-[#334155] bg-[#161F30] text-sm text-slate-500" data-testid="staff-empty">
                No prep list has been released for today yet. Check with your manager.
              </div>
            ) : (
              <div className="flex flex-col gap-3" data-testid="staff-task-list">
                {sheet.tasks.map((t) => {
                  const done = t.batchesPlanned > 0 && t.remaining === 0;
                  const open = expanded[t.id];
                  return (
                    <div key={t.id} className={`${cardCls} p-4`} style={done ? { opacity: 0.55 } : {}} data-testid={`staff-task-${t.id}`}>
                      <div className="flex justify-between items-start gap-3">
                        <div className="flex-1">
                          <div className="font-bold text-slate-100 text-base">{t.name}</div>
                          <div className="text-sm text-slate-400 mt-0.5">
                            Prep <b className="num text-slate-200">{num(t.remaining, 1)}</b> more batch{t.remaining !== 1 ? "es" : ""} of {num(t.batchesPlanned, 1)}
                            <span className="text-slate-500"> ({num(t.card.yieldQty, 1)} {t.card.yieldUOM} per batch)</span>
                          </div>
                          {t.note && <div className="text-xs text-amber-400 mt-1">{t.note}</div>}
                          {t.doneBy && <div className="text-[11px] text-slate-500 mt-1">Last prepped by {t.doneBy}</div>}
                        </div>
                        {done
                          ? <Pill color="#10B981" bg="rgba(16,185,129,0.12)" testId={`staff-done-${t.id}`}><Check size={11} className="inline -mt-0.5" /> Done</Pill>
                          : <button className={btnAcc} onClick={() => { setCompleting(t); setBatches(t.remaining); setErr(""); }} data-testid={`staff-mark-done-${t.id}`}>Mark Prepped</button>}
                      </div>
                      {(t.card.procedure || t.card.equipment || t.card.shelfLife) && (
                        <div className="mt-2">
                          <button className="text-xs font-semibold flex items-center gap-1 hover:underline" style={{ color: "var(--acc, #F97316)" }}
                            onClick={() => setExpanded((x) => ({ ...x, [t.id]: !open }))} data-testid={`staff-card-toggle-${t.id}`}>
                            {open ? <ChevronUp size={13} /> : <ChevronDown size={13} />} Recipe Card
                          </button>
                          {open && (
                            <div className="mt-2 text-xs text-slate-300 bg-[#0F1626] border border-[#28354A] rounded-lg p-3 space-y-1.5" data-testid={`staff-card-${t.id}`}>
                              {t.card.equipment && <div><b>Equipment:</b> {t.card.equipment}</div>}
                              {t.card.shelfLife && <div><b>Shelf life:</b> {t.card.shelfLife}</div>}
                              {t.card.procedure && <div className="whitespace-pre-wrap"><b>Procedure:</b>{"\n"}{t.card.procedure}</div>}
                            </div>
                          )}
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            )}
          </>
        )}
      </div>

      {completing && (
        <div className="fixed inset-0 z-[70] flex items-center justify-center bg-black/60 backdrop-blur-sm" data-testid="staff-complete-modal">
          <div className={`${cardCls} w-full max-w-sm p-5 m-4 bg-[#161F30]`}>
            <div className="font-display font-bold text-slate-100 mb-3">Mark Prepped — {completing.name}</div>
            <div className="flex flex-col gap-3">
              <label className="flex flex-col gap-1 text-xs text-slate-400 font-semibold">Your Name
                <input className={inpCls} data-testid="staff-name-input" placeholder="e.g. Maria" value={name} onChange={(e) => setName(e.target.value)} />
              </label>
              <label className="flex flex-col gap-1 text-xs text-slate-400 font-semibold">Batches Prepped (of {num(completing.remaining, 1)} remaining)
                <input type="number" min="0.5" step="0.5" className={inpCls} data-testid="staff-batches-input" value={batches} onChange={(e) => setBatches(e.target.value)} />
              </label>
            </div>
            <div className="flex gap-2 justify-end mt-4">
              <button className={btnGhost} onClick={() => setCompleting(null)}>Cancel</button>
              <button className={btnAcc} onClick={markDone} disabled={busy} data-testid="staff-confirm-done-button">{busy ? "Saving…" : "Confirm"}</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
