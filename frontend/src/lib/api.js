import axios from "axios";
import { calcPortionsPerUnit, preferredSku } from "./calc";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;
// Supabase migration target -- see docs/SUPABASE_MIGRATION_PLAN.md. Store ids here
// are berts/rudds/papa/comm (from the `stores` table), NOT the Mongo-side
// berts/rudds/papa_leonis -- callers must map before calling any pg* function.
const PG_API = `${API}/pg`;
// Chunk 2 cutover flag: when true, the Prep functions below route through
// /api/pg/* (translating the Mongo-side restaurantId to the Postgres store id)
// instead of the legacy Mongo-backed routes. On by default (Supabase is the only
// database); only an explicit REACT_APP_USE_PG=false build uses the legacy routes.
const USE_PG = process.env.REACT_APP_USE_PG !== "false";
export const isPostgres = USE_PG;
export const nativePurchasesEnabled = USE_PG && process.env.REACT_APP_NATIVE_PURCHASES === "true";
export const actualInventoryEnabled = nativePurchasesEnabled && process.env.REACT_APP_ACTUAL_INVENTORY === "true";
export const catalogMappingEnabled = actualInventoryEnabled && process.env.REACT_APP_CATALOG_MAPPING === "true";
export const orderWorkflowEnabled = catalogMappingEnabled && process.env.REACT_APP_ORDER_WORKFLOW === "true";
export const supplierContactsEnabled = orderWorkflowEnabled && process.env.REACT_APP_SUPPLIER_CONTACTS === "true";
export const supplierContacts = rid => axios.get(`${PG_API}/purchases/${pgStoreId(rid)}/supplier-contacts`).then(r => r.data);
export const saveSupplierContact = (rid, vendor, body, version, key) => axios.put(`${PG_API}/purchases/${pgStoreId(rid)}/supplier-contacts/${encodeURIComponent(vendor)}`, body, { headers: { ...revisionHeaders(version), "Idempotency-Key": key } }).then(r => r.data);
export const createVersionedOrder = (rid, body, key) => axios.post(`${PG_API}/purchases/${pgStoreId(rid)}/order-drafts`, body, { headers: { "Idempotency-Key": key } }).then(r => r.data);
export const orderCommand = (rid, ref, body, version, key) => axios.post(`${PG_API}/purchases/${pgStoreId(rid)}/orders/${ref}/commands`, body, { headers: { ...revisionHeaders(version), "Idempotency-Key": key } }).then(r => r.data);
export const editVersionedOrder = (rid, ref, body, version, key) => axios.put(`${PG_API}/purchases/${pgStoreId(rid)}/order-drafts/${ref}`, body, { headers: { ...revisionHeaders(version), "Idempotency-Key": key } }).then(r => r.data);
export const supplierPriceReview = (rid, sku, offset = 0) => axios.get(`${PG_API}/purchases/${pgStoreId(rid)}/supplier-prices/${sku}`, { params: { offset } }).then(r => r.data);
export const adoptSupplierPrice = (rid, sku, body, key) => axios.post(`${PG_API}/purchases/${pgStoreId(rid)}/supplier-prices/${sku}/adoptions`, body, { headers: { "Idempotency-Key": key } }).then(r => r.data);
export const sharedCatalog = rid => axios.get(`${PG_API}/catalog/${pgStoreId(rid)}`).then(r => r.data);
export const linkSharedItem = (rid, body, revision) => axios.post(`${PG_API}/catalog/${pgStoreId(rid)}/links`, body, { headers: revisionHeaders(revision) }).then(r => r.data);
export const prepSetupEnabled = nativePurchasesEnabled && process.env.REACT_APP_PREP_SETUP === "true";
export const prepPlanningEnabled = prepSetupEnabled && catalogMappingEnabled && process.env.REACT_APP_PREP_PLANNING === "true";
export const prepDayTasksEnabled = prepPlanningEnabled && process.env.REACT_APP_PREP_BATCHES === "true" && process.env.REACT_APP_PREP_OBSERVATIONS === "true" && process.env.REACT_APP_PREP_DAY_TASKS === "true";
export const prepExecutionEnabled = prepDayTasksEnabled && process.env.REACT_APP_PREP_EXECUTION === "true";
export const prepExecution = (rid, day, track) => axios.get(`${purchaseUrl(rid)}/prep-execution/${day}`, { params: { track } }).then(r => r.data);
export const previewPrepExecution = (rid, day, track, body, version) => axios.post(`${purchaseUrl(rid)}/prep-execution/${day}/preview`, body, { params: { track }, headers: revisionHeaders(version) }).then(r => r.data);
export const savePrepExecution = (rid, day, track, body, version, key) => axios.post(`${purchaseUrl(rid)}/prep-execution/${day}/commands`, body, { params: { track }, headers: { ...revisionHeaders(version), "Idempotency-Key": key } }).then(r => r.data);
export const prepDayDraft = (rid, day, track) => axios.get(`${purchaseUrl(rid)}/prep-day-drafts/${day}`, { params: { track } }).then(r => r.data);
export const previewPrepDayDraft = (rid, day, body, version) => axios.post(`${purchaseUrl(rid)}/prep-day-drafts/${day}/preview`, body, { headers: revisionHeaders(version) }).then(r => r.data);
export const savePrepDayDraft = (rid, day, body, version, key) => axios.put(`${purchaseUrl(rid)}/prep-day-drafts/${day}`, body, { headers: { ...revisionHeaders(version), "Idempotency-Key": key } }).then(r => r.data);
export const prepPlanning = rid => axios.get(`${purchaseUrl(rid)}/prep-planning`).then(r => r.data);
export const savePrepPlan = (rid, product, body, version, key) => axios.put(`${purchaseUrl(rid)}/prep-planning/${encodeURIComponent(product)}`, body, { headers: { ...revisionHeaders(version), "Idempotency-Key": key } }).then(r => r.data);
export const prepBatchesEnabled = prepSetupEnabled && process.env.REACT_APP_PREP_BATCHES === "true";
export const prepObservationsEnabled = prepBatchesEnabled && process.env.REACT_APP_PREP_OBSERVATIONS === "true";
const retiredWorkflow = message => Promise.reject(Object.assign(new Error(message), { response: { status: 410, data: { detail: message } } }));
const MONGO_TO_PG_STORE = { berts: "berts", rudds: "rudds", papa_leonis: "papa" };
const pgStoreId = (rid) => MONGO_TO_PG_STORE[rid] || rid;
export const purchaseItems = (rid) => pgListItems(pgStoreId(rid));
const purchaseUrl = (rid) => `${PG_API}/purchases/${pgStoreId(rid)}`;
export const purchaseCapabilities = (rid) => axios.get(`${purchaseUrl(rid)}/capabilities`).then(r => r.data);
export const purchaseFiles = (rid, offset = 0) => axios.get(`${purchaseUrl(rid)}/files`, { params: { offset } }).then(r => r.data);
export const purchaseFile = (rid, id) => axios.get(`${purchaseUrl(rid)}/files/${id}`).then(r => r.data);
export const purchaseFileDocument = (rid, id) => axios.get(`${purchaseUrl(rid)}/documents/${id}`).then(r => r.data);
export const capturePurchase = (rid, file, key) => {
  const form = new FormData(); form.append("file", file);
  return axios.post(`${purchaseUrl(rid)}/files`, form, { headers: { "Idempotency-Key": key } }).then(r => r.data);
};
export const postPurchase = (rid, id, body, key) => axios.post(`${purchaseUrl(rid)}/documents/${id}/post`, body, { headers: { "Idempotency-Key": key } }).then(r => r.data);
export const purchaseHistory = (rid) => axios.get(`${purchaseUrl(rid)}/history`).then(r => r.data);
export const nativeOperatingSummary = (rid) => axios.get(`${purchaseUrl(rid)}/operating-summary`).then(r => r.data);
export const previewPurchaseCorrection = (rid, id, body) => axios.post(`${purchaseUrl(rid)}/documents/${id}/correction-preview`, body).then(r => r.data);
export const correctPurchase = (rid, id, body, key) => axios.post(`${purchaseUrl(rid)}/documents/${id}/correct`, body, { headers: { "Idempotency-Key": key } }).then(r => r.data);
export const purchaseCorrections = (rid, id) => axios.get(`${purchaseUrl(rid)}/documents/${id}/corrections`).then(r => r.data);
export const purchaseRawRows = (rid, id, offset = 0) => axios.get(`${purchaseUrl(rid)}/files/${id}/rows`, { params: { offset } }).then(r => r.data);
export const purchaseSource = (rid, id) => axios.get(`${purchaseUrl(rid)}/files/${id}/source`, { responseType: "blob" }).then(r => r.data);
export const purchaseVendors = (rid) => axios.get(`${purchaseUrl(rid)}/vendors`).then(r => r.data);
export const capturePurchaseSource = (rid, file, key) => {
  const form = new FormData(); form.append("file", file);
  return axios.post(`${purchaseUrl(rid)}/sources`, form, { headers: { "Idempotency-Key": key } }).then(r => r.data);
};
export const captureManualPurchase = (rid, body, key) => axios.post(`${purchaseUrl(rid)}/manual-records`, body, { headers: { "Idempotency-Key": key } }).then(r => r.data);
export const nativeUnitSetup = rid => axios.get(`${purchaseUrl(rid)}/unit-setup`).then(r => r.data);
export const saveNativeUnitProfile = (rid, body, key) => axios.post(`${purchaseUrl(rid)}/unit-profiles`, body, { headers: { "Idempotency-Key": key } }).then(r => r.data);
export const nativePrepSetup = rid => axios.get(`${purchaseUrl(rid)}/prep-setup`).then(r => r.data);
export const nativePrepBatchSetup = rid => axios.get(`${purchaseUrl(rid)}/prep-batches/setup`).then(r => r.data);
export const nativePrepObservationSetup = rid => axios.get(`${purchaseUrl(rid)}/prep-observations/setup`).then(r => r.data);
export const nativePrepPeriodCounts = rid => axios.get(`${purchaseUrl(rid)}/prep-periods/counts`).then(r => r.data);
export const nativePrepOpeningSetup = rid => axios.get(`${purchaseUrl(rid)}/prep-openings/setup`).then(r => r.data);
export const previewNativePrepOpening = (rid, body) => axios.post(`${purchaseUrl(rid)}/prep-openings/preview`, body).then(r => r.data);
export const saveNativePrepOpening = (rid, body, key) => axios.post(`${purchaseUrl(rid)}/prep-openings`, body, { headers: { "Idempotency-Key": key } }).then(r => r.data);
export const previewNativePrepOpeningVoid = (rid, event, body) => axios.post(`${purchaseUrl(rid)}/prep-openings/${encodeURIComponent(event)}/void-preview`, body).then(r => r.data);
export const voidNativePrepOpening = (rid, event, body, key) => axios.post(`${purchaseUrl(rid)}/prep-openings/${encodeURIComponent(event)}/void`, body, { headers: { "Idempotency-Key": key } }).then(r => r.data);
export const previewNativePrepPeriod = (rid, body) => axios.post(`${purchaseUrl(rid)}/prep-periods/preview`, body).then(r => r.data);
export const nativePrepPeriodJournal = rid => axios.get(`${purchaseUrl(rid)}/prep-period-journal`).then(r => r.data);
export const previewNativePrepPeriodClose = (rid, body) => axios.post(`${purchaseUrl(rid)}/prep-period-journal/preview`, body).then(r => r.data);
export const saveNativePrepPeriodClose = (rid, body, key) => axios.post(`${purchaseUrl(rid)}/prep-period-journal`, body, { headers: { "Idempotency-Key": key } }).then(r => r.data);
export const previewNativePrepPeriodReopen = (rid, body) => axios.post(`${purchaseUrl(rid)}/prep-period-journal/reopen-preview`, body).then(r => r.data);
export const saveNativePrepPeriodReopen = (rid, body, key) => axios.post(`${purchaseUrl(rid)}/prep-period-journal/reopen`, body, { headers: { "Idempotency-Key": key } }).then(r => r.data);
export const nativePrepObservationHistory = (rid, purpose, root) => axios.get(`${purchaseUrl(rid)}/prep-observations/${encodeURIComponent(purpose)}/${encodeURIComponent(root)}/history`).then(r => r.data);
export const previewNativePrepObservation = (rid, purpose, body) => axios.post(`${purchaseUrl(rid)}/prep-observations/${encodeURIComponent(purpose)}/preview`, body).then(r => r.data);
export const saveNativePrepObservation = (rid, purpose, body, key) => axios.post(`${purchaseUrl(rid)}/prep-observations/${encodeURIComponent(purpose)}`, body, { headers: { "Idempotency-Key": key } }).then(r => r.data);
export const previewNativePrepObservationChange = (rid, purpose, id, body) => axios.post(`${purchaseUrl(rid)}/prep-observations/${encodeURIComponent(purpose)}/${encodeURIComponent(id)}/change-preview`, body).then(r => r.data);
export const saveNativePrepObservationChange = (rid, purpose, id, body, key) => axios.post(`${purchaseUrl(rid)}/prep-observations/${encodeURIComponent(purpose)}/${encodeURIComponent(id)}/changes`, body, { headers: { "Idempotency-Key": key } }).then(r => r.data);
export const nativePrepBatchHistory = (rid, root) => axios.get(`${purchaseUrl(rid)}/prep-batches/${encodeURIComponent(root)}/history`).then(r => r.data);
export const previewNativePrepBatch = (rid, body) => axios.post(`${purchaseUrl(rid)}/prep-batches/preview`, body).then(r => r.data);
export const saveNativePrepBatch = (rid, body, key) => axios.post(`${purchaseUrl(rid)}/prep-batches`, body, { headers: { "Idempotency-Key": key } }).then(r => r.data);
export const previewNativePrepBatchChange = (rid, id, body) => axios.post(`${purchaseUrl(rid)}/prep-batches/${encodeURIComponent(id)}/change-preview`, body).then(r => r.data);
export const saveNativePrepBatchChange = (rid, id, body, key) => axios.post(`${purchaseUrl(rid)}/prep-batches/${encodeURIComponent(id)}/changes`, body, { headers: { "Idempotency-Key": key } }).then(r => r.data);
export const nativePrepHistory = (rid, id) => axios.get(`${purchaseUrl(rid)}/prep-products/${encodeURIComponent(id)}/history`).then(r => r.data);
export const saveNativePrepProduct = (rid, body, key) => axios.post(`${purchaseUrl(rid)}/prep-products`, body, { headers: { "Idempotency-Key": key } }).then(r => r.data);
export const saveNativePrepProfile = (rid, body, key) => axios.post(`${purchaseUrl(rid)}/prep-unit-profiles`, body, { headers: { "Idempotency-Key": key } }).then(r => r.data);
export const previewNativePrepRecipe = (rid, body) => axios.post(`${purchaseUrl(rid)}/prep-recipes/preview`, body).then(r => r.data);
export const saveNativePrepRecipe = (rid, body, key) => axios.post(`${purchaseUrl(rid)}/prep-recipes`, body, { headers: { "Idempotency-Key": key } }).then(r => r.data);
export const nativeOrderReceiptSetup = (rid, ref) => axios.get(`${purchaseUrl(rid)}/orders/${encodeURIComponent(ref)}/receipt-setup`).then(r => r.data);
export const previewNativeOrderReceipt = (rid, ref, body) => axios.post(`${purchaseUrl(rid)}/orders/${encodeURIComponent(ref)}/receipt-preview`, body).then(r => r.data);
export const linkNativeOrderReceipt = (rid, ref, body, key) => axios.post(`${purchaseUrl(rid)}/orders/${encodeURIComponent(ref)}/receipts`, body, { headers: { "Idempotency-Key": key } }).then(r => r.data);
const reconciliationUrl = (rid, ref, receipt) => `${purchaseUrl(rid)}/orders/${encodeURIComponent(ref)}/receipts/${encodeURIComponent(receipt)}`;
export const nativeOrderReconciliationSetup = (rid, ref, receipt) => axios.get(`${reconciliationUrl(rid, ref, receipt)}/reconciliation-setup`).then(r => r.data);
export const previewNativeOrderReconciliation = (rid, ref, receipt, body) => axios.post(`${reconciliationUrl(rid, ref, receipt)}/reconciliation-preview`, body).then(r => r.data);
export const reconcileNativeOrderReceipt = (rid, ref, receipt, body, key) => axios.post(`${reconciliationUrl(rid, ref, receipt)}/reconciliations`, body, { headers: { "Idempotency-Key": key } }).then(r => r.data);
const actualUrl = (rid) => `${PG_API}/actual-inventory/${pgStoreId(rid)}`;
export const actualSetup = (rid) => axios.get(`${actualUrl(rid)}/setup`).then(r => r.data);
export const actualScopeDetails = (rid, id) => axios.get(`${actualUrl(rid)}/scopes/${id}`).then(r => r.data);
export const actualScope = (rid, body, key) => axios.post(`${actualUrl(rid)}/scope`, body, { headers: { "Idempotency-Key": key } }).then(r => r.data);
export const actualCounts = (rid) => axios.get(`${actualUrl(rid)}/counts`).then(r => r.data);
export const actualCount = (rid, id) => axios.get(`${actualUrl(rid)}/counts/${id}`).then(r => r.data);
export const actualSaveCount = (rid, body, key) => axios.post(`${actualUrl(rid)}/counts`, body, { headers: { "Idempotency-Key": key } }).then(r => r.data);
export const staffCountSheets = (rid) => axios.get(`${actualUrl(rid)}/staff-sheets`).then(r => r.data);
export const issueStaffCountSheet = (rid, body, key) => axios.post(`${actualUrl(rid)}/staff-sheets`, body, { headers: { "Idempotency-Key": key } }).then(r => r.data);
export const decideStaffCountSheet = (rid, id, body, key) => axios.post(`${actualUrl(rid)}/staff-sheets/${id}/decision`, body, { headers: { "Idempotency-Key": key } }).then(r => r.data);
export const staffCountDrafts = (rid, pin) => axios.post(`${PG_API}/staff/${pgStoreId(rid)}/count-drafts`, { pin }).then(r => r.data);
export const submitStaffCountDraft = (rid, id, body, key) => axios.post(`${PG_API}/staff/${pgStoreId(rid)}/count-drafts/${id}/submit`, body, { headers: { "Idempotency-Key": key } }).then(r => r.data);
export const actualReport = (rid, opening, closing) => axios.get(`${actualUrl(rid)}/report`, { params: { opening, closing } }).then(r => r.data);
export const actualClose = (rid, body, key) => axios.post(`${actualUrl(rid)}/close`, body, { headers: { "Idempotency-Key": key } }).then(r => r.data);
export const actualClosed = (rid) => axios.get(`${actualUrl(rid)}/closed-periods`).then(r => r.data);
export const actualReopenPreview = (rid, id) => axios.get(`${actualUrl(rid)}/reopen-preview/${id}`).then(r => r.data);
export const actualReopen = (rid, body, key) => axios.post(`${actualUrl(rid)}/reopen`, body, { headers: { "Idempotency-Key": key } }).then(r => r.data);
export const actualHandoffPreview = (rid, id, target) => axios.get(`${actualUrl(rid)}/scope-handoff-preview/${id}`, { params: { target_count: target } }).then(r => r.data);
export const actualAcceptHandoff = (rid, body, key) => axios.post(`${actualUrl(rid)}/scope-handoffs`, body, { headers: { "Idempotency-Key": key } }).then(r => r.data);
export const actualHandoffs = (rid) => axios.get(`${actualUrl(rid)}/scope-handoffs`).then(r => r.data);
const TOKEN_KEY = "jaymax_session";
// Session tokens are "<base64url JSON payload>.<signature>" with an `exp` (unix seconds).
function tokenExpired(token) {
  try {
    const raw = token.split(".")[0].replace(/-/g, "+").replace(/_/g, "/");
    const { exp } = JSON.parse(atob(raw + "=".repeat((4 - (raw.length % 4)) % 4)));
    return !exp || exp * 1000 <= Date.now();
  } catch { return true; }
}
const session = () => {
  try {
    const s = JSON.parse(localStorage.getItem(TOKEN_KEY) || "null");
    if (s?.token && tokenExpired(s.token)) { endSession(); return null; }
    return s;
  } catch { return null; }
};
// Fired when the server rejects the stored session (expired, or the server's AUTH_SECRET
// changed). App.js listens and returns to the login screen instead of retrying forever.
export const SESSION_EXPIRED_EVENT = "jaymax:session-expired";
export function endSession() {
  if (!localStorage.getItem(TOKEN_KEY)) return;
  localStorage.removeItem(TOKEN_KEY);
  window.dispatchEvent(new Event(SESSION_EXPIRED_EVENT));
}
axios.interceptors.request.use((config) => {
  const token = session()?.token;
  if (token) config.headers.Authorization = ["Bearer", token].join(" ");
  return config;
});
axios.interceptors.response.use(undefined, (error) => {
  const sentToken = String(error?.config?.headers?.Authorization || "").startsWith("Bearer ");
  if (error?.response?.status === 401 && sentToken) endSession();
  return Promise.reject(error);
});

