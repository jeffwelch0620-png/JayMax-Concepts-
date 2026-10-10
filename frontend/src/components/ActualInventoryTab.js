import React, { useEffect, useRef, useState } from "react";
import * as api from "../lib/api";
import { StaffCountReview } from "./StaffCountReview";
import { PageTitle, Field, MetricCard, cardCls, inpCls, btnAcc, btnGhost } from "./common";

const blank = v => v === "" || v == null ? null : v;
const errorText = e => {
  const d = e?.response?.data?.detail;
  return typeof d === "string" ? d : d?.reasons?.join("; ") || d?.message || e.message || "Request failed. Retry or check saved history.";
};
const timingLabel = value => value === "before_receipts" ? "before that day’s receipts" : "after that day’s receipts";

export function PhysicalCountForm({ scope, onSave, onRecount = null, unitProfiles = [] }) {
  const [day, setDay] = useState(onRecount?.header.count_date || "");
  const [timing, setTiming] = useState(onRecount?.header.timing || "");
  const [note, setNote] = useState("");
  const [draft, setDraft] = useState(() => Object.fromEntries(scope.items.map(i => {
    const old = onRecount?.lines.find(l => l.item_code === i.item_code);
    const u = unitProfiles.find(p => p.item_code === i.item_code && p.base_unit === i.base_unit && !p.stale);
    return [i.item_code, { item_code: i.item_code, counted_quantity: old?.counted_quantity ?? "", counted_unit: old?.counted_unit || u?.source_unit || i.base_unit,
      base_units_per_counted_unit: old?.base_units_per_counted_unit ?? u?.base_units_per_source_unit ?? "1", inventory_value: old?.inventory_value ?? "", confirmed: false, note: "" }];
  })));
  const [busy, setBusy] = useState(false), [error, setError] = useState(""), [saved, setSaved] = useState(null);
  const attempt = useRef(null);
  const frozen = busy || !!attempt.current || !!saved;
  function change(code, patch) { setDraft(d => ({ ...d, [code]: { ...d[code], ...patch, confirmed: patch.confirmed ?? false } })); }
  async function save() {
    setError("");
    if (!day || !timing || !note.trim()) { setError("Choose the count date, receipt timing and a count note."); return; }
    if (!attempt.current) {
      attempt.current = { key: crypto.randomUUID(), body: { scope_id: scope.header.id, count_date: day, timing, note,
        corrects_snapshot_id: onRecount?.header.id || null, lines: scope.items.map(i => ({ ...draft[i.item_code],
          counted_quantity: blank(draft[i.item_code].counted_quantity), inventory_value: blank(draft[i.item_code].inventory_value),
          base_units_per_counted_unit: blank(draft[i.item_code].counted_quantity) == null ? null : blank(draft[i.item_code].base_units_per_counted_unit) })) } };
    }
    setBusy(true);
    try {
      const result = await onSave(attempt.current.body, attempt.current.key);
      if (!result?.header?.id || !Array.isArray(result.lines) || result.lines.length !== scope.items.length) throw new Error("Saved count was not confirmed. Retry the same request.");
      setSaved(result); setError("");
    } catch (e) {
      if ([409, 422].includes(e?.response?.status)) attempt.current = null;
      setError(errorText(e));
    } finally { setBusy(false); }
  }
  return <section className={`${cardCls} p-4 space-y-4`} aria-label="Physical inventory count">
    <h3 className="font-semibold">{onRecount ? "Append a corrected count" : "Record a physical count"} · Scope {scope.header.revision}</h3>
    <p className="text-sm text-slate-400">Purchased inventory only. Enter the total value of the inventory physically counted for each item, excluding taxes and fees. A blank quantity or value remains incomplete; an actual zero must be entered as 0.</p>
    <fieldset disabled={frozen} className="space-y-4">
      <div className="grid md:grid-cols-3 gap-3">
        <Field label="Physical count date"><input aria-label="Physical count date" type="date" className={inpCls} value={day} onChange={e => setDay(e.target.value)} /></Field>
        <Field label="Count timing"><select aria-label="Count timing" className={inpCls} value={timing} onChange={e => setTiming(e.target.value)}><option value="">Choose receipt timing</option><option value="before_receipts">Before all receipts on this date</option><option value="after_receipts">After all receipts on this date</option></select></Field>
        <Field label="Count note"><input aria-label="Count note" className={inpCls} value={note} onChange={e => setNote(e.target.value)} /></Field>
      </div>
      <p className="text-xs text-amber-200">Use these boundaries only if the count was taken before all or after all receipts that day. A count between deliveries needs review before closing a period.</p>
      {scope.items.map(i => { const line = draft[i.item_code]; return <div className="border border-slate-700 rounded-lg p-3 space-y-2" key={i.item_code}>
        <p className="font-semibold text-sm">{i.name_snapshot} · {i.item_code} · Inventory unit: {i.base_unit}</p>
        <p className="text-xs text-slate-400">Locations to include: {i.location_notes}</p>
        <div className="grid md:grid-cols-5 gap-3">
          <Field label="Measured quantity"><input aria-label={`Quantity ${i.item_code}`} className={inpCls} inputMode="decimal" value={line.counted_quantity} onChange={e => change(i.item_code, { counted_quantity: e.target.value })} /></Field>
          <Field label="Counted unit"><input aria-label={`Unit ${i.item_code}`} className={inpCls} value={line.counted_unit} onChange={e => change(i.item_code, { counted_unit: e.target.value })} /></Field>
          <Field label={`${i.base_unit} per counted unit`}><input aria-label={`Conversion ${i.item_code}`} className={inpCls} inputMode="decimal" value={line.base_units_per_counted_unit} onChange={e => change(i.item_code, { base_units_per_counted_unit: e.target.value })} /></Field>
          <Field label="Confirmed total value (USD)"><input aria-label={`Value ${i.item_code}`} className={inpCls} inputMode="decimal" value={line.inventory_value} onChange={e => change(i.item_code, { inventory_value: e.target.value })} /></Field>
          <Field label="Value / count evidence"><input aria-label={`Evidence ${i.item_code}`} className={inpCls} value={line.note} onChange={e => change(i.item_code, { note: e.target.value })} /></Field>
        </div>
        <label className="flex gap-2 text-sm"><input aria-label={`Confirm ${i.item_code}`} type="checkbox" checked={line.confirmed} onChange={e => change(i.item_code, { confirmed: e.target.checked })} />I verified this physical quantity, conversion and total value.</label>
      </div>; })}
    </fieldset>
    {error && <p role="alert" className="text-red-300">{error}</p>}
    {saved ? <p role="status" className="text-emerald-300">Count saved and confirmed · {saved.header.status}. {saved.header.status === "incomplete" ? "Append a completed recount before using it for Food Cost." : "Available for actual-usage reporting."}</p>
      : <button className={btnAcc} disabled={busy} onClick={save}>{attempt.current ? "Retry same count save" : "Save count snapshot"}</button>}
  </section>;
}

