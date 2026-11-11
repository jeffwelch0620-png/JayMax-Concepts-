import React, { useCallback, useEffect, useRef, useState } from "react";
import * as api from "../lib/api";
import { actionsFor, amount, carryable, commandBody, formProblem, prepChanges, stateLabel } from "../lib/prepHandoff";
import { cardCls, inpCls, btnAcc, btnGhost, btnDanger, SectionLabel } from "./common";

const TONE = { ok: "text-jm-ok border-jm-ok", warn: "text-jm-warn border-jm-warn", muted: "text-jm-ink-3 border-jm-line" };
const LABEL = { accept: "Accept handoff", take_over: "Take over", correct: "Correct", withdraw: "Withdraw" };
const REASON = { take_over: "Why you are taking it over (e.g. PM manager called out, I'm covering)",
  correct: "What changed", withdraw: "Why it is withdrawn" };
const errorText = e => e?.response?.data?.detail && typeof e.response.data.detail === "string"
  ? e.response.data.detail : "The handoff could not be confirmed. Retry sends the same request again, so it is never saved twice.";
const facts = t => `${amount(t.remaining_base_quantity)} ${t.base_unit} left of ${amount(t.planned_base_quantity)} · ${t.assignee ? t.assignee.name : "Unassigned"} · ${t.status.replace("_", " ")}`;

