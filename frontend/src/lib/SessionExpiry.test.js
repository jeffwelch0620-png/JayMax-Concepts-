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
