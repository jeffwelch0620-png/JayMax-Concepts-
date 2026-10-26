# Journal-aware backup adapter: local implementation and acceptance

October 25, 2026. **Local implementation; not approved hosted execution.**

## Problem and resulting behavior

The frozen six-schema exporter refuses an installed `operations` namespace. PR73's
seven-schema recovery prototype intentionally refuses managed sources and remote
connections. Neither tool can be relabelled as a hosted journal backup.

The new manual adapter has an explicit `receiving7` profile, authenticated v2
envelope, caller-held packet/artifact/source bindings and isolated loopback restore.
The old v1 reader/exporter and PR73 protections are unchanged. Application startup,
FastAPI, UI, feature flags, migrations, roles, policies and grants are unchanged.
The design and its original source inventory remain dated records:

- [Reviewed local design](HOSTED_JOURNAL_BACKUP_ADAPTER_DESIGN_20261025.md).
- [Original design source inventory](HOSTED_JOURNAL_BACKUP_ADAPTER_SOURCE_PINS_20261025.json).
- [Current receiving installation proposal](MANAGER_HANDOFF_INSTALLATION_PROPOSAL_20261025.md).

Owner authorization covers this implementation and fictional tests, JMax updates
and a prompt before draft publication. It does not approve a push, CI/merge,
deployment, hosted connection, backup, service pause, credential, grant, policy,
schema, connection or activation change. No live packet/window has been created.

## Implemented contract

| Component | Behavior |
| --- | --- |
| `application_backup_profiles.py` | Immutable exact six/seven-schema profiles, profile digest, strict JSON and size/digest checks. No automatic discovery/downgrade. |
| `hosted_journal_backup.py` | Explicit-scope catalog/row/sequence fingerprints, managed-dependency binding, one read-only repeatable-read dump snapshot, global role/sequence checks, protected encryption and owned disposable restore. |
| `hosted_journal_backup_cli.py` | Manual `export` or `verify-restore`; requires `--execute`, exact private packet and independently held packet digest, explicit profile and PostgreSQL tools. Reads only the separate maintenance configuration after validation. No URL/password arguments, ambient app-URL fallback or import-time configuration/network. |
| `journal_backup_receipts.py` | Independent v2 profile/source/artifact/facts/receipt/window checks for newly reviewed consumers. Export is not restore verification. Missing journal/ledger coverage cannot satisfy installation evidence. |
| Test runner | New offline and disposable database cases are selected for future normal CI. No CI run is claimed before publication. |

`legacy6` dispatch supports the unchanged v1 reader. The new CLI exports only
`receiving7`; the original six-schema CLI remains separate. A seven-schema v2
envelope is refused by the old reader. This is not compatibility via cropping,
renaming a manifest, monkeypatching schema globals or rewriting frozen source.

The source capture uses the existing direct native IPv6/certificate-verified TLS
maintenance path. It does not change Render/app poolers, buy IPv4, create another
connection plan or fall back on network failure. Exact source binding and current
source hashes are required before DNS; source hashes are rechecked before publish
and at restore entry/closeout. Source/global role facts are also read after ending
the repeatable-read snapshot so that a same-snapshot recheck cannot hide an
observed role/schema change. Sequence drift holds rather than claiming MVCC.

## Archive, custody and recovery boundaries

- The complete application dump includes raw invoice bytes, unmapped columns,
  exact decimal values, ledger, counts/prep data and journal revisions/receipts.
  It creates no stock write or synchronization path. Track 1 remains independent.
- Fernet authenticates the private manifest and archive. The v2 reader additionally
  requires the independently held encrypted-artifact digest and expected bindings.
  Duplicate JSON keys, nonfinite values, malformed/missing fields, wrong profiles,
  partial coverage and changed digests hold. Source capture bindings are retained;
  an archival restore has its own fresh execution window without redating capture.
- Preserve existing ceilings: connect 20 seconds, command 60 seconds, scoped
  fingerprint queries 20 seconds, tool 240 seconds, operation at most 600 seconds,
  cleanup five seconds, archive 64 MiB and envelope 192 MiB. No new memory threshold.
