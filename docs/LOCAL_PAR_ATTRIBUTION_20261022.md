# Local par attribution follow-up — October 22, 2026

## Accepted baseline and scope

PR55 merged with owner approval on October 22 at 7:44:35 p.m. Eastern /
23:44:35 UTC as ec0480b67a89103ded95805bd194a50f676a3480. The merged tree
exactly matches reviewed 25f1e14. All four [reviewed-head CI checks](https://github.com/jeffwelch0620-png/JayMax-Concepts-/actions/runs/39872223468)
and all four [merged-main CI checks](https://github.com/jeffwelch0620-png/JayMax-Concepts-/actions/runs/39873776043)
passed separately: 1,079 frontend tests/83 suites plus strict build, 1,276 Windows
offline cases and 257 backend/disposable PostgreSQL cases; profiles overlap.
The owner approved the existing automatic Render test deployment. Deployment
completion and hosted behavior have not been inspected.

This follow-up is local attribution only on codex/par-local-attribution. Its
measured code revision is c85b7f21ddfaea366885d8d5ea153dfd32d74ae8. Runtime
installer, adapter, original-column and backup fingerprint algorithms, SQL,
timeouts, source pins and preservation/permission guards are unchanged. No
chunked fingerprint batching or parallel target connections were introduced.
Hosted work/service controls and credential/grant/schema/connection changes
remain held. The owner approved publication as
[draft PR56](https://github.com/jeffwelch0620-png/JayMax-Concepts-/pull/56).
Fresh exact-head CI, independent review and merge approval remain separate.

## Attribution and checkout changes

Fixed labels now distinguish original-column metadata, full backup comparisons,
backup catalog/row fingerprints, sequences, writer guards, locks, exact reviewed
DDL, session settings, identity, object/permission checks and outcome checks.
The local harness uses the committed binding factory; wrappers restore original
functions after success/failure. Dynamic relation labels use the existing kind
argument and choose only fixed categories. Exact DDL recognition is diagnostic;
the installer still independently checks its reviewed body and source hashes.
No SQL, parameters, relation names, row contents or driver exception text are
retained by the counters. Production tools never import this module.

Exclusive groups partition measured calls exactly once; inclusive function
totals overlap and cannot be added. Driver execute/fetch/fetchval/fetchrow await
time mixes server work, network waits and client scheduling. Cursor and
transaction protocol traffic stay outside the unchanged measurement boundary.
Sequence reads use cursors: zero counted sequence calls is not zero execution.
Restore is uninstrumented. The new source-integrity guide explains fresh clones
or a clean, explicitly scoped working-copy refresh and w/lf inspection before
new byte-bound artifacts, while preserving the existing exact SQL byte rules.

## Local validation

- Complete offline profile: **1,289 cases**, 459 methods + 830 subtests, zero
  failures/errors/skips, 84.37 seconds.
- Focused metric/packet selection: **36 methods + 68 subtests**, all passed;
  overlaps the complete profile. Covers new-group single attribution, parent
  totals, fixed dynamic labels, errors/restoration, exact DDL recognition,
  cursor exclusion and output redaction.
- The [new restored-data receipt](LOCAL_PAR_ATTRIBUTION_TIMING_20261022.json)
  passed with loaded memory 1500.0 /
  1335.1 MiB. The same retained archive
  matched 120 tables / 45,648 rows / 13 catalog groups. All original rows,
  sequences/catalog/security and original local inventories were preserved;
  the new local table was empty, the ledger delta one, owned server stopped
  and cleanup clean. No nonloopback attempt occurred. Retained encrypted backup,
  closed-window receipts, original timing evidence and all historical pins
  remain unchanged. Fresh packet verified 49 core/56 total bindings and all
  execution approvals false.
- No new frontend/build or broad database profile was run locally for this
  diagnostic-only change; accepted PR55 CI above is baseline evidence, not CI
  on this follow-up. PR56 CI is verified separately after publication; merge
  remains a separate approval gate.

## Measured calls and time

Preparation: **370 calls / 24.359 seconds**.
Apply plus fresh-connection independent verification: **1112 calls /
75.047 seconds**. Counts remain exactly 370/1,112, matching the
accepted boundary; this is attribution, not an execution reduction or speed claim.

| Exclusive group | Prepare calls | Prepare seconds | Apply/verify calls | Apply/verify seconds |
| --- | ---: | ---: | ---: | ---: |
| acl | 3 | 0.000000 | 9 | 0.031000 |
| apply_ddl | 0 | 0.000000 | 1 | 0.078000 |
| backend_permissions | 14 | 0.031000 | 42 | 0.062000 |
| backup_catalog | 15 | 0.188000 | 45 | 0.516000 |
| backup_fingerprints | 119 | 11.077000 | 359 | 33.250000 |
| capture_catalog | 13 | 0.172000 | 39 | 0.579000 |
| fingerprints | 119 | 11.890000 | 359 | 37.859000 |
| identity | 2 | 0.000000 | 5 | 0.015000 |
| index_state | 2 | 0.093000 | 6 | 0.094000 |
| ledger | 23 | 0.108000 | 64 | 0.453000 |
| locks | 0 | 0.000000 | 7 | 0.016000 |
| object_guard | 3 | 0.016000 | 3 | 0.000000 |
| original_columns | 2 | 0.032000 | 6 | 0.111000 |
| other | 0 | 0.000000 | 0 | 0.000000 |
| outcome_check | 0 | 0.000000 | 4 | 0.016000 |
| readiness | 40 | 0.125000 | 120 | 0.217000 |
| readiness_check | 6 | 0.016000 | 18 | 0.094000 |
| sequences | 0 | 0.000000 | 0 | 0.000000 |
| session_settings | 6 | 0.000000 | 16 | 0.015000 |
| writer_guard | 3 | 0.031000 | 9 | 0.047000 |

The earlier receipt placed 458 calls / 35.045 seconds in other. The finer
breakdown above assigns current work at a different granularity; compare phase
totals and function semantics rather than assuming exclusive rows are unchanged
between versions. Inclusive parent values are retained in the JSON.

## Recommendation and remaining gates

Using the same older hosted-preparer additive sensitivity (about 0.415529 extra
seconds per measured call), this run gives **537.116 seconds**, above the
proposed **450-second / 25% headroom planning screen**. This is arithmetic, not
a hosted forecast or latency measurement. At the earlier 75.938-second local
elapsed time, about 900 calls would meet that screen; the target must be
recomputed from the next measured elapsed time, not treated as an approval.
The 600-second limit, 20-second read-statement limit and all preservation checks
remain unchanged. Installation remains held independently of code publication.

Next, review the measured dominant fingerprint work and design one bounded
optimization with independent original-function oracle tests, exact per-table
hash/count/type/exclusion equivalence, unchanged snapshot boundaries and chunk
failure handling. Original-column hashes and full backup hashes have different
formats and purposes; preserve both independently. No result cache across
snapshots/phases, removed verification, timeout increase or parallel target
connection is proposed here. That implementation needs its own owner-authorized
slice. A bounded read-only hosted probe, any new maintenance window, fresh
backup/restore and exact-plan installation still require separate approval.

Par editing stays frozen, ordering manual and Track 1 the accounting baseline.
O1, G04/G13, functional health and operational/managed recovery acceptance remain
separate open workflows. No active maintenance window exists.