function ScopeForm({ setup, onSave }) {
  const [rows, setRows] = useState(() => Object.fromEntries(setup.items.map(i => {
    const old = setup.scope?.items.find(s => s.item_code === i.code);
    return [i.code, { selected: !!old, item_code: i.code, base_unit: old?.base_unit || i.base_unit || "", location_notes: old?.location_notes || "" }];
  })));
  const [note, setNote] = useState(""), [busy, setBusy] = useState(false), [error, setError] = useState("");
  const attempt = useRef(null);
  function change(code, patch) { setRows(r => ({ ...r, [code]: { ...r[code], ...patch } })); }
  async function save() {
    setError("");
    if (!attempt.current) {
      const items = Object.values(rows).filter(r => r.selected).map(({ selected, ...r }) => r);
      if (!note.trim() || !items.length || items.some(i => !i.base_unit || !i.location_notes.trim())) { setError("Choose all purchased food items and confirm each inventory unit and count locations."); return; }
      attempt.current = { key: crypto.randomUUID(), body: { scope_kind: "purchased_items_only", valuation_method: "explicit_count_values", note, items } };
    }
    setBusy(true);
    try { await onSave(attempt.current.body, attempt.current.key); }
    catch (e) { if ([409, 422].includes(e?.response?.status)) attempt.current = null; setError(errorText(e)); }
    finally { setBusy(false); }
  }
  return <section className={`${cardCls} p-4 space-y-4`}><h3 className="font-semibold">Full purchased-food count scope</h3>
    <p className="text-sm text-slate-400">Choose all purchased food inventory items and locations, including items with sales tracking disabled. Prepped items are excluded. Changes create a new scope version; periods cannot compare counts from different scope versions.</p>
    <fieldset disabled={busy || !!attempt.current} className="space-y-3">
      <Field label="Scope confirmation note"><input className={inpCls} value={note} onChange={e => setNote(e.target.value)} /></Field>
      {setup.items.map(i => <div className="grid md:grid-cols-3 gap-3 items-center" key={i.code}>
        <label className="flex gap-2 text-sm"><input type="checkbox" checked={rows[i.code].selected} onChange={e => change(i.code, { selected: e.target.checked })} />{i.name} ({i.code})</label>
        <Field label="Fixed inventory unit"><select className={inpCls} value={rows[i.code].base_unit} disabled={!!i.base_unit} onChange={e => change(i.code, { base_unit: e.target.value })}><option value="">Choose unit</option>{setup.baseUnits.map(u => <option key={u}>{u}</option>)}</select></Field>
        <Field label="Raw inventory count locations"><input className={inpCls} value={rows[i.code].location_notes} onChange={e => change(i.code, { location_notes: e.target.value })} /></Field>
      </div>)}
    </fieldset>{error && <p role="alert" className="text-red-300">{error}</p>}<button className={btnAcc} disabled={busy} onClick={save}>{attempt.current ? "Retry scope confirmation" : "Confirm count scope"}</button>
  </section>;
}

