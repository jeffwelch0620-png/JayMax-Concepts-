import React, { useEffect, useMemo, useState } from "react";
import { Check, X, Send, PackageCheck, Trash2, RotateCcw, ClipboardList, ShieldCheck, Mail, AlertTriangle, FileText } from "lucide-react";
import { fmtMoney, fmtDate, num } from "../lib/calc";
import * as api from "../lib/api";
import { NativeOrderReceiving } from "./NativeOrderReceiving";
import { NativeOrderWorkflow } from "./NativeOrderWorkflow";
import { PageTitle, EmptyState, Pill, cardCls, inpCls, btnAcc, btnGhost, btnDanger } from "./common";

const STATUS_META = {
  draft: { label: "Draft", color: "#94A3B8", bg: "#1E293B" },
  pending: { label: "Pending Approval", color: "#F59E0B", bg: "rgba(245,158,11,0.12)" },
  approved: { label: "Approved", color: "#10B981", bg: "rgba(16,185,129,0.12)" },
  sent: { label: "Sent to Supplier", color: "#38BDF8", bg: "rgba(56,189,248,0.12)" },
  received: { label: "Received", color: "#A78BFA", bg: "rgba(167,139,250,0.12)" },
  receiving: { label: "Partially received", color: "#38BDF8", bg: "rgba(56,189,248,0.12)" },
  rejected: { label: "Rejected", color: "#EF4444", bg: "rgba(239,68,68,0.12)" },
};
const FILTERS = ["all", "draft", "pending", "approved", "sent", "receiving", "received", "rejected"];

function StatusPill({ status }) {
  const m = STATUS_META[status] || STATUS_META.draft;
  return <Pill testId={`po-status-${status}`} color={m.color} bg={m.bg}>{m.label}</Pill>;
}

