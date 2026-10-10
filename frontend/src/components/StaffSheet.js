import React, { useEffect, useMemo, useRef, useState } from "react";
import { Lock, X, Check, ChevronDown, ChevronUp, ChefHat, ClipboardList, Inbox, Bell, BellOff, Save } from "lucide-react";
import { RESTAURANTS, num, fmtDate, isCountActive, todayISO } from "../lib/calc";
import * as api from "../lib/api";
import { StaffCountDrafts } from "./StaffCountDrafts";
import { StaffPrepCountDrafts } from "./StaffPrepCounts";
import { StaffPrepTaskPlan } from "./StaffPrepTasks";
import { enablePushNotifications, disablePushNotifications, pushSupported } from "../lib/push";
import { inpCls, btnAcc, btnGhost, cardCls, Pill } from "./common";
import { useCountSheet, CountSheetControls, CountSheetBanner, CountSheetList, SaveAllCountsButton } from "./CountSheet";

const TRACKS = [
  { id: "daily", label: "Daily Prep" },
  { id: "bulk", label: "Bulk Prep" },
];

// Employee-facing task portal views. "tasks" is the default landing screen
// (an inbox of anything a manager assigned/scheduled); "prep" and "counts"
// are the two task types staff can dive into directly.
const VIEWS = [
  { id: "tasks", label: "Tasks", icon: Inbox },
  { id: "prep", label: "Prep", icon: ChefHat },
  { id: "counts", label: "Counts", icon: ClipboardList },
];

