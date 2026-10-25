import { webcrypto } from "crypto";
import { TextEncoder } from "util";
import { handoffContext, checkedHandoffRequest, handoffFingerprint, handoffJournal, checkedHandoffDay,
  checkedHandoffReceipt, checkedHandoffStatus, checkedHandoffHistory } from "./managerHandoff";
import { handoffOwner as actor, handoffBody as body, handoffDay as day, handoffState as state,
  handoffNote as note, handoffReceipt as receipt, handoffId } from "../testFixtures/managerHandoff";
const c = handoffContext("berts", day, "bulk", actor);
const request = async () => { const b = body(); return { key: handoffId, version: 0, body: b, fingerprint: await handoffFingerprint(actor.id, "berts", b, 0) }; };
beforeAll(() => { Object.defineProperty(window, "crypto", { configurable: true, value: webcrypto }); global.TextEncoder = TextEncoder; });
beforeEach(() => window.sessionStorage.clear());
test("canonical Unicode fingerprint agrees with Python and isolates all command identity", async () => {
  const r = await request(); expect(r.fingerprint).toBe("70b76d6717fca4232b19e2c26ac1ef8e3c444d587588664655ce4974dd371f72");
  for (const args of [["usr_other", "berts", r.body, 0], [actor.id, "rudds", r.body, 0], [actor.id, "berts", r.body, 1], [actor.id, "berts", body({ summary: "changed" }), 0]]) {
    expect(await handoffFingerprint(...args)).not.toBe(r.fingerprint);
  }
});
test.each(["staff", "readonly", "owner_admin", null])("%s does not obtain personal manager UI context", role => expect(handoffContext("berts", day, "bulk", { ...actor, role })).toBeNull());
test("location/date/track are strict and owner does not need a roster selection", () => {
  expect(c).toBeTruthy();
  for (const args of [["comm", day, "bulk", actor], ["berts", "2026-02-30", "bulk", actor], ["berts", day, "all", actor],
    ["berts", day, "bulk", { ...actor, role: "manager", locations: "berts" }], ["berts", day, "bulk", { ...actor, role: "manager", locations: ["rudds"] }]]) expect(handoffContext(...args)).toBeNull();
});
test("journal is exact actor/store scoped, durable before send, and refuses replacement", async () => {
  const r = await request(), j = handoffJournal(actor.id, "berts"); j.save(r); expect(j.read()).toEqual(r);
  expect(handoffJournal("usr_other", "berts").read()).toBeNull(); expect(handoffJournal(actor.id, "rudds").read()).toBeNull();
  expect(() => j.save({ ...r, key: "22222222-2222-4222-8222-222222222222" })).toThrow();
  expect(() => j.clear({ ...r, version: 1 })).toThrow(); expect(j.read()).toEqual(r); j.clear(r); expect(j.read()).toBeNull();
});
test("blocked, full, corrupt and incomplete storage fail closed", async () => {
  const r = await request();
  expect(() => handoffJournal(actor.id, "berts", () => { throw Error(); }).read()).toThrow();
  expect(() => handoffJournal(actor.id, "berts", () => ({ getItem: () => null, setItem: () => { throw Error(); } })).save(r)).toThrow();
  window.sessionStorage.setItem(`jaymax:manager-handoff:v1:${actor.id}:berts`, "{broken");
  expect(() => handoffJournal(actor.id, "berts").read()).toThrow();
});
test("request shape preserves code points and refuses unsafe values", async () => {
  const r = await request(); expect(checkedHandoffRequest({ ...r, body: body({ summary: "🍲".repeat(6000) }) })).toBeTruthy();
  for (const patch of [{ summary: " " }, { summary: "x".repeat(6001) }, { summary: "\ud800" }, { summary: "\0" }, { business_date: "2026-02-30" },
    { actor_id: "forged" }, { action: "correct" }, { settings_revision: true }]) expect(() => checkedHandoffRequest({ ...r, body: body(patch) })).toThrow();
});
test("day read refuses mixed scope, invalid timezone and unknown state", () => {
  expect(checkedHandoffDay(state(), c)).toBeTruthy();
  for (const changes of [{ actor_id: "usr_other" }, { store_id: "rudds" }, { current: note({ status: "complete" }) },
    { settings: { store_id: "berts", timezone_name: "invalid/timezone", revision: 1 } }, { previous: note() }]) expect(() => checkedHandoffDay(state(changes), c)).toThrow();
});
test("receipt can acknowledge original revision while retaining newer shared content", async () => {
  const r = await request(), newer = note({ revision: 3, action: "save_draft", summary: "Newer manager text", actor_id: "usr_other" });
  expect(checkedHandoffReceipt(receipt(r, newer), r, c).current).toEqual(newer);
  for (const changes of [{ request_fingerprint: "0".repeat(64) }, { actor_id: "usr_other" }, { current: note({ revision: 0 }) }, { accepted: { ...receipt(r).accepted, summary: "changed" } }]) expect(() => checkedHandoffReceipt({ ...receipt(r), ...changes }, r, c)).toThrow();
});
test("unconfirmed status cannot acknowledge or discard a request", async () => {
  const r = await request(), v = { ...receipt(r), outcome: "unconfirmed", current: null };
  expect(checkedHandoffStatus(v, r, c).outcome).toBe("unconfirmed");
  expect(() => checkedHandoffStatus({ ...v, request_key: "wrong" }, r, c)).toThrow();
});
test("history requires contiguous same-store revisions and complete pagination claims", async () => {
  const r = await request(), row = receipt(r).accepted;
  const v = { store_id: "berts", actor_id: actor.id, note_id: handoffId, current_revision: 1, after: 0, rows: [row], next_after: null };
  expect(checkedHandoffHistory(v, c, handoffId, 0)).toEqual(v);
  for (const changes of [{ current_revision: 2 }, { rows: [{ ...row, store_id: "rudds" }] }, { rows: [{ ...row, revision: 2 }] }, { next_after: 1 }]) expect(() => checkedHandoffHistory({ ...v, ...changes }, c, handoffId, 0)).toThrow();
});
