# Hosted source-index preflight and backup rehearsal — October 14, 2026

## Writer inventory and maintenance planning checkpoint

The [maintenance plan](HOSTED_SOURCE_INDEX_MAINTENANCE_PLAN.md) records refreshed
read-only Render/database evidence, Companion's potential-writer status, exact
Toast jobs and GMT schedule, live-versus-local credential distinction, pooled
session and HTTP-drain holds, the 45-minute proposal and pending approvals.
The observed live API is PR30 at `6e08ba7`, with auto-deploy on, using `postgres`
on transaction-pooler port 6543; no deployed connection was changed. Adding that
actual role to the inventory reveals two idle pooled postgres sessions and causes
the existing guard to hold. The earlier two-role quiet result was insufficient
to establish the deployed backend was drained.

The verified rehearsal remains passing evidence, but a **fresh backup and restore
inside the approved window are mandatory**, not merely conditional on observed
drift: the adapter's reviewed evidence guard requires this chronology. No v2
execution plan is generated while stop/drain and window approvals are pending.
A separate private non-executable planning packet is saved with all execution
flags false. No services/jobs, hosted index, credentials, permissions or deployment
settings were changed. The local documentation branch remains unpublished.

## Fresh hosted export and disposable restore verified

The owner authorized a fresh encrypted backup and disposable restore. The single
attempt completed **October 14, 2026 at 7:08:48 p.m. EDT**, status
`verified_fresh_hosted_application_backup_and_disposable_restore`, using clean
source **7251683afea1ec149dea239bbb14ef258e2c3014** (PR30 runtime plus the preceding
documentation checkpoint). Runtime hashes were frozen and verified after the
rehearsal. No transport shims or mocked export/restore routines were used.

- The existing certificate-verified owner session-pooler connection supplied a
  read-only repeatable-read snapshot, fingerprints, dependency/role metadata and
  the actual `pg_dump` archive. Sequence state was rechecked and observed stable.
- Encryption, authenticated readback, archive listing, close and partial cleanup
  passed before publication of the final encrypted archive. The backup and its
  separately stored key remain in ACL-verified private local storage.
- Fresh export took **369.219 seconds**: fingerprint **181.000 s**, `pg_dump`
  **175.859 s**, overlapping snapshot aggregate **363.422 s**. All export phases
  passed; all eight requested setting observations were captured and
  `limitReadHeld` was false. Existing 20/60/240-second client deadlines and server
  settings were unchanged. No idle-limit or connectivity cause is inferred.
- Real `pg_restore` into a fresh UUID-named loopback database took **41.297 s**.
  **120 relation fingerprints, 13 catalog groups and 27,271 rows matched** the
  authenticated export manifest. Catalog comparisons include schema/relations,
  columns, constraints, functions, triggers, indexes, views, policies, types,
  sequence definitions and default ACLs. Source and local major versions match;
  source is **17.6**, local tools **17.11**, so patch-version equality is false.
- A second restore refused the populated destination before restoration. The
  restored account role's private-schema denial and inventory role's account-table
  denial passed. This checks those declared grants with local dependency stubs;
  source role memberships, passwords and login behavior were not restored.
- Seventeen new non-login/non-superuser local dependency stubs were prepared.
  Only these newly created stubs and the newly created test database were removed.
  Before/after role/database inventories match, cleanup reported no errors, and
  the owned PostgreSQL server is stopped. No existing local role was modified.
- Independent postflight reauthenticated the archive and verified encrypted,
  manifest and receipt hashes, file ACLs, runtime source hashes and absence of
  `archive.partial`/`backup.partial.enc`. The encrypted archive is **30,287,992
  bytes**, containing a **17,014,272-byte** dump; no business rows, key contents,
  credentials or private paths appear in public evidence.

Evidence SHA-256 values:

| Artifact | SHA-256 |
| --- | --- |
| Encrypted backup | `53a451e3c24a56ad971ddcc86e3e76a3d500b5fa9f40a44a08e77dccb2a9c59b` |
| Inner archive | `06f6e75deee5c461c6779f8d06c7afecfdcc970d4d67ec24c1fc6f1afdcdf235` |
| Application manifest | `1dfe84e02664ff9e5779336f4461d577d394ae9f1438503fdd9a63eba9f5c39c` |
| Protected rehearsal receipt | `63f9a61908ecabadec19cc98edeaa6ea6f99afbc51174e4f430d2633fe095e26` |
| Redacted public receipt | `92c9789329e9b2bb867599b010e6eb13dffa549a716017ff6099207ac4faa052` |

