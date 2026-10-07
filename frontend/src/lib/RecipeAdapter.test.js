jest.mock("axios", () => ({ __esModule: true, default: { get: jest.fn(), put: jest.fn(), interceptors: { request: { use: jest.fn() }, response: { use: jest.fn() } } } }));

let api, axios;
const prior = process.env.REACT_APP_USE_PG;
const pgItem = { code: "berts_original_product", controlNumber: "R01", name: "Invented shared product", vendorSkus: [] };
const recipe = { id: "abc00000-0000-4000-8000-000000000001", name: "Invented prep", recipeType: "prep", yieldQty: null, yieldUOM: null, price: null, lines: [{ sourceType: "item", itemCode: pgItem.code, qty: 2, uom: null }] };
beforeEach(() => {
  jest.resetModules(); process.env.REACT_APP_USE_PG = "true"; api = require("./api"); axios = require("axios").default;
  axios.get.mockImplementation(url => Promise.resolve({ data: url.includes("/items/") ? [pgItem] : url.includes("/dishes/") ? [recipe] : url.includes("/prep/") ? { prepStock: [], prepLogs: [] } : url.includes("/state/") ? { revision: 7 } : [] }));
  axios.put.mockResolvedValue({ data: { ok: true, revision: 8, dishes: [recipe] } });
});
afterAll(() => { if (prior === undefined) delete process.env.REACT_APP_USE_PG; else process.env.REACT_APP_USE_PG = prior; });
test("reading a shared recipe keeps canonical code and the destination store alias", async () => {
  const state = await api.fetchState("rudds");
  expect(state.dishes[0].lines[0]).toMatchObject({ itemCode: pgItem.code, controlNumber: "R01", qty: 2, uom: null });
  expect(state.dishes[0].yieldQty).toBeNull(); expect(state.dishes[0].yieldUOM).toBeNull();
});
test("saving never constructs product identity from a store prefix and local alias", async () => {
  await api.putCollection("rudds", "dishes", [{ ...recipe, lines: [{ sourceType: "item", itemCode: pgItem.code, controlNumber: "OLD", qty: 2, uom: "portion" }] }], 7);
  const [url, body, options] = axios.put.mock.calls[0];
  expect(url).toContain("/dishes/rudds"); expect(options.headers["If-Match"]).toBe('"7"');
  expect(body[0].lines[0]).toMatchObject({ item_code: pgItem.code, qty: 2, uom: "portion" });
  expect(body[0].yield_qty).toBeNull(); expect(body[0].yield_uom).toBeNull();
});
test("new lines resolve their store alias to a linked canonical product", async () => {
  await api.putCollection("rudds", "dishes", [{ ...recipe, lines: [{ sourceType: "item", controlNumber: "R01", qty: 1 }] }], 7);
  expect(axios.put.mock.calls[0][1][0].lines[0].item_code).toBe(pgItem.code);
});
test("missing or conflicting canonical identity holds before a recipe write", async () => {
  await expect(api.putCollection("rudds", "dishes", [{ ...recipe, lines: [{ sourceType: "item", itemCode: "missing", controlNumber: "R01", qty: 1 }] }], 7)).rejects.toThrow("not linked");
  expect(axios.put).not.toHaveBeenCalled();
});
test("boolean quantities cannot be converted to numeric ones by the adapter", async () => {
  await expect(api.putCollection("rudds", "dishes", [{ ...recipe, lines: [{ sourceType: "item", controlNumber: "R01", qty: true }] }], 7)).rejects.toThrow("boolean");
  expect(axios.put).not.toHaveBeenCalled();
});
