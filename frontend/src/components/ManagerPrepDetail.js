import React, { useEffect, useState } from "react";
import * as api from "../lib/api";
import { overviewContext, prepQuantityOverview } from "../lib/managerOverview";
import { readStateWithDeadline } from "../lib/stateRead";
import { loadAssignmentOverview } from "../lib/managerAssignmentOverview";
import { loadManagerTakeover } from "../lib/managerTakeover";
import { ManagerAssignmentOverview } from "./ManagerAssignmentOverview";
import { cardCls } from "./common";

// Read-only detail for the overview's selected store/date/track: native planned, reviewed and
// remaining quantities, recorded assignments and the previous submitted note. GET readers only.
const loading = () => ({ state: "loading" });
const labels = { open: "Open", in_progress: "In progress", complete: "Finished",
  needs_review: "Review required", unavailable: "Progress not confirmed" };
const trackLabel = { daily: "Daily Prep", bulk: "Bulk Prep" };

export function ManagerPrepDetail({ rid, day, track, user, generation = 0, readApi = api }) {
  const [view, setView] = useState(null);
  const context = overviewContext(rid, day, track, user);
  const key = JSON.stringify([context?.key || "", generation, readApi.prepExecutionEnabled === true,
    readApi.staffPrepTasksEnabled === true, readApi.managerHandoffEnabled === true]);
  useEffect(() => {
    let active = true;
    if (!context) { setView(null); return; }
    setView({ key, readApi, prep: loading(), assignments: loading(), note: loading() });
    const receive = (section, value) => {
      if (active) setView(prior => prior?.key === key && prior.readApi === readApi ? { ...prior, [section]: value } : prior);
    };
    async function prepRead() {
      if (readApi.prepExecutionEnabled !== true) return { state: "unavailable", message: "Dated prep unavailable: capability is disabled." };
      try {
        const value = await readStateWithDeadline(() => readApi.prepExecution(context.rid, context.day, context.track), "Overview read timed out.");
        return { ...prepQuantityOverview(value, context), readAt: new Date().toISOString() };
      } catch { return { state: "unavailable", message: "Dated prep not confirmed: read failed or source mismatched. Refresh." }; }
    }
    prepRead().then(async prep => {
      receive("prep", prep);
      if (active) receive("assignments", await loadAssignmentOverview(context, prep, readApi));
    });
    loadManagerTakeover(context.rid, context.day, context.track, user, readApi).then(note => receive("note", note));
    return () => { active = false; };
    // key includes actor/authority, store/date/track, refresh generation and capabilities.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key, readApi]);
  if (!context) return null;
  const current = view?.key === key && view.readApi === readApi ? view : null;
  const prep = current?.prep || loading(), assignments = current?.assignments || loading(), note = current?.note || loading();
  return <div data-testid="manager-prep-detail" className="mt-6 space-y-4">
    <h2 className="font-bold">Prep quantities and assignments · {trackLabel[track]} · {day}</h2>
    <p className="text-sm text-slate-400">Remaining against reviewed output is not an instruction to produce. Pending reports and physical stock require manager review before directing more prep.
      Pending and rejected reports do not contribute to reviewed output. This view does not read reports or confirm that none are pending.</p>
    <section className={cardCls + " p-5"} aria-label="Prep quantities"><h3 className="font-semibold">Planned, reviewed and remaining</h3>
      {prep.state === "loading" ? <p role="status">Loading dated prep…</p> : prep.state !== "ready" ? <p role="status">{prep.message}</p> : <>
        <p>{!prep.hasDraft ? "No dated plan saved" : prep.status === "released" ? "Released plan" : "Draft plan"} · execution revision {prep.revision} · local read {prep.readAt}</p>
        <p className="text-sm text-slate-400">Plan {prep.draftVersionId || "none"}. Each section has its own read; this is not an atomic snapshot.</p>
        {!prep.progressAvailable && <p>Task progress and quantities not confirmed: native progress is unsupported.</p>}
        {prep.historicalReviews > 0 && <p>Earlier task versions have {prep.historicalReviews} production record(s) requiring review.</p>}
        {!prep.tasks.length && <p>No included tasks recorded. This does not confirm that prep is complete.</p>}
        <ul>{prep.tasks.map(t => <li key={t.id} className="my-4"><strong>{t.name}</strong> · {labels[t.state]}
          {t.quantityState === "unavailable" ? <p>Quantities not confirmed. Refresh and review native evidence.</p> : <>
            <p>Planned: {t.planned} {t.unit} · Reviewed recorded output: {t.reviewed} {t.unit}</p>
            {t.quantityState === "review_required" ? <p>Review required · Remaining: Not confirmed pending native reconciliation.</p> : <>
              <p>Remaining: {t.remaining} {t.unit}{t.excess !== "0" ? " · Above plan: " + t.excess + " " + t.unit : ""}</p>
              {t.closed && t.remaining !== "0" && <p>Finished with shortfall: {t.remaining} {t.unit}</p>}
            </>}
          </>}
          <details><summary>Read-only source details for {t.name}</summary>
            <p>Task {t.id} · Product {t.productId} · Recipe version {t.recipeVersionId} · Unit profile {t.profileId} · Planning version {t.planningVersionId}</p>
            {t.links?.map(l => <p key={l.execution_id}>Link {l.execution_id} · Batch root {l.batch_root_id} · Product version {l.product_version_id} · Acknowledged {l.acknowledged_batch_event_id} · Effective {l.effective_batch_event_id}{l.needs_review ? " · Review required" : ""}</p>)}
          </details>
        </li>)}</ul>
      </>}
    </section>
    <ManagerAssignmentOverview value={assignments}/>
    <section className={cardCls + " p-5"} aria-label="Previous submitted note"><h3 className="font-semibold">Previous submitted note</h3>
      <p className="text-sm text-slate-400">Reading does not accept responsibility or confirm readiness. Notes use the native date and track; no AM/PM interpretation is added.</p>
      {note.state === "loading" ? <p role="status">Loading previous note…</p> : note.state !== "ready" ? <p role="status">{note.message}</p> : <>
        <p>Local read {note.readAt}</p>
        {note.previous ? <><p>{note.previous.business_date} · revision {note.previous.revision} · submitted · Note {note.previous.id}</p>
          {note.older && <p>Gap warning: this note is older than the previous calendar day.</p>}
          <p>{note.previous.summary}</p><p>{note.previous.next_shift_note}</p>
        </> : <p>No previous submitted note confirmed. This does not mean ready.</p>}
        {note.currentStatus === "draft" && <p>A note for the selected date is draft, not submitted.</p>}
      </>}
    </section>
    <p className="text-sm text-slate-400">Current recorded evidence, including corrections; not a reconstruction of what was known on the selected date. No stock balance or Food Cost is calculated here.</p>
  </div>;
}
