import { visibleTabs } from "./visibleTabs";

const TABS = ["dashboard", "counts", "prep", "history", "analytics", "managerOverview", "managerHandoff"].map(id => ({ id }));
const ids = (user, flags) => visibleTabs(TABS, user, flags).map(t => t.id);
const on = { analyticsEnabled: true, managerHandoffEnabled: true };

test("the Auditor sees analytics alongside the read-only tabs when it is switched on", () => {
  expect(ids({ role: "readonly", position: "AUD" }, on)).toEqual(["dashboard", "history", "analytics"]);
  expect(ids({ role: "readonly", position: "AUD" }, { analyticsEnabled: false })).toEqual(["dashboard", "history"]);
});

test("a read-only login without the Auditor position keeps dashboard and history only", () => {
  expect(ids({ role: "readonly" }, on)).toEqual(["dashboard", "history"]);
  expect(ids({ role: "readonly", position: "GM" }, on)).toEqual(["dashboard", "history"]); // position and access class disagree
});

test("staff, managers and owners keep their tabs", () => {
  expect(ids({ role: "staff" }, on)).toEqual(["dashboard", "counts", "prep"]);
  expect(ids({ role: "manager", position: "KM" }, on)).toEqual(["dashboard", "counts", "prep", "history", "managerOverview", "managerHandoff"]);
  expect(ids({ role: "manager", position: "GM" }, on)).toContain("analytics");
  expect(ids({ role: "owner" }, { analyticsEnabled: true })).toEqual(["dashboard", "counts", "prep", "history", "analytics", "managerOverview"]);
});
