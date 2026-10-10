import React, { useEffect, useRef, useState } from "react";
import * as api from "../lib/api";
import { cardCls, inpCls, btnAcc, btnGhost, Field } from "./common";
import { countDraftError, validCountReview } from "./StaffCountDrafts";

export function StaffSubmissionReview({ review, onDecide }) {
  const items = review.sheet.sheet_snapshot.items;
  const [values, setValues] = useState(() => Object.fromEntries(items.map(i => [i.item_code, { item_code:i.item_code,inventory_value:"",confirmed:false,note:"" }])));
  const [note, setNote] = useState(""), [checked, setChecked] = useState(false), [busy, setBusy] = useState(false), [error, setError] = useState(""), [saved, setSaved] = useState(null);
  const attempt = useRef(null), frozen = busy || !!attempt.current || !!saved;
  const ready = !!review.latest && !review.errors.length && items.every(i => review.latest.quantities.find(q => q.item_code === i.item_code)?.counted_quantity != null);
  async function decide(decision) {
    setError("");
    if (!attempt.current) attempt.current = { key:crypto.randomUUID(),body:{ decision,note:note.trim(),expected_review_hash:review.reviewHash,
      quantities_reviewed:decision === "accepted" && checked, values:decision === "accepted" ? items.map(i => values[i.item_code]) : [] } };
    setBusy(true);
    try {
      const result = await onDecide(attempt.current.body,attempt.current.key);
      const d = result?.review?.decision;
      if (!d?.id || result.review.sheet?.id !== review.sheet.id || d.decision !== attempt.current.body.decision || d.review_snapshot?.reviewHash !== review.reviewHash || (d.decision === "accepted" && (!result.count?.header?.id || result.count.header.id !== d.snapshot_id || result.count.header.status !== "complete"))) throw new Error("Manager decision was not confirmed. Retry the same request.");
      setSaved(d.decision);
    } catch (e) { if ([409,422].includes(e?.response?.status)) attempt.current = null; setError(countDraftError(e)); }
    finally { setBusy(false); }
  }
  function change(code, patch) { setValues(v => ({ ...v,[code]:{ ...v[code],...patch,confirmed:patch.confirmed ?? false } })); setChecked(false); }
  return <section className={`${cardCls} p-4 space-y-3`} aria-label="Manager staff count review">
    <h3>Staff count review · {review.sheet.count_date} · Scope {review.sheet.sheet_snapshot.scope_revision}</h3>
    <p>{review.sheet.note} · Issued by {review.sheet.issued_by}</p>
    {review.decision ? <p>Final decision: {review.decision.decision} · {review.decision.reviewed_by}. Original submissions remain in history.</p> : <>
      {review.latest ? <p>Revision {review.latest.revision} · Counter: {review.latest.counter_name} · {review.latest.credential_kind === "shared_pin" ? "Shared PIN; counter name self-reported" : "Signed-in submission"} · {review.latest.note}</p> : <p>Awaiting staff quantities. You may reject an unused sheet.</p>}
      {!!review.errors.length && <p role="alert">{review.errors.join("; ")}</p>}
      {!ready && <p>Acceptance is held until every quantity is measured and the issued scope and units remain current.</p>}
      <fieldset disabled={frozen} className="space-y-3">
        {items.map(i => { const q = review.latest?.quantities.find(r => r.item_code === i.item_code); return <div key={i.item_code} className="border border-slate-700 p-3 rounded-lg">
          <p>{i.name_snapshot} · {i.item_code} · {q?.counted_quantity ?? "Uncounted"} {i.counted_unit} · {i.base_units_per_counted_unit} {i.base_unit} per unit</p>
          <p>Locations: {i.location_notes} · Staff evidence: {q?.note || "None entered"}</p>
          <Field label="Explicit total inventory value (USD)"><input aria-label={`Review value ${i.item_code}`} className={inpCls} inputMode="decimal" value={values[i.item_code].inventory_value} onChange={e => change(i.item_code,{inventory_value:e.target.value})} /></Field>
          <Field label="Quantity and value evidence"><input aria-label={`Review evidence ${i.item_code}`} className={inpCls} value={values[i.item_code].note} onChange={e => change(i.item_code,{note:e.target.value})} /></Field>
          <label><input aria-label={`Review confirm ${i.item_code}`} type="checkbox" checked={values[i.item_code].confirmed} onChange={e => change(i.item_code,{confirmed:e.target.checked})} /> I verified this measured quantity, issued conversion and explicit value.</label>
        </div>; })}
        <Field label="Manager decision note"><input aria-label="Manager count decision note" className={inpCls} value={note} onChange={e => setNote(e.target.value)} /></Field>
        <label><input aria-label="Manager quantities reviewed" type="checkbox" checked={checked} onChange={e => setChecked(e.target.checked)} /> I reviewed the latest quantities and all count locations. Accepting creates the accounting count.</label>
      </fieldset>
      {error && <p role="alert">{error} Refresh the sheet after a changed review.</p>}
      {saved ? <p role="status">Manager decision confirmed: {saved}. {saved === "accepted" ? "Explicit-value count recorded; no purchases or usage deductions created." : "No accounting count created."}</p> : attempt.current ? <button className={btnAcc} disabled={busy} onClick={() => decide(attempt.current.body.decision)}>Retry same manager decision</button> : <div className="flex gap-3">
        <button className={btnAcc} disabled={busy || !ready || !checked || !note.trim() || items.some(i => values[i.item_code].inventory_value === "" || !values[i.item_code].confirmed || !values[i.item_code].note.trim())} onClick={() => decide("accepted")}>Accept reviewed quantities and values</button>
        <button className={btnGhost} disabled={busy || !note.trim()} onClick={() => decide("rejected")}>Reject sheet without accounting changes</button>
      </div>}
    </>}
    {!!review.history.length && <details><summary>Quantity submission history ({review.history.length})</summary>{review.history.map(s => <p key={s.id}>Revision {s.revision} · {s.counter_name} · {s.submitted_at} · {s.quantities.map(q => `${q.item_code}: ${q.counted_quantity ?? "Uncounted"}`).join("; ")} · {s.note}</p>)}</details>}
  </section>;
}

