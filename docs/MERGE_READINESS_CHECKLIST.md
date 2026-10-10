# Corrected stack and continuation: build/test merge review

October 9, 2026. Continuation branch: `codex/deployment-reconciliation-review`.
This is a code-review and draft-publication checkpoint. No PR has been merged by
this checkpoint, no manual deployment is initiated, and no operational invoice
data is imported. This recommendation is for the unused build/test deployment.

## 1. Combined review and acceptance

The continuation includes the corrected heads of the existing draft PRs:

| PR | Reviewed head | Existing base |
|---|---|---|
| [14](https://github.com/jeffwelch0620-png/JayMax-Concepts-/pull/14) | `119fb847f4f812c77b4876730936447d94d60ec0` | `main` |
| [15](https://github.com/jeffwelch0620-png/JayMax-Concepts-/pull/15) | `2e8ed7b77be814cbbce7d0d8b55486f6913dfb65` | `codex/postgres-invoice-capture` |
| [16](https://github.com/jeffwelch0620-png/JayMax-Concepts-/pull/16) | `91b028d8d44ac94a0253c1b8c2173a937f628c7f` | `codex/inventory-workflow-continuation` |

Their reviewed commits are ancestors of this checkout. GitHub reports all three
draft and mergeable, with no reported CI check runs; mergeability alone is not
acceptance evidence. The preserved local source checks are the evidence here.

| Current acceptance | Result and scope |
|---|---|
| Backend guards and parsers | 205 passed, 309 subtests passed, no skips. Includes connection/TLS/permissions, migration ordering, invoice raw-field retention, local recovery and handoff contracts. |
| Frontend, unset configuration | 61 suites / 494 tests passed. |
| Frontend, all native features held | 61 suites / 494 tests passed. |
| Frontend, all native features enabled | 61 suites / 494 tests passed. |
| Optimized build | Passed; existing hook-dependency warnings in PurchaseOrdersTab and StaffTab. |
| Disposable PostgreSQL acceptance | 19 distinct cases passed across the first run's 17 passes and the two successful recovery repeats. Whole migration/restore executes under an ordinary owning role as well as the combined restaurant-day fixture. |
| Preservation and publication audit | Original 40 pending paths and their binary diff remain byte-for-byte preserved. Every outgoing Git object is checked against the retained private credential bytes. Public source/evidence is sealed separately from private configuration and backups. |

These selected local checks cover the combined stack; they do not claim every
backend test, every old finding, a full browser walkthrough, or a fresh hosted
acceptance run. The earlier checkpoint documents retain their source and date.

The first backend run passed 200 tests, failed one Mongo compare-and-swap fixture,
and skipped 23 inherited PostgreSQL prep-correction cases because no database was
selected. The fixture now explicitly selects Mongo for its fake; production
routing did not change. The final offline selection removes the database-only
class and adds four invoice-parser cases. The two new prep-correction methods
run against real disposable PostgreSQL instead. Skips are never counted as passes.

The first local database run passed 17 cases, failed the combined backup case and
skipped the ordinary-owner restore because the external runner supplied the wrong
backup-tool environment key. The runner now supplies `NATIVE_BACKUP_PG_DUMP`;
both recovery cases pass on repeat. Both attempts preserve the original local
database/role inventory and stop their owned server. Initial outputs and the
pre-correction fixture are retained in the sealed review evidence.

## 2. What merging can trigger

The owner confirmed that Render automatically deploys from this repository, and
that the application is unused, has no operational data and exists for build
testing. A later authorized merge will therefore refresh that test deployment.
Disabling automatic deployment is not required for this code-only test review.
Live Render environment values and service status were not independently inspected.

The reviewed Blueprint starts the backend and builds the frontend; it contains
no migration/pre-deployment hook. Server startup connects the database pools and
does not apply native SQL, create replacement credentials or import invoices.
This source finding does not verify every external dashboard hook.

The existing designated Supabase build database already has the 29-file native
installation recorded in [its installation checkpoint](HOSTED_NATIVE_INSTALL_CHECKPOINT.md).
Do not replay historical migrations, use migration repair to hide missing old
files, or run an unrestricted database push as a side effect of merging.
Source/delivery checksums and the existing ledger remain the installation evidence.

Native schema installation holds selected legacy writers even with native flags
off. Turning flags off is not a schema rollback. Intermediate PR deployments may
show held legacy screens until the continuation and matched frontend/backend
flags are present. After the stack merges, verify the deployed configuration and
walk through its resulting test behavior before treating any workflow as accepted.

The selected architecture remains hosted Supabase as the authoritative database,
the shared session pooler on port 5432, two restricted backend login profiles on
that same database, and an encrypted local recovery copy. No paid IPv4 add-on or
hosting change is needed for this checkpoint. PostgreSQL mode does not create a
Mongo client or select Mongo after a PostgreSQL failure; unavailable database
workflows return a hold/error. Mongo code remains explicit legacy compatibility.

## 3. Publication and later merge sequence

Publish this continuation as a **draft** based on
`codex/staff-prep-count-continuation` (PR16), then review the four-PR chain. The
publication step is authorized; actual merge still requires the owner's decision.

1. Review corrected PR14 and authorize its merge into `main`.
2. Retarget PR15 to `main`; verify its head, remaining diff and applicable checks
   after PR14 lands, then obtain/execute its authorized merge.
3. Retarget PR16 to `main` after PR15; repeat that comparison and review.
4. Retarget this continuation to `main` after PR16; review the remaining diff and
   final stack evidence before its authorized merge.
5. Check the refreshed Render test deployment, both database connection profiles,
   matched feature flags and a browser workflow before the next operational build.

Merge commits are enabled in this repository and preserve the reviewed ancestry.
Prefer them for this stack. Squashing or rebasing requires separately reconciling
dependent branches and repeating acceptance for changed code. Do not force-push
or silently retarget/merge as part of draft publication. New head or base changes
invalidate the old exact-head comparison until rechecked.

## Accounting baseline and remaining review work

Track 1 remains purchased inventory only, using explicit opening/closing count
values and purchases on the received date. Taxes and fees are retained separately.
The combined invented day preserves $60 opening + $40 received food purchases -
$45 closing = **$55 actual Food Cost** through prep counts, staff production,
containers, waste, period corrections and whole restore. Full vendor source fields
remain stored whether or not a current output mapping exists.

Prep and waste measurements, sales-based portions, planning and recipe-definition
changes explain Track 1. They never substitute for a purchased physical count,
create accounting purchases, or rewrite a closed accounting result silently.
Unknown measurements and costs remain unknown rather than becoming zero.

The [original correction review](PR_REVIEW_CORRECTIONS.md) and historical inventory
review remain retained; this checklist does not mark all findings closed.
Authentication/shared-PIN identity redesign remains deferred as requested. Wider
history/access and cross-module idempotency review, stable completed-history
paging and remaining setup/batch query performance are separate tracked work.
Current query budgets are regression evidence, not measured production latency.

Scheduling, Operations, wider analytics and real Toast ingestion remain future
modules. In particular, this checkpoint does not prove real POS sales imports or
sales-based depletion. Operational use and any hosted replacement-account
promotion still require their documented secure credential staging, live client
registration, capacity and combined recovery checks. These gates do not prevent
reviewing this code-only build/test stack with the original selected credentials.

Earlier documents' local-only or merge-hold statements describe their original
snapshots. This checklist is the current build/test merge recommendation; it
does not retroactively change those receipts or approve operational deployment.
