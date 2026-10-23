# Reviewed-par installer query reduction — local candidate

## Scope

Owner-authorized local tooling changes, regression tests, restored-data timing
rehearsal and JMax updates only. Hosted work and credential, grant and schema
changes remain held. The owner subsequently approved draft PR55 publication and
the [review amendments](PR55_REVIEW_AMENDMENTS.md); merge approval remains separate.
Fictional regression targets and owned disposable local restores
are the only database execution scope.

The previous [local timing receipt](REVIEWED_PAR_LOCAL_TIMING_20261022.json)
measured 714 calls / 15.078 s preparation and 2,396 calls / 58.578 s application
plus fresh-connection verification. The earlier hosted preparer operation was
311.766 s. Those measurements do not establish hosted application timing.

## Changes and preserved checks

1. `deployment_readiness.migration_object_presence` uses four set-based read-only
   queries per inspection. It retains the original table/function-name,
   trigger-parent and index-parent predicates, per-file missing-object order and
   historical/current migration selections. Duplicate references are fetched
   once but still appear in each applicable file's diagnostics. No result is
   cached for a later inspection or across DDL. Index definition/state, role,
   effective privileges, PUBLIC/default grants, disabled triggers and invalid
   constraints keep their existing checks.
2. The par snapshot collects the same identity, original columns/rows, ledger
   and ledger security contract directly, then its complete normative catalog.
   It no longer invokes the older index snapshot's catalog/access report merely
   to replace/discard it. The historical index installer is unchanged.
3. Outcome validation proves exact original columns/types plus the one expected
   new table before comparing original row fingerprints already captured in that
   same outcome snapshot. It removes the second full original-projection scan,
   not the preservation proof. Each subsequent phase and independent connection
   still captures its own new complete snapshot.

The migration SQL/catalog reference, canonical fingerprint formats (which remain
distinct), sequence observations, before/after backup comparisons, fresh writer
checks, transaction/lock ordering, 5/20/30/120/600-second limits, precommit checks,
unknown-commit handling and independent reconciliation are unchanged. No parallel
connections, hidden exclusions, new schema objects or runtime grant repair.

## Source binding

Historical proposal/audit/content-pin files and earlier packets remain immutable.
The [qualification builder](../tools/ops/par_qualification_packet.py) now emits
v2 and explicitly binds the historical and candidate content hashes of exactly
the two changed core tooling files. All remaining core pins and SQL byte hashes
remain historical. A v2 output still binds 49 core / 56 total source files, keeps
all execution approvals false and labels the tooling as requiring independent
review. Old v1 packets, source changes or changed amendment hashes hold. Updating
these local bindings is not approval to reuse any closed maintenance window,
old hosted plan, backup or credential configuration for application.

## Validation

All selected local checks passed:

| Profile | Result |
| --- | --- |
| Focused offline | 48 methods plus 174 subtests; 222 reported cases |
| Complete offline selection | 448 methods plus 821 subtests; 1,269 reported cases; zero failures/errors/skips |
| Disposable PostgreSQL regressions | 51 methods plus 66 subtests; 117 reported cases; zero failures/errors/skips |
| Restored-data timing | Verified applied locally; exact preservation/delta and owned cleanup passed |

These profiles overlap; do not sum them as unique coverage. The offline run took
5,071.38 s and database selection 784.86 s; the original logs/JUnit receipts are
retained, not relabelled as fast runs. The final database receipt verified unchanged
role/database inventory, owned server stopped and no hosted connection. No test
failure was suppressed. The unchanged multipart/FastAPI deprecation notices remain.
Frontend tests/build were not rerun for this tooling-only change; fresh full CI
remains a gate after any approved draft publication.

New regression cases compare batched results and complete reports against an
independent copy of the original per-object predicates, before/after the par
boundary and under both 30-file historical / 31-file current contracts. They
cover duplicate requests, function overloads, wrong schema/parent identities,
fresh drops and query failures. Snapshot parity, one fingerprint pass per
outcome, changed rows/columns/types and later independent reads are checked
alongside existing role, security, accounting, rollback and lost-ack tests.

## Restored-data timing and limits

The [candidate receipt](REVIEWED_PAR_QUERY_REDUCTION_TIMING_20261022.json)
authenticates the same retained application archive as the
[earlier baseline](REVIEWED_PAR_LOCAL_TIMING_20261022.json). Both restores matched
120 tables, 45,648 table rows and 13 catalog groups. Major PostgreSQL versions
match; the source/local patch versions differ. Managed recovery remains untested.

| Stage | Earlier calls | Candidate calls | Earlier elapsed | Candidate elapsed |
| --- | ---: | ---: | ---: | ---: |
| Restore/equality | Not instrumented | Not instrumented | 25.047 s | 40.031 s |
| Preparation | 714 | 370 | 15.078 s | 23.985 s |
| Apply + independent fresh-connection verification | 2,396 | 1,112 | 58.578 s | 69.859 s |

Measured method-call reductions are **48.2%** for preparation and **53.6%** for
apply/verification. The wrapper counts execute/fetch/fetchval/fetchrow calls;
transaction-control and cursor protocol traffic are not counted. Both runs use
the same instrumentation boundary. This is not a count of all network packets.

Elapsed time did **not** improve in these separate executions. Restore, whose
implementation was unchanged, was also slower; this observation does not prove
which environmental/server costs caused the differences. Do not advertise a
local elapsed-time speedup or forecast Supabase timing from these measurements.
The 69.859 s candidate application/verification fits the unchanged 600 s limit
on loopback; hosted fit is still unproven.

