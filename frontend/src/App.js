import React, { useEffect, useMemo, useRef, useState } from "react";
import { Toaster, toast } from "sonner";
import {
  LayoutDashboard, ClipboardList, ClipboardCheck, Settings, FileText, ShoppingCart, BookOpen, ChefHat,
  Printer, Activity, AlertTriangle, TrendingUp, Building2, Download, Upload, Sparkles, Boxes, CalendarClock,
} from "lucide-react";
import { RESTAURANTS, OWNER, isOrderEnabled, statusOf, downloadJSON, todayISO, workweekRange } from "./lib/calc";
import * as api from "./lib/api";
import { DashboardTab } from "./components/DashboardTab";
import { CountsTab } from "./components/CountsTab";
import { SetupTab } from "./components/SetupTab";
import { InvoicesTab } from "./components/InvoicesTab";
import { OrderTab } from "./components/OrderTab";
import { PurchaseOrdersTab } from "./components/PurchaseOrdersTab";
import { MenuTab } from "./components/MenuTab";
import { CostingTab } from "./components/CostingTab";
import { RecipeCardsTab } from "./components/RecipeCardsTab";
import { SalesTrackingTab } from "./components/SalesTrackingTab";
import { AdjustmentsTab } from "./components/AdjustmentsTab";
import { HistoryTab } from "./components/HistoryTab";
import { PrepTab } from "./components/PrepTab";
import { SchedulingTab } from "./components/SchedulingTab";
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
];

const DEFAULT_PERIOD = (() => { const w = workweekRange(); return { periodStart: w.start, periodEnd: w.end, dishSales: {}, itemCounts: {} }; })();
const EMPTY_STATE = { items: [], purchases: [], dishes: [], adjustments: [], reportingPeriods: [], prepStock: [], prepLogs: [], salesPeriod: DEFAULT_PERIOD, areas: [] };

