import React, { useEffect, useRef, useState } from "react";
import * as api from "../lib/api";
import { Field, cardCls, inpCls, btnAcc, btnGhost } from "./common";
import { RESTAURANTS, todayISO } from "../lib/calc";

// M3 Bulk supply (Jeff 2026-10-29): Bert's Bulk is made at Rudd's from Bert's own goods.
// Bert's sends its Bulk count as a request (par minus on hand); Rudd's makes it in the Monday
// or Thursday run and signs off the amounts and packaging, sent and held at Rudd's for Bert's;
// Bert's manager accepts what arrived. One par per item, met wherever the owner's stock is held.
// Anything short stays open until a spot prep or the next run. Amounts are in each item's base unit.

const detail = e => { const d = e?.response?.data?.detail; return typeof d === "string" ? d : Array.isArray(d) ? d.map(x => x.msg).join("; ") : e.message || "Request failed"; };
const decimal = v => /^\d+(?:\.\d+)?$/.test(String(v).trim());
// Store ids from the server ("rudds") shown as names ("Rudd's"); the server calls Papa Leoni's "papa".
export const storeName = id => RESTAURANTS.find(r => r.id === id || (id === "papa" && r.id === "papa_leonis"))?.short || id;
const DAYS = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"];
const amount = (v, unit) => v == null ? "—" : `${Number(v)} ${unit}`;
const STATUS = { requested: "Waiting for the Bulk kitchen", sent: "Sent; waiting for acceptance", accepted: "Accepted", cancelled: "Cancelled" };

// Next Monday or Thursday (Sunday night count -> Monday run, Wednesday night -> Thursday).
export function nextRunDate(today = todayISO()) {
  const d = new Date(`${today}T12:00:00Z`);
  for (let i = 0; i < 7; i++) { if ([1, 4].includes(d.getUTCDay())) return d.toISOString().slice(0, 10); d.setUTCDate(d.getUTCDate() + 1); }
  return today;
}

function useSubmit(onDone) {
  const attempt = useRef(null), [busy, setBusy] = useState(false), [error, setError] = useState("");
  // The exact body is kept with its key, so a retry after a lost response replays the same request.
  async function submit(make, send) {
    setBusy(true); setError("");
    try {
      if (!attempt.current) attempt.current = { key: crypto.randomUUID(), body: await make() };
      const r = await send(attempt.current.body, attempt.current.key); if (!r?.request?.id) throw new Error("Not confirmed. Retry the same save."); attempt.current = null; onDone(r); }
    catch (e) { if ([400, 403, 404, 409, 422].includes(e?.response?.status)) attempt.current = null; setError(detail(e)); }
    finally { setBusy(false); }
  }
  const label = (retry, ready) => busy ? "Saving…" : attempt.current ? retry : ready;
  return { submit, busy, error, setError, label, pending: () => !!attempt.current, reset: () => { attempt.current = null; } };
}

