# Reviewed par installation proposal — October 23, 2026

**Prepared for owner review. No live change is authorized or executed by this
document.** Inventory Build Main is the coordinator. No maintenance window is
active. Existing writers and app/Render connections remain unchanged. This amended
proposal is the single current source of the P1 window schedule; dated archives
are evidence only. Local documentation amendments do not approve S1, P1 or P2.

## Decision requested and boundaries

Approve package **P1: one new 60-minute installation-preparation window**, with
owner availability to suspend/resume Render's `jaymax-api` and a no-other-writes
commitment. P1 permits only the exact temporary writer controls, strict drain,
fresh encrypted application backup, disposable local restore and full read-only
installation qualification described below. **It does not approve application
of SQL.** At the final qualified baseline, a separate **P2** prompt must identify
the executable plan hash, new ledger version, backup/restore bindings and exact
database delta before any DDL, using the [pre-built decision checklist](P2_EXACT_PLAN_DECISION_CHECKLIST.md). If P2 is withheld or guards fail, restore writers
and close the window without installation.

This proposes 60 minutes rather than silently reusing an expired 45-minute
window. Full 600-second work budgets, cleanup and a 600-second writer-restoration
reserve must fit. No tool/SQL timeout is increased. The operator must reject an
activation whose measured conditions cannot support the schedule below.

## Accepted baseline and evidence

- Inventory PR59 merge `c3b429a2da8d1880ecdbcf34ccb5b28033978c6c`; tree
  `52c3b07b494344fe8b09c270a9392576526b57ef`, identical to reviewed `e54202f`.
