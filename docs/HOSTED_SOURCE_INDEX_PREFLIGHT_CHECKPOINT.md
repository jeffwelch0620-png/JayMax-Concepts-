# Hosted source-index preflight and backup hold — October 14, 2026

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
