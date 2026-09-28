import React, { useEffect, useMemo, useState } from "react";
import { Check, Clock3, MinusCircle } from "lucide-react";
import * as api from "../lib/api";
import { fmtDate, fmtMoney, itemDerived, normalizeRecipeSchema, preferredSku, recipeCostSummary, todayISO } from "../lib/calc";
import { EmptyState, Field, MetricCard, Pill, SectionLabel, cardCls, inpCls, btnAcc, btnGhost } from "./common";

function recipeCostIsCalculable(recipe, itemsByCN, recipesById, stack = new Set()) {
  if (!recipe || stack.has(recipe.id) || !recipe.lines?.length) return false;
  const nextStack = new Set(stack);
  nextStack.add(recipe.id);
  let hasCostedInput = false;

  for (const line of recipe.lines) {
    const qty = Number(line.qty ?? line.qtyPortions) || 0;
    if (qty <= 0) continue;
    if (line.sourceType === "prep") {
      if (!recipeCostIsCalculable(recipesById.get(line.recipeId), itemsByCN, recipesById, nextStack)) return false;
      hasCostedInput = true;
      continue;
    }
    const item = itemsByCN.get(line.controlNumber);
    const sku = item && preferredSku(item);
    const derived = item && itemDerived(item);
    if (!sku || sku.price == null || sku.price === "" || !Number.isFinite(Number(sku.price)) || derived.portionsPerUnit <= 0) return false;
    hasCostedInput = true;
  }
  return hasCostedInput;
}

function taskCostPerUnit(task, itemsByCN, recipes, recipesById) {
  if (task.recipeId) {
    const recipe = recipesById.get(task.recipeId);
    if (!recipeCostIsCalculable(recipe, itemsByCN, recipesById)) return null;
    return recipeCostSummary(recipe, [...itemsByCN.values()], recipes).totalCost;
  }
  const item = itemsByCN.get(task.controlNumber);
  const sku = item && preferredSku(item);
  const derived = item && itemDerived(item);
  const capacity = Number(task.vesselCapacity) || 0;
  if (!item || !sku || sku.price == null || sku.price === "" || !Number.isFinite(Number(sku.price)) || derived.portionsPerUnit <= 0 || capacity <= 0) return null;
  return capacity * derived.costPerPortion;
}

function listCostSummary(list, items, recipes) {
  if (!list) return { total: null, unpriced: 0, taskCosts: new Map() };
  const itemsByCN = new Map(items.map((item) => [item.controlNumber, item]));
  const recipesById = new Map(recipes.map((recipe) => [recipe.id, recipe]));
  let total = 0;
  let unpriced = 0;
  const taskCosts = new Map();
  (list.tasks || []).filter((task) => !task.removed).forEach((task) => {
    const costPerUnit = taskCostPerUnit(task, itemsByCN, recipes, recipesById);
    if (costPerUnit == null) {
      unpriced += 1;
      taskCosts.set(task.id, null);
    } else {
      const estimated = costPerUnit * (Number(task.batchesPlanned) || 0);
      total += estimated;
      taskCosts.set(task.id, { estimated, completed: costPerUnit * (Number(task.batchesDone) || 0) });
    }
  });
  return { total, unpriced, taskCosts };
}

function taskProgress(task, released) {
  const planned = Number(task.batchesPlanned) || 0;
  const done = Number(task.batchesDone) || 0;
  if (planned <= 0) return { label: "Not needed", done: true, color: "#94A3B8", bg: "#1E293B" };
  if (done >= planned) return { label: "Complete", done: true, color: "#10B981", bg: "rgba(16,185,129,0.12)" };
  if (done > 0) return { label: "In progress", done: false, color: "#F59E0B", bg: "rgba(245,158,11,0.12)" };
  if (!released) return { label: "Awaiting release", done: false, color: "#94A3B8", bg: "#1E293B" };
  return { label: "Not started", done: false, color: "#94A3B8", bg: "#1E293B" };
}

