import React, { useEffect, useRef, useState } from "react";
import { confirmSave, useRetainedDraft } from "../lib/saveIntegrity";
import { ChefHat, Play, PackageCheck, Layers, X, Plus, Trash2, Check, Sparkles, ClipboardList, Send, Package } from "lucide-react";
import { normalizeRecipeSchema, recipeCostSummary, fmtDate, fmtMoney, num, todayISO, FREQS, VESSELS } from "../lib/calc";
import * as api from "../lib/api";
import { PrepDayDrafts } from "./PrepDayDrafts";
import { HistoricalPrepLists } from "./HistoricalPrepLists";
import { StaffPrepCountReview } from "./StaffPrepCounts";
import { PrepContainers } from "./PrepContainers";
import { PageTitle, EmptyState, Field, SectionLabel, Pill, cardCls, inpCls, btnAcc, btnGhost, btnDanger } from "./common";

function tomorrowISO() {
  const d = new Date();
  d.setDate(d.getDate() + 1);
  return new Date(d.getTime() - d.getTimezoneOffset() * 60000).toISOString().slice(0, 10);
}
function daysAgoISO(n) {
  const d = new Date();
  d.setDate(d.getDate() - n);
  return new Date(d.getTime() - d.getTimezoneOffset() * 60000).toISOString().slice(0, 10);
}

const SUBS = [
  { id: "list", label: "Prep List", icon: ClipboardList },
  { id: "count", label: "Evening Count", icon: Check },
  { id: "inventory", label: "Inventory & Log", icon: Layers },
  { id: "planning", label: "Planning & AI", icon: Sparkles },
  { id: "history", label: "History", icon: Layers },
];

const TRACKS = [
  { id: "daily", label: "Daily Prep" },
  { id: "bulk", label: "Bulk Prep" },
];

// v matches Python's date.weekday() (Mon=0..Sun=6) on the backend -- NOT JS
// Date.getDay() (Sun=0). This is a static label table, never derived from a live
// Date, so there's no actual mismatch today -- just don't "simplify" it later with
// .getDay().
const WEEKDAYS = [
  { v: 0, label: "Mon" }, { v: 1, label: "Tue" }, { v: 2, label: "Wed" }, { v: 3, label: "Thu" },
  { v: 4, label: "Fri" }, { v: 5, label: "Sat" }, { v: 6, label: "Sun" },
];
const weekdayLabel = (v) => WEEKDAYS.find((d) => d.v === v)?.label || "?";

function RecurringScheduleFields({ recurDays, toggleDay, fixedQty, setFixedQty, unitLabel, idPrefix }) {
  return (
    <div className="mb-4">
      <div className="flex gap-1 mb-2">
        {WEEKDAYS.map((d) => (
          <button key={d.v} className={recurDays.includes(d.v) ? btnAcc : btnGhost} style={{ padding: "4px 10px", fontSize: 11 }}
            onClick={() => toggleDay(d.v)} aria-pressed={recurDays.includes(d.v)} data-testid={`${idPrefix}-recur-day-${d.v}`}>{d.label}</button>
        ))}
      </div>
      <Field label={`Fixed Quantity (${unitLabel})`}>
        <input type="number" step="0.5" className={inpCls} data-testid={`${idPrefix}-fixed-qty`}
          value={fixedQty} onChange={(e) => setFixedQty(e.target.value)} />
      </Field>
    </div>
  );
}

export function PrepTab({ drafts, showError = () => {}, rid, items, dishes, persistDishes, prepStock, prepLogs, prepReadStatus, prepCapabilities, applyPrepResult, salesPeriod, showToast }) {
  const [track, setTrack] = useState("daily");
  const [sub, setSub] = useState("list");
  const [prepItems, setPrepItems] = useState([]);
  const reloadPrepItems = () => api.listPrepItems(rid, track).then(setPrepItems).catch(() => {});
  useEffect(() => { reloadPrepItems(); }, [rid, track]); // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <div className="fade-slide-in" data-testid="prep-tab">
      <PageTitle>Prep Production</PageTitle>
      <div className="text-xs text-slate-500 -mt-3 mb-4">
        {api.nativePurchasesEnabled || prepCapabilities?.reportingAvailable === false ? "Prep counts and production explain inventory usage. Track 1 physical counts and received purchases remain the accounting baseline." : "Nightly cycle: the closing manager records the evening prep count, the system builds tomorrow's prep list (par − counted = prep quantity), staff mark tasks prepped, and raw inventory is deducted automatically."}
      </div>
      <div className="flex gap-2 mb-4 flex-wrap" data-testid="prep-track-selector">
        {TRACKS.map((t) => (
          <button key={t.id} className={track === t.id ? btnAcc : btnGhost} onClick={() => setTrack(t.id)} data-testid={`prep-track-${t.id}`}>
            {t.label}
          </button>
        ))}
      </div>
      <div className="text-xs text-slate-500 -mt-2 mb-4">
        {track === "daily"
          ? "On-site prep, replenished to par every day."
          : api.prepPlanningEnabled ? "Bulk prep planning, separate from Daily Prep. Production location and transfers are tracked separately." : "Commissary-kitchen prep — its own standing items, evening count, and daily list, separate from Daily Prep."}
      </div>
      <div className="flex gap-2 mb-5 flex-wrap" data-testid="prep-subtabs">
        {SUBS.filter(s => s.id !== "history" || api.isPostgres).map((s) => {
          const Icon = s.icon;
          return (
            <button key={s.id} className={sub === s.id ? btnAcc : btnGhost} onClick={() => setSub(s.id)} data-testid={`prep-subtab-${s.id}`}>
              <Icon size={14} /> {s.label}
            </button>
          );
        })}
      </div>
      {sub === "list" && (api.prepDayTasksEnabled ? <PrepDayDrafts rid={rid} track={track} drafts={drafts} showToast={showToast}/> : prepCapabilities?.listsAvailable === false ? <p data-testid="prep-list-unavailable">Historical prep lists are retained for review. Use reviewed dated prep tasks for current work.</p> : <PrepListView rid={rid} track={track} items={items} dishes={dishes} prepItems={prepItems} reloadPrepItems={reloadPrepItems} applyPrepResult={applyPrepResult} showToast={showToast} />)}
      {sub === "count" && (api.staffPrepCountsEnabled ? <StaffPrepCountReview key={rid} rid={rid} drafts={drafts}/> : prepCapabilities?.countsAvailable === false ? <p data-testid="prep-count-unavailable">Historical count sessions are retained for review. Ask your manager to issue a reviewed prep count sheet.</p> : <EveningCount rid={rid} track={track} showToast={showToast} />)}
      {sub === "inventory" && (api.prepContainersEnabled ? <PrepContainers key={rid} rid={rid} drafts={drafts} /> : prepReadStatus?.available === false ? <p data-testid="prep-inventory-unavailable">{prepReadStatus.message || "Prep balances are unavailable here. Use reviewed prep counts, production and period reports."}</p> : <InventoryLog drafts={drafts} showError={showError} rid={rid} items={items} dishes={dishes} persistDishes={persistDishes} prepItems={prepItems} prepStock={prepStock} prepLogs={prepLogs} applyPrepResult={applyPrepResult} salesPeriod={salesPeriod} showToast={showToast} />)}
      {sub === "planning" && <Planning showError={showError} rid={rid} dishes={dishes} prepItems={prepItems} prepCapabilities={prepCapabilities} persistDishes={persistDishes} showToast={showToast} />}
      {sub === "history" && api.isPostgres && <HistoricalPrepLists key={rid} rid={rid} />}
    </div>
  );
}

/* ---------------- Edit Recurring Schedule modal ---------------- */
function EditRecurringModal({ prepItem, onClose, onSave, showToast }) {
  const [recurDays, setRecurDays] = useState(prepItem.recurDays || []);
  const [fixedQty, setFixedQty] = useState(prepItem.fixedQty || 0);

  function toggleDay(d) {
    setRecurDays((arr) => arr.includes(d) ? arr.filter((x) => x !== d) : [...arr, d].sort((a, b) => a - b));
  }

  function save() {
    if (recurDays.length === 0) { showToast("Pick at least one day"); return; }
    if (!(Number(fixedQty) > 0)) { showToast("Enter a fixed quantity"); return; }
    onSave(recurDays, Number(fixedQty) || 0);
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm" data-testid="edit-recurring-modal">
      <div className={`${cardCls} w-full max-w-md p-5 m-4 bg-[#161F30]`}>
        <div className="flex justify-between items-center mb-4">
          <div className="font-display font-bold text-slate-100">Recurring Schedule — {prepItem.name}</div>
          <button onClick={onClose} className="text-slate-400 hover:text-white" data-testid="close-edit-recurring"><X size={18} /></button>
        </div>
        <RecurringScheduleFields recurDays={recurDays} toggleDay={toggleDay} fixedQty={fixedQty} setFixedQty={setFixedQty}
          unitLabel={prepItem.sourceType === "item" ? `${prepItem.vesselName}s` : "batch yield units"} idPrefix="edit-recurring" />
        <div className="flex gap-2 justify-end">
          <button className={btnGhost} onClick={onClose}>Cancel</button>
          <button className={btnAcc} onClick={save} data-testid="save-recurring-button">Save</button>
        </div>
      </div>
    </div>
  );
}

