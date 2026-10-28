import { canonicalStoreId } from "./purchaseContract";
import { readStateWithDeadline } from "./stateRead";
import { overviewDecimal, decimalText, overviewDifference } from "./overviewDecimal";

export const B1_SCOPE = Object.freeze({ rid: "berts", day: "2026-10-26", track: "daily" });
export const overviewUuid = v => typeof v === "string" && /^[a-f0-9]{8}(?:-[a-f0-9]{4}){3}-[a-f0-9]{12}$/i.test(v);

const text = v => typeof v === "string" && v.trim().length > 0;
const integer = v => Number.isSafeInteger(v) && v >= 0;
const unique = values => new Set(values).size === values.length;
export const validOverviewDay = value => {
  if (typeof value !== "string" || !/^\d{4}-\d{2}-\d{2}$/.test(value)) return false;
  const time = Date.parse(`${value}T00:00:00Z`);
  return Number.isFinite(time) && new Date(time).toISOString().slice(0, 10) === value;
};
export function overviewContext(rid, day, track, user) {
  if (!["berts", "rudds", "papa_leonis"].includes(rid) || !validOverviewDay(day)
      || !["daily", "bulk"].includes(track) || !text(user?.id)
      || !["owner", "manager"].includes(user?.role)
      || !Array.isArray(user.locations) || !user.locations.every(text)
      || (user.role === "manager" && !user.locations?.includes(rid))) return null;
  return { rid, storeId: canonicalStoreId(rid), day, track,
    key: JSON.stringify([user.id, user.role, [...(user.locations || [])].sort(), rid, day, track]) };
}
function checked(condition) { if (!condition) throw new Error("Overview source not confirmed"); }

export function countOverview(rows, context) {
  checked(Array.isArray(rows) && unique(rows.map(r => r?.id)));
  for (const r of rows) {
    checked(text(r?.id) && r.store_id === context.storeId && text(r.scope_id)
      && integer(r.scope_revision) && validOverviewDay(r.count_date)
      && ["before_receipts", "after_receipts"].includes(r.timing)
      && ["complete", "incomplete"].includes(r.status)
      && typeof r.recorded_at === "string" && /(?:Z|[+-]\d{2}:\d{2})$/.test(r.recorded_at)
      && Number.isFinite(Date.parse(r.recorded_at))
      && (r.corrects_snapshot_id === null || (text(r.corrects_snapshot_id)
        && r.corrects_snapshot_id !== r.id && rows.some(p => p.id === r.corrects_snapshot_id))));
  }
  for (const row of rows) {
    const visited = new Set([row.id]);
    let previous = row.corrects_snapshot_id;
    while (previous) {
      checked(!visited.has(previous));
      visited.add(previous);
      previous = rows.find(r => r.id === previous).corrects_snapshot_id;
    }
  }
  // Current corrected history, not a reconstruction of what was known on that date.
  const superseded = new Set(rows.map(r => r.corrects_snapshot_id).filter(Boolean));
  const current = rows.filter(r => !superseded.has(r.id) && r.count_date <= context.day)
    .sort((a, b) => b.count_date.localeCompare(a.count_date)
      || (b.timing === "after_receipts") - (a.timing === "after_receipts")
      || Date.parse(b.recorded_at) - Date.parse(a.recorded_at) || b.id.localeCompare(a.id));
  return { state: "ready", count: current[0] ? {
    id: current[0].id, date: current[0].count_date, timing: current[0].timing,
    status: current[0].status, scopeRevision: current[0].scope_revision,
  } : null };
}

