# Hosted reviewed-par migration plan - October 18, 2026

## Current status — October 21

The [current installation and acceptance proposal](REVIEWED_PAR_INSTALL_ACCEPTANCE_PLAN_20261021.md)
supersedes the next-action wording in earlier planning records below. Accepted
main is PR53 `46461e5`, tree-identical to reviewed `5c8e3ea`; reviewed-head and
merged-main CI passed all four checks. Bounded submitted-request recovery and
the explicit local-discard exit are merged. Render completion, complete live
installer readiness, exact executable plan/hash, schema application and fictional
acceptance remain separately held. This is local planning only; no new window
or delivery version has been allocated.

The [readiness review](REVIEWED_PAR_READINESS_20261021.md) reconciles accepted
PR51 `07daa29`, the completed 16-check role observation and the separately
approved fresh encrypted backup/disposable restore. Recovery matched 120 tables,
45,638 rows and 13 catalog groups; the window closed at 8:02:45 p.m. Eastern with
the API owner-confirmed Live at 07daa29 and both Toast jobs restored/enabled.
There is no active window, concrete executable par plan or new schema approval.

The saved par table is absent; its unchanged SQL/reference match source. Full
installer readiness, exact historical-ledger/index checks and later restricted
runtime-role permissions remain separate gates. This is not a live preflight
pass or permission repair. Hosted work, credentials, grants and schema changes
remain held; ordering manual and par editing frozen. Any later schema window
needs fresh approval, drain and backup/restore; the October 21 archive is dated
recovery evidence after writers resume. Earlier dated planning stages below do
not reopen an expired window or make the completed backup pending again.

## Earlier planning records

**October 20 gate:** PR48 merged as `cbe8e88` with reviewed-head and merged-main
CI green. The local [N1/N2 diagnostic and preflight-record work](PAR_BACKEND_HOLD_DIAGNOSTICS.md)
does not run a hosted preflight or authorize another window. First review the
follow-up, then prompt for the exact read-only hosted check. Document every
role/rule result and separate permission remediation before any new outage.

**Current local follow-up:** the owner authorized the
[v2 role-classification fix](PAR_INSTALL_ROLE_CLASSIFICATION.md) and regressions.
All 1,025 offline cases and 69 PostgreSQL cases across 21 methods passed in
completed serial selections. Browser denial, backend ledger protection and full existing permission
preservation remain required, with no new backend par access. No hosted connection
or change is part of this work. Prompt before draft publication; a later merge,
new window/fresh backup and exact executable plan approval remain separate.

**October 19 maintenance outcome:** the approved 12:21:26-1:06:26 a.m. Eastern window [closed at 12:39:21 AM Eastern](REVIEWED_PAR_WINDOW_20261019.md) with original API/Toast states restored. Strict writer drain and a fresh encrypted backup/disposable restore passed (120 relations, 13 catalog groups, 45,608 rows). Read-only par-plan preparation held on the trusted Inventory backend role being evaluated under private-client denial checks. No executable plan, schema SQL, grant change or connection cutover occurred. Review role classification locally before another window; retain browser denial, backend ledger denial and strict writer guards. Par editing remains held and ordering manual. Earlier pending/active stages below are dated history.

**Current gate after October 19:** the separately approved
[read-only IPv6 check](PR47_READONLY_IPV6_VALIDATION_20261019.md) passed. Separate
private maintenance config is ready, with app/Render settings unchanged. The owner
reconfirmed only the API/two Toast writers; refreshed controls match. A new
45-minute window awaits approval; no API/Toast pause, backup or schema/data
write occurred in the check. Fresh window/backup/restore and exact-plan application
approval remain separate. Earlier pending read-only stages below are historical.

**Current accepted tooling:** PR47 is merged as `a7270ca` from the exact tested
`755aff3` tree, with reviewed-head and merged-main CI green. The
[direct-maintenance preflight](PR47_DIRECT_MAINTENANCE_PREFLIGHT.md) proposes a
separately approved read-only validation before a new window. The older
local/draft-pending statements below are dated stages. No hosted execution or
schema application is authorized by merging the tooling.

