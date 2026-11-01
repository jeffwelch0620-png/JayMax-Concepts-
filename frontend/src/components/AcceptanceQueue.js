import React, { useEffect, useRef, useState } from "react";
import * as api from "../lib/api";
import { todayISO } from "../lib/calc";
import { prepTracks } from "../lib/prepTracks";
import { cardCls, inpCls, btnGhost } from "./common";
import { StaffProductionDecisions } from "./StaffPrepProduction";
import { StaffPrepCountReview } from "./StaffPrepCounts";
import { SHORTAGE_REASONS } from "./ShortageReport";

const detail = e => (typeof e?.response?.data?.detail === "string" ? e.response.data.detail : e?.message || "The queue wasn't loaded.");
const clock = iso => (iso ? new Date(iso).toLocaleTimeString([], { hour: "numeric", minute: "2-digit" }) : "");

// Acceptance queue (Jeff 2026-10-30): what staff sent in and is waiting on a manager. A BOH Shift
// Leader or above accepts; a Kitchen Manager or above sends work back or reassigns the task. Each
// item is decided on its own review below, which applies the same rule.
export function AcceptanceQueue({ rid, drafts }) {
  const [day, setDay] = useState(todayISO()), [data, setData] = useState(null), [error, setError] = useState(""), [epoch, setEpoch] = useState(0);
  const reads = useRef(0);
  useEffect(() => {
    let active = true;
    const n = ++reads.current;
    const current = () => active && reads.current === n;
    setData(null); setError("");
    api.acceptanceQueue(rid, day)
      .then(q => { if (!current()) return; if (q?.day !== day || !q.waiting || !Array.isArray(q.shortages)) throw new Error("The queue was not confirmed for this date."); setData(q); })
      .catch(e => current() && setError(detail(e)));
    return () => { active = false; };
  }, [rid, day, epoch]);

  const waiting = data ? data.waiting.output + data.waiting.prep_counts + data.waiting.nightly_counts : 0;
  return (
    <div data-testid="acceptance-queue">
      <section className={`${cardCls} p-4 mb-4`} aria-label="Waiting for a manager">
        <div className="flex items-center gap-3 flex-wrap mb-2">
          <h3 className="font-semibold">Waiting for a manager</h3>
          <input className={inpCls} type="date" aria-label="Queue date" value={day} onChange={e => setDay(e.target.value)} />
          <button className={btnGhost} onClick={() => setEpoch(n => n + 1)}>Refresh</button>
        </div>
        {error && <p role="alert" className="text-red-400 text-sm">{error}</p>}
        {data && <>
          <p className="text-sm" data-testid="queue-summary">{waiting === 0 ? "Nothing waiting." :
            `${data.waiting.output} output report${data.waiting.output === 1 ? "" : "s"} · ${data.waiting.prep_counts} prep count${data.waiting.prep_counts === 1 ? "" : "s"} · ${data.waiting.nightly_counts} nightly count${data.waiting.nightly_counts === 1 ? "" : "s"}`}</p>
          <p className="text-xs text-slate-400 mt-1">{data.can_send_back ? "You can accept work, send it back and reassign tasks."
            : data.can_accept ? "You can accept work. Sending work back or reassigning a task needs a Kitchen Manager or above."
            : "Accepting staff work needs a BOH Shift Leader or above."}</p>
          {data.waiting.nightly_counts > 0 && <p className="text-xs text-slate-400 mt-1">Nightly counts are accepted in Actual Inventory → Counts.</p>}
          {!!data.output.length && <ul className="text-sm mt-2" data-testid="queue-output">{data.output.map(o =>
            <li key={o.id}>{clock(o.recorded_at)} · {o.staff_name}{o.identity_verified ? "" : " (claimed)"} · {o.task_name || "Prep task"} · {o.track}</li>)}</ul>}
        </>}
      </section>
      {!!data?.shortages.length && <section className={`${cardCls} p-4 mb-4`} aria-label="Shortages reported" data-testid="queue-shortages">
        <h3 className="font-semibold">Shortages reported</h3>
        <p className="text-xs text-slate-400">Notes from cooks. They don't change counts, pars or production.</p>
        <ul className="text-sm">{data.shortages.map(r => <li key={r.id}>{clock(r.reported_at)} · {r.staff_name} · {r.task_snapshot?.name}: {SHORTAGE_REASONS.find(x => x.id === r.reason)?.label || r.reason}{r.short_quantity ? ` (${Number(r.short_quantity)} ${r.task_snapshot?.source_unit || ""} short)` : ""}. {r.note}</li>)}</ul>
      </section>}
      {data && api.staffPrepProductionEnabled && prepTracks(rid).map(t =>
        <StaffProductionDecisions key={`${rid}:${day}:${t.id}:${epoch}`} rid={rid} day={day} track={t.id} drafts={drafts} />)}
      {data && api.staffPrepCountsEnabled && data.waiting.prep_counts > 0 && <StaffPrepCountReview key={`${rid}:counts:${epoch}`} rid={rid} drafts={drafts} />}
    </div>
  );
}
