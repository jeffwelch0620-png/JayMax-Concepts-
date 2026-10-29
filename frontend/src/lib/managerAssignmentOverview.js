// Selective Package 1 read/join behavior. No writer component is imported.
import { prepQuantityOverview, overviewUuid } from "./managerOverview";
import { readStateWithDeadline } from "./stateRead";
const ordered = v => Array.isArray(v) ? v.map(ordered) : v && typeof v === "object"
  ? Object.fromEntries(Object.keys(v).sort().map(k => [k, ordered(v[k])])) : v;
const same = (a, b) => JSON.stringify(ordered(a)) === JSON.stringify(ordered(b));
function check(ok) { if (!ok) throw new Error("Assignment source not confirmed."); }
export function assignmentOverview(value, context, expected) {
  check(value?.store_id === context.storeId && value.day === context.day && value.track === context.track);
  const prep = prepQuantityOverview(value.execution, context);
  check(prep.draftVersionId === expected.draftVersionId && prep.revision === expected.revision
    && prep.status === expected.status && same(prep.tasks, expected.tasks)
    && Array.isArray(value.members) && Array.isArray(value.assignments)
    && new Set(value.members.map(m => m?.id)).size === value.members.length
    && value.members.every(m => overviewUuid(m?.id) && m.store_id === context.storeId
      && typeof m.name === "string" && typeof m.active === "boolean")
    && value.assignments.length === value.execution.tasks.length
    && new Set(value.assignments.map(a => a?.task_id)).size === value.assignments.length);
  for (const a of value.assignments) {
    check(value.execution.tasks.some(t => t.id === a?.task_id) && typeof a.roster_changed === "boolean"
      && Array.isArray(a.history) && same(a.current, a.history.at(-1) || null));
    a.history.forEach((h, i) => check(overviewUuid(h?.id) && h.store_id === context.storeId && h.task_id === a.task_id
      && h.revision === i + 1 && h.predecessor_id === (i ? a.history[i - 1].id : null)
      && (h.staff_member_id === null || overviewUuid(h.staff_member_id))));
    check(new Set(a.history.map(h => h.id)).size === a.history.length);
    check(!a.current_member || (a.current_member.id === a.current?.staff_member_id
      && value.members.some(m => same(m, a.current_member))));
  }
  return { state: "ready", executionRevision: prep.revision, tasks: prep.tasks.map(t => {
    const a = value.assignments.find(v => v.task_id === t.id), member = a.current_member;
    const assigned = !!a.current?.staff_member_id;
    const needsReview = a.roster_changed || (assigned && (!member?.active || !member.name.trim()));
    return { id: t.id, name: t.name, assignmentId: a.current?.id || null,
      revision: a.current?.revision || 0, memberId: a.current?.staff_member_id || null,
      memberName: member?.name || null,
      responsibility: needsReview ? "Needs review" : assigned ? "Assigned as recorded" : "Unassigned" };
  }) };
}
export async function loadAssignmentOverview(context, expected, api) {
  if (api.prepExecutionEnabled !== true || api.staffPrepTasksEnabled !== true) {
    return { state: "unavailable", reason: "disabled", message: "Assignments unavailable: capability is disabled." };
  }
  if (expected?.state !== "ready") return { state: "unavailable", reason: "error", message: "Assignments not confirmed: refresh the dated plan." };
  try {
    const value = await readStateWithDeadline(() => api.staffPrepTaskSetup(context.rid, context.day, context.track), "Assignment read timed out.");
    return { ...assignmentOverview(value, context, expected), readAt: new Date().toISOString() };
  } catch {
    return { state: "unavailable", reason: "error", message: "Assignments not confirmed: read failed or plan changed. Refresh." };
  }
}
