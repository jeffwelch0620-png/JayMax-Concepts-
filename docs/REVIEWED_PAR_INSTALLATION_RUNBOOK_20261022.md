# Reviewed-par installation runbook — October 22, 2026

**Subsequent local-only follow-up:** the owner authorized the three tooling
changes, regression tests and another timing rehearsal described in
[the query-reduction record](REVIEWED_PAR_QUERY_REDUCTION.md). The original
timings below remain the comparison baseline. No new hosted authorization or
schema plan is created by that local implementation.
The candidate passed 1,269 offline and 117 disposable PostgreSQL cases; apply
plus fresh-connection verification used 1,112 calls / 69.859 s. Calls decreased
53.6% while elapsed time increased; hosted timing remains unproven. The local
performance design-review action below is now implemented and awaiting draft
publication approval/independent review; it is not another authorization to edit
or execute hosted work. All application gates and holds remain in place.

## Status and authority

**No hosted action is authorized by this runbook.** Hosted work and credential,
grant and schema changes remain on hold. The owner's current authorization is
local tooling optimization, regression testing, timing rehearsal and
documentation refresh only. Rehearsal DDL/ACL replay
and temporary role stubs belong only to an owned disposable loopback database;
no existing credential, hosted role, grant, connection or schema is changed.

Accepted application main is PR54 `ed62beb943b29566dfad64e73915126324cfbb1f`,
tree-identical to reviewed `02ac4c00ee657410077eed51cb874bfd9bed00c6`:
`323d5e8d345d2add34fa44da4112a0497dc75c35`. Both reviewed-head and merged-main
CI passed all four checks: 1,079 frontend tests / 83 suites and strict build,
1,261 Windows offline cases and 242 backend/disposable PostgreSQL cases.
Profiles overlap; these are not additional tests run by this documentation update.

The October 22 qualification-only window ran from 2:41:47 to 3:04:43 p.m.
Eastern (22 minutes 56 seconds) and is closed. Strict writer drain passed.
Fresh encrypted application backup/disposable restore matched 120 tables,
45,648 table rows and 13 catalog groups. Sequence/access guards and owned cleanup
passed. The local server was stopped. Read-only qualification returned
`prepared_hosted_plan`, with `sqlCommitted=false`; par storage remained absent
and the ledger remained at 55 versions, maximum `20261015175921`.

Original complete Toast job 3/4 bindings and enabled states were restored and
verified. The owner confirmed API Live at `ed62beb`; one bounded anonymous
health request timed out. Functional health remains unverified. Do not retry
health checks or inspect hosted systems under the current local-only approval.
Companion remained local-only at the last owner confirmation.

## Retained qualification evidence

| Evidence | Safe binding |
| --- | --- |
| Closed-window plan SHA-256 | `2bb82db1c6b92d88bc7b84d0c5eb4eb6961e52977ac4891f1e8c47f271be99e8` |
| Candidate version, not applied | `20261022185416` |
| Closure receipt SHA-256 | `2d5e4ec3958809a5bcd7f2fe90d1b8381c02aa4b04b9b3b6ec2c5270e2755f09` |
| Encrypted artifact SHA-256 | `c8c8e8f9f203f43dd33af1cf533e1979efe70f1ceb68f36d194254c42a887f93` |
| Archive SHA-256 | `77beabc6a2fa88db317dc32ea798fc5c9546ff115a774940851faba842d746df` |
| Exact SQL SHA-256 | `84814517f75bb58940a36facdbf5a7934036ff5b388e97a820038e837416506e` |
| Transaction-free SQL body SHA-256 | `3a189a8b2a352cbd560cea88194dbde1940f160a54e7bcd4616d719c47b88c48` |

The preparer's own operation receipt measured **311.766 seconds**. A prior
outer elapsed observation was 317.313 seconds; they measure different boundaries
and are not two independent executions. Neither measures application.
Private backup/key material, full plans, review inputs and row contents stay
outside Git, cloud sync and Pages. No private path or credential is needed here.

## Local timing rehearsal

**Passed locally on October 22, 3:23:45–3:25:42 p.m. Eastern.** The
[public timing receipt](REVIEWED_PAR_LOCAL_TIMING_20261022.json) records one
completed corrected execution, separate from the earlier held invocations.

