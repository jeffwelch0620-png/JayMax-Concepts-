import React, { useMemo, useRef, useState } from "react";
import { Plus, Trash2, Save, Upload } from "lucide-react";
import { VENDORS, PURCHASE_UNITS, todayISO, fmtDate, fmtMoney, uid, parseCSV, detectVendorFormat, rowsToObjects, normalizePFGRows, normalizeUSFoodsRows, matchRowToItem, suggestMatch } from "../lib/calc";
import { PageTitle, EmptyState, Field, SectionLabel, Pill, cardCls, inpCls, btnAcc, btnGhost } from "./common";

export function InvoicesTab({ items, persistItems, purchases, persistPurchases, showToast, restaurantName }) {
  const [mode, setMode] = useState("auto");
  const [header, setHeader] = useState({ invoiceDate: todayISO(), invoiceNumber: "", vendor: VENDORS[0] });
  const [lines, setLines] = useState([]);
  const [lineDraft, setLineDraft] = useState({ controlNumber: items[0]?.controlNumber || "", qty: "", unit: "case", unitCost: "" });
  const fileRef = useRef(null);
  const autoFileRef = useRef(null);

  function invoiceAlreadyExists(vendor, invoiceNumber, invoiceDate) {
    const numKey = String(invoiceNumber || "").trim().toLowerCase();
    return purchases.some((p) => p.vendor === vendor && String(p.invoiceNumber || "").trim().toLowerCase() === numKey && (!invoiceDate || p.invoiceDate === invoiceDate));
  }

  function addLine() {
    const item = items.find((i) => i.controlNumber === lineDraft.controlNumber);
    if (!item || !lineDraft.qty || !lineDraft.unitCost) return;
    setLines((ls) => [...ls, { controlNumber: item.controlNumber, itemName: item.name, qty: Number(lineDraft.qty) || 0, unit: lineDraft.unit, unitCost: Number(lineDraft.unitCost) || 0 }]);
    setLineDraft((d) => ({ ...d, qty: "", unitCost: "" }));
  }
  function removeLine(idx) { setLines((ls) => ls.filter((_, i) => i !== idx)); }

  function applyPriceUpdates(itemsList, purchaseLines, vendor) {
    return itemsList.map((it) => {
      const hit = purchaseLines.find((l) => l.controlNumber === it.controlNumber);
      if (!hit) return it;
      const skus = it.vendorSkus || [];
      const matchIdx = skus.findIndex((s) => s.vendor === vendor);
      if (matchIdx === -1) return it;
      const updatedSkus = skus.map((s, i) => i === matchIdx ? { ...s, price: hit.unitCost, priceUpdatedAt: hit.invoiceDate || todayISO(), priceSource: "invoice_import" } : s);
      return { ...it, vendorSkus: updatedSkus };
    });
  }

  async function saveInvoice() {
    if (!header.invoiceNumber.trim() || lines.length === 0) return;
    if (invoiceAlreadyExists(header.vendor, header.invoiceNumber, header.invoiceDate)) { showToast(`Invoice ${header.invoiceNumber} is already in purchase history`); return; }
    const invoiceId = uid("inv");
    const newPurchases = lines.map((l) => ({
      id: uid("pl"), invoiceId, invoiceDate: header.invoiceDate, invoiceNumber: header.invoiceNumber.trim(), vendor: header.vendor,
      controlNumber: l.controlNumber, itemName: l.itemName, qty: l.qty, unit: l.unit, unitCost: l.unitCost, extendedCost: l.qty * l.unitCost,
    }));
    await persistPurchases([...purchases, ...newPurchases]);
    await persistItems(applyPriceUpdates(items, newPurchases, header.vendor));
    showToast(`Invoice ${header.invoiceNumber} logged — ${newPurchases.length} line item${newPurchases.length !== 1 ? "s" : ""}`);
    setLines([]);
    setHeader((h) => ({ ...h, invoiceNumber: "" }));
  }

  const [autoRows, setAutoRows] = useState([]);
  const [skippedFiles, setSkippedFiles] = useState([]);
  const [overrides, setOverrides] = useState({});

  function readFileAsText(file) {
    return new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => resolve(String(reader.result || ""));
      reader.onerror = reject;
      reader.readAsText(file);
    });
  }

  async function onAutoFiles(e) {
    const files = Array.from(e.target.files || []);
    if (files.length === 0) return;
    const collected = [];
    const skipped = [];
    for (const file of files) {
      try {
        const text = await readFileAsText(file);
        const rows = parseCSV(text);
        if (rows.length < 2) { skipped.push(file.name); continue; }
        const headers = rows[0].map((h) => h.trim());
        const format = detectVendorFormat(headers);
        if (!format) { skipped.push(file.name); continue; }
        const objs = rowsToObjects(headers, rows.slice(1));
        const normalized = format === "pfg" ? normalizePFGRows(objs) : normalizeUSFoodsRows(objs);
        collected.push(...normalized);
      } catch (err) {
        skipped.push(file.name);
      }
    }
    setAutoRows(collected);
    setSkippedFiles(skipped);
    setOverrides({});
    if (autoFileRef.current) autoFileRef.current.value = "";
  }

  const autoMatched = useMemo(() => autoRows.map((row, idx) => {
    const { item, matchedBy } = matchRowToItem(row, items);
    const suggestion = !item ? suggestMatch(row.description, items) : null;
    return { ...row, idx, item, matchedBy, suggestion };
  }), [autoRows, items]);

  function effectiveItemFor(r) {
    if (r.item) return { item: r.item, source: r.matchedBy };
    const ov = overrides[r.idx];
    if (ov === "skip") return { item: null, source: "skipped" };
    if (ov) return { item: items.find((it) => it.controlNumber === ov) || null, source: "manual" };
    if (r.suggestion && r.suggestion.score >= 0.5) return { item: r.suggestion.item, source: "suggested" };
    return { item: null, source: null };
  }

  const autoGroups = useMemo(() => {
    const map = {};
    autoMatched.forEach((r) => {
      const key = `${r.vendor}|${r.invoiceNumber}`;
      if (!map[key]) map[key] = { vendor: r.vendor, invoiceNumber: r.invoiceNumber, invoiceDate: r.invoiceDate, rows: [] };
      map[key].rows.push(r);
    });
    return Object.values(map).sort((a, b) => a.invoiceDate.localeCompare(b.invoiceDate));
  }, [autoMatched]);

  const autoResolved = autoMatched.map((r) => ({ r, resolved: effectiveItemFor(r) }));
  const duplicateAutoGroups = new Set(autoGroups.filter((g) => invoiceAlreadyExists(g.vendor, g.invoiceNumber, g.invoiceDate)).map((g) => `${g.vendor}|${g.invoiceNumber}`));
  const autoMatchedCount = autoResolved.filter((x) => x.resolved.item && !duplicateAutoGroups.has(`${x.r.vendor}|${x.r.invoiceNumber}`)).length;
  const autoUnresolvedCount = autoResolved.filter((x) => !x.resolved.item).length;

  async function commitAuto() {
    const matchedRows = autoResolved.filter((x) => x.resolved.item && x.r.qty > 0 && !duplicateAutoGroups.has(`${x.r.vendor}|${x.r.invoiceNumber}`)).map((x) => ({ ...x.r, item: x.resolved.item }));
    if (matchedRows.length === 0) return;
    const invoiceIdByGroup = {};
    const newPurchases = matchedRows.map((r) => {
      const key = `${r.vendor}|${r.invoiceNumber}`;
      if (!invoiceIdByGroup[key]) invoiceIdByGroup[key] = uid("inv");
      return {
        id: uid("pl"), invoiceId: invoiceIdByGroup[key], invoiceDate: r.invoiceDate, invoiceNumber: r.invoiceNumber, vendor: r.vendor,
        controlNumber: r.item.controlNumber, itemName: r.item.name, qty: r.qty, unit: r.unit, unitCost: r.unitCost, extendedCost: r.extendedCost || r.qty * r.unitCost,
      };
    });
    const nextItems = items.map((it) => {
      const hits = matchedRows.filter((r) => r.item.controlNumber === it.controlNumber);
      if (hits.length === 0) return it;
      let skus = it.vendorSkus || [];
      hits.forEach((r) => {
        const idx = skus.findIndex((s) => s.vendor === r.vendor);
        if (idx !== -1) {
          const existing = skus[idx];
          skus = skus.map((s, i) => i === idx ? {
            ...s, price: r.unitCost, priceUpdatedAt: r.invoiceDate || todayISO(), priceSource: "invoice_import",
            vendorSku: (!existing.vendorSku || existing.vendorSku === "—") && r.vendorSku ? r.vendorSku : existing.vendorSku,
            packDescription: existing.packDescription || r.packDescription,
          } : s);
        } else {
          skus = [...skus, { id: uid("vs"), vendor: r.vendor, vendorSku: r.vendorSku, packDescription: r.packDescription, purchaseUnit: r.unit || "case", packCount: 0, unitQty: 0, unitUOM: "each", price: r.unitCost, priceUpdatedAt: r.invoiceDate || todayISO(), priceSource: "invoice_import", available: true, preferred: skus.length === 0 }];
        }
      });
      return { ...it, vendorSkus: skus };
    });
    await persistPurchases([...purchases, ...newPurchases]);
    await persistItems(nextItems);
    showToast(`Imported ${newPurchases.length} line item${newPurchases.length !== 1 ? "s" : ""} across ${Object.keys(invoiceIdByGroup).length} invoice${Object.keys(invoiceIdByGroup).length !== 1 ? "s" : ""}`);
    setAutoRows([]); setSkippedFiles([]); setOverrides({});
  }

  const [csvRows, setCsvRows] = useState(null);
  const [csvHeaders, setCsvHeaders] = useState([]);
  const [mapping, setMapping] = useState({ item: "", qty: "", unit: "", cost: "" });

  function onOtherFile(e) {
    const file = e.target.files?.[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = () => {
      const rows = parseCSV(String(reader.result || ""));
      if (rows.length < 2) { showToast("Couldn't find any data rows in that file"); return; }
      setCsvHeaders(rows[0]);
      setCsvRows(rows.slice(1));
      setMapping({ item: "", qty: "", unit: "", cost: "" });
    };
    reader.readAsText(file);
  }

  const csvPreview = useMemo(() => {
    if (!csvRows || !mapping.item || !mapping.qty || !mapping.cost) return [];
    const itemIdx = csvHeaders.indexOf(mapping.item);
    const qtyIdx = csvHeaders.indexOf(mapping.qty);
    const unitIdx = mapping.unit ? csvHeaders.indexOf(mapping.unit) : -1;
    const costIdx = csvHeaders.indexOf(mapping.cost);
    return csvRows.filter((r) => r.some((c) => c !== "")).map((r) => {
      const raw = (r[itemIdx] || "").trim();
      const match = items.find((it) => it.controlNumber.toLowerCase() === raw.toLowerCase())
        || items.find((it) => it.name.toLowerCase() === raw.toLowerCase())
        || items.find((it) => raw && it.name.toLowerCase().includes(raw.toLowerCase()));
      const qty = Number(r[qtyIdx]) || 0;
      const unitCost = Number(r[costIdx]) || 0;
      return { raw, match, qty, unit: unitIdx >= 0 ? (r[unitIdx] || "case") : "case", unitCost };
    });
  }, [csvRows, mapping, csvHeaders, items]);

  async function commitCSV() {
    const matched = csvPreview.filter((r) => r.match && r.qty > 0);
    if (matched.length === 0) return;
    const invoiceId = uid("inv");
    const newPurchases = matched.map((r) => ({
      id: uid("pl"), invoiceId, invoiceDate: header.invoiceDate, invoiceNumber: header.invoiceNumber.trim() || `CSV-${invoiceId.slice(-6)}`, vendor: header.vendor,
      controlNumber: r.match.controlNumber, itemName: r.match.name, qty: r.qty, unit: r.unit, unitCost: r.unitCost, extendedCost: r.qty * r.unitCost,
    }));
    await persistPurchases([...purchases, ...newPurchases]);
    await persistItems(applyPriceUpdates(items, newPurchases, header.vendor));
    showToast(`Imported ${newPurchases.length} line item${newPurchases.length !== 1 ? "s" : ""}`);
    setCsvRows(null); setCsvHeaders([]); setMapping({ item: "", qty: "", unit: "", cost: "" });
    if (fileRef.current) fileRef.current.value = "";
  }

  if (items.length === 0) return <EmptyState text="Add items in Item Setup first — invoices need matching control numbers." />;

  const modeBtn = (m) => mode === m ? btnAcc : btnGhost;

  return (
    <div className="fade-slide-in" data-testid="invoices-tab">
      <PageTitle>Invoice Master</PageTitle>
      <div className="flex gap-2 mb-4 flex-wrap">
        <button data-testid="invoice-mode-auto" className={modeBtn("auto")} onClick={() => setMode("auto")}><Upload size={14} /> US Foods / PFG Import</button>
        <button data-testid="invoice-mode-manual" className={modeBtn("manual")} onClick={() => setMode("manual")}>Manual Entry</button>
        <button data-testid="invoice-mode-other" className={modeBtn("other")} onClick={() => setMode("other")}>Other Vendor (map columns)</button>
      </div>

      {mode === "auto" && (
        <div className={`${cardCls} p-5 mb-6`}>
          <SectionLabel>Upload Invoice Export(s)</SectionLabel>
          <div className="text-[13px] text-slate-400 mb-3">
            Drop in a PFG "CustomerFirstInvoiceExport" file (one file, multiple invoices) and/or US Foods "InvoiceDetails" files (one invoice per file — select as many as you like at once). Format is auto-detected and columns are mapped automatically.
          </div>
          <input ref={autoFileRef} type="file" accept=".csv,text/csv" multiple onChange={onAutoFiles} className="mb-3.5 text-sm text-slate-400 file:mr-3 file:rounded-lg file:border file:border-[#334155] file:bg-[#1E293B] file:px-3 file:py-1.5 file:text-slate-200 file:text-xs file:font-semibold" data-testid="invoice-file-input" />
          {skippedFiles.length > 0 && (
            <div className="text-xs text-red-400 mb-3">Couldn't recognize the format of: {skippedFiles.join(", ")}. Use "Other Vendor" to map its columns manually.</div>
          )}
          {autoGroups.length > 0 && (
            <>
              <div className="flex gap-4 mb-1 flex-wrap">
                <Pill color="#10B981" bg="rgba(16,185,129,0.12)">{autoMatchedCount} ready to import</Pill>
                {autoUnresolvedCount > 0 && <Pill color="#EF4444" bg="rgba(239,68,68,0.12)">{autoUnresolvedCount} need review</Pill>}
                <Pill color="#94A3B8" bg="#1E293B">{autoGroups.length} invoice{autoGroups.length !== 1 ? "s" : ""}</Pill>
              </div>
              <div className="text-xs text-slate-500 mb-3.5">Green rows matched automatically (by vendor SKU or exact name). Amber rows are best-guess suggestions — pick the right item or choose "Skip" for anything genuinely new. Nothing imports until you click the button below.</div>
              {autoGroups.map((g) => {
                const total = g.rows.reduce((s, r) => s + (r.extendedCost || r.qty * r.unitCost), 0);
                return (
                  <div key={`${g.vendor}|${g.invoiceNumber}`} className="mb-4 border border-[#28354A] rounded-lg overflow-hidden">
                    <div className="bg-[#1A2438] px-3 py-2 text-[13px] font-bold flex justify-between" style={{ color: "var(--acc)" }}>
                      <span>{g.vendor} — Invoice {g.invoiceNumber} — {fmtDate(g.invoiceDate)} {duplicateAutoGroups.has(`${g.vendor}|${g.invoiceNumber}`) && <Pill color="#EF4444" bg="rgba(239,68,68,0.12)">Already imported — skipped</Pill>}</span>
                      <span className="num">{fmtMoney(total)}</span>
                    </div>
                    <table className="ops-table">
                      <thead><tr><th>Description</th><th>Vendor SKU</th><th>Matched Item</th><th>Qty</th><th>Unit Cost</th></tr></thead>
                      <tbody>
                        {g.rows.map((r) => {
                          const resolved = effectiveItemFor(r);
                          const rowBg = resolved.source === "sku" || resolved.source === "name" ? "transparent" : resolved.source === "suggested" || resolved.source === "manual" ? "rgba(245,158,11,0.06)" : "rgba(239,68,68,0.08)";
                          return (
                            <tr key={r.idx} style={{ background: rowBg }}>
                              <td>{r.description}</td>
                              <td>{r.vendorSku || "—"}</td>
                              <td>
                                {r.item ? (
                                  <span>{r.item.controlNumber} — {r.item.name} <span className="text-[11px] text-slate-500">({r.matchedBy === "sku" ? "SKU match" : "exact name match"})</span></span>
                                ) : (
                                  <select className={`${inpCls} text-xs py-1.5`} value={overrides[r.idx] ?? (r.suggestion && r.suggestion.score >= 0.5 ? r.suggestion.item.controlNumber : "skip")}
                                    onChange={(e) => setOverrides((o) => ({ ...o, [r.idx]: e.target.value }))}>
                                    <option value="skip">Skip — no match</option>
                                    {r.suggestion && <option value={r.suggestion.item.controlNumber}>Suggested: {r.suggestion.item.controlNumber} — {r.suggestion.item.name}</option>}
                                    {items.filter((it) => !r.suggestion || it.controlNumber !== r.suggestion.item.controlNumber).map((it) => (
                                      <option key={it.controlNumber} value={it.controlNumber}>{it.controlNumber} — {it.name}</option>
                                    ))}
                                  </select>
                                )}
                              </td>
                              <td className="num">{r.qty} {r.unit}</td>
                              <td className="num">{fmtMoney(r.unitCost)}</td>
                            </tr>
                          );
                        })}
                      </tbody>
                    </table>
                  </div>
                );
              })}
              <button className={btnAcc} onClick={commitAuto} disabled={autoMatchedCount === 0} data-testid="import-auto-button">
                <Save size={15} /> Import {autoMatchedCount} Line{autoMatchedCount !== 1 ? "s" : ""}
              </button>
            </>
          )}
        </div>
      )}

      {mode === "manual" && (
        <div className={`${cardCls} p-5 mb-6`}>
          <SectionLabel>Invoice Header</SectionLabel>
          <div className="grid gap-3 mb-4" style={{ gridTemplateColumns: "repeat(auto-fit, minmax(150px, 1fr))" }}>
            <Field label="Invoice Date"><input type="date" className={inpCls} value={header.invoiceDate} onChange={(e) => setHeader((h) => ({ ...h, invoiceDate: e.target.value }))} /></Field>
            <Field label="Invoice #"><input className={inpCls} data-testid="invoice-number-input" value={header.invoiceNumber} onChange={(e) => setHeader((h) => ({ ...h, invoiceNumber: e.target.value }))} placeholder="e.g. INV-100234" /></Field>
            <Field label="Vendor"><select className={inpCls} value={header.vendor} onChange={(e) => setHeader((h) => ({ ...h, vendor: e.target.value }))}>{VENDORS.map((v) => <option key={v} value={v}>{v}</option>)}</select></Field>
          </div>
          <SectionLabel>Line Items</SectionLabel>
          <div className="flex gap-2 flex-wrap items-end mb-3">
            <Field label="Item">
              <select className={inpCls} data-testid="invoice-line-item" value={lineDraft.controlNumber} onChange={(e) => setLineDraft((d) => ({ ...d, controlNumber: e.target.value }))}>
                {items.map((it) => <option key={it.controlNumber} value={it.controlNumber}>{it.controlNumber} — {it.name}</option>)}
              </select>
            </Field>
            <Field label="Qty"><input type="number" step="0.01" className={`${inpCls} w-24`} data-testid="invoice-line-qty" value={lineDraft.qty} onChange={(e) => setLineDraft((d) => ({ ...d, qty: e.target.value }))} /></Field>
            <Field label="Unit"><select className={inpCls} value={lineDraft.unit} onChange={(e) => setLineDraft((d) => ({ ...d, unit: e.target.value }))}>{PURCHASE_UNITS.map((u) => <option key={u} value={u}>{u}</option>)}</select></Field>
            <Field label="Unit Cost ($)"><input type="number" step="0.01" className={`${inpCls} w-24`} data-testid="invoice-line-cost" value={lineDraft.unitCost} onChange={(e) => setLineDraft((d) => ({ ...d, unitCost: e.target.value }))} /></Field>
            <button className={btnGhost} onClick={addLine} data-testid="invoice-add-line"><Plus size={14} /> Add Line</button>
          </div>
          {lines.length > 0 && (
            <table className="ops-table mb-3.5">
              <thead><tr><th>Item</th><th>Qty</th><th>Unit</th><th>Unit Cost</th><th>Extended</th><th></th></tr></thead>
              <tbody>
                {lines.map((l, i) => (
                  <tr key={i}><td>{l.controlNumber} — {l.itemName}</td><td className="num">{l.qty}</td><td>{l.unit}</td><td className="num">{fmtMoney(l.unitCost)}</td><td className="num">{fmtMoney(l.qty * l.unitCost)}</td>
                    <td><button aria-label={`Remove invoice line for ${l.itemName}`} className="text-red-400 hover:text-red-300" onClick={() => removeLine(i)}><Trash2 size={13} /></button></td></tr>
                ))}
              </tbody>
            </table>
          )}
          <button className={btnAcc} onClick={saveInvoice} disabled={lines.length === 0 || !header.invoiceNumber.trim()} data-testid="save-invoice-button"><Save size={15} /> Save Invoice</button>
        </div>
      )}

      {mode === "other" && (
        <div className={`${cardCls} p-5 mb-6`}>
          <SectionLabel>Invoice Header</SectionLabel>
          <div className="grid gap-3 mb-4" style={{ gridTemplateColumns: "repeat(auto-fit, minmax(150px, 1fr))" }}>
            <Field label="Invoice Date"><input type="date" className={inpCls} value={header.invoiceDate} onChange={(e) => setHeader((h) => ({ ...h, invoiceDate: e.target.value }))} /></Field>
            <Field label="Invoice #"><input className={inpCls} value={header.invoiceNumber} onChange={(e) => setHeader((h) => ({ ...h, invoiceNumber: e.target.value }))} placeholder="e.g. INV-100234" /></Field>
            <Field label="Vendor"><select className={inpCls} value={header.vendor} onChange={(e) => setHeader((h) => ({ ...h, vendor: e.target.value }))}>{VENDORS.map((v) => <option key={v} value={v}>{v}</option>)}</select></Field>
          </div>
          <SectionLabel>Upload CSV</SectionLabel>
          <input ref={fileRef} type="file" accept=".csv,text/csv" onChange={onOtherFile} className="mb-3.5 text-sm text-slate-400 file:mr-3 file:rounded-lg file:border file:border-[#334155] file:bg-[#1E293B] file:px-3 file:py-1.5 file:text-slate-200 file:text-xs file:font-semibold" data-testid="invoice-other-file" />
          {csvHeaders.length > 0 && (
            <>
              <div className="grid gap-3 mb-3.5" style={{ gridTemplateColumns: "repeat(auto-fit, minmax(150px, 1fr))" }}>
                {[["item", "Item Column (control # or name)"], ["qty", "Qty Column"], ["unit", "Unit Column (optional)"], ["cost", "Unit Cost Column"]].map(([k, label]) => (
                  <Field key={k} label={label}>
                    <select className={inpCls} value={mapping[k]} onChange={(e) => setMapping((m) => ({ ...m, [k]: e.target.value }))}>
                      <option value="">{k === "unit" ? "— none —" : "— select —"}</option>
                      {csvHeaders.map((h) => <option key={h} value={h}>{h}</option>)}
                    </select>
                  </Field>
                ))}
              </div>
              {csvPreview.length > 0 && (
                <>
                  <SectionLabel>Preview ({csvPreview.filter((r) => r.match).length} matched of {csvPreview.length})</SectionLabel>
                  <table className="ops-table mb-3.5">
                    <thead><tr><th>CSV Value</th><th>Matched Item</th><th>Qty</th><th>Unit Cost</th></tr></thead>
                    <tbody>
                      {csvPreview.slice(0, 50).map((r, i) => (
                        <tr key={i} style={{ background: r.match ? "transparent" : "rgba(239,68,68,0.08)" }}>
                          <td>{r.raw}</td>
                          <td>{r.match ? `${r.match.controlNumber} — ${r.match.name}` : <span className="text-red-400">No match — will be skipped</span>}</td>
                          <td className="num">{r.qty}</td><td className="num">{fmtMoney(r.unitCost)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                  <button className={btnAcc} onClick={commitCSV} disabled={!csvPreview.some((r) => r.match)} data-testid="import-csv-button">
                    <Save size={15} /> Import {csvPreview.filter((r) => r.match).length} Matched Line{csvPreview.filter((r) => r.match).length !== 1 ? "s" : ""}
                  </button>
                </>
              )}
            </>
          )}
        </div>
      )}

      <SectionLabel>Recent Purchases ({purchases.length} total)</SectionLabel>
      {purchases.length === 0 ? <EmptyState text="No purchases logged yet." /> : (
        <div className={`${cardCls} overflow-hidden`}>
          <div className="overflow-x-auto">
            <table className="ops-table">
              <thead><tr><th>Date</th><th>Invoice #</th><th>Vendor</th><th>Item</th><th>Qty</th><th>Ext. Cost</th></tr></thead>
              <tbody>
                {[...purchases].sort((a, b) => b.invoiceDate.localeCompare(a.invoiceDate)).slice(0, 25).map((p) => (
                  <tr key={p.id}><td>{fmtDate(p.invoiceDate)}</td><td>{p.invoiceNumber}</td><td>{p.vendor}</td><td>{p.controlNumber} — {p.itemName}</td><td className="num">{p.qty} {p.unit}</td><td className="num">{fmtMoney(p.extendedCost)}</td></tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}
