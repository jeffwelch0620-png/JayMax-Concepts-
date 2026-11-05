import React, { useEffect, useRef, useState } from "react";
import * as api from "../lib/api";
import { Field, cardCls, inpCls, btnAcc, btnGhost } from "./common";
import { todayISO } from "../lib/calc";
import { plain } from "./PrepPlanning";

// M2 Bulk daily pars, phase B (Jeff 2026-11-05): a quick nightly count of Bulk items only. In daily par
// mode the server compares it with the daily pars for the days left before the next Monday or Thursday
// run, less spot requests already on their way, and shows any spot prep needed. It only suggests: a
// requesting store sends its own spot request; the Bulk kitchen makes its own spot prep. It does not
// replace the Sunday and Wednesday night counts that drive the runs.

const DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
const detail = e => { const d = e?.response?.data?.detail; return typeof d === "string" ? d : Array.isArray(d) ? d.map(x => x.msg).join("; ") : e.message || "Request failed"; };
const decimal = v => /^\d+(?:\.\d+)?$/.test(String(v).trim());
const amount = (v, unit) => v == null ? "—" : `${plain(v)} ${unit}`;
const weekday = iso => DAYS[(new Date(`${iso}T12:00:00Z`).getUTCDay() + 6) % 7];
const nextDay = iso => { const d = new Date(`${iso}T12:00:00Z`); d.setUTCDate(d.getUTCDate() + 1); return d.toISOString().slice(0, 10); };
// Before 6 a.m. a count is still for last night.
export function countNight(now = new Date()) {
  if (now.getHours() >= 6) return todayISO();
  const d = new Date(`${todayISO()}T12:00:00Z`); d.setUTCDate(d.getUTCDate() - 1); return d.toISOString().slice(0, 10);
}

