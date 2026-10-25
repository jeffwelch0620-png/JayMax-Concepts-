import React, { useEffect, useMemo, useRef, useState } from "react";
import * as api from "../lib/api";
import { RESTAURANTS, todayISO } from "../lib/calc";
import { useRetainedDraft } from "../lib/saveIntegrity";
import { readStateWithDeadline } from "../lib/stateRead";
import { handoffContext, handoffJournal, handoffFingerprint, checkedHandoffDay, checkedHandoffReceipt,
  checkedHandoffStatus, checkedHandoffHistory, stableHandoff } from "../lib/managerHandoff";
import { PageTitle, cardCls, inpCls, btnGhost, btnAcc } from "./common";

const reported = { not_assessed: "Not assessed", ready: "Ready (reported)", action_needed: "Action needed" };
const errorText = "Handoff information could not be confirmed. Refresh or check the retained request before sending anything new.";
const fields = n => ({ summary: n?.summary || "", next_shift_note: n?.next_shift_note || "", reported_readiness: n?.reported_readiness || "not_assessed", correction_reason: "" });

export function ManagerHandoffTab({ rid, user, initialContext, drafts, showToast = () => {} }) {
  const scope = stableHandoff([user?.id, rid]);
  const [selection, setSelection] = useState(() => ({ scope, day: initialContext?.rid === rid ? initialContext.day : todayISO(), track: initialContext?.rid === rid ? initialContext.track : "bulk" }));
  const chosen = selection.scope === scope ? selection : { scope, day: todayISO(), track: "bulk" };
  const journal = useMemo(() => handoffJournal(user?.id, rid), [user?.id, rid]);
  const [recovery, setRecovery] = useState(null), [boot, setBoot] = useState(0);
  const c = handoffContext(rid, chosen.day, chosen.track, user);
  const state = recovery?.scope === scope ? recovery : null;
  useEffect(() => {
    let active = true;
    setRecovery({ scope, ready: false, request: null });
    (async () => {
      try {
        const request = journal.read();
        if (request && await handoffFingerprint(user.id, rid, request.body, request.version) !== request.fingerprint) throw Error();
        if (!active) return;
        if (request) setSelection({ scope, day: request.body.business_date, track: request.body.prep_track });
        setRecovery({ scope, ready: true, request });
      } catch { if (active) setRecovery({ scope, ready: false, request: null, error: true }); }
    })();
    return () => { active = false; };
  }, [scope, journal, user?.id, rid, boot]);
  return <div data-testid="manager-handoff">
    <PageTitle>Manager handoff note</PageTitle>
    <p>{RESTAURANTS.find(r => r.id === rid)?.name} Ã‚Â· Shared manager production summary. Reading or submitting a note does not transfer responsibility, complete prep or change Food Cost.</p>
    <div className="flex flex-wrap gap-3 my-4">
      <label className="flex flex-col gap-1">Business date<input className={inpCls} aria-label="Handoff date" type="date" value={chosen.day} disabled={!state?.ready || !!state.request} onChange={e => setSelection({ ...chosen, day: e.target.value })}/></label>
      <label className="flex flex-col gap-1">Prep track<select className={inpCls} aria-label="Handoff track" value={chosen.track} disabled={!state?.ready || !!state.request} onChange={e => setSelection({ ...chosen, track: e.target.value })}><option value="bulk">Bulk Prep</option><option value="daily">Daily Prep</option></select></label>
    </div>
    {!c ? <p role="alert">Select a valid restaurant/date/track for your personal manager or owner account.</p> : !state?.ready ? <p role="alert">{state?.error ? "Browser recovery is unavailable. No new handoff request will be sent." : "Checking this account's retained requestÃ¢â‚¬Â¦"}<button className={btnGhost} onClick={() => setBoot(n => n + 1)}>Recheck browser recovery</button></p> :
      <HandoffForm key={c.key} context={c} drafts={drafts} journal={journal} request={state.request} onRequest={request => setRecovery({ scope, ready: true, request })} showToast={showToast}/>}
  </div>;
}

