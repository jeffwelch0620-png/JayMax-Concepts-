// Fictional, public fixtures. No account credentials or operational records.
export const handoffOwner = { id: "usr_test", role: "owner", locations: [] };
export const handoffDay = "2026-10-25";
export const handoffId = "11111111-1111-4111-8111-111111111111";
export const handoffBody = (changes = {}) => ({ action: "create_draft", note_id: handoffId, business_date: handoffDay,
  prep_track: "bulk", settings_revision: 1, summary: "TEST ONLY: batch summary 🍲", next_shift_note: "Verify labelled portions",
  reported_readiness: "not_assessed", correction_reason: "", ...changes });
export const handoffNote = (changes = {}) => ({ id: handoffId, store_id: "berts", business_date: handoffDay, prep_track: "bulk",
  creator_id: "usr_test", actor_id: "usr_test", timezone_name: "America/New_York", settings_revision: 1, revision: 1,
  status: "draft", action: "create_draft", created_at: "2026-10-25T14:00:00+00:00", updated_at: "2026-10-25T14:00:00+00:00",
  first_submitted_at: null, summary: handoffBody().summary, next_shift_note: handoffBody().next_shift_note,
  reported_readiness: "not_assessed", correction_reason: "", ...changes });
export const handoffState = (changes = {}) => ({ store_id: "berts", actor_id: "usr_test", business_date: handoffDay,
  prep_track: "bulk", settings: { store_id: "berts", timezone_name: "America/New_York", revision: 1 }, current: null, previous: null, ...changes });
export const handoffReceipt = (request, current = null) => ({ store_id: "berts", actor_id: "usr_test", request_key: request.key,
  request_fingerprint: request.fingerprint, expected_revision: request.version, note_id: request.body.note_id,
  accepted: { ...request.body, store_id: "berts", actor_id: "usr_test", note_id: request.body.note_id,
    revision: request.version + 1, recorded_at: "2026-10-25T14:00:00+00:00", status: ["submit", "correct"].includes(request.body.action) ? "submitted" : "draft" },
  current: current || handoffNote({ ...request.body, id: request.body.note_id, revision: request.version + 1,
    status: ["submit", "correct"].includes(request.body.action) ? "submitted" : "draft",
    first_submitted_at: ["submit", "correct"].includes(request.body.action) ? "2026-10-25T14:00:00+00:00" : null }) });
