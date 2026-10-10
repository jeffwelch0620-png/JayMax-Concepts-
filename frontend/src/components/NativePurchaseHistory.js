import React, { useEffect, useState } from "react";
import * as api from "../lib/api";
import { PageTitle, cardCls, inpCls, btnGhost } from "./common";

export function NativePurchaseHistory({ restaurantId, onOpenInvoices }) {
  const [rows, setRows] = useState(null), [error, setError] = useState("");
  const [search, setSearch] = useState(""), [epoch, setEpoch] = useState(0);
  useEffect(() => {
    let active = true;
    setRows(null); setError("");
    api.purchaseHistory(restaurantId).then(result => {
      if (!Array.isArray(result) || result.some(r => !r.line_id || !r.mapping_id || r.base_quantity == null || r.inventory_cost_amount == null)) {
        throw new Error("Posted purchase history was not confirmed. Refresh to retry.");
      }
      if (active) setRows(result);
    }).catch(e => {
      if (active) setError(typeof e?.response?.data?.detail === "string" ? e.response.data.detail : e.message || "Purchase history could not be loaded.");
    });
    return () => { active = false; };
  }, [restaurantId, epoch]);
  const visible = (rows || []).filter(r => [r.item_code, r.description_snapshot, r.vendor_id, r.document_number].some(v => String(v || "").toLowerCase().includes(search.toLowerCase())));
  return <section data-testid="native-purchase-history" className="space-y-4">
    <PageTitle>Posted Purchase History</PageTitle>
    <p>Received dates, physical quantities and food amounts come from the posted purchase ledger. Invoice corrections retain the original entry, its reversal and the replacement. Taxes and fees are retained separately in Invoice Master.</p>
    <p className="text-sm">These are signed ledger entries, not supplier quotes or prices per case. Food Cost uses their net food amount together with the explicit opening and closing count values in Actual Inventory.</p>
    <div className="flex flex-wrap gap-3">
      <input aria-label="Search posted purchases" className={inpCls} value={search} onChange={e => setSearch(e.target.value)} placeholder="Item, supplier or invoice" />
      <button className={btnGhost} onClick={() => setEpoch(n => n + 1)}>Refresh purchase history</button>
      {onOpenInvoices && <button className={btnGhost} onClick={onOpenInvoices}>Open Invoice Master</button>}
    </div>
    {error ? <p role="alert">{error}</p> : rows === null ? <p>Loading posted purchase history…</p> : !visible.length ? <p>{rows.length ? "No matching purchases." : "No purchases have been posted to this ledger."}</p> :
      <div className={`${cardCls} overflow-auto`}><table className="ops-table"><thead><tr>{["Received / inventory date", "Supplier", "Invoice", "Item", "Entry", "Signed quantity", "Food amount (USD)"].map(h => <th key={h}>{h}</th>)}</tr></thead>
        <tbody>{visible.map(r => <tr key={r.fact_id || `${r.line_id}:${r.mapping_id}`}>
          <td>{r.inventory_record_date || "No inventory movement date"}</td><td>{r.vendor_id}</td><td>{r.document_number}</td>
          <td>{r.description_snapshot}{r.item_code ? ` (${r.item_code})` : " · No inventory item"}</td>
          <td>{r.fact_kind === "reversal" ? "Reversal" : r.fact_kind === "replacement" ? "Replacement" : "Original posting"}</td>
          <td>{r.base_quantity} {r.base_unit}</td><td>{r.inventory_cost_amount}</td>
        </tr>)}</tbody></table></div>}
  </section>;
}
