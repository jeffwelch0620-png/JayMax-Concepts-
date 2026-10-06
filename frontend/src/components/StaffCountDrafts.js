import React, { useEffect, useRef, useState } from "react";
import * as api from "../lib/api";
import { cardCls, inpCls, btnAcc, btnGhost, Field } from "./common";

export const countDraftError = e => typeof e?.response?.data?.detail === "string" ? e.response.data.detail : e.message || "The saved outcome could not be confirmed.";
export const validCountReview = (r, rid) => !!r?.sheet?.id && r.sheet.store_id === (rid === "papa_leonis" ? "papa" : rid) && typeof r.reviewHash === "string" && /^[a-f0-9]{64}$/.test(r.reviewHash) && Array.isArray(r.sheet.sheet_snapshot?.items) && Array.isArray(r.errors) && Array.isArray(r.history) && (!r.latest || Array.isArray(r.latest.quantities));

export function StaffQuantityForm({ review, pin, counterName = "", onSubmit }) {
  const items = review.sheet.sheet_snapshot.items;
  const [name, setName] = useState(counterName), [note, setNote] = useState("");
  const [rows, setRows] = useState(() => Object.fromEntries(items.map(i => {
    const prior = review.latest?.quantities.find(q => q.item_code === i.item_code);
    return [i.item_code, { item_code: i.item_code, counted_quantity: prior?.counted_quantity ?? "", note: prior?.note || "" }];
  })));
  const [busy, setBusy] = useState(false), [error, setError] = useState(""), [saved, setSaved] = useState(false);
  const attempt = useRef(null), frozen = busy || !!attempt.current || saved;
  async function submit() {
    setError("");
    if (!name.trim() || !note.trim()) { setError("Enter the counter name and measurement note."); return; }
    if (!attempt.current) attempt.current = { key: crypto.randomUUID(), body: { pin, counter_name: name.trim(), note: note.trim(), expected_review_hash: review.reviewHash,
      lines: items.map(i => ({ ...rows[i.item_code], counted_quantity: rows[i.item_code].counted_quantity === "" ? null : rows[i.item_code].counted_quantity })) } };
    setBusy(true);
    try {
      const result = await onSubmit(attempt.current.body, attempt.current.key);
      if (!result?.submission?.id || result.submission.sheet_id !== review.sheet.id || !result.review?.history?.some(s => s.id === result.submission.id)) throw new Error("Quantity submission was not confirmed. Retry the same request.");
      setSaved(true);
    } catch (e) { if ([409,422].includes(e?.response?.status)) attempt.current = null; setError(countDraftError(e)); }
    finally { setBusy(false); }
  }
  return <section className={`${cardCls} p-4 space-y-3`} aria-label="Staff physical quantity draft">
    <h3>Physical quantities · {review.sheet.count_date} · {review.sheet.timing.replaceAll("_", " ")}</h3>
    <p>{review.sheet.note}</p><p>Count all listed locations in the issued units. Blank means uncounted; enter 0 for a measured zero. This submits quantities for manager review. It does not change accounting inventory or Food Cost.</p>
    <p>Counter names are entered for attribution. A shared PIN does not verify a person's identity.</p>
    {!!review.errors.length && <p role="alert">{review.errors.join("; ")}</p>}
    <fieldset disabled={frozen || !!review.errors.length} className="space-y-3">
      <Field label="Counter name"><input aria-label="Draft counter name" className={inpCls} value={name} onChange={e => setName(e.target.value)} /></Field>
      <Field label="Measurement note"><input aria-label="Draft measurement note" className={inpCls} value={note} onChange={e => setNote(e.target.value)} /></Field>
      {items.map(i => <div key={i.item_code} className="border border-slate-700 p-3 rounded-lg">
        <p>{i.name_snapshot} · {i.item_code} · {i.location_notes}</p><p>{i.counted_unit} · {i.base_units_per_counted_unit} {i.base_unit} per counted unit</p>
        <Field label={`Measured quantity (${i.counted_unit})`}><input aria-label={`Draft quantity ${i.item_code}`} className={inpCls} inputMode="decimal" value={rows[i.item_code].counted_quantity} onChange={e => setRows(r => ({ ...r, [i.item_code]: { ...r[i.item_code], counted_quantity: e.target.value } }))} /></Field>
        <Field label="Count locations / measurement evidence"><input aria-label={`Draft evidence ${i.item_code}`} className={inpCls} value={rows[i.item_code].note} onChange={e => setRows(r => ({ ...r, [i.item_code]: { ...r[i.item_code], note: e.target.value } }))} /></Field>
      </div>)}
    </fieldset>
    {error && <p role="alert">{error} Refresh if another submission or unit review changed this sheet.</p>}
    {saved ? <p role="status">Quantities submitted and confirmed. Manager acceptance and explicit values are still required. Refresh to view or revise the latest submission.</p> : <button className={btnAcc} disabled={busy || !!review.errors.length} onClick={submit}>{attempt.current ? "Retry same quantity submission" : "Submit quantities for review"}</button>}
  </section>;
}

export function StaffCountDrafts({ restaurantId, pin, counterName }) {
  const [reviews, setReviews] = useState(null), [error, setError] = useState(""), [epoch, setEpoch] = useState(0);
  useEffect(() => {
    let active = true; setReviews(null); setError("");
    api.staffCountDrafts(restaurantId, pin).then(result => {
      if (!Array.isArray(result) || result.some(r => !validCountReview(r, restaurantId))) throw new Error("Issued count sheets were not confirmed.");
      if (active) setReviews(result);
    }).catch(e => active && setError(countDraftError(e)));
    return () => { active = false; };
  }, [restaurantId,pin,epoch]);
  return <section className="space-y-4" data-testid="staff-native-count-drafts"><h2>Manager-issued physical counts</h2>
    <button className={btnGhost} onClick={() => setEpoch(n => n+1)}>Refresh issued count sheets</button>
    {error ? <p role="alert">{error}</p> : !reviews ? <p>Loading issued sheets…</p> : reviews.length ? reviews.map(r => <StaffQuantityForm key={`${r.sheet.id}:${r.reviewHash}`} review={r} pin={pin} counterName={counterName} onSubmit={(body,key) => api.submitStaffCountDraft(restaurantId,r.sheet.id,body,key)} />) : <p>No open count sheets. Ask your manager to issue a sheet in Actual Inventory.</p>}
  </section>;
}
