import React, { useEffect, useRef, useState } from "react";
import * as api from "../lib/api";
import { Field, cardCls, inpCls, btnAcc, btnGhost } from "./common";

const blank = () => ({ opening_count_id: "", closing_count_id: "", opening_cutoff: "", closing_cutoff: "", cutoffs_confirmed: false });
const detail = e => typeof e?.response?.data?.detail === "string" ? e.response.data.detail : e.message || "Comparison failed";

export function PrepPeriodComparison({ restaurantId }) {
  const [counts, setCounts] = useState([]), [form, setForm] = useState(blank), [result, setResult] = useState(null), [error, setError] = useState(""), [busy, setBusy] = useState(false);
  const alive = useRef(true);
  useEffect(() => {
    let active = true; alive.current = true;
    api.nativePrepPeriodCounts(restaurantId).then(d => { if (active) setCounts(d.counts); }).catch(e => active && setError(detail(e)));
    return () => { active = false; alive.current = false; };
  }, [restaurantId]);
  function edit(patch) { setForm(f => ({ ...f, cutoffs_confirmed: false, ...patch })); setResult(null); setError(""); }
  async function refresh() {
    setBusy(true); setResult(null); setError("");
    try { const d = await api.nativePrepPeriodCounts(restaurantId); if (alive.current) { setCounts(d.counts); setForm(blank()); } }
    catch (e) { if (alive.current) setError(detail(e)); }
    finally { if (alive.current) setBusy(false); }
  }
  async function compare() {
    setResult(null); setError("");
    if (!form.opening_count_id || !form.closing_count_id || form.opening_count_id === form.closing_count_id || !form.opening_cutoff || !form.closing_cutoff || !form.cutoffs_confirmed) {
      setError("Select two different counts, choose activity cutoffs and confirm their timing."); return;
    }
    setBusy(true);
    try {
      const d = await api.previewNativePrepPeriod(restaurantId, form);
      if (d.report.store_id !== ({ papa_leonis: "papa" }[restaurantId] || restaurantId)) throw new Error("Comparison location was not confirmed.");
      if (alive.current) setResult(d);
    } catch (e) { if (alive.current) setError(detail(e)); }
    finally { if (alive.current) setBusy(false); }
  }
  return <section className={`${cardCls} space-y-4`} aria-label="Prep count period comparison">
    <h2 className="text-lg font-semibold">Prep count period comparison</h2>
    <p>Compare physical prep counts with recorded production, waste and use in other prep. Purchased-inventory Food Cost remains independent.</p>
    <p>Service use is still missing. The remaining depletion can include service use, unrecorded activity or loss; it is not a confirmed waste variance.</p>
    {error && <p role="alert">{error}</p>}
    <button className={btnGhost} disabled={busy} onClick={refresh}>Refresh period counts</button>
    <fieldset disabled={busy} className="space-y-3">
      {[ ["opening", "Opening"], ["closing", "Closing"] ].map(([key,label]) => <div key={key} className="space-y-2">
        <Field label={`${label} prep count`}><select aria-label={`${label} prep count`} className={inpCls} value={form[`${key}_count_id`]} onChange={e => edit({ [`${key}_count_id`]: e.target.value })}>
          <option value="">Choose physical prep count</option>{counts.map(c => <option key={c.id} value={c.id}>{c.performed_at} · {c.timezone_name} · revision {c.revision}</option>)}
        </select></Field>
        <Field label={`${label} activity cutoff`}><select aria-label={`${label} activity cutoff`} className={inpCls} value={form[`${key}_cutoff`]} onChange={e => edit({ [`${key}_cutoff`]: e.target.value })}>
          <option value="">Choose exact-time activity timing</option><option value="before_all">Count was before all activity at this instant</option><option value="after_all">Count was after all activity at this instant</option>
        </select></Field>
      </div>)}
      <p>For adjacent periods, use the same cutoff when a closing count becomes the next opening. If a count occurred between activities at the same timestamp, resolve their timing before comparing.</p>
      <label><input aria-label="Confirm prep period cutoffs" type="checkbox" checked={form.cutoffs_confirmed} onChange={e => edit({ cutoffs_confirmed: e.target.checked })} /> I confirmed both count cutoffs</label>
      <button className={btnAcc} onClick={compare}>Compare prep period</button>
    </fieldset>
    {result && <div aria-label="Prep period results" className="space-y-4">
      <p>Current comparison: {result.report.opening.performed_at} to {result.report.closing.performed_at}. Production completeness is unverified. Service use is not captured; final expected stock and unexplained variance remain unavailable.</p>
      <p>Corrections and backfilled records change a refreshed comparison. This comparison does not close a period or reset stock.</p>
      {result.report.prepared.map(p => <article key={p.product_id} className={`${cardCls} space-y-2`}>
        <h3 className="font-semibold">{p.name} ({p.base_unit})</h3>
        <p>Opening {p.openingQuantity} + recorded production {p.recordedProduction} − closing {p.closingQuantity} = observed depletion {p.observedDepletion}</p>
        <p>Use in other prep: measured {p.recordedNestedUseMeasured}; estimated {p.recordedNestedUseEstimated}. Recorded standalone waste: {p.recordedWaste}.</p>
        <p>Service use or unrecorded loss: {p.serviceUseOrUnrecordedLoss}</p>
        {p.flags.length > 0 && <p role="alert">These quantities conflict with recorded activity. Check count timing, production completeness and usage records; negative differences have been retained.</p>}
      </article>)}
      <h3 className="font-semibold">Purchased-item explanations</h3>
      {result.report.rawExplanations.length === 0 && <p>No recorded raw use or standalone raw waste in this interval.</p>}
      {result.report.rawExplanations.map(r => <article key={r.raw_item_code} className={cardCls}>
        <p>{r.raw_item_code} ({r.base_unit}): gross prep use measured {r.recordedGrossPrepUseMeasured}, estimated {r.recordedGrossPrepUseEstimated}; separate raw waste {r.recordedStandaloneRawWaste}; total recorded explanation {r.recordedRawExplanation}.</p>
        <p>Annotated included trim {r.annotatedIncludedTrim} is already in gross input and is not deducted again. {r.unannotatedInputs > 0 && `${r.unannotatedInputs} input records lack trim measurements.`}</p>
      </article>)}
      <p>Activity tied to opening: {result.report.boundaryEvents.opening.length}; tied to closing: {result.report.boundaryEvents.closing.length}; included records: {result.report.includedEvents.length}.</p>
      <p>Analytical costs remain uncalculated. Food Cost is unchanged.</p>
    </div>}
  </section>;
}