export const authLogin = (email, password) => axios.post(`${API}/auth/login`, { email, password }).then((r) => {
  localStorage.setItem(TOKEN_KEY, JSON.stringify(r.data));
  return r.data;
});
// Email/password logins (owner only).
export const listLogins = () => axios.get(`${API}/auth/users`).then((r) => r.data);
export const createLogin = (body) => axios.post(`${API}/auth/users`, body).then((r) => r.data);
export const resetLoginPassword = (id, password) => axios.put(`${API}/auth/users/${id}/password`, { password }).then((r) => r.data);
export const deleteLogin = (id) => axios.delete(`${API}/auth/users/${id}`).then((r) => r.data);
export const authLogout = () => localStorage.removeItem(TOKEN_KEY);
export const currentSession = () => session();
export const storeSession = (data) => { localStorage.setItem(TOKEN_KEY, JSON.stringify(data)); return data; };

export const fetchState = (rid) => axios.get(`${API}/state/${rid}`).then((r) => USE_PG
  ? Promise.all([pgFetchItemsAndPurchases(rid), pgFetchDishes(rid), pgFetchPrepState(rid)])
    .then(([pg, dishes, prep]) => ({ ...r.data, ...pg, ...prep, dishes: dishes.map(d => pgDishToMongoDish(d, rid, pg.items)) }))
  : r.data);
