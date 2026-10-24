# S1 timeout and metadata coverage follow-up

## Scope and accepted baseline

PR62 is accepted as a009e8a, tree-identical to reviewed d306b8e. Its separate
[reviewed-head CI](https://github.com/jeffwelch0620-png/JayMax-Concepts-/actions/runs/40050416906)
and [merged-main CI](https://github.com/jeffwelch0620-png/JayMax-Concepts-/actions/runs/40051971964)
passed all four checks. The owner authorized F1, F2 and M1 plus local validation,
with a prompt before draft publication. This changes the opt-in operator
[collector](../tools/ops/s1_observation.py), its tests/CI selection and documentation.
It is not imported by the application and supplies no CLI or default transport.
No hosted attempt, service control, operational import, credential/PIN change,
production grant/schema installation, migration, snapshot, dependency, frontend
or connection-setting change is included. Fixture DDL is local and disposable.

## F1 timeout ordering and attribution

Connection establishment remains bounded at 10 seconds. Server statement and
lock limits remain 10 seconds and one second (SET LOCAL 10000ms/1000ms). The
client command limit is **12 seconds**, giving the server's cancellation reply a
margin before the client deadline. These are source constants, not environment
options or operator approval.

The overall work/caller limit remains <=120 seconds. Its work timer expires at
min(work_seconds, remaining_seconds) minus seven seconds, reserving the existing
three-second rollback and four-second owned close. An envelope of seven seconds
or less refuses before connecting; there are at most two sequential connections,
no retry, and no next phase after failure. Independent per-command maxima do not
guarantee that the complete plan fits: metadata has seven reads plus begin/settings/
commit, so its conservative sequential successful ceiling is 10 + 10*12 + 4 =
134 seconds; audit's four reads give 10 + 7*12 + 4 = 98 seconds. The overall
envelope holds earlier rather than extending to their sum. Synchronous disk/OS
stalls still require the separately reviewed handoff/supervisor boundary.

Interpret the receipt with operation, SQLSTATE and envelopeExpired together:

- A controlled server statement-limit cancellation is QueryCanceledError/57014.
  In general 57014 means query_canceled; it is not unique proof of statement_timeout.
- 55P03 is lock_not_available; interpret it with the controlled lock/query context.
- A command-level client TimeoutError without SQLSTATE means its client budget
  expired; it does not by itself establish transport, pooler or server root cause.
- envelopeExpired marks the total envelope; independent operator cancellation
  stays distinguishable. Cleanup preserves the primary error.

These categories follow the [PostgreSQL error-code reference](https://www.postgresql.org/docs/17/errcodes-appendix.html).
The original hosted timeout's exact location/cause remains unconfirmed.

The disposable test uses a test-only pg_sleep reader, a 150ms server limit and
three-second client limit. It must receive actual 57014 at metadata.ledger with
envelopeExpired=false, rollback/close the owned client and skip audit. The offline
no-reply test uses the injected client's shorter test budget and requires
TimeoutError/no SQLSTATE with the same failure label, without envelope expiry.
Production metadata/audit object scope and read queries are not replaced by sleep.

## F2 bounded metadata and contract v2

The private JSONL envelope is jaymax-s1-checkpoint-v2; the public receipt is
jaymax-s1-diagnostics-v2. This identifies the changed private metadata shapes.
All in-repository consumers are tests/documentation and are updated together.
Dated one-off drivers, approvals and receipts outside Git remain unchanged.
A new live handoff must bind these source bytes, enforce v2 and adopt the new
command budget rather than reuse a closed packet.

| Checkpoint | Private shape | Lookahead and retained rows |
| --- | --- | --- |
| metadata.policies | rows, truncated | Fetch 101; retain at most 100 |
| metadata.sessions | rows, truncated | Fetch 21; retain at most 20 |
| metadata.ledger | rows, truncated, total, max_version | Fetch 65; retain newest 64 by version text descending |

The ledger uses window count/max over the full ledger before LIMIT, within the
same read-only snapshot as the row sample. Empty ledgers report total=0 and
max_version=null. Identifiers and aggregates remain private. Public coverage adds
only ledgerTruncated, sessionsTruncated and policiesTruncated: each is null until
its validated checkpoint is durably saved, then a boolean. A failed/oversized
checkpoint cannot publish false completeness. The existing 128 KiB/checkpoint
and 512 KiB/stream caps remain enforced; there is no silent byte trimming here.

status=complete means the requested operations completed, not full inventory or
permission/writer coverage. A truncated or unevaluated metadata checkpoint cannot
support a complete-coverage claim in the future handoff. The package's dated
55/56-row ledger counts are not fresh hosted facts; the regression uses 70
fictional rows, requires total=70/max_version=TEST_ONLY_070, and retains 070..007.

## M1 fictional PIN fixture

The disposable staff_pins stub now makes store_id and pin text NOT NULL, matching
the snapshot's column nullability. The disabled example is TEST_ONLY_X, not NULL.
The real test checks column nullability and configured=false. This changes no
existing store PIN or production schema. N2 storage/key-management/verification/
manager-controls/migration and any S2a reset remain separate security decisions.

## Local validation and next gates

Focused offline checks passed 59 tests plus 109 subtests (168 cases), with one
existing warning. PostgreSQL 17.11 passed the updated module: seven tests plus
13 subtests (20 reported cases), including five real database methods and two
overlapping safety methods. All real cases passed on their first follow-up run.
The loaded start gate passed at 1,417.84 MiB / 23.51% free. Generated databases
were removed, role/database inventories matched and the owned server was verified
stopped. The broad offline profile passed **543 tests + 1,036 subtests = 1,579
reported cases**, zero failures/errors/skips and five existing warnings, including
actual Windows ACL checks. These profiles overlap and are not added together.
The two additional real PostgreSQL methods are in the database CI selection.
Source-contract checks, 70 local Markdown links, unchanged application/migration/
hosting-source checks and whitespace checks passed, with the local validation receipt.

Prompt before publishing a draft PR; fresh CI, independent review, merge and any
automatic test deployment remain separate. All hosted execution and credential,
grant, schema, connection/provider or service changes stay held. A fresh source-
bound S1 handoff and live approval remain required; PIN/role/activity/actor
acceptance, G04/G13/O1 and par installation remain open. Ordering manual; par
editing frozen; Track 1 independent.