export function ActualPeriodView({ report, onClose, busy = false }) {
  const [reviewed, setReviewed] = useState(false), [overages, setOverages] = useState(false), [error, setError] = useState("");
  const attempt = useRef(null);
  async function close() {
    setError("");
    if (!attempt.current) attempt.current = { key: crypto.randomUUID(), body: { opening_snapshot_id: report.openingSnapshotId,
      closing_snapshot_id: report.closingSnapshotId, expected_report_hash: report.reportHash, purchases_reviewed: true, counts_reviewed: true,
      acknowledge_overages: overages, supersedes_closure_id: report.supersedesClosureId || null,
      opening_bridge_id: report.openingBridgeId || null } };
    try { await onClose(attempt.current.body, attempt.current.key); } catch (e) { setError(errorText(e)); }
  }
  return <section className="space-y-4">
    {report.openingBridgeId && <p className="text-emerald-200">Opening quantities and values carry from the reviewed item-list handoff at this boundary.</p>}
    {report.supersedesClosureId && <p className="text-amber-200">This replaces a reopened report. The original report will remain in history. Close reopened periods from oldest to newest.</p>}
    <p className="text-sm">Opening count {report.openingCountDate}, {timingLabel(report.openingTiming)} · Closing count {report.closingCountDate}, {timingLabel(report.closingTiming)}</p>
    <p className="text-xs text-slate-400">Includes receipts and credits dated on or after {report.receivedFrom} and before {report.receivedBefore}. Prep, waste and sales are not deducted from actual usage.</p>
    {!!report.errors.length && <p role="alert" className="text-amber-300">{report.errors.join("; ")}</p>}
    {!!report.warnings.length && <p role="alert" className="text-amber-300">{report.warnings.join("; ")}</p>}
    <div className="grid md:grid-cols-4 gap-3">
      <MetricCard label="Opening physical value" value={report.openingValue == null ? "Incomplete" : `$${report.openingValue}`} />
      <MetricCard label="Net food purchases" value={`$${report.netPurchaseCost}`} sub="received date; excludes tax and fees" />
      <MetricCard label="Closing physical value" value={report.closingValue == null ? "Incomplete" : `$${report.closingValue}`} />
      <MetricCard label="Actual Food Cost" value={report.actualFoodCost == null ? "Incomplete" : `$${report.actualFoodCost}`} sub="opening value + purchases − closing value" />
    </div>
    <div className={`${cardCls} p-4 overflow-auto`}><table className="text-sm w-full"><thead><tr>{["Item", "Unit", "Opening qty", "Net purchased qty", "Closing qty", "Actual usage", "Opening value", "Net purchase cost", "Closing value", "Actual Food Cost"].map(h => <th className="text-left p-2 whitespace-nowrap" key={h}>{h}</th>)}</tr></thead><tbody>{report.rows.map(r => <tr key={r.itemCode}>{[r.name, r.baseUnit, r.openingQuantity, r.netPurchaseQuantity, r.closingQuantity, r.actualUsage, r.openingValue, r.netPurchaseCost, r.closingValue, r.actualFoodCost].map((v, i) => <td className="p-2 border-t border-slate-700" key={i}>{v ?? "Incomplete"}</td>)}</tr>)}</tbody></table></div>
    <label className="flex gap-2 text-sm"><input aria-label="Confirm period review" type="checkbox" checked={reviewed} disabled={busy || !!attempt.current} onChange={e => setReviewed(e.target.checked)} />I verified both physical counts and values, and all received purchases and credits for this period have been reviewed and posted.</label>
    {!!report.warnings.length && <label className="flex gap-2 text-sm"><input type="checkbox" checked={overages} disabled={busy || !!attempt.current} onChange={e => setOverages(e.target.checked)} />I reviewed and acknowledge these quantity/value overages.</label>}
    {error && <p role="alert" className="text-red-300">{error} Refresh the report before making a new close request.</p>}
    <button className={btnAcc} disabled={busy || report.status !== "complete" || !reviewed || (!!report.warnings.length && !overages)} onClick={close}>{attempt.current ? "Retry same period close" : report.supersedesClosureId ? "Close replacement period" : "Close actual inventory period"}</button>
  </section>;
}

