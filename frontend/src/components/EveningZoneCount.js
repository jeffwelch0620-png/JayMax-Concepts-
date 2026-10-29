import React, { useEffect, useRef, useState } from "react";
import * as api from "../lib/api";
import { Field, cardCls, inpCls, btnAcc, btnGhost } from "./common";
import { locationTotal } from "../lib/overviewDecimal";

// The closing manager's evening prep count, walked zone by zone (Bert's Salad Bar: Walk-in,
// Cooler, Below bar, Salad station). Each prepared item is counted in every zone it is kept
// in; the server adds the zones up into the one prep count line, so moving a pan between
// zones never creates food.

export const DEFAULT_TIMEZONE = "America/New_York"; // All three stores are in Eastern Tennessee.
const detail = e => { const d = e?.response?.data?.detail; return typeof d === "string" ? d : Array.isArray(d) ? d.map(x => x.msg).join("; ") : e.message || "Request failed"; };

// The count's time stamp: now, as an offset timestamp plus that day's date in the store's zone.
export function countStamp(timezone, now = new Date()) {
  const parts = Object.fromEntries(new Intl.DateTimeFormat("en-US", { timeZone: timezone, year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", second: "2-digit", hourCycle: "h23" })
    .formatToParts(now).map(p => [p.type, p.value]));
  const local = `${parts.year}-${parts.month}-${parts.day}T${parts.hour}:${parts.minute}:${parts.second}`;
  const offset = Math.round((Date.parse(`${local}Z`) - Math.floor(now.getTime() / 1000) * 1000) / 60000);
  const sign = offset < 0 ? "-" : "+", abs = Math.abs(offset);
  return { performed_at: `${local}${sign}${String(Math.floor(abs / 60)).padStart(2, "0")}:${String(abs % 60).padStart(2, "0")}`, business_date: local.slice(0, 10), timezone_name: timezone };
}

export function ZoneLayoutForm({ products, proposal, onSave }) {
  const [zones, setZones] = useState(() => proposal.zones.map(z => ({ name: z.name, product_ids: [...z.product_ids] })));
  const [newZone, setNewZone] = useState(""), [busy, setBusy] = useState(false), [error, setError] = useState("");
  const attempt = useRef(null);
  const name = id => products.find(p => p.product_id === id)?.name || id;
  function edit(fn) { attempt.current = null; setError(""); setZones(z => fn(z.map(x => ({ ...x, product_ids: [...x.product_ids] })))); }
  const move = (i, d) => edit(z => { const j = i + d; if (j < 0 || j >= z.length) return z; [z[i], z[j]] = [z[j], z[i]]; return z; });
  const toggle = (i, id) => edit(z => { z[i].product_ids = z[i].product_ids.includes(id) ? z[i].product_ids.filter(x => x !== id) : [...z[i].product_ids, id]; return z; });
  const unplaced = products.filter(p => !zones.some(z => z.product_ids.includes(p.product_id)));
  async function save() {
    if (unplaced.length) { setError(`Place every prepared item in a zone: ${unplaced.map(p => p.name).join(", ")}`); return; }
    if (!attempt.current) attempt.current = { key: crypto.randomUUID(), body: { note: "Evening count zones confirmed by manager", zones: zones.filter(z => z.product_ids.length) } };
    setBusy(true); setError("");
    try { await onSave(attempt.current.body, attempt.current.key); }
    catch (e) { if ([409, 422].includes(e?.response?.status)) attempt.current = null; setError(detail(e)); }
    finally { setBusy(false); }
  }
  return <section className={`${cardCls} p-4 space-y-3`} aria-label="Evening count zones">
    <h3 className="font-semibold">Set up evening count zones</h3>
    <p className="text-sm text-slate-400">List the places prepared food is kept, in the order you walk them, and tick which items are kept in each. An item kept in two places is counted in both and added up.</p>
    {zones.map((z, i) => <div key={i} className="border border-slate-700 rounded-lg p-3 space-y-2">
      <div className="flex gap-2 items-end">
        <Field label={`Zone ${i + 1}`}><input aria-label={`Zone name ${i + 1}`} className={inpCls} value={z.name} onChange={e => { const v = e.target.value; edit(x => { x[i].name = v; return x; }); }} /></Field>
        <button className={btnGhost} aria-label={`Move zone ${i + 1} up`} disabled={i === 0} onClick={() => move(i, -1)}>↑</button>
        <button className={btnGhost} aria-label={`Move zone ${i + 1} down`} disabled={i === zones.length - 1} onClick={() => move(i, 1)}>↓</button>
        <button className={btnGhost} aria-label={`Remove zone ${i + 1}`} onClick={() => edit(x => x.filter((_, n) => n !== i))}>Remove</button>
      </div>
      <div className="flex flex-wrap gap-3 text-sm">{products.map(p => <label key={p.product_id} className="flex gap-1"><input type="checkbox" aria-label={`${p.name} in zone ${i + 1}`} checked={z.product_ids.includes(p.product_id)} onChange={() => toggle(i, p.product_id)} />{name(p.product_id)}</label>)}</div>
    </div>)}
    <div className="flex gap-2 items-end">
      <Field label="New zone"><input aria-label="New zone name" className={inpCls} value={newZone} onChange={e => setNewZone(e.target.value)} placeholder="e.g. Salad station" /></Field>
      <button className={btnGhost} disabled={!newZone.trim()} onClick={() => { edit(z => [...z, { name: newZone.trim(), product_ids: [] }]); setNewZone(""); }}>Add zone</button>
    </div>
    {error && <p role="alert">{error}</p>}
    <button className={btnAcc} disabled={busy || !zones.some(z => z.product_ids.length)} onClick={save}>{attempt.current ? "Retry saving zones" : "Save count zones"}</button>
  </section>;
}

export function ZoneCountForm({ setup, onPreview, onSave, now }) {
  const layout = setup.zoneLayout, timezone = setup.policy?.timezone_name || DEFAULT_TIMEZONE;
  const byProduct = Object.fromEntries(setup.products.map(p => [p.product_id, p]));
  const profilesFor = p => setup.profiles.filter(u => u.product_version_id === p.id);
  const where = id => layout.zones.filter(z => z.product_ids.includes(id)).map(z => z.zone_code);
  const [values, setValues] = useState({}), [units, setUnits] = useState(() => Object.fromEntries(setup.products.map(p => [p.product_id, profilesFor(p)[0]?.id || ""])));
  const [note, setNote] = useState(""), [review, setReview] = useState(null), [busy, setBusy] = useState(false), [error, setError] = useState(""), [saved, setSaved] = useState(false);
  const attempt = useRef(null);
  const value = (id, zone) => values[`${id}|${zone}`] ?? "";
  const counted = setup.products.filter(p => where(p.product_id).length);
  const missing = setup.products.filter(p => !where(p.product_id).length);
  function set(id, zone, v) { if (!/^\d*\.?\d*$/.test(v)) return; attempt.current = null; setReview(null); setValues(x => ({ ...x, [`${id}|${zone}`]: v })); }
  const blank = counted.some(p => where(p.product_id).some(z => value(p.product_id, z) === "")) || counted.some(p => !units[p.product_id]);
  function body() {
    return { ...countStamp(timezone, now?.()), calendar_date_confirmed: true, note: note.trim(), complete_scope_confirmed: true, zone_layout_id: layout.header.id,
      lines: counted.map(p => ({ product_version_id: p.id, profile_id: units[p.product_id], evidence: `Counted by zone: ${note.trim()}`,
        zones: where(p.product_id).map(z => ({ zone_code: z, quantity: value(p.product_id, z) })) })) };
  }
  async function preview() {
    setError("");
    if (!note.trim()) { setError("Add a short count note (who counted)."); return; }
    setBusy(true);
    try { const b = body(); setReview({ body: b, result: await onPreview(b) }); }
    catch (e) { setError(detail(e)); }
    finally { setBusy(false); }
  }
  async function save() {
    if (!attempt.current) attempt.current = { key: crypto.randomUUID(), body: { body: review.body, expected_review_hash: review.result.reviewHash, reviewed: true } };
    setBusy(true); setError("");
    try { const r = await onSave(attempt.current.body, attempt.current.key); if (!r?.event?.id) throw new Error("The count was not confirmed. Retry the same save."); setSaved(true); }
    catch (e) { if ([409, 422].includes(e?.response?.status)) { attempt.current = null; setReview(null); } setError(detail(e)); }
    finally { setBusy(false); }
  }
  if (saved) return <p role="status" className={`${cardCls} p-4`}>Evening prep count saved for {review.body.business_date}. Refresh to start another count.</p>;
  return <section className={`${cardCls} p-4 space-y-3`} aria-label="Evening zone count">
    <h3 className="font-semibold">Evening prep count by zone</h3>
    <p className="text-sm text-slate-400">Walk the zones in order. Enter what is in each zone, 0 if it is empty. Items in more than one zone are added up for you. Time and date are taken when you save ({timezone}).</p>
    {!!missing.length && <p role="alert">Not in any zone yet: {missing.map(p => p.name).join(", ")}. Add them in the zone setup before counting.</p>}
    <fieldset disabled={busy || !!attempt.current} className="space-y-3">
      {layout.zones.map(z => <div key={z.zone_code} className="border border-slate-700 rounded-lg p-3 space-y-2" aria-label={`Zone ${z.name}`}>
        <h4 className="font-semibold">{z.walk_position}. {z.name}</h4>
        {z.product_ids.map(id => { const p = byProduct[id]; if (!p) return null; const places = where(id), profiles = profilesFor(p), total = locationTotal(places.map(c => value(id, c)));
          return <div key={id} className="grid md:grid-cols-3 gap-3 items-end">
            <Field label={p.name}><input aria-label={`Count ${p.name} in ${z.name}`} inputMode="decimal" className={inpCls} value={value(id, z.zone_code)} onChange={e => set(id, z.zone_code, e.target.value)} /></Field>
            {profiles.length > 1 ? <Field label="Unit"><select aria-label={`Unit ${p.name}`} className={inpCls} value={units[id]} onChange={e => { attempt.current = null; setReview(null); setUnits(u => ({ ...u, [id]: e.target.value })); }}>{profiles.map(u => <option key={u.id} value={u.id}>{u.source_unit}</option>)}</select></Field>
              : <p className="text-sm">{profiles[0]?.source_unit || "No verified count unit"}</p>}
            {places.length > 1 && <p className="text-xs text-slate-400">Total {total ?? "incomplete"} {profiles.find(u => u.id === units[id])?.source_unit || ""} across {places.length} zones</p>}
          </div>; })}
      </div>)}
      <Field label="Count note"><input aria-label="Evening count note" className={inpCls} value={note} onChange={e => { attempt.current = null; setReview(null); setNote(e.target.value); }} placeholder="e.g. Closing count, J. Smith" /></Field>
    </fieldset>
    {error && <p role="alert">{error}</p>}
    {review ? <div className="space-y-2">
      <p>Totals: {review.result.review.lines.map(l => `${byProduct[l.product_id]?.name || l.product_id} ${l.quantity}`).join(" · ")}</p>
      <button className={btnAcc} disabled={busy} onClick={save}>{attempt.current ? "Retry same count save" : "Save evening count"}</button>
    </div> : <button className={btnAcc} disabled={busy || blank || !!missing.length} onClick={preview}>Review totals</button>}
  </section>;
}

export function EveningZoneCount({ rid }) {
  const [setup, setSetup] = useState(null), [error, setError] = useState(""), [epoch, setEpoch] = useState(0), [editing, setEditing] = useState(false);
  useEffect(() => {
    let active = true; setSetup(null); setError("");
    api.nativePrepObservationSetup(rid).then(d => active && setSetup(d)).catch(e => active && setError(detail(e)));
    return () => { active = false; };
  }, [rid, epoch]);
  if (error) return <p role="alert">{error}</p>;
  if (!setup) return <p>Loading evening count…</p>;
  if (!setup.zoneLayout && !setup.proposedZoneLayout) return <p>Count zones are awaiting setup on this server.</p>;
  const reload = () => { setEditing(false); setEpoch(n => n + 1); };
  return <div className="space-y-4" data-testid="evening-zone-count">
    {!setup.zoneLayout || editing
      ? <ZoneLayoutForm products={setup.products} proposal={editing && setup.zoneLayout ? { zones: setup.zoneLayout.zones } : setup.proposedZoneLayout}
          onSave={async (body, key) => { const r = await api.saveNativePrepZones(rid, body, key); if (!r?.header?.id) throw new Error("Zones were not confirmed. Retry the same save."); reload(); }} />
      : <>
        <div className="flex gap-2 items-center"><p className="text-sm">Zones (revision {setup.zoneLayout.header.revision}): {setup.zoneLayout.zones.map(z => z.name).join(" → ")}</p><button className={btnGhost} onClick={() => setEditing(true)}>Change zones</button></div>
        <ZoneCountForm key={`${setup.zoneLayout.header.id}:${epoch}`} setup={setup} onPreview={b => api.previewNativePrepObservation(rid, "count", b)} onSave={(b, k) => api.saveNativePrepObservation(rid, "count", b, k)} />
      </>}
  </div>;
}
