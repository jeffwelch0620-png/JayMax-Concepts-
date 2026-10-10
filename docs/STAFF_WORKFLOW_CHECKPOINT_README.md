# Staff prep workflow checkpoint — October 7, 2026

[Draft PR #16](https://github.com/jeffwelch0620-png/JayMax-Concepts-/pull/16)
publishes measured Track 2 staff/count/container workflows. The verified
implementation commit is `0c3be1819cba1782d7a29d42294e569fde624bb0`, based on
PR #15 publication commit `ae10c8cab319b7f1ed842711076bacd132653f43`.
Publication adds reviewable source and documentation. It applies no operational
migration, enables no feature, imports no real data and deploys nothing.

## Relationships established

Track 1 includes purchased inventory only. Actual usage remains opening physical
count plus received purchases minus closing physical count, using explicit count
values for Food Cost. Received date is the purchase date of record; taxes/fees
remain separate and original invoice fields remain retained.

Track 2 explains production, prepared counts, allocation and measured waste.
Staff measurements await manager acceptance. Containers reserve prepared output;
storage/service transfers preserve total contents. A measured discard pairs its
contents reduction and waste withdrawal in one transaction. No theoretical prep
or sales movement deducts/revalues Track 1. Future Toast Track 3 sold portions will
remain separate evidence for variance, planning and costing.

| Workflow | Reviewed behavior | Contract |
|---|---|---|
| Physical prep counts | Full manager-issued prepared scope, immutable staff revisions, unknown versus measured zero, atomic acceptance into one count observation. | [Staff counts](STAFF_PREP_COUNT_INTEGRITY.md) |
| Containers | Separate stated/brimful/usable capacities; measured product fill profiles; frozen units, partial fill/storage/service/unpack and independent physical counts. | [Containers](PREP_CONTAINER_INTEGRITY.md) |
| Staff tasks | Explicit date/track release, stable task/roster identities, immutable assignments/reassignments and original request replay after plan changes. | [Assignments](STAFF_PREP_TASK_INTEGRITY.md) |
| Waste | One measured compartment/category loss, paired journal, exact source-allocation arithmetic and latest-only paired reversal. | [Container waste](CONTAINER_WASTE_INTEGRITY.md) |
| Production | Full measured usable output/gross ingredients/lots, immutable drafts/withdrawals, manager acceptance/rejection and explicit optional task finish. | [Staff production](STAFF_PREP_PRODUCTION_INTEGRITY.md) |

Staff submissions, assignments, transfers and rejections do not create production.
Acceptance creates exactly one measured batch and task link, with a separate finish
event only when explicitly chosen. Partial quantities do not imply completion.
Failure of any effect or decision rolls back the transaction. Request keys bind
original scope, body and actor; lost responses are retried using the original key.
UI success requires acknowledgement of the complete matching result/history.

Shared PIN access and selected names remain claimed identity, not verified employee
identity or manager authority. PINs are excluded from snapshots and retained drafts.
Login redesign and employee account mapping remain separate work.

## Schema and evidence

Five new additive migrations follow the foundation/day-task/execution/progress
chain: `20261007_staff_prep_counts.sql`, `20261007_prep_containers.sql`,
`20261007_staff_prep_tasks.sql`, `20261007_container_waste.sql`, and
`20261007_staff_prep_production.sql`. Original legacy prep stock/log/count source
fields are retained; superseded writes are held by their installed native boundary,
including with flags off. Tables/functions are private, relationships are
store-scoped, histories are immutable and transaction seals reject orphan or late
effects. Recycle application connections after schema changes. This is not an
operational bootstrap guide.

The latest checkpoint passed **404 frontend tests / 49 suites**, **36 distinct
selected backend checks**, **23 offline checks**, production build and whole SQL
restore/private ACL checks. The backend figure combines 35 passing regression
cases with two corrected rechecks, one repeated. Previous count/container/task/
waste checkpoints retain their own separate evidence; their counts are not a
single combined suite run. Three existing hook warnings remain in PurchaseOrdersTab,
SchedulingTab and StaffTab. Initial fixture failures and the caught staff bearer
route allowlist gap remain in the evidence with corrected passing results.

Pre-publication snapshot: `JayMax-staff-production-2026-10-07-review-package.zip`,
69 archive entries and 47 verified source paths, SHA-256
`a189a44e007f1fab1653e5b2b3784f8ecf357d4a22df87d9a614d3f7cf1f3045`.
The local archive retains original sources, patch, review notes, test results,
source hashes and previous snapshots. Publication metadata is recorded separately;
the original snapshot is not overwritten. The disposable database was stopped
and remains outside synced folders.

All **15 native feature pairs remain false in example files**. Evidence is local
and synthetic, not live-browser, managed-platform or operational runtime proof.
The [original review](INVENTORY_REVIEW_STATUS.json) retains all 20 findings:
seven fixed within stated scope, twelve open and one intentionally deferred.

## Review sequence and next local work

This PR targets `codex/inventory-workflow-continuation` (PR #15); PR #15 targets
the foundation branch of PR #14. Leave the drafts unmerged until ready. Review/merge
#14 first, retarget and revalidate #15, then retarget and revalidate #16 against the
resulting main branch. Deployment and operational feature enablement are separate
decisions from merging.

The next local continuation reviews remaining legacy operating endpoints, their
read/write cutover boundaries and historical correction dependencies. It will
prepare a combined operating cutover/recovery trial. Future changes remain outside
this published branch until another PR is requested.

Remaining limits include historical dependency correction, sales consumption,
independent reports that may describe overlapping physical work, managed-platform
bootstrap/recovery, supplier delivery outbox and verified employee account mapping.
Container identities do not yet provide physical asset/refill/mixing/transfer
workflows. Scheduling, Operations, analytics and Toast remain future additions.