// AM-to-PM prep handoff for the selected restaurant, date and track (Jeff 2026-11-11). Responsibility only:
// nothing here records production, changes stock, assigns staff or finishes a task.
export function PrepHandoffs({ rid, day, track, showToast = () => {} }) {
  const [data, setData] = useState(null), [error, setError] = useState(""), [loading, setLoading] = useState(false);
  const [readAt, setReadAt] = useState(null);
  const [pending, setPending] = useState(null); // { body, version, key } kept so a retry reuses the same key
  const [busy, setBusy] = useState(false);
  const sequence = useRef(0);

  const load = useCallback(async () => {
    const mine = ++sequence.current; setLoading(true);
    try {
      const v = await api.prepHandoffDay(rid, day, track);
      if (mine !== sequence.current) return;
      setData(v); setReadAt(new Date()); setError("");
    } catch (e) { if (mine === sequence.current) { setData(null); setError(errorText(e)); } }
    finally { if (mine === sequence.current) setLoading(false); }
  }, [rid, day, track]);
  useEffect(() => { setPending(null); load(); }, [load]);

  async function run(request) {
    if (busy) return false;
    setBusy(true); setPending(request); setError("");
    try {
      await api.prepHandoffCommand(rid, request.body, request.version, request.key);
      setPending(null); showToast("Handoff saved."); await load(); return true;
    } catch (e) {
      // A refused request (4xx) is final; keep only requests whose outcome is unknown for a retry.
      if (e?.response && e.response.status < 500) setPending(null);
      setError(errorText(e)); return false;
    } finally { setBusy(false); }
  }
  const send = (action, args, version) => run({ body: commandBody(action, { day, track, ...args }), version, key: window.crypto.randomUUID() });

  if (!data) return <section className={`${cardCls} p-4 my-4`} aria-label="Prep handoffs" data-testid="prep-handoffs">
    <SectionLabel>Carry prep to the evening</SectionLabel>
    {error ? <p role="alert" className="text-jm-bad text-sm">{error}</p> : <p className="text-sm text-jm-ink-2">{loading ? "Loading prep handoffs…" : "No prep handoff data yet."}</p>}
    <button className={`${btnGhost} mt-2`} disabled={loading} onClick={load}>Refresh</button>
  </section>;

  const open = carryable(data.tasks, data.handoffs);
  return <section className={`${cardCls} p-4 my-4`} aria-label="Prep handoffs" data-testid="prep-handoffs">
    <div className="flex flex-wrap items-center justify-between gap-2">
      <SectionLabel>Carry prep to the evening</SectionLabel>
      <span className="text-xs text-jm-ink-3">Prep facts as of last refresh {readAt?.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" })}
        <button className={`${btnGhost} ml-2`} disabled={loading || busy} onClick={load}>Refresh</button></span>
    </div>
    <p className="text-sm text-jm-ink-2 mt-1">Accepting a handoff makes you responsible for it. It does not record production, change stock or finish the task.</p>
    {error && <p role="alert" className="text-jm-bad text-sm mt-2">{error}</p>}
    {pending && <p className="text-sm mt-2">Last request not confirmed. <button className={btnGhost} disabled={busy} onClick={() => run(pending)}>Retry the same request</button>
      <button className={`${btnGhost} ml-2`} disabled={busy} onClick={() => setPending(null)}>Discard</button></p>}
    <ul className="flex flex-col gap-3 mt-3">
      {data.handoffs.map(h => <Handoff key={h.id} h={h} data={data} rid={rid} busy={busy} send={send}/>)}
      {!data.handoffs.length && <li className="text-sm text-jm-ink-3">No prep handed off for this date and track.</li>}
    </ul>
    <NewHandoff tasks={open} managers={data.managers.filter(m => m.id !== data.actor_id)} busy={busy}
      onSend={(task, form) => send("send", { handoffId: window.crypto.randomUUID(), task, form }, 0)}/>
  </section>;
}

function NewHandoff({ tasks, managers, busy, onSend }) {
  const [taskId, setTaskId] = useState(""), [form, setForm] = useState({ recipient_id: "", remaining: "", ready_by: "16:00", note: "" });
  const [problem, setProblem] = useState("");
  const task = tasks.find(t => t.task_id === taskId);
  useEffect(() => { if (taskId && !task) setTaskId(""); }, [taskId, task]);
  if (!tasks.length) return <p className="text-sm text-jm-ink-3 mt-4">No released, unfinished prep left to carry for this date and track.</p>;
  const change = (k, v) => setForm(p => ({ ...p, [k]: v }));
  async function submit() {
    const p = task ? formProblem("send", form) : "Choose a prep task.";
    setProblem(p);
    if (!p && await onSend(task, form)) { setTaskId(""); setForm(f => ({ ...f, remaining: "", note: "" })); }
  }
  return <fieldset disabled={busy} className="border-t border-jm-line mt-4 pt-4 flex flex-col gap-3">
    <legend className="text-sm font-semibold text-jm-ink">Hand off a prep task</legend>
    <label className="flex flex-col gap-1 text-sm">Prep task
      <select className={inpCls} value={taskId} onChange={e => { const t = tasks.find(x => x.task_id === e.target.value); setTaskId(e.target.value); if (t) change("remaining", amount(t.remaining_base_quantity)); }}>
        <option value="">Choose a task</option>
        {tasks.map(t => <option key={t.task_id} value={t.task_id}>{t.name} · {amount(t.remaining_base_quantity)} {t.base_unit} left</option>)}
      </select></label>
    {task && <p className="text-sm text-jm-ink-2">{facts(task)}. Assign a cook on the Prep tab before handing off if needed; the evening manager sees the assignee.</p>}
    <div className="grid gap-3 sm:grid-cols-3">
      <label className="flex flex-col gap-1 text-sm">Evening manager
        <select className={inpCls} value={form.recipient_id} onChange={e => change("recipient_id", e.target.value)}>
          <option value="">Choose a manager</option>{managers.map(m => <option key={m.id} value={m.id}>{m.label}</option>)}
        </select></label>
      <label className="flex flex-col gap-1 text-sm">Remaining{task ? ` (${task.base_unit})` : ""}
        <input className={inpCls} inputMode="decimal" value={form.remaining} onChange={e => change("remaining", e.target.value)}/></label>
      <label className="flex flex-col gap-1 text-sm">Ready by
        <input className={inpCls} type="time" value={form.ready_by} onChange={e => change("ready_by", e.target.value)}/></label>
    </div>
    <label className="flex flex-col gap-1 text-sm">Note for the evening manager
      <textarea className={`${inpCls} min-h-20`} maxLength={2000} value={form.note} onChange={e => change("note", e.target.value)}/></label>
    {problem && <p role="alert" className="text-jm-bad text-sm">{problem}</p>}
    <div><button className={btnAcc} onClick={submit}>Send handoff</button></div>
  </fieldset>;
}

function Handoff({ h, data, rid, busy, send }) {
  const [mode, setMode] = useState(null), [form, setForm] = useState({}), [problem, setProblem] = useState("");
  const [history, setHistory] = useState(null);
  const state = stateLabel(h), changes = prepChanges(h.recorded_prep, h.current_prep);
  const actions = actionsFor(h, data.actor_id, data.senior);
  const prep = h.current_prep || h.recorded_prep;
  function open(action) {
    setProblem("");
    if (action === "accept") { send("accept", { handoff: h }, h.revision); return; }
    setForm(action === "correct" ? { recipient_id: h.recipient_id, remaining: amount(h.remaining_base_quantity), ready_by: h.ready_by, note: h.note, reason: "" } : { reason: "" });
    setMode(action);
  }
  async function confirm() {
    const p = formProblem(mode, form);
    setProblem(p);
    if (!p && await send(mode, { handoff: h, form }, h.revision)) setMode(null);
  }
  async function toggleHistory() {
    if (history) { setHistory(null); return; }
    try { setHistory((await api.prepHandoffHistory(rid, h.id)).rows); } catch { setHistory([]); }
  }
  return <li className="border border-jm-line rounded-lg p-3" data-testid="prep-handoff">
    <div className="flex flex-wrap items-baseline justify-between gap-2">
      <strong className="text-jm-ink-strong">{prep?.name || "Prep task"}</strong>
      <span className={`text-xs font-semibold border rounded-full px-2 py-0.5 ${TONE[state.tone]}`}>{state.text}</span>
    </div>
    <p className="text-sm mt-1">{amount(h.remaining_base_quantity)} {h.base_unit} to finish by {h.ready_by} · from {h.sender}</p>
    {h.current_prep && <p className="text-sm text-jm-ink-2">Now: {facts(h.current_prep)}</p>}
    {h.note && <p className="text-sm whitespace-pre-wrap mt-1">{h.note}</p>}
    {h.reason && <p className="text-xs text-jm-ink-3 mt-1">Last {h.action.replace("_", " ")}: {h.reason}</p>}
    {h.prep_changed && h.status !== "withdrawn" && changes.length > 0 && <div role="status" className="text-sm text-jm-warn mt-2">
      <p>Since the last {h.action === "send" ? "send" : h.action.replace("_", " ")}:</p><ul className="list-disc ml-5">{changes.map(c => <li key={c}>{c}</li>)}</ul></div>}
    <div className="flex flex-wrap gap-2 mt-3">
      {actions.map(a => <button key={a} className={a === "accept" ? btnAcc : a === "withdraw" ? btnDanger : btnGhost} disabled={busy} onClick={() => open(a)}>{LABEL[a]}</button>)}
      <button className={btnGhost} onClick={toggleHistory}>{history ? "Hide history" : "History"}</button>
    </div>
    {mode && <fieldset disabled={busy} className="flex flex-col gap-2 mt-3 border-t border-jm-line pt-3">
      {mode === "correct" && <div className="grid gap-2 sm:grid-cols-3">
        <label className="flex flex-col gap-1 text-sm">Evening manager<select className={inpCls} value={form.recipient_id} onChange={e => setForm({ ...form, recipient_id: e.target.value })}>
          {data.managers.filter(m => m.id !== data.actor_id).map(m => <option key={m.id} value={m.id}>{m.label}</option>)}</select></label>
        <label className="flex flex-col gap-1 text-sm">Remaining ({h.base_unit})<input className={inpCls} inputMode="decimal" value={form.remaining} onChange={e => setForm({ ...form, remaining: e.target.value })}/></label>
        <label className="flex flex-col gap-1 text-sm">Ready by<input className={inpCls} type="time" value={form.ready_by} onChange={e => setForm({ ...form, ready_by: e.target.value })}/></label>
        <label className="flex flex-col gap-1 text-sm sm:col-span-3">Note<textarea className={`${inpCls} min-h-16`} maxLength={2000} value={form.note} onChange={e => setForm({ ...form, note: e.target.value })}/></label>
      </div>}
      <label className="flex flex-col gap-1 text-sm">{REASON[mode]}<textarea className={`${inpCls} min-h-16`} maxLength={1000} value={form.reason} onChange={e => setForm({ ...form, reason: e.target.value })}/></label>
      {mode === "correct" && <p className="text-xs text-jm-ink-3">A correction sends the handoff back for acceptance.</p>}
      {problem && <p role="alert" className="text-jm-bad text-sm">{problem}</p>}
      <div className="flex gap-2"><button className={mode === "withdraw" ? btnDanger : btnAcc} onClick={confirm}>{LABEL[mode]}</button><button className={btnGhost} onClick={() => setMode(null)}>Cancel</button></div>
    </fieldset>}
    {history && <ol className="mt-3 flex flex-col gap-1 text-xs text-jm-ink-2">{history.map(r => <li key={r.revision}>
      {new Date(r.recorded_at).toLocaleString([], { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" })} · {r.action.replace("_", " ")} by {r.actor} → {r.recipient} · {amount(r.remaining_base_quantity)} {r.base_unit} by {r.ready_by}{r.reason ? ` · ${r.reason}` : ""}{r.note ? ` · “${r.note}”` : ""}</li>)}
      {!history.length && <li>History could not be read.</li>}</ol>}
  </li>;
}