export function ReopenPeriodForm({ plan, onReopen }) {
  const [reason, setReason] = useState(""), [reviewed, setReviewed] = useState(false);
  const [busy, setBusy] = useState(false), [error, setError] = useState(""), [saved, setSaved] = useState(false);
  const attempt = useRef(null);
  async function reopen() {
    setError("");
    if (!reason.trim() || !reviewed) { setError("Enter the correction reason and review every affected period."); return; }
    if (!attempt.current) attempt.current = { key: crypto.randomUUID(), body: { first_closure_id: plan.firstClosureId,
      expected_plan_hash: plan.planHash, affected_periods_reviewed: true, reason: reason.trim() } };
    setBusy(true);
    try {
      const result = await onReopen(attempt.current.body, attempt.current.key);
      if (result?.status !== "reopened" || !result.event?.id || result.event.plan_snapshot?.planHash !== plan.planHash)
        throw new Error("Reopening was not confirmed. Retry the same request.");
      setSaved(true);
    } catch (e) {
      if ([409, 422].includes(e?.response?.status)) attempt.current = null;
      setError(errorText(e));
    } finally { setBusy(false); }
  }
  return <section className={`${cardCls} p-4 space-y-3`} aria-label="Review inventory correction">
    <h3 className="font-semibold">Review correction · {plan.affectedPeriods.length} affected periods</h3>
    <p className="text-sm">These periods will await review and replacement. Original counts, purchases and reports remain in history. If correcting an opening count shared with the previous period, start by reopening that previous period.</p>
    <ul className="list-disc pl-5 text-sm">{plan.affectedPeriods.map(p => <li key={p.id}>{p.periodStart} to before {p.receivedBefore} · Original Food Cost ${p.actualFoodCost}</li>)}</ul>
    <fieldset disabled={busy || !!attempt.current || saved} className="space-y-3">
      <Field label="Correction reason"><textarea aria-label="Correction reason" className={inpCls} value={reason} onChange={e => setReason(e.target.value)} /></Field>
      <label className="flex gap-2 text-sm"><input aria-label="Review affected periods" type="checkbox" checked={reviewed} onChange={e => setReviewed(e.target.checked)} />I reviewed every affected period and will reclose them in order after correcting the counts or purchases.</label>
    </fieldset>
    {error && <p role="alert" className="text-red-300">{error} Refresh the correction preview if the affected periods changed.</p>}
    {saved ? <p role="status">Periods reopened and confirmed. Original reports preserved.</p> : <button className={btnAcc} disabled={busy || !reviewed || !reason.trim()} onClick={reopen}>{attempt.current ? "Retry same reopening" : "Reopen affected periods"}</button>}
  </section>;
}

