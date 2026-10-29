import { countOverview, prepOverview, overviewContext, loadManagerOverview, rememberedOverview, validOverviewDay } from "./managerOverview";
import { overviewFixture, overviewTestOwner as owner, OVERVIEW_TEST_DAY as day } from "../testFixtures/managerOverview";
const context = overviewContext("berts", day, "bulk", owner);
const clone = x => JSON.parse(JSON.stringify(x));
test.each(["berts", "rudds", "papa_leonis"])("canonical restaurant scope %s", rid => {
  const c = overviewContext(rid, day, "bulk", owner), f = overviewFixture(rid);
  expect(countOverview(f.counts, c).count.date).toBe(day);
  expect(prepOverview(f.prep, c).tasks).toHaveLength(3);
  expect(c.storeId).toBe(rid === "papa_leonis" ? "papa" : rid);
});
test.each(["2026-02-30", "2026-10-32", "10/25/2026", "", null])("reject invalid day %s", value => expect(validOverviewDay(value)).toBe(false));
test.each([
  { ...owner, role: "staff" }, { ...owner, role: "readonly" }, { ...owner, role: "owner_admin" },
  { ...owner, id: "" }, { ...owner, role: "manager", locations: ["rudds"] }, { ...owner, locations: "berts" },
])("reject unauthorised/malformed actor %#", user => expect(overviewContext("berts", day, "bulk", user)).toBeNull());
test("manager with own scope is accepted; unknown restaurant/track are not", () => {
  expect(overviewContext("berts", day, "bulk", { ...owner, role: "manager" })).not.toBeNull();
  expect(overviewContext("owner", day, "bulk", owner)).toBeNull();
  expect(overviewContext("berts", day, "all", owner)).toBeNull();
});
test("current corrections supersede originals and future counts do not become latest", () => {
  const [original] = overviewFixture().counts;
  const correction = { ...original, id: "correction", corrects_snapshot_id: original.id, status: "incomplete", recorded_at: "2026-10-26T10:00:00Z" };
  const future = { ...original, id: "future", count_date: "2026-10-26" };
  expect(countOverview([original, future, correction], context).count).toMatchObject({ id: "correction", status: "incomplete" });
  expect(countOverview([future], context).count).toBeNull();
});
test("same-day count selects after receipts before before-receipts, without valuing totals", () => {
  const [row] = overviewFixture().counts;
  expect(countOverview([{ ...row, id: "before", timing: "before_receipts" }, row], context).count.id).toBe(row.id);
  expect(countOverview([], context)).toEqual({ state: "ready", count: null });
});
test.each([
  rows => { rows[0].store_id = "rudds"; }, rows => { rows[0].status = "unknown"; },
  rows => { rows[0].scope_revision = "2"; }, rows => { rows[0].count_date = "2026-02-30"; },
  rows => { rows[0].recorded_at = "2026-10-25T18:00:00"; },
  rows => { rows[0].corrects_snapshot_id = "missing"; }, rows => { rows.push(clone(rows[0])); },
  rows => { rows.push({ ...rows[0], id: "cycle", corrects_snapshot_id: rows[0].id }); rows[0].corrects_snapshot_id = "cycle"; },
])("count ambiguity fails closed %#", change => {
  const rows = overviewFixture().counts; change(rows); expect(() => countOverview(rows, context)).toThrow();
});
test("prep work preserves open, in-progress and review-needed states without making accounting claims", () => {
  const value = prepOverview(overviewFixture().prep, context);
  expect(value).toMatchObject({ hasDraft: true, status: "released", revision: 4, progressAvailable: true });
  expect(value.tasks.map(t => t.state)).toEqual(["open", "in_progress", "needs_review"]);
});
test("corrected production can require review even for a previously closed task", () => {
  const { prep } = overviewFixture(); prep.task_progress[2].closed = true;
  expect(prepOverview(prep, context).tasks[2].state).toBe("needs_review");
  prep.task_progress[0] = { ...prep.task_progress[0], status: "complete", closed: true };
  expect(prepOverview(prep, context).tasks[0].state).toBe("complete");
});
test("unsupported progress stays unknown while a source correction still requires review", () => {
  const { prep } = overviewFixture(); prep.progress_supported = false; prep.task_progress = [];
  expect(prepOverview(prep, context).tasks.map(t => t.state)).toEqual(["unavailable", "unavailable", "needs_review"]);
});
test("no draft and no tasks means no dated plan, not completed work", () => {
  const { prep } = overviewFixture(); Object.assign(prep, { status: "draft", draft: null, draft_version_id: null, release: null, tasks: [], task_progress: [], completions: [] });
  expect(prepOverview(prep, context)).toMatchObject({ hasDraft: false, tasks: [] });
});
test("prior draft production reviews remain visible without replacing the current task list", () => {
  const { prep } = overviewFixture(); prep.completions.push({ task_id: "prior-version-task", needs_review: true });
  const result = prepOverview(prep, context);
  expect(result.historicalReviews).toBe(1); expect(result.tasks).toHaveLength(3);
});
test("omitted tasks never appear as outstanding work and quantities never imply completion", () => {
  const { prep } = overviewFixture(); prep.tasks[2].included = false;
  prep.task_progress[0].effective_base_quantity = "999999999999.000001";
  const result = prepOverview(prep, context);
  expect(result.tasks.map(t => t.state)).toEqual(["open", "in_progress"]);
});
test.each([
  p => { p.store_id = "rudds"; }, p => { p.prep_date = "2026-10-26"; }, p => { p.track = "daily"; },
  p => { p.revision = -1; }, p => { p.draft.review_snapshot.track = "daily"; },
  p => { p.release.draft_version_id = "old"; }, p => { p.task_progress.pop(); },
  p => { p.task_progress[0].status = "complete"; }, p => { p.task_progress[0].needs_review = "false"; },
  p => { delete p.progress_supported; }, p => { p.tasks[0].included = null; },
  p => { p.task_progress[1].task_id = p.task_progress[0].task_id; },
  p => { p.draft = null; p.draft_version_id = null; p.status = "draft"; },
  p => { p.completions[0].task_id = null; },
])("malformed or mixed-scope prep read fails closed %#", change => {
  const { prep } = overviewFixture(); change(prep); expect(() => prepOverview(prep, context)).toThrow();
});
function apiFor(f = overviewFixture()) {
  return { actualInventoryEnabled: true, prepExecutionEnabled: true,
    actualCounts: jest.fn().mockResolvedValue(f.counts), prepExecution: jest.fn().mockResolvedValue(f.prep),
    saveState: jest.fn(), staffIdentify: jest.fn(), commitPrepExecution: jest.fn() };
}
test("loader calls only the two existing GET readers in the exact selected scope", async () => {
  const api = apiFor(), receive = jest.fn(); await loadManagerOverview(context, api, receive);
  expect(api.actualCounts).toHaveBeenCalledWith("berts"); expect(api.prepExecution).toHaveBeenCalledWith("berts", day, "bulk");
  expect(receive).toHaveBeenCalledTimes(2); expect(api.saveState).not.toHaveBeenCalled(); expect(api.staffIdentify).not.toHaveBeenCalled(); expect(api.commitPrepExecution).not.toHaveBeenCalled();
});
test("each section fails independently, and errors never expose raw source details", async () => {
  const api = apiFor(), receive = jest.fn(); api.actualCounts.mockRejectedValue(new Error("PRIVATE connection secret"));
  await loadManagerOverview(context, api, receive);
  expect(receive.mock.calls.find(([name]) => name === "counts")[1].state).toBe("unavailable");
  expect(receive.mock.calls.find(([name]) => name === "prep")[1].state).toBe("ready");
  expect(JSON.stringify(receive.mock.calls)).not.toContain("PRIVATE");
});
test("disabled sources and absent authority do not issue reads", async () => {
  const api = apiFor(), receive = jest.fn(); api.actualInventoryEnabled = api.prepExecutionEnabled = false;
  await loadManagerOverview(context, api, receive); await loadManagerOverview(null, api, receive);
  expect(api.actualCounts).not.toHaveBeenCalled(); expect(api.prepExecution).not.toHaveBeenCalled();
  expect(receive.mock.calls.every(([, r]) => r.state === "unavailable")).toBe(true);
});
test("a stuck source times out while its independent sibling succeeds", async () => {
  jest.useFakeTimers();
  try {
    const api = apiFor(), receive = jest.fn(); api.actualCounts.mockReturnValue(new Promise(() => {}));
    const pending = loadManagerOverview(context, api, receive); await Promise.resolve(); await Promise.resolve();
    jest.advanceTimersByTime(60000); await pending;
    expect(receive.mock.calls.find(([name]) => name === "counts")[1].state).toBe("unavailable");
    expect(receive.mock.calls.find(([name]) => name === "prep")[1].state).toBe("ready");
  } finally { jest.useRealTimers(); }
});
test("view preferences are per person/store and never contain records", () => {
  const storage = { getItem: jest.fn(key => key === `manager-overview:${owner.id}:berts` ? JSON.stringify({ day, track: "daily", malicious: "ignored" }) : null) };
  expect(rememberedOverview(storage, owner.id, "berts", day)).toEqual({ day, track: "daily" });
  expect(rememberedOverview(storage, "other", "berts", day)).toEqual({ day, track: "bulk" });
  expect(rememberedOverview({ getItem: () => { throw Error("blocked"); } }, owner.id, "berts", day)).toEqual({ day, track: "bulk" });
  expect(rememberedOverview({ getItem: () => '{"day":"2026-02-30","track":"daily"}' }, owner.id, "berts", day).track).toBe("bulk");
});

