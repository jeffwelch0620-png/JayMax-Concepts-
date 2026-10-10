import React, { act } from "react";
import { createRoot } from "react-dom/client";
import { useStoreState } from "./useStoreState";
import * as api from "./api";

jest.mock("./api", () => ({ fetchState: jest.fn(), putCollection: jest.fn(), putSalesPeriod: jest.fn() }));
const empty = { items: [], dishes: [], salesPeriod: {} };
const session = { user: { role: "manager" } };
const deferred = () => { let resolve, reject; const promise = new Promise((a, b) => { resolve = a; reject = b; }); return { promise, resolve, reject }; };
let root, container, controller, errors;
function Screen({ rid = "berts", auth = session }) {
  controller = useStoreState(rid, auth, empty, errors);
  return <div>{controller.state ? JSON.stringify(controller.state) : "Loading"}</div>;
}
const render = rid => act(async () => root.render(<Screen rid={rid} />));
beforeEach(() => {
  global.IS_REACT_ACT_ENVIRONMENT = true; jest.useFakeTimers(); jest.clearAllMocks(); errors = jest.fn();
  container = document.createElement("div"); document.body.appendChild(container); root = createRoot(container);
  api.fetchState.mockImplementation(rid => Promise.resolve({ revision: rid === "berts" ? 10 : 80, items: [rid] }));
  api.putCollection.mockResolvedValue({ ok: true, revision: 11 });
});

test("retired prep with explicit unavailability loads without manufacturing empty balances", async () => {
  api.fetchState.mockResolvedValue({ revision: 10, items: [], dishes: [], prepStock: null, prepLogs: null,
    prepReadStatus: { available: false, basis: "legacy_prep_retired" },
    legacyStateCapabilities: { inventoryRetired: true, adjustmentsAvailable: false, reportingPeriodsAvailable: false } });
  await render("berts");
  expect(controller.state).not.toBeNull(); expect(controller.state.prepStock).toBeNull(); expect(controller.state.prepLogs).toBeNull();
  expect(controller.state.legacyStateCapabilities.inventoryRetired).toBe(true); expect(errors).not.toHaveBeenCalled();
});

test.each([
  {}, { prepReadStatus: { available: true, basis: "legacy_prep_retired" } },
  { prepReadStatus: { available: false, basis: "other" } },
  { prepReadStatus: { available: false, basis: "legacy_prep_retired" }, prepLogs: [] },
  { prepReadStatus: { available: false, basis: "legacy_prep_retired" }, prepStock: [], prepLogs: [] },
])("retired prep nulls require the complete confirmed unavailable contract %j", async change => {
  api.fetchState.mockResolvedValue({ revision: 10, items: [], prepStock: null, prepLogs: null, ...change });
  await render("berts"); expect(controller.state).toBeNull(); expect(errors).toHaveBeenCalled();
  await act(async () => controller.save("items", ["forbidden"])); expect(api.putCollection).not.toHaveBeenCalled();
});
afterEach(async () => { await act(async () => root.unmount()); container.remove(); jest.useRealTimers(); });

