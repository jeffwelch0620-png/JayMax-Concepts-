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
  validated SQLSTATE, durations, cleanup outcomes and audit counts/coverage flags.
  `envelopeExpired` distinguishes total-envelope expiry from a command timeout
  or independent operator cancellation. SQL, exception messages,
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
- Audit coverage is checkpointed separately as `audit.summary`, `audit.breakdown`
  and `audit.records` within the same audit snapshot. The full-interval aggregate
  supplies total, first and last timestamps for recorded owner/manager activity.
  The row sample contains the earliest 100 and latest 100, ordered using timestamp
  and ID; the two samples can overlap when the total is below 200. They are not
  counts to add together or evidence that every event has been reviewed.
- Public receipts expose only `auditTotal`, `recordsTruncated` and
  `breakdownTruncated` for audit coverage. Each remains null (not evaluated) until
  its corresponding private checkpoint is durably completed. A saved aggregate
  can survive a later sample failure; that does not make the held attempt complete.
  The row sample reports truncation when the aggregate exceeds 200. The grouped
  breakdown uses a 501-row lookahead, keeps at most 500 groups and trims its
  checkpoint to 96 KiB, setting truncation for either limit. Individual record
  checkpoints that exceed the existing cap still hold the attempt.

## Query scope and unchanged safeguards

The fixed collector retains the existing 14-relation scope, 100 policy-metadata
row cap, PIN configured-booleans only for the same three stores, Toast IDs 3/4,
20 session-metadata rows and 64 ledger version/name identifiers. The PR61 review
amendment adds the full-interval audit aggregate and bounded UTC-day/role/user/
method/status-class breakdown, plus the two 100-row minimized samples, against
the same activity table, role filter and approved half-open interval. Full-interval
coverage comes from the aggregate, not the row sample. This covers recorded
owner/manager activity; it does not prove the audit middleware captures every
security-relevant request or resolve actor/consumer attribution. It does not select
PIN values, account password hashes, audit emails, cron commands or SQL text.
User IDs and paths remain private evidence only. Each checkpoint stays within
128 KiB and the cumulative stream within 512 KiB; output-budget failure holds
the attempt without publishing false complete coverage.

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

### PR61 A1 and N1 review amendment

The final focused selection passed **51 tests + 78 subtests = 129 reported cases**
with one existing warning. The broad offline profile passed **535 tests + 1,005
subtests = 1,540 cases**, zero failures/errors/skips and five existing warnings,
including the actual Windows ACL checks. These selections overlap. Source-contract,
local Markdown-link and whitespace checks passed separately.

New cases cover 250 recorded events retaining the newest sample, empty and
199/200/201 boundaries, 500/501 grouped rows, byte-budget truncation, real temporary
JSONL stream limits, partial audit failures, failed summary persistence, oversized
sample refusal and public-receipt redaction. Existing timeout/cancellation tests
now distinguish envelope expiry, command timeout and operator cancellation.

Two initial expanded selections used incomplete dependency paths (seven missing
asyncpg imports, then five missing cryptography imports in unchanged companion
tests); all new diagnostic tests passed in both. One subsequent command selected
a nonexistent runner filename and collected no tests. After selecting the
established local library paths and correct runner module, the focused and broad
profiles above passed. These earlier receipts are retained outside Git and are
not added to the final counts. No dependency, hosted request or database server
was installed or started for this amendment.

## Next gates

1. [Draft PR61](https://github.com/jeffwelch0620-png/JayMax-Concepts-/pull/61) was
   published at 2e8ab80 with all four checks passing in
   [the original-head CI run](https://github.com/jeffwelch0620-png/JayMax-Concepts-/actions/runs/40045888723).
   The owner authorized the local A1/N1 review amendments, testing and same-branch
   push. The original CI does not validate these amendments.
2. Amendment local validation is complete; same-branch push is owner-authorized.
   Obtain fresh exact-head CI and return for owner merge/automatic-test-deployment
   approval. Independent review and any fresh live attempt remain separate gates.
3. Prepare secure controlled-probe inputs, personal-role contexts and a source-
   pinned operator handoff before requesting another bounded S1 attempt. This
   local fix does not complete the PIN/role probes, audit review or API actor and
   consumer attribution. G04/G13 stay open.
4. Keep all hosted execution, service pauses and credential, account/PIN, grant,
   schema, connection/provider changes held. Ordering stays manual; par editing
   frozen; Track 1 independent. No credential retirement or par installation is
   approved by this diagnostic work.
5. N2 remains a separate PIN-storage security decision: review protected storage,
   key management, verification, manager controls and migration on a future owner
   PIN set, including whether resetting store PINs belongs in S2a. Existing PIN
   storage and all credentials are unchanged by PR61.
