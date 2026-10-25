import axios from "axios";
import * as api from "./api";
import { handoffBody, handoffId } from "../testFixtures/managerHandoff";
jest.mock("axios", () => ({ get: jest.fn(), post: jest.fn(), interceptors: { request: { use: jest.fn() }, response: { use: jest.fn() } } }));
beforeEach(() => { axios.get.mockResolvedValue({ data: { fictional: true } }); axios.post.mockResolvedValue({ data: { fictional: true } }); });
test("receiving GETs preserve cancellation and canonical store/date/track/history scope", async () => {
  const signal = new AbortController().signal;
  expect(await api.handoffDay("papa_leonis", "2026-10-25", "bulk", { signal })).toEqual({ fictional: true });
  expect(axios.get).toHaveBeenLastCalledWith(expect.stringContaining("/api/pg/operations/papa/handoff-notes/days/2026-10-25"), { signal, params: { track: "bulk" } });
  await api.handoffHistory("papa_leonis", handoffId, 50, { signal });
  expect(axios.get).toHaveBeenLastCalledWith(expect.stringContaining(`/papa/handoff-notes/notes/${handoffId}/history`), { signal, params: { after: 50 } });
});
test("command and read-only receipt probe preserve exact body, request key and expected revision", async () => {
  const body = handoffBody();
  await api.saveHandoff("berts", body, 0, handoffId); await api.handoffStatus("berts", body, 0, handoffId);
  const calls = axios.post.mock.calls;
  expect(calls.map(c => c[0].split("/").at(-1))).toEqual(["commands", "status"]);
  calls.forEach(c => { expect(c[1]).toBe(body); expect(c[2]).toEqual({ timeout: 60000, headers: { "If-Match": '"0"', "Idempotency-Key": handoffId } }); });
});
test.each([undefined, "false"])("capability defaults off for %s", value => {
  const before = process.env.REACT_APP_MANAGER_HANDOFF_NOTES;
  try {
    if (value === undefined) delete process.env.REACT_APP_MANAGER_HANDOFF_NOTES; else process.env.REACT_APP_MANAGER_HANDOFF_NOTES = value;
    jest.isolateModules(() => expect(require("./api").managerHandoffEnabled).toBe(false));
  } finally { if (before === undefined) delete process.env.REACT_APP_MANAGER_HANDOFF_NOTES; else process.env.REACT_APP_MANAGER_HANDOFF_NOTES = before; }
});