/* ---------------- Add Prep Item modal ---------------- */
function AddPrepItemModal({ rid, track, items, dishes, onClose, onSaved, showToast }) {
  const prepRecipes = dishes.filter((d) => d.recipeType === "prep").map(normalizeRecipeSchema);
  const [sourceType, setSourceType] = useState("item");
  const [controlNumber, setControlNumber] = useState(items[0]?.controlNumber || "");
  const [recipeId, setRecipeId] = useState(prepRecipes[0]?.id || "");
  const [name, setName] = useState("");
  const [vesselIdx, setVesselIdx] = useState(1);
  const [vesselName, setVesselName] = useState(VESSELS[1].name);
  const [vesselCapacity, setVesselCapacity] = useState(VESSELS[1].capacity);
  const [parVessels, setParVessels] = useState(4);
  const [par, setPar] = useState(0);
  const [schedule, setSchedule] = useState("daily");
  const [recurDays, setRecurDays] = useState([]);
  const [fixedQty, setFixedQty] = useState(0);
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);

  const srcItem = items.find((i) => i.controlNumber === controlNumber);
  const srcRecipe = prepRecipes.find((r) => r.id === recipeId);
  const autoName = sourceType === "item" ? (srcItem ? `${srcItem.name} (prepped)` : "") : (srcRecipe?.name || "");
  const portionUnit = sourceType === "item" ? (srcItem?.portionUOM || "oz") : (srcRecipe?.yieldUOM || "oz");

  function pickVessel(idx) {
    setVesselIdx(idx);
    setVesselName(VESSELS[idx].name);
    if (VESSELS[idx].capacity > 0) setVesselCapacity(VESSELS[idx].capacity);
  }

  function toggleDay(d) {
    setRecurDays((arr) => arr.includes(d) ? arr.filter((x) => x !== d) : [...arr, d].sort((a, b) => a - b));
  }

  async function save() {
    const finalName = name.trim() || autoName;
    if (!finalName) { showToast("Name the prep item"); return; }
    if (sourceType === "item" && !controlNumber) { showToast("Pick an inventory item"); return; }
    if (sourceType === "prep" && !recipeId) { showToast("Pick a prep recipe"); return; }
    if (schedule === "recurring" && recurDays.length === 0) { showToast("Pick at least one day"); return; }
    if (schedule === "recurring" && !(Number(fixedQty) > 0)) { showToast("Enter a fixed quantity"); return; }
    setBusy(true);
    try {
      await api.createPrepItem(rid, {
        name: finalName, sourceType, track,
        controlNumber: sourceType === "item" ? controlNumber : null,
        recipeId: sourceType === "prep" ? recipeId : null,
        vesselName, vesselCapacity: Number(vesselCapacity) || 0,
        parVessels: Number(parVessels) || 0, par: sourceType === "prep" ? Number(par) || 0 : 0,
        schedule, note,
        recurDays: schedule === "recurring" ? recurDays : [],
        fixedQty: schedule === "recurring" ? Number(fixedQty) || 0 : 0,
      });
      showToast(`Prep item "${finalName}" added`);
      onSaved();
      onClose();
    } catch (e) { showToast(e?.response?.data?.detail || "Couldn't add the prep item"); }
    finally { setBusy(false); }
  }

  const srcBtn = (t) => sourceType === t ? btnAcc : btnGhost;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm" data-testid="add-prep-item-modal">
      <div className={`${cardCls} w-full max-w-xl p-5 m-4 bg-[#161F30] max-h-[90vh] overflow-y-auto`}>
        <div className="flex justify-between items-center mb-4">
          <div className="font-display font-bold text-slate-100 flex items-center gap-2"><Package size={17} style={{ color: "var(--acc)" }} /> Add Prep Item</div>
          <button onClick={onClose} className="text-slate-400 hover:text-white" data-testid="close-add-prep-item"><X size={18} /></button>
        </div>

        <SectionLabel>Source</SectionLabel>
        <div className="flex gap-2 mb-3">
          <button className={srcBtn("item")} onClick={() => setSourceType("item")} data-testid="prep-source-item">Inventory Item</button>
          <button className={srcBtn("prep")} onClick={() => setSourceType("prep")} data-testid="prep-source-recipe">Prep Recipe</button>
        </div>
        <div className="grid grid-cols-2 gap-3 mb-3">
          {sourceType === "item" ? (
            <Field label="Inventory Item (control #)">
              <select className={inpCls} data-testid="prep-item-source-select" value={controlNumber} onChange={(e) => setControlNumber(e.target.value)}>
                {items.map((it) => <option key={it.controlNumber} value={it.controlNumber}>{it.controlNumber} — {it.name}</option>)}
              </select>
            </Field>
          ) : (
            <Field label="Prep Recipe">
              <select className={inpCls} data-testid="prep-item-source-select" value={recipeId} onChange={(e) => setRecipeId(e.target.value)}>
                {prepRecipes.map((r) => <option key={r.id} value={r.id}>{r.name}</option>)}
              </select>
            </Field>
          )}
          <Field label="Prep Item Name">
            <input className={inpCls} data-testid="prep-item-name" value={name} onChange={(e) => setName(e.target.value)} placeholder={autoName || "e.g. Sliced Tomatoes"} />
          </Field>
        </div>

        <SectionLabel>Service Vessel (what it's prepped into)</SectionLabel>
        <div className="grid grid-cols-2 gap-3 mb-1">
          <Field label="Standard Vessel">
            <select className={inpCls} data-testid="prep-item-vessel" value={vesselIdx} onChange={(e) => pickVessel(Number(e.target.value))}>
              {VESSELS.map((v, i) => <option key={v.name} value={i}>{v.name}{v.capacity ? ` (~${v.capacity} fl oz)` : ""}</option>)}
            </select>
          </Field>
          {sourceType === "item" && (
            <Field label={`Capacity per Vessel (in ${portionUnit} — the item's portion unit)`}>
              <input type="number" step="0.5" className={inpCls} data-testid="prep-item-capacity" value={vesselCapacity} onChange={(e) => setVesselCapacity(e.target.value)} />
            </Field>
          )}
        </div>
        <div className="text-[11px] text-slate-500 mb-3">
          {sourceType === "item"
            ? `Example: raw tomatoes → sliced tomatoes in 1/6 pans. Prepping one ${vesselName} deducts ${num(vesselCapacity, 1)} ${portionUnit} of ${srcItem?.controlNumber || "the item"} from inventory.`
            : `The recipe's batch yield is used for deduction; the vessel is recorded as the service reference (e.g. portion into ${vesselName}s).`}
        </div>

        <div className="grid grid-cols-2 gap-3 mb-3">
          {sourceType === "item" && (
            <Field label={`Par — ${vesselName}s to keep on hand`}>
              <input type="number" step="0.5" className={inpCls} data-testid="prep-item-par" value={parVessels} onChange={(e) => setParVessels(e.target.value)} />
            </Field>
          )}
          {sourceType === "prep" && (
            <Field label={`Par (in ${portionUnit}, this ${track === "bulk" ? "Bulk" : "Daily"} item only)`}>
              <input type="number" step="1" className={inpCls} data-testid="prep-item-recipe-par" value={par} onChange={(e) => setPar(e.target.value)}
                placeholder={srcRecipe ? `defaults to the recipe's own par (${num(srcRecipe.prepPar, 0)})` : "0"} />
            </Field>
          )}
          <Field label="Note (optional)"><input className={inpCls} data-testid="prep-item-note" value={note} onChange={(e) => setNote(e.target.value)} placeholder="e.g. slice thin, date & label" /></Field>
        </div>

        <SectionLabel>Schedule</SectionLabel>
        <div className="flex gap-2 mb-3 flex-wrap">
          <button className={schedule === "daily" ? btnAcc : btnGhost} onClick={() => setSchedule("daily")} data-testid="schedule-daily">Daily — on every prep list</button>
          <button className={schedule === "oneoff" ? btnAcc : btnGhost} onClick={() => setSchedule("oneoff")} data-testid="schedule-oneoff">One-off — add as needed</button>
          {api.isPostgres && <button className={schedule === "recurring" ? btnAcc : btnGhost} onClick={() => setSchedule("recurring")} data-testid="schedule-recurring">Recurring — specific days</button>}
        </div>
        {schedule === "recurring" && (
          <RecurringScheduleFields recurDays={recurDays} toggleDay={toggleDay} fixedQty={fixedQty} setFixedQty={setFixedQty}
            unitLabel={sourceType === "item" ? `${vesselName}s` : portionUnit} idPrefix="prep-item" />
        )}

        <div className="flex gap-2 justify-end">
          <button className={btnGhost} onClick={onClose}>Cancel</button>
          <button className={btnAcc} onClick={save} disabled={busy} data-testid="prep-item-save-button">{busy ? "Saving…" : "Add Prep Item"}</button>
        </div>
      </div>
    </div>
  );
}

