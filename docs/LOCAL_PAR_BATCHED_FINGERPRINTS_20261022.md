# Local bounded par fingerprints - October 22, 2026

## Accepted baseline and publication boundary

[PR57](https://github.com/jeffwelch0620-png/JayMax-Concepts-/pull/57) merged with
owner approval at 9:04:21 p.m. Eastern / October 23 01:04:21 UTC as
54ce10c1ca2e4d040c217a0132d78264ce7624ac. Its tree exactly matches reviewed
a511b381399ebe759a898aa4e6ab3b0a6b9981ab. The four
[reviewed-head checks](https://github.com/jeffwelch0620-png/JayMax-Concepts-/actions/runs/39880360014)
and four [merged-main checks](https://github.com/jeffwelch0620-png/JayMax-Concepts-/actions/runs/39881885410)
passed separately: 1,079 frontend tests / 83 suites plus strict build, 1,323
Windows offline cases and 270 backend/PostgreSQL cases. Profiles overlap.
The merge permits the existing automatic Render test deployment; deployment
completion and hosted behavior were not inspected.

The owner authorized this separate local optimization, local regression/timing
checks and JMax updates. Measured final code is
569ade9f2ce485e7b7bd8d9b189f337211cf16bd on codex/par-bounded-fingerprints.
The owner subsequently approved publication as
[draft PR58](https://github.com/jeffwelch0620-png/JayMax-Concepts-/pull/58), initially
at a5eae9d266270fa3ac5ae07ceb39c1942d0daa08. The publication-link commit changes
documentation only. Fresh exact-head CI, independent review and merge approval
remain separate; no hosted validation is implied. Hosted work/service controls and credential, grant,
schema and connection changes remain held. No maintenance window is active.

## Bounded change and preserved contracts

- New par-only original-projection and backup-fingerprint helpers batch **two
  relations per statement**. An explicit size from one through four is validated
  and tested; current par callers use two. Every chunk requires exact integer
  positions, unique/full coverage, nonnegative integer counts and lowercase
  SHA-256 values before any member is used. Bad results and timeouts fail closed.
- Historical `fingerprints`, `relation_fingerprint` and `fingerprint` function
  bodies stay byte-for-byte unchanged, checked by frozen source hashes. Existing
  non-par backup/index callers continue using them. Independent frozen pre-batch
  functions provide result oracles; the new algorithm does not validate itself.
- The two hash formats stay separate. Original-column preservation retains its
  existing projection, sorted hashes without a newline, exact synthetic exclusions
  and column/type checks; no probe, row limit or fallback is added. The backup
  format keeps newline/C-order hashing, its existing 8 MiB hash-payload probe,
  full-relation cursor fallback and path counters. A full probe is discarded;
  sequences and legacy modes retain the original path.
- Relation-count limits are **not PostgreSQL memory bounds**. Existing 20-second
  statement and 600-second operation limits remain; no retries after malformed
  output or timeout, cross-phase caches, parallel target connections, skipped
  verification or broader exclusions are introduced. Pre/post/fresh-connection
  snapshots and rollback/unknown-outcome guards remain separate.
- Four follow-up source links bind backup, preservation, the par engine and the
  hosted adapter. The engine link begins at its earlier amendment's resulting
  hash. The original two links, proposal, pins, SQL and historical receipts remain
  intact. V2 packets disclose the chain and refuse stale/missing/disconnected
  links and unknown paths. Coverage stays 49 core sources, 56 total sources and
  31 exact SQL files, with every execution approval false. See the
  [operator handoff](PAR_QUALIFICATION_EXECUTION_PACKET.md).

## Final local validation

- **1,352 offline cases** passed: 472 methods plus 880 subtests, zero failures,
  errors or skips, in 60.51 seconds on the final two-relation code.
- **135 PostgreSQL cases** passed: 32 methods plus 103 subtests in 523.33 seconds,
  with zero failures/errors/skips. Coverage includes independent digest parity,
  exact exclusions, NULL/duplicate/Unicode/binary/numeric values, text/UUID
  parameters, chunk boundaries, partition/materialized relations, sequence and
  bounded-cursor fallback paths, malformed results, type/late-row drift,
  repeatable-read freshness, query timeout recovery and installer security/
  rollback/reconciliation guards. Original local database/role inventories matched
  and the owned PostgreSQL server stopped.
- A prior final-code database attempt refused before starting PostgreSQL at about
  941 MiB free. After the owner freed memory, the accepted final run started at
  1,306.3 MiB / 21.66%, meeting the unchanged 1 GiB / 15% floor. Resource refusal
  is not counted as a passed run.
- The final guarded retained-data rehearsal passed: all 120 tables, 45,648 rows
  and 13 catalog groups matched. Original rows/sequences/security were preserved;
  the new local table stayed empty and the ledger delta was one. Local inventories
  were restored, cleanup was clean and the owned server stopped. There were zero
  nonloopback connection attempts (six loopback attempts). Its two loaded memory
  samples were 1,237.8 and 1,201.5 MiB free, above the unchanged start floor.
  The encrypted archive and closed-window receipt
  stayed unchanged; no fresh hosted backup or hosted connection was used.
- No new local frontend/build run was needed for this maintenance-tooling slice.
  Accepted-main CI above is baseline evidence, not fresh CI for this candidate.
  Future publication, independent review and merge remain separate gates.

## Measurement and default selection

The [public receipt](LOCAL_PAR_BATCHED_FINGERPRINTS_20261022.json) retains counts,
fixed categories and numeric timings only. SQL, arguments, identifiers, row
values, private paths and exception text are excluded. The protected receipt is
retained separately. API operations and query methods are separate measurements;
neither establishes protocol round trips.

| Metric | Prepare | Apply plus fresh independent verification |
| --- | ---: | ---: |
| Query-method calls | 254 | 764 |
| Query await seconds | 13.843 | 44.001 |
| Phase elapsed seconds | 14.141 | 45.063 |

Uninstrumented restore took 24.922 seconds. An extra
**local-only unbatched probe** took 14.547 seconds /
255 query calls; it is outside apply/verification elapsed time
and does not replace any later check. Against PR57's dated 1,112 query calls /
75.218 seconds, final apply/verification calls fell **31.29%**.
The runs are not a controlled elapsed-time benchmark or hosted timing proof.

| Exclusive apply/verification group | Query calls | Query await seconds |
| --- | ---: | ---: |
| acl | 9 | 0.032 |
| apply_ddl | 1 | 0.031 |
| backend_permissions | 42 | 0.045 |
| backup_catalog | 48 | 0.330 |
| backup_compare | 0 | 0.000 |
| backup_fingerprints | 185 | 20.156 |
| capture_catalog | 39 | 0.374 |
| fingerprints | 182 | 22.407 |
| identity | 5 | 0.016 |
| index_state | 6 | 0.063 |
| ledger | 64 | 0.297 |
| locks | 7 | 0.016 |
| object_guard | 3 | 0.000 |
| original_columns | 6 | 0.031 |
| other | 0 | 0.000 |
| outcome_check | 4 | 0.000 |
| readiness | 120 | 0.140 |
| readiness_check | 18 | 0.048 |
| sequences | 0 | 0.000 |
| session_settings | 16 | 0.000 |
| writer_guard | 9 | 0.015 |

| Public apply/verification API operation | Calls | Completed | Errors | Cancelled | Exhausted |
| --- | ---: | ---: | ---: | ---: | ---: |
| cursor_create | 3 | 3 | 0 | 0 | 0 |
| cursor_iter | 3 | 3 | 0 | 0 | 0 |
| cursor_next | 6 | 3 | 0 | 0 | 3 |
| transaction_commit | 14 | 14 | 0 | 0 | 0 |
| transaction_create | 14 | 14 | 0 | 0 | 0 |
| transaction_start | 14 | 14 | 0 | 0 | 0 |

The earlier four-relation prototype at 64337e7 passed its own 1,352 offline and
135 PostgreSQL cases and retained-data rehearsal (585 calls / 44.000 seconds).
Its slowest unbatched original-projection query await was 6.172 seconds; four
similarly heavy branches could exceed a 20-second statement. The final default
was reduced to two for more headroom. This is a local sizing judgment, not a
guaranteed hosted upper bound or a calibrated safety factor. Prototype evidence
is retained separately and is not substituted for final two-relation acceptance.

| Final apply/verification group | Largest observed query await seconds |
| --- | ---: |
| acl | 0.016 |
| apply_ddl | 0.031 |
| backend_permissions | 0.015 |
| backup_catalog | 0.031 |
| backup_fingerprints | 6.141 |
| capture_catalog | 0.031 |
| fingerprints | 6.453 |
| identity | 0.016 |
| index_state | 0.032 |
| ledger | 0.016 |
| locks | 0.016 |
| object_guard | 0.000 |
| original_columns | 0.016 |
| outcome_check | 0.000 |
| readiness | 0.016 |
| readiness_check | 0.016 |
| session_settings | 0.000 |
| writer_guard | 0.015 |

Maximum observed await includes instrumentation and client scheduling; it is not
isolated server execution or network latency. No universal exchange count or
18-second fingerprint bound is claimed. Fingerprints dominate the measured work
and were the selected optimization target; they are not proven the only lever.

The old additive sensitivity is dated planning arithmetic:
`45.063 + 764 * ((311.766 - 15.078) / 714)`
= **362.527 seconds**, below
the proposed 450-second planning screen. Public cursor/transaction API counts are
not added. This does not recalibrate the coefficient, establish hosted fit or
change the 600-second operation limit. Hosted timing still needs separately
approved measurement under the existing gates.

## Evidence bindings and next decision

- Public receipt SHA-256: `5bd4c6ca1102c9554cf3e4d451aa754e360ee0563c155e357ad9e59f5475a0d0`.
- Protected full receipt SHA-256: `f71b8d30531b908d94a5462c522945310fa8767004d5db3e2302e0a5670b3969`.
- Final source-packet SHA-256:
  `2c764723e901115b8a7afc8b9820549aab0025da9007ccfc2b2f3cb3081ec616`.
- Four-relation prototype protected receipt SHA-256:
  `238cac1664af86a9daf91cb80482817f9f160b6be8ae4ceea8f0f05bfa1253ed`.

Next action: complete fresh exact-head CI and independent review of draft PR58,
then return for separate owner merge approval.
No hosted work, service pause, credential, grant, schema or connection change is
authorized by this report. Par editing remains frozen, ordering manual and Track
1 independent. O1, G04/G13, functional health, managed recovery and live acceptance
remain separate open work.
