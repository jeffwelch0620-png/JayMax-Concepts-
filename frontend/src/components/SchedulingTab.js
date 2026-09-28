import React, { useEffect, useState } from "react";
import { CalendarClock, ClipboardCheck, GraduationCap, BookMarked, Plus, Trash2, ChefHat, ClipboardList } from "lucide-react";
import { PageTitle, cardCls, inpCls, btnAcc, btnGhost, btnDanger, Pill, EmptyState } from "./common";
import { todayISO, fmtDate } from "../lib/calc";
import * as api from "../lib/api";

const PLANNED = [
  { icon: ClipboardCheck, title: "Checklists & Compliance", desc: "Opening/closing checklists, temp logs, and food-safety compliance sign-offs.", accent: "#10B981" },
  { icon: GraduationCap, title: "Training", desc: "Role-based training modules with completion tracking for every station.", accent: "#3B82F6" },
  { icon: BookMarked, title: "SOP Library", desc: "Searchable standard operating procedures linked to recipes and prep lists.", accent: "#EAB308" },
];

const RECURRENCE_OPTIONS = [
  { id: "once", label: "One-time" },
  { id: "daily", label: "Daily" },
  { id: "weekly", label: "Weekly" },
];

const EMPTY_DRAFT = { taskType: "count", title: "", dueDate: todayISO(), recurrence: "once", assignedTo: "", note: "" };

