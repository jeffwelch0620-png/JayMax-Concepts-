# Reviewed par maintenance qualification proposal

## Decision for review

Prepare a **new, maximum 45-minute qualification window** to pause the known
application producers, prove drain, capture a fresh encrypted application backup,
verify a disposable local restore, and run the existing read-only par preparer.
Return its exact proposed installation delta and plan hash for a later decision.
**This proposal authorizes nothing to run. No window is scheduled or active.**

Service pauses, further hosted access and credential, grant and schema changes
remain held. The proposed window would permit backup and read-only qualification,
**not schema installation**. No hosted DDL, application writes, runtime grant repair, credential
rotation, connection change, manual deployment or live fixture test is included.
The [non-executable packet](REVIEWED_PAR_MAINTENANCE_PROPOSAL_20261022.json) leaves
every execution approval false and start/end, executable plan and version unbound.

## Baseline and readiness

Accepted application source is PR53 merge
`46461e51ea8803b61c5b1d0a2cd7c5564d3a48dd`; the last local evidence commit is
`e356b62a6c436df8b0f3aa962941104eb4f3549f`. The
[installation/acceptance proposal](REVIEWED_PAR_INSTALL_ACCEPTANCE_PLAN_20261021.md)
pins the unchanged migration, catalog reference, 49 installer-source hashes and
31 dependency-ordered migrations. No application/tooling source changes are
proposed by this preparation.

The [October 21 role/writer review](API_ROLE_WRITER_REVIEW_20261021.md) established
the configured primary API binding as `postgres` through the existing Supabase
shared pooler on 6543, with PostgreSQL mode enabled. The accepted code reads that
binding directly. No API session was connected for independent process-level
identity proof. Keep that build path unchanged; O1 restricted-runtime adoption
is separate and is not silently made an installation prerequisite.

The latest saved observations show both Render services deployed at PR53, enabled
Toast jobs 3/4, no additional active cron jobs, no unfinished Toast syncs and no
identifiable additional application client. Six other sessions were consistent
with platform services. Those are dated observations, not stopped-writer proof or
an exhaustive inventory of future, shared-role or disconnected clients. Sixteen
permission checks passed for the reviewed candidate roles, not the API owner role.

Local-only preparation found about **486 MiB free of 6,030 MiB physical memory**
(about 92% used), about **107.7 GiB disk free**, Python 3.12.14, PowerShell 7.6.5,
and PostgreSQL dump/restore tools 17.11. No local database/server was started.
**Do not start an outage with that memory pressure.** Recheck immediately before
any approval is activated. Use at least 1 GiB and 15% physical memory free as a
conservative operator target, with stable process startup; this is a proposed
resource gate, not a changed tool limit or performance guarantee. Run work serially
and preserve unrelated applications. Verify sufficient archive/temp/restore disk
capacity against the actual workload and the owned PostgreSQL 17 recovery path.

## Before seeking execution approval

1. Reconfirm that only `jaymax-api` and Toast jobs 3/4 write, Companion remains
   local-only, and coworkers/manual SQL, scripts and direct Data API clients can
   stay stopped for the entire window. A new writer changes the proposal first.
2. Confirm the owner can manually suspend/resume the API and remain available
   throughout the window if Render automation is unavailable. Its previous
   availability confirmation is historical, not a current commitment.
3. Prepare and inspect a **fresh, source-bound operator packet locally**. Historical
   PR51 control/backup scripts have obsolete source/window pins and must not be
   invoked or have their guards bypassed. Any necessary runner code amendment
   needs its own local review/tests before an outage; none is implemented here.
4. Pass the resource checks, verify private storage/ACLs and recovery tool paths,
   and identify only the owned loopback PostgreSQL server/database targets.
5. Present the concrete window scope below for explicit approval. Record actual
   timezone-aware Eastern/UTC start and hard end before the first hosted action.
   No earlier approval or expired window may be reused.

## Exact controls in the proposed window

| Producer | Future approved action and restoration |
| --- | --- |
| `jaymax-api`, Render `srv-dauimuugekts73ek9lr0` | Read deployment/status and capture the original state. Expected dated commit is PR53. A changed commit or unexpected state holds for review. Ask the available owner to suspend it if automation is unavailable; independently record the suspension evidence. Resume only this service to its captured original state; no forced deployment, settings edit or connection change. |
| Toast job 3, Bert's/Rudd's | Read exact current ID/name/schedule/actor/database/command hash and enabled state. Temporarily disable only this verified job after approval. Restore its original enabled state and verify all other fields unchanged. |
| Toast job 4, Papa Leoni's | Apply the same exact-binding, state-capture and restoration rules independently. |
| Frontend, platform services and other processes | Leave the static frontend and Supabase PostgREST, pooling, networking, monitoring and cron infrastructure running. No broad login revocation or platform/session termination. Manual/direct writers remain stopped by the owner's explicit commitment. |

After those producer controls, obtain two strict quiet observations at least
45 seconds apart. Retain the accepted writer guard: full activity visibility,
existence/LOGIN checks for the exact reviewed roles including `postgres`, zero
other client sessions under those writer logins, no application-schema write
transactions from other clients, and no hidden/disabled client activity.
Also check cron runs, HTTP queue/in-flight evidence and downstream Toast syncs;
quiet SQL alone does not stop queued work returning. The `pg_net` background worker
is not an API client; its presence does not justify killing it. An unclassified
client or unresolved queue/run holds the workflow, even if otherwise idle.
Do not omit the owner role, relax the guard or kill shared/platform sessions to pass.

