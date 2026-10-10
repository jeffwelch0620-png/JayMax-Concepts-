import axios from "axios";
import * as api from "./api";
jest.mock("axios");

test("prep setup uses canonical Postgres store URLs and preserves decimal text and request key", async () => {
  axios.get.mockResolvedValue({ data: {} }); axios.post.mockResolvedValue({ data: {} });
  await api.nativePrepSetup("papa_leonis"); await api.nativePrepHistory("papa_leonis", "product-id");
  const body = { factor: "1.000000000001" }; await api.saveNativePrepProfile("papa_leonis", body, "review-key");
  expect(axios.get.mock.calls[0][0]).toContain("/api/pg/purchases/papa/prep-setup");
  expect(axios.get.mock.calls[1][0]).toContain("/api/pg/purchases/papa/prep-products/product-id/history");
  expect(axios.post.mock.calls[0]).toEqual([expect.stringContaining("/api/pg/purchases/papa/prep-unit-profiles"), body, { headers: { "Idempotency-Key": "review-key" } }]);
});