export function PurchaseOrdersTab({ rid, showToast, onInventoryChange, focusOrder }) {
  const [orders, setOrders] = useState([]);
  const [contacts, setContacts] = useState({});
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState("all");
  const [role, setRole] = useState("manager");
  const [person, setPerson] = useState("");
  const [receiving, setReceiving] = useState(null); // {oid, po, lines:{cn:qty}, invoiceNumber}
  const [rejecting, setRejecting] = useState(null); // {oid, reason}
  const [emailing, setEmailing] = useState(null); // {oid, email}
  const [reorderVendor, setReorderVendor] = useState("");
  const [highlightId, setHighlightId] = useState(null);

  async function refresh() {
    setLoading(true);
    try {
      const [os, vc] = await Promise.all([api.listOrders(rid), api.listVendorContacts(rid).catch(() => [])]);
      setOrders(os);
      const map = {}; (vc || []).forEach((c) => (map[c.vendor] = c.orderEmail));
      setContacts(map);
    } catch { showToast("Couldn't load purchase orders"); }
    setLoading(false);
  }
  useEffect(() => { refresh(); /* eslint-disable-next-line */ }, [rid]);

  useEffect(() => {
    if (!focusOrder?.id) return;
    setFilter("all");
    setHighlightId(focusOrder.id);
    const t = setTimeout(() => {
      const el = document.querySelector(`[data-testid="po-card-${focusOrder.id}"]`);
      if (el) el.scrollIntoView({ behavior: "smooth", block: "center" });
    }, 350);
    const clear = setTimeout(() => setHighlightId(null), 4000);
    return () => { clearTimeout(t); clearTimeout(clear); };
  }, [focusOrder, loading]);

  const shown = useMemo(() => filter === "all" ? orders : orders.filter((o) => o.status === filter), [orders, filter]);
  const counts = useMemo(() => { const c = {}; orders.forEach((o) => { c[o.status] = (c[o.status] || 0) + 1; }); return c; }, [orders]);
  const vendors = useMemo(() => [...new Set(orders.map((o) => o.vendor))].sort(), [orders]);

  function upsert(po) { setOrders((prev) => prev.map((o) => o.id === po.id ? po : o)); }

  async function act(fn, oid, ...args) {
    try { const po = await fn(rid, oid, ...args); upsert(po); return po; }
    catch (e) { showToast(e?.response?.data?.detail || "Action failed"); return null; }
  }

  async function doSubmit(oid) { if (await act(api.submitOrder, oid, person)) showToast("Submitted for owner approval"); }
  async function doApprove(oid) { if (await act(api.approveOrder, oid, person)) showToast("Order approved"); }
  async function doReopen(oid) { if (await act(api.reopenOrder, oid, person)) showToast("Order reopened as draft"); }
  async function doSend(oid) { if (await act(api.sendOrder, oid, person)) showToast("Marked as sent to supplier"); }
  async function doDelete(oid) {
    if (!window.confirm("Delete this order? This cannot be undone.")) return;
    try { await api.deleteOrder(rid, oid); setOrders((p) => p.filter((o) => o.id !== oid)); showToast("Order deleted"); }
    catch (e) { showToast(e?.response?.data?.detail || "Delete failed"); }
  }
  async function confirmReject() {
    if (await act(api.rejectOrder, rejecting.oid, person, rejecting.reason)) showToast("Order rejected");
    setRejecting(null);
  }
  async function confirmReceive() {
    if (api.nativePurchasesEnabled) { showToast("Use the invoice-linked delivery review below."); return; }
    const lines = Object.entries(receiving.lines).map(([controlNumber, receivedQty]) => ({ controlNumber, receivedQty: Number(receivedQty) || 0 }));
    const po = await act(api.receiveOrder, receiving.oid, person, lines, (receiving.invoiceNumber || "").trim());
    if (po) {
      const flagged = po.receiptMatch?.flaggedCount || 0;
      showToast(po.receiptMatch ? (po.receiptMatch.invoiceFound ? (flagged ? `Received — ${flagged} invoice discrepanc${flagged === 1 ? "y" : "ies"} flagged` : "Received — invoice matches, no discrepancies") : `Received — invoice ${receiving.invoiceNumber} not found`) : "Received — inventory updated");
      onInventoryChange?.();
    }
    setReceiving(null);
  }
  async function confirmEmail() {
    const po = await act(api.emailOrder, emailing.oid, (emailing.email || "").trim(), person);
    if (po) {
      showToast(`Order emailed to ${po.emailedTo}`);
      if (po.vendor) setContacts((c) => ({ ...c, [po.vendor]: po.emailedTo }));
    }
    setEmailing(null);
  }
  async function doReorder() {
    if (!reorderVendor) return;
    try { await api.reorderLast(rid, reorderVendor, person); showToast(`Draft created from last ${reorderVendor} order`); setFilter("draft"); refresh(); }
    catch (e) { showToast(e?.response?.data?.detail || "No previous order to reorder"); }
  }
  async function applyPrices(po) {
    const lines = (po.receiptMatch?.lines || [])
      .filter((l) => l.onInvoice && l.flagged && Math.abs(l.priceDiff || 0) > 0.001 && l.invoiceUnitCost > 0)
      .map((l) => ({ controlNumber: l.controlNumber, unitCost: l.invoiceUnitCost }));
    if (!lines.length) { showToast("No price differences to apply"); return; }
    if (!window.confirm(`Update the saved vendor price for ${lines.length} item${lines.length === 1 ? "" : "s"} to the invoice cost? This changes the master item price used for future order estimates.`)) return;
    try {
      const res = await api.applyOrderPrices(rid, po.id, lines);
      showToast(`Updated ${res.updated} saved price${res.updated === 1 ? "" : "s"} to invoice cost`);
      onInventoryChange?.();
    } catch (e) { showToast(e?.response?.data?.detail || "Couldn't update prices"); }
  }

  function openReceive(po) { const lines = {}; po.lines.forEach((l) => (lines[l.controlNumber] = l.qty)); setReceiving({ oid: po.id, po, lines, invoiceNumber: "" }); }
  function openEmail(po) { setEmailing({ oid: po.id, email: contacts[po.vendor] || "" }); }

  if (api.orderWorkflowEnabled) return <NativeOrderWorkflow key={rid} rid={rid} showToast={showToast} onInventoryChange={onInventoryChange} />;
  return (
    <div className="fade-slide-in" data-testid="purchase-orders-tab">
      <PageTitle right={
        <div className="flex items-center gap-2 flex-wrap">
          <input className={`${inpCls} w-40`} placeholder="Your name" value={person} onChange={(e) => setPerson(e.target.value)} data-testid="po-person-input" />
          <div className="flex rounded-lg overflow-hidden border border-[#334155]" data-testid="po-role-toggle">
            {["manager", "owner"].map((r) => (
              <button key={r} onClick={() => setRole(r)} data-testid={`po-role-${r}`}
                className={`px-3 py-2 text-xs font-bold transition ${role === r ? "text-[#0B0F17]" : "text-slate-400 bg-[#161F30] hover:text-white"}`}
                style={role === r ? { background: "var(--acc)" } : {}}>
                {r === "owner" ? <ShieldCheck size={13} className="inline mr-1" /> : <ClipboardList size={13} className="inline mr-1" />}
                {r === "owner" ? "Owner" : "Manager"}
              </button>
            ))}
          </div>
        </div>
      }>Purchase Orders</PageTitle>

      <div className="text-xs text-slate-500 -mt-3 mb-4">
        {role === "owner"
          ? "Owner view — review and approve or reject pending orders submitted by managers."
          : "Manager view — build orders in the Order Generator, submit for owner approval, email approved orders to suppliers, and receive deliveries into inventory."}
      </div>

      {vendors.length > 0 && (
        <div className={`${cardCls} p-3 mb-4 flex items-center gap-2 flex-wrap`} data-testid="po-reorder-bar">
          <span className="text-xs font-bold text-slate-400 flex items-center gap-1.5"><RotateCcw size={13} /> Reorder last order for</span>
          <select className={`${inpCls} w-48`} value={reorderVendor} onChange={(e) => setReorderVendor(e.target.value)} data-testid="po-reorder-vendor">
            <option value="">Select a vendor…</option>
            {vendors.map((v) => <option key={v} value={v}>{v}</option>)}
          </select>
          <button className={btnGhost} onClick={doReorder} disabled={!reorderVendor} data-testid="po-reorder-button">Create Draft</button>
        </div>
      )}

      <div className="flex gap-1.5 mb-4 flex-wrap" data-testid="po-filter-bar">
        {FILTERS.map((s) => (
          <button key={s} onClick={() => setFilter(s)} data-testid={`po-filter-${s}`}
            className={`rounded-full px-3 py-1.5 text-xs font-bold border transition ${filter === s ? "text-[#0B0F17] border-transparent" : "text-slate-400 bg-[#161F30] border-[#28354A] hover:text-white"}`}
            style={filter === s ? { background: "var(--acc)" } : {}}>
            {s === "all" ? "All" : STATUS_META[s].label}{s !== "all" && counts[s] ? ` (${counts[s]})` : ""}
          </button>
        ))}
      </div>

      {loading ? <div className="text-slate-500 text-sm p-8 text-center" data-testid="po-loading">Loading orders…</div>
        : shown.length === 0 ? <EmptyState text={filter === "all" ? "No purchase orders yet. Create one from the Order Generator." : `No ${STATUS_META[filter]?.label?.toLowerCase()} orders.`} />
        : (
        <div className="flex flex-col gap-3" data-testid="po-list">
          {shown.map((po) => {
            const isSelfApproval = !!person.trim() && !!po.createdBy && person.trim().toLowerCase() === po.createdBy.trim().toLowerCase();
            const canReview = role === "owner" && po.status === "pending" && !!person.trim();
            const canApprove = canReview && !isSelfApproval;
            const isReceiving = receiving?.oid === po.id;
            const isRejecting = rejecting?.oid === po.id;
            const isEmailing = emailing?.oid === po.id;
            const rm = po.receiptMatch?.native ? null : po.receiptMatch;
            return (
              <div key={po.id} className={`${cardCls} p-4 transition ${highlightId === po.id ? "ring-2 ring-[var(--acc)]" : ""}`} data-testid={`po-card-${po.id}`}>
                <div className="flex items-start justify-between gap-3 flex-wrap">
                  <div>
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className="font-display font-bold text-slate-100">{po.vendor}</span>
                      <StatusPill status={po.status} />
                      {po.emailedTo && <Pill testId={`po-emailed-${po.id}`} color="#38BDF8" bg="rgba(56,189,248,0.12)"><Mail size={10} className="inline -mt-0.5" /> {po.emailedTo}</Pill>}
                    </div>
                    <div className="text-[11px] text-slate-500 mt-0.5">
                      {po.lines.length} line{po.lines.length !== 1 ? "s" : ""} · {fmtMoney(po.total)} · created {fmtDate((po.createdAt || "").slice(0, 10))}{po.createdBy ? ` by ${po.createdBy}` : ""}
                    </div>
                  </div>
                  <div className="flex gap-1.5 flex-wrap items-center">
                    <button className={btnGhost} data-testid={`po-pdf-${po.id}`} onClick={() => window.open(api.orderPdfUrl(rid, po.id), "_blank", "noopener,noreferrer")}><FileText size={13} /> PDF</button>
                    {po.status === "draft" && <>
                      <button className={btnAcc} data-testid={`po-submit-${po.id}`} onClick={() => doSubmit(po.id)}><Send size={13} /> Submit for Approval</button>
                      <button aria-label={`Delete order for ${po.vendor}`} className={btnDanger} data-testid={`po-delete-${po.id}`} onClick={() => doDelete(po.id)}><Trash2 size={13} /></button>
                    </>}
                    {po.status === "pending" && (canReview ? <>
                      {canApprove
                        ? <button className={btnAcc} data-testid={`po-approve-${po.id}`} onClick={() => doApprove(po.id)}><Check size={13} /> Approve</button>
                        : <Pill color="#F59E0B" bg="rgba(245,158,11,0.12)">You created this order — a different owner must approve it</Pill>}
                      <button className={btnDanger} data-testid={`po-reject-${po.id}`} onClick={() => setRejecting({ oid: po.id, reason: "" })}><X size={13} /> Reject</button>
                    </> : <Pill color="#F59E0B" bg="rgba(245,158,11,0.12)">{role === "owner" ? "Enter your name to review" : "Awaiting owner approval"}</Pill>)}
                    {po.status === "approved" && <>
                      <button className={btnAcc} data-testid={`po-email-${po.id}`} onClick={() => openEmail(po)}><Mail size={13} /> Email Supplier</button>
                      <button className={btnGhost} data-testid={`po-send-${po.id}`} onClick={() => doSend(po.id)}><Send size={13} /> Mark Sent</button>
                    </>}
                    {(po.status === "sent" || (api.nativePurchasesEnabled && po.status === "receiving")) && <>
                      <button className={btnGhost} data-testid={`po-email-${po.id}`} onClick={() => openEmail(po)}><Mail size={13} /> Email Again</button>
                      <button className={btnAcc} data-testid={`po-receive-${po.id}`} onClick={() => openReceive(po)}><PackageCheck size={13} /> Receive Delivery</button>
                    </>}
                    {po.status === "rejected" && <>
                      <button className={btnGhost} data-testid={`po-reopen-${po.id}`} onClick={() => doReopen(po.id)}><RotateCcw size={13} /> Reopen</button>
                      <button aria-label={`Delete order for ${po.vendor}`} className={btnDanger} data-testid={`po-delete-${po.id}`} onClick={() => doDelete(po.id)}><Trash2 size={13} /></button>
                    </>}
                  </div>
                </div>

                {po.status === "rejected" && po.rejectedReason && (
                  <div className="mt-2 text-xs text-red-400 bg-red-500/10 border border-red-500/20 rounded-lg px-3 py-2" data-testid={`po-reject-reason-${po.id}`}>
                    Rejected: {po.rejectedReason}
                  </div>
                )}

                <div className="mt-3 overflow-x-auto">
                  <table className="ops-table">
                    <thead><tr><th>Item</th><th>SKU</th><th>Qty</th><th>Unit Cost</th><th>Line Total</th>{po.status === "received" && !api.nativePurchasesEnabled && <th>Received</th>}</tr></thead>
                    <tbody>
                      {po.lines.map((l) => (
                        <tr key={l.controlNumber}>
                          <td className="text-slate-200"><span className="font-bold" style={{ color: "var(--acc)" }}>{l.controlNumber}</span> {l.name}</td>
                          <td className="text-slate-400">{l.vendorSku || "—"}</td>
                          <td className="num">{num(l.qty, 1)} {l.purchaseUnit}</td>
                          <td className="num">{fmtMoney(l.unitCost)}</td>
                          <td className="num font-semibold">{fmtMoney(l.lineTotal)}</td>
                          {po.status === "received" && !api.nativePurchasesEnabled && <td className="num" style={{ color: (l.receivedQty !== l.qty) ? "#F59E0B" : "#10B981" }}>{num(l.receivedQty, 1)}</td>}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>

                {rm && (
                  <div className={`mt-3 rounded-lg border p-3 ${rm.invoiceFound ? (rm.flaggedCount ? "border-amber-500/40 bg-amber-500/5" : "border-emerald-500/40 bg-emerald-500/5") : "border-red-500/40 bg-red-500/5"}`} data-testid={`po-receipt-match-${po.id}`}>
                    <div className="text-xs font-bold mb-2 flex items-center gap-1.5" style={{ color: rm.invoiceFound ? (rm.flaggedCount ? "#F59E0B" : "#10B981") : "#EF4444" }}>
                      <AlertTriangle size={13} /> Invoice {rm.invoiceNumber} — {rm.invoiceFound ? (rm.flaggedCount ? `${rm.flaggedCount} discrepanc${rm.flaggedCount === 1 ? "y" : "ies"} vs Invoice Master` : "matches Invoice Master, no discrepancies") : "not found in Invoice Master"}
                    </div>
                    {!api.nativePurchasesEnabled && rm.invoiceFound && rm.lines.some((l) => l.onInvoice && l.flagged && Math.abs(l.priceDiff || 0) > 0.001 && l.invoiceUnitCost > 0) && (
                      <div className="mb-2">
                        <button className={btnAcc} data-testid={`po-apply-prices-${po.id}`} onClick={() => applyPrices(po)}>Update saved prices to invoice</button>
                      </div>
                    )}
                    {rm.invoiceFound && (
                      <div className="overflow-x-auto">
                        <table className="ops-table">
                          <thead><tr><th>Item</th><th>Received</th><th>Invoice Qty</th><th>PO Cost</th><th>Invoice Cost</th><th>Δ</th></tr></thead>
                          <tbody>
                            {rm.lines.map((l) => (
                              <tr key={l.controlNumber} style={l.flagged ? { background: "rgba(245,158,11,0.06)" } : {}}>
                                <td className="text-slate-200"><span className="font-bold" style={{ color: "var(--acc)" }}>{l.controlNumber}</span> {l.name}</td>
                                <td className="num">{num(l.receivedQty, 1)}</td>
                                <td className="num">{l.onInvoice ? num(l.invoiceQty, 1) : "—"}</td>
                                <td className="num">{fmtMoney(l.poUnitCost)}</td>
                                <td className="num">{l.onInvoice ? fmtMoney(l.invoiceUnitCost) : "—"}</td>
                                <td className="num" style={{ color: l.flagged ? "#F59E0B" : "#10B981" }}>
                                  {!l.onInvoice ? "not on invoice" : (l.flagged ? [l.qtyDiff ? `qty ${l.qtyDiff > 0 ? "+" : ""}${num(l.qtyDiff, 1)}` : "", l.priceDiff ? `price ${l.priceDiff > 0 ? "+" : ""}${fmtMoney(l.priceDiff)}` : ""].filter(Boolean).join(", ") : "ok")}
                                </td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    )}
                  </div>
                )}

                {isRejecting && (
                  <div className="mt-3 flex gap-2 items-center flex-wrap bg-[#0F1626] border border-red-500/30 rounded-lg p-3" data-testid={`po-reject-form-${po.id}`}>
                    <input className={`${inpCls} flex-1 min-w-[200px]`} placeholder="Reason for rejection" value={rejecting.reason} onChange={(e) => setRejecting((s) => ({ ...s, reason: e.target.value }))} data-testid={`po-reject-input-${po.id}`} />
                    <button className={btnDanger} data-testid={`po-reject-confirm-${po.id}`} onClick={confirmReject}>Confirm Reject</button>
                    <button className={btnGhost} onClick={() => setRejecting(null)}>Cancel</button>
                  </div>
                )}

                {isEmailing && (
                  <div className="mt-3 flex gap-2 items-center flex-wrap bg-[#0F1626] border border-sky-500/30 rounded-lg p-3" data-testid={`po-email-form-${po.id}`}>
                    <span className="text-xs font-bold text-slate-300">Send to supplier:</span>
                    <input type="email" className={`${inpCls} flex-1 min-w-[220px]`} placeholder="supplier@vendor.com" value={emailing.email} onChange={(e) => setEmailing((s) => ({ ...s, email: e.target.value }))} data-testid={`po-email-input-${po.id}`} />
                    <button className={btnAcc} data-testid={`po-email-send-${po.id}`} onClick={confirmEmail} disabled={!emailing.email.trim()}><Mail size={13} /> Send Email</button>
                    <button className={btnGhost} onClick={() => setEmailing(null)}>Cancel</button>
                  </div>
                )}

                {api.nativePurchasesEnabled && (isReceiving || po.receiptMatch?.native) && <NativeOrderReceiving key={`${po.id}:${po.receiptMatch?.receiptId || "new"}`} restaurantId={rid} orderRef={po.id} onSaved={async result => { setReceiving(null); showToast(result?.reconciliation ? "Order comparison reconciled." : "Delivery linked to recorded purchase."); await refresh(); }} />}
                {isReceiving && !api.nativePurchasesEnabled && (
                  <div className="mt-3 bg-[#0F1626] border border-sky-500/30 rounded-lg p-3" data-testid={`po-receive-form-${po.id}`}>
                    <div className="flex items-center gap-2 flex-wrap mb-3">
                      <span className="text-xs font-bold text-slate-300">Invoice # (optional — matches against Invoice Master):</span>
                      <input className={`${inpCls} w-40`} placeholder="e.g. INV-77001" value={receiving.invoiceNumber} onChange={(e) => setReceiving((s) => ({ ...s, invoiceNumber: e.target.value }))} data-testid={`po-receive-invoice-${po.id}`} />
                    </div>
                    <div className="text-xs font-bold text-slate-300 mb-2">Confirm received quantities (adds to inventory on-hand)</div>
                    <div className="flex flex-col gap-2 mb-3">
                      {po.lines.map((l) => (
                        <div key={l.controlNumber} className="flex items-center gap-2 flex-wrap">
                          <span className="text-sm text-slate-300 flex-1 min-w-[160px]"><span className="font-bold" style={{ color: "var(--acc)" }}>{l.controlNumber}</span> {l.name}</span>
                          <span className="text-xs text-slate-500">ordered {num(l.qty, 1)}</span>
                          <input type="number" step="0.1" min="0" className={`${inpCls} w-24`} value={receiving.lines[l.controlNumber]} onChange={(e) => setReceiving((s) => ({ ...s, lines: { ...s.lines, [l.controlNumber]: e.target.value } }))} data-testid={`po-receive-qty-${po.id}-${l.controlNumber}`} />
                          <span className="text-xs text-slate-500">{l.purchaseUnit}</span>
                        </div>
                      ))}
                    </div>
                    <div className="flex gap-2">
                      <button className={btnAcc} data-testid={`po-receive-confirm-${po.id}`} onClick={confirmReceive}><PackageCheck size={13} /> Confirm Receipt</button>
                      <button className={btnGhost} onClick={() => setReceiving(null)}>Cancel</button>
                    </div>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
