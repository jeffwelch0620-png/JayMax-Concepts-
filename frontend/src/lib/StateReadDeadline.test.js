jest.mock("axios", () => ({ __esModule: true, default: { get: jest.fn(), post: jest.fn(), interceptors: { request: { use: jest.fn() }, response: { use: jest.fn() } } } }));

const original = { pg: process.env.REACT_APP_USE_PG, purchases: process.env.REACT_APP_NATIVE_PURCHASES };
let api, axios, timeout, message;
const deferred = () => { let resolve, reject; const promise = new Promise((a, b) => { resolve = a; reject = b; }); return { promise, resolve, reject }; };
const response = url => ({ data: url.includes("/api/state/") ? { revision: 10, areas: [] }
  : url.includes("/prep/") ? { prepStock: null, prepLogs: null } : [] });
const flush = async () => { for (let i = 0; i < 12; i++) await Promise.resolve(); };
function load(pg = "true", purchases = "true") {
  jest.resetModules(); process.env.REACT_APP_USE_PG = pg; process.env.REACT_APP_NATIVE_PURCHASES = purchases;
  api = require("./api"); axios = require("axios").default;
  ({ STATE_READ_TIMEOUT_MS: timeout, STATE_READ_TIMEOUT_MESSAGE: message } = require("./stateRead"));
  axios.get.mockImplementation(url => Promise.resolve(response(url)));
}
beforeEach(() => { jest.useFakeTimers(); load(); });
afterEach(() => { jest.clearAllTimers(); jest.useRealTimers(); });
afterAll(() => {
  for (const [key, value] of Object.entries({ REACT_APP_USE_PG: original.pg, REACT_APP_NATIVE_PURCHASES: original.purchases })) {
    if (value === undefined) delete process.env[key]; else process.env[key] = value;
  }
});

test("the full native read shares cancellation and clears its deadline after success", async () => {
  await expect(api.fetchState("berts")).resolves.toMatchObject({ revision: 10, items: [], dishes: [], prepStock: null });
  expect(axios.get).toHaveBeenCalledTimes(4);
  const signals = axios.get.mock.calls.map(([, options]) => options.signal);
  expect(signals.every(signal => signal === signals[0])).toBe(true);
  expect(signals[0].aborted).toBe(true); expect(jest.getTimerCount()).toBe(0);
});

test("legacy-only state reads are bounded without requesting PostgreSQL children", async () => {
  load("false"); await expect(api.fetchState("berts")).resolves.toEqual({ revision: 10, areas: [] });
  expect(axios.get).toHaveBeenCalledTimes(1); expect(jest.getTimerCount()).toBe(0);
});

test("a never-settling initial transport rejects and is cancelled at the deadline", async () => {
  axios.get.mockReturnValue(new Promise(() => {}));
  const result = api.fetchState("berts").catch(error => error);
  jest.advanceTimersByTime(timeout); await flush();
  expect(await result).toEqual(new Error(message));
  expect(axios.get.mock.calls[0][1].signal.aborted).toBe(true); expect(axios.get).toHaveBeenCalledTimes(1);
});

test.each(["items", "dishes", "prep", "invoices"])("a stalled PostgreSQL %s child rejects the complete read", async child => {
  if (child === "invoices") load("true", "false");
  axios.get.mockImplementation(url => url.includes(`/pg/${child}/`) ? new Promise(() => {}) : Promise.resolve(response(url)));
  const result = api.fetchState("berts").catch(error => error); await flush();
  expect(axios.get).toHaveBeenCalledTimes(child === "invoices" ? 5 : 4);
  jest.advanceTimersByTime(timeout); await flush(); expect(await result).toEqual(new Error(message));
  expect(axios.get.mock.calls.every(([, options]) => options.signal.aborted)).toBe(true);
});

test("the deadline does not restart when the initial read starts PostgreSQL children", async () => {
  const initial = deferred(); axios.get.mockImplementation(url => url.includes("/api/state/") ? initial.promise : new Promise(() => {}));
  const result = api.fetchState("berts").catch(error => error);
  jest.advanceTimersByTime(timeout - 15000); initial.resolve(response("/api/state/berts")); await flush();
  expect(axios.get).toHaveBeenCalledTimes(4);
  jest.advanceTimersByTime(15000); await flush(); expect(await result).toEqual(new Error(message));
});

test("an initial transport completing after timeout cannot launch child reads", async () => {
  const initial = deferred(); axios.get.mockReturnValue(initial.promise);
  const result = api.fetchState("berts").catch(error => error);
  jest.advanceTimersByTime(timeout); await flush(); expect(await result).toEqual(new Error(message));
  initial.resolve(response("/api/state/berts")); await flush();
  expect(axios.get).toHaveBeenCalledTimes(1); expect(jest.getTimerCount()).toBe(0);
});

test("one failed child cancels its siblings while preserving the original failure", async () => {
  axios.get.mockImplementation(url => url.includes("/api/state/") ? Promise.resolve(response(url))
    : url.includes("/items/") ? Promise.reject(new Error("Items unavailable")) : new Promise(() => {}));
  await expect(api.fetchState("berts")).rejects.toThrow("Items unavailable");
  expect(axios.get.mock.calls.every(([, options]) => options.signal.aborted)).toBe(true);
  expect(jest.getTimerCount()).toBe(0);
});

test("an abort-aware transport retains the timeout diagnosis instead of a cancellation error", async () => {
  axios.get.mockImplementation((url, options) => new Promise((resolve, reject) => {
    options.signal.addEventListener("abort", () => reject(new Error("Transport cancelled")));
  }));
  const result = api.fetchState("berts").catch(error => error);
  jest.advanceTimersByTime(timeout); await flush(); expect(await result).toEqual(new Error(message));
});

test("posting a purchase retains its request identity without the state-read deadline", async () => {
  axios.post.mockResolvedValue({ data: { batch_id: "fictional-existing-batch" } });
  const body = { received_date: "2026-10-10", lines: [] };
  await api.postPurchase("berts", "fictional-document", body, "fictional-stable-key");
  expect(axios.post).toHaveBeenCalledWith(expect.stringContaining("/documents/fictional-document/post"), body,
    { headers: { "Idempotency-Key": "fictional-stable-key" } });
  expect(jest.getTimerCount()).toBe(0);
});
