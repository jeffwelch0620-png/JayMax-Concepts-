import React, { useRef, useState } from "react";
import * as api from "../lib/api";
import { inpCls, btnGhost } from "./common";

export const SHORTAGE_REASONS = [
  { id: "out_of_ingredient", label: "Out of an ingredient" },
  { id: "ran_out_of_time", label: "Ran out of time" },
  { id: "equipment", label: "Equipment problem" },
  { id: "other", label: "Other" },
];
const detail = (e, fallback) => (typeof e?.response?.data?.detail === "string" ? e.response.data.detail : fallback);

// A shortage note to the Shift Leader (Jeff 2026-11-01): how much short (optional), why, and a
// note. It changes no counts, pars or production.
export function ShortageReport({ rid, day, track, task, staffId }) {
  const [open, setOpen] = useState(false), [form, setForm] = useState({ short_quantity: "", reason: "", note: "" });
  const [busy, setBusy] = useState(false), [err, setErr] = useState(""), [sent, setSent] = useState(false);
  const attempt = useRef(null);   // a retry after a lost reply reuses its key; an edit is a new report
  const set = (k, v) => { setForm(f => ({ ...f, [k]: v })); attempt.current = null; };

  async function send() {
    if (busy) return;
    if (!form.reason) { setErr("Choose why you're short"); return; }
    if (!form.note.trim()) { setErr("Add a short note for the Shift Leader"); return; }
    if (form.short_quantity !== "" && !(Number(form.short_quantity) > 0)) { setErr("How much short must be more than 0, or leave it blank"); return; }
    const body = { day, track, task_id: task.id, staff_member_id: staffId, reason: form.reason, note: form.note.trim(),
      ...(form.short_quantity !== "" ? { short_quantity: form.short_quantity } : {}) };
    if (!attempt.current) attempt.current = crypto.randomUUID();
    setBusy(true); setErr("");
    try {
      await api.reportShortage(rid, body, attempt.current);
      attempt.current = null; setSent(true); setOpen(false); setForm({ short_quantity: "", reason: "", note: "" });
    } catch (e) {
      if ([403, 409, 422].includes(e?.response?.status)) attempt.current = null;
      setErr(detail(e, "Your report wasn't sent. Try again."));
    } finally { setBusy(false); }
  }

  if (!open) return (
    <span className="inline-flex items-center gap-2">
      <button className={btnGhost} onClick={() => { setOpen(true); setSent(false); setErr(""); }} data-testid={`shortage-open-${task.id}`}>Report shortage</button>
      {sent && <span className="text-xs text-green-400" role="status">Sent to the Shift Leader</span>}
    </span>
  );
  return (
    <div className="flex flex-col gap-2 mt-2" aria-label={`Shortage for ${task.name}`} data-testid={`shortage-form-${task.id}`}>
      <select className={inpCls} aria-label="Why are you short?" value={form.reason} disabled={busy} onChange={e => set("reason", e.target.value)}>
        <option value="">Why are you short?</option>
        {SHORTAGE_REASONS.map(r => <option key={r.id} value={r.id}>{r.label}</option>)}
      </select>
      <input className={inpCls} inputMode="decimal" aria-label={`How much short (${task.source_unit}, optional)`} placeholder={`How much short (${task.source_unit}, optional)`}
        value={form.short_quantity} disabled={busy} onChange={e => set("short_quantity", e.target.value.replace(/[^0-9.]/g, ""))} />
      <input className={inpCls} aria-label="Note for the Shift Leader" placeholder="Note for the Shift Leader" maxLength={1000}
        value={form.note} disabled={busy} onChange={e => set("note", e.target.value)} />
      <span className="flex gap-2">
        <button className={btnGhost} disabled={busy} onClick={send} data-testid={`shortage-send-${task.id}`}>{busy ? "Sending…" : "Send to Shift Leader"}</button>
        <button className={btnGhost} disabled={busy} onClick={() => { setOpen(false); setErr(""); }}>Cancel</button>
      </span>
      {err && <p className="text-red-400 text-xs" role="alert">{err}</p>}
    </div>
  );
}
