import React, { useEffect, useMemo, useState } from "react";
import { Save } from "lucide-react";
import { num, todayISO } from "../lib/calc";
import { cardCls, inpCls, btnAcc, btnGhost } from "./common";

// Shared by the manager's Enter Counts tab and the staff portal's count sheet, so both
// work the same way: pick the count date (backdating allowed), filter by storage area,
// type counts into plain text boxes (no spinner arrows), and see each entry in red
// until it's saved for that date, then white.

export const MAX_BACKDATE_DAYS = 31; // mirrors COUNT_BACKDATE_DAYS in backend/server.py

function isoDaysAgo(n) {
  const d = new Date();
  d.setDate(d.getDate() - n);
  return new Date(d.getTime() - d.getTimezoneOffset() * 60000).toISOString().slice(0, 10);
}

// A count is digits with at most one decimal point; any other keystroke is ignored.
const COUNT_TEXT = /^\d*\.?\d*$/;

const UNSAVED = { borderColor: "rgba(239,68,68,0.75)", background: "rgba(239,68,68,0.12)", color: "#FCA5A5" };
const SAVED = { color: "#FFFFFF" };

// items: [{ controlNumber, name, storageArea, unit, par?, currentStock, lastCounted }]
// onSave(entries: [{controlNumber, onHand}], countDate) -> Promise<{ notApplied?: string[] }>, throws on failure
export function useCountSheet(items, onSave) {
  const [countDate, setCountDate] = useState(() => todayISO());
  const [area, setArea] = useState("");
  const [draft, setDraft] = useState({});        // controlNumber -> text typed but not saved yet
  const [savedHere, setSavedHere] = useState({}); // `${date}|${controlNumber}` -> saved value
  const [busy, setBusy] = useState(false);

  useEffect(() => { setDraft({}); }, [countDate]);

  const areas = useMemo(() => [...new Set(items.map((it) => it.storageArea || "Unassigned"))].sort(), [items]);
  useEffect(() => { if (area && !areas.includes(area)) setArea(""); }, [areas, area]);

  const rows = useMemo(() => {
    const order = new Map(items.map((it, i) => [it.controlNumber, i]));
    return items
      .filter((it) => !area || (it.storageArea || "Unassigned") === area)
      .sort((a, b) => (a.storageArea || "Unassigned").localeCompare(b.storageArea || "Unassigned") || order.get(a.controlNumber) - order.get(b.controlNumber));
  }, [items, area]);

  function savedValue(it) {
    const key = `${countDate}|${it.controlNumber}`;
    if (savedHere[key] !== undefined) return savedHere[key];
    return it.lastCounted && String(it.lastCounted).slice(0, 10) === countDate ? String(it.currentStock ?? "") : undefined;
  }
  const valueOf = (it) => draft[it.controlNumber] ?? savedValue(it) ?? "";
  const isSaved = (it) => draft[it.controlNumber] === undefined && savedValue(it) !== undefined;
  const setValue = (cn, value) => { if (COUNT_TEXT.test(value)) setDraft((d) => ({ ...d, [cn]: value })); };

  const pending = items.filter((it) => draft[it.controlNumber] !== undefined && draft[it.controlNumber] !== "");

  async function save(targets) {
    const entries = [], invalid = [];
    targets.forEach((it) => {
      const text = draft[it.controlNumber];
      if (text === undefined || text === "") return;
      const n = Number(text);
      if (!Number.isFinite(n)) invalid.push(it.name); else entries.push({ controlNumber: it.controlNumber, onHand: n });
    });
    if (invalid.length) return { error: `Check the count for ${invalid.join(", ")}` };
    if (!entries.length) return { error: "Enter a count first" };
    setBusy(true);
    try {
      const date = countDate;
      const result = (await onSave(entries, date)) || {};
      setSavedHere((s) => ({ ...s, ...Object.fromEntries(entries.map((e) => [`${date}|${e.controlNumber}`, String(e.onHand)])) }));
      setDraft((d) => { const next = { ...d }; entries.forEach((e) => delete next[e.controlNumber]); return next; });
      return { saved: entries.length, notApplied: result.notApplied || [] };
    } catch (e) {
      return { error: e?.response?.data?.detail || "Couldn't save counts" };
    } finally {
      setBusy(false);
    }
  }

  return { countDate, setCountDate, area, setArea, areas, rows, valueOf, isSaved, setValue, pending, busy,
    saveOne: (it) => save([it]), saveAll: () => save(items) };
}

