import React, { useEffect, useState } from "react";
import * as api from "../lib/api";
import { btnGhost, cardCls } from "./common";
const coverageNames = { waste: "Waste", containers: "Containers", tasks: "Task links", staffProduction: "Staff acceptance", periods: "Saved reports" };
const actionNames = { void_fill: "Preview an unused fill void", undo: "Preview the latest movement reversal", undo_waste: "Preview paired waste reversal" };

export function PrepCorrectionReview({ restaurantId, eventId, onResult }) {
  const [data, setData] = useState(null), [error, setError] = useState(""), [attempt, setAttempt] = useState(0);
  useEffect(() => {
    let active = true;
    setData(null); setError(""); onResult(null);
    api.nativePrepCorrectionReview(restaurantId, eventId).then(r => {
      const expectedStore = ({ papa_leonis: "papa" }[restaurantId] || restaurantId);
      if (r?.store_id !== expectedStore || r.selectedEventId !== eventId || r.readOnly !== true || r.track1Writeback !== false
        || !["held", "eligible_for_preview"].includes(r.gate?.status)
        || ![r.lots, r.preparedInputHistory, r.containers, r.wasteHistory, r.taskLinks, r.staffDecisions, r.savedPeriods].every(Array.isArray)
        || !r.coverage || !Object.keys(coverageNames).every(k => ["installed", "not_installed"].includes(r.coverage[k]))
        || !r.containers.every(c => c?.fill && typeof c.fill.id === "string" && Array.isArray(c.moves))
        || !/^[0-9a-f]{64}$/.test(r.reviewHash || "")) throw new Error("Dependency review was not confirmed. Refresh it before correction.");
      if (active) { setData(r); onResult({ ...r, restaurantId }); }
    }).catch(e => { if (active) { setError(typeof e?.response?.data?.detail === "string" ? e.response.data.detail : e.message || "Dependency review failed"); onResult(null); } });
    return () => { active = false; };
  }, [restaurantId, eventId, attempt, onResult]);
  return <aside className={`${cardCls} space-y-2`} aria-label="Prep correction dependencies">
    <h3 className="font-semibold">Correction dependencies</h3>
    {!data && !error && <p>Loading linked records…</p>}
    {error && <p role="alert">{error}</p>}
    <button className={btnGhost} onClick={() => { onResult(null); setData(null); setAttempt(v => v + 1); }}>Refresh dependency review</button>
    {data && <>
      <p>{data.gate.reason}</p>
      <p>Track 1 purchased inventory and Food Cost remain unchanged. This review does not approve a correction.</p>
      <p>Coverage: {Object.entries(data.coverage).map(([k, v]) => `${coverageNames[k] || k}: ${v === "installed" ? "available for review" : "not set up"}`).join("; ")}.</p>
      <h4>Affected recorded lots</h4>
      <ul>{data.lots.map(l => <li key={l.id}>{l.id} · {l.kind} · revision {l.revision} · {l.recordedAllocatedQuantity} {l.base_unit} allocated. Historical links may already be reversed.</li>)}</ul>
      <h4>Prepared ingredient allocation history</h4>
      <ul>{data.preparedInputHistory.map(m => <li key={m.id}>{m.event_id} · {m.side} · {m.quantity} {m.base_unit} from {m.source_batch_id}.</li>)}</ul>
      <h4>Containers and movements</h4>
      {data.containers.length === 0 && <p>No linked container fills.</p>}
      {data.containers.map(c => <article key={c.fill.id}><p>{c.fill.label} · {c.fill.id} · storage {c.storage}, service {c.service} {c.fill.base_unit}.</p>
        <ul>{c.moves.map(m => <li key={m.id}>{m.id} · {m.action} · {m.performed_at}</li>)}</ul>
        <p>{c.nextPreviewAction ? `${actionNames[c.nextPreviewAction] || "Review supported actions"}. ` : ""}{c.reviewNote}</p></article>)}
      <h4>Waste history</h4>
      <ul>{data.wasteHistory.map(w => <li key={w.id}>{w.id} · {w.kind} · {w.current ? "latest revision" : "preserved history"}. Container waste requires paired reversal.</li>)}</ul>
      <h4>Task links and accepted staff records</h4>
      <ul>{data.taskLinks.map(t => <li key={t.id}>Task {t.task_id} · link {t.id} · {t.needsReconciliation ? "reconciliation needed now" : "review reconciliation after correction"}{!t.reconciliationSupported && "; progress migration unavailable"}.</li>)}</ul>
      <p>{data.staffDecisions.length} accepted staff records remain immutable.</p>
      <h4>Saved analytical periods</h4>
      <ul>{data.savedPeriods.map(p => <li key={p.id}>{p.id} · {p.reopened ? "reopened history" : "active"} · {p.freshness.status}. {p.effect}</li>)}</ul>
      <p>Resolve supported downstream allocations before their source lot. Each reversal needs its own preview; later activity may hold it. No automatic cascade is available.</p>
    </>}
  </aside>;
}