**Subsequent local follow-up:** the owner approved
[maintenance-only IPv6 tooling and tests](MAINTENANCE_DIRECT_IPV6.md), with a
prompt before draft publication. Read-only investigation reproduced the pooler's
retained/reassigned backend behavior and verified direct IPv6 availability.
The proposed path leaves Render/app connections unchanged and retains every
writer guard. The dated closed window below is not reopened; hosted execution
and exact-plan application remain separate approvals after review and merge.

**Latest outcome:** the [October 18 approved window](REVIEWED_PAR_WINDOW_20261018.md)
closed at 8:35:28 p.m. Eastern, with API/jobs restored and database health connected.
Reviewed sessions remained despite no observed writes; the drain prerequisite held.
Backup/restore, concrete plan and schema application were not started. Investigate
operator/pool session ownership read-only before requesting a new window. Keep
par editing held, ordering manual and the separate exact-plan approval gate.

**Earlier PR46 merge / preflight checkpoint.** Accepted merge
`f762808` passed reviewed-head/merged-main CI, and its API deployment is Live.
The unchanged frontend remains Live on PR45 under its `frontend/` build root.
The [maintenance preflight](REVIEWED_PAR_MAINTENANCE_PREFLIGHT_20261018.md) records
verified retained local evidence, protected non-executable inputs and the owner's
reconfirmed three-writer scope. No Supabase connection or mutation occurred in
that preparation. Obtain a fresh bounded window/backup/restore, then prompt for
the exact plan hash before application. Earlier draft-pending statements below
are historical stages, not current blockers or execution permission.

**Local implementation follow-up:** the owner subsequently authorized building
the guarded installer and rehearsing it locally, with prompts before draft PR
publication and every Supabase application. See the
[par-specific installer/runbook](HOSTED_REVIEWED_PAR_INSTALLER.md). Local acceptance
now covers 69 reported cases across selection and corrected restore rerun, including
real encrypted export/restore, with all 945 offline-profile cases passing. Draft
publication approval and independent review/CI are still pending. These results
do not create an active window or approve an executable hosted plan. The original
preparation requirements below remain the reference; unimplemented-tool statements
describe that earlier stage.

Status: **prepared for review; not an executable hosted application plan**.
The owner approved merging PR45 and preparing this plan, and reserved hosted
application for a separate prompt. No maintenance window is active. No service,
job, hosted schema, role, grant, credential or connection is changed by this plan.

## Accepted source and exact change

