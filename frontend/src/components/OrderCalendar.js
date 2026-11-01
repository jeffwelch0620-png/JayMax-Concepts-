import React, { useEffect, useRef, useState } from "react";
import { CalendarClock } from "lucide-react";
import * as api from "../lib/api";
import { canonicalStoreId } from "../lib/purchaseContract";
import { cardCls, inpCls, btnAcc, btnGhost } from "./common";

// Order calendar (M4, Jeff 2026-11-01): the next order cycle, what is due or overdue, and what is
// still on order. A reminder only: nothing here blocks a count or an order. A late count asks for a
// short reason; a late order asks for it when submitted (Purchase Orders note).
const WORD = { due: "Due", overdue: "Overdue", done: "Done", late: "Done late", upcoming: "Upcoming" };
const TONE = { due: "text-amber-300", overdue: "text-red-400", done: "text-emerald-400", late: "text-amber-300", upcoming: "text-slate-400" };
const dayName = d => new Date(`${d}T12:00:00Z`).toLocaleDateString("en-US", { weekday: "long", month: "short", day: "numeric", timeZone: "UTC" });
const detail = (e, fallback) => (typeof e?.response?.data?.detail === "string" ? e.response.data.detail : fallback);

export function OrderCalendar({ rid }) {
  const [view, setView] = useState(null), [error, setError] = useState(""), [reason, setReason] = useState(""), [busy, setBusy] = useState(false);
  const reads = useRef(0), attempt = useRef(null);

  async function load() {
    const n = ++reads.current;
    try {
      const v = await api.orderCalendar(rid);
      if (n !== reads.current) return;
      if (v?.store_id !== canonicalStoreId(rid)) throw new Error("Order calendar was not confirmed for this location.");
      setView(v); setError("");
    } catch (e) { if (n === reads.current) { setView(null); setError(detail(e, "Couldn't load the order calendar")); } }
  }
  useEffect(() => { load(); return () => { reads.current += 1; }; }, [rid]); // eslint-disable-line react-hooks/exhaustive-deps

  async function saveReason() {
    const cal = view?.calendar, text = reason.trim();
    if (!cal || !text || busy) return;
    // A retry after a lost reply reuses its key; different words are a new note.
    if (!attempt.current || attempt.current.text !== text) attempt.current = { key: crypto.randomUUID(), text };
    setBusy(true); setError("");
    try { await api.recordLateCount(rid, { cycle_date: cal.cycle_date, reason: text }, attempt.current.key); attempt.current = null; setReason(""); await load(); }
    catch (e) { if ([409, 422].includes(e?.response?.status)) attempt.current = null; setError(detail(e, "The reason wasn't saved. Try again.")); }
    finally { setBusy(false); }
  }

  if (error && !view) return <p className="text-red-400 text-xs" role="alert">{error}</p>;
  if (!view || !view.installed) return null;
  const cal = view.calendar;
  return (
    <section className={`${cardCls} p-4`} aria-label="Order calendar" data-testid="order-calendar">
      {cal ? <>
        <div className="flex items-center gap-2 mb-2"><CalendarClock size={16} className="text-slate-400" />
          <span className="font-display font-bold text-slate-100">{cal.cycle_date === cal.today ? "Today's order" : `Next order: ${dayName(cal.cycle_date)}`}</span>
          <span className="text-xs text-slate-400">count by {cal.count_due_label}, orders by {cal.order_due_label} · delivery {dayName(cal.delivery_date)}</span></div>
        <ul className="text-sm space-y-1" data-testid="order-calendar-steps">
          <li>Count: <span className={TONE[cal.count.status]}>{WORD[cal.count.status]}</span></li>
          {cal.vendors.map(v => <li key={v.vendor_id}>{v.name} order: <span className={TONE[v.status]}>{WORD[v.status]}</span>
            {v.drafts > 0 && !["done", "late"].includes(v.status) ? <span className="text-xs text-slate-400"> · {v.drafts} draft{v.drafts > 1 ? "s" : ""} not submitted</span> : null}</li>)}
        </ul>
        {cal.count.needs_reason && <div className="flex gap-2 items-center flex-wrap mt-2" data-testid="late-count">
          <input className={inpCls} aria-label="Why is the count late" placeholder="Why is the count late?" value={reason} disabled={busy} onChange={e => setReason(e.target.value)} />
          <button className={btnAcc} disabled={busy || !reason.trim()} onClick={saveReason}>{busy ? "Saving…" : "Save reason"}</button></div>}
        {cal.notes.length > 0 && <ul className="text-xs text-slate-400 mt-2">{cal.notes.map((n, i) => <li key={i}>{n.kind === "count_late" ? "Late count" : `Late ${n.vendor_id} order`}: {n.reason}</li>)}</ul>}
        {cal.vendors.some(v => v.status === "overdue") && view.can_create === false && <p className="text-xs text-slate-400 mt-2">A Kitchen Manager, FOH Manager or General Manager places the orders.</p>}
      </> : <p className="text-sm text-slate-400">No order calendar is set for this location.</p>}
      {view.on_order.length > 0 && <div className="mt-3" data-testid="on-order">
        <div className="text-xs font-bold text-slate-300 mb-1">On order, not yet received</div>
        <ul className="text-sm space-y-1">{view.on_order.map(o => <li key={o.ref}>{o.vendor_name} · {o.status}{o.expected_delivery ? ` · due ${dayName(o.expected_delivery)}` : ""}
          {o.maybe_counted && <span className="block text-xs text-amber-300">The count on {dayName(o.latest_count_date)} may already include this delivery. Confirm its receipt so it isn't counted twice.</span>}</li>)}</ul></div>}
      {error && <p className="text-red-400 text-xs mt-2" role="alert">{error}</p>}
      <button className={`${btnGhost} mt-2`} disabled={busy} onClick={load}>Refresh</button>
    </section>
  );
}