const revisionHeaders = (revision) => revision == null ? {} : { "If-Match": `"${revision}"` };
export const putCollection = (rid, name, arr, revision) => {
  if (nativePurchasesEnabled && name === "purchases") return retiredWorkflow("Retain this invoice in Invoice Master, then review its received date, quantities and costs before posting.");
  if (USE_PG && name === "items") return pgPutItems(rid, arr, revision);
  if (USE_PG && name === "purchases") return pgPutPurchases(rid, arr, revision);
  if (USE_PG && name === "dishes") return pgPutDishes(rid, arr, revision);
  return axios.put(`${API}/state/${rid}/${name}`, arr, { headers: revisionHeaders(revision) }).then((r) => r.data);
};
export const putSalesPeriod = (rid, sp, revision) => axios.put(`${API}/state/${rid}/salesPeriod`, sp, { headers: revisionHeaders(revision) }).then((r) => r.data);
export const putAreas = (rid, areas, revision) => axios.put(`${API}/state/${rid}/areas`, areas, { headers: revisionHeaders(revision) }).then((r) => r.data);
export const completePrep = (rid, body) => axios.post(`${API}/prep/${rid}/complete`, body).then((r) => r.data);
export const applyPrepSales = (rid, dishSales) => USE_PG ? pgApplyPrepSales(pgStoreId(rid), dishSales) : axios.post(`${API}/prep/${rid}/apply-sales`, { dishSales }).then((r) => r.data);
export const useContainer = (rid, body) => USE_PG ? pgUseContainer(pgStoreId(rid), body) : axios.post(`${API}/prep/${rid}/use-container`, body).then((r) => r.data);
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

