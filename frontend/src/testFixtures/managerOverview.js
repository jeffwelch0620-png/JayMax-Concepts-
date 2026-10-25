// Fictional local test/preview inputs only. Never imported by the production App.
export const OVERVIEW_TEST_DAY = "2026-10-25";
export const overviewTestOwner = { id: "TEST-ONLY-owner", role: "owner", locations: ["berts"], email: "owner@example.invalid" };
export function overviewFixture(rid = "berts", day = OVERVIEW_TEST_DAY, track = "bulk") {
  const store = rid === "papa_leonis" ? "papa" : rid;
  const counts = [{ id: "TEST-ONLY-count", store_id: store, scope_id: "TEST-ONLY-purchased-scope",
    scope_revision: 2, count_date: day, timing: "after_receipts", status: "complete",
    recorded_at: `${day}T18:00:00-04:00`, corrects_snapshot_id: null }];
  const tasks = ["Bulk Sauce", "Portioned Protein", "Vegetable Prep"].map((name, i) => ({
    id: `TEST-ONLY-task-${i}`, included: true, task_snapshot: { name: `TEST ONLY ${name}`, source_unit: "lb" },
  }));
  const prep = { store_id: store, prep_date: day, track, revision: 4, status: "released",
    draft_version_id: "TEST-ONLY-draft", draft: { id: "TEST-ONLY-draft", store_id: store,
      review_snapshot: { prep_date: day, track } },
    release: { id: "TEST-ONLY-release", action: "release", draft_version_id: "TEST-ONLY-draft" },
    tasks, completions: [{ task_id: tasks[2].id, needs_review: true }], progress_supported: true,
    task_progress: tasks.map((t, i) => ({ task_id: t.id, status: ["open", "in_progress", "needs_review"][i],
      closed: false, needs_review: i === 2 })),
  };
  return { counts, prep };
}
