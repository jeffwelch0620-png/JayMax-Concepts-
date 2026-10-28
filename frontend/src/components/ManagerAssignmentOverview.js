import React from "react";
import { cardCls } from "./common";
export function ManagerAssignmentOverview({ value }) {
  return <section className={`${cardCls} p-5`} aria-label="Recorded assignments"><h2>Recorded assignments</h2>
    <p>Assignment is a roster claim, not verified employee identity, responsibility acceptance or production.</p>
    {value.state === "loading" ? <p role="status">Loading assignments…</p> : value.state !== "ready" ? <p role="status">{value.message}</p> : <>
      <p>Execution revision {value.executionRevision} · local read {value.readAt}</p>
      {!value.tasks.length && <p>No included tasks in this plan. Responsibility is not confirmed by an empty list.</p>}
      <ul>{value.tasks.map(t => <li key={t.id}>{t.name} · {t.responsibility}{t.memberName ? ` · ${t.memberName}` : ""}
        <p>Task {t.id} · assignment {t.assignmentId || "none"} · revision {t.revision} · roster ID {t.memberId || "none"}</p>
      </li>)}</ul>
    </>}
  </section>;
}
