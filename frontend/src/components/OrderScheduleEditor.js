import React, { useRef, useState } from "react";
import * as api from "../lib/api";
import { inpCls, btnAcc, btnGhost } from "./common";

// Order schedule changes (Jeff 2026-11-01): only an owner or the Ops Lead sets the weekly order days,
// and skips or moves one cycle (holidays, supplier changes). Every change needs a reason and is kept.
const DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"];   // 0 Monday ... 6 Sunday
const dayName = d => new Date(`${d}T12:00:00Z`).toLocaleDateString("en-US", { weekday: "short", month: "short", day: "numeric", timeZone: "UTC" });
const detail = (e, fallback) => (typeof e?.response?.data?.detail === "string" ? e.response.data.detail : fallback);
const blankDay = () => ({ order_weekday: "", count_due: "12:00", order_due: "15:00", delivery_weekday: "", vendor_ids: [] });

export function OrderScheduleEditor({ rid, schedule, onChanged }) {
  const [open, setOpen] = useState(false), [reason, setReason] = useState(""), [busy, setBusy] = useState(false), [error, setError] = useState("");
  const [day, setDay] = useState(blankDay()), [move, setMove] = useState({ cycle_date: "", moved_to: "", delivery_date: "" });
  const attempt = useRef(null);
  const names = Object.fromEntries((schedule.vendors || []).map(v => [v.id, v.name]));

  async function send(body) {
    const text = reason.trim();
    if (!text || busy) { if (!text) setError("Say why the schedule changes."); return; }
    const full = { ...body, reason: text }, sig = JSON.stringify(full);
    // A retry after a lost reply reuses its key; any other change is a new request.
    if (!attempt.current || attempt.current.sig !== sig) attempt.current = { key: crypto.randomUUID(), sig };
    setBusy(true); setError("");
    try {
      await api.changeOrderSchedule(rid, full, attempt.current.key);
      attempt.current = null; setReason(""); setDay(blankDay()); setMove({ cycle_date: "", moved_to: "", delivery_date: "" });
      await onChanged?.();
    } catch (e) { if ([403, 404, 409, 422].includes(e?.response?.status)) attempt.current = null; setError(detail(e, "The schedule wasn't changed. Try again.")); }
    finally { setBusy(false); }
  }
  const saveDay = () => send({ kind: "set_day", order_weekday: Number(day.order_weekday), count_due: day.count_due, order_due: day.order_due,
    delivery_weekday: Number(day.delivery_weekday), vendor_ids: day.vendor_ids });
  const dayReady = day.order_weekday !== "" && day.delivery_weekday !== "" && day.vendor_ids.length > 0 && day.count_due && day.order_due;

  if (!schedule.can_edit) return null;
  if (!open) return <button className={`${btnGhost} mt-2`} onClick={() => setOpen(true)} data-testid="schedule-open">Change the order schedule</button>;
  return (
    <div className="mt-3 border-t border-jm-line pt-3 space-y-3" data-testid="schedule-editor">
      <div className="text-xs font-bold text-slate-300">Order schedule (owners and the Ops Lead only)</div>
      <label className="block text-sm">Reason for the change<input className={`${inpCls} block w-full mt-1`} aria-label="Reason for the schedule change"
        value={reason} disabled={busy} onChange={e => setReason(e.target.value)} placeholder="e.g. Thanksgiving, supplier changed delivery day" /></label>

      <div><div className="text-sm text-slate-200 mb-1">Next cycles</div>
        <ul className="text-sm space-y-1" data-testid="schedule-upcoming">{schedule.upcoming.map(c => <li key={c.cycle_date} className="flex flex-wrap gap-2 items-center">
          <span>{dayName(c.cycle_date)}{c.change === "skip" ? " · skipped" : c.change === "move" ? ` · moved to ${dayName(c.moved_to)}, delivery ${dayName(c.delivery_date)}` : ` · delivery ${dayName(c.delivery_date)}`}
            {c.reason ? <span className="text-xs text-slate-400"> ({c.reason})</span> : null}</span>
          {c.change ? <button className={btnGhost} disabled={busy} onClick={() => send({ kind: "restore", cycle_date: c.cycle_date })}>Put back</button>
            : <><button className={btnGhost} disabled={busy} onClick={() => send({ kind: "skip", cycle_date: c.cycle_date })}>Skip</button>
                <button className={btnGhost} disabled={busy} onClick={() => setMove({ cycle_date: c.cycle_date, moved_to: "", delivery_date: c.delivery_date })}>Move…</button></>}
        </li>)}</ul>
        {move.cycle_date && <div className="flex flex-wrap gap-2 items-end mt-2" data-testid="schedule-move">
          <span className="text-sm">Move {dayName(move.cycle_date)} to</span>
          <input type="date" className={inpCls} aria-label="New order date" value={move.moved_to} onChange={e => setMove(m => ({ ...m, moved_to: e.target.value }))} />
          <span className="text-sm">delivery</span>
          <input type="date" className={inpCls} aria-label="New delivery date" value={move.delivery_date} onChange={e => setMove(m => ({ ...m, delivery_date: e.target.value }))} />
          <button className={btnAcc} disabled={busy || !move.moved_to || !move.delivery_date} onClick={() => send({ kind: "move", ...move })}>Save move</button>
          <button className={btnGhost} disabled={busy} onClick={() => setMove({ cycle_date: "", moved_to: "", delivery_date: "" })}>Cancel</button></div>}
      </div>

      <div><div className="text-sm text-slate-200 mb-1">Every week</div>
        <ul className="text-sm space-y-1" data-testid="schedule-days">{schedule.days.map(d => <li key={d.order_weekday} className="flex flex-wrap gap-2 items-center">
          <span>{DAYS[d.order_weekday]}: count by {d.count_due_label}, order by {d.order_due_label}, delivery {DAYS[d.delivery_weekday]} · {d.vendor_ids.map(v => names[v] || v).join(", ")}</span>
          <button className={btnGhost} disabled={busy} onClick={() => setDay({ order_weekday: String(d.order_weekday), count_due: d.count_due, order_due: d.order_due, delivery_weekday: String(d.delivery_weekday), vendor_ids: d.vendor_ids })}>Edit</button>
          <button className={btnGhost} disabled={busy} onClick={() => send({ kind: "remove_day", order_weekday: d.order_weekday })}>Remove</button></li>)}</ul>
        <div className="flex flex-wrap gap-2 items-end mt-2" data-testid="schedule-day-form">
          <select className={inpCls} aria-label="Order day" value={day.order_weekday} onChange={e => setDay(x => ({ ...x, order_weekday: e.target.value }))}>
            <option value="">Order day</option>{DAYS.map((n, i) => <option key={n} value={i}>{n}</option>)}</select>
          <label className="text-sm">Count by<input type="time" className={`${inpCls} ml-1`} aria-label="Count due" value={day.count_due} onChange={e => setDay(x => ({ ...x, count_due: e.target.value }))} /></label>
          <label className="text-sm">Order by<input type="time" className={`${inpCls} ml-1`} aria-label="Order due" value={day.order_due} onChange={e => setDay(x => ({ ...x, order_due: e.target.value }))} /></label>
          <select className={inpCls} aria-label="Delivery day" value={day.delivery_weekday} onChange={e => setDay(x => ({ ...x, delivery_weekday: e.target.value }))}>
            <option value="">Delivery day</option>{DAYS.map((n, i) => <option key={n} value={i}>{n}</option>)}</select>
          {(schedule.vendors || []).map(v => <label key={v.id} className="text-sm flex items-center gap-1"><input type="checkbox" aria-label={`Supplier ${v.name}`} checked={day.vendor_ids.includes(v.id)}
            onChange={e => setDay(x => ({ ...x, vendor_ids: e.target.checked ? [...x.vendor_ids, v.id] : x.vendor_ids.filter(i => i !== v.id) }))} />{v.name}</label>)}
          <button className={btnAcc} disabled={busy || !dayReady} onClick={saveDay}>Save order day</button></div>
      </div>
      {error && <p className="text-red-400 text-xs" role="alert">{error}</p>}
      <button className={btnGhost} disabled={busy} onClick={() => { setOpen(false); setError(""); }}>Close</button>
    </div>
  );
}
