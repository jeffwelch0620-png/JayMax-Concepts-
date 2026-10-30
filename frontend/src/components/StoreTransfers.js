import React, { useEffect, useRef, useState } from "react";
import * as api from "../lib/api";
import { Field, cardCls, inpCls, btnAcc, btnGhost } from "./common";
import { todayISO } from "../lib/calc";
import { storeName } from "./BulkSupply";

// M3 store transfers (Jeff 2026-10-29): a purchased item moves out of one store and into the
// other once, at the sender's latest purchase cost, on the date the receiving manager confirms
// what arrived. No purchase or sale is created; each store's food-cost period shows it as a
// transfer in or out. Anything lost on the way stays in the sender's usage. Base units.

const detail = e => { const d = e?.response?.data?.detail; return typeof d === "string" ? d : Array.isArray(d) ? d.map(x => x.msg).join("; ") : e.message || "Request failed"; };
const decimal = v => /^\d+(?:\.\d+)?$/.test(String(v).trim());
const amount = (v, unit) => v == null ? "—" : `${Number(v)} ${unit}`;
const KINDS = { lend: "Out of stock at the other store", batch_ingredient: "Used in a batch for the other store" };
const STATUS = { sent: "Sent; waiting for the receiving store", received: "Received", cancelled: "Cancelled" };

function useSubmit(onDone) {
  const attempt = useRef(null), [busy, setBusy] = useState(false), [error, setError] = useState("");
  async function submit(make, send) {
    setBusy(true); setError("");
    try {
      if (!attempt.current) attempt.current = { key: crypto.randomUUID(), body: await make() };
      const r = await send(attempt.current.body, attempt.current.key);
      if (!r?.transfer?.id) throw new Error("Not confirmed. Retry the same save.");
      attempt.current = null; onDone(r);
    } catch (e) { if ([400, 403, 404, 409, 422].includes(e?.response?.status)) attempt.current = null; setError(detail(e)); }
    finally { setBusy(false); }
  }
  const label = (retry, ready) => busy ? "Saving…" : attempt.current ? retry : ready;
  return { submit, busy, error, setError, label, pending: () => !!attempt.current, reset: () => { attempt.current = null; } };
}

