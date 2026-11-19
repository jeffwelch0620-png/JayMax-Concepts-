import { canSeeAnalytics } from "./positions";

// Which tabs a login sees. Read-only logins (including the Auditor) get the dashboard and history,
// plus analytics when their position allows it (positions.py see_analytics, Jeff 2026-11-19); staff
// get their prep screens. The server checks every permission again.
export const visibleTabs = (tabs, user, { analyticsEnabled = false, managerHandoffEnabled = false } = {}) => {
  const analytics = t => t.id === "analytics" && analyticsEnabled && canSeeAnalytics(user);
  if (user?.role === "readonly") return tabs.filter(t => ["dashboard", "history"].includes(t.id) || analytics(t));
  if (user?.role === "staff") return tabs.filter(t => ["dashboard", "prep", "counts"].includes(t.id));
  return tabs.filter(t => (t.id !== "managerOverview" || ["owner", "manager"].includes(user?.role))
    && (t.id !== "managerHandoff" || (managerHandoffEnabled && ["owner", "manager"].includes(user?.role)))
    && (t.id !== "analytics" || analytics(t)));
};