- Custody uses the unchanged private-directory/ACL primitive. Final publication
  follows source close, authenticated readback and plaintext cleanup. Failure
  reports safe categories/retained-artifact booleans; it does not print raw driver
  text, SQL, rows, paths, credentials or helper definitions. Export custody paths
  are retained in the protected owner record, not public CLI output.
- Restore requires a fresh UUID database, explicit loopback/control endpoint,
  caller-held dedicated cluster system identifier and database OID, matching owner,
  empty target and matching PostgreSQL major. Existing function/type/default-ACL
  or unexpected-schema targets are refused before bootstrap/restore SQL.
- Restoration preserves ownership, ACLs/default ACLs, policies and guards. V2 adds
  type ownership/ACL facts beyond the unchanged six-schema comparison oracle.
  Required roles must be pre-provisioned. Aside from the dedicated local owner,
  roles must be inert NOLOGIN stubs without privileged attributes or memberships.
  This adapter never creates/changes global roles or copies PostgreSQL passwords.
- Only explicitly approved extension families/versions and independently pinned
  zero-argument SQL/non-definer Auth helper definitions may be bootstrapped locally.
  Foreign data, unreviewed language/extension/type or global-default-ACL cases hold.
  Expected local dependency stubs do not disable PR73's managed-marker refusal.
- This is application recovery. Auth/Storage/Vault/cron/platform recovery and real
  operational/accounts LOGIN/password recovery are not verified. Encrypted
  application-table data may include its existing application authentication rows;
  that is distinct from reconstructing PostgreSQL role credentials.

## Consumer transition and remaining gates

| Consumer | This local slice | Before receiving H2/H3 |
| --- | --- | --- |
| New manual seven-schema recovery | Implemented and tested locally; inactive without exact execution approval. | Independent review/CI/merge and separately approved hosted qualification. |
| Frozen six-schema manual/par/index tools and source pins | Unchanged; no v2 coercion or automatic repinning. | Complete retained six-schema work before H2, or separately review a new supported consumer. Six-only commands remain held after H2. |
| New receipt validator | Implemented; requires external artifact/facts/receipt digests, fresh consumer window, ledger/journal coverage and successful cleanup/restore. | Bind it into each newly reviewed executable consumer; this validator alone is not an H2 executor. |
| Historical calibration | Still means its original scoped observation. | It cannot certify operations coverage without a newly reviewed observation profile. |
| S2a/P1/R1 | Existing sequence and approvals remain. | S2a precedes administrative windows; P1 if retained precedes H2; actual R1 blocks H3. NOLOGIN/SET ROLE and fictional owner credentials are not R1. |
| Routine/coworker/scheduled consumers | Not inspected. | Inventory privately under separate approval and classify each supported/completed/explicitly held. Do not leave an active needed backup path on the refusing exporter. |

The consumer matrix is still a hard pre-H2 gate. A green local adapter test or PR
does not authorize installing `operations`, changing a permission/flag or using an
expired maintenance window. The next hosted proposal must bind the accepted source,
private target, dependency policy, active schema/consumer/writer inventory, custody,
budgets and exact scope; it is not generated or activated by this implementation.

## Validation record

All database fixtures are explicitly fictional: Bert's / October 25, 2026 / Bulk
Prep; original CSV-like binary bytes including CRLF, NUL and invalid UTF-8;
`numeric(38,18)` at `0.000000000000000001`; dated migration ledger; draft, submission,
correction and original command receipt. Hosted-looking URL strings never reach
DNS in these tests. Routing/TLS and private-directory boundaries are mocked to an
owned local test server; actual dump/restore, SQL constraints, fingerprints and
command replay execute against PostgreSQL 17. Existing TLS/ACL regression tests
are selected separately. These mocks prove no Supabase handshake or live custody.

Initial focused evidence: 81 methods and 190 subtests passed. Three initial
PostgreSQL cases failed because the fictional `pg_dump` boundary inherited
production TLS against a non-TLS loopback server. Only that test boundary was
corrected; production IPv6/TLS was not weakened. The corrected seven-method /
two-subtest rerun passed. A later expanded 12-method / seven-subtest run passed.
These are historical checkpoints, not additive unique-case totals.

Final local evidence is captured with artifact digests in the
[validation/source record](HOSTED_JOURNAL_BACKUP_ADAPTER_LOCAL_EVIDENCE_20261025.json):

