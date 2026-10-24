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
| null | At least one audit/metadata truncation flag or auditTotal is not durably observed. Unknown takes precedence even if another flag already reports truncation. |
| true | status is complete, auditTotal is an exact integer (not bool), and every audit/metadata key ending in Truncated is exactly false. This includes sessionGroupsTruncated. |
| false | All required visibility inputs are known, but execution is not complete, the total is invalid, or at least one relevant flag reports truncation. |

Operators must inspect **both status and coverageComplete**, then the individual
flags and private evidence. Neither field certifies S1/security acceptance,
actor attribution, complete middleware logging, permissions, writer drain or
installation readiness. A complete recorded-activity sample does not establish
that every security-relevant request was recorded or reviewed.

The review package's full-success fixture has 250 matching audit rows and a
200-row sample, so it correctly asserts false rather than the package's proposed
true. A separate 100-row fixture establishes true. The 70-row ledger fixture
also uses the 100-row baseline, leaving ledger truncation as the sole incomplete
visibility flag. Test profiles retain these distinctions.

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

The 128 KiB checkpoint and 512 KiB stream limits, 10-second connect, 12-second
client command, 10-second statement, one-second lock, <=120-second overall work
envelope and seven-second cleanup reserve are unchanged. No retry follows a
failure. Disk/OS stalls still require the separate supervisor boundary.

## Local validation

The final focused selection passed **63 tests + 141 subtests = 204 cases**, with
one existing multipart warning. The first command collected no tests because its
dependency path omitted backend/readonly_snapshot; restoring the established
module paths produced the passing rerun. No installation or dependency change
was needed. These receipts are retained outside Git.

PostgreSQL 17.11 passed **8 tests + 13 subtests = 21 cases**, including six real
database methods. The new real case opens three explicitly named fictional
clients, checks their groups/counts and newest session ordering, excludes the
observer, and establishes true coverage on 100 audit rows. The existing 250-row
case asserts false; the 70-ledger case isolates ledger truncation. Snapshot
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

## Remaining gates

Local validation is complete. Update JMax and prompt before publishing a draft.
Fresh follow-up CI, independent review and owner merge approval follow that
publication. No fresh S1 live attempt, service pause or credential/grant/schema
change is authorized. S1 PIN/personal-role/activity/actor acceptance, N2 PIN
storage, G04/G13/O1 and par installation remain open. Ordering stays manual;
par editing frozen; Track 1 independent; Inventory remains the stock writer.
