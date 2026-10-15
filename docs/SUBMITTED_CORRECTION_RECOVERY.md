# Submitted invoice-correction recovery

Local continuation of PR33 (`16e21c5`) and the October 15 workflow reconciliation
(`a798cbb`). The owner approved implementation and local testing. Hosted testing,
deployment, migrations, connection changes and credential rotation remain held
or separately deferred. Published as [draft PR34](https://github.com/jeffwelch0620-png/JayMax-Concepts-/pull/34).
The owner approved its review amendments; merging remains a separate approval.

## Problem and resulting behavior

Initial purchase posting already retained its submitted request in a same-tab
session journal. Posted-invoice correction previously retained its exact body/key
only in a component ref. Reload, sign-in or navigation could lose that evidence
after an uncertain save, although database correction guards still applied.

The correction flow now writes a separate, actor/location-scoped session journal
**before the first correction request**. It retains the exact submitted body/key,
version/document identity, predecessor, initial batch, reviewed hash, and selected
original/replacement display facts. Recovery never generates a replacement key
or sends a correction automatically. The frozen review shows received date,
quantities/conversions, reason, reversal/replacement food amounts and separate
tax/fees. An unresolved retained correction prevents another review for that
invoice, including a different captured version of the same invoice identity.

Storage must accept and read back the request before sending. Corrupt/unavailable
storage, quota loss or a mismatched existing review holds submission. The journal
allows at most 32 unresolved invoices and 2 MiB per actor/location. Duplicate
invoice identities and request keys are rejected. An explicit field allowlist
excludes authentication data, arbitrary server metadata and original file bytes.
This is a separate namespace; existing initial-post recovery is unchanged.

## Exact-request status read

`POST /api/pg/purchases/{store}/documents/{version}/correction-status` accepts the
same `ConfirmCorrection` body and `Idempotency-Key` as the correction command.
POST carries the submitted review; this endpoint performs only a repeatable-read,
read-only transaction. It uses the existing manager/owner and location boundary.
No schema, migration, grant or runtime-role change is needed. The review amendment
aligns the API command replay check with the status route's actor/version checks.

For an existing key, the server checks the recorded actor, replacement version,
initial batch and normalized full request fingerprint before identifying its
saved outcome. Both the API command and status route use the same replay helper:
it loads correction details through the invoice/location identity join and checks
actor, replacement version, original/expected batch and full request fingerprint.
A key belonging to another review/user is refused. A foreign-invoice key collision
returns the same generic 409 using an existence-only check; no foreign correction
details are loaded or returned and an already-used key is never reported retryable.
For an unseen
key, it checks original posting identity and current predecessor, then rebuilds
the review using the existing source/period/dependency rules. It never locks an
invoice for writing or cancels an earlier request.

| Outcome | Client behavior |
| --- | --- |
| `saved` | Confirm that this exact correction saved; clear only its retained request. No resend. |
| `saved_replaced` | Confirm that it saved and has a later correction; clear only this request and direct the user to current history. No resend. |
| `retry_available` | No saved correction was visible and the reviewed plan still matches. Enable one explicit retry of the unchanged body/key. |
| `other_request` | Another correction advanced the invoice. Block retry; retain until confirmed local discard or saved-outcome resolution. |
| `held` | Source, period, initial posting or review evidence changed. Block retry; retain until manager review and confirmed local discard or resolution. |
| Failed/malformed/foreign response | Retain, clear any previous retry permission, and offer another status check. |

A negative read is not proof that an earlier write cannot still commit. An
explicit retry invokes the correction command, which rechecks its
transactional guards and returns an already-saved outcome for an exact replay.

## Confirmed local discard

The review amendment adds **Discard retained correction** for `held`,
`other_request` and `retry_available` outcomes. Clicking it performs a fresh
read of the exact retained request before opening confirmation. The confirmation
shows the retained reason, received quantities/conversions, before/after food
amounts and separate tax/fees. Keeping the record sends no command and does not
retain retry permission from the discard check.

Confirming performs a second fresh status read, revalidates the exact journal
record and actor/location, then clears only that version/key. A saved or
saved-replaced result refuses discard and retains evidence for the separate
saved-status resolution action. Failed, malformed or foreign reads, changed
records and storage failure do not authorize discard or retry. A late response
after changing actor/location cannot consume the original journal.

Successful discard closes any selected invoice. The manager explicitly reopens
the current source and previews a new correction; the old body/key is not
silently reused. Discard deletes only this tab's recovery copy, not source files,
purchases or accounting history. It neither cancels an in-flight command nor
overrides source/period/dependency holds. There is no automatic discard or cascade.

The original command can still finish after the final negative read. Commands
based on the same stale predecessor/plan cannot both advance the chain: whichever
arrives second fails its preview/predecessor checks. Both arrival orders are
tested. A genuinely new preview after the winning commit may legitimately create
the next correction; discard is not permanent cancellation.

The client binds status to actor, document/version, initial batch, key,
predecessor and review hash. Status transport uses the existing 60-second read
deadline and abort signal; a late completion cannot enable retry. Mutation
transport keeps its existing behavior. A failed retry needs another status read.
Successful mutation acknowledgements additionally match key, actor, version,
initial batch, predecessor, plan hash, invoice identity and current correction
when reported current. Unconfirmed acknowledgements never clear the journal.

Actor/location changes ignore late responses and preserve the original journal
for that actor's return. Confirmed saves whose local cleanup fails remain
explicitly reported as saved with a cleanup hold, rather than enabling another
write. Reload after fixing storage access can repeat the status/cleanup check.

## Review-amendment validation

Local validation of the amended source passed on October 15, 2026:

- **756 frontend tests in 69 suites**, full native feature profile. The four
  focused recovery/import/journal/deadline suites also passed all 171 tests;
  those tests are included in the full result, not additional cases.
- **741 offline cases** (285 methods plus 456 subtests), no failures/errors/skips.
- **49 PostgreSQL tests plus two race subtests** (51 reported JUnit cases),
  covering the complete posted-correction and native-purchase modules. The six
  focused recovery methods plus the same two subtests also passed first; they
  are included in the full run. Full purchasing/count/store-state snapshots stay
  identical across refused replays and the losing stale-predecessor commands.
- The local PostgreSQL supervisor verified unchanged role/database inventories
  and stopped its owned loopback server. No hosted connection was used.
- Strict `CI=true` production build, ESLint enabled, fictional backend URL:
  `main.f14efe24.js`, SHA-256
  `790f077ad6986ed29bc5b999ff7e16768625bd1252ea9aa9a7949916846e585c`.
  Source-map contents match the final runtime modules after newline normalization.
- Review-contract generation, changed Python parsing, relative document links
  and `git diff --check` pass. No SQL, snapshot, migration or manifest changed.

New component coverage includes all three discardable outcomes, explicit cancel,
fresh saved/saved-replaced refusal before and after opening confirmation, read
failures/malformed/foreign responses, scope changes, replaced local evidence,
storage failure, cap messaging, and a genuinely fresh review with a new key.
Database cases enforce replay actor/version/body/batch ownership, refuse a key
from another invoice without returning its details, and exercise both command
arrival orders after local discard. The full database CI profile includes these
three new methods; its result must be checked on the amended pushed head.

Evidence outside Git:

| Artifact | SHA-256 |
| --- | --- |
| `pr34-amend-frontend-20261015T162721894541Z.json` | `ec9e3ad86f89d3e7711f8827e4c292e2bbbced87b63ab490cd4871b54d3d750a` |
| `pr34-amend-offline-20261015T162732191995Z.xml` | `85be083ee21a3419890e15acadd2d8a1e65c28095ee4338981b83a37aa0d776c` |
| `correction-recovery-tests-20261015T162924101897Z/receipt.json` | `5e1e59e4becbf2c6a4dc35fef06a43a3dea39779b728e951611a9a45f24d12ff` |
| `pr34-amend-validation-20261015.json` (source/evidence hashes and bundle binding) | `4feae495e0f00426e3e45d1b21ba2a2e24a5468abd0dad7f23a1e5a380d59394` |

All local tests passed on their first amendment run. Existing backend
dependency/lifespan and Node `fs.F_OK` deprecation notices remain. No live
transport or hosted acceptance is claimed; hosted testing stays on owner hold.

## Original-head validation and boundaries

The initial pushed head `4ad1a9b` passed these local checks:

- **741 frontend tests across 69 suites**, full native feature profile. The
  final JSON report has zero failed or pending tests.
- **741 offline cases** (285 methods and 456 subtests), with zero failures,
  errors or skips, through `tools/run_review_tests.py offline`.
- **46 backend cases**, running the complete posted-invoice correction and
  native-purchase modules, with zero failures, errors or skips. The three new
  status/recovery database cases also passed an earlier focused run; they are
  included in the 46, not added again.
- Strict `CI=true` production build with ESLint enabled and fictional backend
  URL passed. Final bundle: `main.6fcff632.js`, SHA-256
  `826f9183c660b5273bcceed9cacca3a4faa635c086aaafc120c409fc2e3089f6`.
  Its source map matches the final three changed client modules exactly after
  newline normalization.
- Generated migration/feature guides match source; `git diff --check` passes.
  No SQL/migration file changed.

The PostgreSQL supervisor used only the dedicated loopback PostgreSQL 17 cluster
outside synced Documents/Drive. Original database/role inventories match after
the run and the owned test server is stopped. Full purchasing/count/store-state
snapshots remain equal across status reads and exact retries. Existing closed
period, received-date, tax/fee, signed correction, rollback and source-history
regressions remain in the 46-case selection. This is not the complete 82-case
selected database CI profile. [Original-head CI](https://github.com/jeffwelch0620-png/JayMax-Concepts-/actions/runs/38766732588)
subsequently passed all four jobs. These results precede the review amendments.

The initial focused frontend attempt exposed a test-helper default-argument
mistake and a duplicate local request-key warning. The fixture was corrected;
the journal now rejects duplicate keys across invoices and tests that refusal.
Subsequent focused and final full frontend runs pass. Five existing backend
dependency/lifespan deprecation warnings and the Node `fs.F_OK` deprecation
notice remain; the strict build reported no compile/lint warning failure.

Local evidence is outside Git:

| Artifact | SHA-256 |
| --- | --- |
| `correction-recovery-frontend-final-20261015.json` | `6d624f14794484ac8704acf2f302aabf72924e46e1b596b94eb88f0f9bf4dd0c` |
| `correction-recovery-offline-20261015T1550.xml` | `5ff4a2c112a7d2bf09b3308d5497dda5f338b092477c3cf66083b09c6976a9fb` |
| `correction-recovery-tests-20261015T154943022123Z/receipt.json` | `40348d65898c466ee5c103f82567608265cb74cf6b055f61cc3906b108918f5b` |
| `correction-recovery-validation-20261015.json` (source hashes, counts and bundle binding) | `0ec77c59d500abb822cf7b3d2e3419637dba79024daf00da3e71c2e0370fa994` |

All fixtures are fictional. No hosted test or real invoice import is part of
this work. Deploy the compatible
backend before or with the frontend only after separate approval; an older API
without the status endpoint leaves recovery held rather than authorizing retry.

Scope limits:

- Recovery covers **submitted** corrections. An unsubmitted draft/preview is
  not persisted by this change.
- Same-tab reload and same-user sign-in use `sessionStorage`. Recovery after
  closing the tab, a browser restart or opening another tab is not guaranteed.
- Source-file/manual-capture command persistence and supplier outbox remain
  future slices. Confirmed discard covers validated submitted corrections only;
  corrupt/unavailable storage is held, not automatically purged.
- No live browser, Render transport, hosted pool or production acceptance is
  claimed. GitHub CI must pass on the amended draft head before merge approval.
- Track 1 remains purchased physical counts with explicit values plus received
  purchases; corrections retain reversal/replacement lineage. Taxes/fees stay
  separate. Prep and sales never deduct from or revalue this accounting track.

Implementation: `backend/purchase_corrections.py`,
`frontend/src/lib/pendingCorrections.js`, `frontend/src/lib/api.js`, and
`frontend/src/components/PurchaseImportsTab.js`. New tests cover journal boundaries,
read deadlines, component recovery and real disposable PostgreSQL correction
outcomes. The three new database cases are selected by `tools/run_review_tests.py`
for CI; three additional replay/scoping/discard-race cases join them in the
review amendment. Existing correction/native-purchase regression suites are also
run locally.
