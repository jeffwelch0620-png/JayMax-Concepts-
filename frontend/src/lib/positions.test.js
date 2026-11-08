import { POSITIONS, canSeeAnalytics } from "./positions";

// Mirrors backend/positions.py see_analytics (Jeff 2026-11-06): the General Manager and above.
test("analytics is for the General Manager and above", () => {
  const seen = POSITIONS.filter(p => canSeeAnalytics({ role: p.role, position: p.code })).map(p => p.code);
  expect(seen).toEqual(["OWN", "OPS", "GM"]);
});

test("a login with no position keeps its access class", () => {
  expect(canSeeAnalytics({ role: "owner" })).toBe(true);
  expect(canSeeAnalytics({ role: "manager" })).toBe(false);
  expect(canSeeAnalytics({ role: "manager", position: "OWN" })).toBe(false); // position and access class disagree
  expect(canSeeAnalytics(null)).toBe(false);
});