export const getCountSession = (rid, date, track = "daily") => USE_PG ? pgGetCountSession(pgStoreId(rid), date, track) : axios.get(`${API}/prepcount/${rid}/session`, { params: { date, track } }).then((r) => r.data);
export const saveCountEntry = (rid, sid, body) => USE_PG ? pgSaveCountEntry(pgStoreId(rid), sid, body) : axios.post(`${API}/prepcount/${rid}/session/${sid}/entry`, body).then((r) => r.data);
export const submitCount = (rid, sid, body) => USE_PG ? pgSubmitCount(pgStoreId(rid), sid, body) : axios.post(`${API}/prepcount/${rid}/session/${sid}/submit`, body).then((r) => r.data);
export const countHistory = (rid) => USE_PG ? pgCountHistory(pgStoreId(rid)) : axios.get(`${API}/prepcount/${rid}/history`).then((r) => r.data);

export const getPrepList = (rid, date, track = "daily") => USE_PG ? pgGetPrepList(pgStoreId(rid), date, track) : axios.get(`${API}/preplists/${rid}`, { params: { date, track } }).then((r) => r.data);
export const generatePrepList = (rid, date, track = "daily") => USE_PG ? pgGeneratePrepList(pgStoreId(rid), date, track) : axios.post(`${API}/preplists/${rid}/generate`, { date, track }).then((r) => r.data);
export const updatePrepList = (rid, id, tasks) => USE_PG ? pgUpdatePrepList(pgStoreId(rid), id, tasks) : axios.put(`${API}/preplists/${rid}/${id}`, { tasks }).then((r) => r.data);
export const releasePrepList = (rid, id, releasedBy) => USE_PG ? pgReleasePrepList(pgStoreId(rid), id, releasedBy) : axios.post(`${API}/preplists/${rid}/${id}/release`, { releasedBy }).then((r) => r.data);
export const completeTask = (rid, listId, taskId, body) => USE_PG ? pgCompleteTask(pgStoreId(rid), listId, taskId, body) : axios.post(`${API}/preplists/${rid}/${listId}/task/${taskId}/complete`, body).then((r) => r.data);

export const listOverrides = (rid, date) => USE_PG ? pgListOverrides(pgStoreId(rid), date) : axios.get(`${API}/prep-overrides/${rid}`, { params: { date } }).then((r) => r.data);
export const addOverride = (rid, body) => USE_PG ? pgAddOverride(pgStoreId(rid), body) : axios.post(`${API}/prep-overrides/${rid}`, body).then((r) => r.data);
export const deleteOverride = (rid, oid) => USE_PG ? pgDeleteOverride(pgStoreId(rid), oid) : axios.delete(`${API}/prep-overrides/${rid}/${oid}`).then((r) => r.data);

export const getProjections = (rid) => axios.get(`${API}/projections/${rid}`).then((r) => r.data);
export const putProjection = (rid, body) => axios.put(`${API}/projections/${rid}`, body).then((r) => r.data);
export const prepReport = (rid, from, to) => axios.get(`${API}/reports/${rid}/prep`, { params: { from, to } }).then((r) => r.data);

export const getStaffPin = (rid) => USE_PG ? pgGetStaffPin(pgStoreId(rid)) : axios.get(`${API}/staff/${rid}/pin`).then((r) => r.data);
export const setStaffPin = (rid, staffPin) => USE_PG ? pgSetStaffPin(pgStoreId(rid), staffPin) : axios.post(`${API}/staff/${rid}/pin`, { staffPin }).then((r) => r.data);
export const verifyStaffPin = (rid, pin) => USE_PG ? pgVerifyStaffPin(pgStoreId(rid), pin) : axios.post(`${API}/staff/verify`, { restaurantId: rid, pin }).then((r) => r.data);
export const identifyStaffMember = (rid, pin, staffId) => USE_PG ? pgIdentifyStaffMember(pgStoreId(rid), pin, staffId) : axios.post(`${API}/staff/${rid}/identify`, { pin, staffId }).then((r) => r.data);

export const listStaffMembers = (rid) => USE_PG ? pgListStaffMembers(pgStoreId(rid)) : axios.get(`${API}/staff/${rid}/members`).then((r) => r.data);
export const createStaffMember = (rid, body) => USE_PG ? pgCreateStaffMember(pgStoreId(rid), body) : axios.post(`${API}/staff/${rid}/members`, body).then((r) => r.data);
export const updateStaffMember = (rid, staffId, body) => USE_PG ? pgUpdateStaffMember(pgStoreId(rid), staffId, body) : axios.put(`${API}/staff/${rid}/members/${staffId}`, body).then((r) => r.data);
export const deleteStaffMember = (rid, staffId) => USE_PG ? pgDeleteStaffMember(pgStoreId(rid), staffId) : axios.delete(`${API}/staff/${rid}/members/${staffId}`).then((r) => r.data);

// submitCounts/itemCountSubmissionHistory keep their legacy URLs because CountsTab.js
// is not frontend-gated; the backend selects Mongo or Postgres via its own USE_PG flag
// (see docs/SUPABASE_MIGRATION_PLAN.md, chunk 5.5).
export const submitCounts = (rid, body) => actualInventoryEnabled ? retiredWorkflow("Use Actual Inventory with verified units and explicit count values.") : axios.post(`${API}/counts/${rid}/submit`, body).then((r) => r.data);
export const itemCountSubmissionHistory = (rid, from, to) => axios.get(`${API}/counts/${rid}/history`, { params: { from, to } }).then((r) => r.data);

export const staffPrepsheet = (rid, pin, track = "daily") => USE_PG ? pgStaffPrepsheet(pgStoreId(rid), pin, track) : axios.post(`${API}/staff/${rid}/prepsheet`, { pin, track }).then((r) => r.data);
export const staffCompleteTask = (rid, body) => USE_PG ? pgStaffCompleteTask(pgStoreId(rid), body) : axios.post(`${API}/staff/${rid}/prepsheet/complete`, body).then((r) => r.data);