export function ScopeHandoffReview({ plan, onAccept }) {
  const [note, setNote] = useState(""), [reviewed, setReviewed] = useState(false);
  const [busy, setBusy] = useState(false), [error, setError] = useState(""), [saved, setSaved] = useState(false);
  const attempt = useRef(null);
  async function accept() {
    setError("");
    if (plan.status !== "ready" || !reviewed || !note.trim()) return;
    if (!attempt.current) attempt.current = { key: crypto.randomUUID(), body: { anchor_closure_id: plan.anchorClosureId,
      target_opening_id: plan.newOpeningSnapshotId, expected_plan_hash: plan.planHash, items_reviewed: true, note: note.trim() } };
    setBusy(true);
    try {
      const result = await onAccept(attempt.current.body, attempt.current.key);
      if (result?.status !== "accepted" || !result.bridge?.id || result.bridge.plan_snapshot?.planHash !== plan.planHash)
        throw new Error("Saved item-list handoff was not confirmed. Retry the same request or review its history.");
      setSaved(true);
    } catch (e) {
      if ([409, 422].includes(e?.response?.status)) attempt.current = null;
      setError(errorText(e));
    } finally { setBusy(false); }
  }
  return <section className={`${cardCls} p-4 space-y-3`} aria-label="Review item-list handoff">
    <h3 className="font-semibold">Item-list handoff · Version {plan.oldScopeRevision} → {plan.newScopeRevision}</h3>
    <p className="text-sm">Same physical count on {plan.countDate}, {timingLabel(plan.timing)}. Retained items carry the exact measured quantity and confirmed total value. Added and removed items need explicit zero balances.</p>
    <p className="text-sm">Old closing value: {plan.oldValue == null ? "Incomplete" : `$${plan.oldValue}`} · New opening value: {plan.newValue == null ? "Incomplete" : `$${plan.newValue}`}</p>
    {!!plan.errors.length && <p role="alert" className="text-amber-200">{plan.errors.join("; ")}</p>}
    <div className="overflow-auto"><table className="text-sm w-full"><thead><tr>{["Item", "Change", "Unit", "Old quantity", "New quantity", "Old value", "New value", "Old locations", "New locations"].map(h => <th key={h} className="text-left p-2">{h}</th>)}</tr></thead><tbody>{plan.rows.map(r => <tr key={r.itemCode}>{[r.name, r.change, r.baseUnit, r.oldQuantity ?? (r.change === "added" ? "Not in old list" : "Incomplete"), r.newQuantity ?? (r.change === "removed" ? "Not in new list" : "Incomplete"), r.oldValue ?? (r.change === "added" ? "Not in old list" : "Incomplete"), r.newValue ?? (r.change === "removed" ? "Not in new list" : "Incomplete"), r.oldLocations ?? "—", r.newLocations ?? "—"].map((v, i) => <td key={i} className="p-2 border-t border-slate-700">{v}</td>)}</tr>)}</tbody></table></div>
    <fieldset disabled={busy || !!attempt.current || saved} className="space-y-3">
      <Field label="Handoff evidence"><input aria-label="Handoff evidence" className={inpCls} value={note} onChange={e => setNote(e.target.value)} /></Field>
      <label className="flex gap-2 text-sm"><input aria-label="Confirm item-list handoff" type="checkbox" checked={reviewed} onChange={e => setReviewed(e.target.checked)} />I verified every retained balance, explicit zero additions/removals and all stock locations.</label>
    </fieldset>
    {error && <p role="alert" className="text-red-300">{error} Refresh this preview if the period or counts changed.</p>}
    {saved ? <p role="status">Item-list handoff saved and confirmed. Use its new opening count for the next period.</p> : <button className={btnAcc} disabled={busy || plan.status !== "ready" || !reviewed || !note.trim()} onClick={accept}>{attempt.current ? "Retry same handoff" : "Accept item-list handoff"}</button>}
  </section>;
}