function IssueSheetForm({ scope, onIssue }) {
  const [date,setDate] = useState(""), [timing,setTiming] = useState(""), [note,setNote] = useState(""), [busy,setBusy] = useState(false), [error,setError] = useState(""), [saved,setSaved] = useState(false);
  const attempt = useRef(null);
  async function issue() {
    if (!attempt.current) attempt.current = { key:crypto.randomUUID(),body:{scope_id:scope.header.id,count_date:date,timing,note:note.trim()} };
    setBusy(true); setError("");
    try { const result=await onIssue(attempt.current.body,attempt.current.key); if (!result?.sheet?.id || result.sheet.scope_id !== scope.header.id || result.sheet.count_date !== date || result.sheet.timing !== timing) throw new Error("Issued sheet was not confirmed. Retry the same request."); setSaved(true); }
    catch(e) { if ([409,422].includes(e?.response?.status)) attempt.current=null; setError(countDraftError(e)); }
    finally { setBusy(false); }
  }
  return <div className={`${cardCls} p-4 space-y-3`}><h3>Issue a staff quantity sheet · Current scope {scope.header.revision}</h3>
    <p>Every purchased item needs a current verified count-unit profile. The sheet fixes its date, receipt boundary, locations and conversions. Count between deliveries requires manager review before period close.</p>
    <fieldset disabled={busy || !!attempt.current || saved} className="space-y-3">
      <Field label="Staff sheet physical date"><input aria-label="Staff sheet physical date" type="date" className={inpCls} value={date} onChange={e => setDate(e.target.value)} /></Field>
      <Field label="Staff sheet receipt timing"><select aria-label="Staff sheet receipt timing" className={inpCls} value={timing} onChange={e => setTiming(e.target.value)}><option value="">Choose timing</option><option value="before_receipts">Before all receipts on this date</option><option value="after_receipts">After all receipts on this date</option></select></Field>
      <Field label="Staff sheet instructions"><input aria-label="Staff sheet instructions" className={inpCls} value={note} onChange={e => setNote(e.target.value)} /></Field>
    </fieldset>
    {error && <p role="alert">{error}</p>}{saved ? <><p role="status">Count sheet issued and confirmed. Staff can enter quantities in the Counts portal.</p><button className={btnGhost} onClick={() => { attempt.current=null; setSaved(false); setDate(""); setTiming(""); setNote(""); }}>Start another staff sheet</button></> : <button className={btnAcc} disabled={busy || !date || !timing || !note.trim()} onClick={issue}>{attempt.current ? "Retry same sheet issue" : "Issue staff count sheet"}</button>}
  </div>;
}

export function StaffCountReview({ restaurantId, scope, onAccepted }) {
  const [reviews,setReviews] = useState(null), [error,setError] = useState(""), [epoch,setEpoch] = useState(0);
  useEffect(() => {
    let active=true; setReviews(null); setError("");
    api.staffCountSheets(restaurantId).then(r => { if (!Array.isArray(r) || r.some(review => !validCountReview(review,restaurantId))) throw new Error("Count review history was not confirmed."); if (active) setReviews(r); }).catch(e => active && setError(countDraftError(e)));
    return () => { active=false; };
  },[restaurantId,epoch]);
  return <section className="space-y-4" data-testid="manager-staff-count-review"><h2>Staff quantities and manager acceptance</h2>
    <button className={btnGhost} onClick={() => setEpoch(n => n+1)}>Refresh staff count review</button>
    {scope && <IssueSheetForm key={scope.header.id} scope={scope} onIssue={async (body,key) => { const result=await api.issueStaffCountSheet(restaurantId,body,key); if (result?.sheet?.id) setEpoch(n => n+1); return result; }} />}
    {error ? <p role="alert">{error}</p> : !reviews ? <p>Loading staff count review…</p> : reviews.map(r => <StaffSubmissionReview key={`${r.sheet.id}:${r.reviewHash}`} review={r} onDecide={async (body,key) => { const result=await api.decideStaffCountSheet(restaurantId,r.sheet.id,body,key); if (result?.review?.decision?.decision === "accepted" && result.count?.header?.id) onAccepted?.(); return result; }} />)}
  </section>;
}