export const staffCounts = (rid, pin) => actualInventoryEnabled ? retiredWorkflow("Ask your manager to open Actual Inventory for the reviewed physical count.") : USE_PG ? pgStaffCounts(pgStoreId(rid), pin) : axios.post(`${API}/staff/${rid}/counts`, { pin }).then((r) => r.data);
export const staffSaveCounts = (rid, body) => actualInventoryEnabled ? retiredWorkflow("Save purchased-item counts through Actual Inventory with explicit count values.") : USE_PG ? pgStaffSaveCounts(pgStoreId(rid), body) : axios.post(`${API}/staff/${rid}/counts/save`, body).then((r) => r.data);

export const staffTaskInbox = (rid, pin) => USE_PG ? pgStaffTaskInbox(pgStoreId(rid), pin) : axios.post(`${API}/staff/${rid}/tasks`, { pin }).then((r) => r.data);
export const staffCompleteStaffTask = (rid, taskId, body) => USE_PG ? pgStaffCompleteStaffTask(pgStoreId(rid), taskId, body) : axios.post(`${API}/staff/${rid}/tasks/${taskId}/complete`, body).then((r) => r.data);
export const listStaffTasks = (rid) => USE_PG ? pgListStaffTasks(pgStoreId(rid)) : axios.get(`${API}/staff-tasks/${rid}`).then((r) => r.data);
export const createStaffTask = (rid, body) => USE_PG ? pgCreateStaffTask(pgStoreId(rid), body) : axios.post(`${API}/staff-tasks/${rid}`, body).then((r) => r.data);
export const deleteStaffTask = (rid, taskId) => USE_PG ? pgDeleteStaffTask(pgStoreId(rid), taskId) : axios.delete(`${API}/staff-tasks/${rid}/${taskId}`).then((r) => r.data);

export const pushPublicKey = (rid) => USE_PG ? pgPushPublicKey(pgStoreId(rid)) : axios.get(`${API}/staff/${rid}/push/public-key`).then((r) => r.data);
export const pushSubscribe = (rid, body) => USE_PG ? pgPushSubscribe(pgStoreId(rid), body) : axios.post(`${API}/staff/${rid}/push/subscribe`, body).then((r) => r.data);
export const pushUnsubscribe = (rid, body) => USE_PG ? pgPushUnsubscribe(pgStoreId(rid), body) : axios.post(`${API}/staff/${rid}/push/unsubscribe`, body).then((r) => r.data);

export const runParAdvisor = (rid) => axios.post(`${API}/ai/par-advisor/${rid}`).then((r) => r.data);
export const getParRecs = (rid) => axios.get(`${API}/ai/par-advisor/${rid}`).then((r) => r.data);
export const applyParRec = (rid, recId) => axios.post(`${API}/ai/par-advisor/${rid}/${recId}/apply`).then((r) => r.data);
export const dismissParRec = (rid, recId) => axios.post(`${API}/ai/par-advisor/${rid}/${recId}/dismiss`).then((r) => r.data);

export const listPrepItems = (rid, track = "daily") => USE_PG ? pgListPrepItems(pgStoreId(rid), track) : axios.get(`${API}/prep-items/${rid}`, { params: { track } }).then((r) => r.data);
const pgPrepItemBody = (rid, body) => ({
  ...body, itemCode: body.sourceType === "item" ? `${rid}_${body.controlNumber}` : null,
});
export const createPrepItem = (rid, body) => USE_PG ? pgCreatePrepItem(pgStoreId(rid), pgPrepItemBody(rid, body)) : axios.post(`${API}/prep-items/${rid}`, body).then((r) => r.data);
export const updatePrepItem = (rid, pid, body) => USE_PG ? pgUpdatePrepItem(pgStoreId(rid), pid, pgPrepItemBody(rid, body)) : axios.put(`${API}/prep-items/${rid}/${pid}`, body).then((r) => r.data);
export const deletePrepItem = (rid, pid) => USE_PG ? pgDeletePrepItem(pgStoreId(rid), pid) : axios.delete(`${API}/prep-items/${rid}/${pid}`).then((r) => r.data);
export const addItemToList = (rid, listId, body) => USE_PG ? pgAddItemToList(pgStoreId(rid), listId, body) : axios.post(`${API}/preplists/${rid}/${listId}/add-item`, body).then((r) => r.data);

// ==================== Supabase (Postgres) migration -- /api/pg/* ====================
// See docs/SUPABASE_MIGRATION_PLAN.md. Mirrors the shapes of the functions above one
// for one where a Mongo-backed equivalent already exists, so swapping call sites is a
// name change, not a rewrite. `storeId` throughout is berts/rudds/papa/comm.

// ---- Vendors (global, not store-scoped) ----
export const pgListVendors = () => axios.get(`${PG_API}/vendors`).then((r) => r.data);
export const pgCreateVendor = (body) => axios.post(`${PG_API}/vendors`, body).then((r) => r.data);
export const pgUpdateVendor = (vendorId, body, version) => axios.put(`${PG_API}/vendors/${vendorId}`, body, { headers: revisionHeaders(version) }).then((r) => r.data);

// ---- Items (global catalog + per-store tracking + per-vendor SKUs, flattened) ----
export const pgListItems = (storeId) => axios.get(`${PG_API}/items/${storeId}`).then((r) => r.data);
export const pgCreateItem = (storeId, body) => axios.post(`${PG_API}/items/${storeId}`, body).then((r) => r.data);
export const pgDeleteItem = (storeId, code) => axios.delete(`${PG_API}/items/${storeId}/${code}`).then((r) => r.data);

// ---- Invoices ----
export const pgListInvoices = (storeId, from, to) => axios.get(`${PG_API}/invoices/${storeId}`, { params: { from, to } }).then((r) => r.data);
export const pgCreateInvoice = (storeId, body) => nativePurchasesEnabled ? retiredWorkflow("Use Invoice Master to retain and review this purchase before posting.") : axios.post(`${PG_API}/invoices/${storeId}`, body).then((r) => r.data);

// ---- Dishes (menu items + prep recipes) -- ids are real Postgres uuids, not the
// Mongo-side "dish_xxx"/"prep_xxx" strings. ----
export const pgListDishes = (storeId) => axios.get(`${PG_API}/dishes/${storeId}`).then((r) => r.data);
export const pgSaveDish = (storeId, body) => axios.post(`${PG_API}/dishes/${storeId}`, body).then((r) => r.data);
export const pgReplaceDishes = (storeId, body, revision) => axios.put(`${PG_API}/dishes/${storeId}`, body, { headers: revisionHeaders(revision) }).then((r) => r.data);
export const pgDeleteDish = (storeId, dishId) => axios.delete(`${PG_API}/dishes/${storeId}/${dishId}`).then((r) => r.data);

// ---- Prep: direct recipe batch / sales usage / containers ----
export const pgCompletePrep = (storeId, body) => axios.post(`${PG_API}/prep/${storeId}/complete`, body).then((r) => r.data);
export const pgApplyPrepSales = (storeId, dishSales) => axios.post(`${PG_API}/prep/${storeId}/apply-sales`, { dishSales }).then((r) => r.data);
export const pgUseContainer = (storeId, body) => axios.post(`${PG_API}/prep/${storeId}/use-container`, body).then((r) => r.data);
export const pgFetchPrepState = (rid) => axios.get(`${PG_API}/prep/${pgStoreId(rid)}/state`).then((r) => r.data);

// ---- Prep: evening count sessions ----
export const pgGetCountSession = (storeId, date, track = "daily") => axios.get(`${PG_API}/prepcount/${storeId}/session`, { params: { date, track } }).then((r) => r.data);
export const pgSaveCountEntry = (storeId, sid, body) => axios.post(`${PG_API}/prepcount/${storeId}/session/${sid}/entry`, body).then((r) => r.data);
export const pgSubmitCount = (storeId, sid, body) => axios.post(`${PG_API}/prepcount/${storeId}/session/${sid}/submit`, body).then((r) => r.data);
export const pgCountHistory = (storeId) => axios.get(`${PG_API}/prepcount/${storeId}/history`).then((r) => r.data);