export function RequestForm({ rid, maker, onSent }) {
  const [runDate, setRunDate] = useState(() => nextRunDate()), [group, setGroup] = useState("weekday"), [note, setNote] = useState("");
  const [counts, setCounts] = useState(null), [review, setReview] = useState(null), [checked, setChecked] = useState(false);
  const s = useSubmit(r => { setReview(null); setChecked(false); onSent(r); });
  useEffect(() => {
    let active = true; setCounts(null); setReview(null);
    api.prepDayDraft(rid, runDate, "bulk").then(d => active && setCounts(d.counts || [])).catch(e => active && s.setError(detail(e)));
    return () => { active = false; };
  }, [rid, runDate]); // eslint-disable-line react-hooks/exhaustive-deps
  const latest = counts?.find(c => c.latest);
  const body = () => ({ run_date: runDate, kind: "scheduled", day_group: group, count_event_id: latest.id, note: note.trim() });
  async function preview() {
    s.setError(""); s.reset();
    if (!note.trim()) { s.setError("Add a short note (who counted)."); return; }
    try { const b = body(); setReview({ body: b, result: await api.previewBulkRequest(rid, b) }); setChecked(false); }
    catch (e) { s.setError(detail(e)); }
  }
  const lines = review?.result?.review?.lines || [];
  return <section className={`${cardCls} p-4 space-y-3`} aria-label="Send Bulk request">
    <h3 className="font-semibold">Send Bulk count to {storeName(maker)}</h3>
    <p className="text-sm text-slate-400">Uses last night's prep count. Each item's request is its Bulk par minus what you counted. One par covers your Bulk wherever it is kept, so your count includes your Bulk held at {storeName(maker)} (the "Held at {storeName(maker)}" zone). Sunday night count is for Monday's run; Wednesday night count is for Thursday's.</p>
    <div className="grid md:grid-cols-3 gap-3">
      <Field label="Bulk run date"><input aria-label="Bulk run date" type="date" className={inpCls} value={runDate} onChange={e => setRunDate(e.target.value)} /></Field>
      <Field label={`Par group (${DAYS[new Date(`${runDate}T12:00:00Z`).getUTCDay()] || "run"} run)`}><select aria-label="Bulk par group" className={inpCls} value={group} onChange={e => { setGroup(e.target.value); setReview(null); }}><option value="weekday">Weekday pars</option><option value="weekend">Weekend pars</option></select></Field>
      <Field label="Note"><input aria-label="Bulk request note" className={inpCls} value={note} onChange={e => { setNote(e.target.value); setReview(null); }} placeholder="e.g. Sunday close, J. Smith" /></Field>
    </div>
    {counts && !latest && <p role="alert">No prep count from the night before {runDate}. Count Bulk items first.</p>}
    {s.error && <p role="alert">{s.error}</p>}
    {review ? <>
      <div className="overflow-auto"><table className="ops-table"><thead><tr><th>Item</th><th>Par</th><th>Counted</th><th>Request</th></tr></thead>
        <tbody>{lines.map(l => <tr key={l.ordinal}><td>{l.name}</td><td>{l.target_par} {l.source_unit}</td><td>{amount(l.counted_base_quantity, l.base_unit)}</td><td><strong>{amount(l.requested_base_quantity, l.base_unit)}</strong></td></tr>)}</tbody></table></div>
      <label><input type="checkbox" aria-label="Review Bulk request" checked={checked} onChange={e => setChecked(e.target.checked)} /> I checked the items and amounts.</label>
      <button className={btnAcc} disabled={s.busy || !checked} onClick={() => s.submit(() => ({ request: review.body, expected_review_hash: review.result.reviewHash, reviewed: true }), (b, k) => api.sendBulkRequest(rid, b, k))}>{s.label("Retry the same request", "Send request")}</button>
    </> : <button className={btnAcc} disabled={!latest} onClick={preview}>Preview request</button>}
  </section>;
}

export function SpotForm({ rid, items, onSent }) {
  const [rows, setRows] = useState([{ product_id: "", quantity: "", reason: "" }]), [note, setNote] = useState(""), [runDate, setRunDate] = useState(todayISO());
  const s = useSubmit(r => { setRows([{ product_id: "", quantity: "", reason: "" }]); setNote(""); onSent(r); });
  const edit = (i, patch) => { s.reset(); setRows(x => x.map((r, n) => n === i ? { ...r, ...patch } : r)); };
  const ready = note.trim() && rows.every(r => r.product_id && decimal(r.quantity) && Number(r.quantity) > 0 && r.reason.trim());
  async function send() {
    const request = { run_date: runDate, kind: "spot", note: note.trim(), lines: rows.map(r => ({ product_id: r.product_id, quantity: r.quantity.trim(), reason: r.reason.trim() })) };
    await s.submit(async () => ({ request, expected_review_hash: (await api.previewBulkRequest(rid, request)).reviewHash, reviewed: true }), (b, k) => api.sendBulkRequest(rid, b, k));
  }
  return <section className={`${cardCls} p-4 space-y-3`} aria-label="Spot Bulk request">
    <h3 className="font-semibold">Spot prep request</h3>
    <p className="text-sm text-slate-400">For a shortfall or an unexpected need between runs. Amounts are in each item's par unit.</p>
    <Field label="Needed by"><input aria-label="Spot needed by" type="date" className={inpCls} value={runDate} onChange={e => setRunDate(e.target.value)} /></Field>
    {rows.map((r, i) => <div key={i} className="grid md:grid-cols-3 gap-3">
      <Field label="Item"><select aria-label={`Spot item ${i + 1}`} className={inpCls} value={r.product_id} onChange={e => edit(i, { product_id: e.target.value })}><option value="">Choose…</option>{items.map(p => <option key={p.product_id} value={p.product_id}>{p.name} ({p.unit})</option>)}</select></Field>
      <Field label="Amount"><input aria-label={`Spot amount ${i + 1}`} inputMode="decimal" className={inpCls} value={r.quantity} onChange={e => edit(i, { quantity: e.target.value })} /></Field>
      <Field label="Why"><input aria-label={`Spot reason ${i + 1}`} className={inpCls} value={r.reason} onChange={e => edit(i, { reason: e.target.value })} /></Field>
    </div>)}
    <div className="flex gap-2"><button className={btnGhost} onClick={() => setRows(x => [...x, { product_id: "", quantity: "", reason: "" }])}>Add item</button></div>
    <Field label="Note"><input aria-label="Spot note" className={inpCls} value={note} onChange={e => setNote(e.target.value)} /></Field>
    {s.error && <p role="alert">{s.error}</p>}
    <button className={btnAcc} disabled={s.busy || !ready} onClick={send}>{s.label("Retry the same request", "Send spot request")}</button>
  </section>;
}