// Lets a manager/owner push a Count or Prep task to the PIN-gated employee
// portal (StaffSheet) instead of employees having to remember to check —
// creating a task here also fires a web-push notification (if configured)
// to every subscribed device at this location.
export function SchedulingTab({ rid, showToast }) {
  const [tasks, setTasks] = useState(null);
  const [draft, setDraft] = useState(EMPTY_DRAFT);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");

  async function refresh() {
    if (!rid) return;
    try { setTasks(await api.listStaffTasks(rid)); } catch { setTasks([]); }
  }
  useEffect(() => { refresh(); /* eslint-disable-next-line react-hooks/exhaustive-deps */ }, [rid]);

  async function assign() {
    setErr("");
    if (!draft.title.trim()) { setErr("Give the task a name"); return; }
    setBusy(true);
    try {
      await api.createStaffTask(rid, draft);
      setDraft({ ...EMPTY_DRAFT, dueDate: draft.dueDate });
      await refresh();
      showToast?.("Task assigned — pushed to the employee portal");
    } catch (e) { setErr(e?.response?.data?.detail || "Couldn't assign task"); }
    finally { setBusy(false); }
  }

  async function remove(taskId) {
    await api.deleteStaffTask(rid, taskId);
    await refresh();
  }

  return (
    <div className="fade-slide-in" data-testid="scheduling-tab">
      <PageTitle>Operations</PageTitle>

      <div className={`${cardCls} p-5 mb-6`} data-testid="assign-task-panel">
        <div className="font-display font-bold text-slate-100 mb-1">Assign Employee Tasks</div>
        <div className="text-xs text-slate-500 mb-4">
          Push a Count or Prep task to the staff PIN portal. Employees with notifications enabled get an instant alert.
        </div>
        <div className="grid gap-3" style={{ gridTemplateColumns: "repeat(auto-fit,minmax(160px,1fr))" }}>
          <label className="flex flex-col gap-1 text-xs text-slate-400 font-semibold">Task Type
            <select className={inpCls} data-testid="assign-task-type" value={draft.taskType} onChange={(e) => setDraft((d) => ({ ...d, taskType: e.target.value }))}>
              <option value="count">Count</option>
              <option value="prep">Prep</option>
            </select>
          </label>
          <label className="flex flex-col gap-1 text-xs text-slate-400 font-semibold">Title
            <input className={inpCls} data-testid="assign-task-title" placeholder="e.g. Walk-in count" value={draft.title} onChange={(e) => setDraft((d) => ({ ...d, title: e.target.value }))} />
          </label>
          <label className="flex flex-col gap-1 text-xs text-slate-400 font-semibold">Due Date
            <input type="date" className={inpCls} data-testid="assign-task-due" value={draft.dueDate} onChange={(e) => setDraft((d) => ({ ...d, dueDate: e.target.value }))} />
          </label>
          <label className="flex flex-col gap-1 text-xs text-slate-400 font-semibold">Recurrence
            <select className={inpCls} data-testid="assign-task-recurrence" value={draft.recurrence} onChange={(e) => setDraft((d) => ({ ...d, recurrence: e.target.value }))}>
              {RECURRENCE_OPTIONS.map((o) => <option key={o.id} value={o.id}>{o.label}</option>)}
            </select>
          </label>
          <label className="flex flex-col gap-1 text-xs text-slate-400 font-semibold">Assign To (optional)
            <input className={inpCls} data-testid="assign-task-assignee" placeholder="e.g. Maria" value={draft.assignedTo} onChange={(e) => setDraft((d) => ({ ...d, assignedTo: e.target.value }))} />
          </label>
        </div>
        {err && <div className="text-red-400 text-xs mt-3">{err}</div>}
        <div className="mt-4 flex justify-end">
          <button className={btnAcc} onClick={assign} disabled={busy} data-testid="assign-task-submit"><Plus size={14} /> {busy ? "Assigning…" : "Assign Task"}</button>
        </div>
      </div>

      <div className="mb-6">
        <div className="text-[11px] uppercase tracking-[0.08em] text-slate-500 font-bold mb-2">Assigned Tasks</div>
        {!tasks || tasks.length === 0 ? (
          <EmptyState text="No tasks assigned yet. Use the form above to push a count or prep task to staff." />
        ) : (
          <div className="flex flex-col gap-2" data-testid="assigned-task-list">
            {tasks.map((t) => (
              <div key={t.id} className={`${cardCls} p-3 flex items-center justify-between gap-3`} data-testid={`assigned-task-${t.id}`}>
                <div className="flex items-center gap-2 flex-1">
                  {t.taskType === "count" ? <ClipboardList size={15} className="text-blue-400" /> : <ChefHat size={15} className="text-[#F97316]" />}
                  <div>
                    <div className="font-bold text-slate-100 text-sm">{t.title}</div>
                    <div className="text-xs text-slate-500">Due {fmtDate(t.dueDate)}{t.assignedTo ? ` · ${t.assignedTo}` : ""}</div>
                  </div>
                </div>
                <Pill color={t.status === "done" ? "#10B981" : "#94A3B8"} bg={t.status === "done" ? "rgba(16,185,129,0.12)" : "rgba(148,163,184,0.12)"}>
                  {t.status === "done" ? "Done" : "Pending"}
                </Pill>
                <button className={btnDanger} onClick={() => remove(t.id)} data-testid={`delete-assigned-task-${t.id}`}><Trash2 size={12} /></button>
              </div>
            ))}
          </div>
        )}
      </div>

      <div className="text-xs text-slate-500 -mt-1 mb-5">
        Shift scheduling, checklists/compliance, training, and SOPs are next in the roadmap and will plug into this same per-location workspace.
      </div>
      <div className="grid gap-4" style={{ gridTemplateColumns: "repeat(auto-fit,minmax(260px,1fr))" }}>
        <div className={`${cardCls} p-5`} data-testid="planned-shift-scheduling" style={{ borderTopWidth: 2, borderTopColor: "#F97316" }}>
          <div className="w-9 h-9 rounded-lg flex items-center justify-center mb-3" style={{ background: "#F9731622" }}>
            <CalendarClock size={18} style={{ color: "#F97316" }} />
          </div>
          <div className="font-display font-bold text-slate-100 mb-1">Shift Scheduling</div>
          <div className="text-xs text-slate-400 leading-relaxed">Weekly shift planner per location with labor-cost % tracked against projected sales.</div>
          <div className="mt-3 text-[10px] uppercase tracking-widest font-bold text-slate-600">In roadmap</div>
        </div>
        {PLANNED.map((p) => {
          const Icon = p.icon;
          return (
            <div key={p.title} className={`${cardCls} p-5`} data-testid={`planned-${p.title.toLowerCase().replace(/[^a-z]+/g, "-")}`} style={{ borderTopWidth: 2, borderTopColor: p.accent }}>
              <div className="w-9 h-9 rounded-lg flex items-center justify-center mb-3" style={{ background: `${p.accent}22` }}>
                <Icon size={18} style={{ color: p.accent }} />
              </div>
              <div className="font-display font-bold text-slate-100 mb-1">{p.title}</div>
              <div className="text-xs text-slate-400 leading-relaxed">{p.desc}</div>
              <div className="mt-3 text-[10px] uppercase tracking-widest font-bold text-slate-600">In roadmap</div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