export function ActualInventoryTab({ restaurantId, view = "counts" }) {
  const [setup, setSetup] = useState(null), [counts, setCounts] = useState([]), [closed, setClosed] = useState([]);
  const [configure, setConfigure] = useState(false), [newCount, setNewCount] = useState(0), [recount, setRecount] = useState(null);
  const [opening, setOpening] = useState(""), [closing, setClosing] = useState(""), [report, setReport] = useState(null);
  const [reopenPlan, setReopenPlan] = useState(null);
  const [handoffs, setHandoffs] = useState([]), [handoffTarget, setHandoffTarget] = useState(""), [handoffPlan, setHandoffPlan] = useState(null);
  const [selectedScope, setSelectedScope] = useState(null);
  const [error, setError] = useState(""), [message, setMessage] = useState(""), [busy, setBusy] = useState(false);
  const mounted = useRef(true), requestEpoch = useRef(0);
  useEffect(() => {
    mounted.current = true;
    Promise.all([api.actualSetup(restaurantId), api.actualCounts(restaurantId), api.actualClosed(restaurantId), api.actualHandoffs(restaurantId)]).then(([s, c, p, b]) => {
      if (mounted.current) { setSetup(s); setSelectedScope(s.scope); setCounts(c); setClosed(p); setHandoffs(b); setConfigure(!s.scope); }
    }).catch(e => mounted.current && setError(errorText(e)));
    return () => { mounted.current = false; requestEpoch.current += 1; };
  }, [restaurantId]);
  async function refreshHistory() {
    const [c, p, b] = await Promise.all([api.actualCounts(restaurantId), api.actualClosed(restaurantId), api.actualHandoffs(restaurantId)]);
    if (mounted.current) { setCounts(c); setClosed(p); setHandoffs(b); }
  }
  async function run(fn) {
    setBusy(true); setError(""); setMessage("");
    try { await fn(); } catch (e) { if (mounted.current) setError(errorText(e)); } finally { if (mounted.current) setBusy(false); }
  }
  async function saveCount(body, key) {
    const saved = await api.actualSaveCount(restaurantId, body, key);
    if (!saved?.header?.id) throw new Error("Saved count was not confirmed.");
    refreshHistory().catch(e => mounted.current && setError(`Count saved; history refresh failed: ${errorText(e)}`));
    return saved;
  }
  async function loadReport() {
    const epoch = ++requestEpoch.current;
    await run(async () => { const r = await api.actualReport(restaurantId, opening, closing); if (mounted.current && epoch === requestEpoch.current) setReport(r); });
  }
  async function closeReport(body, key) {
    setBusy(true);
    try {
      const result = await api.actualClose(restaurantId, body, key);
      if (result.status === "historical") throw new Error("Your earlier close was saved, but that report has since been reopened. Review the period history before continuing.");
      if (result.status !== "closed" || !result.closure?.id || result.closure.report_snapshot?.reportHash !== body.expected_report_hash) throw new Error("Saved closed report was not confirmed. Retry the same request.");
      if (mounted.current) { setReport(null); setMessage("Actual inventory period closed and confirmed. Its counts, values and purchases are frozen."); }
      refreshHistory().catch(e => mounted.current && setError(`Period closed; history refresh failed: ${errorText(e)}`));
    } finally { if (mounted.current) setBusy(false); }
  }
  async function loadReopen(id) {
    await run(async () => { const plan = await api.actualReopenPreview(restaurantId, id); if (mounted.current) setReopenPlan(plan); });
  }
  async function reopenReports(body, key) {
    const result = await api.actualReopen(restaurantId, body, key);
    if (result?.status !== "reopened" || !result.event?.id || result.event.plan_snapshot?.planHash !== body.expected_plan_hash)
      throw new Error("Reopening was not confirmed. Retry the same request.");
    if (mounted.current) { setReport(null); setMessage("Periods reopened. Correct counts or post the held purchases, then replace each report from oldest to newest."); }
    refreshHistory().catch(e => mounted.current && setError(`Periods reopened; history refresh failed: ${errorText(e)}`));
    return result;
  }
  async function loadHandoff() {
    await run(async () => { const plan = await api.actualHandoffPreview(restaurantId, latestActive.id, handoffTarget); if (mounted.current) setHandoffPlan(plan); });
  }
  async function acceptHandoff(body, key) {
    const result = await api.actualAcceptHandoff(restaurantId, body, key);
    if (result?.status === "historical") throw new Error("The earlier handoff was saved, but its anchor has been reopened. Review period history and rebuild the handoff.");
    if (result?.status !== "accepted" || !result.bridge?.id || result.bridge.plan_snapshot?.planHash !== body.expected_plan_hash)
      throw new Error("Saved handoff was not confirmed. Retry the same request.");
    if (mounted.current) { requestEpoch.current += 1; setReport(null); setMessage("Item-list handoff confirmed. Use the new opening count to continue actual inventory."); }
    refreshHistory().catch(e => mounted.current && setError(`Handoff saved; history refresh failed: ${errorText(e)}`));
    return result;
  }
  const supersededCounts = new Set(counts.filter(c => c.corrects_snapshot_id).map(c => c.corrects_snapshot_id));
  const protectedCounts = new Set(closed.filter(p => p.period_status === "closed").flatMap(p => [p.opening_snapshot_id, p.closing_snapshot_id]));
  handoffs.filter(b => b.active).forEach(b => { protectedCounts.add(b.old_closing_snapshot_id); protectedCounts.add(b.new_opening_snapshot_id); });
  const pending = closed.filter(p => p.period_status === "reopened").sort((a, b) => a.period_start.localeCompare(b.period_start));
  const countScope = recount?.scope || selectedScope;
  const latestActive = closed.filter(p => p.period_status === "closed").sort((a, b) => b.period_end_exclusive.localeCompare(a.period_end_exclusive))[0];
  return <div className="space-y-5"><PageTitle>{view === "counts" ? "Actual Inventory · Physical Counts" : "Actual Inventory · Food Cost"}</PageTitle>
    <p className="text-sm text-slate-400">Track 1 uses purchased inventory only and explicit count values. Prep and sales explain this baseline separately.</p>
    {view === "counts" && setup && <StaffCountReview key={restaurantId} restaurantId={restaurantId} scope={setup.scope} onAccepted={() => refreshHistory().catch(e => mounted.current && setError(`Count accepted; history refresh failed: ${errorText(e)}`))} />}
    {error && <p role="alert" className="text-red-300">{error}</p>}{message && <p role="status" className="text-emerald-300">{message}</p>}
    {!!pending.length && <p role="alert" className="text-amber-200">{pending.length} reopened periods await replacement. Start with {pending[0].period_start} to before {pending[0].period_end_exclusive}. These original totals are historical until reviewed replacements are closed.</p>}
    {!setup ? <p>Loading actual inventory…</p> : <>
      <div className="flex gap-3 flex-wrap"><button className={btnGhost} disabled={busy} onClick={() => setConfigure(!configure)}>{configure ? "Hide scope setup" : "Review / version count scope"}</button>
        {view === "counts" && setup.scope && <button className={btnGhost} onClick={() => { setRecount(null); setNewCount(n => n + 1); }}>Start another count</button>}</div>
      {configure && <ScopeForm key={setup.scope?.header.id || "initial"} setup={setup} onSave={async (body, key) => {
        const s = await api.actualScope(restaurantId, body, key); if (!s?.header?.id) throw new Error("Scope confirmation was not saved.");
        if (mounted.current) { setSetup(old => ({ ...old, scope: s, scopes: [s.header, ...(old.scopes || []).filter(h => h.id !== s.header.id)] })); setSelectedScope(s); setConfigure(false); setRecount(null); setNewCount(n => n + 1); }
      }} />}
      {view === "counts" && countScope && <Field label="Purchased-item list for this count"><select aria-label="Count item-list version" className={inpCls} disabled={busy} value={countScope.header.id} onChange={e => {
        const id = e.target.value; run(async () => { const s = await api.actualScopeDetails(restaurantId, id); if (mounted.current) { setSelectedScope(s); setRecount(null); setNewCount(n => n + 1); } });
      }}>{(setup.scopes || [setup.scope.header]).map(s => <option key={s.id} value={s.id}>Version {s.revision} · {s.note}</option>)}</select></Field>}
      {view === "counts" && countScope && <PhysicalCountForm key={`${countScope.header.id}:${newCount}:${recount?.header.id || "new"}`} scope={countScope} onSave={saveCount} onRecount={recount} unitProfiles={setup.unitProfiles || []} />}
      {view === "counts" && <div className={`${cardCls} p-4 space-y-2`}><h3 className="font-semibold">Physical count history</h3>{counts.map(c => <div className="flex gap-3 text-sm items-center" key={c.id}><span>{c.count_date} · {timingLabel(c.timing)} · {c.status}{supersededCounts.has(c.id) ? " · replaced by recount" : protectedCounts.has(c.id) ? " · protected by closed period / handoff" : ""}</span><button className={btnGhost} disabled={busy || supersededCounts.has(c.id) || protectedCounts.has(c.id)} onClick={() => run(async () => { setRecount(await api.actualCount(restaurantId, c.id)); setNewCount(n => n + 1); })}>Append recount</button></div>)}</div>}
      {view === "report" && <>
        <section className={`${cardCls} p-4 space-y-3`}><h3 className="font-semibold">Change the purchased-item list</h3>
          <p className="text-sm">After closing the old list, create the new list in Enter Counts and record its opening count at the same physical boundary. Carry retained balances exactly; confirm zero for added items and remove only zero-balance items. Existing stock needs reconciliation before changing lists.</p>
          {latestActive ? <><p className="text-sm">Handoff starts from the active period ending before {latestActive.period_end_exclusive}.</p>
            <Field label="New list opening count"><select aria-label="Handoff opening count" className={inpCls} disabled={busy} value={handoffTarget} onChange={e => { setHandoffTarget(e.target.value); setHandoffPlan(null); }}><option value="">Choose the new opening count</option>{counts.filter(c => c.status === "complete" && !supersededCounts.has(c.id)).map(c => <option key={c.id} value={c.id}>{c.count_date} · {timingLabel(c.timing)} · List version {c.scope_revision}</option>)}</select></Field>
            <button className={btnGhost} disabled={busy || !handoffTarget} onClick={loadHandoff}>Preview / refresh item-list handoff</button></> : <p className="text-sm">Close the first actual-inventory period before creating a list handoff.</p>}
          {handoffPlan && <ScopeHandoffReview key={handoffPlan.planHash} plan={handoffPlan} onAccept={acceptHandoff} />}
          {!!handoffs.length && <details><summary className="cursor-pointer">Item-list handoff history</summary>{handoffs.map(b => <p className="text-sm" key={b.id}>Version {b.plan_snapshot.oldScopeRevision} → {b.plan_snapshot.newScopeRevision} · {b.plan_snapshot.countDate} · {b.active ? "Active handoff" : "Historical — anchor reopened"} · {b.note}</p>)}</details>}
        </section>
        <div className={`${cardCls} p-4 grid md:grid-cols-3 gap-3`}>
          {[['Opening physical count', opening, value => { requestEpoch.current += 1; setOpening(value); setReport(null); }], ['Closing physical count', closing, value => { requestEpoch.current += 1; setClosing(value); setReport(null); }]].map(([label, value, setter]) => <Field label={label} key={label}><select aria-label={label} className={inpCls} disabled={busy} value={value} onChange={e => setter(e.target.value)}><option value="">Choose a count</option>{counts.filter(c => !supersededCounts.has(c.id)).map(c => <option key={c.id} value={c.id}>{c.count_date} · {timingLabel(c.timing)} · {c.status} · {c.id.slice(0, 8)}</option>)}</select></Field>)}
          <button className={btnAcc} disabled={busy || !opening || !closing} onClick={loadReport}>Preview actual usage and Food Cost</button>
        </div>
        {report && <ActualPeriodView key={report.reportHash} report={report} onClose={closeReport} busy={busy} />}
        {reopenPlan && <><button className={btnGhost} disabled={busy} onClick={() => loadReopen(reopenPlan.firstClosureId)}>Refresh correction preview</button><ReopenPeriodForm key={reopenPlan.planHash} plan={reopenPlan} onReopen={reopenReports} /></>}
        <div className={`${cardCls} p-4 space-y-3`}><h3 className="font-semibold">Inventory period history</h3>{closed.map(p => <details key={p.id}><summary className="cursor-pointer">{p.period_start} to before {p.period_end_exclusive} · {p.period_status === "closed" ? "Active closed" : p.period_status === "reopened" ? "Reopened — awaiting replacement" : "Superseded — original report"} · Food Cost ${p.report_snapshot.actualFoodCost}</summary>
          {p.reopen_reason && <p className="text-sm">Correction reason: {p.reopen_reason} · Reopened by {p.reopened_by}</p>}
          {p.period_status === "closed" && <button className={btnGhost} disabled={busy} onClick={() => loadReopen(p.id)}>Review correction / reopening</button>}
          <p className="text-xs text-slate-400">This saved report retains its original counts, values and purchase references. Report fingerprint: {p.report_snapshot.reportHash}</p><div className="overflow-auto"><table className="text-sm w-full"><thead><tr><th>Item</th><th>Actual usage</th><th>Unit</th><th>Actual Food Cost</th></tr></thead><tbody>{p.report_snapshot.rows.map(r => <tr key={r.itemCode}><td>{r.name}</td><td>{r.actualUsage}</td><td>{r.baseUnit}</td><td>{r.actualFoodCost}</td></tr>)}</tbody></table></div></details>)}</div>
      </>}
    </>}
  </div>;
}
