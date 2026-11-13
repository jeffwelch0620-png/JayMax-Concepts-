import React, { useEffect, useMemo, useRef, useState } from "react";
import * as api from "../lib/api";
import { prepTrackLabel } from "../lib/prepTracks";
import { cardCls, inpCls, btnAcc, btnGhost, EmptyState, Field, Pill } from "./common";

// M6 menu portions (Jeff 2026-11-13): which prep items one sold Toast item or modifier uses, and how much,
// in the prep item's own unit. Owners and the Ops Lead set them; the General Manager sees them.
// A portion is a planning reference: it never changes stock or food records.
const num = v => v === null || v === undefined ? "–" : Number(v).toLocaleString(undefined, { maximumFractionDigits: 3 });
const money = v => `$${Number(v || 0).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
const STATUS = {
  mapped: ["Has portions", "var(--jm-ok)", "color-mix(in srgb, var(--jm-ok) 12%, transparent)"],
  no_prep: ["No tracked prep", "var(--jm-ink-3)", "color-mix(in srgb, var(--jm-ink-3) 12%, transparent)"],
  missing: ["Missing", "var(--jm-warn)", "color-mix(in srgb, var(--jm-warn) 12%, transparent)"],
};
const FILTERS = [["missing", "Missing"], ["mapped", "Has portions"], ["no_prep", "No tracked prep"], ["all", "All"]];

function Editor({ rid, item, products, onSaved, onClose }) {
  const [lines, setLines] = useState(item.lines.map(l => ({ product_id: l.product_id, base_quantity: String(Number(l.base_quantity)) })));
  const [noPrep, setNoPrep] = useState(item.no_prep);
  const [fromStart, setFromStart] = useState(true);
  const [from, setFrom] = useState("");
  const [reason, setReason] = useState("");
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);
  const [history, setHistory] = useState(null);
  const attempt = useRef(null);
  const unit = id => products.find(p => p.product_id === id)?.base_unit || "";
  const body = { sold_kind: item.kind, sold_guid: item.guid, sold_name: item.name, no_prep: noPrep, reason: reason.trim(),
    effective_from: fromStart ? null : from || null, lines: noPrep ? [] : lines.filter(l => l.product_id).map(l => ({ product_id: l.product_id, base_quantity: l.base_quantity.trim() })) };
  const signature = JSON.stringify(body);
  useEffect(() => { api.menuPortionHistory(rid, item.kind, item.guid).then(h => setHistory(h.changes || [])).catch(() => setHistory([])); }, [rid, item.kind, item.guid]);
  const save = () => {
    if (!fromStart && !from) { setError("Choose the date the portions start, or apply them from the start"); return; }
    if (body.lines.some(l => !(Number(l.base_quantity) > 0))) { setError("Each prep item needs an amount above zero"); return; }
    // The same key for a retry of the same change, a new one when the change is edited.
    if (!attempt.current || attempt.current.signature !== signature) attempt.current = { signature, key: crypto.randomUUID() };
    setSaving(true); setError("");
    api.saveMenuPortion(rid, body, attempt.current.key)
      .then(() => { attempt.current = null; onSaved(); })
      .catch(e => setError(e?.response?.data?.detail?.toString?.() || "The portions could not be saved"))
      .finally(() => setSaving(false));
  };
  const name = id => products.find(p => p.product_id === id)?.name || "Removed prep item";
  return (
    <div className={`${cardCls} p-4 mb-3`} data-testid="portion-editor">
      <p className="text-sm font-semibold text-slate-200 mb-1">{item.name} <span className="text-slate-500 font-normal">· {item.kind === "item" ? "menu item" : "modifier"}, one sold</span></p>
      <p className="text-xs text-slate-500 mb-3">Each amount is how much of the prep item one {item.kind === "item" ? "of these" : "of this add-on"} uses, in the prep item's own unit.</p>
      <label className="flex items-center gap-2 text-sm text-slate-300 mb-3">
        <input type="checkbox" checked={noPrep} onChange={e => setNoPrep(e.target.checked)} data-testid="portion-no-prep" />
        Uses no tracked prep (drinks, bought-in items)
      </label>
      {!noPrep && <>
        {lines.map((l, i) => (
          <div key={i} className="flex flex-wrap items-end gap-2 mb-2">
            <Field label={i === 0 ? "Prep item" : ""}>
              <select className={inpCls} value={l.product_id} onChange={e => setLines(lines.map((x, j) => j === i ? { ...x, product_id: e.target.value } : x))} data-testid={`portion-product-${i}`}>
                <option value="">Choose…</option>
                {products.map(p => <option key={p.product_id} value={p.product_id}>{p.name}{p.track ? ` (${prepTrackLabel(p.track)})` : ""}</option>)}
              </select>
            </Field>
            <Field label={i === 0 ? "Amount" : ""}>
              <div className="flex items-center gap-2">
                <input className={`${inpCls} w-24`} inputMode="decimal" value={l.base_quantity} onChange={e => setLines(lines.map((x, j) => j === i ? { ...x, base_quantity: e.target.value } : x))} data-testid={`portion-quantity-${i}`} />
                <span className="text-xs text-slate-500">{unit(l.product_id)}</span>
              </div>
            </Field>
            <button className={btnGhost} onClick={() => setLines(lines.filter((_, j) => j !== i))}>Remove</button>
          </div>
        ))}
        <button className={`${btnGhost} mb-3`} onClick={() => setLines([...lines, { product_id: "", base_quantity: "" }])} data-testid="portion-add-line">Add a prep item</button>
      </>}
      <div className="flex flex-wrap gap-3 items-end mb-3">
        <Field label="Applies">
          <select className={inpCls} value={fromStart ? "start" : "date"} onChange={e => setFromStart(e.target.value === "start")} data-testid="portion-applies">
            <option value="start">From the start of the sales history</option>
            <option value="date">From a date</option>
          </select>
        </Field>
        {!fromStart && <Field label="From"><input type="date" className={inpCls} value={from} onChange={e => setFrom(e.target.value)} data-testid="portion-from" /></Field>}
        <Field label="Note (optional)"><input className={`${inpCls} w-64`} maxLength={500} value={reason} onChange={e => setReason(e.target.value)} placeholder="e.g. from the recipe card" /></Field>
      </div>
      {error && <p role="alert" className="text-sm text-jm-bad mb-2">{error}</p>}
      <div className="flex gap-2">
        <button className={btnAcc} onClick={save} disabled={saving} data-testid="portion-save">{saving ? "Saving…" : "Save portions"}</button>
        <button className={btnGhost} onClick={onClose}>Cancel</button>
      </div>
      {history && history.length > 0 && (
        <details className="mt-3 text-xs text-slate-500">
          <summary className="cursor-pointer">Earlier changes ({history.length} lines)</summary>
          <ul className="mt-1 space-y-0.5">
            {history.map(h => <li key={h.id}>{h.recorded_at?.slice(0, 16).replace("T", " ")} · {h.product_id ? `${name(h.product_id)}: ${num(h.base_quantity)} ${h.base_unit}` : Number(h.base_quantity) ? "uses no tracked prep" : "tracked prep again"}
              {h.effective_from ? ` from ${h.effective_from}` : " from the start"} · {h.recorded_by}{h.reason ? ` · ${h.reason}` : ""}</li>)}
          </ul>
        </details>
      )}
    </div>
  );
}

export function MenuPortions({ rid, onChanged }) {
  const [data, setData] = useState(null);
  const [error, setError] = useState("");
  const [filter, setFilter] = useState("missing");
  const [kind, setKind] = useState("item");
  const [search, setSearch] = useState("");
  const [editing, setEditing] = useState(null);
  const load = () => api.menuPortions(rid).then(d => { setData(d); setError(""); }).catch(e => setError(e?.response?.data?.detail || "Menu portions could not be loaded"));
  useEffect(() => { setData(null); setEditing(null); load(); }, [rid]); // eslint-disable-line react-hooks/exhaustive-deps
  const shown = useMemo(() => !data?.available ? [] : data.sold.filter(s => s.kind === kind && (filter === "all" || s.status === filter)
    && (!search.trim() || s.name.toLowerCase().includes(search.trim().toLowerCase()))), [data, filter, kind, search]);
  if (error) return <p role="alert" className="text-sm text-jm-bad">{error}</p>;
  if (!data) return <EmptyState text="Loading menu portions…" />;
  if (!data.available) return <p className="text-sm text-slate-500">{data.reason === "toast" ? "Toast sales are not available to this server yet." : "Menu portions are not set up at this store yet."}</p>;
  const names = Object.fromEntries(data.products.map(p => [p.product_id, p]));
  const items = data.sold.filter(s => s.kind === "item");
  const counts = k => items.filter(s => s.status === k).length;
  return (
    <div data-testid="menu-portions">
      <p className="text-xs text-slate-500 mb-2">
        Menu items sold in the last {data.days} days. {counts("mapped")} have portions, {counts("no_prep")} use no tracked prep and {counts("missing")} are missing.
        {data.can_edit ? " Portions apply from the start of the sales history unless you choose a date." : " Only an owner or the Operations & Integration Lead changes portions."}
      </p>
      <div className="flex flex-wrap gap-3 mb-3 items-end">
        <Field label="Show">
          <select className={inpCls} value={filter} onChange={e => setFilter(e.target.value)} data-testid="portion-filter">
            {FILTERS.map(([k, label]) => <option key={k} value={k}>{label}</option>)}
          </select>
        </Field>
        <Field label="Sold as">
          <select className={inpCls} value={kind} onChange={e => setKind(e.target.value)} data-testid="portion-kind">
            <option value="item">Menu items</option>
            <option value="modifier">Modifiers and add-ons</option>
          </select>
        </Field>
        <Field label="Search"><input className={inpCls} value={search} onChange={e => setSearch(e.target.value)} placeholder="Item name" data-testid="portion-search" /></Field>
      </div>
      {editing && <Editor key={`${editing.kind}:${editing.guid}`} rid={rid} item={editing} products={data.products}
        onClose={() => setEditing(null)} onSaved={() => { setEditing(null); load(); onChanged && onChanged(); }} />}
      {!shown.length ? <p className="text-sm text-slate-500">Nothing to show for this choice.</p> : (
        <div className={`${cardCls} overflow-x-auto`} data-testid="portion-list">
          <table className="w-full text-sm">
            <thead><tr className="text-left text-[11px] uppercase tracking-[0.06em] text-slate-500">
              {["Sold", "Qty (90 days)", "Sales", "Portions", "", ""].map((h, i) => <th key={i} className="px-3 py-2 font-bold">{h}</th>)}</tr></thead>
            <tbody>{shown.slice(0, 200).map(s => (
              <tr key={`${s.kind}:${s.guid}`} className="border-t border-jm-line text-slate-300">
                <td className="px-3 py-2">{s.name}</td>
                <td className="px-3 py-2 whitespace-nowrap">{num(s.quantity)}</td>
                <td className="px-3 py-2 whitespace-nowrap">{money(s.amount)}</td>
                <td className="px-3 py-2">{s.lines.map(l => `${names[l.product_id]?.name || "?"} ${num(l.base_quantity)} ${names[l.product_id]?.base_unit || ""}`).join(" · ") || "–"}</td>
                <td className="px-3 py-2"><Pill color={STATUS[s.status][1]} bg={STATUS[s.status][2]}>{STATUS[s.status][0]}</Pill></td>
                <td className="px-3 py-2 text-right">{data.can_edit && <button className={btnGhost} onClick={() => setEditing(s)} data-testid={`portion-edit-${s.guid}`}>Edit</button>}</td>
              </tr>))}</tbody>
          </table>
          {shown.length > 200 && <p className="text-xs text-slate-500 px-3 py-2">Showing 200 of {shown.length}; search to find others.</p>}
        </div>
      )}
    </div>
  );
}
