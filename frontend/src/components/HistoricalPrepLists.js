import React, { useEffect, useRef, useState } from "react";
import * as api from "../lib/api";
import { cardCls, inpCls, btnGhost } from "./common";

const labels = { all: "All recorded types", daily: "Daily Prep", bulk: "Bulk Prep", unclassified: "Unclassified", other: "Other recorded type" };
const decimalFields = ["yield_qty", "par", "on_hand", "needed_units", "batches_planned", "batches_done", "make_qty"];
const decimal = /^[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?$/;
const storeId = rid => rid === "papa_leonis" ? "papa" : rid;
const kind = value => value === null ? "unclassified" : value === "nightly_prep" ? "daily" : value === "commissary" ? "bulk" : "other";
const position = row => `${row.date}:${row.id}`;
const stored = value => value === null ? "Not recorded" : typeof value === "boolean" ? value ? "Yes" : "No" : typeof value === "object" ? JSON.stringify(value) : String(value);
const archive = value => value?.basis === "legacy_prep_archive" && value.archived === true && value.operational === false;
const uuid = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/;

function confirmed(data, rid, filters, cursor) {
  if (!archive(data) || data.storeId !== storeId(rid) || data.dateFrom !== (filters.date_from || null) || data.dateThrough !== (filters.date_through || null) || data.classification !== filters.classification || !Array.isArray(data.records) || data.records.length > 50) return false;
  const ids = new Set(); let prior = cursor ? `${cursor.after_date}:${cursor.after_id}` : "";
  for (const row of data.records) {
    if (!archive(row) || row.storeId !== storeId(rid) || typeof row.id !== "string" || !uuid.test(row.id) || ids.has(row.id) || !/^\d{4}-\d{2}-\d{2}$/.test(row.date) || !row.header || row.header.id !== row.id || row.header.store_id !== storeId(rid) || row.header.prep_date !== row.date || !["draft", "released"].includes(row.header.status) || !(row.countType === null || typeof row.countType === "string") || row.countType !== row.header.count_type || row.classification !== kind(row.countType) || row.track !== (["daily", "bulk"].includes(row.classification) ? row.classification : null) || !Array.isArray(row.lines)) return false;
    if (filters.classification !== "all" && row.classification !== filters.classification) return false;
    if ((filters.date_from && row.date < filters.date_from) || (filters.date_through && row.date > filters.date_through) || position(row) <= prior) return false;
    const lineIds = new Set();
    for (const line of row.lines) {
      if (!line || typeof line.id !== "string" || !uuid.test(line.id) || lineIds.has(line.id) || line.list_id !== row.id || decimalFields.some(field => line[field] !== null && !(typeof line[field] === "string" && decimal.test(line[field])))) return false;
      lineIds.add(line.id);
    }
    ids.add(row.id); prior = position(row);
  }
  const last = data.records[data.records.length - 1];
  return data.nextCursor === null || !!(last && data.nextCursor?.after_date === last.date && data.nextCursor.after_id === last.id);
}

function StoredFields({ value }) {
  return <dl className="grid gap-1" style={{ gridTemplateColumns: "minmax(110px,1fr) 3fr" }}>{Object.entries(value).map(([key, item]) => <React.Fragment key={key}><dt className="text-slate-400">{key.replace(/_/g, " ")}</dt><dd style={{ whiteSpace: "pre-wrap", overflowWrap: "anywhere" }}>{stored(item)}</dd></React.Fragment>)}</dl>;
}

export function HistoricalPrepLists(props) { return <ArchiveView key={props.rid} {...props} />; }
function ArchiveView({ rid }) {
  const [filters, setFilters] = useState({ date_from: "", date_through: "", classification: "all" });
  const [records, setRecords] = useState(null), [cursor, setCursor] = useState(null), [error, setError] = useState(""), [reading, setReading] = useState(false);
  const sequence = useRef(0);
  useEffect(() => { load(); return () => { sequence.current += 1; }; }, []); // eslint-disable-line react-hooks/exhaustive-deps
  async function load(more = false) {
    const request = ++sequence.current, continuation = more ? cursor : null;
    setReading(true); setError("");
    if (!more) { setRecords(null); setCursor(null); }
    const params = { classification: filters.classification, limit: 50, ...(filters.date_from ? { date_from: filters.date_from } : {}), ...(filters.date_through ? { date_through: filters.date_through } : {}), ...(continuation || {}) };
    try {
      if (filters.date_from && filters.date_through && filters.date_from > filters.date_through) throw new Error("Start date must not follow end date.");
      const data = await api.prepListArchive(rid, params);
      if (sequence.current !== request) return;
      if (!confirmed(data, rid, filters, continuation) || (more && data.records.some(row => records.some(previous => previous.id === row.id)))) throw new Error("Historical list read was not confirmed. Refresh to try again.");
      setRecords(previous => more ? [...previous, ...data.records] : data.records); setCursor(data.nextCursor);
    } catch (e) { if (sequence.current === request) setError(typeof e?.response?.data?.detail === "string" ? e.response.data.detail : e.message || "History could not be loaded."); }
    finally { if (sequence.current === request) setReading(false); }
  }
  function change(key, value) { setFilters(previous => ({ ...previous, [key]: value })); setRecords(null); setCursor(null); setError(""); }
  return <section className={`${cardCls} p-4 mb-6`} data-testid="historical-prep-lists">
    <h2 className="font-bold">Historical Prep Lists</h2>
    <p>Read-only history. Recorded quantities and notes are shown as stored. Unclassified records stay separate from Daily and Bulk Prep. These records do not change inventory or Food Cost.</p>
    <fieldset disabled={reading} className="flex gap-3 flex-wrap my-4">
      <label>From<input aria-label="History from date" type="date" className={inpCls} value={filters.date_from} onChange={e => change("date_from", e.target.value)} /></label>
      <label>Through<input aria-label="History through date" type="date" className={inpCls} value={filters.date_through} onChange={e => change("date_through", e.target.value)} /></label>
      <label>Recorded type<select aria-label="History recorded type" className={inpCls} value={filters.classification} onChange={e => change("classification", e.target.value)}>{Object.entries(labels).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>
      <button className={btnGhost} onClick={() => load()}>Apply / Refresh history</button>
    </fieldset>
    {error && <p role="alert">{error}{records ? " Previously loaded records are shown; additional history is not confirmed." : ""}</p>}
    {reading && <p role="status">Loading history…</p>}
    {records === null ? <p>History awaits a confirmed read.</p> : records.length === 0 ? <p>No historical lists match this selection.</p> : <>
      <p>{records.length} historical lists loaded.{cursor ? " More history is available." : " End of this selection."}</p>
      {records.map(row => <details key={row.id} className="my-3 border rounded p-3" data-testid={`historical-list-${row.id}`}><summary>{row.date} — {labels[row.classification]} — {row.header.status}</summary>
        <p>Historical list reference: {row.id}</p><h3 className="font-bold">Recorded header</h3><StoredFields value={row.header} />
        <h3 className="font-bold mt-3">Recorded lines</h3>{row.lines.length === 0 ? <p>No lines were recorded for this list.</p> : row.lines.map(line => <div key={line.id} className="mt-3 p-2 border rounded"><StoredFields value={line} /></div>)}
      </details>)}
    </>}
    {cursor && <button className={btnGhost} disabled={reading} onClick={() => load(true)}>Load more history</button>}
  </section>;
}
