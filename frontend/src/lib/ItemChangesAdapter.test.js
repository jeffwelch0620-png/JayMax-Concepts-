jest.mock("axios", () => ({ __esModule: true, default: { get: jest.fn(), post: jest.fn(), put: jest.fn(), interceptors: { request: { use: jest.fn() }, response: { use: jest.fn() } } } }));
const flags = ["REACT_APP_USE_PG", "REACT_APP_NATIVE_PURCHASES", "REACT_APP_ACTUAL_INVENTORY", "REACT_APP_CATALOG_MAPPING"];
const original = Object.fromEntries(flags.map(flag => [flag, process.env[flag]]));
let api, axios;
const item = code => ({ code, controlNumber: code, name: code, baseUnit: "lb", countUnit: "case", basePerCountUnit: 20,
  packCount: 4, unitQty: 5, unitUOM: "lb", portionSize: 4, portionUOM: "oz", vendorSkus: [], active: true });
beforeEach(() => {
  jest.resetModules(); flags.forEach(flag => { process.env[flag] = "true"; });
  api = require("./api"); axios = require("axios").default;
  axios.get.mockResolvedValue({ data: [item("one"), item("two")] });
  axios.post.mockResolvedValue({ data: { ok: true, revision: 8 } });
});
afterAll(() => flags.forEach(flag => { if (original[flag] === undefined) delete process.env[flag]; else process.env[flag] = original[flag]; }));
test("an item edit submits only that item and keeps the original reviewed revision", async () => {
  const items = [item("one"), item("two")].map(value => api.pgItemToMongoItem(value, "berts"));
  await api.putCollection("berts", "items", items.map(value => value.itemCode === "two" ? { ...value, par: 9 } : value), 7);
  const [url, body, options] = axios.post.mock.calls[0];
  expect(url).toContain("/items/berts/changes"); expect(body.upserts.map(value => value.code)).toEqual(["two"]);
  expect(body.retire_codes).toEqual([]); expect(options.headers["If-Match"]).toBe('"7"'); expect(axios.put).not.toHaveBeenCalled();
});
test("omitted items are explicit retirements and retained items are not rewritten", async () => {
  await api.putCollection("berts", "items", [api.pgItemToMongoItem(item("one"), "berts")], 7);
  expect(axios.post.mock.calls[0][1]).toEqual({ upserts: [], retire_codes: ["two"] });
});

test("one unrelated edit preserves exact metadata and never submits another precise item", async () => {
  const exact = "1.123456789012345678";
  const current = [item("one"), item("two")].map(row => ({ ...row, packCount: exact, unitQty: exact,
    portionSize: exact, basePerCountUnit: exact, par: exact, vendorSkus: [{ id: row.code + "_sku", vendor: "pfg",
      vendorSku: row.code, purchaseUnit: "case", packCount: exact, unitQty: exact, unitUOM: "lb", basePerPurchaseUnit: exact }] }));
  axios.get.mockResolvedValue({ data: current });
  const edited = current.map(row => api.pgItemToMongoItem(row, "berts")).map(row => row.itemCode === "one" ? { ...row, name: "Renamed only" } : row);
  await api.putCollection("berts", "items", edited, 7);
  const body = axios.post.mock.calls[0][1];
  expect(body.upserts).toHaveLength(1); expect(body.upserts[0].code).toBe("one");
  expect(body.upserts[0]).toMatchObject({ pack_count: exact, unit_qty: exact, portion_size: exact, base_per_count_unit: exact, par: exact });
  expect(body.upserts[0].vendor_skus[0]).toMatchObject({ pack_count: exact, unit_qty: exact, base_per_purchase_unit: exact });
  expect(body.retire_codes).toEqual([]);
});
test("a stale or rejected acknowledgement is not replaced by a retry with a newer revision", async () => {
  axios.post.mockRejectedValue({ response: { status: 409 } });
  await expect(api.putCollection("berts", "items", [], 7)).rejects.toMatchObject({ response: { status: 409 } });
  expect(axios.post).toHaveBeenCalledTimes(1); expect(axios.post.mock.calls[0][2].headers["If-Match"]).toBe('"7"');
});
test("adding a verified item is not blocked by an unrelated stored unknown supplier conversion", async () => {
  const current = [item("one"), { ...item("two"), vendorSkus: [{ id: "unconfirmed", vendor: "usfoods",
    vendorSku: "two-unconfirmed", purchaseUnit: "case", basePerPurchaseUnit: null,
    packCount: null, unitQty: null, unitUOM: null }] }];
  axios.get.mockResolvedValue({ data: current });
  const newItem = { ...item("new"), vendorSkus: [{ vendor: "PFG", vendorSku: "TEST-NEW",
    packCount: 1, unitQty: 20, unitUOM: "lb", purchaseUnit: "case" }] };
  await api.putCollection("berts", "items", [...current.map(value => api.pgItemToMongoItem(value, "berts")),
    api.pgItemToMongoItem(newItem, "berts")], 7);
  const [, body, options] = axios.post.mock.calls[0];
  expect(body.upserts.map(value => value.code)).toEqual(["new"]);
  expect(body.upserts[0].vendor_skus[0].base_per_purchase_unit).toBe("20");
  expect(body.retire_codes).toEqual([]);
  expect(options.headers["If-Match"]).toBe('"7"');
  expect(axios.post).toHaveBeenCalledTimes(1);
});
