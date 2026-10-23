# Local S1 observation diagnostics — October 23, 2026

## Problem and scope

The approved revision-2 S1 attempt is closed with partial results. A metadata
TimeoutError followed the session-metadata checkpoint; the receipt cannot tell
whether the next ledger read or transaction exit failed. Detailed observations
were held in memory until whole-run success, so the failure artifact retained
counts but not the complete minimized prefix. Do not retrospectively label that
hosted failure a ledger timeout or infer its cause from a fictional reproduction.

This local follow-up provides a reviewed replacement for that one-off collector:
[s1_observation.py](../tools/ops/s1_observation.py). It is not imported by the app,
has no CLI, transport, credentials, dotenv/configuration lookup or import-time
I/O. No hosted request, database server, credential/grant/schema change or service
control was used in this work. The original dated operator execution and receipts
remain unchanged outside Git. Future handoffs must call the new collector rather
than silently rerunning or modifying that closed attempt.

## Behavior

- Every connect, transaction begin/settings/read/commit/rollback, owned close,
  termination and closure confirmation has a fixed operation label and duration.
  A ledger-read failure is distinct from a commit, rollback or close failure.
- Each completed minimized observation is flushed and fsynced to a previously
  prepared private JSONL stream before the next read. A later failure preserves
  its completed prefix. A partial final line is not a completed checkpoint.
  Per-checkpoint and total output caps are 128 KiB and 512 KiB.
  A failed stream cannot be reused after a short write/flush/fsync failure, and
  an asynchronous or uncompleted sink cannot claim a durable checkpoint.
- Public diagnostics contain only fixed labels, statuses, safe error categories,
  validated SQLSTATE, durations and cleanup outcomes. SQL, exception messages,
  connection strings, actor/employee/session rows and private observations never
  enter that receipt. Unknown exception type names become OtherError.
- The primary observation exception survives rollback/close/terminate failures;
  secondary failures remain visible in their own operations. Cleanup-only failure
  holds the run too. Saturating the 64-event diagnostic budget cannot suppress
  actual owned connection cleanup. No retry or next phase follows a failure.
- Existing read-only snapshot behavior is retained: successful exit commits a
  read-only transaction; exceptional exit attempts rollback. Receipts name the
  actual action instead of falsely marking a successful read-only commit as a
  confirmed rollback. No write transaction or business commit is introduced.

## Unchanged boundaries

The fixed collector retains the existing 14-relation scope, 100 policy-metadata
row cap, PIN configured-booleans only for the same three stores, Toast IDs 3/4,
20 session-metadata rows, 64 ledger version/name identifiers and 200 minimized
manager/owner activity records ordered by created_at and id. It does not select
PIN values, account password hashes, audit emails, cron commands or SQL text.

There are at most two sequential injected connections. Connect and command
timeouts remain 10 seconds, server statement timeout 10 seconds, lock timeout
one second, rollback timeout three seconds and owned-close timeout four seconds.
The work timer reserves seven seconds for the existing three-second rollback
and four-second owned close inside the 120-second/caller-remaining envelope.
An available envelope of seven seconds or less refuses before connecting.
No second connection or replay occurs after failure.

The helper is **not an approval or credential boundary**. A fresh operator
handoff must independently bind the exact packet and source bytes, target,
verified maintenance TLS/transport, user approval, memory gate, wall deadline,
exclusive claim and private evidence ACLs before supplying its connector and
already-open evidence stream. It must preserve protected inputs and write a safe
final receipt even when collect raises. Existing maintenance.connect remains
responsible for its transport checks and for closing a connection that fails
before it can be returned to the collector.

Synchronous checkpoint writes use the existing local filesystem; this unit-tested
helper is not evidence of hard wall-clock recovery from an OS/disk stall. The
future handoff still needs resource, deadline and supervisor/cleanup review.
The sink must be prepared before any connection is opened; no repeated private
ACL subprocess is needed between query checkpoints.

Example composition, deliberately omitting executable credential/approval setup:

```python
diagnostics = Diagnostics(JsonlCheckpoints(already_prepared_private_stream))
# approved_connect delegates to existing verified maintenance.connect with the
# bound project and readonly=True; it never substitutes the app connection.
try:
    await collect(approved_connect, diagnostics,
                  audit_from=approved_audit_start, as_of=approved_attempt_start,
                  remaining_seconds=remaining_check_budget)
finally:
    # Persist diagnostics.receipt() using a prepared receipt sink. Preserve a
    # prior observation error if final receipt publication also fails.
    # A held diagnostic result does not authorize retry or another live window.
    ...
```

## Local validation

The new module is selected by the existing Windows offline CI profile. Tests use
fictional in-process connectors/transactions and temporary files only, including
the actual fixed query plan, JSONL prefix readback, fsync/short-write failures,
primary-plus-cleanup failures, missing closure, real asyncio cancellation,
exact limits, secret redaction and refusal to reuse a diagnostic attempt.

The pre-strengthening focused run passed **42 tests + 63 subtests = 105 reported cases**,
including existing read-only snapshot and runner checks. One existing multipart
deprecation warning remains. The first new-module run passed 23/24 tests plus
40 subtests; its one failure was a misplaced closure assertion in the invalid-
input fixture. Moving that assertion to the second-phase failure fixture produced
a passing 24-test/40-subtest rerun before strengthening the cleanup-budget tests.
These profiles overlap and must not be added together.

The first broad offline profile passed **526 tests + 990 subtests = 1,516 cases**,
including both existing Windows ACL checks, with five existing warnings. Review
then tightened the cleanup reserve and checkpoint-sink validation; a final full
offline rerun passed **529 tests + 993 subtests = 1,522 cases**, with zero failures,
errors or skips and the same five existing warnings. These totals overlap.
The final run includes the strengthened module and real Windows ACL checks.
No frontend
or database-server test is needed for this operator-only diagnostic change;
application code, dependencies, migrations and hosting configuration are unchanged.

## Next gates

1. Local code review and final broad offline checks are complete. Repository
   and JMax documentation record this local-only checkpoint; no PR is published.
2. Prompt the owner before publishing a draft PR. Fresh CI, independent review,
   merge and any automatic test deployment remain separate approval steps.
3. Prepare secure controlled-probe inputs, personal-role contexts and a source-
   pinned operator handoff before requesting another bounded S1 attempt. This
   local fix does not complete the PIN/role probes, audit review or API actor and
   consumer attribution. G04/G13 stay open.
4. Keep all hosted execution, service pauses and credential, account/PIN, grant,
   schema, connection/provider changes held. Ordering stays manual; par editing
   frozen; Track 1 independent. No credential retirement or par installation is
   approved by this diagnostic work.
