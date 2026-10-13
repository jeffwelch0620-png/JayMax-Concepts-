jest.mock("axios", () => ({ __esModule: true, default: { interceptors: { request: { use: jest.fn() }, response: { use: jest.fn() } } } }));
test("locally expired sessions notify the App once and send no expired bearer", () => {
  jest.resetModules();
  const axios = require("axios").default;
  const { currentSession, SESSION_EXPIRED_EVENT } = require("./api");
  const notify = jest.fn(); window.addEventListener(SESSION_EXPIRED_EVENT, notify);
  try {
    const token = `${btoa(JSON.stringify({ exp: Math.floor(Date.now() / 1000) - 1 }))}.synthetic`;
    localStorage.setItem("jaymax_session", JSON.stringify({ token, user: { role: "manager" } }));
    const request = axios.interceptors.request.use.mock.calls[0][0];
    expect(request({ headers: {} }).headers.Authorization).toBeUndefined();
    expect(currentSession()).toBeNull(); expect(currentSession()).toBeNull();
    expect(localStorage.getItem("jaymax_session")).toBeNull(); expect(notify).toHaveBeenCalledTimes(1);
  } finally { window.removeEventListener(SESSION_EXPIRED_EVENT, notify); localStorage.clear(); }
});


test.each(["expiry", "sign-out"])("%s preserves the submitted purchase recovery copy for the original user", kind => {
  jest.resetModules();
  const { currentSession, authLogout } = require("./api");
  const { pendingPurchaseJournal, pendingPurchaseRecord } = require("./pendingPurchases");
  const originalKey = "00000000-0000-4000-8000-000000000001";
  const body = { confirmed_currency: "USD", received_date: "2026-10-12", lines: [{ line_id: "line-1", classification: "food", movement_kind: "receipt", item_code: "food", base_unit: "each", received_quantity: "1", received_unit: "each", base_units_per_received_unit: "1", movement_date: null, original_line_id: null, verified: true, note: "TEST ONLY original reviewed receipt" }] };
  const record = pendingPurchaseRecord({ id: "file-1", original_filename: "TEST ONLY.csv" },
    { id: "version-1", header: { document_id: "identity-1", document_type: "invoice" }, totals: {}, lines: [{ id: "line-1" }] }, body, originalKey);
  try {
    sessionStorage.clear(); const journal = pendingPurchaseJournal("owner-1", "berts"); journal.save(record);
    const raw = sessionStorage.getItem(sessionStorage.key(0));
    const token = `${btoa(JSON.stringify({ exp: Math.floor(Date.now() / 1000) + (kind === "expiry" ? -1 : 600) }))}.synthetic`;
    localStorage.setItem("jaymax_session", JSON.stringify({ token, user: { id: "owner-1" } }));
    if (kind === "sign-out") authLogout(); expect(currentSession()).toBeNull();
    expect(sessionStorage.getItem(sessionStorage.key(0))).toBe(raw);
    expect(pendingPurchaseJournal("owner-1", "berts").list()).toEqual([record]);
    expect(pendingPurchaseJournal("owner-2", "berts").list()).toEqual([]);
  } finally { sessionStorage.clear(); localStorage.clear(); }
});