| Stage | Elapsed seconds | Measured database calls |
| --- | ---: | ---: |
| Authenticated restore and equality | 25.047 | Not instrumented in the restore utility |
| Local read-only preparation | 15.078 | 714 |
| Application plus independent fresh-connection verification | 58.578 | 2,396 |

Restore matched 120 tables, 45,648 table rows and 13 catalog groups. Local
application acknowledged commit and independent reconciliation returned
`verified_applied`: the new table had zero rows and exactly one ledger row was
added. Original rows/sequences/catalog/security were preserved. The complete
original local role/database/membership inventory was restored, the owned server
stopped, and cleanup reported no errors. Retained archive/window receipts were
unchanged. Seven validated loopback connection attempts and zero rejected/nonlocal
connection attempts were recorded. A separate connector-stub check passed nine
cases (six refused before the connector, three accepted local shapes), opening
zero databases. No application, migration, guard, timeout or permission-candidate
source changed.

Loaded resource samples before execution were 1,259.6 and 1,254.5 MiB free
(20.89% and 20.80%). The timing harness SHA-256 is
`17d523284b1781b74e0cf3834d21286618a173a96e4240ccfaa6cb8bc97111c6`;
its protected full receipt SHA-256 is
`9d7b68867dceae1534cdaa28480a42687bb6543129cc0537c64d42a5a867b3e4`.
The harness and initial receipts remain local evidence outside the repository;
they are not a new supported hosted execution entry point.

The single-use local harness authenticates the retained archive, checks all
49 installer-source and 56 packet-source hashes, and refuses non-test socket
targets before any database work. It starts only the owned PostgreSQL 17 server
bound to `127.0.0.1:55439`, with at least 1 GiB and 15% free physical memory after
dependencies load. It creates a fresh UUID-named disposable database and missing
role stubs only; no source passwords or memberships are restored. Only temporary
writer-role stubs receive LOGIN for the unchanged writer guard; no passwords
are set and existing roles are not altered.

The accepted restore utility must first prove archive/catalog/row equality.
The harness then uses the unchanged accepted `prepare`, `apply` and `reconcile`
functions, as the disposable integration tests do. A new explicitly local review
binds the loopback target, local server patch version and current local baseline.
It is not a hosted plan. It does not invoke the hosted CLI, load an owner DSN,
reuse the closed window, falsify a hosted identity or patch production guards.

Preparation is timed separately. Application connection, apply, connection close,
fresh read-only connection and independent reconciliation share the unchanged
**600-second** limit. Local query counts/times are recorded without SQL or row
contents. The new par table must be empty, exactly one ledger row added, and
all original rows/sequences/catalog/security preserved. Cleanup must restore
the original local role/database/membership inventory and stop the owned server.

This rehearsal does not validate Supabase routing/TLS, source project identity,
current source writer controls, remote latency, future backups or hosted health.
Local timings cannot establish that a future hosted application fits 600 seconds.
Do not enlarge timeouts or reduce preservation checks to meet a schedule.

Retain the initial harness failure before database startup: its first network
guard blocked Python's internal event-loop self-pipe. Guard installation was
moved after event-loop construction but before any database work. A subsequent
invocation stopped at the loaded-memory gate. The first database attempt refused
a nested temporary directory before restore; the corrected attempt refused the
backup helper's empty-password argument representation before its target
connection. Both runs restored local inventory and stopped the server. The
harness was corrected to use the accepted fresh-directory layout and accept
`None` or an empty password for the same fixed loopback target. No nonempty
password, source credential or production guard was changed. One draft
connector-check command had a syntax error before collection; the corrected
nine-case check passed. None of these earlier attempts is a passing rehearsal.

### Hosted timing remains unresolved

The local pass proves the restored-data path fits 600 seconds **on loopback**.
It does not prove the hosted path fits that limit. Application/verification
made 2,396 measured database calls, about 3.36 times preparation's 714. The
recent hosted preparation took 311.766 seconds, versus 15.078 locally. Server
load, network latency, caching and transport differ, so neither ratio is a
reliable hosted application forecast.

