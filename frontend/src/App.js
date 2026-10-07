import React, { useEffect, useMemo, useRef, useState } from "react";
import { Toaster, toast } from "sonner";
import {
  LayoutDashboard, ClipboardList, ClipboardCheck, Settings, FileText, ShoppingCart, BookOpen, ChefHat,
  Printer, Activity, AlertTriangle, TrendingUp, Building2, Sparkles, Boxes, CalendarClock, Users,
} from "lucide-react";
import { RESTAURANTS, OWNER, isOrderEnabled, statusOf, downloadJSON, todayISO, workweekRange } from "./lib/calc";
import * as api from "./lib/api";
import { useStoreState } from "./lib/useStoreState";
import { DashboardTab } from "./components/DashboardTab";
import { CountsTab } from "./components/CountsTab";
import { SetupTab } from "./components/SetupTab";
import { InvoicesTab } from "./components/InvoicesTab";
import { ActualInventoryTab } from "./components/ActualInventoryTab";
import { BackupControls } from "./components/BackupControls";
import { OrderTab } from "./components/OrderTab";
import { PurchaseOrdersTab } from "./components/PurchaseOrdersTab";
import { MenuTab } from "./components/MenuTab";
import { CostingTab } from "./components/CostingTab";
import { RecipeCardsTab } from "./components/RecipeCardsTab";
import { SalesTrackingTab } from "./components/SalesTrackingTab";
import { AdjustmentsTab } from "./components/AdjustmentsTab";
import { HistoryTab } from "./components/HistoryTab";
import { NativePurchaseHistory } from "./components/NativePurchaseHistory";
import { PrepTab } from "./components/PrepTab";
import { SchedulingTab } from "./components/SchedulingTab";
import { StaffTab } from "./components/StaffTab";
import { OwnerDashboard } from "./components/OwnerDashboard";
import { AiAssistant } from "./components/AiAssistant";
import { StaffSheet } from "./components/StaffSheet";
import { Login } from "./components/Login";

const TABS = [
  { id: "dashboard", label: "Dashboard", icon: LayoutDashboard },
  { id: "prep", label: "Prep", icon: ChefHat },
  { id: "counts", label: "Enter Counts", icon: ClipboardList },
  { id: "setup", label: "Item Setup", icon: Settings },
  { id: "invoices", label: "Invoice Master", icon: FileText },
  { id: "order", label: "Order Generator", icon: ShoppingCart },
  { id: "purchaseOrders", label: "Purchase Orders", icon: ClipboardCheck },
  { id: "menu", label: "Menu", icon: BookOpen },
  { id: "costing", label: "Menu Costing", icon: Boxes },
  { id: "recipeCards", label: "Recipe Cards", icon: Printer },
  { id: "sales", label: "Sales Tracking", icon: Activity },
  { id: "adjustments", label: "Waste / Adjustments", icon: AlertTriangle },
  { id: "history", label: "Price History", icon: TrendingUp },
  { id: "scheduling", label: "Operations", icon: CalendarClock },
  { id: "team", label: "Staff", icon: Users },
];

const DEFAULT_PERIOD = (() => { const w = workweekRange(); return { periodStart: w.start, periodEnd: w.end, dishSales: {}, itemCounts: {} }; })();
const EMPTY_STATE = { items: [], purchases: [], dishes: [], adjustments: [], reportingPeriods: [], prepStock: [], prepLogs: [], salesPeriod: DEFAULT_PERIOD, areas: [] };