export default function App() {
  const [session, setSession] = useState(() => api.currentSession());
  const [loc, setLoc] = useState(() => api.currentSession()?.user?.role === "owner" ? "owner" : (api.currentSession()?.user?.locations || [])[0] || "berts");
  const [activeTab, setActiveTab] = useState("dashboard");
  const [S, setS] = useState(null);
  const [historyFocusCN, setHistoryFocusCN] = useState(null);
  const [dashboardFlaggedOnly, setDashboardFlaggedOnly] = useState(false);
  const [costingFocus, setCostingFocus] = useState(null);
  const [aiOpen, setAiOpen] = useState(false);
  const [aiRid, setAiRid] = useState(null);
  const [staffOpen, setStaffOpen] = useState(false);
  const [focusOrder, setFocusOrder] = useState(null);
  const backupRef = useRef(null);
  const pendingTabRef = useRef(null);
  // Always holds the most recently selected location, read inside async callbacks
  // below to discard a response that arrives after the user has already switched
  // locations again (a slow fetch for the old location landing after a newer one).
  const locRef = useRef(loc);
  locRef.current = loc;

  const isOwner = !!session && loc === "owner" && session.user.role === "owner";
  const current = isOwner ? OWNER : RESTAURANTS.find((r) => r.id === loc) || RESTAURANTS[0];
  const accessibleRestaurants = RESTAURANTS.filter((r) => session?.user?.role === "owner" || session?.user?.locations?.includes(r.id));
  const visibleTabs = session?.user?.role === "readonly"
    ? TABS.filter((t) => ["dashboard", "history"].includes(t.id))
    : session?.user?.role === "staff"
      ? TABS.filter((t) => ["dashboard", "prep", "counts"].includes(t.id))
      : TABS;

  useEffect(() => {
    if (!session || isOwner) return;
    setS(null);
    setActiveTab(pendingTabRef.current || "dashboard");
    pendingTabRef.current = null;
    const requestedLoc = loc;
    api.fetchState(loc)
      .then((data) => { if (locRef.current === requestedLoc) setS({ ...EMPTY_STATE, ...data }); })
      .catch(() => toast.error("Couldn't load location data — is the backend up?"));
  }, [loc, isOwner]);

  useEffect(() => {
    if (!session || isOwner) return undefined;
    const timer = setInterval(() => {
      api.fetchState(loc).then((data) => {
        if (locRef.current === loc) setS((previous) => ({ ...previous, ...data }));
      }).catch(() => {});
    }, 15000);
    return () => clearInterval(timer);
  }, [loc, isOwner]);

  const showToast = (msg) => toast.success(msg);

  function persistCollection(name, next) {
    setS((p) => ({ ...p, [name]: next }));
    return api.putCollection(loc, name, next, S?.revision).then((result) => {
      setS((p) => ({ ...p, revision: result.revision ?? p.revision }));
      return result;
    }).catch((err) => {
      toast.error(err?.response?.status === 409 ? "This data changed elsewhere — reload before saving" : `Couldn't save ${name} — check your connection`);
      return null;
    });
  }
  const persistItems = (next) => persistCollection("items", next);
  const persistPurchases = (next) => persistCollection("purchases", next);
  const persistDishes = (next) => persistCollection("dishes", next);
  const persistAdjustments = (next) => persistCollection("adjustments", next);
  const persistReportingPeriods = (next) => persistCollection("reportingPeriods", next);
  const persistAreas = (next) => persistCollection("areas", next);
  function persistSalesPeriod(next) {
    setS((p) => ({ ...p, salesPeriod: next }));
    return api.putSalesPeriod(loc, next, S?.revision).then((result) => {
      setS((p) => ({ ...p, revision: result.revision ?? p.revision }));
      return result;
    }).catch((err) => {
      toast.error(err?.response?.status === 409 ? "This data changed elsewhere — reload before saving" : "Couldn't save the sales period");
      return null;
    });
  }
  function applyPrepResult(res) {
    setS((p) => ({ ...p, items: res.items ?? p.items, prepStock: res.prepStock ?? p.prepStock, prepLogs: res.log ? [res.log, ...(p.prepLogs || [])] : p.prepLogs }));
  }

  function openCosting(dishId) { setCostingFocus({ id: dishId, nonce: Date.now() + Math.random() }); setActiveTab("costing"); }
  function openOrder(rid, orderId) { pendingTabRef.current = "purchaseOrders"; setFocusOrder({ id: orderId, nonce: Date.now() + Math.random() }); if (rid === loc) { setActiveTab("purchaseOrders"); } else { setLoc(rid); } }

  const alertCount = useMemo(() => !S ? 0 : S.items.filter((it) => isOrderEnabled(it) && statusOf(it).key !== "ok").length, [S]);

  function backupAll() {
    if (!S) return;
    downloadJSON(`${current.short.replace(/\W+/g, "")}_backup_${todayISO()}.json`, {
      exportedAt: new Date().toISOString(), restaurant: loc,
      items: S.items, purchases: S.purchases, dishes: S.dishes, areas: S.areas, salesPeriod: S.salesPeriod, adjustments: S.adjustments, reportingPeriods: S.reportingPeriods,
    });
    showToast("Backup downloaded");
  }

  function restoreBackup(e) {
    const file = e.target.files?.[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = async () => {
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
        const step = async (label, fn) => { if (!(await fn())) failed.push(label); };
        await step("items", () => persistItems(data.items || []));
        await step("purchases", () => persistPurchases(data.purchases || []));
        await step("dishes", () => persistDishes(data.dishes || []));
        if (data.areas) await step("areas", () => persistAreas(data.areas));
        if (data.salesPeriod) await step("sales period", () => persistSalesPeriod(data.salesPeriod));
        await step("adjustments", () => persistAdjustments(data.adjustments || []));
        await step("reporting periods", () => persistReportingPeriods(data.reportingPeriods || []));
        if (failed.length) {
          toast.error(`Restore finished with problems — ${failed.join(", ")} did not save. Re-check those sections and try again.`);
        } else {
          showToast("Backup restored");
        }
      } catch (err) { toast.error("Couldn't read that file"); }
    };
    reader.readAsText(file);
    if (backupRef.current) backupRef.current.value = "";
  }

  if (!session) return <Login onLogin={setSession} />;
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
                  <button onClick={backupAll} className="flex items-center gap-1.5 rounded-full px-3 py-1.5 text-xs font-semibold border border-[#334155] bg-[#161F30] text-slate-300 hover:border-[var(--acc)] transition" data-testid="backup-button"><Download size={13} /> Backup</button>
                  <button onClick={() => backupRef.current?.click()} className="flex items-center gap-1.5 rounded-full px-3 py-1.5 text-xs font-semibold border border-[#334155] bg-[#161F30] text-slate-300 hover:border-[var(--acc)] transition" data-testid="restore-button"><Upload size={13} /> Restore</button>
                  <input ref={backupRef} type="file" accept=".json,application/json" onChange={restoreBackup} className="hidden" />
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
            {activeTab === "dashboard" && <DashboardTab items={S.items} purchases={S.purchases} dishes={S.dishes} adjustments={S.adjustments} salesPeriod={S.salesPeriod} reportingPeriods={S.reportingPeriods} onOpenHistory={(cn) => { setHistoryFocusCN(cn); setActiveTab("history"); }} flaggedOnly={dashboardFlaggedOnly} setFlaggedOnly={setDashboardFlaggedOnly} />}
            {activeTab === "prep" && <PrepTab rid={loc} items={S.items} dishes={S.dishes} persistDishes={persistDishes} prepStock={S.prepStock} prepLogs={S.prepLogs} applyPrepResult={applyPrepResult} salesPeriod={S.salesPeriod} showToast={showToast} />}
            {activeTab === "counts" && <CountsTab items={S.items} persist={persistItems} showToast={showToast} />}
            {activeTab === "setup" && <SetupTab items={S.items} persistItems={persistItems} areas={S.areas} persistAreas={persistAreas} showToast={showToast} rid={loc} />}
            {activeTab === "invoices" && <InvoicesTab items={S.items} persistItems={persistItems} purchases={S.purchases} persistPurchases={persistPurchases} showToast={showToast} restaurantName={current.name} />}
            {activeTab === "order" && <OrderTab items={S.items} showToast={showToast} restaurantName={current.name} rid={loc} onCreatedPO={() => setActiveTab("purchaseOrders")} />}
            {activeTab === "purchaseOrders" && <PurchaseOrdersTab rid={loc} showToast={showToast} focusOrder={focusOrder} onInventoryChange={() => { const requestedLoc = loc; api.fetchState(loc).then((data) => { if (locRef.current === requestedLoc) setS({ ...EMPTY_STATE, ...data }); }); }} />}
            {activeTab === "menu" && <MenuTab dishes={S.dishes} onAddNew={() => openCosting(null)} onOpenDish={(id) => openCosting(id)} />}
            {activeTab === "costing" && <CostingTab items={S.items} dishes={S.dishes} persist={persistDishes} showToast={showToast} focusDish={costingFocus} />}
            {activeTab === "recipeCards" && <RecipeCardsTab items={S.items} dishes={S.dishes} />}
            {activeTab === "sales" && <SalesTrackingTab items={S.items} dishes={S.dishes} purchases={S.purchases} adjustments={S.adjustments} salesPeriod={S.salesPeriod} persist={persistSalesPeriod} reportingPeriods={S.reportingPeriods} persistReportingPeriods={persistReportingPeriods} showToast={showToast} />}
            {activeTab === "adjustments" && <AdjustmentsTab items={S.items} adjustments={S.adjustments} persist={persistAdjustments} showToast={showToast} />}
            {activeTab === "history" && <HistoryTab items={S.items} purchases={S.purchases} focusControlNumber={historyFocusCN} />}
            {activeTab === "scheduling" && <SchedulingTab />}
          </>
        )}
      </main>

      {staffOpen && <StaffSheet onClose={() => setStaffOpen(false)} />}
      <AiAssistant rid={aiRid || (isOwner ? "berts" : loc)} setRid={setAiRid} open={aiOpen} onClose={() => setAiOpen(false)} />
    </div>
  );
}