// onPending: told while a save is unresolved, so the Bulk panel keeps this form (and its retry key) open.
export function BulkQuickCount({ rid, onSpot, onPending = () => {} }) {
  const [night, setNight] = useState(() => countNight()), [data, setData] = useState(null), [error, setError] = useState("");
  const [quantities, setQuantities] = useState({}), [note, setNote] = useState(""), [busy, setBusy] = useState(false);
  // The exact body is kept with its key, so a retry after a lost response replays the same count.
  const attempt = useRef(null), [pending, setPending] = useState(false);
  const unresolved = busy || pending;
  useEffect(() => { onPending(unresolved); }, [unresolved]); // eslint-disable-line react-hooks/exhaustive-deps
  function show(d) {
    setData(d);
    const latest = d.counts?.[d.counts.length - 1];
    setQuantities(Object.fromEntries(d.items.map(i => { const l = latest?.lines?.find(x => x.product_id === i.product_id); return [i.product_id, l ? plain(l.quantity) : ""]; })));
  }
  useEffect(() => {
    let active = true; setData(null); setError("");
    api.bulkQuickCount(rid, night).then(d => active && show(d)).catch(e => active && setError(detail(e)));
    return () => { active = false; };
  }, [rid, night]);
  const ready = data && data.items.length && note.trim() && note.trim().length <= 2000 && data.items.every(i => decimal(quantities[i.product_id] ?? ""));
  async function save() {
    setBusy(true); setError("");
    try {
      if (!attempt.current) attempt.current = { key: crypto.randomUUID(), version: data.revision, body: { business_date: night, performed_at: new Date().toISOString(), note: note.trim(),
        lines: data.items.map(i => ({ product_id: i.product_id, quantity: quantities[i.product_id].trim() })) } };
      setPending(true);
      const r = await api.saveBulkQuickCount(rid, attempt.current.body, attempt.current.version, attempt.current.key);
      if (r?.request_key !== attempt.current.key || r.business_date !== attempt.current.body.business_date || (!r.replayed && r.revision !== attempt.current.version + 1)) throw new Error("Not confirmed. Retry the same count.");
      attempt.current = null; setPending(false); setNote(""); show(r);
    } catch (e) {
      if ([400, 403, 404, 409, 422, 428].includes(e?.response?.status)) { attempt.current = null; setPending(false); }
      setError(detail(e));
      // Someone else saved this night's count first: reload it (keeping what was typed) so a correction uses its version.
      if (e?.response?.status === 409) { try { setData(await api.bulkQuickCount(rid, night)); } catch { /* the refusal stays shown */ } }
    }
    finally { setBusy(false); }
  }
  const short = (data?.check || []).filter(c => Number(c.short_base_quantity) > 0);
  // Items added to Bulk after this count: a missing count is not zero, so the check is incomplete.
  const uncounted = (data?.check || []).filter(c => c.counted === false);
  const requests = data?.maker_store_id;
  return <section className={`${cardCls} p-4 space-y-3`} aria-label="Quick Bulk count">
    <h3 className="font-semibold">Quick Bulk count</h3>
    <p className="text-sm text-slate-400">Count only your Bulk items tonight{requests ? ", including your Bulk held at the Bulk kitchen" : ""}. With daily pars, this shows whether a spot prep is needed before the next run. It does not replace the Sunday and Wednesday night counts for the runs.</p>
    <Field label="Night counted"><input aria-label="Quick count night" type="date" className={inpCls} value={night} disabled={busy || pending} onChange={e => setNight(e.target.value)} /></Field>
    {error && <p role="alert">{error}</p>}
    {!data ? !error && <p>Loading Bulk items…</p> : <>
      {!data.items.length && <p>No active to-par Bulk items to count here.</p>}
      <fieldset disabled={busy || pending} className="space-y-3">
        <div className="grid md:grid-cols-3 gap-3">{data.items.map(i => <Field key={i.product_id} label={`${i.name} (${i.source_unit})`}>
          <input aria-label={`Quick count ${i.name}`} inputMode="decimal" className={inpCls} value={quantities[i.product_id] ?? ""} onChange={e => setQuantities(q => ({ ...q, [i.product_id]: e.target.value }))} /></Field>)}</div>
        <Field label="Note"><input aria-label="Quick count note" className={inpCls} value={note} onChange={e => setNote(e.target.value)} placeholder="Who counted" /></Field>
      </fieldset>
      {!!data.items.length && <button className={btnAcc} disabled={busy || !ready && !pending} onClick={save}>{busy ? "Saving…" : pending ? "Retry the same count" : data.revision ? "Save corrected count" : "Save count"}</button>}
      {!!data.revision && <p className="text-sm">Saved count version {data.revision} for the night of {weekday(night)} {night}.</p>}
      {data.revision > 0 && data.par_mode !== "daily" && <p className="text-sm">The spot-prep check uses daily pars. This store uses weekday / weekend pars, so the count is kept without a check.</p>}
      {data.check && <div aria-label="Spot prep check">
        <p className="text-sm">{data.days_before_next_run.length ? `Days left before the ${weekday(data.next_run)} ${data.next_run} run: ${data.days_before_next_run.map(d => DAYS[d]).join(", ")}.` : `The ${weekday(data.next_run)} ${data.next_run} run covers tomorrow, so no spot prep is needed.`}</p>
        <div className="overflow-auto"><table className="ops-table"><thead><tr><th>Item</th><th>Needed until the run</th><th>Counted</th><th>Spot requests on the way</th><th>Short</th></tr></thead>
          <tbody>{data.check.map(c => <tr key={c.product_id}><td>{c.name}</td><td>{amount(c.need_base_quantity, c.base_unit)}</td><td>{c.counted === false ? <strong>Not counted</strong> : amount(c.counted_base_quantity, c.base_unit)}</td><td>{amount(c.incoming_base_quantity, c.base_unit)}</td>
            <td>{Number(c.short_base_quantity) > 0 ? <strong>{amount(c.short_base_quantity, c.base_unit)}</strong> : "—"}</td></tr>)}</tbody></table></div>
        {!!uncounted.length && <p role="alert">Not in this count: {uncounted.map(c => c.name).join(", ")}. Save a corrected count with every item before relying on this check.</p>}
        {!short.length ? !uncounted.length && <p>No spot prep needed before the next run.</p> : requests
          ? <button className={btnGhost} onClick={() => onSpot(short.map(c => ({ product_id: c.product_id, quantity: plain(c.spot_quantity), reason: `Quick count ${night}: short before the ${data.next_run} run` })), nextDay(night))}>Fill in a spot request for review</button>
          : <p><strong>Spot prep needed before the {weekday(data.next_run)} run:</strong> {short.map(c => `${c.name} ${plain(c.spot_quantity)} ${c.source_unit}`).join(", ")}.</p>}
      </div>}
    </>}
  </section>;
}
