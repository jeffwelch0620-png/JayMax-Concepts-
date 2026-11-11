// AM-to-PM prep handoff (Jeff 2026-11-11). Pure helpers for the Manager handoff tab: which tasks can be
// carried, how a handoff's state reads to the signed-in manager, and what changed in its linked prep.

export function amount(value) {
  const n = Number(value);
  return Number.isFinite(n) ? String(Math.round(n * 100) / 100) : "?";
}

// Released, unfinished tasks with no open handoff.
export function carryable(tasks = [], handoffs = []) {
  const open = new Set(handoffs.filter(h => h.status !== "withdrawn").map(h => h.task_id));
  return tasks.filter(t => t && t.available && !t.closed && !open.has(t.task_id));
}

const STATE = {
  waiting: { text: "Waiting for", tone: "warn" },
  accepted: { text: "Accepted by", tone: "ok" },
  needs_acceptance: { text: "Prep changed · needs acceptance again from", tone: "warn" },
  withdrawn: { text: "Withdrawn", tone: "muted" },
};

export function stateLabel(h) {
  const s = STATE[h.effective_status] || STATE.waiting;
  return { tone: s.tone, text: h.effective_status === "withdrawn" ? s.text : `${s.text} ${h.recipient}` };
}

// What the signed-in manager may do with this handoff now.
export function actionsFor(h, me, senior) {
  if (h.status === "withdrawn") return [];
  const out = [];
  if (me === h.recipient_id && h.effective_status !== "accepted") out.push("accept");
  if (me !== h.recipient_id) out.push("take_over");
  if (me === h.sender_id || senior) out.push("correct", "withdraw");
  return out;
}

const person = a => (a ? a.name : "Unassigned");

// The differences between the prep facts recorded with the handoff and the facts now.
export function prepChanges(recorded, current) {
  if (!current) return ["The linked prep task can no longer be read."];
  if (!recorded) return [];
  const out = [];
  if (!current.available && recorded.available) out.push("The prep list was reopened or replaced; this task is no longer released.");
  if (current.closed && !recorded.closed) out.push("The task was finished.");
  if (current.needs_review && !recorded.needs_review) out.push("Recorded production now needs review.");
  if (recorded.remaining_base_quantity !== current.remaining_base_quantity)
    out.push(`Remaining went from ${amount(recorded.remaining_base_quantity)} to ${amount(current.remaining_base_quantity)} ${current.base_unit}.`);
  if ((recorded.assignee?.id || null) !== (current.assignee?.id || null))
    out.push(`Assignee changed from ${person(recorded.assignee)} to ${person(current.assignee)}.`);
  if (recorded.planned_base_quantity !== current.planned_base_quantity)
    out.push(`Planned amount changed from ${amount(recorded.planned_base_quantity)} to ${amount(current.planned_base_quantity)} ${current.base_unit}.`);
  if (!out.length && recorded.status !== current.status) out.push(`Status changed from ${recorded.status} to ${current.status}.`);
  return out;
}

// The command body for one action, from the handoff (or new task) and the form values.
export function commandBody(action, { handoffId, day, track, task, handoff, form = {} }) {
  const facts = handoff ? handoff.current_prep : task;
  const body = { action, handoff_id: handoffId || handoff.id, business_date: day, prep_track: track,
    task_id: handoff ? handoff.task_id : task.task_id, prep_hash: facts.prep_hash };
  if (action === "send" || action === "correct") {
    Object.assign(body, { recipient_id: form.recipient_id, remaining_base_quantity: String(form.remaining).trim(),
      ready_by: form.ready_by, note: (form.note || "").trim() });
  }
  if (action === "correct" || action === "take_over" || action === "withdraw") body.reason = (form.reason || "").trim();
  return body;
}

export function formProblem(action, form = {}) {
  if (action === "send" || action === "correct") {
    if (!form.recipient_id) return "Choose the evening manager.";
    if (!/^\d+(\.\d{1,12})?$/.test(String(form.remaining ?? "").trim())) return "Enter the remaining amount as a number.";
    if (!/^([01]\d|2[0-3]):[0-5]\d$/.test(form.ready_by || "")) return "Enter a ready-by time.";
  }
  if (["correct", "take_over", "withdraw"].includes(action) && !(form.reason || "").trim()) return "Write a reason.";
  return "";
}