// ---- Prep: lists ----
export const pgGetPrepList = (storeId, date, track = "daily") => axios.get(`${PG_API}/preplists/${storeId}`, { params: { date, track } }).then((r) => r.data);
export const pgGeneratePrepList = (storeId, date, track = "daily") => axios.post(`${PG_API}/preplists/${storeId}/generate`, { date, track }).then((r) => r.data);
export const pgUpdatePrepList = (storeId, id, tasks) => axios.put(`${PG_API}/preplists/${storeId}/${id}`, { tasks }).then((r) => r.data);
export const pgReleasePrepList = (storeId, id, releasedBy) => axios.post(`${PG_API}/preplists/${storeId}/${id}/release`, { releasedBy }).then((r) => r.data);
export const pgCompleteTask = (storeId, listId, taskId, body) => axios.post(`${PG_API}/preplists/${storeId}/${listId}/task/${taskId}/complete`, body).then((r) => r.data);
export const pgAddItemToList = (storeId, listId, body) => axios.post(`${PG_API}/preplists/${storeId}/${listId}/add-item`, body).then((r) => r.data);

// ---- Prep: standing Prep Items catalog ----
export const pgListPrepItems = (storeId, track) => axios.get(`${PG_API}/prep-items/${storeId}`, { params: track ? { track } : {} }).then((r) => r.data);
export const pgCreatePrepItem = (storeId, body) => axios.post(`${PG_API}/prep-items/${storeId}`, body).then((r) => r.data);
export const pgUpdatePrepItem = (storeId, pid, body) => axios.put(`${PG_API}/prep-items/${storeId}/${pid}`, body).then((r) => r.data);
export const pgDeletePrepItem = (storeId, pid) => axios.delete(`${PG_API}/prep-items/${storeId}/${pid}`).then((r) => r.data);

// ---- Prep: day overrides ----
export const pgListOverrides = (storeId, date) => axios.get(`${PG_API}/prep-overrides/${storeId}`, { params: date ? { date } : {} }).then((r) => r.data);
export const pgAddOverride = (storeId, body) => axios.post(`${PG_API}/prep-overrides/${storeId}`, body).then((r) => r.data);
export const pgDeleteOverride = (storeId, oid) => axios.delete(`${PG_API}/prep-overrides/${storeId}/${oid}`).then((r) => r.data);

// ---- Staff PIN portal (chunk 5) ----
export const pgGetStaffPin = (storeId) => axios.get(`${PG_API}/staff/${storeId}/pin`).then((r) => r.data);
export const pgSetStaffPin = (storeId, staffPin) => axios.post(`${PG_API}/staff/${storeId}/pin`, { staffPin }).then((r) => r.data);
export const pgVerifyStaffPin = (storeId, pin) => axios.post(`${PG_API}/staff/${storeId}/verify`, { pin }).then((r) => r.data);
export const pgIdentifyStaffMember = (storeId, pin, staffId) => axios.post(`${PG_API}/staff/${storeId}/identify`, { pin, staffId }).then((r) => r.data);

export const pgListStaffMembers = (storeId) => axios.get(`${PG_API}/staff/${storeId}/members`).then((r) => r.data);
export const pgCreateStaffMember = (storeId, body) => axios.post(`${PG_API}/staff/${storeId}/members`, body).then((r) => r.data);
export const pgUpdateStaffMember = (storeId, staffId, body) => axios.put(`${PG_API}/staff/${storeId}/members/${staffId}`, body).then((r) => r.data);
export const pgDeleteStaffMember = (storeId, staffId) => axios.delete(`${PG_API}/staff/${storeId}/members/${staffId}`).then((r) => r.data);

export const pgStaffPrepsheet = (storeId, pin, track = "daily") => axios.post(`${PG_API}/staff/${storeId}/prepsheet`, { pin, track }).then((r) => r.data);
export const pgStaffCompleteTask = (storeId, body) => axios.post(`${PG_API}/staff/${storeId}/prepsheet/complete`, body).then((r) => r.data);

export const pgStaffCounts = (storeId, pin) => actualInventoryEnabled ? retiredWorkflow("Ask your manager to use Actual Inventory for reviewed physical counts.") : axios.post(`${PG_API}/staff/${storeId}/counts`, { pin }).then((r) => r.data);
export const pgStaffSaveCounts = (storeId, body) => actualInventoryEnabled ? retiredWorkflow("Use Actual Inventory with verified units and explicit count values.") : axios.post(`${PG_API}/staff/${storeId}/counts/save`, body).then((r) => r.data);

export const pgStaffTaskInbox = (storeId, pin) => axios.post(`${PG_API}/staff/${storeId}/tasks`, { pin }).then((r) => r.data);
export const pgStaffCompleteStaffTask = (storeId, taskId, body) => axios.post(`${PG_API}/staff/${storeId}/tasks/${taskId}/complete`, body).then((r) => r.data);
export const pgListStaffTasks = (storeId) => axios.get(`${PG_API}/staff-tasks/${storeId}`).then((r) => r.data);
export const pgCreateStaffTask = (storeId, body) => axios.post(`${PG_API}/staff-tasks/${storeId}`, body).then((r) => r.data);
export const pgDeleteStaffTask = (storeId, taskId) => axios.delete(`${PG_API}/staff-tasks/${storeId}/${taskId}`).then((r) => r.data);

export const pgPushPublicKey = (storeId) => axios.get(`${PG_API}/staff/${storeId}/push/public-key`).then((r) => r.data);
export const pgPushSubscribe = (storeId, body) => axios.post(`${PG_API}/staff/${storeId}/push/subscribe`, body).then((r) => r.data);
export const pgPushUnsubscribe = (storeId, body) => axios.post(`${PG_API}/staff/${storeId}/push/unsubscribe`, body).then((r) => r.data);