export function CountSheetControls({ sheet, name, setName, nameTestId }) {
  return (
    <div className="flex items-end gap-2 flex-wrap">
      <label className="flex flex-col gap-1 text-xs text-slate-400 font-semibold">Counted By
        <input className={`${inpCls} w-40`} data-testid={nameTestId} placeholder="Your name" value={name} onChange={(e) => setName(e.target.value)} />
      </label>
      <label className="flex flex-col gap-1 text-xs text-slate-400 font-semibold">Count Date
        <input type="date" className={`${inpCls} w-40`} data-testid="count-date-input" value={sheet.countDate}
          min={isoDaysAgo(MAX_BACKDATE_DAYS)} max={todayISO()}
          onChange={(e) => e.target.value && sheet.setCountDate(e.target.value)} />
      </label>
      <label className="flex flex-col gap-1 text-xs text-slate-400 font-semibold">Storage Area
        <select className={`${inpCls} w-44`} data-testid="count-area-select" value={sheet.area} onChange={(e) => sheet.setArea(e.target.value)}>
          <option value="">All areas</option>
          {sheet.areas.map((a) => <option key={a} value={a}>{a}</option>)}
        </select>
      </label>
    </div>
  );
}

export function CountSheetBanner({ sheet }) {
  if (sheet.countDate === todayISO()) return null;
  const d = new Date(sheet.countDate + "T00:00:00").toLocaleDateString("en-US", { weekday: "long", month: "short", day: "numeric", year: "numeric" });
  return (
    <div className="rounded-lg border border-amber-500/40 bg-amber-500/10 text-amber-300 text-xs px-3 py-2 mb-3" data-testid="count-backdate-banner">
      Entering counts for <b>{d}</b>. If an item already has a newer count, this one is saved to Count History but won't change its on-hand amount.
    </div>
  );
}

function CountInput({ sheet, it, className = "" }) {
  const saved = sheet.isSaved(it);
  return (
    <input type="text" inputMode="decimal" autoComplete="off" placeholder="Count"
      data-testid={`count-input-${it.controlNumber}`} data-saved={saved ? "true" : "false"}
      className={`${inpCls} ${className}`} style={saved ? SAVED : UNSAVED}
      value={sheet.valueOf(it)} onChange={(e) => sheet.setValue(it.controlNumber, e.target.value)} />
  );
}

// showPar: the manager view shows par; the staff view shows who counted last.
export function CountSheetList({ sheet, onSaveOne, showPar }) {
  if (sheet.rows.length === 0) return <div className="text-slate-500 text-sm py-10 text-center" data-testid="count-area-empty">No items in this storage area.</div>;
  return (
    <div className="flex flex-col gap-2" data-testid="count-sheet-list">
      {sheet.rows.map((it, i) => {
        const areaName = it.storageArea || "Unassigned";
        const newArea = !sheet.area && (i === 0 || (sheet.rows[i - 1].storageArea || "Unassigned") !== areaName);
        return (
          <React.Fragment key={it.controlNumber}>
            {newArea && <div className="text-[11px] uppercase tracking-[0.08em] text-slate-500 font-bold mt-2 first:mt-0">{areaName}</div>}
            <div className={`${cardCls} p-3 flex items-center gap-3 flex-wrap sm:flex-nowrap`} data-testid={`count-row-${it.controlNumber}`}>
              <div className="flex-1 min-w-[160px]">
                <div className="text-xs font-bold" style={{ color: "var(--acc)" }}>{it.controlNumber}</div>
                <div className="font-semibold text-slate-100 text-sm leading-snug break-words">{it.name}</div>
                <div className="text-xs text-slate-500">
                  {showPar ? `Par ${num(it.par)} ${it.unit || ""}` : it.lastCountedBy ? `Last by ${it.lastCountedBy}` : ""}
                </div>
              </div>
              <div className="flex items-center gap-1.5" onKeyDown={(e) => { if (e.key === "Enter") onSaveOne(it); }}>
                <CountInput sheet={sheet} it={it} className="w-28 text-center" />
                <span className="text-xs text-slate-500 w-14">{it.unit}</span>
              </div>
              <button className={btnGhost} data-testid={`count-save-${it.controlNumber}`} disabled={sheet.busy} onClick={() => onSaveOne(it)}>Save</button>
            </div>
          </React.Fragment>
        );
      })}
    </div>
  );
}

export function SaveAllCountsButton({ sheet, onClick, testId }) {
  const n = sheet.pending.length;
  return (
    <button data-testid={testId} className={btnAcc} onClick={onClick} disabled={sheet.busy || n === 0}>
      <Save size={15} /> {sheet.busy ? "Saving…" : n ? `Save ${n} Count${n === 1 ? "" : "s"}` : "Save All Counts"}
    </button>
  );
}
