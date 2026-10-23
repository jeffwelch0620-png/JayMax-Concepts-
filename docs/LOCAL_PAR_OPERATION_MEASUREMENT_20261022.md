# Local par cursor and transaction measurement — October 22, 2026

## Accepted baseline and authorization

[PR56](https://github.com/jeffwelch0620-png/JayMax-Concepts-/pull/56) merged with
owner approval at 8:25:45 p.m. Eastern / October 23 00:25:45 UTC as
86a44d4914107db6b3a958c19f8442caba767aaa. Its tree exactly matches reviewed
c5e1b3892955a33024ea5b9f6b97ebbafb088053. The four
[reviewed-head checks](https://github.com/jeffwelch0620-png/JayMax-Concepts-/actions/runs/39875813288)
and four [merged-main checks](https://github.com/jeffwelch0620-png/JayMax-Concepts-/actions/runs/39878059249)
passed separately: 1,079 frontend tests / 83 suites plus strict build, 1,289
Windows offline cases and 257 backend/disposable PostgreSQL cases. Profiles
overlap. The merge permits the existing automatic Render test deployment;
deployment completion and hosted behavior were not inspected.

The owner authorized this local measurement follow-up and reserved approval
before the next draft push. Measured source is
0674d899c9fed6ed3bcc6fbe47e848cb797084bb on
codex/par-local-operation-metrics. Nothing from this follow-up has been pushed.
Hosted work/service controls and credential/grant/schema/connection changes
remain held. No maintenance window is active.

## Changes and measurement contract

N1 is covered by an offline test importing the actual par adapter and checking
that every attribution binding resolves to a coroutine. Fixed labels and both
positional/keyword sequence/table selectors are checked against the public groups.

The optional local connection wrapper now separately observes public cursor and
transaction API calls. Cursor creation, iterator construction, each next request,
awaited cursor creation, fetch/fetchrow/forward, transaction creation, manual
start/commit/rollback and context enter/exit have fixed labels. Counts, await or
synchronous-call seconds and completed/error/cancelled/exhausted outcomes are
retained; group totals reconcile. Query-method counts/time keep the original
execute/fetch/fetchval/fetchrow boundary, including inclusive/exclusive semantics.
New operation counters are lazy, preserving query-only metric structure.

**These are API operations, not protocol round trips.** A 250-row iterable at
prefetch 100 produces 251 observed next requests, including terminal exhaustion;
that is not 251 network exchanges or a measurement of three fetch batches.
Buffered rows can require no network I/O. No inferred open/close or batch count
is added; no private asyncpg protocol hook or extra query is introduced.
Public transaction context exit delegates commit/rollback/savepoint decisions to
the driver; it is not relabelled as a successful database commit. A refused
transaction start can be an observed error with no statement executed. Context
suppression values and original errors/cancellation propagate unchanged.

Only fixed categories and numeric totals enter the metrics. SQL, arguments,
relation/row identifiers, returned values and exception text are not retained.
The wrapper necessarily references its live driver objects, but does not copy
their data into receipts. Production tools never import it. Unknown driver
methods continue to pass through without measurement. Concurrent scopes remain
task-local. Rounded zero seconds does not mean no work occurred.

## Validation

- All **1,323 offline cases** passed: 469 methods + 854 subtests, zero failures,
  errors or skips, in 108.17 seconds. The 20 focused metric methods overlap this
  profile. An initial standalone invocation lacked the local cryptography library;
  correcting the test environment resolved that setup failure before acceptance.
- Five new PostgreSQL methods / eight subtests (**13 reported cases**) passed,
  with no failures/errors/skips. Real asyncpg coverage includes cached/uncached,
  empty/exact-batch/250-row/early-exit cursors, awaited/manual cursor operations,
  invalid arguments, nested transactions, commit/rollback, rejected reuse,
  timeout/cancellation recovery, and original backup sequence/fallback parity.
  These methods are included in the disposable database CI profile. The launcher
  verified unchanged database/role inventories and stopped the owned server.
- The separately guarded restored-data rehearsal passed at the measured revision.
  It enforced loaded memory, exact source/packet hashes and a loopback-only socket
  guard before database work. Start memory was 1,168.1 / 1,156.4 MiB free, above
  the unchanged 1 GiB / 15% floor. All 120 tables / 45,648 rows / 13 catalog groups
  matched the retained archive; original rows/sequences/security and complete local
  inventories were preserved. The new local table remained empty, the ledger delta
  was one, cleanup was clean and the owned server stopped. Seven loopback connection
  attempts and zero nonloopback attempts were reported. No fresh hosted backup was
  taken; the retained encrypted archive and closed-window inputs are unchanged.
- All 49 core-source and 31 exact migration bindings are unchanged. A fresh v2
  packet binds 56 total sources, including the updated CI test selection; all
  execution approvals remain false. Historical packets/pins/receipts are unchanged.
- No new local frontend/build or broad database run was needed for this isolated
  instrumentation change. Accepted-main CI above is baseline coverage, not fresh
  CI on this unpushed follow-up. Publication, fresh CI and merge remain later gates.

## Restored-data measurements

The [public receipt](LOCAL_PAR_OPERATION_MEASUREMENT_20261022.json) retains the
original query totals and separate operation/group/outcome totals. Zero operation
groups are omitted from this public projection; its protected full receipt retains
the complete fixed vocabulary. Restore took 42.094 seconds and was uninstrumented.

Public receipt SHA-256:
`fdec367563bd83ebf340589b00421146de2b55b0685b4df7ae874ff1ba50b90f`.
Protected full receipt SHA-256:
`66dc36129a17810732fedb1e86fbf3e0f5c586f0f41dc78ca517c17142cf1584`.
Fresh packet SHA-256:
`dce56844b5eb886623740c24746a4e3e9c891c8b3505ca04456cae19535ef9d4`.
Private paths and original row/catalog data are not published.

| Metric | Prepare | Apply plus fresh independent verification |
| --- | ---: | ---: |
| Existing query-method calls | 370 | 1,112 |
| Existing query await seconds | 24.061 | 73.389 |
| Phase elapsed seconds | 24.703 | 75.218 |
| Cursor factory calls | 1 | 3 |
| Cursor iterator constructions | 1 | 3 |
| Cursor next requests | 2 | 6 |
| Rows yielded / exhaustion outcomes | 1 / 1 | 3 / 3 |
| Transaction factory calls | 6 | 14 |
| Manual transaction starts | 6 | 14 |
| Manual transaction commits | 6 | 14 |

Observed cursor work in this archive belongs to the sequence group. Query totals
remain exactly equal to PR56's 370/1,112 boundary, with zero unclassified query
calls. The large cursor fallback and context/savepoint/error paths are covered by
the fictional PostgreSQL fixtures, not claimed as events in this archive. Timing
varies between runs; no execution reduction or elapsed speedup is claimed.

## Model and next decision

Do **not** add these API counts to queryCalls and multiply by the old 0.415529
coefficient. That sensitivity coefficient came from a different driver-method
boundary and already mixes transport, server work and client overhead. Observing
API operations does not establish extra network exchanges or a recalibrated model.
The earlier 537.116-second sensitivity remains dated arithmetic above the proposed
450-second screen; the 600-second operation limit and 20-second statement limit
remain unchanged. This slice does not establish hosted readiness or approval.

After independent review, propose the next bounded local fingerprint optimization
as a separate slice. Preserve both formats independently: original-column
preservation has no existing 8 MiB aggregation probe/fallback, while the backup
fingerprint does. A chunk-times-payload estimate is not a hard bound on PostgreSQL
memory. Any later implementation needs exact oracle parity, exclusions/types/nulls/
duplicates/Unicode/chunk-boundary coverage, complete positional-result validation,
unchanged snapshots, fail-closed timeout behavior and explicit source amendments.
Do not remove verification, cache across phases or introduce parallel target
connections. A later hosted calibration probe needs separate owner approval.

Next action: ask the owner before pushing a new draft PR. Hosted work, service
controls and credential/grant/schema/connection changes stay held. Par editing
stays frozen, ordering manual and Track 1 independent. O1, G04/G13, functional
health, managed recovery and live acceptance remain separate open workflows.
