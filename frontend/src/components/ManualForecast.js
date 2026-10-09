import React, { useEffect, useRef, useState } from "react";
import * as api from "../lib/api";
import { useRetainedDraft } from "../lib/saveIntegrity";
import { cardCls, inpCls, btnAcc, Field, SectionLabel } from "./common";

const amount = value => typeof value === "string" && /^\d{1,10}(\.\d{1,2})?$/.test(value);
const cents = value => value.replace(/^0+(?=\d)/, "").split(".").map((v, i) => i ? v.padEnd(2, "0") : v).join(".") + (value.includes(".") ? "" : ".00");
const store = rid => rid === "papa_leonis" ? "papa" : rid;
export function validForecastReview(value, rid, date) {
  return value?.restaurantId === rid && value.storeId === store(rid) && value.date === date
    && value.basis === "manual_sales_forecast" && value.accounting === false && /^[a-f0-9]{64}$/.test(value.sourceVersion)
    && (value.projection === null || (value.projection.restaurantId === rid && value.projection.storeId === store(rid)
      && value.projection.date === date && value.projection.sourceVersion === value.sourceVersion
      && value.projection.basis === value.basis && value.projection.accounting === false && amount(value.projection.amount)
      && typeof value.projection.note === "string"));
}
export function ManualForecast({ rid, drafts, showToast }) {
  const tomorrow = new Date(); tomorrow.setDate(tomorrow.getDate() + 1);
  const initial = { date: `${tomorrow.getFullYear()}-${String(tomorrow.getMonth() + 1).padStart(2, "0")}-${String(tomorrow.getDate()).padStart(2, "0")}`, amount: "", note: "", version: null };
  const [draft, edit, acknowledge] = useRetainedDraft(`forecast:${rid}`, initial, drafts);
  const [review, setReview] = useState(null), [error, setError] = useState(""), [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(false);
  const [recent, setRecent] = useState(null), [recentError, setRecentError] = useState("");
  const scope = useRef(0), pending = useRef(false), current = useRef(draft); current.current = draft;
  useEffect(() => { const lifecycle = scope; ++lifecycle.current; return () => { ++lifecycle.current; }; }, [rid, draft.date]);
  useEffect(() => {
    let active = true; setRecent(null); setRecentError("");
    api.getProjections(rid).then(rows => {
      if (!active) return;
      if (!Array.isArray(rows) || rows.some(row => !validForecastReview({ ...row, projection: row }, rid, row.date))) throw new Error("Recent forecasts were not confirmed.");
      setRecent(rows);
    }).catch(e => { if (active) setRecentError(e.message || "Recent forecasts unavailable."); });
    return () => { active = false; };
  }, [rid]);
  async function load() {
    const generation = ++scope.current, day = draft.date;
    setLoading(true); setReview(null); setError("");
    try {
      const value = await api.getProjectionReview(rid, day);
      if (generation !== scope.current) return;
      if (!validForecastReview(value, rid, day)) throw new Error("Forecast review was not confirmed.");
      setReview(value);
      edit(p => ({ ...p, version: value.sourceVersion }));
    } catch (e) { if (generation === scope.current) setError(e?.response?.data?.detail || e.message || "Forecast review unavailable. Your draft is retained."); }
    finally { if (generation === scope.current) setLoading(false); }
  }
  // A retained draft requires an explicit new review on returning to this form.
  useEffect(() => { setReview(null); setLoading(false); setBusy(false); setError(""); }, [rid, draft.date]);
  function change(field, value) { edit(p => ({ ...p, [field]: value, ...(field === "date" ? { version: null } : {}) })); }
  async function save() {
    if (pending.current) return;
    if (!amount(draft.amount)) { setError("Enter a nonnegative amount with at most two decimal places."); return; }
    if (!review || review.date !== draft.date || draft.version !== review.sourceVersion) { setError("Review this date before saving."); return; }
    const submitted = draft, generation = scope.current;
    pending.current = true; setBusy(true); setError("");
    try {
      const value = await api.putProjection(rid, { date: submitted.date, amount: submitted.amount, note: submitted.note }, submitted.version);
      if (generation !== scope.current) return;
      if (value?.ok !== true || !validForecastReview(value, rid, submitted.date) || value.projection === null
          || cents(value.projection.amount) !== cents(submitted.amount) || value.projection.note !== submitted.note) {
        throw new Error("Save was not confirmed. Review this date again; your draft is retained.");
      }
      setReview(value);
      acknowledge(submitted, { ...submitted, amount: "", note: "", version: value.sourceVersion });
      setRecent(rows => rows === null ? rows : [value.projection, ...rows.filter(row => row.date !== submitted.date)].sort((a, b) => b.date.localeCompare(a.date)));
      if (current.current !== submitted) edit(p => ({ ...p, version: value.sourceVersion }));
      showToast?.("Projected sales saved");
    } catch (e) {
      if (generation === scope.current) { setReview(null); setError(e?.response?.data?.detail || e.message || "Save failed. Review this date again; your draft is retained."); }
    } finally { pending.current = false; if (generation === scope.current) setBusy(false); }
  }
  return <div className={`${cardCls} p-5`} data-testid="projections-card">
    <SectionLabel>Projected Sales (Manual Daily Entry)</SectionLabel>
    <p>Planning estimate only. Actual inventory and Food Cost use physical counts and received purchases.</p>
    <div className="flex gap-2 flex-wrap items-end mb-3">
      <Field label="Date"><input type="date" className={inpCls} data-testid="projection-date" value={draft.date} disabled={busy} onChange={e => change("date", e.target.value)} /></Field>
      <Field label="Amount ($)"><input inputMode="decimal" className={inpCls} data-testid="projection-amount" value={draft.amount} onChange={e => change("amount", e.target.value)} /></Field>
      <Field label="Note"><input className={inpCls} maxLength={2000} data-testid="projection-note" value={draft.note} onChange={e => change("note", e.target.value)} /></Field>
      <button className={btnAcc} disabled={busy || loading} onClick={load} data-testid="projection-review-button">Review date</button>
      <button className={btnAcc} disabled={busy || loading || !review} onClick={save} data-testid="projection-save-button">Save</button>
    </div>
    {loading && <p role="status">Loading forecast review…</p>}
    {error && <p role="alert">{error}</p>}
    {review && <p data-testid="projection-reviewed-value">{review.projection ? `Current forecast: $${review.projection.amount} — ${review.projection.note}` : "No forecast saved for this date."} Review this value before replacing it.</p>}
    {recentError && <p role="alert">{recentError}</p>}
    {recent?.slice(0, 6).map(row => <p key={row.date}>{row.date}: ${row.amount}{row.note ? ` — ${row.note}` : ""}</p>)}
  </div>;
}
