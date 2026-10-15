import React, { useEffect, useMemo, useState } from "react";
import * as api from "../lib/api";
import { ManualPurchaseEntry } from "./ManualPurchaseEntry";
import { cardCls, inpCls, btnAcc, btnGhost } from "./common";
import { captureFileIdentity, captureRecord, captureRecoveryOutcome, normalizedManual, pendingCaptureJournal, stableCaptureValue } from "../lib/pendingCaptures";

const errorText = e => typeof e?.response?.data?.detail === "string" ? e.response.data.detail : e.message || "Source status could not be confirmed.";

export function PurchaseSourceCapture({ restaurantId, actorId, manualReady, vendors, files, busy, onBusy, onCaptured }) {
  const journal = useMemo(() => pendingCaptureJournal(actorId, restaurantId), [actorId, restaurantId]);
  const scope = useMemo(() => ({ active: true, journal, locked: false, selectedFiles: new Map() }), [journal]);
  const [records, setRecords] = useState([]), [checks, setChecks] = useState({}), [unavailable, setUnavailable] = useState(false);
  const [kind, setKind] = useState("csv"), [file, setFile] = useState(null), [error, setError] = useState("");
  const [epoch, setEpoch] = useState(0), [discard, setDiscard] = useState(null);
  useEffect(() => {
    scope.active = true;
    setChecks({}); setFile(null); setKind("csv"); setError(""); setDiscard(null); setEpoch(n => n + 1);
    try { setRecords(journal.list()); setUnavailable(false); } catch (e) { setUnavailable(true); setError(errorText(e)); }
    return () => { scope.active = false; };
  }, [scope, journal]);
  function current(record) {
    if (!scope.active) throw new Error("The signed-in user or restaurant changed. Reopen source recovery.");
    const found = journal.list().find(r => r.key === record.key);
    if (!found || stableCaptureValue(found) !== stableCaptureValue(record)) throw new Error("The retained source request changed. Check again.");
    return found;
  }
  function refresh() { if (scope.active) setRecords(journal.list()); }
  async function run(fn) {
    if (scope.locked || !scope.active) throw new Error("A source request is already running.");
    scope.locked = true; onBusy(true); setError("");
    try { return await fn(); }
    catch (e) { if (scope.active) setError(errorText(e)); throw e; }
    finally { scope.locked = false; if (scope.active) onBusy(false); }
  }
  async function check(record) {
    current(record);
    setChecks(s => ({ ...s, [record.key]: null }));
    const outcome = captureRecoveryOutcome(await api.checkCaptureSavedStatus(restaurantId, record), record, actorId, restaurantId);
    current(record);
    if (outcome.outcome !== "saved") { setChecks(s => ({ ...s, [record.key]: outcome })); return null; }
    const saved = await api.purchaseFile(restaurantId, outcome.fileId);
    current(record);
    if (saved?.id !== outcome.fileId || saved.source_sha256 !== outcome.sourceSha256 || saved.captureStatus !== "captured" || !Array.isArray(saved.documents)
      || (record.kind === "manual" && stableCaptureValue(saved.manualRecord) !== stableCaptureValue(record.body))) throw new Error("Saved source details were not confirmed. The original request is retained.");
    journal.clear(record); refresh(); scope.selectedFiles.delete(record.key); setDiscard(null);
    if (record.kind === "manual") setEpoch(n => n + 1); else setFile(null);
    onCaptured(saved, record.kind);
    return saved;
  }
  async function send(record, retry = false) {
    current(record);
    if (retry && checks[record.key]?.outcome !== "retry_available") throw new Error("Check saved status before retrying this source.");
    let source;
    if (record.kind !== "manual") {
      source = scope.selectedFiles.get(record.key);
      if (!source || stableCaptureValue(await captureFileIdentity(source, record.kind)) !== stableCaptureValue(record.body)) throw new Error("Reselect the original file with the same filename and exact bytes before retrying.");
      current(record);
    }
    setChecks(s => ({ ...s, [record.key]: null }));
    let commandError;
    try {
      if (record.kind === "manual") await api.captureManualPurchase(restaurantId, record.body, record.key);
      else await (record.kind === "source" ? api.capturePurchaseSource : api.capturePurchase)(restaurantId, source, record.key);
    } catch (e) { commandError = e; }
    // A lost or malformed command response is not proof of failure or success.
    const saved = await check(record);
    if (!saved) throw commandError || new Error("Capture is not yet confirmed. Check again or explicitly retry the same request.");
    return saved;
  }
  async function submitManual(body, key) {
    return run(async () => {
      const record = journal.save(captureRecord("manual", normalizedManual(body), key)); refresh();
      return send(record);
    });
  }
  async function submitFile() {
    return run(async () => {
      const source = file, body = await captureFileIdentity(source, kind);
      if (!scope.active) return;
      const record = journal.save(captureRecord(kind, body, crypto.randomUUID())); refresh();
      scope.selectedFiles.set(record.key, source);
      return send(record);
    });
  }
  const ignore = promise => promise.catch(() => {});
  const fileHeld = records.some(r => r.kind !== "manual"), manualHeld = records.some(r => r.kind === "manual");
  return <>
    {error && <p role="alert">{error}</p>}
    {!!records.length && <section aria-label="Retained source captures" className={`${cardCls} p-4 space-y-3`}>
      <h3>Submitted sources retained in this tab</h3>
      <p>Requests survive reload and sign-in by the same user in this tab. Nothing is resent automatically. Keep this tab open; recovery after closing it or restarting the browser is not guaranteed. Original file bytes are not stored in browser recovery.</p>
      {records.map(r => <div key={r.key} className="border border-slate-700 p-3 space-y-2">
        <p>{r.kind === "manual" ? `Manual source: ${r.body.documents.document_number || "Unnumbered"}` : r.body.filename}</p>
        <button className={btnGhost} disabled={busy || !!discard} onClick={() => ignore(run(() => check(r)))}>Check source saved status</button>
        {r.kind !== "manual" && <label>Reselect original file for retry <input aria-label={`Reselect source ${r.key}`} type="file" disabled={busy || !!discard} onChange={e => { scope.selectedFiles.set(r.key, e.target.files?.[0]); }} /></label>}
        {checks[r.key]?.outcome === "retry_available" && <>
          <p>No complete capture was visible in this read. The original request may still complete. Retry uses its same key and exact source.</p>
          <button className={btnAcc} disabled={busy || !!discard} onClick={() => ignore(run(() => send(r, true)))}>Retry retained source</button>
          <button className={btnGhost} disabled={busy || !!discard} onClick={() => setDiscard(r)}>Discard retained source request</button>
        </>}
      </div>)}
      {discard && <div aria-label="Confirm source request discard">
        <p>This removes only this tab's recovery record. It does not delete retained sources or cancel the original request, which may still finish. Check the captured files before entering a replacement.</p>
        <button className={btnGhost} disabled={busy} onClick={() => setDiscard(null)}>Keep source request</button>
        <button className={btnGhost} disabled={busy} onClick={() => ignore(run(async () => {
          if (await check(discard)) return;
          current(discard); journal.clear(discard); refresh(); scope.selectedFiles.delete(discard.key); setDiscard(null); setEpoch(n => n + 1);
        }))}>Confirm discard source request</button>
      </div>}
    </section>}
    <div className={`${cardCls} p-4 flex gap-3 flex-wrap items-center`}>
      {manualReady && <select aria-label="Source upload type" className={inpCls} disabled={busy || unavailable || fileHeld} value={kind} onChange={e => { setKind(e.target.value); setFile(null); }}><option value="csv">PFG / US Foods CSV</option><option value="source">Other invoice / receipt source</option></select>}
      <label>{kind === "csv" ? "PFG or US Foods original CSV" : "Retain original receipt, PDF, photo or other supplier file"} <input key={`${kind}:${fileHeld}`} aria-label="Invoice file" type="file" accept={kind === "csv" ? ".csv,text/csv" : undefined} disabled={busy || unavailable || fileHeld} onChange={e => setFile(e.target.files?.[0] || null)} /></label>
      <button className={btnAcc} disabled={busy || unavailable || fileHeld || !file} onClick={() => ignore(submitFile())}>Capture / retry file</button>
    </div>
    {manualReady && <ManualPurchaseEntry key={epoch} vendors={vendors} files={files} onCapture={submitManual} busy={busy || unavailable || manualHeld} />}
  </>;
}
