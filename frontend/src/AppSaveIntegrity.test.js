import React, { act } from "react";
import { createRoot } from "react-dom/client";
import App from "./App";
import * as api from "./lib/api";
import { toast } from "sonner";

jest.mock("./lib/api", () => ({ currentSession: jest.fn(), fetchState: jest.fn(), putCollection: jest.fn(), putSalesPeriod: jest.fn(), SESSION_EXPIRED_EVENT: "test-expired" }));
jest.mock("sonner", () => ({ Toaster: () => null, toast: { success: jest.fn(), error: jest.fn() } }));
let mockSetupProps;
jest.mock("./components/SetupTab", () => ({ SetupTab: props => { mockSetupProps = props; return <p>Item setup</p>; } }));
jest.mock("./components/DashboardTab", () => ({ DashboardTab: props => <p data-testid="saved-items">{props.items.map(i => i.name).join(",")}</p> }));
jest.mock("./components/AiAssistant", () => ({ AiAssistant: () => null }));
let root, container;
const manager = { user: { role: "manager", locations: ["berts", "rudds"], email: "test@example.test" } };
const item = { controlNumber: "F1", name: "berts", salesTracked: true, vendorSkus: [], packCount: 1, unitQty: 1, unitUOM: "each" };
const state = (rid, revision = 10, sold = "2") => ({ revision, items: [{ ...item, name: rid }], dishes: [{ id: "dish", name: "Synthetic dish", lines: [] }], salesPeriod: { periodStart: "2026-10-01", periodEnd: "2026-10-07", dishSales: { dish: sold }, itemCounts: {} } });
const find = id => container.querySelector(`[data-testid="${id}"]`);
const click = id => act(async () => find(id).click());
beforeEach(() => {
  global.IS_REACT_ACT_ENVIRONMENT = true; jest.useFakeTimers(); jest.clearAllMocks();
  api.currentSession.mockReturnValue(manager); api.fetchState.mockImplementation(rid => Promise.resolve(state(rid, rid === "berts" ? 10 : 80)));
  container = document.createElement("div"); document.body.appendChild(container); root = createRoot(container);
});
afterEach(async () => { await act(async () => root.unmount()); container.remove(); jest.useRealTimers(); });

test("App isolates delayed saves, messages and callbacks across restaurant navigation", async () => {
  await act(async () => root.render(<App />)); await click("nav-tab-setup");
  const old = mockSetupProps; let complete, request;
  api.putCollection.mockReturnValueOnce(new Promise(resolve => { complete = resolve; }));
  act(() => { request = old.persistItems([{ ...item, name: "old saved" }]); });
  await click("location-tab-rudds"); expect(find("saved-items").textContent).toBe("rudds");
  await act(async () => { complete({ revision: 11 }); expect(await request).toBeNull(); old.showToast("old success"); });
  expect(find("saved-items").textContent).toBe("rudds"); expect(toast.success).not.toHaveBeenCalled();
  await act(async () => expect(old.persistItems([])).resolves.toBeNull()); expect(api.putCollection).toHaveBeenCalledTimes(1);
  await click("nav-tab-setup"); api.putCollection.mockResolvedValueOnce({ revision: 81 });
  await act(async () => mockSetupProps.persistItems([{ ...item, name: "new saved" }]));
  expect(api.putCollection).toHaveBeenLastCalledWith("rudds", "items", [{ ...item, name: "new saved" }], 80);
});
test("App ignores an original A fetch after A to B to A", async () => {
  let complete; api.fetchState.mockReturnValueOnce(new Promise(resolve => { complete = resolve; }));
  await act(async () => root.render(<App />)); await click("location-tab-rudds"); await click("location-tab-berts");
  await act(async () => complete(state("obsolete A", 999)));
  expect(find("saved-items").textContent).toBe("berts");
});
test("App polling cannot erase or silently rebase a dirty sales draft", async () => {
  await act(async () => root.render(<App />)); await click("nav-tab-sales");
  await act(async () => {
    const field = find("dish-sales-dish"); Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value").set.call(field, "17");
    field.dispatchEvent(new Event("input", { bubbles: true }));
  });
  // Refresh saved data before the pending debounce fires.
  api.fetchState.mockResolvedValueOnce(state("berts", 20, "99")); await click("refresh-location-data");
  expect(find("dish-sales-dish").value).toBe("17");
  await act(async () => jest.advanceTimersByTime(700));
  expect(api.putSalesPeriod).not.toHaveBeenCalled(); expect(find("dish-sales-dish").value).toBe("17"); expect(toast.success).not.toHaveBeenCalled();
  await click("nav-tab-dashboard"); await click("nav-tab-sales"); expect(find("dish-sales-dish").value).toBe("17");
});

test("leaving during legacy restore stops further writes and suppresses old-location results", async () => {
  const reader = { readAsText: jest.fn(), result: JSON.stringify({ items: [item], purchases: [] }) };
  const fileReader = jest.spyOn(window, "FileReader").mockImplementation(() => reader);
  const confirm = jest.spyOn(window, "confirm").mockReturnValue(true);
  try {
    await act(async () => root.render(<App />));
    await act(async () => {
      const field = container.querySelector('input[type="file"]');
      Object.defineProperty(field, "files", { value: [new File(["synthetic"], "test.json")] });
      field.dispatchEvent(new Event("change", { bubbles: true }));
    });
    let complete, restoration;
    api.putCollection.mockReturnValueOnce(new Promise(resolve => { complete = resolve; }));
    act(() => { restoration = reader.onload(); });
    await click("location-tab-rudds");
    await act(async () => { complete({ revision: 11 }); await restoration; });
    expect(api.putCollection).toHaveBeenCalledTimes(1); expect(find("saved-items").textContent).toBe("rudds");
    expect(toast.success).not.toHaveBeenCalled(); expect(toast.error).not.toHaveBeenCalled();
  } finally { fileReader.mockRestore(); confirm.mockRestore(); }
});
