import React, { useCallback, useEffect, useRef, useState } from "react";
import * as api from "../lib/api";
import { Field, cardCls, inpCls, btnAcc, btnGhost } from "./common";
import { PrepCorrectionReview } from "./PrepCorrectionReview";

const blank = () => ({ recipe_version_id: "", planned_batches: "", output_quantity: "", performed_at: "", business_date: "", timezone_name: "",
  calendar_date_confirmed: false, single_output_confirmed: false, inputs: [], note: "" });
const detail = e => { const d = e?.response?.data?.detail; return typeof d === "string" ? d : Array.isArray(d) ? d.map(x => x.msg).join("; ") : e.message || "Batch recording failed"; };

export function PreparedBatchLedger({ restaurantId }) {
  const [data, setData] = useState(null), [form, setForm] = useState(blank), [mode, setMode] = useState("initial"), [eventId, setEventId] = useState(""), [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false), [error, setError] = useState(""), [message, setMessage] = useState(""), [review, setReview] = useState(null), [confirmed, setConfirmed] = useState(false), [history, setHistory] = useState(null);
  const pending = useRef(null), alive = useRef(true);
  const [dependencies, setDependencies] = useState(null);
  const receiveDependencies = useCallback(result => { setDependencies(result); setReview(null); setConfirmed(false); }, []);
  const dependenciesReady = dependencies?.restaurantId === restaurantId && dependencies?.selectedEventId === eventId && dependencies?.gate?.status === "eligible_for_preview";
  useEffect(() => {
    let active = true; alive.current = true;
    api.nativePrepBatchSetup(restaurantId).then(d => active && setData(d)).catch(e => active && setError(detail(e)));
    return () => { active = false; alive.current = false; };
  }, [restaurantId]);
  const frozen = busy || !!pending.current;
  const recipe = data?.recipes.find(r => r.id === form.recipe_version_id);
  const event = data?.events.find(e => e.id === eventId);
  function change(fn) { fn(); setReview(null); setConfirmed(false); setHistory(null); setMessage(""); }
  function update(k, v) { change(() => setForm(f => ({ ...f, [k]: v }))); }
  function input(index, k, v) { change(() => setForm(f => ({ ...f, inputs: f.inputs.map((x, i) => i === index ? { ...x, [k]: v } : x) }))); }
  function selectRecipe(id) {
    const r = data.recipes.find(x => x.id === id);
    change(() => setForm(f => ({ ...f, recipe_version_id: id, output_quantity: "", inputs: (r?.lines || []).map(l => ({
      recipe_line_id: l.id, quantity: "", source_unit: l.source_unit, factor: l.factor, measurement_basis: "", source_batch_id: null,
      included_loss_quantity: "", evidence: "", loss_evidence: "" })) })));
  }
  function selectEvent(id) {
    setDependencies(null);
    const e = data.events.find(x => x.id === id);
    change(() => { setEventId(id); setReason(""); setForm(e?.review_snapshot.batch ? { ...e.review_snapshot.batch, inputs: e.review_snapshot.batch.inputs.map(x => ({ ...x, included_loss_quantity: x.included_loss_quantity ?? "", loss_evidence: x.loss_evidence ?? "" })) } : blank()); });
  }
  function batchBody() { return { ...form, inputs: form.inputs.map(x => ({ ...x, source_batch_id: x.source_batch_id || null, included_loss_quantity: x.included_loss_quantity === "" ? null : x.included_loss_quantity, loss_evidence: x.loss_evidence || null })) }; }
  function body() { return mode === "initial" ? batchBody() : { kind: mode, reason, replacement: mode === "replacement" ? batchBody() : null }; }
  async function refresh() {
    if (pending.current) return;
    setBusy(true); setError("");
    try { const d = await api.nativePrepBatchSetup(restaurantId); if (alive.current) { setData(d); setReview(null); setConfirmed(false); setHistory(null); } }
    catch (e) { if (alive.current) setError(detail(e)); }
    finally { if (alive.current) setBusy(false); }
  }
  async function preview() {
    if (mode !== "initial" && !dependenciesReady) return;
    setBusy(true); setReview(null); setConfirmed(false); setError("");
    try {
      const payload = body();
      const r = mode === "initial" ? await api.previewNativePrepBatch(restaurantId, payload) : await api.previewNativePrepBatchChange(restaurantId, eventId, payload);
      if (alive.current) setReview({ ...r, payload, mode, eventId });
    } catch (e) { if (alive.current) setError(detail(e)); }
    finally { if (alive.current) setBusy(false); }
  }
  async function save() {
    if (!pending.current && review?.mode !== "initial" && !dependenciesReady) return;
    if (!pending.current && (!review || !confirmed)) return;
    setBusy(true); setError("");
    try {
      if (!pending.current) pending.current = { mode: review.mode, eventId: review.eventId, key: crypto.randomUUID(), body: {
        [review.mode === "initial" ? "batch" : "change"]: review.payload, expected_review_hash: review.reviewHash, reviewed: true } };
      const p = pending.current;
      const r = p.mode === "initial" ? await api.saveNativePrepBatch(restaurantId, p.body, p.key) : await api.saveNativePrepBatchChange(restaurantId, p.eventId, p.body, p.key);
      const expectedStore = ({ papa_leonis: "papa" }[restaurantId] || restaurantId);
      if (!r.event?.id || r.event.store_id !== expectedStore || r.event.kind !== p.mode || r.event.review_hash !== p.body.expected_review_hash
        || (r.event.predecessor_id || null) !== (p.mode === "initial" ? null : p.eventId)) throw new Error("Saved batch was not confirmed. Retry this same record.");
      if (!alive.current) return;
      pending.current = null; setReview(null); setConfirmed(false); setForm(blank()); setEventId(""); setReason(""); setMode("initial"); setHistory(null);
      setMessage("Batch journal saved. Track 1 Food Cost remains based on purchased inventory counts and receipts.");
      try { const d = await api.nativePrepBatchSetup(restaurantId); if (alive.current) setData(d); }
      catch (e) { if (alive.current) setError(`Batch saved; refresh failed: ${detail(e)}`); }
    } catch (e) {
      if (alive.current) {
        setError(detail(e));
        if ([409, 422].includes(e?.response?.status)) { pending.current = null; setReview(null); setConfirmed(false); }
      }
    } finally { if (alive.current) setBusy(false); }
  }
  async function showHistory(root) {
    setBusy(true); setError("");
    try { const h = await api.nativePrepBatchHistory(restaurantId, root); if (alive.current) setHistory(h); }
    catch (e) { if (alive.current) setError(detail(e)); }
    finally { if (alive.current) setBusy(false); }
  }
  const fields = [["planned_batches", "Planned recipe batches"], ["output_quantity", `Measured usable output (${recipe?.outputUnit || "approved output unit"})`], ["performed_at", "Prepared at (ISO timestamp with offset)"], ["business_date", "Preparation calendar date (YYYY-MM-DD)"], ["timezone_name", "Location timezone (for example America/New_York)"], ["note", "Batch evidence / note"]];
  return <section className={`${cardCls} space-y-4`} aria-label="Prep batch journal">
    <h2 className="text-lg font-semibold">Prep batch journal</h2>
    <p>Record gross ingredients and measured usable output. Included trim explains that input; it does not create another withdrawal. Costs await a costing policy.</p>
    <p>Lot quantities below are recorded unallocated output. Physical prep counts and standalone waste remain separate from this batch journal. Service usage is still pending.</p>
    {error && <p role="alert">{error}</p>}{message && <p role="status">{message}</p>}
    <button className={btnGhost} disabled={frozen} onClick={refresh}>Refresh batch setup</button>
    {data && <>
      <fieldset disabled={frozen} className="space-y-3">
        <Field label="Record action"><select className={inpCls} aria-label="Record action" value={mode} onChange={e => change(() => { setMode(e.target.value); setForm(blank()); setEventId(""); setReason(""); })}><option value="initial">Record new batch</option><option value="replacement">Correct recorded batch</option><option value="void">Void erroneous record</option></select></Field>
        {mode !== "initial" && <>
          <Field label="Current batch"><select aria-label="Current batch" className={inpCls} value={eventId} onChange={e => selectEvent(e.target.value)}><option value="">Select current batch</option>{data.events.filter(e => e.kind !== "void").map(e => <option key={e.id} value={e.id}>{e.business_date} · {e.id} · revision {e.revision}</option>)}</select></Field>
          <Field label="Correction reason"><input aria-label="Correction reason" className={inpCls} value={reason} onChange={e => change(() => setReason(e.target.value))} /></Field>
          <p>Corrections keep the original date and prepared item. Resolve batches that used this output first. Voiding an erroneous record is not waste reporting.</p>
          {eventId && <PrepCorrectionReview key={`${restaurantId}:${eventId}`} restaurantId={restaurantId} eventId={eventId} onResult={receiveDependencies} />}
        </>}
        {mode !== "void" && <>
          <Field label="Approved recipe"><select aria-label="Approved recipe" className={inpCls} value={form.recipe_version_id} onChange={e => selectRecipe(e.target.value)}><option value="">Select reviewed recipe</option>{data.recipes.map(r => <option key={r.id} value={r.id} disabled={r.reviewNeeded}>{r.review_snapshot.product.name} · recipe {r.revision}{r.reviewNeeded ? " · review needed" : ""}</option>)}</select></Field>
          {fields.map(([key, label]) => <Field key={key} label={label}><input aria-label={label} className={inpCls} value={form[key]} readOnly={mode === "replacement" && ["performed_at", "business_date", "timezone_name"].includes(key)} onChange={e => update(key, e.target.value)} /></Field>)}
          {form.inputs.map((x, i) => {
            const l = recipe?.lines.find(v => v.id === x.recipe_line_id);
            const pid = l?.source_snapshot?.recipe?.product_id;
            return <fieldset key={x.recipe_line_id} className={`${cardCls} space-y-2`}><legend>Ingredient {i + 1}: {l?.raw_item_code || l?.source_snapshot?.product?.name || "prepared item"} ({x.source_unit})</legend>
              <Field label={`Gross input ${i + 1}`}><input aria-label={`Gross input ${i + 1}`} className={inpCls} value={x.quantity} onChange={e => input(i, "quantity", e.target.value)} /></Field>
              <Field label={`Input basis ${i + 1}`}><select aria-label={`Input basis ${i + 1}`} className={inpCls} value={x.measurement_basis} onChange={e => input(i, "measurement_basis", e.target.value)}><option value="">Choose measurement basis</option><option value="measured">Measured</option><option value="recipe_estimate">Recipe estimate</option></select></Field>
              {l?.source_kind === "prepared" && <Field label={`Prepared source lot ${i + 1}`}><select aria-label={`Prepared source lot ${i + 1}`} className={inpCls} value={x.source_batch_id || ""} onChange={e => input(i, "source_batch_id", e.target.value)}><option value="">Select recorded source lot</option>{data.lots.filter(v => v.product_id === pid).map(v => <option key={v.id} value={v.id}>{v.sourceKind === "opening" ? "Opening count" : "Prep batch"} · {v.id} · {v.remainingRecordedQuantity} {v.base_unit} unallocated</option>)}</select></Field>}
              <Field label={`Input evidence ${i + 1}`}><input aria-label={`Input evidence ${i + 1}`} className={inpCls} value={x.evidence} onChange={e => input(i, "evidence", e.target.value)} /></Field>
              <Field label={`Included trim/loss ${i + 1} (blank means unknown)`}><input aria-label={`Included trim/loss ${i + 1} (blank means unknown)`} className={inpCls} value={x.included_loss_quantity} onChange={e => input(i, "included_loss_quantity", e.target.value)} /></Field>
              <Field label={`Loss evidence ${i + 1}`}><input aria-label={`Loss evidence ${i + 1}`} className={inpCls} value={x.loss_evidence} onChange={e => input(i, "loss_evidence", e.target.value)} /></Field>
            </fieldset>;
          })}
          <label className="block"><input type="checkbox" checked={form.calendar_date_confirmed} onChange={e => update("calendar_date_confirmed", e.target.checked)} /> I confirm calendar-day reporting and this location timezone</label>
          <label className="block"><input type="checkbox" checked={form.single_output_confirmed} onChange={e => update("single_output_confirmed", e.target.checked)} /> This batch has one usable output; no recoverable byproducts need separate mapping</label>
        </>}
        <button className={btnAcc} disabled={mode !== "initial" && (!eventId || !dependenciesReady)} onClick={preview}>Review batch quantities</button>
      </fieldset>
      {review && <div className={`${cardCls} space-y-3`} aria-label="Batch quantity review">
        <p>{review.review.kind} · {review.review.business_date} · {review.review.timezone_name}</p>
        {review.review.usableBaseOutput !== null && <p>Usable output: {review.review.usableBaseOutput} {review.review.base_unit}. Standard output: {review.review.standardBaseOutput} {review.review.base_unit}.</p>}
        <ul>{review.review.inputs.map((x, i) => <li key={x.recipe_line_id}>Input {i + 1}: {x.base_quantity} {x.base_unit}, {x.measurement_basis}. Standard: {x.standardBaseQuantity}. Included loss: {x.includedLossBaseQuantity ?? "unknown"}. {x.sourceBatch && `Source batch ${x.sourceBatch.id}.`}</li>)}</ul>
        <p>Costs: not calculated. Corrections reverse prior applied quantities before recording the replacement.</p>
        <label><input type="checkbox" disabled={frozen} checked={confirmed} onChange={e => setConfirmed(e.target.checked)} /> I reviewed the sources, measurements and included loss</label>
        <button className={btnAcc} disabled={busy || (!confirmed && !pending.current)} onClick={save}>{pending.current ? "Retry same batch record" : "Save reviewed batch"}</button>
      </div>}
      <h3 className="font-semibold">Recorded batch history</h3>
      {data.events.length === 0 && <p>No native batches recorded.</p>}
      {data.events.map(e => <div key={e.id}><span>{e.business_date} · {e.kind} · revision {e.revision} · {e.id} </span><button className={btnGhost} disabled={frozen} onClick={() => showHistory(e.root_id)}>History for {e.id}</button></div>)}
      {history && <div aria-label="Batch history">{history.events.map(e => <article key={e.id} className={cardCls}><p>Revision {e.revision} · {e.kind} · {e.reason}</p><ul>{e.review_snapshot.movements.map((m, i) => <li key={i}>{m.side}: {m.kind} {m.quantity} {m.base_unit}{m.source_batch_id && ` from ${m.source_batch_id}`}</li>)}</ul></article>)}</div>}
      {event && event.kind === "void" && <p>This record is voided and cannot be reopened.</p>}
    </>}
  </section>;
}
