import React, { useEffect, useState } from "react";
import * as api from "../lib/api";
import { cardCls, btnGhost } from "./common";

export function NativeInventoryPosition({ restaurantId }) {
  const [data, setData] = useState(null), [error, setError] = useState(""), [epoch, setEpoch] = useState(0);
  useEffect(() => {
    let active = true; setData(null); setError("");
    api.nativeOperatingSummary(restaurantId).then(result => {
      if (result?.basis !== "native_received_purchases_and_explicit_counts" || !Array.isArray(result.items) || result.liveOnHandAvailable !== false) throw new Error("Native count information was not confirmed.");
      if (active) setData(result);
    }).catch(e => { if (active) setError(typeof e?.response?.data?.detail === "string" ? e.response.data.detail : e.message || "Count information could not be loaded."); });
    return () => { active = false; };
  }, [restaurantId, epoch]);
  return <section className={`${cardCls} p-4 space-y-3`} data-testid="native-inventory-position">
    <h3 className="font-semibold">Last physical inventory count</h3>
    <p className="text-sm">This is a dated measurement of purchased items. Live on-hand is unknown between counts until prep, waste and sales explanations are available. Purchases do not establish what remains after use.</p>
    <button className={btnGhost} onClick={() => setEpoch(n => n + 1)}>Refresh physical count</button>
    {error ? <p role="alert">{error}</p> : !data ? <p>Loading reviewed counts…</p> : <>
      <p>Count status: {data.countStatus?.replaceAll("_", " ")} · {data.count?.count_date || "No current-scope count"} · {data.count?.timing?.replaceAll("_", " ") || ""}</p>
      <p>Explicit value at that count: {data.inventoryValue == null ? "Unavailable" : `${data.inventoryValue} USD`}</p>
      <p>Net received food purchases: {data.netFoodPurchases30} USD, {data.receivedFrom} to before {data.receivedBefore}. Taxes and fees remain separate.</p>
      {data.countStatus === "complete" && <div className="overflow-auto"><table className="ops-table"><thead><tr><th>Item</th><th>Counted quantity</th><th>Physical base quantity</th><th>Explicit value (USD)</th></tr></thead><tbody>{data.items.map(r => <tr key={r.item_code}><td>{r.item_code}</td><td>{r.counted_quantity} {r.counted_unit}</td><td>{r.base_quantity} {r.base_unit}</td><td>{r.inventory_value}</td></tr>)}</tbody></table></div>}
    </>}
  </section>;
}