export function StaffSheet({ onClose, onElevate, drafts }) {
  const privatePrepCountDrafts = useRef(new Map());
  const taskRequests = useRef(0);
  useEffect(() => () => { taskRequests.current += 1; }, []);
  const prepCountDrafts = drafts || privatePrepCountDrafts.current;
  const [rid, setRid] = useState("");
  const [track, setTrack] = useState("daily");
  const [pin, setPin] = useState("");
  const [err, setErr] = useState("");
  const [unlocked, setUnlocked] = useState(false);
  const [unlocking, setUnlocking] = useState(false);
  const [view, setView] = useState("tasks");

  // Roster picker — shown between PIN entry and the main portal when this
  // restaurant has named staff set up (Staff tab); identifies who is tapping
  // in so tasks/counts get attributed and Owner/Admin can be elevated.
  const [roster, setRoster] = useState(null);
  const [identifying, setIdentifying] = useState(false);
  const [staffName, setStaffName] = useState("");
  const [staffId, setStaffId] = useState(null);

  // Prep view state
  const [sheet, setSheet] = useState(null);
  const [completing, setCompleting] = useState(null);
  const [name, setName] = useState("");
  const [batches, setBatches] = useState(1);
  const [expanded, setExpanded] = useState({});
  const [busy, setBusy] = useState(false);

  // Task inbox state
  const [tasks, setTasks] = useState(null);
  const [completingTask, setCompletingTask] = useState(null);
  const [taskName, setTaskName] = useState("");
  const [taskBusy, setTaskBusy] = useState(false);

  // Counts view state
  const [counts, setCounts] = useState(null);
  const [countsName, setCountsName] = useState("");

  // Push notifications
  const [pushOn, setPushOn] = useState(false);
  const [pushBusy, setPushBusy] = useState(false);

  const restaurant = RESTAURANTS.find((r) => r.id === rid);

  useEffect(() => {
    if (!unlocked || !pushSupported()) return;
    navigator.serviceWorker.ready
      .then((reg) => reg.pushManager.getSubscription())
      .then((sub) => setPushOn(!!sub))
      .catch(() => {});
  }, [unlocked]);

  async function unlock() {
    setErr("");
    if (!rid) { setErr("Pick your restaurant first"); return; }
    setUnlocking(true);
    try {
      const v = await api.verifyStaffPin(rid, pin);
      if (!v.ok) { setErr("Wrong PIN — check with your manager"); return; }
      if (v.staff && v.staff.length > 0) { setRoster(v.staff); return; }
      setUnlocked(true);
      setView("tasks");
      await refreshTasks();
    } catch (e) { setErr(e?.response?.data?.detail || "Couldn't unlock — try again"); }
    finally { setUnlocking(false); }
  }

  async function identify(staffId) {
    setErr("");
    setIdentifying(true);
    try {
      if (api.staffPrepTasksEnabled) {
        const member = roster?.find(m => m.id === staffId);
        if (!member) throw new Error("Choose a current roster member");
        setStaffId(member.id); setStaffName(member.name); setTaskName(member.name); setCountsName(member.name);
        setRoster(null); setUnlocked(true); setView("tasks"); await refreshTasks(); return;
      }
      const r = await api.identifyStaffMember(rid, pin, staffId);
      if (r.role === "owner_admin" && r.session) { onElevate?.(r.session); return; }
      setStaffName(r.name || "");
      setTaskName(r.name || "");
      setCountsName(r.name || "");
      setRoster(null);
      setUnlocked(true);
      setView("tasks");
      await refreshTasks();
    } catch (e) { setErr(e?.response?.data?.detail || "Couldn't identify — try again"); }
    finally { setIdentifying(false); }
  }

  function lock() {
    taskRequests.current += 1;
    setCompletingTask(null);
    for (const key of prepCountDrafts.keys()) if (key.startsWith("staff-prep-submit:")||key.startsWith("staff-production-submit:")) prepCountDrafts.delete(key);
    setUnlocked(false);
    setPin("");
    setRoster(null);
    setStaffName("");
    setStaffId(null);
    setSheet(null);
    setTasks(null);
    setCounts(null);
  }

  async function togglePush() {
    setPushBusy(true);
    setErr("");
    try {
      if (pushOn) { await disablePushNotifications(rid, pin); setPushOn(false); }
      else { await enablePushNotifications(rid, pin); setPushOn(true); }
    } catch (e) { setErr(e?.message || "Couldn't update notification settings"); }
    finally { setPushBusy(false); }
  }

  // ---------------- Task inbox ----------------
  async function refreshTasks() {
    const sequence = ++taskRequests.current;
    setTasks(null); setCompletingTask(null);
    try {
      const result = await api.staffTaskInbox(rid, pin);
      if (!Array.isArray(result?.tasks)) throw new Error("Task inbox was not confirmed.");
      if (sequence === taskRequests.current) setTasks(result);
    } catch (e) {
      if (sequence === taskRequests.current) setTasks(e?.response?.status === 410 ? { retired: true } : { unavailable: true });
    }
  }

  async function markTaskDone() {
    setErr("");
    if (!taskName.trim()) { setErr("Enter your name so we know who did it"); return; }
    setTaskBusy(true);
    try {
      await api.staffCompleteStaffTask(rid, completingTask.id, { pin, doneBy: taskName.trim() });
      setCompletingTask(null);
      await refreshTasks();
    } catch (e) { setErr(e?.response?.data?.detail || "Couldn't save — tell your manager"); }
    finally { setTaskBusy(false); }
  }

  // ---------------- Prep view ----------------
  async function loadPrep() {
    if (api.staffPrepTasksEnabled) return;
    try { setSheet(await api.staffPrepsheet(rid, pin, track)); } catch { /* keep current */ }
  }
  useEffect(() => {
    if (unlocked && view === "prep") loadPrep();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [unlocked, view, track]);

  async function markDone() {
    setErr("");
    if (!name.trim()) { setErr("Enter your name so we know who prepped it"); return; }
    setBusy(true);
    try {
      await api.staffCompleteTask(rid, { pin, listId: sheet.listId, taskId: completing.id, batches: Number(batches) || 0, doneBy: name.trim() });
      setCompleting(null);
      await loadPrep();
    } catch (e) { setErr(e?.response?.data?.detail || "Couldn't save — tell your manager"); }
    finally { setBusy(false); }
  }

  // ---------------- Counts view ----------------
  async function loadCounts() {
    try {
      setCounts(await api.staffCounts(rid, pin));
    } catch { /* keep current */ }
  }
  useEffect(() => {
    if (unlocked && view === "counts" && !api.actualInventoryEnabled) loadCounts();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [unlocked, view]);

  async function saveCounts(entries, countDate) {
    const result = await api.staffSaveCounts(rid, { pin, doneBy: countsName.trim(), countDate, counts: entries });
    loadCounts();
    return result;
  }

  return (
    <div className="fixed inset-0 z-[60] bg-[#0B0F17] overflow-y-auto" data-testid="staff-sheet">
      <div className="max-w-[640px] mx-auto px-4 py-6 pb-24">
        <div className="flex justify-between items-center mb-6">
          <div className="flex items-center gap-2.5">
            <span className="w-9 h-9 rounded-xl flex items-center justify-center bg-[#F97316]"><ChefHat size={18} className="text-[#0B0F17]" /></span>
            <div>
              <div className="font-display font-bold text-slate-100">Employee Tasks</div>
              <div className="text-[10px] uppercase tracking-[0.14em] text-slate-500 font-bold">Staff View — Tasks Only</div>
            </div>
          </div>
          <button onClick={onClose} className="p-2 text-slate-400 hover:text-white transition" data-testid="staff-sheet-close"><X size={20} /></button>
        </div>

        {!unlocked && roster ? (
          <div className={`${cardCls} p-6`} data-testid="staff-roster-picker">
            <div className="flex items-center gap-2 mb-4"><Lock size={16} style={{ color: "#F97316" }} /><span className="font-display font-bold text-slate-100">Who are you?</span></div>
            <div className="flex flex-col gap-2">
              {roster.map((m) => (
                <button key={m.id} onClick={() => identify(m.id)} disabled={identifying} data-testid={`staff-roster-pick-${m.id}`}
                  className={`${cardCls} p-3 text-left font-bold text-slate-100 hover:border-[var(--acc,#F97316)] transition`}>
                  {m.name}
                </button>
              ))}
            </div>
            <button className={`${btnGhost} mt-4`} onClick={() => setRoster(null)} data-testid="staff-roster-back">Back</button>
            {err && <div className="text-red-400 text-xs mt-3" data-testid="staff-error">{err}</div>}
          </div>
        ) : !unlocked ? (
          <div className={`${cardCls} p-6`} data-testid="staff-pin-gate">
            <div className="flex items-center gap-2 mb-4"><Lock size={16} style={{ color: "#F97316" }} /><span className="font-display font-bold text-slate-100">Enter your store's staff PIN</span></div>
            <div className="flex gap-2 mb-4 flex-wrap">
              {RESTAURANTS.map((r) => (
                <button key={r.id} onClick={() => setRid(r.id)} data-testid={`staff-store-${r.id}`}
                  className={`rounded-full px-4 py-2 text-sm font-bold border transition ${rid === r.id ? "text-[#0B0F17]" : "text-slate-400 bg-[#161F30] border-[#28354A]"}`}
                  style={rid === r.id ? { background: r.accent, borderColor: r.accent } : {}}>
                  {r.short}
                </button>
              ))}
            </div>
            <div className="flex gap-2">
              <input type="password" inputMode="numeric" className={`${inpCls} flex-1 text-center text-xl tracking-[0.4em]`} data-testid="staff-pin-entry"
                placeholder="••••" maxLength={8} value={pin} onChange={(e) => setPin(e.target.value)}
                onKeyDown={(e) => { if (e.key === "Enter") unlock(); }} />
              <button className={btnAcc} onClick={unlock} disabled={unlocking} data-testid="staff-unlock-button">{unlocking ? "Unlocking…" : "Unlock"}</button>
            </div>
            {err && <div className="text-red-400 text-xs mt-3" data-testid="staff-error">{err}</div>}
          </div>
        ) : (
          <>
            <div className="flex justify-between items-center mb-4 flex-wrap gap-2">
              <div className="flex gap-2 flex-wrap" data-testid="staff-view-selector">
                {VIEWS.map((v) => {
                  const Icon = v.icon;
                  return (
                    <button key={v.id} onClick={() => setView(v.id)} data-testid={`staff-view-${v.id}`}
                      className={v.id === view ? btnAcc : btnGhost}>
                      <Icon size={14} /> {v.label}
                    </button>
                  );
                })}
              </div>
              <div className="flex gap-2">
                {staffName && <span className="text-xs text-slate-500 self-center" data-testid="staff-identified-as">{api.staffPrepTasksEnabled ? "Selected roster name: " : "Signed in as "}{staffName}</span>}
                {pushSupported() && (
                  <button className={btnGhost} onClick={togglePush} disabled={pushBusy} data-testid="staff-push-toggle">
                    {pushOn ? <Bell size={13} /> : <BellOff size={13} />} {pushOn ? "Notifications On" : "Enable Notifications"}
                  </button>
                )}
                <button className={btnGhost} onClick={lock} data-testid="staff-lock-button"><Lock size={13} /> Lock</button>
              </div>
            </div>

            {err && <div className="text-red-400 text-xs mb-3" data-testid="staff-error">{err}</div>}
            {api.nativePurchasesEnabled && <div className={`${cardCls} p-4 mb-4`} data-testid="staff-purchase-handoff">
              <p className="font-semibold">Deliveries and purchase receipts</p>
              <p className="text-sm">Give all supplier invoices, receipts and credits to your manager for Invoice Master. Your manager retains the complete source, verifies what arrived and the date received, then posts the purchase. Prep and task completion do not record a purchase.</p>
            </div>}

            {view === "tasks" && (
              <TasksView restaurant={restaurant} tasks={tasks} onRefresh={refreshTasks}
                onOpenPrep={() => setView("prep")} onOpenCounts={() => setView("counts")}
                onComplete={(t) => { setCompletingTask(t); setTaskName(staffName); setErr(""); }} />
            )}

            {view === "prep" && (
              api.staffPrepTasksEnabled ? <><select aria-label="Staff prep track" className={inpCls} value={track} onChange={e=>setTrack(e.target.value)}>{TRACKS.map(t=><option key={t.id} value={t.id}>{t.label}</option>)}</select><StaffPrepTaskPlan key={rid} rid={rid} pin={pin} staffId={staffId} track={track} drafts={prepCountDrafts}/></> : <PrepView restaurant={restaurant} track={track} setTrack={setTrack} sheet={sheet} onRefresh={loadPrep}
                expanded={expanded} setExpanded={setExpanded}
                onComplete={(t) => { setCompleting(t); setBatches(t.remaining); setName(staffName); setErr(""); }} />
            )}

            {view === "counts" && (
              <><div>{api.staffPrepCountsEnabled && <StaffPrepCountDrafts key={`prep:${rid}`} rid={rid} pin={pin} counterName={staffName || countsName} drafts={prepCountDrafts}/>}</div>
              {api.actualInventoryEnabled ? <StaffCountDrafts key={rid} restaurantId={rid} pin={pin} counterName={staffName || countsName} /> : <CountsView restaurant={restaurant} counts={counts} onRefresh={loadCounts}
                name={countsName} setName={setCountsName} onSave={saveCounts} setErr={setErr} />
              }</>
            )}
          </>
        )}
      </div>

      {completing && (
        <div className="fixed inset-0 z-[70] flex items-center justify-center bg-black/60 backdrop-blur-sm" data-testid="staff-complete-modal">
          <div className={`${cardCls} w-full max-w-sm p-5 m-4 bg-[#161F30]`}>
            <div className="font-display font-bold text-slate-100 mb-3">Mark Prepped — {completing.name}</div>
            <div className="flex flex-col gap-3">
              <label className="flex flex-col gap-1 text-xs text-slate-400 font-semibold">Your Name
                <input className={inpCls} data-testid="staff-name-input" placeholder="e.g. Maria" value={name} onChange={(e) => setName(e.target.value)} />
              </label>
              <label className="flex flex-col gap-1 text-xs text-slate-400 font-semibold">Batches Prepped (of {num(completing.remaining, 1)} remaining)
                <input type="number" min="0.5" step="0.5" className={inpCls} data-testid="staff-batches-input" value={batches} onChange={(e) => setBatches(e.target.value)} />
              </label>
            </div>
            <div className="flex gap-2 justify-end mt-4">
              <button className={btnGhost} onClick={() => setCompleting(null)}>Cancel</button>
              <button className={btnAcc} onClick={markDone} disabled={busy} data-testid="staff-confirm-done-button">{busy ? "Saving…" : "Confirm"}</button>
            </div>
          </div>
        </div>
      )}

      {completingTask && (
        <div className="fixed inset-0 z-[70] flex items-center justify-center bg-black/60 backdrop-blur-sm" data-testid="staff-task-complete-modal">
          <div className={`${cardCls} w-full max-w-sm p-5 m-4 bg-[#161F30]`}>
            <div className="font-display font-bold text-slate-100 mb-3">Mark Done — {completingTask.title}</div>
            <label className="flex flex-col gap-1 text-xs text-slate-400 font-semibold">Your Name
              <input className={inpCls} data-testid="staff-task-name-input" placeholder="e.g. Maria" value={taskName} onChange={(e) => setTaskName(e.target.value)} />
            </label>
            <div className="flex gap-2 justify-end mt-4">
              <button className={btnGhost} onClick={() => setCompletingTask(null)}>Cancel</button>
              <button className={btnAcc} onClick={markTaskDone} disabled={taskBusy} data-testid="staff-task-confirm-done-button">{taskBusy ? "Saving…" : "Confirm"}</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function TasksView({ restaurant, tasks, onRefresh, onOpenPrep, onOpenCounts, onComplete }) {
  if (!tasks) return <p role="status">Loading tasks…</p>;
  return (
    <>
      <div className="flex justify-between items-center mb-4 flex-wrap gap-2">
        <div>
          <div className="font-display font-bold text-slate-100">{restaurant?.name} — Today's Tasks</div>
          {tasks.date && <div className="text-xs text-slate-500">{fmtDate(tasks.date)}</div>}
        </div>
        <button className={btnGhost} onClick={onRefresh} data-testid="staff-refresh">Refresh</button>
      </div>
      <div className="flex gap-2 mb-4 flex-wrap">
        <button className={btnGhost} onClick={onOpenPrep} data-testid="staff-jump-prep"><ChefHat size={13} /> Open Prep Sheet</button>
        <button className={btnGhost} onClick={onOpenCounts} data-testid="staff-jump-counts"><ClipboardList size={13} /> Open Counts</button>
      </div>
      {tasks.retired ? (
        <div role="status" data-testid="staff-tasks-retired">Use the prep task plan and reviewed count sheets for current work. Historical employee tasks are available to managers as read-only history.</div>
      ) : tasks.unavailable ? (
        <div role="alert">Tasks could not be loaded. Refresh to try again.</div>
      ) : tasks.tasks.length === 0 ? (
        <div className="text-center py-14 px-5 rounded-xl border border-dashed border-[#334155] bg-[#161F30] text-sm text-slate-500" data-testid="staff-tasks-empty">
          No tasks assigned for today. Check with your manager, or use Prep / Counts above.
        </div>
      ) : (
        <div className="flex flex-col gap-3" data-testid="staff-tasks-list">
          {tasks.tasks.map((t) => (
            <div key={t.id} className={`${cardCls} p-4`} data-testid={`staff-task-item-${t.id}`}>
              <div className="flex justify-between items-start gap-3">
                <div className="flex-1">
                  <div className="font-bold text-slate-100 text-base">{t.title}</div>
                  <div className="text-sm text-slate-400 mt-0.5">
                    <Pill color={t.taskType === "count" ? "#3B82F6" : "#F97316"} bg={t.taskType === "count" ? "rgba(59,130,246,0.12)" : "rgba(249,115,22,0.12)"}>
                      {t.taskType === "count" ? "Count" : "Prep"}
                    </Pill>
                    <span className="ml-2">Due {fmtDate(t.dueDate)}</span>
                  </div>
                  {t.note && <div className="text-xs text-amber-400 mt-1">{t.note}</div>}
                  {t.assignedTo && <div className="text-[11px] text-slate-500 mt-1">Assigned to {t.assignedTo}</div>}
                </div>
                <button className={btnAcc} onClick={() => onComplete(t)} data-testid={`staff-task-done-${t.id}`}>Mark Done</button>
              </div>
            </div>
          ))}
        </div>
      )}
    </>
  );
}

function PrepView({ restaurant, track, setTrack, sheet, onRefresh, expanded, setExpanded, onComplete }) {
  return (
    <>
      <div className="flex gap-2 mb-4 flex-wrap" data-testid="staff-track-selector">
        {TRACKS.map((t) => (
          <button key={t.id} onClick={() => setTrack(t.id)} data-testid={`staff-track-${t.id}`}
            className={t.id === track ? btnAcc : btnGhost}>
            {t.label}
          </button>
        ))}
      </div>
      {!sheet ? null : (
        <>
          <div className="flex justify-between items-center mb-4 flex-wrap gap-2">
            <div>
              <div className="font-display font-bold text-slate-100">{restaurant?.name} — {TRACKS.find((t) => t.id === track)?.label}</div>
              <div className="text-xs text-slate-500">Prep list for {fmtDate(sheet.date)}</div>
            </div>
            <button className={btnGhost} onClick={onRefresh} data-testid="staff-refresh">Refresh</button>
          </div>

          {sheet.tasks.length === 0 ? (
            <div className="text-center py-14 px-5 rounded-xl border border-dashed border-[#334155] bg-[#161F30] text-sm text-slate-500" data-testid="staff-empty">
              No prep list has been released for today yet. Check with your manager.
            </div>
          ) : (
            <div className="flex flex-col gap-3" data-testid="staff-task-list">
              {sheet.tasks.map((t) => {
                const done = t.batchesPlanned > 0 && t.remaining === 0;
                const open = expanded[t.id];
                return (
                  <div key={t.id} className={`${cardCls} p-4`} style={done ? { opacity: 0.55 } : {}} data-testid={`staff-task-${t.id}`}>
                    <div className="flex justify-between items-start gap-3">
                      <div className="flex-1">
                        <div className="font-bold text-slate-100 text-base">{t.name}</div>
                        <div className="text-sm text-slate-400 mt-0.5">
                          Prep <b className="num text-slate-200">{num(t.remaining, 1)}</b> more batch{t.remaining !== 1 ? "es" : ""} of {num(t.batchesPlanned, 1)}
                          <span className="text-slate-500"> ({num(t.card.yieldQty, 1)} {t.card.yieldUOM} per batch)</span>
                        </div>
                        {t.note && <div className="text-xs text-amber-400 mt-1">{t.note}</div>}
                        {t.doneBy && <div className="text-[11px] text-slate-500 mt-1">Last prepped by {t.doneBy}</div>}
                      </div>
                      {done
                        ? <Pill color="#10B981" bg="rgba(16,185,129,0.12)" testId={`staff-done-${t.id}`}><Check size={11} className="inline -mt-0.5" /> Done</Pill>
                        : <button className={btnAcc} onClick={() => onComplete(t)} data-testid={`staff-mark-done-${t.id}`}>Mark Prepped</button>}
                    </div>
                    {(t.card.procedure || t.card.equipment || t.card.shelfLife) && (
                      <div className="mt-2">
                        <button className="text-xs font-semibold flex items-center gap-1 hover:underline" style={{ color: "var(--acc, #F97316)" }}
                          onClick={() => setExpanded((x) => ({ ...x, [t.id]: !open }))} data-testid={`staff-card-toggle-${t.id}`}>
                          {open ? <ChevronUp size={13} /> : <ChevronDown size={13} />} Recipe Card
                        </button>
                        {open && (
                          <div className="mt-2 text-xs text-slate-300 bg-[#0F1626] border border-[#28354A] rounded-lg p-3 space-y-1.5" data-testid={`staff-card-${t.id}`}>
                            {t.card.equipment && <div><b>Equipment:</b> {t.card.equipment}</div>}
                            {t.card.shelfLife && <div><b>Shelf life:</b> {t.card.shelfLife}</div>}
                            {t.card.procedure && <div className="whitespace-pre-wrap"><b>Procedure:</b>{"\n"}{t.card.procedure}</div>}
                          </div>
                        )}
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          )}
        </>
      )}
    </>
  );
}

function CountsView({ restaurant, counts, onRefresh, name, setName, onSave, setErr }) {
  const items = useMemo(() => (counts?.items || []).filter(isCountActive).map((it) => ({ ...it, unit: it.unitUOM })), [counts]);
  const sheet = useCountSheet(items, onSave);
  const [notice, setNotice] = useState("");

  async function run(action) {
    setErr(""); setNotice("");
    if (!name.trim()) { setErr("Enter your name so the counts are attributed"); return; }
    const r = await action();
    if (r.error) { setErr(r.error === "Couldn't save counts" ? "Couldn't save — tell your manager" : r.error); return; }
    setNotice(r.notApplied.length
      ? `Saved ${r.saved}. ${r.notApplied.length} already had a newer count, so on-hand wasn't changed.`
      : r.saved === 1 ? "Count saved" : `${r.saved} counts saved`);
  }

  if (!counts) return null;
  return (
    <>
      <div className="flex justify-between items-center mb-4 flex-wrap gap-2">
        <div>
          <div className="font-display font-bold text-slate-100">{restaurant?.name} — Physical Count</div>
          <div className="text-xs text-slate-500">Counts for {fmtDate(sheet.countDate || todayISO())}</div>
        </div>
        <button className={btnGhost} onClick={onRefresh} data-testid="staff-refresh">Refresh</button>
      </div>
      <div className="mb-3"><CountSheetControls sheet={sheet} name={name} setName={setName} nameTestId="staff-counts-name" /></div>
      <CountSheetBanner sheet={sheet} />
      {items.length === 0 ? (
        <div className="text-center py-14 px-5 rounded-xl border border-dashed border-[#334155] bg-[#161F30] text-sm text-slate-500" data-testid="staff-counts-empty">
          No items are set up for the count yet. Check with your manager.
        </div>
      ) : (
        <CountSheetList sheet={sheet} onSaveOne={(it) => run(() => sheet.saveOne(it))} />
      )}
      {notice && <div className="text-emerald-400 text-xs mt-3" data-testid="staff-counts-notice">{notice}</div>}
      <div className="mt-4 flex justify-end">
        <SaveAllCountsButton sheet={sheet} onClick={() => run(sheet.saveAll)} testId="staff-save-counts-button" />
      </div>
    </>
  );
}