// B1 receiving tests use a separate native-shaped fictional basket.
describe("B1 native quantity projection",()=>{
 const b1=require("../testFixtures/managerB1"), project=require("./managerOverview").prepQuantityOverview;
 const c=overviewContext("berts","2026-10-26","daily",b1.b1Owner);
 test("T01–T04 exact native examples, no cross-product total and no mutation",()=>{
   const f=b1.b1Fixture(), before=JSON.stringify(f);const p=project(f.prep,c);
   expect(p.tasks[0]).toMatchObject({planned:"4",reviewed:"3",remaining:"1",unit:"lb"});
   expect(p.tasks[1]).toMatchObject({closed:true,remaining:"1"});
   expect(p.tasks[2]).toMatchObject({reviewed:"0",remaining:"4"});
   for(const i of [3,4]){expect(p.tasks[i].quantityState).toBe("review_required");expect(p.tasks[i].remaining).toBeUndefined();}
   expect(p.tasks[5].remaining).toBe("0.876543210988");expect(p.tasks[6]).toMatchObject({remaining:"0",excess:"1"});
   expect(p.total).toBeUndefined();expect(JSON.stringify(f)).toBe(before);
 });
 test.each([
  p=>{p.tasks[0].planned_base_quantity=null;},p=>{p.task_progress[0].reviewed_base_quantity="-1";},
  p=>{p.tasks[0].task_snapshot.base_unit="portion";},p=>{p.task_progress[0].planned_base_quantity="5";},
  p=>{p.task_progress[0].reviewed_base_quantity=3;},p=>{p.task_progress[0].reviewed_base_quantity="1.0000000000001";},
  p=>{p.task_progress[0].links.push(p.task_progress[0].links[0]);},p=>{p.completions[0].effective_batch.store_id="rudds";},
  p=>{p.completions[0].effective_batch.product_id=b1.b1Id(999);},p=>{p.completions[0].effective_batch.base_unit="each";},
  p=>{p.completions[0].effective_batch.review_snapshot.usableBaseOutput="2";},p=>{p.task_progress[0].links=[];}
 ])("T04/T06 inconsistent native row holds quantities %#",change=>{const f=b1.b1Fixture();change(f.prep);const t=project(f.prep,c).tasks[0];expect(t.quantityState).toBe("unavailable");expect(t.remaining).toBeUndefined();});
 test("T03 changed batch IDs require review even when flags are inconsistent",()=>{const f=b1.b1Fixture();f.prep.task_progress[0].links[0].effective_batch_event_id=b1.b1Id(999);const t=project(f.prep,c).tasks[0];expect(t.state).toBe("needs_review");expect(t.remaining).toBeUndefined();});
 test("T04 explicit zero planned and reviewed is confirmed",()=>{const f=b1.b1Fixture(),t=f.prep.tasks[2],p=f.prep.task_progress[2];t.planned_base_quantity=t.task_snapshot.planned_base_quantity=p.planned_base_quantity="0";expect(project(f.prep,c).tasks[2]).toMatchObject({planned:"0",reviewed:"0",remaining:"0"});});
});