| Selection | Result | Interpretation |
| --- | --- | --- |
| Broad offline profile | **2,128 reported cases: 886 methods + 1,242 subtests; no failures, errors or skips.** | All normal offline selections executed. Five inherited FastAPI/multipart deprecation warnings remain. This preceded the final CLI-only target-record amendment. |
| Final focused selection | **298 reported cases: 86 methods + 212 subtests passed.** | Overlaps the broad run; additionally exercises the final exact target-record binding and successful private-config CLI export/public-output boundary. Only inherited multipart deprecation warning. |
| Combined new adapter + PR73 PostgreSQL regression | **37 reported cases: 21 methods + 16 subtests passed.** | Includes the new same-cluster cases, prior receiving installer/recovery, actual restricted fixture LOGINs, ACLs/RLS, custom type ACL, extension/helper recovery, drift, timeout and immutable history/replay. It preceded final packet/CLI-only amendments. |
| Broad cross-cluster checkpoint | **19 reported cases: 12 methods + seven subtests passed.** | Independent initialized PostgreSQL clusters, different fictional owner passwords, distinct system identifiers and pre-provisioned NOLOGIN stubs. Same computer; not a full machine/provider recovery claim. |
| Final same-cluster binding selection | **Two methods passed.** | Full seven-schema export/restore/replay plus missing/LOGIN-enabled role refusals with expanded source/project binding. |
| Final cross-cluster binding selection | **Two methods passed.** | Same two cases against the second independent server after final packet amendments. Current code/source/packet bindings; owner passwords were not copied. |

These selections overlap; do not sum them as distinct scenarios. No frontend
source changed, so frontend tests/build were not repeated for this tooling-only
slice. CI/review/merge and all hosted/live acceptance remain pending.

Every owned server was stopped, owned connections/tools were closed, and fictional
target databases/temporary artifact directories were cleaned by their test owners.
`cleanupVerified` in an adapter receipt concerns its owned connections/processes
and partial files. The restored database is deliberately retained for independent
replay/inspection; the engine never drops databases or alters global role stubs.
An operator must separately complete owned-target/stub/server closeout. A future
hosted-data rehearsal must prove private, off-Git/off-sync database-storage custody
and the dedicated-server ownership inventory under its exact approved packet; a
UUID/system identifier alone is not permission to use an arbitrary local server.

Restore CLI packets now additionally bind the exact private target-record byte
SHA-256 before reading its environment-variable names or opening a connection.
Swapping a different otherwise valid owned-target file requires a new approval
packet. The packet/project digest is cross-checked independently against its exact
direct endpoint. All 14 runtime/helper source files are bound and all 34 original
frozen worktree hashes were verified unchanged. Cross-platform guard tests accept
only the previously recorded exact worktree/Git-blob bytes where the original
inventory explicitly recorded a checkout-line-ending difference.

## Reproducing the selections

Use Python 3.12 with the reviewed backend dependencies and fresh JUnit output paths:

- `python tools/run_review_tests.py offline --report <new-local-report.xml>`
- With an owned PostgreSQL 17 control database, `NATIVE_PURCHASE_TEST_DSN` and
  matching `NATIVE_BACKUP_PG_DUMP`: `python tools/run_review_tests.py database --report <new-local-report.xml>`.
- Target just `backend/tests/test_hosted_journal_backup_pg.py::JournalDatabaseTests`
  for the new database cases. An optional `NATIVE_JOURNAL_RESTORE_TEST_DSN` selects
  a separately initialized loopback control server with the same fictional owner
  role and different fictional password. It must be explicitly owned and empty;
  do not point either variable at any app/hosted/operational database. Source and
  second control endpoints are validated before fixture connections.

The complete repository database profile also contains unrelated existing cases;
only the named combined/new selections above were run locally for this slice.
Future CI is configured to run the full profile. Local server startup retained the
existing 1 GiB / 15% memory gate; no paid network option, security-setting change,
service pause, hosted connection or real credential/grant/schema change occurred.

Next action: prompt for publication as one new draft PR. Independent review and
fresh CI must precede merge approval. Continue holding every live action and the
consumer transition/installation gates described above.