test("acknowledged writes update saved totals and pass the restaurant revision", async () => {
  await render("berts"); await act(async () => controller.save("items", ["confirmed"]));
  expect(api.putCollection).toHaveBeenCalledWith("berts", "items", ["confirmed"], 10);
  expect(container.textContent).toContain("confirmed");
  await act(async () => controller.save("dishes", ["recipe"]));
  expect(api.putCollection).toHaveBeenLastCalledWith("berts", "dishes", ["recipe"], 11);
});
test.each([409, 422, 500, "offline"])("failure %s does not change saved totals", async status => {
  await render("berts"); api.putCollection.mockRejectedValue({ response: { status }, message: "Offline" });
  let result; await act(async () => { result = await controller.save("items", ["unsaved"]); });
  expect(result).toBeNull(); expect(container.textContent).not.toContain("unsaved"); expect(container.textContent).toContain("berts"); expect(errors).toHaveBeenCalled();
});
test.each([null, {}, { ok: false, revision: 11 }, { revision: "11" }, { revision: 9 }, { revision: 11, items: "malformed" }])("unconfirmed acknowledgement %j cannot announce or apply a save", async result => {
  await render("berts"); api.putCollection.mockResolvedValue(result);
  await act(async () => expect(controller.save("items", ["bad"])).resolves.toBeNull());
  expect(container.textContent).not.toContain("bad"); expect(errors).toHaveBeenCalled();
});
test("pending writes cannot show optimistic stock or be replaced by polling", async () => {
  await render("berts"); const saving = deferred(); api.putCollection.mockReturnValue(saving.promise);
  let request; act(() => { request = controller.save("items", ["confirmed later"]); });
  await act(async () => jest.advanceTimersByTime(30000));
  expect(api.fetchState).toHaveBeenCalledTimes(1); expect(container.textContent).not.toContain("confirmed later");
  await act(async () => { saving.resolve({ revision: 11 }); await request; });
  expect(container.textContent).toContain("confirmed later");
});
test("a read started before a write cannot undo its acknowledgement", async () => {
  await render("berts"); const oldRead = deferred(); api.fetchState.mockReturnValueOnce(oldRead.promise);
  let refreshing; act(() => { refreshing = controller.refresh(); });
  await act(async () => controller.save("items", ["new saved"]));
  await act(async () => { oldRead.resolve({ revision: 10, items: ["old"] }); await refreshing; });
  expect(container.textContent).toContain("new saved"); expect(container.textContent).not.toContain('"old"');
});
test("overlapping whole-store saves are refused until the first finishes", async () => {
  await render("berts"); const saving = deferred(); api.putCollection.mockReturnValue(saving.promise);
  let first; act(() => { first = controller.save("items", ["first"]); });
  await act(async () => expect(controller.save("items", ["second"])).resolves.toBeNull());
  expect(api.putCollection).toHaveBeenCalledTimes(1);
  await act(async () => { saving.resolve({ revision: 11 }); await first; });
});
test("A to B to A discards the original A read and its errors", async () => {
  const oldA = deferred(); api.fetchState.mockReturnValueOnce(oldA.promise);
  await render("berts"); await render("rudds"); await render("berts");
  await act(async () => oldA.resolve({ revision: 99, items: ["obsolete A"] }));
  expect(container.textContent).not.toContain("obsolete A"); expect(controller.state.revision).toBe(10);
});
test("A save cannot update B, and returning A reloads after that save finishes", async () => {
  await render("berts"); const saving = deferred(); api.putCollection.mockReturnValue(saving.promise);
  const oldController = controller; let request;
  act(() => { request = controller.save("items", ["old request"]); });
  await render("rudds"); expect(controller.state.revision).toBe(80);
  await render("berts"); expect(container.textContent).toBe("Loading");
  api.fetchState.mockResolvedValueOnce({ revision: 11, items: ["fresh saved A"] });
  await act(async () => { saving.resolve({ revision: 11 }); expect(await request).toEqual({ revision: 11 }); });
  expect(container.textContent).toContain("fresh saved A");
  await act(async () => expect(oldController.save("items", ["stale callback"])).resolves.toBeNull());
  expect(api.putCollection).toHaveBeenCalledTimes(1);
});
test("late A acknowledgement cannot change B's next If-Match revision", async () => {
  await render("berts"); const saving = deferred(); api.putCollection.mockReturnValueOnce(saving.promise);
  let first; act(() => { first = controller.save("items", ["A"]); }); await render("rudds");
  await act(async () => { saving.resolve({ revision: 11 }); await first; });
  api.putCollection.mockResolvedValueOnce({ revision: 81 });
  await act(async () => controller.save("items", ["B"]));
  expect(api.putCollection).toHaveBeenLastCalledWith("rudds", "items", ["B"], 80);
});
test("dirty sales based on an older revision cannot overwrite a polled period", async () => {
  await render("berts"); api.fetchState.mockResolvedValueOnce({ revision: 11, salesPeriod: { dishSales: { toast: 20 } } });
  await act(async () => controller.refresh());
  await act(async () => expect(controller.save("salesPeriod", { dishSales: { toast: 1 } }, 10)).resolves.toBeNull());
  expect(api.putSalesPeriod).not.toHaveBeenCalled(); expect(controller.state.salesPeriod.dishSales.toast).toBe(20);
});
test("unmount discards late callbacks and clears the poll timer", async () => {
  const reading = deferred(); api.fetchState.mockReturnValueOnce(reading.promise); await render("berts");
  await act(async () => root.unmount());
  await act(async () => { reading.reject(new Error("late error")); jest.advanceTimersByTime(30000); });
  expect(errors).not.toHaveBeenCalled(); expect(api.fetchState).toHaveBeenCalledTimes(1);
});

test("malformed location collections remain unavailable instead of becoming saved data", async () => {
  api.fetchState.mockResolvedValueOnce({ revision: 10, items: "malformed" });
  await render("berts"); expect(container.textContent).toBe("Loading"); expect(errors).toHaveBeenCalled();
  expect(controller.loadError).toBeTruthy();
  await act(async () => controller.refresh()); expect(controller.state.items).toEqual(["berts"]);
  expect(controller.loadError).toBeNull();
});

test("a confirmed write cannot acknowledge drafts in a replacement login session", async () => {
  await render("berts"); const saving = deferred(); api.putCollection.mockReturnValue(saving.promise);
  let request; act(() => { request = controller.save("items", ["old session"]); });
  await act(async () => root.render(<Screen rid="berts" auth={{ user: { role: "manager" } }} />));
  await act(async () => { saving.resolve({ revision: 11 }); expect(await request).toBeNull(); });
  expect(container.textContent).not.toContain("old session");
});
test("poll failures notify once until a successful refresh resets the failure streak", async () => {
  await render("berts"); api.fetchState.mockRejectedValue(new Error("Offline"));
  await act(async () => jest.advanceTimersByTime(45000)); expect(errors).toHaveBeenCalledTimes(1);
  api.fetchState.mockResolvedValueOnce({ revision: 11, items: ["recovered"] });
  let latest; await act(async () => { latest = await controller.refresh(); });
  expect(latest).toEqual({ revision: 11, items: ["recovered"] });
  await act(async () => controller.refresh()); expect(errors).toHaveBeenCalledTimes(2);
});
test("refresh returns no retry baseline if the location changed during the read", async () => {
  await render("berts"); const pending = deferred(); api.fetchState.mockReturnValueOnce(pending.promise);
  let read; act(() => { read = controller.refresh(); }); await render("rudds");
  await act(async () => { pending.resolve({ revision: 11, items: ["old location"] }); expect(await read).toBeUndefined(); });
  expect(controller.state.revision).toBe(80);
});
test("a superseded failed poll cannot announce failure after a newer successful read", async () => {
  await render("berts"); const old = deferred(); api.fetchState.mockReturnValueOnce(old.promise);
  let pending; act(() => { pending = controller.refresh(); });
  api.fetchState.mockResolvedValueOnce({ revision: 11, items: ["fresh"] }); await act(async () => controller.refresh());
  await act(async () => { old.reject(new Error("old failed poll")); await pending; });
  expect(errors).not.toHaveBeenCalled(); expect(controller.state.items).toEqual(["fresh"]);
});