export function prepOverview(value, context) {
  checked(value?.store_id === context.storeId && value.prep_date === context.day
    && value.track === context.track && integer(value.revision)
    && ["draft", "released"].includes(value.status) && Array.isArray(value.tasks)
    && Array.isArray(value.completions) && unique(value.tasks.map(t => t?.id))
    && typeof value.progress_supported === "boolean");
  checked(value.draft_version_id === null ? value.draft === null :
    text(value.draft_version_id) && value.draft?.id === value.draft_version_id
    && value.draft.store_id === context.storeId
    && value.draft.review_snapshot?.prep_date === context.day
    && value.draft.review_snapshot?.track === context.track);
  checked(value.draft_version_id !== null || (!value.tasks.length && !value.completions.length && value.status === "draft"));
  checked(value.status !== "released" || (value.release?.action === "release"
    && value.release.draft_version_id === value.draft_version_id && text(value.release.id)));
  for (const task of value.tasks) checked(text(task?.id) && typeof task.included === "boolean"
    && text(task.task_snapshot?.name));
  const supported = value.progress_supported === true;
  if (supported) {
    checked(Array.isArray(value.task_progress) && value.task_progress.length === value.tasks.length
      && unique(value.task_progress.map(p => p?.task_id)));
    for (const p of value.task_progress) checked(value.tasks.some(t => t.id === p?.task_id)
      && ["open", "in_progress", "complete", "needs_review"].includes(p.status)
      && typeof p.closed === "boolean" && typeof p.needs_review === "boolean"
      && (p.needs_review ? p.status === "needs_review" : p.closed ? p.status === "complete" : ["open", "in_progress"].includes(p.status)));
  }
  const flagged = new Set();
  let historicalReviews = 0;
  for (const completion of value.completions) {
    checked(text(completion?.task_id) && typeof completion.needs_review === "boolean");
    if (completion.needs_review) {
      if (value.tasks.some(t => t.id === completion.task_id)) flagged.add(completion.task_id);
      else historicalReviews++; // Execution history can refer to an earlier draft's tasks.
    }
  }
  const tasks = value.tasks.filter(t => t.included).map(task => {
    const p = supported ? value.task_progress.find(v => v.task_id === task.id) : null;
    return { id: task.id, name: task.task_snapshot.name,
      state: flagged.has(task.id) || p?.needs_review ? "needs_review" : p?.status || "unavailable" };
  });
  return { state: "ready", status: value.status, revision: value.revision,
    draftVersionId: value.draft_version_id,
    hasDraft: value.draft_version_id !== null, progressAvailable: supported, historicalReviews, tasks };
}