function HandoffForm({ context: c, drafts, journal, request, onRequest, showToast }) {
  const [draft, setDraft, acknowledge] = useRetainedDraft(`manager-handoff:${c.actor}:${c.store}:${c.day}:${c.track}`,
    { loaded: false, version: 0, note_id: null, settings_revision: null, ...fields(null) }, drafts);
  const [data, setData] = useState(null), [error, setError] = useState(""), [busy, setBusy] = useState(false), [reading, setReading] = useState(false);
  const [history, setHistory] = useState(null);
  const life = useRef({ active: true }), sequence = useRef(0), inFlight = useRef(false);
  useEffect(() => {
    const current = life.current; current.active = true; load();
    return () => { current.active = false; };
    // Context changes remount the form, keeping each retained draft separately scoped.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  function fromCurrent(v) {
    return { loaded: true, version: v.current?.revision || 0, note_id: v.current?.id || window.crypto.randomUUID(),
      settings_revision: v.current?.settings_revision || v.settings.revision, ...fields(v.current) };
  }
  async function load() {
    const serial = ++sequence.current; setReading(true);
    try {
      const v = checkedHandoffDay(await readStateWithDeadline(options => api.handoffDay(c.rid, c.day, c.track, options)), c);
      if (!life.current.active || serial !== sequence.current) return;
      setData(v); setHistory(null); setError("");
      if (!draft.loaded) acknowledge(draft, fromCurrent(v));
    } catch { if (life.current.active && serial === sequence.current) { setData(null); setHistory(null); setError(errorText); } }
    finally { if (life.current.active && serial === sequence.current) setReading(false); }
  }
  const stale = data && ((data.current?.revision || 0) !== draft.version || (!!data.current && data.current.id !== draft.note_id)
    || (!data.current && data.settings.revision !== draft.settings_revision));
  const changed = data?.current && ["summary", "next_shift_note", "reported_readiness"].some(k => draft[k] !== data.current[k]);
  const locked = busy || reading || !!request;
  function change(key, value) { setDraft(p => ({ ...p, [key]: value })); }
  function selectCurrent(keepEdits) {
    if (locked || !data) return;
    const next = fromCurrent(data);
    if (keepEdits) setDraft(p => ({ ...p, version: next.version, note_id: next.note_id, settings_revision: next.settings_revision, correction_reason: "" }));
    else acknowledge(draft, next);
    setError("Current version selected. Review the saved text and your edits before the next command.");
  }
  async function accept(result, sent) {
    checkedHandoffReceipt(result, sent, c);
    journal.clear(sent);
    onRequest(null);
    // A status receipt can arrive even if the separate day read is unavailable.
    // Keep that read unavailable until refreshed instead of inventing settings.
    setData(p => p ? { ...p, current: result.current } : null);
    acknowledge(draft, { loaded: true, version: result.current.revision, note_id: result.current.id,
      settings_revision: result.current.settings_revision, ...fields(result.current) });
    setHistory(null); setError(""); showToast("Handoff note confirmed. Current saved version displayed.");
  }
  async function send(action) {
    if (inFlight.current || reading || !data || (!request && stale)) return;
    inFlight.current = true; setBusy(true); setError("");
    try {
      let sent = request;
      if (!sent) {
        const body = { action, note_id: draft.note_id, business_date: c.day, prep_track: c.track,
          settings_revision: draft.settings_revision, summary: draft.summary.trim(), next_shift_note: draft.next_shift_note,
          reported_readiness: draft.reported_readiness, correction_reason: action === "correct" ? draft.correction_reason.trim() : "" };
        sent = { key: window.crypto.randomUUID(), version: draft.version, body,
          fingerprint: await handoffFingerprint(c.actor, c.store, body, draft.version) };
        if (!life.current.active) return;
        journal.save(sent); onRequest(sent);
      }
      const result = await api.saveHandoff(c.rid, sent.body, sent.version, sent.key);
      if (life.current.active) await accept(result, sent);
    } catch { if (life.current.active) setError("The request is not confirmed. If retained, check its status or retry only that exact request. Invalid or blank text must be corrected before sending."); }
    finally { inFlight.current = false; if (life.current.active) setBusy(false); }
  }
  async function checkStatus() {
    if (!request || inFlight.current) return;
    inFlight.current = true; setBusy(true);
    try {
      const v = checkedHandoffStatus(await api.handoffStatus(c.rid, request.body, request.version, request.key), request, c);
      if (!life.current.active) return;
      if (v.outcome === "saved") await accept(v, request);
      else setError("No matching receipt was visible. The original may still complete. Retry only the retained request, or explicitly discard its browser recovery after reviewing the saved note.");
    } catch { if (life.current.active) setError(errorText); }
    finally { inFlight.current = false; if (life.current.active) setBusy(false); }
  }
  function discard() {
    if (busy || reading || !request || !window.confirm("Discard this browser recovery request? A committed note is not undone. Refresh and review the saved record before starting another request.")) return;
    try { journal.clear(request); onRequest(null); setError("Recovery discarded. Refresh and review current values before any new command."); setData(null); }
    catch { setError(errorText); }
  }
  async function readHistory(after = 0) {
    if (!data?.current || busy || reading) return;
    const readSequence = sequence.current;
    setBusy(true);
    try {
      const v = checkedHandoffHistory(await readStateWithDeadline(options => api.handoffHistory(c.rid, data.current.id, after, options)), c, data.current.id, after);
      if (!life.current.active || readSequence !== sequence.current) return;
      if (after && history?.revision !== v.current_revision) throw Error();
      setHistory({ revision: v.current_revision, rows: [...(after ? history.rows : []), ...v.rows], next: v.next_after });
    } catch { if (life.current.active) setError("History changed or could not be confirmed. Refresh history before combining pages."); }
    finally { if (life.current.active) setBusy(false); }
  }
  return <div>
    {error && <p role="alert">{error}</p>}
    {request && <section className={`${cardCls} p-4 my-4`} aria-label="Retained handoff request"><h2>Retained request Ã‚Â· {request.body.business_date} Ã‚Â· {request.body.prep_track}</h2><p>Editing is held until this exact request is confirmed or explicitly discarded. Reauthentication does not grant another account access to it.</p>{data ? <p>{request.body.summary}</p> : <p>Note text is held until a current authorized read succeeds.</p>}<button className={btnGhost} disabled={busy} onClick={checkStatus}>Check retained handoff status</button><button className={btnAcc} disabled={busy || reading || !data} onClick={() => send()}>Retry exact handoff request</button><button className={btnGhost} disabled={busy || reading} onClick={discard}>Discard browser recovery</button></section>}
    <button className={btnGhost} disabled={busy || reading} onClick={load}>Refresh handoff note</button>
    {!data ? <p>Awaiting a confirmed store/timezone and handoff read.</p> : <>
      <section className={`${cardCls} p-4 my-4`} aria-label="Previous submitted handoff"><h2>Previous submitted note</h2>{data.previous ? <><p>{data.previous.business_date} Ã‚Â· {data.previous.prep_track} Ã‚Â· {reported[data.previous.reported_readiness]}</p><p className="whitespace-pre-wrap">{data.previous.summary}</p><h3>Next-shift note</h3><p className="whitespace-pre-wrap">{data.previous.next_shift_note || "No next-shift text was entered."}</p></> : <p>No earlier submitted note is recorded for this store and track. This does not confirm readiness.</p>}</section>
      <section className={`${cardCls} p-4 my-4`}><h2>{data.current ? `${data.current.status} Ã‚Â· revision ${data.current.revision}` : "No saved note for this date/track"}</h2><p>Current store timezone: {data.settings.timezone_name}.{data.current && ` Note recorded in ${data.current.timezone_name} (settings revision ${data.current.settings_revision}).`} Reported readiness does not complete any prep work.</p>
        {data.current && <details><summary>Current saved text</summary><p className="whitespace-pre-wrap">{data.current.summary}</p><p className="whitespace-pre-wrap">{data.current.next_shift_note}</p></details>}
        {stale && <p role="alert">The saved version or timezone context changed. Review the current record before rebasing retained edits.</p>}
        <fieldset disabled={locked} className="flex flex-col gap-3 my-4">
          <label className="flex flex-col gap-2">Shift summary<textarea aria-label="Handoff summary" className={`${inpCls} w-full min-h-32`} maxLength={12000} value={draft.summary} onChange={e => change("summary", e.target.value)}/></label>
          <label className="flex flex-col gap-2">Next-shift note<textarea aria-label="Handoff next note" className={`${inpCls} w-full min-h-24`} maxLength={8000} value={draft.next_shift_note} onChange={e => change("next_shift_note", e.target.value)}/></label>
          <label className="flex flex-col gap-2">Reported readiness<select aria-label="Handoff readiness" className={inpCls} value={draft.reported_readiness} onChange={e => change("reported_readiness", e.target.value)}>{Object.entries(reported).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select></label>
          {data.current?.status === "submitted" && <label className="flex flex-col gap-2">Correction reason<textarea aria-label="Handoff correction reason" className={`${inpCls} w-full min-h-24`} maxLength={4000} value={draft.correction_reason} onChange={e => change("correction_reason", e.target.value)}/></label>}
        </fieldset>
        {!request && <div className="flex gap-2 flex-wrap"><button className={btnAcc} disabled={locked || stale} onClick={() => send(data.current?.status === "submitted" ? "correct" : data.current ? "save_draft" : "create_draft")}>{data.current?.status === "submitted" ? "Save handoff correction" : "Save handoff draft"}</button>
          {data.current?.status === "draft" && <button className={btnGhost} disabled={locked || stale || changed} onClick={() => send("submit")}>Submit saved handoff note</button>}
          <button className={btnGhost} disabled={locked} onClick={() => selectCurrent(false)}>Use current saved content</button>{stale && <button className={btnGhost} disabled={locked} onClick={() => selectCurrent(true)}>Review current version and keep edits</button>}</div>}
        {changed && data.current?.status === "draft" && <p>Save the edited draft before submitting it.</p>}
      </section>
      {data.current && <section><button className={btnGhost} disabled={busy} onClick={() => readHistory()}>Refresh handoff history</button>{history && <><p>Recorded history through revision {history.revision}{history.next !== null ? " Ã‚Â· more pages available" : " Ã‚Â· complete for this read"}.</p><ol>{history.rows.map(r => <li key={r.revision} className={`${cardCls} p-4 my-2`}><strong>Revision {r.revision} Ã‚Â· {r.action}</strong><p className="whitespace-pre-wrap">{r.summary}</p><p className="whitespace-pre-wrap">{r.next_shift_note}</p><p>{reported[r.reported_readiness]} Ã‚Â· {r.correction_reason}</p><details><summary>Record attribution</summary><p>{r.actor_id} Ã‚Â· {r.recorded_at}</p></details></li>)}</ol>{history.next !== null && <button className={btnGhost} disabled={busy} onClick={() => readHistory(history.next)}>More handoff history</button>}</>}</section>}
    </>}
  </div>;
}
