jest.mock("axios", () => ({ __esModule: true, default: { post: jest.fn(), put: jest.fn(), get: jest.fn(), interceptors: { request: { use: jest.fn() }, response: { use: jest.fn() } } } }));

let api, axios;
const original = { pg: process.env.REACT_APP_USE_PG, purchases: process.env.REACT_APP_NATIVE_PURCHASES, counts: process.env.REACT_APP_ACTUAL_INVENTORY };
function load(pg = "true", purchases = "true", counts = "true") {
  jest.resetModules(); process.env.REACT_APP_USE_PG = pg; process.env.REACT_APP_NATIVE_PURCHASES = purchases; process.env.REACT_APP_ACTUAL_INVENTORY = counts;
  api = require("./api"); axios = require("axios").default;
  axios.post.mockResolvedValue({ data: { ok: true } }); axios.get.mockResolvedValue({ data: [] });
}
afterAll(() => {
  for (const [key, value] of Object.entries({ REACT_APP_USE_PG: original.pg, REACT_APP_NATIVE_PURCHASES: original.purchases, REACT_APP_ACTUAL_INVENTORY: original.counts })) {
    if (value === undefined) delete process.env[key]; else process.env[key] = value;
  }
});
test.each([{ rows: [] }, { rows: [{ invoiceId: "already-known", invoiceNumber: "KNOWN", vendor: "PFG" }] }])("native purchase snapshots reject even empty or already-known input without making requests", async ({ rows }) => {
  load(); await expect(api.putCollection("berts", "purchases", rows, 9)).rejects.toMatchObject({ response: { status: 410 } });
  expect(axios.get).not.toHaveBeenCalled(); expect(axios.put).not.toHaveBeenCalled(); expect(axios.post).not.toHaveBeenCalled();
});
test("old direct invoice and staff count callers cannot bypass native routing", async () => {
  load(); for (const call of [() => api.pgCreateInvoice("berts", {}), () => api.staffCounts("berts", "1234"), () => api.staffSaveCounts("berts", {}), () => api.pgStaffCounts("berts", "1234"), () => api.pgStaffSaveCounts("berts", {}), () => api.submitCounts("berts", {})]) {
    await expect(call()).rejects.toMatchObject({ response: { status: 410 } });
  }
  expect(axios.post).not.toHaveBeenCalled();
});
test("native purchase posting preserves location mapping and request identity", async () => {
  load(); const body = { received_date: "2026-10-04", lines: [] };
  await api.postPurchase("papa_leonis", "source-id", body, "unchanged-key");
  expect(axios.post).toHaveBeenCalledWith(expect.stringContaining("/purchases/papa/documents/source-id/post"), body, { headers: { "Idempotency-Key": "unchanged-key" } });
});
test("native operating reads retain the Papa location mapping", async () => {
  load(); await api.nativeOperatingSummary("papa_leonis");
  expect(axios.get).toHaveBeenCalledWith(expect.stringContaining("/purchases/papa/operating-summary"));
});
test("staff quantity submission maps Papa and keeps the issued sheet and request key", async () => {
  load(); const body = { pin: "invented", lines: [], expected_review_hash: "a".repeat(64) };
  await api.submitStaffCountDraft("papa_leonis", "issued-sheet", body, "unchanged-key");
  expect(axios.post).toHaveBeenCalledWith(expect.stringContaining("/pg/staff/papa/count-drafts/issued-sheet/submit"), body, { headers: { "Idempotency-Key": "unchanged-key" } });
});
test("native item reads keep old stock unknown while flag-off compatibility retains it", () => {
  const item = { code: "food", name: "Invented food", currentStock: 999, vendorSkus: [] };
  load(); expect(api.pgItemToMongoItem(item, "berts").currentStock).toBeNull();
  load("true", "true", "false"); expect(api.pgItemToMongoItem(item, "berts").currentStock).toBe(999);
});
test("purchase-only mode leaves legacy count entry available until actual inventory is enabled", async () => {
  load("true", "true", "false"); await api.staffSaveCounts("papa_leonis", { counts: [] });
  expect(axios.post).toHaveBeenCalledWith(expect.stringContaining("/pg/staff/papa/counts/save"), { counts: [] });
});
test.each([["true", "/pg/invoices/berts"], ["false", "/staff/berts/counts/save"]])("disabled native flags preserve earlier %s workflows", async (pg, path) => {
  load(pg, "false", "true");
  if (pg === "true") await api.pgCreateInvoice("berts", {}); else await api.staffSaveCounts("berts", {});
  expect(axios.post).toHaveBeenCalledWith(expect.stringContaining(path), {});
});
