import axios from "axios";
import * as api from "./api";
jest.mock("axios");
test("waste and count requests retain the canonical location, journal and exact key", async () => {
  axios.get.mockResolvedValue({ data: {} }); axios.post.mockResolvedValue({ data: {} });
  await api.nativePrepObservationSetup("papa_leonis"); await api.nativePrepObservationHistory("papa_leonis", "count", "root");
  await api.previewNativePrepObservation("papa_leonis", "waste", { quantity: "5.000000000001" }); await api.saveNativePrepObservation("papa_leonis", "count", { quantity: "0" }, "key");
  await api.previewNativePrepObservationChange("papa_leonis", "count", "event", { kind: "void" }); await api.saveNativePrepObservationChange("papa_leonis", "count", "event", { kind: "void" }, "change-key");
  expect(axios.get.mock.calls[0][0]).toMatch(/\/pg\/purchases\/papa\/prep-observations\/setup$/);
  expect(axios.get.mock.calls[1][0]).toMatch(/\/pg\/purchases\/papa\/prep-observations\/count\/root\/history$/);
  expect(axios.post.mock.calls[1]).toEqual([expect.stringMatching(/\/pg\/purchases\/papa\/prep-observations\/count$/), { quantity: "0" }, { headers: { "Idempotency-Key": "key" } }]);
  expect(axios.post.mock.calls[3][2]).toEqual({ headers: { "Idempotency-Key": "change-key" } });
});
