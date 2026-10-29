import { canonicalStoreId } from "./purchaseContract";
import { validOverviewDay } from "./managerOverview";
import { validPrepTrack } from "./prepTracks";
const uuid = v => typeof v === "string" && /^[a-f0-9]{8}(?:-[a-f0-9]{4}){3}-[a-f0-9]{12}$/i.test(v);
const id = v => typeof v === "string" && /^[A-Za-z0-9_.-]{1,160}$/.test(v);
const integer = v => Number.isSafeInteger(v) && v >= 0 && v <= 2147483647;
const exact = (v, keys) => v && typeof v === "object" && !Array.isArray(v) && Object.keys(v).length === keys.length && keys.every(k => Object.hasOwn(v, k));
const timestamp = v => typeof v === "string" && /(?:Z|[+-]\d\d:\d\d)$/.test(v) && Number.isFinite(Date.parse(v));
const readiness = v => ["not_assessed", "ready", "action_needed"].includes(v);
const zone = v => { try { new Intl.DateTimeFormat("en", { timeZone: v }).format(); return typeof v === "string" && !!v; } catch { return false; } };
const unicode = v => { for (const c of v) { const p = c.codePointAt(0); if (p === 0 || (p >= 0xd800 && p <= 0xdfff)) return false; } return true; };
const text = (v, max, required = false) => typeof v === "string" && [...v].length <= max && unicode(v) && (!required || !!v.trim());
const fail = () => new Error("Handoff information or recovery could not be confirmed. Retain this request and refresh.");
function check(ok) { if (!ok) throw fail(); }
export const stableHandoff = v => JSON.stringify(sort(v));
function sort(v) { return Array.isArray(v) ? v.map(sort) : v && typeof v === "object" ? Object.fromEntries(Object.keys(v).sort().map(k => [k, sort(v[k])])) : v; }
export function handoffContext(rid, day, track, actor) {
  if (!["berts", "rudds", "papa_leonis"].includes(rid) || !validOverviewDay(day) || day.startsWith("0000") || !validPrepTrack(rid, track)
    || !id(actor?.id) || !["owner", "manager"].includes(actor.role) || (actor.role === "manager" && (!Array.isArray(actor.locations) || !actor.locations.includes(rid)))) return null;
  return { rid, store: canonicalStoreId(rid), day, track, actor: actor.id,
    key: stableHandoff([actor.id, actor.role, actor.locations, rid, day, track]) };
}
const bodyKeys = ["action", "note_id", "business_date", "prep_track", "settings_revision", "summary", "next_shift_note", "reported_readiness", "correction_reason"];
export function checkedHandoffRequest(r) {
  check(exact(r, ["key", "version", "body", "fingerprint"]) && uuid(r.key) && integer(r.version) && r.version < 2147483647 && /^[a-f0-9]{64}$/.test(r.fingerprint));
  const b = r.body;
  check(exact(b, bodyKeys) && ["create_draft", "save_draft", "submit", "correct"].includes(b.action)
    && uuid(b.note_id) && validOverviewDay(b.business_date) && !b.business_date.startsWith("0000") && ["daily", "bulk", "salad"].includes(b.prep_track)
    && integer(b.settings_revision) && b.settings_revision > 0 && text(b.summary, 6000, true) && b.summary === b.summary.trim()
    && text(b.next_shift_note, 4000) && readiness(b.reported_readiness) && text(b.correction_reason, 2000)
    && b.correction_reason === b.correction_reason.trim() && ((b.action === "correct") === !!b.correction_reason)
    && ((b.action === "create_draft") === (r.version === 0)));
  return r;
}
export async function handoffFingerprint(actor, store, body, version) {
  const raw = stableHandoff({ actor, store: canonicalStoreId(store), command: body, expected: version });
  const digest = await window.crypto.subtle.digest("SHA-256", new TextEncoder().encode(raw));
  return [...new Uint8Array(digest)].map(b => b.toString(16).padStart(2, "0")).join("");
}
export function handoffJournal(actor, rid, storage = () => window.sessionStorage) {
  const store = canonicalStoreId(rid), key = `jaymax:manager-handoff:v1:${actor}:${store}`;
  function read() {
    try {
      check(id(actor) && ["berts", "rudds", "papa"].includes(store));
      const raw = storage().getItem(key); if (raw === null) return null;
      check(new Blob([raw]).size <= 128 * 1024);
      const v = JSON.parse(raw); check(exact(v, ["schema", "actorId", "storeId", "request"]) && v.schema === 1 && v.actorId === actor && v.storeId === store);
      return checkedHandoffRequest(v.request);
    } catch { throw fail(); }
  }
  return { read, save(request) {
    checkedHandoffRequest(request); const previous = read();
    if (previous) { check(stableHandoff(previous) === stableHandoff(request)); return previous; }
    const raw = JSON.stringify({ schema: 1, actorId: actor, storeId: store, request });
    check(new Blob([raw]).size <= 128 * 1024);
    try { storage().setItem(key, raw); check(storage().getItem(key) === raw); } catch { throw fail(); }
    return request;
  }, clear(request) {
    check(stableHandoff(read()) === stableHandoff(request));
    try { storage().removeItem(key); check(storage().getItem(key) === null); } catch { throw fail(); }
  } };
}
export function checkedHandoffNote(n, c, previous = false) {
  check(n?.store_id === c.store && uuid(n.id) && validOverviewDay(n.business_date) && n.prep_track === c.track
    && (previous ? n.business_date < c.day && n.status === "submitted" : n.business_date === c.day)
    && id(n.creator_id) && id(n.actor_id) && zone(n.timezone_name) && integer(n.settings_revision) && n.settings_revision > 0
    && integer(n.revision) && n.revision > 0 && timestamp(n.created_at) && timestamp(n.updated_at)
    && ["draft", "submitted"].includes(n.status) && (n.status === "draft" ? n.first_submitted_at === null : timestamp(n.first_submitted_at))
    && text(n.summary, 6000, true) && text(n.next_shift_note, 4000) && readiness(n.reported_readiness)
    && (n.status === "draft" ? ["create_draft", "save_draft"].includes(n.action) : ["submit", "correct"].includes(n.action))
    && text(n.correction_reason, 2000) && ((n.action === "correct") === !!n.correction_reason.trim()));
  return n;
}
export function checkedHandoffDay(v, c) {
  check(v?.store_id === c.store && v.actor_id === c.actor && v.business_date === c.day && v.prep_track === c.track
    && v.settings?.store_id === c.store && zone(v.settings.timezone_name) && integer(v.settings.revision) && v.settings.revision > 0);
  if (v.current !== null) checkedHandoffNote(v.current, c);
  if (v.previous !== null) checkedHandoffNote(v.previous, c, true);
  return v;
}
export function checkedHandoffReceipt(v, r, c) {
  checkedHandoffRequest(r);
  check(v?.store_id === c.store && v.actor_id === c.actor && v.request_key === r.key && v.note_id === r.body.note_id
    && v.expected_revision === r.version && v.request_fingerprint === r.fingerprint);
  checkedHandoffNote(v.current, c);
  const a = v.accepted;
  check(a?.store_id === c.store && a.note_id === r.body.note_id && a.actor_id === c.actor && a.revision === r.version + 1
    && timestamp(a.recorded_at) && a.action === r.body.action && a.status === (["submit", "correct"].includes(r.body.action) ? "submitted" : "draft")
    && ["summary", "next_shift_note", "reported_readiness", "correction_reason"].every(k => a[k] === r.body[k])
    && v.current.id === r.body.note_id && v.current.settings_revision === r.body.settings_revision && v.current.revision >= a.revision
    && (v.current.revision !== a.revision || ["summary", "next_shift_note", "reported_readiness", "correction_reason", "action", "actor_id", "status"].every(k => v.current[k] === a[k])));
  return v;
}
export function checkedHandoffStatus(v, r, c) {
  if (v?.outcome === "saved") return checkedHandoffReceipt(v, r, c);
  check(v?.outcome === "unconfirmed" && v.store_id === c.store && v.actor_id === c.actor && v.request_key === r.key
    && v.note_id === r.body.note_id && v.expected_revision === r.version && v.request_fingerprint === r.fingerprint);
  if (v.current !== null) { checkedHandoffNote(v.current, c); check(v.current.id === r.body.note_id); }
  return v;
}
export function checkedHandoffHistory(v, c, noteId, after) {
  check(v?.store_id === c.store && v.actor_id === c.actor && v.note_id === noteId && v.after === after
    && integer(v.current_revision) && Array.isArray(v.rows) && v.rows.length <= 50);
  v.rows.forEach((r, i) => check(r.store_id === c.store && r.note_id === noteId && r.revision === after + i + 1
    && r.revision <= v.current_revision && id(r.actor_id) && timestamp(r.recorded_at) && text(r.summary, 6000, true)
    && text(r.next_shift_note, 4000) && readiness(r.reported_readiness) && text(r.correction_reason, 2000)
    && ["create_draft", "save_draft", "submit", "correct"].includes(r.action)
    && r.status === (["submit", "correct"].includes(r.action) ? "submitted" : "draft")
    && ((r.action === "correct") === !!r.correction_reason.trim())));
  check(v.next_after === null ? (v.rows.length ? v.rows.at(-1).revision === v.current_revision : after >= v.current_revision)
    : v.rows.length === 50 && v.next_after === v.rows[49].revision && v.next_after < v.current_revision);
  return v;
}
