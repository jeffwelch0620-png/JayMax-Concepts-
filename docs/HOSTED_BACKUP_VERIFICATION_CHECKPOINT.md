# Encrypted hosted application backup and isolated restore

October 9, 2026. Local review branch only. No push, merge, deployment, hosted write,
credential change, application activation or paid IPv4 add-on. Supabase remains
authoritative using the session pooler on 5432. The local encrypted copy is for
recovery; it does not synchronize edits back into hosted inventory.

## Completed evidence

Receipt: `hosted-backup-trial-20261009T185020854644Z.json`, completed at
2026-10-09 18:59:01 UTC. Status:
`verified_hosted_application_backup_and_local_restore`.

| Check | Result |
| --- | --- |
| Scoped schemas | public, purchasing, actual_inventory, prep_inventory, integrations, supabase_migrations |
| Data/sequence fingerprints | All 120 matched |
| Non-sequence records | All 8,335 matched |
| Catalog groups | All 13 matched, including definitions, ownership, policies and ACLs |
| Migration-file hashes captured | 30 |
| Hosted baseline and application fingerprints | Preserved after export/restore |
| Sequence state | Observed stable during export; not MVCC-consistent |
| Out-of-scope catalog dependencies | Zero discovered; no helper/extension bootstrap required |
| Restored access | Account private-schema access denied; inventory account-table access denied |
| Restore into populated target | Refused |
| Local target/created role stubs | Cleaned up; test server stopped |
| Local backup guard tests | 10 passed; no failures, errors or skips |

PostgreSQL 17.6 source and 17.11 tools/local server share a major version, not a
patch version. The compatibility claim is this successful actual comparison.
Existing integration payloads are included; this trial imported no sample invoices
or new operational records. All six schemas' source columns and history are copied,
including fields with no mapped output. Track 1 data is preserved independently of
prep/sales. There are zero closed source periods; no runtime Food Cost report
comparison is claimed.

Archive SHA-256:
`84a8bd454f8e45d01d9e202976fbfbf6737e8dbe66f273776bd0969c22a7912e`.
Encrypted-file SHA-256:
`5baf64df60db3774cf134f33e891cf2ef52eb9ca78d230a23b797cf807062f6e`.
Authenticated application-manifest SHA-256:
`1ec3d72828acb69e27164690a49424314c36436210f7477bbe5c2a491118805b`.

The archive and key are in separate current-user/SYSTEM-restricted local folders
outside Git and Drive. Exact private locations are retained in the local receipt.
Shared packages contain sanitized evidence and code, never raw dumps, invoice
bytes, encrypted database archives, environment files or keys. An off-device
recovery copy of the archive/key has not been created.

## Implementation and corrected holds

`hosted_backup.py` pins the expected owner/project/session endpoint, verifies TLS,
uses a read-only repeatable-read exported snapshot for one six-schema custom dump,
and authenticates the archive plus private manifest with Fernet encryption.
Metadata includes role attributes/membership without passwords, migration hashes,
catalog/data fingerprints and separate sequence observations. Export alone returns
`exported_not_restore_verified`; only a complete strict comparison verifies restore.

Restoration authenticates before connecting, refuses remote/control or nonempty
targets, requires a fresh UUID-named loopback database and compatible major version,
and checks role stubs/ownership. Application objects restore transactionally with
stop-on-error. It preserves the initial public schema while applying its archived
ACL. Role stubs support ownership/grants, not restored identities or passwords.

Earlier held receipts remain held and are retained with the evidence. Initial
Windows ACL construction was corrected. Large existing JSON payloads made raw-row
transfer fingerprinting time out; server-side canonical row hashing avoids that
payload transfer. Public-schema recreation lost its default PUBLIC USAGE grant;
filtering only the schema-creation TOC entry preserves the initial grant and keeps
the archived schema ACL. Linux/Windows locale ordering produced false catalog
hashes despite equal definitions; canonical session settings, byte-order ACL sorting
and Python record sorting make comparisons portable. The final trial passes every
strict group, not a relaxed comparison.

Ten guards cover actual private Windows ACLs, encryption/binary round trips,
tampering/wrong key/project/scope/digest/size, endpoint restrictions, refusal before
connection, subprocess environment/logging and precise public-schema TOC handling.
The existing disposable-only `native_backup.py` and application pools are unchanged.

## Manual entry point

Run from `backend` with reviewed Python dependencies, PostgreSQL 17 tools and
PowerShell 7. Export reads the owner connection from a private dotenv file:

```text
python hosted_backup_cli.py export --owner-config PRIVATE_CONFIG_FILE --expected-project PROJECT_REFERENCE --pg-bin POSTGRESQL_BIN_DIRECTORY
```

Before verification, prepare a new empty dedicated loopback database named
`native_purchase_test_backup_` plus 32 hexadecimal characters, with the manifest's
database owner and required NOLOGIN role stubs. The utility does not create global
roles or alter their passwords. Put the connection in a private environment
variable; pass its name rather than the URL:

```text
python hosted_backup_cli.py verify-restore --connection-env PRIVATE_RESTORE_VARIABLE --backup ENCRYPTED_BACKUP_FILE --key-file PRIVATE_KEY_FILE --expected-project PROJECT_REFERENCE --pg-bin POSTGRESQL_BIN_DIRECTORY
```

Preserve the safe receipt, then remove only that disposable target. The private key
is required to recover the archive. The tool is manual, Windows-specific and bounded
to a 64 MiB custom archive. Scheduling, retention and operational restore remain
future work. The actual trial also verified decryption/readback of the encrypted file.

## Remaining gates

This does not verify Supabase Auth, Storage files, Vault, scheduled jobs, managed
services, global role memberships/passwords, or application login/write workflows
on a restored system. Catalog dependency discovery does not prove dynamic managed
calls recover. Those require separate rehearsals. Provider-specific work is
described in [Supabase recovery scope](https://supabase.com/docs/guides/platform/migrating-within-supabase/backup-restore)
and [database-backup limits](https://supabase.com/docs/guides/platform/backups),
including separately retained Storage files.

The [isolated LOGIN hold](ISOLATED_LOGIN_COMPARISON_CHECKPOINT.md) remains unresolved:
fresh session-pooler authentication succeeded after the owner set inventory NOLOGIN.
No credentials were retired or rotated here. Combined credential/recovery,
browser/Data API, deployment and sequential PR checks remain pending. Continue
holding merges and active cutover. No backup schedule or off-device copy is implied.
