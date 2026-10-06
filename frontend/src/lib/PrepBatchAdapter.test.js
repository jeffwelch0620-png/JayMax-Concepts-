import axios from "axios";
import * as api from "./api";
jest.mock("axios");
test("batch records, corrections and history use the canonical location and exact request key", async () => {
  axios.get.mockResolvedValue({ data: {} }); axios.post.mockResolvedValue({ data: {} });
  await api.nativePrepBatchSetup("papa_leonis"); await api.nativePrepBatchHistory("papa_leonis", "root");
  await api.previewNativePrepBatch("papa_leonis", { inputs: [] }); await api.saveNativePrepBatch("papa_leonis", { quantity: "0.000000000001" }, "key");
  await api.previewNativePrepBatchChange("papa_leonis", "event", { kind: "void" }); await api.saveNativePrepBatchChange("papa_leonis", "event", { kind: "void" }, "change-key");
  expect(axios.get.mock.calls[0][0]).toMatch(/\/pg\/purchases\/papa\/prep-batches\/setup$/);
  expect(axios.get.mock.calls[1][0]).toMatch(/\/pg\/purchases\/papa\/prep-batches\/root\/history$/);
  expect(axios.post.mock.calls[1]).toEqual([expect.stringMatching(/\/pg\/purchases\/papa\/prep-batches$/), { quantity: "0.000000000001" }, { headers: { "Idempotency-Key": "key" } }]);
  expect(axios.post.mock.calls[3][2]).toEqual({ headers: { "Idempotency-Key": "change-key" } });
});