For arithmetic sensitivity only, adding 250/400/500 ms per measured candidate
call gives approximately **347.859 / 514.659 / 625.859 seconds**, respectively.
These are not hosted measurements or injected-delay tests. Keep every timeout,
preservation check and recovery reserve. Independent review is the next gate,
not an automatic outage or another local optimization by implication.

The candidate's new local table was empty and ledger delta exactly one row.
Original rows, sequences, catalog and security were preserved. Complete original
local role/database/membership inventory was restored, seven guarded loopback
connection attempts and zero blocked/nonlocal attempts recorded, and the owned
server stopped without cleanup errors. Retained encrypted archive and closed-window
receipt were unchanged. Loaded memory before startup was 1,424.9 / 1,384.2 MiB
(23.63% / 22.95%). No Supabase/Render request, service control or real credential,
grant, connection or schema change occurred.

Candidate v2 source packet SHA-256:
`7cebd3528398acec1d85b4aed727fc5f7702d5a91138778d678e502d1eb16e43`.
Protected full timing receipt SHA-256:
`c82b80085f54a5b52d0df7cd1de21072b117086efdd8fa7a11b0770e73e4ad0f`.
The single-use local harness/archive/key/full-plan paths stay outside Git/Pages.

Syntax, generated contract guides, relative links, unchanged historical/guard
sources, exact migration hash and packet verification are checked before commit.
The core apply/prepare/readiness/role/plan-validation/reconciliation-lock functions
retain their original AST outside the two expressly changed snapshot/outcome
collection sections. The historical index installer and hosted adapter are unchanged.

## Next gate

The function-timing rerun and all final-head/merged-main CI checks passed.
PR55 merged with separate owner approval as ec0480b. The
[local attribution follow-up](LOCAL_PAR_ATTRIBUTION_20261022.md) is published
with owner approval as draft PR56, for independent review and fresh CI. Merge
remains a separate owner decision.
Even improved loopback timings do not prove hosted fit; retain the separate
health, writer/drain, fresh backup/restore, exact-plan, installation-window and
fictional live acceptance approvals in the
[installation runbook](REVIEWED_PAR_INSTALLATION_RUNBOOK_20261022.md).


## PR55 review amendments

The branch was merged normally with accepted main ed62beb in a4adba8. That
merge's tree is exactly the original reviewed 84fd182 tree; no rebase or
force-push was used. The bounded code amendments are 0153381. The packet CLI
now refuses Python below 3.12 before parsing arguments or reading/writing files.
All 18 portable core Python/JSON paths are LF-pinned; all 31 exact migration
hashes and their reviewed LF/CRLF rules are unchanged. Historical manifests,
receipts and approved-source hashes are retained. Fresh byte-bound packets and
plans remain required after any checkout-byte change.

Local validation passed **1,276 offline cases** (453 methods + 823 subtests),
with no failures/errors/skips, in 84.93 seconds. The focused packet/readiness/
instrumentation selection passed 33 methods + 63 subtests, overlapping the full
profile. The three PostgreSQL regression methods and 12 subtests passed (15
reported cases) in 82.20 seconds, with original local inventories restored and
the owned server stopped. No Supabase/Render connection or service control was
used. Fresh CI, exact-head review and owner merge approval remain separate.

The [new instrumented local receipt](REVIEWED_PAR_QUERY_REDUCTION_FUNCTION_TIMING_20261022.json)
retains counts and seconds without SQL, parameters or row values. Earlier
receipts are unchanged. Preparation measured **370 calls /
24.766 seconds**; apply plus fresh-connection independent
verification measured **1112 calls / 75.938
seconds**. The original rows, sequences, catalog and security were preserved,
the new local table was empty and the ledger delta was exactly one. All original
local inventories were restored, the owned server stopped and cleanup had no
errors. This diagnostic run is not a controlled speed comparison or hosted proof.
The initial attempt held before database startup at 971.3 MiB free; it is retained
as a resource refusal, not counted as a passed rehearsal.

Exclusive groups below attribute every measured driver method exactly once;
their counts and unrounded seconds reconcile to each phase total. The JSON also
contains inclusive function totals, which overlap and must not be added together.
ACL/index groups outside leaf catalog/fingerprint/ledger functions are classified
by fixed local query shapes; query text itself is never retained. Await time mixes
server work, transport and client scheduling. Cursor/transaction protocol traffic
is excluded, matching the earlier method-count boundary. Restore is uninstrumented.

| Exclusive group | Prepare calls | Prepare seconds | Apply/verify calls | Apply/verify seconds |
| --- | ---: | ---: | ---: | ---: |
| acl | 6 | 0.015000 | 18 | 0.048000 |
| capture_catalog | 13 | 0.172000 | 39 | 0.502000 |
| fingerprints | 120 | 12.078000 | 362 | 37.827000 |
| index_state | 2 | 0.109000 | 6 | 0.077000 |
| ledger | 17 | 0.063000 | 49 | 0.328000 |
| other | 152 | 11.440000 | 458 | 35.045000 |
| readiness | 42 | 0.140000 | 126 | 0.251000 |
| readiness_check | 18 | 0.062000 | 54 | 0.125000 |

The original candidate's hosted-derived additive estimate is about 532 seconds
(69.859 + 1,112 x 0.415529). Substituting this diagnostic run's measured elapsed
time gives about **538.007 seconds**. Neither is a hosted prediction. Both
exceed the proposed **450-second planning threshold**, so installation remains
held. The 600-second limit and every preservation check remain unchanged.
A separately authorized bounded read-only hosted probe may inform a later
proposal; no such probe is authorized or performed here. Par editing remains
frozen, ordering manual and Track 1 independent.
