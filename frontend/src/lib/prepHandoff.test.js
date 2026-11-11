import { actionsFor, carryable, commandBody, formProblem, prepChanges, stateLabel } from "./prepHandoff";

const facts = (over = {}) => ({ task_id: "t1", name: "Ranch dressing", base_unit: "gal", planned_base_quantity: "4", reviewed_base_quantity: "1",
  remaining_base_quantity: "3", status: "in_progress", closed: false, needs_review: false, available: true,
  assignee: { id: "s1", name: "Sample cook" }, prep_hash: "a".repeat(64), ...over });
const handoff = (over = {}) => ({ id: "h1", task_id: "t1", sender_id: "am", recipient_id: "pm", recipient: "pm@example.test",
  status: "waiting", effective_status: "waiting", recorded_prep: facts(), current_prep: facts(), ...over });

test("only released, unfinished tasks without an open handoff can be carried", () => {
  const tasks = [facts(), facts({ task_id: "t2", closed: true }), facts({ task_id: "t3", available: false }), facts({ task_id: "t4" })];
  expect(carryable(tasks, [handoff()]).map(t => t.task_id)).toEqual(["t4"]);
  expect(carryable(tasks, [handoff({ status: "withdrawn" })]).map(t => t.task_id)).toEqual(["t1", "t4"]);
});

test("the named manager accepts; others take over; the sender or a GM corrects and withdraws", () => {
  expect(actionsFor(handoff(), "pm", false)).toEqual(["accept"]);
  expect(actionsFor(handoff(), "am", false)).toEqual(["take_over", "correct", "withdraw"]);
  expect(actionsFor(handoff(), "backup", false)).toEqual(["take_over"]);
  expect(actionsFor(handoff(), "gm", true)).toEqual(["take_over", "correct", "withdraw"]);
  expect(actionsFor(handoff({ status: "accepted", effective_status: "needs_acceptance" }), "pm", false)).toEqual(["accept"]);
  expect(actionsFor(handoff({ status: "accepted", effective_status: "accepted" }), "pm", false)).toEqual([]);
  expect(actionsFor(handoff({ status: "withdrawn", effective_status: "withdrawn" }), "am", true)).toEqual([]);
});

test("state reads as who holds the handoff and whether it needs acceptance again", () => {
  expect(stateLabel(handoff()).text).toBe("Waiting for pm@example.test");
  expect(stateLabel(handoff({ effective_status: "needs_acceptance" })).text).toMatch(/needs acceptance again from pm@example.test/);
  expect(stateLabel(handoff({ effective_status: "withdrawn" })).text).toBe("Withdrawn");
});

test("prep changes name the amount, assignee and availability differences", () => {
  expect(prepChanges(facts(), facts())).toEqual([]);
  expect(prepChanges(facts(), facts({ remaining_base_quantity: "1.5", assignee: null }))).toEqual([
    "Remaining went from 3 to 1.5 gal.", "Assignee changed from Sample cook to Unassigned."]);
  expect(prepChanges(facts(), facts({ available: false }))[0]).toMatch(/no longer released/);
  expect(prepChanges(facts(), null)).toEqual(["The linked prep task can no longer be read."]);
});

test("command bodies carry the reviewed prep digest and only the fields the action takes", () => {
  const form = { recipient_id: "pm", remaining: " 3 ", ready_by: "16:30", note: " Two tubs left ", reason: " PM called out " };
  expect(commandBody("send", { handoffId: "h1", day: "2026-11-11", track: "daily", task: facts(), form })).toEqual({
    action: "send", handoff_id: "h1", business_date: "2026-11-11", prep_track: "daily", task_id: "t1", prep_hash: "a".repeat(64),
    recipient_id: "pm", remaining_base_quantity: "3", ready_by: "16:30", note: "Two tubs left" });
  const accept = commandBody("accept", { day: "2026-11-11", track: "daily", handoff: handoff({ current_prep: facts({ prep_hash: "b".repeat(64) }) }) });
  expect(accept).toEqual({ action: "accept", handoff_id: "h1", business_date: "2026-11-11", prep_track: "daily", task_id: "t1", prep_hash: "b".repeat(64) });
  expect(commandBody("take_over", { day: "2026-11-11", track: "daily", handoff: handoff(), form }).reason).toBe("PM called out");
});

test("form problems are plain instructions", () => {
  expect(formProblem("send", {})).toBe("Choose the evening manager.");
  expect(formProblem("send", { recipient_id: "pm", remaining: "two", ready_by: "16:30" })).toMatch(/number/);
  expect(formProblem("send", { recipient_id: "pm", remaining: "2", ready_by: "" })).toMatch(/ready-by/);
  expect(formProblem("take_over", { reason: " " })).toBe("Write a reason.");
  expect(formProblem("accept", {})).toBe("");
});
