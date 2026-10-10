# Prep progress and reconciliation — October 7, 2026

This local milestone extends the manager execution workflow with partial production
and reviewed corrections/voids. Changes remain uncommitted and unpublished; PR #14
is the unchanged earlier foundation checkpoint. No real import, operational database
write, feature enablement or deployment is included. The earlier execution document
and snapshot retain the preceding one-batch checkpoint and its evidence.

## Progress is independent of planned quantity

A released task can link several reviewed production batches through `link` commands.
Each whole batch root belongs to one task across all days and tracks, even after a
correction or void. There is no editable link quantity, fractional batch allocation
or automatic redistribution between tasks. Record the measured native production
first, then select its current product/recipe/location/service-date evidence.

Linking production leaves the task open or in progress. A separate reviewed `finish`
command records the manager's decision that the task is finished. It requires
positive current reviewed production and no changed evidence awaiting reconciliation.
It does not create another batch, require produced quantity to equal the plan, or
automatically finish a task when its quantity reaches the par. The earlier one-batch
`complete` command remains supported for a task without previous production links.

For example, a planned four-pound task can record 1.123456789012 pounds and then
2.000000000001 pounds. Its reviewed output is exactly **3.123456789013 pounds**, and
the task remains in progress until the manager finishes it with a reason. Planned
output and measured output remain distinct for variance analysis.

Per-task projections expose planned base quantity, effective current recorded
quantity, reviewed current quantity, an explicit closed decision, and status:
open, in progress, complete or needs review. Exact sums are calculated in PostgreSQL
numeric and returned as decimal strings. No floating-point summation occurs. A
changed batch remains visible in the effective total but is excluded from the
reviewed total until its latest version is acknowledged.

## Review corrected or voided production

When a linked batch is corrected, its original task link remains immutable. A
`reconcile` command selects that original link and the latest current version of
the same production root, with a reason and explicit task outcome. The preview
retains original link evidence, current batch evidence and the complete prior task
progress, so a further correction or another command invalidates the review.

For positive corrected production, the manager can keep/reopen the task for further
production or explicitly finish it. Other changed linked batches must also be
reviewed before any command can finish the task. Repeated corrections require
another review; an already acknowledged version cannot be reconciled again simply
to toggle task state.

A void must reopen or keep the task open. Its effective and reviewed production
contribution becomes zero, and its original root remains reserved to that task.
After review, newly recorded replacement production can be linked and the task
finished. If other valid batches remain, finishing requires a separate explicit
decision. A task with no positive reviewed production cannot be finished.

Corrections can record a different reviewed recipe version for the same prepared
product while preserving the production root's original location/date identity.
Reconciliation exposes the changed recipe and actual production evidence instead
of pretending it still used the task's planned recipe. New production links must
still match the pinned task recipe. Future arbitrary task reassignment or splitting
one batch across tasks requires a separate reviewed allocation workflow.

The released list stays pinned once any production history has been linked,
including partial or subsequently voided production. Task reconciliation does not
reopen the whole dated draft or reinterpret its count/par/recipe source evidence.

## Integrity and migration

`20261007_prep_progress.sql` follows `20261007_prep_execution.sql`. It adds nullable
reconciliation identity/outcome fields, extends the immutable action contract and
replaces the former one-task/one-batch constraints with once-per-production-root
linking plus reviewed task-state guards. The original rows, timestamps, review
snapshots/hashes and request fingerprints are preserved. Legacy release/reopen/
complete command serialization remains identical so exact old retries still work
after the additive upgrade.

Database guards require matching task, draft, list, location, released phase,
current production root and full reviewed evidence. They reject empty finish,
fabricated progress totals, reused roots, unchanged reconciliations, incorrect
original links, closing against a void, and closing while another link changed.
Commands and store revisions roll back atomically on failure. Release/reopen
phase lookups now explicitly select those two actions, so partial progress cannot
accidentally unlock a released draft. Installed database guards still apply when
the feature flag is off.

The existing `PREP_EXECUTION_ENABLED` and `REACT_APP_PREP_EXECUTION` gates remain
false in repository examples. Older schemas retain the earlier three commands;
new commands are held until the progress migration is present. Existing account
authorization remains owner/manager for these writes; no login or staff-role
redesign is included.

The manager panel retains exact uncertain command requests through signed-in
navigation, invalidates previews after evidence edits, and validates location,
date, track, revision, command hash, history and task-progress acknowledgements.
An unconfirmed response cannot announce success or clear the request. This remains
in-memory draft retention, without a promise across logout or browser reload.

## Accounting and remaining work

All progress and reconciliation commands append references and decisions only.
They create no production events or movements and never change purchases,
purchased-item physical counts, count valuations, tax/fee records or Food Cost.
Native batch corrections retain their existing analytical reversal/replacement
movements; reconciliation does not perform those corrections a second time.
Track 1 remains the accounting baseline, while prep and future Toast sales explain it.

Local tests use invented fixtures and disposable loopback PostgreSQL outside
synced Documents/Drive. The package preserves direct SQL guards, concurrent retries
and conflicts, exact quantities, old-schema upgrade proof, whole SQL restore and
frontend acknowledgement/retention evidence. These checks are not live browser,
managed-platform or production proof.

Final verification passed: 329 frontend tests across 40 suites, 30 distinct backend
checks across the main run and two focused rechecks, 23 offline checks, whole SQL
restore, additive upgrade and production build with three existing hook warnings.
The main run had a connection timeout and a fixture cached-statement error after
DDL. Upgrade testing now recycles fixture connections, matching a stopped-app
migration/restart rehearsal; the application pool already disables statement
caching. Both cases passed rechecks. All attempts are retained in the package.

Next: native staff prep count submissions and verified container execution, then
staff execution authorization/assignment and the remaining integration contracts.
Arbitrary batch allocation/reassignment and durable browser-reload recovery remain
separate work. Toast remains a future analytical integration.
