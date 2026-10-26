# Manager handoff installer and encrypted recovery: local implementation

October 25, 2026. Local fictional validation only. The owner approved this bounded
follow-up to the [installation proposal](MANAGER_HANDOFF_INSTALLATION_PROPOSAL_20261025.md).
No hosted execution, service controls, real credentials, grants, policies, schema,
application connections or feature settings are approved or changed by it.

## Implemented scope

`backend/manager_handoff_install.py` adds a separate local receiving adapter.
All entry points that connect or mutate require a literal loopback PostgreSQL
URL and an explicitly disposable `native_purchase_test_*` database, excluding the
control database, remote names, URL options and operational database names. It
does not load configuration files, create roles, write passwords or enable flags.
There is no hosted command-line entry point or automatic installation on startup.

The plan binds the actual local target without a password, source hashes, current
legacy value/catalog/ledger fingerprints, restricted role attributes, and three
independently rendered payloads. One transaction installs:

1. The unchanged receiving SQL body, using the existing transaction lexer to
   remove only the reviewed outer BEGIN/COMMIT.
2. Explicit runtime table verbs and four `handoff_backend_v1` policies.
3. The fictional Bert's / America/New_York / revision-1 settings row.

Each payload receives its own exact statement/body hash and explicit ledger row.
The caller must supply three collision-free versions and independently retain
the exact plan digest. Locks, source/baseline rechecks, guard/catalog/permission
checks and original-value/ledger preservation precede commit. No `IF NOT EXISTS`,
partial-schema repair or automatic retry is included. A late failure rolls back
all three payloads; lost commit acknowledgement is UNKNOWN and requires explicit
read-only reconciliation. Even a not-installed result does not authorize retry.

The effective-permission verifier uses actual separate operational/accounts LOGIN
connections. It refuses ownership, privileged role attributes/memberships,
unreviewed delegation/column ACLs, extra policy recipients and malformed/disabled
guard wiring. It checks the independent receiving catalog and current policy/ACL
matrix without widening the historical native runtime profile. Required store
reads use the operational login; account-column reads use the accounts login.
The primary connection cannot substitute for the accounts connection.

This is feature-local qualification, **not** full native-role or account/login
readiness. The report explicitly leaves that wider qualification unproven. No
server-route changes or broader identity/security adoption are bundled here.

`backend/manager_handoff_recovery.py` adds an explicit seven-schema encrypted
fictional recovery format, including `operations`. It uses one consistent source
snapshot, canonical row/sequence and catalog fingerprints, authenticated encrypted
archive bytes and a bounded, empty disposable restore target. ACLs/policies remain
in the dump; existing same-cluster fictional roles are required for restoration.
Compare restored data, ownership, ACLs, constraints, functions, triggers and RLS,
then prove the original saved request still replays against the newer correction.
No plaintext archive survives its owned temporary restore directory.

Restore uses `--no-owner`, but post-restore facts include ownership, ACLs and
role-addressed policies. The documented tested path uses the same-named owner
role and a cluster where the operational/accounts roles already exist. The tools
do not reconstruct roles or passwords. Cross-cluster recovery is unverified;
there is no cluster-identifier binding that categorically blocks it. Do not
describe an untested cross-cluster restore as an enforced refusal or a passed case.

The existing `hosted_backup` module and old six-schema archive format remain
unchanged. The new code neither monkeypatches `SCHEMAS` nor rewrites sealed par
pins. This local profile refuses managed/extension/foreign-server dependencies
rather than claiming it restores them. Its format/target guard is deliberately
local-only; it is not yet an approved hosted recovery path or operational restore.
Role-password, cross-cluster role reconstruction, managed-service recovery and
full release readiness are explicitly outside its acceptance claim.

## Validation evidence

The first focused selection passed 45 methods and 55 subtests (100 reported
cases), covering the new offline guards, unchanged legacy backup tests and
current manager authorization/input validation. The first PostgreSQL selection
passed 13/18 methods plus five subtests; five new installer paths were held by an
ambiguous `has_function_privilege` argument binding (integer OID inferred as a
function name). The query now explicitly casts role/name and function/OID. No
existing journal regression failed, and the owned local server stopped cleanly.

The corrected serial run passed **18 methods and 12 subtests (30 reported cases)**
in 280.97 seconds, including the strengthened column-delegation and nonempty
function-only restore-target cases. It covers all six new installation/recovery
methods and all 12 existing journal methods. The owned server stopped cleanly.
No initial failure is called a clean pass. A subsequent source-binding hardening
adds the frozen ledger/reconciliation helper files to the exact plan inventory;
the final actual-LOGIN installation check is recorded separately below.

