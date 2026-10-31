import React, { useEffect, useRef, useState } from "react";
import * as api from "../lib/api";
import { Field, cardCls, inpCls, btnAcc, btnGhost } from "./common";
import { todayISO } from "../lib/calc";

// Station board (Jeff 2026-10-30). The Shift Leader puts each person on a station at shift start
// and moves them during the shift; every stint is kept for station and per-employee metrics.
// A cook's task queue is their station's unassigned tasks plus anything assigned to them by name.
// A Kitchen Manager sets which station normally makes each prep item.

const detail = e => { const d = e?.response?.data?.detail; return typeof d === "string" ? d : Array.isArray(d) ? d.map(x => x.msg).join("; ") : e.message || "Request failed"; };
const clock = iso => iso ? new Date(iso).toLocaleTimeString([], { hour: "numeric", minute: "2-digit" }) : "";

export function StationBoard({ rid }) {
  const day = todayISO();
  const [board, setBoard] = useState(null), [error, setError] = useState(""), [busy, setBusy] = useState(false), [epoch, setEpoch] = useState(0);
  const attempt = useRef(null), reads = useRef(0);
  useEffect(() => {
    // A move bumps `reads`, so a board read still in flight when it starts can't overwrite the move's newer board.
    let active = true;
    const n = ++reads.current;
    const current = () => active && reads.current === n;
    api.stationBoard(rid, day).then(b => current() && setBoard(b)).catch(e => current() && setError(detail(e)));
    return () => { active = false; };
  }, [rid, day, epoch]);

  // One move at a time; a retry after a lost response replays the same request.
  async function move(staff_member_id, station_code, reason = "moved") {
    const body = { staff_member_id, station_code, reason };
    if (!attempt.current || JSON.stringify(attempt.current.body) !== JSON.stringify(body)) attempt.current = { key: crypto.randomUUID(), body };
    setBusy(true); setError(""); reads.current++;
    try { const r = await api.moveStation(rid, day, body, attempt.current.key); attempt.current = null; if (r?.board) setBoard(r.board); }
    catch (e) { if ([400, 403, 404, 409, 422].includes(e?.response?.status)) attempt.current = null; setError(detail(e)); }
    finally { setBusy(false); }
  }

  async function setDefault(product_id, station_code) {
    setBusy(true); setError("");
    try { await api.setProductStation(rid, product_id, { station_code: station_code || null, note: "Set on the station board" }, crypto.randomUUID()); setEpoch(n => n + 1); }
    catch (e) { setError(detail(e)); }
    finally { setBusy(false); }
  }

  if (!board) return error ? <p role="alert">{error}</p> : <p>Loading stations…</p>;
  const onStation = Object.fromEntries(board.open.map(s => [s.staff_member_id, s]));
  const active = board.stations.filter(s => s.active);
  return <div className="space-y-4" data-testid="station-board">
    {error && <p role="alert">{error}</p>}
    <section className={`${cardCls} p-4 space-y-3`} aria-label="Who is on which station">
      <h3 className="font-semibold">Stations today</h3>
      <div className="grid md:grid-cols-3 gap-3">
        {active.map(st => {
          const people = board.open.filter(s => s.station_code === st.code);
          return <div key={st.code} className="border border-slate-700 rounded-lg p-3" data-testid={`station-${st.code}`}>
            <p className="font-semibold">{st.name} <span className="text-xs text-slate-400">{st.department}</span></p>
            {people.length ? people.map(p => <p key={p.stint_id} className="text-sm">{p.staff_name} · since {clock(p.started_at)}</p>) : <p className="text-sm text-slate-400">Nobody: its tasks stay with the Shift Leader</p>}
          </div>;
        })}
      </div>
    </section>
    <section className={`${cardCls} p-4 space-y-2`} aria-label="Put people on stations">
      <h3 className="font-semibold">Crew</h3>
      {board.roster.map(m => {
        const current = onStation[m.id];
        return <div key={m.id} className="flex flex-wrap items-end gap-3">
          <span className="min-w-[160px]">{m.name}{m.active ? "" : " (inactive: take off station)"}</span>
          <Field label="Station"><select aria-label={`Station for ${m.name}`} className={inpCls} disabled={busy || !m.active} value={current?.station_code || ""}
            onChange={e => e.target.value ? move(m.id, e.target.value) : move(m.id, null, "off_station")}>
            <option value="">Not on a station</option>
            {active.map(st => <option key={st.code} value={st.code}>{st.name}</option>)}
          </select></Field>
          {current && <button className={btnGhost} disabled={busy} onClick={() => move(m.id, null, "shift_end")}>End shift</button>}
        </div>;
      })}
    </section>
    <section className={`${cardCls} p-4 space-y-2`} aria-label="Default station per prep item">
      <h3 className="font-semibold">Which station makes each prep item</h3>
      <p className="text-sm text-slate-400">Unassigned tasks for an item go to whoever is on its station. Kitchen Manager and up.</p>
      {board.products.map(p => <div key={p.product_id} className="flex flex-wrap items-end gap-3">
        <span className="min-w-[200px]">{p.name}</span>
        <select aria-label={`Default station for ${p.name}`} className={inpCls} disabled={busy} value={p.station_code || ""} onChange={e => setDefault(p.product_id, e.target.value)}>
          <option value="">No default (assign by name)</option>
          {active.map(st => <option key={st.code} value={st.code}>{st.name}</option>)}
        </select>
      </div>)}
    </section>
    {!!board.history.length && <section className={`${cardCls} p-4`} aria-label="Station time today">
      <h3 className="font-semibold">Station time today</h3>
      <ul className="text-sm">{board.history.map(h => <li key={h.stint_id}>{h.staff_name}: {h.station_name} {clock(h.started_at)}–{h.ended_at ? clock(h.ended_at) : "now"}</li>)}</ul>
    </section>}
    <button className={btnGhost} disabled={busy} onClick={() => setEpoch(n => n + 1)}>Refresh</button>
  </div>;
}
