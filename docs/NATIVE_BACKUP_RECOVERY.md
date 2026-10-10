# Native inventory backup and recovery verification

This build step verifies recovery in disposable local PostgreSQL databases. It is
not a deployed backup service or permission to restore an operational database.
The tool rejects remote databases, ordinary database names and the test control
database. All verification data is invented; supplied vendor CSVs are not imported.

## Coverage

The native backup captures the entire application database, including `public`,
`purchasing`, `actual_inventory` and any other non-system schemas. It retains:

- Store/item/vendor relationships, fixed units and the existing operational tables.
- Original invoice bytes, every positional source field, supplier versions/parties,
  mapping decisions, reconciliations, initial postings and linked corrections.
- Physical counts and explicit values, linked recounts, closed reports, reopen
  events, report replacements, original and rebuilt item-list handoffs.
- Functions, generated columns, constraints, indexes, views, triggers, policies,
  object ownership and grants needed to retain data-integrity protections.

Prep and sales records are backed up as application data. They still cannot change
Track 1 usage or Food Cost. The accounting source remains purchased-item counts
and signed received-date purchase facts; taxes and fees remain separate.

## Capture and verification

`backend/native_backup.py` opens a read-only repeatable-read transaction and exports
its PostgreSQL snapshot. The row/schema manifest and `pg_dump` use that same snapshot,
so a concurrent store update cannot make the dump describe a different database
state from the manifest. Every table has a row count and SHA-256 over sorted complete
row representations, including original bytea data. Catalog groups record checksums
for schemas, relations, columns, constraints, functions, triggers, internal trigger
states, indexes, views, policies, extensions, types and sequences.

The SQL backup uses native `pg_dump` INSERT statements. Ownership and ACL statements
are retained. Object owners and referenced roles must already exist in the restore
environment; cluster role passwords are not backed up. ACL comparison normalizes
implicit default grants and their explicit equivalents. It still compares the
grantees, permissions, grant options, grantors and object owners.

The tested environment blocks `pg_restore.exe` through Windows Application Control.
No policy was disabled and no blocked executable was altered or relabeled. The
native SQL dump is restored through `asyncpg`. Only the paired outer `pg_dump` psql
input guards are removed; original multiline supplier strings inside SQL literals
remain intact. A custom-format archive/`pg_restore` recovery is not claimed tested.

Restore requires a different, empty disposable database on the same PostgreSQL
version. It refuses existing tables, views, functions or application schemas. It
does not clean, merge, replace or drop existing application data. The empty standard
`public` schema is retained because PostgreSQL 17 omits its creation from the dump.
SQL execution runs in one transaction, so a SQL failure rolls back all its objects
and data. The current default-public-schema setup is tested; an unusually customized
default schema requires a separate rehearsal.

After SQL execution succeeds, a fresh read-only manifest must match every captured
row count, row hash and catalog hash before the result is marked `verified`. A
verification mismatch leaves the disposable database for inspection, records the
different tables/catalog groups and never reports success. A checksum mismatch,
missing manifest, same source/target name or nonempty destination is refused before
any restore write. Earlier backup folders are never overwritten.

Sequences are not MVCC-protected by exported snapshots. Their state is captured and
compared, but sequence activity must be quiesced for a reliable recovery rehearsal.
The tested current schema uses UUID identities and has no application sequences.
Schema-changing work should likewise be paused during operational backup rehearsal.
Runtime/storage requirements for larger databases remain to be measured; INSERT
dumps and full logical hashes favor transparent build verification over compactness.

## App controls

When `REACT_APP_NATIVE_PURCHASES` is active together with PostgreSQL, the app's legacy
JSON Backup/Restore buttons are disabled with an explanation. Their old export
omits native invoice/count/report history, and its restore cannot reconstruct this
graph. Both handlers also guard against invoking that legacy operation in native
mode. Legacy mode retains its existing actions; this step does not repair or certify
the legacy restore workflow. No database administration endpoint is exposed to the
app and no operational backup button is advertised as finished.

## Reproduce locally

Use trusted PostgreSQL tools and disposable source/target connections in environment
variables. Do not place a connection URL or password in a command argument or report.
Apply the public test reference schema and all five native migrations to the source.
The destination must already be an empty, distinctly named test database. Both
connections must use a literal loopback address and `native_purchase_test_*` names.

```text
python backend/native_backup.py create --connection-env NATIVE_BACKUP_SOURCE_DSN --pg-dump <trusted-pg_dump-path> --output <new-backup-directory>
python backend/native_backup.py verify-restore --connection-env NATIVE_BACKUP_TARGET_DSN --backup <backup-directory>
```

Keep `database.sql`, `manifest.json` and the restore-verification records together.
The captured manifest initially says `captured_not_yet_restore_verified`; only a
matching restore generates a separate `verified` result. Checksums detect accidental
damage; they are not a digital signature proving an archive's origin. Restore only
trusted backups created through the controlled rehearsal workflow.

Synthetic tests:

```text
python -m pytest --noconftest backend/tests/test_native_backup.py -q
npm test -- --watchAll=false --runInBand BackupControls.test.js PurchaseImportsTab.test.js ActualInventoryTab.test.js
npm run build
```

Tests need the guarded disposable `NATIVE_PURCHASE_TEST_DSN`, `NATIVE_BACKUP_PG_DUMP`
and an optional `NATIVE_BACKUP_EVIDENCE` output directory. Source/target databases
are generated per case and removed afterward. A local runner stops its test service
in `finally`. The verified synthetic dump and manifests can be kept for review.

## Acceptance case and remaining deployment work

The rich recovery fixture covers PFG and US Foods, duplicated vendor address fields,
unknown fields and multiline invoice text, a received-date/quantity/cost correction,
linked price credit and physical return, explicit counts, recounts, two reopened
chains, five immutable report generations and two item-list handoff generations.
Checks compare restored API histories and report hashes, original source bytes,
correction retry results, immutable history and closed-date write protections.
Recovery exposed a tied purchase-history ordering issue: original and reversal
entries shared the old sort keys. The history route now uses mapping/event IDs as
additional sort keys, keeping the same records in the same order after restore.

The two latest closed periods retain actual Food Cost of $60.00 and $21.00. Large
invented prep/sales values do not change those results. Other tests cover a concurrent
write during capture, damaged/missing input, same-source or occupied destinations,
failed-SQL rollback and prevention of false verification success. Screen tests cover
disabled incomplete JSON actions in native mode and preserved legacy-mode controls.

Before enabling operational use, rehearse recovery against the intended managed
PostgreSQL environment, with its roles, extensions, RLS, external files/storage,
secrets/configuration, supported connection mode and acceptable backup/restore time.
Retention, encryption, off-device copies and a recurring verified-recovery process
also need an operating decision. Scheduling, Operations and Toast integrations may
add external state beyond the database and need their own coverage checks.

This local rehearsal closes the new-schema recovery proof gap. It does not certify
managed-platform recovery or make the legacy application export a complete backup.
Manual/other-vendor sources now share the native ledger; see
[manual purchase sources](MANUAL_PURCHASE_SOURCES.md) for the sixth migration and
its additional recovery proof. Operational unit adapters, unnumbered-receipt policy,
dependent-credit correction bundles and uncommon adjustments still precede
accounting cutover.