After adding the frozen ledger/reconciliation helper files to the source binding,
the final actual-LOGIN installation check passed **1/1** in 41.41 seconds; its
owned server stopped. This overlaps the 18-method selection and is not an
additional unique feature case. Source/manifest hashes, Python compilation,
generated-guide consistency and local Markdown links were checked. All 22
accepted proposal-source files, including sealed native/par/backup inputs, remain
byte-unchanged. No application/frontend file changed in this follow-up.

Evidence filenames under the existing owned `manager-handoff-local-20261025`
directory: focused `install-offline-20261025T220739166093Z`, initial database
`install-database-20261025T222210381838Z`, corrected database
`install-database-20261025T222806849981Z`, final bound-source check
`install-database-20261025T231116461018Z`; stopped broad profile
`offline-20261025T223927764782Z`. Receipts are local validation evidence, not
hosted/CI results or operational backup artifacts.

The broad offline profile was started serially but stopped as incomplete after
more than 30 minutes with less than 25 percent progress. The runner and its
identified descendants were stopped; no unrelated app was closed. There is no
completed broad local pass or JUnit receipt to substitute for one. The focused
100-case result and 30-case PostgreSQL result above remain valid; selections
overlap. Fresh full Windows/offline and backend CI remain required after a
separately approved draft publication. Do not describe this as full local-suite
acceptance or merge readiness.

The disposable runner scrubs app/PG connection settings and uses fictional
SCRAM credentials, a fresh owned loopback PostgreSQL 17 cluster, the existing
at-least-1-GiB/15-percent start gate and explicit stop verification. No supplier
CSV, operational account, password/PIN, hosted configuration or data is loaded.
All 22 accepted source inventory entries remain byte-unchanged. Frontend files
are unchanged; their previous CI receipts are historical, not newly run tests.

## Remaining gates

PR73 review amendments D1/L1/L2/N1 make the hosted adapter/backup-consumer gate
mandatory before H2, document the S2a/P1/adapter/H0-H3 order, require actual R1
qualification before H3, and state the restore-fidelity boundary above. The
installer now preserves its primary/start/UNKNOWN error if rollback or connection
cleanup also fails, retaining safe cleanup error classes; failed close after an
acknowledged commit carries `commitAcknowledged=true` and never returns success.
Managed project schema/role markers are refused on owned connections and rechecked
in the mutation/snapshot paths. Marker absence is additional defense, not proof
that every loopback-forwarded target is safe. Only fictional markers are created
in local tests. The amendment passed **107 focused offline cases** (48 methods
and 59 subtests) and **32 disposable PostgreSQL cases** (20 methods and 12
subtests), including both new real database regressions and all existing journal
methods. The database run took 301.79 seconds and its owned server stopped.
Evidence: `install-offline-20261026T001602718492Z` and
`install-database-20261026T001757129337Z` (UTC filenames; October 25 Eastern).
No test/resource threshold was lowered: the loaded database start check passed
at 1,055 MiB / 17.5 percent after an earlier lower memory observation. All 22
accepted raw-byte inputs remain unchanged, and compilation/guide/link checks
passed. Fresh amended-head CI remains a separate required gate.

PR73 was published at initial head `6bb5429`; its
[initial CI](https://github.com/jeffwelch0620-png/JayMax-Concepts-/actions/runs/40245339030)
passed all four checks. The owner subsequently authorized these review amendments
and merge after successful tests/CI. Initial-head results are historical and are
not substituted for the amended-head checks. Hosted testing and real credential,
grant, policy, schema, connection and flag changes remain held.

Finish amendment JMax readback and fresh tested-head CI before the owner-authorized
merge. Prompt before any later new draft PR. The earlier
source inventory is the dated proposal baseline, not a claim this implementation
was present at that time; its raw byte hashes are preserved rather than rewritten.

After acceptance of this local work, prepare a separately reviewed hosted adapter
and exact preflight/maintenance/backup binding. Do not remove loopback guards to
run these tools against Supabase. Actual project/role/writer verification, fresh
encrypted pre-install backup, restore proof, collision-free ledger versions,
timezone confirmation, exact SQL approval and flag/build activation still need
their own approved scope. S1 harness work and named responsibility transfer stay
separate. Ordering remains manual and Inventory stays the sole stock writer.