**Acceptance boundary:** the fresh application-scope backup/restore prerequisite
now has passing evidence. Managed Supabase recovery and combined credential
rotation recovery remain unqualified; no operational release or hosted apply is
approved. Two closed-period rows are included and fingerprint-matched, but no
runtime Food Cost report comparison was performed. Writer draining was not
demonstrated, and concurrent writers were not paused; this is a captured snapshot,
not proof that today's hosted database remains unchanged after it.

**Next:** refresh the writer inventory (actual Render backend and database role,
Toast scheduled jobs and any other sources), prepare a coordinated stop/resume
window with the observed rehearsal duration, and obtain exact plan approval. A
maintenance-time backup may need refreshing if intervening writes invalidate the
reviewed baseline. Apply only the single additive index and ledger entry after
those gates, followed by independent reconciliation and the fictional accounting
control. Hosted SQL/index, settings, services, credentials and scheduled jobs were
unchanged in this rehearsal. These notes remain local on
`codex/post-pr30-hosted-diagnostics`; no new PR is published by this step.

The earlier backup hold below is retained as historical evidence, superseded only
for the successful application-scope export/restore checks recorded above.

## PR30 merged and bounded metadata diagnostic

PR30 merged with owner approval on October 14 at 6:30:56 p.m. EDT:
**6e08ba7fca10d640ce311d0a9a10e75aa3838dfc**, amended head
**202691137bdb67376798bff1bdad3ff358ed11fd**. All four
[amended-head checks](https://github.com/jeffwelch0620-png/JayMax-Concepts-/actions/runs/38647473285)
and [merged-main checks](https://github.com/jeffwelch0620-png/JayMax-Concepts-/actions/runs/38648177850)
pass: 689 frontend tests across 67 suites plus production build, 700 offline cases
(267 methods plus 433 subtests), and 73 disposable PostgreSQL cases (62 methods
plus 11 subtests). Backend profiles have zero failures, errors or skips.

The next step ran one bounded read-only metadata diagnostic against the existing
designated owner session-pooler connection, pinned to the merged source. It used
the export's existing TLS, connection configuration, read-only repeatable-read
snapshot and fingerprint code; it stopped before dependencies, dump, encryption
or restore. The overall deadline was 180 seconds, with the unchanged 20-second
connect and 60-second client command limits. There was no automatic retry.

The diagnostic completed at **6:34:03 p.m. EDT** in **154.485 seconds**, status
`metadata_diagnostic_passed_not_backup_verified`. All phases passed:

| Phase | Seconds |
| --- | ---: |
| Connection and existing session configuration | 1.219 |
| PostgreSQL setting observations | 0.187 |
| Schema check | 0.203 |
| Fingerprint metadata and rows | 152.594 |
| Snapshot aggregate, overlapping the preceding subphases | 153.172 |
| Connection close | 0.078 |

Fingerprints captured **120 relations and 13 catalog groups**; no business rows,
SQL, credentials or private paths appear in public evidence. The fingerprint
SHA-256 is `2cbc5c682dd0a727889aa45e1549e226f0f57c6181fa551859057aa4941a5fef`.
The protected private receipt's SHA-256 is
`b0d0b5d66571757c7063b25074be054c38082ce815bebe9caf1ccc7f1c2a67d0`.

All eight settings were captured; `limitReadHeld` is false:

| PostgreSQL session setting | Observed value |
| --- | ---: |
| statement_timeout | 120000 ms |
| idle_in_transaction_session_timeout | 0 ms |
| idle_session_timeout | 0 ms |
| transaction_timeout | 0 ms |
| tcp_keepalives_idle | 1800 s |
| tcp_keepalives_interval | 60 s |
| tcp_keepalives_count | 9 |
| tcp_user_timeout | 0 ms |

These are observations, not changed settings. The statement/client limits apply
to individual commands, not the sum of all fingerprint commands. Pooler limits
remain outside `pg_settings`. The prior connection loss was not reproduced in
this attempt; its cause remains unproved. Successful metadata inspection is not
an encrypted backup, restore verification, or a writer-drain demonstration.

**Next:** fresh encrypted export and disposable restore using the existing
reviewed helpers, then independent acceptance of those receipts. Writer inventory
(including both active Toast jobs), a coordinated window, exact plan approval and
the single additive index installation still follow. No hosted migration/index,
credentials/privileges, permanent settings, service pauses or scheduled-job changes
were performed. This checkpoint update is local on
`codex/post-pr30-hosted-diagnostics`; no new PR is published by this step.

## PR30 review amendments

The independent review confirms the backup publication and plan guards. Its CI
observation predates the completed [four green checks at a6229a2](https://github.com/jeffwelch0620-png/JayMax-Concepts-/actions/runs/38645650942):
689 frontend tests, 695 offline cases and a fresh full 73-case disposable database
profile. The initial local parser failure remains in the history below.

- Unexpected diagnostic setting values/units are omitted from `serverLimits`,
  listed in `serverLimitsNotCaptured`, and marked by `limitReadHeld: true`.
  This metadata problem does not abort export. Actual query/connection failures,
  snapshot failures, verification failures and cleanup failures still hold it.
- `pg_settings` observes the PostgreSQL server session only. The session pooler's
  own client/idle limits are not captured. Clean server readings cannot rule out
  a pooler timeout; phase and elapsed-time observations suggest hypotheses, not
  a proved cause. No limits, keepalives or connection settings are changed.
- Held CLI receipts include boolean-only `backupArtifacts` flags for retained
  `backup.key`, `backup.partial.enc`, `archive.partial`, and a final backup's
  presence. Failed inspection is flagged separately, never inferred as absence.
  Paths and key contents are excluded. Keys remain private, including when a
  candidate survives cleanup/publication failure; no automatic deletion of
  recovery material is introduced. A retained key or partial is not an accepted
  backup. The original failure remains primary if artifact inspection fails.

Amendment validation passes **700 offline cases** (267 methods plus 433
subtests), zero failures/errors/skips. Tests cover unexpected values/units,
continued authenticated export with valid settings retained, a real query-error
category still holding export, and failed artifact inspection preserving the
original error. A focused first run exposed an overly broad test assertion that
rejected the safe field name `privateKeyRetained`; the assertion now checks actual
sensitive values and paths. The final offline XML is retained separately.
The amended head requires fresh CI before the owner-authorized merge.
Hosted backup/restore and index application remain held pending their own evidence.

## PR29 merge and backup-artifact/diagnostic follow-up

PR29 merged with owner approval at **6f27edcfeb80c92d18eda09798cc9a9c295791ab**
(reviewed head **50485a5**). All four
[merged-main CI checks pass](https://github.com/jeffwelch0620-png/JayMax-Concepts-/actions/runs/38640974919).
The next local branch is `codex/backup-artifact-diagnostics`.

- **N1:** encrypted readback, archive listing, connection close and partial-file
  cleanup complete before `backup.partial.enc` is promoted to `backup.jmax.enc`.
  A close-only failure removes the candidate; other cleanup/publication failures
  may retain a protected partial artifact, but no accepted final name or success
  receipt is produced. The key remains private; no automatic recovery/retry is added.
- **N2:** additive plans have a fixed top-level field allowlist. Held receipt/error
  fields and unknown keys are rejected; optional execution flags must be explicitly
  false. Original source/history checks remain. Hashing a held local dry-run
  receipt cannot make it executable.
- **CLI gap:** standalone held backup output uses the shared original error,
  validated SQLSTATE and cleanup categories, plus allowlisted diagnostics.
  Driver text, SQL, URLs, credentials and arbitrary attached metadata are excluded.
- **N3 preparation:** export records named phases, effective server limits after
  existing connection configuration, and the existing 20-second connection,
  60-second command and 240-second subprocess deadlines. No timeout, keepalive,
  role, endpoint or hosting setting is changed. Unsupported/not-captured settings
  are listed explicitly. Signed values such as the Windows socket getter's
  observed `-1` are retained without interpreting them as usable durations.
  `snapshot_total` overlaps its subphases; do not sum all
  durations to estimate a window. Diagnostics identify a failed phase and preserve
  the original error, including failed rollback/close.

Local validation passes **695 offline cases** (264 methods plus 431 subtests),
with zero failures, errors or skips and the existing five dependency warnings.
Two targeted database cases passed on the first run: durable read-only planning/
application with the unchanged fictional $55 Food Cost control, and CLI plan-hash/
retained-receipt behavior. The new export/restore case initially failed because
the diagnostic parser rejected a legitimate signed observation (`-1`) from the
Windows socket getters. That parser was corrected and the export case passes in
a targeted rerun. Thus **3 distinct targeted database cases have passing evidence
across two runs**; a fresh full 73-case database-profile result and candidate CI
have not yet been produced. The initial failure XML is retained. Source hashes
match the rerun, the local role/database inventory is unchanged, and the owned
PostgreSQL 17 server is stopped.

The new fixture uses real dump/restore tools with two labelled fictional rows on
disposable loopback databases; its test-only transport shim does not qualify the
hosted pooler or its TLS path. It verifies authenticated export, matching isolated
restore, unchanged source rows and absence of a final-named backup after a close
failure. No runtime plan-validator code changed after its passing database tests.
The follow-up is prepared for independent draft review.
The previous hosted connection-loss/backup hold remains in force. Finish
independent review before another bounded hosted diagnostic; only then determine
the actual failure phase and whether a controlled connection experiment is useful.
No operational invoices were imported, hosted index was applied, or active
configuration, privileges, credentials or scheduled jobs were changed here.

The prior checkpoints below are retained as historical evidence.

## PR28 merge and receipt/cleanup follow-up

PR28 merged with owner approval at **c5cce2b858b59bad284db93725ef12ab7db0885b**
(reviewed head **84e96a9**). All four
[merged-main CI checks pass](https://github.com/jeffwelch0620-png/JayMax-Concepts-/actions/runs/38630008470).
The next local branch is `codex/readonly-receipt-cleanup-integrity`.

The follow-up extends error-preserving read-only snapshots to native backup
fingerprints, original-column preservation, deployment inspection, additive
planning/reconciliation, and the hosted adapter. The short activity probe keeps
its original default isolation. Existing write transactions, SQL bodies,
snapshot boundaries and lock acquisition order remain unchanged.

Held receipts record the original error class, a validated five-character
SQLSTATE and the snapshot cleanup category. Unlock, connection-close and partial
file cleanup categories are recorded when present. Driver messages, SQL text,
credentials and exception representations are excluded. Cleanup-only failures
hold the result; existing known/unknown commit outcomes are retained. Both
reconcilers protect the original failure from a subsequent unlock failure.

Local validation: **663 offline cases** (253 methods plus 410 subtests) pass,
with zero failures, errors or skips. The canonical database selection completed
with **71 passing cases** (60 methods plus 11 subtests) and one new fixture
failure: the savepoint test used a read-committed outer transaction with a
repeatable-read nested snapshot. Its fixture now uses matching repeatable-read
isolation and separately verifies that mismatched isolation is refused. That
one corrected case passes in a targeted PostgreSQL rerun. Thus **72 distinct
database cases have passing evidence across the two runs**; no fresh all-green
full database-profile XML or candidate CI is claimed. The initial failure XML is
retained. No runtime code changed after the full database run; only that test
fixture and documentation changed. The rerun's source hashes are verified, its
role/database inventory is unchanged, and the owned PostgreSQL 17 server is
stopped. The existing five dependency deprecation warnings remain.

This follow-up is ready for independent draft review. No new hosted connections, migrations, index
application, privilege changes, role/password changes, timeout changes or TCP
keepalive changes were made in this follow-up. The hosted backup/restore hold
below still applies; a merge is not backup acceptance.

After independent review, begin diagnosis with elapsed phase/subphase timings
and effective server **and client** limits on the same connections that perform
the inspection/export. Include `transaction_timeout`,
`idle_in_transaction_session_timeout`, `statement_timeout`,
`idle_session_timeout`, TCP keepalive values, and client command/operation
deadlines. Record only safe categories and durations. The captured failure was
during metadata inspection, before the dump subprocess; dump-idle termination
is a hypothesis, not the demonstrated cause. Table fingerprints already use
separate statements under the same snapshot. Keepalive changes would be a
separate controlled experiment, not the initial read-only observation, and must
account for the client-to-pooler and pooler-to-database connection segments.

The prior PR27/preflight checkpoint follows as historical evidence.

PR27 merged with owner approval at **a39e46fd77b6799b4f12e3482a4ac14add9eb0d1**
(approved head **168c02e**). All four
[merged-main CI checks pass](https://github.com/jeffwelch0620-png/JayMax-Concepts-/actions/runs/38606086807).
The next local branch is `codex/hosted-source-index-maintenance-preflight`.
No index installation, hosting change or database privilege change occurred.

## Read-only preflight

The existing certificate-verified owner session-pooler connection works for
bounded inspection. PostgreSQL reports **17.6**; local dump/restore binaries are
**17.11**, the same major version. The actor/database match the designated build
target, and complete activity-inspection authority is available.

All **29 original native delivery mappings** and **25 historical migration rows**
still verify against their retained source/body hashes. The live ledger contains
**54 rows**, its uniqueness/access contract passes, and the source-lookup index
is absent. Ordinary `anon`/`authenticated` ledger access remains denied. The two
recorded backend LOGIN roles exist and had zero sessions in that observation.
This does not establish that every possible writer is stopped.

Minimal owner configuration and the original installation receipt were prepared
under protected `%LOCALAPPDATA%\JayMaxBuild` storage. Active app configuration,
passwords, endpoints, service plans and permanent role attributes were not changed.

Two active scheduled jobs must be included in the writer inventory:

| Job ID | Recorded name | Cron expression |
| --- | --- | --- |
| 3 | jmax-toast-berts-rudds-daily | `15 10 * * *` |
| 4 | jmax-toast-papa-daily | `20 10 * * *` |

Expressions are recorded as configured; their execution timezone has not been
verified. Their commands reference network/Vault services. Commands, tokens and
endpoint details remain private; no job or Edge Function was invoked. Inspect
their target ingestion behavior and coordinate any temporary pause before the
maintenance window. Existing Toast payloads are present; a build database must
not be treated as empty merely because it has no operational inventory usage.

## Backup rehearsal remains held

Fresh read-only export attempts did not produce a usable, restore-verified
archive. A separate bounded diagnostic captured the original
`ConnectionDoesNotExistError` (SQLSTATE `08003`) during an extended metadata read.
Transaction exit then replaced it with `InterfaceError` because rollback used a
closed connection. A temporary system-awake lease did not prevent a subsequent
disconnect and was restored on exit. The underlying connection-loss cause is
not proved; database/pooler timeout settings were inspected without changing them.

The isolated local restore was not reached. Do not claim backup/recovery
acceptance, create an approved installation plan, or apply the index from these
held receipts. All failure receipts remain in protected local storage. No real
vendor invoice files were imported, and no hosted business rows were written.

## Local follow-up

A small shared `readonly_snapshot` context preserves the original inspection
failure when rollback also fails, retaining only the cleanup exception type.
Successful snapshots still commit their read-only transaction; failed starts,
failed commits and cancellation remain failures. Hosted metadata inspection,
backup export and restore-fingerprint reads use this context. No timeout is
increased and no automatic hosted retry or SQL application is added.

The current offline selection passes **637 reported cases**: **242 methods plus
395 subtests**, with zero failures, errors or skips. New tests exercise original
connection loss, failed rollback, cancellation, failed begin/commit, and the
actual metadata-reader/exporter entry points. The existing five dependency
deprecation warnings are retained. This is local error-handling evidence, not a
successful hosted export or local database restore. Counts overlap earlier
checkpoints and are not summed. This follow-up is prepared for independent draft
review; candidate CI is separate from the merged-main result above.

## Next approval and execution sequence

1. Independently review/publish this local error-preservation follow-up before
   adopting it for hosted operations. Keep the current connection/hosting standard.
2. Establish a stable, bounded source snapshot and finish a fresh encrypted export
   plus disposable local restore. Measure export and restore separately; no
   successful duration or maintenance-window estimate is claimed yet.
3. Confirm the actual Render backend service and all other writers, including
   the two Toast jobs, direct submissions and any other app instances. Render's
   [maintenance mode](https://render.com/docs/maintenance-mode) blocks public
   traffic while leaving the process running, so it alone does not stop background
   writers. Its [suspend API](https://api-docs.render.com/reference/suspend-service-1)
   is a separate service-stop mechanism; no control was changed in this work.
4. Separately approve a 10–60 minute maintenance window and the exact temporary
   writer-stop/resume actions. Capture a new backup and matching restore inside
   that window, then generate/hash the v2 hosted dry-run plan.
5. Obtain owner approval of that exact plan hash before applying the one index
   and ledger row. Independently reconcile, verify the current-source read and
   closed fictional $212 Food Cost control, then resume writers and record results.

See [the hosted adapter runbook](HOSTED_ADDITIVE_INDEX_RUNBOOK.md). Merge approval
does not substitute for the exact hosted plan/maintenance approval. Never replay
the 30-file fresh installer or loosen preservation gates to obtain a pass.