export function SendTransferForm({ rid, items, stores, onSent, onPending = () => {} }) {
  const [form, setForm] = useState({ to_store_id: stores[0]?.id || "", item_code: "", sent_base_quantity: "", kind: "lend", sent_date: todayISO(), note: "" });
  const [review, setReview] = useState(null), [checked, setChecked] = useState(false), [previewing, setPreviewing] = useState(false);
  const revision = useRef(0);
  const s = useSubmit(r => { setReview(null); setChecked(false); setForm(f => ({ ...f, item_code: "", sent_base_quantity: "", note: "" })); onSent(r); });
  // While a send is unresolved (e.g. its response was lost) the inputs stay frozen, so a retry
  // replays the same request instead of creating a second transfer.
  const frozen = s.busy || s.pending() || previewing;
  // The form can't be hidden while a send is unresolved, which would drop the retry's request key.
  const unresolved = s.busy || s.pending();
  useEffect(() => { onPending(unresolved); }, [unresolved]); // eslint-disable-line react-hooks/exhaustive-deps
  const set = (k, v) => { if (frozen) return; revision.current += 1; setReview(null); setChecked(false); setForm(f => ({ ...f, [k]: v })); };
  const unit = items.find(i => i.code === form.item_code)?.base_unit || "";
  const ready = form.to_store_id && form.item_code && decimal(form.sent_base_quantity) && Number(form.sent_base_quantity) > 0 && form.note.trim();
  const body = () => ({ ...form, sent_base_quantity: form.sent_base_quantity.trim(), note: form.note.trim() });
  async function preview() {
    s.setError(""); setPreviewing(true);
    const asked = revision.current;
    try {
      const b = body(), result = await api.previewActualTransfer(rid, b);
      if (asked === revision.current) setReview({ body: b, result });  // an answer for older inputs is dropped
    } catch (e) { s.setError(detail(e)); }
    finally { setPreviewing(false); }
  }
  const r = review?.result?.review;
  return <section className={`${cardCls} p-4 space-y-3`} aria-label="Send store transfer">
    <h3 className="font-semibold">Send to another store</h3>
    <p className="text-sm text-slate-400">For a purchased item the other store is out of, or one of your items used in a batch for them. It leaves your inventory and enters theirs at your latest purchase cost once their manager confirms what arrived.</p>
    <fieldset disabled={frozen} className="grid md:grid-cols-3 gap-3">
      <Field label="To"><select aria-label="Transfer to store" className={inpCls} value={form.to_store_id} onChange={e => set("to_store_id", e.target.value)}>{stores.map(x => <option key={x.id} value={x.id}>{storeName(x.id)}</option>)}</select></Field>
      <Field label="Item"><select aria-label="Transfer item" className={inpCls} value={form.item_code} onChange={e => set("item_code", e.target.value)}><option value="">Choose…</option>{items.map(i => <option key={i.code} value={i.code}>{i.name} ({i.base_unit})</option>)}</select></Field>
      <Field label={`Amount${unit ? ` (${unit})` : ""}`}><input aria-label="Transfer amount" inputMode="decimal" className={inpCls} value={form.sent_base_quantity} onChange={e => set("sent_base_quantity", e.target.value)} /></Field>
      <Field label="Why"><select aria-label="Transfer reason" className={inpCls} value={form.kind} onChange={e => set("kind", e.target.value)}>{Object.entries(KINDS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select></Field>
      <Field label="Sent on"><input aria-label="Transfer sent date" type="date" className={inpCls} value={form.sent_date} onChange={e => set("sent_date", e.target.value)} /></Field>
      <Field label="Note"><input aria-label="Transfer note" className={inpCls} value={form.note} onChange={e => set("note", e.target.value)} placeholder="Your name and what it's for" /></Field>
    </fieldset>
    {s.error && <p role="alert">{s.error}</p>}
    {r ? <>
      <p>{amount(review.body.sent_base_quantity, r.base_unit)} of {r.name} to {storeName(r.to_store_id)}, about <strong>${r.estimated_cost_amount}</strong> at your latest purchase cost (${r.cost.cost_amount} for {amount(r.cost.base_quantity, r.base_unit)} on {r.cost.record_date}). The final amount uses what arrives.</p>
      <label><input type="checkbox" aria-label="Review store transfer" disabled={frozen} checked={checked} onChange={e => setChecked(e.target.checked)} /> I checked the item, amount and store.</label>
      <button className={btnAcc} disabled={s.busy || !checked} onClick={() => s.submit(() => ({ transfer: review.body, expected_review_hash: review.result.reviewHash, reviewed: true }), (b, k) => api.sendActualTransfer(rid, b, k))}>{s.label("Retry the same transfer", "Send transfer")}</button>
    </> : <button className={btnAcc} disabled={!ready || frozen} onClick={preview}>{previewing ? "Checking…" : "Preview transfer"}</button>}
  </section>;
}

export function TransferCard({ rid, store, transfer: t, onChange }) {
  const [open, setOpen] = useState(false), [qty, setQty] = useState(() => String(Number(t.sent_base_quantity))), [day, setDay] = useState(todayISO()), [note, setNote] = useState("");
  const s = useSubmit(() => { setOpen(false); onChange(); });
  const incoming = t.to_store_id === store, outgoing = t.from_store_id === store;
  const ready = decimal(qty) && note.trim();
  return <div className="border border-slate-700 rounded-lg p-3 space-y-2" data-testid="store-transfer">
    <p><strong>{t.name}</strong> · {amount(t.sent_base_quantity, t.base_unit)} {outgoing ? `to ${storeName(t.to_store_id)}` : `from ${storeName(t.from_store_id)}`} · sent {t.sent_date} · {STATUS[t.status]}</p>
    <p className="text-sm text-slate-400">{KINDS[t.kind]} · {t.note}{t.status === "received" ? ` · received ${amount(t.received_base_quantity, t.base_unit)} on ${t.record_date} for $${t.transfer_cost_amount}${Number(t.short_base_quantity) > 0 ? ` · ${amount(t.short_base_quantity, t.base_unit)} short (stays in the sending store's usage)` : ""}` : ""}</p>
    {s.error && <p role="alert">{s.error}</p>}
    {incoming && t.status === "sent" && (open ? <div className="grid md:grid-cols-4 gap-3 items-end">
      <Field label={`Arrived (${t.base_unit})`}><input aria-label={`Received ${t.name}`} inputMode="decimal" className={inpCls} value={qty} onChange={e => { s.reset(); setQty(e.target.value); }} /></Field>
      <Field label="Arrived on"><input aria-label="Transfer received date" type="date" className={inpCls} value={day} onChange={e => { s.reset(); setDay(e.target.value); }} /></Field>
      <Field label="Note"><input aria-label="Transfer receipt note" className={inpCls} value={note} onChange={e => { s.reset(); setNote(e.target.value); }} placeholder="Your name" /></Field>
      <button className={btnAcc} disabled={s.busy || !ready} onClick={() => s.submit(() => ({ action: "receive", received_base_quantity: qty.trim(), record_date: day, note: note.trim() }), (b, k) => api.stepActualTransfer(rid, t.id, b, k))}>{s.label("Retry the same receipt", "Confirm received")}</button>
    </div> : <button className={btnAcc} onClick={() => setOpen(true)}>Confirm what arrived</button>)}
    {outgoing && t.status === "sent" && <button className={btnGhost} disabled={s.busy} onClick={() => s.submit(() => ({ action: "cancel", note: "Cancelled by sending manager" }), (b, k) => api.stepActualTransfer(rid, t.id, b, k))}>{s.label("Retry cancel", "Cancel transfer")}</button>}
  </div>;
}

export function StoreTransfers({ rid }) {
  const [data, setData] = useState(null), [error, setError] = useState(""), [epoch, setEpoch] = useState(0), [sending, setSending] = useState(false), [pending, setPending] = useState(false);
  const since = (() => { const d = new Date(`${todayISO()}T12:00:00Z`); d.setUTCDate(d.getUTCDate() - 28); return d.toISOString().slice(0, 10); })();
  useEffect(() => {
    let active = true; setError("");
    api.actualTransfers(rid, since).then(d => active && setData(d)).catch(e => active && setError(detail(e)));
    return () => { active = false; };
  }, [rid, epoch]); // eslint-disable-line react-hooks/exhaustive-deps
  if (error) return <p role="alert">{error}</p>;
  if (!data) return <p>Loading store transfers…</p>;
  const reload = () => { setPending(false); setSending(false); setEpoch(n => n + 1); };
  const waiting = data.transfers.filter(t => t.status === "sent" && t.to_store_id === data.store_id);
  return <div className="space-y-4" data-testid="store-transfers">
    <div className="flex gap-2 items-center"><h3 className="font-semibold">Store transfers</h3>
      <button className={sending ? btnAcc : btnGhost} disabled={pending} title={pending ? "Finish or retry the send first" : undefined} onClick={() => setSending(!sending)}>Send to another store</button></div>
    {!!waiting.length && <p role="status">{waiting.length} transfer(s) to confirm.</p>}
    {sending && <SendTransferForm rid={rid} items={data.items} stores={data.stores} onSent={reload} onPending={setPending} />}
    {!data.transfers.length && <p className="text-sm">No transfers in the last four weeks.</p>}
    {data.transfers.map(t => <TransferCard key={t.id} rid={rid} store={data.store_id} transfer={t} onChange={reload} />)}
  </div>;
}
