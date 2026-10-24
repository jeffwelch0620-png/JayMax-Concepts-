# S1 visibility, session aggregation and ledger validation

## Accepted baseline and scope

The owner approved merging [PR63](https://github.com/jeffwelch0620-png/JayMax-Concepts-/pull/63)
and its existing automatic Render test deployment. It merged as
**0cba049b271005b434df02feac2f0e9453fe67db**, tree-identical to reviewed
423bded2bdc07786d218cff37b3c1eb55f0a4e59. All four
[reviewed-head checks](https://github.com/jeffwelch0620-png/JayMax-Concepts-/actions/runs/40053598106)
passed. The separate
[merged-main run](https://github.com/jeffwelch0620-png/JayMax-Concepts-/actions/runs/40054929392)
passed all four checks independently. This source checkpoint does not claim
Render runtime acceptance.

The owner authorized L1/L2/L3 and local testing, with a prompt before the next
draft push. This changes only the opt-in [collector](../tools/ops/s1_observation.py),
tests, database CI selection and documentation. The application does not import
it. No hosted connection, service control, credential/PIN, grant, production
schema, dependency, hosting or application connection change is included.
Fictional fixture DDL stays inside fresh disposable loopback databases.

## L1: nullable visibility summary

The public receipt adds `coverageComplete`, a boolean or null:

| Value | Meaning |
| --- | --- |
| null | A required aggregate-coverage flag or auditTotal is not durably observed. Unknown takes precedence even if another coverage flag reports truncation. |
| true | status is complete, auditTotal is an exact integer (not bool), and breakdownTruncated, sessionGroupsTruncated, ledgerTruncated and policiesTruncated are each exactly false. |
| false | All required aggregate inputs are known, but execution is not complete, the total is invalid, or at least one coverage flag reports truncation. |

C1 corrects the initial PR63 L1 specification. Coverage flags are explicitly
`breakdownTruncated`, `sessionGroupsTruncated`, `ledgerTruncated` and
`policiesTruncated`. Sample flags `recordsTruncated` and `sessionsTruncated`
remain in the public receipt unchanged and are informational: intentionally
bounded samples do not make complete aggregates incomplete. Sample flags alone,
including an unknown sample flag, do not determine aggregate completeness.
Failed execution still reports false when aggregates are known; missing or
unpersisted aggregates report null. Session total stays in the private durable
session checkpoint alongside its group-coverage flag.

Ledger truncation remains consequential because count/max do not represent all
migration version/name entries. The retained ledger sample therefore cannot
claim complete ledger visibility when more than 64 entries exist.

Operators must inspect **both status and coverageComplete**, then the individual
coverage and sample flags and private evidence. coverageComplete concerns
aggregate visibility, not sample completeness or review of every activity row.
Neither field certifies S1/security acceptance,
actor attribution, complete middleware logging, permissions, writer drain or
installation readiness. A complete recorded-activity sample does not establish
that every security-relevant request was recorded or reviewed.

The 250-row audit fixture now asserts true aggregate coverage alongside
recordsTruncated true. The 100-row fixture retains a smaller control. The 70-row
ledger fixture uses that control and still reports false aggregate coverage;
51 session groups also report false even though the complete session total is
retained. More than 20 sessions with complete groups may report true while the
session sample flag remains true.

## L2: one session observation, bounded private output

`metadata.sessions` now returns:

```text
{rows: [...], truncated: boolean, groups: [...], total: integer,
 groupsTruncated: boolean}
```

One SQL statement materializes the minimized pg_stat_activity observation for
the current database, excluding the observer's own backend. Its full total,
newest-first sample and aggregate groups all derive from that observed set.
The sample keeps at most 20 rows, ordered by backend_start descending (nulls
last), then PID descending, with a 21st-row lookahead. Groups use only usename,
application_name, state and count; they retain at most 50 deterministic groups
with a 51st-group lookahead. Total is the complete observed count, never the sum
of a potentially truncated group list.

The private sample retains only role, application name, state, start time and
session reference. No client address, query text or cron command is selected.
Names, PIDs and group counts remain out of the public receipt. Public
`sessionsTruncated` and `sessionGroupsTruncated` remain null until the whole
session checkpoint is durably written; validation, serialization or sink failure
cannot publish either as complete. Group truncation participates in L1.

Session state can change after observation. A materialized observation avoids
cross-query disagreement; it does not prove all writers are identified, paused
or drained, and is not permission to terminate sessions.

## L3: consistent ledger aggregate

Ledger total must remain an exact nonnegative integer. The max_version key is
required: a positive total requires a string; a zero total requires null. A
missing key, positive total with null, zero with a string, bool/negative total or
nonstrings are refused before persistence. Existing newest-64 sample, one-row
lookahead and same-statement full total/maximum remain unchanged.

## Version and operator handoff

The changed session object and public coverage fields use explicit
**jaymax-s1-checkpoint-v3** and **jaymax-s1-diagnostics-v3** contracts. PR63's
[v2 record](S1_TIMEOUT_METADATA_FOLLOWUP_20261023.md) remains dated history;
existing files are not rewritten. Current composition is described in the
[diagnostic runbook](S1_LOCAL_DIAGNOSTICS_20261023.md). A fresh source-bound handoff
must adopt v3 explicitly, verify private sinks/readers and bind exact source,
target/TLS, identity, approval, deadline, resource gate and cleanup before any
future live request. A closed approval or old v2 packet cannot be reused.
C1 keeps v3 as a pre-live semantics correction. No executable v3 live packet
has been issued in this workflow; the published draft/reference is not one.
Future executable packets must bind the amended source and final semantics.

The 128 KiB checkpoint and 512 KiB stream limits, 10-second connect, 12-second
client command, 10-second statement, one-second lock, <=120-second overall work
envelope and seven-second cleanup reserve are unchanged. No retry follows a
failure. Disk/OS stalls still require the separate supervisor boundary.

## Initial PR64 validation at 3dc1943 (before C1)

The final focused selection passed **63 tests + 141 subtests = 204 cases**, with
one existing multipart warning. The first command collected no tests because its
dependency path omitted backend/readonly_snapshot; restoring the established
module paths produced the passing rerun. No installation or dependency change
was needed. These receipts are retained outside Git.

PostgreSQL 17.11 passed **8 tests + 13 subtests = 21 cases**, including six real
database methods. The new real case opens three explicitly named fictional
clients, checks their groups/counts and newest session ordering, excludes the
observer, and establishes true coverage on 100 audit rows. Under the original
all-truncation-flags definition, the 250-row case asserted false; C1 supersedes
that expectation above. The 70-ledger case isolates ledger truncation. Snapshot
equality and public redaction/byte caps passed. Loaded start memory was
1,418.66 MiB / 23.53%, above the unchanged 1 GiB / 15% requirement. Temporary
databases were removed; role/database inventories matched; the owned server was
verified stopped.

The broad offline selection passed **547 tests + 1,068 subtests = 1,615 cases**,
with zero failures, errors or skips and five existing deprecation warnings. It
includes the actual Windows ACL checks. Profiles overlap and must not be summed.
Source/link and whitespace checks validate the current documentation, database
runner selection and unchanged application/migration/hosting files. No frontend
change was made; the accepted baseline's CI validates its frontend/build.

## C1 amendment validation

The focused selection passed **64 tests + 145 subtests = 209 cases**, with one
existing multipart warning. It verifies sample limits remain visible without
holding aggregate coverage, all four explicit coverage flags still hold or
remain unknown correctly, exact integer/status checks remain, and an oversized
or failed audit-record checkpoint cannot turn a failed run into success.
Updated session boundary cases cover >20 rows with complete groups and 51 capped
groups. The real 250-row case expects true aggregate coverage and a truncated
record sample; the ledger case remains false.

The disposable PostgreSQL 17.11 amendment rerun passed **8 tests + 13 subtests =
21 cases**, including all six real collector methods, with no failures/errors/
skips. Loaded start memory was 1,462.93 MiB / 24.26%. Fixture snapshots matched,
temporary databases were removed, role/database inventories matched and the
owned local server was verified stopped. No hosted connection or credential,
grant or production schema change occurred.

The broad offline amendment run passed **548 tests + 1,072 subtests = 1,620
cases**, including the actual Windows ACL checks, with zero failures/errors/
skips and five existing deprecation warnings. Source/link and whitespace checks
passed; 78 local Markdown links resolve and application, migration, frontend,
hosting and connection source remain unchanged. These profiles overlap.

## Remaining gates

PR64 is draft and unmerged. The owner authorized the C1 amendment, local tests,
documentation/JMax updates and pushing to its existing branch. Fresh amended-head
CI and owner merge/automatic-test-deployment approval remain separate.
No fresh S1 live attempt, service pause or credential/grant/schema
change is authorized. S1 PIN/personal-role/activity/actor acceptance, N2 PIN
storage, G04/G13/O1 and par installation remain open. Ordering stays manual;
par editing frozen; Track 1 independent; Inventory remains the stock writer.