export function StepForm({ rid, request, action, onDone }) {
  const sent = action === "accept";
  const [rows, setRows] = useState(() => request.lines.map(l => ({ ordinal: l.ordinal, base_quantity: String(Number(sent ? l.sent_base_quantity : l.requested_base_quantity)), held: "0", packaging: "" })));
  const [handoff, setHandoff] = useState("delivery"), [note, setNote] = useState("");
  const s = useSubmit(onDone);
  const edit = (i, patch) => { s.reset(); setRows(x => x.map((r, n) => n === i ? { ...r, ...patch } : r)); };
  const ready = note.trim() && rows.every(r => decimal(r.base_quantity) && (sent || (decimal(r.held) && (Number(r.base_quantity) + Number(r.held) === 0 || r.packaging.trim()))));
  const body = () => ({ action, note: note.trim(), ...(sent ? {} : { handoff }),
    lines: rows.map(r => ({ ordinal: r.ordinal, base_quantity: r.base_quantity.trim(), ...(sent ? {} : { held_base_quantity: r.held.trim(), ...(r.packaging.trim() ? { packaging: r.packaging.trim() } : {}) }) })) });
  const maker = storeName(request.maker_store_id), owner = storeName(request.store_id);
  return <div className="space-y-2" aria-label={sent ? "Accept Bulk delivery" : "Sign off Bulk made"}>
    <p className="text-sm">{sent ? "Enter what actually arrived. What is held at the Bulk kitchen still counts toward your par; anything less than requested stays open as a shortfall."
      : `Enter what you made for ${owner}: what you are sending, what stays here held for ${owner} (still ${owner}'s stock, counted in ${owner}'s count), and the packaging (e.g. 3 × 4 qt deli). Enter 0 for anything not made.`}</p>
    {request.lines.map((l, i) => <div key={l.ordinal} className="grid md:grid-cols-4 gap-3 items-end">
      <Field label={`${l.name} (${l.base_unit})`}><input aria-label={`${sent ? "Accepted" : "Sent"} ${l.name}`} inputMode="decimal" className={inpCls} value={rows[i].base_quantity} onChange={e => edit(i, { base_quantity: e.target.value })} /></Field>
      {sent ? <p className="text-sm">Sent {amount(l.sent_base_quantity, l.base_unit)} · held at {maker} {amount(l.held_base_quantity, l.base_unit)} · {l.packaging || "no packaging"}</p>
        : <><Field label={`Held at ${maker}`}><input aria-label={`Held ${l.name}`} inputMode="decimal" className={inpCls} value={rows[i].held} onChange={e => edit(i, { held: e.target.value })} /></Field>
          <Field label="Packaging"><input aria-label={`Packaging ${l.name}`} className={inpCls} value={rows[i].packaging} onChange={e => edit(i, { packaging: e.target.value })} /></Field></>}
    </div>)}
    {!sent && <Field label="Handoff"><select aria-label="Bulk handoff" className={inpCls} value={handoff} onChange={e => { s.reset(); setHandoff(e.target.value); }}><option value="delivery">Delivered</option><option value="pickup">Ready for pickup</option></select></Field>}
    <Field label="Sign-off note"><input aria-label="Bulk sign-off note" className={inpCls} value={note} onChange={e => { s.reset(); setNote(e.target.value); }} placeholder="Your name" /></Field>
    {s.error && <p role="alert">{s.error}</p>}
    <button className={btnAcc} disabled={s.busy || !ready} onClick={() => s.submit(body, (b, k) => api.signBulkStep(rid, request.id, b, k))}>{s.label("Retry the same sign-off", sent ? "Accept delivery" : "Sign off made")}</button>
  </div>;
}

function CancelButton({ rid, request, onDone }) {
  const s = useSubmit(onDone);
  return <>{s.error && <p role="alert">{s.error}</p>}<button className={btnGhost} disabled={s.busy} onClick={() => s.submit(() => ({ action: "cancel", note: "Cancelled by requesting manager" }), (b, k) => api.signBulkStep(rid, request.id, b, k))}>Cancel request</button></>;
}

