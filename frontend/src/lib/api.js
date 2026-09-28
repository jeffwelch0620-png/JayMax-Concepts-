import axios from "axios";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

export const fetchState = (rid) => axios.get(`${API}/state/${rid}`).then((r) => r.data);
export const putCollection = (rid, name, arr) => axios.put(`${API}/state/${rid}/${name}`, arr).then((r) => r.data);
export const putSalesPeriod = (rid, sp) => axios.put(`${API}/state/${rid}/salesPeriod`, sp).then((r) => r.data);
export const putAreas = (rid, areas) => axios.put(`${API}/state/${rid}/areas`, areas).then((r) => r.data);
export const completePrep = (rid, body) => axios.post(`${API}/prep/${rid}/complete`, body).then((r) => r.data);
export const applyPrepSales = (rid, dishSales) => axios.post(`${API}/prep/${rid}/apply-sales`, { dishSales }).then((r) => r.data);
export const useContainer = (rid, body) => axios.post(`${API}/prep/${rid}/use-container`, body).then((r) => r.data);
export const ownerSummary = () => axios.get(`${API}/owner/summary`).then((r) => r.data);
export const ownerPrepSummary = () => axios.get(`${API}/owner/prep-summary`).then((r) => r.data);
export const ownerOrders = () => axios.get(`${API}/owner/orders`).then((r) => r.data);
export const ownerDiscrepancies = () => axios.get(`${API}/owner/discrepancies`).then((r) => r.data);
export const ownerVendorScorecard = () => axios.get(`${API}/owner/vendor-scorecard`).then((r) => r.data);
export const orderPdfUrl = (rid, oid) => `${API}/orders/${rid}/${oid}/pdf`;
export const applyOrderPrices = (rid, oid, lines) => axios.post(`${API}/orders/${rid}/${oid}/apply-prices`, { lines }).then((r) => r.data);

export const listVendorContacts = (rid) => axios.get(`${API}/vendor-contacts/${rid}`).then((r) => r.data);
export const putVendorContact = (rid, vendor, orderEmail) => axios.put(`${API}/vendor-contacts/${rid}`, { vendor, orderEmail }).then((r) => r.data);
export const emailOrder = (rid, oid, email, by) => axios.post(`${API}/orders/${rid}/${oid}/email`, { email, by }).then((r) => r.data);
export const reorderLast = (rid, vendor, createdBy) => axios.post(`${API}/orders/${rid}/reorder-last`, { vendor, createdBy }).then((r) => r.data);

export const listOrders = (rid, status) => axios.get(`${API}/orders/${rid}`, { params: status ? { status } : {} }).then((r) => r.data);
export const createOrder = (rid, body) => axios.post(`${API}/orders/${rid}`, body).then((r) => r.data);
export const updateOrder = (rid, oid, body) => axios.put(`${API}/orders/${rid}/${oid}`, body).then((r) => r.data);
export const submitOrder = (rid, oid, by) => axios.post(`${API}/orders/${rid}/${oid}/submit`, { by }).then((r) => r.data);
export const approveOrder = (rid, oid, by) => axios.post(`${API}/orders/${rid}/${oid}/approve`, { by }).then((r) => r.data);
export const rejectOrder = (rid, oid, by, reason) => axios.post(`${API}/orders/${rid}/${oid}/reject`, { by, reason }).then((r) => r.data);
export const reopenOrder = (rid, oid, by) => axios.post(`${API}/orders/${rid}/${oid}/reopen`, { by }).then((r) => r.data);
export const sendOrder = (rid, oid, by) => axios.post(`${API}/orders/${rid}/${oid}/send`, { by }).then((r) => r.data);
export const receiveOrder = (rid, oid, by, lines, invoiceNumber) => axios.post(`${API}/orders/${rid}/${oid}/receive`, { by, lines, invoiceNumber }).then((r) => r.data);
export const deleteOrder = (rid, oid) => axios.delete(`${API}/orders/${rid}/${oid}`).then((r) => r.data);
export const aiHistory = (rid) => axios.get(`${API}/ai/history/${rid}`).then((r) => r.data);
export const aiClear = (rid) => axios.delete(`${API}/ai/history/${rid}`).then((r) => r.data);

export const getCountSession = (rid, date, track = "daily") => axios.get(`${API}/prepcount/${rid}/session`, { params: { date, track } }).then((r) => r.data);
export const saveCountEntry = (rid, sid, body) => axios.post(`${API}/prepcount/${rid}/session/${sid}/entry`, body).then((r) => r.data);
export const submitCount = (rid, sid, body) => axios.post(`${API}/prepcount/${rid}/session/${sid}/submit`, body).then((r) => r.data);
export const countHistory = (rid) => axios.get(`${API}/prepcount/${rid}/history`).then((r) => r.data);

