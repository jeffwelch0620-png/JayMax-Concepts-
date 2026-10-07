import React, { useEffect, useRef, useState } from "react";
import * as api from "../lib/api";
import { Field, cardCls, inpCls, btnAcc, btnGhost } from "./common";

const stamp = () => ({ performed_at: "", business_date: "", timezone_name: "", calendar_date_confirmed: false, note: "" });
const blankWaste = () => ({ source_kind: "raw", raw_item_code: "", product_version_id: null, profile_id: null, source_batch_id: null,
  quantity: "", source_unit: "", factor: "", measurement_basis: "measured", category: "", already_included_in_batch: true });
const detail = e => { const d = e?.response?.data?.detail; return typeof d === "string" ? d : Array.isArray(d) ? d.map(x => x.msg).join("; ") : e.message || "Observation failed"; };

export function PrepObservations({ restaurantId }) {
  const [data, setData] = useState(null), [purpose, setPurpose] = useState("waste"), [mode, setMode] = useState("initial"), [eventId, setEventId] = useState(""), [reason, setReason] = useState("");
  const [time, setTime] = useState(stamp), [waste, setWaste] = useState(blankWaste), [lines, setLines] = useState([]), [complete, setComplete] = useState(false);
  const [busy, setBusy] = useState(false), [error, setError] = useState(""), [message, setMessage] = useState(""), [review, setReview] = useState(null), [confirmed, setConfirmed] = useState(false), [history, setHistory] = useState(null);
  const pending = useRef(null), alive = useRef(true);
  function freshLines(d) { return d.products.map(p => ({ product_id: p.product_id, product_version_id: p.id, profile_id: "", quantity: "", evidence: "" })); }
  useEffect(() => {
    let active = true; alive.current = true;
    api.nativePrepObservationSetup(restaurantId).then(d => { if (active) { setData(d); setLines(freshLines(d)); } }).catch(e => active && setError(detail(e)));
    return () => { active = false; alive.current = false; };
  }, [restaurantId]);
  const frozen = busy || !!pending.current;
  const product = data?.products.find(p => p.id === waste.product_version_id);
  const profiles = data?.profiles.filter(u => u.product_version_id === waste.product_version_id) || [];
  function change(fn) { fn(); setReview(null); setConfirmed(false); setHistory(null); setMessage(""); }
  function reset(d = data) { setTime(stamp()); setWaste(blankWaste()); setLines(d ? freshLines(d) : []); setComplete(false); setEventId(""); setReason(""); }
  function selectEvent(id) {
    const e = data.events.find(x => x.id === id);
    change(() => {
      setEventId(id); setReason(""); setComplete(false);
      if (!e?.review_snapshot.body) return;
      const b = e.review_snapshot.body;
      setTime({ performed_at: b.performed_at, business_date: b.business_date, timezone_name: b.timezone_name, calendar_date_confirmed: false, note: b.note });
      if (purpose === "waste") {
        const w = { ...b }; ["performed_at", "business_date", "timezone_name", "calendar_date_confirmed", "note"].forEach(k => delete w[k]);
        setWaste({ ...w, already_included_in_batch: true });
      } else setLines(e.review_snapshot.lines.map(l => {
        const p = data.products.find(x => x.product_id === l.product_id);
        return { product_id: l.product_id, product_version_id: p?.id || l.product_version_id,
          profile_id: data.profiles.some(u => u.id === l.profile_id && u.product_version_id === p?.id) ? l.profile_id : "", quantity: l.quantity, evidence: l.evidence };
      }));
    });
  }
  function body() {
    if (purpose === "waste") return { ...time, ...waste, raw_item_code: waste.raw_item_code || null, product_version_id: waste.product_version_id || null, profile_id: waste.profile_id || null, source_batch_id: waste.source_batch_id || null };
    return { ...time, complete_scope_confirmed: complete, lines: lines.map(({ product_id, ...l }) => l) };
  }
  async function refresh() {
    if (pending.current) return;
    setBusy(true); setError("");
    try { const d = await api.nativePrepObservationSetup(restaurantId); if (alive.current) { setData(d); reset(d); setReview(null); setConfirmed(false); setHistory(null); } }
    catch (e) { if (alive.current) setError(detail(e)); }
    finally { if (alive.current) setBusy(false); }
  }
  async function preview() {
    if (mode !== "initial" && !reason.trim()) { setError("Add a reason for this correction or void."); return; }
    if (mode !== "void") {
      if (!time.performed_at.trim() || !time.business_date.trim() || !time.timezone_name.trim() || !time.note.trim() || !time.calendar_date_confirmed) {
        setError("Enter the observation date, time with offset, timezone and evidence, then confirm this calendar day."); return;
      }
      if (purpose === "count" && (!lines.length || lines.some(l => !l.profile_id || !l.quantity.trim() || !l.evidence.trim()))) {
        setError("Choose a verified measurement and enter an observed quantity and evidence for every item. Unknown is not zero."); return;
      }
      if (purpose === "count" && !complete) { setError("Confirm the complete counted scope before reviewing."); return; }
      if (purpose === "waste" && waste.already_included_in_batch) { setError("Confirm this measured waste is separate from gross prep input and included trim."); return; }
      if (purpose === "waste" && (!waste.quantity.trim() || !waste.category || !waste.source_unit || !waste.factor
        || (waste.source_kind === "raw" ? !waste.raw_item_code : !waste.product_version_id || !waste.profile_id || !waste.source_batch_id))) {
        setError("Choose a verified waste item and unit, a source batch for prepared waste, and enter the measured amount and reason."); return;
      }
    }
    setBusy(true); setError(""); setReview(null); setConfirmed(false);
    try {
      const payload = mode === "initial" ? body() : { kind: mode, reason, replacement: mode === "replacement" ? body() : null };
      const r = mode === "initial" ? await api.previewNativePrepObservation(restaurantId, purpose, payload) : await api.previewNativePrepObservationChange(restaurantId, purpose, eventId, payload);
      if (alive.current) setReview({ ...r, payload, purpose, mode, eventId });
    } catch (e) { if (alive.current) setError(detail(e)); }
    finally { if (alive.current) setBusy(false); }
  }
  async function save() {
    if (!pending.current && (!review || !confirmed)) return;
    setBusy(true); setError("");
    try {
      if (!pending.current) pending.current = { purpose: review.purpose, mode: review.mode, eventId: review.eventId, key: crypto.randomUUID(), body: {
        [review.mode === "initial" ? "body" : "change"]: review.payload, expected_review_hash: review.reviewHash, reviewed: true } };
      const p = pending.current;
      const r = p.mode === "initial" ? await api.saveNativePrepObservation(restaurantId, p.purpose, p.body, p.key) : await api.saveNativePrepObservationChange(restaurantId, p.purpose, p.eventId, p.body, p.key);
      if (!r.event?.id || r.event.store_id !== ({ papa_leonis: "papa" }[restaurantId] || restaurantId) || r.event.purpose !== p.purpose
        || r.event.kind !== p.mode || r.event.review_hash !== p.body.expected_review_hash || (r.event.predecessor_id || null) !== (p.mode === "initial" ? null : p.eventId)) throw new Error("Saved observation was not confirmed. Retry this same record.");
      if (!alive.current) return;
      pending.current = null; setReview(null); setConfirmed(false); setHistory(null); setMode("initial"); reset();
      setMessage("Observation saved. Purchased-inventory Food Cost remains unchanged.");
      try { const d = await api.nativePrepObservationSetup(restaurantId); if (alive.current) { setData(d); setLines(freshLines(d)); } }
      catch (e) { if (alive.current) setError(`Observation saved; refresh failed: ${detail(e)}`); }
    } catch (e) {
      if (alive.current) { setError(detail(e)); if ([409, 422].includes(e?.response?.status)) { pending.current = null; setReview(null); setConfirmed(false); } }
    } finally { if (alive.current) setBusy(false); }
  }
  async function showHistory(e) {
    setBusy(true); setError("");
    try { const h = await api.nativePrepObservationHistory(restaurantId, e.purpose, e.root_id); if (alive.current) setHistory(h); }
    catch (err) { if (alive.current) setError(detail(err)); }
    finally { if (alive.current) setBusy(false); }
  }
  function updateWaste(patch) { change(() => setWaste(w => ({ ...w, ...patch }))); }
  function updateLine(index, patch) { change(() => setLines(ls => ls.map((l, i) => i === index ? { ...l, ...patch } : l))); }
  const timeFields = [["performed_at", "Observed at (timestamp with offset)"], ["business_date", "Observation calendar date (YYYY-MM-DD)"], ["timezone_name", "Location timezone"], ["note", "Observation evidence / note"]];
  return <section className={`${cardCls} space-y-4`} aria-label="Prep waste and physical counts">
    <h2 className="text-lg font-semibold">Waste and physical prep counts</h2>
    <p>Separate waste explains loss once. Counts record what is physically present; they do not reset recorded batch balances. Both stay separate from purchased-inventory Food Cost.</p>
    <p>Batch costs remain uncalculated. Recorded source output below includes prep allocations and standalone prepared waste; service usage and variance reports are still pending.</p>
    {error && <p role="alert">{error}</p>}{message && <p role="status">{message}</p>}
    <button className={btnGhost} disabled={frozen} onClick={refresh}>Refresh observation setup</button>
    {data && <>
      {data.policy && <p>Confirmed calendar-day timezone: {data.policy.timezone_name}</p>}
      <fieldset disabled={frozen} className="space-y-3">
        <Field label="Observation journal"><select aria-label="Observation journal" className={inpCls} value={purpose} onChange={e => change(() => { setPurpose(e.target.value); setMode("initial"); reset(); })}><option value="waste">Standalone waste</option><option value="count">Physical prep count</option></select></Field>
        <Field label="Observation action"><select aria-label="Observation action" className={inpCls} value={mode} onChange={e => change(() => { setMode(e.target.value); reset(); })}><option value="initial">Record new observation</option><option value="replacement">Correct observation</option><option value="void">Void erroneous observation</option></select></Field>
        {mode !== "initial" && <>
          <Field label="Current observation"><select aria-label="Current observation" className={inpCls} value={eventId} onChange={e => selectEvent(e.target.value)}><option value="">Select current observation</option>{data.events.filter(e => e.purpose === purpose && e.kind !== "void").map(e => <option key={e.id} value={e.id} disabled={!!e.review_snapshot?.container_fill_id}>{e.business_date} · {e.id} · revision {e.revision}{e.review_snapshot?.container_fill_id?" · use paired container reversal":""}</option>)}</select></Field>
          <Field label="Observation correction reason"><input aria-label="Observation correction reason" className={inpCls} value={reason} onChange={e => change(() => setReason(e.target.value))} /></Field>
          <p>Corrections retain the original date and item or count scope. Void means a record entered in error.</p>
        </>}
        {mode !== "void" && <>
          {timeFields.map(([key, label]) => <Field key={key} label={label}><input aria-label={label} className={inpCls} value={time[key]} readOnly={mode === "replacement" && key !== "note"} onChange={e => change(() => setTime(t => ({ ...t, [key]: e.target.value })))} /></Field>)}
          <label><input aria-label="Confirm observation calendar day" type="checkbox" checked={time.calendar_date_confirmed} onChange={e => change(() => setTime(t => ({ ...t, calendar_date_confirmed: e.target.checked })))} /> I confirm this calendar date and location timezone</label>
          {purpose === "waste" ? <>
            <Field label="Waste source type"><select aria-label="Waste source type" className={inpCls} value={waste.source_kind} onChange={e => change(() => setWaste({ ...blankWaste(), source_kind: e.target.value }))}><option value="raw">Purchased raw item</option><option value="prepared">Prepared source batch</option></select></Field>
            {waste.source_kind === "raw" ? <Field label="Purchased waste item"><select aria-label="Purchased waste item" className={inpCls} value={waste.raw_item_code || ""} onChange={e => { const raw = data.rawItems.find(x => x.code === e.target.value); updateWaste({ raw_item_code: raw?.code || "", source_unit: raw?.base_unit || "", factor: raw?.base_unit ? "1" : "" }); }}><option value="">Select verified purchased item</option>{data.rawItems.map(x => <option key={x.code} value={x.code} disabled={!x.base_unit}>{x.name} · {x.base_unit || "unit review needed"}</option>)}</select></Field> : <>
              <Field label="Prepared waste item"><select aria-label="Prepared waste item" className={inpCls} value={waste.product_version_id || ""} onChange={e => updateWaste({ product_version_id: e.target.value, profile_id: null, source_batch_id: null, source_unit: "", factor: "" })}><option value="">Select prepared identity</option>{data.products.map(x => <option key={x.id} value={x.id}>{x.name}</option>)}</select></Field>
              <Field label="Waste measured unit"><select aria-label="Waste measured unit" className={inpCls} value={waste.profile_id || ""} onChange={e => { const u = profiles.find(x => x.id === e.target.value); updateWaste({ profile_id: u?.id || null, source_unit: u?.source_unit || "", factor: u?.base_units_per_source_unit || "" }); }}><option value="">Choose verified measurement</option>{profiles.map(u => <option key={u.id} value={u.id}>{u.source_unit} · {u.base_units_per_source_unit} {product?.base_unit}</option>)}</select></Field>
              <Field label="Waste source lot"><select aria-label="Waste source lot" className={inpCls} value={waste.source_batch_id || ""} onChange={e => updateWaste({ source_batch_id: e.target.value })}><option value="">Select recorded source lot</option>{data.lots.filter(x => x.product_id === product?.product_id).map(x => <option key={x.id} value={x.id}>{x.sourceKind === "opening" ? "Opening count" : "Prep batch"} · {x.id} · {x.remainingRecordedQuantity} {x.base_unit} unallocated</option>)}</select></Field>
            </>}
            <Field label={`Measured waste quantity (${waste.source_unit || "select unit"})`}><input aria-label="Measured waste quantity" className={inpCls} value={waste.quantity} onChange={e => updateWaste({ quantity: e.target.value })} /></Field>
            <Field label="Waste category"><select aria-label="Waste category" className={inpCls} value={waste.category} onChange={e => updateWaste({ category: e.target.value })}><option value="">Choose waste reason</option><option value="storage_spoilage">Storage / spoilage</option><option value="service_discard">Service discard</option><option value="other">Other explained disposal</option></select></Field>
            <label><input aria-label="Confirm separate waste" type="checkbox" checked={!waste.already_included_in_batch} onChange={e => updateWaste({ already_included_in_batch: !e.target.checked })} /> I measured this disposal separately; it is not already in gross prep input or included trim</label>
          </> : <>
            <p>Count every listed prepared item. Enter an observed zero for an empty item; leave an unknown quantity blank and resolve it before saving.</p>
            {lines.map((l, i) => { const p = data.products.find(x => x.product_id === l.product_id); return <fieldset key={l.product_id} className={`${cardCls} space-y-2`}><legend>{p?.name || l.product_id}</legend>
              <Field label={`Count measurement ${i + 1}`}><select aria-label={`Count measurement ${i + 1}`} className={inpCls} value={l.profile_id} onChange={e => updateLine(i, { profile_id: e.target.value })}><option value="">Choose verified count measurement</option>{data.profiles.filter(u => u.product_version_id === l.product_version_id).map(u => <option key={u.id} value={u.id}>{u.source_unit} · {u.base_units_per_source_unit} {p?.base_unit}</option>)}</select></Field>
              <Field label={`Physical prep quantity ${i + 1}`}><input aria-label={`Physical prep quantity ${i + 1}`} className={inpCls} value={l.quantity} onChange={e => updateLine(i, { quantity: e.target.value })} /></Field>
              <Field label={`Count evidence ${i + 1}`}><input aria-label={`Count evidence ${i + 1}`} className={inpCls} value={l.evidence} onChange={e => updateLine(i, { evidence: e.target.value })} /></Field>
            </fieldset>; })}
            <label><input aria-label="Confirm full prep scope" type="checkbox" checked={complete} onChange={e => change(() => setComplete(e.target.checked))} /> I physically counted the complete listed prepared-item scope</label>
          </>}
        </>}
        <button className={btnAcc} disabled={mode !== "initial" && !eventId} onClick={preview}>Review observation</button>
      </fieldset>
      {review && <div className={`${cardCls} space-y-3`} aria-label="Observation review">
        <p>{review.review.purpose} · {review.review.kind} · {review.review.business_date}</p>
        {review.review.baseQuantity && <p>Measured separate waste: {review.review.baseQuantity} {review.review.base_unit}. No additional Food Cost deduction.</p>}
        <ul>{review.review.lines.map(l => <li key={l.product_id}>Physical prep count: {l.base_quantity} {l.base_unit}. {l.evidence}</li>)}</ul>
        <p>Costs: not calculated. Count quantities remain observations and do not reset recorded source output.</p>
        <label><input aria-label="Confirm observation review" type="checkbox" disabled={frozen} checked={confirmed} onChange={e => setConfirmed(e.target.checked)} /> I reviewed the measurements, source and scope</label>
        <button className={btnAcc} disabled={busy || (!confirmed && !pending.current)} onClick={save}>{pending.current ? "Retry same observation" : "Save reviewed observation"}</button>
      </div>}
      <h3 className="font-semibold">Observation history</h3>
      {data.events.length === 0 && <p>No native waste or prep counts recorded.</p>}
      {data.events.map(e => <div key={e.id}>{e.business_date} · {e.purpose} · {e.kind} · revision {e.revision} <button className={btnGhost} disabled={frozen} onClick={() => showHistory(e)}>History for {e.id}</button></div>)}
      {history && <div aria-label="Observation history">{history.events.map(e => <article key={e.id} className={cardCls}><p>{e.purpose} revision {e.revision} · {e.kind} · {e.reason}</p><ul>{e.review_snapshot.movements.map((m, i) => <li key={i}>{m.side}: {m.quantity} {m.base_unit}{m.source_batch_id && ` from batch ${m.source_batch_id}`}</li>)}{e.review_snapshot.lines.map(l => <li key={l.product_id}>Observed {l.base_quantity} {l.base_unit} · {l.evidence}</li>)}</ul></article>)}</div>}
    </>}
  </section>;
}