The original numbers below are historical. The query-reduction candidate uses
1,112 apply/verification calls and took 69.859 seconds locally, versus the older
2,396 calls / 58.578 seconds. The candidate has fewer calls but no measured
elapsed-time speedup. Its [retained receipt](REVIEWED_PAR_QUERY_REDUCTION_TIMING_20261022.json)
is unchanged. For planning only:

| Candidate sensitivity | Modeled apply/verification total |
| --- | ---: |
| Hosted-derived extra cost: (311.766 - 15.078) / 714, about 0.416 seconds per call | About 532 seconds |
| Proposed installation planning gate | At most 450 seconds, leaving at least 25% of the 600-second limit |

This simple additive estimate leaves only about 68 seconds (11%) and does not
meet the proposed gate. It mixes network delay, server work and scheduling from
different runs; it is not a latency measurement or a guaranteed upper bound.
Larger batched queries may have different server costs, but these measurements
do not establish what caused the increase in elapsed time. A model below 450
seconds is a necessary planning screen, not sufficient installation approval.
Keep hosted application held until evidence supports that headroom and the
owner approves all separate window and exact-plan gates. Never raise the
600-second limit or remove preservation checks to pass the screen.

Local diagnostic instrumentation reports counts and seconds for readiness,
fingerprints, catalog capture, ACL/index checks, ledger and readiness_check.
Inclusive function totals overlap; exclusive groups attribute every measured
driver method once and must reconcile to phase totals. It retains no SQL,
parameters or row values. A separately owner-approved bounded read-only hosted
probe could later distinguish server work from round-trip costs; none is
authorized or performed by this PR.

For planning sensitivity only, add a fixed extra delay to each measured local
application call; this arithmetic is not a delay-injected or hosted execution:

| Hypothetical extra delay per call | Modeled apply/verification total |
| --- | ---: |
| 100 ms | 298.178 s |
| 200 ms | 537.778 s |
| 250 ms | 657.578 s, exceeding 600 s |
| 400 ms | 1,016.978 s, exceeding 600 s |

Only about 226 ms average additional cost per measured call exhausts the local
headroom. Preserve all checks and the 600-second limit. **Recommendation: keep
hosted application held and review the repeated query/scan cost locally before
proposing another installation outage.** Any optimization needs separate owner
authorization, regression tests and independent review. A deliberately timed-out
hosted apply is not an acceptable profiling method. Narrow hosted profiling, if
later necessary, needs separate read-only approval and cannot itself permit DDL.

## Exact future installation delta

Use only [the reviewed additive par migration](../migrations/20261018_reviewed_inventory_pars.sql)
through the [core](../tools/ops/apply_reviewed_par_migration.py) and
[hosted envelope](../tools/ops/hosted_reviewed_pars.py). The
[catalog reference](REVIEWED_PAR_INSTALL_CATALOG.json) remains normative.

- One initially empty `purchasing.inventory_par_versions` table: 17 columns,
  17 constraints and six unique indexes.
- One guard function, three user triggers and 12 internal foreign-key triggers.
- RLS and revocations for the new objects; no runtime grants, policies, role
  cutover or credential changes.
- One new migration-ledger row with a freshly reconciled delivery version.

No legacy-par backfill, automatically confirmed zero, existing business-row
rewrite or store-revision increment occurs during installation. Later legitimate
par commands append history and advance the store revision atomically.
Purchased-inventory accounting remains independent of prep and sales. Ordering
remains manual; the par-editing freeze ends only after installation and acceptance.

## Before proposing an application window

1. Review this local result and address the query/latency risk before an outage.
   The current recommendation is a local performance design review, not hosted
   application or changing timeouts. Obtain separate
   authority for a bounded read-only API health check; stop for review if recovery
   is not established. This runbook authorizes neither the check nor a repair.
2. Review/merge any approved documentation follow-up through the usual separate
   PR gates. Rebind future source evidence to the accepted tree and exact bytes.
   The qualification packet's pinned qualification-only scope is unchanged;
   it cannot authorize application or be edited to add an apply command.
3. Reconfirm all current writers, Companion status, no-other-writes commitment
   and owner availability for API suspend/resume. Capture current deployment and
   exact Toast bindings. A changed writer or baseline changes the plan first.
