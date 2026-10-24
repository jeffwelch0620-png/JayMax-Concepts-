# S1 collector disposable PostgreSQL test

## Purpose and boundaries

PR61 is accepted as bacf51b, tree-identical to reviewed head 7cbc7a5, with separate
reviewed-head and merged-main CI passed. Its in-process tests did not execute the
complete collector SQL against PostgreSQL. The re-review reports a separate
PostgreSQL 16 check of the three audit statements with 600 synthetic rows; that
is reviewer-reported evidence, not a complete collector or live acceptance run.

N3 adds [test_s1_observation_pg.py](../backend/tests/test_s1_observation_pg.py) to
the existing [database CI selection](../tools/run_review_tests.py). All data is
fictional and all fixture DDL is confined to a newly generated database on the
dedicated loopback test cluster. No application collector, identity guard, route,
dependency, migration, schema snapshot or hosted setting changes. No app or
maintenance configuration is loaded. This does not authorize hosted execution,
credentials/PINs, grants, schema installation, service controls or a new live S1
window. Ordering remains manual; par editing frozen; Track 1 independent.

## Fixture and coverage

The fixture rejects any DSN other than the explicit loopback
purchase_implementation_test/native_purchase_test_control connection, with a
port and without query/fragment overrides, before any connection. It creates a
randomly named native_purchase_test_s1 database and registers cleanup immediately.
The activity_log definition is extracted unchanged from
[supabase/schema.sql](../supabase/schema.sql). It seeds 250 owner/manager events
over multiple UTC days, plus excluded out-of-window and staff-role events;
fictional store PIN configuration; cron jobs 3/4; migration version/name rows;
empty metadata stubs for the remaining fixed objects; and one fictional policy.

The complete test uses two real asyncpg connections with
default_transaction_read_only=on, real repeatable-read/read-only transactions,
all fixed metadata/ledger/audit SQL, and a temporary JsonlCheckpoints file. It
asserts the exact scoped aggregate, both 100-row edge samples including the
oldest/newest events, accurate truncation, JSONL parsing and byte caps, no private
values in the public receipt, unchanged fixture rows, and owned connection/session
closure. No SQL is mocked or rewritten in this path.

Production requires the postgres/postgres/postgres maintenance identity. The
dedicated CI role and generated database intentionally differ. A test-only adapter
first executes the real identity SELECT and verifies the actual disposable role,
database and transaction_read_only=on, then translates only those returned
identity fields to let the existing production guard run. This is not proof of
the hosted maintenance identity or TLS. There is no production bypass flag or
weakened guard; a separate real test omits the adapter and requires refusal and
owned closure. Offline cases reject wrong role/database/read-only adapter inputs.

A third real test removes name only from its isolated fixture ledger. The actual
ledger SQL must raise UndefinedColumnError (SQLSTATE 42703); the private prefix
through metadata.sessions must remain parsable, audit coverage stays unevaluated,
and no second connection is opened. This does not establish the cause of the old
hosted timeout, whose exact failing step remains unconfirmed.

The fixture removes its generated databases, closes its clients and leaves roles
unchanged. The local operator wrapper verifies the existing memory start gate
(at least 1 GiB and 15% free), owns only the known stopped PostgreSQL 17 cluster,
checks its PID/data directory, compares role/database inventories and stops it
after testing. No shared or hosted objects are installed or altered.

## Validation and publication

The broad local offline profile passed **538 tests + 1,018 subtests = 1,556 cases**,
with zero failures/errors/skips and five existing warnings, including actual
Windows ACL checks. It includes the new disposable-target/identity-adapter safety
checks and verifies that all three N3 database methods are in DATABASE_CASES,
while only their offline safety class is in the offline selection. This profile
does not run the PostgreSQL methods. The initial overlapping focused selection
passed 39 tests plus 74 subtests before the runner-selection assertion was added.

The final overlapping focused selection passed **40 tests + 74 subtests = 114
cases**, including the runner-selection assertion. After a fresh passing memory
gate, PostgreSQL **17.11** executed the full new module: **5 tests + 13 subtests =
18 reported cases**, with zero failures/errors/skips. Three methods use real
PostgreSQL; two safety methods overlap the offline selections. All three real
cases passed on their first database run. The start reading after loading the
wrapper was 1,229.63 MiB / 20.39% free. The wrapper verified unchanged database/role
inventories and that the owned local server was stopped afterward.

No database server was started while the resource gate failed. The last fictional
PIN literal was lengthened to avoid accidental matches with six-decimal timing
values in redaction assertions; the final focused and PostgreSQL profiles ran
that fixture. The broad offline safety methods were unchanged by that literal.
No hosted request, operational data import, dependency installation, credential
change or production schema/grant change occurred.

Source-contract checks, 64 local Markdown links, unchanged production-source checks
and whitespace checks passed and are recorded with the local validation receipt.
No new PR has been pushed; prompt the owner before publication. Fresh CI,
independent review, merge and hosted execution remain separate gates.

## Remaining work

After local validation and independent PR review, prepare a fresh source-bound S1
handoff with secure probe inputs, existing role contexts, approval, target/source,
deadline, resource and private-evidence guards before requesting another live
attempt. N3 does not complete PIN/role probes, activity review or API actor/consumer
attribution. G04/G13/O1 remain open. N2 PIN-storage/key-management/verification/
manager-controls/migration and any S2a PIN reset remain a separate security decision.
