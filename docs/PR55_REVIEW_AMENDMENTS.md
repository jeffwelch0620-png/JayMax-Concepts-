# PR55 review amendments — October 22, 2026

PR55 remains draft. The owner authorized local amendments, tests and normal
pushes, with a return for merge approval. Hosted work, service controls and
credential, grant, connection and schema changes remain held. Only disposable
loopback PostgreSQL regression testing was performed.

## Completed changes

- **B1:** merge commit a4adba8 joins accepted main ed62beb to the PR branch.
  Its tree is exactly reviewed 84fd182's tree:
  `b5209507df7bb1e12ba2f112ae64f15c5727ae30`. No rebase or force-push occurred.
- **N2:** code amendment 0153381 adds an early Python 3.12 minimum-runtime guard
  to the packet CLI. Unsupported versions return `held`, a fixed reason and
  exit 2 before arguments, source reads or output writes. The regression checks
  unsupported versions, no file I/O and no argument processing.
- **N1:** checkout rules pin all 18 portable core Python/JSON paths to LF. All
  31 exact SQL byte hashes and their reviewed LF/CRLF rules remain unchanged.
  Historical proposal and source manifests are unchanged. Content equivalence
  does not replace raw byte bindings; changed checkout bytes require freshly
  generated/reviewed packets and plans.
- **P1, design/instrumentation:** the runbook now records the approximately
  532-second additive estimate and a proposed 450-second planning threshold
  (25% headroom). This is a planning screen, not proof or execution authority.
  The existing 600-second limit and preservation checks are unchanged.
  Optional local-only diagnostic wrappers report driver-method counts/seconds
  for readiness, fingerprints, catalog capture, ACL/index state, ledger and
  readiness_check. Inclusive function totals overlap; exclusive groups attribute
  each method once and reconcile to phase totals. SQL, parameters, rows and
  exception text are not retained by those counters. Production tools never
  import the instrumentation module.

## Fresh validation

At code amendment 0153381fc33c82b0de93e1236cb8ccc1fa71563e:

- Complete local offline profile: **1,276 cases**, 453 methods + 823 subtests;
  zero failures/errors/skips, 84.93 seconds.
- Focused packet/readiness/metrics checks: 33 methods + 63 subtests, all passed;
  overlaps the complete profile.
- Three new PostgreSQL regression methods + 12 subtests: **15 cases**, all
  passed in 82.20 seconds. Complete local role/database inventories restored,
  owned server stopped, no hosted connection.
- All four [fresh CI checks](https://github.com/jeffwelch0620-png/JayMax-Concepts-/actions/runs/39870349090)
  passed: **1,079 frontend tests / 83 suites and strict build**, **1,276 Windows
  offline cases**, **257 backend/disposable PostgreSQL cases** (142 methods +
  115 subtests), and the aggregate required check. Profiles overlap local/prior
  evidence. The CI database profile selects all three new regression methods.
- Syntax, generated contract checks, core text attributes, all exact SQL hashes
  and tree-preservation checks passed. New v2 packet generation verified all
  49 core / 56 total source bindings; every execution approval remains false.

## Remaining before a merge recommendation

The real restored-data function-timing rerun has **not completed**. Its first
attempt held before database startup because loaded memory was **971.3 MiB**,
below the existing **1,024 MiB / 15%** start requirement. No connection was made
and the server remained stopped. That refusal is not counted as a passed timing
run. Protected refusal-receipt SHA-256:
`e41ca7f50d5fed84d3efd8a27c1b40c498f923f753f99ed959cc3c5d2a33488e`.

Keep the original timing receipts unchanged. Once a fresh loaded-process
resource observation passes, run the prepared loopback-only restored-data
rehearsal, verify preservation and complete owned cleanup, then publish a new
count/time-only function breakdown with both exclusive and inclusive semantics.
Bind the harness to the then-reviewed source tree and verify a fresh packet;
do not bypass source checks or weaken the resource floor.

The retained candidate had 1,112 calls / 69.859 seconds. The arithmetic
69.859 + 1,112 x ((311.766 - 15.078) / 714) gives **531.928 seconds** — about
68 seconds (11%) remaining under 600. This exceeds the proposed 450-second
planning screen. The estimate mixes transport, server and scheduling costs
from different runs; the rise in local cost per call does not establish its
cause. Instrumentation alone cannot prove hosted timing. A future bounded
read-only hosted probe requires separate owner approval and cannot authorize DDL.

PR55 should remain draft until the remaining timing evidence and final-head CI
are verified and the owner separately approves merge/automatic test deployment.
Installation remains held independently of a code merge. No old maintenance
window or dated backup may be reused as current authority. Par editing remains
frozen, ordering manual and Track 1 accounting independent. O1/G04/G13 and live
functional acceptance remain separate workflows.
