# PR55 review amendments — October 22, 2026

PR55 merged with separate owner approval as ec0480b on October 22 at 7:44:35
p.m. Eastern. Its tree matches reviewed 25f1e14; reviewed-head and merged-main
CI each passed all four checks. The owner authorized local amendments, tests and
normal pushes, then separately approved merge/automatic test deployment.
Hosted work, service controls and
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

## Completed restored-data function timing

After the owner freed memory, fresh loaded-process observations passed and the
loopback-only restored-data run completed at a8f9e3d. The production/tooling
sources at that head are unchanged from green code commit 0153381; a8f9e3d's
four [fresh CI checks](https://github.com/jeffwelch0620-png/JayMax-Concepts-/actions/runs/39871230590)
also passed separately, with the same profile counts.

The [new function-timing receipt](REVIEWED_PAR_QUERY_REDUCTION_FUNCTION_TIMING_20261022.json)
and [exclusive breakdown](REVIEWED_PAR_QUERY_REDUCTION.md#pr55-review-amendments)
record 370 preparation calls and 1,112 apply/fresh-verification calls. The latter
took **75.938 seconds** on loopback. Inclusive function totals overlap;
exclusive counts/seconds reconcile to phase totals. Await times are not pure
server execution or network latency. No SQL, parameters or row values are in
the public breakdown, and production tools do not import the instrumentation.

Original rows, sequences, catalog/security and complete local inventories were
preserved; the new local par table was empty and ledger delta exactly one. The
owned server stopped, cleanup had no errors, retained encrypted backup and
closed-window evidence were unchanged, and there were no nonloopback attempts.
The original timing receipts remain unchanged. The first attempt held before
database startup at 971.3 MiB free, below the unchanged 1,024 MiB/15% start floor;
it remains refusal evidence and is not counted as a successful timing run.

The original 69.859-second candidate gives a 531.928-second additive sensitivity
estimate using the older hosted preparer. Substituting this diagnostic run gives
approximately **538.007 seconds**. These are not hosted forecasts and do not
establish why local cost per call changed. Both exceed the proposed **450-second
planning screen**. Hosted application therefore remains held independently of
whether this code/documentation PR is merged. No timeout or preservation check
was relaxed. A later bounded read-only hosted probe requires separate approval.

## Merge completed and remaining holds

All four [final-head checks](https://github.com/jeffwelch0620-png/JayMax-Concepts-/actions/runs/39872223468)
and all four [merged-main checks](https://github.com/jeffwelch0620-png/JayMax-Concepts-/actions/runs/39873776043)
passed separately. Deployment completion and hosted behavior have not been
inspected. The [local attribution follow-up](LOCAL_PAR_ATTRIBUTION_20261022.md)
is unpushed, pending a separate owner draft-push decision. No hosted request,
service control or real credential/grant/schema/
connection change occurred. No maintenance window is active, and no dated backup
or old window is current authority. Par editing remains frozen, ordering manual
and Track 1 independent. O1/G04/G13 and live acceptance remain separate workflows.