export const getPrepList = (rid, date, track = "daily") => axios.get(`${API}/preplists/${rid}`, { params: { date, track } }).then((r) => r.data);
export const generatePrepList = (rid, date, track = "daily") => axios.post(`${API}/preplists/${rid}/generate`, { date, track }).then((r) => r.data);
export const updatePrepList = (rid, id, tasks) => axios.put(`${API}/preplists/${rid}/${id}`, { tasks }).then((r) => r.data);
export const releasePrepList = (rid, id, releasedBy) => axios.post(`${API}/preplists/${rid}/${id}/release`, { releasedBy }).then((r) => r.data);
export const completeTask = (rid, listId, taskId, body) => axios.post(`${API}/preplists/${rid}/${listId}/task/${taskId}/complete`, body).then((r) => r.data);

export const listOverrides = (rid, date) => axios.get(`${API}/prep-overrides/${rid}`, { params: { date } }).then((r) => r.data);
export const addOverride = (rid, body) => axios.post(`${API}/prep-overrides/${rid}`, body).then((r) => r.data);
export const deleteOverride = (rid, oid) => axios.delete(`${API}/prep-overrides/${rid}/${oid}`).then((r) => r.data);

export const getProjections = (rid) => axios.get(`${API}/projections/${rid}`).then((r) => r.data);
export const putProjection = (rid, body) => axios.put(`${API}/projections/${rid}`, body).then((r) => r.data);
export const prepReport = (rid, from, to) => axios.get(`${API}/reports/${rid}/prep`, { params: { from, to } }).then((r) => r.data);

export const getStaffPin = (rid) => axios.get(`${API}/staff/${rid}/pin`).then((r) => r.data);
export const setStaffPin = (rid, staffPin) => axios.post(`${API}/staff/${rid}/pin`, { staffPin }).then((r) => r.data);
export const verifyStaffPin = (rid, pin) => axios.post(`${API}/staff/verify`, { restaurantId: rid, pin }).then((r) => r.data);
export const staffPrepsheet = (rid, pin, track = "daily") => axios.post(`${API}/staff/${rid}/prepsheet`, { pin, track }).then((r) => r.data);
export const staffCompleteTask = (rid, body) => axios.post(`${API}/staff/${rid}/prepsheet/complete`, body).then((r) => r.data);

export const runParAdvisor = (rid) => axios.post(`${API}/ai/par-advisor/${rid}`).then((r) => r.data);
export const getParRecs = (rid) => axios.get(`${API}/ai/par-advisor/${rid}`).then((r) => r.data);
export const applyParRec = (rid, recId) => axios.post(`${API}/ai/par-advisor/${rid}/${recId}/apply`).then((r) => r.data);
export const dismissParRec = (rid, recId) => axios.post(`${API}/ai/par-advisor/${rid}/${recId}/dismiss`).then((r) => r.data);

export const listPrepItems = (rid, track = "daily") => axios.get(`${API}/prep-items/${rid}`, { params: { track } }).then((r) => r.data);
export const createPrepItem = (rid, body) => axios.post(`${API}/prep-items/${rid}`, body).then((r) => r.data);
export const updatePrepItem = (rid, pid, body) => axios.put(`${API}/prep-items/${rid}/${pid}`, body).then((r) => r.data);
export const deletePrepItem = (rid, pid) => axios.delete(`${API}/prep-items/${rid}/${pid}`).then((r) => r.data);
export const addItemToList = (rid, listId, body) => axios.post(`${API}/preplists/${rid}/${listId}/add-item`, body).then((r) => r.data);

export async function streamChat(rid, message, { onDelta, onError, onDone }) {
  const res = await fetch(`${API}/ai/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ restaurantId: rid, message }),
  });
  if (!res.ok || !res.body) {
    onError?.(`Request failed (${res.status})`);
    onDone?.();
    return;
  }
  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buf = "";
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    buf += decoder.decode(value, { stream: true });
    const parts = buf.split("\n\n");
    buf = parts.pop() || "";
    for (const part of parts) {
      const line = part.trim();
      if (!line.startsWith("data:")) continue;
      const payload = line.slice(5).trim();
      if (payload === "[DONE]") continue;
      try {
        const obj = JSON.parse(payload);
        if (obj.t) onDelta?.(obj.t);
        if (obj.error) onError?.(obj.error);
      } catch { /* ignore partial frames */ }
    }
  }
  onDone?.();
}