// B1 uses native base quantities; no report totals or stock balance are inferred.
export function b1PrepOverview(value, context) {
  const result = prepOverview(value, context);
  for (const task of value.tasks) {
    checked(overviewUuid(task.id) && task.store_id === context.storeId
      && task.version_id === value.draft_version_id && overviewUuid(task.version_id)
      && ["product_id", "planning_version_id", "recipe_version_id", "unit_profile_id"].every(k =>
        overviewUuid(task[k]) && task[k] === task.task_snapshot[k]));
  }
  if (value.draft_version_id !== null) checked(overviewUuid(value.draft_version_id));
  checked(unique(value.tasks.map(t => t.product_id)));
  return { ...result, tasks: result.tasks.map(row => {
    const task = value.tasks.find(t => t.id === row.id);
    const progress = value.progress_supported ? value.task_progress.find(p => p.task_id === row.id) : null;
    const changedIds = Array.isArray(progress?.links) && progress.links.some(l => l?.acknowledged_batch_event_id !== l?.effective_batch_event_id);
    const identity = { productId: task.product_id, recipeVersionId: task.recipe_version_id,
      profileId: task.unit_profile_id, planningVersionId: task.planning_version_id };
    try {
      const unit = task.task_snapshot.base_unit;
      checked(["lb", "oz", "g", "kg", "fl_oz", "ml", "l", "gal", "each"].includes(unit) && progress);
      const planned = overviewDecimal(task.planned_base_quantity);
      checked(planned === overviewDecimal(task.task_snapshot.planned_base_quantity)
        && planned === overviewDecimal(progress.planned_base_quantity));
      const reviewed = overviewDecimal(progress.reviewed_base_quantity);
      const effective = overviewDecimal(progress.effective_base_quantity);
      checked(Array.isArray(progress.links) && unique(progress.links.map(l => l?.execution_id))
        && unique(progress.links.map(l => l?.batch_root_id)));
      let actualSum = BigInt(0), reviewedSum = BigInt(0), changed = row.state === "needs_review";
      const links = progress.links.map(link => {
        checked(["execution_id", "acknowledged_batch_event_id", "effective_batch_event_id", "batch_root_id"].every(k => overviewUuid(link?.[k]))
          && typeof link.needs_review === "boolean");
        const mismatch = link.acknowledged_batch_event_id !== link.effective_batch_event_id;
        changed = changed || mismatch || link.needs_review;
        checked(link.needs_review === mismatch);
        const amount = overviewDecimal(link.effective_base_quantity);
        const completion = value.completions.find(c => c.execution_id === link.execution_id);
        checked(completion?.task_id === task.id && completion.acknowledged_batch_event_id === link.acknowledged_batch_event_id
          && completion.effective_batch?.id === link.effective_batch_event_id
          && completion.effective_batch.root_id === link.batch_root_id
          && completion.effective_batch.store_id === context.storeId
          && completion.effective_batch.product_id === task.product_id
          && completion.effective_batch.base_unit === unit && completion.needs_review === mismatch
          && overviewUuid(completion.effective_batch.product_version_id)
          && ["initial", "replacement", "void"].includes(completion.effective_batch.kind));
        checked(amount === (completion.effective_batch.kind === "void" ? BigInt(0)
          : overviewDecimal(completion.effective_batch.review_snapshot?.usableBaseOutput)));
        actualSum += amount;
        if (!mismatch) reviewedSum += amount;
        return { ...link, product_version_id: completion.effective_batch.product_version_id };
      });
      checked(actualSum === effective && reviewedSum === reviewed
        && value.completions.filter(c => c.task_id === task.id).length === links.length);
      const quantities = { unit, planned: decimalText(planned), reviewed: decimalText(reviewed),
        effective: decimalText(effective), links, closed: progress.closed };
      return { ...row, ...identity, ...quantities, state: changed ? "needs_review" : row.state,
        quantityState: changed ? "review_required" : "ready",
        ...(changed ? {} : overviewDifference(task.planned_base_quantity, progress.reviewed_base_quantity)) };
    } catch {
      return { ...row, ...identity, state: changedIds ? "needs_review" : row.state, quantityState: "unavailable" };
    }
  }) };
}

// GET readers only. Existing API authentication and server authorization remain authoritative.
export async function loadManagerOverview(context, api, receive) {
  if (!context) return;
  const sections = [
    ["counts", api.actualInventoryEnabled === true, () => api.actualCounts(context.rid), countOverview],
    ["prep", api.prepExecutionEnabled === true, () => api.prepExecution(context.rid, context.day, context.track), prepOverview],
  ];
  await Promise.all(sections.map(async ([name, enabled, read, validate]) => {
    if (!enabled) { receive(name, { state: "unavailable", message: "This workflow is not enabled." }); return; }
    try {
      const value = await readStateWithDeadline(read, "Overview read timed out.");
      receive(name, validate(value, context));
    } catch {
      receive(name, { state: "unavailable", message: "This section could not be confirmed. Refresh or open the original workflow." });
    }
  }));
}

export function rememberedOverview(storage, actorId, rid, fallbackDay) {
  try {
    const saved = JSON.parse(storage?.getItem(`manager-overview:${actorId}:${rid}`) || "null");
    if (saved && validOverviewDay(saved.day) && ["daily", "bulk"].includes(saved.track)) return { day: saved.day, track: saved.track };
  } catch { /* View preferences are optional; business records are never cached here. */ }
  return { day: fallbackDay, track: "bulk" };
}
export function overviewStorage() {
  try { return window.sessionStorage; } catch { return null; }
}