- [PR45](https://github.com/jeffwelch0620-png/JayMax-Concepts-/pull/45) was
  owner-approved and squash-merged as
  `9dac63e659945aae3b68b613c13785af6a4ea658` from reviewed head
  `93941d4e1da6e3816f9b3975dd2f156c85e28719`.
- All four reviewed-head checks passed in
  [CI run 39103163918](https://github.com/jeffwelch0620-png/JayMax-Concepts-/actions/runs/39103163918):
  1,026 frontend tests/80 suites and strict build, 151 reported backend cases,
  906 reported Windows cases, and the aggregate check. The corrected local
  PostgreSQL selection passed 48 reported cases; overlapping runs are not added.
- Source: [`migrations/20261018_reviewed_inventory_pars.sql`](../migrations/20261018_reviewed_inventory_pars.sql),
  migration **31** in the reviewed dependency order.
- Raw SHA-256:
  `84814517f75bb58940a36facdbf5a7934036ff5b388e97a820038e837416506e`.
- Verified transaction-free body SHA-256:
  `3a189a8b2a352cbd560cea88194dbde1940f160a54e7bcd4616d719c47b88c48`
  (4,407 UTF-8 bytes). The existing SQL lexer was executed locally without a
  database connection; the checked-out source matches the accepted merge bytes.
- Adds `purchasing.inventory_par_versions`, its constraints/indexes, function
  `purchasing.guard_inventory_par()`, and triggers `valid_inventory_par`,
  `immutable_inventory_par`, `retained_inventory_par` on that table. It uses
  existing `purchasing.reject_fact_change()` and verified physical profiles.
- RLS is enabled, with no new client policy. Direct PUBLIC/anon/authenticated
  table/function privileges are revoked. Unexpected inherited/default access
  must be detected, not waived. Restricted backend-role expansion is deferred.
- Existing `store_items.par`, rows, units, prices, purchases, physical counts,
  prep/waste, sales and closed-period values are not backfilled or rewritten.
  The new table starts empty. Later explicit par commands can append history
  and atomically advance `public.store_state.revision`; installation does not.

The unchanged SQL is the reviewed scope, not a whole-schema installer or an
instruction to run Supabase CLI filename-order application. Preserve original
29-file delivery evidence and the separately installed source index/history.

## Current evidence and the remaining preparation gate

All four **merged-main** checks also passed in
[run 39165819254](https://github.com/jeffwelch0620-png/JayMax-Concepts-/actions/runs/39165819254)
for exact merge `9dac63e`. This is separate from reviewed-head CI and does not
establish hosted schema installation or live par acceptance.

Read-only Render dashboard inspection verifies both automatic deployments
**Live on `9dac63e`**: frontend `dep-dbaj6gpsrm7s73ahimtg` (28.9 seconds) and
API `dep-dbaj6gpsrm7s73ahimf0` (1 minute 52 seconds). No manual deployment,
environment setting, service pause or job control was used. Deployment status
does not establish authenticated par behavior or a fresh database comparison.

The completed [October 15 source-index window](HOSTED_INDEX_WINDOW_20261015.md)
recorded 55 ledger rows and delivery `20261015175921`. That is dated evidence,
not a fresh database observation. Expect a new row only if a fresh reconciliation
proves this exact baseline. Additional migrations/writers require a revised plan.
The prior backup and window approvals cannot authorize this change.

**The current index-only tools cannot apply or reconcile a new table.**
`tools/ops/apply_additive_migration.py` and `tools/ops/hosted_additive_index.py`
pin the source-index file and an index-only catalog delta. Do not change their
source constant, feed them this SQL, bypass their checks, or replay the original
fresh installer. A separately reviewed par-specific additive adapter and its
disposable PostgreSQL tests are required before any hosted execution prompt.
Its design requirements are below; it is not implemented by this documentation.

The owner accepted a temporary par-editing freeze after the application deploys.
Legacy par references remain read-only/unconfirmed, missing storage keeps new
reviews unavailable, and ordering stays manual. No automatic ordering, paid
IPv4 add-on, provider move, feature-flag change or credential cutover is proposed.

## Par-specific adapter requirements

1. Pin the accepted migration's raw bytes and the transaction-free body from the
   existing reviewed `hosted_test_trial.migration_body` lexer. Record both hashes.
   The file contains outer BEGIN/COMMIT; use only that verified body inside the
   adapter's single outer transaction with the ledger insert. Sending the whole
   file inside another transaction would break the intended atomic boundary.
2. Validate the designated build project, database/actor/server identity and
   certificate/hostname using the existing private administrative direct/session
   connection. Retain its current saved endpoint; no URL/password in arguments,
   logs, Pages or Git. A stable session is required; do not substitute the app's
   transaction-pooled connection for session locks and transaction state.
3. Bind a new plan to the successful original delivery, installed source-index
   receipt, every current ledger fingerprint, current source hashes, exact
   migration body, baseline rows/sequences/catalog/security, client-denial checks,
   approved writer inventory/window and a new restore-verified encrypted backup.
   Choose a unique 14-digit delivery version greater than every actual installed
   version; do not preassign it from a filename or rewrite older history.
4. Refuse a colliding table/function/trigger/index, partial install, mismatched
   body/history, hidden activity, unexpected ACL/policy/default privileges,
   unreviewed source, expired window, active/late writer or changed evidence.
   Compare full definitions, not names or readiness presence alone.
5. Serialize with existing installers using lock `781340621`. Under bounded
   timeouts, lock the ledger and reviewed existing application relations before
   taking the repeatable-read baseline snapshot. Recheck writer drain and all
   baseline facts under those locks. One outer transaction creates the exact
   objects and inserts exactly one correctly named/body-hashed ledger row.
6. Allow only the new table's definitions, automatically generated constraints
   and indexes, guard function/three triggers, security settings and one ledger
   row as catalog deltas. Compare actual definitions to a disposable installed
   reference. Do not mask all purchasing/catalog differences to make it pass.
   All original business rows, sequences, existing object definitions, role
   attributes/memberships, grants and original ledger fingerprints must match.
7. Preserve the existing refusal/receipt model: exact plan-hash approval, private
   protected inputs/output, no overwrite, progress receipt before DDL, no automatic
   retry, acknowledged rollback versus unknown outcome, and independent fresh-
   connection reconciliation after success, interruption or lost acknowledgement.
   Report applied/not-applied/unknown; unknown is not permission to resend SQL.

Local adapter acceptance must cover successful install + one ledger row; wrong
source/project/actor/backup/window; missing/changed/extra historical ledger rows;
existing/partial objects; precise new catalog delta; unchanged old rows/sequences;
RLS/direct-client denial; append-only update/delete/truncate guards; rollback on
DDL/ledger error; active/hidden/late writers and a write during lock wait; lost
commit/rollback responses; uncertain reconciliation and already-applied refusal;
fresh encrypted export and isolated restore including new par history; and exact
decimal/replay/physical-count/Food Cost independence. Use fictional loopback-only
databases with verified owned cleanup. No hosted test is implied by local passes.

## Before proposing a maintenance window

- Finish the adapter, run its meaningful local acceptance, request a draft-PR
  push, obtain independent review, and check exact-head CI/merge approval under
  the established workflow. This plan is not permission to publish another PR.
- Verify merged-main CI and the actual PR45 frontend/API deployment separately.
  Do not infer a Live deployment from the GitHub merge or healthy old service.
  A read-only missing-storage/manual-order check does not authorize a par write.
- Reconfirm every possible writer. Previously observed controls were Render API
  `srv-dauimuugekts73ek9lr0` and cron jobs 3 `jmax-toast-berts-rudds-daily`, 4
  `jmax-toast-papa-daily`. Re-read names, IDs, schedules, command hashes, activity
  and original enabled states; these identifiers are historical until refreshed.
  Companion was local-only at the last owner confirmation; ask again rather
  than assume it cannot now connect. Include coworkers' SQL, scripts, previews,
  other app instances, Edge Function/import work and both local backend logins.
- Do not pause anything while preparing/reviewing. Request a new bounded window
  and no-manual-writes commitment when the tested adapter is ready. Recheck
  provider notices then. No expired 45-minute window is reused or scheduled here.
- Keep the owner/configuration, backup archive and separate key under the
  existing ACL-protected `%LOCALAPPDATA%/JayMaxBuild` storage, outside Git/Drive.
  Record only safe hashes/counts/statuses in shared documentation.

## Proposed execution sequence - approval still required

| Stage | Required evidence and stop condition |
| --- | --- |
| 1. Start a newly approved window | Record timezone-aware deadline and original exact API/job states. Pause only approved producers, block new submissions and verify downstream imports completed. Full activity visibility, reviewed login drain, no unowned write transaction and queue/run evidence are required. Empty HTTP queue alone cannot establish downstream completion. Never terminate platform/unknown sessions to pass a guard. |
| 2. Fresh backup and disposable restore | After drain, capture a new authenticated encrypted application backup covering application schemas and ledger with current source hashes. Verify archive/key ACLs and hashes, matching PostgreSQL major version, restored rows/sequences/catalog/security and owned local cleanup. Failed/partial backup or restore stops the window before DDL. This is not managed Supabase Auth/Storage/Vault recovery. |
| 3. Read-only exact plan | End read-only preflight transactions before apply. Bind fresh baseline, restored backup, source/body hashes, next delivery version, reviewed security/object delta, timeouts and remaining window. Present the concrete plan SHA-256 and safe change summary to the owner. **Prompt before application. Window approval alone is insufficient.** |
| 4. Apply once after exact approval | Revalidate identity/evidence/drain/deadline; use one transaction for exact DDL and one ledger row. Proposed unchanged limits: 5 s lock, 20 s probes, 30 s DDL, 120 s idle transaction and 600 s adapter operation. These are requirements, not implemented/benchmarked par-adapter promises. Do not silently extend limits or apply too near the deadline. |
| 5. Independently reconcile | Fresh connection must prove one complete approved outcome: table empty, exact constraints/indexes/function/triggers/RLS/ACLs, original rows/sequences/catalog/history unchanged and one new ledger entry. Current 31-migration readiness and separate definition/security checks must pass. Preserve the historical $212.00 Food Cost control and complete protected accounting comparison. |
| 6. Restore writers and check service | Only when the outcome and baseline preservation are known, restore each writer to its recorded original state. Check exact deployment, API database health and ordinary authenticated reads; health alone is insufficient. Reconcile uncertain outcomes before resuming, and notify the owner if recovery cannot fit the approved deadline. Record window closure and actual elapsed durations. |
| 7. Labelled live par acceptance | After maintenance recovery and approval of the exact fictional fixture, use normal owner routes to test confirm, explicit zero, withdraw, fresh-instance readback, history, stale count-profile review, changed supplier pack, stale store revision and exact retry. Record each expected revision/history delta; keep real purchase/count/prep/waste/sales/period data unchanged and order quantities manual. Never delete immutable test history to clean up. |

The earlier source-index operation took over seven minutes for apply plus
independent verification, even with a small dataset. That is not a benchmark for
this table migration. Measure the adapter locally, reserve cleanup/recovery time
and choose the actual window after fresh evidence. If review consumes the budget,
restore producers without applying and arrange a new window; silence is not approval.

## Failure and rollback policy

- **Before DDL or known acknowledged rollback:** retain the failed receipt;
  independently verify the unchanged baseline, restore original writer states
  and leave confirmations frozen. Re-plan; do not repair ledger/history ad hoc.
- **Lost connection/commit acknowledgement:** keep the exact plan/evidence and
  treat the outcome as unknown. A fresh reconciler must wait/refuse while the
  original installer still holds its session lock, then distinguish full apply,
  full baseline or inconsistent state. No automatic DDL retry or broad session kill.
- **Known committed install:** retain the additive schema/history. A separately
  approved application rollback may use the prior verified deployment while
  leaving the table; do not drop the table/function or delete ledger/history,
  especially after any par review. Any destructive repair or backup restoration
  needs its own reviewed loss/restore plan and explicit approval.
- **Post-install route/security failure:** keep par editing unavailable and
  ordering manual; inspect the exact defect. Do not add public policies, widen
  grants, change owner connections or bypass existing revision guards as a shortcut.

## Runtime-role and release boundaries

The existing build connection is not the separately tested restricted-role
deployment. This plan does not cut over credentials or broaden its old manifest.
The later O1 work must include explicit trusted-backend SELECT/INSERT and RLS
policies for the new table, existing verified-profile/item-base reads and
`store_state` insert/update dependencies, plus existing catalog SHARE-lock ACLs.
Never grant UPDATE/DELETE/TRUNCATE on immutable par history or browser access.
Prove positive and negative location/actor routes under the selected role before
deployment. Migration installation alone does not close O1 or operational release.

Track 1 remains purchased-item opening count plus received purchases minus
closing count, with explicit count values and separate tax/fees. Prep/waste and
sales remain explanations. This planning table is neither an accounting entry
nor proof of available stock, a measured operational par or an automatic order.

## Approval packet to present later

The final prompt must identify the exact build target privately, approved window,
paused/drained writer evidence, new backup/restore receipts, accepted code and
tool hashes, raw/body migration hashes, full installed baseline and proposed new
delivery version, exact plan SHA-256, allowed catalog/ledger delta, bounded
timeouts, manual-order/freeze behavior and rollback/reconciliation route. No
executable plan hash or delivery version can be asserted from this prose alone.

References: [par contract](REVIEWED_INVENTORY_PARS.md),
[apply order](../migrations/APPLY_ORDER.md),
[historical completed index window](HOSTED_INDEX_WINDOW_20261015.md),
[backup workflow](HOSTED_TO_LOCAL_BACKUP_WORKFLOW.md),
[restricted-role assessment](RUNTIME_ROLE_PERMISSION_ASSESSMENT.md),
[current workflow](WORKFLOW_RECONCILIATION_20261015.md).

## Validation of this planning-only slice

Local checks verify migration LF/raw bytes against the accepted merge, parse the
body with the existing transaction-boundary lexer, resolve relative Markdown
links and run `git diff --check`. No application or database test suite is
rerun for these prose-only edits. PR45's reviewed-head/merged-main CI and prior
local database results are separate evidence, not tests of a new par adapter.
The local invalid copied Git ref `refs/remotes/origin/main (1)` blocked fetch;
its exact recorded contents were moved to a recoverable file outside `.git`,
then origin/main fetched successfully. No valid ref, commit or working file was
deleted or reset. The follow-up branch starts at accepted merge `9dac63e`.
