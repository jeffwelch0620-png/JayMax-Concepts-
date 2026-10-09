# Hosted Supabase to local recovery copy

Prepared October 9, 2026. This is the implementation and acceptance plan, not a
completed hosted backup, automated job, restore utility or verified recovery claim.
Nothing is scheduled by this checkpoint.

## Scope and authority

Supabase remains the sole authoritative database. Export from it into a private,
encrypted local backup. Restore tests use a new disposable database, never the
connected hosted project and never a live local database. Restored data is for
verification/recovery; it must not feed back into hosted inventory through sync.

The older `native_backup.py` remains deliberately limited to disposable loopback
databases and `public`, `purchasing`, `actual_inventory`. Do not loosen that tool's
remote-source/restore guards or call its three-schema proof a complete current
application backup. Add a separate hosted-export entry point and reuse only the
verified comparison primitives where their scope is explicit.

Initial application export scope, confirmed present in the current hosted catalog:

| Schema | Required content |
| --- | --- |
| `public` | Catalog, mappings, legacy/reference history, app users and settings |
| `purchasing` | Original imported bytes/fields, supplier lines, posting/correction history, receipts and separate tax/fee data |
| `actual_inventory` | Physical purchased-item counts, explicit valuations, period closures and immutable corrections; Track 1 accounting baseline |
| `prep_inventory` | Prep batches/counts, conversions, containers, waste, observations and historical Track 2 explanation |
| `integrations` | Existing integration tables and mappings; future Toast sales/source history belongs in the reviewed schema scope |
| `supabase_migrations` | Applied Supabase migration history, currently present |

Export every table/column in these schemas, including fields that have no mapped UI
output. Keep historical and source records intact. Never reconstruct Track 1 from
prep or sales during backup or restore. Preserve date-received accounting, explicit
count values, item/location IDs, original units and mappings, and separate fees/taxes.
Add future scheduling/operations/analytics schemas to the manifest deliberately;
unknown schemas require classification rather than silent omission.

The observed provider schemas are `auth`, `cron`, `extensions`, `graphql`,
`graphql_public`, `net`, `realtime`, `storage`, `vault`. They need a separate
Supabase-managed recovery inventory: enabled extensions, custom functions/triggers/
policies, Auth use and users, Storage metadata and actual objects, Vault/encryption
keys, scheduled jobs, publications and external service configuration. Do not assume
they can be restored into plain PostgreSQL by copying application tables.
The current zero Storage metadata rows do not prove Storage will remain unused.
Supabase database backups do not contain the stored object files themselves.
([Database backup scope](https://supabase.com/docs/guides/platform/backups))

## Export implementation sequence

1. Require an expected project reference and reviewed owner/backup connection from
   private configuration. Validate endpoint, database and project before connecting;
   reject DSN routing overrides. Require certificate and hostname verification.
   Use the session pooler on 5432; direct IPv6 remains an optional tested local path.
   Do not buy IPv4, rotate passwords or use an application role as the backup owner.
2. Create a current-user-restricted folder outside Git and Google Drive's live
   database folders. Use a temporary private credential/passfile or subprocess-only
   environment; never put passwords in command arguments, logs or shared manifests.
3. Discover all schemas, extensions, application relations, role definitions and
   grants. Compare discovery with the scope manifest and hold on missing/unclassified
   objects. Record migration-file checksums alongside database migration history.
   Export role attributes/membership without password hashes. Credential recovery
   uses separately secured private configuration; data backups do not replace it.
4. Begin one repeatable-read, read-only source transaction. Export its snapshot and
   keep it open while `pg_dump` captures all six schemas in one custom-format archive
   using that snapshot. Use PostgreSQL 17 tooling compatible with the observed 17.6
   server. No parallel dumps are needed for the current small build database.
5. Within the same snapshot, record sorted table row counts/data fingerprints and
   catalog fingerprints for columns, constraints, indexes, functions, triggers,
   policies and ACLs. Preserve bytea/source invoice bytes. Record sequence state
   separately: sequences and global roles are not MVCC-snapshot-consistent, so a
   quiescent export or explicit sequence reconciliation is required for recovery.
6. Encrypt the archive and private manifest with authenticated encryption. Keep its
   recovery key separately in private configuration with a tested recovery copy.
   Verify encrypted bytes/digests, atomic finalization, decryption and archive TOC;
   only then mark export complete. Failed/incomplete output is never a usable backup.
   Shared review packages contain only sanitized receipts and hashes, never data,
   passwords, user records, raw SQL, encrypted archives or recovery keys.

`pg_dump` selecting schemas does not automatically supply every out-of-scope
dependency. Capture and classify dependencies before claiming this scope is
restorable. Supabase's managed recovery instructions also require special handling
for migration history, modified managed schemas and encryption keys.
([Supabase recovery procedure](https://supabase.com/docs/guides/platform/migrating-within-supabase/backup-restore))

## Restore and acceptance sequence

1. Verify archive authentication, manifest format/project/scope, digests, tooling
   versions and migration checksums before issuing restore SQL. Refuse a damaged,
   incomplete, unclassified or partial backup. Refuse remote/control/nonempty targets.
2. Create a UUID-named `native_purchase_test_*` database on the dedicated loopback
   test server. Prepare reviewed dependency schemas, extensions and role stubs there.
   Use a version-compatible local Supabase stack for the separate managed-services
   rehearsal; a plain PostgreSQL restore only proves the declared application scope.
3. Restore transactionally with stop-on-error. Restore ownership/grants from reviewed
   metadata; secrets remain separately provisioned. Never leave a failed restore
   available to app users. Preserve/audit expected trigger and row-security states.
4. Compare all included table/catalog fingerprints, original invoice bytes, immutable
   ledgers, mappings, migration history and sequences. Compare Food Cost reports and
   Track 1 closures independently of prep/sales; then compare Track 2 explanations.
   For Track 3, verify existing integration records and any future Toast data without
   claiming POS portion counts establish actual consumption.
5. Run readiness and restricted-role write/access guards against the isolated target.
   Assert that retry/idempotency and historical correction behavior survived. Record
   complete verification results with explicit application-vs-managed scope limits.
6. Stop and clean up only the named disposable target after preserving sanitized
   evidence. Report failure as held; successful export alone is not successful recovery.

After the first complete trial, select a daily backup time and retention policy with
the owner, include a pre-migration snapshot, and repeat isolated restore drills.
An encrypted off-device recovery copy protects against loss of the local computer;
keep its decryption key separate. Scheduling and cloud-copy actions remain future
work, not an implied request to create an automation now.

## Remaining release conditions

Implement and prove this workflow before promising local disaster recovery.
Separately resolve exact-role retirement through the pooler, complete the combined
credential/recovery checkpoint, finish browser/Data API and deployment checks, and
review the pending PR chain before proposing sequential merges. TLS success does
not waive those existing holds or activate disabled native workflows.