export function RequestCard({ rid, store, request, onChange }) {
  const [open, setOpen] = useState(false);
  const making = request.maker_store_id === store, asking = request.store_id === store;
  const can = making && request.status === "requested" ? "fulfill" : asking && request.status === "sent" ? "accept" : null;
  return <div className="border border-slate-700 rounded-lg p-3 space-y-2" data-testid="bulk-request">
    <p><strong>{request.kind === "spot" ? "Spot" : "Bulk run"} {request.run_date}</strong> · {making ? `for ${storeName(request.store_id)}` : `from ${storeName(request.maker_store_id)}`} · {STATUS[request.status]}{request.events.find(e => e.action === "fulfill") ? ` · ${request.events.find(e => e.action === "fulfill").handoff === "pickup" ? "pickup" : "delivery"}` : ""}</p>
    <div className="overflow-auto"><table className="ops-table"><thead><tr><th>Item</th><th>Requested</th><th>Sent</th><th>Held at {storeName(request.maker_store_id)}</th><th>Packaging</th><th>Accepted</th><th>Short</th></tr></thead>
      <tbody>{request.lines.map(l => <tr key={l.ordinal}><td>{l.name}</td><td>{amount(l.requested_base_quantity, l.base_unit)}</td><td>{amount(l.sent_base_quantity, l.base_unit)}</td><td>{amount(l.held_base_quantity, l.base_unit)}</td><td>{l.packaging || "—"}</td><td>{amount(l.accepted_base_quantity, l.base_unit)}</td><td>{l.shortfall_base_quantity != null && Number(l.shortfall_base_quantity) > 0 ? <strong>{amount(l.shortfall_base_quantity, l.base_unit)}</strong> : "—"}</td></tr>)}</tbody></table></div>
    {can && (open ? <StepForm rid={rid} request={request} action={can} onDone={() => { setOpen(false); onChange(); }} /> : <button className={btnAcc} onClick={() => setOpen(true)}>{can === "fulfill" ? "Sign off what was made" : "Accept delivery"}</button>)}
    {asking && request.status === "requested" && <CancelButton rid={rid} request={request} onDone={onChange} />}
  </div>;
}

export function BulkSupply({ rid }) {
  const [data, setData] = useState(null), [items, setItems] = useState([]), [error, setError] = useState(""), [epoch, setEpoch] = useState(0), [form, setForm] = useState(null);
  const since = (() => { const d = new Date(`${todayISO()}T12:00:00Z`); d.setUTCDate(d.getUTCDate() - 28); return d.toISOString().slice(0, 10); })();
  useEffect(() => {
    let active = true; setError("");
    api.bulkSupply(rid, since).then(d => active && setData(d)).catch(e => active && setError(detail(e)));
    return () => { active = false; };
  }, [rid, epoch]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    if (form !== "spot") return undefined;
    let active = true;
    api.prepPlanning(rid).then(p => {
      if (!active) return;
      const names = Object.fromEntries((p.products || []).map(v => [v.product_id, v.name])), units = Object.fromEntries((p.unitProfiles || []).map(u => [u.id, u.source_unit]));
      setItems((p.plans || []).filter(x => x.active && x.track === "bulk").map(x => ({ product_id: x.product_id, name: names[x.product_id] || x.product_id, unit: units[x.unit_profile_id] || "" })));
    }).catch(() => {});
    return () => { active = false; };
  }, [rid, form]);
  if (error) return <p role="alert">{error}</p>;
  if (!data) return <p>Loading Bulk supply…</p>;
  const store = data.store_id, reload = () => { setForm(null); setEpoch(n => n + 1); };
  if (!data.maker_store_id && !data.makes_for.length) return null;
  return <div className="space-y-4 mb-6" data-testid="bulk-supply">
    {data.maker_store_id && <div className="flex gap-2">
      <button className={form === "request" ? btnAcc : btnGhost} onClick={() => setForm(form === "request" ? null : "request")}>Send Bulk count</button>
      <button className={form === "spot" ? btnAcc : btnGhost} onClick={() => setForm(form === "spot" ? null : "spot")}>Spot request</button>
    </div>}
    {data.makes_for.length > 0 && <p className="text-sm text-slate-400">Bulk held here for {data.makes_for.map(storeName).join(", ")} is their stock and counts toward their par: count only your own Bulk in your count.</p>}
    {form === "request" && <RequestForm rid={rid} maker={data.maker_store_id} onSent={reload} />}
    {form === "spot" && <SpotForm rid={rid} items={items} onSent={reload} />}
    {!!data.open_shortfalls.length && <section className={`${cardCls} p-4`} aria-label="Open Bulk shortfalls">
      <h3 className="font-semibold">Still owed</h3>
      <ul>{data.open_shortfalls.map(s => <li key={`${s.request_id}:${s.product_id}`}>{s.name}: {amount(s.shortfall_base_quantity, s.base_unit)} short from {s.run_date}{s.store_id !== store ? ` (${storeName(s.store_id)})` : ""}</li>)}</ul>
    </section>}
    <section className={`${cardCls} p-4 space-y-3`} aria-label="Bulk requests">
      <h3 className="font-semibold">{data.makes_for.length ? `Bulk requests from ${data.makes_for.map(storeName).join(", ")}` : "Your Bulk requests"}</h3>
      {!data.requests.length && <p className="text-sm">No requests in the last four weeks.</p>}
      {data.requests.map(r => <RequestCard key={r.id} rid={rid} store={store} request={r} onChange={reload} />)}
    </section>
  </div>;
}
