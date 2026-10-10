# Manager prep execution — October 7, 2026

This local continuation adds manager release, reopen and task completion to the
reviewed dated prep drafts. All changes remain uncommitted and unpublished. PR #14
is unchanged; no feature enablement, operational database write, real invoice import
or deployment is included. Earlier milestone documents describe their original checkpoints.

## Release and revision history

A manager previews and explicitly reviews a command against the saved draft and
the observed execution revision. Release rechecks the full draft source evidence:
the active standing plan scope, recipe ancestry, verified units, day overrides and
selected latest prior-day physical count. Changed sources require a fresh saved
draft. Included tasks with unknown quantities cannot be released. A known zero
needs no production and cannot be marked complete by linking a positive batch.

Release pins the exact immutable draft version. Subsequent edits are held until
the manager reopens it with a reason. Reopen is allowed only before any task has
production linked. It appends history instead of deleting the release or rewriting
the draft. The original draft review continues to describe a draft; execution
status comes from the separate command history, preserving the earlier sealed facts.

The database enforces continuous execution revisions, list/location/draft identity,
valid release/reopen/completion transitions, positive resolved completion tasks,
selected current recipe/unit/count references, current production identity and
matching immutable evidence. Store-row locks serialize commands with draft edits.
It freezes released draft edits even with the execution flag disabled. API source
rechecks additionally cover mutable legacy ingredient/recipe ancestry; the SQL
guard is not a replacement for that full source review.

## Completion uses measured production once

Record a reviewed native batch in Prep Production first, including its measured
output and complete ingredient evidence. The manager then selects a released task
and links its completion to that existing current production record. The batch
must have the task's pinned recipe and prepared product, the same location and
service calendar date, and positive measured output. Opening prep stock, voided or
superseded batches, other recipes/products/days/locations and omitted/zero tasks
cannot complete the task.

The measured output may differ from the planned output. Both remain visible and
the manager supplies a completion reason. Planning a four-pound task and recording
three pounds of measured production retains **four planned and three produced**;
completion does not substitute the plan for actual production or guess a batch count.

Each task accepts one completion, and each production root can complete only one
task across all days/tracks. A correction of the same batch cannot be relinked to
another task. Completion appends an evidence reference, **not another production
event or inventory movement**. Native production's existing analytical movements
remain the only batch quantity evidence. Purchased-item counts and received purchases
remain Track 1's accounting and Food Cost baseline.

Native batch corrections and voids continue to preserve their own history. The
completion retains its original batch reference while the current execution view
shows the effective latest batch and a manager-review flag whenever it changed.
A void is visibly flagged; it is not silently shown as valid completed production.
This milestone does not clear that flag or erase/reassign completion. A later
reviewed execution reconciliation command is required before that operating
scenario can be considered finished.

## Save integrity and interface

Commands require an `If-Match` execution revision, matching fresh preview hash,
strict explicit review and UUID request key. Revision zero means no execution
history, separate from the dated draft's own revision. Atomic insertion preserves
account-derived actor attribution and rolls back store revisions on failure.
Same-key exact retries acknowledge the original command and return the current
execution state separately. A changed body, actor, date, track or observed version
cannot reuse the key.

The manager panel displays planned task quantities alongside reviewed measured
batch candidates, and shows corrections/voids. Day editors hold released drafts.
Inputs invalidate reviewed previews when changed. Uncertain requests retain their
exact key/body/version through signed-in navigation; mismatched acknowledgements
cannot announce success or clear them. Conflicts retain the reason and require a
fresh read/preview. Late responses cannot alter another service day. This in-memory
retention does not promise persistence across logout or browser reload.

## Schema, gating and remaining workflow

`20261007_prep_execution.sql` is additive and follows the dated draft migration and
`20261005_prep_opening_sources.sql` production/opening boundary. It adds immutable
`prep_inventory.execution_events`; it changes no legacy raw data or accounting facts.
`PREP_EXECUTION_ENABLED` requires dated drafts and all their existing dependencies.
The corresponding frontend flag is `REACT_APP_PREP_EXECUTION`. Both example flags
remain **false**. Disabling the flag does not unfreeze legacy or released-draft writes.

These commands use existing owner/manager purchase authorization. Staff assignment,
staff execution access, partial/multiple-batch completion, corrected-completion
reconciliation, staff prep count submissions and verified container execution remain
future work. No login redesign or guessed staff identity is introduced here.

## Verification

Invented fixtures run on disposable loopback PostgreSQL outside synced Documents
and Drive. Checks cover release/reopen/edit history, concurrent exact retries and
different-key conflicts, stale plan/count sources, unknown quantities, measured
output differences, cross-track batch reuse, correction/void visibility, direct SQL
guards, atomic rollback, flag-off holds and whole SQL restore with retry readback.
Frontend component/adapter checks cover acknowledgement validation, retained exact
requests, conflicts, released editor holds and stale day callbacks. The review
package includes exact source hashes, cumulative patch, test/build results and the
unchanged earlier snapshot. These are local checks, not live browser or deployment proof.

Final verification passed: 324 frontend tests across 40 suites, 49 selected backend
checks, 23 offline checks and production build with the same three existing hook
warnings. One frontend adapter test initially expected an unquoted revision header;
its expectation was corrected to the existing quoted ETag contract. Both the
attempt and final passing results are retained.

Next: reviewed execution reconciliation and partial production linkage, then staff
prep counts and verified container workflows. Toast sales remain a later analytical
track and cannot change Track 1 accounting inventory.