/* ---------------- Evening Count ---------------- */
function EveningCount({ rid, track, showToast }) {
  const [date, setDate] = useState(todayISO());
  const [session, setSession] = useState(null);
  const [drafts, setDrafts] = useState({});
  const [noteDrafts, setNoteDrafts] = useState({});
  const [countedBy, setCountedBy] = useState(() => localStorage.getItem("prepCountedBy") || "");
  const [savingId, setSavingId] = useState("");
  const [showRev, setShowRev] = useState(false);
  const [loadError, setLoadError] = useState("");
  const request = useRef(0);

  const load = () => { const id = ++request.current; setSession(null); setLoadError(""); return api.getCountSession(rid, date, track).then((s) => {
    if (request.current !== id) return;
    setSession(s);
    const d = {}, n = {};
    (s.entries || []).forEach((e) => { const k = e.recipeId || e.prepItemId; d[k] = e.onHand === null || e.onHand === undefined ? "" : e.onHand; n[k] = e.note || ""; });
    setDrafts(d);
    setNoteDrafts(n);
  }).catch(e => { if (request.current === id) setLoadError(e?.response?.data?.detail || "Couldn't confirm the count session. Retry to load it."); }); };
  useEffect(() => { load(); return () => { request.current++; }; }, [rid, date, track]); // eslint-disable-line react-hooks/exhaustive-deps

  if (loadError) return <div role="alert" data-testid="count-load-error">{loadError}<button onClick={load} className={btnGhost}>Retry count session</button></div>;
  if (!session) return <div className="text-slate-500 text-sm" data-testid="count-loading">Loading count session…</div>;
  const recipes = session.recipes || [];
  const prepItems = session.prepItems || [];
  const entryFor = (key) => (session.entries || []).find((e) => (e.recipeId || e.prepItemId) === key) || {};
  const allKeys = [...recipes.map((r) => r.id), ...prepItems.map((p) => p.id)];
  const uncounted = allKeys.filter((k) => entryFor(k).onHand === null || entryFor(k).onHand === undefined).length;

  async function saveEntry(key, isPrepItem) {
    const raw = drafts[key];
    if (raw === "" || raw === undefined || raw === null) { showToast("Enter a number — blank counts aren't saved"); return; }
    if (!countedBy.trim()) { showToast("Enter your name first so the count is attributed"); return; }
    localStorage.setItem("prepCountedBy", countedBy.trim());
    setSavingId(key);
    try {
      const body = { onHand: Number(raw), note: noteDrafts[key] || "", countedBy: countedBy.trim() };
      if (isPrepItem) body.prepItemId = key; else body.recipeId = key;
      const res = await api.saveCountEntry(rid, session.id, body);
      setSession((s) => ({ ...s, revision: res.revision, entries: s.entries.map((e) => (e.recipeId || e.prepItemId) === key ? res.entry : e) }));
      showToast("Count saved");
    } catch (e) { showToast(e?.response?.data?.detail || "Couldn't save that count"); }
    finally { setSavingId(""); }
  }

  async function submit() {
    if (!countedBy.trim()) { showToast("Enter your name first"); return; }
    let ack = false;
    if (uncounted > 0) {
      if (!window.confirm(`${uncounted} item${uncounted !== 1 ? "s have" : " has"} no saved count. A blank is never treated as zero — uncounted items will be planned at full par. Submit anyway?`)) return;
      ack = true;
    }
    try {
      await api.submitCount(rid, session.id, { countedBy: countedBy.trim(), acknowledgeUncounted: ack });
      showToast("Evening count submitted — the prep list can now be generated from it");
      load();
    } catch (e) { showToast(e?.response?.data?.detail || "Couldn't submit the count"); }
  }

  function countRow(key, name, unit, sub, isPrepItem) {
    const e = entryFor(key);
    const saved = e.savedAt && drafts[key] !== "" && Number(drafts[key]) === e.onHand;
    return (
      <tr key={key} data-testid={`count-row-${key}`}>
        <td>
          <div className="font-semibold text-slate-200 flex items-center gap-1.5"><ChefHat size={14} style={{ color: "var(--acc)" }} /> {name}</div>
          {sub && <div className="text-[11px] text-slate-500">{sub}</div>}
        </td>
        <td>
          <input type="number" step="0.1" min="0" className={`${inpCls} w-24`} data-testid={`count-input-${key}`}
            placeholder="—" value={drafts[key] ?? ""} onChange={(e2) => setDrafts((d) => ({ ...d, [key]: e2.target.value }))} />
          {" "}<span className="text-xs text-slate-500">{unit}</span>
        </td>
        <td><input className={`${inpCls} w-40 py-1.5`} data-testid={`count-note-${key}`} placeholder="optional" value={noteDrafts[key] ?? ""} onChange={(e2) => setNoteDrafts((n) => ({ ...n, [key]: e2.target.value }))} /></td>
        <td>
          {saved
            ? <span className="text-emerald-400 text-xs font-semibold flex items-center gap-1" data-testid={`count-saved-${key}`}><Check size={13} /> Saved{e.savedBy ? ` by ${e.savedBy}` : ""}</span>
            : <span className="text-slate-500 text-xs">{e.onHand !== null && e.onHand !== undefined ? "Edited — unsaved" : "Not counted"}</span>}
        </td>
        <td><button className={btnGhost} onClick={() => saveEntry(key, isPrepItem)} disabled={savingId === key} data-testid={`count-save-${key}`}>{savingId === key ? "Saving…" : "Save"}</button></td>
      </tr>
    );
  }

  return (
    <div data-testid="evening-count">
      <div className={`${cardCls} p-4 mb-4 flex gap-3 flex-wrap items-end`}>
        <Field label="Count Date"><input type="date" className={inpCls} data-testid="count-date" value={date} onChange={(e) => setDate(e.target.value)} /></Field>
        <Field label="Counted By"><input className={inpCls} data-testid="counted-by-input" placeholder="Your name" value={countedBy} onChange={(e) => setCountedBy(e.target.value)} /></Field>
        {session.status === "submitted"
          ? <Pill testId="count-status-pill" color="#10B981" bg="rgba(16,185,129,0.12)">Submitted{session.countedBy ? ` by ${session.countedBy}` : ""}</Pill>
          : <Pill testId="count-status-pill" color="#F59E0B" bg="rgba(245,158,11,0.12)">Open — {uncounted} uncounted</Pill>}
        <button className={btnAcc} onClick={submit} data-testid="submit-count-button"><Send size={14} /> Submit Evening Count</button>
      </div>

      {session.status === "submitted" && (
        <div className="bg-blue-500/10 border border-blue-500/40 rounded-lg px-3.5 py-2.5 text-blue-300 text-xs mb-4" data-testid="submitted-banner">
          Submitted {session.submittedAt ? fmtDate(session.submittedAt.slice(0, 10)) : ""}. Any correction is saved as a new visible revision — the original is never erased. Current revision: <b className="num">{session.revision}</b>.
          {(session.revisions || []).length > 0 && (
            <button className="ml-2 underline font-semibold" onClick={() => setShowRev(!showRev)} data-testid="toggle-revisions">
              {showRev ? "Hide" : "Show"} {(session.revisions || []).length} prior revision{(session.revisions || []).length !== 1 ? "s" : ""}
            </button>
          )}
        </div>
      )}
      {showRev && (session.revisions || []).map((rev, i) => (
        <div key={i} className={`${cardCls} p-3 mb-2 text-xs`} data-testid={`revision-${rev.revision}`}>
          <div className="font-bold text-slate-300 mb-1">Revision {rev.revision} — archived {fmtDate((rev.archivedAt || "").slice(0, 10))} by {rev.archivedBy || "—"}</div>
          {(rev.entries || []).filter((e) => e.onHand !== null).map((e) => {
            const key = e.recipeId || e.prepItemId;
            const r = recipes.find((x) => x.id === key) || prepItems.find((x) => x.id === key);
            return <div key={key} className="text-slate-400">{r?.name || key}: <span className="num">{num(e.onHand, 1)} {r?.yieldUOM || r?.vesselName}</span> (by {e.savedBy || "—"})</div>;
          })}
        </div>
      ))}

      {recipes.length === 0 && prepItems.length === 0 ? <EmptyState text="No prep recipes or prep items yet. Add them in Menu Costing or the Prep List tab." /> : (
        <div className={`${cardCls} overflow-hidden`}>
          <div className="overflow-x-auto">
            <table className="ops-table" data-testid="prep-count-table">
              <thead><tr><th>Prep Item</th><th>On Hand Now</th><th>Note</th><th>Saved State</th><th></th></tr></thead>
              <tbody>
                {recipes.map((r) => countRow(r.id, r.name, r.yieldUOM, r.shelfLife ? `Shelf life: ${r.shelfLife}` : "", false))}
                {prepItems.map((p) => countRow(p.id, p.name, `× ${p.vesselName}`, `Count in ${p.vesselName}s · par ${num(p.parVessels, 1)}`, true))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}

/* ---------------- Prep List ---------------- */
function PrepListView({ rid, track, items, dishes, prepItems, reloadPrepItems, applyPrepResult, showToast }) {
  const [date, setDate] = useState(tomorrowISO());
  const [list, setList] = useState(null);
  const [loaded, setLoaded] = useState(false);
  const [plannedDrafts, setPlannedDrafts] = useState({});
  const [releasedBy, setReleasedBy] = useState(() => localStorage.getItem("prepCountedBy") || "");
  const [completing, setCompleting] = useState(null);
  const [cBatches, setCBatches] = useState(1);
  const [cBy, setCBy] = useState(() => localStorage.getItem("prepCountedBy") || "");
  const [containers, setContainers] = useState([]);
  const [busy, setBusy] = useState(false);
  const [showAdd, setShowAdd] = useState(false);
  const [editingRecurring, setEditingRecurring] = useState(null);
  const [loadError, setLoadError] = useState("");
  const request = useRef(0);

  const load = () => {
    const id = ++request.current; setLoaded(false); setList(null); setLoadError("");
    api.getPrepList(rid, date, track).then((r) => {
      if (request.current !== id) return;
      setList(r.list);
      setLoaded(true);
      const d = {};
      (r.list?.tasks || []).forEach((t) => { d[t.id] = t.batchesPlanned; });
      setPlannedDrafts(d);
    }).catch(e => { if (request.current === id) setLoadError(e?.response?.data?.detail || "Couldn't confirm the prep list. Retry to load it."); });
  };
  useEffect(() => { load(); return () => { request.current++; }; }, [rid, date, track]); // eslint-disable-line react-hooks/exhaustive-deps

  async function generate() {
    try {
      const r = await api.generatePrepList(rid, date, track);
      setList(r.list);
      const d = {};
      (r.list?.tasks || []).forEach((t) => { d[t.id] = t.batchesPlanned; });
      setPlannedDrafts(d);
      showToast(r.regenerated ? "Prep list generated from the latest submitted count" : "A list already exists for that date — loaded it");
    } catch (e) { showToast(e?.response?.data?.detail || "Couldn't generate the prep list"); }
  }

  async function saveDraft() {
    try {
      await api.updatePrepList(rid, list.id, list.tasks.map((t) => ({ ...t, batchesPlanned: Number(plannedDrafts[t.id]) || 0 })));
      showToast("Draft adjustments saved");
      load();
    } catch (e) { showToast(e?.response?.data?.detail || "Couldn't save adjustments"); }
  }

  async function release() {
    if (!releasedBy.trim()) { showToast("Enter your name to release the list"); return; }
    localStorage.setItem("prepCountedBy", releasedBy.trim());
    try {
      await api.releasePrepList(rid, list.id, releasedBy.trim());
      showToast("Prep list released — staff can now see it on the Prep Sheet");
      load();
    } catch (e) { showToast(e?.response?.data?.detail || "Couldn't release the list"); }
  }

  function openComplete(task) {
    const remaining = Math.max(0, task.batchesPlanned - task.batchesDone);
    setCompleting(task);
    setCBatches(remaining || 1);
    const sizeGuess = task.yieldUOM === "oz" || task.yieldUOM === "fl oz" ? 32 : Math.max(1, task.yieldQty);
    setContainers([{ label: task.vesselName || "Deli container", size: sizeGuess, count: Math.max(1, Math.round(((remaining || 1) * task.yieldQty) / sizeGuess)) }]);
  }

  async function confirmComplete() {
    if (!completing) return;
    if (!cBy.trim()) { showToast("Enter who prepped it"); return; }
    localStorage.setItem("prepCountedBy", cBy.trim());
    setBusy(true);
    try {
      const res = await api.completeTask(rid, list.id, completing.id, { batches: Number(cBatches) || 0, doneBy: cBy.trim(), containers });
      applyPrepResult(res);
      setList(res.list);
      showToast(`${completing.name}: ${cBatches} ${completing.taskType === "vessel" ? "vessel(s)" : `batch${Number(cBatches) !== 1 ? "es" : ""}`} prepped — inventory deducted${res.log ? ` (${fmtMoney(res.log.totalCost)})` : ""}`);
      setCompleting(null);
    } catch (e) { showToast(e?.response?.data?.detail || "Couldn't complete the task"); }
    finally { setBusy(false); }
  }

  async function toggleSchedule(p, schedule) {
    try {
      await api.updatePrepItem(rid, p.id, { name: p.name, sourceType: p.sourceType, controlNumber: p.controlNumber, recipeId: p.recipeId, vesselName: p.vesselName, vesselCapacity: p.vesselCapacity, parVessels: p.parVessels, par: p.par, track: p.track, schedule, note: p.note || "" });
      reloadPrepItems();
      showToast(`${p.name} → ${schedule === "daily" ? "Daily" : "One-off"}`);
    } catch (e) { showToast("Couldn't update the schedule"); }
  }

  async function saveRecurring(p, recurDays, fixedQty) {
    try {
      await api.updatePrepItem(rid, p.id, { name: p.name, sourceType: p.sourceType, controlNumber: p.controlNumber, recipeId: p.recipeId, vesselName: p.vesselName, vesselCapacity: p.vesselCapacity, parVessels: p.parVessels, par: p.par, track: p.track, schedule: "recurring", recurDays, fixedQty, note: p.note || "" });
      reloadPrepItems();
      showToast(`${p.name} → Recurring`);
      setEditingRecurring(null);
    } catch (e) { showToast(e?.response?.data?.detail || "Couldn't update the schedule"); }
  }

  async function removePrepItem(p) {
    if (!window.confirm(`Remove "${p.name}" from the standing prep items?`)) return;
    try {
      const result = await api.deletePrepItem(rid, p.id);
      if (result?.ok !== true) throw new Error("Prep item removal was not confirmed.");
      reloadPrepItems();
      showToast("Prep item removed");
    } catch (e) { showToast(e?.response?.data?.detail || e.message || "Couldn't remove the prep item"); }
  }

  async function addToDay(p) {
    try {
      const r = await api.addItemToList(rid, list.id, { prepItemId: p.id });
      setList(r.list);
      showToast(`${p.name} added to ${fmtDate(date)}'s list`);
    } catch (e) { showToast(e?.response?.data?.detail || "Couldn't add it to the list"); }
  }

  if (loadError) return <div role="alert" data-testid="prep-list-load-error">{loadError}<button onClick={load} className={btnGhost}>Retry prep list</button></div>;
  const tasks = (list?.tasks || []).filter((t) => !t.removed);
  const doneCount = tasks.filter((t) => t.batchesPlanned > 0 && t.batchesDone >= t.batchesPlanned).length;
  const oneOffs = prepItems.filter((p) => p.schedule === "oneoff");
  const onListIds = new Set(tasks.map((t) => t.prepItemId).filter(Boolean));

  return (
    <div data-testid="prep-list-view">
      {api.prepPlanningEnabled && <p>Standing prep settings are retained for reference. Edit reviewed planning settings in Setup; task execution cutover is pending.</p>}
      <div className={`${cardCls} p-4 mb-4 flex gap-3 flex-wrap items-end`}>
        <Field label="Prep-For Date"><input type="date" className={inpCls} data-testid="prep-list-date" value={date} onChange={(e) => setDate(e.target.value)} /></Field>
        {!list && loaded && <button className={btnAcc} onClick={generate} data-testid="generate-prep-list-button"><Plus size={14} /> Generate from Latest Count</button>}
        {list && (
          <>
            <Pill testId="list-status-pill" color={list.status === "released" ? "#10B981" : "#F59E0B"} bg={list.status === "released" ? "rgba(16,185,129,0.12)" : "rgba(245,158,11,0.12)"}>
              {list.status === "released" ? `Released${list.releasedBy ? ` by ${list.releasedBy}` : ""}` : "Draft — review & release"}
            </Pill>
            <Pill color="#94A3B8" bg="#1E293B">{doneCount}/{tasks.length} tasks done</Pill>
            {list.status === "draft" && (
              <>
                <button className={btnGhost} onClick={saveDraft} data-testid="save-draft-list-button">Save Adjustments</button>
                <Field label="Released By"><input className={inpCls} data-testid="released-by-input" placeholder="Manager name" value={releasedBy} onChange={(e) => setReleasedBy(e.target.value)} /></Field>
                <button className={btnAcc} onClick={release} data-testid="release-prep-list-button"><Send size={14} /> Release to Staff</button>
              </>
            )}
          </>
        )}
        <button className={btnGhost} disabled={api.prepPlanningEnabled} onClick={() => setShowAdd(true)} data-testid="add-prep-item-button"><Package size={14} /> Add Prep Item</button>
      </div>

      {!list && loaded && (
        <EmptyState text={`No prep list for ${fmtDate(date)} yet. Submit tonight's count (Evening Count tab), then generate the list here.`} />
      )}
      {list && (
        <>
          <div className="text-xs text-slate-500 mb-2">Generated from the {fmtDate(list.generatedFromDate)} evening count.</div>
          <div className={`${cardCls} overflow-hidden`}>
            <div className="overflow-x-auto">
              <table className="ops-table" data-testid="prep-tasks-table">
                <thead><tr><th>Prep Task</th><th>Counted</th><th>Par</th><th>Needed</th><th>Planned</th><th>Done</th><th></th></tr></thead>
                <tbody>
                  {tasks.map((t) => {
                    const remaining = Math.max(0, t.batchesPlanned - t.batchesDone);
                    const done = t.batchesPlanned > 0 && remaining === 0;
                    const isVessel = t.taskType === "vessel";
                    return (
                      <tr key={t.id} data-testid={`task-row-${t.id}`} style={done ? { opacity: 0.55 } : {}}>
                        <td>
                          <div className="font-semibold text-slate-200">{t.name}</div>
                          {t.vesselName && <div className="text-[11px] text-slate-400 mt-0.5">Prep into <b>{t.vesselName}</b>{isVessel && t.vesselCapacity ? ` (${num(t.vesselCapacity, 1)} each)` : ""}{t.controlNumber ? ` · from ${t.controlNumber}` : ""}</div>}
                          {t.note && <div className="text-[11px] text-amber-400 mt-0.5">{t.note}</div>}
                          {t.doneBy && <div className="text-[11px] text-slate-500 mt-0.5">Last prepped by {t.doneBy}</div>}
                        </td>
                        <td className="num">{t.uncounted ? <Pill color="#F59E0B" bg="rgba(245,158,11,0.12)">not counted</Pill> : `${num(t.counted, 1)} ${isVessel ? t.vesselName : t.yieldUOM}`}</td>
                        <td className="num">{num(t.par, 1)}{isVessel ? ` ${t.vesselName}` : ""}</td>
                        <td className="num">{num(t.neededUnits, 1)} {isVessel ? t.vesselName : t.yieldUOM}</td>
                        <td>
                          {list.status === "draft" ? (
                            <span className="flex items-center gap-1">
                              <input type="number" min="0" step="0.5" className={`${inpCls} w-20 py-1`} data-testid={`planned-${t.id}`}
                                value={plannedDrafts[t.id] ?? 0} onChange={(e) => setPlannedDrafts((p) => ({ ...p, [t.id]: e.target.value }))} />
                              <span className="text-[11px] text-slate-500">{isVessel ? t.vesselName : "batches"}</span>
                            </span>
                          ) : <span className="num">{num(t.batchesPlanned, 1)} {isVessel ? `× ${t.vesselName}` : "batches"}</span>}
                        </td>
                        <td>
                          {done
                            ? <span className="text-emerald-400 text-xs font-bold flex items-center gap-1" data-testid={`task-done-${t.id}`}><Check size={13} /> Done</span>
                            : <span className="num text-slate-300">{num(t.batchesDone, 1)}/{num(t.batchesPlanned, 1)}</span>}
                        </td>
                        <td>
                          {list.status === "released" && !done && (
                            <button className={btnAcc} onClick={() => openComplete(t)} disabled={busy} data-testid={`task-complete-${t.id}`}>
                              <Play size={13} /> Prepped
                            </button>
                          )}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </div>
        </>
      )}

      {prepItems.length > 0 && (
        <div className="mt-6">
          <SectionLabel>Standing Prep Items</SectionLabel>
          <div className={`${cardCls} overflow-hidden`} data-testid="standing-prep-items">
            <div className="overflow-x-auto">
              <table className="ops-table">
                <thead><tr><th>Item</th><th>Source</th><th>Vessel</th><th>Par</th><th>Schedule</th><th></th></tr></thead>
                <tbody>
                  {prepItems.map((p) => (
                    <tr key={p.id} data-testid={`standing-item-${p.id}`}>
                      <td className="font-semibold text-slate-200">{p.name}</td>
                      <td>{p.sourceType === "item" ? <Pill color="#06B6D4" bg="rgba(6,182,212,0.12)">ITEM · {p.controlNumber}</Pill> : <Pill color="#EAB308" bg="rgba(234,179,8,0.12)">PREP RECIPE</Pill>}</td>
                      <td className="text-slate-300">{p.vesselName}{p.sourceType === "item" && p.vesselCapacity ? ` (${num(p.vesselCapacity, 1)})` : ""}</td>
                      <td className="num">
                        {p.schedule === "recurring"
                          ? `${(p.recurDays || []).map(weekdayLabel).join("/")} · ${num(p.fixedQty, p.sourceType === "item" ? 1 : 0)} ${p.sourceType === "item" ? p.vesselName : ""}`
                          : p.sourceType === "item" ? `${num(p.parVessels, 1)} ${p.vesselName}` : (p.par ? num(p.par, 0) : "uses recipe's own par")}
                      </td>
                      <td>
                        <div className="flex gap-1">
                          <button className={p.schedule === "daily" ? btnAcc : btnGhost} style={{ padding: "4px 10px", fontSize: 11 }} disabled={api.prepPlanningEnabled} onClick={() => toggleSchedule(p, "daily")} data-testid={`schedule-daily-${p.id}`}>Daily</button>
                          <button className={p.schedule === "oneoff" ? btnAcc : btnGhost} style={{ padding: "4px 10px", fontSize: 11 }} disabled={api.prepPlanningEnabled} onClick={() => toggleSchedule(p, "oneoff")} data-testid={`schedule-oneoff-${p.id}`}>One-off</button>
                          {api.isPostgres && <button className={p.schedule === "recurring" ? btnAcc : btnGhost} style={{ padding: "4px 10px", fontSize: 11 }} disabled={api.prepPlanningEnabled} onClick={() => setEditingRecurring(p)} data-testid={`schedule-recurring-${p.id}`}>Recurring</button>}
                        </div>
                      </td>
                      <td>
                        <div className="flex gap-1.5 items-center">
                          {p.schedule === "oneoff" && list && !onListIds.has(p.id) && (
                            <button className={btnGhost} style={{ padding: "4px 10px", fontSize: 11 }} onClick={() => addToDay(p)} data-testid={`add-to-day-${p.id}`}>+ Add to {fmtDate(date)}</button>
                          )}
                          <button aria-label={`Delete ${p.name}`} className={btnDanger} disabled={api.prepPlanningEnabled} onClick={() => removePrepItem(p)} data-testid={`delete-prep-item-${p.id}`}><Trash2 size={13} /></button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
          {oneOffs.length > 0 && <div className="text-[11px] text-slate-500 mt-2">One-off items stay off the daily list — add them to a specific day when needed.</div>}
        </div>
      )}

      {showAdd && (
        <AddPrepItemModal rid={rid} track={track} items={items} dishes={dishes} showToast={showToast}
          onClose={() => setShowAdd(false)} onSaved={reloadPrepItems} />
      )}

      {editingRecurring && (
        <EditRecurringModal prepItem={editingRecurring} onClose={() => setEditingRecurring(null)} showToast={showToast}
          onSave={(recurDays, fixedQty) => saveRecurring(editingRecurring, recurDays, fixedQty)} />
      )}

      {completing && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm" data-testid="task-complete-modal">
          <div className={`${cardCls} w-full max-w-lg p-5 m-4 bg-[#161F30] max-h-[90vh] overflow-y-auto`}>
            <div className="flex justify-between items-center mb-3">
              <div className="font-display font-bold text-slate-100">Mark Prepped — {completing.name}</div>
              <button onClick={() => setCompleting(null)} className="text-slate-400 hover:text-white" data-testid="close-complete-modal"><X size={18} /></button>
            </div>
            <div className="grid grid-cols-2 gap-3 mb-3">
              <Field label={completing.taskType === "vessel" ? `${completing.vesselName}s Prepped (partial allowed)` : "Batches Prepped (partial allowed)"}>
                <input type="number" min="0.5" step="0.5" className={inpCls} data-testid="complete-batches-input" value={cBatches} onChange={(e) => setCBatches(e.target.value)} />
              </Field>
              <Field label="Prepped By"><input className={inpCls} data-testid="complete-by-input" placeholder="Name" value={cBy} onChange={(e) => setCBy(e.target.value)} /></Field>
            </div>
            <div className="text-xs text-slate-400 mb-3">
              {completing.taskType === "vessel"
                ? <>Completing deducts <b className="num">{num((Number(cBatches) || 0) * (completing.vesselCapacity || 0), 1)}</b> portion units of <b>{completing.controlNumber}</b> from inventory ({num(completing.vesselCapacity, 1)} per {completing.vesselName}) and stocks the prep inventory.</>
                : "Completing deducts raw ingredients from inventory per the recipe and stocks the prep inventory. Remaining batches stay open for someone else to finish."}
            </div>
            {completing.taskType !== "vessel" && (
              <>
                <SectionLabel>Break Into Service Containers (optional)</SectionLabel>
                {containers.map((c, i) => (
                  <div key={i} className="flex gap-2 items-end mb-2">
                    <Field label="Label"><input className={inpCls} data-testid={`container-label-${i}`} value={c.label} onChange={(e) => setContainers((cs) => cs.map((x, j) => j === i ? { ...x, label: e.target.value } : x))} /></Field>
                    <Field label={`Size (${completing.yieldUOM})`}><input type="number" step="1" className={`${inpCls} w-24`} value={c.size} onChange={(e) => setContainers((cs) => cs.map((x, j) => j === i ? { ...x, size: Number(e.target.value) || 0 } : x))} /></Field>
                    <Field label="Count"><input type="number" step="1" className={`${inpCls} w-20`} value={c.count} onChange={(e) => setContainers((cs) => cs.map((x, j) => j === i ? { ...x, count: Number(e.target.value) || 0 } : x))} /></Field>
                    <button aria-label="Remove container row" className="text-red-400 hover:text-red-300 pb-2" onClick={() => setContainers((cs) => cs.filter((_, j) => j !== i))}><Trash2 size={15} /></button>
                  </div>
                ))}
                <button className={`${btnGhost} mb-4`} onClick={() => setContainers((cs) => [...cs, { label: "Deli container", size: 32, count: 1 }])} data-testid="add-container-row"><Plus size={14} /> Add Container Type</button>
              </>
            )}
            <div className="flex gap-2 justify-end">
              <button className={btnGhost} onClick={() => setCompleting(null)}>Cancel</button>
              <button className={btnAcc} onClick={confirmComplete} disabled={busy} data-testid="confirm-task-complete-button">{busy ? "Working…" : "Confirm & Deduct Inventory"}</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

/* ---------------- Prep Inventory, Log & Report ---------------- */
function InventoryLog({ drafts, showError, rid, items, dishes, persistDishes, prepItems, prepStock, prepLogs, applyPrepResult, salesPeriod, showToast }) {
  const [busy, setBusy] = useState(false);
  const [rFrom, setRFrom] = useState(daysAgoISO(30));
  const [rTo, setRTo] = useState(todayISO());
  const [report, setReport] = useState(null);
  const prepRecipes = dishes.filter((d) => d.recipeType === "prep").map(normalizeRecipeSchema);
  const stockByRecipe = Object.fromEntries((prepStock || []).filter((s) => s.recipeId).map((s) => [s.recipeId, s]));
  const itemStocks = (prepStock || []).filter((s) => s.prepItemId);
  const recentLogs = [...(prepLogs || [])].sort((a, b) => (b.createdAt || "").localeCompare(a.createdAt || "")).slice(0, 12);

  const [metadata, editMetadata, clearMetadata] = useRetainedDraft(`prep-metadata:${rid}`, {}, drafts);
  const [metadataError, setMetadataError] = useState("");
  function updateMeta(recipe, field, val) {
    editMetadata(current => ({ ...current, [recipe.id]: { ...current[recipe.id], [field]: val } }));
  }
  async function saveMeta(recipe) {
    const submitted = metadata;
    const changes = submitted[recipe.id];
    if (!changes) return;
    const next = dishes.map(d => d.id === recipe.id ? { ...d, ...changes,
      ...(changes.prepPar !== undefined ? { prepPar: Number(changes.prepPar) || 0 } : {}) } : d);
    if (!(await confirmSave(() => persistDishes(next), message => { setMetadataError(message); showError(message); }))) return;
    const remaining = { ...submitted }; delete remaining[recipe.id];
    const cleared = clearMetadata(submitted, remaining);
    // Other unsaved recipe settings remain in the retained draft cache.
    if (cleared && Object.keys(remaining).length) editMetadata(remaining);
    setMetadataError(""); showToast("Prep settings saved");
  }

  async function handleApplySales() {
    setBusy(true);
    try {
      const res = await api.applyPrepSales(rid, salesPeriod.dishSales || {});
      applyPrepResult(res);
      const totalUsed = res.log.usage.reduce((s, u) => s + u.used, 0);
      showToast(`Prep usage from sales applied — ${num(totalUsed, 1)} yield units drawn down`);
    } catch (e) { showToast(e?.response?.data?.detail || "No prep usage found in the saved sales figures"); }
    finally { setBusy(false); }
  }

  async function handleUseContainer(recipeId, containerId) {
    try {
      const res = await api.useContainer(rid, { recipeId, containerId });
      applyPrepResult(res);
      showToast("Container moved to service");
    } catch (e) { showToast("Couldn't update container"); }
  }

  async function runReport() {
    try {
      setReport(await api.prepReport(rid, rFrom, rTo));
    } catch (e) { showToast("Couldn't build the report"); }
  }

  return (
    <div data-testid="prep-inventory-log">
      {metadataError && <p role="alert">{metadataError}</p>}
      {Object.keys(metadata).length > 0 && <p role="status">Unsaved prep settings. Use Save prep settings to confirm each recipe. Drafts survive tab changes; save before reloading or signing out.</p>}
      <div className="flex justify-end mb-3">
        <button className={btnGhost} onClick={handleApplySales} disabled={busy} data-testid="apply-sales-usage-button" title="Draw down prep inventory using the quantities entered in Sales Tracking">
          <PackageCheck size={15} /> Deduct Prep Usage from Sales
        </button>
      </div>

      <SectionLabel>Prep Inventory — On Hand & Service Containers</SectionLabel>
      {prepRecipes.length === 0 && itemStocks.length === 0 ? <EmptyState text="No prep recipes yet. Create one in Menu Costing with type 'Prep / Sub-Recipe', or add a prep item in the Prep List tab." /> : (
        <div className="grid gap-3 mb-6" style={{ gridTemplateColumns: "repeat(auto-fit,minmax(320px,1fr))" }} data-testid="prep-inventory-grid">
          {prepRecipes.map((r) => {
            const stock = stockByRecipe[r.id];
            const onHand = Number(stock?.onHand) || 0;
            const par = Number(r.prepPar) || 0;
            const low = par > 0 && onHand < par;
            return (
              <div key={r.id} className={`${cardCls} p-4`} data-testid={`prep-stock-${r.id}`}>
                <div className="flex justify-between items-start gap-2 mb-2">
                  <div>
                    <div className="font-semibold text-slate-100 text-sm">{r.name}</div>
                    <div className="text-[11px] text-slate-500">{FREQS.find((f) => f.id === (r.frequency || "daily"))?.label} · par {num(par, 0)} {r.yieldUOM}</div>
                  </div>
                  <Pill color={low ? "#F59E0B" : "#10B981"} bg={low ? "rgba(245,158,11,0.12)" : "rgba(16,185,129,0.12)"}>{num(onHand, 1)} {r.yieldUOM}</Pill>
                </div>
                <div className="h-1.5 rounded-full bg-[#0F1626] overflow-hidden mb-3">
                  <div className="h-full rounded-full transition-all" style={{ width: `${par > 0 ? Math.min(100, (onHand / par) * 100) : 0}%`, background: low ? "#F59E0B" : "#10B981" }} />
                </div>
                <div className="flex items-center gap-2 mb-2">
                  <span className="text-[11px] text-slate-500">Par:</span>
                  <input type="number" step="1" className={`${inpCls} w-20 py-1`} data-testid={`prep-par-${r.id}`} value={metadata[r.id]?.prepPar ?? r.prepPar ?? 0} onChange={(e) => updateMeta(r, "prepPar", e.target.value)} />
                  <span className="text-[11px] text-slate-500">Freq:</span>
                  <select className={`${inpCls} py-1 text-xs`} data-testid={`prep-freq-select-${r.id}`} value={metadata[r.id]?.frequency ?? r.frequency ?? "daily"} onChange={(e) => updateMeta(r, "frequency", e.target.value)}>
                    {FREQS.map((f) => <option key={f.id} value={f.id}>{f.label}</option>)}
                  </select>
                  <button className={btnGhost} disabled={!metadata[r.id]} onClick={() => saveMeta(r)} data-testid={`prep-save-meta-${r.id}`}>Save prep settings</button>
                </div>
                {(stock?.containers || []).length > 0 && (
                  <div className="mt-2 border-t border-[#22304A] pt-2">
                    <div className="text-[11px] uppercase tracking-wide text-slate-500 font-bold mb-1.5 flex items-center gap-1"><Layers size={11} /> Service Containers</div>
                    <div className="flex flex-col gap-1.5">
                      {stock.containers.map((c) => (
                        <div key={c.id} className="flex items-center justify-between text-xs bg-[#0F1626] rounded-md px-2.5 py-1.5 border border-[#28354A]" data-testid={`container-${c.id}`}>
                          <span className="text-slate-300">{c.count}× {c.label} ({num(c.size, 0)} {stock.yieldUOM} each)</span>
                          <button className="text-[11px] font-semibold hover:underline" style={{ color: "var(--acc)" }} data-testid={`use-container-${c.id}`} onClick={() => handleUseContainer(r.id, c.id)}>Send 1 to service</button>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            );
          })}
          {itemStocks.map((s) => {
            const def = prepItems.find((p) => p.id === s.prepItemId);
            const par = Number(def?.parVessels) || 0;
            const onHand = Number(s.onHand) || 0;
            const low = par > 0 && onHand < par;
            return (
              <div key={s.prepItemId} className={`${cardCls} p-4`} data-testid={`prep-stock-item-${s.prepItemId}`}>
                <div className="flex justify-between items-start gap-2 mb-2">
                  <div>
                    <div className="font-semibold text-slate-100 text-sm">{s.name}</div>
                    <div className="text-[11px] text-slate-500">{def?.schedule === "oneoff" ? "One-off" : "Daily"} · from {def?.controlNumber || "—"} · par {num(par, 1)} {s.yieldUOM}</div>
                  </div>
                  <Pill color={low ? "#F59E0B" : "#10B981"} bg={low ? "rgba(245,158,11,0.12)" : "rgba(16,185,129,0.12)"}>{num(onHand, 1)} {s.yieldUOM}</Pill>
                </div>
                <div className="h-1.5 rounded-full bg-[#0F1626] overflow-hidden">
                  <div className="h-full rounded-full transition-all" style={{ width: `${par > 0 ? Math.min(100, (onHand / par) * 100) : 0}%`, background: low ? "#F59E0B" : "#10B981" }} />
                </div>
              </div>
            );
          })}
        </div>
      )}

      <SectionLabel>Deduction Log</SectionLabel>
      {recentLogs.length === 0 ? <EmptyState text="No prep activity yet. Complete a prep task to see deductions here." /> : (
        <div className={`${cardCls} overflow-hidden mb-6`} data-testid="prep-log-table">
          <div className="overflow-x-auto">
            <table className="ops-table">
              <thead><tr><th>Date</th><th>Activity</th><th>Detail</th><th>Raw Cost</th></tr></thead>
              <tbody>
                {recentLogs.map((l, i) => (
                  <tr key={l.createdAt + i}>
                    <td>{fmtDate(l.date)}</td>
                    <td className="font-semibold text-slate-200">{l.name}</td>
                    <td className="text-xs text-slate-400">
                      {l.kind === "batch" && `+${num(l.produced, 1)} ${l.yieldUOM} produced · ${(l.usage || []).map((u) => `${u.controlNumber} −${num(u.units, 2)} ${u.purchaseUnit}`).join(", ")}`}
                      {l.kind === "sales_usage" && (l.usage || []).map((u) => `${u.name}: −${num(u.used, 1)} ${u.yieldUOM}`).join("; ")}
                      {l.kind === "container_use" && `${num(Math.abs(l.produced), 1)} ${l.yieldUOM} to service`}
                    </td>
                    <td className="num">{l.totalCost ? fmtMoney(l.totalCost) : "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      <SectionLabel>Prep Activity Report</SectionLabel>
      <div className={`${cardCls} p-4 mb-4 flex gap-3 flex-wrap items-end`}>
        <Field label="From"><input type="date" className={inpCls} data-testid="report-from" value={rFrom} onChange={(e) => setRFrom(e.target.value)} /></Field>
        <Field label="To"><input type="date" className={inpCls} data-testid="report-to" value={rTo} onChange={(e) => setRTo(e.target.value)} /></Field>
        <button className={btnAcc} onClick={runReport} data-testid="run-prep-report-button">Run Report</button>
      </div>
      {report && (
        <div className={`${cardCls} overflow-hidden`} data-testid="prep-report-table">
          <div className="overflow-x-auto">
            <table className="ops-table">
              <thead><tr><th>Prep Item</th><th>Counts Recorded</th><th>Prepped</th><th>Used via Sales</th><th>To Service</th><th>Raw Cost</th></tr></thead>
              <tbody>
                {report.recipes.map((r) => (
                  <tr key={r.recipeId} data-testid={`report-row-${r.recipeId}`}>
                    <td className="font-semibold text-slate-200">{r.name}</td>
                    <td className="text-xs text-slate-400">
                      {r.counts.length === 0 ? "—" : r.counts.map((c) => `${fmtDate(c.date)}: ${num(c.onHand, 1)}${c.by ? ` (${c.by})` : ""}`).join(" · ")}
                    </td>
                    <td className="num">{num(r.produced, 1)} {r.yieldUOM}</td>
                    <td className="num">{num(r.usedBySales, 1)} {r.yieldUOM}</td>
                    <td className="num">{num(r.sentToService, 1)} {r.yieldUOM}</td>
                    <td className="num">{fmtMoney(r.producedCost)}</td>
                  </tr>
                ))}
                {(report.prepItems || []).map((r) => (
                  <tr key={r.prepItemId} data-testid={`report-row-${r.prepItemId}`}>
                    <td className="font-semibold text-slate-200">{r.name} <Pill color="#06B6D4" bg="rgba(6,182,212,0.12)">ITEM</Pill></td>
                    <td className="text-xs text-slate-400">
                      {r.counts.length === 0 ? "—" : r.counts.map((c) => `${fmtDate(c.date)}: ${num(c.onHand, 1)}${c.by ? ` (${c.by})` : ""}`).join(" · ")}
                    </td>
                    <td className="num">{num(r.produced, 1)} {r.yieldUOM}</td>
                    <td className="num">—</td>
                    <td className="num">—</td>
                    <td className="num">{fmtMoney(r.producedCost)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="px-4 py-3 text-xs text-slate-400 border-t border-[#28354A]">
            {report.sessions.length} count session{report.sessions.length !== 1 ? "s" : ""} in range · Total raw cost prepped: <b className="num">{fmtMoney(report.totals.producedCost)}</b>
          </div>
        </div>
      )}
    </div>
  );
}

/* ---------------- Planning: projections, overrides, PIN, AI par advisor ---------------- */
function Planning({ showError, rid, dishes, prepItems, prepCapabilities, persistDishes, showToast }) {
  const overridesHeld = prepCapabilities?.listsAvailable === false || api.prepDayTasksEnabled;
  const advisorHeld = prepCapabilities?.reportingAvailable === false || api.prepPlanningEnabled || api.prepBatchesEnabled;
  const prepRecipes = dishes.filter((d) => d.recipeType === "prep").map(normalizeRecipeSchema);
  const [proj, setProj] = useState({ date: tomorrowISO(), amount: "", note: "" });
  const [projList, setProjList] = useState([]);
  const [ovr, setOvr] = useState({ date: tomorrowISO(), type: "add", target: "", customName: "", par: "", batches: 1, note: "" });
  const [ovrList, setOvrList] = useState([]);
  const [pin, setPin] = useState("");
  const [pinInfo, setPinInfo] = useState(null);
  const [recs, setRecs] = useState([]);
  const [trends, setTrends] = useState("");
  const [advisorBusy, setAdvisorBusy] = useState(false);

  useEffect(() => {
    api.getProjections(rid).then(setProjList).catch(() => {});
    if (!overridesHeld) api.listOverrides(rid).then(setOvrList).catch(() => {});
    api.getStaffPin(rid).then((p) => { setPinInfo(p); setPin(p.staffPin); }).catch(() => {});
    if (!advisorHeld) api.getParRecs(rid).then(setRecs).catch(() => {});
  }, [rid, overridesHeld, advisorHeld]);

  const targetName = (o) => prepRecipes.find((r) => r.id === o.recipeId)?.name || prepItems.find((p) => p.id === o.prepItemId)?.name || o.customName || "item";

  async function saveProjection() {
    if (!(Number(proj.amount) > 0)) { showToast("Enter a projected sales amount"); return; }
    try {
      await api.putProjection(rid, { date: proj.date, amount: Number(proj.amount), note: proj.note });
      showToast("Projected sales saved");
      setProj((p) => ({ ...p, amount: "", note: "" }));
      api.getProjections(rid).then(setProjList).catch(() => {});
    } catch (e) { showToast("Couldn't save the projection"); }
  }

  async function saveOverride() {
    if (overridesHeld) return;
    const recipeId = ovr.target.startsWith("r:") ? ovr.target.slice(2) : null;
    const prepItemId = ovr.target.startsWith("p:") ? ovr.target.slice(2) : null;
    if (ovr.type !== "add" && !recipeId && !prepItemId) { showToast("Pick a prep item for this override"); return; }
    if (ovr.type === "add" && !recipeId && !prepItemId && !ovr.customName.trim()) { showToast("Name the one-off item or pick a prep recipe"); return; }
    try {
      await api.addOverride(rid, { date: ovr.date, type: ovr.type, recipeId, prepItemId, customName: ovr.customName, par: ovr.par !== "" ? Number(ovr.par) : null, batches: Number(ovr.batches) || 1, note: ovr.note });
      showToast("Day override saved — it applies when the list for that date is generated");
      setOvr((o) => ({ ...o, note: "", customName: "" }));
      api.listOverrides(rid).then(setOvrList).catch(() => {});
    } catch (e) { showToast(e?.response?.data?.detail || "Couldn't save the override"); }
  }

  async function removeOverride(id) {
    if (overridesHeld) return;
    try { await api.deleteOverride(rid, id); setOvrList((l) => l.filter((o) => o.id !== id)); showToast("Override removed"); }
    catch (e) { showError(e?.response?.data?.detail || "Couldn't confirm removal. The override remains visible for review."); }
  }

  async function savePin() {
    try {
      await api.setStaffPin(rid, pin);
      showToast("Staff PIN updated");
      api.getStaffPin(rid).then(setPinInfo).catch(() => {});
    } catch (e) { showToast(e?.response?.data?.detail || "Couldn't update the PIN"); }
  }

  async function runAdvisor() {
    if (advisorHeld) return;
    setAdvisorBusy(true);
    try {
      const r = await api.runParAdvisor(rid);
      setRecs((prev) => [...r.recommendations, ...prev]);
      setTrends(r.trends || "");
      showToast(r.sparse ? "Not enough history for firm recommendations yet — trends recorded" : `${r.recommendations.length} recommendation${r.recommendations.length !== 1 ? "s" : ""} generated`);
    } catch (e) { showToast(e?.response?.data?.detail || "The advisor couldn't run right now"); }
    finally { setAdvisorBusy(false); }
  }

  async function applyRec(rec) {
    if (advisorHeld) return;
    try {
      const saved = await persistDishes(dishes.map((d) => d.id === rec.recipeId ? { ...d, prepPar: rec.recommendedPar } : d));
      if (!saved) return;
      await api.applyParRec(rid, rec.id);
      setRecs((l) => l.filter((x) => x.id !== rec.id));
      showToast(`Par for ${rec.recipeName} updated to ${num(rec.recommendedPar, 0)}`);
    } catch (e) { showError("Couldn't finish applying the recommendation. Review the saved par before retrying."); }
  }
  async function dismissRec(rec) {
    await api.dismissParRec(rid, rec.id).catch(() => {});
    setRecs((l) => l.filter((x) => x.id !== rec.id));
  }

  return (
    <div data-testid="planning-view">
      <div className="grid gap-4" style={{ gridTemplateColumns: "repeat(auto-fit,minmax(340px,1fr))" }}>
        <div className={`${cardCls} p-5`} data-testid="projections-card">
          <SectionLabel>Projected Sales (Manual Daily Entry)</SectionLabel>
          <div className="flex gap-2 flex-wrap items-end mb-3">
            <Field label="Date"><input type="date" className={inpCls} data-testid="projection-date" value={proj.date} onChange={(e) => setProj((p) => ({ ...p, date: e.target.value }))} /></Field>
            <Field label="Amount ($)"><input type="number" step="100" className={`${inpCls} w-28`} data-testid="projection-amount" value={proj.amount} onChange={(e) => setProj((p) => ({ ...p, amount: e.target.value }))} placeholder="4500" /></Field>
            <Field label="Note"><input className={inpCls} data-testid="projection-note" value={proj.note} onChange={(e) => setProj((p) => ({ ...p, note: e.target.value }))} placeholder="e.g. Friday rush" /></Field>
            <button className={btnAcc} onClick={saveProjection} data-testid="projection-save-button"><Plus size={14} /> Save</button>
          </div>
          {projList.slice(0, 6).map((p) => (
            <div key={p.date} className="flex justify-between text-xs py-1.5 border-b border-[#22304A] last:border-0">
              <span className="text-slate-300">{fmtDate(p.date)}{p.note ? ` — ${p.note}` : ""}</span>
              <span className="num font-bold">{fmtMoney(p.amount)}</span>
            </div>
          ))}
          <div className="text-[11px] text-slate-500 mt-2">Toast report import comes later — once you share a sample export or API access.</div>
        </div>

        {overridesHeld ? <p data-testid="prep-overrides-unavailable">Historical day adjustments are retained for review. Use reviewed dated prep tasks for current adjustments.</p> : <div className={`${cardCls} p-5`} data-testid="overrides-card">
          <SectionLabel>One-Day Adjustments (don't change the standing list)</SectionLabel>
          <div className="flex gap-2 flex-wrap items-end mb-2">
            <Field label="For Date"><input type="date" className={inpCls} data-testid="override-date" value={ovr.date} onChange={(e) => setOvr((o) => ({ ...o, date: e.target.value }))} /></Field>
            <Field label="Type">
              <select className={inpCls} data-testid="override-type" value={ovr.type} onChange={(e) => setOvr((o) => ({ ...o, type: e.target.value }))}>
                <option value="add">Add one-off item</option>
                <option value="par">Change par for this date</option>
                <option value="remove">Remove item for this date</option>
              </select>
            </Field>
            <Field label="Prep Item">
              <select className={inpCls} data-testid="override-recipe" value={ovr.target} onChange={(e) => setOvr((o) => ({ ...o, target: e.target.value }))}>
                <option value="">— {ovr.type === "add" ? "custom / none" : "select"} —</option>
                <optgroup label="Prep recipes">{prepRecipes.map((r) => <option key={r.id} value={`r:${r.id}`}>{r.name}</option>)}</optgroup>
                {prepItems.length > 0 && <optgroup label="Container prep items">{prepItems.map((p) => <option key={p.id} value={`p:${p.id}`}>{p.name}</option>)}</optgroup>}
              </select>
            </Field>
            {ovr.type === "add" && !ovr.target && <Field label="Custom Item Name"><input className={inpCls} data-testid="override-custom-name" value={ovr.customName} onChange={(e) => setOvr((o) => ({ ...o, customName: e.target.value }))} placeholder="e.g. Catering tray sauce" /></Field>}
            {ovr.type === "par" && <Field label="Par for That Date"><input type="number" className={`${inpCls} w-24`} data-testid="override-par" value={ovr.par} onChange={(e) => setOvr((o) => ({ ...o, par: e.target.value }))} /></Field>}
            {ovr.type === "add" && <Field label="Batches"><input type="number" min="1" step="1" className={`${inpCls} w-20`} data-testid="override-batches" value={ovr.batches} onChange={(e) => setOvr((o) => ({ ...o, batches: e.target.value }))} /></Field>}
            <Field label="Note"><input className={inpCls} data-testid="override-note" value={ovr.note} onChange={(e) => setOvr((o) => ({ ...o, note: e.target.value }))} placeholder="Why? (catering, holiday…)" /></Field>
            <button className={btnAcc} onClick={saveOverride} data-testid="override-add-button"><Plus size={14} /> Add Override</button>
          </div>
          {ovrList.length > 0 && ovrList.slice(0, 8).map((o) => (
            <div key={o.id} className="flex justify-between items-center text-xs py-1.5 border-b border-[#22304A] last:border-0" data-testid={`override-row-${o.id}`}>
              <span className="text-slate-300">
                <Pill color="#EAB308" bg="rgba(234,179,8,0.12)">{o.type}</Pill> {fmtDate(o.date)} — {targetName(o)}
                {o.par !== null && o.par !== undefined && o.type === "par" ? ` → par ${num(o.par, 0)}` : ""}
                {o.type === "add" ? ` × ${num(o.batches, 0)} batch` : ""}
                {o.note ? ` (${o.note})` : ""}
              </span>
              <button aria-label={`Remove override for ${targetName(o)}`} className="text-red-400 hover:text-red-300" onClick={() => removeOverride(o.id)} data-testid={`override-delete-${o.id}`}><Trash2 size={13} /></button>
            </div>
          ))}
        </div>

        }
        <div className={`${cardCls} p-5`} data-testid="staff-pin-card">
          <SectionLabel>Staff Prep Sheet PIN</SectionLabel>
          <div className="text-xs text-slate-400 mb-3">
            Staff open the <b>Prep Sheet</b> (button in the header) on a shared kitchen phone or tablet and enter this PIN. They see only today's prep tasks — no costs, no inventory levels, no editing.
          </div>
          <div className="flex gap-2 items-end">
            <Field label={`PIN ${pinInfo && !pinInfo.custom ? "(default)" : ""}`}><input className={`${inpCls} w-28`} data-testid="staff-pin-input" value={pin} onChange={(e) => setPin(e.target.value)} maxLength={8} /></Field>
            <button className={btnGhost} onClick={savePin} data-testid="staff-pin-save-button">Save PIN</button>
          </div>
        </div>

        {advisorHeld ? <p data-testid="prep-advisor-unavailable">Historical par advice is unavailable for current planning. Use reviewed prep observations and planning settings.</p> : <div className={`${cardCls} p-5`} data-testid="par-advisor-card">
          <SectionLabel>AI Par Advisor</SectionLabel>
          <div className="text-xs text-slate-400 mb-3">
            Sous analyzes evening counts, amounts prepped, usage via sales, and projections, then recommends par changes. Recommendations are advisory — nothing changes until you tap Apply. It needs a few weeks of real counts before firm recommendations; until then it reports trends.
          </div>
          <button className={`${btnAcc} mb-3`} onClick={runAdvisor} disabled={advisorBusy} data-testid="run-par-advisor-button">
            <Sparkles size={14} /> {advisorBusy ? "Analyzing…" : "Analyze & Recommend"}
          </button>
          {trends && <div className="text-xs text-slate-300 bg-[#0F1626] border border-[#28354A] rounded-lg p-3 mb-3" data-testid="advisor-trends">{trends}</div>}
          {recs.map((r) => (
            <div key={r.id} className="border border-[#28354A] rounded-lg p-3 mb-2 bg-[#0F1626]" data-testid={`par-rec-${r.id}`}>
              <div className="flex justify-between items-center gap-2 mb-1">
                <span className="font-semibold text-sm text-slate-100">{r.recipeName}</span>
                <span className="num text-xs"><span className="text-slate-400">{num(r.currentPar, 0)}</span> <span style={{ color: "var(--acc)" }}>→ {num(r.recommendedPar, 0)}</span></span>
              </div>
              <div className="text-xs text-slate-400 mb-2">{r.reasoning}</div>
              <div className="flex gap-2">
                <button className={btnAcc} onClick={() => applyRec(r)} data-testid={`par-apply-${r.id}`}><Check size={13} /> Apply</button>
                <button className={btnGhost} onClick={() => dismissRec(r)} data-testid={`par-dismiss-${r.id}`}>Dismiss</button>
              </div>
            </div>
          ))}
        </div>}
      </div>
    </div>
  );
}
