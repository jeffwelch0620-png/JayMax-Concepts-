import { prepTracks, validPrepTrack, prepTrackLabel } from "./prepTracks";
import { overviewContext } from "./managerOverview";
import { handoffContext } from "./managerHandoff";

const owner = { id: "usr_owner", role: "owner", locations: ["berts", "rudds", "papa_leonis"] };

test("Salad Bar is offered only at Bert's", () => {
  expect(prepTracks("berts").map(t => t.id)).toEqual(["daily", "bulk", "salad"]);
  for (const rid of ["rudds", "papa_leonis", ""]) expect(prepTracks(rid).map(t => t.id)).toEqual(["daily", "bulk"]);
  expect(validPrepTrack("berts", "salad")).toBe(true);
  expect(validPrepTrack("rudds", "salad")).toBe(false);
  expect(validPrepTrack("berts", "weekly")).toBe(false);
  expect(prepTrackLabel("salad")).toBe("Salad Bar Prep");
});

test("overview and handoff contexts accept Salad at Bert's and refuse it elsewhere", () => {
  expect(overviewContext("berts", "2026-10-29", "salad", owner)?.track).toBe("salad");
  expect(overviewContext("rudds", "2026-10-29", "salad", owner)).toBeNull();
  expect(handoffContext("berts", "2026-10-29", "salad", owner)?.track).toBe("salad");
  expect(handoffContext("papa_leonis", "2026-10-29", "salad", owner)).toBeNull();
  expect(overviewContext("rudds", "2026-10-29", "bulk", owner)?.track).toBe("bulk");
});