## Forty-five-minute operating budget

The following cutoffs are deliberately conservative. Measure progress with the
hard wall-clock deadline and a monotonic local budget; keep individual waits short
enough to report progress and act on the remaining reserve.

| Relative time | Required work and cutoff |
| --- | --- |
| 0–8 minutes | Revalidate target/control bindings, capture original states, pause the approved API/jobs and verify strict drain. If drain is not established by minute 8, start no export: restore changed controls and close early. |
| 8–18 minutes | One fresh encrypted application export, with the existing maximum 600-second export budget and an earlier stop if the remaining window cannot cover cleanup. Finish by minute 18; otherwise stop owned work safely and begin restoration. No automatic retry. |
| 18–24 minutes | Restore into one newly created UUID-named loopback PostgreSQL 17 database; verify fingerprints/access guards, nonempty-target refusal and owned cleanup. If not complete by minute 24, skip qualification and restore producers. |
| 24–34 minutes | Only if at least the full 600-second operation budget plus ten minutes for producer restoration remain, run the accepted read-only preparer against the fresh backup. Bind the proposed delivery version and exact target/delta/hash. Finish by minute 34; otherwise retain the held result and restore producers. No DDL is permitted. |
| 34–45 minutes | Verify owned hosted clients are closed, restore exact original Toast/API states, verify recovery within the approved read-only health scope and close the window. Record the known outcome and cleanup. If restoration or cleanup is uncertain, escalate immediately with the remaining time; no automatic extension or blind resume. |

This is a planning budget, not proof that the work will fit. A delayed start,
resource problem or measured worst-case budget that cannot fit these stages means
no pause or no next stage. Existing lock/probe/DDL/idle-transaction/operation
limits stay **5/20/30/120/600 seconds**; DDL's limit is recorded only for a later
installation, not permission to use it in this window. No timeout is enlarged.

## Backup, restore and qualification acceptance

The export uses the unchanged private maintenance-only direct IPv6 configuration,
verified target/TLS, server read-only mode and uniquely labelled owned sessions.
The app's pooler settings remain untouched. Capture the six application schemas:
`public`, `purchasing`, `actual_inventory`, `prep_inventory`, `integrations` and
`supabase_migrations`. Bind all current migration bytes and ledger data. Write a
new authenticated encrypted archive and separate encryption key in ACL-protected
local storage outside Git and cloud sync. A backup key is not a new DB credential.
No password, real row content, DSN or raw private command is shared in the report.

The proposed later restore necessarily creates/replays schema and ACL metadata
**only in the isolated disposable local target**, plus temporary NOLOGIN role
stubs as needed. Its approval must explicitly include that local rehearsal; no
Supabase credential, role, membership, grant, RLS or schema is changed. Never
restore to the hosted source or a nonempty local database. Verify matching major
version, complete supported row/sequence/catalog fingerprints, archive bindings,
restored access guards, and the original local role/database inventory afterward.
Remove only owned test objects and return the owned local server to its original
state. Do not run restored app workflows, cron jobs or operational imports.

Read-only qualification must reconcile all historical ledger bodies/names/hashes,
the existing source index, exact new-object collision state, current catalog and
permissions, all 31 readiness dependencies, and fresh backup equality. Allocate
no executable version/hash now. The later generated plan may describe only the
already-reviewed additive par migration: one empty history table with its exact
constraints/indexes/triggers/function, new-object RLS/revocations and one ledger
row. No legacy-par backfill, runtime grants or business-row rewrite is included.
Any refusal remains a hold; this proposal does not authorize fixing it in place.

The October 21 recovery matched 120 tables, 45,638 rows and 13 catalog groups;
these are historical comparison points, not fixed expected counts for a new
snapshot. Managed Auth/Storage/Vault/cron recovery, passwords/memberships, G04,
O1 and operational release remain outside the application restore qualification.

## Closure and the later schema decision

Return source/target bindings, producer states, drain timestamps, backup/key ACL
results and hashes, restore equality/cleanup, full preparer result, any exact
plan hash, and restored writer evidence. After any failure, preserve its original
error and separately report cleanup failures. Retain uncertain artifacts/keys;
do not silently delete evidence or retry. A known read-only failure allows early
closure after owned cleanup and restoration. An unexpected write or ambiguous
outcome stops the workflow for owner review; no repair/drop/replay is authorized.

Keep schema application held even if qualification passes. Once writers resume,
this backup/plan is dated qualification evidence: **do not apply it later without
a new approved stop/drain, fresh backup and exact target/baseline reconciliation**.
That intentionally favors a reviewable decision over applying under time pressure.
If the owner later wants preparation and separately approved exact-hash application
within one uninterrupted window, review that broader scope before starting it.

The later schema approval must explicitly cover the migration's new-object RLS
and revocations as well as DDL/ledger insertion. Credential changes and runtime
grants remain separate. Fictional par save/reload/recovery acceptance follows a
known verified installation under its own scoped approval. Par editing stays
frozen, ordering manual and Track 1 independent throughout this preparation.
