import React, { useEffect, useMemo, useState } from "react";
import * as api from "../lib/api";
import { RESTAURANTS, todayISO } from "../lib/calc";
import { loadManagerOverview, overviewContext, overviewStorage, rememberedOverview } from "../lib/managerOverview";
import { PageTitle, cardCls, inpCls, btnGhost } from "./common";

const labels = { open: "Open", in_progress: "In progress", complete: "Complete",
  needs_review: "Manager review required", unavailable: "Progress not confirmed" };
const loading = () => ({ state: "loading" });
export function ManagerOverviewTab({ rid, user, onOpenCounts, onOpenPrep, onOpenHandoff, readApi = api }) {
  const scope = JSON.stringify([user?.id, rid]);
  const initial = useMemo(() => ({ ...rememberedOverview(overviewStorage(), user?.id, rid, todayISO()), scope }), [scope, rid, user?.id]);
  const [selected, setSelected] = useState(initial);
  const selection = selected.scope === scope ? selected : initial;
  const setSelection = patch => setSelected({ ...selection, ...patch });
  const [refresh, setRefresh] = useState(0), [view, setView] = useState(null);
  const context = overviewContext(rid, selection.day, selection.track, user);
  const key = context?.key || "";
  const countsEnabled = readApi.actualInventoryEnabled === true, prepEnabled = readApi.prepExecutionEnabled === true;
  useEffect(() => {
    let active = true;
    if (!key) { setView(null); return; }
    try { overviewStorage()?.setItem(`manager-overview:${user.id}:${rid}`, JSON.stringify({ day: selection.day, track: selection.track })); } catch { /* Optional navigation preference. */ }
    setView({ key, counts: loading(), prep: loading() });
    loadManagerOverview(context, readApi, (section, value) => {
      if (active) setView(prior => prior?.key === key ? { ...prior, [section]: value } : prior);
    });
    return () => { active = false; };
    // The key includes actor, authority scope, restaurant, date and track.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key, refresh, readApi, countsEnabled, prepEnabled]);
  const currentView = view?.key === key ? view : null;
  const count = currentView?.counts || loading(), prep = currentView?.prep || loading();
  const restaurant = RESTAURANTS.find(r => r.id === rid);
  return <div data-testid="manager-overview" className="fade-slide-in">
    <PageTitle right={<button className={btnGhost} disabled={!context} onClick={() => setRefresh(n => n + 1)}>Refresh manager overview</button>}>Manager overview</PageTitle>
    <p>{restaurant?.name || "Choose a restaurant"} · Read-only overview. Open the original workflow to act.</p>
    <div className="flex gap-4 flex-wrap my-4">
      <label>Prep date <input className={inpCls} aria-label="Manager overview date" type="date" value={selection.day} onChange={e => setSelection({ day: e.target.value })}/></label>
      <label>Prep track <select className={inpCls} aria-label="Manager overview track" value={selection.track} onChange={e => setSelection({ track: e.target.value })}>
        <option value="bulk">Bulk Prep</option><option value="daily">Daily Prep</option>
      </select></label>
    </div>
    {!context ? <p role="alert">Choose a valid date and a restaurant available to your personal manager or owner account.</p> : <>
      <div className="grid gap-4 md:grid-cols-2">
        <section className={`${cardCls} p-5`} aria-label="Recorded physical count">
          <h2 className="font-bold mb-2">Recorded physical count</h2>
          <p className="text-sm text-slate-400">Purchased items · Track 1 · latest current count on or before {selection.day}. This is not live on-hand inventory.</p>
          {count.state === "loading" ? <p role="status">Loading count history…</p> : count.state === "unavailable" ? <p role="status">{count.message}</p> : count.count ? <>
            <p className="mt-3 font-semibold">{count.count.date} · {count.count.status === "complete" ? "Complete" : "Incomplete"}</p>
            <p>{count.count.timing === "after_receipts" ? "After" : "Before"} that day’s receipts · item-list revision {count.count.scopeRevision}</p>
            <p className="text-sm text-slate-400">View explicit count values in Actual Inventory. This view does not calculate Food Cost.</p>
          </> : <p className="mt-3">No physical count is recorded for this date or earlier. Inventory value is unavailable.</p>}
          <button className={`${btnGhost} mt-4`} disabled={!countsEnabled} onClick={() => onOpenCounts?.({ rid })}>Open Actual Inventory</button>
        </section>
        <section className={`${cardCls} p-5`} aria-label="Dated prep work">
          <h2 className="font-bold mb-2">{selection.track === "bulk" ? "Bulk Prep" : "Daily Prep"} · {selection.day}</h2>
          <p className="text-sm text-slate-400">Track 2 explains usage. Assignment, reported production, manager review and stock posting remain separate.</p>
          {prep.state === "loading" ? <p role="status">Loading dated prep work…</p> : prep.state === "unavailable" ? <p role="status">{prep.message}</p> : <>
            <p className="mt-3 font-semibold">{!prep.hasDraft ? "No dated plan saved" : prep.status === "released" ? "Released plan" : "Draft plan"} · revision {prep.revision}</p>
            {!prep.progressAvailable && <p>Task progress is not confirmed by this read.</p>}
            {prep.historicalReviews > 0 && <p>Earlier task versions have {prep.historicalReviews} production record(s) requiring manager review. Open the dated workflow to review the history.</p>}
            {!prep.tasks.length ? <p>No included prep tasks are recorded. This does not confirm that prep is complete.</p> : <ul className="mt-3 space-y-2">{prep.tasks.map(task => <li key={task.id}>
              <strong>{task.name}</strong><span> · {labels[task.state]}</span>
            </li>)}</ul>}
          </>}
          <button className={`${btnGhost} mt-4`} disabled={!prepEnabled} onClick={() => onOpenPrep?.({ rid, day: selection.day, track: selection.track })}>Open dated prep workflow</button>
        </section>
      </div>
      {readApi.managerHandoffEnabled && <button className={`${btnGhost} mt-4`} onClick={() => onOpenHandoff?.({ rid, day: selection.day, track: selection.track })}>Open dated manager handoff</button>}
      <p className="mt-4 text-sm text-slate-400">Counts and task history are shown as currently recorded, including corrections. They do not reconstruct what was known on a past date.</p>
    </>}
  </div>;
}
