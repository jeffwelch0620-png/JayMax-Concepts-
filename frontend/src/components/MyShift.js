import React, { useEffect, useRef, useState } from "react";
import { MapPin } from "lucide-react";
import * as api from "../lib/api";
import { todayISO } from "../lib/calc";
import { prepTracks } from "../lib/prepTracks";
import { inpCls, btnAcc, cardCls } from "./common";
import { StaffPrepTaskPlan } from "./StaffPrepTasks";

const ACCENT = "#f45a17";   // Companion orange (AGENTS.md: employee screens follow the Companion format)
const detail = (e, fallback) => (typeof e?.response?.data?.detail === "string" ? e.response.data.detail : fallback);

// Station check-in: the cook confirms where they are working today, which routes their station's
// unassigned prep tasks to them (Jeff 2026-10-30). A Shift Leader can still move them on the board.
export function StationCheckIn({ rid, staffId, onChanged }) {
  const day = todayISO();
  const [data, setData] = useState(null), [choice, setChoice] = useState(""), [busy, setBusy] = useState(false), [err, setErr] = useState("");
  const attempt = useRef(null), reads = useRef(0);

  async function load() {
    const n = ++reads.current;
    try {
      const s = await api.staffStation(rid, day);
      if (n !== reads.current) return;
      if (s?.staff_member_id !== staffId || s.business_date !== day || !Array.isArray(s.stations)) throw new Error("Station was not confirmed");
      setData(s); setChoice(s.station_code || ""); setErr("");
    } catch (e) { if (n === reads.current) { setData(null); setErr(detail(e, "Couldn't load your station")); } }
  }
  useEffect(() => { load(); return () => { reads.current += 1; }; }, [rid, staffId]); // eslint-disable-line react-hooks/exhaustive-deps

  async function confirm() {
    if (!choice || busy) return;
    const body = { staff_member_id: staffId, station_code: choice, business_date: day };
    // A retry after a lost reply reuses the same key; a different choice is a new request.
    if (!attempt.current || attempt.current.code !== choice) attempt.current = { key: crypto.randomUUID(), code: choice };
    setBusy(true); setErr(""); reads.current += 1;
    try {
      await api.confirmStaffStation(rid, body, attempt.current.key);
      attempt.current = null;
      await load();
      onChanged?.();
    } catch (e) {
      if ([403, 409, 422].includes(e?.response?.status)) attempt.current = null;
      setErr(detail(e, "Your station wasn't saved. Try again."));
    } finally { setBusy(false); }
  }

  const current = data?.stations.find(s => s.code === data.station_code);
  return (
    <section className={`${cardCls} p-4 mb-4`} aria-label="My station" data-testid="my-station">
      <div className="flex items-center gap-2 mb-2"><MapPin size={16} style={{ color: ACCENT }} />
        <span className="font-display font-bold text-slate-100">{current ? `You're on ${current.name}` : "Pick your station"}</span></div>
      {data && <div className="flex gap-2 items-center flex-wrap">
        <select className={inpCls} aria-label="Your station" value={choice} disabled={busy} onChange={e => setChoice(e.target.value)} data-testid="my-station-select">
          <option value="">Choose a station</option>
          {data.stations.map(s => <option key={s.code} value={s.code}>{s.name}</option>)}
        </select>
        <button className={btnAcc} style={{ background: ACCENT }} disabled={busy || !choice || choice === data.station_code} onClick={confirm} data-testid="my-station-confirm">
          {busy ? "Saving…" : current ? "Move here" : "Start here"}</button>
      </div>}
      {err && <p className="text-red-400 text-xs mt-2" role="alert">{err}</p>}
    </section>
  );
}

// The signed-in cook's shift: their station, then their prep tasks with output reporting.
export function MyShift({ rid, staffId, staffName, track, setTrack, drafts }) {
  const [version, setVersion] = useState(0);   // a station change re-reads the task list
  return (
    <div data-testid="my-shift">
      <h2 className="font-display font-bold text-xl text-slate-100 mb-3" style={{ color: ACCENT }}>Hi, {staffName}</h2>
      <StationCheckIn rid={rid} staffId={staffId} onChanged={() => setVersion(v => v + 1)} />
      {prepTracks(rid).length > 1 && <select aria-label="Staff prep track" className={`${inpCls} mb-3`} value={track} onChange={e => setTrack(e.target.value)}>
        {prepTracks(rid).map(t => <option key={t.id} value={t.id}>{t.label}</option>)}</select>}
      <StaffPrepTaskPlan key={`${rid}:${version}`} rid={rid} pin="" staffId={staffId} track={track} drafts={drafts} personal />
    </div>
  );
}