export default function App() {
  const [session, setSession] = useState(() => api.currentSession());
  const [loginNotice, setLoginNotice] = useState("");
  useEffect(() => {
    const onExpired = () => { setSession(null); setLoginNotice("Your session expired. Please sign in again."); };
    window.addEventListener(api.SESSION_EXPIRED_EVENT, onExpired);
    return () => window.removeEventListener(api.SESSION_EXPIRED_EVENT, onExpired);
  }, []);
  const [loc, setLoc] = useState(() => api.currentSession()?.user?.role === "owner" ? "owner" : (api.currentSession()?.user?.locations || [])[0] || "berts");
  const [activeTab, setActiveTab] = useState("dashboard");
  const [historyFocusCN, setHistoryFocusCN] = useState(null);
  const [dashboardFlaggedOnly, setDashboardFlaggedOnly] = useState(false);
  const [costingFocus, setCostingFocus] = useState(null);
  const [aiOpen, setAiOpen] = useState(false);
  const [aiRid, setAiRid] = useState(null);
  const [staffOpen, setStaffOpen] = useState(false);
  const [focusOrder, setFocusOrder] = useState(null);
  const backupRef = useRef(null);
  const pendingTabRef = useRef(null);
  const drafts = useRef(new Map());
  useEffect(() => { drafts.current.clear(); }, [session]);
  const store = useStoreState(loc, session, EMPTY_STATE, message => toast.error(message));
  const S = store.state;
  const isOwner = !!session && loc === "owner" && session.user.role === "owner";
  const current = isOwner ? OWNER : RESTAURANTS.find((r) => r.id === loc) || RESTAURANTS[0];
  const accessibleRestaurants = RESTAURANTS.filter((r) => session?.user?.role === "owner" || session?.user?.locations?.includes(r.id));
  const visibleTabs = session?.user?.role === "readonly"
    ? TABS.filter((t) => ["dashboard", "history"].includes(t.id))
    : session?.user?.role === "staff"
      ? TABS.filter((t) => ["dashboard", "prep", "counts"].includes(t.id))
      : TABS;

  useEffect(() => {
    setCostingFocus(null);
    setActiveTab(pendingTabRef.current || "dashboard");
    pendingTabRef.current = null;
  }, [loc, session]);

  const showToast = (msg) => { if (store.isCurrent()) toast.success(msg); };
  const showError = (msg) => { if (store.isCurrent()) toast.error(msg); };
  const persistItems = next => store.save("items", next);
  const persistPurchases = next => store.save("purchases", next);
  const persistDishes = next => store.save("dishes", next);
  const persistAdjustments = next => store.save("adjustments", next);
  const persistReportingPeriods = next => store.save("reportingPeriods", next);
  const persistAreas = next => store.save("areas", next);
  const persistSalesPeriod = (next, revision) => store.save("salesPeriod", next, revision);
  function applyPrepResult(res) {
    store.apply(p => ({ ...p, items: res.items ?? p.items, prepStock: res.prepStock ?? p.prepStock,
      prepLogs: res.log ? [res.log, ...(p.prepLogs || [])] : p.prepLogs }));
  }

  function openCosting(dishId) { setCostingFocus({ id: dishId, nonce: Date.now() + Math.random() }); setActiveTab("costing"); }
  function openOrder(rid, orderId) { pendingTabRef.current = "purchaseOrders"; setFocusOrder({ id: orderId, nonce: Date.now() + Math.random() }); if (rid === loc) { setActiveTab("purchaseOrders"); } else { setLoc(rid); } }

  const alertCount = useMemo(() => !S || api.actualInventoryEnabled ? 0 : S.items.filter((it) => isOrderEnabled(it) && statusOf(it).key !== "ok").length, [S]);

  function backupAll() {
    if (api.nativePurchasesEnabled) { toast.error("App files cannot provide a complete inventory backup. Complete recovery is awaiting setup."); return; }
    if (!S) return;
    downloadJSON(`${current.short.replace(/\W+/g, "")}_backup_${todayISO()}.json`, {
      exportedAt: new Date().toISOString(), restaurant: loc,
      items: S.items, purchases: S.purchases, dishes: S.dishes, areas: S.areas, salesPeriod: S.salesPeriod, adjustments: S.adjustments, reportingPeriods: S.reportingPeriods,
    });
    showToast("Backup downloaded");
  }

  function restoreBackup(e) {
    if (api.nativePurchasesEnabled) { toast.error("App files omit inventory history and cannot restore this inventory mode."); return; }
    const file = e.target.files?.[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = async () => {
      if (!store.isCurrent()) return;
      try {
        const data = JSON.parse(String(reader.result || "{}"));
        if (!Array.isArray(data.items) || !Array.isArray(data.purchases)) { toast.error("That file doesn't look like a backup"); return; }
        const ok = window.confirm(`Restoring will replace ALL current data for ${current.name}. This can't be undone. Continue?`);
        if (!ok) return;
        // persistX()/persistSalesPeriod() each swallow their own network errors (showing
        // a per-collection toast) and resolve to a falsy value on failure — so `await`
        // alone never surfaces a partial failure here. Track which sections actually
        // saved so the final message reflects what really happened, instead of always
        // claiming success.
        const failed = [];
        const step = async (label, fn) => { if (!store.isCurrent() || !(await fn())) failed.push(label); };
        await step("items", () => persistItems(data.items || []));
        await step("purchases", () => persistPurchases(data.purchases || []));
        await step("dishes", () => persistDishes(data.dishes || []));
        if (data.areas) await step("areas", () => persistAreas(data.areas));
        if (data.salesPeriod) await step("sales period", () => persistSalesPeriod(data.salesPeriod));
        await step("adjustments", () => persistAdjustments(data.adjustments || []));
        await step("reporting periods", () => persistReportingPeriods(data.reportingPeriods || []));
        if (!store.isCurrent()) return;
        if (failed.length) {
          toast.error(`Restore finished with problems — ${failed.join(", ")} did not save. Re-check those sections and try again.`);
        } else {
          showToast("Backup restored");
        }
      } catch (err) { if (store.isCurrent()) toast.error("Couldn't read that file"); }
    };
    reader.readAsText(file);
    if (backupRef.current) backupRef.current.value = "";
  }

  if (!session) {
    return staffOpen
      ? <StaffSheet drafts={drafts.current} onClose={() => setStaffOpen(false)} onElevate={(sess) => { api.storeSession(sess); setSession(sess); setStaffOpen(false); }} />
      : <Login onLogin={(sess) => { setLoginNotice(""); setSession(sess); }} onOpenStaff={() => setStaffOpen(true)} notice={loginNotice} />;
  }
  return (
    <div className="min-h-screen bg-[#0B0F17] text-slate-100" style={{ "--acc": current.accent }}>
      <Toaster position="bottom-center" theme="dark" toastOptions={{ style: { background: "#161F30", border: "1px solid #28354A", color: "#F8FAFC" } }} />

      <header className="sticky top-0 z-40 bg-[#0B0F17]/90 backdrop-blur-md border-b border-[#28354A]" data-testid="app-header">
        <div className="max-w-[1280px] mx-auto px-4 sm:px-6 pt-4">
          <div className="flex justify-between items-center flex-wrap gap-3">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-xl flex items-center justify-center font-display font-extrabold text-lg text-[#0B0F17]" style={{ background: current.accent }}>
                {isOwner ? <Building2 size={20} /> : current.short[0]}
              </div>
              <div>
                <div className="font-display text-lg font-bold tracking-tight leading-tight" data-testid="header-title">{current.name}</div>
                <div className="text-[10px] uppercase tracking-[0.14em] text-slate-500 font-bold">
                  {isOwner ? "Group Overview · 3 Locations · ~$8M Annual Sales" : `${current.location ? current.location + " · " : ""}Inventory · Costing · Prep · Ordering`}
                </div>
              </div>
            </div>
            <div className="flex items-center gap-2 flex-wrap">
              {!isOwner && alertCount > 0 && (
                <button
                  onClick={() => { setDashboardFlaggedOnly(true); setActiveTab("dashboard"); }}
                  className="flex items-center gap-1.5 rounded-full px-3 py-1.5 text-xs font-semibold border border-amber-500/40 bg-amber-500/10 text-amber-300 hover:bg-amber-500/20 transition"
                  data-testid="alerts-badge"
                >
                  <AlertTriangle size={13} /> {alertCount} item{alertCount !== 1 ? "s" : ""} need attention
                </button>
              )}
              {!isOwner && (
                <>
                  <button onClick={store.refresh} data-testid="refresh-location-data" className="text-xs text-slate-300">Refresh saved data</button>
                  <BackupControls nativeMode={api.nativePurchasesEnabled} onBackup={backupAll} onRestore={() => backupRef.current?.click()} />
                  {!api.nativePurchasesEnabled && <input ref={backupRef} type="file" accept=".json,application/json" onChange={restoreBackup} className="hidden" />}
                </>
              )}
              <button
                onClick={() => setStaffOpen(true)}
                className="flex items-center gap-1.5 rounded-full px-3.5 py-1.5 text-xs font-bold border border-[#334155] bg-[#161F30] text-slate-300 hover:border-[var(--acc)] hover:text-white transition"
                data-testid="open-staff-sheet"
              >
                <ClipboardCheck size={13} /> Prep Sheet
              </button>
              <button
                onClick={() => setAiOpen(true)}
                className="flex items-center gap-1.5 rounded-full px-3.5 py-1.5 text-xs font-bold text-[#0B0F17] hover:brightness-110 transition"
                style={{ background: current.accent }}
                data-testid="open-ai-assistant"
              >
                <Sparkles size={13} /> Ask Sous
              </button>
            </div>
          </div>

          <div className="flex gap-1.5 mt-4 overflow-x-auto pb-1" data-testid="location-selector">
            {(session.user.role === "owner" ? [OWNER, ...RESTAURANTS] : accessibleRestaurants).map((r) => (
              <button
                key={r.id}
                onClick={() => setLoc(r.id)}
                data-testid={`location-tab-${r.id}`}
                className={`flex items-center gap-1.5 whitespace-nowrap rounded-full px-3.5 py-1.5 text-xs font-bold border transition ${loc === r.id ? "text-[#0B0F17]" : "text-slate-400 bg-[#161F30] border-[#28354A] hover:text-white"}`}
                style={loc === r.id ? { background: r.accent, borderColor: r.accent } : {}}
              >
                {r.id === "owner" && <Building2 size={12} />}
                {r.short}
              </button>
            ))}
          </div>
          <button onClick={() => { api.authLogout(); setSession(null); }} className="mt-2 text-xs text-slate-500 hover:text-white">Sign out ({session.user.email})</button>

          {!isOwner && (
            <nav className="flex gap-0.5 mt-2 overflow-x-auto" data-testid="main-nav">
              {visibleTabs.map((t) => {
                const Icon = t.icon;
                const active = activeTab === t.id;
                return (
                  <button
                    key={t.id}
                    onClick={() => setActiveTab(t.id)}
                    data-testid={`nav-tab-${t.id}`}
                    className={`flex items-center gap-1.5 whitespace-nowrap px-3 py-2.5 text-xs font-semibold border-b-2 transition ${active ? "text-white" : "text-slate-500 border-transparent hover:text-slate-300"}`}
                    style={active ? { borderBottomColor: current.accent } : {}}
                  >
                    <Icon size={13} />{t.label}
                  </button>
                );
              })}
            </nav>
          )}
        </div>
      </header>

      <main className="max-w-[1280px] mx-auto px-4 sm:px-6 py-6 pb-20">
        {isOwner ? (
          <OwnerDashboard onOpenLocation={(id) => setLoc(id)} onOpenOrder={openOrder} />
        ) : !S ? (
          <div className="text-slate-500 text-sm p-10 text-center" data-testid="loading-state">Loading {current.name}…</div>
        ) : (
          <>
            {activeTab === "dashboard" && (api.actualInventoryEnabled ? <ActualInventoryTab key={`${loc}:report`} restaurantId={loc} view="report" /> : api.nativePurchasesEnabled ? <p>Accounting reports are awaiting Actual Inventory setup and explicit physical count values. Purchases are reviewed in Invoice Master.</p> : <DashboardTab rid={loc} items={S.items} purchases={S.purchases} dishes={S.dishes} adjustments={S.adjustments} salesPeriod={S.salesPeriod} reportingPeriods={S.reportingPeriods} onOpenHistory={(cn) => { setHistoryFocusCN(cn); setActiveTab("history"); }} flaggedOnly={dashboardFlaggedOnly} setFlaggedOnly={setDashboardFlaggedOnly} />)}
            {activeTab === "prep" && <PrepTab showError={showError} drafts={drafts.current} key={loc} rid={loc} items={S.items} dishes={S.dishes} persistDishes={persistDishes} prepStock={S.prepStock} prepLogs={S.prepLogs} applyPrepResult={applyPrepResult} salesPeriod={S.salesPeriod} showToast={showToast} />}
            {activeTab === "counts" && (api.actualInventoryEnabled ? <ActualInventoryTab key={`${loc}:counts`} restaurantId={loc} /> : <CountsTab key={loc} rid={loc} items={S.items} onCountsApplied={(next) => store.apply(p => ({ ...p, items: next }))} showToast={showToast} />)}
            {activeTab === "setup" && <SetupTab onCatalogLinked={store.refresh} showError={showError} drafts={drafts.current} key={loc} items={S.items} persistItems={persistItems} areas={S.areas} persistAreas={persistAreas} showToast={showToast} rid={loc} />}
            {activeTab === "invoices" && <InvoicesTab showError={showError} drafts={drafts.current} key={loc} rid={loc} items={S.items} persistItems={persistItems} purchases={S.purchases} persistPurchases={persistPurchases} showToast={showToast} restaurantName={current.name} />}
            {activeTab === "order" && <OrderTab key={loc} items={S.items} showToast={showToast} restaurantName={current.name} rid={loc} onCreatedPO={() => setActiveTab("purchaseOrders")} />}
            {activeTab === "purchaseOrders" && <PurchaseOrdersTab key={loc} rid={loc} showToast={showToast} focusOrder={focusOrder} onInventoryChange={store.refresh} />}
            {activeTab === "menu" && <MenuTab dishes={S.dishes} onAddNew={() => openCosting(null)} onOpenDish={(id) => openCosting(id)} />}
            {activeTab === "costing" && <CostingTab rid={loc} showError={showError} drafts={drafts.current} key={loc} items={S.items} dishes={S.dishes} persist={persistDishes} showToast={showToast} focusDish={costingFocus} />}
            {activeTab === "recipeCards" && <RecipeCardsTab items={S.items} dishes={S.dishes} />}
            {activeTab === "sales" && <SalesTrackingTab revision={S.revision} rid={loc} showError={showError} drafts={drafts.current} key={loc} actualMode={api.nativePurchasesEnabled} items={S.items} dishes={S.dishes} purchases={S.purchases} adjustments={S.adjustments} salesPeriod={S.salesPeriod} persist={persistSalesPeriod} reportingPeriods={S.reportingPeriods} persistReportingPeriods={persistReportingPeriods} showToast={showToast} />}
            {activeTab === "adjustments" && <AdjustmentsTab rid={loc} showError={showError} drafts={drafts.current} key={loc} items={S.items} adjustments={S.adjustments} persist={persistAdjustments} showToast={showToast} />}
            {activeTab === "history" && (api.nativePurchasesEnabled ? <NativePurchaseHistory key={loc} restaurantId={loc} onOpenInvoices={() => setActiveTab("invoices")} /> : <HistoryTab items={S.items} purchases={S.purchases} focusControlNumber={historyFocusCN} />)}
            {activeTab === "scheduling" && <SchedulingTab key={loc} rid={loc} showToast={showToast} />}
            {activeTab === "team" && <StaffTab key={loc} rid={loc} showToast={showToast} />}
          </>
        )}
      </main>

      {staffOpen && <StaffSheet drafts={drafts.current} onClose={() => setStaffOpen(false)} onElevate={(sess) => { api.storeSession(sess); setSession(sess); setStaffOpen(false); }} />}
      <AiAssistant rid={aiRid || (isOwner ? "berts" : loc)} setRid={setAiRid} open={aiOpen} onClose={() => setAiOpen(false)} />
    </div>
  );
}