- Reviewed-head and merged-main CI each passed separately; merged-main run
  [39982704918](https://github.com/jeffwelch0620-png/JayMax-Concepts-/actions/runs/39982704918).
- October 23 approved health observation passed once: HTTP 200, `status: ok`,
  `database: connected`, cleanup confirmed. This was pool-presence evidence.
- October 23 approved calibration passed in 45.797 s with complete scope:
  118 original-column tables, 120 backup relations and 13 catalog groups.
  Observed maxima: setup 0.375 s; original 8.375 s; backup 5.063 s. These satisfy
  the 10-second observed-read planning screen; they are one live-writer sample.
- Calibration receipt SHA-256:
  `23f883b02e4b8ad551e9b9a59ee2562f7c30243748a6beab2e832497434cfda9`.
- Source inventory is clean; all 49 par-installer source bindings and reviewed
  SQL/catalog bytes are checked locally in the accompanying source audit.

The older above-threshold timing estimates and closed-window plans are dated
history. The local 362.527-second additive sensitivity passes the 450-second
planning screen, but is not a forecast of this outage. The new calibration must
not be multiplied into an invented end-to-end installation guarantee.

## P1: exact temporary live changes

| Target | Allowed change | Restoration and stop condition |
| --- | --- | --- |
| Render service `jaymax-api`, service ID `srv-dauimuugekts73ek9lr0` | Capture actual Live commit/state; suspend only this API after fresh owner approval. Owner may operate the dashboard if automation is unavailable. | Resume the same service; no Manual Deploy, rollback or settings/plan change. Confirm Live at captured commit. A different commit or unavailable controls holds activation. |
| Toast cron job 3, Bert's/Rudd's | Capture exact job identity, schedule, role and command digest; change only `active` to false after matching the reviewed job. | Restore captured original `active` state and verify all original bindings; do not replay missed runs or alter command/schedule. |
| Toast cron job 4, Papa Leoni's | Same bounded control as job 3. | Same exact-state restoration; no other cron job is changed. |
| Supabase application connection | Existing private maintenance-only direct IPv6/TLS path for drain, backup and qualification. No app pool/role/credential cutover. | Verify exact build project privately; close only owned clients. No platform-backend termination or permission repair. |
| Local recovery target | Create only an owned disposable loopback PostgreSQL 17 restore target and required temporary role stubs using the reviewed runner. | Verify original local role/database inventory, drop only owned disposable artifacts, stop the owned server. No operational restore. |

### P1 activation checklist — complete before the clock starts

- [ ] Owner separately approves P1, remains available for suspend/resume and has
  reviewed the [P2 decision checklist](P2_EXACT_PLAN_DECISION_CHECKLIST.md) in advance.
  A two-minute decision slot is a ceiling, not pressure to approve; no timely
  decision means restore writers and close without installation.
- [ ] Freshly confirm the only controllable writers are jaymax-api and exact
  Toast jobs 3/4, Companion remains local-only, and no manual/script/coworker
  writes or **merges to main during the window** will occur. Merges can
  automatically deploy the API. Unexpected deployment/activity holds execution.
- [ ] Prepare a memory target of **at least 1.3 GiB free before activation**,
  retaining the existing hard start gate of at least **1 GiB and 15% free under
  load** and existing monitoring/stop floors. The 1.3 GiB target is headroom, not
  a new tool gate or permission to close other applications. The owner can close
  unused apps before activation. Earlier 610 MiB / 914.7 MiB refusals are dated
  observations; no memory or resource check is performed by this document.
- [ ] Place the window outside staff activity and away from Toast's scheduled
  starts. The dated job strings are `15 10 * * *` and `20 10 * * *`, with
  `cron.timezone=GMT` in retained evidence. Capture current timezone/schedules
  during separately approved preflight and convert for the actual window date:
  10:15/10:20 UTC is 06:15/06:20 EDT or 05:15/05:20 EST. Do not change schedules.
- [ ] Capture API/frontend Live source equivalence to accepted c3b429a and the
  intended reviewed documentation follow-up, original API state, exact Toast
  identities/schedules/roles/command digests, and available restoration controls.
  A different/unreviewed source holds before suspension; never deploy to force a match.
- [ ] Record the actual dashboard instance plan. The October 21 capture showed
  **Free** while `render.yaml` declares `starter`; neither proves today's plan.
  Capture the discrepancy without changing a plan, instance, settings or billing.
- [ ] Recheck protected configuration/artifact custody, available disk and owned
  PostgreSQL 17 recovery tools through the existing guarded runner. Use no stale
  binding after a credential/configuration change; regenerate/requalify packets.

Unknown writers, insufficient resources, unavailable restore controls or an
incomplete checklist hold activation. Record the actual start/deadline only after
fresh approval and passing loaded checks. No previous window is reopened.

Strict drain requires two full-visibility quiet observations at least 45 seconds
apart, reviewed-role session/transaction checks and no outstanding cron/HTTP/sync
work. Repeat the pre-export guard. Empty query results alone do not stop future
writers returning. Do not terminate Supabase platform sessions to make a guard pass.

## Proposed relative schedule and recovery reserve

The clock begins only when the operator acknowledges a fresh P1 approval and
records the start/deadline. Complete resource/source/private-storage preparation
before activation. The following are stage ceilings and operator stop points,
not a new controller or promises that every stage will use its full budget.

| Relative time | Activity / decision |
| --- | --- |
| 0:00–6:00 | Capture original states, suspend approved writers, establish strict drain. If not complete, recover and close. |
| 6:00–16:15 | Fresh encrypted export, with the existing 600-second work limit plus bounded cleanup. Retain authenticated source/ledger/catalog/sequence evidence and private key custody. |
| 16:15–26:30 | Disposable local restore/verification and owned cleanup, within the remaining stage reserve. Compare rows, sequences, catalogs, ledger and access guards; refuse a nonempty target. |
| 26:30–36:45 | Full current qualification, source/baseline reconciliation and exact P2 plan preparation. Any stale/missing/changed baseline holds. |
| 36:45–38:45 | Present P2 target/delta/version/plan SHA/backup bindings for owner approval. No response is not approval. |
| **By 39:00** | Hard latest start of apply/independent verification, only with exact P2 approval, at least 1,200 s for work/restoration **plus 15 s cleanup**, and the closing margin. At 39:00 the 60-minute window has 1,260 s left. If late or reserves do not fit, do not apply; restore writers and close. |
| 39:00–49:15 | At most the existing 600-second apply/verification budget and bounded cleanup. No retry after an ambiguous commit. |
| 49:15–59:15 | Restore and verify original writers, including the owner-reported Render Live commit. |
| 59:15–60:00 | Closure evidence and remaining uncertainty. No deadline extension. |

If any stage threatens the later reserve, cancel only owned work through the
reviewed cleanup path, restore original writers and close without applying.
The adapter's 660-second technical floor is not the operator's recovery margin.
Resource start remains at least 1 GiB and 15% free under load; monitoring and
private ACL/disk guards remain unchanged. Do not close unrelated applications.

## P2: exact proposed persistent delta, still not executable approval

Only `migrations/20261018_reviewed_inventory_pars.sql` through the accepted
par-specific installer/envelope may be used. Do not replay old migrations or
install Companion's chain.

| Object | Exact allowed delta |
| --- | --- |
| `purchasing.inventory_par_versions` | One initially empty append-only table, 17 columns and 17 constraints (three foreign keys, with 12 internal FK triggers). |
| Indexes | Six unique indexes: `inventory_par_versions_pkey`, `inventory_par_versions_predecessor_id_key`, `inventory_par_versions_request_key_key`, `inventory_par_versions_id_store_id_item_code_key`, `inventory_par_versions_store_id_item_code_revision_key`, `inventory_par_root`. |
| Function | One invoker trigger function, `purchasing.guard_inventory_par()`. |
| Triggers | `valid_inventory_par`, `immutable_inventory_par`, `retained_inventory_par`, plus 12 internal foreign-key triggers. |
| New-object security | Enable RLS; revoke PUBLIC and existing anon/authenticated direct rights on the new table/function. Add no policies or runtime grants. This narrow new-object security delta must be included explicitly in P2, despite the continuing general grant hold. |
| Ledger | One `reviewed_inventory_pars` row with the verified transaction-free body and a fresh 14-digit version greater than the actual installed maximum. |

Columns in order: `id uuid`, `store_id text`, `item_code text`, `revision integer`,
`predecessor_id uuid`, `unit_profile_id uuid`, `source_unit text`,
`quantity numeric`, `factor numeric`, `base_unit text`, `base_quantity numeric`,
`confirmed boolean`, `coverage_note text`, `actor text`, `recorded_at timestamptz`,
`request_key uuid`, `request_fingerprint bytea`.

Reviewed raw SQL SHA-256:
`84814517f75bb58940a36facdbf5a7934036ff5b388e97a820038e837416506e`.
Transaction-free body SHA-256:
`3a189a8b2a352cbd560cea88194dbde1940f160a54e7bcd4616d719c47b88c48`.
Catalog reference SHA-256:
`8a18effb17929604c76817ed7478b112033df4886e4434c0c1e6a4cce01e8e17`.
The normative reference also includes index attributes; its 28 column records
are not 28 table columns. There is no new schema, sequence, type, view,
extension, backfill, confirmed zero, existing business-row rewrite or installation
store-revision increment.

**No executable plan SHA or delivery version is allocated locally.** They depend
on the freshly drained hosted baseline and authenticated backup/restore receipts.
P2 must name these exact fresh bindings. This proposal's hash cannot substitute
for an installer plan hash, and the consumed calibration approval cannot be reused.

Preserve lock/probe/DDL/idle/operation limits of 5/20/30/120/600 seconds. Original
rows, sequences, object definitions, roles/memberships/grants/policies and ledger
history must remain unchanged except for the approved additive delta. Apply and
fresh independent outcome verification must agree before writers resume. If the
response is lost, reconcile the original plan; never resend SQL to discover its
outcome. A confirmed additive install is retained, not dropped as a rollback.
Repair/restoration requires its own reviewed authority.

## P3: later fictional acceptance, separately approved

After a verified installation and writer restoration, prepare an exact Bert's
fictional-fixture packet: item/profile IDs, actor and store revisions, protected
Track 1 baseline, expected history/revision increments and transport controls.
Cover confirm, explicit zero, withdrawal, exact decimals, stale profile/revision,
same-key retry, reload/sign-in recovery, dropped response, held/local discard
and wrong-actor/location refusal. Keep all fictional history; no business-data
cleanup/delete or real purchase/count/prep/sales change is included.

A separately approved S2a rotation must stay outside P1. Afterwards regenerate
configuration-bound inputs, record the new private revision/digests and repeat
required qualification; today's consumed health/calibration receipts cannot
authorize a new run. The security plan recommends S1 then targeted S2a before
par maintenance, subject to owner decisions on the concrete packets. R1 is not
an invented prerequisite for installing pars on the existing build path.

The par editing freeze ends only after acceptance. Ordering stays manual and
Track 1 independent. Credential rotation, O1 runtime grants/connection cutover,
identity adoption, managed-service recovery and operational release are separate
packages. Par installation can proceed on the existing owner-connected build
path; O1 is not silently made a new installer prerequisite.

## Approval record

P1 window: **not approved**. P2 exact SQL plan: **not generated / not approved**.
P3 live acceptance: **not approved**. No service or database change has been made
while preparing this proposal. Approving a document, local design or PR does not
activate a window or authorize a later stage by implication.