// ==================== Chunk 3: state-blob adapter for Items/Purchases ====================
// See docs/SUPABASE_MIGRATION_PLAN.md. fetchState/putCollection below reshape the granular
// pg Items/Invoices endpoints into the exact `items`/`purchases` array shapes every existing
// component already reads, so nothing downstream of App.js needs to change. Only active when
// USE_PG is on; dishes/adjustments/prepStock/etc. still come from Mongo either way (not
// migrated yet). Known limitations, not attempted here: an invoice line's vendor can only be
// one of the 5 canonical VENDOR_NAME_TO_ID vendors -- a free-text vendor name from CSV
// auto-import falls back to "other"; and purchases/invoices are only ever appended, never
// edited or deleted, matching what the current UI (InvoicesTab) actually does.
const VENDOR_NAME_TO_ID = { "US Foods": "us_foods", "PFG": "pfg", "Sysco": "sysco", "Webstaurant": "webstaurant", "Other": "other" };
const VENDOR_ID_TO_NAME = Object.fromEntries(Object.entries(VENDOR_NAME_TO_ID).map(([k, v]) => [v, k]));
const numOrNull = v => {
  if (v === "" || v == null) return null;
  if (typeof v === "boolean") throw new Error("Enter a numeric value, not a boolean.");
  const value = Number(v);
  if (!Number.isFinite(value)) throw new Error("Enter a finite numeric value before saving.");
  return value;
};
export function catalogPrice(v) {
  if (v === "" || v == null) return null;
  const value = String(v).trim();
  if (!/^(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?$/.test(value) || !Number.isFinite(Number(value))) throw new Error("Enter a non-negative finite supplier price, or leave it unknown.");
  return value; // Keep the entered decimal digits; catalog price is not a float.
}

function pgSkuToMongoSku(s) {
  return {
    vendorId: s.vendor, basePerPurchaseUnit: s.basePerPurchaseUnit,
    id: s.id, vendor: s.vendorName || VENDOR_ID_TO_NAME[s.vendor] || s.vendor, vendorSku: s.vendorSku,
    vendorDescription: s.vendorDescription ?? null,
    packDescription: s.vendorDescription ?? "",
    purchaseUnit: s.purchaseUnit, packCount: s.packCount ?? "", unitQty: s.unitQty ?? "", unitUOM: s.unitUOM || "",
    price: s.price ?? null, priceUpdatedAt: s.priceUpdatedAt || "", priceSource: s.priceSource ?? null, priceIssues: s.priceIssues || [],
    available: s.available, preferred: s.preferred,
  };
}

export function pgItemToMongoItem(pgItem, rid) {
  const prefix = `${rid}_`;
  const controlNumber = pgItem.controlNumber || (pgItem.code.startsWith(prefix) ? pgItem.code.slice(prefix.length) : pgItem.code);
  const preferred = preferredSku(pgItem);
  return {
    controlNumber, name: pgItem.name, storageArea: pgItem.storageArea || "",
    itemCode: pgItem.code, baseUnit: pgItem.baseUnit, countUnit: pgItem.countUnit, basePerCountUnit: pgItem.basePerCountUnit,
    sharedStoreCount: pgItem.sharedStoreCount,
    catalogActive: pgItem.catalogActive, active: pgItem.active, countActive: pgItem.countActive,
    orderEnabled: pgItem.orderEnabled, salesTracked: pgItem.salesTracked,
    itemType: pgItem.costingType,
    category: pgItem.category, classification: pgItem.itemType,
    isHighValue: pgItem.isHighValue, notes: pgItem.notes,
    purchaseUnit: preferred?.purchaseUnit || "case",
    packCount: pgItem.packCount ?? "", unitQty: pgItem.unitQty ?? "", unitUOM: pgItem.unitUOM || "",
    portionSize: pgItem.portionSize ?? "", portionUOM: pgItem.portionUOM || "",
    par: pgItem.par, currentStock: actualInventoryEnabled ? null : pgItem.currentStock, stockBasis: pgItem.stockBasis,
    lastCounted: pgItem.lastCounted ?? null, lastCountedBy: pgItem.lastCountedBy ?? null, needsReview: pgItem.needsReview,
    vendorSkus: pgItem.vendorSkus.map(pgSkuToMongoSku),
  };
}

function packTotalFor(sourceObj, item) {
  const packCount = Number(sourceObj?.packCount ?? item.packCount) || 0;
  const unitQty = Number(sourceObj?.unitQty ?? item.unitQty) || 0;
  const unitUOM = sourceObj?.unitUOM || item.unitUOM || "each";
  return { packTotal: packCount * unitQty, unitUOM };
}

const physicalUnits = { lb: ["mass", 453.59237], oz: ["mass", 28.349523125], kg: ["mass", 1000], g: ["mass", 1],
  gal: ["volume", 3785.411784], fl_oz: ["volume", 29.5735295625], l: ["volume", 1000], ml: ["volume", 1],
  qt: ["volume", 946.352946], pt: ["volume", 473.176473], cup: ["volume", 236.5882365], each: ["count", 1], dozen: ["count", 12] };
const physicalUnit = value => value === "fl oz" ? "fl_oz" : value === "ct" ? "each" : value;
function physicalPackFactor(packTotal, unit, base) {
  const from = physicalUnits[physicalUnit(unit)], to = physicalUnits[physicalUnit(base)];
  if (!(packTotal > 0) || !from || !to || from[0] !== to[0]) throw new Error("Confirm a physical pack quantity and compatible inventory unit before saving this item.");
  return packTotal * from[1] / to[1]; // Catalog metadata only; native profiles require separate decimal review.
}
export function mongoItemToPgBody(item, rid) {
  const skus = item.vendorSkus || [];
  const preferred = preferredSku(item);
  const { packTotal, unitUOM } = packTotalFor(preferred, item);
  const nativeBase = physicalUnit(item.baseUnit || item.unitUOM || unitUOM);
  const basePerCountUnit = nativePurchasesEnabled ? item.basePerCountUnit ?? physicalPackFactor(packTotal, unitUOM, nativeBase)
    : calcPortionsPerUnit(packTotal, unitUOM, item.portionSize, item.portionUOM).value || 1;
  const countActive = !!(item.countActive ?? item.active);
  return {
    code: item.itemCode || `${rid}_${item.controlNumber}`, name: item.name, base_unit: nativePurchasesEnabled ? nativeBase : item.portionUOM || "each",
    ...(catalogMappingEnabled ? { control_number: item.controlNumber } : {}),
    category: item.category, item_type: item.classification,
    is_high_value: item.isHighValue, notes: item.notes,
    costing_type: item.itemType || "portion",
    pack_count: numOrNull(item.packCount), unit_qty: numOrNull(item.unitQty), unit_uom: item.unitUOM || null,
    portion_size: numOrNull(item.portionSize), portion_uom: item.portionUOM || null,
    count_unit: nativePurchasesEnabled ? item.countUnit || item.purchaseUnit || preferred?.purchaseUnit || "case" : item.purchaseUnit || preferred?.purchaseUnit || "case",
    base_per_count_unit: basePerCountUnit,
    storage_area: item.storageArea || null,
    counted_nightly: countActive,
    par: Number(item.par) || 0,
    active: !!(item.active ?? countActive),
    order_enabled: item.orderEnabled !== false,
    sales_tracked: item.salesTracked !== false,
    needs_review: !!item.needsReview,
    vendor_skus: skus.map((s) => {
      const { packTotal: skuPackTotal, unitUOM: skuUOM } = packTotalFor(s, item);
      const basePerPurchaseUnit = nativePurchasesEnabled ? s.basePerPurchaseUnit ?? physicalPackFactor(skuPackTotal, skuUOM, nativeBase)
        : calcPortionsPerUnit(skuPackTotal, skuUOM, item.portionSize, item.portionUOM).value || null;
      return {
        vendor_id: s.vendorId || VENDOR_NAME_TO_ID[s.vendor] || "other", vendor_sku: s.vendorSku || s.id || "",
        vendor_description: s.packDescription === "" && s.vendorDescription === null ? null : s.packDescription ?? s.vendorDescription ?? null, purchase_unit: s.purchaseUnit || item.purchaseUnit || "case",
        base_per_purchase_unit: basePerPurchaseUnit,
        pack_count: numOrNull(s.packCount), unit_qty: numOrNull(s.unitQty), unit_uom: s.unitUOM || null,
        price: catalogPrice(s.price), preferred: !!s.preferred, available: s.available !== false,
      };
    }),
  };
}

async function pgFetchItemsAndPurchases(rid) {
  const storeId = pgStoreId(rid);
  const [pgItems, pgInvoices] = await Promise.all([pgListItems(storeId), nativePurchasesEnabled ? Promise.resolve([]) : pgListInvoices(storeId)]);
  const items = pgItems.map((it) => pgItemToMongoItem(it, rid));
  const purchases = [];
  for (const inv of pgInvoices) {
    for (const line of inv.lines) {
      const cn = line.itemCode && line.itemCode.startsWith(`${rid}_`) ? line.itemCode.slice(rid.length + 1) : (line.itemCode || "");
      purchases.push({
        id: line.id, invoiceId: inv.id, invoiceDate: inv.invoiceDate, invoiceNumber: inv.invoiceNumber || "",
        vendor: VENDOR_ID_TO_NAME[inv.vendorId] || inv.vendorId,
        controlNumber: cn, itemName: line.itemName || line.description || "",
        qty: line.qty, unit: line.unit || "", unitCost: line.unitPrice, extendedCost: line.extended,
      });
    }
  }
  return { items, purchases };
}

async function pgPutItems(rid, arr, revision) {
  const storeId = pgStoreId(rid);
  return axios.put(`${PG_API}/items/${storeId}`, arr.map((it) => mongoItemToPgBody(it, rid)),
    { headers: revisionHeaders(revision) }).then((r) => r.data);
}

async function pgPutPurchases(rid, arr, revision) {
  const storeId = pgStoreId(rid);
  const [existingInvoices, items] = await Promise.all([pgListInvoices(storeId), pgListItems(storeId)]);
  const itemsByCode = new Map(items.map((it) => [it.code, it]));
  const known = new Set(existingInvoices.map((inv) => `${inv.vendorId}|${inv.invoiceNumber}|${inv.invoiceDate}`));
  const byInvoiceId = new Map();
  for (const p of arr) {
    if (!byInvoiceId.has(p.invoiceId)) byInvoiceId.set(p.invoiceId, []);
    byInvoiceId.get(p.invoiceId).push(p);
  }
  const creates = [];
  for (const lines of byInvoiceId.values()) {
    const [first] = lines;
    const vendorId = VENDOR_NAME_TO_ID[first.vendor] || "other";
    const key = `${vendorId}|${first.invoiceNumber}|${first.invoiceDate}`;
    if (known.has(key)) continue;
    creates.push(pgCreateInvoice(storeId, {
      vendor_id: vendorId, invoice_number: first.invoiceNumber, invoice_date: first.invoiceDate, source: "manual",
      lines: lines.map((l) => {
        const item = itemsByCode.get(`${rid}_${l.controlNumber}`);
        const sku = item?.vendorSkus.find((s) => s.vendor === (VENDOR_NAME_TO_ID[first.vendor] || first.vendor));
        return { vendor_item_id: sku?.id || null, description: l.itemName, qty: Number(l.qty) || 0, purchase_unit: l.unit, unit_price: Number(l.unitCost) || 0 };
      }),
    }));
  }
  await Promise.all(creates);
  return { revision };
}

// ==================== Chunk 4: state-blob adapter for Dishes/Recipes ====================
// Same pattern as items/purchases above. One real difference: pg dish ids are actual
// Postgres uuids (Prep's own endpoints already key prep_recipe_stock/prep_logs/
// prep_overrides by this same uuid), NOT the Mongo-side client-generated "dish_xxx"/
// "prep_xxx" strings -- a brand-new dish created in CostingTab still gets a "dish_xxx"
// id client-side until it's saved, at which point the real uuid from the pg response
// replaces it. Known limitation: `reportingPeriods.dishSales` (Sales Tracking, not
// migrated) is keyed by the OLD Mongo dish id and will NOT resolve against these new
// uuids -- Sales Tracking needs its own migration pass before this can be a real
// cutover. Also: creating a brand-new prep recipe and a brand-new menu item that
// references it in the SAME save isn't ordered/dependency-sorted here (dish_lines'
// prep_dish_id FK needs the prep dish to exist first) -- matches how CostingTab only
// ever edits one dish per save in practice, but a batch of unrelated new dishes with
// cross-references would need that.
const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const isUuid = (s) => typeof s === "string" && UUID_RE.test(s);

function pgLineToMongoLine(l, rid, items) {
  const prefix = `${rid}_`;
  const item = items.find(it => it.itemCode === l.itemCode);
  return {
    sourceType: l.sourceType,
    itemCode: l.sourceType === "item" ? l.itemCode : null,
    controlNumber: l.sourceType === "item" && l.itemCode ? (item?.controlNumber || (l.itemCode.startsWith(prefix) ? l.itemCode.slice(prefix.length) : l.itemCode)) : null,
    recipeId: l.sourceType === "prep" ? l.prepDishId : null,
    qty: l.qty, uom: l.uom ?? null,
  };
}

function mongoLineToPgBody(l, rid, items) {
  const item = l.sourceType === "item" ? items.find(it => l.itemCode ? it.itemCode === l.itemCode : it.controlNumber === l.controlNumber) : null;
  if (l.sourceType === "item" && !item) throw new Error("Ingredient is not linked to this restaurant. Reload and review the recipe mapping.");
  return {
    source_type: l.sourceType,
    item_code: item?.itemCode || null,
    prep_dish_id: l.sourceType === "prep" ? l.recipeId : null,
    qty: numOrNull(l.qty ?? l.qtyPortions), uom: l.uom ?? null,
  };
}

function pgDishToMongoDish(d, rid, items) {
  return {
    id: d.id, name: d.name, menuCode: d.menuCode || "", recipeType: d.recipeType,
    price: d.price ?? "", targetPct: d.targetPct ?? "", yieldQty: d.yieldQty ?? (d.recipeType === "prep" ? null : 1), yieldUOM: d.yieldUOM ?? (d.recipeType === "prep" ? null : "each"),
    prepPar: d.prepPar ?? 0, procedure: d.procedure || "", equipment: d.equipment || "", shelfLife: d.shelfLife || "",
    menuCategory: d.menuCategory || "", description: d.description || "", photoUrl: d.photoUrl || "",
    portionNote: d.portionNote || "", frequency: d.frequency || "daily",
    lines: (d.lines || []).map((l) => pgLineToMongoLine(l, rid, items)),
  };
}

function mongoDishToPgBody(dish, rid, items) {
  return {
    id: isUuid(dish.id) ? dish.id : null,
    name: dish.name, menu_code: dish.menuCode || null, recipe_type: dish.recipeType || "menu",
    price: numOrNull(dish.price), target_pct: numOrNull(dish.targetPct), yield_qty: numOrNull(dish.yieldQty),
    yield_uom: dish.yieldUOM || null, prep_par: numOrNull(dish.prepPar),
    procedure: dish.procedure || null, equipment: dish.equipment || null, shelf_life: dish.shelfLife || null,
    menu_category: dish.menuCategory || null, description: dish.description || null, photo_url: dish.photoUrl || null,
    portion_note: dish.portionNote || null, frequency: dish.frequency || null,
    lines: (dish.lines || []).map((l) => mongoLineToPgBody(l, rid, items)),
  };
}

async function pgFetchDishes(rid) {
  const storeId = pgStoreId(rid);
  return pgListDishes(storeId);
}

async function pgPutDishes(rid, arr, revision) {
  const items = (await pgListItems(pgStoreId(rid))).map(it => pgItemToMongoItem(it, rid));
  const saved = await pgReplaceDishes(pgStoreId(rid), arr.map((dish) => ({
    ...mongoDishToPgBody(dish, rid, items), client_id: isUuid(dish.id) ? null : dish.id,
  })), revision);
  return { revision: saved.revision, dishes: saved.dishes.map((dish) => pgDishToMongoDish(dish, rid, items)) };
}

export async function streamChat(rid, message, { onDelta, onError, onDone }) {
  let res;
  try {
    res = await fetch(`${API}/ai/chat`, {
      method: "POST",
      headers: { "Content-Type": "application/json", ...(session()?.token ? { Authorization: ["Bearer", session().token].join(" ") } : {}) },
      body: JSON.stringify({ restaurantId: rid, message }),
    });
  } catch {
    onError?.("Can't reach the server. Check your connection, or the API may still be starting up.");
    onDone?.();
    return;
  }
  if (res.status === 401) endSession();
  if (!res.ok || !res.body) {
    let detail = "";
    try { detail = (await res.json())?.detail || ""; } catch { /* not JSON */ }
    onError?.(detail || `Request failed (${res.status})`);
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