4. Prepare a new installation-inclusive maintenance proposal. Include resource
   checks under load, private archive/key storage, isolated restore route,
   conservative stop times, independent outcome reconciliation and original
   producer restoration. Do not schedule or activate a window from this document.

The prior [installation/acceptance proposal](REVIEWED_PAR_INSTALL_ACCEPTANCE_PLAN_20261021.md)
retains the exact fictional acceptance cases. The immutable
[qualification proposal](REVIEWED_PAR_MAINTENANCE_PROPOSAL_20261022.md) and
[operator handoff](PAR_QUALIFICATION_EXECUTION_PACKET.md) remain dated evidence
for their narrower scope; they are not the next application authorization.

## Future application controls — still held

Obtain explicit installation-inclusive window approval before pausing producers.
Then pass strict full-visibility drain twice at least 45 seconds apart, including
cron/HTTP queues/downstream work. Capture and verify a **fresh** encrypted backup
and disposable restore; re-run full qualification against that baseline. Present
the current exact target/delta/version/backup bindings and **new plan SHA-256**.
Only separately approved exact-plan authority may permit DDL, new-object
RLS/revocations and ledger insertion. Existing credential and runtime-grant
holds do not lift by implication.

Preserve limits: lock/probe/DDL/idle-transaction/operation = **5/20/30/120/600
seconds**. The adapter's technical floor is 660 seconds remaining before apply;
the operating plan must reserve **at least 600 seconds for producer restoration
in addition to the full 600-second apply/verification budget**. Apply may not
start with less than that larger operator reserve. Do not use the technical
floor to consume the recovery margin. If fresh preparation or approval takes
too long, restore producers and close without application. No automatic retry,
extension, skipped guard or platform-session termination.

Treat 45 minutes as a proposed maximum rather than proof the complete workflow
fits. Budget from observed work, existing operation limits and owner response
time. If a defensible schedule cannot fit, return an alternative for review
before any pause rather than inventing a larger window or timeout.

The core locks the baseline, applies the exact transaction-free body and ledger
entry together, and verifies preservation before commit. The envelope closes the
write connection and reconciles using a fresh read-only connection. If commit or
rollback acknowledgement is lost, retain the exact plan/progress receipt and
classify the outcome independently. Never resend SQL to discover whether it ran.
A confirmed install must retain the additive table, not drop it as a rollback.
Restoration/repair/replay requires separately reviewed authority.

Before resuming producers, prove the exact empty-table/catalog/ledger delta and
preservation of original rows, sequences and security. Restore the captured
original producer states and verify only the health scope approved for that
window. Record closure and uncertainties. Once app acceptance appends par rows,
the installation reconciler's empty-table requirement is no longer a health check.

## Separate acceptance and release gates

After a known installation and writer restoration, obtain a distinct approval
packet for exact labelled Bert's items/profiles, expected append/store-revision
counts, accounting baseline and any transport controls. Cover confirm, explicit
zero, withdrawal, exact tiny decimals, stale revisions, same-key replay, reload
and sign-in recovery, dropped responses, held/local discard and actor/location
isolation. Retain fictional history and verify temporary test-control cleanup.
Compare protected purchases/counts/closures/prep/waste/sales and the exact scoped
Food Cost report; do not replace it with a dashboard total.

Keep the current owner-connected build path unchanged. O1 restricted-runtime
ACL/RLS adoption, G04 security/personal-login acceptance, managed Supabase recovery,
Companion adoption and operational release are separate unfinished workflows.
Installation alone closes none of them.

## Local validation and collaborator records

The corrected restored-data rehearsal passed as recorded above; nine isolated
connector checks passed with no database connection. JSON receipt assertions,
harness syntax, all 49 installer hashes and 56 packet hashes, 170 relative links
across the three amended/new Markdown files, and Git whitespace checks passed.
These are not a new run of the historical frontend/offline/PostgreSQL CI suites.
Application source and source SQL are unchanged, so those full suites were not
rerun for this documentation/evidence-only update.

JMax root, Inventory workflow, progress and hosted-par proposal records were
reconciled and read back after access recovered. The earlier active-window
claims were replaced with closure and local timing findings. Unrelated Companion
history remains intact. No new PR, hosted request or live acceptance was performed.