export function DashboardPrepWindow({ rid, items, dishes }) {
  const [track, setTrack] = useState("daily");
  const [date, setDate] = useState(todayISO());
  const [lists, setLists] = useState({ daily: null, bulk: null });
  const [failed, setFailed] = useState({ daily: false, bulk: false });
  const [loading, setLoading] = useState(true);
  const recipes = useMemo(() => dishes.map(normalizeRecipeSchema), [dishes]);
  const costs = useMemo(() => ({
    daily: listCostSummary(lists.daily, items, recipes),
    bulk: listCostSummary(lists.bulk, items, recipes),
  }), [lists, items, recipes]);
  const selectedList = lists[track];
  const selectedCosts = costs[track];
  const tasks = (selectedList?.tasks || []).filter((task) => !task.removed);
  const completedCount = tasks.filter((task) => taskProgress(task, selectedList?.status === "released").done).length;
  const allComplete = tasks.length > 0 && completedCount === tasks.length;

  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      const results = await Promise.allSettled([
        api.getPrepList(rid, date, "daily"),
        api.getPrepList(rid, date, "bulk"),
      ]);
      if (cancelled) return;
      setLists({
        daily: results[0].status === "fulfilled" ? results[0].value.list : null,
        bulk: results[1].status === "fulfilled" ? results[1].value.list : null,
      });
      setFailed({ daily: results[0].status === "rejected", bulk: results[1].status === "rejected" });
      setLoading(false);
    };
    setLoading(true);
    load();
    const timer = setInterval(load, 30000);
    return () => { cancelled = true; clearInterval(timer); };
  }, [rid, date]);

  const costValue = (key) => {
    const list = lists[key];
    const summary = costs[key];
    if (!list) return "—";
    const pricedTasks = (list.tasks || []).filter((task) => !task.removed).length - summary.unpriced;
    return pricedTasks === 0 && (list.tasks || []).some((task) => !task.removed) ? "—" : fmtMoney(summary.total);
  };
  const costSub = (key) => {
    const list = lists[key];
    if (!list) return failed[key] ? "Couldn't load this prep list" : `No prep list for ${fmtDate(date)}`;
    const tasksCount = (list.tasks || []).filter((task) => !task.removed).length;
    const pricedCount = tasksCount - costs[key].unpriced;
    return costs[key].unpriced ? `${pricedCount} priced · ${costs[key].unpriced} not calculable` : `${pricedCount} priced prep task${pricedCount === 1 ? "" : "s"}`;
  };

  return (
    <section className={`${cardCls} p-5 mb-6`} data-testid="dashboard-prep-window">
      <div className="flex justify-between items-end gap-3 flex-wrap mb-4">
        <div>
          <SectionLabel>Prep Window</SectionLabel>
          <div className="text-xs text-slate-500">Track task completion and estimated ingredient cost for each prep team.</div>
        </div>
        <Field label="Prep-for date">
          <input type="date" className={inpCls} data-testid="dashboard-prep-date" value={date} onChange={(event) => setDate(event.target.value)} />
        </Field>
      </div>

      <div className="grid gap-3 mb-4" style={{ gridTemplateColumns: "repeat(auto-fit,minmax(190px,1fr))" }}>
        <MetricCard testId="daily-prep-cost" label="Estimated Daily Prep Cost" value={costValue("daily")} sub={costSub("daily")} />
        <MetricCard testId="bulk-prep-cost" label="Estimated Bulk Prep Cost" value={costValue("bulk")} sub={costSub("bulk")} />
      </div>

      <div className="flex justify-between items-center gap-3 flex-wrap mb-3">
        <div className="flex gap-2" role="group" aria-label="Prep list track" data-testid="dashboard-prep-track-selector">
          <button className={track === "daily" ? btnAcc : btnGhost} aria-pressed={track === "daily"} onClick={() => setTrack("daily")} data-testid="dashboard-prep-track-daily">Daily Prep</button>
          <button className={track === "bulk" ? btnAcc : btnGhost} aria-pressed={track === "bulk"} onClick={() => setTrack("bulk")} data-testid="dashboard-prep-track-bulk">Bulk Prep</button>
        </div>
        {selectedList && (
          <div className="flex gap-2 items-center">
            <Pill color={selectedList.status === "released" ? "#10B981" : "#F59E0B"} bg={selectedList.status === "released" ? "rgba(16,185,129,0.12)" : "rgba(245,158,11,0.12)"}>
              {selectedList.status === "released" ? "Released" : "Draft"}
            </Pill>
            <Pill color="#94A3B8" bg="#1E293B">{completedCount}/{tasks.length} complete</Pill>
          </div>
        )}
      </div>

      {loading && !selectedList ? (
        <div className="text-slate-500 text-sm py-5 text-center" data-testid="dashboard-prep-loading">Loading prep list…</div>
      ) : failed[track] ? (
        <EmptyState text="Couldn't load this prep list. Try again shortly." />
      ) : !selectedList ? (
        <EmptyState text={`No ${track === "daily" ? "Daily" : "Bulk"} Prep list for ${fmtDate(date)} yet.`} />
      ) : tasks.length === 0 ? (
        <EmptyState text="This prep list has no active tasks." good />
      ) : (
        <>
          {allComplete && (
            <div className="bg-emerald-500/10 border border-emerald-500/40 rounded-lg px-3.5 py-2.5 text-emerald-300 text-xs mb-3" data-testid="dashboard-prep-complete-banner">
              <b>All prep is complete.</b> Completed item costs are shown where ingredient pricing is available.
            </div>
          )}
          <div className="overflow-x-auto">
            <table className="ops-table" data-testid="dashboard-prep-task-table">
              <thead><tr><th>Prep Task</th><th>Status</th><th>Completed By</th><th>Cost</th></tr></thead>
              <tbody>
                {tasks.map((task) => {
                  const progress = taskProgress(task, selectedList.status === "released");
                  const taskCost = selectedCosts.taskCosts.get(task.id);
                  const planned = Number(task.batchesPlanned) || 0;
                  const done = Number(task.batchesDone) || 0;
                  return (
                    <tr key={task.id} data-testid={`dashboard-prep-task-${task.id}`}>
                      <td>
                        <div className="font-semibold text-slate-200">{task.name}</div>
                        <div className="text-[11px] text-slate-500">{task.taskType === "vessel" ? `${done}/${planned} ${task.vesselName || "vessels"}` : `${done}/${planned} batches`}</div>
                      </td>
                      <td>
                        <span className="inline-flex items-center gap-1.5 text-xs font-semibold" style={{ color: progress.color }}>
                          {progress.done ? (planned === 0 ? <MinusCircle size={13} /> : <Check size={13} />) : <Clock3 size={13} />}
                          {progress.label}
                        </span>
                      </td>
                      <td className="text-xs text-slate-300">{done > 0 && task.doneBy ? `${progress.done ? "Completed" : "Last prepped"} by ${task.doneBy}` : "—"}</td>
                      <td className="num text-xs">
                        {taskCost == null ? "—" : progress.done ? fmtMoney(taskCost.completed) : done > 0 ? `${fmtMoney(taskCost.completed)} done · ${fmtMoney(taskCost.estimated)} est.` : `${fmtMoney(taskCost.estimated)} est.`}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </>
      )}
    </section>
  );
}
