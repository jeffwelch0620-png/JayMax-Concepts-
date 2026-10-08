jest.mock("axios", () => ({ __esModule: true, default: { get: jest.fn(), put: jest.fn(), post: jest.fn(), interceptors: { request: { use: jest.fn() }, response: { use: jest.fn() } } } }));

let api, axios;
const prior = process.env.REACT_APP_USE_PG;
const pgItem = { code: "berts_original_product", controlNumber: "R01", name: "Invented shared product", vendorSkus: [] };
const recipe = { id: "abc00000-0000-4000-8000-000000000001", name: "Invented prep", recipeType: "prep", yieldQty: null, yieldUOM: null, price: null, lines: [{ sourceType: "item", itemCode: pgItem.code, qty: 2, uom: null }] };
beforeEach(() => {
  jest.resetModules(); process.env.REACT_APP_USE_PG = "true"; api = require("./api"); axios = require("axios").default;
  axios.get.mockImplementation(url => Promise.resolve({ data: url.includes("/items/") ? [pgItem] : url.includes("/dishes/") ? [recipe] : url.includes("/prep/") ? { prepStock: [], prepLogs: [] } : url.includes("/state/") ? { revision: 7 } : [] }));
  axios.put.mockResolvedValue({ data: { ok: true, revision: 8, dishes: [recipe] } });
  axios.post.mockResolvedValue({ data: { ok: true, revision: 8, dishes: [recipe] } });
});
afterAll(() => { if (prior === undefined) delete process.env.REACT_APP_USE_PG; else process.env.REACT_APP_USE_PG = prior; });
test("reading a shared recipe keeps canonical code and the destination store alias", async () => {
  const state = await api.fetchState("rudds");
  expect(state.dishes[0].lines[0]).toMatchObject({ itemCode: pgItem.code, controlNumber: "R01", qty: 2, uom: null });
  expect(state.dishes[0].yieldQty).toBeNull(); expect(state.dishes[0].yieldUOM).toBeNull();
});
test("saving never constructs product identity from a store prefix and local alias", async () => {
  await api.putCollection("rudds", "dishes", [{ ...recipe, lines: [{ sourceType: "item", itemCode: pgItem.code, controlNumber: "OLD", qty: 2, uom: "portion" }] }], 7);
  const [url, body, options] = axios.post.mock.calls[0];
  expect(url).toContain("/dishes/rudds/changes"); expect(options.headers["If-Match"]).toBe('"7"');
  expect(body.upserts[0].lines[0]).toMatchObject({ item_code: pgItem.code, qty: 2, uom: "portion" });
  expect(body.upserts[0].yield_qty).toBeNull(); expect(body.upserts[0].yield_uom).toBeNull();
  expect(axios.put).not.toHaveBeenCalled();
});
test("new lines resolve their store alias to a linked canonical product", async () => {
  await api.putCollection("rudds", "dishes", [{ ...recipe, lines: [{ sourceType: "item", controlNumber: "R01", qty: 1 }] }], 7);
  expect(axios.post.mock.calls[0][1].upserts[0].lines[0].item_code).toBe(pgItem.code);
});
test("missing or conflicting canonical identity holds before a recipe write", async () => {
  await expect(api.putCollection("rudds", "dishes", [{ ...recipe, lines: [{ sourceType: "item", itemCode: "missing", controlNumber: "R01", qty: 1 }] }], 7)).rejects.toThrow("not linked");
  expect(axios.put).not.toHaveBeenCalled();
  expect(axios.post).not.toHaveBeenCalled();
});
test("boolean quantities cannot be converted to numeric ones by the adapter", async () => {
  await expect(api.putCollection("rudds", "dishes", [{ ...recipe, lines: [{ sourceType: "item", controlNumber: "R01", qty: true }] }], 7)).rejects.toThrow("boolean");
  expect(axios.put).not.toHaveBeenCalled();
  expect(axios.post).not.toHaveBeenCalled();
});

test("an unrelated edit retains incomplete and unlinked legacy recipes without rewriting them", async () => {
  const legacy = { ...recipe, lines: [{ sourceType: "item", itemCode: "unlinked_old_product", qty: 2, uom: null }] };
  const valid = { ...recipe, id: "abc00000-0000-4000-8000-000000000002", name: "Valid prep", yieldQty: 4, yieldUOM: "qt", lines: [{ sourceType: "item", itemCode: pgItem.code, qty: 2, uom: "portion" }] };
  axios.get.mockImplementation(url => Promise.resolve({ data: url.includes("/items/") ? [pgItem] : url.includes("/dishes/") ? [legacy, valid] : url.includes("/state/") ? { revision: 7 } : url.includes("/prep/") ? { prepStock: [], prepLogs: [] } : [] }));
  const state = await api.fetchState("rudds");
  const result = await api.putCollection("rudds", "dishes", state.dishes.map(dish => dish.id === valid.id ? { ...dish, name: "Edited prep" } : dish), 7);
  expect(axios.post.mock.calls[0][1].upserts.map(dish => dish.id)).toEqual([valid.id]);
  expect(axios.post.mock.calls[0][1].delete_ids).toEqual([]);
  expect(axios.post.mock.calls[0][2].headers["If-Match"]).toBe('"7"');
  expect(result.revision).toBe(8);
});

test("unchanged incomplete definitions produce no upserts, and removed IDs are explicit", async () => {
  const state = await api.fetchState("rudds");
  await api.putCollection("rudds", "dishes", state.dishes, 7);
  expect(axios.post.mock.calls[0][1]).toEqual({ upserts: [], delete_ids: [] });
  await api.putCollection("rudds", "dishes", [], 7);
  expect(axios.post.mock.calls[1][1]).toEqual({ upserts: [], delete_ids: [recipe.id] });
});

test("new recipe acknowledgements preserve the server's canonical identity mapping", async () => {
  axios.post.mockResolvedValue({ data: { revision: 8, dishes: [recipe], clientIds: { "prep-local": recipe.id } } });
  const result = await api.putCollection("rudds", "dishes", [{ ...recipe, id: "prep-local" }], 7);
  expect(axios.post.mock.calls[0][1].upserts[0]).toMatchObject({ id: null, client_id: "prep-local" });
  expect(result.clientIds["prep-local"]).toBe(recipe.id);
});
